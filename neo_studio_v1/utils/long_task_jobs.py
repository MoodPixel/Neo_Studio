from __future__ import annotations

import time
from uuid import uuid4
from typing import Any

_TASKS: dict[str, dict[str, dict[str, Any]]] = {}
_DEFAULT_MAX_AGE_SEC = 60 * 60


def _bucket(namespace: str) -> dict[str, dict[str, Any]]:
    key = str(namespace or 'default').strip() or 'default'
    if key not in _TASKS:
        _TASKS[key] = {}
    return _TASKS[key]


def cleanup_long_tasks(namespace: str, max_age_sec: int = _DEFAULT_MAX_AGE_SEC) -> int:
    store = _bucket(namespace)
    cutoff = time.time() - max(60, int(max_age_sec or _DEFAULT_MAX_AGE_SEC))
    dead = [job_id for job_id, row in store.items() if float(row.get('started_at') or 0) < cutoff]
    for job_id in dead:
        store.pop(job_id, None)
    return len(dead)


def create_long_task(namespace: str, payload: dict[str, Any] | None = None, *, prefix: str = 'task') -> dict[str, Any]:
    cleanup_long_tasks(namespace)
    row = dict(payload or {})
    row.setdefault('job_id', f"{prefix}_{uuid4().hex}")
    row.setdefault('state', 'queued')
    row.setdefault('started_at', time.time())
    _bucket(namespace)[str(row['job_id'])] = row
    return row


def get_long_task(namespace: str, job_id: str) -> dict[str, Any] | None:
    return _bucket(namespace).get(str(job_id or '').strip())


def update_long_task(namespace: str, job_id: str, updates: dict[str, Any] | None = None) -> dict[str, Any] | None:
    row = get_long_task(namespace, job_id)
    if not row:
        return None
    row.update(dict(updates or {}))
    return row
