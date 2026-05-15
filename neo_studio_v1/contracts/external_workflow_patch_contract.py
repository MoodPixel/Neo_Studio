from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION = 'external-workflow-patch-contract-v1'

VALID_WORKFLOW_PATCH_STRATEGIES = {
    'replace_workflow',
    'append_nodes',
    'preprocess_source',
    'postprocess_output',
    'sidecar_run',
    'metadata_only',
}

VALID_WORKFLOW_PATCH_TIMINGS = {
    'before_base',
    'after_base',
    'preprocess',
    'postprocess',
    'sidecar',
    'metadata',
}

VALID_WORKFLOW_PATCH_OUTPUT_ROLES = {
    'primary',
    'preview',
    'sidecar',
    'mask',
    'debug',
    'asset',
}

VALID_WORKFLOW_PATCH_OUTPUT_TYPES = {
    'image',
    'rgba_image',
    'rgb_image',
    'alpha_mask',
    'mask',
    'json',
    'metadata',
    'log',
    'latent',
    'conditioning',
    'unknown',
}

_STRATEGY_DEFAULT_TIMING = {
    'replace_workflow': 'before_base',
    'append_nodes': 'after_base',
    'preprocess_source': 'preprocess',
    'postprocess_output': 'postprocess',
    'sidecar_run': 'sidecar',
    'metadata_only': 'metadata',
}


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


def _text(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _key(value: Any, default: str = '') -> str:
    return _text(value, default).lower().replace(' ', '_').replace('-', '_')


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        return [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(value)


def _string_list(value: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        text = _text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _safe_relative_path(value: Any) -> str:
    text = _text(value).replace('\\', '/')
    if not text or text.startswith('/'):
        return ''
    path = PurePosixPath(text)
    if '..' in path.parts:
        return ''
    return path.as_posix()


def _normalize_outputs(value: Any) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value)):
        if isinstance(item, str):
            output = {'id': item, 'type': 'unknown', 'role': 'sidecar'}
        elif isinstance(item, dict):
            output = dict(item)
        else:
            continue
        output_id = _text(output.get('id') or output.get('key') or output.get('name') or f'output_{index + 1}')
        output_type = _key(output.get('type') or 'unknown')
        output_role = _key(output.get('role') or 'sidecar')
        outputs.append({
            'id': output_id,
            'type': output_type,
            'role': output_role,
            'path': _text(output.get('path') or output.get('target') or ''),
            'label': _text(output.get('label') or output_id),
            'required': bool(output.get('required', False)),
            'metadata': _dict(output.get('metadata')),
        })
    return outputs


def normalize_workflow_patch(raw: dict[str, Any] | None, *, extension_id: str = '', index: int = 0) -> dict[str, Any]:
    """Normalize one declarative external workflow patch.

    This is a contract object only. It never applies graph mutations directly.
    The future execution bridge must consume this normalized declaration and
    decide whether/how to apply it after validation.
    """
    data = dict(raw or {})
    strategy = _key(data.get('strategy') or data.get('type') or 'metadata_only')
    timing = _key(data.get('timing') or data.get('phase') or _STRATEGY_DEFAULT_TIMING.get(strategy, 'metadata'))
    patch_id = _text(data.get('id') or data.get('patch_id') or f'patch_{index + 1}')
    template = _safe_relative_path(data.get('template') or data.get('workflow_template') or data.get('workflow') or '')
    nodes = _dict(data.get('nodes') or data.get('graph_patch') or {})
    inputs = _dict(data.get('inputs'))
    outputs = _normalize_outputs(data.get('outputs'))
    requires_confirmation = bool(data.get('requires_confirmation', False))
    if strategy == 'replace_workflow':
        requires_confirmation = bool(data.get('requires_confirmation', True))

    return {
        'contract_version': EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION,
        'id': patch_id,
        'extension_id': _text(extension_id or data.get('extension_id')),
        'strategy': strategy,
        'timing': timing,
        'template': template,
        'inputs': inputs,
        'outputs': outputs,
        'nodes': nodes,
        'conditions': _dict(data.get('conditions')),
        'mode': _text(data.get('mode') or ''),
        'target_sections': _string_list(data.get('target_sections') or data.get('sections') or []),
        'requires_confirmation': requires_confirmation,
        'enabled': bool(data.get('enabled', True)),
        'description': _text(data.get('description') or ''),
        'metadata': _dict(data.get('metadata')),
        'raw': _copy(raw or {}),
    }


def normalize_workflow_patches(raw: Any, *, extension_id: str = '') -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    if isinstance(raw, dict) and any(key in raw for key in ('strategy', 'type', 'template', 'workflow_template', 'nodes')):
        raw_items = [raw]
    elif isinstance(raw, dict):
        raw_items = raw.get('items') or raw.get('patches') or raw.get('workflow_patches') or []
    else:
        raw_items = raw
    for index, item in enumerate(_list(raw_items)):
        if isinstance(item, dict):
            patches.append(normalize_workflow_patch(item, extension_id=extension_id, index=index))
    return patches


def validate_workflow_patch(patch: dict[str, Any]) -> dict[str, Any]:
    patch = normalize_workflow_patch(patch, extension_id=patch.get('extension_id') or '', index=0)
    errors: list[str] = []
    warnings: list[str] = []

    strategy = patch.get('strategy')
    if strategy not in VALID_WORKFLOW_PATCH_STRATEGIES:
        errors.append(f"workflow patch strategy '{strategy}' is not registered.")

    timing = patch.get('timing')
    if timing not in VALID_WORKFLOW_PATCH_TIMINGS:
        errors.append(f"workflow patch timing '{timing}' is not registered.")

    if strategy in {'replace_workflow', 'sidecar_run', 'preprocess_source', 'postprocess_output'} and not patch.get('template'):
        errors.append(f"workflow patch strategy '{strategy}' requires a safe extension-relative template path.")

    if strategy == 'append_nodes' and not patch.get('nodes'):
        errors.append("workflow patch strategy 'append_nodes' requires a nodes/graph_patch object.")

    if strategy == 'replace_workflow' and not patch.get('requires_confirmation'):
        errors.append("workflow patch strategy 'replace_workflow' must require visible confirmation.")

    for output in patch.get('outputs') or []:
        output_type = output.get('type')
        output_role = output.get('role')
        if output_type not in VALID_WORKFLOW_PATCH_OUTPUT_TYPES:
            warnings.append(f"workflow patch output type '{output_type}' is custom or unknown.")
        if output_role not in VALID_WORKFLOW_PATCH_OUTPUT_ROLES:
            errors.append(f"workflow patch output role '{output_role}' is not registered.")

    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'patch': patch}


def validate_workflow_patches(raw: Any, *, extension_id: str = '') -> dict[str, Any]:
    patches = normalize_workflow_patches(raw, extension_id=extension_id)
    errors: list[str] = []
    warnings: list[str] = []
    for patch in patches:
        result = validate_workflow_patch(patch)
        errors.extend(result.get('errors') or [])
        warnings.extend(result.get('warnings') or [])
    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'patches': patches,
        'contract_version': EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION,
    }
