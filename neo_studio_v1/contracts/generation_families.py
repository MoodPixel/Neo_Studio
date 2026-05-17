from __future__ import annotations

from copy import deepcopy

GENERATION_FAMILY_SCHEMA_VERSION = 3

_MODE_ALIASES = {
    'txt2img_basic': 'txt2img',
    'txt2img_shell': 'txt2img',
    'img2img_shell': 'img2img',
    'inpaint_shell': 'inpaint',
    'outpaint_shell': 'outpaint',
}


def normalize_generation_mode(mode: str | None) -> str:
    value = str(mode or 'txt2img').strip().lower() or 'txt2img'
    return _MODE_ALIASES.get(value, value)


def normalize_inpaint_backend(backend: str | None) -> str:
    value = str(backend or 'standard').strip().lower()
    return value if value in {'standard', 'lanpaint'} else 'standard'


GENERATION_FAMILY_DEFINITIONS = {
    'sdxl_sd': {
        'schema_version': GENERATION_FAMILY_SCHEMA_VERSION,
        'id': 'sdxl_sd',
        'surface': 'generate',
        'label': 'SDXL / SD',
        'backend_role': 'image',
        'enabled': True,
        'supports': {
            'txt2img': True,
            'img2img': True,
            'inpaint': True,
            'outpaint': True,
            'controlnet': True,
            'ipadapter': True,
            'lora': True,
            'metadata_replay': True,
            'helper_bridge': True,
        },
        'mode_backend_support': {
            'inpaint': {
                'standard': {'enabled': True, 'status': 'stable', 'reason': 'SDXL / SD uses the classic latent inpaint path today.'},
                'lanpaint': {'enabled': True, 'status': 'experimental', 'reason': 'SDXL / SD LanPaint inpaint is available in this build. Sampler/schema compatibility is validated against the live LanPaint_KSampler node before queueing.'},
            },
            'outpaint': {
                'standard': {'enabled': True, 'status': 'stable', 'reason': 'Outpaint currently stays on the standard SDXL / SD path.'},
                'lanpaint': {'enabled': False, 'status': 'planned', 'reason': 'LanPaint outpaint is not wired for SDXL / SD yet.'},
            },
        },
        'visible_sections': ['workspace_setup', 'build', 'assets', 'reference', 'finish', 'helper', 'results', 'preview'],
        'default_preset_ids': [],
        'input_types': ['text', 'image', 'mask'],
        'output_types': ['image'],
    },
    'flux': {
        'schema_version': GENERATION_FAMILY_SCHEMA_VERSION,
        'id': 'flux',
        'surface': 'generate',
        'label': 'Flux',
        'backend_role': 'image',
        'enabled': True,
        'supports': {
            'txt2img': True,
            'img2img': True,
            'inpaint': False,
            'outpaint': True,
            'controlnet': False,
            'ipadapter': False,
            'lora': True,
            'metadata_replay': True,
            'helper_bridge': True,
        },
        'mode_backend_support': {
            'inpaint': {
                'lanpaint': {'enabled': False, 'status': 'planned', 'reason': 'Flux inpaint is staged for a later LanPaint pass and is not available yet.'},
            },
            'outpaint': {
                'standard': {'enabled': True, 'status': 'experimental', 'reason': 'Flux outpaint uses the standard padded-source latent outpaint route with Flux sampling, not a LanPaint route.'},
                'lanpaint': {'enabled': False, 'status': 'planned', 'reason': 'Flux LanPaint outpaint is staged for a later pass; use the standard Flux padded-source outpaint route instead.'},
            },
        },
        'visible_sections': ['workspace_setup', 'build', 'assets', 'finish', 'helper', 'results', 'preview'],
        'default_preset_ids': [],
        'input_types': ['text', 'image'],
        'output_types': ['image'],
    },
    'qwen_image_edit': {
        'schema_version': GENERATION_FAMILY_SCHEMA_VERSION,
        'id': 'qwen_image_edit',
        'surface': 'generate',
        'label': 'Qwen Image Edit',
        'backend_role': 'image',
        'enabled': True,
        'supports': {
            'txt2img': True,
            'img2img': True,
            'inpaint': True,
            'outpaint': True,
            'controlnet': False,
            'ipadapter': False,
            'lora': False,
            'metadata_replay': True,
            'helper_bridge': True,
        },
        'mode_backend_support': {
            'inpaint': {
                'standard': {'enabled': False, 'status': 'unavailable', 'reason': 'Qwen Image Edit routes live inpaint through LanPaint, not the standard latent path.'},
                'lanpaint': {'enabled': True, 'status': 'experimental', 'reason': 'Qwen LanPaint inpaint is live in this build. Outpaint uses the separate Qwen padded-source image-edit route.'},
            },
            'outpaint': {
                'standard': {'enabled': True, 'status': 'experimental', 'reason': 'Qwen Image Edit outpaint uses the Qwen image-edit padded-source route, not the SDXL latent outpaint sampler path.'},
                'lanpaint': {'enabled': False, 'status': 'planned', 'reason': 'Qwen LanPaint outpaint is not used for this route; use the Qwen image-edit padded-source route instead.'},
            },
        },
        'visible_sections': ['workspace_setup', 'build', 'assets', 'finish', 'helper', 'results', 'preview'],
        'default_preset_ids': [],
        'input_types': ['text', 'image', 'instruction'],
        'output_types': ['image'],
    },
    'zimage': {
        'schema_version': GENERATION_FAMILY_SCHEMA_VERSION,
        'id': 'zimage',
        'surface': 'generate',
        'label': 'Zimage',
        'backend_role': 'image',
        'enabled': True,
        'supports': {
            'txt2img': True,
            'img2img': True,
            'inpaint': False,
            'outpaint': False,
            'controlnet': False,
            'ipadapter': False,
            'lora': False,
            'metadata_replay': True,
            'helper_bridge': True,
        },
        'mode_backend_support': {
            'inpaint': {
                'standard': {'enabled': False, 'status': 'unavailable', 'reason': 'Zimage does not expose an inpaint backend in this build.'},
                'lanpaint': {'enabled': False, 'status': 'unavailable', 'reason': 'Zimage does not expose a LanPaint backend in this build.'},
            },
            'outpaint': {
                'standard': {'enabled': False, 'status': 'unavailable', 'reason': 'Zimage does not expose an outpaint backend in this build.'},
                'lanpaint': {'enabled': False, 'status': 'unavailable', 'reason': 'Zimage does not expose a LanPaint outpaint backend in this build.'},
            },
        },
        'visible_sections': ['workspace_setup', 'build', 'assets', 'helper', 'results', 'preview'],
        'default_preset_ids': [],
        'input_types': ['text', 'image'],
        'output_types': ['image'],
    },
}


def get_generation_family_definition(family: str | None) -> dict:
    key = str(family or 'sdxl_sd').strip().lower() or 'sdxl_sd'
    return deepcopy(GENERATION_FAMILY_DEFINITIONS.get(key) or GENERATION_FAMILY_DEFINITIONS['sdxl_sd'])


def list_generation_families(include_disabled: bool = True) -> list[dict]:
    rows = []
    for key in GENERATION_FAMILY_DEFINITIONS:
        row = deepcopy(GENERATION_FAMILY_DEFINITIONS[key])
        if include_disabled or row.get('enabled'):
            rows.append(row)
    return rows


def get_supported_generation_modes(family: str | None) -> list[str]:
    row = get_generation_family_definition(family)
    supports = row.get('supports') or {}
    ordered = ['txt2img', 'img2img', 'inpaint', 'outpaint']
    return [mode for mode in ordered if bool(supports.get(mode))]


def _mode_backend_row(row: dict, mode: str) -> dict:
    return deepcopy(((row.get('mode_backend_support') or {}).get(mode) or {}))


def validate_generation_support(family: str | None, mode: str | None, inpaint_backend: str | None = None) -> dict:
    row = get_generation_family_definition(family)
    normalized_family = str(row.get('id') or 'sdxl_sd')
    normalized_mode = normalize_generation_mode(mode)
    backend = normalize_inpaint_backend(inpaint_backend)
    supports = row.get('supports') or {}

    if normalized_mode not in {'txt2img', 'img2img', 'inpaint', 'outpaint'}:
        return {
            'ok': False,
            'family': normalized_family,
            'mode': normalized_mode,
            'backend': backend,
            'message': 'Unsupported generation mode.',
            'reason': 'unsupported_mode',
            'status': 'error',
        }

    if not bool(supports.get(normalized_mode)):
        mode_row = _mode_backend_row(row, normalized_mode)
        backend_row = mode_row.get(backend) or {}
        message = str(backend_row.get('reason') or f"{row.get('label') or normalized_family} does not support {normalized_mode} in this build.")
        return {
            'ok': False,
            'family': normalized_family,
            'mode': normalized_mode,
            'backend': backend,
            'message': message,
            'reason': 'mode_disabled',
            'status': str(backend_row.get('status') or 'unavailable'),
        }

    if normalized_mode in {'inpaint', 'outpaint'}:
        mode_row = _mode_backend_row(row, normalized_mode)
        if mode_row:
            backend_row = mode_row.get(backend)
            if not backend_row or not bool(backend_row.get('enabled')):
                fallback_reason = f"{row.get('label') or normalized_family} does not support {backend} for {normalized_mode} in this build."
                return {
                    'ok': False,
                    'family': normalized_family,
                    'mode': normalized_mode,
                    'backend': backend,
                    'message': str((backend_row or {}).get('reason') or fallback_reason),
                    'reason': 'backend_disabled',
                    'status': str((backend_row or {}).get('status') or 'unavailable'),
                }

    return {
        'ok': True,
        'family': normalized_family,
        'mode': normalized_mode,
        'backend': backend,
        'message': '',
        'reason': 'ok',
        'status': 'enabled',
    }
