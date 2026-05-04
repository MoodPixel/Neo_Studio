from __future__ import annotations

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
from .video_upscale_jobs import build_local_output_url, clamp_int, probe_video, process_alive, read_ffmpeg_progress, tail_text

VIDEO_INTERPOLATE_INPUT_DIR = USER_DATA_DIR / 'video_interpolate_inputs'
VIDEO_INTERPOLATE_OUTPUT_DIR = USER_DATA_DIR / 'video_interpolate_outputs'
VIDEO_INTERPOLATE_RUNTIME_DIR = USER_DATA_DIR / 'video_interpolate_runtime'

VIDEO_INTERPOLATE_QUALITY_MODES = {
    'balanced': {'id': 'balanced', 'label': 'Balanced'},
    'smooth': {'id': 'smooth', 'label': 'Smoother motion'},
    'detail_safe': {'id': 'detail_safe', 'label': 'Detail safe'},
}
VIDEO_INTERPOLATE_TIMING_INTENTS = {
    'preserve_timing': {'id': 'preserve_timing', 'label': 'Preserve timing'},
    'slow_motion': {'id': 'slow_motion', 'label': 'Slow motion'},
}
VIDEO_INTERPOLATE_PRESETS = {
    '16_to_24': {'id': '16_to_24', 'label': '16 → 24 FPS', 'target_fps': 24, 'multiplier': '1.5'},
    '16_to_30': {'id': '16_to_30', 'label': '16 → 30 FPS', 'target_fps': 30, 'multiplier': '1.875'},
    '24_to_30': {'id': '24_to_30', 'label': '24 → 30 FPS', 'target_fps': 30, 'multiplier': '1.25'},
    '30_to_60': {'id': '30_to_60', 'label': '30 → 60 FPS', 'target_fps': 60, 'multiplier': '2'},
}


def ensure_video_interpolate_dirs() -> None:
    ensure_generation_dirs()
    VIDEO_INTERPOLATE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_INTERPOLATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_INTERPOLATE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_video_interpolate_quality_mode(value: Any) -> str:
    clean = str(value or 'balanced').strip().lower() or 'balanced'
    return clean if clean in VIDEO_INTERPOLATE_QUALITY_MODES else 'balanced'


def normalize_video_interpolate_timing_intent(value: Any) -> str:
    clean = str(value or 'preserve_timing').strip().lower() or 'preserve_timing'
    return clean if clean in VIDEO_INTERPOLATE_TIMING_INTENTS else 'preserve_timing'


def normalize_video_interpolate_preset(value: Any) -> str:
    clean = str(value or '').strip().lower()
    return clean if clean in VIDEO_INTERPOLATE_PRESETS else ''


def clamp_multiplier(value: Any, default: float = 2.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    parsed = max(1.0, min(4.0, parsed))
    return round(parsed, 3)


def save_interpolate_input_video(raw: bytes, filename: str, *, prefix: str = 'interpolate_source') -> dict[str, Any]:
    if not raw:
        raise ValueError('Source video file was empty.')
    ensure_video_interpolate_dirs()
    source_name = str(filename or prefix).strip() or prefix
    stem = safe_name(Path(source_name).stem) or prefix
    suffix = Path(source_name).suffix[:12] or '.mp4'
    target = VIDEO_INTERPOLATE_INPUT_DIR / f'{prefix}_{uuid4().hex[:8]}_{stem}{suffix}'
    target.write_bytes(raw)
    return {
        'path': target,
        'filename': target.name,
        'bytes': len(raw),
    }


def normalize_video_interpolate_payload(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(data or {})
    source_ref = payload.get('source_output_ref') if isinstance(payload.get('source_output_ref'), dict) else {}
    preset_id = normalize_video_interpolate_preset(payload.get('interpolation_preset') or payload.get('preset_id'))
    preset = VIDEO_INTERPOLATE_PRESETS.get(preset_id, {})
    target_fps_value = payload.get('target_fps') if payload.get('target_fps') not in {None, ''} else preset.get('target_fps', 30)
    multiplier_value = payload.get('interpolation_multiplier') if payload.get('interpolation_multiplier') not in {None, ''} else preset.get('multiplier', 2.0)
    return {
        **payload,
        'surface': 'video',
        'family': 'local_ffmpeg',
        'workflow_type': 'video_interpolate',
        'lane': 'interpolate',
        'interpolation_preset': preset_id,
        'target_fps': clamp_int(target_fps_value, 30, 8, 60),
        'interpolation_multiplier': clamp_multiplier(multiplier_value, 2.0),
        'motion_quality_mode': normalize_video_interpolate_quality_mode(payload.get('motion_quality_mode') or payload.get('quality_mode')),
        'timing_intent': normalize_video_interpolate_timing_intent(payload.get('timing_intent') or payload.get('intent')),
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


def validate_video_interpolate_payload(data: dict[str, Any] | None = None) -> list[str]:
    payload = normalize_video_interpolate_payload(data)
    errors: list[str] = []
    if not payload['source_video_local_path'] and not payload['source_video'] and not payload['source_output_ref'].get('view_url') and not payload['source_output_ref'].get('local_path'):
        errors.append('Select a source video or send an existing output into the Interpolate lane first.')
    return errors


def build_interpolate_output_paths(job_id: str, *, source_name: str = 'video') -> dict[str, Path]:
    ensure_video_interpolate_dirs()
    stem = safe_name(Path(source_name).stem) or 'video'
    job_safe = safe_name(job_id) or 'video_job'
    filename = f'{job_safe}_{stem}_interpolated.mp4'
    progress_path = VIDEO_INTERPOLATE_RUNTIME_DIR / f'{job_safe}.progress'
    log_path = VIDEO_INTERPOLATE_RUNTIME_DIR / f'{job_safe}.log'
    output_path = VIDEO_INTERPOLATE_OUTPUT_DIR / filename
    return {
        'filename': filename,
        'output_path': output_path,
        'progress_path': progress_path,
        'log_path': log_path,
    }


def _motion_quality_filter(target_fps: int, quality_mode: str) -> str:
    clean_mode = normalize_video_interpolate_quality_mode(quality_mode)
    if clean_mode == 'smooth':
        return f'minterpolate=fps={int(target_fps)}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'
    if clean_mode == 'detail_safe':
        return f'minterpolate=fps={int(target_fps)}:mi_mode=mci:mc_mode=obmc:me_mode=bidir:vsbmc=1:scd=fdiff:scd_threshold=8'
    return f'minterpolate=fps={int(target_fps)}:mi_mode=mci:mc_mode=obmc:me_mode=bidir:vsbmc=0'


def _build_atempo_chain(speed_ratio: float) -> str:
    ratio = max(0.25, min(4.0, float(speed_ratio or 1.0)))
    filters: list[str] = []
    while ratio < 0.5:
        filters.append('atempo=0.5')
        ratio /= 0.5
    while ratio > 2.0:
        filters.append('atempo=2.0')
        ratio /= 2.0
    filters.append(f'atempo={ratio:.5f}'.rstrip('0').rstrip('.'))
    return ','.join(filters)


def build_interpolate_ffmpeg_command(*, source_path: str | Path, output_path: str | Path, progress_path: str | Path, source_fps: float, target_fps: int, timing_intent: str, quality_mode: str) -> list[str]:
    source_fps = max(1.0, float(source_fps or target_fps or 1.0))
    target_fps = max(8, int(target_fps or round(source_fps)))
    clean_intent = normalize_video_interpolate_timing_intent(timing_intent)
    interpolation_filter = _motion_quality_filter(target_fps, quality_mode)
    if clean_intent == 'slow_motion':
        slow_factor = max(1.0, float(target_fps) / float(source_fps or target_fps))
        vf_chain = f'setpts={slow_factor:.6f}*PTS,{interpolation_filter}'
    else:
        vf_chain = interpolation_filter
    cmd = [
        'ffmpeg', '-y', '-i', str(source_path),
        '-map', '0:v:0', '-map', '0:a?',
        '-vf', vf_chain,
    ]
    if clean_intent == 'slow_motion':
        slow_factor = max(1.0, float(target_fps) / float(source_fps or target_fps))
        cmd.extend(['-af', _build_atempo_chain(1.0 / slow_factor)])
    cmd.extend([
        '-c:v', 'libx264', '-crf', '18' if normalize_video_interpolate_quality_mode(quality_mode) == 'detail_safe' else '20',
        '-preset', 'slow' if normalize_video_interpolate_quality_mode(quality_mode) != 'balanced' else 'medium',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        '-progress', str(progress_path), '-nostats',
        str(output_path),
    ])
    return cmd


def spawn_video_interpolate_process(*, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_video_interpolate_payload(payload)
    source_path = Path(clean.get('source_video_local_path') or clean.get('source_video') or '')
    if not source_path.exists():
        raise ValueError('The selected source video file was not found locally.')
    source_meta = probe_video(source_path)
    source_fps = float(source_meta.get('fps') or 0.0)
    resolved_target_fps = int(clean.get('target_fps') or 30)
    resolved_multiplier = clamp_multiplier(clean.get('interpolation_multiplier') or (resolved_target_fps / source_fps if source_fps > 0 else 2.0), 2.0)
    if source_fps > 0 and resolved_target_fps <= int(round(source_fps)):
        raise ValueError(f'Interpolate needs a target FPS higher than the source clip ({source_fps:.2f} FPS).')
    timing_intent = normalize_video_interpolate_timing_intent(clean.get('timing_intent'))
    output_duration = float(source_meta.get('duration_seconds') or 0.0)
    if timing_intent == 'slow_motion' and source_fps > 0:
        output_duration = output_duration * max(1.0, float(resolved_target_fps) / source_fps)
    paths = build_interpolate_output_paths(job_id, source_name=source_path.name)
    for file_path in (paths['output_path'], paths['progress_path'], paths['log_path']):
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    cmd = build_interpolate_ffmpeg_command(
        source_path=source_path,
        output_path=paths['output_path'],
        progress_path=paths['progress_path'],
        source_fps=source_fps,
        target_fps=resolved_target_fps,
        timing_intent=timing_intent,
        quality_mode=clean.get('motion_quality_mode') or 'balanced',
    )
    log_handle = open(paths['log_path'], 'ab')
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, start_new_session=True)
    log_handle.close()
    return {
        **clean,
        'source_video_local_path': str(source_path),
        'source_video_label': clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or source_path.name,
        'source_probe': source_meta,
        'resolved_source_fps': source_fps,
        'resolved_target_fps': resolved_target_fps,
        'resolved_multiplier': resolved_multiplier,
        'resolved_output_width': int(source_meta.get('width') or 0),
        'resolved_output_height': int(source_meta.get('height') or 0),
        'resolved_output_duration_seconds': output_duration,
        'interpolate_pid': int(proc.pid),
        'interpolate_process_group_id': int(proc.pid),
        'interpolate_command': ' '.join(shlex.quote(part) for part in cmd),
        'interpolate_output_path': str(paths['output_path']),
        'interpolate_output_filename': str(paths['filename']),
        'interpolate_progress_path': str(paths['progress_path']),
        'interpolate_log_path': str(paths['log_path']),
    }


def build_local_video_interpolate_output_record(*, job_id: str, payload: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
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
        'subfolder': 'local_video_interpolate',
        'type': 'local',
        'duration_seconds': payload.get('resolved_output_duration_seconds') or payload.get('source_probe', {}).get('duration_seconds'),
        'fps': payload.get('resolved_target_fps') or payload.get('target_fps'),
        'size_preset': f"{payload.get('resolved_output_width')}x{payload.get('resolved_output_height')}",
        'mime_type': mime_type,
    }


def sync_local_video_interpolate_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    if str(payload.get('workflow_type') or '').strip() != 'video_interpolate':
        return job
    current_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    if current_state in {'completed', 'failed', 'cancelled'}:
        return job
    duration_seconds = float(payload.get('resolved_output_duration_seconds') or (payload.get('source_probe') or {}).get('duration_seconds') or 0.0)
    progress = read_ffmpeg_progress(payload.get('interpolate_progress_path') or '', duration_seconds=duration_seconds)
    output_path = Path(str(payload.get('interpolate_output_path') or ''))
    pid = payload.get('interpolate_pid')
    if process_alive(pid):
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'running',
            'status_text': 'Running local Interpolate lane.',
            'progress': progress,
        }) or job
    if output_path.exists() and output_path.stat().st_size > 0:
        output = build_local_video_interpolate_output_record(job_id=str(job.get('job_id') or job.get('id') or ''), payload=payload, output_path=output_path)
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'completed',
            'status_text': 'Interpolate lane finished locally.',
            'progress': {'percent': 100, 'detail': 'Completed'},
            'outputs': [output],
            'error': '',
        }) or job
    log_tail = tail_text(payload.get('interpolate_log_path') or '')
    return update_generation_job(job.get('job_id') or job.get('id') or '', {
        'state': 'failed',
        'status_text': 'The local Interpolate lane failed before an interpolated file was written.',
        'progress': {'percent': max(5, int(progress.get('percent') or 5)), 'detail': 'Failed'},
        'error': log_tail or 'Local Interpolate lane failed.',
    }) or job


def cancel_local_video_interpolate_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    pid = payload.get('interpolate_process_group_id') or payload.get('interpolate_pid')
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
        'status_text': 'Stopped from Neo Studio. Local Interpolate lane interrupted.',
        'progress': {'percent': 0, 'detail': 'Cancelled'},
        'error': '',
    }) or job
