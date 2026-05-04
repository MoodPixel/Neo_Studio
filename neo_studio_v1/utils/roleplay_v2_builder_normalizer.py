from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..contracts.roleplay_v2_records import canonical_entity_kind, normalize_entity_links

BUILDER_TEMPLATE_JSON_DIR = Path(__file__).resolve().parent.parent / 'contracts' / 'builder_templates' / 'json'

_TOP_LEVEL_KEYS = [
    'id',
    'kind',
    'schema_version',
    'source_container_id',
    'label',
    'display_label',
    'summary',
    'canon_status',
    'visibility',
    'tags',
    'tone_tags',
    'links',
    'fields',
    'memory_hints',
    'meta',
]


def _template_payload(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    path = BUILDER_TEMPLATE_JSON_DIR / f'{clean_kind}.template.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _deep_merge_known(template: Any, patch: Any) -> Any:
    if isinstance(template, dict):
        raw_patch = patch if isinstance(patch, dict) else {}
        merged: dict[str, Any] = {}
        for key, template_value in template.items():
            if key in raw_patch:
                merged[key] = _deep_merge_known(template_value, raw_patch.get(key))
            else:
                merged[key] = deepcopy(template_value)
        return merged
    if isinstance(template, list):
        if isinstance(patch, list):
            return deepcopy(patch)
        return deepcopy(template)
    if patch is None:
        return deepcopy(template)
    return deepcopy(patch)


def _collect_unknown_paths(template: Any, patch: Any, prefix: str = '') -> list[str]:
    if not isinstance(template, dict) or not isinstance(patch, dict):
        return []
    unknown: list[str] = []
    for key, value in patch.items():
        path = f'{prefix}.{key}' if prefix else str(key)
        if key not in template:
            unknown.append(path)
            continue
        unknown.extend(_collect_unknown_paths(template.get(key), value, path))
    return unknown


def _clean_list(values: Any) -> list[Any]:
    if isinstance(values, list):
        return [item for item in values]
    if values is None:
        return []
    return [values]


def _clean_text(value: Any) -> str:
    return str(value or '').strip()


def normalize_builder_payload(*, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    raw = payload if isinstance(payload, dict) else {}
    template = _template_payload(clean_kind)
    if not template:
        raise ValueError('Template payload is not available for this builder yet.')

    normalized: dict[str, Any] = {}
    raw_links = raw.get('links') if isinstance(raw.get('links'), dict) else {}
    report = {
        'kind': clean_kind,
        'dropped_top_level_keys': [key for key in raw.keys() if key not in _TOP_LEVEL_KEYS],
        'unknown_field_paths': _collect_unknown_paths(template.get('fields') or {}, raw.get('fields') or {}, 'fields'),
        'unknown_memory_hint_paths': _collect_unknown_paths(template.get('memory_hints') or {}, raw.get('memory_hints') or {}, 'memory_hints'),
        'unknown_link_paths': [],
    }

    normalized['id'] = _clean_text(raw.get('id'))
    normalized['kind'] = clean_kind
    normalized['schema_version'] = int(raw.get('schema_version') or template.get('schema_version') or 1)
    normalized['label'] = _clean_text(raw.get('label') or template.get('label'))
    normalized['display_label'] = _clean_text(raw.get('display_label') or template.get('display_label'))
    normalized['summary'] = _clean_text(raw.get('summary') or template.get('summary'))
    normalized['canon_status'] = _clean_text(raw.get('canon_status') or template.get('canon_status') or 'primary_canon')
    normalized['visibility'] = _clean_text(raw.get('visibility') or template.get('visibility') or 'author_private')
    normalized['tags'] = _clean_list(raw.get('tags') or template.get('tags') or [])
    normalized['tone_tags'] = _clean_list(raw.get('tone_tags') or template.get('tone_tags') or [])

    template_links = template.get('links') if isinstance(template.get('links'), dict) else {}
    source_container_id = _clean_text(raw.get('source_container_id') or raw_links.get('source_container_id'))
    report['unknown_link_paths'] = [path for path in _collect_unknown_paths(template_links, raw_links, 'links') if path != 'links.source_container_id']
    merged_links = _deep_merge_known(template_links, raw_links)
    if source_container_id:
        merged_links['source_container_id'] = source_container_id
    normalized_links = normalize_entity_links(clean_kind, merged_links)
    normalized['links'] = normalized_links
    normalized['source_container_id'] = _clean_text(normalized_links.get('source_container_id') or raw.get('source_container_id'))

    template_fields = template.get('fields') if isinstance(template.get('fields'), dict) else {}
    raw_fields = raw.get('fields') if isinstance(raw.get('fields'), dict) else {}
    normalized['fields'] = _deep_merge_known(template_fields, raw_fields)

    template_memory_hints = template.get('memory_hints') if isinstance(template.get('memory_hints'), dict) else {}
    raw_memory_hints = raw.get('memory_hints') if isinstance(raw.get('memory_hints'), dict) else {}
    normalized['memory_hints'] = _deep_merge_known(template_memory_hints, raw_memory_hints)

    raw_meta = raw.get('meta') if isinstance(raw.get('meta'), dict) else {}
    template_meta = template.get('meta') if isinstance(template.get('meta'), dict) else {}
    normalized['meta'] = _deep_merge_known(template_meta, raw_meta)

    report['dropped_count'] = sum(len(report[key]) for key in ('dropped_top_level_keys', 'unknown_field_paths', 'unknown_memory_hint_paths', 'unknown_link_paths'))
    report['canonical_links'] = {
        'scope_keys': sorted((normalized_links.get('scope') or {}).keys()),
        'related_keys': sorted((normalized_links.get('related') or {}).keys()),
    }
    report['template_bound'] = True

    return {
        'ok': True,
        'kind': clean_kind,
        'template_payload': template,
        'normalized_payload': normalized,
        'normalization': report,
    }
