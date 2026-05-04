from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import re
import sqlite3
from uuid import uuid4
from pathlib import Path
from typing import Any

from .memory_service.sqlite_store import MEMORY_DB_PATH, ensure_memory_foundation, sqlite_conn
from .memory_service.chroma_store import ROLEPLAY_V2_COLLECTION, delete_memory_chunks_for_scope, ensure_chroma_foundation, get_embedding_backend_status, query_memory, upsert_memory_chunks
from .storage_io import read_json_object
from .roleplay_v2_snapshot_store import normalize_memory_scope, normalize_promotion_scope

RP2_SQLITE_SCHEMA_VERSION = 2

RP2_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS rp2_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_entities (
        entity_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        display_label TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        source_container_id TEXT NOT NULL DEFAULT '',
        canon_status TEXT NOT NULL DEFAULT 'primary_canon',
        visibility TEXT NOT NULL DEFAULT 'author_private',
        record_status TEXT NOT NULL DEFAULT 'draft',
        tags_json TEXT NOT NULL DEFAULT '[]',
        tone_tags_json TEXT NOT NULL DEFAULT '[]',
        links_json TEXT NOT NULL DEFAULT '{}',
        fields_json TEXT NOT NULL DEFAULT '{}',
        memory_hints_json TEXT NOT NULL DEFAULT '{}',
        meta_json TEXT NOT NULL DEFAULT '{}',
        graph_json TEXT NOT NULL DEFAULT '{}',
        normalization_json TEXT NOT NULL DEFAULT '{}',
        source_json_path TEXT NOT NULL DEFAULT '',
        raw_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_entity_versions (
        version_snapshot_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL DEFAULT '',
        version_num INTEGER NOT NULL DEFAULT 1,
        source_json_path TEXT NOT NULL DEFAULT '',
        record_json TEXT NOT NULL DEFAULT '{}',
        graph_json TEXT NOT NULL DEFAULT '{}',
        normalization_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_edges (
        edge_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL DEFAULT '',
        source_kind TEXT NOT NULL DEFAULT '',
        family TEXT NOT NULL DEFAULT '',
        slot TEXT NOT NULL DEFAULT '',
        relation TEXT NOT NULL DEFAULT '',
        reverse_relation TEXT NOT NULL DEFAULT '',
        target_id TEXT NOT NULL DEFAULT '',
        target_kind TEXT NOT NULL DEFAULT '',
        target_kind_candidates_json TEXT NOT NULL DEFAULT '[]',
        cardinality TEXT NOT NULL DEFAULT 'one',
        status TEXT NOT NULL DEFAULT 'active',
        visibility TEXT NOT NULL DEFAULT 'public',
        source_mode TEXT NOT NULL DEFAULT 'manual',
        notes TEXT NOT NULL DEFAULT '',
        edge_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_relationship_state (
        relationship_state_id TEXT PRIMARY KEY,
        source_entity_id TEXT NOT NULL DEFAULT '',
        target_entity_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        bundle_id TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        relationship_label TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        trust_level REAL NOT NULL DEFAULT 0.5,
        tension_level REAL NOT NULL DEFAULT 0.0,
        drift_score REAL NOT NULL DEFAULT 0.0,
        carry_forward INTEGER NOT NULL DEFAULT 1,
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'sandbox',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        state_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_story_sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        output_preset TEXT NOT NULL DEFAULT 'roleplay',
        interaction_mode TEXT NOT NULL DEFAULT 'roleplay',
        current_entity_id TEXT NOT NULL DEFAULT '',
        current_checkpoint_id TEXT NOT NULL DEFAULT '',
        runtime_bundle_ref TEXT NOT NULL DEFAULT '',
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'sandbox',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        session_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_scene_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        focus_entity_id TEXT NOT NULL DEFAULT '',
        location_id TEXT NOT NULL DEFAULT '',
        unresolved_threads_json TEXT NOT NULL DEFAULT '[]',
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'sandbox',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        scene_state_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_memory_fragments (
        memory_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        builder_record_id TEXT NOT NULL DEFAULT '',
        canon_id TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        memory_type TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL DEFAULT '',
        salience REAL NOT NULL DEFAULT 0.0,
        tags_json TEXT NOT NULL DEFAULT '[]',
        world_id TEXT NOT NULL DEFAULT '',
        universe_id TEXT NOT NULL DEFAULT '',
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'source',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        scope_json TEXT NOT NULL DEFAULT '{}',
        fragment_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_shared_memories (
        shared_memory_id TEXT PRIMARY KEY,
        entity_a_id TEXT NOT NULL DEFAULT '',
        entity_b_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        builder_record_id TEXT NOT NULL DEFAULT '',
        canon_id TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL DEFAULT '',
        salience REAL NOT NULL DEFAULT 0.0,
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'source',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        memory_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_callback_anchors (
        callback_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        builder_record_id TEXT NOT NULL DEFAULT '',
        canon_id TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        anchor_text TEXT NOT NULL DEFAULT '',
        salience REAL NOT NULL DEFAULT 0.0,
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'source',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        callback_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_turn_summaries (
        turn_summary_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        turn_index INTEGER NOT NULL DEFAULT 0,
        summary TEXT NOT NULL DEFAULT '',
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'sandbox',
        summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_retrieval_traces (
        trace_id TEXT PRIMARY KEY,
        bundle_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL DEFAULT 'roleplay',
        source_scope TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL DEFAULT '',
        session_id TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL DEFAULT '',
        source_snapshot_id TEXT NOT NULL DEFAULT '',
        canon_snapshot_id TEXT NOT NULL DEFAULT '',
        sandbox_id TEXT NOT NULL DEFAULT '',
        storyline_id TEXT NOT NULL DEFAULT '',
        branch_id TEXT NOT NULL DEFAULT '',
        memory_scope TEXT NOT NULL DEFAULT 'sandbox',
        promotion_scope TEXT NOT NULL DEFAULT 'sandbox_only',
        query_text TEXT NOT NULL DEFAULT '',
        selected_ids_json TEXT NOT NULL DEFAULT '[]',
        trace_json TEXT NOT NULL DEFAULT '{}',
        packet_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_memory_recurrence (
        memory_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        bucket_key TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        last_selected_at TEXT NOT NULL DEFAULT '',
        cooldown_until TEXT NOT NULL DEFAULT '',
        selected_count INTEGER NOT NULL DEFAULT 0,
        recurrence_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp2_memory_controls (
        memory_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        is_pinned INTEGER NOT NULL DEFAULT 0,
        is_suppressed INTEGER NOT NULL DEFAULT 0,
        is_resolved INTEGER NOT NULL DEFAULT 0,
        cooldown_until TEXT NOT NULL DEFAULT '',
        control_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp2_entities_kind ON rp2_entities(kind)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp2_entities_source_container ON rp2_entities(source_container_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp2_edges_source ON rp2_edges(source_id, family, relation)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp2_edges_target ON rp2_edges(target_id, reverse_relation)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp2_entity_versions_entity ON rp2_entity_versions(entity_id, version_num DESC)
    """,
)

RP2_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    'rp2_relationship_state': {
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'session_id': "TEXT NOT NULL DEFAULT ''",
        'checkpoint_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'sandbox'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
    },
    'rp2_memory_fragments': {
        'project_id': "TEXT NOT NULL DEFAULT ''",
        'builder_record_id': "TEXT NOT NULL DEFAULT ''",
        'canon_id': "TEXT NOT NULL DEFAULT ''",
        'source_ref': "TEXT NOT NULL DEFAULT ''",
        'title': "TEXT NOT NULL DEFAULT ''",
        'summary': "TEXT NOT NULL DEFAULT ''",
        'text': "TEXT NOT NULL DEFAULT ''",
        'salience': 'REAL NOT NULL DEFAULT 0.0',
        'tags_json': "TEXT NOT NULL DEFAULT '[]'",
        'world_id': "TEXT NOT NULL DEFAULT ''",
        'universe_id': "TEXT NOT NULL DEFAULT ''",
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'session_id': "TEXT NOT NULL DEFAULT ''",
        'checkpoint_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'source'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
        'scope_json': "TEXT NOT NULL DEFAULT '{}'",
        'fragment_json': "TEXT NOT NULL DEFAULT '{}'",
    },
    'rp2_story_sessions': {
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'sandbox'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
    },
    'rp2_scene_checkpoints': {
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'sandbox'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
    },
    'rp2_shared_memories': {
        'project_id': "TEXT NOT NULL DEFAULT ''",
        'builder_record_id': "TEXT NOT NULL DEFAULT ''",
        'canon_id': "TEXT NOT NULL DEFAULT ''",
        'source_ref': "TEXT NOT NULL DEFAULT ''",
        'salience': 'REAL NOT NULL DEFAULT 0.0',
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'session_id': "TEXT NOT NULL DEFAULT ''",
        'checkpoint_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'source'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
    },
    'rp2_callback_anchors': {
        'project_id': "TEXT NOT NULL DEFAULT ''",
        'builder_record_id': "TEXT NOT NULL DEFAULT ''",
        'canon_id': "TEXT NOT NULL DEFAULT ''",
        'source_ref': "TEXT NOT NULL DEFAULT ''",
        'salience': 'REAL NOT NULL DEFAULT 0.0',
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'session_id': "TEXT NOT NULL DEFAULT ''",
        'checkpoint_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'source'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
    },
    'rp2_turn_summaries': {
        'bundle_id': "TEXT NOT NULL DEFAULT ''",
        'project_id': "TEXT NOT NULL DEFAULT ''",
        'entity_id': "TEXT NOT NULL DEFAULT ''",
        'mode': "TEXT NOT NULL DEFAULT 'roleplay'",
        'source_ref': "TEXT NOT NULL DEFAULT ''",
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'sandbox'",
    },
    'rp2_retrieval_traces': {
        'bundle_id': "TEXT NOT NULL DEFAULT ''",
        'project_id': "TEXT NOT NULL DEFAULT ''",
        'entity_id': "TEXT NOT NULL DEFAULT ''",
        'mode': "TEXT NOT NULL DEFAULT 'roleplay'",
        'source_scope': "TEXT NOT NULL DEFAULT ''",
        'source_id': "TEXT NOT NULL DEFAULT ''",
        'source_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'canon_snapshot_id': "TEXT NOT NULL DEFAULT ''",
        'sandbox_id': "TEXT NOT NULL DEFAULT ''",
        'storyline_id': "TEXT NOT NULL DEFAULT ''",
        'branch_id': "TEXT NOT NULL DEFAULT ''",
        'memory_scope': "TEXT NOT NULL DEFAULT 'sandbox'",
        'promotion_scope': "TEXT NOT NULL DEFAULT 'sandbox_only'",
        'packet_json': "TEXT NOT NULL DEFAULT '{}'",
    },
}

RP2_POST_MIGRATION_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_rp2_relationship_state_entities ON rp2_relationship_state(source_entity_id, target_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_relationship_state_scope ON rp2_relationship_state(storyline_id, session_id, branch_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_relationship_state_memory_scope ON rp2_relationship_state(memory_scope, promotion_scope, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_fragments_entity_type ON rp2_memory_fragments(entity_id, memory_type)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_fragments_source_ref ON rp2_memory_fragments(source_ref)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_fragments_builder_record ON rp2_memory_fragments(builder_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_fragments_canon ON rp2_memory_fragments(canon_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_shared_memories_source_ref ON rp2_shared_memories(source_ref)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_shared_memories_builder_record ON rp2_shared_memories(builder_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_callback_anchors_entity ON rp2_callback_anchors(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_callback_anchors_source_ref ON rp2_callback_anchors(source_ref)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_callback_anchors_builder_record ON rp2_callback_anchors(builder_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_turn_summaries_bundle ON rp2_turn_summaries(bundle_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_turn_summaries_entity ON rp2_turn_summaries(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_turn_summaries_source_ref ON rp2_turn_summaries(source_ref)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_retrieval_traces_bundle ON rp2_retrieval_traces(bundle_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_retrieval_traces_project ON rp2_retrieval_traces(project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_retrieval_traces_entity ON rp2_retrieval_traces(entity_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_recurrence_entity ON rp2_memory_recurrence(entity_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rp2_memory_controls_entity ON rp2_memory_controls(entity_id, updated_at DESC)",
)


def _json(value: Any, default: str = '{}') -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default), ensure_ascii=False)
    except Exception:
        return default


def _loads(value: Any, default: Any) -> Any:
    try:
        raw = str(value or '').strip()
        return json.loads(raw) if raw else default
    except Exception:
        return default



def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _clean(value: Any) -> str:
    return str(value or '').strip()



RP2_SCOPE_FILTER_FIELD_MAP: dict[str, str] = {
    'source_snapshot_id': 'source_snapshot_id',
    'canon_snapshot_id': 'canon_snapshot_id',
    'sandbox_id': 'sandbox_id',
    'storyline_id': 'storyline_id',
    'session_id': 'session_id',
    'checkpoint_id': 'checkpoint_id',
    'branch_id': 'branch_id',
    'memory_scope': 'memory_scope',
    'promotion_scope': 'promotion_scope',
}


RP2_SCOPE_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    'rp2_relationship_state': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_memory_fragments': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_shared_memories': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_callback_anchors': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_turn_summaries': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope'),
    'rp2_retrieval_traces': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'storyline_id', 'session_id', 'checkpoint_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_story_sessions': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'branch_id', 'memory_scope', 'promotion_scope'),
    'rp2_scene_checkpoints': ('source_snapshot_id', 'canon_snapshot_id', 'sandbox_id', 'branch_id', 'memory_scope', 'promotion_scope'),
}


def _scope_value(field_name: str, value: Any) -> str:
    if field_name == 'memory_scope':
        return normalize_memory_scope(value, 'sandbox')
    if field_name == 'promotion_scope':
        return normalize_promotion_scope(value, 'sandbox_only')
    return _clean(value)



def _scope_filters(*, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, str]:
    raw = {
        'source_snapshot_id': source_snapshot_id,
        'canon_snapshot_id': canon_snapshot_id,
        'sandbox_id': sandbox_id,
        'storyline_id': storyline_id,
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'branch_id': branch_id,
        'memory_scope': memory_scope,
        'promotion_scope': promotion_scope,
    }
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not _clean(value):
            continue
        normalized = _scope_value(key, value)
        if normalized:
            out[key] = normalized
    return out



def _append_scope_where(where_parts: list[str], params: list[Any], *, table_alias: str = '', scope_filters: dict[str, str] | None = None) -> None:
    filters = scope_filters if isinstance(scope_filters, dict) else {}
    prefix = f'{table_alias}.' if table_alias else ''
    for field_name in RP2_SCOPE_FILTER_FIELD_MAP:
        value = filters.get(field_name)
        if value:
            where_parts.append(f'{prefix}{field_name} = ?')
            params.append(value)



def _scope_column_status(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for table_name, required in RP2_SCOPE_REQUIRED_COLUMNS.items():
        columns = _table_columns(conn, table_name)
        missing = [column for column in required if column not in columns]
        out[table_name] = {
            'required_columns': list(required),
            'present_columns': sorted(columns),
            'missing_columns': missing,
            'ready': not missing,
        }
    return out




def _scalar_count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int((row['count'] if row else 0) or 0)


def _count_by_column(conn: sqlite3.Connection, *, table_name: str, column_name: str, where_sql: str = '', params: tuple[Any, ...] = ()) -> dict[str, int]:
    counts: dict[str, int] = {}
    sql = f"SELECT COALESCE(NULLIF(TRIM({column_name}), ''), '__empty__') AS bucket, COUNT(*) AS count FROM {table_name} {where_sql} GROUP BY bucket"
    for row in conn.execute(sql, params).fetchall():
        bucket = _clean(row['bucket']) or '__empty__'
        counts[bucket] = int(row['count'] or 0)
    return counts


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row['name'] or '').strip() for row in conn.execute(f'PRAGMA table_info({table_name})') if str(row['name'] or '').strip()}


def _ensure_table_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = _table_columns(conn, table_name)
    for column_name, column_sql in columns.items():
        if column_name not in existing:
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}')


def ensure_roleplay_v2_sqlite_backbone() -> Path:
    ensure_memory_foundation()
    with sqlite_conn() as conn:
        for statement in RP2_SCHEMA_STATEMENTS:
            conn.execute(statement)
        for table_name, columns in RP2_MIGRATION_COLUMNS.items():
            _ensure_table_columns(conn, table_name, columns)
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS rp2_entity_search USING fts5(entity_id UNINDEXED, label, display_label, summary, tags, search_text)"
            )
        except sqlite3.OperationalError:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rp2_entity_search(entity_id TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', display_label TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', search_text TEXT NOT NULL DEFAULT '')"
            )
        for statement in RP2_POST_MIGRATION_INDEXES:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO rp2_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ('schema_version', str(RP2_SQLITE_SCHEMA_VERSION)),
        )
    return MEMORY_DB_PATH


def _replace_entity_search_row(conn: sqlite3.Connection, *, record: dict[str, Any]) -> None:
    entity_id = _clean(record.get('id'))
    if not entity_id:
        return
    label = _clean(record.get('label'))
    display_label = _clean(record.get('display_label'))
    summary = _clean(record.get('summary'))
    tags = ' '.join(str(item or '').strip() for item in (record.get('tags') or []) if str(item or '').strip())
    search_text = ' \n'.join(part for part in [label, display_label, summary, tags] if part)
    conn.execute('DELETE FROM rp2_entity_search WHERE entity_id=?', (entity_id,))
    conn.execute(
        'INSERT INTO rp2_entity_search(entity_id, label, display_label, summary, tags, search_text) VALUES(?, ?, ?, ?, ?, ?)',
        (entity_id, label, display_label, summary, tags, search_text),
    )


def _next_entity_version(conn: sqlite3.Connection, entity_id: str) -> int:
    row = conn.execute('SELECT COALESCE(MAX(version_num), 0) AS max_version FROM rp2_entity_versions WHERE entity_id=?', (entity_id,)).fetchone()
    return int((row['max_version'] if row else 0) or 0) + 1


def _delete_scope_rows(conn: sqlite3.Connection, *, builder_record_id: str = '', canon_id: str = '', source_ref: str = '') -> str:
    if builder_record_id:
        conn.execute('DELETE FROM rp2_memory_fragments WHERE builder_record_id=?', (builder_record_id,))
        conn.execute('DELETE FROM rp2_shared_memories WHERE builder_record_id=?', (builder_record_id,))
        conn.execute('DELETE FROM rp2_callback_anchors WHERE builder_record_id=?', (builder_record_id,))
        return 'builder_record_id'
    if canon_id:
        conn.execute('DELETE FROM rp2_memory_fragments WHERE canon_id=?', (canon_id,))
        conn.execute('DELETE FROM rp2_shared_memories WHERE canon_id=?', (canon_id,))
        conn.execute('DELETE FROM rp2_callback_anchors WHERE canon_id=?', (canon_id,))
        return 'canon_id'
    if source_ref:
        conn.execute('DELETE FROM rp2_memory_fragments WHERE source_ref=?', (source_ref,))
        conn.execute('DELETE FROM rp2_shared_memories WHERE source_ref=?', (source_ref,))
        conn.execute('DELETE FROM rp2_callback_anchors WHERE source_ref=?', (source_ref,))
        return 'source_ref'
    return ''


def upsert_rp2_entity_record(*, record: dict[str, Any], source_json_path: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    entity_id = _clean(record.get('id'))
    if not entity_id:
        raise ValueError('entity record id is required for SQLite sync.')
    meta = record.get('meta') if isinstance(record.get('meta'), dict) else {}
    links = record.get('links') if isinstance(record.get('links'), dict) else {}
    graph = record.get('graph') if isinstance(record.get('graph'), dict) else {}
    normalization = record.get('normalization') if isinstance(record.get('normalization'), dict) else {}
    with sqlite_conn() as conn:
        version_num = _next_entity_version(conn, entity_id)
        conn.execute(
            '''
            INSERT INTO rp2_entities(
                entity_id, kind, label, display_label, summary, source_container_id,
                canon_status, visibility, record_status, tags_json, tone_tags_json,
                links_json, fields_json, memory_hints_json, meta_json, graph_json,
                normalization_json, source_json_path, raw_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                kind=excluded.kind,
                label=excluded.label,
                display_label=excluded.display_label,
                summary=excluded.summary,
                source_container_id=excluded.source_container_id,
                canon_status=excluded.canon_status,
                visibility=excluded.visibility,
                record_status=excluded.record_status,
                tags_json=excluded.tags_json,
                tone_tags_json=excluded.tone_tags_json,
                links_json=excluded.links_json,
                fields_json=excluded.fields_json,
                memory_hints_json=excluded.memory_hints_json,
                meta_json=excluded.meta_json,
                graph_json=excluded.graph_json,
                normalization_json=excluded.normalization_json,
                source_json_path=excluded.source_json_path,
                raw_json=excluded.raw_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            ''',
            (
                entity_id,
                _clean(record.get('kind')),
                _clean(record.get('label')),
                _clean(record.get('display_label')),
                _clean(record.get('summary')),
                _clean(links.get('source_container_id')),
                _clean(record.get('canon_status') or 'primary_canon'),
                _clean(record.get('visibility') or 'author_private'),
                _clean(meta.get('status') or 'draft'),
                _json(record.get('tags') or [], '[]'),
                _json(record.get('tone_tags') or [], '[]'),
                _json(links, '{}'),
                _json(record.get('fields') or {}, '{}'),
                _json(record.get('memory_hints') or {}, '{}'),
                _json(meta, '{}'),
                _json(graph, '{}'),
                _json(normalization, '{}'),
                _clean(source_json_path),
                _json(record, '{}'),
                _clean(meta.get('created_at')),
                _clean(meta.get('updated_at')),
            ),
        )
        snapshot_id = f'{entity_id}:v{version_num}'
        conn.execute(
            '''
            INSERT INTO rp2_entity_versions(version_snapshot_id, entity_id, version_num, source_json_path, record_json, graph_json, normalization_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                snapshot_id,
                entity_id,
                version_num,
                _clean(source_json_path),
                _json(record, '{}'),
                _json(graph, '{}'),
                _json(normalization, '{}'),
                _clean(meta.get('updated_at') or meta.get('created_at')),
            ),
        )
        conn.execute('DELETE FROM rp2_edges WHERE source_id=?', (entity_id,))
        edge_count = 0
        for edge in (graph.get('edges') or []):
            if not isinstance(edge, dict):
                continue
            conn.execute(
                '''
                INSERT INTO rp2_edges(
                    edge_id, source_id, source_kind, family, slot, relation, reverse_relation,
                    target_id, target_kind, target_kind_candidates_json, cardinality,
                    status, visibility, source_mode, notes, edge_json, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    source_kind=excluded.source_kind,
                    family=excluded.family,
                    slot=excluded.slot,
                    relation=excluded.relation,
                    reverse_relation=excluded.reverse_relation,
                    target_id=excluded.target_id,
                    target_kind=excluded.target_kind,
                    target_kind_candidates_json=excluded.target_kind_candidates_json,
                    cardinality=excluded.cardinality,
                    status=excluded.status,
                    visibility=excluded.visibility,
                    source_mode=excluded.source_mode,
                    notes=excluded.notes,
                    edge_json=excluded.edge_json,
                    updated_at=excluded.updated_at
                ''',
                (
                    _clean(edge.get('edge_id')),
                    _clean(edge.get('source_id')),
                    _clean(edge.get('source_kind')),
                    _clean(edge.get('family')),
                    _clean(edge.get('slot')),
                    _clean(edge.get('relation')),
                    _clean(edge.get('reverse_relation')),
                    _clean(edge.get('target_id')),
                    _clean(edge.get('target_kind')),
                    _json(edge.get('target_kind_candidates') or [], '[]'),
                    _clean(edge.get('cardinality') or 'one'),
                    _clean(edge.get('status') or 'active'),
                    _clean(edge.get('visibility') or 'public'),
                    _clean(edge.get('source_mode') or 'manual'),
                    _clean(edge.get('notes')),
                    _json(edge, '{}'),
                    _clean(meta.get('updated_at')),
                ),
            )
            edge_count += 1
        _replace_entity_search_row(conn, record=record)
    return {
        'ok': True,
        'db_path': str(MEMORY_DB_PATH),
        'entity_id': entity_id,
        'edge_count': edge_count,
        'version_num': version_num,
    }


def upsert_rp2_memory_outputs(
    *,
    memory_fragments: list[dict[str, Any]] | None = None,
    shared_memories: list[dict[str, Any]] | None = None,
    builder_record_id: str = '',
    canon_id: str = '',
    source_ref: str = '',
    prune_existing: bool = True,
) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    fragments = [row for row in (memory_fragments or []) if isinstance(row, dict)]
    shared_rows = [row for row in (shared_memories or []) if isinstance(row, dict)]
    clean_builder_record_id = _clean(builder_record_id)
    clean_canon_id = _clean(canon_id)
    clean_source_ref = _clean(source_ref) or _clean((fragments[0].get('source_ref') if fragments else '') or (shared_rows[0].get('source_ref') if shared_rows else ''))
    fragment_count = 0
    shared_count = 0
    callback_count = 0
    prune_scope = ''
    with sqlite_conn() as conn:
        if prune_existing:
            prune_scope = _delete_scope_rows(conn, builder_record_id=clean_builder_record_id, canon_id=clean_canon_id, source_ref=clean_source_ref)
        for row in fragments:
            extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
            meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
            row_builder_record_id = _clean(extra.get('builder_record_id') or clean_builder_record_id)
            row_canon_id = _clean(extra.get('canon_id') or clean_canon_id)
            row_source_ref = _clean(row.get('source_ref') or clean_source_ref)
            scene_ready = _clean(row.get('scene_ready_text'))
            canonical_text = _clean(row.get('canonical_text'))
            summary = scene_ready or canonical_text[:480]
            scope = {
                'chapter_ref': _clean(row.get('chapter_ref')),
                'scene_ref': _clean(row.get('scene_ref')),
                'canon_status': _clean(row.get('canon_status')),
                'confidence': row.get('confidence'),
                'relationship_target_ids': row.get('relationship_target_ids') or [],
                'emotional_valence': _clean(row.get('emotional_valence')),
                'status': _clean(meta.get('status')),
            }
            conn.execute(
                '''
                INSERT INTO rp2_memory_fragments(
                    memory_id, entity_id, project_id, builder_record_id, canon_id, source_ref,
                    memory_type, title, summary, text, salience, tags_json, world_id,
                    universe_id, source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id,
                    session_id, checkpoint_id, branch_id, memory_scope, promotion_scope,
                    scope_json, fragment_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    entity_id=excluded.entity_id,
                    project_id=excluded.project_id,
                    builder_record_id=excluded.builder_record_id,
                    canon_id=excluded.canon_id,
                    source_ref=excluded.source_ref,
                    memory_type=excluded.memory_type,
                    title=excluded.title,
                    summary=excluded.summary,
                    text=excluded.text,
                    salience=excluded.salience,
                    tags_json=excluded.tags_json,
                    world_id=excluded.world_id,
                    universe_id=excluded.universe_id,
                    source_snapshot_id=excluded.source_snapshot_id,
                    canon_snapshot_id=excluded.canon_snapshot_id,
                    sandbox_id=excluded.sandbox_id,
                    storyline_id=excluded.storyline_id,
                    session_id=excluded.session_id,
                    checkpoint_id=excluded.checkpoint_id,
                    branch_id=excluded.branch_id,
                    memory_scope=excluded.memory_scope,
                    promotion_scope=excluded.promotion_scope,
                    scope_json=excluded.scope_json,
                    fragment_json=excluded.fragment_json,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                ''',
                (
                    _clean(row.get('id')),
                    _clean(row.get('entity_id')),
                    _clean(extra.get('project_id')),
                    row_builder_record_id,
                    row_canon_id,
                    row_source_ref,
                    _clean(row.get('memory_type')),
                    _clean(row.get('title')),
                    summary,
                    canonical_text,
                    float(row.get('salience') or 0.0),
                    _json(row.get('tags') or [], '[]'),
                    _clean(row.get('world_id')),
                    _clean(row.get('universe_id')),
                    _clean(row.get('source_snapshot_id') or extra.get('source_snapshot_id')),
                    _clean(row.get('canon_snapshot_id') or extra.get('canon_snapshot_id')),
                    _clean(row.get('sandbox_id') or extra.get('sandbox_id')),
                    _clean(row.get('storyline_id') or extra.get('storyline_id')),
                    _clean(row.get('session_id') or extra.get('session_id')),
                    _clean(row.get('checkpoint_id') or extra.get('checkpoint_id')),
                    _clean(row.get('branch_id') or extra.get('branch_id')),
                    _clean(row.get('memory_scope') or extra.get('memory_scope') or 'source'),
                    _clean(row.get('promotion_scope') or extra.get('promotion_scope') or 'sandbox_only'),
                    _json(scope, '{}'),
                    _json(row, '{}'),
                    _clean(meta.get('created_at')),
                    _clean(meta.get('updated_at')),
                ),
            )
            fragment_count += 1
            if _clean(row.get('memory_type')) == 'callback_anchor':
                conn.execute(
                    '''
                    INSERT INTO rp2_callback_anchors(
                        callback_id, entity_id, project_id, builder_record_id, canon_id, source_ref,
                        label, anchor_text, salience, source_snapshot_id, canon_snapshot_id, sandbox_id,
                        storyline_id, session_id, checkpoint_id, branch_id, memory_scope, promotion_scope,
                        callback_json, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(callback_id) DO UPDATE SET
                        entity_id=excluded.entity_id,
                        project_id=excluded.project_id,
                        builder_record_id=excluded.builder_record_id,
                        canon_id=excluded.canon_id,
                        source_ref=excluded.source_ref,
                        label=excluded.label,
                        anchor_text=excluded.anchor_text,
                        salience=excluded.salience,
                        source_snapshot_id=excluded.source_snapshot_id,
                        canon_snapshot_id=excluded.canon_snapshot_id,
                        sandbox_id=excluded.sandbox_id,
                        storyline_id=excluded.storyline_id,
                        session_id=excluded.session_id,
                        checkpoint_id=excluded.checkpoint_id,
                        branch_id=excluded.branch_id,
                        memory_scope=excluded.memory_scope,
                        promotion_scope=excluded.promotion_scope,
                        callback_json=excluded.callback_json,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    ''',
                    (
                        _clean(row.get('id')),
                        _clean(row.get('entity_id')),
                        _clean(extra.get('project_id')),
                        row_builder_record_id,
                        row_canon_id,
                        row_source_ref,
                        _clean(row.get('title')),
                        summary,
                        float(row.get('salience') or 0.0),
                        _clean(row.get('source_snapshot_id') or extra.get('source_snapshot_id')),
                        _clean(row.get('canon_snapshot_id') or extra.get('canon_snapshot_id')),
                        _clean(row.get('sandbox_id') or extra.get('sandbox_id')),
                        _clean(row.get('storyline_id') or extra.get('storyline_id')),
                        _clean(row.get('session_id') or extra.get('session_id')),
                        _clean(row.get('checkpoint_id') or extra.get('checkpoint_id')),
                        _clean(row.get('branch_id') or extra.get('branch_id')),
                        _clean(row.get('memory_scope') or extra.get('memory_scope') or 'source'),
                        _clean(row.get('promotion_scope') or extra.get('promotion_scope') or 'sandbox_only'),
                        _json(row, '{}'),
                        _clean(meta.get('created_at')),
                        _clean(meta.get('updated_at')),
                    ),
                )
                callback_count += 1
        for row in shared_rows:
            participants = [str(item or '').strip() for item in (row.get('participant_ids') or []) if str(item or '').strip()]
            entity_a_id = participants[0] if participants else ''
            entity_b_id = participants[1] if len(participants) > 1 else ''
            extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
            meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
            conn.execute(
                '''
                INSERT INTO rp2_shared_memories(
                    shared_memory_id, entity_a_id, entity_b_id, project_id, builder_record_id, canon_id,
                    source_ref, label, text, salience, source_snapshot_id, canon_snapshot_id, sandbox_id,
                    storyline_id, session_id, checkpoint_id, branch_id, memory_scope, promotion_scope,
                    memory_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shared_memory_id) DO UPDATE SET
                    entity_a_id=excluded.entity_a_id,
                    entity_b_id=excluded.entity_b_id,
                    project_id=excluded.project_id,
                    builder_record_id=excluded.builder_record_id,
                    canon_id=excluded.canon_id,
                    source_ref=excluded.source_ref,
                    label=excluded.label,
                    text=excluded.text,
                    salience=excluded.salience,
                    source_snapshot_id=excluded.source_snapshot_id,
                    canon_snapshot_id=excluded.canon_snapshot_id,
                    sandbox_id=excluded.sandbox_id,
                    storyline_id=excluded.storyline_id,
                    session_id=excluded.session_id,
                    checkpoint_id=excluded.checkpoint_id,
                    branch_id=excluded.branch_id,
                    memory_scope=excluded.memory_scope,
                    promotion_scope=excluded.promotion_scope,
                    memory_json=excluded.memory_json,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                ''',
                (
                    _clean(row.get('id')),
                    entity_a_id,
                    entity_b_id,
                    _clean(extra.get('project_id')),
                    _clean(extra.get('builder_record_id') or clean_builder_record_id),
                    _clean(extra.get('canon_id') or clean_canon_id),
                    _clean(row.get('source_ref') or clean_source_ref),
                    _clean(row.get('title')),
                    _clean(row.get('summary')),
                    float(row.get('salience') or 0.0),
                    _clean(row.get('source_snapshot_id') or extra.get('source_snapshot_id')),
                    _clean(row.get('canon_snapshot_id') or extra.get('canon_snapshot_id')),
                    _clean(row.get('sandbox_id') or extra.get('sandbox_id')),
                    _clean(row.get('storyline_id') or extra.get('storyline_id')),
                    _clean(row.get('session_id') or extra.get('session_id')),
                    _clean(row.get('checkpoint_id') or extra.get('checkpoint_id')),
                    _clean(row.get('branch_id') or extra.get('branch_id')),
                    _clean(row.get('memory_scope') or extra.get('memory_scope') or 'source'),
                    _clean(row.get('promotion_scope') or extra.get('promotion_scope') or 'sandbox_only'),
                    _json(row, '{}'),
                    _clean(meta.get('created_at')),
                    _clean(meta.get('updated_at')),
                ),
            )
            shared_count += 1
    overview = fetch_rp2_sqlite_overview()
    return {
        'ok': True,
        'db_path': str(MEMORY_DB_PATH),
        'fragment_count': fragment_count,
        'shared_memory_count': shared_count,
        'callback_anchor_count': callback_count,
        'prune_scope': prune_scope,
        'builder_record_id': clean_builder_record_id,
        'canon_id': clean_canon_id,
        'source_ref': clean_source_ref,
        'overview': overview,
    }




def upsert_rp2_story_session_record(*, session: dict[str, Any]) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    if not isinstance(session, dict):
        raise ValueError('story session payload is required.')
    session_id = _clean(session.get('id'))
    if not session_id:
        raise ValueError('story session id is required for SQLite sync.')
    meta = session.get('meta') if isinstance(session.get('meta'), dict) else {}
    scene_state_seed = session.get('scene_state_seed') if isinstance(session.get('scene_state_seed'), dict) else {}
    cast_ids = scene_state_seed.get('cast_entity_ids') if isinstance(scene_state_seed.get('cast_entity_ids'), list) else []
    title = _clean(session.get('session_summary')) or _clean(scene_state_seed.get('scene_goal')) or f'Session {session_id}'
    with sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO rp2_story_sessions(
                session_id, project_id, title, output_preset, interaction_mode, current_entity_id,
                current_checkpoint_id, runtime_bundle_ref, source_snapshot_id, canon_snapshot_id,
                sandbox_id, branch_id, memory_scope, promotion_scope, session_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                project_id=excluded.project_id,
                title=excluded.title,
                output_preset=excluded.output_preset,
                interaction_mode=excluded.interaction_mode,
                current_entity_id=excluded.current_entity_id,
                current_checkpoint_id=excluded.current_checkpoint_id,
                runtime_bundle_ref=excluded.runtime_bundle_ref,
                source_snapshot_id=excluded.source_snapshot_id,
                canon_snapshot_id=excluded.canon_snapshot_id,
                sandbox_id=excluded.sandbox_id,
                branch_id=excluded.branch_id,
                memory_scope=excluded.memory_scope,
                promotion_scope=excluded.promotion_scope,
                session_json=excluded.session_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                session_id,
                _clean(session.get('project_id')),
                title,
                _clean(session.get('output_preset') or 'roleplay'),
                _clean(session.get('interaction_mode') or 'roleplay'),
                _clean((cast_ids[0] if cast_ids else '') or scene_state_seed.get('active_entity_id')),
                _clean(session.get('active_checkpoint_id')),
                _clean(session.get('latest_runtime_bundle_id') or session.get('seed_runtime_bundle_id')),
                _clean(session.get('source_snapshot_id')),
                _clean(session.get('canon_snapshot_id')),
                _clean(session.get('sandbox_id')),
                _clean(session.get('branch_id')),
                _clean(session.get('memory_scope') or 'sandbox'),
                _clean(session.get('promotion_scope') or 'sandbox_only'),
                _json(session, '{}'),
                _clean(meta.get('created_at')),
                _clean(meta.get('updated_at')),
            ),
        )
    return {'ok': True, 'session_id': session_id, 'db_path': str(MEMORY_DB_PATH)}


def upsert_rp2_scene_checkpoint_record(*, checkpoint: dict[str, Any]) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    if not isinstance(checkpoint, dict):
        raise ValueError('scene checkpoint payload is required.')
    checkpoint_id = _clean(checkpoint.get('id'))
    if not checkpoint_id:
        raise ValueError('scene checkpoint id is required for SQLite sync.')
    meta = checkpoint.get('meta') if isinstance(checkpoint.get('meta'), dict) else {}
    scene_state = checkpoint.get('scene_state') if isinstance(checkpoint.get('scene_state'), dict) else {}
    continuity_payload = checkpoint.get('continuity_payload') if isinstance(checkpoint.get('continuity_payload'), dict) else {}
    selected_entity_ids = checkpoint.get('selected_entity_ids') if isinstance(checkpoint.get('selected_entity_ids'), list) else []
    unresolved_threads = continuity_payload.get('resume_unresolved_thread_ids') if isinstance(continuity_payload.get('resume_unresolved_thread_ids'), list) else checkpoint.get('selected_memory_ids') or []
    with sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO rp2_scene_checkpoints(
                checkpoint_id, session_id, label, focus_entity_id, location_id, unresolved_threads_json,
                source_snapshot_id, canon_snapshot_id, sandbox_id, branch_id, memory_scope, promotion_scope,
                scene_state_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(checkpoint_id) DO UPDATE SET
                session_id=excluded.session_id,
                label=excluded.label,
                focus_entity_id=excluded.focus_entity_id,
                location_id=excluded.location_id,
                unresolved_threads_json=excluded.unresolved_threads_json,
                source_snapshot_id=excluded.source_snapshot_id,
                canon_snapshot_id=excluded.canon_snapshot_id,
                sandbox_id=excluded.sandbox_id,
                branch_id=excluded.branch_id,
                memory_scope=excluded.memory_scope,
                promotion_scope=excluded.promotion_scope,
                scene_state_json=excluded.scene_state_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                checkpoint_id,
                _clean(checkpoint.get('session_id')),
                _clean(checkpoint.get('title') or checkpoint.get('summary') or checkpoint_id),
                _clean((selected_entity_ids[0] if selected_entity_ids else '') or scene_state.get('active_entity_id')),
                _clean(scene_state.get('active_location_id') or scene_state.get('location_id')),
                _json(unresolved_threads, '[]'),
                _clean(checkpoint.get('source_snapshot_id')),
                _clean(checkpoint.get('canon_snapshot_id')),
                _clean(checkpoint.get('sandbox_id')),
                _clean(checkpoint.get('branch_id')),
                _clean(checkpoint.get('memory_scope') or 'sandbox'),
                _clean(checkpoint.get('promotion_scope') or 'sandbox_only'),
                _json({'scene_state': scene_state, 'continuity_payload': continuity_payload, 'checkpoint': checkpoint}, '{}'),
                _clean(meta.get('created_at')),
                _clean(meta.get('updated_at')),
            ),
        )
    return {'ok': True, 'checkpoint_id': checkpoint_id, 'db_path': str(MEMORY_DB_PATH)}

def persist_rp2_turn_summary(*, turn_summary_id: str = '', session_id: str = '', checkpoint_id: str = '', bundle_id: str = '', project_id: str = '', entity_id: str = '', mode: str = 'roleplay', source_ref: str = '', turn_index: int = 0, summary: str = '', summary_payload: dict[str, Any] | None = None, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_id = _clean(turn_summary_id) or f"turnsum_{uuid4().hex[:12]}"
    payload = deepcopy(summary_payload) if isinstance(summary_payload, dict) else {}
    now = _utc_iso()
    clean_summary = _clean(summary)
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope or 'sandbox',
    )
    with sqlite_conn() as conn:
        conn.execute(
            '''
            INSERT INTO rp2_turn_summaries(
                turn_summary_id, session_id, checkpoint_id, bundle_id, project_id, entity_id, mode,
                source_ref, turn_index, summary, source_snapshot_id, canon_snapshot_id, sandbox_id,
                storyline_id, branch_id, memory_scope, summary_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(turn_summary_id) DO UPDATE SET
                session_id=excluded.session_id,
                checkpoint_id=excluded.checkpoint_id,
                bundle_id=excluded.bundle_id,
                project_id=excluded.project_id,
                entity_id=excluded.entity_id,
                mode=excluded.mode,
                source_ref=excluded.source_ref,
                turn_index=excluded.turn_index,
                summary=excluded.summary,
                source_snapshot_id=excluded.source_snapshot_id,
                canon_snapshot_id=excluded.canon_snapshot_id,
                sandbox_id=excluded.sandbox_id,
                storyline_id=excluded.storyline_id,
                branch_id=excluded.branch_id,
                memory_scope=excluded.memory_scope,
                summary_json=excluded.summary_json,
                updated_at=excluded.updated_at
            ''',
            (
                clean_id,
                _clean(session_id),
                _clean(checkpoint_id),
                _clean(bundle_id),
                _clean(project_id),
                _clean(entity_id),
                _clean(mode) or 'roleplay',
                _clean(source_ref),
                max(0, int(turn_index or 0)),
                clean_summary,
                scope_filters.get('source_snapshot_id', ''),
                scope_filters.get('canon_snapshot_id', ''),
                scope_filters.get('sandbox_id', ''),
                scope_filters.get('storyline_id', ''),
                scope_filters.get('branch_id', ''),
                scope_filters.get('memory_scope', normalize_memory_scope('sandbox', 'sandbox')),
                _json(payload, '{}'),
                _clean(payload.get('created_at')) or now,
                now,
            ),
        )
    return {
        'ok': True,
        'turn_summary_id': clean_id,
        'summary': clean_summary,
        'db_path': str(MEMORY_DB_PATH),
    }


def persist_rp2_relationship_state(*, relationship_state_id: str = '', source_entity_id: str = '', target_entity_id: str = '', project_id: str = '', bundle_id: str = '', source_ref: str = '', relationship_label: str = '', summary: str = '', trust_level: float = 0.5, tension_level: float = 0.0, drift_score: float = 0.0, carry_forward: bool = True, state_payload: dict[str, Any] | None = None, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox', promotion_scope: str = 'sandbox_only') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_id = _clean(relationship_state_id) or f"relstate_{uuid4().hex[:12]}"
    payload = deepcopy(state_payload) if isinstance(state_payload, dict) else {}
    now = _utc_iso()
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope or 'sandbox',
        promotion_scope=promotion_scope or 'sandbox_only',
    )
    with sqlite_conn() as conn:
        conn.execute(
            '''
            INSERT INTO rp2_relationship_state(
                relationship_state_id, source_entity_id, target_entity_id, project_id, bundle_id, source_ref,
                relationship_label, summary, trust_level, tension_level, drift_score, carry_forward,
                source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                branch_id, memory_scope, promotion_scope, state_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relationship_state_id) DO UPDATE SET
                source_entity_id=excluded.source_entity_id,
                target_entity_id=excluded.target_entity_id,
                project_id=excluded.project_id,
                bundle_id=excluded.bundle_id,
                source_ref=excluded.source_ref,
                relationship_label=excluded.relationship_label,
                summary=excluded.summary,
                trust_level=excluded.trust_level,
                tension_level=excluded.tension_level,
                drift_score=excluded.drift_score,
                carry_forward=excluded.carry_forward,
                source_snapshot_id=excluded.source_snapshot_id,
                canon_snapshot_id=excluded.canon_snapshot_id,
                sandbox_id=excluded.sandbox_id,
                storyline_id=excluded.storyline_id,
                session_id=excluded.session_id,
                checkpoint_id=excluded.checkpoint_id,
                branch_id=excluded.branch_id,
                memory_scope=excluded.memory_scope,
                promotion_scope=excluded.promotion_scope,
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            ''',
            (
                clean_id,
                _clean(source_entity_id),
                _clean(target_entity_id),
                _clean(project_id),
                _clean(bundle_id),
                _clean(source_ref),
                _clean(relationship_label),
                _clean(summary),
                float(trust_level or 0.0),
                float(tension_level or 0.0),
                float(drift_score or 0.0),
                1 if carry_forward else 0,
                scope_filters.get('source_snapshot_id', ''),
                scope_filters.get('canon_snapshot_id', ''),
                scope_filters.get('sandbox_id', ''),
                scope_filters.get('storyline_id', ''),
                scope_filters.get('session_id', ''),
                scope_filters.get('checkpoint_id', ''),
                scope_filters.get('branch_id', ''),
                scope_filters.get('memory_scope', normalize_memory_scope('sandbox', 'sandbox')),
                scope_filters.get('promotion_scope', normalize_promotion_scope('sandbox_only', 'sandbox_only')),
                _json(payload, '{}'),
                _clean(payload.get('created_at')) or now,
                now,
            ),
        )
    return {'ok': True, 'relationship_state_id': clean_id, 'db_path': str(MEMORY_DB_PATH)}


def fetch_rp2_relationship_state_rows(*, entity_id: str = '', project_id: str = '', limit: int = 6, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_project_id = _clean(project_id)
    where_parts: list[str] = []
    params: list[Any] = []
    if clean_project_id:
        where_parts.append('project_id = ?')
        params.append(clean_project_id)
    if clean_entity_id:
        where_parts.append('(source_entity_id = ? OR target_entity_id = ?)')
        params.extend([clean_entity_id, clean_entity_id])
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    _append_scope_where(where_parts, params, scope_filters=scope_filters)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
    sql = f'''
        SELECT relationship_state_id, source_entity_id, target_entity_id, project_id, bundle_id, source_ref,
               relationship_label, summary, trust_level, tension_level, drift_score, carry_forward,
               source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
               branch_id, memory_scope, promotion_scope, state_json, created_at, updated_at
        FROM rp2_relationship_state
        {where_sql}
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT ?
    '''
    params.append(max(1, min(int(limit or 6), 40)))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        for row in conn.execute(sql, params).fetchall():
            payload = _loads(row['state_json'], {}) if row['state_json'] else {}
            rows.append({
                'relationship_state_id': _clean(row['relationship_state_id']),
                'source_entity_id': _clean(row['source_entity_id']),
                'target_entity_id': _clean(row['target_entity_id']),
                'project_id': _clean(row['project_id']),
                'bundle_id': _clean(row['bundle_id']),
                'source_ref': _clean(row['source_ref']),
                'relationship_label': _clean(row['relationship_label']),
                'summary': _clean(row['summary']),
                'trust_level': float(row['trust_level'] or 0.0),
                'tension_level': float(row['tension_level'] or 0.0),
                'drift_score': float(row['drift_score'] or 0.0),
                'carry_forward': bool(int(row['carry_forward'] or 0)),
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']),
                'promotion_scope': _clean(row['promotion_scope']),
                'state_payload': payload if isinstance(payload, dict) else {},
                'created_at': _clean(row['created_at']),
                'updated_at': _clean(row['updated_at']),
            })
    return {
        'ok': True,
        'rows': rows,
        'count': len(rows),
        'entity_id': clean_entity_id,
        'project_id': clean_project_id,
        'scope_filters': scope_filters,
    }


def fetch_rp2_sqlite_overview() -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    with sqlite_conn() as conn:
        schema_row = conn.execute("SELECT value FROM rp2_meta WHERE key='schema_version'").fetchone()
        entities = conn.execute('SELECT COUNT(*) AS count FROM rp2_entities').fetchone()
        edges = conn.execute('SELECT COUNT(*) AS count FROM rp2_edges').fetchone()
        relationship_state = conn.execute('SELECT COUNT(*) AS count FROM rp2_relationship_state').fetchone()
        versions = conn.execute('SELECT COUNT(*) AS count FROM rp2_entity_versions').fetchone()
        fragments = conn.execute('SELECT COUNT(*) AS count FROM rp2_memory_fragments').fetchone()
        shared = conn.execute('SELECT COUNT(*) AS count FROM rp2_shared_memories').fetchone()
        callbacks = conn.execute('SELECT COUNT(*) AS count FROM rp2_callback_anchors').fetchone()
        turn_summaries = conn.execute('SELECT COUNT(*) AS count FROM rp2_turn_summaries').fetchone()
        traces = conn.execute('SELECT COUNT(*) AS count FROM rp2_retrieval_traces').fetchone()
        recurrence = conn.execute('SELECT COUNT(*) AS count FROM rp2_memory_recurrence').fetchone()
        controls = conn.execute('SELECT COUNT(*) AS count FROM rp2_memory_controls').fetchone()
        sessions = conn.execute('SELECT COUNT(*) AS count FROM rp2_story_sessions').fetchone()
        checkpoints = conn.execute('SELECT COUNT(*) AS count FROM rp2_scene_checkpoints').fetchone()
        scope_columns = _scope_column_status(conn)
        scope_inventory = {
            'memory_scope': {
                'relationship_state': _count_by_column(conn, table_name='rp2_relationship_state', column_name='memory_scope'),
                'memory_fragments': _count_by_column(conn, table_name='rp2_memory_fragments', column_name='memory_scope'),
                'shared_memories': _count_by_column(conn, table_name='rp2_shared_memories', column_name='memory_scope'),
                'callback_anchors': _count_by_column(conn, table_name='rp2_callback_anchors', column_name='memory_scope'),
                'turn_summaries': _count_by_column(conn, table_name='rp2_turn_summaries', column_name='memory_scope'),
                'retrieval_traces': _count_by_column(conn, table_name='rp2_retrieval_traces', column_name='memory_scope'),
                'story_sessions': _count_by_column(conn, table_name='rp2_story_sessions', column_name='memory_scope'),
                'scene_checkpoints': _count_by_column(conn, table_name='rp2_scene_checkpoints', column_name='memory_scope'),
            },
            'promotion_scope': {
                'relationship_state': _count_by_column(conn, table_name='rp2_relationship_state', column_name='promotion_scope'),
                'memory_fragments': _count_by_column(conn, table_name='rp2_memory_fragments', column_name='promotion_scope'),
                'shared_memories': _count_by_column(conn, table_name='rp2_shared_memories', column_name='promotion_scope'),
                'callback_anchors': _count_by_column(conn, table_name='rp2_callback_anchors', column_name='promotion_scope'),
                'retrieval_traces': _count_by_column(conn, table_name='rp2_retrieval_traces', column_name='promotion_scope'),
                'story_sessions': _count_by_column(conn, table_name='rp2_story_sessions', column_name='promotion_scope'),
                'scene_checkpoints': _count_by_column(conn, table_name='rp2_scene_checkpoints', column_name='promotion_scope'),
            },
        }
        scope_presence = {
            'relationship_state_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_relationship_state WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
            'memory_fragment_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_memory_fragments WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
            'shared_memory_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_shared_memories WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
            'callback_anchor_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_callback_anchors WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
            'turn_summary_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_turn_summaries WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
            'retrieval_trace_scoped_rows': _scalar_count(conn, "SELECT COUNT(*) AS count FROM rp2_retrieval_traces WHERE sandbox_id <> '' OR storyline_id <> '' OR session_id <> '' OR source_snapshot_id <> ''"),
        }
        return {
            'ok': True,
            'db_path': str(MEMORY_DB_PATH),
            'schema_version': int(_clean(schema_row['value']) or RP2_SQLITE_SCHEMA_VERSION) if schema_row else RP2_SQLITE_SCHEMA_VERSION,
            'entity_count': int((entities['count'] if entities else 0) or 0),
            'edge_count': int((edges['count'] if edges else 0) or 0),
            'relationship_state_count': int((relationship_state['count'] if relationship_state else 0) or 0),
            'version_count': int((versions['count'] if versions else 0) or 0),
            'memory_fragment_count': int((fragments['count'] if fragments else 0) or 0),
            'shared_memory_count': int((shared['count'] if shared else 0) or 0),
            'callback_anchor_count': int((callbacks['count'] if callbacks else 0) or 0),
            'turn_summary_count': int((turn_summaries['count'] if turn_summaries else 0) or 0),
            'retrieval_trace_count': int((traces['count'] if traces else 0) or 0),
            'recurrence_count': int((recurrence['count'] if recurrence else 0) or 0),
            'control_count': int((controls['count'] if controls else 0) or 0),
            'story_session_count': int((sessions['count'] if sessions else 0) or 0),
            'scene_checkpoint_count': int((checkpoints['count'] if checkpoints else 0) or 0),
            'scope_columns': scope_columns,
            'scope_inventory': scope_inventory,
            'scope_presence': scope_presence,
        }



def _iso_to_dt(value: Any) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except Exception:
        return None


def fetch_rp2_recurrence_map(*, project_id: str = '', entity_id: str = '') -> dict[str, dict[str, Any]]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    where_parts: list[str] = []
    params: list[Any] = []
    if clean_project_id:
        where_parts.append('project_id=?')
        params.append(clean_project_id)
    if clean_entity_id:
        where_parts.append('entity_id=?')
        params.append(clean_entity_id)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
    out: dict[str, dict[str, Any]] = {}
    with sqlite_conn() as conn:
        sql = f"SELECT memory_id, project_id, entity_id, bucket_key, source_ref, last_selected_at, cooldown_until, selected_count, recurrence_json, updated_at FROM rp2_memory_recurrence {where_sql}"
        for row in conn.execute(sql, tuple(params)).fetchall():
            out[_clean(row['memory_id'])] = {
                'memory_id': _clean(row['memory_id']),
                'project_id': _clean(row['project_id']),
                'entity_id': _clean(row['entity_id']),
                'bucket_key': _clean(row['bucket_key']),
                'source_ref': _clean(row['source_ref']),
                'last_selected_at': _clean(row['last_selected_at']),
                'cooldown_until': _clean(row['cooldown_until']),
                'selected_count': int(row['selected_count'] or 0),
                'recurrence_payload': _loads(row['recurrence_json'], {}) if row['recurrence_json'] else {},
                'updated_at': _clean(row['updated_at']),
            }
    return out


def persist_rp2_recurrence_rows(*, project_id: str = '', entity_id: str = '', mode: str = 'roleplay', selected_rows_by_bucket: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    rows_by_bucket = selected_rows_by_bucket if isinstance(selected_rows_by_bucket, dict) else {}
    existing = fetch_rp2_recurrence_map(project_id=clean_project_id, entity_id=clean_entity_id)
    updated = 0
    now = datetime.now(timezone.utc)
    with sqlite_conn() as conn:
        for bucket_key, rows in rows_by_bucket.items():
            for row in rows or []:
                memory_id = _clean(row.get('id'))
                if not memory_id:
                    continue
                current = existing.get(memory_id, {})
                selected_count = int(current.get('selected_count') or 0) + 1
                cooldown_minutes = min(180, 15 + (selected_count * 10))
                cooldown_until = (now + timedelta(minutes=cooldown_minutes)).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
                recurrence_payload = {
                    'mode': _clean(mode) or 'roleplay',
                    'source_backend': _clean(row.get('source_backend')),
                    'title': _clean(row.get('title')),
                    'recovery_tags': list(row.get('recovery_tags') or []),
                    'selected_count': selected_count,
                }
                conn.execute(
                    """
                    INSERT OR REPLACE INTO rp2_memory_recurrence (
                        memory_id, project_id, entity_id, bucket_key, source_ref,
                        last_selected_at, cooldown_until, selected_count, recurrence_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        clean_project_id,
                        clean_entity_id,
                        _clean(bucket_key),
                        _clean(row.get('source_ref')),
                        now.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
                        cooldown_until,
                        selected_count,
                        _json(recurrence_payload),
                        now.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
                    ),
                )
                updated += 1
    return {'ok': True, 'updated': updated, 'project_id': clean_project_id, 'entity_id': clean_entity_id}

def fetch_rp2_memory_control_map(*, project_id: str = '', entity_id: str = '') -> dict[str, dict[str, Any]]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    where_parts: list[str] = []
    params: list[Any] = []
    if clean_project_id:
        where_parts.append('project_id=?')
        params.append(clean_project_id)
    if clean_entity_id:
        where_parts.append('entity_id=?')
        params.append(clean_entity_id)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
    out: dict[str, dict[str, Any]] = {}
    with sqlite_conn() as conn:
        sql = f"SELECT memory_id, project_id, entity_id, is_pinned, is_suppressed, is_resolved, cooldown_until, control_json, updated_at FROM rp2_memory_controls {where_sql}"
        for row in conn.execute(sql, tuple(params)).fetchall():
            out[_clean(row['memory_id'])] = {
                'memory_id': _clean(row['memory_id']),
                'project_id': _clean(row['project_id']),
                'entity_id': _clean(row['entity_id']),
                'is_pinned': bool(int(row['is_pinned'] or 0)),
                'is_suppressed': bool(int(row['is_suppressed'] or 0)),
                'is_resolved': bool(int(row['is_resolved'] or 0)),
                'cooldown_until': _clean(row['cooldown_until']),
                'control_payload': _loads(row['control_json'], {}) if row['control_json'] else {},
                'updated_at': _clean(row['updated_at']),
            }
    return out


def set_rp2_memory_control(*, memory_id: str, project_id: str = '', entity_id: str = '', action: str = 'pin', cooldown_minutes: int = 60) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_memory_id = _clean(memory_id)
    if not clean_memory_id:
        raise ValueError('memory_id is required.')
    clean_action = _clean(action).lower() or 'pin'
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    current = fetch_rp2_memory_control_map(project_id=_clean(project_id), entity_id=_clean(entity_id)).get(clean_memory_id, {})
    row = {
        'is_pinned': bool(current.get('is_pinned')),
        'is_suppressed': bool(current.get('is_suppressed')),
        'is_resolved': bool(current.get('is_resolved')),
        'cooldown_until': _clean(current.get('cooldown_until')),
    }
    if clean_action == 'pin':
        row['is_pinned'] = True
        row['is_suppressed'] = False
    elif clean_action == 'suppress':
        row['is_suppressed'] = True
        row['is_pinned'] = False
    elif clean_action == 'resolve':
        row['is_resolved'] = True
    elif clean_action == 'cooldown':
        row['cooldown_until'] = (datetime.now(timezone.utc) + timedelta(minutes=max(1, int(cooldown_minutes or 60)))).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    elif clean_action == 'clear':
        row = {'is_pinned': False, 'is_suppressed': False, 'is_resolved': False, 'cooldown_until': ''}
    payload = {'action': clean_action, 'cooldown_minutes': int(cooldown_minutes or 0), 'updated_at': now}
    with sqlite_conn() as conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO rp2_memory_controls (
                memory_id, project_id, entity_id, is_pinned, is_suppressed, is_resolved, cooldown_until, control_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                clean_memory_id,
                _clean(project_id),
                _clean(entity_id),
                1 if row['is_pinned'] else 0,
                1 if row['is_suppressed'] else 0,
                1 if row['is_resolved'] else 0,
                _clean(row['cooldown_until']),
                _json(payload),
                now,
            ),
        )
    return {'ok': True, 'memory_id': clean_memory_id, 'project_id': _clean(project_id), 'entity_id': _clean(entity_id), 'action': clean_action, 'control': {**row, 'control_payload': payload}}



def persist_rp2_retrieval_trace(*, bundle_id: str = '', project_id: str = '', entity_id: str = '', mode: str = 'roleplay', source_scope: str = '', source_id: str = '', query_text: str = '', selected_ids: list[str] | None = None, trace: dict[str, Any] | None = None, packet: dict[str, Any] | None = None, session_id: str = '', checkpoint_id: str = '', source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', branch_id: str = '', memory_scope: str = 'sandbox', promotion_scope: str = 'sandbox_only') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_bundle_id = _clean(bundle_id)
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_mode = _clean(mode) or 'roleplay'
    clean_source_scope = _clean(source_scope)
    clean_source_id = _clean(source_id)
    clean_query_text = _clean(query_text)
    clean_session_id = _clean(session_id)
    clean_checkpoint_id = _clean(checkpoint_id)
    clean_selected_ids = [str(item or '').strip() for item in (selected_ids or []) if str(item or '').strip()]
    clean_trace = trace if isinstance(trace, dict) else {}
    clean_packet = packet if isinstance(packet, dict) else {}
    trace_basis = clean_bundle_id or clean_query_text or clean_entity_id or clean_project_id or 'trace'
    trace_basis_slug = re.sub(r'[^a-z0-9_-]+', '-', str(trace_basis or '').lower()).strip('-') or 'trace'
    trace_id = _clean((clean_trace.get('trace_id') if isinstance(clean_trace, dict) else '') or '') or _clean(f"trace_{trace_basis_slug}_{len(clean_selected_ids)}")
    if not trace_id.startswith('trace_'):
        trace_id = f'trace_{trace_id}'
    created_at = _clean((clean_trace.get('created_at') if isinstance(clean_trace, dict) else '') or '')
    created_at = created_at or _clean((clean_packet.get('working_memory') or {}).get('retrieved_at') if isinstance(clean_packet.get('working_memory'), dict) else '')
    with sqlite_conn() as conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO rp2_retrieval_traces (
                trace_id, bundle_id, project_id, entity_id, mode, source_scope, source_id,
                session_id, checkpoint_id, source_snapshot_id, canon_snapshot_id, sandbox_id,
                storyline_id, branch_id, memory_scope, promotion_scope,
                query_text, selected_ids_json, trace_json, packet_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                trace_id,
                clean_bundle_id,
                clean_project_id,
                clean_entity_id,
                clean_mode,
                clean_source_scope,
                clean_source_id,
                clean_session_id,
                clean_checkpoint_id,
                _clean(source_snapshot_id),
                _clean(canon_snapshot_id),
                _clean(sandbox_id),
                _clean(storyline_id),
                _clean(branch_id),
                _clean(memory_scope or 'sandbox'),
                _clean(promotion_scope or 'sandbox_only'),
                clean_query_text,
                _json(clean_selected_ids, '[]'),
                _json(clean_trace, '{}'),
                _json(clean_packet, '{}'),
                created_at,
            ),
        )
    overview = fetch_rp2_sqlite_overview()
    return {
        'ok': True,
        'trace_id': trace_id,
        'bundle_id': clean_bundle_id,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'selected_count': len(clean_selected_ids),
        'overview': overview,
    }



def fetch_rp2_turn_summary_debug_rows(*, bundle_id: str = '', project_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 24, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
    )
    conditions: list[str] = []
    params: list[Any] = []
    if _clean(bundle_id):
        conditions.append('t.bundle_id = ?')
        params.append(_clean(bundle_id))
    if _clean(project_id):
        conditions.append('t.project_id = ?')
        params.append(_clean(project_id))
    if _clean(entity_id):
        conditions.append('t.entity_id = ?')
        params.append(_clean(entity_id))
    if _clean(source_ref):
        conditions.append('t.source_ref = ?')
        params.append(_clean(source_ref))
    _append_scope_where(conditions, params, table_alias='t', scope_filters=scope_filters)
    if _clean(checkpoint_id):
        conditions.append('t.checkpoint_id = ?')
        params.append(_clean(checkpoint_id))
    if _clean(query):
        like = f"%{_clean(query)}%"
        conditions.append('(t.summary LIKE ? OR t.source_ref LIKE ? OR t.entity_id LIKE ?)')
        params.extend([like, like, like])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    sql = f'''        SELECT t.turn_summary_id, t.session_id, t.checkpoint_id, t.bundle_id, t.project_id, t.entity_id,
               e.label AS entity_label, t.mode, t.source_ref, t.turn_index, t.summary, t.summary_json,
               t.source_snapshot_id, t.canon_snapshot_id, t.sandbox_id, t.storyline_id, t.branch_id, t.memory_scope,
               t.created_at, t.updated_at
        FROM rp2_turn_summaries t
        LEFT JOIN rp2_entities e ON e.entity_id = t.entity_id
        {where_clause}
        ORDER BY COALESCE(t.updated_at, t.created_at) DESC, t.turn_index DESC
        LIMIT ?
    '''
    params.append(max(1, min(int(limit or 24), 100)))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        for row in conn.execute(sql, params).fetchall():
            payload = _loads(row['summary_json'], {}) if row['summary_json'] else {}
            rows.append({
                'turn_summary_id': _clean(row['turn_summary_id']),
                'bundle_id': _clean(row['bundle_id']),
                'project_id': _clean(row['project_id']),
                'entity_id': _clean(row['entity_id']),
                'entity_label': _clean(row['entity_label']),
                'mode': _clean(row['mode']),
                'source_ref': _clean(row['source_ref']),
                'turn_index': int(row['turn_index'] or 0),
                'summary': _clean(row['summary']),
                'summary_payload': payload if isinstance(payload, dict) else {},
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'created_at': _clean(row['created_at']),
                'updated_at': _clean(row['updated_at']),
            })
    return {
        'ok': True,
        'rows': rows,
        'count': len(rows),
        'bundle_id': _clean(bundle_id),
        'entity_id': _clean(entity_id),
        'scope_filters': dict(scope_filters),
    }


def fetch_rp2_post_turn_memory_debug_rows(*, bundle_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 24, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_bundle_id = _clean(bundle_id)
    clean_entity_id = _clean(entity_id)
    clean_source_ref = _clean(source_ref)
    like_source = f'{clean_bundle_id}:turn:%' if clean_bundle_id and not clean_source_ref else ''
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    conditions: list[str] = []
    params: list[Any] = []
    if clean_entity_id:
        conditions.append('m.entity_id = ?')
        params.append(clean_entity_id)
    if clean_source_ref:
        conditions.append('m.source_ref = ?')
        params.append(clean_source_ref)
    elif like_source:
        conditions.append('m.source_ref LIKE ?')
        params.append(like_source)
    else:
        conditions.append("m.source_ref LIKE '%:turn:%'")
    _append_scope_where(conditions, params, table_alias='m', scope_filters=scope_filters)
    if _clean(query):
        like = f"%{_clean(query)}%"
        conditions.append('(m.title LIKE ? OR m.summary LIKE ? OR m.text LIKE ?)')
        params.extend([like, like, like])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    limit_value = max(1, min(int(limit or 24), 120))
    fragment_rows: list[dict[str, Any]] = []
    shared_rows: list[dict[str, Any]] = []
    callback_rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        frag_sql = f'''            SELECT m.memory_id, m.entity_id, e.label AS entity_label, m.memory_type, m.title, m.summary, m.text,
                   m.salience, m.source_ref, m.source_snapshot_id, m.canon_snapshot_id, m.sandbox_id,
                   m.storyline_id, m.session_id, m.checkpoint_id, m.branch_id, m.memory_scope, m.promotion_scope,
                   m.fragment_json, m.updated_at
            FROM rp2_memory_fragments m
            LEFT JOIN rp2_entities e ON e.entity_id = m.entity_id
            {where_clause}
            ORDER BY COALESCE(m.updated_at, '') DESC
            LIMIT ?
        '''
        frag_params = list(params) + [limit_value]
        for row in conn.execute(frag_sql, frag_params).fetchall():
            fragment_payload = _loads(row['fragment_json'], {}) if row['fragment_json'] else {}
            extra_payload = fragment_payload.get('extra') if isinstance(fragment_payload, dict) else {}
            compact = {
                'memory_id': _clean(row['memory_id']),
                'entity_id': _clean(row['entity_id']),
                'entity_label': _clean(row['entity_label']),
                'memory_type': _clean(row['memory_type']),
                'title': _clean(row['title']),
                'summary': _clean(row['summary']),
                'text': _clean(row['text'])[:360],
                'salience': float(row['salience'] or 0.0),
                'source_ref': _clean(row['source_ref']),
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': _clean(row['promotion_scope']).lower(),
                'confidence': float((fragment_payload.get('confidence') or 0.0) if isinstance(fragment_payload, dict) else 0.0),
                'promotion_status': _clean((extra_payload.get('promotion_status') if isinstance(extra_payload, dict) else '') or (fragment_payload.get('meta') or {}).get('status') if isinstance(fragment_payload, dict) else ''),
                'updated_at': _clean(row['updated_at']),
            }
            fragment_rows.append(compact)
            if compact['memory_type'] == 'callback_anchor':
                callback_rows.append({
                    'callback_id': compact['memory_id'],
                    'entity_id': compact['entity_id'],
                    'entity_label': compact['entity_label'],
                    'label': compact['title'],
                    'text': compact['summary'] or compact['text'],
                    'salience': compact['salience'],
                    'source_ref': compact['source_ref'],
                    'source_snapshot_id': compact['source_snapshot_id'],
                    'canon_snapshot_id': compact['canon_snapshot_id'],
                    'sandbox_id': compact['sandbox_id'],
                    'storyline_id': compact['storyline_id'],
                    'session_id': compact['session_id'],
                    'checkpoint_id': compact['checkpoint_id'],
                    'branch_id': compact['branch_id'],
                    'memory_scope': compact['memory_scope'],
                    'promotion_scope': compact['promotion_scope'],
                    'updated_at': compact['updated_at'],
                })
        shared_where_parts = []
        shared_params: list[Any] = []
        if clean_source_ref:
            shared_where_parts.append('s.source_ref = ?')
            shared_params.append(clean_source_ref)
        elif like_source:
            shared_where_parts.append('s.source_ref LIKE ?')
            shared_params.append(like_source)
        else:
            shared_where_parts.append("s.source_ref LIKE '%:turn:%'")
        if clean_entity_id:
            shared_where_parts.append('(s.entity_a_id = ? OR s.entity_b_id = ?)')
            shared_params.extend([clean_entity_id, clean_entity_id])
        _append_scope_where(shared_where_parts, shared_params, table_alias='s', scope_filters=scope_filters)
        shared_where_sql = f"WHERE {' AND '.join(shared_where_parts)}" if shared_where_parts else ''
        shared_sql = f'''            SELECT s.shared_memory_id, s.entity_a_id, a.label AS entity_a_label, s.entity_b_id, b.label AS entity_b_label,
                   s.label, s.text, s.salience, s.source_ref, s.source_snapshot_id, s.canon_snapshot_id,
                   s.sandbox_id, s.storyline_id, s.session_id, s.checkpoint_id, s.branch_id,
                   s.memory_scope, s.promotion_scope, s.memory_json, s.updated_at
            FROM rp2_shared_memories s
            LEFT JOIN rp2_entities a ON a.entity_id = s.entity_a_id
            LEFT JOIN rp2_entities b ON b.entity_id = s.entity_b_id
            {shared_where_sql}
            ORDER BY COALESCE(s.updated_at, '') DESC
            LIMIT ?
        '''
        shared_params.append(limit_value)
        for row in conn.execute(shared_sql, shared_params).fetchall():
            shared_payload = _loads(row['memory_json'], {}) if row['memory_json'] else {}
            extra_payload = shared_payload.get('extra') if isinstance(shared_payload, dict) else {}
            shared_rows.append({
                'shared_memory_id': _clean(row['shared_memory_id']),
                'entity_a_id': _clean(row['entity_a_id']),
                'entity_a_label': _clean(row['entity_a_label']),
                'entity_b_id': _clean(row['entity_b_id']),
                'entity_b_label': _clean(row['entity_b_label']),
                'label': _clean(row['label']),
                'text': _clean(row['text'])[:360],
                'salience': float(row['salience'] or 0.0),
                'promotion_status': _clean((extra_payload.get('promotion_status') if isinstance(extra_payload, dict) else '') or (shared_payload.get('meta') or {}).get('status') if isinstance(shared_payload, dict) else ''),
                'confidence': float((extra_payload.get('promotion_confidence') if isinstance(extra_payload, dict) else 0.0) or 0.0),
                'source_ref': _clean(row['source_ref']),
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': _clean(row['promotion_scope']).lower(),
                'updated_at': _clean(row['updated_at']),
            })
    return {
        'ok': True,
        'bundle_id': clean_bundle_id,
        'entity_id': clean_entity_id,
        'source_ref': clean_source_ref,
        'scope_filters': dict(scope_filters),
        'memory_fragments': fragment_rows,
        'shared_memories': shared_rows,
        'callback_anchors': callback_rows,
        'count': len(fragment_rows) + len(shared_rows),
    }

def evaluate_rp2_writeback_rows(*, bundle_id: str = '', project_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 24) -> dict[str, Any]:
    turn_rows_payload = fetch_rp2_turn_summary_debug_rows(bundle_id=bundle_id, project_id=project_id, entity_id=entity_id, source_ref=source_ref, query=query, limit=limit)
    turn_rows = turn_rows_payload.get('rows') if isinstance(turn_rows_payload.get('rows'), list) else []
    promotion_totals: dict[str, dict[str, int]] = {}
    mode_totals: dict[str, int] = {}
    profile_focus_totals: dict[str, int] = {}
    skipped_reasons: dict[str, int] = {}
    confidence_totals: dict[str, list[float]] = {}
    for row in turn_rows:
        payload = row.get('summary_payload') if isinstance(row.get('summary_payload'), dict) else {}
        promotion_report = payload.get('promotion_report') if isinstance(payload.get('promotion_report'), dict) else {}
        mode_profile = payload.get('mode_profile') if isinstance(payload.get('mode_profile'), dict) else {}
        mode_key = _clean((mode_profile.get('key') if isinstance(mode_profile, dict) else '') or row.get('mode') or 'roleplay')
        if mode_key:
            mode_totals[mode_key] = int(mode_totals.get(mode_key) or 0) + 1
        profile_focus = _clean((mode_profile.get('focus') if isinstance(mode_profile, dict) else '') or '')
        if profile_focus:
            profile_focus_totals[profile_focus] = int(profile_focus_totals.get(profile_focus) or 0) + 1
        for memory_kind, decision in promotion_report.items():
            if not isinstance(decision, dict):
                continue
            status = _clean(decision.get('promotion_status') or 'unknown')
            promotion_totals.setdefault(memory_kind, {})
            promotion_totals[memory_kind][status] = int(promotion_totals[memory_kind].get(status) or 0) + 1
            confidence_totals.setdefault(memory_kind, []).append(float(decision.get('confidence') or 0.0))
            if status == 'discarded':
                reason = _clean(decision.get('reason') or 'discarded')
                skipped_reasons[reason] = int(skipped_reasons.get(reason) or 0) + 1
    averaged_confidence = {key: round(sum(values) / max(1, len(values)), 4) for key, values in confidence_totals.items() if values}
    memory_rows_payload = fetch_rp2_post_turn_memory_debug_rows(bundle_id=bundle_id, entity_id=entity_id, source_ref=source_ref, query=query, limit=max(12, limit * 2))
    suggestions: list[str] = []
    if (promotion_totals.get('relationship_belief') or {}).get('durable', 0) == 0 and mode_totals.get('roleplay'):
        suggestions.append('Roleplay turns are not promoting relationship beliefs to durable. Consider lowering the roleplay relationship durable threshold slightly.')
    if (promotion_totals.get('episodic_memory') or {}).get('durable', 0) == 0 and mode_totals.get('novel'):
        suggestions.append('Novel turns are not accumulating durable episodic memory. Consider slightly lowering novel episodic thresholds or increasing episodic confidence bias.')
    if (promotion_totals.get('callback_anchor') or {}).get('durable', 0) == 0 and mode_totals.get('cinematic'):
        suggestions.append('Cinematic turns are not landing durable callback anchors. Consider lifting cinematic callback salience or confidence bias.')
    return {
        'ok': True,
        'bundle_id': _clean(bundle_id),
        'project_id': _clean(project_id),
        'entity_id': _clean(entity_id),
        'source_ref': _clean(source_ref),
        'query': _clean(query),
        'turn_summary_count': len(turn_rows),
        'mode_totals': mode_totals,
        'profile_focus_totals': profile_focus_totals,
        'promotion_totals': promotion_totals,
        'average_confidence': averaged_confidence,
        'skipped_reasons': skipped_reasons,
        'suggestions': suggestions,
        'recent_turn_summaries': turn_rows[: min(8, len(turn_rows))],
        'memory_rows': memory_rows_payload,
    }


def fetch_rp2_retrieval_trace_rows(*, project_id: str = '', entity_id: str = '', bundle_id: str = '', trace_id: str = '', query: str = '', limit: int = 20) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_bundle_id = _clean(bundle_id)
    clean_trace_id = _clean(trace_id)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 20), 100))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_project_id:
            where_parts.append('t.project_id=?')
            params.append(clean_project_id)
        if clean_entity_id:
            where_parts.append('t.entity_id=?')
            params.append(clean_entity_id)
        if clean_bundle_id:
            where_parts.append('t.bundle_id=?')
            params.append(clean_bundle_id)
        if clean_trace_id:
            where_parts.append('t.trace_id=?')
            params.append(clean_trace_id)
        if clean_query:
            where_parts.append('(t.query_text LIKE ? OR t.bundle_id LIKE ? OR t.trace_id LIKE ?)')
            wildcard = f'%{clean_query}%'
            params.extend([wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                t.trace_id, t.bundle_id, t.project_id, t.entity_id, e.label AS entity_label,
                t.mode, t.source_scope, t.source_id, t.query_text, t.created_at,
                t.selected_ids_json, t.trace_json, t.packet_json
            FROM rp2_retrieval_traces t
            LEFT JOIN rp2_entities e ON e.entity_id=t.entity_id
            {where_sql}
            ORDER BY t.created_at DESC, t.trace_id DESC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            item = dict(row)
            selected_ids = json.loads(item.get('selected_ids_json') or '[]') if str(item.get('selected_ids_json') or '').strip() else []
            trace_json = json.loads(item.get('trace_json') or '{}') if str(item.get('trace_json') or '').strip() else {}
            packet_json = json.loads(item.get('packet_json') or '{}') if str(item.get('packet_json') or '').strip() else {}
            item['selected_ids'] = selected_ids
            item['selected_count'] = len(selected_ids)
            item['trace'] = trace_json if isinstance(trace_json, dict) else {}
            item['packet'] = packet_json if isinstance(packet_json, dict) else {}
            item['selection_policy'] = _clean((item['trace'].get('selection_policy') if isinstance(item['trace'], dict) else '') or '')
            item['budget_map'] = (item['trace'].get('budget_map') if isinstance(item['trace'], dict) and isinstance(item['trace'].get('budget_map'), dict) else {})
            rows.append(item)

    return {
        'ok': True,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'bundle_id': clean_bundle_id,
        'trace_id': clean_trace_id,
        'query': clean_query,
        'limit': clean_limit,
        'rows': rows,
    }


def _continuity_control_state(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    cooldown_until = _clean(row.get('cooldown_until'))
    cooldown_active = False
    if cooldown_until:
        try:
            cooldown_active = datetime.fromisoformat(cooldown_until.replace('Z', '+00:00')) > datetime.now(timezone.utc)
        except Exception:
            cooldown_active = False
    return {
        'is_pinned': bool(row.get('is_pinned')),
        'is_suppressed': bool(row.get('is_suppressed')),
        'is_resolved': bool(row.get('is_resolved')),
        'cooldown_until': cooldown_until,
        'cooldown_active': cooldown_active,
        'updated_at': _clean(row.get('updated_at')),
    }


def _continuity_recurrence_state(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    cooldown_until = _clean(row.get('cooldown_until'))
    cooldown_active = False
    if cooldown_until:
        try:
            cooldown_active = datetime.fromisoformat(cooldown_until.replace('Z', '+00:00')) > datetime.now(timezone.utc)
        except Exception:
            cooldown_active = False
    recurrence_payload = row.get('recurrence_payload') if isinstance(row.get('recurrence_payload'), dict) else {}
    return {
        'selected_count': int(row.get('selected_count') or 0),
        'bucket_key': _clean(row.get('bucket_key')),
        'last_selected_at': _clean(row.get('last_selected_at')),
        'cooldown_until': cooldown_until,
        'cooldown_active': cooldown_active,
        'updated_at': _clean(row.get('updated_at')),
        'recurrence_payload': recurrence_payload,
    }


def _fetch_rp2_continuity_seed_rows(memory_ids: list[str]) -> dict[str, dict[str, Any]]:
    clean_ids = [item for item in {_clean(value) for value in (memory_ids or [])} if item]
    if not clean_ids:
        return {}
    ensure_roleplay_v2_sqlite_backbone()
    out: dict[str, dict[str, Any]] = {}
    placeholders = ','.join('?' for _ in clean_ids)
    with sqlite_conn() as conn:
        frag_sql = f'''
            SELECT m.memory_id, m.entity_id, e.label AS entity_label, m.memory_type, m.title, m.summary, m.text,
                   m.salience, m.source_ref, m.updated_at
            FROM rp2_memory_fragments m
            LEFT JOIN rp2_entities e ON e.entity_id = m.entity_id
            WHERE m.memory_id IN ({placeholders})
        '''
        for row in conn.execute(frag_sql, tuple(clean_ids)).fetchall():
            memory_id = _clean(row['memory_id'])
            out[memory_id] = {
                'memory_id': memory_id,
                'title': _clean(row['title']) or memory_id,
                'summary': _clean(row['summary']),
                'text_excerpt': _clean(row['text'])[:360],
                'memory_type': _clean(row['memory_type']),
                'entity_id': _clean(row['entity_id']),
                'entity_label': _clean(row['entity_label']),
                'source_ref': _clean(row['source_ref']),
                'salience': float(row['salience'] or 0.0),
                'updated_at': _clean(row['updated_at']),
                'row_sources': ['memory_fragment'],
                'trace_refs': [],
            }
        shared_sql = f'''
            SELECT s.shared_memory_id, s.entity_a_id, a.label AS entity_a_label, s.entity_b_id, b.label AS entity_b_label,
                   s.label, s.text, s.salience, s.source_ref, s.updated_at
            FROM rp2_shared_memories s
            LEFT JOIN rp2_entities a ON a.entity_id = s.entity_a_id
            LEFT JOIN rp2_entities b ON b.entity_id = s.entity_b_id
            WHERE s.shared_memory_id IN ({placeholders})
        '''
        for row in conn.execute(shared_sql, tuple(clean_ids)).fetchall():
            memory_id = _clean(row['shared_memory_id'])
            existing = out.get(memory_id, {})
            sources = list(dict.fromkeys([*(existing.get('row_sources') or []), 'shared_memory']))
            out[memory_id] = {
                **existing,
                'memory_id': memory_id,
                'title': _clean(row['label']) or existing.get('title') or memory_id,
                'summary': existing.get('summary') or _clean(row['text'])[:220],
                'text_excerpt': existing.get('text_excerpt') or _clean(row['text'])[:360],
                'memory_type': existing.get('memory_type') or 'shared_memory',
                'entity_id': existing.get('entity_id') or _clean(row['entity_a_id']) or _clean(row['entity_b_id']),
                'entity_label': existing.get('entity_label') or _clean(row['entity_a_label']) or _clean(row['entity_b_label']),
                'source_ref': existing.get('source_ref') or _clean(row['source_ref']),
                'salience': max(float(existing.get('salience') or 0.0), float(row['salience'] or 0.0)),
                'updated_at': existing.get('updated_at') or _clean(row['updated_at']),
                'row_sources': sources,
                'trace_refs': existing.get('trace_refs') or [],
                'shared_with': [item for item in [_clean(row['entity_a_id']), _clean(row['entity_b_id'])] if item],
            }
        callback_sql = f'''
            SELECT c.callback_id, c.entity_id, e.label AS entity_label, c.label, c.anchor_text, c.salience, c.source_ref, c.updated_at
            FROM rp2_callback_anchors c
            LEFT JOIN rp2_entities e ON e.entity_id = c.entity_id
            WHERE c.callback_id IN ({placeholders})
        '''
        for row in conn.execute(callback_sql, tuple(clean_ids)).fetchall():
            memory_id = _clean(row['callback_id'])
            existing = out.get(memory_id, {})
            sources = list(dict.fromkeys([*(existing.get('row_sources') or []), 'callback_anchor']))
            out[memory_id] = {
                **existing,
                'memory_id': memory_id,
                'title': existing.get('title') or _clean(row['label']) or memory_id,
                'summary': existing.get('summary') or _clean(row['anchor_text'])[:220],
                'text_excerpt': existing.get('text_excerpt') or _clean(row['anchor_text'])[:360],
                'memory_type': existing.get('memory_type') or 'callback_anchor',
                'entity_id': existing.get('entity_id') or _clean(row['entity_id']),
                'entity_label': existing.get('entity_label') or _clean(row['entity_label']),
                'source_ref': existing.get('source_ref') or _clean(row['source_ref']),
                'salience': max(float(existing.get('salience') or 0.0), float(row['salience'] or 0.0)),
                'updated_at': existing.get('updated_at') or _clean(row['updated_at']),
                'row_sources': sources,
                'trace_refs': existing.get('trace_refs') or [],
            }
    for memory_id in clean_ids:
        if memory_id not in out:
            out[memory_id] = {
                'memory_id': memory_id,
                'title': memory_id,
                'summary': '',
                'text_excerpt': '',
                'memory_type': '',
                'entity_id': '',
                'entity_label': '',
                'source_ref': '',
                'salience': 0.0,
                'updated_at': '',
                'row_sources': ['lookup_only'],
                'trace_refs': [],
            }
    return out


def _merge_continuity_row(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = deepcopy(existing) if isinstance(existing, dict) else {}
    row = incoming if isinstance(incoming, dict) else {}
    for key in ('memory_id', 'title', 'summary', 'text_excerpt', 'memory_type', 'entity_id', 'entity_label', 'source_ref', 'updated_at'):
        value = row.get(key)
        if value not in (None, '', []):
            if key not in base or base.get(key) in (None, '', []):
                base[key] = value
            elif key in {'summary', 'text_excerpt'} and len(str(value)) > len(str(base.get(key) or '')):
                base[key] = value
    for key in ('score', 'rerank_score', 'continuity_bias', 'salience'):
        value = row.get(key)
        if value is not None:
            try:
                numeric = float(value)
            except Exception:
                continue
            base[key] = max(float(base.get(key) or 0.0), numeric)
    if row.get('retrieval_rank'):
        if not base.get('retrieval_rank') or int(row.get('retrieval_rank') or 0) < int(base.get('retrieval_rank') or 999999):
            base['retrieval_rank'] = int(row.get('retrieval_rank') or 0)
    if row.get('selected_from_trace') is not None:
        base['selected_from_trace'] = bool(base.get('selected_from_trace')) or bool(row.get('selected_from_trace'))
    if row.get('shared_with'):
        base['shared_with'] = list(dict.fromkeys([*(base.get('shared_with') or []), *(row.get('shared_with') or [])]))
    if row.get('recovery_tags'):
        base['recovery_tags'] = list(dict.fromkeys([*(base.get('recovery_tags') or []), *(row.get('recovery_tags') or [])]))
    if row.get('row_sources'):
        base['row_sources'] = list(dict.fromkeys([*(base.get('row_sources') or []), *(row.get('row_sources') or [])]))
    if row.get('trace_refs'):
        traces = base.get('trace_refs') or []
        seen = {(_clean(item.get('trace_id')), _clean(item.get('bundle_id')), _clean(item.get('source_ref')), _clean(item.get('row_origin'))) for item in traces if isinstance(item, dict)}
        for item in row.get('trace_refs') or []:
            if not isinstance(item, dict):
                continue
            sig = (_clean(item.get('trace_id')), _clean(item.get('bundle_id')), _clean(item.get('source_ref')), _clean(item.get('row_origin')))
            if sig in seen:
                continue
            traces.append(item)
            seen.add(sig)
        base['trace_refs'] = traces
    return base


def fetch_rp2_continuity_control_rows(*, project_id: str = '', entity_id: str = '', bundle_id: str = '', trace_id: str = '', source_ref: str = '', query: str = '', limit: int = 24, origin: str = 'auto', memory_ids: list[str] | None = None) -> dict[str, Any]:
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_bundle_id = _clean(bundle_id)
    clean_trace_id = _clean(trace_id)
    clean_source_ref = _clean(source_ref)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 24), 200))
    clean_origin = _clean(origin).lower() or 'auto'
    lookup_ids = [item for item in {_clean(value) for value in (memory_ids or [])} if item]
    control_map = fetch_rp2_memory_control_map(project_id=clean_project_id, entity_id=clean_entity_id)
    recurrence_map = fetch_rp2_recurrence_map(project_id=clean_project_id, entity_id=clean_entity_id)
    rows_by_id: dict[str, dict[str, Any]] = _fetch_rp2_continuity_seed_rows(lookup_ids)
    selected_ids: set[str] = set()
    trace_entry: dict[str, Any] | None = None
    include_retrieval = clean_origin in {'auto', 'all', 'retrieval', 'runtime', 'runtime_trace'}
    include_writeback = clean_origin in {'auto', 'all', 'writeback', 'scene', 'continuity'}
    if include_retrieval and (clean_trace_id or clean_bundle_id or clean_project_id or clean_entity_id or clean_query):
        trace_rows = fetch_rp2_retrieval_trace_rows(project_id=clean_project_id, entity_id=clean_entity_id, bundle_id=clean_bundle_id, trace_id=clean_trace_id, query=clean_query, limit=1).get('rows') or []
        trace_entry = trace_rows[0] if trace_rows else None
        trace_payload = trace_entry.get('trace') if isinstance(trace_entry, dict) and isinstance(trace_entry.get('trace'), dict) else {}
        selected_ids = {item for item in (trace_entry.get('selected_ids') or []) if _clean(item)} if isinstance(trace_entry, dict) else set()
        retrieval_rows = []
        if isinstance(trace_payload, dict):
            if isinstance(trace_payload.get('results'), list) and trace_payload.get('results'):
                retrieval_rows = trace_payload.get('results') or []
            elif isinstance(trace_payload.get('reranked_candidates'), list) and trace_payload.get('reranked_candidates'):
                retrieval_rows = (trace_payload.get('reranked_candidates') or [])[:clean_limit]
            else:
                retrieval_rows = (trace_payload.get('candidates') or [])[:clean_limit]
        for idx, item in enumerate(retrieval_rows):
            if not isinstance(item, dict):
                continue
            memory_id = _clean(item.get('id') or item.get('memory_id') or item.get('shared_memory_id') or item.get('callback_id'))
            if not memory_id:
                continue
            seed = rows_by_id.get(memory_id, {'memory_id': memory_id, 'row_sources': [], 'trace_refs': []})
            row = _merge_continuity_row(seed, {
                'memory_id': memory_id,
                'title': _clean(item.get('title')) or _clean(item.get('label')) or memory_id,
                'summary': _clean(item.get('summary')),
                'text_excerpt': _clean(item.get('text') or item.get('document'))[:360],
                'memory_type': _clean(item.get('memory_type')),
                'entity_id': _clean(item.get('entity_id')),
                'entity_label': _clean(item.get('entity_label')),
                'source_ref': _clean(item.get('source_ref')),
                'score': float(item.get('score') or 0.0),
                'rerank_score': float(item.get('rerank_score') or 0.0),
                'continuity_bias': float(item.get('continuity_bias') or 0.0),
                'salience': float(item.get('salience') or 0.0),
                'retrieval_rank': idx + 1,
                'selected_from_trace': memory_id in selected_ids,
                'recovery_tags': [tag for tag in (item.get('recovery_tags') or []) if _clean(tag)],
                'row_sources': ['retrieval_result'],
                'trace_refs': [{
                    'trace_id': _clean(trace_entry.get('trace_id')) if isinstance(trace_entry, dict) else '',
                    'bundle_id': _clean(trace_entry.get('bundle_id')) if isinstance(trace_entry, dict) else '',
                    'project_id': _clean(trace_entry.get('project_id')) if isinstance(trace_entry, dict) else '',
                    'entity_id': _clean(trace_entry.get('entity_id')) if isinstance(trace_entry, dict) else '',
                    'query_text': _clean(trace_entry.get('query_text')) if isinstance(trace_entry, dict) else clean_query,
                    'source_scope': _clean(trace_entry.get('source_scope')) if isinstance(trace_entry, dict) else '',
                    'source_id': _clean(trace_entry.get('source_id')) if isinstance(trace_entry, dict) else '',
                    'source_ref': _clean(item.get('source_ref')),
                    'created_at': _clean(trace_entry.get('created_at')) if isinstance(trace_entry, dict) else '',
                    'row_origin': 'retrieval_result',
                }],
            })
            rows_by_id[memory_id] = row
    if include_writeback and (clean_bundle_id or clean_entity_id or clean_source_ref or clean_query or lookup_ids):
        writeback_payload = fetch_rp2_post_turn_memory_debug_rows(bundle_id=clean_bundle_id, entity_id=clean_entity_id, source_ref=clean_source_ref, query=clean_query, limit=max(clean_limit, len(lookup_ids) or clean_limit))
        for item in (writeback_payload.get('memory_fragments') or []):
            if not isinstance(item, dict):
                continue
            memory_id = _clean(item.get('memory_id'))
            if not memory_id:
                continue
            row = _merge_continuity_row(rows_by_id.get(memory_id), {
                'memory_id': memory_id,
                'title': _clean(item.get('title')) or memory_id,
                'summary': _clean(item.get('summary')),
                'text_excerpt': _clean(item.get('text'))[:360],
                'memory_type': _clean(item.get('memory_type')),
                'entity_id': _clean(item.get('entity_id')),
                'entity_label': _clean(item.get('entity_label')),
                'source_ref': _clean(item.get('source_ref')),
                'salience': float(item.get('salience') or 0.0),
                'updated_at': _clean(item.get('updated_at')),
                'row_sources': ['writeback_memory'],
                'trace_refs': [{
                    'trace_id': clean_trace_id,
                    'bundle_id': clean_bundle_id,
                    'project_id': clean_project_id,
                    'entity_id': _clean(item.get('entity_id')) or clean_entity_id,
                    'query_text': clean_query,
                    'source_scope': 'post_turn_memory',
                    'source_id': _clean(item.get('entity_id')) or clean_entity_id,
                    'source_ref': _clean(item.get('source_ref')),
                    'created_at': _clean(item.get('updated_at')),
                    'row_origin': 'writeback_memory',
                }],
            })
            rows_by_id[memory_id] = row
        for item in (writeback_payload.get('shared_memories') or []):
            if not isinstance(item, dict):
                continue
            memory_id = _clean(item.get('shared_memory_id'))
            if not memory_id:
                continue
            row = _merge_continuity_row(rows_by_id.get(memory_id), {
                'memory_id': memory_id,
                'title': _clean(item.get('label')) or memory_id,
                'summary': _clean(item.get('text'))[:220],
                'text_excerpt': _clean(item.get('text'))[:360],
                'memory_type': 'shared_memory',
                'entity_id': _clean(item.get('entity_a_id')) or clean_entity_id,
                'entity_label': _clean(item.get('entity_a_label')) or _clean(item.get('entity_b_label')),
                'source_ref': _clean(item.get('source_ref')),
                'salience': float(item.get('salience') or 0.0),
                'updated_at': _clean(item.get('updated_at')),
                'shared_with': [value for value in [_clean(item.get('entity_a_id')), _clean(item.get('entity_b_id'))] if value],
                'row_sources': ['shared_memory'],
                'trace_refs': [{
                    'trace_id': clean_trace_id,
                    'bundle_id': clean_bundle_id,
                    'project_id': clean_project_id,
                    'entity_id': _clean(item.get('entity_a_id')) or clean_entity_id,
                    'query_text': clean_query,
                    'source_scope': 'shared_memory',
                    'source_id': _clean(item.get('entity_a_id')) or clean_entity_id,
                    'source_ref': _clean(item.get('source_ref')),
                    'created_at': _clean(item.get('updated_at')),
                    'row_origin': 'shared_memory',
                }],
            })
            rows_by_id[memory_id] = row
    for memory_id in lookup_ids:
        rows_by_id.setdefault(memory_id, {'memory_id': memory_id, 'title': memory_id, 'row_sources': ['lookup_only'], 'trace_refs': []})
    rows: list[dict[str, Any]] = []
    for memory_id, row in rows_by_id.items():
        control_state = _continuity_control_state(control_map.get(memory_id))
        recurrence_state = _continuity_recurrence_state(recurrence_map.get(memory_id))
        cooldown_state = {
            'control_until': control_state.get('cooldown_until') or '',
            'control_active': bool(control_state.get('cooldown_active')),
            'recurrence_until': recurrence_state.get('cooldown_until') or '',
            'recurrence_active': bool(recurrence_state.get('cooldown_active')),
        }
        cooldown_state['any_active'] = bool(cooldown_state['control_active'] or cooldown_state['recurrence_active'])
        if bool(control_state.get('is_pinned')):
            status_label = 'Pinned'
        elif bool(control_state.get('is_suppressed')):
            status_label = 'Suppressed'
        elif bool(control_state.get('is_resolved')):
            status_label = 'Resolved'
        elif cooldown_state['any_active']:
            status_label = 'Cooling down'
        else:
            status_label = 'Neutral'
        rows.append({
            'memory_id': memory_id,
            'title': _clean(row.get('title')) or memory_id,
            'summary': _clean(row.get('summary')),
            'text_excerpt': _clean(row.get('text_excerpt')),
            'memory_type': _clean(row.get('memory_type')),
            'entity_id': _clean(row.get('entity_id')),
            'entity_label': _clean(row.get('entity_label')),
            'source_ref': _clean(row.get('source_ref')),
            'score': round(float(row.get('score') or 0.0), 6),
            'rerank_score': round(float(row.get('rerank_score') or 0.0), 6),
            'continuity_bias': round(float(row.get('continuity_bias') or 0.0), 6),
            'salience': round(float(row.get('salience') or 0.0), 6),
            'retrieval_rank': int(row.get('retrieval_rank') or 0),
            'selected_from_trace': bool(row.get('selected_from_trace')),
            'recovery_tags': [tag for tag in (row.get('recovery_tags') or []) if _clean(tag)],
            'row_sources': [tag for tag in (row.get('row_sources') or []) if _clean(tag)],
            'trace_refs': [item for item in (row.get('trace_refs') or []) if isinstance(item, dict)],
            'shared_with': [value for value in (row.get('shared_with') or []) if _clean(value)],
            'updated_at': _clean(row.get('updated_at')),
            'control_state': control_state,
            'recurrence_state': recurrence_state,
            'cooldown_state': cooldown_state,
            'status_label': status_label,
        })
    rows.sort(key=lambda item: (
        0 if item.get('control_state', {}).get('is_pinned') else 1,
        0 if item.get('selected_from_trace') else 1,
        int(item.get('retrieval_rank') or 999999),
        -int(item.get('recurrence_state', {}).get('selected_count') or 0),
        -float(item.get('score') or 0.0),
        -float(item.get('salience') or 0.0),
        item.get('updated_at') or '',
        item.get('memory_id') or '',
    ))
    rows = rows[:clean_limit]
    return {
        'ok': True,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'bundle_id': clean_bundle_id,
        'trace_id': clean_trace_id,
        'source_ref': clean_source_ref,
        'query': clean_query,
        'origin': clean_origin,
        'limit': clean_limit,
        'rows': rows,
        'count': len(rows),
        'selected_count': len([row for row in rows if row.get('selected_from_trace')]),
        'control_map_size': len(control_map) if isinstance(control_map, dict) else 0,
        'recurrence_map_size': len(recurrence_map) if isinstance(recurrence_map, dict) else 0,
        'trace_entry': {
            'trace_id': _clean(trace_entry.get('trace_id')) if isinstance(trace_entry, dict) else '',
            'bundle_id': _clean(trace_entry.get('bundle_id')) if isinstance(trace_entry, dict) else clean_bundle_id,
            'project_id': _clean(trace_entry.get('project_id')) if isinstance(trace_entry, dict) else clean_project_id,
            'entity_id': _clean(trace_entry.get('entity_id')) if isinstance(trace_entry, dict) else clean_entity_id,
            'query_text': _clean(trace_entry.get('query_text')) if isinstance(trace_entry, dict) else clean_query,
            'created_at': _clean(trace_entry.get('created_at')) if isinstance(trace_entry, dict) else '',
            'selection_policy': _clean(trace_entry.get('selection_policy')) if isinstance(trace_entry, dict) else '',
        },
    }


def _prune_missing_entities(conn: sqlite3.Connection, present_ids: set[str]) -> int:
    if not present_ids:
        stale_ids = [str(row['entity_id'] or '').strip() for row in conn.execute('SELECT entity_id FROM rp2_entities') if str(row['entity_id'] or '').strip()]
    else:
        placeholders = ','.join('?' for _ in present_ids)
        stale_ids = [
            str(row['entity_id'] or '').strip()
            for row in conn.execute(f'SELECT entity_id FROM rp2_entities WHERE entity_id NOT IN ({placeholders})', tuple(sorted(present_ids)))
            if str(row['entity_id'] or '').strip()
        ]
    removed = 0
    for entity_id in stale_ids:
        conn.execute('DELETE FROM rp2_entities WHERE entity_id=?', (entity_id,))
        conn.execute('DELETE FROM rp2_edges WHERE source_id=? OR target_id=?', (entity_id, entity_id))
        conn.execute('DELETE FROM rp2_entity_versions WHERE entity_id=?', (entity_id,))
        conn.execute('DELETE FROM rp2_entity_search WHERE entity_id=?', (entity_id,))
        conn.execute('DELETE FROM rp2_memory_fragments WHERE entity_id=? OR builder_record_id=? OR source_ref=?', (entity_id, entity_id, entity_id))
        conn.execute('DELETE FROM rp2_shared_memories WHERE entity_a_id=? OR entity_b_id=? OR builder_record_id=? OR source_ref=?', (entity_id, entity_id, entity_id, entity_id))
        conn.execute('DELETE FROM rp2_callback_anchors WHERE entity_id=? OR builder_record_id=? OR source_ref=?', (entity_id, entity_id, entity_id))
        removed += 1
    return removed


def sync_rp2_entities_from_directory(*, entities_dir: Path, prune_missing: bool = False) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    synced = 0
    skipped = 0
    present_ids: set[str] = set()
    for path in sorted(Path(entities_dir).glob('*.json')):
        payload = read_json_object(path, None)
        if not isinstance(payload, dict) or payload.get('record_type') != 'entity_record':
            skipped += 1
            continue
        present_ids.add(_clean(payload.get('id')))
        upsert_rp2_entity_record(record=payload, source_json_path=str(path))
        synced += 1
    pruned = 0
    if prune_missing:
        with sqlite_conn() as conn:
            pruned = _prune_missing_entities(conn, present_ids)
    overview = fetch_rp2_sqlite_overview()
    return {
        'ok': True,
        'db_path': str(MEMORY_DB_PATH),
        'synced': synced,
        'skipped': skipped,
        'pruned': pruned,
        'overview': overview,
    }


def fetch_rp2_entity_debug_rows(*, kind: str = '', query: str = '', limit: int = 20) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_kind = _clean(kind)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 20), 100))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_kind:
            where_parts.append('e.kind=?')
            params.append(clean_kind)
        if clean_query:
            where_parts.append('(e.label LIKE ? OR e.display_label LIKE ? OR e.summary LIKE ? OR e.entity_id LIKE ?)')
            wildcard = f'%{clean_query}%'
            params.extend([wildcard, wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                e.entity_id, e.kind, e.label, e.display_label, e.summary, e.source_container_id,
                e.record_status, e.updated_at,
                json_extract(e.graph_json, '$.edge_summary.edge_count') AS edge_count,
                json_extract(e.graph_json, '$.edge_summary.reverse_edge_count') AS reverse_edge_count
            FROM rp2_entities e
            {where_sql}
            ORDER BY e.updated_at DESC, e.label ASC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            rows.append(dict(row))
    return {
        'ok': True,
        'kind': clean_kind,
        'query': clean_query,
        'limit': clean_limit,
        'rows': rows,
    }


def fetch_rp2_edge_debug_rows(*, entity_id: str = '', relation: str = '', limit: int = 40) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_relation = _clean(relation)
    clean_limit = max(1, min(int(limit or 40), 200))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_entity_id:
            where_parts.append('(e.source_id=? OR e.target_id=?)')
            params.extend([clean_entity_id, clean_entity_id])
        if clean_relation:
            where_parts.append('(e.relation=? OR e.reverse_relation=?)')
            params.extend([clean_relation, clean_relation])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                e.edge_id, e.source_id, e.source_kind, s.label AS source_label,
                e.family, e.slot, e.relation, e.reverse_relation,
                e.target_id, e.target_kind, t.label AS target_label,
                e.cardinality, e.status, e.visibility, e.updated_at
            FROM rp2_edges e
            LEFT JOIN rp2_entities s ON s.entity_id=e.source_id
            LEFT JOIN rp2_entities t ON t.entity_id=e.target_id
            {where_sql}
            ORDER BY e.updated_at DESC, e.family ASC, e.relation ASC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            item = dict(row)
            if clean_entity_id:
                item['direction'] = 'outgoing' if _clean(item.get('source_id')) == clean_entity_id else 'incoming'
            rows.append(item)
    return {
        'ok': True,
        'entity_id': clean_entity_id,
        'relation': clean_relation,
        'limit': clean_limit,
        'rows': rows,
    }


def fetch_rp2_memory_fragment_debug_rows(*, entity_id: str = '', memory_type: str = '', query: str = '', limit: int = 24) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_memory_type = _clean(memory_type)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 24), 200))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_entity_id:
            where_parts.append('(m.entity_id=? OR m.builder_record_id=? OR m.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        if clean_memory_type:
            where_parts.append('m.memory_type=?')
            params.append(clean_memory_type)
        if clean_query:
            where_parts.append('(m.title LIKE ? OR m.summary LIKE ? OR m.text LIKE ? OR m.memory_id LIKE ?)')
            wildcard = f'%{clean_query}%'
            params.extend([wildcard, wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                m.memory_id, m.entity_id, e.label AS entity_label, m.memory_type,
                m.title, m.summary, m.salience, m.source_ref, m.builder_record_id,
                m.canon_id, m.updated_at
            FROM rp2_memory_fragments m
            LEFT JOIN rp2_entities e ON e.entity_id=m.entity_id
            {where_sql}
            ORDER BY m.updated_at DESC, m.salience DESC, m.title ASC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            rows.append(dict(row))
    return {
        'ok': True,
        'entity_id': clean_entity_id,
        'memory_type': clean_memory_type,
        'query': clean_query,
        'limit': clean_limit,
        'rows': rows,
    }


def fetch_rp2_shared_memory_debug_rows(*, entity_id: str = '', query: str = '', limit: int = 16) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 16), 100))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_entity_id:
            where_parts.append('(s.entity_a_id=? OR s.entity_b_id=? OR s.builder_record_id=? OR s.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id, clean_entity_id])
        if clean_query:
            where_parts.append('(s.label LIKE ? OR s.text LIKE ? OR s.shared_memory_id LIKE ?)')
            wildcard = f'%{clean_query}%'
            params.extend([wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                s.shared_memory_id, s.entity_a_id, a.label AS entity_a_label,
                s.entity_b_id, b.label AS entity_b_label,
                s.label, s.text, s.salience, s.source_ref, s.builder_record_id,
                s.canon_id, s.updated_at
            FROM rp2_shared_memories s
            LEFT JOIN rp2_entities a ON a.entity_id=s.entity_a_id
            LEFT JOIN rp2_entities b ON b.entity_id=s.entity_b_id
            {where_sql}
            ORDER BY s.updated_at DESC, s.salience DESC, s.label ASC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            rows.append(dict(row))
    return {
        'ok': True,
        'entity_id': clean_entity_id,
        'query': clean_query,
        'limit': clean_limit,
        'rows': rows,
    }


def fetch_rp2_callback_anchor_debug_rows(*, entity_id: str = '', query: str = '', limit: int = 24) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_query = _clean(query)
    clean_limit = max(1, min(int(limit or 24), 200))
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_entity_id:
            where_parts.append('(c.entity_id=? OR c.builder_record_id=? OR c.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        if clean_query:
            where_parts.append('(c.label LIKE ? OR c.anchor_text LIKE ? OR c.callback_id LIKE ?)')
            wildcard = f'%{clean_query}%'
            params.extend([wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        query_sql = f'''
            SELECT
                c.callback_id, c.entity_id, e.label AS entity_label,
                c.label, c.anchor_text, c.salience, c.source_ref,
                c.builder_record_id, c.canon_id, c.updated_at
            FROM rp2_callback_anchors c
            LEFT JOIN rp2_entities e ON e.entity_id=c.entity_id
            {where_sql}
            ORDER BY c.updated_at DESC, c.salience DESC, c.label ASC
            LIMIT ?
        '''
        params.append(clean_limit)
        for row in conn.execute(query_sql, tuple(params)):
            rows.append(dict(row))
    return {
        'ok': True,
        'entity_id': clean_entity_id,
        'query': clean_query,
        'limit': clean_limit,
        'rows': rows,
    }


def _tokenize_runtime_query(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9']+", str(text or '').lower()) if token}


def _runtime_score_row(*, query_tokens: set[str], title: str, summary: str, text: str, salience: float) -> float:
    if not query_tokens:
        return round(float(salience or 0.0), 6)
    haystack_tokens = _tokenize_runtime_query(f'{title} {summary} {text}')
    if not haystack_tokens:
        return round(float(salience or 0.0) * 0.3, 6)
    overlap = len(query_tokens & haystack_tokens)
    overlap_bonus = overlap * 0.12
    title_bonus = 0.1 if any(token in _tokenize_runtime_query(title) for token in query_tokens) else 0.0
    summary_bonus = 0.06 if any(token in _tokenize_runtime_query(summary) for token in query_tokens) else 0.0
    return round(float(salience or 0.0) * 0.35 + overlap_bonus + title_bonus + summary_bonus, 6)


CONTINUITY_CALLBACK_CUES = {'remember', 'again', 'still', 'yet', 'owe', 'promise', 'promised', 'unfinished', 'later', 'return', 'echo', 'lingers', 'question', 'unresolved'}
CONTINUITY_RELATIONSHIP_CUES = {'trust', 'tension', 'love', 'hurt', 'distance', 'closer', 'cold', 'angry', 'jealous', 'afraid', 'comfort', 'together', 'between', 'bond'}


def _continuity_recovery_bias(*, query_tokens: set[str], memory_type: str = '', title: str = '', summary: str = '', text: str = '', source_ref: str = '') -> tuple[float, list[str]]:
    clean_type = _clean(memory_type)
    haystack_tokens = _tokenize_runtime_query(f'{title} {summary} {text} {source_ref}')
    if not haystack_tokens:
        return 0.0, []
    recovery_tags: list[str] = []
    bias = 0.0
    callback_overlap = len(query_tokens & CONTINUITY_CALLBACK_CUES)
    relationship_overlap = len(query_tokens & CONTINUITY_RELATIONSHIP_CUES)
    haystack_callback = len(haystack_tokens & CONTINUITY_CALLBACK_CUES)
    haystack_relationship = len(haystack_tokens & CONTINUITY_RELATIONSHIP_CUES)
    if clean_type in {'callback_anchor', 'thread_state'}:
        if callback_overlap or haystack_callback:
            bias += 0.18 + (0.03 * min(3, callback_overlap + haystack_callback))
            recovery_tags.append('callback_recovery')
        if 'thread' in clean_type or 'unresolved' in haystack_tokens:
            bias += 0.08
            recovery_tags.append('unresolved_thread')
    if clean_type in {'relationship_belief', 'shared_memory'}:
        if relationship_overlap or haystack_relationship:
            bias += 0.16 + (0.02 * min(3, relationship_overlap + haystack_relationship))
            recovery_tags.append('relationship_recovery')
    if clean_type == 'episodic_memory':
        overlap = len(query_tokens & haystack_tokens)
        if overlap >= 2:
            bias += 0.08
            recovery_tags.append('episodic_overlap')
    if source_ref and source_ref in text:
        bias += 0.03
        recovery_tags.append('source_ref_echo')
    return round(bias, 6), recovery_tags



def select_rp2_runtime_memory_rows(*, project_id: str = '', entity_id: str = '', query: str = '', limit: int = 8, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_query = _clean(query)
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    per_bucket_limit = max(1, min(int(limit or 8), 12))
    query_tokens = _tokenize_runtime_query(clean_query)
    grouped: dict[str, list[dict[str, Any]]] = {
        'world_facts': [],
        'episodic_memories': [],
        'canon_guards': [],
        'callback_anchors': [],
        'relationship_beliefs': [],
        'shared_memories': [],
    }
    candidate_count = 0
    selected_count = 0
    memory_type_map = {
        'semantic_fact': 'world_facts',
        'episodic_memory': 'episodic_memories',
        'canon_guard': 'canon_guards',
        'callback_anchor': 'callback_anchors',
        'thread_state': 'callback_anchors',
        'relationship_belief': 'relationship_beliefs',
    }
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_project_id:
            where_parts.append('m.project_id=?')
            params.append(clean_project_id)
        if clean_entity_id:
            where_parts.append('(m.entity_id=? OR m.builder_record_id=? OR m.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        _append_scope_where(where_parts, params, table_alias='m', scope_filters=scope_filters)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        fragment_sql = f'''            SELECT memory_id, entity_id, memory_type, title, summary, text, salience, tags_json, source_ref,
                   source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                   branch_id, memory_scope, promotion_scope, updated_at
            FROM rp2_memory_fragments m
            {where_sql}
            ORDER BY m.salience DESC, m.updated_at DESC
            LIMIT 120
        '''
        for row in conn.execute(fragment_sql, tuple(params)):
            candidate_count += 1
            memory_type_name = _clean(row['memory_type'])
            bucket = memory_type_map.get(memory_type_name)
            if not bucket:
                continue
            continuity_bias, recovery_tags = _continuity_recovery_bias(
                query_tokens=query_tokens,
                memory_type=memory_type_name,
                title=_clean(row['title']),
                summary=_clean(row['summary']),
                text=_clean(row['text']),
                source_ref=_clean(row['source_ref']),
            )
            compact = {
                'id': _clean(row['memory_id']),
                'memory_type': memory_type_name,
                'title': _clean(row['title']),
                'text': _clean(row['summary']) or _clean(row['text']),
                'source_ref': _clean(row['source_ref']),
                'salience': float(row['salience'] or 0.0),
                'tags': json.loads(row['tags_json'] or '[]') if str(row['tags_json'] or '').strip() else [],
                'score': round(_runtime_score_row(query_tokens=query_tokens, title=_clean(row['title']), summary=_clean(row['summary']), text=_clean(row['text']), salience=float(row['salience'] or 0.0)) + continuity_bias, 6),
                'continuity_bias': continuity_bias,
                'recovery_tags': recovery_tags,
                'source_backend': 'sqlite_bridge',
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': _clean(row['promotion_scope']).lower(),
            }
            grouped[bucket].append(compact)
        shared_where_parts = []
        shared_params: list[Any] = []
        if clean_project_id:
            shared_where_parts.append('s.project_id=?')
            shared_params.append(clean_project_id)
        if clean_entity_id:
            shared_where_parts.append('(s.entity_a_id=? OR s.entity_b_id=? OR s.builder_record_id=? OR s.source_ref=?)')
            shared_params.extend([clean_entity_id, clean_entity_id, clean_entity_id, clean_entity_id])
        _append_scope_where(shared_where_parts, shared_params, table_alias='s', scope_filters=scope_filters)
        shared_where_sql = f"WHERE {' AND '.join(shared_where_parts)}" if shared_where_parts else ''
        shared_sql = f'''            SELECT shared_memory_id, entity_a_id, entity_b_id, label, text, salience, source_ref,
                   source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                   branch_id, memory_scope, promotion_scope, updated_at
            FROM rp2_shared_memories s
            {shared_where_sql}
            ORDER BY s.salience DESC, s.updated_at DESC
            LIMIT 80
        '''
        for row in conn.execute(shared_sql, tuple(shared_params)):
            candidate_count += 1
            continuity_bias, recovery_tags = _continuity_recovery_bias(
                query_tokens=query_tokens,
                memory_type='shared_memory',
                title=_clean(row['label']),
                summary=_clean(row['text']),
                text=_clean(row['text']),
                source_ref=_clean(row['source_ref']),
            )
            compact = {
                'id': _clean(row['shared_memory_id']),
                'title': _clean(row['label']),
                'summary': _clean(row['text']),
                'participant_ids': [_clean(row['entity_a_id']), _clean(row['entity_b_id'])],
                'salience': float(row['salience'] or 0.0),
                'source_ref': _clean(row['source_ref']),
                'score': round(_runtime_score_row(query_tokens=query_tokens, title=_clean(row['label']), summary=_clean(row['text']), text=_clean(row['text']), salience=float(row['salience'] or 0.0)) + continuity_bias, 6),
                'continuity_bias': continuity_bias,
                'recovery_tags': recovery_tags,
                'source_backend': 'sqlite_bridge',
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': _clean(row['promotion_scope']).lower(),
            }
            grouped['shared_memories'].append(compact)
    for key in list(grouped.keys()):
        grouped[key].sort(key=lambda item: (float(item.get('score') or 0.0), float(item.get('salience') or 0.0)), reverse=True)
        grouped[key] = grouped[key][:per_bucket_limit]
        selected_count += len(grouped[key])
    return {
        'backend': 'sqlite_bridge_scaffold',
        'query': clean_query,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'scope_filters': dict(scope_filters),
        'candidate_count': candidate_count,
        'selected_count': selected_count,
        'results': grouped,
    }


def _shared_scope_match(*, promotion_scope: str, linked_world_id: str = '', linked_universe_id: str = '', row_world_id: str = '', row_universe_id: str = '') -> bool:
    clean_scope = _clean(promotion_scope).lower()
    if clean_scope == 'shared_world':
        return bool(_clean(linked_world_id) and _clean(row_world_id) and _clean(linked_world_id) == _clean(row_world_id))
    if clean_scope == 'shared_universe':
        return bool(_clean(linked_universe_id) and _clean(row_universe_id) and _clean(linked_universe_id) == _clean(row_universe_id))
    return False


def fetch_rp2_shared_continuity_rows(*, project_id: str = '', entity_id: str = '', query: str = '', limit: int = 8, linked_world_id: str = '', linked_universe_id: str = '', exclude_storyline_id: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_query = _clean(query)
    clean_exclude_storyline_id = _clean(exclude_storyline_id)
    query_tokens = _tokenize_runtime_query(clean_query)
    per_bucket_limit = max(1, min(int(limit or 8), 12))
    grouped: dict[str, list[dict[str, Any]]] = {
        'world_facts': [],
        'episodic_memories': [],
        'canon_guards': [],
        'callback_anchors': [],
        'relationship_beliefs': [],
        'shared_memories': [],
    }
    candidate_count = 0
    selected_count = 0
    memory_type_map = {
        'semantic_fact': 'world_facts',
        'episodic_memory': 'episodic_memories',
        'canon_guard': 'canon_guards',
        'callback_anchor': 'callback_anchors',
        'thread_state': 'callback_anchors',
        'relationship_belief': 'relationship_beliefs',
    }
    with sqlite_conn() as conn:
        where_parts = ["m.promotion_scope IN ('shared_world','shared_universe')"]
        params: list[Any] = []
        if clean_project_id:
            where_parts.append('m.project_id=?')
            params.append(clean_project_id)
        if clean_entity_id:
            where_parts.append('(m.entity_id=? OR m.builder_record_id=? OR m.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        if clean_exclude_storyline_id:
            where_parts.append('(m.storyline_id = "" OR m.storyline_id != ?)')
            params.append(clean_exclude_storyline_id)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        frag_sql = f'''
            SELECT memory_id, entity_id, builder_record_id, memory_type, title, summary, text, salience, tags_json, source_ref,
                   world_id, universe_id, storyline_id, session_id, checkpoint_id, branch_id, memory_scope, promotion_scope, fragment_json, updated_at
            FROM rp2_memory_fragments m
            {where_sql}
            ORDER BY m.salience DESC, m.updated_at DESC
            LIMIT 180
        '''
        for row in conn.execute(frag_sql, tuple(params)).fetchall():
            fragment_payload = _loads(row['fragment_json'], {}) if row['fragment_json'] else {}
            extra_payload = fragment_payload.get('extra') if isinstance(fragment_payload, dict) else {}
            row_world_id = _clean(row['world_id']) or _clean((extra_payload.get('shared_world_id') if isinstance(extra_payload, dict) else '') or (extra_payload.get('world_id') if isinstance(extra_payload, dict) else ''))
            row_universe_id = _clean(row['universe_id']) or _clean((extra_payload.get('shared_universe_id') if isinstance(extra_payload, dict) else '') or (extra_payload.get('universe_id') if isinstance(extra_payload, dict) else ''))
            promotion_scope = _clean(row['promotion_scope']).lower()
            if not _shared_scope_match(promotion_scope=promotion_scope, linked_world_id=linked_world_id, linked_universe_id=linked_universe_id, row_world_id=row_world_id, row_universe_id=row_universe_id):
                continue
            candidate_count += 1
            memory_type_name = _clean(row['memory_type'])
            bucket = memory_type_map.get(memory_type_name)
            if not bucket:
                continue
            continuity_bias, recovery_tags = _continuity_recovery_bias(
                query_tokens=query_tokens,
                memory_type=memory_type_name,
                title=_clean(row['title']),
                summary=_clean(row['summary']),
                text=_clean(row['text']),
                source_ref=_clean(row['source_ref']),
            )
            grouped[bucket].append({
                'id': _clean(row['memory_id']),
                'memory_type': memory_type_name,
                'title': _clean(row['title']),
                'text': _clean(row['summary']) or _clean(row['text']),
                'source_ref': _clean(row['source_ref']),
                'salience': float(row['salience'] or 0.0),
                'tags': json.loads(row['tags_json'] or '[]') if str(row['tags_json'] or '').strip() else [],
                'score': round(_runtime_score_row(query_tokens=query_tokens, title=_clean(row['title']), summary=_clean(row['summary']), text=_clean(row['text']), salience=float(row['salience'] or 0.0)) + continuity_bias, 6),
                'continuity_bias': continuity_bias,
                'recovery_tags': recovery_tags,
                'source_backend': 'shared_continuity',
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': promotion_scope,
                'shared_world_id': row_world_id,
                'shared_universe_id': row_universe_id,
            })
        shared_where_parts = ["s.promotion_scope IN ('shared_world','shared_universe')"]
        shared_params: list[Any] = []
        if clean_project_id:
            shared_where_parts.append('s.project_id=?')
            shared_params.append(clean_project_id)
        if clean_entity_id:
            shared_where_parts.append('(s.entity_a_id=? OR s.entity_b_id=? OR s.builder_record_id=? OR s.source_ref=?)')
            shared_params.extend([clean_entity_id, clean_entity_id, clean_entity_id, clean_entity_id])
        if clean_exclude_storyline_id:
            shared_where_parts.append('(s.storyline_id = "" OR s.storyline_id != ?)')
            shared_params.append(clean_exclude_storyline_id)
        shared_where_sql = f"WHERE {' AND '.join(shared_where_parts)}" if shared_where_parts else ''
        shared_sql = f'''
            SELECT shared_memory_id, entity_a_id, entity_b_id, label, text, salience, source_ref,
                   storyline_id, session_id, checkpoint_id, branch_id, memory_scope, promotion_scope, memory_json, updated_at
            FROM rp2_shared_memories s
            {shared_where_sql}
            ORDER BY s.salience DESC, s.updated_at DESC
            LIMIT 120
        '''
        for row in conn.execute(shared_sql, tuple(shared_params)).fetchall():
            shared_payload = _loads(row['memory_json'], {}) if row['memory_json'] else {}
            extra_payload = shared_payload.get('extra') if isinstance(shared_payload, dict) else {}
            row_world_id = _clean((extra_payload.get('shared_world_id') if isinstance(extra_payload, dict) else '') or (extra_payload.get('world_id') if isinstance(extra_payload, dict) else ''))
            row_universe_id = _clean((extra_payload.get('shared_universe_id') if isinstance(extra_payload, dict) else '') or (extra_payload.get('universe_id') if isinstance(extra_payload, dict) else ''))
            promotion_scope = _clean(row['promotion_scope']).lower()
            if not _shared_scope_match(promotion_scope=promotion_scope, linked_world_id=linked_world_id, linked_universe_id=linked_universe_id, row_world_id=row_world_id, row_universe_id=row_universe_id):
                continue
            candidate_count += 1
            continuity_bias, recovery_tags = _continuity_recovery_bias(
                query_tokens=query_tokens,
                memory_type='shared_memory',
                title=_clean(row['label']),
                summary=_clean(row['text']),
                text=_clean(row['text']),
                source_ref=_clean(row['source_ref']),
            )
            grouped['shared_memories'].append({
                'id': _clean(row['shared_memory_id']),
                'title': _clean(row['label']),
                'summary': _clean(row['text']),
                'participant_ids': [_clean(row['entity_a_id']), _clean(row['entity_b_id'])],
                'salience': float(row['salience'] or 0.0),
                'source_ref': _clean(row['source_ref']),
                'score': round(_runtime_score_row(query_tokens=query_tokens, title=_clean(row['label']), summary=_clean(row['text']), text=_clean(row['text']), salience=float(row['salience'] or 0.0)) + continuity_bias, 6),
                'continuity_bias': continuity_bias,
                'recovery_tags': recovery_tags,
                'source_backend': 'shared_continuity',
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': promotion_scope,
                'shared_world_id': row_world_id,
                'shared_universe_id': row_universe_id,
            })
    for key in list(grouped.keys()):
        grouped[key].sort(key=lambda item: (float(item.get('score') or 0.0), float(item.get('salience') or 0.0)), reverse=True)
        grouped[key] = grouped[key][:per_bucket_limit]
        selected_count += len(grouped[key])
    return {
        'ok': True,
        'backend': 'shared_continuity_bridge',
        'query': clean_query,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'linked_world_id': _clean(linked_world_id),
        'linked_universe_id': _clean(linked_universe_id),
        'exclude_storyline_id': clean_exclude_storyline_id,
        'candidate_count': candidate_count,
        'selected_count': selected_count,
        'results': grouped,
    }


def fetch_rp2_shared_relationship_state_rows(*, entity_id: str = '', project_id: str = '', limit: int = 6, linked_world_id: str = '', linked_universe_id: str = '', exclude_storyline_id: str = '') -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    clean_entity_id = _clean(entity_id)
    clean_project_id = _clean(project_id)
    clean_exclude_storyline_id = _clean(exclude_storyline_id)
    rows: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        where_parts = ["promotion_scope IN ('shared_world','shared_universe')"]
        params: list[Any] = []
        if clean_project_id:
            where_parts.append('project_id = ?')
            params.append(clean_project_id)
        if clean_entity_id:
            where_parts.append('(source_entity_id = ? OR target_entity_id = ?)')
            params.extend([clean_entity_id, clean_entity_id])
        if clean_exclude_storyline_id:
            where_parts.append('(storyline_id = "" OR storyline_id != ?)')
            params.append(clean_exclude_storyline_id)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        sql = f'''
            SELECT relationship_state_id, source_entity_id, target_entity_id, project_id, bundle_id, source_ref,
                   relationship_label, summary, trust_level, tension_level, drift_score, carry_forward,
                   source_snapshot_id, canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                   branch_id, memory_scope, promotion_scope, state_json, created_at, updated_at
            FROM rp2_relationship_state
            {where_sql}
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
        '''
        params.append(max(1, min(int(limit or 6), 40)) * 8)
        for row in conn.execute(sql, tuple(params)).fetchall():
            payload = _loads(row['state_json'], {}) if row['state_json'] else {}
            row_world_id = _clean((payload.get('shared_world_id') if isinstance(payload, dict) else '') or (payload.get('world_id') if isinstance(payload, dict) else ''))
            row_universe_id = _clean((payload.get('shared_universe_id') if isinstance(payload, dict) else '') or (payload.get('universe_id') if isinstance(payload, dict) else ''))
            promotion_scope = _clean(row['promotion_scope']).lower()
            if not _shared_scope_match(promotion_scope=promotion_scope, linked_world_id=linked_world_id, linked_universe_id=linked_universe_id, row_world_id=row_world_id, row_universe_id=row_universe_id):
                continue
            rows.append({
                'relationship_state_id': _clean(row['relationship_state_id']),
                'source_entity_id': _clean(row['source_entity_id']),
                'target_entity_id': _clean(row['target_entity_id']),
                'project_id': _clean(row['project_id']),
                'bundle_id': _clean(row['bundle_id']),
                'source_ref': _clean(row['source_ref']),
                'relationship_label': _clean(row['relationship_label']),
                'summary': _clean(row['summary']),
                'trust_level': float(row['trust_level'] or 0.0),
                'tension_level': float(row['tension_level'] or 0.0),
                'drift_score': float(row['drift_score'] or 0.0),
                'carry_forward': bool(int(row['carry_forward'] or 0)),
                'source_snapshot_id': _clean(row['source_snapshot_id']),
                'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                'sandbox_id': _clean(row['sandbox_id']),
                'storyline_id': _clean(row['storyline_id']),
                'session_id': _clean(row['session_id']),
                'checkpoint_id': _clean(row['checkpoint_id']),
                'branch_id': _clean(row['branch_id']),
                'memory_scope': _clean(row['memory_scope']).lower(),
                'promotion_scope': promotion_scope,
                'state_payload': payload if isinstance(payload, dict) else {},
                'shared_world_id': row_world_id,
                'shared_universe_id': row_universe_id,
                'created_at': _clean(row['created_at']),
                'updated_at': _clean(row['updated_at']),
            })
            if len(rows) >= max(1, min(int(limit or 6), 40)):
                break
    return {
        'ok': True,
        'rows': rows,
        'count': len(rows),
        'entity_id': clean_entity_id,
        'project_id': clean_project_id,
        'linked_world_id': _clean(linked_world_id),
        'linked_universe_id': _clean(linked_universe_id),
        'exclude_storyline_id': clean_exclude_storyline_id,
    }


def fetch_rp2_chroma_status() -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    embedding_status = get_embedding_backend_status()
    chroma_ready = bool(ensure_chroma_foundation())
    scope_fields = list(RP2_SCOPE_FILTER_FIELD_MAP.keys())
    resolved_collection = _clean((embedding_status.get('resolved_collections') or {}).get('roleplay_v2')) or ROLEPLAY_V2_COLLECTION
    if chroma_ready:
        state = 'ready'
        badge_label = 'ready'
        summary = f"{_clean(embedding_status.get('active_backend_label')) or 'Memory backend'} ready. SQLite memory can sync into {resolved_collection} and semantic preview is available."
        action_hint = 'Use Sync SQLite → Chroma after large memory changes if you want the mirror refreshed immediately.'
    elif _clean(embedding_status.get('storage_mode')) == 'sqlite_only':
        state = 'sqlite_only'
        badge_label = 'sqlite only'
        summary = 'Chroma mirror is unavailable in this environment. Roleplay V2 still keeps memory in SQLite, but mirror sync and semantic preview are offline.'
        action_hint = 'You can keep compiling and running from SQLite-backed memory. Bring Chroma back later if you want semantic preview.'
    else:
        state = 'degraded'
        badge_label = 'degraded'
        summary = 'The Chroma mirror is not ready yet. SQLite memory is still intact, but semantic preview and mirror sync are not healthy right now.'
        action_hint = 'Refresh status again after the embedding backend and Chroma foundation finish loading.'
    return {
        'ok': True,
        'chroma_ready': chroma_ready,
        'state': state,
        'badge_label': badge_label,
        'summary': summary,
        'action_hint': action_hint,
        'embedding_status': embedding_status,
        'sqlite_overview': fetch_rp2_sqlite_overview(),
        'collection': ROLEPLAY_V2_COLLECTION,
        'resolved_collection': resolved_collection,
        'storage_mode': embedding_status.get('storage_mode'),
        'storage_mode_label': embedding_status.get('storage_mode_label'),
        'scope_metadata_fields': scope_fields,
        'scope_metadata_ready': chroma_ready,
        'semantic_preview_available': chroma_ready,
        'sync_available': chroma_ready,
    }


def sync_rp2_memory_to_chroma(*, project_id: str = '', entity_id: str = '', limit: int = 500) -> dict[str, Any]:
    ensure_roleplay_v2_sqlite_backbone()
    chroma_ready = bool(ensure_chroma_foundation())
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_limit = max(1, min(int(limit or 500), 2000))
    chunks: list[dict[str, Any]] = []
    if not chroma_ready:
        embedding_status = get_embedding_backend_status()
        return {
            'ok': False,
            'collection': ROLEPLAY_V2_COLLECTION,
            'resolved_collection': _clean((embedding_status.get('resolved_collections') or {}).get('roleplay_v2')) or ROLEPLAY_V2_COLLECTION,
            'indexed': 0,
            'reason': 'chroma_unavailable',
            'state': 'sqlite_only' if _clean(embedding_status.get('storage_mode')) == 'sqlite_only' else 'degraded',
            'message': 'Chroma mirror is unavailable right now. Roleplay V2 memory still stays durable in SQLite; sync can run again once Chroma is available.',
            'embedding_status': embedding_status,
        }
    with sqlite_conn() as conn:
        where_parts = []
        params: list[Any] = []
        if clean_project_id:
            where_parts.append('m.project_id=?')
            params.append(clean_project_id)
        if clean_entity_id:
            where_parts.append('(m.entity_id=? OR m.builder_record_id=? OR m.source_ref=?)')
            params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
        sql = f'''
            SELECT memory_id AS chunk_id, entity_id, project_id, builder_record_id, canon_id, source_ref,
                   memory_type, title, summary, text, salience, tags_json, source_snapshot_id,
                   canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                   branch_id, memory_scope, promotion_scope, updated_at
            FROM rp2_memory_fragments m
            {where_sql}
            ORDER BY m.updated_at DESC, m.salience DESC
            LIMIT ?
        '''
        local_params = list(params) + [clean_limit]
        for row in conn.execute(sql, tuple(local_params)):
            document = '\n'.join(part for part in [_clean(row['title']), _clean(row['summary']), _clean(row['text'])] if part)
            if not document:
                continue
            chunks.append({
                'id': _clean(row['chunk_id']),
                'document': document,
                'metadata': {
                    'chunk_type': 'memory_fragment',
                    'entity_id': _clean(row['entity_id']),
                    'project_id': _clean(row['project_id']),
                    'builder_record_id': _clean(row['builder_record_id']),
                    'canon_id': _clean(row['canon_id']),
                    'source_ref': _clean(row['source_ref']),
                    'memory_type': _clean(row['memory_type']),
                    'title': _clean(row['title']),
                    'salience': float(row['salience'] or 0.0),
                    'source_snapshot_id': _clean(row['source_snapshot_id']),
                    'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                    'sandbox_id': _clean(row['sandbox_id']),
                    'storyline_id': _clean(row['storyline_id']),
                    'session_id': _clean(row['session_id']),
                    'checkpoint_id': _clean(row['checkpoint_id']),
                    'branch_id': _clean(row['branch_id']),
                    'memory_scope': _clean(row['memory_scope']),
                    'promotion_scope': _clean(row['promotion_scope']),
                    'updated_at': _clean(row['updated_at']),
                },
            })
        shared_where_parts = []
        shared_params: list[Any] = []
        if clean_project_id:
            shared_where_parts.append('s.project_id=?')
            shared_params.append(clean_project_id)
        if clean_entity_id:
            shared_where_parts.append('(s.entity_a_id=? OR s.entity_b_id=? OR s.builder_record_id=? OR s.source_ref=?)')
            shared_params.extend([clean_entity_id, clean_entity_id, clean_entity_id, clean_entity_id])
        shared_where_sql = f"WHERE {' AND '.join(shared_where_parts)}" if shared_where_parts else ''
        shared_sql = f'''
            SELECT shared_memory_id AS chunk_id, entity_a_id, entity_b_id, project_id, builder_record_id,
                   canon_id, source_ref, label, text, salience, source_snapshot_id,
                   canon_snapshot_id, sandbox_id, storyline_id, session_id, checkpoint_id,
                   branch_id, memory_scope, promotion_scope, updated_at
            FROM rp2_shared_memories s
            {shared_where_sql}
            ORDER BY s.updated_at DESC, s.salience DESC
            LIMIT ?
        '''
        for row in conn.execute(shared_sql, tuple(list(shared_params) + [max(50, clean_limit // 2)])):
            document = '\n'.join(part for part in [_clean(row['label']), _clean(row['text'])] if part)
            if not document:
                continue
            chunks.append({
                'id': _clean(row['chunk_id']),
                'document': document,
                'metadata': {
                    'chunk_type': 'shared_memory',
                    'entity_id': _clean(row['entity_a_id']) or _clean(row['entity_b_id']),
                    'entity_a_id': _clean(row['entity_a_id']),
                    'entity_b_id': _clean(row['entity_b_id']),
                    'project_id': _clean(row['project_id']),
                    'builder_record_id': _clean(row['builder_record_id']),
                    'canon_id': _clean(row['canon_id']),
                    'source_ref': _clean(row['source_ref']),
                    'memory_type': 'shared_memory',
                    'title': _clean(row['label']),
                    'salience': float(row['salience'] or 0.0),
                    'source_snapshot_id': _clean(row['source_snapshot_id']),
                    'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                    'sandbox_id': _clean(row['sandbox_id']),
                    'storyline_id': _clean(row['storyline_id']),
                    'session_id': _clean(row['session_id']),
                    'checkpoint_id': _clean(row['checkpoint_id']),
                    'branch_id': _clean(row['branch_id']),
                    'memory_scope': _clean(row['memory_scope']),
                    'promotion_scope': _clean(row['promotion_scope']),
                    'updated_at': _clean(row['updated_at']),
                },
            })
        callback_where_parts = []
        callback_params: list[Any] = []
        if clean_project_id:
            callback_where_parts.append('c.project_id=?')
            callback_params.append(clean_project_id)
        if clean_entity_id:
            callback_where_parts.append('(c.entity_id=? OR c.builder_record_id=? OR c.source_ref=?)')
            callback_params.extend([clean_entity_id, clean_entity_id, clean_entity_id])
        callback_where_sql = f"WHERE {' AND '.join(callback_where_parts)}" if callback_where_parts else ''
        callback_sql = f'''
            SELECT callback_id AS chunk_id, entity_id, project_id, builder_record_id, canon_id,
                   source_ref, label, anchor_text, salience, source_snapshot_id, canon_snapshot_id,
                   sandbox_id, storyline_id, session_id, checkpoint_id, branch_id, memory_scope,
                   promotion_scope, updated_at
            FROM rp2_callback_anchors c
            {callback_where_sql}
            ORDER BY c.updated_at DESC, c.salience DESC
            LIMIT ?
        '''
        for row in conn.execute(callback_sql, tuple(list(callback_params) + [max(50, clean_limit // 2)])):
            document = '\\n'.join(part for part in [_clean(row['label']), _clean(row['anchor_text'])] if part)
            if not document:
                continue
            callback_id = _clean(row['chunk_id'])
            chunks.append({
                'id': f"cb_{callback_id}" if callback_id else '',
                'document': document,
                'metadata': {
                    'chunk_type': 'callback_anchor',
                    'entity_id': _clean(row['entity_id']),
                    'project_id': _clean(row['project_id']),
                    'builder_record_id': _clean(row['builder_record_id']),
                    'canon_id': _clean(row['canon_id']),
                    'source_ref': _clean(row['source_ref']),
                    'memory_type': 'callback_anchor',
                    'title': _clean(row['label']),
                    'salience': float(row['salience'] or 0.0),
                    'callback_id': callback_id,
                    'source_chunk_id': callback_id,
                    'source_snapshot_id': _clean(row['source_snapshot_id']),
                    'canon_snapshot_id': _clean(row['canon_snapshot_id']),
                    'sandbox_id': _clean(row['sandbox_id']),
                    'storyline_id': _clean(row['storyline_id']),
                    'session_id': _clean(row['session_id']),
                    'checkpoint_id': _clean(row['checkpoint_id']),
                    'branch_id': _clean(row['branch_id']),
                    'memory_scope': _clean(row['memory_scope']),
                    'promotion_scope': _clean(row['promotion_scope']),
                    'updated_at': _clean(row['updated_at']),
                },
            })
    chunks.sort(key=lambda item: float((item.get('metadata') or {}).get('salience') or 0.0), reverse=True)
    deduped_chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    for chunk in chunks:
        chunk_id = _clean(chunk.get('id'))
        if not chunk_id or chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        deduped_chunks.append(chunk)
    chunks = deduped_chunks[:clean_limit]
    # Upsert alone leaves old Chroma ids behind when recompiled text changes.
    # Clear the active compile scope first, then mirror the current SQLite rows.
    chroma_prune_ok = delete_memory_chunks_for_scope(
        ROLEPLAY_V2_COLLECTION,
        entity_id=clean_entity_id,
        builder_record_id=clean_entity_id,
        source_ref=clean_entity_id,
    ) if clean_entity_id else True
    indexed_ok = upsert_memory_chunks(ROLEPLAY_V2_COLLECTION, chunks)
    embedding_status = get_embedding_backend_status()
    resolved_collection = _clean((embedding_status.get('resolved_collections') or {}).get('roleplay_v2')) or ROLEPLAY_V2_COLLECTION
    return {
        'ok': bool(indexed_ok),
        'collection': ROLEPLAY_V2_COLLECTION,
        'resolved_collection': resolved_collection,
        'indexed': len(chunks) if indexed_ok else 0,
        'pruned_existing_chroma_scope': bool(chroma_prune_ok),
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'message': f"Mirrored {len(chunks) if indexed_ok else 0} SQLite memory row(s) into {resolved_collection}." if indexed_ok else 'Chroma mirror sync did not index any rows.',
        'embedding_status': embedding_status,
    }


def query_rp2_chroma_debug(*, query_text: str, project_id: str = '', entity_id: str = '', limit: int = 12, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    clean_query = _clean(query_text)
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_limit = max(1, min(int(limit or 12), 50))
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    if not clean_query:
        return {'ok': True, 'query_text': '', 'rows': [], 'collection': ROLEPLAY_V2_COLLECTION, 'scope_filters': scope_filters}
    multiplier = 5 if scope_filters else 2
    rows = query_memory(ROLEPLAY_V2_COLLECTION, query_text=clean_query, n_results=min(100, clean_limit * multiplier))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        meta = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
        if clean_project_id and _clean(meta.get('project_id')) != clean_project_id:
            continue
        if clean_entity_id and clean_entity_id not in {_clean(meta.get('entity_id')), _clean(meta.get('entity_a_id')), _clean(meta.get('entity_b_id')), _clean(meta.get('builder_record_id')), _clean(meta.get('source_ref'))}:
            continue
        scope_match = True
        for field_name, expected in scope_filters.items():
            if _scope_value(field_name, meta.get(field_name)) != expected:
                scope_match = False
                break
        if not scope_match:
            continue
        filtered.append({
            'id': _clean(row.get('id')),
            'document': _clean(row.get('document')),
            'distance': row.get('distance'),
            'metadata': meta,
            'source': _clean(row.get('source')) or 'chroma',
        })
        if len(filtered) >= clean_limit:
            break
    return {
        'ok': True,
        'collection': ROLEPLAY_V2_COLLECTION,
        'query_text': clean_query,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'scope_filters': scope_filters,
        'rows': filtered,
        'embedding_status': get_embedding_backend_status(),
    }



def _runtime_bucket_for_meta(memory_type: str = '', chunk_type: str = '') -> str:
    clean_type = _clean(memory_type)
    clean_chunk_type = _clean(chunk_type)
    mapping = {
        'semantic_fact': 'world_facts',
        'episodic_memory': 'episodic_memories',
        'canon_guard': 'canon_guards',
        'callback_anchor': 'callback_anchors',
        'thread_state': 'callback_anchors',
        'relationship_belief': 'relationship_beliefs',
        'shared_memory': 'shared_memories',
    }
    return mapping.get(clean_type) or mapping.get(clean_chunk_type) or ''



def select_rp2_hybrid_runtime_memory_rows(*, project_id: str = '', entity_id: str = '', query: str = '', limit: int = 8, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    sqlite_rows = select_rp2_runtime_memory_rows(
        project_id=project_id,
        entity_id=entity_id,
        query=query,
        limit=limit,
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    clean_query = _clean(query)
    clean_project_id = _clean(project_id)
    clean_entity_id = _clean(entity_id)
    clean_limit = max(1, min(int(limit or 8), 12))
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    grouped: dict[str, list[dict[str, Any]]] = {
        'world_facts': [],
        'episodic_memories': [],
        'canon_guards': [],
        'callback_anchors': [],
        'relationship_beliefs': [],
        'shared_memories': [],
    }
    candidate_count = 0
    if clean_query:
        rows = query_memory(ROLEPLAY_V2_COLLECTION, query_text=clean_query, n_results=max(clean_limit * 10, 24))
        query_tokens = _tokenize_runtime_query(clean_query)
        for row in rows:
            meta = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
            if clean_project_id and _clean(meta.get('project_id')) != clean_project_id:
                continue
            if clean_entity_id and clean_entity_id not in {
                _clean(meta.get('entity_id')),
                _clean(meta.get('entity_a_id')),
                _clean(meta.get('entity_b_id')),
                _clean(meta.get('builder_record_id')),
                _clean(meta.get('source_ref')),
            }:
                continue
            scope_mismatch = False
            for field_name, expected in scope_filters.items():
                actual = _clean(meta.get(field_name), lower=field_name in {'memory_scope', 'promotion_scope'})
                if actual != expected:
                    scope_mismatch = True
                    break
            if scope_mismatch:
                continue
            bucket = _runtime_bucket_for_meta(meta.get('memory_type'), meta.get('chunk_type'))
            if not bucket:
                continue
            candidate_count += 1
            distance = row.get('distance')
            semantic_score = 0.0
            if isinstance(distance, (int, float)):
                semantic_score = round(1.0 - float(distance), 6)
            memory_type_name = _clean(meta.get('memory_type')) or _clean(meta.get('chunk_type'))
            lexical_score = _runtime_score_row(
                query_tokens=query_tokens,
                title=_clean(meta.get('title')) or _clean(row.get('id')),
                summary=_clean(row.get('document'))[:220],
                text=_clean(row.get('document'))[:600],
                salience=float(meta.get('salience') or 0.0),
            )
            continuity_bias, recovery_tags = _continuity_recovery_bias(
                query_tokens=query_tokens,
                memory_type=memory_type_name,
                title=_clean(meta.get('title')) or _clean(row.get('id')),
                summary=_clean(row.get('document'))[:220],
                text=_clean(row.get('document'))[:600],
                source_ref=_clean(meta.get('source_ref')),
            )
            compact = {
                'id': _clean(row.get('id')),
                'memory_type': memory_type_name,
                'title': _clean(meta.get('title')) or _clean(row.get('id')),
                'text': _clean(row.get('document'))[:600],
                'source_ref': _clean(meta.get('source_ref')),
                'salience': float(meta.get('salience') or 0.0),
                'tags': [tag for tag in [meta.get('memory_type'), meta.get('chunk_type')] if _clean(tag)],
                'score': round((semantic_score * 0.65) + (lexical_score * 0.35) + continuity_bias, 6),
                'continuity_bias': continuity_bias,
                'recovery_tags': recovery_tags,
                'semantic_score': semantic_score,
                'lexical_score': lexical_score,
                'source_backend': 'chroma_bridge',
                'source_snapshot_id': _clean(meta.get('source_snapshot_id')),
                'canon_snapshot_id': _clean(meta.get('canon_snapshot_id')),
                'sandbox_id': _clean(meta.get('sandbox_id')),
                'storyline_id': _clean(meta.get('storyline_id')),
                'session_id': _clean(meta.get('session_id')),
                'checkpoint_id': _clean(meta.get('checkpoint_id')),
                'branch_id': _clean(meta.get('branch_id')),
                'memory_scope': _clean(meta.get('memory_scope')).lower(),
                'promotion_scope': _clean(meta.get('promotion_scope')).lower(),
            }
            if bucket == 'shared_memories':
                compact['summary'] = _clean(row.get('document'))[:360]
                compact['participant_ids'] = [_clean(meta.get('entity_a_id')), _clean(meta.get('entity_b_id'))]
            grouped[bucket].append(compact)
    selected_count = 0
    for key in list(grouped.keys()):
        grouped[key].sort(key=lambda item: (float(item.get('score') or 0.0), float(item.get('salience') or 0.0)), reverse=True)
        grouped[key] = grouped[key][:clean_limit]
        selected_count += len(grouped[key])
    return {
        'backend': 'sqlite_chroma_hybrid_scaffold',
        'query': clean_query,
        'project_id': clean_project_id,
        'entity_id': clean_entity_id,
        'scope_filters': dict(scope_filters),
        'candidate_count': int(sqlite_rows.get('candidate_count') or 0) + candidate_count,
        'selected_count': int(sqlite_rows.get('selected_count') or 0) + selected_count,
        'sqlite_bridge': sqlite_rows,
        'chroma_bridge': {
            'backend': 'chroma_bridge_scaffold',
            'candidate_count': candidate_count,
            'selected_count': selected_count,
            'scope_filters': dict(scope_filters),
            'results': grouped,
            'recovery_backend': 'semantic_continuity_tuned_scaffold',
        },
    }

