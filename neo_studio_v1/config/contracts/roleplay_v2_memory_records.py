from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .roleplay_v2_mode_model import normalize_mode_model

ROLEPLAY_V2_MEMORY_SCHEMA_VERSION = 1
ROLEPLAY_V2_MEMORY_TYPES = {
    'semantic_fact',
    'episodic_memory',
    'shared_memory',
    'relationship_belief',
    'self_belief',
    'callback_anchor',
    'emotional_wound',
    'goal',
    'secret',
    'voice_rule',
    'canon_guard',
    'thread_state',
}
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
        if text:
            out.append(text)
    return out



def _json_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}



def _memory_scope(value: Any, *, default: str = 'sandbox') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_MEMORY_SCOPES else default



def _promotion_scope(value: Any, *, default: str = 'sandbox_only') -> str:
    clean = _clean(value or default, lower=True, limit=80)
    return clean if clean in ROLEPLAY_V2_PROMOTION_SCOPES else default



def build_memory_fragment_record(*, memory_type: str, entity_id: str = '', fragment_id: str = '', title: str = '', canonical_text: str = '', first_person_text: str = '', scene_ready_text: str = '', source_ref: str = '', source_excerpt: str = '', chapter_ref: str = '', scene_ref: str = '', world_id: str = '', universe_id: str = '', source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox', promotion_scope: str = 'sandbox_only', relationship_target_ids: list[str] | None = None, tags: list[str] | None = None, salience: float = 0.5, emotional_valence: str = 'neutral', canon_status: str = 'approved', confidence: float = 1.0, extra: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_type = _clean(memory_type, lower=True)
    if clean_type not in ROLEPLAY_V2_MEMORY_TYPES:
        raise ValueError('Unsupported roleplay V2 memory type.')
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
        'record_type': 'memory_fragment',
        'id': _clean(fragment_id) or f'mem_{uuid4().hex[:10]}',
        'memory_type': clean_type,
        'entity_id': _clean(entity_id, limit=120),
        'title': _clean(title, limit=200),
        'canonical_text': _clean(canonical_text, limit=12000),
        'first_person_text': _clean(first_person_text, limit=12000),
        'scene_ready_text': _clean(scene_ready_text, limit=12000),
        'source_ref': _clean(source_ref, limit=500),
        'source_excerpt': _clean(source_excerpt, limit=4000),
        'chapter_ref': _clean(chapter_ref, limit=120),
        'scene_ref': _clean(scene_ref, limit=120),
        'world_id': _clean(world_id, limit=120),
        'universe_id': _clean(universe_id, limit=120),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'storyline_id': _clean(storyline_id, limit=120),
        'session_id': _clean(session_id, limit=120),
        'checkpoint_id': _clean(checkpoint_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'memory_scope': _memory_scope(memory_scope),
        'promotion_scope': _promotion_scope(promotion_scope),
        'relationship_target_ids': _clean_list(relationship_target_ids or [], limit=120),
        'tags': _clean_list(tags or [], limit=64),
        'salience': max(0.0, min(1.0, float(salience or 0.0))),
        'emotional_valence': _clean(emotional_valence or 'neutral', limit=40, lower=True),
        'canon_status': _clean(canon_status or 'approved', limit=40, lower=True),
        'confidence': max(0.0, min(1.0, float(confidence or 0.0))),
        'extra': _json_dict(extra),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'active', lower=True),
            'notes': _clean(meta_row.get('notes'), limit=4000),
        },
    }



def build_timeline_event_record(*, event_id: str = '', entity_id: str = '', title: str = '', summary: str = '', event_order: int = 0, chapter_ref: str = '', scene_ref: str = '', participants: list[str] | None = None, source_ref: str = '', extra: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
        'record_type': 'timeline_event',
        'id': _clean(event_id) or f'event_{uuid4().hex[:10]}',
        'entity_id': _clean(entity_id, limit=120),
        'title': _clean(title, limit=200),
        'summary': _clean(summary, limit=12000),
        'event_order': max(0, int(event_order or 0)),
        'chapter_ref': _clean(chapter_ref, limit=120),
        'scene_ref': _clean(scene_ref, limit=120),
        'participants': _clean_list(participants or [], limit=120),
        'source_ref': _clean(source_ref, limit=500),
        'extra': _json_dict(extra),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'active', lower=True),
        },
    }



def build_relationship_record(*, relationship_id: str = '', source_entity_id: str = '', target_entity_id: str = '', relationship_type: str = '', summary: str = '', trust_level: float = 0.5, tension_level: float = 0.0, bond_tags: list[str] | None = None, source_ref: str = '', extra: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
        'record_type': 'relationship_record',
        'id': _clean(relationship_id) or f'rel_{uuid4().hex[:10]}',
        'source_entity_id': _clean(source_entity_id, limit=120),
        'target_entity_id': _clean(target_entity_id, limit=120),
        'relationship_type': _clean(relationship_type, limit=80, lower=True),
        'summary': _clean(summary, limit=8000),
        'trust_level': max(0.0, min(1.0, float(trust_level or 0.0))),
        'tension_level': max(0.0, min(1.0, float(tension_level or 0.0))),
        'bond_tags': _clean_list(bond_tags or [], limit=64),
        'source_ref': _clean(source_ref, limit=500),
        'extra': _json_dict(extra),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'active', lower=True),
        },
    }



def build_shared_memory_record(*, shared_memory_id: str = '', participant_ids: list[str] | None = None, title: str = '', summary: str = '', source_ref: str = '', chapter_ref: str = '', scene_ref: str = '', source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox', promotion_scope: str = 'sandbox_only', salience: float = 0.5, extra: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
        'record_type': 'shared_memory',
        'id': _clean(shared_memory_id) or f'shared_{uuid4().hex[:10]}',
        'participant_ids': _clean_list(participant_ids or [], limit=120),
        'title': _clean(title, limit=200),
        'summary': _clean(summary, limit=12000),
        'source_ref': _clean(source_ref, limit=500),
        'chapter_ref': _clean(chapter_ref, limit=120),
        'scene_ref': _clean(scene_ref, limit=120),
        'source_snapshot_id': _clean(source_snapshot_id, limit=120),
        'canon_snapshot_id': _clean(canon_snapshot_id, limit=120),
        'sandbox_id': _clean(sandbox_id, limit=120),
        'storyline_id': _clean(storyline_id, limit=120),
        'session_id': _clean(session_id, limit=120),
        'checkpoint_id': _clean(checkpoint_id, limit=120),
        'branch_id': _clean(branch_id, limit=120),
        'memory_scope': _memory_scope(memory_scope),
        'promotion_scope': _promotion_scope(promotion_scope),
        'salience': max(0.0, min(1.0, float(salience or 0.0))),
        'extra': _json_dict(extra),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'active', lower=True),
        },
    }



def build_runtime_bundle_record(*, bundle_id: str = '', mode: str = 'roleplay', interaction_mode: str = 'roleplay', mode_goal: str = '', source_scope: str = '', source_id: str = '', selected_entity_ids: list[str] | None = None, selected_memory_ids: list[str] | None = None, packet: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    mode_model = normalize_mode_model(output_preset=mode, interaction_mode=interaction_mode, prefer='output')
    return {
        'schema_version': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
        'record_type': 'runtime_bundle',
        'id': _clean(bundle_id) or f'bundle_{uuid4().hex[:10]}',
        'mode': _clean(mode_model.get('output_preset') or 'roleplay', limit=80, lower=True),
        'interaction_mode': _clean(mode_model.get('interaction_mode') or 'roleplay', limit=80, lower=True),
        'mode_goal': _clean(mode_goal or mode_model.get('goal_key') or 'roleplay', limit=80, lower=True),
        'source_scope': _clean(source_scope, limit=120, lower=True),
        'source_id': _clean(source_id, limit=120),
        'selected_entity_ids': _clean_list(selected_entity_ids or [], limit=120),
        'selected_memory_ids': _clean_list(selected_memory_ids or [], limit=120),
        'packet': _json_dict(packet),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'draft', lower=True),
        },
    }
