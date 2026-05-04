from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .library_constants import DEFAULT_ROOT, USER_DATA_DIR
from .logging_utils import get_logger
from .storage_io import atomic_write_json, read_json

logger = get_logger(__name__)

ROLEPLAY_SCHEMA_VERSION = 4
LEGACY_ROLEPLAY_ROOT = USER_DATA_DIR / 'roleplay'
ROLEPLAY_ROOT = DEFAULT_ROOT / 'roleplay'
ROLEPLAY_FOUNDATION_PATH = ROLEPLAY_ROOT / 'foundation_manifest.json'
ROLEPLAY_UNIVERSES_DIR = ROLEPLAY_ROOT / 'universes'
ROLEPLAY_WORLDS_DIR = ROLEPLAY_ROOT / 'worlds'
ROLEPLAY_REGIONS_DIR = ROLEPLAY_ROOT / 'regions'
ROLEPLAY_CITIES_DIR = ROLEPLAY_ROOT / 'cities'
ROLEPLAY_LOCATIONS_DIR = ROLEPLAY_ROOT / 'locations'
ROLEPLAY_ORGANIZATIONS_DIR = ROLEPLAY_ROOT / 'organizations'
ROLEPLAY_ARTIFACTS_DIR = ROLEPLAY_ROOT / 'artifacts'
ROLEPLAY_RITUALS_DIR = ROLEPLAY_ROOT / 'rituals'
ROLEPLAY_CYCLES_DIR = ROLEPLAY_ROOT / 'cycles'
ROLEPLAY_CREATURES_DIR = ROLEPLAY_ROOT / 'creatures'
ROLEPLAY_LEGENDS_DIR = ROLEPLAY_ROOT / 'legends'
ROLEPLAY_PACKS_DIR = ROLEPLAY_ROOT / 'packs'
ROLEPLAY_STORIES_DIR = ROLEPLAY_ROOT / 'stories'
ROLEPLAY_CHARACTERS_DIR = ROLEPLAY_ROOT / 'characters'
ROLEPLAY_SCENARIOS_DIR = ROLEPLAY_ROOT / 'scenarios'
ROLEPLAY_PARTS_DIR = ROLEPLAY_ROOT / 'story_parts'
ROLEPLAY_SESSIONS_DIR = ROLEPLAY_ROOT / 'sessions'
ROLEPLAY_ASSETS_DIR = ROLEPLAY_ROOT / 'assets'
ROLEPLAY_STORY_COVERS_DIR = ROLEPLAY_ASSETS_DIR / 'story_covers'
ROLEPLAY_CHARACTER_IMAGES_DIR = ROLEPLAY_ASSETS_DIR / 'character_images'
ROLEPLAY_IMPORTS_DIR = ROLEPLAY_ROOT / 'imports'
ROLEPLAY_EXPORTS_DIR = ROLEPLAY_ROOT / 'exports'

ROLEPLAY_CANON_MODES = {
    'follow_exact': 'Follow canon exactly',
    'follow_until_divergence': 'Follow canon until divergence',
    'self_insert': 'Insert yourself into canon',
    'what_if': 'Alternate take / what-if',
}

ROLEPLAY_OUTPUT_PRESETS = {
    'roleplay': 'Roleplay',
    'short_story': 'Short Story',
    'novel': 'Novel Mode',
    'cinematic': 'Cinematic Mode',
}

ROLEPLAY_PACKET_LAYERS = [
    'system_rules',
    'universe_packet',
    'world_packet',
    'character_packets',
    'scenario_packet',
    'story_canon',
    'part_canon',
    'rolling_summary',
    'recent_turns',
    'live_instruction',
]

ROLEPLAY_DIRS = [
    ROLEPLAY_ROOT,
    ROLEPLAY_UNIVERSES_DIR,
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
    ROLEPLAY_STORIES_DIR,
    ROLEPLAY_CHARACTERS_DIR,
    ROLEPLAY_SCENARIOS_DIR,
    ROLEPLAY_PARTS_DIR,
    ROLEPLAY_SESSIONS_DIR,
    ROLEPLAY_ASSETS_DIR,
    ROLEPLAY_STORY_COVERS_DIR,
    ROLEPLAY_CHARACTER_IMAGES_DIR,
    ROLEPLAY_IMPORTS_DIR,
    ROLEPLAY_EXPORTS_DIR,
]



def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def slugify(text: str, fallback: str = 'item') -> str:
    cleaned = re.sub(r'[^a-z0-9]+', '-', str(text or '').strip().lower())
    cleaned = cleaned.strip('-')
    return cleaned or fallback



def make_record_id(prefix: str, label: str = '') -> str:
    base = slugify(label, prefix)
    return f'{prefix}_{base}_{uuid4().hex[:8]}'



def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)



def _read_json(path: Path, default: Any) -> Any:
    data = read_json(path, default)
    if data is default and path.exists():
        logger.exception('Failed to read JSON from %s', path)
    return data



def default_generation_controls() -> dict[str, Any]:
    return {
        'max_tokens': 320,
        'temperature': 0.82,
        'top_p': 0.92,
        'top_k': 60,
        'stop_strings': [],
    }





def default_linked_story_context() -> dict[str, list[str]]:
    return {
        'legend_ids': [],
        'universe_ids': [],
        'world_ids': [],
        'region_ids': [],
        'city_ids': [],
        'location_ids': [],
        'organization_ids': [],
        'character_ids': [],
        'artifact_ids': [],
        'ritual_ids': [],
        'cycle_ids': [],
        'creature_ids': [],
        'pack_ids': [],
        'scenario_ids': [],
    }

def default_advanced_controls() -> dict[str, Any]:
    return {
        'memory_canon_notes': '',
        'author_note': '',
        'output_preset': 'roleplay',
        'canon_mode': 'what_if',
        'generation': default_generation_controls(),
    }


def default_story_progression() -> dict[str, Any]:
    return {
        'chapter_index': 1,
        'chapter_label': '',
        'part_index': 1,
        'beat_focus': '',
        'active_pov': '',
        'active_location': '',
        'active_cast_focus': '',
        'part_objective': '',
        'tension_level': 'medium',
        'pacing_target': 'steady',
    }


def default_branching_config() -> dict[str, Any]:
    return {
        'story_mode': 'linear',
        'option_count': 3,
        'allow_custom_option': True,
        'latest_options': [],
        'choice_history': [],
    }



def universe_template(name: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'universe',
        'id': make_record_id('universe', name),
        'name': str(name or '').strip(),
        'summary': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def world_template(name: str = '', universe_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'world',
        'id': make_record_id('world', name),
        'universe_id': str(universe_id or '').strip(),
        'name': str(name or '').strip(),
        'summary': '',
        'lore': '',
        'rules': '',
        'places': [],
        'factions': [],
        'organization_ids': [],
        'organization_names': [],
        'realm_type': '',
        'calendar_notes': '',
        'geography_notes': '',
        'society_notes': '',
        'faith_notes': '',
        'people_notes': '',
        'inhabitant_species_ids': [],
        'inhabitant_species_names': [],
        'creature_fauna_ids': [],
        'creature_fauna_names': [],
        'cycle_ids': [],
        'cycle_names': [],
        'canon_notes': '',
        'tags': [],
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def character_template(name: str = '', world_id: str = '', universe_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'character',
        'id': make_record_id('character', name),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'name': str(name or '').strip(),
        'display_name': str(name or '').strip(),
        'summary': '',
        'gender': '',
        'pronouns': '',
        'role_tier': 'main',
        'species': '',
        'designation': '',
        'occupation': '',
        'student_details': '',
        'hobbies': '',
        'affiliations': '',
        'organization_ids': [],
        'organization_names': [],
        'origin_world_id': str(world_id or '').strip(),
        'current_world_id': str(world_id or '').strip(),
        'origin_region_id': '',
        'current_region_id': '',
        'origin_city_id': '',
        'current_city_id': '',
        'origin_location_id': '',
        'current_location_id': '',
        'origin_location_label': '',
        'current_location_label': '',
        'appearance': '',
        'personality': '',
        'speech_style': '',
        'relationship_notes': '',
        'relationships': [],
        'abilities': [],
        'artifact_ids': [],
        'artifact_names': [],
        'ritual_ids': [],
        'ritual_names': [],
        'cycle_ids': [],
        'cycle_names': [],
        'wardrobes': [],
        'story_hooks': [],
        'canon_notes': '',
        'private_notes': '',
        'avatar': {
            'image_path': '',
            'thumb_path': '',
            'alt_text': '',
        },
        'tags': [],
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def scenario_template(title: str = '', world_id: str = '', universe_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'scenario',
        'id': make_record_id('scenario', title),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'title': str(title or '').strip(),
        'premise': '',
        'opening_beat': '',
        'tone': '',
        'location_region_id': '',
        'location_city_id': '',
        'location_id': '',
        'location_label': '',
        'objective': '',
        'linked_character_ids': [],
        'organization_ids': [],
        'organization_names': [],
        'cast': [],
        'scene_notes': '',
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def city_template(name: str = '', world_id: str = '', region_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'city',
        'id': make_record_id('city', name),
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'name': str(name or '').strip(),
        'city_type': 'city',
        'summary': '',
        'access_notes': '',
        'organization_ids': [],
        'organization_names': [],
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def location_template(name: str = '', anchor_type: str = 'world', universe_id: str = '', world_id: str = '', region_id: str = '', city_id: str = '', parent_location_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'location',
        'id': make_record_id('location', name),
        'anchor_type': str(anchor_type or 'world').strip(),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'city_id': str(city_id or '').strip(),
        'parent_location_id': str(parent_location_id or '').strip(),
        'name': str(name or '').strip(),
        'display_name': str(name or '').strip(),
        'function_label': '',
        'location_type': 'building',
        'summary': '',
        'atmosphere': '',
        'scene_uses': [],
        'access_notes': '',
        'hazards': '',
        'rules': '',
        'public_notes': '',
        'hidden_truth': '',
        'artifact_ids': [],
        'artifact_names': [],
        'ritual_ids': [],
        'ritual_names': [],
        'cycle_ids': [],
        'cycle_names': [],
        'organization_ids': [],
        'organization_names': [],
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }






def organization_template(name: str = '', universe_id: str = '', world_id: str = '', region_id: str = '', city_id: str = '', base_location_id: str = '', parent_organization_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'organization',
        'id': make_record_id('organization', name),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'city_id': str(city_id or '').strip(),
        'base_location_id': str(base_location_id or '').strip(),
        'parent_organization_id': str(parent_organization_id or '').strip(),
        'name': str(name or '').strip(),
        'display_name': str(name or '').strip(),
        'group_type': 'organization',
        'summary': '',
        'leadership': '',
        'beliefs': '',
        'goals': '',
        'reputation': '',
        'resources': '',
        'membership_rules': '',
        'public_face': '',
        'hidden_truth': '',
        'ally_organization_ids': [],
        'ally_organization_names': [],
        'rival_organization_ids': [],
        'rival_organization_names': [],
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def artifact_template(name: str = '', world_id: str = '', region_id: str = '', city_id: str = '', location_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'artifact',
        'id': make_record_id('artifact', name),
        'name': str(name or '').strip(),
        'item_type': 'weapon',
        'rarity': 'normal',
        'state': 'active',
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'city_id': str(city_id or '').strip(),
        'location_id': str(location_id or '').strip(),
        'current_holder_character_id': '',
        'source_tradition': '',
        'summary': '',
        'effects': '',
        'costs': '',
        'activation': '',
        'lawful_status': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def ritual_template(name: str = '', world_id: str = '', region_id: str = '', location_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'ritual',
        'id': make_record_id('ritual', name),
        'name': str(name or '').strip(),
        'ritual_type': 'ritual',
        'school': '',
        'state': 'known',
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'location_id': str(location_id or '').strip(),
        'effect_summary': '',
        'requirements': '',
        'risks': '',
        'lawful_status': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def cycle_template(name: str = '', universe_id: str = '', world_id: str = '', region_id: str = '', location_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'cycle',
        'id': make_record_id('cycle', name),
        'name': str(name or '').strip(),
        'cycle_type': 'celestial',
        'scope_type': 'world',
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'region_id': str(region_id or '').strip(),
        'location_id': str(location_id or '').strip(),
        'affected_species': '',
        'affected_designation': '',
        'cadence': '',
        'trigger': '',
        'stages': '',
        'effects': '',
        'safeguards': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def creature_template(name: str = '', world_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'creature',
        'id': make_record_id('creature', name),
        'world_id': str(world_id or '').strip(),
        'name': str(name or '').strip(),
        'category': 'creature',
        'sentience': 'unknown',
        'summary': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def legend_template(title: str = '', universe_id: str = '', world_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'legend',
        'id': make_record_id('legend', title),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'title': str(title or '').strip(),
        'scope': 'world',
        'legend_type': 'myth',
        'truth_status': 'disputed',
        'public_version': '',
        'hidden_version': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def pack_template(title: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'pack',
        'id': make_record_id('pack', title),
        'title': str(title or '').strip(),
        'pack_type': 'rule',
        'summary': '',
        'content': '',
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }


def region_template(name: str = '', world_id: str = '', parent_region_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'region',
        'id': make_record_id('region', name),
        'world_id': str(world_id or '').strip(),
        'parent_region_id': str(parent_region_id or '').strip(),
        'name': str(name or '').strip(),
        'region_type': 'kingdom',
        'summary': '',
        'organization_ids': [],
        'organization_names': [],
        'canon_notes': '',
        'tags': [],
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def story_template(title: str = '', world_id: str = '', universe_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'story',
        'id': make_record_id('story', title),
        'universe_id': str(universe_id or '').strip(),
        'world_id': str(world_id or '').strip(),
        'universe_label': '',
        'world_label': '',
        'title': str(title or '').strip(),
        'summary': '',
        'lead_character_ids': [],
        'lead_character_names': [],
        'linked_context': default_linked_story_context(),
        'story_mode': 'linear',
        'branching': default_branching_config(),
        'part_ids': [],
        'pinned_canon': '',
        'cover': {
            'image_path': '',
            'thumb_path': '',
            'alt_text': '',
        },
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'draft',
        },
    }



def story_part_template(story_id: str = '', title: str = '', order_index: int = 1) -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'story_part',
        'id': make_record_id('part', title or f'part-{order_index}'),
        'story_id': str(story_id or '').strip(),
        'title': str(title or '').strip() or f'Part {max(1, int(order_index or 1))}',
        'order_index': max(1, int(order_index or 1)),
        'summary': '',
        'scene_notes': '',
        'pinned_canon': '',
        'linked_context': default_linked_story_context(),
        'progression': default_story_progression(),
        'branching': default_branching_config(),
        'transcript': [],
        'scene_text': '',
        'assets': [],
        'branch': {
            'parent_part_id': '',
            'branch_label': '',
        },
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'draft',
        },
    }



def session_template(story_id: str = '', part_id: str = '') -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'kind': 'session',
        'id': make_record_id('session', story_id or part_id or 'roleplay'),
        'story_id': str(story_id or '').strip(),
        'part_id': str(part_id or '').strip(),
        'rolling_summary': '',
        'recent_turns': [],
        'pending_reply': '',
        'latest_finish_reason': '',
        'truncated': False,
        'draft_user_input': '',
        'advanced_controls': default_advanced_controls(),
        'meta': {
            'created_at': now_iso(),
            'updated_at': now_iso(),
            'status': 'active',
        },
    }



def foundation_manifest() -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_SCHEMA_VERSION,
        'created_at': now_iso(),
        'updated_at': now_iso(),
        'paths': {
            'root': str(ROLEPLAY_ROOT),
            'legacy_root': str(LEGACY_ROLEPLAY_ROOT),
            'universes': str(ROLEPLAY_UNIVERSES_DIR),
            'worlds': str(ROLEPLAY_WORLDS_DIR),
            'regions': str(ROLEPLAY_REGIONS_DIR),
            'cities': str(ROLEPLAY_CITIES_DIR),
            'locations': str(ROLEPLAY_LOCATIONS_DIR),
            'organizations': str(ROLEPLAY_ORGANIZATIONS_DIR),
            'artifacts': str(ROLEPLAY_ARTIFACTS_DIR),
            'rituals': str(ROLEPLAY_RITUALS_DIR),
            'cycles': str(ROLEPLAY_CYCLES_DIR),
            'stories': str(ROLEPLAY_STORIES_DIR),
            'characters': str(ROLEPLAY_CHARACTERS_DIR),
            'scenarios': str(ROLEPLAY_SCENARIOS_DIR),
            'story_parts': str(ROLEPLAY_PARTS_DIR),
            'sessions': str(ROLEPLAY_SESSIONS_DIR),
            'assets': str(ROLEPLAY_ASSETS_DIR),
            'imports': str(ROLEPLAY_IMPORTS_DIR),
            'exports': str(ROLEPLAY_EXPORTS_DIR),
        },
        'supported_kinds': [
            'universe',
            'world',
            'region',
            'city',
            'location',
            'organization',
            'artifact',
            'ritual',
            'cycle',
            'character',
            'scenario',
            'story',
            'story_part',
            'session',
        ],
        'canon_modes': ROLEPLAY_CANON_MODES,
        'output_presets': ROLEPLAY_OUTPUT_PRESETS,
        'packet_layers': ROLEPLAY_PACKET_LAYERS,
        'templates': {
            'universe': universe_template(),
            'world': world_template(),
            'region': region_template(),
            'city': city_template(),
            'location': location_template(),
            'organization': organization_template(),
            'artifact': artifact_template(),
            'ritual': ritual_template(),
            'cycle': cycle_template(),
            'character': character_template(),
            'scenario': scenario_template(),
            'story': story_template(),
            'story_part': story_part_template(),
            'session': session_template(),
        },
    }



def ensure_roleplay_foundation() -> dict[str, Any]:
    for path in ROLEPLAY_DIRS:
        path.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(ROLEPLAY_FOUNDATION_PATH, {})
    if not isinstance(manifest, dict) or int(manifest.get('schema_version') or 0) != ROLEPLAY_SCHEMA_VERSION:
        manifest = foundation_manifest()
    else:
        defaults = foundation_manifest()
        manifest['updated_at'] = now_iso()
        paths = manifest.get('paths') if isinstance(manifest.get('paths'), dict) else {}
        paths.update({key: value for key, value in defaults['paths'].items() if key not in paths})
        manifest['paths'] = paths
        supported = list(manifest.get('supported_kinds') or [])
        for value in defaults['supported_kinds']:
            if value not in supported:
                supported.append(value)
        manifest['supported_kinds'] = supported
        manifest.setdefault('canon_modes', ROLEPLAY_CANON_MODES)
        manifest.setdefault('output_presets', ROLEPLAY_OUTPUT_PRESETS)
        manifest.setdefault('packet_layers', ROLEPLAY_PACKET_LAYERS)
        templates = manifest.get('templates') if isinstance(manifest.get('templates'), dict) else {}
        templates.update({key: value for key, value in defaults['templates'].items() if key not in templates})
        manifest['templates'] = templates

    _write_json(ROLEPLAY_FOUNDATION_PATH, manifest)
    return manifest



def _count_json_records(path: Path) -> int:
    return len(list(path.glob('*.json')))



def foundation_stats() -> dict[str, int]:
    ensure_roleplay_foundation()
    return {
        'universes': _count_json_records(ROLEPLAY_UNIVERSES_DIR),
        'worlds': _count_json_records(ROLEPLAY_WORLDS_DIR),
        'regions': _count_json_records(ROLEPLAY_REGIONS_DIR),
        'cities': _count_json_records(ROLEPLAY_CITIES_DIR),
        'locations': _count_json_records(ROLEPLAY_LOCATIONS_DIR),
        'organizations': _count_json_records(ROLEPLAY_ORGANIZATIONS_DIR),
        'artifacts': _count_json_records(ROLEPLAY_ARTIFACTS_DIR),
        'rituals': _count_json_records(ROLEPLAY_RITUALS_DIR),
        'cycles': _count_json_records(ROLEPLAY_CYCLES_DIR),
        'stories': _count_json_records(ROLEPLAY_STORIES_DIR),
        'characters': _count_json_records(ROLEPLAY_CHARACTERS_DIR),
        'scenarios': _count_json_records(ROLEPLAY_SCENARIOS_DIR),
        'sessions': _count_json_records(ROLEPLAY_SESSIONS_DIR),
    }



def get_roleplay_foundation_state() -> dict[str, Any]:
    manifest = ensure_roleplay_foundation()
    return {
        'ok': True,
        'manifest': manifest,
        'stats': foundation_stats(),
        'storage_root': str(ROLEPLAY_ROOT),
        'legacy_root': str(LEGACY_ROLEPLAY_ROOT),
    }
