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


def _chunk(chunk_id: str, document: str, *, lane: str, chunk_type: str, entity_type: str, entity_id: str, source_ref: str = '', scope_type: str = '', scope_id: str = '', importance: float = 0.5, created_at: str = '', extra_metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    doc = _clean(document, 2200)
    if not doc:
        return None
    metadata = {
        'lane': str(lane or '').strip(),
        'chunk_type': str(chunk_type or '').strip(),
        'entity_type': str(entity_type or '').strip(),
        'entity_id': str(entity_id or '').strip(),
        'scope_type': str(scope_type or entity_type or '').strip(),
        'scope_id': str(scope_id or entity_id or '').strip(),
        'source_ref': str(source_ref or '').strip(),
        'importance': float(importance or 0.0),
        'created_at': str(created_at or '').strip(),
    }
    if isinstance(extra_metadata, dict):
        for key, value in extra_metadata.items():
            if value is not None:
                metadata[str(key)] = value
    return {
        'id': chunk_id,
        'document': doc,
        'metadata': metadata,
    }



def _split_project_file_content(content: Any, *, max_chars: int = 1800, max_parts: int = 8) -> list[str]:
    text = str(content or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n+', text) if part.strip()] or [text]
    parts: list[str] = []
    current = ''
    for paragraph in paragraphs:
        cleaned = re.sub(r'\s+', ' ', paragraph).strip()
        if not cleaned:
            continue
        if len(cleaned) > max_chars:
            if current:
                parts.append(current.strip())
                current = ''
            for start in range(0, len(cleaned), max_chars):
                chunk = cleaned[start:start + max_chars].strip()
                if chunk:
                    parts.append(chunk)
                if len(parts) >= max_parts:
                    return parts
            continue
        candidate = f'{current}\n\n{cleaned}'.strip() if current else cleaned
        if len(candidate) > max_chars and current:
            parts.append(current.strip())
            current = cleaned
            if len(parts) >= max_parts:
                return parts
        else:
            current = candidate
    if current and len(parts) < max_parts:
        parts.append(current.strip())
    return parts[:max_parts]

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
        if _clean(record.get('voice_rules')):
            _append(out, _chunk('assistant::profile::voice_rules', f"Assistant voice rules: {_clean(record.get('voice_rules'), 1200)}", lane='assistant', chunk_type='assistant_voice_rule', entity_type='profile', entity_id='default', source_ref=source_ref, importance=1.0, created_at=created_at))
        if _clean(record.get('relationship_notes')):
            _append(out, _chunk('assistant::profile::relationship_notes', f"Assistant relationship/familiarity notes: {_clean(record.get('relationship_notes'), 1200)}", lane='assistant', chunk_type='relationship_belief', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.92, created_at=created_at))
        if _clean(record.get('response_boundaries')):
            _append(out, _chunk('assistant::profile::response_boundaries', f"Assistant response boundaries: {_clean(record.get('response_boundaries'), 1200)}", lane='assistant', chunk_type='guardrail', entity_type='profile', entity_id='default', source_ref=source_ref, importance=1.0, created_at=created_at))
        style_doc = f"Address style: {_clean(record.get('address_style'), 40)} | Response detail: {_clean(record.get('response_detail'), 40)} | Support style: {_clean(record.get('support_style'), 40)} | Default mode: {_clean(record.get('default_mode'), 40)} | Continuity style: {_clean(record.get('continuity_style'), 80)} | Persona enabled: {_clean(record.get('persona_enabled'), 20)}"
        _append(out, _chunk('assistant::profile::style', style_doc, lane='assistant', chunk_type='style_shift', entity_type='profile', entity_id='default', source_ref=source_ref, importance=0.82, created_at=created_at))
    elif entity_type == 'project':
        project_title = _clean(record.get('title') or 'New project', 160)
        project_meta = {
            'project_id': entity_id,
            'memory_project_id': entity_id,
            'project_title': project_title,
            'memory_scope': 'project',
            'visibility': 'project_private',
            'bleed_policy': 'deny_global',
            'sandbox_policy': 'project_boxed',
        }
        summary = build_assistant_project_summary(record)
        _append(out, _chunk(f'assistant::project::{entity_id}::summary', summary, lane='assistant', chunk_type='summary', entity_type='project', entity_id=entity_id, scope_type='project', scope_id=entity_id, source_ref=source_ref, importance=0.88, created_at=created_at, extra_metadata=project_meta))
        if _clean(record.get('brief')):
            _append(out, _chunk(f'assistant::project::{entity_id}::brief', f"Project brief: {_clean(record.get('brief'), 1800)}", lane='assistant', chunk_type='project_fact', entity_type='project', entity_id=entity_id, scope_type='project', scope_id=entity_id, source_ref=source_ref, importance=0.94, created_at=created_at, extra_metadata=project_meta))
        for idx, card in enumerate((record.get('context_cards') if isinstance(record.get('context_cards'), list) else [])[:6], start=1):
            if not isinstance(card, dict):
                continue
            title = _clean(card.get('title'), 120)
            content = _clean(card.get('content'), 1400)
            if not content:
                continue
            chunk_type = 'workflow' if re.search(r'voice|style|tone|workflow|process|rules?', f'{title} {content}', re.IGNORECASE) else 'project_fact'
            _append(out, _chunk(f'assistant::project::{entity_id}::card::{idx}', f"Project card — {title}: {content}", lane='assistant', chunk_type=chunk_type, entity_type='project', entity_id=entity_id, scope_type='project', scope_id=entity_id, source_ref=source_ref, importance=0.78, created_at=created_at, extra_metadata={**project_meta, 'source_kind': 'context_card', 'source_title': title}))
        for idx, file_item in enumerate((record.get('context_files') if isinstance(record.get('context_files'), list) else [])[:10], start=1):
            if not isinstance(file_item, dict):
                continue
            title = _clean(file_item.get('title') or f'Project file {idx}', 160)
            source_kind = _clean(file_item.get('source_kind') or 'text', 80)
            file_id = _clean(file_item.get('id') or str(idx), 120)
            for part_idx, part in enumerate(_split_project_file_content(file_item.get('content')), start=1):
                file_meta = {
                    **project_meta,
                    'chunk_type': 'project_docs',
                    'source_kind': 'context_file',
                    'source_title': title,
                    'source_file_id': file_id,
                    'document_kind': source_kind,
                    'part_index': part_idx,
                }
                label = f"Project file — {title}" if part_idx == 1 else f"Project file — {title} (part {part_idx})"
                _append(out, _chunk(f'assistant::project::{entity_id}::file::{idx}::{part_idx}', f"{label}: {part}", lane='assistant', chunk_type='project_docs', entity_type='project', entity_id=entity_id, scope_type='project', scope_id=entity_id, source_ref=source_ref, importance=0.9, created_at=str(file_item.get('created_at') or created_at).strip(), extra_metadata=file_meta))
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
