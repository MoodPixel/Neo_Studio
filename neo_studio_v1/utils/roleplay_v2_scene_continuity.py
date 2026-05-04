from __future__ import annotations

import hashlib
from typing import Any

from ..contracts.roleplay_v2_memory_records import build_memory_fragment_record, build_shared_memory_record
from .roleplay_v2_package_store import save_record


def _clean(value: Any, limit: int = 0) -> str:
    text = str(value or '').strip()
    if limit > 0:
        text = text[:limit]
    return text


def _scope_value(scope: dict[str, Any] | None, key: str, default: str = '') -> str:
    if not isinstance(scope, dict):
        return default
    return _clean(scope.get(key) or default, limit=120 if key.endswith('_id') else 80)


def _scope_token(scope: dict[str, Any] | None, *, bundle_id: str = '') -> str:
    parts = [
        _scope_value(scope, 'checkpoint_id'),
        _scope_value(scope, 'branch_id'),
        _scope_value(scope, 'session_id'),
        _scope_value(scope, 'sandbox_id'),
        _scope_value(scope, 'storyline_id'),
        _clean(bundle_id, limit=120),
    ]
    raw = '|'.join(parts).strip('|') or _clean(bundle_id, limit=120) or 'unscoped'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


def _compact_turns(transcript: list[dict[str, Any]], limit: int = 4) -> list[str]:
    items = []
    for row in transcript[-limit:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get('role') or '').strip().lower()
        content = str(row.get('content') or '').strip()
        if not content:
            continue
        label = 'User' if role == 'user' else 'Assistant' if role == 'assistant' else role.title()
        items.append(f"{label}: {content}")
    return items


def save_scene_continuity_snapshot(*, bundle: dict[str, Any], continuity: dict[str, Any], transcript: list[dict[str, Any]], scene_state: dict[str, Any], story_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    bundle_id = str(bundle.get('id') or '').strip()
    if not bundle_id:
        return {'ok': False, 'reason': 'missing_bundle_id'}
    focus_id = ''
    focus = packet.get('entity_focus') if isinstance(packet.get('entity_focus'), dict) else {}
    focus_id = str(focus.get('id') or '').strip()
    project_id = str(packet.get('project_id') or '').strip()
    recent = _compact_turns(transcript)
    if not recent:
        return {'ok': False, 'reason': 'empty_transcript'}
    summary_bits = [str(continuity.get('scene_state_summary') or '').strip(), str(continuity.get('continuity_note') or '').strip()]
    summary_bits.extend(recent)
    summary = '\n'.join(bit for bit in summary_bits if bit).strip()
    scope_token = _scope_token(story_scope, bundle_id=bundle_id)
    scope_fields = {
        'source_snapshot_id': _scope_value(story_scope, 'source_snapshot_id'),
        'canon_snapshot_id': _scope_value(story_scope, 'canon_snapshot_id'),
        'sandbox_id': _scope_value(story_scope, 'sandbox_id'),
        'storyline_id': _scope_value(story_scope, 'storyline_id'),
        'session_id': _scope_value(story_scope, 'session_id'),
        'checkpoint_id': _scope_value(story_scope, 'checkpoint_id'),
        'branch_id': _scope_value(story_scope, 'branch_id'),
        'memory_scope': _scope_value(story_scope, 'memory_scope', 'sandbox') or 'sandbox',
        'promotion_scope': _scope_value(story_scope, 'promotion_scope', 'sandbox_only') or 'sandbox_only',
    }

    saved_fragment = None
    if focus_id:
        saved_fragment = build_memory_fragment_record(
            memory_type='episodic_memory',
            fragment_id=f'mem_scene_{scope_token}_{bundle_id}',
            entity_id=focus_id,
            title=f'Scene continuity · {str(focus.get("label") or focus_id).strip()}',
            canonical_text=summary,
            scene_ready_text='\n'.join(recent[-3:]).strip() or summary,
            source_ref=bundle_id,
            world_id=str(scene_state.get('active_world_id') or '').strip(),
            source_snapshot_id=scope_fields['source_snapshot_id'],
            canon_snapshot_id=scope_fields['canon_snapshot_id'],
            sandbox_id=scope_fields['sandbox_id'],
            storyline_id=scope_fields['storyline_id'],
            session_id=scope_fields['session_id'],
            checkpoint_id=scope_fields['checkpoint_id'],
            branch_id=scope_fields['branch_id'],
            memory_scope=scope_fields['memory_scope'],
            promotion_scope=scope_fields['promotion_scope'],
            relationship_target_ids=list(scene_state.get('focus_stack') or [])[1:4],
            tags=['scene_continuity', str(packet.get('mode') or '').strip() or 'roleplay'],
            salience=0.78,
            emotional_valence='charged',
            extra={'project_id': project_id, 'runtime_bundle_id': bundle_id, 'continuity_mode': str(scene_state.get('continuity_mode') or '').strip(), **scope_fields},
            meta={'status': 'active'},
        )
        save_record(saved_fragment)

    participant_ids = [str(item or '').strip() for item in (scene_state.get('focus_stack') or []) if str(item or '').strip()]
    saved_shared = None
    if len(participant_ids) >= 2:
        saved_shared = build_shared_memory_record(
            shared_memory_id=f'shared_scene_{scope_token}_{bundle_id}',
            participant_ids=participant_ids[:4],
            title=f'Scene continuity · {str(focus.get("label") or participant_ids[0]).strip()}',
            summary='\n'.join(recent[-3:]).strip(),
            source_ref=bundle_id,
            source_snapshot_id=scope_fields['source_snapshot_id'],
            canon_snapshot_id=scope_fields['canon_snapshot_id'],
            sandbox_id=scope_fields['sandbox_id'],
            storyline_id=scope_fields['storyline_id'],
            session_id=scope_fields['session_id'],
            checkpoint_id=scope_fields['checkpoint_id'],
            branch_id=scope_fields['branch_id'],
            memory_scope=scope_fields['memory_scope'],
            promotion_scope=scope_fields['promotion_scope'],
            salience=0.72,
            extra={'project_id': project_id, 'runtime_bundle_id': bundle_id, 'scene_state_summary': str(continuity.get('scene_state_summary') or '').strip(), **scope_fields},
            meta={'status': 'active'},
        )
        save_record(saved_shared)

    return {'ok': True, 'memory_fragment': saved_fragment, 'shared_memory': saved_shared}
