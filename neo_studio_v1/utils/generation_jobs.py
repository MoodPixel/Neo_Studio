from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from ..contracts.job_records import (
    JOB_SCHEMA_VERSION,
    build_generation_job_record,
    merge_job_updates,
    normalize_job_record,
)
from .library_common import atomic_write_json, read_json_dict
from .library_constants import USER_DATA_DIR

GENERATION_STATE_PATH = USER_DATA_DIR / 'generation_jobs.json'
GENERATION_INPUT_DIR = USER_DATA_DIR / 'generation_inputs'


def ensure_generation_dirs() -> None:
    GENERATION_INPUT_DIR.mkdir(parents=True, exist_ok=True)


def _default_state() -> Dict[str, Any]:
    return {'schema_version': JOB_SCHEMA_VERSION, 'jobs': []}


def load_generation_state() -> Dict[str, Any]:
    data = read_json_dict(GENERATION_STATE_PATH)
    jobs = data.get('jobs') if isinstance(data.get('jobs'), list) else []
    normalized_jobs = [normalize_job_record(row) for row in jobs if isinstance(row, dict)]
    return {'schema_version': JOB_SCHEMA_VERSION, 'jobs': normalized_jobs}


def save_generation_state(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [normalize_job_record(row) for row in list(data.get('jobs') or []) if isinstance(row, dict)]
    payload = {'schema_version': JOB_SCHEMA_VERSION, 'jobs': rows}
    atomic_write_json(GENERATION_STATE_PATH, payload)
    return payload


def create_generation_job(*, payload: Dict[str, Any], backend_profile: Dict[str, Any], prompt_id: str = '', queue_number: int | None = None, compile_notes: list[str] | None = None, workflow_graph: Dict[str, Any] | None = None, prompt_id_ref: str = '', parent_job_id: str = '', retry_of_job_id: str = '', source_output_id: str = '') -> Dict[str, Any]:
    state = load_generation_state()
    job = build_generation_job_record(
        payload=payload,
        backend_profile=backend_profile,
        prompt_id=prompt_id,
        queue_number=queue_number,
        compile_notes=compile_notes,
        workflow_graph=workflow_graph,
        prompt_id_ref=prompt_id_ref,
        parent_job_id=parent_job_id,
        retry_of_job_id=retry_of_job_id,
        source_output_id=source_output_id,
    )
    jobs = list(state.get('jobs') or [])
    jobs.insert(0, job)
    state['jobs'] = jobs[:100]
    save_generation_state(state)
    return job


def get_generation_job(job_id: str) -> Dict[str, Any] | None:
    target = str(job_id or '').strip()
    if not target:
        return None
    for job in load_generation_state().get('jobs', []):
        if str(job.get('id') or '') == target:
            return normalize_job_record(job)
    return None


def update_generation_job(job_id: str, updates: Dict[str, Any]) -> Dict[str, Any] | None:
    target = str(job_id or '').strip()
    if not target:
        return None
    state = load_generation_state()
    jobs = list(state.get('jobs') or [])
    out = None
    for idx, job in enumerate(jobs):
        if str(job.get('id') or '') != target:
            continue
        merged = merge_job_updates(job, updates or {})
        jobs[idx] = merged
        out = merged
        break
    if out is None:
        return None
    state['jobs'] = jobs
    save_generation_state(state)
    return out


def list_generation_jobs(limit: int = 20) -> list[Dict[str, Any]]:
    rows = list(load_generation_state().get('jobs') or [])
    # Keep the run list ordered by submission time, not updated_at.
    # Background finalization can repeatedly touch an older/stuck job, which
    # used to push that stale job above the actual latest run and clear the
    # current batch thumbnail strip in the UI.
    rows.sort(key=lambda row: str(row.get('submitted_at') or row.get('created_at') or row.get('updated_at') or ''), reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]
