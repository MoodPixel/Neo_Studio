from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..utils.roleplay_asset_store import resolve_roleplay_asset_path, save_character_avatar, save_story_cover
from ..utils.roleplay_story_store import list_story_cards
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/asset/upload')
async def api_roleplay_asset_upload(
    asset_kind: str = Form(''),
    record_id: str = Form(''),
    file: UploadFile = File(...),
):
    try:
        if asset_kind == 'character_avatar':
            record = await save_character_avatar(record_id, file)
            return JSONResponse({'ok': True, 'record': record, 'message': f"Saved avatar for {record.get('display_name') or record.get('name') or 'character'}."})
        if asset_kind == 'story_cover':
            record = await save_story_cover(record_id, file)
            return JSONResponse({'ok': True, 'record': record, 'stories': list_story_cards(), 'message': f"Saved cover for {record.get('title') or 'story'}."})
        return json_error('Unsupported roleplay asset kind.', 400)
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/asset/file')
async def api_roleplay_asset_file(asset_path: str = ''):
    path = resolve_roleplay_asset_path(asset_path)
    if not path:
        return json_error('Roleplay asset not found.', 404)
    return FileResponse(path)
