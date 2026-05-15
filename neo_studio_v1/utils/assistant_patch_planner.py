from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .assistant_repo_indexer import find_repo_root

SAFE_TEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss', '.json', '.md', '.txt', '.yml', '.yaml',
    '.toml', '.ini', '.cfg', '.bat', '.ps1', '.sh', '.xml', '.jinja', '.j2'
}
BLOCKED_PARTS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.env'}
MAX_PATCH_FILE_BYTES = 180_000
MAX_PROPOSED_CONTENT_CHARS = 260_000
VALID_ACTIONS = {'add', 'modify', 'replace', 'delete'}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _repo_root() -> Path:
    return find_repo_root().resolve()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_repo_root()).as_posix()
    except Exception:
        return path.name


def safe_patch_path(raw_path: str, *, must_exist: bool = False, allow_missing_parent: bool = False) -> Path:
    root = _repo_root()
    clean = str(raw_path or '').strip().replace('\\', '/')
    if not clean:
        raise ValueError('Patch path is required.')
    if clean.startswith('/') or ':' in clean[:4]:
        raise ValueError('Only repository-relative patch paths are allowed.')
    path = (root / clean).resolve()
    try:
        path.relative_to(root)
    except Exception as exc:
        raise ValueError('Patch path escapes the Neo Studio repository root.') from exc
    if any(part in BLOCKED_PARTS for part in path.relative_to(root).parts):
        raise ValueError('Patch path is blocked by Assistant patch guardrails.')
    if path.suffix.lower() not in SAFE_TEXT_EXTENSIONS:
        raise ValueError('Assistant patch planner only supports known text/code/document files.')
    if must_exist and not path.exists():
        raise ValueError(f'Patch target does not exist: {_rel(path)}')
    parent = path.parent
    if not parent.exists() and not allow_missing_parent:
        raise ValueError(f'Patch target parent folder does not exist: {_rel(parent)}')
    return path


def _read_existing(path: Path) -> str:
    if not path.exists():
        return ''
    if not path.is_file():
        raise ValueError(f'Patch target is not a file: {_rel(path)}')
    size = int(path.stat().st_size)
    if size > MAX_PATCH_FILE_BYTES:
        raise ValueError(f'Patch target is too large for safe patch planning: {_rel(path)} ({size} bytes).')
    return path.read_text(encoding='utf-8', errors='replace')


def _normalize_action(raw: str) -> str:
    action = str(raw or '').strip().lower()
    if action == 'update':
        action = 'modify'
    if action not in VALID_ACTIONS:
        raise ValueError(f'Unsupported patch action: {raw!r}. Use add, modify, replace, or delete.')
    return action


def _proposed_content(change: Dict[str, Any], existing: str, action: str) -> str:
    if action == 'delete':
        return ''
    if 'proposed_content' in change:
        text = str(change.get('proposed_content') or '')
    elif 'content' in change:
        text = str(change.get('content') or '')
    elif 'new_content' in change:
        text = str(change.get('new_content') or '')
    elif 'find' in change and 'replace' in change:
        find = str(change.get('find') or '')
        replace = str(change.get('replace') or '')
        if not find:
            raise ValueError('find/replace patch changes require a non-empty find value.')
        if find not in existing:
            raise ValueError('find text was not found in the target file.')
        count_raw = change.get('count')
        count = int(count_raw) if isinstance(count_raw, int) or str(count_raw or '').isdigit() else -1
        text = existing.replace(find, replace, count if count > 0 else existing.count(find))
    else:
        raise ValueError('Patch change requires proposed_content/content/new_content or find+replace.')
    if len(text) > MAX_PROPOSED_CONTENT_CHARS:
        raise ValueError('Proposed patch content is too large for safe preview/apply.')
    return text


def normalize_patch_plan(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError('Patch plan must be a JSON object.')
    raw_changes = plan.get('changes')
    if not isinstance(raw_changes, list) or not raw_changes:
        raise ValueError('Patch plan requires a non-empty changes list.')
    normalized_changes: List[Dict[str, Any]] = []
    for index, raw_change in enumerate(raw_changes):
        if not isinstance(raw_change, dict):
            raise ValueError(f'Patch change #{index + 1} must be an object.')
        action = _normalize_action(str(raw_change.get('action') or 'modify'))
        path = safe_patch_path(str(raw_change.get('path') or ''), must_exist=action in {'modify', 'replace', 'delete'}, allow_missing_parent=action == 'add')
        if action == 'add' and path.exists() and not bool(raw_change.get('overwrite')):
            raise ValueError(f'Add patch target already exists: {_rel(path)}. Set overwrite=true or use modify.')
        existing = _read_existing(path)
        proposed = _proposed_content(raw_change, existing, action)
        normalized_changes.append({
            'index': index,
            'path': _rel(path),
            'absolute_path': str(path),
            'action': action,
            'summary': str(raw_change.get('summary') or raw_change.get('reason') or '').strip(),
            'overwrite': bool(raw_change.get('overwrite')),
            'existing_content': existing,
            'proposed_content': proposed,
            'existing_sha256': hashlib.sha256(existing.encode('utf-8')).hexdigest() if existing else '',
            'proposed_sha256': hashlib.sha256(proposed.encode('utf-8')).hexdigest() if proposed else '',
            'line_count_before': len(existing.splitlines()),
            'line_count_after': len(proposed.splitlines()),
        })
    normalized_public = [{k: v for k, v in item.items() if k not in {'absolute_path', 'existing_content', 'proposed_content'}} for item in normalized_changes]
    fingerprint_src = json.dumps({'title': plan.get('title') or '', 'changes': normalized_public}, sort_keys=True)
    return {
        'version': 'assistant_patch_plan_v1',
        'plan_id': hashlib.sha256(fingerprint_src.encode('utf-8')).hexdigest()[:16],
        'title': str(plan.get('title') or 'Assistant patch plan').strip()[:180],
        'summary': str(plan.get('summary') or plan.get('description') or '').strip()[:4000],
        'risk': _estimate_plan_risk(normalized_changes),
        'created_at': _utc_now(),
        'change_count': len(normalized_changes),
        'changes': normalized_changes,
    }


def _estimate_plan_risk(changes: List[Dict[str, Any]]) -> str:
    if any(item.get('action') == 'delete' for item in changes):
        return 'danger'
    if len(changes) >= 8:
        return 'medium'
    if any(int(item.get('line_count_after') or 0) > 800 for item in changes):
        return 'medium'
    return 'medium' if any(item.get('action') == 'add' for item in changes) else 'safe'


def _unified_diff(path: str, old: str, new: str) -> str:
    return ''.join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f'a/{path}',
        tofile=f'b/{path}',
        lineterm='',
    ))


def preview_patch_plan(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    normalized = normalize_patch_plan(plan)
    public_changes: List[Dict[str, Any]] = []
    total_added = 0
    total_removed = 0
    for item in normalized['changes']:
        diff = _unified_diff(str(item['path']), str(item['existing_content']), str(item['proposed_content']))
        added = sum(1 for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
        removed = sum(1 for line in diff.splitlines() if line.startswith('-') and not line.startswith('---'))
        total_added += added
        total_removed += removed
        public_changes.append({
            'index': item['index'],
            'path': item['path'],
            'action': item['action'],
            'summary': item['summary'],
            'existing_sha256': item['existing_sha256'],
            'proposed_sha256': item['proposed_sha256'],
            'line_count_before': item['line_count_before'],
            'line_count_after': item['line_count_after'],
            'added_lines': added,
            'removed_lines': removed,
            'diff': diff[:80_000],
            'diff_truncated': len(diff) > 80_000,
        })
    return {
        'ok': True,
        'version': normalized['version'],
        'plan_id': normalized['plan_id'],
        'title': normalized['title'],
        'summary': normalized['summary'],
        'risk': normalized['risk'],
        'change_count': normalized['change_count'],
        'total_added_lines': total_added,
        'total_removed_lines': total_removed,
        'requires_confirmation': True,
        'can_apply': normalized['risk'] != 'danger',
        'guardrails': {
            'repo_relative_paths_only': True,
            'text_files_only': True,
            'blocked_parts': sorted(BLOCKED_PARTS),
            'delete_actions_block_apply': True,
            'backup_before_write': True,
        },
        'changes': public_changes,
    }


def _backup_path(root: Path, rel_path: str, backup_id: str) -> Path:
    return root / 'data' / 'assistant_patch_backups' / backup_id / rel_path


def apply_patch_plan(plan: Dict[str, Any] | None, *, confirmed: bool = False, allow_delete: bool = False) -> Dict[str, Any]:
    if not confirmed:
        raise PermissionError('Patch apply requires explicit confirmation.')
    normalized = normalize_patch_plan(plan)
    if normalized['risk'] == 'danger' and not allow_delete:
        raise PermissionError('Patch plans with delete actions are blocked unless allow_delete=true is explicitly set.')
    root = _repo_root()
    backup_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + normalized['plan_id']
    applied: List[Dict[str, Any]] = []
    for item in normalized['changes']:
        path = Path(str(item['absolute_path']))
        rel = str(item['path'])
        backup = _backup_path(root, rel, backup_id)
        if path.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        if item['action'] == 'delete':
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(item['proposed_content']), encoding='utf-8', newline='')
        applied.append({
            'path': rel,
            'action': item['action'],
            'backup_path': _rel(backup) if backup.exists() else '',
            'before_sha256': item['existing_sha256'],
            'after_sha256': item['proposed_sha256'],
        })
    manifest_path = root / 'data' / 'assistant_patch_backups' / backup_id / '_patch_manifest.json'
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        'backup_id': backup_id,
        'applied_at': _utc_now(),
        'plan_id': normalized['plan_id'],
        'title': normalized['title'],
        'summary': normalized['summary'],
        'applied': applied,
    }, indent=2), encoding='utf-8')
    return {
        'ok': True,
        'version': 'assistant_patch_apply_v1',
        'plan_id': normalized['plan_id'],
        'backup_id': backup_id,
        'backup_manifest': _rel(manifest_path),
        'applied_count': len(applied),
        'applied': applied,
    }


def validate_patch_plan(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    preview = preview_patch_plan(plan)
    return {
        'ok': True,
        'version': 'assistant_patch_validation_v1',
        'plan_id': preview['plan_id'],
        'risk': preview['risk'],
        'change_count': preview['change_count'],
        'can_apply': preview['can_apply'],
        'requires_confirmation': True,
        'total_added_lines': preview['total_added_lines'],
        'total_removed_lines': preview['total_removed_lines'],
        'changes': [{k: item[k] for k in ('index', 'path', 'action', 'summary', 'added_lines', 'removed_lines') if k in item} for item in preview['changes']],
    }
