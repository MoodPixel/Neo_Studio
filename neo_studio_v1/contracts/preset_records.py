from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_preset_record(kind: str, name: str, payload: dict[str, Any] | None = None, *, scope: str = "surface", surface: str = "", family: str = "", source: str = "custom") -> dict[str, Any]:
    payload = dict(payload or {})
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'preset',
        'preset_kind': str(kind or '').strip().lower() or 'generic',
        'preset_id': str(payload.get('preset_id') or f"{kind}:{name}").strip(),
        'name': str(name or payload.get('name') or '').strip(),
        'scope': str(scope or payload.get('scope') or 'surface').strip().lower(),
        'surface': str(surface or payload.get('surface') or '').strip().lower(),
        'family': str(family or payload.get('family') or '').strip().lower(),
        'source': str(source or payload.get('source') or 'custom').strip().lower(),
        'editable': bool(payload.get('editable', True)),
        'favorite': bool(payload.get('favorite', False)),
        'group': str(payload.get('group') or '').strip(),
        'notes': str(payload.get('notes') or '').strip(),
        'tags': [str(item).strip() for item in (payload.get('tags') or []) if str(item).strip()],
        'usage_count': int(payload.get('usage_count') or 0),
        'last_used': str(payload.get('last_used') or '').strip(),
        'updated_at': str(payload.get('updated_at') or _now_iso()).strip(),
        'payload': payload,
    }


def build_preset_bundle(prompt_presets: dict[str, dict[str, Any]] | None = None, caption_presets: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    prompt_presets = prompt_presets or {}
    caption_presets = caption_presets or {}
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'preset_bundle',
        'exported_at': _now_iso(),
        'prompt_presets': {name: normalize_preset_record('prompt', name, payload, surface='prompt_caption') for name, payload in prompt_presets.items()},
        'caption_presets': {name: normalize_preset_record('caption', name, payload, surface='prompt_caption') for name, payload in caption_presets.items()},
    }
