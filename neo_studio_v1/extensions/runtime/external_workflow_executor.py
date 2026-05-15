from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from ...utils.extension_registry import build_external_extension_registry

RUNTIME_VERSION = "external-workflow-executor-v1"
SUPPORTED_STRATEGIES = {"replace_workflow", "sidecar_run", "postprocess_output", "preprocess_source", "append_nodes", "metadata_only"}


def _as_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def _key(value: Any) -> str:
    return _text(value).lower().replace(" ", "_")


def _first(payload: Mapping[str, Any], *keys: str, fallback: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return fallback


def _build_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the generic extension context from the normalized generation payload."""
    payload = _as_dict(payload)
    mode = _key(_first(payload, "mode", "workflow_type", "_neo_effective_mode", fallback="txt2img")) or "txt2img"
    family = _key(_first(payload, "family", "model_family", "generation_family", "_neo_effective_family", fallback="sdxl_sd")) or "sdxl_sd"
    batch_size = _first(payload, "_neo_effective_batch_size", "batch_size", "batch", fallback=1)
    try:
        batch_size = max(1, int(batch_size))
    except Exception:
        batch_size = 1
    return {
        "surface": "image",
        "workflow": mode,
        "workflow_type": mode,
        "mode": mode,
        "family": family,
        "model_family": family,
        "generation_family": family,
        "batch_size": batch_size,
        "prompt": _first(payload, "positive", "positive_prompt", "prompt", fallback=""),
        "positive": _first(payload, "positive", "positive_prompt", "prompt", fallback=""),
        "positive_prompt": _first(payload, "positive_prompt", "positive", "prompt", fallback=""),
        "negative_prompt": _first(payload, "negative_prompt", "negative", fallback=""),
        "negative": _first(payload, "negative", "negative_prompt", fallback=""),
        "checkpoint": _first(payload, "checkpoint", "ckpt_name", "model", fallback=""),
        "ckpt_name": _first(payload, "ckpt_name", "checkpoint", "model", fallback=""),
        "model": _first(payload, "model", "checkpoint", "ckpt_name", fallback=""),
        "seed": _first(payload, "seed", fallback=0),
        "steps": _first(payload, "steps", "sampling_steps", fallback=28),
        "cfg": _first(payload, "cfg", "cfg_scale", fallback=5.0),
        "cfg_scale": _first(payload, "cfg_scale", "cfg", fallback=5.0),
        "sampler": _first(payload, "sampler", "sampler_name", fallback="dpmpp_2m_sde"),
        "sampler_name": _first(payload, "sampler_name", "sampler", fallback="dpmpp_2m_sde"),
        "scheduler": _first(payload, "scheduler", fallback="karras"),
        "denoise": _first(payload, "denoise", "denoising_strength", fallback=1.0),
        "denoising_strength": _first(payload, "denoising_strength", "denoise", fallback=1.0),
        "width": _first(payload, "width", "W", fallback=1024),
        "height": _first(payload, "height", "H", fallback=1024),
        "has_prompt": bool(_text(_first(payload, "positive", "positive_prompt", "prompt", fallback=""))),
        "prompt_available": bool(_text(_first(payload, "positive", "positive_prompt", "prompt", fallback=""))),
        "source_image_name": _first(payload, "source_image_name", "init_image_name", "input_image_name", fallback=""),
        "source_image_available": bool(_first(payload, "source_image_name", "init_image_name", "input_image_name", fallback="")),
        "selected_output_available": bool(_first(payload, "generationSelectedOutputSnapshot", "selected_output_snapshot", fallback=None)),
    }


def _records_by_id(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for bucket in ("enabled", "installed", "disabled", "invalid"):
        for item in _as_list(registry.get(bucket)):
            if not isinstance(item, dict):
                continue
            extension_id = _text(item.get("extension_id") or item.get("id"))
            if extension_id and extension_id not in out:
                out[extension_id] = item
    return out


def _safe_backend_entry(record: Mapping[str, Any]) -> str:
    entry = _text(record.get("backend_entry") or record.get("backend_routes"))
    if not entry:
        raw = _as_dict(record.get("raw_manifest"))
        entry = _text(raw.get("backend_entry") or raw.get("backend_routes"))
    entry = entry.replace("\\", "/")
    if entry.startswith("/") or ".." in Path(entry).parts:
        return ""
    return entry


def _load_adapter_function(record: Mapping[str, Any]) -> tuple[Callable[..., dict[str, Any]] | None, str | None]:
    extension_id = _text(record.get("extension_id") or record.get("id")) or "external_extension"
    extension_dir = Path(_text(record.get("extension_dir")))
    if not extension_dir.exists():
        return None, "extension_dir_missing"
    entry = _safe_backend_entry(record) or "backend/adapter.py"
    adapter_path = (extension_dir / entry).resolve()
    try:
        adapter_path.relative_to(extension_dir.resolve())
    except Exception:
        return None, "backend_entry_outside_extension_dir"
    if not adapter_path.exists():
        return None, f"backend_entry_missing:{entry}"
    module_name = "neo_external_adapter_" + "".join(ch if ch.isalnum() else "_" for ch in extension_id)
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        return None, "backend_entry_import_spec_failed"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        return None, f"backend_entry_import_failed:{exc}"
    fn = getattr(module, "build_execution_plan", None)
    if not callable(fn):
        return None, "build_execution_plan_missing"
    return fn, None


def _extract_active_extension_entries(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    block = _as_dict(payload.get("external_extensions"))
    out: dict[str, dict[str, Any]] = {}
    for extension_id, entry in block.items():
        if not isinstance(entry, dict):
            continue
        requested = bool(entry.get("enabled"))
        effective = bool(entry.get("effective_enabled") or _as_dict(entry.get("effective_state")).get("effective_enabled") or _as_dict(entry.get("effective_state")).get("active"))
        if requested and effective:
            out[str(extension_id)] = entry
    return out


def _plan_graph_from(plan: Mapping[str, Any]) -> dict[str, Any]:
    patch = _as_dict(plan.get("workflow_patch"))
    graph = _as_dict(patch.get("graph"))
    if graph:
        return graph
    comfy_package = _as_dict(patch.get("comfyui_graph"))
    return _as_dict(comfy_package.get("graph"))


def _plan_strategy(plan: Mapping[str, Any]) -> str:
    return _key(_as_dict(plan.get("workflow_patch")).get("strategy"))


def _plan_is_effective(plan: Mapping[str, Any]) -> bool:
    effective = _as_dict(plan.get("effective_state"))
    patch = _as_dict(plan.get("workflow_patch"))
    return bool(effective.get("effective_enabled") or effective.get("active") or patch.get("enabled"))


def apply_external_workflow_injection(
    workflow: dict[str, Any],
    payload: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Apply validated external workflow execution plans to a compiled workflow.

    This is the global runtime bridge. Extension adapters may declare workflow
    patches, but only this function can mutate/replace the ComfyUI graph used by
    Neo. It keeps every mutation visible in the payload metadata.
    """
    workflow = _as_dict(workflow)
    payload = _as_dict(payload)
    registry = registry if isinstance(registry, dict) else build_external_extension_registry(surface="image", include_invalid=True)
    records = _records_by_id(registry)
    active_entries = _extract_active_extension_entries(payload)
    if not active_entries:
        payload.setdefault("_neo_external_workflow_execution", {
            "runtime_version": RUNTIME_VERSION,
            "applied": False,
            "reason": "no_effective_external_extensions",
        })
        return workflow, payload, []

    notes: list[str] = []
    context = _build_context(payload)
    replacement_plans: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    non_replacement_plans: list[dict[str, Any]] = []

    for extension_id, entry in active_entries.items():
        record = records.get(extension_id) or {}
        if not record:
            notes.append(f"External workflow runtime skipped {extension_id}: registry record missing.")
            continue
        build_plan, load_error = _load_adapter_function(record)
        if load_error or not build_plan:
            raise ValueError(f"External extension {extension_id} cannot execute: {load_error or 'adapter unavailable'}")
        raw_state = _as_dict(entry.get("raw_state"))
        # Preserve the visible user-enabled state even when the frontend raw_state
        # only stored field-level settings.
        raw_state.setdefault("enabled", bool(entry.get("enabled", True)))
        try:
            plan = build_plan(raw_state, context, extension_root=record.get("extension_dir"))
        except Exception as exc:
            raise ValueError(f"External extension {extension_id} execution plan failed: {exc}") from exc
        plan = _as_dict(plan)
        payload_entry = _as_dict(plan.get("payload_entry"))
        if payload_entry:
            payload.setdefault("external_extensions", {})[extension_id] = payload_entry
        strategy = _plan_strategy(plan)
        if strategy and strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(f"External extension {extension_id} declared unsupported workflow strategy: {strategy}")
        if not _plan_is_effective(plan):
            notes.append(f"External extension {extension_id} produced a non-effective execution plan; workflow left unchanged.")
            continue
        if strategy == "replace_workflow":
            graph = _plan_graph_from(plan)
            if not graph:
                raise ValueError(f"External extension {extension_id} requested replace_workflow but did not provide an executable ComfyUI graph.")
            replacement_plans.append((extension_id, plan, graph))
        else:
            non_replacement_plans.append({
                "extension_id": extension_id,
                "strategy": strategy or "metadata_only",
                "status": "declared_not_applied_in_phase13",
            })
            notes.append(f"External extension {extension_id} declared {strategy or 'metadata_only'}; Phase 13 only mutates replace_workflow graphs.")

    if len(replacement_plans) > 1:
        ids = ", ".join(item[0] for item in replacement_plans)
        raise ValueError(f"Multiple external extensions requested replace_workflow in the same run: {ids}. Disable one extension before queueing.")

    execution_record: dict[str, Any] = {
        "runtime_version": RUNTIME_VERSION,
        "applied": False,
        "strategy": None,
        "extension_id": None,
        "notes": notes,
        "non_replacement_plans": non_replacement_plans,
    }

    if replacement_plans:
        extension_id, plan, graph = replacement_plans[0]
        workflow = graph
        patch = _as_dict(plan.get("workflow_patch"))
        effective = _as_dict(plan.get("effective_state"))
        metadata = _as_dict(plan.get("metadata"))
        execution_record.update({
            "applied": True,
            "strategy": "replace_workflow",
            "extension_id": extension_id,
            "template": patch.get("template") or effective.get("workflow_template"),
            "graph_wiring_version": patch.get("graph_wiring_version"),
            "primary_output_type": patch.get("primary_output_type"),
            "output_bindings": _as_dict(patch.get("output_bindings")),
            "node_count": len(workflow),
            "policy": "base_graph_replaced_by_validated_external_template",
        })
        payload["_neo_external_workflow_replaced"] = True
        payload["_neo_external_workflow_replaced_by"] = extension_id
        payload["_neo_external_workflow_template"] = execution_record.get("template")
        payload["_neo_external_workflow_primary_output_type"] = execution_record.get("primary_output_type")
        payload["_neo_effective_batch_size"] = 1
        payload["batch_size"] = 1
        payload.setdefault("_neo_external_extensions_runtime_metadata", {})[extension_id] = metadata
        notes.append(f"External workflow runtime replaced base graph with {extension_id} template {execution_record.get('template') or 'unknown'}.")

    payload["_neo_external_workflow_execution"] = execution_record
    return workflow, payload, notes
