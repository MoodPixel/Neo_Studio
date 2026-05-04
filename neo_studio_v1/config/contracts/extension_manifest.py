from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_FILENAME = 'neo_extension.json'
LEGACY_MANIFEST_FILENAME = 'manifest.json'

VALID_TARGET_SURFACES = {
    'admin', 'image', 'video', 'audio', 'board', 'assistant', 'roleplay', 'library', 'settings', 'system'
}
VALID_MOUNT_TYPES = {
    'panel', 'toolbar_action', 'sidebar_item', 'surface_tab', 'backend_only', 'comfy_pack', 'workflow_pack'
}
VALID_PERMISSION_KEYS = {
    'filesystem_read', 'filesystem_write', 'network', 'provider_access', 'comfy_access',
    'task_create', 'frontend_injection', 'backend_routes', 'settings_read', 'settings_write',
    'models_read', 'models_write', 'logs_read', 'logs_write'
}


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


def extension_manifest_template() -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'id': 'author.extension_name',
        'name': 'Extension Name',
        'version': '1.0.0',
        'author': '',
        'description': '',
        'target_surface': 'image',
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
    target_surface = _clean_key(data.get('target_surface') or data.get('surface'))
    mount_type = _clean_key(data.get('mount_type') or data.get('type') or ('backend_only' if backend.get('routes') and not frontend.get('entry_js') else 'panel'))
    permissions = _list(data.get('permissions'))
    requires_nodes = _list(comfy.get('requires_nodes') or data.get('requires_nodes') or data.get('required_nodes'))

    normalized = {
        'schema_version': int(data.get('schema_version') or SCHEMA_VERSION),
        'record_type': 'extension_manifest',
        'id': extension_id,
        'extension_id': extension_id,
        'name': _clean_text(data.get('name') or data.get('title') or extension_id),
        'title': _clean_text(data.get('title') or data.get('name') or extension_id),
        'version': _clean_text(data.get('version') or '1.0.0'),
        'author': _clean_text(data.get('author')),
        'description': _clean_text(data.get('description')),
        'target_surface': target_surface,
        'surface': _clean_key(data.get('surface') or target_surface),
        'target_tab': _clean_key(data.get('target_tab') or data.get('workspace')),
        'target_subtab': _clean_key(data.get('target_subtab') or data.get('workspace') or data.get('target_tab')),
        'workspace': _clean_key(data.get('workspace') or data.get('target_subtab') or data.get('target_tab')),
        'mount_type': mount_type,
        'frontend': {
            'entry_js': _clean_text(frontend.get('entry_js') or data.get('entry_js') or data.get('ui_entry')),
            'entry_css': _clean_text(frontend.get('entry_css') or data.get('entry_css')),
            'mount_id': _clean_text(frontend.get('mount_id') or data.get('mount_id')),
        },
        'backend': {
            'routes': _clean_text(backend.get('routes') or data.get('backend_routes')),
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
        'title': clean['title'] or clean['name'],
        'description': clean['description'],
        'surface': clean['surface'] or clean['target_surface'],
        'target_surface': clean['target_surface'],
        'target_tab': clean['target_tab'],
        'target_subtab': clean['target_subtab'],
        'workspace': clean['workspace'],
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
