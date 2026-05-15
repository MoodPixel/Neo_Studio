from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

from .external_extension_payloads import stamp_external_extension_payload_contract
from .image_output_selection import stamp_output_selection_contract
from .retired_image_sections import sanitize_image_payload_for_retired_sections

ImageCommandType = Literal[
    'main_generate',
    'preview_action',
    'preview_upscale',
    'preview_adetailer',
    'upscale_lab',
    'image_upscale',
    'supir',
    'scene_director',
]

_IMAGE_COMMAND_VERSION = 'image-command-v1'
_PREVIEW_ACTIONS = {'preview_action', 'preview_upscale', 'preview_adetailer'}
_UPSCALE_ACTIONS = {'image_upscale', 'upscale_lab'}


def _deepcopy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _clean_dict(value: Any) -> dict[str, Any]:
    return _deepcopy(value) if isinstance(value, dict) else {}


@dataclass(slots=True)
class ImagePayloadEnvelope:
    """Stage 2 Image Tab command envelope.

    This is intentionally additive. The legacy workflow builders still receive a
    flattened payload, but the UI/backend boundary can now describe *which*
    command is being executed instead of relying on mixed mega-payload flags.
    """

    command_type: str = 'main_generate'
    version: str = _IMAGE_COMMAND_VERSION
    image_state: dict[str, Any] = field(default_factory=dict)
    build: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    modules: dict[str, Any] = field(default_factory=dict)
    preview_action: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    legacy_payload: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_image_payload_envelope(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(
        payload.get('version') == _IMAGE_COMMAND_VERSION
        or payload.get('command_type')
        or payload.get('image_command')
    )


def infer_image_command_type(payload: dict[str, Any] | None) -> str:
    payload = payload if isinstance(payload, dict) else {}
    explicit = str(payload.get('command_type') or payload.get('image_command') or '').strip().lower()
    if explicit:
        return explicit
    preview_action = payload.get('preview_action') if isinstance(payload.get('preview_action'), dict) else {}
    legacy_preview = payload.get('_neo_preview_action') or preview_action.get('action_type') or preview_action.get('type')
    legacy_preview = str(legacy_preview or '').strip().lower()
    if legacy_preview:
        if 'adetailer' in legacy_preview or 'detailer' in legacy_preview:
            return 'preview_adetailer'
        if 'upscale' in legacy_preview:
            return 'preview_upscale'
        return 'preview_action'
    mode = str(payload.get('mode') or payload.get('workflow_type') or payload.get('refine_mode') or '').strip().lower()
    if mode in {'upscale', 'upscale_lab'}:
        return 'upscale_lab'
    if mode == 'supir':
        return 'supir'
    return 'main_generate'


def build_image_payload_envelope(
    legacy_payload: dict[str, Any] | None,
    *,
    command_type: str | None = None,
    image_state: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    preview_action: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy_payload, _stage6_removed = sanitize_image_payload_for_retired_sections(_clean_dict(legacy_payload))
    command = str(command_type or infer_image_command_type(legacy_payload) or 'main_generate').strip().lower()
    state = _clean_dict(image_state or legacy_payload.get('image_state'))
    build = _clean_dict(state.get('build'))
    state_source = _clean_dict(state.get('source'))
    modules = _clean_dict(state.get('modules'))
    if isinstance(legacy_payload.get('dynamic_thresholding'), dict) and not isinstance(modules.get('dynamic_thresholding'), dict):
        modules['dynamic_thresholding'] = _clean_dict(legacy_payload.get('dynamic_thresholding'))
    source_block = {**state_source, **_clean_dict(source or legacy_payload.get('source'))}
    preview_block = _clean_dict(preview_action or legacy_payload.get('preview_action'))
    if legacy_payload.get('generationPreviewActionTarget') and not preview_block.get('target'):
        preview_block['target'] = legacy_payload.get('generationPreviewActionTarget')
    return ImagePayloadEnvelope(
        command_type=command,
        image_state=state,
        build=build,
        source=source_block,
        settings=legacy_payload,
        modules=modules,
        preview_action=preview_block,
        lineage=_clean_dict(lineage or legacy_payload.get('lineage')),
        legacy_payload=legacy_payload,
        meta={
            'stage': 'stage6_retired_sections_safe_removal',
            'legacy_compatible': True,
            **_clean_dict(meta or legacy_payload.get('meta')),
        },
    ).to_dict()


def flatten_image_payload_envelope(envelope_or_payload: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return a legacy-compatible payload plus the envelope metadata.

    The flattening order is deliberately conservative:
    legacy settings remain the base, then canonical image state fills missing
    build/source/module fields, and finally command metadata is stamped for
    diagnostics. This avoids Stage 2 changing workflow behavior while removing
    ambiguity at the route boundary.
    """
    if not isinstance(envelope_or_payload, dict):
        return {}, None
    if not is_image_payload_envelope(envelope_or_payload):
        legacy, _stage6_removed = sanitize_image_payload_for_retired_sections(_clean_dict(envelope_or_payload))
        legacy['_neo_image_command_type'] = infer_image_command_type(legacy)
        legacy['_neo_payload_contract_version'] = 'legacy+stage2-detected'
        legacy = stamp_external_extension_payload_contract(legacy)
        return legacy, None

    envelope, _stage6_envelope_removed = sanitize_image_payload_for_retired_sections(_clean_dict(envelope_or_payload))
    legacy, _stage6_legacy_removed = sanitize_image_payload_for_retired_sections(_clean_dict(envelope.get('legacy_payload') or envelope.get('settings')))
    image_state = _clean_dict(envelope.get('image_state'))
    build = _clean_dict(envelope.get('build') or image_state.get('build'))
    source = _clean_dict(envelope.get('source') or image_state.get('source'))
    modules, _stage6_module_removed = sanitize_image_payload_for_retired_sections(_clean_dict(envelope.get('modules') or image_state.get('modules')))
    preview_action = _clean_dict(envelope.get('preview_action'))
    command_type = str(envelope.get('command_type') or infer_image_command_type(legacy)).strip().lower() or 'main_generate'

    for key in ('width', 'height', 'family', 'checkpoint', 'sampler', 'scheduler', 'seed', 'steps', 'cfg'):
        if build.get(key) not in (None, '') and legacy.get(key) in (None, ''):
            legacy[key] = build.get(key)
    if source.get('active_source_image') and not legacy.get('source_image_name'):
        legacy['source_image_name'] = source.get('active_source_image')
    if source.get('selected_output_snapshot') and not legacy.get('generationSelectedOutputSnapshot'):
        legacy['generationSelectedOutputSnapshot'] = source.get('selected_output_snapshot')
    if source.get('preview_action_target') and not legacy.get('generationPreviewActionTarget'):
        legacy['generationPreviewActionTarget'] = source.get('preview_action_target')

    for module_key, legacy_key in (
        ('scene_director', 'scene_director'),
        ('dynamic_thresholding', 'dynamic_thresholding'),
        ('ipadapter', 'ipadapter'),
        ('controlnet', 'controlnet'),
        ('lora_stack', 'lora_stack'),
        ('embeddings', 'embeddings'),
        ('finish_action', 'finish_action'),
    ):
        value = modules.get(module_key)
        if value not in (None, '', [], {}) and legacy.get(legacy_key) in (None, '', [], {}):
            legacy[legacy_key] = value

    if preview_action:
        legacy['preview_action'] = preview_action
        if not legacy.get('_neo_preview_action'):
            legacy['_neo_preview_action'] = preview_action.get('action_type') or preview_action.get('type') or command_type

    if command_type in _PREVIEW_ACTIONS and not legacy.get('_neo_preview_action'):
        legacy['_neo_preview_action'] = command_type
    if command_type in _UPSCALE_ACTIONS and not legacy.get('mode'):
        legacy['mode'] = 'upscale'

    legacy['_neo_image_command_type'] = command_type
    legacy['_neo_payload_contract_version'] = _IMAGE_COMMAND_VERSION
    legacy['_neo_command_envelope'] = {
        'command_type': command_type,
        'version': envelope.get('version') or _IMAGE_COMMAND_VERSION,
        'has_image_state': bool(image_state),
        'has_preview_action': bool(preview_action),
        'has_lineage': bool(envelope.get('lineage')),
        'retired_sections_sanitized': True,
        'retired_sections_version': 'image-retired-sections-v1',
    }
    legacy = stamp_external_extension_payload_contract(legacy)
    legacy = stamp_output_selection_contract(legacy, envelope)
    legacy, _stage6_final_removed = sanitize_image_payload_for_retired_sections(legacy)
    return legacy, envelope
