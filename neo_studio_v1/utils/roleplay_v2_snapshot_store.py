from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts.roleplay_v2_records import normalize_canon_record, normalize_entity_record, normalize_source_document_record
from .library_constants import DEFAULT_ROOT
from .storage_io import atomic_write_json, read_json_object


ROLEPLAY_V2_MEMORY_SCOPES = {
    'source',
    'sandbox',
    'durable',
}

ROLEPLAY_V2_PROMOTION_SCOPES = {
    'sandbox_only',
    'shared_world',
    'shared_universe',
    'durable_project',
}

ROLEPLAY_V2_STORY_SNAPSHOT_SCHEMA_VERSION = 1

ROLEPLAY_V2_ROOT = DEFAULT_ROOT / 'roleplay_v2'
ROLEPLAY_V2_ENTITIES_DIR = ROLEPLAY_V2_ROOT / 'entities'
ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR = ROLEPLAY_V2_ROOT / 'source_documents'
ROLEPLAY_V2_CANON_RECORDS_DIR = ROLEPLAY_V2_ROOT / 'canon_records'
ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR = ROLEPLAY_V2_ROOT / 'memory_fragments'
ROLEPLAY_V2_STORY_SNAPSHOTS_DIR = ROLEPLAY_V2_ROOT / 'story_snapshots'



def _clean(value: Any, *, lower: bool = False, limit: int = 0) -> str:
    text = str(value or '').strip()
    if lower:
        text = text.lower()
    if limit > 0:
        text = text[:limit]
    return text



def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _record_id(prefix: str, provided: str = '') -> str:
    return _clean(provided, limit=120) or f'{prefix}_{uuid4().hex[:10]}'



def _clean_list(values: Any, *, limit: int = 0) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = _clean(item, limit=limit)
        if text and text not in out:
            out.append(text)
    return out



def _json_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}



def _json_list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []



def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    path.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item in sorted(path.glob('*.json')):
        row = read_json_object(item, None)
        if isinstance(row, dict):
            rows.append(row)
    return rows



def allocate_source_snapshot_id(provided: str = '') -> str:
    return _record_id('source_snapshot', provided)



def allocate_canon_snapshot_id(provided: str = '') -> str:
    return _record_id('canon_snapshot', provided)



def allocate_sandbox_id(provided: str = '') -> str:
    return _record_id('sandbox', provided)



def allocate_branch_id(provided: str = '') -> str:
    return _record_id('branch', provided)



def normalize_memory_scope(value: Any, default: str = 'sandbox') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_MEMORY_SCOPES else default



def normalize_promotion_scope(value: Any, default: str = 'sandbox_only') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_PROMOTION_SCOPES else default



def build_scope_contract(
    *,
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    storyline_id: str = '',
    session_id: str = '',
    checkpoint_id: str = '',
    branch_id: str = '',
    memory_scope: str = 'sandbox',
    promotion_scope: str = 'sandbox_only',
) -> dict[str, str]:
    return {
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'storyline_id': _clean(storyline_id, limit=120),
        'session_id': _clean(session_id, limit=120),
        'checkpoint_id': _clean(checkpoint_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'memory_scope': normalize_memory_scope(memory_scope),
        'promotion_scope': normalize_promotion_scope(promotion_scope),
    }



def story_snapshot_path(snapshot_id: str) -> Path:
    ROLEPLAY_V2_STORY_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return ROLEPLAY_V2_STORY_SNAPSHOTS_DIR / f"{_clean(snapshot_id, limit=120)}.json"



def load_story_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    clean_id = _clean(snapshot_id, limit=120)
    if not clean_id:
        return None
    return read_json_object(story_snapshot_path(clean_id), None)



def save_story_snapshot(snapshot_payload: dict[str, Any]) -> dict[str, Any]:
    clean_id = _clean((snapshot_payload or {}).get('id'), limit=120)
    if not clean_id:
        raise ValueError('Story snapshot is missing id.')
    payload = deepcopy(snapshot_payload if isinstance(snapshot_payload, dict) else {})
    atomic_write_json(story_snapshot_path(clean_id), payload)
    return payload



def _story_anchor_ids(storyline: dict[str, Any], scene_state_seed: dict[str, Any] | None = None) -> list[str]:
    scene_seed = scene_state_seed if isinstance(scene_state_seed, dict) else {}
    anchor_ids = [
        _clean(storyline.get('linked_world_id'), limit=120),
        _clean(storyline.get('linked_universe_id'), limit=120),
        *_clean_list(storyline.get('linked_scenario_ids') or [], limit=120),
        *_clean_list(storyline.get('linked_entity_ids') or [], limit=120),
        *_clean_list(scene_seed.get('focus_stack') or [], limit=120),
    ]
    return _clean_list(anchor_ids, limit=120)



def _related_entity_records(anchor_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_id in anchor_ids:
        row = read_json_object(ROLEPLAY_V2_ENTITIES_DIR / f'{entity_id}.json', None)
        if isinstance(row, dict):
            rows.append(normalize_entity_record(row))
    return rows



def _related_source_documents(*, project_id: str, anchor_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _load_json_rows(ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR):
        clean_project = _clean(row.get('project_id'), limit=120)
        linked_ids = _clean_list(row.get('linked_entity_ids') or [], limit=120)
        if project_id and clean_project == project_id:
            rows.append(normalize_source_document_record(row))
            continue
        if anchor_ids and any(item in anchor_ids for item in linked_ids):
            rows.append(normalize_source_document_record(row))
    return rows



def _related_canon_records(*, project_id: str, anchor_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _load_json_rows(ROLEPLAY_V2_CANON_RECORDS_DIR):
        clean_project = _clean(row.get('project_id'), limit=120)
        scope_id = _clean(row.get('scope_id'), limit=120)
        linked_ids = _clean_list(row.get('linked_entity_ids') or [], limit=120)
        if project_id and clean_project == project_id:
            rows.append(normalize_canon_record(row))
            continue
        if scope_id and scope_id in anchor_ids:
            rows.append(normalize_canon_record(row))
            continue
        if anchor_ids and any(item in anchor_ids for item in linked_ids):
            rows.append(normalize_canon_record(row))
    return rows



def _related_source_memory_fragments(*, project_id: str, anchor_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _load_json_rows(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR):
        clean_scope = _clean(row.get('memory_scope') or ((row.get('extra') or {}).get('memory_scope') if isinstance(row.get('extra'), dict) else ''), lower=True, limit=80)
        if clean_scope and clean_scope != 'source':
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        entity_id = _clean(row.get('entity_id'), limit=120)
        builder_record_id = _clean(extra.get('builder_record_id') or extra.get('canon_id') or '', limit=120)
        row_project_id = _clean(extra.get('project_id') or '', limit=120)
        if project_id and row_project_id == project_id:
            rows.append({
                'id': _clean(row.get('id'), limit=120),
                'memory_type': _clean(row.get('memory_type'), lower=True, limit=80),
                'entity_id': entity_id,
                'builder_record_id': builder_record_id,
                'title': _clean(row.get('title'), limit=200),
                'source_ref': _clean(row.get('source_ref'), limit=500),
                'updated_at': _clean(((row.get('meta') or {}).get('updated_at') if isinstance(row.get('meta'), dict) else ''), limit=80),
            })
            continue
        if anchor_ids and ({entity_id, builder_record_id} & set(anchor_ids)):
            rows.append({
                'id': _clean(row.get('id'), limit=120),
                'memory_type': _clean(row.get('memory_type'), lower=True, limit=80),
                'entity_id': entity_id,
                'builder_record_id': builder_record_id,
                'title': _clean(row.get('title'), limit=200),
                'source_ref': _clean(row.get('source_ref'), limit=500),
                'updated_at': _clean(((row.get('meta') or {}).get('updated_at') if isinstance(row.get('meta'), dict) else ''), limit=80),
            })
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        row_id = _clean(row.get('id'), limit=120)
        if row_id and row_id not in seen:
            seen.add(row_id)
            deduped.append(row)
    return deduped



def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    inventory = snapshot.get('inventory') if isinstance(snapshot.get('inventory'), dict) else {}
    return {
        'id': _clean(snapshot.get('id'), limit=120),
        'snapshot_kind': _clean(snapshot.get('snapshot_kind'), lower=True, limit=40),
        'created_at': _clean(snapshot.get('created_at'), limit=80),
        'project_id': _clean(((snapshot.get('storyline') or {}).get('project_id') if isinstance(snapshot.get('storyline'), dict) else ''), limit=120),
        'entity_count': int(inventory.get('entity_count') or 0),
        'source_document_count': int(inventory.get('source_document_count') or 0),
        'canon_record_count': int(inventory.get('canon_record_count') or 0),
        'source_memory_fragment_count': int(inventory.get('source_memory_fragment_count') or 0),
        'seed_runtime_bundle_id': _clean(((snapshot.get('seed') or {}).get('runtime_bundle_id') if isinstance(snapshot.get('seed'), dict) else ''), limit=120),
    }



def build_story_start_snapshot(
    *,
    snapshot_kind: str,
    snapshot_id: str,
    storyline: dict[str, Any],
    scene_state_seed: dict[str, Any] | None = None,
    seed_runtime_bundle_id: str = '',
) -> dict[str, Any]:
    clean_kind = _clean(snapshot_kind, lower=True, limit=40)
    if clean_kind not in {'source', 'canon'}:
        raise ValueError('snapshot_kind must be source or canon.')
    clean_storyline = deepcopy(storyline if isinstance(storyline, dict) else {})
    clean_scene_seed = _json_dict(scene_state_seed)
    project_id = _clean(clean_storyline.get('project_id'), limit=120)
    anchor_ids = _story_anchor_ids(clean_storyline, clean_scene_seed)
    entities = _related_entity_records(anchor_ids)
    source_documents = _related_source_documents(project_id=project_id, anchor_ids=anchor_ids)
    canon_records = _related_canon_records(project_id=project_id, anchor_ids=anchor_ids)
    source_memory_fragments = _related_source_memory_fragments(project_id=project_id, anchor_ids=anchor_ids)
    created_at = _now_iso()
    payload = {
        'schema_version': ROLEPLAY_V2_STORY_SNAPSHOT_SCHEMA_VERSION,
        'record_type': 'story_start_snapshot',
        'id': _clean(snapshot_id, limit=120),
        'snapshot_kind': clean_kind,
        'snapshot_status': 'frozen',
        'created_at': created_at,
        'storyline': {
            'id': _clean(clean_storyline.get('id'), limit=120),
            'title': _clean(clean_storyline.get('title'), limit=200),
            'project_id': project_id,
            'linked_world_id': _clean(clean_storyline.get('linked_world_id'), limit=120),
            'linked_universe_id': _clean(clean_storyline.get('linked_universe_id'), limit=120),
            'linked_scenario_ids': _clean_list(clean_storyline.get('linked_scenario_ids') or [], limit=120),
            'linked_entity_ids': _clean_list(clean_storyline.get('linked_entity_ids') or [], limit=120),
            'continuity_policy': _clean(clean_storyline.get('continuity_policy') or 'runtime_anchored', lower=True, limit=80),
        },
        'anchor_ids': anchor_ids,
        'seed': {
            'runtime_bundle_id': _clean(seed_runtime_bundle_id, limit=120),
            'scene_state_seed': clean_scene_seed,
        },
        'scope_contract': build_scope_contract(
            source_snapshot_id=_clean(snapshot_id, limit=120) if clean_kind == 'source' else _clean(clean_storyline.get('source_snapshot_id'), limit=120),
            canon_snapshot_id=_clean(snapshot_id, limit=120) if clean_kind == 'canon' else _clean(clean_storyline.get('canon_snapshot_id'), limit=120),
            storyline_id=_clean(clean_storyline.get('id'), limit=120),
            memory_scope='source',
            promotion_scope='sandbox_only',
        ),
        'inventory': {
            'entity_count': len(entities),
            'source_document_count': len(source_documents),
            'canon_record_count': len(canon_records),
            'source_memory_fragment_count': len(source_memory_fragments),
        },
        'records': {
            'entities': entities,
            'source_documents': source_documents if clean_kind == 'source' else [],
            'canon_records': canon_records if clean_kind == 'canon' else [],
            'source_memory_fragments': source_memory_fragments if clean_kind == 'source' else [],
        },
    }
    return payload



def materialize_story_start_snapshots(
    *,
    storyline: dict[str, Any],
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    scene_state_seed: dict[str, Any] | None = None,
    seed_runtime_bundle_id: str = '',
) -> dict[str, Any]:
    clean_storyline = deepcopy(storyline if isinstance(storyline, dict) else {})
    resolved_source_id = allocate_source_snapshot_id(source_snapshot_id or clean_storyline.get('source_snapshot_id'))
    resolved_canon_id = allocate_canon_snapshot_id(canon_snapshot_id or clean_storyline.get('canon_snapshot_id'))
    source_snapshot = load_story_snapshot(resolved_source_id)
    if not isinstance(source_snapshot, dict):
        source_snapshot = build_story_start_snapshot(
            snapshot_kind='source',
            snapshot_id=resolved_source_id,
            storyline=clean_storyline,
            scene_state_seed=scene_state_seed,
            seed_runtime_bundle_id=seed_runtime_bundle_id,
        )
        save_story_snapshot(source_snapshot)
    canon_snapshot = load_story_snapshot(resolved_canon_id)
    if not isinstance(canon_snapshot, dict):
        canon_snapshot = build_story_start_snapshot(
            snapshot_kind='canon',
            snapshot_id=resolved_canon_id,
            storyline=clean_storyline,
            scene_state_seed=scene_state_seed,
            seed_runtime_bundle_id=seed_runtime_bundle_id,
        )
        save_story_snapshot(canon_snapshot)
    return {
        'source_snapshot_id': resolved_source_id,
        'canon_snapshot_id': resolved_canon_id,
        'source_snapshot': source_snapshot,
        'canon_snapshot': canon_snapshot,
        'source_summary': _snapshot_summary(source_snapshot),
        'canon_summary': _snapshot_summary(canon_snapshot),
    }
