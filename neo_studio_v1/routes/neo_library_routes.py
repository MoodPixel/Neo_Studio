from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
import mimetypes
from pathlib import Path
from typing import Any

from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import FileResponse, JSONResponse

_LIB_DIR = Path(__file__).resolve().parents[2] / 'neo_library_v1' / 'lib'
if str(_LIB_DIR) not in sys.path:
    sys.path.append(str(_LIB_DIR))

from neo_library_store import get_output_dirs, load_output_record, output_image_names, resolve_output_path  # type: ignore
from prompt_preset_store import PromptPresetStore  # type: ignore
from vault_store import VaultStore  # type: ignore

from ..utils.library_captions import get_caption_record
from ..utils.library_prompts import get_prompt_record, prompt_categories
from ..utils.library_settings_store import get_library_root
from ..utils.library_stats import stats
from ..utils.storage_compat import build_storage_compat_snapshot
from ..utils.library_storage import iter_records
from ..utils.storage_io import atomic_write_json, read_json_object
from ..utils.shared_data_paths import library_data_path
from .common import json_error, json_exception

router = APIRouter()


_LIBRARIES_DIR = Path(__file__).resolve().parents[2] / 'neo_library_v1' / 'libraries'
_NUM_ITEM = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_BULLET_ITEM = re.compile(r"^\s*-\s+(.*\S)\s*$")

_MAPGEN_SETTINGS_PATH = library_data_path('mapgen_settings.json', legacy_rel='mapgen_settings.json', default_json={})
_MAPGEN_SCRIPT = Path(__file__).resolve().parents[2] / 'neo_library_v1' / 'tools' / 'batch_hints.py'
_ASSETS_DIR = library_data_path('assets', legacy_rel='assets')
_LORA_PREVIEWS_DIR = library_data_path('lora_previews', legacy_rel='lora_previews')



_CC_EXPLICIT_TOKENS = {
    'penis', 'breast', 'vagina', 'nipple', 'nsfw', 'explicit', 'sex', 'cum', 'ejac', 'anal', 'oral', 'fetish', 'nude', 'naked', 'areola'
}


def _ps_norm_token(value: str) -> str:
    value = str(value or '').strip().lower()
    value = re.sub(r'[\s_\-]+', ' ', value)
    return re.sub(r'[^a-z0-9 ]+', '', value).strip()


def _cc_is_explicit(text: str) -> bool:
    t = _ps_norm_token(text).replace(' ', '_')
    return any(tok in t for tok in _CC_EXPLICIT_TOKENS)


def _cc_parse_file_meta(p: Path) -> dict[str, str]:
    stem = p.stem
    parts = [x.strip() for x in stem.split('__') if x.strip()]
    out = {
        'source_file': str(p),
        'filename': p.name,
        'stem': stem,
        'gender': '',
        'era': 'any',
        'rating': 'safe',
        'group': 'misc',
        'section': 'misc',
        'library': 'general',
        'category': stem,
    }
    if not parts:
        return out
    gender = (parts[0] or '').strip().lower()
    if gender not in ('male', 'female', 'unisex'):
        return out
    out['gender'] = gender
    if len(parts) >= 4:
        out['section'] = (parts[1] or 'misc').strip() or 'misc'
        out['library'] = (parts[2] or 'general').strip() or 'general'
        tail = '__'.join(parts[3:])
    elif len(parts) == 3:
        mid_tokens = [t for t in re.split(r'[_\s]+', parts[1]) if t]
        out['section'] = (mid_tokens[0] if mid_tokens else 'misc').strip() or 'misc'
        out['library'] = ('_'.join(mid_tokens[1:]) if len(mid_tokens) > 1 else 'general').strip() or 'general'
        tail = parts[2]
    else:
        return out
    out['group'] = out['section']
    tail_tokens = [t for t in re.split(r'[_\s]+', tail) if t]
    for tok in tail_tokens:
        tl = tok.lower()
        if tl in ('modern', 'fantasy', 'futuristic', 'any'):
            out['era'] = tl
        elif tl in ('safe', 'restricted'):
            out['rating'] = tl
    return out


def _cc_entries(gender: str, era: str, show_restricted: bool) -> list[dict[str, str]]:
    g = (gender or '').strip().lower()
    e = (era or 'any').strip().lower()
    entries: list[dict[str, str]] = []
    store = _vault_store()
    for p in sorted(store._lib_dir.glob('*.md')) if store._lib_dir.exists() else []:
        meta = _cc_parse_file_meta(p)
        if not meta.get('gender'):
            continue
        if _cc_is_explicit(meta.get('filename', '')) or _cc_is_explicit(meta.get('library', '')):
            continue
        mg = (meta.get('gender') or '').strip().lower()
        if g == 'male':
            if mg not in ('male', 'unisex'):
                continue
        elif g == 'female':
            if mg not in ('female', 'unisex'):
                continue
        elif g == 'unisex':
            if mg != 'unisex':
                continue
        me = (meta.get('era') or 'any').strip().lower()
        if e != 'any' and me not in ('any', e):
            continue
        if meta.get('rating') == 'restricted' and not show_restricted:
            continue
        entries.append(meta)
    entries.sort(key=lambda x: ((x.get('section') or ''), (x.get('library') or ''), (x.get('filename') or '')))
    return entries


def _cc_group_choices(entries: list[dict[str, str]]) -> list[str]:
    groups = []
    seen = set()
    for m in entries or []:
        g = m.get('section') or 'misc'
        if g in seen:
            continue
        seen.add(g)
        groups.append(g)
    return groups


def _cc_lib_choices(entries: list[dict[str, str]], group: str) -> list[str]:
    out = []
    seen = set()
    for m in entries or []:
        if _ps_norm_token(m.get('section') or 'misc') == _ps_norm_token(group or 'misc'):
            lib = (m.get('library') or 'general').strip()
            norm = _ps_norm_token(lib)
            norm_alt = norm[:-1] if norm.endswith('s') else norm + 's'
            key = f"{_ps_norm_token(m.get('section') or group)}__{norm}"
            if key in seen or f"{_ps_norm_token(m.get('section') or group)}__{norm_alt}" in seen:
                continue
            seen.add(key)
            out.append(lib)
    out.sort(key=_ps_norm_token)
    return out


def _cc_pack_item_value(rec: dict[str, Any]) -> str:
    payload = {
        'name': str(rec.get('name') or '').strip(),
        'desc': str(rec.get('desc') or '').strip(),
        'aliases': [str(a).strip() for a in (rec.get('aliases') or []) if str(a).strip()],
        'subcategory': str(rec.get('subcategory') or '').strip(),
    }
    return json.dumps(payload, ensure_ascii=False)


def _cc_item_choices(query: str, source_file: str, entries: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    if not source_file:
        return []
    qn = _ps_norm_token(query or '')
    safe: list[dict[str, Any]] = []
    seen = set()
    sources: list[str] = []
    sf = str(source_file)
    try:
        sec, lib = sf.split('__', 1) if ('__' in sf and not sf.lower().endswith('.md')) else (None, None)
    except ValueError:
        sec, lib = None, None
    store = _vault_store()
    if sec is not None and lib is not None:
        pool = entries or []
        if pool:
            for meta in pool:
                if _ps_norm_token(meta.get('section') or 'misc') == _ps_norm_token(sec) and _ps_norm_token(meta.get('library') or 'general') == _ps_norm_token(lib):
                    sources.append(str(meta.get('source_file') or ''))
        else:
            for p in sorted(store._lib_dir.glob('*.md')) if store._lib_dir.exists() else []:
                meta = _cc_parse_file_meta(p)
                if _ps_norm_token(meta.get('section') or 'misc') == _ps_norm_token(sec) and _ps_norm_token(meta.get('library') or 'general') == _ps_norm_token(lib):
                    sources.append(str(p))
    else:
        sources.append(sf)
    sources = list(dict.fromkeys([s for s in sources if s]))
    for src in sources:
        try:
            lines = Path(src).read_text(encoding='utf-8', errors='ignore').splitlines()
        except OSError:
            continue
        for line in lines:
            rec = store._parse_keyword_line(line)
            if not rec:
                continue
            nm = (rec.get('name') or '').strip()
            desc = (rec.get('desc') or '').strip()
            if not nm or _cc_is_explicit(nm):
                continue
            hay = _ps_norm_token(nm + ' ' + ' '.join(rec.get('aliases') or []) + ' ' + desc)
            if qn and qn not in hay:
                continue
            key = re.sub(r'[^a-z0-9]+', '', _ps_norm_token(nm))
            if key in seen:
                continue
            seen.add(key)
            label = nm
            if desc:
                snippet = desc if len(desc) <= 88 else (desc[:85].rstrip() + '…')
                label = f"{nm} — {snippet}"
            safe.append({
                'label': label,
                'value': _cc_pack_item_value(rec),
                'name': nm,
                'desc': desc,
                'aliases': rec.get('aliases') or [],
                'subcategory': rec.get('subcategory') or '',
            })
    safe.sort(key=lambda x: _ps_norm_token(x.get('label') or ''))
    return safe


def _shared_prompt_dir() -> Path:
    d = get_library_root() / 'prompts'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _preset_category_choices() -> list[str]:
    vals = set(prompt_categories() or [])
    try:
        vals.update(PromptPresetStore().list_categories() or [])
    except (OSError, TypeError, ValueError):
        pass
    vals.add('uncategorized')
    return sorted([v for v in vals if str(v or '').strip()], key=str.lower)


def _preset_meta_text(it: dict[str, Any]) -> str:
    if not it:
        return ''
    bits = []
    if it.get('favorite'):
        bits.append('⭐ favorite')
    if it.get('group'):
        bits.append(f"group: {it.get('group')}")
    if it.get('usage_count'):
        bits.append(f"used: {it.get('usage_count')}")
    if it.get('last_used'):
        bits.append(f"last used: {it.get('last_used')}")
    if it.get('updated'):
        bits.append(f"updated: {it.get('updated')}")
    return ' · '.join(bits)


def _sync_prompt_record(pid: str, title: str, pos: str, neg: str, category: str, notes: str):
    if not pid:
        return
    fp = _shared_prompt_dir() / f'forge_{pid}.json'
    now = datetime.now().isoformat(timespec='seconds')
    old = {}
    try:
        old = read_json_object(fp, {}) if fp.exists() else {}
    except Exception:
        old = {}
    rec = {
        'schema_version': 1,
        'id': f'forge_{pid}',
        'kind': 'prompt',
        'name': (title or 'Untitled').strip() or 'Untitled',
        'category': (category or '').strip() or 'uncategorized',
        'prompt': (pos or '').strip(),
        'raw_prompt': (pos or '').strip(),
        'negative_prompt': (neg or '').strip(),
        'notes': (notes or '').strip(),
        'model': '',
        'created_at': old.get('created_at') or now,
        'updated_at': now,
        'tags': [],
        'source': 'forge_prompt_composer',
    }
    atomic_write_json(fp, rec)


def _delete_synced_prompt_record(pid: str):
    if not pid:
        return
    (_shared_prompt_dir() / f'forge_{pid}.json').unlink(missing_ok=True)


def _synced_prompt_meta(pid: str) -> dict[str, Any]:
    if not pid:
        return {}
    fp = _shared_prompt_dir() / f'forge_{pid}.json'
    try:
        return read_json_object(fp, {}) if fp.exists() else {}
    except Exception:
        return {}


def _composer_preset_choices(query: str = '', category: str = 'all') -> list[dict[str, Any]]:
    ps = PromptPresetStore()
    rows = []
    for label, pid in ps.list_choices(query, category):
        rows.append({'label': label, 'value': pid})
    return rows


def _vault_store() -> VaultStore:
    return VaultStore()


def _split_csv_tokens(value: str) -> list[str]:
    items = []
    for part in str(value or '').split(','):
        part = str(part or '').strip()
        if part:
            items.append(part)
    return items


def _clean_lora_record(rec: dict):
    clean = {}
    for k, v in (rec or {}).items():
        if isinstance(v, Path):
            clean[k] = str(v)
        else:
            clean[k] = v
    preview_paths = []
    primary = str(clean.get('preview_image') or '').strip()
    if primary:
        preview_paths.append(primary)
    for path in (clean.get('preview_images') or []):
        p = str(path or '').strip()
        if p and p not in preview_paths:
            preview_paths.append(p)
    clean['preview_images'] = preview_paths
    clean['preview_url'] = f"/api/neo-library/lora-preview-file?path={quote(primary)}" if primary and Path(primary).exists() else ''
    clean['preview_urls'] = [
        {
            'path': p,
            'url': f"/api/neo-library/lora-preview-file?path={quote(p)}",
            'name': Path(p).name,
        }
        for p in preview_paths if Path(p).exists()
    ]
    remote = clean.get('remote_source') if isinstance(clean.get('remote_source'), dict) else {}
    clean['provider'] = str(remote.get('provider') or clean.get('provider') or '').strip()
    clean['provider_url'] = str(remote.get('url') or clean.get('provider_url') or '').strip()
    clean['provider_label'] = str(remote.get('model_name') or '').strip() or str(clean.get('name') or '').strip()
    return clean


def _lora_preview_file_response(path_str: str):
    path = Path(str(path_str or '').strip())
    if not path_str or not path.exists() or not path.is_file():
        return None
    if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}:
        return None
    media_type = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type)


def _parse_library_items(md_text: str):
    rows = []
    for line in md_text.splitlines():
        m = _NUM_ITEM.match(line)
        if m:
            rows.append(m.group(2).strip())
            continue
        m = _BULLET_ITEM.match(line)
        if m:
            rows.append(m.group(1).strip())
    return rows


def _composer_library_names():
    if not _LIBRARIES_DIR.exists():
        return []
    return [path.stem for path in sorted(_LIBRARIES_DIR.glob('*.md'))]


def _composer_library_items(library: str = '', query: str = ''):
    names = _composer_library_names()
    chosen = ''
    if library:
        candidate = Path(library).stem
        if candidate in names:
            chosen = candidate
    if not chosen and names:
        chosen = names[0]
    if not chosen:
        return names, '', []
    path = _LIBRARIES_DIR / f'{chosen}.md'
    try:
        source = path.read_text(encoding='utf-8')
    except Exception:
        return names, chosen, []
    rows = _parse_library_items(source)
    query_lc = (query or '').strip().lower()
    if query_lc:
        rows = [row for row in rows if query_lc in row.lower()]
    return names, chosen, rows


def _prompt_browser_entries(
    query: str = '',
    category: str = '',
    model: str = '',
    prompt_style: str = '',
    sort: str = 'newest',
    page: int = 1,
    page_size: int = 12,
):
    query_lc = (query or '').strip().lower()
    category = (category or '').strip()
    model_lc = (model or '').strip().lower()
    style_lc = (prompt_style or '').strip().lower()
    sort_mode = (sort or 'newest').strip().lower()
    if sort_mode not in {'newest', 'oldest', 'az'}:
        sort_mode = 'newest'
    rows = []
    for rec in iter_records('prompt'):
        rec_category = str(rec.get('category') or 'uncategorized').strip() or 'uncategorized'
        rec_model = str(rec.get('model') or '').strip()
        rec_style = str(rec.get('style') or '').strip()
        updated_at = str(rec.get('updated_at') or rec.get('created_at') or '')
        if category and rec_category != category:
            continue
        if model_lc and model_lc not in rec_model.lower():
            continue
        if style_lc and style_lc not in rec_style.lower():
            continue
        haystack = ' '.join([
            str(rec.get('name') or ''),
            rec_category,
            rec_model,
            rec_style,
            str(rec.get('prompt') or ''),
            str(rec.get('notes') or ''),
        ]).lower()
        if query_lc and query_lc not in haystack:
            continue
        rows.append({
            'id': str(rec.get('id') or ''),
            'name': str(rec.get('name') or '').strip() or '(untitled)',
            'category': rec_category,
            'model': rec_model,
            'style': rec_style,
            'created_at': str(rec.get('created_at') or ''),
            'updated_at': updated_at,
            'prompt_preview': str(rec.get('prompt') or '')[:220],
            'prompt': str(rec.get('prompt') or ''),
            'notes': str(rec.get('notes') or ''),
            'raw_prompt': str(rec.get('raw_prompt') or rec.get('prompt') or ''),
        })

    if sort_mode == 'az':
        rows.sort(key=lambda item: (str(item.get('name') or '').lower(), str(item.get('updated_at') or item.get('created_at') or '')))
    else:
        rows.sort(
            key=lambda item: (str(item.get('updated_at') or item.get('created_at') or ''), str(item.get('name') or '').lower()),
            reverse=(sort_mode == 'newest'),
        )

    total = len(rows)
    page_size = max(1, int(page_size or 12))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, int(page or 1)), total_pages)
    start = (page - 1) * page_size
    return rows[start:start + page_size], total, total_pages, page


def _output_browser_entries(mode: str = 'txt2img', page: int = 1, page_size: int = 25):
    mode = (mode or 'txt2img').strip().lower()
    if mode not in {'txt2img', 'img2img'}:
        mode = 'txt2img'
    names = output_image_names(mode)
    total = len(names)
    page_size = max(1, int(page_size or 25))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, int(page or 1)), total_pages)
    start = (page - 1) * page_size
    chunk = names[start:start + page_size]
    return chunk, total, total_pages, page, str(get_output_dirs().get(mode) or '')


@router.get('/api/neo-library/composer-library-browser')
async def api_neo_library_composer_library_browser(library: str = '', query: str = ''):
    names, selected, items = _composer_library_items(library=library, query=query)
    return JSONResponse({
        'ok': True,
        'libraries': names,
        'selected_library': selected,
        'items': items,
        'total': len(items),
    })




@router.get('/api/neo-library/storage-compat')
async def api_neo_library_storage_compat():
    return JSONResponse(build_storage_compat_snapshot())

@router.get('/api/neo-library/summary')
async def api_neo_library_summary():
    base = stats()
    base['prompt_categories'] = prompt_categories()
    base['library_root'] = str(get_library_root())
    return JSONResponse({'ok': True, 'summary': base})


@router.get('/api/neo-library/prompt-browser')
async def api_neo_library_prompt_browser(
    query: str = '',
    category: str = '',
    model: str = '',
    prompt_style: str = '',
    sort: str = 'newest',
    page: int = 1,
    page_size: int = 12,
):
    entries, total, total_pages, current_page = _prompt_browser_entries(
        query=query,
        category=category,
        model=model,
        prompt_style=prompt_style,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return JSONResponse({
        'ok': True,
        'entries': entries,
        'categories': prompt_categories(),
        'total': total,
        'page': current_page,
        'page_size': max(1, int(page_size or 12)),
        'total_pages': total_pages,
        'sort': (sort or 'newest').strip().lower() or 'newest',
    })


@router.get('/api/neo-library/prompt-record')
async def api_neo_library_prompt_record(prompt_id: str = '', category: str = '', name: str = ''):
    rec = get_prompt_record(prompt_id=prompt_id, category=category, name=name)
    if not rec:
        return json_error('Prompt not found.', 404)
    clean = {k: v for k, v in rec.items() if not str(k).startswith('_')}
    return JSONResponse({'ok': True, 'record': clean, 'categories': prompt_categories()})


@router.get('/api/neo-library/caption-sync')
async def api_neo_library_caption_sync(category: str = '', name: str = '', image_name: str = ''):
    rows = []
    category = (category or '').strip()
    for rec in iter_records('caption'):
        rec_category = str(rec.get('category') or 'uncategorized').strip() or 'uncategorized'
        if category and rec_category != category:
            continue
        image_rel = str(rec.get('image_path') or '')
        image_filename = Path(image_rel).name if image_rel else ''
        rows.append({
            'id': str(rec.get('id') or ''),
            'name': str(rec.get('name') or '').strip() or '(untitled)',
            'category': rec_category,
            'image_name': image_filename,
            'updated_at': str(rec.get('updated_at') or rec.get('created_at') or ''),
        })

    rows.sort(key=lambda item: (item['updated_at'], item['name'].lower()), reverse=True)
    categories = sorted({str((rec.get('category') or 'uncategorized')).strip() or 'uncategorized' for rec in iter_records('caption')}, key=str.lower) or ['uncategorized']
    if not category:
        category = categories[0] if categories else 'uncategorized'
        rows = [row for row in rows if row['category'] == category]
    if category and category not in categories:
        categories.append(category)
        categories.sort(key=str.lower)

    selected = None
    target_image = (image_name or '').strip().lower()
    target_name = (name or '').strip().lower()
    if target_image:
        selected = next((row for row in rows if row['image_name'].lower() == target_image), None)
    if not selected and target_name:
        selected = next((row for row in rows if row['name'].lower() == target_name), None)
    if not selected and rows:
        selected = rows[0]

    record = None
    if selected:
        record = get_caption_record(caption_id=selected['id'])
        if record:
            clean = {k: v for k, v in record.items() if not str(k).startswith('_')}
            clean['thumb_url'] = f"/api/caption-thumb?caption_id={clean.get('id')}" if clean.get('id') else ''
            clean['image_url'] = f"/api/caption-image-file?caption_id={clean.get('id')}" if clean.get('id') else ''
            record = clean

    names = []
    seen_names = set()
    image_names = []
    seen_images = set()
    for row in rows:
        if row['name'].lower() not in seen_names:
            seen_names.add(row['name'].lower())
            names.append(row['name'])
        if row['image_name'] and row['image_name'].lower() not in seen_images:
            seen_images.add(row['image_name'].lower())
            image_names.append(row['image_name'])

    return JSONResponse({
        'ok': True,
        'categories': categories,
        'selected_category': category,
        'names': names,
        'images': image_names,
        'record': record,
    })


@router.get('/api/neo-library/output-browser')
async def api_neo_library_output_browser(mode: str = 'txt2img', page: int = 1, page_size: int = 25):
    entries, total, total_pages, current_page, output_root = _output_browser_entries(mode=mode, page=page, page_size=page_size)
    return JSONResponse({
        'ok': True,
        'mode': (mode or 'txt2img').strip().lower() or 'txt2img',
        'entries': entries,
        'total': total,
        'page': current_page,
        'page_size': max(1, int(page_size or 25)),
        'total_pages': total_pages,
        'output_root': output_root,
        'available_modes': sorted(list(get_output_dirs().keys())),
    })


@router.get('/api/neo-library/output-record')
async def api_neo_library_output_record(mode: str = 'txt2img', name: str = ''):
    rec = load_output_record(mode, name)
    image_url = f"/api/neo-library/output-file?mode={mode}&name={name}"
    return JSONResponse({'ok': True, 'record': {**rec, 'image_url': image_url}})


@router.get('/api/neo-library/output-file')
async def api_neo_library_output_file(mode: str = 'txt2img', name: str = ''):
    path = resolve_output_path(mode, name)
    if not path:
        return json_error('Output image not found.', 404)
    return FileResponse(path)


@router.get('/api/neo-library/lora-browser')
async def api_neo_library_lora_browser(
    kind: str = 'lora',
    query: str = '',
    category: str = 'all',
    base_model: str = 'all',
    style_category: str = 'all',
):
    kind = (kind or 'lora').strip().lower()
    if kind not in {'lora', 'ti'}:
        kind = 'lora'
    store = _vault_store()
    entries = []
    for (label, lid) in store.list_lora_choices(
        q=query,
        kind=kind,
        category=category or 'all',
        base_model=base_model or 'all',
        style_category=style_category or 'all',
    ):
        rec = store.get_lora(lid) or {}
        entries.append({
            'label': label,
            'id': lid,
            'name': str(rec.get('name') or '').strip(),
            'category': str(rec.get('category') or '').strip(),
            'rel': str(rec.get('rel') or '').strip(),
            'base_model': str(rec.get('base_model') or '').strip(),
            'style_category': str(rec.get('style_category') or '').strip(),
            'provider_label': str(rec.get('provider_label') or '').strip(),
            'notes': str(rec.get('notes') or '').strip(),
        })
    return JSONResponse({
        'ok': True,
        'kind': kind,
        'entries': entries,
        'categories': ['all', *store.list_lora_categories(kind)],
        'base_models': ['all', *store.list_lora_base_models(kind)],
        'style_categories': ['all', *store.list_lora_style_categories(kind)],
    })


@router.get('/api/neo-library/lora-record')
async def api_neo_library_lora_record(lid: str = ''):
    store = _vault_store()
    rec = store.get_lora(lid) if lid else None
    if not rec:
        return json_error('LoRA / TI entry not found.', 404)
    clean = _clean_lora_record(rec)
    return JSONResponse({'ok': True, 'record': clean})


@router.get('/api/neo-library/lora-preview-file')
async def api_neo_library_lora_preview_file(path: str = ''):
    response = _lora_preview_file_response(path)
    if response is None:
        return json_error('Preview image not found.', 404)
    return response


@router.post('/api/neo-library/lora-civitai-import')
async def api_neo_library_lora_civitai_import(
    lid: str = Form(''),
    civitai_url: str = Form(''),
    merge_mode: str = Form('fill_missing'),
    overwrite_fields_csv: str = Form(''),
):
    store = _vault_store()
    if not lid:
        return json_error('Select a LoRA / TI entry first.', 400)
    try:
        result = store.import_civitai_into_lora(
            lid,
            civitai_url or '',
            merge_mode=(merge_mode or 'fill_missing'),
            overwrite_fields=_split_csv_tokens(overwrite_fields_csv),
        )
    except Exception as e:
        return json_exception(e, default_message='CivitAI import failed.', default_status=400, logger_override=logger, context='neo library civitai import')
    if not result.get('ok'):
        return json_error(str(result.get('message') or 'CivitAI import failed.'), 400)
    rec = store.get_lora(lid) or {}
    return JSONResponse({'ok': True, 'message': result.get('message') or 'CivitAI import complete.', 'record': _clean_lora_record(rec), 'result': result})


@router.post('/api/neo-library/lora-set-primary-preview')
async def api_neo_library_lora_set_primary_preview(
    lid: str = Form(''),
    preview_path: str = Form(''),
):
    store = _vault_store()
    if not lid or not preview_path:
        return json_error('Pick a LoRA / TI entry and a preview first.', 400)
    ok = store.set_primary_lora_preview(lid, preview_path)
    if not ok:
        return json_error('Could not update the primary preview.', 400)
    rec = store.get_lora(lid) or {}
    return JSONResponse({'ok': True, 'message': 'Primary preview updated.', 'record': _clean_lora_record(rec)})


@router.get('/api/neo-library/lora-insert-block')
async def api_neo_library_lora_insert_block(
    lid: str = '',
    strength: float = 1.0,
    include_triggers: bool = True,
    selected_triggers: str = '',
):
    store = _vault_store()
    rec = store.get_lora(lid) if lid else None
    if not rec:
        return json_error('LoRA / TI entry not found.', 404)
    chosen = _split_csv_tokens(selected_triggers)
    block = store.build_lora_insert_block(
        lid=lid,
        strength=float(strength or 1.0),
        selected_triggers=chosen if chosen else None,
        include_triggers=bool(include_triggers),
    )
    return JSONResponse({'ok': True, 'block': block, 'record': _clean_lora_record(rec)})




def _keyword_insert_text(rec: dict[str, Any], include_desc: bool = True) -> str:
    name = str(rec.get('name') or '').strip()
    desc = str(rec.get('desc') or '').strip()
    if include_desc and desc:
        return f"{name}, {desc}" if name else desc
    return name


def _open_folder_status(path: str) -> str:
    p = str(path or '').strip()
    if not p:
        return '⚠️ No folder path.'
    try:
        if not os.path.exists(p):
            return f'⚠️ Folder not found: {p}'
        if sys.platform.startswith('win'):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', p])
        else:
            subprocess.Popen(['xdg-open', p])
        return f'✅ Opened: {p}'
    except OSError as e:
        return f'⚠️ Could not open folder: {e}'


def _mapgen_defaults() -> dict[str, Any]:
    return {
        'python_exe': '',
        'script_path': str(_MAPGEN_SCRIPT),
        'in_dir': '',
        'out_dir': '',
        'mapset_name': '',
        'mode': 'cover',
        'detect': 512,
        'portrait_size': '896x1344',
        'landscape_size': '1344x896',
        'name_suffix': True,
        'do_canny': True,
        'do_openpose': True,
        'do_depth': False,
        'canny_low': 150,
        'canny_high': 300,
        'blur': 3,
        'clahe': False,
        'sharpen': False,
        'denoise': False,
        'canny_invert': False,
        'canny_thickness': 'none',
        'canny_adaptive': False,
        'canny_clean_bg': False,
        'canny_clean_thresh': 128,
        'device': 'cpu',
        'hands': False,
        'face': False,
        'depth_device': 'cpu',
        'depth_invert': False,
        'recursive': False,
        'skip_existing': True,
    }


def _mapgen_load_settings() -> dict[str, Any]:
    data = _mapgen_defaults()
    try:
        if _MAPGEN_SETTINGS_PATH.exists():
            saved = read_json(_MAPGEN_SETTINGS_PATH, {})
            if isinstance(saved, dict):
                data.update(saved)
    except Exception:
        pass
    return data


def _mapgen_save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    data = _mapgen_defaults()
    data.update({k: v for k, v in payload.items() if k in data})
    atomic_write_json(_MAPGEN_SETTINGS_PATH, data)
    return data


def _sanitize_name(text: str) -> str:
    text = str(text or '').strip().replace('\\', '/').strip('/')
    out = []
    for ch in text:
        out.append(ch if (ch.isalnum() or ch in ('_', '-', ' ')) else '_')
    text = ''.join(out).strip().replace('  ', ' ').replace(' ', '_')
    return text[:80]


def _effective_out_dir(out_dir: str, mapset_name: str) -> str:
    base = Path(str(out_dir or '').strip())
    name = _sanitize_name(mapset_name)
    return str((base / name)) if name else str(base)


def _gather_maps_from_out(out_eff: str) -> dict[str, list[str]]:
    base = Path(str(out_eff or '').strip())
    exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
    out: dict[str, list[str]] = {'canny': [], 'openpose': [], 'depth': []}
    if not base.exists():
        return out
    for kind in ('canny', 'openpose', 'depth'):
        root = base / kind
        if not root.exists():
            continue
        for fp in root.rglob('*'):
            if fp.is_file() and fp.suffix.lower() in exts:
                out[kind].append(str(fp))
    return out


def _register_out_as_mapset(out_eff: str, mapset_title: str, enforce_suffix: bool = True) -> str:
    store = _vault_store()
    out_eff = str(out_eff or '').strip()
    if not out_eff:
        return '⚠️ No output folder.'
    if not os.path.exists(out_eff):
        return f'⚠️ Output folder not found: {out_eff}'
    title = str(mapset_title or '').strip() or Path(out_eff).name
    mid = ''
    want = _ps_norm_token(title)
    for m in (store.data.get('mapsets') or []):
        if _ps_norm_token(str(m.get('title') or '')) == want:
            mid = str(m.get('id') or '')
            break
    if not mid:
        mid = store.create_mapset(title, '')
    total = 0
    files_by_type = _gather_maps_from_out(out_eff)
    for kind, files in files_by_type.items():
        if files:
            total += store.add_maps_to_mapset(mid, files, map_type=kind, auto_detect=False, enforce_suffix=bool(enforce_suffix))
    if total == 0:
        return '⚠️ No maps found to import. Make sure maps were generated first.'
    return f'✅ Registered output as mapset: {title} (imported {total} map(s))'


def _mapset_folder(mid: str) -> str:
    if not mid:
        return ''
    try:
        return str((_ASSETS_DIR / mid).resolve())
    except OSError:
        return str(_ASSETS_DIR / mid)


def _map_paths_payload(store: VaultStore, mid: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for kind in ('canny', 'depth', 'openpose'):
        rows = []
        for label, path in store.list_map_paths(mid, kind):
            rows.append({'label': label, 'path': path})
        out[kind] = rows
    return out


@router.get('/api/neo-library/keyword-browser')
async def api_neo_library_keyword_browser(category: str = 'all', subcategory: str = 'all', query: str = ''):
    store = _vault_store()
    cats = ['all', *store.list_keyword_categories()]
    cat = category if category in cats else (cats[1] if len(cats) > 1 else 'all')
    subs = ['all', *store.list_keyword_subcategories(cat)]
    sub = subcategory if subcategory in subs else (subs[1] if len(subs) > 1 else 'all')
    entries = [{'label': label, 'id': tid} for (label, tid) in store.list_tag_choices(q=query or '', category=cat, subcategory=sub)]
    return JSONResponse({'ok': True, 'categories': cats, 'subcategories': subs, 'selected_category': cat, 'selected_subcategory': sub, 'entries': entries})


@router.get('/api/neo-library/keyword-record')
async def api_neo_library_keyword_record(tid: str = ''):
    store = _vault_store()
    rec = store.get_tag(tid) if tid else None
    if not rec:
        return json_error('Keyword not found.', 404)
    return JSONResponse({'ok': True, 'record': rec})


@router.get('/api/neo-library/keyword-insert-text')
async def api_neo_library_keyword_insert_text(tid: str = '', include_desc: bool = True):
    store = _vault_store()
    rec = store.get_tag(tid) if tid else None
    if not rec:
        return json_error('Keyword not found.', 404)
    return JSONResponse({'ok': True, 'text': _keyword_insert_text(rec, include_desc=bool(include_desc)), 'record': rec})


@router.post('/api/neo-library/keyword-save')
async def api_neo_library_keyword_save(
    tid: str = Form(''),
    category: str = Form(''),
    subcategory: str = Form('general'),
    name: str = Form(''),
    aliases: str = Form(''),
    desc: str = Form(''),
    enabled: bool = Form(True),
):
    store = _vault_store()
    out_id = store.upsert_tag(tid or '', category or '', subcategory or 'general', name or '', aliases or '', desc or '', bool(enabled))
    if not out_id:
        return json_error('Keyword name is required.', 400)
    return JSONResponse({'ok': True, 'message': 'Keyword saved.', 'tid': out_id, 'record': store.get_tag(out_id), 'categories': ['all', *store.list_keyword_categories()], 'subcategories': ['all', *store.list_keyword_subcategories(category or 'all')]})


@router.post('/api/neo-library/keyword-delete')
async def api_neo_library_keyword_delete(tid: str = Form('')):
    store = _vault_store()
    if not tid:
        return json_error('Nothing selected.', 400)
    store.delete_tag(tid)
    return JSONResponse({'ok': True, 'message': 'Keyword deleted.'})


@router.post('/api/neo-library/lora-scan')
async def api_neo_library_lora_scan(
    lora_dir: str = Form(''),
    embed_dir: str = Form(''),
    include_ti: bool = Form(True),
):
    store = _vault_store()
    added, updated = store.scan_loras(lora_dir or '', embed_dir or '', include_ti=bool(include_ti))
    return JSONResponse({'ok': True, 'message': f'Scan complete. Added: {added}, updated: {updated}.', 'added': added, 'updated': updated})


@router.post('/api/neo-library/lora-save')
async def api_neo_library_lora_save(
    lid: str = Form(''),
    default_strength: float = Form(0.8),
    min_strength: float = Form(0.6),
    max_strength: float = Form(1.0),
    triggers: str = Form(''),
    keywords: str = Form(''),
    style_category: str = Form(''),
    base_model: str = Form(''),
    example_prompt: str = Form(''),
    preview_image: str = Form(''),
    caution_notes: str = Form(''),
    notes: str = Form(''),
    prompt_options_json: str = Form('[]'),
    enabled: bool = Form(True),
):
    store = _vault_store()
    try:
        prompt_options = json.loads(prompt_options_json or '[]') if str(prompt_options_json or '').strip() else []
        if not isinstance(prompt_options, list):
            prompt_options = []
    except Exception:
        prompt_options = []
    out = store.upsert_lora_meta(
        lid or '',
        triggers or '',
        keywords or '',
        float(default_strength or 0.8),
        notes or '',
        enabled=bool(enabled),
        min_strength=float(min_strength or 0.6),
        max_strength=float(max_strength or 1.0),
        base_model=base_model or '',
        caution_notes=caution_notes or '',
        example_prompt=example_prompt or '',
        preview_image=preview_image or '',
        style_category=style_category or '',
        prompt_options=prompt_options,
    )
    if not out:
        return json_error('LoRA / TI entry not found.', 404)
    rec = store.get_lora(lid or '')
    return JSONResponse({'ok': True, 'message': 'LoRA / TI metadata saved.', 'record': _clean_lora_record(rec or {})})


@router.post('/api/neo-library/lora-delete')
async def api_neo_library_lora_delete(lid: str = Form('')):
    store = _vault_store()
    if not lid:
        return json_error('Nothing selected.', 400)
    store.delete_lora(lid)
    return JSONResponse({'ok': True, 'message': 'LoRA / TI entry deleted.'})


@router.get('/api/neo-library/vault-overview')
async def api_neo_library_vault_overview():
    store = _vault_store()
    return JSONResponse({
        'ok': True,
        'keyword_count': len(store.data.get('tags') or []),
        'pack_count': len(store.data.get('packs') or []),
        'lora_count': len([x for x in (store.data.get('loras') or []) if str((x or {}).get('kind') or 'lora').strip().lower() == 'lora']),
        'ti_count': len([x for x in (store.data.get('loras') or []) if str((x or {}).get('kind') or '').strip().lower() == 'ti']),
        'mapset_count': len(store.data.get('mapsets') or []),
        'assets_root': str(_ASSETS_DIR),
        'lora_previews_dir': str(_LORA_PREVIEWS_DIR),
        'default_lora_dir': store._default_lora_dir(),
        'default_embed_dir': store._default_embed_dir(),
    })


@router.get('/api/neo-library/mapset-browser')
async def api_neo_library_mapset_browser(query: str = ''):
    store = _vault_store()
    rows = []
    for label, mid in store.list_mapset_choices(q=query or ''):
        rows.append({'label': label, 'id': mid})
    return JSONResponse({'ok': True, 'entries': rows, 'assets_root': str(_ASSETS_DIR)})


@router.get('/api/neo-library/mapset-record')
async def api_neo_library_mapset_record(mid: str = ''):
    store = _vault_store()
    rec = store.get_mapset(mid) if mid else None
    if not rec:
        return json_error('Mapset not found.', 404)
    return JSONResponse({'ok': True, 'record': rec, 'folder': _mapset_folder(mid), 'maps': _map_paths_payload(store, mid)})


@router.post('/api/neo-library/mapset-create')
async def api_neo_library_mapset_create(title: str = Form(''), tags_csv: str = Form('')):
    store = _vault_store()
    mid = store.create_mapset(title or 'New Mapset', tags_csv or '')
    rec = store.get_mapset(mid) or {}
    return JSONResponse({'ok': True, 'message': 'Mapset created.', 'record': rec, 'folder': _mapset_folder(mid), 'maps': _map_paths_payload(store, mid)})


@router.post('/api/neo-library/mapset-save')
async def api_neo_library_mapset_save(mid: str = Form(''), title: str = Form(''), tags_csv: str = Form('')):
    store = _vault_store()
    if not mid:
        return json_error('Select a mapset first.', 400)
    store.update_mapset_meta(mid, title or '', tags_csv or '')
    rec = store.get_mapset(mid) or {}
    return JSONResponse({'ok': True, 'message': 'Mapset saved.', 'record': rec, 'folder': _mapset_folder(mid), 'maps': _map_paths_payload(store, mid)})


@router.post('/api/neo-library/mapset-delete')
async def api_neo_library_mapset_delete(mid: str = Form('')):
    store = _vault_store()
    if not mid:
        return json_error('Nothing selected.', 400)
    store.delete_mapset(mid)
    return JSONResponse({'ok': True, 'message': 'Mapset deleted.'})


@router.post('/api/neo-library/mapset-import-folder')
async def api_neo_library_mapset_import_folder(
    mid: str = Form(''),
    folder: str = Form(''),
    recursive: bool = Form(False),
    import_mode: str = Form('auto-detect by filename'),
    enforce_suffix: bool = Form(True),
):
    store = _vault_store()
    if not mid:
        return json_error('Select a mapset first.', 400)
    folder = str(folder or '').strip().strip('"').strip("'")
    if not folder or not os.path.isdir(folder):
        return json_error('Folder not found.', 400)
    exts = {'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}
    paths: list[str] = []
    if recursive:
        for root, _, files in os.walk(folder):
            for fn in files:
                if Path(fn).suffix.lower() in exts:
                    paths.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(folder):
            pth = os.path.join(folder, fn)
            if os.path.isfile(pth) and Path(fn).suffix.lower() in exts:
                paths.append(pth)
    if not paths:
        return json_error('No images found in that folder.', 400)
    auto_detect = (import_mode == 'auto-detect by filename')
    map_type = 'canny' if auto_detect else import_mode
    count = store.add_maps_to_mapset(mid, paths, map_type=map_type, auto_detect=auto_detect, enforce_suffix=bool(enforce_suffix))
    rec = store.get_mapset(mid) or {}
    return JSONResponse({'ok': True, 'message': f'Imported {count} map(s) from folder.', 'record': rec, 'folder': _mapset_folder(mid), 'maps': _map_paths_payload(store, mid)})


@router.post('/api/neo-library/open-folder')
async def api_neo_library_open_folder(path: str = Form('')):
    return JSONResponse({'ok': True, 'message': _open_folder_status(path or '')})


@router.get('/api/neo-library/mapgen-settings')
async def api_neo_library_mapgen_settings():
    data = _mapgen_load_settings()
    data['effective_out_dir'] = _effective_out_dir(str(data.get('out_dir') or ''), str(data.get('mapset_name') or ''))
    return JSONResponse({'ok': True, 'settings': data})


@router.post('/api/neo-library/mapgen-settings-save')
async def api_neo_library_mapgen_settings_save(payload: dict[str, Any]):
    data = _mapgen_save_settings(payload or {})
    data['effective_out_dir'] = _effective_out_dir(str(data.get('out_dir') or ''), str(data.get('mapset_name') or ''))
    return JSONResponse({'ok': True, 'message': 'Map Generator settings saved.', 'settings': data})


@router.post('/api/neo-library/mapgen-run')
async def api_neo_library_mapgen_run(payload: dict[str, Any]):
    cfg = _mapgen_save_settings(payload or {})
    script_path = Path(str(cfg.get('script_path') or _MAPGEN_SCRIPT)).resolve()
    if not script_path.exists():
        return json_error(f'Map generator script not found: {script_path}', 404)
    py = str(cfg.get('python_exe') or '').strip() or sys.executable
    out_dir_eff = _effective_out_dir(str(cfg.get('out_dir') or ''), str(cfg.get('mapset_name') or ''))
    args = [py, str(script_path), '--in_dir', str(cfg.get('in_dir') or ''), '--out_dir', out_dir_eff, '--mode', str(cfg.get('mode') or 'cover'), '--detect', str(int(cfg.get('detect') or 512)), '--portrait_size', str(cfg.get('portrait_size') or '896x1344'), '--landscape_size', str(cfg.get('landscape_size') or '1344x896'), '--canny_low', str(int(cfg.get('canny_low') or 150)), '--canny_high', str(int(cfg.get('canny_high') or 300)), '--blur', str(int(cfg.get('blur') or 3)), '--canny_thickness', str(cfg.get('canny_thickness') or 'none'), '--device', str(cfg.get('device') or 'cpu'), '--depth_device', str(cfg.get('depth_device') or 'cpu')]
    if cfg.get('name_suffix'): args.append('--name_suffix')
    if cfg.get('do_canny'): args.append('--canny')
    if cfg.get('do_openpose'): args.append('--openpose')
    if cfg.get('do_depth'): args.append('--depth')
    if cfg.get('clahe'): args.append('--clahe')
    if cfg.get('sharpen'): args.append('--sharpen')
    if cfg.get('denoise'): args.append('--denoise')
    if cfg.get('canny_invert'): args.append('--canny_invert')
    if cfg.get('canny_adaptive'): args.append('--canny_adaptive')
    if cfg.get('canny_clean_bg'): args.append('--canny_clean_bg')
    if cfg.get('hands'): args.append('--hands')
    if cfg.get('face'): args.append('--face')
    if cfg.get('depth_invert'): args.append('--depth_invert')
    if cfg.get('recursive'): args.append('--recursive')
    if cfg.get('skip_existing'): args.append('--skip_existing')
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
        log = (proc.stdout or '') + (('\n' + proc.stderr) if proc.stderr else '')
    except Exception as e:
        return json_exception(e, default_message='Could not run map generator.', default_status=500, logger_override=logger, context='neo library map generator')
    return JSONResponse({'ok': proc.returncode == 0, 'returncode': proc.returncode, 'log': log.strip(), 'effective_out_dir': out_dir_eff, 'command': ' '.join(shlex.quote(a) for a in args)})


@router.post('/api/neo-library/mapgen-register-output')
async def api_neo_library_mapgen_register_output(out_dir: str = Form(''), mapset_name: str = Form(''), enforce_suffix: bool = Form(True)):
    msg = _register_out_as_mapset(out_dir or '', mapset_name or '', enforce_suffix=bool(enforce_suffix))
    return JSONResponse({'ok': msg.startswith('✅'), 'message': msg})


@router.get('/api/neo-library/composer-character-builder-data')
async def api_neo_library_composer_character_builder_data(
    gender: str = 'male',
    era: str = 'any',
    show_restricted: bool = False,
    section: str = '',
    library: str = '',
    query: str = '',
):
    entries = _cc_entries(gender=gender, era=era, show_restricted=show_restricted)
    sections = _cc_group_choices(entries)
    selected_section = section if section in sections else (sections[0] if sections else '')
    libraries = _cc_lib_choices(entries, selected_section) if selected_section else []
    selected_library = library if library in libraries else (libraries[0] if libraries else '')
    source_key = f'{selected_section}__{selected_library}' if selected_section and selected_library else ''
    items = _cc_item_choices(query=query, source_file=source_key, entries=entries) if source_key else []
    return JSONResponse({
        'ok': True,
        'sections': sections,
        'selected_section': selected_section,
        'libraries': libraries,
        'selected_library': selected_library,
        'items': items,
        'total': len(items),
    })


@router.get('/api/neo-library/composer-prompt-presets')
async def api_neo_library_composer_prompt_presets(query: str = '', browse_cat: str = 'all'):
    ps = PromptPresetStore()
    compare_choices = _composer_preset_choices('', 'all')
    return JSONResponse({
        'ok': True,
        'categories': ['all', *_preset_category_choices()],
        'entries': _composer_preset_choices(query, browse_cat),
        'compare_entries': compare_choices,
        'groups': ps.list_groups() or [],
    })


@router.get('/api/neo-library/composer-prompt-preset-record')
async def api_neo_library_composer_prompt_preset_record(pid: str = ''):
    ps = PromptPresetStore()
    it = ps.get(pid) if pid else None
    if not it:
        return json_error('Saved prompt not found.', 404)
    synced = _synced_prompt_meta(pid)
    category = (it.get('category') or synced.get('category') or 'uncategorized').strip() or 'uncategorized'
    notes = it.get('notes') or synced.get('notes') or ''
    payload = dict(it)
    payload['category'] = category
    payload['notes'] = notes
    payload['meta_text'] = _preset_meta_text(it)
    return JSONResponse({'ok': True, 'record': payload, 'categories': _preset_category_choices()})


@router.post('/api/neo-library/composer-prompt-preset-save-new')
async def api_neo_library_composer_prompt_preset_save_new(
    title: str = Form(...),
    positive: str = Form(''),
    negative: str = Form(''),
    category: str = Form('uncategorized'),
    new_category: str = Form(''),
    notes: str = Form(''),
    group: str = Form(''),
    favorite: bool = Form(False),
):
    ps = PromptPresetStore()
    final_cat = (new_category or '').strip() or (category or '').strip() or 'uncategorized'
    pid = ps.upsert('', title or 'Untitled', positive or '', negative or '', {}, {}, {}, assets=None, category=final_cat, notes=notes or '', group=group or '', favorite=bool(favorite))
    if not pid:
        return json_error('Title required.', 400)
    _sync_prompt_record(pid, title or 'Untitled', positive or '', negative or '', final_cat, notes or '')
    return JSONResponse({'ok': True, 'message': 'Saved new prompt.', 'pid': pid, 'record': ps.get(pid), 'categories': _preset_category_choices()})


@router.post('/api/neo-library/composer-prompt-preset-update')
async def api_neo_library_composer_prompt_preset_update(
    pid: str = Form(...),
    title: str = Form(...),
    positive: str = Form(''),
    negative: str = Form(''),
    category: str = Form('uncategorized'),
    new_category: str = Form(''),
    notes: str = Form(''),
    group: str = Form(''),
    favorite: bool = Form(False),
):
    ps = PromptPresetStore()
    final_cat = (new_category or '').strip() or (category or '').strip() or 'uncategorized'
    out = ps.upsert(pid, title or 'Untitled', positive or '', negative or '', {}, {}, {}, assets=None, category=final_cat, notes=notes or '', group=group or '', favorite=bool(favorite))
    if not out:
        return json_error('Could not update saved prompt.', 400)
    _sync_prompt_record(out, title or 'Untitled', positive or '', negative or '', final_cat, notes or '')
    return JSONResponse({'ok': True, 'message': 'Updated saved prompt.', 'pid': out, 'record': ps.get(out), 'categories': _preset_category_choices()})


@router.post('/api/neo-library/composer-prompt-preset-delete')
async def api_neo_library_composer_prompt_preset_delete(pid: str = Form(...)):
    ps = PromptPresetStore()
    if not ps.get(pid):
        return json_error('Saved prompt not found.', 404)
    ps.delete(pid)
    _delete_synced_prompt_record(pid)
    return JSONResponse({'ok': True, 'message': 'Deleted saved prompt.', 'categories': _preset_category_choices()})


@router.post('/api/neo-library/composer-prompt-preset-duplicate')
async def api_neo_library_composer_prompt_preset_duplicate(pid: str = Form(...)):
    ps = PromptPresetStore()
    out = ps.duplicate(pid)
    if not out:
        return json_error('Duplicate failed.', 400)
    dup = ps.get(out) or {}
    _sync_prompt_record(out, dup.get('title') or 'Untitled', dup.get('positive') or '', dup.get('negative') or '', dup.get('category') or 'uncategorized', dup.get('notes') or '')
    return JSONResponse({'ok': True, 'message': 'Duplicated preset.', 'pid': out, 'record': dup, 'categories': _preset_category_choices()})


@router.post('/api/neo-library/composer-prompt-preset-toggle-favorite')
async def api_neo_library_composer_prompt_preset_toggle_favorite(pid: str = Form(...)):
    ps = PromptPresetStore()
    state = ps.toggle_favorite(pid)
    if state is None:
        return json_error('Saved prompt not found.', 404)
    rec = ps.get(pid) or {}
    return JSONResponse({'ok': True, 'favorite': bool(state), 'record': rec, 'meta_text': _preset_meta_text(rec)})


@router.get('/api/neo-library/composer-prompt-preset-compare')
async def api_neo_library_composer_prompt_preset_compare(pid_a: str = '', pid_b: str = ''):
    ps = PromptPresetStore()
    cmp = ps.compare(pid_a, pid_b)
    return JSONResponse({'ok': bool(cmp.get('ok')), 'comparison': cmp})


@router.get('/api/neo-library/composer-prompt-preset-export')
async def api_neo_library_composer_prompt_preset_export(pid: str = ''):
    ps = PromptPresetStore()
    if not pid:
        return json_error('Select a saved prompt first.', 400)
    try:
        payload = ps.export_one(pid)
    except Exception as e:
        return json_exception(e, default_status=400, logger_override=logger, context='neo library prompt preset export')
    return JSONResponse({'ok': True, 'payload': payload})
