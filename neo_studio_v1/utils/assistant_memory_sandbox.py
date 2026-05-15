from __future__ import annotations

"""Project memory sandboxing helpers for Assistant memory.

Phase 12 rule: memory is filtered by scope before it is allowed into an
answer context. Scoring/reranking must never be the thing that prevents bleed;
bleed prevention is a hard eligibility gate.
"""

from dataclasses import asdict, dataclass
from typing import Any

GLOBAL_SCOPES = {"global", "profile", "assistant_wide"}
PROJECT_SCOPES = {"project", "project_only"}
SESSION_SCOPES = {"session", "thread"}
PRIVATE_SCOPES = {"private", "sensitive"}
QUARANTINE_SCOPES = {"quarantine", "review"}

ALLOW_GLOBAL_POLICIES = {"allow_global", "assistant_wide", "global_ok"}
DENY_GLOBAL_POLICIES = {"deny_global", "project_only", "session_only", "private_only", "quarantine"}


@dataclass(frozen=True)
class MemoryScopeDecision:
    allowed: bool
    reason: str
    memory_scope: str
    project_id: str
    bleed_policy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, limit)]


def infer_memory_scope_for_import(*, project_id: str, visibility: str, assistant_domain: str = "", import_type: str = "") -> dict[str, str]:
    """Return canonical scope metadata for a new imported memory chunk.

    Defaults are intentionally strict: uploads made inside a project are project
    memories unless the visibility explicitly says assistant/global. This keeps
    Mood Pixel lore out of normal assistant chat and keeps client data boxed.
    """

    clean_project_id = _clean(project_id, 120)
    clean_visibility = _clean(visibility, 120).lower()
    domain = _clean(assistant_domain, 120).lower()
    import_kind = _clean(import_type, 120).lower()

    if clean_visibility in {"global", "assistant_wide", "profile", "public_global"}:
        return {
            "memory_scope": "global",
            "memory_project_id": "",
            "visibility": clean_visibility or "assistant_wide",
            "bleed_policy": "allow_global",
            "sandbox_policy": "global_visible",
        }

    if clean_visibility in {"quarantine", "review", "hidden_until_review"}:
        return {
            "memory_scope": "quarantine",
            "memory_project_id": clean_project_id,
            "visibility": "hidden_until_review",
            "bleed_policy": "quarantine",
            "sandbox_policy": "deny_until_reviewed",
        }

    if clean_visibility in {"private", "sensitive", "client_private"} or domain in {"client_work", "communication"}:
        return {
            "memory_scope": "project",
            "memory_project_id": clean_project_id,
            "visibility": clean_visibility or "project_private",
            "bleed_policy": "deny_global",
            "sandbox_policy": "project_boxed_private",
        }

    if clean_project_id:
        return {
            "memory_scope": "project",
            "memory_project_id": clean_project_id,
            "visibility": clean_visibility or "project_private",
            "bleed_policy": "deny_global",
            "sandbox_policy": "project_boxed",
        }

    return {
        "memory_scope": "global",
        "memory_project_id": "",
        "visibility": clean_visibility or "assistant_wide",
        "bleed_policy": "allow_global",
        "sandbox_policy": "global_visible",
    }


def normalize_chunk_scope_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict(metadata or {})
    scope_type = _clean(meta.get("scope_type"), 80).lower()
    project_id = _clean(meta.get("project_id") or meta.get("memory_project_id"), 120)
    visibility = _clean(meta.get("visibility"), 120).lower()

    memory_scope = _clean(meta.get("memory_scope"), 80).lower()
    if not memory_scope:
        if scope_type in {"profile", "global"}:
            memory_scope = "global"
        elif scope_type == "session":
            memory_scope = "session"
        elif project_id or scope_type == "project":
            memory_scope = "project"
        else:
            memory_scope = "global"

    memory_project_id = _clean(meta.get("memory_project_id") or project_id, 120)
    bleed_policy = _clean(meta.get("bleed_policy"), 120).lower()
    if not bleed_policy:
        if memory_scope in PROJECT_SCOPES or memory_project_id:
            bleed_policy = "deny_global"
        elif memory_scope in QUARANTINE_SCOPES:
            bleed_policy = "quarantine"
        elif memory_scope in PRIVATE_SCOPES:
            bleed_policy = "private_only"
        else:
            bleed_policy = "allow_global"

    meta["memory_scope"] = memory_scope
    meta["memory_project_id"] = memory_project_id
    meta["bleed_policy"] = bleed_policy
    meta["sandbox_policy"] = _clean(meta.get("sandbox_policy") or ("project_boxed" if memory_project_id else "global_visible"), 120)
    meta["visibility"] = visibility or _clean(meta.get("visibility") or ("project_private" if memory_project_id else "assistant_wide"), 120)
    return meta


def is_memory_allowed_for_scope(metadata: dict[str, Any] | None, active_scope: dict[str, Any] | None) -> MemoryScopeDecision:
    meta = normalize_chunk_scope_metadata(metadata)
    scope = active_scope if isinstance(active_scope, dict) else {}
    active_project_id = _clean(scope.get("project_id"), 120)
    active_session_id = _clean(scope.get("session_id"), 120)
    explicit_private = bool(scope.get("allow_private_memory") or scope.get("explicit_private_memory_access"))
    explicit_cross_project = bool(scope.get("allow_cross_project_memory") or scope.get("explicit_project_memory_access"))

    memory_scope = _clean(meta.get("memory_scope"), 80).lower()
    memory_project_id = _clean(meta.get("memory_project_id") or meta.get("project_id"), 120)
    memory_session_id = _clean(meta.get("memory_session_id") or (meta.get("scope_id") if meta.get("scope_type") == "session" else ""), 120)
    bleed_policy = _clean(meta.get("bleed_policy"), 120).lower()

    if memory_scope in QUARANTINE_SCOPES or bleed_policy == "quarantine":
        return MemoryScopeDecision(False, "quarantine_hidden_until_review", memory_scope, memory_project_id, bleed_policy)

    if memory_scope in PRIVATE_SCOPES or bleed_policy == "private_only":
        if explicit_private:
            return MemoryScopeDecision(True, "explicit_private_access", memory_scope, memory_project_id, bleed_policy)
        return MemoryScopeDecision(False, "private_memory_requires_explicit_access", memory_scope, memory_project_id, bleed_policy)

    if memory_scope in SESSION_SCOPES:
        if active_session_id and memory_session_id and active_session_id == memory_session_id:
            return MemoryScopeDecision(True, "same_session", memory_scope, memory_project_id, bleed_policy)
        return MemoryScopeDecision(False, "different_session", memory_scope, memory_project_id, bleed_policy)

    if memory_scope in PROJECT_SCOPES or memory_project_id:
        if active_project_id and memory_project_id and active_project_id == memory_project_id:
            return MemoryScopeDecision(True, "same_project", memory_scope or "project", memory_project_id, bleed_policy)
        if explicit_cross_project:
            return MemoryScopeDecision(True, "explicit_cross_project_access", memory_scope or "project", memory_project_id, bleed_policy)
        return MemoryScopeDecision(False, "project_memory_denied_outside_active_project", memory_scope or "project", memory_project_id, bleed_policy)

    if memory_scope in GLOBAL_SCOPES or bleed_policy in ALLOW_GLOBAL_POLICIES:
        return MemoryScopeDecision(True, "global_memory", memory_scope or "global", memory_project_id, bleed_policy or "allow_global")

    if bleed_policy in DENY_GLOBAL_POLICIES and not active_project_id:
        return MemoryScopeDecision(False, "deny_global_policy", memory_scope, memory_project_id, bleed_policy)

    return MemoryScopeDecision(True, "default_allowed_global", memory_scope or "global", memory_project_id, bleed_policy or "allow_global")


def sandbox_filter_items(items: list[dict[str, Any]], scope: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    for item in items or []:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        normalized = normalize_chunk_scope_metadata(metadata)
        decision = is_memory_allowed_for_scope(normalized, scope)
        enriched = {**item, "metadata": normalized, "sandbox_decision": decision.to_dict()}
        if decision.allowed:
            allowed.append(enriched)
        else:
            denied.append({**enriched, "drop_reason": decision.reason})
    return allowed, denied
