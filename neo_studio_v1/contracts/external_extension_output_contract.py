from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION = 'external-extension-output-contract-v1'

VALID_EXTENSION_OUTPUT_TYPES = {
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
    'file',
    'unknown',
}

VALID_EXTENSION_OUTPUT_ROLES = {
    'primary',
    'preview',
    'sidecar',
    'mask',
    'debug',
    'asset',
}

_RESERVED_DEBUG_ROLES = {'debug'}


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _text(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _key(value: Any, default: str = '') -> str:
    return _text(value, default).lower().replace(' ', '_').replace('-', '_')


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        return [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(value)


def _safe_relative_path(value: Any) -> str:
    text = _text(value).replace('\\', '/')
    if not text or text.startswith('/'):
        return ''
    path = PurePosixPath(text)
    if '..' in path.parts:
        return ''
    return path.as_posix()


def normalize_extension_output(raw: Any, *, extension_id: str = '', run_id: str = '', index: int = 0) -> dict[str, Any]:
    """Normalize one external extension output declaration or collected output.

    This object is intentionally metadata-only. It does not save, replace, or
    publish files by itself; later output-policy enforcement decides how a
    normalized output is handled.
    """
    if isinstance(raw, str):
        data = {'id': raw, 'type': 'unknown', 'role': 'sidecar'}
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        data = {}

    output_id = _text(data.get('id') or data.get('output_id') or data.get('key') or data.get('name') or f'output_{index + 1}')
    output_type = _key(data.get('type') or data.get('media_type') or 'unknown')
    role = _key(data.get('role') or 'sidecar')
    path = _safe_relative_path(data.get('path') or data.get('file') or data.get('target') or '')

    return {
        'contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
        'extension_id': _text(data.get('extension_id') or extension_id),
        'run_id': _text(data.get('run_id') or run_id),
        'id': output_id,
        'type': output_type,
        'role': role,
        'path': path,
        'label': _text(data.get('label') or output_id),
        'required': bool(data.get('required', False)),
        'available': bool(data.get('available', bool(path))),
        'visible': bool(data.get('visible', True)),
        'metadata': _dict(data.get('metadata')),
        'raw': _copy(raw if raw is not None else {}),
    }


def normalize_extension_outputs(raw_outputs: Any, *, extension_id: str = '', run_id: str = '') -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw_outputs)):
        output = normalize_extension_output(item, extension_id=extension_id, run_id=run_id, index=index)
        if output.get('id'):
            outputs.append(output)
    return outputs


def validate_extension_output(output: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_extension_output(output, extension_id=output.get('extension_id') or '', run_id=output.get('run_id') or '')
    errors: list[str] = []
    warnings: list[str] = []

    if not normalized.get('extension_id'):
        errors.append('external extension output requires extension_id.')
    if not normalized.get('id'):
        errors.append('external extension output requires id.')

    output_type = normalized.get('type')
    role = normalized.get('role')
    if output_type not in VALID_EXTENSION_OUTPUT_TYPES:
        warnings.append(f"external extension output type '{output_type}' is custom or unknown.")
    if role not in VALID_EXTENSION_OUTPUT_ROLES:
        errors.append(f"external extension output role '{role}' is not registered.")

    if role in _RESERVED_DEBUG_ROLES and normalized.get('visible'):
        warnings.append('debug outputs must remain visibly labeled as debug-only artifacts.')

    if normalized.get('path') and output.get('path') and not _safe_relative_path(output.get('path')):
        errors.append('external extension output path must be relative and cannot traverse parent directories.')

    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'output': normalized}


def validate_extension_outputs(raw_outputs: Any, *, extension_id: str = '', run_id: str = '') -> dict[str, Any]:
    outputs = normalize_extension_outputs(raw_outputs, extension_id=extension_id, run_id=run_id)
    errors: list[str] = []
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []
    for output in outputs:
        result = validate_extension_output(output)
        errors.extend(result.get('errors') or [])
        warnings.extend(result.get('warnings') or [])
        normalized.append(result.get('output') or output)
    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'outputs': normalized,
        'contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
    }


def build_extension_output_group(
    *,
    extension_id: str,
    run_id: str = '',
    outputs: Any = None,
    metadata: dict[str, Any] | None = None,
    status: str = 'declared',
) -> dict[str, Any]:
    validation = validate_extension_outputs(outputs or [], extension_id=extension_id, run_id=run_id)
    return {
        'contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
        'extension_id': _text(extension_id),
        'run_id': _text(run_id),
        'status': _key(status or 'declared'),
        'outputs': validation.get('outputs') or [],
        'metadata': _dict(metadata),
        'warnings': list(validation.get('warnings') or []),
        'errors': list(validation.get('errors') or []),
        'valid': bool(validation.get('ok')),
    }
