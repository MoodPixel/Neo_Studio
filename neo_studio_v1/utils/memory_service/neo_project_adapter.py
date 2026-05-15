from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..logging_utils import get_logger
from .chroma_store import NEO_PROJECT_COLLECTION, delete_memory_chunks_for_entity, upsert_memory_chunks
from .sqlite_store import ensure_memory_foundation, execute, record_memory_write, upsert_memory_chunks_sqlite, delete_memory_chunks_for_entity_sqlite

logger = get_logger(__name__)

NEO_PROJECT_LANE = 'neo_project'
DEFAULT_PROJECT_ID = 'neo_studio'

ALLOWED_NEO_PROJECT_MEMORY_TYPES = {
    'repo_fact',
    'system_record',
    'implementation_decision',
    'extension_contract',
    'workflow_rule',
    'bug_history',
    'fix_pattern',
    'failed_attempt',
    'validation_result',
    'guardrail',
    'todo',
    'summary',
}

TYPE_IMPORTANCE_DEFAULTS = {
    'guardrail': 0.92,
    'implementation_decision': 0.88,
    'extension_contract': 0.86,
    'workflow_rule': 0.84,
    'fix_pattern': 0.82,
    'bug_history': 0.78,
    'repo_fact': 0.72,
    'system_record': 0.70,
    'validation_result': 0.68,
    'failed_attempt': 0.66,
    'todo': 0.62,
    'summary': 0.55,
}


def _clean(value: Any, limit: int = 2400) -> str:
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def _json(value: Any, default: str = '{}') -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default), ensure_ascii=False)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _normalise_type(value: Any) -> str:
    clean = _clean(value, 80).lower().replace('-', '_').replace(' ', '_')
    return clean if clean in ALLOWED_NEO_PROJECT_MEMORY_TYPES else 'repo_fact'


def build_neo_project_memory_chunk(record: dict[str, Any], *, source_json_path: str = '') -> dict[str, Any] | None:
    """Build a durable memory chunk for Neo project/repo facts.

    This lane is intentionally separate from Assistant personal/session memory.
    It should hold stable Neo Studio implementation knowledge: system records,
    workflow rules, bug/fix history, extension contracts, and validation notes.
    """
    record = record if isinstance(record, dict) else {}
    memory_type = _normalise_type(record.get('memory_type') or record.get('chunk_type') or record.get('type'))
    project_id = _clean(record.get('project_id') or DEFAULT_PROJECT_ID, 120) or DEFAULT_PROJECT_ID
    entity_type = _clean(record.get('entity_type') or memory_type, 80) or memory_type
    entity_id = _clean(record.get('id') or record.get('entity_id') or f'{memory_type}_{uuid4().hex}', 180)
    title = _clean(record.get('title') or record.get('label') or memory_type.replace('_', ' ').title(), 220)
    component = _clean(record.get('component') or record.get('tab') or record.get('area') or '', 120)
    file_path = _clean(record.get('file_path') or record.get('path') or '', 260)
    source_ref = _clean(record.get('source_ref') or source_json_path or file_path, 300)
    content = _clean(record.get('content') or record.get('summary') or record.get('note') or record.get('text') or '', 2600)
    if not content:
        return None
    created_at = _clean(record.get('created_at') or record.get('updated_at') or _now_iso(), 80)
    updated_at = _clean(record.get('updated_at') or created_at, 80)
    importance_raw = record.get('importance')
    try:
        importance = float(importance_raw) if importance_raw is not None else float(TYPE_IMPORTANCE_DEFAULTS.get(memory_type, 0.66))
    except Exception:
        importance = float(TYPE_IMPORTANCE_DEFAULTS.get(memory_type, 0.66))
    importance = max(0.0, min(1.0, importance))
    tags = record.get('tags') if isinstance(record.get('tags'), list) else []
    tag_text = ', '.join(_clean(tag, 60) for tag in tags if _clean(tag, 60))
    document_bits = [f'Title: {title}', f'Type: {memory_type}']
    if component:
        document_bits.append(f'Component: {component}')
    if file_path:
        document_bits.append(f'File: {file_path}')
    if tag_text:
        document_bits.append(f'Tags: {tag_text}')
    document_bits.append(f'Detail: {content}')
    document = _clean(' | '.join(document_bits), 3000)
    return {
        'id': f'neo_project::{project_id}::{memory_type}::{entity_id}',
        'document': document,
        'metadata': {
            'lane': NEO_PROJECT_LANE,
            'chunk_type': memory_type,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'scope_type': _clean(record.get('scope_type') or 'project', 80) or 'project',
            'scope_id': _clean(record.get('scope_id') or project_id, 160) or project_id,
            'project_id': project_id,
            'campaign_id': '',
            'component': component,
            'file_path': file_path,
            'source_ref': source_ref,
            'importance': importance,
            'created_at': created_at,
            'updated_at': updated_at,
            'tags': tag_text,
        },
    }


def sync_neo_project_memory(record: dict[str, Any], *, source_json_path: str = '') -> bool:
    """Upsert one Neo project memory record into SQLite + Chroma mirror."""
    try:
        ensure_memory_foundation()
        chunk = build_neo_project_memory_chunk(record, source_json_path=source_json_path)
        if not chunk:
            return False
        metadata = chunk.get('metadata') if isinstance(chunk.get('metadata'), dict) else {}
        entity_id = str(metadata.get('entity_id') or '').strip()
        upserted = upsert_memory_chunks_sqlite(lane=NEO_PROJECT_LANE, collection_name=NEO_PROJECT_COLLECTION, chunks=[chunk])
        chroma_ok = upsert_memory_chunks(NEO_PROJECT_COLLECTION, [chunk])
        record_memory_write(
            write_log_id=f'npmwl_{uuid4().hex}',
            lane=NEO_PROJECT_LANE,
            entity_type=str(metadata.get('entity_type') or '').strip(),
            entity_id=entity_id,
            operation='upsert',
            source_ref=str(source_json_path or metadata.get('source_ref') or '').strip(),
            details={'sqlite_chunk_count': upserted, 'chroma_upserted': chroma_ok, 'memory_type': metadata.get('chunk_type')},
            created_at=str(metadata.get('updated_at') or metadata.get('created_at') or '').strip(),
        )
        return True
    except Exception:
        logger.exception('Neo project memory sync failed.')
        return False


def delete_neo_project_memory(entity_id: str) -> bool:
    clean_id = str(entity_id or '').strip()
    if not clean_id:
        return False
    try:
        ensure_memory_foundation()
        delete_memory_chunks_for_entity_sqlite(lane=NEO_PROJECT_LANE, entity_id=clean_id)
        delete_memory_chunks_for_entity(NEO_PROJECT_COLLECTION, entity_id=clean_id)
        record_memory_write(
            write_log_id=f'npmwl_{uuid4().hex}',
            lane=NEO_PROJECT_LANE,
            entity_type='neo_project_memory',
            entity_id=clean_id,
            operation='delete',
            details={},
            created_at=_now_iso(),
        )
        return True
    except Exception:
        logger.exception('Neo project memory delete failed for %s.', clean_id)
        return False
