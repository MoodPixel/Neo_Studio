from __future__ import annotations

from pathlib import Path
from typing import Any
import json

APP_DIR = Path(__file__).resolve().parents[1]
CENTRAL_ROOT = APP_DIR.parent
LIBRARY_USER_DATA = CENTRAL_ROOT / 'neo_library_data'
STUDIO_USER_DATA = LIBRARY_USER_DATA / 'studio_user_data'
LEGACY_LIBRARY_USER_DATA = CENTRAL_ROOT / 'neo_studio_v1' / 'neo_library_data'
LEGACY_STUDIO_USER_DATA = CENTRAL_ROOT / 'neo_studio_v1' / 'studio_user_data'


def _ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_default_json(path: Path, default_json: Any = None) -> None:
    if default_json is None or path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_json, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def library_user_data_root() -> Path:
    LIBRARY_USER_DATA.mkdir(parents=True, exist_ok=True)
    return LIBRARY_USER_DATA


def studio_user_data_root() -> Path:
    STUDIO_USER_DATA.mkdir(parents=True, exist_ok=True)
    return STUDIO_USER_DATA


def library_data_path(rel: str = '', *, legacy_rel: str | None = None, default_json: Any = None) -> Path:
    rel_clean = str(rel or '').replace('\\', '/').lstrip('/')
    path = library_user_data_root() / rel_clean if rel_clean else library_user_data_root()
    if rel_clean:
        _ensure_parent(path)
        _ensure_default_json(path, default_json)
    return path


def studio_data_path(rel: str = '', *, legacy_rel: str | None = None, default_json: Any = None) -> Path:
    rel_clean = str(rel or '').replace('\\', '/').lstrip('/')
    path = studio_user_data_root() / rel_clean if rel_clean else studio_user_data_root()
    if rel_clean:
        _ensure_parent(path)
        _ensure_default_json(path, default_json)
    return path

__all__ = [
    'CENTRAL_ROOT', 'LIBRARY_USER_DATA', 'STUDIO_USER_DATA', 'LEGACY_LIBRARY_USER_DATA', 'LEGACY_STUDIO_USER_DATA',
    'library_data_path', 'studio_data_path', 'library_user_data_root', 'studio_user_data_root',
]
