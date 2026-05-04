from __future__ import annotations

import json
import mimetypes
import os
import shlex
import signal
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from .generation_jobs import ensure_generation_dirs, update_generation_job
from .library_common import safe_name
from .library_constants import USER_DATA_DIR

VIDEO_UPSCALE_INPUT_DIR = USER_DATA_DIR / 'video_upscale_inputs'
VIDEO_UPSCALE_OUTPUT_DIR = USER_DATA_DIR / 'video_upscale_outputs'
VIDEO_UPSCALE_RUNTIME_DIR = USER_DATA_DIR / 'video_upscale_runtime'

VIDEO_UPSCALE_PROFILES = {
    'fast_local': {'id': 'fast_local', 'label': 'Fast Local'},
    'quality_conservative': {'id': 'quality_conservative', 'label': 'Quality Conservative'},
}
VIDEO_UPSCALE_TARGETS = {
    '1280x720': {'id': '1280x720', 'label': '1280 × 720', 'width': 1280, 'height': 720},
    '1920x1080': {'id': '1920x1080', 'label': '1920 × 1080', 'width': 1920, 'height': 1080},
    '2560x1440': {'id': '2560x1440', 'label': '2560 × 1440', 'width': 2560, 'height': 1440},
}
VIDEO_UPSCALE_CONTAINERS = {'mp4', 'mov', 'webm'}
VIDEO_UPSCALE_CODECS = {'auto', 'h264', 'hevc'}
VIDEO_UPSCALE_FPS_MODES = {'preserve', 'custom'}


def ensure_video_upscale_dirs() -> None:
    ensure_generation_dirs()
    VIDEO_UPSCALE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_UPSCALE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_UPSCALE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def normalize_video_upscale_profile(value: Any) -> str:
    clean = str(value or 'fast_local').strip().lower() or 'fast_local'
    return clean if clean in VIDEO_UPSCALE_PROFILES else 'fast_local'


def normalize_video_upscale_target(value: Any) -> str:
    clean = str(value or '1920x1080').strip().lower() or '1920x1080'
    return clean if clean in VIDEO_UPSCALE_TARGETS else '1920x1080'


def normalize_video_upscale_container(value: Any) -> str:
    clean = str(value or 'mp4').strip().lower() or 'mp4'
    return clean if clean in VIDEO_UPSCALE_CONTAINERS else 'mp4'


def normalize_video_upscale_codec(value: Any, *, container: str = 'mp4') -> str:
    clean = str(value or 'auto').strip().lower() or 'auto'
    if clean not in VIDEO_UPSCALE_CODECS:
        clean = 'auto'
    if container == 'webm' and clean in {'h264', 'hevc'}:
        return 'auto'
    return clean


def normalize_video_upscale_fps_mode(value: Any) -> str:
    clean = str(value or 'preserve').strip().lower() or 'preserve'
    return clean if clean in VIDEO_UPSCALE_FPS_MODES else 'preserve'


def clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        parsed = default
    return max(low, min(high, parsed))


def save_upscale_input_video(raw: bytes, filename: str, *, prefix: str = 'upscale_source') -> dict[str, Any]:
    if not raw:
        raise ValueError('Source video file was empty.')
    ensure_video_upscale_dirs()
    source_name = str(filename or prefix).strip() or prefix
    stem = safe_name(Path(source_name).stem) or prefix
    suffix = Path(source_name).suffix[:12] or '.mp4'
    target = VIDEO_UPSCALE_INPUT_DIR / f'{prefix}_{uuid4().hex[:8]}_{stem}{suffix}'
    target.write_bytes(raw)
    return {
        'path': target,
        'filename': target.name,
        'bytes': len(raw),
    }


def probe_video(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    cmd = [
        'ffprobe', '-v', 'error', '-print_format', 'json',
        '-show_streams', '-show_format', str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout or '{}')
    streams = payload.get('streams') if isinstance(payload.get('streams'), list) else []
    stream = next((item for item in streams if isinstance(item, dict) and item.get('codec_type') == 'video'), None)
    if not stream:
        raise ValueError('No video stream was found in the selected source video.')
    width = int(stream.get('width') or 0)
    height = int(stream.get('height') or 0)
    fps_text = str(stream.get('avg_frame_rate') or stream.get('r_frame_rate') or '0/1').strip() or '0/1'
    try:
        fps = float(Fraction(fps_text)) if fps_text not in {'0/0', '0'} else 0.0
    except Exception:
        fps = 0.0
    duration_text = str(stream.get('duration') or (payload.get('format') or {}).get('duration') or '').strip()
    try:
        duration_seconds = max(0.0, float(duration_text))
    except Exception:
        duration_seconds = 0.0
    return {
        'width': width,
        'height': height,
        'fps': fps,
        'duration_seconds': duration_seconds,
        'codec_name': str(stream.get('codec_name') or '').strip(),
        'pix_fmt': str(stream.get('pix_fmt') or '').strip(),
    }


def fit_resolution(src_width: int, src_height: int, target_key: str) -> dict[str, Any]:
    preset = VIDEO_UPSCALE_TARGETS[normalize_video_upscale_target(target_key)]
    src_width = max(2, int(src_width or preset['width']))
    src_height = max(2, int(src_height or preset['height']))
    target_w = int(preset['width'])
    target_h = int(preset['height'])
    scale = min(target_w / src_width, target_h / src_height)
    out_w = max(2, int(round((src_width * scale) / 2.0) * 2))
    out_h = max(2, int(round((src_height * scale) / 2.0) * 2))
    return {
        'preset': preset['id'],
        'preset_label': preset['label'],
        'width': out_w,
        'height': out_h,
        'target_width': target_w,
        'target_height': target_h,
        'source_width': src_width,
        'source_height': src_height,
    }


def build_local_output_url(job_id: str, filename: str) -> str:
    return f"/api/video/output-file/{safe_name(job_id) or 'video_job'}/{filename}"


def output_route_filename(path: str | Path) -> str:
    return Path(path).name


def normalize_video_upscale_payload(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(data or {})
    container = normalize_video_upscale_container(payload.get('output_container') or payload.get('container'))
    fps_mode = normalize_video_upscale_fps_mode(payload.get('fps_mode'))
    output_fps = clamp_int(payload.get('output_fps') or payload.get('custom_fps') or 24, 24, 8, 60)
    source_ref = payload.get('source_output_ref') if isinstance(payload.get('source_output_ref'), dict) else {}
    return {
        **payload,
        'surface': 'video',
        'family': 'local_ffmpeg',
        'workflow_type': 'video_upscale',
        'lane': 'upscale',
        'upscale_profile': normalize_video_upscale_profile(payload.get('upscale_profile') or payload.get('profile')),
        'target_resolution': normalize_video_upscale_target(payload.get('target_resolution') or payload.get('target_size')),
        'fps_mode': fps_mode,
        'output_fps': output_fps,
        'output_container': container,
        'output_codec': normalize_video_upscale_codec(payload.get('output_codec') or payload.get('codec'), container=container),
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


def validate_video_upscale_payload(data: dict[str, Any] | None = None) -> list[str]:
    payload = normalize_video_upscale_payload(data)
    errors: list[str] = []
    if not payload['source_video_local_path'] and not payload['source_video'] and not payload['source_output_ref'].get('view_url') and not payload['source_output_ref'].get('local_path'):
        errors.append('Select a source video or send an existing output into the Upscale lane first.')
    if payload['output_container'] == 'webm' and payload['output_codec'] in {'h264', 'hevc'}:
        errors.append('WebM stays on auto / VP9 in this first Upscale lane. Pick MP4 or MOV for H.264 / HEVC.')
    return errors


def build_upscale_output_paths(job_id: str, *, source_name: str = 'video', container: str = 'mp4') -> dict[str, Path]:
    ensure_video_upscale_dirs()
    stem = safe_name(Path(source_name).stem) or 'video'
    job_safe = safe_name(job_id) or 'video_job'
    filename = f'{job_safe}_{stem}_upscaled.{container}'
    progress_path = VIDEO_UPSCALE_RUNTIME_DIR / f'{job_safe}.progress'
    log_path = VIDEO_UPSCALE_RUNTIME_DIR / f'{job_safe}.log'
    output_path = VIDEO_UPSCALE_OUTPUT_DIR / filename
    return {
        'filename': filename,
        'output_path': output_path,
        'progress_path': progress_path,
        'log_path': log_path,
    }


def build_upscale_ffmpeg_command(*, source_path: str | Path, output_path: str | Path, progress_path: str | Path, output_width: int, output_height: int, output_fps: int, container: str, codec: str, upscale_profile: str) -> list[str]:
    vf_parts = [f'scale={int(output_width)}:{int(output_height)}:flags=lanczos']
    if normalize_video_upscale_profile(upscale_profile) == 'quality_conservative':
        vf_parts.append('unsharp=5:5:0.25:3:3:0.0')
    vf_chain = ','.join(vf_parts)
    cmd = [
        'ffmpeg', '-y', '-i', str(source_path),
        '-map', '0:v:0', '-map', '0:a?',
        '-vf', vf_chain,
        '-r', str(int(output_fps)),
    ]
    clean_container = normalize_video_upscale_container(container)
    clean_codec = normalize_video_upscale_codec(codec, container=clean_container)
    profile = normalize_video_upscale_profile(upscale_profile)
    if clean_container in {'mp4', 'mov'}:
        if clean_codec == 'hevc':
            cmd += ['-c:v', 'libx265', '-crf', '22' if profile == 'quality_conservative' else '24', '-preset', 'medium', '-tag:v', 'hvc1']
        else:
            cmd += ['-c:v', 'libx264', '-crf', '18' if profile == 'quality_conservative' else '20', '-preset', 'slow' if profile == 'quality_conservative' else 'faster']
        cmd += ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart']
    else:
        cmd += ['-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '30' if profile == 'quality_conservative' else '34', '-row-mt', '1', '-deadline', 'good', '-cpu-used', '2' if profile == 'quality_conservative' else '4', '-c:a', 'libopus', '-b:a', '128k']
    cmd += ['-progress', str(progress_path), '-nostats', str(output_path)]
    return cmd


def spawn_video_upscale_process(*, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_video_upscale_payload(payload)
    source_path = Path(clean.get('source_video_local_path') or clean.get('source_video') or '')
    if not source_path.exists():
        raise ValueError('The selected source video file was not found locally.')
    source_meta = probe_video(source_path)
    target = fit_resolution(source_meta['width'], source_meta['height'], clean['target_resolution'])
    fps_value = int(round(source_meta['fps'])) if clean['fps_mode'] == 'preserve' and source_meta.get('fps') else int(clean['output_fps'])
    fps_value = max(8, min(60, fps_value or int(clean['output_fps']) or 24))
    paths = build_upscale_output_paths(job_id, source_name=source_path.name, container=clean['output_container'])
    for file_path in (paths['output_path'], paths['progress_path'], paths['log_path']):
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    cmd = build_upscale_ffmpeg_command(
        source_path=source_path,
        output_path=paths['output_path'],
        progress_path=paths['progress_path'],
        output_width=target['width'],
        output_height=target['height'],
        output_fps=fps_value,
        container=clean['output_container'],
        codec=clean['output_codec'],
        upscale_profile=clean['upscale_profile'],
    )
    log_handle = open(paths['log_path'], 'ab')
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, start_new_session=True)
    log_handle.close()
    return {
        **clean,
        'source_video_local_path': str(source_path),
        'source_video_label': clean.get('source_video_label') or clean.get('source_output_ref', {}).get('label') or source_path.name,
        'source_probe': source_meta,
        'resolved_output_width': target['width'],
        'resolved_output_height': target['height'],
        'resolved_target_width': target['target_width'],
        'resolved_target_height': target['target_height'],
        'resolved_fps': fps_value,
        'upscale_pid': int(proc.pid),
        'upscale_process_group_id': int(proc.pid),
        'upscale_command': ' '.join(shlex.quote(part) for part in cmd),
        'upscale_output_path': str(paths['output_path']),
        'upscale_output_filename': str(paths['filename']),
        'upscale_progress_path': str(paths['progress_path']),
        'upscale_log_path': str(paths['log_path']),
    }


def read_ffmpeg_progress(progress_path: str | Path, *, duration_seconds: float = 0.0) -> dict[str, Any]:
    path = Path(progress_path)
    if not path.exists():
        return {'percent': 5, 'detail': 'Queued'}
    text = path.read_text(encoding='utf-8', errors='ignore')
    values: dict[str, str] = {}
    for line in text.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    progress = str(values.get('progress') or '').strip().lower()
    out_time_raw = values.get('out_time_us') or values.get('out_time_ms') or '0'
    try:
        out_time_us = float(out_time_raw)
    except Exception:
        out_time_us = 0.0
    if values.get('out_time_ms') and not values.get('out_time_us'):
        out_time_us *= 1000.0
    percent = 5
    if duration_seconds > 0:
        percent = int(max(5, min(99, round((out_time_us / 1_000_000.0) / duration_seconds * 100.0))))
    detail = 'Running local upscale'
    if progress == 'end':
        percent = 100
        detail = 'Completed'
    return {'percent': percent, 'detail': detail}


def process_alive(pid: Any) -> bool:
    try:
        clean = int(pid)
    except Exception:
        return False
    if clean <= 0:
        return False
    try:
        result = subprocess.run(['ps', '-o', 'stat=', '-p', str(clean)], capture_output=True, text=True, check=False)
        status = str(result.stdout or '').strip()
        if not status:
            return False
        if 'Z' in status.upper():
            return False
        return True
    except Exception:
        try:
            os.kill(clean, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False


def tail_text(path: str | Path, limit: int = 1200) -> str:
    target = Path(path)
    if not target.exists():
        return ''
    raw = target.read_text(encoding='utf-8', errors='ignore')
    return raw[-limit:].strip()


def build_local_video_output_record(*, job_id: str, payload: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
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
        'subfolder': 'local_video_upscale',
        'type': 'local',
        'duration_seconds': payload.get('source_probe', {}).get('duration_seconds'),
        'fps': payload.get('resolved_fps') or payload.get('output_fps'),
        'size_preset': f"{payload.get('resolved_output_width')}x{payload.get('resolved_output_height')}",
        'mime_type': mime_type,
    }


def sync_local_video_upscale_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    if str(payload.get('workflow_type') or '').strip() != 'video_upscale':
        return job
    current_state = str(job.get('status') or job.get('state') or 'queued').strip().lower() or 'queued'
    if current_state in {'completed', 'failed', 'cancelled'}:
        return job
    duration_seconds = float((payload.get('source_probe') or {}).get('duration_seconds') or 0.0)
    progress = read_ffmpeg_progress(payload.get('upscale_progress_path') or '', duration_seconds=duration_seconds)
    output_path = Path(str(payload.get('upscale_output_path') or ''))
    pid = payload.get('upscale_pid')
    if process_alive(pid):
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'running',
            'status_text': 'Running local Upscale lane.',
            'progress': progress,
        }) or job
    if output_path.exists() and output_path.stat().st_size > 0:
        output = build_local_video_output_record(job_id=str(job.get('job_id') or job.get('id') or ''), payload=payload, output_path=output_path)
        return update_generation_job(job.get('job_id') or job.get('id') or '', {
            'state': 'completed',
            'status_text': 'Upscale finished locally.',
            'progress': {'percent': 100, 'detail': 'Completed'},
            'outputs': [output],
            'error': '',
        }) or job
    log_tail = tail_text(payload.get('upscale_log_path') or '')
    return update_generation_job(job.get('job_id') or job.get('id') or '', {
        'state': 'failed',
        'status_text': 'The local Upscale lane failed before a deliverable file was written.',
        'progress': {'percent': max(5, int(progress.get('percent') or 5)), 'detail': 'Failed'},
        'error': log_tail or 'Local Upscale lane failed.',
    }) or job


def cancel_local_video_upscale_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get('payload') if isinstance(job.get('payload'), dict) else {}
    pid = payload.get('upscale_process_group_id') or payload.get('upscale_pid')
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
        'status_text': 'Stopped from Neo Studio. Local Upscale lane interrupted.',
        'progress': {'percent': 0, 'detail': 'Cancelled'},
        'error': '',
    }) or job
