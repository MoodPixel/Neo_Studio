from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .common import json_error
from ..utils.backend_manager import connect_profile, get_manager_state, refresh_profile
from ..utils.node_manager import (
    get_last_node_manager_log,
    install_custom_node,
    list_custom_nodes,
    load_node_manager_settings,
    open_custom_node_path,
    save_node_manager_settings,
    update_custom_node,
)

router = APIRouter()


@router.get('/api/node-manager/state')
async def api_node_manager_state():
    payload = await asyncio.to_thread(list_custom_nodes)
    payload['backend_session'] = get_manager_state().get('session', {}).get('image', {})
    return JSONResponse({'ok': True, **payload})


@router.post('/api/node-manager/settings-save')
async def api_node_manager_settings_save(payload: dict):
    settings = await asyncio.to_thread(save_node_manager_settings, payload or {})
    state = await asyncio.to_thread(list_custom_nodes, settings)
    state['backend_session'] = get_manager_state().get('session', {}).get('image', {})
    return JSONResponse({'ok': True, 'message': 'Node manager settings saved.', **state})


@router.post('/api/node-manager/install')
async def api_node_manager_install(payload: dict):
    git_url = str((payload or {}).get('git_url') or '').strip()
    branch = str((payload or {}).get('branch') or '').strip()
    if not git_url:
        return json_error('Paste a Git URL first.', 400)
    try:
        settings = load_node_manager_settings()
        result = await asyncio.to_thread(install_custom_node, git_url, branch, settings)
        state = await asyncio.to_thread(list_custom_nodes, settings)
        state['backend_session'] = get_manager_state().get('session', {}).get('image', {})
        return JSONResponse({'ok': True, 'message': 'Custom node installed. Restart ComfyUI to load the new nodes.', 'node': result.get('node'), 'log': result.get('log') or get_last_node_manager_log(), **state})
    except Exception as exc:
        return json_error(str(exc), 500)


@router.post('/api/node-manager/update')
async def api_node_manager_update(payload: dict):
    folder_name = str((payload or {}).get('folder_name') or '').strip()
    if not folder_name:
        return json_error('Pick an installed node first.', 400)
    try:
        settings = load_node_manager_settings()
        result = await asyncio.to_thread(update_custom_node, folder_name, settings)
        state = await asyncio.to_thread(list_custom_nodes, settings)
        state['backend_session'] = get_manager_state().get('session', {}).get('image', {})
        return JSONResponse({'ok': True, 'message': 'Custom node updated. Restart ComfyUI to make sure new code is loaded.', 'node': result.get('node'), 'log': result.get('log') or get_last_node_manager_log(), **state})
    except Exception as exc:
        return json_error(str(exc), 500)


@router.post('/api/node-manager/open-folder')
async def api_node_manager_open_folder(payload: dict):
    folder_name = str((payload or {}).get('folder_name') or '').strip()
    try:
        settings = load_node_manager_settings()
        target = await asyncio.to_thread(open_custom_node_path, folder_name, settings)
        state = await asyncio.to_thread(list_custom_nodes, settings)
        state['backend_session'] = get_manager_state().get('session', {}).get('image', {})
        return JSONResponse({'ok': True, 'message': f'Opened {target}', 'opened_path': target, **state})
    except Exception as exc:
        return json_error(str(exc), 500)


@router.post('/api/node-manager/reconnect-image-backend')
async def api_node_manager_reconnect_image_backend():
    session = get_manager_state().get('session', {}).get('image', {})
    profile_id = str(session.get('profile_id') or '').strip()
    result = await (connect_profile('image', profile_id) if profile_id else refresh_profile('image'))
    payload = await asyncio.to_thread(list_custom_nodes)
    payload['backend_session'] = get_manager_state().get('session', {}).get('image', {})
    return JSONResponse({'ok': bool(result.get('ok')), 'message': result.get('message') or 'Image backend refresh finished.', 'probe': result, **payload})
