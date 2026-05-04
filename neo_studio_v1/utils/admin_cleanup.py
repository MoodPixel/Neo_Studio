from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
import shutil

from .config import ROOT_DIR
from .library_constants import USER_DATA_DIR
from .backend_manager import load_backend_settings

GENERATION_INPUTS_DIR = USER_DATA_DIR / 'generation_inputs'


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path.absolute()


def _is_safe_cleanup_target(path: Path) -> bool:
    resolved = _safe_resolve(path)
    root = _safe_resolve(ROOT_DIR)
    user_data = _safe_resolve(USER_DATA_DIR)
    # Only allow known temp/cache/input/output-style folders, never roots or model/custom_node folders.
    if not str(resolved):
        return False
    if resolved in {root, user_data, root.parent, Path(resolved.anchor)}:
        return False
    parts = {part.lower() for part in resolved.parts}
    if {'models', 'custom_nodes', 'extensions'} & parts:
        return False
    leaf = resolved.name.lower()
    allowed_leafs = {'input', 'inputs', 'output', 'outputs', 'generation_inputs'}
    return leaf in allowed_leafs or 'generation_inputs' in parts


def _folder_stats(path: Path) -> Dict[str, Any]:
    exists = path.exists() and path.is_dir()
    file_count = 0
    folder_count = 0
    size_bytes = 0
    if exists:
        try:
            for item in path.rglob('*'):
                try:
                    if item.is_file():
                        file_count += 1
                        size_bytes += item.stat().st_size
                    elif item.is_dir():
                        folder_count += 1
                except Exception:
                    continue
        except Exception:
            pass
    return {
        'path': str(path),
        'exists': exists,
        'safe': _is_safe_cleanup_target(path),
        'file_count': file_count,
        'folder_count': folder_count,
        'size_bytes': size_bytes,
    }


def _delete_contents(path: Path) -> Dict[str, Any]:
    stats_before = _folder_stats(path)
    removed_files = 0
    removed_folders = 0
    errors: list[str] = []
    if not stats_before['safe']:
        return {**stats_before, 'removed_files': 0, 'removed_folders': 0, 'errors': ['Unsafe cleanup target blocked.']}
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return {**stats_before, 'removed_files': 0, 'removed_folders': 0, 'errors': []}
    for child in list(path.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
                removed_folders += 1
            else:
                child.unlink()
                removed_files += 1
        except Exception as exc:
            errors.append(f'{child}: {exc}')
    after = _folder_stats(path)
    return {
        **after,
        'removed_files': removed_files,
        'removed_folders': removed_folders,
        'errors': errors,
        'before': stats_before,
    }


def _candidate_comfy_roots() -> list[Path]:
    roots: list[Path] = []
    settings = load_backend_settings()
    profiles = settings.get('profiles') if isinstance(settings.get('profiles'), dict) else {}
    for role, rows in profiles.items():
        if role != 'image':
            continue
        for profile in rows if isinstance(rows, list) else []:
            if not isinstance(profile, dict):
                continue
            backend_type = str(profile.get('backend_type') or profile.get('type') or '').lower()
            launcher = profile.get('launcher') if isinstance(profile.get('launcher'), dict) else {}
            cwd = str(launcher.get('working_dir') or '').strip()
            path = str(launcher.get('backend_path') or '').strip()
            if backend_type and 'comfy' not in backend_type and 'comfy' not in cwd.lower() and 'comfy' not in path.lower():
                continue
            if cwd:
                roots.append(Path(cwd))
            elif path:
                p = Path(path)
                roots.append(p.parent if p.suffix else p)
    # also include common sibling when user runs from portable path under root
    for rel in ('ComfyUI', 'ComfyUI_windows_portable', '../ComfyUI', '../ComfyUI_windows_portable'):
        roots.append((ROOT_DIR / rel))
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(_safe_resolve(root)).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _first_existing_child(names: Iterable[str]) -> Path | None:
    for root in _candidate_comfy_roots():
        for name in names:
            candidate = root / name
            if candidate.exists() and candidate.is_dir():
                return candidate
    # fallback to active configured first root even if folder is missing so UI can create/clean later.
    roots = _candidate_comfy_roots()
    if roots:
        return roots[0] / next(iter(names))
    return None


def cleanup_targets() -> Dict[str, Dict[str, Any]]:
    comfy_input = _first_existing_child(['input', 'inputs'])
    comfy_output = _first_existing_child(['output', 'outputs'])
    targets = {
        'neo_generation_inputs': GENERATION_INPUTS_DIR,
        'comfy_input': comfy_input,
        'comfy_output': comfy_output,
    }
    return {key: _folder_stats(path) if path else {'path': '', 'exists': False, 'safe': False, 'file_count': 0, 'folder_count': 0, 'size_bytes': 0} for key, path in targets.items()}


def clean_targets(keys: list[str]) -> Dict[str, Any]:
    available = cleanup_targets()
    cleaned: Dict[str, Any] = {}
    for key in keys:
        if key not in available:
            cleaned[key] = {'ok': False, 'errors': ['Unknown cleanup target.']}
            continue
        path = Path(str(available[key].get('path') or ''))
        cleaned[key] = _delete_contents(path)
        cleaned[key]['ok'] = not cleaned[key].get('errors')
    return {'ok': True, 'targets': cleanup_targets(), 'cleaned': cleaned}
