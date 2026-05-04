from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any

try:
    import json5  # type: ignore
except Exception:  # pragma: no cover
    json5 = None

from ..contracts.roleplay_v2_records import canonical_entity_kind
from .kobold import _post_chat, clamp_float, clamp_int
from .roleplay_v2_builder_normalizer import normalize_builder_payload
from .roleplay_v2_builder_workspace import FIRST_IMPLEMENTED_BUILDERS, get_builder_template_payload, load_builder_record

MODE_GUIDANCE = {
    'draft_scratch': 'Draft a clean new Forge V2 builder JSON payload from the brief.',
    'fill_missing': 'Keep existing strong details and only fill missing or weak areas where helpful.',
    'rewrite_current': 'Rewrite the current Forge V2 JSON into a cleaner, more coherent draft while preserving the same core intent and links.',
}

STYLE_GUIDANCE = {
    'strict': 'Stay close to the explicit brief. Only make conservative additions needed to complete the schema cleanly.',
    'balanced': 'Preserve the core brief, but invent useful missing details when they improve coherence, specificity, and roleplay usability.',
    'generative': 'Use the brief as a seed, then creatively complete missing details so the builder record feels specific, reusable, and alive while still matching the selected context.',
}

STYLE_TEMPERATURES = {
    'strict': 0.18,
    'balanced': 0.36,
    'generative': 0.55,
}

ASSIST_CHAT_TIMEOUT_SECONDS = 600.0


_SCOPE_DEFAULTS_BY_KIND: dict[str, dict[str, str]] = {
    'universe': {},
    'world': {'universe_id': 'universe_id'},
    'region': {'world_id': 'world_id'},
    'city': {'world_id': 'world_id', 'region_id': 'region_id'},
    'location': {'universe_id': 'universe_id', 'world_id': 'world_id', 'region_id': 'region_id', 'city_id': 'city_id'},
    'character': {
        'origin_world_id': 'world_id',
        'current_world_id': 'world_id',
        'origin_region_id': 'region_id',
        'current_region_id': 'region_id',
        'origin_city_id': 'city_id',
        'current_city_id': 'city_id',
        'origin_location_id': 'location_id',
        'current_location_id': 'location_id',
    },
    'organization': {'universe_id': 'universe_id', 'world_id': 'world_id', 'region_id': 'region_id', 'city_id': 'city_id', 'base_location_id': 'location_id'},
    'artifact': {'world_id': 'world_id', 'region_id': 'region_id', 'city_id': 'city_id', 'location_id': 'location_id'},
    'ritual': {'world_id': 'world_id', 'region_id': 'region_id', 'location_id': 'location_id'},
    'cycle': {'universe_id': 'universe_id', 'world_id': 'world_id', 'region_id': 'region_id', 'location_id': 'location_id'},
    'creature': {'world_id': 'world_id', 'region_id': 'region_id', 'location_id': 'location_id'},
    'legend': {'universe_id': 'universe_id', 'world_id': 'world_id', 'region_id': 'region_id', 'location_id': 'location_id'},
    'scenario': {'universe_id': 'universe_id', 'world_id': 'world_id', 'region_id': 'region_id', 'city_id': 'city_id', 'location_id': 'location_id'},
}


_RELATED_DEFAULTS_BY_KIND: dict[str, dict[str, str]] = {
    'character': {'organization_ids': 'organization_ids'},
    'scenario': {'organization_ids': 'organization_ids'},
}


SUMMARY_FIELD_HINTS = {
    'character': 'Prioritize fields.identity, appearance_presence, personality_behavior_speech, goals_desire_fear_wounds, and story_roleplay_use.',
    'world': 'Prioritize fields.identity, atmosphere, culture, systems, factions, and story_roleplay_use style sections if present.',
    'location': 'Prioritize identity, atmosphere, function, scene utility, and hidden tension.',
    'organization': 'Prioritize identity, public face, internal logic, reputation, membership dynamics, and story utility.',
    'scenario': 'Prioritize premise, cast hooks, playable tension, scene openings, and continuity-ready conflict structure.',
}


def _clean_kind(kind: str) -> str:
    clean = canonical_entity_kind(kind)
    if clean not in FIRST_IMPLEMENTED_BUILDERS:
        raise ValueError('Choose a supported Forge builder workflow first.')
    return clean



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



def _repair_loose_json_text(text: str) -> str:
    repaired = str(text or '').strip()
    if not repaired:
        return repaired
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    repaired = re.sub(r'(["0-9}\]])(\s*\n\s*)(")', r'\1,\2\3', repaired)
    repaired = re.sub(r'(["0-9}\]])(\s+)(")', r'\1,\2\3', repaired)
    return repaired



def _parse_pythonish_object(text: str) -> dict[str, Any] | None:
    candidate = str(text or '').strip()
    if not candidate:
        return None
    candidate = re.sub(r'\btrue\b', 'True', candidate, flags=re.I)
    candidate = re.sub(r'\bfalse\b', 'False', candidate, flags=re.I)
    candidate = re.sub(r'\bnull\b', 'None', candidate, flags=re.I)
    try:
        data = ast.literal_eval(candidate)
    except Exception:
        return None
    return data if isinstance(data, dict) else None



def _parse_candidate_json_object(text: str) -> dict[str, Any] | None:
    candidate = str(text or '').strip()
    parsers = [json.loads]
    if json5 is not None:
        parsers.append(json5.loads)
    for parser in parsers:
        try:
            data = parser(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    repaired = _repair_loose_json_text(candidate)
    if repaired != candidate:
        for parser in parsers:
            try:
                data = parser(repaired)
            except Exception:
                continue
            if isinstance(data, dict):
                return data
    pythonish = _parse_pythonish_object(candidate)
    if isinstance(pythonish, dict):
        return pythonish
    if repaired != candidate:
        pythonish = _parse_pythonish_object(repaired)
        if isinstance(pythonish, dict):
            return pythonish
    return None



def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError('Forge assist returned an empty response.')
    parsed = _parse_candidate_json_object(cleaned)
    if parsed is not None:
        return parsed
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('Forge assist did not return valid JSON.')
    candidate = cleaned[start:end + 1]
    parsed = _parse_candidate_json_object(candidate)
    if parsed is not None:
        return parsed
    try:
        json.loads(candidate)
    except Exception as exc:
        raise ValueError(f'Forge assist JSON parse failed: {exc}') from exc
    raise ValueError('Forge assist must return one JSON object.')



async def _repair_json_with_backend(*, model: str, raw_text: str, template: dict[str, Any], kind: str) -> str:
    repair_prompt = (
        'Repair the malformed JSON below into one valid JSON object. '
        'Return JSON only. No markdown. No commentary. No code fences. '
        'Do not change the intended meaning. '
        'Do not add unknown keys. '
        'Keep the exact schema shape from the provided template.\n\n'
        f'Target kind: {kind}\n\n'
        f'Template shape:\n{json.dumps(template, ensure_ascii=False, indent=2)}\n\n'
        f'Malformed JSON to repair:\n{raw_text}'
    )
    response = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You are a strict JSON repair assistant. Return one valid JSON object only.'},
                {'role': 'user', 'content': repair_prompt},
            ],
            'max_tokens': clamp_int(2200, 280, 2600, 2200),
            'temperature': 0.05,
            'top_p': 0.9,
            'top_k': 40,
            'repetition_penalty': 1.02,
        },
        timeout=ASSIST_CHAT_TIMEOUT_SECONDS,
    )
    return str(response.get('content', '') or '')


def _merge_on_template(template: Any, payload: Any) -> Any:
    if isinstance(template, dict):
        source = payload if isinstance(payload, dict) else {}
        return {key: _merge_on_template(template[key], source.get(key)) for key in template.keys()}
    if isinstance(template, list):
        return copy.deepcopy(payload) if isinstance(payload, list) else copy.deepcopy(template)
    if isinstance(template, bool):
        return bool(payload) if isinstance(payload, bool) else copy.deepcopy(template)
    if isinstance(template, int) and not isinstance(template, bool):
        try:
            return int(payload)
        except Exception:
            return copy.deepcopy(template)
    if isinstance(template, float):
        try:
            return float(payload)
        except Exception:
            return copy.deepcopy(template)
    if isinstance(template, str):
        return str(payload or '').strip() if payload is not None else copy.deepcopy(template)
    return copy.deepcopy(template)



def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return value == 0
    return False



def _fill_missing(existing: Any, drafted: Any) -> Any:
    if isinstance(existing, dict) and isinstance(drafted, dict):
        merged = copy.deepcopy(existing)
        for key, value in drafted.items():
            merged[key] = _fill_missing(merged.get(key), value)
        return merged
    if isinstance(existing, list) and existing:
        return copy.deepcopy(existing)
    if _is_empty(existing) and not _is_empty(drafted):
        return copy.deepcopy(drafted)
    return copy.deepcopy(existing if not _is_empty(existing) else drafted)



def _parse_existing_json(kind: str, current_json: str) -> dict[str, Any]:
    clean = str(current_json or '').strip()
    if not clean:
        return {}
    try:
        parsed = json.loads(clean)
    except Exception as exc:
        raise ValueError(f'Current Forge JSON is not valid JSON: {exc}') from exc
    if not isinstance(parsed, dict):
        raise ValueError('Current Forge JSON must be a JSON object.')
    normalized = normalize_builder_payload(kind=kind, payload=parsed)
    return normalized.get('normalized_payload') or {}



def _clean_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    org_ids = source.get('organization_ids')
    if isinstance(org_ids, str):
        try:
            org_ids = json.loads(org_ids)
        except Exception:
            org_ids = [org_ids]
    if not isinstance(org_ids, list):
        org_ids = []
    return {
        'universe_id': str(source.get('universe_id') or '').strip(),
        'world_id': str(source.get('world_id') or '').strip(),
        'region_id': str(source.get('region_id') or '').strip(),
        'city_id': str(source.get('city_id') or '').strip(),
        'location_id': str(source.get('location_id') or '').strip(),
        'scenario_id': str(source.get('scenario_id') or '').strip(),
        'species_hint': str(source.get('species_hint') or '').strip(),
        'organization_ids': [str(value or '').strip() for value in org_ids if str(value or '').strip()],
    }



def _record_brief(record_id: str) -> dict[str, Any] | None:
    clean_id = str(record_id or '').strip()
    if not clean_id:
        return None
    try:
        payload = load_builder_record(clean_id)
    except Exception:
        return None
    builder_payload = payload.get('builder_payload') if isinstance(payload, dict) else {}
    if not isinstance(builder_payload, dict):
        return None
    result = {
        'id': builder_payload.get('id') or clean_id,
        'kind': builder_payload.get('kind') or '',
        'label': builder_payload.get('label') or '',
        'display_label': builder_payload.get('display_label') or '',
        'summary': builder_payload.get('summary') or '',
    }
    return {key: value for key, value in result.items() if value}



def _context_packet(context: dict[str, Any]) -> dict[str, Any]:
    packet: dict[str, Any] = {
        'selected_ids': {key: value for key, value in context.items() if key.endswith('_id') and value},
    }
    if context.get('species_hint'):
        packet['species_hint'] = context['species_hint']
    if context.get('organization_ids'):
        packet['organization_ids'] = context['organization_ids']
    for key in ('universe_id', 'world_id', 'region_id', 'city_id', 'location_id', 'scenario_id'):
        brief = _record_brief(context.get(key, ''))
        if brief:
            packet[key[:-3]] = brief
    organizations = [_record_brief(record_id) for record_id in context.get('organization_ids') or []]
    organizations = [item for item in organizations if item]
    if organizations:
        packet['organizations'] = organizations[:8]
    return packet



def _inject_context_defaults(kind: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    links = result.get('links') if isinstance(result.get('links'), dict) else {}
    scope = links.get('scope') if isinstance(links.get('scope'), dict) else {}
    related = links.get('related') if isinstance(links.get('related'), dict) else {}

    for scope_key, context_key in (_SCOPE_DEFAULTS_BY_KIND.get(kind) or {}).items():
        if scope_key in scope and _is_empty(scope.get(scope_key)) and not _is_empty(context.get(context_key)):
            scope[scope_key] = copy.deepcopy(context.get(context_key))

    for related_key, context_key in (_RELATED_DEFAULTS_BY_KIND.get(kind) or {}).items():
        if related_key in related and _is_empty(related.get(related_key)) and context.get(context_key):
            related[related_key] = copy.deepcopy(context.get(context_key))

    if kind == 'character' and context.get('species_hint'):
        fields = result.get('fields') if isinstance(result.get('fields'), dict) else {}
        identity = fields.get('identity') if isinstance(fields.get('identity'), dict) else {}
        if 'species_or_race' in identity and _is_empty(identity.get('species_or_race')):
            identity['species_or_race'] = str(context.get('species_hint') or '').strip()

    return result



def _schema_prompt_lines(payload: Any, prefix: str = '') -> list[str]:
    lines: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            dotted = f'{prefix}.{key}' if prefix else key
            if isinstance(value, dict):
                lines.append(f'- {dotted}: object')
                lines.extend(_schema_prompt_lines(value, dotted))
            elif isinstance(value, list):
                lines.append(f'- {dotted}: array')
            else:
                lines.append(f'- {dotted}: {type(value).__name__}')
    return lines


async def draft_builder_json(
    kind: str,
    brief: str,
    *,
    mode: str = 'draft_scratch',
    draft_style: str = 'balanced',
    current_json: str = '',
    model: str = 'default',
    context: dict[str, Any] | None = None,
    max_tokens: int = 1500,
    temperature: float | None = None,
    top_p: float = 0.92,
    top_k: int = 50,
) -> dict[str, Any]:
    clean_kind = _clean_kind(kind)
    clean_mode = _clean_mode(mode)
    clean_style = _clean_style(draft_style)
    brief_text = str(brief or '').strip()
    current = _parse_existing_json(clean_kind, current_json)
    context_payload = _clean_context(context)
    template_info = get_builder_template_payload(clean_kind)
    template = copy.deepcopy(template_info.get('json_template_payload') or {})
    if not template:
        raise ValueError('Template payload is not available for this builder yet.')

    if clean_mode == 'draft_scratch' and not brief_text:
        raise ValueError('Add a short brief before drafting Forge JSON with AI.')
    if clean_mode != 'draft_scratch' and not current and not brief_text:
        raise ValueError('Load current Forge JSON or add a brief before using fill missing or rewrite mode.')

    context_packet = _context_packet(context_payload)
    system_prompt = (
        'You are a structured Forge V2 builder drafting assistant. '
        'Return only one valid JSON object. '
        'No markdown. No code fences. No commentary. No explanations. '
        'Keep the exact schema shape from the provided template. '
        'Do not add unknown keys. '
        'Do not flatten nested objects. '
        'Preserve the V2 top-level structure including links, fields, memory_hints, and meta. '
        'Never invent database IDs or foreign IDs. '
        'Only keep IDs that already exist in the current draft or selected context. '
        'Write concise, production-ready field text that is actually useful in roleplay and authoring.'
    )
    user_prompt = (
        f'Target Forge builder kind: {clean_kind}\n'
        f'Draft mode: {clean_mode}\n'
        f'Mode instruction: {MODE_GUIDANCE[clean_mode]}\n'
        f'Drafting style: {clean_style}\n'
        f'Style instruction: {STYLE_GUIDANCE[clean_style]}\n'
        f'Field emphasis: {SUMMARY_FIELD_HINTS.get(clean_kind, "Prioritize the fields most likely to make this record usable in Forge, Scene, and Stories.")}\n\n'
        'Return JSON matching this exact V2 schema shape:\n'
        f'{json.dumps(template, ensure_ascii=False, indent=2)}\n\n'
        'Schema notes:\n'
        f'{chr(10).join(_schema_prompt_lines(template))}\n\n'
        f'Selected context packet:\n{json.dumps(context_packet, ensure_ascii=False, indent=2)}\n\n'
        f'Current Forge JSON draft:\n{json.dumps(current, ensure_ascii=False, indent=2) if current else "{}"}\n\n'
        f'User brief:\n{brief_text or "(no extra brief provided)"}\n\n'
        'Rules:\n'
        '- Preserve explicit facts from the user brief.\n'
        '- Keep nested V2 structure intact.\n'
        '- Fill blank fields with believable specifics instead of repeating the same phrase everywhere.\n'
        '- Keep ids empty unless they already exist in current JSON or selected context.\n'
        '- Keep arrays schema-aligned.\n'
        '- Do not convert V2 nested fields into flat legacy keys.\n\n'
        'Return one JSON object only.'
    )

    response = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 280, 2400, 1500),
            'temperature': clamp_float(STYLE_TEMPERATURES[clean_style] if temperature is None else temperature, 0.0, 1.2, STYLE_TEMPERATURES[clean_style]),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 50),
            'repetition_penalty': 1.05,
        },
        timeout=ASSIST_CHAT_TIMEOUT_SECONDS,
    )

    raw_response_text = str(response.get('content', '') or '')
    try:
        parsed = _extract_json_object(raw_response_text)
    except ValueError as parse_error:
        repaired_text = await _repair_json_with_backend(model=model, raw_text=raw_response_text, template=template, kind=clean_kind)
        try:
            parsed = _extract_json_object(repaired_text)
        except ValueError:
            raise parse_error
    drafted = _merge_on_template(template, parsed)

    if clean_mode == 'fill_missing' and current:
        result = _fill_missing(current, drafted)
    elif clean_mode == 'rewrite_current' and current:
        result = _merge_on_template(_merge_on_template(template, current), drafted)
    else:
        result = drafted

    result['kind'] = clean_kind
    result = _inject_context_defaults(clean_kind, result, context_payload)
    normalized = normalize_builder_payload(kind=clean_kind, payload=result)
    final_payload = normalized.get('normalized_payload') or result

    return {
        'ok': True,
        'kind': clean_kind,
        'mode': clean_mode,
        'draft_style': clean_style,
        'draft_json': json.dumps(final_payload, ensure_ascii=False, indent=2),
        'record': final_payload,
        'context_packet': context_packet,
        'normalization': normalized.get('normalization') or {},
        'template_kind': clean_kind,
        'finish_reason': response.get('finish_reason', ''),
        'reasoning_stripped': bool(response.get('reasoning_stripped')),
    }


def _pretty_label_python(value: str) -> str:
    raw = str(value or '').strip().replace('-', '_')
    if not raw:
        return ''
    parts = [part for part in raw.split('_') if part]
    formatted: list[str] = []
    for part in parts:
        lower = part.lower()
        if lower == 'id':
            formatted.append('ID')
        elif lower == 'ids':
            formatted.append('IDs')
        elif lower == 'json':
            formatted.append('JSON')
        else:
            formatted.append(lower[:1].upper() + lower[1:])
    return ' '.join(formatted)



def build_parser_safe_builder_markdown_template(kind: str) -> str:
    clean_kind = _clean_kind(kind)
    template_info = get_builder_template_payload(clean_kind)
    template = copy.deepcopy(template_info.get('json_template_payload') or {})
    if not template:
        raise ValueError('Template payload is not available for this builder yet.')
    title_label = 'Name' if clean_kind == 'character' else 'Title'
    lines = [f'# {_pretty_label_python(clean_kind)} Builder Template', '', '## Metadata']
    lines.extend([
        f'{title_label}:',
        'Display Name:',
        'Summary:',
        'Canon Status:',
        'Visibility:',
        'Tags:',
        'Tone Tags:',
        'Source Container ID:',
        '',
    ])
    links = template.get('links') if isinstance(template.get('links'), dict) else {}
    scope = links.get('scope') if isinstance(links.get('scope'), dict) else {}
    related = links.get('related') if isinstance(links.get('related'), dict) else {}
    if scope or related:
        lines.append('## Links')
        for key in scope.keys():
            lines.append(f'{_pretty_label_python(key)}:')
        for key in related.keys():
            lines.append(f'{_pretty_label_python(key)}:')
        lines.append('')
    fields = template.get('fields') if isinstance(template.get('fields'), dict) else {}
    for section_key, section_value in fields.items():
        if not isinstance(section_value, dict):
            continue
        lines.append(f'## {_pretty_label_python(section_key)}')
        for field_key in section_value.keys():
            lines.append(f'{_pretty_label_python(field_key)}:')
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


async def draft_builder_markdown(
    kind: str,
    brief: str,
    *,
    mode: str = 'draft_scratch',
    draft_style: str = 'balanced',
    current_json: str = '',
    model: str = 'default',
    context: dict[str, Any] | None = None,
    max_tokens: int = 1800,
    temperature: float | None = None,
    top_p: float = 0.92,
    top_k: int = 50,
) -> dict[str, Any]:
    clean_kind = _clean_kind(kind)
    clean_mode = _clean_mode(mode)
    clean_style = _clean_style(draft_style)
    brief_text = str(brief or '').strip()
    current = _parse_existing_json(clean_kind, current_json)
    context_payload = _clean_context(context)
    context_packet = _context_packet(context_payload)
    markdown_template = build_parser_safe_builder_markdown_template(clean_kind)
    if clean_mode == 'draft_scratch' and not brief_text:
        raise ValueError('Add a short brief before drafting Forge markdown with AI.')
    if clean_mode != 'draft_scratch' and not current and not brief_text:
        raise ValueError('Load current Forge JSON or add a brief before using fill missing or rewrite mode.')

    system_prompt = (
        'You are a structured Forge V2 markdown drafting assistant. '
        'Return markdown only. No JSON. No code fences. No commentary. No explanations. '
        'Keep every heading and field label exactly as provided in the template. '
        'Only fill values after the colons. '
        'Do not rename sections. '
        'Leave unknown IDs blank. '
        'Do not invent foreign IDs.'
    )
    user_prompt = (
        f'Target Forge builder kind: {clean_kind}\n'
        f'Draft mode: {clean_mode}\n'
        f'Mode instruction: {MODE_GUIDANCE[clean_mode]}\n'
        f'Drafting style: {clean_style}\n'
        f'Style instruction: {STYLE_GUIDANCE[clean_style]}\n'
        f'Field emphasis: {SUMMARY_FIELD_HINTS.get(clean_kind, "Prioritize the fields most likely to make this record usable in Forge, Scene, and Stories.")}\n\n'
        'Return markdown matching this exact parser-safe template structure:\n'
        f'{markdown_template}\n\n'
        f'Selected context packet:\n{json.dumps(context_packet, ensure_ascii=False, indent=2)}\n\n'
        f'Current Forge JSON draft for reference:\n{json.dumps(current, ensure_ascii=False, indent=2) if current else "{}"}\n\n'
        f'User brief:\n{brief_text or "(no extra brief provided)"}\n\n'
        'Rules:\n'
        '- Preserve explicit facts from the brief.\n'
        '- Keep the headings and field labels exactly as written in the template.\n'
        '- Fill only the value side of each field.\n'
        '- Use short bullet lists only when a field clearly wants a list.\n'
        '- Keep IDs blank unless already known from the current draft or context.\n'
        '- Do not output unsupported extra sections.\n\n'
        'Return the completed markdown template only.'
    )
    response = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 280, 2600, 1800),
            'temperature': clamp_float(STYLE_TEMPERATURES[clean_style] if temperature is None else temperature, 0.0, 1.2, STYLE_TEMPERATURES[clean_style]),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 50),
            'repetition_penalty': 1.05,
        },
        timeout=ASSIST_CHAT_TIMEOUT_SECONDS,
    )
    draft_markdown = _strip_code_fences(response.get('content', ''))
    if not draft_markdown:
        raise ValueError('Forge assist returned an empty markdown draft.')
    return {
        'ok': True,
        'kind': clean_kind,
        'mode': clean_mode,
        'draft_style': clean_style,
        'draft_markdown': draft_markdown,
        'draft_text': draft_markdown,
        'template_markdown': markdown_template,
        'context_packet': context_packet,
        'message': f'{_pretty_label_python(clean_kind)} Forge markdown draft ready.',
        'finish_reason': response.get('finish_reason', ''),
        'reasoning_stripped': bool(response.get('reasoning_stripped')),
    }
