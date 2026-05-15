from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .assistant_store import load_project, update_project
from .assistant_knowledge_ingestion import ingest_knowledge_document
from .memory_service.chroma_store import ASSISTANT_COLLECTION, upsert_memory_chunks
from .memory_service.sqlite_store import ensure_memory_foundation, record_memory_write, upsert_memory_chunks_sqlite
from .assistant_memory_reindex import refresh_after_memory_write

MAX_MANUAL_CAPTURE_CHARS = 120_000


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec='seconds') + 'Z'


def _clean_text(value: Any, limit: int = MAX_MANUAL_CAPTURE_CHARS) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text[:limit].strip()


def _safe_title(value: Any, fallback: str = 'Manual memory') -> str:
    title = ' '.join(str(value or '').strip().split())[:180]
    return title or fallback


def _slug(value: str, fallback: str = 'capture') -> str:
    text = re.sub(r'[^a-zA-Z0-9._-]+', '-', str(value or '').strip()).strip('-._').lower()
    return text[:80] or fallback


def _split_text(text: str, max_chars: int = 5500) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    blocks = [block.strip() for block in re.split(r'\n\s*\n', clean) if block.strip()]
    chunks: list[str] = []
    current = ''
    for block in blocks or [clean]:
        if current and len(current) + len(block) + 2 > max_chars:
            chunks.append(current.strip())
            current = block
        else:
            current = f'{current}\n\n{block}'.strip() if current else block
    if current.strip():
        chunks.append(current.strip())
    return chunks or [clean[:max_chars]]


def capture_manual_memory(*, text: str, title: str = '', capture_type: str = 'memory', project_id: str = '', session_id: str = '', canon_status: str = 'draft', visibility: str = 'project_private', source: str = 'manual') -> dict[str, Any]:
    """Capture pasted/selected/chat text into Assistant memory.

    Project lore/canon captures reuse the structured knowledge importer so entity graph,
    import reports, and canon metadata stay consistent with file imports. Generic memory
    captures write a small project/session-scoped memory chunk directly.
    """
    content = _clean_text(text)
    if not content:
        raise ValueError('No text was provided to save as memory.')
    if len(content) > MAX_MANUAL_CAPTURE_CHARS:
        raise ValueError('That memory capture is too large. Keep manual captures under 120k characters.')

    clean_project_id = str(project_id or '').strip()
    clean_capture_type = str(capture_type or 'memory').strip().lower()
    clean_source = str(source or 'manual').strip().lower()[:40] or 'manual'
    safe_title = _safe_title(title, 'Manual memory')

    if clean_capture_type in {'project_lore', 'canon_draft', 'active_canon', 'pasted_knowledge'}:
        if not clean_project_id:
            raise ValueError('Select a project before saving this as project knowledge.')
        status = str(canon_status or '').strip().lower() or 'draft'
        if clean_capture_type == 'canon_draft':
            status = 'draft'
        elif clean_capture_type == 'active_canon':
            status = 'active'
        filename = f'{_slug(safe_title, "manual-knowledge")}.txt'
        report = ingest_knowledge_document(
            project_id=clean_project_id,
            filename=filename,
            raw=content.encode('utf-8'),
            canon_status=status,
            visibility=visibility or 'project_private',
            import_mode=f'{clean_source}:{clean_capture_type}',
        )
        return {**report, 'capture_type': clean_capture_type, 'manual_capture': True}

    now = _now_iso()
    capture_id = f'manual_capture_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:8]}'
    source_ref = f'assistant_manual_capture:{clean_project_id or "global"}:{session_id or "no-session"}:{capture_id}'
    chunks = []
    parts = _split_text(content)
    for idx, part in enumerate(parts):
        document = f'Title: {safe_title}\nSource: {clean_source}\nCapture type: {clean_capture_type}\nProject: {clean_project_id or "global"}\nSession: {session_id or "none"}\n\n{part}'
        chunks.append({
            'id': f'assistant::manual::{capture_id}::{idx:04d}',
            'document': document,
            'metadata': {
                'lane': 'assistant',
                'chunk_type': 'manual_memory',
                'entity_type': 'manual_capture',
                'entity_id': capture_id,
                'scope_type': 'project' if clean_project_id else ('session' if session_id else 'global'),
                'scope_id': clean_project_id or session_id or 'global',
                'project_id': clean_project_id,
                'session_id': str(session_id or '').strip(),
                'source_ref': source_ref,
                'source': clean_source,
                'capture_type': clean_capture_type,
                'title': safe_title,
                'importance': 0.72,
                'created_at': now,
                'updated_at': now,
            },
        })
    ensure_memory_foundation()
    sqlite_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=chunks)
    chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, chunks)

    updated_project = None
    if clean_project_id:
        project = load_project(clean_project_id)
        if project:
            linked = list(project.get('linked_records') if isinstance(project.get('linked_records'), list) else [])
            linked.append({
                'id': f'project_record_{uuid4().hex[:12]}',
                'title': f'Manual memory: {safe_title}',
                'record_type': 'manual_memory',
                'note': f'Saved {len(chunks)} manual memory chunk(s) from {clean_source}.',
                'source': source_ref,
                'created_at': now,
            })
            updated_project = update_project(clean_project_id, {'linked_records': linked}) or project

    record_memory_write(
        write_log_id=f'awl_{uuid4().hex}',
        lane='assistant',
        entity_type='manual_capture',
        entity_id=capture_id,
        operation='capture',
        source_ref=source_ref,
        details={
            'capture_id': capture_id,
            'capture_type': clean_capture_type,
            'project_id': clean_project_id,
            'session_id': session_id,
            'title': safe_title,
            'chunk_count': len(chunks),
            'source': clean_source,
        },
        created_at=now,
    )
    memory_refresh = refresh_after_memory_write(
        lane='assistant',
        project_id=clean_project_id,
        session_id=str(session_id or '').strip(),
        reason='manual_capture',
        chunk_ids=[str(chunk.get('id') or '').strip() for chunk in chunks if str(chunk.get('id') or '').strip()],
        auto_refresh=True,
    )
    return {
        'ok': True,
        'capture_id': capture_id,
        'capture_type': clean_capture_type,
        'project_id': clean_project_id,
        'session_id': session_id,
        'title': safe_title,
        'chunk_count': len(chunks),
        'sqlite_chunk_count': sqlite_count,
        'chroma_upserted': bool(chroma_ok),
        'source_ref': source_ref,
        'created_at': now,
        'project': updated_project,
        'manual_capture': True,
        'memory_index_state': memory_refresh.get('index_state') if isinstance(memory_refresh, dict) else {},
        'memory_refresh': memory_refresh,
    }
