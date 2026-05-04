from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .roleplay_foundation import ROLEPLAY_PARTS_DIR, ROLEPLAY_STORIES_DIR, story_template, now_iso, default_linked_story_context
from .roleplay_library_store import get_record
from .storage_io import atomic_write_json, read_json_object
from .memory_service.roleplay_adapter import mark_roleplay_story_deleted, sync_roleplay_story


def _story_path(story_id: str) -> Path:
    return ROLEPLAY_STORIES_DIR / f"{story_id}.json"


def _read_story(path: Path) -> dict[str, Any] | None:
    return read_json_object(path, None)


def _write_story(record: dict[str, Any]) -> dict[str, Any]:
    ROLEPLAY_STORIES_DIR.mkdir(parents=True, exist_ok=True)
    path = _story_path(str(record.get('id') or '').strip())
    atomic_write_json(path, record)
    sync_roleplay_story(record, source_json_path=str(path))
    return record



LINKED_CONTEXT_KIND_MAP: dict[str, str] = {
    'legend_ids': 'legend',
    'universe_ids': 'universe',
    'world_ids': 'world',
    'region_ids': 'region',
    'city_ids': 'city',
    'location_ids': 'location',
    'organization_ids': 'organization',
    'character_ids': 'character',
    'artifact_ids': 'artifact',
    'ritual_ids': 'ritual',
    'cycle_ids': 'cycle',
    'creature_ids': 'creature',
    'pack_ids': 'pack',
    'scenario_ids': 'scenario',
}


def normalize_linked_context(raw: Any) -> dict[str, list[str]]:
    context = default_linked_story_context()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return context
    for key in context:
        values = raw.get(key)
        if isinstance(values, list):
            clean = []
            for item in values:
                sid = str(item or '').strip()
                if sid and sid not in clean:
                    clean.append(sid)
            context[key] = clean
    return context


def linked_context_counts(raw: Any) -> dict[str, int]:
    context = normalize_linked_context(raw)
    return {key: len(values) for key, values in context.items() if values}


def linked_context_summary(raw: Any, label: str = 'Linked context') -> str:
    context = normalize_linked_context(raw)
    lines: list[str] = []
    for key, kind in LINKED_CONTEXT_KIND_MAP.items():
        ids = context.get(key) or []
        if not ids:
            continue
        names: list[str] = []
        for record_id in ids:
            rec = get_record(kind, record_id)
            if not rec:
                continue
            title = str(rec.get('title') or rec.get('name') or rec.get('display_name') or '').strip()
            if title:
                names.append(title)
        if names:
            heading = key.replace('_ids', '').replace('_', ' ').title()
            lines.append(f"{heading}: {', '.join(names[:8])}")
    if not lines:
        return ''
    return f"{label}:\n" + '\n'.join(lines)

def normalize_branching_story_config(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    story_mode = str(data.get('story_mode') or '').strip().lower()
    story_mode = 'branching' if story_mode == 'branching' else 'linear'
    try:
        option_count = max(2, min(6, int(data.get('option_count') or 3)))
    except Exception:
        option_count = 3
    allow_custom_option = bool(data.get('allow_custom_option', True))
    return {
        'story_mode': story_mode,
        'option_count': option_count,
        'allow_custom_option': allow_custom_option,
    }

def _normalize_name_list(raw: str) -> list[str]:
    items = []
    for part in str(raw or '').replace(';', ',').split(','):
        clean = part.strip()
        if clean and clean not in items:
            items.append(clean)
    return items


def list_story_cards() -> list[dict[str, Any]]:
    ROLEPLAY_STORIES_DIR.mkdir(parents=True, exist_ok=True)
    cards: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_STORIES_DIR.glob('*.json')):
        rec = _read_story(path)
        if not rec:
            continue
        meta = rec.get('meta') or {}
        cover = rec.get('cover') or {}
        cards.append({
            'id': rec.get('id', ''),
            'title': rec.get('title', ''),
            'summary': rec.get('summary', ''),
            'universe_label': rec.get('universe_label', ''),
            'world_label': rec.get('world_label', ''),
            'lead_character_names': rec.get('lead_character_names') or [],
            'status': meta.get('status', 'draft'),
            'updated_at': meta.get('updated_at', ''),
            'part_count': len(rec.get('part_ids') or []),
            'story_mode': str(rec.get('story_mode') or 'linear'),
            'branching': normalize_branching_story_config(rec.get('branching')),
            'linked_context_counts': linked_context_counts(rec.get('linked_context')),
            'cover_image_path': cover.get('image_path', ''),
            'cover_thumb_path': cover.get('thumb_path', ''),
        })
    cards.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    return cards


def get_story_record(story_id: str) -> dict[str, Any] | None:
    clean_id = str(story_id or '').strip()
    if not clean_id:
        return None
    return _read_story(_story_path(clean_id))


def save_story_record(*, story_id: str = '', title: str, summary: str = '', universe_label: str = '', world_label: str = '', lead_characters: str = '', status: str = 'draft', canon_mode: str = 'what_if', output_preset: str = 'roleplay', linked_context: Any = None, story_mode: str = 'linear', option_count: int = 3, allow_custom_option: bool = True) -> dict[str, Any]:
    clean_title = str(title or '').strip()
    if not clean_title:
        raise ValueError('Story title is required.')

    record = get_story_record(story_id) if str(story_id or '').strip() else None
    if not record:
        record = story_template(clean_title)

    record['title'] = clean_title
    record['summary'] = str(summary or '').strip()
    record['universe_label'] = str(universe_label or '').strip()
    record['world_label'] = str(world_label or '').strip()
    record['lead_character_names'] = _normalize_name_list(lead_characters)
    record['linked_context'] = normalize_linked_context(linked_context or record.get('linked_context'))
    branching = normalize_branching_story_config({'story_mode': story_mode, 'option_count': option_count, 'allow_custom_option': allow_custom_option})
    record['story_mode'] = branching['story_mode']
    record['branching'] = {**(record.get('branching') or {}), **branching}
    advanced = record.get('advanced_controls') or {}
    advanced['canon_mode'] = str(canon_mode or 'what_if').strip() or 'what_if'
    advanced['output_preset'] = str(output_preset or 'roleplay').strip() or 'roleplay'
    record['advanced_controls'] = advanced
    meta = record.get('meta') or {}
    if not meta.get('created_at'):
        meta['created_at'] = now_iso()
    meta['updated_at'] = now_iso()
    meta['status'] = str(status or 'draft').strip() or 'draft'
    record['meta'] = meta
    return _write_story(record)


def delete_story_record(story_id: str) -> bool:
    clean_id = str(story_id or '').strip()
    if not clean_id:
        return False
    path = _story_path(clean_id)
    record = _read_story(path) or {}
    if not path.exists():
        return False
    for part_id in record.get('part_ids') or []:
        part_path = ROLEPLAY_PARTS_DIR / f"{str(part_id or '').strip()}.json"
        if part_path.exists():
            part_path.unlink()
    path.unlink()
    mark_roleplay_story_deleted(clean_id, source_json_path=str(path))
    return True
