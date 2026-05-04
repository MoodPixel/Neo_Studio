from __future__ import annotations

from pathlib import Path

from ..contracts.memory_records import normalize_memory_health_snapshot
from .assistant_store import PROJECTS_DIR, SESSIONS_DIR, SESSIONS_INDEX_PATH, list_sessions
from .memory_service.sqlite_store import fetch_memory_admin_overview, fetch_summary_records
from .roleplay_foundation import ROLEPLAY_PARTS_DIR, ROLEPLAY_SESSIONS_DIR


def _count_json_files(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return len([item for item in path.iterdir() if item.is_file() and item.suffix.lower() == '.json'])


def build_memory_health_snapshot() -> dict:
    assistant_session_files = _count_json_files(SESSIONS_DIR)
    assistant_projects = _count_json_files(PROJECTS_DIR)
    assistant_index_rows = len(list_sessions())
    roleplay_part_files = _count_json_files(ROLEPLAY_PARTS_DIR)
    latest_roleplay_session = ROLEPLAY_SESSIONS_DIR / 'latest_session.json'
    overview = fetch_memory_admin_overview()
    summaries = fetch_summary_records(limit=1000)
    totals = overview.get('totals') if isinstance(overview.get('totals'), dict) else {}
    issues: list[str] = []
    if assistant_session_files and assistant_index_rows != assistant_session_files:
        issues.append(f'Assistant session index mismatch: {assistant_index_rows} indexed vs {assistant_session_files} session files.')
    if not latest_roleplay_session.exists() and roleplay_part_files:
        issues.append('Roleplay latest session snapshot is missing while roleplay part files exist.')
    if int(totals.get('all') or 0) == 0 and (assistant_session_files or roleplay_part_files):
        issues.append('Memory chunk store is empty even though assistant or roleplay data files exist.')
    return normalize_memory_health_snapshot({
        'assistant_session_files': assistant_session_files,
        'assistant_index_rows': assistant_index_rows,
        'assistant_projects': assistant_projects,
        'roleplay_part_files': roleplay_part_files,
        'roleplay_latest_session_present': latest_roleplay_session.exists(),
        'memory_chunks_total': int(totals.get('all') or 0),
        'memory_chunks_assistant': int(totals.get('assistant') or 0),
        'memory_chunks_roleplay': int(totals.get('roleplay') or 0),
        'summary_records_count': len(summaries),
        'issues': issues,
    })
