import json
from typing import Any

from .config import CHARACTER_STORE_PATH
from .logging_utils import get_logger
from .storage_io import atomic_write_json, read_json

logger = get_logger(__name__)

CHARACTER_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_character_map() -> dict[str, str]:
    try:
        if not CHARACTER_STORE_PATH.exists():
            return {}
        data = read_json(CHARACTER_STORE_PATH, [])
        if isinstance(data, dict):
            out: dict[str, str] = {}
            for key, value in data.items():
                name = str(key or '').strip()
                if not name:
                    continue
                if isinstance(value, dict):
                    content = str(value.get('content') or value.get('text') or value.get('character') or '').strip()
                else:
                    content = str(value or '').strip()
                if content:
                    out[name] = content
            return out
    except Exception:
        logger.exception('Failed to load saved characters from %s', CHARACTER_STORE_PATH)
    return {}

def write_character_map(data: dict[str, str]) -> None:
    clean: dict[str, str] = {}
    for key, value in (data or {}).items():
        name = str(key or '').strip()
        if not name:
            continue
        clean[name] = str(value or '').strip()
    atomic_write_json(CHARACTER_STORE_PATH, clean)

def character_entries() -> list[dict[str, str]]:
    data = load_character_map()
    return [
        {'id': name, 'label': name, 'name': name}
        for name in sorted(data.keys(), key=lambda s: s.lower())
    ]

def get_character_record(name: str) -> dict[str, Any] | None:
    target = (name or '').strip()
    if not target:
        return None
    data = load_character_map()
    if target not in data:
        return None
    return {'id': target, 'name': target, 'content': data[target]}

def save_character_record(name: str, content: str) -> dict[str, str]:
    clean_name = (name or '').strip()
    clean_content = (content or '').strip()
    if not clean_name:
        raise ValueError('Character name is required.')
    if not clean_content:
        raise ValueError('Character content is required.')
    data = load_character_map()
    data[clean_name] = clean_content
    write_character_map(data)
    return {'id': clean_name, 'name': clean_name, 'content': clean_content}

def delete_character_record(name: str) -> bool:
    clean_name = (name or '').strip()
    if not clean_name:
        return False
    data = load_character_map()
    if clean_name not in data:
        return False
    data.pop(clean_name, None)
    write_character_map(data)
    return True
