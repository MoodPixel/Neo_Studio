from __future__ import annotations

"""Retrieval authority modes for Assistant memory answers.

Phase 15 controls how retrieved memory competes with the model's built-in
knowledge. Sandboxing decides *which memories may be seen*. Authority decides
*which source is allowed to drive the answer*.
"""

from dataclasses import asdict, dataclass
from typing import Any

from .assistant_retrieval_grounding import build_grounding_prompt_block, grounding_metadata

AUTHORITY_MODES = {
    "canon_strict",
    "hybrid_creative",
    "real_world_strict",
    "evidence_strict",
    "assistant_balanced",
}

CANON_PROJECT_TYPES = {
    "universe",
    "worldbuilding",
    "fiction",
    "story",
    "roleplay",
    "creative_lore",
    "lore",
}

EVIDENCE_PROJECT_TYPES = {
    "client",
    "client_work",
    "email",
    "communication",
    "business",
    "legalish",
    "project_docs",
    "technical",
    "code",
}

EXTERNAL_COMPARISON_SIGNALS = {
    "real world",
    "irl",
    "actual",
    "astronomy",
    "science",
    "historical",
    "compare",
    "outside the project",
    "external meaning",
    "symbolism",
    "inspiration",
}


@dataclass(frozen=True)
class AuthorityDecision:
    authority_mode: str
    reason: str
    suppress_pretrained_knowledge: bool
    allow_external_blending: bool
    require_source_grounding: bool
    missing_memory_policy: str
    project_memory_is_authoritative: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, limit)]


def _lower(value: Any, limit: int = 240) -> str:
    return _clean(value, limit).lower()


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def query_requests_external_blending(query_text: str, scope: dict[str, Any] | None = None) -> bool:
    scope = _safe_dict(scope)
    text = _lower("\n".join([
        query_text,
        scope.get("latest_user_message") or "",
        scope.get("thread_instruction") or "",
        scope.get("context_note") or "",
    ]), 3000)
    return any(signal in text for signal in EXTERNAL_COMPARISON_SIGNALS)


def resolve_authority_mode(
    *,
    scope: dict[str, Any] | None = None,
    query_text: str = "",
    requested_mode: str = "",
) -> AuthorityDecision:
    scope = _safe_dict(scope)
    requested = _lower(
        requested_mode
        or scope.get("authority_mode")
        or scope.get("retrieval_authority_mode")
        or scope.get("answer_authority_mode")
        or scope.get("memory_authority_mode"),
        120,
    )
    project_id = _clean(scope.get("project_id"), 120)
    project_type = _lower(scope.get("project_type"), 120)
    project_profile_label = _lower(scope.get("project_profile_label"), 160)
    mode = _lower(scope.get("mode"), 80)
    external_requested = query_requests_external_blending(query_text, scope)

    if requested in AUTHORITY_MODES:
        selected = requested
        reason = "explicit_authority_mode"
    elif project_id and (project_type in CANON_PROJECT_TYPES or any(t in project_profile_label for t in CANON_PROJECT_TYPES)):
        selected = "hybrid_creative" if external_requested else "canon_strict"
        reason = "creative_project_defaults_to_canon_strict"
    elif project_id and (project_type in EVIDENCE_PROJECT_TYPES or any(t in project_profile_label for t in EVIDENCE_PROJECT_TYPES)):
        selected = "evidence_strict"
        reason = "evidence_project_defaults_to_source_grounded"
    elif mode in {"writing", "brainstorm", "creative"}:
        selected = "hybrid_creative"
        reason = "creative_thread_mode"
    elif project_id:
        selected = "assistant_balanced"
        reason = "general_project_context"
    else:
        selected = "real_world_strict"
        reason = "global_chat_defaults_to_real_world"

    if selected == "canon_strict":
        return AuthorityDecision(
            authority_mode=selected,
            reason=reason,
            suppress_pretrained_knowledge=True,
            allow_external_blending=False,
            require_source_grounding=True,
            missing_memory_policy="say_project_canon_not_found_before_guessing",
            project_memory_is_authoritative=True,
        )
    if selected == "evidence_strict":
        return AuthorityDecision(
            authority_mode=selected,
            reason=reason,
            suppress_pretrained_knowledge=True,
            allow_external_blending=False,
            require_source_grounding=True,
            missing_memory_policy="say_source_not_found_before_guessing",
            project_memory_is_authoritative=True,
        )
    if selected == "real_world_strict":
        return AuthorityDecision(
            authority_mode=selected,
            reason=reason,
            suppress_pretrained_knowledge=False,
            allow_external_blending=False,
            require_source_grounding=False,
            missing_memory_policy="answer_from_general_knowledge_when_safe",
            project_memory_is_authoritative=False,
        )
    if selected == "hybrid_creative":
        return AuthorityDecision(
            authority_mode=selected,
            reason=reason,
            suppress_pretrained_knowledge=False,
            allow_external_blending=True,
            require_source_grounding=False,
            missing_memory_policy="blend_only_when_helpful_and_label_sources",
            project_memory_is_authoritative=False,
        )
    return AuthorityDecision(
        authority_mode="assistant_balanced",
        reason=reason,
        suppress_pretrained_knowledge=False,
        allow_external_blending=True,
        require_source_grounding=False,
        missing_memory_policy="use_best_available_context",
        project_memory_is_authoritative=False,
    )


def selected_items_have_active_project_memory(memory_pack: dict[str, Any] | None, project_id: str = "") -> bool:
    if not isinstance(memory_pack, dict):
        return False
    active = _clean(project_id, 120)
    for item in memory_pack.get("items") or []:
        if not isinstance(item, dict):
            continue
        meta = _safe_dict(item.get("metadata"))
        item_project = _clean(meta.get("memory_project_id") or meta.get("project_id"), 120)
        if item_project and (not active or item_project == active):
            return True
    return False


def build_authority_prompt_block(
    *,
    scope: dict[str, Any] | None = None,
    memory_pack: dict[str, Any] | None = None,
    query_text: str = "",
    requested_mode: str = "",
) -> str:
    scope = _safe_dict(scope)
    decision = resolve_authority_mode(scope=scope, query_text=query_text, requested_mode=requested_mode)
    project_title = _clean(scope.get("project_title"), 160) or "the active project"
    project_id = _clean(scope.get("project_id"), 120)
    has_project_memory = selected_items_have_active_project_memory(memory_pack, project_id)

    lines = [
        "Retrieval authority mode: " + decision.authority_mode,
        "Authority reason: " + decision.reason,
    ]

    if decision.authority_mode == "canon_strict":
        lines.extend([
            f"You are answering inside {project_title}.",
            "Treat active project canon, structured records, source canon, and retrieved project memory as authoritative.",
            "Do not start with or merge in real-world/general definitions for project terms unless the user explicitly asks for external comparison.",
            "For named lore terms, answer in-project first using available project memory. Use phrasing like 'In this project...' only when it improves clarity.",
            "If no project canon is retrieved for the asked term, say the project canon was not found instead of inventing or replacing it with real-world knowledge.",
            "Locked project terms override external meanings from games, fandoms, religions, philosophy, science, dictionaries, and generic mythology.",
        ])
        if has_project_memory:
            lines.append("Active project memory was retrieved; prefer it over pretrained/general knowledge.")
    elif decision.authority_mode == "evidence_strict":
        lines.extend([
            "Answer from retrieved/client/project evidence first.",
            "Do not infer missing client facts from general knowledge. If source evidence is missing, say what is missing and ask for the needed detail only when required.",
            "Locked source terms override generic industry assumptions unless the user asks for external advice or comparison.",
        ])
    elif decision.authority_mode == "real_world_strict":
        lines.extend([
            "Answer as global/general chat.",
            "Do not treat project-only memories as real-world truth. If project/story memory is disclosed, label it as project/story context.",
        ])
    elif decision.authority_mode == "hybrid_creative":
        lines.extend([
            "Creative blending is allowed, but keep source boundaries clear.",
            "When mixing project lore with real-world symbolism or inspiration, separate canon from external interpretation.",
        ])
    else:
        lines.append("Use the best available context, while respecting source scope and conflict priority.")

    grounding_block = build_grounding_prompt_block(
        authority_mode=decision.authority_mode,
        memory_pack=memory_pack,
        scope=scope,
        query_text=query_text,
    )
    if grounding_block:
        lines.append(grounding_block)

    return "\n".join(lines).strip()


def authority_metadata(scope: dict[str, Any] | None = None, query_text: str = "", requested_mode: str = "", memory_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = resolve_authority_mode(scope=scope, query_text=query_text, requested_mode=requested_mode).to_dict()
    decision["grounding"] = grounding_metadata(
        authority_mode=str(decision.get("authority_mode") or ""),
        memory_pack=memory_pack,
        scope=scope,
        query_text=query_text,
    )
    return decision
