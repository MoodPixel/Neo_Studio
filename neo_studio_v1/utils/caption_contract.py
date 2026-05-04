from __future__ import annotations

import json
from typing import Any, Mapping

CAPTION_COMPONENT_TYPES = {'', 'face', 'person', 'outfit', 'pose', 'location', 'custom'}
CAPTION_MODES = {'full_image', 'face_only', 'person_only', 'outfit_only', 'pose_only', 'location_only', 'custom_crop'}
BATCH_CAPTION_MODES = CAPTION_MODES - {'custom_crop'}
CAPTION_DETAIL_LEVELS = {'basic', 'detailed', 'attribute_rich'}

DEFAULT_MAX_NEW_TOKENS = 160
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 40


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        num = int(value)
    except Exception:
        return default
    return max(low, min(high, num))


def _clamp_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        num = float(value)
    except Exception:
        return default
    return max(low, min(high, num))


def normalize_component_type(value: str) -> str:
    value = (value or '').strip().lower().replace(' ', '_')
    return value if value in CAPTION_COMPONENT_TYPES else ''


def normalize_caption_mode(value: str, *, allow_custom_crop: bool = True) -> str:
    value = (value or 'full_image').strip().lower().replace(' ', '_')
    allowed = CAPTION_MODES if allow_custom_crop else BATCH_CAPTION_MODES
    return value if value in allowed else 'full_image'


def normalize_batch_caption_mode(value: str) -> str:
    return normalize_caption_mode(value, allow_custom_crop=False)


def normalize_detail_level(value: str) -> str:
    value = (value or 'detailed').strip().lower().replace('-', '_').replace(' ', '_')
    return value if value in CAPTION_DETAIL_LEVELS else 'detailed'


def default_component_for_mode(mode: str) -> str:
    return {
        'face_only': 'face',
        'person_only': 'person',
        'outfit_only': 'outfit',
        'pose_only': 'pose',
        'location_only': 'location',
        'custom_crop': 'custom',
    }.get(normalize_caption_mode(mode), '')


def normalize_crop_meta(crop_meta: Any) -> dict[str, float] | None:
    if not isinstance(crop_meta, dict):
        return None
    try:
        x = max(0.0, min(1.0, float(crop_meta.get('x', 0.0))))
        y = max(0.0, min(1.0, float(crop_meta.get('y', 0.0))))
        w = max(0.0, min(1.0 - x, float(crop_meta.get('w', 0.0))))
        h = max(0.0, min(1.0 - y, float(crop_meta.get('h', 0.0))))
    except Exception:
        return None
    if w <= 0.01 or h <= 0.01:
        return None
    return {'x': round(x, 6), 'y': round(y, 6), 'w': round(w, 6), 'h': round(h, 6)}


def parse_crop_json(raw: str) -> dict[str, float] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return normalize_crop_meta(payload)


def default_crop_meta(mode: str) -> dict[str, float] | None:
    mode = normalize_caption_mode(mode)
    if mode == 'face_only':
        return {'x': 0.18, 'y': 0.02, 'w': 0.64, 'h': 0.42}
    if mode == 'person_only':
        return {'x': 0.10, 'y': 0.03, 'w': 0.80, 'h': 0.92}
    if mode == 'outfit_only':
        return {'x': 0.18, 'y': 0.18, 'w': 0.64, 'h': 0.62}
    if mode == 'pose_only':
        return {'x': 0.08, 'y': 0.03, 'w': 0.84, 'h': 0.92}
    return None


def normalize_sampling(*, max_new_tokens: Any, temperature: Any, top_p: Any, top_k: Any) -> dict[str, Any]:
    return {
        'max_new_tokens': _clamp_int(max_new_tokens, 24, 1000, DEFAULT_MAX_NEW_TOKENS),
        'temperature': _clamp_float(temperature, 0.0, 1.5, DEFAULT_TEMPERATURE),
        'top_p': _clamp_float(top_p, 0.0, 1.0, DEFAULT_TOP_P),
        'top_k': _clamp_int(top_k, 0, 200, DEFAULT_TOP_K),
    }


def build_caption_settings(*, max_new_tokens: Any, temperature: Any, top_p: Any, top_k: Any, caption_mode: str = 'full_image', component_type: str = '', detail_level: str = 'detailed', crop_meta: Any = None, allow_custom_crop: bool = True, use_mode_default_component: bool = False) -> dict[str, Any]:
    sampling = normalize_sampling(max_new_tokens=max_new_tokens, temperature=temperature, top_p=top_p, top_k=top_k)
    mode = normalize_caption_mode(caption_mode, allow_custom_crop=allow_custom_crop)
    component = normalize_component_type(component_type)
    if use_mode_default_component and not component:
        component = default_component_for_mode(mode)
    payload = {
        **sampling,
        'caption_mode': mode,
        'component_type': component,
        'detail_level': normalize_detail_level(detail_level),
    }
    crop = normalize_crop_meta(crop_meta)
    if crop:
        payload['crop_meta'] = crop
    return payload


def normalize_caption_preset_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(payload or {})
    clean = build_caption_settings(
        max_new_tokens=raw.get('max_new_tokens', DEFAULT_MAX_NEW_TOKENS),
        temperature=raw.get('temperature', DEFAULT_TEMPERATURE),
        top_p=raw.get('top_p', DEFAULT_TOP_P),
        top_k=raw.get('top_k', DEFAULT_TOP_K),
        caption_mode=raw.get('caption_mode', 'full_image'),
        component_type=raw.get('component_type', ''),
        detail_level=raw.get('detail_level', 'detailed'),
        crop_meta=raw.get('crop_meta'),
        use_mode_default_component=True,
    )
    for key in ('prompt_style', 'caption_length', 'custom_prompt', 'prefix', 'suffix', 'output_style', 'group', 'notes', 'kind', 'last_used'):
        if key in raw:
            clean[key] = str(raw.get(key) or '').strip() if key not in {'kind', 'last_used'} else str(raw.get(key) or '').strip()
    for key in ('favorite',):
        if key in raw:
            clean[key] = bool(raw.get(key))
    for key in ('usage_count',):
        if key in raw:
            clean[key] = _clamp_int(raw.get(key), 0, 1_000_000, 0)
    return clean
