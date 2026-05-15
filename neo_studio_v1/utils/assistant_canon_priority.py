from __future__ import annotations

"""Global assistant evidence/canon priority rules.

Phase 7 is intentionally broader than worldbuilding canon.  It ranks uploaded
assistant memory by source authority so answers prefer the most reliable record
for the active domain: lore canon, client briefs, communication threads,
project system docs, code/config/logs, notes, and reference material.
"""

from dataclasses import asdict, dataclass
from typing import Any


PRIORITY_SCHEMA_VERSION = "assistant_canon_priority.v1"

CANON_STATUS_RANK = {
    "primary_canon": 100,
    "active": 90,
    "approved": 88,
    "confirmed": 86,
    "secondary_canon": 78,
    "working": 64,
    "draft": 52,
    "speculative": 40,
    "unverified": 32,
    "deprecated": 12,
    "archived": 8,
    "rejected": 0,
}

DOMAIN_TIER_RANKS: dict[str, dict[str, int]] = {
    "creative_lore": {
        "canon_record": 100,
        "structured_lore_record": 92,
        "source_canon": 88,
        "structured_summary": 76,
        "draft_lore": 52,
        "working_note": 38,
        "raw_reference": 34,
        "unknown": 30,
    },
    "client_work": {
        "client_direct_brief": 100,
        "active_scope_or_offer": 94,
        "client_message": 90,
        "project_requirement": 84,
        "pricing_rule": 82,
        "delivery_note": 74,
        "user_note": 66,
        "derived_summary": 54,
        "raw_reference": 38,
        "unknown": 30,
    },
    "communication": {
        "received_message": 96,
        "sent_message": 92,
        "active_draft": 78,
        "message_template": 62,
        "conversation_note": 54,
        "derived_summary": 46,
        "unknown": 30,
    },
    "project_system": {
        "mandatory_protocol": 100,
        "validation_checklist": 96,
        "workflow_registry": 92,
        "implementation_record": 86,
        "source_code": 82,
        "project_documentation": 78,
        "working_note": 54,
        "derived_summary": 44,
        "unknown": 30,
    },
    "technical": {
        "source_code": 96,
        "config_file": 92,
        "error_log": 86,
        "implementation_record": 80,
        "technical_reference": 72,
        "derived_summary": 44,
        "unknown": 30,
    },
    "notes": {
        "decision_note": 78,
        "working_note": 62,
        "conversation_note": 58,
        "derived_summary": 42,
        "unknown": 30,
    },
    "reference": {
        "source_reference": 76,
        "raw_reference": 62,
        "derived_summary": 42,
        "unknown": 30,
    },
    "structured_data": {
        "structured_schema": 96,
        "structured_record": 90,
        "source_reference": 68,
        "unknown": 30,
    },
}

# Domains where lower-priority chunks should generally not override higher ones.
STRICT_CONFLICT_DOMAINS = {"creative_lore", "client_work", "project_system", "technical", "structured_data"}


@dataclass(frozen=True)
class PriorityDecision:
    priority_schema_version: str
    evidence_tier: str
    evidence_tier_rank: int
    canon_status_rank: int
    source_authority_rank: int
    truth_priority_rank: int
    conflict_policy: str
    freshness_policy: str
    can_override_lower_priority: bool
    requires_source_check_for_conflict: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 160) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, limit)]


def _lower(value: Any) -> str:
    return _clean(value, 200).lower()


def _section_text(metadata: dict[str, Any]) -> str:
    return " ".join(
        _lower(metadata.get(key))
        for key in (
            "section_title",
            "section_role",
            "section_path",
            "structured_record_kind",
            "structured_record_label",
            "chunk_type",
            "document_kind",
            "source_filename",
            "source_ref",
        )
    )


def _infer_evidence_tier(metadata: dict[str, Any]) -> tuple[str, list[str]]:
    domain = _lower(metadata.get("assistant_domain") or "reference") or "reference"
    import_type = _lower(metadata.get("import_type"))
    chunk_type = _lower(metadata.get("chunk_type"))
    section_role = _lower(metadata.get("section_role"))
    canon_status = _lower(metadata.get("canon_status"))
    text = _section_text(metadata)
    has_structured = bool(metadata.get("structured_record_id") or metadata.get("has_structured_record"))
    reasons: list[str] = []

    if canon_status in {"deprecated", "archived", "rejected"}:
        reasons.append(f"canon_status:{canon_status}")
        return "working_note" if domain != "creative_lore" else "draft_lore", reasons

    if domain == "creative_lore":
        if chunk_type in {"canon_guard", "lore_rule", "definition_record"} or canon_status == "primary_canon":
            reasons.append("creative_lore:canon_rule_or_primary")
            return "canon_record", reasons
        if has_structured:
            reasons.append("creative_lore:structured_record")
            return "structured_lore_record", reasons
        if metadata.get("is_source_backed") or metadata.get("source_doc_id"):
            reasons.append("creative_lore:source_backed")
            return "source_canon", reasons
        if canon_status in {"draft", "speculative"}:
            reasons.append(f"creative_lore:{canon_status}")
            return "draft_lore", reasons
        return "raw_reference", reasons

    if domain == "client_work":
        if "client" in text and any(s in text for s in ("brief", "message", "requirement", "scope")):
            reasons.append("client_work:client_direct_context")
            return "client_direct_brief", reasons
        if section_role in {"pricing", "timeline", "deliverables", "requirements"} or chunk_type in {"pricing_rule", "scope_requirement"}:
            reasons.append("client_work:scope_pricing_delivery")
            return "active_scope_or_offer", reasons
        if "message" in text or "email" in text:
            reasons.append("client_work:message")
            return "client_message", reasons
        if has_structured:
            reasons.append("client_work:structured_requirement")
            return "project_requirement", reasons
        return "user_note" if import_type == "conversation_notes" else "derived_summary", reasons

    if domain == "communication":
        if any(s in text for s in ("received", "incoming", "client message", "from:")):
            reasons.append("communication:received")
            return "received_message", reasons
        if any(s in text for s in ("sent", "outgoing", "reply", "to:")):
            reasons.append("communication:sent")
            return "sent_message", reasons
        if "draft" in text:
            reasons.append("communication:draft")
            return "active_draft", reasons
        if "template" in text:
            reasons.append("communication:template")
            return "message_template", reasons
        return "conversation_note", reasons

    if domain == "project_system":
        if any(s in text for s in ("mandatory_protocol", "mandatory protocol", "ai_mandatory")):
            reasons.append("project_system:mandatory_protocol")
            return "mandatory_protocol", reasons
        if "validation" in text and "checklist" in text:
            reasons.append("project_system:validation_checklist")
            return "validation_checklist", reasons
        if "workflow" in text and "registry" in text:
            reasons.append("project_system:workflow_registry")
            return "workflow_registry", reasons
        if "phase" in text or "implementation" in text:
            reasons.append("project_system:implementation_record")
            return "implementation_record", reasons
        if chunk_type in {"code_reference", "config_reference"} or import_type == "code_or_config":
            reasons.append("project_system:source_code_or_config")
            return "source_code", reasons
        return "project_documentation", reasons

    if domain == "technical":
        if chunk_type == "code_reference" or import_type == "code_or_config":
            reasons.append("technical:source_code_or_config")
            return "source_code", reasons
        if "config" in text or section_role == "config":
            reasons.append("technical:config")
            return "config_file", reasons
        if "log" in text or section_role == "log":
            reasons.append("technical:log")
            return "error_log", reasons
        return "technical_reference", reasons

    if domain == "structured_data" or import_type == "json_schema":
        if import_type == "json_schema":
            reasons.append("structured_data:json_schema")
            return "structured_schema", reasons
        if has_structured:
            reasons.append("structured_data:structured_record")
            return "structured_record", reasons
        return "source_reference", reasons

    if domain == "notes":
        if section_role == "decision" or "decision" in text:
            reasons.append("notes:decision")
            return "decision_note", reasons
        if "conversation" in import_type or "conversation" in text:
            reasons.append("notes:conversation")
            return "conversation_note", reasons
        return "working_note", reasons

    if metadata.get("is_summary_chunk"):
        reasons.append("fallback:summary")
        return "derived_summary", reasons
    if metadata.get("is_source_backed"):
        reasons.append("fallback:source_backed")
        return "source_reference", reasons
    return "unknown", reasons


def build_priority_decision(metadata: dict[str, Any]) -> PriorityDecision:
    metadata = metadata if isinstance(metadata, dict) else {}
    domain = _lower(metadata.get("assistant_domain") or "reference") or "reference"
    tier, reasons = _infer_evidence_tier(metadata)
    tier_rank = DOMAIN_TIER_RANKS.get(domain, DOMAIN_TIER_RANKS["reference"]).get(tier, 30)
    canon_status = _lower(metadata.get("canon_status") or "unverified") or "unverified"
    canon_rank = CANON_STATUS_RANK.get(canon_status, 32)

    source_authority_rank = 0
    if metadata.get("source_doc_id") and metadata.get("source_hash_sha256"):
        source_authority_rank += 10
        reasons.append("source:preserved_hash")
    if metadata.get("structured_record_id"):
        source_authority_rank += 8
        reasons.append("source:structured_record")
    if metadata.get("metadata_quality_score"):
        try:
            source_authority_rank += int(float(metadata.get("metadata_quality_score") or 0) * 6)
        except Exception:
            pass

    if bool(metadata.get("is_summary_chunk")):
        source_authority_rank -= 8
        reasons.append("source:summary_penalty")
    if canon_status in {"deprecated", "archived", "rejected"}:
        source_authority_rank -= 20
        reasons.append("source:inactive_penalty")

    truth_priority_rank = max(0, min(120, int((tier_rank * 0.60) + (canon_rank * 0.25) + source_authority_rank)))
    strict = domain in STRICT_CONFLICT_DOMAINS
    conflict_policy = "prefer_highest_priority_source" if strict else "prefer_highest_priority_but_allow_context"
    freshness_policy = "stable_canon_over_recency" if domain in {"creative_lore", "project_system", "structured_data"} else "recent_active_context_can_win"

    return PriorityDecision(
        priority_schema_version=PRIORITY_SCHEMA_VERSION,
        evidence_tier=tier,
        evidence_tier_rank=int(tier_rank),
        canon_status_rank=int(canon_rank),
        source_authority_rank=int(source_authority_rank),
        truth_priority_rank=int(truth_priority_rank),
        conflict_policy=conflict_policy,
        freshness_policy=freshness_policy,
        can_override_lower_priority=truth_priority_rank >= 70,
        requires_source_check_for_conflict=strict,
        reasons=reasons[:12],
    )


def apply_priority_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return metadata enriched with global answer/evidence priority fields."""

    metadata = dict(metadata or {})
    decision = build_priority_decision(metadata).to_dict()
    metadata.update(decision)
    # Keep Phase 6 evidence_rank compatible, but let global truth rank become the
    # retrieval-facing signal.  Do not lower an existing strong evidence_rank.
    try:
        existing = int(float(metadata.get("evidence_rank") or 0))
    except Exception:
        existing = 0
    metadata["evidence_rank"] = max(existing, int(decision["truth_priority_rank"]))
    metadata["answer_priority_label"] = f"{metadata.get('assistant_domain') or 'reference'}:{decision['evidence_tier']}"
    return metadata


def priority_bonus(metadata: dict[str, Any]) -> float:
    """Small retrieval bonus from the global truth priority rank."""

    try:
        rank = float((metadata or {}).get("truth_priority_rank") or 0)
    except Exception:
        rank = 0.0
    return min(0.14, max(0.0, rank / 120.0 * 0.14))
