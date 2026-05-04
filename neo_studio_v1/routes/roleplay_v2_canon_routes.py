from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_canon_compiler import compile_approved_breakdown, get_canon_record, list_project_canon
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/v2/canon/compile-from-breakdown')
async def api_roleplay_v2_canon_compile_from_breakdown(helper_output_id: str = Form(''), allow_unapproved: str = Form('false')):
    clean_helper_output_id = str(helper_output_id or '').strip()
    if not clean_helper_output_id:
        return json_error('Helper output id is required.', 400)
    try:
        result = compile_approved_breakdown(
            clean_helper_output_id,
            allow_unapproved=str(allow_unapproved or '').strip().lower() in {'1', 'true', 'yes', 'on'},
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    canon_id = ((result.get('canon_record') or {}).get('id') or '').strip()
    return JSONResponse({'ok': True, **result, 'message': f'Canon compile finished as {canon_id}.'})


@router.get('/api/roleplay/v2/canon/record')
async def api_roleplay_v2_canon_record(canon_id: str = ''):
    record = get_canon_record(canon_id)
    if not record:
        return json_error('Canon record not found.', 404)
    return JSONResponse({'ok': True, 'canon_record': record})


@router.get('/api/roleplay/v2/canon/project')
async def api_roleplay_v2_canon_project(project_id: str = ''):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('Project id is required.', 400)
    return JSONResponse({'ok': True, **list_project_canon(clean_project_id)})
