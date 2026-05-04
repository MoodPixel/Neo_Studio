from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

SURFACE_SCHEMA_VERSION = 2


CUTOVER_STATE_PATH = Path(__file__).resolve().parents[2] / 'devtools' / 'migrations' / 'roleplay_v2_soft_cutover_state.json'


def load_roleplay_v2_cutover_state() -> dict:
    if not CUTOVER_STATE_PATH.exists():
        return {
            'soft_cutover_active': False,
            'hide_legacy_surface': False,
            'legacy_read_only': False,
            'force_v2_label': False,
        }
    try:
        payload = json.loads(CUTOVER_STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        payload = {}
    return {
        'soft_cutover_active': bool(payload.get('soft_cutover_active')),
        'hide_legacy_surface': bool(payload.get('hide_legacy_surface')),
        'legacy_read_only': bool(payload.get('legacy_read_only')),
        'force_v2_label': bool(payload.get('force_v2_label')),
    }


SURFACE_DEFINITIONS = {
    'generate': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'generate',
        'label': 'Image',
        'nav_order': 10,
        'maturity': 'partially_stable',
        'section_id': 'tab-generate',
        'lazy_module': 'generation',
        'required_backend_roles': ['image'],
        'optional_backend_roles': ['text'],
        'default_subsurface': 'sdxl_sd',
        'helper_enabled': True,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Build images, edits, and model-family workflows from one visual workspace.',
    },
    'video': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'video',
        'label': 'Video',
        'nav_order': 20,
        'maturity': 'skeleton',
        'section_id': 'tab-video',
        'lazy_module': 'video',
        'required_backend_roles': ['video'],
        'optional_backend_roles': ['image', 'text'],
        'default_subsurface': 'wan22_5b_balanced',
        'helper_enabled': True,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Simple video-level workspace only for now: basic prompt/setup lanes are present, but the full video pipeline is not finished yet.',
    },
    'voice': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'voice',
        'label': 'Voice',
        'nav_order': 30,
        'maturity': 'skeleton',
        'section_id': 'tab-voice',
        'lazy_module': 'voice',
        'required_backend_roles': ['voice'],
        'optional_backend_roles': ['text'],
        'default_subsurface': 'tts',
        'helper_enabled': True,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Not yet implemented: Voice is a placeholder shell for future TTS planning, backend wiring, preview, and export tools.',
    },
    'audio': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'audio',
        'label': 'Music / SFX',
        'nav_order': 40,
        'maturity': 'skeleton',
        'section_id': 'tab-audio',
        'lazy_module': 'audio',
        'required_backend_roles': ['audio'],
        'optional_backend_roles': ['text'],
        'default_subsurface': 'generate',
        'helper_enabled': True,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Not yet implemented: Music / SFX is a placeholder shell for future audio generation, preview, and export tools.',
    },
    'board': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'board',
        'label': 'Board',
        'nav_order': 75,
        'maturity': 'skeleton',
        'section_id': 'tab-board',
        'lazy_module': 'board',
        'required_backend_roles': [],
        'optional_backend_roles': [],
        'default_subsurface': 'workspace',
        'helper_enabled': False,
        'show_backend_chip': False,
        'admin_section_key': None,
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Plan ideas, references, notes, and rough creative direction in a lightweight local-first board workspace.',
    },
    'manager': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'manager',
        'label': 'Prompt & Caption',
        'nav_order': 50,
        'maturity': 'partially_stable',
        'section_id': 'tab-manager',
        'lazy_module': 'manager',
        'required_backend_roles': [],
        'optional_backend_roles': ['text', 'image'],
        'default_subsurface': 'prompt',
        'helper_enabled': True,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Write prompts, caption images, search the library, and save reusable text tools.',
    },
    'roleplay_v2': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'roleplay_v2',
        'label': 'Roleplay',
        'nav_order': 60,
        'maturity': 'stable',
        'section_id': 'tab-roleplay_v2',
        'lazy_module': 'roleplay_v2',
        'required_backend_roles': [],
        'optional_backend_roles': ['text'],
        'default_subsurface': 'workspace',
        'helper_enabled': False,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Use the unified story surface for roleplay, source-first authoring, runtime bundles, save/resume, and scene-state-aware live continuation.',
    },
    'assistant': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'assistant',
        'label': 'Assistant',
        'nav_order': 70,
        'maturity': 'partially_stable',
        'section_id': 'tab-assistant',
        'lazy_module': 'assistant',
        'required_backend_roles': ['text'],
        'optional_backend_roles': [],
        'default_subsurface': 'chat',
        'helper_enabled': False,
        'show_backend_chip': True,
        'admin_section_key': 'backends',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Use the utility assistant for planning, support, cleanup, and creative problem-solving.',
    },
    'admin': {
        'schema_version': SURFACE_SCHEMA_VERSION,
        'id': 'admin',
        'label': 'Admin',
        'nav_order': 80,
        'maturity': 'partially_stable',
        'section_id': 'tab-admin',
        'lazy_module': 'admin',
        'required_backend_roles': [],
        'optional_backend_roles': ['text', 'image'],
        'default_subsurface': 'system',
        'helper_enabled': False,
        'show_backend_chip': False,
        'admin_section_key': 'system',
        'dev_only': False,
        'enabled': True,
        'launch_board_copy': 'Manage backends, extensions, data health, and startup rules without cluttering the other tabs.',
    },
}


def _sorted_surface_rows(include_disabled: bool = True) -> list[dict]:
    rows: list[dict] = []
    cutover_state = load_roleplay_v2_cutover_state()
    legacy_hidden = bool(cutover_state.get('hide_legacy_surface'))
    for key in SURFACE_DEFINITIONS:
        row = deepcopy(SURFACE_DEFINITIONS[key])
        if key == 'roleplay_v2' and legacy_hidden:
            row['nav_order'] = 60
            row['label'] = 'Roleplay'
        row.setdefault('section_id', f"tab-{row['id']}")
        row.setdefault('lazy_module', row['id'])
        row.setdefault('nav_order', 999)
        row.setdefault('maturity', 'stable')
        if include_disabled or row.get('enabled'):
            rows.append(row)
    rows.sort(key=lambda item: (int(item.get('nav_order') or 999), item.get('id') or ''))
    return rows


def list_surface_definitions(include_disabled: bool = True) -> list[dict]:
    return _sorted_surface_rows(include_disabled=include_disabled)


def build_surface_boot_registry(include_disabled: bool = False) -> list[dict]:
    rows = []
    for row in _sorted_surface_rows(include_disabled=include_disabled):
        rows.append({
            'schema_version': row.get('schema_version', SURFACE_SCHEMA_VERSION),
            'id': row['id'],
            'label': row['label'],
            'nav_order': row.get('nav_order', 999),
            'maturity': row.get('maturity', 'stable'),
            'section_id': row.get('section_id', f"tab-{row['id']}"),
            'lazy_module': row.get('lazy_module', row['id']),
            'required_backend_roles': list(row.get('required_backend_roles') or []),
            'optional_backend_roles': list(row.get('optional_backend_roles') or []),
            'default_subsurface': row.get('default_subsurface'),
            'helper_enabled': bool(row.get('helper_enabled')),
            'show_backend_chip': bool(row.get('show_backend_chip')),
            'admin_section_key': row.get('admin_section_key'),
            'dev_only': bool(row.get('dev_only')),
            'enabled': bool(row.get('enabled', True)),
            'launch_board_copy': row.get('launch_board_copy', ''),
        })
    return rows
