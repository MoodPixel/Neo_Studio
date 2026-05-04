from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..utils.backend_manager import (
    AVAILABLE_BACKEND_TYPES,
    connect_profile,
    delete_profile,
    disconnect_profile,
    get_manager_state,
    maybe_auto_reconnect,
    get_profile,
    get_launch_log,
    launch_profile_backend,
    normalize_url,
    open_profile_native_ui,
    probe_profile,
    refresh_profile,
    set_active_profile,
    set_low_vram_mode,
    upsert_profile,
)
from .common import json_error

router = APIRouter()


@router.get('/api/backend-manager/state')
async def api_backend_manager_state():
    await maybe_auto_reconnect()
    return JSONResponse({'ok': True, **get_manager_state()})


@router.post('/api/backend-manager/profile-save')
async def api_backend_profile_save(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    backend_type = str((payload or {}).get('backend_type') or '').strip().lower()
    if backend_type not in AVAILABLE_BACKEND_TYPES.get(role, []):
        return json_error(f'Unsupported backend type for {role}: {backend_type or "(none)"}', 400)
    profile = upsert_profile(role, payload or {})
    return JSONResponse({'ok': True, 'message': f'{role.title()} backend profile saved.', 'profile': profile, **get_manager_state()})


@router.post('/api/backend-manager/profile-delete')
async def api_backend_profile_delete(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    if not profile_id:
        return json_error('No profile selected to delete.', 400)
    state = delete_profile(role, profile_id)
    return JSONResponse({'ok': True, 'message': f'{role.title()} backend profile deleted.', **get_manager_state(), 'settings_snapshot': state})


@router.post('/api/backend-manager/profile-select')
async def api_backend_profile_select(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    if not profile_id:
        return json_error('No profile selected.', 400)
    profile = get_profile(role, profile_id)
    if not profile:
        return json_error('Selected profile was not found.', 404)
    set_active_profile(role, profile_id)
    return JSONResponse({'ok': True, 'message': f'{role.title()} backend profile selected.', 'profile': profile, **get_manager_state()})


@router.post('/api/backend-manager/settings-save')
async def api_backend_settings_save(payload: dict):
    enabled = bool((payload or {}).get('low_vram_mode', True))
    set_low_vram_mode(enabled)
    return JSONResponse({'ok': True, 'message': 'Backend manager settings saved.', **get_manager_state()})


@router.post('/api/backend-manager/test')
async def api_backend_test(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    profile = get_profile(role, profile_id)
    if not profile:
        temp_backend_type = str((payload or {}).get('backend_type') or '').strip().lower() or AVAILABLE_BACKEND_TYPES[role][0]
        profile = {
            'id': '',
            'name': '(unsaved)',
            'backend_type': temp_backend_type,
            'base_url': normalize_url((payload or {}).get('base_url') or ''),
            'timeout_sec': int((payload or {}).get('timeout_sec') or 8),
            'auto_reconnect': False,
        }
    result = await probe_profile(role, profile)
    return JSONResponse({'ok': True, 'result': result, 'profile': profile})


@router.post('/api/backend-manager/connect')
async def api_backend_connect(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    result = await connect_profile(role, profile_id or None)
    success = bool(result.get('session', {}).get('connected'))
    return JSONResponse({'ok': True, 'success': success, 'message': result.get('message') or ('Connected.' if success else 'Connection failed.'), 'result': result, **get_manager_state()})


@router.post('/api/backend-manager/refresh')
async def api_backend_refresh(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    result = await refresh_profile(role)
    success = bool(result.get('session', {}).get('connected')) or result.get('state') in {'degraded', 'connected'}
    return JSONResponse({'ok': True, 'success': success, 'message': result.get('message') or ('Backend refreshed.' if success else 'Refresh failed.'), 'result': result, **get_manager_state()})


@router.post('/api/backend-manager/disconnect')
async def api_backend_disconnect(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    session = disconnect_profile(role)
    return JSONResponse({'ok': True, 'message': f'{role.title()} backend disconnected.', 'session': session, **get_manager_state()})


@router.post('/api/backend-manager/launch')
async def api_backend_launch(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    try:
        result = launch_profile_backend(role, profile_id or None)
    except Exception as exc:
        return json_error(str(exc) or 'Could not launch backend.', 400)
    return JSONResponse({'ok': True, 'message': result.get('message') or 'Backend launch requested.', 'result': result, **get_manager_state()})


@router.post('/api/backend-manager/open-native-ui')
async def api_backend_open_native_ui(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    try:
        result = open_profile_native_ui(role, profile_id or None)
    except Exception as exc:
        return json_error(str(exc) or 'Could not open native UI.', 400)
    return JSONResponse({'ok': True, **result})


@router.post('/api/backend-manager/launch-log')
async def api_backend_launch_log(payload: dict):
    role = str((payload or {}).get('role') or '').strip().lower()
    profile_id = str((payload or {}).get('profile_id') or '').strip()
    if role not in AVAILABLE_BACKEND_TYPES:
        return json_error('Invalid backend role.', 400)
    return JSONResponse(get_launch_log(role, profile_id or None))
