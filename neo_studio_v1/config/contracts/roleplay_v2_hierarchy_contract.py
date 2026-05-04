from __future__ import annotations

from copy import deepcopy
from typing import Any

ROLEPLAY_V2_AUTHORING_HIERARCHY_VERSION = 1

ROLEPLAY_V2_AUTHORING_ENTRY_POINTS: list[dict[str, Any]] = [
    {
        'entry_id': 'universe',
        'kind': 'universe',
        'label': 'Build a Universe',
        'description': 'Start from the widest setting shell and attach worlds under it.',
        'recommended_for': ['multi-world planning', 'cosmology-first projects', 'large worldbuilding'],
    },
    {
        'entry_id': 'world',
        'kind': 'world',
        'label': 'Build a World',
        'description': 'Start from a single setting when you do not need a full universe wrapper first.',
        'recommended_for': ['single-setting projects', 'realm-first planning', 'regional story spaces'],
    },
    {
        'entry_id': 'character',
        'kind': 'character',
        'label': 'Build a Character',
        'description': 'Start from a person or lead POV and attach them to world scope later.',
        'recommended_for': ['character-first writing', 'roleplay setup', 'romance or rivalry arcs'],
    },
    {
        'entry_id': 'location',
        'kind': 'location',
        'label': 'Build a Location',
        'description': 'Start from a place, setpiece, or scene anchor and connect the rest around it.',
        'recommended_for': ['scene-first writing', 'city or landmark planning', 'travel-heavy stories'],
    },
    {
        'entry_id': 'organization',
        'kind': 'organization',
        'label': 'Build an Organization',
        'description': 'Start from the group, faction, court, or guild that drives the conflict.',
        'recommended_for': ['political stories', 'faction-heavy settings', 'court intrigue'],
    },
    {
        'entry_id': 'scenario',
        'kind': 'scenario',
        'label': 'Build a Story Scenario',
        'description': 'Start from the active premise and hook it into the setting and cast.',
        'recommended_for': ['plot-first writing', 'session seeds', 'scene kickoff planning'],
    },
    {
        'entry_id': 'continue_scope',
        'kind': '',
        'label': 'Continue Existing Scope',
        'description': 'Reopen a saved chain and keep building downward from the current scope.',
        'recommended_for': ['ongoing projects', 'large universes', 'incremental worldbuilding'],
    },
]

ROLEPLAY_V2_SUBCATEGORY_RULES: dict[str, dict[str, Any]] = {
    'location': {
        'field_path': 'fields.identity.location_type',
        'label': 'Location Type',
        'values': ['hall', 'temple', 'market', 'street', 'port', 'gate', 'forest_site', 'ruin', 'estate', 'tavern', 'archive', 'crypt', 'fort', 'bridge', 'sanctum', 'wild_site', 'hybrid'],
    },
    'character': {
        'field_path': 'fields.identity.designation',
        'label': 'Designation',
        'values': ['alpha', 'omega', 'beta', 'enigma', 'normal'],
    },
    'organization': {
        'field_path': 'fields.identity.group_type',
        'label': 'Group Type',
        'values': ['royal_house', 'court', 'guild', 'religious_order', 'military_order', 'criminal_network', 'cult', 'archive_or_scholarly_body', 'mercantile_power', 'clan', 'political_faction', 'rebel_group', 'intelligence_network', 'hybrid'],
    },
    'artifact': {
        'field_path': 'fields.classification_state.rarity',
        'label': 'Rarity',
        'values': ['common', 'uncommon', 'rare', 'very_rare', 'legendary', 'unique'],
    },
    'ritual': {
        'field_path': 'fields.identity.practice_type',
        'label': 'Practice Type',
        'values': ['ritual', 'spell', 'potion', 'technique', 'discipline', 'binding', 'healing_method', 'combat_method', 'forbidden_practice', 'hybrid'],
    },
    'cycle': {
        'field_path': 'fields.identity.system_type',
        'label': 'System Type',
        'values': ['cycle', 'condition', 'curse', 'disease', 'metaphysical_system', 'social_system', 'biological_system', 'transformation_system', 'environmental_pattern', 'hybrid'],
    },
    'creature': {
        'field_path': 'fields.identity.category',
        'label': 'Category',
        'values': ['animal', 'beast', 'predator', 'mount', 'companion', 'magical_fauna', 'sentient_being', 'hidden_being', 'aquatic_creature', 'avian_creature', 'hybrid'],
    },
    'legend': {
        'field_path': 'fields.identity.legend_type',
        'label': 'Legend Type',
        'values': ['origin_legend', 'prophecy', 'historical_legend', 'saint_or_hero_legend', 'warning_tale', 'monster_legend', 'sacred_legend', 'dynastic_legend', 'hidden_history', 'hybrid'],
    },
}

ROLEPLAY_V2_AUTHORING_HIERARCHY: dict[str, dict[str, Any]] = {
    'universe': {
        'display_name': 'Universe',
        'lane': 'setting',
        'entry_label': 'Build a Universe',
        'scope_tier': 'root',
        'parent_kinds': [],
        'primary_parent_kind': '',
        'scope_slots': [],
        'auto_scope_paths': [],
        'child_kinds': ['world', 'legend', 'organization', 'cycle', 'scenario'],
        'recommended_child_kinds': ['world'],
        'scope_priority': [],
    },
    'world': {
        'display_name': 'World',
        'lane': 'setting',
        'entry_label': 'Build a World',
        'scope_tier': 'world',
        'parent_kinds': ['universe'],
        'primary_parent_kind': 'universe',
        'scope_slots': ['universe_id'],
        'auto_scope_paths': ['links.scope.universe_id'],
        'child_kinds': ['region', 'city', 'location', 'character', 'organization', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario'],
        'recommended_child_kinds': ['region', 'city', 'location', 'character'],
        'scope_priority': ['universe_id'],
    },
    'region': {
        'display_name': 'Region / Kingdom',
        'lane': 'setting',
        'entry_label': 'Build a Region',
        'scope_tier': 'regional',
        'parent_kinds': ['world'],
        'primary_parent_kind': 'world',
        'scope_slots': ['world_id', 'parent_region_id', 'capital_city_id', 'seat_location_id'],
        'auto_scope_paths': ['links.scope.world_id'],
        'child_kinds': ['city', 'location', 'character', 'organization', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario'],
        'recommended_child_kinds': ['city', 'location', 'character', 'organization'],
        'scope_priority': ['world_id', 'parent_region_id', 'capital_city_id', 'seat_location_id'],
    },
    'city': {
        'display_name': 'City / Settlement',
        'lane': 'setting',
        'entry_label': 'Build a City',
        'scope_tier': 'city',
        'parent_kinds': ['region', 'world'],
        'primary_parent_kind': 'region',
        'scope_slots': ['world_id', 'region_id', 'parent_city_id', 'capital_of_region_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id'],
        'child_kinds': ['location', 'character', 'organization', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario'],
        'recommended_child_kinds': ['location', 'character', 'organization', 'scenario'],
        'scope_priority': ['world_id', 'region_id', 'parent_city_id', 'capital_of_region_id'],
    },
    'location': {
        'display_name': 'Location',
        'lane': 'setting',
        'entry_label': 'Build a Location',
        'scope_tier': 'scene_anchor',
        'parent_kinds': ['city', 'region', 'world', 'universe'],
        'primary_parent_kind': 'city',
        'scope_slots': ['universe_id', 'world_id', 'region_id', 'city_id', 'parent_location_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id', 'links.scope.city_id'],
        'child_kinds': ['character', 'organization', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario'],
        'recommended_child_kinds': ['character', 'organization', 'artifact', 'scenario'],
        'scope_priority': ['universe_id', 'world_id', 'region_id', 'city_id', 'parent_location_id'],
    },
    'character': {
        'display_name': 'Character',
        'lane': 'people',
        'entry_label': 'Build a Character',
        'scope_tier': 'person',
        'parent_kinds': ['world', 'region', 'city', 'location'],
        'primary_parent_kind': 'city',
        'scope_slots': ['origin_world_id', 'origin_region_id', 'origin_city_id', 'origin_location_id', 'current_world_id', 'current_region_id', 'current_city_id', 'current_location_id'],
        'auto_scope_paths': ['links.scope.current_world_id', 'links.scope.current_region_id', 'links.scope.current_city_id', 'links.scope.current_location_id'],
        'child_kinds': ['artifact', 'ritual', 'scenario'],
        'recommended_child_kinds': ['scenario'],
        'scope_priority': ['current_world_id', 'current_region_id', 'current_city_id', 'current_location_id', 'origin_world_id', 'origin_region_id', 'origin_city_id', 'origin_location_id'],
    },
    'organization': {
        'display_name': 'Organization',
        'lane': 'institutions',
        'entry_label': 'Build an Organization',
        'scope_tier': 'group',
        'parent_kinds': ['universe', 'world', 'region', 'city', 'location'],
        'primary_parent_kind': 'city',
        'scope_slots': ['universe_id', 'world_id', 'region_id', 'city_id', 'base_location_id', 'parent_organization_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id', 'links.scope.city_id', 'links.scope.base_location_id'],
        'child_kinds': ['character', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario'],
        'recommended_child_kinds': ['character', 'artifact', 'scenario'],
        'scope_priority': ['universe_id', 'world_id', 'region_id', 'city_id', 'base_location_id', 'parent_organization_id'],
    },
    'artifact': {
        'display_name': 'Artifact',
        'lane': 'arcana',
        'entry_label': 'Build an Artifact',
        'scope_tier': 'object',
        'parent_kinds': ['world', 'region', 'city', 'location', 'character', 'organization', 'ritual', 'legend'],
        'primary_parent_kind': 'location',
        'scope_slots': ['world_id', 'region_id', 'city_id', 'location_id', 'current_holder_id', 'source_organization_id', 'source_ritual_id', 'source_legend_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id', 'links.scope.city_id', 'links.scope.location_id'],
        'child_kinds': ['ritual', 'scenario'],
        'recommended_child_kinds': ['scenario'],
        'scope_priority': ['world_id', 'region_id', 'city_id', 'location_id', 'current_holder_id', 'source_organization_id', 'source_ritual_id', 'source_legend_id'],
    },
    'ritual': {
        'display_name': 'Ritual / Practice',
        'lane': 'arcana',
        'entry_label': 'Build a Ritual',
        'scope_tier': 'practice',
        'parent_kinds': ['world', 'region', 'location', 'organization', 'artifact', 'legend'],
        'primary_parent_kind': 'location',
        'scope_slots': ['world_id', 'region_id', 'location_id', 'source_artifact_id', 'source_organization_id', 'source_legend_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id', 'links.scope.location_id'],
        'child_kinds': ['artifact', 'cycle', 'creature', 'scenario'],
        'recommended_child_kinds': ['artifact', 'cycle', 'scenario'],
        'scope_priority': ['world_id', 'region_id', 'location_id', 'source_artifact_id', 'source_organization_id', 'source_legend_id'],
    },
    'cycle': {
        'display_name': 'Cycle / System',
        'lane': 'arcana',
        'entry_label': 'Build a Cycle',
        'scope_tier': 'system',
        'parent_kinds': ['universe', 'world', 'region', 'location', 'organization', 'legend'],
        'primary_parent_kind': 'world',
        'scope_slots': ['universe_id', 'world_id', 'region_id', 'location_id', 'source_organization_id', 'source_legend_id'],
        'auto_scope_paths': ['links.scope.universe_id', 'links.scope.world_id', 'links.scope.region_id', 'links.scope.location_id'],
        'child_kinds': ['artifact', 'creature', 'scenario'],
        'recommended_child_kinds': ['scenario'],
        'scope_priority': ['universe_id', 'world_id', 'region_id', 'location_id', 'source_organization_id', 'source_legend_id'],
    },
    'creature': {
        'display_name': 'Creature',
        'lane': 'people',
        'entry_label': 'Build a Creature',
        'scope_tier': 'being',
        'parent_kinds': ['world', 'region', 'location', 'organization', 'cycle', 'legend'],
        'primary_parent_kind': 'location',
        'scope_slots': ['world_id', 'region_id', 'location_id', 'source_cycle_id', 'source_organization_id', 'source_legend_id'],
        'auto_scope_paths': ['links.scope.world_id', 'links.scope.region_id', 'links.scope.location_id'],
        'child_kinds': ['scenario'],
        'recommended_child_kinds': ['scenario'],
        'scope_priority': ['world_id', 'region_id', 'location_id', 'source_cycle_id', 'source_organization_id', 'source_legend_id'],
    },
    'legend': {
        'display_name': 'Legend',
        'lane': 'history',
        'entry_label': 'Build a Legend',
        'scope_tier': 'history',
        'parent_kinds': ['universe', 'world', 'region', 'location'],
        'primary_parent_kind': 'world',
        'scope_slots': ['universe_id', 'world_id', 'region_id', 'location_id'],
        'auto_scope_paths': ['links.scope.universe_id', 'links.scope.world_id', 'links.scope.region_id', 'links.scope.location_id'],
        'child_kinds': ['artifact', 'ritual', 'cycle', 'creature', 'scenario'],
        'recommended_child_kinds': ['scenario'],
        'scope_priority': ['universe_id', 'world_id', 'region_id', 'location_id'],
    },
    'scenario': {
        'display_name': 'Scenario',
        'lane': 'story',
        'entry_label': 'Build a Story Scenario',
        'scope_tier': 'story_seed',
        'parent_kinds': ['universe', 'world', 'region', 'city', 'location', 'character', 'organization'],
        'primary_parent_kind': 'location',
        'scope_slots': ['universe_id', 'world_id', 'region_id', 'city_id', 'location_id'],
        'auto_scope_paths': ['links.scope.universe_id', 'links.scope.world_id', 'links.scope.region_id', 'links.scope.city_id', 'links.scope.location_id'],
        'child_kinds': [],
        'recommended_child_kinds': [],
        'scope_priority': ['universe_id', 'world_id', 'region_id', 'city_id', 'location_id'],
    },
}


def get_roleplay_v2_hierarchy_entry(kind: str) -> dict[str, Any]:
    clean_kind = str(kind or '').strip().lower()
    entry = ROLEPLAY_V2_AUTHORING_HIERARCHY.get(clean_kind) or {}
    subcategory = ROLEPLAY_V2_SUBCATEGORY_RULES.get(clean_kind)
    payload = deepcopy(entry)
    payload['kind'] = clean_kind
    payload['subcategory'] = deepcopy(subcategory) if subcategory else None
    return payload



def build_roleplay_v2_authoring_hierarchy_contract() -> dict[str, Any]:
    return {
        'hierarchy_version': ROLEPLAY_V2_AUTHORING_HIERARCHY_VERSION,
        'entry_points': deepcopy(ROLEPLAY_V2_AUTHORING_ENTRY_POINTS),
        'kinds': {kind: get_roleplay_v2_hierarchy_entry(kind) for kind in ROLEPLAY_V2_AUTHORING_HIERARCHY.keys()},
        'subcategory_rules': deepcopy(ROLEPLAY_V2_SUBCATEGORY_RULES),
        'notes': {
            'collection_rule': 'Hierarchy changes how records are collected and linked, not the stable saved record ids.',
            'autofill_rule': 'Parent scope ids should auto-fill from the current scope but stay editable.',
            'story_rule': 'Universe / World / Era belong to authoring scope. Storyline / Session / Branch belong to evolving narrative scope.',
        },
    }



def build_roleplay_v2_hierarchy_context(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = get_roleplay_v2_hierarchy_entry(kind)
    raw = payload if isinstance(payload, dict) else {}
    scope = raw.get('links', {}).get('scope') if isinstance(raw.get('links'), dict) else {}
    scope = scope if isinstance(scope, dict) else {}
    scope_priority = list(entry.get('scope_priority') or entry.get('scope_slots') or [])
    current_scope = []
    for slot in scope_priority:
        value = str(scope.get(slot) or '').strip()
        if value:
            current_scope.append({'slot': slot, 'value': value, 'label': slot.replace('_', ' ')})
    return {
        'kind': entry.get('kind') or str(kind or '').strip().lower(),
        'entry_label': entry.get('entry_label') or '',
        'lane': entry.get('lane') or '',
        'scope_tier': entry.get('scope_tier') or '',
        'parent_kinds': deepcopy(entry.get('parent_kinds') or []),
        'primary_parent_kind': entry.get('primary_parent_kind') or '',
        'scope_slots': deepcopy(entry.get('scope_slots') or []),
        'auto_scope_paths': deepcopy(entry.get('auto_scope_paths') or []),
        'child_kinds': deepcopy(entry.get('child_kinds') or []),
        'recommended_child_kinds': deepcopy(entry.get('recommended_child_kinds') or []),
        'subcategory': deepcopy(entry.get('subcategory')) if entry.get('subcategory') else None,
        'current_scope': current_scope,
    }
