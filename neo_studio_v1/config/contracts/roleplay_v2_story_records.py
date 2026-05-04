from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .roleplay_v2_mode_model import normalize_mode_model
from uuid import uuid4

ROLEPLAY_V2_STORY_SCHEMA_VERSION = 1
ROLEPLAY_V2_STORY_RECORD_TYPES = {
    'storyline',
    'story_session',
    'story_checkpoint',
    'story_draft_snapshot',
}
ROLEPLAY_V2_STORY_STATUSES = {
    'draft',
    'active',
    'paused',
    'complete',
    'archived',
}
ROLEPLAY_V2_STORY_SESSION_MODES = {
    'live_scene',
    'import_seeded',
    'reader_resume',
    'authoring',
}
ROLEPLAY_V2_STORY_CHECKPOINT_TYPES = {
    'live_save',
    'branch',
    'import_seed',
    'chapter_mark',
    'milestone',
}
ROLEPLAY_V2_STORY_CONTINUITY_POLICIES = {
    'runtime_anchored',
    'session_persistent',
    'fresh_scene',
}
ROLEPLAY_V2_STORY_MEMORY_SCOPES = {
    'source',
    'sandbox',
    'durable',
}
ROLEPLAY_V2_STORY_PROMOTION_SCOPES = {
    'sandbox_only',
    'shared_world',
    'shared_universe',
    'durable_project',
}


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



def _meta(meta: dict[str, Any] | None = None, *, default_status: str = 'draft') -> dict[str, Any]:
    row = _json_dict(meta)
    now = _now_iso()
    status = _clean(row.get('status') or default_status, lower=True, limit=40)
    if status not in ROLEPLAY_V2_STORY_STATUSES:
        status = default_status
    return {
        'created_at': _clean(row.get('created_at')) or now,
        'updated_at': _clean(row.get('updated_at')) or now,
        'status': status,
        'notes': _clean(row.get('notes'), limit=4000),
    }



def _record_id(prefix: str, provided: str = '') -> str:
    return _clean(provided, limit=120) or f'{prefix}_{uuid4().hex[:10]}'



def _continuity_policy(value: Any, *, default: str = 'runtime_anchored') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_STORY_CONTINUITY_POLICIES else default



def _memory_scope(value: Any, *, default: str = 'sandbox') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_STORY_MEMORY_SCOPES else default



def _promotion_scope(value: Any, *, default: str = 'sandbox_only') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_STORY_PROMOTION_SCOPES else default



def build_storyline_record(
    *,
    storyline_id: str = '',
    title: str = '',
    summary: str = '',
    project_id: str = '',
    linked_world_id: str = '',
    linked_universe_id: str = '',
    linked_scenario_ids: list[str] | None = None,
    linked_entity_ids: list[str] | None = None,
    tags: list[str] | None = None,
    cover: dict[str, Any] | None = None,
    default_runtime_profile: dict[str, Any] | None = None,
    continuity_policy: str = 'runtime_anchored',
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    active_sandbox_id: str = '',
    root_branch_id: str = '',
    active_session_id: str = '',
    session_ids: list[str] | None = None,
    source_document_ids: list[str] | None = None,
    root_checkpoint_ids: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_STORY_SCHEMA_VERSION,
        'record_type': 'storyline',
        'id': _record_id('storyline', storyline_id),
        'title': _clean(title, limit=200),
        'summary': _clean(summary, limit=4000),
        'project_id': _clean(project_id, limit=120),
        'linked_world_id': _clean(linked_world_id, limit=120),
        'linked_universe_id': _clean(linked_universe_id, limit=120),
        'linked_scenario_ids': _clean_list(linked_scenario_ids or [], limit=120),
        'linked_entity_ids': _clean_list(linked_entity_ids or [], limit=120),
        'tags': _clean_list(tags or [], limit=64),
        'cover': _json_dict(cover),
        'default_runtime_profile': _json_dict(default_runtime_profile),
        'continuity_policy': _continuity_policy(continuity_policy),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'active_sandbox_id': _clean(active_sandbox_id, limit=120),
        'root_branch_id': _clean(root_branch_id, limit=120),
        'active_session_id': _clean(active_session_id, limit=120),
        'session_ids': _clean_list(session_ids or [], limit=120),
        'source_document_ids': _clean_list(source_document_ids or [], limit=120),
        'root_checkpoint_ids': _clean_list(root_checkpoint_ids or [], limit=120),
        'extra': _json_dict(extra),
        'meta': _meta(meta, default_status='draft'),
    }



def normalize_storyline_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_storyline_record(
        storyline_id=raw.get('id') or raw.get('storyline_id') or '',
        title=raw.get('title') or raw.get('label') or '',
        summary=raw.get('summary') or '',
        project_id=raw.get('project_id') or '',
        linked_world_id=raw.get('linked_world_id') or '',
        linked_universe_id=raw.get('linked_universe_id') or '',
        linked_scenario_ids=raw.get('linked_scenario_ids') or [],
        linked_entity_ids=raw.get('linked_entity_ids') or [],
        tags=raw.get('tags') or [],
        cover=raw.get('cover'),
        default_runtime_profile=raw.get('default_runtime_profile'),
        continuity_policy=raw.get('continuity_policy') or 'runtime_anchored',
        source_snapshot_id=raw.get('source_snapshot_id') or '',
        canon_snapshot_id=raw.get('canon_snapshot_id') or '',
        active_sandbox_id=raw.get('active_sandbox_id') or '',
        root_branch_id=raw.get('root_branch_id') or '',
        active_session_id=raw.get('active_session_id') or '',
        session_ids=raw.get('session_ids') or [],
        source_document_ids=raw.get('source_document_ids') or [],
        root_checkpoint_ids=raw.get('root_checkpoint_ids') or [],
        meta=raw.get('meta'),
        extra=raw.get('extra'),
    )



def build_story_session_record(
    *,
    session_id: str = '',
    storyline_id: str = '',
    project_id: str = '',
    session_mode: str = 'live_scene',
    seed_checkpoint_id: str = '',
    active_checkpoint_id: str = '',
    checkpoint_ids: list[str] | None = None,
    seed_runtime_bundle_id: str = '',
    latest_runtime_bundle_id: str = '',
    continuity_mode: str = 'runtime_anchored',
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    branch_id: str = '',
    memory_scope: str = 'sandbox',
    promotion_scope: str = 'sandbox_only',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    scene_state_seed: dict[str, Any] | None = None,
    session_summary: str = '',
    last_turn_at: str = '',
    turn_count: int = 0,
    autosave_enabled: bool = True,
    meta: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_mode = _clean(session_mode or 'live_scene', lower=True, limit=80)
    if clean_mode not in ROLEPLAY_V2_STORY_SESSION_MODES:
        clean_mode = 'live_scene'
    mode_model = normalize_mode_model(output_preset=output_preset, interaction_mode=interaction_mode, prefer='output')
    return {
        'schema_version': ROLEPLAY_V2_STORY_SCHEMA_VERSION,
        'record_type': 'story_session',
        'id': _record_id('story_session', session_id),
        'storyline_id': _clean(storyline_id, limit=120),
        'project_id': _clean(project_id, limit=120),
        'session_mode': clean_mode,
        'seed_checkpoint_id': _clean(seed_checkpoint_id, limit=120),
        'active_checkpoint_id': _clean(active_checkpoint_id, limit=120),
        'checkpoint_ids': _clean_list(checkpoint_ids or [], limit=120),
        'seed_runtime_bundle_id': _clean(seed_runtime_bundle_id, limit=120),
        'latest_runtime_bundle_id': _clean(latest_runtime_bundle_id, limit=120),
        'continuity_mode': _continuity_policy(continuity_mode),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'memory_scope': _memory_scope(memory_scope),
        'promotion_scope': _promotion_scope(promotion_scope),
        'output_preset': _clean(mode_model.get('output_preset') or 'roleplay', lower=True, limit=80),
        'interaction_mode': _clean(mode_model.get('interaction_mode') or 'roleplay', lower=True, limit=80),
        'scene_state_seed': _json_dict(scene_state_seed),
        'session_summary': _clean(session_summary, limit=4000),
        'last_turn_at': _clean(last_turn_at, limit=80),
        'turn_count': max(0, int(turn_count or 0)),
        'autosave_enabled': bool(autosave_enabled),
        'extra': _json_dict(extra),
        'meta': _meta(meta, default_status='draft'),
    }



def normalize_story_session_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_story_session_record(
        session_id=raw.get('id') or raw.get('session_id') or '',
        storyline_id=raw.get('storyline_id') or '',
        project_id=raw.get('project_id') or '',
        session_mode=raw.get('session_mode') or 'live_scene',
        seed_checkpoint_id=raw.get('seed_checkpoint_id') or '',
        active_checkpoint_id=raw.get('active_checkpoint_id') or '',
        checkpoint_ids=raw.get('checkpoint_ids') or [],
        seed_runtime_bundle_id=raw.get('seed_runtime_bundle_id') or '',
        latest_runtime_bundle_id=raw.get('latest_runtime_bundle_id') or '',
        continuity_mode=raw.get('continuity_mode') or 'runtime_anchored',
        source_snapshot_id=raw.get('source_snapshot_id') or '',
        canon_snapshot_id=raw.get('canon_snapshot_id') or '',
        sandbox_id=raw.get('sandbox_id') or '',
        branch_id=raw.get('branch_id') or '',
        memory_scope=raw.get('memory_scope') or 'sandbox',
        promotion_scope=raw.get('promotion_scope') or 'sandbox_only',
        output_preset=raw.get('output_preset') or 'roleplay',
        interaction_mode=raw.get('interaction_mode') or 'roleplay',
        scene_state_seed=raw.get('scene_state_seed'),
        session_summary=raw.get('session_summary') or '',
        last_turn_at=raw.get('last_turn_at') or '',
        turn_count=raw.get('turn_count') or 0,
        autosave_enabled=raw.get('autosave_enabled', True),
        meta=raw.get('meta'),
        extra=raw.get('extra'),
    )



def build_story_checkpoint_record(
    *,
    checkpoint_id: str = '',
    storyline_id: str = '',
    session_id: str = '',
    checkpoint_type: str = 'live_save',
    title: str = '',
    summary: str = '',
    parent_checkpoint_id: str = '',
    branch_label: str = '',
    branch_choice: dict[str, Any] | None = None,
    order_index: int = 0,
    transcript: list[dict[str, Any]] | None = None,
    scene_text: str = '',
    scene_state: dict[str, Any] | None = None,
    continuity_payload: dict[str, Any] | None = None,
    runtime_bundle_id: str = '',
    runtime_source_scope: str = '',
    runtime_source_id: str = '',
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    branch_id: str = '',
    memory_scope: str = 'sandbox',
    promotion_scope: str = 'sandbox_only',
    selected_entity_ids: list[str] | None = None,
    selected_memory_ids: list[str] | None = None,
    linked_scenario_ids: list[str] | None = None,
    linked_entity_ids: list[str] | None = None,
    memory_fragment_ids: list[str] | None = None,
    shared_memory_ids: list[str] | None = None,
    progression: dict[str, Any] | None = None,
    reader_snapshot: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_type = _clean(checkpoint_type or 'live_save', lower=True, limit=80)
    if clean_type not in ROLEPLAY_V2_STORY_CHECKPOINT_TYPES:
        clean_type = 'live_save'
    return {
        'schema_version': ROLEPLAY_V2_STORY_SCHEMA_VERSION,
        'record_type': 'story_checkpoint',
        'id': _record_id('story_checkpoint', checkpoint_id),
        'storyline_id': _clean(storyline_id, limit=120),
        'session_id': _clean(session_id, limit=120),
        'checkpoint_type': clean_type,
        'title': _clean(title, limit=200),
        'summary': _clean(summary, limit=4000),
        'parent_checkpoint_id': _clean(parent_checkpoint_id, limit=120),
        'branch_label': _clean(branch_label, limit=120),
        'branch_choice': _json_dict(branch_choice),
        'order_index': max(0, int(order_index or 0)),
        'transcript': _json_list(transcript),
        'scene_text': _clean(scene_text, limit=160000),
        'scene_state': _json_dict(scene_state),
        'continuity_payload': _json_dict(continuity_payload),
        'runtime_bundle_id': _clean(runtime_bundle_id, limit=120),
        'runtime_source_scope': _clean(runtime_source_scope, lower=True, limit=120),
        'runtime_source_id': _clean(runtime_source_id, limit=120),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'memory_scope': _memory_scope(memory_scope),
        'promotion_scope': _promotion_scope(promotion_scope),
        'selected_entity_ids': _clean_list(selected_entity_ids or [], limit=120),
        'selected_memory_ids': _clean_list(selected_memory_ids or [], limit=120),
        'linked_scenario_ids': _clean_list(linked_scenario_ids or [], limit=120),
        'linked_entity_ids': _clean_list(linked_entity_ids or [], limit=120),
        'memory_fragment_ids': _clean_list(memory_fragment_ids or [], limit=120),
        'shared_memory_ids': _clean_list(shared_memory_ids or [], limit=120),
        'progression': _json_dict(progression),
        'reader_snapshot': _json_dict(reader_snapshot),
        'extra': _json_dict(extra),
        'meta': _meta(meta, default_status='draft'),
    }



def normalize_story_checkpoint_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_story_checkpoint_record(
        checkpoint_id=raw.get('id') or raw.get('checkpoint_id') or '',
        storyline_id=raw.get('storyline_id') or '',
        session_id=raw.get('session_id') or '',
        checkpoint_type=raw.get('checkpoint_type') or 'live_save',
        title=raw.get('title') or '',
        summary=raw.get('summary') or '',
        parent_checkpoint_id=raw.get('parent_checkpoint_id') or '',
        branch_label=raw.get('branch_label') or '',
        branch_choice=raw.get('branch_choice'),
        order_index=raw.get('order_index') or 0,
        transcript=raw.get('transcript'),
        scene_text=raw.get('scene_text') or '',
        scene_state=raw.get('scene_state'),
        continuity_payload=raw.get('continuity_payload'),
        runtime_bundle_id=raw.get('runtime_bundle_id') or '',
        runtime_source_scope=raw.get('runtime_source_scope') or '',
        runtime_source_id=raw.get('runtime_source_id') or '',
        source_snapshot_id=raw.get('source_snapshot_id') or '',
        canon_snapshot_id=raw.get('canon_snapshot_id') or '',
        sandbox_id=raw.get('sandbox_id') or '',
        branch_id=raw.get('branch_id') or '',
        memory_scope=raw.get('memory_scope') or 'sandbox',
        promotion_scope=raw.get('promotion_scope') or 'sandbox_only',
        selected_entity_ids=raw.get('selected_entity_ids') or [],
        selected_memory_ids=raw.get('selected_memory_ids') or [],
        linked_scenario_ids=raw.get('linked_scenario_ids') or [],
        linked_entity_ids=raw.get('linked_entity_ids') or [],
        memory_fragment_ids=raw.get('memory_fragment_ids') or [],
        shared_memory_ids=raw.get('shared_memory_ids') or [],
        progression=raw.get('progression'),
        reader_snapshot=raw.get('reader_snapshot'),
        meta=raw.get('meta'),
        extra=raw.get('extra'),
    )



def build_story_draft_snapshot(
    *,
    draft_id: str = '',
    storyline_id: str = '',
    session_id: str = '',
    runtime_bundle_id: str = '',
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    branch_id: str = '',
    transcript: list[dict[str, Any]] | None = None,
    scene_state: dict[str, Any] | None = None,
    unsaved_user_input: str = '',
    meta: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_STORY_SCHEMA_VERSION,
        'record_type': 'story_draft_snapshot',
        'id': _record_id('story_draft', draft_id),
        'storyline_id': _clean(storyline_id, limit=120),
        'session_id': _clean(session_id, limit=120),
        'runtime_bundle_id': _clean(runtime_bundle_id, limit=120),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'transcript': _json_list(transcript),
        'scene_state': _json_dict(scene_state),
        'unsaved_user_input': _clean(unsaved_user_input, limit=12000),
        'extra': _json_dict(extra),
        'meta': _meta(meta, default_status='draft'),
    }



def normalize_story_draft_snapshot(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return build_story_draft_snapshot(
        draft_id=raw.get('id') or raw.get('draft_id') or '',
        storyline_id=raw.get('storyline_id') or '',
        session_id=raw.get('session_id') or '',
        runtime_bundle_id=raw.get('runtime_bundle_id') or '',
        source_snapshot_id=raw.get('source_snapshot_id') or '',
        canon_snapshot_id=raw.get('canon_snapshot_id') or '',
        sandbox_id=raw.get('sandbox_id') or '',
        branch_id=raw.get('branch_id') or '',
        transcript=raw.get('transcript'),
        scene_state=raw.get('scene_state'),
        unsaved_user_input=raw.get('unsaved_user_input') or '',
        meta=raw.get('meta'),
        extra=raw.get('extra'),
    )
