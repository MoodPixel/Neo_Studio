from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from ..logging_utils import get_logger
from .chroma_store import ROLEPLAY_COLLECTION, delete_memory_chunks_for_entity, upsert_memory_chunks
from .extractor import extract_memory_candidates
from .sqlite_store import ensure_memory_foundation, execute, record_memory_write, upsert_memory_chunks_sqlite, delete_memory_chunks_for_entity_sqlite
from .summary_engine import build_roleplay_part_summary, build_roleplay_snapshot_summary, build_roleplay_story_summary

logger = get_logger(__name__)


def _json(value: Any, default: str = '{}') -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default), ensure_ascii=False)
    except Exception:
        return default


def _upsert_summary_record(*, summary_record_id: str, scope_type: str, scope_id: str, summary_type: str, content: str, source_ref: str = '', created_at: str = '', updated_at: str = '') -> None:
    execute(
        '''
        INSERT INTO summary_records(
            summary_record_id, lane, scope_type, scope_id, summary_type, content, source_ref, created_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(summary_record_id) DO UPDATE SET
            lane=excluded.lane,
            scope_type=excluded.scope_type,
            scope_id=excluded.scope_id,
            summary_type=excluded.summary_type,
            content=excluded.content,
            source_ref=excluded.source_ref,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at
        ''',
        (
            str(summary_record_id or '').strip(),
            'roleplay',
            str(scope_type or '').strip(),
            str(scope_id or '').strip(),
            str(summary_type or '').strip(),
            str(content or '').strip(),
            str(source_ref or '').strip(),
            str(created_at or '').strip(),
            str(updated_at or '').strip(),
        ),
    )


def sync_roleplay_story(story: dict[str, Any], *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        story_id = str(story.get('id') or '').strip()
        meta = story.get('meta') if isinstance(story.get('meta'), dict) else {}
        advanced = story.get('advanced_controls') if isinstance(story.get('advanced_controls'), dict) else {}
        execute(
            '''
            INSERT INTO roleplay_campaigns(
                campaign_id, story_id, title, universe_label, world_label, story_mode,
                linked_context_json, advanced_controls_json, summary, status, source_json_path,
                raw_json, created_at, updated_at, is_deleted
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(campaign_id) DO UPDATE SET
                story_id=excluded.story_id,
                title=excluded.title,
                universe_label=excluded.universe_label,
                world_label=excluded.world_label,
                story_mode=excluded.story_mode,
                linked_context_json=excluded.linked_context_json,
                advanced_controls_json=excluded.advanced_controls_json,
                summary=excluded.summary,
                status=excluded.status,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                is_deleted=0
            ''',
            (
                story_id,
                story_id,
                str(story.get('title') or '').strip(),
                str(story.get('universe_label') or '').strip(),
                str(story.get('world_label') or '').strip(),
                str(story.get('story_mode') or 'linear').strip(),
                _json(story.get('linked_context') or {}, '{}'),
                _json(advanced, '{}'),
                str(story.get('summary') or '').strip(),
                str(meta.get('status') or 'draft').strip(),
                str(source_json_path or '').strip(),
                _json(story, '{}'),
                str(meta.get('created_at') or '').strip(),
                str(meta.get('updated_at') or '').strip(),
            ),
        )
        execute(
            '''
            INSERT INTO roleplay_arc_state(
                arc_state_id, campaign_id, label, stage, active_part_id, unresolved_threads_json, notes, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arc_state_id) DO UPDATE SET
                campaign_id=excluded.campaign_id,
                label=excluded.label,
                stage=excluded.stage,
                active_part_id=excluded.active_part_id,
                unresolved_threads_json=excluded.unresolved_threads_json,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            ''',
            (
                f'arc::{story_id}::primary',
                story_id,
                str(story.get('title') or '').strip(),
                'active' if str(meta.get('status') or '').strip() != 'draft' else 'draft',
                str((story.get('part_ids') or [''])[-1] if isinstance(story.get('part_ids'), list) and (story.get('part_ids') or []) else '').strip(),
                '[]',
                str(story.get('summary') or '').strip(),
                str(meta.get('updated_at') or '').strip(),
            ),
        )
        summary = build_roleplay_story_summary(story)
        _upsert_summary_record(
            summary_record_id=f'summary_record::roleplay::story::{story_id}',
            scope_type='story',
            scope_id=story_id,
            summary_type='story_digest',
            content=summary,
            source_ref=source_json_path,
            created_at=str(meta.get('created_at') or '').strip(),
            updated_at=str(meta.get('updated_at') or '').strip(),
        )
        chunks = extract_memory_candidates('roleplay', 'story', story, source_ref=source_json_path)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='roleplay', collection_name=ROLEPLAY_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ROLEPLAY_COLLECTION, chunks)
        record_memory_write(write_log_id=f'rwl_{uuid4().hex}', lane='roleplay', entity_type='campaign', entity_id=story_id, operation='upsert', source_ref=str(source_json_path or '').strip(), details={'story_mode': str(story.get('story_mode') or 'linear').strip(), 'summary_length': len(summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'chroma_upserted': chroma_ok}, created_at=str(meta.get('updated_at') or meta.get('created_at') or '').strip())
        return True
    except Exception:
        logger.exception('Roleplay memory mirror failed for story sync.')
        return False


def sync_roleplay_part_summary(part: dict[str, Any], *, source_json_path: str = '', summary_type: str = 'part_save') -> bool:
    try:
        ensure_memory_foundation()
        part_id = str(part.get('id') or '').strip()
        story_id = str(part.get('story_id') or '').strip()
        meta = part.get('meta') if isinstance(part.get('meta'), dict) else {}
        transcript = part.get('transcript') if isinstance(part.get('transcript'), list) else []
        progression = part.get('progression') if isinstance(part.get('progression'), dict) else {}
        digest_summary = build_roleplay_part_summary(part)
        execute(
            '''
            INSERT INTO roleplay_session_summaries(
                summary_id, story_id, part_id, summary_type, title, content, progression_json,
                linked_context_json, transcript_turn_count, source_json_path, raw_json, status,
                created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_id) DO UPDATE SET
                story_id=excluded.story_id,
                part_id=excluded.part_id,
                summary_type=excluded.summary_type,
                title=excluded.title,
                content=excluded.content,
                progression_json=excluded.progression_json,
                linked_context_json=excluded.linked_context_json,
                transcript_turn_count=excluded.transcript_turn_count,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                status=excluded.status,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            ''',
            (
                f'roleplay_summary::{summary_type}::{part_id}',
                story_id,
                part_id,
                str(summary_type or 'part_save').strip(),
                str(part.get('title') or '').strip(),
                digest_summary,
                _json(progression, '{}'),
                _json(part.get('linked_context') or {}, '{}'),
                len(transcript),
                str(source_json_path or '').strip(),
                _json(part, '{}'),
                str(meta.get('status') or '').strip(),
                str(meta.get('created_at') or '').strip(),
                str(meta.get('updated_at') or '').strip(),
            ),
        )
        _upsert_summary_record(
            summary_record_id=f'summary_record::roleplay::{summary_type}::{part_id}',
            scope_type='part',
            scope_id=part_id,
            summary_type=str(summary_type or 'part_save').strip(),
            content=digest_summary,
            source_ref=source_json_path,
            created_at=str(meta.get('created_at') or '').strip(),
            updated_at=str(meta.get('updated_at') or '').strip(),
        )
        chunks = extract_memory_candidates('roleplay', 'part', part, source_ref=source_json_path)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='roleplay', collection_name=ROLEPLAY_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ROLEPLAY_COLLECTION, chunks)
        record_memory_write(write_log_id=f'rwl_{uuid4().hex}', lane='roleplay', entity_type='part_summary', entity_id=part_id, operation='upsert', source_ref=str(source_json_path or '').strip(), details={'story_id': story_id, 'summary_type': str(summary_type or 'part_save').strip(), 'summary_length': len(digest_summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'chroma_upserted': chroma_ok}, created_at=str(meta.get('updated_at') or meta.get('created_at') or '').strip())
        return True
    except Exception:
        logger.exception('Roleplay memory mirror failed for part summary sync.')
        return False


def sync_roleplay_session_snapshot(snapshot: dict[str, Any], *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        story_id = str(snapshot.get('story_id') or '').strip()
        part_id = str(snapshot.get('part_id') or '').strip()
        updated_at = str(snapshot.get('updated_at') or '').strip()
        created_at = str(snapshot.get('created_at') or updated_at).strip()
        turns = snapshot.get('transcript') if isinstance(snapshot.get('transcript'), list) else snapshot.get('recent_turns') if isinstance(snapshot.get('recent_turns'), list) else []
        progression = snapshot.get('progression') if isinstance(snapshot.get('progression'), dict) else {}
        digest_summary = build_roleplay_snapshot_summary(snapshot)
        execute(
            '''
            INSERT INTO roleplay_session_summaries(
                summary_id, story_id, part_id, summary_type, title, content, progression_json,
                linked_context_json, transcript_turn_count, source_json_path, raw_json, status,
                created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_id) DO UPDATE SET
                story_id=excluded.story_id,
                part_id=excluded.part_id,
                summary_type=excluded.summary_type,
                title=excluded.title,
                content=excluded.content,
                progression_json=excluded.progression_json,
                linked_context_json=excluded.linked_context_json,
                transcript_turn_count=excluded.transcript_turn_count,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                status=excluded.status,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            ''',
            (
                f'roleplay_summary::autosave::{story_id or "none"}::{part_id or "none"}',
                story_id,
                part_id,
                'autosave',
                str(snapshot.get('part_title') or snapshot.get('story_title') or 'Latest snapshot').strip(),
                digest_summary,
                _json(progression, '{}'),
                _json(snapshot.get('part_linked_context') or {}, '{}'),
                len(turns),
                str(source_json_path or '').strip(),
                _json(snapshot, '{}'),
                'active',
                created_at,
                updated_at,
            ),
        )
        _upsert_summary_record(
            summary_record_id=f'summary_record::roleplay::autosave::{story_id or "none"}::{part_id or "none"}',
            scope_type='snapshot',
            scope_id=f'{story_id}::{part_id}',
            summary_type='autosave',
            content=digest_summary,
            source_ref=source_json_path,
            created_at=created_at,
            updated_at=updated_at,
        )
        chunks = extract_memory_candidates('roleplay', 'snapshot', snapshot, source_ref=source_json_path)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='roleplay', collection_name=ROLEPLAY_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ROLEPLAY_COLLECTION, chunks)
        record_memory_write(write_log_id=f'rwl_{uuid4().hex}', lane='roleplay', entity_type='session_snapshot', entity_id=f'{story_id}::{part_id}', operation='upsert', source_ref=str(source_json_path or '').strip(), details={'summary_type': 'autosave', 'summary_length': len(digest_summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'chroma_upserted': chroma_ok}, created_at=updated_at or created_at)
        return True
    except Exception:
        logger.exception('Roleplay memory mirror failed for autosave snapshot sync.')
        return False


def mark_roleplay_story_deleted(story_id: str, *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        clean_id = str(story_id or '').strip()
        execute('UPDATE roleplay_campaigns SET is_deleted=1 WHERE campaign_id=? OR story_id=?', (clean_id, clean_id))
        delete_memory_chunks_for_entity_sqlite(lane='roleplay', entity_id=clean_id)
        delete_memory_chunks_for_entity(ROLEPLAY_COLLECTION, entity_id=clean_id)
        record_memory_write(write_log_id=f'rwl_{uuid4().hex}', lane='roleplay', entity_type='campaign', entity_id=clean_id, operation='delete', source_ref=str(source_json_path or '').strip())
        return True
    except Exception:
        logger.exception('Roleplay memory mirror failed for story delete.')
        return False
