from __future__ import annotations

"""Source-aware Assistant retrieval gates.

Phase 13 sits above Phase 12 sandboxing. Phase 12 prevents accidental project
bleed. Phase 13 adds an intentional, disclosed creative-reference path: global
chat may use project lore as story context, but never as global truth and never
for client/private data.
"""

from dataclasses import asdict, dataclass
import re
from typing import Any

from .assistant_memory_sandbox import (
    is_memory_allowed_for_scope,
    normalize_chunk_scope_metadata,
    PRIVATE_SCOPES,
    QUARANTINE_SCOPES,
)

RETRIEVAL_MODES = {
    "global_safe",
    "project_active",
    "cross_project_search",
    "admin_debug",
    "creative_reference",
}

CREATIVE_DOMAINS = {"creative_lore", "worldbuilding", "story", "fiction", "roleplay", "structured_data"}
CREATIVE_IMPORT_TYPES = {"raw_creative_lore", "markdown_lore", "json_schema", "worldbuilding_lore"}
CREATIVE_CHUNK_TYPES = {
    "lore_record",
    "canon_guard",
    "definition_record",
    "relationship_record",
    "event_record",
    "myth_record",
    "world_lore_concept",
    "world_fact",
    "character_fact",
}
SENSITIVE_DOMAINS = {"client_work", "communication", "email", "private", "sensitive"}

CREATIVE_QUERY_SIGNALS = {
    "lore", "story", "fiction", "world", "worldbuilding", "canon", "character", "realm",
    "void", "magic", "myth", "mythology", "chapter", "scene", "plot", "universe",
    "creature", "faction", "kingdom", "ritual", "spell", "curse", "what is", "who is",
}


@dataclass(frozen=True)
class SourceAwareDecision:
    allowed: bool
    reason: str
    retrieval_mode: str
    disclosure_required: bool = False
    disclosure_label: str = ""
    source_project_id: str = ""
    source_project_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, limit)]


def _lower(value: Any, limit: int = 240) -> str:
    return _clean(value, limit).lower()


def query_looks_creative_reference(query_text: str, scope: dict[str, Any] | None = None) -> bool:
    scope = scope if isinstance(scope, dict) else {}
    text = _lower(" ".join([
        query_text,
        scope.get("latest_user_message") or "",
        scope.get("thread_instruction") or "",
        scope.get("context_note") or "",
    ]), 3000)
    if not text:
        return False
    if any(signal in text for signal in CREATIVE_QUERY_SIGNALS):
        return True
    # Single proper-ish fantasy identifier, e.g. DarkVoid/Dark Void, is often a lore lookup.
    compact = re.sub(r"[^a-z0-9]+", "", text)
    return len(compact) >= 5 and len(text.split()) <= 6 and not any(ch.isdigit() for ch in compact)


def resolve_source_aware_retrieval_mode(
    *,
    scope: dict[str, Any] | None,
    query_text: str = "",
    requested_mode: str = "",
) -> str:
    scope = scope if isinstance(scope, dict) else {}
    requested = _lower(requested_mode or scope.get("retrieval_mode") or scope.get("memory_retrieval_mode"), 120)
    if requested in RETRIEVAL_MODES:
        return requested
    if bool(scope.get("admin_debug_memory") or scope.get("debug_memory")):
        return "admin_debug"
    if bool(scope.get("allow_cross_project_memory") or scope.get("explicit_project_memory_access")):
        return "cross_project_search"
    if _clean(scope.get("project_id"), 120):
        return "project_active"
    if query_looks_creative_reference(query_text, scope):
        return "creative_reference"
    return "global_safe"


def _is_sensitive_project_memory(meta: dict[str, Any]) -> bool:
    domain = _lower(meta.get("assistant_domain"), 120)
    import_type = _lower(meta.get("import_type"), 120)
    visibility = _lower(meta.get("visibility"), 120)
    bleed_policy = _lower(meta.get("bleed_policy"), 120)
    memory_scope = _lower(meta.get("memory_scope"), 80)
    if memory_scope in PRIVATE_SCOPES or memory_scope in QUARANTINE_SCOPES:
        return True
    if domain in SENSITIVE_DOMAINS:
        return True
    if import_type in {"client_project_data", "email_or_message_data"}:
        return True
    if visibility in {"private", "sensitive", "client_private", "hidden_until_review"}:
        return True
    if bleed_policy in {"private_only", "quarantine"}:
        return True
    return False


def _is_creative_project_memory(meta: dict[str, Any]) -> bool:
    domain = _lower(meta.get("assistant_domain"), 120)
    import_type = _lower(meta.get("import_type"), 120)
    chunk_type = _lower(meta.get("chunk_type"), 120)
    project_type = _lower(meta.get("project_type"), 120)
    answer_role = _lower(meta.get("answer_context_role"), 120)
    tags = meta.get("retrieval_tags") if isinstance(meta.get("retrieval_tags"), list) else []
    tag_text = _lower(" ".join(str(t) for t in tags[:80]), 1000)
    return (
        domain in CREATIVE_DOMAINS
        or import_type in CREATIVE_IMPORT_TYPES
        or chunk_type in CREATIVE_CHUNK_TYPES
        or project_type in {"worldbuilding", "creative", "fiction", "lore"}
        or answer_role == "canon_evidence"
        or any(token in tag_text for token in ("lore", "canon", "worldbuilding", "character", "myth"))
    )


def source_disclosure_label(meta: dict[str, Any]) -> str:
    project_title = _clean(meta.get("project_title"), 120)
    project_id = _clean(meta.get("memory_project_id") or meta.get("project_id"), 120)
    label = project_title or project_id or "linked project"
    return f"From {label} project memory"


def is_memory_allowed_source_aware(
    metadata: dict[str, Any] | None,
    scope: dict[str, Any] | None,
    retrieval_mode: str,
) -> SourceAwareDecision:
    meta = normalize_chunk_scope_metadata(metadata)
    scope = scope if isinstance(scope, dict) else {}
    mode = _lower(retrieval_mode, 80) or "global_safe"
    project_id = _clean(meta.get("memory_project_id") or meta.get("project_id"), 120)
    project_title = _clean(meta.get("project_title"), 120)
    memory_scope = _lower(meta.get("memory_scope"), 80)
    bleed_policy = _lower(meta.get("bleed_policy"), 120)

    if mode == "admin_debug":
        if memory_scope in QUARANTINE_SCOPES or bleed_policy == "quarantine":
            return SourceAwareDecision(False, "quarantine_hidden_even_in_debug", mode, False, "", project_id, project_title)
        return SourceAwareDecision(True, "admin_debug_allowed", mode, bool(project_id), source_disclosure_label(meta), project_id, project_title)

    if mode == "global_safe":
        if project_id or memory_scope in {"project", "project_only", "session", "thread"} or bleed_policy == "deny_global":
            return SourceAwareDecision(False, "global_safe_blocks_project_memory", mode, False, "", project_id, project_title)
        base = is_memory_allowed_for_scope(meta, {**scope, "project_id": "", "allow_cross_project_memory": False})
        return SourceAwareDecision(base.allowed, base.reason, mode, False, "", project_id, project_title)

    if mode == "project_active":
        base = is_memory_allowed_for_scope(meta, scope)
        return SourceAwareDecision(base.allowed, base.reason, mode, False, "", project_id, project_title)

    if mode == "creative_reference":
        base = is_memory_allowed_for_scope(meta, {**scope, "project_id": "", "allow_cross_project_memory": False})
        if base.allowed:
            return SourceAwareDecision(True, "global_or_profile_memory", mode, False, "", project_id, project_title)
        if project_id and not _is_sensitive_project_memory(meta) and _is_creative_project_memory(meta):
            return SourceAwareDecision(True, "creative_project_reference_allowed_with_disclosure", mode, True, source_disclosure_label(meta), project_id, project_title)
        return SourceAwareDecision(False, "creative_reference_blocks_non_lore_or_sensitive_project_memory", mode, False, "", project_id, project_title)

    if mode == "cross_project_search":
        if _is_sensitive_project_memory(meta):
            return SourceAwareDecision(False, "cross_project_blocks_sensitive_or_private_memory", mode, False, "", project_id, project_title)
        return SourceAwareDecision(True, "explicit_cross_project_allowed_with_disclosure", mode, bool(project_id), source_disclosure_label(meta), project_id, project_title)

    base = is_memory_allowed_for_scope(meta, scope)
    return SourceAwareDecision(base.allowed, base.reason, mode, False, "", project_id, project_title)


def source_aware_filter_items(
    items: list[dict[str, Any]],
    scope: dict[str, Any] | None,
    retrieval_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    for item in items or []:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        normalized = normalize_chunk_scope_metadata(metadata)
        decision = is_memory_allowed_source_aware(normalized, scope, retrieval_mode)
        enriched_meta = dict(normalized)
        enriched_meta["retrieval_mode"] = decision.retrieval_mode
        enriched_meta["source_disclosure_required"] = bool(decision.disclosure_required)
        enriched_meta["source_disclosure_label"] = decision.disclosure_label
        enriched_meta["source_context_policy"] = "fictional_or_project_context_only" if decision.disclosure_required else "normal_context"
        enriched = {**item, "metadata": enriched_meta, "source_aware_decision": decision.to_dict()}
        if decision.allowed:
            allowed.append(enriched)
        else:
            denied.append({**enriched, "drop_reason": decision.reason})
    return allowed, denied


def build_source_disclosure_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    labels: list[str] = []
    project_ids: list[str] = []
    for item in items or []:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if not bool(meta.get("source_disclosure_required")):
            continue
        label = _clean(meta.get("source_disclosure_label"), 160)
        project_id = _clean(meta.get("memory_project_id") or meta.get("project_id"), 120)
        if label and label not in labels:
            labels.append(label)
        if project_id and project_id not in project_ids:
            project_ids.append(project_id)
    return {
        "required": bool(labels),
        "labels": labels[:8],
        "project_ids": project_ids[:8],
        "instruction": "When using disclosed project memories in global chat, label them as project/story context, not real-world/global truth." if labels else "",
    }
