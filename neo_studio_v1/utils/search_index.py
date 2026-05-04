from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .characters import load_character_map
from .library_captions import caption_entries, get_caption_record
from .library_presets import get_caption_presets, get_prompt_presets
from .library_prompts import get_prompt_record, prompt_entries
from .output_metadata import iter_output_metadata_records
from .library_storage import iter_records
from .shared_data_paths import library_data_path
from .library_settings_store import get_library_root
from .library_common import read_json_dict
from .prompt_bundles import iter_bundle_records


@dataclass
class SearchFilters:
    type_filter: str = ''
    category: str = ''
    model: str = ''
    style: str = ''
    lora: str = ''
    character: str = ''


def parse_search_query(query: str) -> Tuple[str, SearchFilters]:
    filters = SearchFilters()
    remaining: List[str] = []
    for token in (query or '').split():
        lowered = token.lower()
        if lowered.startswith('type:'):
            filters.type_filter = lowered.split(':', 1)[1].strip()
        elif lowered.startswith('category:'):
            filters.category = token.split(':', 1)[1].strip()
        elif lowered.startswith('model:'):
            filters.model = token.split(':', 1)[1].strip()
        elif lowered.startswith('style:'):
            filters.style = token.split(':', 1)[1].strip()
        elif lowered.startswith('lora:'):
            filters.lora = token.split(':', 1)[1].strip()
        elif lowered.startswith('character:'):
            filters.character = token.split(':', 1)[1].strip()
        else:
            remaining.append(token)
    return ' '.join(remaining).strip(), filters


def _registry_loras() -> List[Dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    vault_db_path = library_data_path('vault_db.json', legacy_rel='vault_db.json', default_json={'tags': [], 'packs': [], 'mapsets': [], 'loras': []})
    data = read_json_dict(vault_db_path)
    rows = data.get('loras') or []
    return [row for row in rows if isinstance(row, dict)]


def _text_score(query: str, haystack: str) -> int:
    query = (query or '').strip().lower()
    haystack = (haystack or '').lower()
    if not haystack:
        return 0
    if not query:
        return 1
    score = 0
    for token in [x for x in query.split() if x]:
        if token in haystack:
            score += 3
        if haystack.startswith(token):
            score += 2
    if query and query in haystack:
        score += 8
    return score


def _passes_common_filters(item: Dict[str, Any], filters: SearchFilters) -> bool:
    if filters.category and filters.category.lower() not in str(item.get('category') or '').lower():
        return False
    if filters.model and filters.model.lower() not in str(item.get('model') or '').lower():
        return False
    if filters.style and filters.style.lower() not in str(item.get('style') or item.get('prompt_style') or '').lower():
        return False
    if filters.character and filters.character.lower() not in str(item.get('character_name') or item.get('name') or '').lower():
        return False
    return True


def global_search(query: str, limit: int = 80) -> Dict[str, List[Dict[str, Any]]]:
    query_text, filters = parse_search_query(query)
    type_filter = (filters.type_filter or '').strip().lower()
    results: Dict[str, List[Dict[str, Any]]] = {
        'prompts': [],
        'captions': [],
        'characters': [],
        'presets': [],
        'loras': [],
        'metadata_records': [],
        'bundles': [],
    }

    def type_allowed(name: str) -> bool:
        return not type_filter or type_filter in {name, name.rstrip('s')}

    if type_allowed('prompts'):
        for rec in iter_records('prompt'):
            item = {
                'id': rec.get('id') or '',
                'name': rec.get('name') or '(untitled)',
                'category': rec.get('category') or 'uncategorized',
                'model': rec.get('model') or '',
                'style': rec.get('style') or '',
                'snippet': (rec.get('prompt') or '')[:220],
                'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
                'kind': 'prompt',
            }
            if not _passes_common_filters(item, filters):
                continue
            haystack = ' '.join([item['name'], item['category'], item['model'], item['style'], rec.get('prompt') or '', rec.get('notes') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['prompts'].append(item)

    if type_allowed('captions'):
        for rec in iter_records('caption'):
            lora_blob = ' '.join(str(x.get('name') or '') for x in (rec.get('settings') or {}).get('loras', []))
            item = {
                'id': rec.get('id') or '',
                'name': rec.get('name') or '(untitled)',
                'category': rec.get('category') or 'uncategorized',
                'model': rec.get('model') or '',
                'prompt_style': rec.get('prompt_style') or '',
                'snippet': (rec.get('caption') or '')[:220],
                'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
                'kind': 'caption',
            }
            if not _passes_common_filters(item, filters):
                continue
            if filters.lora and filters.lora.lower() not in lora_blob.lower():
                continue
            haystack = ' '.join([item['name'], item['category'], item['model'], item['prompt_style'], rec.get('caption') or '', rec.get('notes') or '', lora_blob])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['captions'].append(item)

    if type_allowed('characters'):
        for name, content in load_character_map().items():
            item = {
                'id': name,
                'name': name,
                'character_name': name,
                'snippet': content[:220],
                'kind': 'character',
            }
            if not _passes_common_filters(item, filters):
                continue
            haystack = f'{name} {content}'
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['characters'].append(item)

    if type_allowed('presets'):
        prompt_presets = get_prompt_presets()
        for name, preset in prompt_presets.items():
            item = {
                'id': f'prompt:{name}',
                'name': name,
                'preset_kind': 'prompt',
                'style': preset.get('style') or '',
                'snippet': (preset.get('custom_instructions') or '')[:220],
                'kind': 'preset',
            }
            if not _passes_common_filters(item, filters):
                continue
            haystack = ' '.join([name, item['style'], preset.get('custom_instructions') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['presets'].append(item)
        caption_presets = get_caption_presets()
        for name, preset in caption_presets.items():
            item = {
                'id': f'caption:{name}',
                'name': name,
                'preset_kind': 'caption',
                'style': preset.get('prompt_style') or '',
                'snippet': (preset.get('custom_prompt') or '')[:220],
                'kind': 'preset',
            }
            if not _passes_common_filters(item, filters):
                continue
            haystack = ' '.join([name, item['style'], preset.get('custom_prompt') or '', preset.get('caption_length') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['presets'].append(item)

    if type_allowed('loras'):
        for row in _registry_loras():
            triggers = ', '.join(row.get('triggers') or [])
            keywords = ', '.join(row.get('keywords') or [])
            item = {
                'id': row.get('id') or row.get('name') or '',
                'name': row.get('name') or '(unnamed)',
                'category': row.get('category') or '',
                'style': row.get('kind') or 'lora',
                'snippet': ', '.join(x for x in [triggers, keywords, row.get('notes') or ''] if x)[:220],
                'default_strength': row.get('default_strength'),
                'triggers': row.get('triggers') or [],
                'kind': 'lora',
            }
            if not _passes_common_filters(item, filters):
                continue
            if filters.lora and filters.lora.lower() not in item['name'].lower():
                continue
            haystack = ' '.join([item['name'], item['category'], triggers, keywords, row.get('notes') or '', row.get('file') or '', row.get('rel') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['loras'].append(item)

    if type_allowed('bundles'):
        for rec in iter_bundle_records():
            lora_blob = ' '.join(rec.get('loras') or [])
            item = {
                'id': rec.get('id') or '',
                'name': rec.get('name') or '(untitled)',
                'model': rec.get('model_default') or '',
                'style': rec.get('checkpoint_default') or '',
                'snippet': (' / '.join([rec.get('positive_prompt') or '', rec.get('style_notes') or '']))[:220],
                'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
                'kind': 'bundle',
            }
            if not _passes_common_filters(item, filters):
                continue
            if filters.lora and filters.lora.lower() not in lora_blob.lower():
                continue
            if filters.character and filters.character.lower() not in str(rec.get('character_name') or '').lower():
                continue
            haystack = ' '.join([item['name'], item['model'], item['style'], rec.get('positive_prompt') or '', rec.get('negative_prompt') or '', rec.get('style_notes') or '', lora_blob, rec.get('character_name') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['bundles'].append(item)

    if type_allowed('metadata_records'):
        for rec in iter_output_metadata_records():
            data = rec.get('data') or {}
            lora_blob = ' '.join(str(x.get('name') or '') for x in (data.get('loras') or []))
            item = {
                'id': rec.get('id') or '',
                'name': rec.get('name') or '(unnamed)',
                'model': (data.get('settings') or {}).get('Model') or '',
                'snippet': (data.get('positive_prompt') or '')[:220],
                'updated_at': rec.get('updated_at') or rec.get('created_at') or '',
                'kind': 'metadata_record',
            }
            if not _passes_common_filters(item, filters):
                continue
            if filters.lora and filters.lora.lower() not in lora_blob.lower():
                continue
            haystack = ' '.join([item['name'], item['model'], data.get('positive_prompt') or '', data.get('negative_prompt') or '', lora_blob, rec.get('notes') or '', rec.get('source_filename') or ''])
            score = _text_score(query_text, haystack)
            if score:
                item['score'] = score
                results['metadata_records'].append(item)

    for key in results:
        results[key] = sorted(results[key], key=lambda row: (-(int(row.get('score') or 0)), str(row.get('updated_at') or '')), reverse=False)[:limit]
    return results
