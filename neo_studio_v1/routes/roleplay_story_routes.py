from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from ..utils.roleplay_story_store import delete_story_record, get_story_record, list_story_cards, save_story_record
from ..utils.roleplay_story_blueprints import import_story_blueprint
from ..utils.roleplay_session_store import build_story_reader_payload
from ..utils.roleplay_story_exports import persist_story_export, render_story_export
from .common import json_error

router = APIRouter()


@router.get('/api/roleplay/stories')
async def api_roleplay_stories():
    return JSONResponse({'ok': True, 'stories': list_story_cards()})


@router.get('/api/roleplay/story')
async def api_roleplay_story(story_id: str = ''):
    record = get_story_record(story_id)
    if not record:
        return json_error('Story not found.', 404)
    return JSONResponse({'ok': True, 'story': record})


@router.get('/api/roleplay/story-reader')
async def api_roleplay_story_reader(story_id: str = ''):
    try:
        payload = build_story_reader_payload(story_id)
    except Exception as exc:
        return json_error(str(exc), 404)
    return JSONResponse({'ok': True, **payload})




@router.get('/api/roleplay/story/export')
async def api_roleplay_story_export(story_id: str = '', export_format: str = 'md', export_mode: str = 'readable', save_copy: bool = False):
    try:
        content, filename, media_type = render_story_export(story_id, export_format, export_mode)
        saved_path = str(persist_story_export(story_id, export_format, export_mode)) if save_copy else ''
    except Exception as exc:
        return json_error(str(exc), 400)
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
    }
    if saved_path:
        headers['X-Neo-Export-Path'] = saved_path
    return Response(content=content, media_type=media_type, headers=headers)


@router.post('/api/roleplay/story/save')
async def api_roleplay_story_save(
    story_id: str = Form(''),
    title: str = Form(''),
    summary: str = Form(''),
    universe_label: str = Form(''),
    world_label: str = Form(''),
    lead_characters: str = Form(''),
    status: str = Form('draft'),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('roleplay'),
    story_mode: str = Form('linear'),
    branch_option_count: int = Form(3),
    branch_allow_custom_option: bool = Form(True),
    linked_context_json: str = Form('{}'),
):
    try:
        record = save_story_record(
            story_id=story_id,
            title=title,
            summary=summary,
            universe_label=universe_label,
            world_label=world_label,
            lead_characters=lead_characters,
            status=status,
            canon_mode=canon_mode,
            output_preset=output_preset,
            linked_context=linked_context_json,
            story_mode=story_mode,
            option_count=branch_option_count,
            allow_custom_option=branch_allow_custom_option,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'story': record, 'stories': list_story_cards(), 'message': f"Saved story: {record.get('title', 'Story')}"})


@router.post('/api/roleplay/story/delete')
async def api_roleplay_story_delete(story_id: str = Form('')):
    ok = delete_story_record(story_id)
    if not ok:
        return json_error('Story not found.', 404)
    return JSONResponse({'ok': True, 'stories': list_story_cards(), 'message': 'Story deleted.'})


@router.post('/api/roleplay/story/import-blueprint')
async def api_roleplay_story_import_blueprint(
    source_kind: str = Form('auto'),
    title: str = Form(''),
    source_text: str = Form(''),
    status: str = Form('draft'),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('novel'),
    linked_context_json: str = Form('{}'),
    story_mode: str = Form('linear'),
    branch_option_count: int = Form(3),
    branch_allow_custom_option: bool = Form(True),
    file: UploadFile | None = File(None),
):
    try:
        uploaded_text = ''
        filename = ''
        if file is not None:
            filename = str(file.filename or '').strip()
            uploaded_bytes = await file.read()
            uploaded_text = uploaded_bytes.decode('utf-8', errors='ignore') if uploaded_bytes else ''
        payload = import_story_blueprint(
            source_text=source_text or uploaded_text,
            source_kind=source_kind,
            title=title,
            filename=filename,
            status=status,
            canon_mode=canon_mode,
            output_preset=output_preset,
            linked_context=linked_context_json,
            story_mode=story_mode,
            option_count=branch_option_count,
            allow_custom_option=branch_allow_custom_option,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({
        'ok': True,
        **payload,
        'stories': list_story_cards(),
        'message': f"Imported {payload.get('parts_count', 0)} parts into {payload.get('story', {}).get('title', 'story')}",
    })
