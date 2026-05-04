from __future__ import annotations

from copy import deepcopy
from typing import Any

ROLEPLAY_V2_PRIORITY_VALUES = ['low', 'medium', 'high']
ROLEPLAY_V2_REVEAL_GATING_VALUES = [
    'open',
    'staged',
    'gated_by_trust',
    'gated_by_discovery',
    'gm_only',
    'restricted',
]
ROLEPLAY_V2_MEMORY_FRAGMENT_TYPE_VALUES = [
    'identity_fact',
    'world_fact',
    'semantic_fact',
    'canon_guard',
    'callback_anchor',
    'relationship_belief',
    'shared_memory',
    'episodic_event',
    'location_state',
    'scene_pressure',
    'story_hook',
    'self_belief',
    'goal',
    'secret',
    'voice_rule',
]
ROLEPLAY_V2_MEMORY_DURABILITY_VALUES = [
    'session_only',
    'continuity',
    'long_term',
]

ROLEPLAY_V2_SHARED_MEMORY_HINTS_CONTRACT = {
    'schema_version': 1,
    'notes': [
        'Memory hints should supplement canonical fields, not replace them.',
        'Callback anchors and runtime guard notes should stay short and retrieval-friendly.',
    ],
    'shape': {
        'memory_anchors': [],
        'sensory_anchors': [],
        'callback_anchors': [],
        'belief_seeds': [],
        'recurring_omens': [],
        'taboo_triggers': [],
        'runtime_guard_notes': '',
        'reveal_gating': {
            'mode': 'staged',
            'notes': '',
        },
        'priority': {
            'scene_use_relevance': 'high',
            'emotional_salience': 'high',
            'continuity_priority': 'high',
        },
        'memory_fragment_candidates': [],
    },
    'optional_extensions': [
        'relationship_anchors',
        'identity_anchors',
        'location_anchors',
    ],
    'priority_values': list(ROLEPLAY_V2_PRIORITY_VALUES),
    'reveal_gating_values': list(ROLEPLAY_V2_REVEAL_GATING_VALUES),
    'memory_fragment_type_values': list(ROLEPLAY_V2_MEMORY_FRAGMENT_TYPE_VALUES),
    'durability_values': list(ROLEPLAY_V2_MEMORY_DURABILITY_VALUES),
    'memory_fragment_candidate_shape': {
        'path': 'fields.public_hidden_truth.hidden_truth',
        'fragment_type': 'canon_guard',
        'visibility': 'restricted',
        'priority': 'high',
        'durability': 'continuity',
        'notes': '',
    },
}


def build_shared_memory_hints_contract() -> dict[str, Any]:
    return deepcopy(ROLEPLAY_V2_SHARED_MEMORY_HINTS_CONTRACT)
