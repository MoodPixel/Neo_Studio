from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_draft_record(surface: str, payload: dict[str, Any] | None = None, *, family: str = '', draft_id: str = '', scope: str = 'surface') -> dict[str, Any]:
    payload = dict(payload or {})
    normalized_surface = str(surface or payload.get('surface') or '').strip().lower()
    normalized_family = str(family or payload.get('family') or '').strip().lower()
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'draft',
        'draft_id': str(draft_id or payload.get('draft_id') or f'{normalized_surface}:draft').strip(),
        'surface': normalized_surface,
        'family': normalized_family,
        'scope': str(scope or payload.get('scope') or 'surface').strip().lower(),
        'updated_at': str(payload.get('updated_at') or _now_iso()).strip(),
        'payload': payload,
    }
