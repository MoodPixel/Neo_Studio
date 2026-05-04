from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

BOARD_RECORD_SCHEMA_VERSION = 1
BOARD_RECORD_TYPE = 'board'
BOARD_ITEM_TYPES = {'sticky', 'checklist', 'text', 'image', 'audio', 'video'}
DEFAULT_BOARD_NAME = 'Untitled Board'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def new_board_id() -> str:
    return f'board_{uuid4().hex[:12]}'


def new_item_id() -> str:
    return f'item_{uuid4().hex[:12]}'


def normalize_board_name(name: Any, fallback: str = DEFAULT_BOARD_NAME) -> str:
    clean = ' '.join(str(name or '').strip().split())
    return clean[:120] if clean else fallback


def normalize_canvas_payload(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    return {
        'background': str(raw.get('background') or 'default').strip() or 'default',
        'zoom': _number(raw.get('zoom'), 1.0, minimum=0.1, maximum=4.0),
        'pan_x': _number(raw.get('pan_x'), 0.0, minimum=-100000.0, maximum=100000.0),
        'pan_y': _number(raw.get('pan_y'), 0.0, minimum=-100000.0, maximum=100000.0),
        'grid_enabled': bool(raw.get('grid_enabled', True)),
    }


def normalize_board_item(payload: Any, *, fallback_z: int = 1, now: str | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    item_type = str(raw.get('type') or 'sticky').strip().lower()
    if item_type not in BOARD_ITEM_TYPES:
        item_type = 'sticky'
    stamp = now or utc_now_iso()
    checked_items = raw.get('checked_items') if isinstance(raw.get('checked_items'), list) else []
    return {
        'id': str(raw.get('id') or new_item_id()).strip() or new_item_id(),
        'type': item_type,
        'x': _number(raw.get('x'), 120.0, minimum=-100000.0, maximum=100000.0),
        'y': _number(raw.get('y'), 120.0, minimum=-100000.0, maximum=100000.0),
        'w': _number(raw.get('w'), 260.0, minimum=80.0, maximum=4000.0),
        'h': _number(raw.get('h'), 180.0, minimum=60.0, maximum=4000.0),
        'z': int(_number(raw.get('z'), float(fallback_z), minimum=0.0, maximum=1000000.0)),
        'color': str(raw.get('color') or '').strip(),
        'title': str(raw.get('title') or '').strip()[:240],
        'content': str(raw.get('content') or ''),
        'checked_items': [normalize_checklist_item(item) for item in checked_items],
        'media_path': str(raw.get('media_path') or '').strip(),
        'media_kind': str(raw.get('media_kind') or '').strip().lower(),
        'created_at': str(raw.get('created_at') or stamp),
        'updated_at': str(raw.get('updated_at') or stamp),
    }


def normalize_checklist_item(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    linked_item_ids = raw.get('linked_item_ids') if isinstance(raw.get('linked_item_ids'), list) else []
    clean_links: list[str] = []
    for link_id in linked_item_ids:
        clean = str(link_id or '').strip()
        if clean and clean not in clean_links:
            clean_links.append(clean[:120])
    return {
        'id': str(raw.get('id') or new_item_id()).strip() or new_item_id(),
        'text': str(raw.get('text') or '').strip()[:500],
        'checked': bool(raw.get('checked', False)),
        'color': normalize_checklist_color(raw.get('color')),
        'linked_item_ids': clean_links,
    }


def normalize_checklist_color(value: Any) -> str:
    clean = str(value or '').strip()
    if len(clean) == 7 and clean.startswith('#'):
        try:
            int(clean[1:], 16)
            return clean.lower()
        except Exception:
            pass
    return '#4ade80'


def normalize_board_record(payload: Any, *, board_id: str = '', preserve_timestamps: bool = True) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    stamp = utc_now_iso()
    resolved_id = str(board_id or raw.get('id') or new_board_id()).strip() or new_board_id()
    created_at = str(raw.get('created_at') or stamp) if preserve_timestamps else stamp
    items = raw.get('items') if isinstance(raw.get('items'), list) else []
    return {
        'schema_version': BOARD_RECORD_SCHEMA_VERSION,
        'record_type': BOARD_RECORD_TYPE,
        'id': resolved_id,
        'name': normalize_board_name(raw.get('name')),
        'created_at': created_at,
        'updated_at': stamp,
        'canvas': normalize_canvas_payload(raw.get('canvas')),
        'items': [normalize_board_item(item, fallback_z=index + 1, now=stamp) for index, item in enumerate(items)],
    }


def build_new_board_record(name: Any = DEFAULT_BOARD_NAME) -> dict[str, Any]:
    return normalize_board_record({'id': new_board_id(), 'name': normalize_board_name(name), 'canvas': {}, 'items': []}, preserve_timestamps=False)


def build_board_summary(record: dict[str, Any]) -> dict[str, Any]:
    items = record.get('items') if isinstance(record.get('items'), list) else []
    return {
        'id': str(record.get('id') or '').strip(),
        'name': normalize_board_name(record.get('name')),
        'created_at': str(record.get('created_at') or ''),
        'updated_at': str(record.get('updated_at') or ''),
        'item_count': len(items),
    }


def clone_board_payload(record: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
    clone = deepcopy(record if isinstance(record, dict) else {})
    stamp = utc_now_iso()
    clone['id'] = new_board_id()
    clone['name'] = normalize_board_name(name if name is not None else f"{clone.get('name') or DEFAULT_BOARD_NAME} Copy")
    clone['created_at'] = stamp
    clone['updated_at'] = stamp
    for index, item in enumerate(clone.get('items') if isinstance(clone.get('items'), list) else []):
        if isinstance(item, dict):
            item['id'] = new_item_id()
            item['z'] = int(item.get('z') or index + 1)
            item['created_at'] = stamp
            item['updated_at'] = stamp
    return normalize_board_record(clone, preserve_timestamps=True)


def _number(value: Any, fallback: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        num = float(value)
    except Exception:
        num = float(fallback)
    if minimum is not None:
        num = max(float(minimum), num)
    if maximum is not None:
        num = min(float(maximum), num)
    return num
