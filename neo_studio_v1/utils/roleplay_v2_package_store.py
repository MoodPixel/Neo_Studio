from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .roleplay_v2_foundation import (
    ROLEPLAY_V2_CANON_RECORDS_DIR,
    ROLEPLAY_V2_CREATOR_DRAFTS_DIR,
    ROLEPLAY_V2_ENTITIES_DIR,
    ROLEPLAY_V2_EXPORTS_DIR,
    ROLEPLAY_V2_HELPER_OUTPUTS_DIR,
    ROLEPLAY_V2_IMPORTS_DIR,
    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR,
    ROLEPLAY_V2_NOVEL_PROJECTS_DIR,
    ROLEPLAY_V2_PACKAGES_DIR,
    ROLEPLAY_V2_RELATIONSHIPS_DIR,
    ROLEPLAY_V2_RUNTIME_BUNDLES_DIR,
    ROLEPLAY_V2_SHARED_MEMORIES_DIR,
    ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR,
    ROLEPLAY_V2_TIMELINE_EVENTS_DIR,
    ROLEPLAY_V2_STORYLINES_DIR,
    ROLEPLAY_V2_STORY_SESSIONS_DIR,
    ROLEPLAY_V2_STORY_CHECKPOINTS_DIR,
    ROLEPLAY_V2_STORY_DRAFTS_DIR,
)
from .storage_io import atomic_write_json, read_json_object

RECORD_DIR_MAP = {
    'entity_record': ROLEPLAY_V2_ENTITIES_DIR,
    'source_document': ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR,
    'creator_draft': ROLEPLAY_V2_CREATOR_DRAFTS_DIR,
    'helper_output': ROLEPLAY_V2_HELPER_OUTPUTS_DIR,
    'canon_record': ROLEPLAY_V2_CANON_RECORDS_DIR,
    'memory_fragment': ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR,
    'timeline_event': ROLEPLAY_V2_TIMELINE_EVENTS_DIR,
    'relationship_record': ROLEPLAY_V2_RELATIONSHIPS_DIR,
    'shared_memory': ROLEPLAY_V2_SHARED_MEMORIES_DIR,
    'runtime_bundle': ROLEPLAY_V2_RUNTIME_BUNDLES_DIR,
    'novel_project': ROLEPLAY_V2_NOVEL_PROJECTS_DIR,
    'storyline': ROLEPLAY_V2_STORYLINES_DIR,
    'story_session': ROLEPLAY_V2_STORY_SESSIONS_DIR,
    'story_checkpoint': ROLEPLAY_V2_STORY_CHECKPOINTS_DIR,
    'story_draft_snapshot': ROLEPLAY_V2_STORY_DRAFTS_DIR,
}



def record_dir(record_type: str) -> Path:
    clean = str(record_type or '').strip().lower()
    if clean not in RECORD_DIR_MAP:
        raise ValueError(f'Unsupported Roleplay V2 record type: {clean or "unknown"}.')
    path = RECORD_DIR_MAP[clean]
    path.mkdir(parents=True, exist_ok=True)
    return path



def record_path(record_type: str, record_id: str) -> Path:
    return record_dir(record_type) / f'{str(record_id or "").strip()}.json'



def load_saved_record(record_type: str, record_id: str) -> dict[str, Any] | None:
    return read_json_object(record_path(record_type, record_id), None)



def save_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError('Record must be a JSON object.')
    record_type = str(record.get('record_type') or '').strip().lower()
    record_id = str(record.get('id') or '').strip()
    if not record_type or not record_id:
        raise ValueError('Record is missing record_type or id.')
    path = record_path(record_type, record_id)
    atomic_write_json(path, record)
    return record



def export_file_path(filename: str) -> Path:
    ROLEPLAY_V2_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return ROLEPLAY_V2_EXPORTS_DIR / str(filename or '').strip()



def import_file_path(filename: str) -> Path:
    ROLEPLAY_V2_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return ROLEPLAY_V2_IMPORTS_DIR / str(filename or '').strip()



def package_record_path(package_id: str) -> Path:
    ROLEPLAY_V2_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    return ROLEPLAY_V2_PACKAGES_DIR / f'{str(package_id or "").strip()}.json'



def save_package_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    package_id = str((manifest or {}).get('id') or '').strip()
    if not package_id:
        raise ValueError('Package manifest is missing id.')
    atomic_write_json(package_record_path(package_id), manifest)
    return manifest



def clone_record(record: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(record if isinstance(record, dict) else {})
