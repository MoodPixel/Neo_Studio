from __future__ import annotations

import json
import os
import platform
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .assistant_action_memory import sync_action_memory
from .logging_utils import get_logger

logger = get_logger(__name__)

LOCAL_PC_CONTROL_VERSION = 'assistant_local_pc_control_v1'
DEFAULT_TIMEOUT_SECONDS = 20
MAX_STDOUT_CHARS = 6000
MAX_PATH_CHARS = 900

# Commands are intentionally preset-only. No raw shell strings in Phase 11.
# This gives the Assistant local utility without handing it an unguarded terminal.
COMMAND_PRESETS: Dict[str, Dict[str, Any]] = {
    'python.version': {
        'label': 'Python Version',
        'description': 'Show the Python interpreter version used to launch Neo.',
        'risk': 'safe',
        'requires_confirmation': False,
        'argv': [sys.executable, '--version'],
        'timeout_seconds': 10,
    },
    'git.status': {
        'label': 'Git Status',
        'description': 'Run git status --short in the Neo repo root if Git is available.',
        'risk': 'medium',
        'requires_confirmation': True,
        'argv': ['git', 'status', '--short'],
        'timeout_seconds': 15,
        'cwd': 'repo_root',
    },
    'git.branch': {
        'label': 'Git Current Branch',
        'description': 'Show the current Git branch in the Neo repo root if Git is available.',
        'risk': 'safe',
        'requires_confirmation': False,
        'argv': ['git', 'branch', '--show-current'],
        'timeout_seconds': 10,
        'cwd': 'repo_root',
    },
    'repo.tree.assistant': {
        'label': 'Assistant File Tree',
        'description': 'List Assistant-related files inside the Neo repo using Python, cross-platform.',
        'risk': 'safe',
        'requires_confirmation': False,
        'argv': [
            sys.executable,
            '-c',
            "from pathlib import Path\nroot=Path.cwd()\nfor p in sorted(root.glob('neo_studio_v1/**/*assistant*'))[:220]:\n print(p.as_posix())\nfor p in sorted((root/'neo_system_records'/'02_TABS'/'assistant').rglob('*'))[:220]:\n print(p.as_posix())\n",
        ],
        'timeout_seconds': 15,
        'cwd': 'repo_root',
    },
}

WINDOWS_APP_PRESETS: Dict[str, Dict[str, Any]] = {
    'notepad': {'label': 'Notepad', 'argv': ['notepad.exe'], 'risk': 'safe', 'requires_confirmation': False},
    'calculator': {'label': 'Calculator', 'argv': ['calc.exe'], 'risk': 'safe', 'requires_confirmation': False},
    'explorer': {'label': 'File Explorer', 'argv': ['explorer.exe'], 'risk': 'safe', 'requires_confirmation': False},
}

MAC_APP_PRESETS: Dict[str, Dict[str, Any]] = {
    'textedit': {'label': 'TextEdit', 'argv': ['open', '-a', 'TextEdit'], 'risk': 'safe', 'requires_confirmation': False},
    'finder': {'label': 'Finder', 'argv': ['open', '.'], 'risk': 'safe', 'requires_confirmation': False},
}

LINUX_APP_PRESETS: Dict[str, Dict[str, Any]] = {
    'files': {'label': 'Files', 'argv': ['xdg-open', '.'], 'risk': 'safe', 'requires_confirmation': False},
}

BLOCKED_COMMAND_TOKENS = {
    'rm', 'del', 'erase', 'rmdir', 'format', 'shutdown', 'restart', 'reboot', 'reg', 'regedit',
    'diskpart', 'powershell', 'pwsh', 'cmd', 'bash', 'sh', 'curl', 'wget', 'ssh', 'scp', 'ftp',
    'pip', 'npm', 'pnpm', 'yarn', 'winget', 'choco', 'scoop', 'sudo', 'su', 'chmod', 'chown',
}

BLOCKED_EXTENSIONS = {'.exe', '.bat', '.cmd', '.ps1', '.vbs', '.scr', '.msi', '.dll', '.com'}


@dataclass(frozen=True)
class LocalActionResult:
    ok: bool
    action_type: str
    risk: str
    requires_confirmation: bool
    executed: bool
    message: str
    details: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            'ok': self.ok,
            'version': LOCAL_PC_CONTROL_VERSION,
            'action_type': self.action_type,
            'risk': self.risk,
            'requires_confirmation': self.requires_confirmation,
            'executed': self.executed,
            'message': self.message,
            'details': self.details,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _clean(value: Any, limit: int = 600) -> str:
    return str(value or '').replace('\r', ' ').replace('\n', ' ').strip()[:limit]


def _platform_key() -> str:
    name = platform.system().lower()
    if name.startswith('win'):
        return 'windows'
    if name == 'darwin':
        return 'macos'
    if name == 'linux':
        return 'linux'
    return name or 'unknown'


def _app_presets() -> Dict[str, Dict[str, Any]]:
    key = _platform_key()
    if key == 'windows':
        return WINDOWS_APP_PRESETS
    if key == 'macos':
        return MAC_APP_PRESETS
    if key == 'linux':
        return LINUX_APP_PRESETS
    return {}


def _safe_json(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalise_existing_path(value: Any, *, require_exists: bool = True) -> Path:
    raw = str(value or '').strip().strip('"')
    if not raw:
        raise ValueError('path is required.')
    if len(raw) > MAX_PATH_CHARS:
        raise ValueError('path is too long.')
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded).resolve()
    if require_exists and not path.exists():
        raise ValueError('path does not exist.')
    return path


def _path_risk(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    is_exec = suffix in BLOCKED_EXTENSIONS
    return {
        'path': str(path),
        'exists': path.exists(),
        'is_file': path.is_file(),
        'is_dir': path.is_dir(),
        'suffix': suffix,
        'risk': 'medium' if is_exec else 'safe',
        'requires_confirmation': bool(is_exec),
        'blocked_reason': 'Executable/script paths require explicit confirmation and are not auto-opened.' if is_exec else '',
    }


def list_local_action_catalog() -> Dict[str, Any]:
    return {
        'ok': True,
        'version': LOCAL_PC_CONTROL_VERSION,
        'platform': _platform_key(),
        'guardrails': {
            'raw_shell_blocked': True,
            'keyboard_mouse_automation': 'not_available_in_phase_11',
            'destructive_file_ops': 'blocked',
            'network_installers': 'blocked',
            'password_payment_entry': 'blocked',
            'medium_actions_require_confirmation': True,
        },
        'actions': [
            {'id': 'open_path', 'label': 'Open path', 'risk': 'safe_or_medium', 'requires_confirmation': 'only executable/script paths', 'description': 'Open a local file or folder using the OS default handler.'},
            {'id': 'reveal_path', 'label': 'Reveal path', 'risk': 'safe', 'requires_confirmation': False, 'description': 'Open the parent folder for a local file/folder.'},
            {'id': 'launch_app', 'label': 'Launch approved app preset', 'risk': 'safe', 'requires_confirmation': False, 'description': 'Launch a configured OS app preset.'},
            {'id': 'run_command_preset', 'label': 'Run command preset', 'risk': 'safe_or_medium', 'requires_confirmation': 'preset dependent', 'description': 'Run one approved command preset without shell=True.'},
        ],
        'app_presets': {key: {k: v for k, v in val.items() if k != 'argv'} for key, val in _app_presets().items()},
        'command_presets': {key: {k: v for k, v in val.items() if k != 'argv'} for key, val in COMMAND_PRESETS.items()},
    }


def _preview_open_path(args: Dict[str, Any], *, reveal: bool = False) -> LocalActionResult:
    path = _normalise_existing_path(args.get('path'))
    info = _path_risk(path)
    if reveal:
        info['target'] = str(path.parent if path.is_file() else path)
        info['risk'] = 'safe'
        info['requires_confirmation'] = False
    return LocalActionResult(
        ok=True,
        action_type='reveal_path' if reveal else 'open_path',
        risk=str(info.get('risk') or 'safe'),
        requires_confirmation=bool(info.get('requires_confirmation')),
        executed=False,
        message='Local path action is ready for execution.',
        details=info,
    )


def _open_with_os(path: Path) -> None:
    if _platform_key() == 'windows':
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if _platform_key() == 'macos':
        subprocess.Popen(['open', str(path)])
        return
    subprocess.Popen(['xdg-open', str(path)])


def _execute_open_path(args: Dict[str, Any], *, confirmed: bool = False, reveal: bool = False) -> LocalActionResult:
    preview = _preview_open_path(args, reveal=reveal)
    if preview.requires_confirmation and not confirmed:
        raise PermissionError('This local path action requires explicit confirmation.')
    if not reveal and str(preview.details.get('suffix') or '').lower() in BLOCKED_EXTENSIONS:
        # Guardrail: even with confirmation, avoid launching scripts/executables through open_path.
        # App launches must use approved presets or explicit user-run outside Neo.
        raise PermissionError('Opening executable/script paths is blocked. Use an approved app preset or run it manually.')
    target = Path(str(preview.details.get('target') or preview.details.get('path')))
    _open_with_os(target)
    return LocalActionResult(
        ok=True,
        action_type=preview.action_type,
        risk=preview.risk,
        requires_confirmation=preview.requires_confirmation,
        executed=True,
        message='Local path action executed.',
        details={**preview.details, 'executed_at': _now_iso()},
    )


def _preview_launch_app(args: Dict[str, Any]) -> LocalActionResult:
    app_id = _clean(args.get('app_id'), 120).lower()
    if not app_id:
        raise ValueError('app_id is required.')
    presets = _app_presets()
    spec = presets.get(app_id)
    if not spec:
        raise ValueError(f'Unknown or unsupported approved app preset: {app_id}')
    details = {k: v for k, v in spec.items() if k != 'argv'}
    details['app_id'] = app_id
    details['platform'] = _platform_key()
    return LocalActionResult(
        ok=True,
        action_type='launch_app',
        risk=str(spec.get('risk') or 'safe'),
        requires_confirmation=bool(spec.get('requires_confirmation')),
        executed=False,
        message='Approved app launch is ready.',
        details=details,
    )


def _execute_launch_app(args: Dict[str, Any], *, confirmed: bool = False) -> LocalActionResult:
    preview = _preview_launch_app(args)
    if preview.requires_confirmation and not confirmed:
        raise PermissionError('This app launch requires explicit confirmation.')
    spec = _app_presets()[str(preview.details.get('app_id'))]
    subprocess.Popen([str(part) for part in spec.get('argv') or []], cwd=str(_repo_root()))
    return LocalActionResult(
        ok=True,
        action_type='launch_app',
        risk=preview.risk,
        requires_confirmation=preview.requires_confirmation,
        executed=True,
        message='Approved app launch executed.',
        details={**preview.details, 'executed_at': _now_iso()},
    )


def _validate_argv(argv: Sequence[Any]) -> List[str]:
    clean = [str(part) for part in argv if str(part or '').strip()]
    if not clean:
        raise ValueError('Command preset has no argv.')
    for part in clean:
        token = Path(part).name.lower()
        if token in BLOCKED_COMMAND_TOKENS:
            raise PermissionError(f'Command token is blocked by local PC guardrails: {token}')
    return clean


def _preview_command_preset(args: Dict[str, Any]) -> LocalActionResult:
    preset_id = _clean(args.get('preset_id'), 160).lower()
    if not preset_id:
        raise ValueError('preset_id is required.')
    spec = COMMAND_PRESETS.get(preset_id)
    if not spec:
        raise ValueError(f'Unknown command preset: {preset_id}')
    argv = _validate_argv(spec.get('argv') or [])
    return LocalActionResult(
        ok=True,
        action_type='run_command_preset',
        risk=str(spec.get('risk') or 'safe'),
        requires_confirmation=bool(spec.get('requires_confirmation')),
        executed=False,
        message='Approved command preset is ready.',
        details={
            'preset_id': preset_id,
            'label': spec.get('label'),
            'description': spec.get('description'),
            'argv_preview': shlex.join(argv),
            'timeout_seconds': int(spec.get('timeout_seconds') or DEFAULT_TIMEOUT_SECONDS),
            'cwd': str(_repo_root()) if spec.get('cwd') == 'repo_root' else '',
        },
    )


def _execute_command_preset(args: Dict[str, Any], *, confirmed: bool = False) -> LocalActionResult:
    preview = _preview_command_preset(args)
    if preview.requires_confirmation and not confirmed:
        raise PermissionError('This command preset requires explicit confirmation.')
    spec = COMMAND_PRESETS[str(preview.details.get('preset_id'))]
    argv = _validate_argv(spec.get('argv') or [])
    cwd = str(_repo_root()) if spec.get('cwd') == 'repo_root' else None
    timeout = max(1, min(60, int(spec.get('timeout_seconds') or DEFAULT_TIMEOUT_SECONDS)))
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=False)
    stdout = (completed.stdout or '')[:MAX_STDOUT_CHARS]
    stderr = (completed.stderr or '')[:MAX_STDOUT_CHARS]
    return LocalActionResult(
        ok=completed.returncode == 0,
        action_type='run_command_preset',
        risk=preview.risk,
        requires_confirmation=preview.requires_confirmation,
        executed=True,
        message='Command preset executed.' if completed.returncode == 0 else 'Command preset returned a non-zero exit code.',
        details={
            **preview.details,
            'returncode': int(completed.returncode),
            'stdout': stdout,
            'stderr': stderr,
            'executed_at': _now_iso(),
        },
    )


def preview_local_action(action_type: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = _safe_json(arguments)
    kind = _clean(action_type, 80).lower()
    if kind == 'open_path':
        return _preview_open_path(args).as_dict()
    if kind == 'reveal_path':
        return _preview_open_path(args, reveal=True).as_dict()
    if kind == 'launch_app':
        return _preview_launch_app(args).as_dict()
    if kind == 'run_command_preset':
        return _preview_command_preset(args).as_dict()
    raise ValueError(f'Unsupported local action type: {kind}')


def execute_local_action(
    action_type: str,
    arguments: Dict[str, Any] | None = None,
    *,
    confirmed: bool = False,
    session_id: str = '',
    project_id: str = '',
) -> Dict[str, Any]:
    args = _safe_json(arguments)
    kind = _clean(action_type, 80).lower()
    try:
        if kind == 'open_path':
            result = _execute_open_path(args, confirmed=confirmed)
        elif kind == 'reveal_path':
            result = _execute_open_path(args, confirmed=confirmed, reveal=True)
        elif kind == 'launch_app':
            result = _execute_launch_app(args, confirmed=confirmed)
        elif kind == 'run_command_preset':
            result = _execute_command_preset(args, confirmed=confirmed)
        else:
            raise ValueError(f'Unsupported local action type: {kind}')
        payload = result.as_dict()
        sync_action_memory(
            action_type='tool_result',
            status='success' if payload.get('ok') else 'failed',
            summary=f"Local PC action {kind} executed. risk={payload.get('risk')} message={payload.get('message')}",
            details={'local_action': payload, 'arguments': args, 'confirmed': bool(confirmed)},
            session_id=session_id,
            project_id=project_id,
            entity_id=f"local_pc_{kind}_{abs(hash(json.dumps({'args': args, 'result': payload}, sort_keys=True, default=str))) % 10**12}",
            source_ref=f'assistant_local_pc:{kind}',
        )
        return payload
    except Exception as exc:
        sync_action_memory(
            action_type='failed_attempt',
            status='failed',
            summary=f'Local PC action {kind} failed: {exc}',
            details={'action_type': kind, 'arguments': args, 'confirmed': bool(confirmed), 'error': str(exc)},
            session_id=session_id,
            project_id=project_id,
            entity_id=f"local_pc_failed_{kind}_{abs(hash(json.dumps(args, sort_keys=True, default=str))) % 10**12}",
            source_ref=f'assistant_local_pc:{kind}',
        )
        raise


# Tool-registry wrappers

def tool_local_action_catalog(args: Dict[str, Any]) -> Dict[str, Any]:
    return list_local_action_catalog()


def tool_local_action_preview(args: Dict[str, Any]) -> Dict[str, Any]:
    return preview_local_action(str((args or {}).get('action_type') or ''), (args or {}).get('arguments') if isinstance((args or {}).get('arguments'), dict) else {})


def tool_local_action_execute(args: Dict[str, Any]) -> Dict[str, Any]:
    return execute_local_action(
        str((args or {}).get('action_type') or ''),
        (args or {}).get('arguments') if isinstance((args or {}).get('arguments'), dict) else {},
        confirmed=bool((args or {}).get('confirmed')),
        session_id=str((args or {}).get('session_id') or '').strip(),
        project_id=str((args or {}).get('project_id') or '').strip(),
    )
