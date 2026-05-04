from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .library_common import atomic_write_json, read_json_dict
from .library_constants import USER_DATA_DIR
from .logging_utils import get_logger

logger = get_logger(__name__)

NODE_MANAGER_SETTINGS_PATH = USER_DATA_DIR / 'node_manager.json'


LAST_NODE_MANAGER_LOG = ''


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _guess_custom_nodes_path() -> str:
    candidates = [
        Path.cwd() / 'custom_nodes',
        Path.cwd().parent / 'custom_nodes',
        Path(__file__).resolve().parents[3] / 'custom_nodes',
    ]
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_dir():
                return str(candidate.resolve())
        except Exception:
            continue
    return ''


DEFAULT_NODE_MANAGER_SETTINGS: Dict[str, Any] = {
    'custom_nodes_path': _guess_custom_nodes_path(),
    'python_executable': sys.executable,
}


def _normalize_path(text: str) -> str:
    raw = str(text or '').strip().strip('"')
    if not raw:
        return ''
    try:
        return str(Path(raw).expanduser().resolve())
    except Exception:
        return raw


def load_node_manager_settings() -> Dict[str, Any]:
    data = read_json_dict(NODE_MANAGER_SETTINGS_PATH)
    merged = dict(DEFAULT_NODE_MANAGER_SETTINGS)
    merged['custom_nodes_path'] = _normalize_path(data.get('custom_nodes_path') or merged['custom_nodes_path'])
    merged['python_executable'] = _normalize_path(data.get('python_executable') or merged['python_executable'])
    return merged


def save_node_manager_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_node_manager_settings()
    if isinstance(payload, dict):
        if 'custom_nodes_path' in payload:
            settings['custom_nodes_path'] = _normalize_path(payload.get('custom_nodes_path') or '')
        if 'python_executable' in payload:
            settings['python_executable'] = _normalize_path(payload.get('python_executable') or '')
    if not settings.get('python_executable'):
        settings['python_executable'] = sys.executable
    atomic_write_json(NODE_MANAGER_SETTINGS_PATH, settings)
    return settings


def _set_last_log(text: str) -> str:
    global LAST_NODE_MANAGER_LOG
    LAST_NODE_MANAGER_LOG = str(text or '')
    return LAST_NODE_MANAGER_LOG


def get_last_node_manager_log() -> str:
    return LAST_NODE_MANAGER_LOG


def _run_command(cmd: list[str], cwd: Path | None = None, timeout: int = 1200) -> Dict[str, Any]:
    command_str = ' '.join(cmd)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        stdout = proc.stdout or ''
        stderr = proc.stderr or ''
        log_text = f'$ {command_str}\n{stdout}'
        if stderr:
            log_text += f'\n[stderr]\n{stderr}'
        _set_last_log(log_text.strip())
        return {
            'ok': proc.returncode == 0,
            'returncode': proc.returncode,
            'stdout': stdout,
            'stderr': stderr,
            'log': LAST_NODE_MANAGER_LOG,
        }
    except Exception as exc:
        log_text = f'$ {command_str}\n[error]\n{exc}'
        _set_last_log(log_text)
        return {'ok': False, 'returncode': -1, 'stdout': '', 'stderr': str(exc), 'log': LAST_NODE_MANAGER_LOG}


def _git_capture(repo_dir: Path, args: list[str]) -> str:
    result = _run_command(['git', *args], cwd=repo_dir, timeout=90)
    if not result.get('ok'):
        return ''
    return str(result.get('stdout') or '').strip()


def inspect_custom_node(repo_dir: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        'name': repo_dir.name,
        'folder_name': repo_dir.name,
        'path': str(repo_dir.resolve()),
        'is_git': (repo_dir / '.git').exists(),
        'remote_url': '',
        'branch': '',
        'commit': '',
        'has_requirements': (repo_dir / 'requirements.txt').exists(),
        'last_modified': _utc_now(),
    }
    try:
        stat = repo_dir.stat()
        info['last_modified'] = datetime.utcfromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat() + 'Z'
    except Exception:
        pass
    if info['is_git']:
        info['remote_url'] = _git_capture(repo_dir, ['config', '--get', 'remote.origin.url'])
        info['branch'] = _git_capture(repo_dir, ['rev-parse', '--abbrev-ref', 'HEAD'])
        info['commit'] = _git_capture(repo_dir, ['rev-parse', '--short', 'HEAD'])
    return info


def list_custom_nodes(settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = settings or load_node_manager_settings()
    root = Path(cfg.get('custom_nodes_path') or '') if cfg.get('custom_nodes_path') else None
    rows = []
    if root and root.exists() and root.is_dir():
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith('.') or child.name.startswith('__'):
                continue
            rows.append(inspect_custom_node(child))
    return {
        'settings': cfg,
        'custom_nodes_path_exists': bool(root and root.exists() and root.is_dir()),
        'nodes': rows,
        'last_log': get_last_node_manager_log(),
    }


def _requirements_install(repo_dir: Path, python_executable: str) -> Dict[str, Any]:
    req = repo_dir / 'requirements.txt'
    if not req.exists():
        _set_last_log(f'No requirements.txt found in {repo_dir.name}. Clone/update finished with no pip step.')
        return {'ok': True, 'log': LAST_NODE_MANAGER_LOG, 'skipped': True}
    return _run_command([python_executable, '-m', 'pip', 'install', '-r', str(req)], cwd=repo_dir)


def _folder_name_from_git_url(git_url: str) -> str:
    raw = str(git_url or '').strip().rstrip('/')
    name = raw.rsplit('/', 1)[-1]
    if name.endswith('.git'):
        name = name[:-4]
    return name or 'custom_node'


def install_custom_node(git_url: str, branch: str = '', settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = settings or load_node_manager_settings()
    root_raw = str(cfg.get('custom_nodes_path') or '').strip()
    root = Path(root_raw) if root_raw else None
    python_executable = str(cfg.get('python_executable') or sys.executable)
    if not str(git_url or '').strip():
        raise ValueError('Paste a Git URL first.')
    if not root:
        raise ValueError('Set the custom_nodes path first.')
    root.mkdir(parents=True, exist_ok=True)
    folder_name = _folder_name_from_git_url(git_url)
    target_dir = root / folder_name
    if target_dir.exists():
        raise ValueError(f'{folder_name} already exists in custom_nodes.')
    cmd = ['git', 'clone']
    if str(branch or '').strip():
        cmd += ['--branch', str(branch).strip()]
    cmd += [str(git_url).strip(), folder_name]
    clone_result = _run_command(cmd, cwd=root, timeout=1800)
    if not clone_result.get('ok'):
        raise RuntimeError(clone_result.get('stderr') or clone_result.get('stdout') or 'Git clone failed.')
    pip_result = _requirements_install(target_dir, python_executable)
    if not pip_result.get('ok'):
        raise RuntimeError(pip_result.get('stderr') or pip_result.get('stdout') or 'Dependency install failed.')
    return {'node': inspect_custom_node(target_dir), 'log': get_last_node_manager_log()}


def update_custom_node(folder_name: str, settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = settings or load_node_manager_settings()
    root_raw = str(cfg.get('custom_nodes_path') or '').strip()
    root = Path(root_raw) if root_raw else None
    python_executable = str(cfg.get('python_executable') or sys.executable)
    if not root:
        raise ValueError('Set the custom_nodes path first.')
    repo_dir = root / str(folder_name or '').strip()
    if not repo_dir.exists() or not repo_dir.is_dir():
        raise ValueError('Pick an installed node first.')
    if not (repo_dir / '.git').exists():
        raise ValueError('Selected folder is not a git-based custom node.')
    pull_result = _run_command(['git', 'pull', '--ff-only'], cwd=repo_dir, timeout=1800)
    if not pull_result.get('ok'):
        raise RuntimeError(pull_result.get('stderr') or pull_result.get('stdout') or 'Git pull failed.')
    pip_result = _requirements_install(repo_dir, python_executable)
    if not pip_result.get('ok'):
        raise RuntimeError(pip_result.get('stderr') or pip_result.get('stdout') or 'Dependency install failed.')
    return {'node': inspect_custom_node(repo_dir), 'log': get_last_node_manager_log()}


def open_custom_node_path(folder_name: str = '', settings: Dict[str, Any] | None = None) -> str:
    cfg = settings or load_node_manager_settings()
    root_raw = str(cfg.get('custom_nodes_path') or '').strip()
    root = Path(root_raw) if root_raw else None
    if not root:
        raise ValueError('Set the custom_nodes path first.')
    target = root / str(folder_name or '').strip() if folder_name else root
    if not target.exists():
        raise ValueError('Target path does not exist yet.')
    try:
        if os.name == 'nt':
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(target)])
        else:
            subprocess.Popen(['xdg-open', str(target)])
    except Exception as exc:
        raise RuntimeError(f'Could not open the folder: {exc}') from exc
    _set_last_log(f'Opened {target}')
    return str(target)
