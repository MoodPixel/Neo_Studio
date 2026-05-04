from __future__ import annotations

import json
import mimetypes
import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from .generation_jobs import ensure_generation_dirs, update_generation_job
from .library_common import safe_name
from .library_constants import USER_DATA_DIR
from .video_upscale_jobs import build_local_output_url, probe_video, process_alive, read_ffmpeg_progress, tail_text

VIDEO_REPAIR_INPUT_DIR = USER_DATA_DIR / 'video_repair_inputs'
VIDEO_REPAIR_OUTPUT_DIR = USER_DATA_DIR / 'video_repair_outputs'
VIDEO_REPAIR_RUNTIME_DIR = USER_DATA_DIR / 'video_repair_runtime'

VIDEO_REPAIR_STRENGTHS = {
    'gentle': {'id': 'gentle', 'label': 'Gentle'},
    'balanced': {'id': 'balanced', 'label': 'Balanced'},
    'aggressive': {'id': 'aggressive', 'label': 'Aggressive'},
}
VIDEO_REPAIR_FOCUS = {
    'general_cleanup': {'id': 'general_cleanup', 'label': 'General cleanup'},
    'compression_cleanup': {'id': 'compression_cleanup', 'label': 'Compression artifact cleanup'},
}


def ensure_video_repair_dirs() -> None:
    ensure_generation_dirs()
    VIDEO_REPAIR_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_REPAIR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_REPAIR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def normalize_video_repair_strength(value: Any) -> str:
    clean = str(value or 'balanced').strip().lower() or 'balanced'
    return clean if clean in VIDEO_REPAIR_STRENGTHS else 'balanced'


def normalize_video_repair_focus(value: Any) -> str:
    clean = str(value or 'general_cleanup').strip().lower() or 'general_cleanup'
    return clean if clean in VIDEO_REPAIR_FOCUS else 'general_cleanup'


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def save_repair_input_video(raw: bytes, filename: str, *, prefix: str = 'repair_source') -> dict[str, Any]:
    if not raw:
        raise ValueError('Source video file was empty.')
    ensure_video_repair_dirs()
    source_name = str(filename or prefix).strip() or prefix
    stem = safe_name(Path(source_name).stem) or prefix
    suffix = Path(source_name).suffix[:12] or '.mp4'
    target = VIDEO_REPAIR_INPUT_DIR / f'{prefix}_{uuid4().hex[:8]}_{stem}{suffix}'
    target.write_bytes(raw)
    return {
        'path': target,
        'filename': target.name,
        'bytes': len(raw),
    }


def normalize_video_repair_payload(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(data or {})
    source_ref = payload.get('source_output_ref') if isinstance(payload.get('source_output_ref'), dict) else {}
    return {
        **payload,
        'surface': 'video',
        'family': 'local_ffmpeg',
        'workflow_type': 'video_repair',
        'lane': 'repair',
        'repair_strength_preset': normalize_video_repair_strength(payload.get('repair_strength_preset') or payload.get('repair_strength')),
        'repair_cleanup_focus': normalize_video_repair_focus(payload.get('repair_cleanup_focus') or payload.get('repair_focus')),
        'stabilize_temporal': truthy(payload.get('stabilize_temporal') or payload.get('repair_stabilize_temporal')),
        'source_video': str(payload.get('source_video') or '').strip(),
        'source_video_local_path': str(payload.get('source_video_local_path') or '').strip(),
        'source_video_label': str(payload.get('source_video_label') or '').strip(),
        'source_output_ref': {
            'job_id': str(source_ref.get('job_id') or '').strip(),
            'output_id': str(source_ref.get('output_id') or '').strip(),
            'filename': str(source_ref.get('filename') or '').strip(),
            'subfolder': str(source_ref.get('subfolder') or '').strip(),
            'type': str(source_ref.get('type') or '').strip(),
            'view_url': str(source_ref.get('view_url') or '').strip(),
            'local_path': str(source_ref.get('local_path') or '').strip(),
            'label': str(source_ref.get('label') or '').strip(),
        },
    }


def validate_video_repair_payload(data: dict[str, Any] | None = None) -> list[str]:
    payload = normalize_video_repair_payload(data)
    errors: list[str] = []
    if not payload['source_video_local_path'] and not payload['source_video'] and not payload['source_output_ref'].get('view_url') and not payload['source_output_ref'].get('local_path'):
        errors.append('Select a source video or send an existing output into the Repair lane first.')
    return errors


def build_repair_output_paths(job_id: str, *, source_name: str = 'video') -> dict[str, Path]:
    ensure_video_repair_dirs()
    stem = safe_name(Path(source_name).stem) or 'video'
    job_safe = safe_name(job_id) or 'video_job'
    filename = f'{job_safe}_{stem}_repaired.mp4'
    progress_path = VIDEO_REPAIR_RUNTIME_DIR / f'{job_safe}.progress'
    log_path = VIDEO_REPAIR_RUNTIME_DIR / f'{job_safe}.log'
    output_path = VIDEO_REPAIR_OUTPUT_DIR / filename
    return {
        'filename': filename,
        'output_path': output_path,
        'progress_path': progress_path,
        'log_path': log_path,
    }


def build_repair_filter_chain(*, strength: str, cleanup_focus: str, stabilize_temporal: bool) -> str:
    clean_strength = normalize_video_repair_strength(strength)
    clean_focus = normalize_video_repair_focus(cleanup_focus)
    filters: list[str] = []
    if stabilize_temporal:
        filters.append('deshake=x=16:y=16:rx=16:ry=16:edge=mirror')
    if clean_focus == 'compression_cleanup':
        if clean_strength == 'gentle':
            filters.append('deblock=filter=weak:block=4')
        elif clean_strength == 'aggressive':
            filters.append('deblock=filter=strong:block=6')
        else:
            filters.append('deblock=filter=strong:block=4')
    if clean_strength == 'gentle':
        filters.append('hqdn3d=1.25:1.25:4.0:4.0')
        filters.append('unsharp=3:3:0.12:3:3:0.0')
    elif clean_strength == 'aggressive':
        filters.append('hqdn3d=2.8:2.4:7.0:6.0')
        filters.append('unsharp=5:5:0.12:3:3:0.0')
    else:
        filters.append('hqdn3d=1.8:1.8:5.5:5.5')
        filters.append('unsharp=5:5:0.18:3:3:0.0')
    return ','.join(filters)


def build_repair_ffmpeg_command(*, source_path: str | Path, output_path: str | Path, progress_path: str | Path, strength: str, cleanup_focus: str, stabilize_temporal: bool) -> list[str]:
    vf_chain = build_repair_filter_chain(strength=strength, cleanup_focus=cleanup_focus, stabilize_temporal=stabilize_temporal)
    clean_strength = normalize_video_repair_strength(strength)
    crf = '18' if clean_strength == 'gentle' else ('20' if clean_strength == 'balanced' else '22')
    preset = 'slow' if clean_strength != 'gentle' else 'medium'
    return [
        'ffmpeg', '-y', '-i', str(source_path),
        '-map', '0:v:0', '-map', '0:a?',
        '-vf', vf_chain,
        '-c:v', 'libx264', '-crf', crf, '-preset', preset,
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        '-progress', str(progress_path), '-nostats',
        str(output_path),
    ]


def spawn_video_repair_process(*, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_video_repair_payload(payload)
    source_path = Path(clean.get('source_video_local_path') or clean.get('source_video') or '')
    if not source_path.exists():
        raise ValueError('The selected source video file was not found locally.')
    source_meta = probe_video(source_path)
    paths = build_repair_output_paths(job_id, source_name=source_path.name)
    for file_path in (paths['output_path'], paths['progress_path'], paths['log_path']):
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    cmd = build_repair_ffmpeg_command(
        source_path=source_path,
        output_path=paths['output_path'],
        progress_path=paths['progress_path'],
        strength=clean['repair_strength_preset'],
        cleanup_focus=clean['repair_cleanup_focus'],
        stabilize_temporal=clean['stabilize_temporal'],
    )
    log_handle = open(paths['log_path'], 'ab')
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, start_new_session=True)
    log_handle.close()
    return {
        **clean,
        'source_video_local_path': str(source_path),
        'source_video_label': clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or source_path.name,
        'source_probe': source_meta,
        'resolved_output_width': int(source_meta.get('width') or 0),
        'resolved_output_height': int(source_meta.get('height') or 0),
        'resolved_fps': int(round(float(source_meta.get('fps') or 0))) if float(source_meta.get('fps') or 0) > 0 else 0,
        'repair_pid': int(proc.pid),
        'repair_process_group_id': int(proc.pid),
        'repair_command': ' '.join(shlex.quote(part) for part in cmd),
        'repair_output_path': str(paths['output_path']),
        'repair_output_filename': str(paths['filename']),
        'repair_progress_path': str(paths['progress_path']),
        'repair_log_path': str(paths['log_path']),
    }


def build_local_video_repair_output_record(*, job_id: str, payload: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    target = Path(output_path)
    filename = target.name
    mime_type = mimetypes.guess_type(str(target))[0] or 'video/mp4'
    return {
        'schema_version': 1,
        'record_type': 'job_output_ref',
        'output_id': filename,
        'job_id': str(job_id),
        'media_type': 'video',
        'status': 'saved',
        'filename': filename,
        'local_path': str(target),
        'view_url': build_local_output_url(str(job_id), filename),
        'subfolder': 'local_video_repair',
        'type': 'local',
        'duration_seconds': payload.get('source_probe', {}).get('duration_seconds'),
        'fps': payload.get('resolved_fps') or payload.get('source_probe', {}).get('fps'),
        'size_preset': f"{payload.get('resolved_output_width')}x{payload.get('resolved_output_height')}",
        'mime_type': mime_type,
    }


def sync_local_video_repair_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    if str(payload.get('workflow_type') or '').strip() != 'video_repair':
        return job
    current_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    if current_state in {'completed', 'failed', 'cancelled'}:
        return job
    duration_seconds = float((payload.get('source_probe') or {}).get('duration_seconds') or 0.0)
    progress = read_ffmpeg_progress(payload.get('repair_progress_path') or '', duration_seconds=duration_seconds)
    output_path = Path(str(payload.get('repair_output_path') or ''))
    pid = payload.get('repair_pid')
    if process_alive(pid):
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'running',
            'status_text': 'Running local Repair lane.',
            'progress': progress,
        }) or job
    if output_path.exists() and output_path.stat().st_size > 0:
        output = build_local_video_repair_output_record(job_id=str(job.get('job_id') or job.get('id') or ''), payload=payload, output_path=output_path)
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'completed',
            'status_text': 'Repair lane finished locally.',
            'progress': {'percent': 100, 'detail': 'Completed'},
            'outputs': [output],
            'error': '',
        }) or job
    log_tail = tail_text(payload.get('repair_log_path') or '')
    return update_generation_job(job.get('job_id') or job.get('id') or '', {
        'state': 'failed',
        'status_text': 'The local Repair lane failed before a repaired file was written.',
        'progress': {'percent': max(5, int(progress.get('percent') or 5)), 'detail': 'Failed'},
        'error': log_tail or 'Local Repair lane failed.',
    }) or job


def cancel_local_video_repair_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    pid = payload.get('repair_process_group_id') or payload.get('repair_pid')
    try:
        clean_pid = int(pid)
    except Exception:
        clean_pid = 0
    if clean_pid > 0:
        try:
            os.killpg(clean_pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(clean_pid, signal.SIGTERM)
            except Exception:
                pass
    return update_generation_job(job.get('job_id') or job.get('id') or '', {
        'state': 'cancelled',
        'status_text': 'Stopped from Neo Studio. Local Repair lane interrupted.',
        'progress': {'percent': 0, 'detail': 'Cancelled'},
        'error': '',
    }) or job
