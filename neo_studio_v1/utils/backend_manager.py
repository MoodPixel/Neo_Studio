from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import os
import shlex
import subprocess
import sys
import webbrowser

from ..contracts.backend_profiles import (
    BACKEND_PROFILE_ADAPTERS,
    BACKEND_PROFILE_SCHEMA_VERSION,
    MANAGED_BACKEND_PROFILE_ROLES,
    ROLE_DEFAULT_TIMEOUTS,
    default_backend_settings_payload,
    normalize_backend_profile_for_role,
    normalize_backend_settings_payload,
)
from .library_common import atomic_write_json, read_json_dict
from .library_constants import USER_DATA_DIR
from .backend_probe_runtime import probe_comfyui, probe_generic_service, probe_koboldcpp
from .logging_utils import get_logger

logger = get_logger(__name__)

BACKEND_SETTINGS_PATH = USER_DATA_DIR / 'backend_manager.json'
BACKEND_LAUNCH_LOG_DIR = USER_DATA_DIR / 'backend_launch_logs'
BACKEND_LAUNCH_RUNTIME_PATH = USER_DATA_DIR / 'backend_launch_runtime.json'

ACTIVE_BACKEND_ROLES = MANAGED_BACKEND_PROFILE_ROLES
DEFAULT_SETTINGS: Dict[str, Any] = default_backend_settings_payload()
DEFAULT_TIMEOUTS = {role: int(ROLE_DEFAULT_TIMEOUTS.get(role, 8)) for role in ACTIVE_BACKEND_ROLES}
AVAILABLE_BACKEND_TYPES = {role: list(BACKEND_PROFILE_ADAPTERS.get(role, ())) for role in ACTIVE_BACKEND_ROLES}

# Phase 5: saved launcher state is only a recovery hint. If Neo restarts,
# in-memory process handles are gone, so old launching/running rows must not
# keep surface launch buttons locked forever.
STALE_LAUNCHING_RUNTIME_SECONDS = 120
STALE_RUNNING_RUNTIME_SECONDS = 300

AUTO_RECONNECT_ATTEMPTED = False

LAUNCH_RUNTIME_STATE: Dict[str, Dict[str, Any]] = {}
ACTIVE_LAUNCH_PROCESSES: Dict[str, subprocess.Popen[Any]] = {}


def _load_launch_runtime_state() -> Dict[str, Dict[str, Any]]:
    data = read_json_dict(BACKEND_LAUNCH_RUNTIME_PATH)
    rows = data.get('runtime') if isinstance(data.get('runtime'), dict) else data
    if not isinstance(rows, dict):
        return {}
    runtime: Dict[str, Dict[str, Any]] = {}
    for role, row in rows.items():
        clean_role = str(role or '').strip().lower()
        if clean_role not in ACTIVE_BACKEND_ROLES or not isinstance(row, dict):
            continue
        status = str(row.get('status') or 'unknown').strip().lower()
        if status not in {'unknown', 'launching', 'running', 'failed'}:
            status = 'unknown'
        runtime[clean_role] = {
            'role': clean_role,
            'profile_id': str(row.get('profile_id') or '').strip(),
            'profile_name': str(row.get('profile_name') or '').strip(),
            'status': status,
            'started_at': str(row.get('started_at') or '').strip(),
            'updated_at': str(row.get('updated_at') or '').strip(),
            'command': str(row.get('command') or '').strip(),
            'log_path': str(row.get('log_path') or '').strip(),
            'message': str(row.get('message') or '').strip(),
        }
    return runtime


def _save_launch_runtime_state() -> Dict[str, Dict[str, Any]]:
    payload = {
        'schema_version': 1,
        'updated_at': _utc_now(),
        'runtime': deepcopy(LAUNCH_RUNTIME_STATE),
    }
    atomic_write_json(BACKEND_LAUNCH_RUNTIME_PATH, payload)
    return deepcopy(LAUNCH_RUNTIME_STATE)


def _set_launch_runtime(role: str, state: Dict[str, Any]) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    current = LAUNCH_RUNTIME_STATE.get(clean_role, {})
    status = str(state.get('status') or current.get('status') or 'unknown').strip().lower()
    if status not in {'unknown', 'launching', 'running', 'failed'}:
        status = 'unknown'
    merged = {
        **current,
        **state,
        'role': clean_role,
        'status': status,
        'updated_at': _utc_now(),
    }
    LAUNCH_RUNTIME_STATE[clean_role] = merged
    _save_launch_runtime_state()
    return deepcopy(merged)



def _parse_launch_runtime_timestamp(value: Any) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _launch_runtime_age_seconds(row: Dict[str, Any]) -> float | None:
    stamp = _parse_launch_runtime_timestamp(row.get('updated_at') or row.get('started_at'))
    if stamp is None:
        return None
    try:
        return max(0.0, (datetime.utcnow() - stamp).total_seconds())
    except Exception:
        return None


def _cleanup_stale_launch_runtime_state(save: bool = True) -> bool:
    # Phase 5: reset stale launch rows on boot / state refresh.
    # This is intentionally conservative: a current connected session or a
    # tracked live Popen handle is proof enough to keep a row active.
    changed = False
    for role, row in list(LAUNCH_RUNTIME_STATE.items()):
        clean_role = str(role or '').strip().lower()
        status = str((row or {}).get('status') or 'unknown').strip().lower()
        if status not in {'launching', 'running'}:
            continue
        if _launch_process_is_alive(clean_role):
            continue
        if bool(SESSION_STATE.get(clean_role, {}).get('connected')):
            continue
        age = _launch_runtime_age_seconds(row)
        max_age = STALE_LAUNCHING_RUNTIME_SECONDS if status == 'launching' else STALE_RUNNING_RUNTIME_SECONDS
        # Missing/invalid timestamps are stale because they cannot be trusted.
        if age is None or age >= max_age:
            LAUNCH_RUNTIME_STATE[clean_role] = {
                **row,
                'role': clean_role,
                'status': 'unknown',
                'updated_at': _utc_now(),
                'message': (
                    f'Stale {status} launcher state was cleared. '
                    'No connected backend or live launch process is currently tracked; launch is available again.'
                ),
            }
            changed = True
    if changed and save:
        _save_launch_runtime_state()
    return changed

def _refresh_launch_process_state() -> None:
    # Display-only process liveness tracking for launch buttons.
    # This does not stop, hide, or force-control any backend process.
    if not ACTIVE_LAUNCH_PROCESSES:
        return
    for role, process in list(ACTIVE_LAUNCH_PROCESSES.items()):
        try:
            exit_code = process.poll()
        except Exception:
            exit_code = None
        if exit_code is None:
            continue
        ACTIVE_LAUNCH_PROCESSES.pop(role, None)
        runtime = LAUNCH_RUNTIME_STATE.get(role, {})
        _set_launch_runtime(role, {
            **runtime,
            'status': 'failed' if exit_code else 'unknown',
            'message': f'Backend launcher process exited with code {exit_code}. Launch button is available again.',
        })


def _launch_process_is_alive(role: str) -> bool:
    process = ACTIVE_LAUNCH_PROCESSES.get(role)
    if process is None:
        return False
    try:
        return process.poll() is None
    except Exception:
        return False


def _runtime_row_for_display(role: str, row: Dict[str, Any]) -> Dict[str, Any]:
    # Phase 4: saved "running" is not proof after reload.
    clean_role = str(role or "").strip().lower()
    output = deepcopy(row or {})
    status = str(output.get("status") or "unknown").strip().lower()
    tracked_process_alive = _launch_process_is_alive(clean_role)
    session_connected = bool(SESSION_STATE.get(clean_role, {}).get("connected"))
    verified_running = bool(session_connected or tracked_process_alive)
    output["verified_running"] = verified_running
    output["tracked_process_alive"] = tracked_process_alive
    output["session_connected"] = session_connected
    if status == "running" and not verified_running:
        output["status"] = "unknown"
        output["message"] = "Launcher status is stale. Backend is not connected and no live launch process is tracked; launch is available again."
    return output


def get_launch_runtime_state() -> Dict[str, Dict[str, Any]]:
    if not LAUNCH_RUNTIME_STATE:
        LAUNCH_RUNTIME_STATE.update(_load_launch_runtime_state())
        _cleanup_stale_launch_runtime_state(save=True)
    _refresh_launch_process_state()
    _cleanup_stale_launch_runtime_state(save=True)
    return {role: _runtime_row_for_display(role, row) for role, row in deepcopy(LAUNCH_RUNTIME_STATE).items()}

SESSION_STATE: Dict[str, Dict[str, Any]] = {
    'text': {
        'state': 'offline',
        'connected': False,
        'message': 'No active text backend connected.',
        'backend_type': 'koboldcpp',
        'profile_id': '',
        'profile_name': '',
        'base_url': '',
        'capabilities': [],
        'last_checked': '',
        'latency_ms': None,
        'details': {},
    },
    'image': {
        'state': 'offline',
        'connected': False,
        'message': 'No active image backend connected.',
        'backend_type': 'comfyui',
        'profile_id': '',
        'profile_name': '',
        'base_url': '',
        'capabilities': [],
        'last_checked': '',
        'latency_ms': None,
        'details': {},
    },
    'video': {
        'state': 'offline',
        'connected': False,
        'message': 'No active video backend connected.',
        'backend_type': 'comfyui',
        'profile_id': '',
        'profile_name': '',
        'base_url': '',
        'capabilities': [],
        'last_checked': '',
        'latency_ms': None,
        'details': {},
    },
    'voice': {
        'state': 'offline',
        'connected': False,
        'message': 'No active voice backend connected.',
        'backend_type': 'kokoro',
        'profile_id': '',
        'profile_name': '',
        'base_url': '',
        'capabilities': [],
        'last_checked': '',
        'latency_ms': None,
        'details': {},
    },
    'audio': {
        'state': 'offline',
        'connected': False,
        'message': 'No active audio backend connected.',
        'backend_type': 'stable_audio',
        'profile_id': '',
        'profile_name': '',
        'base_url': '',
        'capabilities': [],
        'last_checked': '',
        'latency_ms': None,
        'details': {},
    },
}


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def normalize_url(url: str) -> str:
    text = str(url or '').strip()
    if not text:
        return ''
    if not text.startswith('http://') and not text.startswith('https://'):
        text = 'http://' + text
    return text.rstrip('/')


def _ensure_supported_role(role: str) -> str:
    clean_role = str(role or '').strip().lower()
    if clean_role not in ACTIVE_BACKEND_ROLES:
        raise ValueError(f'Unsupported backend role: {role}')
    return clean_role


def _profile_id(profile: Dict[str, Any] | None) -> str:
    if not isinstance(profile, dict):
        return ''
    return str(profile.get('profile_id') or profile.get('id') or '').strip()


def _profile_name(profile: Dict[str, Any] | None) -> str:
    if not isinstance(profile, dict):
        return ''
    return str(profile.get('label') or profile.get('name') or '').strip()


def _normalize_profile(role: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    clean = normalize_backend_profile_for_role(clean_role, profile if isinstance(profile, dict) else {})
    clean['base_url'] = normalize_url(clean.get('base_url') or '')
    clean['backend_type'] = str(clean.get('backend_type') or clean.get('adapter') or '').strip().lower()
    clean['adapter'] = str(clean.get('adapter') or clean.get('backend_type') or '').strip().lower()
    clean['profile_id'] = _profile_id(clean)
    clean['id'] = clean['profile_id']
    clean['label'] = _profile_name(clean)
    clean['name'] = clean['label']
    raw_launcher = clean.get('launcher') if isinstance(clean.get('launcher'), dict) else {}
    launch_type = str(raw_launcher.get('launch_type') or 'bat').strip().lower()
    if launch_type not in {'exe', 'bat', 'py', 'custom'}:
        launch_type = 'bat'
    clean['launcher'] = {
        'launch_type': launch_type,
        'backend_path': str(raw_launcher.get('backend_path') or '').strip(),
        'working_dir': str(raw_launcher.get('working_dir') or '').strip(),
        'launch_args': str(raw_launcher.get('launch_args') or '').strip(),
        'native_ui_url': normalize_url(raw_launcher.get('native_ui_url') or ''),
        'enabled': bool(raw_launcher.get('enabled', True)),
    }
    return clean


def _filtered_manager_payload(data: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = normalize_backend_settings_payload(data if isinstance(data, dict) else {})
    payload['schema_version'] = int(payload.get('schema_version') or BACKEND_PROFILE_SCHEMA_VERSION)
    for role in ACTIVE_BACKEND_ROLES:
        rows = payload.get('profiles', {}).get(role) or []
        payload['profiles'][role] = [_normalize_profile(role, row if isinstance(row, dict) else {}) for row in rows]
        active_id = str(payload.get('active_profile_ids', {}).get(role) or '').strip()
        ids = {_profile_id(row) for row in payload['profiles'][role] if _profile_id(row)}
        if active_id not in ids:
            payload['active_profile_ids'][role] = next(iter(ids), '')
        active_id = str(payload['active_profile_ids'].get(role) or '').strip()
        for row in payload['profiles'][role]:
            row['is_default_for_role'] = _profile_id(row) == active_id
    return payload


def load_backend_settings() -> Dict[str, Any]:
    data = read_json_dict(BACKEND_SETTINGS_PATH)
    return _filtered_manager_payload(data)


def save_backend_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = _filtered_manager_payload(data)
    atomic_write_json(BACKEND_SETTINGS_PATH, payload)
    return payload


def list_profiles(role: str) -> list[Dict[str, Any]]:
    clean_role = _ensure_supported_role(role)
    settings = load_backend_settings()
    return list(settings.get('profiles', {}).get(clean_role, []))


def get_profile(role: str, profile_id: str | None = None) -> Dict[str, Any] | None:
    clean_role = _ensure_supported_role(role)
    settings = load_backend_settings()
    target_id = str(profile_id or settings.get('active_profile_ids', {}).get(clean_role) or '').strip()
    for row in settings.get('profiles', {}).get(clean_role, []):
        if _profile_id(row) == target_id:
            return row
    return None


def upsert_profile(role: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    settings = load_backend_settings()
    rows = list(settings.get('profiles', {}).get(clean_role, []))
    raw_payload = payload if isinstance(payload, dict) else {}
    incoming_launcher = raw_payload.get('launcher') if isinstance(raw_payload.get('launcher'), dict) else {}
    incoming_launcher_has_path = bool(str(incoming_launcher.get('backend_path') or '').strip())
    incoming_launcher_has_any = any(str(incoming_launcher.get(key) or '').strip() for key in ('backend_path', 'working_dir', 'launch_args', 'native_ui_url'))
    raw_target_id = str(raw_payload.get('profile_id') or raw_payload.get('id') or '').strip()
    # Guardrail: if a stale UI refresh posts an empty launcher for an existing profile,
    # preserve the previously saved launch fields instead of wiping them.
    if raw_target_id and not incoming_launcher_has_path and not incoming_launcher_has_any:
        existing = next((row for row in rows if _profile_id(row) == raw_target_id), None)
        existing_launcher = existing.get('launcher') if isinstance(existing, dict) and isinstance(existing.get('launcher'), dict) else {}
        if str(existing_launcher.get('backend_path') or '').strip():
            raw_payload = {**raw_payload, 'launcher': existing_launcher}
    profile = _normalize_profile(clean_role, raw_payload)
    target_id = _profile_id(profile)
    found = False
    for idx, row in enumerate(rows):
        if _profile_id(row) == target_id:
            rows[idx] = profile
            found = True
            break
    if not found:
        rows.append(profile)
    settings['profiles'][clean_role] = rows
    settings['active_profile_ids'][clean_role] = target_id
    saved = save_backend_settings(settings)
    return next((row for row in saved.get('profiles', {}).get(clean_role, []) if _profile_id(row) == target_id), profile)


def delete_profile(role: str, profile_id: str) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    settings = load_backend_settings()
    target_id = str(profile_id or '').strip()
    rows = [row for row in settings.get('profiles', {}).get(clean_role, []) if _profile_id(row) != target_id]
    if not rows:
        rows = deepcopy(DEFAULT_SETTINGS.get('profiles', {}).get(clean_role, []))
    settings['profiles'][clean_role] = rows
    ids = {_profile_id(row) for row in rows if _profile_id(row)}
    active_id = str(settings.get('active_profile_ids', {}).get(clean_role) or '').strip()
    if active_id not in ids:
        settings['active_profile_ids'][clean_role] = next(iter(ids), '')
    if clean_role in SESSION_STATE and str(SESSION_STATE[clean_role].get('profile_id') or '').strip() == target_id:
        SESSION_STATE[clean_role] = {
            **SESSION_STATE[clean_role],
            'state': 'offline',
            'connected': False,
            'message': 'Backend disconnected.',
            'profile_id': '',
            'profile_name': '',
            'base_url': '',
            'capabilities': [],
            'details': {},
        }
    return save_backend_settings(settings)


def set_active_profile(role: str, profile_id: str) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    settings = load_backend_settings()
    settings['active_profile_ids'][clean_role] = str(profile_id or '').strip()
    return save_backend_settings(settings)


def set_low_vram_mode(enabled: bool) -> Dict[str, Any]:
    settings = load_backend_settings()
    settings['settings']['low_vram_mode'] = bool(enabled)
    return save_backend_settings(settings)


async def probe_profile(role: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    backend_type = str(profile.get('backend_type') or profile.get('adapter') or '').strip().lower()
    if clean_role == 'text' and backend_type == 'koboldcpp':
        return await probe_koboldcpp(profile)
    if clean_role in {'image', 'video'} and backend_type == 'comfyui':
        return await probe_comfyui(profile, role=clean_role)
    if clean_role == 'voice' and backend_type in {'kokoro', 'chatterbox', 'zonos', 'custom_tts'}:
        return await probe_generic_service(profile, adapter=backend_type, role='voice', capabilities=['tts', 'voices', 'preview'])
    if clean_role == 'audio' and backend_type in {'stable_audio', 'ace_step', 'custom_audio'}:
        return await probe_generic_service(profile, adapter=backend_type, role='audio', capabilities=['text_to_audio', 'audio_to_audio', 'preview'])
    return {
        'ok': False,
        'backend_type': backend_type,
        'base_url': normalize_url(profile.get('base_url') or ''),
        'state': 'error',
        'message': f'Unsupported backend type for role {clean_role}: {backend_type or "(none)"}',
        'latency_ms': None,
        'capabilities': [],
        'details': {},
    }


async def connect_profile(role: str, profile_id: str | None = None) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    profile = get_profile(clean_role, profile_id)
    if not profile:
        return {
            'ok': False,
            'state': 'error',
            'message': f'No saved {clean_role} backend profile found.',
            'capabilities': [],
            'details': {},
        }
    result = await probe_profile(clean_role, profile)
    resolved_profile_id = _profile_id(profile)
    resolved_name = _profile_name(profile)
    session = {
        'state': result.get('state') or ('connected' if result.get('ok') else 'error'),
        'connected': bool(result.get('ok')),
        'message': result.get('message') or '',
        'backend_type': profile.get('backend_type') or result.get('backend_type') or '',
        'profile_id': resolved_profile_id,
        'profile_name': resolved_name,
        'base_url': result.get('base_url') or profile.get('base_url') or '',
        'capabilities': list(result.get('capabilities') or []),
        'last_checked': _utc_now(),
        'latency_ms': result.get('latency_ms'),
        'details': result.get('details') or {},
    }
    if result.get('models'):
        session['details']['models'] = result.get('models')
    SESSION_STATE[clean_role] = session
    if result.get('ok'):
        settings = load_backend_settings()
        settings['active_profile_ids'][clean_role] = resolved_profile_id
        save_backend_settings(settings)
    return {**result, 'session': deepcopy(session), 'profile': profile}


async def refresh_profile(role: str) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    session = SESSION_STATE.get(clean_role, {})
    profile_id = str(session.get('profile_id') or load_backend_settings().get('active_profile_ids', {}).get(clean_role) or '').strip()
    if not profile_id:
        return {
            'ok': False,
            'state': 'offline',
            'message': f'No {clean_role} backend profile selected.',
            'session': deepcopy(SESSION_STATE.get(clean_role, {})),
        }
    return await connect_profile(clean_role, profile_id)


def disconnect_profile(role: str) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    session = SESSION_STATE.get(clean_role, {})
    SESSION_STATE[clean_role] = {
        **session,
        'state': 'offline',
        'connected': False,
        'message': 'Disconnected.',
        'base_url': '',
        'capabilities': [],
        'latency_ms': None,
        'details': {},
        'last_checked': _utc_now(),
    }
    return deepcopy(SESSION_STATE[clean_role])


def get_effective_base_url(role: str) -> str:
    clean_role = _ensure_supported_role(role)
    session = SESSION_STATE.get(clean_role) or {}
    if session.get('connected') and session.get('base_url'):
        return normalize_url(session.get('base_url') or '')
    return ''



def _launcher_log_path(role: str, profile_id: str) -> Path:
    BACKEND_LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_profile = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in str(profile_id or 'unsaved'))
    return BACKEND_LAUNCH_LOG_DIR / f'{role}_{safe_profile}.log'

def _build_launch_command(launcher: Dict[str, Any]) -> tuple[list[str] | str, bool]:
    launch_type = str(launcher.get('launch_type') or 'bat').strip().lower()
    backend_path = str(launcher.get('backend_path') or '').strip()
    launch_args = str(launcher.get('launch_args') or '').strip()
    if not backend_path:
        raise ValueError('Backend path / command is empty.')
    if launch_type == 'custom':
        command = backend_path
        if launch_args:
            command = f'{command} {launch_args}'
        return command, True
    args = shlex.split(launch_args, posix=(os.name != 'nt')) if launch_args else []
    if launch_type == 'py':
        return [sys.executable, backend_path, *args], False
    if launch_type == 'bat' and os.name == 'nt':
        return ['cmd.exe', '/c', backend_path, *args], False
    return [backend_path, *args], False

def launch_profile_backend(role: str, profile_id: str | None = None) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    profile = get_profile(clean_role, profile_id)
    if not profile:
        raise ValueError(f'No saved {clean_role} backend profile found.')
    launcher = profile.get('launcher') if isinstance(profile.get('launcher'), dict) else {}
    if not str(launcher.get('backend_path') or '').strip():
        state = _set_launch_runtime(clean_role, {
            'profile_id': _profile_id(profile),
            'profile_name': _profile_name(profile),
            'status': 'failed',
            'started_at': _utc_now(),
            'command': '',
            'log_path': '',
            'message': 'No backend launcher path/command saved for this profile.',
        })
        raise ValueError(state['message'])
    profile_id_resolved = _profile_id(profile)
    log_path = _launcher_log_path(clean_role, profile_id_resolved)
    cwd = str(launcher.get('working_dir') or '').strip() or None
    try:
        command, use_shell = _build_launch_command(launcher)
        command_text = command if isinstance(command, str) else ' '.join(command)
        if cwd and not Path(cwd).exists():
            raise ValueError(f'Working directory does not exist: {cwd}')
        _set_launch_runtime(clean_role, {
            'profile_id': profile_id_resolved,
            'profile_name': _profile_name(profile),
            'status': 'launching',
            'started_at': _utc_now(),
            'command': command_text,
            'log_path': str(log_path),
            'message': 'Backend launch requested.',
        })
        log_handle = open(log_path, 'a', encoding='utf-8', errors='replace')
        log_handle.write(f"\n[{_utc_now()}] Launch requested for {clean_role}/{profile_id_resolved}\n")
        log_handle.write(f"Command: {command_text}\n")
        if cwd:
            log_handle.write(f"Working directory: {cwd}\n")
        log_handle.flush()
        # Keep backend launch visible/stable for Phase 8.
        # We intentionally DO NOT hide or capture the backend console here.
        # On Windows, open a normal new console so users can see Comfy/Kobold startup output.
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        process = subprocess.Popen(
            command,
            cwd=cwd,
            shell=use_shell,
            stdin=subprocess.DEVNULL,
            close_fds=(os.name != 'nt'),
            creationflags=creationflags,
        )
        try:
            log_handle.close()
        except Exception:
            pass
        ACTIVE_LAUNCH_PROCESSES[clean_role] = process
        state = _set_launch_runtime(clean_role, {
            'profile_id': profile_id_resolved,
            'profile_name': _profile_name(profile),
            'status': 'running',
            'started_at': _utc_now(),
            'command': command_text,
            'log_path': str(log_path),
            'message': f'Backend launch started. Runtime tracking is display-only; Neo will not stop this process yet.',
        })
        # Keep PID out of the saved public runtime payload for Phase 8. We are not using it for stop/kill control yet.
        state['pid_display_only'] = process.pid
        return deepcopy(state)
    except Exception as exc:
        message = str(exc) or 'Backend launch failed.'
        try:
            BACKEND_LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8', errors='replace') as log_handle:
                log_handle.write(f"\n[{_utc_now()}] Launch failed for {clean_role}/{profile_id_resolved}: {message}\n")
        except Exception:
            pass
        _set_launch_runtime(clean_role, {
            'profile_id': profile_id_resolved,
            'profile_name': _profile_name(profile),
            'status': 'failed',
            'started_at': _utc_now(),
            'command': str(launcher.get('backend_path') or '').strip(),
            'log_path': str(log_path),
            'message': message,
        })
        raise

def get_launch_log(role: str, profile_id: str | None = None) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    profile = get_profile(clean_role, profile_id)
    resolved = _profile_id(profile) if profile else str(profile_id or '').strip()
    log_path = _launcher_log_path(clean_role, resolved or 'unsaved')
    if not log_path.exists():
        return {'ok': True, 'log_path': str(log_path), 'log': 'No launch log has been written yet.'}
    text = log_path.read_text(encoding='utf-8', errors='replace')
    return {'ok': True, 'log_path': str(log_path), 'log': text[-12000:]}

def open_profile_native_ui(role: str, profile_id: str | None = None) -> Dict[str, Any]:
    clean_role = _ensure_supported_role(role)
    profile = get_profile(clean_role, profile_id)
    if not profile:
        raise ValueError(f'No saved {clean_role} backend profile found.')
    launcher = profile.get('launcher') if isinstance(profile.get('launcher'), dict) else {}
    url = normalize_url(launcher.get('native_ui_url') or profile.get('base_url') or '')
    if not url:
        raise ValueError('No native UI URL or Base URL is saved for this profile.')
    webbrowser.open(url)
    return {'ok': True, 'url': url, 'message': f'Opened native UI in browser only: {url}'}

def get_manager_state() -> Dict[str, Any]:
    settings = load_backend_settings()
    return {
        'settings': settings,
        'profiles': settings.get('profiles', {}),
        'active_profile_ids': settings.get('active_profile_ids', {}),
        'session': deepcopy(SESSION_STATE),
        'launcher_runtime': get_launch_runtime_state(),
        'available_backend_types': AVAILABLE_BACKEND_TYPES,
        'managed_roles': list(ACTIVE_BACKEND_ROLES),
    }


async def maybe_auto_reconnect() -> None:
    global AUTO_RECONNECT_ATTEMPTED
    if AUTO_RECONNECT_ATTEMPTED:
        return
    AUTO_RECONNECT_ATTEMPTED = True
    settings = load_backend_settings()
    for role in ACTIVE_BACKEND_ROLES:
        active_id = str(settings.get('active_profile_ids', {}).get(role) or '').strip()
        profile = get_profile(role, active_id) if active_id else None
        if not profile or not profile.get('auto_reconnect'):
            continue
        try:
            await connect_profile(role, active_id)
        except Exception as exc:
            logger.warning('Auto reconnect failed for %s backend %s: %s', role, active_id, exc)
