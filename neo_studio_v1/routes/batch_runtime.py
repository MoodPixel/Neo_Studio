from __future__ import annotations

import asyncio
import csv
import json
import os
import platform
import re
import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4

from ..utils.caption_contract import build_caption_settings, normalize_batch_caption_mode, normalize_component_type, normalize_detail_level
from ..utils.config import APP_DIR
from ..utils.kobold import caption_image_with_settings
from ..utils.library_captions import image_files_in_folder, save_caption_from_path
from ..utils.library_settings_store import list_categories
from ..utils.library_stats import stats
from ..utils.logging_utils import get_logger
from ..utils.storage_io import atomic_write_json as shared_atomic_write_json, atomic_write_text as shared_atomic_write_text
from ..utils.shared_data_paths import studio_data_path
from .common import parse_bool, parse_exts

logger = get_logger(__name__)

BATCH_JOBS: dict[str, dict] = {}
BATCH_LOCK = threading.Lock()
BATCH_STATE_DIR = studio_data_path('batch_jobs', legacy_rel='batch_jobs')
BATCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
BATCH_POST_ACTION_COUNTDOWN = 60
ACTIVE_BATCH_THREADS: set[str] = set()

_ALLOWED_DATASET_TRANSFER_MODES = {'copy', 'move'}
_ALLOWED_DATASET_LOG_FORMATS = {'none', 'csv', 'json'}
_TERMINAL_FILE_STATES = {'completed', 'failed', 'skipped'}
_ORPHAN_ACTIVE_JOB_STATES = {'queued', 'running', 'cancelling'}


def _normalize_dataset_transfer_mode(value: str) -> str:
    value = (value or 'copy').strip().lower()
    return value if value in _ALLOWED_DATASET_TRANSFER_MODES else 'copy'


def _normalize_dataset_log_format(value: str) -> str:
    value = (value or 'csv').strip().lower()
    return value if value in _ALLOWED_DATASET_LOG_FORMATS else 'csv'


def _dataset_token(value: str, fallback: str = 'dataset') -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '').strip()).strip('_')
    return cleaned or fallback


def _dataset_sequence_number(params: dict, image_path: str | Path, index: int) -> int:
    seq_map = params.get('dataset_sequence_map') or {}
    key = str(image_path)
    try:
        value = int(seq_map.get(key))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return max(1, int(params.get('numbering_start') or 1)) + max(0, int(index) - 1)


def _dataset_output_base(params: dict, image_path: str | Path, index: int) -> Path:
    img = Path(image_path)
    output_root = Path(str(params.get('output_folder') or '')).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    if params.get('dataset_rename_images', True):
        seq = _dataset_sequence_number(params, img, index)
        padding = max(1, int(params.get('dataset_number_padding') or 4))
        num_text = str(seq).zfill(padding)
        prefix = _dataset_token(params.get('dataset_name_prefix') or 'dataset', 'dataset')
        pattern = str(params.get('dataset_name_pattern') or '{prefix}_{num}').strip() or '{prefix}_{num}'
        base_name = (pattern
            .replace('{prefix}', prefix)
            .replace('{num}', num_text)
            .replace('{n}', num_text)
            .replace('{index}', str(seq)))
        base_name = _dataset_token(base_name, f'{prefix}_{num_text}')
        return output_root / base_name
    src_root = Path(str(params.get('folder_path') or '')).expanduser()
    try:
        rel = img.relative_to(src_root)
        return (output_root / rel).with_suffix('')
    except ValueError:
        return output_root / img.stem


def _dataset_image_output_path(params: dict, image_path: str | Path, index: int) -> Path:
    img = Path(image_path)
    target = _dataset_output_base(params, img, index).with_suffix(img.suffix.lower() or img.suffix or '.png')
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _dataset_txt_output_path(params: dict, image_path: str | Path, index: int) -> Path:
    target = _dataset_output_base(params, image_path, index).with_suffix('.txt')
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _dataset_log_path(params: dict) -> Path | None:
    log_format = _normalize_dataset_log_format(params.get('dataset_log_format') or 'csv')
    if log_format == 'none':
        return None
    output_root = Path(str(params.get('output_folder') or '')).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root / f'dataset_prepare_log.{log_format}'


def _state_path(job_id: str) -> Path:
    return BATCH_STATE_DIR / f'{job_id}.json'


def _now() -> float:
    return time.time()


def _json_safe(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    shared_atomic_write_text(path, text)


def _atomic_write_json(path: Path, payload: dict | list) -> None:
    shared_atomic_write_json(path, _json_safe(payload))


def _write_dataset_prepare_log(params: dict, rows: list[dict]) -> Path | None:
    path = _dataset_log_path(params)
    if not path:
        return None
    fields = [
        'original_filename',
        'original_path',
        'new_filename',
        'output_image_path',
        'caption_file',
        'action',
        'result',
        'caption_status',
        'error_message',
    ]
    if path.suffix.lower() == '.json':
        _atomic_write_json(path, rows)
        return path
    tmp = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, '') for field in fields})
    os.replace(tmp, path)
    return path


def _dataset_row(img: Path, *, image_target: Path | None = None, txt_target: Path | None = None, action: str = '', result: str = '', caption_status: str = '', error_message: str = '') -> dict:
    return {
        'original_filename': img.name,
        'original_path': str(img),
        'new_filename': image_target.name if image_target else '',
        'output_image_path': str(image_target) if image_target else '',
        'caption_file': str(txt_target) if txt_target else '',
        'action': action,
        'result': result,
        'caption_status': caption_status,
        'error_message': error_message,
    }


def _normalize_file_status_record(path: str, record: dict | None = None) -> dict:
    meta = dict(record or {})
    return {
        'path': path,
        'name': meta.get('name') or Path(path).name,
        'status': str(meta.get('status') or 'pending'),
        'started_at': float(meta.get('started_at') or 0.0),
        'finished_at': float(meta.get('finished_at') or 0.0),
        'message': str(meta.get('message') or ''),
        'error_message': str(meta.get('error_message') or ''),
        'output_image_path': str(meta.get('output_image_path') or ''),
        'output_caption_path': str(meta.get('output_caption_path') or ''),
        'action': str(meta.get('action') or ''),
    }


def _ensure_file_statuses(state: dict, images: list[Path] | None = None) -> dict[str, dict]:
    existing = state.get('file_statuses') or {}
    normalized: dict[str, dict] = {}
    if isinstance(existing, dict):
        for path, record in existing.items():
            normalized[str(path)] = _normalize_file_status_record(str(path), record if isinstance(record, dict) else None)
    ordered_paths = []
    if images:
        ordered_paths.extend(str(p) for p in images)
    elif state.get('params', {}).get('target_images'):
        ordered_paths.extend(str(p) for p in (state.get('params', {}).get('target_images') or []))
    elif state.get('remaining_items'):
        ordered_paths.extend(str(p) for p in (state.get('remaining_items') or []))
    if state.get('current_item_path'):
        ordered_paths.append(str(state['current_item_path']))
    for path in ordered_paths:
        normalized.setdefault(path, _normalize_file_status_record(path))
    state['file_statuses'] = normalized
    return normalized


def _set_file_status(state: dict, image_path: str | Path, status: str, **updates) -> None:
    key = str(image_path)
    statuses = _ensure_file_statuses(state)
    record = dict(statuses.get(key) or _normalize_file_status_record(key))
    record['status'] = status
    for field, value in updates.items():
        if value is None:
            continue
        if isinstance(value, Path):
            value = str(value)
        record[field] = value
    if status == 'running':
        record['started_at'] = float(record.get('started_at') or _now())
        record['finished_at'] = 0.0
    elif status in _TERMINAL_FILE_STATES:
        record['finished_at'] = float(record.get('finished_at') or _now())
    statuses[key] = _normalize_file_status_record(key, record)
    state['file_statuses'] = statuses


def _remaining_items_from_state(state: dict) -> list[str]:
    statuses = _ensure_file_statuses(state)
    return [path for path, meta in statuses.items() if meta.get('status') in {'pending', 'running'}]


def _counts_from_state(state: dict) -> tuple[int, int, int, int, int]:
    statuses = _ensure_file_statuses(state)
    saved = sum(1 for meta in statuses.values() if meta.get('status') == 'completed')
    skipped = sum(1 for meta in statuses.values() if meta.get('status') == 'skipped')
    errors = sum(1 for meta in statuses.values() if meta.get('status') == 'failed')
    processed = saved + skipped + errors
    duplicates = max(0, int(state.get('duplicates') or 0))
    return processed, saved, skipped, errors, duplicates


def _dataset_outputs_valid(params: dict, image_path: str | Path, index: int) -> tuple[bool, Path, Path | None]:
    image_target = _dataset_image_output_path(params, image_path, index)
    needs_caption = bool(params.get('dataset_caption_images'))
    save_txt = bool(params.get('dataset_save_txt')) and needs_caption
    txt_target = _dataset_txt_output_path(params, image_path, index) if save_txt else None
    image_ok = image_target.exists() and image_target.is_file()
    txt_ok = True if not txt_target else txt_target.exists() and txt_target.is_file() and txt_target.stat().st_size > 0
    return image_ok and txt_ok, image_target, txt_target


def persist_batch_state(job_id: str) -> None:
    with BATCH_LOCK:
        state = BATCH_JOBS.get(job_id)
        if not state:
            return
        payload = dict(state)
        _ensure_file_statuses(payload)
        payload['remaining_items'] = _remaining_items_from_state(payload)
        processed, saved, skipped, errors, duplicates = _counts_from_state(payload)
        payload['processed'] = processed
        payload['saved'] = saved
        payload['skipped'] = skipped
        payload['errors'] = errors
        payload['duplicates'] = duplicates
        payload['completed_files'] = saved
        payload['failed_files'] = errors
        payload['skipped_files'] = skipped
        payload = _json_safe(payload)
    try:
        _atomic_write_json(_state_path(job_id), payload)
    except (OSError, TypeError, ValueError):
        logger.exception('Failed to persist batch state for %s', job_id)


def _repair_orphaned_state(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    job_id = str(data.get('job_id') or '')
    status = str(data.get('status') or '').strip().lower()
    if status not in _ORPHAN_ACTIVE_JOB_STATES:
        _ensure_file_statuses(data)
        data['remaining_items'] = _remaining_items_from_state(data)
        processed, saved, skipped, errors, duplicates = _counts_from_state(data)
        data['processed'] = processed
        data['saved'] = saved
        data['skipped'] = skipped
        data['errors'] = errors
        data['duplicates'] = duplicates
        data['completed_files'] = saved
        data['failed_files'] = errors
        data['skipped_files'] = skipped
        return data
    with BATCH_LOCK:
        is_active = job_id in ACTIVE_BATCH_THREADS
    if is_active:
        return data
    statuses = _ensure_file_statuses(data)
    interrupted_item = ''
    for path, meta in list(statuses.items()):
        if meta.get('status') == 'running':
            statuses[path] = _normalize_file_status_record(path, {**meta, 'status': 'pending', 'message': 'Returned to queue after interruption.'})
            interrupted_item = path
    current_item_path = str(data.get('current_item_path') or '').strip()
    if current_item_path:
        meta = dict(statuses.get(current_item_path) or _normalize_file_status_record(current_item_path))
        if meta.get('status') not in _TERMINAL_FILE_STATES:
            meta['status'] = 'pending'
            meta['message'] = 'Returned to queue after interruption.'
            statuses[current_item_path] = _normalize_file_status_record(current_item_path, meta)
            interrupted_item = interrupted_item or current_item_path
    data['file_statuses'] = statuses
    data['status'] = 'interrupted'
    data['cancel_requested'] = False
    data['post_action_status'] = 'idle'
    data['post_action_execute_at'] = 0.0
    data['current_item_started_at'] = 0.0
    data['last_item_elapsed_seconds'] = 0.0
    data['remaining_items'] = _remaining_items_from_state(data)
    processed, saved, skipped, errors, duplicates = _counts_from_state(data)
    data['processed'] = processed
    data['saved'] = saved
    data['skipped'] = skipped
    data['errors'] = errors
    data['duplicates'] = duplicates
    data['completed_files'] = saved
    data['failed_files'] = errors
    data['skipped_files'] = skipped
    if interrupted_item:
        data['current_item_name'] = Path(interrupted_item).name
        data['current_item_path'] = interrupted_item
    item_text = Path(interrupted_item).name if interrupted_item else 'batch queue'
    data['message'] = f'Interrupted batch detected. Ready to resume from {item_text}.'
    data['interrupted_at'] = float(data.get('interrupted_at') or _now())
    return data


def load_batch_state(job_id: str) -> dict | None:
    path = _state_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            before = json.dumps(_json_safe(data), sort_keys=True, ensure_ascii=False)
            repaired = _repair_orphaned_state(data)
            after = json.dumps(_json_safe(repaired), sort_keys=True, ensure_ascii=False)
            if after != before:
                _atomic_write_json(path, repaired)
            return repaired
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logger.exception('Failed to load batch state for %s', job_id)
    return None


def _heal_saved_batch_states() -> None:
    for path in sorted(BATCH_STATE_DIR.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        before = json.dumps(_json_safe(data), sort_keys=True, ensure_ascii=False)
        repaired = _repair_orphaned_state(data)
        after = json.dumps(_json_safe(repaired), sort_keys=True, ensure_ascii=False)
        if after != before:
            try:
                _atomic_write_json(path, repaired)
            except OSError:
                logger.exception('Failed to heal orphaned batch state %s', path.name)


def list_saved_batch_jobs() -> list[dict]:
    _heal_saved_batch_states()
    items: list[dict] = []
    for path in sorted(BATCH_STATE_DIR.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        items.append({
            'job_id': data.get('job_id') or path.stem,
            'status': data.get('status') or 'unknown',
            'message': data.get('message') or '',
            'folder_path': data.get('params', {}).get('folder_path', ''),
            'output_folder': data.get('params', {}).get('output_folder', ''),
            'mode': data.get('mode') or data.get('params', {}).get('mode', 'dataset'),
            'total_items': int(data.get('total_items') or 0),
            'processed': int(data.get('processed') or 0),
            'saved': int(data.get('saved') or 0),
            'skipped': int(data.get('skipped') or 0),
            'errors': int(data.get('errors') or 0),
            'started_at': float(data.get('started_at') or 0.0),
            'finished_at': float(data.get('finished_at') or 0.0),
            'interrupted': str(data.get('status') or '') == 'interrupted',
        })
    items.sort(key=lambda x: x.get('started_at') or 0.0, reverse=True)
    return items[:20]


def batch_summary(state: dict) -> str:
    processed = int(state.get('processed') or 0)
    saved = int(state.get('saved') or 0)
    skipped = int(state.get('skipped') or 0)
    errors = int(state.get('errors') or 0)
    duplicates = int(state.get('duplicates') or 0)
    parts = [f'Processed: {processed}', f'saved: {saved}', f'skipped: {skipped}', f'errors: {errors}']
    if duplicates:
        parts.append(f'duplicates: {duplicates}')
    return ', '.join(parts) + '.'


def _status_with_eta(payload: dict) -> dict:
    now = _now()
    started = float(payload.get('started_at') or now)
    current_started = float(payload.get('current_item_started_at') or 0.0)
    payload['elapsed_total_seconds'] = max(0.0, now - started)
    payload['elapsed_current_seconds'] = max(0.0, now - current_started) if current_started and payload.get('status') == 'running' else float(payload.get('last_item_elapsed_seconds') or 0.0)
    total = max(0, int(payload.get('total_items') or 0))
    current = max(0, int(payload.get('current_index') or 0))
    payload['progress_percent'] = (current / total * 100.0) if total else 0.0
    avg_seconds = 0.0
    processed = max(0, int(payload.get('processed') or 0))
    if processed > 0 and payload['elapsed_total_seconds'] > 0:
        avg_seconds = payload['elapsed_total_seconds'] / processed
    elif current > 0 and payload['elapsed_total_seconds'] > 0:
        avg_seconds = payload['elapsed_total_seconds'] / current
    remaining = max(0, total - current)
    payload['avg_item_seconds'] = avg_seconds
    payload['eta_seconds'] = max(0.0, avg_seconds * remaining) if avg_seconds and payload.get('status') in {'running', 'queued', 'cancelling', 'interrupted'} else 0.0
    return payload


def batch_status_payload(job_id: str) -> dict | None:
    with BATCH_LOCK:
        state = BATCH_JOBS.get(job_id)
    if not state:
        state = load_batch_state(job_id)
        if state:
            with BATCH_LOCK:
                BATCH_JOBS[job_id] = state
    if not state:
        return None
    with BATCH_LOCK:
        live = BATCH_JOBS.get(job_id) or state
        payload = dict(live)
    payload = _repair_orphaned_state(payload)
    payload = _status_with_eta(payload)
    payload['summary'] = batch_summary(payload)
    payload['detail_lines'] = list(payload.get('detail_lines') or [])[-300:]
    payload['error_lines'] = list(payload.get('error_lines') or [])[-100:]
    payload['duplicate_lines'] = list(payload.get('duplicate_lines') or [])[-100:]
    payload['failed_items'] = list(payload.get('failed_items') or [])[-200:]
    payload['remaining_items'] = _remaining_items_from_state(payload)
    payload['remaining_items_count'] = len(payload.get('remaining_items') or [])
    payload['ok'] = True
    payload['job_id'] = job_id
    payload['recent_jobs'] = list_saved_batch_jobs()
    if payload.get('post_action_execute_at'):
        payload['post_action_seconds_left'] = max(0, int(float(payload['post_action_execute_at']) - _now()))
    else:
        payload['post_action_seconds_left'] = 0
    return payload


def update_batch_state(job_id: str, persist: bool = True, **updates) -> None:
    with BATCH_LOCK:
        state = BATCH_JOBS.get(job_id)
        if not state:
            return
        state.update(updates)
        _ensure_file_statuses(state)
        state['remaining_items'] = _remaining_items_from_state(state)
        processed, saved, skipped, errors, duplicates = _counts_from_state(state)
        state['processed'] = processed
        state['saved'] = saved
        state['skipped'] = skipped
        state['errors'] = errors
        state['duplicates'] = duplicates
        state['completed_files'] = saved
        state['failed_files'] = errors
        state['skipped_files'] = skipped
    if persist:
        persist_batch_state(job_id)


def _mark_cancel(job_id: str) -> dict | None:
    payload = batch_status_payload(job_id)
    if not payload:
        return None
    status = payload.get('status')
    if status in {'completed', 'failed', 'cancelled'}:
        return payload
    if status == 'interrupted':
        update_batch_state(job_id, status='cancelled', message='Interrupted batch dismissed.', finished_at=_now(), current_item_name='', current_item_path='')
        return batch_status_payload(job_id)
    update_batch_state(job_id, cancel_requested=True, status='cancelling', message='Cancel requested. The batch will stop after the current file finishes.')
    return batch_status_payload(job_id)


def request_batch_cancel(job_id: str) -> dict | None:
    return _mark_cancel(job_id)


def _write_export_log(state: dict) -> Path:
    log_path = BATCH_STATE_DIR / f"{state.get('job_id','batch')}_log.txt"
    lines: list[str] = []
    lines.append('Neo Studio Batch Run Log')
    lines.append('=' * 30)
    lines.append(f"Job ID: {state.get('job_id','')}")
    lines.append(f"Status: {state.get('status','')}")
    lines.append(f"Mode: {state.get('mode','')}")
    lines.append(f"Folder: {state.get('params', {}).get('folder_path','')}")
    lines.append(f"Output folder: {state.get('params', {}).get('output_folder','')}")
    lines.append(f"Summary: {batch_summary(state)}")
    lines.append('')
    if state.get('duplicate_lines'):
        lines.append('Duplicate Summary')
        lines.append('-' * 18)
        lines.extend(state.get('duplicate_lines') or [])
        lines.append('')
    if state.get('error_lines'):
        lines.append('Errors')
        lines.append('-' * 18)
        lines.extend(state.get('error_lines') or [])
        lines.append('')
    failed_items = list(state.get('failed_items') or [])
    if failed_items:
        lines.append('Failed Files')
        lines.append('-' * 18)
        lines.extend(failed_items)
        lines.append('')
    if state.get('detail_lines'):
        lines.append('Details')
        lines.append('-' * 18)
        lines.extend(state.get('detail_lines') or [])
        lines.append('')
    _atomic_write_text(log_path, '\n'.join(lines))
    return log_path


def export_batch_log_payload(job_id: str) -> dict | None:
    payload = batch_status_payload(job_id)
    if not payload:
        return None
    log_path = _write_export_log(payload)
    return {
        'ok': True,
        'job_id': job_id,
        'filename': log_path.name,
        'path': str(log_path),
        'content': log_path.read_text(encoding='utf-8'),
        'message': 'Batch log exported.',
    }


def _windows_post_action_command(action: str) -> str | None:
    action = (action or '').strip().lower()
    if action == 'shutdown':
        return 'shutdown /s /t 0'
    if action == 'hibernate':
        return 'shutdown /h'
    if action == 'sleep':
        return 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0'
    return None


def _execute_post_action(job_id: str, action: str) -> None:
    command = _windows_post_action_command(action)
    if not command:
        return
    if platform.system().lower() != 'windows':
        update_batch_state(job_id, post_action_status='unsupported', message=f'Post-task action {action} is only enabled on Windows.')
        return
    try:
        update_batch_state(job_id, post_action_status='executing', message=f'Executing post-task action: {action}.')
        os.system(command)
    except Exception:
        logger.exception('Failed to execute post-task action %s for %s', action, job_id)
        update_batch_state(job_id, post_action_status='failed', message=f'Failed to execute post-task action: {action}.')


def _schedule_post_action(job_id: str, action: str) -> None:
    action = (action or 'none').strip().lower()
    if action in {'', 'none', 'do_nothing'}:
        return
    execute_at = _now() + BATCH_POST_ACTION_COUNTDOWN
    update_batch_state(job_id, post_action=action, post_action_status='countdown', post_action_execute_at=execute_at, message=f'Batch finished. {action.title()} will run in {BATCH_POST_ACTION_COUNTDOWN} seconds unless cancelled.')

    def worker():
        while True:
            state = batch_status_payload(job_id)
            if not state:
                return
            if state.get('post_action_status') == 'cancelled':
                return
            left = int(state.get('post_action_seconds_left') or 0)
            if left <= 0:
                break
            time.sleep(1)
        latest = batch_status_payload(job_id)
        if latest and latest.get('post_action_status') != 'cancelled':
            _execute_post_action(job_id, action)

    threading.Thread(target=worker, daemon=True).start()


def cancel_post_action(job_id: str) -> dict | None:
    payload = batch_status_payload(job_id)
    if not payload:
        return None
    if not payload.get('post_action_execute_at'):
        return payload
    update_batch_state(job_id, post_action_status='cancelled', post_action_execute_at=0.0, message='Post-task action cancelled.')
    return batch_status_payload(job_id)


def _build_retry_or_resume_params(job_id: str, *, retry_failed_only: bool = False) -> tuple[dict, int] | tuple[None, int]:
    state = batch_status_payload(job_id)
    if not state:
        return None, 0
    params = dict(state.get('params') or {})
    if not params:
        return None, 0
    statuses = state.get('file_statuses') or {}
    if retry_failed_only:
        target_items = [path for path, meta in statuses.items() if isinstance(meta, dict) and meta.get('status') == 'failed']
        if not target_items:
            target_items = [x for x in (state.get('failed_items') or []) if x]
    else:
        target_items = [path for path, meta in statuses.items() if isinstance(meta, dict) and meta.get('status') in {'pending', 'running'}]
        if not target_items:
            target_items = [x for x in (state.get('remaining_items') or []) if x]
        current_item = str(state.get('current_item_path') or '').strip()
        if current_item and current_item not in target_items:
            current_meta = statuses.get(current_item) or {}
            if not isinstance(current_meta, dict) or current_meta.get('status') not in _TERMINAL_FILE_STATES:
                target_items.insert(0, current_item)
    target_items = list(dict.fromkeys(target_items))
    if not target_items:
        return None, 0
    params['target_images'] = target_items
    return params, len(target_items)


def create_retry_batch_job(job_id: str) -> dict | None:
    params, count = _build_retry_or_resume_params(job_id, retry_failed_only=True)
    if not params:
        return None
    return create_batch_job(params, count, source_job_id=job_id, purpose='retry_failed')


def create_resume_batch_job(job_id: str) -> dict | None:
    params, count = _build_retry_or_resume_params(job_id, retry_failed_only=False)
    if not params:
        return None
    return create_batch_job(params, count, source_job_id=job_id, purpose='resume')


def _append_detail(detail_lines: list[str], message: str) -> None:
    detail_lines.append(message)
    del detail_lines[:-300]


def _append_error(error_lines: list[str], message: str) -> None:
    error_lines.append(message)
    del error_lines[:-100]


def _append_duplicate(duplicate_lines: list[str], message: str) -> None:
    duplicate_lines.append(message)
    del duplicate_lines[:-100]


async def run_batch_caption_job(job_id: str, params: dict) -> None:
    with BATCH_LOCK:
        ACTIVE_BATCH_THREADS.add(job_id)
    try:
        try:
            images = [Path(x) for x in (params.get('target_images') or []) if x]
            if not images:
                images = image_files_in_folder(params['folder_path'], recursive=params['recursive'], include_exts=params['include_exts'])
        except Exception as e:
            update_batch_state(job_id, status='failed', message=str(e), finished_at=_now())
            return
        if not images:
            update_batch_state(job_id, status='failed', message='No supported image files found in that folder.', finished_at=_now())
            return

        if params.get('mode') == 'dataset' and not str(params.get('output_folder') or '').strip():
            update_batch_state(job_id, status='failed', message='Dataset Preparation needs an output folder.', finished_at=_now())
            return

        with BATCH_LOCK:
            state = BATCH_JOBS.get(job_id)
            if state is None:
                return
            statuses = _ensure_file_statuses(state, images)
            for img in images:
                statuses.setdefault(str(img), _normalize_file_status_record(str(img)))
            state['file_statuses'] = statuses
            state['total_items'] = len(images)
            state['remaining_items'] = _remaining_items_from_state(state)
        persist_batch_state(job_id)

        error_lines: list[str] = []
        duplicate_lines: list[str] = []
        detail_lines: list[str] = []
        failed_items: list[str] = []
        dataset_log_rows: list[dict] = []
        counter = max(1, int(params['numbering_start'] or 1))
        total = len(images)
        update_batch_state(job_id, total_items=total, remaining_items=[str(p) for p in images], message=f'Queued {total} files.', dataset_log_path='')

        for idx, img in enumerate(images, start=1):
            img_path = str(img)
            item_started = _now()
            remaining_items = [str(p) for p in images[idx:]]
            with BATCH_LOCK:
                state = BATCH_JOBS.get(job_id)
                if state is None:
                    return
                _set_file_status(state, img_path, 'running', started_at=item_started, message='Processing file.')
            update_batch_state(
                job_id,
                status='running',
                current_index=idx,
                current_item_name=img.name,
                current_item_path=img_path,
                current_item_started_at=item_started,
                remaining_items=remaining_items,
                message=f'Processing {idx}/{total}: {img.name}',
                detail_lines=detail_lines,
                error_lines=error_lines,
                duplicate_lines=duplicate_lines,
                failed_items=failed_items,
            )
            try:
                if params['mode'] == 'dataset':
                    image_target = _dataset_image_output_path(params, img, idx)
                    needs_caption = bool(params.get('dataset_caption_images'))
                    save_txt = bool(params.get('dataset_save_txt')) and needs_caption
                    txt_target = _dataset_txt_output_path(params, img, idx) if save_txt else None
                    transfer_mode = _normalize_dataset_transfer_mode(params.get('dataset_transfer_mode') or 'copy')

                    valid_outputs, image_target, txt_target = _dataset_outputs_valid(params, img, idx)
                    if valid_outputs and params.get('dataset_skip_processed', True):
                        _append_detail(detail_lines, f'Skipped existing output: {img.name} -> {image_target.name}')
                        dataset_log_rows.append(_dataset_row(img, image_target=image_target, txt_target=txt_target, action=transfer_mode, result='skipped', caption_status='skipped_existing', error_message='Existing output already valid.'))
                        with BATCH_LOCK:
                            state = BATCH_JOBS.get(job_id)
                            if state:
                                _set_file_status(state, img_path, 'skipped', message='Existing output already valid.', output_image_path=image_target, output_caption_path=txt_target, action=transfer_mode, finished_at=_now())
                        continue

                    existing_outputs = []
                    if image_target.exists():
                        existing_outputs.append(image_target.name)
                    if save_txt and txt_target and txt_target.exists():
                        existing_outputs.append(txt_target.name)
                    if existing_outputs and not params.get('overwrite_existing'):
                        if params.get('dataset_skip_processed', True):
                            _append_detail(detail_lines, f"Skipped existing output: {img.name} -> {', '.join(existing_outputs)}")
                            dataset_log_rows.append(_dataset_row(img, image_target=image_target, txt_target=txt_target, action=transfer_mode, result='skipped', caption_status='skipped_existing', error_message='Existing output found.'))
                            with BATCH_LOCK:
                                state = BATCH_JOBS.get(job_id)
                                if state:
                                    _set_file_status(state, img_path, 'skipped', message='Existing output found.', output_image_path=image_target, output_caption_path=txt_target, action=transfer_mode, finished_at=_now())
                            continue
                        raise RuntimeError(f"Output already exists: {', '.join(existing_outputs)}")

                    caption_text = ''
                    caption_status = 'disabled'
                    finish_reason = ''
                    if needs_caption:
                        result = await caption_image_with_settings(
                            image_path=img_path,
                            model=params['model'],
                            prompt_style=params['prompt_style'],
                            caption_length=params['caption_length'],
                            custom_prompt=params['custom_prompt'],
                            max_tokens=params['max_new_tokens'],
                            temperature=params['temperature'],
                            top_p=params['top_p'],
                            top_k=params['top_k'],
                            prefix=params['prefix'],
                            suffix=params['suffix'],
                            output_style=params['output_style'],
                            caption_mode=params['caption_mode'],
                            detail_level=params['detail_level'],
                        )
                        caption_text = (result.get('text', '') or '').strip()
                        finish_reason = str(result.get('finish_reason', '') or '').strip().lower()
                        if not caption_text:
                            raise RuntimeError('No caption text was generated.')
                        if finish_reason == 'error' or caption_text.lower().startswith('vision error:') or caption_text == 'Invalid image file.':
                            raise RuntimeError(caption_text)
                        caption_status = 'generated'
                    image_target.parent.mkdir(parents=True, exist_ok=True)
                    if transfer_mode == 'move':
                        shutil.move(str(img), str(image_target))
                    else:
                        shutil.copy2(img, image_target)
                    if save_txt and txt_target:
                        _atomic_write_text(txt_target, caption_text + '\n')
                        _append_detail(detail_lines, f'Prepared dataset pair: {img.name} -> {image_target.name} + {txt_target.name}')
                    else:
                        _append_detail(detail_lines, f'Prepared dataset image: {img.name} -> {image_target.name}')
                    dataset_log_rows.append(_dataset_row(img, image_target=image_target, txt_target=txt_target, action=transfer_mode, result='saved', caption_status=caption_status))
                    with BATCH_LOCK:
                        state = BATCH_JOBS.get(job_id)
                        if state:
                            _set_file_status(state, img_path, 'completed', message='Dataset output written.', output_image_path=image_target, output_caption_path=txt_target, action=transfer_mode, finished_at=_now())
                else:
                    result = await caption_image_with_settings(
                        image_path=img_path,
                        model=params['model'],
                        prompt_style=params['prompt_style'],
                        caption_length=params['caption_length'],
                        custom_prompt=params['custom_prompt'],
                        max_tokens=params['max_new_tokens'],
                        temperature=params['temperature'],
                        top_p=params['top_p'],
                        top_k=params['top_k'],
                        prefix=params['prefix'],
                        suffix=params['suffix'],
                        output_style=params['output_style'],
                        caption_mode=params['caption_mode'],
                        detail_level=params['detail_level'],
                    )
                    caption_text = (result.get('text', '') or '').strip()
                    finish_reason = str(result.get('finish_reason', '') or '').strip().lower()
                    if not caption_text:
                        raise RuntimeError('No caption text was generated.')
                    if finish_reason == 'error' or caption_text.lower().startswith('vision error:') or caption_text == 'Invalid image file.':
                        raise RuntimeError(caption_text)
                    name = f"{params['base_name']}_{counter:03d}"
                    rec = save_caption_from_path(
                        name=name,
                        category=params['category'],
                        caption=caption_text,
                        image_path=img_path,
                        model=params['model'],
                        raw_caption=caption_text,
                        skip_duplicates=params['skip_duplicates'],
                        prompt_style=params['prompt_style'],
                        finish_reason=result.get('finish_reason', ''),
                        settings=params['settings'],
                        component_type=params['component_type'],
                        caption_mode=params['caption_mode'],
                        detail_level=params['detail_level'],
                    )
                    if rec is None:
                        _append_duplicate(duplicate_lines, f'Duplicate skipped: {img.name}')
                        _append_detail(detail_lines, f'Skipped duplicate: {img.name}')
                        with BATCH_LOCK:
                            state = BATCH_JOBS.get(job_id)
                            if state:
                                state['duplicates'] = int(state.get('duplicates') or 0) + 1
                                _set_file_status(state, img_path, 'skipped', message='Duplicate skipped by image hash.', finished_at=_now())
                    else:
                        counter += 1
                        _append_detail(detail_lines, f'Saved library entry: {img.name}')
                        with BATCH_LOCK:
                            state = BATCH_JOBS.get(job_id)
                            if state:
                                _set_file_status(state, img_path, 'completed', message='Library entry saved.', finished_at=_now())
            except Exception as e:
                failed_items.append(img_path)
                del failed_items[:-200]
                _append_error(error_lines, f'{img.name}: {e}')
                _append_detail(detail_lines, f'Error: {img.name} -> {e}')
                with BATCH_LOCK:
                    state = BATCH_JOBS.get(job_id)
                    if state:
                        _set_file_status(state, img_path, 'failed', message='Processing failed.', error_message=str(e), finished_at=_now())
                if params['mode'] == 'dataset':
                    try:
                        dataset_log_rows.append(_dataset_row(img, image_target=_dataset_image_output_path(params, img, idx), txt_target=_dataset_txt_output_path(params, img, idx) if params.get('dataset_caption_images') and params.get('dataset_save_txt') else None, action=_normalize_dataset_transfer_mode(params.get('dataset_transfer_mode') or 'copy'), result='error', caption_status='error', error_message=str(e)))
                    except Exception:
                        dataset_log_rows.append(_dataset_row(img, action=_normalize_dataset_transfer_mode(params.get('dataset_transfer_mode') or 'copy'), result='error', caption_status='error', error_message=str(e)))
            finally:
                state = batch_status_payload(job_id) or {}
                processed, saved_count, skipped, errors, duplicates = _counts_from_state(state)
                update_batch_state(
                    job_id,
                    processed=processed,
                    saved=saved_count,
                    skipped=skipped,
                    errors=errors,
                    duplicates=duplicates,
                    detail_lines=detail_lines,
                    error_lines=error_lines,
                    duplicate_lines=duplicate_lines,
                    failed_items=failed_items,
                    last_item_elapsed_seconds=max(0.0, _now() - item_started),
                )
                if state.get('cancel_requested'):
                    dataset_log_path = ''
                    if params['mode'] == 'dataset':
                        try:
                            written = _write_dataset_prepare_log(params, dataset_log_rows)
                            dataset_log_path = str(written) if written else ''
                            if written:
                                _append_detail(detail_lines, f'Dataset log written: {written}')
                        except Exception as log_error:
                            _append_error(error_lines, f'Dataset log failed: {log_error}')
                    final_message = f"Batch cancelled. {batch_summary({'processed': processed, 'saved': saved_count, 'skipped': skipped, 'errors': errors, 'duplicates': duplicates})}"
                    update_batch_state(
                        job_id,
                        status='cancelled',
                        message=final_message,
                        processed=processed,
                        saved=saved_count,
                        skipped=skipped,
                        errors=errors,
                        duplicates=duplicates,
                        current_index=idx,
                        finished_at=_now(),
                        stats=stats(),
                        categories=list_categories(),
                        dataset_log_path=dataset_log_path,
                        detail_lines=detail_lines,
                        error_lines=error_lines,
                        current_item_name='',
                        current_item_path='',
                        current_item_started_at=0.0,
                    )
                    _write_export_log(batch_status_payload(job_id) or {})
                    return

        dataset_log_path = ''
        if params['mode'] == 'dataset':
            try:
                written = _write_dataset_prepare_log(params, dataset_log_rows)
                dataset_log_path = str(written) if written else ''
                if written:
                    _append_detail(detail_lines, f'Dataset log written: {written}')
            except Exception as log_error:
                _append_error(error_lines, f'Dataset log failed: {log_error}')
                _append_detail(detail_lines, f'Dataset log failed: {log_error}')

        state = batch_status_payload(job_id) or {}
        processed, saved_count, skipped, errors, duplicates = _counts_from_state(state)
        final_message = f"Batch finished. {batch_summary({'processed': processed, 'saved': saved_count, 'skipped': skipped, 'errors': errors, 'duplicates': duplicates})}"
        update_batch_state(
            job_id,
            status='completed',
            message=final_message,
            processed=processed,
            saved=saved_count,
            skipped=skipped,
            errors=errors,
            duplicates=duplicates,
            current_index=total,
            current_item_name='',
            current_item_path='',
            current_item_started_at=0.0,
            remaining_items=[],
            finished_at=_now(),
            stats=stats(),
            categories=list_categories(),
            dataset_log_path=dataset_log_path,
            detail_lines=detail_lines,
            error_lines=error_lines,
        )
        state = batch_status_payload(job_id) or {}
        _write_export_log(state)
        _schedule_post_action(job_id, params.get('post_task_action', 'none'))
    finally:
        with BATCH_LOCK:
            ACTIVE_BATCH_THREADS.discard(job_id)


def start_batch_thread(job_id: str, params: dict) -> None:
    asyncio.run(run_batch_caption_job(job_id, params))


def create_batch_job(params: dict, image_count: int, *, source_job_id: str = '', purpose: str = 'run') -> dict:
    job_id = str(uuid4())
    target_images = [str(x) for x in (params.get('target_images') or []) if x]
    file_statuses = {path: _normalize_file_status_record(path) for path in target_images}
    state = {
        'job_id': job_id,
        'source_job_id': source_job_id,
        'purpose': purpose,
        'status': 'queued',
        'message': f'Queued {image_count} files.',
        'mode': params['mode'],
        'total_items': image_count,
        'current_index': 0,
        'current_item_name': '',
        'current_item_path': '',
        'current_item_started_at': 0.0,
        'last_item_elapsed_seconds': 0.0,
        'processed': 0,
        'saved': 0,
        'skipped': 0,
        'errors': 0,
        'duplicates': 0,
        'completed_files': 0,
        'failed_files': 0,
        'skipped_files': 0,
        'detail_lines': [],
        'error_lines': [],
        'duplicate_lines': [],
        'failed_items': [],
        'remaining_items': list(target_images),
        'file_statuses': file_statuses,
        'started_at': _now(),
        'finished_at': 0.0,
        'stats': {},
        'categories': [],
        'cancel_requested': False,
        'post_action': params.get('post_task_action', 'none'),
        'post_action_status': 'idle',
        'post_action_execute_at': 0.0,
        'dataset_log_path': '',
        'params': dict(params),
    }
    with BATCH_LOCK:
        BATCH_JOBS[job_id] = state
    persist_batch_state(job_id)
    thread = threading.Thread(target=start_batch_thread, args=(job_id, params), daemon=True)
    thread.start()
    payload = batch_status_payload(job_id) or {'ok': True, 'job_id': job_id}
    payload['message'] = f'Started batch for {image_count} files.'
    return payload


def normalized_batch_params(*, model: str, mode: str, folder_path: str, category: str, base_name: str, numbering_start: int,
    overwrite_existing: str, skip_existing_txt: str, skip_duplicates: str, recursive: str, include_exts: str,
    prompt_style: str, caption_length: str, custom_prompt: str, max_new_tokens: int, temperature: float,
    top_p: float, top_k: int, prefix: str, suffix: str, output_style: str, output_folder: str,
    component_type: str, caption_mode: str, detail_level: str, post_task_action: str,
    dataset_caption_images: str = 'true', dataset_save_txt: str = 'true', dataset_rename_images: str = 'true',
    dataset_transfer_mode: str = 'copy', dataset_skip_processed: str = 'true', dataset_name_prefix: str = 'character',
    dataset_name_pattern: str = '{prefix}_{num}', dataset_number_padding: int = 4, dataset_log_format: str = 'csv',
    clamp_int=None, clamp_float=None) -> dict:
    max_new_tokens = clamp_int(max_new_tokens, 24, 1000, 160)
    temperature = clamp_float(temperature, 0.0, 1.5, 0.2)
    top_p = clamp_float(top_p, 0.0, 1.0, 0.9)
    top_k = clamp_int(top_k, 0, 200, 40)
    caption_mode = normalize_batch_caption_mode(caption_mode)
    component_type = normalize_component_type(component_type)
    detail_level = normalize_detail_level(detail_level)
    dataset_caption_images_bool = parse_bool(dataset_caption_images)
    dataset_save_txt_bool = parse_bool(dataset_save_txt) and dataset_caption_images_bool
    dataset_rename_images_bool = parse_bool(dataset_rename_images)
    settings = build_caption_settings(
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        caption_mode=caption_mode,
        component_type=component_type,
        detail_level=detail_level,
        allow_custom_crop=False,
    )
    max_new_tokens = settings['max_new_tokens']
    temperature = settings['temperature']
    top_p = settings['top_p']
    top_k = settings['top_k']
    caption_mode = settings['caption_mode']
    component_type = settings['component_type']
    detail_level = settings['detail_level']
    return {
        'model': model,
        'mode': (mode or 'dataset').strip().lower(),
        'folder_path': folder_path,
        'category': (category or '').strip() or 'uncategorized',
        'base_name': (base_name or '').strip() or 'Batch_Caption',
        'numbering_start': max(1, int(numbering_start or 1)),
        'overwrite_existing': parse_bool(overwrite_existing),
        'skip_existing_txt': parse_bool(skip_existing_txt),
        'skip_duplicates': parse_bool(skip_duplicates),
        'recursive': parse_bool(recursive),
        'include_exts': parse_exts(include_exts),
        'prompt_style': prompt_style,
        'caption_length': caption_length,
        'custom_prompt': custom_prompt,
        'max_new_tokens': max_new_tokens,
        'temperature': temperature,
        'top_p': top_p,
        'top_k': top_k,
        'prefix': prefix,
        'suffix': suffix,
        'output_style': output_style,
        'output_folder': output_folder,
        'component_type': component_type,
        'caption_mode': caption_mode,
        'detail_level': detail_level,
        'post_task_action': (post_task_action or 'none').strip().lower() or 'none',
        'dataset_caption_images': dataset_caption_images_bool,
        'dataset_save_txt': dataset_save_txt_bool,
        'dataset_rename_images': dataset_rename_images_bool,
        'dataset_transfer_mode': _normalize_dataset_transfer_mode(dataset_transfer_mode),
        'dataset_skip_processed': parse_bool(dataset_skip_processed),
        'dataset_name_prefix': (dataset_name_prefix or '').strip() or 'character',
        'dataset_name_pattern': (dataset_name_pattern or '').strip() or '{prefix}_{num}',
        'dataset_number_padding': max(1, clamp_int(dataset_number_padding, 1, 8, 4)),
        'dataset_log_format': _normalize_dataset_log_format(dataset_log_format),
        'settings': settings,
    }
