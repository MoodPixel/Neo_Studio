from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .roleplay_foundation import (
    ROLEPLAY_IMPORTS_DIR,
    ROLEPLAY_SCHEMA_VERSION,
    now_iso,
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
)
from .roleplay_library_store import KIND_MAP, get_record, import_record
from .storage_io import atomic_write_json, read_json_object

TITLE_KEY_BY_KIND = {
    'universe': 'name',
    'character': 'name',
    'world': 'name',
    'region': 'name',
    'city': 'name',
    'location': 'name',
    'organization': 'name',
    'artifact': 'name',
    'ritual': 'name',
    'cycle': 'name',
    'creature': 'name',
    'legend': 'title',
    'pack': 'title',
    'scenario': 'title',
}

KIND_LABELS = {
    'legend': 'Legends',
    'universe': 'Universes',
    'world': 'Worlds',
    'region': 'Kingdoms / Regions',
    'city': 'Cities / Settlements',
    'location': 'Locations',
    'organization': 'Organizations / Factions',
    'character': 'Characters',
    'artifact': 'Weapons / Artifacts',
    'ritual': 'Spells / Rituals / Techniques',
    'cycle': 'Cycles / Conditions / Systems',
    'creature': 'Creatures / Animals / Fauna',
    'pack': 'Packs',
    'scenario': 'Scenarios',
}

SECTION_SPLIT_RE = re.compile(r'\n(?=#+\s+|[A-Z][A-Za-z0-9 /&()_\-]{1,60}:\s*(?:\n|$))')
KV_RE = re.compile(r'^([A-Za-z][A-Za-z0-9 /&()_\-]{1,60}):\s*(.+)$')


def _template_for_kind(kind: str, label: str = '', raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = raw or {}
    if kind == 'universe':
        return universe_template(label)
    if kind == 'character':
        return character_template(label, str(raw.get('world_id') or raw.get('current_world_id') or raw.get('origin_world_id') or '').strip(), str(raw.get('universe_id') or '').strip())
    if kind == 'world':
        return world_template(label, str(raw.get('universe_id') or '').strip())
    if kind == 'region':
        return region_template(label, str(raw.get('world_id') or '').strip(), str(raw.get('parent_region_id') or '').strip())
    if kind == 'city':
        return city_template(label, str(raw.get('world_id') or '').strip(), str(raw.get('region_id') or '').strip())
    if kind == 'location':
        return location_template(
            label,
            str(raw.get('anchor_type') or 'world').strip(),
            str(raw.get('universe_id') or '').strip(),
            str(raw.get('world_id') or '').strip(),
            str(raw.get('region_id') or '').strip(),
            str(raw.get('city_id') or '').strip(),
            str(raw.get('parent_location_id') or '').strip(),
        )
    if kind == 'organization':
        return organization_template(
            label,
            str(raw.get('universe_id') or '').strip(),
            str(raw.get('world_id') or '').strip(),
            str(raw.get('region_id') or '').strip(),
            str(raw.get('city_id') or '').strip(),
            str(raw.get('base_location_id') or '').strip(),
            str(raw.get('parent_organization_id') or '').strip(),
        )
    if kind == 'artifact':
        return artifact_template(label, str(raw.get('world_id') or '').strip(), str(raw.get('region_id') or '').strip(), str(raw.get('city_id') or '').strip(), str(raw.get('location_id') or '').strip())
    if kind == 'ritual':
        return ritual_template(label, str(raw.get('world_id') or '').strip(), str(raw.get('region_id') or '').strip(), str(raw.get('location_id') or '').strip())
    if kind == 'cycle':
        return cycle_template(
            label,
            str(raw.get('universe_id') or '').strip(),
            str(raw.get('world_id') or '').strip(),
            str(raw.get('region_id') or '').strip(),
            str(raw.get('location_id') or '').strip(),
        )
    if kind == 'creature':
        return creature_template(label, str(raw.get('world_id') or '').strip())
    if kind == 'legend':
        return legend_template(label, str(raw.get('universe_id') or '').strip(), str(raw.get('world_id') or '').strip())
    if kind == 'pack':
        return pack_template(label)
    if kind == 'scenario':
        return scenario_template(label, str(raw.get('world_id') or '').strip(), str(raw.get('universe_id') or '').strip())
    raise ValueError('Unsupported library kind.')


def _preview_path(preview_id: str) -> Path:
    return ROLEPLAY_IMPORTS_DIR / f'{preview_id}.json'


def _write_preview(payload: dict[str, Any]) -> None:
    ROLEPLAY_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_preview_path(str(payload.get('preview_id') or '').strip()), payload)


def _read_preview(preview_id: str) -> dict[str, Any]:
    path = _preview_path(preview_id)
    if not path.exists():
        raise ValueError('Import preview expired or was not found.')
    data = read_json_object(path, None)
    if not isinstance(data, dict):
        raise ValueError('Import preview is invalid.')
    return data


def _clean_text(value: Any) -> str:
    return str(value or '').replace('\r\n', '\n').strip()


def _safe_name(filename: str) -> str:
    clean = re.sub(r'[^A-Za-z0-9._\-]+', '_', str(filename or '').strip())
    return clean[:120] or 'import'


def _normalize_kind(value: Any) -> str:
    clean = re.sub(r'[^a-z]+', '', str(value or '').strip().lower())
    alias_map = {
        'legend': 'legend',
        'legends': 'legend',
        'universe': 'universe',
        'universes': 'universe',
        'world': 'world',
        'worlds': 'world',
        'kingdom': 'region',
        'kingdoms': 'region',
        'region': 'region',
        'regions': 'region',
        'city': 'city',
        'cities': 'city',
        'settlement': 'city',
        'settlements': 'city',
        'location': 'location',
        'locations': 'location',
        'organization': 'organization',
        'organizations': 'organization',
        'faction': 'organization',
        'factions': 'organization',
        'guild': 'organization',
        'guilds': 'organization',
        'cult': 'organization',
        'cults': 'organization',
        'circle': 'organization',
        'circles': 'organization',
        'character': 'character',
        'characters': 'character',
        'artifact': 'artifact',
        'artifacts': 'artifact',
        'weapon': 'artifact',
        'weapons': 'artifact',
        'ritual': 'ritual',
        'rituals': 'ritual',
        'spell': 'ritual',
        'spells': 'ritual',
        'technique': 'ritual',
        'techniques': 'ritual',
        'cycle': 'cycle',
        'cycles': 'cycle',
        'condition': 'cycle',
        'conditions': 'cycle',
        'system': 'cycle',
        'systems': 'cycle',
        'creature': 'creature',
        'creatures': 'creature',
        'animal': 'creature',
        'animals': 'creature',
        'fauna': 'creature',
        'pack': 'pack',
        'packs': 'pack',
        'scenario': 'scenario',
        'scenarios': 'scenario',
    }
    return alias_map.get(clean, '')


def _split_inline_list(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    if '\n' in text:
        items = []
        for line in text.splitlines():
            cleaned = re.sub(r'^\s*[-*+]\s*', '', line).strip()
            if cleaned:
                items.append(cleaned)
        return items
    return [item for item in [part.strip() for part in re.split(r'[,;|]', text)] if item]


def _normalise_meta(raw_meta: Any) -> dict[str, Any]:
    base = raw_meta if isinstance(raw_meta, dict) else {}
    meta = copy.deepcopy(base)
    meta.setdefault('created_at', now_iso())
    meta.setdefault('status', 'active')
    meta['imported_at'] = now_iso()
    return meta


def _coerce_record(kind: str, raw: dict[str, Any], *, preserve_id: bool = True) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(raw, dict):
        raise ValueError('Imported record must be a JSON object.')
    detected_kind = _normalize_kind(raw.get('kind')) or kind
    if detected_kind != kind:
        raise ValueError(f'Imported record kind mismatch. Expected {kind}, got {detected_kind or "unknown"}.')
    title_key = TITLE_KEY_BY_KIND[kind]
    label = _clean_text(raw.get(title_key))
    if not label and kind == 'character':
        label = _clean_text(raw.get('display_name'))
    if not label and kind == 'scenario':
        label = _clean_text(raw.get('premise'))[:60].strip()
    if not label:
        raise ValueError(f'Imported {KIND_LABELS.get(kind, kind)} record is missing {title_key.replace("_", " ")}.')
    base = _template_for_kind(kind, label, raw)
    record = copy.deepcopy(base)
    warnings: list[str] = []
    for key, value in raw.items():
        if key == 'kind':
            continue
        if key in {'schema_version'}:
            continue
        if key in {'meta'}:
            record['meta'] = _normalise_meta(value)
            continue
        if key == 'id' and preserve_id:
            clean_id = _clean_text(value)
            if clean_id:
                record['id'] = clean_id
            continue
        record[key] = copy.deepcopy(value)
    record['kind'] = kind
    record['schema_version'] = ROLEPLAY_SCHEMA_VERSION
    if title_key == 'name':
        record['name'] = label
        if kind == 'character' and not _clean_text(record.get('display_name')):
            record['display_name'] = label
        if kind == 'location' and not _clean_text(record.get('display_name')):
            record['display_name'] = label
        if kind == 'organization' and not _clean_text(record.get('display_name')):
            record['display_name'] = label
    else:
        record['title'] = label
    record['meta'] = _normalise_meta(record.get('meta'))
    if get_record(kind, _clean_text(record.get('id'))):
        warnings.append(f'Existing {kind} with ID {record.get("id")} will be updated on commit.')
    return record, warnings


def _extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    source = text.lstrip('\ufeff')
    if not source.startswith('---\n'):
        return {}, text
    end = source.find('\n---\n', 4)
    if end == -1:
        return {}, text
    block = source[4:end]
    remainder = source[end + 5 :]
    data: dict[str, Any] = {}
    for line in block.splitlines():
        match = KV_RE.match(line.strip())
        if not match:
            continue
        data[_normalize_label(match.group(1))] = match.group(2).strip()
    return data, remainder


def _normalize_label(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')


def _parse_markdown(text: str) -> dict[str, Any]:
    frontmatter, body = _extract_frontmatter(text)
    sections: dict[str, str] = {}
    kv: dict[str, str] = {}
    first_heading = ''
    current_key = 'body'
    buffer: list[str] = []

    def flush() -> None:
        if current_key not in sections:
            sections[current_key] = ''
        chunk = '\n'.join(buffer).strip()
        if not chunk:
            return
        sections[current_key] = f"{sections[current_key]}\n{chunk}".strip() if sections[current_key] else chunk

    for raw_line in body.replace('\r\n', '\n').split('\n'):
        line = raw_line.rstrip()
        heading_match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line.strip())
        naked_heading = re.match(r'^([A-Z][A-Za-z0-9 /&()_\-]{1,60}):\s*$', line.strip())
        kv_match = KV_RE.match(line.strip())
        if heading_match or naked_heading:
            flush()
            buffer = []
            title = (heading_match.group(1) if heading_match else naked_heading.group(1)).strip()
            if not first_heading:
                first_heading = title
            current_key = _normalize_label(title)
            continue
        if kv_match:
            key = _normalize_label(kv_match.group(1))
            value = kv_match.group(2).strip()
            kv[key] = value
        buffer.append(line)
    flush()
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', sections.get('body', '')) if p.strip()]
    return {
        'frontmatter': frontmatter,
        'sections': sections,
        'kv': kv,
        'first_heading': first_heading,
        'paragraphs': paragraphs,
        'text': body.strip(),
    }


def _pick_markdown_value(parsed: dict[str, Any], *keys: str, multiline: bool = True) -> str:
    frontmatter = parsed.get('frontmatter') or {}
    kv = parsed.get('kv') or {}
    sections = parsed.get('sections') or {}
    for key in keys:
        norm = _normalize_label(key)
        value = frontmatter.get(norm)
        if value:
            return _clean_text(value)
        value = kv.get(norm)
        if value:
            return _clean_text(value)
        value = sections.get(norm)
        if value:
            return _clean_text(value)
    if multiline and parsed.get('paragraphs'):
        return _clean_text(parsed['paragraphs'][0])
    return ''


def _pick_markdown_list(parsed: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = _pick_markdown_value(parsed, key, multiline=True)
        items = _split_inline_list(value)
        if items:
            return items
    return []


def _cast_from_markdown(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    cast_text = _pick_markdown_value(parsed, 'cast', 'characters', multiline=True)
    if not cast_text:
        return []
    items: list[dict[str, Any]] = []
    for line in cast_text.splitlines():
        clean = re.sub(r'^\s*[-*+]\s*', '', line).strip()
        if not clean:
            continue
        name, _, role = clean.partition(' - ')
        items.append({
            'character_id': '',
            'character_name': name.strip(),
            'scene_role': role.strip() or 'supporting',
            'presence': 'on_scene',
            'notes': '',
        })
    return items


def _record_from_markdown(kind: str, text: str) -> tuple[dict[str, Any], list[str]]:
    parsed = _parse_markdown(text)
    title_key = TITLE_KEY_BY_KIND[kind]
    lead_title = _pick_markdown_value(parsed, title_key, 'title', 'name', 'heading', multiline=False) or _clean_text(parsed.get('first_heading'))
    if not lead_title:
        raise ValueError(f'{KIND_LABELS.get(kind, kind)} import needs a heading or {title_key.replace("_", " ")} line.')
    raw: dict[str, Any] = {}
    if title_key == 'name':
        raw['name'] = lead_title
    else:
        raw['title'] = lead_title

    if kind == 'character':
        raw.update({
            'display_name': _pick_markdown_value(parsed, 'display_name', 'display name', multiline=False) or lead_title,
            'summary': _pick_markdown_value(parsed, 'summary', 'overview', 'description'),
            'gender': _pick_markdown_value(parsed, 'gender', multiline=False),
            'pronouns': _pick_markdown_value(parsed, 'pronouns', multiline=False),
            'role_tier': _pick_markdown_value(parsed, 'role_tier', 'role', 'story_role', multiline=False) or 'main',
            'species': _pick_markdown_value(parsed, 'species', 'race', multiline=False),
            'designation': _pick_markdown_value(parsed, 'designation', multiline=False),
            'occupation': _pick_markdown_value(parsed, 'occupation', 'job', multiline=False),
            'appearance': _pick_markdown_value(parsed, 'appearance', 'looks'),
            'personality': _pick_markdown_value(parsed, 'personality', 'temperament'),
            'speech_style': _pick_markdown_value(parsed, 'speech_style', 'speech', 'voice'),
            'relationship_notes': _pick_markdown_value(parsed, 'relationship_notes', 'relationships'),
            'affiliations': _pick_markdown_value(parsed, 'affiliations', 'factions'),
            'hobbies': _pick_markdown_value(parsed, 'hobbies', 'pursuits'),
            'student_details': _pick_markdown_value(parsed, 'student_details', 'student'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
            'story_hooks': [{'type': 'hook', 'title': item, 'notes': ''} for item in _pick_markdown_list(parsed, 'story_hooks', 'hooks')],
        })
    elif kind == 'world':
        raw.update({
            'summary': _pick_markdown_value(parsed, 'summary', 'overview', 'logline'),
            'realm_type': _pick_markdown_value(parsed, 'realm_type', 'realm', 'world_type', multiline=False),
            'calendar_notes': _pick_markdown_value(parsed, 'calendar_notes', 'calendar', 'timekeeping'),
            'lore': _pick_markdown_value(parsed, 'lore', 'history'),
            'rules': _pick_markdown_value(parsed, 'rules', 'laws', 'magic_rules'),
            'geography_notes': _pick_markdown_value(parsed, 'geography_notes', 'geography'),
            'society_notes': _pick_markdown_value(parsed, 'society_notes', 'society', 'power'),
            'faith_notes': _pick_markdown_value(parsed, 'faith_notes', 'faith', 'law_magic'),
            'people_notes': _pick_markdown_value(parsed, 'people_notes', 'people', 'peoples_creatures_hidden'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'organization':
        raw.update({
            'display_name': _pick_markdown_value(parsed, 'display_name', 'display name', multiline=False) or lead_title,
            'group_type': _pick_markdown_value(parsed, 'group_type', 'type', multiline=False) or 'organization',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview', 'description'),
            'leadership': _pick_markdown_value(parsed, 'leadership', 'leaders'),
            'beliefs': _pick_markdown_value(parsed, 'beliefs', 'doctrine', 'values'),
            'goals': _pick_markdown_value(parsed, 'goals', 'aims'),
            'reputation': _pick_markdown_value(parsed, 'reputation', multiline=False),
            'resources': _pick_markdown_value(parsed, 'resources', 'assets'),
            'membership_rules': _pick_markdown_value(parsed, 'membership_rules', 'membership', 'membership rules'),
            'public_face': _pick_markdown_value(parsed, 'public_face', 'public face'),
            'hidden_truth': _pick_markdown_value(parsed, 'hidden_truth', 'hidden truth', 'secret'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
            'ally_organization_names': _pick_markdown_list(parsed, 'allies', 'ally organizations'),
            'rival_organization_names': _pick_markdown_list(parsed, 'rivals', 'enemy organizations'),
        })
    elif kind == 'region':
        raw.update({
            'region_type': _pick_markdown_value(parsed, 'region_type', 'type', multiline=False) or 'kingdom',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'city':
        raw.update({
            'city_type': _pick_markdown_value(parsed, 'city_type', 'type', multiline=False) or 'city',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'access_notes': _pick_markdown_value(parsed, 'access_notes', 'access'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'location':
        raw.update({
            'display_name': _pick_markdown_value(parsed, 'display_name', 'display name', multiline=False) or lead_title,
            'function_label': _pick_markdown_value(parsed, 'function_label', 'function', multiline=False),
            'location_type': _pick_markdown_value(parsed, 'location_type', 'type', multiline=False) or 'building',
            'anchor_type': _pick_markdown_value(parsed, 'anchor_type', 'anchor', multiline=False) or 'world',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'atmosphere': _pick_markdown_value(parsed, 'atmosphere', 'mood'),
            'scene_uses': _pick_markdown_list(parsed, 'scene_uses', 'scene uses', 'uses'),
            'access_notes': _pick_markdown_value(parsed, 'access_notes', 'access'),
            'hazards': _pick_markdown_value(parsed, 'hazards', 'dangers'),
            'rules': _pick_markdown_value(parsed, 'rules', 'house_rules'),
            'public_notes': _pick_markdown_value(parsed, 'public_notes', 'public'),
            'hidden_truth': _pick_markdown_value(parsed, 'hidden_truth', 'hidden', 'secret'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'artifact':
        raw.update({
            'item_type': _pick_markdown_value(parsed, 'item_type', 'type', multiline=False) or 'weapon',
            'rarity': _pick_markdown_value(parsed, 'rarity', 'tier', multiline=False) or 'normal',
            'state': _pick_markdown_value(parsed, 'state', multiline=False) or 'active',
            'source_tradition': _pick_markdown_value(parsed, 'source_tradition', 'source', 'tradition', multiline=False),
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'effects': _pick_markdown_value(parsed, 'effects', 'abilities'),
            'costs': _pick_markdown_value(parsed, 'costs', 'drawbacks'),
            'activation': _pick_markdown_value(parsed, 'activation', 'trigger'),
            'lawful_status': _pick_markdown_value(parsed, 'lawful_status', 'lawful', multiline=False),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'ritual':
        raw.update({
            'ritual_type': _pick_markdown_value(parsed, 'ritual_type', 'type', multiline=False) or 'ritual',
            'school': _pick_markdown_value(parsed, 'school', 'tradition', multiline=False),
            'state': _pick_markdown_value(parsed, 'state', multiline=False) or 'known',
            'effect_summary': _pick_markdown_value(parsed, 'effect_summary', 'effects', 'summary'),
            'requirements': _pick_markdown_value(parsed, 'requirements', 'materials'),
            'risks': _pick_markdown_value(parsed, 'risks', 'costs'),
            'lawful_status': _pick_markdown_value(parsed, 'lawful_status', 'lawful', multiline=False),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'cycle':
        raw.update({
            'cycle_type': _pick_markdown_value(parsed, 'cycle_type', 'type', multiline=False) or 'celestial',
            'scope_type': _pick_markdown_value(parsed, 'scope_type', 'scope', multiline=False) or 'world',
            'affected_species': _pick_markdown_value(parsed, 'affected_species', 'species', multiline=False),
            'affected_designation': _pick_markdown_value(parsed, 'affected_designation', 'designation', multiline=False),
            'cadence': _pick_markdown_value(parsed, 'cadence', 'frequency', multiline=False),
            'trigger': _pick_markdown_value(parsed, 'trigger', multiline=False),
            'stages': _pick_markdown_value(parsed, 'stages'),
            'effects': _pick_markdown_value(parsed, 'effects'),
            'safeguards': _pick_markdown_value(parsed, 'safeguards', 'protections'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'creature':
        raw.update({
            'category': _pick_markdown_value(parsed, 'category', 'type', multiline=False) or 'creature',
            'sentience': _pick_markdown_value(parsed, 'sentience', multiline=False) or 'unknown',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'universe':
        raw.update({
            'summary': _pick_markdown_value(parsed, 'summary', 'overview', 'logline'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'legend':
        raw.update({
            'scope': _pick_markdown_value(parsed, 'scope', multiline=False) or 'world',
            'legend_type': _pick_markdown_value(parsed, 'legend_type', 'type', multiline=False) or 'myth',
            'truth_status': _pick_markdown_value(parsed, 'truth_status', 'truth', multiline=False) or 'disputed',
            'public_version': _pick_markdown_value(parsed, 'public_version', 'public'),
            'hidden_version': _pick_markdown_value(parsed, 'hidden_version', 'hidden'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'pack':
        raw.update({
            'pack_type': _pick_markdown_value(parsed, 'pack_type', 'type', multiline=False) or 'rule',
            'summary': _pick_markdown_value(parsed, 'summary', 'overview'),
            'content': _pick_markdown_value(parsed, 'content', 'body', 'details'),
            'canon_notes': _pick_markdown_value(parsed, 'canon_notes', 'canon', 'notes'),
        })
    elif kind == 'scenario':
        raw.update({
            'premise': _pick_markdown_value(parsed, 'premise', 'summary', 'overview'),
            'opening_beat': _pick_markdown_value(parsed, 'opening_beat', 'opening'),
            'tone': _pick_markdown_value(parsed, 'tone', multiline=False),
            'location_label': _pick_markdown_value(parsed, 'location_label', 'location', multiline=False),
            'objective': _pick_markdown_value(parsed, 'objective', multiline=False),
            'scene_notes': _pick_markdown_value(parsed, 'scene_notes', 'notes', 'canon_notes'),
            'cast': _cast_from_markdown(parsed),
        })
    else:
        raise ValueError('Unsupported library kind.')
    record, warnings = _coerce_record(kind, raw, preserve_id=False)
    warnings.append('Markdown import is best-effort. Review linked IDs, relationship arrays, and canon details before saving.')
    return record, warnings


def _records_from_json_payload(payload: Any, requested_kind: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get('records'), list):
        records = payload.get('records') or []
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError('JSON import must be an object, an array, or an object with a records array.')
    if not records:
        raise ValueError('Import file does not contain any records.')
    detected_kind = requested_kind
    if not detected_kind:
        kinds = {_normalize_kind(item.get('kind')) for item in records if isinstance(item, dict) and _normalize_kind(item.get('kind'))}
        if len(kinds) > 1:
            raise ValueError('JSON import contains multiple library kinds. Choose a target kind and import one kind at a time.')
        detected_kind = next(iter(kinds), '')
    if not detected_kind:
        raise ValueError('Could not detect the library kind from JSON. Choose a target library and try again.')
    normalised: list[dict[str, Any]] = []
    for item in records:
        record, record_warnings = _coerce_record(detected_kind, item, preserve_id=True)
        normalised.append(record)
        warnings.extend(record_warnings)
    return detected_kind, normalised, warnings


def _build_summary(preview_id: str, source_name: str, source_type: str, kind: str, records: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    items = []
    overwrite_count = 0
    for record in records:
        record_id = _clean_text(record.get('id'))
        if record_id and get_record(kind, record_id):
            overwrite_count += 1
        label = _clean_text(record.get(TITLE_KEY_BY_KIND[kind])) or _clean_text(record.get('display_name')) or 'Untitled'
        subtitle_parts = []
        for key in ('summary', 'premise', 'role_tier', 'realm_type', 'region_type', 'city_type', 'location_type', 'item_type', 'ritual_type', 'cycle_type', 'category', 'pack_type', 'legend_type'):
            value = _clean_text(record.get(key))
            if value:
                subtitle_parts.append(value)
            if len(subtitle_parts) >= 2:
                break
        items.append({
            'id': record_id,
            'label': label,
            'subtitle': ' · '.join(subtitle_parts),
        })
    return {
        'preview_id': preview_id,
        'source_name': source_name,
        'source_type': source_type,
        'import_kind': kind,
        'import_kind_label': KIND_LABELS.get(kind, kind.title()),
        'record_count': len(records),
        'overwrite_count': overwrite_count,
        'warnings': warnings,
        'items': items,
    }


def build_import_preview(filename: str, content_bytes: bytes, requested_kind: str = '') -> dict[str, Any]:
    clean_kind = _normalize_kind(requested_kind)
    if clean_kind and clean_kind not in KIND_MAP:
        raise ValueError('Unsupported target library kind.')
    suffix = Path(filename or '').suffix.lower()
    source_name = _safe_name(filename)
    text = content_bytes.decode('utf-8-sig', errors='replace')
    source_type = 'json'
    if suffix in {'.md', '.markdown', '.txt'} and not text.lstrip().startswith('{') and not text.lstrip().startswith('['):
        source_type = 'markdown'
    elif suffix == '.json':
        source_type = 'json'
    elif suffix in {'.txt', '.md', '.markdown'} and text.lstrip().startswith(('{', '[')):
        source_type = 'json'
    else:
        source_type = 'markdown' if suffix in {'.md', '.markdown', '.txt'} else 'json'

    if source_type == 'json':
        try:
            payload = json.loads(text)
        except Exception as exc:
            raise ValueError(f'Could not parse JSON import: {exc}') from exc
        import_kind, records, warnings = _records_from_json_payload(payload, clean_kind)
    else:
        if not clean_kind:
            raise ValueError('Choose a target library kind before importing Markdown or TXT.')
        import_kind = clean_kind
        record, warnings = _record_from_markdown(import_kind, text)
        records = [record]

    preview_id = f'import_preview_{uuid4().hex[:12]}'
    preview_payload = {
        'preview_id': preview_id,
        'created_at': now_iso(),
        'source_name': source_name,
        'source_type': source_type,
        'import_kind': import_kind,
        'records': records,
        'summary': _build_summary(preview_id, source_name, source_type, import_kind, records, warnings),
        'raw_excerpt': text[:5000],
        'raw_text': text,
    }
    _write_preview(preview_payload)
    return preview_payload


def commit_import_preview(preview_id: str) -> dict[str, Any]:
    preview = _read_preview(preview_id)
    kind = _normalize_kind(preview.get('import_kind'))
    if kind not in KIND_MAP:
        raise ValueError('Import preview target kind is invalid.')
    records = preview.get('records') or []
    if not isinstance(records, list) or not records:
        raise ValueError('Import preview does not contain records to save.')
    saved_records = [import_record(kind, record) for record in records if isinstance(record, dict)]
    return {
        'preview_id': preview_id,
        'import_kind': kind,
        'import_kind_label': KIND_LABELS.get(kind, kind.title()),
        'saved_records': saved_records,
        'saved_count': len(saved_records),
    }
