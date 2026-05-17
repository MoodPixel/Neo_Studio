from __future__ import annotations

from dataclasses import dataclass
from typing import Any

IMAGE_EXTENSION_TARGET_CONTRACT_VERSION = "image-extension-target-contract-v1"


@dataclass(frozen=True)
class ImageExtensionTarget:
    id: str
    section: str
    label: str
    description: str
    allowed_contribution_types: tuple[str, ...]


IMAGE_EXTENSION_TARGETS: dict[str, ImageExtensionTarget] = {
    "image.build": ImageExtensionTarget(
        id="image.build",
        section="build",
        label="Build",
        description="Base generation, model routing, prompt assembly, and workflow selection contributions.",
        allowed_contribution_types=("prompt_fragment", "workflow_patch", "validator_rule", "ui_panel", "metadata_patch"),
    ),
    "image.assets": ImageExtensionTarget(
        id="image.assets",
        section="assets",
        label="Assets",
        description="Asset source, upload, selected-image, reusable output, and input-slot contributions.",
        allowed_contribution_types=("asset_source", "source_slot", "ui_panel", "metadata_patch", "validator_rule"),
    ),
    "image.reference": ImageExtensionTarget(
        id="image.reference",
        section="reference",
        label="Reference",
        description="Identity, reference image, ControlNet, IPAdapter, and regional/reference conditioning contributions.",
        allowed_contribution_types=("conditioning_patch", "node_patch", "source_slot", "ui_panel", "validator_rule"),
    ),
    "image.finish": ImageExtensionTarget(
        id="image.finish",
        section="finish",
        label="Finish",
        description="Post-process, refinement, ADetailer, highres, upscale, and cleanup contributions.",
        allowed_contribution_types=("postprocess_patch", "node_patch", "ui_panel", "validator_rule", "metadata_patch"),
    ),
    "image.results": ImageExtensionTarget(
        id="image.results",
        section="results",
        label="Results",
        description="Gallery, output visibility, result actions, export, append/replace, and save behavior contributions.",
        allowed_contribution_types=("output_role", "metadata_patch", "ui_panel", "validator_rule"),
    ),
    "image.workflow": ImageExtensionTarget(
        id="image.workflow",
        section="workflow",
        label="Workflow",
        description="Whole-workflow or graph-level contributors that must be conflict-checked before compile.",
        allowed_contribution_types=("workflow_patch", "replace_workflow", "validator_rule", "metadata_patch"),
    ),
    "image.output": ImageExtensionTarget(
        id="image.output",
        section="output",
        label="Output",
        description="Decode/output-role contributors such as alpha, masks, previews, composites, and export bundles.",
        allowed_contribution_types=("output_role", "workflow_patch", "metadata_patch", "validator_rule", "ui_panel"),
    ),
    "image.extensions_manager": ImageExtensionTarget(
        id="image.extensions_manager",
        section="extensions",
        label="Extensions Manager",
        description="Install, enable, inspect, health, and extension-local configuration panels.",
        allowed_contribution_types=("ui_panel", "metadata_patch", "validator_rule"),
    ),
    "image.save_metadata": ImageExtensionTarget(
        id="image.save_metadata",
        section="results",
        label="Save Metadata",
        description="Run metadata, sidecar, provenance, and audit payload contributions.",
        allowed_contribution_types=("metadata_patch", "output_role", "validator_rule"),
    ),
}

# Legacy section names remain accepted so installed extensions do not break.
IMAGE_EXTENSION_TARGET_ALIASES: dict[str, str] = {
    "base_generation": "image.build",
    "build": "image.build",
    "prompt_stack": "image.build",
    "assets": "image.assets",
    "asset": "image.assets",
    "reference": "image.reference",
    "references": "image.reference",
    "controlnet": "image.reference",
    "ipadapter": "image.reference",
    "scene_director": "image.reference",
    "finish": "image.finish",
    "postprocess": "image.finish",
    "post_process": "image.finish",
    "adetailer": "image.finish",
    "highres": "image.finish",
    "highres_fix": "image.finish",
    "results": "image.results",
    "gallery": "image.results",
    "preview": "image.results",
    "output": "image.output",
    "outputs": "image.output",
    "workflow": "image.workflow",
    "workflows": "image.workflow",
    "extensions": "image.extensions_manager",
    "extension_manager": "image.extensions_manager",
    "extensions_manager": "image.extensions_manager",
    "save_metadata": "image.save_metadata",
    "metadata": "image.save_metadata",
}

VALID_IMAGE_EXTENSION_TARGET_IDS = frozenset(IMAGE_EXTENSION_TARGETS)
VALID_LEGACY_IMAGE_SECTION_IDS = frozenset(IMAGE_EXTENSION_TARGET_ALIASES)
VALID_IMAGE_EXTENSION_TARGET_OR_SECTION_IDS = VALID_IMAGE_EXTENSION_TARGET_IDS | VALID_LEGACY_IMAGE_SECTION_IDS


def _clean_key(value: Any) -> str:
    return str(value if value is not None else "").strip().lower().replace(" ", "_")


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_key(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def canonical_image_extension_target(value: Any) -> str:
    key = _clean_key(value)
    if not key:
        return ""
    if key in IMAGE_EXTENSION_TARGETS:
        return key
    return IMAGE_EXTENSION_TARGET_ALIASES.get(key, "")


def normalize_image_extension_targets(value: Any) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        target = canonical_image_extension_target(item)
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def validate_image_extension_targets(value: Any) -> dict[str, Any]:
    raw = _list(value)
    normalized = normalize_image_extension_targets(raw)
    invalid = [item for item in raw if not canonical_image_extension_target(item)]
    return {
        "ok": not invalid,
        "version": IMAGE_EXTENSION_TARGET_CONTRACT_VERSION,
        "targets": normalized,
        "invalid": invalid,
        "warnings": [f"image extension target '{item}' is not registered." for item in invalid],
    }


def image_extension_target_contract(targets: Any = None) -> dict[str, Any]:
    normalized = normalize_image_extension_targets(targets)
    return {
        "version": IMAGE_EXTENSION_TARGET_CONTRACT_VERSION,
        "targets": normalized,
        "available_targets": [
            {
                "id": item.id,
                "section": item.section,
                "label": item.label,
                "description": item.description,
                "allowed_contribution_types": list(item.allowed_contribution_types),
            }
            for item in IMAGE_EXTENSION_TARGETS.values()
        ],
    }
