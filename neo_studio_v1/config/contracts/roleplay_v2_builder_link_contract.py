from __future__ import annotations

from copy import deepcopy
from typing import Any

ROLEPLAY_V2_LINK_RESOLUTION_STATES = [
    'resolved',
    'stub',
    'unresolved_text',
]

ROLEPLAY_V2_LINK_CARDINALITY_VALUES = [
    'one',
    'many',
]

ROLEPLAY_V2_LINK_STATUS_VALUES = [
    'active',
    'former',
    'hidden',
    'contested',
]

ROLEPLAY_V2_LINK_SOURCE_MODE_VALUES = [
    'manual',
    'imported',
    'inferred',
]

ROLEPLAY_V2_LINK_FAMILIES = {
    'scope': [
        'universe_id', 'world_id', 'region_id', 'city_id', 'location_id',
    ],
    'parent': [
        'parent_region_id', 'parent_location_id', 'parent_organization_id', 'parent_city_id',
    ],
    'state': [
        'origin_world_id', 'current_world_id', 'origin_region_id', 'current_region_id',
        'origin_city_id', 'current_city_id', 'origin_location_id', 'current_location_id',
        'base_location_id', 'capital_city_id', 'capital_of_region_id', 'seat_location_id', 'primary_world_id',
        'current_holder_id', 'source_organization_id', 'source_ritual_id', 'source_legend_id',
        'source_artifact_id', 'source_cycle_id',
    ],
    'related': [
        'world_ids', 'region_ids', 'city_ids', 'location_ids',
        'character_ids', 'organization_ids', 'location_ids', 'artifact_ids', 'ritual_ids', 'cycle_ids', 'creature_ids', 'legend_ids', 'scenario_ids',
        'cast_character_ids', 'leader_character_ids', 'member_character_ids',
        'ally_organization_ids', 'rival_organization_ids',
        'linked_character_ids', 'linked_organization_ids', 'linked_location_ids', 'anchor_entity_id',
        'linked_artifact_ids', 'linked_ritual_ids', 'linked_cycle_ids', 'linked_creature_ids',
    ],
}

ROLEPLAY_V2_NORMALIZED_EDGE_KEYS = [
    'source_id',
    'source_kind',
    'family',
    'slot',
    'relation',
    'reverse_relation',
    'target_id',
    'target_kind',
    'target_kind_candidates',
    'cardinality',
    'status',
    'visibility',
    'source_mode',
    'notes',
]

ROLEPLAY_V2_SHARED_LINK_CONTRACT = {
    'schema_version': 1,
    'strategy': 'canonical_nested_forward_links_with_derived_reverse_views',
    'authoring_shape': {
        'source_container_id': '',
        'scope': {},
        'related': {},
        'reverse_links': {
            'strategy': 'derived',
            'materialized': {},
        },
    },
    'slot_rules': {
        'single_link_suffix': '_id',
        'multi_link_suffix': '_ids',
        'families': deepcopy(ROLEPLAY_V2_LINK_FAMILIES),
        'notes': [
            'Use explicit semantic slot names rather than generic cast_ids/member_ids/holder_entity_id patterns.',
            'Featured or presentation-only lists should not be treated as core graph edges.',
            'Reverse views should group incoming edges by semantic reverse_relation rather than raw slot name.',
        ],
    },
    'normalized_edge_keys': list(ROLEPLAY_V2_NORMALIZED_EDGE_KEYS),
    'normalized_edge_enums': {
        'link_resolution_status': list(ROLEPLAY_V2_LINK_RESOLUTION_STATES),
        'cardinality': list(ROLEPLAY_V2_LINK_CARDINALITY_VALUES),
        'status': list(ROLEPLAY_V2_LINK_STATUS_VALUES),
        'source_mode': list(ROLEPLAY_V2_LINK_SOURCE_MODE_VALUES),
    },
    'graph_projection_rules': {
        'reverse_links_are_materialized_from_forward_edges': True,
        'relationship_sections_emit_graph_edges': True,
        'save_time_graph_refresh': True,
        'notes': [
            'Forward links remain the authored source of truth.',
            'Reverse links and normalized edge summaries should be regenerated after each save.',
        ],
    },
    'relationship_entry_shape': {
        'target_entity_id': '',
        'target_entity_kind': '',
        'target_label': '',
        'link_resolution_status': 'resolved',
        'relationship_type': '',
        'subtype': '',
        'status': 'active',
        'visibility': 'public',
        'emotional_weight': 'medium',
        'trust_level': 5,
        'conflict_level': 0,
        'attachment_valence': 'neutral',
        'power_dynamic': '',
        'public_summary': '',
        'hidden_truth': '',
        'history_summary': '',
        'scene_behavior_notes': '',
        'memory_hints': {
            'callback_anchors': [],
            'scene_relevance': 'medium',
        },
    },
}


def build_shared_link_contract() -> dict[str, Any]:
    return deepcopy(ROLEPLAY_V2_SHARED_LINK_CONTRACT)


