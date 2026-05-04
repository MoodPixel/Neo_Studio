from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple

from .caption_contract import normalize_caption_preset_payload
from ..contracts.preset_records import build_preset_bundle, normalize_preset_record
from .library_constants import BUILTIN_CAPTION_PRESETS, BUILTIN_PROMPT_PRESETS
from .library_settings_store import _load_settings, _save_settings


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _normalize_prompt_preset(preset: Dict[str, Any], kind: str = 'custom') -> Dict[str, Any]:
    clean = {**BUILTIN_PROMPT_PRESETS['Custom'], **(preset or {})}
    clean['kind'] = kind
    clean['group'] = str(clean.get('group') or '').strip()
    clean['notes'] = str(clean.get('notes') or '').strip()
    clean['favorite'] = bool(clean.get('favorite', False))
    clean['usage_count'] = int(clean.get('usage_count') or 0)
    clean['last_used'] = str(clean.get('last_used') or '').strip()
    return clean


def _normalize_caption_preset(preset: Dict[str, Any], kind: str = 'custom') -> Dict[str, Any]:
    clean = normalize_caption_preset_payload({**BUILTIN_CAPTION_PRESETS['Custom'], **(preset or {})})
    clean['kind'] = kind
    clean['group'] = str(clean.get('group') or '').strip()
    clean['notes'] = str(clean.get('notes') or '').strip()
    clean['favorite'] = bool(clean.get('favorite', False))
    clean['usage_count'] = int(clean.get('usage_count') or 0)
    clean['last_used'] = str(clean.get('last_used') or '').strip()
    return clean


def get_last_used_prompt_preset() -> str:
    data = _load_settings()
    return str(data.get('last_prompt_preset') or 'Descriptive').strip() or 'Descriptive'


def set_last_used_prompt_preset(name: str) -> str:
    value = (name or '').strip() or 'Descriptive'
    data = _load_settings()
    data['last_prompt_preset'] = value
    custom = data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {}
    if value in custom and isinstance(custom.get(value), dict):
        item = _normalize_prompt_preset(custom.get(value) or {})
        item['usage_count'] = int(item.get('usage_count') or 0) + 1
        item['last_used'] = _now_iso()
        custom[value] = item
        data['prompt_presets'] = custom
    _save_settings(data)
    return value


def get_prompt_presets() -> Dict[str, Dict[str, Any]]:
    data = _load_settings()
    custom = data.get('prompt_presets')
    merged = {k: _normalize_prompt_preset(v, kind='builtin') for k, v in BUILTIN_PROMPT_PRESETS.items()}
    if isinstance(custom, dict):
        for name, preset in custom.items():
            if not isinstance(preset, dict):
                continue
            merged[str(name)] = _normalize_prompt_preset(preset, kind='custom')
    return merged


def save_prompt_preset(name: str, settings: Dict[str, Any]) -> str:
    name = (name or '').strip()
    if not name:
        raise ValueError('Preset name is required.')
    if name in BUILTIN_PROMPT_PRESETS:
        raise ValueError('Choose a different name. Built-in preset names are reserved.')
    data = _load_settings()
    custom = data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {}
    existing = custom.get(name) if isinstance(custom.get(name), dict) else {}
    clean = _normalize_prompt_preset(existing, kind='custom')
    for key in ('style', 'custom_instructions', 'max_tokens', 'temperature', 'top_p', 'top_k', 'group', 'notes', 'favorite'):
        if key in settings:
            clean[key] = settings[key]
    custom[name] = clean
    data['prompt_presets'] = custom
    data['last_prompt_preset'] = name
    _save_settings(data)
    return name


def delete_prompt_preset(name: str) -> None:
    name = (name or '').strip()
    if not name:
        raise ValueError('Preset name is required.')
    if name in BUILTIN_PROMPT_PRESETS:
        raise ValueError('Built-in presets cannot be deleted.')
    data = _load_settings()
    custom = data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {}
    if name in custom:
        custom.pop(name, None)
        data['prompt_presets'] = custom
        if (data.get('last_prompt_preset') or '').strip() == name:
            data['last_prompt_preset'] = 'Descriptive'
        _save_settings(data)


def toggle_prompt_preset_favorite(name: str) -> bool:
    name = (name or '').strip()
    if not name or name in BUILTIN_PROMPT_PRESETS:
        raise ValueError('Only custom presets can be favorited here.')
    data = _load_settings()
    custom = data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {}
    item = _normalize_prompt_preset(custom.get(name) or {}, kind='custom')
    item['favorite'] = not bool(item.get('favorite'))
    custom[name] = item
    data['prompt_presets'] = custom
    _save_settings(data)
    return bool(item['favorite'])


def duplicate_prompt_preset(source_name: str, new_name: str) -> str:
    presets = get_prompt_presets()
    src = presets.get((source_name or '').strip())
    if not src:
        raise ValueError('Preset not found.')
    target = (new_name or '').strip()
    if not target:
        raise ValueError('New preset name is required.')
    if target in BUILTIN_PROMPT_PRESETS:
        raise ValueError('Choose a different name. Built-in preset names are reserved.')
    payload = dict(src)
    payload['favorite'] = False
    payload['usage_count'] = 0
    payload['last_used'] = ''
    return save_prompt_preset(target, payload)


def compare_prompt_presets(name_a: str, name_b: str) -> Dict[str, Any]:
    presets = get_prompt_presets()
    a = presets.get((name_a or '').strip())
    b = presets.get((name_b or '').strip())
    if not a or not b:
        raise ValueError('Select two prompt presets to compare.')
    diffs = []
    for key in ('style', 'custom_instructions', 'max_tokens', 'temperature', 'top_p', 'top_k', 'group', 'notes'):
        if a.get(key) != b.get(key):
            diffs.append({'field': key, 'a': a.get(key), 'b': b.get(key)})
    return {'title_a': name_a, 'title_b': name_b, 'differences': diffs}


def list_preset_records() -> Dict[str, Dict[str, Any]]:
    return {
        'prompt_presets': {name: normalize_preset_record('prompt', name, preset, surface='prompt_caption', source=str(preset.get('kind') or 'custom')) for name, preset in get_prompt_presets().items()},
        'caption_presets': {name: normalize_preset_record('caption', name, preset, surface='prompt_caption', source=str(preset.get('kind') or 'custom')) for name, preset in get_caption_presets().items()},
    }


def export_single_preset_payload(kind: str, name: str) -> Dict[str, Any]:
    kind = (kind or '').strip().lower()
    name = (name or '').strip()
    if kind == 'prompt':
        preset = get_prompt_presets().get(name)
        if not preset:
            raise ValueError('Prompt preset not found.')
        return build_preset_bundle({name: preset}, {})
    if kind == 'caption':
        preset = get_caption_presets().get(name)
        if not preset:
            raise ValueError('Caption preset not found.')
        return build_preset_bundle({}, {name: preset})
    raise ValueError('Unknown preset kind.')


def get_last_used_caption_preset() -> str:
    data = _load_settings()
    return str(data.get('last_caption_preset') or 'Tags').strip() or 'Tags'


def set_last_used_caption_preset(name: str) -> str:
    value = (name or '').strip() or 'Tags'
    data = _load_settings()
    data['last_caption_preset'] = value
    custom = data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {}
    if value in custom and isinstance(custom.get(value), dict):
        item = _normalize_caption_preset(custom.get(value) or {}, kind='custom')
        item['usage_count'] = int(item.get('usage_count') or 0) + 1
        item['last_used'] = _now_iso()
        custom[value] = item
        data['caption_presets'] = custom
    _save_settings(data)
    return value


def get_caption_presets() -> Dict[str, Dict[str, Any]]:
    data = _load_settings()
    custom = data.get('caption_presets')
    merged = {k: _normalize_caption_preset(v, kind='builtin') for k, v in BUILTIN_CAPTION_PRESETS.items()}
    if isinstance(custom, dict):
        for name, preset in custom.items():
            if not isinstance(preset, dict):
                continue
            merged[str(name)] = _normalize_caption_preset(preset, kind='custom')
    return merged


def save_caption_preset(name: str, settings: Dict[str, Any]) -> str:
    name = (name or '').strip()
    if not name:
        raise ValueError('Preset name is required.')
    if name in BUILTIN_CAPTION_PRESETS:
        raise ValueError('Choose a different name. Built-in preset names are reserved.')
    data = _load_settings()
    custom = data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {}
    existing = custom.get(name) if isinstance(custom.get(name), dict) else {}
    clean = _normalize_caption_preset(existing, kind='custom')
    for key in ('prompt_style', 'caption_length', 'custom_prompt', 'max_new_tokens', 'temperature', 'top_p', 'top_k', 'prefix', 'suffix', 'output_style', 'group', 'notes', 'favorite'):
        if key in settings:
            clean[key] = settings[key]
    custom[name] = clean
    data['caption_presets'] = custom
    data['last_caption_preset'] = name
    _save_settings(data)
    return name


def delete_caption_preset(name: str) -> None:
    name = (name or '').strip()
    if not name:
        raise ValueError('Preset name is required.')
    if name in BUILTIN_CAPTION_PRESETS:
        raise ValueError('Built-in presets cannot be deleted.')
    data = _load_settings()
    custom = data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {}
    if name in custom:
        custom.pop(name, None)
        data['caption_presets'] = custom
        if (data.get('last_caption_preset') or '').strip() == name:
            data['last_caption_preset'] = 'Tags'
        _save_settings(data)


def toggle_caption_preset_favorite(name: str) -> bool:
    name = (name or '').strip()
    if not name or name in BUILTIN_CAPTION_PRESETS:
        raise ValueError('Only custom presets can be favorited here.')
    data = _load_settings()
    custom = data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {}
    item = _normalize_caption_preset(custom.get(name) or {}, kind='custom')
    item['favorite'] = not bool(item.get('favorite'))
    custom[name] = item
    data['caption_presets'] = custom
    _save_settings(data)
    return bool(item['favorite'])


def duplicate_caption_preset(source_name: str, new_name: str) -> str:
    presets = get_caption_presets()
    src = presets.get((source_name or '').strip())
    if not src:
        raise ValueError('Preset not found.')
    target = (new_name or '').strip()
    if not target:
        raise ValueError('New preset name is required.')
    if target in BUILTIN_CAPTION_PRESETS:
        raise ValueError('Choose a different name. Built-in preset names are reserved.')
    payload = dict(src)
    payload['favorite'] = False
    payload['usage_count'] = 0
    payload['last_used'] = ''
    return save_caption_preset(target, payload)


def compare_caption_presets(name_a: str, name_b: str) -> Dict[str, Any]:
    presets = get_caption_presets()
    a = presets.get((name_a or '').strip())
    b = presets.get((name_b or '').strip())
    if not a or not b:
        raise ValueError('Select two caption presets to compare.')
    diffs = []
    for key in ('prompt_style', 'caption_length', 'custom_prompt', 'max_new_tokens', 'temperature', 'top_p', 'top_k', 'prefix', 'suffix', 'output_style', 'group', 'notes'):
        if a.get(key) != b.get(key):
            diffs.append({'field': key, 'a': a.get(key), 'b': b.get(key)})
    return {'title_a': name_a, 'title_b': name_b, 'differences': diffs}


def export_presets_payload() -> Dict[str, Any]:
    data = _load_settings()
    return {
        'schema_version': 1,
        'exported_at': _now_iso(),
        'prompt_presets': data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {},
        'caption_presets': data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {},
    }


def import_presets_payload(payload: Dict[str, Any], mode: str = 'merge') -> Dict[str, int]:
    if not isinstance(payload, dict):
        raise ValueError('Preset import file must contain a JSON object.')
    data = _load_settings()
    mode = (mode or 'merge').strip().lower()
    if mode not in {'merge', 'replace'}:
        mode = 'merge'

    prompt_presets = payload.get('prompt_presets') if isinstance(payload.get('prompt_presets'), dict) else {}
    caption_presets = payload.get('caption_presets') if isinstance(payload.get('caption_presets'), dict) else {}
    kept_prompt = {} if mode == 'replace' else (data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {})
    kept_caption = {} if mode == 'replace' else (data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {})

    imported_prompt = 0
    for name, preset in prompt_presets.items():
        name = str(name).strip()
        if not name or name in BUILTIN_PROMPT_PRESETS or not isinstance(preset, dict):
            continue
        kept_prompt[name] = _normalize_prompt_preset(preset, kind='custom')
        imported_prompt += 1

    imported_caption = 0
    for name, preset in caption_presets.items():
        name = str(name).strip()
        if not name or name in BUILTIN_CAPTION_PRESETS or not isinstance(preset, dict):
            continue
        kept_caption[name] = _normalize_caption_preset(preset, kind='custom')
        imported_caption += 1

    data['prompt_presets'] = kept_prompt
    data['caption_presets'] = kept_caption
    _save_settings(data)
    return {'prompt_presets': imported_prompt, 'caption_presets': imported_caption}
