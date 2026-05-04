from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from ..contracts.roleplay_v2_mode_model import normalize_mode_model
from ..contracts.roleplay_v2_scene_state import normalize_scene_state
from ..contracts.roleplay_v2_memory_records import build_memory_fragment_record, build_shared_memory_record
from ..contracts.roleplay_v2_story_records import (
    build_story_checkpoint_record,
    build_story_session_record,
    build_storyline_record,
    normalize_story_checkpoint_record,
    normalize_story_session_record,
    normalize_storyline_record,
)
from .roleplay_v2_foundation import (
    ROLEPLAY_V2_STORY_CHECKPOINTS_DIR,
    ROLEPLAY_V2_STORY_SESSIONS_DIR,
    ROLEPLAY_V2_STORYLINES_DIR,
)
from .roleplay_v2_package_store import load_saved_record, save_record
from .roleplay_v2_runtime_bundle import get_runtime_bundle
from .roleplay_v2_sqlite_store import fetch_rp2_post_turn_memory_debug_rows, fetch_rp2_relationship_state_rows, fetch_rp2_turn_summary_debug_rows, upsert_rp2_memory_outputs, persist_rp2_relationship_state
from .storage_io import read_json_object
from .roleplay_v2_snapshot_store import allocate_source_snapshot_id, allocate_canon_snapshot_id, allocate_sandbox_id, allocate_branch_id, normalize_memory_scope, normalize_promotion_scope, materialize_story_start_snapshots


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _clean(value: Any, *, lower: bool = False, limit: int = 0) -> str:
    text = str(value or '').strip()
    if lower:
        text = text.lower()
    if limit > 0:
        text = text[:limit]
    return text



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



def _parse_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, type(default)):
        return deepcopy(raw)
    if not isinstance(raw, str):
        return deepcopy(default)
    try:
        value = json.loads(raw or '')
    except Exception:
        return deepcopy(default)
    if isinstance(default, dict) and isinstance(value, dict):
        return value
    if isinstance(default, list) and isinstance(value, list):
        return value
    return deepcopy(default)



def _touch_meta(record: dict[str, Any], *, default_status: str = 'draft') -> dict[str, Any]:
    meta = record.get('meta') if isinstance(record.get('meta'), dict) else {}
    if not meta.get('created_at'):
        meta['created_at'] = _now_iso()
    meta['updated_at'] = _now_iso()
    meta['status'] = _clean(meta.get('status') or default_status, lower=True, limit=40) or default_status
    record['meta'] = meta
    return record



def _apply_story_start_snapshot_summary(record: dict[str, Any], *, source_summary: dict[str, Any] | None = None, canon_summary: dict[str, Any] | None = None, inherited_from_storyline_id: str = '') -> dict[str, Any]:
    extra = record.get('extra') if isinstance(record.get('extra'), dict) else {}
    payload = {
        'status': 'frozen',
        'source': deepcopy(source_summary) if isinstance(source_summary, dict) else {},
        'canon': deepcopy(canon_summary) if isinstance(canon_summary, dict) else {},
    }
    if _clean(inherited_from_storyline_id, limit=120):
        payload['inherited_from_storyline_id'] = _clean(inherited_from_storyline_id, limit=120)
    extra['story_start_snapshot'] = payload
    record['extra'] = extra
    return record



def _list_records(directory, normalizer) -> list[dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        items.append(normalizer(row))
    return items



def _storyline_summary(row: dict[str, Any], *, session_count: int = 0, checkpoint_count: int = 0) -> dict[str, Any]:
    meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
    return {
        'id': _clean(row.get('id')),
        'title': _clean(row.get('title')),
        'summary': _clean(row.get('summary')),
        'project_id': _clean(row.get('project_id')),
        'linked_world_id': _clean(row.get('linked_world_id')),
        'linked_universe_id': _clean(row.get('linked_universe_id')),
        'linked_scenario_ids': _clean_list(row.get('linked_scenario_ids') or [], limit=120),
        'linked_entity_ids': _clean_list(row.get('linked_entity_ids') or [], limit=120),
        'tags': _clean_list(row.get('tags') or [], limit=64),
        'cover': _json_dict(row.get('cover')),
        'continuity_policy': _clean(row.get('continuity_policy') or 'runtime_anchored', lower=True),
        'source_snapshot_id': _clean(row.get('source_snapshot_id')),
        'canon_snapshot_id': _clean(row.get('canon_snapshot_id')),
        'active_sandbox_id': _clean(row.get('active_sandbox_id')),
        'root_branch_id': _clean(row.get('root_branch_id')),
        'active_session_id': _clean(row.get('active_session_id')),
        'session_count': max(0, int(session_count or 0)),
        'checkpoint_count': max(0, int(checkpoint_count or 0)),
        'status': _clean(meta.get('status') or 'draft', lower=True),
        'updated_at': _clean(meta.get('updated_at')),
    }



def _session_summary(row: dict[str, Any], *, checkpoint_count: int = 0) -> dict[str, Any]:
    meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
    return {
        'id': _clean(row.get('id')),
        'storyline_id': _clean(row.get('storyline_id')),
        'project_id': _clean(row.get('project_id')),
        'session_mode': _clean(row.get('session_mode'), lower=True),
        'seed_checkpoint_id': _clean(row.get('seed_checkpoint_id')),
        'active_checkpoint_id': _clean(row.get('active_checkpoint_id')),
        'checkpoint_count': max(0, int(checkpoint_count or len(row.get('checkpoint_ids') or []))),
        'seed_runtime_bundle_id': _clean(row.get('seed_runtime_bundle_id')),
        'latest_runtime_bundle_id': _clean(row.get('latest_runtime_bundle_id')),
        'continuity_mode': _clean(row.get('continuity_mode') or 'runtime_anchored', lower=True),
        'source_snapshot_id': _clean(row.get('source_snapshot_id')),
        'canon_snapshot_id': _clean(row.get('canon_snapshot_id')),
        'sandbox_id': _clean(row.get('sandbox_id')),
        'branch_id': _clean(row.get('branch_id')),
        'memory_scope': _clean(row.get('memory_scope') or 'sandbox', lower=True),
        'promotion_scope': _clean(row.get('promotion_scope') or 'sandbox_only', lower=True),
        'output_preset': _clean(row.get('output_preset') or 'roleplay', lower=True),
        'interaction_mode': _clean(row.get('interaction_mode') or 'roleplay', lower=True),
        'session_summary': _clean(row.get('session_summary')),
        'last_turn_at': _clean(row.get('last_turn_at')),
        'turn_count': max(0, int(row.get('turn_count') or 0)),
        'autosave_enabled': bool(row.get('autosave_enabled', True)),
        'status': _clean(meta.get('status') or 'draft', lower=True),
        'updated_at': _clean(meta.get('updated_at')),
    }



def _checkpoint_summary(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
    return {
        'id': _clean(row.get('id')),
        'storyline_id': _clean(row.get('storyline_id')),
        'session_id': _clean(row.get('session_id')),
        'checkpoint_type': _clean(row.get('checkpoint_type') or 'live_save', lower=True),
        'title': _clean(row.get('title')),
        'summary': _clean(row.get('summary')),
        'parent_checkpoint_id': _clean(row.get('parent_checkpoint_id')),
        'branch_label': _clean(row.get('branch_label')),
        'order_index': max(0, int(row.get('order_index') or 0)),
        'runtime_bundle_id': _clean(row.get('runtime_bundle_id')),
        'runtime_source_scope': _clean(row.get('runtime_source_scope'), lower=True),
        'source_snapshot_id': _clean(row.get('source_snapshot_id')),
        'canon_snapshot_id': _clean(row.get('canon_snapshot_id')),
        'sandbox_id': _clean(row.get('sandbox_id')),
        'branch_id': _clean(row.get('branch_id')),
        'memory_scope': _clean(row.get('memory_scope') or 'sandbox', lower=True),
        'promotion_scope': _clean(row.get('promotion_scope') or 'sandbox_only', lower=True),
        'runtime_source_id': _clean(row.get('runtime_source_id')),
        'selected_entity_ids': _clean_list(row.get('selected_entity_ids') or [], limit=120),
        'selected_memory_ids': _clean_list(row.get('selected_memory_ids') or [], limit=120),
        'status': _clean(meta.get('status') or 'draft', lower=True),
        'updated_at': _clean(meta.get('updated_at')),
    }



def list_storylines() -> list[dict[str, Any]]:
    items = _list_records(ROLEPLAY_V2_STORYLINES_DIR, normalize_storyline_record)
    sessions = _list_records(ROLEPLAY_V2_STORY_SESSIONS_DIR, normalize_story_session_record)
    checkpoints = _list_records(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR, normalize_story_checkpoint_record)
    session_counts: dict[str, int] = {}
    checkpoint_counts: dict[str, int] = {}
    for row in sessions:
        story_id = _clean(row.get('storyline_id'))
        if story_id:
            session_counts[story_id] = session_counts.get(story_id, 0) + 1
    for row in checkpoints:
        story_id = _clean(row.get('storyline_id'))
        if story_id:
            checkpoint_counts[story_id] = checkpoint_counts.get(story_id, 0) + 1
    summaries = [
        _storyline_summary(row, session_count=session_counts.get(_clean(row.get('id')), 0), checkpoint_count=checkpoint_counts.get(_clean(row.get('id')), 0))
        for row in items
    ]
    summaries.sort(key=lambda row: row.get('updated_at') or '', reverse=True)
    return summaries



def get_storyline(storyline_id: str) -> dict[str, Any] | None:
    clean_id = _clean(storyline_id)
    if not clean_id:
        return None
    row = load_saved_record('storyline', clean_id)
    return normalize_storyline_record(row) if isinstance(row, dict) else None



def create_storyline(*, title: str, summary: str = '', project_id: str = '', linked_world_id: str = '', linked_universe_id: str = '', linked_scenario_ids: list[str] | str | None = None, linked_entity_ids: list[str] | str | None = None, tags: list[str] | str | None = None, continuity_policy: str = 'runtime_anchored', source_snapshot_id: str = '', canon_snapshot_id: str = '', active_sandbox_id: str = '', root_branch_id: str = '') -> dict[str, Any]:
    clean_title = _clean(title, limit=200)
    if not clean_title:
        raise ValueError('Storyline title is required.')
    storyline = build_storyline_record(
        title=clean_title,
        summary=_clean(summary, limit=4000),
        project_id=_clean(project_id, limit=120),
        linked_world_id=_clean(linked_world_id, limit=120),
        linked_universe_id=_clean(linked_universe_id, limit=120),
        linked_scenario_ids=_clean_list(_parse_json(linked_scenario_ids, []) if isinstance(linked_scenario_ids, str) else (linked_scenario_ids or []), limit=120),
        linked_entity_ids=_clean_list(_parse_json(linked_entity_ids, []) if isinstance(linked_entity_ids, str) else (linked_entity_ids or []), limit=120),
        tags=_clean_list(_parse_json(tags, []) if isinstance(tags, str) else (tags or []), limit=64),
        continuity_policy=continuity_policy,
        source_snapshot_id=allocate_source_snapshot_id(source_snapshot_id),
        canon_snapshot_id=allocate_canon_snapshot_id(canon_snapshot_id),
        active_sandbox_id=_clean(active_sandbox_id, limit=120),
        root_branch_id=_clean(root_branch_id or allocate_branch_id(''), limit=120),
    )
    snapshot_payload = materialize_story_start_snapshots(
        storyline=storyline,
        source_snapshot_id=storyline.get('source_snapshot_id'),
        canon_snapshot_id=storyline.get('canon_snapshot_id'),
    )
    storyline['source_snapshot_id'] = _clean(snapshot_payload.get('source_snapshot_id'), limit=120)
    storyline['canon_snapshot_id'] = _clean(snapshot_payload.get('canon_snapshot_id'), limit=120)
    _apply_story_start_snapshot_summary(
        storyline,
        source_summary=snapshot_payload.get('source_summary') if isinstance(snapshot_payload, dict) else {},
        canon_summary=snapshot_payload.get('canon_summary') if isinstance(snapshot_payload, dict) else {},
    )
    _touch_meta(storyline, default_status='draft')
    return save_record(storyline)



def list_story_sessions(storyline_id: str) -> list[dict[str, Any]]:
    clean_story_id = _clean(storyline_id)
    if not clean_story_id:
        return []
    sessions = [row for row in _list_records(ROLEPLAY_V2_STORY_SESSIONS_DIR, normalize_story_session_record) if _clean(row.get('storyline_id')) == clean_story_id]
    checkpoints = _list_records(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR, normalize_story_checkpoint_record)
    checkpoint_counts: dict[str, int] = {}
    for row in checkpoints:
        session_id = _clean(row.get('session_id'))
        if session_id:
            checkpoint_counts[session_id] = checkpoint_counts.get(session_id, 0) + 1
    items = [_session_summary(row, checkpoint_count=checkpoint_counts.get(_clean(row.get('id')), 0)) for row in sessions]
    items.sort(key=lambda row: row.get('updated_at') or '', reverse=True)
    return items



def get_story_session(session_id: str) -> dict[str, Any] | None:
    clean_id = _clean(session_id)
    if not clean_id:
        return None
    row = load_saved_record('story_session', clean_id)
    return normalize_story_session_record(row) if isinstance(row, dict) else None



def create_story_session(*, storyline_id: str, project_id: str = '', session_mode: str = 'live_scene', seed_checkpoint_id: str = '', seed_runtime_bundle_id: str = '', continuity_mode: str = 'runtime_anchored', source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox', promotion_scope: str = 'sandbox_only', output_preset: str = 'roleplay', interaction_mode: str = 'roleplay', scene_state_seed: dict[str, Any] | str | None = None, session_summary: str = '') -> dict[str, Any]:
    storyline = get_storyline(storyline_id)
    if not storyline:
        raise ValueError('Storyline not found.')
    clean_scene_state_seed = normalize_scene_state(_parse_json(scene_state_seed, {}) if isinstance(scene_state_seed, str) else (scene_state_seed or {}))
    mode_model = normalize_mode_model(
        output_preset=output_preset or clean_scene_state_seed.get('output_preset') or 'roleplay',
        interaction_mode=interaction_mode or clean_scene_state_seed.get('interaction_mode') or 'roleplay',
        prefer='output',
    )
    clean_scene_state_seed['output_preset'] = str(mode_model.get('output_preset') or 'roleplay').strip().lower()
    clean_scene_state_seed['interaction_mode'] = str(mode_model.get('interaction_mode') or 'roleplay').strip().lower()
    snapshot_payload = materialize_story_start_snapshots(
        storyline=storyline,
        source_snapshot_id=source_snapshot_id or storyline.get('source_snapshot_id'),
        canon_snapshot_id=canon_snapshot_id or storyline.get('canon_snapshot_id'),
        scene_state_seed=clean_scene_state_seed,
        seed_runtime_bundle_id=_clean(seed_runtime_bundle_id, limit=120),
    )
    storyline['source_snapshot_id'] = _clean(snapshot_payload.get('source_snapshot_id'), limit=120)
    storyline['canon_snapshot_id'] = _clean(snapshot_payload.get('canon_snapshot_id'), limit=120)
    _apply_story_start_snapshot_summary(
        storyline,
        source_summary=snapshot_payload.get('source_summary') if isinstance(snapshot_payload, dict) else {},
        canon_summary=snapshot_payload.get('canon_summary') if isinstance(snapshot_payload, dict) else {},
    )
    session = build_story_session_record(
        storyline_id=_clean(storyline_id, limit=120),
        project_id=_clean(project_id or storyline.get('project_id'), limit=120),
        session_mode=session_mode,
        seed_checkpoint_id=_clean(seed_checkpoint_id, limit=120),
        seed_runtime_bundle_id=_clean(seed_runtime_bundle_id, limit=120),
        continuity_mode=continuity_mode or storyline.get('continuity_policy') or 'runtime_anchored',
        source_snapshot_id=_clean(snapshot_payload.get('source_snapshot_id'), limit=120),
        canon_snapshot_id=_clean(snapshot_payload.get('canon_snapshot_id'), limit=120),
        sandbox_id=allocate_sandbox_id(sandbox_id),
        branch_id=allocate_branch_id(branch_id or storyline.get('root_branch_id')),
        memory_scope=normalize_memory_scope(memory_scope),
        promotion_scope=normalize_promotion_scope(promotion_scope),
        output_preset=mode_model.get('output_preset') or 'roleplay',
        interaction_mode=mode_model.get('interaction_mode') or 'roleplay',
        scene_state_seed=clean_scene_state_seed,
        session_summary=_clean(session_summary, limit=4000),
    )
    _apply_story_start_snapshot_summary(
        session,
        source_summary=snapshot_payload.get('source_summary') if isinstance(snapshot_payload, dict) else {},
        canon_summary=snapshot_payload.get('canon_summary') if isinstance(snapshot_payload, dict) else {},
        inherited_from_storyline_id=_clean(storyline.get('id'), limit=120),
    )
    _touch_meta(session, default_status='draft')
    saved = save_record(session)
    storyline['session_ids'] = _clean_list((storyline.get('session_ids') or []) + [_clean(saved.get('id'))], limit=120)
    storyline['active_session_id'] = _clean(saved.get('id'), limit=120)
    storyline['active_sandbox_id'] = _clean(saved.get('sandbox_id'), limit=120)
    _touch_meta(storyline, default_status=_clean((storyline.get('meta') or {}).get('status') or 'draft', lower=True) or 'draft')
    save_record(storyline)
    return saved



def list_story_checkpoints(*, storyline_id: str = '', session_id: str = '') -> list[dict[str, Any]]:
    clean_story_id = _clean(storyline_id)
    clean_session_id = _clean(session_id)
    items = []
    for row in _list_records(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR, normalize_story_checkpoint_record):
        if clean_story_id and _clean(row.get('storyline_id')) != clean_story_id:
            continue
        if clean_session_id and _clean(row.get('session_id')) != clean_session_id:
            continue
        items.append(_checkpoint_summary(row))
    items.sort(key=lambda row: (int(row.get('order_index') or 0), row.get('updated_at') or ''))
    return items



def get_story_checkpoint(checkpoint_id: str) -> dict[str, Any] | None:
    clean_id = _clean(checkpoint_id)
    if not clean_id:
        return None
    row = load_saved_record('story_checkpoint', clean_id)
    return normalize_story_checkpoint_record(row) if isinstance(row, dict) else None



def _scene_text_from_transcript(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in transcript or []:
        if not isinstance(item, dict):
            continue
        role = _clean(item.get('role'), lower=True)
        content = _clean(item.get('content'), limit=12000)
        if not role or not content:
            continue
        lines.append(f"{role.title()}: {content}")
    return '\n\n'.join(lines)[:160000]




def _runtime_scene_state_seed(bundle_id: str) -> dict[str, Any]:
    clean_bundle_id = _clean(bundle_id)
    if not clean_bundle_id:
        return {}
    bundle = get_runtime_bundle(clean_bundle_id)
    if not isinstance(bundle, dict):
        return {}
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    seed = packet.get('scene_state_seed') if isinstance(packet.get('scene_state_seed'), dict) else {}
    return normalize_scene_state(seed)



def _focus_entity_id(*, continuity_payload: dict[str, Any], scene_state: dict[str, Any], selected_entity_ids: list[str]) -> str:
    candidates = [
        _clean((continuity_payload.get('focus_id') if isinstance(continuity_payload, dict) else '') or ''),
        _clean(((scene_state.get('focus_stack') or [None])[0] if isinstance(scene_state.get('focus_stack'), list) and scene_state.get('focus_stack') else '')),
        _clean(selected_entity_ids[0] if selected_entity_ids else ''),
        _clean((continuity_payload.get('saved_memory_fragment_id') if isinstance(continuity_payload, dict) else '') or ''),
    ]
    for item in candidates:
        if item:
            return item
    return ''




def _build_checkpoint_continuity_snapshot(*, project_id: str, runtime_bundle_id: str, scene_state: dict[str, Any], continuity_payload: dict[str, Any], selected_entity_ids: list[str], story_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    focus_entity_id = _focus_entity_id(continuity_payload=continuity_payload, scene_state=scene_state, selected_entity_ids=selected_entity_ids)
    source_ref = _clean((continuity_payload.get('writeback_source_ref') if isinstance(continuity_payload, dict) else '') or '')
    scope = _json_dict(story_scope)
    turn_data = fetch_rp2_turn_summary_debug_rows(
        bundle_id=runtime_bundle_id,
        project_id=project_id,
        entity_id=focus_entity_id,
        source_ref=source_ref,
        limit=8,
        source_snapshot_id=_clean(scope.get('source_snapshot_id'), limit=120),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id'), limit=120),
        sandbox_id=_clean(scope.get('sandbox_id'), limit=120),
        storyline_id=_clean(scope.get('storyline_id'), limit=120),
        session_id=_clean(scope.get('session_id'), limit=120),
        checkpoint_id=_clean(scope.get('checkpoint_id'), limit=120),
        branch_id=_clean(scope.get('branch_id'), limit=120),
        memory_scope=_clean(scope.get('memory_scope'), lower=True, limit=80),
    )
    relationship_state = fetch_rp2_relationship_state_rows(
        entity_id=focus_entity_id,
        project_id=project_id,
        limit=6,
        source_snapshot_id=_clean(scope.get('source_snapshot_id'), limit=120),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id'), limit=120),
        sandbox_id=_clean(scope.get('sandbox_id'), limit=120),
        storyline_id=_clean(scope.get('storyline_id'), limit=120),
        session_id=_clean(scope.get('session_id'), limit=120),
        checkpoint_id=_clean(scope.get('checkpoint_id'), limit=120),
        branch_id=_clean(scope.get('branch_id'), limit=120),
        memory_scope=_clean(scope.get('memory_scope'), lower=True, limit=80),
        promotion_scope=_clean(scope.get('promotion_scope'), lower=True, limit=80),
    )
    post_turn = fetch_rp2_post_turn_memory_debug_rows(
        bundle_id=runtime_bundle_id,
        entity_id=focus_entity_id,
        source_ref=source_ref,
        limit=16,
        source_snapshot_id=_clean(scope.get('source_snapshot_id'), limit=120),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id'), limit=120),
        sandbox_id=_clean(scope.get('sandbox_id'), limit=120),
        storyline_id=_clean(scope.get('storyline_id'), limit=120),
        session_id=_clean(scope.get('session_id'), limit=120),
        checkpoint_id=_clean(scope.get('checkpoint_id'), limit=120),
        branch_id=_clean(scope.get('branch_id'), limit=120),
        memory_scope=_clean(scope.get('memory_scope'), lower=True, limit=80),
        promotion_scope=_clean(scope.get('promotion_scope'), lower=True, limit=80),
    )
    memory_rows = post_turn.get('memory_fragments') or []
    unresolved_threads = [row for row in memory_rows if _clean(row.get('memory_type')) == 'thread_state'][:6]
    callback_anchors = post_turn.get('callback_anchors') or []
    return {
        'runtime_bundle_id': _clean(runtime_bundle_id),
        'focus_entity_id': focus_entity_id,
        'source_ref': source_ref,
        'story_scope': scope,
        'turn_summaries': turn_data.get('rows') or [],
        'relationship_state': relationship_state.get('rows') or [],
        'unresolved_threads': unresolved_threads,
        'callback_anchors': callback_anchors[:6],
        'memory_fragments': memory_rows[:10],
        'shared_memories': post_turn.get('shared_memories') or [],
    }

def _merge_resume_scene_state(*, runtime_seed: dict[str, Any], session_seed: dict[str, Any], checkpoint_state: dict[str, Any], continuity_snapshot: dict[str, Any], continuity_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = normalize_scene_state({**(runtime_seed or {}), **(session_seed or {}), **(checkpoint_state or {})})
    trace = {
        'runtime_seed_keys': sorted(list((runtime_seed or {}).keys())),
        'session_seed_keys': sorted(list((session_seed or {}).keys())),
        'checkpoint_state_keys': sorted(list((checkpoint_state or {}).keys())),
        'continuity_snapshot_keys': sorted(list((continuity_snapshot or {}).keys())),
    }
    focus_stack = list(merged.get('focus_stack') or [])
    focus_entity_id = _clean((continuity_snapshot.get('focus_entity_id') if isinstance(continuity_snapshot, dict) else '') or '')
    if focus_entity_id and focus_entity_id not in focus_stack:
        focus_stack.insert(0, focus_entity_id)
    for row in (continuity_snapshot.get('relationship_state') or [])[:3]:
        target_id = _clean((row.get('target_entity_id') or row.get('source_entity_id')) if isinstance(row, dict) else '')
        if target_id and target_id not in focus_stack:
            focus_stack.append(target_id)
    merged['focus_stack'] = [item for item in focus_stack if _clean(item)][:6]
    memory_source_ids = list(merged.get('memory_source_ids') or [])
    for row in (continuity_snapshot.get('unresolved_threads') or [])[:4]:
        memory_id = _clean(row.get('memory_id') or row.get('callback_id') or '')
        if memory_id and memory_id not in memory_source_ids:
            memory_source_ids.append(memory_id)
    merged['memory_source_ids'] = memory_source_ids[:8]
    merged['continuity_mode'] = _clean((checkpoint_state.get('continuity_mode') if isinstance(checkpoint_state, dict) else '') or (session_seed.get('continuity_mode') if isinstance(session_seed, dict) else '') or (continuity_payload.get('continuity_mode') if isinstance(continuity_payload, dict) else '') or merged.get('continuity_mode') or 'runtime_anchored')
    merged['resume_turn_summary_ids'] = [_clean(row.get('turn_summary_id')) for row in (continuity_snapshot.get('turn_summaries') or []) if _clean(row.get('turn_summary_id'))][:8]
    merged['resume_relationship_state_ids'] = [_clean(row.get('relationship_state_id')) for row in (continuity_snapshot.get('relationship_state') or []) if _clean(row.get('relationship_state_id'))][:8]
    merged['resume_unresolved_thread_ids'] = [_clean(row.get('memory_id')) for row in (continuity_snapshot.get('unresolved_threads') or []) if _clean(row.get('memory_id'))][:8]
    return merged, trace



def _merge_resume_continuity_payload(*, base_payload: dict[str, Any], continuity_snapshot: dict[str, Any], merged_scene_state: dict[str, Any], merge_trace: dict[str, Any]) -> dict[str, Any]:
    payload = _json_dict(base_payload)
    payload['continuity_snapshot'] = _json_dict(continuity_snapshot)
    payload['resume_merge_trace'] = _json_dict(merge_trace)
    payload['scene_state'] = _json_dict(merged_scene_state)
    payload['resume_turn_summary_ids'] = _clean_list([row.get('turn_summary_id') for row in (continuity_snapshot.get('turn_summaries') or [])], limit=120)
    payload['resume_relationship_state_ids'] = _clean_list([row.get('relationship_state_id') for row in (continuity_snapshot.get('relationship_state') or [])], limit=120)
    payload['resume_unresolved_thread_ids'] = _clean_list([row.get('memory_id') for row in (continuity_snapshot.get('unresolved_threads') or [])], limit=120)
    payload['writeback_source_ref'] = _clean((continuity_snapshot.get('source_ref') if isinstance(continuity_snapshot, dict) else '') or (payload.get('writeback_source_ref') if isinstance(payload, dict) else '') or '')
    if not _clean(payload.get('turn_summary_text')) and (continuity_snapshot.get('turn_summaries') or []):
        payload['turn_summary_text'] = _clean(((continuity_snapshot.get('turn_summaries') or [{}])[0]).get('summary'), limit=4000)
    return payload


def _mode_lock_snapshot(*, output_preset: str = '', interaction_mode: str = '', scene_state: dict[str, Any] | None = None, continuity_payload: dict[str, Any] | None = None, runtime_bundle_id: str = '') -> dict[str, Any]:
    scene_state = normalize_scene_state(scene_state or {})
    continuity_payload = _json_dict(continuity_payload)
    mode_model = normalize_mode_model(
        output_preset=output_preset or scene_state.get('output_preset') or continuity_payload.get('output_preset') or 'roleplay',
        interaction_mode=interaction_mode or scene_state.get('interaction_mode') or continuity_payload.get('interaction_mode') or 'roleplay',
        prefer='output',
    )
    return {
        'output_preset': _clean(mode_model.get('output_preset') or 'roleplay', lower=True),
        'interaction_mode': _clean(mode_model.get('interaction_mode') or 'roleplay', lower=True),
        'continuity_mode': _clean(scene_state.get('continuity_mode') or continuity_payload.get('continuity_mode') or 'runtime_anchored', lower=True) or 'runtime_anchored',
        'runtime_bundle_id': _clean(runtime_bundle_id, limit=120),
        'captured_at': _now_iso(),
    }


def _resolve_resume_mode_lock(*, session: dict[str, Any], checkpoint: dict[str, Any] | None, merged_scene_state: dict[str, Any], continuity_payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    session_extra = session.get('extra') if isinstance(session.get('extra'), dict) else {}
    checkpoint_extra = (checkpoint or {}).get('extra') if isinstance((checkpoint or {}).get('extra'), dict) else {}
    session_lock = _json_dict(session_extra.get('mode_lock'))
    checkpoint_lock = _json_dict(checkpoint_extra.get('mode_lock'))
    continuity_lock = _json_dict(continuity_payload.get('mode_lock'))
    scene_output = _clean(merged_scene_state.get('output_preset') or '', lower=True)
    scene_interaction = _clean(merged_scene_state.get('interaction_mode') or '', lower=True)

    resolved = {
        'output_preset': _clean(checkpoint_lock.get('output_preset') or continuity_lock.get('output_preset') or session_lock.get('output_preset') or session.get('output_preset') or scene_output or 'roleplay', lower=True) or 'roleplay',
        'interaction_mode': _clean(checkpoint_lock.get('interaction_mode') or continuity_lock.get('interaction_mode') or session_lock.get('interaction_mode') or session.get('interaction_mode') or scene_interaction or 'roleplay', lower=True) or 'roleplay',
        'continuity_mode': _clean(checkpoint_lock.get('continuity_mode') or continuity_lock.get('continuity_mode') or session_lock.get('continuity_mode') or session.get('continuity_mode') or merged_scene_state.get('continuity_mode') or 'runtime_anchored', lower=True) or 'runtime_anchored',
        'session_mode_lock': session_lock,
        'checkpoint_mode_lock': checkpoint_lock,
        'continuity_mode_lock': continuity_lock,
    }
    warnings: list[str] = []
    if session_lock and checkpoint_lock and _clean(session_lock.get('output_preset'), lower=True) and _clean(checkpoint_lock.get('output_preset'), lower=True) and _clean(session_lock.get('output_preset'), lower=True) != _clean(checkpoint_lock.get('output_preset'), lower=True):
        warnings.append(f"Session mode lock is {_clean(session_lock.get('output_preset'), lower=True)} but checkpoint mode lock is {_clean(checkpoint_lock.get('output_preset'), lower=True)}.")
    if scene_output and resolved['output_preset'] != scene_output:
        warnings.append(f"Resume is restoring output preset {resolved['output_preset']} over scene-state seed {scene_output}.")
    if scene_interaction and resolved['interaction_mode'] != scene_interaction:
        warnings.append(f"Resume is restoring interaction mode {resolved['interaction_mode']} over scene-state seed {scene_interaction}.")
    resolved['mode_drift_detected'] = bool(warnings)
    return resolved, warnings

def save_story_checkpoint(
    *,
    storyline_id: str,
    session_id: str,
    title: str = '',
    summary: str = '',
    checkpoint_type: str = 'live_save',
    transcript: list[dict[str, Any]] | str | None = None,
    scene_text: str = '',
    scene_state: dict[str, Any] | str | None = None,
    continuity_payload: dict[str, Any] | str | None = None,
    runtime_bundle_id: str = '',
    runtime_source_scope: str = '',
    runtime_source_id: str = '',
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    branch_id: str = '',
    memory_scope: str = 'sandbox',
    promotion_scope: str = 'sandbox_only',
    selected_entity_ids: list[str] | str | None = None,
    selected_memory_ids: list[str] | str | None = None,
    linked_scenario_ids: list[str] | str | None = None,
    linked_entity_ids: list[str] | str | None = None,
    parent_checkpoint_id: str = '',
    branch_label: str = '',
    branch_choice: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    storyline = get_storyline(storyline_id)
    if not storyline:
        raise ValueError('Storyline not found.')
    session = get_story_session(session_id)
    if not session or _clean(session.get('storyline_id')) != _clean(storyline_id):
        raise ValueError('Story session not found.')

    clean_transcript = _parse_json(transcript, []) if isinstance(transcript, str) else _json_list(transcript)
    clean_scene_state = normalize_scene_state(_parse_json(scene_state, {}) if isinstance(scene_state, str) else (scene_state or {}))
    clean_continuity = _parse_json(continuity_payload, {}) if isinstance(continuity_payload, str) else _json_dict(continuity_payload)
    clean_selected_entity_ids = _clean_list(_parse_json(selected_entity_ids, []) if isinstance(selected_entity_ids, str) else (selected_entity_ids or []), limit=120)
    clean_project_id = _clean(storyline.get('project_id') or session.get('project_id'), limit=120)
    mode_lock = _mode_lock_snapshot(
        output_preset=_clean(clean_scene_state.get('output_preset') or session.get('output_preset') or 'roleplay', lower=True),
        interaction_mode=_clean(clean_scene_state.get('interaction_mode') or session.get('interaction_mode') or 'roleplay', lower=True),
        scene_state=clean_scene_state,
        continuity_payload=clean_continuity,
        runtime_bundle_id=_clean(runtime_bundle_id, limit=120),
    )
    continuity_snapshot = _build_checkpoint_continuity_snapshot(
        project_id=clean_project_id,
        runtime_bundle_id=_clean(runtime_bundle_id, limit=120),
        scene_state=clean_scene_state,
        continuity_payload=clean_continuity,
        selected_entity_ids=clean_selected_entity_ids,
        story_scope=(resolve_story_scope_from_ids(storyline_id=_clean(storyline_id, limit=120), session_id=_clean(session_id, limit=120)).get('story_scope') or {}),
    )
    clean_continuity = _merge_resume_continuity_payload(
        base_payload={**clean_continuity, 'mode_lock': mode_lock},
        continuity_snapshot=continuity_snapshot,
        merged_scene_state={**clean_scene_state, 'output_preset': mode_lock.get('output_preset'), 'interaction_mode': mode_lock.get('interaction_mode')},
        merge_trace={'source': 'checkpoint_save', 'runtime_bundle_id': _clean(runtime_bundle_id, limit=120), 'mode_lock': mode_lock},
    )
    clean_title = _clean(title, limit=200) or f"Checkpoint {len(session.get('checkpoint_ids') or []) + 1}"
    clean_summary = _clean(summary, limit=4000)
    clean_scene_text = _clean(scene_text, limit=160000) or _scene_text_from_transcript(clean_transcript)
    order_index = len(session.get('checkpoint_ids') or []) + 1

    checkpoint = build_story_checkpoint_record(
        storyline_id=_clean(storyline_id, limit=120),
        session_id=_clean(session_id, limit=120),
        checkpoint_type=checkpoint_type,
        title=clean_title,
        summary=clean_summary,
        parent_checkpoint_id=_clean(parent_checkpoint_id, limit=120),
        branch_label=_clean(branch_label, limit=120),
        branch_choice=_parse_json(branch_choice, {}) if isinstance(branch_choice, str) else _json_dict(branch_choice),
        order_index=order_index,
        transcript=clean_transcript,
        scene_text=clean_scene_text,
        scene_state=clean_scene_state,
        continuity_payload=clean_continuity,
        runtime_bundle_id=_clean(runtime_bundle_id, limit=120),
        runtime_source_scope=_clean(runtime_source_scope, lower=True, limit=120),
        runtime_source_id=_clean(runtime_source_id, limit=120),
        source_snapshot_id=allocate_source_snapshot_id(source_snapshot_id or session.get('source_snapshot_id') or storyline.get('source_snapshot_id')),
        canon_snapshot_id=allocate_canon_snapshot_id(canon_snapshot_id or session.get('canon_snapshot_id') or storyline.get('canon_snapshot_id')),
        sandbox_id=allocate_sandbox_id(sandbox_id or session.get('sandbox_id') or storyline.get('active_sandbox_id')),
        branch_id=allocate_branch_id(branch_id or session.get('branch_id') or storyline.get('root_branch_id')),
        memory_scope=normalize_memory_scope(memory_scope),
        promotion_scope=normalize_promotion_scope(promotion_scope),
        selected_entity_ids=clean_selected_entity_ids,
        selected_memory_ids=_clean_list(_parse_json(selected_memory_ids, []) if isinstance(selected_memory_ids, str) else (selected_memory_ids or []), limit=120),
        linked_scenario_ids=_clean_list(_parse_json(linked_scenario_ids, []) if isinstance(linked_scenario_ids, str) else (linked_scenario_ids or storyline.get('linked_scenario_ids') or []), limit=120),
        linked_entity_ids=_clean_list(_parse_json(linked_entity_ids, []) if isinstance(linked_entity_ids, str) else (linked_entity_ids or storyline.get('linked_entity_ids') or []), limit=120),
        extra={'continuity_snapshot': continuity_snapshot, 'mode_lock': mode_lock},
    )
    _touch_meta(checkpoint, default_status='draft')
    saved = save_record(checkpoint)

    checkpoint_id = _clean(saved.get('id'), limit=120)
    session['checkpoint_ids'] = _clean_list((session.get('checkpoint_ids') or []) + [checkpoint_id], limit=120)
    session['active_checkpoint_id'] = checkpoint_id
    session['latest_runtime_bundle_id'] = _clean(runtime_bundle_id, limit=120) or _clean(session.get('latest_runtime_bundle_id'), limit=120)
    session['last_turn_at'] = _clean((saved.get('meta') or {}).get('updated_at'), limit=80) or _now_iso()
    session['turn_count'] = max(0, int(session.get('turn_count') or 0), len([row for row in clean_transcript if isinstance(row, dict) and _clean(row.get('role'), lower=True) == 'user']))
    if clean_summary:
        session['session_summary'] = clean_summary
    if clean_scene_state:
        session['scene_state_seed'] = clean_scene_state
    session['output_preset'] = _clean(mode_lock.get('output_preset') or session.get('output_preset') or 'roleplay', lower=True)
    session['interaction_mode'] = _clean(mode_lock.get('interaction_mode') or session.get('interaction_mode') or 'roleplay', lower=True)
    session_extra = session.get('extra') if isinstance(session.get('extra'), dict) else {}
    session_extra['continuity_snapshot'] = continuity_snapshot
    session_extra['mode_lock'] = mode_lock
    session['extra'] = session_extra
    _touch_meta(session, default_status=_clean((session.get('meta') or {}).get('status') or 'draft', lower=True) or 'draft')
    save_record(session)

    storyline['active_session_id'] = _clean(session.get('id'), limit=120)
    if not _clean(parent_checkpoint_id, limit=120):
        storyline['root_checkpoint_ids'] = _clean_list((storyline.get('root_checkpoint_ids') or []) + [checkpoint_id], limit=120)
    _touch_meta(storyline, default_status=_clean((storyline.get('meta') or {}).get('status') or 'draft', lower=True) or 'draft')
    save_record(storyline)
    return saved





def resolve_story_scope_from_ids(*, storyline_id: str = '', session_id: str = '', checkpoint_id: str = '') -> dict[str, Any]:
    active_storyline = get_storyline(storyline_id) if _clean(storyline_id) else None
    active_session = get_story_session(session_id) if _clean(session_id) else None
    active_checkpoint = get_story_checkpoint(checkpoint_id) if _clean(checkpoint_id) else None
    if active_checkpoint and not active_session:
        active_session = get_story_session(_clean(active_checkpoint.get('session_id')))
    if active_session and not active_storyline:
        active_storyline = get_storyline(_clean(active_session.get('storyline_id')))
    if active_storyline and not active_session and _clean(active_storyline.get('active_session_id')):
        active_session = get_story_session(_clean(active_storyline.get('active_session_id')))
    if active_session and not active_checkpoint and _clean(active_session.get('active_checkpoint_id')):
        active_checkpoint = get_story_checkpoint(_clean(active_session.get('active_checkpoint_id')))
    story_scope = {
        'source_snapshot_id': _clean((active_checkpoint or {}).get('source_snapshot_id') or (active_session or {}).get('source_snapshot_id') or (active_storyline or {}).get('source_snapshot_id'), limit=120),
        'canon_snapshot_id': _clean((active_checkpoint or {}).get('canon_snapshot_id') or (active_session or {}).get('canon_snapshot_id') or (active_storyline or {}).get('canon_snapshot_id'), limit=120),
        'sandbox_id': _clean((active_checkpoint or {}).get('sandbox_id') or (active_session or {}).get('sandbox_id') or (active_storyline or {}).get('active_sandbox_id'), limit=120),
        'storyline_id': _clean((active_storyline or {}).get('id'), limit=120),
        'session_id': _clean((active_session or {}).get('id'), limit=120),
        'checkpoint_id': _clean((active_checkpoint or {}).get('id'), limit=120),
        'branch_id': _clean((active_checkpoint or {}).get('branch_id') or (active_session or {}).get('branch_id') or (active_storyline or {}).get('root_branch_id'), limit=120),
        'memory_scope': normalize_memory_scope((active_checkpoint or {}).get('memory_scope') or (active_session or {}).get('memory_scope') or 'sandbox'),
        'promotion_scope': normalize_promotion_scope((active_checkpoint or {}).get('promotion_scope') or (active_session or {}).get('promotion_scope') or 'sandbox_only'),
    }
    return {
        'storyline': active_storyline,
        'session': active_session,
        'checkpoint': active_checkpoint,
        'story_scope': story_scope,
    }


def _shared_publish_targets(storyline: dict[str, Any]) -> dict[str, str]:
    return {
        'shared_world': _clean(storyline.get('linked_world_id'), limit=120),
        'shared_universe': _clean(storyline.get('linked_universe_id'), limit=120),
    }



def _shared_scope_payload(storyline: dict[str, Any], publish_scope: str) -> dict[str, str]:
    clean_scope = normalize_promotion_scope(publish_scope, 'sandbox_only')
    targets = _shared_publish_targets(storyline)
    scope_value = _clean(targets.get(clean_scope), limit=120)
    payload = {
        'publish_scope': clean_scope,
        'shared_world_id': targets.get('shared_world', ''),
        'shared_universe_id': targets.get('shared_universe', ''),
        'scope_value': scope_value,
        'scope_key': f'{clean_scope}:{scope_value}' if clean_scope in {'shared_world', 'shared_universe'} and scope_value else '',
    }
    return payload



def _shared_publication_record_id(prefix: str, publish_scope: str, original_id: str, checkpoint_id: str) -> str:
    clean_prefix = _clean(prefix, lower=True, limit=24) or 'sharedpub'
    clean_scope = _clean(publish_scope, lower=True, limit=24) or 'shared'
    clean_original = _clean(original_id, limit=48) or 'row'
    clean_checkpoint = _clean(checkpoint_id, limit=32) or 'checkpoint'
    return f'{clean_prefix}_{clean_scope}_{clean_checkpoint}_{clean_original}'[:120]



def _shared_publication_summary(storyline: dict[str, Any]) -> dict[str, Any]:
    extra = storyline.get('extra') if isinstance(storyline.get('extra'), dict) else {}
    summary = extra.get('shared_continuity_summary') if isinstance(extra.get('shared_continuity_summary'), dict) else {}
    published_counts = summary.get('published_counts') if isinstance(summary.get('published_counts'), dict) else {}
    return {
        'published_counts': {key: int(published_counts.get(key) or 0) for key in ['shared_world', 'shared_universe']},
        'last_published_at': _clean(summary.get('last_published_at'), limit=80),
        'last_checkpoint_id': _clean(summary.get('last_checkpoint_id'), limit=120),
        'shared_world_id': _clean(summary.get('shared_world_id') or storyline.get('linked_world_id'), limit=120),
        'shared_universe_id': _clean(summary.get('shared_universe_id') or storyline.get('linked_universe_id'), limit=120),
    }



def publish_checkpoint_shared_continuity(*, storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', publish_scope: str = 'shared_world') -> dict[str, Any]:
    storyline = get_storyline(storyline_id)
    if not storyline:
        raise ValueError('Storyline not found.')
    session = get_story_session(session_id) if _clean(session_id, limit=120) else None
    checkpoint = get_story_checkpoint(checkpoint_id) if _clean(checkpoint_id, limit=120) else None
    if checkpoint and not session:
        session = get_story_session(_clean(checkpoint.get('session_id'), limit=120))
    if session and _clean(session.get('storyline_id'), limit=120) != _clean(storyline.get('id'), limit=120):
        raise ValueError('Story session does not belong to this storyline.')
    if checkpoint and session and _clean(checkpoint.get('session_id'), limit=120) != _clean(session.get('id'), limit=120):
        raise ValueError('Checkpoint does not belong to this session.')
    if not session:
        raise ValueError('Story session not found.')
    if not checkpoint:
        active_checkpoint_id = _clean(session.get('active_checkpoint_id'), limit=120)
        checkpoint = get_story_checkpoint(active_checkpoint_id) if active_checkpoint_id else None
    if not checkpoint:
        raise ValueError('Story checkpoint not found.')

    shared_scope = _shared_scope_payload(storyline, publish_scope)
    if shared_scope['publish_scope'] not in {'shared_world', 'shared_universe'}:
        raise ValueError('Pick a valid shared continuity scope.')
    if not shared_scope['scope_value']:
        raise ValueError(f"This storyline is not linked to a {shared_scope['publish_scope'].replace('shared_', '')} scope yet.")

    continuity_snapshot = _json_dict(((checkpoint.get('extra') or {}).get('continuity_snapshot')))
    if not continuity_snapshot:
        continuity_snapshot = _build_checkpoint_continuity_snapshot(
            project_id=_clean(storyline.get('project_id') or session.get('project_id'), limit=120),
            runtime_bundle_id=_clean(checkpoint.get('runtime_bundle_id'), limit=120),
            scene_state=normalize_scene_state(checkpoint.get('scene_state') or session.get('scene_state_seed') or {}),
            continuity_payload=_json_dict(checkpoint.get('continuity_payload')),
            selected_entity_ids=_clean_list(checkpoint.get('selected_entity_ids') or [], limit=120),
            story_scope=(resolve_story_scope_from_ids(storyline_id=_clean(storyline.get('id'), limit=120), session_id=_clean(session.get('id'), limit=120), checkpoint_id=_clean(checkpoint.get('id'), limit=120)).get('story_scope') or {}),
        )

    project_id = _clean(storyline.get('project_id') or session.get('project_id'), limit=120)
    source_snapshot_id = _clean(checkpoint.get('source_snapshot_id') or session.get('source_snapshot_id') or storyline.get('source_snapshot_id'), limit=120)
    canon_snapshot_id = _clean(checkpoint.get('canon_snapshot_id') or session.get('canon_snapshot_id') or storyline.get('canon_snapshot_id'), limit=120)
    branch_id = _clean(checkpoint.get('branch_id') or session.get('branch_id') or storyline.get('root_branch_id'), limit=120)
    published_at = _now_iso()

    fragment_rows: list[dict[str, Any]] = []
    shared_rows: list[dict[str, Any]] = []
    relationship_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in continuity_snapshot.get('memory_fragments') or []:
        if not isinstance(row, dict):
            continue
        memory_type = _clean(row.get('memory_type'), lower=True, limit=80)
        memory_id = _clean(row.get('memory_id') or row.get('id'), limit=120)
        if not memory_type or not memory_id:
            continue
        published_id = _shared_publication_record_id('sharedpub', shared_scope['publish_scope'], memory_id, _clean(checkpoint.get('id'), limit=120))
        text_payload = _clean(row.get('summary') or row.get('text'), limit=6000)
        if not text_payload:
            skipped.append({'kind': memory_type, 'reason': 'empty_memory_text', 'source_id': memory_id})
            continue
        fragment_rows.append(build_memory_fragment_record(
            memory_type=memory_type,
            fragment_id=published_id,
            entity_id=_clean(row.get('entity_id'), limit=120),
            title=_clean(row.get('title'), limit=200) or f'Shared continuity · {memory_type}',
            canonical_text=text_payload,
            scene_ready_text=text_payload,
            source_ref=_clean(row.get('source_ref'), limit=240),
            world_id=shared_scope['shared_world_id'],
            universe_id=shared_scope['shared_universe_id'],
            source_snapshot_id=source_snapshot_id,
            canon_snapshot_id=canon_snapshot_id,
            sandbox_id='',
            storyline_id=_clean(checkpoint.get('storyline_id'), limit=120),
            session_id=_clean(checkpoint.get('session_id'), limit=120),
            checkpoint_id=_clean(checkpoint.get('id'), limit=120),
            branch_id=branch_id,
            memory_scope='durable',
            promotion_scope=shared_scope['publish_scope'],
            relationship_target_ids=_clean_list(row.get('relationship_target_ids') or [], limit=120),
            tags=_clean_list(list(row.get('tags') or []) + ['shared_continuity', shared_scope['publish_scope'], 'published_checkpoint'], limit=80),
            salience=float(row.get('salience') or 0.0),
            emotional_valence='charged',
            canon_status='approved',
            confidence=max(0.6, float(row.get('confidence') or 0.0)),
            extra={
                'project_id': project_id,
                'promotion_status': 'published_shared_continuity',
                'shared_scope_key': shared_scope['scope_key'],
                'shared_world_id': shared_scope['shared_world_id'],
                'shared_universe_id': shared_scope['shared_universe_id'],
                'published_from_storyline_id': _clean(checkpoint.get('storyline_id'), limit=120),
                'published_from_session_id': _clean(checkpoint.get('session_id'), limit=120),
                'published_from_checkpoint_id': _clean(checkpoint.get('id'), limit=120),
                'published_at': published_at,
            },
            meta={'status': 'published_shared_continuity'},
        ))

    for row in continuity_snapshot.get('shared_memories') or []:
        if not isinstance(row, dict):
            continue
        source_id = _clean(row.get('shared_memory_id') or row.get('id'), limit=120)
        if not source_id:
            continue
        text_payload = _clean(row.get('text') or row.get('summary'), limit=6000)
        if not text_payload:
            skipped.append({'kind': 'shared_memory', 'reason': 'empty_shared_text', 'source_id': source_id})
            continue
        participant_ids = _clean_list([row.get('entity_a_id'), row.get('entity_b_id')] + list(row.get('participant_ids') or []), limit=120)
        shared_rows.append(build_shared_memory_record(
            shared_memory_id=_shared_publication_record_id('sharedmem', shared_scope['publish_scope'], source_id, _clean(checkpoint.get('id'), limit=120)),
            participant_ids=participant_ids,
            title=_clean(row.get('label') or row.get('title'), limit=200) or 'Shared continuity memory',
            summary=text_payload,
            source_ref=_clean(row.get('source_ref'), limit=240),
            source_snapshot_id=source_snapshot_id,
            canon_snapshot_id=canon_snapshot_id,
            sandbox_id='',
            storyline_id=_clean(checkpoint.get('storyline_id'), limit=120),
            session_id=_clean(checkpoint.get('session_id'), limit=120),
            checkpoint_id=_clean(checkpoint.get('id'), limit=120),
            branch_id=branch_id,
            memory_scope='durable',
            promotion_scope=shared_scope['publish_scope'],
            salience=float(row.get('salience') or 0.0),
            extra={
                'project_id': project_id,
                'promotion_status': 'published_shared_continuity',
                'promotion_confidence': max(0.6, float(row.get('confidence') or 0.0)),
                'shared_scope_key': shared_scope['scope_key'],
                'shared_world_id': shared_scope['shared_world_id'],
                'shared_universe_id': shared_scope['shared_universe_id'],
                'published_from_storyline_id': _clean(checkpoint.get('storyline_id'), limit=120),
                'published_from_session_id': _clean(checkpoint.get('session_id'), limit=120),
                'published_from_checkpoint_id': _clean(checkpoint.get('id'), limit=120),
                'published_at': published_at,
            },
            meta={'status': 'published_shared_continuity'},
        ))

    for row in continuity_snapshot.get('relationship_state') or []:
        if not isinstance(row, dict):
            continue
        source_id = _clean(row.get('relationship_state_id'), limit=120)
        if not source_id:
            continue
        relationship_rows.append({
            'relationship_state_id': _shared_publication_record_id('sharedrel', shared_scope['publish_scope'], source_id, _clean(checkpoint.get('id'), limit=120)),
            'source_entity_id': _clean(row.get('source_entity_id'), limit=120),
            'target_entity_id': _clean(row.get('target_entity_id'), limit=120),
            'project_id': project_id,
            'bundle_id': _clean(row.get('bundle_id'), limit=120),
            'source_ref': _clean(row.get('source_ref'), limit=240),
            'relationship_label': _clean(row.get('relationship_label'), limit=200),
            'summary': _clean(row.get('summary'), limit=4000),
            'trust_level': float(row.get('trust_level') or 0.0),
            'tension_level': float(row.get('tension_level') or 0.0),
            'drift_score': float(row.get('drift_score') or 0.0),
            'carry_forward': bool(row.get('carry_forward')),
            'state_payload': {
                **(_json_dict(row.get('state_payload'))),
                'shared_scope_key': shared_scope['scope_key'],
                'shared_world_id': shared_scope['shared_world_id'],
                'shared_universe_id': shared_scope['shared_universe_id'],
                'published_from_storyline_id': _clean(checkpoint.get('storyline_id'), limit=120),
                'published_from_session_id': _clean(checkpoint.get('session_id'), limit=120),
                'published_from_checkpoint_id': _clean(checkpoint.get('id'), limit=120),
                'published_at': published_at,
            },
            'source_snapshot_id': source_snapshot_id,
            'canon_snapshot_id': canon_snapshot_id,
            'sandbox_id': '',
            'storyline_id': _clean(checkpoint.get('storyline_id'), limit=120),
            'session_id': _clean(checkpoint.get('session_id'), limit=120),
            'checkpoint_id': _clean(checkpoint.get('id'), limit=120),
            'branch_id': branch_id,
            'memory_scope': 'durable',
            'promotion_scope': shared_scope['publish_scope'],
        })

    sqlite_sync = upsert_rp2_memory_outputs(
        memory_fragments=fragment_rows,
        shared_memories=shared_rows,
        builder_record_id='',
        canon_id='',
        source_ref=f'shared_publish:{_clean(checkpoint.get("id"), limit=120)}',
        prune_existing=False,
    )
    for row in relationship_rows:
        persist_rp2_relationship_state(**row)

    checkpoint_extra = checkpoint.get('extra') if isinstance(checkpoint.get('extra'), dict) else {}
    shared_publications = checkpoint_extra.get('shared_continuity_publications') if isinstance(checkpoint_extra.get('shared_continuity_publications'), dict) else {}
    shared_publications[shared_scope['publish_scope']] = {
        'published_at': published_at,
        'shared_scope_key': shared_scope['scope_key'],
        'shared_world_id': shared_scope['shared_world_id'],
        'shared_universe_id': shared_scope['shared_universe_id'],
        'memory_fragment_ids': _clean_list([row.get('id') for row in fragment_rows], limit=120),
        'shared_memory_ids': _clean_list([row.get('id') for row in shared_rows], limit=120),
        'relationship_state_ids': _clean_list([row.get('relationship_state_id') for row in relationship_rows], limit=120),
        'published_counts': {
            'memory_fragments': len(fragment_rows),
            'shared_memories': len(shared_rows),
            'relationship_state': len(relationship_rows),
            'total': len(fragment_rows) + len(shared_rows) + len(relationship_rows),
        },
    }
    checkpoint_extra['shared_continuity_publications'] = shared_publications
    checkpoint['extra'] = checkpoint_extra
    _touch_meta(checkpoint, default_status=_clean((checkpoint.get('meta') or {}).get('status') or 'draft', lower=True) or 'draft')
    save_record(checkpoint)

    storyline_extra = storyline.get('extra') if isinstance(storyline.get('extra'), dict) else {}
    summary = storyline_extra.get('shared_continuity_summary') if isinstance(storyline_extra.get('shared_continuity_summary'), dict) else {}
    published_counts = summary.get('published_counts') if isinstance(summary.get('published_counts'), dict) else {}
    published_counts[shared_scope['publish_scope']] = int(published_counts.get(shared_scope['publish_scope']) or 0) + len(fragment_rows) + len(shared_rows) + len(relationship_rows)
    summary.update({
        'published_counts': published_counts,
        'last_published_at': published_at,
        'last_checkpoint_id': _clean(checkpoint.get('id'), limit=120),
        'shared_world_id': shared_scope['shared_world_id'],
        'shared_universe_id': shared_scope['shared_universe_id'],
        'last_publish_scope': shared_scope['publish_scope'],
    })
    storyline_extra['shared_continuity_summary'] = summary
    storyline['extra'] = storyline_extra
    _touch_meta(storyline, default_status=_clean((storyline.get('meta') or {}).get('status') or 'draft', lower=True) or 'draft')
    save_record(storyline)

    return {
        'ok': True,
        'publish_scope': shared_scope['publish_scope'],
        'shared_scope_key': shared_scope['scope_key'],
        'shared_world_id': shared_scope['shared_world_id'],
        'shared_universe_id': shared_scope['shared_universe_id'],
        'storyline_id': _clean(storyline.get('id'), limit=120),
        'session_id': _clean(session.get('id'), limit=120),
        'checkpoint_id': _clean(checkpoint.get('id'), limit=120),
        'published_at': published_at,
        'published_counts': {
            'memory_fragments': len(fragment_rows),
            'shared_memories': len(shared_rows),
            'relationship_state': len(relationship_rows),
            'total': len(fragment_rows) + len(shared_rows) + len(relationship_rows),
        },
        'sqlite_sync': sqlite_sync,
        'skipped': skipped,
    }


def get_storyline_detail(storyline_id: str) -> dict[str, Any]:
    storyline = get_storyline(storyline_id)
    if not storyline:
        raise ValueError('Storyline not found.')
    sessions = [get_story_session(item['id']) for item in list_story_sessions(storyline_id)]
    session_rows = [row for row in sessions if isinstance(row, dict)]
    checkpoints = [get_story_checkpoint(item['id']) for item in list_story_checkpoints(storyline_id=storyline_id)]
    checkpoint_rows = [row for row in checkpoints if isinstance(row, dict)]
    return {
        'storyline': storyline,
        'storyline_summary': _storyline_summary(storyline, session_count=len(session_rows), checkpoint_count=len(checkpoint_rows)),
        'sessions': session_rows,
        'session_summaries': [_session_summary(row, checkpoint_count=len([cp for cp in checkpoint_rows if _clean(cp.get('session_id')) == _clean(row.get('id'))])) for row in session_rows],
        'checkpoints': checkpoint_rows,
        'checkpoint_summaries': [_checkpoint_summary(row) for row in checkpoint_rows],
    }




def build_story_resume_payload(*, storyline_id: str = '', session_id: str = '', checkpoint_id: str = '') -> dict[str, Any]:
    scope_resolution = resolve_story_scope_from_ids(storyline_id=storyline_id, session_id=session_id, checkpoint_id=checkpoint_id)
    active_storyline = scope_resolution.get('storyline')
    active_session = scope_resolution.get('session')
    active_checkpoint = scope_resolution.get('checkpoint')
    story_scope = _json_dict(scope_resolution.get('story_scope'))

    if not active_storyline:
        raise ValueError('Storyline not found.')
    if not active_session:
        raise ValueError('Story session not found.')

    runtime_bundle_id = _clean((active_checkpoint or {}).get('runtime_bundle_id')) or _clean(active_session.get('latest_runtime_bundle_id')) or _clean(active_session.get('seed_runtime_bundle_id'))
    runtime_seed = _runtime_scene_state_seed(runtime_bundle_id)
    session_seed = normalize_scene_state(active_session.get('scene_state_seed') or {})
    checkpoint_state = normalize_scene_state((active_checkpoint or {}).get('scene_state') or {})
    base_continuity = _json_dict((active_checkpoint or {}).get('continuity_payload'))
    continuity_snapshot = _json_dict(((active_checkpoint or {}).get('extra') or {}).get('continuity_snapshot')) or _json_dict((active_session.get('extra') or {}).get('continuity_snapshot'))
    if not continuity_snapshot:
        continuity_snapshot = _build_checkpoint_continuity_snapshot(
            project_id=_clean(active_storyline.get('project_id') or active_session.get('project_id'), limit=120),
            runtime_bundle_id=runtime_bundle_id,
            scene_state=checkpoint_state or session_seed,
            continuity_payload=base_continuity,
            selected_entity_ids=_clean_list((active_checkpoint or {}).get('selected_entity_ids') or []),
            story_scope=story_scope,
        )
    merged_scene_state, merge_trace = _merge_resume_scene_state(
        runtime_seed=runtime_seed,
        session_seed=session_seed,
        checkpoint_state=checkpoint_state,
        continuity_snapshot=continuity_snapshot,
        continuity_payload=base_continuity,
    )
    mode_lock, mode_lock_warnings = _resolve_resume_mode_lock(
        session=active_session,
        checkpoint=active_checkpoint,
        merged_scene_state=merged_scene_state,
        continuity_payload=base_continuity,
    )
    merged_scene_state['output_preset'] = _clean(mode_lock.get('output_preset') or merged_scene_state.get('output_preset') or 'roleplay', lower=True)
    merged_scene_state['interaction_mode'] = _clean(mode_lock.get('interaction_mode') or merged_scene_state.get('interaction_mode') or 'roleplay', lower=True)
    merged_scene_state['continuity_mode'] = _clean(mode_lock.get('continuity_mode') or merged_scene_state.get('continuity_mode') or 'runtime_anchored', lower=True)
    merged_scene_state['story_scope'] = _json_dict(story_scope)
    merge_trace['mode_lock'] = mode_lock
    merge_trace['mode_lock_warnings'] = list(mode_lock_warnings)
    merge_trace['story_scope'] = _json_dict(story_scope)
    merged_continuity = _merge_resume_continuity_payload(
        base_payload={**base_continuity, 'mode_lock': mode_lock, 'mode_lock_warnings': mode_lock_warnings, 'story_scope': story_scope},
        continuity_snapshot=continuity_snapshot,
        merged_scene_state=merged_scene_state,
        merge_trace=merge_trace,
    )
    payload = {
        'storyline': active_storyline,
        'session': active_session,
        'checkpoint': active_checkpoint,
        'resume': {
            'storyline_id': _clean(active_storyline.get('id')),
            'session_id': _clean(active_session.get('id')),
            'checkpoint_id': _clean((active_checkpoint or {}).get('id')),
            'runtime_bundle_id': runtime_bundle_id,
            'story_scope': story_scope,
            'transcript': _json_list((active_checkpoint or {}).get('transcript') or []),
            'scene_state': merged_scene_state,
            'continuity_payload': merged_continuity,
            'continuity_snapshot': continuity_snapshot,
            'resume_merge_trace': merge_trace,
            'mode_lock': mode_lock,
            'mode_lock_warnings': list(mode_lock_warnings),
            'output_preset': _clean(mode_lock.get('output_preset') or active_session.get('output_preset') or 'roleplay', lower=True),
            'interaction_mode': _clean(mode_lock.get('interaction_mode') or active_session.get('interaction_mode') or 'roleplay', lower=True),
        },
    }
    return payload

