from __future__ import annotations

import copy
from typing import Any

from .roleplay_foundation import ROLEPLAY_SCHEMA_VERSION, slugify
from .roleplay_library_imports import KIND_LABELS, TITLE_KEY_BY_KIND, _normalize_kind, _template_for_kind
from .roleplay_library_store import get_record

EXAMPLE_LABELS = {
    'legend': 'Your Legend Title',
    'universe': 'Your Universe Name',
    'world': 'Your World Name',
    'region': 'Your Region Name',
    'city': 'Your City Name',
    'location': 'Your Location Name',
    'organization': 'Your Organization Name',
    'character': 'Your Character Name',
    'artifact': 'Your Artifact Name',
    'ritual': 'Your Ritual Name',
    'cycle': 'Your Cycle Name',
    'creature': 'Your Creature Name',
    'pack': 'Your Pack Title',
    'scenario': 'Your Scenario Title',
}


def _clean_kind(kind: str) -> str:
    clean = _normalize_kind(kind)
    if clean not in TITLE_KEY_BY_KIND:
        raise ValueError('Choose a supported library kind first.')
    return clean



def build_template_payload(kind: str) -> dict[str, Any]:
    clean = _clean_kind(kind)
    payload = copy.deepcopy(_template_for_kind(clean))
    title_key = TITLE_KEY_BY_KIND[clean]
    payload['schema_version'] = ROLEPLAY_SCHEMA_VERSION
    payload['kind'] = clean
    payload['id'] = f'{clean}_your-id-here'
    payload[title_key] = EXAMPLE_LABELS.get(clean, '')
    if clean == 'character':
        payload['display_name'] = payload['name']
    if clean == 'location':
        payload['display_name'] = payload['name']
    if clean == 'organization':
        payload['display_name'] = payload['name']
    payload['meta'] = {
        'created_at': 'YYYY-MM-DDTHH:MM:SSZ',
        'updated_at': 'YYYY-MM-DDTHH:MM:SSZ',
        'status': 'active',
    }
    return payload



def build_record_export_payload(kind: str, record_id: str) -> dict[str, Any]:
    clean = _clean_kind(kind)
    record = get_record(clean, record_id)
    if not record:
        raise ValueError('Library record not found.')
    return copy.deepcopy(record)



def export_filename(kind: str, record: dict[str, Any] | None = None, *, template: bool = False) -> str:
    clean = _clean_kind(kind)
    if template:
        return f'roleplay_{clean}_template.json'
    label = ''
    if isinstance(record, dict):
        label = str(record.get('display_name') or record.get('name') or record.get('title') or '').strip()
    slug = slugify(label, clean)
    return f'roleplay_{clean}_{slug}.json'
