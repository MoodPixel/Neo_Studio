from __future__ import annotations

import hashlib
import re
from typing import Any

from ..contracts.roleplay_v2_memory_records import build_memory_fragment_record, build_shared_memory_record
from .roleplay_v2_sandbox_guard import enforce_sandbox_writeback_scope
from .roleplay_v2_sqlite_store import (
    fetch_rp2_relationship_state_rows,
    persist_rp2_relationship_state,
    persist_rp2_turn_summary,
    upsert_rp2_memory_outputs,
)


_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
_WRITEBACK_PROMOTION_RULES = {
    'episodic_memory': {'persist_threshold': 0.55, 'durable_threshold': 0.80},
    'relationship_belief': {'persist_threshold': 0.62, 'durable_threshold': 0.82},
    'callback_anchor': {'persist_threshold': 0.60, 'durable_threshold': 0.78},
    'thread_state': {'persist_threshold': 0.61, 'durable_threshold': 0.79},
    'shared_memory': {'persist_threshold': 0.58, 'durable_threshold': 0.76},
}

_WRITEBACK_MODE_PROFILES = {
    'roleplay': {
        'key': 'roleplay',
        'focus': 'relationship_callback_pressure',
        'confidence_bias': {'relationship_belief': 0.08, 'callback_anchor': 0.07, 'thread_state': 0.08, 'shared_memory': 0.05, 'episodic_memory': -0.01},
        'threshold_shift': {'relationship_belief': -0.04, 'callback_anchor': -0.03, 'thread_state': -0.03, 'shared_memory': -0.02},
        'salience': {'relationship_belief': 0.78, 'callback_anchor': 0.74, 'thread_state': 0.78, 'shared_memory': 0.74, 'episodic_memory': 0.76},
    },
    'short_story': {
        'key': 'short_story',
        'focus': 'balanced_scene_carry',
        'confidence_bias': {'episodic_memory': 0.03, 'relationship_belief': 0.03, 'callback_anchor': 0.02, 'thread_state': 0.03, 'shared_memory': 0.02},
        'threshold_shift': {'episodic_memory': -0.01, 'relationship_belief': -0.01, 'thread_state': -0.01},
        'salience': {'relationship_belief': 0.74, 'callback_anchor': 0.70, 'thread_state': 0.75, 'shared_memory': 0.72, 'episodic_memory': 0.82},
    },
    'novel': {
        'key': 'novel',
        'focus': 'episodic_relationship_accumulation',
        'confidence_bias': {'episodic_memory': 0.08, 'relationship_belief': 0.07, 'thread_state': 0.06, 'shared_memory': 0.04, 'callback_anchor': 0.02},
        'threshold_shift': {'episodic_memory': -0.04, 'relationship_belief': -0.03, 'thread_state': -0.02, 'shared_memory': -0.01},
        'salience': {'relationship_belief': 0.80, 'callback_anchor': 0.68, 'thread_state': 0.76, 'shared_memory': 0.76, 'episodic_memory': 0.88},
    },
    'cinematic': {
        'key': 'cinematic',
        'focus': 'staging_callback_pressure',
        'confidence_bias': {'episodic_memory': 0.05, 'callback_anchor': 0.08, 'thread_state': 0.08, 'relationship_belief': -0.02, 'shared_memory': 0.0},
        'threshold_shift': {'callback_anchor': -0.04, 'thread_state': -0.04, 'episodic_memory': -0.02, 'relationship_belief': 0.02},
        'salience': {'relationship_belief': 0.66, 'callback_anchor': 0.80, 'thread_state': 0.82, 'shared_memory': 0.68, 'episodic_memory': 0.84},
    },
}


def _clean(value: Any, limit: int = 0) -> str:
    text = str(value or '').strip()
    if limit > 0:
        text = text[:limit]
    return text



def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value or 0.0)))



def _clean_list(values: Any, limit: int = 0) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = _clean(item, limit=limit)
        if text:
            out.append(text)
    return out


def _writeback_scope(story_scope: dict[str, Any] | None, *, bundle: dict[str, Any], project_id: str = '') -> dict[str, str]:
    scope = story_scope if isinstance(story_scope, dict) else {}
    clean_scope = {
        'project_id': _clean(scope.get('project_id') or project_id or bundle.get('project_id')),
        'storyline_id': _clean(scope.get('storyline_id'), limit=120),
        'session_id': _clean(scope.get('session_id'), limit=120),
        'checkpoint_id': _clean(scope.get('checkpoint_id'), limit=120),
        'source_snapshot_id': _clean(scope.get('source_snapshot_id'), limit=120),
        'canon_snapshot_id': _clean(scope.get('canon_snapshot_id'), limit=120),
        'sandbox_id': _clean(scope.get('sandbox_id'), limit=120),
        'branch_id': _clean(scope.get('branch_id'), limit=120),
        'memory_scope': _clean(scope.get('memory_scope') or 'sandbox', limit=80).lower() or 'sandbox',
        'promotion_scope': _clean(scope.get('promotion_scope') or 'sandbox_only', limit=80).lower() or 'sandbox_only',
    }
    if clean_scope['memory_scope'] not in {'source', 'sandbox', 'durable'}:
        clean_scope['memory_scope'] = 'sandbox'
    if clean_scope['promotion_scope'] not in {'sandbox_only', 'shared_world', 'shared_universe', 'durable_project'}:
        clean_scope['promotion_scope'] = 'sandbox_only'
    return enforce_sandbox_writeback_scope(clean_scope)


def _scope_token(scope: dict[str, Any], *, bundle_id: str = '') -> str:
    raw = '|'.join([
        _clean(scope.get('checkpoint_id')),
        _clean(scope.get('branch_id')),
        _clean(scope.get('session_id')),
        _clean(scope.get('sandbox_id')),
        _clean(scope.get('storyline_id')),
        _clean(bundle_id),
    ])
    if not raw.strip('|'):
        raw = _clean(bundle_id) or 'unscoped'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


def _scoped_turn_id(prefix: str, *, scope: dict[str, Any], bundle_id: str = '', turn_index: int = 0, focus_id: str = '', target_id: str = '') -> str:
    token = _scope_token(scope, bundle_id=bundle_id)
    parts = [prefix, token]
    if bundle_id:
        parts.append(_clean(bundle_id, limit=120))
    if turn_index:
        parts.append(str(max(0, int(turn_index or 0))))
    if focus_id:
        parts.append(_clean(focus_id, limit=120))
    if target_id:
        parts.append(_clean(target_id, limit=120))
    return '_'.join(part for part in parts if part)


def _scope_extra(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        'source_snapshot_id': _clean(scope.get('source_snapshot_id')),
        'canon_snapshot_id': _clean(scope.get('canon_snapshot_id')),
        'sandbox_id': _clean(scope.get('sandbox_id')),
        'storyline_id': _clean(scope.get('storyline_id')),
        'session_id': _clean(scope.get('session_id')),
        'checkpoint_id': _clean(scope.get('checkpoint_id')),
        'branch_id': _clean(scope.get('branch_id')),
        'memory_scope': _clean(scope.get('memory_scope') or 'sandbox').lower(),
        'promotion_scope': _clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
    }



def _writeback_mode_profile(output_preset: str = 'roleplay', interaction_mode: str = 'roleplay') -> dict[str, Any]:
    clean_mode = _clean(output_preset).lower() or 'roleplay'
    profile = dict(_WRITEBACK_MODE_PROFILES.get(clean_mode) or _WRITEBACK_MODE_PROFILES['roleplay'])
    profile['key'] = _clean(profile.get('key') or clean_mode or 'roleplay')
    profile['interaction_mode'] = _clean(interaction_mode).lower() or 'roleplay'
    if profile['interaction_mode'] == 'authoring':
        confidence_bias = dict(profile.get('confidence_bias') or {})
        confidence_bias['episodic_memory'] = float(confidence_bias.get('episodic_memory') or 0.0) + 0.02
        confidence_bias['thread_state'] = float(confidence_bias.get('thread_state') or 0.0) + 0.02
        profile['confidence_bias'] = confidence_bias
    return profile


def _mode_tuned_confidence(memory_kind: str, base_confidence: float, mode_profile: dict[str, Any]) -> float:
    bias_map = mode_profile.get('confidence_bias') if isinstance(mode_profile.get('confidence_bias'), dict) else {}
    return _clamp(float(base_confidence or 0.0) + float(bias_map.get(memory_kind) or 0.0), 0.0, 0.97)


def _mode_salience(memory_kind: str, default: float, mode_profile: dict[str, Any]) -> float:
    salience_map = mode_profile.get('salience') if isinstance(mode_profile.get('salience'), dict) else {}
    return float(salience_map.get(memory_kind) or default)


def _recent_turn_lines(transcript: list[dict[str, Any]], limit: int = 4) -> list[str]:
    lines: list[str] = []
    for row in transcript[-limit:]:
        if not isinstance(row, dict):
            continue
        role = _clean(row.get('role')).lower()
        content = _clean(row.get('content'))
        if not content:
            continue
        label = 'You' if role == 'user' else 'Scene' if role == 'assistant' else role.title()
        lines.append(f'{label}: {content}')
    return lines



def _first_sentence(text: Any, limit: int = 220) -> str:
    value = _clean(text)
    if not value:
        return ''
    parts = _SENTENCE_SPLIT_RE.split(value, maxsplit=1)
    return _clean(parts[0], limit=limit)



def _turn_index(transcript: list[dict[str, Any]]) -> int:
    assistant_turns = sum(1 for row in transcript if isinstance(row, dict) and _clean(row.get('role')).lower() == 'assistant' and _clean(row.get('content')))
    return max(1, assistant_turns)



def _relationship_summary(participant_ids: list[str], recent_turns: list[str], continuity: dict[str, Any], reply_text: str) -> str:
    if len(participant_ids) < 2:
        return ''
    labels = ' ↔ '.join(participant_ids[:2])
    beat = _clean(continuity.get('continuity_note') or continuity.get('state_note') or continuity.get('scene_state_summary'), limit=220)
    reply_line = _first_sentence(reply_text, limit=220)
    pieces = [f'Current interaction drift for {labels}.']
    if beat:
        pieces.append(beat)
    if reply_line:
        pieces.append(reply_line)
    elif recent_turns:
        pieces.append(_clean(recent_turns[-1], limit=220))
    return ' '.join(piece for piece in pieces if piece).strip()



def _promotion_decision(memory_kind: str, confidence: float, mode_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = _WRITEBACK_PROMOTION_RULES.get(memory_kind, {'persist_threshold': 0.55, 'durable_threshold': 0.80})
    threshold_shift_map = mode_profile.get('threshold_shift') if isinstance(mode_profile, dict) and isinstance(mode_profile.get('threshold_shift'), dict) else {}
    threshold_shift = float(threshold_shift_map.get(memory_kind) or 0.0)
    persist_threshold = float(rules.get('persist_threshold') or 0.55) + threshold_shift
    durable_threshold = float(rules.get('durable_threshold') or 0.80) + threshold_shift
    clean_confidence = _clamp(confidence)
    if clean_confidence < persist_threshold:
        return {
            'memory_kind': memory_kind,
            'confidence': clean_confidence,
            'persist': False,
            'promotion_status': 'discarded',
            'canon_status': 'provisional',
            'reason': f'below_threshold_{persist_threshold:.2f}',
        }
    promotion_status = 'durable' if clean_confidence >= durable_threshold else 'continuity'
    canon_status = 'approved' if promotion_status == 'durable' else 'provisional'
    return {
        'memory_kind': memory_kind,
        'confidence': clean_confidence,
        'persist': True,
        'promotion_status': promotion_status,
        'canon_status': canon_status,
        'reason': 'meets_threshold',
    }



def _episodic_confidence(*, reply_text: str, user_message: str, recent_turns: list[str], continuity: dict[str, Any], finish_reason: str) -> float:
    score = 0.52
    if _clean(reply_text):
        score += 0.14
    if _clean(user_message):
        score += 0.08
    if len(recent_turns) >= 3:
        score += 0.07
    if _clean(continuity.get('scene_state_summary')):
        score += 0.08
    if _clean(finish_reason):
        score += 0.04
    return _clamp(score, 0.0, 0.95)



def _relationship_confidence(*, participant_ids: list[str], continuity: dict[str, Any], recent_turns: list[str], interaction_mode: str) -> float:
    score = 0.44
    if len(participant_ids) >= 2:
        score += 0.14
    if _clean(continuity.get('continuity_note')) or _clean(continuity.get('state_note')):
        score += 0.10
    if len(recent_turns) >= 3:
        score += 0.06
    if _clean(interaction_mode).lower() == 'roleplay':
        score += 0.06
    return _clamp(score, 0.0, 0.9)



def _callback_confidence(*, scene_state: dict[str, Any], reply_text: str) -> float:
    if _clean(scene_state.get('beat_focus')) or _clean(scene_state.get('part_objective')):
        return 0.78
    if _first_sentence(reply_text):
        return 0.63
    return 0.0



def _thread_state_confidence(*, scene_state: dict[str, Any], continuity: dict[str, Any], user_message: str, reply_text: str) -> float:
    score = 0.0
    if _clean(scene_state.get('beat_focus')) or _clean(scene_state.get('part_objective')):
        score = 0.74
    elif '?' in _clean(user_message) or '?' in _clean(reply_text):
        score = 0.68
    elif _clean(continuity.get('continuity_note')):
        score = 0.62
    return _clamp(score, 0.0, 0.9)



def _thread_state_text(*, focus_label: str, scene_state: dict[str, Any], continuity: dict[str, Any], user_message: str, reply_text: str) -> str:
    anchor = _clean(scene_state.get('beat_focus'), limit=220) or _clean(scene_state.get('part_objective'), limit=220)
    if not anchor and '?' in _clean(user_message):
        anchor = _first_sentence(user_message, limit=220)
    if not anchor and '?' in _clean(reply_text):
        anchor = _first_sentence(reply_text, limit=220)
    if not anchor:
        anchor = _clean(continuity.get('continuity_note'), limit=220)
    if not anchor:
        return ''
    return f'Unresolved thread for {focus_label}: {anchor}'



def _shared_confidence(*, participant_ids: list[str], recent_turns: list[str], continuity: dict[str, Any]) -> float:
    score = 0.42
    if len(participant_ids) >= 2:
        score += 0.15
    if len(recent_turns) >= 3:
        score += 0.07
    if _clean(continuity.get('scene_state_summary')):
        score += 0.08
    if _clean(continuity.get('continuity_note')):
        score += 0.06
    return _clamp(score, 0.0, 0.88)



def _relationship_drift_metrics(*, user_message: str, reply_text: str, continuity: dict[str, Any]) -> tuple[float, float, float]:
    text = f"{_clean(user_message).lower()} {_clean(reply_text).lower()} {_clean(continuity.get('continuity_note')).lower()}"
    trust_delta = 0.0
    tension_delta = 0.0
    positive_tokens = ['trust', 'safe', 'gentle', 'sorry', 'promise', 'stay', 'together', 'soft']
    negative_tokens = ['lie', 'lied', 'anger', 'angry', 'threat', 'leave', 'fear', 'hurt', 'cold']
    if any(token in text for token in positive_tokens):
        trust_delta += 0.06
    if any(token in text for token in negative_tokens):
        tension_delta += 0.08
    if '?' in _clean(user_message) or '?' in _clean(reply_text):
        tension_delta += 0.04
    if _clean(continuity.get('scene_state_summary')):
        trust_delta += 0.02
    drift_score = _clamp(abs(trust_delta) + abs(tension_delta), 0.0, 0.3)
    return trust_delta, tension_delta, drift_score



def _next_relationship_state(*, focus_id: str, target_id: str, project_id: str, bundle_id: str, source_ref: str, focus_label: str, target_label: str, summary: str, user_message: str, reply_text: str, continuity: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    latest_rows = fetch_rp2_relationship_state_rows(
        entity_id=focus_id,
        project_id=project_id,
        limit=12,
        source_snapshot_id=_clean(scope.get('source_snapshot_id')),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
        sandbox_id=_clean(scope.get('sandbox_id')),
        storyline_id=_clean(scope.get('storyline_id')),
        session_id=_clean(scope.get('session_id')),
        checkpoint_id=_clean(scope.get('checkpoint_id')),
        branch_id=_clean(scope.get('branch_id')),
        memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
        promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
    ).get('rows') or []
    prior = next((row for row in latest_rows if _clean(row.get('target_entity_id')) == target_id or _clean(row.get('source_entity_id')) == target_id), {})
    prior_trust = float(prior.get('trust_level') or 0.5)
    prior_tension = float(prior.get('tension_level') or 0.0)
    trust_delta, tension_delta, drift_score = _relationship_drift_metrics(user_message=user_message, reply_text=reply_text, continuity=continuity)
    trust_level = _clamp(prior_trust + trust_delta, 0.0, 1.0)
    tension_level = _clamp(prior_tension + tension_delta, 0.0, 1.0)
    return {
        'relationship_state_id': _scoped_turn_id('relstate', scope=scope, bundle_id=bundle_id, focus_id=focus_id, target_id=target_id),
        'source_entity_id': focus_id,
        'target_entity_id': target_id,
        'project_id': project_id,
        'bundle_id': bundle_id,
        'source_ref': source_ref,
        'relationship_label': f'{focus_label} ↔ {target_label}' if target_label else f'{focus_label} carry-forward',
        'summary': summary,
        'trust_level': trust_level,
        'tension_level': tension_level,
        'drift_score': drift_score,
        'carry_forward': True,
        'source_snapshot_id': _clean(scope.get('source_snapshot_id')),
        'canon_snapshot_id': _clean(scope.get('canon_snapshot_id')),
        'sandbox_id': _clean(scope.get('sandbox_id')),
        'storyline_id': _clean(scope.get('storyline_id')),
        'session_id': _clean(scope.get('session_id')),
        'checkpoint_id': _clean(scope.get('checkpoint_id')),
        'branch_id': _clean(scope.get('branch_id')),
        'memory_scope': _clean(scope.get('memory_scope') or 'sandbox').lower(),
        'promotion_scope': _clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
        'state_payload': {
            'prior_trust_level': prior_trust,
            'prior_tension_level': prior_tension,
            'trust_delta': trust_delta,
            'tension_delta': tension_delta,
            'drift_score': drift_score,
            'scope_token': _scope_token(scope, bundle_id=bundle_id),
        },
    }



def writeback_scene_turn(
    *,
    bundle: dict[str, Any],
    transcript: list[dict[str, Any]],
    scene_state: dict[str, Any],
    continuity: dict[str, Any],
    user_message: str,
    reply_text: str,
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    finish_reason: str = '',
    story_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    focus = packet.get('entity_focus') if isinstance(packet.get('entity_focus'), dict) else {}
    bundle_id = _clean(bundle.get('id'))
    focus_id = _clean(focus.get('id'))
    focus_label = _clean(focus.get('label') or focus_id or 'focus entity', limit=120)
    project_id = _clean((story_scope or {}).get('project_id') or packet.get('project_id') or bundle.get('project_id'))
    scope = _writeback_scope(story_scope, bundle=bundle, project_id=project_id)
    turn_index = _turn_index(transcript)
    source_ref = f'{bundle_id}:turn:{turn_index}' if bundle_id else f'turn:{turn_index}'
    recent_turns = _recent_turn_lines(transcript)
    summary_bits = [
        _clean(continuity.get('scene_state_summary'), limit=500),
        _clean(continuity.get('continuity_note'), limit=320),
        _clean(user_message, limit=260),
        _first_sentence(reply_text, limit=320),
    ]
    summary = ' | '.join(bit for bit in summary_bits if bit).strip() or _clean(reply_text, limit=320)

    participant_ids = _clean_list(scene_state.get('focus_stack') or [], limit=120)
    anchor_text = _clean(scene_state.get('beat_focus'), limit=240) or _clean(scene_state.get('part_objective'), limit=240) or _first_sentence(reply_text, limit=240)
    relationship_summary = _relationship_summary(participant_ids, recent_turns, continuity, reply_text)
    thread_text = _thread_state_text(focus_label=focus_label, scene_state=scene_state, continuity=continuity, user_message=user_message, reply_text=reply_text)
    mode_profile = _writeback_mode_profile(output_preset=output_preset, interaction_mode=interaction_mode)

    promotion_report = {
        'episodic_memory': _promotion_decision('episodic_memory', _mode_tuned_confidence('episodic_memory', _episodic_confidence(reply_text=reply_text, user_message=user_message, recent_turns=recent_turns, continuity=continuity, finish_reason=finish_reason), mode_profile), mode_profile),
        'relationship_belief': _promotion_decision('relationship_belief', _mode_tuned_confidence('relationship_belief', _relationship_confidence(participant_ids=participant_ids, continuity=continuity, recent_turns=recent_turns, interaction_mode=interaction_mode), mode_profile), mode_profile) if relationship_summary else {**_promotion_decision('relationship_belief', 0.0, mode_profile), 'reason': 'no_relationship_context'},
        'callback_anchor': _promotion_decision('callback_anchor', _mode_tuned_confidence('callback_anchor', _callback_confidence(scene_state=scene_state, reply_text=reply_text), mode_profile), mode_profile) if anchor_text else {**_promotion_decision('callback_anchor', 0.0, mode_profile), 'reason': 'no_anchor_text'},
        'thread_state': _promotion_decision('thread_state', _mode_tuned_confidence('thread_state', _thread_state_confidence(scene_state=scene_state, continuity=continuity, user_message=user_message, reply_text=reply_text), mode_profile), mode_profile) if thread_text else {**_promotion_decision('thread_state', 0.0, mode_profile), 'reason': 'no_unresolved_thread'},
        'shared_memory': _promotion_decision('shared_memory', _mode_tuned_confidence('shared_memory', _shared_confidence(participant_ids=participant_ids, recent_turns=recent_turns, continuity=continuity), mode_profile), mode_profile) if len(participant_ids) >= 2 else {**_promotion_decision('shared_memory', 0.0, mode_profile), 'reason': 'insufficient_participants'},
    }

    summary_payload = {
        'bundle_id': bundle_id,
        'project_id': project_id,
        'entity_id': focus_id,
        'mode': _clean(output_preset) or 'roleplay',
        'interaction_mode': _clean(interaction_mode) or 'roleplay',
        'finish_reason': _clean(finish_reason),
        'recent_turns': recent_turns,
        'continuity': continuity if isinstance(continuity, dict) else {},
        'scene_state': scene_state if isinstance(scene_state, dict) else {},
        'mode_profile': mode_profile,
        'promotion_report': promotion_report,
        'story_scope': dict(scope),
    }
    turn_summary = persist_rp2_turn_summary(
        turn_summary_id=_scoped_turn_id('turnsum', scope=scope, bundle_id=bundle_id, turn_index=turn_index),
        session_id=_clean(scope.get('session_id')),
        checkpoint_id=_clean(scope.get('checkpoint_id')),
        bundle_id=bundle_id,
        project_id=project_id,
        entity_id=focus_id,
        mode=_clean(output_preset) or 'roleplay',
        source_ref=source_ref,
        turn_index=turn_index,
        summary=summary,
        summary_payload=summary_payload,
        source_snapshot_id=_clean(scope.get('source_snapshot_id')),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
        sandbox_id=_clean(scope.get('sandbox_id')),
        storyline_id=_clean(scope.get('storyline_id')),
        branch_id=_clean(scope.get('branch_id')),
        memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
    )

    extra_base = {
        'project_id': project_id,
        'builder_record_id': focus_id,
        'canon_id': focus_id,
        **_scope_extra(scope),
    }
    fragments: list[dict[str, Any]] = []
    shared_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    episodic_decision = promotion_report['episodic_memory']
    episodic = build_memory_fragment_record(
        memory_type='episodic_memory',
        fragment_id=_scoped_turn_id('memturn', scope=scope, bundle_id=bundle_id, turn_index=turn_index, focus_id=focus_id),
        entity_id=focus_id,
        title=f'Turn continuity · {focus_label} · {turn_index}',
        canonical_text='\n'.join(recent_turns).strip() or summary,
        scene_ready_text=_clean(reply_text, limit=4000) or summary,
        source_ref=source_ref,
        world_id=_clean(scene_state.get('active_world_id')),
        source_snapshot_id=_clean(scope.get('source_snapshot_id')),
        canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
        sandbox_id=_clean(scope.get('sandbox_id')),
        storyline_id=_clean(scope.get('storyline_id')),
        session_id=_clean(scope.get('session_id')),
        checkpoint_id=_clean(scope.get('checkpoint_id')),
        branch_id=_clean(scope.get('branch_id')),
        memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
        promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
        relationship_target_ids=participant_ids[1:4],
        tags=['turn_writeback', 'episodic_memory', _clean(output_preset) or 'roleplay', episodic_decision['promotion_status'], _clean(scope.get('memory_scope') or 'sandbox').lower()],
        salience=_mode_salience('episodic_memory', 0.8, mode_profile),
        emotional_valence='charged',
        canon_status=episodic_decision['canon_status'],
        confidence=episodic_decision['confidence'],
        extra={**extra_base, 'turn_index': turn_index, 'writeback_kind': 'scene_turn', 'promotion_status': episodic_decision['promotion_status']},
        meta={'status': episodic_decision['promotion_status']},
    )
    if episodic_decision['persist']:
        fragments.append(episodic)
    else:
        skipped.append({'memory_kind': 'episodic_memory', 'reason': episodic_decision['reason']})

    relationship_fragment = None
    relationship_decision = promotion_report['relationship_belief']
    if relationship_summary:
        relationship_fragment = build_memory_fragment_record(
            memory_type='relationship_belief',
            fragment_id=_scoped_turn_id('relturn', scope=scope, bundle_id=bundle_id, turn_index=turn_index, focus_id=focus_id),
            entity_id=focus_id,
            title=f'Relationship drift · {focus_label}',
            canonical_text=relationship_summary,
            scene_ready_text=relationship_summary,
            source_ref=source_ref,
            source_snapshot_id=_clean(scope.get('source_snapshot_id')),
            canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
            sandbox_id=_clean(scope.get('sandbox_id')),
            storyline_id=_clean(scope.get('storyline_id')),
            session_id=_clean(scope.get('session_id')),
            checkpoint_id=_clean(scope.get('checkpoint_id')),
            branch_id=_clean(scope.get('branch_id')),
            memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
            promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
            relationship_target_ids=participant_ids[1:3],
            tags=['turn_writeback', 'relationship_belief', _clean(output_preset) or 'roleplay', relationship_decision['promotion_status'], _clean(scope.get('memory_scope') or 'sandbox').lower()],
            salience=_mode_salience('relationship_belief', 0.72, mode_profile),
            emotional_valence='charged',
            canon_status=relationship_decision['canon_status'],
            confidence=relationship_decision['confidence'],
            extra={**extra_base, 'turn_index': turn_index, 'writeback_kind': 'relationship_drift', 'promotion_status': relationship_decision['promotion_status']},
            meta={'status': relationship_decision['promotion_status']},
        )
        if relationship_decision['persist']:
            fragments.append(relationship_fragment)
        else:
            skipped.append({'memory_kind': 'relationship_belief', 'reason': relationship_decision['reason']})

    relationship_state = {}
    if relationship_fragment and participant_ids[1:2]:
        target_id = _clean(participant_ids[1])
        relationship_state = _next_relationship_state(
            focus_id=focus_id,
            target_id=target_id,
            project_id=project_id,
            bundle_id=bundle_id,
            source_ref=source_ref,
            focus_label=focus_label,
            target_label=target_id,
            summary=relationship_summary,
            user_message=user_message,
            reply_text=reply_text,
            continuity=continuity,
            scope=scope,
        )
        persist_rp2_relationship_state(**relationship_state)

    thread_fragment = None
    thread_decision = promotion_report['thread_state']
    if thread_text:
        thread_fragment = build_memory_fragment_record(
            memory_type='thread_state',
            fragment_id=_scoped_turn_id('threadturn', scope=scope, bundle_id=bundle_id, turn_index=turn_index, focus_id=focus_id),
            entity_id=focus_id,
            title=f'Unresolved thread · {focus_label}',
            canonical_text=thread_text,
            scene_ready_text=thread_text,
            source_ref=source_ref,
            source_snapshot_id=_clean(scope.get('source_snapshot_id')),
            canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
            sandbox_id=_clean(scope.get('sandbox_id')),
            storyline_id=_clean(scope.get('storyline_id')),
            session_id=_clean(scope.get('session_id')),
            checkpoint_id=_clean(scope.get('checkpoint_id')),
            branch_id=_clean(scope.get('branch_id')),
            memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
            promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
            tags=['turn_writeback', 'thread_state', 'carry_forward', _clean(output_preset) or 'roleplay', thread_decision['promotion_status'], _clean(scope.get('memory_scope') or 'sandbox').lower()],
            salience=_mode_salience('thread_state', 0.74, mode_profile),
            emotional_valence='charged',
            canon_status=thread_decision['canon_status'],
            confidence=thread_decision['confidence'],
            extra={**extra_base, 'turn_index': turn_index, 'writeback_kind': 'unresolved_thread', 'promotion_status': thread_decision['promotion_status'], 'carry_forward': True, 'unresolved': True},
            meta={'status': thread_decision['promotion_status']},
        )
        if thread_decision['persist']:
            fragments.append(thread_fragment)
        else:
            skipped.append({'memory_kind': 'thread_state', 'reason': thread_decision['reason']})

    shared_decision = promotion_report['shared_memory']
    shared_row = None
    if len(participant_ids) >= 2:
        shared_row = build_shared_memory_record(
            shared_memory_id=_scoped_turn_id('sharedturn', scope=scope, bundle_id=bundle_id, turn_index=turn_index, focus_id=focus_id),
            participant_ids=participant_ids[:4],
            title=f'Shared turn memory · {focus_label}',
            summary='\n'.join(recent_turns[-3:]).strip() or summary,
            source_ref=source_ref,
            source_snapshot_id=_clean(scope.get('source_snapshot_id')),
            canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
            sandbox_id=_clean(scope.get('sandbox_id')),
            storyline_id=_clean(scope.get('storyline_id')),
            session_id=_clean(scope.get('session_id')),
            checkpoint_id=_clean(scope.get('checkpoint_id')),
            branch_id=_clean(scope.get('branch_id')),
            memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
            promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
            salience=_mode_salience('shared_memory', 0.7, mode_profile),
            extra={**extra_base, 'turn_index': turn_index, 'writeback_kind': 'shared_turn', 'promotion_status': shared_decision['promotion_status'], 'promotion_confidence': shared_decision['confidence']},
            meta={'status': shared_decision['promotion_status']},
        )
        if shared_decision['persist']:
            shared_rows.append(shared_row)
        else:
            skipped.append({'memory_kind': 'shared_memory', 'reason': shared_decision['reason']})

    callback_fragment = None
    callback_decision = promotion_report['callback_anchor']
    if anchor_text:
        callback_fragment = build_memory_fragment_record(
            memory_type='callback_anchor',
            fragment_id=_scoped_turn_id('cbturn', scope=scope, bundle_id=bundle_id, turn_index=turn_index, focus_id=focus_id),
            entity_id=focus_id,
            title=f'Callback anchor · {focus_label}',
            canonical_text=anchor_text,
            scene_ready_text=anchor_text,
            source_ref=source_ref,
            source_snapshot_id=_clean(scope.get('source_snapshot_id')),
            canon_snapshot_id=_clean(scope.get('canon_snapshot_id')),
            sandbox_id=_clean(scope.get('sandbox_id')),
            storyline_id=_clean(scope.get('storyline_id')),
            session_id=_clean(scope.get('session_id')),
            checkpoint_id=_clean(scope.get('checkpoint_id')),
            branch_id=_clean(scope.get('branch_id')),
            memory_scope=_clean(scope.get('memory_scope') or 'sandbox').lower(),
            promotion_scope=_clean(scope.get('promotion_scope') or 'sandbox_only').lower(),
            tags=['turn_writeback', 'callback_anchor', _clean(output_preset) or 'roleplay', callback_decision['promotion_status'], _clean(scope.get('memory_scope') or 'sandbox').lower()],
            salience=_mode_salience('callback_anchor', 0.68, mode_profile),
            emotional_valence='charged',
            canon_status=callback_decision['canon_status'],
            confidence=callback_decision['confidence'],
            extra={**extra_base, 'turn_index': turn_index, 'writeback_kind': 'callback_anchor', 'promotion_status': callback_decision['promotion_status'], 'carry_forward': bool(thread_text)},
            meta={'status': callback_decision['promotion_status']},
        )
        if callback_decision['persist']:
            fragments.append(callback_fragment)
        else:
            skipped.append({'memory_kind': 'callback_anchor', 'reason': callback_decision['reason']})

    sqlite_sync = upsert_rp2_memory_outputs(
        memory_fragments=fragments,
        shared_memories=shared_rows,
        builder_record_id=focus_id,
        canon_id=focus_id,
        source_ref=source_ref,
        prune_existing=False,
    )
    return {
        'ok': True,
        'turn_index': turn_index,
        'source_ref': source_ref,
        'writeback_scope': dict(scope),
        'mode_profile': mode_profile,
        'promotion_report': promotion_report,
        'skipped': skipped,
        'turn_summary': {
            'id': _clean(turn_summary.get('turn_summary_id')),
            'summary': _clean(turn_summary.get('summary')),
        },
        'episodic_memory': {
            'id': _clean(episodic.get('id')),
            'title': _clean(episodic.get('title')),
            'summary': _clean(episodic.get('scene_ready_text') or episodic.get('canonical_text'), limit=320),
            'promotion_status': episodic_decision['promotion_status'],
            'confidence': episodic_decision['confidence'],
            'persisted': episodic_decision['persist'],
        },
        'relationship_drift': {
            'id': _clean((relationship_fragment or {}).get('id')),
            'title': _clean((relationship_fragment or {}).get('title')),
            'summary': _clean((relationship_fragment or {}).get('scene_ready_text') or (relationship_fragment or {}).get('canonical_text'), limit=320),
            'promotion_status': relationship_decision['promotion_status'],
            'confidence': relationship_decision['confidence'],
            'persisted': relationship_decision['persist'],
        } if relationship_fragment or relationship_summary else {},
        'relationship_state': {
            'id': _clean(relationship_state.get('relationship_state_id')),
            'label': _clean(relationship_state.get('relationship_label')),
            'summary': _clean(relationship_state.get('summary'), limit=320),
            'trust_level': float(relationship_state.get('trust_level') or 0.0),
            'tension_level': float(relationship_state.get('tension_level') or 0.0),
            'drift_score': float(relationship_state.get('drift_score') or 0.0),
        } if relationship_state else {},
        'callback_anchor': {
            'id': _clean((callback_fragment or {}).get('id')),
            'label': _clean((callback_fragment or {}).get('title')),
            'text': _clean((callback_fragment or {}).get('scene_ready_text') or (callback_fragment or {}).get('canonical_text'), limit=240),
            'promotion_status': callback_decision['promotion_status'],
            'confidence': callback_decision['confidence'],
            'persisted': callback_decision['persist'],
        } if callback_fragment or anchor_text else {},
        'unresolved_thread': {
            'id': _clean((thread_fragment or {}).get('id')),
            'title': _clean((thread_fragment or {}).get('title')),
            'summary': _clean((thread_fragment or {}).get('scene_ready_text') or (thread_fragment or {}).get('canonical_text'), limit=280),
            'promotion_status': thread_decision['promotion_status'],
            'confidence': thread_decision['confidence'],
            'persisted': thread_decision['persist'],
        } if thread_fragment or thread_text else {},
        'shared_memory': {
            'id': _clean((shared_row or {}).get('id')),
            'title': _clean((shared_row or {}).get('title')),
            'summary': _clean((shared_row or {}).get('summary'), limit=320),
            'promotion_status': shared_decision['promotion_status'],
            'confidence': shared_decision['confidence'],
            'persisted': shared_decision['persist'],
        } if shared_row else {},
        'sqlite_sync': sqlite_sync,
    }
