from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...contracts.external_extension_policies import DEFAULT_OUTPUT_POLICY, VALID_EXTERNAL_OUTPUT_POLICIES

OUTPUT_POLICY_ENFORCER_VERSION = 'external-extension-output-policy-enforcer-v1'


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _key(value: Any, default: str = '') -> str:
    text = str(value if value is not None else default).strip().lower().replace(' ', '_').replace('-', '_')
    return text or default


def _extension_payload_state(payload: dict[str, Any] | None, extension_id: str) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    block = payload.get('external_extensions') if isinstance(payload.get('external_extensions'), dict) else {}
    state = block.get(extension_id) if isinstance(block.get(extension_id), dict) else {}
    return _copy(state)


def _requested_policy(state: dict[str, Any], output: dict[str, Any] | None = None) -> str:
    output = output if isinstance(output, dict) else {}
    effective = state.get('effective_state') if isinstance(state.get('effective_state'), dict) else {}
    raw = state.get('raw_state') if isinstance(state.get('raw_state'), dict) else {}
    policy = _key(
        output.get('output_policy')
        or output.get('policy')
        or effective.get('output_policy')
        or state.get('output_policy')
        or raw.get('output_policy')
        or DEFAULT_OUTPUT_POLICY,
        DEFAULT_OUTPUT_POLICY,
    )
    if policy not in VALID_EXTERNAL_OUTPUT_POLICIES:
        return DEFAULT_OUTPUT_POLICY
    return policy


def _replace_confirmed(state: dict[str, Any]) -> bool:
    effective = state.get('effective_state') if isinstance(state.get('effective_state'), dict) else {}
    raw = state.get('raw_state') if isinstance(state.get('raw_state'), dict) else {}
    return bool(
        effective.get('replace_confirmed')
        or effective.get('confirmed_replace_output')
        or raw.get('replace_confirmed')
        or raw.get('confirmed_replace_output')
    )


def _replace_target(state: dict[str, Any], output: dict[str, Any] | None = None) -> str:
    output = output if isinstance(output, dict) else {}
    effective = state.get('effective_state') if isinstance(state.get('effective_state'), dict) else {}
    raw = state.get('raw_state') if isinstance(state.get('raw_state'), dict) else {}
    return str(
        output.get('replace_target')
        or output.get('target_output_id')
        or effective.get('replace_target')
        or effective.get('target_output_id')
        or raw.get('replace_target')
        or raw.get('target_output_id')
        or ''
    ).strip()


def enforce_output_policy_for_output(*, payload: dict[str, Any] | None, extension_id: str, output: dict[str, Any]) -> dict[str, Any]:
    """Return the visible action Neo may take for one extension output.

    This is intentionally policy-only. It does not save, delete, replace, copy,
    or move files. Runtime/storage layers must read this report and perform only
    allowed actions.
    """
    state = _extension_payload_state(payload, extension_id)
    policy = _requested_policy(state, output)
    role = _key(output.get('role') or 'sidecar', 'sidecar')
    warnings: list[str] = []
    errors: list[str] = []
    blocked = False
    action = 'preview_only'
    save_behavior = 'not_saved_as_final'
    target = ''

    if policy == 'preview':
        action = 'preview_only'
        save_behavior = 'do_not_save_as_final'
    elif policy == 'new_run':
        action = 'create_new_extension_run'
        save_behavior = 'save_as_separate_run'
    elif policy == 'append':
        action = 'append_to_current_run_assets'
        save_behavior = 'save_as_asset_sidecar'
    elif policy == 'replace':
        target = _replace_target(state, output)
        if not _replace_confirmed(state):
            blocked = True
            errors.append('replace output policy requires visible user confirmation.')
        if not target:
            blocked = True
            errors.append('replace output policy requires an explicit target output id/path.')
        action = 'replace_existing_target'
        save_behavior = 'replace_confirmed_target_only'
        warnings.append('replace is restricted: Neo must only replace the confirmed target and must preserve metadata traceability.')
    else:
        policy = DEFAULT_OUTPUT_POLICY
        action = 'preview_only'
        save_behavior = 'do_not_save_as_final'
        warnings.append(f"Unknown output policy normalized to '{DEFAULT_OUTPUT_POLICY}'.")

    # Debug outputs are never allowed to become primary replacement targets.
    if role == 'debug' and policy in {'replace', 'new_run'}:
        blocked = True
        errors.append('debug outputs cannot use replace or new_run output policy.')

    return {
        'enforcer_version': OUTPUT_POLICY_ENFORCER_VERSION,
        'extension_id': extension_id,
        'output_id': str(output.get('id') or '').strip(),
        'output_role': role,
        'requested_policy': policy,
        'effective_policy': 'blocked' if blocked else policy,
        'action': 'blocked' if blocked else action,
        'save_behavior': 'none_blocked' if blocked else save_behavior,
        'replace_target': target,
        'blocked': blocked,
        'warnings': warnings,
        'errors': errors,
        'visible': True,
    }


def enforce_extension_output_policies(*, payload: dict[str, Any] | None, output_collection: dict[str, Any] | None) -> dict[str, Any]:
    collection = output_collection if isinstance(output_collection, dict) else {}
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    blocked = False

    for group in _list(collection.get('outputs')):
        if not isinstance(group, dict):
            continue
        extension_id = str(group.get('extension_id') or '').strip()
        if not extension_id:
            continue
        for output in _list(group.get('outputs')):
            if not isinstance(output, dict):
                continue
            report = enforce_output_policy_for_output(payload=payload, extension_id=extension_id, output=output)
            results.append(report)
            warnings.extend([f"{extension_id}/{report.get('output_id')}: {warning}" for warning in report.get('warnings') or []])
            errors.extend([f"{extension_id}/{report.get('output_id')}: {error}" for error in report.get('errors') or []])
            blocked = blocked or bool(report.get('blocked'))

    return {
        'enforcer_version': OUTPUT_POLICY_ENFORCER_VERSION,
        'valid': not blocked,
        'blocked': blocked,
        'policies': results,
        'warnings': warnings,
        'errors': errors,
        'rules': {
            'preview': 'show result without saving as final output',
            'new_run': 'save extension result as a separate run',
            'append': 'append extension result to current run assets',
            'replace': 'replace only an explicitly confirmed target',
        },
        'visible': True,
    }


def attach_output_policy_enforcement(payload: dict[str, Any], output_collection: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    report = enforce_extension_output_policies(payload=payload, output_collection=output_collection)
    output_collection['policy_enforcement'] = report
    output_collection['policy'] = 'central_output_policy_enforced_visible'
    output_collection.setdefault('warnings', [])
    output_collection.setdefault('errors', [])
    if isinstance(output_collection.get('warnings'), list):
        output_collection['warnings'].extend(report.get('warnings') or [])
    if isinstance(output_collection.get('errors'), list):
        output_collection['errors'].extend(report.get('errors') or [])
    meta = payload.get('_neo_external_extensions') if isinstance(payload.get('_neo_external_extensions'), dict) else {}
    meta['output_policy_enforcement'] = report
    payload['_neo_external_extensions'] = meta
    payload['_neo_external_extension_output_policy_enforcement'] = report
    return payload
