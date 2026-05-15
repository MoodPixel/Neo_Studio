from __future__ import annotations

from copy import deepcopy
from typing import Any

# Phase 1 external-extension policy contract.
# These values are intentionally generic and must not name a specific extension.
EXTERNAL_EXTENSION_POLICY_VERSION = 'external-extension-policy-v1'

VALID_EXTERNAL_SOURCE_POLICIES = {'prompt', 'selected_image', 'upload', 'output', 'none'}
VALID_EXTERNAL_OUTPUT_POLICIES = {'append', 'replace', 'preview', 'new_run'}
VALID_EXTERNAL_BATCH_POLICIES = {'supported', 'force_1', 'blocked', 'sequential'}
VALID_EXTERNAL_CONTEXT_POLICIES = {'prompt', 'model', 'image', 'identity', 'metadata', 'none'}

DEFAULT_SOURCE_POLICY = 'none'
DEFAULT_OUTPUT_POLICY = 'preview'
DEFAULT_BATCH_POLICY = 'force_1'
DEFAULT_CONTEXT_POLICY = ['prompt', 'model']

# Replacement and identity access are allowed only when explicitly declared.
RESTRICTED_OUTPUT_POLICIES = {'replace'}
RESTRICTED_CONTEXT_POLICIES = {'identity'}


def _deepcopy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _clean_key(value: Any) -> str:
    return str(value or '').strip().lower().replace(' ', '_')


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        key = _clean_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_external_extension_policies(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize external-extension policies into safe explicit values.

    This does not execute an extension. It makes policy behavior visible and
    deterministic for registry, payload, and validator layers.
    """
    data = dict(raw or {})
    warnings: list[str] = []
    errors: list[str] = []

    source_policy = _list(data.get('source_policy') or data.get('sources'))
    if not source_policy:
        source_policy = [DEFAULT_SOURCE_POLICY]
        warnings.append(f"source_policy missing; defaulting to '{DEFAULT_SOURCE_POLICY}'.")
    invalid_sources = [item for item in source_policy if item not in VALID_EXTERNAL_SOURCE_POLICIES]
    if invalid_sources:
        errors.extend([f"source_policy '{item}' is not registered." for item in invalid_sources])

    output_policy = _list(data.get('output_policy') or data.get('outputs'))
    if not output_policy:
        output_policy = [DEFAULT_OUTPUT_POLICY]
        warnings.append(f"output_policy missing; defaulting to '{DEFAULT_OUTPUT_POLICY}'.")
    invalid_outputs = [item for item in output_policy if item not in VALID_EXTERNAL_OUTPUT_POLICIES]
    if invalid_outputs:
        errors.extend([f"output_policy '{item}' is not registered." for item in invalid_outputs])
    if any(item in RESTRICTED_OUTPUT_POLICIES for item in output_policy):
        warnings.append('replace output policy is restricted and must remain visibly user-enabled before execution.')

    batch_policy = _clean_key(data.get('batch_policy') or data.get('batch'))
    if not batch_policy:
        batch_policy = DEFAULT_BATCH_POLICY
        warnings.append(f"batch_policy missing; defaulting to '{DEFAULT_BATCH_POLICY}'.")
    if batch_policy not in VALID_EXTERNAL_BATCH_POLICIES:
        errors.append(f"batch_policy '{batch_policy}' is not registered.")

    context_policy = _list(data.get('context_policy') or data.get('context_usage'))
    if not context_policy:
        context_policy = list(DEFAULT_CONTEXT_POLICY)
        warnings.append("context_policy missing; defaulting to prompt + model only.")
    invalid_context = [item for item in context_policy if item not in VALID_EXTERNAL_CONTEXT_POLICIES]
    if invalid_context:
        errors.extend([f"context_policy '{item}' is not registered." for item in invalid_context])
    if any(item in RESTRICTED_CONTEXT_POLICIES for item in context_policy):
        warnings.append('identity context is restricted and must be explicitly surfaced in UI before execution.')

    return {
        'policy_version': EXTERNAL_EXTENSION_POLICY_VERSION,
        'source_policy': source_policy,
        'output_policy': output_policy,
        'batch_policy': batch_policy,
        'context_policy': context_policy,
        'defaults_applied': {
            'source_policy': source_policy == [DEFAULT_SOURCE_POLICY] and not _list(data.get('source_policy') or data.get('sources')),
            'output_policy': output_policy == [DEFAULT_OUTPUT_POLICY] and not _list(data.get('output_policy') or data.get('outputs')),
            'batch_policy': batch_policy == DEFAULT_BATCH_POLICY and not _clean_key(data.get('batch_policy') or data.get('batch')),
            'context_policy': context_policy == list(DEFAULT_CONTEXT_POLICY) and not _list(data.get('context_policy') or data.get('context_usage')),
        },
        'restricted': {
            'output_policy': [item for item in output_policy if item in RESTRICTED_OUTPUT_POLICIES],
            'context_policy': [item for item in context_policy if item in RESTRICTED_CONTEXT_POLICIES],
        },
        'warnings': warnings,
        'errors': errors,
        'ok': not errors,
        'raw_policy': _deepcopy(data),
    }


def external_extension_policy_template() -> dict[str, Any]:
    return {
        'policy_version': EXTERNAL_EXTENSION_POLICY_VERSION,
        'source_policy': [DEFAULT_SOURCE_POLICY],
        'output_policy': [DEFAULT_OUTPUT_POLICY],
        'batch_policy': DEFAULT_BATCH_POLICY,
        'context_policy': list(DEFAULT_CONTEXT_POLICY),
        'notes': [
            'External extensions must declare source/output/batch/context policies.',
            'Default behavior is safe: preview output, force_1 batch, prompt+model context only.',
            'Replacement output and identity context require explicit visible UI before execution.',
        ],
    }
