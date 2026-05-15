from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from ..logging_utils import get_logger
from .chroma_store import ASSISTANT_COLLECTION, delete_memory_chunks_for_entity, upsert_memory_chunks
from .extractor import extract_memory_candidates
from .sqlite_store import ensure_memory_foundation, execute, record_memory_write, upsert_memory_chunks_sqlite, delete_memory_chunks_for_entity_sqlite
from .summary_engine import (
    build_assistant_profile_summary,
    build_assistant_project_summary,
    build_assistant_session_summary,
)

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
            'assistant',
            str(scope_type or '').strip(),
            str(scope_id or '').strip(),
            str(summary_type or '').strip(),
            str(content or '').strip(),
            str(source_ref or '').strip(),
            str(created_at or '').strip(),
            str(updated_at or '').strip(),
        ),
    )


def sync_assistant_profile(profile: dict[str, Any], *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        updated_at = str(profile.get('updated_at') or '').strip()
        execute(
            '''
            INSERT INTO assistant_profiles(
                profile_id, assistant_name, user_name, address_style, default_mode, response_detail,
                support_style, about_user, preferences, avoid, source_json_path, raw_json, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                assistant_name=excluded.assistant_name,
                user_name=excluded.user_name,
                address_style=excluded.address_style,
                default_mode=excluded.default_mode,
                response_detail=excluded.response_detail,
                support_style=excluded.support_style,
                about_user=excluded.about_user,
                preferences=excluded.preferences,
                avoid=excluded.avoid,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            ''',
            (
                'default',
                str(profile.get('assistant_name') or 'Neo').strip(),
                str(profile.get('user_name') or '').strip(),
                str(profile.get('address_style') or 'adaptive').strip(),
                str(profile.get('default_mode') or 'general').strip(),
                str(profile.get('response_detail') or 'balanced').strip(),
                str(profile.get('support_style') or 'balanced').strip(),
                str(profile.get('about_user') or '').strip(),
                str(profile.get('preferences') or '').strip(),
                str(profile.get('avoid') or '').strip(),
                str(source_json_path or '').strip(),
                _json(profile, '{}'),
                updated_at,
            ),
        )
        summary = build_assistant_profile_summary(profile)
        _upsert_summary_record(
            summary_record_id='summary_record::assistant::profile::default',
            scope_type='profile',
            scope_id='default',
            summary_type='profile_digest',
            content=summary,
            source_ref=source_json_path,
            created_at=updated_at,
            updated_at=updated_at,
        )
        chunks = extract_memory_candidates('assistant', 'profile', profile, source_ref=source_json_path)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, chunks)
        record_memory_write(
            write_log_id=f'awl_{uuid4().hex}', lane='assistant', entity_type='profile', entity_id='default',
            operation='upsert', source_ref=str(source_json_path or '').strip(),
            details={'updated_at': updated_at, 'summary_length': len(summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'chroma_upserted': chroma_ok}, created_at=updated_at,
        )
        return True
    except Exception:
        logger.exception('Assistant memory mirror failed for profile sync.')
        return False


def sync_assistant_project(project: dict[str, Any], *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        project_id = str(project.get('id') or '').strip()
        created_at = str(project.get('created_at') or '').strip()
        updated_at = str(project.get('updated_at') or '').strip()
        execute(
            '''
            INSERT INTO assistant_projects(
                project_id, title, description, brief, context_cards_json, context_files_json,
                linked_records_json, thread_count, source_json_path, raw_json, created_at, updated_at, is_deleted
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(project_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                brief=excluded.brief,
                context_cards_json=excluded.context_cards_json,
                context_files_json=excluded.context_files_json,
                linked_records_json=excluded.linked_records_json,
                thread_count=excluded.thread_count,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                is_deleted=0
            ''',
            (
                project_id,
                str(project.get('title') or 'New project').strip(),
                str(project.get('description') or '').strip(),
                str(project.get('brief') or '').strip(),
                _json(project.get('context_cards') or [], '[]'),
                _json(project.get('context_files') or [], '[]'),
                _json(project.get('linked_records') or [], '[]'),
                int(project.get('thread_count') or 0),
                str(source_json_path or '').strip(),
                _json(project, '{}'),
                created_at,
                updated_at,
            ),
        )
        summary = build_assistant_project_summary(project)
        _upsert_summary_record(
            summary_record_id=f'summary_record::assistant::project::{project_id}',
            scope_type='project',
            scope_id=project_id,
            summary_type='project_digest',
            content=summary,
            source_ref=source_json_path,
            created_at=created_at,
            updated_at=updated_at,
        )
        chunks = extract_memory_candidates('assistant', 'project', project, source_ref=source_json_path)
        # Project context files can be added, edited, or removed. Clear prior project chunks
        # before re-upserting the deterministic current set so stale removed file chunks do
        # not remain retrievable after a project save. SQLite upsert restores current chunks
        # and preserves pin/suppression fields on matching chunk ids.
        deleted_sqlite_chunks = delete_memory_chunks_for_entity_sqlite(lane='assistant', entity_id=project_id)
        delete_memory_chunks_for_entity(ASSISTANT_COLLECTION, entity_id=project_id)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, chunks)
        record_memory_write(
            write_log_id=f'awl_{uuid4().hex}', lane='assistant', entity_type='project', entity_id=project_id,
            operation='upsert', source_ref=str(source_json_path or '').strip(),
            details={'updated_at': updated_at, 'summary_length': len(summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'deleted_sqlite_chunks': deleted_sqlite_chunks, 'chroma_upserted': chroma_ok}, created_at=updated_at or created_at,
        )
        return True
    except Exception:
        logger.exception('Assistant memory mirror failed for project sync.')
        return False


def sync_assistant_session(session: dict[str, Any], *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        session_id = str(session.get('id') or '').strip()
        created_at = str(session.get('created_at') or '').strip()
        updated_at = str(session.get('updated_at') or '').strip()
        execute(
            '''
            INSERT INTO assistant_sessions(
                session_id, project_id, title, mode, thread_instruction, helper_context_json,
                context_note, context_items_json, draft, params_json, memory_summary, message_count,
                preview, pending_continue, pending_continue_reason, source_json_path, raw_json,
                created_at, updated_at, is_deleted
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(session_id) DO UPDATE SET
                project_id=excluded.project_id,
                title=excluded.title,
                mode=excluded.mode,
                thread_instruction=excluded.thread_instruction,
                helper_context_json=excluded.helper_context_json,
                context_note=excluded.context_note,
                context_items_json=excluded.context_items_json,
                draft=excluded.draft,
                params_json=excluded.params_json,
                memory_summary=excluded.memory_summary,
                message_count=excluded.message_count,
                preview=excluded.preview,
                pending_continue=excluded.pending_continue,
                pending_continue_reason=excluded.pending_continue_reason,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                is_deleted=0
            ''',
            (
                session_id,
                str(session.get('project_id') or '').strip(),
                str(session.get('title') or 'New assistant chat').strip(),
                str(session.get('mode') or 'general').strip(),
                str(session.get('thread_instruction') or '').strip(),
                _json(session.get('helper_context') or {}, '{}'),
                str(session.get('context_note') or '').strip(),
                _json(session.get('context_items') or [], '[]'),
                str(session.get('draft') or '').rstrip(),
                _json(session.get('params') or {}, '{}'),
                str(session.get('memory_summary') or '').strip(),
                int(session.get('message_count') or len(session.get('messages') or [])),
                str(session.get('preview') or '').strip(),
                1 if bool(session.get('pending_continue')) else 0,
                str(session.get('pending_continue_reason') or '').strip(),
                str(source_json_path or '').strip(),
                _json(session, '{}'),
                created_at,
                updated_at,
            ),
        )
        digest_summary = build_assistant_session_summary(session)
        execute(
            '''
            INSERT INTO assistant_summaries(
                summary_id, session_id, project_id, summary_type, content, source_message_count,
                source_json_path, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_id) DO UPDATE SET
                session_id=excluded.session_id,
                project_id=excluded.project_id,
                summary_type=excluded.summary_type,
                content=excluded.content,
                source_message_count=excluded.source_message_count,
                source_json_path=excluded.source_json_path,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            ''',
            (
                f'assistant_summary::{session_id}::session_digest',
                session_id,
                str(session.get('project_id') or '').strip(),
                'session_digest',
                digest_summary,
                int(session.get('message_count') or len(session.get('messages') or [])),
                str(source_json_path or '').strip(),
                created_at,
                updated_at,
            ),
        )
        memory_summary = str(session.get('memory_summary') or '').strip()
        if memory_summary:
            execute(
                '''
                INSERT INTO assistant_summaries(
                    summary_id, session_id, project_id, summary_type, content, source_message_count,
                    source_json_path, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(summary_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    project_id=excluded.project_id,
                    summary_type=excluded.summary_type,
                    content=excluded.content,
                    source_message_count=excluded.source_message_count,
                    source_json_path=excluded.source_json_path,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                ''',
                (
                    f'assistant_summary::{session_id}::thread_memory',
                    session_id,
                    str(session.get('project_id') or '').strip(),
                    'thread_memory',
                    memory_summary,
                    int(session.get('message_count') or len(session.get('messages') or [])),
                    str(source_json_path or '').strip(),
                    str(session.get('memory_updated_at') or updated_at).strip(),
                    str(session.get('memory_updated_at') or updated_at).strip(),
                ),
            )
        _upsert_summary_record(
            summary_record_id=f'summary_record::assistant::session::{session_id}',
            scope_type='session',
            scope_id=session_id,
            summary_type='session_digest',
            content=digest_summary,
            source_ref=source_json_path,
            created_at=created_at,
            updated_at=updated_at,
        )
        chunks = extract_memory_candidates('assistant', 'session', session, source_ref=source_json_path)
        sqlite_chunk_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=chunks)
        chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, chunks)
        record_memory_write(
            write_log_id=f'awl_{uuid4().hex}', lane='assistant', entity_type='session', entity_id=session_id,
            operation='upsert', source_ref=str(source_json_path or '').strip(),
            details={'updated_at': updated_at, 'project_id': str(session.get('project_id') or '').strip(), 'summary_length': len(digest_summary), 'chunk_count': len(chunks), 'sqlite_chunk_count': sqlite_chunk_count, 'chroma_upserted': chroma_ok}, created_at=updated_at or created_at,
        )
        return True
    except Exception:
        logger.exception('Assistant memory mirror failed for session sync.')
        return False


def mark_assistant_project_deleted(project_id: str, *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        clean_id = str(project_id or '').strip()
        execute('UPDATE assistant_projects SET is_deleted=1 WHERE project_id=?', (clean_id,))
        delete_memory_chunks_for_entity_sqlite(lane='assistant', entity_id=clean_id)
        delete_memory_chunks_for_entity(ASSISTANT_COLLECTION, entity_id=clean_id)
        record_memory_write(write_log_id=f'awl_{uuid4().hex}', lane='assistant', entity_type='project', entity_id=clean_id, operation='delete', source_ref=str(source_json_path or '').strip())
        return True
    except Exception:
        logger.exception('Assistant memory mirror failed for project delete.')
        return False


def mark_assistant_session_deleted(session_id: str, *, source_json_path: str = '') -> bool:
    try:
        ensure_memory_foundation()
        clean_id = str(session_id or '').strip()
        execute('UPDATE assistant_sessions SET is_deleted=1 WHERE session_id=?', (clean_id,))
        delete_memory_chunks_for_entity_sqlite(lane='assistant', entity_id=clean_id)
        delete_memory_chunks_for_entity(ASSISTANT_COLLECTION, entity_id=clean_id)
        record_memory_write(write_log_id=f'awl_{uuid4().hex}', lane='assistant', entity_type='session', entity_id=clean_id, operation='delete', source_ref=str(source_json_path or '').strip())
        return True
    except Exception:
        logger.exception('Assistant memory mirror failed for session delete.')
        return False
