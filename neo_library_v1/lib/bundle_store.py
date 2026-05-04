from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from neo_library_store import get_library_root, get_output_metadata_root
try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path

EXT_ROOT = Path(__file__).resolve().parents[1]
USER_DATA_DIR = library_data_path('', legacy_rel='')
CC_SAVED_PATH = library_data_path('saved_characters.json', legacy_rel='saved_characters.json', default_json=[])


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _safe_name(name: str) -> str:
    name = (name or '').strip() or 'untitled'
    cleaned = ''.join(c if c.isalnum() or c in ('-', '_', ' ') else '_' for c in name).strip()
    return cleaned[:80] or 'untitled'


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"


def _record_sort_key(rec: Dict[str, Any]) -> str:
    return str(rec.get('updated_at') or rec.get('created_at') or '')


def _bundle_dir() -> Path:
    root = get_library_root() / 'bundles'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bundle_image_dir() -> Path:
    root = get_library_root() / 'bundle_images'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_json_dict(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _normalize_loras(value: Any) -> List[str]:
    if isinstance(value, list):
        rows = value
    else:
        rows = str(value or '').replace('\n', ',').split(',')
    out: List[str] = []
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


def _saved_characters_map() -> Dict[str, str]:
    try:
        data = json.loads(CC_SAVED_PATH.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {str(k): str(v or '') for k, v in data.items()}
    except Exception:
        pass
    return {}


def character_entries() -> List[Dict[str, Any]]:
    data = _saved_characters_map()
    rows = []
    for name in sorted(data.keys(), key=str.lower):
        rows.append({'id': name, 'name': name, 'label': name})
    return rows


def _snapshot_character(name: str) -> Dict[str, Any] | None:
    nm = (name or '').strip()
    if not nm:
        return None
    data = _saved_characters_map()
    if nm not in data:
        return None
    return {'id': nm, 'name': nm, 'content': data.get(nm) or ''}


def metadata_record_entries() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for fp in sorted(get_output_metadata_root().glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        name = str(rec.get('name') or '').strip() or fp.stem
        rid = str(rec.get('id') or fp.stem).strip()
        created = str(rec.get('created_at') or '')[:19].replace('T', ' ')
        label = f'{name} — {created}' if created else name
        rows.append({'id': rid, 'name': name, 'label': label})
    return rows


def _snapshot_metadata_record(record_id: str) -> Dict[str, Any] | None:
    rid = (record_id or '').strip()
    if not rid:
        return None
    for fp in sorted(get_output_metadata_root().glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        if str(rec.get('id') or fp.stem).strip() == rid:
            return {
                'id': rec.get('id') or rid,
                'name': rec.get('name') or fp.stem,
                'source_filename': rec.get('source_filename') or '',
                'created_at': rec.get('created_at') or '',
                'data': rec.get('data') or {},
            }
    return None


def iter_bundle_records() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for fp in sorted(_bundle_dir().glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        if isinstance(rec, dict):
            rec['_record_path'] = str(fp)
            rows.append(rec)
    return rows


def _clean_bundle_record(record: Dict[str, Any]) -> Dict[str, Any]:
    clean = {k: v for k, v in record.items() if not str(k).startswith('_')}
    rel = str(clean.get('reference_image_rel') or '').strip()
    clean['reference_image_path'] = str((get_library_root() / rel).resolve()) if rel and (get_library_root() / rel).exists() else ''
    return clean


def bundle_entries() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for rec in sorted(iter_bundle_records(), key=_record_sort_key, reverse=True):
        clean = _clean_bundle_record(rec)
        created = str(clean.get('created_at') or '')[:19].replace('T', ' ')
        name = str(clean.get('name') or '').strip() or '(untitled)'
        items.append({
            'id': str(clean.get('id') or ''),
            'name': name,
            'label': f'{name} — {created}' if created else name,
            'character_name': clean.get('character_name') or '',
            'updated_at': clean.get('updated_at') or clean.get('created_at') or '',
            'has_reference_image': bool(clean.get('reference_image_rel')),
            'model_default': clean.get('model_default') or '',
            'checkpoint_default': clean.get('checkpoint_default') or '',
        })
    return items


def _unique_bundle_name(requested_name: str, exclude_id: str | None = None) -> str:
    base = _safe_name(requested_name)
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


def get_bundle_record(bundle_id: str = '', name: str = '') -> Dict[str, Any] | None:
    target_id = (bundle_id or '').strip()
    target_name = (name or '').strip().lower()
    for rec in iter_bundle_records():
        if target_id and str(rec.get('id') or '') == target_id:
            return _clean_bundle_record(rec)
        if target_name and str(rec.get('name') or '').strip().lower() == target_name:
            return _clean_bundle_record(rec)
    return None


def _write_bundle_record(record: Dict[str, Any], path: Path | None = None) -> Dict[str, Any]:
    target = path or (_bundle_dir() / f"{record['id']}.json")
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    return _clean_bundle_record(record)


def _attach_reference_image(record: Dict[str, Any], source_path: str = '', clear_existing: bool = False) -> Dict[str, Any]:
    src_path = Path(str(source_path or '').strip()) if str(source_path or '').strip() else None
    old_rel = str(record.get('reference_image_rel') or '').strip()
    if clear_existing and old_rel:
        (get_library_root() / old_rel).unlink(missing_ok=True)
        record['reference_image_rel'] = ''
        record['reference_image_name'] = ''
    if not src_path or not src_path.exists() or not src_path.is_file():
        return record
    image_dir = _bundle_image_dir()
    suffix = src_path.suffix.lower() or '.png'
    dst = image_dir / f"{record['id']}{suffix}"
    try:
        if src_path.resolve() != dst.resolve():
            shutil.copy2(src_path, dst)
    except Exception:
        shutil.copy2(src_path, dst)
    if old_rel and old_rel != str(dst.relative_to(get_library_root())).replace('\\', '/'):
        (get_library_root() / old_rel).unlink(missing_ok=True)
    record['reference_image_rel'] = str(dst.relative_to(get_library_root())).replace('\\', '/')
    record['reference_image_name'] = src_path.name
    record['reference_updated_at'] = _now_iso()
    return record


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
    reference_image_path: str = '',
) -> Dict[str, Any]:
    now = _now_iso()
    record = {
        'schema_version': 1,
        'id': _new_id('bnd'),
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
        'metadata_snapshot': _snapshot_metadata_record(metadata_record_id) if metadata_record_id else None,
        'reference_image_rel': '',
        'reference_image_name': '',
        'created_at': now,
        'updated_at': now,
        'source': 'neo_library_bundle',
    }
    record = _attach_reference_image(record, reference_image_path)
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
    reference_image_path: str = '',
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
    existing = _attach_reference_image(existing, reference_image_path, clear_existing=bool(clear_reference_image))
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
            return _write_bundle_record(clean)
    return dup
