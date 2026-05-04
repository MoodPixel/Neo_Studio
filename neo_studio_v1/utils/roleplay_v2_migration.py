from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .roleplay_v2_foundation import (
    ROLEPLAY_V2_ENTITIES_DIR,
    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR,
    ROLEPLAY_V2_SHARED_MEMORIES_DIR,
    ROLEPLAY_V2_STORY_SESSIONS_DIR,
    ROLEPLAY_V2_STORY_CHECKPOINTS_DIR,
)
from .roleplay_v2_sqlite_store import (
    fetch_rp2_chroma_status,
    fetch_rp2_sqlite_overview,
    sync_rp2_entities_from_directory,
    sync_rp2_memory_to_chroma,
    upsert_rp2_memory_outputs,
    upsert_rp2_scene_checkpoint_record,
    upsert_rp2_story_session_record,
)
from .storage_io import atomic_write_json, read_json_object

MIGRATION_REPORT_PATH = Path(__file__).resolve().parents[2] / 'devtools' / 'migrations' / 'roleplay_v2_phase14_last_run.json'


def _count_json_files(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return len(list(path.glob('*.json')))


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    path.mkdir(parents=True, exist_ok=True)
    for item in sorted(path.glob('*.json')):
        row = read_json_object(item, None)
        if isinstance(row, dict):
            out.append(row)
    return out


def _cleanup_profile(sqlite_overview: dict[str, Any] | None = None, chroma_status: dict[str, Any] | None = None) -> dict[str, Any]:
    overview = deepcopy(sqlite_overview) if isinstance(sqlite_overview, dict) else fetch_rp2_sqlite_overview()
    chroma = deepcopy(chroma_status) if isinstance(chroma_status, dict) else fetch_rp2_chroma_status()
    sqlite_ready = int(overview.get('entity_count') or 0) > 0 and int(overview.get('memory_fragment_count') or 0) > 0
    chroma_ready = bool(chroma.get('chroma_ready')) and sqlite_ready
    file_index_multiplier = 0.82 if sqlite_ready else 1.0
    file_store_multiplier = 0.84 if sqlite_ready else 1.0
    if chroma_ready:
        file_index_multiplier *= 0.78
        file_store_multiplier *= 0.8
    notes = []
    if sqlite_ready:
        notes.append('SQLite is carrying real V2 entity + memory rows, so legacy file retrieval can be downgraded.')
    else:
        notes.append('SQLite still needs a builder/memory backfill before legacy file retrieval should be trusted less.')
    if chroma_ready:
        notes.append('Chroma mirror is ready, so semantic recall can shoulder more of the continuity load.')
    else:
        notes.append('Chroma mirror is not ready yet; keep semantic cleanup partial until the mirror is synced.')
    return {
        'sqlite_ready': sqlite_ready,
        'chroma_ready': chroma_ready,
        'downgrade_legacy_file_index': sqlite_ready,
        'downgrade_legacy_file_store': sqlite_ready,
        'file_index_multiplier': round(float(file_index_multiplier), 4),
        'file_store_multiplier': round(float(file_store_multiplier), 4),
        'notes': notes,
    }


def build_phase14_migration_status() -> dict[str, Any]:
    sqlite_overview = fetch_rp2_sqlite_overview()
    chroma_status = fetch_rp2_chroma_status()
    inventory = {
        'entities': _count_json_files(ROLEPLAY_V2_ENTITIES_DIR),
        'memory_fragments': _count_json_files(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR),
        'shared_memories': _count_json_files(ROLEPLAY_V2_SHARED_MEMORIES_DIR),
        'story_sessions': _count_json_files(ROLEPLAY_V2_STORY_SESSIONS_DIR),
        'story_checkpoints': _count_json_files(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR),
    }
    scope_columns = sqlite_overview.get('scope_columns') if isinstance(sqlite_overview.get('scope_columns'), dict) else {}
    relationship_scope_status = scope_columns.get('rp2_relationship_state') if isinstance(scope_columns.get('rp2_relationship_state'), dict) else {}
    gaps: list[str] = []
    if inventory['entities'] > int(sqlite_overview.get('entity_count') or 0):
        gaps.append('sqlite_entities_need_backfill')
    if inventory['memory_fragments'] > int(sqlite_overview.get('memory_fragment_count') or 0):
        gaps.append('sqlite_memory_need_backfill')
    if inventory['story_sessions'] > int(sqlite_overview.get('story_session_count') or 0):
        gaps.append('sqlite_story_sessions_need_backfill')
    if inventory['story_checkpoints'] > int(sqlite_overview.get('scene_checkpoint_count') or 0):
        gaps.append('sqlite_scene_checkpoints_need_backfill')
    if relationship_scope_status and not bool(relationship_scope_status.get('ready')):
        gaps.append('sqlite_relationship_scope_columns_missing')
    if not bool(chroma_status.get('scope_metadata_ready')):
        gaps.append('chroma_scope_metadata_unavailable')
    cleanup = _cleanup_profile(sqlite_overview, chroma_status)
    return {
        'ok': True,
        'inventory': inventory,
        'sqlite_overview': sqlite_overview,
        'chroma_status': chroma_status,
        'cleanup_profile': cleanup,
        'scope_migration': {
            'schema_version': sqlite_overview.get('schema_version'),
            'relationship_state_scope_ready': bool(relationship_scope_status.get('ready')),
            'relationship_state_missing_columns': relationship_scope_status.get('missing_columns') or [],
            'sqlite_scope_presence': sqlite_overview.get('scope_presence') if isinstance(sqlite_overview.get('scope_presence'), dict) else {},
            'sqlite_scope_inventory': sqlite_overview.get('scope_inventory') if isinstance(sqlite_overview.get('scope_inventory'), dict) else {},
            'chroma_scope_fields': chroma_status.get('scope_metadata_fields') or [],
            'chroma_scope_ready': bool(chroma_status.get('scope_metadata_ready')),
        },
        'gaps': gaps,
        'migration_report_path': str(MIGRATION_REPORT_PATH),
    }


def run_phase14_migration(*, sync_builders: bool = True, backfill_memory: bool = True, backfill_stories: bool = True, sync_chroma: bool = True, prune_missing: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {'ok': True, 'steps': []}
    if sync_builders:
        builder_sync = sync_rp2_entities_from_directory(entities_dir=ROLEPLAY_V2_ENTITIES_DIR, prune_missing=bool(prune_missing))
        report['builder_sync'] = builder_sync
        report['steps'].append({'step': 'builder_sync', 'synced': builder_sync.get('synced', 0), 'pruned': builder_sync.get('pruned', 0), 'entity_count': ((builder_sync.get('overview') or {}).get('entity_count') if isinstance(builder_sync.get('overview'), dict) else 0), 'edge_count': ((builder_sync.get('overview') or {}).get('edge_count') if isinstance(builder_sync.get('overview'), dict) else 0)})
    if backfill_memory:
        memory_rows = _load_json_rows(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR)
        shared_rows = _load_json_rows(ROLEPLAY_V2_SHARED_MEMORIES_DIR)
        memory_sync = upsert_rp2_memory_outputs(memory_fragments=memory_rows, shared_memories=shared_rows, prune_existing=False)
        report['memory_sync'] = memory_sync
        report['steps'].append({
            'step': 'memory_backfill',
            'fragment_count': memory_sync.get('fragment_count', 0),
            'shared_memory_count': memory_sync.get('shared_memory_count', 0),
            'callback_anchor_count': memory_sync.get('callback_anchor_count', 0),
        })
    if backfill_stories:
        sessions = _load_json_rows(ROLEPLAY_V2_STORY_SESSIONS_DIR)
        checkpoints = _load_json_rows(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR)
        session_results = [upsert_rp2_story_session_record(session=row) for row in sessions]
        checkpoint_results = [upsert_rp2_scene_checkpoint_record(checkpoint=row) for row in checkpoints]
        report['story_sync'] = {
            'session_count': len(session_results),
            'checkpoint_count': len(checkpoint_results),
        }
        report['steps'].append({'step': 'story_backfill', 'session_count': len(session_results), 'checkpoint_count': len(checkpoint_results)})
    if sync_chroma:
        chroma_sync = sync_rp2_memory_to_chroma(limit=2000)
        report['chroma_sync'] = chroma_sync
        report['steps'].append({'step': 'chroma_sync', 'indexed': chroma_sync.get('indexed', 0), 'collection': chroma_sync.get('collection', '')})
    report['status'] = build_phase14_migration_status()
    report['cleanup_profile'] = report['status'].get('cleanup_profile') if isinstance(report.get('status'), dict) else {}
    MIGRATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(MIGRATION_REPORT_PATH, report)
    report['migration_report_path'] = str(MIGRATION_REPORT_PATH)
    return report
