from __future__ import annotations

from typing import Any

from .shared_data_paths import studio_data_path
from .storage_io import atomic_write_json

WORKSPACE_PRESETS_PATH = studio_data_path(
    'image/workspace_presets.json',
    default_json={'kind': 'neo_generation_workspace_presets_v1', 'presets': [], 'default_id': ''},
)


def _clean_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _clone_json_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_workspace_preset(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    draft = _clone_json_dict(item.get('draft'))
    if not draft:
        return None
    preset_id = _clean_text(item.get('id'))
    if not preset_id:
        return None
    return {
        'id': preset_id,
        'name': _clean_text(item.get('name'), 'Untitled preset'),
        'updated_at': int(float(item.get('updated_at') or 0)) if str(item.get('updated_at') or '').strip() else 0,
        'draft': draft,
    }


def load_workspace_presets() -> dict[str, Any]:
    try:
        import json
        raw = json.loads(WORKSPACE_PRESETS_PATH.read_text(encoding='utf-8'))
    except Exception:
        raw = {}
    rows = raw.get('presets', []) if isinstance(raw, dict) else []
    presets = [item for item in (normalize_workspace_preset(row) for row in rows) if item]
    default_id = _clean_text(raw.get('default_id') if isinstance(raw, dict) else '')
    preset_ids = {str(item.get('id') or '') for item in presets}
    if default_id and default_id not in preset_ids and not default_id.startswith('builtin:'):
        default_id = ''
    return {
        'kind': 'neo_generation_workspace_presets_v1',
        'presets': presets,
        'default_id': default_id,
        'path': str(WORKSPACE_PRESETS_PATH),
    }


def save_workspace_presets(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    presets = [item for item in (normalize_workspace_preset(row) for row in payload.get('presets', [])) if item]
    default_id = _clean_text(payload.get('default_id'))
    preset_ids = {str(item.get('id') or '') for item in presets}
    if default_id and default_id not in preset_ids and not default_id.startswith('builtin:'):
        default_id = ''
    data = {
        'kind': 'neo_generation_workspace_presets_v1',
        'presets': presets,
        'default_id': default_id,
    }
    WORKSPACE_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(WORKSPACE_PRESETS_PATH, data)
    return {**data, 'path': str(WORKSPACE_PRESETS_PATH)}
