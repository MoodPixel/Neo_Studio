from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..contracts.generation_families import normalize_generation_mode, normalize_inpaint_backend
from ..contracts.inpaint_payloads import get_shared_inpaint_payload

SOURCE_WORKFLOWS = {'img2img', 'inpaint', 'outpaint'}
MASK_WORKFLOWS = {'inpaint'}
BATCH_FORCE_ONE_WORKFLOWS = {'img2img', 'inpaint', 'outpaint', 'lanpaint'}
OUTPUT_POLICY_ALIASES = {
    'new_run': 'new_current_run',
    'new_current_run': 'new_current_run',
    'append': 'append_derived',
    'append_derived': 'append_derived',
    'replace': 'replace_selected',
    'replace_selected': 'replace_selected',
    'preview': 'preview_only',
    'preview_only': 'preview_only',
}
SAFE_OUTPUT_POLICIES = set(OUTPUT_POLICY_ALIASES.values())


def _text(value: Any) -> str:
    return str(value or '').strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'active'}
    return bool(value)




def _normalize_output_policy(value: Any, *, mode: str = 'txt2img') -> tuple[str, str, list[dict[str, Any]]]:
    raw = _text(value or 'new_current_run') or 'new_current_run'
    key = raw.strip().lower()
    warnings: list[dict[str, Any]] = []
    effective = OUTPUT_POLICY_ALIASES.get(key)
    if not effective:
        effective = 'new_current_run'
        warnings.append(_warning(
            'output_policy_reset',
            f'Unknown output policy {raw!r}; using New run.',
            target='output_policy',
        ))
    # Source-image workflows should not silently replace a parent unless a later phase
    # adds a dedicated confirmation path. Keep the request visible and safe.
    if mode in SOURCE_WORKFLOWS and effective == 'replace_selected':
        warnings.append(_warning(
            'output_policy_replace_requires_confirmation',
            f'{mode} requested Replace selected, but this workflow queues as New run until explicit replace confirmation exists.',
            target='output_policy',
        ))
        effective = 'new_current_run'
    return raw, effective, warnings

def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except Exception:
        return default


def _nested_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        nested = get_shared_inpaint_payload(payload)
        return nested if isinstance(nested, dict) else {}
    except Exception:
        return {}


def _source_image_name(payload: dict[str, Any]) -> str:
    nested = _nested_payload(payload)
    source_images = nested.get('source_images') if isinstance(nested.get('source_images'), dict) else {}
    candidates = [
        source_images.get('base_image_name') if isinstance(source_images, dict) else '',
        payload.get('source_image_name'),
        payload.get('source_image'),
        payload.get('active_source_image'),
        payload.get('generationPreviewActionTarget'),
        payload.get('generationSelectedOutputSnapshot'),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ('filename', 'source_image_name', 'name', 'path', 'output_id'):
                value = _text(candidate.get(key))
                if value:
                    return value
        else:
            value = _text(candidate)
            if value:
                return value
    return ''


def _mask_image_name(payload: dict[str, Any]) -> str:
    nested = _nested_payload(payload)
    mask_row = nested.get('mask') if isinstance(nested.get('mask'), dict) else {}
    candidates = [
        mask_row.get('mask_image_name') if isinstance(mask_row, dict) else '',
        payload.get('mask_image_name'),
        payload.get('mask_image'),
    ]
    for candidate in candidates:
        value = _text(candidate)
        if value:
            return value
    return ''


def _outpaint_values(payload: dict[str, Any]) -> dict[str, int]:
    nested = _nested_payload(payload)
    row = nested.get('outpaint') if isinstance(nested.get('outpaint'), dict) else {}
    return {
        'left': _as_int(row.get('left') if isinstance(row, dict) else None, _as_int(payload.get('outpaint_left'))),
        'top': _as_int(row.get('top') if isinstance(row, dict) else None, _as_int(payload.get('outpaint_top'))),
        'right': _as_int(row.get('right') if isinstance(row, dict) else None, _as_int(payload.get('outpaint_right'))),
        'bottom': _as_int(row.get('bottom') if isinstance(row, dict) else None, _as_int(payload.get('outpaint_bottom'))),
    }


def _error(code: str, message: str, *, target: str = '', severity: str = 'block') -> dict[str, Any]:
    return {'code': code, 'message': message, 'target': target, 'severity': severity}


def _warning(code: str, message: str, *, target: str = '', severity: str = 'warning') -> dict[str, Any]:
    return {'code': code, 'message': message, 'target': target, 'severity': severity}


@dataclass
class ImageWorkflowValidationResult:
    valid: bool = True
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    auto_fixes: list[dict[str, Any]] = field(default_factory=list)
    effective_payload: dict[str, Any] = field(default_factory=dict)
    effective_systems: list[str] = field(default_factory=list)
    batch_policy: dict[str, Any] = field(default_factory=dict)
    output_policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        reason = self.errors[0]['message'] if self.errors else ''
        return {
            'valid': bool(self.valid),
            'reason': reason,
            'errors': self.errors,
            'warnings': self.warnings,
            'auto_fixes': self.auto_fixes,
            'effective_payload': self.effective_payload,
            'effective_systems': self.effective_systems,
            'batch_policy': self.batch_policy,
            'output_policy': self.output_policy,
        }


def validate_image_workflow_payload(payload: dict[str, Any] | None, *, active_systems: list[str] | None = None) -> dict[str, Any]:
    """Validate Image Tab workflow guardrails before graph compile.

    This extends the documented Dynamic Workflow Validator contract without owning
    workflow switching. It reports raw/effective mode, source requirements,
    batch policy, and output policy in a transparent result object.
    """
    raw_payload = payload if isinstance(payload, dict) else {}
    effective = deepcopy(raw_payload)
    raw_mode = _text(raw_payload.get('mode') or raw_payload.get('workflow_type') or 'txt2img') or 'txt2img'
    mode = normalize_generation_mode(raw_mode)
    if mode not in {'txt2img', 'img2img', 'inpaint', 'outpaint'}:
        mode = 'txt2img'
    effective['mode'] = mode
    effective['workflow_type'] = mode

    family = _text(raw_payload.get('family') or raw_payload.get('_neo_effective_family'))
    model_source = _text(raw_payload.get('model_source') or raw_payload.get('_neo_effective_model_source'))
    inpaint_backend = normalize_inpaint_backend(raw_payload.get('inpaint_backend') or 'standard')
    active = list(active_systems or raw_payload.get('active_systems') or raw_payload.get('_neo_active_systems') or [])

    source_name = _source_image_name(effective)
    mask_name = _mask_image_name(effective)
    outpaint = _outpaint_values(effective)
    batch_requested = max(1, _as_int(raw_payload.get('batch_size') or raw_payload.get('batch'), 1))
    batch_effective = batch_requested
    output_policy_requested, output_policy_effective, output_policy_warnings = _normalize_output_policy(
        raw_payload.get('output_policy') or raw_payload.get('_neo_output_policy') or 'new_current_run',
        mode=mode,
    )

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(output_policy_warnings)
    auto_fixes: list[dict[str, Any]] = []

    if mode in SOURCE_WORKFLOWS and not source_name:
        errors.append(_error('missing_source_image', f'{mode} requires a source image before queueing.', target='source_image'))
    if mode in MASK_WORKFLOWS and not mask_name:
        errors.append(_error('missing_mask_image', 'inpaint requires a mask image before queueing.', target='mask_image'))
    if mode == 'outpaint' and sum(outpaint.values()) <= 0:
        errors.append(_error('missing_outpaint_expansion', 'outpaint requires padding on at least one side before queueing.', target='outpaint_expansion'))
    if mode == 'outpaint' and (_truthy(raw_payload.get('scene_director_enabled')) or 'scene_director' in active):
        warnings.append(_warning('scene_director_restricted_for_outpaint', 'Scene Director is not supported for outpaint and must be skipped by compile.', target='scene_director'))
    if mode != 'inpaint' and inpaint_backend != 'standard':
        auto_fixes.append({'code': 'inpaint_backend_reset', 'message': f'{mode} uses standard backend; stale inpaint backend was reset.', 'target': 'inpaint_backend', 'from': inpaint_backend, 'to': 'standard'})
        effective['inpaint_backend'] = 'standard'
    else:
        effective['inpaint_backend'] = inpaint_backend
    if mode in BATCH_FORCE_ONE_WORKFLOWS and batch_requested > 1:
        warnings.append(_warning('batch_force_one_required', f'{mode} is a source-image workflow; batch size must run as 1.', target='batch_size'))
        auto_fixes.append({
            'code': 'batch_size_force_one',
            'message': f'{mode} requested batch size {batch_requested}; effective batch size is 1 for source-image workflow safety.',
            'target': 'batch_size',
            'from': batch_requested,
            'to': 1,
            'visible': True,
        })
        batch_effective = 1
        effective['batch_size'] = 1
        effective['_neo_batch_guard_applied'] = True
        effective['_neo_batch_guard_reason'] = f'{mode}_source_image_single'
    elif mode == 'txt2img':
        batch_effective = batch_requested

    incoming_workflow_state = raw_payload.get('workflow_state') if isinstance(raw_payload.get('workflow_state'), dict) else {}
    workflow_state = {
        'raw_mode': _text(incoming_workflow_state.get('raw_mode') or raw_mode) or raw_mode,
        'effective_mode': mode,
        'switch_reason': _text(incoming_workflow_state.get('switch_reason') or raw_payload.get('_neo_workflow_switch_reason') or 'backend_validation'),
        'source_kind': _text(incoming_workflow_state.get('source_kind') or raw_payload.get('_neo_source_kind') or ('uploaded_source' if source_name else 'none')),
        'source_id': _text(incoming_workflow_state.get('source_id') or raw_payload.get('_neo_source_id') or source_name),
        'source_name': source_name,
        'output_policy': output_policy_effective,
        'validation_status': 'blocked' if errors else 'valid',
        'source_required': mode in SOURCE_WORKFLOWS,
        'mask_required': mode in MASK_WORKFLOWS,
        'outpaint_expansion': outpaint,
        'visible': True,
        'owner': 'image_workflow_validator',
        'batch_policy': {
            'requested': batch_requested,
            'effective': batch_effective,
            'policy': 'force_1' if mode in BATCH_FORCE_ONE_WORKFLOWS else 'allow',
            'reason': 'source_image_workflow' if mode in BATCH_FORCE_ONE_WORKFLOWS else '',
            'visible': True,
        },
        'output_policy_requested': output_policy_requested,
        'output_policy_effective': output_policy_effective,
        'visible': True,
        'owner': 'image_workflow_validator',
        'version': 'phase_g_batch_output_policy_rules_v1',
    }
    effective['workflow_state'] = workflow_state
    effective['_neo_workflow_state'] = workflow_state
    effective['_neo_workflow_validation'] = {
        **workflow_state,
        'source_image_name': source_name,
        'mask_image_name': mask_name,
        'family': family,
        'model_source': model_source,
    }
    effective['_neo_workflow_validation_status'] = 'blocked' if errors else 'valid'
    effective['_neo_effective_mode'] = mode
    effective['_neo_requested_batch_size'] = batch_requested
    effective['_neo_effective_batch_size'] = batch_effective
    effective['_neo_output_policy'] = output_policy_effective
    effective['_neo_output_policy_requested'] = output_policy_requested
    if '_neo_batch_guard_applied' not in effective:
        effective['_neo_batch_guard_applied'] = False
        effective['_neo_batch_guard_reason'] = ''

    result = ImageWorkflowValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        auto_fixes=auto_fixes,
        effective_payload=effective,
        effective_systems=active,
        batch_policy={
            'requested': batch_requested,
            'effective': batch_effective,
            'policy': 'force_1' if mode in BATCH_FORCE_ONE_WORKFLOWS else 'allow',
            'reason': 'source_image_workflow' if mode in BATCH_FORCE_ONE_WORKFLOWS else '',
            'visible': True,
        },
        output_policy={'requested': output_policy_requested, 'effective': output_policy_effective, 'policy': output_policy_effective, 'visible': True},
    )
    return result.to_dict()


__all__ = ['validate_image_workflow_payload', 'ImageWorkflowValidationResult']
