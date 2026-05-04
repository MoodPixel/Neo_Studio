from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
import mimetypes

import httpx
import websockets
from uuid import uuid4

from fastapi import APIRouter, Form, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from ..contracts import (
    build_video_contract_boot_payload,
    build_video_job_record,
    build_video_result_record,
    normalize_video_advanced_adapters,
    normalize_video_backend_assets,
    normalize_video_mode,
    normalize_video_profile,
    normalize_video_post_processes,
    normalize_video_post_pipeline_template,
    match_video_post_pipeline_template,
    get_video_post_pipeline_steps,
    get_video_post_pipeline_label,
    validate_video_request,
)
from ..utils.backend_manager import get_manager_state, get_profile
from ..utils.comfy_adapter import ComfyBackendAdapter
from ..utils.comfy_workflows import build_video_balanced_workflow, build_video_balanced_wrapper_workflow, build_video_quality_workflow
from ..utils.generation_jobs import (
    GENERATION_INPUT_DIR,
    create_generation_job,
    ensure_generation_dirs,
    get_generation_job,
    list_generation_jobs,
    update_generation_job,
)
from ..utils.library_common import atomic_write_json, read_json_dict, safe_name
from ..utils.library_constants import USER_DATA_DIR
from ..utils.logging_utils import get_logger
from ..utils.video_upscale_jobs import (
    VIDEO_UPSCALE_PROFILES,
    VIDEO_UPSCALE_TARGETS,
    cancel_local_video_upscale_job,
    normalize_video_upscale_payload,
    probe_video,
    save_upscale_input_video,
    spawn_video_upscale_process,
    sync_local_video_upscale_job,
    validate_video_upscale_payload,
)
from ..utils.video_repair_jobs import (
    VIDEO_REPAIR_FOCUS,
    VIDEO_REPAIR_STRENGTHS,
    cancel_local_video_repair_job,
    normalize_video_repair_payload,
    save_repair_input_video,
    spawn_video_repair_process,
    sync_local_video_repair_job,
    validate_video_repair_payload,
)
from ..utils.video_interpolate_jobs import (
    VIDEO_INTERPOLATE_PRESETS,
    VIDEO_INTERPOLATE_QUALITY_MODES,
    VIDEO_INTERPOLATE_TIMING_INTENTS,
    cancel_local_video_interpolate_job,
    normalize_video_interpolate_payload,
    save_interpolate_input_video,
    spawn_video_interpolate_process,
    sync_local_video_interpolate_job,
    validate_video_interpolate_payload,
)
from ..utils.video_adapter_presets import (
    delete_video_adapter_preset,
    get_video_adapter_preset,
    list_video_adapter_presets,
    save_video_adapter_preset,
)
from ..utils.video_presets import (
    build_video_preset_summary,
    clear_default_video_preset,
    delete_video_preset,
    get_default_video_preset_id,
    get_video_preset,
    list_video_preset_categories,
    list_video_presets,
    save_video_preset,
    set_default_video_preset,
)
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


VIDEO_MANIFEST_DIR = USER_DATA_DIR / 'video_output_manifests'
VIDEO_PROMPT_SYNC_GRACE_SECONDS = 20
VIDEO_PROMPT_FINALIZATION_GRACE_SECONDS = 45


def _parse_iso_utc(value: str):
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except Exception:
        return None


def _job_age_seconds(job: dict) -> float:
    if not isinstance(job, dict):
        return 0.0
    candidate = (
        str(job.get('submitted_at') or '').strip()
        or str(job.get('created_at') or '').strip()
        or str(job.get('updated_at') or '').strip()
    )
    started = _parse_iso_utc(candidate)
    if started is None:
        return 0.0
    try:
        return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    except Exception:
        return 0.0


def _job_update_age_seconds(job: dict) -> float:
    if not isinstance(job, dict):
        return 0.0
    updated = _parse_iso_utc(str(job.get('updated_at') or '').strip())
    if updated is None:
        return _job_age_seconds(job)
    try:
        return max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())
    except Exception:
        return 0.0


def _queue_prompt_state(queue_payload, prompt_id: str) -> str | None:
    target = str(prompt_id or '').strip()
    if not target:
        return None

    def _contains_prompt(rows) -> bool:
        for row in rows or []:
            if isinstance(row, (list, tuple)):
                for item in row:
                    if str(item or '') == target:
                        return True
            elif isinstance(row, dict):
                if str(row.get('prompt_id') or '') == target:
                    return True
            elif str(row or '') == target:
                return True
        return False

    if isinstance(queue_payload, dict):
        if _contains_prompt(queue_payload.get('queue_running')):
            return 'running'
        if _contains_prompt(queue_payload.get('queue_pending')):
            return 'queued'
    return None


def _find_video_job_for_progress(client_id: str = '', prompt_id: str = '') -> dict | None:
    client = str(client_id or '').strip()
    prompt = str(prompt_id or '').strip()
    rows = [
        row for row in list_generation_jobs(limit=100)
        if str(row.get('surface') or '').strip() == 'video'
    ]
    rows.sort(key=lambda row: str(row.get('updated_at') or row.get('created_at') or ''), reverse=True)
    if prompt:
        prompt_rows = [row for row in rows if str(row.get('prompt_id') or '').strip() == prompt]
        if client:
            exact = [row for row in prompt_rows if str((row.get('payload') or {}).get('client_id') or '').strip() == client]
            if exact:
                return exact[0]
        if prompt_rows:
            return prompt_rows[0]
    if client:
        client_rows = [row for row in rows if str((row.get('payload') or {}).get('client_id') or '').strip() == client]
        if client_rows:
            return client_rows[0]
    return None


def _extract_video_ws_error_message(raw_data: dict | None) -> str:
    data = raw_data if isinstance(raw_data, dict) else {}
    parts: list[str] = []
    node_type = str(data.get('node_type') or '').strip()
    node_id = str(data.get('node_id') or data.get('node') or '').strip()
    exception_type = str(data.get('exception_type') or '').strip()
    exception_message = str(data.get('exception_message') or data.get('message') or '').strip()
    if node_type:
        parts.append(node_type)
    elif node_id:
        parts.append(f'Node {node_id}')
    if exception_type:
        parts.append(exception_type)
    if exception_message:
        parts.append(exception_message)
    summary = ' | '.join(part for part in parts if part)
    if summary:
        return summary
    details = data.get('traceback') if isinstance(data.get('traceback'), list) else []
    if details:
        return str(details[0]).strip()
    return 'ComfyUI reported an execution error while running the video workflow.'


def _apply_video_progress_event(client_id: str = '', message: dict | None = None) -> dict | None:
    packet = message if isinstance(message, dict) else {}
    event_type = str(packet.get('type') or '').strip().lower()
    raw_data = packet.get('data') if isinstance(packet.get('data'), dict) else packet
    if not event_type:
        return None
    prompt_id = str(raw_data.get('prompt_id') or packet.get('prompt_id') or '').strip()
    job = _find_video_job_for_progress(client_id=client_id, prompt_id=prompt_id)
    if not job:
        return None
    current_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    if current_state in {'failed', 'cancelled'} and event_type != 'execution_success':
        return job

    current_percent = int(((job.get('progress') or {}).get('percent') or 0) or 0)
    updates: dict | None = None
    if event_type == 'status':
        remaining = 0
        if isinstance(raw_data, dict):
            exec_info = raw_data.get('exec_info') if isinstance(raw_data.get('exec_info'), dict) else {}
            status_info = raw_data.get('status') if isinstance(raw_data.get('status'), dict) else {}
            nested_exec = status_info.get('exec_info') if isinstance(status_info.get('exec_info'), dict) else {}
            remaining = int(exec_info.get('queue_remaining') or nested_exec.get('queue_remaining') or 0)
        detail = f'Queued in ComfyUI ({remaining} remaining)' if remaining > 0 else 'Queued in ComfyUI'
        updates = {
            'state': 'queued' if current_state not in {'running', 'completed'} else current_state,
            'status_text': detail,
            'progress': {'percent': max(5, current_percent), 'detail': 'Waiting in queue'},
            'error': '',
        }
    elif event_type == 'execution_start':
        updates = {
            'state': 'running',
            'prompt_id': prompt_id or str(job.get('prompt_id') or ''),
            'status_text': 'Starting video generation in ComfyUI.',
            'progress': {'percent': max(4, current_percent), 'detail': 'Starting generation'},
            'error': '',
        }
    elif event_type == 'progress':
        value = int(raw_data.get('value') or packet.get('value') or 0)
        maximum = int(raw_data.get('max') or packet.get('max') or 0)
        pct = min(96, int((value / maximum) * 100)) if maximum > 0 else max(12, current_percent)
        updates = {
            'state': 'running',
            'status_text': f'Generating video in ComfyUI ({value}/{maximum or "?"}).',
            'progress': {'percent': pct, 'detail': f'Generating {value}/{maximum or "?"}'},
            'error': '',
        }
    elif event_type == 'executing':
        node = raw_data.get('node') if isinstance(raw_data, dict) else None
        if node is None:
            updates = {
                'state': 'running',
                'status_text': 'Backend execution finished. Waiting for output registration.',
                'progress': {'percent': max(97, current_percent), 'detail': 'Finalizing output'},
                'error': '',
            }
        else:
            updates = {
                'state': 'running',
                'status_text': f'Executing backend node {node}.',
                'progress': {'percent': max(15, current_percent), 'detail': f'Executing node {node}'},
                'error': '',
            }
    elif event_type == 'executed':
        updates = {
            'state': 'running',
            'status_text': 'Backend wrote a node result. Waiting for final output registration.',
            'progress': {'percent': max(90, current_percent), 'detail': 'Writing output'},
            'error': '',
        }
    elif event_type == 'execution_success':
        updates = {
            'state': 'running',
            'status_text': 'Backend execution finished. Waiting for history/output registration.',
            'progress': {'percent': max(99, current_percent), 'detail': 'Registering output'},
            'error': '',
        }
    elif event_type == 'execution_error':
        message_text = _extract_video_ws_error_message(raw_data)
        updates = {
            'state': 'failed',
            'status_text': 'Video generation failed in ComfyUI.',
            'error': message_text,
            'error_message': message_text,
            'progress': {'percent': max(1, current_percent), 'detail': 'Execution failed'},
        }
    elif event_type == 'execution_interrupted':
        updates = {
            'state': 'cancelled',
            'status_text': 'Video generation was interrupted in ComfyUI.',
            'error': '',
            'progress': {'percent': current_percent, 'detail': 'Interrupted'},
        }

    if not updates:
        return job
    updated = update_generation_job(job.get('job_id') or job.get('id') or '', updates) or job
    logger.info('Video progress event applied | type=%s | job_id=%s | prompt_id=%s | client_id=%s', event_type, updated.get('job_id') or updated.get('id') or '', prompt_id or updated.get('prompt_id') or '', client_id)
    return updated


def _video_profile_or_error():
    manager_state = get_manager_state()
    session = (manager_state.get('session') or {}).get('video') or {}
    if not session.get('connected'):
        return None, session, json_error('Connect the Video Backend first.', 400)
    profile = get_profile('video', session.get('profile_id') or None)
    if not profile:
        return None, session, json_error('Active Video Backend profile was not found.', 404)
    adapter = ComfyBackendAdapter(profile.get('base_url') or session.get('base_url') or '', timeout_sec=int(profile.get('timeout_sec') or 30))
    return adapter, session, None


VIDEO_POST_STAGE_LABELS = {
    'generate': 'Generate',
    'repair': 'Repair',
    'upscale': 'Upscale',
    'interpolate': 'Interpolate',
}


VIDEO_STATUS_LABELS = {
    'draft': 'Draft',
    'validating': 'Validating',
    'queued': 'Queued',
    'running': 'Running',
    'completed': 'Completed',
    'failed': 'Failed',
    'cancelled': 'Cancelled',
}


def _video_workflow_label(payload: dict | None) -> str:
    row = payload if isinstance(payload, dict) else {}
    workflow_type = str(row.get('workflow_type') or '').strip()
    if workflow_type == 'video_upscale':
        return 'Upscale lane'
    if workflow_type == 'video_repair':
        return 'Repair lane'
    if workflow_type == 'video_interpolate':
        return 'Interpolate lane'
    return 'Generation'


def _video_status_snapshot(job: dict | None) -> dict:
    row = job if isinstance(job, dict) else {}
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    status = str(row.get('status') or row.get('state') or 'queued').strip().lower() or 'queued'
    progress = row.get('progress') if isinstance(row.get('progress'), dict) else {}
    pipeline = _video_post_pipeline_summary(payload)
    workflow_label = _video_workflow_label(payload)
    current_stage_label = str(pipeline.get('current_stage_label') or workflow_label).strip() or workflow_label
    detail = str(progress.get('detail') or '').strip()
    if not detail:
        if status == 'running':
            detail = 'Rendering' if workflow_label == 'Generation' else f'Running {workflow_label.lower()}'
        elif status == 'queued':
            detail = 'Waiting in queue'
        elif status == 'completed':
            detail = 'Finished'
        elif status == 'cancelled':
            detail = 'Stopped'
        elif status == 'failed':
            detail = 'Failed'
        else:
            detail = VIDEO_STATUS_LABELS.get(status, status.title())
    return {
        'state': status,
        'state_label': VIDEO_STATUS_LABELS.get(status, status.title()),
        'workflow_label': workflow_label,
        'current_stage_label': current_stage_label,
        'progress_label': detail,
    }


def _current_video_stage(payload: dict | None) -> str:
    row = payload if isinstance(payload, dict) else {}
    workflow_type = str(row.get('workflow_type') or '').strip()
    if workflow_type == 'video_repair':
        return 'repair'
    if workflow_type == 'video_upscale':
        return 'upscale'
    if workflow_type == 'video_interpolate':
        return 'interpolate'
    return 'generate'



def _video_post_pipeline_summary(payload: dict | None) -> dict:
    row = payload if isinstance(payload, dict) else {}
    template_id = normalize_video_post_pipeline_template(row.get('post_pipeline_template') or match_video_post_pipeline_template(row.get('post_process')))
    steps = get_video_post_pipeline_steps(template_id, fallback_values=row.get('post_process'))
    current_stage = _current_video_stage(row)
    next_stage = ''
    if steps:
        if current_stage == 'generate':
            next_stage = steps[0]
        elif current_stage in steps:
            idx = steps.index(current_stage)
            next_stage = steps[idx + 1] if idx + 1 < len(steps) else ''
    dispatch = row.get('post_pipeline_dispatch') if isinstance(row.get('post_pipeline_dispatch'), dict) else {}
    return {
        'template_id': template_id,
        'label': get_video_post_pipeline_label(template_id, fallback_values=steps),
        'enabled': bool(steps),
        'steps': steps,
        'step_labels': [VIDEO_POST_STAGE_LABELS.get(item, item.title()) for item in steps],
        'current_stage': current_stage,
        'current_stage_label': VIDEO_POST_STAGE_LABELS.get(current_stage, current_stage.title()),
        'next_stage': next_stage,
        'next_stage_label': VIDEO_POST_STAGE_LABELS.get(next_stage, next_stage.title()) if next_stage else '',
        'next_job_id': str(dispatch.get('next_job_id') or '').strip(),
        'status': str(dispatch.get('status') or ('complete' if steps and not next_stage else 'pending' if steps else 'disabled')).strip() or 'disabled',
        'message': str(dispatch.get('message') or '').strip(),
        'root_job_id': str(row.get('post_pipeline_root_job_id') or dispatch.get('root_job_id') or '').strip(),
        'handoff_error': str(dispatch.get('error_message') or '').strip(),
    }



def _prepare_video_post_pipeline_payload(payload: dict | None, *, current_stage: str, root_job_id: str = '') -> dict:
    row = deepcopy(payload) if isinstance(payload, dict) else {}
    summary = _video_post_pipeline_summary(row)
    dispatch = row.get('post_pipeline_dispatch') if isinstance(row.get('post_pipeline_dispatch'), dict) else {}
    row['post_pipeline_template'] = summary['template_id']
    row['post_process'] = list(summary['steps'])
    if root_job_id or row.get('post_pipeline_root_job_id'):
        row['post_pipeline_root_job_id'] = str(root_job_id or row.get('post_pipeline_root_job_id') or '').strip()
    row['post_pipeline_dispatch'] = {
        'status': str(dispatch.get('status') or 'pending').strip() or 'pending',
        'current_stage': current_stage,
        'next_stage': summary['next_stage'] if current_stage == summary['current_stage'] else str(dispatch.get('next_stage') or '').strip(),
        'next_job_id': str(dispatch.get('next_job_id') or '').strip() if current_stage == str(dispatch.get('current_stage') or '').strip() else '',
        'message': str(dispatch.get('message') or '').strip() if current_stage == str(dispatch.get('current_stage') or '').strip() else '',
        'root_job_id': str(root_job_id or row.get('post_pipeline_root_job_id') or dispatch.get('root_job_id') or '').strip(),
        'error_message': str(dispatch.get('error_message') or '').strip() if current_stage == str(dispatch.get('current_stage') or '').strip() else '',
    }
    return row



def _select_video_output_ref(job: dict | None, preferred_output_id: str = '') -> dict | None:
    row = job if isinstance(job, dict) else {}
    outputs = [item for item in (row.get('outputs') or []) if isinstance(item, dict)]
    if not outputs:
        return None
    target_id = str(preferred_output_id or '').strip()
    selected = None
    if target_id:
        for item in outputs:
            if str(item.get('output_id') or item.get('filename') or '').strip() == target_id:
                selected = item
                break
    if selected is None:
        selected = outputs[0]
    if not isinstance(selected, dict):
        return None
    label = str(selected.get('filename') or selected.get('output_id') or 'video_output.mp4').strip() or 'video_output.mp4'
    return {
        'job_id': str(row.get('job_id') or row.get('id') or '').strip(),
        'output_id': str(selected.get('output_id') or selected.get('filename') or '').strip(),
        'filename': str(selected.get('filename') or '').strip(),
        'subfolder': str(selected.get('subfolder') or '').strip(),
        'type': str(selected.get('type') or '').strip(),
        'view_url': str(selected.get('view_url') or '').strip(),
        'local_path': str(selected.get('local_path') or '').strip(),
        'label': label,
    }



def _build_chained_stage_payload(source_job: dict, stage: str, source_output_ref: dict, pipeline: dict) -> dict:
    source_payload = deepcopy(source_job.get('payload') or {}) if isinstance(source_job.get('payload'), dict) else {}
    root_job_id = str(source_payload.get('post_pipeline_root_job_id') or pipeline.get('root_job_id') or source_job.get('job_id') or source_job.get('id') or '').strip()
    base = {
        **source_payload,
        'surface': 'video',
        'post_pipeline_template': pipeline.get('template_id') or 'generate_only',
        'post_process': list(pipeline.get('steps') or []),
        'post_pipeline_root_job_id': root_job_id,
        'post_pipeline_dispatch': {
            'status': 'pending',
            'current_stage': stage,
            'next_stage': '',
            'next_job_id': '',
            'message': '',
            'root_job_id': root_job_id,
            'error_message': '',
        },
    }
    source_label = str(source_output_ref.get('label') or source_output_ref.get('filename') or 'video_output.mp4').strip() or 'video_output.mp4'
    if stage == 'repair':
        base.update({
            'workflow_type': 'video_repair',
            'lane': 'repair',
            'repair_strength_preset': str(source_payload.get('repair_strength_preset') or 'balanced').strip() or 'balanced',
            'repair_cleanup_focus': str(source_payload.get('repair_cleanup_focus') or 'general_cleanup').strip() or 'general_cleanup',
            'stabilize_temporal': bool(source_payload.get('stabilize_temporal') if 'stabilize_temporal' in source_payload else source_payload.get('repair_stabilize_temporal')),
            'source_video_label': source_label,
            'source_output_ref': source_output_ref,
        })
        return base
    if stage == 'upscale':
        base.update({
            'workflow_type': 'video_upscale',
            'lane': 'upscale',
            'upscale_profile': str(source_payload.get('upscale_profile') or 'fast_local').strip() or 'fast_local',
            'target_resolution': str(source_payload.get('upscale_target_resolution') or source_payload.get('target_resolution') or '1920x1080').strip() or '1920x1080',
            'fps_mode': str(source_payload.get('upscale_fps_mode') or source_payload.get('fps_mode') or 'preserve').strip() or 'preserve',
            'output_fps': source_payload.get('upscale_output_fps') or source_payload.get('output_fps') or 24,
            'output_container': str(source_payload.get('upscale_output_container') or source_payload.get('output_container') or 'mp4').strip() or 'mp4',
            'output_codec': str(source_payload.get('upscale_output_codec') or source_payload.get('output_codec') or 'auto').strip() or 'auto',
            'source_video_label': source_label,
            'source_output_ref': source_output_ref,
        })
        return base
    if stage == 'interpolate':
        base.update({
            'workflow_type': 'video_interpolate',
            'lane': 'interpolate',
            'interpolation_preset': str(source_payload.get('interpolation_preset') or '').strip(),
            'target_fps': source_payload.get('interpolate_target_fps') or source_payload.get('target_fps') or 30,
            'interpolation_multiplier': source_payload.get('interpolate_multiplier') or source_payload.get('interpolation_multiplier') or 2,
            'motion_quality_mode': str(source_payload.get('interpolate_quality_mode') or source_payload.get('motion_quality_mode') or 'balanced').strip() or 'balanced',
            'timing_intent': str(source_payload.get('interpolate_timing_intent') or source_payload.get('timing_intent') or 'preserve_timing').strip() or 'preserve_timing',
            'source_video_label': source_label,
            'source_output_ref': source_output_ref,
        })
        return base
    raise ValueError(f'Unsupported chained stage: {stage}')



async def _queue_video_post_stage_from_job(source_job: dict, stage: str, source_output_ref: dict, pipeline: dict) -> dict:
    stage_payload = _build_chained_stage_payload(source_job, stage, source_output_ref, pipeline)
    if stage == 'repair':
        prepared = await _prepare_video_repair_source(stage_payload, None)
        queued = await _queue_video_repair_job(prepared)
    elif stage == 'upscale':
        prepared = await _prepare_video_upscale_source(stage_payload, None)
        queued = await _queue_video_upscale_job(prepared)
    elif stage == 'interpolate':
        prepared = await _prepare_video_interpolate_source(stage_payload, None)
        queued = await _queue_video_interpolate_job(prepared)
    else:
        raise ValueError(f'Unsupported chained stage: {stage}')
    next_job = queued.get('job') if isinstance(queued, dict) else None
    if isinstance(next_job, dict):
        note = f"Chained from {VIDEO_POST_STAGE_LABELS.get(_current_video_stage(source_job.get('payload') or {}), 'Generate')} as part of {pipeline.get('label') or 'Generate only'}."
        compile_notes = list(next_job.get('compile_notes') or [])
        if note not in compile_notes:
            compile_notes.insert(0, note)
            next_job = update_generation_job(next_job.get('job_id') or next_job.get('id') or '', {'compile_notes': compile_notes}) or next_job
    return {'job': next_job}



async def _maybe_dispatch_video_post_pipeline(job: dict | None) -> tuple[dict | None, dict | None, str]:
    if not isinstance(job, dict):
        return None, None, ''
    status = str(job.get('status') or job.get('state') or '').strip().lower()
    if status != 'completed':
        return job, None, ''
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    pipeline = _video_post_pipeline_summary(payload)
    if not pipeline.get('enabled'):
        return job, None, ''
    dispatch = payload.get('post_pipeline_dispatch') if isinstance(payload.get('post_pipeline_dispatch'), dict) else {}
    existing_next_job_id = str(dispatch.get('next_job_id') or '').strip()
    if existing_next_job_id:
        return job, get_generation_job(existing_next_job_id), str(dispatch.get('message') or '').strip()
    if not pipeline.get('next_stage'):
        if str(dispatch.get('status') or '').strip() != 'complete':
            new_payload = deepcopy(payload)
            new_payload['post_pipeline_dispatch'] = {
                'status': 'complete',
                'current_stage': pipeline.get('current_stage') or '',
                'next_stage': '',
                'next_job_id': '',
                'message': 'Chained post pipeline finished.',
                'root_job_id': str(new_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or '').strip(),
                'error_message': '',
            }
            compile_notes = list(job.get('compile_notes') or [])
            if 'Chained post pipeline finished.' not in compile_notes:
                compile_notes.append('Chained post pipeline finished.')
            job = update_generation_job(job.get('job_id') or job.get('id') or '', {
                'payload': new_payload,
                'compile_notes': compile_notes,
            }) or job
        return job, None, 'Chained post pipeline finished.'
    source_output_ref = _select_video_output_ref(job)
    if not source_output_ref:
        return job, None, ''
    try:
        queued = await _queue_video_post_stage_from_job(job, pipeline['next_stage'], source_output_ref, pipeline)
        next_job = queued.get('job') if isinstance(queued, dict) else None
    except Exception as exc:
        logger.warning('Could not queue chained video post stage %s for %s | %s', pipeline.get('next_stage'), job.get('job_id') or job.get('id') or '', exc)
        new_payload = deepcopy(payload)
        new_payload['post_pipeline_dispatch'] = {
            'status': 'handoff_failed',
            'current_stage': pipeline.get('current_stage') or '',
            'next_stage': pipeline.get('next_stage') or '',
            'next_job_id': '',
            'message': '',
            'root_job_id': str(new_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or '').strip(),
            'error_message': str(exc),
        }
        compile_notes = list(job.get('compile_notes') or [])
        handoff_note = f"Chained {pipeline.get('next_stage_label') or 'next lane'} could not be queued: {exc}"
        if handoff_note not in compile_notes:
            compile_notes.append(handoff_note)
        job = update_generation_job(job.get('job_id') or job.get('id') or '', {
            'payload': new_payload,
            'compile_notes': compile_notes,
        }) or job
        return job, None, ''
    if not isinstance(next_job, dict):
        return job, None, ''
    message = f"Chained {pipeline.get('next_stage_label') or pipeline.get('next_stage') or 'next stage'} queued next."
    new_payload = deepcopy(payload)
    new_payload['post_pipeline_dispatch'] = {
        'status': 'dispatched',
        'current_stage': pipeline.get('current_stage') or '',
        'next_stage': pipeline.get('next_stage') or '',
        'next_job_id': str(next_job.get('job_id') or next_job.get('id') or '').strip(),
        'message': message,
        'root_job_id': str(new_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or '').strip(),
        'error_message': '',
    }
    compile_notes = list(job.get('compile_notes') or [])
    if message not in compile_notes:
        compile_notes.append(message)
    job = update_generation_job(job.get('job_id') or job.get('id') or '', {
        'payload': new_payload,
        'compile_notes': compile_notes,
    }) or job
    return job, next_job, message


async def _save_upload(upload: UploadFile | None, prefix: str) -> dict | None:
    if not upload:
        return None
    raw = await upload.read()
    if not raw:
        return None
    ensure_generation_dirs()
    stem = safe_name(Path(upload.filename or prefix).stem) or prefix
    suffix = Path(upload.filename or '').suffix[:12]
    filename = f'{prefix}_{uuid4().hex[:8]}_{stem}{suffix}'
    target = GENERATION_INPUT_DIR / filename
    target.write_bytes(raw)
    return {
        'path': target,
        'filename': target.name,
        'content': raw,
    }


def _remote_path_from_upload_result(remote: dict, fallback_filename: str) -> str:
    remote_name = str(remote.get('name') or fallback_filename)
    remote_subfolder = str(remote.get('subfolder') or 'neo_studio').strip('/')
    return f'{remote_subfolder}/{remote_name}' if remote_subfolder else remote_name


async def _upload_saved(adapter: ComfyBackendAdapter, saved: dict | None) -> str:
    if not saved:
        return ''
    remote = await adapter.upload_image(saved['content'], saved['filename'])
    return _remote_path_from_upload_result(remote, saved['filename'])


def _extract_history_videos(history_entry: dict | None, adapter: ComfyBackendAdapter, payload: dict | None = None) -> list[dict]:
    outputs: list[dict] = []
    job_payload = payload if isinstance(payload, dict) else {}
    duration_seconds = job_payload.get('duration_seconds')
    fps = job_payload.get('fps')
    size_preset = str(job_payload.get('size_preset') or '').strip()
    if not isinstance(history_entry, dict):
        return outputs
    for node_data in (history_entry.get('outputs') or {}).values():
        if not isinstance(node_data, dict):
            continue
        for key in ('videos', 'gifs'):
            for item in node_data.get(key) or []:
                if not isinstance(item, dict) or not item.get('filename'):
                    continue
                filename = str(item.get('filename') or '').strip()
                subfolder = str(item.get('subfolder') or '').strip()
                file_type = str(item.get('type') or 'output').strip() or 'output'
                media_type = 'video' if key == 'videos' else 'animated'
                outputs.append({
                    'schema_version': 1,
                    'record_type': 'job_output_ref',
                    'output_id': filename,
                    'job_id': '',
                    'media_type': media_type,
                    'status': 'remote',
                    'filename': filename,
                    'subfolder': subfolder,
                    'type': file_type,
                    'view_url': adapter.build_view_url(filename, subfolder, file_type),
                    'duration_seconds': duration_seconds,
                    'fps': fps,
                    'size_preset': size_preset,
                })
    return outputs


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _video_runtime_guardrails(payload: dict | None) -> dict:
    row = payload if isinstance(payload, dict) else {}
    workflow_type = str(row.get('workflow_type') or '').strip()
    if workflow_type == 'video_upscale':
        return _video_upscale_runtime_guardrails(row)
    if workflow_type == 'video_repair':
        return _video_repair_runtime_guardrails(row)
    if workflow_type == 'video_interpolate':
        return _video_interpolate_runtime_guardrails(row)
    mode = normalize_video_mode(row.get('mode') or '')
    profile = normalize_video_profile(row.get('profile') or '', mode=mode)
    duration = max(1, _coerce_int(row.get('duration_seconds') or row.get('duration') or 5, 5))
    fps = max(1, _coerce_int(row.get('fps') or 16, 16))
    size = str(row.get('size_preset') or row.get('size') or '832x480').strip() or '832x480'
    quality = profile != 'wan22_5b_balanced'

    score = 0
    if quality:
        score += 3
    if mode == 'i2v':
        score += 1
    if duration >= 8:
        score += 1
    if duration >= 12:
        score += 1
    if fps >= 20:
        score += 1
    if fps >= 24:
        score += 1
    if size in {'1024x576', '576x1024'}:
        score += 1

    heaviness = 'heavy' if score >= 4 else ('medium' if score >= 2 else 'light')
    warnings: list[str] = []
    if not quality and heaviness in {'medium', 'heavy'}:
        warnings.append('This balanced request is no longer low-VRAM-safe. Shorter clips, 832 × 480, and 16 FPS are safer.')
    if quality:
        warnings.append('This will be slow on most single-GPU setups. Keep the clip short unless you know the backend can handle the 14B path.')
    if quality and duration > 5:
        warnings.append('High Quality clips longer than 5 seconds raise runtime cost and failure risk fast.')
    elif not quality and duration > 8:
        warnings.append('Balanced clips longer than 8 seconds are more likely to stall or feel slow on modest VRAM.')
    if fps >= 24:
        warnings.append('24 FPS is the heaviest shell cap in this build. Use it only when you actually need the smoother motion.')
    elif fps > 16:
        warnings.append('Higher FPS raises render cost. 16 FPS is the safer default for draft clips.')
    if size in {'1024x576', '576x1024'}:
        warnings.append('The larger resolution preset costs more VRAM and time than 832 × 480.')
    if mode == 'i2v' and quality:
        warnings.append('High Quality I2V keeps the start image anchored, but the heavier expert pair makes bad input images more expensive to fix.')

    slow_copy = {
        'light': 'This should stay in the lighter runtime lane if the backend is actually set up for Wan 2.2.',
        'medium': 'This is a medium-weight request. It should run, but it is no longer a casual low-VRAM draft.',
        'heavy': 'This is a heavy request. Expect a slower queue, longer runtime, and less forgiveness from the backend.',
    }[heaviness]
    return {
        'estimated_heaviness': heaviness,
        'warnings': warnings,
        'slow_copy': slow_copy,
    }




def _video_upscale_runtime_guardrails(payload: dict | None) -> dict:
    row = normalize_video_upscale_payload(payload if isinstance(payload, dict) else {})
    profile = str(row.get('upscale_profile') or 'fast_local').strip().lower() or 'fast_local'
    target = VIDEO_UPSCALE_TARGETS.get(str(row.get('target_resolution') or '1920x1080'), VIDEO_UPSCALE_TARGETS['1920x1080'])
    fps_mode = str(row.get('fps_mode') or 'preserve').strip().lower() or 'preserve'
    output_fps = max(8, _coerce_int(row.get('output_fps') or 24, 24))
    score = 0
    if profile == 'quality_conservative':
        score += 1
    if target['id'] == '1920x1080':
        score += 1
    elif target['id'] == '2560x1440':
        score += 2
    if fps_mode == 'custom' and output_fps >= 30:
        score += 1
    if fps_mode == 'custom' and output_fps >= 60:
        score += 1
    heaviness = 'heavy' if score >= 4 else ('medium' if score >= 2 else 'light')
    warnings: list[str] = []
    if profile == 'quality_conservative':
        warnings.append('Quality Conservative takes longer than Fast Local, but it stays in a preserve-first upscale lane instead of a creative rerender path.')
    if target['id'] == '2560x1440':
        warnings.append('1440p delivery asks more of local CPU / GPU and will be noticeably slower than 720p or 1080p.')
    if fps_mode == 'custom' and output_fps > 30:
        warnings.append('Raising FPS in the Upscale lane does not invent smoother motion. Keep preserve-FPS unless you truly need a delivery override.')
    if str(row.get('output_container') or 'mp4') == 'webm':
        warnings.append('WebM stays on the conservative auto codec path in this first Upscale lane.')
    slow_copy = {
        'light': 'This Upscale request should stay in the lighter local lane.',
        'medium': 'This Upscale request is medium-weight. It should run locally, but it will take longer than a casual draft pass.',
        'heavy': 'This Upscale request is heavy for a first conservative pass. Expect a slower local export and a larger delivery file.',
    }[heaviness]
    return {
        'estimated_heaviness': heaviness,
        'warnings': warnings,
        'slow_copy': slow_copy,
    }


def _video_repair_runtime_guardrails(payload: dict | None) -> dict:
    row = normalize_video_repair_payload(payload if isinstance(payload, dict) else {})
    strength = str(row.get('repair_strength_preset') or 'balanced').strip().lower() or 'balanced'
    focus = str(row.get('repair_cleanup_focus') or 'general_cleanup').strip().lower() or 'general_cleanup'
    stabilize = bool(row.get('stabilize_temporal'))
    source_probe = row.get('source_probe') if isinstance(row.get('source_probe'), dict) else {}
    duration_seconds = float(source_probe.get('duration_seconds') or 0.0)
    score = 0
    if strength == 'balanced':
        score += 1
    elif strength == 'aggressive':
        score += 2
    if focus == 'compression_cleanup':
        score += 1
    if stabilize:
        score += 1
    if duration_seconds >= 20:
        score += 1
    if duration_seconds >= 45:
        score += 1
    heaviness = 'heavy' if score >= 4 else ('medium' if score >= 2 else 'light')
    warnings: list[str] = []
    if strength == 'aggressive':
        warnings.append('Aggressive repair can over-smooth fine texture. Use it when the clip is genuinely broken, not just a little rough.')
    if focus == 'compression_cleanup':
        warnings.append('Compression cleanup leans harder into preserve-first smoothing to tame blockiness and mosquito noise.')
    if stabilize:
        warnings.append('Temporal stabilization is mild on purpose, but it still adds render time and can slightly crop or shift the frame.')
    if duration_seconds >= 45:
        warnings.append('Longer clips make local Repair noticeably slower. Split the clip when you only need to rescue part of it.')
    slow_copy = {
        'light': 'This Repair request should stay in the lighter local cleanup lane.',
        'medium': 'This Repair request is medium-weight. It should still stay local, but the preserve-first cleanup pass will take a while.',
        'heavy': 'This Repair request is heavy for a local rescue pass. Expect a slower export, especially if stabilization is enabled.',
    }[heaviness]
    return {
        'estimated_heaviness': heaviness,
        'warnings': warnings,
        'slow_copy': slow_copy,
    }


def _video_interpolate_runtime_guardrails(payload: dict | None) -> dict:
    row = normalize_video_interpolate_payload(payload if isinstance(payload, dict) else {})
    source_probe = row.get('source_probe') if isinstance(row.get('source_probe'), dict) else {}
    source_fps = float(source_probe.get('fps') or 0.0)
    target_fps = max(8, _coerce_int(row.get('target_fps') or row.get('resolved_target_fps') or 30, 30))
    multiplier = float(row.get('resolved_multiplier') or row.get('interpolation_multiplier') or 2.0)
    quality_mode = str(row.get('motion_quality_mode') or 'balanced').strip().lower() or 'balanced'
    timing_intent = str(row.get('timing_intent') or 'preserve_timing').strip().lower() or 'preserve_timing'
    duration_seconds = float(row.get('resolved_output_duration_seconds') or source_probe.get('duration_seconds') or 0.0)
    score = 0
    if quality_mode == 'smooth':
        score += 1
    elif quality_mode == 'detail_safe':
        score += 2
    if target_fps >= 30:
        score += 1
    if target_fps >= 48:
        score += 1
    if target_fps >= 60:
        score += 1
    if timing_intent == 'slow_motion':
        score += 1
    if duration_seconds >= 20:
        score += 1
    if duration_seconds >= 45:
        score += 1
    heaviness = 'heavy' if score >= 5 else ('medium' if score >= 2 else 'light')
    warnings: list[str] = []
    if source_fps and target_fps <= source_fps:
        warnings.append(f'Interpolate only helps when the target FPS is higher than the source clip ({source_fps:.2f} FPS).')
    if target_fps >= 60:
        warnings.append('60 FPS interpolation is the heaviest delivery path in this lane. Use it when the smoother motion is worth the extra export time.')
    elif target_fps >= 30:
        warnings.append('Higher target FPS adds render time fast. Stay closer to the original clip unless you really need a smoother deliverable.')
    if timing_intent == 'slow_motion':
        warnings.append('Slow motion stretches the clip length. Audio is time-stretched to match, so expect a more processed result than Preserve timing.')
    if quality_mode == 'smooth':
        warnings.append('Smoother motion pushes harder on synthetic in-between frames. Great for choppy clips, but watch for edge warping on fast motion.')
    elif quality_mode == 'detail_safe':
        warnings.append('Detail Safe stays more conservative around cuts and texture, but it is the slowest local interpolation mode.')
    if source_fps and multiplier >= 2.5 and target_fps > source_fps * 2.5:
        warnings.append('This target FPS is much higher than the source clip. Expect diminishing returns if the original motion is already rough.')
    slow_copy = {
        'light': 'This Interpolate request should stay in the lighter local polish lane.',
        'medium': 'This Interpolate request is medium-weight. It should stay local, but higher FPS and smarter frame blending take time.',
        'heavy': 'This Interpolate request is heavy for a local polish pass. Expect a slower export, especially with slow motion or 60 FPS output.',
    }[heaviness]
    return {
        'estimated_heaviness': heaviness,
        'warnings': warnings,
        'slow_copy': slow_copy,
    }


def _local_video_output_response(path: Path) -> FileResponse:
    media_type = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type, filename=path.name)


async def _download_video_output_ref(source_output_ref: dict | None, *, save_func=save_upscale_input_video, prefix: str = 'upscale_output') -> dict | None:
    row = source_output_ref if isinstance(source_output_ref, dict) else {}
    local_path = Path(str(row.get('local_path') or '').strip()) if str(row.get('local_path') or '').strip() else None
    if local_path and local_path.exists():
        return {
            'path': local_path,
            'filename': local_path.name,
            'bytes': local_path.stat().st_size,
        }
    view_url = str(row.get('view_url') or '').strip()
    if not view_url:
        return None
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(view_url)
        response.raise_for_status()
        content = response.content
    source_name = str(row.get('filename') or 'video_output.mp4').strip() or 'video_output.mp4'
    return save_func(content, source_name, prefix=prefix)


async def _prepare_video_upscale_source(payload: dict, source_video_file: UploadFile | None = None) -> dict:
    clean = normalize_video_upscale_payload(payload)
    saved = None
    if source_video_file and hasattr(source_video_file, 'filename'):
        raw = await source_video_file.read()
        if raw:
            saved = save_upscale_input_video(raw, str(source_video_file.filename or 'source_video.mp4'), prefix='upscale_upload')
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(source_video_file.filename or saved['filename'])
    if not saved and clean.get('source_output_ref'):
        saved = await _download_video_output_ref(clean.get('source_output_ref'), save_func=save_upscale_input_video, prefix='upscale_output')
        if saved:
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or saved['filename'])
    errors = validate_video_upscale_payload(clean)
    if errors:
        raise ValueError(errors[0])
    probe = probe_video(clean.get('source_video_local_path') or clean.get('source_video') or '')
    clean['source_probe'] = probe
    if not clean.get('source_video_label'):
        clean['source_video_label'] = Path(str(clean.get('source_video_local_path') or clean.get('source_video') or 'source_video.mp4')).name
    return clean


async def _prepare_video_repair_source(payload: dict, source_video_file: UploadFile | None = None) -> dict:
    clean = normalize_video_repair_payload(payload)
    saved = None
    if source_video_file and hasattr(source_video_file, 'filename'):
        raw = await source_video_file.read()
        if raw:
            saved = save_repair_input_video(raw, str(source_video_file.filename or 'source_video.mp4'), prefix='repair_upload')
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(source_video_file.filename or saved['filename'])
    if not saved and clean.get('source_output_ref'):
        saved = await _download_video_output_ref(clean.get('source_output_ref'), save_func=save_repair_input_video, prefix='repair_output')
        if saved:
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or saved['filename'])
    errors = validate_video_repair_payload(clean)
    if errors:
        raise ValueError(errors[0])
    probe = probe_video(clean.get('source_video_local_path') or clean.get('source_video') or '')
    clean['source_probe'] = probe
    if not clean.get('source_video_label'):
        clean['source_video_label'] = Path(str(clean.get('source_video_local_path') or clean.get('source_video') or 'source_video.mp4')).name
    return clean


async def _prepare_video_interpolate_source(payload: dict, source_video_file: UploadFile | None = None) -> dict:
    clean = normalize_video_interpolate_payload(payload)
    saved = None
    if source_video_file and hasattr(source_video_file, 'filename'):
        raw = await source_video_file.read()
        if raw:
            saved = save_interpolate_input_video(raw, str(source_video_file.filename or 'source_video.mp4'), prefix='interpolate_upload')
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(source_video_file.filename or saved['filename'])
    if not saved and clean.get('source_output_ref'):
        saved = await _download_video_output_ref(clean.get('source_output_ref'), save_func=save_interpolate_input_video, prefix='interpolate_output')
        if saved:
            clean['source_video_local_path'] = str(saved['path'])
            clean['source_video'] = saved['filename']
            clean['source_video_label'] = str(clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or saved['filename'])
    errors = validate_video_interpolate_payload(clean)
    if errors:
        raise ValueError(errors[0])
    probe = probe_video(clean.get('source_video_local_path') or clean.get('source_video') or '')
    clean['source_probe'] = probe
    if not clean.get('source_video_label'):
        clean['source_video_label'] = Path(str(clean.get('source_video_local_path') or clean.get('source_video') or 'source_video.mp4')).name
    return clean


async def _queue_video_interpolate_job(payload: dict) -> dict:
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalize_video_interpolate_payload(payload),
        current_stage='interpolate',
        root_job_id=str((payload or {}).get('post_pipeline_root_job_id') or ''),
    )
    runtime = _video_interpolate_runtime_guardrails(normalized_payload)
    fake_profile = {
        'id': 'local_ffmpeg_video_interpolate',
        'backend_type': 'local_ffmpeg',
        'name': 'Local FFmpeg Interpolate',
        'base_url': '',
    }
    job = create_generation_job(
        payload=normalized_payload,
        backend_profile=fake_profile,
        prompt_id='',
        queue_number=None,
        compile_notes=[
            f"Interpolate lane will target {normalized_payload.get('target_fps')} FPS using {VIDEO_INTERPOLATE_QUALITY_MODES.get(normalized_payload.get('motion_quality_mode'), VIDEO_INTERPOLATE_QUALITY_MODES['balanced'])['label']} mode.",
            f"Timing intent: {VIDEO_INTERPOLATE_TIMING_INTENTS.get(normalized_payload.get('timing_intent'), VIDEO_INTERPOLATE_TIMING_INTENTS['preserve_timing'])['label']}.",
            'This lane is polish-first by design: smooth motion and standardize delivery FPS without rerendering the clip.',
        ],
        workflow_graph={},
        parent_job_id=str((normalized_payload.get('source_output_ref') or {}).get('job_id') or ''),
        source_output_id=str((normalized_payload.get('source_output_ref') or {}).get('output_id') or ''),
    )
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalized_payload,
        current_stage='interpolate',
        root_job_id=str(normalized_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or ''),
    )
    spawned_payload = spawn_video_interpolate_process(job_id=str(job.get('job_id') or job.get('id') or ''), payload=normalized_payload)
    job = update_generation_job(job.get('id') or job.get('job_id') or '', {
        'surface': 'video',
        'family': 'local_ffmpeg',
        'media_type': 'video',
        'state': 'running',
        'status_text': 'Running local Interpolate lane.',
        'progress': {'percent': 5, 'detail': 'Starting interpolation'},
        'payload': spawned_payload,
        'compile_notes': [
            f"Target FPS: {spawned_payload.get('resolved_target_fps')}",
            f"Effective multiplier: {spawned_payload.get('resolved_multiplier')}x",
            f"Quality mode: {VIDEO_INTERPOLATE_QUALITY_MODES.get(spawned_payload.get('motion_quality_mode'), VIDEO_INTERPOLATE_QUALITY_MODES['balanced'])['label']}",
            f"Timing intent: {VIDEO_INTERPOLATE_TIMING_INTENTS.get(spawned_payload.get('timing_intent'), VIDEO_INTERPOLATE_TIMING_INTENTS['preserve_timing'])['label']}",
            runtime['slow_copy'],
        ] + runtime.get('warnings', []),
        'error': '',
    }) or job
    return {
        'job': job,
        'normalized_payload': spawned_payload,
    }


async def _queue_video_repair_job(payload: dict) -> dict:
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalize_video_repair_payload(payload),
        current_stage='repair',
        root_job_id=str((payload or {}).get('post_pipeline_root_job_id') or ''),
    )
    runtime = _video_repair_runtime_guardrails(normalized_payload)
    fake_profile = {
        'id': 'local_ffmpeg_video_repair',
        'backend_type': 'local_ffmpeg',
        'name': 'Local FFmpeg Repair',
        'base_url': '',
    }
    job = create_generation_job(
        payload=normalized_payload,
        backend_profile=fake_profile,
        prompt_id='',
        queue_number=None,
        compile_notes=[
            f"Repair lane will run {VIDEO_REPAIR_STRENGTHS.get(normalized_payload.get('repair_strength_preset'), VIDEO_REPAIR_STRENGTHS['balanced'])['label']} cleanup with {VIDEO_REPAIR_FOCUS.get(normalized_payload.get('repair_cleanup_focus'), VIDEO_REPAIR_FOCUS['general_cleanup'])['label'].lower()}.",
            'This lane is preserve-first by design: fix, clean, and stabilize without pretending to regenerate the whole clip.',
        ],
        workflow_graph={},
        parent_job_id=str((normalized_payload.get('source_output_ref') or {}).get('job_id') or ''),
        source_output_id=str((normalized_payload.get('source_output_ref') or {}).get('output_id') or ''),
    )
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalized_payload,
        current_stage='repair',
        root_job_id=str(normalized_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or ''),
    )
    spawned_payload = spawn_video_repair_process(job_id=str(job.get('job_id') or job.get('id') or ''), payload=normalized_payload)
    job = update_generation_job(job.get('id') or job.get('job_id') or '', {
        'surface': 'video',
        'family': 'local_ffmpeg',
        'media_type': 'video',
        'state': 'running',
        'status_text': 'Running local Repair lane.',
        'progress': {'percent': 5, 'detail': 'Starting repair'},
        'payload': spawned_payload,
        'compile_notes': [
            f"Repair strength: {VIDEO_REPAIR_STRENGTHS.get(spawned_payload.get('repair_strength_preset'), VIDEO_REPAIR_STRENGTHS['balanced'])['label']}.",
            f"Cleanup focus: {VIDEO_REPAIR_FOCUS.get(spawned_payload.get('repair_cleanup_focus'), VIDEO_REPAIR_FOCUS['general_cleanup'])['label']}.",
            'Temporal stabilization: enabled.' if spawned_payload.get('stabilize_temporal') else 'Temporal stabilization: off.',
            runtime['slow_copy'],
        ] + runtime.get('warnings', []),
        'error': '',
    }) or job
    return {
        'job': job,
        'normalized_payload': spawned_payload,
    }


async def _queue_video_upscale_job(payload: dict) -> dict:
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalize_video_upscale_payload(payload),
        current_stage='upscale',
        root_job_id=str((payload or {}).get('post_pipeline_root_job_id') or ''),
    )
    runtime = _video_upscale_runtime_guardrails(normalized_payload)
    fake_profile = {
        'id': 'local_ffmpeg_video_upscale',
        'backend_type': 'local_ffmpeg',
        'name': 'Local FFmpeg Upscale',
        'base_url': '',
    }
    job = create_generation_job(
        payload=normalized_payload,
        backend_profile=fake_profile,
        prompt_id='',
        queue_number=None,
        compile_notes=[
            f"Upscale lane will export to {normalized_payload.get('target_resolution')} using {VIDEO_UPSCALE_PROFILES.get(normalized_payload.get('upscale_profile'), VIDEO_UPSCALE_PROFILES['fast_local'])['label']}.",
            'This lane is conservative by design: upscale first, do not rerender the motion.',
        ],
        workflow_graph={},
        parent_job_id=str((normalized_payload.get('source_output_ref') or {}).get('job_id') or ''),
        source_output_id=str((normalized_payload.get('source_output_ref') or {}).get('output_id') or ''),
    )
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalized_payload,
        current_stage='upscale',
        root_job_id=str(normalized_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or ''),
    )
    spawned_payload = spawn_video_upscale_process(job_id=str(job.get('job_id') or job.get('id') or ''), payload=normalized_payload)
    job = update_generation_job(job.get('id') or job.get('job_id') or '', {
        'surface': 'video',
        'family': 'local_ffmpeg',
        'media_type': 'video',
        'state': 'running',
        'status_text': 'Running local Upscale lane.',
        'progress': {'percent': 5, 'detail': 'Starting upscale'},
        'payload': spawned_payload,
        'compile_notes': [
            f"Upscale lane will export to {spawned_payload.get('resolved_output_width')}x{spawned_payload.get('resolved_output_height')} at {spawned_payload.get('resolved_fps')} FPS.",
            f"Profile: {VIDEO_UPSCALE_PROFILES.get(spawned_payload.get('upscale_profile'), VIDEO_UPSCALE_PROFILES['fast_local'])['label']}.",
            runtime['slow_copy'],
        ] + runtime.get('warnings', []),
        'error': '',
    }) or job
    return {
        'job': job,
        'normalized_payload': spawned_payload,
    }

def _video_manifest_path(job_id: str) -> Path:
    safe_job_id = safe_name(str(job_id or 'video_job').replace('/', '_')) or 'video_job'
    return VIDEO_MANIFEST_DIR / f'{safe_job_id}.json'


def _build_video_manifest(job: dict, outputs: list[dict]) -> dict:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    runtime = _video_runtime_guardrails(payload)
    workflow_type = str(payload.get('workflow_type') or 'video_generation').strip() or 'video_generation'
    request = {
        'prompt': str(payload.get('prompt') or '').strip(),
        'negative_prompt': str(payload.get('negative_prompt') or '').strip(),
        'source_image': str(payload.get('source_image') or '').strip(),
        'duration_seconds': payload.get('duration_seconds'),
        'fps': payload.get('fps'),
        'size_preset': str(payload.get('size_preset') or '').strip(),
        'seed': str(payload.get('seed') or '').strip(),
    }
    if workflow_type == 'video_upscale':
        request = {
            'source_video_label': str(payload.get('source_video_label') or '').strip(),
            'source_video_local_path': str(payload.get('source_video_local_path') or '').strip(),
            'target_resolution': str(payload.get('target_resolution') or '').strip(),
            'resolved_output_width': payload.get('resolved_output_width'),
            'resolved_output_height': payload.get('resolved_output_height'),
            'fps_mode': str(payload.get('fps_mode') or '').strip(),
            'output_fps': payload.get('resolved_fps') or payload.get('output_fps'),
            'output_container': str(payload.get('output_container') or '').strip(),
            'output_codec': str(payload.get('output_codec') or '').strip(),
            'upscale_profile': str(payload.get('upscale_profile') or '').strip(),
        }
    if workflow_type == 'video_repair':
        request = {
            'source_video_label': str(payload.get('source_video_label') or '').strip(),
            'source_video_local_path': str(payload.get('source_video_local_path') or '').strip(),
            'repair_strength_preset': str(payload.get('repair_strength_preset') or '').strip(),
            'repair_cleanup_focus': str(payload.get('repair_cleanup_focus') or '').strip(),
            'stabilize_temporal': bool(payload.get('stabilize_temporal')),
            'resolved_output_width': payload.get('resolved_output_width'),
            'resolved_output_height': payload.get('resolved_output_height'),
            'output_fps': payload.get('resolved_fps') or (payload.get('source_probe') or {}).get('fps'),
        }
    if workflow_type == 'video_interpolate':
        request = {
            'source_video_label': str(payload.get('source_video_label') or '').strip(),
            'source_video_local_path': str(payload.get('source_video_local_path') or '').strip(),
            'interpolation_preset': str(payload.get('interpolation_preset') or '').strip(),
            'target_fps': payload.get('resolved_target_fps') or payload.get('target_fps'),
            'interpolation_multiplier': payload.get('resolved_multiplier') or payload.get('interpolation_multiplier'),
            'motion_quality_mode': str(payload.get('motion_quality_mode') or '').strip(),
            'timing_intent': str(payload.get('timing_intent') or '').strip(),
            'resolved_output_width': payload.get('resolved_output_width'),
            'resolved_output_height': payload.get('resolved_output_height'),
            'resolved_output_duration_seconds': payload.get('resolved_output_duration_seconds'),
        }
    return {
        'schema_version': 1,
        'record_type': 'video_output_manifest',
        'job_id': str(job.get('job_id') or job.get('id') or '').strip(),
        'prompt_id': str(job.get('prompt_id') or '').strip(),
        'surface': 'video',
        'workflow_type': workflow_type,
        'lane': str(payload.get('lane') or ('upscale' if workflow_type == 'video_upscale' else 'repair' if workflow_type == 'video_repair' else 'interpolate' if workflow_type == 'video_interpolate' else 'generate')).strip(),
        'mode': normalize_video_mode(payload.get('mode') or ''),
        'profile': normalize_video_profile(payload.get('profile') or '', mode=payload.get('mode') or ''),
        'status': str(job.get('status') or job.get('state') or 'completed').strip().lower() or 'completed',
        'created_at': str(job.get('created_at') or ''),
        'updated_at': str(job.get('updated_at') or ''),
        'request': request,
        'runtime': runtime,
        'post_pipeline': _video_post_pipeline_summary(payload),
        'outputs': [
            {
                'output_id': str(item.get('output_id') or item.get('filename') or '').strip(),
                'filename': str(item.get('filename') or '').strip(),
                'media_type': str(item.get('media_type') or 'video').strip() or 'video',
                'view_url': str(item.get('view_url') or '').strip(),
                'subfolder': str(item.get('subfolder') or '').strip(),
                'type': str(item.get('type') or 'output').strip() or 'output',
                'duration_seconds': item.get('duration_seconds'),
                'fps': item.get('fps'),
                'size_preset': str(item.get('size_preset') or '').strip(),
            }
            for item in outputs if isinstance(item, dict)
        ],
    }


def _save_video_output_manifest(job: dict, outputs: list[dict]) -> Path:
    VIDEO_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = _video_manifest_path(job.get('job_id') or job.get('id') or '')
    atomic_write_json(path, _build_video_manifest(job, outputs))
    return path


def _extract_comfy_node_error_lines(node_errors) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def _push(value):
        clean = str(value or '').strip()
        if not clean:
            return
        if clean not in seen:
            out.append(clean)
            seen.add(clean)

    def _walk(value, *, prefix: str = ''):
        if value is None:
            return
        if isinstance(value, str):
            _push(f"{prefix}{value}" if prefix else value)
            return
        if isinstance(value, (int, float, bool)):
            _push(f"{prefix}{value}" if prefix else str(value))
            return
        if isinstance(value, list):
            for item in value:
                _walk(item, prefix=prefix)
            return
        if isinstance(value, dict):
            node_label = str(value.get('class_type') or value.get('type') or value.get('node_type') or '').strip()
            if node_label:
                _push(f"Node: {node_label}")
            for key in ('message', 'details', 'error', 'reason', 'detail'):
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip():
                    _push(raw)
            errors = value.get('errors')
            if isinstance(errors, list):
                for item in errors:
                    if isinstance(item, dict):
                        msg = str(item.get('message') or item.get('details') or item.get('error') or item.get('reason') or '').strip()
                        if msg:
                            _push(msg)
                    else:
                        _walk(item)
            for key, item in value.items():
                if key in {'errors', 'message', 'details', 'error', 'reason', 'detail', 'class_type', 'type', 'node_type'}:
                    continue
                if isinstance(item, (dict, list)):
                    _walk(item)
            return
        _push(str(value))

    _walk(node_errors)
    return out


def _summarize_video_node_errors(node_errors) -> str:
    lines = _extract_comfy_node_error_lines(node_errors)
    if not lines:
        return 'ComfyUI rejected the video workflow during node validation before the job entered queue/history.'
    important = lines[:4]
    summary = ' | '.join(important)
    return f'ComfyUI rejected the video workflow during node validation: {summary}'


def _plain_video_failure_message(job: dict) -> str:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    raw = str(job.get('error') or job.get('error_message') or job.get('status_text') or '').strip()
    lower = raw.lower()
    workflow_type = str(payload.get('workflow_type') or '').strip()
    if workflow_type == 'video_upscale' and raw:
        return raw
    if workflow_type == 'video_upscale' and not raw:
        return 'The local Upscale lane failed before a usable deliverable file was written.'
    if workflow_type == 'video_repair' and raw:
        return raw
    if workflow_type == 'video_repair' and not raw:
        return 'The local Repair lane failed before a repaired file was written.'
    if workflow_type == 'video_interpolate' and raw:
        return raw
    if workflow_type == 'video_interpolate' and not raw:
        return 'The local Interpolate lane failed before an interpolated file was written.'
    if 'cannot copy out of meta tensor' in lower:
        return (
            'Wan text encoder failed to load. '
            'The selected UMT5 encoder file is incomplete, corrupted, or mismatched '
            'for CLIPLoader type="wan". Replace the encoder with a clean official copy, '
            'refresh Video assets, and retry.'
        )
    if 'clip missing:' in lower or 'sd1clipmodel' in lower:
        return (
            'The backend loaded the wrong or an incomplete text encoder for the Wan video run. '
            'Reinstall the selected Wan UMT5 encoder and re-select it from the live asset list.'
        )
    if not raw:
        return 'The job failed before Neo got a useful backend error. Check the backend connection, model files, and the current video settings.'
    if 'source image' in lower:
        return 'Image to Video failed because the source image was missing or invalid.'
    if 'connect the video backend' in lower or 'backend first' in lower:
        return 'Video backend is offline. Reconnect it, then retry the job.'
    if 'prompt is required' in lower:
        return 'This job was missing the main prompt.'
    if 'timeout' in lower:
        return 'The backend took too long to answer. Try a shorter clip or reconnect the video backend.'
    return raw


def _enrich_video_job(job: dict | None) -> dict | None:
    if not isinstance(job, dict):
        return None
    row = deepcopy(job)
    payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
    status = str(row.get('status') or row.get('state') or 'queued').strip().lower() or 'queued'
    runtime = _video_runtime_guardrails(payload)
    outputs = [item for item in (row.get('outputs') or []) if isinstance(item, dict)]
    manifest_path = _video_manifest_path(row.get('job_id') or row.get('id') or '')
    manifest_exists = manifest_path.exists()
    row['video_runtime'] = {
        **runtime,
        'post_pipeline': _video_post_pipeline_summary(payload),
        'status_snapshot': _video_status_snapshot(row),
        'can_cancel': status in {'queued', 'running'},
        'can_retry': status in {'completed', 'failed', 'cancelled'},
        'output_count': len(outputs),
        'manifest_path': str(manifest_path) if manifest_exists else '',
        'manifest_url': f"/api/video/manifest/{row.get('job_id') or row.get('id') or ''}" if manifest_exists else '',
        'latest_output_url': str(outputs[0].get('view_url') or '').strip() if outputs else '',
        'failure_message': _plain_video_failure_message(row) if status == 'failed' else '',
    }
    return row


async def _refresh_remote_video_generation_job(job: dict) -> tuple[dict, dict | None, str]:
    if not isinstance(job, dict):
        return job, None, ''

    current_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    if current_state in {'failed', 'cancelled'}:
        return job, None, ''

    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    workflow_type = str(payload.get('workflow_type') or '').strip()
    if workflow_type in {'video_upscale', 'video_repair', 'video_interpolate'}:
        return job, None, ''

    adapter, _session, _error = _video_profile_or_error()
    next_job = None
    next_message = ''
    if adapter and job.get('prompt_id'):
        try:
            history = await adapter.get_history(job.get('prompt_id'))
            data = history.get(job.get('prompt_id')) if isinstance(history, dict) else None
            if data:
                outputs = _extract_history_videos(data, adapter, job.get('payload') or {})
                state = 'completed'
                history_status = data.get('status') if isinstance(data.get('status'), dict) else {}
                if history_status and not history_status.get('completed', True):
                    state = 'running'
                status_text = 'Render finished.' if state == 'completed' else 'Rendering in ComfyUI.'
                updates = {
                    'state': state,
                    'status_text': status_text,
                    'error': '',
                    'progress': {'percent': 100 if state == 'completed' else 65, 'detail': 'Finished' if state == 'completed' else 'Rendering'},
                }
                if outputs:
                    for item in outputs:
                        item['job_id'] = str(job.get('job_id') or job.get('id') or '')
                    updates['outputs'] = outputs
                job = update_generation_job(job.get('id') or job.get('job_id') or '', updates) or job
                if state == 'completed' and outputs:
                    manifest_path = _save_video_output_manifest(job, outputs)
                    job, next_job, next_message = await _maybe_dispatch_video_post_pipeline(job)
                    job = _enrich_video_job(job) or job
                    if isinstance(job, dict):
                        job.setdefault('video_runtime', {})
                        job['video_runtime']['manifest_path'] = str(manifest_path)
                        job['video_runtime']['manifest_url'] = f"/api/video/manifest/{job.get('job_id') or job.get('id') or ''}"
            else:
                try:
                    queue_state = await adapter.get_queue()
                    prompt_state = _queue_prompt_state(queue_state, job.get('prompt_id') or '')
                    if prompt_state:
                        job = update_generation_job(job.get('id') or job.get('job_id') or '', {
                            'state': prompt_state,
                            'status_text': 'Rendering in ComfyUI.' if prompt_state == 'running' else 'Waiting in ComfyUI queue.',
                            'progress': {'percent': 65 if prompt_state == 'running' else 5, 'detail': 'Rendering' if prompt_state == 'running' else 'Waiting in queue'},
                            'error': '',
                        }) or job
                    else:
                        age_seconds = _job_age_seconds(job)
                        updated_age_seconds = _job_update_age_seconds(job)
                        fallback_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
                        status_text = str(job.get('status_text') or '').strip().lower()
                        in_finalization = (
                            'waiting for history/output registration' in status_text
                            or 'waiting for output registration' in status_text
                            or int(((job.get('progress') or {}).get('percent') or 0) or 0) >= 95
                        )
                        if fallback_state in {'failed', 'cancelled'}:
                            return job, next_job, next_message
                        if in_finalization and updated_age_seconds < VIDEO_PROMPT_FINALIZATION_GRACE_SECONDS:
                            job = update_generation_job(job.get('id') or job.get('job_id') or '', {
                                'state': 'running',
                                'status_text': 'Backend execution finished. Waiting for history/output registration.',
                                'error': '',
                                'progress': {'percent': max(99, int(((job.get('progress') or {}).get('percent') or 0) or 0)), 'detail': 'Registering output'},
                            }) or job
                        elif age_seconds < VIDEO_PROMPT_SYNC_GRACE_SECONDS:
                            if fallback_state not in {'queued', 'running'}:
                                fallback_state = 'queued'
                            job = update_generation_job(job.get('id') or job.get('job_id') or '', {
                                'state': fallback_state,
                                'status_text': 'Prompt accepted. Waiting for the Video Backend to expose it in queue/history…',
                                'error': '',
                                'progress': {'percent': 5 if fallback_state == 'queued' else 65, 'detail': 'Syncing with backend'},
                            }) or job
                        else:
                            job = update_generation_job(job.get('id') or job.get('job_id') or '', {
                                'state': 'failed',
                                'status_text': 'Video backend no longer reports this prompt.',
                                'error': 'The connected Video Backend accepted the prompt earlier, but it is no longer visible in history or queue. This usually means the backend restarted, the queue was cleared, or the prompt was sent to a different Comfy instance.',
                                'progress': {'percent': 0, 'detail': 'No longer active'},
                            }) or job
                except Exception:
                    pass
        except Exception as exc:
            logger.warning('Could not refresh video job %s | %s', job.get('job_id') or job.get('id') or '', exc)

    return job, next_job, next_message



async def _compile_and_queue_video_job(
    *,
    adapter: ComfyBackendAdapter,
    session: dict,
    payload: dict,
    retry_of_job_id: str = '',
    parent_job_id: str = '',
) -> dict:
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    payload['mode'] = mode
    payload['profile'] = profile
    backend_engine = _selected_video_backend_engine(payload)
    payload['video_backend_engine'] = backend_engine
    quality_tier = 'balanced' if profile == 'wan22_5b_balanced' else 'quality'

    if backend_engine == 'kijai_wrapper':
        quality_tier = 'balanced'
        workflow_builder = build_video_balanced_wrapper_workflow
    else:
        workflow_builder = build_video_balanced_workflow if quality_tier == 'balanced' else build_video_quality_workflow
    workflow, normalized_payload, compile_notes = workflow_builder(payload)
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalized_payload,
        current_stage='generate',
        root_job_id=str((normalized_payload or {}).get('post_pipeline_root_job_id') or ''),
    )

    active_profile = get_profile('video', session.get('profile_id') or None) or {
        'backend_type': 'comfyui',
        'name': session.get('profile_name') or 'ComfyUI Video',
        'base_url': session.get('base_url') or '',
    }
    reserved_prompt_id = str(normalized_payload.get('prompt_id') or payload.get('prompt_id') or uuid4()).strip()
    job = create_generation_job(
        payload=normalized_payload,
        backend_profile=active_profile,
        prompt_id=reserved_prompt_id,
        queue_number=None,
        compile_notes=compile_notes,
        workflow_graph=workflow,
        parent_job_id=parent_job_id,
        retry_of_job_id=retry_of_job_id,
    )
    normalized_payload = _prepare_video_post_pipeline_payload(
        normalized_payload,
        current_stage='generate',
        root_job_id=str(normalized_payload.get('post_pipeline_root_job_id') or job.get('job_id') or job.get('id') or ''),
    )
    job = update_generation_job(job.get('id') or job.get('job_id') or '', {
        'surface': 'video',
        'family': 'wan22',
        'media_type': 'video',
        'payload': normalized_payload,
        'compile_notes': compile_notes,
        'workflow_graph': workflow,
        'prompt_id': reserved_prompt_id,
        'status_text': 'Submitting the video workflow to ComfyUI…',
        'progress': {'percent': 2, 'detail': 'Submitting prompt'},
        'error': '',
    }) or job

    try:
        queued = await adapter.queue_prompt(workflow, prompt_id=reserved_prompt_id)
    except Exception as exc:
        failed_job = update_generation_job(job.get('id') or job.get('job_id') or '', {
            'state': 'failed',
            'status_text': 'Could not queue the video workflow in ComfyUI.',
            'error': str(exc),
            'progress': {'percent': 0, 'detail': 'Queue request failed'},
        }) or job
        raise RuntimeError(str(exc)) from exc

    actual_prompt_id = str(queued.get('prompt_id') or reserved_prompt_id).strip() or reserved_prompt_id
    logger.info(
        'Video prompt queued in ComfyUI | engine=%s | prompt_id=%s | queue_number=%s | node_errors=%s',
        backend_engine,
        actual_prompt_id,
        queued.get('number'),
        bool(queued.get('node_errors')),
    )
    runtime = _video_runtime_guardrails(normalized_payload)
    if backend_engine == 'kijai_wrapper':
        queue_copy = 'Queued balanced video in ComfyUI through Kijai Wrapper.'
    else:
        queue_copy = 'Queued balanced video in ComfyUI.' if quality_tier == 'balanced' else 'Queued high-quality video in ComfyUI.'
    progress_detail = 'Waiting in queue'
    if runtime['estimated_heaviness'] == 'heavy':
        queue_copy = f'{queue_copy} This request is heavy and may take a while.'
    job = update_generation_job(job.get('id') or job.get('job_id') or '', {
        'surface': 'video',
        'family': 'wan22',
        'media_type': 'video',
        'prompt_id': actual_prompt_id,
        'queue_number': queued.get('number'),
        'status_text': queue_copy,
        'progress': {'percent': 5, 'detail': progress_detail},
        'payload': normalized_payload,
        'compile_notes': compile_notes,
        'workflow_graph': workflow,
        'error': '',
    }) or job
    if queued.get('node_errors'):
        validation_summary = _summarize_video_node_errors(queued.get('node_errors'))
        job = update_generation_job(job.get('id') or job.get('job_id') or '', {
            'state': 'failed',
            'status_text': 'ComfyUI rejected the video workflow during node validation.',
            'error': validation_summary,
            'error_message': json.dumps(queued.get('node_errors'), ensure_ascii=False),
            'progress': {'percent': 0, 'detail': 'Validation failed'},
        }) or job
    return {
        'job': job,
        'workflow': workflow,
        'compile_notes': compile_notes,
        'normalized_payload': normalized_payload,
        'queue_number': queued.get('number'),
        'prompt_id': actual_prompt_id,
        'queued': queued,
        'node_errors': queued.get('node_errors') or {},
        'node_error_summary': _summarize_video_node_errors(queued.get('node_errors')) if queued.get('node_errors') else '',
    }


async def _video_history_rows(limit: int) -> list[dict]:
    rows = [row for row in list_generation_jobs(limit=max(12, limit * 4)) if str(row.get('surface') or '').strip() == 'video']
    out: list[dict] = []
    for row in rows[: max(1, min(50, int(limit or 12)))]:
        if not isinstance(row, dict):
            continue
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        workflow_type = str(payload.get('workflow_type') or '').strip()
        if workflow_type == 'video_upscale':
            row = sync_local_video_upscale_job(row) or row
        elif workflow_type == 'video_repair':
            row = sync_local_video_repair_job(row) or row
        elif workflow_type == 'video_interpolate':
            row = sync_local_video_interpolate_job(row) or row
        elif str(row.get('prompt_id') or '').strip() and str(row.get('status') or row.get('state') or '').strip().lower() not in {'completed', 'failed', 'cancelled'}:
            row, _next_job, _message = await _refresh_remote_video_generation_job(row)
        if str(row.get('status') or row.get('state') or '').strip().lower() == 'completed' and row.get('outputs'):
            try:
                _save_video_output_manifest(row, [item for item in (row.get('outputs') or []) if isinstance(item, dict)])
            except Exception:
                pass
            try:
                row, _next_job, _message = await _maybe_dispatch_video_post_pipeline(row)
            except Exception:
                pass
        out.append(_enrich_video_job(row) or row)
    return out


def _video_presets_payload() -> dict:
    presets = [row for row in list_video_presets() if isinstance(row, dict)]
    return {
        'presets': presets,
        'summaries': [build_video_preset_summary(row) for row in presets],
        'default_preset_id': get_default_video_preset_id(),
        'categories': list_video_preset_categories(),
    }


def _video_adapter_pair_presets_payload() -> dict:
    presets = [row for row in list_video_adapter_presets() if isinstance(row, dict)]
    return {
        'pair_presets': presets,
    }


def _clean_video_asset_choices(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        clean = str(raw or '').strip()
        if clean and clean not in seen:
            out.append(clean)
            seen.add(clean)
    return out


def _prefer_video_asset_choices(values, *required_groups: tuple[str, ...]) -> list[str]:
    options = _clean_video_asset_choices(values)
    if not options:
        return []
    lowered = [(item, item.lower()) for item in options]
    picked: list[str] = []
    seen: set[str] = set()
    for item, low in lowered:
        if all(any(token in low for token in group) for group in required_groups if group):
            if item not in seen:
                picked.append(item)
                seen.add(item)
    return picked or options


def _is_video_gguf_asset_name(value: str) -> bool:
    clean = str(value or '').strip().lower()
    return clean.endswith('.gguf') or '.gguf' in clean


def _merge_video_asset_choices(*groups) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            clean = str(raw or '').strip()
            if clean and clean not in seen:
                out.append(clean)
                seen.add(clean)
    return out


def _pick_video_gguf_asset_choices(values, *required_groups: tuple[str, ...]) -> list[str]:
    gguf_values = [item for item in _clean_video_asset_choices(values) if _is_video_gguf_asset_name(item)]
    if not gguf_values:
        return []
    if not required_groups:
        return gguf_values
    return _prefer_video_asset_choices(gguf_values, *required_groups)


def _is_kijai_wrapper_encoder_name(value: str) -> bool:
    clean = str(value or '').strip().lower()
    if not clean:
        return False
    if 'umt5-xxl-enc' in clean:
        return True
    return 'umt5' in clean and 'scaled' not in clean and ('enc' in clean or 'wanvideo' in clean)


def _video_wrapper_catalog_sections(wrapper: dict | None) -> dict:
    row = wrapper if isinstance(wrapper, dict) else {}
    common_required_nodes = [
        'WanVideoModelLoader',
        'WanVideoVAELoader',
        'WanVideoTextEncodeCached',
        'WanVideoEmptyEmbeds',
        'WanVideoSampler',
        'WanVideoDecode',
    ]
    i2v_required_nodes = ['WanVideoImageToVideoEncode']
    available_nodes = [name for name in common_required_nodes + i2v_required_nodes if isinstance(row.get(name), dict) and row.get(name, {}).get('present')]
    missing_nodes = [name for name in common_required_nodes if name not in available_nodes]
    model_choices = _clean_video_asset_choices((row.get('WanVideoModelLoader') or {}).get('choices') or row.get('model_choices') or [])
    encoder_choices = _clean_video_asset_choices((row.get('WanVideoTextEncodeCached') or {}).get('choices') or (row.get('LoadWanVideoT5TextEncoder') or {}).get('choices') or row.get('encoder_choices') or [])
    vae_choices = _clean_video_asset_choices((row.get('WanVideoVAELoader') or {}).get('choices') or row.get('vae_choices') or [])
    available = not missing_nodes and bool(model_choices) and bool(encoder_choices) and bool(vae_choices)
    i2v_available = available and 'WanVideoImageToVideoEncode' in available_nodes
    note = 'Balanced video can auto-route through Kijai WanVideoWrapper when a wrapper-style text encoder is selected. Native Wan and Wrapper stay as separate backend engines even though they share the same asset folders.'
    return {
        'available': available,
        'i2v_available': i2v_available,
        'available_nodes': available_nodes,
        'missing_nodes': missing_nodes,
        'required_nodes': common_required_nodes,
        'required_nodes_i2v': common_required_nodes + i2v_required_nodes,
        'model_choices': model_choices,
        'encoder_choices': encoder_choices,
        'vae_choices': vae_choices,
        'note': note,
    }


def _video_wrapper_node_info_payload(object_info: dict | None, *field_names: str) -> dict:
    info = object_info if isinstance(object_info, dict) else {}
    return {
        'present': bool(info),
        'choices': _extract_video_node_required_choices(info, *field_names) if field_names else [],
    }


async def _video_wrapper_catalog_payload(adapter: ComfyBackendAdapter) -> dict:
    nodes = {
        'WanVideoModelLoader': ('model',),
        'WanVideoVAELoader': ('model_name',),
        'WanVideoTextEncodeCached': ('model_name',),
        'LoadWanVideoT5TextEncoder': ('model_name',),
        'WanVideoEmptyEmbeds': (),
        'WanVideoImageToVideoEncode': (),
        'WanVideoSampler': (),
        'WanVideoDecode': (),
    }
    payload: dict[str, dict] = {}
    for node_name, field_names in nodes.items():
        try:
            node_info = await adapter.get_object_info(node_name)
        except Exception:
            node_info = {}
        if isinstance(node_info, dict) and node_name in node_info:
            node_info = node_info.get(node_name)
        payload[node_name] = _video_wrapper_node_info_payload(node_info if isinstance(node_info, dict) else {}, *field_names)
    return payload


def _selected_video_backend_engine(payload: dict, catalog_payload: dict | None = None) -> str:
    explicit = str(payload.get('video_backend_engine') or '').strip().lower()
    if explicit in {'wan_native', 'kijai_wrapper'}:
        return explicit
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    backend_assets = payload.get('backend_assets') if isinstance(payload.get('backend_assets'), dict) else {}
    selected_encoder = ''
    if profile in {'wan22_5b_balanced', 'raw_free'}:
        selected_encoder = str(backend_assets.get('balanced_clip_name') or payload.get('clip_name') or '').strip()
        if _is_kijai_wrapper_encoder_name(selected_encoder):
            return 'kijai_wrapper'
    return 'wan_native'


def _validate_kijai_wrapper_backend_capabilities(catalog_payload: dict, payload: dict) -> None:
    catalog = catalog_payload.get('catalog') if isinstance(catalog_payload, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    wrapper = catalog.get('wrapper') if isinstance(catalog.get('wrapper'), dict) else {}
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    if profile not in {'wan22_5b_balanced', 'raw_free'}:
        raise ValueError('Kijai Wrapper routing is currently limited to the Balanced / Low VRAM or Raw / Free video profiles in this build.')
    if not wrapper.get('available'):
        missing = [str(item or '').strip() for item in (wrapper.get('missing_nodes') or []) if str(item or '').strip()]
        suffix = f' Missing wrapper nodes: {", ".join(missing)}.' if missing else ''
        raise ValueError(f'The connected ComfyUI build does not expose the required Kijai WanVideoWrapper nodes yet. Install or refresh the wrapper extension, then retry.{suffix}')
    if mode == 'i2v' and not wrapper.get('i2v_available'):
        raise ValueError('The connected ComfyUI build is missing WanVideoImageToVideoEncode, so Balanced I2V cannot use the Kijai Wrapper lane yet.')
    backend_assets = payload.get('backend_assets') if isinstance(payload.get('backend_assets'), dict) else {}
    selected_encoder = str(backend_assets.get('balanced_clip_name') or payload.get('clip_name') or '').strip()
    if not _is_kijai_wrapper_encoder_name(selected_encoder):
        raise ValueError('Kijai Wrapper routing needs a wrapper-style text encoder selection such as umt5-xxl-enc-fp8_e4m3fn.safetensors.')


def _video_backend_asset_catalog_sections(catalog: dict | None, *, clip_loader_types: list[str] | None = None, wrapper_catalog: dict | None = None) -> dict:
    row = catalog if isinstance(catalog, dict) else {}
    wrapper_sections = _video_wrapper_catalog_sections(wrapper_catalog)
    native_unets = _clean_video_asset_choices(row.get('unet') or row.get('diffusion_models') or [])
    native_encoders = _clean_video_asset_choices(row.get('clip') or row.get('text_encoders') or [])
    native_vaes = _clean_video_asset_choices(row.get('vae') or [])

    wrapper_unets = _clean_video_asset_choices(wrapper_sections.get('model_choices') or [])
    wrapper_encoders = _clean_video_asset_choices(wrapper_sections.get('encoder_choices') or [])
    wrapper_vaes = _clean_video_asset_choices(wrapper_sections.get('vae_choices') or [])

    unets = _merge_video_asset_choices(native_unets, wrapper_unets)
    encoders = _merge_video_asset_choices(native_encoders, wrapper_encoders)
    vaes = _merge_video_asset_choices(native_vaes, wrapper_vaes)

    native_wan_encoders = _prefer_video_asset_choices(native_encoders, ('umt5',))
    wrapper_wan_encoders = _prefer_video_asset_choices(wrapper_encoders, ('umt5',))
    wan_encoders = _merge_video_asset_choices(native_wan_encoders, wrapper_wan_encoders)
    wan_vaes = _prefer_video_asset_choices(vaes, ('wan',))
    balanced_unets = _prefer_video_asset_choices(unets, ('wan',), ('ti2v', '5b'))
    quality_t2v_high = _prefer_video_asset_choices(unets, ('wan',), ('t2v',), ('high',))
    quality_t2v_low = _prefer_video_asset_choices(unets, ('wan',), ('t2v',), ('low',))
    quality_i2v_high = _prefer_video_asset_choices(unets, ('wan',), ('i2v',), ('high',))
    quality_i2v_low = _prefer_video_asset_choices(unets, ('wan',), ('i2v',), ('low',))
    gguf_unets = [item for item in unets if _is_video_gguf_asset_name(item)]
    balanced_gguf = _pick_video_gguf_asset_choices(gguf_unets, ('wan',), ('ti2v', '5b', 'hybrid'))
    quality_t2v_high_gguf = _pick_video_gguf_asset_choices(gguf_unets, ('wan',), ('t2v',), ('high', 'hn'))
    quality_t2v_low_gguf = _pick_video_gguf_asset_choices(gguf_unets, ('wan',), ('t2v',), ('low', 'ln'))
    quality_i2v_high_gguf = _pick_video_gguf_asset_choices(gguf_unets, ('wan',), ('i2v',), ('high', 'hn'))
    quality_i2v_low_gguf = _pick_video_gguf_asset_choices(gguf_unets, ('wan',), ('i2v',), ('low', 'ln'))
    balanced_unets = _merge_video_asset_choices(balanced_unets, balanced_gguf)
    quality_t2v_high = _merge_video_asset_choices(quality_t2v_high, quality_t2v_high_gguf)
    quality_t2v_low = _merge_video_asset_choices(quality_t2v_low, quality_t2v_low_gguf)
    quality_i2v_high = _merge_video_asset_choices(quality_i2v_high, quality_i2v_high_gguf)
    quality_i2v_low = _merge_video_asset_choices(quality_i2v_low, quality_i2v_low_gguf)
    features = row.get('features') if isinstance(row.get('features'), dict) else {}
    gguf_available = bool(gguf_unets) and bool(features.get('gguf_unet_loader'))
    return {
        'all': {
            'unet_models': unets,
            'encoder_models': encoders,
            'vae_models': vaes,
            'defaults': {
                'unet_name': _pick_video_catalog_default(unets, 'wan2.2_ti2v_5B_fp16.safetensors', fallback='wan2.2_ti2v_5B_fp16.safetensors'),
                'clip_name': _pick_video_catalog_default(encoders, 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'umt5-xxl-enc-fp8_e4m3fn.safetensors', fallback='umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
                'vae_name': _pick_video_catalog_default(vaes, 'wan2.2_vae.safetensors', 'wan_2.1_vae.safetensors', 'ae.safetensors', fallback='wan2.2_vae.safetensors'),
            },
        },
        'balanced': {
            'unet_models': balanced_unets or unets,
            'encoder_models': wan_encoders,
            'vae_models': wan_vaes or vaes,
            'defaults': {
                'unet_name': _pick_video_catalog_default(balanced_unets or unets, 'wan2.2_ti2v_5B_fp16.safetensors', fallback='wan2.2_ti2v_5B_fp16.safetensors'),
                'clip_name': _pick_video_catalog_default(wan_encoders or encoders, 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'umt5-xxl-enc-fp8_e4m3fn.safetensors', fallback='umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
                'vae_name': _pick_video_catalog_default(wan_vaes or vaes, 'wan2.2_vae.safetensors', 'wan_2.1_vae.safetensors', 'ae.safetensors', fallback='wan2.2_vae.safetensors'),
            },
        },
        'quality_t2v': {
            'high_noise_unet_models': quality_t2v_high or unets,
            'low_noise_unet_models': quality_t2v_low or unets,
            'encoder_models': wan_encoders,
            'vae_models': wan_vaes or vaes,
            'defaults': {
                'high_noise_unet_name': _pick_video_catalog_default(quality_t2v_high or unets, 'wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors', fallback='wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors'),
                'low_noise_unet_name': _pick_video_catalog_default(quality_t2v_low or unets, 'wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors', fallback='wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors'),
                'clip_name': _pick_video_catalog_default(wan_encoders or encoders, 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'umt5-xxl-enc-fp8_e4m3fn.safetensors', fallback='umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
                'vae_name': _pick_video_catalog_default(wan_vaes or vaes, 'wan_2.1_vae.safetensors', 'wan2.2_vae.safetensors', 'ae.safetensors', fallback='wan_2.1_vae.safetensors'),
            },
        },
        'quality_i2v': {
            'high_noise_unet_models': quality_i2v_high or unets,
            'low_noise_unet_models': quality_i2v_low or unets,
            'encoder_models': wan_encoders,
            'vae_models': wan_vaes or vaes,
            'defaults': {
                'high_noise_unet_name': _pick_video_catalog_default(quality_i2v_high or unets, 'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors', fallback='wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors'),
                'low_noise_unet_name': _pick_video_catalog_default(quality_i2v_low or unets, 'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors', fallback='wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors'),
                'clip_name': _pick_video_catalog_default(wan_encoders or encoders, 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'umt5-xxl-enc-fp8_e4m3fn.safetensors', fallback='umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
                'vae_name': _pick_video_catalog_default(wan_vaes or vaes, 'wan_2.1_vae.safetensors', 'wan2.2_vae.safetensors', 'ae.safetensors', fallback='wan_2.1_vae.safetensors'),
            },
        },
        'gguf': {
            'available': gguf_available,
            'detected_unet_models': gguf_unets,
            'routing': 'unet_loader_gguf' if gguf_available else 'native_only',
            'note': 'Video now detects Wan GGUF UNET assets through Comfy object_info and routes selected .gguf UNETs through UnetLoaderGGUF. Encoders and VAEs still stay on the native Wan path.',
        },
        'wrapper': wrapper_sections,
        'encoder_loader': {
            'class_type': 'CLIPLoader',
            'supported_types': [str(item or '').strip() for item in (clip_loader_types or []) if str(item or '').strip()],
            'wan_supported': any(str(item or '').strip().lower() == 'wan' for item in (clip_loader_types or [])),
        },
        'counts': {
            'unet': len(unets),
            'encoder': len(encoders),
            'vae': len(vaes),
        },
    }


VIDEO_STALE_ASSET_ALIASES = {
    'umt5_xxl_fp8_e4m3fn_scaled.safetensors': ['umt5-xxl-enc-fp8_e4m3fn.safetensors'],
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': ['umt5_xxl_fp8_e4m3fn_scaled.safetensors'],
    'wan2.2_vae.safetensors': ['wan_2.1_vae.safetensors', 'ae.safetensors'],
    'wan_2.1_vae.safetensors': ['wan2.2_vae.safetensors', 'ae.safetensors'],
}


def _normalize_video_asset_choice_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _resolve_live_video_asset_choice(value: str, allowed: list[str] | tuple[str, ...] | None) -> str:
    clean = str(value or '').strip()
    choices = [str(item or '').strip() for item in (allowed or []) if str(item or '').strip()]
    if not clean:
        return ''
    if clean in choices:
        return clean
    for candidate in VIDEO_STALE_ASSET_ALIASES.get(clean.lower(), []):
        if candidate in choices:
            return candidate
    normalized = _normalize_video_asset_choice_key(clean).replace('scaled', '')
    matches = [item for item in choices if _normalize_video_asset_choice_key(item).replace('scaled', '') == normalized]
    return matches[0] if len(matches) == 1 else ''


def _pick_video_catalog_default(choices: list[str], *preferred: str, fallback: str = '') -> str:
    cleaned = [str(item or '').strip() for item in (choices or []) if str(item or '').strip()]
    for candidate in preferred:
        resolved = _resolve_live_video_asset_choice(candidate, cleaned)
        if resolved:
            return resolved
    return cleaned[0] if cleaned else str(fallback or '').strip()


def _video_asset_lists_for_profile(catalog: dict, profile: str, *, free_mode: bool = False) -> dict[str, list[str]]:
    clean_profile = normalize_video_profile(profile or '', mode='')
    if free_mode or clean_profile == 'raw_free':
        all_assets = catalog.get('all') if isinstance(catalog.get('all'), dict) else {}
        return {
            'balanced_unet_name': list(all_assets.get('unet_models') or []),
            'balanced_clip_name': list(all_assets.get('encoder_models') or []),
            'balanced_vae_name': list(all_assets.get('vae_models') or []),
            'quality_high_noise_unet_name': list(all_assets.get('unet_models') or []),
            'quality_low_noise_unet_name': list(all_assets.get('unet_models') or []),
            'quality_clip_name': list(all_assets.get('encoder_models') or []),
            'quality_vae_name': list(all_assets.get('vae_models') or []),
        }
    if clean_profile == 'wan22_5b_balanced':
        balanced = catalog.get('balanced') if isinstance(catalog.get('balanced'), dict) else {}
        return {
            'balanced_unet_name': list(balanced.get('unet_models') or []),
            'balanced_clip_name': list(balanced.get('encoder_models') or []),
            'balanced_vae_name': list(balanced.get('vae_models') or []),
        }
    quality = catalog.get('quality_i2v') if clean_profile == 'wan22_14b_i2v_quality' else catalog.get('quality_t2v')
    quality = quality if isinstance(quality, dict) else {}
    return {
        'quality_high_noise_unet_name': list(quality.get('high_noise_unet_models') or []),
        'quality_low_noise_unet_name': list(quality.get('low_noise_unet_models') or []),
        'quality_clip_name': list(quality.get('encoder_models') or []),
        'quality_vae_name': list(quality.get('vae_models') or []),
    }


def _validate_video_backend_assets_against_catalog(payload: dict, catalog_payload: dict) -> dict:
    backend_assets = normalize_video_backend_assets(payload, profile=str(payload.get('profile') or '').strip(), mode=str(payload.get('mode') or '').strip())
    catalog = catalog_payload.get('catalog') if isinstance(catalog_payload, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    counts = catalog.get('counts') if isinstance(catalog.get('counts'), dict) else {}
    if not (catalog_payload.get('connected') and (counts.get('unet') or counts.get('encoder') or counts.get('vae'))):
        raise ValueError('Video asset validation needs a live backend catalog first. Refresh assets, then retry.')
    allowed_map = _video_asset_lists_for_profile(catalog, str(payload.get('profile') or '').strip(), free_mode=bool(payload.get('free_asset_mode') or payload.get('video_free_asset_mode')))
    labels = {
        'balanced_unet_name': 'Balanced model',
        'balanced_clip_name': 'Balanced text encoder',
        'balanced_vae_name': 'Balanced VAE',
        'quality_high_noise_unet_name': 'High-noise model',
        'quality_low_noise_unet_name': 'Low-noise model',
        'quality_clip_name': 'Quality text encoder',
        'quality_vae_name': 'Quality VAE',
    }
    resolved_assets = dict(backend_assets)
    for key, allowed in allowed_map.items():
        selected = str(backend_assets.get(key) or '').strip()
        if not selected:
            raise ValueError(f"{labels.get(key, key)} is required before queueing video generation.")
        allowed_clean = [str(item or '').strip() for item in allowed if str(item or '').strip()]
        if not allowed_clean:
            raise ValueError(f"{labels.get(key, key)} could not be validated because the live backend catalog did not return any choices for that field.")
        resolved = _resolve_live_video_asset_choice(selected, allowed_clean)
        if not resolved:
            raise ValueError(f'{labels.get(key, key)} "{selected}" is not in the live backend catalog. Refresh assets or pick one of the current backend choices.')
        resolved_assets[key] = resolved
    return resolved_assets


def _extract_video_node_required_choices(object_info: dict | None, *field_names: str) -> list[str]:
    info = object_info if isinstance(object_info, dict) else {}
    return ComfyBackendAdapter._extract_node_required_choices(info, *field_names)


def _is_raw_free_video_profile(profile: str = '', *, mode: str = '') -> bool:
    return normalize_video_profile(profile or '', mode=mode) == 'raw_free'


async def _video_clip_loader_types(adapter: ComfyBackendAdapter) -> list[str]:
    try:
        clip_loader_info = await adapter.get_object_info('CLIPLoader')
    except Exception:
        return []
    if isinstance(clip_loader_info, dict) and 'CLIPLoader' in clip_loader_info:
        clip_loader_info = clip_loader_info.get('CLIPLoader')
    return _extract_video_node_required_choices(clip_loader_info if isinstance(clip_loader_info, dict) else {}, 'type')


def _validate_wan_video_backend_capabilities(catalog_payload: dict, payload: dict) -> None:
    catalog = catalog_payload.get('catalog') if isinstance(catalog_payload, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    encoder_loader = catalog.get('encoder_loader') if isinstance(catalog.get('encoder_loader'), dict) else {}
    supported_types = [str(item or '').strip().lower() for item in (encoder_loader.get('supported_types') or []) if str(item or '').strip()]
    if not supported_types or 'wan' not in supported_types:
        readable = ', '.join(sorted(set(item for item in supported_types if item)))
        suffix = f' Advertised CLIPLoader types: {readable}.' if readable else ' The CLIPLoader object_info payload did not expose any supported type choices.'
        raise ValueError(f'The connected ComfyUI build does not advertise CLIPLoader type "wan" for Wan video text encoders. Update ComfyUI, refresh Video assets, then retry.{suffix}')
    profile = normalize_video_profile(str(payload.get('profile') or '').strip(), mode=str(payload.get('mode') or '').strip())
    free_mode = bool(payload.get('free_asset_mode') or payload.get('video_free_asset_mode'))
    sections = (catalog.get('all') if (free_mode or profile == 'raw_free') else (catalog.get('balanced') if profile == 'wan22_5b_balanced' else (catalog.get('quality_i2v') if profile == 'wan22_14b_i2v_quality' else catalog.get('quality_t2v'))))
    sections = sections if isinstance(sections, dict) else {}
    encoder_choices = [str(item or '').strip() for item in (sections.get('encoder_models') or []) if str(item or '').strip()]
    if not encoder_choices:
        raise ValueError('The connected video backend did not return any Wan-compatible UMT5 text encoder choices for this profile. Refresh assets or install the official Wan text encoder bundle first.')


def _video_model_lane_kind(value: str = '') -> str:
    clean = str(value or '').strip().lower()
    if not clean:
        return ''
    clean = re.split(r'[\/]', clean)[-1]
    if re.search(r'(?<![a-z0-9])ti2v(?![a-z0-9])', clean):
        return 'ti2v'
    if re.search(r'(?<![a-z0-9])i2v(?![a-z0-9])', clean):
        return 'i2v'
    if re.search(r'(?<![a-z0-9])t2v(?![a-z0-9])', clean):
        return 't2v'
    return ''


def _video_mode_allows_model_kind(mode: str = '', kind: str = '') -> bool:
    clean_mode = normalize_video_mode(mode)
    clean_kind = str(kind or '').strip().lower()
    if not clean_kind:
        return True
    if clean_kind == 'ti2v':
        return True
    if clean_mode == 'i2v':
        return clean_kind == 'i2v'
    return clean_kind == 't2v'


def _video_asset_basename(value: str = '') -> str:
    clean = str(value or '').strip().lower()
    if not clean:
        return ''
    clean = re.split(r'[\/]', clean)[-1]
    return clean


def _native_required_vae_for_video_model(value: str = '') -> str:
    clean = _video_asset_basename(value)
    if not clean:
        return ''
    is_wan22 = 'wan2.2' in clean or 'wan22' in clean
    if not is_wan22:
        return ''
    is_5b_ti2v = ('ti2v' in clean and '5b' in clean)
    if is_5b_ti2v:
        return 'wan2.2_vae.safetensors'
    is_14b = '14b' in clean or 'a14b' in clean or 't2v' in clean or 'i2v' in clean
    if is_14b:
        return 'wan_2.1_vae.safetensors'
    return ''


def _active_video_model_guardrail_rows(payload: dict) -> list[tuple[str, str]]:
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    engine = str(payload.get('video_backend_engine') or '').strip().lower() or _selected_video_backend_engine(payload)
    backend_assets = payload.get('backend_assets') if isinstance(payload.get('backend_assets'), dict) else {}
    if engine == 'kijai_wrapper' or profile == 'wan22_5b_balanced' or (profile == 'raw_free' and engine == 'kijai_wrapper'):
        return [('Balanced model', str(backend_assets.get('balanced_unet_name') or payload.get('unet_name') or '').strip())]
    return [
        ('High-noise model', str(backend_assets.get('quality_high_noise_unet_name') or payload.get('quality_high_noise_unet_name') or '').strip()),
        ('Low-noise model', str(backend_assets.get('quality_low_noise_unet_name') or payload.get('quality_low_noise_unet_name') or '').strip()),
    ]


def _active_video_vae_guardrail_row(payload: dict) -> tuple[str, str]:
    mode = normalize_video_mode(payload.get('mode') or '')
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    engine = str(payload.get('video_backend_engine') or '').strip().lower() or _selected_video_backend_engine(payload)
    backend_assets = payload.get('backend_assets') if isinstance(payload.get('backend_assets'), dict) else {}
    if engine == 'kijai_wrapper' or profile == 'wan22_5b_balanced' or (profile == 'raw_free' and engine == 'kijai_wrapper'):
        return ('Balanced VAE', str(backend_assets.get('balanced_vae_name') or payload.get('vae_name') or '').strip())
    return ('Quality VAE', str(backend_assets.get('quality_vae_name') or payload.get('vae_name_quality') or payload.get('vae_name') or '').strip())


def _validate_video_runtime_guardrails(payload: dict) -> None:
    mode = normalize_video_mode(payload.get('mode') or '')
    engine = str(payload.get('video_backend_engine') or '').strip().lower() or _selected_video_backend_engine(payload)
    profile = normalize_video_profile(payload.get('profile') or '', mode=mode)
    advanced_adapters = normalize_video_advanced_adapters(payload, profile=profile)
    if engine == 'kijai_wrapper' and advanced_adapters.get('enabled'):
        raise ValueError('Kijai Wrapper + LoRAs / adapters is not supported in this build yet. Switch Backend engine to Wan Native or disable adapters before queueing.')
    expected_label = 'Image to Video' if mode == 'i2v' else 'Text to Video'
    allowed_hint = 'I2V or TI2V' if mode == 'i2v' else 'T2V or TI2V'
    active_models = _active_video_model_guardrail_rows(payload)
    for label, selected in active_models:
        kind = _video_model_lane_kind(selected)
        if not selected or not kind or _video_mode_allows_model_kind(mode, kind):
            continue
        actual_label = 'Image to Video' if kind == 'i2v' else 'Text to Video' if kind == 't2v' else 'Text/Image to Video'
        raise ValueError(f'{label} "{selected}" looks like an {actual_label} checkpoint, but the current mode is {expected_label}. Pick a {allowed_hint} model for this lane.')
    if engine == 'wan_native':
        vae_label, selected_vae = _active_video_vae_guardrail_row(payload)
        selected_vae_base = _video_asset_basename(selected_vae)
        for model_label, model_name in active_models:
            required_vae = _native_required_vae_for_video_model(model_name)
            if not required_vae or not selected_vae_base or selected_vae_base == required_vae:
                continue
            raise ValueError(
                f'{model_label} "{model_name}" expects {required_vae} in Wan Native, but {vae_label} is set to "{selected_vae}". '
                'Switch the VAE to the matching native Wan file before queueing.'
            )


async def _video_backend_asset_catalog_payload() -> dict:
    manager_state = get_manager_state()
    session = (manager_state.get('session') or {}).get('video') or {}
    payload = {
        'connected': bool(session.get('connected')),
        'backend_ready': False,
        'catalog': _video_backend_asset_catalog_sections({}),
        'session': session,
    }
    if not payload['connected']:
        return payload
    profile = get_profile('video', session.get('profile_id') or None)
    if not profile:
        return payload
    adapter = ComfyBackendAdapter(profile.get('base_url') or session.get('base_url') or '', timeout_sec=int(profile.get('timeout_sec') or 30))
    try:
        catalog = await adapter.get_catalog()
        clip_loader_types = await _video_clip_loader_types(adapter)
        wrapper_catalog = await _video_wrapper_catalog_payload(adapter)
        payload['catalog'] = _video_backend_asset_catalog_sections(catalog, clip_loader_types=clip_loader_types, wrapper_catalog=wrapper_catalog)
        counts = payload['catalog'].get('counts') if isinstance(payload['catalog'].get('counts'), dict) else {}
        encoder_loader = payload['catalog'].get('encoder_loader') if isinstance(payload['catalog'].get('encoder_loader'), dict) else {}
        wrapper = payload['catalog'].get('wrapper') if isinstance(payload['catalog'].get('wrapper'), dict) else {}
        has_assets = bool((counts.get('unet') or counts.get('encoder') or counts.get('vae')))
        payload['backend_ready'] = bool(has_assets and (encoder_loader.get('wan_supported') or wrapper.get('available')))
    except Exception as exc:
        logger.warning('Could not load video backend asset catalog: %s', exc)
    return payload


async def _video_adapter_catalog_payload() -> dict:
    manager_state = get_manager_state()
    session = (manager_state.get('session') or {}).get('video') or {}
    payload = {
        'connected': bool(session.get('connected')),
        'backend_ready': False,
        'supports_paired_lora': False,
        'loras': [],
        'session': session,
        **_video_adapter_pair_presets_payload(),
    }
    if not payload['connected']:
        return payload
    profile = get_profile('video', session.get('profile_id') or None)
    if not profile:
        return payload
    adapter = ComfyBackendAdapter(profile.get('base_url') or session.get('base_url') or '', timeout_sec=int(profile.get('timeout_sec') or 30))
    try:
        catalog = await adapter.get_catalog()
        payload['loras'] = list(catalog.get('loras') or []) if isinstance(catalog, dict) else []
    except Exception as exc:
        logger.warning('Could not load video adapter catalog: %s', exc)
    try:
        model_only_info = await adapter.get_object_info('LoraLoaderModelOnly')
        if isinstance(model_only_info, dict) and 'LoraLoaderModelOnly' in model_only_info:
            model_only_info = model_only_info.get('LoraLoaderModelOnly')
        fallback_info = await adapter.get_object_info('LoraLoader')
        if isinstance(fallback_info, dict) and 'LoraLoader' in fallback_info:
            fallback_info = fallback_info.get('LoraLoader')
        payload['supports_paired_lora'] = bool(model_only_info or fallback_info)
        payload['backend_ready'] = bool(payload['loras']) and bool(payload['supports_paired_lora'])
    except Exception as exc:
        logger.warning('Could not inspect paired adapter node support: %s', exc)
    return payload


@router.websocket('/api/video/progress/ws')
async def ws_video_progress(websocket: WebSocket):
    """Video progress websocket is intentionally disabled.

    The prior proxy bridged browser -> Neo -> ComfyUI /ws. On Windows/ComfyUI this produced
    repeated ConnectionResetError [WinError 10054] noise when the browser refreshed, the tab
    re-bound, or the remote end closed mid-teardown. Video tracking now uses polling only.
    Keeping the route alive but inert prevents stale cached front-end bundles from opening a
    proxy connection to ComfyUI.
    """
    await websocket.accept()
    try:
        await websocket.send_json({
            'type': 'disabled',
            'data': {
                'message': 'Video live progress websocket is disabled in this build. Video tracking uses polling only.'
            },
        })
    except Exception:
        pass
    finally:
        try:
            await websocket.close(code=1000)
        except Exception:
            pass


@router.get('/api/video/presets')
async def api_video_presets():
    return JSONResponse({'ok': True, **_video_presets_payload()})


@router.post('/api/video/presets/save')
async def api_video_preset_save(name: str = Form(...), settings_json: str = Form('{}'), preset_id: str = Form(''), category: str = Form('custom'), notes: str = Form('')):
    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Preset payload must be a JSON object.')
        saved = save_video_preset(name=name, payload=payload, preset_id=preset_id, category=category, notes=notes)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not save video preset')
        return json_error(f'Could not save video preset: {exc}', 502)
    return JSONResponse({'ok': True, 'message': f"Saved video preset: {saved.get('name') or 'Untitled video preset'}", 'preset': saved, **_video_presets_payload()})


@router.post('/api/video/presets/delete')
async def api_video_preset_delete(preset_id: str = Form('')):
    try:
        target = get_video_preset(preset_id)
        if not target:
            raise ValueError('Saved video preset was not found.')
        delete_video_preset(preset_id)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not delete video preset')
        return json_error(f'Could not delete video preset: {exc}', 502)
    return JSONResponse({'ok': True, 'message': f"Deleted video preset: {target.get('name') or 'Untitled video preset'}", **_video_presets_payload()})


@router.post('/api/video/presets/set-default')
async def api_video_preset_set_default(preset_id: str = Form('')):
    try:
        target = get_video_preset(preset_id)
        if not target:
            raise ValueError('Saved video preset was not found.')
        set_default_video_preset(preset_id)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not set default video preset')
        return json_error(f'Could not set default video preset: {exc}', 502)
    return JSONResponse({'ok': True, 'message': f"Default video preset set: {target.get('name') or 'Untitled video preset'}", **_video_presets_payload()})


@router.post('/api/video/presets/clear-default')
async def api_video_preset_clear_default():
    clear_default_video_preset()
    return JSONResponse({'ok': True, 'message': 'Default video preset cleared.', **_video_presets_payload()})


@router.get('/api/video/assets')
async def api_video_assets():
    return JSONResponse({'ok': True, **(await _video_backend_asset_catalog_payload())})


@router.get('/api/video/adapters')
async def api_video_adapters():
    return JSONResponse({'ok': True, **(await _video_adapter_catalog_payload())})


@router.post('/api/video/adapter-presets/save')
async def api_video_adapter_preset_save(name: str = Form(...), high_noise_adapter: str = Form(''), low_noise_adapter: str = Form(''), strength: str = Form('0.8'), preset_id: str = Form('')):
    try:
        saved = save_video_adapter_preset(
            name=name,
            high_noise_adapter=high_noise_adapter,
            low_noise_adapter=low_noise_adapter,
            strength=strength,
            preset_id=preset_id,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not save video adapter pair preset')
        return json_error(f'Could not save the video adapter pair preset: {exc}', 502)
    return JSONResponse({'ok': True, 'message': f"Saved adapter pair preset: {saved.get('name') or 'Untitled adapter pair'}", 'preset': saved, **_video_adapter_pair_presets_payload()})


@router.post('/api/video/adapter-presets/delete')
async def api_video_adapter_preset_delete(preset_id: str = Form('')):
    try:
        target = get_video_adapter_preset(preset_id)
        if not target:
            raise ValueError('Adapter pair preset was not found.')
        delete_video_adapter_preset(preset_id)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not delete video adapter pair preset')
        return json_error(f'Could not delete the video adapter pair preset: {exc}', 502)
    return JSONResponse({'ok': True, 'message': f"Deleted adapter pair preset: {target.get('name') or 'Untitled adapter pair'}", **_video_adapter_pair_presets_payload()})


@router.get('/api/video/contract')
async def api_video_contract():
    return JSONResponse({
        'ok': True,
        'contract': build_video_contract_boot_payload(),
    })


@router.post('/api/video/upscale')
async def api_video_upscale(request: Request):
    form = await request.form()
    settings_json = str(form.get('settings_json') or '{}')
    source_video_file = form.get('source_video_file')
    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a JSON object.')
    except Exception as exc:
        return json_error(f'Invalid upscale payload: {exc}', 400)

    try:
        prepared = await _prepare_video_upscale_source(payload, source_video_file if hasattr(source_video_file, 'filename') else None)
        queue_payload = await _queue_video_upscale_job(prepared)
    except ValueError as exc:
        logger.warning('Video upscale validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not queue the local Upscale lane')
        return json_error(f'Could not queue the local Upscale lane: {exc}', 502)

    job = queue_payload['job']
    return JSONResponse({
        'ok': True,
        'message': 'Queued local Upscale lane.',
        'job': _enrich_video_job(job),
    })


@router.post('/api/video/repair')
async def api_video_repair(request: Request):
    form = await request.form()
    settings_json = str(form.get('settings_json') or '{}')
    source_video_file = form.get('source_video_file')
    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a JSON object.')
    except Exception as exc:
        return json_error(f'Invalid repair payload: {exc}', 400)

    try:
        prepared = await _prepare_video_repair_source(payload, source_video_file if hasattr(source_video_file, 'filename') else None)
        queue_payload = await _queue_video_repair_job(prepared)
    except ValueError as exc:
        logger.warning('Video repair validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not queue the local Repair lane')
        return json_error(f'Could not queue the local Repair lane: {exc}', 502)

    job = queue_payload['job']
    return JSONResponse({
        'ok': True,
        'message': 'Queued local Repair lane.',
        'job': _enrich_video_job(job),
    })


@router.post('/api/video/interpolate')
async def api_video_interpolate(settings_json: str = Form(...), source_video_file: UploadFile | None = None):
    try:
        payload = json.loads(settings_json or '{}')
        prepared = await _prepare_video_interpolate_source(payload, source_video_file if hasattr(source_video_file, 'filename') else None)
        queue_payload = await _queue_video_interpolate_job(prepared)
        job = queue_payload['job']
    except ValueError as exc:
        logger.warning('Video interpolate validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not queue local video interpolate lane')
        return json_error(f'Could not queue the local Interpolate lane: {exc}', 502)

    return JSONResponse({
        'ok': True,
        'message': 'Queued local Interpolate lane.',
        'job': _enrich_video_job(job),
        'queue_number': None,
        'prompt_id': '',
        'contract_result': build_video_result_record({
            'job_id': job.get('job_id') or job.get('id') or '',
            'mode': 't2v',
            'profile': 'wan22_5b_balanced',
            'status': job.get('state') or job.get('status') or 'running',
            'outputs': [],
            'artifacts': {},
            'error': {'message': ''},
        }),
    })


@router.post('/api/video/generate')
async def api_video_generate(request: Request):
    adapter, session, error = _video_profile_or_error()
    if error:
        return error

    form = await request.form()
    settings_json = str(form.get('settings_json') or '{}')
    source_image_file = form.get('source_image_file')
    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a JSON object.')
    except Exception as exc:
        return json_error(f'Invalid video payload: {exc}', 400)

    try:
        if str(payload.get('client_id') or '').strip():
            adapter.client_id = str(payload.get('client_id') or '').strip()

        free_mode = bool(payload.get('free_asset_mode') or payload.get('video_free_asset_mode') or _is_raw_free_video_profile(str(payload.get('profile') or '').strip(), mode=str(payload.get('mode') or '').strip()))
        if free_mode:
            asset_catalog_payload = {
                'connected': True,
                'backend_ready': True,
                'catalog': _video_backend_asset_catalog_sections({}),
                'session': session,
            }
            payload['backend_assets'] = normalize_video_backend_assets(
                payload,
                profile=str(payload.get('profile') or '').strip(),
                mode=str(payload.get('mode') or '').strip(),
            )
        else:
            asset_catalog_payload = await _video_backend_asset_catalog_payload()
            payload['backend_assets'] = _validate_video_backend_assets_against_catalog(payload, asset_catalog_payload)
        backend_assets = payload['backend_assets'] if isinstance(payload.get('backend_assets'), dict) else {}
        payload['unet_name'] = str(backend_assets.get('balanced_unet_name') or payload.get('unet_name') or '').strip()
        payload['clip_name'] = str(backend_assets.get('balanced_clip_name') or payload.get('clip_name') or '').strip()
        payload['vae_name'] = str(backend_assets.get('balanced_vae_name') or payload.get('vae_name') or '').strip()
        payload['quality_high_noise_unet_name'] = str(backend_assets.get('quality_high_noise_unet_name') or payload.get('quality_high_noise_unet_name') or '').strip()
        payload['quality_low_noise_unet_name'] = str(backend_assets.get('quality_low_noise_unet_name') or payload.get('quality_low_noise_unet_name') or '').strip()
        payload['clip_name_quality'] = str(backend_assets.get('quality_clip_name') or payload.get('clip_name_quality') or payload.get('clip_name') or '').strip()
        payload['vae_name_quality'] = str(backend_assets.get('quality_vae_name') or payload.get('vae_name_quality') or payload.get('vae_name') or '').strip()
        payload['video_backend_engine'] = _selected_video_backend_engine(payload, asset_catalog_payload)
        if not free_mode:
            if payload['video_backend_engine'] == 'kijai_wrapper':
                _validate_kijai_wrapper_backend_capabilities(asset_catalog_payload, payload)
            else:
                _validate_wan_video_backend_capabilities(asset_catalog_payload, payload)

        saved_source = await _save_upload(source_image_file if hasattr(source_image_file, 'filename') else None, 'video_source')
        if saved_source:
            payload['source_image'] = str(payload.get('source_image') or saved_source['filename']).strip() or saved_source['filename']
            payload['source_image_name'] = await _upload_saved(adapter, saved_source)

        payload['advanced_adapters'] = normalize_video_advanced_adapters(payload, profile=str(payload.get('profile') or '').strip())
        _validate_video_runtime_guardrails(payload)
        errors = validate_video_request(payload)
        if errors:
            raise ValueError(errors[0])

        queue_payload = await _compile_and_queue_video_job(adapter=adapter, session=session, payload=payload)
    except ValueError as exc:
        logger.warning('Video validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not queue the video workflow')
        return json_error(f'Could not queue the video workflow: {exc}', 502)

    job = queue_payload['job']
    normalized_payload = queue_payload['normalized_payload']
    job_status = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    contract_job = build_video_job_record({
        **normalized_payload,
        'job_id': job.get('job_id') or job.get('id') or '',
        'status': job_status,
        'warnings': queue_payload['compile_notes'] + _video_runtime_guardrails(normalized_payload).get('warnings', []),
        'source_image': normalized_payload.get('source_image') or normalized_payload.get('source_image_name') or '',
    })
    enriched_job = _enrich_video_job(job)
    if queue_payload.get('node_errors'):
        return JSONResponse({
            'ok': False,
            'message': queue_payload.get('node_error_summary') or 'ComfyUI rejected the video workflow during node validation.',
            'job': enriched_job,
            'contract_job': contract_job,
            'queue_number': queue_payload['queue_number'],
            'prompt_id': queue_payload['prompt_id'],
            'queued': queue_payload.get('queued') or {},
            'node_errors': queue_payload.get('node_errors') or {},
        }, status_code=409)
    return JSONResponse({
        'ok': True,
        'job': enriched_job,
        'contract_job': contract_job,
        'queue_number': queue_payload['queue_number'],
        'prompt_id': queue_payload['prompt_id'],
    })


@router.get('/api/video/job/{job_id}')
async def api_video_job(job_id: str):
    job = get_generation_job(job_id)
    if not job:
        return json_error('Video job not found.', 404)

    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    workflow_type = str(payload.get('workflow_type') or '').strip()
    next_job = None
    next_message = ''
    if workflow_type in {'video_upscale', 'video_repair', 'video_interpolate'}:
        job = (
            sync_local_video_upscale_job(job) if workflow_type == 'video_upscale'
            else sync_local_video_repair_job(job) if workflow_type == 'video_repair'
            else sync_local_video_interpolate_job(job)
        ) or job
        outputs = [item for item in (job.get('outputs') or []) if isinstance(item, dict)]
        next_job = None
        next_message = ''
        if str(job.get('status') or job.get('state') or '').strip().lower() == 'completed' and outputs:
            manifest_path = _save_video_output_manifest(job, outputs)
            job, next_job, next_message = await _maybe_dispatch_video_post_pipeline(job)
            job = _enrich_video_job(job) or job
            if isinstance(job, dict):
                job.setdefault('video_runtime', {})
                job['video_runtime']['manifest_path'] = str(manifest_path)
                job['video_runtime']['manifest_url'] = f"/api/video/manifest/{job.get('job_id') or job.get('id') or ''}"
        job_view = _enrich_video_job(job) or job
        runtime_view = (job_view or {}).get('video_runtime') if isinstance(job_view, dict) else {}
        contract_result = build_video_result_record({
            'job_id': job.get('job_id') or job.get('id') or '',
            'mode': payload.get('mode') or 't2v',
            'profile': payload.get('profile') or 'wan22_5b_balanced',
            'status': job.get('status') or job.get('state') or 'queued',
            'outputs': [
                {
                    'output_id': item.get('output_id') or item.get('filename') or '',
                    'media_type': item.get('media_type') or 'video',
                    'path': item.get('view_url') or '',
                    'filename': item.get('filename') or '',
                    'duration_seconds': item.get('duration_seconds'),
                    'fps': item.get('fps'),
                    'size_preset': item.get('size_preset') or '',
                }
                for item in (job.get('outputs') or []) if isinstance(item, dict)
            ],
            'artifacts': {'manifest_path': str(runtime_view.get('manifest_path') or '')},
            'error': {'message': runtime_view.get('failure_message') or job.get('error') or ''},
        })
        return JSONResponse({'ok': True, 'job': job_view, 'contract_result': contract_result, 'next_job': _enrich_video_job(next_job) if isinstance(next_job, dict) else None, 'message': next_message})

    if str(job.get('prompt_id') or '').strip():
        job, next_job, next_message = await _refresh_remote_video_generation_job(job)

    job_view = _enrich_video_job(job) or job
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    runtime_view = (job_view or {}).get('video_runtime') if isinstance(job_view, dict) else {}
    contract_result = build_video_result_record({
        'job_id': job.get('job_id') or job.get('id') or '',
        'mode': payload.get('mode') or 't2v',
        'profile': payload.get('profile') or 'wan22_5b_balanced',
        'status': job.get('status') or job.get('state') or 'queued',
        'outputs': [
            {
                'output_id': item.get('output_id') or item.get('filename') or '',
                'media_type': item.get('media_type') or 'video',
                'path': item.get('view_url') or '',
                'filename': item.get('filename') or '',
                'duration_seconds': item.get('duration_seconds'),
                'fps': item.get('fps'),
                'size_preset': item.get('size_preset') or '',
            }
            for item in (job.get('outputs') or []) if isinstance(item, dict)
        ],
        'artifacts': {'manifest_path': str(runtime_view.get('manifest_path') or '')},
        'error': {'message': runtime_view.get('failure_message') or job.get('error') or ''},
    })
    return JSONResponse({'ok': True, 'job': job_view, 'contract_result': contract_result, 'next_job': _enrich_video_job(next_job) if isinstance(next_job, dict) else None, 'message': next_message})


@router.get('/api/video/history')
async def api_video_history(limit: int = Query(8, ge=1, le=24)):
    return JSONResponse({'ok': True, 'jobs': await _video_history_rows(limit)})


@router.get('/api/video/manifest/{job_id}')
async def api_video_manifest(job_id: str):
    job = get_generation_job(job_id)
    if not job or str(job.get('surface') or '').strip() != 'video':
        return json_error('Video job not found.', 404)
    path = _video_manifest_path(job.get('job_id') or job.get('id') or '')
    if not path.exists():
        return json_error('Video output manifest not found yet.', 404)
    return JSONResponse({'ok': True, 'manifest': read_json_dict(path)})


@router.get('/api/video/output-file/{job_id}/{filename}')
async def api_video_output_file(job_id: str, filename: str):
    job = get_generation_job(job_id)
    if not job or str(job.get('surface') or '').strip() != 'video':
        return json_error('Video job not found.', 404)
    for item in (job.get('outputs') or []):
        if not isinstance(item, dict):
            continue
        if str(item.get('filename') or '').strip() != str(filename or '').strip():
            continue
        path = Path(str(item.get('local_path') or '').strip())
        if not path.exists():
            return json_error('Video output file was not found on disk.', 404)
        return _local_video_output_response(path)
    return json_error('Video output file was not found.', 404)


@router.post('/api/video/cancel')
async def api_video_cancel(job_id: str = Form(''), prompt_id: str = Form('')):
    target_job = get_generation_job(job_id) if str(job_id or '').strip() else None
    target_payload = target_job.get('payload') if isinstance(target_job, dict) and isinstance(target_job.get('payload'), dict) else {}
    if str(target_payload.get('workflow_type') or '').strip() == 'video_upscale':
        cancelled = cancel_local_video_upscale_job(target_job) if target_job else None
        return JSONResponse({
            'ok': True,
            'message': 'Stop sent to the local Upscale lane.',
            'result': {'mode': 'local_upscale'},
            'queue_result': None,
            'job': _enrich_video_job(cancelled) if cancelled else None,
        })
    if str(target_payload.get('workflow_type') or '').strip() == 'video_repair':
        cancelled = cancel_local_video_repair_job(target_job) if target_job else None
        return JSONResponse({
            'ok': True,
            'message': 'Stop sent to the local Repair lane.',
            'result': {'mode': 'local_repair'},
            'queue_result': None,
            'job': _enrich_video_job(cancelled) if cancelled else None,
        })
    if str(target_payload.get('workflow_type') or '').strip() == 'video_interpolate':
        cancelled = cancel_local_video_interpolate_job(target_job) if target_job else None
        return JSONResponse({
            'ok': True,
            'message': 'Stop sent to the local Interpolate lane.',
            'result': {'mode': 'local_interpolate'},
            'queue_result': None,
            'job': _enrich_video_job(cancelled) if cancelled else None,
        })

    adapter, _session, error = _video_profile_or_error()
    if error:
        return error
    try:
        result = await adapter.interrupt(str(prompt_id or '').strip() or None)
    except Exception as exc:
        logger.warning('Video interrupt failed: %s', exc)
        return json_error('Could not interrupt the current video job.', 502)

    queue_result = None
    try:
        queue_result = await adapter.clear_queue()
    except Exception:
        queue_result = None

    updated = None
    if str(job_id or '').strip():
        updated = update_generation_job(job_id, {
            'state': 'cancelled',
            'status_text': 'Stopped from Neo Studio. Current run interrupted and pending video queue cleared.',
            'progress': {'percent': 0, 'detail': 'Cancelled'},
            'error': '',
        })
    return JSONResponse({
        'ok': True,
        'message': 'Stop sent to ComfyUI. Current run interrupted and pending video queue cleared.',
        'result': result,
        'queue_result': queue_result,
        'job': _enrich_video_job(updated) if updated else None,
    })


@router.post('/api/video/retry')
async def api_video_retry(job_id: str = Form('')):
    target = str(job_id or '').strip()
    if not target:
        return json_error('Video job id is required for retry.', 400)
    source_job = get_generation_job(target)
    if not source_job or str(source_job.get('surface') or '').strip() != 'video':
        return json_error('Video job not found.', 404)

    payload = deepcopy(source_job.get('payload') or {}) if isinstance(source_job.get('payload'), dict) else {}
    payload.pop('post_pipeline_dispatch', None)
    if not payload:
        return json_error('The selected video job does not have a retryable payload.', 400)

    if str(payload.get('workflow_type') or '').strip() == 'video_upscale':
        try:
            prepared = await _prepare_video_upscale_source(payload, None)
            queue_payload = await _queue_video_upscale_job(prepared)
        except ValueError as exc:
            logger.warning('Video upscale retry validation failed: %s', exc)
            return json_error(str(exc), 400)
        except Exception as exc:
            logger.exception('Could not retry the local Upscale lane')
            return json_error(f'Could not retry the local Upscale lane: {exc}', 502)
        return JSONResponse({
            'ok': True,
            'message': 'Queued a retry of the selected Upscale lane job.',
            'source_job_id': target,
            'job': _enrich_video_job(queue_payload['job']),
            'queue_number': None,
            'prompt_id': '',
        })

    if str(payload.get('workflow_type') or '').strip() == 'video_repair':
        try:
            prepared = await _prepare_video_repair_source(payload, None)
            queue_payload = await _queue_video_repair_job(prepared)
        except ValueError as exc:
            logger.warning('Video repair retry validation failed: %s', exc)
            return json_error(str(exc), 400)
        except Exception as exc:
            logger.exception('Could not retry the local Repair lane')
            return json_error(f'Could not retry the local Repair lane: {exc}', 502)
        return JSONResponse({
            'ok': True,
            'message': 'Queued a retry of the selected Repair lane job.',
            'source_job_id': target,
            'job': _enrich_video_job(queue_payload['job']),
            'queue_number': None,
            'prompt_id': '',
        })

    if str(payload.get('workflow_type') or '').strip() == 'video_interpolate':
        try:
            prepared = await _prepare_video_interpolate_source(payload, None)
            queue_payload = await _queue_video_interpolate_job(prepared)
        except ValueError as exc:
            logger.warning('Video interpolate retry validation failed: %s', exc)
            return json_error(str(exc), 400)
        except Exception as exc:
            logger.exception('Could not retry the local Interpolate lane')
            return json_error(f'Could not retry the local Interpolate lane: {exc}', 502)
        return JSONResponse({
            'ok': True,
            'message': 'Queued a retry of the selected Interpolate lane job.',
            'source_job_id': target,
            'job': _enrich_video_job(queue_payload['job']),
            'queue_number': None,
            'prompt_id': '',
        })

    adapter, session, error = _video_profile_or_error()
    if error:
        return error

    try:
        payload['advanced_adapters'] = normalize_video_advanced_adapters(payload, profile=str(payload.get('profile') or '').strip())
        errors = validate_video_request(payload)
        if errors:
            raise ValueError(errors[0])
        queue_payload = await _compile_and_queue_video_job(
            adapter=adapter,
            session=session,
            payload=payload,
            retry_of_job_id=target,
            parent_job_id=target,
        )
    except ValueError as exc:
        logger.warning('Video retry validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not retry the video workflow')
        return json_error(f'Could not retry the video workflow: {exc}', 502)

    return JSONResponse({
        'ok': True,
        'message': 'Queued a retry of the selected video job.',
        'source_job_id': target,
        'job': _enrich_video_job(queue_payload['job']),
        'queue_number': queue_payload['queue_number'],
        'prompt_id': queue_payload['prompt_id'],
    })
