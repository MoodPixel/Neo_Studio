from __future__ import annotations

from typing import Any

VALID_OUTPUT_PRESETS = {'roleplay', 'short_story', 'novel', 'cinematic'}
VALID_INTERACTION_MODES = {'roleplay', 'authoring'}
AUTHORING_OUTPUT_PRESETS = {'short_story', 'novel', 'cinematic'}
DEFAULT_AUTHORING_OUTPUT_PRESET = 'novel'


def _clean(value: Any, *, lower: bool = False) -> str:
    text = str(value or '').strip()
    return text.lower() if lower else text


def normalize_mode_model(
    output_preset: str = '',
    interaction_mode: str = '',
    *,
    prefer: str = 'output',
    fallback_authoring_output: str = DEFAULT_AUTHORING_OUTPUT_PRESET,
) -> dict[str, Any]:
    clean_output = _clean(output_preset, lower=True)
    clean_interaction = _clean(interaction_mode, lower=True)
    clean_prefer = _clean(prefer, lower=True)
    authoring_fallback = _clean(fallback_authoring_output, lower=True)
    if authoring_fallback not in AUTHORING_OUTPUT_PRESETS:
        authoring_fallback = DEFAULT_AUTHORING_OUTPUT_PRESET
    if clean_output not in VALID_OUTPUT_PRESETS:
        clean_output = ''
    if clean_interaction not in VALID_INTERACTION_MODES:
        clean_interaction = ''

    if clean_prefer == 'interaction':
        if clean_interaction == 'authoring':
            clean_output = clean_output if clean_output in AUTHORING_OUTPUT_PRESETS else authoring_fallback
        elif clean_interaction == 'roleplay':
            clean_output = clean_output if clean_output in VALID_OUTPUT_PRESETS else 'roleplay'
        else:
            clean_output = 'roleplay'
            clean_interaction = 'roleplay'
    else:
        if clean_output in AUTHORING_OUTPUT_PRESETS:
            clean_interaction = clean_interaction if clean_interaction in VALID_INTERACTION_MODES else 'authoring'
        else:
            clean_output = 'roleplay'
            clean_interaction = 'roleplay'

    goal_labels = {
        'roleplay': 'Roleplay',
        'short_story': 'Short story authoring',
        'novel': 'Novel authoring',
        'cinematic': 'Cinematic authoring',
    }
    goal_key = clean_output if clean_output in AUTHORING_OUTPUT_PRESETS else 'roleplay'
    return {
        'output_preset': clean_output,
        'interaction_mode': clean_interaction,
        'goal_key': goal_key,
        'goal_label': goal_labels.get(goal_key, 'Roleplay'),
        'is_authoring': clean_interaction == 'authoring',
    }
