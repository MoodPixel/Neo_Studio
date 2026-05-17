from __future__ import annotations

from copy import deepcopy
from typing import Any

from .image_extension_targets import normalize_image_extension_targets
from .image_extension_mount_rules import (
    IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
    resolve_image_extension_mounts,
)
from .image_cross_system_conflict_matrix import (
    IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
    resolve_image_cross_system_conflicts,
)
from .model_family_capability_matrix import (
    MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
    validate_family_extension_target_support,
    validate_family_system_support,
    validate_family_workflow_support,
)

IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION = "image-extension-compatibility-resolver-v2"

WORKFLOW_OWNER_MODES = {"replace_workflow"}
OUTPUT_AFFECTING_MODES = {"workflow_patch", "replace_workflow", "postprocess_output", "preprocess_source", "mixed_workflow"}


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _dict(value: Any) -> dict[str, Any]:
    return _copy(value) if isinstance(value, dict) else {}


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


def _supports(allowed: Any, current: Any) -> bool:
    values = _list(allowed)
    if not values:
        return True
    current_key = _key(current)
    return "*" in values or "any" in values or current_key in values


def _metadata_blocks(entry: dict[str, Any], registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    workflow = _dict(entry.get("workflow")) or _dict(registry.get("workflow"))
    output = _dict(entry.get("output")) or _dict(registry.get("output"))
    return workflow, output


def _workflow_mode(entry: dict[str, Any], registry: dict[str, Any]) -> str:
    workflow, _output = _metadata_blocks(entry, registry)
    raw_modes = [
        entry.get("workflow_mode"),
        workflow.get("mode"),
        registry.get("workflow_mode"),
        registry.get("default_workflow_mode"),
    ]
    for value in raw_modes:
        mode = _key(value)
        if mode:
            return mode
    return "metadata_only"


def _extension_targets(entry: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    raw = (
        entry.get("extension_targets")
        or entry.get("targets")
        or registry.get("extension_targets")
        or registry.get("targets")
        or entry.get("target_sections")
        or registry.get("target_sections")
        or []
    )
    return normalize_image_extension_targets(raw)


def _extension_systems(entry: dict[str, Any], registry: dict[str, Any], extension_id: str) -> list[str]:
    raw = (
        entry.get("systems")
        or entry.get("image_systems")
        or registry.get("systems")
        or registry.get("image_systems")
        or registry.get("system_id")
        or []
    )
    systems = _list(raw)
    if systems:
        return systems
    # Fallback keeps existing extensions useful before every manifest is migrated.
    slug = _key(extension_id.split(".", 1)[-1] if "." in extension_id else extension_id)
    if slug in {"layerdiffuse", "layer_diffuse"}:
        return ["layerdiffuse"]
    return []


def _supported_workflows(entry: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    return _list(entry.get("supported_workflows") or registry.get("supported_workflows"))


def _supported_families(entry: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    return _list(
        entry.get("supported_model_families")
        or entry.get("model_families")
        or registry.get("supported_model_families")
        or registry.get("model_families")
    )


def build_image_extension_compatibility_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    workflow = _key(payload.get("workflow") or payload.get("workflow_type") or payload.get("mode") or payload.get("_neo_image_command_type") or "txt2img") or "txt2img"
    family = _key(payload.get("family") or payload.get("model_family") or payload.get("generation_family") or "sdxl_sd") or "sdxl_sd"
    backend = _key(payload.get("backend") or payload.get("inpaint_backend") or payload.get("outpaint_backend") or payload.get("image_backend") or "standard") or "standard"
    active_systems = _list(payload.get("active_systems") or payload.get("systems") or payload.get("enabled_systems"))
    return {
        "resolver_version": IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        "matrix_version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "conflict_matrix_version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
        "surface": _key(payload.get("surface") or "image") or "image",
        "family": family,
        "model_family": family,
        "workflow": workflow,
        "workflow_type": workflow,
        "backend": backend,
        "active_systems": active_systems,
        "section": _key(payload.get("section") or payload.get("target_section") or ""),
    }


def resolve_image_extension_compatibility(
    extension_id: str,
    entry: dict[str, Any] | None = None,
    *,
    registry_record: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve whether one image extension is compatible with the active family/workflow.

    The resolver does not mutate payload state. It returns visibility, enablement,
    blocking reasons, warnings, and the effective targets/systems that validation/UI
    layers can display without hidden behavior.
    """
    entry = entry if isinstance(entry, dict) else {}
    registry = registry_record if isinstance(registry_record, dict) else {}
    context = context if isinstance(context, dict) else {}
    family = _key(context.get("family") or context.get("model_family") or "sdxl_sd") or "sdxl_sd"
    workflow = _key(context.get("workflow") or context.get("workflow_type") or "txt2img") or "txt2img"
    backend = _key(context.get("backend") or "standard") or "standard"

    targets = _extension_targets(entry, registry)
    systems = _extension_systems(entry, registry, extension_id)
    mode = _workflow_mode(entry, registry)
    supported_workflows = _supported_workflows(entry, registry)
    supported_families = _supported_families(entry, registry)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    workflow_result = validate_family_workflow_support(family, workflow, backend)
    if not workflow_result.get("ok"):
        errors.append({
            "code": "family_workflow_not_supported",
            "message": workflow_result.get("message") or "Model family does not support this workflow.",
            "detail": workflow_result,
        })

    if supported_workflows and not _supports(supported_workflows, workflow):
        errors.append({
            "code": "extension_workflow_not_supported",
            "message": f"{extension_id} does not support {workflow}.",
            "detail": {"supported_workflows": supported_workflows, "workflow": workflow},
        })

    if supported_families and not _supports(supported_families, family):
        errors.append({
            "code": "extension_family_not_supported",
            "message": f"{extension_id} does not support {family}.",
            "detail": {"supported_model_families": supported_families, "family": family},
        })

    target_results: list[dict[str, Any]] = []
    for target in targets:
        result = validate_family_extension_target_support(family, target)
        target_results.append(result)
        if not result.get("ok"):
            errors.append({
                "code": "extension_target_not_supported_by_family",
                "message": result.get("message") or f"{family} does not support {target}.",
                "detail": result,
            })

    system_results: list[dict[str, Any]] = []
    for system in systems:
        result = validate_family_system_support(family, system)
        system_results.append(result)
        if result.get("ok"):
            continue
        if result.get("status") == "planned":
            warnings.append({
                "code": "extension_system_staged_for_family",
                "message": result.get("message") or f"{system} is staged for {family}.",
                "detail": result,
            })
        else:
            errors.append({
                "code": "extension_system_not_supported_by_family",
                "message": result.get("message") or f"{family} does not support {system}.",
                "detail": result,
            })

    active_systems = _list(context.get("active_systems"))
    conflict_result = resolve_image_cross_system_conflicts(
        active_systems,
        systems,
        workflow=workflow,
        family=family,
    )
    for item in conflict_result.get("errors") or []:
        errors.append({
            "code": item.get("code") or "cross_system_conflict",
            "message": item.get("message") or "Image systems are not compatible in this workflow.",
            "detail": item,
        })
    for item in conflict_result.get("warnings") or []:
        warnings.append({
            "code": item.get("code") or "cross_system_warning",
            "message": item.get("message") or "Image systems require compatibility review.",
            "detail": item,
        })

    if mode in WORKFLOW_OWNER_MODES and active_systems:
        warnings.append({
            "code": "workflow_owner_with_active_systems",
            "message": "Workflow-owner extensions must be conflict-checked against active Image systems before compile.",
            "detail": {"active_systems": active_systems, "workflow_mode": mode},
        })

    mounts = resolve_image_extension_mounts(extension_id, entry, registry_record=registry, context=context)
    blocked = bool(errors)
    status = "blocked" if blocked else ("warning" if warnings else "ready")
    return {
        "version": IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        "matrix_version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "mount_rules_version": IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
        "conflict_matrix_version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
        "extension_id": extension_id,
        "family": family,
        "workflow": workflow,
        "backend": backend,
        "targets": targets,
        "systems": systems,
        "workflow_mode": mode,
        "mounts": mounts.get("mounts", []),
        "primary_mount": mounts.get("primary_mount", {}),
        "mount_policy": mounts.get("policy", ""),
        "visible": True,
        "enabled": not blocked,
        "blocked": blocked,
        "status": status,
        "disabled_reason": errors[0]["code"] if errors else "",
        "disabled_message": errors[0]["message"] if errors else "",
        "errors": errors,
        "warnings": warnings,
        "target_results": target_results,
        "system_results": system_results,
        "conflict_result": conflict_result,
        "cross_system_conflicts": conflict_result,
        "effective_extension": {
            "extension_id": extension_id,
            "targets": targets,
            "systems": systems,
            "workflow_mode": mode,
            "family": family,
            "workflow": workflow,
            "backend": backend,
            "active_systems": active_systems,
            "conflict_matrix_version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
            "enabled": not blocked,
        },
    }


def resolve_image_extension_block_compatibility(
    block: dict[str, dict[str, Any]] | None,
    *,
    external_registry: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .external_extension_workflow_validator import _registry_record_for  # local import avoids cycle

    block = block if isinstance(block, dict) else {}
    registry = external_registry if isinstance(external_registry, dict) else {}
    context = context if isinstance(context, dict) else {}
    results: dict[str, dict[str, Any]] = {}
    visible: list[str] = []
    enabled: list[str] = []
    blocked: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    effective_extensions: list[dict[str, Any]] = []

    for extension_id, entry in block.items():
        if not isinstance(entry, dict):
            continue
        result = resolve_image_extension_compatibility(
            extension_id,
            entry,
            registry_record=_registry_record_for(extension_id, registry),
            context=context,
        )
        results[extension_id] = result
        if result.get("visible"):
            visible.append(extension_id)
        if result.get("enabled"):
            enabled.append(extension_id)
            effective_extensions.append(_dict(result.get("effective_extension")))
        if result.get("blocked"):
            blocked.append(extension_id)
            errors.append(f"{extension_id}: {result.get('disabled_message') or result.get('disabled_reason')}")
        warnings.extend([f"{extension_id}: {item.get('message') or item.get('code')}" for item in result.get("warnings") or []])

    return {
        "version": IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        "matrix_version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "mount_rules_version": IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
        "conflict_matrix_version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
        "ok": not blocked,
        "visible": visible,
        "enabled": enabled,
        "blocked": blocked,
        "warnings": warnings,
        "errors": errors,
        "effective_extensions": effective_extensions,
        "results": results,
    }


def build_image_extension_compatibility_report(
    external_registry: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a UI-facing compatibility report for registered external extensions.

    This is a read-only resolver bridge for Phase D UI filtering. It does not
    enable, disable, mutate, or compile extension workflow patches. The caller
    can use the returned results to show visible disabled reasons before queue.
    """
    registry = external_registry if isinstance(external_registry, dict) else {}
    context = build_image_extension_compatibility_context(context or {})
    records: dict[str, dict[str, Any]] = {}
    for bucket in ("installed", "enabled", "disabled", "external_extensions", "extension_packs", "invalid", "invalid_extensions"):
        for item in registry.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            extension_id = _key(item.get("extension_id") or item.get("id"))
            if not extension_id or extension_id in records:
                continue
            records[extension_id] = item

    results: dict[str, dict[str, Any]] = {}
    visible: list[str] = []
    enabled: list[str] = []
    blocked: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    for extension_id, record in records.items():
        entry = {
            "enabled": bool(record.get("enabled")),
            "target_sections": _copy(record.get("target_sections") or []),
            "targets": _copy(record.get("targets") or record.get("extension_targets") or []),
            "extension_targets": _copy(record.get("extension_targets") or record.get("targets") or []),
            "supported_workflows": _copy(record.get("supported_workflows") or []),
            "supported_model_families": _copy(record.get("supported_model_families") or record.get("model_families") or []),
            "systems": _copy(record.get("systems") or record.get("image_systems") or []),
            "image_systems": _copy(record.get("image_systems") or record.get("systems") or []),
            "workflow": _copy(record.get("workflow") or {}),
            "output": _copy(record.get("output") or {}),
            "workflow_mode": record.get("workflow_mode"),
        }
        result = resolve_image_extension_compatibility(
            extension_id,
            entry,
            registry_record=record,
            context=context,
        )
        results[extension_id] = result
        if result.get("visible"):
            visible.append(extension_id)
        if result.get("enabled"):
            enabled.append(extension_id)
        if result.get("blocked"):
            blocked.append(extension_id)
            errors.append(f"{extension_id}: {result.get('disabled_message') or result.get('disabled_reason')}")
        warnings.extend([f"{extension_id}: {item.get('message') or item.get('code')}" for item in result.get("warnings") or []])

    return {
        "ok": not blocked,
        "version": IMAGE_EXTENSION_COMPATIBILITY_RESOLVER_VERSION,
        "matrix_version": MODEL_FAMILY_CAPABILITY_MATRIX_VERSION,
        "mount_rules_version": IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
        "conflict_matrix_version": IMAGE_CROSS_SYSTEM_CONFLICT_MATRIX_VERSION,
        "context": context,
        "visible": visible,
        "enabled": enabled,
        "blocked": blocked,
        "warnings": warnings,
        "errors": errors,
        "results": results,
        "policy": "ui_filter_with_visible_disabled_reason",
    }
