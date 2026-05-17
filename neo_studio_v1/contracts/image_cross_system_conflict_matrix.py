from __future__ import annotations

from copy import deepcopy
from typing import Any

IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION = "image-cross-system-conflict-matrix-v1"


def _key(value: Any) -> str:
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
        text = _key(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


# Pair rules are symmetric. They describe cross-system behavior only; family and
# workflow support are still owned by the model-family matrix and workflow registry.
IMAGE_CROSS_SYSTEM_CONFLICT_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("scene_director", "layerdiffuse"): {
        "severity": "allow",
        "status": "compatible",
        "message": "Scene Director may run with LayerDiffuse when the selected LayerDiffuse mode supports the active workflow and model family.",
    },
    ("controlnet", "layerdiffuse"): {
        "severity": "allow",
        "status": "compatible",
        "message": "ControlNet guidance may run before LayerDiffuse output packaging when both systems support the active workflow and family.",
    },
    ("ipadapter", "layerdiffuse"): {
        "severity": "allow",
        "status": "compatible",
        "message": "IPAdapter identity/reference conditioning may run before LayerDiffuse output packaging when both systems support the active workflow and family.",
    },
    ("style_stack", "layerdiffuse"): {
        "severity": "allow",
        "status": "compatible",
        "message": "Style Stack is a prompt contributor and may combine with LayerDiffuse output modes.",
    },
    ("adetailer", "layerdiffuse"): {
        "severity": "warn",
        "status": "target_sensitive",
        "message": "ADetailer should target the RGB/preview image, not the raw alpha output, when LayerDiffuse is active.",
    },
    ("highres_fix", "layerdiffuse"): {
        "severity": "warn",
        "status": "alpha_sensitive",
        "message": "Highres Fix may alter alpha edges. Preserve LayerDiffuse alpha roles or run upscale on the RGB/preview target only.",
    },
    ("lanpaint", "layerdiffuse"): {
        "severity": "block",
        "status": "workflow_conflict",
        "message": "LanPaint and LayerDiffuse cannot both own source/mask/output workflow mutation in the same run until a verified bridge exists.",
    },
    ("outpaint_canvas_editor", "layerdiffuse"): {
        "severity": "block",
        "status": "workflow_conflict",
        "message": "Outpaint canvas editing and LayerDiffuse output patching cannot run together unless a verified outpaint LayerDiffuse workflow is selected.",
    },
    ("scene_director", "outpaint_canvas_editor"): {
        "severity": "block",
        "status": "workflow_conflict",
        "message": "Scene Director is not valid for the standard outpaint canvas workflow.",
    },
    ("scene_director", "lanpaint"): {
        "severity": "warn",
        "status": "workflow_sensitive",
        "message": "Scene Director with LanPaint is only valid when a compatible source/mask path is available.",
    },
    ("controlnet", "lanpaint"): {
        "severity": "warn",
        "status": "workflow_sensitive",
        "message": "ControlNet with LanPaint requires a compatible control-image route for the selected family and mask workflow.",
    },
    ("ipadapter", "controlnet"): {
        "severity": "warn",
        "status": "batch_sensitive",
        "message": "IPAdapter plus ControlNet may require batch clamping or repeated source images.",
    },
}

WORKFLOW_SCOPED_SYSTEM_BLOCKS: dict[str, set[str]] = {
    "outpaint": {"scene_director", "lanpaint", "region_targeted_character_builder"},
    "lanpaint": {"outpaint", "outpaint_canvas_editor"},
}


def _pair_key(left: str, right: str) -> tuple[str, str]:
    a = _key(left)
    b = _key(right)
    return (a, b) if (a, b) in IMAGE_CROSS_SYSTEM_CONFLICT_RULES else (b, a)


def rule_for_system_pair(left: Any, right: Any) -> dict[str, Any]:
    left_key = _key(left)
    right_key = _key(right)
    if not left_key or not right_key or left_key == right_key:
        return {}
    rule = IMAGE_CROSS_SYSTEM_CONFLICT_RULES.get(_pair_key(left_key, right_key))
    if not rule:
        return {}
    out = deepcopy(rule)
    out.update({"left": left_key, "right": right_key, "systems": [left_key, right_key]})
    return out


def resolve_image_cross_system_conflicts(
    active_systems: Any = None,
    extension_systems: Any = None,
    *,
    workflow: Any = None,
    family: Any = None,
) -> dict[str, Any]:
    """Resolve allow/warn/block system interactions for Image workflow contributors.

    This is a read-only matrix. It does not toggle systems, mutate payload, or
    decide model-family support. It only reports cross-system conflicts so UI and
    validator layers can show the same visible reason before graph compile.
    """
    active = _list(active_systems)
    extension = _list(extension_systems)
    combined: list[str] = []
    for system in [*active, *extension]:
        if system not in combined:
            combined.append(system)

    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    allows: list[dict[str, Any]] = []
    workflow_key = _key(workflow)

    workflow_blocks = WORKFLOW_SCOPED_SYSTEM_BLOCKS.get(workflow_key, set())
    for system in combined:
        if system in workflow_blocks:
            errors.append({
                "code": "workflow_system_conflict",
                "severity": "block",
                "family": _key(family),
                "workflow": workflow_key,
                "systems": [system],
                "message": f"{system} is not valid for the {workflow_key} workflow.",
                "detail": {"workflow": workflow_key, "blocked_system": system},
            })

    for index, left in enumerate(combined):
        for right in combined[index + 1:]:
            rule = rule_for_system_pair(left, right)
            if not rule:
                continue
            severity = _key(rule.get("severity"))
            record = {
                "code": "cross_system_conflict" if severity == "block" else ("cross_system_warning" if severity == "warn" else "cross_system_allowed"),
                "severity": severity or "allow",
                "family": _key(family),
                "workflow": workflow_key,
                "systems": rule.get("systems") or [left, right],
                "status": rule.get("status") or "declared",
                "message": rule.get("message") or "Image systems require compatibility review.",
                "detail": {"rule": {k: v for k, v in rule.items() if k not in {"message"}}},
            }
            if severity == "block":
                errors.append(record)
            elif severity == "warn":
                warnings.append(record)
            else:
                allows.append(record)

    return {
        "version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
        "ok": not errors,
        "family": _key(family),
        "workflow": workflow_key,
        "active_systems": active,
        "extension_systems": extension,
        "systems": combined,
        "errors": errors,
        "warnings": warnings,
        "allows": allows,
        "policy": "central_cross_system_matrix_visible_block_or_warn",
    }
