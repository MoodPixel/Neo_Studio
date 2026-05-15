from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import re

from .external_workflow_patch_contract import (
    EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION,
    normalize_workflow_patches,
    validate_workflow_patches,
)

from .external_extension_output_contract import EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION

from .external_extension_policies import (
    VALID_EXTERNAL_BATCH_POLICIES,
    VALID_EXTERNAL_CONTEXT_POLICIES,
    VALID_EXTERNAL_OUTPUT_POLICIES,
    VALID_EXTERNAL_SOURCE_POLICIES,
    DEFAULT_BATCH_POLICY,
    DEFAULT_OUTPUT_POLICY,
    DEFAULT_SOURCE_POLICY,
    DEFAULT_CONTEXT_POLICY,
    EXTERNAL_EXTENSION_POLICY_VERSION,
    normalize_external_extension_policies,
)

SCHEMA_VERSION = 1
MANIFEST_FILENAME = 'neo_extension.json'
LEGACY_MANIFEST_FILENAME = 'manifest.json'

VALID_TARGET_SURFACES = {
    'admin', 'image', 'video', 'audio', 'board', 'assistant', 'roleplay', 'library', 'settings', 'system', 'global'
}
VALID_MOUNT_TYPES = {
    'panel', 'toolbar_action', 'sidebar_item', 'surface_tab', 'backend_only', 'comfy_pack', 'workflow_pack'
}
VALID_PERMISSION_KEYS = {
    'filesystem_read', 'filesystem_write', 'network', 'provider_access', 'comfy_access',
    'task_create', 'frontend_injection', 'backend_routes', 'settings_read', 'settings_write',
    'models_read', 'models_write', 'logs_read', 'logs_write'
}

VALID_EXTENSION_TYPES = {'external_extension', 'built_in_module'}

VALID_EXTERNAL_TARGET_SECTIONS = {
    'base_generation', 'build', 'prompt_stack', 'reference', 'finish', 'assets', 'output', 'preview', 'extensions'
}
VALID_EXTERNAL_WORKFLOWS = {'txt2img', 'img2img', 'inpaint', 'outpaint', 'lanpaint', 'any'}
EXTERNAL_MANIFEST_REQUIRED_FIELDS = (
    'id', 'type', 'surface', 'name', 'version', 'target_sections', 'supported_workflows',
    'supported_model_families', 'source_policy', 'output_policy', 'batch_policy'
)

RESERVED_BUILT_IN_EXTENSION_IDS = {
    'scene_director',
    'image.scene_director',
    'neo.scene_director',
}
EXTERNAL_EXTENSION_ID_PATTERN = re.compile(r'^(?P<surface>[a-z][a-z0-9_]*)\.(?P<slug>[a-z][a-z0-9_-]*)$')

EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION = 'external-extension-metadata-adapter-v1'
EXTERNAL_EXTENSION_UI_CONTRACT_VERSION = 'external-extension-ui-contract-v1'
EXTERNAL_EXTENSION_DEFAULT_UI_SHELL = 'standard_collapsible'



def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _clean_text(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _clean_key(value: Any, default: str = '') -> str:
    return _clean_text(value, default).strip().lower().replace(' ', '_')


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
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _lower_list(value: Any) -> list[str]:
    return [_clean_key(item) for item in _list(value) if _clean_key(item)]


def _extension_type_for(data: dict[str, Any], extension_id: str = '') -> str:
    raw_type = _clean_key(data.get('extension_type') or data.get('type'))
    if raw_type in VALID_EXTENSION_TYPES:
        return raw_type
    source = _clean_key(data.get('source'))
    if bool(data.get('built_in', False)) or source in {'built_in', 'built_in_extension', 'builtin', 'system_builtin'}:
        return 'built_in_module'
    return 'external_extension'


def split_external_extension_id(extension_id: str) -> dict[str, str]:
    text = _clean_text(extension_id)
    match = EXTERNAL_EXTENSION_ID_PATTERN.match(text)
    if not match:
        return {'surface': '', 'slug': ''}
    return {'surface': match.group('surface'), 'slug': match.group('slug')}


def is_reserved_extension_id(extension_id: str) -> bool:
    return _clean_text(extension_id).lower() in RESERVED_BUILT_IN_EXTENSION_IDS



def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                hit = _clean_text(item)
                if hit:
                    return hit
        else:
            hit = _clean_text(value)
            if hit:
                return hit
    return ''


def _first_key(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                hit = _clean_key(item)
                if hit:
                    return hit
        else:
            hit = _clean_key(value)
            if hit:
                return hit
    return ''


def _normalize_extension_outputs(value: Any) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value if isinstance(value, list) else ([] if value is None else [value])):
        if isinstance(item, str):
            output = {'type': item, 'role': 'sidecar'}
        elif isinstance(item, dict):
            output = dict(item)
        else:
            continue
        output_type = _clean_key(output.get('type') or output.get('output_type') or output.get('id') or 'unknown')
        role = _clean_key(output.get('role') or 'sidecar')
        output_id = _clean_key(output.get('id') or output.get('key') or f'{role}_{output_type}_{index + 1}')
        key = f'{output_id}:{output_type}:{role}'
        if not output_type or key in seen:
            continue
        seen.add(key)
        outputs.append({
            'id': output_id,
            'type': output_type,
            'role': role,
            'label': _clean_text(output.get('label') or output.get('name') or output_type.replace('_', ' ').title()),
            'required_for': _list(output.get('required_for')),
            'required': bool(output.get('required', False)),
        })
    return outputs


def normalize_extension_metadata_adapter(
    data: dict[str, Any] | None,
    *,
    source_policy: list[str] | None = None,
    output_policy: list[str] | None = None,
    batch_policy: str = '',
    context_policy: list[str] | None = None,
    target_sections: list[str] | None = None,
    supported_workflows: list[str] | None = None,
    workflow_patches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the global UI/workflow/output metadata adapter block.

    This is intentionally extension-agnostic. It adapts existing manifest fields
    into the visible shell contract used by all external extension panels.
    Extension-specific adapters may still provide effective runtime state later,
    but they must not be required just to show target/output/workflow metadata.
    """
    raw = _dict(data)
    ui_raw = _dict(raw.get('ui'))
    workflow_raw = _dict(raw.get('workflow'))
    output_raw = _dict(raw.get('output'))
    visibility_raw = _dict(raw.get('output_visibility') or raw.get('visibility_contract'))
    patches = workflow_patches or []
    outputs = _normalize_extension_outputs(raw.get('outputs') or output_raw.get('outputs'))
    if not outputs:
        for patch in patches:
            outputs.extend(_normalize_extension_outputs(patch.get('outputs') if isinstance(patch, dict) else None))

    patch_strategies = [_clean_key(patch.get('strategy')) for patch in patches if isinstance(patch, dict) and _clean_key(patch.get('strategy'))]
    default_workflow_mode = _first_key(
        workflow_raw.get('mode'),
        raw.get('workflow_mode'),
        raw.get('default_workflow_mode'),
        raw.get('default_patch_strategy'),
        patch_strategies,
        'metadata_only',
    )
    if len(set(patch_strategies)) > 1 and not _first_key(workflow_raw.get('mode'), raw.get('workflow_mode'), raw.get('default_workflow_mode'), raw.get('default_patch_strategy')):
        default_workflow_mode = 'mixed_workflow'

    primary_output_type = _first_key(
        output_raw.get('primary_type'),
        output_raw.get('primary_output_type'),
        raw.get('primary_output_type'),
        [output.get('type') for output in outputs if output.get('role') == 'primary'],
        [output.get('type') for output in outputs],
    )
    default_output_policy = _first_key(
        output_raw.get('policy'),
        output_raw.get('default_policy'),
        raw.get('default_output_policy'),
        raw.get('output_policy_default'),
        'new_run' if 'new_run' in (output_policy or []) else (output_policy or []),
    )
    default_target = _first_key(
        workflow_raw.get('target'),
        raw.get('target'),
        raw.get('workflow_target'),
        supported_workflows or [],
        target_sections or [],
    )
    output_affecting = bool(
        outputs
        or default_workflow_mode not in {'metadata_only', 'none'}
        or any(policy in {'new_run', 'append', 'replace'} for policy in (output_policy or []))
    )

    ui_contract = {
        'version': _clean_text(ui_raw.get('version') or ui_raw.get('contract') or EXTERNAL_EXTENSION_UI_CONTRACT_VERSION),
        'shell': _clean_key(ui_raw.get('shell') or EXTERNAL_EXTENSION_DEFAULT_UI_SHELL),
        'default_expanded': bool(ui_raw.get('default_expanded', False)),
        'show_status_chips': bool(ui_raw.get('show_status_chips', True)),
        'show_target': bool(ui_raw.get('show_target', True)),
        'show_output_policy': bool(ui_raw.get('show_output_policy', True)),
        'show_validation': bool(ui_raw.get('show_validation', True)),
        'show_payload_details': bool(ui_raw.get('show_payload_details', False)),
    }
    workflow_contract = {
        'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
        'target': default_target,
        'mode': default_workflow_mode,
        'default_mode': default_workflow_mode,
        'supported_workflows': list(supported_workflows or []),
        'patch_strategies': sorted(set(patch_strategies)),
        'patch_count': len(patches),
        'requires_visible_confirmation': any(bool(patch.get('requires_confirmation')) for patch in patches if isinstance(patch, dict)),
    }
    output_contract = {
        'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
        'policy': default_output_policy,
        'default_policy': default_output_policy,
        'primary_type': primary_output_type,
        'primary_output_type': primary_output_type,
        'outputs': outputs,
        'output_affecting': output_affecting,
        'batch_policy': _clean_key(batch_policy),
    }
    output_visibility = {
        'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
        'active_state_visible': bool(visibility_raw.get('active_state_visible', True)),
        'target_visible': bool(visibility_raw.get('target_visible', output_affecting)),
        'output_policy_visible': bool(visibility_raw.get('output_policy_visible', output_affecting)),
        'workflow_mode_visible': bool(visibility_raw.get('workflow_mode_visible', output_affecting)),
        'primary_output_visible': bool(visibility_raw.get('primary_output_visible', bool(primary_output_type))),
        'batch_policy_visible': bool(visibility_raw.get('batch_policy_visible', bool(batch_policy))),
        'disabled_reason_visible': bool(visibility_raw.get('disabled_reason_visible', True)),
        'hidden_behavior_allowed': False,
    }
    return {
        'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
        'ui': ui_contract,
        'workflow': workflow_contract,
        'output': output_contract,
        'output_visibility': output_visibility,
        'target': default_target,
        'workflow_mode': default_workflow_mode,
        'output_policy_default': default_output_policy,
        'primary_output_type': primary_output_type,
        'batch_policy': _clean_key(batch_policy),
        'source_policy': list(source_policy or []),
        'context_policy': list(context_policy or []),
    }


def extension_manifest_template() -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'id': 'image.extension_name',
        'extension_id': 'image.extension_name',
        'type': 'external_extension',
        'extension_type': 'external_extension',
        'slug': 'extension_name',
        'name': 'Extension Name',
        'version': '1.0.0',
        'author': '',
        'description': '',
        'target_surface': 'image',
        'surface': 'image',
        'target_sections': [],
        'supported_workflows': [],
        'supported_model_families': [],
        'source_policy': [DEFAULT_SOURCE_POLICY],
        'output_policy': [DEFAULT_OUTPUT_POLICY],
        'batch_policy': DEFAULT_BATCH_POLICY,
        'context_policy': list(DEFAULT_CONTEXT_POLICY),
        'ui': {
            'version': EXTERNAL_EXTENSION_UI_CONTRACT_VERSION,
            'shell': EXTERNAL_EXTENSION_DEFAULT_UI_SHELL,
            'default_expanded': False,
            'show_status_chips': True,
            'show_target': True,
            'show_output_policy': True,
            'show_validation': True,
        },
        'workflow': {
            'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
            'target': '',
            'mode': 'metadata_only',
        },
        'output': {
            'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
            'policy': DEFAULT_OUTPUT_POLICY,
            'primary_type': '',
            'outputs': [],
            'output_affecting': False,
        },
        'output_visibility': {
            'metadata_adapter_version': EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION,
            'active_state_visible': True,
            'target_visible': False,
            'output_policy_visible': False,
            'workflow_mode_visible': False,
            'primary_output_visible': False,
            'batch_policy_visible': False,
            'disabled_reason_visible': True,
            'hidden_behavior_allowed': False,
        },
        'ui_schema': {
            'surface': 'image',
            'mount': 'image.extensions.manager',
            'sections': [],
        },
        'workflow_patches': [],
        'workflow_patch_contract_version': EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION,
        'output_contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
        'policy_version': EXTERNAL_EXTENSION_POLICY_VERSION,
        'ui_entry': '',
        'backend_entry': '',
        'target_tab': '',
        'target_subtab': '',
        'mount_type': 'panel',
        'frontend': {
            'entry_js': '',
            'entry_css': '',
            'mount_id': '',
        },
        'backend': {
            'routes': '',
            'adapter': '',
            'healthcheck': '',
        },
        'comfy': {
            'custom_nodes': '',
            'workflows': '',
            'requires_nodes': [],
        },
        'dependencies': {
            'python': [],
            'npm': [],
            'neo_extensions': [],
            'providers': [],
            'comfy_nodes': [],
            'models': [],
            'external_apps': [],
            'notes': [],
        },
        'permissions': [],
        'compatibility': {
            'min_neo_version': '1.0.0',
            'max_neo_version': '',
        },
        'enabled_default': False,
    }


def normalize_extension_manifest(raw: dict[str, Any] | None, *, manifest_path: str = '', source: str = 'manifest') -> dict[str, Any]:
    data = dict(raw or {})
    frontend = _dict(data.get('frontend'))
    backend = _dict(data.get('backend'))
    comfy = _dict(data.get('comfy'))
    dependencies = _dict(data.get('dependencies'))
    compatibility = _dict(data.get('compatibility'))

    extension_id = _clean_text(data.get('id') or data.get('extension_id'))
    extension_type = _extension_type_for(data, extension_id)
    id_parts = split_external_extension_id(extension_id)
    target_surface = _clean_key(data.get('target_surface') or data.get('surface') or id_parts.get('surface'))
    legacy_type_as_mount = _clean_key(data.get('type')) if _clean_key(data.get('type')) not in VALID_EXTENSION_TYPES else ''
    mount_type = _clean_key(data.get('mount_type') or legacy_type_as_mount or ('backend_only' if backend.get('routes') and not frontend.get('entry_js') else 'panel'))
    permissions = _list(data.get('permissions'))
    requires_nodes = _list(comfy.get('requires_nodes') or data.get('requires_nodes') or data.get('required_nodes'))
    target_sections = _lower_list(data.get('target_sections') or data.get('sections') or data.get('injects_sections'))
    supported_workflows = _lower_list(data.get('supported_workflows') or data.get('workflows_supported') or data.get('workflow_modes'))
    supported_model_families = _lower_list(data.get('supported_model_families') or data.get('model_families') or data.get('families') or data.get('allowed_families'))
    policy_contract = normalize_external_extension_policies(data)
    source_policy = policy_contract['source_policy']
    output_policy = policy_contract['output_policy']
    batch_policy = policy_contract['batch_policy']
    context_policy = policy_contract['context_policy']
    ui_entry = _clean_text(frontend.get('entry_js') or data.get('entry_js') or data.get('ui_entry'))
    backend_entry = _clean_text(backend.get('routes') or data.get('backend_routes') or data.get('backend_entry'))
    ui_schema = _dict(data.get('ui_schema'))
    workflow_patches = normalize_workflow_patches(
        data.get('workflow_patches') or data.get('workflow_patch') or data.get('patches') or data.get('workflow_runtime'),
        extension_id=extension_id,
    )
    metadata_adapter = normalize_extension_metadata_adapter(
        data,
        source_policy=source_policy,
        output_policy=output_policy,
        batch_policy=batch_policy,
        context_policy=context_policy,
        target_sections=target_sections,
        supported_workflows=supported_workflows,
        workflow_patches=workflow_patches,
    )

    normalized = {
        'schema_version': int(data.get('schema_version') or SCHEMA_VERSION),
        'record_type': 'extension_manifest',
        'id': extension_id,
        'extension_id': extension_id,
        'type': extension_type,
        'extension_type': extension_type,
        'slug': _clean_key(data.get('slug') or id_parts.get('slug') or ''),
        'reserved': is_reserved_extension_id(extension_id),
        'built_in': extension_type == 'built_in_module',
        'name': _clean_text(data.get('name') or data.get('title') or extension_id),
        'title': _clean_text(data.get('title') or data.get('name') or extension_id),
        'version': _clean_text(data.get('version') or '1.0.0'),
        'author': _clean_text(data.get('author')),
        'description': _clean_text(data.get('description')),
        'target_surface': target_surface,
        'surface': _clean_key(data.get('surface') or target_surface),
        'target_sections': target_sections,
        'supported_workflows': supported_workflows,
        'supported_model_families': supported_model_families,
        'source_policy': source_policy,
        'output_policy': output_policy,
        'batch_policy': batch_policy,
        'context_policy': context_policy,
        'metadata_adapter_version': metadata_adapter['metadata_adapter_version'],
        'ui': metadata_adapter['ui'],
        'workflow': metadata_adapter['workflow'],
        'output': metadata_adapter['output'],
        'output_visibility': metadata_adapter['output_visibility'],
        'workflow_mode': metadata_adapter['workflow_mode'],
        'output_policy_default': metadata_adapter['output_policy_default'],
        'primary_output_type': metadata_adapter['primary_output_type'],
        'ui_schema': ui_schema,
        'workflow_patches': workflow_patches,
        'workflow_patch_contract_version': EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION,
        'output_contract_version': EXTERNAL_EXTENSION_OUTPUT_CONTRACT_VERSION,
        'policy_version': policy_contract['policy_version'],
        'policy_defaults_applied': policy_contract['defaults_applied'],
        'policy_restricted': policy_contract['restricted'],
        'policy_warnings': policy_contract['warnings'],
        'policy_errors': policy_contract['errors'],
        'ui_entry': ui_entry,
        'backend_entry': backend_entry,
        'target_tab': _clean_key(data.get('target_tab') or data.get('workspace')),
        'target_subtab': _clean_key(data.get('target_subtab') or data.get('workspace') or data.get('target_tab')),
        'workspace': _clean_key(data.get('workspace') or data.get('target_subtab') or data.get('target_tab')),
        'mount_type': mount_type,
        'frontend': {
            'entry_js': ui_entry,
            'entry_css': _clean_text(frontend.get('entry_css') or data.get('entry_css')),
            'mount_id': _clean_text(frontend.get('mount_id') or data.get('mount_id')),
        },
        'backend': {
            'routes': backend_entry,
            'adapter': _clean_text(backend.get('adapter') or data.get('adapter') or data.get('adapter_path')),
            'healthcheck': _clean_text(backend.get('healthcheck') or data.get('healthcheck')),
        },
        'comfy': {
            'custom_nodes': _clean_text(comfy.get('custom_nodes') or data.get('comfy_nodes')),
            'workflows': _clean_text(comfy.get('workflows') or data.get('workflows')),
            'requires_nodes': requires_nodes,
        },
        'dependencies': {
            'python': _list(dependencies.get('python')),
            'npm': _list(dependencies.get('npm')),
            'neo_extensions': _list(dependencies.get('neo_extensions') or data.get('requires_extensions')),
            'providers': _list(dependencies.get('providers') or data.get('requires_backends')),
            'comfy_nodes': _list(dependencies.get('comfy_nodes') or dependencies.get('nodes') or data.get('requires_nodes') or comfy.get('requires_nodes')),
            'models': _list(dependencies.get('models') or data.get('requires_models')),
            'external_apps': _list(dependencies.get('external_apps') or dependencies.get('apps') or data.get('requires_apps')),
            'notes': _list(dependencies.get('notes') or data.get('dependency_notes')),
        },
        'permissions': permissions,
        'compatibility': {
            'min_neo_version': _clean_text(compatibility.get('min_neo_version') or data.get('min_neo_version') or '1.0.0'),
            'max_neo_version': _clean_text(compatibility.get('max_neo_version') or data.get('max_neo_version')),
        },
        'enabled_default': bool(data.get('enabled_default', data.get('enabled', False))),
        'manifest_path': _clean_text(manifest_path or data.get('manifest_path')),
        'source': _clean_text(source or data.get('source') or 'manifest'),
        'updated_at': _clean_text(data.get('updated_at') or _now_iso()),
    }
    return normalized


def validate_extension_manifest(raw: dict[str, Any] | None) -> dict[str, Any]:
    manifest = normalize_extension_manifest(raw)
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest['id']:
        errors.append('id is required.')
    elif manifest['extension_type'] == 'external_extension':
        parts = split_external_extension_id(manifest['id'])
        if not parts.get('surface') or not parts.get('slug'):
            errors.append('external extension id must match <surface>.<extension_slug> using lowercase letters, numbers, underscores, or hyphens.')
        elif parts['surface'] != manifest['surface'] and parts['surface'] != manifest['target_surface']:
            errors.append('external extension id surface must match surface/target_surface.')
        if is_reserved_extension_id(manifest['id']):
            errors.append('external extension id is reserved for a built-in Neo module.')
        for field in EXTERNAL_MANIFEST_REQUIRED_FIELDS:
            value = manifest.get(field)
            if field == 'type':
                value = manifest.get('extension_type')
            if field == 'surface':
                value = manifest.get('surface') or manifest.get('target_surface')
            if isinstance(value, list):
                missing = not value
            else:
                missing = not _clean_text(value)
            if missing:
                errors.append(f'external extension manifest missing required field: {field}.')
        warnings.extend(manifest.get('policy_warnings') or [])
        errors.extend(manifest.get('policy_errors') or [])
        for section in manifest['target_sections']:
            if section not in VALID_EXTERNAL_TARGET_SECTIONS:
                errors.append(f"external extension target section '{section}' is not registered.")
        for workflow in manifest['supported_workflows']:
            if workflow not in VALID_EXTERNAL_WORKFLOWS:
                errors.append(f"external extension workflow '{workflow}' is not registered.")
        ui_schema = manifest.get('ui_schema') if isinstance(manifest.get('ui_schema'), dict) else {}
        if ui_schema:
            ui_surface = _clean_key(ui_schema.get('surface') or manifest.get('surface'))
            ui_mount = _clean_text(ui_schema.get('mount') or '')
            ui_sections = ui_schema.get('sections')
            if ui_surface and ui_surface != manifest.get('surface'):
                errors.append('external extension ui_schema.surface must match the manifest surface.')
            if ui_mount and not ui_mount.startswith(f"{manifest.get('surface')}."):
                warnings.append('external extension ui_schema.mount should use the same surface namespace as the manifest.')
            if ui_sections is not None and not isinstance(ui_sections, list):
                errors.append('external extension ui_schema.sections must be a list when provided.')

        output_visibility = manifest.get('output_visibility') if isinstance(manifest.get('output_visibility'), dict) else {}
        output_contract = manifest.get('output') if isinstance(manifest.get('output'), dict) else {}
        workflow_contract = manifest.get('workflow') if isinstance(manifest.get('workflow'), dict) else {}
        if output_contract.get('output_affecting') and output_visibility.get('hidden_behavior_allowed'):
            errors.append('external extension output-affecting behavior cannot allow hidden behavior.')
        if output_contract.get('output_affecting') and not output_visibility.get('target_visible'):
            errors.append('external extension output-affecting behavior must expose target visibility.')
        if output_contract.get('output_affecting') and not output_visibility.get('output_policy_visible'):
            errors.append('external extension output-affecting behavior must expose output policy visibility.')
        if output_contract.get('output_affecting') and not workflow_contract.get('target'):
            warnings.append('external extension output-affecting behavior should declare or infer a workflow target.')

        patch_validation = validate_workflow_patches(manifest.get('workflow_patches') or [], extension_id=manifest.get('id') or '')
        warnings.extend(patch_validation.get('warnings') or [])
        errors.extend(patch_validation.get('errors') or [])

        for source_policy in manifest['source_policy']:
            if source_policy not in VALID_EXTERNAL_SOURCE_POLICIES:
                errors.append(f"external extension source policy '{source_policy}' is not registered.")
        for output_policy in manifest['output_policy']:
            if output_policy not in VALID_EXTERNAL_OUTPUT_POLICIES:
                errors.append(f"external extension output policy '{output_policy}' is not registered.")
        if manifest['batch_policy'] and manifest['batch_policy'] not in VALID_EXTERNAL_BATCH_POLICIES:
            errors.append(f"external extension batch policy '{manifest['batch_policy']}' is not registered.")
        for context_policy in manifest['context_policy']:
            if context_policy not in VALID_EXTERNAL_CONTEXT_POLICIES:
                errors.append(f"external extension context policy '{context_policy}' is not registered.")
    if manifest['extension_type'] not in VALID_EXTENSION_TYPES:
        errors.append('extension type must be external_extension or built_in_module.')
    if not manifest['name']:
        errors.append('name is required.')
    if not manifest['version']:
        errors.append('version is required.')
    if not manifest['target_surface']:
        errors.append('target_surface is required.')
    elif manifest['target_surface'] not in VALID_TARGET_SURFACES:
        warnings.append(f"target_surface '{manifest['target_surface']}' is not in the known surface list.")
    if not manifest['mount_type']:
        errors.append('mount_type is required.')
    elif manifest['mount_type'] not in VALID_MOUNT_TYPES:
        warnings.append(f"mount_type '{manifest['mount_type']}' is custom or unknown.")

    entry_js = manifest['frontend']['entry_js']
    routes = manifest['backend']['routes']
    if manifest['mount_type'] in {'panel', 'toolbar_action', 'sidebar_item', 'surface_tab'} and not entry_js:
        warnings.append('frontend.entry_js is recommended for UI mount types.')
    if manifest['mount_type'] == 'backend_only' and not routes:
        warnings.append('backend.routes is recommended for backend_only extensions.')

    for permission in manifest['permissions']:
        if permission not in VALID_PERMISSION_KEYS:
            warnings.append(f"permission '{permission}' is custom or unknown.")

    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'manifest': manifest}


def manifest_to_extension_pack(manifest: dict[str, Any], *, enabled: bool | None = None) -> dict[str, Any]:
    clean = normalize_extension_manifest(manifest, manifest_path=manifest.get('manifest_path') or '', source=manifest.get('source') or 'manifest')
    providers = clean['dependencies']['providers']
    requires_nodes = clean['comfy']['requires_nodes']
    entry_js = clean['frontend']['entry_js']
    adapter = clean['backend']['adapter']
    routes = clean['backend']['routes']
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'extension_pack',
        'extension_id': clean['id'],
        'type': clean['extension_type'],
        'extension_type': clean['extension_type'],
        'slug': clean.get('slug', ''),
        'reserved': bool(clean.get('reserved', False)),
        'built_in': bool(clean.get('built_in', False)),
        'title': clean['title'] or clean['name'],
        'description': clean['description'],
        'surface': clean['surface'] or clean['target_surface'],
        'target_surface': clean['target_surface'],
        'target_tab': clean['target_tab'],
        'target_subtab': clean['target_subtab'],
        'workspace': clean['workspace'],
        'target_sections': clean['target_sections'],
        'supported_workflows': clean['supported_workflows'],
        'supported_model_families': clean['supported_model_families'],
        'source_policy': clean['source_policy'],
        'output_policy': clean['output_policy'],
        'batch_policy': clean['batch_policy'],
        'context_policy': clean['context_policy'],
        'ui_schema': clean.get('ui_schema') if isinstance(clean.get('ui_schema'), dict) else {},
        'workflow_patches': clean.get('workflow_patches') if isinstance(clean.get('workflow_patches'), list) else [],
        'workflow_patch_contract_version': clean.get('workflow_patch_contract_version', EXTERNAL_WORKFLOW_PATCH_CONTRACT_VERSION),
        'policy_version': clean.get('policy_version', EXTERNAL_EXTENSION_POLICY_VERSION),
        'policy_defaults_applied': clean.get('policy_defaults_applied', {}),
        'policy_restricted': clean.get('policy_restricted', {}),
        'policy_warnings': clean.get('policy_warnings', []),
        'metadata_adapter_version': clean.get('metadata_adapter_version', EXTERNAL_EXTENSION_METADATA_ADAPTER_VERSION),
        'ui': clean.get('ui', {}),
        'workflow': clean.get('workflow', {}),
        'output': clean.get('output', {}),
        'output_visibility': clean.get('output_visibility', {}),
        'workflow_mode': clean.get('workflow_mode', ''),
        'output_policy_default': clean.get('output_policy_default', ''),
        'primary_output_type': clean.get('primary_output_type', ''),
        'ui_entry': clean['ui_entry'],
        'backend_entry': clean['backend_entry'],
        'mount_type': clean['mount_type'],
        'author': clean['author'],
        'permissions': clean['permissions'],
        'requires_backends': providers,
        'requires_nodes': requires_nodes,
        'required_nodes': requires_nodes,
        'requires_extensions': clean['dependencies']['neo_extensions'],
        'dependencies': clean['dependencies'],
        'dependency_notes': {
            'python': clean['dependencies']['python'],
            'npm': clean['dependencies']['npm'],
            'neo_extensions': clean['dependencies']['neo_extensions'],
            'providers': clean['dependencies']['providers'],
            'comfy_nodes': clean['dependencies']['comfy_nodes'],
            'models': clean['dependencies']['models'],
            'external_apps': clean['dependencies']['external_apps'],
            'notes': clean['dependencies']['notes'],
        },
        'ui_entry': entry_js,
        'entry_css': clean['frontend']['entry_css'],
        'backend_routes': routes,
        'adapter': adapter,
        'adapter_path': adapter,
        'manifest_path': clean['manifest_path'],
        'source': clean['source'],
        'version': clean['version'],
        'min_neo_version': clean['compatibility']['min_neo_version'],
        'max_neo_version': clean['compatibility']['max_neo_version'],
        'enabled': clean['enabled_default'] if enabled is None else bool(enabled),
        'updated_at': clean['updated_at'],
    }


def manifest_relative_path(manifest: Path, app_dir: Path) -> str:
    try:
        return str(manifest.relative_to(app_dir)).replace('\\', '/')
    except Exception:
        return str(manifest).replace('\\', '/')
