from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .characters import load_character_map, write_character_map
from .library_common import ensure_dir, new_id, safe_name
from .library_presets import (
    _load_settings,
    _normalize_caption_preset,
    _normalize_prompt_preset,
    _save_settings,
    export_presets_payload,
)
from .library_prompts import get_prompt_record, unique_prompt_name
from .library_storage import iter_records
from .library_captions import get_caption_record
from .library_settings_store import get_library_root, list_categories, update_categories_file
from .output_metadata import iter_output_metadata_records
from .prompt_bundles import iter_bundle_records
from .storage_io import atomic_write_json

EXPORT_SCHEMA_VERSION = 1
MANIFEST_NAME = 'neo_studio_library_manifest.json'


# ---------- generic helpers ----------

def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _clean_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: deepcopy(v) for k, v in record.items() if not str(k).startswith('_')}


def _normalize_mode(mode: str) -> str:
    mode = (mode or 'merge').strip().lower()
    return mode if mode in {'merge', 'overwrite', 'skip_duplicates'} else 'merge'


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_selected_categories(categories: Iterable[str] | None) -> List[str]:
    out = []
    seen = set()
    for raw in categories or []:
        item = str(raw or '').strip() or 'uncategorized'
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _ensure_unique_name(name: str, existing_names: Iterable[str], suffix: str = 'Imported') -> str:
    base = safe_name(name)
    used = {str(x or '').strip().lower() for x in existing_names if str(x or '').strip()}
    if base.lower() not in used:
        return base
    i = 2
    while True:
        candidate = f'{base} ({suffix} {i})'
        if candidate.lower() not in used:
            return candidate
        i += 1


def _candidate_exists(folder: Path, record_id: str) -> bool:
    return bool(record_id and (folder / f'{record_id}.json').exists())


def _assign_record_id(folder: Path, record: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    item = deepcopy(record)
    rid = str(item.get('id') or '').strip()
    if not rid or _candidate_exists(folder, rid):
        item['id'] = new_id(prefix)
    return item


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _safe_asset_rel(rel_path: str) -> str:
    rel = str(rel_path or '').replace('\\', '/').strip().lstrip('/')
    rel = '/'.join([part for part in rel.split('/') if part not in ('', '.', '..')])
    return rel


def _zip_asset_name(rel_path: str) -> str:
    return f'assets/{_safe_asset_rel(rel_path)}'


# ---------- export ----------

def _filter_category(record: Dict[str, Any], selected_categories: List[str]) -> bool:
    if not selected_categories:
        return True
    category = str(record.get('category') or 'uncategorized').strip() or 'uncategorized'
    return category in selected_categories


def _export_prompts(selected_categories: List[str]) -> List[Dict[str, Any]]:
    rows = []
    for rec in iter_records('prompt'):
        if not _filter_category(rec, selected_categories):
            continue
        rows.append(_clean_record(rec))
    return rows


def _export_captions(selected_categories: List[str]) -> List[Dict[str, Any]]:
    rows = []
    for rec in iter_records('caption'):
        if not _filter_category(rec, selected_categories):
            continue
        rows.append(_clean_record(rec))
    return rows


def _export_characters() -> Dict[str, str]:
    return load_character_map() or {}


def _export_presets() -> Dict[str, Any]:
    return export_presets_payload()


def _export_metadata() -> List[Dict[str, Any]]:
    return [_clean_record(rec) for rec in iter_output_metadata_records()]


def _export_bundles() -> List[Dict[str, Any]]:
    return [_clean_record(rec) for rec in iter_bundle_records()]


def _manifest_payload(
    *,
    include_prompts: bool,
    include_captions: bool,
    include_characters: bool,
    include_presets: bool,
    include_categories: bool,
    include_metadata: bool,
    include_bundles: bool,
    selected_categories: List[str],
    full_snapshot: bool,
) -> Dict[str, Any]:
    return {
        'schema_version': EXPORT_SCHEMA_VERSION,
        'exported_at': _now_iso(),
        'app': 'neo_studio',
        'full_snapshot': bool(full_snapshot),
        'selected_categories': selected_categories,
        'sections': {
            'prompts': _export_prompts(selected_categories) if include_prompts else [],
            'captions': _export_captions(selected_categories) if include_captions else [],
            'characters': _export_characters() if include_characters else {},
            'presets': _export_presets() if include_presets else {'schema_version': 1, 'prompt_presets': {}, 'caption_presets': {}},
            'categories': list_categories() if include_categories else [],
            'metadata': _export_metadata() if include_metadata else [],
            'bundles': _export_bundles() if include_bundles else [],
        },
    }


def build_library_export_zip(
    *,
    include_prompts: bool = True,
    include_captions: bool = True,
    include_characters: bool = True,
    include_presets: bool = True,
    include_categories: bool = True,
    include_metadata: bool = True,
    include_bundles: bool = True,
    selected_categories: Iterable[str] | None = None,
    full_snapshot: bool = False,
) -> Tuple[bytes, str, Dict[str, Any]]:
    selected = _normalize_selected_categories(selected_categories)
    if full_snapshot:
        include_prompts = include_captions = include_characters = include_presets = include_categories = include_metadata = include_bundles = True
        selected = []

    manifest = _manifest_payload(
        include_prompts=include_prompts,
        include_captions=include_captions,
        include_characters=include_characters,
        include_presets=include_presets,
        include_categories=include_categories,
        include_metadata=include_metadata,
        include_bundles=include_bundles,
        selected_categories=selected,
        full_snapshot=full_snapshot,
    )

    root = get_library_root()
    summary = {
        'prompts': len(manifest['sections']['prompts']),
        'captions': len(manifest['sections']['captions']),
        'characters': len(manifest['sections']['characters']),
        'prompt_presets': len((manifest['sections']['presets'] or {}).get('prompt_presets') or {}),
        'caption_presets': len((manifest['sections']['presets'] or {}).get('caption_presets') or {}),
        'categories': len(manifest['sections']['categories']),
        'metadata': len(manifest['sections']['metadata']),
        'bundles': len(manifest['sections']['bundles']),
    }

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
        for rec in manifest['sections']['captions']:
            for key in ('image_path', 'thumb_path'):
                rel = _safe_asset_rel(rec.get(key) or '')
                if not rel:
                    continue
                src = root / rel
                if src.exists() and src.is_file():
                    zf.write(src, _zip_asset_name(rel))
        for rec in manifest['sections']['bundles']:
            rel = _safe_asset_rel(rec.get('reference_image_rel') or '')
            if not rel:
                continue
            src = root / rel
            if src.exists() and src.is_file():
                zf.write(src, _zip_asset_name(rel))

    filename = f"neo_studio_library_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return mem.getvalue(), filename, summary


# ---------- import helpers ----------

def _load_archive_payload(content: bytes) -> Tuple[Dict[str, Any], Dict[str, bytes]]:
    assets: Dict[str, bytes] = {}
    if content[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
            try:
                manifest = json.loads(zf.read(MANIFEST_NAME).decode('utf-8'))
            except KeyError:
                raise ValueError('Import archive is missing neo_studio_library_manifest.json')
            for name in zf.namelist():
                if name.startswith('assets/') and not name.endswith('/'):
                    assets[name] = zf.read(name)
            return manifest, assets
    payload = json.loads(content.decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Import file must contain a JSON object or library zip.')
    return payload, assets


def _existing_prompt_names(category: str) -> List[str]:
    return [str(rec.get('name') or '').strip() for rec in iter_records('prompt') if str(rec.get('category') or 'uncategorized').strip() == category]


def _existing_caption_names(category: str) -> List[str]:
    return [str(rec.get('name') or '').strip() for rec in iter_records('caption') if str(rec.get('category') or 'uncategorized').strip() == category]


def _existing_bundle_names() -> List[str]:
    return [str(rec.get('name') or '').strip() for rec in iter_bundle_records()]


def _prompt_duplicate(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return (
        str(existing.get('prompt') or '').strip() == str(incoming.get('prompt') or '').strip()
        and str(existing.get('model') or '').strip() == str(incoming.get('model') or '').strip()
        and str(existing.get('notes') or '').strip() == str(incoming.get('notes') or '').strip()
    )


def _caption_duplicate(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return (
        str(existing.get('hash') or '').strip() and str(existing.get('hash') or '').strip() == str(incoming.get('hash') or '').strip()
    ) or (
        str(existing.get('caption') or '').strip() == str(incoming.get('caption') or '').strip()
        and str(existing.get('name') or '').strip().lower() == str(incoming.get('name') or '').strip().lower()
        and str(existing.get('category') or 'uncategorized').strip() == str(incoming.get('category') or 'uncategorized').strip()
    )


def _character_duplicate(existing: str, incoming: str) -> bool:
    return str(existing or '').strip() == str(incoming or '').strip()


def _preset_duplicate(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return json.dumps(existing, sort_keys=True, ensure_ascii=False) == json.dumps(incoming, sort_keys=True, ensure_ascii=False)


def _metadata_duplicate(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return (
        str(existing.get('name') or '').strip().lower() == str(incoming.get('name') or '').strip().lower()
        and json.dumps(existing.get('data') or {}, sort_keys=True, ensure_ascii=False) == json.dumps(incoming.get('data') or {}, sort_keys=True, ensure_ascii=False)
    )


def _bundle_duplicate(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return (
        str(existing.get('name') or '').strip().lower() == str(incoming.get('name') or '').strip().lower()
        and str(existing.get('positive_prompt') or '').strip() == str(incoming.get('positive_prompt') or '').strip()
        and str(existing.get('negative_prompt') or '').strip() == str(incoming.get('negative_prompt') or '').strip()
    )


def _save_asset_from_archive(root: Path, rel_path: str, assets: Dict[str, bytes]) -> str:
    rel = _safe_asset_rel(rel_path)
    if not rel:
        return ''
    asset_key = _zip_asset_name(rel)
    payload = assets.get(asset_key)
    if payload is None:
        return rel
    dst = root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(payload)
    return rel.replace('\\', '/')


def _import_prompt_records(records: List[Dict[str, Any]], mode: str, summary: Dict[str, Any]) -> None:
    root = get_library_root()
    folder = root / 'prompts'
    ensure_dir(folder)
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        incoming = _clean_record(raw)
        category = str(incoming.get('category') or 'uncategorized').strip() or 'uncategorized'
        name = safe_name(incoming.get('name') or 'untitled')
        existing = get_prompt_record(category=category, name=name)
        if existing:
            if mode == 'overwrite':
                item = deepcopy(incoming)
                item['id'] = str(existing.get('id') or '')
                item['name'] = name
                item['category'] = category
                item['schema_version'] = max(2, int(item.get('schema_version') or 2))
                _write_json(Path(existing.get('_record_path') or (folder / f"{item['id']}.json")), item)
                summary['prompts']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'prompt', 'name': name, 'category': category, 'action': 'overwritten'})
            elif mode == 'skip_duplicates' and _prompt_duplicate(existing, incoming):
                summary['prompts']['skipped'] += 1
                summary['conflicts'].append({'kind': 'prompt', 'name': name, 'category': category, 'action': 'skipped_duplicate'})
            else:
                new_name = unique_prompt_name(category, f'{name} (Imported)')
                item = _assign_record_id(folder, incoming, 'prm')
                item['name'] = new_name
                item['category'] = category
                _write_json(folder / f"{item['id']}.json", item)
                summary['prompts']['imported'] += 1
                summary['conflicts'].append({'kind': 'prompt', 'name': name, 'category': category, 'action': 'renamed', 'new_name': new_name})
        else:
            item = _assign_record_id(folder, incoming, 'prm')
            item['name'] = name
            item['category'] = category
            _write_json(folder / f"{item['id']}.json", item)
            summary['prompts']['imported'] += 1
        update_categories_file(category)


def _import_caption_records(records: List[Dict[str, Any]], assets: Dict[str, bytes], mode: str, summary: Dict[str, Any]) -> None:
    root = get_library_root()
    folder = root / 'captions'
    ensure_dir(folder)
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        incoming = _clean_record(raw)
        category = str(incoming.get('category') or 'uncategorized').strip() or 'uncategorized'
        name = safe_name(incoming.get('name') or 'untitled')
        existing = get_caption_record(name=name, category=category)
        if existing:
            if mode == 'overwrite':
                old_image = root / str(existing.get('image_path') or '')
                old_thumb = root / str(existing.get('thumb_path') or '')
                old_image.unlink(missing_ok=True)
                old_thumb.unlink(missing_ok=True)
                item = deepcopy(incoming)
                item['id'] = str(existing.get('id') or '')
                # keep predictable local asset paths by using existing id
                ext = Path(str(item.get('image_path') or '')).suffix or '.png'
                item['image_path'] = f'images/{item["id"]}{ext}'
                item['thumb_path'] = f'thumbs/{item["id"]}.webp'
                _save_asset_from_archive(root, item['image_path'], assets)
                _save_asset_from_archive(root, item['thumb_path'], assets)
                _write_json(Path(existing.get('_record_path') or (folder / f"{item['id']}.json")), item)
                summary['captions']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'caption', 'name': name, 'category': category, 'action': 'overwritten'})
            elif mode == 'skip_duplicates' and _caption_duplicate(existing, incoming):
                summary['captions']['skipped'] += 1
                summary['conflicts'].append({'kind': 'caption', 'name': name, 'category': category, 'action': 'skipped_duplicate'})
            else:
                new_name = _ensure_unique_name(f'{name} (Imported)', _existing_caption_names(category))
                item = _assign_record_id(folder, incoming, 'cap')
                item['name'] = new_name
                ext = Path(str(item.get('image_path') or '')).suffix or '.png'
                item['image_path'] = f'images/{item["id"]}{ext}'
                item['thumb_path'] = f'thumbs/{item["id"]}.webp'
                _save_asset_from_archive(root, item['image_path'], assets)
                _save_asset_from_archive(root, item['thumb_path'], assets)
                _write_json(folder / f"{item['id']}.json", item)
                summary['captions']['imported'] += 1
                summary['conflicts'].append({'kind': 'caption', 'name': name, 'category': category, 'action': 'renamed', 'new_name': new_name})
        else:
            item = _assign_record_id(folder, incoming, 'cap')
            item['name'] = name
            ext = Path(str(item.get('image_path') or '')).suffix or '.png'
            item['image_path'] = f'images/{item["id"]}{ext}'
            item['thumb_path'] = f'thumbs/{item["id"]}.webp'
            _save_asset_from_archive(root, item['image_path'], assets)
            _save_asset_from_archive(root, item['thumb_path'], assets)
            _write_json(folder / f"{item['id']}.json", item)
            summary['captions']['imported'] += 1
        update_categories_file(category)


def _import_characters(mapping: Dict[str, Any], mode: str, summary: Dict[str, Any]) -> None:
    existing = load_character_map() or {}
    changed = False
    for raw_name, raw_content in (mapping or {}).items():
        name = str(raw_name or '').strip()
        content = str(raw_content or '').strip()
        if not name or not content:
            continue
        if name in existing:
            if mode == 'overwrite':
                existing[name] = content
                summary['characters']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'character', 'name': name, 'action': 'overwritten'})
                changed = True
            elif mode == 'skip_duplicates' and _character_duplicate(existing.get(name), content):
                summary['characters']['skipped'] += 1
                summary['conflicts'].append({'kind': 'character', 'name': name, 'action': 'skipped_duplicate'})
            else:
                new_name = _ensure_unique_name(f'{name} (Imported)', existing.keys())
                existing[new_name] = content
                summary['characters']['imported'] += 1
                summary['conflicts'].append({'kind': 'character', 'name': name, 'action': 'renamed', 'new_name': new_name})
                changed = True
        else:
            existing[name] = content
            summary['characters']['imported'] += 1
            changed = True
    if changed:
        write_character_map(existing)


def _import_presets(payload: Dict[str, Any], mode: str, summary: Dict[str, Any]) -> None:
    data = _load_settings()
    prompt_custom = data.get('prompt_presets') if isinstance(data.get('prompt_presets'), dict) else {}
    caption_custom = data.get('caption_presets') if isinstance(data.get('caption_presets'), dict) else {}

    changed = False
    incoming_prompt = payload.get('prompt_presets') if isinstance(payload.get('prompt_presets'), dict) else {}
    incoming_caption = payload.get('caption_presets') if isinstance(payload.get('caption_presets'), dict) else {}

    for name, preset in incoming_prompt.items():
        clean_name = str(name or '').strip()
        if not clean_name or not isinstance(preset, dict):
            continue
        norm = _normalize_prompt_preset(preset, kind='custom')
        if clean_name in prompt_custom:
            if mode == 'overwrite':
                prompt_custom[clean_name] = norm
                summary['prompt_presets']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'prompt_preset', 'name': clean_name, 'action': 'overwritten'})
                changed = True
            elif mode == 'skip_duplicates' and _preset_duplicate(prompt_custom.get(clean_name) or {}, norm):
                summary['prompt_presets']['skipped'] += 1
                summary['conflicts'].append({'kind': 'prompt_preset', 'name': clean_name, 'action': 'skipped_duplicate'})
            else:
                new_name = _ensure_unique_name(f'{clean_name} (Imported)', prompt_custom.keys())
                prompt_custom[new_name] = norm
                summary['prompt_presets']['imported'] += 1
                summary['conflicts'].append({'kind': 'prompt_preset', 'name': clean_name, 'action': 'renamed', 'new_name': new_name})
                changed = True
        else:
            prompt_custom[clean_name] = norm
            summary['prompt_presets']['imported'] += 1
            changed = True

    for name, preset in incoming_caption.items():
        clean_name = str(name or '').strip()
        if not clean_name or not isinstance(preset, dict):
            continue
        norm = _normalize_caption_preset(preset, kind='custom')
        if clean_name in caption_custom:
            if mode == 'overwrite':
                caption_custom[clean_name] = norm
                summary['caption_presets']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'caption_preset', 'name': clean_name, 'action': 'overwritten'})
                changed = True
            elif mode == 'skip_duplicates' and _preset_duplicate(caption_custom.get(clean_name) or {}, norm):
                summary['caption_presets']['skipped'] += 1
                summary['conflicts'].append({'kind': 'caption_preset', 'name': clean_name, 'action': 'skipped_duplicate'})
            else:
                new_name = _ensure_unique_name(f'{clean_name} (Imported)', caption_custom.keys())
                caption_custom[new_name] = norm
                summary['caption_presets']['imported'] += 1
                summary['conflicts'].append({'kind': 'caption_preset', 'name': clean_name, 'action': 'renamed', 'new_name': new_name})
                changed = True
        else:
            caption_custom[clean_name] = norm
            summary['caption_presets']['imported'] += 1
            changed = True

    if changed:
        data['prompt_presets'] = prompt_custom
        data['caption_presets'] = caption_custom
        _save_settings(data)


def _import_categories(rows: List[str], summary: Dict[str, Any]) -> None:
    for item in rows or []:
        category = str(item or '').strip() or 'uncategorized'
        update_categories_file(category)
    summary['categories']['imported'] += len([x for x in rows or [] if str(x or '').strip()])


def _import_metadata(records: List[Dict[str, Any]], mode: str, summary: Dict[str, Any], metadata_id_map: Dict[str, str]) -> None:
    root = get_library_root()
    folder = root / 'output_metadata'
    ensure_dir(folder)
    existing_rows = iter_output_metadata_records()
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        incoming = _clean_record(raw)
        old_id = str(incoming.get('id') or '').strip()
        name = safe_name(incoming.get('name') or 'metadata')
        existing = next((r for r in existing_rows if str(r.get('name') or '').strip().lower() == name.lower()), None)
        if existing:
            if mode == 'overwrite':
                item = deepcopy(incoming)
                item['id'] = str(existing.get('id') or '')
                _write_json(Path(existing.get('_record_path') or (folder / f"{item['id']}.json")), item)
                summary['metadata']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'metadata', 'name': name, 'action': 'overwritten'})
                metadata_id_map[old_id] = item['id']
            elif mode == 'skip_duplicates' and _metadata_duplicate(existing, incoming):
                summary['metadata']['skipped'] += 1
                summary['conflicts'].append({'kind': 'metadata', 'name': name, 'action': 'skipped_duplicate'})
                metadata_id_map[old_id] = str(existing.get('id') or old_id)
            else:
                new_name = _ensure_unique_name(f'{name} (Imported)', [r.get('name') for r in existing_rows])
                item = _assign_record_id(folder, incoming, 'meta')
                item['name'] = new_name
                _write_json(folder / f"{item['id']}.json", item)
                existing_rows.append(item)
                summary['metadata']['imported'] += 1
                summary['conflicts'].append({'kind': 'metadata', 'name': name, 'action': 'renamed', 'new_name': new_name})
                metadata_id_map[old_id] = item['id']
        else:
            item = _assign_record_id(folder, incoming, 'meta')
            item['name'] = name
            _write_json(folder / f"{item['id']}.json", item)
            existing_rows.append(item)
            summary['metadata']['imported'] += 1
            metadata_id_map[old_id] = item['id']


def _import_bundles(records: List[Dict[str, Any]], assets: Dict[str, bytes], mode: str, summary: Dict[str, Any], metadata_id_map: Dict[str, str]) -> None:
    root = get_library_root()
    folder = root / 'bundles'
    ensure_dir(folder)
    existing_rows = iter_bundle_records()
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        incoming = _clean_record(raw)
        name = safe_name(incoming.get('name') or 'bundle')
        incoming_metadata_id = str(incoming.get('metadata_record_id') or '').strip()
        if incoming_metadata_id and incoming_metadata_id in metadata_id_map:
            incoming['metadata_record_id'] = metadata_id_map[incoming_metadata_id]
            snap = incoming.get('metadata_snapshot') if isinstance(incoming.get('metadata_snapshot'), dict) else None
            if snap:
                snap['id'] = metadata_id_map[incoming_metadata_id]
        existing = next((r for r in existing_rows if str(r.get('name') or '').strip().lower() == name.lower()), None)
        if existing:
            if mode == 'overwrite':
                old_rel = _safe_asset_rel(existing.get('reference_image_rel') or '')
                if old_rel:
                    (root / old_rel).unlink(missing_ok=True)
                item = deepcopy(incoming)
                item['id'] = str(existing.get('id') or '')
                if item.get('reference_image_rel'):
                    ext = Path(str(item.get('reference_image_rel') or '')).suffix or '.png'
                    item['reference_image_rel'] = f'bundle_images/{item["id"]}{ext}'
                    _save_asset_from_archive(root, item['reference_image_rel'], assets)
                _write_json(Path(existing.get('_record_path') or (folder / f"{item['id']}.json")), item)
                summary['bundles']['overwritten'] += 1
                summary['conflicts'].append({'kind': 'bundle', 'name': name, 'action': 'overwritten'})
            elif mode == 'skip_duplicates' and _bundle_duplicate(existing, incoming):
                summary['bundles']['skipped'] += 1
                summary['conflicts'].append({'kind': 'bundle', 'name': name, 'action': 'skipped_duplicate'})
            else:
                new_name = _ensure_unique_name(f'{name} (Imported)', _existing_bundle_names())
                item = _assign_record_id(folder, incoming, 'bnd')
                item['name'] = new_name
                if item.get('reference_image_rel'):
                    ext = Path(str(item.get('reference_image_rel') or '')).suffix or '.png'
                    item['reference_image_rel'] = f'bundle_images/{item["id"]}{ext}'
                    _save_asset_from_archive(root, item['reference_image_rel'], assets)
                _write_json(folder / f"{item['id']}.json", item)
                existing_rows.append(item)
                summary['bundles']['imported'] += 1
                summary['conflicts'].append({'kind': 'bundle', 'name': name, 'action': 'renamed', 'new_name': new_name})
        else:
            item = _assign_record_id(folder, incoming, 'bnd')
            item['name'] = name
            if item.get('reference_image_rel'):
                ext = Path(str(item.get('reference_image_rel') or '')).suffix or '.png'
                item['reference_image_rel'] = f'bundle_images/{item["id"]}{ext}'
                _save_asset_from_archive(root, item['reference_image_rel'], assets)
            _write_json(folder / f"{item['id']}.json", item)
            existing_rows.append(item)
            summary['bundles']['imported'] += 1


def import_library_archive(content: bytes, mode: str = 'merge') -> Dict[str, Any]:
    mode = _normalize_mode(mode)
    payload, assets = _load_archive_payload(content)
    if not isinstance(payload, dict):
        raise ValueError('Import payload is invalid.')
    sections = payload.get('sections') if isinstance(payload.get('sections'), dict) else payload
    summary = {
        'mode': mode,
        'schema_version': int(payload.get('schema_version') or 1),
        'imported_at': _now_iso(),
        'prompts': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'captions': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'characters': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'prompt_presets': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'caption_presets': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'categories': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'metadata': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'bundles': {'imported': 0, 'overwritten': 0, 'skipped': 0},
        'conflicts': [],
    }
    metadata_id_map: Dict[str, str] = {}
    _import_categories(sections.get('categories') if isinstance(sections.get('categories'), list) else [], summary)
    _import_characters(sections.get('characters') if isinstance(sections.get('characters'), dict) else {}, mode, summary)
    presets = sections.get('presets') if isinstance(sections.get('presets'), dict) else {}
    _import_presets(presets, mode, summary)
    _import_prompt_records(sections.get('prompts') if isinstance(sections.get('prompts'), list) else [], mode, summary)
    _import_metadata(sections.get('metadata') if isinstance(sections.get('metadata'), list) else [], mode, summary, metadata_id_map)
    _import_caption_records(sections.get('captions') if isinstance(sections.get('captions'), list) else [], assets, mode, summary)
    _import_bundles(sections.get('bundles') if isinstance(sections.get('bundles'), list) else [], assets, mode, summary, metadata_id_map)
    summary['conflicts_preview'] = summary['conflicts'][:25]
    summary['totals'] = {
        key: sum(value.values()) for key, value in summary.items() if isinstance(value, dict) and set(value.keys()) >= {'imported', 'overwritten', 'skipped'}
    }
    return summary
