from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..contracts import normalize_video_advanced_adapters, normalize_video_backend_assets, normalize_video_mode, normalize_video_post_processes, normalize_video_preset_record, normalize_video_profile, normalize_video_post_pipeline_template, get_video_post_pipeline_label
from .library_common import atomic_write_json, new_id, read_json_dict, record_sort_key
from .library_constants import USER_DATA_DIR

VIDEO_PRESET_STORE_PATH = USER_DATA_DIR / 'video_presets.json'
VIDEO_PRESET_STORE_SCHEMA_VERSION = 1
VIDEO_PRESET_CATEGORIES = {
    'short_social_clip': 'Short social clip',
    'slow_cinematic': 'Slow cinematic',
    'subtle_image_animation': 'Subtle image animation',
    'aggressive_motion_test': 'Aggressive motion test',
    'low_vram_safe': 'Low-VRAM safe',
    'custom': 'Custom',
}


def _now_sortable() -> str:
    from datetime import datetime
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'



def list_video_preset_categories() -> list[dict[str, str]]:
    return [{'id': key, 'label': value} for key, value in VIDEO_PRESET_CATEGORIES.items()]



def normalize_video_preset_category(value: Any) -> str:
    clean = str(value or '').strip().lower().replace(' ', '_').replace('-', '_')
    return clean if clean in VIDEO_PRESET_CATEGORIES else 'custom'



def _default_state() -> dict[str, Any]:
    return {
        'schema_version': VIDEO_PRESET_STORE_SCHEMA_VERSION,
        'default_preset_id': '',
        'presets': [],
    }



def load_video_preset_state() -> dict[str, Any]:
    data = read_json_dict(VIDEO_PRESET_STORE_PATH)
    rows = data.get('presets') if isinstance(data.get('presets'), list) else []
    default_preset_id = str(data.get('default_preset_id') or '').strip()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            normalized_rows.append(normalize_video_saved_preset_record(row))
        except Exception:
            continue
    normalized_rows.sort(key=record_sort_key, reverse=True)
    if default_preset_id and not any(str(item.get('preset_id') or '') == default_preset_id for item in normalized_rows):
        default_preset_id = ''
    return {
        'schema_version': VIDEO_PRESET_STORE_SCHEMA_VERSION,
        'default_preset_id': default_preset_id,
        'presets': normalized_rows,
    }



def save_video_preset_state(data: dict[str, Any]) -> dict[str, Any]:
    rows = [normalize_video_saved_preset_record(row) for row in list(data.get('presets') or []) if isinstance(row, dict)]
    rows.sort(key=record_sort_key, reverse=True)
    default_preset_id = str(data.get('default_preset_id') or '').strip()
    if default_preset_id and not any(str(item.get('preset_id') or '') == default_preset_id for item in rows):
        default_preset_id = ''
    payload = {
        'schema_version': VIDEO_PRESET_STORE_SCHEMA_VERSION,
        'default_preset_id': default_preset_id,
        'presets': rows,
    }
    VIDEO_PRESET_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(VIDEO_PRESET_STORE_PATH, payload)
    return payload



def normalize_video_saved_preset_record(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(data) if isinstance(data, dict) else {}
    existing_request = payload.get('request') if isinstance(payload.get('request'), dict) else {}
    existing_runtime = payload.get('runtime_hint') if isinstance(payload.get('runtime_hint'), dict) else {}
    creative_direction = payload.get('creative_direction') if isinstance(payload.get('creative_direction'), dict) else {}
    preset = normalize_video_preset_record({
        'preset_id': payload.get('preset_id') or payload.get('id') or new_id('video_preset'),
        'name': payload.get('name') or 'Untitled video preset',
        'mode': payload.get('mode') or '',
        'profile': payload.get('profile') or '',
        'negative_prompt': existing_request.get('negative_prompt') or payload.get('negative_prompt') or '',
        'duration_seconds': existing_request.get('duration_seconds') or payload.get('duration_seconds') or payload.get('duration') or 5,
        'fps': existing_request.get('fps') or payload.get('fps') or 16,
        'size_preset': existing_request.get('size_preset') or payload.get('size_preset') or payload.get('size') or '832x480',
        'seed': existing_request.get('seed') or payload.get('seed') or '',
        'post_process': payload.get('post_process') or [],
        'runtime_hint': {
            'heaviness': existing_runtime.get('heaviness') or payload.get('heaviness') or '',
            'notes': existing_runtime.get('notes') or payload.get('notes') or '',
        },
        'source': payload.get('source') or 'custom',
        'updated_at': payload.get('updated_at') or _now_sortable(),
    })
    created_at = str(payload.get('created_at') or preset.get('updated_at') or _now_sortable()).strip() or _now_sortable()
    category = normalize_video_preset_category(payload.get('category') or '')
    preset['created_at'] = created_at
    preset['updated_at'] = str(payload.get('updated_at') or preset.get('updated_at') or created_at).strip() or created_at
    preset['category'] = category
    preset['category_label'] = VIDEO_PRESET_CATEGORIES.get(category, VIDEO_PRESET_CATEGORIES['custom'])
    preset['creative_direction'] = {
        'style_prompt': str(creative_direction.get('style_prompt') or payload.get('quality_style_prompt') or '').strip(),
        'camera_prompt': str(creative_direction.get('camera_prompt') or payload.get('quality_camera_prompt') or '').strip(),
    }
    preset['backend_assets'] = normalize_video_backend_assets(payload, profile=preset.get('profile') or '', mode=preset.get('mode') or '')
    preset['advanced_adapters'] = normalize_video_advanced_adapters(payload, profile=preset.get('profile') or '')
    preset['post_pipeline_template'] = normalize_video_post_pipeline_template(payload.get('post_pipeline_template') or preset.get('post_pipeline_template') or '')
    preset['post_pipeline_label'] = get_video_post_pipeline_label(preset.get('post_pipeline_template') or '')
    preset['post_process'] = normalize_video_post_processes(payload.get('post_process') or preset.get('post_process') or [])
    return preset



def build_video_preset_summary(preset: dict[str, Any] | None) -> dict[str, Any]:
    row = normalize_video_saved_preset_record(preset if isinstance(preset, dict) else {})
    request = row.get('request') if isinstance(row.get('request'), dict) else {}
    creative_direction = row.get('creative_direction') if isinstance(row.get('creative_direction'), dict) else {}
    profile = normalize_video_profile(row.get('profile') or '', mode=row.get('mode') or '')
    mode = normalize_video_mode(row.get('mode') or '')
    quality_label = 'High Quality' if profile != 'wan22_5b_balanced' else 'Balanced / Low VRAM'
    advanced_adapters = row.get('advanced_adapters') if isinstance(row.get('advanced_adapters'), dict) else {}
    backend_assets = row.get('backend_assets') if isinstance(row.get('backend_assets'), dict) else {}
    return {
        'preset_id': str(row.get('preset_id') or ''),
        'name': str(row.get('name') or 'Untitled video preset'),
        'category': str(row.get('category') or 'custom'),
        'category_label': str(row.get('category_label') or VIDEO_PRESET_CATEGORIES['custom']),
        'mode': mode,
        'profile': profile,
        'quality_label': quality_label,
        'output_label': f"{request.get('duration_seconds')}s · {request.get('fps')} FPS · {request.get('size_preset')}",
        'negative_prompt_included': bool(str(request.get('negative_prompt') or '').strip()),
        'seed': str(request.get('seed') or '').strip(),
        'creative_direction_included': bool(str(creative_direction.get('style_prompt') or '').strip() or str(creative_direction.get('camera_prompt') or '').strip()),
        'backend_assets_included': bool(any(str(backend_assets.get(key) or '').strip() for key in ('balanced_unet_name', 'balanced_clip_name', 'balanced_vae_name', 'quality_high_noise_unet_name', 'quality_low_noise_unet_name', 'quality_clip_name', 'quality_vae_name'))),
        'adapter_pair_included': bool(advanced_adapters.get('enabled') and advanced_adapters.get('high_noise_adapter') and advanced_adapters.get('low_noise_adapter')),
        'adapter_included': bool(advanced_adapters.get('enabled') and (advanced_adapters.get('single_adapter') or (advanced_adapters.get('high_noise_adapter') and advanced_adapters.get('low_noise_adapter')))),
        'post_process_count': len(row.get('post_process') or []),
        'post_pipeline_template': str(row.get('post_pipeline_template') or 'generate_only'),
        'post_pipeline_label': str(row.get('post_pipeline_label') or get_video_post_pipeline_label(row.get('post_pipeline_template') or '')),
        'post_pipeline_enabled': bool(row.get('post_process') or []),
        'notes': str((row.get('runtime_hint') or {}).get('notes') or '').strip(),
        'updated_at': str(row.get('updated_at') or ''),
    }



def list_video_presets() -> list[dict[str, Any]]:
    return list(load_video_preset_state().get('presets') or [])



def get_video_preset(preset_id: str) -> dict[str, Any] | None:
    target = str(preset_id or '').strip()
    if not target:
        return None
    for row in load_video_preset_state().get('presets') or []:
        if str(row.get('preset_id') or '') == target:
            return row
    return None



def get_default_video_preset_id() -> str:
    return str(load_video_preset_state().get('default_preset_id') or '').strip()



def save_video_preset(*, name: str, payload: dict[str, Any], preset_id: str = '', category: str = 'custom', notes: str = '') -> dict[str, Any]:
    clean_name = str(name or '').strip()
    if not clean_name:
        raise ValueError('Video preset name is required.')
    state = load_video_preset_state()
    rows = list(state.get('presets') or [])
    existing = None
    target_id = str(preset_id or '').strip()
    if target_id:
        for idx, row in enumerate(rows):
            if str(row.get('preset_id') or '') == target_id:
                existing = row
                break
        if existing is None:
            raise ValueError('Saved video preset was not found.')
    merged_payload = {
        **(existing or {}),
        **(payload or {}),
        'preset_id': target_id or (existing or {}).get('preset_id') or new_id('video_preset'),
        'name': clean_name,
        'category': category,
        'notes': notes,
        'created_at': (existing or {}).get('created_at') or _now_sortable(),
        'updated_at': _now_sortable(),
        'source': 'saved_record',
    }
    saved = normalize_video_saved_preset_record(merged_payload)
    replaced = False
    for idx, row in enumerate(rows):
        if str(row.get('preset_id') or '') == str(saved.get('preset_id') or ''):
            rows[idx] = saved
            replaced = True
            break
    if not replaced:
        rows.insert(0, saved)
    state['presets'] = rows[:100]
    save_video_preset_state(state)
    return saved



def delete_video_preset(preset_id: str) -> None:
    target = str(preset_id or '').strip()
    if not target:
        raise ValueError('Video preset id is required.')
    state = load_video_preset_state()
    rows = [row for row in list(state.get('presets') or []) if str(row.get('preset_id') or '') != target]
    if len(rows) == len(list(state.get('presets') or [])):
        raise ValueError('Saved video preset was not found.')
    state['presets'] = rows
    if str(state.get('default_preset_id') or '').strip() == target:
        state['default_preset_id'] = ''
    save_video_preset_state(state)



def set_default_video_preset(preset_id: str) -> str:
    target = str(preset_id or '').strip()
    if not target:
        raise ValueError('Video preset id is required.')
    if not get_video_preset(target):
        raise ValueError('Saved video preset was not found.')
    state = load_video_preset_state()
    state['default_preset_id'] = target
    save_video_preset_state(state)
    return target



def clear_default_video_preset() -> None:
    state = load_video_preset_state()
    state['default_preset_id'] = ''
    save_video_preset_state(state)
