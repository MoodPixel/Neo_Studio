from __future__ import annotations

import copy
import json
import re
from typing import Any

from .kobold import _post_chat, clamp_float, clamp_int
from .roleplay_library_exports import build_template_payload
from .roleplay_library_imports import TITLE_KEY_BY_KIND, _normalize_kind
from .roleplay_library_store import get_record

SUPPORTED_KINDS = [
    'legend',
    'universe',
    'world',
    'region',
    'city',
    'location',
    'organization',
    'character',
    'artifact',
    'ritual',
    'cycle',
    'creature',
    'pack',
    'scenario',
]

MODE_GUIDANCE = {
    'draft_scratch': 'Draft a clean new schema record from the brief.',
    'fill_missing': 'Keep existing strong details and only fill missing or weak areas where helpful.',
    'rewrite_current': 'Rewrite the current JSON into a cleaner, more coherent draft while preserving the same core intent and links.',
}

STYLE_GUIDANCE = {
    'strict': 'Stay close to the explicit brief. Only make minimal, conservative additions needed to complete the schema cleanly.',
    'balanced': 'Preserve the core brief, but invent useful missing details when they improve coherence, specificity, and roleplay usability.',
    'generative': 'Use the brief as a seed, then creatively complete missing details so the record feels fully usable, specific, and alive while still matching the selected context.',
}

STYLE_TEMPERATURES = {
    'strict': 0.18,
    'balanced': 0.38,
    'generative': 0.58,
}

SUMMARY_KEYS = [
    'name', 'display_name', 'title', 'summary', 'group_type', 'realm_type', 'region_type', 'city_type', 'location_type',
    'tone', 'premise', 'objective', 'lore', 'society_notes', 'faith_notes', 'people_notes', 'atmosphere', 'beliefs',
    'goals', 'reputation', 'public_face', 'hidden_truth', 'species', 'category', 'function_label', 'leadership',
    'location_label', 'occupation', 'designation', 'speech_style', 'personality'
]



def _clean_kind(kind: str) -> str:
    clean = _normalize_kind(kind)
    if clean not in SUPPORTED_KINDS:
        raise ValueError('Choose a supported library kind first.')
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



def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError('AI draft returned an empty response.')
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('AI draft did not return valid JSON.')
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception as exc:
        raise ValueError(f'AI draft JSON parse failed: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError('AI draft must return a JSON object.')
    return data



def _remove_placeholder_fields(payload: dict[str, Any]) -> dict[str, Any]:
    clean = copy.deepcopy(payload)
    clean.pop('id', None)
    clean.pop('meta', None)
    return clean



def _prepare_template(kind: str) -> dict[str, Any]:
    template = _remove_placeholder_fields(build_template_payload(kind))
    title_key = TITLE_KEY_BY_KIND[kind]
    if title_key in template:
        template[title_key] = ''
    return template



def _parse_existing_json(raw: str) -> dict[str, Any]:
    text = str(raw or '').strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ValueError(f'Could not parse current JSON editor content: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('Current JSON editor content must be one JSON object.')
    return payload



def _merge_on_template(template: Any, incoming: Any) -> Any:
    if isinstance(template, dict):
        source = incoming if isinstance(incoming, dict) else {}
        merged: dict[str, Any] = {}
        for key, base_value in template.items():
            if key in source:
                merged[key] = _merge_on_template(base_value, source.get(key))
            else:
                merged[key] = copy.deepcopy(base_value)
        return merged
    if isinstance(template, list):
        if isinstance(incoming, list):
            return copy.deepcopy(incoming)
        return copy.deepcopy(template)
    if incoming is None:
        return copy.deepcopy(template)
    return copy.deepcopy(incoming)



def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False



def _fill_missing(current: Any, drafted: Any) -> Any:
    if isinstance(current, dict) and isinstance(drafted, dict):
        merged: dict[str, Any] = {}
        keys = set(current.keys()) | set(drafted.keys())
        for key in keys:
            current_value = current.get(key)
            drafted_value = drafted.get(key)
            if isinstance(current_value, (dict, list)) and isinstance(drafted_value, type(current_value)):
                merged[key] = _fill_missing(current_value, drafted_value)
                continue
            merged[key] = copy.deepcopy(drafted_value if _is_empty(current_value) else current_value)
        return merged
    if isinstance(current, list):
        return copy.deepcopy(drafted if _is_empty(current) else current)
    return copy.deepcopy(drafted if _is_empty(current) else current)



def _preserve_existing_identity(result: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    for key in ['id', 'meta']:
        if key in current and current.get(key):
            result[key] = copy.deepcopy(current[key])
    for key in [
        'world_id', 'region_id', 'city_id', 'location_id', 'universe_id', 'parent_region_id', 'parent_location_id',
        'anchor_type', 'current_world_id', 'current_region_id', 'current_city_id', 'current_location_id',
        'origin_world_id', 'origin_region_id', 'origin_city_id', 'origin_location_id', 'base_location_id',
        'location_region_id', 'location_city_id', 'parent_organization_id'
    ]:
        if key in current and current.get(key) and (key not in result or _is_empty(result.get(key))):
            result[key] = copy.deepcopy(current[key])
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
                kind = type(value).__name__
                lines.append(f'- {dotted}: {kind}')
    return lines



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



def _record_label(record: dict[str, Any] | None) -> str:
    item = record if isinstance(record, dict) else {}
    return str(item.get('display_name') or item.get('name') or item.get('title') or '').strip()



def _compact_record(record: dict[str, Any] | None) -> dict[str, Any]:
    item = record if isinstance(record, dict) else {}
    compact: dict[str, Any] = {}
    for key in ['id', 'kind', 'universe_id', 'world_id', 'region_id', 'city_id', 'location_id', 'base_location_id'] + SUMMARY_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            compact[key] = value.strip()
        elif value not in (None, '', [], {}):
            compact[key] = value
    return compact



def _resolve_context_links(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = dict(context)
    records: dict[str, Any] = {
        'universe': None,
        'world': None,
        'region': None,
        'city': None,
        'location': None,
        'scenario': None,
        'organizations': [],
    }

    if resolved['scenario_id']:
        records['scenario'] = get_record('scenario', resolved['scenario_id'])
        scenario = records['scenario'] or {}
        if not resolved['world_id']:
            resolved['world_id'] = str(scenario.get('world_id') or '').strip()
        if not resolved['universe_id']:
            resolved['universe_id'] = str(scenario.get('universe_id') or '').strip()
        if not resolved['location_id']:
            resolved['location_id'] = str(scenario.get('location_id') or '').strip()
        if not resolved['city_id']:
            resolved['city_id'] = str(scenario.get('location_city_id') or '').strip()
        if not resolved['region_id']:
            resolved['region_id'] = str(scenario.get('location_region_id') or '').strip()

    if resolved['location_id']:
        records['location'] = get_record('location', resolved['location_id'])
        location = records['location'] or {}
        resolved['city_id'] = resolved['city_id'] or str(location.get('city_id') or '').strip()
        resolved['region_id'] = resolved['region_id'] or str(location.get('region_id') or '').strip()
        resolved['world_id'] = resolved['world_id'] or str(location.get('world_id') or '').strip()
        resolved['universe_id'] = resolved['universe_id'] or str(location.get('universe_id') or '').strip()

    if resolved['city_id']:
        records['city'] = get_record('city', resolved['city_id'])
        city = records['city'] or {}
        resolved['region_id'] = resolved['region_id'] or str(city.get('region_id') or '').strip()
        resolved['world_id'] = resolved['world_id'] or str(city.get('world_id') or '').strip()

    if resolved['region_id']:
        records['region'] = get_record('region', resolved['region_id'])
        region = records['region'] or {}
        resolved['world_id'] = resolved['world_id'] or str(region.get('world_id') or '').strip()

    if resolved['world_id']:
        records['world'] = get_record('world', resolved['world_id'])
        world = records['world'] or {}
        resolved['universe_id'] = resolved['universe_id'] or str(world.get('universe_id') or '').strip()

    if resolved['universe_id']:
        records['universe'] = get_record('universe', resolved['universe_id'])

    organization_records: list[dict[str, Any]] = []
    for org_id in resolved['organization_ids']:
        rec = get_record('organization', org_id)
        if rec:
            organization_records.append(rec)
    records['organizations'] = organization_records
    return resolved, records



def _context_packet(context: dict[str, Any], records: dict[str, Any]) -> dict[str, Any]:
    packet: dict[str, Any] = {
        'selected_ids': {key: value for key, value in context.items() if key.endswith('_id') and value},
    }
    if context.get('species_hint'):
        packet['species_hint'] = context['species_hint']
    if context.get('organization_ids'):
        packet['organization_ids'] = context['organization_ids']
    for key in ['universe', 'world', 'region', 'city', 'location', 'scenario']:
        rec = records.get(key)
        if rec:
            packet[key] = _compact_record(rec)
    orgs = records.get('organizations') or []
    if orgs:
        packet['organizations'] = [_compact_record(rec) for rec in orgs[:8]]
    return packet



def _label_from_context(records: dict[str, Any], *, prefer_location: bool = False) -> str:
    order = ['location', 'city', 'region', 'world', 'universe'] if prefer_location else ['world', 'region', 'city', 'location', 'universe']
    for key in order:
        label = _record_label(records.get(key))
        if label:
            return label
    return ''



def _set_if_empty(payload: dict[str, Any], key: str, value: Any) -> None:
    if key in payload and not _is_empty(value) and _is_empty(payload.get(key)):
        payload[key] = copy.deepcopy(value)



def _inject_context_defaults(kind: str, result: dict[str, Any], context: dict[str, Any], records: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(result)
    org_ids = context.get('organization_ids') or []
    org_names = [_record_label(item) for item in (records.get('organizations') or []) if _record_label(item)]

    _set_if_empty(payload, 'universe_id', context.get('universe_id'))
    if kind != 'world':
        _set_if_empty(payload, 'world_id', context.get('world_id'))
    if kind in {'city', 'location', 'organization'}:
        _set_if_empty(payload, 'region_id', context.get('region_id'))
        _set_if_empty(payload, 'city_id', context.get('city_id'))
    elif kind == 'region':
        _set_if_empty(payload, 'world_id', context.get('world_id'))
    elif kind == 'scenario':
        _set_if_empty(payload, 'location_region_id', context.get('region_id'))
        _set_if_empty(payload, 'location_city_id', context.get('city_id'))
        _set_if_empty(payload, 'location_id', context.get('location_id'))
        _set_if_empty(payload, 'location_label', _label_from_context(records, prefer_location=True))
    elif kind == 'character':
        _set_if_empty(payload, 'current_world_id', context.get('world_id'))
        _set_if_empty(payload, 'current_region_id', context.get('region_id'))
        _set_if_empty(payload, 'current_city_id', context.get('city_id'))
        _set_if_empty(payload, 'current_location_id', context.get('location_id'))
        _set_if_empty(payload, 'current_location_label', _label_from_context(records, prefer_location=True))
        _set_if_empty(payload, 'species', context.get('species_hint'))
    elif kind == 'organization':
        _set_if_empty(payload, 'base_location_id', context.get('location_id'))
    elif kind == 'location':
        _set_if_empty(payload, 'region_id', context.get('region_id'))
        _set_if_empty(payload, 'city_id', context.get('city_id'))

    if 'organization_ids' in payload and org_ids:
        _set_if_empty(payload, 'organization_ids', org_ids)
    if 'organization_names' in payload and org_names:
        _set_if_empty(payload, 'organization_names', org_names)
    if kind == 'organization':
        if 'ally_organization_ids' in payload and org_ids and _is_empty(payload.get('ally_organization_ids')):
            payload['ally_organization_ids'] = copy.deepcopy(org_ids)
        if 'ally_organization_names' in payload and org_names and _is_empty(payload.get('ally_organization_names')):
            payload['ally_organization_names'] = copy.deepcopy(org_names)
    return payload



def _title_field_hint(kind: str) -> str:
    return {
        'character': 'For sparse character briefs, invent a plausible full name, age-adjacent vibe, study/work path, emotional tension, and speech texture when helpful.',
        'world': 'For sparse world briefs, invent a coherent setting identity, social texture, and power structure instead of repeating the same adjectives back.',
        'organization': 'For sparse organization briefs, invent a believable public face, internal logic, goals, and reputation that fit the linked world context.',
        'location': 'For sparse location briefs, invent function, atmosphere, scene utility, and hidden tension that match the selected place context.',
        'scenario': 'For sparse scenario briefs, invent a playable objective, emotional premise, and opening beat that fit the linked cast/place context.',
    }.get(kind, 'If the brief is sparse, complete missing details intelligently so the record feels usable instead of merely paraphrased.')



async def draft_library_json(
    kind: str,
    brief: str,
    *,
    mode: str = 'draft_scratch',
    draft_style: str = 'balanced',
    current_json: str = '',
    model: str = 'default',
    context: dict[str, Any] | None = None,
    max_tokens: int = 1400,
    temperature: float | None = None,
    top_p: float = 0.92,
    top_k: int = 50,
) -> dict[str, Any]:
    clean_kind = _clean_kind(kind)
    clean_mode = _clean_mode(mode)
    clean_style = _clean_style(draft_style)
    brief_text = str(brief or '').strip()
    current = _parse_existing_json(current_json)
    template = _prepare_template(clean_kind)
    normalized_context, context_records = _resolve_context_links(_clean_context(context))
    context_packet = _context_packet(normalized_context, context_records)

    if clean_mode == 'draft_scratch' and not brief_text:
        raise ValueError('Add a short brief before drafting JSON with AI.')
    if clean_mode != 'draft_scratch' and not current:
        raise ValueError('Load or paste current JSON into the editor before using fill missing or rewrite mode.')

    system_prompt = (
        'You are a structured roleplay library drafting assistant. '
        'Return only one valid JSON object. '
        'No markdown. No code fences. No commentary. No explanations. '
        'Keep the exact schema shape from the provided template. '
        'Do not add unknown keys. '
        'If a linked record ID is unknown, keep it empty or preserve the existing value. '
        'Never invent foreign IDs. '
        'Use the linked context packet as silent fuel for coherence. '
        'Do not merely rewrite the brief into JSON. '
        'Complete missing detail intelligently when the drafting style allows it. '
        'Write concise, reusable, production-ready field text.'
    )
    user_prompt = (
        f'Target library kind: {clean_kind}\n'
        f'Draft mode: {clean_mode}\n'
        f'Mode instruction: {MODE_GUIDANCE[clean_mode]}\n'
        f'Drafting style: {clean_style}\n'
        f'Style instruction: {STYLE_GUIDANCE[clean_style]}\n'
        f'Generation emphasis: {_title_field_hint(clean_kind)}\n\n'
        'JSON schema shape to follow exactly:\n'
        f'{json.dumps(template, indent=2, ensure_ascii=False)}\n\n'
        'Schema notes:\n'
        f'{chr(10).join(_schema_prompt_lines(template))}\n\n'
        f'Linked context packet:\n{json.dumps(context_packet, indent=2, ensure_ascii=False)}\n\n'
        f'Current JSON draft:\n{json.dumps(current, indent=2, ensure_ascii=False) if current else "{}"}\n\n'
        f'User brief:\n{brief_text or "(no extra brief provided)"}\n\n'
        'Rules:\n'
        '- Preserve explicit facts from the user brief.\n'
        '- Use selected world/place/org/species context when it improves coherence.\n'
        '- Fill blank fields with believable specifics instead of repeating the same phrase in every field.\n'
        '- Keep IDs empty unless they are already provided in the schema/context/current JSON.\n'
        '- Keep arrays valid and schema-aligned.\n\n'
        'Return one JSON object only.'
    )

    response = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 240, 2200, 1400),
            'temperature': clamp_float(STYLE_TEMPERATURES[clean_style] if temperature is None else temperature, 0.0, 1.2, STYLE_TEMPERATURES[clean_style]),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 50),
            'repetition_penalty': 1.05,
        },
        timeout=300.0,
    )

    parsed = _extract_json_object(response.get('content', ''))
    drafted = _merge_on_template(template, parsed)

    if clean_mode == 'fill_missing' and current:
        result = _fill_missing(_merge_on_template(template, current), drafted)
    elif clean_mode == 'rewrite_current' and current:
        result = _merge_on_template(_merge_on_template(template, current), drafted)
    else:
        result = drafted

    result['kind'] = clean_kind
    result['schema_version'] = template.get('schema_version', result.get('schema_version'))
    result = _preserve_existing_identity(result, current)
    result = _inject_context_defaults(clean_kind, result, normalized_context, context_records)

    return {
        'kind': clean_kind,
        'mode': clean_mode,
        'draft_style': clean_style,
        'draft_json': json.dumps(result, indent=2, ensure_ascii=False),
        'record': result,
        'context_packet': context_packet,
        'finish_reason': response.get('finish_reason', ''),
        'reasoning_stripped': bool(response.get('reasoning_stripped')),
    }
