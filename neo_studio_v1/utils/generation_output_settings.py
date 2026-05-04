from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .library_common import atomic_write_json, read_json_dict, safe_name
from .library_constants import USER_DATA_DIR

GENERATION_OUTPUT_SETTINGS_PATH = USER_DATA_DIR / 'generation_output_settings.json'
DEFAULT_OUTPUT_ROOT = USER_DATA_DIR / 'generated_outputs'
_DEFAULT_CATEGORY = 'Uncategorized'
_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
_INDEX_RE = re.compile(r'^(?P<prefix>.+?)_(?P<index>\d{2,8})_(?P<seed>\d+)')


def category_slug(name: str) -> str:
    text = safe_name(name or _DEFAULT_CATEGORY).strip().lower()
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^a-z0-9_\-]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text or 'uncategorized'


def category_display_name(name: str) -> str:
    text = safe_name(name or _DEFAULT_CATEGORY).strip()
    text = re.sub(r'\s+', ' ', text)
    return text or _DEFAULT_CATEGORY


def _dedupe_categories(values: Iterable[str] | None) -> List[str]:
    rows: List[str] = []
    seen = set()
    for value in values or []:
        display = category_display_name(str(value or ''))
        key = display.casefold()
        if not display or key in seen:
            continue
        seen.add(key)
        rows.append(display)
    if not rows:
        rows = [_DEFAULT_CATEGORY]
    return rows


def default_generation_output_settings() -> Dict[str, Any]:
    return {
        'output_root': str(DEFAULT_OUTPUT_ROOT),
        'categories': [_DEFAULT_CATEGORY],
        'selected_category': _DEFAULT_CATEGORY,
        'filename_padding': 4,
    }


def load_generation_output_settings() -> Dict[str, Any]:
    data = read_json_dict(GENERATION_OUTPUT_SETTINGS_PATH)
    defaults = default_generation_output_settings()
    output_root = str(data.get('output_root') or defaults['output_root']).strip() or defaults['output_root']
    categories = _dedupe_categories(data.get('categories') if isinstance(data.get('categories'), list) else defaults['categories'])
    selected = category_display_name(str(data.get('selected_category') or categories[0] or _DEFAULT_CATEGORY))
    if selected.casefold() not in {item.casefold() for item in categories}:
        categories.append(selected)
    padding = data.get('filename_padding', defaults['filename_padding'])
    try:
        padding = max(2, min(8, int(padding)))
    except Exception:
        padding = defaults['filename_padding']
    return {
        'output_root': output_root,
        'categories': categories,
        'selected_category': selected,
        'filename_padding': padding,
    }


def save_generation_output_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    current = load_generation_output_settings()
    output_root = str(settings.get('output_root') or current['output_root']).strip() or current['output_root']
    categories = _dedupe_categories(settings.get('categories') if isinstance(settings.get('categories'), list) else current['categories'])
    selected = category_display_name(str(settings.get('selected_category') or current['selected_category'] or categories[0]))
    if selected.casefold() not in {item.casefold() for item in categories}:
        categories.append(selected)
    try:
        padding = max(2, min(8, int(settings.get('filename_padding', current.get('filename_padding', 4)))))
    except Exception:
        padding = 4
    payload = {
        'output_root': output_root,
        'categories': categories,
        'selected_category': selected,
        'filename_padding': padding,
    }
    atomic_write_json(GENERATION_OUTPUT_SETTINGS_PATH, payload)
    return payload


def ensure_output_root(root: str | Path | None = None) -> Path:
    target = Path(str(root or load_generation_output_settings().get('output_root') or DEFAULT_OUTPUT_ROOT)).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_category_dir(output_root: str | Path, category_name: str) -> Path:
    root = ensure_output_root(output_root)
    category_dir = root / category_display_name(category_name)
    category_dir.mkdir(parents=True, exist_ok=True)
    return category_dir


def add_generation_category(name: str, *, output_root: str | None = None) -> Dict[str, Any]:
    settings = load_generation_output_settings()
    display = category_display_name(name)
    categories = list(settings.get('categories') or [])
    if display.casefold() not in {item.casefold() for item in categories}:
        categories.append(display)
    settings = save_generation_output_settings({
        **settings,
        'output_root': output_root or settings.get('output_root') or str(DEFAULT_OUTPUT_ROOT),
        'categories': categories,
        'selected_category': display,
    })
    ensure_category_dir(settings['output_root'], display)
    return settings


def next_category_index(category_dir: str | Path, prefix: str) -> int:
    folder = Path(category_dir)
    folder.mkdir(parents=True, exist_ok=True)
    max_index = 0
    lowered_prefix = str(prefix or '').strip().lower()
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        match = _INDEX_RE.match(path.stem)
        if not match:
            continue
        if match.group('prefix').strip().lower() != lowered_prefix:
            continue
        try:
            value = int(match.group('index'))
        except Exception:
            continue
        if value > max_index:
            max_index = value
    return max_index + 1
