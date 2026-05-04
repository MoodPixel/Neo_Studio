from __future__ import annotations

import re
from typing import Any

from .summary_engine import (
    build_assistant_profile_summary,
    build_assistant_project_summary,
    build_assistant_session_summary,
    build_roleplay_part_summary,
    build_roleplay_snapshot_summary,
    build_roleplay_story_summary,
)


def _clean(value: Any, limit: int = 1200) -> str:
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def _chunk(chunk_id: str, document: str, *, lane: str, chunk_type: str, entity_type: str, entity_id: str, source_ref: str = '', scope_type: str = '', scope_id: str = '', importance: float = 0.5, created_at: str = '') -> dict[str, Any] | None:
    doc = _clean(document, 2200)
    if not doc:
        return None
    return {
        'id': chunk_id,
        'document': doc,
        'metadata': {
            'lane': str(lane or '').strip(),
            'chunk_type': str(chunk_type or '').strip(),
            'entity_type': str(entity_type or '').strip(),
            'entity_id': str(entity_id or '').strip(),
            'scope_type': str(scope_type or entity_type or '').strip(),
            'scope_id': str(scope_id or entity_id or '').strip(),
            'source_ref': str(source_ref or '').strip(),
            'importance': float(importance or 0.0),
            'created_at': str(created_at or '').strip(),
        },
    }


def _append(out: list[dict[str, Any]], item: dict[str, Any] | None) -> None:
    if item:
        out.append(item)


def _assistant_chunks(entity_type: str, record: dict[str, Any], *, source_ref: str = '') -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    entity_id = str(record.get('id') or 'default').strip() or 'default'
    created_at = str(record.get('updated_at') or record.get('created_at') or '').strip()
    if entity_type == 'profile':
        summary = build_assistant_profile_summary(record)
        _append(out, _chunk('assistant::profile::summary', summary, lane='assistant', chunk_type='summary', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.9, created_at=created_at))
        if _clean(record.get('preferences')):
            _append(out, _chunk('assistant::profile::preferences', f"User preferences: {_clean(record.get('preferences'), 1200)}", lane='assistant', chunk_type='preference', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.98, created_at=created_at))
        if _clean(record.get('avoid')):
            _append(out, _chunk('assistant::profile::avoid', f"Avoid patterns: {_clean(record.get('avoid'), 900)}", lane='assistant', chunk_type='preference', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.95, created_at=created_at))
        style_doc = f"Address style: {_clean(record.get('address_style'), 40)} | Response detail: {_clean(record.get('response_detail'), 40)} | Support style: {_clean(record.get('support_style'), 40)} | Default mode: {_clean(record.get('default_mode'), 40)}"
        _append(out, _chunk('assistant::profile::style', style_doc, lane='assistant', chunk_type='style_shift', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.82, created_at=created_at))
    elif entity_type == 'project':
        summary = build_assistant_project_summary(record)
        _append(out, _chunk(f'assistant::project::{entity_id}::summary', summary, lane='assistant', chunk_type='summary', entity_type='project', entity_id=entity_id, source_ref=source_ref, importance=0.88, created_at=created_at))
        if _clean(record.get('brief')):
            _append(out, _chunk(f'assistant::project::{entity_id}::brief', f"Project brief: {_clean(record.get('brief'), 1800)}", lane='assistant', chunk_type='project_fact', entity_type='project', entity_id=entity_id, source_ref=source_ref, importance=0.94, created_at=created_at))
        for idx, card in enumerate((record.get('context_cards') if isinstance(record.get('context_cards'), list) else [])[:6], start=1):
            if not isinstance(card, dict):
                continue
            title = _clean(card.get('title'), 120)
            content = _clean(card.get('content'), 1400)
            if not content:
                continue
            chunk_type = 'workflow' if re.search(r'voice|style|tone|workflow|process|rules?', f'{title} {content}', re.IGNORECASE) else 'project_fact'
            _append(out, _chunk(f'assistant::project::{entity_id}::card::{idx}', f"{title}: {content}", lane='assistant', chunk_type=chunk_type, entity_type='project', entity_id=entity_id, source_ref=source_ref, importance=0.78, created_at=created_at))
    elif entity_type == 'session':
        summary = build_assistant_session_summary(record)
        project_id = str(record.get('project_id') or '').strip()
        scope_type = 'project' if project_id else 'session'
        scope_id = project_id or entity_id
        _append(out, _chunk(f'assistant::session::{entity_id}::summary', summary, lane='assistant', chunk_type='summary', entity_type='session', entity_id=entity_id, scope_type=scope_type, scope_id=scope_id, source_ref=source_ref, importance=0.84, created_at=created_at))
        if _clean(record.get('thread_instruction')):
            _append(out, _chunk(f'assistant::session::{entity_id}::thread_instruction', f"Thread instruction: {_clean(record.get('thread_instruction'), 1600)}", lane='assistant', chunk_type='workflow', entity_type='session', entity_id=entity_id, scope_type=scope_type, scope_id=scope_id, source_ref=source_ref, importance=0.86, created_at=created_at))
        helper = record.get('helper_context') if isinstance(record.get('helper_context'), dict) else {}
        if _clean(helper.get('instruction')):
            _append(out, _chunk(f'assistant::session::{entity_id}::helper', f"Workspace helper: {_clean(helper.get('workspace'), 60)} | target={_clean(helper.get('target'), 60)} | action={_clean(helper.get('action'), 60)} | instruction={_clean(helper.get('instruction'), 1200)}", lane='assistant', chunk_type='workflow', entity_type='session', entity_id=entity_id, scope_type=scope_type, scope_id=scope_id, source_ref=source_ref, importance=0.8, created_at=created_at))
        if _clean(record.get('context_note')):
            _append(out, _chunk(f'assistant::session::{entity_id}::context_note', f"Pinned thread context: {_clean(record.get('context_note'), 1500)}", lane='assistant', chunk_type='project_fact', entity_type='session', entity_id=entity_id, scope_type=scope_type, scope_id=scope_id, source_ref=source_ref, importance=0.72, created_at=created_at))
        messages = record.get('messages') if isinstance(record.get('messages'), list) else []
        latest_assistant = next((item for item in reversed(messages) if isinstance(item, dict) and str(item.get('role') or '') == 'assistant' and _clean(item.get('content'))), None)
        if latest_assistant:
            _append(out, _chunk(f'assistant::session::{entity_id}::latest_assistant', f"Preferred recent answer pattern: {_clean(latest_assistant.get('content'), 1600)}", lane='assistant', chunk_type='example_output', entity_type='session', entity_id=entity_id, scope_type=scope_type, scope_id=scope_id, source_ref=source_ref, importance=0.58, created_at=created_at))
    return out


def _roleplay_chunks(entity_type: str, record: dict[str, Any], *, source_ref: str = '') -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    entity_id = str(record.get('id') or record.get('story_id') or record.get('part_id') or '').strip()
    created_at = str((record.get('meta') or {}).get('updated_at') if isinstance(record.get('meta'), dict) else record.get('updated_at') or '').strip()
    if entity_type == 'story':
        summary = build_roleplay_story_summary(record)
        _append(out, _chunk(f'roleplay::story::{entity_id}::summary', summary, lane='roleplay', chunk_type='summary', entity_type='story', entity_id=entity_id, source_ref=source_ref, importance=0.9, created_at=created_at))
        world_bits = ' | '.join([part for part in [
            f"Universe: {_clean(record.get('universe_label'), 160)}",
            f"World: {_clean(record.get('world_label'), 160)}",
            f"Story mode: {_clean(record.get('story_mode'), 40)}",
            f"Pinned canon: {_clean(record.get('pinned_canon'), 1000)}",
        ] if _clean(part)])
        _append(out, _chunk(f'roleplay::story::{entity_id}::world', world_bits, lane='roleplay', chunk_type='world_fact', entity_type='story', entity_id=entity_id, source_ref=source_ref, importance=0.84, created_at=created_at))
    elif entity_type == 'part':
        summary = build_roleplay_part_summary(record)
        story_id = str(record.get('story_id') or '').strip()
        _append(out, _chunk(f'roleplay::part::{entity_id}::summary', summary, lane='roleplay', chunk_type='summary', entity_type='part', entity_id=entity_id, scope_type='story', scope_id=story_id or entity_id, source_ref=source_ref, importance=0.82, created_at=created_at))
        if _clean(record.get('summary')) or _clean(record.get('scene_notes')):
            _append(out, _chunk(f'roleplay::part::{entity_id}::event', f"Scene event: {_clean(record.get('summary') or record.get('scene_notes'), 1500)}", lane='roleplay', chunk_type='event', entity_type='part', entity_id=entity_id, scope_type='story', scope_id=story_id or entity_id, source_ref=source_ref, importance=0.88, created_at=created_at))
        if _clean(record.get('pinned_canon')):
            _append(out, _chunk(f'roleplay::part::{entity_id}::canon', f"Current canon note: {_clean(record.get('pinned_canon'), 1500)}", lane='roleplay', chunk_type='world_fact', entity_type='part', entity_id=entity_id, scope_type='story', scope_id=story_id or entity_id, source_ref=source_ref, importance=0.86, created_at=created_at))
    elif entity_type == 'snapshot':
        summary = build_roleplay_snapshot_summary(record)
        story_id = str(record.get('story_id') or '').strip()
        part_id = str(record.get('part_id') or '').strip()
        content = _clean(record.get('rolling_summary') or record.get('summary') or '', 1500)
        if content:
            _append(out, _chunk(f'roleplay::snapshot::{story_id or "none"}::{part_id or "none"}', summary, lane='roleplay', chunk_type='summary', entity_type='snapshot', entity_id=f'{story_id}::{part_id}', scope_type='story', scope_id=story_id or f'{story_id}::{part_id}', source_ref=source_ref, importance=0.42, created_at=created_at))
    return out


def extract_memory_candidates(lane: str, entity_type: str, record: dict[str, Any] | None = None, *, source_ref: str = '') -> list[dict[str, Any]]:
    record = record or {}
    lane_clean = str(lane or '').strip().lower()
    entity_clean = str(entity_type or '').strip().lower()
    if lane_clean == 'assistant':
        return _assistant_chunks(entity_clean, record, source_ref=source_ref)
    if lane_clean == 'roleplay':
        return _roleplay_chunks(entity_clean, record, source_ref=source_ref)
    return []
