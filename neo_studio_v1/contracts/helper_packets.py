from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_helper_packet(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'helper_packet',
        'packet_id': str(raw.get('packet_id') or uuid4()).strip(),
        'source_surface': str(raw.get('source_surface') or '').strip().lower(),
        'source_family': str(raw.get('source_family') or '').strip().lower(),
        'source_section': str(raw.get('source_section') or '').strip().lower(),
        'target_mode': str(raw.get('target_mode') or 'assistant').strip().lower(),
        'title': str(raw.get('title') or '').strip(),
        'context_payload': raw.get('context_payload') if isinstance(raw.get('context_payload'), dict) else {},
        'allowed_apply_actions': [str(item).strip() for item in (raw.get('allowed_apply_actions') or []) if str(item).strip()],
        'created_at': str(raw.get('created_at') or _now_iso()).strip(),
    }
