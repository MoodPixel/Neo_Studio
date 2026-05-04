from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

APP_SETTINGS_SCHEMA_VERSION = 1

DEFAULT_APP_SETTINGS: Dict[str, Any] = {
    'schema_version': APP_SETTINGS_SCHEMA_VERSION,
    'theme': {
        'appearance': 'dark',
        'accent_color': 'blue',
    },
    'startup': {
        'show_welcome_on_launch': True,
        'last_open_surface': 'generate',
        'dev_mode': False,
    },
    'ui': {
        'compact_backend_status': True,
        'use_workspace_setup_strip': True,
        'generation_action_order': 'left',
        'surface_sidebar_collapsed': False,
    },
    'surfaces': {
        'generate': {},
        'video': {},
        'voice': {},
        'audio': {},
        'manager': {},
        'roleplay': {},
        'assistant': {},
        'admin': {},
    },
}


def normalize_app_settings_payload(data: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = deepcopy(DEFAULT_APP_SETTINGS)
    data = data if isinstance(data, dict) else {}
    if isinstance(data.get('theme'), dict):
        payload['theme']['appearance'] = str(data['theme'].get('appearance') or payload['theme']['appearance']).strip() or payload['theme']['appearance']
        payload['theme']['accent_color'] = str(data['theme'].get('accent_color') or payload['theme']['accent_color']).strip() or payload['theme']['accent_color']
    if isinstance(data.get('startup'), dict):
        payload['startup']['show_welcome_on_launch'] = bool(data['startup'].get('show_welcome_on_launch', payload['startup']['show_welcome_on_launch']))
        payload['startup']['last_open_surface'] = str(data['startup'].get('last_open_surface') or payload['startup']['last_open_surface']).strip() or payload['startup']['last_open_surface']
        payload['startup']['dev_mode'] = bool(data['startup'].get('dev_mode', payload['startup']['dev_mode']))
    if isinstance(data.get('ui'), dict):
        payload['ui']['compact_backend_status'] = bool(data['ui'].get('compact_backend_status', payload['ui']['compact_backend_status']))
        payload['ui']['use_workspace_setup_strip'] = bool(data['ui'].get('use_workspace_setup_strip', payload['ui']['use_workspace_setup_strip']))
        payload['ui']['generation_action_order'] = str(data['ui'].get('generation_action_order') or payload['ui']['generation_action_order']).strip().lower()
        if payload['ui']['generation_action_order'] not in {'left', 'right'}:
            payload['ui']['generation_action_order'] = payload['ui']['generation_action_order'] if payload['ui']['generation_action_order'] in {'left','right'} else 'left'
        payload['ui']['surface_sidebar_collapsed'] = bool(data['ui'].get('surface_sidebar_collapsed', payload['ui']['surface_sidebar_collapsed']))
    if isinstance(data.get('surfaces'), dict):
        for key, value in data['surfaces'].items():
            if isinstance(value, dict):
                payload['surfaces'][str(key)] = deepcopy(value)
    return payload
