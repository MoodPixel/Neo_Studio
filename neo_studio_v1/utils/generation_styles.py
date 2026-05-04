from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, List

from .library_constants import USER_DATA_DIR

STYLE_FIELDS = ['name', 'prompt', 'negative_prompt']
GENERATION_STYLES_PATH = USER_DATA_DIR / 'generation_styles.csv'


def _normalize_style_row(row: dict) -> dict:
    return {
        'name': str(row.get('name') or '').strip(),
        'prompt': str(row.get('prompt') or '').strip(),
        'negative_prompt': str(row.get('negative_prompt') or '').strip(),
    }


def ensure_generation_styles_file() -> Path:
    GENERATION_STYLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GENERATION_STYLES_PATH.exists():
        with GENERATION_STYLES_PATH.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=STYLE_FIELDS)
            writer.writeheader()
    return GENERATION_STYLES_PATH


def load_generation_styles() -> List[Dict[str, str]]:
    path = ensure_generation_styles_file()
    rows: List[Dict[str, str]] = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = _normalize_style_row(row or {})
            if clean['name']:
                rows.append(clean)
    return rows


def save_generation_styles(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    path = ensure_generation_styles_file()
    cleaned = []
    seen = set()
    for row in rows or []:
        clean = _normalize_style_row(row or {})
        key = clean['name'].casefold()
        if not clean['name'] or key in seen:
            continue
        seen.add(key)
        cleaned.append(clean)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=STYLE_FIELDS)
        writer.writeheader()
        writer.writerows(cleaned)
    return cleaned


def upsert_generation_style(*, name: str, prompt: str, negative_prompt: str, original_name: str = '') -> List[Dict[str, str]]:
    target_name = str(name or '').strip()
    if not target_name:
        raise ValueError('Style name is required.')
    rows = load_generation_styles()
    original_key = str(original_name or target_name).strip().casefold()
    new_row = _normalize_style_row({'name': target_name, 'prompt': prompt, 'negative_prompt': negative_prompt})
    replaced = False
    out: List[Dict[str, str]] = []
    for row in rows:
        if row['name'].casefold() == original_key and not replaced:
            out.append(new_row)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(new_row)
    return save_generation_styles(out)


def delete_generation_style(name: str) -> List[Dict[str, str]]:
    target = str(name or '').strip().casefold()
    if not target:
        raise ValueError('Pick a style first.')
    rows = [row for row in load_generation_styles() if row['name'].casefold() != target]
    return save_generation_styles(rows)


def duplicate_generation_style(source_name: str, new_name: str) -> List[Dict[str, str]]:
    source_key = str(source_name or '').strip().casefold()
    target_name = str(new_name or '').strip()
    if not source_key:
        raise ValueError('Pick a source style first.')
    if not target_name:
        raise ValueError('New style name is required.')
    rows = load_generation_styles()
    src = next((row for row in rows if row['name'].casefold() == source_key), None)
    if not src:
        raise ValueError('Source style was not found.')
    rows.append({'name': target_name, 'prompt': src.get('prompt') or '', 'negative_prompt': src.get('negative_prompt') or ''})
    return save_generation_styles(rows)


def import_generation_styles_csv(content: bytes) -> List[Dict[str, str]]:
    try:
        text = content.decode('utf-8-sig')
    except Exception:
        text = content.decode('utf-8', errors='ignore')
    reader = csv.DictReader(io.StringIO(text))
    imported: List[Dict[str, str]] = []
    for row in reader:
        clean = _normalize_style_row(row or {})
        if clean['name']:
            imported.append(clean)
    existing = load_generation_styles()
    merged = {row['name'].casefold(): row for row in existing}
    ordered = existing[:]
    for row in imported:
        key = row['name'].casefold()
        if key in merged:
            for idx, existing_row in enumerate(ordered):
                if existing_row['name'].casefold() == key:
                    ordered[idx] = row
                    break
        else:
            ordered.append(row)
        merged[key] = row
    return save_generation_styles(ordered)


def export_generation_styles_path() -> Path:
    return ensure_generation_styles_file()
