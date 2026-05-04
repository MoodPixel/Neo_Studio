from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .library_common import new_id, record_sort_key, safe_name
from .library_settings_store import get_library_root
from .library_storage import delete_temp_upload, temp_path_from_id
from .output_metadata import get_output_metadata_record
from .characters import get_character_record
from .storage_io import atomic_write_json


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _bundle_dir() -> Path:
    root = get_library_root()
    path = root / 'bundles'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bundle_image_dir() -> Path:
    root = get_library_root()
    path = root / 'bundle_images'
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundle_entries() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for rec in sorted(iter_bundle_records(), key=record_sort_key, reverse=True):
        created = str(rec.get('created_at') or '')[:19].replace('T', ' ')
        name = str(rec.get('name') or '').strip() or '(untitled)'
        item = {
            'id': str(rec.get('id') or ''),
            'name': name,
            'label': f'{name} — {created}' if created else name,
            'character_name': rec.get('character_name') or '',
            'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
            'has_reference_image': bool(rec.get('reference_image_rel')),
            'model_default': rec.get('model_default') or '',
            'checkpoint_default': rec.get('checkpoint_default') or '',
        }
        items.append(item)
    return items


def iter_bundle_records() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fp in sorted(_bundle_dir().glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
            if isinstance(rec, dict):
                rec['_record_path'] = str(fp)
                out.append(rec)
        except Exception:
            continue
    return out


def _unique_bundle_name(requested_name: str, exclude_id: str | None = None) -> str:
    base = safe_name(requested_name)
    used = set()
    for rec in iter_bundle_records():
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


def _normalize_loras(value: Any) -> List[str]:
    if isinstance(value, list):
        rows = value
    else:
        rows = str(value or '').replace('\n', ',').split(',')
    out = []
    seen = set()
    for row in rows:
        item = str(row or '').strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(item)
    return out


def get_bundle_record(bundle_id: str = '', name: str = '') -> Dict[str, Any] | None:
    target_id = (bundle_id or '').strip()
    target_name = (name or '').strip().lower()
    for rec in iter_bundle_records():
        if target_id and str(rec.get('id') or '') == target_id:
            return _clean_bundle_record(rec)
        if target_name and str(rec.get('name') or '').strip().lower() == target_name:
            return _clean_bundle_record(rec)
    return None


def _reference_urls(record: Dict[str, Any]) -> Dict[str, str]:
    bundle_id = str(record.get('id') or '')
    image_url = f'/api/bundle-reference-image?bundle_id={bundle_id}' if bundle_id and record.get('reference_image_rel') else ''
    return {'reference_image_url': image_url}


def _clean_bundle_record(record: Dict[str, Any]) -> Dict[str, Any]:
    clean = {k: v for k, v in record.items() if not str(k).startswith('_')}
    clean.update(_reference_urls(clean))
    return clean


def _snapshot_metadata_record(record_id: str) -> Dict[str, Any] | None:
    rec = get_output_metadata_record(record_id)
    if not rec:
        return None
    return {
        'id': rec.get('id') or '',
        'name': rec.get('name') or '',
        'source_filename': rec.get('source_filename') or '',
        'created_at': rec.get('created_at') or '',
        'data': rec.get('data') or {},
    }


def _snapshot_character(name: str) -> Dict[str, Any] | None:
    rec = get_character_record(name)
    if not rec:
        return None
    return {'id': rec.get('id') or '', 'name': rec.get('name') or '', 'content': rec.get('content') or ''}


def attach_reference_image_from_temp(record: Dict[str, Any], temp_image_id: str, original_name: str = '') -> Dict[str, Any]:
    temp_image_id = (temp_image_id or '').strip()
    if not temp_image_id:
        return record
    src = temp_path_from_id(temp_image_id)
    if not src.exists():
        return record
    image_dir = _bundle_image_dir()
    suffix = src.suffix.lower() or '.png'
    dst = image_dir / f"{record['id']}{suffix}"
    shutil.copy2(src, dst)
    delete_temp_upload(temp_image_id)
    old_rel = str(record.get('reference_image_rel') or '').strip()
    if old_rel and old_rel != str(dst.relative_to(get_library_root())):
        old_path = get_library_root() / old_rel
        old_path.unlink(missing_ok=True)
    record['reference_image_rel'] = str(dst.relative_to(get_library_root())).replace('\\', '/')
    record['reference_image_name'] = original_name or dst.name
    record['reference_updated_at'] = _now_iso()
    return record


def _write_bundle_record(record: Dict[str, Any], path: Path | None = None) -> Dict[str, Any]:
    target = path or (_bundle_dir() / f"{record['id']}.json")
    atomic_write_json(target, record)
    return _clean_bundle_record(record)


def save_bundle(
    name: str,
    positive_prompt: str,
    negative_prompt: str = '',
    character_name: str = '',
    loras: Any = None,
    model_default: str = '',
    checkpoint_default: str = '',
    cfg_default: Any = '',
    steps_default: Any = '',
    sampler_default: str = '',
    style_notes: str = '',
    metadata_record_id: str = '',
    metadata_snapshot: Dict[str, Any] | None = None,
    reference_temp_image_id: str = '',
    reference_image_name: str = '',
) -> Dict[str, Any]:
    now = _now_iso()
    record = {
        'schema_version': 1,
        'id': new_id('bnd'),
        'kind': 'bundle',
        'name': _unique_bundle_name(name),
        'positive_prompt': str(positive_prompt or '').strip(),
        'negative_prompt': str(negative_prompt or '').strip(),
        'character_name': str(character_name or '').strip(),
        'character_snapshot': _snapshot_character(character_name) if character_name else None,
        'loras': _normalize_loras(loras),
        'model_default': str(model_default or '').strip(),
        'checkpoint_default': str(checkpoint_default or '').strip(),
        'cfg_default': str(cfg_default or '').strip(),
        'steps_default': str(steps_default or '').strip(),
        'sampler_default': str(sampler_default or '').strip(),
        'style_notes': str(style_notes or '').strip(),
        'metadata_record_id': str(metadata_record_id or '').strip(),
        'metadata_snapshot': metadata_snapshot or (_snapshot_metadata_record(metadata_record_id) if metadata_record_id else None),
        'reference_image_rel': '',
        'reference_image_name': '',
        'created_at': now,
        'updated_at': now,
        'source': 'neo_studio_bundle',
    }
    if reference_temp_image_id:
        record = attach_reference_image_from_temp(record, reference_temp_image_id, reference_image_name)
    return _write_bundle_record(record)


def update_bundle_record(
    bundle_id: str,
    name: str,
    positive_prompt: str,
    negative_prompt: str = '',
    character_name: str = '',
    loras: Any = None,
    model_default: str = '',
    checkpoint_default: str = '',
    cfg_default: Any = '',
    steps_default: Any = '',
    sampler_default: str = '',
    style_notes: str = '',
    metadata_record_id: str = '',
    reference_temp_image_id: str = '',
    reference_image_name: str = '',
    clear_reference_image: bool = False,
) -> Dict[str, Any]:
    existing = None
    path = None
    for rec in iter_bundle_records():
        if str(rec.get('id') or '') == (bundle_id or '').strip():
            existing = rec
            path = Path(rec.get('_record_path') or '')
            break
    if not existing or not path:
        raise FileNotFoundError('Bundle not found.')
    old_rel = str(existing.get('reference_image_rel') or '').strip()
    existing['name'] = _unique_bundle_name(name or existing.get('name') or 'untitled', exclude_id=existing.get('id'))
    existing['positive_prompt'] = str(positive_prompt or '').strip()
    existing['negative_prompt'] = str(negative_prompt or '').strip()
    existing['character_name'] = str(character_name or '').strip()
    existing['character_snapshot'] = _snapshot_character(character_name) if character_name else None
    existing['loras'] = _normalize_loras(loras)
    existing['model_default'] = str(model_default or '').strip()
    existing['checkpoint_default'] = str(checkpoint_default or '').strip()
    existing['cfg_default'] = str(cfg_default or '').strip()
    existing['steps_default'] = str(steps_default or '').strip()
    existing['sampler_default'] = str(sampler_default or '').strip()
    existing['style_notes'] = str(style_notes or '').strip()
    existing['metadata_record_id'] = str(metadata_record_id or '').strip()
    existing['metadata_snapshot'] = _snapshot_metadata_record(metadata_record_id) if metadata_record_id else None
    existing['updated_at'] = _now_iso()
    if clear_reference_image and old_rel:
        (get_library_root() / old_rel).unlink(missing_ok=True)
        existing['reference_image_rel'] = ''
        existing['reference_image_name'] = ''
    if reference_temp_image_id:
        existing = attach_reference_image_from_temp(existing, reference_temp_image_id, reference_image_name)
    return _write_bundle_record({k: v for k, v in existing.items() if not str(k).startswith('_')}, path)


def delete_bundle_record(bundle_id: str) -> bool:
    target = (bundle_id or '').strip()
    if not target:
        return False
    for rec in iter_bundle_records():
        if str(rec.get('id') or '') != target:
            continue
        rel = str(rec.get('reference_image_rel') or '').strip()
        if rel:
            (get_library_root() / rel).unlink(missing_ok=True)
        Path(rec.get('_record_path') or '').unlink(missing_ok=True)
        return True
    return False


def duplicate_bundle_record(bundle_id: str, new_name: str = '') -> Dict[str, Any]:
    rec = get_bundle_record(bundle_id=bundle_id)
    if not rec:
        raise FileNotFoundError('Bundle not found.')
    dup = save_bundle(
        name=new_name or f"{rec.get('name') or 'Bundle'} Copy",
        positive_prompt=rec.get('positive_prompt') or '',
        negative_prompt=rec.get('negative_prompt') or '',
        character_name=rec.get('character_name') or '',
        loras=rec.get('loras') or [],
        model_default=rec.get('model_default') or '',
        checkpoint_default=rec.get('checkpoint_default') or '',
        cfg_default=rec.get('cfg_default') or '',
        steps_default=rec.get('steps_default') or '',
        sampler_default=rec.get('sampler_default') or '',
        style_notes=rec.get('style_notes') or '',
        metadata_record_id=rec.get('metadata_record_id') or '',
        metadata_snapshot=rec.get('metadata_snapshot') or None,
    )
    rel = str(rec.get('reference_image_rel') or '').strip()
    if rel:
        src = get_library_root() / rel
        if src.exists():
            dst = _bundle_image_dir() / f"{dup['id']}{src.suffix.lower() or '.png'}"
            shutil.copy2(src, dst)
            dup_full = get_bundle_record(bundle_id=dup['id']) or dup
            clean = {k: v for k, v in dup_full.items() if not str(k).startswith('_')}
            clean['reference_image_rel'] = str(dst.relative_to(get_library_root())).replace('\\', '/')
            clean['reference_image_name'] = rec.get('reference_image_name') or src.name
            _write_bundle_record(clean)
            return get_bundle_record(bundle_id=dup['id']) or _clean_bundle_record(clean)
    return dup