from __future__ import annotations

from copy import deepcopy
from typing import Any

from .extension_manifest import VALID_EXTERNAL_TARGET_SECTIONS
from .external_extension_policies import DEFAULT_BATCH_POLICY, DEFAULT_OUTPUT_POLICY, DEFAULT_SOURCE_POLICY
from .image_extension_compatibility_resolver import (
    IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
    build_image_extension_compatibility_context,
    resolve_image_extension_compatibility,
    resolve_image_extension_block_compatibility,
)

EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION = 'external-extension-workflow-validator-v3'
EXTERNAL_EXTENSION_WORKFLOW_ENFORCEMENT_VERSION = 'external-extension-workflow-enforcement-v1'
OUTPUT_AFFECTING_WORKFLOW_MODES = {'replace_workflow', 'sidecar_run', 'postprocess_output', 'preprocess_source', 'mixed_workflow'}
OUTPUT_MUTATING_POLICIES = {'new_run', 'append', 'replace'}
VISIBLE_CONFIRMATION_WORKFLOW_MODES = {'replace_workflow'}


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


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


def _key(value: Any) -> str:
    return str(value or '').strip().lower().replace(' ', '_')


def _lookup_key(value: Any) -> str:
    return str(value or '').strip().lower()


def _clean_warning_list(values: Any, *, registry_found: bool = False) -> list[str]:
    warnings = _list(values)
    if not registry_found:
        return warnings
    return [
        warning
        for warning in warnings
        if warning.strip().lower() != 'external extension is not registered in the external extension registry.'
    ]


def _clear_stale_disabled_reason(reason: Any, *, registry_found: bool = False) -> str | None:
    text = str(reason or '').strip()
    if registry_found and text == 'not_registered':
        return None
    return text or None


def _supports(allowed: Any, current: Any) -> bool:
    values = [_key(item) for item in _list(allowed) if _key(item)]
    if not values:
        return True
    current_key = _key(current)
    return '*' in values or 'any' in values or current_key in values


def build_external_extension_validation_context(payload: dict[str, Any] | None = None, *, files: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the stable validator context used by backend and docs.

    This does not inspect or mutate Comfy workflows. It only resolves the raw
    generation state required to decide whether an external extension is allowed
    to remain effective.
    """
    payload = payload if isinstance(payload, dict) else {}
    files = files if isinstance(files, dict) else {}
    workflow = _key(payload.get('mode') or payload.get('workflow_type') or payload.get('_neo_image_command_type') or 'txt2img') or 'txt2img'
    family = _key(payload.get('family') or payload.get('model_family') or payload.get('generation_family') or 'sdxl_sd') or 'sdxl_sd'
    batch_size = payload.get('batch_size') or payload.get('batch') or payload.get('batchSize') or 1
    try:
        batch_size = int(batch_size)
    except Exception:
        batch_size = 1
    source_name = payload.get('source_image_name') or payload.get('init_image_name') or payload.get('input_image_name')
    selected_output = payload.get('generationSelectedOutputSnapshot') or payload.get('selected_output_snapshot')
    prompt = payload.get('prompt') or payload.get('positive') or payload.get('positive_prompt')
    return {
        'surface': _key(payload.get('surface') or 'image') or 'image',
        'workflow': workflow,
        'workflow_type': workflow,
        'family': family,
        'model_family': family,
        'batch_size': max(1, batch_size),
        'has_prompt': bool(str(prompt or '').strip()),
        'prompt_available': bool(str(prompt or '').strip()),
        'has_source_image': bool(source_name or files.get('source_image') or files.get('image_file') or files.get('image_files')),
        'source_image_available': bool(source_name or files.get('source_image') or files.get('image_file') or files.get('image_files')),
        'selected_output_available': bool(selected_output or files.get('selected_output')),
        'command_type': _key(payload.get('_neo_image_command_type') or ''),
    }


def _source_available(source: str, context: dict[str, Any]) -> bool:
    source = _key(source or DEFAULT_SOURCE_POLICY)
    if source in {'none', 'prompt'}:
        return True if source == 'none' else bool(context.get('prompt_available') or context.get('has_prompt'))
    if source in {'selected_image', 'upload', 'source_image'}:
        return bool(context.get('source_image_available') or context.get('has_source_image'))
    if source == 'output':
        return bool(context.get('selected_output_available'))
    return True



def _first_key(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                hit = _key(item)
                if hit:
                    return hit
        else:
            hit = _key(value)
            if hit:
                return hit
    return ''


def _metadata_blocks(entry: dict[str, Any], registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workflow = _dict(entry.get('workflow')) or _dict(registry.get('workflow'))
    output = _dict(entry.get('output')) or _dict(registry.get('output'))
    visibility = _dict(entry.get('output_visibility')) or _dict(registry.get('output_visibility'))
    return workflow, output, visibility


def _required_comfy_nodes(registry: dict[str, Any]) -> list[str]:
    nodes: list[str] = []
    comfy = _dict(registry.get('comfy'))
    deps = _dict(registry.get('dependencies'))
    raw = _dict(registry.get('raw_manifest'))
    for value in (
        registry.get('required_comfy_nodes'),
        registry.get('requires_nodes'),
        registry.get('required_nodes'),
        comfy.get('requires_nodes'),
        deps.get('comfy_nodes'),
        deps.get('nodes'),
        raw.get('required_comfy_nodes'),
        raw.get('requires_nodes'),
        _dict(raw.get('comfy')).get('requires_nodes'),
    ):
        nodes.extend(_list(value))
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        key = _lookup_key(node)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(node)
    return out


def _missing_comfy_nodes(registry: dict[str, Any], context: dict[str, Any]) -> list[str]:
    required = _required_comfy_nodes(registry)
    if not required:
        return []
    available_raw = context.get('available_comfy_nodes') or context.get('comfy_nodes_available') or context.get('available_nodes')
    if available_raw is None:
        # No capability snapshot means the runtime cannot prove a missing node.
        # Keep this as visible validation metadata without hard-blocking here.
        return []
    available = {_lookup_key(item) for item in _list(available_raw)}
    return [node for node in required if _lookup_key(node) not in available]


def _entry_workflow_mode(entry: dict[str, Any], registry: dict[str, Any]) -> str:
    workflow, _output, _visibility = _metadata_blocks(entry, registry)
    patch = _dict(entry.get('workflow_patch'))
    strategies = [_key(item) for item in _list(workflow.get('patch_strategies')) if _key(item)]
    return _first_key(
        entry.get('workflow_mode'),
        workflow.get('mode'),
        patch.get('strategy'),
        strategies,
        registry.get('workflow_mode'),
        'metadata_only',
    )


def _entry_output_policy(entry: dict[str, Any], registry: dict[str, Any]) -> str:
    _workflow, output, _visibility = _metadata_blocks(entry, registry)
    return _first_key(
        entry.get('output_policy'),
        output.get('policy'),
        output.get('default_policy'),
        registry.get('output_policy_default'),
        registry.get('output_policy'),
        DEFAULT_OUTPUT_POLICY,
    )


def _entry_target(entry: dict[str, Any], registry: dict[str, Any]) -> str:
    workflow, _output, _visibility = _metadata_blocks(entry, registry)
    return _first_key(
        entry.get('target'),
        workflow.get('target'),
        registry.get('target'),
        registry.get('supported_workflows'),
        entry.get('target_sections'),
        registry.get('target_sections'),
    )


def _entry_output_affecting(entry: dict[str, Any], registry: dict[str, Any]) -> bool:
    workflow, output, _visibility = _metadata_blocks(entry, registry)
    mode = _entry_workflow_mode(entry, registry)
    policy = _entry_output_policy(entry, registry)
    return bool(
        output.get('output_affecting')
        or output.get('primary_type')
        or output.get('primary_output_type')
        or output.get('outputs')
        or mode in OUTPUT_AFFECTING_WORKFLOW_MODES
        or policy in OUTPUT_MUTATING_POLICIES
        or workflow.get('patch_count')
    )


def _visibility_errors(entry: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    if not _entry_output_affecting(entry, registry):
        return []
    workflow, output, visibility = _metadata_blocks(entry, registry)
    errors: list[str] = []
    if visibility.get('hidden_behavior_allowed'):
        errors.append('hidden_output_behavior_not_allowed')
    if visibility.get('target_visible') is False:
        errors.append('output_target_must_be_visible')
    if visibility.get('output_policy_visible') is False:
        errors.append('output_policy_must_be_visible')
    if _entry_workflow_mode(entry, registry) in OUTPUT_AFFECTING_WORKFLOW_MODES and visibility.get('workflow_mode_visible') is False:
        errors.append('workflow_mode_must_be_visible')
    if not _entry_target(entry, registry):
        errors.append('output_affecting_extension_missing_target')
    if not _entry_output_policy(entry, registry):
        errors.append('output_affecting_extension_missing_output_policy')
    if _entry_workflow_mode(entry, registry) in VISIBLE_CONFIRMATION_WORKFLOW_MODES and not workflow.get('requires_visible_confirmation') and not _dict(entry.get('raw_state')).get('replace_workflow_confirmed'):
        errors.append('replace_workflow_requires_visible_confirmation')
    return errors

def _registry_aliases_for_record(item: dict[str, Any]) -> list[str]:
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


def _registry_record_for(extension_id: str, registry: dict[str, Any] | None) -> dict[str, Any]:
    registry = registry if isinstance(registry, dict) else {}
    requested = _lookup_key(extension_id)
    for bucket in (
        'enabled',
        'installed',
        'disabled',
        'invalid',
        'external_extensions',
        'extension_packs',
        'invalid_extensions',
    ):
        for item in registry.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            aliases = {_lookup_key(alias) for alias in _registry_aliases_for_record(item)}
            if requested in aliases:
                return item
    return {}


def _fresh_registry_record_for(extension_id: str) -> dict[str, Any]:
    """Force one backend registry rebuild before declaring an extension missing."""
    try:
        from ..utils.extension_registry import build_external_extension_registry, rebuild_extension_registry
    except Exception:
        return {}
    try:
        surface = str(extension_id or '').split('.', 1)[0].strip().lower() if '.' in str(extension_id or '') else ''
        rebuild_extension_registry()
        registry = build_external_extension_registry(surface=surface)
        return _registry_record_for(extension_id, registry)
    except Exception:
        return {}


def validate_external_extension_entry_for_workflow(
    extension_id: str,
    entry: dict[str, Any],
    *,
    registry_record: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one normalized external-extension payload entry.

    Invalid states are not removed. They are made visible and forced to
    effective_enabled=false so workflow mutation cannot occur silently.
    """
    context = context if isinstance(context, dict) else {}
    compat_context = build_image_extension_compatibility_context(context)
    # Keep validation context source/batch fields while adding canonical family/workflow/backend fields.
    compat_context.update({key: value for key, value in context.items() if key not in compat_context})
    entry = _dict(entry)
    registry = _dict(registry_record) or _fresh_registry_record_for(extension_id)
    registry_found = bool(registry)
    warnings = _clean_warning_list(entry.get('warnings'), registry_found=registry_found)
    disabled_reason = _clear_stale_disabled_reason(entry.get('disabled_reason'), registry_found=registry_found)
    effective_enabled = bool(entry.get('effective_enabled'))

    if registry_found and entry.get('enabled') and not effective_enabled:
        # Earlier payload stamps may carry effective_enabled=false only because
        # they were evaluated against a stale registry. Once the backend registry
        # resolves the extension, restart validation from the user's visible
        # enabled state instead of preserving that stale disabled result.
        effective_enabled = True

    status = _key(registry.get('status'))
    if not registry:
        effective_enabled = False
        disabled_reason = disabled_reason or 'not_registered'
    elif status in {'invalid', 'broken'} or not registry.get('manifest_valid', True):
        effective_enabled = False
        disabled_reason = disabled_reason or registry.get('disabled_reason') or 'manifest_invalid'
    elif status == 'missing_dependency':
        effective_enabled = False
        disabled_reason = disabled_reason or registry.get('disabled_reason') or 'missing_dependency'
    elif not registry.get('enabled', False) or status == 'disabled':
        effective_enabled = False
        disabled_reason = disabled_reason or registry.get('disabled_reason') or 'disabled'

    supported_workflows = registry.get('supported_workflows') or []
    if effective_enabled and not _supports(supported_workflows, context.get('workflow') or context.get('workflow_type')):
        effective_enabled = False
        disabled_reason = f"unsupported_workflow:{context.get('workflow') or context.get('workflow_type') or 'unknown'}"

    supported_families = registry.get('supported_model_families') or []
    if effective_enabled and not _supports(supported_families, context.get('family') or context.get('model_family')):
        effective_enabled = False
        disabled_reason = f"unsupported_model_family:{context.get('family') or context.get('model_family') or 'unknown'}"

    compatibility = resolve_image_extension_compatibility(
        extension_id,
        entry,
        registry_record=registry,
        context=compat_context,
    )
    if effective_enabled and compatibility.get('blocked'):
        effective_enabled = False
        disabled_reason = compatibility.get('disabled_reason') or 'extension_compatibility_blocked'
        message = compatibility.get('disabled_message')
        if message:
            warnings.append(message)

    target_sections = _list(entry.get('target_sections') or registry.get('target_sections') or [])
    unknown_sections = [section for section in target_sections if _key(section) not in VALID_EXTERNAL_TARGET_SECTIONS]
    if unknown_sections:
        effective_enabled = False
        disabled_reason = disabled_reason or 'unknown_target_section:' + ','.join(unknown_sections)

    source = _key(entry.get('source') or DEFAULT_SOURCE_POLICY)
    if effective_enabled and not _source_available(source, context):
        effective_enabled = False
        disabled_reason = f'required_source_unavailable:{source}'

    workflow_mode = _entry_workflow_mode(entry, registry)
    output_policy = _entry_output_policy(entry, registry)
    output_target = _entry_target(entry, registry)
    output_affecting = _entry_output_affecting(entry, registry)
    raw_state = _dict(entry.get('raw_state'))
    if effective_enabled and output_policy == 'replace' and not raw_state.get('replace_confirmed'):
        effective_enabled = False
        disabled_reason = 'replace_requires_visible_confirmation'

    visibility_errors = _visibility_errors(entry, registry)
    if effective_enabled and visibility_errors:
        effective_enabled = False
        disabled_reason = disabled_reason or visibility_errors[0]

    missing_nodes = _missing_comfy_nodes(registry, context)
    if effective_enabled and missing_nodes:
        effective_enabled = False
        disabled_reason = 'missing_comfy_nodes:' + ','.join(missing_nodes)

    context_policy = [_key(item) for item in _list(entry.get('context_policy') or registry.get('context_policy') or [])]
    if effective_enabled and 'identity' in context_policy and not raw_state.get('identity_context_confirmed'):
        effective_enabled = False
        disabled_reason = 'identity_context_requires_visible_confirmation'

    batch_policy = _key(entry.get('batch_policy') or registry.get('batch_policy') or DEFAULT_BATCH_POLICY)
    batch_size = int(context.get('batch_size') or 1)
    auto_fixes: list[str] = []
    if batch_size > 1 and batch_policy == 'blocked':
        effective_enabled = False
        disabled_reason = 'batch_blocked'
    elif batch_size > 1 and batch_policy == 'force_1':
        # Phase 1 does not rewrite the main batch field. It exposes the validated
        # effective state so the next execution layer can clamp/block visibly.
        warnings.append('batch_force_1_requires_backend_clamp_or_user_warning')
        auto_fixes.append('effective_batch_size=1')

    effective_state = _dict(entry.get('effective_state'))
    effective_state.update({
        'enabled': effective_enabled,
        'effective_enabled': effective_enabled,
        'validator_version': EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION,
        'workflow': context.get('workflow') or context.get('workflow_type') or '',
        'family': context.get('family') or context.get('model_family') or '',
        'batch_size': batch_size,
        'source_available': _source_available(source, context),
        'workflow_mode': workflow_mode,
        'output_policy': output_policy,
        'output_target': output_target,
        'output_affecting': output_affecting,
        'visibility_errors': visibility_errors,
        'missing_comfy_nodes': missing_nodes,
        'compatibility': compatibility,
        'compatibility_resolver_version': IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        'status_chip': 'Needs node' if missing_nodes else ('Conflict' if disabled_reason and 'conflict' in str(disabled_reason) else ('Blocked' if disabled_reason and not effective_enabled else ('Warning' if compatibility.get('warnings') else 'Ready'))),
        'auto_fixes': auto_fixes,
    })

    entry.update({
        'effective_enabled': effective_enabled,
        'effective_state': effective_state,
        'warnings': _list(warnings),
        'disabled_reason': disabled_reason,
        'workflow_validation': {
            'ok': bool(effective_enabled or not entry.get('enabled')),
            'blocked': bool(entry.get('enabled') and not effective_enabled),
            'disabled_reason': disabled_reason,
            'warnings': _list(warnings),
            'auto_fixes': auto_fixes,
            'visibility_errors': visibility_errors,
            'missing_comfy_nodes': missing_nodes,
            'compatibility': compatibility,
            'compatibility_resolver_version': IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
            'workflow_mode': workflow_mode,
            'output_policy': output_policy,
            'output_target': output_target,
            'output_affecting': output_affecting,
            'context': _copy(context),
            'validator_version': EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION,
        },
    })
    return entry


def validate_external_extension_payload_block(
    block: dict[str, dict[str, Any]] | None,
    *,
    external_registry: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    block = block if isinstance(block, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for extension_id, entry in block.items():
        if not isinstance(entry, dict):
            continue
        out[extension_id] = validate_external_extension_entry_for_workflow(
            extension_id,
            entry,
            registry_record=_registry_record_for(extension_id, external_registry),
            context=context,
        )

    replace_ids = [
        extension_id
        for extension_id, entry in out.items()
        if entry.get('enabled') and _dict(entry.get('effective_state')).get('workflow_mode') == 'replace_workflow'
    ]
    if len(replace_ids) > 1:
        reason = 'workflow_replacement_conflict:' + ','.join(replace_ids)
        for extension_id in replace_ids:
            entry = out[extension_id]
            entry['effective_enabled'] = False
            entry['disabled_reason'] = reason
            warnings = _list(entry.get('warnings'))
            warnings.append('Only one external extension may replace the base workflow per run.')
            entry['warnings'] = warnings
            effective_state = _dict(entry.get('effective_state'))
            effective_state.update({
                'effective_enabled': False,
                'workflow_conflict': True,
                'conflicting_extensions': replace_ids,
                'status_chip': 'Conflict',
            })
            entry['effective_state'] = effective_state
            validation = _dict(entry.get('workflow_validation'))
            validation.update({
                'ok': False,
                'blocked': True,
                'disabled_reason': reason,
                'warnings': warnings,
                'workflow_conflict': True,
                'conflicting_extensions': replace_ids,
            })
            entry['workflow_validation'] = validation
    compatibility_report = resolve_image_extension_block_compatibility(out, external_registry=external_registry, context=context or {})
    for extension_id, result in (compatibility_report.get('results') or {}).items():
        entry = out.get(extension_id)
        if not isinstance(entry, dict):
            continue
        effective_state = _dict(entry.get('effective_state'))
        effective_state['compatibility'] = result
        effective_state['compatibility_resolver_version'] = IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION
        entry['effective_state'] = effective_state
        validation = _dict(entry.get('workflow_validation'))
        validation['compatibility'] = result
        validation['compatibility_resolver_version'] = IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION
        entry['workflow_validation'] = validation
    return out


def build_external_extension_validation_report(block: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    block = block if isinstance(block, dict) else {}
    blocked: list[str] = []
    active: list[str] = []
    warnings: list[str] = []
    disabled: dict[str, str] = {}
    auto_fixes: dict[str, list[str]] = {}
    for extension_id, entry in block.items():
        if not isinstance(entry, dict):
            continue
        if entry.get('effective_enabled'):
            active.append(extension_id)
        reason = str(entry.get('disabled_reason') or '').strip()
        if entry.get('enabled') and not entry.get('effective_enabled'):
            blocked.append(extension_id)
        if reason:
            disabled[extension_id] = reason
        entry_warnings = _list(entry.get('warnings'))
        warnings.extend([f'{extension_id}: {warning}' for warning in entry_warnings])
        fixes = _list(_dict(entry.get('workflow_validation')).get('auto_fixes'))
        if fixes:
            auto_fixes[extension_id] = fixes
    compatibility = {
        extension_id: _dict(_dict(entry.get('effective_state')).get('compatibility'))
        for extension_id, entry in block.items()
        if isinstance(entry, dict) and _dict(_dict(entry.get('effective_state')).get('compatibility'))
    }
    return {
        'ok': not blocked,
        'active': active,
        'blocked': blocked,
        'disabled': disabled,
        'warnings': warnings,
        'auto_fixes': auto_fixes,
        'compatibility': compatibility,
        'compatibility_resolver_version': IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        'validator_version': EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION,
        'policy': 'block_or_auto_disable_with_visible_reason',
    }


def _validation_message_for(extension_id: str, entry: dict[str, Any]) -> str:
    validation = _dict(entry.get('workflow_validation'))
    compatibility = _dict(validation.get('compatibility') or _dict(entry.get('effective_state')).get('compatibility'))
    message = str(compatibility.get('disabled_message') or '').strip()
    reason = str(validation.get('disabled_reason') or entry.get('disabled_reason') or compatibility.get('disabled_reason') or '').strip()
    if message and reason:
        return f'{extension_id} — {message} ({reason})'
    if message:
        return f'{extension_id} — {message}'
    if reason:
        return f'{extension_id} — {reason}'
    return f'{extension_id} — blocked by extension workflow validation'


def build_external_extension_workflow_enforcement_record(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return the Dynamic Workflow Validator enforcement shell for external extensions.

    This function is read-only. It consumes the stamped extension validation
    report and formats the data that queue-time enforcement and UI/debug
    metadata can share.
    """
    payload = payload if isinstance(payload, dict) else {}
    block = payload.get('external_extensions') if isinstance(payload.get('external_extensions'), dict) else {}
    report = payload.get('_neo_external_extensions_validation') if isinstance(payload.get('_neo_external_extensions_validation'), dict) else build_external_extension_validation_report(block)
    blocked_ids = _list(report.get('blocked'))
    blocked_messages = []
    for extension_id in blocked_ids:
        entry = _dict(block.get(extension_id))
        blocked_messages.append(_validation_message_for(extension_id, entry))
    warnings = _list(report.get('warnings'))
    auto_fixes_raw = report.get('auto_fixes') if isinstance(report.get('auto_fixes'), dict) else {}
    auto_fixes = {str(key): _list(value) for key, value in auto_fixes_raw.items()}
    return {
        'version': EXTERNAL_EXTENSION_WORKFLOW_ENFORCEMENT_VERSION,
        'validator_version': EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION,
        'compatibility_resolver_version': IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        'ok': not blocked_ids,
        'blocked': blocked_ids,
        'blocked_messages': blocked_messages,
        'warnings': warnings,
        'auto_fixes': auto_fixes,
        'policy': 'block_enabled_incompatible_extensions_before_workflow_compile',
        'visible': True,
    }


def enforce_external_extension_workflow_validation(payload: dict[str, Any] | None) -> list[str]:
    """Block queue when enabled external extensions are incompatible.

    Earlier phases could mark invalid extensions non-effective. Phase E wires that
    result into the Dynamic Workflow Validator: if the user explicitly enabled an
    extension and the resolver/validator blocks it, generation stops before graph
    compile instead of silently running without the requested extension.
    """
    if not isinstance(payload, dict):
        return []
    record = build_external_extension_workflow_enforcement_record(payload)
    payload['_neo_workflow_validator_external_extensions'] = record
    payload['_neo_dynamic_workflow_validator_external_extensions'] = record
    if not record.get('ok'):
        messages = _list(record.get('blocked_messages'))
        detail = '; '.join(messages) if messages else ', '.join(_list(record.get('blocked')))
        raise ValueError('External extension compatibility blocked this run: ' + (detail or 'unknown extension conflict'))
    notes: list[str] = []
    for warning in _list(record.get('warnings')):
        notes.append('External extension validator warning: ' + warning)
    for extension_id, fixes in (record.get('auto_fixes') or {}).items():
        for fix in _list(fixes):
            notes.append(f'External extension validator auto-fix: {extension_id} {fix}')
    return notes
