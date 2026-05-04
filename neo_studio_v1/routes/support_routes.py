from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..utils.guide_registry import ensure_support_guides_foundation, list_support_guides, upsert_support_guide
from ..utils.helper_bridge import create_helper_packet, list_helper_packets
from .common import json_error, json_exception

router = APIRouter()


@router.get('/api/support/guides')
async def api_support_guides(surface: str = '', section: str = ''):
    try:
        ensure_support_guides_foundation()
        return JSONResponse({'ok': True, 'schema_version': 1, 'guides': list_support_guides(surface=surface, section=section)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load support guides.', default_status=500)


@router.post('/api/support/guide')
async def api_support_guide_upsert(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Guide payload was invalid.', 400)
        record = upsert_support_guide(payload)
        return JSONResponse({'ok': True, 'record': record})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save support guide.', default_status=500)


@router.get('/api/support/helper-packets')
async def api_helper_packets(source_surface: str = '', target_mode: str = '', limit: int = 20):
    try:
        return JSONResponse({'ok': True, 'schema_version': 1, 'packets': list_helper_packets(source_surface=source_surface, target_mode=target_mode, limit=limit)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load helper packets.', default_status=500)


@router.post('/api/support/helper-packets')
async def api_helper_packet_create(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Helper packet payload was invalid.', 400)
        record = create_helper_packet(payload)
        return JSONResponse({'ok': True, 'record': record})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save helper packet.', default_status=500)
