from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...contracts.external_extension_output_contract import (
    EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
    build_extension_output_group,
)
from .output_policy_enforcer import attach_output_policy_enforcement
from ...contracts.external_extension_run_metadata import attach_external_extension_run_metadata

OUTPUT_COLLECTOR_VERSION = 'external-extension-output-collector-v1'


def _declared_output_groups(report: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    run_id = str(report.get('run_id') or report.get('job_id') or '').strip()
    for patch in report.get('patches') or []:
        if not isinstance(patch, dict):
            continue
        extension_id = str(patch.get('extension_id') or '').strip()
        outputs = patch.get('outputs') or patch.get('outputs_declared') or []
        if not extension_id and isinstance(outputs, list) and outputs:
            extension_id = str((outputs[0] if isinstance(outputs[0], dict) else {}).get('extension_id') or '').strip()
        if not extension_id:
            continue
        group = build_extension_output_group(
            extension_id=extension_id,
            run_id=run_id,
            outputs=outputs,
            metadata={
                'patch_id': patch.get('patch_id'),
                'strategy': patch.get('strategy'),
                'template': patch.get('template'),
                'applied': patch.get('applied'),
                'queued_as_sidecar': patch.get('queued_as_sidecar'),
            },
            status='declared',
        )
        groups.append(group)
    return groups


def build_extension_output_collection_shell(runtime_report: dict[str, Any] | None = None, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    report = deepcopy(runtime_report) if isinstance(runtime_report, dict) else {}
    groups = _declared_output_groups(report)
    warnings = list(report.get('warnings') or [])
    errors = list(report.get('errors') or [])
    for group in groups:
        warnings.extend([f"{group.get('extension_id')}: {warning}" for warning in group.get('warnings') or []])
        errors.extend([f"{group.get('extension_id')}: {error}" for error in group.get('errors') or []])
    shell = {
        'collector_version': OUTPUT_COLLECTOR_VERSION,
        'output_contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
        'active': list(report.get('active_extensions') or []),
        'patches': list(report.get('patches') or []),
        'outputs': groups,
        'warnings': warnings,
        'errors': errors,
        'policy': 'declared_outputs_only_no_save_no_replace',
        'visible': True,
    }
    if isinstance(payload, dict):
        attach_output_policy_enforcement(payload, shell)
    return shell


def attach_extension_output_collection(payload: dict[str, Any], runtime_report: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    shell = build_extension_output_collection_shell(runtime_report, payload=payload)
    payload['_neo_external_extension_output_collection'] = shell
    meta = payload.get('_neo_external_extensions') if isinstance(payload.get('_neo_external_extensions'), dict) else {}
    meta['output_collection'] = shell
    payload['_neo_external_extensions'] = meta
    attach_external_extension_run_metadata(payload, runtime_report=runtime_report, output_collection=shell)
    return payload
