from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .library_common import atomic_write_json, new_id, read_json_dict, record_sort_key
from .library_constants import USER_DATA_DIR

VIDEO_ADAPTER_PRESET_STORE_PATH = USER_DATA_DIR / 'video_adapter_pair_presets.json'
VIDEO_ADAPTER_PRESET_STORE_SCHEMA_VERSION = 1


def _now_sortable() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _default_state() -> dict[str, Any]:
    return {
        'schema_version': VIDEO_ADAPTER_PRESET_STORE_SCHEMA_VERSION,
        'presets': [],
    }


def normalize_video_adapter_preset_record(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(data) if isinstance(data, dict) else {}
    record_id = str(payload.get('preset_id') or payload.get('id') or new_id('video_adapter_pair')).strip()
    name = str(payload.get('name') or 'Untitled adapter pair').strip() or 'Untitled adapter pair'
    high_noise_adapter = str(payload.get('high_noise_adapter') or payload.get('high_noise_name') or '').strip()
    low_noise_adapter = str(payload.get('low_noise_adapter') or payload.get('low_noise_name') or '').strip()
    try:
        strength = float(payload.get('strength') if payload.get('strength') is not None else 0.8)
    except Exception:
        strength = 0.8
    strength = max(0.0, min(2.0, round(strength, 4)))
    created_at = str(payload.get('created_at') or _now_sortable()).strip() or _now_sortable()
    updated_at = str(payload.get('updated_at') or created_at).strip() or created_at
    return {
        'preset_id': record_id,
        'id': record_id,
        'record_type': 'video_adapter_pair_preset',
        'name': name,
        'high_noise_adapter': high_noise_adapter,
        'low_noise_adapter': low_noise_adapter,
        'strength': strength,
        'created_at': created_at,
        'updated_at': updated_at,
    }


def load_video_adapter_preset_state() -> dict[str, Any]:
    data = read_json_dict(VIDEO_ADAPTER_PRESET_STORE_PATH)
    rows = data.get('presets') if isinstance(data.get('presets'), list) else []
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            normalized_rows.append(normalize_video_adapter_preset_record(row))
        except Exception:
            continue
    normalized_rows.sort(key=record_sort_key, reverse=True)
    return {
        'schema_version': VIDEO_ADAPTER_PRESET_STORE_SCHEMA_VERSION,
        'presets': normalized_rows,
    }


def save_video_adapter_preset_state(data: dict[str, Any]) -> dict[str, Any]:
    rows = [normalize_video_adapter_preset_record(row) for row in list(data.get('presets') or []) if isinstance(row, dict)]
    rows.sort(key=record_sort_key, reverse=True)
    payload = {
        'schema_version': VIDEO_ADAPTER_PRESET_STORE_SCHEMA_VERSION,
        'presets': rows[:100],
    }
    VIDEO_ADAPTER_PRESET_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(VIDEO_ADAPTER_PRESET_STORE_PATH, payload)
    return payload


def list_video_adapter_presets() -> list[dict[str, Any]]:
    return list(load_video_adapter_preset_state().get('presets') or [])


def get_video_adapter_preset(preset_id: str) -> dict[str, Any] | None:
    target = str(preset_id or '').strip()
    if not target:
        return None
    for row in list_video_adapter_presets():
        if str(row.get('preset_id') or '') == target:
            return row
    return None


def save_video_adapter_preset(*, name: str, high_noise_adapter: str, low_noise_adapter: str, strength: Any, preset_id: str = '') -> dict[str, Any]:
    clean_name = str(name or '').strip()
    if not clean_name:
        raise ValueError('Adapter pair preset name is required.')
    clean_high = str(high_noise_adapter or '').strip()
    clean_low = str(low_noise_adapter or '').strip()
    if not clean_high or not clean_low:
        raise ValueError('Both the high-noise and low-noise adapter slots are required for a paired adapter preset.')
    state = load_video_adapter_preset_state()
    rows = list(state.get('presets') or [])
    existing = None
    target_id = str(preset_id or '').strip()
    if target_id:
        for row in rows:
            if str(row.get('preset_id') or '') == target_id:
                existing = row
                break
        if existing is None:
            raise ValueError('Adapter pair preset was not found.')
    merged = {
        **(existing or {}),
        'preset_id': target_id or (existing or {}).get('preset_id') or new_id('video_adapter_pair'),
        'name': clean_name,
        'high_noise_adapter': clean_high,
        'low_noise_adapter': clean_low,
        'strength': strength,
        'created_at': (existing or {}).get('created_at') or _now_sortable(),
        'updated_at': _now_sortable(),
    }
    saved = normalize_video_adapter_preset_record(merged)
    replaced = False
    for index, row in enumerate(rows):
        if str(row.get('preset_id') or '') == str(saved.get('preset_id') or ''):
            rows[index] = saved
            replaced = True
            break
    if not replaced:
        rows.insert(0, saved)
    state['presets'] = rows[:100]
    save_video_adapter_preset_state(state)
    return saved


def delete_video_adapter_preset(preset_id: str) -> None:
    target = str(preset_id or '').strip()
    if not target:
        raise ValueError('Adapter pair preset id is required.')
    state = load_video_adapter_preset_state()
    rows = [row for row in list(state.get('presets') or []) if str(row.get('preset_id') or '') != target]
    if len(rows) == len(list(state.get('presets') or [])):
        raise ValueError('Adapter pair preset was not found.')
    state['presets'] = rows
    save_video_adapter_preset_state(state)
