from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ..library_constants import DEFAULT_ROOT
from ..logging_utils import get_logger

logger = get_logger(__name__)

MEMORY_ROOT = DEFAULT_ROOT / 'memory'
MEMORY_DB_PATH = MEMORY_ROOT / 'neo_memory.sqlite3'
SCHEMA_VERSION = 3

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS memory_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_profiles (
        profile_id TEXT PRIMARY KEY,
        assistant_name TEXT NOT NULL DEFAULT 'Neo',
        user_name TEXT NOT NULL DEFAULT '',
        address_style TEXT NOT NULL DEFAULT 'adaptive',
        default_mode TEXT NOT NULL DEFAULT 'general',
        response_detail TEXT NOT NULL DEFAULT 'balanced',
        support_style TEXT NOT NULL DEFAULT 'balanced',
        about_user TEXT NOT NULL DEFAULT '',
        preferences TEXT NOT NULL DEFAULT '',
        avoid TEXT NOT NULL DEFAULT '',
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_projects (
        project_id TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT 'New project',
        description TEXT NOT NULL DEFAULT '',
        brief TEXT NOT NULL DEFAULT '',
        context_cards_json TEXT NOT NULL DEFAULT '[]',
        context_files_json TEXT NOT NULL DEFAULT '[]',
        linked_records_json TEXT NOT NULL DEFAULT '[]',
        thread_count INTEGER NOT NULL DEFAULT 0,
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        is_deleted INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT 'New assistant chat',
        mode TEXT NOT NULL DEFAULT 'general',
        thread_instruction TEXT NOT NULL DEFAULT '',
        helper_context_json TEXT NOT NULL DEFAULT '{}',
        context_note TEXT NOT NULL DEFAULT '',
        context_items_json TEXT NOT NULL DEFAULT '[]',
        draft TEXT NOT NULL DEFAULT '',
        params_json TEXT NOT NULL DEFAULT '{}',
        memory_summary TEXT NOT NULL DEFAULT '',
        message_count INTEGER NOT NULL DEFAULT 0,
        preview TEXT NOT NULL DEFAULT '',
        pending_continue INTEGER NOT NULL DEFAULT 0,
        pending_continue_reason TEXT NOT NULL DEFAULT '',
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        is_deleted INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_style_preferences (
        preference_id TEXT PRIMARY KEY,
        scope_type TEXT NOT NULL DEFAULT 'profile',
        scope_id TEXT NOT NULL DEFAULT '',
        preference_key TEXT NOT NULL DEFAULT '',
        preference_value TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0.0,
        source_ref TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_task_patterns (
        pattern_id TEXT PRIMARY KEY,
        label TEXT NOT NULL DEFAULT '',
        pattern_key TEXT NOT NULL DEFAULT '',
        notes_json TEXT NOT NULL DEFAULT '{}',
        confidence REAL NOT NULL DEFAULT 0.0,
        last_seen_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_summaries (
        summary_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        summary_type TEXT NOT NULL DEFAULT 'thread_memory',
        content TEXT NOT NULL DEFAULT '',
        source_message_count INTEGER NOT NULL DEFAULT 0,
        source_json_path TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_campaigns (
        campaign_id TEXT PRIMARY KEY,
        story_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        universe_label TEXT NOT NULL DEFAULT '',
        world_label TEXT NOT NULL DEFAULT '',
        story_mode TEXT NOT NULL DEFAULT 'linear',
        linked_context_json TEXT NOT NULL DEFAULT '{}',
        advanced_controls_json TEXT NOT NULL DEFAULT '{}',
        summary TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        is_deleted INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_roleplay_campaigns_story_id
    ON roleplay_campaigns(story_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_character_state (
        character_state_id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL DEFAULT '',
        character_id TEXT NOT NULL DEFAULT '',
        current_location_id TEXT NOT NULL DEFAULT '',
        current_location_label TEXT NOT NULL DEFAULT '',
        current_goal TEXT NOT NULL DEFAULT '',
        emotional_state TEXT NOT NULL DEFAULT '',
        notes_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_relationship_state (
        relationship_state_id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL DEFAULT '',
        source_character_id TEXT NOT NULL DEFAULT '',
        target_character_id TEXT NOT NULL DEFAULT '',
        relationship_type TEXT NOT NULL DEFAULT '',
        trust_level REAL NOT NULL DEFAULT 0.0,
        intimacy_level REAL NOT NULL DEFAULT 0.0,
        conflict_level REAL NOT NULL DEFAULT 0.0,
        notes TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_world_state (
        world_state_id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL DEFAULT '',
        scope_type TEXT NOT NULL DEFAULT '',
        scope_id TEXT NOT NULL DEFAULT '',
        delta_kind TEXT NOT NULL DEFAULT '',
        delta_text TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_arc_state (
        arc_state_id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        stage TEXT NOT NULL DEFAULT '',
        active_part_id TEXT NOT NULL DEFAULT '',
        unresolved_threads_json TEXT NOT NULL DEFAULT '[]',
        notes TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roleplay_session_summaries (
        summary_id TEXT PRIMARY KEY,
        story_id TEXT NOT NULL DEFAULT '',
        part_id TEXT NOT NULL DEFAULT '',
        summary_type TEXT NOT NULL DEFAULT 'part_save',
        title TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL DEFAULT '',
        progression_json TEXT NOT NULL DEFAULT '{}',
        linked_context_json TEXT NOT NULL DEFAULT '{}',
        transcript_turn_count INTEGER NOT NULL DEFAULT 0,
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summary_records (
        summary_record_id TEXT PRIMARY KEY,
        lane TEXT NOT NULL DEFAULT '',
        scope_type TEXT NOT NULL DEFAULT '',
        scope_id TEXT NOT NULL DEFAULT '',
        summary_type TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_chunks (
        chunk_id TEXT PRIMARY KEY,
        lane TEXT NOT NULL DEFAULT '',
        collection_name TEXT NOT NULL DEFAULT '',
        chunk_type TEXT NOT NULL DEFAULT '',
        entity_type TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        scope_type TEXT NOT NULL DEFAULT '',
        scope_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        campaign_id TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        importance REAL NOT NULL DEFAULT 0.0,
        document TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        is_deleted INTEGER NOT NULL DEFAULT 0,
        is_pinned INTEGER NOT NULL DEFAULT 0,
        pin_note TEXT NOT NULL DEFAULT '',
        is_suppressed INTEGER NOT NULL DEFAULT 0,
        suppressed_reason TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_lane_scope
    ON memory_chunks(lane, scope_type, scope_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_lane_entity
    ON memory_chunks(lane, entity_type, entity_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_lane_project_campaign
    ON memory_chunks(lane, project_id, campaign_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_write_log (
        write_log_id TEXT PRIMARY KEY,
        lane TEXT NOT NULL DEFAULT '',
        entity_type TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        operation TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT ''
    )
    """,
)


def _json(value: Any, default: str = '{}') -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default), ensure_ascii=False)
    except Exception:
        return default


@contextmanager
def sqlite_conn() -> Iterator[sqlite3.Connection]:
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=OFF')
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_memory_chunk_columns(conn: sqlite3.Connection) -> None:
    existing = {str(row['name'] or '').strip() for row in conn.execute('PRAGMA table_info(memory_chunks)')}
    wanted = {
        'is_pinned': "ALTER TABLE memory_chunks ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0",
        'pin_note': "ALTER TABLE memory_chunks ADD COLUMN pin_note TEXT NOT NULL DEFAULT ''",
        'is_suppressed': "ALTER TABLE memory_chunks ADD COLUMN is_suppressed INTEGER NOT NULL DEFAULT 0",
        'suppressed_reason': "ALTER TABLE memory_chunks ADD COLUMN suppressed_reason TEXT NOT NULL DEFAULT ''",
    }
    for key, statement in wanted.items():
        if key not in existing:
            conn.execute(statement)


def ensure_memory_foundation() -> Path:
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    with sqlite_conn() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _ensure_memory_chunk_columns(conn)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_memory_chunks_pinned_suppressed ON memory_chunks(lane, is_pinned, is_suppressed)')
        conn.execute(
            'INSERT INTO memory_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            ('schema_version', str(SCHEMA_VERSION)),
        )
    return MEMORY_DB_PATH


def execute(statement: str, params: tuple[Any, ...] = ()) -> None:
    with sqlite_conn() as conn:
        conn.execute(statement, params)


def upsert_memory_chunks_sqlite(*, lane: str, collection_name: str, chunks: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0
    count = 0
    with sqlite_conn() as conn:
        for item in chunks:
            chunk_id = str(item.get('id') or '').strip()
            document = str(item.get('document') or '').strip()
            metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
            if not chunk_id or not document:
                continue
            conn.execute(
                '''
                INSERT INTO memory_chunks(
                    chunk_id, lane, collection_name, chunk_type, entity_type, entity_id,
                    scope_type, scope_id, project_id, campaign_id, source_ref, importance,
                    document, metadata_json, created_at, updated_at, is_deleted,
                    is_pinned, pin_note, is_suppressed, suppressed_reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '', 0, '')
                ON CONFLICT(chunk_id) DO UPDATE SET
                    lane=excluded.lane,
                    collection_name=excluded.collection_name,
                    chunk_type=excluded.chunk_type,
                    entity_type=excluded.entity_type,
                    entity_id=excluded.entity_id,
                    scope_type=excluded.scope_type,
                    scope_id=excluded.scope_id,
                    project_id=excluded.project_id,
                    campaign_id=excluded.campaign_id,
                    source_ref=excluded.source_ref,
                    importance=excluded.importance,
                    document=excluded.document,
                    metadata_json=excluded.metadata_json,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    is_deleted=0,
                    is_pinned=memory_chunks.is_pinned,
                    pin_note=memory_chunks.pin_note,
                    is_suppressed=memory_chunks.is_suppressed,
                    suppressed_reason=memory_chunks.suppressed_reason
                ''',
                (
                    chunk_id,
                    str(lane or '').strip(),
                    str(collection_name or '').strip(),
                    str(metadata.get('chunk_type') or '').strip(),
                    str(metadata.get('entity_type') or '').strip(),
                    str(metadata.get('entity_id') or '').strip(),
                    str(metadata.get('scope_type') or '').strip(),
                    str(metadata.get('scope_id') or '').strip(),
                    str(metadata.get('project_id') or '').strip(),
                    str(metadata.get('campaign_id') or '').strip(),
                    str(metadata.get('source_ref') or '').strip(),
                    float(metadata.get('importance') or 0.0),
                    document,
                    _json(metadata, '{}'),
                    str(metadata.get('created_at') or '').strip(),
                    str(metadata.get('updated_at') or metadata.get('created_at') or '').strip(),
                ),
            )
            count += 1
    return count


def delete_memory_chunks_for_entity_sqlite(*, lane: str, entity_id: str) -> int:
    clean_lane = str(lane or '').strip()
    clean_id = str(entity_id or '').strip()
    if not clean_lane or not clean_id:
        return 0
    with sqlite_conn() as conn:
        cursor = conn.execute('UPDATE memory_chunks SET is_deleted=1, updated_at=CURRENT_TIMESTAMP WHERE lane=? AND entity_id=?', (clean_lane, clean_id))
        return int(cursor.rowcount or 0)


def record_memory_write(*, write_log_id: str, lane: str, entity_type: str, entity_id: str, operation: str, source_ref: str = '', details: Any = None, created_at: str = '') -> None:
    execute(
        '''
        INSERT OR REPLACE INTO memory_write_log(
            write_log_id, lane, entity_type, entity_id, operation, source_ref, details_json, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            str(write_log_id or '').strip(),
            str(lane or '').strip(),
            str(entity_type or '').strip(),
            str(entity_id or '').strip(),
            str(operation or '').strip(),
            str(source_ref or '').strip(),
            _json(details, '{}'),
            str(created_at or '').strip(),
        ),
    )


def _loads_json(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if str(raw or '').strip() else default
    except Exception:
        return default


def fetch_memory_chunks(*, lane: str = '', scope_type: str = '', scope_id: str = '', entity_type: str = '', entity_id: str = '', project_id: str = '', campaign_id: str = '', chunk_type: str = '', include_deleted: bool = False, include_suppressed: bool = False, only_pinned: bool = False, q: str = '', limit: int = 20) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if lane:
        clauses.append('lane=?')
        params.append(str(lane or '').strip())
    if not include_deleted:
        clauses.append('is_deleted=0')
    if not include_suppressed:
        clauses.append('is_suppressed=0')
    if scope_type:
        clauses.append('scope_type=?')
        params.append(str(scope_type or '').strip())
    if scope_id:
        clauses.append('scope_id=?')
        params.append(str(scope_id or '').strip())
    if entity_type:
        clauses.append('entity_type=?')
        params.append(str(entity_type or '').strip())
    if entity_id:
        clauses.append('entity_id=?')
        params.append(str(entity_id or '').strip())
    if project_id:
        clauses.append('project_id=?')
        params.append(str(project_id or '').strip())
    if campaign_id:
        clauses.append('campaign_id=?')
        params.append(str(campaign_id or '').strip())
    if chunk_type:
        clauses.append('chunk_type=?')
        params.append(str(chunk_type or '').strip())
    if only_pinned:
        clauses.append('is_pinned=1')
    clean_q = str(q or '').strip()
    if clean_q:
        like = f'%{clean_q}%'
        clauses.append('(document LIKE ? OR source_ref LIKE ? OR entity_id LIKE ? OR scope_id LIKE ? OR chunk_type LIKE ?)')
        params.extend([like, like, like, like, like])
    sql = 'SELECT * FROM memory_chunks'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY is_pinned DESC, is_suppressed ASC, updated_at DESC, importance DESC, created_at DESC LIMIT ?'
    params.append(max(1, int(limit or 20)))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        for row in conn.execute(sql, tuple(params)):
            item = dict(row)
            item['metadata'] = _loads_json(item.pop('metadata_json', '{}'), {})
            rows.append(item)
    return rows


def fetch_summary_records(*, lane: str = '', scope_type: str = '', scope_id: str = '', limit: int = 20) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if lane:
        clauses.append('lane=?')
        params.append(str(lane or '').strip())
    if scope_type:
        clauses.append('scope_type=?')
        params.append(str(scope_type or '').strip())
    if scope_id:
        clauses.append('scope_id=?')
        params.append(str(scope_id or '').strip())
    sql = 'SELECT * FROM summary_records'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY updated_at DESC, created_at DESC LIMIT ?'
    params.append(max(1, int(limit or 20)))
    with sqlite_conn() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params))]


def fetch_memory_write_logs(*, lane: str = '', entity_type: str = '', entity_id: str = '', limit: int = 20) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if lane:
        clauses.append('lane=?')
        params.append(str(lane or '').strip())
    if entity_type:
        clauses.append('entity_type=?')
        params.append(str(entity_type or '').strip())
    if entity_id:
        clauses.append('entity_id=?')
        params.append(str(entity_id or '').strip())
    sql = 'SELECT * FROM memory_write_log'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY created_at DESC LIMIT ?'
    params.append(max(1, int(limit or 20)))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        for row in conn.execute(sql, tuple(params)):
            item = dict(row)
            item['details'] = _loads_json(item.pop('details_json', '{}'), {})
            rows.append(item)
    return rows


def mark_memory_chunk_ids_deleted(chunk_ids: list[str]) -> int:
    ids = [str(item or '').strip() for item in (chunk_ids or []) if str(item or '').strip()]
    if not ids:
        return 0
    placeholders = ','.join('?' for _ in ids)
    with sqlite_conn() as conn:
        cursor = conn.execute(f'UPDATE memory_chunks SET is_deleted=1, updated_at=CURRENT_TIMESTAMP WHERE chunk_id IN ({placeholders})', tuple(ids))
        return int(cursor.rowcount or 0)


def delete_summary_record_ids(summary_record_ids: list[str]) -> int:
    ids = [str(item or '').strip() for item in (summary_record_ids or []) if str(item or '').strip()]
    if not ids:
        return 0
    placeholders = ','.join('?' for _ in ids)
    with sqlite_conn() as conn:
        cursor = conn.execute(f'DELETE FROM summary_records WHERE summary_record_id IN ({placeholders})', tuple(ids))
        return int(cursor.rowcount or 0)


def get_memory_meta_value(key: str, default: str = '') -> str:
    clean_key = str(key or '').strip()
    if not clean_key:
        return str(default or '')
    with sqlite_conn() as conn:
        row = conn.execute('SELECT value FROM memory_meta WHERE key=?', (clean_key,)).fetchone()
        if not row:
            return str(default or '')
        return str(row['value'] or default or '')


def set_memory_meta_value(key: str, value: Any) -> str:
    clean_key = str(key or '').strip()
    clean_value = str(value or '').strip()
    if not clean_key:
        return clean_value
    execute('INSERT INTO memory_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (clean_key, clean_value))
    return clean_value


def fetch_memory_chunk_status_map(chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(item or '').strip() for item in (chunk_ids or []) if str(item or '').strip()]
    if not ids:
        return {}
    placeholders = ','.join('?' for _ in ids)
    out: dict[str, dict[str, Any]] = {}
    with sqlite_conn() as conn:
        for row in conn.execute(f'SELECT chunk_id, is_pinned, pin_note, is_suppressed, suppressed_reason, is_deleted FROM memory_chunks WHERE chunk_id IN ({placeholders})', tuple(ids)):
            out[str(row['chunk_id'] or '').strip()] = {
                'is_pinned': bool(row['is_pinned']),
                'pin_note': str(row['pin_note'] or '').strip(),
                'is_suppressed': bool(row['is_suppressed']),
                'suppressed_reason': str(row['suppressed_reason'] or '').strip(),
                'is_deleted': bool(row['is_deleted']),
            }
    return out


def update_memory_chunk_state(*, chunk_id: str, is_pinned: bool | None = None, pin_note: str | None = None, is_suppressed: bool | None = None, suppressed_reason: str | None = None) -> bool:
    clean_id = str(chunk_id or '').strip()
    if not clean_id:
        return False
    parts: list[str] = []
    params: list[Any] = []
    if is_pinned is not None:
        parts.append('is_pinned=?')
        params.append(1 if is_pinned else 0)
    if pin_note is not None:
        parts.append('pin_note=?')
        params.append(str(pin_note or '').strip())
    if is_suppressed is not None:
        parts.append('is_suppressed=?')
        params.append(1 if is_suppressed else 0)
    if suppressed_reason is not None:
        parts.append('suppressed_reason=?')
        params.append(str(suppressed_reason or '').strip())
    if not parts:
        return False
    parts.append('updated_at=CURRENT_TIMESTAMP')
    params.append(clean_id)
    with sqlite_conn() as conn:
        cursor = conn.execute(f"UPDATE memory_chunks SET {', '.join(parts)} WHERE chunk_id=?", tuple(params))
        return bool(cursor.rowcount or 0)


def fetch_memory_chunk_by_id(chunk_id: str) -> dict[str, Any] | None:
    clean_id = str(chunk_id or '').strip()
    if not clean_id:
        return None
    with sqlite_conn() as conn:
        row = conn.execute('SELECT * FROM memory_chunks WHERE chunk_id=?', (clean_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item['metadata'] = _loads_json(item.pop('metadata_json', '{}'), {})
        return item


def fetch_memory_admin_overview() -> dict[str, Any]:
    overview: dict[str, Any] = {
        'totals': {'all': 0, 'assistant': 0, 'roleplay': 0, 'pinned': 0, 'suppressed': 0, 'deleted': 0},
        'by_chunk_type': {},
        'by_lane_chunk_type': {},
    }
    with sqlite_conn() as conn:
        row = conn.execute(
            '''
            SELECT
                COUNT(*) AS all_count,
                SUM(CASE WHEN lane='assistant' AND is_deleted=0 THEN 1 ELSE 0 END) AS assistant_count,
                SUM(CASE WHEN lane='roleplay' AND is_deleted=0 THEN 1 ELSE 0 END) AS roleplay_count,
                SUM(CASE WHEN is_pinned=1 AND is_deleted=0 THEN 1 ELSE 0 END) AS pinned_count,
                SUM(CASE WHEN is_suppressed=1 AND is_deleted=0 THEN 1 ELSE 0 END) AS suppressed_count,
                SUM(CASE WHEN is_deleted=1 THEN 1 ELSE 0 END) AS deleted_count
            FROM memory_chunks
            '''
        ).fetchone()
        if row:
            overview['totals'] = {
                'all': int(row['all_count'] or 0),
                'assistant': int(row['assistant_count'] or 0),
                'roleplay': int(row['roleplay_count'] or 0),
                'pinned': int(row['pinned_count'] or 0),
                'suppressed': int(row['suppressed_count'] or 0),
                'deleted': int(row['deleted_count'] or 0),
            }
        for row in conn.execute('SELECT lane, chunk_type, COUNT(*) AS chunk_count FROM memory_chunks WHERE is_deleted=0 GROUP BY lane, chunk_type ORDER BY lane ASC, chunk_count DESC, chunk_type ASC'):
            lane = str(row['lane'] or '').strip() or 'unknown'
            chunk_type = str(row['chunk_type'] or '').strip() or 'unknown'
            count = int(row['chunk_count'] or 0)
            overview['by_chunk_type'][chunk_type] = int(overview['by_chunk_type'].get(chunk_type, 0)) + count
            lane_map = overview['by_lane_chunk_type'].setdefault(lane, {})
            lane_map[chunk_type] = count
    return overview


def update_memory_chunk_sandbox(*, chunk_id: str, memory_scope: str | None = None, project_id: str | None = None, visibility: str | None = None, bleed_policy: str | None = None, sandbox_policy: str | None = None) -> bool:
    """Update chunk sandbox metadata and matching indexed columns.

    This supports Memory Manager actions such as move to project/global,
    quarantine, or release from quarantine without deleting the source.
    """
    clean_id = str(chunk_id or '').strip()
    if not clean_id:
        return False
    with sqlite_conn() as conn:
        row = conn.execute('SELECT * FROM memory_chunks WHERE chunk_id=?', (clean_id,)).fetchone()
        if not row:
            return False
        metadata = _loads_json(row['metadata_json'] or '{}', {})
        metadata = metadata if isinstance(metadata, dict) else {}
        if memory_scope is not None:
            metadata['memory_scope'] = str(memory_scope or '').strip()
        if project_id is not None:
            metadata['memory_project_id'] = str(project_id or '').strip()
            metadata['project_id'] = str(project_id or '').strip()
        if visibility is not None:
            metadata['visibility'] = str(visibility or '').strip()
        if bleed_policy is not None:
            metadata['bleed_policy'] = str(bleed_policy or '').strip()
        if sandbox_policy is not None:
            metadata['sandbox_policy'] = str(sandbox_policy or '').strip()

        scope = str(metadata.get('memory_scope') or row['scope_type'] or '').strip()
        proj = str(metadata.get('memory_project_id') or metadata.get('project_id') or '').strip()
        if scope in {'global', 'profile', 'assistant_wide'}:
            scope_type = 'profile' if scope == 'profile' else 'global'
            scope_id = ''
            db_project_id = ''
            metadata['project_id'] = ''
            metadata['memory_project_id'] = ''
        elif scope in {'quarantine', 'review'}:
            scope_type = 'quarantine'
            scope_id = proj
            db_project_id = proj
        elif scope in {'session', 'thread'}:
            scope_type = 'session'
            scope_id = str(metadata.get('memory_session_id') or row['scope_id'] or '').strip()
            db_project_id = proj
        else:
            scope_type = 'project'
            scope_id = proj
            db_project_id = proj
        cursor = conn.execute(
            '''
            UPDATE memory_chunks
            SET scope_type=?, scope_id=?, project_id=?, metadata_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE chunk_id=?
            ''',
            (scope_type, scope_id, db_project_id, _json(metadata, '{}'), clean_id),
        )
        return bool(cursor.rowcount or 0)


def bulk_update_memory_chunk_sandbox(*, chunk_ids: list[str], memory_scope: str | None = None, project_id: str | None = None, visibility: str | None = None, bleed_policy: str | None = None, sandbox_policy: str | None = None) -> int:
    count = 0
    for chunk_id in chunk_ids or []:
        if update_memory_chunk_sandbox(
            chunk_id=str(chunk_id or '').strip(),
            memory_scope=memory_scope,
            project_id=project_id,
            visibility=visibility,
            bleed_policy=bleed_policy,
            sandbox_policy=sandbox_policy,
        ):
            count += 1
    return count
