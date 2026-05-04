from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from ..contracts.extension_packs import normalize_extension_pack, normalize_workflow_pack

APP_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = APP_DIR.parent
EXTERNAL_EXTENSIONS_DIR = ROOT_DIR / 'neo_extensions'
INSTALLED_DIR = EXTERNAL_EXTENSIONS_DIR / 'installed'
DISABLED_DIR = EXTERNAL_EXTENSIONS_DIR / 'disabled'
CACHE_DIR = EXTERNAL_EXTENSIONS_DIR / 'cache'
LEGACY_EXTENSIONS_DIR = APP_DIR / 'extensions'
DATA_DIR = ROOT_DIR / 'neo_library_data' / 'studio_user_data'
LOG_DIR = DATA_DIR / 'extension_logs'
REGISTRY_PATH = DATA_DIR / 'extension_registry.json'
MANIFEST_FILENAMES = ('neo_extension.json', 'manifest.json')

REGISTRY_SCHEMA_VERSION = 2
VALID_STATUSES = {'enabled', 'disabled', 'broken', 'missing_dependency', 'version_mismatch'}
REQUIRED_MANIFEST_FIELDS = ('id', 'name', 'version', 'target_surface', 'mount_type')
KNOWN_PERMISSION_NAMES = {
    'filesystem_read', 'filesystem_write', 'network', 'provider_access', 'comfy_access',
    'task_creation', 'frontend_injection', 'backend_routes', 'comfy', 'filesystem_readonly',
    'filesystem_writeable', 'settings_read', 'settings_write',
}
KNOWN_MOUNT_TYPES = {'panel', 'toolbar', 'sidebar', 'surface', 'backend', 'workflow_pack', 'node_pack'}
KNOWN_SURFACES = {'image', 'audio', 'video', 'board', 'assistant', 'admin', 'global', 'new_surface'}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        if not path.exists():
            return fallback
        with path.open('r', encoding='utf-8') as handle:
            return json.load(handle)
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    tmp.replace(path)


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or '').strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out



def _clean_relative_path(value: Any) -> str:
    """Return a safe extension-relative path for frontend/backend entries."""
    text = str(value or '').strip().replace('\\', '/')
    if not text or text.startswith('/') or '..' in Path(text).parts:
        return ''
    return text


def _asset_url(extension_id: str, relative_path: str) -> str:
    relative_path = _clean_relative_path(relative_path)
    if not extension_id or not relative_path:
        return ''
    return f"/api/extensions/assets/{quote(extension_id, safe='')}/{quote(relative_path, safe='/')}"


def _extension_relative_path(extension_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(extension_dir.resolve()).as_posix()
    except Exception:
        return ''


def _workflow_id_from(extension_id: str, relative_path: str, fallback: str = '') -> str:
    base = fallback or Path(relative_path).stem or 'workflow'
    clean = ''.join(ch.lower() if ch.isalnum() else '_' for ch in base).strip('_') or 'workflow'
    ext_key = ''.join(ch.lower() if ch.isalnum() else '_' for ch in extension_id).strip('_') or 'extension'
    return f'{ext_key}.{clean}'


def _read_workflow_meta(path: Path) -> dict[str, Any]:
    """Best-effort workflow metadata reader. It never fails extension scanning."""
    data = _read_json(path, {})
    return data if isinstance(data, dict) else {}


def _workflow_pack_from_file(*, extension_id: str, extension_dir: Path, workflow_file: Path, manifest: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = defaults or {}
    relative_path = _extension_relative_path(extension_dir, workflow_file)
    meta = _read_workflow_meta(workflow_file)
    declared_id = str(defaults.get('workflow_id') or meta.get('workflow_id') or meta.get('id') or '').strip()
    title = str(defaults.get('title') or meta.get('title') or meta.get('name') or workflow_file.stem.replace('_', ' ').replace('-', ' ').title()).strip()
    return normalize_workflow_pack({
        'workflow_id': declared_id or _workflow_id_from(extension_id, relative_path, workflow_file.stem),
        'title': title,
        'description': str(defaults.get('description') or meta.get('description') or '').strip(),
        'surface': str(defaults.get('surface') or defaults.get('target_surface') or manifest.get('target_surface') or manifest.get('surface') or '').strip().lower(),
        'target_surface': str(defaults.get('target_surface') or defaults.get('surface') or manifest.get('target_surface') or manifest.get('surface') or '').strip().lower(),
        'target_tab': str(defaults.get('target_tab') or defaults.get('workspace') or manifest.get('target_tab') or manifest.get('workspace') or manifest.get('target_subtab') or '').strip().lower(),
        'family': str(defaults.get('family') or meta.get('family') or '').strip().lower(),
        'mode': str(defaults.get('mode') or meta.get('mode') or '').strip().lower(),
        'backend_role': str(defaults.get('backend_role') or defaults.get('backend') or meta.get('backend_role') or meta.get('backend') or manifest.get('backend_role') or '').strip().lower(),
        'family': str(defaults.get('family') or meta.get('family') or manifest.get('family') or '').strip().lower(),
        'families': _string_list(defaults.get('families') or defaults.get('allowed_families') or meta.get('families') or manifest.get('families') or manifest.get('allowed_families') or []),
        'allowed_families': _string_list(defaults.get('allowed_families') or defaults.get('families') or meta.get('allowed_families') or manifest.get('allowed_families') or manifest.get('families') or []),
        'blocked_families': _string_list(defaults.get('blocked_families') or defaults.get('disabled_families') or meta.get('blocked_families') or manifest.get('blocked_families') or manifest.get('disabled_families') or []),
        'disabled_families': _string_list(defaults.get('disabled_families') or defaults.get('blocked_families') or meta.get('disabled_families') or manifest.get('disabled_families') or manifest.get('blocked_families') or []),
        'optional_nodes': _string_list(defaults.get('optional_nodes') or meta.get('optional_nodes') or manifest.get('optional_nodes') or []),
        'feature_key': str(defaults.get('feature_key') or meta.get('feature_key') or '').strip(),
        'payload_key': str(defaults.get('payload_key') or meta.get('payload_key') or '').strip(),
        'module_payload_key': str(defaults.get('module_payload_key') or meta.get('module_payload_key') or '').strip(),
        'ui_card': str(defaults.get('ui_card') or meta.get('ui_card') or '').strip(),
        'owner_module': str(defaults.get('owner_module') or meta.get('owner_module') or '').strip(),
        'workflow_path': relative_path,
        'workflow_file': workflow_file.name,
        'workflow_kind': str(defaults.get('workflow_kind') or defaults.get('kind') or meta.get('workflow_kind') or meta.get('kind') or 'workflow').strip().lower(),
        'imported_from': extension_id,
        'requires_nodes': _string_list(defaults.get('requires_nodes') or meta.get('requires_nodes') or manifest.get('requires_nodes') or []),
        'requires_extensions': [extension_id],
        'sections': _string_list(defaults.get('sections') or meta.get('sections') or []),
        'tags': _string_list(defaults.get('tags') or meta.get('tags') or []),
        'source': 'extension_workflow_import',
        'version': str(defaults.get('version') or meta.get('version') or manifest.get('version') or '1.0').strip(),
        'enabled': bool(defaults.get('enabled', meta.get('enabled', True))),
    })


def _collect_workflow_packs_from_manifest(record: dict[str, Any], extension_dir: Path) -> list[dict[str, Any]]:
    """Collect workflow packs declared directly or imported from workflow folders/files."""
    raw = record.get('raw_manifest') if isinstance(record.get('raw_manifest'), dict) else {}
    extension_id = str(record.get('extension_id') or record.get('id') or extension_dir.name).strip()
    if not extension_id:
        return []
    packs: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def add_pack(pack: dict[str, Any]) -> None:
        if not isinstance(pack, dict):
            return
        packs.append(pack)

    # Explicit manifest workflow_packs keep working.
    for workflow in raw.get('workflow_packs') or []:
        if isinstance(workflow, dict):
            item = dict(workflow)
            if not item.get('requires_extensions'):
                item['requires_extensions'] = [extension_id]
            if not item.get('surface') and raw.get('target_surface'):
                item['surface'] = raw.get('target_surface')
            if not item.get('target_surface') and raw.get('target_surface'):
                item['target_surface'] = raw.get('target_surface')
            if not item.get('target_tab'):
                item['target_tab'] = raw.get('target_tab') or raw.get('workspace') or raw.get('target_subtab') or ''
            add_pack(normalize_workflow_pack(item, source='extension_manifest'))

    declared = raw.get('workflows')
    workflow_folder = raw.get('workflow_folder') or raw.get('workflows_dir') or ''
    workflow_defaults: dict[str, Any] = {}
    if isinstance(declared, dict):
        workflow_folder = declared.get('folder') or declared.get('dir') or declared.get('path') or workflow_folder
        workflow_defaults = declared
        for item in declared.get('items') or []:
            if isinstance(item, dict):
                path_text = _clean_relative_path(item.get('path') or item.get('file') or '')
                if path_text:
                    workflow_path = (extension_dir / path_text).resolve()
                    if workflow_path.exists() and workflow_path.is_file():
                        seen_paths.add(str(workflow_path))
                        add_pack(_workflow_pack_from_file(extension_id=extension_id, extension_dir=extension_dir, workflow_file=workflow_path, manifest=raw, defaults={**workflow_defaults, **item}))
                else:
                    explicit = dict(item)
                    explicit.setdefault('requires_extensions', [extension_id])
                    explicit.setdefault('surface', raw.get('target_surface') or raw.get('surface') or '')
                    explicit.setdefault('target_surface', raw.get('target_surface') or raw.get('surface') or '')
                    explicit.setdefault('target_tab', raw.get('target_tab') or raw.get('workspace') or raw.get('target_subtab') or '')
                    add_pack(normalize_workflow_pack(explicit, source='extension_manifest'))
    elif isinstance(declared, list):
        for item in declared:
            if isinstance(item, dict):
                path_text = _clean_relative_path(item.get('path') or item.get('file') or '')
                if path_text:
                    workflow_path = (extension_dir / path_text).resolve()
                    if workflow_path.exists() and workflow_path.is_file():
                        seen_paths.add(str(workflow_path))
                        add_pack(_workflow_pack_from_file(extension_id=extension_id, extension_dir=extension_dir, workflow_file=workflow_path, manifest=raw, defaults=item))
                else:
                    explicit = dict(item)
                    explicit.setdefault('requires_extensions', [extension_id])
                    explicit.setdefault('surface', raw.get('target_surface') or raw.get('surface') or '')
                    explicit.setdefault('target_surface', raw.get('target_surface') or raw.get('surface') or '')
                    explicit.setdefault('target_tab', raw.get('target_tab') or raw.get('workspace') or raw.get('target_subtab') or '')
                    add_pack(normalize_workflow_pack(explicit, source='extension_manifest'))

    # Comfy workflow folder from manifest standard.
    comfy = raw.get('comfy') if isinstance(raw.get('comfy'), dict) else {}
    workflow_folder = workflow_folder or comfy.get('workflows') or raw.get('comfy_workflows') or ''
    workflow_folder = _clean_relative_path(workflow_folder)
    if workflow_folder:
        folder_path = (extension_dir / workflow_folder).resolve()
        try:
            if folder_path.exists() and folder_path.is_dir() and extension_dir.resolve() in folder_path.parents:
                for workflow_file in sorted(folder_path.rglob('*.json'), key=lambda p: p.as_posix().lower()):
                    if str(workflow_file.resolve()) in seen_paths:
                        continue
                    seen_paths.add(str(workflow_file.resolve()))
                    add_pack(_workflow_pack_from_file(extension_id=extension_id, extension_dir=extension_dir, workflow_file=workflow_file, manifest=raw, defaults=workflow_defaults))
        except Exception:
            pass
    return packs

def _registry_template() -> dict[str, Any]:
    return {
        'schema_version': REGISTRY_SCHEMA_VERSION,
        'record_type': 'neo_extension_registry',
        'updated_at': _now_iso(),
        'extension_packs': [],
        'workflow_packs': [],
        'sources': {
            'installed_dir': str(INSTALLED_DIR),
            'disabled_dir': str(DISABLED_DIR),
            'legacy_extensions_dir': str(LEGACY_EXTENSIONS_DIR),
            'cache_dir': str(CACHE_DIR),
        },
    }


def _load_registry() -> dict[str, Any]:
    registry = _read_json(REGISTRY_PATH, {})
    if not isinstance(registry, dict):
        registry = {}
    base = _registry_template()
    base.update(registry)
    base['extension_packs'] = registry.get('extension_packs') if isinstance(registry.get('extension_packs'), list) else []
    base['workflow_packs'] = registry.get('workflow_packs') if isinstance(registry.get('workflow_packs'), list) else []
    return base


def _save_registry(registry: dict[str, Any]) -> dict[str, Any]:
    registry['schema_version'] = REGISTRY_SCHEMA_VERSION
    registry['record_type'] = 'neo_extension_registry'
    registry['updated_at'] = _now_iso()
    registry['sources'] = {
        'installed_dir': str(INSTALLED_DIR),
        'disabled_dir': str(DISABLED_DIR),
        'legacy_extensions_dir': str(LEGACY_EXTENSIONS_DIR),
        'cache_dir': str(CACHE_DIR),
    }
    _write_json(REGISTRY_PATH, registry)
    return registry


def _ensure_dirs() -> None:
    for path in (INSTALLED_DIR, DISABLED_DIR, CACHE_DIR, DATA_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def validate_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {'ok': False, 'valid': False, 'errors': ['Manifest must be a JSON object.'], 'warnings': []}
    for field in REQUIRED_MANIFEST_FIELDS:
        if not str(payload.get(field) or payload.get('extension_id' if field == 'id' else field) or '').strip():
            errors.append(f'Missing required field: {field}')
    extension_id = str(payload.get('id') or payload.get('extension_id') or '').strip()
    if extension_id and any(ch.isspace() for ch in extension_id):
        errors.append('id must not contain spaces. Use lowercase snake_case or kebab-case.')
    mount_type = str(payload.get('mount_type') or '').strip().lower()
    if mount_type and mount_type not in KNOWN_MOUNT_TYPES:
        warnings.append(f'Unknown mount_type: {mount_type}')
    target_surface = str(payload.get('target_surface') or payload.get('surface') or '').strip().lower()
    if target_surface and target_surface not in KNOWN_SURFACES:
        warnings.append(f'Unknown target_surface: {target_surface}')
    for permission in _string_list(payload.get('permissions') or []):
        if permission not in KNOWN_PERMISSION_NAMES:
            warnings.append(f'Unknown permission: {permission}')
    return {'ok': len(errors) == 0, 'valid': len(errors) == 0, 'errors': errors, 'warnings': warnings}



def _dependency_notes_from_manifest(payload: dict[str, Any]) -> dict[str, list[str]]:
    """Return display-only dependency notes from extension manifests.

    Phase 14 is intentionally non-installing: Neo only surfaces what an
    extension says it needs so users/devs can install/check items manually.
    """
    deps = payload.get('dependencies') if isinstance(payload.get('dependencies'), dict) else {}
    comfy = payload.get('comfy') if isinstance(payload.get('comfy'), dict) else {}
    def many(*values: Any) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            for item in _string_list(value):
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
        return out
    return {
        'python': many(deps.get('python'), payload.get('python_dependencies')),
        'npm': many(deps.get('npm'), payload.get('npm_dependencies')),
        'neo_extensions': many(deps.get('neo_extensions'), payload.get('requires_extensions')),
        'providers': many(deps.get('providers'), payload.get('requires_backends')),
        'comfy_nodes': many(deps.get('comfy_nodes'), deps.get('nodes'), comfy.get('requires_nodes'), payload.get('requires_nodes'), payload.get('required_nodes')),
        'models': many(deps.get('models'), payload.get('requires_models'), payload.get('models_required')),
        'external_apps': many(deps.get('external_apps'), deps.get('apps'), payload.get('requires_apps'), payload.get('external_apps')),
        'notes': many(deps.get('notes'), payload.get('dependency_notes')),
    }

def _dependency_note_count(notes: dict[str, list[str]]) -> int:
    return sum(len(v) for v in notes.values() if isinstance(v, list))

def _find_manifest(extension_dir: Path) -> Path | None:
    if not extension_dir.is_dir():
        return None
    for filename in MANIFEST_FILENAMES:
        candidate = extension_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _iter_manifest_dirs() -> list[tuple[Path, str, bool]]:
    roots: list[tuple[Path, str, bool]] = [
        (INSTALLED_DIR, 'external', True),
        (DISABLED_DIR, 'external', False),
        (LEGACY_EXTENSIONS_DIR, 'system', True),
    ]
    found: list[tuple[Path, str, bool]] = []
    seen: set[str] = set()
    for root, source, default_enabled in roots:
        if not root.exists():
            continue
        direct_manifest = _find_manifest(root)
        if direct_manifest:
            key = str(root.resolve())
            if key not in seen:
                found.append((root, source, default_enabled))
                seen.add(key)
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith('__'):
                continue
            manifest = _find_manifest(child)
            if manifest:
                key = str(child.resolve())
                if key not in seen:
                    found.append((child, source, default_enabled))
                    seen.add(key)
            # Support legacy grouped extensions: extensions/image/foo/manifest.json
            for grandchild in sorted(child.iterdir(), key=lambda p: p.name.lower()) if child.is_dir() else []:
                if not grandchild.is_dir() or grandchild.name.startswith('__'):
                    continue
                if _find_manifest(grandchild):
                    key = str(grandchild.resolve())
                    if key not in seen:
                        found.append((grandchild, source, default_enabled))
                        seen.add(key)
    return found


def _manifest_to_extension_record(extension_dir: Path, source: str, default_enabled: bool) -> dict[str, Any]:
    manifest_path = _find_manifest(extension_dir)
    payload: dict[str, Any] = {}
    if manifest_path:
        loaded = _read_json(manifest_path, {})
        payload = loaded if isinstance(loaded, dict) else {}
    validation = validate_manifest_payload(payload)
    extension_id = str(payload.get('id') or payload.get('extension_id') or extension_dir.name).strip()
    normalized = normalize_extension_pack(
        payload,
        extension_id=extension_id,
        title=str(payload.get('name') or payload.get('title') or extension_id).strip(),
        source=source,
        manifest_path=str(manifest_path or ''),
        manifest_valid=bool(validation.get('valid')),
        manifest_warnings=validation.get('warnings') or validation.get('errors') or [],
        enabled=bool(payload.get('enabled', default_enabled)),
    )
    normalized['id'] = extension_id
    normalized['name'] = str(payload.get('name') or normalized.get('title') or extension_id).strip()
    normalized['extension_dir'] = str(extension_dir)
    normalized['status'] = _status_for_record(normalized, validation)
    normalized['last_scanned_at'] = _now_iso()
    dependency_notes = _dependency_notes_from_manifest(payload)
    normalized['dependencies'] = dependency_notes
    normalized['dependency_notes'] = dependency_notes
    normalized['dependency_note_count'] = _dependency_note_count(dependency_notes)
    normalized['dependency_status'] = 'notes_only' if normalized['dependency_note_count'] else 'none_declared'
    normalized['entry_js'] = _clean_relative_path(payload.get('entry_js') or payload.get('ui_entry') or '')
    normalized['entry_css'] = _clean_relative_path(payload.get('entry_css') or '')
    normalized['frontend_entry'] = _clean_relative_path(payload.get('frontend_entry') or payload.get('entry_js') or payload.get('ui_entry') or '')
    normalized['backend_routes'] = _clean_relative_path(payload.get('backend_routes') or '')
    normalized['mount_point'] = str(payload.get('mount_point') or payload.get('slot') or '').strip()
    normalized['target_tab'] = str(payload.get('target_tab') or payload.get('workspace') or payload.get('target_subtab') or '').strip()
    normalized['panel_title'] = str(payload.get('panel_title') or payload.get('title') or payload.get('name') or extension_id).strip()
    normalized['frontend_hooks'] = payload.get('frontend_hooks') if isinstance(payload.get('frontend_hooks'), list) else []
    normalized['built_in'] = bool(payload.get('built_in', False))
    if normalized['built_in']:
        normalized['source'] = 'built_in'
    normalized['raw_manifest'] = payload
    return normalized


def _status_for_record(record: dict[str, Any], validation: dict[str, Any] | None = None) -> str:
    validation = validation or {'valid': bool(record.get('manifest_valid')), 'errors': []}
    if not validation.get('valid', False):
        return 'broken'
    if not bool(record.get('enabled', True)):
        return 'disabled'
    if _string_list(record.get('missing_dependencies') or []):
        return 'missing_dependency'
    if str(record.get('version_status') or '').strip() == 'version_mismatch':
        return 'version_mismatch'
    return 'enabled'


def rebuild_extension_registry() -> dict[str, Any]:
    _ensure_dirs()
    existing = _load_registry()
    enabled_overrides = {
        str(pack.get('extension_id') or pack.get('id') or '').strip(): bool(pack.get('enabled', True))
        for pack in existing.get('extension_packs', [])
        if isinstance(pack, dict) and str(pack.get('extension_id') or pack.get('id') or '').strip()
    }
    extension_packs: list[dict[str, Any]] = []
    workflow_packs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for extension_dir, source, default_enabled in _iter_manifest_dirs():
        record = _manifest_to_extension_record(extension_dir, source, default_enabled)
        extension_id = str(record.get('extension_id') or record.get('id') or extension_dir.name).strip()
        if not extension_id:
            continue
        if extension_id in enabled_overrides:
            record['enabled'] = enabled_overrides[extension_id]
            record['status'] = _status_for_record(record, {'valid': record.get('manifest_valid', False), 'errors': []})
        if extension_id in seen_ids:
            record['status'] = 'broken'
            record.setdefault('manifest_warnings', []).append('Duplicate extension id detected; later record ignored by runtime filters.')
        seen_ids.add(extension_id)
        extension_packs.append(record)
        workflow_packs.extend(_collect_workflow_packs_from_manifest(record, extension_dir))
    registry = _registry_template()
    registry['extension_packs'] = extension_packs
    registry['workflow_packs'] = workflow_packs
    registry['counts'] = _build_counts(extension_packs, workflow_packs)
    return _save_registry(registry)


def ensure_extension_registry() -> dict[str, Any]:
    _ensure_dirs()
    if not REGISTRY_PATH.exists():
        return rebuild_extension_registry()
    registry = _load_registry()
    if not isinstance(registry.get('extension_packs'), list):
        return rebuild_extension_registry()
    return registry


def _build_counts(extension_packs: list[dict[str, Any]], workflow_packs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        'extensions_total': len(extension_packs),
        'extensions_enabled': 0,
        'extensions_disabled': 0,
        'extensions_broken': 0,
        'workflow_packs_total': len(workflow_packs),
        'workflow_packs': len(workflow_packs),
        'enabled_workflow_packs': 0,
    }
    for pack in extension_packs:
        status = str(pack.get('status') or '').lower()
        if status == 'enabled' and pack.get('enabled', True):
            counts['extensions_enabled'] += 1
        elif status == 'broken':
            counts['extensions_broken'] += 1
        else:
            counts['extensions_disabled'] += 1
    enabled_extensions = {str(pack.get('extension_id') or '').strip() for pack in extension_packs if isinstance(pack, dict) and pack.get('enabled', True) and str(pack.get('status') or '').lower() == 'enabled'}
    for workflow in workflow_packs:
        required = set(_string_list(workflow.get('requires_extensions') or [])) if isinstance(workflow, dict) else set()
        if isinstance(workflow, dict) and workflow.get('enabled', True) and (not required or required.issubset(enabled_extensions)):
            counts['enabled_workflow_packs'] += 1
    return counts


def registry_counts() -> dict[str, int]:
    registry = ensure_extension_registry()
    return _build_counts(registry.get('extension_packs', []), registry.get('workflow_packs', []))


def list_extension_packs(surface: str = '', target_surface: str = '', family: str = '', workspace: str = '', enabled_only: bool = False) -> list[dict[str, Any]]:
    registry = ensure_extension_registry()
    packs = [pack for pack in registry.get('extension_packs', []) if isinstance(pack, dict)]
    surface_value = (target_surface or surface or '').strip().lower()
    family_value = family.strip().lower()
    workspace_value = workspace.strip().lower()
    out: list[dict[str, Any]] = []
    for pack in packs:
        if enabled_only and (not pack.get('enabled', True) or pack.get('status') != 'enabled'):
            continue
        if surface_value and str(pack.get('target_surface') or pack.get('surface') or '').strip().lower() != surface_value:
            continue
        if workspace_value and str(pack.get('workspace') or pack.get('target_tab') or pack.get('target_subtab') or '').strip().lower() != workspace_value:
            continue
        if family_value and not extension_allowed_for_family(str(pack.get('extension_id') or pack.get('id') or ''), family_value).get('allowed', False):
            continue
        out.append(pack)
    return out


def list_workflow_packs(surface: str = '', family: str = '', enabled_only: bool = False) -> list[dict[str, Any]]:
    registry = ensure_extension_registry()
    packs = [pack for pack in registry.get('workflow_packs', []) if isinstance(pack, dict)]
    surface_value = surface.strip().lower()
    family_value = family.strip().lower()
    out: list[dict[str, Any]] = []
    enabled_extensions = {str(pack.get('extension_id') or '').strip() for pack in list_extension_packs(enabled_only=True)}
    for pack in packs:
        if surface_value and str(pack.get('surface') or '').strip().lower() != surface_value:
            continue
        if family_value:
            pack_family = str(pack.get('family') or '').strip().lower()
            allowed_families = [item.lower() for item in _string_list(pack.get('allowed_families') or pack.get('families') or ([] if not pack_family else [pack_family]))]
            blocked_families = [item.lower() for item in _string_list(pack.get('blocked_families') or pack.get('disabled_families') or [])]
            if pack_family and pack_family != family_value:
                continue
            if allowed_families and family_value not in allowed_families:
                continue
            if family_value in blocked_families:
                continue
            pack_extension_id = str(pack.get('extension_id') or '').strip()
            if pack_extension_id and not extension_allowed_for_family(pack_extension_id, family_value).get('allowed', False):
                continue
        required_extensions = set(_string_list(pack.get('requires_extensions') or []))
        if enabled_only and required_extensions and not required_extensions.issubset(enabled_extensions):
            continue
        out.append(pack)
    return out


def _find_pack(extension_id: str) -> tuple[dict[str, Any] | None, int, dict[str, Any]]:
    registry = ensure_extension_registry()
    extension_id = extension_id.strip()
    for index, pack in enumerate(registry.get('extension_packs', [])):
        if str(pack.get('extension_id') or pack.get('id') or '').strip() == extension_id:
            return pack, index, registry
    return None, -1, registry


def upsert_extension_pack(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('Extension payload must be an object.')
    extension_id = str(payload.get('extension_id') or payload.get('id') or '').strip()
    if not extension_id:
        raise ValueError('Extension id is required.')
    registry = ensure_extension_registry()
    record = normalize_extension_pack(payload, extension_id=extension_id)
    record['id'] = extension_id
    record['status'] = _status_for_record(record, {'valid': bool(record.get('manifest_valid', True)), 'errors': []})
    packs = registry.setdefault('extension_packs', [])
    for idx, pack in enumerate(packs):
        if str(pack.get('extension_id') or pack.get('id') or '').strip() == extension_id:
            packs[idx] = {**pack, **record, 'updated_at': _now_iso()}
            _save_registry(registry)
            return packs[idx]
    record['updated_at'] = _now_iso()
    packs.append(record)
    _save_registry(registry)
    return record


def set_extension_pack_enabled(extension_id: str, enabled: bool) -> dict[str, Any] | None:
    pack, index, registry = _find_pack(extension_id)
    if pack is None or index < 0:
        return None
    pack['enabled'] = bool(enabled)
    pack['status'] = _status_for_record(pack, {'valid': bool(pack.get('manifest_valid', True)), 'errors': []})
    pack['updated_at'] = _now_iso()
    registry['extension_packs'][index] = pack
    _save_registry(registry)
    return pack


def extension_allowed_for_family(extension_id: str, family: str = '') -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    family_value = family.strip().lower()
    if not pack:
        return {'ok': True, 'allowed': False, 'reason': 'extension_not_found', 'extension_id': extension_id, 'family': family}
    if not pack.get('enabled', True) or pack.get('status') != 'enabled':
        return {'ok': True, 'allowed': False, 'reason': 'extension_disabled_or_unavailable', 'extension_id': extension_id, 'family': family}
    allowed_families = [item.lower() for item in _string_list(pack.get('allowed_families') or pack.get('families') or [])]
    blocked_families = [item.lower() for item in _string_list(pack.get('blocked_families') or pack.get('disabled_families') or [])]
    if family_value and family_value in blocked_families:
        return {'ok': True, 'allowed': False, 'reason': 'family_blocked', 'extension_id': extension_id, 'family': family}
    if allowed_families and family_value and family_value not in allowed_families:
        return {'ok': True, 'allowed': False, 'reason': 'family_not_allowed', 'extension_id': extension_id, 'family': family}
    return {'ok': True, 'allowed': True, 'reason': 'allowed', 'extension_id': extension_id, 'family': family}




def build_frontend_hook_registry(target_surface: str = '', mount_type: str = '', enabled_only: bool = True) -> dict[str, Any]:
    """Build the frontend runtime map consumed by Neo browser-side extension hooks."""
    surface_value = str(target_surface or '').strip().lower()
    mount_value = str(mount_type or '').strip().lower()
    packs = list_extension_packs(target_surface=surface_value, enabled_only=enabled_only)
    hooks: list[dict[str, Any]] = []
    for pack in packs:
        extension_id = str(pack.get('extension_id') or pack.get('id') or '').strip()
        if not extension_id:
            continue
        pack_mount = str(pack.get('mount_type') or '').strip().lower()
        if mount_value and pack_mount != mount_value:
            continue
        if pack_mount not in {'panel', 'toolbar', 'sidebar'}:
            continue
        entry_js = _clean_relative_path(pack.get('frontend_entry') or pack.get('entry_js') or '')
        entry_css = _clean_relative_path(pack.get('entry_css') or '')
        hook = {
            'extension_id': extension_id,
            'id': extension_id,
            'name': str(pack.get('name') or pack.get('title') or extension_id),
            'version': str(pack.get('version') or ''),
            'target_surface': str(pack.get('target_surface') or pack.get('surface') or '').strip().lower(),
            'target_tab': str(pack.get('target_tab') or pack.get('workspace') or '').strip(),
            'mount_type': pack_mount,
            'mount_point': str(pack.get('mount_point') or '').strip(),
            'panel_title': str(pack.get('panel_title') or pack.get('name') or pack.get('title') or extension_id),
            'entry_js': entry_js,
            'entry_css': entry_css,
            'entry_js_url': _asset_url(extension_id, entry_js),
            'entry_css_url': _asset_url(extension_id, entry_css),
            'permissions': _string_list(pack.get('permissions') or []),
            'source': str(pack.get('source') or ''),
        }
        hooks.append(hook)
    grouped = {'panel': [], 'toolbar': [], 'sidebar': []}
    for hook in hooks:
        grouped.setdefault(hook['mount_type'], []).append(hook)
    return {
        'ok': True,
        'schema_version': REGISTRY_SCHEMA_VERSION,
        'target_surface': surface_value,
        'mount_type': mount_value,
        'hooks': hooks,
        'grouped': grouped,
        'counts': {key: len(value) for key, value in grouped.items()},
    }


# -----------------------------
# Phase 6: Extension Manager maintenance actions
# -----------------------------

def _safe_folder_name(value: Any, fallback: str = 'extension') -> str:
    text = str(value or fallback).strip().replace(' ', '_')
    safe = ''.join(ch for ch in text if ch.isalnum() or ch in ('-', '_', '.')).strip('._')
    return safe or fallback

def _write_extension_log(extension_id: str, lines: list[str] | str) -> str:
    _ensure_dirs()
    safe_id = _safe_folder_name(extension_id or 'extension')
    path = LOG_DIR / f'{safe_id}.log'
    text = '\n'.join(lines) if isinstance(lines, list) else str(lines or '')
    with path.open('a', encoding='utf-8') as handle:
        handle.write(f'[{_now_iso()}] {text}\n')
    return str(path)

def _run_command(command: list[str], cwd: Path | None = None, timeout: int = 180) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, shell=False)
        output = (proc.stdout or '') + (("\n" + proc.stderr) if proc.stderr else '')
        return int(proc.returncode), output.strip()
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or '') if isinstance(exc.stdout, str) else '') + '\n' + ((exc.stderr or '') if isinstance(exc.stderr, str) else '')
        return 124, f'Command timed out.\n{output}'.strip()
    except Exception as exc:
        return 1, str(exc)

def _copytree_clean(src: Path, dst: Path, overwrite: bool = False) -> None:
    if dst.exists():
        if not overwrite:
            raise FileExistsError(f'Extension folder already exists: {dst.name}')
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

def _candidate_extension_root(root: Path) -> Path:
    if _find_manifest(root):
        return root
    children = [child for child in root.iterdir() if child.is_dir()]
    manifest_children = [child for child in children if _find_manifest(child)]
    if len(manifest_children) == 1:
        return manifest_children[0]
    for child in children:
        try:
            nested = _candidate_extension_root(child)
            if _find_manifest(nested):
                return nested
        except Exception:
            pass
    return root

def _load_manifest_from_root(root: Path) -> tuple[dict[str, Any], Path | None]:
    manifest = _find_manifest(root)
    payload = _read_json(manifest, {}) if manifest else {}
    return (payload if isinstance(payload, dict) else {}, manifest)

def _extension_id_from_root(root: Path) -> str:
    payload, _ = _load_manifest_from_root(root)
    return _safe_folder_name(payload.get('id') or payload.get('extension_id') or root.name)

def install_extension_from_folder(source_dir: str | Path, *, overwrite: bool = False, enable: bool = True, source_label: str = 'folder') -> dict[str, Any]:
    _ensure_dirs()
    source_path = Path(source_dir).resolve()
    if not source_path.exists() or not source_path.is_dir():
        raise FileNotFoundError('Extension source folder was not found.')
    extension_root = _candidate_extension_root(source_path)
    payload, manifest = _load_manifest_from_root(extension_root)
    validation = validate_manifest_payload(payload)
    if not validation.get('valid'):
        raise ValueError('Extension manifest is invalid: ' + '; '.join(validation.get('errors') or ['unknown manifest error']))
    extension_id = _extension_id_from_root(extension_root)
    target = INSTALLED_DIR / extension_id
    _copytree_clean(extension_root, target, overwrite=overwrite)
    log_path = _write_extension_log(extension_id, [f'Installed extension {extension_id} from {source_label}.', f'Source: {source_path}', f'Target: {target}', f'Manifest: {manifest.name if manifest else "—"}'])
    rebuild_extension_registry()
    pack, index, registry = _find_pack(extension_id)
    if pack:
        pack['enabled'] = bool(enable)
        pack['status'] = _status_for_record(pack, {'valid': bool(pack.get('manifest_valid', True)), 'errors': []})
        pack['install_log_path'] = log_path
        registry['extension_packs'][index] = pack
        _save_registry(registry)
        return {'ok': True, 'extension_id': extension_id, 'record': pack, 'log_path': log_path}
    return {'ok': True, 'extension_id': extension_id, 'record': None, 'log_path': log_path}

def install_extension_from_zip(zip_path: str | Path, *, overwrite: bool = False, enable: bool = True) -> dict[str, Any]:
    _ensure_dirs()
    zip_file = Path(zip_path).resolve()
    if not zip_file.exists() or not zipfile.is_zipfile(zip_file):
        raise ValueError('Extension ZIP was not found or is not a valid ZIP file.')
    with tempfile.TemporaryDirectory(prefix='neo_ext_zip_', dir=str(CACHE_DIR)) as tmp:
        tmp_root = Path(tmp)
        with zipfile.ZipFile(zip_file) as archive:
            archive.extractall(tmp_root)
        return install_extension_from_folder(tmp_root, overwrite=overwrite, enable=enable, source_label=f'zip:{zip_file.name}')

def install_extension_from_git(git_url: str, *, branch: str = '', overwrite: bool = False, enable: bool = True) -> dict[str, Any]:
    _ensure_dirs()
    url = str(git_url or '').strip()
    if not url:
        raise ValueError('Git URL is required.')
    parsed = urlparse(url)
    fallback_name = Path(parsed.path).stem or 'git_extension'
    clone_dir = CACHE_DIR / f'git_{_safe_folder_name(fallback_name)}_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    command = ['git', 'clone', '--depth', '1']
    if branch.strip():
        command += ['--branch', branch.strip()]
    command += [url, str(clone_dir)]
    code, output = _run_command(command, timeout=300)
    if code != 0:
        raise RuntimeError('Git clone failed. ' + output)
    result = install_extension_from_folder(clone_dir, overwrite=overwrite, enable=enable, source_label=f'git:{url}')
    _write_extension_log(result.get('extension_id', fallback_name), ['Git clone output:', output or '(no output)'])
    return result

def update_extension(extension_id: str) -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    if not pack:
        raise FileNotFoundError('Extension was not found.')
    root = Path(str(pack.get('extension_dir') or '')).resolve()
    if not root.exists():
        raise FileNotFoundError('Extension folder was not found.')
    log_lines = [f'Update requested for {extension_id}.']
    git_dir = root / '.git'
    if git_dir.exists():
        code, output = _run_command(['git', 'pull', '--ff-only'], cwd=root, timeout=300)
        log_lines.append(output or '(git pull produced no output)')
        if code != 0:
            log_path = _write_extension_log(extension_id, log_lines)
            raise RuntimeError(f'Git update failed. See log: {log_path}')
    else:
        log_lines.append('No .git folder found; update performed as registry rescan only.')
    log_path = _write_extension_log(extension_id, log_lines)
    registry = rebuild_extension_registry()
    pack, _, _ = _find_pack(extension_id)
    return {'ok': True, 'extension_id': extension_id, 'record': pack, 'log_path': log_path, 'registry': registry}

def remove_extension(extension_id: str, *, delete_files: bool = True) -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    if not pack:
        raise FileNotFoundError('Extension was not found.')
    if bool(pack.get('built_in', False)):
        raise PermissionError('Built-in extensions cannot be removed from Extension Manager; disable them instead.')
    root = Path(str(pack.get('extension_dir') or '')).resolve()
    protected_roots = {LEGACY_EXTENSIONS_DIR.resolve(), APP_DIR.resolve()}
    removed = False
    if delete_files and root.exists() and not any(root == pr or pr in root.parents for pr in protected_roots):
        shutil.rmtree(root)
        removed = True
    elif root.exists() and root.is_dir() and not any(root == pr or pr in root.parents for pr in protected_roots):
        disabled_target = DISABLED_DIR / root.name
        if disabled_target.exists():
            shutil.rmtree(disabled_target)
        shutil.move(str(root), str(disabled_target))
        removed = True
    log_path = _write_extension_log(extension_id, f'Removed extension. Files changed: {removed}.')
    registry = rebuild_extension_registry()
    return {'ok': True, 'extension_id': extension_id, 'removed': removed, 'log_path': log_path, 'registry': registry}

def repair_extension_registry(extension_id: str = '') -> dict[str, Any]:
    registry = rebuild_extension_registry()
    if extension_id:
        pack, _, _ = _find_pack(extension_id)
        _write_extension_log(extension_id, 'Repair/rescan requested for this extension.')
        return {'ok': True, 'extension_id': extension_id, 'record': pack, 'registry': registry}
    return {'ok': True, 'registry': registry}

def open_extension_folder(extension_id: str) -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    if not pack:
        raise FileNotFoundError('Extension was not found.')
    root = Path(str(pack.get('extension_dir') or '')).resolve()
    if not root.exists():
        raise FileNotFoundError('Extension folder was not found.')
    if os.name == 'nt':
        subprocess.Popen(['explorer', str(root)])
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(root)])
    else:
        subprocess.Popen(['xdg-open', str(root)])
    return {'ok': True, 'extension_id': extension_id, 'path': str(root)}

def get_extension_manifest(extension_id: str) -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    if not pack:
        raise FileNotFoundError('Extension was not found.')
    raw = pack.get('raw_manifest') if isinstance(pack.get('raw_manifest'), dict) else {}
    return {'ok': True, 'extension_id': extension_id, 'manifest': raw, 'record': pack}

def get_extension_log(extension_id: str) -> dict[str, Any]:
    pack, _, _ = _find_pack(extension_id)
    if not pack:
        raise FileNotFoundError('Extension was not found.')
    safe_id = _safe_folder_name(extension_id)
    log_path = LOG_DIR / f'{safe_id}.log'
    text = ''
    if log_path.exists():
        text = log_path.read_text(encoding='utf-8', errors='replace')[-20000:]
    return {'ok': True, 'extension_id': extension_id, 'log_path': str(log_path), 'log': text or 'No extension log yet.'}



# -----------------------------
# Phase 11: Extension health + repair helpers
# -----------------------------

def _extension_health_reason(pack: dict[str, Any]) -> str:
    """Return a compact human-readable health reason for an extension record."""
    if not isinstance(pack, dict):
        return 'invalid_record'
    status = str(pack.get('status') or '').strip().lower() or 'unknown'
    if status == 'enabled':
        return 'healthy'
    if status == 'disabled':
        return 'disabled_by_user_or_disabled_folder'
    warnings = _string_list(pack.get('manifest_warnings') or [])
    if status == 'broken':
        if warnings:
            return '; '.join(warnings[:5])
        if not pack.get('manifest_valid', True):
            return 'manifest_invalid'
        return 'extension_marked_broken'
    if status == 'missing_dependency':
        deps = _string_list(pack.get('missing_dependencies') or pack.get('dependencies') or [])
        return 'missing dependencies: ' + (', '.join(deps) if deps else 'unknown')
    if status == 'version_mismatch':
        return 'version mismatch: requires ' + str(pack.get('min_neo_version') or 'unknown Neo version')
    return status


def build_extension_health_report() -> dict[str, Any]:
    """Rescan and return extension health without mutating extension files."""
    registry = rebuild_extension_registry()
    packs = [pack for pack in registry.get('extension_packs', []) if isinstance(pack, dict)]
    health_items: list[dict[str, Any]] = []
    counts = {'healthy': 0, 'disabled': 0, 'broken': 0, 'warning': 0, 'total': len(packs)}
    for pack in packs:
        status = str(pack.get('status') or '').strip().lower() or 'unknown'
        warnings = _string_list(pack.get('manifest_warnings') or [])
        severity = 'ok'
        if status == 'enabled' and not warnings:
            counts['healthy'] += 1
        elif status == 'disabled':
            severity = 'disabled'
            counts['disabled'] += 1
        elif status in {'broken', 'missing_dependency', 'version_mismatch'}:
            severity = 'broken' if status == 'broken' else 'warning'
            if status == 'broken':
                counts['broken'] += 1
            else:
                counts['warning'] += 1
        else:
            severity = 'warning'
            counts['warning'] += 1
        health_items.append({
            'extension_id': str(pack.get('extension_id') or pack.get('id') or ''),
            'name': str(pack.get('name') or pack.get('title') or pack.get('extension_id') or ''),
            'status': status,
            'enabled': bool(pack.get('enabled', True)),
            'severity': severity,
            'reason': _extension_health_reason(pack),
            'manifest_path': str(pack.get('manifest_path') or ''),
            'extension_dir': str(pack.get('extension_dir') or ''),
            'warnings': warnings,
        })
    return {'ok': True, 'counts': counts, 'health': health_items, 'registry': registry}


def disable_broken_extensions() -> dict[str, Any]:
    """Disable only broken/problem records in the registry; do not delete files."""
    registry = ensure_extension_registry()
    changed: list[str] = []
    for pack in registry.get('extension_packs', []):
        if not isinstance(pack, dict):
            continue
        status = str(pack.get('status') or '').strip().lower()
        if status in {'broken', 'missing_dependency', 'version_mismatch'} and pack.get('enabled', True):
            previous_status = status
            ext_id = str(pack.get('extension_id') or pack.get('id') or '')
            reason = _extension_health_reason(pack)
            pack['enabled'] = False
            pack['status'] = 'disabled'
            pack['updated_at'] = _now_iso()
            changed.append(ext_id)
            if ext_id:
                _write_extension_log(ext_id, f'Disabled by Phase 11 health repair. Previous status: {previous_status}. Reason: {reason}')
    _save_registry(registry)
    return {'ok': True, 'disabled': changed, 'registry': registry}


def clear_extension_cache() -> dict[str, Any]:
    """Clear Neo extension cache folder only. Installed/disabled extensions are untouched."""
    _ensure_dirs()
    removed = 0
    if CACHE_DIR.exists():
        for child in CACHE_DIR.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed += 1
            except Exception:
                pass
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return {'ok': True, 'removed_items': removed, 'cache_dir': str(CACHE_DIR)}
def get_extension_manifest_standard() -> dict[str, Any]:
    return {
        'schema_version': REGISTRY_SCHEMA_VERSION,
        'manifest_filename': 'neo_extension.json',
        'legacy_manifest_filename': 'manifest.json',
        'required_fields': list(REQUIRED_MANIFEST_FIELDS),
        'recommended_fields': [
            'author', 'description', 'target_tab', 'mount_point', 'panel_title', 'entry_js', 'entry_css', 'backend_routes',
            'permissions', 'dependencies', 'min_neo_version', 'workflow_packs', 'workflows', 'workflow_folder', 'backend_routes',
        ],
        'known_mount_types': sorted(KNOWN_MOUNT_TYPES),
        'known_surfaces': sorted(KNOWN_SURFACES),
        'known_permissions': sorted(KNOWN_PERMISSION_NAMES),
        'example': {
            'id': 'neo_example_panel',
            'name': 'Neo Example Panel',
            'version': '1.0.0',
            'author': 'Neo Studio',
            'target_surface': 'image',
            'mount_type': 'panel',
            'mount_point': 'image.right_panel',
            'panel_title': 'Example Panel',
            'entry_js': 'static/example_panel.js',
            'entry_css': 'static/example_panel.css',
            'backend_routes': 'server/routes.py',
            'permissions': ['frontend_injection', 'backend_routes'],
            'runtime_prefix': '/api/extensions/runtime/neo_example_panel',
            'workflows': {
                'folder': 'workflows',
                'backend_role': 'image',
                'target_surface': 'image'
            },
            'workflow_packs': [
                {
                    'workflow_id': 'neo_example_panel.basic_image',
                    'title': 'Basic Image Workflow',
                    'surface': 'image',
                    'backend_role': 'image',
                    'workflow_path': 'workflows/basic_image.json'
                }
            ],
            'min_neo_version': '1.0.0',
        },
    }

# -----------------------------
# Phase 13: Extension workflow import helpers
# -----------------------------

def get_workflow_pack(workflow_id: str) -> dict[str, Any]:
    workflow_id = str(workflow_id or '').strip()
    registry = ensure_extension_registry()
    for pack in registry.get('workflow_packs', []):
        if isinstance(pack, dict) and str(pack.get('workflow_id') or '').strip() == workflow_id:
            return {'ok': True, 'pack': pack}
    return {'ok': False, 'error': 'Workflow pack was not found.', 'pack': None}


def get_workflow_pack_content(workflow_id: str) -> dict[str, Any]:
    found = get_workflow_pack(workflow_id)
    if not found.get('ok'):
        return found
    pack = found.get('pack') or {}
    extension_ids = _string_list(pack.get('requires_extensions') or [])
    if not extension_ids:
        return {'ok': False, 'error': 'Workflow pack has no owning extension.', 'pack': pack}
    owner_id = extension_ids[0]
    owner, _, _ = _find_pack(owner_id)
    if not owner:
        return {'ok': False, 'error': 'Owning extension was not found.', 'pack': pack}
    extension_dir = Path(str(owner.get('extension_dir') or '')).resolve()
    workflow_path = _clean_relative_path(pack.get('workflow_path') or '')
    if not workflow_path:
        return {'ok': False, 'error': 'Workflow pack does not reference a workflow file.', 'pack': pack}
    file_path = (extension_dir / workflow_path).resolve()
    if extension_dir not in file_path.parents and file_path != extension_dir:
        return {'ok': False, 'error': 'Workflow path is outside the extension folder.', 'pack': pack}
    if not file_path.exists() or not file_path.is_file():
        return {'ok': False, 'error': 'Workflow file was not found.', 'pack': pack}
    return {
        'ok': True,
        'pack': pack,
        'content': _read_json(file_path, {}),
        'workflow_path': workflow_path,
        'extension_id': owner_id,
    }
