from __future__ import annotations

import copy
import json
import re
from typing import Any

from .kobold import _post_chat, clamp_float, clamp_int

SOURCE_TEMPLATE: dict[str, Any] = {
    'title': '',
    'source_name': '',
    'raw_text': '',
    'cleaned_text': '',
    'source_format': 'text',
    'document_type': 'novel_chapter',
    'order_index': 1,
    'chapter_number': 1,
    'scene_number': 0,
    'extra': {
        'part_arc': '',
        'pov': '',
        'tense': 'past',
        'chapter_goal': '',
        'author_notes': '',
        'draft_status': 'draft',
    },
}

MODE_GUIDANCE = {
    'draft_scratch': 'Draft a clean new source ingest JSON payload from the brief and any pasted source text.',
    'fill_missing': 'Keep existing strong details and only fill missing or weak metadata fields where helpful.',
    'rewrite_current': 'Rewrite the current source JSON into a cleaner, more coherent ingest draft while preserving the same core material.',
}

STYLE_GUIDANCE = {
    'strict': 'Stay close to the explicit brief and source material. Only make conservative additions needed to complete the payload cleanly.',
    'balanced': 'Preserve the source material and brief, but infer useful metadata when it improves ingest readiness and structure.',
    'generative': 'Use the brief and source material as a seed, then creatively complete missing metadata so the ingest payload feels specific and ready to use.',
}

STYLE_TEMPERATURES = {
    'strict': 0.18,
    'balanced': 0.36,
    'generative': 0.55,
}


def _clean_mode(mode: str) -> str:
    clean = re.sub(r'[^a-z_]+', '', str(mode or '').strip().lower())
    return clean if clean in MODE_GUIDANCE else 'draft_scratch'



def _clean_style(style: str) -> str:
    clean = re.sub(r'[^a-z_]+', '', str(style or '').strip().lower())
    return clean if clean in STYLE_GUIDANCE else 'balanced'



def _strip_code_fences(text: str) -> str:
    cleaned = str(text or '').strip()
    cleaned = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    return cleaned.strip()



def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError('Source assist returned an empty response.')
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('Source assist did not return valid JSON.')
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception as exc:
        raise ValueError(f'Source assist JSON parse failed: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError('Source assist must return a JSON object.')
    return data



def _merge_on_template(template: Any, payload: Any) -> Any:
    if isinstance(template, dict):
        source = payload if isinstance(payload, dict) else {}
        return {key: _merge_on_template(template[key], source.get(key)) for key in template.keys()}
    if isinstance(template, list):
        return payload if isinstance(payload, list) else copy.deepcopy(template)
    if isinstance(template, int):
        try:
            return int(payload)
        except Exception:
            return template
    if isinstance(template, float):
        try:
            return float(payload)
        except Exception:
            return template
    if isinstance(template, str):
        return str(payload or '').strip() if payload is not None else template
    return copy.deepcopy(template)



def _fill_missing(existing: Any, drafted: Any) -> Any:
    if isinstance(existing, dict) and isinstance(drafted, dict):
        merged = copy.deepcopy(existing)
        for key, value in drafted.items():
            merged[key] = _fill_missing(merged.get(key), value)
        return merged
    if isinstance(existing, list) and existing:
        return copy.deepcopy(existing)
    if existing in (None, '', 0) and drafted not in (None, ''):
        return copy.deepcopy(drafted)
    return copy.deepcopy(existing if existing not in (None, '') else drafted)



def _parse_existing_json(current_json: str) -> dict[str, Any]:
    clean = str(current_json or '').strip()
    if not clean:
        return {}
    try:
        parsed = json.loads(clean)
    except Exception as exc:
        raise ValueError(f'Current assist JSON is not valid JSON: {exc}') from exc
    if not isinstance(parsed, dict):
        raise ValueError('Current assist JSON must be a JSON object.')
    return _merge_on_template(SOURCE_TEMPLATE, parsed)



def _payload_has_meaningful_values(payload: dict[str, Any] | None) -> bool:
    current = payload if isinstance(payload, dict) else {}
    extra = current.get('extra') if isinstance(current.get('extra'), dict) else {}
    text_fields = [
        current.get('title'),
        current.get('source_name'),
        current.get('raw_text'),
        current.get('cleaned_text'),
        extra.get('part_arc'),
        extra.get('pov'),
        extra.get('chapter_goal'),
        extra.get('author_notes'),
    ]
    if any(str(value or '').strip() for value in text_fields):
        return True
    if str(current.get('document_type') or '').strip() not in {'', 'novel_chapter'}:
        return True
    if int(current.get('order_index') or 0) > 1 or int(current.get('chapter_number') or 0) > 1 or int(current.get('scene_number') or 0) > 0:
        return True
    if str(extra.get('draft_status') or '').strip() not in {'', 'draft'}:
        return True
    if str(extra.get('tense') or '').strip() not in {'', 'past'}:
        return True
    return False


def _infer_source_format(source_name: str = '', current_payload: dict[str, Any] | None = None) -> str:
    filename = str(source_name or '').strip().lower()
    if filename.endswith('.md'):
        return 'markdown'
    current = current_payload if isinstance(current_payload, dict) else {}
    existing = str(current.get('source_format') or '').strip().lower()
    if existing in {'text', 'markdown'}:
        return existing
    return 'text'



def _source_preview(text: str, limit: int = 12000) -> tuple[str, bool]:
    clean = str(text or '').strip()
    if len(clean) <= limit:
        return clean, False
    return clean[:limit], True


async def draft_source_document_json(
    *,
    brief: str = '',
    source_text: str = '',
    source_name: str = '',
    current_json: str = '',
    mode: str = 'draft_scratch',
    draft_style: str = 'balanced',
    model: str = 'default',
    max_tokens: int = 1200,
    temperature: float | None = None,
    top_p: float = 0.92,
    top_k: int = 50,
) -> dict[str, Any]:
    clean_mode = _clean_mode(mode)
    clean_style = _clean_style(draft_style)
    brief_text = str(brief or '').strip()
    source_body = str(source_text or '').strip()
    current = _parse_existing_json(current_json)
    has_current = _payload_has_meaningful_values(current)
    if clean_mode == 'draft_scratch' and not brief_text and not source_body:
        raise ValueError('Add a brief or paste a source text/file before drafting source ingest JSON.')
    if clean_mode != 'draft_scratch' and not has_current and not source_body and not brief_text:
        raise ValueError('Load current source JSON, a brief, or source text before using fill missing or rewrite mode.')

    preview_text, was_truncated = _source_preview(source_body)
    system_prompt = (
        'You are a structured source ingest assistant for a creative writing workspace. '
        'Return only one valid JSON object. '
        'No markdown. No code fences. No commentary. No explanations. '
        'Keep the exact schema shape provided. '
        'Do not invent project IDs or database IDs. '
        'Do not duplicate the full source text into cleaned_text unless it is genuinely needed. '
        'Focus on strong ingest metadata: title, document_type, order/chapter/scene placement, and extra fields.'
    )
    user_prompt = (
        f'Draft mode: {clean_mode}\n'
        f'Mode instruction: {MODE_GUIDANCE[clean_mode]}\n'
        f'Drafting style: {clean_style}\n'
        f'Style instruction: {STYLE_GUIDANCE[clean_style]}\n\n'
        'Return JSON matching this exact schema shape:\n'
        f'{json.dumps(SOURCE_TEMPLATE, ensure_ascii=False, indent=2)}\n\n'
        'Schema rules:\n'
        '- raw_text will be injected by the app after generation when source text is provided; do not try to repeat the whole source body there\n'
        '- source_name should be a filename-like label if one is obvious\n'
        '- source_format must be text or markdown\n'
        '- document_type should be one of novel_chapter, novel_scene_section, novel_outline, author_notes, reference_excerpt\n'
        '- tense should usually be past or present\n'
        '- draft_status should be draft, outline, revision, polish, or final\n'
        '- keep cleaned_text short or empty; do not echo huge bodies of text\n\n'
        f'Current JSON draft:\n{json.dumps(current, ensure_ascii=False, indent=2) if current else "{}"}\n\n'
        f'User brief:\n{brief_text or "(no extra brief provided)"}\n\n'
        f'Source name:\n{source_name or "(none)"}\n\n'
        f'Source text preview ({"truncated" if was_truncated else "full"}):\n{preview_text or "(no source text provided)"}\n\n'
        'Return one JSON object only.'
    )

    response = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 280, 2200, 1200),
            'temperature': clamp_float(STYLE_TEMPERATURES[clean_style] if temperature is None else temperature, 0.0, 1.2, STYLE_TEMPERATURES[clean_style]),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 50),
            'repetition_penalty': 1.05,
        },
        timeout=300.0,
    )

    parsed = _extract_json_object(response.get('content', ''))
    drafted = _merge_on_template(SOURCE_TEMPLATE, parsed)

    if clean_mode == 'fill_missing' and current:
        result = _fill_missing(current, drafted)
    elif clean_mode == 'rewrite_current' and current:
        merged = _merge_on_template(SOURCE_TEMPLATE, current)
        result = _merge_on_template(merged, drafted)
    else:
        result = drafted

    result['source_name'] = str(source_name or result.get('source_name') or current.get('source_name') or '').strip()
    result['source_format'] = _infer_source_format(result.get('source_name', ''), result)
    if source_body:
        result['raw_text'] = source_body
        if str(result.get('cleaned_text') or '').strip() == source_body.strip():
            result['cleaned_text'] = ''
    elif current.get('raw_text'):
        result['raw_text'] = str(current.get('raw_text') or '')

    return {
        'mode': clean_mode,
        'draft_style': clean_style,
        'draft_json': json.dumps(result, ensure_ascii=False, indent=2),
        'record': result,
        'source_name': result.get('source_name', ''),
        'source_text_truncated_for_prompt': was_truncated,
        'finish_reason': response.get('finish_reason', ''),
        'reasoning_stripped': bool(response.get('reasoning_stripped')),
    }
