from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable
from uuid import uuid4

JOB_SCHEMA_VERSION = 2
JOB_KIND = 'neo_studio_job'
JOB_TYPE_GENERATION = 'generation'
FINAL_JOB_STATES = {'completed', 'failed', 'cancelled'}
STATUS_ALIASES = {
    'queued': 'queued',
    'running': 'running',
    'completed': 'completed',
    'error': 'failed',
    'failed': 'failed',
    'cancelled': 'cancelled',
}


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def infer_generation_family(payload: Dict[str, Any] | None) -> str:
    data = payload if isinstance(payload, dict) else {}
    explicit = str(data.get('family') or data.get('model_family') or '').strip().lower()
    if explicit:
        return explicit
    if str(data.get('model_source') or '').strip().lower() == 'gguf':
        return 'flux_gguf'
    if str(data.get('gguf_unet') or '').strip() or str(data.get('gguf_clip_primary') or '').strip() or str(data.get('gguf_clip_secondary') or '').strip():
        return 'flux_gguf'
    return 'sdxl_sd'


def normalize_job_status(value: str = '') -> str:
    clean = str(value or 'queued').strip().lower()
    return STATUS_ALIASES.get(clean, 'queued')


def normalize_job_output_refs(rows: Iterable[Dict[str, Any]] | None) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        clean = deepcopy(item)
        clean.setdefault('schema_version', 1)
        clean.setdefault('record_type', 'job_output_ref')
        clean.setdefault('media_type', 'image')
        clean.setdefault('status', 'saved')
        clean.setdefault('output_id', str(clean.get('saved_filename') or clean.get('filename') or '').strip())
        clean.setdefault('job_id', str(clean.get('saved_from_job_id') or clean.get('job_id') or '').strip())
        clean.setdefault('lineage', {
            'job_id': clean.get('job_id') or '',
            'parent_job_id': str(clean.get('parent_job_id') or '').strip(),
            'source_output_id': str(clean.get('source_output_id') or '').strip(),
            'retry_of_job_id': str(clean.get('retry_of_job_id') or '').strip(),
        })
        out.append(clean)
    return out


def build_generation_job_record(*, payload: Dict[str, Any], backend_profile: Dict[str, Any], prompt_id: str = '', queue_number: int | None = None, compile_notes: list[str] | None = None, workflow_graph: Dict[str, Any] | None = None, prompt_id_ref: str = '', parent_job_id: str = '', retry_of_job_id: str = '', source_output_id: str = '') -> Dict[str, Any]:
    now = _now_iso()
    family = infer_generation_family(payload)
    backend_profile_id = str(backend_profile.get('id') or backend_profile.get('profile_id') or '').strip()
    job_id = f'gen_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:8]}'
    job = {
        'schema_version': JOB_SCHEMA_VERSION,
        'kind': JOB_KIND,
        'job_type': JOB_TYPE_GENERATION,
        'id': job_id,
        'job_id': job_id,
        'surface': 'generate',
        'family': family,
        'media_type': 'image',
        'created_at': now,
        'updated_at': now,
        'submitted_at': now,
        'started_at': '',
        'finished_at': '',
        'state': 'queued',
        'status': 'queued',
        'status_text': 'Queued in ComfyUI.',
        'progress': {'percent': 0, 'detail': 'Queued'},
        'backend_profile_id': backend_profile_id,
        'backend_type': str(backend_profile.get('backend_type') or backend_profile.get('adapter') or 'comfyui'),
        'backend_name': str(backend_profile.get('name') or backend_profile.get('label') or ''),
        'backend_url': str(backend_profile.get('base_url') or ''),
        'prompt_id': prompt_id,
        'prompt_ref_id': prompt_id_ref,
        'queue_number': queue_number,
        'payload': deepcopy(payload),
        'compile_notes': list(compile_notes or []),
        'workflow_graph': deepcopy(workflow_graph) if isinstance(workflow_graph, dict) else {},
        'outputs': [],
        'output_ids': [],
        'error': '',
        'error_message': '',
        'lineage': {
            'job_id': job_id,
            'parent_job_id': str(parent_job_id or '').strip(),
            'retry_of_job_id': str(retry_of_job_id or '').strip(),
            'source_output_id': str(source_output_id or '').strip(),
        },
    }
    return job


def normalize_job_record(record: Dict[str, Any] | None) -> Dict[str, Any]:
    row = deepcopy(record) if isinstance(record, dict) else {}
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    state = str(row.get('state') or row.get('status') or 'queued').strip().lower() or 'queued'
    status = normalize_job_status(state)
    created_at = str(row.get('created_at') or row.get('submitted_at') or _now_iso())
    updated_at = str(row.get('updated_at') or created_at)
    outputs = normalize_job_output_refs(row.get('outputs'))
    output_ids = [str(item.get('output_id') or '').strip() for item in outputs if str(item.get('output_id') or '').strip()]
    progress = row.get('progress') if isinstance(row.get('progress'), dict) else {}
    percent = progress.get('percent')
    if percent is None:
        if status == 'completed':
            percent = 100
        elif status == 'running':
            percent = 50
        else:
            percent = 0
    family = str(row.get('family') or '').strip() or infer_generation_family(payload)
    job_id = str(row.get('job_id') or row.get('id') or '').strip() or f'gen_legacy_{uuid4().hex[:8]}'
    started_at = str(row.get('started_at') or '')
    finished_at = str(row.get('finished_at') or '')
    if status == 'running' and not started_at:
        started_at = updated_at or created_at
    if status in FINAL_JOB_STATES and not finished_at:
        finished_at = updated_at or created_at
    error_message = str(row.get('error_message') or row.get('error') or '').strip()
    lineage = row.get('lineage') if isinstance(row.get('lineage'), dict) else {}
    normalized = {
        'schema_version': JOB_SCHEMA_VERSION,
        'kind': JOB_KIND,
        'job_type': str(row.get('job_type') or JOB_TYPE_GENERATION),
        'id': job_id,
        'job_id': job_id,
        'surface': str(row.get('surface') or 'generate'),
        'family': family,
        'media_type': str(row.get('media_type') or 'image'),
        'created_at': created_at,
        'updated_at': updated_at,
        'submitted_at': str(row.get('submitted_at') or created_at),
        'started_at': started_at,
        'finished_at': finished_at,
        'state': state,
        'status': status,
        'status_text': str(row.get('status_text') or ''),
        'progress': {
            'percent': max(0, min(100, int(percent or 0))),
            'detail': str(progress.get('detail') or row.get('status_text') or '').strip(),
        },
        'backend_profile_id': str(row.get('backend_profile_id') or '').strip(),
        'backend_type': str(row.get('backend_type') or ''),
        'backend_name': str(row.get('backend_name') or ''),
        'backend_url': str(row.get('backend_url') or ''),
        'prompt_id': str(row.get('prompt_id') or ''),
        'prompt_ref_id': str(row.get('prompt_ref_id') or row.get('prompt_id') or ''),
        'queue_number': row.get('queue_number'),
        'payload': payload,
        'compile_notes': list(row.get('compile_notes') or []),
        'workflow_graph': deepcopy(row.get('workflow_graph') or {}) if isinstance(row.get('workflow_graph'), dict) else {},
        'outputs': outputs,
        'output_ids': output_ids,
        'error': error_message,
        'error_message': error_message,
        'lineage': {
            'job_id': job_id,
            'parent_job_id': str(lineage.get('parent_job_id') or row.get('parent_job_id') or '').strip(),
            'retry_of_job_id': str(lineage.get('retry_of_job_id') or row.get('retry_of_job_id') or '').strip(),
            'source_output_id': str(lineage.get('source_output_id') or row.get('source_output_id') or '').strip(),
        },
    }
    return normalized


def merge_job_updates(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(existing)
    merged.update(deepcopy(updates or {}))
    merged['updated_at'] = _now_iso()
    outputs = merged.get('outputs') if isinstance(merged.get('outputs'), list) else []
    merged['outputs'] = normalize_job_output_refs(outputs)
    merged['output_ids'] = [str(item.get('output_id') or '').strip() for item in merged['outputs'] if str(item.get('output_id') or '').strip()]
    state = str(merged.get('state') or merged.get('status') or 'queued').strip().lower() or 'queued'
    merged['state'] = state
    merged['status'] = normalize_job_status(state)
    error_message = str(merged.get('error_message') or merged.get('error') or '').strip()
    merged['error'] = error_message
    merged['error_message'] = error_message
    progress = merged.get('progress') if isinstance(merged.get('progress'), dict) else {}
    if not progress:
        progress = {'percent': 100 if merged['status'] == 'completed' else (50 if merged['status'] == 'running' else 0), 'detail': str(merged.get('status_text') or '').strip()}
    merged['progress'] = progress
    if merged['status'] == 'running' and not str(merged.get('started_at') or '').strip():
        merged['started_at'] = merged['updated_at']
    if merged['status'] in FINAL_JOB_STATES and not str(merged.get('finished_at') or '').strip():
        merged['finished_at'] = merged['updated_at']
    return normalize_job_record(merged)
