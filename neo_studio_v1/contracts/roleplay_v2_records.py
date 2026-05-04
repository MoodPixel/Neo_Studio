from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .roleplay_v2_builder_canonical_map import (
    ROLEPLAY_V2_CANONICAL_ENTITY_KINDS,
    ROLEPLAY_V2_CANONICAL_ENTITY_MAP,
    ROLEPLAY_V2_CANONICAL_SOURCE_CONTAINER_KINDS,
    ROLEPLAY_V2_SCHEMA_VERSION,
)
from .roleplay_v2_hierarchy_contract import get_roleplay_v2_hierarchy_entry

ROLEPLAY_V2_BUILDER_SCHEMA_VERSION = ROLEPLAY_V2_SCHEMA_VERSION
ROLEPLAY_V2_LINK_STRATEGY = 'canonical_nested_forward_links_with_derived_reverse_views'

ROLEPLAY_V2_SOURCE_CONTAINER_KINDS = list(ROLEPLAY_V2_CANONICAL_SOURCE_CONTAINER_KINDS)

ROLEPLAY_V2_ENTITY_KINDS = list(ROLEPLAY_V2_CANONICAL_ENTITY_KINDS)

ROLEPLAY_V2_RECORD_TYPES = {
    'entity_record',
    'source_document',
    'creator_draft',
    'helper_output',
    'canon_record',
    'memory_fragment',
    'timeline_event',
    'relationship_record',
    'shared_memory',
    'runtime_bundle',
    'portable_package_manifest',
    'novel_project',
    'storyline',
    'story_session',
    'story_checkpoint',
    'story_draft_snapshot',
}

ROLEPLAY_V2_ENTITY_SPECS: dict[str, dict[str, Any]] = deepcopy(ROLEPLAY_V2_CANONICAL_ENTITY_MAP)

ROLEPLAY_V2_ENTITY_ALIASES = {
    'kingdom': 'region',
    'settlement': 'city',
    'spell': 'ritual',
    'technique': 'ritual',
    'potion': 'ritual',
    'condition': 'cycle',
    'system': 'cycle',
    'animal': 'creature',
    'fauna': 'creature',
    'weapon': 'artifact',
    'faction': 'organization',
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _clean(value: Any, *, limit: int = 0, lower: bool = False) -> str:
    text = str(value or '').strip()
    if lower:
        text = text.lower()
    if limit > 0:
        text = text[:limit]
    return text


def _clean_list(values: Any, *, limit: int = 0, lower: bool = False) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = _clean(item, limit=limit, lower=lower)
        if text:
            out.append(text)
    return out


def _json_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _record_id(prefix: str, provided: str = '') -> str:
    clean_prefix = _clean(prefix, lower=True) or 'record'
    clean_provided = _clean(provided)
    return clean_provided or f'{clean_prefix}_{uuid4().hex[:10]}'


def _meta(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    created_at = _clean(data.get('created_at')) or _now_iso()
    updated_at = _clean(data.get('updated_at')) or created_at
    return {
        'created_at': created_at,
        'updated_at': updated_at,
        'status': _clean(data.get('status') or 'active', lower=True),
        'version': max(1, int(data.get('version') or 1)),
        'tags': _clean_list(data.get('tags') or [], limit=64),
        'notes': _clean(data.get('notes'), limit=4000),
    }


def canonical_entity_kind(kind: str) -> str:
    clean_kind = _clean(kind, lower=True)
    return ROLEPLAY_V2_ENTITY_ALIASES.get(clean_kind, clean_kind)


def get_entity_spec(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    spec = ROLEPLAY_V2_ENTITY_SPECS.get(clean_kind)
    if not spec:
        raise ValueError('Unsupported roleplay V2 entity kind.')
    return deepcopy(spec)


def default_entity_links(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    spec = ROLEPLAY_V2_ENTITY_SPECS.get(clean_kind) or {}
    scope_keys = sorted(set(spec.get('link_ownership', {}).get('scope') or []))
    related_keys = sorted(set(spec.get('link_ownership', {}).get('related') or []))
    return {
        'scope': {key: '' for key in scope_keys},
        'related': {key: [] for key in related_keys},
        'reverse_links': {
            'strategy': 'derived',
            'materialized': {},
        },
        'source_container_id': '',
    }


def normalize_entity_links(kind: str, links: dict[str, Any] | None = None) -> dict[str, Any]:
    base = default_entity_links(kind)
    raw = links if isinstance(links, dict) else {}
    for key, value in raw.items():
        if key == 'scope' and isinstance(value, dict):
            for scope_key, scope_value in value.items():
                base['scope'][str(scope_key)] = _clean(scope_value, limit=120)
        elif key == 'related' and isinstance(value, dict):
            for related_key, related_value in value.items():
                base['related'][str(related_key)] = _clean_list(related_value or [], limit=120)
        elif key == 'reverse_links' and isinstance(value, dict):
            strategy = _clean(value.get('strategy') or 'derived', limit=60, lower=True)
            materialized = _json_dict(value.get('materialized'))
            base['reverse_links'] = {'strategy': strategy or 'derived', 'materialized': materialized}
        elif key == 'source_container_id':
            base['source_container_id'] = _clean(value, limit=120)
        elif isinstance(value, list):
            base['related'][str(key)] = _clean_list(value, limit=120)
        elif isinstance(value, dict):
            base[str(key)] = deepcopy(value)
        else:
            if key in base['scope']:
                base['scope'][str(key)] = _clean(value, limit=120)
            elif key.endswith('_id'):
                base['scope'][str(key)] = _clean(value, limit=120)
            else:
                base[str(key)] = _clean(value, limit=4000)
    return base


def build_entity_contract(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    spec = get_entity_spec(clean_kind)
    return {
        'builder_schema_version': ROLEPLAY_V2_BUILDER_SCHEMA_VERSION,
        'kind': clean_kind,
        'display_name': str(spec.get('display_name') or clean_kind.title()),
        'category': str(spec.get('category') or 'entity'),
        'primary_label_key': str(spec.get('primary_label_key') or 'label'),
        'link_strategy': ROLEPLAY_V2_LINK_STRATEGY,
        'builder_sections': list(spec.get('builder_sections') or []),
        'canonical_fields': list(spec.get('canonical_fields') or []),
        'authoring_field_paths': list(spec.get('authoring_field_paths') or []),
        'link_ownership': deepcopy(spec.get('link_ownership') or {}),
        'edge_sections': list(spec.get('edge_sections') or []),
        'derived_reverse_links': list(spec.get('derived_reverse_links') or []),
        'runtime_surface': deepcopy(spec.get('runtime_surface') or {}),
        'memory_compile': deepcopy(spec.get('memory_compile') or {}),
        'authoring_hierarchy': get_roleplay_v2_hierarchy_entry(clean_kind),
    }


def build_entity_record(*, kind: str, label: str = '', entity_id: str = '', data: dict[str, Any] | None = None, links: dict[str, Any] | None = None, source_refs: list[str] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    if clean_kind not in ROLEPLAY_V2_ENTITY_KINDS:
        raise ValueError('Unsupported roleplay V2 entity kind.')
    raw_data = _json_dict(data)
    fields = _json_dict(raw_data.get('fields')) if isinstance(raw_data.get('fields'), dict) else deepcopy(raw_data)
    memory_hints = _json_dict(raw_data.get('memory_hints'))
    summary = _clean(raw_data.get('summary') or fields.get('summary') or fields.get('identity', {}).get('summary'), limit=4000)
    display_label = _clean(raw_data.get('display_label') or fields.get('display_label') or '', limit=160)
    canon_status = _clean(raw_data.get('canon_status') or 'primary_canon', limit=80, lower=True)
    visibility = _clean(raw_data.get('visibility') or 'author_private', limit=80, lower=True)
    tags = _clean_list(raw_data.get('tags') or [], limit=64)
    tone_tags = _clean_list(raw_data.get('tone_tags') or [], limit=64)
    return {
        'schema_version': ROLEPLAY_V2_SCHEMA_VERSION,
        'record_type': 'entity_record',
        'kind': clean_kind,
        'id': _record_id(clean_kind, entity_id),
        'label': _clean(label, limit=160),
        'display_label': display_label,
        'summary': summary,
        'canon_status': canon_status or 'primary_canon',
        'visibility': visibility or 'author_private',
        'tags': tags,
        'tone_tags': tone_tags,
        'data': raw_data,
        'fields': fields,
        'memory_hints': memory_hints,
        'links': normalize_entity_links(clean_kind, links),
        'source_refs': _clean_list(source_refs or [], limit=240),
        'contract': build_entity_contract(clean_kind),
        'meta': _meta(meta),
    }


def normalize_entity_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    excluded = {'schema_version', 'record_type', 'kind', 'id', 'entity_id', 'label', 'display_label', 'summary', 'canon_status', 'visibility', 'tags', 'tone_tags', 'name', 'title', 'links', 'source_refs', 'contract', 'meta', 'fields', 'memory_hints'}
    data = raw.get('data') if isinstance(raw.get('data'), dict) else {k: v for k, v in raw.items() if k not in excluded}
    if isinstance(raw.get('fields'), dict):
        data = {**_json_dict(data), 'fields': deepcopy(raw.get('fields'))}
    if isinstance(raw.get('memory_hints'), dict):
        data = {**_json_dict(data), 'memory_hints': deepcopy(raw.get('memory_hints'))}
    if raw.get('summary') and 'summary' not in data:
        data['summary'] = raw.get('summary')
    if raw.get('display_label') and 'display_label' not in data:
        data['display_label'] = raw.get('display_label')
    if raw.get('canon_status') and 'canon_status' not in data:
        data['canon_status'] = raw.get('canon_status')
    if raw.get('visibility') and 'visibility' not in data:
        data['visibility'] = raw.get('visibility')
    if raw.get('tags') and 'tags' not in data:
        data['tags'] = raw.get('tags')
    if raw.get('tone_tags') and 'tone_tags' not in data:
        data['tone_tags'] = raw.get('tone_tags')
    return build_entity_record(
        kind=raw.get('kind') or '',
        label=raw.get('label') or raw.get('name') or raw.get('title') or '',
        entity_id=raw.get('id') or raw.get('entity_id') or '',
        data=data,
        links=raw.get('links'),
        source_refs=raw.get('source_refs') or [],
        meta=raw.get('meta'),
    )


def build_canon_record(*, canon_id: str = '', label: str = '', scope_type: str = '', scope_id: str = '', project_id: str = '', summary: str = '', linked_entity_ids: list[str] | None = None, source_refs: list[str] | None = None, data: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_SCHEMA_VERSION,
        'record_type': 'canon_record',
        'id': _record_id('canon_record', canon_id),
        'label': _clean(label, limit=200),
        'scope_type': _clean(scope_type, lower=True, limit=80),
        'scope_id': _clean(scope_id, limit=120),
        'project_id': _clean(project_id, limit=120),
        'summary': _clean(summary, limit=12000),
        'linked_entity_ids': _clean_list(linked_entity_ids or [], limit=120),
        'source_refs': _clean_list(source_refs or [], limit=240),
        'data': _json_dict(data),
        'meta': _meta(meta),
    }


def normalize_canon_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_canon_record(
        canon_id=raw.get('id') or raw.get('canon_id') or '',
        label=raw.get('label') or raw.get('title') or '',
        scope_type=raw.get('scope_type') or '',
        scope_id=raw.get('scope_id') or '',
        project_id=raw.get('project_id') or '',
        summary=raw.get('summary') or '',
        linked_entity_ids=raw.get('linked_entity_ids') or [],
        source_refs=raw.get('source_refs') or [],
        data=raw.get('data'),
        meta=raw.get('meta'),
    )


def build_source_document_record(*, document_id: str = '', project_id: str = '', document_type: str = 'source_text', title: str = '', source_name: str = '', source_format: str = 'text', raw_text: str = '', cleaned_text: str = '', order_index: int = 0, chapter_number: int = 0, scene_number: int = 0, linked_entity_ids: list[str] | None = None, extra: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_SCHEMA_VERSION,
        'record_type': 'source_document',
        'id': _record_id('source_document', document_id),
        'project_id': _clean(project_id, limit=120),
        'document_type': _clean(document_type or 'source_text', lower=True, limit=80),
        'title': _clean(title, limit=200),
        'source_name': _clean(source_name, limit=240),
        'source_format': _clean(source_format or 'text', lower=True, limit=40),
        'raw_text': _clean(raw_text, limit=400000),
        'cleaned_text': _clean(cleaned_text or raw_text, limit=400000),
        'order_index': max(0, int(order_index or 0)),
        'chapter_number': max(0, int(chapter_number or 0)),
        'scene_number': max(0, int(scene_number or 0)),
        'linked_entity_ids': _clean_list(linked_entity_ids or [], limit=120),
        'source_container_type': 'novel_project',
        'extra': _json_dict(extra),
        'meta': _meta(meta),
    }


def normalize_source_document_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_source_document_record(
        document_id=raw.get('id') or raw.get('document_id') or '',
        project_id=raw.get('project_id') or '',
        document_type=raw.get('document_type') or 'source_text',
        title=raw.get('title') or raw.get('label') or raw.get('source_name') or '',
        source_name=raw.get('source_name') or '',
        source_format=raw.get('source_format') or '',
        raw_text=raw.get('raw_text') or raw.get('text') or '',
        cleaned_text=raw.get('cleaned_text') or '',
        order_index=raw.get('order_index') or 0,
        chapter_number=raw.get('chapter_number') or 0,
        scene_number=raw.get('scene_number') or 0,
        linked_entity_ids=raw.get('linked_entity_ids') or [],
        extra=raw.get('extra'),
        meta=raw.get('meta'),
    )


def build_novel_project_record(*, project_id: str = '', title: str = '', author: str = '', source_language: str = 'en', chapter_count: int = 0, chapter_ids: list[str] | None = None, linked_world_id: str = '', linked_universe_id: str = '', meta: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_SCHEMA_VERSION,
        'record_type': 'novel_project',
        'container_kind': 'source_project',
        'id': _record_id('novel_project', project_id),
        'title': _clean(title, limit=200),
        'author': _clean(author, limit=160),
        'source_language': _clean(source_language or 'en', limit=32, lower=True),
        'chapter_count': max(0, int(chapter_count or 0)),
        'chapter_ids': _clean_list(chapter_ids or [], limit=120),
        'linked_world_id': _clean(linked_world_id, limit=120),
        'linked_universe_id': _clean(linked_universe_id, limit=120),
        'domain_boundary': {
            'is_source_container': True,
            'entity_record_allowed': False,
            'runtime_packet_role': 'source_scope_anchor',
        },
        'extra': _json_dict(extra),
        'meta': _meta(meta),
    }


def normalize_novel_project_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_novel_project_record(
        project_id=raw.get('id') or raw.get('project_id') or '',
        title=raw.get('title') or raw.get('label') or '',
        author=raw.get('author') or '',
        source_language=raw.get('source_language') or 'en',
        chapter_count=raw.get('chapter_count') or 0,
        chapter_ids=raw.get('chapter_ids') or [],
        linked_world_id=raw.get('linked_world_id') or '',
        linked_universe_id=raw.get('linked_universe_id') or '',
        meta=raw.get('meta'),
        extra=raw.get('extra'),
    )

