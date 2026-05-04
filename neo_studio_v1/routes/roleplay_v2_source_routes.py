from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_source_assist import draft_source_document_json
from ..utils.roleplay_v2_source_projects import (
    create_novel_project,
    get_novel_project,
    get_project_workspace,
    get_source_document,
    list_novel_projects,
    save_source_document,
)
from .common import json_error

router = APIRouter()


def _json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw or '[]')
        return data if isinstance(data, list) else []
    except Exception:
        return []


@router.post('/api/roleplay/v2/source/project/create')
async def api_roleplay_v2_source_project_create(
    title: str = Form(''),
    author: str = Form(''),
    source_language: str = Form('en'),
    linked_world_id: str = Form(''),
    linked_universe_id: str = Form(''),
    extra_json: str = Form('{}'),
):
    clean_title = str(title or '').strip()
    if not clean_title:
        return json_error('Project title is required.', 400)
    try:
        extra = json.loads(extra_json or '{}') if extra_json else {}
    except Exception:
        extra = {}
    try:
        project = create_novel_project(
            title=clean_title,
            author=author,
            source_language=source_language,
            linked_world_id=linked_world_id,
            linked_universe_id=linked_universe_id,
            extra=extra if isinstance(extra, dict) else {},
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'project': project, 'message': f"Created source project {project['title']}."})


@router.get('/api/roleplay/v2/source/project/list')
async def api_roleplay_v2_source_project_list():
    return JSONResponse({'ok': True, 'projects': list_novel_projects()})


@router.get('/api/roleplay/v2/source/project')
async def api_roleplay_v2_source_project(project_id: str = ''):
    project = get_novel_project(project_id)
    if not project:
        return json_error('Project not found.', 404)
    return JSONResponse({'ok': True, 'project': project})


@router.get('/api/roleplay/v2/source/project/workspace')
async def api_roleplay_v2_source_project_workspace(project_id: str = ''):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('Project id is required.', 400)
    try:
        workspace = get_project_workspace(clean_project_id)
    except Exception as exc:
        return json_error(str(exc), 404)
    return JSONResponse({'ok': True, **workspace})


@router.post('/api/roleplay/v2/source/document/save-text')
async def api_roleplay_v2_source_document_save_text(
    project_id: str = Form(''),
    title: str = Form(''),
    source_name: str = Form(''),
    raw_text: str = Form(''),
    cleaned_text: str = Form(''),
    source_format: str = Form('text'),
    document_type: str = Form('novel_chapter'),
    order_index: int = Form(0),
    chapter_number: int = Form(0),
    scene_number: int = Form(0),
    linked_entity_ids_json: str = Form('[]'),
    extra_json: str = Form('{}'),
):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('Project id is required.', 400)
    clean_raw_text = str(raw_text or '').strip()
    if not clean_raw_text:
        return json_error('Source text is required.', 400)
    try:
        extra = json.loads(extra_json or '{}') if extra_json else {}
    except Exception:
        extra = {}
    try:
        document = save_source_document(
            project_id=clean_project_id,
            title=title,
            source_name=source_name,
            raw_text=clean_raw_text,
            cleaned_text=cleaned_text,
            source_format=source_format,
            document_type=document_type,
            order_index=order_index,
            chapter_number=chapter_number,
            scene_number=scene_number,
            linked_entity_ids=_json_list(linked_entity_ids_json),
            extra=extra if isinstance(extra, dict) else {},
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'document': document, 'message': f"Saved source document {document['title'] or document['id']}."})


@router.post('/api/roleplay/v2/source/document/upload')
async def api_roleplay_v2_source_document_upload(
    project_id: str = Form(''),
    title: str = Form(''),
    document_type: str = Form('novel_chapter'),
    order_index: int = Form(0),
    chapter_number: int = Form(0),
    scene_number: int = Form(0),
    linked_entity_ids_json: str = Form('[]'),
    extra_json: str = Form('{}'),
    file: UploadFile | None = File(None),
):
    if file is None:
        return json_error('Choose a source file first.', 400)
    try:
        content = await file.read()
        raw_text = content.decode('utf-8', errors='ignore')
    except Exception as exc:
        return json_error(str(exc), 400)
    try:
        extra = json.loads(extra_json or '{}') if extra_json else {}
    except Exception:
        extra = {}
    try:
        document = save_source_document(
            project_id=str(project_id or '').strip(),
            title=title or file.filename or '',
            source_name=file.filename or 'upload.txt',
            raw_text=raw_text,
            source_format='text' if str(file.filename or '').lower().endswith('.txt') else 'markdown' if str(file.filename or '').lower().endswith('.md') else 'text',
            document_type=document_type,
            order_index=order_index,
            chapter_number=chapter_number,
            scene_number=scene_number,
            linked_entity_ids=_json_list(linked_entity_ids_json),
            extra=extra if isinstance(extra, dict) else {},
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'document': document, 'message': f"Uploaded source document {document['source_name']}."})




@router.post('/api/roleplay/v2/source/assist-json')
async def api_roleplay_v2_source_assist_json(
    brief: str = Form(''),
    source_text: str = Form(''),
    source_name: str = Form(''),
    draft_mode: str = Form('draft_scratch'),
    draft_style: str = Form('balanced'),
    model: str = Form('default'),
    current_json: str = Form(''),
    max_tokens: int = Form(1200),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(50),
    file: UploadFile | None = File(None),
):
    clean_source_text = str(source_text or '').strip()
    clean_source_name = str(source_name or '').strip()
    if file is not None:
        try:
            uploaded_bytes = await file.read()
            uploaded_text = uploaded_bytes.decode('utf-8', errors='ignore')
        except Exception as exc:
            return json_error(str(exc), 400)
        if not clean_source_text:
            clean_source_text = uploaded_text
        if not clean_source_name:
            clean_source_name = str(file.filename or '').strip()
    try:
        draft = await draft_source_document_json(
            brief=brief,
            source_text=clean_source_text,
            source_name=clean_source_name,
            current_json=current_json,
            mode=draft_mode,
            draft_style=draft_style,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    record = draft.get('record') if isinstance(draft.get('record'), dict) else {}
    document_type = str(record.get('document_type') or '').replace('_', ' ') or 'source document'
    return JSONResponse({
        'ok': True,
        **draft,
        'message': f"Source assist drafted {document_type} JSON. Review it, then send it into Source ingest.",
    })


@router.get('/api/roleplay/v2/source/document')
async def api_roleplay_v2_source_document(document_id: str = ''):
    document = get_source_document(document_id)
    if not document:
        return json_error('Source document not found.', 404)
    return JSONResponse({'ok': True, 'document': document})
