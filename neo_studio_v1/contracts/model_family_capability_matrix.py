from __future__ import annotations

from copy import deepcopy
from typing import Any

from .generation_families import (
    GENERATION_FAMILY_DEFINITIONS,
    normalize_generation_mode,
    normalize_inpaint_backend,
)
from .image_extension_targets import canonical_image_extension_target

MODEL_FAMILY_CAPABILITY_MATRIX_VERSION = "model-family-capability-matrix-v1"

_WORKFLOW_ORDER = ("txt2img", "img2img", "inpaint", "outpaint")
_SYSTEM_ORDER = (
    "style_stack",
    "scene_director",
    "controlnet",
    "ipadapter",
    "lora",
    "adetailer",
    "highres_fix",
    "layerdiffuse",
    "metadata_replay",
    "helper_bridge",
)

# Central matrix used by the future Image Extension Compatibility Resolver.
# It intentionally describes family capabilities only; it does not mutate active workflows.
MODEL_FAMILY_CAPABILITY_MATRIX: dict[str, dict[str, Any]] = {
    "sdxl_sd": {
        "version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "family": "sdxl_sd",
        "label": "SDXL / SD",
        "status": "stable",
        "supported_workflows": ["txt2img", "img2img", "inpaint", "outpaint"],
        "staged_workflows": [],
        "blocked_workflows": [],
        "supported_systems": [
            "style_stack",
            "scene_director",
            "controlnet",
            "ipadapter",
            "lora",
            "adetailer",
            "highres_fix",
            "layerdiffuse",
            "metadata_replay",
            "helper_bridge",
        ],
        "staged_systems": [],
        "blocked_systems": [],
        "supported_extension_targets": [
            "image.build",
            "image.assets",
            "image.reference",
            "image.finish",
            "image.results",
            "image.workflow",
            "image.output",
            "image.extensions_manager",
            "image.save_metadata",
        ],
        "workflow_backends": {
            "inpaint": {"standard": "stable", "lanpaint": "experimental"},
            "outpaint": {"standard": "stable", "lanpaint": "planned"},
        },
        "input_types": ["text", "image", "mask"],
        "output_roles": ["image", "preview", "metadata", "mask", "alpha"],
    },
    "flux": {
        "version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "family": "flux",
        "label": "Flux",
        "status": "experimental",
        "supported_workflows": ["txt2img", "img2img", "outpaint"],
        "staged_workflows": ["inpaint"],
        "blocked_workflows": [],
        "supported_systems": ["style_stack", "lora", "highres_fix", "metadata_replay", "helper_bridge"],
        "staged_systems": ["controlnet", "ipadapter", "adetailer"],
        "blocked_systems": ["scene_director", "layerdiffuse"],
        "supported_extension_targets": [
            "image.build",
            "image.assets",
            "image.finish",
            "image.results",
            "image.workflow",
            "image.extensions_manager",
            "image.save_metadata",
        ],
        "workflow_backends": {
            "inpaint": {"lanpaint": "planned"},
            "outpaint": {"standard": "experimental", "lanpaint": "planned"},
        },
        "input_types": ["text", "image"],
        "output_roles": ["image", "preview", "metadata"],
    },
    "qwen_image_edit": {
        "version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "family": "qwen_image_edit",
        "label": "Qwen Image Edit",
        "status": "experimental",
        "supported_workflows": ["txt2img", "img2img", "inpaint", "outpaint"],
        "staged_workflows": [],
        "blocked_workflows": [],
        "supported_systems": ["style_stack", "metadata_replay", "helper_bridge"],
        "staged_systems": ["adetailer", "highres_fix"],
        "blocked_systems": ["scene_director", "controlnet", "ipadapter", "lora", "layerdiffuse"],
        "supported_extension_targets": [
            "image.build",
            "image.assets",
            "image.finish",
            "image.results",
            "image.workflow",
            "image.extensions_manager",
            "image.save_metadata",
        ],
        "workflow_backends": {
            "inpaint": {"standard": "unavailable", "lanpaint": "experimental"},
            "outpaint": {"standard": "experimental", "lanpaint": "planned"},
        },
        "input_types": ["text", "image", "instruction"],
        "output_roles": ["image", "preview", "metadata"],
        "required_assets": ["mmproj"],
    },
    "zimage": {
        "version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "family": "zimage",
        "label": "Zimage",
        "status": "staged",
        "supported_workflows": ["txt2img", "img2img"],
        "staged_workflows": [],
        "blocked_workflows": ["inpaint", "outpaint"],
        "supported_systems": ["style_stack", "metadata_replay", "helper_bridge"],
        "staged_systems": ["highres_fix", "adetailer"],
        "blocked_systems": ["scene_director", "controlnet", "ipadapter", "lora", "layerdiffuse"],
        "supported_extension_targets": [
            "image.build",
            "image.assets",
            "image.results",
            "image.workflow",
            "image.extensions_manager",
            "image.save_metadata",
        ],
        "workflow_backends": {
            "inpaint": {"standard": "unavailable", "lanpaint": "unavailable"},
            "outpaint": {"standard": "unavailable", "lanpaint": "unavailable"},
        },
        "input_types": ["text", "image"],
        "output_roles": ["image", "preview", "metadata"],
    },
}


def _family_key(family: Any) -> str:
    key = str(family or "sdxl_sd").strip().lower() or "sdxl_sd"
    return key if key in MODEL_FAMILY_CAPABILITY_MATRIX else "sdxl_sd"


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip().lower().replace(" ", "_")


def _unique(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _clean(value)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def get_model_family_capabilities(family: Any) -> dict[str, Any]:
    return deepcopy(MODEL_FAMILY_CAPABILITY_MATRIX[_family_key(family)])


def list_model_family_capabilities() -> list[dict[str, Any]]:
    return [deepcopy(MODEL_FAMILY_CAPABILITY_MATRIX[key]) for key in MODEL_FAMILY_CAPABILITY_MATRIX]


def is_workflow_supported(family: Any, workflow: Any, backend: Any = None) -> bool:
    return validate_family_workflow_support(family, workflow, backend).get("ok") is True


def validate_family_workflow_support(family: Any, workflow: Any, backend: Any = None) -> dict[str, Any]:
    row = get_model_family_capabilities(family)
    mode = normalize_generation_mode(str(workflow or "txt2img"))
    family_id = row["family"]
    if mode not in _WORKFLOW_ORDER:
        return {
            "ok": False,
            "family": family_id,
            "workflow": mode,
            "backend": normalize_inpaint_backend(backend),
            "status": "error",
            "reason": "unsupported_workflow",
            "message": "Unsupported generation workflow.",
        }

    if mode not in row.get("supported_workflows", []):
        status = "planned" if mode in row.get("staged_workflows", []) else "unavailable"
        return {
            "ok": False,
            "family": family_id,
            "workflow": mode,
            "backend": normalize_inpaint_backend(backend),
            "status": status,
            "reason": "workflow_not_supported",
            "message": f"{row.get('label') or family_id} does not support {mode} in this build.",
        }

    if mode in {"inpaint", "outpaint"}:
        backend_key = normalize_inpaint_backend(backend)
        backend_status = ((row.get("workflow_backends") or {}).get(mode) or {}).get(backend_key)
        if backend_status in {None, "unavailable", "disabled", "blocked", "planned"}:
            return {
                "ok": False,
                "family": family_id,
                "workflow": mode,
                "backend": backend_key,
                "status": str(backend_status or "unavailable"),
                "reason": "backend_not_supported",
                "message": f"{row.get('label') or family_id} does not support {backend_key} {mode} in this build.",
            }
        status = str(backend_status)
    else:
        backend_key = normalize_inpaint_backend(backend)
        status = "enabled"

    return {
        "ok": True,
        "family": family_id,
        "workflow": mode,
        "backend": backend_key,
        "status": status,
        "reason": "ok",
        "message": "",
    }


def is_extension_target_supported(family: Any, target: Any) -> bool:
    return validate_family_extension_target_support(family, target).get("ok") is True


def validate_family_extension_target_support(family: Any, target: Any) -> dict[str, Any]:
    row = get_model_family_capabilities(family)
    target_id = canonical_image_extension_target(target)
    family_id = row["family"]
    if not target_id:
        return {
            "ok": False,
            "family": family_id,
            "target": str(target or ""),
            "status": "error",
            "reason": "unknown_target",
            "message": "Unknown Image extension target.",
        }
    if target_id not in row.get("supported_extension_targets", []):
        return {
            "ok": False,
            "family": family_id,
            "target": target_id,
            "status": "unavailable",
            "reason": "target_not_supported",
            "message": f"{row.get('label') or family_id} does not support extensions mounted at {target_id} in this build.",
        }
    return {
        "ok": True,
        "family": family_id,
        "target": target_id,
        "status": "enabled",
        "reason": "ok",
        "message": "",
    }


def validate_family_system_support(family: Any, system: Any) -> dict[str, Any]:
    row = get_model_family_capabilities(family)
    system_id = _clean(system)
    family_id = row["family"]
    if not system_id:
        return {
            "ok": False,
            "family": family_id,
            "system": system_id,
            "status": "error",
            "reason": "missing_system",
            "message": "Missing Image system id.",
        }
    if system_id in row.get("supported_systems", []):
        return {"ok": True, "family": family_id, "system": system_id, "status": "enabled", "reason": "ok", "message": ""}
    if system_id in row.get("staged_systems", []):
        return {
            "ok": False,
            "family": family_id,
            "system": system_id,
            "status": "planned",
            "reason": "system_staged",
            "message": f"{system_id} is staged for {row.get('label') or family_id}, but is not active in this build.",
        }
    return {
        "ok": False,
        "family": family_id,
        "system": system_id,
        "status": "unavailable",
        "reason": "system_not_supported",
        "message": f"{row.get('label') or family_id} does not support {system_id} in this build.",
    }


def summarize_family_matrix_for_ui(family: Any) -> dict[str, Any]:
    row = get_model_family_capabilities(family)
    workflows = {workflow: validate_family_workflow_support(row["family"], workflow) for workflow in _WORKFLOW_ORDER}
    systems = {system: validate_family_system_support(row["family"], system) for system in _SYSTEM_ORDER}
    targets = {
        target: validate_family_extension_target_support(row["family"], target)
        for target in row.get("supported_extension_targets", [])
    }
    return {
        "version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "family": row["family"],
        "label": row.get("label") or row["family"],
        "status": row.get("status") or "unknown",
        "workflows": workflows,
        "systems": systems,
        "extension_targets": targets,
        "input_types": list(row.get("input_types") or []),
        "output_roles": list(row.get("output_roles") or []),
        "required_assets": list(row.get("required_assets") or []),
    }


def assert_generation_family_matrix_is_in_sync() -> list[str]:
    """Return human-readable sync errors between legacy generation family rows and the matrix."""
    errors: list[str] = []
    for family_id, row in GENERATION_FAMILY_DEFINITIONS.items():
        if family_id not in MODEL_FAMILY_CAPABILITY_MATRIX:
            errors.append(f"missing matrix row for {family_id}")
            continue
        matrix = MODEL_FAMILY_CAPABILITY_MATRIX[family_id]
        supports = row.get("supports") or {}
        for workflow in _WORKFLOW_ORDER:
            legacy_enabled = bool(supports.get(workflow))
            matrix_enabled = workflow in (matrix.get("supported_workflows") or [])
            if legacy_enabled != matrix_enabled:
                errors.append(f"{family_id}.{workflow} legacy={legacy_enabled} matrix={matrix_enabled}")
    return errors
