from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .roleplay_foundation import (
    ROLEPLAY_UNIVERSES_DIR,
    ROLEPLAY_CHARACTERS_DIR,
    ROLEPLAY_SCENARIOS_DIR,
    ROLEPLAY_WORLDS_DIR,
    ROLEPLAY_REGIONS_DIR,
    ROLEPLAY_CITIES_DIR,
    ROLEPLAY_LOCATIONS_DIR,
    ROLEPLAY_ORGANIZATIONS_DIR,
    ROLEPLAY_ARTIFACTS_DIR,
    ROLEPLAY_RITUALS_DIR,
    ROLEPLAY_CYCLES_DIR,
    ROLEPLAY_CREATURES_DIR,
    ROLEPLAY_LEGENDS_DIR,
    ROLEPLAY_PACKS_DIR,
    universe_template,
    character_template,
    scenario_template,
    world_template,
    region_template,
    city_template,
    location_template,
    organization_template,
    artifact_template,
    ritual_template,
    cycle_template,
    creature_template,
    legend_template,
    pack_template,
    now_iso,
)
from .storage_io import atomic_write_json, read_json_object

KindDef = tuple[Path, Callable[..., dict[str, Any]], str]
KIND_MAP: dict[str, KindDef] = {
    'universe': (ROLEPLAY_UNIVERSES_DIR, universe_template, 'name'),
    'character': (ROLEPLAY_CHARACTERS_DIR, character_template, 'name'),
    'world': (ROLEPLAY_WORLDS_DIR, world_template, 'name'),
    'region': (ROLEPLAY_REGIONS_DIR, region_template, 'name'),
    'city': (ROLEPLAY_CITIES_DIR, city_template, 'name'),
    'location': (ROLEPLAY_LOCATIONS_DIR, location_template, 'name'),
    'organization': (ROLEPLAY_ORGANIZATIONS_DIR, organization_template, 'name'),
    'artifact': (ROLEPLAY_ARTIFACTS_DIR, artifact_template, 'name'),
    'ritual': (ROLEPLAY_RITUALS_DIR, ritual_template, 'name'),
    'cycle': (ROLEPLAY_CYCLES_DIR, cycle_template, 'name'),
    'creature': (ROLEPLAY_CREATURES_DIR, creature_template, 'name'),
    'legend': (ROLEPLAY_LEGENDS_DIR, legend_template, 'title'),
    'pack': (ROLEPLAY_PACKS_DIR, pack_template, 'title'),
    'scenario': (ROLEPLAY_SCENARIOS_DIR, scenario_template, 'title'),
}


def _path_for(kind: str, record_id: str) -> Path:
    directory, _factory, _title_key = KIND_MAP[kind]
    return directory / f'{record_id}.json'


def _read_json(path: Path) -> dict[str, Any] | None:
    return read_json_object(path, None)


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(path, payload)
    return payload


def list_records(kind: str) -> list[dict[str, Any]]:
    if kind not in KIND_MAP:
        return []
    directory, _factory, title_key = KIND_MAP[kind]
    directory.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob('*.json')):
        rec = _read_json(path)
        if not rec:
            continue
        title = str(rec.get(title_key) or '').strip() or str(rec.get('display_name') or '').strip() or 'Untitled'
        subtitle = ''
        if kind == 'character':
            subtitle = ' · '.join([p for p in [str(rec.get('role_tier') or '').strip(), str(rec.get('gender') or '').strip(), str(rec.get('pronouns') or '').strip()] if p])
        elif kind == 'world':
            subtitle = ' · '.join([p for p in [str(rec.get('realm_type') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'region':
            subtitle = ' · '.join([p for p in [str(rec.get('region_type') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'city':
            subtitle = ' · '.join([p for p in [str(rec.get('city_type') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'location':
            subtitle = ' · '.join([p for p in [str(rec.get('location_type') or '').strip(), str(rec.get('function_label') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'organization':
            subtitle = ' · '.join([p for p in [str(rec.get('group_type') or '').strip(), str(rec.get('reputation') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'artifact':
            subtitle = ' · '.join([p for p in [str(rec.get('item_type') or '').strip(), str(rec.get('rarity') or '').strip(), str(rec.get('state') or '').strip()] if p])
        elif kind == 'ritual':
            subtitle = ' · '.join([p for p in [str(rec.get('ritual_type') or '').strip(), str(rec.get('state') or '').strip(), str(rec.get('school') or '').strip()] if p])
        elif kind == 'cycle':
            subtitle = ' · '.join([p for p in [str(rec.get('cycle_type') or '').strip(), str(rec.get('scope_type') or '').strip(), str(rec.get('cadence') or '').strip()] if p])
        elif kind == 'creature':
            subtitle = ' · '.join([p for p in [str(rec.get('category') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'legend':
            subtitle = ' · '.join([p for p in [str(rec.get('scope') or '').strip(), str(rec.get('truth_status') or '').strip()] if p])
        elif kind == 'universe':
            subtitle = str(rec.get('summary') or '').strip()
        elif kind == 'pack':
            subtitle = ' · '.join([p for p in [str(rec.get('pack_type') or '').strip(), str(rec.get('summary') or '').strip()] if p])
        elif kind == 'scenario':
            subtitle = ' · '.join([p for p in [str(rec.get('location_label') or '').strip(), str(rec.get('premise') or '').strip()] if p])
        avatar = rec.get('avatar') or {}
        items.append({
            'id': rec.get('id', ''),
            'kind': kind,
            'title': title,
            'subtitle': subtitle,
            'updated_at': (rec.get('meta') or {}).get('updated_at', ''),
            'avatar_image_path': avatar.get('image_path', ''),
            'world_id': str(rec.get('world_id') or '').strip(),
            'region_id': str(rec.get('region_id') or '').strip(),
            'city_id': str(rec.get('city_id') or '').strip(),
            'universe_id': str(rec.get('universe_id') or '').strip(),
            'group_type': str(rec.get('group_type') or '').strip(),
            'category': str(rec.get('category') or '').strip(),
        })
    items.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    return items


def get_record(kind: str, record_id: str) -> dict[str, Any] | None:
    if kind not in KIND_MAP:
        return None
    clean_id = str(record_id or '').strip()
    if not clean_id:
        return None
    return _read_json(_path_for(kind, clean_id))


def _new_record(kind: str, label: str, fields: dict[str, Any]) -> dict[str, Any]:
    _directory, factory, _title_key = KIND_MAP[kind]
    if kind == 'universe':
        return factory(label)
    if kind == 'character':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('universe_id') or '').strip())
    if kind == 'world':
        return factory(label, str(fields.get('universe_id') or '').strip())
    if kind == 'region':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('parent_region_id') or '').strip())
    if kind == 'city':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip())
    if kind == 'location':
        return factory(label, str(fields.get('anchor_type') or 'world').strip(), str(fields.get('universe_id') or '').strip(), str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip(), str(fields.get('city_id') or '').strip(), str(fields.get('parent_location_id') or '').strip())
    if kind == 'organization':
        return factory(label, str(fields.get('universe_id') or '').strip(), str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip(), str(fields.get('city_id') or '').strip(), str(fields.get('base_location_id') or '').strip(), str(fields.get('parent_organization_id') or '').strip())
    if kind == 'artifact':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip(), str(fields.get('city_id') or '').strip(), str(fields.get('location_id') or '').strip())
    if kind == 'ritual':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip(), str(fields.get('location_id') or '').strip())
    if kind == 'cycle':
        return factory(label, str(fields.get('universe_id') or '').strip(), str(fields.get('world_id') or '').strip(), str(fields.get('region_id') or '').strip(), str(fields.get('location_id') or '').strip())
    if kind == 'creature':
        return factory(label, str(fields.get('world_id') or '').strip())
    if kind == 'legend':
        return factory(label, str(fields.get('universe_id') or '').strip(), str(fields.get('world_id') or '').strip())
    if kind == 'pack':
        return factory(label)
    if kind == 'scenario':
        return factory(label, str(fields.get('world_id') or '').strip(), str(fields.get('universe_id') or '').strip())
    return factory(label)


def save_record(kind: str, record_id: str = '', **fields: Any) -> dict[str, Any]:
    if kind not in KIND_MAP:
        raise ValueError('Unsupported library kind.')
    directory, _factory, title_key = KIND_MAP[kind]
    title_value = str(fields.get(title_key) or '').strip()
    if not title_value and kind == 'character':
        title_value = str(fields.get('display_name') or '').strip()
    if not title_value and kind == 'scenario':
        title_value = str(fields.get('premise') or '').strip()[:60].strip()
    if not title_value:
        raise ValueError(f'{title_key.replace("_", " ").title()} is required.')
    clean_id = str(record_id or '').strip()
    record = get_record(kind, clean_id) if clean_id else None
    if not record:
        record = _new_record(kind, title_value, fields)
    for key, value in fields.items():
        if key in {'id', 'kind', 'schema_version', 'meta'}:
            continue
        record[key] = value
    meta = record.get('meta') or {}
    if not meta.get('created_at'):
        meta['created_at'] = now_iso()
    meta['updated_at'] = now_iso()
    record['meta'] = meta
    directory.mkdir(parents=True, exist_ok=True)
    return _write_json(_path_for(kind, str(record.get('id') or '').strip()), record)


def import_record(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind not in KIND_MAP:
        raise ValueError('Unsupported library kind.')
    if not isinstance(payload, dict):
        raise ValueError('Imported record payload must be an object.')
    directory, _factory, title_key = KIND_MAP[kind]
    label = str(payload.get(title_key) or '').strip()
    if not label and kind == 'character':
        label = str(payload.get('display_name') or '').strip()
    if not label and kind == 'scenario':
        label = str(payload.get('premise') or '').strip()[:60].strip()
    if not label:
        raise ValueError(f'{title_key.replace("_", " ").title()} is required.')
    record_id = str(payload.get('id') or '').strip()
    existing = get_record(kind, record_id) if record_id else None
    record = dict(existing or {})
    if not record:
        record = _new_record(kind, label, payload)
    for key, value in payload.items():
        if key in {'kind'}:
            continue
        record[key] = value
    meta = record.get('meta') or {}
    if existing and not meta.get('created_at'):
        meta['created_at'] = (existing.get('meta') or {}).get('created_at') or now_iso()
    if not meta.get('created_at'):
        meta['created_at'] = now_iso()
    if meta.get('updated_at'):
        meta.setdefault('imported_original_updated_at', meta.get('updated_at'))
    meta['updated_at'] = now_iso()
    meta['imported_at'] = now_iso()
    record['meta'] = meta
    record['kind'] = kind
    directory.mkdir(parents=True, exist_ok=True)
    return _write_json(_path_for(kind, str(record.get('id') or '').strip()), record)


def delete_record(kind: str, record_id: str) -> bool:
    if kind not in KIND_MAP:
        return False
    clean_id = str(record_id or '').strip()
    if not clean_id:
        return False
    path = _path_for(kind, clean_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def library_state() -> dict[str, list[dict[str, Any]]]:
    return {
        'universes': list_records('universe'),
        'characters': list_records('character'),
        'worlds': list_records('world'),
        'regions': list_records('region'),
        'cities': list_records('city'),
        'locations': list_records('location'),
        'organizations': list_records('organization'),
        'artifacts': list_records('artifact'),
        'rituals': list_records('ritual'),
        'cycles': list_records('cycle'),
        'creatures': list_records('creature'),
        'legends': list_records('legend'),
        'packs': list_records('pack'),
        'scenarios': list_records('scenario'),
    }
