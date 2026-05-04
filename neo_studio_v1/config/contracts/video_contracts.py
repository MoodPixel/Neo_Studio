from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable
from uuid import uuid4

VIDEO_CONTRACT_SCHEMA_VERSION = 1
VIDEO_JOB_SCHEMA_VERSION = 1
VIDEO_RESULT_SCHEMA_VERSION = 1
VIDEO_PRESET_SCHEMA_VERSION = 1

VIDEO_MODE_DEFINITIONS = {
    't2v': {
        'id': 't2v',
        'label': 'Text to Video',
        'short_label': 'T2V',
        'description': 'Generate video from prompt-first input.',
        'requires_source_image': False,
        'allowed_profiles': ['wan22_5b_balanced', 'wan22_14b_t2v_quality', 'raw_free'],
        'default_profile': 'wan22_5b_balanced',
        'enabled': True,
    },
    'i2v': {
        'id': 'i2v',
        'label': 'Image to Video',
        'short_label': 'I2V',
        'description': 'Animate a starting image into motion-guided video.',
        'requires_source_image': True,
        'allowed_profiles': ['wan22_5b_balanced', 'wan22_14b_i2v_quality', 'raw_free'],
        'default_profile': 'wan22_5b_balanced',
        'enabled': True,
    },
}

VIDEO_PROFILE_DEFINITIONS = {
    'wan22_5b_balanced': {
        'id': 'wan22_5b_balanced',
        'label': 'Balanced / Low VRAM',
        'technical_label': 'Wan 2.2 5B Balanced',
        'family': 'wan22',
        'quality_tier': 'balanced',
        'backend_role': 'video',
        'supports_modes': ['t2v', 'i2v'],
        'vram_class': 'light',
        'default_for_modes': ['t2v', 'i2v'],
        'notes': 'Default lower-VRAM path for both Text to Video and Image to Video.',
        'enabled': True,
    },
    'wan22_14b_t2v_quality': {
        'id': 'wan22_14b_t2v_quality',
        'label': 'High Quality · Text to Video',
        'technical_label': 'Wan 2.2 14B T2V Quality',
        'family': 'wan22',
        'quality_tier': 'quality',
        'backend_role': 'video',
        'supports_modes': ['t2v'],
        'vram_class': 'heavy',
        'default_for_modes': [],
        'notes': 'Higher-quality Text to Video path with heavier runtime cost.',
        'enabled': True,
    },
    'wan22_14b_i2v_quality': {
        'id': 'wan22_14b_i2v_quality',
        'label': 'High Quality · Image to Video',
        'technical_label': 'Wan 2.2 14B I2V Quality',
        'family': 'wan22',
        'quality_tier': 'quality',
        'backend_role': 'video',
        'supports_modes': ['i2v'],
        'vram_class': 'heavy',
        'default_for_modes': [],
        'notes': 'Higher-quality Image to Video path with heavier runtime cost.',
        'enabled': True,
    },
    'raw_free': {
        'id': 'raw_free',
        'label': 'Raw / Free',
        'technical_label': 'Manual engine + asset routing',
        'family': 'manual',
        'quality_tier': 'flex',
        'backend_role': 'video',
        'supports_modes': ['t2v', 'i2v'],
        'vram_class': 'medium',
        'default_for_modes': [],
        'notes': 'Free routing profile. The selected backend engine and manual asset picks decide the workflow lane instead of the old balanced/quality presets.',
        'enabled': True,
    },
}

VIDEO_POST_PROCESS_DEFINITIONS = {
    'repair': {
        'id': 'repair',
        'label': 'Repair',
        'description': 'Cleanup / stabilize an existing video output.',
        'enabled': True,
    },
    'upscale': {
        'id': 'upscale',
        'label': 'Upscale',
        'description': 'Increase delivery resolution after generation.',
        'enabled': True,
    },
    'interpolate': {
        'id': 'interpolate',
        'label': 'Interpolate',
        'description': 'Insert frames to smooth lower-FPS output.',
        'enabled': True,
    },
}


VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS = {
    'generate_only': {
        'id': 'generate_only',
        'label': 'Generate only',
        'description': 'Run generation only. No post lanes are auto-chained.',
        'steps': [],
        'enabled': True,
        'default': True,
    },
    'generate_upscale': {
        'id': 'generate_upscale',
        'label': 'Generate → Upscale',
        'description': 'Generate the clip first, then hand the finished output to Upscale.',
        'steps': ['upscale'],
        'enabled': True,
        'default': False,
    },
    'generate_repair_upscale': {
        'id': 'generate_repair_upscale',
        'label': 'Generate → Repair → Upscale',
        'description': 'Generate the clip, clean it up, then send the repaired output to Upscale.',
        'steps': ['repair', 'upscale'],
        'enabled': True,
        'default': False,
    },
    'generate_repair_upscale_interpolate': {
        'id': 'generate_repair_upscale_interpolate',
        'label': 'Generate → Repair → Upscale → Interpolate',
        'description': 'Generate the clip, clean it, upscale it, then smooth the final delivery FPS.',
        'steps': ['repair', 'upscale', 'interpolate'],
        'enabled': True,
        'default': False,
    },
}

VIDEO_RUNTIME_STATUS_DEFINITIONS = {
    'draft': {
        'id': 'draft',
        'label': 'Draft',
        'terminal': False,
    },
    'validating': {
        'id': 'validating',
        'label': 'Validating',
        'terminal': False,
    },
    'queued': {
        'id': 'queued',
        'label': 'Queued',
        'terminal': False,
    },
    'running': {
        'id': 'running',
        'label': 'Running',
        'terminal': False,
    },
    'completed': {
        'id': 'completed',
        'label': 'Completed',
        'terminal': True,
    },
    'failed': {
        'id': 'failed',
        'label': 'Failed',
        'terminal': True,
    },
    'cancelled': {
        'id': 'cancelled',
        'label': 'Cancelled',
        'terminal': True,
    },
}

VIDEO_MODE_ALIASES = {
    'txt2video': 't2v',
    'img2video': 'i2v',
    'extend': 'i2v',
}

VIDEO_PROFILE_ALIASES = {
    'wan': 'wan22_5b_balanced',
    'ltxv': 'wan22_5b_balanced',
    'hunyuan': 'wan22_5b_balanced',
}

VIDEO_RUNTIME_STATUS_ALIASES = {
    'draft': 'draft',
    'validate': 'validating',
    'validating': 'validating',
    'queued': 'queued',
    'pending': 'queued',
    'running': 'running',
    'processing': 'running',
    'done': 'completed',
    'complete': 'completed',
    'completed': 'completed',
    'success': 'completed',
    'succeeded': 'completed',
    'error': 'failed',
    'failed': 'failed',
    'cancelled': 'cancelled',
    'canceled': 'cancelled',
}

VIDEO_ADVANCED_ADAPTER_SUPPORT = {
    'default_strength': 0.8,
    'available_profiles': ['wan22_5b_balanced', 'wan22_14b_t2v_quality', 'wan22_14b_i2v_quality', 'raw_free'],
    'single_slots': ['single_adapter'],
    'paired_slots': ['high_noise_adapter', 'low_noise_adapter'],
    'supports_single_adapter': True,
    'supports_pair_presets': True,
    'profile_modes': {
        'wan22_5b_balanced': {
            'mode': 'single',
            'label': 'Single LoRA / adapter',
            'supports_pair_presets': False,
        },
        'wan22_14b_t2v_quality': {
            'mode': 'paired',
            'label': 'Paired LoRAs / adapters',
            'supports_pair_presets': True,
        },
        'wan22_14b_i2v_quality': {
            'mode': 'paired',
            'label': 'Paired LoRAs / adapters',
            'supports_pair_presets': True,
        },
        'raw_free': {
            'mode': 'paired',
            'label': 'Paired LoRAs / adapters',
            'supports_pair_presets': True,
        },
    },
}

VIDEO_BACKEND_ASSET_DEFAULTS = {
    'balanced': {
        'unet_name': 'wan2.2_ti2v_5B_fp16.safetensors',
        'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'vae_name': 'wan2.2_vae.safetensors',
    },
    'quality_t2v': {
        'high_noise_unet_name': 'wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors',
        'low_noise_unet_name': 'wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors',
        'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'vae_name': 'wan_2.1_vae.safetensors',
    },
    'quality_i2v': {
        'high_noise_unet_name': 'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',
        'low_noise_unet_name': 'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors',
        'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'vae_name': 'wan_2.1_vae.safetensors',
    },
    'gguf': {
        'available': False,
        'note': 'Video can detect Wan GGUF UNET assets when the backend exposes UnetLoaderGGUF choices through object_info. Encoders and VAEs still stay on the native Wan path.',
    },
}

VIDEO_INPUT_VALIDATION_RULES = {
    'prompt': {
        'required': True,
        'min_length': 1,
        'max_length': 4000,
    },
    'negative_prompt': {
        'required': False,
        'max_length': 4000,
    },
    'source_image': {
        'required_for_modes': ['i2v'],
        'max_length': 4096,
    },
    'duration_seconds': {
        'required': True,
        'minimum': 1,
        'maximum': 30,
    },
    'fps': {
        'required': True,
        'minimum': 8,
        'maximum': 30,
    },
    'size_preset': {
        'required': True,
        'allowed': ['832x480', '1024x576', '576x1024', 'auto_source_fit', 'source_match', 'custom'],
    },
    'post_process': {
        'required': False,
        'allowed': ['repair', 'upscale', 'interpolate'],
        'allow_multiple': True,
        'unique': True,
    },
    'seed': {
        'required': False,
        'max_length': 64,
        'allow_empty': True,
    },
    'advanced_adapters': {
        'required': False,
        'quality_only': True,
        'paired_slots': ['high_noise_adapter', 'low_noise_adapter'],
        'strength_minimum': 0.0,
        'strength_maximum': 2.0,
        'pair_preset_supported': True,
    },
    'backend_assets': {
        'required': False,
        'profile_scoped': True,
        'balanced_fields': ['balanced_unet_name', 'balanced_clip_name', 'balanced_vae_name'],
        'quality_fields': ['quality_high_noise_unet_name', 'quality_low_noise_unet_name', 'quality_clip_name', 'quality_vae_name'],
    },
}

VIDEO_JOB_FIELD_ORDER = [
    'job_id',
    'surface',
    'mode',
    'profile',
    'status',
    'request',
    'advanced_adapters',
    'backend_assets',
    'post_process',
    'runtime',
    'lineage',
    'result',
]

VIDEO_RESULT_FIELD_ORDER = [
    'result_id',
    'job_id',
    'surface',
    'mode',
    'profile',
    'status',
    'outputs',
    'artifacts',
    'metrics',
    'error',
]

VIDEO_PRESET_FIELD_ORDER = [
    'preset_id',
    'surface',
    'mode',
    'profile',
    'request',
    'advanced_adapters',
    'backend_assets',
    'post_process',
    'runtime_hint',
]


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        if value is None:
            return fallback
        clean = str(value).strip()
        if not clean:
            return fallback
        return int(float(clean))
    except Exception:
        return fallback


def _normalize_seed(value: Any) -> str:
    text = str(value or '').strip()
    return text[: VIDEO_INPUT_VALIDATION_RULES['seed']['max_length']] if text else ''


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'on', 'enabled'}


def _normalize_video_adapter_name(value: Any) -> str:
    return str(value or '').strip()[:255]


def _normalize_video_asset_name(value: Any) -> str:
    return str(value or '').strip()[:255]


def _video_backend_asset_defaults_for_profile(profile: str = '', *, mode: str = '') -> dict[str, str]:
    clean_profile = normalize_video_profile(profile or '', mode=mode)
    clean_mode = normalize_video_mode(mode)
    if clean_profile == 'wan22_14b_i2v_quality':
        return deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS['quality_i2v'])
    if clean_profile == 'wan22_14b_t2v_quality':
        return deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS['quality_t2v'])
    if clean_profile == 'raw_free':
        return deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS['quality_i2v' if clean_mode == 'i2v' else 'quality_t2v'])
    return deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS['balanced'])


def normalize_video_backend_assets(data: dict[str, Any] | None = None, *, profile: str = '', mode: str = '') -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    nested = payload.get('backend_assets') if isinstance(payload.get('backend_assets'), dict) else {}
    target_profile = normalize_video_profile(profile or payload.get('profile') or '', mode=mode or payload.get('mode') or '')
    balanced_defaults = deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS['balanced'])
    quality_defaults = _video_backend_asset_defaults_for_profile(target_profile, mode=mode or payload.get('mode') or '')
    return {
        'balanced_unet_name': _normalize_video_asset_name(nested.get('balanced_unet_name') or payload.get('balanced_unet_name') or payload.get('unet_name') or balanced_defaults.get('unet_name') or ''),
        'balanced_clip_name': _normalize_video_asset_name(nested.get('balanced_clip_name') or payload.get('balanced_clip_name') or payload.get('clip_name') or balanced_defaults.get('clip_name') or ''),
        'balanced_vae_name': _normalize_video_asset_name(nested.get('balanced_vae_name') or payload.get('balanced_vae_name') or payload.get('vae_name') or balanced_defaults.get('vae_name') or ''),
        'quality_high_noise_unet_name': _normalize_video_asset_name(nested.get('quality_high_noise_unet_name') or payload.get('quality_high_noise_unet_name') or quality_defaults.get('high_noise_unet_name') or ''),
        'quality_low_noise_unet_name': _normalize_video_asset_name(nested.get('quality_low_noise_unet_name') or payload.get('quality_low_noise_unet_name') or quality_defaults.get('low_noise_unet_name') or ''),
        'quality_clip_name': _normalize_video_asset_name(nested.get('quality_clip_name') or payload.get('quality_clip_name') or payload.get('clip_name_quality') or payload.get('clip_name') or quality_defaults.get('clip_name') or ''),
        'quality_vae_name': _normalize_video_asset_name(nested.get('quality_vae_name') or payload.get('quality_vae_name') or payload.get('vae_name_quality') or payload.get('vae_name') or quality_defaults.get('vae_name') or ''),
        'profile_scope': target_profile,
    }


def normalize_video_advanced_adapters(data: dict[str, Any] | None = None, *, profile: str = '') -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    nested = payload.get('advanced_adapters') if isinstance(payload.get('advanced_adapters'), dict) else {}
    target_profile = normalize_video_profile(profile or payload.get('profile') or '', mode=payload.get('mode') or '')
    enabled = _normalize_bool(nested.get('enabled') if 'enabled' in nested else payload.get('advanced_adapters_enabled') or payload.get('enable_adapters'))
    try:
        strength = float(nested.get('strength') if nested.get('strength') is not None else payload.get('adapter_strength') or VIDEO_ADVANCED_ADAPTER_SUPPORT['default_strength'])
    except Exception:
        strength = float(VIDEO_ADVANCED_ADAPTER_SUPPORT['default_strength'])
    strength = max(0.0, min(2.0, round(strength, 4)))
    capability = deepcopy((VIDEO_ADVANCED_ADAPTER_SUPPORT.get('profile_modes') or {}).get(target_profile) or {})
    adapter_mode = str(capability.get('mode') or ('paired' if target_profile in {'wan22_14b_t2v_quality', 'wan22_14b_i2v_quality'} else 'single')).strip() or 'single'
    single_adapter = _normalize_video_adapter_name(
        nested.get('single_adapter')
        or nested.get('adapter')
        or nested.get('adapter_name')
        or nested.get('lora_name')
        or payload.get('adapter_single')
        or payload.get('single_adapter')
        or payload.get('adapter_name')
        or payload.get('lora_name')
    )
    high_noise_adapter = _normalize_video_adapter_name(nested.get('high_noise_adapter') or nested.get('high_noise_name') or payload.get('adapter_high_noise') or payload.get('adapter_high_noise_name'))
    low_noise_adapter = _normalize_video_adapter_name(nested.get('low_noise_adapter') or nested.get('low_noise_name') or payload.get('adapter_low_noise') or payload.get('adapter_low_noise_name'))
    pair_preset_id = _normalize_video_adapter_name(nested.get('pair_preset_id') or payload.get('adapter_pair_preset_id'))
    pair_preset_name = _normalize_video_adapter_name(nested.get('pair_preset_name') or payload.get('adapter_pair_preset_name'))
    return {
        'enabled': bool(enabled),
        'supported': target_profile in VIDEO_ADVANCED_ADAPTER_SUPPORT['available_profiles'],
        'profile_mode': adapter_mode,
        'mode': adapter_mode,
        'pair_preset_id': pair_preset_id if adapter_mode == 'paired' else '',
        'pair_preset_name': pair_preset_name if adapter_mode == 'paired' else '',
        'strength': strength,
        'single_adapter': single_adapter if adapter_mode == 'single' else '',
        'high_noise_adapter': high_noise_adapter if adapter_mode == 'paired' else '',
        'low_noise_adapter': low_noise_adapter if adapter_mode == 'paired' else '',
    }


def _seed_is_valid(value: Any) -> bool:
    text = _normalize_seed(value)
    if not text:
        return True
    if text in {'-1', 'random'}:
        return True
    try:
        int(text)
        return True
    except Exception:
        return False


def list_video_modes(include_disabled: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in VIDEO_MODE_DEFINITIONS:
        row = deepcopy(VIDEO_MODE_DEFINITIONS[key])
        if include_disabled or row.get('enabled'):
            rows.append(row)
    return rows


def list_video_profiles(include_disabled: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in VIDEO_PROFILE_DEFINITIONS:
        row = deepcopy(VIDEO_PROFILE_DEFINITIONS[key])
        if include_disabled or row.get('enabled'):
            rows.append(row)
    return rows


def list_video_post_processes(include_disabled: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in VIDEO_POST_PROCESS_DEFINITIONS:
        row = deepcopy(VIDEO_POST_PROCESS_DEFINITIONS[key])
        if include_disabled or row.get('enabled'):
            rows.append(row)
    return rows


def list_video_post_pipeline_templates(include_disabled: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS:
        row = deepcopy(VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS[key])
        if include_disabled or row.get('enabled'):
            rows.append(row)
    return rows


def list_video_runtime_statuses() -> list[dict[str, Any]]:
    return [deepcopy(VIDEO_RUNTIME_STATUS_DEFINITIONS[key]) for key in VIDEO_RUNTIME_STATUS_DEFINITIONS]


def normalize_video_mode(value: str = '') -> str:
    clean = str(value or '').strip().lower()
    clean = VIDEO_MODE_ALIASES.get(clean, clean)
    return clean if clean in VIDEO_MODE_DEFINITIONS else 't2v'


def normalize_video_profile(value: str = '', *, mode: str = '') -> str:
    clean_mode = normalize_video_mode(mode)
    clean = str(value or '').strip().lower()
    clean = VIDEO_PROFILE_ALIASES.get(clean, clean)
    if clean in VIDEO_PROFILE_DEFINITIONS:
        if clean_mode and clean_mode in VIDEO_MODE_DEFINITIONS and clean in VIDEO_MODE_DEFINITIONS[clean_mode]['allowed_profiles']:
            return clean
        if not mode:
            return clean
    if clean_mode in VIDEO_MODE_DEFINITIONS:
        return VIDEO_MODE_DEFINITIONS[clean_mode].get('default_profile', 'wan22_5b_balanced')
    return 'wan22_5b_balanced'


def normalize_video_post_process(value: str = '') -> str:
    clean = str(value or '').strip().lower()
    return clean if clean in VIDEO_POST_PROCESS_DEFINITIONS else ''


def normalize_video_post_processes(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        clean = normalize_video_post_process(raw)
        if clean and clean not in seen:
            out.append(clean)
            seen.add(clean)
    return out


def normalize_video_post_pipeline_template(value: str = '') -> str:
    clean = str(value or '').strip().lower()
    return clean if clean in VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS else 'generate_only'



def match_video_post_pipeline_template(values: Iterable[str] | None) -> str:
    clean_steps = normalize_video_post_processes(values)
    for key, row in VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS.items():
        if normalize_video_post_processes(row.get('steps') or []) == clean_steps:
            return key
    return 'generate_only'



def get_video_post_pipeline_steps(template_id: str = '', *, fallback_values: Iterable[str] | None = None) -> list[str]:
    clean_template = normalize_video_post_pipeline_template(template_id or match_video_post_pipeline_template(fallback_values))
    row = VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS.get(clean_template) or VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS['generate_only']
    return normalize_video_post_processes(row.get('steps') or [])



def get_video_post_pipeline_label(template_id: str = '', *, fallback_values: Iterable[str] | None = None) -> str:
    clean_template = normalize_video_post_pipeline_template(template_id or match_video_post_pipeline_template(fallback_values))
    row = VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS.get(clean_template) or VIDEO_POST_PIPELINE_TEMPLATE_DEFINITIONS['generate_only']
    return str(row.get('label') or 'Generate only')


def normalize_video_runtime_status(value: str = '') -> str:
    clean = str(value or 'draft').strip().lower()
    return VIDEO_RUNTIME_STATUS_ALIASES.get(clean, 'draft')


def validate_video_request(data: dict[str, Any] | None) -> list[str]:
    payload = data if isinstance(data, dict) else {}
    errors: list[str] = []
    mode = normalize_video_mode(payload.get('mode') or payload.get('workflow_mode') or '')
    requested_profile = str(payload.get('profile') or '').strip().lower()
    normalized_requested_profile = VIDEO_PROFILE_ALIASES.get(requested_profile, requested_profile)
    profile = normalize_video_profile(requested_profile or '', mode=mode)
    prompt = str(payload.get('prompt') or '').strip()
    negative_prompt = str(payload.get('negative_prompt') or payload.get('negative') or '').strip()
    source_image = str(payload.get('source_image') or '').strip()
    size_preset = str(payload.get('size_preset') or payload.get('size') or '').strip()
    seed = _normalize_seed(payload.get('seed'))
    advanced_adapters = normalize_video_advanced_adapters(payload, profile=profile)
    try:
        duration_seconds = _coerce_int(payload.get('duration_seconds') or payload.get('duration'), 0)
    except Exception:
        duration_seconds = 0
    try:
        fps = _coerce_int(payload.get('fps'), 0)
    except Exception:
        fps = 0

    if len(prompt) < VIDEO_INPUT_VALIDATION_RULES['prompt']['min_length']:
        errors.append('Prompt is required.')
    if len(prompt) > VIDEO_INPUT_VALIDATION_RULES['prompt']['max_length']:
        errors.append('Prompt exceeds the maximum length for the video contract.')
    if len(negative_prompt) > VIDEO_INPUT_VALIDATION_RULES['negative_prompt']['max_length']:
        errors.append('Negative prompt exceeds the maximum length for the video contract.')
    if mode == 'i2v' and not source_image:
        errors.append('Source image is required for Image to Video mode.')
    if source_image and len(source_image) > VIDEO_INPUT_VALIDATION_RULES['source_image']['max_length']:
        errors.append('Source image path exceeds the maximum length for the video contract.')
    if duration_seconds < VIDEO_INPUT_VALIDATION_RULES['duration_seconds']['minimum'] or duration_seconds > VIDEO_INPUT_VALIDATION_RULES['duration_seconds']['maximum']:
        errors.append('Duration must stay within the frozen video contract range.')
    if fps < VIDEO_INPUT_VALIDATION_RULES['fps']['minimum'] or fps > VIDEO_INPUT_VALIDATION_RULES['fps']['maximum']:
        errors.append('FPS must stay within the frozen video contract range.')
    if size_preset not in VIDEO_INPUT_VALIDATION_RULES['size_preset']['allowed']:
        errors.append('Resolution preset is outside the frozen video contract.')
    if size_preset in {'custom', 'source_match', 'auto_source_fit'}:
        try:
            width = _coerce_int(payload.get('width'), 0)
            height = _coerce_int(payload.get('height'), 0)
        except Exception:
            width = 0
            height = 0
        if width <= 0 or height <= 0:
            errors.append('Custom video size needs width and height.')
        if size_preset in {'source_match', 'auto_source_fit'} and mode != 'i2v':
            errors.append('Source-driven video sizing is only valid for Image to Video mode.')
    if seed and len(seed) > VIDEO_INPUT_VALIDATION_RULES['seed']['max_length']:
        errors.append('Seed value exceeds the maximum length for the video contract.')
    if not _seed_is_valid(seed):
        errors.append('Seed must be blank, random, -1, or an integer.')
    if requested_profile and normalized_requested_profile not in VIDEO_PROFILE_DEFINITIONS:
        errors.append('Selected profile is outside the frozen video contract.')
    elif requested_profile and normalized_requested_profile not in VIDEO_MODE_DEFINITIONS[mode]['allowed_profiles']:
        errors.append('Selected profile is not valid for the current video mode.')
    elif not requested_profile and profile not in VIDEO_MODE_DEFINITIONS[mode]['allowed_profiles']:
        errors.append('Selected profile is not valid for the current video mode.')
    if advanced_adapters.get('enabled'):
        if profile not in VIDEO_ADVANCED_ADAPTER_SUPPORT['available_profiles']:
            errors.append('Advanced adapters are not available for the selected video profile.')
        elif str(advanced_adapters.get('mode') or advanced_adapters.get('profile_mode') or '').strip() == 'paired':
            if not advanced_adapters.get('high_noise_adapter') or not advanced_adapters.get('low_noise_adapter'):
                errors.append('Paired adapters need both the high-noise and low-noise slots filled.')
        else:
            if not advanced_adapters.get('single_adapter'):
                errors.append('Balanced adapters need a LoRA / adapter selected when the adapter lane is enabled.')
    return errors


def build_video_job_record(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    mode = normalize_video_mode(payload.get('mode') or payload.get('workflow_mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    post_pipeline_template = normalize_video_post_pipeline_template(payload.get('post_pipeline_template') or match_video_post_pipeline_template(payload.get('post_process')))
    post_process = get_video_post_pipeline_steps(post_pipeline_template, fallback_values=payload.get('post_process'))
    advanced_adapters = normalize_video_advanced_adapters(payload, profile=profile)
    backend_assets = normalize_video_backend_assets(payload, profile=profile, mode=mode)
    errors = validate_video_request({
        'mode': mode,
        'profile': profile,
        'prompt': payload.get('prompt'),
        'negative_prompt': payload.get('negative_prompt') or payload.get('negative'),
        'source_image': payload.get('source_image'),
        'duration_seconds': payload.get('duration_seconds') or payload.get('duration'),
        'fps': payload.get('fps'),
        'size_preset': payload.get('size_preset') or payload.get('size'),
        'seed': payload.get('seed'),
        'advanced_adapters': advanced_adapters,
    })
    now = _now_iso()
    job_id = str(payload.get('job_id') or payload.get('id') or f'video_job_{uuid4().hex[:10]}').strip()
    return {
        'schema_version': VIDEO_JOB_SCHEMA_VERSION,
        'record_type': 'video_job',
        'job_id': job_id,
        'id': job_id,
        'surface': 'video',
        'mode': mode,
        'profile': profile,
        'status': normalize_video_runtime_status(payload.get('status') or ('draft' if errors else 'validating')),
        'created_at': str(payload.get('created_at') or now),
        'updated_at': str(payload.get('updated_at') or now),
        'request': {
            'prompt': str(payload.get('prompt') or '').strip(),
            'negative_prompt': str(payload.get('negative_prompt') or payload.get('negative') or '').strip(),
            'source_image': str(payload.get('source_image') or '').strip(),
            'duration_seconds': _coerce_int(payload.get('duration_seconds') or payload.get('duration'), 5),
            'fps': _coerce_int(payload.get('fps'), 16),
            'size_preset': str(payload.get('size_preset') or payload.get('size') or '832x480').strip(),
            'width': _coerce_int(payload.get('width'), 0),
            'height': _coerce_int(payload.get('height'), 0),
            'seed': _normalize_seed(payload.get('seed')),
        },
        'advanced_adapters': advanced_adapters,
        'backend_assets': backend_assets,
        'post_pipeline_template': post_pipeline_template,
        'post_pipeline_label': get_video_post_pipeline_label(post_pipeline_template),
        'post_process': post_process,
        'runtime': {
            'backend_role': 'video',
            'heaviness': str(payload.get('heaviness') or VIDEO_PROFILE_DEFINITIONS[profile].get('vram_class') or 'light'),
            'warnings': [str(item).strip() for item in (payload.get('warnings') or []) if str(item).strip()],
            'validation_errors': errors,
        },
        'lineage': {
            'preset_id': str(payload.get('preset_id') or '').strip(),
            'source_job_id': str(payload.get('source_job_id') or '').strip(),
            'source_result_id': str(payload.get('source_result_id') or '').strip(),
        },
        'result': {
            'result_id': str(payload.get('result_id') or '').strip(),
            'output_ids': [str(item).strip() for item in (payload.get('output_ids') or []) if str(item).strip()],
        },
    }


def build_video_result_record(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    now = _now_iso()
    result_id = str(payload.get('result_id') or payload.get('id') or f'video_result_{uuid4().hex[:10]}').strip()
    outputs: list[dict[str, Any]] = []
    for item in payload.get('outputs') or []:
        if not isinstance(item, dict):
            continue
        outputs.append({
            'output_id': str(item.get('output_id') or item.get('id') or '').strip(),
            'media_type': str(item.get('media_type') or 'video').strip() or 'video',
            'path': str(item.get('path') or '').strip(),
            'filename': str(item.get('filename') or '').strip(),
            'duration_seconds': item.get('duration_seconds'),
            'fps': item.get('fps'),
            'size_preset': str(item.get('size_preset') or item.get('resolution') or '').strip(),
        })
    error = payload.get('error') if isinstance(payload.get('error'), dict) else {}
    return {
        'schema_version': VIDEO_RESULT_SCHEMA_VERSION,
        'record_type': 'video_result',
        'result_id': result_id,
        'id': result_id,
        'job_id': str(payload.get('job_id') or '').strip(),
        'surface': 'video',
        'mode': mode,
        'profile': profile,
        'status': normalize_video_runtime_status(payload.get('status') or 'draft'),
        'created_at': str(payload.get('created_at') or now),
        'updated_at': str(payload.get('updated_at') or now),
        'outputs': outputs,
        'artifacts': {
            'manifest_path': str((payload.get('artifacts') or {}).get('manifest_path') or '').strip(),
            'preview_path': str((payload.get('artifacts') or {}).get('preview_path') or '').strip(),
        },
        'metrics': {
            'queue_seconds': (payload.get('metrics') or {}).get('queue_seconds'),
            'runtime_seconds': (payload.get('metrics') or {}).get('runtime_seconds'),
        },
        'error': {
            'code': str(error.get('code') or '').strip(),
            'message': str(error.get('message') or '').strip(),
        },
    }


def normalize_video_preset_record(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    now = _now_iso()
    preset_id = str(payload.get('preset_id') or payload.get('id') or f'video_preset_{uuid4().hex[:10]}').strip()
    post_pipeline_template = normalize_video_post_pipeline_template(payload.get('post_pipeline_template') or match_video_post_pipeline_template(payload.get('post_process')))
    post_process = get_video_post_pipeline_steps(post_pipeline_template, fallback_values=payload.get('post_process'))
    advanced_adapters = normalize_video_advanced_adapters(payload, profile=profile)
    backend_assets = normalize_video_backend_assets(payload, profile=profile, mode=mode)
    return {
        'schema_version': VIDEO_PRESET_SCHEMA_VERSION,
        'record_type': 'video_preset',
        'preset_id': preset_id,
        'id': preset_id,
        'surface': 'video',
        'name': str(payload.get('name') or 'Untitled video preset').strip(),
        'mode': mode,
        'profile': profile,
        'request': {
            'prompt': str((payload.get('request') or {}).get('prompt') or payload.get('prompt') or '').strip(),
            'negative_prompt': str((payload.get('request') or {}).get('negative_prompt') or payload.get('negative_prompt') or '').strip(),
            'duration_seconds': _coerce_int((payload.get('request') or {}).get('duration_seconds') or payload.get('duration_seconds'), 5),
            'fps': _coerce_int((payload.get('request') or {}).get('fps') or payload.get('fps'), 16),
            'size_preset': str((payload.get('request') or {}).get('size_preset') or payload.get('size_preset') or '832x480').strip(),
            'width': _coerce_int((payload.get('request') or {}).get('width') or payload.get('width'), 0),
            'height': _coerce_int((payload.get('request') or {}).get('height') or payload.get('height'), 0),
            'seed': _normalize_seed((payload.get('request') or {}).get('seed') or payload.get('seed')),
        },
        'advanced_adapters': advanced_adapters,
        'backend_assets': backend_assets,
        'post_pipeline_template': post_pipeline_template,
        'post_pipeline_label': get_video_post_pipeline_label(post_pipeline_template),
        'post_process': post_process,
        'runtime_hint': {
            'heaviness': str((payload.get('runtime_hint') or {}).get('heaviness') or VIDEO_PROFILE_DEFINITIONS[profile].get('vram_class') or 'light'),
            'notes': str((payload.get('runtime_hint') or {}).get('notes') or payload.get('notes') or '').strip(),
        },
        'source': str(payload.get('source') or 'custom').strip() or 'custom',
        'updated_at': str(payload.get('updated_at') or now),
    }


def build_video_contract_boot_payload() -> dict[str, Any]:
    return {
        'schema_version': VIDEO_CONTRACT_SCHEMA_VERSION,
        'surface': 'video',
        'modes': list_video_modes(include_disabled=False),
        'profiles': list_video_profiles(include_disabled=False),
        'post_process': list_video_post_processes(include_disabled=False),
        'post_pipeline_templates': list_video_post_pipeline_templates(include_disabled=False),
        'runtime_status': list_video_runtime_statuses(),
        'validation_rules': deepcopy(VIDEO_INPUT_VALIDATION_RULES),
        'advanced_adapter_support': deepcopy(VIDEO_ADVANCED_ADAPTER_SUPPORT),
        'backend_asset_defaults': deepcopy(VIDEO_BACKEND_ASSET_DEFAULTS),
        'schemas': {
            'job': {
                'schema_version': VIDEO_JOB_SCHEMA_VERSION,
                'record_type': 'video_job',
                'field_order': list(VIDEO_JOB_FIELD_ORDER),
                'required_fields': ['job_id', 'surface', 'mode', 'profile', 'status', 'request', 'post_process', 'runtime'],
                'request_fields': ['prompt', 'negative_prompt', 'source_image', 'duration_seconds', 'fps', 'size_preset', 'width', 'height', 'seed'],
                'optional_fields': ['advanced_adapters', 'backend_assets', 'post_pipeline_template'],
            },
            'result': {
                'schema_version': VIDEO_RESULT_SCHEMA_VERSION,
                'record_type': 'video_result',
                'field_order': list(VIDEO_RESULT_FIELD_ORDER),
                'required_fields': ['result_id', 'job_id', 'surface', 'mode', 'profile', 'status', 'outputs', 'artifacts', 'metrics', 'error'],
            },
            'preset': {
                'schema_version': VIDEO_PRESET_SCHEMA_VERSION,
                'record_type': 'video_preset',
                'field_order': list(VIDEO_PRESET_FIELD_ORDER),
                'required_fields': ['preset_id', 'surface', 'mode', 'profile', 'request', 'post_process', 'runtime_hint'],
                'optional_fields': ['advanced_adapters', 'backend_assets', 'post_pipeline_template'],
            },
        },
        'schema_templates': {
            'job': build_video_job_record({}),
            'result': build_video_result_record({}),
            'preset': normalize_video_preset_record({}),
        },
        'defaults': {
            'mode': 't2v',
            'profile': 'wan22_5b_balanced',
            'duration_seconds': 5,
            'fps': 16,
            'size_preset': '832x480',
            'post_process': [],
            'post_pipeline_template': 'generate_only',
            'seed': '',
            'advanced_adapters': normalize_video_advanced_adapters({}),
            'backend_assets': normalize_video_backend_assets({}),
        },
        'v1_exclusions': ['camera_control', 'first_frame_last_frame', 'speech_to_video', 'animate', 'lora_training', 'raw_workflow_editing'],
    }
