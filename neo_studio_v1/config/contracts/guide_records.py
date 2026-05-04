from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_guide_record(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    guide_id = str(raw.get('guide_id') or '').strip()
    if not guide_id:
        surface = str(raw.get('surface') or 'global').strip().lower() or 'global'
        section = str(raw.get('section') or 'general').strip().lower() or 'general'
        field_id = str(raw.get('field_id') or '').strip().lower()
        guide_id = ':'.join([part for part in [surface, section, field_id] if part])
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'guide',
        'guide_id': guide_id,
        'title': str(raw.get('title') or '').strip(),
        'short_help': str(raw.get('short_help') or '').strip(),
        'long_help': str(raw.get('long_help') or '').strip(),
        'surface': str(raw.get('surface') or '').strip().lower(),
        'section': str(raw.get('section') or '').strip().lower(),
        'field_id': str(raw.get('field_id') or '').strip().lower(),
        'tags': [str(item).strip() for item in (raw.get('tags') or []) if str(item).strip()],
        'editable_by_user': bool(raw.get('editable_by_user', True)),
        'user_override_allowed': bool(raw.get('user_override_allowed', True)),
        'source': str(raw.get('source') or 'system').strip().lower(),
        'updated_at': str(raw.get('updated_at') or _now_iso()).strip(),
    }
