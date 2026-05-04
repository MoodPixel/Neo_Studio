from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..utils.app_settings import load_app_settings, save_app_settings
from ..utils.backend_manager import get_manager_state
from ..utils.guide_registry import ensure_support_guides_foundation, load_support_guides
from ..utils.helper_bridge import load_helper_packets
from ..utils.node_manager import list_custom_nodes, load_node_manager_settings
from ..utils.memory_health import build_memory_health_snapshot
from ..utils.system_summary import get_recent_totals
from ..utils.extension_registry import ensure_extension_registry, registry_counts
from ..utils.admin_cleanup import cleanup_targets, clean_targets
from .common import json_error, json_exception

router = APIRouter()


@router.get('/api/admin/overview')
async def api_admin_overview():
    try:
        guides = load_support_guides()
        helper_packets = load_helper_packets()
        ensure_extension_registry()
        node_state = list_custom_nodes(load_node_manager_settings())
        return JSONResponse({
            'ok': True,
            'app_settings': load_app_settings(),
            'backend_state': get_manager_state(),
            'support_guides_count': len(guides.get('guides') or []),
            'helper_packets_count': len(helper_packets.get('packets') or []),
            'extension_registry_counts': registry_counts(),
            'memory_health': build_memory_health_snapshot(),
            'recent_totals': get_recent_totals(),
            'node_manager': {
                'custom_nodes_path_exists': bool(node_state.get('custom_nodes_path_exists')),
                'installed_count': len(node_state.get('nodes') or []),
                'settings': node_state.get('settings') or {},
            },
        })
    except Exception as exc:
        return json_exception(exc, default_message='Could not load admin overview.', default_status=500)



@router.get('/api/admin/storage-cleanup/targets')
async def api_admin_storage_cleanup_targets():
    try:
        return JSONResponse({'ok': True, 'targets': cleanup_targets()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not inspect cleanup targets.', default_status=500)


@router.post('/api/admin/storage-cleanup/clean')
async def api_admin_storage_cleanup_clean(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Cleanup payload was invalid.', 400)
        keys = payload.get('targets')
        if not isinstance(keys, list) or not keys:
            return json_error('Select at least one cleanup target.', 400)
        clean_keys = [str(key).strip() for key in keys if str(key).strip()]
        return JSONResponse(clean_targets(clean_keys))
    except Exception as exc:
        return json_exception(exc, default_message='Could not clean selected folders.', default_status=500)


@router.get('/api/admin/memory-health')
async def api_admin_memory_health():
    try:
        return JSONResponse({'ok': True, 'snapshot': build_memory_health_snapshot()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load memory health snapshot.', default_status=500)


@router.get('/api/admin/settings')
async def api_admin_settings_get():
    try:
        return JSONResponse({'ok': True, 'settings': load_app_settings()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load admin settings.', default_status=500)


@router.post('/api/admin/settings')
async def api_admin_settings_save(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Settings payload was invalid.', 400)
        current = load_app_settings()
        theme = current.get('theme') if isinstance(current.get('theme'), dict) else {}
        startup = current.get('startup') if isinstance(current.get('startup'), dict) else {}
        ui = current.get('ui') if isinstance(current.get('ui'), dict) else {}
        if isinstance(payload.get('theme'), dict):
            theme.update(payload.get('theme') or {})
        if isinstance(payload.get('startup'), dict):
            startup.update(payload.get('startup') or {})
        if isinstance(payload.get('ui'), dict):
            ui.update(payload.get('ui') or {})
        merged = dict(current)
        merged['theme'] = theme
        merged['startup'] = startup
        merged['ui'] = ui
        return JSONResponse({'ok': True, 'settings': save_app_settings(merged)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save admin settings.', default_status=500)
