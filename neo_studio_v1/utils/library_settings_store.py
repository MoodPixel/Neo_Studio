from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .library_common import atomic_write_json, ensure_dir, read_json_dict, sync_library_root_to_shared_settings
from .library_constants import DEFAULT_ROOT, NEO_LIBRARY_SETTINGS_PATH, SETTINGS_PATH, TEMP_DIR, USER_DATA_DIR

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_settings() -> Dict[str, Any]:
    data = read_json_dict(SETTINGS_PATH)
    if not str(data.get('library_root') or '').strip():
        fallback = read_json_dict(NEO_LIBRARY_SETTINGS_PATH)
        shared_root = str(fallback.get('library_root') or '').strip()
        if shared_root:
            data['library_root'] = shared_root
    return data


def _save_settings(data: Dict[str, Any]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(SETTINGS_PATH, data)
    if 'library_root' in data:
        sync_library_root_to_shared_settings(str(data.get('library_root') or ''))


def get_last_used_category(kind: str) -> str:
    data = _load_settings()
    key = 'last_prompt_category' if kind == 'prompt' else 'last_caption_category'
    return str(data.get(key) or 'uncategorized').strip() or 'uncategorized'


def set_last_used_category(kind: str, category: str) -> str:
    value = (category or '').strip() or 'uncategorized'
    data = _load_settings()
    key = 'last_prompt_category' if kind == 'prompt' else 'last_caption_category'
    data[key] = value
    _save_settings(data)
    return value


def get_library_root() -> Path:
    data = _load_settings()
    override = str(data.get('library_root') or '').strip()
    root = Path(override) if override else DEFAULT_ROOT
    ensure_dir(root)
    for name in ('captions', 'prompts', 'images', 'thumbs', 'output_metadata', 'bundles', 'bundle_images'):
        ensure_dir(root / name)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    from .library_storage import cleanup_temp_uploads
    cleanup_temp_uploads()
    return root


def set_library_root(path: str) -> str:
    target = str(path or '').strip()
    data = _load_settings()
    if not target:
        data['library_root'] = ''
        _save_settings(data)
        return ''

    target_path = Path(target).expanduser()
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        for name in ('captions', 'prompts', 'images', 'thumbs', 'output_metadata', 'bundles', 'bundle_images'):
            ensure_dir(target_path / name)
        probe = tempfile.NamedTemporaryFile(delete=False, dir=target_path, prefix='neo_write_test_', suffix='.tmp')
        probe_path = Path(probe.name)
        probe.close()
        probe_path.unlink(missing_ok=True)
    except Exception as e:
        raise ValueError(f'Library path is not writable: {target_path} ({e})')

    normalized = str(target_path.resolve())
    data['library_root'] = normalized
    _save_settings(data)
    return normalized


def list_categories() -> List[str]:
    vals = set()
    root = get_library_root()
    cats_fp = root / 'categories.json'
    try:
        stored = read_json(cats_fp, [])
        if isinstance(stored, list):
            for cat in stored:
                cat = str(cat or '').strip()
                if cat:
                    vals.add(cat)
    except Exception:
        pass
    for kind in ('captions', 'prompts'):
        for fp in (root / kind).glob('*.json'):
            try:
                data = read_json(fp, {})
                cat = str(data.get('category') or '').strip() or 'uncategorized'
                vals.add(cat)
            except Exception:
                continue
    if not vals:
        vals.add('uncategorized')
    return sorted(vals, key=str.lower)


def update_categories_file(category: str) -> None:
    category = (category or '').strip() or 'uncategorized'
    root = get_library_root()
    fp = root / 'categories.json'
    current: List[str] = []
    try:
        current = read_json(fp, {})
        if not isinstance(current, list):
            current = []
    except Exception:
        current = []
    if category not in current:
        current.append(category)
        current = sorted(set(current), key=str.lower)
        atomic_write_json(fp, current)
