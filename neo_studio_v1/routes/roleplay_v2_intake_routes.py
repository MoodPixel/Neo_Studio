from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_creator_intake import preview_creator_input, save_preview_as_draft, get_saved_draft
from .common import json_error, parse_bool

router = APIRouter()


@router.post('/api/roleplay/v2/intake/preview-text')
async def api_roleplay_v2_intake_preview_text(
    intake_mode: str = Form('helper_assisted'),
    helper_mode: str = Form('structure_only'),
    target_kind: str = Form(''),
    source_name: str = Form('editor_input.txt'),
    source_text: str = Form(''),
    target_id: str = Form(''),
):
    clean_text = str(source_text or '').strip()
    if not clean_text:
        return json_error('Paste source text or JSON first.', 400)
    try:
        preview = preview_creator_input(
            intake_mode=intake_mode,
            helper_mode=helper_mode,
            target_kind=target_kind,
            source_name=source_name,
            source_text=source_text,
            target_id=target_id,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **preview, 'message': f"Preview ready for {preview.get('detected_kind') or target_kind or 'record'} via {preview['intake_mode']}."})


@router.post('/api/roleplay/v2/intake/preview-file')
async def api_roleplay_v2_intake_preview_file(
    intake_mode: str = Form('helper_assisted'),
    helper_mode: str = Form('structure_only'),
    target_kind: str = Form(''),
    target_id: str = Form(''),
    file: UploadFile | None = File(None),
):
    if file is None:
        return json_error('Choose a file first.', 400)
    try:
        content = await file.read()
        source_text = content.decode('utf-8', errors='ignore')
        preview = preview_creator_input(
            intake_mode=intake_mode,
            helper_mode=helper_mode,
            target_kind=target_kind,
            source_name=file.filename or 'upload.txt',
            source_text=source_text,
            target_id=target_id,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **preview, 'message': f"Preview ready from {file.filename or 'upload'} via {preview['intake_mode']}."})


@router.post('/api/roleplay/v2/intake/save-draft')
async def api_roleplay_v2_intake_save_draft(preview_id: str = Form(''), approved: str = Form('false')):
    clean_preview_id = str(preview_id or '').strip()
    if not clean_preview_id:
        return json_error('Preview id is required.', 400)
    try:
        result = save_preview_as_draft(clean_preview_id, approved=parse_bool(approved))
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': 'Draft saved to Roleplay V2 creator lanes.'})


@router.get('/api/roleplay/v2/intake/draft')
async def api_roleplay_v2_intake_draft(draft_id: str = ''):
    draft = get_saved_draft(draft_id)
    if not draft:
        return json_error('Draft not found.', 404)
    return JSONResponse({'ok': True, 'draft_record': draft})
