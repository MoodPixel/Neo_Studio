from __future__ import annotations

from copy import deepcopy
from typing import Any

from .extension_manifest import split_external_extension_id
from .external_extension_policies import (
    DEFAULT_BATCH_POLICY,
    DEFAULT_CONTEXT_POLICY,
    DEFAULT_OUTPUT_POLICY,
    DEFAULT_SOURCE_POLICY,
    EXTERNAL_EXTENSION_POLICY_VERSION,
    VALID_EXTERNAL_BATCH_POLICIES,
    VALID_EXTERNAL_CONTEXT_POLICIES,
    VALID_EXTERNAL_OUTPUT_POLICIES,
    VALID_EXTERNAL_SOURCE_POLICIES,
)

from .external_extension_workflow_validator import (
    build_external_extension_validation_context,
    build_external_extension_validation_report,
    validate_external_extension_payload_block,
)

EXTERNAL_EXTENSION_PAYLOAD_VERSION = 'external-extension-payload-v1'
EXTERNAL_EXTENSION_METADATA_VERSION = 'external-extension-metadata-v1'


def _deepcopy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _deepcopy(value) if isinstance(value, dict) else {}


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
        text = str(item or '').strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _clean_key(value: Any) -> str:
    return str(value or '').strip().lower().replace(' ', '_')


def _lookup_key(value: Any) -> str:
    return str(value or '').strip().lower()


def _clean_warning_list(values: Any, *, registry_found: bool = False) -> list[str]:
    warnings = _list(values)
    if not registry_found:
        return warnings
    stale_fragments = {
        'external extension is not registered in the external extension registry.',
    }
    return [warning for warning in warnings if warning.strip().lower() not in stale_fragments]


def _clear_stale_disabled_reason(reason: Any, *, registry_found: bool = False) -> str | None:
    text = str(reason or '').strip()
    if registry_found and text in {'not_registered'}:
        return None
    return text or None


def _registry_aliases_for_record(item: dict[str, Any]) -> list[str]:
    """Return stable lookup aliases for an external extension registry record.

    Generation payloads use manifest ids like image.layerdiffuse. Some older
    registry paths and copied extension folders may expose folder slugs or
    surface/slug pairs. All aliases point to the same validated registry record;
    this does not enable invalid extensions, it only prevents false
    not_registered states caused by key mismatches.
    """
    aliases: list[str] = []
    for key in ('extension_id', 'id'):
        value = str(item.get(key) or '').strip()
        if value:
            aliases.append(value)
    raw_manifest = item.get('raw_manifest') if isinstance(item.get('raw_manifest'), dict) else {}
    for key in ('extension_id', 'id'):
        value = str(raw_manifest.get(key) or '').strip()
        if value:
            aliases.append(value)
    slug = str(item.get('slug') or raw_manifest.get('slug') or '').strip()
    surface = str(item.get('surface') or item.get('target_surface') or raw_manifest.get('surface') or raw_manifest.get('target_surface') or '').strip()
    if surface and slug:
        aliases.append(f'{surface}.{slug}')
    folder = str(item.get('extension_dir') or '').replace('\\', '/').rstrip('/').split('/')[-1].strip()
    if folder:
        aliases.append(folder)
        if surface:
            aliases.append(f'{surface}.{folder}')
    out: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if not alias or alias in seen:
            continue
        seen.add(alias)
        out.append(alias)
    return out


def _registry_records_by_id(external_registry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    registry = external_registry if isinstance(external_registry, dict) else {}
    records: dict[str, dict[str, Any]] = {}
    for bucket in (
        'installed',
        'enabled',
        'disabled',
        'invalid',
        'external_extensions',
        'extension_packs',
        'invalid_extensions',
    ):
        for item in registry.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            for alias in _registry_aliases_for_record(item):
                lookup = _lookup_key(alias)
                if lookup and lookup not in records:
                    records[lookup] = item
    return records


def _fresh_registry_record_for(extension_id: str) -> dict[str, Any]:
    """Best-effort generation-time registry refresh for stale validator snapshots.

    This is intentionally conservative: it only returns records produced by the
    real backend registry builder after a forced rebuild. It does not trust
    frontend state and it does not synthesize a fake enabled extension.
    """
    try:
        from ..utils.extension_registry import build_external_extension_registry, rebuild_extension_registry
    except Exception:
        return {}
    try:
        surface = split_external_extension_id(extension_id).get('surface') or ''
        rebuild_extension_registry()
        refreshed = build_external_extension_registry(surface=surface)
        records = _registry_records_by_id(refreshed)
        return records.get(_lookup_key(extension_id), {})
    except Exception:
        return {}


def _iter_raw_extension_rows(raw_block: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(raw_block, dict):
        return []
    rows: list[tuple[str, dict[str, Any]]] = []
    for key, value in raw_block.items():
        extension_id = str(key or '').strip()
        row = _dict(value)
        if not extension_id:
            extension_id = str(row.get('extension_id') or row.get('id') or '').strip()
        if not extension_id:
            continue
        rows.append((extension_id, row))
    return rows


def normalize_external_extension_payload_entry(
    extension_id: str,
    raw_entry: dict[str, Any] | None = None,
    *,
    registry_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one external extension payload entry without executing it.

    This contract is intentionally transparent: it preserves raw UI state and
    publishes the effective backend state separately. Invalid/disabled entries
    are kept visible but are forced to effective enabled=false so they cannot
    mutate generation behavior.
    """
    extension_id = str(extension_id or '').strip()
    raw = _dict(raw_entry)
    registry = _dict(registry_record) or _fresh_registry_record_for(extension_id)
    registry_found = bool(registry)
    warnings = _clean_warning_list(raw.get('warnings'), registry_found=registry_found)
    disabled_reason = _clear_stale_disabled_reason(raw.get('disabled_reason'), registry_found=registry_found)

    parts = split_external_extension_id(extension_id)
    if not parts.get('surface') or not parts.get('slug'):
        disabled_reason = disabled_reason or 'invalid_extension_id'
        warnings.append('External extension id must match <surface>.<extension_slug>.')

    registry_status = str(registry.get('status') or '').strip().lower()
    registry_enabled = bool(registry.get('enabled', False)) and registry_status == 'enabled'
    if registry:
        if registry.get('disabled_reason') and not disabled_reason:
            disabled_reason = str(registry.get('disabled_reason'))
        warnings.extend(_list(registry.get('warnings') or []))
    else:
        disabled_reason = disabled_reason or 'not_registered'
        warnings.append('External extension is not registered in the external extension registry.')

    requested_enabled = bool(raw.get('enabled', False))
    effective_enabled = requested_enabled and registry_enabled and not disabled_reason

    source = _clean_key(raw.get('source') or raw.get('source_policy') or DEFAULT_SOURCE_POLICY)
    if source not in VALID_EXTERNAL_SOURCE_POLICIES:
        warnings.append(f"External extension source '{source}' is not registered; using '{DEFAULT_SOURCE_POLICY}'.")
        source = DEFAULT_SOURCE_POLICY

    output_policy = _clean_key(raw.get('output_policy') or raw.get('output') or DEFAULT_OUTPUT_POLICY)
    if output_policy not in VALID_EXTERNAL_OUTPUT_POLICIES:
        warnings.append(f"External extension output policy '{output_policy}' is not registered; using '{DEFAULT_OUTPUT_POLICY}'.")
        output_policy = DEFAULT_OUTPUT_POLICY

    batch_policy = _clean_key(raw.get('batch_policy') or raw.get('batch') or registry.get('batch_policy') or DEFAULT_BATCH_POLICY)
    if batch_policy not in VALID_EXTERNAL_BATCH_POLICIES:
        warnings.append(f"External extension batch policy '{batch_policy}' is not registered; using '{DEFAULT_BATCH_POLICY}'.")
        batch_policy = DEFAULT_BATCH_POLICY

    context_policy = _list(raw.get('context_policy') or registry.get('context_policy') or DEFAULT_CONTEXT_POLICY)
    invalid_context = [item for item in context_policy if _clean_key(item) not in VALID_EXTERNAL_CONTEXT_POLICIES]
    if invalid_context:
        warnings.append('External extension context policy contains unregistered values; using prompt + model only.')
        context_policy = list(DEFAULT_CONTEXT_POLICY)

    target_sections = _list(raw.get('target_sections') or registry.get('target_sections') or [])
    raw_state = _dict(raw.get('raw_state')) or {k: _deepcopy(v) for k, v in raw.items() if k not in {'effective_state'}}
    effective_state = _dict(raw.get('effective_state'))
    effective_state.update({
        'enabled': effective_enabled,
        'source': source,
        'target_sections': target_sections,
        'output_policy': output_policy,
        'batch_policy': batch_policy,
        'context_policy': context_policy,
        'policy_version': EXTERNAL_EXTENSION_POLICY_VERSION,
    })

    return {
        'enabled': requested_enabled,
        'effective_enabled': effective_enabled,
        'source': source,
        'target_sections': target_sections,
        'output_policy': output_policy,
        'batch_policy': batch_policy,
        'context_policy': context_policy,
        'policy_version': EXTERNAL_EXTENSION_POLICY_VERSION,
        'raw_state': raw_state,
        'effective_state': effective_state,
        'warnings': _list(warnings),
        'disabled_reason': disabled_reason,
        'payload_version': EXTERNAL_EXTENSION_PAYLOAD_VERSION,
    }


def normalize_external_extension_payload_block(raw_block: Any, *, external_registry: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    records = _registry_records_by_id(external_registry)
    normalized: dict[str, dict[str, Any]] = {}
    for extension_id, raw_entry in _iter_raw_extension_rows(raw_block):
        normalized[extension_id] = normalize_external_extension_payload_entry(
            extension_id,
            raw_entry,
            registry_record=records.get(_lookup_key(extension_id)),
        )
    return normalized


def build_external_extension_metadata_shell(block: dict[str, dict[str, Any]] | None = None, *, validation_report: dict[str, Any] | None = None) -> dict[str, Any]:
    block = block if isinstance(block, dict) else {}
    validation = validation_report if isinstance(validation_report, dict) else {}
    active = [extension_id for extension_id, entry in block.items() if isinstance(entry, dict) and entry.get('effective_enabled')]
    disabled = [extension_id for extension_id, entry in block.items() if isinstance(entry, dict) and not entry.get('effective_enabled')]
    warnings: list[str] = []
    disabled_reasons: dict[str, str] = {}
    raw_state: dict[str, Any] = {}
    effective_state: dict[str, Any] = {}
    validation_state: dict[str, Any] = {}
    for extension_id, entry in block.items():
        if not isinstance(entry, dict):
            continue
        raw_state[extension_id] = _dict(entry.get('raw_state'))
        effective_state[extension_id] = _dict(entry.get('effective_state'))
        validation_state[extension_id] = _dict(entry.get('workflow_validation'))
        reason = str(entry.get('disabled_reason') or '').strip()
        if reason:
            disabled_reasons[extension_id] = reason
        for warning in _list(entry.get('warnings')):
            warnings.append(f'{extension_id}: {warning}')
    return {
        'active': active,
        'disabled': disabled,
        'disabled_reasons': disabled_reasons,
        'warnings': warnings,
        'raw_state': raw_state,
        'effective_state': effective_state,
        'validation': validation,
        'validation_state': validation_state,
        'payload_version': EXTERNAL_EXTENSION_PAYLOAD_VERSION,
        'metadata_version': EXTERNAL_EXTENSION_METADATA_VERSION,
    }


def build_external_extension_output_metadata_shell(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the output-safe external extension audit shell.

    This is safe to store on output sidecars and library records. It does not
    execute extension logic and does not include workflow graph mutations.
    """
    payload = payload if isinstance(payload, dict) else {}
    block = payload.get('external_extensions') if isinstance(payload.get('external_extensions'), dict) else {}
    existing = payload.get('_neo_external_extensions') if isinstance(payload.get('_neo_external_extensions'), dict) else {}
    validation = payload.get('_neo_external_extensions_validation') if isinstance(payload.get('_neo_external_extensions_validation'), dict) else {}
    shell = build_external_extension_metadata_shell(block, validation_report=validation)
    if existing:
        # Preserve any already-stamped shell fields, then refresh canonical raw/effective/validation data.
        merged = _dict(existing)
        merged.update(shell)
        shell = merged
    shell['output_metadata_policy'] = 'audit_only_no_execution_no_hidden_mutation'
    shell['visible'] = True
    return shell


def stamp_external_extension_payload_contract(payload: dict[str, Any], *, external_registry: dict[str, Any] | None = None, validation_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach the transparent external-extension payload shell to a generation payload.

    This is additive and safe for Phase 1: it does not call extension code, does
    not rewrite workflow settings, and marks disabled/invalid extensions as
    non-effective instead of silently removing them.
    """
    if not isinstance(payload, dict):
        return {}
    raw_block = payload.get('external_extensions')
    if not isinstance(raw_block, dict):
        image_state = payload.get('image_state') if isinstance(payload.get('image_state'), dict) else {}
        modules = image_state.get('modules') if isinstance(image_state.get('modules'), dict) else {}
        raw_block = modules.get('external_extensions') if isinstance(modules.get('external_extensions'), dict) else {}
    normalized = normalize_external_extension_payload_block(raw_block, external_registry=external_registry)
    context = validation_context if isinstance(validation_context, dict) else build_external_extension_validation_context(payload)
    normalized = validate_external_extension_payload_block(normalized, external_registry=external_registry, context=context)
    payload['external_extensions'] = normalized
    validation_report = build_external_extension_validation_report(normalized)
    payload['_neo_external_extensions'] = build_external_extension_metadata_shell(normalized, validation_report=validation_report)
    payload['_neo_external_extensions_validation'] = validation_report
    payload['_neo_external_extensions_visible'] = True
    payload['_neo_external_extensions_policy'] = 'transparent_raw_effective_no_hidden_mutation'
    return payload
