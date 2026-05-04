from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_memory_manifest(*, lane: str, scope_type: str, scope_id: str, summary_text: str = '', message_count: int = 0, updated_at: str = '', source_json_path: str = '', extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'memory_manifest',
        'lane': str(lane or '').strip().lower(),
        'scope_type': str(scope_type or '').strip().lower(),
        'scope_id': str(scope_id or '').strip(),
        'summary_text': str(summary_text or '').strip()[:6000],
        'summary_char_count': len(str(summary_text or '').strip()[:6000]),
        'message_count': max(0, int(message_count or 0)),
        'updated_at': str(updated_at or _now_iso()).strip(),
        'source_json_path': str(source_json_path or '').strip(),
        'extra': extra if isinstance(extra, dict) else {},
    }


def normalize_session_index_entry(lane: str, row: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(row or {}), **overrides}
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'session_index_entry',
        'lane': str(lane or raw.get('lane') or '').strip().lower(),
        'id': str(raw.get('id') or '').strip(),
        'title': str(raw.get('title') or '').strip(),
        'mode': str(raw.get('mode') or '').strip().lower(),
        'updated_at': str(raw.get('updated_at') or '').strip(),
        'created_at': str(raw.get('created_at') or '').strip(),
        'message_count': max(0, int(raw.get('message_count') or 0)),
        'preview': str(raw.get('preview') or '').strip()[:180],
        'project_id': str(raw.get('project_id') or '').strip(),
        'helper_label': str(raw.get('helper_label') or '').strip()[:120],
        'context_count': max(0, int(raw.get('context_count') or 0)),
    }


def normalize_memory_health_snapshot(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'memory_health_snapshot',
        'assistant_session_files': max(0, int(raw.get('assistant_session_files') or 0)),
        'assistant_index_rows': max(0, int(raw.get('assistant_index_rows') or 0)),
        'assistant_projects': max(0, int(raw.get('assistant_projects') or 0)),
        'roleplay_part_files': max(0, int(raw.get('roleplay_part_files') or 0)),
        'roleplay_latest_session_present': bool(raw.get('roleplay_latest_session_present', False)),
        'memory_chunks_total': max(0, int(raw.get('memory_chunks_total') or 0)),
        'memory_chunks_assistant': max(0, int(raw.get('memory_chunks_assistant') or 0)),
        'memory_chunks_roleplay': max(0, int(raw.get('memory_chunks_roleplay') or 0)),
        'summary_records_count': max(0, int(raw.get('summary_records_count') or 0)),
        'issues': [str(item).strip() for item in (raw.get('issues') or []) if str(item).strip()],
        'updated_at': str(raw.get('updated_at') or _now_iso()).strip(),
    }
