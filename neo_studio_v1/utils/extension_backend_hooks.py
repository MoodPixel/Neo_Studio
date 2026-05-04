from __future__ import annotations

import importlib.util
import json
import traceback
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import APIRouter, FastAPI

from .extension_registry import (
    REGISTRY_SCHEMA_VERSION,
    _clean_relative_path,
    _find_pack,
    _string_list,
    list_extension_packs,
)

APP_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = APP_DIR.parent
DATA_DIR = ROOT_DIR / 'neo_library_data' / 'studio_user_data'
BACKEND_HOOK_LOG_PATH = DATA_DIR / 'extension_backend_hooks.json'

_loaded_backend_hooks: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _write_backend_log() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': REGISTRY_SCHEMA_VERSION,
        'record_type': 'neo_extension_backend_hooks',
        'updated_at': _now_iso(),
        'hooks': list(_loaded_backend_hooks.values()),
    }
    tmp = BACKEND_HOOK_LOG_PATH.with_suffix(BACKEND_HOOK_LOG_PATH.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    tmp.replace(BACKEND_HOOK_LOG_PATH)


def _safe_extension_file(extension_dir: str, relative_path: str) -> Path | None:
    root = Path(extension_dir or '').resolve()
    cleaned = _clean_relative_path(relative_path)
    if not cleaned or not root.exists() or not root.is_dir():
        return None
    candidate = (root / cleaned).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _load_module(extension_id: str, route_file: Path) -> ModuleType:
    module_name = f'neo_external_extension_{extension_id.replace("-", "_").replace(".", "_")}_routes'
    spec = importlib.util.spec_from_file_location(module_name, str(route_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Could not create import spec for {route_file}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_router(module: ModuleType) -> APIRouter:
    router = getattr(module, 'router', None)
    if isinstance(router, APIRouter):
        return router
    factory = getattr(module, 'get_router', None)
    if callable(factory):
        created = factory()
        if isinstance(created, APIRouter):
            return created
    raise RuntimeError('Backend route module must expose `router = APIRouter()` or `get_router()` returning APIRouter.')


def _pack_can_load_backend(pack: dict[str, Any]) -> tuple[bool, str]:
    if not pack.get('enabled', True) or str(pack.get('status') or '') != 'enabled':
        return False, 'extension_disabled_or_unavailable'
    backend_routes = _clean_relative_path(pack.get('backend_routes') or '')
    if not backend_routes:
        return False, 'no_backend_routes_declared'
    permissions = set(_string_list(pack.get('permissions') or []))
    if 'backend_routes' not in permissions:
        return False, 'missing_backend_routes_permission'
    return True, 'ready'


def build_backend_hook_registry(enabled_only: bool = True) -> dict[str, Any]:
    packs = list_extension_packs(enabled_only=enabled_only)
    hooks: list[dict[str, Any]] = []
    for pack in packs:
        extension_id = str(pack.get('extension_id') or pack.get('id') or '').strip()
        if not extension_id:
            continue
        allowed, reason = _pack_can_load_backend(pack)
        backend_routes = _clean_relative_path(pack.get('backend_routes') or '')
        if not backend_routes and enabled_only:
            continue
        hook = {
            'extension_id': extension_id,
            'id': extension_id,
            'name': str(pack.get('name') or pack.get('title') or extension_id),
            'version': str(pack.get('version') or ''),
            'target_surface': str(pack.get('target_surface') or pack.get('surface') or '').strip().lower(),
            'backend_routes': backend_routes,
            'runtime_prefix': f'/api/extensions/runtime/{extension_id}',
            'permissions': _string_list(pack.get('permissions') or []),
            'status': str(pack.get('status') or ''),
            'enabled': bool(pack.get('enabled', True)),
            'loadable': allowed,
            'reason': reason,
            'loaded': extension_id in _loaded_backend_hooks and _loaded_backend_hooks[extension_id].get('loaded'),
            'load_error': (_loaded_backend_hooks.get(extension_id) or {}).get('error', ''),
        }
        hooks.append(hook)
    return {
        'ok': True,
        'schema_version': REGISTRY_SCHEMA_VERSION,
        'hooks': hooks,
        'loaded': list(_loaded_backend_hooks.values()),
        'counts': {
            'declared': len(hooks),
            'loadable': sum(1 for hook in hooks if hook.get('loadable')),
            'loaded': sum(1 for hook in hooks if hook.get('loaded')),
            'errors': sum(1 for hook in hooks if hook.get('load_error')),
        },
    }


def mount_enabled_extension_backend_routes(app: FastAPI) -> dict[str, Any]:
    """Mount enabled extension APIRouters under /api/extensions/runtime/{extension_id}.

    Extensions are isolated behind their own prefix. A broken extension records an
    error and does not stop Neo Studio from booting.
    """
    packs = list_extension_packs(enabled_only=True)
    for pack in packs:
        extension_id = str(pack.get('extension_id') or pack.get('id') or '').strip()
        if not extension_id or extension_id in _loaded_backend_hooks:
            continue
        allowed, reason = _pack_can_load_backend(pack)
        base_record = {
            'extension_id': extension_id,
            'name': str(pack.get('name') or pack.get('title') or extension_id),
            'backend_routes': _clean_relative_path(pack.get('backend_routes') or ''),
            'runtime_prefix': f'/api/extensions/runtime/{extension_id}',
            'loaded_at': _now_iso(),
            'loaded': False,
            'reason': reason,
            'error': '',
        }
        if not allowed:
            if reason != 'no_backend_routes_declared':
                _loaded_backend_hooks[extension_id] = base_record
            continue
        try:
            route_file = _safe_extension_file(str(pack.get('extension_dir') or ''), str(pack.get('backend_routes') or ''))
            if route_file is None:
                raise RuntimeError('backend_routes file is missing or outside extension folder.')
            module = _load_module(extension_id, route_file)
            router = _extract_router(module)
            app.include_router(router, prefix=base_record['runtime_prefix'])
            base_record.update({
                'loaded': True,
                'route_file': str(route_file),
                'reason': 'loaded',
            })
        except Exception as exc:
            base_record.update({
                'loaded': False,
                'reason': 'load_error',
                'error': str(exc),
                'traceback': traceback.format_exc(limit=8),
            })
        _loaded_backend_hooks[extension_id] = base_record
    _write_backend_log()
    return build_backend_hook_registry(enabled_only=False)


def get_backend_hook_status(extension_id: str = '') -> dict[str, Any]:
    if extension_id:
        pack, _, _ = _find_pack(extension_id)
        record = _loaded_backend_hooks.get(extension_id)
        return {'ok': True, 'extension_id': extension_id, 'pack': pack or {}, 'backend_hook': record or {}}
    return build_backend_hook_registry(enabled_only=False)
