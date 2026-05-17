from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .image_extension_targets import canonical_image_extension_target, normalize_image_extension_targets

IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION = "image-extension-section-mount-rules-v1"


@dataclass(frozen=True)
class ImageExtensionMountRule:
    target: str
    section: str
    workspace: str
    slot: str
    dom_id: str
    label: str
    policy: str = "section_mount"


IMAGE_EXTENSION_SECTION_MOUNTS: dict[str, ImageExtensionMountRule] = {
    "image.build": ImageExtensionMountRule(
        target="image.build",
        section="build",
        workspace="create",
        slot="image.create.build.external_extensions",
        dom_id="neo-ext-slot-image-create-build",
        label="Build external extensions",
    ),
    "image.assets": ImageExtensionMountRule(
        target="image.assets",
        section="assets",
        workspace="assets_reuse",
        slot="image.assets_reuse.assets.external_extensions",
        dom_id="neo-ext-slot-image-assets-reuse-assets",
        label="Assets external extensions",
    ),
    "image.reference": ImageExtensionMountRule(
        target="image.reference",
        section="reference",
        workspace="guide_match",
        slot="image.guide_match.reference.external_extensions",
        dom_id="neo-ext-slot-image-guide-match-reference",
        label="Reference external extensions",
    ),
    "image.finish": ImageExtensionMountRule(
        target="image.finish",
        section="finish",
        workspace="enhance",
        slot="image.enhance.finish.external_extensions",
        dom_id="neo-ext-slot-image-enhance-finish",
        label="Finish external extensions",
    ),
    "image.results": ImageExtensionMountRule(
        target="image.results",
        section="results",
        workspace="results",
        slot="image.results.preview.external_extensions",
        dom_id="neo-ext-slot-image-results-preview",
        label="Results preview external extensions",
    ),
    "image.output": ImageExtensionMountRule(
        target="image.output",
        section="output",
        workspace="results",
        slot="image.results.output.external_extensions",
        dom_id="neo-ext-slot-image-results-output",
        label="Output external extensions",
    ),
    "image.workflow": ImageExtensionMountRule(
        target="image.workflow",
        section="workflow",
        workspace="create",
        slot="image.create.base_generation.external_extensions",
        dom_id="neo-ext-slot-image-create-base-generation",
        label="Workflow external extensions",
    ),
    "image.extensions_manager": ImageExtensionMountRule(
        target="image.extensions_manager",
        section="extensions",
        workspace="extensions",
        slot="image.extensions.manager",
        dom_id="neo-ext-slot-image-extensions-manager",
        label="Extensions manager",
        policy="manager_mount",
    ),
    "image.save_metadata": ImageExtensionMountRule(
        target="image.save_metadata",
        section="results",
        workspace="results",
        slot="image.results.output.external_extensions",
        dom_id="neo-ext-slot-image-results-output",
        label="Save metadata external extensions",
    ),
}

# Prefer operational Image sections over manager-only slots when an extension has
# multiple targets and did not explicitly choose a UI mount.
IMAGE_EXTENSION_PRIMARY_MOUNT_PRIORITY: tuple[str, ...] = (
    "image.workflow",
    "image.build",
    "image.reference",
    "image.assets",
    "image.finish",
    "image.output",
    "image.results",
    "image.save_metadata",
    "image.extensions_manager",
)


def _key(value: Any) -> str:
    return str(value if value is not None else "").strip().lower().replace(" ", "_")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _rule_to_dict(rule: ImageExtensionMountRule) -> dict[str, Any]:
    return {
        "target": rule.target,
        "section": rule.section,
        "workspace": rule.workspace,
        "slot": rule.slot,
        "dom_id": rule.dom_id,
        "label": rule.label,
        "policy": rule.policy,
    }


def _declared_targets(entry: dict[str, Any], registry_record: dict[str, Any] | None = None) -> list[str]:
    registry = registry_record if isinstance(registry_record, dict) else {}
    return normalize_image_extension_targets(
        entry.get("extension_targets")
        or entry.get("targets")
        or registry.get("extension_targets")
        or registry.get("targets")
        or entry.get("target_sections")
        or registry.get("target_sections")
        or []
    )


def _explicit_mount(entry: dict[str, Any], registry_record: dict[str, Any] | None = None) -> str:
    registry = registry_record if isinstance(registry_record, dict) else {}
    ui_entry = _dict(entry.get("ui_schema"))
    ui_registry = _dict(registry.get("ui_schema"))
    for value in (
        entry.get("mount"),
        entry.get("mount_point"),
        ui_entry.get("mount"),
        registry.get("mount"),
        registry.get("mount_point"),
        ui_registry.get("mount"),
    ):
        text = str(value if value is not None else "").strip()
        if text:
            return text
    return ""


def mount_rule_for_target(target: Any) -> dict[str, Any]:
    canonical = canonical_image_extension_target(target)
    rule = IMAGE_EXTENSION_SECTION_MOUNTS.get(canonical)
    return _rule_to_dict(rule) if rule else {}


def resolve_image_extension_mounts(
    extension_id: str,
    entry: dict[str, Any] | None = None,
    *,
    registry_record: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve section mount slots for one Image extension.

    This is read-only routing metadata. It does not enable an extension, move data,
    or mutate the manifest. UI layers can use it to mount panels in the relevant
    Image subtab while preserving visible disabled states from the compatibility resolver.
    """
    entry = entry if isinstance(entry, dict) else {}
    registry = registry_record if isinstance(registry_record, dict) else {}
    context = context if isinstance(context, dict) else {}
    section_filter = canonical_image_extension_target(context.get("section") or context.get("target_section") or "")
    targets = _declared_targets(entry, registry)
    explicit_mount = _explicit_mount(entry, registry)

    mounts: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for target in targets:
        rule = IMAGE_EXTENSION_SECTION_MOUNTS.get(target)
        if not rule:
            continue
        if section_filter and target != section_filter:
            continue
        mount = _rule_to_dict(rule)
        if mount["slot"] in seen_slots:
            continue
        seen_slots.add(mount["slot"])
        mounts.append(mount)

    primary_target = ""
    for target in IMAGE_EXTENSION_PRIMARY_MOUNT_PRIORITY:
        if target in targets and (not section_filter or target == section_filter):
            primary_target = target
            break
    if not primary_target and targets:
        primary_target = targets[0]

    primary_mount = mount_rule_for_target(primary_target)
    if explicit_mount:
        # Explicit UI mount remains authoritative for backwards compatibility.
        primary_mount = {
            "target": primary_target or "image.extensions_manager",
            "section": "explicit",
            "workspace": "explicit",
            "slot": explicit_mount,
            "dom_id": "",
            "label": "Explicit extension UI mount",
            "policy": "explicit_manifest_mount",
        }

    return {
        "version": IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
        "extension_id": _key(extension_id),
        "targets": targets,
        "section_filter": section_filter,
        "explicit_mount": explicit_mount,
        "mounts": mounts,
        "primary_target": primary_target,
        "primary_mount": primary_mount,
        "policy": "explicit_manifest_mount_preserved_else_section_target_mount",
    }


def build_image_extension_mount_report(
    external_registry: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = external_registry if isinstance(external_registry, dict) else {}
    context = context if isinstance(context, dict) else {}
    records: dict[str, dict[str, Any]] = {}
    for bucket in ("installed", "enabled", "disabled", "external_extensions", "extension_packs", "invalid", "invalid_extensions"):
        for item in registry.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            extension_id = _key(item.get("extension_id") or item.get("id"))
            if not extension_id or extension_id in records:
                continue
            records[extension_id] = item

    results = {
        extension_id: resolve_image_extension_mounts(extension_id, record, registry_record=record, context=context)
        for extension_id, record in records.items()
    }
    return {
        "ok": True,
        "version": IMAGE_EXTENSION_SECTION_MOUNT_RULES_VERSION,
        "context": {
            "surface": _key(context.get("surface") or "image") or "image",
            "section": _key(context.get("section") or context.get("target_section") or ""),
            "workspace": _key(context.get("workspace") or ""),
        },
        "results": results,
        "available_mounts": [_rule_to_dict(rule) for rule in IMAGE_EXTENSION_SECTION_MOUNTS.values()],
        "policy": "section_mount_rules_with_explicit_manifest_mount_preserved",
    }
