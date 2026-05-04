from __future__ import annotations

from pathlib import Path
from typing import Any

from .roleplay_v2_foundation import ROLEPLAY_V2_IMPORTS_DIR
from .storage_io import atomic_write_json, read_json_object

PREVIEW_PREFIX = 'intake_preview'


def _preview_path(preview_id: str) -> Path:
    return ROLEPLAY_V2_IMPORTS_DIR / f'{preview_id}.json'



def write_intake_preview(payload: dict[str, Any]) -> dict[str, Any]:
    preview_id = str(payload.get('preview_id') or '').strip()
    if not preview_id:
        raise ValueError('Preview payload is missing preview_id.')
    ROLEPLAY_V2_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_preview_path(preview_id), payload)
    return payload



def read_intake_preview(preview_id: str) -> dict[str, Any]:
    clean_id = str(preview_id or '').strip()
    if not clean_id:
        raise ValueError('Preview id is required.')
    data = read_json_object(_preview_path(clean_id), None)
    if not isinstance(data, dict):
        raise ValueError('Preview not found or invalid.')
    return data
