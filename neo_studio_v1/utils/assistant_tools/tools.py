from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..assistant_repo_indexer import build_repo_index, find_repo_root, search_repo_index
from ...contracts.external_workflow_patch_contract import validate_workflow_patch, validate_workflow_patches

MAX_READ_BYTES = 80_000
SAFE_TEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss', '.json', '.md', '.txt', '.yml', '.yaml',
    '.toml', '.ini', '.cfg', '.bat', '.ps1', '.sh', '.xml', '.jinja', '.j2'
}
BLOCKED_PARTS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.env'}


def _repo_root() -> Path:
    return find_repo_root()


def _safe_repo_path(raw_path: str) -> Path:
    root = _repo_root().resolve()
    clean = str(raw_path or '').strip().replace('\\', '/')
    if not clean:
        raise ValueError('Path is required.')
    if clean.startswith('/') or ':' in clean[:4]:
        raise ValueError('Only repository-relative paths are allowed.')
    path = (root / clean).resolve()
    try:
        path.relative_to(root)
    except Exception as exc:
        raise ValueError('Path escapes the Neo Studio repository root.') from exc
    if any(part in BLOCKED_PARTS for part in path.relative_to(root).parts):
        raise ValueError('That path is blocked by Assistant tool guardrails.')
    return path


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_repo_root().resolve()).as_posix()
    except Exception:
        return path.name


def tool_repo_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str((args or {}).get('query') or '').strip()
    limit = int((args or {}).get('limit') or 8)
    return search_repo_index(query, limit=max(1, min(limit, 30)))


def tool_repo_index_rebuild(args: Dict[str, Any]) -> Dict[str, Any]:
    max_files = int((args or {}).get('max_files') or 1200)
    index = build_repo_index(max_files=max(100, min(max_files, 5000)))
    return {
        'version': str(index.get('version') or ''),
        'file_count': int(index.get('file_count') or 0),
        'kind_counts': index.get('kind_counts') if isinstance(index.get('kind_counts'), dict) else {},
        'skipped_after_limit': int(index.get('skipped_after_limit') or 0),
    }


def tool_repo_read_file(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_repo_path(str((args or {}).get('path') or ''))
    if not path.exists() or not path.is_file():
        raise ValueError('File not found.')
    if path.suffix.lower() not in SAFE_TEXT_EXTENSIONS:
        raise ValueError('Only known text files can be read through Assistant tools.')
    size = int(path.stat().st_size)
    if size > MAX_READ_BYTES:
        raise ValueError(f'File is too large for safe preview ({size} bytes > {MAX_READ_BYTES} bytes).')
    text = path.read_text(encoding='utf-8', errors='replace')
    return {
        'path': _rel(path),
        'size_bytes': size,
        'extension': path.suffix.lower(),
        'content': text,
        'line_count': len(text.splitlines()),
    }


def tool_repo_inspect_path(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_repo_path(str((args or {}).get('path') or ''))
    if not path.exists():
        raise ValueError('Path not found.')
    stat = path.stat()
    payload: Dict[str, Any] = {
        'path': _rel(path),
        'exists': True,
        'is_file': path.is_file(),
        'is_dir': path.is_dir(),
        'size_bytes': int(stat.st_size) if path.is_file() else 0,
    }
    if path.is_dir():
        entries: List[Dict[str, Any]] = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:120]:
            if child.name in BLOCKED_PARTS:
                continue
            entries.append({'name': child.name, 'path': _rel(child), 'is_dir': child.is_dir(), 'size_bytes': int(child.stat().st_size) if child.is_file() else 0})
        payload['entries'] = entries
    return payload


def _extension_manifest_paths() -> List[Path]:
    root = _repo_root()
    base = root / 'neo_extensions' / 'installed'
    if not base.exists():
        return []
    out: List[Path] = []
    for path in sorted(base.glob('*/neo_extension.json')):
        if path.is_file():
            out.append(path)
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding='utf-8', errors='replace'))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def tool_extension_list(args: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for manifest_path in _extension_manifest_paths():
        manifest = _load_json(manifest_path)
        items.append({
            'id': str(manifest.get('id') or manifest_path.parent.name),
            'name': str(manifest.get('name') or manifest_path.parent.name),
            'version': str(manifest.get('version') or ''),
            'path': _rel(manifest_path.parent),
            'manifest_path': _rel(manifest_path),
            'enabled': bool(manifest.get('enabled', True)),
            'has_workflow_patches': bool(manifest.get('workflow_patches')),
            'has_ui_panels': bool(manifest.get('ui') or manifest.get('panels')),
        })
    return {'count': len(items), 'extensions': items}


def tool_extension_inspect(args: Dict[str, Any]) -> Dict[str, Any]:
    extension_id = str((args or {}).get('extension_id') or '').strip()
    if not extension_id:
        raise ValueError('extension_id is required.')
    matches = []
    for manifest_path in _extension_manifest_paths():
        manifest = _load_json(manifest_path)
        mid = str(manifest.get('id') or manifest_path.parent.name).strip()
        if extension_id in {mid, manifest_path.parent.name}:
            matches.append((manifest_path, manifest))
    if not matches:
        raise ValueError('Extension not found.')
    manifest_path, manifest = matches[0]
    readme = manifest_path.parent / 'README.md'
    readme_preview = readme.read_text(encoding='utf-8', errors='replace')[:5000] if readme.exists() else ''
    return {
        'id': str(manifest.get('id') or manifest_path.parent.name),
        'name': str(manifest.get('name') or manifest_path.parent.name),
        'version': str(manifest.get('version') or ''),
        'path': _rel(manifest_path.parent),
        'manifest_path': _rel(manifest_path),
        'manifest': manifest,
        'readme_preview': readme_preview,
    }


def tool_workflow_patch_validate(args: Dict[str, Any]) -> Dict[str, Any]:
    raw = (args or {}).get('patches')
    if raw is None:
        raw = (args or {}).get('patch')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as exc:
            raise ValueError('patch/patches must be JSON or a dict/list.') from exc
    if isinstance(raw, list):
        return validate_workflow_patches(raw, extension_id=str((args or {}).get('extension_id') or 'assistant_tool_preview'))
    if isinstance(raw, dict):
        return validate_workflow_patch(raw)
    raise ValueError('patch/patches must be a dict or list.')


def tool_patch_plan_validate(args: Dict[str, Any]) -> Dict[str, Any]:
    from ..assistant_patch_planner import validate_patch_plan
    plan = (args or {}).get('plan') if isinstance((args or {}).get('plan'), dict) else args
    return validate_patch_plan(plan if isinstance(plan, dict) else {})


def tool_patch_plan_preview(args: Dict[str, Any]) -> Dict[str, Any]:
    from ..assistant_patch_planner import preview_patch_plan
    plan = (args or {}).get('plan') if isinstance((args or {}).get('plan'), dict) else args
    return preview_patch_plan(plan if isinstance(plan, dict) else {})


def tool_patch_plan_apply(args: Dict[str, Any]) -> Dict[str, Any]:
    from ..assistant_patch_planner import apply_patch_plan
    plan = (args or {}).get('plan') if isinstance((args or {}).get('plan'), dict) else args
    return apply_patch_plan(
        plan if isinstance(plan, dict) else {},
        confirmed=bool((args or {}).get('confirmed')),
        allow_delete=bool((args or {}).get('allow_delete')),
    )
