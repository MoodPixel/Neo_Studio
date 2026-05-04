from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_story_store import (
    build_story_resume_payload,
    create_story_session,
    create_storyline,
    get_story_checkpoint,
    get_story_session,
    get_storyline_detail,
    list_story_checkpoints,
    list_story_sessions,
    list_storylines,
    publish_checkpoint_shared_continuity,
    save_story_checkpoint,
)
from .common import json_error, json_exception
from ..utils.roleplay_asset_store import save_roleplay_v2_storyline_cover

router = APIRouter()


@router.get('/api/roleplay/v2/stories')
async def api_roleplay_v2_stories():
    return JSONResponse({'ok': True, 'storylines': list_storylines()})


@router.post('/api/roleplay/v2/storyline/create')
async def api_roleplay_v2_storyline_create(
    title: str = Form(''),
    summary: str = Form(''),
    project_id: str = Form(''),
    linked_world_id: str = Form(''),
    linked_universe_id: str = Form(''),
    linked_scenario_ids_json: str = Form('[]'),
    linked_entity_ids_json: str = Form('[]'),
    tags_json: str = Form('[]'),
    continuity_policy: str = Form('runtime_anchored'),
    source_snapshot_id: str = Form(''),
    canon_snapshot_id: str = Form(''),
    active_sandbox_id: str = Form(''),
    root_branch_id: str = Form(''),
):
    try:
        storyline = create_storyline(
            title=title,
            summary=summary,
            project_id=project_id,
            linked_world_id=linked_world_id,
            linked_universe_id=linked_universe_id,
            linked_scenario_ids=linked_scenario_ids_json,
            linked_entity_ids=linked_entity_ids_json,
            tags=tags_json,
            continuity_policy=continuity_policy,
            source_snapshot_id=source_snapshot_id,
            canon_snapshot_id=canon_snapshot_id,
            active_sandbox_id=active_sandbox_id,
            root_branch_id=root_branch_id,
        )
    except Exception as exc:
        return json_exception(exc, default_status=400, context='roleplay v2 storyline create')
    return JSONResponse({'ok': True, 'storyline': storyline, 'storylines': list_storylines(), 'message': f"Created storyline: {storyline.get('title') or 'Storyline'}"})




@router.post('/api/roleplay/v2/storyline/cover-upload')
async def api_roleplay_v2_storyline_cover_upload(
    storyline_id: str = Form(''),
    file: UploadFile = File(...),
):
    try:
        storyline = await save_roleplay_v2_storyline_cover(storyline_id, file)
    except Exception as exc:
        return json_exception(exc, default_status=400, context='roleplay v2 storyline cover upload')
    return JSONResponse({'ok': True, 'storyline': storyline, 'storylines': list_storylines(), 'message': f"Saved cover for {storyline.get('title') or 'storyline'}."})

@router.get('/api/roleplay/v2/storyline')
async def api_roleplay_v2_storyline(storyline_id: str = ''):
    try:
        payload = get_storyline_detail(storyline_id)
    except Exception as exc:
        return json_exception(exc, default_status=404, context='roleplay v2 storyline detail')
    return JSONResponse({'ok': True, **payload})


@router.get('/api/roleplay/v2/story-sessions')
async def api_roleplay_v2_story_sessions(storyline_id: str = ''):
    if not str(storyline_id or '').strip():
        return json_error('Storyline id is required.', 400)
    return JSONResponse({'ok': True, 'sessions': list_story_sessions(storyline_id)})


@router.post('/api/roleplay/v2/story-session/create')
async def api_roleplay_v2_story_session_create(
    storyline_id: str = Form(''),
    project_id: str = Form(''),
    session_mode: str = Form('live_scene'),
    seed_checkpoint_id: str = Form(''),
    seed_runtime_bundle_id: str = Form(''),
    continuity_mode: str = Form('runtime_anchored'),
    source_snapshot_id: str = Form(''),
    canon_snapshot_id: str = Form(''),
    sandbox_id: str = Form(''),
    branch_id: str = Form(''),
    memory_scope: str = Form('sandbox'),
    promotion_scope: str = Form('sandbox_only'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    scene_state_seed_json: str = Form('{}'),
    session_summary: str = Form(''),
):
    try:
        session = create_story_session(
            storyline_id=storyline_id,
            project_id=project_id,
            session_mode=session_mode,
            seed_checkpoint_id=seed_checkpoint_id,
            seed_runtime_bundle_id=seed_runtime_bundle_id,
            continuity_mode=continuity_mode,
            source_snapshot_id=source_snapshot_id,
            canon_snapshot_id=canon_snapshot_id,
            sandbox_id=sandbox_id,
            branch_id=branch_id,
            memory_scope=memory_scope,
            promotion_scope=promotion_scope,
            output_preset=output_preset,
            interaction_mode=interaction_mode,
            scene_state_seed=scene_state_seed_json,
            session_summary=session_summary,
        )
    except Exception as exc:
        return json_exception(exc, default_status=400, context='roleplay v2 story session create')
    return JSONResponse({'ok': True, 'session': session, 'sessions': list_story_sessions(storyline_id), 'message': f"Created story session: {session.get('id') or 'session'}"})


@router.get('/api/roleplay/v2/story-session')
async def api_roleplay_v2_story_session(session_id: str = ''):
    session = get_story_session(session_id)
    if not session:
        return json_error('Story session not found.', 404)
    return JSONResponse({'ok': True, 'session': session})


@router.get('/api/roleplay/v2/story-checkpoints')
async def api_roleplay_v2_story_checkpoints(storyline_id: str = '', session_id: str = ''):
    if not str(storyline_id or '').strip() and not str(session_id or '').strip():
        return json_error('Storyline id or session id is required.', 400)
    return JSONResponse({'ok': True, 'checkpoints': list_story_checkpoints(storyline_id=storyline_id, session_id=session_id)})


@router.post('/api/roleplay/v2/story-checkpoint/save')
async def api_roleplay_v2_story_checkpoint_save(
    storyline_id: str = Form(''),
    session_id: str = Form(''),
    title: str = Form(''),
    summary: str = Form(''),
    checkpoint_type: str = Form('live_save'),
    transcript_json: str = Form('[]'),
    scene_text: str = Form(''),
    scene_state_json: str = Form('{}'),
    continuity_payload_json: str = Form('{}'),
    runtime_bundle_id: str = Form(''),
    runtime_source_scope: str = Form(''),
    runtime_source_id: str = Form(''),
    source_snapshot_id: str = Form(''),
    canon_snapshot_id: str = Form(''),
    sandbox_id: str = Form(''),
    branch_id: str = Form(''),
    memory_scope: str = Form('sandbox'),
    promotion_scope: str = Form('sandbox_only'),
    selected_entity_ids_json: str = Form('[]'),
    selected_memory_ids_json: str = Form('[]'),
    linked_scenario_ids_json: str = Form('[]'),
    linked_entity_ids_json: str = Form('[]'),
    parent_checkpoint_id: str = Form(''),
    branch_label: str = Form(''),
    branch_choice_json: str = Form('{}'),
):
    try:
        checkpoint = save_story_checkpoint(
            storyline_id=storyline_id,
            session_id=session_id,
            title=title,
            summary=summary,
            checkpoint_type=checkpoint_type,
            transcript=transcript_json,
            scene_text=scene_text,
            scene_state=scene_state_json,
            continuity_payload=continuity_payload_json,
            runtime_bundle_id=runtime_bundle_id,
            runtime_source_scope=runtime_source_scope,
            runtime_source_id=runtime_source_id,
            source_snapshot_id=source_snapshot_id,
            canon_snapshot_id=canon_snapshot_id,
            sandbox_id=sandbox_id,
            branch_id=branch_id,
            memory_scope=memory_scope,
            promotion_scope=promotion_scope,
            selected_entity_ids=selected_entity_ids_json,
            selected_memory_ids=selected_memory_ids_json,
            linked_scenario_ids=linked_scenario_ids_json,
            linked_entity_ids=linked_entity_ids_json,
            parent_checkpoint_id=parent_checkpoint_id,
            branch_label=branch_label,
            branch_choice=branch_choice_json,
        )
    except Exception as exc:
        return json_exception(exc, default_status=400, context='roleplay v2 story checkpoint save')
    return JSONResponse({
        'ok': True,
        'checkpoint': checkpoint,
        'checkpoints': list_story_checkpoints(storyline_id=storyline_id, session_id=session_id),
        'message': f"Saved checkpoint: {checkpoint.get('title') or 'Checkpoint'}",
    })


@router.post('/api/roleplay/v2/story-checkpoint/publish-shared')
async def api_roleplay_v2_story_checkpoint_publish_shared(
    storyline_id: str = Form(''),
    session_id: str = Form(''),
    checkpoint_id: str = Form(''),
    publish_scope: str = Form('shared_world'),
):
    try:
        publication = publish_checkpoint_shared_continuity(
            storyline_id=storyline_id,
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            publish_scope=publish_scope,
        )
        detail = get_storyline_detail(publication.get('storyline_id') or storyline_id)
    except Exception as exc:
        return json_exception(exc, default_status=400, context='roleplay v2 story shared continuity publish')
    message_scope = str(publication.get('publish_scope') or 'shared continuity').replace('shared_', 'shared ')
    return JSONResponse({
        'ok': True,
        'publication': publication,
        'storyline': detail.get('storyline'),
        'sessions': detail.get('sessions'),
        'checkpoints': detail.get('checkpoints'),
        'message': f"Published checkpoint continuity to {message_scope}.",
    })


@router.get('/api/roleplay/v2/story-checkpoint')
async def api_roleplay_v2_story_checkpoint(checkpoint_id: str = ''):
    checkpoint = get_story_checkpoint(checkpoint_id)
    if not checkpoint:
        return json_error('Story checkpoint not found.', 404)
    return JSONResponse({'ok': True, 'checkpoint': checkpoint})


@router.get('/api/roleplay/v2/story-resume')
async def api_roleplay_v2_story_resume(storyline_id: str = '', session_id: str = '', checkpoint_id: str = ''):
    try:
        payload = build_story_resume_payload(storyline_id=storyline_id, session_id=session_id, checkpoint_id=checkpoint_id)
    except Exception as exc:
        return json_exception(exc, default_status=404, context='roleplay v2 story resume')
    return JSONResponse({'ok': True, **payload})
