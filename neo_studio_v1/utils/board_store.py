from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts.board_records import build_board_summary, build_new_board_record, normalize_board_name, normalize_board_record
from .shared_data_paths import studio_data_path, studio_user_data_root
from .storage_io import atomic_write_json, read_json_object

BOARD_STORE_DIR = studio_data_path('boards')
BOARD_RECORDS_DIR = BOARD_STORE_DIR / 'records'
BOARD_MEDIA_DIR = BOARD_STORE_DIR / 'media'
BOARD_INDEX_PATH = BOARD_STORE_DIR / 'index.json'
BOARD_RECOVERY_DIR = BOARD_STORE_DIR / 'recovery'

_SAFE_ID_RE = re.compile(r'[^a-zA-Z0-9_-]+')


def ensure_board_foundation() -> dict[str, Any]:
    studio_user_data_root()
    BOARD_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    (BOARD_MEDIA_DIR / 'images').mkdir(parents=True, exist_ok=True)
    (BOARD_MEDIA_DIR / 'videos').mkdir(parents=True, exist_ok=True)
    (BOARD_MEDIA_DIR / 'audio').mkdir(parents=True, exist_ok=True)
    BOARD_RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    index = _read_index()
    _write_index(index)
    return index


def list_boards() -> list[dict[str, Any]]:
    ensure_board_foundation()
    summaries = _read_index().get('boards') or []
    if not isinstance(summaries, list):
        summaries = []
    return sorted([item for item in summaries if isinstance(item, dict)], key=lambda item: str(item.get('updated_at') or ''), reverse=True)


def create_board(name: str = '') -> dict[str, Any]:
    ensure_board_foundation()
    record = build_new_board_record(normalize_board_name(name))
    _write_record(record)
    _upsert_summary(record)
    return record


def load_board(board_id: str) -> dict[str, Any] | None:
    ensure_board_foundation()
    path = _record_path(board_id)
    if not path.exists():
        return None
    raw = read_json_object(path, None)
    if raw is None:
        return None
    record = normalize_board_record(raw, board_id=_safe_board_id(board_id))
    if record != raw:
        _write_record(record)
        _upsert_summary(record)
    return record


def save_board(board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_board_foundation()
    clean_id = _safe_board_id(board_id)
    existing = load_board(clean_id)
    merged: dict[str, Any] = dict(payload or {})
    if existing:
        merged.setdefault('created_at', existing.get('created_at'))
    record = normalize_board_record(merged, board_id=clean_id, preserve_timestamps=True)
    _write_record(record)
    _upsert_summary(record)
    return record


def rename_board(board_id: str, name: str) -> dict[str, Any]:
    record = load_board(board_id)
    if not record:
        raise FileNotFoundError('Board not found.')
    record['name'] = normalize_board_name(name)
    return save_board(record['id'], record)



def save_board_recovery(board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an unsaved board snapshot for recovery under neo_library_data."""
    ensure_board_foundation()
    clean_id = _safe_board_id(board_id)
    record = normalize_board_record(dict(payload or {}), board_id=clean_id, preserve_timestamps=True)
    recovery = {
        'schema_version': 1,
        'record_type': 'board_recovery_snapshot',
        'board_id': clean_id,
        'saved_at': record.get('updated_at'),
        'board': record,
    }
    atomic_write_json(_recovery_path(clean_id), recovery)
    return recovery


def load_board_recovery(board_id: str) -> dict[str, Any] | None:
    ensure_board_foundation()
    path = _recovery_path(board_id)
    raw = read_json_object(path, None)
    if not isinstance(raw, dict) or not isinstance(raw.get('board'), dict):
        return None
    raw['board'] = normalize_board_record(raw['board'], board_id=_safe_board_id(board_id), preserve_timestamps=True)
    return raw


def clear_board_recovery(board_id: str) -> bool:
    ensure_board_foundation()
    path = _recovery_path(board_id)
    existed = path.exists()
    if existed:
        path.unlink()
    return existed

def delete_board(board_id: str) -> bool:
    ensure_board_foundation()
    clean_id = _safe_board_id(board_id)
    path = _record_path(clean_id)
    existed = path.exists()
    if existed:
        path.unlink()
    clear_board_recovery(clean_id)
    index = _read_index()
    boards = index.get('boards') if isinstance(index.get('boards'), list) else []
    index['boards'] = [item for item in boards if isinstance(item, dict) and str(item.get('id') or '') != clean_id]
    _write_index(index)
    return existed



_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
_IMAGE_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'}
_AUDIO_MIME_TYPES = {'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/ogg', 'audio/aac', 'audio/flac', 'audio/mp4', 'audio/m4a', 'audio/webm', 'video/webm'}
_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v', '.ogv'}
_VIDEO_MIME_TYPES = {'video/mp4', 'video/webm', 'video/quicktime', 'video/x-m4v', 'video/ogg'}


def save_board_image_upload(fileobj: Any, filename: str = '', content_type: str = '') -> dict[str, Any]:
    """Save a board image upload under neo_library_data/studio_user_data/boards/media/images."""
    ensure_board_foundation()
    source_name = Path(str(filename or 'image')).name
    suffix = Path(source_name).suffix.lower()
    mime = str(content_type or '').split(';', 1)[0].strip().lower()
    if suffix not in _IMAGE_EXTENSIONS:
        raise ValueError('Only PNG, JPG, JPEG, WEBP, and GIF images are supported for board image cards.')
    if mime and mime not in _IMAGE_MIME_TYPES:
        raise ValueError('Uploaded file does not look like a supported image.')
    stored_name = f"img_{uuid4().hex[:16]}{suffix}"
    target = BOARD_MEDIA_DIR / 'images' / stored_name
    with target.open('wb') as fh:
        shutil.copyfileobj(fileobj, fh)
    return {
        'media_path': f'images/{stored_name}',
        'media_kind': 'image',
        'filename': source_name,
        'url': f'/api/board/media/images/{stored_name}',
    }


def save_board_audio_upload(fileobj: Any, filename: str = '', content_type: str = '') -> dict[str, Any]:
    """Save a board audio upload under neo_library_data/studio_user_data/boards/media/audio."""
    ensure_board_foundation()
    source_name = Path(str(filename or 'audio')).name
    suffix = Path(source_name).suffix.lower()
    mime = str(content_type or '').split(';', 1)[0].strip().lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise ValueError('Only MP3, WAV, OGG, M4A, AAC, FLAC, and WEBM audio files are supported for board audio cards.')
    if mime and mime not in _AUDIO_MIME_TYPES and not mime.startswith('audio/'):
        raise ValueError('Uploaded file does not look like a supported audio file.')
    stored_name = f"aud_{uuid4().hex[:16]}{suffix}"
    target = BOARD_MEDIA_DIR / 'audio' / stored_name
    with target.open('wb') as fh:
        shutil.copyfileobj(fileobj, fh)
    return {
        'media_path': f'audio/{stored_name}',
        'media_kind': 'audio',
        'filename': source_name,
        'url': f'/api/board/media/audio/{stored_name}',
    }



def save_board_video_upload(fileobj: Any, filename: str = '', content_type: str = '') -> dict[str, Any]:
    """Save a board video upload under neo_library_data/studio_user_data/boards/media/videos."""
    ensure_board_foundation()
    source_name = Path(str(filename or 'video')).name
    suffix = Path(source_name).suffix.lower()
    mime = str(content_type or '').split(';', 1)[0].strip().lower()
    if suffix not in _VIDEO_EXTENSIONS:
        raise ValueError('Only MP4, WEBM, MOV, M4V, and OGV video files are supported for board video cards.')
    if mime and mime not in _VIDEO_MIME_TYPES and not mime.startswith('video/') and mime != 'application/octet-stream':
        raise ValueError('Uploaded file does not look like a supported video file.')
    stored_name = f"vid_{uuid4().hex[:16]}{suffix}"
    target = BOARD_MEDIA_DIR / 'videos' / stored_name
    with target.open('wb') as fh:
        shutil.copyfileobj(fileobj, fh)
    return {
        'media_path': f'videos/{stored_name}',
        'media_kind': 'video',
        'filename': source_name,
        'url': f'/api/board/media/videos/{stored_name}',
    }
def resolve_board_media_path(media_kind: str, filename: str) -> Path | None:
    ensure_board_foundation()
    clean_kind = str(media_kind or '').strip().lower()
    clean_name = Path(str(filename or '')).name
    allowed = {'images', 'videos', 'audio'}
    if clean_kind not in allowed or not clean_name:
        return None
    path = BOARD_MEDIA_DIR / clean_kind / clean_name
    try:
        path.relative_to(BOARD_MEDIA_DIR)
    except Exception:
        return None
    return path if path.exists() and path.is_file() else None

def _read_index() -> dict[str, Any]:
    raw = read_json_object(BOARD_INDEX_PATH, None)
    if not isinstance(raw, dict):
        raw = {}
    boards = raw.get('boards') if isinstance(raw.get('boards'), list) else []
    return {'schema_version': 1, 'record_type': 'board_index', 'boards': boards}


def _write_index(index: dict[str, Any]) -> None:
    BOARD_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(BOARD_INDEX_PATH, index)


def _write_record(record: dict[str, Any]) -> None:
    path = _record_path(str(record.get('id') or ''))
    atomic_write_json(path, record)


def _upsert_summary(record: dict[str, Any]) -> None:
    index = _read_index()
    summary = build_board_summary(record)
    boards = [item for item in (index.get('boards') if isinstance(index.get('boards'), list) else []) if isinstance(item, dict) and str(item.get('id') or '') != summary['id']]
    boards.append(summary)
    index['boards'] = sorted(boards, key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    _write_index(index)


def _record_path(board_id: str) -> Path:
    return BOARD_RECORDS_DIR / f'{_safe_board_id(board_id)}.json'


def _recovery_path(board_id: str) -> Path:
    return BOARD_RECOVERY_DIR / f'{_safe_board_id(board_id)}.json'


def _safe_board_id(board_id: str) -> str:
    clean = _SAFE_ID_RE.sub('', str(board_id or '').strip())
    if not clean:
        raise ValueError('Board id is required.')
    return clean
