from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict
from uuid import uuid4

BACKEND_PROFILE_SCHEMA_VERSION = 1
BACKEND_PROFILE_ROLES = ('text', 'image', 'video', 'voice', 'audio', 'embedding')
MANAGED_BACKEND_PROFILE_ROLES = ('text', 'image', 'video', 'voice', 'audio')
AUXILIARY_BACKEND_PROFILE_ROLES = ('embedding',)
BACKEND_PROFILE_ADAPTERS: Dict[str, tuple[str, ...]] = {
    'text': ('koboldcpp',),
    'image': ('comfyui',),
    'video': ('comfyui',),
    'voice': ('kokoro', 'chatterbox', 'zonos', 'custom_tts'),
    'audio': ('stable_audio', 'ace_step', 'custom_audio'),
    'embedding': ('hashing_local', 'chroma_default', 'custom_embedding'),
}

ROLE_DEFAULT_TIMEOUTS = {
    'text': 8,
    'image': 12,
    'video': 20,
    'voice': 20,
    'audio': 30,
    'embedding': 8,
}

ROLE_DEFAULT_BASE_URLS = {
    'text': 'http://localhost:5001',
    'image': 'http://127.0.0.1:8188',
    'video': 'http://127.0.0.1:8188',
    'voice': '',
    'audio': '',
    'embedding': '',
}

ROLE_DEFAULT_CAPABILITIES = {
    'text': ['chat', 'models'],
    'image': ['txt2img', 'img2img', 'inpaint', 'outpaint'],
    'video': ['t2v', 'i2v', 'repair', 'upscale', 'interpolate'],
    'voice': ['tts', 'voices', 'preview'],
    'audio': ['text_to_audio', 'audio_to_audio', 'preview'],
    'embedding': ['embed', 'query'],
}

ROLE_DEFAULT_HEALTHCHECKS = {
    'text': {'type': 'http', 'path': '/v1/models', 'timeout_sec': 8},
    'image': {'type': 'http', 'path': '/system_stats', 'timeout_sec': 12},
    'video': {'type': 'http', 'path': '/system_stats', 'timeout_sec': 20},
    'voice': {'type': 'none', 'path': '', 'timeout_sec': 20},
    'audio': {'type': 'none', 'path': '', 'timeout_sec': 30},
    'embedding': {'type': 'none', 'path': '', 'timeout_sec': 8},
}


def _normalize_url(url: str) -> str:
    text = str(url or '').strip()
    if not text:
        return ''
    if not text.startswith('http://') and not text.startswith('https://'):
        text = 'http://' + text
    return text.rstrip('/')


def normalize_backend_profile_for_role(role: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    clean_role = str(role or '').strip().lower()
    if clean_role not in BACKEND_PROFILE_ROLES:
        raise ValueError(f'Unsupported backend role: {role}')
    adapter_options = BACKEND_PROFILE_ADAPTERS.get(clean_role, ('',))
    adapter = str(profile.get('adapter') or profile.get('backend_type') or adapter_options[0] or '').strip().lower()
    if adapter not in adapter_options:
        adapter = adapter_options[0] or ''
    timeout_default = int(ROLE_DEFAULT_TIMEOUTS.get(clean_role, 8))
    try:
        timeout_sec = int(float(profile.get('timeout_sec') or timeout_default))
    except Exception:
        timeout_sec = timeout_default
    timeout_sec = max(2, min(120, timeout_sec))
    base_url = _normalize_url(str(profile.get('base_url') or ROLE_DEFAULT_BASE_URLS.get(clean_role, '')))
    raw_health = profile.get('healthcheck') if isinstance(profile.get('healthcheck'), dict) else {}
    healthcheck = {
        'type': str(raw_health.get('type') or ROLE_DEFAULT_HEALTHCHECKS[clean_role]['type']).strip() or 'none',
        'path': str(raw_health.get('path') or ROLE_DEFAULT_HEALTHCHECKS[clean_role]['path']).strip(),
        'timeout_sec': int(raw_health.get('timeout_sec') or timeout_sec),
    }
    auth = profile.get('auth') if isinstance(profile.get('auth'), dict) else {'mode': 'none'}
    capabilities = profile.get('capabilities') if isinstance(profile.get('capabilities'), list) else list(ROLE_DEFAULT_CAPABILITIES.get(clean_role, []))
    profile_id = str(profile.get('id') or profile.get('profile_id') or f'{clean_role}_{adapter}_{uuid4().hex[:8]}').strip()
    label = str(profile.get('label') or profile.get('name') or f'{adapter.title()} Profile').strip() or f'{adapter.title()} Profile'
    notes = str(profile.get('notes') or '').strip()
    raw_launcher = profile.get('launcher') if isinstance(profile.get('launcher'), dict) else {}
    launch_type = str(raw_launcher.get('launch_type') or raw_launcher.get('type') or 'bat').strip().lower()
    if launch_type not in {'exe', 'bat', 'py', 'custom'}:
        launch_type = 'bat'
    launcher = {
        'launch_type': launch_type,
        'backend_path': str(raw_launcher.get('backend_path') or raw_launcher.get('path') or '').strip(),
        'working_dir': str(raw_launcher.get('working_dir') or raw_launcher.get('cwd') or '').strip(),
        'launch_args': str(raw_launcher.get('launch_args') or raw_launcher.get('args') or '').strip(),
        'native_ui_url': _normalize_url(str(raw_launcher.get('native_ui_url') or '')).strip(),
        'enabled': bool(raw_launcher.get('enabled', True)),
    }
    return {
        'schema_version': BACKEND_PROFILE_SCHEMA_VERSION,
        'profile_id': profile_id,
        'id': profile_id,
        'role': clean_role,
        'label': label,
        'name': label,
        'adapter': adapter,
        'backend_type': adapter,
        'transport': str(profile.get('transport') or 'http').strip().lower() or 'http',
        'base_url': base_url,
        'timeout_sec': timeout_sec,
        'healthcheck': healthcheck,
        'auth': auth,
        'capabilities': [str(item).strip() for item in capabilities if str(item).strip()],
        'auto_reconnect': bool(profile.get('auto_reconnect')),
        'enabled': bool(profile.get('enabled', True)),
        'is_default_for_role': bool(profile.get('is_default_for_role', False)),
        'dev_only': bool(profile.get('dev_only', False)),
        'notes': notes,
        'launcher': launcher,
    }


def default_profile_for_role(role: str) -> Dict[str, Any] | None:
    clean_role = str(role or '').strip().lower()
    if clean_role == 'text':
        return normalize_backend_profile_for_role('text', {
            'profile_id': 'text_kobold_local',
            'label': 'KoboldCpp Local',
            'adapter': 'koboldcpp',
            'base_url': ROLE_DEFAULT_BASE_URLS['text'],
            'timeout_sec': ROLE_DEFAULT_TIMEOUTS['text'],
            'auto_reconnect': False,
            'enabled': True,
            'is_default_for_role': True,
        })
    if clean_role == 'image':
        return normalize_backend_profile_for_role('image', {
            'profile_id': 'image_comfy_local',
            'label': 'ComfyUI Local',
            'adapter': 'comfyui',
            'base_url': ROLE_DEFAULT_BASE_URLS['image'],
            'timeout_sec': ROLE_DEFAULT_TIMEOUTS['image'],
            'auto_reconnect': False,
            'enabled': True,
            'is_default_for_role': True,
        })
    if clean_role == 'video':
        return normalize_backend_profile_for_role('video', {
            'profile_id': 'video_comfy_local',
            'label': 'ComfyUI Video Local',
            'adapter': 'comfyui',
            'base_url': ROLE_DEFAULT_BASE_URLS['video'],
            'timeout_sec': ROLE_DEFAULT_TIMEOUTS['video'],
            'auto_reconnect': False,
            'enabled': True,
            'is_default_for_role': True,
            'notes': 'Separate video role using the same adapter family so image and video contracts can evolve independently.',
        })
    return None


def default_backend_settings_payload() -> Dict[str, Any]:
    payload = {
        'schema_version': BACKEND_PROFILE_SCHEMA_VERSION,
        'profiles': {role: [] for role in BACKEND_PROFILE_ROLES},
        'active_profile_ids': {role: '' for role in BACKEND_PROFILE_ROLES},
        'settings': {
            'low_vram_mode': True,
        },
    }
    for role in ('text', 'image', 'video'):
        profile = default_profile_for_role(role)
        if profile:
            payload['profiles'][role] = [profile]
            payload['active_profile_ids'][role] = profile['profile_id']
    return payload


def normalize_backend_settings_payload(data: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = default_backend_settings_payload()
    data = data if isinstance(data, dict) else {}
    if isinstance(data.get('profiles'), dict):
        for role in BACKEND_PROFILE_ROLES:
            rows = data.get('profiles', {}).get(role)
            if isinstance(rows, list) and rows:
                payload['profiles'][role] = [normalize_backend_profile_for_role(role, row if isinstance(row, dict) else {}) for row in rows]
    if isinstance(data.get('active_profile_ids'), dict):
        for role in BACKEND_PROFILE_ROLES:
            value = str(data.get('active_profile_ids', {}).get(role) or '').strip()
            if value:
                payload['active_profile_ids'][role] = value
    if isinstance(data.get('settings'), dict):
        payload['settings']['low_vram_mode'] = bool(data.get('settings', {}).get('low_vram_mode', payload['settings']['low_vram_mode']))
    for role in BACKEND_PROFILE_ROLES:
        rows = payload['profiles'].get(role, [])
        ids = {str(row.get('profile_id') or row.get('id') or '').strip() for row in rows if str(row.get('profile_id') or row.get('id') or '').strip()}
        active = str(payload['active_profile_ids'].get(role) or '').strip()
        if active not in ids:
            payload['active_profile_ids'][role] = next(iter(ids), '')
        default_assigned = False
        for row in rows:
            row['is_default_for_role'] = str(row.get('profile_id') or row.get('id') or '').strip() == str(payload['active_profile_ids'].get(role) or '').strip()
            if row['is_default_for_role']:
                default_assigned = True
        if not default_assigned and rows:
            rows[0]['is_default_for_role'] = True
    return payload
