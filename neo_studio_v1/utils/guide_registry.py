from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts.guide_records import normalize_guide_record
from .shared_data_paths import studio_data_path
from .storage_io import atomic_write_json, read_json_object

GUIDE_STORE_PATH = studio_data_path('support_guides.json', legacy_rel='support_guides.json', default_json={'guides': []})


DEFAULT_GUIDES = [
    {
        'guide_id': 'generation:workspace_setup',
        'title': 'Generation workspace setup',
        'short_help': 'Pick a model family first, then confirm the connected image backend and required assets before launching.',
        'long_help': 'Use SDXL / SD for checkpoint-first workflows, Flux for GGUF workflows, and the staged families only when their pipeline is wired. Backend connection is surface-level; profile editing lives in Admin.',
        'surface': 'generation',
        'section': 'workspace_setup',
        'tags': ['generation', 'image', 'setup'],
    },
    {
        'guide_id': 'prompt_caption:presets',
        'title': 'Prompt and caption presets',
        'short_help': 'Presets should stay scoped, reusable, and clearly named by purpose.',
        'long_help': 'Use prompt presets for authoring styles and caption presets for captioning styles. Keep group, notes, and tags clean so future migration and export stay stable.',
        'surface': 'prompt_caption',
        'section': 'presets',
        'tags': ['presets', 'prompt', 'caption'],
    },
    {
        'guide_id': 'assistant:helper_bridge',
        'title': 'Assistant helper bridge',
        'short_help': 'Other surfaces can send context packets into Assistant instead of duplicating helper logic locally.',
        'long_help': 'Use helper packets to preserve source surface, source section, and allowed apply actions. This keeps future cross-tab help flows structured and auditable.',
        'surface': 'assistant',
        'section': 'helper_bridge',
        'tags': ['assistant', 'helper', 'packets'],
    },
    {
        'guide_id': 'admin:backends',
        'title': 'Backend management',
        'short_help': 'Connect from the active surface, configure profiles inside Admin.',
        'long_help': 'Runtime connect or disconnect actions belong in the active tab. Adapter profiles, defaults, health checks, and transport details belong in Admin.',
        'surface': 'admin',
        'section': 'backends',
        'tags': ['admin', 'backend'],
    },
]


def _normalize_store(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    records = raw.get('guides') if isinstance(raw.get('guides'), list) else []
    normalized = [normalize_guide_record(item) for item in records if isinstance(item, dict)]
    return {
        'schema_version': 1,
        'guides': normalized,
    }


def ensure_support_guides_foundation() -> dict[str, Any]:
    if GUIDE_STORE_PATH.exists():
        current = _normalize_store(read_json_object(GUIDE_STORE_PATH, {'guides': []}))
        if current.get('guides'):
            return current
    payload = {'guides': [normalize_guide_record(item) for item in DEFAULT_GUIDES]}
    clean = _normalize_store(payload)
    GUIDE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(GUIDE_STORE_PATH, clean)
    return clean


def load_support_guides() -> dict[str, Any]:
    return _normalize_store(read_json_object(GUIDE_STORE_PATH, {'guides': []}))


def list_support_guides(*, surface: str = '', section: str = '') -> list[dict[str, Any]]:
    payload = ensure_support_guides_foundation()
    surface = str(surface or '').strip().lower()
    section = str(section or '').strip().lower()
    out = []
    for item in payload.get('guides') or []:
        if surface and str(item.get('surface') or '').strip().lower() != surface:
            continue
        if section and str(item.get('section') or '').strip().lower() != section:
            continue
        out.append(item)
    return out


def upsert_support_guide(record: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_support_guides_foundation()
    clean = normalize_guide_record(record, source='user')
    guides = payload.get('guides') or []
    out = []
    replaced = False
    for item in guides:
        if str(item.get('guide_id') or '') == clean['guide_id']:
            out.append(clean)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(clean)
    store = {'schema_version': 1, 'guides': out}
    atomic_write_json(GUIDE_STORE_PATH, store)
    return clean
