from __future__ import annotations

"""Assistant-specific memory profile.

This module keeps the Assistant retrieval rules separate from Roleplay memory.
The Assistant can reuse the same SQLite/Chroma foundation, but its memory
ranking should favor technical usefulness, project relevance, stable user
preferences, and safe execution guardrails instead of narrative continuity.
"""

from typing import Final

ASSISTANT_MEMORY_TYPES: Final[tuple[str, ...]] = (
    'user_preference',
    'assistant_voice_rule',
    'project_fact',
    'repo_fact',
    'bug_history',
    'fix_pattern',
    'procedural_rule',
    'failed_attempt',
    'decision_record',
    'guardrail',
    'episodic_event',
    'semantic_fact',
    # legacy compatibility types from the original assistant mirror
    'preference',
    'style_shift',
    'workflow',
    'example_output',
    'summary',
)

# Higher numbers survive the retrieval budget more often.
ASSISTANT_TYPE_WEIGHTS: Final[dict[str, float]] = {
    'guardrail': 1.24,
    'procedural_rule': 1.20,
    'fix_pattern': 1.18,
    'user_preference': 1.17,
    'assistant_voice_rule': 1.15,
    'bug_history': 1.13,
    'failed_attempt': 1.10,
    'decision_record': 1.09,
    'repo_fact': 1.08,
    'semantic_fact': 1.06,
    'episodic_event': 1.03,
    'project_fact': 1.00,
    # legacy compatibility
    'preference': 1.16,
    'style_shift': 1.12,
    'workflow': 1.08,
    'example_output': 0.90,
    'summary': 0.72,
}

# Prevent one class of memory from flooding the context pack.
ASSISTANT_TYPE_LIMITS: Final[dict[str, int]] = {
    'guardrail': 2,
    'procedural_rule': 2,
    'fix_pattern': 2,
    'user_preference': 2,
    'assistant_voice_rule': 2,
    'bug_history': 2,
    'failed_attempt': 1,
    'decision_record': 2,
    'repo_fact': 3,
    'semantic_fact': 2,
    'episodic_event': 2,
    'project_fact': 3,
    # legacy compatibility
    'preference': 2,
    'style_shift': 1,
    'workflow': 2,
    'example_output': 1,
    'summary': 1,
}

ASSISTANT_MAX_ITEMS: Final[int] = 8
ASSISTANT_MAX_CHARS: Final[int] = 3600

PROFILE_CHUNK_TYPES: Final[tuple[str, ...]] = (
    'user_preference',
    'assistant_voice_rule',
    'guardrail',
)

PROJECT_CHUNK_TYPES: Final[tuple[str, ...]] = (
    'project_fact',
    'repo_fact',
    'procedural_rule',
    'decision_record',
    'semantic_fact',
)

SESSION_CHUNK_TYPES: Final[tuple[str, ...]] = (
    'episodic_event',
    'bug_history',
    'fix_pattern',
    'failed_attempt',
    'decision_record',
)


def normalize_assistant_chunk_type(raw: str, *, fallback: str = 'project_fact') -> str:
    """Normalize loose/legacy labels into the Assistant memory profile."""
    clean = str(raw or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'preference': 'user_preference',
        'preferences': 'user_preference',
        'style': 'assistant_voice_rule',
        'style_shift': 'assistant_voice_rule',
        'voice': 'assistant_voice_rule',
        'tone': 'assistant_voice_rule',
        'workflow': 'procedural_rule',
        'process': 'procedural_rule',
        'rule': 'procedural_rule',
        'rules': 'procedural_rule',
        'bug': 'bug_history',
        'issue': 'bug_history',
        'fix': 'fix_pattern',
        'solution': 'fix_pattern',
        'failure': 'failed_attempt',
        'failed': 'failed_attempt',
        'decision': 'decision_record',
        'record': 'decision_record',
        'guard': 'guardrail',
        'safety': 'guardrail',
        'memory': 'semantic_fact',
        'fact': 'semantic_fact',
        'repo': 'repo_fact',
        'repository': 'repo_fact',
        'project': 'project_fact',
        'event': 'episodic_event',
        'task': 'episodic_event',
    }
    clean = aliases.get(clean, clean)
    if clean in ASSISTANT_MEMORY_TYPES:
        return clean
    return fallback
