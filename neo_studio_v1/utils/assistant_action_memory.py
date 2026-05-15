from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .logging_utils import get_logger
from .memory_service.chroma_store import ASSISTANT_COLLECTION, upsert_memory_chunks
from .memory_service.neo_project_adapter import DEFAULT_PROJECT_ID, sync_neo_project_memory
from .memory_service.sqlite_store import ensure_memory_foundation, fetch_memory_chunks, record_memory_write, upsert_memory_chunks_sqlite

logger = get_logger(__name__)

ACTION_MEMORY_VERSION = 'assistant_action_memory_v1'
MAX_TEXT = 1800
MAX_DETAIL_TEXT = 4200
MAX_RECENT_EVENTS = 20

ASSISTANT_ACTION_TYPES = {
    'action_log',
    'task_memory',
    'tool_result',
    'patch_result',
    'validation_result',
    'failed_attempt',
    'decision_record',
}

TECHNICAL_PROJECT_TYPES = {
    'patch_result': 'implementation_decision',
    'validation_result': 'validation_result',
    'failed_attempt': 'failed_attempt',
    'tool_result': 'repo_fact',
    'task_memory': 'summary',
    'decision_record': 'implementation_decision',
    'action_log': 'summary',
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def _safe_json(value: Any, limit: int = MAX_DETAIL_TEXT) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value or '')
    return raw[:limit]


def _hash_payload(payload: Dict[str, Any]) -> str:
    raw = _safe_json(payload, limit=12000)
    return hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:18]


def _normalise_action_type(value: Any, *, status: str = '') -> str:
    clean = _clean(value, 80).lower().replace('-', '_').replace(' ', '_')
    if _clean(status, 40).lower() in {'error', 'failed', 'failure'}:
        return 'failed_attempt'
    return clean if clean in ASSISTANT_ACTION_TYPES else 'action_log'


def _extract_paths(value: Any) -> List[str]:
    paths: List[str] = []
    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, val in item.items():
                lk = str(key or '').lower()
                if lk in {'path', 'file', 'file_path', 'backup_path', 'backup_manifest'} and isinstance(val, str):
                    clean = _clean(val, 300)
                    if clean and clean not in paths:
                        paths.append(clean)
                elif lk in {'changes', 'applied', 'files', 'results'}:
                    walk(val)
        elif isinstance(item, list):
            for entry in item[:40]:
                walk(entry)
    walk(value)
    return paths[:20]


def _summarise_tool_result(tool_id: str, result: Dict[str, Any], *, status: str) -> str:
    if status != 'success':
        return f'Tool {tool_id} failed: {_clean(result.get("error") or result, 900)}'
    inner = result.get('result') if isinstance(result.get('result'), dict) else result
    bits = [f'Tool {tool_id} executed successfully.']
    if isinstance(inner, dict):
        if inner.get('message'):
            bits.append(_clean(inner.get('message'), 500))
        if inner.get('file_count') is not None:
            bits.append(f"file_count={inner.get('file_count')}")
        if inner.get('result_count') is not None:
            bits.append(f"result_count={inner.get('result_count')}")
        if inner.get('applied_count') is not None:
            bits.append(f"applied_count={inner.get('applied_count')}")
        if inner.get('backup_id'):
            bits.append(f"backup_id={_clean(inner.get('backup_id'), 120)}")
    return ' '.join(bits)[:MAX_TEXT]


def build_action_memory_chunk(
    *,
    action_type: str,
    status: str,
    summary: str,
    details: Dict[str, Any] | None = None,
    session_id: str = '',
    project_id: str = '',
    entity_id: str = '',
    source_ref: str = '',
    importance: float | None = None,
) -> Dict[str, Any] | None:
    details = details if isinstance(details, dict) else {}
    clean_status = _clean(status or 'success', 40).lower() or 'success'
    memory_type = _normalise_action_type(action_type, status=clean_status)
    clean_summary = _clean(summary, MAX_TEXT)
    if not clean_summary:
        return None
    now = _now_iso()
    clean_project_id = _clean(project_id, 160)
    clean_session_id = _clean(session_id, 160)
    if not entity_id:
        entity_id = f'{memory_type}_{_hash_payload({"summary": clean_summary, "details": details, "created_at": now})}'
    clean_entity_id = _clean(entity_id, 220)
    paths = _extract_paths(details)
    detail_json = _safe_json(details, MAX_DETAIL_TEXT)
    path_text = ', '.join(paths[:8])
    importance_value = 0.68
    if memory_type in {'patch_result', 'decision_record'}:
        importance_value = 0.82
    elif memory_type == 'failed_attempt':
        importance_value = 0.78
    elif memory_type == 'validation_result':
        importance_value = 0.72
    elif memory_type == 'task_memory':
        importance_value = 0.74
    if importance is not None:
        try:
            importance_value = max(0.0, min(1.0, float(importance)))
        except Exception:
            pass
    document_bits = [
        f'Type: {memory_type}',
        f'Status: {clean_status}',
        f'Summary: {clean_summary}',
    ]
    if clean_session_id:
        document_bits.append(f'Session: {clean_session_id}')
    if clean_project_id:
        document_bits.append(f'Project: {clean_project_id}')
    if path_text:
        document_bits.append(f'Files: {path_text}')
    if detail_json:
        document_bits.append(f'Details: {detail_json}')
    document = _clean(' | '.join(document_bits), 3200)
    return {
        'id': f'assistant::{memory_type}::{clean_entity_id}',
        'document': document,
        'metadata': {
            'lane': 'assistant',
            'chunk_type': memory_type,
            'entity_type': 'assistant_action',
            'entity_id': clean_entity_id,
            'scope_type': 'session' if clean_session_id else ('project' if clean_project_id else 'profile'),
            'scope_id': clean_session_id or clean_project_id or 'default',
            'project_id': clean_project_id,
            'campaign_id': '',
            'session_id': clean_session_id,
            'status': clean_status,
            'source_ref': _clean(source_ref or details.get('source_ref') or '', 300),
            'importance': importance_value,
            'created_at': now,
            'updated_at': now,
            'paths': path_text,
            'version': ACTION_MEMORY_VERSION,
        },
    }


def sync_action_memory(
    *,
    action_type: str,
    status: str,
    summary: str,
    details: Dict[str, Any] | None = None,
    session_id: str = '',
    project_id: str = '',
    entity_id: str = '',
    source_ref: str = '',
    mirror_to_neo_project: bool = True,
    importance: float | None = None,
) -> Dict[str, Any]:
    """Write one Assistant action/task memory event.

    This intentionally writes to the Assistant lane first, then mirrors technical
    events into the Neo Project lane so later repo/debug work can retrieve them.
    Failures are swallowed by callers when used as telemetry; direct API calls
    receive the returned ok/error payload.
    """
    try:
        ensure_memory_foundation()
        chunk = build_action_memory_chunk(
            action_type=action_type,
            status=status,
            summary=summary,
            details=details,
            session_id=session_id,
            project_id=project_id,
            entity_id=entity_id,
            source_ref=source_ref,
            importance=importance,
        )
        if not chunk:
            return {'ok': False, 'error': 'empty_action_memory'}
        metadata = chunk.get('metadata') if isinstance(chunk.get('metadata'), dict) else {}
        sqlite_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=[chunk])
        chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, [chunk])
        record_memory_write(
            write_log_id=f'aamwl_{uuid4().hex}',
            lane='assistant',
            entity_type='assistant_action',
            entity_id=str(metadata.get('entity_id') or '').strip(),
            operation='upsert_action_memory',
            source_ref=str(source_ref or metadata.get('source_ref') or '').strip(),
            details={'memory_type': metadata.get('chunk_type'), 'status': metadata.get('status'), 'sqlite_chunk_count': sqlite_count, 'chroma_upserted': chroma_ok},
            created_at=str(metadata.get('updated_at') or metadata.get('created_at') or '').strip(),
        )
        neo_project_ok = False
        if mirror_to_neo_project and str(metadata.get('chunk_type') or '') in TECHNICAL_PROJECT_TYPES:
            project_memory_type = TECHNICAL_PROJECT_TYPES.get(str(metadata.get('chunk_type') or ''), 'summary')
            neo_project_ok = sync_neo_project_memory({
                'id': f"action_{metadata.get('entity_id')}",
                'memory_type': project_memory_type,
                'project_id': DEFAULT_PROJECT_ID,
                'component': 'assistant',
                'title': f"Assistant {metadata.get('chunk_type')} — {metadata.get('status')}",
                'content': summary,
                'source_ref': source_ref or metadata.get('source_ref') or 'assistant_action_memory',
                'tags': ['assistant', 'action-memory', str(metadata.get('chunk_type') or '')],
                'importance': min(0.92, float(metadata.get('importance') or 0.68) + 0.04),
            })
        return {
            'ok': True,
            'chunk_id': chunk.get('id'),
            'memory_type': metadata.get('chunk_type'),
            'status': metadata.get('status'),
            'sqlite_chunk_count': sqlite_count,
            'chroma_upserted': chroma_ok,
            'neo_project_mirrored': neo_project_ok,
        }
    except Exception as exc:
        logger.exception('Assistant action memory write failed.')
        return {'ok': False, 'error': str(exc)}


def record_tool_action_memory(
    *,
    tool_id: str,
    arguments: Dict[str, Any] | None,
    result: Dict[str, Any] | None = None,
    error: str = '',
    confirmed: bool = False,
    session_id: str = '',
    project_id: str = '',
) -> Dict[str, Any]:
    status = 'failed' if error else 'success'
    payload = {
        'tool_id': _clean(tool_id, 160),
        'arguments': arguments if isinstance(arguments, dict) else {},
        'result': result if isinstance(result, dict) else {},
        'error': _clean(error, 1200),
        'confirmed': bool(confirmed),
    }
    action_type = 'failed_attempt' if error else ('patch_result' if str(tool_id or '').startswith('patch.') and str(tool_id or '').endswith('apply') else 'tool_result')
    summary = _summarise_tool_result(tool_id, {'result': result or {}, 'error': error}, status=status)
    return sync_action_memory(
        action_type=action_type,
        status=status,
        summary=summary,
        details=payload,
        session_id=session_id,
        project_id=project_id,
        entity_id=f'tool_{_clean(tool_id, 120)}_{_hash_payload(payload)}',
        source_ref=f'assistant_tool:{_clean(tool_id, 160)}',
    )


def record_patch_action_memory(
    *,
    operation: str,
    plan: Dict[str, Any] | None,
    result: Dict[str, Any] | None = None,
    error: str = '',
    confirmed: bool = False,
    session_id: str = '',
    project_id: str = '',
) -> Dict[str, Any]:
    status = 'failed' if error else 'success'
    clean_operation = _clean(operation, 80) or 'patch'
    result = result if isinstance(result, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    title = _clean(plan.get('title') or result.get('title') or 'Assistant patch plan', 220)
    change_count = result.get('change_count') if result.get('change_count') is not None else len(plan.get('changes') if isinstance(plan.get('changes'), list) else [])
    applied_count = result.get('applied_count')
    if error:
        summary = f'Patch {clean_operation} failed for {title}: {_clean(error, 900)}'
        action_type = 'failed_attempt'
    elif clean_operation == 'apply':
        summary = f'Patch plan applied: {title}. applied_count={applied_count if applied_count is not None else change_count}. backup_id={_clean(result.get("backup_id"), 160)}'
        action_type = 'patch_result'
    else:
        summary = f'Patch plan {clean_operation} completed: {title}. change_count={change_count}. risk={_clean(result.get("risk"), 80)}'
        action_type = 'validation_result'
    payload = {'operation': clean_operation, 'plan': plan, 'result': result, 'error': error, 'confirmed': bool(confirmed)}
    return sync_action_memory(
        action_type=action_type,
        status=status,
        summary=summary,
        details=payload,
        session_id=session_id,
        project_id=project_id,
        entity_id=f'patch_{clean_operation}_{_hash_payload(payload)}',
        source_ref=f'assistant_patch:{clean_operation}',
    )


def record_manual_task_memory(
    *,
    summary: str,
    outcome: str = '',
    session_id: str = '',
    project_id: str = '',
    details: Dict[str, Any] | None = None,
    memory_type: str = 'task_memory',
) -> Dict[str, Any]:
    clean_summary = _clean(summary, MAX_TEXT)
    if outcome:
        clean_summary = f'{clean_summary} Outcome: {_clean(outcome, 900)}'.strip()
    payload = details if isinstance(details, dict) else {}
    return sync_action_memory(
        action_type=memory_type,
        status='success',
        summary=clean_summary,
        details=payload,
        session_id=session_id,
        project_id=project_id,
        entity_id=f'task_{_hash_payload({"summary": clean_summary, "details": payload})}',
        source_ref='assistant_task_writeback',
    )


def recent_action_memory(*, session_id: str = '', project_id: str = '', limit: int = MAX_RECENT_EVENTS) -> Dict[str, Any]:
    rows = fetch_memory_chunks(lane='assistant', include_deleted=False, include_suppressed=False, limit=500)
    clean_session = _clean(session_id, 160)
    clean_project = _clean(project_id, 160)
    out: List[Dict[str, Any]] = []
    for row in rows:
        chunk_type = str(row.get('chunk_type') or '').strip()
        if chunk_type not in ASSISTANT_ACTION_TYPES:
            continue
        meta = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
        row_session = str(meta.get('session_id') or '').strip()
        row_project = str(row.get('project_id') or meta.get('project_id') or '').strip()
        if clean_session and row_session and row_session != clean_session:
            continue
        if clean_project and row_project and row_project != clean_project:
            continue
        out.append(row)
        if len(out) >= max(1, min(100, int(limit or MAX_RECENT_EVENTS))):
            break
    return {'ok': True, 'version': ACTION_MEMORY_VERSION, 'count': len(out), 'items': out}
