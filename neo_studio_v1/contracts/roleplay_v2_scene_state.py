from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .roleplay_v2_mode_model import normalize_mode_model

ROLEPLAY_V2_SCENE_STATE_SCHEMA_VERSION = 1
ROLEPLAY_V2_NARRATOR_POSTURES = {
    'partner_focus',
    'duet_first_person',
    'gm_facilitated',
    'omniscient_narration',
}
ROLEPLAY_V2_CONTINUITY_MODES = {
    'runtime_anchored',
    'session_persistent',
    'fresh_scene',
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


def build_scene_state(
    *,
    active_world_id: str = '',
    active_scenario_id: str = '',
    cast_entity_ids: list[str] | None = None,
    focus_stack: list[str] | None = None,
    narrator_posture: str = 'partner_focus',
    continuity_mode: str = 'runtime_anchored',
    runtime_bundle_id: str = '',
    runtime_bundle_inputs: dict[str, Any] | None = None,
    memory_source_ids: list[str] | None = None,
    canon_guard_source_ids: list[str] | None = None,
    source_container_id: str = '',
    scene_goal: str = '',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    scene_notes: str = '',
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_posture = _clean(narrator_posture or 'partner_focus', lower=True, limit=80)
    if clean_posture not in ROLEPLAY_V2_NARRATOR_POSTURES:
        clean_posture = 'partner_focus'
    clean_continuity = _clean(continuity_mode or 'runtime_anchored', lower=True, limit=80)
    if clean_continuity not in ROLEPLAY_V2_CONTINUITY_MODES:
        clean_continuity = 'runtime_anchored'
    mode_model = normalize_mode_model(output_preset=output_preset, interaction_mode=interaction_mode, prefer='output')
    meta_row = _json_dict(meta)
    created_at = _clean(meta_row.get('created_at')) or _now_iso()
    updated_at = _clean(meta_row.get('updated_at')) or created_at
    return {
        'schema_version': ROLEPLAY_V2_SCENE_STATE_SCHEMA_VERSION,
        'record_type': 'roleplay_v2_scene_state',
        'active_world_id': _clean(active_world_id, limit=120),
        'active_scenario_id': _clean(active_scenario_id, limit=120),
        'cast_entity_ids': _clean_list(cast_entity_ids or [], limit=120),
        'focus_stack': _clean_list(focus_stack or [], limit=120),
        'narrator_posture': clean_posture,
        'continuity_mode': clean_continuity,
        'runtime_bundle_id': _clean(runtime_bundle_id, limit=120),
        'runtime_bundle_inputs': _json_dict(runtime_bundle_inputs),
        'memory_source_ids': _clean_list(memory_source_ids or [], limit=120),
        'canon_guard_source_ids': _clean_list(canon_guard_source_ids or [], limit=120),
        'source_container_id': _clean(source_container_id, limit=120),
        'scene_goal': _clean(scene_goal, limit=400),
        'output_preset': _clean(mode_model.get('output_preset') or 'roleplay', lower=True, limit=80),
        'interaction_mode': _clean(mode_model.get('interaction_mode') or 'roleplay', lower=True, limit=80),
        'scene_notes': _clean(scene_notes, limit=4000),
        'contract_rules': {
            'cast_is_explicit': True,
            'focus_is_ranked': True,
            'reverse_links_are_derived': True,
            'memory_sources_are_explicit': True,
            'canon_guards_are_explicit': True,
        },
        'meta': {
            'created_at': created_at,
            'updated_at': updated_at,
            'status': _clean(meta_row.get('status') or 'active', lower=True, limit=40),
        },
    }


def normalize_scene_state(scene_state: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(scene_state or {}), **overrides}
    return build_scene_state(
        active_world_id=raw.get('active_world_id') or '',
        active_scenario_id=raw.get('active_scenario_id') or '',
        cast_entity_ids=raw.get('cast_entity_ids') or [],
        focus_stack=raw.get('focus_stack') or [],
        narrator_posture=raw.get('narrator_posture') or 'partner_focus',
        continuity_mode=raw.get('continuity_mode') or 'runtime_anchored',
        runtime_bundle_id=raw.get('runtime_bundle_id') or '',
        runtime_bundle_inputs=raw.get('runtime_bundle_inputs'),
        memory_source_ids=raw.get('memory_source_ids') or [],
        canon_guard_source_ids=raw.get('canon_guard_source_ids') or [],
        source_container_id=raw.get('source_container_id') or '',
        scene_goal=raw.get('scene_goal') or '',
        output_preset=raw.get('output_preset') or 'roleplay',
        interaction_mode=raw.get('interaction_mode') or 'roleplay',
        scene_notes=raw.get('scene_notes') or '',
        meta=raw.get('meta'),
    )


def scene_state_summary(scene_state: dict[str, Any] | None = None) -> dict[str, Any]:
    row = normalize_scene_state(scene_state or {})
    lines = [
        f"Posture · {row['narrator_posture']}",
        f"Continuity · {row['continuity_mode']}",
        f"Cast · {len(row['cast_entity_ids'])}",
        f"Focus stack · {', '.join(row['focus_stack']) if row['focus_stack'] else 'none'}",
    ]
    if row['active_world_id']:
        lines.append(f"World · {row['active_world_id']}")
    if row['active_scenario_id']:
        lines.append(f"Scenario · {row['active_scenario_id']}")
    if row['scene_goal']:
        lines.append(f"Goal · {row['scene_goal']}")
    if row['runtime_bundle_id']:
        lines.append(f"Runtime bundle · {row['runtime_bundle_id']}")
    if row['memory_source_ids']:
        lines.append(f"Memory sources · {len(row['memory_source_ids'])}")
    if row['canon_guard_source_ids']:
        lines.append(f"Canon guards · {len(row['canon_guard_source_ids'])}")
    return {
        'scene_state': row,
        'line_count': len(lines),
        'summary_text': '\n'.join(lines),
    }
