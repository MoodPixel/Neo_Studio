from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from .config import CHARACTER_STORE_PATH, ROOT_DIR
from .shared_data_paths import library_data_path, studio_data_path, LIBRARY_USER_DATA, STUDIO_USER_DATA
from .library_common import read_json_dict
from .library_settings_store import get_library_root
from .prompt_bundles import bundle_entries

LEGACY_ROOT = ROOT_DIR / 'neo_library_v1'
LEGACY_USER_DATA = LEGACY_ROOT / 'user_data'
LEGACY_SETTINGS_PATH = library_data_path('neo_library_settings.json', legacy_rel='neo_library_settings.json', default_json={})
LEGACY_PROMPT_PRESETS_PATH = library_data_path('prompt_presets.json', legacy_rel='prompt_presets.json', default_json={'prompts': []})
LEGACY_VAULT_DB_PATH = library_data_path('vault_db.json', legacy_rel='vault_db.json', default_json={'tags': [], 'packs': [], 'mapsets': [], 'loras': []})
LEGACY_LIBRARIES_DIR = LEGACY_ROOT / 'libraries'
LEGACY_LORA_PREVIEW_CACHE_DIR = library_data_path('lora_previews', legacy_rel='lora_previews')


def _path_info(path: Path, *, label: str, purpose: str, shared: bool = False) -> Dict[str, Any]:
    exists = path.exists()
    is_dir = path.is_dir() if exists else str(path).endswith(os.sep)
    writable = False
    try:
        probe = path if path.is_dir() else path.parent
        if probe.exists():
            test_path = probe / '.neo_write_test.tmp'
            test_path.write_text('ok', encoding='utf-8')
            test_path.unlink(missing_ok=True)
            writable = True
    except Exception:
        writable = False
    return {
        'label': label,
        'path': str(path),
        'exists': exists,
        'is_dir': bool(is_dir),
        'writable': writable,
        'shared': bool(shared),
        'purpose': purpose,
    }


def _load_vault_data() -> Dict[str, Any]:
    data = read_json_dict(LEGACY_VAULT_DB_PATH)
    if not data:
        return {'tags': [], 'packs': [], 'mapsets': [], 'loras': []}
    data.setdefault('tags', [])
    data.setdefault('packs', [])
    data.setdefault('mapsets', [])
    data.setdefault('loras', [])
    return data


def _load_legacy_prompt_preset_count() -> int:
    try:
        raw = json.loads(LEGACY_PROMPT_PRESETS_PATH.read_text(encoding='utf-8'))
        rows = raw.get('prompts') if isinstance(raw, dict) else []
        if isinstance(rows, list):
            return len(rows)
    except Exception:
        pass
    return 0


def _load_output_dirs() -> Dict[str, str]:
    lib_dir = LEGACY_ROOT / 'lib'
    if str(lib_dir) not in sys.path:
        sys.path.append(str(lib_dir))
    try:
        from neo_library_store import get_output_dirs  # type: ignore

        rows = get_output_dirs() or {}
        return {str(k): str(v) for k, v in rows.items() if str(v or '').strip()}
    except Exception:
        settings = read_json_dict(LEGACY_SETTINGS_PATH)
        rows = settings.get('output_dirs') if isinstance(settings.get('output_dirs'), dict) else {}
        return {str(k): str(v) for k, v in rows.items() if str(v or '').strip()}


def _legacy_lora_parent_dirs(vault_data: Dict[str, Any]) -> List[str]:
    seen = []
    for row in (vault_data.get('loras') or []):
        if not isinstance(row, dict):
            continue
        file_path = str(row.get('file') or '').strip()
        if not file_path:
            continue
        parent = str(Path(file_path).parent)
        if parent and parent not in seen:
            seen.append(parent)
    return seen


def build_storage_compat_snapshot() -> Dict[str, Any]:
    root = get_library_root()
    vault = _load_vault_data()
    output_dirs = _load_output_dirs()
    legacy_settings = read_json_dict(LEGACY_SETTINGS_PATH)
    cards = [
        _path_info(root, label='Library root', purpose='Prompts, captions, bundles, output metadata, images, thumbs.', shared=True),
        _path_info(LEGACY_SETTINGS_PATH, label='Legacy shared settings', purpose='Shared Library settings file. Library root stays synced here.', shared=True),
        _path_info(CHARACTER_STORE_PATH, label='Character store', purpose='Saved characters continue using the shared Library character path.', shared=True),
        _path_info(LEGACY_LIBRARIES_DIR, label='Prompt snippet libraries', purpose='Prompt Composer snippet markdown files still load from the shared Library snippets folder.', shared=True),
        _path_info(LEGACY_VAULT_DB_PATH, label='Vault / LoRA registry', purpose='Vault data, mapsets, and LoRA registry continue using the old vault DB.', shared=True),
        _path_info(root / 'bundles', label='Bundle records', purpose='Prompt bundles/projects continue saving under the active library root.', shared=True),
        _path_info(root / 'bundle_images', label='Bundle reference images', purpose='Reference images linked to prompt bundles.', shared=True),
        _path_info(root / 'output_metadata', label='Recovered output metadata', purpose='Recovered generation metadata saved from Output Reuse.', shared=True),
        _path_info(LEGACY_PROMPT_PRESETS_PATH, label='Legacy prompt preset store', purpose='Legacy prompt preset payload remains on disk for compatibility tracking.', shared=True),
        _path_info(LEGACY_LORA_PREVIEW_CACHE_DIR, label='LoRA preview cache', purpose='Preview cache folder used by the shared Library vault workflow.', shared=True),
    ]
    counts = {
        'prompt_records': len(list((root / 'prompts').glob('*.json'))),
        'caption_records': len(list((root / 'captions').glob('*.json'))),
        'bundle_records': len(bundle_entries()),
        'composer_libraries': len(list(LEGACY_LIBRARIES_DIR.glob('*.md'))) if LEGACY_LIBRARIES_DIR.exists() else 0,
        'characters': len(json.loads(CHARACTER_STORE_PATH.read_text(encoding='utf-8'))) if CHARACTER_STORE_PATH.exists() else 0,
        'vault_tags': len(vault.get('tags') or []),
        'vault_packs': len(vault.get('packs') or []),
        'vault_mapsets': len(vault.get('mapsets') or []),
        'vault_loras': len(vault.get('loras') or []),
        'legacy_prompt_presets': _load_legacy_prompt_preset_count(),
    }
    notes = [
        'Prompt Composer snippet files still use neo_library_v1/libraries/*.md.',
        f'Characters now resolve through shared data root: {CHARACTER_STORE_PATH}.',
        f'Vault + LoRA registry now resolve through shared data root: {LEGACY_VAULT_DB_PATH}.',
        'Output folder inspection still follows the shared Library output directory config when available.',
        'Prompt/caption records and bundle data still follow the active library root instead of being moved into a new hidden location.',
    ]
    if not LEGACY_SETTINGS_PATH.exists():
        notes.append('Legacy shared settings file does not exist yet. It will be created automatically the next time library root is saved.')
    if legacy_settings.get('library_root'):
        notes.append(f"Legacy shared library_root = {legacy_settings.get('library_root')}")
    return {
        'ok': True,
        'policy': 'Preserve shared Library file locations first. New native UI should reuse those paths instead of inventing new hidden storage.',
        'cards': cards,
        'counts': counts,
        'output_dirs': output_dirs,
        'legacy_lora_parent_dirs': _legacy_lora_parent_dirs(vault),
        'notes': notes,
    }
