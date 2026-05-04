from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from .roleplay_foundation import (
    ROLEPLAY_ASSETS_DIR,
    ROLEPLAY_CHARACTER_IMAGES_DIR,
    ROLEPLAY_STORY_COVERS_DIR,
)
from .roleplay_library_store import get_record as get_library_record, _path_for as library_path_for
from .roleplay_story_store import get_story_record, _story_path
from .roleplay_v2_story_store import get_storyline as get_v2_storyline
from .roleplay_v2_package_store import save_record as save_v2_record
from .roleplay_foundation import now_iso
from .storage_io import atomic_write_json

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def _safe_ext(filename: str) -> str:
    ext = Path(str(filename or '')).suffix.lower()
    return ext if ext in IMAGE_EXTENSIONS else '.png'


def _relative_asset_path(path: Path) -> str:
    return path.relative_to(ROLEPLAY_ASSETS_DIR.parent).as_posix()


def resolve_roleplay_asset_path(asset_path: str) -> Path | None:
    clean = str(asset_path or '').strip().replace('\\', '/')
    if not clean:
        return None
    path = (ROLEPLAY_ASSETS_DIR.parent / clean).resolve()
    try:
        path.relative_to(ROLEPLAY_ASSETS_DIR.parent.resolve())
    except Exception:
        return None
    return path if path.exists() else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


async def save_character_avatar(record_id: str, upload: UploadFile) -> dict[str, Any]:
    record = get_library_record('character', record_id)
    if not record:
        raise ValueError('Character record not found.')
    ext = _safe_ext(upload.filename or '')
    filename = f"character_{record.get('id', 'record')}_{uuid4().hex[:8]}{ext}"
    dest = ROLEPLAY_CHARACTER_IMAGES_DIR / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('wb') as f:
        shutil.copyfileobj(upload.file, f)
    avatar = record.get('avatar') or {}
    avatar['image_path'] = _relative_asset_path(dest)
    avatar['thumb_path'] = _relative_asset_path(dest)
    avatar['alt_text'] = str(record.get('display_name') or record.get('name') or '').strip()
    record['avatar'] = avatar
    meta = record.get('meta') or {}
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    _write_json(library_path_for('character', str(record.get('id') or '').strip()), record)
    return record




async def save_roleplay_v2_storyline_cover(storyline_id: str, upload: UploadFile) -> dict[str, Any]:
    record = get_v2_storyline(storyline_id)
    if not record:
        raise ValueError('Storyline record not found.')
    ext = _safe_ext(upload.filename or '')
    filename = f"storyline_{record.get('id', 'record')}_{uuid4().hex[:8]}{ext}"
    dest = ROLEPLAY_STORY_COVERS_DIR / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('wb') as f:
        shutil.copyfileobj(upload.file, f)
    cover = record.get('cover') or {}
    cover['image_path'] = _relative_asset_path(dest)
    cover['thumb_path'] = _relative_asset_path(dest)
    cover['alt_text'] = str(record.get('title') or '').strip()
    record['cover'] = cover
    meta = record.get('meta') or {}
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    return save_v2_record(record)

async def save_story_cover(record_id: str, upload: UploadFile) -> dict[str, Any]:
    record = get_story_record(record_id)
    if not record:
        raise ValueError('Story record not found.')
    ext = _safe_ext(upload.filename or '')
    filename = f"story_{record.get('id', 'record')}_{uuid4().hex[:8]}{ext}"
    dest = ROLEPLAY_STORY_COVERS_DIR / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('wb') as f:
        shutil.copyfileobj(upload.file, f)
    cover = record.get('cover') or {}
    cover['image_path'] = _relative_asset_path(dest)
    cover['thumb_path'] = _relative_asset_path(dest)
    cover['alt_text'] = str(record.get('title') or '').strip()
    record['cover'] = cover
    meta = record.get('meta') or {}
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    _write_json(_story_path(str(record.get('id') or '').strip()), record)
    return record
