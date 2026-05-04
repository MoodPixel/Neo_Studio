from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_retrieval import query_memory, rebuild_retrieval, retrieval_status, update_retrieval_settings
from ..utils.roleplay_v2_story_store import resolve_story_scope_from_ids
from .common import json_error

router = APIRouter()


@router.get('/api/roleplay/v2/retrieval/status')
async def api_roleplay_v2_retrieval_status():
    return JSONResponse({'ok': True, **retrieval_status()})


@router.post('/api/roleplay/v2/retrieval/settings/save')
async def api_roleplay_v2_retrieval_settings_save(
    backend: str = Form(''),
    embedding_model_path: str = Form(''),
    reranker_backend: str = Form(''),
    reranker_model_path: str = Form(''),
    top_k: int = Form(8),
    preview_k: int = Form(16),
):
    try:
        settings = update_retrieval_settings(
            backend=backend,
            embedding_model_path=embedding_model_path,
            reranker_backend=reranker_backend,
            reranker_model_path=reranker_model_path,
            top_k=top_k,
            preview_k=preview_k,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'settings': settings, 'message': 'Retrieval settings saved.'})


@router.post('/api/roleplay/v2/retrieval/reindex')
async def api_roleplay_v2_retrieval_reindex():
    try:
        result = rebuild_retrieval()
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': 'Retrieval index rebuilt.'})


@router.post('/api/roleplay/v2/retrieval/query')
async def api_roleplay_v2_retrieval_query(
    query: str = Form(''),
    project_id: str = Form(''),
    entity_id: str = Form(''),
    memory_type: str = Form(''),
    top_k: int = Form(8),
    preview_k: int = Form(16),
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
        result = query_memory(
            query=query,
            project_id=project_id,
            entity_id=entity_id,
            memory_type=memory_type,
            top_k=top_k,
            preview_k=preview_k,
            source_snapshot_id=source_snapshot_id or story_scope.get('source_snapshot_id') or '',
            canon_snapshot_id=canon_snapshot_id or story_scope.get('canon_snapshot_id') or '',
            sandbox_id=sandbox_id or story_scope.get('sandbox_id') or '',
            storyline_id=storyline_id or story_scope.get('storyline_id') or '',
            session_id=session_id or story_scope.get('session_id') or '',
            checkpoint_id=checkpoint_id or story_scope.get('checkpoint_id') or '',
            branch_id=branch_id or story_scope.get('branch_id') or '',
            memory_scope=memory_scope or story_scope.get('memory_scope') or '',
            promotion_scope=promotion_scope or story_scope.get('promotion_scope') or '',
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result})
