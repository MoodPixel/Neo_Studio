from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .caption_contract import normalize_caption_mode, normalize_component_type, normalize_crop_meta, normalize_detail_level
from .library_common import new_id, normalize_ext_list, record_sort_key, safe_name, sha256_file
from .library_settings_store import get_library_root, set_last_used_category, update_categories_file
from .library_storage import delete_temp_upload, iter_records, make_thumb, temp_path_from_id
from .storage_io import atomic_write_json



def save_caption(
    name: str,
    category: str,
    caption: str,
    temp_image_id: str,
    model: str,
    notes: str = '',
    raw_caption: str = '',
    preset_name: str = '',
    prompt_style: str = '',
    finish_reason: str = '',
    settings: Dict[str, Any] | None = None,
    component_type: str = '',
    caption_mode: str = 'full_image',
    crop_meta: Dict[str, Any] | None = None,
    detail_level: str = 'detailed',
) -> Dict[str, Any]:
    root = get_library_root()
    category = (category or '').strip() or 'uncategorized'
    src = temp_path_from_id(temp_image_id)
    if not src.exists():
        raise FileNotFoundError('Uploaded image is no longer available. Please caption it again.')
    now = datetime.now().isoformat(timespec='seconds')
    entry_id = new_id('cap')
    ext = src.suffix.lower() or '.png'
    image_rel = f'images/{entry_id}{ext}'
    thumb_rel = f'thumbs/{entry_id}.webp'
    image_dst = root / image_rel
    thumb_dst = root / thumb_rel
    shutil.copy2(src, image_dst)
    make_thumb(image_dst, thumb_dst)
    record = {
        'schema_version': 4,
        'id': entry_id,
        'kind': 'caption',
        'name': safe_name(name),
        'category': category,
        'image_path': image_rel.replace('\\', '/'),
        'thumb_path': thumb_rel.replace('\\', '/'),
        'caption': (caption or '').strip(),
        'raw_caption': (raw_caption or caption or '').strip(),
        'model': (model or '').strip(),
        'created_at': now,
        'updated_at': now,
        'tags': [t.strip() for t in (caption or '').split(',') if t.strip()][:40],
        'notes': (notes or '').strip(),
        'hash': sha256_file(image_dst),
        'source': 'neo_studio',
        'preset_name': (preset_name or '').strip(),
        'prompt_style': (prompt_style or '').strip(),
        'finish_reason': (finish_reason or '').strip(),
        'settings': settings or {},
        'component_type': normalize_component_type(component_type),
        'caption_mode': normalize_caption_mode(caption_mode),
        'detail_level': normalize_detail_level(detail_level),
        'crop_meta': normalize_crop_meta(crop_meta),
    }
    fp = root / 'captions' / f'{entry_id}.json'
    atomic_write_json(fp, record)
    update_categories_file(category)
    set_last_used_category('caption', category)
    delete_temp_upload(temp_image_id)
    return record


def save_caption_from_path(
    name: str,
    category: str,
    caption: str,
    image_path: str,
    model: str,
    notes: str = '',
    raw_caption: str = '',
    skip_duplicates: bool = False,
    prompt_style: str = '',
    finish_reason: str = '',
    settings: Dict[str, Any] | None = None,
    component_type: str = '',
    caption_mode: str = 'full_image',
    crop_meta: Dict[str, Any] | None = None,
    detail_level: str = 'detailed',
) -> Dict[str, Any] | None:
    root = get_library_root()
    category = (category or '').strip() or 'uncategorized'
    src = _normalize_fs_path(image_path)
    if not src.exists():
        raise FileNotFoundError(f'Image not found: {image_path}')
    src_hash = sha256_file(src)
    if skip_duplicates:
        for rec in iter_records('caption'):
            if str(rec.get('hash') or '') == src_hash:
                return None
    now = datetime.now().isoformat(timespec='seconds')
    entry_id = new_id('cap')
    ext = src.suffix.lower() or '.png'
    image_rel = f'images/{entry_id}{ext}'
    thumb_rel = f'thumbs/{entry_id}.webp'
    image_dst = root / image_rel
    thumb_dst = root / thumb_rel
    shutil.copy2(src, image_dst)
    make_thumb(image_dst, thumb_dst)
    record = {
        'schema_version': 4,
        'id': entry_id,
        'kind': 'caption',
        'name': safe_name(name),
        'category': category,
        'image_path': image_rel.replace('\\', '/'),
        'thumb_path': thumb_rel.replace('\\', '/'),
        'caption': (caption or '').strip(),
        'raw_caption': (raw_caption or caption or '').strip(),
        'model': (model or '').strip(),
        'created_at': now,
        'updated_at': now,
        'tags': [t.strip() for t in (caption or '').split(',') if t.strip()][:40],
        'notes': (notes or '').strip(),
        'hash': src_hash,
        'source': 'neo_studio',
        'prompt_style': (prompt_style or '').strip(),
        'finish_reason': (finish_reason or '').strip(),
        'settings': settings or {},
        'component_type': normalize_component_type(component_type),
        'caption_mode': normalize_caption_mode(caption_mode),
        'detail_level': normalize_detail_level(detail_level),
        'crop_meta': normalize_crop_meta(crop_meta),
    }
    fp = root / 'captions' / f'{entry_id}.json'
    atomic_write_json(fp, record)
    update_categories_file(category)
    set_last_used_category('caption', category)
    return record


def dataset_txt_output_path(image_path: str | Path, input_root: str | Path, output_folder: str = '') -> Path:
    img = _normalize_fs_path(image_path)
    out_root_raw = (output_folder or '').strip()
    if not out_root_raw:
        return img.with_suffix('.txt')

    src_root = _normalize_fs_path(input_root)
    out_root = _normalize_fs_path(out_root_raw)
    out_root.mkdir(parents=True, exist_ok=True)

    try:
        rel = img.relative_to(src_root)
        target = (out_root / rel).with_suffix('.txt')
    except Exception:
        target = out_root / f'{img.stem}.txt'

    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def image_files_in_folder(folder_path: str, recursive: bool = False, include_exts: Iterable[str] | None = None) -> List[Path]:
    root = _normalize_fs_path(folder_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError('Input folder not found.')
    allowed = normalize_ext_list(include_exts)
    iterator = root.rglob('*') if recursive else root.iterdir()
    files = [p for p in sorted(iterator) if p.is_file() and p.suffix.lower() in allowed]
    return files


def caption_entries(
    query: str = '',
    category: str = '',
    model: str = '',
    prompt_style: str = '',
    date_from: str = '',
    date_to: str = '',
    limit: int = 200,
    component_type: str = '',
    detail_level: str = '',
    component_only: bool = False,
    sort: str = 'newest',
    page: int = 1,
    page_size: int | None = None,
    return_total: bool = False,
) -> List[Dict[str, Any]] | tuple[List[Dict[str, Any]], int]:
    query_lc = (query or '').strip().lower()
    category = (category or '').strip()
    model_lc = (model or '').strip().lower()
    style_lc = (prompt_style or '').strip().lower()
    component_type = normalize_component_type(component_type)
    detail_level = normalize_detail_level(detail_level) if detail_level else ''
    sort_mode = (sort or 'newest').strip().lower()
    if sort_mode not in {'newest', 'oldest', 'az'}:
        sort_mode = 'newest'
    current_page = max(1, int(page or 1))
    effective_page_size = max(1, int(page_size or limit or 200))
    results: List[Dict[str, Any]] = []
    for rec in sorted(iter_records('caption'), key=record_sort_key, reverse=True):
        rec_category = str(rec.get('category') or 'uncategorized').strip() or 'uncategorized'
        rec_model = str(rec.get('model') or '').strip()
        rec_style = str(rec.get('prompt_style') or '').strip()
        rec_component = normalize_component_type(str(rec.get('component_type') or ''))
        rec_mode = normalize_caption_mode(str(rec.get('caption_mode') or 'full_image'))
        rec_detail = normalize_detail_level(str(rec.get('detail_level') or 'detailed'))
        updated_at = str(rec.get('updated_at') or rec.get('created_at') or '')
        if category and rec_category != category:
            continue
        if model_lc and model_lc not in rec_model.lower():
            continue
        if style_lc and style_lc not in rec_style.lower():
            continue
        if component_type and rec_component != component_type:
            continue
        if detail_level and rec_detail != detail_level:
            continue
        if component_only and not rec_component:
            continue
        if date_from and updated_at[:10] < date_from[:10]:
            continue
        if date_to and updated_at[:10] > date_to[:10]:
            continue
        haystack = ' '.join([
            str(rec.get('name') or ''),
            rec_category,
            rec_model,
            rec_style,
            str(rec.get('caption') or ''),
            str(rec.get('notes') or ''),
            rec_component,
            rec_mode,
        ]).lower()
        if query_lc and query_lc not in haystack:
            continue
        results.append({
            'id': str(rec.get('id') or ''),
            'name': str(rec.get('name') or '').strip() or '(untitled)',
            'label': str(rec.get('name') or '').strip() or '(untitled)',
            'category': rec_category,
            'model': rec_model,
            'prompt_style': rec_style,
            'created_at': str(rec.get('created_at') or ''),
            'updated_at': updated_at,
            'caption_preview': str(rec.get('caption') or '')[:180],
            'caption': str(rec.get('caption') or ''),
            'notes': str(rec.get('notes') or ''),
            'component_type': rec_component,
            'caption_mode': rec_mode,
            'detail_level': rec_detail,
            'crop_meta': normalize_crop_meta(rec.get('crop_meta')),
        })

    if sort_mode == 'az':
        results.sort(key=lambda item: (
            str(item.get('name') or '').lower(),
            str(item.get('updated_at') or item.get('created_at') or ''),
        ))
    else:
        results.sort(
            key=lambda item: (
                str(item.get('updated_at') or item.get('created_at') or ''),
                str(item.get('name') or '').lower(),
            ),
            reverse=(sort_mode == 'newest'),
        )

    total = len(results)
    if page_size is not None:
        total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
        current_page = min(max(1, current_page), total_pages)
        start = (current_page - 1) * effective_page_size
        paged = results[start:start + effective_page_size]
    else:
        paged = results[:max(1, int(limit or 200))]

    if return_total:
        return paged, total
    return paged


def get_caption_record(caption_id: str = '', name: str = '', category: str = '') -> Dict[str, Any] | None:
    target_id = (caption_id or '').strip()
    target_name = (name or '').strip().lower()
    category = (category or '').strip()
    for rec in sorted(iter_records('caption'), key=record_sort_key, reverse=True):
        rec_category = str(rec.get('category') or 'uncategorized').strip() or 'uncategorized'
        if target_id and str(rec.get('id') or '').strip() == target_id:
            return rec
        if category and rec_category != category:
            continue
        if target_name and str(rec.get('name') or '').strip().lower() == target_name:
            return rec
    return None


def update_caption_record(
    caption_id: str = '',
    name: str = '',
    category: str = '',
    caption: str = '',
    notes: str = '',
    model: str = '',
    prompt_style: str = '',
    component_type: str = '',
    detail_level: str = '',
) -> Dict[str, Any]:
    rec = get_caption_record(caption_id=caption_id, name=name, category=category)
    if not rec:
        raise FileNotFoundError('Caption not found.')
    rec['name'] = safe_name(name or rec.get('name') or 'untitled')
    rec['category'] = (category or rec.get('category') or 'uncategorized').strip() or 'uncategorized'
    rec['caption'] = (caption or '').strip()
    rec['raw_caption'] = str(rec.get('raw_caption') or rec['caption']).strip() or rec['caption']
    rec['notes'] = (notes or '').strip()
    rec['model'] = (model or rec.get('model') or '').strip()
    rec['prompt_style'] = (prompt_style or rec.get('prompt_style') or '').strip()
    rec['component_type'] = normalize_component_type(component_type or rec.get('component_type') or '')
    rec['detail_level'] = normalize_detail_level(detail_level or rec.get('detail_level') or 'detailed')
    rec['updated_at'] = datetime.now().isoformat(timespec='seconds')
    rec['tags'] = [t.strip() for t in rec['caption'].split(',') if t.strip()][:40]
    fp = Path(str(rec.get('_record_path') or ''))
    clean = {k: v for k, v in rec.items() if not str(k).startswith('_')}
    atomic_write_json(fp, clean)
    update_categories_file(rec['category'])
    return clean


def delete_caption_record(caption_id: str = '', name: str = '', category: str = '') -> bool:
    rec = get_caption_record(caption_id=caption_id, name=name, category=category)
    if not rec:
        return False
    fp = Path(str(rec.get('_record_path') or ''))
    root = get_library_root()
    image_path = root / str(rec.get('image_path') or '')
    thumb_path = root / str(rec.get('thumb_path') or '')
    try:
        fp.unlink(missing_ok=True)
    except Exception:
        pass
    image_path.unlink(missing_ok=True)
    thumb_path.unlink(missing_ok=True)
    return True
