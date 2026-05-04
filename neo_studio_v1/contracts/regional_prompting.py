from __future__ import annotations

from typing import Any

REGIONAL_BACKEND_IDS = ('auto', 'native', 'node', 'dense_diffusion')
REGIONAL_SUPPORTED_FAMILIES = ('sdxl_sd',)
REGIONAL_SUPPORTED_MODES_V1 = ('txt2img',)
REGIONAL_SUPPORTED_MODES_FUTURE = ('txt2img', 'img2img')

DENSE_DIFFUSION_REQUIRED_NODES = (
    'DenseDiffusionAddCondNode',
    'DenseDiffusionApplyNode',
    'smZ Conditioning Normalize',
)

DENSE_DIFFUSION_PREFERRED_NODES = (
    'smZ CLIPTextEncode',
)

DENSE_DIFFUSION_OPTIONAL_NODE_GROUPS = (
    'ControlNetLoader',
    'DepthAnythingV2Preprocessor',
    'ControlNetApplyAdvanced',
    'UltralyticsDetectorProvider',
    'BboxDetectorSEGS',
    'ImpactSEGSOrderedFilter',
    'MaskToSEGS',
    'ZML_YoloToMask',
    'ZML_MaskSeparateDistance',
    'UltimateSDUpscale',
    'rgthree utility nodes',
)

REGIONAL_PROMOTION_GATE = {
    'native': {
        'status': 'promoted',
        'promoted': True,
        'verified_case_count': 5,
        'minimum_verified_case_count': 5,
        'acceptance_met': True,
        'notes': [
            'Native mask conditioning remains available as the basic fallback regional path.',
            'Use it when the Node backend is unavailable or when you want the lighter built-in masked composer.',
        ],
    },
    'node': {
        'status': 'promoted',
        'promoted': True,
        'verified_case_count': 4,
        'minimum_verified_case_count': 4,
        'acceptance_met': True,
        'notes': [
            'Impact Pack regional backend is the current advanced production path after the Sprint 5 repair pass.',
            'Keep sampler safety guardrails in place because unsupported sampler combinations can still produce noise.',
        ],
    },
    'dense_diffusion': {
        'status': 'hidden',
        'promoted': False,
        'verified_case_count': 0,
        'minimum_verified_case_count': 4,
        'acceptance_met': False,
        'notes': [
            'Dense Diffusion is hidden in normal UI because the current environment still fails regional compatibility checks.',
            'Do not re-enable until the backend passes a dedicated compatibility repair and regression sweep.',
        ],
    },
}



def build_regional_testing_matrix() -> dict[str, Any]:
    return {
        'required_test_cases': [
            {
                'id': 'two_people_split_wardrobe',
                'title': 'Two people · split wardrobe',
                'goal': 'Left/right subjects keep their own clothing and styling without swapping.',
                'checks': ['distinct clothing preserved', 'minimal face/style contamination', 'masks visibly matter'],
            },
            {
                'id': 'subject_vs_prop',
                'title': 'Subject vs prop',
                'goal': 'Object prompt stays inside its region instead of leaking into the subject.',
                'checks': ['prop stays local', 'global scene prompt remains coherent'],
            },
            {
                'id': 'opposed_styles',
                'title': 'Opposed styles',
                'goal': 'Strongly different region prompts remain separated under the same global scene.',
                'checks': ['minimal cross-contamination', 'region prompts remain legible'],
            },
            {
                'id': 'negative_pressure',
                'title': 'Negative pressure',
                'goal': 'Global negative prompt does not collapse local region intent into mush.',
                'checks': ['global negative remains stable', 'regional positives still differentiate subjects'],
            },
        ],
        'promotion_rule': {
            'minimum_verified_case_count': 4,
            'must_pass_all_required_cases': True,
            'must_match_truth_ui': True,
            'must_restore_saved_state_cleanly': True,
            'must_not_hide_backend_fallbacks': True,
        },
    }


def build_regional_promotion_gate() -> dict[str, Any]:
    return {
        'sprint': 'Sprint 4 — testing + promotion gate',
        'gate': REGIONAL_PROMOTION_GATE,
        'testing_matrix': build_regional_testing_matrix(),
        'summary': {
            'current_promoted_backend': 'node',
            'dense_diffusion_release_state': 'hidden_disabled',
            'node_backend_release_state': 'promoted',
        },
    }


def normalize_regional_backend_mode(value: Any, default: str = 'auto') -> str:
    backend = str(value or default).strip().lower() or default
    if backend not in REGIONAL_BACKEND_IDS:
        return default
    return backend


def build_dense_diffusion_contract() -> dict[str, Any]:
    return {
        'id': 'dense_diffusion',
        'label': 'Advanced Regional (Dense Diffusion)',
        'status': 'available_if_dependencies_exist',
        'experimental': True,
        'default': False,
        'supported_families': list(REGIONAL_SUPPORTED_FAMILIES),
        'supported_modes_v1': list(REGIONAL_SUPPORTED_MODES_V1),
        'supported_modes_future': list(REGIONAL_SUPPORTED_MODES_FUTURE),
        'required_nodes': list(DENSE_DIFFUSION_REQUIRED_NODES),
        'preferred_nodes': list(DENSE_DIFFUSION_PREFERRED_NODES),
        'optional_node_groups': list(DENSE_DIFFUSION_OPTIONAL_NODE_GROUPS),
        'excluded_from_first_pass': [
            'automatic detection/detailers',
            'ControlNet depth extras',
            'upscalers/post-processing',
            'hand/face repair lanes',
            'YOLO/SEGS auto-splitting helpers',
        ],
        'region_contract': {
            'required': ['id', 'label', 'prompt', 'mask_image', 'strength', 'enabled', 'order'],
            'optional': ['negative_prompt'],
        },
        'notes': [
            'Sprint 2 adds a minimal SDXL txt2img compiler branch using Dense Diffusion model patching.',
            'Per-region negatives are still intentionally limited in the first pass; keep the global negative prompt as the main safety rail.',
            'Advanced backend should remain SDXL-only until it proves better region separation than the native backend.',
        ],
    }


def build_regional_prompt_contract() -> dict[str, Any]:
    return {
        'sprint': 'Sprint 1 — Audit + contract',
        'current_default_backend': 'node',
        'future_backend_candidates': [],
        'supported_families': list(REGIONAL_SUPPORTED_FAMILIES),
        'supported_modes_v1': list(REGIONAL_SUPPORTED_MODES_V1),
        'supported_modes_future': list(REGIONAL_SUPPORTED_MODES_FUTURE),
        'backends': {
            'native': {
                'label': 'Native Regional',
                'status': 'available',
                'default': False,
                'notes': ['Basic fallback regional composer path.', 'Keeps the existing Neo UI contract intact when the advanced backend is unavailable.'],
            },
            'node': {
                'label': 'Impact Pack Regional',
                'status': 'available_if_dependencies_exist',
                'default': True,
                'notes': ['Current advanced regional backend using RegionalPrompt / RegionalSampler nodes.', 'Known sampler safety limits are tracked in the runtime capability matrix.'],
            },
            'dense_diffusion': build_dense_diffusion_contract(),
        },
    }
