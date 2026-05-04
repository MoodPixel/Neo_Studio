from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .library_common import atomic_write_json, new_id, record_sort_key, safe_name
from .library_settings_store import get_library_root, set_last_used_category, update_categories_file
from .library_storage import iter_records


def unique_prompt_name(category: str, requested_name: str, exclude_id: str | None = None) -> str:
    base = safe_name(requested_name)
    used = set()
    cat = (category or '').strip() or 'uncategorized'
    for rec in iter_records('prompt'):
        if str(rec.get('category') or 'uncategorized').strip() != cat:
            continue
        if exclude_id and str(rec.get('id') or '') == exclude_id:
            continue
        used.add(str(rec.get('name') or '').strip().lower())
    if base.lower() not in used:
        return base
    i = 2
    while True:
        candidate = f'{base} ({i})'
        if candidate.lower() not in used:
            return candidate
        i += 1


def prompt_categories() -> List[str]:
    vals = sorted({str((r.get('category') or 'uncategorized')).strip() or 'uncategorized' for r in iter_records('prompt')}, key=str.lower)
    return vals or ['uncategorized']


def prompt_entries(category: str = '') -> List[Dict[str, str]]:
    cat = (category or '').strip()
    items = []
    for rec in sorted(iter_records('prompt'), key=record_sort_key, reverse=True):
        rc = str((rec.get('category') or 'uncategorized')).strip() or 'uncategorized'
        if cat and rc != cat:
            continue
        created = str(rec.get('created_at') or '')[:19].replace('T', ' ')
        name = str((rec.get('name') or '')).strip() or '(untitled)'
        label = f'{name} — {created}' if created else name
        items.append({
            'id': str(rec.get('id') or ''),
            'name': name,
            'label': label,
            'category': rc,
            'created_at': created,
        })
    return items


def prompt_names(category: str) -> List[str]:
    return [x['label'] for x in prompt_entries(category)]


def get_prompt_record(category: str = '', name: str = '', prompt_id: str = '') -> Dict[str, Any] | None:
    cat = (category or '').strip()
    prompt_id = (prompt_id or '').strip()
    target = (name or '').strip().lower()
    for rec in sorted(iter_records('prompt'), key=record_sort_key, reverse=True):
        rc = str((rec.get('category') or 'uncategorized')).strip() or 'uncategorized'
        if prompt_id and str(rec.get('id') or '') == prompt_id:
            return rec
        if cat and rc != cat:
            continue
        if target and str((rec.get('name') or '')).strip().lower() == target:
            return rec
    return None


def save_prompt(
    name: str,
    category: str,
    prompt: str,
    model: str,
    notes: str = '',
    tags: List[str] | None = None,
    raw_prompt: str = '',
    preset_name: str = '',
    style: str = '',
    finish_reason: str = '',
    settings: Dict[str, Any] | None = None,
    generation_mode: str = 'generate',
) -> Dict[str, Any]:
    root = get_library_root()
    category = (category or '').strip() or 'uncategorized'
    now = datetime.now().isoformat(timespec='seconds')
    entry_id = new_id('prm')
    final_name = unique_prompt_name(category, name)
    record = {
        'schema_version': 2,
        'id': entry_id,
        'kind': 'prompt',
        'name': final_name,
        'category': category,
        'prompt': (prompt or '').strip(),
        'raw_prompt': (raw_prompt or prompt or '').strip(),
        'notes': (notes or '').strip(),
        'model': (model or '').strip(),
        'created_at': now,
        'updated_at': now,
        'tags': tags or [],
        'source': 'neo_studio',
        'preset_name': (preset_name or '').strip(),
        'style': (style or '').strip(),
        'finish_reason': (finish_reason or '').strip(),
        'settings': settings or {},
        'generation_mode': (generation_mode or 'generate').strip(),
    }
    fp = root / 'prompts' / f'{entry_id}.json'
    atomic_write_json(fp, record)
    update_categories_file(category)
    set_last_used_category('prompt', category)
    return record


def update_prompt_record(
    category: str = '',
    name: str = '',
    prompt: str = '',
    model: str = '',
    notes: str = '',
    raw_prompt: str = '',
    prompt_id: str = '',
    style: str = '',
) -> Dict[str, Any]:
    rec = get_prompt_record(category=category, name=name, prompt_id=prompt_id)
    if not rec:
        raise FileNotFoundError('Prompt not found.')
    rec_id = str(rec.get('id') or '')
    next_category = (category or rec.get('category') or 'uncategorized').strip() or 'uncategorized'
    next_name = unique_prompt_name(next_category, name or rec.get('name') or 'untitled', exclude_id=rec_id)
    rec['name'] = next_name
    rec['category'] = next_category
    rec['prompt'] = (prompt or '').strip()
    rec['raw_prompt'] = (raw_prompt or prompt or '').strip()
    rec['model'] = (model or rec.get('model') or '').strip()
    rec['notes'] = (notes or '').strip()
    rec['style'] = (style or rec.get('style') or '').strip()
    rec['updated_at'] = datetime.now().isoformat(timespec='seconds')
    fp = Path(rec.get('_record_path') or '')
    clean = {k: v for k, v in rec.items() if not k.startswith('_')}
    atomic_write_json(fp, clean)
    update_categories_file(next_category)
    set_last_used_category('prompt', next_category)
    return clean


def delete_prompt_record(category: str = '', name: str = '', prompt_id: str = '') -> bool:
    rec = get_prompt_record(category=category, name=name, prompt_id=prompt_id)
    if not rec:
        return False
    Path(rec.get('_record_path') or '').unlink(missing_ok=True)
    return True
