from __future__ import annotations

import json
import math
import random
import re
from typing import Any, Dict, Tuple

from ..contracts.generation_families import normalize_generation_mode, normalize_inpaint_backend, validate_generation_support
from ..contracts.inpaint_payloads import merge_shared_inpaint_payload, get_shared_inpaint_payload
from ..config.feature_flags import REGIONAL_ENABLE_NODE_BACKEND, REGIONAL_ENABLE_DENSE_DIFFUSION, REGIONAL_ENABLE_EXPERIMENTAL

VALID_SAMPLERS = {
    'euler',
    'euler_ancestral',
    'heun',
    'heunpp2',
    'dpm_2',
    'dpm_2_ancestral',
    'lms',
    'dpm_fast',
    'dpm_adaptive',
    'dpmpp_2s_ancestral',
    'dpmpp_sde',
    'dpmpp_sde_gpu',
    'dpmpp_2m',
    'dpmpp_2m_sde',
    'dpmpp_2m_sde_gpu',
    'dpmpp_3m_sde',
    'res_multistep',
    'ddim',
    'uni_pc',
    'uni_pc_bh2',
    'lcm',
    'plms',
}

SAMPLER_ALIASES = {
    'euler a': 'euler_ancestral',
    'euler_a': 'euler_ancestral',
    'heun++ 2': 'heunpp2',
    'heunpp2': 'heunpp2',
    'dpm++ 2m': 'dpmpp_2m',
    'dpmpp_2m': 'dpmpp_2m',
    'unipc': 'uni_pc',
    'uni_pc': 'uni_pc',
}

VALID_LANPAINT_SAMPLERS = {
    'euler',
    'euler_ancestral',
    'heun',
    'heunpp2',
    'dpm_2',
    'dpm_2_ancestral',
    'ddim',
}

VALID_LANPAINT_SCHEDULERS = {
    'normal',
    'simple',
    'ddim_uniform',
}

LANPAINT_SAMPLER_RULES_BY_FAMILY = {
    'sdxl_sd': {
        'default_sampler': 'heun',
        'default_scheduler': 'normal',
        'allowed_samplers': {'euler', 'euler_ancestral', 'heun', 'heunpp2', 'dpm_2', 'dpm_2_ancestral', 'ddim'},
        'allowed_schedulers': {'normal', 'simple', 'ddim_uniform'},
        'policy': 'SDXL / SD LanPaint allows deterministic/ODE-style base samplers. Heun is the realism-first default.',
    },
    'qwen_image_edit': {
        'default_sampler': 'euler',
        'default_scheduler': 'simple',
        'allowed_samplers': {'euler'},
        'allowed_schedulers': {'simple'},
        'policy': 'Qwen LanPaint stays conservative for the current GGUF/Rapid graph until broader sampler combinations are validated.',
    },
    'flux': {
        'default_sampler': 'euler',
        'default_scheduler': 'simple',
        'allowed_samplers': {'euler'},
        'allowed_schedulers': {'simple'},
        'policy': 'Flux LanPaint is experimental/limited in this build and should stay on low-guidance conservative defaults when enabled later.',
    },
}

PROMPT_WEIGHT_PATTERN = re.compile(r'[\(\[]\s*([^\(\)\[\]]+?)\s*:\s*(-?\d*\.?\d+)\s*[\)\]]')


def _as_ref(value: Any) -> list[Any] | None:
    """Normalize a Comfy node ref into a safe two-item list."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return [str(value[0]), int(value[1])]
        except Exception:
            return [str(value[0]), 0]
    return None


def _add_load_image_node(graph: Dict[str, Any], next_id: int, image_name: Any, *, upload: str = 'image') -> tuple[int, list[Any]]:
    """Shared image-source loader for all image-based builders."""
    image_name = str(image_name or '').strip()
    if not image_name:
        raise ValueError('A source image is required for this workflow path.')
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': image_name,
            'upload': upload or 'image',
        },
    }
    return next_id + 1, [str(node_id), 0]


def _add_save_image_node(graph: Dict[str, Any], next_id: int, image_ref: Any, *, prefix: str = 'NeoStudio') -> tuple[int, list[Any]]:
    """Shared final SaveImage node so main/preview/upscale builders terminate consistently."""
    normalized_ref = _as_ref(image_ref)
    if normalized_ref is None:
        raise ValueError('SaveImage needs a valid image reference.')
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'SaveImage',
        'inputs': {
            'filename_prefix': str(prefix or 'NeoStudio'),
            'images': list(normalized_ref),
        },
    }
    return next_id + 1, [str(node_id), 0]


def _normalize_preview_action_contract(payload: Dict[str, Any]) -> dict[str, Any]:
    """Read the Phase 2 preview-action envelope into one backend-facing shape."""
    raw = payload.get('_neo_preview_action')
    if not isinstance(raw, dict):
        raw = {}
    action_type = str(raw.get('action_type') or payload.get('preview_action_type') or '').strip().lower()
    execution_mode = str(raw.get('execution_mode') or payload.get('mode') or payload.get('workflow_type') or '').strip().lower()
    save_lane = str(raw.get('save_lane') or payload.get('save_mode_override') or payload.get('output_mode_override') or payload.get('mode') or '').strip().lower()
    return {
        'action_type': action_type,
        'source_output_id': str(raw.get('source_output_id') or payload.get('source_output_id') or '').strip(),
        'source_output_key': str(raw.get('source_output_key') or payload.get('source_output_key') or '').strip(),
        'parent_output_key': str(raw.get('parent_output_key') or payload.get('parent_output_key') or '').strip(),
        'execution_mode': execution_mode,
        'workflow_variant': str(raw.get('workflow_variant') or payload.get('workflow_variant') or '').strip().lower(),
        'save_lane': save_lane,
        'derived_stage': str(raw.get('derived_stage') or payload.get('derived_stage') or '').strip().lower(),
        'parent_job_id': str(raw.get('parent_job_id') or payload.get('parent_job_id') or '').strip(),
        'source_job_id': str(raw.get('source_job_id') or payload.get('source_job_id') or '').strip(),
    }


def _normalize_workflow_builder_contract(payload: Dict[str, Any], *, builder_name: str, mode: Any = '', source_image_name: Any = '') -> dict[str, Any]:
    """Shared backend workflow-builder contract for Phase 3 normalization."""
    preview_action = _normalize_preview_action_contract(payload)
    requested_mode = str(mode or payload.get('mode') or payload.get('workflow_type') or '').strip().lower()
    source_image = str(source_image_name or payload.get('source_image_name') or '').strip()
    source_policy = str(payload.get('source_resize_mode') or '').strip().lower()
    if bool(payload.get('detailer_output_pass')) and source_image:
        source_policy = 'native'
    if not source_policy:
        source_policy = 'native' if source_image else 'none'
    save_lane = preview_action.get('save_lane') or str(payload.get('save_mode_override') or payload.get('output_mode_override') or requested_mode or builder_name).strip().lower()
    return {
        'schema_version': 1,
        'builder_name': str(builder_name or '').strip().lower(),
        'requested_mode': requested_mode,
        'execution_mode': preview_action.get('execution_mode') or requested_mode,
        'workflow_type': str(payload.get('workflow_type') or requested_mode).strip().lower(),
        'source_image_name': source_image,
        'source_policy': source_policy,
        'save_lane': save_lane,
        'preview_action': preview_action,
    }


def _attach_builder_contract(payload: Dict[str, Any], contract: dict[str, Any], compile_notes: list[str] | None = None) -> None:
    """Stamp normalized builder metadata onto the payload for job/debug parity."""
    payload['_neo_builder_contract'] = contract
    if compile_notes is not None:
        action = (contract.get('preview_action') or {}).get('action_type') or 'main'
        compile_notes.append(
            f"Workflow builder normalized · {contract.get('builder_name')} · exec {contract.get('execution_mode') or contract.get('requested_mode')} · save {contract.get('save_lane')} · action {action}."
        )


def normalize_sampler_name(value: str) -> str:
    text = str(value or '').strip().lower()
    text = SAMPLER_ALIASES.get(text, text)
    return text or 'euler'


def normalize_scheduler_name(value: str) -> str:
    text = str(value or '').strip().lower()
    aliases = {
        'sgm uniform': 'sgm_uniform',
        'linear quadratic': 'linear_quadratic',
        'kl optimal': 'kl_optimal',
        'ddim uniform': 'ddim_uniform',
        'align your steps': 'align_your_steps',
        'polyexponential': 'polyexponential',
    }
    return aliases.get(text, text or 'normal')


def get_lanpaint_sampler_policy(family: str | None) -> dict[str, Any]:
    key = str(family or 'sdxl_sd').strip().lower()
    return LANPAINT_SAMPLER_RULES_BY_FAMILY.get(key, LANPAINT_SAMPLER_RULES_BY_FAMILY['sdxl_sd'])


def apply_lanpaint_sampler_policy(
    family: str | None,
    sampler_name: str,
    scheduler_name: str,
) -> tuple[str, str, list[str]]:
    policy = get_lanpaint_sampler_policy(family)
    requested_sampler = normalize_sampler_name(sampler_name)
    requested_scheduler = normalize_scheduler_name(scheduler_name)
    effective_sampler = requested_sampler
    effective_scheduler = requested_scheduler
    notes: list[str] = []

    if requested_sampler not in policy['allowed_samplers']:
        effective_sampler = policy['default_sampler']
        notes.append(
            f"LanPaint sampler auto-fixed for {family or 'sdxl_sd'}: {requested_sampler} is not in this family policy, using {effective_sampler}."
        )
    if requested_scheduler not in policy['allowed_schedulers']:
        effective_scheduler = policy['default_scheduler']
        notes.append(
            f"LanPaint scheduler auto-fixed for {family or 'sdxl_sd'}: {requested_scheduler} is not in this family policy, using {effective_scheduler}."
        )
    return effective_sampler, effective_scheduler, notes


LANPAINT_KSAMPLER_ADVANCED_INPUTS = {
    'LanPaint_Lambda': ('lambda', 'lanpaint_lambda'),
    'LanPaint_StepSize': ('step_size', 'lanpaint_step_size'),
    'LanPaint_Beta': ('beta', 'lanpaint_beta'),
    'LanPaint_Friction': ('friction', 'lanpaint_friction'),
    'LanPaint_EarlyStop': ('early_stop', 'lanpaint_early_stop'),
}


def _supported_lanpaint_inputs(payload: Dict[str, Any]) -> set[str]:
    raw = payload.get('_neo_lanpaint_supported_inputs')
    if isinstance(raw, (list, tuple, set)):
        return {str(item).strip() for item in raw if str(item or '').strip()}
    if isinstance(raw, dict):
        return {str(key).strip() for key, value in raw.items() if value and str(key or '').strip()}
    return set()


def _build_lanpaint_ksampler_inputs(
    *,
    payload: Dict[str, Any],
    model_ref: Any,
    positive_ref: Any,
    negative_ref: Any,
    sampler_input: Any,
    seed: int,
    steps: int,
    cfg: float,
    sampler_name: str,
    scheduler_name: str,
    denoise: float,
) -> tuple[dict[str, Any], list[str]]:
    """Build LanPaint_KSampler inputs from the normalized LanPaint settings contract.

    Phase 4 wires the Phase 1/2 settings into the node, but only sends advanced
    controls when backend validation has exposed matching LanPaint_KSampler input
    names. This prevents hidden ComfyUI schema mutations and keeps older LanPaint
    nodes queue-safe.
    """
    inpaint_payload = get_shared_inpaint_payload(payload)
    lanpaint = (inpaint_payload.get('lanpaint') or {}) if isinstance(inpaint_payload, dict) else {}
    supported_inputs = _supported_lanpaint_inputs(payload)
    inputs: dict[str, Any] = {
        'model': list(model_ref),
        'positive': list(positive_ref),
        'negative': list(negative_ref),
        'latent_image': list(sampler_input),
        'seed': seed,
        'steps': steps,
        'cfg': cfg,
        'sampler_name': sampler_name,
        'scheduler': scheduler_name,
        'denoise': denoise,
        'LanPaint_NumSteps': int(lanpaint.get('num_steps') or payload.get('lanpaint_num_steps') or 5),
        'LanPaint_PromptMode': str(lanpaint.get('prompt_mode') or payload.get('lanpaint_prompt_mode') or 'Image First'),
        'LanPaint_Info': str(lanpaint.get('info') or payload.get('lanpaint_info') or ''),
        'Inpainting_mode': '🖼️ Image Inpainting',
    }

    wired: list[str] = ['LanPaint_NumSteps', 'LanPaint_PromptMode', 'LanPaint_Info']
    skipped: list[str] = []
    for node_key, (nested_key, flat_key) in LANPAINT_KSAMPLER_ADVANCED_INPUTS.items():
        value = lanpaint.get(nested_key) if isinstance(lanpaint, dict) else None
        if value is None:
            value = payload.get(flat_key)
        if value is None:
            continue
        if supported_inputs and node_key not in supported_inputs:
            skipped.append(node_key)
            continue
        if not supported_inputs:
            skipped.append(node_key)
            continue
        inputs[node_key] = value
        wired.append(node_key)

    transparency = dict(payload.get('_neo_lanpaint_sampler_policy') or {})
    transparency['settings_requested'] = {
        'num_steps': inputs.get('LanPaint_NumSteps'),
        'prompt_mode': inputs.get('LanPaint_PromptMode'),
        'lambda': lanpaint.get('lambda'),
        'step_size': lanpaint.get('step_size'),
        'beta': lanpaint.get('beta'),
        'friction': lanpaint.get('friction'),
        'early_stop': lanpaint.get('early_stop'),
    }
    transparency['settings_wired'] = wired
    transparency['settings_skipped'] = skipped
    payload['_neo_lanpaint_sampler_policy'] = transparency

    notes = [
        'LanPaint workflow builder wired normalized settings into LanPaint_KSampler: ' + ', '.join(wired) + '.'
    ]
    if skipped:
        notes.append('LanPaint advanced settings not sent because the live LanPaint_KSampler schema did not expose them: ' + ', '.join(skipped) + '.')
    return inputs, notes


def parse_seed(value: Any) -> int:
    text = str(value or '').strip()
    if not text or text == '-1':
        return random.randint(1, 2**63 - 1)
    try:
        parsed = int(float(text))
    except Exception:
        parsed = random.randint(1, 2**63 - 1)
    return max(1, min(parsed, 2**63 - 1))


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        parsed = default
    return max(lo, min(parsed, hi))


def _clamp_float(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(lo, min(parsed, hi))


def _merge_prompt(main_text: str, style_text: str) -> str:
    chunks = [str(main_text or '').strip(), str(style_text or '').strip()]
    return ', '.join([chunk for chunk in chunks if chunk])


def _merge_prompt_parts(*parts: Any) -> str:
    chunks = [str(part or '').strip() for part in parts]
    return ', '.join([chunk for chunk in chunks if chunk])


def _normalize_pass_target(value: Any, default: str = 'both') -> str:
    target = str(value or default).strip().lower() or default
    return target if target in {'both', 'base', 'finish'} else default


def _normalize_prompt_conditioning_mode(value: Any) -> str:
    mode = str(value or 'raw').strip().lower() or 'raw'
    return mode if mode in {'raw', 'soft_clamp', 'balanced'} else 'raw'


def _supports_clip_skip(payload: Dict[str, Any]) -> bool:
    model_source = str(payload.get('model_source') or 'checkpoint').strip().lower() or 'checkpoint'
    if model_source == 'checkpoint':
        return True
    if model_source != 'gguf':
        return False
    clip_mode = str(payload.get('gguf_clip_mode') or 'dual').strip().lower() or 'dual'
    clip_type = str(payload.get('gguf_clip_type') or 'flux').strip().lower() or 'flux'
    if clip_mode == 'single' and clip_type == 'qwen_image':
        return False
    return clip_type in {'stable_diffusion', 'sdxl', 'sd3'}


def _normalize_clip_skip(value: Any) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        parsed = 1
    return max(1, min(parsed, 4))


def _condition_prompt_text(text: Any, mode: str) -> str:
    raw = str(text or '')
    conditioning_mode = _normalize_prompt_conditioning_mode(mode)
    if not raw or conditioning_mode == 'raw':
        return raw
    if conditioning_mode == 'soft_clamp':
        min_weight, max_weight = 0.4, 1.6
    else:
        min_weight, max_weight = 0.5, 1.45

    def repl(match: re.Match[str]) -> str:
        body = ' '.join(str(match.group(1) or '').split()) if conditioning_mode == 'balanced' else str(match.group(1) or '').strip()
        try:
            weight = float(match.group(2) or 1.0)
        except Exception:
            weight = 1.0
        weight = max(min_weight, min(max_weight, weight))
        normalized = f'{weight:.2f}'.rstrip('0').rstrip('.')
        return f'({body}:{normalized})'

    conditioned = PROMPT_WEIGHT_PATTERN.sub(repl, raw)
    if conditioning_mode == 'balanced':
        conditioned = re.sub(r'\s*,\s*,+', ', ', conditioned)
        conditioned = re.sub(r'\s{2,}', ' ', conditioned)
        conditioned = conditioned.strip(' ,')
    return conditioned


def _build_pass_prompt_pair(payload: Dict[str, Any], pass_name: str = 'base') -> tuple[str, str]:
    pass_key = 'finish' if str(pass_name or '').strip().lower() == 'finish' else 'base'
    style_positive_key = 'refine_style_positive' if pass_key == 'finish' else 'style_positive'
    style_negative_key = 'refine_style_negative' if pass_key == 'finish' else 'style_negative'
    ti_positive_key = 'ti_finish_positive' if pass_key == 'finish' else 'ti_base_positive'
    ti_negative_key = 'ti_finish_negative' if pass_key == 'finish' else 'ti_base_negative'
    positive_text = _merge_prompt_parts(payload.get('positive') or '', payload.get(style_positive_key) or '', payload.get(ti_positive_key) or '')
    negative_text = _merge_prompt_parts(payload.get('negative') or '', payload.get(style_negative_key) or '', payload.get(ti_negative_key) or '')
    conditioning_mode = _normalize_prompt_conditioning_mode(payload.get('prompt_conditioning_mode'))
    return _condition_prompt_text(positive_text, conditioning_mode), _condition_prompt_text(negative_text, conditioning_mode)


def _select_lora_units_for_pass(units: list[dict[str, Any]], pass_name: str) -> list[dict[str, Any]]:
    wanted = 'finish' if str(pass_name or '').strip().lower() == 'finish' else 'base'
    filtered: list[dict[str, Any]] = []
    for unit in units or []:
        target = _normalize_pass_target(unit.get('target') if isinstance(unit, dict) else 'both', 'both')
        if target in {'both', wanted}:
            filtered.append(unit)
    return filtered


def _normalize_dynamic_thresholding_settings(payload: Dict[str, Any]) -> dict[str, Any]:
    """Read the Image tab CFG Fix / Dynamic Thresholding module from legacy or envelope payloads."""
    row: Any = None
    if isinstance(payload, dict):
        modules = payload.get('modules')
        if isinstance(modules, dict) and isinstance(modules.get('dynamic_thresholding'), dict):
            row = modules.get('dynamic_thresholding')
        elif isinstance(payload.get('dynamic_thresholding'), dict):
            row = payload.get('dynamic_thresholding')
    if not isinstance(row, dict):
        return {'enabled': False, 'preset': 'off', 'mode': 'simple'}

    preset = str(row.get('preset') or ('advanced' if row.get('enabled') else 'off')).strip().lower()
    mode = str(row.get('mode') or '').strip().lower()
    node = str(row.get('node') or '').strip()
    if not mode:
        mode = 'full' if node == 'DynamicThresholdingFull' else 'simple'
    if mode not in {'simple', 'full'}:
        mode = 'simple'

    return {
        'enabled': bool(row.get('enabled')) and preset != 'off',
        'preset': preset or 'off',
        'mode': mode,
        'node': 'DynamicThresholdingFull' if mode == 'full' else 'DynamicThresholdingSimple',
        'mimic_scale': _clamp_float(row.get('mimic_scale') or 7.0, 7.0, 0.0, 100.0),
        'threshold_percentile': _clamp_float(row.get('threshold_percentile') or 1.0, 1.0, 0.0, 1.0),
        'auto_disable_low_cfg': bool(row.get('auto_disable_low_cfg', True)),
        'auto_disable_family': bool(row.get('auto_disable_family', True)),
    }


def _sanitize_sdxl_only_modules_for_family(payload: Dict[str, Any], *, family: str, model_source: str = '', gguf_clip_type: str = '') -> list[str]:
    """Hard backend gate for SDXL-only modules.

    Frontend visibility can become stale while users switch Image-tab families. This
    sanitizer runs inside the workflow compiler so blocked modules cannot leak into
    Qwen / Flux / GGUF workflows even if stale UI state is submitted.
    """
    notes: list[str] = []
    if not isinstance(payload, dict):
        return notes

    family_key = str(family or '').strip().lower()
    model_source_key = str(model_source or payload.get('model_source') or '').strip().lower()
    gguf_clip_type_key = str(gguf_clip_type or payload.get('gguf_clip_type') or '').strip().lower()
    is_sdxl_checkpoint_family = (
        family_key in {'sdxl_sd', 'sdxl', 'sd'}
        and model_source_key != 'gguf'
        and gguf_clip_type_key != 'qwen_image'
    )

    if is_sdxl_checkpoint_family:
        return notes

    disabled_row = {
        'enabled': False,
        'preset': 'off',
        'mode': 'simple',
        'node': 'DynamicThresholdingSimple',
        'backend_blocked': True,
        'blocked_reason': f'family={family_key or "unknown"}; model_source={model_source_key or "unknown"}; gguf_clip_type={gguf_clip_type_key or "unknown"}',
    }

    existing = None
    modules = payload.get('modules')
    if isinstance(modules, dict) and isinstance(modules.get('dynamic_thresholding'), dict):
        existing = modules.get('dynamic_thresholding')
    elif isinstance(payload.get('dynamic_thresholding'), dict):
        existing = payload.get('dynamic_thresholding')

    was_enabled = bool(existing and existing.get('enabled'))
    if not isinstance(modules, dict):
        modules = {}
        payload['modules'] = modules
    modules['dynamic_thresholding'] = dict(disabled_row)
    payload['dynamic_thresholding'] = dict(disabled_row)

    if was_enabled:
        notes.append('CFG Fix / Dynamic Thresholding was blocked by backend safety gate because it is SDXL-checkpoint only.')
    return notes



def _apply_dynamic_thresholding(graph: Dict[str, Any], next_id: int, model_ref, payload: Dict[str, Any], *, family: str, model_source: str, gguf_clip_type: str, qwen_mode: bool, cfg: float, pass_label: str = 'base') -> tuple[int, Any, list[str]]:
    """Patch MODEL with mcmonkey Dynamic Thresholding right before Image tab sampler usage."""
    settings = _normalize_dynamic_thresholding_settings(payload)
    notes: list[str] = []
    if not settings.get('enabled'):
        return next_id, model_ref, notes

    family_key = str(family or '').strip().lower()
    model_source_key = str(model_source or '').strip().lower()
    # Dynamic Thresholding is exposed as an SDXL/SD quality module.
    # Do not let stale GGUF/Qwen form fields from other family panels block the SDXL checkpoint path.
    if settings.get('auto_disable_family', True) and family_key not in {'sdxl_sd', 'sdxl', 'sd'}:
        notes.append(f'Dynamic Thresholding skipped for this pass because family {family_key or "unknown"} is not SDXL/SD.')
        return next_id, model_ref, notes
    if settings.get('auto_disable_family', True) and model_source_key == 'gguf':
        notes.append('Dynamic Thresholding skipped for this pass because the active model source is GGUF.')
        return next_id, model_ref, notes

    if settings.get('auto_disable_low_cfg', True) and float(cfg or 0) <= 7.0:
        notes.append(f"Dynamic Thresholding skipped for this pass because CFG {round(float(cfg or 0), 2)} is already low.")
        return next_id, model_ref, notes

    node_class = 'DynamicThresholdingFull' if settings.get('mode') == 'full' else 'DynamicThresholdingSimple'
    inputs: dict[str, Any] = {
        'model': list(model_ref),
        'mimic_scale': float(settings.get('mimic_scale') or 7.0),
        'threshold_percentile': float(settings.get('threshold_percentile') or 1.0),
    }
    if node_class == 'DynamicThresholdingFull':
        inputs.update({
            'mimic_mode': 'Half Cosine Up',
            'mimic_scale_min': 3.5,
            'cfg_mode': 'Half Cosine Up',
            'cfg_scale_min': 3.5,
            'sched_val': 1.0,
            'separate_feature_channels': 'disable',
            'scaling_startpoint': 'MEAN',
            'variability_measure': 'AD',
            'interpolate_phi': 1.0,
        })

    node_id = next_id
    graph[str(node_id)] = {
        'class_type': node_class,
        'inputs': inputs,
    }
    notes.append(f"Dynamic Thresholding CFG Fix applied on {pass_label} pass · {node_class.replace('DynamicThresholding', '')} · mimic {inputs['mimic_scale']} · percentile {inputs['threshold_percentile']}.")
    return next_id + 1, [str(node_id), 0], notes


def _apply_lora_stack(graph: Dict[str, Any], next_id: int, model_ref, clip_ref, units: list[dict[str, Any]]):
    for unit in units or []:
        next_id, model_ref, clip_ref = _apply_optional_lora(
            graph,
            next_id,
            model_ref,
            clip_ref,
            unit.get('name') or '',
            unit.get('strength') or 0.8,
        )
    return next_id, model_ref, clip_ref


def _apply_ipadapter_stack(graph: Dict[str, Any], next_id: int, model_ref, units: list[dict[str, Any]]):
    shared_faceid_loader_ref = None
    for unit in units or []:
        next_id, model_ref, shared_faceid_loader_ref = _apply_optional_ipadapter(graph, next_id, model_ref, unit, shared_faceid_loader_ref)
    return next_id, model_ref


def _encode_prompt_pair(
    graph: Dict[str, Any],
    next_id: int,
    clip_ref,
    positive_text: str,
    negative_text: str,
    *,
    flux_mode: bool = False,
    qwen_mode: bool = False,
    guidance: float = 3.5,
    vae_ref = None,
    qwen_image_refs: list[Any] | None = None,
    qwen_target_latent_ref = None,
    qwen_images_on_negative: bool = False,
):
    positive_id = next_id
    if qwen_mode:
        positive_inputs = {
            'prompt': positive_text,
            'clip': list(clip_ref),
        }
        negative_inputs = {
            'prompt': negative_text,
            'clip': list(clip_ref),
        }
        if vae_ref is not None:
            positive_inputs['vae'] = list(vae_ref)
            negative_inputs['vae'] = list(vae_ref)
        if qwen_target_latent_ref is not None:
            positive_inputs['target_latent'] = list(qwen_target_latent_ref)
            negative_inputs['target_latent'] = list(qwen_target_latent_ref)
        for index, image_ref in enumerate((qwen_image_refs or [])[:4], start=1):
            if image_ref is None:
                continue
            positive_inputs[f'image{index}'] = list(image_ref)
            if qwen_images_on_negative:
                negative_inputs[f'image{index}'] = list(image_ref)
        graph[str(positive_id)] = {
            'class_type': 'TextEncodeQwenImageEditPlus',
            'inputs': positive_inputs,
        }
        graph[str(next_id + 1)] = {
            'class_type': 'TextEncodeQwenImageEditPlus',
            'inputs': negative_inputs,
        }
    elif flux_mode:
        graph[str(positive_id)] = {
            'class_type': 'CLIPTextEncodeFlux',
            'inputs': {
                'clip_l': positive_text,
                't5xxl': positive_text,
                'guidance': guidance,
                'clip': list(clip_ref),
            },
        }
        graph[str(next_id + 1)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': negative_text,
                'clip': list(clip_ref),
            },
        }
    else:
        graph[str(positive_id)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': positive_text,
                'clip': list(clip_ref),
            },
        }
        graph[str(next_id + 1)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': negative_text,
                'clip': list(clip_ref),
            },
        }
    return next_id + 2, [str(positive_id), 0], [str(next_id + 1), 0]


def _apply_clip_skip(graph: Dict[str, Any], next_id: int, clip_ref, clip_skip: int):
    skip = _normalize_clip_skip(clip_skip)
    if skip <= 1:
        return next_id, clip_ref
    graph[str(next_id)] = {
        'class_type': 'CLIPSetLastLayer',
        'inputs': {
            'clip': list(clip_ref),
            'stop_at_clip_layer': -skip,
        },
    }
    return next_id + 1, [str(next_id), 0]


def _apply_controlnet_stack(graph: Dict[str, Any], next_id: int, positive_ref, negative_ref, vae_ref, units: list[dict[str, Any]]):
    for unit in units or []:
        next_id, positive_ref, negative_ref = _apply_optional_controlnet(
            graph,
            next_id,
            positive_ref,
            negative_ref,
            vae_ref,
            unit.get('model') or '',
            unit.get('image_name') or '',
            unit.get('strength') or 1.0,
        )
    return next_id, positive_ref, negative_ref


def _apply_flux_sampling_patch(graph: Dict[str, Any], next_id: int, model_ref, width: int, height: int):
    graph[str(next_id)] = {
        'class_type': 'ModelSamplingFlux',
        'inputs': {
            'max_shift': 1.15,
            'base_shift': 0.5,
            'width': width,
            'height': height,
            'model': list(model_ref),
        },
    }
    return next_id + 1, [str(next_id), 0]



def _apply_qwen_sampling_patch(graph: Dict[str, Any], next_id: int, model_ref, shift: float = 3.0, cfgnorm_strength: float = 1.0):
    graph[str(next_id)] = {
        'class_type': 'ModelSamplingAuraFlow',
        'inputs': {
            'shift': round(float(shift), 4),
            'model': list(model_ref),
        },
    }
    aura_ref = [str(next_id), 0]
    graph[str(next_id + 1)] = {
        'class_type': 'CFGNorm',
        'inputs': {
            'model': list(aura_ref),
            'strength': round(float(cfgnorm_strength), 4),
        },
    }
    return next_id + 2, [str(next_id + 1), 0]


def _prepare_qwen_conditioning_images(
    graph: Dict[str, Any],
    next_id: int,
    payload: Dict[str, Any],
    mode: str,
    *,
    outpaint_left: int = 0,
    outpaint_top: int = 0,
    outpaint_right: int = 0,
    outpaint_bottom: int = 0,
    outpaint_feather: int = 24,
):
    normalized_mode = normalize_generation_mode(mode)
    if normalized_mode == 'txt2img':
        return next_id, []

    inpaint_payload = get_shared_inpaint_payload(payload)
    source_images_row = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
    composition_row = (inpaint_payload.get('composition') or {}) if isinstance(inpaint_payload, dict) else {}

    base_image_name = str(source_images_row.get('base_image_name') or payload.get('source_image_name') or '').strip()
    reference_image_2_name = str(source_images_row.get('reference_image_2_name') or payload.get('source_image__2_name') or '').strip()
    composition_image_name = str(source_images_row.get('composition_image_name') or payload.get('source_image__3_name') or '').strip()
    composition_source_mode = str(composition_row.get('source_mode') or payload.get('composition_source_mode') or 'source_image').strip().lower()
    composition_guide_type = str(composition_row.get('guide_type') or payload.get('composition_guide_type') or 'none').strip().lower()

    composition_slot_name = composition_image_name if composition_source_mode == 'composition_image' and composition_image_name else base_image_name
    source_names = [base_image_name, reference_image_2_name, composition_slot_name]
    if not any(source_names):
        raise ValueError('Qwen Image Edit needs a source image.')

    qwen_refs = []
    for index, source_image in enumerate(source_names):
        if not source_image:
            qwen_refs.append(None)
            continue
        load_id = next_id
        graph[str(load_id)] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image,
                'upload': 'image',
            },
        }
        current_ref = [str(load_id), 0]
        next_id += 1

        if index == 0 and normalized_mode == 'outpaint':
            if outpaint_left + outpaint_top + outpaint_right + outpaint_bottom <= 0:
                raise ValueError('Outpaint needs padding on at least one side.')
            pad_id = next_id
            graph[str(pad_id)] = {
                'class_type': 'ImagePadForOutpaint',
                'inputs': {
                    'image': list(current_ref),
                    'left': outpaint_left,
                    'top': outpaint_top,
                    'right': outpaint_right,
                    'bottom': outpaint_bottom,
                    'feathering': outpaint_feather,
                },
            }
            current_ref = [str(pad_id), 0]
            next_id += 1

        if index == 2 and composition_guide_type in {'depth', 'pose'}:
            if composition_guide_type == 'depth':
                guide_class = str(payload.get('composition_depth_node_class') or 'DepthAnythingV2Preprocessor').strip() or 'DepthAnythingV2Preprocessor'
                guide_id = next_id
                guide_inputs = {
                    'image': list(current_ref),
                }
                if guide_class == 'DepthAnythingV2Preprocessor':
                    guide_inputs['ckpt_name'] = str(payload.get('composition_depth_ckpt_name') or 'depth_anything_v2_vitl.pth').strip() or 'depth_anything_v2_vitl.pth'
                    guide_inputs['resolution'] = _clamp_int(payload.get('composition_depth_resolution') or 512, 512, 64, 4096)
                elif guide_class in {'DepthAnythingPreprocessor', 'MiDaSDepthMapPreprocessor', 'MiDaS-DepthMapPreprocessor', 'ZoeDepthMapPreprocessor', 'Zoe-DepthMapPreprocessor'}:
                    guide_inputs['resolution'] = _clamp_int(payload.get('composition_depth_resolution') or 512, 512, 64, 4096)
                graph[str(guide_id)] = {
                    'class_type': guide_class,
                    'inputs': guide_inputs,
                }
                current_ref = [str(guide_id), 0]
                next_id += 1
            elif composition_guide_type == 'pose':
                guide_class = str(payload.get('composition_pose_node_class') or 'DWPreprocessor').strip() or 'DWPreprocessor'
                guide_id = next_id
                guide_inputs = {
                    'image': list(current_ref),
                }
                if guide_class == 'DWPreprocessor':
                    guide_inputs.update({
                        'detect_hand': 'enable',
                        'detect_body': 'enable',
                        'detect_face': 'enable',
                        'resolution': _clamp_int(payload.get('composition_pose_resolution') or 1024, 1024, 64, 4096),
                        'bbox_detector': str(payload.get('composition_pose_bbox_detector') or 'yolox_l.onnx').strip() or 'yolox_l.onnx',
                        'pose_estimator': str(payload.get('composition_pose_estimator') or 'dw-ll_ucoco_384_bs5.torchscript.pt').strip() or 'dw-ll_ucoco_384_bs5.torchscript.pt',
                        'scale_stick_for_xinsr_cn': 'disable',
                    })
                elif guide_class == 'OpenposePreprocessor':
                    guide_inputs['resolution'] = _clamp_int(payload.get('composition_pose_resolution') or 1024, 1024, 64, 4096)
                graph[str(guide_id)] = {
                    'class_type': guide_class,
                    'inputs': guide_inputs,
                }
                current_ref = [str(guide_id), 0]
                next_id += 1

        qwen_refs.append(list(current_ref))

    return next_id, qwen_refs



def _build_qwen_sampler_input(
    graph: Dict[str, Any],
    next_id: int,
    payload: Dict[str, Any],
    mode: str,
    *,
    width: int,
    height: int,
    batch_size: int,
    vae_ref=None,
    inpaint_target: str = 'masked',
    outpaint_left: int = 0,
    outpaint_top: int = 0,
    outpaint_right: int = 0,
    outpaint_bottom: int = 0,
    outpaint_feather: int = 24,
):
    normalized_mode = normalize_generation_mode(mode)
    if normalized_mode == 'inpaint':
        inpaint_payload = get_shared_inpaint_payload(payload)
        source_images_row = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
        mask_row = (inpaint_payload.get('mask') or {}) if isinstance(inpaint_payload, dict) else {}
        output_row = (inpaint_payload.get('output') or {}) if isinstance(inpaint_payload, dict) else {}
        source_image = str(source_images_row.get('base_image_name') or payload.get('source_image_name') or '').strip()
        mask_image = str(mask_row.get('mask_image_name') or payload.get('mask_image_name') or '').strip()
        if not source_image or not mask_image:
            raise ValueError('Qwen inpaint needs both a source image and a mask image.')
        if vae_ref is None:
            raise ValueError('Qwen inpaint needs a VAE reference before building the LanPaint lane.')

        load_id = next_id
        graph[str(load_id)] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image,
                'upload': 'image',
            },
        }
        next_id += 1
        image_ref = [str(load_id), 0]

        megapixels = _clamp_float(output_row.get('megapixels') if output_row.get('megapixels') is not None else payload.get('megapixels') or 0.0, 0.0, 0.0, 16.0)
        if megapixels > 0:
            scale_id = next_id
            graph[str(scale_id)] = {
                'class_type': 'ImageScaleToTotalPixels',
                'inputs': {
                    'image': list(image_ref),
                    'upscale_method': 'lanczos',
                    'megapixels': round(megapixels, 4),
                    'resolution_steps': 1,
                },
            }
            image_ref = [str(scale_id), 0]
            next_id += 1

        size_id = next_id
        graph[str(size_id)] = {
            'class_type': 'GetImageSize',
            'inputs': {
                'image': list(image_ref),
            },
        }
        next_id += 1

        mask_id = next_id
        graph[str(mask_id)] = {
            'class_type': 'LoadImageMask',
            'inputs': {
                'image': mask_image,
                'channel': 'red',
            },
        }
        next_id += 1
        active_mask_ref = [str(mask_id), 0]

        grow_by = _clamp_int(mask_row.get('grow_mask_by') if mask_row.get('grow_mask_by') is not None else payload.get('grow_mask_by') or 6, 6, 0, 256)
        blur_by = _clamp_float(mask_row.get('blur_mask_by') if mask_row.get('blur_mask_by') is not None else payload.get('blur_mask_by') or payload.get('mask_blur') or 0.0, 0.0, 0.0, 256.0)
        if grow_by > 0 or blur_by > 0:
            grow_id = next_id
            graph[str(grow_id)] = {
                'class_type': 'GrowMaskWithBlur',
                'inputs': {
                    'mask': list(active_mask_ref),
                    'expand': grow_by,
                    'incremental_expandrate': 0,
                    'tapered_corners': True,
                    'flip_input': False,
                    'blur_radius': round(blur_by, 4),
                    'lerp_alpha': 1,
                    'decay_factor': 1,
                    'fill_holes': False,
                },
            }
            active_mask_ref = [str(grow_id), 0]
            next_id += 1

        mask_to_image_id = next_id
        graph[str(mask_to_image_id)] = {
            'class_type': 'MaskToImage',
            'inputs': {
                'mask': list(active_mask_ref),
            },
        }
        next_id += 1

        scale_mask_id = next_id
        graph[str(scale_mask_id)] = {
            'class_type': 'ImageScale',
            'inputs': {
                'image': [str(mask_to_image_id), 0],
                'upscale_method': 'nearest-exact',
                'width': [str(size_id), 0],
                'height': [str(size_id), 1],
                'crop': 'center',
            },
        }
        next_id += 1

        image_to_mask_id = next_id
        graph[str(image_to_mask_id)] = {
            'class_type': 'ImageToMask',
            'inputs': {
                'image': [str(scale_mask_id), 0],
                'channel': 'red',
            },
        }
        next_id += 1
        active_mask_ref = [str(image_to_mask_id), 0]

        if inpaint_target == 'unmasked':
            invert_id = next_id
            graph[str(invert_id)] = {
                'class_type': 'InvertMask',
                'inputs': {
                    'mask': list(active_mask_ref),
                },
            }
            active_mask_ref = [str(invert_id), 0]
            next_id += 1

        encode_id = next_id
        graph[str(encode_id)] = {
            'class_type': 'VAEEncode',
            'inputs': {
                'pixels': list(image_ref),
                'vae': list(vae_ref),
            },
        }
        next_id += 1

        noise_mask_id = next_id
        graph[str(noise_mask_id)] = {
            'class_type': 'SetLatentNoiseMask',
            'inputs': {
                'samples': [str(encode_id), 0],
                'mask': list(active_mask_ref),
            },
        }
        next_id += 1
        return next_id, [str(noise_mask_id), 0], list(image_ref)

    if normalized_mode not in {'txt2img', 'img2img'}:
        raise ValueError('Qwen Image Edit in Neo does not expose this mode in the live workspace yet.')
    latent_id = next_id
    graph[str(latent_id)] = {
        'class_type': 'EmptyLatentImage',
        'inputs': {
            'width': width,
            'height': height,
            'batch_size': batch_size,
        },
    }
    next_id += 1
    sampler_input = [str(latent_id), 0]
    return next_id, sampler_input, None


def _apply_optional_lora(graph: Dict[str, Any], next_id: int, model_ref, clip_ref, lora_name: str, strength: float):
    if not str(lora_name or '').strip():
        return next_id, model_ref, clip_ref
    graph[str(next_id)] = {
        'class_type': 'LoraLoader',
        'inputs': {
            'lora_name': str(lora_name).strip(),
            'strength_model': round(float(strength), 4),
            'strength_clip': round(float(strength), 4),
            'model': list(model_ref),
            'clip': list(clip_ref),
        },
    }
    return next_id + 1, [str(next_id), 0], [str(next_id), 1]


def _apply_optional_controlnet(graph: Dict[str, Any], next_id: int, positive_ref, negative_ref, vae_ref, controlnet_name: str, control_image_name: str, strength: float) -> Tuple[int, Any, Any]:
    if not str(controlnet_name or '').strip() or not str(control_image_name or '').strip():
        return next_id, positive_ref, negative_ref
    load_image_id = next_id
    graph[str(load_image_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': str(control_image_name).strip(),
            'upload': 'image',
        },
    }
    loader_id = next_id + 1
    graph[str(loader_id)] = {
        'class_type': 'ControlNetLoader',
        'inputs': {
            'control_net_name': str(controlnet_name).strip(),
        },
    }
    apply_id = next_id + 2
    graph[str(apply_id)] = {
        'class_type': 'ControlNetApplyAdvanced',
        'inputs': {
            'strength': round(float(strength), 4),
            'start_percent': 0,
            'end_percent': 1,
            'positive': list(positive_ref),
            'negative': list(negative_ref),
            'control_net': [str(loader_id), 0],
            'image': [str(load_image_id), 0],
            'vae': list(vae_ref),
        },
    }
    return next_id + 3, [str(apply_id), 0], [str(apply_id), 1]



def _normalize_ipadapter_image_names(unit: dict[str, Any]) -> list[str]:
    names: list[str] = []
    raw_names = unit.get('image_names')
    if isinstance(raw_names, list):
        names.extend(str(item or '').strip() for item in raw_names if str(item or '').strip())
    elif isinstance(raw_names, str) and raw_names.strip():
        names.append(raw_names.strip())
    fallback_name = str(unit.get('image_name') or '').strip()
    if fallback_name and fallback_name not in names:
        names.insert(0, fallback_name)
    return names


def _build_ipadapter_image_ref(graph: Dict[str, Any], next_id: int, image_names: list[str]):
    cleaned = [str(name or '').strip() for name in image_names if str(name or '').strip()]
    if not cleaned:
        return next_id, None
    load_id = next_id
    graph[str(load_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': cleaned[0],
            'upload': 'image',
        },
    }
    next_id += 1
    current_ref = [str(load_id), 0]
    for image_name in cleaned[1:]:
        extra_load_id = next_id
        graph[str(extra_load_id)] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': image_name,
                'upload': 'image',
            },
        }
        batch_id = next_id + 1
        graph[str(batch_id)] = {
            'class_type': 'ImageBatch',
            'inputs': {
                'image1': list(current_ref),
                'image2': [str(extra_load_id), 0],
            },
        }
        current_ref = [str(batch_id), 0]
        next_id += 2
    return next_id, current_ref



def _apply_optional_ipadapter_standard(graph: Dict[str, Any], next_id: int, model_ref, unit: dict[str, Any]):
    ipadapter_name = str(unit.get('model') or '').strip()
    clip_vision_name = str(unit.get('clip_vision') or '').strip()
    image_names = _normalize_ipadapter_image_names(unit)
    if not ipadapter_name or not clip_vision_name or not image_names:
        return next_id, model_ref
    next_id, image_ref = _build_ipadapter_image_ref(graph, next_id, image_names)
    if not image_ref:
        return next_id, model_ref
    loader_id = next_id
    graph[str(loader_id)] = {
        'class_type': 'IPAdapterModelLoader',
        'inputs': {
            'ipadapter_file': ipadapter_name,
        },
    }
    clip_loader_id = next_id + 1
    graph[str(clip_loader_id)] = {
        'class_type': 'CLIPVisionLoader',
        'inputs': {
            'clip_name': clip_vision_name,
        },
    }
    apply_id = next_id + 2
    graph[str(apply_id)] = {
        'class_type': 'IPAdapterAdvanced',
        'inputs': {
            'model': list(model_ref),
            'ipadapter': [str(loader_id), 0],
            'image': list(image_ref),
            'weight': round(float(unit.get('weight') or 1.0), 4),
            'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
            'start_at': round(float(unit.get('start_at') or 0.0), 4),
            'end_at': round(float(unit.get('end_at') or 1.0), 4),
            'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
            'clip_vision': [str(clip_loader_id), 0],
        },
    }
    return next_id + 3, [str(apply_id), 0]



def _apply_optional_ipadapter_faceid(graph: Dict[str, Any], next_id: int, model_ref, unit: dict[str, Any], shared_loader_ref=None):
    clip_vision_name = str(unit.get('clip_vision') or '').strip()
    image_name = str(unit.get('image_name') or '').strip()
    if not clip_vision_name or not image_name:
        return next_id, model_ref, shared_loader_ref

    load_image_id = next_id
    graph[str(load_image_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': image_name,
            'upload': 'image',
        },
    }
    next_id += 1

    # FaceID's unified loader injects the FaceID LoRA into the model.
    # Loading it once per IPAdapter slot stacks that LoRA repeatedly and causes identity bleed/collapse.
    # Treat faceid_lora_strength as a global Identity Preset setting and share one loader per stack.
    provider = str(unit.get('faceid_provider') or 'CUDA').strip() or 'CUDA'
    if not shared_loader_ref:
        preset = str(unit.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2'
        loader_id = next_id
        graph[str(loader_id)] = {
            'class_type': 'IPAdapterUnifiedLoaderFaceID',
            'inputs': {
                'model': list(model_ref),
                'preset': preset,
                'lora_strength': round(float(unit.get('faceid_lora_strength') or 0.75), 4),
                'provider': provider,
            },
        }
        shared_loader_ref = [str(loader_id), 1]
        model_ref = [str(loader_id), 0]
        next_id += 1

    clip_loader_id = next_id
    graph[str(clip_loader_id)] = {
        'class_type': 'CLIPVisionLoader',
        'inputs': {
            'clip_name': clip_vision_name,
        },
    }
    apply_id = next_id + 1
    graph[str(apply_id)] = {
        'class_type': 'IPAdapterFaceID',
        'inputs': {
            'model': list(model_ref),
            'ipadapter': list(shared_loader_ref),
            'image': [str(load_image_id), 0],
            'weight': round(float(unit.get('weight') or 1.0), 4),
            'weight_faceidv2': round(float(unit.get('weight_faceidv2') or unit.get('weight') or 1.0), 4),
            'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
            'start_at': round(float(unit.get('start_at') or 0.0), 4),
            'end_at': round(float(unit.get('end_at') or 1.0), 4),
            'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
            'clip_vision': [str(clip_loader_id), 0],
        },
    }
    return next_id + 2, [str(apply_id), 0], shared_loader_ref


def _apply_optional_ipadapter(graph: Dict[str, Any], next_id: int, model_ref, unit: dict[str, Any], shared_faceid_loader_ref=None):
    mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
    if mode == 'faceid':
        return _apply_optional_ipadapter_faceid(graph, next_id, model_ref, unit, shared_faceid_loader_ref)
    next_id, model_ref = _apply_optional_ipadapter_standard(graph, next_id, model_ref, unit)
    return next_id, model_ref, shared_faceid_loader_ref



def _normalize_lora_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    raw_units = payload.get('loras')
    if isinstance(raw_units, list):
        for unit in raw_units:
            if not isinstance(unit, dict):
                continue
            apply_to = str(unit.get('apply_to') or unit.get('applyTo') or 'global').strip().lower()
            if apply_to and apply_to != 'global':
                continue
            name = str(unit.get('name') or unit.get('lora_name') or '').strip()
            if not name:
                continue
            units.append({
                'name': name,
                'strength': _clamp_float(unit.get('strength') or unit.get('lora_strength') or 0.8, 0.8, -4.0, 4.0),
                'target': _normalize_pass_target(unit.get('target') or unit.get('pass_target') or 'both', 'both'),
            })
    if units:
        return units
    name = str(payload.get('lora_name') or '').strip()
    if name:
        units.append({
            'name': name,
            'strength': _clamp_float(payload.get('lora_strength') or 0.8, 0.8, -4.0, 4.0),
            'target': _normalize_pass_target(payload.get('lora_target') or 'both', 'both'),
        })
    return units


def _normalize_controlnet_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    raw_units = payload.get('controlnet_units')
    if isinstance(raw_units, list):
        for unit in raw_units:
            if not isinstance(unit, dict):
                continue
            model_name = str(unit.get('model') or unit.get('controlnet_name') or '').strip()
            if not model_name:
                continue
            units.append({
                'model': model_name,
                'image_name': str(unit.get('image_name') or unit.get('control_image_name') or '').strip(),
                'strength': _clamp_float(unit.get('strength') or unit.get('controlnet_strength') or 1.0, 1.0, 0.0, 2.0),
                'preprocessor': str(unit.get('preprocessor') or 'none').strip().lower() or 'none',
            })
    if units:
        return units
    model_name = str(payload.get('controlnet_name') or '').strip()
    if model_name:
        units.append({
            'model': model_name,
            'image_name': str(payload.get('control_image_name') or '').strip(),
            'strength': _clamp_float(payload.get('controlnet_strength') or 1.0, 1.0, 0.0, 2.0),
            'preprocessor': str(payload.get('controlnet_preprocessor') or 'none').strip().lower() or 'none',
        })
    return units




def _scene_director_suppresses_global_ipadapter(payload: Dict[str, Any]) -> bool:
    """Return True when Scene Director must own IPAdapter application.

    The request payload may still contain legacy scalar global IPAdapter fields
    because Scene Director region bindings reuse those values as their source.
    Those scalar fields must not be allowed to rebuild a global IPAdapter stack
    after the route layer has intentionally emptied ipadapter_units.
    """
    return bool(
        payload.get('scene_director_suppress_global_ipadapter')
        or payload.get('ipadapter_global_suppressed_by_scene_director')
    )


def _normalize_ipadapter_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    if _scene_director_suppresses_global_ipadapter(payload):
        return []
    units: list[dict[str, Any]] = []
    raw_units = payload.get('ipadapter_units')
    if isinstance(raw_units, list):
        for unit in raw_units:
            if not isinstance(unit, dict):
                continue
            mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
            model_name = str(unit.get('model') or unit.get('ipadapter_name') or '').strip()
            clip_vision_name = str(unit.get('clip_vision') or unit.get('clip_vision_name') or '').strip()
            if not clip_vision_name:
                continue
            if mode != 'faceid' and not model_name:
                continue
            image_names = unit.get('image_names') if isinstance(unit.get('image_names'), list) else []
            image_names = [str(item or '').strip() for item in image_names if str(item or '').strip()]
            image_name = str(unit.get('image_name') or '').strip()
            if image_name and image_name not in image_names:
                image_names.insert(0, image_name)
            units.append({
                'mode': mode,
                'model': model_name,
                'clip_vision': clip_vision_name,
                'image_name': image_name,
                'image_names': image_names,
                'weight': _clamp_float(unit.get('weight') or 1.0, 1.0, -1.0, 5.0),
                'weight_faceidv2': _clamp_float(unit.get('weight_faceidv2') or unit.get('weight') or 1.0, 1.0, -1.0, 5.0),
                'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
                'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
                'start_at': _clamp_float(unit.get('start_at') or 0.0, 0.0, 0.0, 1.0),
                'end_at': _clamp_float(unit.get('end_at') or 1.0, 1.0, 0.0, 1.0),
                'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
                'faceid_preset': str(unit.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
                'faceid_provider': str(unit.get('faceid_provider') or 'CUDA').strip() or 'CUDA',
                'faceid_lora_strength': _clamp_float(unit.get('faceid_lora_strength') or 0.75, 0.75, 0.0, 2.0),
            })
    if units:
        return units
    mode = str(payload.get('ipadapter_mode') or 'standard').strip().lower() or 'standard'
    model_name = str(payload.get('ipadapter_name') or '').strip()
    clip_vision_name = str(payload.get('ipadapter_clip_vision') or '').strip()
    if clip_vision_name and (mode == 'faceid' or model_name):
        payload_image_names = payload.get('ipadapter_image_names') if isinstance(payload.get('ipadapter_image_names'), list) else []
        payload_image_names = [str(item or '').strip() for item in payload_image_names if str(item or '').strip()]
        payload_image_name = str(payload.get('ipadapter_image_name') or '').strip()
        if payload_image_name and payload_image_name not in payload_image_names:
            payload_image_names.insert(0, payload_image_name)
        units.append({
            'mode': mode,
            'model': model_name,
            'clip_vision': clip_vision_name,
            'image_name': payload_image_name,
            'image_names': payload_image_names,
            'weight': _clamp_float(payload.get('ipadapter_weight') or 1.0, 1.0, -1.0, 5.0),
            'weight_faceidv2': _clamp_float(payload.get('ipadapter_weight_faceidv2') or payload.get('ipadapter_weight') or 1.0, 1.0, -1.0, 5.0),
            'weight_type': str(payload.get('ipadapter_weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(payload.get('ipadapter_combine_embeds') or 'concat').strip() or 'concat',
            'start_at': _clamp_float(payload.get('ipadapter_start_at') or 0.0, 0.0, 0.0, 1.0),
            'end_at': _clamp_float(payload.get('ipadapter_end_at') or 1.0, 1.0, 0.0, 1.0),
            'embeds_scaling': str(payload.get('ipadapter_embeds_scaling') or 'V only').strip() or 'V only',
            'faceid_preset': str(payload.get('ipadapter_faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
            'faceid_provider': str(payload.get('ipadapter_faceid_provider') or 'CUDA').strip() or 'CUDA',
            'faceid_lora_strength': _clamp_float(payload.get('ipadapter_faceid_lora_strength') or 0.75, 0.75, 0.0, 2.0),
        })
    return units



def _normalize_detailer_passes(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    raw_units = payload.get('detailer_passes')
    if isinstance(raw_units, list):
        for unit in raw_units:
            if not isinstance(unit, dict):
                continue
            model_name = str(unit.get('detector_model') or unit.get('model') or '').strip()
            enabled = bool(unit.get('enabled', True))
            if not enabled or not model_name:
                continue
            units.append({
                'uid': str(unit.get('uid') or '').strip(),
                'provider': str(unit.get('provider') or 'ultralytics').strip().lower() or 'ultralytics',
                'mode': str(unit.get('mode') or 'face').strip().lower() or 'face',
                'detector_type': str(unit.get('detector_type') or 'bbox').strip().lower() or 'bbox',
                'detector_model': model_name,
                'sam_model': str(unit.get('sam_model') or '').strip(),
                'custom_classes': str(unit.get('custom_classes') or '').strip(),
                'confidence': _clamp_float(unit.get('confidence') or 0.35, 0.35, 0.01, 1.0),
                'top_k': _clamp_int(unit.get('top_k') or 0, 0, 0, 50),
                'bbox_grow': _clamp_int(unit.get('bbox_grow') or 12, 12, 0, 512),
                'mask_blur': _clamp_int(unit.get('mask_blur') or 4, 4, 0, 128),
                'denoise': _clamp_float(unit.get('denoise') or 0.35, 0.35, 0.01, 1.0),
                'steps': _clamp_int(unit.get('steps') or 12, 12, 1, 150),
                'use_main_prompt': bool(unit.get('use_main_prompt', True)),
                'force_inpaint': bool(unit.get('force_inpaint', True)),
                'positive': str(unit.get('positive') or '').strip(),
                'negative': str(unit.get('negative') or '').strip(),
                'order_mode': str(unit.get('order_mode') or unit.get('order') or 'auto').strip().lower() or 'auto',
                'start_index': _clamp_int(unit.get('start_index') or 1, 1, 1, 99),
                'count': _clamp_int(unit.get('count') or 1, 1, 0, 99),
                'min_area': _clamp_int(unit.get('min_area') or 0, 0, 0, 100000000),
                'max_area': _clamp_int(unit.get('max_area') or 0, 0, 0, 100000000),
                'reference_lock': _normalize_detailer_reference_lock_mode(unit.get('reference_lock')),
                'target_mode': str(unit.get('target_mode') or 'auto_detect').strip().lower() or 'auto_detect',
                'manual_boxes': str(unit.get('manual_boxes') or '').strip(),
            })
    if units:
        return units
    detailer = payload.get('detailer')
    if isinstance(detailer, dict) and bool(detailer.get('enabled')) and str(detailer.get('detector_model') or '').strip():
        units.append({
            'uid': 'primary',
            'provider': str(detailer.get('provider') or 'ultralytics').strip().lower() or 'ultralytics',
            'mode': str(detailer.get('mode') or 'face').strip().lower() or 'face',
            'detector_type': str(detailer.get('detector_type') or 'bbox').strip().lower() or 'bbox',
            'detector_model': str(detailer.get('detector_model') or '').strip(),
            'sam_model': str(detailer.get('sam_model') or '').strip(),
            'custom_classes': str(detailer.get('custom_classes') or '').strip(),
            'confidence': _clamp_float(detailer.get('confidence') or 0.35, 0.35, 0.01, 1.0),
            'top_k': _clamp_int(detailer.get('top_k') or 0, 0, 0, 50),
            'bbox_grow': _clamp_int(detailer.get('bbox_grow') or 12, 12, 0, 512),
            'mask_blur': _clamp_int(detailer.get('mask_blur') or 4, 4, 0, 128),
            'denoise': _clamp_float(detailer.get('denoise') or 0.35, 0.35, 0.01, 1.0),
            'steps': _clamp_int(detailer.get('steps') or 12, 12, 1, 150),
            'use_main_prompt': bool(detailer.get('use_main_prompt', True)),
            'force_inpaint': bool(detailer.get('force_inpaint', True)),
            'positive': str(detailer.get('positive') or '').strip(),
            'negative': str(detailer.get('negative') or '').strip(),
            'order_mode': str(detailer.get('order_mode') or detailer.get('order') or 'auto').strip().lower() or 'auto',
            'start_index': _clamp_int(detailer.get('start_index') or 1, 1, 1, 99),
            'count': _clamp_int(detailer.get('count') or 1, 1, 0, 99),
            'min_area': _clamp_int(detailer.get('min_area') or 0, 0, 0, 100000000),
            'max_area': _clamp_int(detailer.get('max_area') or 0, 0, 0, 100000000),
            'reference_lock': _normalize_detailer_reference_lock_mode(detailer.get('reference_lock')),
            'target_mode': str(detailer.get('target_mode') or 'auto_detect').strip().lower() or 'auto_detect',
            'manual_boxes': str(detailer.get('manual_boxes') or '').strip(),
        })
    return units



def _split_detailer_sep_text(value: Any) -> list[str]:
    """Split Forge-style ADetailer [SEP] prompt text into per-target chunks.

    Empty input returns an empty list so normal single-prompt behavior is unchanged.
    Empty chunks inside a [SEP] sequence are preserved as blanks because users may
    intentionally skip a target prompt, but trailing separators are ignored. A
    trailing blank used to create an unintended extra detailer pass.
    """
    text = str(value or '')
    if '[SEP]' not in text:
        cleaned = text.strip()
        return [cleaned] if cleaned else []
    parts = [part.strip() for part in text.split('[SEP]')]
    while parts and parts[-1] == '':
        parts.pop()
    return parts


def _detailer_has_sep_prompts(unit: dict[str, Any]) -> bool:
    return '[SEP]' in str(unit.get('positive') or '') or '[SEP]' in str(unit.get('negative') or '')


def _expand_detailer_sep_units(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one ADetailer pass into one deterministic SEGS pass per [SEP] chunk.

    This mirrors Forge-style character separation while keeping Neo's target-order
    controls deterministic: target 1 receives prompt chunk 1, target 2 receives
    chunk 2, and so on. If one side has fewer chunks, its last chunk is reused.
    """
    if not _detailer_has_sep_prompts(unit):
        return [unit]

    positive_parts = _split_detailer_sep_text(unit.get('positive'))
    negative_parts = _split_detailer_sep_text(unit.get('negative'))
    total = max(len(positive_parts), len(negative_parts), 1)
    base_start = max(1, int(unit.get('start_index') or 1))
    expanded: list[dict[str, Any]] = []
    for offset in range(total):
        next_unit = dict(unit)
        next_unit['positive'] = positive_parts[min(offset, len(positive_parts) - 1)] if positive_parts else ''
        next_unit['negative'] = negative_parts[min(offset, len(negative_parts) - 1)] if negative_parts else ''
        next_unit['use_main_prompt'] = False
        next_unit['start_index'] = base_start + offset
        next_unit['count'] = 1
        next_unit['_sep_target_filter'] = True
        next_unit['_sep_target_index'] = offset + 1
        next_unit['_sep_target_total'] = total
        expanded.append(next_unit)
    return expanded

def _detailer_labels_for_unit(unit: dict[str, Any]) -> str:
    """Return the Impact Pack labels selector used by DetectorSEGS nodes.

    Recent ComfyUI Impact Pack versions require a `labels` input on
    BboxDetectorSEGS / SegmDetectorSEGS. Neo's UI can optionally pass
    custom classes; otherwise `all` keeps the previous behavior.
    """
    custom = str(unit.get('custom_classes') or '').strip()
    return custom if custom else 'all'


def _detailer_uses_segs_routing(unit: dict[str, Any]) -> bool:
    return (
        bool(unit.get('_sep_target_filter'))
        or str(unit.get('order_mode') or 'auto') != 'auto'
        or int(unit.get('start_index') or 1) != 1
        or int(unit.get('count') or 1) not in (0, 1)
        or int(unit.get('min_area') or 0) > 0
        or int(unit.get('max_area') or 0) > 0
        or str(unit.get('target_mode') or 'auto_detect') == 'manual_boxes'
        or str(unit.get('reference_lock') or 'none') != 'none'
    )


def _detailer_order_filter_config(order_mode: str) -> tuple[str, bool] | None:
    mode = str(order_mode or 'auto').strip().lower() or 'auto'
    mapping = {
        'left_to_right': ('x1', False),
        'right_to_left': ('x1', True),
        'top_to_bottom': ('y1', False),
        'bottom_to_top': ('y1', True),
        'largest_first': ('area(=w*h)', True),
        'smallest_first': ('area(=w*h)', False),
    }
    return mapping.get(mode)


def _build_detailer_detector_provider(graph: Dict[str, Any], next_id: int, unit: dict[str, Any]):
    provider = str(unit.get('provider') or 'ultralytics').strip().lower() or 'ultralytics'
    detector_model = str(unit.get('detector_model') or '').strip()
    if not detector_model:
        return next_id, None, None, None, "no detector model selected"

    if provider == 'ultralytics':
        detector_model_for_provider = detector_model if '/' in detector_model else f"{'segm' if unit.get('detector_type') == 'segm' else 'bbox'}/{detector_model}"
        detector_class_type = 'UltralyticsDetectorProvider'
    elif provider == 'onnx':
        detector_model_for_provider = detector_model
        detector_class_type = 'ONNXDetectorProvider'
    else:
        return next_id, None, None, None, f"provider '{provider}' is not wired in the workflow compiler yet"

    detector_id = next_id
    graph[str(detector_id)] = {
        'class_type': detector_class_type,
        'inputs': {
            'model_name': detector_model_for_provider,
        },
    }
    return next_id + 1, detector_id, detector_model_for_provider, provider, None


def _build_detailer_prompt_refs(graph: Dict[str, Any], next_id: int, clip_ref, unit: dict[str, Any], default_positive_ref, default_negative_ref):
    pass_positive_ref = default_positive_ref
    pass_negative_ref = default_negative_ref
    if not bool(unit.get('use_main_prompt', True)) and (str(unit.get('positive') or '').strip() or str(unit.get('negative') or '').strip()):
        pass_positive_id = next_id
        graph[str(pass_positive_id)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': str(unit.get('positive') or '').strip() or '',
                'clip': list(clip_ref),
            },
        }
        pass_negative_id = next_id + 1
        graph[str(pass_negative_id)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': str(unit.get('negative') or '').strip() or '',
                'clip': list(clip_ref),
            },
        }
        pass_positive_ref = [str(pass_positive_id), 0]
        pass_negative_ref = [str(pass_negative_id), 0]
        next_id += 2
    return next_id, pass_positive_ref, pass_negative_ref


def _parse_detailer_manual_boxes(raw_value: Any, width: int, height: int) -> list[dict[str, float]]:
    raw_text = str(raw_value or '').strip()
    if not raw_text or width <= 0 or height <= 0:
        return []

    def _parse_component(token: str, base: int) -> float:
        value = str(token or '').strip()
        if not value:
            raise ValueError('empty coordinate')
        if value.endswith('%'):
            return max(0.0, min(1.0, float(value[:-1]) / 100.0))
        return max(0.0, float(value) / float(base))

    boxes: list[dict[str, float]] = []
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        mode = 'xywh'
        lowered = cleaned.lower()
        if lowered.startswith('xyxy:'):
            mode = 'xyxy'
            cleaned = cleaned.split(':', 1)[1]
        elif lowered.startswith('xywh:'):
            cleaned = cleaned.split(':', 1)[1]
        parts = [part.strip() for part in cleaned.split(',') if part.strip()]
        if len(parts) != 4:
            continue
        try:
            if mode == 'xyxy':
                x1 = _parse_component(parts[0], width)
                y1 = _parse_component(parts[1], height)
                x2 = _parse_component(parts[2], width)
                y2 = _parse_component(parts[3], height)
                x = min(x1, x2)
                y = min(y1, y2)
                w = abs(x2 - x1)
                h = abs(y2 - y1)
            else:
                x = _parse_component(parts[0], width)
                y = _parse_component(parts[1], height)
                w = _parse_component(parts[2], width)
                h = _parse_component(parts[3], height)
            w = max(0.0, min(1.0 - x, w))
            h = max(0.0, min(1.0 - y, h))
            if w <= 0.0 or h <= 0.0:
                continue
            boxes.append({'x': round(x, 6), 'y': round(y, 6), 'w': round(w, 6), 'h': round(h, 6)})
        except Exception:
            continue
    return boxes


def _build_manual_detailer_segs(graph: Dict[str, Any], next_id: int, width: int, height: int, manual_box: dict[str, float], unit: dict[str, Any] | None = None):
    unit = unit or {}
    next_id, mask_layers, _ = _build_rect_mask_layers(graph, next_id, width, height, {**manual_box, 'falloff': 0.0})
    mask_ref = list(mask_layers[0][0]) if mask_layers else None
    if not mask_ref:
        return next_id, None
    mask_to_segs_id = next_id
    graph[str(mask_to_segs_id)] = {
        'class_type': 'MaskToSEGS',
        'inputs': {
            'mask': list(mask_ref),
            'combined': False,
            'crop_factor': 1.12,
            'bbox_fill': False,
            'drop_size': 1,
            'contour_fill': False,
        },
    }
    segs_ref = [str(mask_to_segs_id), 0]
    next_id += 1

    dilation = max(0, int(unit.get('bbox_grow') or 0))
    if dilation > 0:
        dilate_id = next_id
        graph[str(dilate_id)] = {
            'class_type': 'ImpactDilateMaskInSEGS',
            'inputs': {
                'segs': list(segs_ref),
                'dilation': dilation,
            },
        }
        segs_ref = [str(dilate_id), 0]
        next_id += 1

    blur_value = max(0, int(unit.get('mask_blur') or 0))
    if blur_value > 0:
        kernel_size = max(3, blur_value * 2 + 1)
        if kernel_size % 2 == 0:
            kernel_size += 1
        blur_id = next_id
        graph[str(blur_id)] = {
            'class_type': 'ImpactGaussianBlurMaskInSEGS',
            'inputs': {
                'segs': list(segs_ref),
                'kernel_size': kernel_size,
                'sigma': max(1.0, round(blur_value / 2.0, 2)),
            },
        }
        segs_ref = [str(blur_id), 0]
        next_id += 1
    return next_id, segs_ref



def _normalize_detailer_reference_lock_mode(reference_lock: Any) -> str:
    raw = str(reference_lock or 'none').strip().lower().replace('-', '_') or 'none'
    aliases = {
        'off': 'none',
        'no': 'none',
        'disabled': 'none',
        'identity': 'soft_identity',
        'soft': 'soft_identity',
        'soft_faceid': 'soft_identity',
        'strong': 'strong_identity',
        'strong_faceid': 'strong_identity',
        'face': 'face_only',
        'faceid': 'face_only',
        'style': 'style_only',
        'ip_adapter': 'ipadapter',
        'ip_adapter_faceid': 'ipadapter',
    }
    raw = aliases.get(raw, raw)
    allowed = {'none', 'soft_identity', 'strong_identity', 'face_only', 'style_only', 'controlnet', 'ipadapter', 'both'}
    return raw if raw in allowed else 'none'


def _detailer_reference_lock_label(reference_lock: Any) -> str:
    mode = _normalize_detailer_reference_lock_mode(reference_lock)
    labels = {
        'none': 'off',
        'soft_identity': 'soft identity',
        'strong_identity': 'strong identity',
        'face_only': 'face only',
        'style_only': 'style only',
        'controlnet': 'controlnet',
        'ipadapter': 'legacy ipadapter',
        'both': 'legacy both',
    }
    return labels.get(mode, mode.replace('_', ' '))


def _detailer_reference_lock_needs_ipadapter(reference_lock: str) -> bool:
    mode = _normalize_detailer_reference_lock_mode(reference_lock)
    return mode in {'soft_identity', 'strong_identity', 'face_only', 'style_only', 'ipadapter', 'both'}


def _detailer_reference_lock_needs_controlnet(reference_lock: str) -> bool:
    mode = _normalize_detailer_reference_lock_mode(reference_lock)
    return mode in {'controlnet', 'both'}

def _apply_detailer_reference_lock_model(graph: Dict[str, Any], next_id: int, model_ref, payload: Dict[str, Any], reference_lock: str):
    """Resolve ADetailer reference-lock intent without injecting brittle optional nodes.

    The main graph may already have IP-Adapter / FaceID conditioning baked into
    model_ref. This function keeps the detail pass safe by reusing that model_ref
    and producing explicit readiness notes for the report/status panel instead of
    blindly adding nodes that may be missing in the user's ComfyUI install.
    """
    notes: list[str] = []
    detailer_model_ref = model_ref
    mode = _normalize_detailer_reference_lock_mode(reference_lock)
    if not _detailer_reference_lock_needs_ipadapter(mode):
        return next_id, detailer_model_ref, notes

    ipadapter_units = _normalize_ipadapter_units(payload)
    faceid_unit = next((item for item in ipadapter_units if item.get('clip_vision') and _normalize_ipadapter_image_names(item) and str(item.get('mode') or 'standard').strip().lower() == 'faceid'), None)
    standard_unit = next((item for item in ipadapter_units if item.get('clip_vision') and _normalize_ipadapter_image_names(item) and item.get('model')), None)

    if mode in {'strong_identity', 'face_only'}:
        if faceid_unit:
            notes.append(f'{_detailer_reference_lock_label(mode)} lock ready: reusing the main FaceID-conditioned model for the detail pass')
        elif standard_unit:
            notes.append(f'{_detailer_reference_lock_label(mode)} lock requested but no FaceID unit was found; falling back to the available IP-Adapter reference')
        else:
            notes.append(f'{_detailer_reference_lock_label(mode)} lock requested but no eligible FaceID/IP-Adapter reference unit was configured')
    elif mode == 'soft_identity':
        if faceid_unit:
            notes.append('soft identity lock ready: reusing the main FaceID-conditioned model with gentle identity intent')
        elif standard_unit:
            notes.append('soft identity lock ready: reusing the main IP-Adapter reference because no FaceID unit was found')
        else:
            notes.append('soft identity lock requested but no eligible FaceID/IP-Adapter reference unit was configured')
    elif mode == 'style_only':
        if standard_unit:
            notes.append('style-only lock ready: reusing the main IP-Adapter reference for color/lighting/texture guidance')
        elif faceid_unit:
            notes.append('style-only lock requested but only FaceID was configured; using available FaceID-conditioned model cautiously')
        else:
            notes.append('style-only lock requested but no eligible IP-Adapter reference unit was configured')
    elif mode in {'ipadapter', 'both'}:
        ip_unit = faceid_unit or standard_unit
        if ip_unit:
            unit_mode = str(ip_unit.get('mode') or 'standard').strip().lower() or 'standard'
            notes.append('legacy ipadapter lock ready: reusing the main faceid-conditioned model for the detail pass' if unit_mode == 'faceid' else 'legacy ipadapter lock ready: reusing the main ipadapter-conditioned model for the detail pass')
        else:
            notes.append('legacy ipadapter lock requested but no eligible IP-Adapter / FaceID unit was available')
    return next_id, detailer_model_ref, notes



def _resolve_detailer_cfg(payload: Dict[str, Any], unit: dict[str, Any], inherited_cfg: float) -> tuple[float, str]:
    """Return the effective CFG for ADetailer/Selective Repair passes.

    Detailer passes are local repair workflows; inheriting very high txt2img CFG
    can overcook faces and small regions. Keep the raw main CFG untouched and
    expose the effective repair CFG through metadata/compile notes.
    """
    raw_value = unit.get('cfg') if unit.get('cfg') not in (None, '') else payload.get('detailer_cfg')
    if raw_value in (None, ''):
        raw_value = payload.get('adetailer_cfg')
    explicit = raw_value not in (None, '')
    requested = _clamp_float(raw_value if explicit else inherited_cfg, inherited_cfg, 1.0, 30.0)
    cap = _clamp_float(payload.get('detailer_cfg_cap') or payload.get('adetailer_cfg_cap') or 8.0, 8.0, 1.0, 30.0)
    allow_high = bool(payload.get('detailer_allow_high_cfg') or payload.get('adetailer_allow_high_cfg'))
    effective = requested if allow_high else min(requested, cap)
    policy = {
        'requested_cfg': requested,
        'effective_cfg': effective,
        'cap': cap,
        'explicit': explicit,
        'allow_high_cfg': allow_high,
    }
    payload['_neo_detailer_cfg_policy'] = policy
    if effective != requested:
        return effective, f'Detailer CFG capped {requested:g} → {effective:g} for local repair stability.'
    return effective, f'Detailer CFG effective {effective:g}.'

def _apply_detailer_segs_pass(graph: Dict[str, Any], next_id: int, current_image_ref, model_ref, clip_ref, vae_ref, payload: Dict[str, Any], unit: dict[str, Any], seed: int, cfg: float, sampler_name: str, scheduler_name: str, pass_positive_ref, pass_negative_ref, detector_id: int | None, provider: str | None):
    detector_type = str(unit.get('detector_type') or 'bbox').strip().lower() or 'bbox'
    threshold = _clamp_float(unit.get('confidence') or 0.35, 0.35, 0.01, 1.0)
    dilation = _clamp_int(unit.get('bbox_grow') or 12, 12, -512, 512)
    crop_factor = 2.0
    drop_size = 10
    width = _clamp_int(payload.get('width') or 1024, 1024, 256, 4096)
    height = _clamp_int(payload.get('height') or 1024, 1024, 256, 4096)
    manual_box = unit.get('manual_box') if isinstance(unit.get('manual_box'), dict) else None
    labels = _detailer_labels_for_unit(unit)

    if manual_box is not None:
        next_id, segs_ref = _build_manual_detailer_segs(graph, next_id, width, height, manual_box, unit)
        if segs_ref is None:
            return next_id, current_image_ref, ['manual box could not be converted into a SEGS target']
    else:
        if detector_type == 'segm' and provider == 'ultralytics':
            detector_segs_id = next_id
            graph[str(detector_segs_id)] = {
                'class_type': 'SegmDetectorSEGS',
                'inputs': {
                    'segm_detector': [str(detector_id), 1],
                    'image': list(current_image_ref),
                    'threshold': threshold,
                    'dilation': dilation,
                    'crop_factor': crop_factor,
                    'drop_size': drop_size,
                    'labels': labels,
                },
            }
        else:
            detector_segs_id = next_id
            graph[str(detector_segs_id)] = {
                'class_type': 'BboxDetectorSEGS',
                'inputs': {
                    'bbox_detector': [str(detector_id), 0],
                    'image': list(current_image_ref),
                    'threshold': threshold,
                    'dilation': dilation,
                    'crop_factor': crop_factor,
                    'drop_size': drop_size,
                    'labels': labels,
                },
            }
        segs_ref = [str(detector_segs_id), 0]
        next_id += 1

    order_config = _detailer_order_filter_config(str(unit.get('order_mode') or 'auto'))
    if bool(unit.get('_sep_target_filter')) or order_config is not None or int(unit.get('start_index') or 1) != 1 or int(unit.get('count') or 1) not in (0, 1):
        target, descending = order_config or ('none', True)
        ordered_filter_id = next_id
        graph[str(ordered_filter_id)] = {
            'class_type': 'ImpactSEGSOrderedFilter',
            'inputs': {
                'segs': list(segs_ref),
                'target': target,
                'order': bool(descending),
                'take_start': max(0, int(unit.get('start_index') or 1) - 1),
                'take_count': int(unit.get('count') or 0) if int(unit.get('count') or 0) > 0 else 9999,
            },
        }
        segs_ref = [str(ordered_filter_id), 0]
        next_id += 1

    min_area = int(unit.get('min_area') or 0)
    max_area = int(unit.get('max_area') or 0)
    if min_area > 0 or max_area > 0:
        range_filter_id = next_id
        graph[str(range_filter_id)] = {
            'class_type': 'ImpactSEGSRangeFilter',
            'inputs': {
                'segs': list(segs_ref),
                'target': 'area(=w*h)',
                'mode': True,
                'min_value': max(0, min_area),
                'max_value': max_area if max_area > 0 else 67108864,
            },
        }
        segs_ref = [str(range_filter_id), 0]
        next_id += 1

    controlnet_units = _normalize_controlnet_units(payload)
    reference_lock = _normalize_detailer_reference_lock_mode(unit.get('reference_lock'))
    reference_notes: list[str] = []
    if _detailer_reference_lock_needs_controlnet(reference_lock):
        if controlnet_units:
            reference_notes.append('reusing the main controlnet-conditioned prompts for the detail pass')
        else:
            reference_notes.append('controlnet-lock requested but no ControlNet units are configured')

    next_id, detailer_model_ref, ipadapter_reference_notes = _apply_detailer_reference_lock_model(graph, next_id, model_ref, payload, reference_lock)
    reference_notes.extend(ipadapter_reference_notes)

    basic_pipe_id = next_id
    graph[str(basic_pipe_id)] = {
        'class_type': 'ToBasicPipe',
        'inputs': {
            'model': list(detailer_model_ref),
            'clip': list(clip_ref),
            'vae': list(vae_ref),
            'positive': list(pass_positive_ref),
            'negative': list(pass_negative_ref),
        },
    }
    segs_detailer_id = next_id + 1
    graph[str(segs_detailer_id)] = {
        'class_type': 'SEGSDetailer',
        'inputs': {
            'image': list(current_image_ref),
            'segs': list(segs_ref),
            'guide_size': 512.0,
            'guide_size_for': True,
            'max_size': float(max(width, height, 1024)),
            'seed': max(1, seed),
            'steps': _clamp_int(unit.get('steps') or 12, 12, 1, 150),
            'cfg': cfg,
            'sampler_name': sampler_name,
            'scheduler': scheduler_name,
            'denoise': _clamp_float(unit.get('denoise') or 0.35, 0.35, 0.01, 1.0),
            'noise_mask': True,
            'force_inpaint': bool(unit.get('force_inpaint', True)),
            'basic_pipe': [str(basic_pipe_id), 0],
            'refiner_ratio': 0.2,
            'batch_size': 1,
            'cycle': 1,
            'inpaint_model': False,
            'noise_mask_feather': _clamp_int(unit.get('mask_blur') or 4, 4, 0, 128),
        },
    }
    paste_id = next_id + 2
    graph[str(paste_id)] = {
        'class_type': 'SEGSPaste',
        'inputs': {
            'image': list(current_image_ref),
            'segs': [str(segs_detailer_id), 0],
            'feather': _clamp_int(unit.get('mask_blur') or 4, 4, 0, 128),
            'alpha': 255,
        },
    }
    return next_id + 3, [str(paste_id), 0], reference_notes


def _apply_optional_detailers(graph: Dict[str, Any], next_id: int, image_ref, model_ref, clip_ref, vae_ref, payload: Dict[str, Any], seed: int, cfg: float, sampler_name: str, scheduler_name: str, default_positive_ref, default_negative_ref) -> Tuple[int, Any, list[str]]:
    units = _normalize_detailer_passes(payload)
    if not units:
        return next_id, image_ref, []

    notes: list[str] = ['Experimental Impact Pack detailer graph enabled.']
    current_image_ref = image_ref
    width = _clamp_int(payload.get('width') or 1024, 1024, 256, 4096)
    height = _clamp_int(payload.get('height') or 1024, 1024, 256, 4096)
    for index, unit in enumerate(units, start=1):
        manual_boxes = _parse_detailer_manual_boxes(unit.get('manual_boxes'), width, height) if str(unit.get('target_mode') or 'auto_detect') == 'manual_boxes' else []
        base_run_units = [{**unit, 'manual_box': box} for box in manual_boxes] if manual_boxes else [unit]
        run_units: list[dict[str, Any]] = []
        for base_run_unit in base_run_units:
            run_units.extend(_expand_detailer_sep_units(base_run_unit))
        if str(unit.get('target_mode') or 'auto_detect') == 'manual_boxes' and not manual_boxes:
            notes.append(f'Detailer pass {index} skipped: manual boxes mode was enabled but no valid boxes were provided.')
            continue
        if _detailer_has_sep_prompts(unit):
            notes.append(f'Detailer pass {index} expanded [SEP] prompts into {len(run_units)} ordered target pass(es).')

        for box_index, run_unit in enumerate(run_units, start=1):
            detector_id = None
            detector_model_for_provider = 'manual boxes'
            provider = None
            if run_unit.get('manual_box') is None:
                next_id, detector_id, detector_model_for_provider, provider, detector_error = _build_detailer_detector_provider(graph, next_id, run_unit)
                if detector_error:
                    notes.append(f'Detailer pass {index} skipped: {detector_error}.')
                    break

            next_id, pass_positive_ref, pass_negative_ref = _build_detailer_prompt_refs(
                graph,
                next_id,
                clip_ref,
                run_unit,
                default_positive_ref,
                default_negative_ref,
            )

            pass_seed = max(1, seed + index + box_index - 1)
            pass_label = f'Detailer pass {index}' if len(run_units) == 1 else f'Detailer pass {index}.{box_index}'
            pass_cfg, cfg_note = _resolve_detailer_cfg(payload, run_unit, cfg)
            if cfg_note:
                notes.append(f'{pass_label}: {cfg_note}')

            if _detailer_uses_segs_routing(run_unit):
                next_id, current_image_ref, reference_notes = _apply_detailer_segs_pass(
                    graph,
                    next_id,
                    current_image_ref,
                    model_ref,
                    clip_ref,
                    vae_ref,
                    payload,
                    run_unit,
                    pass_seed,
                    pass_cfg,
                    sampler_name,
                    scheduler_name,
                    pass_positive_ref,
                    pass_negative_ref,
                    detector_id,
                    provider,
                )
                if run_unit.get('manual_box') is not None:
                    notes.append(f'{pass_label} queued with manual target boxes via SEGS routing.')
                else:
                    notes.append(f"{pass_label} queued with SEGS routing using {detector_model_for_provider} ({run_unit.get('mode') or 'face'} / {run_unit.get('detector_type') or 'bbox'}).")
                if run_unit.get('_sep_target_filter'):
                    notes.append(f"{pass_label} applies [SEP] chunk {run_unit.get('_sep_target_index')} of {run_unit.get('_sep_target_total')} to ordered target #{run_unit.get('start_index')}.")
                notes.append(f'{pass_label} now applies manual/order/count/area target filters before paste-back.')
                for reference_note in reference_notes:
                    notes.append(f'{pass_label}: {reference_note}.')
                continue

            sam_ref = None
            sam_model_name = str(run_unit.get('sam_model') or '').strip()
            if sam_model_name:
                sam_loader_id = next_id
                graph[str(sam_loader_id)] = {
                    'class_type': 'SAMLoader',
                    'inputs': {
                        'model_name': sam_model_name,
                        'device_mode': 'AUTO',
                    },
                }
                sam_ref = [str(sam_loader_id), 0]
                next_id += 1

            face_detailer_inputs = {
                'image': list(current_image_ref),
                'model': list(model_ref),
                'clip': list(clip_ref),
                'vae': list(vae_ref),
                'guide_size': 512.0,
                'guide_size_for': True,
                'max_size': float(max(width, height, 1024)),
                'seed': pass_seed,
                'steps': _clamp_int(run_unit.get('steps') or 12, 12, 1, 150),
                'cfg': pass_cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler_name,
                'positive': list(pass_positive_ref),
                'negative': list(pass_negative_ref),
                'denoise': _clamp_float(run_unit.get('denoise') or 0.35, 0.35, 0.01, 1.0),
                'feather': _clamp_int(run_unit.get('mask_blur') or 4, 4, 0, 128),
                'noise_mask': True,
                'force_inpaint': bool(run_unit.get('force_inpaint', True)),
                'bbox_threshold': _clamp_float(run_unit.get('confidence') or 0.35, 0.35, 0.01, 1.0),
                'bbox_dilation': _clamp_int(run_unit.get('bbox_grow') or 12, 12, 0, 512),
                'bbox_crop_factor': 2.0,
                'sam_detection_hint': 'center-1',
                'sam_dilation': _clamp_int(run_unit.get('bbox_grow') or 12, 12, 0, 512),
                'sam_threshold': 0.88,
                'sam_bbox_expansion': _clamp_int(run_unit.get('bbox_grow') or 12, 12, 0, 512),
                'sam_mask_hint_threshold': 0.70,
                'sam_mask_hint_use_negative': 'False',
                'drop_size': 10,
                'bbox_detector': [str(detector_id), 0],
                'wildcard': '',
                'cycle': 1,
                'inpaint_model': False,
                'noise_mask_feather': _clamp_int(run_unit.get('mask_blur') or 4, 4, 0, 128),
            }
            if provider == 'ultralytics' and run_unit.get('detector_type') == 'segm':
                face_detailer_inputs['segm_detector_opt'] = [str(detector_id), 1]
            if sam_ref is not None:
                face_detailer_inputs['sam_model_opt'] = list(sam_ref)

            detailer_id = next_id
            graph[str(detailer_id)] = {
                'class_type': 'FaceDetailer',
                'inputs': face_detailer_inputs,
            }
            current_image_ref = [str(detailer_id), 0]
            next_id += 1
            notes.append(f"{pass_label} queued with {detector_model_for_provider} ({run_unit.get('mode') or 'face'} / {run_unit.get('detector_type') or 'bbox'}).")
            if _normalize_detailer_reference_lock_mode(run_unit.get('reference_lock')) != 'none':
                notes.append(f'{pass_label}: {_detailer_reference_lock_label(run_unit.get("reference_lock"))} reference lock remains staged on the legacy FaceDetailer path; use non-auto target order/manual boxes for full SEGS reference-lock reporting.')

    return next_id, current_image_ref, notes

def _normalize_refine_resize_method(method: Any, refine_mode: str, refine_strategy: str = 'standard', qwen_mode: bool = False) -> str:
    raw = str(method or '').strip().lower()
    image_allowed = {'nearest-exact', 'bilinear', 'area', 'bicubic', 'lanczos'}
    latent_allowed = {'nearest-exact', 'bilinear', 'area', 'bicubic', 'bislerp'}
    # Qwen re-edit uses ImageScaleBy on decoded images before re-encoding.
    # ImageScaleBy in the user's Comfy build does not accept bislerp, so force image-safe methods.
    if qwen_mode and refine_strategy == 'qwen_reedit':
        return raw if raw in image_allowed else 'lanczos'
    if refine_mode == 'image_upscale':
        return raw if raw in image_allowed else 'lanczos'
    if raw == 'lanczos':
        return 'bislerp'
    return raw if raw in latent_allowed else 'bislerp'


def _maybe_refine(graph: Dict[str, Any], next_id: int, latent_ref, model_ref, positive_ref, negative_ref, payload: Dict[str, Any], seed: int, vae_ref, clip_ref=None, positive_text: str='', negative_text: str='', qwen_mode: bool=False, guidance: float=3.5):
    if not bool(payload.get('refine_enabled')):
        return next_id, latent_ref
    scale_by = _clamp_float(payload.get('refine_scale') or 1.5, 1.5, 1.1, 4.0)
    refine_steps = _clamp_int(payload.get('refine_steps') or max(8, int(_clamp_int(payload.get('steps') or 28, 28, 1, 150) * 0.45)), 12, 4, 80)
    refine_mode = str(payload.get('refine_mode') or 'latent').strip().lower()
    refine_strategy = str(payload.get('refine_strategy') or 'standard').strip().lower() or 'standard'
    refine_denoise_default = 0.18 if refine_mode == 'image_upscale' else 0.12
    refine_denoise = _clamp_float(payload.get('refine_denoise') or refine_denoise_default, refine_denoise_default, 0.05, 0.95)
    refine_resize_method = _normalize_refine_resize_method(payload.get('refine_resize_method') or 'lanczos', refine_mode, refine_strategy, qwen_mode)
    upscale_model_name = str(payload.get('refine_upscaler') or '').strip()
    refine_cfg_default = 4.8 if refine_mode == 'image_upscale' else 5.2
    refine_cfg = _clamp_float(payload.get('refine_cfg') or payload.get('cfg') or refine_cfg_default, refine_cfg_default, 1.0, 30.0)
    refine_sampler = normalize_sampler_name(payload.get('refine_sampler') or payload.get('sampler') or 'euler')
    refine_scheduler = normalize_scheduler_name(payload.get('refine_scheduler') or payload.get('scheduler') or 'normal')
    use_tiled_vae = bool(payload.get('refine_tiled_vae', True))
    tile_size = _clamp_int(payload.get('refine_tile_size') or 512, 512, 64, 4096)
    tile_overlap = _clamp_int(payload.get('refine_tile_overlap') or 64, 64, 0, 1024)

    def _build_ultimate_sd_upscale_inputs(base_image_ref, positive_conditioning_ref):
        input_keys = list(payload.get('_neo_ultimate_input_keys') or []) if isinstance(payload.get('_neo_ultimate_input_keys'), list) else []
        keyset = {str(k) for k in input_keys if isinstance(k, str) and str(k).strip()}
        if not keyset:
            return None

        ultimate_inputs: Dict[str, Any] = {
            'image': list(base_image_ref),
            'model': list(model_ref),
            'positive': list(positive_conditioning_ref),
            'negative': list(negative_ref),
            'vae': list(vae_ref),
        }
        if upscale_model_name:
            ultimate_inputs['upscale_model'] = [str(payload.get('_neo_refine_upscale_loader_id') or ''), 0]

        scalar_map = {
            'upscale_by': scale_by,
            'seed': max(1, seed),
            'steps': refine_steps,
            'cfg': refine_cfg,
            'sampler_name': refine_sampler,
            'scheduler': refine_scheduler,
            'denoise': refine_denoise,
            'mode_type': 'Linear',
            'tile_width': tile_size,
            'tile_height': tile_size,
            'mask_blur': 8,
            'tile_padding': max(16, min(tile_overlap, 128)),
            'seam_fix_mode': 'None',
            'seam_fix_denoise': 1.0,
            'seam_fix_width': max(32, tile_overlap),
            'seam_fix_mask_blur': 8,
            'seam_fix_padding': max(16, min(tile_overlap // 2 if tile_overlap > 0 else 16, 64)),
            'force_uniform_tiles': True,
            'tiled_decode': False,
            'seed_mode': 'randomize',
            'control_after_generate': 'randomize',
            'batch_size': 1,
        }
        alias_map = {
            'sampler': 'sampler_name',
            'tile_w': 'tile_width',
            'tile_h': 'tile_height',
            'upscale_model_opt': 'upscale_model',
            'upscale_model_optional': 'upscale_model',
            'seed_num': 'seed',
        }
        for key, alias in alias_map.items():
            if key in keyset and alias in ultimate_inputs:
                ultimate_inputs[key] = ultimate_inputs[alias]
            elif key in keyset and alias in scalar_map:
                ultimate_inputs[key] = scalar_map[alias]

        for key, value in scalar_map.items():
            if key in keyset:
                ultimate_inputs[key] = value

        required_core = {'image', 'model', 'positive', 'negative', 'vae'}
        if not required_core.issubset(set(ultimate_inputs.keys()) | keyset):
            return None
        return ultimate_inputs

    def _build_ultimate_preserve_refine(current_next_id: int, current_latent_ref):
        if not bool(payload.get('_neo_refine_use_ultimate_upscale')):
            return None
        if not upscale_model_name:
            return None

        source_only_image = bool(payload.get('upscale_lab_source_only')) and refine_mode == 'image_upscale' and not qwen_mode
        if source_only_image:
            source_image_name = str(payload.get('source_image_name') or '').strip()
            if not source_image_name:
                return None
            load_id = current_next_id
            graph[str(load_id)] = {
                'class_type': 'LoadImage',
                'inputs': {
                    'image': source_image_name,
                    'upload': 'image',
                },
            }
            current_image_ref = [str(load_id), 0]
            current_next_id += 1
        else:
            decode_id = current_next_id
            graph[str(decode_id)] = {
                'class_type': 'VAEDecode',
                'inputs': {
                    'samples': list(current_latent_ref),
                    'vae': list(vae_ref),
                },
            }
            current_image_ref = [str(decode_id), 0]
            current_next_id += 1

        tile_controlnet_model = str(payload.get('_neo_refine_tile_controlnet_model') or '').strip()
        positive_for_upscale_ref = list(positive_ref)
        if tile_controlnet_model:
            controlnet_loader_id = current_next_id
            graph[str(controlnet_loader_id)] = {
                'class_type': 'ControlNetLoader',
                'inputs': {
                    'control_net_name': tile_controlnet_model,
                },
            }
            current_next_id += 1
            apply_id = current_next_id
            graph[str(apply_id)] = {
                'class_type': 'ControlNetApply',
                'inputs': {
                    'conditioning': list(positive_ref),
                    'control_net': [str(controlnet_loader_id), 0],
                    'image': list(current_image_ref),
                    'strength': 1.0,
                },
            }
            positive_for_upscale_ref = [str(apply_id), 0]
            current_next_id += 1

        if upscale_model_name:
            loader_id = current_next_id
            graph[str(loader_id)] = {
                'class_type': 'UpscaleModelLoader',
                'inputs': {'model_name': upscale_model_name},
            }
            payload['_neo_refine_upscale_loader_id'] = str(loader_id)
            current_next_id += 1

        ultimate_inputs = _build_ultimate_sd_upscale_inputs(current_image_ref, positive_for_upscale_ref)
        loader_ref = str(payload.get('_neo_refine_upscale_loader_id') or '')
        if loader_ref and '_neo_refine_upscale_loader_id' in payload:
            try:
                del payload['_neo_refine_upscale_loader_id']
            except Exception:
                pass
        if not ultimate_inputs:
            return None

        ultimate_id = current_next_id
        graph[str(ultimate_id)] = {
            'class_type': 'UltimateSDUpscale',
            'inputs': ultimate_inputs,
        }
        current_next_id += 1

        # Preserve-first Ultimate SD Upscale already returns the final IMAGE.
        # Re-encoding that image back into latent space and decoding it again
        # introduces avoidable drift versus the native Comfy graph the user
        # validated manually. Store the direct final image ref so the outer
        # workflow can skip the extra encode/decode round-trip.
        payload['_neo_refine_direct_image_ref'] = [str(ultimate_id), 0]
        payload['_neo_refine_direct_image_mode'] = 'ultimate_sd_upscale'
        return current_next_id, (list(current_latent_ref) if current_latent_ref is not None else None)

    if qwen_mode and refine_strategy == 'qwen_reedit':
        decode_id = next_id
        graph[str(decode_id)] = {
            'class_type': 'VAEDecode',
            'inputs': {
                'samples': list(latent_ref),
                'vae': list(vae_ref),
            },
        }
        current_image_ref = [str(decode_id), 0]
        next_id += 1
        if upscale_model_name:
            loader_id = next_id
            graph[str(loader_id)] = {
                'class_type': 'UpscaleModelLoader',
                'inputs': {'model_name': upscale_model_name},
            }
            upscale_id = next_id + 1
            graph[str(upscale_id)] = {
                'class_type': 'ImageUpscaleWithModel',
                'inputs': {
                    'upscale_model': [str(loader_id), 0],
                    'image': list(current_image_ref),
                },
            }
            current_image_ref = [str(upscale_id), 0]
            next_id += 2
            native_scale = _infer_upscale_model_native_scale(upscale_model_name)
            extra_scale = scale_by / native_scale if native_scale > 0 else scale_by
            if abs(extra_scale - 1.0) > 0.01:
                rescale_id = next_id
                graph[str(rescale_id)] = {
                    'class_type': 'ImageScaleBy',
                    'inputs': {
                        'image': list(current_image_ref),
                        'upscale_method': refine_resize_method,
                        'scale_by': max(0.05, min(extra_scale, 8.0)),
                    },
                }
                current_image_ref = [str(rescale_id), 0]
                next_id += 1
        else:
            scale_id = next_id
            graph[str(scale_id)] = {
                'class_type': 'ImageScaleBy',
                'inputs': {
                    'image': list(current_image_ref),
                    'upscale_method': refine_resize_method,
                    'scale_by': scale_by,
                },
            }
            current_image_ref = [str(scale_id), 0]
            next_id += 1
        encode_id = next_id
        graph[str(encode_id)] = {
            'class_type': 'VAEEncode',
            'inputs': {
                'pixels': list(current_image_ref),
                'vae': list(vae_ref),
            },
        }
        next_id += 1
        qwen_refs = [list(current_image_ref)]
        next_id, refine_positive_ref, refine_negative_ref = _encode_prompt_pair(
            graph,
            next_id,
            clip_ref,
            positive_text,
            negative_text,
            flux_mode=False,
            qwen_mode=True,
            guidance=guidance,
            vae_ref=vae_ref,
            qwen_image_refs=qwen_refs,
            qwen_images_on_negative=True,
        )
        sampler_id = next_id
        graph[str(sampler_id)] = {
            'class_type': 'KSampler',
            'inputs': {
                'seed': max(1, seed),
                'steps': refine_steps,
                'cfg': refine_cfg,
                'sampler_name': refine_sampler,
                'scheduler': refine_scheduler,
                'denoise': refine_denoise,
                'model': list(model_ref),
                'positive': list(refine_positive_ref),
                'negative': list(refine_negative_ref),
                'latent_image': [str(encode_id), 0],
            },
        }
        return next_id + 1, [str(sampler_id), 0]

    if refine_mode == 'image_upscale':
        ultimate_result = _build_ultimate_preserve_refine(next_id, latent_ref)
        if ultimate_result is not None:
            return ultimate_result

        decode_id = next_id
        graph[str(decode_id)] = {
            'class_type': 'VAEDecode',
            'inputs': {
                'samples': list(latent_ref),
                'vae': list(vae_ref),
            },
        }
        current_image_ref = [str(decode_id), 0]
        next_id += 1
        if upscale_model_name:
            loader_id = next_id
            graph[str(loader_id)] = {
                'class_type': 'UpscaleModelLoader',
                'inputs': {
                    'model_name': upscale_model_name,
                },
            }
            upscale_id = next_id + 1
            graph[str(upscale_id)] = {
                'class_type': 'ImageUpscaleWithModel',
                'inputs': {
                    'upscale_model': [str(loader_id), 0],
                    'image': list(current_image_ref),
                },
            }
            current_image_ref = [str(upscale_id), 0]
            next_id += 2

            native_scale = _infer_upscale_model_native_scale(upscale_model_name)
            extra_scale = scale_by / native_scale if native_scale > 0 else scale_by
            if abs(extra_scale - 1.0) > 0.01:
                rescale_id = next_id
                graph[str(rescale_id)] = {
                    'class_type': 'ImageScaleBy',
                    'inputs': {
                        'image': list(current_image_ref),
                        'upscale_method': refine_resize_method,
                        'scale_by': max(0.05, min(extra_scale, 8.0)),
                    },
                }
                current_image_ref = [str(rescale_id), 0]
                next_id += 1
        else:
            scale_id = next_id
            graph[str(scale_id)] = {
                'class_type': 'ImageScaleBy',
                'inputs': {
                    'image': list(current_image_ref),
                    'upscale_method': refine_resize_method,
                    'scale_by': scale_by,
                },
            }
            current_image_ref = [str(scale_id), 0]
            next_id += 1
        encode_id = next_id
        encode_class = 'VAEEncodeTiled' if use_tiled_vae else 'VAEEncode'
        encode_inputs = {
            'pixels': list(current_image_ref),
            'vae': list(vae_ref),
        }
        if use_tiled_vae:
            encode_inputs['tile_size'] = tile_size
            encode_inputs['overlap'] = tile_overlap
            encode_inputs['temporal_size'] = 64
            encode_inputs['temporal_overlap'] = 8
        graph[str(encode_id)] = {
            'class_type': encode_class,
            'inputs': encode_inputs,
        }
        sampler_id = next_id + 1
        graph[str(sampler_id)] = {
            'class_type': 'KSampler',
            'inputs': {
                'seed': max(1, seed),
                'steps': refine_steps,
                'cfg': refine_cfg,
                'sampler_name': refine_sampler,
                'scheduler': refine_scheduler,
                'denoise': refine_denoise,
                'model': list(model_ref),
                'positive': list(positive_ref),
                'negative': list(negative_ref),
                'latent_image': [str(encode_id), 0],
            },
        }
        return next_id + 2, [str(sampler_id), 0]

    upscale_id = next_id
    graph[str(upscale_id)] = {
        'class_type': 'LatentUpscaleBy',
        'inputs': {
            'samples': list(latent_ref),
            'upscale_method': refine_resize_method,
            'scale_by': scale_by,
        },
    }
    sampler_id = next_id + 1
    graph[str(sampler_id)] = {
        'class_type': 'KSampler',
        'inputs': {
            'seed': max(1, seed),
            'steps': refine_steps,
            'cfg': refine_cfg,
            'sampler_name': refine_sampler,
            'scheduler': refine_scheduler,
            'denoise': refine_denoise,
            'model': list(model_ref),
            'positive': list(positive_ref),
            'negative': list(negative_ref),
            'latent_image': [str(upscale_id), 0],
        },
    }
    return next_id + 2, [str(sampler_id), 0]




def _normalize_regional_prompt_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    # Phase 7 Scene Director bridge: only extension-owned SDXL / SD 1.5 units are allowed through.
    scene_units = payload.get("scene_director_regional_units")
    if isinstance(scene_units, list) and bool(payload.get("scene_director_enabled")):
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(scene_units, start=1):
            if not isinstance(raw, dict) or raw.get("enabled") is False:
                continue
            prompt = str(raw.get("prompt") or "").strip()
            negative_prompt = str(raw.get("negative_prompt") or "").strip()
            # Keep V052 active for Identity Profile-only regions. Without this, blank region prompts
            # prevent subject masks from being created, so profile IPAdapter units cannot attach.
            if not prompt and not negative_prompt:
                if payload.get('scene_director_ipadapter_units') or payload.get('scene_director_identity_units'):
                    prompt = str(raw.get("label") or f"Region {index}").strip()
                else:
                    continue
            unit = dict(raw)
            unit["index"] = int(unit.get("index") or index)
            unit["label"] = str(unit.get("label") or f"Region {index}")
            unit["prompt"] = prompt
            unit["negative_prompt"] = negative_prompt
            unit["mask_source"] = "rect"
            unit["backend_mode"] = "native"
            unit["overlap_mode"] = "blend"
            unit["composer_mode"] = "scene_director"
            normalized.append(unit)
        return normalized
    return []



def _build_rect_mask_layers(graph: Dict[str, Any], next_id: int, width: int, height: int, unit: dict[str, Any]):
    x_px = max(0, min(width - 8, int(round(width * float(unit.get('x') or 0.0)))))
    y_px = max(0, min(height - 8, int(round(height * float(unit.get('y') or 0.0)))))
    region_width = max(8, min(width - x_px, int(round(width * float(unit.get('w') or 0.33)))))
    region_height = max(8, min(height - y_px, int(round(height * float(unit.get('h') or 1.0)))))
    softness_pct = max(0.0, min(20.0, float(unit.get('falloff') or 0.0)))
    if softness_pct <= 0.0:
        softness_px = 0
        layers = [(0, 1.0)]
    else:
        softness_px = max(1, int(round(min(region_width, region_height) * (softness_pct / 100.0))))
        layers = [
            (0, 0.14),
            (max(1, int(round(softness_px * 0.33))), 0.18),
            (max(1, int(round(softness_px * 0.66))), 0.24),
            (max(1, softness_px), 0.44),
        ]
    built_layers: list[tuple[list[str], float]] = []
    for inset_px, weight in layers:
        inner_x = min(width - 8, x_px + inset_px)
        inner_y = min(height - 8, y_px + inset_px)
        inner_width = max(8, min(width - inner_x, region_width - (inset_px * 2)))
        inner_height = max(8, min(height - inner_y, region_height - (inset_px * 2)))
        base_mask_id = next_id
        graph[str(base_mask_id)] = {
            'class_type': 'SolidMask',
            'inputs': {
                'value': 0.0,
                'width': width,
                'height': height,
            },
        }
        region_mask_id = next_id + 1
        graph[str(region_mask_id)] = {
            'class_type': 'SolidMask',
            'inputs': {
                'value': 1.0,
                'width': inner_width,
                'height': inner_height,
            },
        }
        composite_id = next_id + 2
        graph[str(composite_id)] = {
            'class_type': 'MaskComposite',
            'inputs': {
                'destination': [str(base_mask_id), 0],
                'source': [str(region_mask_id), 0],
                'x': inner_x,
                'y': inner_y,
                'operation': 'add',
            },
        }
        built_layers.append(([str(composite_id), 0], float(weight)))
        next_id += 3
    return next_id, built_layers, softness_px


def _resolve_node_quality_controls(payload: Dict[str, Any], width: int, height: int, units: list[dict[str, Any]], overlap_mode: str) -> dict[str, Any]:
    min_dim = max(1, min(width, height))
    feather_default = 8 if min_dim <= 768 else 10
    if any(float(unit.get('falloff') or 0.0) > 0 for unit in units):
        feather_default = max(feather_default, 10)
    overlap_default = 8 if overlap_mode == 'blend' else 4

    feather_raw = payload.get('regional_node_feather_px')
    overlap_raw = payload.get('regional_node_overlap_factor')

    try:
        feather_px = int(round(float(feather_raw))) if feather_raw not in (None, '') else feather_default
    except Exception:
        feather_px = feather_default
    try:
        overlap_factor = int(round(float(overlap_raw))) if overlap_raw not in (None, '') else overlap_default
    except Exception:
        overlap_factor = overlap_default

    feather_px = max(2, min(32, feather_px))
    overlap_factor = max(0, min(32, overlap_factor))
    return {
        'feather_px': feather_px,
        'overlap_factor': overlap_factor,
    }


def _build_impact_rect_mask_ref(graph: Dict[str, Any], next_id: int, width: int, height: int, unit: dict[str, Any], feather_px: int):
    x_px = max(0, min(width - 8, int(round(width * float(unit.get('x') or 0.0)))))
    y_px = max(0, min(height - 8, int(round(height * float(unit.get('y') or 0.0)))))
    region_width = max(8, min(width - x_px, int(round(width * float(unit.get('w') or 0.33)))))
    region_height = max(8, min(height - y_px, int(round(height * float(unit.get('h') or 1.0)))))
    base_mask_id = next_id
    graph[str(base_mask_id)] = {
        'class_type': 'SolidMask',
        'inputs': {
            'value': 0.0,
            'width': width,
            'height': height,
        },
    }
    region_mask_id = next_id + 1
    graph[str(region_mask_id)] = {
        'class_type': 'SolidMask',
        'inputs': {
            'value': 1.0,
            'width': region_width,
            'height': region_height,
        },
    }
    composite_id = next_id + 2
    graph[str(composite_id)] = {
        'class_type': 'MaskComposite',
        'inputs': {
            'destination': [str(base_mask_id), 0],
            'source': [str(region_mask_id), 0],
            'x': x_px,
            'y': y_px,
            'operation': 'add',
        },
    }
    unit_feather_px = feather_px
    falloff = float(unit.get('falloff') or 0.0)
    if falloff > 0:
        unit_feather_px = max(unit_feather_px, int(round(min(width, height) * min(0.08, max(0.0, falloff / 100.0)))))
    unit_feather_px = max(2, min(32, unit_feather_px))
    feather_id = next_id + 3
    graph[str(feather_id)] = {
        'class_type': 'FeatherMask',
        'inputs': {
            'mask': [str(composite_id), 0],
            'left': unit_feather_px if region_width < width else 0,
            'top': unit_feather_px if region_height < height else 0,
            'right': unit_feather_px if region_width < width else 0,
            'bottom': unit_feather_px if region_height < height else 0,
        },
    }
    return next_id + 4, [str(feather_id), 0], unit_feather_px


def _resolve_regional_backend(payload: Dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    requested_backend = str((units[0].get('backend_mode') if units else payload.get('regional_backend_mode')) or 'auto').strip().lower() or 'auto'
    caps = payload.get('regional_backend_capabilities') if isinstance(payload.get('regional_backend_capabilities'), dict) else {}
    native_caps = caps.get('native') if isinstance(caps.get('native'), dict) else {}
    node_caps = caps.get('node') if isinstance(caps.get('node'), dict) else {}
    native_available = bool(native_caps.get('available', True))
    node_available = bool(node_caps.get('available', False))
    uses_mask_regions = any(str(unit.get('mask_source') or 'rect') == 'mask_image' for unit in units)
    uses_falloff = any(float(unit.get('falloff') or 0.0) > 0 for unit in units)
    fallback_reason = ''
    downgrade_notes: list[str] = []
    actual_backend = 'native'
    if requested_backend == 'dense_diffusion':
        fallback_reason = 'Dense Diffusion is hidden in this build while Neo focuses on the working Node backend path.'
        requested_backend = 'auto'
    if requested_backend == 'node':
        if not (REGIONAL_ENABLE_EXPERIMENTAL and REGIONAL_ENABLE_NODE_BACKEND):
            fallback_reason = str(node_caps.get('disabled_reason') or 'Node regional backend is disabled in this build.')
        elif not node_available:
            fallback_reason = 'Requested node backend is unavailable in this build.'
        else:
            actual_backend = 'node'
            if uses_falloff and not bool(node_caps.get('supports_falloff')):
                downgrade_notes.append('Impact Pack node routing does not support Regional Composer falloff yet, so box softness is approximated with overlap only.')
    elif requested_backend == 'auto':
        if node_available:
            actual_backend = 'node'
            if uses_falloff and not bool(node_caps.get('supports_falloff')):
                downgrade_notes.append('Impact Pack node routing does not support Regional Composer falloff yet, so box softness is approximated with overlap only.')
        else:
            fallback_reason = str(node_caps.get('disabled_reason') or 'Node backend unavailable, so Auto falls back to Native.')
    if actual_backend == 'native' and not native_available:
        fallback_reason = (fallback_reason + ' Native regional backend is also unavailable.').strip()
    return {
        'requested_backend': requested_backend if requested_backend in {'auto','native','node','dense_diffusion'} else 'auto',
        'actual_backend': actual_backend,
        'fallback_reason': fallback_reason,
        'downgrade_notes': downgrade_notes,
        'uses_mask_regions': uses_mask_regions,
        'uses_falloff': uses_falloff,
    }




def _resolve_active_vae_debug(payload: Dict[str, Any], vae_ref) -> dict[str, Any]:
    active_name = str(payload.get('_neo_active_vae_name') or payload.get('vae_name') or payload.get('vae') or '').strip()
    checkpoint_ref = payload.get('_neo_checkpoint_vae_ref') if isinstance(payload.get('_neo_checkpoint_vae_ref'), list) else None
    ref_list = list(vae_ref) if isinstance(vae_ref, (list, tuple)) and len(vae_ref) >= 2 else None
    using_external = bool(active_name) and bool(ref_list) and not (checkpoint_ref and list(checkpoint_ref) == ref_list)
    return {
        'active_name': active_name,
        'using_external': using_external,
        'ref': ref_list,
        'checkpoint_ref': list(checkpoint_ref) if checkpoint_ref else None,
    }


def _append_node_vae_consistency_notes(notes: list[str], payload: Dict[str, Any], vae_ref, base_pipe_id: int | None = None, regional_pipe_ids: list[int] | None = None):
    info = _resolve_active_vae_debug(payload, vae_ref)
    ref = info.get('ref') or ['?', '?']
    regional_pipe_ids = regional_pipe_ids or []
    if info.get('using_external'):
        notes.append(f"Impact Pack node routing is forcing VAE consistency with explicit VAELoader asset '{info['active_name']}' on ref {ref[0]}:{ref[1]}.")
    else:
        notes.append(f"Impact Pack node routing is using checkpoint VAE ref {ref[0]}:{ref[1]} consistently across base pipe, regional pipes, and final decode.")
    if base_pipe_id is not None:
        notes.append(f"Impact Pack base ToBasicPipe is wired to VAE ref {ref[0]}:{ref[1]} via node {base_pipe_id}.")
    if regional_pipe_ids:
        notes.append(f"Impact Pack regional ToBasicPipe nodes {', '.join(str(x) for x in regional_pipe_ids)} are all wired to the same VAE ref {ref[0]}:{ref[1]}.")
    notes.append(f"Impact Pack final VAEDecode should resolve against the same active VAE ref {ref[0]}:{ref[1]} after regional sampling.")


def _extract_node_regional_style_prompt(text: str) -> str:
    raw = str(text or '').strip()
    if not raw:
        return ''
    clauses = [part.strip() for part in re.split(r'[\n;,]+', raw) if part.strip()]
    if not clauses:
        return raw
    interaction_keywords = (
        'holding hands', 'holding', 'hands', 'hug', 'hugging', 'kiss', 'kissing', 'embrace', 'embracing',
        'partner', 'romantic', 'tension', 'standing close', 'close together', 'couple', 'duo', 'group',
        'friends', 'posing', 'looking at', 'looking into', 'looking toward', 'facing', 'pose', 'connection'
    )
    identity_keywords = (
        'man', 'woman', 'men', 'women', 'boy', 'girl', 'person', 'people', 'male', 'female',
        'hair', 'hoodie', 'jacket', 'coat', 'shirt', 'suit', 'dress', 'skin', 'eyes', 'expression',
        'smile', 'serious', 'blonde', 'black hair', 'streetwear', 'formal', 'playful'
    )
    style_keywords = (
        'cinematic', 'photo', 'photography', 'editorial', 'studio', 'lighting', 'light', 'depth of field',
        'dof', 'bokeh', '35mm', '50mm', '85mm', 'lens', 'high detail', 'detailed', 'ultra realistic',
        'realistic', 'texture', 'sharp focus', 'natural skin texture', 'film', 'filmic', 'contrast',
        'color grading', 'warm tones', 'cool tones', 'soft light', 'soft lighting', 'hard light'
    )
    kept: list[str] = []
    for clause in clauses:
        lower = clause.lower()
        if any(keyword in lower for keyword in interaction_keywords):
            continue
        if any(keyword in lower for keyword in identity_keywords):
            continue
        if any(keyword in lower for keyword in style_keywords):
            kept.append(clause)
        elif len(kept) < 2:
            kept.append(clause)
        if len(kept) >= 4:
            break
    if kept:
        return ', '.join(kept)
    return ', '.join(clauses[:2])


def _extract_node_identity_focus_clauses(text: str) -> list[str]:
    local_prompt = str(text or '').strip()
    if not local_prompt:
        return []
    clauses = [part.strip() for part in re.split(r'[\n;,]+', local_prompt) if part.strip()]
    identity_keywords = (
        'hair', 'hoodie', 'jacket', 'coat', 'shirt', 'suit', 'dress', 'skin', 'eyes', 'expression',
        'smile', 'serious', 'blonde', 'black hair', 'brown hair', 'streetwear', 'formal', 'playful',
        'red', 'blue', 'green', 'white', 'black', 'jawline', 'facial features', 'nose', 'lips',
        'short hair', 'long hair', 'curly hair', 'straight hair', 'tattoo', 'piercing'
    )
    focused: list[str] = []
    for clause in clauses:
        lower = clause.lower()
        if any(keyword in lower for keyword in identity_keywords):
            focused.append(clause)
        if len(focused) >= 3:
            break
    return focused


def _extract_node_structural_prompt_clauses(text: str) -> list[str]:
    raw = str(text or '').strip()
    if not raw:
        return []
    clauses = [part.strip() for part in re.split(r'[\n;,]+', raw) if part.strip()]
    structure_keywords = (
        'two people', 'two men', 'two women', 'standing close', 'close together', 'together',
        'portrait', 'cinematic photo', 'photo', 'photography', 'waist up', 'upper body',
        'facing each other', 'standing side by side', 'close portrait', 'framed together'
    )
    kept: list[str] = []
    for clause in clauses:
        lower = clause.lower()
        if any(keyword in lower for keyword in structure_keywords):
            kept.append(clause)
        if len(kept) >= 2:
            break
    return kept


def _build_node_spatial_prompt_clauses(unit: dict[str, Any]) -> list[str]:
    x = max(0.0, min(1.0, float(unit.get('x') or 0.0)))
    y = max(0.0, min(1.0, float(unit.get('y') or 0.0)))
    w = max(0.0, min(1.0, float(unit.get('w') or 0.0)))
    h = max(0.0, min(1.0, float(unit.get('h') or 0.0)))
    cx = x + (w / 2.0)
    cy = y + (h / 2.0)
    clauses: list[str] = []

    if w >= 0.9 and h >= 0.9:
        return clauses

    if w <= 0.7:
        if cx <= 0.38:
            clauses.append('left side of the frame')
            clauses.append('slightly facing right')
        elif cx >= 0.62:
            clauses.append('right side of the frame')
            clauses.append('slightly facing left')
        else:
            clauses.append('center of the frame')

    if h <= 0.7:
        if cy <= 0.38:
            clauses.append('upper part of the frame')
            if 'slightly facing right' not in clauses and 'slightly facing left' not in clauses:
                clauses.append('slightly angled downward toward the other subject')
        elif cy >= 0.62:
            clauses.append('lower part of the frame')
            if 'slightly facing right' not in clauses and 'slightly facing left' not in clauses:
                clauses.append('slightly angled upward toward the other subject')

    return clauses[:3]


def _build_node_regional_positive_prompt(payload: Dict[str, Any], unit: dict[str, Any]) -> str:
    local_prompt = str(unit.get('prompt') or '').strip()
    if not local_prompt:
        return str(payload.get('positive') or payload.get('prompt') or '').strip()
    global_source = str(payload.get('positive') or payload.get('prompt') or '')
    global_style_prompt = _extract_node_regional_style_prompt(global_source)
    structure_clauses = _extract_node_structural_prompt_clauses(global_source)
    spatial_clauses = _build_node_spatial_prompt_clauses(unit)
    style_prompt = str(unit.get('style_prompt') or unit.get('style_hint') or '').strip()
    identity_boost = max(0.5, min(2.0, float(unit.get('identity_boost') or 1.0)))

    prompt_parts = [local_prompt]
    identity_focus = _extract_node_identity_focus_clauses(local_prompt)
    if identity_focus:
        prompt_parts.extend(identity_focus[: 2 if identity_boost >= 1.15 else 1])
    if spatial_clauses:
        prompt_parts.extend(spatial_clauses)
    if structure_clauses:
        prompt_parts.extend(structure_clauses[:1])
    if style_prompt:
        prompt_parts.append(style_prompt)
    if global_style_prompt:
        prompt_parts.append(global_style_prompt)
    merged = _merge_prompt_parts(*prompt_parts)
    return merged or local_prompt or global_style_prompt or global_source.strip()


def _combine_conditioning_refs(graph: Dict[str, Any], next_id: int, left_ref, right_ref):
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'ConditioningCombine',
        'inputs': {
            'conditioning_1': list(left_ref),
            'conditioning_2': list(right_ref),
        },
    }
    return next_id + 1, [str(node_id), 0]


def _encode_regional_text_conditioning(graph: Dict[str, Any], next_id: int, clip_ref, text: str, payload: Dict[str, Any]):
    caps = payload.get('regional_backend_capabilities') if isinstance(payload.get('regional_backend_capabilities'), dict) else {}
    dense_caps = caps.get('dense_diffusion') if isinstance(caps.get('dense_diffusion'), dict) else {}
    wants_smz = bool(dense_caps.get('available')) and 'smZ CLIPTextEncode' not in (dense_caps.get('missing_preferred_components') or [])
    prompt_text = str(text or '').strip()
    if wants_smz:
        node_id = next_id
        graph[str(node_id)] = {
            'class_type': 'smZ CLIPTextEncode',
            'inputs': {
                'clip': list(clip_ref),
                'text': prompt_text,
                'parser': 'comfy',
                'mean_normalization': False,
                'multi_conditioning': False,
                'use_old_emphasis_implementation': False,
                'with_SDXL': False,
                'ascore': 6.0,
                'width': 1024,
                'height': 1024,
                'crop_w': 0,
                'crop_h': 0,
                'target_width': 1024,
                'target_height': 1024,
                'text_g': prompt_text,
                'text_l': prompt_text,
                'smZ_steps': 1,
            },
        }
        return next_id + 1, [str(node_id), 0], True
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'CLIPTextEncode',
        'inputs': {
            'text': prompt_text,
            'clip': list(clip_ref),
        },
    }
    return next_id + 1, [str(node_id), 0], False


def _normalize_conditioning_ref(graph: Dict[str, Any], next_id: int, conditioning_ref):
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'smZ Conditioning Normalize',
        'inputs': {
            'conditioning': list(conditioning_ref),
        },
    }
    return next_id + 1, [str(node_id), 0]


def _apply_regional_prompting_dense(graph: Dict[str, Any], next_id: int, model_ref, clip_ref, positive_ref, negative_ref, payload: Dict[str, Any], width: int, height: int, units: list[dict[str, Any]], overlap_mode: str):
    notes: list[str] = ['[DenseDiffusion debug] Starting regional compile pass.']
    dense_model_ref = list(model_ref)
    mask_image_count = 0
    used_smz_encode = False
    negative_limited = False
    use_priority = overlap_mode == 'priority'
    ordered_units = sorted(units, key=lambda item: (int(item.get('priority') or 99), int(item.get('index') or 99))) if use_priority else list(units)
    notes.append(f'[DenseDiffusion debug] Requested {len(ordered_units)} region(s) at {width}x{height}.')
    notes.append('[DenseDiffusion debug] Sampler must use the patched model returned by DenseDiffusionApplyNode.')
    for index, unit in enumerate(ordered_units, start=1):
        unit_prompt = str(unit.get('prompt') or '').strip()
        if not unit_prompt:
            continue
        if str(unit.get('negative_prompt') or '').strip():
            negative_limited = True
        label = str(unit.get('label') or '').strip() or f'Region {index}'
        if str(unit.get('mask_source') or 'rect') == 'mask_image' and str(unit.get('mask_image_name') or '').strip():
            next_id, mask_ref, used_mask_image, _ = _build_regional_mask_ref(graph, next_id, width, height, unit)
            mask_layers = [(mask_ref, 1.0)] if mask_ref else []
            if used_mask_image:
                mask_image_count += 1
        else:
            next_id, rect_layers, _ = _build_rect_mask_layers(graph, next_id, width, height, unit)
            mask_layers = rect_layers
        notes.append(f"[DenseDiffusion debug] {label}: prompt_present={bool(unit_prompt)} mask_source={str(unit.get('mask_source') or 'rect')} mask_layers={len(mask_layers)} strength={round(float(unit.get('positive_strength') or unit.get('strength') or 1.0), 4)}.")
        merged_prompt = _merge_prompt_parts(payload.get('positive') or '', unit_prompt)
        notes.append(f"[DenseDiffusion debug] {label}: merged prompt preview -> {merged_prompt[:120]}")
        next_id, region_cond_ref, used_smz = _encode_regional_text_conditioning(graph, next_id, clip_ref, merged_prompt, payload)
        used_smz_encode = used_smz_encode or used_smz
        notes.append(f"[DenseDiffusion debug] {label}: conditioning encoded via {'smZ CLIPTextEncode' if used_smz else 'CLIPTextEncode'}.")
        next_id, region_cond_ref = _normalize_conditioning_ref(graph, next_id, region_cond_ref)
        notes.append(f"[DenseDiffusion debug] {label}: conditioning normalized before model injection.")
        for layer_ref, layer_weight in mask_layers:
            add_id = next_id
            graph[str(add_id)] = {
                'class_type': 'DenseDiffusionAddCondNode',
                'inputs': {
                    'model': list(dense_model_ref),
                    'conditioning': list(region_cond_ref),
                    'mask': list(layer_ref),
                    'strength': round(float(unit.get('positive_strength') or unit.get('strength') or 1.0) * float(layer_weight), 4),
                },
            }
            dense_model_ref = [str(add_id), 0]
            notes.append(f"[DenseDiffusion debug] {label}: DenseDiffusionAddCondNode applied with weight {round(float(unit.get('positive_strength') or unit.get('strength') or 1.0) * float(layer_weight), 4)} -> model {dense_model_ref[0]}.")
            next_id += 1
        label_prefix = f"{str(unit.get('label') or '').strip()}: " if str(unit.get('label') or '').strip() else ''
        if str(unit.get('mask_source') or 'rect') == 'mask_image':
            notes.append(f"{label_prefix or f'Regional prompt {index}: '}Dense Diffusion mask image region queued on the {str(unit.get('mask_channel') or 'alpha')} channel.")
        else:
            falloff = float(unit.get('falloff') or 0.0)
            suffix = f" and roughly {int(round(falloff))}% soft edges" if falloff > 0 else ''
            notes.append(f"{label_prefix or f'Regional prompt {index}: '}Dense Diffusion region queued at {int(round(float(unit.get('x') or 0.0) * 100))}%/{int(round(float(unit.get('y') or 0.0) * 100))}% with {int(round(float(unit.get('w') or 0.0) * 100))}%×{int(round(float(unit.get('h') or 0.0) * 100))}% coverage{suffix}.")
    notes.append(f"[DenseDiffusion debug] Final patched model before apply -> {dense_model_ref[0]}")
    apply_id = next_id
    graph[str(apply_id)] = {
        'class_type': 'DenseDiffusionApplyNode',
        'inputs': {
            'model': list(dense_model_ref),
        },
    }
    next_id += 1
    current_model_ref = [str(apply_id), 0]
    current_positive_ref = [str(apply_id), 1]
    notes.append(f"[DenseDiffusion debug] DenseDiffusionApplyNode finalized patched model {current_model_ref[0]} and returned conditioning output {current_positive_ref[0]}.")
    if negative_limited:
        notes.append('Dense Diffusion Sprint 2 keeps per-region negatives limited; the main negative prompt still comes from the global negative field.')
    if used_smz_encode:
        notes.append('Dense Diffusion regional prompts used smZ CLIPTextEncode for prompt encoding.')
    else:
        notes.append('Dense Diffusion regional prompts fell back to standard CLIPTextEncode because smZ CLIPTextEncode was not detected.')
    notes.append('Dense Diffusion currently does not compose with IPAdapter model patching; disable IPAdapter if the backend behaves unpredictably.')
    notes.append('[DenseDiffusion debug] If output still follows the global prompt only, verify that the sampler consumes the patched model ref shown above instead of the original checkpoint model.')
    return next_id, current_model_ref, current_positive_ref, negative_ref, notes, mask_image_count


def _build_regional_mask_ref(graph: Dict[str, Any], next_id: int, width: int, height: int, unit: dict[str, Any], backend: str = 'native', feather_px: int | None = None):
    if str(unit.get('mask_source') or 'rect') == 'mask_image' and str(unit.get('mask_image_name') or '').strip():
        mask_id = next_id
        graph[str(mask_id)] = {
            'class_type': 'LoadImageMask',
            'inputs': {
                'image': str(unit.get('mask_image_name') or '').strip(),
                'channel': str(unit.get('mask_channel') or 'alpha').strip().lower() or 'alpha',
            },
        }
        return next_id + 1, [str(mask_id), 0], True, 0
    if backend == 'node':
        next_id, mask_ref, feather_px = _build_impact_rect_mask_ref(graph, next_id, width, height, unit, int(feather_px or 8))
        return next_id, mask_ref, False, feather_px
    next_id, mask_layers, softness_px = _build_rect_mask_layers(graph, next_id, width, height, {**unit, 'falloff': 0.0})
    mask_ref = list(mask_layers[0][0]) if mask_layers else None
    return next_id, mask_ref, False, softness_px


def _apply_regional_prompting_impact(graph: Dict[str, Any], next_id: int, model_ref, clip_ref, vae_ref, positive_ref, negative_ref, sampler_input, payload: Dict[str, Any], width: int, height: int, seed: int, steps: int, cfg: float, sampler_name: str, scheduler_name: str, denoise: float, units: list[dict[str, Any]], overlap_mode: str):
    notes: list[str] = []
    selected_vae_name = str(payload.get('vae_name') or payload.get('vae') or '').strip()
    regional_prompt_refs: list[list[str]] = []
    regional_pipe_ids: list[int] = []
    mask_image_count = 0
    uses_negative = False

    safe_sampler_name = 'dpmpp_2m'
    safe_scheduler_name = 'karras'
    sampler_overridden = False
    if str(sampler_name or '').strip().lower() != safe_sampler_name or str(scheduler_name or '').strip().lower() != safe_scheduler_name:
        sampler_overridden = True
        sampler_name = safe_sampler_name
        scheduler_name = safe_scheduler_name

    quality = _resolve_node_quality_controls(payload, width, height, units, overlap_mode)
    overlap_factor = int(quality.get('overlap_factor') or 8)
    default_feather_px = int(quality.get('feather_px') or 8)
    sigma_factor = 1.0

    base_pipe_id = next_id
    graph[str(base_pipe_id)] = {
        'class_type': 'ToBasicPipe',
        'inputs': {
            'model': list(model_ref),
            'clip': list(clip_ref),
            'vae': list(vae_ref),
            'positive': list(positive_ref),
            'negative': list(negative_ref),
        },
    }
    base_sampler_id = next_id + 1
    graph[str(base_sampler_id)] = {
        'class_type': 'KSamplerAdvancedProvider',
        'inputs': {
            'cfg': cfg,
            'sampler_name': sampler_name,
            'scheduler': scheduler_name,
            'sigma_factor': sigma_factor,
            'basic_pipe': [str(base_pipe_id), 0],
        },
    }
    next_id += 2

    for idx, unit in enumerate(units, start=1):
        next_id, mask_ref, used_mask_image, feather_px = _build_regional_mask_ref(graph, next_id, width, height, unit, backend='node', feather_px=default_feather_px)
        if used_mask_image:
            mask_image_count += 1
        region_positive_ref = positive_ref
        region_negative_ref = negative_ref
        regional_positive_prompt = _build_node_regional_positive_prompt(payload, unit)
        if regional_positive_prompt:
            prompt_id = next_id
            graph[str(prompt_id)] = {
                'class_type': 'CLIPTextEncode',
                'inputs': {
                    'text': regional_positive_prompt,
                    'clip': list(clip_ref),
                },
            }
            region_positive_ref = [str(prompt_id), 0]
            next_id += 1
        if str(unit.get('negative_prompt') or '').strip():
            uses_negative = True
            negative_id = next_id
            graph[str(negative_id)] = {
                'class_type': 'CLIPTextEncode',
                'inputs': {
                    'text': str(unit.get('negative_prompt') or '').strip(),
                    'clip': list(clip_ref),
                },
            }
            next_id, region_negative_ref = _combine_conditioning_refs(graph, next_id + 1, negative_ref, [str(negative_id), 0])
        regional_pipe_id = next_id
        regional_pipe_ids.append(regional_pipe_id)
        graph[str(regional_pipe_id)] = {
            'class_type': 'ToBasicPipe',
            'inputs': {
                'model': list(model_ref),
                'clip': list(clip_ref),
                'vae': list(vae_ref),
                'positive': list(region_positive_ref),
                'negative': list(region_negative_ref),
            },
        }
        regional_sampler_id = next_id + 1
        graph[str(regional_sampler_id)] = {
            'class_type': 'KSamplerAdvancedProvider',
            'inputs': {
                'cfg': cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler_name,
                'sigma_factor': sigma_factor,
                'basic_pipe': [str(regional_pipe_id), 0],
            },
        }
        regional_prompt_id = next_id + 2
        graph[str(regional_prompt_id)] = {
            'class_type': 'RegionalPrompt',
            'inputs': {
                'mask': list(mask_ref),
                'advanced_sampler': [str(regional_sampler_id), 0],
                'variation_seed': 0,
                'variation_strength': 0.0,
                'variation_method': 'linear',
            },
        }
        regional_prompt_refs.append([str(regional_prompt_id), 0])
        next_id += 3
        label_prefix = f"{str(unit.get('label') or '').strip()}: " if str(unit.get('label') or '').strip() else ''
        if used_mask_image:
            notes.append(f"{label_prefix or f'Regional prompt {idx}: '}Impact Pack mask region queued on the {str(unit.get('mask_channel') or 'alpha')} channel.")
        else:
            notes.append(f"{label_prefix or f'Regional prompt {idx}: '}Impact Pack box region queued at {int(round(float(unit.get('x') or 0.0) * 100))}%/{int(round(float(unit.get('y') or 0.0) * 100))}% with {int(round(float(unit.get('w') or 0.0) * 100))}%×{int(round(float(unit.get('h') or 0.0) * 100))}% coverage and ~{feather_px}px feathering.")
    if not regional_prompt_refs:
        return next_id, None, notes, mask_image_count
    combined_ref = regional_prompt_refs[0]
    for extra_ref in regional_prompt_refs[1:]:
        combine_id = next_id
        graph[str(combine_id)] = {
            'class_type': 'CombineRegionalPrompts',
            'inputs': {
                'regional_prompts1': list(combined_ref),
                'regional_prompts2': list(extra_ref),
            },
        }
        combined_ref = [str(combine_id), 0]
        next_id += 1
    regional_sampler_id = next_id
    graph[str(regional_sampler_id)] = {
        'class_type': 'RegionalSamplerAdvanced',
        'inputs': {
            'add_noise': True,
            'noise_seed': seed,
            'steps': steps,
            'start_at_step': 0,
            'end_at_step': 10000,
            'overlap_factor': overlap_factor,
            'restore_latent': True,
            'return_with_leftover_noise': False,
            'latent_image': list(sampler_input),
            'base_sampler': [str(base_sampler_id), 0],
            'regional_prompts': list(combined_ref),
            'additional_mode': 'ratio between',
            'additional_sampler': 'AUTO',
            'additional_sigma_ratio': 0.3,
        },
    }
    next_id += 1
    if sampler_overridden:
        notes.append('Impact Pack node routing forced the known-safe sampler stack dpmpp_2m / karras to avoid colored-noise failures with unsupported sampler combinations.')
    if uses_negative:
        notes.append('Impact Pack node routing is using per-region negative prompts through regional KSamplerAdvanced conditionings.')
    _append_node_vae_consistency_notes(notes, payload, vae_ref, base_pipe_id=base_pipe_id, regional_pipe_ids=regional_pipe_ids)
    notes.append(f'Impact Pack node routing compiled {len(regional_prompt_refs)} regional prompt(s) into RegionalSamplerAdvanced.')
    notes.append(f'Impact Pack node quality tuning is using overlap factor {overlap_factor} and default feather {default_feather_px}px to reduce prompt stitching and over-soft blending.')
    notes.append('Impact Pack node conditioning balance now compiles each region with local-first identity anchors, spatial frame cues, and filtered global support instead of a full global/local conditioning stack.')
    notes.append(f'Impact Pack node routing matched the proven Neo test graph with overlap factor {overlap_factor}, sigma factor {sigma_factor}, ratio-between additional sampling, and spatial anchoring cues.')
    return next_id, [str(regional_sampler_id), 0], notes, mask_image_count



def _normalize_scene_director_ipadapter_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    raw_units = payload.get('scene_director_ipadapter_units')
    if not isinstance(raw_units, list):
        return units
    for unit in raw_units:
        if not isinstance(unit, dict):
            continue
        mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
        if mode not in {'standard', 'faceid'}:
            mode = 'standard'
        model_name = str(unit.get('model') or unit.get('ipadapter_name') or '').strip()
        clip_vision_name = str(unit.get('clip_vision') or unit.get('clip_vision_name') or '').strip()
        image_names = unit.get('image_names') if isinstance(unit.get('image_names'), list) else []
        image_names = [str(item or '').strip() for item in image_names if str(item or '').strip()]
        image_name = str(unit.get('image_name') or '').strip()
        if image_name and image_name not in image_names:
            image_names.insert(0, image_name)
        if not clip_vision_name or not image_names or (mode != 'faceid' and not model_name):
            continue
        region_index = _clamp_int(unit.get('region_index') or 1, 1, 1, 4)
        normalized = {
            'uid': str(unit.get('uid') or f'scene_region_{region_index}').strip(),
            'mode': mode,
            'region_id': str(unit.get('region_id') or '').strip(),
            'region_index': region_index,
            'label': str(unit.get('label') or f'Region {region_index}').strip(),
            'model': model_name,
            'clip_vision': clip_vision_name,
            'image_name': image_names[0],
            'image_names': image_names,
            'weight': _clamp_float(unit.get('weight') or 0.52, 0.52, 0.0, 2.0),
            'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
            'start_at': _clamp_float(unit.get('start_at') if unit.get('start_at') is not None else 0.05, 0.05, 0.0, 1.0),
            'end_at': _clamp_float(unit.get('end_at') if unit.get('end_at') is not None else 0.75, 0.75, 0.0, 1.0),
            'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
            'attn_mask_output_index': _clamp_int(unit.get('attn_mask_output_index') or (5 + region_index), 5 + region_index, 6, 9),
            'faceid_preset': str(unit.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
            'faceid_provider': str(unit.get('faceid_provider') or 'CUDA').strip() or 'CUDA',
            'faceid_lora_strength': _clamp_float(unit.get('faceid_lora_strength') if unit.get('faceid_lora_strength') is not None else 0.75, 0.75, 0.0, 2.0),
            'weight_faceidv2': _clamp_float(unit.get('weight_faceidv2') if unit.get('weight_faceidv2') is not None else (unit.get('weight') if unit.get('weight') is not None else 1.0), 1.0, 0.0, 2.0),
        }
        units.append(normalized)
    return units


def _apply_scene_director_ipadapter_stack(graph: Dict[str, Any], next_id: int, model_ref, scene_node_id: int, payload: Dict[str, Any]):
    """Apply Scene Director IPAdapter units to the model produced by NeoSceneDirector.

    Phase 10.3.14 repair:
    - Restores the standard IPAdapter branch that was accidentally overwritten by LoRA-binding code.
    - Keeps FaceID on the same unified preset route used by the working main Neo IPAdapter lane.
    - Never injects standalone InsightFaceLoader/IPAdapterInsightFaceLoader nodes from Scene Director.
    - Uses Scene Director subject mask outputs as attn_mask for regional locking.
    """
    units = _normalize_scene_director_ipadapter_units(payload)
    notes: list[str] = []
    current_model_ref = list(model_ref)
    shared_faceid_loader_ref = None
    for unit in units:
        next_id, image_ref = _build_ipadapter_image_ref(graph, next_id, unit.get('image_names') or [unit.get('image_name')])
        if not image_ref:
            notes.append(f"Scene Director IPAdapter skipped {str(unit.get('label') or 'region')}: no reference image could be loaded.")
            continue
        mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
        region_index = int(unit.get('region_index') or 1)
        attn_mask_ref = [str(scene_node_id), int(unit.get('attn_mask_output_index') or (5 + region_index))]

        if mode == 'faceid':
            # Match the main Neo IPAdapter FaceID lane. This unified loader owns the FaceID
            # preset + provider path internally on installs where normal FaceID already works.
            if not shared_faceid_loader_ref:
                loader_id = next_id
                graph[str(loader_id)] = {
                    'class_type': 'IPAdapterUnifiedLoaderFaceID',
                    'inputs': {
                        'model': list(current_model_ref),
                        'preset': str(unit.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
                        'lora_strength': round(float(unit.get('faceid_lora_strength') if unit.get('faceid_lora_strength') is not None else 0.75), 4),
                        'provider': str(unit.get('faceid_provider') or 'CUDA').strip() or 'CUDA',
                    },
                }
                shared_faceid_loader_ref = [str(loader_id), 1]
                current_model_ref = [str(loader_id), 0]
                next_id += 1

            clip_loader_id = next_id
            graph[str(clip_loader_id)] = {
                'class_type': 'CLIPVisionLoader',
                'inputs': {
                    'clip_name': str(unit.get('clip_vision') or '').strip(),
                },
            }
            apply_id = next_id + 1
            graph[str(apply_id)] = {
                'class_type': 'IPAdapterFaceID',
                'inputs': {
                    'model': list(current_model_ref),
                    'ipadapter': list(shared_faceid_loader_ref),
                    'clip_vision': [str(clip_loader_id), 0],
                    'image': list(image_ref),
                    'weight': round(float(unit.get('weight') if unit.get('weight') is not None else 0.52), 4),
                    'weight_faceidv2': round(float(unit.get('weight_faceidv2') if unit.get('weight_faceidv2') is not None else (unit.get('weight') if unit.get('weight') is not None else 1.0)), 4),
                    'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
                    'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
                    'start_at': round(float(unit.get('start_at') if unit.get('start_at') is not None else 0.05), 4),
                    'end_at': round(float(unit.get('end_at') if unit.get('end_at') is not None else 0.75), 4),
                    'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
                    'attn_mask': attn_mask_ref,
                },
            }
            current_model_ref = [str(apply_id), 0]
            notes.append(f"Scene Director FaceID locked {str(unit.get('label') or 'region')} with subject_{region_index}_mask through the unified FaceID preset route.")
            next_id += 2
            continue

        # Standard masked IPAdapter branch. This was the part that got corrupted in 10.3.13.
        model_name = str(unit.get('model') or '').strip()
        clip_name = str(unit.get('clip_vision') or '').strip()
        if not model_name or not clip_name:
            notes.append(f"Scene Director IPAdapter skipped {str(unit.get('label') or 'region')}: missing IPAdapter model or CLIP Vision.")
            continue
        loader_id = next_id
        graph[str(loader_id)] = {
            'class_type': 'IPAdapterModelLoader',
            'inputs': {
                'ipadapter_file': model_name,
            },
        }
        clip_loader_id = next_id + 1
        graph[str(clip_loader_id)] = {
            'class_type': 'CLIPVisionLoader',
            'inputs': {
                'clip_name': clip_name,
            },
        }
        apply_id = next_id + 2
        graph[str(apply_id)] = {
            'class_type': 'IPAdapterAdvanced',
            'inputs': {
                'model': list(current_model_ref),
                'ipadapter': [str(loader_id), 0],
                'clip_vision': [str(clip_loader_id), 0],
                'image': list(image_ref),
                'weight': round(float(unit.get('weight') if unit.get('weight') is not None else 0.52), 4),
                'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
                'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
                'start_at': round(float(unit.get('start_at') if unit.get('start_at') is not None else 0.05), 4),
                'end_at': round(float(unit.get('end_at') if unit.get('end_at') is not None else 0.75), 4),
                'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
                'attn_mask': attn_mask_ref,
            },
        }
        current_model_ref = [str(apply_id), 0]
        notes.append(f"Scene Director IPAdapter locked {str(unit.get('label') or 'region')} with subject_{region_index}_mask.")
        next_id += 3

    if units:
        faceid_count = sum(1 for unit in units if str(unit.get('mode') or '').lower() == 'faceid')
        standard_count = len(units) - faceid_count
        if faceid_count:
            notes.append(f"Scene Director used one shared FaceID unified loader for {faceid_count} FaceID region binding(s).")
        if standard_count:
            notes.append(f"Scene Director applied {standard_count} standard masked IPAdapter region binding(s).")
    return next_id, current_model_ref, notes

def _normalize_scene_director_lora_units(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve Scene Director region LoRA bindings against existing Neo LoRA slots.

    Phase 9.2 implements regional LoRA as a masked low-denoise latent pass after the
    base Scene Director sample. This is intentionally not a global LoraLoader on the
    first sampler; bound slots are removed from the global LoRA stack by the adapter.
    """
    bindings = payload.get('scene_director_lora_bindings')
    sources = payload.get('scene_director_bound_lora_units_source')
    if not isinstance(bindings, list) or not isinstance(sources, list):
        return []
    source_by_slot: dict[int, dict[str, Any]] = {}
    for index, src in enumerate(sources):
        if not isinstance(src, dict):
            continue
        try:
            slot = int(src.get('_neo_lora_slot_index') or index + 1)
        except Exception:
            slot = index + 1
        if slot > 0:
            source_by_slot[slot] = src
    out: list[dict[str, Any]] = []
    seen_regions: set[int] = set()
    for bind in bindings:
        if not isinstance(bind, dict):
            continue
        try:
            region_index = int(bind.get('region_index') or 0)
        except Exception:
            region_index = 0
        try:
            slot = int(bind.get('slot') or 0)
        except Exception:
            slot = 0
        if region_index <= 0 or region_index > 4 or slot <= 0:
            continue
        if region_index in seen_regions:
            continue
        source = source_by_slot.get(slot)
        if not source:
            continue
        name = str(source.get('name') or source.get('lora_name') or '').strip()
        if not name:
            continue
        weight_mode = str(bind.get('weight_mode') or 'slot_default').strip().lower() or 'slot_default'
        if weight_mode == 'custom':
            strength = _clamp_float(bind.get('strength'), 0.8, -4.0, 4.0)
        else:
            strength = _clamp_float(source.get('strength') or source.get('lora_strength') or 0.8, 0.8, -4.0, 4.0)
        out.append({
            'region_index': region_index,
            'slot': slot,
            'name': name,
            'strength': strength,
            'label': str(bind.get('label') or f'Region {region_index}'),
            'uid': str(bind.get('uid') or f'scene_lora_region_{region_index}'),
        })
        seen_regions.add(region_index)
    return out


def _apply_scene_director_regional_lora_passes(
    graph: Dict[str, Any],
    next_id: int,
    latent_ref,
    model_ref,
    clip_ref,
    vae_ref,
    scene_node_id: int | str | None,
    payload: Dict[str, Any],
    seed: int,
    steps: int,
    cfg: float,
    sampler_name: str,
    scheduler_name: str,
):
    """Apply region-bound LoRA slots as masked latent refinement passes.

    Normal LoRA is model-wide, so Phase 9.2 avoids applying bound LoRAs to the first
    full-canvas sampler. Instead, each bound LoRA runs a short low-denoise sampler pass
    with the Scene Director subject mask attached to the latent. This gives practical
    regional LoRA behavior while keeping global LoRAs separate and avoiding whole-image
    leakage.
    """
    units = _normalize_scene_director_lora_units(payload)
    if not units or not scene_node_id:
        return next_id, latent_ref, []
    notes: list[str] = []
    try:
        scene_node = int(scene_node_id)
    except Exception:
        scene_node = int(str(scene_node_id))
    denoise = _clamp_float(payload.get('scene_director_lora_denoise') or 0.35, 0.35, 0.05, 0.85)
    lora_steps = max(4, int(_clamp_float(payload.get('scene_director_lora_steps') or min(14, max(8, int(steps * 0.35))), 12, 1, 80)))
    current_latent_ref = list(latent_ref)
    for offset, unit in enumerate(units):
        region_index = int(unit.get('region_index') or 1)
        mask_output_index = 5 + region_index  # V052 output 6 = subject_1_mask, 7 = subject_2_mask, etc.
        mask_ref = [str(scene_node), mask_output_index]

        lora_id = next_id
        graph[str(lora_id)] = {
            'class_type': 'LoraLoader',
            'inputs': {
                'model': list(model_ref),
                'clip': list(clip_ref),
                'lora_name': str(unit.get('name') or '').strip(),
                'strength_model': round(float(unit.get('strength') or 0.8), 4),
                'strength_clip': round(float(unit.get('strength') or 0.8), 4),
            },
        }
        positive_id = next_id + 1
        graph[str(positive_id)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'clip': [str(lora_id), 1],
                'text': [str(scene_node), 3],
            },
        }
        negative_id = next_id + 2
        graph[str(negative_id)] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'clip': [str(lora_id), 1],
                'text': [str(scene_node), 4],
            },
        }
        mask_latent_id = next_id + 3
        graph[str(mask_latent_id)] = {
            'class_type': 'SetLatentNoiseMask',
            'inputs': {
                'samples': list(current_latent_ref),
                'mask': mask_ref,
            },
        }
        sampler_id = next_id + 4
        graph[str(sampler_id)] = {
            'class_type': 'KSampler',
            'inputs': {
                'seed': int(seed) + 9703 + (offset * 101),
                'steps': int(lora_steps),
                'cfg': float(cfg),
                'sampler_name': str(sampler_name),
                'scheduler': str(scheduler_name),
                'denoise': float(denoise),
                'model': [str(lora_id), 0],
                'positive': [str(positive_id), 0],
                'negative': [str(negative_id), 0],
                'latent_image': [str(mask_latent_id), 0],
            },
        }
        current_latent_ref = [str(sampler_id), 0]
        notes.append(f"Scene Director regional LoRA applied slot {int(unit.get('slot') or 0)} to {str(unit.get('label') or f'Region {region_index}')} with subject_{region_index}_mask, denoise {denoise:.2f}.")
        next_id += 5
    if units:
        notes.append('Scene Director Phase 9.2 keeps region-bound LoRAs out of the global LoRA stack and applies them as masked refinement passes.')
    return next_id, current_latent_ref, notes



# Phase 10.3.4: server-side prompt attention bridge for Scene Director.
# Final Comfy graph construction is the source of truth, so prompt strength is
# applied here even if the browser sends plain region text.
def _neo_scene_director_clamp_prompt_strength(value: Any) -> float:
    try:
        n = float(value)
    except Exception:
        return 1.0
    if not math.isfinite(n):
        return 1.0
    return max(0.0, min(2.0, round(n, 2)))


def _neo_scene_director_format_strength(value: Any) -> str:
    n = _neo_scene_director_clamp_prompt_strength(value)
    if abs(n - int(n)) < 1e-9:
        return str(int(n))
    return (f"{n:.2f}").rstrip('0').rstrip('.')


def _neo_scene_director_apply_prompt_strength(text: Any, strength: Any) -> str:
    prompt = str(text or '').strip()
    if not prompt:
        return ''
    safe = _neo_scene_director_clamp_prompt_strength(strength)
    if safe <= 0 or abs(safe - 1.0) < 0.001:
        return prompt
    value = _neo_scene_director_format_strength(safe)
    m = re.match(r"^\(([\s\S]*):\s*([0-9]*\.?[0-9]+)\)$", prompt)
    if m:
        return f"({m.group(1).strip()}:{value})"
    return f"({prompt}:{value})"


def _neo_scene_director_strength_map(payload: Dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    units = payload.get('scene_director_regional_units')
    if not isinstance(units, list):
        return result
    for index, unit in enumerate(units, start=1):
        if not isinstance(unit, dict):
            continue
        strength = _neo_scene_director_clamp_prompt_strength(unit.get('strength', 1.0))
        keys = [str(unit.get('id') or '').strip(), str(unit.get('label') or '').strip(), f"region_{index}", f"person_{index}", f"object_{index}", str(index)]
        for key in keys:
            if key:
                result[key] = strength
    return result


def _neo_scene_director_patch_scene_json_prompt_strength(scene_json: str, payload: Dict[str, Any]) -> tuple[str, bool]:
    raw = str(scene_json or '').strip()
    if not raw:
        return raw, False
    try:
        data = json.loads(raw)
    except Exception:
        return raw, False
    if not isinstance(data, dict):
        return raw, False
    strength_map = _neo_scene_director_strength_map(payload)
    changed = False
    def strength_for(item: dict[str, Any], fallback_index: int, fallback_prefix: str) -> float:
        keys = [str(item.get('id') or '').strip(), str(item.get('label') or '').strip(), f'{fallback_prefix}_{fallback_index}', f'region_{fallback_index}', str(fallback_index)]
        for key in keys:
            if key in strength_map:
                return strength_map[key]
        return _neo_scene_director_clamp_prompt_strength(item.get('prompt_strength', item.get('strength', 1.0)))
    for section, prefix in (('subjects', 'person'), ('objects', 'object')):
        items = data.get(section)
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            strength = strength_for(item, idx, prefix)
            item['prompt_strength'] = strength
            original = str(item.get('prompt') or '').strip()
            patched = _neo_scene_director_apply_prompt_strength(original, strength)
            if patched != original:
                item['prompt'] = patched
                changed = True
    if changed:
        try:
            return json.dumps(data, ensure_ascii=False), True
        except Exception:
            return raw, False
    return raw, False

def _apply_scene_director_v052_node(graph: Dict[str, Any], next_id: int, model_ref, clip_ref, positive_ref, negative_ref, payload: Dict[str, Any], width: int, height: int):
    """Route Scene Director through the proven NeoSceneDirectorV052 custom node and optional masked per-region IPAdapter chain."""
    scene_json = str(payload.get('scene_director_v052_scene_json') or '').strip()
    scene_json, prompt_strength_patched = _neo_scene_director_patch_scene_json_prompt_strength(scene_json, payload)
    if not scene_json:
        return next_id, model_ref, positive_ref, negative_ref, []
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'NeoSceneDirectorV052',
        'inputs': {
            'model': list(model_ref),
            'clip': list(clip_ref),
            'width': int(width),
            'height': int(height),
            'global_prompt_override': str(payload.get('scene_director_v052_global_prompt_override') or ''),
            'base_weight': str(payload.get('scene_director_v052_base_weight') or '0.55'),
            'region_gain': str(payload.get('scene_director_v052_region_gain') or '0.40'),
            'max_subject_slots': int(payload.get('scene_director_v052_max_subject_slots') or 1),
            'normalize_masks': bool(payload.get('scene_director_v052_normalize_masks', True)),
            'enable_auto_prompts': bool(payload.get('scene_director_v052_enable_auto_prompts', True)),
            'scene_json': scene_json,
        },
    }
    payload['_scene_director_v052_node_id'] = node_id
    positive_encode_id = next_id + 1
    graph[str(positive_encode_id)] = {
        'class_type': 'CLIPTextEncode',
        'inputs': {
            'clip': list(clip_ref),
            'text': [str(node_id), 3],
        },
    }
    negative_encode_id = next_id + 2
    graph[str(negative_encode_id)] = {
        'class_type': 'CLIPTextEncode',
        'inputs': {
            'clip': list(clip_ref),
            'text': [str(node_id), 4],
        },
    }
    notes = [
        'Scene Director Phase 8 routed through NeoSceneDirectorV052 with editable prompt contracts.',
        'Scene Director V052 is generating count-locked positive/negative prompts from scene_json before sampling.',
    ]
    if payload.get('scene_director_regional_units'):
        notes.append(f"Scene Director V052 received {len(payload.get('scene_director_regional_units') or [])} required subject slot(s).")
    if prompt_strength_patched:
        notes.append('Scene Director prompt strength was applied server-side as A1111/Forge attention syntax before CLIP encoding.')
    next_id = next_id + 3
    scene_model_ref = [str(node_id), 0]
    # Stage 6.1 repair: apply prepared Scene Director native IPAdapter slot
    # bindings and Character Profile / FaceID units as masked model patches.
    # V052 outputs subject masks at indices 6..9; the normalized units already
    # carry the matching attn_mask_output_index.
    if payload.get('scene_director_ipadapter_units') or payload.get('scene_director_identity_units'):
        next_id, scene_model_ref, ip_notes = _apply_scene_director_ipadapter_stack(
            graph,
            next_id,
            scene_model_ref,
            node_id,
            payload,
        )
        notes.extend(ip_notes)
    elif payload.get('scene_director_ipadapter_bindings'):
        notes.append('Scene Director found IPAdapter binding metadata, but no prepared region IPAdapter units reached the graph. Check the native IPAdapter slot has a model, CLIP Vision, and reference image.')
    return next_id, scene_model_ref, [str(positive_encode_id), 0], [str(negative_encode_id), 0], notes

def _apply_regional_prompting(graph: Dict[str, Any], next_id: int, model_ref, positive_ref, negative_ref, clip_ref, vae_ref, sampler_input, payload: Dict[str, Any], width: int, height: int, mode: str, seed: int, steps: int, cfg: float, sampler_name: str, scheduler_name: str, denoise: float):
    units = _normalize_regional_prompt_units(payload)
    notes: list[str] = []
    if not units:
        return next_id, model_ref, positive_ref, negative_ref, sampler_input, notes, False
    scene_variant = str(payload.get('scene_director_model_variant') or (units[0].get('model_variant') if units else '') or '').strip().lower()
    if payload.get('scene_director_enabled'):
        if scene_variant == 'sd15':
            notes.append('Scene Director Phase 8 is using the SD 1.5 V052 + per-region IPAdapter profile.')
        elif scene_variant == 'sdxl':
            notes.append('Scene Director Phase 8 is using the SDXL V052 + per-region IPAdapter profile.')
        else:
            notes.append('Scene Director Phase 8 is using the shared SD checkpoint V052 + per-region IPAdapter profile.')
    scene_director_v052_requested = bool(payload.get('scene_director_enabled')) and str(payload.get('scene_director_backend_mode') or payload.get('regional_backend_mode') or '').strip().lower() == 'v052_node'
    if mode not in {'txt2img', 'img2img', 'inpaint'}:
        if scene_director_v052_requested:
            notes.append(f'Scene Director V052 skipped for {mode}: this mode is not wired in Phase 5.')
            payload['_neo_scene_director_applied'] = False
            payload['_neo_scene_director_skip_reason'] = f'unsupported_mode_{mode}'
        else:
            notes.append('Regional Composer is currently wired for txt2img/img2img/inpaint first; this generation mode ignores the regional map for now.')
        return next_id, model_ref, positive_ref, negative_ref, sampler_input, notes, False

    if scene_director_v052_requested:
        next_id, scene_model_ref, scene_positive_ref, scene_negative_ref, scene_notes = _apply_scene_director_v052_node(
            graph, next_id, model_ref, clip_ref, positive_ref, negative_ref, payload, width, height
        )
        notes.extend(scene_notes)
        if scene_notes:
            # Phase 8.3 / Phase 5: Scene Director replaces the base positive/negative conditioning with
            # V052-generated conditioning. Main ControlNet must therefore be re-applied *after*
            # the V052 node so Canny/OpenPose/Depth/etc. keep working normally as global helpers.
            # For inpaint, this affects conditioning only; source image + mask latent path is
            # built before this call and remains preserved. ControlNet remains global, not
            # region-bound. Region-bound tools stay limited to IPAdapter and future regional LoRA.
            controlnet_units = _normalize_controlnet_units(payload)
            if controlnet_units:
                next_id, scene_positive_ref, scene_negative_ref = _apply_controlnet_stack(
                    graph, next_id, scene_positive_ref, scene_negative_ref, vae_ref, controlnet_units
                )
                notes.append(f'Scene Director Phase 8.3 preserved {len(controlnet_units)} global ControlNet unit(s) after V052 conditioning.')
            payload['_neo_scene_director_applied'] = True
            payload['_neo_scene_director_mode'] = mode
            
            if mode == 'inpaint':
                payload['_neo_scene_director_mask_preserved'] = True
                notes.append('Scene Director V052 applied to inpaint conditioning; source image, mask, and SetLatentNoiseMask sampler input preserved.')
            else:
                notes.append(f'Scene Director V052 applied to {mode} conditioning; sampler/source latent path preserved.')
            return next_id, scene_model_ref, scene_positive_ref, scene_negative_ref, sampler_input, notes, False
        payload['_neo_scene_director_applied'] = False
        payload['_neo_scene_director_skip_reason'] = 'missing_scene_json'
        notes.append('Scene Director V052 node parity requested but no scene_json was available; falling back to native regional conditioning.')

    if mode != 'txt2img':
        notes.append('Native Regional Composer fallback remains txt2img-only; img2img/inpaint only use Scene Director V052 when available.')
        return next_id, model_ref, positive_ref, negative_ref, sampler_input, notes, False

    composer_mode = str((units[0].get('composer_mode') if units else payload.get('regional_composer_mode')) or 'basic').strip().lower() or 'basic'
    overlap_mode = str((units[0].get('overlap_mode') if units else payload.get('regional_overlap_mode')) or 'blend').strip().lower() or 'blend'
    backend_resolution = _resolve_regional_backend(payload, units)
    runtime_backend = str(backend_resolution.get('actual_backend') or 'native').strip().lower() or 'native'
    requested_backend = str(backend_resolution.get('requested_backend') or 'auto').strip().lower() or 'auto'
    if requested_backend == 'native':
        notes.append('Regional Composer forced native mask conditioning for a more predictable prompt map pass.')
    if backend_resolution.get('fallback_reason'):
        notes.append(str(backend_resolution.get('fallback_reason') or '').strip())
    for note in (backend_resolution.get('downgrade_notes') or []):
        if str(note).strip():
            notes.append(str(note).strip())
    if overlap_mode == 'priority':
        units = sorted(units, key=lambda item: (int(item.get('priority') or 99), int(item.get('index') or 99)))
        notes.append('Regional Composer is using priority overlap order; higher-priority regions are compiled first.')

    current_model_ref = model_ref
    current_positive_ref = positive_ref
    current_negative_ref = negative_ref
    current_sampler_input = sampler_input
    mask_image_count = 0

    used_node_sampler = False
    if runtime_backend == 'dense_diffusion':
        next_id, current_model_ref, current_positive_ref, current_negative_ref, dense_notes, mask_image_count = _apply_regional_prompting_dense(
            graph, next_id, model_ref, clip_ref, positive_ref, negative_ref, payload, width, height, units, overlap_mode,
        )
        notes.extend(dense_notes)
    elif runtime_backend == 'node':
        next_id, current_sampler_input, node_notes, mask_image_count = _apply_regional_prompting_impact(
            graph, next_id, model_ref, clip_ref, vae_ref, positive_ref, negative_ref, sampler_input, payload, width, height, seed, steps, cfg, sampler_name, scheduler_name, denoise, units, overlap_mode,
        )
        notes.extend(node_notes)
        used_node_sampler = True
    else:
        for index, unit in enumerate(units, start=1):
            mask_ref = None
            mask_layers = []
            if str(unit.get('mask_source') or 'rect') == 'mask_image' and str(unit.get('mask_image_name') or '').strip():
                load_mask_id = next_id
                graph[str(load_mask_id)] = {
                    'class_type': 'LoadImage',
                    'inputs': {
                        'image': str(unit.get('mask_image_name') or '').strip(),
                        'upload': 'image',
                    },
                }
                image_to_mask_id = next_id + 1
                graph[str(image_to_mask_id)] = {
                    'class_type': 'ImageToMask',
                    'inputs': {
                        'image': [str(load_mask_id), 0],
                        'channel': str(unit.get('mask_channel') or 'alpha').strip().lower() or 'alpha',
                    },
                }
                mask_ref = [str(image_to_mask_id), 0]
                next_id += 2
                mask_image_count += 1
            else:
                next_id, mask_layers, _ = _build_rect_mask_layers(graph, next_id, width, height, unit)
                mask_ref = list(mask_layers[0][0]) if mask_layers else None
            positive_strength = float(unit.get('positive_strength') or unit.get('strength') or 1.0)
            negative_strength = float(unit.get('negative_strength') or unit.get('strength') or 1.0)
            label_prefix = f"{str(unit.get('label') or '').strip()}: " if str(unit.get('label') or '').strip() else ''
            if str(unit.get('prompt') or '').strip():
                for layer_ref, layer_weight in (mask_layers if str(unit.get('mask_source') or 'rect') != 'mask_image' else [(mask_ref, 1.0)]):
                    prompt_id = next_id
                    graph[str(prompt_id)] = {
                        'class_type': 'CLIPTextEncode',
                        'inputs': {
                            'text': str(unit.get('prompt') or '').strip(),
                            'clip': list(clip_ref),
                        },
                    }
                    masked_cond_id = next_id + 1
                    graph[str(masked_cond_id)] = {
                        'class_type': 'ConditioningSetMask',
                        'inputs': {
                            'conditioning': [str(prompt_id), 0],
                            'mask': list(layer_ref),
                            'strength': round(positive_strength * float(layer_weight), 4),
                            'set_cond_area': 'mask bounds',
                        },
                    }
                    combine_id = next_id + 2
                    graph[str(combine_id)] = {
                        'class_type': 'ConditioningCombine',
                        'inputs': {
                            'conditioning_1': list(current_positive_ref),
                            'conditioning_2': [str(masked_cond_id), 0],
                        },
                    }
                    current_positive_ref = [str(combine_id), 0]
                    next_id += 3
            if str(unit.get('negative_prompt') or '').strip():
                for layer_ref, layer_weight in (mask_layers if str(unit.get('mask_source') or 'rect') != 'mask_image' else [(mask_ref, 1.0)]):
                    prompt_id = next_id
                    graph[str(prompt_id)] = {
                        'class_type': 'CLIPTextEncode',
                        'inputs': {
                            'text': str(unit.get('negative_prompt') or '').strip(),
                            'clip': list(clip_ref),
                        },
                    }
                    masked_cond_id = next_id + 1
                    graph[str(masked_cond_id)] = {
                        'class_type': 'ConditioningSetMask',
                        'inputs': {
                            'conditioning': [str(prompt_id), 0],
                            'mask': list(layer_ref),
                            'strength': round(negative_strength * float(layer_weight), 4),
                            'set_cond_area': 'mask bounds',
                        },
                    }
                    combine_id = next_id + 2
                    graph[str(combine_id)] = {
                        'class_type': 'ConditioningCombine',
                        'inputs': {
                            'conditioning_1': list(current_negative_ref),
                            'conditioning_2': [str(masked_cond_id), 0],
                        },
                    }
                    current_negative_ref = [str(combine_id), 0]
                    next_id += 3
            if str(unit.get('mask_source') or 'rect') == 'mask_image':
                notes.append(f"{label_prefix or f'Regional prompt {index}: '}mask image on the {str(unit.get('mask_channel') or 'alpha')} channel.")
            else:
                falloff = float(unit.get('falloff') or 0.0)
                if falloff > 0:
                    notes.append(f"{label_prefix or f'Regional prompt {index}: '}queued at {int(round(float(unit.get('x') or 0.0) * 100))}%/{int(round(float(unit.get('y') or 0.0) * 100))}% with {int(round(float(unit.get('w') or 0.0) * 100))}%×{int(round(float(unit.get('h') or 0.0) * 100))}% coverage and roughly {int(round(falloff))}% soft edges.")
                else:
                    notes.append(f"{label_prefix or f'Regional prompt {index}: '}queued at {int(round(float(unit.get('x') or 0.0) * 100))}%/{int(round(float(unit.get('y') or 0.0) * 100))}% with {int(round(float(unit.get('w') or 0.0) * 100))}%×{int(round(float(unit.get('h') or 0.0) * 100))}% coverage.")

    summary = f"Regional Composer enabled with {len(units)} active region(s). {composer_mode.title()} mode · requested {requested_backend.title()} · actual {runtime_backend.title()} · {overlap_mode.title()} overlap."
    if mask_image_count:
        summary += f' {mask_image_count} region(s) use uploaded mask images.'
    notes.insert(0, summary)
    return next_id, current_model_ref, current_positive_ref, current_negative_ref, current_sampler_input, notes, used_node_sampler

def _maybe_supir(graph: Dict[str, Any], next_id: int, image_ref, payload: Dict[str, Any], seed: int):
    notes: list[str] = []
    if not bool(payload.get('supir_enabled')):
        return next_id, image_ref, notes
    supir_model = str(payload.get('supir_model') or '').strip()
    sdxl_model = str(payload.get('supir_sdxl_model') or payload.get('checkpoint') or '').strip()
    if not supir_model or not sdxl_model:
        notes.append('SUPIR was enabled but a SUPIR checkpoint or SDXL checkpoint was missing, so the SUPIR pass was skipped.')
        return next_id, image_ref, notes
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'SUPIR_Upscale',
        'inputs': {
            'supir_model': supir_model,
            'sdxl_model': sdxl_model,
            'image': list(image_ref),
            'seed': max(1, seed),
            'resize_method': 'lanczos',
            'scale_by': _clamp_float(payload.get('supir_scale') or 1.5, 1.5, 0.25, 8.0),
            'steps': _clamp_int(payload.get('supir_steps') or 45, 45, 3, 4096),
            'restoration_scale': _clamp_float(payload.get('supir_restoration_scale') if payload.get('supir_restoration_scale') is not None else -1.0, -1.0, -1.0, 6.0),
            'cfg_scale': _clamp_float(payload.get('supir_cfg_scale') or 4.0, 4.0, 0.0, 100.0),
            'a_prompt': str(payload.get('supir_a_prompt') or 'high quality, detailed'),
            'n_prompt': str(payload.get('supir_n_prompt') or 'bad quality, blurry, messy'),
            's_churn': 5,
            's_noise': 1.003,
            'control_scale': _clamp_float(payload.get('supir_control_scale') or 1.0, 1.0, 0.0, 10.0),
            'cfg_scale_start': _clamp_float(payload.get('supir_cfg_scale') or 4.0, 4.0, 0.0, 100.0),
            'control_scale_start': 0.0,
            'color_fix_type': str(payload.get('supir_color_fix_type') or 'Wavelet').strip() or 'Wavelet',
            'keep_model_loaded': True,
            'use_tiled_vae': bool(payload.get('supir_tiled_vae', True)),
            'encoder_tile_size_pixels': _clamp_int(payload.get('supir_encoder_tile_size') or 512, 512, 64, 8192),
            'decoder_tile_size_latent': _clamp_int(payload.get('supir_decoder_tile_size') or 64, 64, 32, 8192),
        },
    }
    notes.append(f'SUPIR restoration pass queued with {supir_model} over {sdxl_model}.')
    return next_id + 1, [str(node_id), 0], notes



def _resolve_standard_inpaint_inputs(payload: Dict[str, Any], inpaint_payload: Dict[str, Any] | None) -> dict:
    source_images_row = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
    mask_row = (inpaint_payload.get('mask') or {}) if isinstance(inpaint_payload, dict) else {}
    return {
        'source_image': str(source_images_row.get('base_image_name') or payload.get('source_image_name') or '').strip(),
        'mask_image': str(mask_row.get('mask_image_name') or payload.get('mask_image_name') or '').strip(),
        'grow_mask_by': _clamp_int(mask_row.get('grow_mask_by') if mask_row.get('grow_mask_by') is not None else payload.get('grow_mask_by') or 6, 6, 0, 128),
    }


def _build_standard_sdxl_inpaint_sampler_input(
    graph: Dict[str, Any],
    next_id: int,
    *,
    source_image: str,
    mask_image: str,
    vae_ref,
    inpaint_target: str,
    inpaint_context: str,
    grow_mask_by: int,
) -> Tuple[int, list[Any], list[str]]:
    if not source_image or not mask_image:
        raise ValueError('Inpaint needs both a source image and a mask image.')

    notes = ['SDXL inpaint source/mask latent prep engaged: classic mask-aware path.']
    load_id = next_id
    graph[str(load_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': source_image,
            'upload': 'image',
        },
    }
    mask_id = next_id + 1
    graph[str(mask_id)] = {
        'class_type': 'LoadImageMask',
        'inputs': {
            'image': mask_image,
            'channel': 'red',
        },
    }
    active_mask_ref = [str(mask_id), 0]
    next_id += 2

    if inpaint_target == 'unmasked':
        invert_id = next_id
        graph[str(invert_id)] = {
            'class_type': 'InvertMask',
            'inputs': {
                'mask': list(active_mask_ref),
            },
        }
        active_mask_ref = [str(invert_id), 0]
        next_id += 1
        notes.append('SDXL standard inpaint is targeting the unmasked region by inverting the incoming mask.')

    if inpaint_context == 'masked_focus':
        encode_id = next_id
        graph[str(encode_id)] = {
            'class_type': 'VAEEncodeForInpaint',
            'inputs': {
                'pixels': [str(load_id), 0],
                'vae': list(vae_ref),
                'mask': list(active_mask_ref),
                'grow_mask_by': grow_mask_by,
            },
        }
        notes.append(f'SDXL masked-focus context is using VAEEncodeForInpaint with grow_mask_by {grow_mask_by}.')
        return next_id + 1, [str(encode_id), 0], notes

    encode_id = next_id
    graph[str(encode_id)] = {
        'class_type': 'VAEEncode',
        'inputs': {
            'pixels': [str(load_id), 0],
            'vae': list(vae_ref),
        },
    }
    noise_mask_id = next_id + 1
    graph[str(noise_mask_id)] = {
        'class_type': 'SetLatentNoiseMask',
        'inputs': {
            'samples': [str(encode_id), 0],
            'mask': list(active_mask_ref),
        },
    }
    notes.append('SDXL full-image context is encoding the source image first, then attaching the mask with SetLatentNoiseMask.')
    return next_id + 2, [str(noise_mask_id), 0], notes


def _build_standard_sdxl_outpaint_sampler_input(
    graph: Dict[str, Any],
    next_id: int,
    *,
    source_image: str,
    vae_ref,
    outpaint_left: int,
    outpaint_top: int,
    outpaint_right: int,
    outpaint_bottom: int,
    outpaint_feather: int,
) -> Tuple[int, list[Any], list[str]]:
    if not source_image:
        raise ValueError('Outpaint needs a source image.')
    if outpaint_left + outpaint_top + outpaint_right + outpaint_bottom <= 0:
        raise ValueError('Outpaint needs padding on at least one side.')

    notes = [
        'SDXL standard outpaint branch engaged: ImagePadForOutpaint + latent noise mask.',
        f'SDXL outpaint padding — left {outpaint_left}, top {outpaint_top}, right {outpaint_right}, bottom {outpaint_bottom}, feather {outpaint_feather}.',
    ]
    load_id = next_id
    graph[str(load_id)] = {
        'class_type': 'LoadImage',
        'inputs': {
            'image': source_image,
            'upload': 'image',
        },
    }
    pad_id = next_id + 1
    graph[str(pad_id)] = {
        'class_type': 'ImagePadForOutpaint',
        'inputs': {
            'image': [str(load_id), 0],
            'left': outpaint_left,
            'top': outpaint_top,
            'right': outpaint_right,
            'bottom': outpaint_bottom,
            'feathering': outpaint_feather,
        },
    }
    encode_id = next_id + 2
    graph[str(encode_id)] = {
        'class_type': 'VAEEncode',
        'inputs': {
            'pixels': [str(pad_id), 0],
            'vae': list(vae_ref),
        },
    }
    noise_mask_id = next_id + 3
    graph[str(noise_mask_id)] = {
        'class_type': 'SetLatentNoiseMask',
        'inputs': {
            'samples': [str(encode_id), 0],
            'mask': [str(pad_id), 1],
        },
    }
    return next_id + 4, [str(noise_mask_id), 0], notes



def _apply_phase9_effective_payload_hygiene(payload: Dict[str, Any], *, mode: str, family: str, model_source: str, inpaint_backend: str, scene_director_requested: bool) -> tuple[str, str, list[str]]:
    """Normalize compiled workflow intent without deleting raw UI state.

    Phase 9 policy:
    - UI may keep stale family/backend/model fields for user convenience.
    - The workflow compiler must use explicit effective values so stale Qwen,
      LanPaint, Scene Director, or backend state cannot silently affect the wrong
      workflow lane.
    """
    notes: list[str] = []
    effective_backend = normalize_inpaint_backend(inpaint_backend or 'standard')
    if mode != 'inpaint' and effective_backend != 'standard':
        notes.append(f'Phase 9 hygiene: ignored stale inpaint backend {effective_backend!r} for {mode}; compiled as standard.')
        effective_backend = 'standard'
        payload['inpaint_backend'] = 'standard'
        nested_payload = payload.get('inpaint_payload')
        if isinstance(nested_payload, dict):
            nested_payload['backend'] = 'standard'
    elif mode == 'inpaint':
        payload['inpaint_backend'] = effective_backend
        nested_payload = payload.get('inpaint_payload')
        if isinstance(nested_payload, dict):
            nested_payload['backend'] = effective_backend

    effective_model_source = model_source if model_source in {'checkpoint', 'gguf'} else 'checkpoint'
    effective_family = str(family or '').strip().lower()
    effective_scene_director_applied = bool(scene_director_requested and mode in {'txt2img', 'img2img', 'inpaint'})
    scene_director_skip_reason = ''
    if scene_director_requested and not effective_scene_director_applied:
        scene_director_skip_reason = 'outpaint_not_supported' if mode == 'outpaint' else 'unsupported_mode'

    effective_lanpaint_route = bool(mode == 'inpaint' and effective_backend == 'lanpaint')
    effective_qwen_route = bool(effective_model_source == 'gguf' and effective_family == 'qwen_image_edit')

    payload['_neo_effective_mode'] = mode
    payload['_neo_effective_family'] = effective_family
    payload['_neo_effective_model_source'] = effective_model_source
    payload['_neo_effective_inpaint_backend'] = effective_backend
    payload['_neo_effective_lanpaint_route'] = effective_lanpaint_route
    payload['_neo_effective_qwen_route'] = effective_qwen_route
    payload['_neo_scene_director_applied'] = effective_scene_director_applied
    payload['_neo_scene_director_mode'] = mode
    scene_state = payload.get('scene_director_state')
    if isinstance(scene_state, dict):
        raw_scene_mode = str(scene_state.get('mode') or mode).strip().lower() or mode
        preview_action = payload.get('_neo_preview_action') if isinstance(payload.get('_neo_preview_action'), dict) else {}
        source_mode = str(preview_action.get('save_lane') or payload.get('save_mode_override') or raw_scene_mode).strip().lower() or raw_scene_mode
        scene_state['_neo_source_mode'] = source_mode
        scene_state['_neo_execution_mode'] = mode
        scene_state['_neo_mode_sync_policy'] = 'source_preserved_execution_visible'
        if raw_scene_mode != mode:
            scene_state['_neo_raw_mode'] = raw_scene_mode
            scene_state['mode'] = mode
            payload['_neo_scene_director_source_mode'] = source_mode
            payload['_neo_scene_director_execution_mode'] = mode
            payload['_neo_scene_director_mode_sync'] = f'{raw_scene_mode}->{mode}'
            notes.append(f'Phase 9 hygiene: Scene Director state mode synced {raw_scene_mode!r} -> {mode!r}; source mode preserved as {source_mode!r}.')
    if scene_director_skip_reason:
        payload['_neo_scene_director_skip_reason'] = scene_director_skip_reason
    else:
        payload.pop('_neo_scene_director_skip_reason', None)
    payload['_neo_state_hygiene_phase'] = 'phase9_effective_compile_contract_v1'

    raw_model_source = str(payload.get('model_source') or '').strip().lower()
    if raw_model_source and raw_model_source != effective_model_source:
        notes.append(f'Phase 9 hygiene: model_source normalized {raw_model_source!r} -> {effective_model_source!r}.')
    if effective_model_source == 'checkpoint' and (payload.get('gguf_unet') or payload.get('gguf_clip_primary') or payload.get('gguf_clip_secondary')):
        payload['_neo_gguf_fields_present_but_inactive'] = True
        notes.append('Phase 9 hygiene: GGUF/Qwen UI fields are present but inactive because checkpoint route is compiled.')
    else:
        payload['_neo_gguf_fields_present_but_inactive'] = False

    return effective_backend, effective_model_source, notes

def build_generation_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    payload = merge_shared_inpaint_payload(payload)

    inpaint_payload = get_shared_inpaint_payload(payload)
    mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')
    if mode not in {'txt2img', 'img2img', 'inpaint', 'outpaint'}:
        raise ValueError('Unsupported generation mode.')

    family = str(payload.get('family') or '').strip().lower()
    inpaint_backend = normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard')
    # Phase 9 hygiene: LanPaint/inpaint backend is only meaningful for inpaint.
    # Keep raw UI fields, but compile source-image non-inpaint lanes as standard.
    if mode in {'txt2img', 'img2img', 'outpaint'} and inpaint_backend != 'standard':
        inpaint_backend = 'standard'
        payload['inpaint_backend'] = 'standard'
        nested_payload = payload.get('inpaint_payload')
        if isinstance(nested_payload, dict):
            nested_payload['backend'] = 'standard'
        if mode == 'txt2img':
            payload.pop('inpaint_payload', None)
    support_check = validate_generation_support(family, mode, inpaint_backend)
    if not support_check.get('ok'):
        raise ValueError(str(support_check.get('message') or 'This family / mode combo is not available in this build.'))
    model_source = str(payload.get('model_source') or 'checkpoint').strip().lower()
    if family == 'qwen_image_edit' and str(payload.get('gguf_unet') or '').strip():
        model_source = 'gguf'
    if model_source not in {'checkpoint', 'gguf'}:
        model_source = 'checkpoint'

    checkpoint = str(payload.get('checkpoint') or '').strip()
    gguf_unet = str(payload.get('gguf_unet') or '').strip()
    gguf_clip_mode = str(payload.get('gguf_clip_mode') or 'dual').strip().lower()
    if gguf_clip_mode not in {'single', 'dual'}:
        gguf_clip_mode = 'dual'
    gguf_clip_type = str(payload.get('gguf_clip_type') or 'flux').strip().lower()
    if family == 'qwen_image_edit':
        gguf_clip_type = 'qwen_image'
        gguf_clip_mode = 'single'
    if gguf_clip_type == 'qwen_image':
        gguf_clip_mode = 'single'
    if gguf_clip_mode == 'dual':
        if gguf_clip_type not in {'flux', 'sd3', 'sdxl'}:
            gguf_clip_type = 'flux'
    else:
        if gguf_clip_type not in {'stable_diffusion', 'flux', 'sd3', 'sdxl', 'qwen_image'}:
            gguf_clip_type = 'stable_diffusion'
    gguf_clip_primary = str(payload.get('gguf_clip_primary') or '').strip()
    gguf_clip_secondary = str(payload.get('gguf_clip_secondary') or '').strip()
    gguf_guidance_default = 3.0 if gguf_clip_type == 'qwen_image' else 3.5
    gguf_guidance = _clamp_float(payload.get('gguf_guidance') or gguf_guidance_default, gguf_guidance_default, 0.0, 20.0)

    if model_source == 'gguf':
        if not gguf_unet:
            raise ValueError('Choose a GGUF model first.')
        if not gguf_clip_primary:
            raise ValueError('Choose at least one GGUF encoder first.')
        if gguf_clip_mode == 'dual' and not gguf_clip_secondary:
            raise ValueError('Choose the second GGUF encoder first.')
    else:
        if not checkpoint:
            raise ValueError('Choose a checkpoint first.')

    gguf_family_defaults = model_source == 'gguf' and gguf_clip_type in {'flux', 'qwen_image'}
    qwen_fast_defaults = bool(model_source == 'gguf' and gguf_clip_type == 'qwen_image' and any(token in gguf_unet.lower() for token in ('rapid', 'lightning', 'turbo', 'aio')))
    default_steps = 4 if qwen_fast_defaults else (25 if gguf_family_defaults else 28)
    default_cfg = 1.0 if gguf_family_defaults else 6.5
    lanpaint_policy = get_lanpaint_sampler_policy(family)
    lanpaint_route_requested = mode == 'inpaint' and inpaint_backend == 'lanpaint'
    default_sampler = lanpaint_policy['default_sampler'] if lanpaint_route_requested else ('sa_solver' if qwen_fast_defaults else 'euler')
    default_scheduler = lanpaint_policy['default_scheduler'] if lanpaint_route_requested else ('beta' if qwen_fast_defaults else ('simple' if gguf_family_defaults else 'normal'))

    seed = parse_seed(payload.get('seed'))
    width = _clamp_int(payload.get('width') or 1024, 1024, 256, 2048)
    height = _clamp_int(payload.get('height') or 1024, 1024, 256, 2048)
    steps = _clamp_int(payload.get('steps') or default_steps, default_steps, 1, 150)
    cfg = _clamp_float(payload.get('cfg') or default_cfg, default_cfg, 1.0, 30.0)
    batch_size = _clamp_int(payload.get('batch_size') or 1, 1, 1, 8)
    denoise = _clamp_float(payload.get('denoise') or 1.0, 1.0, 0.0, 1.0)
    sampler_name = normalize_sampler_name(payload.get('sampler') or default_sampler)
    scheduler_name = normalize_scheduler_name(payload.get('scheduler') or default_scheduler)
    lanpaint_policy_notes: list[str] = []
    if lanpaint_route_requested:
        sampler_name, scheduler_name, lanpaint_policy_notes = apply_lanpaint_sampler_policy(family, sampler_name, scheduler_name)
        payload['_neo_lanpaint_sampler_policy'] = {
            'family': family,
            'requested_sampler': normalize_sampler_name(payload.get('sampler') or default_sampler),
            'requested_scheduler': normalize_scheduler_name(payload.get('scheduler') or default_scheduler),
            'effective_sampler': sampler_name,
            'effective_scheduler': scheduler_name,
            'allowed_samplers': sorted(lanpaint_policy['allowed_samplers']),
            'allowed_schedulers': sorted(lanpaint_policy['allowed_schedulers']),
            'policy': lanpaint_policy.get('policy') or '',
        }
    vae_name = str(payload.get('vae_name') or payload.get('vae') or '').strip()
    inpaint_target = str(payload.get('inpaint_target') or 'masked').strip().lower()
    if inpaint_target not in {'masked', 'unmasked'}:
        inpaint_target = 'masked'
    inpaint_context = str(payload.get('inpaint_context') or 'full_image').strip().lower()
    if inpaint_context not in {'full_image', 'masked_focus'}:
        inpaint_context = 'full_image'
    outpaint_row = (inpaint_payload.get('outpaint') or {}) if isinstance(inpaint_payload, dict) else {}
    outpaint_left = _clamp_int(outpaint_row.get('left') if outpaint_row.get('left') is not None else payload.get('outpaint_left') or 0, 0, 0, 2048)
    outpaint_top = _clamp_int(outpaint_row.get('top') if outpaint_row.get('top') is not None else payload.get('outpaint_top') or 0, 0, 0, 2048)
    outpaint_right = _clamp_int(outpaint_row.get('right') if outpaint_row.get('right') is not None else payload.get('outpaint_right') or 0, 0, 0, 2048)
    outpaint_bottom = _clamp_int(outpaint_row.get('bottom') if outpaint_row.get('bottom') is not None else payload.get('outpaint_bottom') or 0, 0, 0, 2048)
    outpaint_feather = _clamp_int(outpaint_row.get('feather') if outpaint_row.get('feather') is not None else payload.get('outpaint_feather') or 24, 24, 0, 512)
    lora_units = _normalize_lora_units(payload)
    controlnet_units = _normalize_controlnet_units(payload)
    ipadapter_units = _normalize_ipadapter_units(payload)
    detailer_units = _normalize_detailer_passes(payload)
    qwen_mode = model_source == 'gguf' and gguf_clip_type == 'qwen_image'
    sdxl_standard_inpaint = family == 'sdxl_sd' and mode == 'inpaint' and inpaint_backend == 'standard'
    sdxl_lanpaint_inpaint = family == 'sdxl_sd' and mode == 'inpaint' and inpaint_backend == 'lanpaint'
    sdxl_standard_outpaint = family == 'sdxl_sd' and mode == 'outpaint' and inpaint_backend == 'standard'
    qwen_image_refs: list[Any] = []
    refine_mode_requested = str(payload.get('refine_mode') or 'latent').strip().lower()
    refine_strategy = str(payload.get('refine_strategy') or 'standard').strip().lower() or 'standard'
    qwen_reedit_source_only = bool(payload.get('upscale_lab_source_only')) and qwen_mode and bool(payload.get('refine_enabled')) and refine_strategy == 'qwen_reedit'
    image_upscale_source_only = bool(payload.get('upscale_lab_source_only')) and bool(payload.get('refine_enabled')) and refine_mode_requested == 'image_upscale' and not qwen_reedit_source_only

    base_positive_text, base_negative_text = _build_pass_prompt_pair(payload, 'base')
    refine_positive_text, refine_negative_text = _build_pass_prompt_pair(payload, 'finish')
    if not base_positive_text:
        raise ValueError('Positive prompt is empty.')

    prompt_conditioning_mode = _normalize_prompt_conditioning_mode(payload.get('prompt_conditioning_mode'))
    clip_skip = _normalize_clip_skip(payload.get('clip_skip') or 1)
    clip_skip_supported = _supports_clip_skip(payload)

    compile_notes: list[str] = []
    compile_notes.extend(_sanitize_sdxl_only_modules_for_family(payload, family=family, model_source=model_source, gguf_clip_type=gguf_clip_type))
    builder_contract = _normalize_workflow_builder_contract(payload, builder_name='generation', mode=mode)
    _attach_builder_contract(payload, builder_contract, compile_notes)
    if model_source == 'gguf':
        compile_notes.append(f"GGUF workflow enabled · {gguf_unet}")
        compile_notes.append(f"GGUF encoder path: {gguf_clip_mode} · {gguf_clip_type.replace('_', ' ')}")
        if not vae_name:
            raise ValueError('Choose a VAE for the GGUF workflow first.')

    scene_director_requested = bool(payload.get('scene_director_enabled')) and str(payload.get('scene_director_backend_mode') or payload.get('regional_backend_mode') or '').strip().lower() == 'v052_node'
    inpaint_backend, model_source, hygiene_notes = _apply_phase9_effective_payload_hygiene(
        payload,
        mode=mode,
        family=family,
        model_source=model_source,
        inpaint_backend=inpaint_backend,
        scene_director_requested=scene_director_requested,
    )
    compile_notes.extend(hygiene_notes)
    if scene_director_requested and mode == 'outpaint':
        payload['_neo_scene_director_outpaint_policy'] = 'skip_outpaint'
        # Keep the UI state intact, but make the compiled workflow contract explicit:
        # outpaint expands canvas/source pixels, while Scene Director regional conditioning
        # is intentionally scoped to txt2img, img2img, and inpaint in this build.
        compile_notes.append('Scene Director skipped for outpaint: outpaint uses source canvas expansion only in this build.')
    requested_batch_size = batch_size

    # Phase 8: precise batch / conditioning safety guard.
    # Important: Scene Director regional conditioning is intentionally NOT treated as
    # batch-unsafe by itself. We only collapse batch for known unsafe source-image,
    # preview-action, detector, FaceID, or single-control-image routes.
    batch_guard_reasons: list[str] = []
    if mode in {'img2img', 'inpaint', 'outpaint'}:
        batch_guard_reasons.append(f'{mode}_source_image_single')
    if bool(payload.get('_neo_preview_action')) or str(payload.get('_neo_workflow_command') or '').strip().lower() in {'preview_action', 'preview_upscale', 'selective_repair'}:
        batch_guard_reasons.append('preview_action_single_output')
    if detailer_units or bool(payload.get('detailer_output_pass')):
        batch_guard_reasons.append('impact_detailer_single_image')
    if any(str((unit or {}).get('mode') or '').strip().lower() == 'faceid' for unit in ipadapter_units):
        batch_guard_reasons.append('ipadapter_faceid_single_image')
    # ControlNet can be batch-safe only when the graph explicitly repeats/aligns the
    # control map to latent batch size. The current Neo ControlNet lane accepts a single
    # control image, so clamp until an explicit repeat/batch mode exists.
    if controlnet_units and batch_size > 1:
        batch_guard_reasons.append('controlnet_single_control_image')

    if batch_guard_reasons and batch_size > 1:
        batch_size = 1
        payload['_neo_batch_guard_applied'] = True
        payload['_neo_batch_guard_reason'] = '+'.join(dict.fromkeys(batch_guard_reasons))
        payload['_neo_requested_batch_size'] = requested_batch_size
        payload['_neo_effective_batch_size'] = batch_size
        payload['_neo_scene_director_batch_policy'] = 'preserve_unless_other_batch_unsafe_feature'
        compile_notes.append(
            'Batch safety guard forced batch size 1 · reason: '
            + payload['_neo_batch_guard_reason'].replace('_', ' ')
            + '.'
        )
    elif scene_director_requested and mode == 'txt2img' and batch_size > 1:
        # Phase 3/8: Scene Director regional conditioning is batch-safe in the existing txt2img lane.
        # Do not collapse batch just because Scene Director is enabled.
        payload['_neo_batch_guard_applied'] = False
        payload['_neo_batch_guard_reason'] = 'scene_director_txt2img_batch_preserved'
        payload['_neo_requested_batch_size'] = requested_batch_size
        payload['_neo_effective_batch_size'] = batch_size
        payload['_neo_scene_director_batch_policy'] = 'preserve'
        compile_notes.append(f'Scene Director txt2img batch preserved · batch_size={batch_size}.')
    else:
        payload['_neo_batch_guard_applied'] = False
        payload['_neo_batch_guard_reason'] = ''
        payload['_neo_requested_batch_size'] = requested_batch_size
        payload['_neo_effective_batch_size'] = batch_size
        payload['_neo_scene_director_batch_policy'] = 'not_applicable_or_single'
    if qwen_mode:
        compile_notes.append('Qwen GGUF path is mirroring the known-good Rapid AIO graph: GGUF UNet + GGUF text encoder + mmproj sidecar + Qwen image-conditioning node + EmptyLatentImage sampler input.')
        if str(payload.get('model_source') or '').strip().lower() != 'gguf':
            compile_notes.append('Qwen family forced the GGUF route even though the incoming payload still said checkpoint.')
    if bool(payload.get('refine_enabled')):
        refine_mode_note = str(payload.get('refine_mode') or 'latent').strip().replace('_', ' ')
        compile_notes.append(f'Upscale Lab enabled ({refine_mode_note}).')
        if qwen_reedit_source_only:
            compile_notes.append('Upscale Lab source-only mode is active: skipping the main Qwen pass and starting the re-edit from the selected output image.')
        elif image_upscale_source_only:
            compile_notes.append('Upscale Lab source-only mode is active: reusing the selected output image directly for the preserve-first upscale pass and skipping the base sampler redraw.')
    if qwen_fast_defaults:
        compile_notes.append('Qwen fast-model defaults engaged (CFG 1 · 4 steps).')
    if lanpaint_route_requested:
        compile_notes.append(f"LanPaint sampler policy active: {lanpaint_policy.get('policy') or 'family-specific policy'}")
        requested_sampler = normalize_sampler_name(payload.get('sampler') or default_sampler)
        requested_scheduler = normalize_scheduler_name(payload.get('scheduler') or default_scheduler)
        compile_notes.append(f'LanPaint requested sampler: {requested_sampler} / {requested_scheduler}.')
        compile_notes.append(f'LanPaint effective sampler: {sampler_name} / {scheduler_name}.')
        if requested_sampler != sampler_name or requested_scheduler != scheduler_name:
            compile_notes.append(f'LanPaint auto-fix visible: {requested_sampler} / {requested_scheduler} → {sampler_name} / {scheduler_name}.')
        compile_notes.extend(lanpaint_policy_notes)
    if prompt_conditioning_mode != 'raw':
        compile_notes.append(f'Prompt conditioning: {prompt_conditioning_mode.replace("_", " ")}.')
    if clip_skip > 1 and clip_skip_supported:
        compile_notes.append(f'Clip skip {clip_skip} enabled for prompt encoding.')
    elif clip_skip > 1 and not clip_skip_supported:
        compile_notes.append('Clip skip was requested, but the current model family ignores it here.')
    if bool(payload.get('supir_enabled')):
        compile_notes.append('SUPIR restoration upscale is enabled as a final optional image pass.')
    if mode == 'inpaint':
        composition_row = (inpaint_payload.get('composition') or {}) if isinstance(inpaint_payload, dict) else {}
        source_images_row = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
        compile_notes.append(f"Inpaint target: {inpaint_target.replace('_', ' ')} · context: {inpaint_context.replace('_', ' ')}.")
        compile_notes.append(f"Shared inpaint payload active · backend {inpaint_payload.get('backend') or 'standard'} · guide {composition_row.get('guide_type') or 'none'} · source {composition_row.get('source_mode') or 'source_image'}.")
        if sdxl_standard_inpaint:
            compile_notes.append('SDXL inpaint branch: standard latent mask path active.')
        if qwen_mode:
            if str(source_images_row.get('reference_image_2_name') or '').strip():
                compile_notes.append('Qwen inpaint multi-image conditioning: image2 reference is active.')
            if str(source_images_row.get('composition_image_name') or '').strip() or str(composition_row.get('source_mode') or '').strip() == 'source_image':
                chosen = 'composition image' if str(composition_row.get('source_mode') or '').strip() == 'composition_image' else 'base image'
                compile_notes.append(f'Qwen inpaint composition slot wired: image3 now follows the {chosen} path.')
                guide_kind = str(composition_row.get('guide_type') or 'none').strip().lower()
                if guide_kind in {'depth', 'pose'}:
                    compile_notes.append(f'Qwen composition guide preprocessor active: {guide_kind}.')
        if qwen_mode and inpaint_backend == 'lanpaint':
            compile_notes.append('Qwen base inpaint branch engaged: LanPaint sampler + grown / blurred mask + latent noise mask prep.')
        elif sdxl_lanpaint_inpaint:
            compile_notes.append('SDXL base inpaint branch engaged: LanPaint sampler + standard source/mask latent prep.')
    if mode == 'outpaint':
        composition_row = (inpaint_payload.get('composition') or {}) if isinstance(inpaint_payload, dict) else {}
        compile_notes.append(f"Outpaint padding L{outpaint_left} T{outpaint_top} R{outpaint_right} B{outpaint_bottom} · feather {outpaint_feather}.")
        compile_notes.append(f"Shared inpaint payload active · backend {inpaint_payload.get('backend') or 'standard'} · guide {composition_row.get('guide_type') or 'none'} · source {composition_row.get('source_mode') or 'source_image'}.")
    if len(lora_units) > 1:
        compile_notes.append(f'Queued {len(lora_units)} LoRA units in sequence.')
    base_only_lora_count = sum(1 for unit in lora_units if _normalize_pass_target(unit.get('target') or 'both', 'both') == 'base')
    finish_only_lora_count = sum(1 for unit in lora_units if _normalize_pass_target(unit.get('target') or 'both', 'both') == 'finish')
    if base_only_lora_count:
        compile_notes.append(f'{base_only_lora_count} LoRA unit(s) target the base pass only.')
    if finish_only_lora_count:
        compile_notes.append(f'{finish_only_lora_count} LoRA unit(s) target the finish / redraw pass only.')
    missing_control_images = sum(1 for unit in controlnet_units if unit.get('model') and not unit.get('image_name'))
    if missing_control_images:
        compile_notes.append(f'{missing_control_images} ControlNet unit(s) were missing control images and will be skipped.')
    missing_ipadapter_images = sum(1 for unit in ipadapter_units if not unit.get('clip_vision') or not (_normalize_ipadapter_image_names(unit)) or (str(unit.get('mode') or 'standard').strip().lower() != 'faceid' and not unit.get('model')))
    if len(ipadapter_units) > 1:
        compile_notes.append(f'Queued {len(ipadapter_units)} IPAdapter units in sequence.')
    elif ipadapter_units:
        compile_notes.append('Queued 1 IPAdapter unit.')
    multi_ref_count = sum(1 for unit in ipadapter_units if len(_normalize_ipadapter_image_names(unit)) > 1)
    if multi_ref_count:
        compile_notes.append(f'Multi-reference IPAdapter batching enabled on {multi_ref_count} unit(s).')
    faceid_count = sum(1 for unit in ipadapter_units if str(unit.get('mode') or 'standard').strip().lower() == 'faceid')
    if faceid_count:
        compile_notes.append(f'FaceID mode enabled on {faceid_count} IPAdapter unit(s).')
    if missing_ipadapter_images:
        compile_notes.append(f'{missing_ipadapter_images} IPAdapter unit(s) were missing a reference image, model, or CLIP Vision encoder and will be skipped.')
    if detailer_units:
        compile_notes.append(f'Queued {len(detailer_units)} experimental detailer pass(es) for Impact Pack.')

    graph: Dict[str, Any] = {}
    next_id = 1
    if model_source == 'gguf':
        if qwen_mode:
            graph[str(next_id)] = {
                'class_type': 'LoaderGGUF',
                'inputs': {
                    'gguf_name': gguf_unet,
                },
            }
            model_ref = [str(next_id), 0]
            next_id += 1
            graph[str(next_id)] = {
                'class_type': 'ClipLoaderGGUF',
                'inputs': {
                    'clip_name': gguf_clip_primary,
                    'type': gguf_clip_type,
                    'device': 'default',
                },
            }
        else:
            graph[str(next_id)] = {
                'class_type': 'UnetLoaderGGUF',
                'inputs': {
                    'unet_name': gguf_unet,
                },
            }
            model_ref = [str(next_id), 0]
            next_id += 1
            if gguf_clip_mode == 'dual':
                graph[str(next_id)] = {
                    'class_type': 'DualCLIPLoaderGGUF',
                    'inputs': {
                        'clip_name1': gguf_clip_primary,
                        'clip_name2': gguf_clip_secondary,
                        'type': gguf_clip_type,
                    },
                }
            else:
                graph[str(next_id)] = {
                    'class_type': 'CLIPLoaderGGUF',
                    'inputs': {
                        'clip_name': gguf_clip_primary,
                        'type': gguf_clip_type,
                    },
                }
        clip_ref = [str(next_id), 0]
        next_id += 1
        vae_ref = None
    else:
        graph = {
            '1': {
                'class_type': 'CheckpointLoaderSimple',
                'inputs': {
                    'ckpt_name': checkpoint,
                },
            },
        }
        next_id = 2
        model_ref = ['1', 0]
        clip_ref = ['1', 1]
        vae_ref = ['1', 2]

    payload['_neo_checkpoint_vae_ref'] = ['1', 2] if '1' in graph else None
    if vae_name:
        vae_is_gguf = vae_name.lower().endswith('.gguf')
        vae_loader_class = 'VaeGGUF' if vae_is_gguf else 'VAELoader'
        if vae_is_gguf and not qwen_mode:
            compile_notes.append('GGUF VAE routing engaged for the selected VAE asset.')
        graph[str(next_id)] = {
            'class_type': vae_loader_class,
            'inputs': {
                'vae_name': vae_name,
            },
        }
        vae_ref = [str(next_id), 0]
        payload['_neo_active_vae_name'] = vae_name
        payload['_neo_active_vae_ref'] = list(vae_ref)
        compile_notes.append(f'Explicit VAE loader added to workflow: {vae_name}.')
        next_id += 1
    else:
        payload['_neo_active_vae_name'] = ''
        payload['_neo_active_vae_ref'] = list(vae_ref) if vae_ref is not None else None
        compile_notes.append('No external VAE selected; workflow will decode with the checkpoint VAE.')

    if qwen_mode:
        next_id, qwen_image_refs = _prepare_qwen_conditioning_images(
            graph,
            next_id,
            payload,
            mode,
            outpaint_left=outpaint_left,
            outpaint_top=outpaint_top,
            outpaint_right=outpaint_right,
            outpaint_bottom=outpaint_bottom,
            outpaint_feather=outpaint_feather,
        )
        next_id, sampler_input, qwen_conditioning_base_ref = _build_qwen_sampler_input(
            graph,
            next_id,
            payload,
            mode,
            width=width,
            height=height,
            batch_size=batch_size,
            vae_ref=vae_ref,
            inpaint_target=inpaint_target,
            outpaint_left=outpaint_left,
            outpaint_top=outpaint_top,
            outpaint_right=outpaint_right,
            outpaint_bottom=outpaint_bottom,
            outpaint_feather=outpaint_feather,
        )
        if qwen_conditioning_base_ref is not None and qwen_image_refs:
            qwen_image_refs[0] = list(qwen_conditioning_base_ref)
    else:
        sampler_input = None

    root_model_ref = list(model_ref)
    root_clip_ref = list(clip_ref)
    flux_mode = model_source == 'gguf' and gguf_clip_type == 'flux'
    if clip_skip > 1 and clip_skip_supported and not flux_mode:
        next_id, root_clip_ref = _apply_clip_skip(graph, next_id, list(root_clip_ref), clip_skip)
    root_clip_ref = list(root_clip_ref)

    next_id, model_ref, clip_ref = _apply_lora_stack(graph, next_id, list(root_model_ref), list(root_clip_ref), _select_lora_units_for_pass(lora_units, 'base'))
    next_id, model_ref = _apply_ipadapter_stack(graph, next_id, model_ref, ipadapter_units)
    if flux_mode:
        next_id, model_ref = _apply_flux_sampling_patch(graph, next_id, model_ref, width, height)
    next_id, positive_ref, negative_ref = _encode_prompt_pair(
        graph,
        next_id,
        clip_ref,
        base_positive_text,
        base_negative_text,
        flux_mode=flux_mode,
        qwen_mode=qwen_mode,
        guidance=gguf_guidance,
        vae_ref=vae_ref,
        qwen_image_refs=qwen_image_refs,
        qwen_images_on_negative=True,
    )
    next_id, positive_ref, negative_ref = _apply_controlnet_stack(graph, next_id, positive_ref, negative_ref, vae_ref, controlnet_units)

    refine_model_ref = list(model_ref)
    refine_clip_ref = list(clip_ref)
    refine_positive_ref = list(positive_ref)
    refine_negative_ref = list(negative_ref)
    if bool(payload.get('refine_enabled')):
        next_id, refine_model_ref, refine_clip_ref = _apply_lora_stack(graph, next_id, list(root_model_ref), list(root_clip_ref), _select_lora_units_for_pass(lora_units, 'finish'))
        next_id, refine_model_ref = _apply_ipadapter_stack(graph, next_id, refine_model_ref, ipadapter_units)
        if flux_mode:
            next_id, refine_model_ref = _apply_flux_sampling_patch(graph, next_id, refine_model_ref, width, height)
        next_id, refine_positive_ref, refine_negative_ref = _encode_prompt_pair(
            graph,
            next_id,
            refine_clip_ref,
            refine_positive_text,
            refine_negative_text,
            flux_mode=flux_mode,
            qwen_mode=qwen_mode,
            guidance=gguf_guidance,
            vae_ref=vae_ref,
            qwen_image_refs=qwen_image_refs,
            qwen_images_on_negative=False,
        )
        next_id, refine_positive_ref, refine_negative_ref = _apply_controlnet_stack(graph, next_id, refine_positive_ref, refine_negative_ref, vae_ref, controlnet_units)

    detailer_output_pass = bool(payload.get('detailer_output_pass'))
    if detailer_output_pass:
        source_image = str(payload.get('source_image_name') or '').strip()
        if not source_image:
            raise ValueError('Selective Repair later pass needs a source image.')
        load_id = next_id
        graph[str(load_id)] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image,
                'upload': 'image',
            },
        }
        image_ref = [str(load_id), 0]
        next_id += 1
        active_model_ref = refine_model_ref if bool(payload.get('refine_enabled')) else model_ref
        active_clip_ref = refine_clip_ref if bool(payload.get('refine_enabled')) else clip_ref
        active_positive_ref = refine_positive_ref if bool(payload.get('refine_enabled')) else positive_ref
        active_negative_ref = refine_negative_ref if bool(payload.get('refine_enabled')) else negative_ref
        compile_notes.append('Selective Repair later pass is reusing the active output directly.')
    else:
        regional_sampler_complete = False

        if image_upscale_source_only:
            sampler_input = None
            latent_ref = None
        elif qwen_mode:
            sampler_input = list(sampler_input)
        elif mode == 'txt2img':
            latent_id = next_id
            graph[str(latent_id)] = {
                'class_type': 'EmptyLatentImage',
                'inputs': {
                    'width': width,
                    'height': height,
                    'batch_size': batch_size,
                },
            }
            next_id += 1
            sampler_input = [str(latent_id), 0]
        elif mode == 'img2img':
            source_image = str(payload.get('source_image_name') or '').strip()
            if not source_image:
                raise ValueError('Img2img needs a source image.')
            next_id, loaded_image_ref = _add_load_image_node(graph, next_id, source_image)
            encode_id = next_id
            graph[str(encode_id)] = {
                'class_type': 'VAEEncode',
                'inputs': {
                    'pixels': list(loaded_image_ref),
                    'vae': list(vae_ref),
                },
            }
            sampler_input = [str(encode_id), 0]
            next_id += 1
        elif mode == 'inpaint':
            standard_inpaint_inputs = _resolve_standard_inpaint_inputs(payload, inpaint_payload if isinstance(inpaint_payload, dict) else None)
            next_id, sampler_input, sdxl_inpaint_notes = _build_standard_sdxl_inpaint_sampler_input(
                graph,
                next_id,
                source_image=standard_inpaint_inputs['source_image'],
                mask_image=standard_inpaint_inputs['mask_image'],
                vae_ref=vae_ref,
                inpaint_target=inpaint_target,
                inpaint_context=inpaint_context,
                grow_mask_by=standard_inpaint_inputs['grow_mask_by'],
            )
            compile_notes.extend(sdxl_inpaint_notes)
        else:
            source_images_row = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
            source_image = str(source_images_row.get('base_image_name') or payload.get('source_image_name') or '').strip()
            next_id, sampler_input, sdxl_outpaint_notes = _build_standard_sdxl_outpaint_sampler_input(
                graph,
                next_id,
                source_image=source_image,
                vae_ref=vae_ref,
                outpaint_left=outpaint_left,
                outpaint_top=outpaint_top,
                outpaint_right=outpaint_right,
                outpaint_bottom=outpaint_bottom,
                outpaint_feather=outpaint_feather,
            )
            compile_notes.extend(sdxl_outpaint_notes)

        if qwen_reedit_source_only:
            if not qwen_image_refs:
                raise ValueError('Upscale Lab source-only mode needs a source image for Qwen re-edit.')
            encode_id = next_id
            graph[str(encode_id)] = {
                'class_type': 'VAEEncode',
                'inputs': {
                    'pixels': list(qwen_image_refs[0]),
                    'vae': list(vae_ref),
                },
            }
            latent_ref = [str(encode_id), 0]
            next_id += 1
        elif image_upscale_source_only:
            latent_ref = None
        else:
            next_id, model_ref, positive_ref, negative_ref, sampler_input, regional_notes, regional_sampler_complete = _apply_regional_prompting(
                graph,
                next_id,
                model_ref,
                positive_ref,
                negative_ref,
                clip_ref,
                vae_ref,
                sampler_input,
                payload,
                width,
                height,
                mode,
                seed,
                steps,
                cfg,
                sampler_name,
                scheduler_name,
                denoise,
            )
            compile_notes.extend(regional_notes)

            if regional_sampler_complete:
                if _normalize_dynamic_thresholding_settings(payload).get('enabled'):
                    compile_notes.append('Dynamic Thresholding skipped because regional prompting already completed the sampler.')
                latent_ref = list(sampler_input)
            else:
                next_id, model_ref, dynamic_thresholding_notes = _apply_dynamic_thresholding(
                    graph,
                    next_id,
                    model_ref,
                    payload,
                    family=family,
                    model_source=model_source,
                    gguf_clip_type=gguf_clip_type,
                    qwen_mode=qwen_mode,
                    cfg=cfg,
                    pass_label='base',
                )
                compile_notes.extend(dynamic_thresholding_notes)

                if mode == 'inpaint' and inpaint_backend == 'lanpaint':
                    if qwen_mode:
                        next_id, model_ref = _apply_qwen_sampling_patch(graph, next_id, model_ref)
                    sampler_id = next_id
                    lanpaint_inputs, lanpaint_input_notes = _build_lanpaint_ksampler_inputs(
                        payload=payload,
                        model_ref=model_ref,
                        positive_ref=positive_ref,
                        negative_ref=negative_ref,
                        sampler_input=sampler_input,
                        seed=seed,
                        steps=steps,
                        cfg=cfg,
                        sampler_name=sampler_name,
                        scheduler_name=scheduler_name,
                        denoise=denoise,
                    )
                    compile_notes.extend(lanpaint_input_notes)
                    graph[str(sampler_id)] = {
                        'class_type': 'LanPaint_KSampler',
                        'inputs': lanpaint_inputs,
                    }
                    latent_ref = [str(sampler_id), 0]
                    next_id += 1
                else:
                    sampler_id = next_id
                    graph[str(sampler_id)] = {
                        'class_type': 'KSampler',
                        'inputs': {
                            'seed': seed,
                            'steps': steps,
                            'cfg': cfg,
                            'sampler_name': sampler_name,
                            'scheduler': scheduler_name,
                            'denoise': denoise,
                            'model': list(model_ref),
                            'positive': list(positive_ref),
                            'negative': list(negative_ref),
                            'latent_image': list(sampler_input),
                        },
                    }
                    latent_ref = [str(sampler_id), 0]
                    next_id += 1

        if payload.get('scene_director_enabled') and payload.get('scene_director_lora_bindings'):
            next_id, latent_ref, scene_lora_notes = _apply_scene_director_regional_lora_passes(
                graph,
                next_id,
                latent_ref,
                model_ref,
                clip_ref,
                vae_ref,
                payload.get('_scene_director_v052_node_id'),
                payload,
                seed,
                steps,
                cfg,
                sampler_name,
                scheduler_name,
            )
            compile_notes.extend(scene_lora_notes)

        if bool(payload.get('refine_enabled')):
            next_id, refine_model_ref, dynamic_thresholding_refine_notes = _apply_dynamic_thresholding(
                graph,
                next_id,
                refine_model_ref,
                payload,
                family=family,
                model_source=model_source,
                gguf_clip_type=gguf_clip_type,
                qwen_mode=qwen_mode,
                cfg=cfg,
                pass_label='finish',
            )
            compile_notes.extend(dynamic_thresholding_refine_notes)

        next_id, latent_ref = _maybe_refine(
            graph, next_id, latent_ref, refine_model_ref, refine_positive_ref, refine_negative_ref, payload, seed, vae_ref,
            clip_ref=refine_clip_ref,
            positive_text=refine_positive_text,
            negative_text=refine_negative_text,
            qwen_mode=qwen_mode,
            guidance=gguf_guidance,
        )

        active_model_ref = refine_model_ref if bool(payload.get('refine_enabled')) else model_ref
        active_clip_ref = refine_clip_ref if bool(payload.get('refine_enabled')) else clip_ref
        active_positive_ref = refine_positive_ref if bool(payload.get('refine_enabled')) else positive_ref
        active_negative_ref = refine_negative_ref if bool(payload.get('refine_enabled')) else negative_ref

        direct_image_ref = payload.pop('_neo_refine_direct_image_ref', None)
        direct_image_mode = str(payload.pop('_neo_refine_direct_image_mode', '') or '').strip()
        if isinstance(direct_image_ref, (list, tuple)) and len(direct_image_ref) == 2:
            image_ref = [str(direct_image_ref[0]), int(direct_image_ref[1])]
            if direct_image_mode == 'ultimate_sd_upscale':
                compile_notes.append('Final image output is taken directly from UltimateSDUpscale to preserve native Comfy parity and avoid extra encode/decode drift.')
            else:
                compile_notes.append('Final image output is using a direct image ref from the refine stage.')
        else:
            decode_id = next_id
            graph[str(decode_id)] = {
                'class_type': 'VAEDecode',
                'inputs': {
                    'samples': list(latent_ref),
                    'vae': list(vae_ref),
                },
            }
            compile_notes.append(f'Final VAEDecode is wired to VAE node/output: {vae_ref[0]}:{vae_ref[1]}.')
            active_vae_name = str(payload.get('_neo_active_vae_name') or '').strip()
            if active_vae_name:
                compile_notes.append(f'Active workflow VAE consistency target: explicit asset {active_vae_name} on ref {vae_ref[0]}:{vae_ref[1]}.')
            else:
                compile_notes.append(f'Active workflow VAE consistency target: checkpoint VAE on ref {vae_ref[0]}:{vae_ref[1]}.')
            image_ref = [str(decode_id), 0]
            next_id += 1

    next_id, image_ref, detailer_notes = _apply_optional_detailers(
        graph,
        next_id,
        image_ref,
        active_model_ref,
        active_clip_ref,
        vae_ref,
        payload,
        seed,
        cfg,
        sampler_name,
        scheduler_name,
        active_positive_ref,
        active_negative_ref,
    )
    compile_notes.extend(detailer_notes)

    next_id, image_ref, supir_notes = _maybe_supir(graph, next_id, image_ref, payload, seed)
    compile_notes.extend(supir_notes)

    next_id, _saved_image_ref = _add_save_image_node(graph, next_id, image_ref, prefix='NeoStudio')

    normalized_payload = {
        **payload,
        'mode': mode,
        'seed': str(seed),
        'width': width,
        'height': height,
        'steps': steps,
        'cfg': cfg,
        'batch_size': batch_size,
        'denoise': denoise,
        'sampler': sampler_name,
        'scheduler': scheduler_name,
        '_neo_effective_mode': payload.get('_neo_effective_mode') or mode,
        '_neo_effective_family': payload.get('_neo_effective_family') or family,
        '_neo_effective_model_source': payload.get('_neo_effective_model_source') or model_source,
        '_neo_effective_inpaint_backend': payload.get('_neo_effective_inpaint_backend') or inpaint_backend,
        '_neo_effective_lanpaint_route': bool(payload.get('_neo_effective_lanpaint_route')),
        '_neo_effective_qwen_route': bool(payload.get('_neo_effective_qwen_route')),
        '_neo_scene_director_applied': bool(payload.get('_neo_scene_director_applied')),
        '_neo_scene_director_skip_reason': payload.get('_neo_scene_director_skip_reason') or '',
        '_neo_state_hygiene_phase': payload.get('_neo_state_hygiene_phase') or 'phase9_effective_compile_contract_v1',
        'gguf_clip_mode': gguf_clip_mode,
        'gguf_clip_type': gguf_clip_type,
        'outpaint_left': outpaint_left,
        'outpaint_top': outpaint_top,
        'outpaint_right': outpaint_right,
        'outpaint_bottom': outpaint_bottom,
        'outpaint_feather': outpaint_feather,
    }
    return graph, normalized_payload, compile_notes


def _infer_upscale_model_native_scale(model_name: str) -> float:
    name = str(model_name or '').strip().lower()
    match = re.search(r'(?<!\d)(\d+(?:\.\d+)?)x(?!\d)', name)
    if not match:
        return 1.0
    try:
        value = float(match.group(1))
    except Exception:
        value = 1.0
    return max(0.1, min(value, 16.0))


def build_image_upscale_workflow(payload: Dict[str, Any]):
    source_image_name = str(payload.get('source_image_name') or '').strip()
    if not source_image_name:
        raise ValueError('Image Upscale needs a source image.')

    upscale_model = str(payload.get('image_upscale_model') or '').strip()
    resize_method = str(payload.get('image_upscale_resize_method') or 'lanczos').strip().lower()
    if resize_method not in {'nearest-exact', 'bilinear', 'area', 'bicubic', 'lanczos'}:
        resize_method = 'lanczos'
    scale_by = _clamp_float(payload.get('image_upscale_scale') or 2.0, 2.0, 0.25, 8.0)

    restore_assist = str(payload.get('image_upscale_restore_assist') or 'off').strip().lower()
    if restore_assist not in {'off', 'codeformer'}:
        restore_assist = 'off'
    restore_model = str(payload.get('image_upscale_restore_model') or '').strip()
    restore_fidelity = _clamp_float(payload.get('image_upscale_restore_fidelity') or 0.65, 0.65, 0.0, 1.0)
    restore_detection = str(payload.get('image_upscale_restore_detection') or 'retinaface_resnet50').strip() or 'retinaface_resnet50'

    graph: Dict[str, Any] = {}
    compile_notes: list[str] = []
    builder_contract = _normalize_workflow_builder_contract(payload, builder_name='image_upscale', mode='image_upscale_finish', source_image_name=source_image_name)
    _attach_builder_contract(payload, builder_contract, compile_notes)
    next_id = 1

    next_id, current_image_ref = _add_load_image_node(graph, next_id, source_image_name)

    if upscale_model:
        loader_id = next_id
        graph[str(loader_id)] = {
            'class_type': 'UpscaleModelLoader',
            'inputs': {'model_name': upscale_model},
        }
        upscale_id = next_id + 1
        graph[str(upscale_id)] = {
            'class_type': 'ImageUpscaleWithModel',
            'inputs': {
                'upscale_model': [str(loader_id), 0],
                'image': list(current_image_ref),
            },
        }
        current_image_ref = [str(upscale_id), 0]
        next_id += 2
        native_scale = _infer_upscale_model_native_scale(upscale_model)
        extra_scale = scale_by / native_scale if native_scale > 0 else scale_by
        if abs(extra_scale - 1.0) > 0.01:
            rescale_id = next_id
            graph[str(rescale_id)] = {
                'class_type': 'ImageScaleBy',
                'inputs': {
                    'image': list(current_image_ref),
                    'upscale_method': resize_method,
                    'scale_by': max(0.05, min(extra_scale, 8.0)),
                },
            }
            current_image_ref = [str(rescale_id), 0]
            next_id += 1
        compile_notes.append(f'Image Upscale will use {upscale_model} with a target scale of {scale_by}x.')
    else:
        scale_id = next_id
        graph[str(scale_id)] = {
            'class_type': 'ImageScaleBy',
            'inputs': {
                'image': list(current_image_ref),
                'upscale_method': resize_method,
                'scale_by': scale_by,
            },
        }
        current_image_ref = [str(scale_id), 0]
        next_id += 1
        compile_notes.append(f'Image Upscale will use interpolation-only resize at {scale_by}x ({resize_method}).')

    if restore_assist == 'codeformer' and restore_model:
        loader_id = next_id
        graph[str(loader_id)] = {
            'class_type': 'FaceRestoreModelLoader',
            'inputs': {'model_name': restore_model},
        }
        restore_id = next_id + 1
        graph[str(restore_id)] = {
            'class_type': 'FaceRestoreCFWithModel',
            'inputs': {
                'facerestore_model': [str(loader_id), 0],
                'image': list(current_image_ref),
                'facedetection': restore_detection,
                'codeformer_fidelity': restore_fidelity,
            },
        }
        current_image_ref = [str(restore_id), 0]
        next_id += 2
        compile_notes.append(f'CodeFormer restore assist will run with {restore_model} at fidelity {restore_fidelity}.')
    elif restore_assist != 'off':
        compile_notes.append('Restore assist was requested, but Neo skipped it because no compatible restore model was selected.')

    next_id, _saved_image_ref = _add_save_image_node(graph, next_id, current_image_ref, prefix='NeoStudioUpscale')

    normalized_payload = {
        **payload,
        'mode': 'image_upscale_finish',
        'image_upscale_model': upscale_model,
        'image_upscale_scale': scale_by,
        'image_upscale_resize_method': resize_method,
        'image_upscale_restore_assist': restore_assist,
        'image_upscale_restore_model': restore_model,
        'image_upscale_restore_fidelity': restore_fidelity,
        'image_upscale_restore_detection': restore_detection,
        'batch_size': 1,
        'source_image_name': source_image_name,
    }
    return graph, normalized_payload, compile_notes


VIDEO_BALANCED_SIZE_PRESETS = {
    '832x480': (832, 480),
    '1024x576': (1024, 576),
    '576x1024': (576, 1024),
}


def _snap_video_dimension(value: Any, fallback: int) -> int:
    try:
        numeric = int(float(value))
    except Exception:
        numeric = int(fallback)
    numeric = max(256, min(2048, numeric))
    snapped = int(round(numeric / 16.0) * 16)
    return max(256, min(2048, snapped))


def _normalize_video_size_preset(value: Any, width_value: Any = None, height_value: Any = None) -> tuple[str, int, int]:
    clean = str(value or '832x480').strip().lower() or '832x480'
    if clean in {'custom', 'source_match', 'match_source', 'auto_source_fit', 'auto_best_fit'}:
        width = _snap_video_dimension(width_value or 832, 832)
        height = _snap_video_dimension(height_value or 480, 480)
        if clean in {'source_match', 'match_source'}:
            return 'source_match', width, height
        if clean in {'auto_source_fit', 'auto_best_fit'}:
            return 'auto_source_fit', width, height
        return 'custom', width, height
    width, height = VIDEO_BALANCED_SIZE_PRESETS.get(clean, VIDEO_BALANCED_SIZE_PRESETS['832x480'])
    return clean if clean in VIDEO_BALANCED_SIZE_PRESETS else '832x480', width, height




def _attach_native_video_resized_start_image(graph: Dict[str, Any], *, load_node_id: str, target_input_node_id: str, target_input_name: str, width: int, height: int, resize_node_id: str) -> None:
    graph[str(resize_node_id)] = {
        'class_type': 'ImageScale',
        'inputs': {
            'image': [str(load_node_id), 0],
            'upscale_method': 'lanczos',
            'width': int(width),
            'height': int(height),
            'crop': 'disabled',
        },
    }
    graph[str(target_input_node_id)]['inputs'][str(target_input_name)] = [str(resize_node_id), 0]

def _normalize_video_length_frames(duration_seconds: Any, fps: Any) -> int:
    seconds = _clamp_int(duration_seconds, 5, 1, 12)
    frame_rate = _clamp_int(fps, 16, 8, 24)
    raw = max(1, seconds * frame_rate)
    remainder = (raw - 1) % 4
    if remainder:
        raw += 4 - remainder
    return max(1, min(raw, 121))


def _normalize_video_advanced_adapter_payload(payload: Dict[str, Any]) -> dict[str, Any]:
    raw = payload.get('advanced_adapters') if isinstance(payload.get('advanced_adapters'), dict) else {}
    enabled_raw = raw.get('enabled') if 'enabled' in raw else payload.get('advanced_adapters_enabled') or payload.get('enable_adapters')
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    else:
        enabled = str(enabled_raw or '').strip().lower() in {'1', 'true', 'yes', 'on', 'enabled'}
    requested_profile = str(payload.get('profile') or '').strip().lower() or 'wan22_5b_balanced'
    adapter_mode = str(raw.get('mode') or raw.get('profile_mode') or ('paired' if requested_profile in {'wan22_14b_t2v_quality', 'wan22_14b_i2v_quality'} else 'single')).strip().lower() or 'single'
    return {
        'enabled': bool(enabled),
        'mode': adapter_mode,
        'profile_mode': adapter_mode,
        'pair_preset_id': str(raw.get('pair_preset_id') or payload.get('adapter_pair_preset_id') or '').strip() if adapter_mode == 'paired' else '',
        'pair_preset_name': str(raw.get('pair_preset_name') or payload.get('adapter_pair_preset_name') or '').strip() if adapter_mode == 'paired' else '',
        'single_adapter': str(raw.get('single_adapter') or raw.get('adapter') or raw.get('adapter_name') or raw.get('lora_name') or payload.get('adapter_single') or payload.get('single_adapter') or payload.get('adapter_name') or payload.get('lora_name') or '').strip() if adapter_mode == 'single' else '',
        'high_noise_adapter': str(raw.get('high_noise_adapter') or raw.get('high_noise_name') or payload.get('adapter_high_noise') or payload.get('adapter_high_noise_name') or '').strip() if adapter_mode == 'paired' else '',
        'low_noise_adapter': str(raw.get('low_noise_adapter') or raw.get('low_noise_name') or payload.get('adapter_low_noise') or payload.get('adapter_low_noise_name') or '').strip() if adapter_mode == 'paired' else '',
        'strength': _clamp_float(raw.get('strength') if raw.get('strength') is not None else payload.get('adapter_strength') or 0.8, 0.8, 0.0, 2.0),
    }


def _apply_video_single_adapter(graph: Dict[str, Any], next_id: int, model_ref, lora_name: str, strength: float):
    clean_name = str(lora_name or '').strip()
    if not clean_name:
        return next_id, model_ref
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'LoraLoaderModelOnly',
        'inputs': {
            'model': list(model_ref),
            'lora_name': clean_name,
            'strength_model': round(float(strength or 0.8), 4),
        },
    }
    return next_id + 1, [str(node_id), 0]


def _apply_video_paired_adapter(graph: Dict[str, Any], next_id: int, model_ref, lora_name: str, strength: float):
    clean_name = str(lora_name or '').strip()
    if not clean_name:
        return next_id, model_ref
    node_id = next_id
    graph[str(node_id)] = {
        'class_type': 'LoraLoaderModelOnly',
        'inputs': {
            'model': list(model_ref),
            'lora_name': clean_name,
            'strength_model': round(float(strength or 0.8), 4),
        },
    }
    return next_id + 1, [str(node_id), 0]


def build_video_balanced_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    mode = str(payload.get('mode') or 't2v').strip().lower() or 't2v'
    if mode not in {'t2v', 'i2v'}:
        mode = 't2v'
    requested_profile = str(payload.get('profile') or 'wan22_5b_balanced').strip().lower() or 'wan22_5b_balanced'
    if requested_profile != 'wan22_5b_balanced':
        raise ValueError('Phase 2 only ships the Balanced / Low VRAM video path right now.')

    prompt = str(payload.get('prompt') or '').strip()
    if not prompt:
        raise ValueError('Prompt is required.')
    negative_prompt = str(payload.get('negative_prompt') or payload.get('negative') or '').strip()
    size_preset, width, height = _normalize_video_size_preset(payload.get('size_preset') or payload.get('size'), payload.get('width'), payload.get('height'))
    fps = _clamp_int(payload.get('fps'), 16, 8, 24)
    duration_seconds = _clamp_int(payload.get('duration_seconds') or payload.get('duration'), 5, 1, 12)
    length_frames = _normalize_video_length_frames(duration_seconds, fps)
    seed_value = parse_seed(payload.get('seed'))
    source_image_name = str(payload.get('source_image_name') or '').strip()
    advanced_adapters = _normalize_video_advanced_adapter_payload(payload)
    if advanced_adapters['enabled'] and not advanced_adapters.get('single_adapter'):
        raise ValueError('Balanced video adapters need one LoRA / adapter selected.')
    if mode == 'i2v' and not source_image_name:
        raise ValueError('Image to Video needs a source image upload for the balanced workflow.')

    graph: Dict[str, Any] = {
        '1': _video_unet_loader_node(
            payload.get('unet_name') or 'wan2.2_ti2v_5B_fp16.safetensors',
            payload.get('weight_dtype') or 'default',
        ),
        '2': _wan_video_clip_loader_node(
            payload.get('clip_name') or 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
            payload.get('clip_device') or 'default',
        ),
        '3': {
            'class_type': 'VAELoader',
            'inputs': {
                'vae_name': str(payload.get('vae_name') or 'wan2.2_vae.safetensors').strip(),
            },
        },
        '4': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': prompt,
                'clip': ['2', 0],
            },
        },
        '5': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': negative_prompt or 'blurry, low quality, jpeg artifacts, static shot, duplicate subjects, warped anatomy, flicker',
                'clip': ['2', 0],
            },
        },
        '6': {
            'class_type': 'ModelSamplingSD3',
            'inputs': {
                'model': ['1', 0],
                'shift': float(payload.get('sampling_shift') or 8),
            },
        },
        '7': {
            'class_type': 'Wan22ImageToVideoLatent',
            'inputs': {
                'vae': ['3', 0],
                'width': width,
                'height': height,
                'length': length_frames,
                'batch_size': 1,
            },
        },
        '8': {
            'class_type': 'KSampler',
            'inputs': {
                'model': ['6', 0],
                'seed': seed_value,
                'steps': _clamp_int(payload.get('steps'), 20, 8, 40),
                'cfg': _clamp_float(payload.get('cfg'), 5.0, 1.0, 10.0),
                'sampler_name': normalize_sampler_name(str(payload.get('sampler_name') or 'uni_pc')),
                'scheduler': normalize_scheduler_name(str(payload.get('scheduler') or 'simple')),
                'positive': ['4', 0],
                'negative': ['5', 0],
                'latent_image': ['7', 0],
                'denoise': 1.0,
            },
        },
        '9': {
            'class_type': 'VAEDecode',
            'inputs': {
                'samples': ['8', 0],
                'vae': ['3', 0],
            },
        },
        '10': {
            'class_type': 'CreateVideo',
            'inputs': {
                'images': ['9', 0],
                'fps': float(fps),
            },
        },
        '11': {
            'class_type': 'SaveVideo',
            'inputs': {
                'video': ['10', 0],
                'filename_prefix': str(payload.get('filename_prefix') or 'video/NeoStudioBalanced').strip() or 'video/NeoStudioBalanced',
                'format': str(payload.get('video_format') or 'auto').strip() or 'auto',
                'codec': str(payload.get('video_codec') or 'auto').strip() or 'auto',
            },
        },
    }

    if mode == 'i2v':
        graph['12'] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image_name,
                'upload': 'image',
            },
        }
        _attach_native_video_resized_start_image(graph, load_node_id='12', target_input_node_id='7', target_input_name='start_image', width=width, height=height, resize_node_id='13')

    balanced_model_ref = ['1', 0]
    next_id = max(int(key) for key in graph.keys()) + 1
    if advanced_adapters['enabled']:
        next_id, balanced_model_ref = _apply_video_single_adapter(graph, next_id, balanced_model_ref, advanced_adapters.get('single_adapter') or '', advanced_adapters.get('strength') or 0.8)
    graph['6']['inputs']['model'] = list(balanced_model_ref)

    _assert_wan_native_video_loader_graph(graph)

    normalized_payload = {
        **payload,
        'surface': 'video',
        'family': 'wan22',
        'workflow_type': 'video_balanced',
        'mode': mode,
        'profile': 'wan22_5b_balanced',
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'duration_seconds': duration_seconds,
        'fps': fps,
        'size_preset': size_preset,
        'width': width,
        'height': height,
        'video_length_frames': length_frames,
        'seed': str(payload.get('seed') or '').strip(),
        'seed_value': seed_value,
        'steps': _clamp_int(payload.get('steps'), 20, 8, 40),
        'cfg': _clamp_float(payload.get('cfg'), 5.0, 1.0, 10.0),
        'sampler_name': normalize_sampler_name(str(payload.get('sampler_name') or 'uni_pc')),
        'scheduler': normalize_scheduler_name(str(payload.get('scheduler') or 'simple')),
        'source_image_name': source_image_name,
        'advanced_adapters': advanced_adapters,
        'uses_gguf_unet': _is_video_gguf_unet_name(payload.get('unet_name') or 'wan2.2_ti2v_5B_fp16.safetensors'),
    }

    compile_notes = [
        f'Balanced video uses Wan 2.2 TI2V 5B with {width}x{height} at {fps} FPS.',
        f'Neo rounded the latent length to {length_frames} frames for Wan 2.2 compatibility.',
        'Low-VRAM defaults stay conservative here: 20 steps, CFG 5, uni_pc, simple scheduler.',
    ]
    compile_notes.append('Wan-native encoder routing is locked to CLIPLoader type=wan for Balanced video runs.')
    if normalized_payload['uses_gguf_unet']:
        compile_notes.append('Balanced UNet routing switched to UnetLoaderGGUF because the selected Wan model is a GGUF file.')
    if advanced_adapters['enabled'] and advanced_adapters.get('single_adapter'):
        compile_notes.append(f"Balanced adapter load: {advanced_adapters.get('single_adapter')} at strength {advanced_adapters.get('strength') or 0.8}.")
    if mode == 'i2v':
        compile_notes.append('The balanced I2V path is anchoring motion from the uploaded source image.')
    else:
        compile_notes.append('The balanced T2V path is running prompt-only generation with no start image.')
    return graph, normalized_payload, compile_notes


def _normalize_video_quality_length_frames(duration_seconds: Any, fps: Any) -> int:
    seconds = max(1, _clamp_int(duration_seconds, 5, 1, 30))
    frame_rate = max(8, _clamp_int(fps, 16, 8, 30))
    return max(1, min(int(seconds * frame_rate) + 1, 241))


def _normalize_video_quality_steps(value: Any, default: int = 20) -> int:
    return _clamp_int(value, default, 12, 40)


def _normalize_video_quality_split_step(value: Any, steps: int) -> int:
    default_split = max(2, steps // 2)
    return _clamp_int(value, default_split, 1, max(1, steps - 1))


def _build_quality_video_prompt(payload: Dict[str, Any]) -> str:
    return _merge_prompt_parts(
        payload.get('prompt') or '',
        payload.get('quality_style_prompt') or '',
        payload.get('quality_camera_prompt') or '',
    ).strip()


def _is_video_gguf_unet_name(value: Any) -> bool:
    clean = str(value or '').strip().lower()
    return clean.endswith('.gguf') or '.gguf' in clean


def _video_unet_loader_node(unet_name: Any, weight_dtype: Any = 'default') -> Dict[str, Any]:
    clean_name = str(unet_name or '').strip()
    if _is_video_gguf_unet_name(clean_name):
        return {
            'class_type': 'UnetLoaderGGUF',
            'inputs': {
                'unet_name': clean_name,
            },
        }
    return {
        'class_type': 'UNETLoader',
        'inputs': {
            'unet_name': clean_name,
            'weight_dtype': str(weight_dtype or 'default').strip() or 'default',
        },
    }


def _wan_video_clip_loader_node(clip_name: Any, device: Any = 'default') -> Dict[str, Any]:
    return {
        'class_type': 'CLIPLoader',
        'inputs': {
            'clip_name': str(clip_name or 'umt5_xxl_fp8_e4m3fn_scaled.safetensors').strip() or 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
            'type': 'wan',
            'device': str(device or 'default').strip() or 'default',
        },
    }


def _assert_wan_native_video_loader_graph(graph: Dict[str, Any]) -> None:
    clip_nodes = [node for node in (graph or {}).values() if isinstance(node, dict) and str(node.get('class_type') or '').strip() == 'CLIPLoader']
    if not clip_nodes:
        raise ValueError('Wan-native video workflows require a CLIPLoader node.')
    for node in clip_nodes:
        inputs = node.get('inputs') if isinstance(node.get('inputs'), dict) else {}
        clip_name = str(inputs.get('clip_name') or '').strip()
        clip_type = str(inputs.get('type') or '').strip().lower()
        if not clip_name:
            raise ValueError('Wan-native video workflows require a text encoder selection before queueing.')
        if clip_type != 'wan':
            raise ValueError('Wan-native video workflows must route the text encoder through CLIPLoader type="wan".')





def _is_kijai_wrapper_encoder_name(value: Any) -> bool:
    clean = str(value or '').strip().lower()
    if not clean:
        return False
    if 'umt5-xxl-enc' in clean:
        return True
    return 'umt5' in clean and 'scaled' not in clean and ('enc' in clean or 'wanvideo' in clean)


def _wrapper_text_encoder_quantization(value: Any) -> str:
    clean = str(value or '').strip().lower()
    return 'fp8_e4m3fn' if 'fp8_e4m3fn' in clean else 'disabled'


def _wrapper_scheduler_name(value: Any) -> str:
    clean = str(value or '').strip().lower()
    aliases = {
        'uni_pc': 'unipc',
        'uni_pc_bh2': 'unipc',
        'simple': 'unipc',
        'normal': 'unipc',
        'sgm_uniform': 'unipc',
    }
    mapped = aliases.get(clean, clean or 'unipc')
    return mapped or 'unipc'


def build_video_balanced_wrapper_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    mode = str(payload.get('mode') or 't2v').strip().lower() or 't2v'
    if mode not in {'t2v', 'i2v'}:
        mode = 't2v'
    requested_profile = str(payload.get('profile') or 'wan22_5b_balanced').strip().lower() or 'wan22_5b_balanced'
    if requested_profile not in {'wan22_5b_balanced', 'raw_free'}:
        raise ValueError('Kijai Wrapper routing is currently limited to the Balanced / Low VRAM or Raw / Free video profiles in this build.')

    prompt = str(payload.get('prompt') or '').strip()
    if not prompt:
        raise ValueError('Prompt is required.')
    negative_prompt = str(payload.get('negative_prompt') or payload.get('negative') or '').strip()
    size_preset, width, height = _normalize_video_size_preset(payload.get('size_preset') or payload.get('size'), payload.get('width'), payload.get('height'))
    fps = _clamp_int(payload.get('fps'), 16, 8, 24)
    duration_seconds = _clamp_int(payload.get('duration_seconds') or payload.get('duration'), 5, 1, 12)
    length_frames = _normalize_video_length_frames(duration_seconds, fps)
    seed_value = parse_seed(payload.get('seed'))
    steps = _clamp_int(payload.get('steps'), 20, 6, 40)
    cfg = _clamp_float(payload.get('cfg'), 5.0, 1.0, 10.0)
    shift = _clamp_float(payload.get('sampling_shift') or payload.get('shift'), 8.0, 0.0, 32.0)
    scheduler = _wrapper_scheduler_name(payload.get('scheduler') or payload.get('scheduler_name'))
    source_image_name = str(payload.get('source_image_name') or '').strip()
    advanced_adapters = _normalize_video_advanced_adapter_payload(payload)
    if advanced_adapters['enabled']:
        raise ValueError('Balanced Kijai Wrapper routing in this build does not support Neo adapter injection yet. Disable LoRAs / adapters, then retry.')
    if mode == 'i2v' and not source_image_name:
        raise ValueError('Image to Video needs a source image upload for the Kijai Wrapper workflow.')

    encoder_name = str(payload.get('clip_name') or 'umt5-xxl-enc-fp8_e4m3fn.safetensors').strip()
    if not encoder_name:
        raise ValueError('Balanced text encoder is required before queueing the Kijai Wrapper workflow.')
    graph: Dict[str, Any] = {
        '1': {
            'class_type': 'WanVideoModelLoader',
            'inputs': {
                'model': str(payload.get('unet_name') or 'wan2.2_ti2v_5B_fp16.safetensors').strip(),
                'base_precision': 'fp16',
                'quantization': 'disabled',
                'load_device': 'offload_device',
                'attention_mode': 'sdpa',
                'rms_norm_function': 'default',
            },
        },
        '2': {
            'class_type': 'WanVideoVAELoader',
            'inputs': {
                'model_name': str(payload.get('vae_name') or 'wan2.2_vae.safetensors').strip(),
                'precision': 'fp16',
                'use_cpu_cache': False,
                'verbose': False,
            },
        },
        '3': {
            'class_type': 'WanVideoTextEncodeCached',
            'inputs': {
                'model_name': encoder_name,
                'precision': 'bf16',
                'positive_prompt': prompt,
                'negative_prompt': negative_prompt or 'blurry, low quality, jpeg artifacts, static shot, duplicate subjects, warped anatomy, flicker',
                'quantization': _wrapper_text_encoder_quantization(encoder_name),
                'use_disk_cache': False,
                'device': 'gpu',
            },
        },
        '6': {
            'class_type': 'WanVideoSampler',
            'inputs': {
                'model': ['1', 0],
                'image_embeds': ['4', 0],
                'text_embeds': ['3', 0],
                'steps': steps,
                'cfg': cfg,
                'shift': shift,
                'seed': seed_value,
                'force_offload': True,
                'scheduler': scheduler,
                'riflex_freq_index': 0,
            },
        },
        '7': {
            'class_type': 'WanVideoDecode',
            'inputs': {
                'vae': ['2', 0],
                'samples': ['6', 0],
                'enable_vae_tiling': False,
                'tile_x': 272,
                'tile_y': 272,
                'tile_stride_x': 144,
                'tile_stride_y': 128,
                'normalization': 'default',
            },
        },
        '8': {
            'class_type': 'CreateVideo',
            'inputs': {
                'images': ['7', 0],
                'fps': float(fps),
            },
        },
        '9': {
            'class_type': 'SaveVideo',
            'inputs': {
                'video': ['8', 0],
                'filename_prefix': str(payload.get('filename_prefix') or 'video/NeoStudioBalancedWrapper').strip() or 'video/NeoStudioBalancedWrapper',
                'format': str(payload.get('video_format') or 'auto').strip() or 'auto',
                'codec': str(payload.get('video_codec') or 'auto').strip() or 'auto',
            },
        },
    }

    if mode == 'i2v':
        graph['4'] = {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image_name,
                'upload': 'image',
            },
        }
        graph['5'] = {
            'class_type': 'WanVideoImageToVideoEncode',
            'inputs': {
                'width': width,
                'height': height,
                'num_frames': length_frames,
                'noise_aug_strength': 0.0,
                'start_latent_strength': 1.0,
                'end_latent_strength': 1.0,
                'force_offload': True,
                'vae': ['2', 0],
                'start_image': ['10', 0],
                'fun_or_fl2v_model': False,
                'tiled_vae': False,
                'augment_empty_frames': 0.0,
            },
        }
        graph['10'] = {
            'class_type': 'ImageScale',
            'inputs': {
                'image': ['4', 0],
                'upscale_method': 'lanczos',
                'width': width,
                'height': height,
                'crop': 'disabled',
            },
        }
        graph['6']['inputs']['image_embeds'] = ['5', 0]
    else:
        graph['4'] = {
            'class_type': 'WanVideoEmptyEmbeds',
            'inputs': {
                'width': width,
                'height': height,
                'num_frames': length_frames,
            },
        }

    normalized_payload = {
        **payload,
        'surface': 'video',
        'family': 'wan22',
        'workflow_type': 'video_balanced',
        'video_backend_engine': 'kijai_wrapper',
        'mode': mode,
        'profile': 'wan22_5b_balanced',
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'duration_seconds': duration_seconds,
        'fps': fps,
        'size_preset': size_preset,
        'width': width,
        'height': height,
        'video_length_frames': length_frames,
        'seed': str(payload.get('seed') or '').strip(),
        'seed_value': seed_value,
        'steps': steps,
        'cfg': cfg,
        'sampling_shift': shift,
        'scheduler': scheduler,
        'source_image_name': source_image_name,
        'advanced_adapters': advanced_adapters,
        'compiled_prompt': prompt,
    }

    compile_notes = [
        f'Balanced video uses the Kijai WanVideoWrapper path with {width}x{height} at {fps} FPS.',
        f'Neo rounded the latent length to {length_frames} frames for wrapper compatibility.',
        f'Wrapper text encoding is routed through {encoder_name}.',
        'This route skips the native CLIPLoader type="wan" stack and uses the wrapper T5 text encoder path instead.',
    ]
    if mode == 'i2v':
        compile_notes.append('Balanced I2V is anchored through WanVideoImageToVideoEncode in the wrapper path.')
    return graph, normalized_payload, compile_notes

def build_video_quality_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    mode = str(payload.get('mode') or 't2v').strip().lower() or 't2v'
    requested_profile = str(payload.get('profile') or '').strip().lower()
    if requested_profile in {'wan22_14b_t2v_quality', 'raw_free'} and mode == 't2v':
        return _build_video_quality_t2v_workflow(payload)
    if requested_profile in {'wan22_14b_i2v_quality', 'raw_free'} and mode == 'i2v':
        return _build_video_quality_i2v_workflow(payload)
    raise ValueError('The selected profile is not a runnable Wan 2.2 quality video profile.')


def _build_video_quality_t2v_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    prompt = _build_quality_video_prompt(payload)
    if not prompt:
        raise ValueError('Prompt is required.')
    negative_prompt = str(payload.get('negative_prompt') or payload.get('negative') or '').strip()
    size_preset, width, height = _normalize_video_size_preset(payload.get('size_preset') or payload.get('size'), payload.get('width'), payload.get('height'))
    fps = _clamp_int(payload.get('fps'), 16, 8, 24)
    duration_seconds = _clamp_int(payload.get('duration_seconds') or payload.get('duration'), 5, 1, 18)
    length_frames = _normalize_video_quality_length_frames(duration_seconds, fps)
    seed_value = parse_seed(payload.get('seed'))
    steps = _normalize_video_quality_steps(payload.get('steps_quality') or payload.get('steps'), 20)
    split_step = _normalize_video_quality_split_step(payload.get('split_steps_quality') or payload.get('split_step'), steps)
    cfg = _clamp_float(payload.get('cfg_quality') or payload.get('cfg'), 3.5, 1.0, 8.0)
    sampler_name = normalize_sampler_name(str(payload.get('sampler_name_quality') or payload.get('sampler_name') or 'euler'))
    scheduler = normalize_scheduler_name(str(payload.get('scheduler_quality') or payload.get('scheduler') or 'simple'))
    advanced_adapters = _normalize_video_advanced_adapter_payload(payload)
    if advanced_adapters['enabled'] and (not advanced_adapters['high_noise_adapter'] or not advanced_adapters['low_noise_adapter']):
        raise ValueError('Paired video adapters need both the high-noise and low-noise slots filled.')

    graph: Dict[str, Any] = {
        '1': _video_unet_loader_node(
            payload.get('quality_high_noise_unet_name') or 'wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors',
            payload.get('quality_high_noise_weight_dtype') or 'default',
        ),
        '2': _video_unet_loader_node(
            payload.get('quality_low_noise_unet_name') or 'wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors',
            payload.get('quality_low_noise_weight_dtype') or 'default',
        ),
        '3': _wan_video_clip_loader_node(
            payload.get('clip_name_quality') or payload.get('clip_name') or 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
            payload.get('clip_device_quality') or payload.get('clip_device') or 'default',
        ),
        '4': {
            'class_type': 'VAELoader',
            'inputs': {
                'vae_name': str(payload.get('vae_name_quality') or payload.get('vae_name') or 'wan_2.1_vae.safetensors').strip(),
            },
        },
        '5': {
            'class_type': 'ModelSamplingSD3',
            'inputs': {
                'model': ['1', 0],
                'shift': float(payload.get('sampling_shift_quality') or payload.get('sampling_shift') or 5),
            },
        },
        '6': {
            'class_type': 'ModelSamplingSD3',
            'inputs': {
                'model': ['2', 0],
                'shift': float(payload.get('sampling_shift_quality') or payload.get('sampling_shift') or 5),
            },
        },
        '7': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': prompt,
                'clip': ['3', 0],
            },
        },
        '8': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': negative_prompt or 'overexposed, blurry, static, watermark, subtitle, extra limbs, deformed anatomy, duplicate subjects, flicker, flat gray image',
                'clip': ['3', 0],
            },
        },
        '9': {
            'class_type': 'EmptyHunyuanLatentVideo',
            'inputs': {
                'width': width,
                'height': height,
                'length': length_frames,
                'batch_size': 1,
            },
        },
        '10': {
            'class_type': 'KSamplerAdvanced',
            'inputs': {
                'model': ['5', 0],
                'add_noise': 'enable',
                'noise_seed': seed_value,
                'steps': steps,
                'cfg': cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler,
                'positive': ['7', 0],
                'negative': ['8', 0],
                'latent_image': ['9', 0],
                'start_at_step': 0,
                'end_at_step': split_step,
                'return_with_leftover_noise': 'enable',
            },
        },
        '11': {
            'class_type': 'KSamplerAdvanced',
            'inputs': {
                'model': ['6', 0],
                'add_noise': 'disable',
                'noise_seed': seed_value,
                'steps': steps,
                'cfg': cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler,
                'positive': ['7', 0],
                'negative': ['8', 0],
                'latent_image': ['10', 0],
                'start_at_step': split_step,
                'end_at_step': steps,
                'return_with_leftover_noise': 'disable',
            },
        },
        '12': {
            'class_type': 'VAEDecode',
            'inputs': {
                'samples': ['11', 0],
                'vae': ['4', 0],
            },
        },
        '13': {
            'class_type': 'CreateVideo',
            'inputs': {
                'images': ['12', 0],
                'fps': float(fps),
            },
        },
        '14': {
            'class_type': 'SaveVideo',
            'inputs': {
                'video': ['13', 0],
                'filename_prefix': str(payload.get('filename_prefix') or 'video/NeoStudioQualityT2V').strip() or 'video/NeoStudioQualityT2V',
                'format': str(payload.get('video_format') or 'auto').strip() or 'auto',
                'codec': str(payload.get('video_codec') or 'auto').strip() or 'auto',
            },
        },
    }

    high_noise_model_ref = ['1', 0]
    low_noise_model_ref = ['2', 0]
    next_id = max(int(key) for key in graph.keys()) + 1
    if advanced_adapters['enabled']:
        next_id, high_noise_model_ref = _apply_video_paired_adapter(graph, next_id, high_noise_model_ref, advanced_adapters['high_noise_adapter'], advanced_adapters['strength'])
        next_id, low_noise_model_ref = _apply_video_paired_adapter(graph, next_id, low_noise_model_ref, advanced_adapters['low_noise_adapter'], advanced_adapters['strength'])
    graph['9']['inputs']['model'] = list(high_noise_model_ref)
    graph['10']['inputs']['model'] = list(low_noise_model_ref)

    _assert_wan_native_video_loader_graph(graph)

    normalized_payload = {
        **payload,
        'surface': 'video',
        'family': 'wan22',
        'workflow_type': 'video_quality_t2v',
        'mode': 't2v',
        'profile': 'wan22_14b_t2v_quality',
        'prompt': str(payload.get('prompt') or '').strip(),
        'compiled_prompt': prompt,
        'negative_prompt': negative_prompt,
        'duration_seconds': duration_seconds,
        'fps': fps,
        'size_preset': size_preset,
        'width': width,
        'height': height,
        'video_length_frames': length_frames,
        'seed': str(payload.get('seed') or '').strip(),
        'seed_value': seed_value,
        'steps': steps,
        'split_step': split_step,
        'cfg': cfg,
        'sampler_name': sampler_name,
        'scheduler': scheduler,
        'quality_style_prompt': str(payload.get('quality_style_prompt') or '').strip(),
        'quality_camera_prompt': str(payload.get('quality_camera_prompt') or '').strip(),
        'heaviness': 'heavy',
        'advanced_adapters': advanced_adapters,
        'uses_gguf_high_noise_unet': _is_video_gguf_unet_name(payload.get('quality_high_noise_unet_name') or 'wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors'),
        'uses_gguf_low_noise_unet': _is_video_gguf_unet_name(payload.get('quality_low_noise_unet_name') or 'wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors'),
    }

    compile_notes = [
        f'High Quality T2V uses Wan 2.2 14B with separate high-noise and low-noise expert UNETs at {width}x{height} and {fps} FPS.',
        f'Neo split the {steps}-step schedule at step {split_step} so the low-noise expert can take over detail refinement.',
        'This path is intentionally heavier and slower than Balanced / Low VRAM. Backend-side offload or reduced output size may still be needed on constrained GPUs.',
    ]
    compile_notes.append('Wan-native encoder routing is locked to CLIPLoader type=wan for High Quality T2V runs.')
    if normalized_payload['uses_gguf_high_noise_unet'] or normalized_payload['uses_gguf_low_noise_unet']:
        compile_notes.append('High Quality T2V switched the selected Wan expert UNETs onto UnetLoaderGGUF wherever the chosen asset is a GGUF file.')
    if advanced_adapters['enabled']:
        compile_notes.append(f"Advanced adapters are enabled with a paired {advanced_adapters['strength']:.2f} strength load across the high-noise and low-noise experts.")
        if advanced_adapters.get('pair_preset_name') or advanced_adapters.get('pair_preset_id'):
            compile_notes.append(f"Adapter pair preset: {advanced_adapters.get('pair_preset_name') or advanced_adapters.get('pair_preset_id')}.")
    if duration_seconds > 5:
        compile_notes.append('This request is longer than the official 5s quality examples, so runtime and failure risk both go up.')
    return graph, normalized_payload, compile_notes


def _build_video_quality_i2v_workflow(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    prompt = _build_quality_video_prompt(payload)
    if not prompt:
        raise ValueError('Prompt is required.')
    negative_prompt = str(payload.get('negative_prompt') or payload.get('negative') or '').strip()
    size_preset, width, height = _normalize_video_size_preset(payload.get('size_preset') or payload.get('size'), payload.get('width'), payload.get('height'))
    fps = _clamp_int(payload.get('fps'), 16, 8, 24)
    duration_seconds = _clamp_int(payload.get('duration_seconds') or payload.get('duration'), 5, 1, 18)
    length_frames = _normalize_video_quality_length_frames(duration_seconds, fps)
    seed_value = parse_seed(payload.get('seed'))
    steps = _normalize_video_quality_steps(payload.get('steps_quality') or payload.get('steps'), 20)
    split_step = _normalize_video_quality_split_step(payload.get('split_steps_quality') or payload.get('split_step'), steps)
    cfg = _clamp_float(payload.get('cfg_quality') or payload.get('cfg'), 3.5, 1.0, 8.0)
    sampler_name = normalize_sampler_name(str(payload.get('sampler_name_quality') or payload.get('sampler_name') or 'euler'))
    scheduler = normalize_scheduler_name(str(payload.get('scheduler_quality') or payload.get('scheduler') or 'simple'))
    source_image_name = str(payload.get('source_image_name') or '').strip()
    advanced_adapters = _normalize_video_advanced_adapter_payload(payload)
    if advanced_adapters['enabled'] and (not advanced_adapters['high_noise_adapter'] or not advanced_adapters['low_noise_adapter']):
        raise ValueError('Paired video adapters need both the high-noise and low-noise slots filled.')
    if not source_image_name:
        raise ValueError('High Quality Image to Video needs a source image upload.')

    graph: Dict[str, Any] = {
        '1': _video_unet_loader_node(
            payload.get('quality_high_noise_unet_name') or 'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',
            payload.get('quality_high_noise_weight_dtype') or 'default',
        ),
        '2': _video_unet_loader_node(
            payload.get('quality_low_noise_unet_name') or 'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors',
            payload.get('quality_low_noise_weight_dtype') or 'default',
        ),
        '3': _wan_video_clip_loader_node(
            payload.get('clip_name_quality') or payload.get('clip_name') or 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
            payload.get('clip_device_quality') or payload.get('clip_device') or 'default',
        ),
        '4': {
            'class_type': 'VAELoader',
            'inputs': {
                'vae_name': str(payload.get('vae_name_quality') or payload.get('vae_name') or 'wan_2.1_vae.safetensors').strip(),
            },
        },
        '5': {
            'class_type': 'LoadImage',
            'inputs': {
                'image': source_image_name,
                'upload': 'image',
            },
        },
        '6': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': prompt,
                'clip': ['3', 0],
            },
        },
        '7': {
            'class_type': 'CLIPTextEncode',
            'inputs': {
                'text': negative_prompt or 'overexposed, blurry, static, watermark, subtitle, extra limbs, deformed anatomy, duplicate subjects, flicker, unrealistic camera motion',
                'clip': ['3', 0],
            },
        },
        '8': {
            'class_type': 'WanImageToVideo',
            'inputs': {
                'positive': ['6', 0],
                'negative': ['7', 0],
                'vae': ['4', 0],
                'start_image': ['16', 0],
                'width': width,
                'height': height,
                'length': length_frames,
                'batch_size': 1,
            },
        },
        '9': {
            'class_type': 'ModelSamplingSD3',
            'inputs': {
                'model': ['1', 0],
                'shift': float(payload.get('sampling_shift_quality') or payload.get('sampling_shift') or 5),
            },
        },
        '10': {
            'class_type': 'ModelSamplingSD3',
            'inputs': {
                'model': ['2', 0],
                'shift': float(payload.get('sampling_shift_quality') or payload.get('sampling_shift') or 5),
            },
        },
        '11': {
            'class_type': 'KSamplerAdvanced',
            'inputs': {
                'model': ['9', 0],
                'add_noise': 'enable',
                'noise_seed': seed_value,
                'steps': steps,
                'cfg': cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler,
                'positive': ['8', 0],
                'negative': ['8', 1],
                'latent_image': ['8', 2],
                'start_at_step': 0,
                'end_at_step': split_step,
                'return_with_leftover_noise': 'enable',
            },
        },
        '12': {
            'class_type': 'KSamplerAdvanced',
            'inputs': {
                'model': ['10', 0],
                'add_noise': 'disable',
                'noise_seed': seed_value,
                'steps': steps,
                'cfg': cfg,
                'sampler_name': sampler_name,
                'scheduler': scheduler,
                'positive': ['8', 0],
                'negative': ['8', 1],
                'latent_image': ['11', 0],
                'start_at_step': split_step,
                'end_at_step': steps,
                'return_with_leftover_noise': 'disable',
            },
        },
        '13': {
            'class_type': 'VAEDecode',
            'inputs': {
                'samples': ['12', 0],
                'vae': ['4', 0],
            },
        },
        '14': {
            'class_type': 'CreateVideo',
            'inputs': {
                'images': ['13', 0],
                'fps': float(fps),
            },
        },
        '15': {
            'class_type': 'SaveVideo',
            'inputs': {
                'video': ['14', 0],
                'filename_prefix': str(payload.get('filename_prefix') or 'video/NeoStudioQualityI2V').strip() or 'video/NeoStudioQualityI2V',
                'format': str(payload.get('video_format') or 'auto').strip() or 'auto',
                'codec': str(payload.get('video_codec') or 'auto').strip() or 'auto',
            },
        },
    }

    graph['16'] = {
        'class_type': 'ImageScale',
        'inputs': {
            'image': ['5', 0],
            'upscale_method': 'lanczos',
            'width': width,
            'height': height,
            'crop': 'disabled',
        },
    }

    high_noise_model_ref = ['1', 0]
    low_noise_model_ref = ['2', 0]
    next_id = max(int(key) for key in graph.keys()) + 1
    if advanced_adapters['enabled']:
        next_id, high_noise_model_ref = _apply_video_paired_adapter(graph, next_id, high_noise_model_ref, advanced_adapters['high_noise_adapter'], advanced_adapters['strength'])
        next_id, low_noise_model_ref = _apply_video_paired_adapter(graph, next_id, low_noise_model_ref, advanced_adapters['low_noise_adapter'], advanced_adapters['strength'])
    graph['9']['inputs']['model'] = list(high_noise_model_ref)
    graph['10']['inputs']['model'] = list(low_noise_model_ref)

    _assert_wan_native_video_loader_graph(graph)

    normalized_payload = {
        **payload,
        'surface': 'video',
        'family': 'wan22',
        'workflow_type': 'video_quality_i2v',
        'mode': 'i2v',
        'profile': 'wan22_14b_i2v_quality',
        'prompt': str(payload.get('prompt') or '').strip(),
        'compiled_prompt': prompt,
        'negative_prompt': negative_prompt,
        'duration_seconds': duration_seconds,
        'fps': fps,
        'size_preset': size_preset,
        'width': width,
        'height': height,
        'video_length_frames': length_frames,
        'seed': str(payload.get('seed') or '').strip(),
        'seed_value': seed_value,
        'steps': steps,
        'split_step': split_step,
        'cfg': cfg,
        'sampler_name': sampler_name,
        'scheduler': scheduler,
        'source_image_name': source_image_name,
        'quality_style_prompt': str(payload.get('quality_style_prompt') or '').strip(),
        'quality_camera_prompt': str(payload.get('quality_camera_prompt') or '').strip(),
        'heaviness': 'heavy',
        'advanced_adapters': advanced_adapters,
        'uses_gguf_high_noise_unet': _is_video_gguf_unet_name(payload.get('quality_high_noise_unet_name') or 'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors'),
        'uses_gguf_low_noise_unet': _is_video_gguf_unet_name(payload.get('quality_low_noise_unet_name') or 'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors'),
    }

    compile_notes = [
        f'High Quality I2V uses Wan 2.2 14B with separate high-noise and low-noise expert UNETs anchored to the uploaded start image at {width}x{height} and {fps} FPS.',
        f'Neo split the {steps}-step schedule at step {split_step} so the low-noise expert takes over detail refinement after the motion anchor is established.',
        'This path is intentionally heavier and slower than Balanced / Low VRAM. Backend-side offload or reduced output size may still be needed on constrained GPUs.',
    ]
    compile_notes.append('Wan-native encoder routing is locked to CLIPLoader type=wan for High Quality I2V runs.')
    if normalized_payload['uses_gguf_high_noise_unet'] or normalized_payload['uses_gguf_low_noise_unet']:
        compile_notes.append('High Quality I2V switched the selected Wan expert UNETs onto UnetLoaderGGUF wherever the chosen asset is a GGUF file.')
    if advanced_adapters['enabled']:
        compile_notes.append(f"Advanced adapters are enabled with a paired {advanced_adapters['strength']:.2f} strength load across the high-noise and low-noise experts.")
        if advanced_adapters.get('pair_preset_name') or advanced_adapters.get('pair_preset_id'):
            compile_notes.append(f"Adapter pair preset: {advanced_adapters.get('pair_preset_name') or advanced_adapters.get('pair_preset_id')}.")
    if duration_seconds > 5:
        compile_notes.append('This request is longer than the official 5s quality examples, so runtime and failure risk both go up.')
    return graph, normalized_payload, compile_notes