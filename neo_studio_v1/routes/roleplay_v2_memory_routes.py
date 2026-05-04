from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_memory_compiler import compile_memory_from_canon, compile_memory_from_builder_record, get_memory_fragment, list_project_memory, list_memory_for_record
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/v2/memory/compile-from-canon')
async def api_roleplay_v2_memory_compile_from_canon(canon_id: str = Form('')):
    clean_canon_id = str(canon_id or '').strip()
    if not clean_canon_id:
        return json_error('Canon id is required.', 400)
    try:
        result = compile_memory_from_canon(clean_canon_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': f"Memory compile finished for {clean_canon_id}."})


@router.get('/api/roleplay/v2/memory/fragment')
async def api_roleplay_v2_memory_fragment(fragment_id: str = ''):
    fragment = get_memory_fragment(fragment_id)
    if not fragment:
        return json_error('Memory fragment not found.', 404)
    return JSONResponse({'ok': True, 'memory_fragment': fragment})


@router.get('/api/roleplay/v2/memory/project')
async def api_roleplay_v2_memory_project(project_id: str = ''):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('Project id is required.', 400)
    return JSONResponse({'ok': True, **list_project_memory(clean_project_id)})


@router.post('/api/roleplay/v2/memory/compile-from-builder')
async def api_roleplay_v2_memory_compile_from_builder(record_id: str = Form('')):
    clean_record_id = str(record_id or '').strip()
    if not clean_record_id:
        return json_error('Builder record id is required.', 400)
    try:
        result = compile_memory_from_builder_record(clean_record_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': f"Builder memory compile finished for {clean_record_id}."})


@router.get('/api/roleplay/v2/memory/by-record')
async def api_roleplay_v2_memory_by_record(record_id: str = '', limit: int = 24):
    clean_record_id = str(record_id or '').strip()
    if not clean_record_id:
        return json_error('Record id is required.', 400)
    return JSONResponse({'ok': True, **list_memory_for_record(clean_record_id, limit=limit)})
