from __future__ import annotations

from copy import deepcopy
from typing import Any

ROLEPLAY_V2_BUILDER_SHARED_SCHEMA_VERSION = 1

ROLEPLAY_V2_CANON_STATUS_VALUES = [
    'primary_canon',
    'secondary_canon',
    'alternate_canon',
    'uncertain_canon',
    'legacy_canon',
]

ROLEPLAY_V2_VISIBILITY_VALUES = [
    'public',
    'restricted',
    'hidden',
    'author_private',
]

ROLEPLAY_V2_RECORD_STATUS_VALUES = [
    'draft',
    'draft_stub',
    'reviewed',
    'approved',
    'runtime_ready',
    'archived',
]

ROLEPLAY_V2_SHARED_TOP_LEVEL_KEYS = [
    'id',
    'kind',
    'schema_version',
    'source_container_id',
    'label',
    'display_label',
    'summary',
    'canon_status',
    'visibility',
    'tags',
    'tone_tags',
    'links',
    'fields',
    'memory_hints',
    'meta',
]

ROLEPLAY_V2_SHARED_FIELD_FAMILIES = [
    'identity',
    'placement_scope',
    'classification_state',
    'appearance_presence',
    'public_hidden_truth',
    'relationships',
    'story_roleplay_use',
    'scene_runtime_use',
    'scene_utility',
    'rich_authoring',
]

ROLEPLAY_V2_SHARED_RECORD_CONTRACT = {
    'schema_version': ROLEPLAY_V2_BUILDER_SHARED_SCHEMA_VERSION,
    'authoring_mode': 'forge_payload_matches_saved_entity_record_shape',
    'record_envelope': {
        'required_top_level_keys': list(ROLEPLAY_V2_SHARED_TOP_LEVEL_KEYS),
        'primary_label_key': 'label',
        'primary_summary_key': 'summary',
        'builder_specific_ui_labels_allowed': True,
        'builder_specific_label_aliases': {
            'scenario': 'title',
            'legend': 'title',
            'character': 'name',
            'world': 'name',
            'universe': 'name',
            'region': 'name',
            'city': 'name',
            'location': 'name',
            'organization': 'name',
            'artifact': 'name',
            'ritual': 'name',
            'cycle': 'name',
            'creature': 'name',
        },
        'notes': [
            'Forge templates, loaded builder payloads, and saved entity records should share the same top-level shape.',
            'Canonical links should remain nested under links.scope and links.related instead of being flattened for authoring.',
        ],
    },
    'shared_enums': {
        'canon_status': list(ROLEPLAY_V2_CANON_STATUS_VALUES),
        'visibility': list(ROLEPLAY_V2_VISIBILITY_VALUES),
        'record_status': list(ROLEPLAY_V2_RECORD_STATUS_VALUES),
    },
    'shared_field_families': list(ROLEPLAY_V2_SHARED_FIELD_FAMILIES),
    'save_rules': {
        'single_schema_of_truth': True,
        'backward_compatibility_required': False,
        'builder_payload_equals_saved_shape': True,
    },
    'id_policy': {
        'strategy': 'kind_slug_with_collision_suffix',
        'kind_prefixed_ids': True,
        'label_renames_do_not_rewrite_existing_ids': True,
        'notes': [
            'New records should receive stable kind-prefixed slug IDs on first save.',
            'Existing saved IDs stay locked even if the label changes later.',
        ],
    },
}


def build_shared_record_contract() -> dict[str, Any]:
    return deepcopy(ROLEPLAY_V2_SHARED_RECORD_CONTRACT)
