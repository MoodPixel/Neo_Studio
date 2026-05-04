from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_runtime_bundle import build_runtime_bundle, get_runtime_bundle, list_project_runtime_bundles, get_runtime_bundle_trace, build_runtime_recovery_eval
from ..utils.roleplay_v2_story_store import resolve_story_scope_from_ids
from ..utils.roleplay_v2_sqlite_store import fetch_rp2_retrieval_trace_rows, fetch_rp2_chroma_status, sync_rp2_memory_to_chroma, query_rp2_chroma_debug, fetch_rp2_turn_summary_debug_rows, fetch_rp2_post_turn_memory_debug_rows, evaluate_rp2_writeback_rows, set_rp2_memory_control, fetch_rp2_continuity_control_rows
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/v2/runtime/build')
async def api_roleplay_v2_runtime_build(
    mode: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    source_scope: str = Form('project'),
    source_id: str = Form(''),
    project_id: str = Form(''),
    entity_id: str = Form(''),
    query: str = Form(''),
    top_k: int = Form(8),
    save_bundle: bool = Form(True),
    storyline_id: str = Form(''),
    session_id: str = Form(''),
    checkpoint_id: str = Form(''),
    source_snapshot_id: str = Form(''),
    canon_snapshot_id: str = Form(''),
    sandbox_id: str = Form(''),
    branch_id: str = Form(''),
    memory_scope: str = Form(''),
    promotion_scope: str = Form(''),
):
    try:
        resolved_scope = resolve_story_scope_from_ids(storyline_id=storyline_id, session_id=session_id, checkpoint_id=checkpoint_id) if any([storyline_id, session_id, checkpoint_id]) else {}
        story_scope = (resolved_scope.get('story_scope') if isinstance(resolved_scope, dict) else {}) or {}
        result = build_runtime_bundle(
            mode=mode,
            interaction_mode=interaction_mode,
            source_scope=source_scope,
            source_id=source_id,
            project_id=project_id,
            entity_id=entity_id,
            query=query,
            top_k=top_k,
            save_bundle=save_bundle,
            storyline_id=storyline_id or story_scope.get('storyline_id') or '',
            session_id=session_id or story_scope.get('session_id') or '',
            checkpoint_id=checkpoint_id or story_scope.get('checkpoint_id') or '',
            source_snapshot_id=source_snapshot_id or story_scope.get('source_snapshot_id') or '',
            canon_snapshot_id=canon_snapshot_id or story_scope.get('canon_snapshot_id') or '',
            sandbox_id=sandbox_id or story_scope.get('sandbox_id') or '',
            branch_id=branch_id or story_scope.get('branch_id') or '',
            memory_scope=memory_scope or story_scope.get('memory_scope') or '',
            promotion_scope=promotion_scope or story_scope.get('promotion_scope') or '',
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': 'Runtime bundle built.'})


@router.get('/api/roleplay/v2/runtime/bundle')
async def api_roleplay_v2_runtime_bundle(bundle_id: str = ''):
    row = get_runtime_bundle(bundle_id)
    if not row:
        return json_error('Runtime bundle not found.', 404)
    return JSONResponse({'ok': True, 'bundle': row})


@router.get('/api/roleplay/v2/runtime/project')
async def api_roleplay_v2_runtime_project(project_id: str = ''):
    return JSONResponse({'ok': True, **list_project_runtime_bundles(project_id)})


@router.get('/api/roleplay/v2/runtime/retrieval-trace')
async def api_roleplay_v2_runtime_retrieval_trace(bundle_id: str = ''):
    row = get_runtime_bundle_trace(bundle_id)
    if not row:
        return json_error('Runtime bundle trace not found.', 404)
    return JSONResponse({'ok': True, **row})


@router.get('/api/roleplay/v2/runtime/retrieval-history')
async def api_roleplay_v2_runtime_retrieval_history(project_id: str = '', entity_id: str = '', bundle_id: str = '', query: str = '', limit: int = 20):
    return JSONResponse({'ok': True, **fetch_rp2_retrieval_trace_rows(project_id=project_id, entity_id=entity_id, bundle_id=bundle_id, query=query, limit=limit)})


@router.get('/api/roleplay/v2/runtime/retrieval-history-entry')
async def api_roleplay_v2_runtime_retrieval_history_entry(trace_id: str = ''):
    data = fetch_rp2_retrieval_trace_rows(trace_id=trace_id, limit=1)
    rows = data.get('rows') if isinstance(data.get('rows'), list) else []
    if not rows:
        return json_error('Retrieval history entry not found.', 404)
    return JSONResponse({'ok': True, 'entry': rows[0]})




@router.get('/api/roleplay/v2/runtime/recovery-eval')
async def api_roleplay_v2_runtime_recovery_eval(bundle_id: str = '', trace_id: str = '', project_id: str = '', entity_id: str = '', query: str = '', mode: str = 'roleplay', top_k: int = 8):
    try:
        payload = build_runtime_recovery_eval(bundle_id=bundle_id, trace_id=trace_id, project_id=project_id, entity_id=entity_id, query=query, mode=mode, top_k=top_k)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse(payload)

@router.get('/api/roleplay/v2/runtime/chroma-status')
async def api_roleplay_v2_runtime_chroma_status():
    return JSONResponse({'ok': True, **fetch_rp2_chroma_status()})


@router.post('/api/roleplay/v2/runtime/chroma-sync')
async def api_roleplay_v2_runtime_chroma_sync(project_id: str = Form(''), entity_id: str = Form(''), limit: int = Form(500)):
    return JSONResponse({'ok': True, **sync_rp2_memory_to_chroma(project_id=project_id, entity_id=entity_id, limit=limit)})


@router.get('/api/roleplay/v2/runtime/chroma-query')
async def api_roleplay_v2_runtime_chroma_query(query_text: str = '', project_id: str = '', entity_id: str = '', limit: int = 12):
    return JSONResponse({'ok': True, **query_rp2_chroma_debug(query_text=query_text, project_id=project_id, entity_id=entity_id, limit=limit)})




@router.get('/api/roleplay/v2/runtime/writeback-eval')
async def api_roleplay_v2_runtime_writeback_eval(bundle_id: str = '', project_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 24):
    return JSONResponse(evaluate_rp2_writeback_rows(bundle_id=bundle_id, project_id=project_id, entity_id=entity_id, source_ref=source_ref, query=query, limit=limit))

@router.get('/api/roleplay/v2/runtime/writeback-turn-summaries')
async def api_roleplay_v2_runtime_writeback_turn_summaries(bundle_id: str = '', project_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 16):
    return JSONResponse(fetch_rp2_turn_summary_debug_rows(bundle_id=bundle_id, project_id=project_id, entity_id=entity_id, source_ref=source_ref, query=query, limit=limit))


@router.get('/api/roleplay/v2/runtime/writeback-memory')
async def api_roleplay_v2_runtime_writeback_memory(bundle_id: str = '', entity_id: str = '', source_ref: str = '', query: str = '', limit: int = 24):
    return JSONResponse(fetch_rp2_post_turn_memory_debug_rows(bundle_id=bundle_id, entity_id=entity_id, source_ref=source_ref, query=query, limit=limit))


@router.get('/api/roleplay/v2/runtime/continuity-rows')
async def api_roleplay_v2_runtime_continuity_rows(project_id: str = '', entity_id: str = '', bundle_id: str = '', trace_id: str = '', source_ref: str = '', query: str = '', origin: str = 'auto', memory_ids: str = '', limit: int = 24):
    ids = [item.strip() for item in str(memory_ids or '').split(',') if item.strip()]
    try:
        payload = fetch_rp2_continuity_control_rows(project_id=project_id, entity_id=entity_id, bundle_id=bundle_id, trace_id=trace_id, source_ref=source_ref, query=query, origin=origin, memory_ids=ids, limit=limit)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse(payload)


@router.post('/api/roleplay/v2/runtime/memory-control')
async def api_roleplay_v2_runtime_memory_control(memory_id: str = Form(''), project_id: str = Form(''), entity_id: str = Form(''), action: str = Form('pin'), cooldown_minutes: int = Form(60)):
    try:
        payload = set_rp2_memory_control(memory_id=memory_id, project_id=project_id, entity_id=entity_id, action=action, cooldown_minutes=cooldown_minutes)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse(payload)
