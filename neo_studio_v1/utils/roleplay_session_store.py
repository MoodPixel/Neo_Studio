from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts.memory_records import build_memory_manifest
from .roleplay_foundation import (
    ROLEPLAY_PARTS_DIR,
    ROLEPLAY_SESSIONS_DIR,
    now_iso,
    session_template,
    story_part_template,
)
from .roleplay_story_store import _story_path, get_story_record, normalize_linked_context, linked_context_summary
from .storage_io import atomic_write_json, read_json_object
from .memory_service.roleplay_adapter import sync_roleplay_part_summary, sync_roleplay_session_snapshot, sync_roleplay_story

LATEST_SESSION_NAME = 'latest_session.json'


PROGRESSION_DEFAULTS: dict[str, Any] = {
    'chapter_index': 1,
    'chapter_label': '',
    'part_index': 1,
    'beat_focus': '',
    'active_pov': '',
    'active_location': '',
    'active_cast_focus': '',
    'part_objective': '',
    'tension_level': 'medium',
    'pacing_target': 'steady',
}


def normalize_progression(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    clean = dict(PROGRESSION_DEFAULTS)
    try:
        clean['chapter_index'] = max(1, int(data.get('chapter_index') or 1))
    except Exception:
        clean['chapter_index'] = 1
    try:
        clean['part_index'] = max(1, int(data.get('part_index') or 1))
    except Exception:
        clean['part_index'] = 1
    for key in ['chapter_label', 'beat_focus', 'active_pov', 'active_location', 'active_cast_focus', 'part_objective']:
        clean[key] = str(data.get(key) or '').strip()
    tension = str(data.get('tension_level') or 'medium').strip().lower()
    clean['tension_level'] = tension if tension in {'low', 'simmering', 'medium', 'high', 'climax'} else 'medium'
    pacing = str(data.get('pacing_target') or 'steady').strip().lower()
    clean['pacing_target'] = pacing if pacing in {'slow_burn', 'steady', 'urgent', 'lull', 'aftermath'} else 'steady'
    return clean


def progression_summary(raw: Any) -> str:
    data = normalize_progression(raw)
    bits: list[str] = []
    chapter = f"Chapter {data['chapter_index']}"
    if data['chapter_label']:
        chapter += f" — {data['chapter_label']}"
    bits.append(chapter)
    bits.append(f"Part {data['part_index']}")
    if data['beat_focus']:
        bits.append(f"Beat: {data['beat_focus']}")
    if data['active_pov']:
        bits.append(f"POV: {data['active_pov']}")
    if data['active_location']:
        bits.append(f"Location: {data['active_location']}")
    if data['active_cast_focus']:
        bits.append(f"Cast: {data['active_cast_focus']}")
    if data['part_objective']:
        bits.append(f"Objective: {data['part_objective']}")
    bits.append(f"Tension: {data['tension_level']}")
    bits.append(f"Pacing: {data['pacing_target']}")
    return ' | '.join(bits)


def normalize_branch_options(raw: Any) -> list[dict[str, str]]:
    items = []
    for idx, item in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        items.append({
            'id': str(item.get('id') or f'opt_{idx}').strip() or f'opt_{idx}',
            'label': str(item.get('label') or f'Option {idx}').strip() or f'Option {idx}',
            'text': text,
        })
    return items


def normalize_branch_choice_history(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        rows.append({
            'assistant_turn_index': int(item.get('assistant_turn_index') or 0),
            'choice_id': str(item.get('choice_id') or '').strip(),
            'label': str(item.get('label') or '').strip(),
            'text': text,
            'source': str(item.get('source') or 'generated').strip() or 'generated',
        })
    return rows


def normalize_branching_state(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    story_mode = str(data.get('story_mode') or '').strip().lower()
    story_mode = 'branching' if story_mode == 'branching' else 'linear'
    try:
        option_count = max(2, min(6, int(data.get('option_count') or 3)))
    except Exception:
        option_count = 3
    return {
        'story_mode': story_mode,
        'option_count': option_count,
        'allow_custom_option': bool(data.get('allow_custom_option', True)),
        'latest_options': normalize_branch_options(data.get('latest_options')),
        'choice_history': normalize_branch_choice_history(data.get('choice_history')),
    }


def _part_path(part_id: str) -> Path:
    return ROLEPLAY_PARTS_DIR / f'{part_id}.json'


def _session_path(name: str = LATEST_SESSION_NAME) -> Path:
    return ROLEPLAY_SESSIONS_DIR / name


def _read_json(path: Path) -> dict[str, Any] | None:
    return read_json_object(path, None)


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(path, payload)
    return payload


def _normalize_messages(messages: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for entry in messages if isinstance(messages, list) else []:
        if not isinstance(entry, dict):
            continue
        role = 'assistant' if str(entry.get('role') or '').strip() == 'assistant' else 'user'
        content = str(entry.get('content') or '').strip()
        if content:
            items.append({'role': role, 'content': content})
    return items


def _scene_text(messages: list[dict[str, str]], user_name: str, partner_name: str) -> str:
    user_label = str(user_name or '').strip() or 'You'
    partner_label = str(partner_name or '').strip() or 'Scene partner'
    lines = []
    for entry in messages:
        label = partner_label if entry.get('role') == 'assistant' else user_label
        lines.append(f'{label}: {entry.get("content", "")}')
    return '\n\n'.join(lines).strip()


def _transcript_from_scene_text(scene_text: str, user_name: str, partner_name: str) -> list[dict[str, str]]:
    user_label = f"{str(user_name or '').strip() or 'You'}:"
    partner_label = f"{str(partner_name or '').strip() or 'Scene partner'}:"
    items: list[dict[str, str]] = []
    for block in [part.strip() for part in str(scene_text or '').split('\n\n') if part.strip()]:
        if block.startswith(user_label):
            items.append({'role': 'user', 'content': block[len(user_label):].strip()})
        elif block.startswith(partner_label):
            items.append({'role': 'assistant', 'content': block[len(partner_label):].strip()})
        else:
            items.append({'role': 'assistant', 'content': block})
    return _normalize_messages(items)


def get_part_record(part_id: str) -> dict[str, Any] | None:
    return _read_json(_part_path(str(part_id or '').strip()))


def list_story_parts(story_id: str) -> list[dict[str, Any]]:
    story = get_story_record(story_id)
    if not story:
        return []
    parts: list[dict[str, Any]] = []
    for idx, part_id in enumerate(story.get('part_ids') or [], start=1):
        rec = get_part_record(str(part_id or '').strip())
        if not rec:
            continue
        transcript = _normalize_messages(rec.get('transcript'))
        branch = rec.get('branch') or {}
        branching = normalize_branching_state(rec.get('branching'))
        parts.append({
            'id': rec.get('id', ''),
            'story_id': rec.get('story_id', ''),
            'title': rec.get('title', '') or f'Part {idx}',
            'order_index': int(rec.get('order_index') or idx),
            'summary': rec.get('summary', ''),
            'updated_at': (rec.get('meta') or {}).get('updated_at', ''),
            'status': (rec.get('meta') or {}).get('status', 'draft'),
            'turn_count': len(transcript),
            'branch_label': branch.get('branch_label', ''),
            'parent_part_id': branch.get('parent_part_id', ''),
            'linked_context_counts': {k: len(v) for k, v in normalize_linked_context(rec.get('linked_context')).items() if v},
            'progression': normalize_progression(rec.get('progression')),
            'progression_summary': progression_summary(rec.get('progression')),
            'story_mode': str(branching.get('story_mode') or 'linear'),
            'latest_options_count': len(branching.get('latest_options') or []),
            'choice_history_count': len(branching.get('choice_history') or []),
        })
    parts.sort(key=lambda item: (int(item.get('order_index') or 0), str(item.get('updated_at') or '')))
    return parts




def build_story_branch_map(story_id: str) -> dict[str, Any]:
    story = get_story_record(story_id)
    if not story:
        raise ValueError('Story not found.')
    listed_parts = list_story_parts(story_id)
    lookup = {str(item.get('id') or '').strip(): item for item in listed_parts if str(item.get('id') or '').strip()}
    child_map: dict[str, list[str]] = {}
    for item in listed_parts:
        parent_id = str(item.get('parent_part_id') or '').strip()
        if parent_id:
            child_map.setdefault(parent_id, []).append(str(item.get('id') or '').strip())

    def compute_depth(part_id: str) -> int:
        depth = 0
        seen: set[str] = set()
        current = str(lookup.get(part_id, {}).get('parent_part_id') or '').strip()
        while current and current in lookup and current not in seen:
            depth += 1
            seen.add(current)
            current = str(lookup.get(current, {}).get('parent_part_id') or '').strip()
        return depth

    nodes: list[dict[str, Any]] = []
    for item in listed_parts:
        rec = get_part_record(str(item.get('id') or '').strip()) or {}
        branching = normalize_branching_state(rec.get('branching'))
        node_id = str(item.get('id') or '').strip()
        parent_id = str(item.get('parent_part_id') or '').strip()
        children = child_map.get(node_id, [])
        nodes.append({
            **item,
            'depth': compute_depth(node_id),
            'is_root': not parent_id or parent_id not in lookup,
            'child_ids': children,
            'child_count': len(children),
            'latest_options': branching.get('latest_options', []),
            'choice_history': branching.get('choice_history', []),
            'choice_history_count': len(branching.get('choice_history') or []),
            'checkpoint_label': item.get('branch_label') or ('Start' if not parent_id else 'Checkpoint'),
        })

    nodes.sort(key=lambda item: (int(item.get('order_index') or 0), int(item.get('depth') or 0), str(item.get('updated_at') or '')))
    root_nodes = [item for item in nodes if item.get('is_root')]
    start_part_id = str(root_nodes[0].get('id') or '').strip() if root_nodes else ''
    return {
        'story': story,
        'nodes': nodes,
        'start_part_id': start_part_id,
        'checkpoint_count': len(nodes),
        'branch_count': len([item for item in nodes if item.get('parent_part_id')]),
    }

def build_story_reader_payload(story_id: str) -> dict[str, Any]:
    story = get_story_record(story_id)
    if not story:
        raise ValueError('Story not found.')
    parts: list[dict[str, Any]] = []
    for item in list_story_parts(story_id):
        rec = get_part_record(str(item.get('id') or '').strip()) or {}
        transcript = _normalize_messages(rec.get('transcript'))
        branch = rec.get('branch') or {}
        parts.append({
            'id': rec.get('id', ''),
            'story_id': rec.get('story_id', ''),
            'title': rec.get('title', '') or item.get('title', ''),
            'order_index': int(rec.get('order_index') or item.get('order_index') or 0),
            'summary': rec.get('summary', ''),
            'scene_notes': rec.get('scene_notes', ''),
            'pinned_canon': rec.get('pinned_canon', ''),
            'scene_text': rec.get('scene_text', ''),
            'transcript': transcript,
            'updated_at': (rec.get('meta') or {}).get('updated_at', ''),
            'status': (rec.get('meta') or {}).get('status', 'draft'),
            'turn_count': len(transcript),
            'branch_label': branch.get('branch_label', ''),
            'parent_part_id': branch.get('parent_part_id', ''),
            'linked_context': normalize_linked_context(rec.get('linked_context')),
            'progression': normalize_progression(rec.get('progression')),
            'progression_summary': progression_summary(rec.get('progression')),
            'story_mode': str((rec.get('branching') or {}).get('story_mode') or 'linear'),
        })
    parts.sort(key=lambda item: (int(item.get('order_index') or 0), str(item.get('updated_at') or '')))
    return {'story': story, 'parts': parts}


def save_part_from_session(*, story_id: str, roleplay_state: dict[str, Any], part_title: str = '', part_id: str = '') -> dict[str, Any]:
    story = get_story_record(story_id)
    if not story:
        raise ValueError('Save a story card first before saving parts.')
    transcript = _normalize_messages(roleplay_state.get('transcript'))
    if not transcript and not str(roleplay_state.get('user_input') or '').strip():
        raise ValueError('There is no live scene content to save yet.')

    clean_part_id = str(part_id or '').strip()
    existing = get_part_record(clean_part_id) if clean_part_id else None
    order_index = len(story.get('part_ids') or []) + (0 if existing else 1)
    record = existing or story_part_template(story_id=story_id, title=part_title, order_index=order_index)
    if str(part_title or '').strip():
        record['title'] = str(part_title).strip()
    record['story_id'] = story_id
    record['transcript'] = transcript
    record['scene_text'] = _scene_text(transcript, str(roleplay_state.get('user_name') or ''), str(roleplay_state.get('partner_name') or ''))
    record['scene_notes'] = str(roleplay_state.get('scene_notes') or '').strip()
    record['pinned_canon'] = str(roleplay_state.get('memory_notes') or '').strip()
    record['linked_context'] = normalize_linked_context(roleplay_state.get('part_linked_context') or record.get('linked_context'))
    progression = normalize_progression(roleplay_state.get('progression') or record.get('progression'))
    record['progression'] = progression
    branching = normalize_branching_state(roleplay_state.get('branching') or {'story_mode': story.get('story_mode'), **(story.get('branching') or {})})
    record['branching'] = branching
    summary = str(roleplay_state.get('summary') or '').strip()
    if summary:
        record['summary'] = summary
    adv = record.get('advanced_controls') or {}
    adv.update({
        'author_note': str(roleplay_state.get('author_note') or '').strip(),
        'custom_tone': str(roleplay_state.get('custom_tone') or '').strip(),
        'tone': str(roleplay_state.get('tone') or '').strip(),
        'canon_mode': str(roleplay_state.get('canon_mode') or 'what_if').strip() or 'what_if',
        'output_preset': str(roleplay_state.get('output_preset') or 'roleplay').strip() or 'roleplay',
        'reply_style': str(roleplay_state.get('style') or '').strip(),
        'generation': {
            'max_tokens': int(roleplay_state.get('max_tokens') or 320),
            'temperature': float(roleplay_state.get('temperature') or 0.82),
            'top_p': float(roleplay_state.get('top_p') or 0.92),
            'top_k': int(roleplay_state.get('top_k') or 60),
        },
        'user_name': str(roleplay_state.get('user_name') or '').strip(),
        'partner_name': str(roleplay_state.get('partner_name') or '').strip(),
        'scenario': str(roleplay_state.get('scenario') or '').strip(),
        'user_character_id': str(roleplay_state.get('user_character_id') or '').strip(),
        'partner_character_id': str(roleplay_state.get('partner_character_id') or '').strip(),
        'world_id': str(roleplay_state.get('world_id') or '').strip(),
        'scenario_id': str(roleplay_state.get('scenario_id') or '').strip(),
        'interaction_mode': str(roleplay_state.get('interaction_mode') or 'roleplay').strip() or 'roleplay',
        'input_intent': str(roleplay_state.get('input_intent') or 'auto').strip() or 'auto',
        'story_scope_notes': str(roleplay_state.get('story_scope_notes') or '').strip(),
        'chapter_scope_notes': str(roleplay_state.get('chapter_scope_notes') or '').strip(),
        'part_scope_notes': str(roleplay_state.get('part_scope_notes') or '').strip(),
        'chapter_index': int(progression.get('chapter_index') or 1),
        'chapter_label': str(progression.get('chapter_label') or '').strip(),
        'part_index': int(progression.get('part_index') or 1),
        'beat_focus': str(progression.get('beat_focus') or '').strip(),
        'active_pov': str(progression.get('active_pov') or '').strip(),
        'active_location': str(progression.get('active_location') or '').strip(),
        'active_cast_focus': str(progression.get('active_cast_focus') or '').strip(),
        'part_objective': str(progression.get('part_objective') or '').strip(),
        'tension_level': str(progression.get('tension_level') or 'medium').strip(),
        'pacing_target': str(progression.get('pacing_target') or 'steady').strip(),
        'story_mode': str(branching.get('story_mode') or 'linear').strip(),
        'branch_option_count': int(branching.get('option_count') or 3),
        'branch_allow_custom_option': bool(branching.get('allow_custom_option', True)),
        'branch_latest_options': normalize_branch_options(branching.get('latest_options')),
        'branch_choice_history': normalize_branch_choice_history(branching.get('choice_history')),
        'story_linked_context_text': str(roleplay_state.get('story_linked_context_text') or '').strip(),
        'part_linked_context_text': str(roleplay_state.get('part_linked_context_text') or '').strip(),
    })
    record['advanced_controls'] = adv
    meta = record.get('meta') or {}
    if not meta.get('created_at'):
        meta['created_at'] = now_iso()
    meta['updated_at'] = now_iso()
    meta['status'] = 'saved'
    record['meta'] = meta
    part_path = _part_path(str(record.get('id') or '').strip())
    _write_json(part_path, record)

    story_ids = [str(item or '').strip() for item in (story.get('part_ids') or []) if str(item or '').strip()]
    if record['id'] not in story_ids:
        story_ids.append(record['id'])
    story['part_ids'] = story_ids
    story_meta = story.get('meta') or {}
    story_meta['updated_at'] = now_iso()
    story['meta'] = story_meta
    story_path = _story_path(str(story.get('id') or '').strip())
    _write_json(story_path, story)
    sync_roleplay_part_summary(record, source_json_path=str(part_path), summary_type='part_save')
    sync_roleplay_story(story, source_json_path=str(story_path))
    return record


def save_part_edits(*, part_id: str, title: str = '', summary: str = '', scene_notes: str = '', pinned_canon: str = '', scene_text: str = '', linked_context: Any = None) -> dict[str, Any]:
    record = get_part_record(part_id)
    if not record:
        raise ValueError('Story part not found.')
    adv = record.get('advanced_controls') or {}
    if str(title or '').strip():
        record['title'] = str(title).strip()
    record['summary'] = str(summary or '').strip()
    record['scene_notes'] = str(scene_notes or '').strip()
    record['pinned_canon'] = str(pinned_canon or '').strip()
    record['scene_text'] = str(scene_text or '').strip()
    record['linked_context'] = normalize_linked_context(linked_context or record.get('linked_context'))
    record['progression'] = normalize_progression(record.get('progression'))
    record['transcript'] = _transcript_from_scene_text(record['scene_text'], adv.get('user_name', ''), adv.get('partner_name', ''))
    meta = record.get('meta') or {}
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    record['memory_manifest'] = build_memory_manifest(
        lane='roleplay',
        scope_type='session_snapshot',
        scope_id=str(record.get('part_id') or record.get('story_id') or 'latest_session').strip(),
        summary_text=str(record.get('rolling_summary') or '').strip(),
        message_count=len(record.get('recent_turns') or []),
        updated_at=str(meta.get('updated_at') or now_iso()).strip(),
        extra={
            'story_id': str(record.get('story_id') or '').strip(),
            'part_id': str(record.get('part_id') or '').strip(),
        },
    )
    part_path = _part_path(str(record.get('id') or '').strip())
    _write_json(part_path, record)
    sync_roleplay_part_summary(record, source_json_path=str(part_path), summary_type='part_edit')
    story = get_story_record(str(record.get('story_id') or '').strip())
    if story:
        story_meta = story.get('meta') or {}
        story_meta['updated_at'] = now_iso()
        story['meta'] = story_meta
        story_path = _story_path(str(story.get('id') or '').strip())
        _write_json(story_path, story)
        sync_roleplay_story(story, source_json_path=str(story_path))
    return record


def branch_story_part(part_id: str, branch_label: str = '', choice_id: str = '', choice_label: str = '', choice_text: str = '', choice_source: str = 'generated') -> dict[str, Any]:
    record = get_part_record(part_id)
    if not record:
        raise ValueError('Story part not found.')
    story_id = str(record.get('story_id') or '').strip()
    story = get_story_record(story_id)
    if not story:
        raise ValueError('Parent story not found.')
    new_order = len(story.get('part_ids') or []) + 1
    label = str(branch_label or '').strip() or 'Alternate path'
    branched = story_part_template(story_id=story_id, title=f"{record.get('title', 'Part')} — {label}", order_index=new_order)
    branched['summary'] = record.get('summary', '')
    branched['scene_notes'] = record.get('scene_notes', '')
    branched['pinned_canon'] = record.get('pinned_canon', '')
    branched['scene_text'] = record.get('scene_text', '')
    branched['transcript'] = _normalize_messages(record.get('transcript'))
    branched['advanced_controls'] = dict(record.get('advanced_controls') or {})
    branched['progression'] = normalize_progression(record.get('progression'))
    branching = normalize_branching_state(record.get('branching'))
    choice_text_clean = str(choice_text or '').strip()
    if choice_text_clean:
        history = normalize_branch_choice_history(branching.get('choice_history'))
        history.append({
            'assistant_turn_index': max(0, len(branched['transcript']) - 1),
            'choice_id': str(choice_id or '').strip(),
            'label': str(choice_label or label or '').strip(),
            'text': choice_text_clean,
            'source': str(choice_source or 'generated').strip() or 'generated',
        })
        branching['choice_history'] = history
        branching['latest_options'] = []
    branched['branching'] = branching
    branched['branch'] = {
        'parent_part_id': str(record.get('id') or '').strip(),
        'branch_label': label,
        'checkpoint_part_id': str(record.get('id') or '').strip(),
    }
    meta = branched.get('meta') or {}
    meta['status'] = 'branch'
    meta['updated_at'] = now_iso()
    branched['meta'] = meta
    part_path = _part_path(str(branched.get('id') or '').strip())
    _write_json(part_path, branched)
    story_ids = [str(item or '').strip() for item in (story.get('part_ids') or []) if str(item or '').strip()]
    story_ids.append(str(branched.get('id') or '').strip())
    story['part_ids'] = story_ids
    story_meta = story.get('meta') or {}
    story_meta['updated_at'] = now_iso()
    story['meta'] = story_meta
    story_path = _story_path(story_id)
    _write_json(story_path, story)
    sync_roleplay_part_summary(branched, source_json_path=str(part_path), summary_type='branch')
    sync_roleplay_story(story, source_json_path=str(story_path))
    return branched


def build_session_payload(story_id: str, part_id: str) -> dict[str, Any]:
    story = get_story_record(story_id)
    part = get_part_record(str(part_id or '').strip())
    if not story or not part:
        raise ValueError('Story part not found.')
    adv = part.get('advanced_controls') or {}
    generation = adv.get('generation') or {}
    transcript = _normalize_messages(part.get('transcript'))
    if not transcript and str(part.get('scene_text') or '').strip():
        transcript = _transcript_from_scene_text(part.get('scene_text', ''), adv.get('user_name', ''), adv.get('partner_name', ''))
    story_linked_context = normalize_linked_context(story.get('linked_context'))
    part_linked_context = normalize_linked_context(part.get('linked_context'))
    progression = normalize_progression(part.get('progression') or adv)
    story_branching = normalize_branching_state({'story_mode': story.get('story_mode'), **(story.get('branching') or {})})
    part_branching = normalize_branching_state(part.get('branching') or adv)
    return {
        'story_id': story.get('id', ''),
        'part_id': part.get('id', ''),
        'story_linked_context': story_linked_context,
        'part_linked_context': part_linked_context,
        'story_linked_context_text': linked_context_summary(story_linked_context, 'Story linked context'),
        'part_linked_context_text': linked_context_summary(part_linked_context, 'Part linked context'),
        'scenario': adv.get('scenario', ''),
        'user_name': adv.get('user_name', ''),
        'partner_name': adv.get('partner_name', ''),
        'user_character_id': adv.get('user_character_id', ''),
        'partner_character_id': adv.get('partner_character_id', ''),
        'world_id': adv.get('world_id', ''),
        'scenario_id': adv.get('scenario_id', ''),
        'tone': adv.get('tone', ''),
        'custom_tone': adv.get('custom_tone', ''),
        'canon_mode': adv.get('canon_mode', 'what_if'),
        'output_preset': adv.get('output_preset', 'roleplay'),
        'style': adv.get('reply_style', ''),
        'interaction_mode': adv.get('interaction_mode', 'roleplay'),
        'input_intent': adv.get('input_intent', 'auto'),
        'scene_notes': part.get('scene_notes', ''),
        'memory_notes': part.get('pinned_canon', ''),
        'author_note': adv.get('author_note', ''),
        'story_scope_notes': adv.get('story_scope_notes', ''),
        'chapter_scope_notes': adv.get('chapter_scope_notes', ''),
        'part_scope_notes': adv.get('part_scope_notes', ''),
        'progression': progression,
        'progression_summary': progression_summary(progression),
        'chapter_index': progression.get('chapter_index', 1),
        'chapter_label': progression.get('chapter_label', ''),
        'part_index': progression.get('part_index', 1),
        'beat_focus': progression.get('beat_focus', ''),
        'active_pov': progression.get('active_pov', ''),
        'active_location': progression.get('active_location', ''),
        'active_cast_focus': progression.get('active_cast_focus', ''),
        'part_objective': progression.get('part_objective', ''),
        'tension_level': progression.get('tension_level', 'medium'),
        'pacing_target': progression.get('pacing_target', 'steady'),
        'story_mode': story_branching.get('story_mode', 'linear'),
        'branching': part_branching,
        'branch_option_count': part_branching.get('option_count', story_branching.get('option_count', 3)),
        'branch_allow_custom_option': part_branching.get('allow_custom_option', story_branching.get('allow_custom_option', True)),
        'branch_latest_options': part_branching.get('latest_options', []),
        'branch_choice_history': part_branching.get('choice_history', []),
        'max_tokens': generation.get('max_tokens', 320),
        'temperature': generation.get('temperature', 0.82),
        'top_p': generation.get('top_p', 0.92),
        'top_k': generation.get('top_k', 60),
        'transcript': transcript,
        'user_input': '',
        'lastReplyRequest': None,
        'story_title': story.get('title', ''),
        'part_title': part.get('title', ''),
    }


def autosave_session_snapshot(roleplay_state: dict[str, Any], *, story_id: str = '', part_id: str = '') -> dict[str, Any]:
    record = session_template(story_id=story_id, part_id=part_id)
    record['rolling_summary'] = str(roleplay_state.get('summary') or '').strip()
    record['recent_turns'] = _normalize_messages(roleplay_state.get('transcript'))
    record['draft_user_input'] = str(roleplay_state.get('user_input') or '').strip()
    record['pending_reply'] = str(roleplay_state.get('pending_reply') or '').strip()
    record['latest_finish_reason'] = str(roleplay_state.get('latest_finish_reason') or '').strip()
    record['truncated'] = bool(roleplay_state.get('truncated'))
    record['advanced_controls'] = {
        'scenario': str(roleplay_state.get('scenario') or '').strip(),
        'user_name': str(roleplay_state.get('user_name') or '').strip(),
        'partner_name': str(roleplay_state.get('partner_name') or '').strip(),
        'user_character_id': str(roleplay_state.get('user_character_id') or '').strip(),
        'partner_character_id': str(roleplay_state.get('partner_character_id') or '').strip(),
        'world_id': str(roleplay_state.get('world_id') or '').strip(),
        'scenario_id': str(roleplay_state.get('scenario_id') or '').strip(),
        'tone': str(roleplay_state.get('tone') or '').strip(),
        'custom_tone': str(roleplay_state.get('custom_tone') or '').strip(),
        'canon_mode': str(roleplay_state.get('canon_mode') or 'what_if').strip() or 'what_if',
        'output_preset': str(roleplay_state.get('output_preset') or 'roleplay').strip() or 'roleplay',
        'reply_style': str(roleplay_state.get('style') or '').strip(),
        'scene_notes': str(roleplay_state.get('scene_notes') or '').strip(),
        'memory_notes': str(roleplay_state.get('memory_notes') or '').strip(),
        'author_note': str(roleplay_state.get('author_note') or '').strip(),
        'interaction_mode': str(roleplay_state.get('interaction_mode') or 'roleplay').strip() or 'roleplay',
        'input_intent': str(roleplay_state.get('input_intent') or 'auto').strip() or 'auto',
        'story_scope_notes': str(roleplay_state.get('story_scope_notes') or '').strip(),
        'chapter_scope_notes': str(roleplay_state.get('chapter_scope_notes') or '').strip(),
        'part_scope_notes': str(roleplay_state.get('part_scope_notes') or '').strip(),
        'chapter_index': int(normalize_progression(roleplay_state.get('progression')).get('chapter_index') or 1),
        'chapter_label': str(normalize_progression(roleplay_state.get('progression')).get('chapter_label') or '').strip(),
        'part_index': int(normalize_progression(roleplay_state.get('progression')).get('part_index') or 1),
        'beat_focus': str(normalize_progression(roleplay_state.get('progression')).get('beat_focus') or '').strip(),
        'active_pov': str(normalize_progression(roleplay_state.get('progression')).get('active_pov') or '').strip(),
        'active_location': str(normalize_progression(roleplay_state.get('progression')).get('active_location') or '').strip(),
        'active_cast_focus': str(normalize_progression(roleplay_state.get('progression')).get('active_cast_focus') or '').strip(),
        'part_objective': str(normalize_progression(roleplay_state.get('progression')).get('part_objective') or '').strip(),
        'tension_level': str(normalize_progression(roleplay_state.get('progression')).get('tension_level') or 'medium').strip(),
        'pacing_target': str(normalize_progression(roleplay_state.get('progression')).get('pacing_target') or 'steady').strip(),
        'story_mode': str(normalize_branching_state(roleplay_state.get('branching')).get('story_mode') or 'linear').strip(),
        'branch_option_count': int(normalize_branching_state(roleplay_state.get('branching')).get('option_count') or 3),
        'branch_allow_custom_option': bool(normalize_branching_state(roleplay_state.get('branching')).get('allow_custom_option', True)),
        'branch_latest_options': normalize_branch_options(normalize_branching_state(roleplay_state.get('branching')).get('latest_options')),
        'branch_choice_history': normalize_branch_choice_history(normalize_branching_state(roleplay_state.get('branching')).get('choice_history')),
        'story_linked_context': normalize_linked_context(roleplay_state.get('story_linked_context')),
        'part_linked_context': normalize_linked_context(roleplay_state.get('part_linked_context')),
        'story_linked_context_text': str(roleplay_state.get('story_linked_context_text') or '').strip(),
        'part_linked_context_text': str(roleplay_state.get('part_linked_context_text') or '').strip(),
        'generation': {
            'max_tokens': int(roleplay_state.get('max_tokens') or 320),
            'temperature': float(roleplay_state.get('temperature') or 0.82),
            'top_p': float(roleplay_state.get('top_p') or 0.92),
            'top_k': int(roleplay_state.get('top_k') or 60),
        },
        'last_reply_request': roleplay_state.get('lastReplyRequest') or None,
    }
    meta = record.get('meta') or {}
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    record['memory_manifest'] = build_memory_manifest(
        lane='roleplay',
        scope_type='session_snapshot',
        scope_id=str(record.get('part_id') or record.get('story_id') or 'latest_session').strip(),
        summary_text=str(record.get('rolling_summary') or '').strip(),
        message_count=len(record.get('recent_turns') or []),
        updated_at=str(meta.get('updated_at') or now_iso()).strip(),
        extra={
            'story_id': str(record.get('story_id') or '').strip(),
            'part_id': str(record.get('part_id') or '').strip(),
        },
    )
    session_path = _session_path()
    saved = _write_json(session_path, record)
    snapshot_payload = {
        'story_id': str(record.get('story_id') or '').strip(),
        'part_id': str(record.get('part_id') or '').strip(),
        'rolling_summary': str(record.get('rolling_summary') or '').strip(),
        'summary': str(roleplay_state.get('summary') or '').strip(),
        'recent_turns': record.get('recent_turns') or [],
        'progression': normalize_progression(roleplay_state.get('progression')),
        'part_linked_context': normalize_linked_context(roleplay_state.get('part_linked_context')),
        'updated_at': str((record.get('meta') or {}).get('updated_at') or '').strip(),
        'created_at': str((record.get('meta') or {}).get('created_at') or '').strip(),
        'story_title': str(roleplay_state.get('story_title') or '').strip(),
        'part_title': str(roleplay_state.get('part_title') or '').strip(),
        'memory_manifest': record.get('memory_manifest') or {},
    }
    sync_roleplay_session_snapshot(snapshot_payload, source_json_path=str(session_path))
    return saved


def load_latest_session_snapshot() -> dict[str, Any] | None:
    record = _read_json(_session_path())
    if not record:
        return None
    adv = record.get('advanced_controls') or {}
    generation = adv.get('generation') or {}
    progression = normalize_progression(adv)
    story_branching = normalize_branching_state({
        'story_mode': adv.get('story_mode'),
        'option_count': adv.get('branch_option_count'),
        'allow_custom_option': adv.get('branch_allow_custom_option'),
        'latest_options': adv.get('branch_latest_options'),
        'choice_history': adv.get('branch_choice_history'),
    })
    part_branching = normalize_branching_state({
        'story_mode': adv.get('story_mode'),
        'option_count': adv.get('branch_option_count'),
        'allow_custom_option': adv.get('branch_allow_custom_option'),
        'latest_options': adv.get('branch_latest_options'),
        'choice_history': adv.get('branch_choice_history'),
    })
    return {
        'story_id': record.get('story_id', ''),
        'part_id': record.get('part_id', ''),
        'scenario': adv.get('scenario', ''),
        'user_name': adv.get('user_name', ''),
        'partner_name': adv.get('partner_name', ''),
        'user_character_id': adv.get('user_character_id', ''),
        'partner_character_id': adv.get('partner_character_id', ''),
        'world_id': adv.get('world_id', ''),
        'scenario_id': adv.get('scenario_id', ''),
        'tone': adv.get('tone', ''),
        'custom_tone': adv.get('custom_tone', ''),
        'canon_mode': adv.get('canon_mode', 'what_if'),
        'output_preset': adv.get('output_preset', 'roleplay'),
        'style': adv.get('reply_style', ''),
        'interaction_mode': adv.get('interaction_mode', 'roleplay'),
        'input_intent': adv.get('input_intent', 'auto'),
        'scene_notes': adv.get('scene_notes', ''),
        'memory_notes': adv.get('memory_notes', ''),
        'author_note': adv.get('author_note', ''),
        'story_scope_notes': adv.get('story_scope_notes', ''),
        'chapter_scope_notes': adv.get('chapter_scope_notes', ''),
        'part_scope_notes': adv.get('part_scope_notes', ''),
        'progression': progression,
        'progression_summary': progression_summary(progression),
        'chapter_index': progression.get('chapter_index', 1),
        'chapter_label': progression.get('chapter_label', ''),
        'part_index': progression.get('part_index', 1),
        'beat_focus': progression.get('beat_focus', ''),
        'active_pov': progression.get('active_pov', ''),
        'active_location': progression.get('active_location', ''),
        'active_cast_focus': progression.get('active_cast_focus', ''),
        'part_objective': progression.get('part_objective', ''),
        'tension_level': progression.get('tension_level', 'medium'),
        'pacing_target': progression.get('pacing_target', 'steady'),
        'story_mode': story_branching.get('story_mode', 'linear'),
        'branching': part_branching,
        'branch_option_count': part_branching.get('option_count', story_branching.get('option_count', 3)),
        'branch_allow_custom_option': part_branching.get('allow_custom_option', story_branching.get('allow_custom_option', True)),
        'branch_latest_options': part_branching.get('latest_options', []),
        'branch_choice_history': part_branching.get('choice_history', []),
        'story_linked_context': normalize_linked_context(adv.get('story_linked_context')),
        'part_linked_context': normalize_linked_context(adv.get('part_linked_context')),
        'story_linked_context_text': adv.get('story_linked_context_text', ''),
        'part_linked_context_text': adv.get('part_linked_context_text', ''),
        'max_tokens': generation.get('max_tokens', 320),
        'temperature': generation.get('temperature', 0.82),
        'top_p': generation.get('top_p', 0.92),
        'top_k': generation.get('top_k', 60),
        'transcript': _normalize_messages(record.get('recent_turns')),
        'user_input': record.get('draft_user_input', ''),
        'lastReplyRequest': adv.get('last_reply_request') or None,
    }
