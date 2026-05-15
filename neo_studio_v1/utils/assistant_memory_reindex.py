from __future__ import annotations

"""Live Assistant memory reindexing and cache invalidation helpers.

Phase 14 goal: new/edited Assistant memory should become retrievable without a
server restart.  This module keeps a tiny in-process dirty-state registry and
centralizes the hooks used by ingestion, manual capture, sandbox edits, and UI
status endpoints.

It intentionally avoids importing FastAPI or route modules so it can be used by
low-level memory writers without circular imports.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _clean(value: Any, limit: int = 200) -> str:
    return str(value or '').strip()[:limit]


@dataclass
class MemoryDirtyScope:
    lane: str = 'assistant'
    project_id: str = ''
    session_id: str = ''
    scope_type: str = ''
    scope_id: str = ''
    reason: str = 'memory_updated'
    source_ref: str = ''
    chunk_ids: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_now_iso)

    def key(self) -> tuple[str, str, str, str, str]:
        return (
            _clean(self.lane or 'assistant', 40),
            _clean(self.project_id, 120),
            _clean(self.session_id, 120),
            _clean(self.scope_type, 80),
            _clean(self.scope_id, 120),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'lane': self.lane,
            'project_id': self.project_id,
            'session_id': self.session_id,
            'scope_type': self.scope_type,
            'scope_id': self.scope_id,
            'reason': self.reason,
            'source_ref': self.source_ref,
            'chunk_ids': list(self.chunk_ids),
            'chunk_count': len(self.chunk_ids),
            'updated_at': self.updated_at,
        }


_LOCK = RLock()
_DIRTY: dict[tuple[str, str, str, str, str], MemoryDirtyScope] = {}
_LAST_REFRESH: dict[str, Any] = {
    'ok': True,
    'state': 'synced',
    'message': 'Memory index is synced.',
    'updated_at': _now_iso(),
    'refreshed_count': 0,
}


def mark_memory_dirty(
    *,
    lane: str = 'assistant',
    project_id: str = '',
    session_id: str = '',
    scope_type: str = '',
    scope_id: str = '',
    reason: str = 'memory_updated',
    source_ref: str = '',
    chunk_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Mark a lane/project/session as needing a live refresh."""
    scope = MemoryDirtyScope(
        lane=_clean(lane or 'assistant', 40),
        project_id=_clean(project_id, 120),
        session_id=_clean(session_id, 120),
        scope_type=_clean(scope_type, 80),
        scope_id=_clean(scope_id, 120),
        reason=_clean(reason or 'memory_updated', 120),
        source_ref=_clean(source_ref, 500),
        chunk_ids=[_clean(item, 180) for item in (chunk_ids or []) if _clean(item, 180)],
    )
    with _LOCK:
        existing = _DIRTY.get(scope.key())
        if existing:
            merged = list(dict.fromkeys([*existing.chunk_ids, *scope.chunk_ids]))[:500]
            existing.chunk_ids = merged
            existing.reason = scope.reason or existing.reason
            existing.source_ref = scope.source_ref or existing.source_ref
            existing.updated_at = _now_iso()
            out = existing.to_dict()
        else:
            _DIRTY[scope.key()] = scope
            out = scope.to_dict()
        _LAST_REFRESH.update({
            'ok': True,
            'state': 'dirty',
            'message': 'Memory changed. Live refresh is pending.',
            'updated_at': _now_iso(),
        })
    return out


def consume_dirty_scopes(*, lane: str = '', project_id: str = '', session_id: str = '') -> list[dict[str, Any]]:
    clean_lane = _clean(lane, 40)
    clean_project = _clean(project_id, 120)
    clean_session = _clean(session_id, 120)
    consumed: list[MemoryDirtyScope] = []
    with _LOCK:
        for key, scope in list(_DIRTY.items()):
            if clean_lane and scope.lane != clean_lane:
                continue
            if clean_project and scope.project_id != clean_project:
                continue
            if clean_session and scope.session_id != clean_session:
                continue
            consumed.append(scope)
            _DIRTY.pop(key, None)
    return [scope.to_dict() for scope in consumed]


def memory_index_state() -> dict[str, Any]:
    with _LOCK:
        dirty = [scope.to_dict() for scope in _DIRTY.values()]
        state = 'dirty' if dirty else str(_LAST_REFRESH.get('state') or 'synced')
        return {
            'ok': True,
            'state': state,
            'dirty_count': len(dirty),
            'dirty_scopes': dirty[:50],
            'last_refresh': dict(_LAST_REFRESH),
            'badge': '🟡 Updating' if state == 'refreshing' else ('🔴 Reindex required' if dirty else '🟢 Synced'),
            'updated_at': _now_iso(),
        }


def invalidate_memory_caches(*, lane: str = 'assistant', project_id: str = '', session_id: str = '', reason: str = 'memory_updated', chunk_ids: list[str] | None = None) -> dict[str, Any]:
    """Public invalidation hook used immediately after memory writes.

    The current retriever mostly queries SQLite/Chroma live, but several maps and
    future vector/rerank layers can cache state.  Keeping this hook now makes the
    architecture explicit and gives the UI a reliable dirty badge.
    """
    return mark_memory_dirty(
        lane=lane,
        project_id=project_id,
        session_id=session_id,
        reason=reason,
        chunk_ids=chunk_ids or [],
    )


def refresh_memory_indexes(*, lane: str = 'assistant', project_id: str = '', session_id: str = '', force: bool = False) -> dict[str, Any]:
    """Refresh the active memory backend from SQLite and clear dirty state.

    This is intentionally coarse for safety: the active backend reindexes from
    SQLite, while dirty scopes keep the operation project-aware for diagnostics.
    When a true per-chunk vector backend lands, this function is the single place
    to swap from full lane reindex to incremental chunk upsert.
    """
    clean_lane = _clean(lane or 'assistant', 40)
    with _LOCK:
        _LAST_REFRESH.update({
            'ok': True,
            'state': 'refreshing',
            'message': 'Refreshing memory index...',
            'updated_at': _now_iso(),
        })
    dirty = consume_dirty_scopes(lane=clean_lane, project_id=project_id, session_id=session_id)
    if not dirty and not force:
        with _LOCK:
            _LAST_REFRESH.update({
                'ok': True,
                'state': 'synced',
                'message': 'Memory index is already synced.',
                'updated_at': _now_iso(),
                'refreshed_count': 0,
            })
        return memory_index_state()

    reindex_ok = False
    reindex_error = ''
    try:
        from .memory_service.chroma_store import reindex_active_backend_from_sqlite
        reindex_active_backend_from_sqlite(lane=clean_lane)
        reindex_ok = True
    except Exception as exc:  # keep retrieval usable even if vector refresh fails
        reindex_error = str(exc) or exc.__class__.__name__

    with _LOCK:
        _LAST_REFRESH.update({
            'ok': bool(reindex_ok),
            'state': 'synced' if reindex_ok else 'dirty',
            'message': 'Memory index refreshed.' if reindex_ok else 'Memory refresh failed; restart or run manual reindex.',
            'updated_at': _now_iso(),
            'refreshed_count': len(dirty),
            'project_id': _clean(project_id, 120),
            'session_id': _clean(session_id, 120),
            'error': reindex_error,
        })
        if not reindex_ok:
            # put scopes back when refresh failed
            for row in dirty:
                scope = MemoryDirtyScope(
                    lane=row.get('lane') or clean_lane,
                    project_id=row.get('project_id') or '',
                    session_id=row.get('session_id') or '',
                    scope_type=row.get('scope_type') or '',
                    scope_id=row.get('scope_id') or '',
                    reason=row.get('reason') or 'refresh_failed',
                    source_ref=row.get('source_ref') or '',
                    chunk_ids=row.get('chunk_ids') if isinstance(row.get('chunk_ids'), list) else [],
                )
                _DIRTY[scope.key()] = scope
    state = memory_index_state()
    state['refresh_attempt'] = {
        'ok': reindex_ok,
        'error': reindex_error,
        'dirty_scopes_consumed': dirty,
        'force': bool(force),
    }
    return state


def refresh_after_memory_write(*, lane: str = 'assistant', project_id: str = '', session_id: str = '', reason: str = 'memory_write', chunk_ids: list[str] | None = None, auto_refresh: bool = True) -> dict[str, Any]:
    dirty = invalidate_memory_caches(lane=lane, project_id=project_id, session_id=session_id, reason=reason, chunk_ids=chunk_ids or [])
    if not auto_refresh:
        return {'ok': True, 'dirty': dirty, 'index_state': memory_index_state(), 'refreshed': False}
    refreshed = refresh_memory_indexes(lane=lane, project_id=project_id, session_id=session_id)
    return {'ok': True, 'dirty': dirty, 'index_state': refreshed, 'refreshed': True}
