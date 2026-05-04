from __future__ import annotations
import json
import re
from pathlib import Path
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from ..utils.assistant_chat import stream_assistant_reply, transform_assistant_text
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
        session = {**session, 'project_context': {'title': project.get('title') or '', 'description': project.get('description') or '', 'brief': project.get('brief') or '', 'context_cards': project.get('context_cards') or [], 'context_files': project.get('context_files') or []}}
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
    project_id = str(session.get('project_id') or '').strip()
    if project_id:
        project = load_project(project_id)
        if project:
            session = {**session, 'project_context': {'title': project.get('title') or '', 'description': project.get('description') or '', 'brief': project.get('brief') or '', 'context_cards': project.get('context_cards') or [], 'context_files': project.get('context_files') or []}}
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
    project_id = str(session.get('project_id') or '').strip()
    if project_id:
        project = load_project(project_id)
        if project:
            session = {**session, 'project_context': {'title': project.get('title') or '', 'description': project.get('description') or '', 'brief': project.get('brief') or '', 'context_cards': project.get('context_cards') or [], 'context_files': project.get('context_files') or []}}
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
    elif bool(payload.get('reindex', True)):
        try:
            reindex_active_backend_from_sqlite(lane=lane_key)
        except Exception:
            pass
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
