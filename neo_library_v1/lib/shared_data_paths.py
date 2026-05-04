from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CENTRAL_ROOT = ROOT / 'neo_library_data'
LIBRARY_USER_DATA = CENTRAL_ROOT / 'library_user_data'
STUDIO_USER_DATA = CENTRAL_ROOT / 'studio_user_data'
LEGACY_LIBRARY_USER_DATA = ROOT / 'neo_library_v1' / 'user_data'
LEGACY_STUDIO_USER_DATA = ROOT / 'neo_studio_v1' / 'user_data'

_JSON_EXTS = {'.json'}
_PATH_PREFIXES = [
    str(LEGACY_LIBRARY_USER_DATA).replace('\\', '/'),
    str(LEGACY_STUDIO_USER_DATA).replace('\\', '/'),
]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _normalize_text(text: str) -> str:
    return text.replace('\\', '/')


def _rewrite_legacy_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _rewrite_legacy_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_legacy_strings(v) for v in value]
    if isinstance(value, str):
        norm = _normalize_text(value)
        for prefix in _PATH_PREFIXES:
            if norm.startswith(prefix):
                suffix = norm[len(prefix):].lstrip('/')
                return str((LIBRARY_USER_DATA / suffix).resolve())
        return value
    return value


def _migrate_json_file(src: Path, dst: Path) -> None:
    try:
        data = json.loads(src.read_text(encoding='utf-8'))
        data = _rewrite_legacy_strings(data)
        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        shutil.copy2(src, dst)


def _ensure_migrated(target: Path, legacy: Path | None) -> Path:
    _ensure_dir(target.parent)
    if target.exists() or legacy is None or not legacy.exists():
        return target
    if legacy.is_dir():
        shutil.copytree(legacy, target, dirs_exist_ok=True)
        return target
    if legacy.suffix.lower() in _JSON_EXTS:
        _migrate_json_file(legacy, target)
    else:
        shutil.copy2(legacy, target)
    return target


def library_user_data_root() -> Path:
    _ensure_dir(LIBRARY_USER_DATA)
    return LIBRARY_USER_DATA


def studio_user_data_root() -> Path:
    _ensure_dir(STUDIO_USER_DATA)
    return STUDIO_USER_DATA


def library_data_path(*parts: str, legacy_rel: str | None = None, default_json: Any | None = None) -> Path:
    target = library_user_data_root().joinpath(*parts)
    legacy = LEGACY_LIBRARY_USER_DATA / legacy_rel if legacy_rel else None
    _ensure_migrated(target, legacy)
    if default_json is not None and not target.exists():
        _ensure_dir(target.parent)
        target.write_text(json.dumps(default_json, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def studio_data_path(*parts: str, legacy_rel: str | None = None, default_json: Any | None = None) -> Path:
    target = studio_user_data_root().joinpath(*parts)
    legacy = LEGACY_STUDIO_USER_DATA / legacy_rel if legacy_rel else None
    _ensure_migrated(target, legacy)
    if default_json is not None and not target.exists():
        _ensure_dir(target.parent)
        target.write_text(json.dumps(default_json, ensure_ascii=False, indent=2), encoding='utf-8')
    return target
