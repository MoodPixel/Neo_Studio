from __future__ import annotations

from copy import deepcopy
from typing import Any

from .external_extension_payloads import (
    EXTERNAL_EXTENSION_METADATA_VERSION,
    EXTERNAL_EXTENSION_PAYLOAD_VERSION,
    build_external_extension_metadata_shell,
)

EXTERNAL_EXTENSION_RUN_METADATA_VERSION = 'external-extension-run-metadata-v1'


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _payload_block(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    block = payload.get('external_extensions')
    return block if isinstance(block, dict) else {}


def _validation_report(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    value = payload.get('_neo_external_extensions_validation')
    return value if isinstance(value, dict) else {}


def _runtime_report(payload: dict[str, Any] | None, runtime_report: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(runtime_report, dict):
        return _copy(runtime_report)
    payload = payload if isinstance(payload, dict) else {}
    value = payload.get('_neo_external_workflow_execution')
    return value if isinstance(value, dict) else {}


def _output_collection(payload: dict[str, Any] | None, output_collection: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(output_collection, dict):
        return _copy(output_collection)
    payload = payload if isinstance(payload, dict) else {}
    value = payload.get('_neo_external_extension_output_collection')
    return value if isinstance(value, dict) else {}


def _capability_report(payload: dict[str, Any] | None, capability_report: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(capability_report, dict):
        return _copy(capability_report)
    payload = payload if isinstance(payload, dict) else {}
    value = payload.get('_neo_external_extension_capabilities')
    return value if isinstance(value, dict) else {}


def _patches_by_extension(runtime_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for patch in _list(runtime_report.get('patches')):
        if not isinstance(patch, dict):
            continue
        extension_id = _text(patch.get('extension_id'))
        if not extension_id:
            continue
        out.setdefault(extension_id, []).append(_copy(patch))
    return out


def _outputs_by_extension(output_collection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for group in _list(output_collection.get('outputs')):
        if not isinstance(group, dict):
            continue
        extension_id = _text(group.get('extension_id'))
        if extension_id:
            out[extension_id] = _copy(group)
    return out


def _policy_by_extension(output_collection: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    enforcement = output_collection.get('policy_enforcement') if isinstance(output_collection.get('policy_enforcement'), dict) else {}
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _list(enforcement.get('policies')):
        if not isinstance(row, dict):
            continue
        extension_id = _text(row.get('extension_id'))
        if extension_id:
            out.setdefault(extension_id, []).append(_copy(row))
    return out


def _capability_by_extension(capability_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # Supports both the Phase H {extensions:{id:...}} shape and direct {id:...} maps.
    source = capability_report.get('extensions') if isinstance(capability_report.get('extensions'), dict) else capability_report
    out: dict[str, dict[str, Any]] = {}
    for extension_id, row in (source or {}).items():
        if isinstance(row, dict):
            out[str(extension_id)] = _copy(row)
    return out


def build_external_extension_run_metadata(
    payload: dict[str, Any] | None = None,
    *,
    runtime_report: dict[str, Any] | None = None,
    output_collection: dict[str, Any] | None = None,
    capability_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the durable run-level external extension audit record.

    This is metadata-only. It does not execute workflows, mutate graphs, save
    files, replace outputs, or enable/disable extensions. It records the exact
    state Neo had at run time so future outputs remain explainable.
    """
    payload = payload if isinstance(payload, dict) else {}
    block = _payload_block(payload)
    validation = _validation_report(payload)
    runtime = _runtime_report(payload, runtime_report)
    collection = _output_collection(payload, output_collection)
    capabilities = _capability_report(payload, capability_report)

    base_shell = build_external_extension_metadata_shell(block, validation_report=validation)
    patches_by_extension = _patches_by_extension(runtime)
    outputs_by_extension = _outputs_by_extension(collection)
    policies_by_extension = _policy_by_extension(collection)
    capabilities_by_extension = _capability_by_extension(capabilities)

    extension_ids = sorted(set(block.keys()) | set(patches_by_extension.keys()) | set(outputs_by_extension.keys()))
    per_extension: dict[str, dict[str, Any]] = {}
    warnings = list(base_shell.get('warnings') or [])
    errors: list[str] = []

    for extension_id in extension_ids:
        state = block.get(extension_id) if isinstance(block.get(extension_id), dict) else {}
        effective_state = _dict(state.get('effective_state'))
        raw_state = _dict(state.get('raw_state'))
        patches = patches_by_extension.get(extension_id, [])
        outputs = outputs_by_extension.get(extension_id, {})
        policies = policies_by_extension.get(extension_id, [])
        patch_templates = [p.get('template') for p in patches if p.get('template')]
        patch_strategies = [p.get('strategy') for p in patches if p.get('strategy')]
        row_warnings = []
        row_errors = []
        for warning in _list(state.get('warnings')):
            row_warnings.append(str(warning))
        for patch in patches:
            row_warnings.extend([str(w) for w in _list(patch.get('warnings'))])
            row_errors.extend([str(e) for e in _list(patch.get('errors'))])
        for policy in policies:
            row_warnings.extend([str(w) for w in _list(policy.get('warnings'))])
            row_errors.extend([str(e) for e in _list(policy.get('errors'))])
        if state.get('disabled_reason'):
            row_warnings.append('disabled: ' + str(state.get('disabled_reason')))
        per_extension[extension_id] = {
            'enabled': bool(state.get('enabled')),
            'effective_enabled': bool(state.get('effective_enabled')),
            'mode': _text(effective_state.get('mode') or raw_state.get('mode')),
            'source': _text(state.get('source') or effective_state.get('source') or raw_state.get('source')),
            'target_sections': list(state.get('target_sections') or []),
            'output_policy': _text(state.get('output_policy') or effective_state.get('output_policy') or raw_state.get('output_policy')),
            'batch_policy': _text(state.get('batch_policy') or effective_state.get('batch_policy') or raw_state.get('batch_policy')),
            'context_policy': list(state.get('context_policy') or []),
            'workflow_templates': patch_templates,
            'workflow_strategies': patch_strategies,
            'patches': patches,
            'outputs': outputs,
            'output_policy_enforcement': policies,
            'validation': _dict(state.get('workflow_validation')),
            'capability': capabilities_by_extension.get(extension_id, {}),
            'raw_state': raw_state,
            'effective_state': effective_state,
            'warnings': row_warnings,
            'errors': row_errors,
            'visible': True,
        }
        warnings.extend([f'{extension_id}: {warning}' for warning in row_warnings])
        errors.extend([f'{extension_id}: {error}' for error in row_errors])

    runtime_errors = [str(e) for e in _list(runtime.get('errors'))]
    runtime_warnings = [str(w) for w in _list(runtime.get('warnings'))]
    collection_errors = [str(e) for e in _list(collection.get('errors'))]
    collection_warnings = [str(w) for w in _list(collection.get('warnings'))]
    errors.extend(runtime_errors + collection_errors)
    warnings.extend(runtime_warnings + collection_warnings)

    return {
        'run_metadata_version': EXTERNAL_EXTENSION_RUN_METADATA_VERSION,
        'payload_version': EXTERNAL_EXTENSION_PAYLOAD_VERSION,
        'metadata_version': EXTERNAL_EXTENSION_METADATA_VERSION,
        'active': list(base_shell.get('active') or []),
        'disabled': list(base_shell.get('disabled') or []),
        'per_extension': per_extension,
        'validation': validation,
        'workflow_execution': runtime,
        'output_collection': collection,
        'output_policy_enforcement': collection.get('policy_enforcement') if isinstance(collection.get('policy_enforcement'), dict) else {},
        'capabilities': capabilities,
        'raw_state': _dict(base_shell.get('raw_state')),
        'effective_state': _dict(base_shell.get('effective_state')),
        'warnings': warnings,
        'errors': errors,
        'valid': not errors,
        'visible': True,
        'policy': 'run_metadata_audit_only_no_execution_no_hidden_mutation',
    }


def attach_external_extension_run_metadata(
    payload: dict[str, Any],
    *,
    runtime_report: dict[str, Any] | None = None,
    output_collection: dict[str, Any] | None = None,
    capability_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    metadata = build_external_extension_run_metadata(
        payload,
        runtime_report=runtime_report,
        output_collection=output_collection,
        capability_report=capability_report,
    )
    meta_shell = payload.get('_neo_external_extensions') if isinstance(payload.get('_neo_external_extensions'), dict) else {}
    meta_shell['run_metadata'] = metadata
    payload['_neo_external_extensions'] = meta_shell
    payload['_neo_external_extension_run_metadata'] = metadata
    return payload
