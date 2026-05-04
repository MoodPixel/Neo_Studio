from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .generation_families import normalize_generation_mode, normalize_inpaint_backend

INPAINT_PAYLOAD_SCHEMA_VERSION = 1


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or '').strip()


LANPAINT_PROMPT_MODE_VALUES = {
    'image_first': 'Image First',
    'prompt_first': 'Prompt First',
    'Image First': 'Image First',
    'Prompt First': 'Prompt First',
}

DEFAULT_LANPAINT_SETTINGS = {
    'enabled': False,
    'num_steps': 5,
    'prompt_mode': 'Image First',
    'lambda': 6.0,
    'step_size': 0.25,
    'beta': 1.0,
    'friction': 12.0,
    'early_stop': 2,
    'info': '',
}


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    token = _text(value).lower()
    if token in {'1', 'true', 'yes', 'on', 'enabled', 'enable'}:
        return True
    if token in {'0', 'false', 'no', 'off', 'disabled', 'disable'}:
        return False
    return default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, _int(value, default)))


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _float(value, default)))


def normalize_lanpaint_prompt_mode(value: Any) -> str:
    raw = _text(value)
    if raw in LANPAINT_PROMPT_MODE_VALUES:
        return LANPAINT_PROMPT_MODE_VALUES[raw]
    token = raw.lower().replace('-', '_').replace(' ', '_')
    if token in LANPAINT_PROMPT_MODE_VALUES:
        return LANPAINT_PROMPT_MODE_VALUES[token]
    return DEFAULT_LANPAINT_SETTINGS['prompt_mode']


def normalize_lanpaint_settings(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Normalize LanPaint controls without assuming the UI has been wired yet.

    Phase 1 contract only defines safe payload/default behavior. Later phases can expose
    these controls in the UI and pass supported keys into the live LanPaint node schema.
    """
    row = payload if isinstance(payload, dict) else {}
    nested = row.get('lanpaint') if isinstance(row.get('lanpaint'), dict) else {}

    def pick(*keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in row and row.get(key) is not None:
                return row.get(key)
            if key in nested and nested.get(key) is not None:
                return nested.get(key)
        return default

    backend = normalize_inpaint_backend(row.get('inpaint_backend') or nested.get('backend') or 'standard')
    mode = normalize_generation_mode(row.get('mode') or row.get('workflow_type') or 'txt2img')
    enabled_default = mode == 'inpaint' and backend == 'lanpaint'

    return {
        'enabled': _bool(pick('lanpaint_enabled', 'enabled', default=enabled_default), enabled_default),
        'num_steps': _clamp_int(pick('lanpaint_num_steps', 'LanPaint_NumSteps', 'num_steps', default=DEFAULT_LANPAINT_SETTINGS['num_steps']), DEFAULT_LANPAINT_SETTINGS['num_steps'], 1, 20),
        'prompt_mode': normalize_lanpaint_prompt_mode(pick('lanpaint_prompt_mode', 'LanPaint_PromptMode', 'prompt_mode', default=DEFAULT_LANPAINT_SETTINGS['prompt_mode'])),
        'lambda': _clamp_float(pick('lanpaint_lambda', 'LanPaint_Lambda', 'lambda', default=DEFAULT_LANPAINT_SETTINGS['lambda']), DEFAULT_LANPAINT_SETTINGS['lambda'], 0.0, 50.0),
        'step_size': _clamp_float(pick('lanpaint_step_size', 'LanPaint_StepSize', 'step_size', default=DEFAULT_LANPAINT_SETTINGS['step_size']), DEFAULT_LANPAINT_SETTINGS['step_size'], 0.0, 10.0),
        'beta': _clamp_float(pick('lanpaint_beta', 'LanPaint_Beta', 'beta', default=DEFAULT_LANPAINT_SETTINGS['beta']), DEFAULT_LANPAINT_SETTINGS['beta'], 0.0, 50.0),
        'friction': _clamp_float(pick('lanpaint_friction', 'LanPaint_Friction', 'friction', default=DEFAULT_LANPAINT_SETTINGS['friction']), DEFAULT_LANPAINT_SETTINGS['friction'], 0.0, 100.0),
        'early_stop': _clamp_int(pick('lanpaint_early_stop', 'LanPaint_EarlyStop', 'early_stop', default=DEFAULT_LANPAINT_SETTINGS['early_stop']), DEFAULT_LANPAINT_SETTINGS['early_stop'], 0, 20),
        'info': _text(pick('lanpaint_info', 'LanPaint_Info', 'info', default=DEFAULT_LANPAINT_SETTINGS['info'])),
    }


def normalize_composition_guide_type(value: Any) -> str:
    token = _text(value).lower()
    if token in {'depth', 'pose'}:
        return token
    return 'none'


def normalize_composition_source_mode(value: Any) -> str:
    token = _text(value).lower()
    if token in {'composition', 'composition_image', 'image3', 'source_image__3'}:
        return 'composition_image'
    return 'source_image'


def build_shared_inpaint_payload(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    mode = normalize_generation_mode(row.get('mode') or row.get('workflow_type') or 'txt2img')
    source_image_name = _text(row.get('source_image_name'))
    reference_image_2_name = _text(row.get('source_image__2_name') or row.get('reference_image_2_name'))
    composition_image_name = _text(row.get('source_image__3_name') or row.get('composition_image_name') or row.get('reference_image_3_name'))
    composition_source_mode = normalize_composition_source_mode(row.get('composition_source_mode'))
    composition_guide_type = normalize_composition_guide_type(row.get('composition_guide_type'))
    width = _int(row.get('width'), 1024)
    height = _int(row.get('height'), 1024)
    megapixels = _float(row.get('megapixels') if row.get('megapixels') is not None else row.get('resolution_megapixels'), 0.0)
    grow_mask_by = _int(row.get('grow_mask_by'), 6)
    blur_mask_by = _int(row.get('blur_mask_by') if row.get('blur_mask_by') is not None else row.get('mask_blur'), 0)

    return {
        'schema_version': INPAINT_PAYLOAD_SCHEMA_VERSION,
        'family': _text(row.get('family') or 'sdxl_sd') or 'sdxl_sd',
        'mode': mode,
        'backend': normalize_inpaint_backend(row.get('inpaint_backend') or 'standard'),
        'source_images': {
            'base_image_name': source_image_name,
            'reference_image_2_name': reference_image_2_name,
            'composition_image_name': composition_image_name,
        },
        'mask': {
            'mask_image_name': _text(row.get('mask_image_name')),
            'grow_mask_by': grow_mask_by,
            'blur_mask_by': blur_mask_by,
        },
        'outpaint': {
            'left': _int(row.get('outpaint_left'), 0),
            'top': _int(row.get('outpaint_top'), 0),
            'right': _int(row.get('outpaint_right'), 0),
            'bottom': _int(row.get('outpaint_bottom'), 0),
            'feather': _int(row.get('outpaint_feather'), 24),
        },
        'output': {
            'width': width,
            'height': height,
            'megapixels': megapixels,
        },
        'lanpaint': normalize_lanpaint_settings(row),
        'composition': {
            'guide_type': composition_guide_type,
            'source_mode': composition_source_mode,
            'guide_image_name': composition_image_name if composition_source_mode == 'composition_image' else source_image_name,
        },
    }


def merge_shared_inpaint_payload(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row = deepcopy(payload if isinstance(payload, dict) else {})
    nested = build_shared_inpaint_payload(row)
    row['inpaint_payload'] = nested

    source_images = nested.get('source_images') or {}
    mask = nested.get('mask') or {}
    outpaint = nested.get('outpaint') or {}
    output = nested.get('output') or {}
    composition = nested.get('composition') or {}

    row['inpaint_backend'] = nested.get('backend') or 'standard'
    row['source_image_name'] = source_images.get('base_image_name') or row.get('source_image_name') or ''
    row['source_image__2_name'] = source_images.get('reference_image_2_name') or row.get('source_image__2_name') or ''
    row['source_image__3_name'] = source_images.get('composition_image_name') or row.get('source_image__3_name') or ''
    row['mask_image_name'] = mask.get('mask_image_name') or row.get('mask_image_name') or ''
    row['grow_mask_by'] = mask.get('grow_mask_by')
    row['blur_mask_by'] = mask.get('blur_mask_by')
    row['outpaint_left'] = outpaint.get('left')
    row['outpaint_top'] = outpaint.get('top')
    row['outpaint_right'] = outpaint.get('right')
    row['outpaint_bottom'] = outpaint.get('bottom')
    row['outpaint_feather'] = outpaint.get('feather')
    row['width'] = output.get('width')
    row['height'] = output.get('height')
    if output.get('megapixels') is not None:
        row['megapixels'] = output.get('megapixels')
    row['composition_guide_type'] = composition.get('guide_type') or 'none'
    row['composition_source_mode'] = composition.get('source_mode') or 'source_image'

    lanpaint = nested.get('lanpaint') or normalize_lanpaint_settings(row)
    row['lanpaint'] = lanpaint
    row['lanpaint_enabled'] = lanpaint.get('enabled')
    row['lanpaint_num_steps'] = lanpaint.get('num_steps')
    row['lanpaint_prompt_mode'] = lanpaint.get('prompt_mode')
    row['lanpaint_lambda'] = lanpaint.get('lambda')
    row['lanpaint_step_size'] = lanpaint.get('step_size')
    row['lanpaint_beta'] = lanpaint.get('beta')
    row['lanpaint_friction'] = lanpaint.get('friction')
    row['lanpaint_early_stop'] = lanpaint.get('early_stop')
    row['lanpaint_info'] = lanpaint.get('info') or ''
    return row


def get_shared_inpaint_payload(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    nested = row.get('inpaint_payload')
    if isinstance(nested, dict) and nested.get('schema_version') == INPAINT_PAYLOAD_SCHEMA_VERSION:
        return build_shared_inpaint_payload(merge_shared_inpaint_payload(row))
    return build_shared_inpaint_payload(row)
