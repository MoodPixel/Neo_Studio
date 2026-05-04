from __future__ import annotations

"""Stage 5 Image workflow builder facade.

This module is the canonical entry point for Image Tab workflow compilation.
It does not rewrite the existing Comfy graph builders yet; it routes every Image
command through a shared contract so future refactors can move common model/VAE,
conditioning, source-image, save-node, and metadata logic into one place without
changing route code again.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal, Tuple

ImageWorkflowCommand = Literal[
    'main_generate',
    'preview_action',
    'image_upscale',
    'upscale_lab',
    'supir',
]

WorkflowTuple = Tuple[Dict[str, Any], Dict[str, Any], list[str]]


@dataclass(slots=True)
class ImageWorkflowContext:
    command: ImageWorkflowCommand
    payload: Dict[str, Any]
    notes: list[str] = field(default_factory=list)

    @property
    def mode(self) -> str:
        return str(self.payload.get('mode') or self.payload.get('workflow_type') or 'txt2img').strip().lower() or 'txt2img'

    @property
    def is_preview(self) -> bool:
        return self.command == 'preview_action' or bool(self.payload.get('_neo_preview_action'))


def detect_image_workflow_command(payload: Dict[str, Any], *, fallback: ImageWorkflowCommand = 'main_generate') -> ImageWorkflowCommand:
    """Resolve the Image command type from the Stage 2 envelope / legacy flags."""
    if not isinstance(payload, dict):
        return fallback

    explicit = str(payload.get('_neo_command_type') or payload.get('command_type') or '').strip().lower()
    if explicit in {'main_generate', 'preview_action', 'image_upscale', 'upscale_lab', 'supir'}:
        return explicit  # type: ignore[return-value]

    envelope = payload.get('_neo_command_envelope')
    if isinstance(envelope, dict):
        env_command = str(envelope.get('command') or envelope.get('command_type') or '').strip().lower()
        if env_command in {'main_generate', 'preview_action', 'image_upscale', 'upscale_lab', 'supir'}:
            return env_command  # type: ignore[return-value]

    if payload.get('_neo_preview_action'):
        return 'preview_action'
    if payload.get('image_upscale_enabled') or payload.get('image_upscale_source_mode'):
        return 'image_upscale' if fallback == 'image_upscale' else fallback
    if payload.get('supir_enabled'):
        return 'supir'
    return fallback


def _append_core_metadata(normalized_payload: Dict[str, Any], context: ImageWorkflowContext) -> Dict[str, Any]:
    normalized = dict(normalized_payload or {})
    normalized.setdefault('_neo_workflow_command', context.command)
    normalized.setdefault('_neo_workflow_mode', context.mode)
    normalized.setdefault('_neo_preview_action', bool(context.is_preview))
    normalized.setdefault('_neo_stage5_builder_facade', True)
    return normalized


def _run_legacy_builder(builder: Callable[[Dict[str, Any]], WorkflowTuple], context: ImageWorkflowContext) -> WorkflowTuple:
    workflow, normalized_payload, notes = builder(context.payload)
    normalized_payload = _append_core_metadata(normalized_payload, context)
    merged_notes = [*context.notes, *(notes or [])]
    if 'Stage 5 builder facade: routed through canonical Image workflow entrypoint.' not in merged_notes:
        merged_notes.insert(0, 'Stage 5 builder facade: routed through canonical Image workflow entrypoint.')
    return workflow, normalized_payload, merged_notes


def build_image_workflow(payload: Dict[str, Any], *, command: ImageWorkflowCommand | None = None) -> WorkflowTuple:
    """Canonical Image Tab workflow compiler entrypoint.

    Today this delegates to the proven legacy graph builders to avoid breaking
    Character Profile, IPAdapter, Canvas, ADetailer, SUPIR, and upscale behavior.
    The key Stage 5 change is that routes no longer call multiple builders
    directly; future extraction can happen behind this stable facade.
    """
    resolved_command = command or detect_image_workflow_command(payload)
    context = ImageWorkflowContext(command=resolved_command, payload=dict(payload or {}))

    # Import lazily to avoid circular imports while this facade is adopted.
    from .comfy_workflows import build_generation_workflow, build_image_upscale_workflow

    if resolved_command == 'image_upscale':
        return _run_legacy_builder(build_image_upscale_workflow, context)

    # Preview, Upscale Lab, SUPIR, txt2img, img2img, inpaint, ControlNet,
    # Scene Director, IPAdapter and ADetailer still compile through the main
    # generation builder until their shared modules are extracted safely.
    return _run_legacy_builder(build_generation_workflow, context)


__all__ = [
    'ImageWorkflowCommand',
    'ImageWorkflowContext',
    'detect_image_workflow_command',
    'build_image_workflow',
]
