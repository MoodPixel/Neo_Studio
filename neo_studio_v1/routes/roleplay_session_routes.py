from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_session_store import (
    autosave_session_snapshot,
    branch_story_part,
    build_session_payload,
    build_story_branch_map,
    get_part_record,
    list_story_parts,
    load_latest_session_snapshot,
    save_part_edits,
    save_part_from_session,
)
from ..utils.roleplay_story_store import list_story_cards
from .common import json_error

router = APIRouter()

@router.get('/api/roleplay/story-parts')
async def api_roleplay_story_parts(story_id: str = ''):
    return JSONResponse({'ok': True, 'parts': list_story_parts(story_id)})

@router.post('/api/roleplay/session/save-part')
async def api_roleplay_session_save_part(
    story_id: str = Form(''),
    part_id: str = Form(''),
    part_title: str = Form(''),
    roleplay_state_json: str = Form('{}'),
):
    try:
        roleplay_state = json.loads(roleplay_state_json or '{}')
        if not isinstance(roleplay_state, dict):
            roleplay_state = {}
        part = save_part_from_session(story_id=story_id, part_id=part_id, part_title=part_title, roleplay_state=roleplay_state)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'part': part, 'parts': list_story_parts(story_id), 'stories': list_story_cards(), 'message': f"Saved part: {part.get('title', 'Part')}"})

@router.get('/api/roleplay/session/load-part')
async def api_roleplay_session_load_part(story_id: str = '', part_id: str = ''):
    try:
        payload = build_session_payload(story_id=story_id, part_id=part_id)
    except Exception as exc:
        return json_error(str(exc), 404)
    return JSONResponse({'ok': True, 'session': payload, 'message': 'Story part loaded into Roleplay.'})

@router.post('/api/roleplay/session/autosave')
async def api_roleplay_session_autosave(story_id: str = Form(''), part_id: str = Form(''), roleplay_state_json: str = Form('{}')):
    try:
        roleplay_state = json.loads(roleplay_state_json or '{}')
        if not isinstance(roleplay_state, dict):
            roleplay_state = {}
        autosave_session_snapshot(roleplay_state, story_id=story_id, part_id=part_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'message': 'Roleplay draft autosaved.'})

@router.get('/api/roleplay/session/recover')
async def api_roleplay_session_recover():
    payload = load_latest_session_snapshot()
    if not payload:
        return json_error('No saved roleplay draft found yet.', 404)
    return JSONResponse({'ok': True, 'session': payload, 'message': 'Recovered last roleplay draft.'})


@router.get('/api/roleplay/part')
async def api_roleplay_part(part_id: str = ''):
    part = get_part_record(part_id)
    if not part:
        return json_error('Story part not found.', 404)
    return JSONResponse({'ok': True, 'part': part})


@router.post('/api/roleplay/part/save')
async def api_roleplay_part_save(
    part_id: str = Form(''),
    title: str = Form(''),
    summary: str = Form(''),
    scene_notes: str = Form(''),
    pinned_canon: str = Form(''),
    scene_text: str = Form(''),
    linked_context_json: str = Form('{}'),
):
    try:
        part = save_part_edits(part_id=part_id, title=title, summary=summary, scene_notes=scene_notes, pinned_canon=pinned_canon, scene_text=scene_text, linked_context=linked_context_json)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'part': part, 'parts': list_story_parts(str(part.get('story_id') or '').strip()), 'stories': list_story_cards(), 'message': f"Saved part: {part.get('title', 'Part')}"})


@router.get('/api/roleplay/story-branch-map')
async def api_roleplay_story_branch_map(story_id: str = ''):
    try:
        payload = build_story_branch_map(story_id)
    except Exception as exc:
        return json_error(str(exc), 404)
    return JSONResponse({'ok': True, **payload})


@router.post('/api/roleplay/part/branch')
async def api_roleplay_part_branch(
    part_id: str = Form(''),
    branch_label: str = Form(''),
    choice_id: str = Form(''),
    choice_label: str = Form(''),
    choice_text: str = Form(''),
    choice_source: str = Form('generated'),
):
    try:
        part = branch_story_part(
            part_id=part_id,
            branch_label=branch_label,
            choice_id=choice_id,
            choice_label=choice_label,
            choice_text=choice_text,
            choice_source=choice_source,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    story_id = str(part.get('story_id') or '').strip()
    return JSONResponse({
        'ok': True,
        'part': part,
        'parts': list_story_parts(story_id),
        'branch_map': build_story_branch_map(story_id),
        'stories': list_story_cards(),
        'message': f"Created branch: {part.get('title', 'Part')}",
    })
