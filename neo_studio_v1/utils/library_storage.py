from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from .library_constants import FORMAT_TO_SUFFIX, IMAGE_EXTS, MAX_TEMP_AGE_HOURS, MAX_UPLOAD_BYTES, TEMP_DIR


def cleanup_temp_uploads(max_age_hours: int = MAX_TEMP_AGE_HOURS) -> int:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    removed = 0
    for fp in TEMP_DIR.iterdir():
        if not fp.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(fp.stat().st_mtime)
            if modified < cutoff:
                fp.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    return removed


def save_temp_upload(src_bytes: bytes, suffix: str) -> Dict[str, str]:
    cleanup_temp_uploads()
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    if not src_bytes:
        raise ValueError('Upload is empty.')
    if len(src_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f'Image is too large. Max size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')

    try:
        with Image.open(BytesIO(src_bytes)) as im:
            im.verify()
            image_format = (im.format or '').upper()
    except Exception as e:
        raise ValueError(f'Invalid image upload: {e}')

    final_suffix = FORMAT_TO_SUFFIX.get(image_format)
    if not final_suffix:
        requested_suffix = (suffix or '').strip().lower()
        if requested_suffix and requested_suffix in IMAGE_EXTS:
            final_suffix = requested_suffix
        else:
            raise ValueError('Unsupported image format. Allowed formats: PNG, JPG, WEBP, BMP.')

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=final_suffix, dir=TEMP_DIR)
    try:
        tmp.write(src_bytes)
    finally:
        tmp.close()
    return {'temp_image_id': Path(tmp.name).name, 'temp_image_path': tmp.name}


def temp_path_from_id(temp_image_id: str) -> Path:
    return (TEMP_DIR / Path(temp_image_id).name).resolve()


def delete_temp_upload(temp_image_id: str) -> None:
    try:
        temp_path_from_id(temp_image_id).unlink(missing_ok=True)
    except Exception:
        pass


def make_thumb(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im = im.convert('RGB')
        im.thumbnail((512, 512))
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, format='WEBP', quality=90, method=6)


def iter_records(kind: str) -> List[Dict[str, Any]]:
    from .library_settings_store import get_library_root

    root = get_library_root()
    folder = root / ('prompts' if kind == 'prompt' else 'captions')
    out: List[Dict[str, Any]] = []
    for fp in sorted(folder.glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
            if isinstance(rec, dict):
                rec['_record_path'] = str(fp)
                out.append(rec)
        except Exception:
            continue
    return out
