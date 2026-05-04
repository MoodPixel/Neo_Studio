from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts.draft_records import normalize_draft_record
from .storage_io import atomic_write_json, read_json_object


def load_draft(path: Path, *, surface: str, default: dict[str, Any] | None = None) -> dict[str, Any] | None:
    raw = read_json_object(path, None)
    if raw is None:
        return default
    if isinstance(raw, dict) and str(raw.get('record_type') or '').strip().lower() == 'draft' and isinstance(raw.get('payload'), dict):
        return normalize_draft_record(surface, raw.get('payload') or {}, family=str(raw.get('family') or ''), draft_id=str(raw.get('draft_id') or ''))
    if isinstance(raw, dict):
        return normalize_draft_record(surface, raw)
    return default


def save_draft(path: Path, *, surface: str, payload: dict[str, Any], family: str = '', draft_id: str = '') -> dict[str, Any]:
    clean = normalize_draft_record(surface, payload, family=family, draft_id=draft_id or f'{surface}:draft')
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, clean)
    return clean
