from __future__ import annotations

from typing import Any, Dict

from .library_presets import get_last_used_caption_preset, get_last_used_prompt_preset
from .library_settings_store import get_last_used_category, get_library_root, list_categories


def stats() -> Dict[str, Any]:
    root = get_library_root()
    prompt_count = len(list((root / 'prompts').glob('*.json')))
    caption_count = len(list((root / 'captions').glob('*.json')))
    return {
        'root': str(root),
        'prompt_count': prompt_count,
        'caption_count': caption_count,
        'categories': list_categories(),
        'last_prompt_category': get_last_used_category('prompt'),
        'last_caption_category': get_last_used_category('caption'),
        'last_caption_preset': get_last_used_caption_preset(),
        'last_prompt_preset': get_last_used_prompt_preset(),
    }
