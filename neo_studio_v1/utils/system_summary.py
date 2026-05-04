from __future__ import annotations

from .characters import load_character_map
from .library_storage import iter_records
from .library_presets import get_caption_presets, get_prompt_presets
from .output_metadata import iter_output_metadata_records
from .prompt_bundles import bundle_entries


def _sort_recent(rows, limit=8):
    def key(row):
        return str(row.get('updated_at') or row.get('created_at') or '')
    rows = sorted(rows, key=key, reverse=True)
    return rows[:limit]


def _recent_items(limit: int = 8):
    prompts = _sort_recent([
        {
            'kind': 'prompt',
            'id': rec.get('id') or '',
            'name': rec.get('name') or '(untitled)',
            'category': rec.get('category') or 'uncategorized',
            'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
        }
        for rec in iter_records('prompt')
    ], limit)
    captions = _sort_recent([
        {
            'kind': 'caption',
            'id': rec.get('id') or '',
            'name': rec.get('name') or '(untitled)',
            'category': rec.get('category') or 'uncategorized',
            'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
        }
        for rec in iter_records('caption')
    ], limit)
    chars = _sort_recent([
        {
            'kind': 'character',
            'id': name,
            'name': name,
            'updated_at': '',
        }
        for name in (load_character_map() or {}).keys()
    ], limit)
    metadata = _sort_recent([
        {
            'kind': 'metadata',
            'id': rec.get('id') or '',
            'name': rec.get('name') or '(unnamed)',
            'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
        }
        for rec in iter_output_metadata_records()
    ], limit)
    bundles = _sort_recent([
        {
            'kind': 'bundle',
            'id': rec.get('id') or '',
            'name': rec.get('name') or '(untitled)',
            'updated_at': rec.get('updated_at') or '',
            'character_name': rec.get('character_name') or '',
            'model_default': rec.get('model_default') or '',
        }
        for rec in bundle_entries()
    ], limit)
    prompt_presets = _sort_recent([
        {
            'kind': 'prompt_preset',
            'name': name,
            'favorite': bool(preset.get('favorite')),
            'group': preset.get('group') or '',
            'updated_at': preset.get('last_used') or '',
            'usage_count': preset.get('usage_count') or 0,
        }
        for name, preset in get_prompt_presets().items()
    ], limit)
    caption_presets = _sort_recent([
        {
            'kind': 'caption_preset',
            'name': name,
            'favorite': bool(preset.get('favorite')),
            'group': preset.get('group') or '',
            'updated_at': preset.get('last_used') or '',
            'usage_count': preset.get('usage_count') or 0,
        }
        for name, preset in get_caption_presets().items()
    ], limit)
    return {
        'prompts': prompts,
        'captions': captions,
        'characters': chars,
        'metadata': metadata,
        'bundles': bundles,
        'prompt_presets': prompt_presets,
        'caption_presets': caption_presets,
    }


def get_recent_totals(limit: int = 8) -> dict[str, int]:
    items = _recent_items(limit=max(1, min(20, int(limit or 8))))
    return {key: len(value) for key, value in items.items()}
