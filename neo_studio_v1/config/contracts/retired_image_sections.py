from __future__ import annotations

from copy import deepcopy
from typing import Any

"""Stage 6 retired Image Tab section contract.

Cleanup Prep, the old Reference Match shell, and Expression Editor are no longer
active Image Tab sections. IPAdapter is explicitly *not* retired and must
survive sanitization even if older docs described it near Reference Match.
"""

STAGE6_RETIRED_IMAGE_SECTION_VERSION = 'image-retired-sections-v1'

RETIRED_IMAGE_SECTION_LABELS = {
    'cleanup_prep': 'Cleanup Prep',
    'reference_match_shell': 'Reference Match shell',
    'expression_editor': 'Expression Editor',
    'legacy_regional_prompter': 'Legacy Regional Prompter',
}

RETIRED_IMAGE_FEATURE_PREFIXES = (
    'regional_',
    'regionalPrompt',
    'expression_',
    'expression_editor_',
    'expressionEditor',
    'expression_sample_',
    'reference_match_',
    'referenceMatch',
    'cleanup_prep_',
    'cleanupPrep',
)

RETIRED_IMAGE_FEATURE_KEYS = {
    'regionalBackendCapabilities',
    'regional_prompt_regions',
    'regional_backend_capabilities',
    'regional_prompt_enabled',
    'regional_prompt',
    'expression_editor_pass',
    'expression_editor_enabled',
    'expression_pass',
    'expression_enabled',
    'expression_editor',
    'expressionEditor',
    'expression_sample',
    'reference_match_enabled',
    'reference_match',
    'referenceMatch',
    'reference_match_shell',
    'cleanup_prep_enabled',
    'cleanup_prep',
    'cleanupPrep',
}

RETIRED_IMAGE_MODULE_KEYS = {
    'cleanup_prep',
    'cleanupPrep',
    'reference_match',
    'referenceMatch',
    'reference_match_shell',
    'expression_editor',
    'expressionEditor',
    'legacy_regional_prompter',
}

RETIRED_IMAGE_PREVIEW_ACTION_TYPES = {
    'expression',
    'expression_editor',
    'reference_match',
    'reference_match_shell',
    'cleanup_prep',
    'regional',
    'regional_prompt',
}

SURVIVING_REFERENCE_FEATURE_KEYS = {
    'ipadapter',
    'ipadapter_units',
    'ipadapter_image',
    'ipadapter_image_name',
    'ipadapter_model',
    'ipadapter_weight',
    'scene_director_ipadapter_units',
    'scene_director_identity_units',
    'character_profile',
    'character_profiles',
}


def _clone(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def is_retired_image_key(key: object) -> bool:
    text = str(key)
    if text in SURVIVING_REFERENCE_FEATURE_KEYS:
        return False
    return text in RETIRED_IMAGE_FEATURE_KEYS or any(text.startswith(prefix) for prefix in RETIRED_IMAGE_FEATURE_PREFIXES)


def sanitize_retired_image_sections(value: Any, *, removed: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if is_retired_image_key(key):
                if removed is not None:
                    removed.append(str(key))
                continue
            cleaned[key] = sanitize_retired_image_sections(item, removed=removed)
        return cleaned
    if isinstance(value, list):
        return [sanitize_retired_image_sections(item, removed=removed) for item in value]
    return _clone(value)


def sanitize_image_modules(modules: Any, *, removed: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(modules, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in modules.items():
        if str(key) in RETIRED_IMAGE_MODULE_KEYS or is_retired_image_key(key):
            if removed is not None:
                removed.append(str(key))
            continue
        cleaned[str(key)] = sanitize_retired_image_sections(value, removed=removed)
    return cleaned


def sanitize_preview_action_contract(payload: dict[str, Any]) -> None:
    action = payload.get('_neo_preview_action')
    if isinstance(action, str):
        if action.strip().lower() in RETIRED_IMAGE_PREVIEW_ACTION_TYPES:
            payload.pop('_neo_preview_action', None)
        return
    if not isinstance(action, dict):
        return
    action_type = str(action.get('action_type') or action.get('type') or '').strip().lower()
    if action_type in RETIRED_IMAGE_PREVIEW_ACTION_TYPES:
        payload.pop('_neo_preview_action', None)
        payload.pop('preview_action', None)
        if action_type in {'expression', 'expression_editor'}:
            payload['detailer_output_pass'] = False
        return
    payload['_neo_preview_action'] = sanitize_retired_image_sections(action)


def sanitize_builder_contract(payload: dict[str, Any]) -> None:
    contract = payload.get('_neo_builder_contract')
    if not isinstance(contract, dict):
        return
    contract = sanitize_retired_image_sections(contract)
    preview = contract.get('preview_action')
    if isinstance(preview, dict):
        action_type = str(preview.get('action_type') or preview.get('type') or '').strip().lower()
        if action_type in RETIRED_IMAGE_PREVIEW_ACTION_TYPES:
            contract.pop('preview_action', None)
        else:
            contract['preview_action'] = sanitize_retired_image_sections(preview)
    payload['_neo_builder_contract'] = contract


def sanitize_image_payload_for_retired_sections(payload: Any) -> tuple[dict[str, Any], list[str]]:
    removed: list[str] = []
    cleaned = sanitize_retired_image_sections(payload if isinstance(payload, dict) else {}, removed=removed)
    if not isinstance(cleaned, dict):
        cleaned = {}
    if isinstance(cleaned.get('modules'), dict):
        cleaned['modules'] = sanitize_image_modules(cleaned.get('modules'), removed=removed)
    if isinstance(cleaned.get('image_state'), dict) and isinstance(cleaned['image_state'].get('modules'), dict):
        cleaned['image_state']['modules'] = sanitize_image_modules(cleaned['image_state'].get('modules'), removed=removed)
    sanitize_preview_action_contract(cleaned)
    sanitize_builder_contract(cleaned)
    cleaned['_neo_retired_sections_sanitized'] = True
    cleaned['_neo_retired_sections_version'] = STAGE6_RETIRED_IMAGE_SECTION_VERSION
    if removed:
        cleaned['_neo_retired_sections_removed_count'] = len(set(removed))
    return cleaned, removed
