from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any

from ...utils.extension_registry import ROOT_DIR, build_external_extension_registry

CAPABILITY_PROBE_VERSION = 'external-extension-capability-probe-v1'


def _string_list(value: Any) -> list[str]:
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


def _safe_relative_path(value: Any) -> str:
    text = str(value or '').strip().replace('\\', '/')
    if not text or text.startswith('/'):
        return ''
    path = PurePosixPath(text)
    if '..' in path.parts:
        return ''
    return path.as_posix()


def _existing_dir(path: Any) -> Path | None:
    try:
        candidate = Path(str(path or '')).expanduser().resolve()
    except Exception:
        return None
    return candidate if candidate.exists() and candidate.is_dir() else None


def _candidate_comfy_custom_node_dirs(extra_paths: list[str] | None = None) -> list[Path]:
    candidates: list[Path] = []
    env_names = ('NEO_COMFYUI_DIR', 'COMFYUI_PATH', 'COMFYUI_DIR')
    for env_name in env_names:
        raw = os.environ.get(env_name)
        if not raw:
            continue
        base = Path(raw).expanduser()
        candidates.extend([base / 'custom_nodes', base])
    for raw in extra_paths or []:
        base = Path(raw).expanduser()
        candidates.extend([base / 'custom_nodes', base])
    candidates.extend([
        ROOT_DIR / 'ComfyUI' / 'custom_nodes',
        ROOT_DIR.parent / 'ComfyUI' / 'custom_nodes',
        ROOT_DIR / 'comfyui' / 'custom_nodes',
        ROOT_DIR.parent / 'comfyui' / 'custom_nodes',
    ])
    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _existing_dir(candidate)
        if not resolved:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _node_exists(node_name: str, search_dirs: list[Path]) -> tuple[bool, str]:
    target = str(node_name or '').strip()
    if not target:
        return False, ''
    target_lower = target.lower()
    target_dashless = target_lower.replace('_', '-').replace(' ', '-')
    for directory in search_dirs:
        for child in directory.iterdir() if directory.exists() else []:
            name = child.name.lower()
            stem = child.stem.lower()
            normalized = name.replace('_', '-').replace(' ', '-')
            if target_lower in {name, stem} or target_dashless == normalized or target_lower in name:
                return True, str(child)
    return False, ''


def _extension_dir(record: dict[str, Any]) -> Path | None:
    return _existing_dir(record.get('extension_dir'))


def _template_requirements(record: dict[str, Any]) -> list[str]:
    templates: list[str] = []
    for patch in record.get('workflow_patches') or []:
        if not isinstance(patch, dict):
            continue
        template = _safe_relative_path(patch.get('template') or patch.get('workflow_template'))
        if template:
            templates.append(template)
    return _string_list(templates)


def _template_exists(extension_dir: Path | None, template: str) -> tuple[bool, str]:
    safe = _safe_relative_path(template)
    if not safe or not extension_dir:
        return False, ''
    candidate = (extension_dir / safe).resolve()
    try:
        candidate.relative_to(extension_dir.resolve())
    except Exception:
        return False, ''
    if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == '.json':
        return True, str(candidate)
    return False, str(candidate)


def _capability_requirements(record: dict[str, Any]) -> dict[str, Any]:
    dependencies = record.get('dependencies') if isinstance(record.get('dependencies'), dict) else {}
    requirements = record.get('capability_requirements') if isinstance(record.get('capability_requirements'), dict) else {}
    return {
        'comfy_nodes': _string_list(
            requirements.get('comfy_nodes')
            or record.get('required_comfy_nodes')
            or dependencies.get('comfy_nodes')
            or []
        ),
        'workflow_templates': _string_list(
            requirements.get('workflow_templates')
            or record.get('required_workflow_templates')
            or _template_requirements(record)
        ),
        'models': _string_list(requirements.get('models') or dependencies.get('models') or []),
        'providers': _string_list(requirements.get('providers') or dependencies.get('providers') or []),
        'external_apps': _string_list(requirements.get('external_apps') or dependencies.get('external_apps') or []),
        'python': _string_list(requirements.get('python') or dependencies.get('python') or []),
    }


def probe_external_extension_capability(
    record: dict[str, Any],
    *,
    comfy_custom_node_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    extension_id = str(record.get('extension_id') or record.get('id') or '').strip()
    status = str(record.get('status') or '').strip().lower()
    requirements = _capability_requirements(record)
    ext_dir = _extension_dir(record)
    node_dirs = comfy_custom_node_dirs if comfy_custom_node_dirs is not None else _candidate_comfy_custom_node_dirs()
    missing: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {
        'manifest': {
            'ok': bool(record.get('manifest_valid', status != 'broken')),
            'status': status or 'unknown',
        },
        'comfy_custom_nodes': [],
        'workflow_templates': [],
        'models': [],
        'providers': [],
        'external_apps': [],
        'python': [],
    }

    if not checks['manifest']['ok']:
        missing.append('manifest')

    if requirements['comfy_nodes'] and not node_dirs:
        warnings.append('No ComfyUI custom_nodes directory was found. Set NEO_COMFYUI_DIR or COMFYUI_PATH for stronger capability checks.')
    for node in requirements['comfy_nodes']:
        exists, found_path = _node_exists(node, node_dirs)
        checks['comfy_custom_nodes'].append({'name': node, 'available': exists, 'path': found_path})
        if not exists:
            missing.append(f'comfy_node:{node}')

    for template in requirements['workflow_templates']:
        exists, found_path = _template_exists(ext_dir, template)
        checks['workflow_templates'].append({'template': template, 'available': exists, 'path': found_path})
        if not exists:
            missing.append(f'workflow_template:{template}')

    # These requirements are intentionally reported as declared/unchecked in Phase H.
    # Actual model/provider/app probing should be wired into their owning registries later.
    for key in ('models', 'providers', 'external_apps', 'python'):
        for item in requirements[key]:
            checks[key].append({'name': item, 'available': None, 'status': 'declared_unchecked'})
            warnings.append(f'{key[:-1] if key.endswith("s") else key}:{item} declared but not checked by this probe yet.')

    disabled_reason = str(record.get('disabled_reason') or '').strip()
    if disabled_reason and disabled_reason != 'enabled':
        warnings.append(f'Extension registry status: {disabled_reason}')

    available = not missing and status not in {'broken', 'missing_dependency', 'version_mismatch'}
    return {
        'extension_id': extension_id,
        'name': str(record.get('name') or extension_id).strip(),
        'surface': str(record.get('surface') or record.get('target_surface') or '').strip().lower(),
        'available': bool(available),
        'status': 'ready' if available else 'missing_requirements',
        'registry_status': status or 'unknown',
        'missing': missing,
        'warnings': warnings,
        'requirements': requirements,
        'checks': checks,
        'extension_dir': str(ext_dir or record.get('extension_dir') or ''),
    }


def probe_external_extension_capabilities(surface: str = '', include_invalid: bool = True) -> dict[str, Any]:
    registry = build_external_extension_registry(surface=surface, include_invalid=include_invalid)
    records = registry.get('installed') if isinstance(registry, dict) else []
    node_dirs = _candidate_comfy_custom_node_dirs()
    capabilities: dict[str, Any] = {}
    ready = 0
    missing_count = 0
    warnings: list[str] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        capability = probe_external_extension_capability(record, comfy_custom_node_dirs=node_dirs)
        extension_id = capability.get('extension_id')
        if not extension_id:
            continue
        capabilities[str(extension_id)] = capability
        if capability.get('available'):
            ready += 1
        else:
            missing_count += 1
        warnings.extend([f'{extension_id}: {warning}' for warning in capability.get('warnings') or []])
    return {
        'ok': True,
        'schema_version': 1,
        'probe_version': CAPABILITY_PROBE_VERSION,
        'surface': str(surface or '').strip().lower(),
        'available': ready,
        'missing_requirements': missing_count,
        'capabilities': capabilities,
        'warnings': warnings,
        'search_paths': {
            'comfy_custom_nodes': [str(path) for path in node_dirs],
        },
        'built_in_modules_excluded': True,
    }
