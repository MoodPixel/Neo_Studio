from __future__ import annotations
import json
import re
from pathlib import Path
from fastapi import APIRouter, File, Form, UploadFile, Body
from fastapi.responses import JSONResponse, StreamingResponse
from ..utils.assistant_chat import stream_assistant_reply, transform_assistant_text
from ..utils.assistant_persona_layer import build_assistant_persona_preview
from ..utils.assistant_context_builder import build_assistant_context_pack
from ..utils.assistant_repo_indexer import build_repo_index, load_repo_index, search_repo_index
from ..utils.assistant_patch_planner import validate_patch_plan, preview_patch_plan, apply_patch_plan
from ..utils.assistant_action_memory import record_manual_task_memory, recent_action_memory
from ..utils.assistant_local_pc_control import list_local_action_catalog, preview_local_action, execute_local_action
from ..utils.assistant_validation_logs import run_assistant_validation_suite, read_assistant_logs, log_assistant_event
from ..utils.assistant_project_profiles import list_project_profiles, resolve_project_profile
from ..utils.assistant_tools.registry import get_assistant_tool_catalog, list_assistant_tools
from ..utils.assistant_tools.executor import preview_assistant_tool_call, execute_assistant_tool
from ..utils.memory_service.assistant_adapter import sync_assistant_profile, sync_assistant_project, sync_assistant_session
from ..utils.memory_service.chroma_store import (
    ASSISTANT_COLLECTION,
    ROLEPLAY_COLLECTION,
    delete_memory_chunk_ids,
    get_embedding_backend_status,
    reindex_active_backend_from_sqlite,
    set_active_embedding_backend,
)
from ..utils.memory_service.retriever import build_memory_pack
from ..utils.memory_service.assistant_embedding_runtime import (
    get_assistant_model_status,
    update_assistant_model_settings,
)
from ..utils.memory_service.reranker import get_reranker_status
from ..utils.memory_service.sqlite_store import (
    delete_summary_record_ids,
    execute,
    fetch_memory_admin_overview,
    fetch_memory_chunk_by_id,
    fetch_memory_chunks,
    fetch_memory_write_logs,
    fetch_summary_records,
    mark_memory_chunk_ids_deleted,
    record_memory_write,
    sqlite_conn,
    update_memory_chunk_state,
    bulk_update_memory_chunk_sandbox,
)
from ..utils.assistant_knowledge_ingestion import (
    MAX_KNOWLEDGE_UPLOAD_BYTES,
    ingest_knowledge_document,
    list_project_import_reports,
)
from ..utils.assistant_record_conversion import preview_raw_text_record_conversion
from ..utils.assistant_retrieval_tests import generate_retrieval_test_questions, run_retrieval_tests
from ..utils.assistant_memory_reindex import memory_index_state, refresh_memory_indexes, refresh_after_memory_write
from ..utils.assistant_manual_capture import (
    MAX_MANUAL_CAPTURE_CHARS,
    capture_manual_memory,
)
from ..utils.assistant_entity_registry import (
    fetch_project_entities,
    fetch_project_relationships,
    project_entity_graph_summary,
)
from ..utils.assistant_canon_workflow import (
    analyze_canon_change,
    apply_canon_change_proposal,
    create_canon_change_proposal,
    list_canon_change_proposals,
    list_entity_change_history,
)
from ..utils.assistant_store import (
    create_session,
    delete_session,
    ensure_assistant_foundation,
    list_modes,
    list_projects,
    list_sessions,
    load_profile,
    load_project,
    load_session,
    create_project,
    rename_project,
    rename_session,
    delete_project,
    save_profile,
    save_session,
    update_project,
)
from .common import json_error
router = APIRouter()
MAX_CONTEXT_UPLOAD_BYTES = 1024 * 1024
ensure_assistant_foundation()


def _project_id_from_payload_session(payload: dict, session: dict) -> str:
    payload = payload if isinstance(payload, dict) else {}
    session = session if isinstance(session, dict) else {}
    candidates = [
        session.get('project_id'),
        payload.get('project_id'),
        payload.get('active_project_id'),
        payload.get('selected_project_id'),
        session.get('active_project_id'),
        session.get('selected_project_id'),
        session.get('default_project_id'),
    ]
    for value in candidates:
        clean = str(value or '').strip()
        if clean:
            return clean
    return ''


def _assistant_project_context(project: dict) -> dict:
    project = project if isinstance(project, dict) else {}
    return {
        'title': project.get('title') or '',
        'description': project.get('description') or '',
        'brief': project.get('brief') or '',
        'project_type': project.get('project_type') or 'general',
        'custom_profile': project.get('custom_profile') if isinstance(project.get('custom_profile'), dict) else {},
        'project_profile': resolve_project_profile(project),
        'context_cards': project.get('context_cards') or [],
        'context_files': project.get('context_files') or [],
    }


def _hydrate_assistant_session_project(payload: dict, session: dict) -> dict:
    session = session if isinstance(session, dict) else {}
    project_id = _project_id_from_payload_session(payload, session)
    if not project_id:
        return session
    project = load_project(project_id)
    if not project:
        return {**session, 'project_id': project_id}
    return {**session, 'project_id': project_id, 'project_context': _assistant_project_context(project)}
def _assistant_search_snippet(text: str, query: str, width: int = 180) -> str:
    raw = str(text or '').replace('\r', ' ').replace('\n', ' ')
    clean = ' '.join(raw.split())
    if not clean:
        return ''
    query_clean = str(query or '').strip().lower()
    idx = clean.lower().find(query_clean)
    if idx < 0:
        return clean[:width]
    start = max(0, idx - width // 3)
    end = min(len(clean), idx + len(query_clean) + (width // 2))
    snippet = clean[start:end].strip()
    if start > 0:
        snippet = '…' + snippet
    if end < len(clean):
        snippet = snippet + '…'
    return snippet
def _assistant_search_match(text: str, query: str) -> bool:
    return str(query or '').lower() in str(text or '').lower()
def _assistant_memory_scope(profile: dict, session: dict) -> dict:
    messages = session.get('messages') if isinstance(session.get('messages'), list) else []
    latest_user = ''
    for item in reversed(messages):
        if isinstance(item, dict) and str(item.get('role') or '').strip().lower() == 'user':
            latest_user = str(item.get('content') or '').strip()
            if latest_user:
                break
    project_context = session.get('project_context') if isinstance(session.get('project_context'), dict) else {}
    return {
        'profile_id': 'default',
        'project_id': str(session.get('project_id') or '').strip(),
        'session_id': str(session.get('id') or '').strip(),
        'mode': str(session.get('mode') or '').strip(),
        'thread_instruction': str(session.get('thread_instruction') or '').strip(),
        'context_note': str(session.get('context_note') or '').strip(),
        'project_title': str(project_context.get('title') or '').strip(),
        'project_brief': str(project_context.get('brief') or '').strip(),
        'project_type': str(project_context.get('project_type') or 'general').strip(),
        'project_profile_label': str((project_context.get('project_profile') or {}).get('display_label') or (project_context.get('project_profile') or {}).get('label') or '').strip() if isinstance(project_context.get('project_profile'), dict) else '',
        'latest_user_message': latest_user,
    }
def _assistant_related_chunks(session_id: str, project_id: str, limit: int = 120) -> list[dict]:
    rows = fetch_memory_chunks(lane='assistant', limit=max(12, limit))
    out = []
    seen = set()
    for row in rows:
        chunk_id = str(row.get('chunk_id') or '').strip()
        if not chunk_id or chunk_id in seen:
            continue
        scope_type = str(row.get('scope_type') or '').strip()
        scope_id = str(row.get('scope_id') or '').strip()
        entity_id = str(row.get('entity_id') or '').strip()
        row_project_id = str(row.get('project_id') or '').strip()
        keep = scope_type == 'profile'
        if session_id and (entity_id == session_id or (scope_type == 'session' and scope_id == session_id)):
            keep = True
        if project_id and (row_project_id == project_id or (scope_type == 'project' and scope_id == project_id) or entity_id == project_id):
            keep = True
        if keep:
            out.append(row)
            seen.add(chunk_id)
        if len(out) >= max(8, limit):
            break
    return out
def _assistant_related_summaries(session_id: str, project_id: str) -> list[dict]:
    rows = fetch_summary_records(lane='assistant', limit=80)
    out = []
    seen = set()
    for row in rows:
        rid = str(row.get('summary_record_id') or '').strip()
        if not rid or rid in seen:
            continue
        scope_type = str(row.get('scope_type') or '').strip()
        scope_id = str(row.get('scope_id') or '').strip()
        if scope_type == 'profile' or (session_id and scope_type == 'session' and scope_id == session_id) or (project_id and scope_type == 'project' and scope_id == project_id):
            out.append(row)
            seen.add(rid)
        if len(out) >= 8:
            break
    return out
def _assistant_related_writes(session_id: str, project_id: str) -> list[dict]:
    rows = fetch_memory_write_logs(lane='assistant', limit=80)
    out = []
    for row in rows:
        entity_id = str(row.get('entity_id') or '').strip()
        if entity_id in {'default', session_id, project_id}:
            out.append(row)
        if len(out) >= 8:
            break
    return out
def _assistant_chunk_counts(session_id: str, project_id: str) -> dict:
    counts = {'profile': 0, 'project': 0, 'session': 0}
    with sqlite_conn() as conn:
        counts['profile'] = int((conn.execute("SELECT COUNT(*) FROM memory_chunks WHERE lane='assistant' AND is_deleted=0 AND scope_type='profile'").fetchone() or [0])[0] or 0)
        if project_id:
            counts['project'] = int((conn.execute("SELECT COUNT(*) FROM memory_chunks WHERE lane='assistant' AND is_deleted=0 AND (project_id=? OR (scope_type='project' AND scope_id=?))", (project_id, project_id)).fetchone() or [0])[0] or 0)
        if session_id:
            counts['session'] = int((conn.execute("SELECT COUNT(*) FROM memory_chunks WHERE lane='assistant' AND is_deleted=0 AND (entity_id=? OR (scope_type='session' AND scope_id=?))", (session_id, session_id)).fetchone() or [0])[0] or 0)
    return counts
def _assistant_memory_payload(session_id: str, preview_text: str = '') -> dict:
    session = load_session(session_id) if session_id else None
    if not session:
        raise ValueError('Assistant chat not found.')
    profile = load_profile()
    project_id = str(session.get('project_id') or '').strip()
    project = load_project(project_id) if project_id else None
    if project:
        session = {**session, 'project_context': {
            'title': project.get('title') or '',
            'description': project.get('description') or '',
            'brief': project.get('brief') or '',
            'project_type': project.get('project_type') or 'general',
            'custom_profile': project.get('custom_profile') if isinstance(project.get('custom_profile'), dict) else {},
            'project_profile': resolve_project_profile(project),
            'context_cards': project.get('context_cards') or [],
            'context_files': project.get('context_files') or [],
        }}
    scope = _assistant_memory_scope(profile, session)
    query_bits = [str(preview_text or '').strip(), scope.get('latest_user_message') or '', scope.get('thread_instruction') or '', scope.get('context_note') or '', scope.get('project_title') or '', scope.get('project_brief') or '']
    memory_pack = build_memory_pack('assistant', scope=scope, query_text='\n'.join(bit for bit in query_bits if bit))
    recent_chunks = _assistant_related_chunks(str(session.get('id') or '').strip(), project_id)
    summaries = _assistant_related_summaries(str(session.get('id') or '').strip(), project_id)
    writes = _assistant_related_writes(str(session.get('id') or '').strip(), project_id)
    return {
        'session_id': str(session.get('id') or '').strip(),
        'project_id': project_id,
        'backend': get_embedding_backend_status(),
        'counts': _assistant_chunk_counts(str(session.get('id') or '').strip(), project_id),
        'persona_preview': build_assistant_persona_preview(profile, session, memory_pack),
        'retrieval_preview': {
            'summary': str(memory_pack.get('summary') or '').strip(),
            'item_count': int(memory_pack.get('item_count') or 0),
            'candidate_count': int(memory_pack.get('candidate_count') or 0),
            'diagnostics': memory_pack.get('diagnostics') if isinstance(memory_pack.get('diagnostics'), dict) else {},
            'items': [{
                'id': str(item.get('id') or '').strip(),
                'document': str(item.get('document') or '').strip(),
                'score': float(item.get('score') or 0.0),
                'overlap': float(item.get('overlap') or 0.0),
                'source': str(item.get('source') or '').strip(),
                'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
                'diagnostics': item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {},
            } for item in (memory_pack.get('items') if isinstance(memory_pack.get('items'), list) else [])],
        },
        'recent_chunks': recent_chunks[:8],
        'summaries': summaries[:6],
        'recent_writes': writes[:6],
    }
def _assistant_scope_chunk_ids(scope_type: str, scope_id: str, chunk_type: str = '') -> list[str]:
    rows = fetch_memory_chunks(lane='assistant', include_deleted=False, limit=5000)
    ids: list[str] = []
    for row in rows:
        chunk_id = str(row.get('chunk_id') or '').strip()
        if not chunk_id:
            continue
        row_scope_type = str(row.get('scope_type') or '').strip()
        row_scope_id = str(row.get('scope_id') or '').strip()
        entity_id = str(row.get('entity_id') or '').strip()
        project_id = str(row.get('project_id') or '').strip()
        row_chunk_type = str(row.get('chunk_type') or '').strip()
        if chunk_type and row_chunk_type != chunk_type:
            continue
        if scope_type == 'profile' and (row_scope_type == 'profile' or entity_id == 'default'):
            ids.append(chunk_id)
        elif scope_type == 'project' and (project_id == scope_id or (row_scope_type == 'project' and row_scope_id == scope_id) or entity_id == scope_id):
            ids.append(chunk_id)
        elif scope_type == 'session' and (entity_id == scope_id or (row_scope_type == 'session' and row_scope_id == scope_id)):
            ids.append(chunk_id)
    return ids


def _memory_admin_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", str(text or '').lower()))


def _memory_conflict_pairs(lane: str = '', limit: int = 18) -> list[dict]:
    rows = fetch_memory_chunks(lane=lane, include_deleted=False, include_suppressed=False, limit=800)
    grouped: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in rows:
        key = (
            str(row.get('lane') or '').strip(),
            str(row.get('chunk_type') or '').strip(),
            str(row.get('scope_type') or '').strip(),
            str(row.get('scope_id') or row.get('project_id') or row.get('campaign_id') or '').strip(),
        )
        grouped.setdefault(key, []).append(row)
    neg_words = {'not', 'never', 'no', 'without', "can't", 'cant', "don't", 'dont', "doesn't", 'doesnt'}
    conflicts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for group_rows in grouped.values():
        if len(group_rows) < 2:
            continue
        for i in range(len(group_rows)):
            left = group_rows[i]
            left_id = str(left.get('chunk_id') or '').strip()
            left_doc = str(left.get('document') or '').strip()
            left_tokens = _memory_admin_tokens(left_doc)
            if len(left_tokens) < 3:
                continue
            for j in range(i + 1, len(group_rows)):
                right = group_rows[j]
                right_id = str(right.get('chunk_id') or '').strip()
                pair_key = tuple(sorted((left_id, right_id)))
                if not right_id or pair_key in seen:
                    continue
                seen.add(pair_key)
                right_doc = str(right.get('document') or '').strip()
                right_tokens = _memory_admin_tokens(right_doc)
                if len(right_tokens) < 3:
                    continue
                overlap = len(left_tokens & right_tokens)
                union = len(left_tokens | right_tokens) or 1
                jaccard = overlap / union
                if jaccard < 0.24:
                    continue
                left_neg = bool(left_tokens & neg_words)
                right_neg = bool(right_tokens & neg_words)
                exact_same = left_doc.lower() == right_doc.lower()
                if exact_same:
                    continue
                if not (left_neg != right_neg or jaccard >= 0.42):
                    continue
                newer = left if str(left.get('updated_at') or left.get('created_at') or '') >= str(right.get('updated_at') or right.get('created_at') or '') else right
                preferred = left if bool(left.get('is_pinned')) else right if bool(right.get('is_pinned')) else newer
                rejected = right if preferred is left else left
                conflicts.append({
                    'lane': str(left.get('lane') or '').strip(),
                    'chunk_type': str(left.get('chunk_type') or '').strip(),
                    'scope_type': str(left.get('scope_type') or '').strip(),
                    'scope_id': str(left.get('scope_id') or '').strip(),
                    'similarity': round(jaccard, 3),
                    'reason': 'negation_flip' if left_neg != right_neg else 'same_scope_overlap',
                    'preferred_chunk_id': str(preferred.get('chunk_id') or '').strip(),
                    'chunk_ids': [left_id, right_id],
                    'items': [left, right],
                    'suggested_keep': {'chunk_id': str(preferred.get('chunk_id') or '').strip(), 'updated_at': str(preferred.get('updated_at') or preferred.get('created_at') or '').strip(), 'is_pinned': bool(preferred.get('is_pinned'))},
                    'suggested_drop': {'chunk_id': str(rejected.get('chunk_id') or '').strip(), 'updated_at': str(rejected.get('updated_at') or rejected.get('created_at') or '').strip(), 'is_pinned': bool(rejected.get('is_pinned'))},
                })
    conflicts.sort(key=lambda item: (item.get('similarity') or 0.0, 1 if item.get('reason') == 'negation_flip' else 0), reverse=True)
    return conflicts[:max(1, int(limit or 18))]


def _memory_admin_payload(lane: str = '', q: str = '', chunk_type: str = '', include_suppressed: bool = False) -> dict:
    clean_lane = str(lane or '').strip().lower()
    clean_q = str(q or '').strip()
    clean_chunk_type = str(chunk_type or '').strip().lower()
    rows = fetch_memory_chunks(lane=clean_lane, chunk_type=clean_chunk_type, include_deleted=False, include_suppressed=include_suppressed, q=clean_q, limit=180)
    recent_writes = fetch_memory_write_logs(lane=clean_lane, limit=12)
    return {
        'backend': get_embedding_backend_status(),
        'overview': fetch_memory_admin_overview(),
        'filters': {'lane': clean_lane, 'q': clean_q, 'chunk_type': clean_chunk_type, 'include_suppressed': bool(include_suppressed)},
        'items': rows,
        'conflicts': _memory_conflict_pairs(clean_lane, limit=18),
        'recent_writes': recent_writes[:12],
    }
@router.get('/api/assistant/bootstrap')
async def api_assistant_bootstrap():
    return JSONResponse({
        'ok': True,
        'profile': load_profile(),
        'modes': list_modes(),
        'projects': list_projects(),
        'sessions': list_sessions(),
    })

@router.get('/api/assistant/memory-backends')
async def api_assistant_memory_backends():
    return JSONResponse({'ok': True, **get_embedding_backend_status()})


@router.post('/api/assistant/memory-backend-select')
async def api_assistant_memory_backend_select(payload: dict):
    backend_key = str((payload or {}).get('backend_key') or '').strip()
    if not backend_key:
        return json_error('Pick an embedding backend first.', 400)
    try:
        backend = set_active_embedding_backend(backend_key)
        reindex = bool((payload or {}).get('reindex', True))
        reindex_result = reindex_active_backend_from_sqlite() if reindex else {'ok': True, 'indexed': 0, 'per_lane': {}}
        message = f"Embedding backend switched to {backend.get('label') or backend_key}."
        return JSONResponse({'ok': True, **get_embedding_backend_status(), 'selected': backend, 'reindex_result': reindex_result, 'message': message})
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc) or 'Could not switch the embedding backend.', 500)




@router.get('/api/assistant/memory-model-runtime')
async def api_assistant_memory_model_runtime():
    return JSONResponse({'ok': True, 'embedding_status': get_embedding_backend_status(), 'reranker_status': get_reranker_status(), **get_assistant_model_status()})


@router.post('/api/assistant/memory-model-runtime')
async def api_assistant_memory_model_runtime_update(payload: dict):
    try:
        data = update_assistant_model_settings(
            embedding_model_path=(payload or {}).get('embedding_model_path', None),
            embedding_device=(payload or {}).get('embedding_device', None),
            reranker_backend=(payload or {}).get('reranker_backend', None),
            reranker_model_path=(payload or {}).get('reranker_model_path', None),
            reranker_device=(payload or {}).get('reranker_device', None),
        )
        # Refresh the backend list after path/dependency changes. Reindex only when requested.
        reindex = bool((payload or {}).get('reindex', False))
        reindex_result = reindex_active_backend_from_sqlite() if reindex else {'ok': True, 'indexed': 0, 'per_lane': {}}
        return JSONResponse({'ok': True, **data, 'embedding_status': get_embedding_backend_status(), 'reranker_status': get_reranker_status(), 'reindex_result': reindex_result, 'message': 'Assistant model runtime settings saved.'})
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc) or 'Could not save Assistant model runtime settings.', 500)

@router.get('/api/assistant/search')
async def api_assistant_search(q: str = ''):
    query = str(q or '').strip()
    if len(query) < 2:
        return json_error('Type at least 2 characters to search Assistant content.', 400)
    results = []
    query_lower = query.lower()
    for row in list_sessions():
        if not isinstance(row, dict):
            continue
        session_id = str(row.get('id') or '').strip()
        if not session_id:
            continue
        session = load_session(session_id)
        if not session:
            continue
        title = str(session.get('title') or 'Assistant chat').strip() or 'Assistant chat'
        project_id = str(session.get('project_id') or '').strip()
        if _assistant_search_match(title, query_lower) or _assistant_search_match(session.get('preview') or '', query_lower):
            results.append({
                'kind': 'session',
                'label': 'Chat',
                'title': title,
                'snippet': _assistant_search_snippet(session.get('preview') or title, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
        thread_instruction = str(session.get('thread_instruction') or '').strip()
        if thread_instruction and _assistant_search_match(thread_instruction, query_lower):
            results.append({
                'kind': 'thread_instruction',
                'label': 'Thread instruction',
                'title': title,
                'snippet': _assistant_search_snippet(thread_instruction, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
        context_note = str(session.get('context_note') or '').strip()
        if context_note and _assistant_search_match(context_note, query_lower):
            results.append({
                'kind': 'thread_note',
                'label': 'Thread note',
                'title': title,
                'snippet': _assistant_search_snippet(context_note, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
        memory_summary = str(session.get('memory_summary') or '').strip()
        if memory_summary and _assistant_search_match(memory_summary, query_lower):
            results.append({
                'kind': 'thread_memory',
                'label': 'Thread memory',
                'title': title,
                'snippet': _assistant_search_snippet(memory_summary, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
        message_hits = 0
        for msg in session.get('messages') if isinstance(session.get('messages'), list) else []:
            if message_hits >= 2:
                break
            if not isinstance(msg, dict):
                continue
            content = str(msg.get('content') or '').strip()
            if not content or not _assistant_search_match(content, query_lower):
                continue
            results.append({
                'kind': 'message',
                'label': str(msg.get('role') or 'message').strip().capitalize(),
                'title': title,
                'snippet': _assistant_search_snippet(content, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
            message_hits += 1
        item_hits = 0
        for item in session.get('context_items') if isinstance(session.get('context_items'), list) else []:
            if item_hits >= 2:
                break
            if not isinstance(item, dict):
                continue
            content = str(item.get('content') or '').strip()
            if not content or not _assistant_search_match(content, query_lower):
                continue
            results.append({
                'kind': 'thread_context',
                'label': 'Thread file',
                'title': f"{title} · {str(item.get('title') or 'Context item').strip() or 'Context item'}",
                'snippet': _assistant_search_snippet(content, query_lower),
                'session_id': session_id,
                'project_id': project_id,
            })
            item_hits += 1
    for project in list_projects():
        if not isinstance(project, dict):
            continue
        project_id = str(project.get('id') or '').strip()
        project_title = str(project.get('title') or 'Project').strip() or 'Project'
        description = str(project.get('description') or '').strip()
        brief = str(project.get('brief') or '').strip()
        if _assistant_search_match(project_title, query_lower) or _assistant_search_match(description, query_lower):
            results.append({
                'kind': 'project',
                'label': 'Project',
                'title': project_title,
                'snippet': _assistant_search_snippet(description or project_title, query_lower),
                'project_id': project_id,
            })
        if brief and _assistant_search_match(brief, query_lower):
            results.append({
                'kind': 'project_brief',
                'label': 'Project brief',
                'title': project_title,
                'snippet': _assistant_search_snippet(brief, query_lower),
                'project_id': project_id,
            })
        card_hits = 0
        for card in project.get('context_cards') if isinstance(project.get('context_cards'), list) else []:
            if card_hits >= 2:
                break
            if not isinstance(card, dict):
                continue
            card_text = f"{card.get('title') or ''} {card.get('content') or ''}"
            if not _assistant_search_match(card_text, query_lower):
                continue
            results.append({
                'kind': 'project_card',
                'label': 'Project card',
                'title': f"{project_title} · {str(card.get('title') or 'Context card').strip() or 'Context card'}",
                'snippet': _assistant_search_snippet(card.get('content') or '', query_lower),
                'project_id': project_id,
            })
            card_hits += 1
        file_hits = 0
        for item in project.get('context_files') if isinstance(project.get('context_files'), list) else []:
            if file_hits >= 2:
                break
            if not isinstance(item, dict):
                continue
            file_text = f"{item.get('title') or ''} {item.get('content') or ''}"
            if not _assistant_search_match(file_text, query_lower):
                continue
            results.append({
                'kind': 'project_file',
                'label': 'Project file',
                'title': f"{project_title} · {str(item.get('title') or 'Project file').strip() or 'Project file'}",
                'snippet': _assistant_search_snippet(item.get('content') or '', query_lower),
                'project_id': project_id,
            })
            file_hits += 1
        record_hits = 0
        for item in project.get('linked_records') if isinstance(project.get('linked_records'), list) else []:
            if record_hits >= 3:
                break
            if not isinstance(item, dict):
                continue
            record_text = f"{item.get('title') or ''} {item.get('note') or ''} {item.get('record_type') or ''}"
            if not _assistant_search_match(record_text, query_lower):
                continue
            results.append({
                'kind': 'project_record',
                'label': 'Linked record',
                'title': f"{project_title} · {str(item.get('title') or 'Linked record').strip() or 'Linked record'}",
                'snippet': _assistant_search_snippet(f"{item.get('record_type') or ''} {item.get('note') or ''}", query_lower),
                'project_id': project_id,
            })
            record_hits += 1
    return JSONResponse({'ok': True, 'query': query, 'results': results[:40]})
@router.post('/api/assistant/profile-save')
async def api_assistant_profile_save(payload: dict):
    profile = save_profile(payload or {})
    return JSONResponse({'ok': True, 'profile': profile, 'message': 'Assistant profile saved.'})

@router.post('/api/assistant/persona-preview')
async def api_assistant_persona_preview(payload: dict):
    profile = (payload or {}).get('profile') if isinstance((payload or {}).get('profile'), dict) else load_profile()
    session_id = str((payload or {}).get('session_id') or '').strip()
    session = load_session(session_id) if session_id else {}
    q = str((payload or {}).get('q') or '').strip()
    memory_pack = {}
    if session:
        scope = _assistant_memory_scope(profile, session)
        query_bits = [q, scope.get('latest_user_message') or '', scope.get('thread_instruction') or '', scope.get('context_note') or '', scope.get('project_title') or '', scope.get('project_brief') or '']
        memory_pack = build_memory_pack('assistant', scope=scope, query_text='\n'.join(bit for bit in query_bits if bit))
    return JSONResponse({'ok': True, 'persona': build_assistant_persona_preview(profile, session, memory_pack)})

@router.get('/api/assistant/project-profiles')
async def api_assistant_project_profiles():
    return JSONResponse({'ok': True, 'profiles': list_project_profiles()})

@router.post('/api/assistant/project-create')
async def api_assistant_project_create(payload: dict):
    project = create_project(payload or {})
    return JSONResponse({'ok': True, 'project': project, 'projects': list_projects(), 'message': 'Assistant project created.'})
@router.post('/api/assistant/project-rename')
async def api_assistant_project_rename(payload: dict):
    project_id = str((payload or {}).get('project_id') or '').strip()
    title = str((payload or {}).get('title') or '').strip()
    description = (payload or {}).get('description')
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not title:
        return json_error('Project title cannot be empty.', 400)
    project = rename_project(project_id, title, description if isinstance(description, str) else None)
    if not project:
        return json_error('Assistant project not found.', 404)
    return JSONResponse({'ok': True, 'project': project, 'projects': list_projects(), 'sessions': list_sessions(), 'message': 'Assistant project renamed.'})
@router.post('/api/assistant/project-save')
async def api_assistant_project_save(payload: dict):
    project_id = str((payload or {}).get('project_id') or '').strip()
    if not project_id:
        return json_error('No assistant project selected.', 400)
    project = update_project(project_id, {
        'description': str((payload or {}).get('description') or '').strip(),
        'brief': str((payload or {}).get('brief') or '').strip(),
        'project_type': str((payload or {}).get('project_type') or '').strip(),
        'custom_profile': (payload or {}).get('custom_profile') if isinstance((payload or {}).get('custom_profile'), dict) else None,
        'context_cards': (payload or {}).get('context_cards') if isinstance((payload or {}).get('context_cards'), list) else None,
        'context_files': (payload or {}).get('context_files') if isinstance((payload or {}).get('context_files'), list) else None,
        'linked_records': (payload or {}).get('linked_records') if isinstance((payload or {}).get('linked_records'), list) else None,
    })
    if not project:
        return json_error('Assistant project not found.', 404)
    return JSONResponse({'ok': True, 'project': project, 'projects': list_projects(), 'message': 'Assistant project context saved.'})
@router.post('/api/assistant/project-delete')
async def api_assistant_project_delete(payload: dict):
    project_id = str((payload or {}).get('project_id') or '').strip()
    if not project_id:
        return json_error('No assistant project selected.', 400)
    deleted = delete_project(project_id)
    if not deleted:
        return json_error('Could not delete the assistant project.', 500)
    return JSONResponse({'ok': True, 'projects': list_projects(), 'sessions': list_sessions(), 'message': 'Assistant project deleted.'})


@router.get('/api/assistant/project-entity-graph')
async def api_assistant_project_entity_graph(project_id: str, q: str = '', limit: int = 80):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse(project_entity_graph_summary(clean_project_id, q=str(q or '').strip(), limit=int(limit or 80)))
    except Exception:
        return json_error('Could not load the project entity graph.', 500)

@router.get('/api/assistant/project-entities')
async def api_assistant_project_entities(project_id: str, kind: str = '', q: str = '', limit: int = 80):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse({'ok': True, 'project_id': clean_project_id, 'entities': fetch_project_entities(clean_project_id, kind=str(kind or '').strip(), q=str(q or '').strip(), limit=int(limit or 80))})
    except Exception:
        return json_error('Could not load project entities.', 500)

@router.get('/api/assistant/project-entity-relationships')
async def api_assistant_project_entity_relationships(project_id: str, entity_uid: str = '', limit: int = 120):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse({'ok': True, 'project_id': clean_project_id, 'relationships': fetch_project_relationships(clean_project_id, entity_uid=str(entity_uid or '').strip(), limit=int(limit or 120))})
    except Exception:
        return json_error('Could not load project entity relationships.', 500)



@router.post('/api/assistant/project-canon-change/analyze')
async def api_assistant_project_canon_change_analyze(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    if not project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse(analyze_canon_change(
            project_id=project_id,
            action=str((payload or {}).get('action') or 'upsert_entity'),
            entity_uid=str((payload or {}).get('entity_uid') or ''),
            entity_id=str((payload or {}).get('entity_id') or ''),
            kind=str((payload or {}).get('kind') or 'record'),
            label=str((payload or {}).get('label') or ''),
            summary=str((payload or {}).get('summary') or ''),
            canon_status=str((payload or {}).get('canon_status') or 'draft'),
            visibility=str((payload or {}).get('visibility') or 'project_private'),
        ))
    except Exception:
        return json_error('Could not analyze canon change.', 500)


@router.post('/api/assistant/project-canon-change/propose')
async def api_assistant_project_canon_change_propose(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    if not project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse(create_canon_change_proposal(
            project_id=project_id,
            action=str((payload or {}).get('action') or 'upsert_entity'),
            entity_uid=str((payload or {}).get('entity_uid') or ''),
            entity_id=str((payload or {}).get('entity_id') or ''),
            kind=str((payload or {}).get('kind') or 'record'),
            label=str((payload or {}).get('label') or ''),
            summary=str((payload or {}).get('summary') or ''),
            canon_status=str((payload or {}).get('canon_status') or 'draft'),
            visibility=str((payload or {}).get('visibility') or 'project_private'),
            reason=str((payload or {}).get('reason') or ''),
            payload=(payload or {}),
        ))
    except Exception:
        return json_error('Could not create canon proposal.', 500)


@router.get('/api/assistant/project-canon-change/proposals')
async def api_assistant_project_canon_change_proposals(project_id: str, status: str = '', limit: int = 50):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse({'ok': True, 'project_id': clean_project_id, 'proposals': list_canon_change_proposals(clean_project_id, status=str(status or '').strip(), limit=int(limit or 50))})
    except Exception:
        return json_error('Could not load canon proposals.', 500)


@router.post('/api/assistant/project-canon-change/apply')
async def api_assistant_project_canon_change_apply(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    proposal_id = str((payload or {}).get('proposal_id') or '').strip()
    if not project_id or not proposal_id:
        return json_error('Project and proposal are required.', 400)
    try:
        result = apply_canon_change_proposal(project_id=project_id, proposal_id=proposal_id, confirm=bool((payload or {}).get('confirm')))
        status = 200 if result.get('ok') else 400
        return JSONResponse(result, status_code=status)
    except Exception:
        return json_error('Could not apply canon proposal.', 500)


@router.get('/api/assistant/project-canon-change/history')
async def api_assistant_project_canon_change_history(project_id: str, entity_uid: str = '', limit: int = 50):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    try:
        return JSONResponse({'ok': True, 'project_id': clean_project_id, 'history': list_entity_change_history(clean_project_id, entity_uid=str(entity_uid or '').strip(), limit=int(limit or 50))})
    except Exception:
        return json_error('Could not load canon change history.', 500)





@router.post('/api/assistant/project-knowledge-record-preview')
async def api_assistant_project_knowledge_record_preview(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    text = str((payload or {}).get('text') or '').strip()
    title = str((payload or {}).get('title') or 'Pasted raw text').strip() or 'Pasted raw text'
    canon_status = str((payload or {}).get('canon_status') or 'draft').strip() or 'draft'
    visibility = str((payload or {}).get('visibility') or 'project_private').strip() or 'project_private'
    requested_import_type = str((payload or {}).get('import_type') or '').strip()
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not text:
        return json_error('Paste raw text before previewing record conversion.', 400)
    if len(text) > MAX_MANUAL_CAPTURE_CHARS:
        return json_error('That raw text block is too large. Keep preview imports under 120k characters.', 400)
    try:
        preview = preview_raw_text_record_conversion(
            project_id=project_id,
            filename=f'{title}.txt' if not Path(title).suffix else title,
            text=text,
            canon_status=canon_status,
            visibility=visibility,
            requested_import_type=requested_import_type,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Raw text record preview failed. Check the server logs for details.', 500)
    return JSONResponse({'ok': True, 'preview': preview, 'message': f'Preview created: {preview.get("record_count") or 0} record(s), {preview.get("section_count") or 0} section(s).'})


@router.post('/api/assistant/project-knowledge-record-convert')
async def api_assistant_project_knowledge_record_convert(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    text = str((payload or {}).get('text') or '').strip()
    title = str((payload or {}).get('title') or 'Converted raw text').strip() or 'Converted raw text'
    canon_status = str((payload or {}).get('canon_status') or 'draft').strip() or 'draft'
    visibility = str((payload or {}).get('visibility') or 'project_private').strip() or 'project_private'
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not text:
        return json_error('Paste raw text before converting to records.', 400)
    if len(text) > MAX_MANUAL_CAPTURE_CHARS:
        return json_error('That raw text block is too large. Keep conversion imports under 120k characters.', 400)
    filename = f'{title}.txt' if not Path(title).suffix else title
    try:
        report = ingest_knowledge_document(
            project_id=project_id,
            filename=filename,
            raw=text.encode('utf-8'),
            canon_status=canon_status,
            visibility=visibility,
            import_mode='record_conversion',
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Raw text record conversion failed. Check the server logs for details.', 500)
    return JSONResponse({
        'ok': True,
        'report': report,
        'project': report.get('project'),
        'projects': list_projects(),
        'message': f'Converted raw text into {report.get("structured_record_count") or 0} record(s) and {report.get("chunk_count") or 0} memory chunk(s).',
    })

@router.post('/api/assistant/project-knowledge-import-text')
async def api_assistant_project_knowledge_import_text(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    text = str((payload or {}).get('text') or '').strip()
    title = str((payload or {}).get('title') or 'Pasted knowledge').strip() or 'Pasted knowledge'
    canon_status = str((payload or {}).get('canon_status') or 'draft').strip() or 'draft'
    visibility = str((payload or {}).get('visibility') or 'project_private').strip() or 'project_private'
    capture_type = str((payload or {}).get('capture_type') or 'pasted_knowledge').strip() or 'pasted_knowledge'
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not text:
        return json_error('Paste some knowledge text first.', 400)
    if len(text) > MAX_MANUAL_CAPTURE_CHARS:
        return json_error('That pasted knowledge block is too large. Keep pasted imports under 120k characters.', 400)
    try:
        report = capture_manual_memory(
            project_id=project_id,
            session_id=str((payload or {}).get('session_id') or '').strip(),
            title=title,
            text=text,
            capture_type=capture_type,
            canon_status=canon_status,
            visibility=visibility,
            source='paste',
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Pasted knowledge import failed. Check the server logs for details.', 500)
    return JSONResponse({'ok': True, 'report': report, 'project': report.get('project'), 'projects': list_projects(), 'message': f'Imported pasted knowledge as {report.get("chunk_count") or 0} chunk(s).'})


@router.post('/api/assistant/manual-memory-capture')
async def api_assistant_manual_memory_capture(payload: dict = Body(...)):
    text = str((payload or {}).get('text') or '').strip()
    if not text:
        return json_error('No text was provided to save.', 400)
    try:
        result = capture_manual_memory(
            project_id=str((payload or {}).get('project_id') or '').strip(),
            session_id=str((payload or {}).get('session_id') or '').strip(),
            title=str((payload or {}).get('title') or '').strip(),
            text=text,
            capture_type=str((payload or {}).get('capture_type') or 'memory').strip(),
            canon_status=str((payload or {}).get('canon_status') or 'draft').strip(),
            visibility=str((payload or {}).get('visibility') or 'project_private').strip(),
            source=str((payload or {}).get('source') or 'chat').strip(),
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Could not save that text to memory.', 500)
    return JSONResponse({'ok': True, 'result': result, 'project': result.get('project'), 'projects': list_projects(), 'message': f'Saved {result.get("chunk_count") or 0} memory chunk(s).'})

@router.get('/api/assistant/project-knowledge-imports')
async def api_assistant_project_knowledge_imports(project_id: str):
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return json_error('No assistant project selected.', 400)
    return JSONResponse({'ok': True, 'project_id': clean_project_id, 'imports': list_project_import_reports(clean_project_id)})



@router.post('/api/assistant/project-knowledge-retrieval-tests/generate')
async def api_assistant_project_knowledge_retrieval_tests_generate(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    import_id = str((payload or {}).get('import_id') or '').strip()
    limit = int((payload or {}).get('limit') or 14)
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not import_id:
        return json_error('Select an import before generating retrieval test questions.', 400)
    try:
        tests = generate_retrieval_test_questions(project_id=project_id, import_id=import_id, limit=limit)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Could not generate retrieval test questions.', 500)
    return JSONResponse({'ok': True, 'tests': tests, 'message': f'Generated {tests.get("question_count") or 0} retrieval test question(s).'})


@router.post('/api/assistant/project-knowledge-retrieval-tests/run')
async def api_assistant_project_knowledge_retrieval_tests_run(payload: dict = Body(...)):
    project_id = str((payload or {}).get('project_id') or '').strip()
    import_id = str((payload or {}).get('import_id') or '').strip()
    questions = (payload or {}).get('questions') if isinstance((payload or {}).get('questions'), list) else None
    limit = int((payload or {}).get('limit') or 10)
    if not project_id:
        return json_error('No assistant project selected.', 400)
    if not import_id:
        return json_error('Select an import before running retrieval tests.', 400)
    try:
        result = run_retrieval_tests(project_id=project_id, import_id=import_id, questions=questions, limit=limit)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Could not run retrieval tests.', 500)
    return JSONResponse({'ok': True, 'result': result, 'message': f'Retrieval tests complete: {result.get("pass_count") or 0} pass, {result.get("weak_count") or 0} weak, {result.get("fail_count") or 0} fail.'})

@router.post('/api/assistant/project-knowledge-import')
async def api_assistant_project_knowledge_import(
    project_id: str = Form(...),
    canon_status: str = Form('draft'),
    visibility: str = Form('project_private'),
    import_mode: str = Form('memory'),
    file: UploadFile = File(...),
):
    filename = str(file.filename or 'knowledge.txt').strip() or 'knowledge.txt'
    payload = await file.read()
    if len(payload or b'') > MAX_KNOWLEDGE_UPLOAD_BYTES:
        return json_error('That knowledge file is too large. Keep imports under 3 MB for now.', 400)
    try:
        report = ingest_knowledge_document(
            project_id=project_id,
            filename=filename,
            raw=payload or b'',
            canon_status=canon_status,
            visibility=visibility,
            import_mode=import_mode,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error('Knowledge import failed. Check the server logs for details.', 500)
    return JSONResponse({'ok': True, 'report': report, 'project': report.get('project'), 'projects': list_projects(), 'message': f'Imported {report.get("chunk_count") or 0} knowledge chunk(s).'})
@router.post('/api/assistant/context-upload')
async def api_assistant_context_upload(file: UploadFile = File(...)):
    filename = str(file.filename or 'context.txt').strip() or 'context.txt'
    suffix = Path(filename).suffix.lower()
    allowed = {'.txt', '.md', '.markdown', '.json', '.csv', '.log', '.py', '.js', '.ts', '.html', '.css', '.xml', '.yaml', '.yml'}
    if suffix not in allowed:
        return json_error('That file type is not supported for Assistant context yet. Use a text-based file for now.', 400)
    payload = await file.read()
    if not payload:
        return json_error('That upload was empty.', 400)
    if len(payload) > MAX_CONTEXT_UPLOAD_BYTES:
        return json_error('That file is too large. Keep Assistant context uploads under 1 MB.', 400)
    try:
        content = payload.decode('utf-8')
    except UnicodeDecodeError:
        content = payload.decode('utf-8', errors='ignore') or payload.decode('latin-1', errors='ignore')
    content = content.strip()
    if not content:
        return json_error('That file did not contain readable text.', 400)
    title = Path(filename).stem[:160] or 'Context item'
    source_kind = suffix.lstrip('.') or 'text'
    return JSONResponse({
        'ok': True,
        'item': {
            'title': title,
            'source_kind': source_kind,
            'content': content[:18000],
            'char_count': len(content[:18000]),
        },
        'message': f'Loaded context from {filename}.',
    })
@router.post('/api/assistant/session-create')
async def api_assistant_session_create(payload: dict):
    session = create_session(payload or {})
    return JSONResponse({'ok': True, 'session': session, 'sessions': list_sessions(), 'message': 'Assistant chat created.'})
@router.get('/api/assistant/session-load')
async def api_assistant_session_load(session_id: str):
    session = load_session(session_id)
    if not session:
        return json_error('Assistant chat not found.', 404)
    return JSONResponse({'ok': True, 'session': session})
@router.post('/api/assistant/session-save')
async def api_assistant_session_save(payload: dict):
    session = save_session(payload or {})
    return JSONResponse({'ok': True, 'session': session, 'sessions': list_sessions(), 'message': 'Assistant chat saved.'})
@router.post('/api/assistant/session-delete')
async def api_assistant_session_delete(payload: dict):
    session_id = str((payload or {}).get('session_id') or '').strip()
    if not session_id:
        return json_error('No assistant chat selected.', 400)
    deleted = delete_session(session_id)
    if not deleted:
        return json_error('Could not delete the assistant chat.', 500)
    return JSONResponse({'ok': True, 'sessions': list_sessions(), 'message': 'Assistant chat deleted.'})
@router.post('/api/assistant/session-rename')
async def api_assistant_session_rename(payload: dict):
    session_id = str((payload or {}).get('session_id') or '').strip()
    title = str((payload or {}).get('title') or '').strip()
    if not session_id:
        return json_error('No assistant chat selected.', 400)
    if not title:
        return json_error('Title cannot be empty.', 400)
    session = rename_session(session_id, title)
    if not session:
        return json_error('Assistant chat not found.', 404)
    return JSONResponse({'ok': True, 'session': session, 'sessions': list_sessions(), 'message': 'Assistant chat renamed.'})
@router.post('/api/assistant/message-transform')
async def api_assistant_message_transform(payload: dict):
    model = str((payload or {}).get('model') or 'default').strip() or 'default'
    transform = str((payload or {}).get('transform') or '').strip().lower()
    source_text = str((payload or {}).get('source_text') or '').strip()
    profile = (payload or {}).get('profile') if isinstance((payload or {}).get('profile'), dict) else load_profile()
    session = (payload or {}).get('session') if isinstance((payload or {}).get('session'), dict) else {}
    if not source_text:
        return json_error('No source text supplied for transform.', 400)
    session = _hydrate_assistant_session_project(payload or {}, session)
    result = await transform_assistant_text(model=model, profile=profile, session=session, source_text=source_text, transform=transform)
    if not result.get('ok'):
        return json_error(result.get('message') or 'Transform failed.', 400)
    return JSONResponse({'ok': True, **result, 'message': 'Transform ready.'})
@router.post('/api/assistant/chat-stream')
async def api_assistant_chat_stream(payload: dict):
    model = str((payload or {}).get('model') or 'default').strip() or 'default'
    profile = (payload or {}).get('profile') if isinstance((payload or {}).get('profile'), dict) else load_profile()
    session = (payload or {}).get('session') if isinstance((payload or {}).get('session'), dict) else {}
    messages = (payload or {}).get('messages') if isinstance((payload or {}).get('messages'), list) else []
    session = _hydrate_assistant_session_project(payload or {}, session)
    params = session.get('params') if isinstance(session.get('params'), dict) else {}
    max_tokens = int(float((payload or {}).get('max_tokens') or params.get('max_tokens') or 640))
    temperature = float((payload or {}).get('temperature') if (payload or {}).get('temperature') is not None else params.get('temperature') or 0.7)
    top_p = float((payload or {}).get('top_p') if (payload or {}).get('top_p') is not None else params.get('top_p') or 0.92)
    top_k = int(float((payload or {}).get('top_k') or params.get('top_k') or 60))
    async def event_stream():
        async for event in stream_assistant_reply(
            model=model,
            profile=profile,
            session=session,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        ):
            event_type = str(event.get('type') or 'message')
            payload_json = json.dumps(event, ensure_ascii=False)
            yield f'event: {event_type}\ndata: {payload_json}\n\n'
    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@router.get('/api/assistant/context-pack-preview')
async def api_assistant_context_pack_preview(session_id: str = '', q: str = ''):
    try:
        session = load_session(session_id) if session_id else None
        if not session:
            return json_error('Assistant chat not found.', 404)
        session = _hydrate_assistant_session_project({'project_id': session.get('project_id')}, session)
        profile = load_profile()
        pack = build_assistant_context_pack(profile, session, session.get('messages') or [], preview_text=q or '')
        return JSONResponse({'ok': True, 'context_pack': pack})
    except Exception as exc:
        return json_error(str(exc) or 'Could not build Assistant context pack.', 500)


@router.get('/api/assistant/repo-index')
async def api_assistant_repo_index(q: str = '', limit: int = 8):
    try:
        if str(q or '').strip():
            payload = search_repo_index(str(q or '').strip(), limit=max(1, min(int(limit or 8), 30)))
        else:
            index = load_repo_index(rebuild_if_missing=True)
            payload = {
                'version': str(index.get('version') or ''),
                'file_count': int(index.get('file_count') or 0),
                'kind_counts': index.get('kind_counts') if isinstance(index.get('kind_counts'), dict) else {},
                'indexed_at': str(index.get('indexed_at') or ''),
                'results': [],
                'result_count': 0,
            }
        return JSONResponse({'ok': True, 'repo_index': payload})
    except Exception as exc:
        return json_error(str(exc) or 'Could not load Assistant repo index.', 500)


@router.post('/api/assistant/repo-index-rebuild')
async def api_assistant_repo_index_rebuild(payload: dict):
    try:
        max_files = max(100, min(int((payload or {}).get('max_files') or 1200), 5000))
        index = build_repo_index(max_files=max_files)
        return JSONResponse({'ok': True, 'repo_index': {
            'version': str(index.get('version') or ''),
            'file_count': int(index.get('file_count') or 0),
            'kind_counts': index.get('kind_counts') if isinstance(index.get('kind_counts'), dict) else {},
            'indexed_at': str(index.get('indexed_at') or ''),
            'skipped_after_limit': int(index.get('skipped_after_limit') or 0),
        }})
    except Exception as exc:
        return json_error(str(exc) or 'Could not rebuild Assistant repo index.', 500)


@router.get('/api/assistant/tool-catalog')
async def api_assistant_tool_catalog(category: str = ''):
    try:
        if str(category or '').strip():
            tools = list_assistant_tools(category=category)
            categories = sorted({str(tool.get('category') or '') for tool in tools if str(tool.get('category') or '')})
            payload = {'version': 'assistant_tool_registry_v1', 'count': len(tools), 'categories': categories, 'tools': tools}
        else:
            payload = get_assistant_tool_catalog()
        return JSONResponse({'ok': True, 'catalog': payload})
    except Exception as exc:
        return json_error(str(exc) or 'Could not load Assistant tool catalog.', 500)


@router.post('/api/assistant/tool-preview')
async def api_assistant_tool_preview(payload: dict):
    try:
        tool_id = str((payload or {}).get('tool_id') or '').strip()
        args = (payload or {}).get('arguments') if isinstance((payload or {}).get('arguments'), dict) else {}
        return JSONResponse({'ok': True, 'preview': preview_assistant_tool_call(tool_id, args)})
    except Exception as exc:
        return json_error(str(exc) or 'Could not preview Assistant tool call.', 400)


@router.post('/api/assistant/tool-execute')
async def api_assistant_tool_execute(payload: dict):
    try:
        tool_id = str((payload or {}).get('tool_id') or '').strip()
        args = (payload or {}).get('arguments') if isinstance((payload or {}).get('arguments'), dict) else {}
        result = execute_assistant_tool(
            tool_id,
            args,
            confirmed=bool((payload or {}).get('confirmed')),
            context={
                'session_id': str((payload or {}).get('session_id') or '').strip(),
                'project_id': str((payload or {}).get('project_id') or '').strip(),
            },
        )
        return JSONResponse({'ok': True, 'execution': result})
    except PermissionError as exc:
        return json_error(str(exc) or 'Confirmation required.', 403)
    except Exception as exc:
        return json_error(str(exc) or 'Could not execute Assistant tool.', 400)


@router.get('/api/assistant/local-actions/catalog')
async def api_assistant_local_actions_catalog():
    try:
        return JSONResponse({'ok': True, 'catalog': list_local_action_catalog()})
    except Exception as exc:
        return json_error(str(exc) or 'Could not load local PC action catalog.', 500)


@router.post('/api/assistant/local-actions/preview')
async def api_assistant_local_action_preview(payload: dict):
    try:
        action_type = str((payload or {}).get('action_type') or '').strip()
        args = (payload or {}).get('arguments') if isinstance((payload or {}).get('arguments'), dict) else {}
        return JSONResponse({'ok': True, 'preview': preview_local_action(action_type, args)})
    except Exception as exc:
        return json_error(str(exc) or 'Could not preview local PC action.', 400)


@router.post('/api/assistant/local-actions/execute')
async def api_assistant_local_action_execute(payload: dict):
    try:
        action_type = str((payload or {}).get('action_type') or '').strip()
        args = (payload or {}).get('arguments') if isinstance((payload or {}).get('arguments'), dict) else {}
        result = execute_local_action(
            action_type,
            args,
            confirmed=bool((payload or {}).get('confirmed')),
            session_id=str((payload or {}).get('session_id') or '').strip(),
            project_id=str((payload or {}).get('project_id') or '').strip(),
        )
        return JSONResponse({'ok': True, 'execution': result})
    except PermissionError as exc:
        return json_error(str(exc) or 'Confirmation required for local PC action.', 403)
    except Exception as exc:
        return json_error(str(exc) or 'Could not execute local PC action.', 400)


@router.post('/api/assistant/patch-plan-validate')
async def api_assistant_patch_plan_validate(payload: dict):
    try:
        plan = (payload or {}).get('plan') if isinstance((payload or {}).get('plan'), dict) else payload
        return JSONResponse({'ok': True, 'validation': validate_patch_plan(plan if isinstance(plan, dict) else {})})
    except Exception as exc:
        return json_error(str(exc) or 'Could not validate patch plan.', 400)


@router.post('/api/assistant/patch-plan-preview')
async def api_assistant_patch_plan_preview(payload: dict):
    try:
        plan = (payload or {}).get('plan') if isinstance((payload or {}).get('plan'), dict) else payload
        return JSONResponse({'ok': True, 'preview': preview_patch_plan(plan if isinstance(plan, dict) else {})})
    except Exception as exc:
        return json_error(str(exc) or 'Could not preview patch plan.', 400)


@router.post('/api/assistant/patch-plan-apply')
async def api_assistant_patch_plan_apply(payload: dict):
    try:
        plan = (payload or {}).get('plan') if isinstance((payload or {}).get('plan'), dict) else payload
        result = apply_patch_plan(
            plan if isinstance(plan, dict) else {},
            confirmed=bool((payload or {}).get('confirmed')),
            allow_delete=bool((payload or {}).get('allow_delete')),
        )
        return JSONResponse({'ok': True, 'apply': result})
    except PermissionError as exc:
        return json_error(str(exc) or 'Confirmation required.', 403)
    except Exception as exc:
        return json_error(str(exc) or 'Could not apply patch plan.', 400)


@router.get('/api/assistant/action-memory-recent')
async def api_assistant_action_memory_recent(session_id: str = '', project_id: str = '', limit: int = 24):
    try:
        return JSONResponse(recent_action_memory(session_id=session_id, project_id=project_id, limit=max(1, min(int(limit or 24), 100))))
    except Exception as exc:
        return json_error(str(exc) or 'Could not load Assistant action memory.', 500)


@router.post('/api/assistant/task-memory-write')
async def api_assistant_task_memory_write(payload: dict):
    try:
        result = record_manual_task_memory(
            summary=str((payload or {}).get('summary') or '').strip(),
            outcome=str((payload or {}).get('outcome') or '').strip(),
            session_id=str((payload or {}).get('session_id') or '').strip(),
            project_id=str((payload or {}).get('project_id') or '').strip(),
            details=(payload or {}).get('details') if isinstance((payload or {}).get('details'), dict) else {},
            memory_type=str((payload or {}).get('memory_type') or 'task_memory').strip() or 'task_memory',
        )
        return JSONResponse({'ok': True, 'task_memory': result})
    except Exception as exc:
        return json_error(str(exc) or 'Could not write Assistant task memory.', 400)

@router.get('/api/assistant/memory-inspect')
async def api_assistant_memory_inspect(session_id: str = '', q: str = ''):
    clean_session_id = str(session_id or '').strip()
    if not clean_session_id:
        return json_error('No assistant chat selected.', 400)
    try:
        payload = _assistant_memory_payload(clean_session_id, preview_text=q)
        return JSONResponse({'ok': True, **payload})
    except ValueError as exc:
        return json_error(str(exc), 404)
    except Exception as exc:
        return json_error(str(exc) or 'Could not inspect Assistant memory.', 500)
@router.post('/api/assistant/memory-repair')
async def api_assistant_memory_repair(payload: dict):
    session_id = str((payload or {}).get('session_id') or '').strip()
    if not session_id:
        return json_error('No assistant chat selected.', 400)
    session = load_session(session_id)
    if not session:
        return json_error('Assistant chat not found.', 404)
    profile = load_profile()
    project_id = str(session.get('project_id') or '').strip()
    project = load_project(project_id) if project_id else None
    sync_assistant_profile(profile, source_json_path='')
    if project:
        sync_assistant_project(project, source_json_path='')
    sync_assistant_session(session, source_json_path='')
    result = _assistant_memory_payload(session_id, preview_text=str((payload or {}).get('q') or '').strip())
    return JSONResponse({'ok': True, **result, 'message': 'Assistant adaptive memory rebuilt for the active thread.'})
@router.post('/api/assistant/memory-reset')
async def api_assistant_memory_reset(payload: dict):
    scope_type = str((payload or {}).get('scope_type') or '').strip().lower()
    session_id = str((payload or {}).get('session_id') or '').strip()
    project_id = str((payload or {}).get('project_id') or '').strip()
    chunk_type = str((payload or {}).get('chunk_type') or '').strip().lower()
    if chunk_type in {'all', 'any'}:
        chunk_type = ''
    if scope_type not in {'profile', 'project', 'session'}:
        return json_error('Pick a valid Assistant memory scope to reset.', 400)
    scope_id = 'default' if scope_type == 'profile' else project_id if scope_type == 'project' else session_id
    if not scope_id:
        return json_error('That Assistant memory scope is missing its ID.', 400)
    chunk_ids = _assistant_scope_chunk_ids(scope_type, scope_id, chunk_type=chunk_type)
    sqlite_deleted = mark_memory_chunk_ids_deleted(chunk_ids)
    delete_memory_chunk_ids(ASSISTANT_COLLECTION, chunk_ids)
    summary_deleted = 0
    if not chunk_type or chunk_type == 'summary':
        summary_rows = [row for row in fetch_summary_records(lane='assistant', limit=500) if (str(row.get('scope_type') or '').strip() == scope_type and str(row.get('scope_id') or '').strip() == scope_id)]
        summary_deleted = delete_summary_record_ids([str(row.get('summary_record_id') or '').strip() for row in summary_rows])
        if scope_type == 'session':
            session = load_session(scope_id)
            if session:
                session['memory_summary'] = ''
                session['memory_updated_at'] = ''
                save_session(session)
                execute('DELETE FROM assistant_summaries WHERE session_id=?', (scope_id,))
        elif scope_type == 'project':
            execute('DELETE FROM assistant_summaries WHERE project_id=?', (scope_id,))
    record_memory_write(
        write_log_id=f'awl_reset_{scope_type}_{scope_id}_{chunk_type or "all"}',
        lane='assistant',
        entity_type=scope_type,
        entity_id=scope_id,
        operation='reset',
        details={'chunk_type': chunk_type or 'all', 'sqlite_chunks_deleted': sqlite_deleted, 'summary_records_deleted': summary_deleted},
    )
    inspect_session_id = session_id or next((str(row.get('session_id') or '').strip() for row in list_sessions() if str(row.get('project_id') or '').strip() == project_id), '')
    scope_label = f"{scope_type} {chunk_type.replace('_', ' ')}" if chunk_type else scope_type
    response = {'ok': True, 'message': f'Assistant {scope_label} memory reset.'}
    if inspect_session_id:
        try:
            response.update(_assistant_memory_payload(inspect_session_id))
        except Exception:
            pass
    return JSONResponse(response)




@router.get('/api/assistant/memory-index-state')
async def api_assistant_memory_index_state():
    try:
        return JSONResponse(memory_index_state())
    except Exception as exc:
        return json_error(str(exc) or 'Could not read memory index state.', 500)


@router.post('/api/assistant/memory-index-refresh')
async def api_assistant_memory_index_refresh(payload: dict = Body({})):
    try:
        result = refresh_memory_indexes(
            lane=str((payload or {}).get('lane') or 'assistant').strip() or 'assistant',
            project_id=str((payload or {}).get('project_id') or '').strip(),
            session_id=str((payload or {}).get('session_id') or '').strip(),
            force=bool((payload or {}).get('force')),
        )
        return JSONResponse(result)
    except Exception as exc:
        return json_error(str(exc) or 'Could not refresh memory index.', 500)


@router.get('/api/assistant/memory-admin')
async def api_assistant_memory_admin(lane: str = '', q: str = '', chunk_type: str = '', include_suppressed: bool = False):
    try:
        payload = _memory_admin_payload(lane=lane, q=q, chunk_type=chunk_type, include_suppressed=include_suppressed)
        return JSONResponse({'ok': True, **payload})
    except Exception as exc:
        return json_error(str(exc) or 'Could not load memory admin tools.', 500)


@router.post('/api/assistant/memory-item-state')
async def api_assistant_memory_item_state(payload: dict):
    chunk_id = str((payload or {}).get('chunk_id') or '').strip()
    if not chunk_id:
        return json_error('Pick a memory item first.', 400)
    row = fetch_memory_chunk_by_id(chunk_id)
    if not row:
        return json_error('Memory item not found.', 404)
    pin_requested = (payload or {}).get('is_pinned')
    suppress_requested = (payload or {}).get('is_suppressed')
    pin_note = (payload or {}).get('pin_note')
    suppressed_reason = (payload or {}).get('suppressed_reason')
    ok = update_memory_chunk_state(
        chunk_id=chunk_id,
        is_pinned=bool(pin_requested) if pin_requested is not None else None,
        pin_note=str(pin_note or '').strip() if pin_note is not None else None,
        is_suppressed=bool(suppress_requested) if suppress_requested is not None else None,
        suppressed_reason=str(suppressed_reason or '').strip() if suppressed_reason is not None else None,
    )
    if not ok:
        return json_error('Could not update that memory item.', 500)
    updated = fetch_memory_chunk_by_id(chunk_id) or row
    lane_key = str(updated.get('lane') or '').strip().lower()
    collection_name = ASSISTANT_COLLECTION if lane_key == 'assistant' else ROLEPLAY_COLLECTION
    if bool(updated.get('is_suppressed')):
        delete_memory_chunk_ids(collection_name, [chunk_id])
        refresh_after_memory_write(lane=lane_key or 'assistant', project_id=str(updated.get('project_id') or '').strip(), reason='memory_item_suppressed', chunk_ids=[chunk_id], auto_refresh=False)
    elif bool(payload.get('reindex', True)):
        refresh_after_memory_write(lane=lane_key or 'assistant', project_id=str(updated.get('project_id') or '').strip(), reason='memory_item_state_update', chunk_ids=[chunk_id], auto_refresh=True)
    record_memory_write(
        write_log_id=f'awl_item_state_{chunk_id}',
        lane=lane_key,
        entity_type=str(updated.get('entity_type') or '').strip(),
        entity_id=str(updated.get('entity_id') or '').strip(),
        operation='pin_state_update',
        source_ref=str(updated.get('source_ref') or '').strip(),
        details={'chunk_id': chunk_id, 'is_pinned': bool(updated.get('is_pinned')), 'pin_note': str(updated.get('pin_note') or '').strip(), 'is_suppressed': bool(updated.get('is_suppressed')), 'suppressed_reason': str(updated.get('suppressed_reason') or '').strip()},
    )
    return JSONResponse({'ok': True, 'item': updated, 'message': 'Memory item updated.', **_memory_admin_payload(lane=lane_key)})




@router.post('/api/assistant/memory-sandbox-update')
async def api_assistant_memory_sandbox_update(payload: dict = Body(...)):
    chunk_ids = [str(item or '').strip() for item in ((payload or {}).get('chunk_ids') or []) if str(item or '').strip()]
    if not chunk_ids:
        single = str((payload or {}).get('chunk_id') or '').strip()
        if single:
            chunk_ids = [single]
    if not chunk_ids:
        return json_error('Pick at least one memory item first.', 400)
    memory_scope = str((payload or {}).get('memory_scope') or '').strip() or None
    project_id = str((payload or {}).get('project_id') or '').strip()
    visibility = str((payload or {}).get('visibility') or '').strip() or None
    bleed_policy = str((payload or {}).get('bleed_policy') or '').strip() or None
    sandbox_policy = str((payload or {}).get('sandbox_policy') or '').strip() or None
    if memory_scope in {'project', 'project_only'} and not project_id:
        return json_error('Choose a project before moving memory into a project sandbox.', 400)
    if memory_scope in {'global', 'profile', 'assistant_wide'}:
        project_id = ''
        bleed_policy = bleed_policy or 'allow_global'
        visibility = visibility or 'assistant_wide'
        sandbox_policy = sandbox_policy or 'global_visible'
    elif memory_scope in {'quarantine', 'review'}:
        bleed_policy = bleed_policy or 'quarantine'
        visibility = visibility or 'hidden_until_review'
        sandbox_policy = sandbox_policy or 'deny_until_reviewed'
    elif memory_scope:
        bleed_policy = bleed_policy or 'deny_global'
        visibility = visibility or 'project_private'
        sandbox_policy = sandbox_policy or 'project_boxed'
    try:
        updated_count = bulk_update_memory_chunk_sandbox(
            chunk_ids=chunk_ids,
            memory_scope=memory_scope,
            project_id=project_id,
            visibility=visibility,
            bleed_policy=bleed_policy,
            sandbox_policy=sandbox_policy,
        )
        memory_refresh = refresh_after_memory_write(lane='assistant', project_id=project_id, reason='sandbox_update', chunk_ids=chunk_ids, auto_refresh=True)
        record_memory_write(
            write_log_id=f'awl_sandbox_update_{chunk_ids[0][:16]}_{updated_count}',
            lane='assistant',
            entity_type='memory_sandbox',
            entity_id=project_id or memory_scope or 'global',
            operation='sandbox_update',
            details={
                'chunk_ids': chunk_ids,
                'updated_count': updated_count,
                'memory_scope': memory_scope,
                'project_id': project_id,
                'visibility': visibility,
                'bleed_policy': bleed_policy,
                'sandbox_policy': sandbox_policy,
            },
        )
        return JSONResponse({'ok': True, 'updated_count': updated_count, 'memory_index_state': memory_refresh.get('index_state') if isinstance(memory_refresh, dict) else {}, 'message': f'Updated sandbox settings for {updated_count} memory item(s).', **_memory_admin_payload(lane='assistant')})
    except Exception as exc:
        return json_error(str(exc) or 'Could not update memory sandbox settings.', 500)

@router.post('/api/assistant/memory-conflict-resolve')
async def api_assistant_memory_conflict_resolve(payload: dict):
    preferred_chunk_id = str((payload or {}).get('preferred_chunk_id') or '').strip()
    rejected_chunk_ids = [str(item or '').strip() for item in ((payload or {}).get('rejected_chunk_ids') or []) if str(item or '').strip()]
    reason = str((payload or {}).get('reason') or 'conflict_resolved').strip() or 'conflict_resolved'
    if not preferred_chunk_id or not rejected_chunk_ids:
        return json_error('Pick one memory to keep and at least one to suppress.', 400)
    preferred = fetch_memory_chunk_by_id(preferred_chunk_id)
    if not preferred:
        return json_error('Preferred memory item was not found.', 404)
    update_memory_chunk_state(chunk_id=preferred_chunk_id, is_pinned=True, is_suppressed=False, pin_note='Resolved as preferred memory', suppressed_reason='')
    for rejected_id in rejected_chunk_ids:
        update_memory_chunk_state(chunk_id=rejected_id, is_suppressed=True, suppressed_reason=reason)
    lane_key = str(preferred.get('lane') or '').strip().lower()
    collection_name = ASSISTANT_COLLECTION if lane_key == 'assistant' else ROLEPLAY_COLLECTION
    delete_memory_chunk_ids(collection_name, rejected_chunk_ids)
    try:
        reindex_active_backend_from_sqlite(lane=lane_key)
    except Exception:
        pass
    record_memory_write(
        write_log_id=f'awl_conflict_{preferred_chunk_id}',
        lane=lane_key,
        entity_type=str(preferred.get('entity_type') or '').strip(),
        entity_id=str(preferred.get('entity_id') or '').strip(),
        operation='conflict_resolved',
        source_ref=str(preferred.get('source_ref') or '').strip(),
        details={'preferred_chunk_id': preferred_chunk_id, 'rejected_chunk_ids': rejected_chunk_ids, 'reason': reason},
    )
    return JSONResponse({'ok': True, 'message': 'Memory conflict resolved.', **_memory_admin_payload(lane=lane_key)})


@router.get('/api/assistant/validation/status')
async def api_assistant_validation_status(limit: int = 20):
    try:
        return JSONResponse(read_assistant_logs(kind='validation', limit=max(1, min(int(limit or 20), 100))))
    except Exception as exc:
        return json_error(str(exc) or 'Could not load Assistant validation logs.', 500)


@router.post('/api/assistant/validation/run')
async def api_assistant_validation_run(payload: dict | None = None):
    try:
        result = run_assistant_validation_suite(include_optional=bool((payload or {}).get('include_optional', True)))
        return JSONResponse(result)
    except Exception as exc:
        return json_error(str(exc) or 'Could not run Assistant validation suite.', 500)


@router.get('/api/assistant/logs')
async def api_assistant_logs(kind: str = 'events', limit: int = 50):
    try:
        clean_kind = str(kind or 'events').strip().lower()
        if clean_kind not in {'events', 'validation'}:
            clean_kind = 'events'
        return JSONResponse(read_assistant_logs(kind=clean_kind, limit=max(1, min(int(limit or 50), 200))))
    except Exception as exc:
        return json_error(str(exc) or 'Could not load Assistant logs.', 500)


@router.post('/api/assistant/log-event')
async def api_assistant_log_event(payload: dict):
    try:
        event = log_assistant_event(
            event_type=str((payload or {}).get('event_type') or 'manual_event').strip(),
            source=str((payload or {}).get('source') or 'assistant_ui').strip(),
            status=str((payload or {}).get('status') or 'info').strip(),
            details=(payload or {}).get('details') if isinstance((payload or {}).get('details'), dict) else {},
        )
        return JSONResponse({'ok': True, 'event': event})
    except Exception as exc:
        return json_error(str(exc) or 'Could not write Assistant event log.', 400)
