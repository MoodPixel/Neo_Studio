from __future__ import annotations

from copy import deepcopy
from typing import Any

from .extension_manifest import VALID_EXTERNAL_TARGET_SECTIONS
from .external_extension_policies import DEFAULT_BATCH_POLICY, DEFAULT_OUTPUT_POLICY, DEFAULT_SOURCE_POLICY

EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION = 'external-extension-workflow-validator-v1'


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

    target_sections = _list(entry.get('target_sections') or registry.get('target_sections') or [])
    unknown_sections = [section for section in target_sections if _key(section) not in VALID_EXTERNAL_TARGET_SECTIONS]
    if unknown_sections:
        effective_enabled = False
        disabled_reason = disabled_reason or 'unknown_target_section:' + ','.join(unknown_sections)

    source = _key(entry.get('source') or DEFAULT_SOURCE_POLICY)
    if effective_enabled and not _source_available(source, context):
        effective_enabled = False
        disabled_reason = f'required_source_unavailable:{source}'

    output_policy = _key(entry.get('output_policy') or DEFAULT_OUTPUT_POLICY)
    raw_state = _dict(entry.get('raw_state'))
    if effective_enabled and output_policy == 'replace' and not raw_state.get('replace_confirmed'):
        effective_enabled = False
        disabled_reason = 'replace_requires_visible_confirmation'

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
    return {
        'ok': not blocked,
        'active': active,
        'blocked': blocked,
        'disabled': disabled,
        'warnings': warnings,
        'auto_fixes': auto_fixes,
        'validator_version': EXTERNAL_EXTENSION_WORKFLOW_VALIDATOR_VERSION,
        'policy': 'block_or_auto_disable_with_visible_reason',
    }
