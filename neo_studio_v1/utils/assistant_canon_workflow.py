from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from .assistant_entity_registry import (
    CANON_ORDER,
    _clean,
    _load_json,
    _normalize_kind,
    _row_to_entity,
    _safe_json,
    ensure_entity_registry_foundation,
    fetch_project_entities,
)
from .memory_service.sqlite_store import sqlite_conn

CANON_WORKFLOW_VERSION = 'assistant_canon_workflow_v1'
MUTABLE_CANON_STATUSES = {'draft', 'active', 'primary_canon', 'secondary_canon', 'speculative', 'disputed', 'deprecated', 'archived', 'contradicted'}


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _slug(value: str, fallback: str = 'item') -> str:
    clean = re.sub(r'[^a-zA-Z0-9._:-]+', '-', str(value or '').strip()).strip('-._:')
    return (clean or fallback)[:180]


def ensure_canon_workflow_foundation() -> None:
    ensure_entity_registry_foundation()
    with sqlite_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS assistant_canon_change_proposals (
                proposal_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT 'upsert_entity',
                target_entity_uid TEXT NOT NULL DEFAULT '',
                target_entity_id TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'record',
                label TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                canon_status TEXT NOT NULL DEFAULT 'draft',
                visibility TEXT NOT NULL DEFAULT 'project_private',
                reason TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                warnings_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                applied_at TEXT NOT NULL DEFAULT ''
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_assistant_canon_proposals_project ON assistant_canon_change_proposals(project_id, status, updated_at)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS assistant_canon_change_history (
                history_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                proposal_id TEXT NOT NULL DEFAULT '',
                entity_uid TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                before_json TEXT NOT NULL DEFAULT '{}',
                after_json TEXT NOT NULL DEFAULT '{}',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_assistant_canon_history_entity ON assistant_canon_change_history(project_id, entity_uid, created_at)')


def _entity_uid_for(project_id: str, entity_id: str, label: str, kind: str) -> str:
    if entity_id:
        return f'{project_id}::{_slug(entity_id, "entity")} '
    return f'{project_id}::{_slug(f"{kind}:{label}".lower(), "entity")}'


def _fetch_entity_by_uid(project_id: str, entity_uid: str) -> dict[str, Any] | None:
    ensure_canon_workflow_foundation()
    with sqlite_conn() as conn:
        row = conn.execute('SELECT * FROM assistant_entities WHERE project_id=? AND entity_uid=? AND is_deleted=0', (project_id, entity_uid)).fetchone()
    return _row_to_entity(row) if row else None


def _row_to_proposal(row) -> dict[str, Any]:
    return {
        'proposal_id': row['proposal_id'],
        'project_id': row['project_id'],
        'action': row['action'],
        'target_entity_uid': row['target_entity_uid'],
        'target_entity_id': row['target_entity_id'],
        'kind': row['kind'],
        'label': row['label'],
        'summary': row['summary'],
        'canon_status': row['canon_status'],
        'visibility': row['visibility'],
        'reason': row['reason'],
        'payload': _load_json(row['payload_json'], {}),
        'warnings': _load_json(row['warnings_json'], []),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'applied_at': row['applied_at'],
    }


def _history_row(row) -> dict[str, Any]:
    return {
        'history_id': row['history_id'],
        'project_id': row['project_id'],
        'proposal_id': row['proposal_id'],
        'entity_uid': row['entity_uid'],
        'action': row['action'],
        'before': _load_json(row['before_json'], {}),
        'after': _load_json(row['after_json'], {}),
        'reason': row['reason'],
        'created_at': row['created_at'],
    }


def analyze_canon_change(*, project_id: str, action: str = 'upsert_entity', entity_uid: str = '', entity_id: str = '', kind: str = 'record', label: str = '', summary: str = '', canon_status: str = 'draft', visibility: str = 'project_private') -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    action = str(action or 'upsert_entity').strip()
    kind = _normalize_kind(kind or 'record')
    label = _clean(label or entity_id or 'Untitled entity', 240)
    entity_id = _clean(entity_id or '', 240)
    summary = _clean(summary or '', 6000)
    canon_status = str(canon_status or 'draft').strip()
    visibility = str(visibility or 'project_private').strip()
    warnings: list[dict[str, Any]] = []
    if not clean_project_id:
        warnings.append({'severity': 'error', 'type': 'missing_project', 'message': 'No project selected.'})
    if action not in {'upsert_entity', 'update_entity', 'promote_entity', 'deprecate_entity', 'archive_entity'}:
        warnings.append({'severity': 'error', 'type': 'unsupported_action', 'message': f'Unsupported canon action: {action}'})
    if canon_status not in MUTABLE_CANON_STATUSES:
        warnings.append({'severity': 'warn', 'type': 'unknown_canon_status', 'message': f'Unknown canon status: {canon_status}'})
    existing = None
    if entity_uid:
        existing = _fetch_entity_by_uid(clean_project_id, entity_uid)
    if not existing and (entity_id or label):
        candidates = fetch_project_entities(clean_project_id, kind=kind, q=entity_id or label, limit=25)
        for item in candidates:
            same_id = entity_id and str(item.get('entity_id') or '').lower() == entity_id.lower()
            same_label = label and str(item.get('label') or '').lower() == label.lower()
            if same_id or same_label:
                existing = item
                entity_uid = str(item.get('entity_uid') or '')
                break
    if existing:
        old_rank = CANON_ORDER.get(str(existing.get('canon_status') or ''), 0)
        new_rank = CANON_ORDER.get(canon_status, 50)
        if new_rank < old_rank and action in {'upsert_entity', 'update_entity', 'promote_entity'}:
            warnings.append({'severity': 'warn', 'type': 'canon_downgrade', 'message': f'Existing entity is {existing.get("canon_status")}; proposed status is {canon_status}.'})
        if summary and existing.get('summary') and summary.strip() != str(existing.get('summary') or '').strip():
            overlap = _rough_overlap(str(existing.get('summary') or ''), summary)
            if overlap < 0.12:
                warnings.append({'severity': 'warn', 'type': 'low_summary_overlap', 'message': 'Proposed summary differs strongly from existing entity summary. Review before applying.'})
        if label and existing.get('label') and label.lower() != str(existing.get('label') or '').lower():
            warnings.append({'severity': 'info', 'type': 'label_change', 'message': f'Label may change from "{existing.get("label")}" to "{label}".'})
    else:
        near = fetch_project_entities(clean_project_id, kind=kind, q=label, limit=10) if clean_project_id and label else []
        near_labels = [item for item in near if str(item.get('label') or '').lower() != label.lower()]
        if near_labels:
            warnings.append({'severity': 'info', 'type': 'possible_duplicate', 'message': 'Similar entities already exist.', 'matches': [{'entity_uid': m.get('entity_uid'), 'label': m.get('label'), 'canon_status': m.get('canon_status')} for m in near_labels[:5]]})
    return {
        'ok': not any(w.get('severity') == 'error' for w in warnings),
        'version': CANON_WORKFLOW_VERSION,
        'project_id': clean_project_id,
        'action': action,
        'target_entity_uid': entity_uid,
        'existing_entity': existing,
        'proposed': {
            'entity_id': entity_id,
            'kind': kind,
            'label': label,
            'summary': summary,
            'canon_status': canon_status,
            'visibility': visibility,
        },
        'warnings': warnings,
    }


def _rough_overlap(a: str, b: str) -> float:
    def tokens(s: str) -> set[str]:
        return {t for t in re.findall(r'[a-zA-Z0-9_]{4,}', s.lower()) if t not in {'with', 'this', 'that', 'from', 'into', 'they', 'their'}}
    aa, bb = tokens(a), tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, min(len(aa), len(bb)))


def create_canon_change_proposal(*, project_id: str, action: str = 'upsert_entity', entity_uid: str = '', entity_id: str = '', kind: str = 'record', label: str = '', summary: str = '', canon_status: str = 'draft', visibility: str = 'project_private', reason: str = '', payload: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_canon_workflow_foundation()
    analysis = analyze_canon_change(project_id=project_id, action=action, entity_uid=entity_uid, entity_id=entity_id, kind=kind, label=label, summary=summary, canon_status=canon_status, visibility=visibility)
    proposal_id = f'canon_{uuid4().hex[:14]}'
    now = _now_iso()
    proposed = analysis.get('proposed') or {}
    warnings = analysis.get('warnings') or []
    status = 'blocked' if any(w.get('severity') == 'error' for w in warnings) else 'draft'
    with sqlite_conn() as conn:
        conn.execute('''
            INSERT INTO assistant_canon_change_proposals(proposal_id, project_id, action, target_entity_uid, target_entity_id, kind, label, summary, canon_status, visibility, reason, payload_json, warnings_json, status, created_at, updated_at, applied_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
        ''', (
            proposal_id, str(project_id or '').strip(), action, str(analysis.get('target_entity_uid') or entity_uid or '').strip(),
            str(proposed.get('entity_id') or entity_id or '').strip(), str(proposed.get('kind') or kind or 'record').strip(),
            str(proposed.get('label') or label or '').strip(), str(proposed.get('summary') or summary or '').strip(),
            str(proposed.get('canon_status') or canon_status or 'draft').strip(), str(proposed.get('visibility') or visibility or 'project_private').strip(),
            _clean(reason, 1200), _safe_json(payload or {}), _safe_json(warnings), status, now, now,
        ))
        row = conn.execute('SELECT * FROM assistant_canon_change_proposals WHERE proposal_id=?', (proposal_id,)).fetchone()
    proposal = _row_to_proposal(row)
    proposal['analysis'] = analysis
    return {'ok': status != 'blocked', 'proposal': proposal, 'analysis': analysis}


def list_canon_change_proposals(project_id: str, *, status: str = '', limit: int = 50) -> list[dict[str, Any]]:
    ensure_canon_workflow_foundation()
    where = ['project_id=?']
    params: list[Any] = [str(project_id or '').strip()]
    if status:
        where.append('status=?')
        params.append(str(status).strip())
    sql = 'SELECT * FROM assistant_canon_change_proposals WHERE ' + ' AND '.join(where) + ' ORDER BY updated_at DESC LIMIT ?'
    params.append(max(1, min(int(limit or 50), 200)))
    with sqlite_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_proposal(row) for row in rows]


def apply_canon_change_proposal(*, project_id: str, proposal_id: str, confirm: bool = False) -> dict[str, Any]:
    ensure_canon_workflow_foundation()
    if not confirm:
        return {'ok': False, 'error': 'confirmation_required', 'message': 'Set confirm=true to apply this canon change.'}
    clean_project_id = str(project_id or '').strip()
    with sqlite_conn() as conn:
        row = conn.execute('SELECT * FROM assistant_canon_change_proposals WHERE project_id=? AND proposal_id=?', (clean_project_id, proposal_id)).fetchone()
        if not row:
            return {'ok': False, 'error': 'proposal_not_found'}
        proposal = _row_to_proposal(row)
        if proposal.get('status') == 'applied':
            return {'ok': True, 'proposal': proposal, 'message': 'Proposal already applied.'}
        if proposal.get('status') == 'blocked':
            return {'ok': False, 'error': 'proposal_blocked', 'proposal': proposal}
        before = None
        target_uid = str(proposal.get('target_entity_uid') or '').strip()
        if target_uid:
            before_row = conn.execute('SELECT * FROM assistant_entities WHERE project_id=? AND entity_uid=? AND is_deleted=0', (clean_project_id, target_uid)).fetchone()
            before = _row_to_entity(before_row) if before_row else None
        action = str(proposal.get('action') or 'upsert_entity')
        now = _now_iso()
        final_status = str(proposal.get('canon_status') or 'draft')
        if action == 'promote_entity' and final_status == 'draft':
            final_status = 'active'
        if action == 'deprecate_entity':
            final_status = 'deprecated'
        if action == 'archive_entity':
            final_status = 'archived'
        if before:
            entity_uid = before['entity_uid']
            after = {**before,
                'label': proposal.get('label') or before.get('label') or '',
                'summary': proposal.get('summary') or before.get('summary') or '',
                'canon_status': final_status,
                'visibility': proposal.get('visibility') or before.get('visibility') or 'project_private',
                'updated_at': now,
            }
            conn.execute('''
                UPDATE assistant_entities SET label=?, summary=?, canon_status=?, visibility=?, updated_at=? WHERE project_id=? AND entity_uid=?
            ''', (after['label'], after['summary'], after['canon_status'], after['visibility'], now, clean_project_id, entity_uid))
        else:
            kind = str(proposal.get('kind') or 'record')
            label = str(proposal.get('label') or proposal.get('target_entity_id') or 'Entity')
            entity_id = str(proposal.get('target_entity_id') or '').strip()
            entity_uid = f'{clean_project_id}::{_slug(entity_id or f"{kind}:{label}".lower(), "entity")}'
            after = {
                'entity_uid': entity_uid,
                'project_id': clean_project_id,
                'entity_id': entity_id,
                'kind': _normalize_kind(kind),
                'label': label,
                'summary': str(proposal.get('summary') or ''),
                'canon_status': final_status,
                'visibility': str(proposal.get('visibility') or 'project_private'),
                'source_ref': 'canon_workflow',
                'source_filename': '',
                'import_id': '',
                'metadata': {'created_by': CANON_WORKFLOW_VERSION, 'proposal_id': proposal_id},
                'created_at': now,
                'updated_at': now,
            }
            conn.execute('''
                INSERT INTO assistant_entities(entity_uid, project_id, entity_id, kind, label, summary, canon_status, visibility, source_ref, source_filename, import_id, metadata_json, created_at, updated_at, is_deleted)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'canon_workflow', '', '', ?, ?, ?, 0)
            ''', (entity_uid, clean_project_id, after['entity_id'], after['kind'], after['label'], after['summary'], after['canon_status'], after['visibility'], _safe_json(after['metadata']), now, now))
        history_id = f'canonhist_{uuid4().hex[:14]}'
        conn.execute('''
            INSERT INTO assistant_canon_change_history(history_id, project_id, proposal_id, entity_uid, action, before_json, after_json, reason, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (history_id, clean_project_id, proposal_id, entity_uid, action, _safe_json(before or {}), _safe_json(after or {}), str(proposal.get('reason') or ''), now))
        conn.execute('UPDATE assistant_canon_change_proposals SET status="applied", applied_at=?, updated_at=?, target_entity_uid=? WHERE project_id=? AND proposal_id=?', (now, now, entity_uid, clean_project_id, proposal_id))
    return {'ok': True, 'proposal_id': proposal_id, 'entity_uid': entity_uid, 'before': before, 'after': after, 'history_id': history_id, 'message': 'Canon change applied.'}


def list_entity_change_history(project_id: str, *, entity_uid: str = '', limit: int = 50) -> list[dict[str, Any]]:
    ensure_canon_workflow_foundation()
    where = ['project_id=?']
    params: list[Any] = [str(project_id or '').strip()]
    if entity_uid:
        where.append('entity_uid=?')
        params.append(str(entity_uid).strip())
    sql = 'SELECT * FROM assistant_canon_change_history WHERE ' + ' AND '.join(where) + ' ORDER BY created_at DESC LIMIT ?'
    params.append(max(1, min(int(limit or 50), 200)))
    with sqlite_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_history_row(row) for row in rows]
