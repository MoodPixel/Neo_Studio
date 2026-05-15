from __future__ import annotations

"""Global assistant chunk type normalization.

Phase 5 keeps upload ingestion from leaking file extensions or sample-specific
labels into retrieval limits. Chunk type should describe what the memory *is*,
not whether the source file was .txt/.md/.csv.
"""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ChunkTypeResult:
    chunk_type: str
    retrieval_family: str
    confidence: float
    reasons: list[str]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "chunk_type": self.chunk_type,
            "retrieval_family": self.retrieval_family,
            "chunk_type_confidence": round(float(self.confidence), 3),
            "chunk_type_reasons": "; ".join(self.reasons[:8]),
        }

    def to_report(self) -> dict[str, Any]:
        return asdict(self)


GENERIC_FILE_TYPES = {
    "txt", "text", "md", "markdown", "csv", "json", "json5", "yaml", "yml", "log", "document", "knowledge", "raw",
}

STRUCTURED_KIND_TO_CHUNK_TYPE = {
    # Creative/worldbuilding domains
    "world": "lore_record",
    "region": "lore_record",
    "kingdom": "lore_record",
    "kingdom_or_region": "lore_record",
    "city": "lore_record",
    "location": "lore_record",
    "character": "character_record",
    "creature": "creature_record",
    "faction": "organization_record",
    "organization": "organization_record",
    "ritual": "lore_rule",
    "law": "lore_rule",
    "event": "lore_event",
    "condition": "lore_condition",
    "bond": "lore_relationship",
    "myth": "lore_myth",
    "world_lore_concept": "lore_record",
    "lore_source_record": "lore_record",
    # Client/work domains
    "client": "client_profile",
    "client_brief": "client_brief",
    "brief": "client_brief",
    "scope": "scope_requirement",
    "pricing": "pricing_rule",
    "deliverable": "deliverable_spec",
    "revision": "scope_requirement",
    # Communication domains
    "email": "communication_thread",
    "message": "communication_thread",
    "chat": "communication_thread",
    "reply_template": "communication_template",
    # Project/system domains
    "project_doc": "project_documentation",
    "system_record": "project_documentation",
    "implementation_decision": "implementation_decision",
    "workflow_rule": "workflow_rule",
    "guardrail": "guardrail",
    # Technical/reference domains
    "code": "code_reference",
    "config": "config_reference",
    "log": "log_reference",
    "reference": "reference_material",
    "note": "note_record",
}

IMPORT_TYPE_TO_CHUNK_TYPE = {
    "json_schema": "structured_record",
    "markdown_structured": "structured_reference",
    "raw_creative_lore": "lore_record",
    "client_project_data": "client_brief",
    "email_or_message_data": "communication_thread",
    "project_docs": "project_documentation",
    "code_or_config": "code_reference",
    "conversation_notes": "note_record",
    "raw_reference_text": "reference_material",
}

DOMAIN_TO_CHUNK_TYPE = {
    "structured_data": "structured_record",
    "creative_lore": "lore_record",
    "client_work": "client_brief",
    "communication": "communication_thread",
    "project_system": "project_documentation",
    "technical": "code_reference",
    "notes": "note_record",
    "reference": "reference_material",
}

SECTION_ROLE_TO_CHUNK_TYPE = {
    "identity": "identity_record",
    "definition": "definition_record",
    "summary": "summary_record",
    "requirements": "scope_requirement",
    "deliverables": "deliverable_spec",
    "pricing": "pricing_rule",
    "timeline": "timeline_record",
    "client": "client_profile",
    "message": "communication_thread",
    "email": "communication_thread",
    "decision": "implementation_decision",
    "guardrail": "guardrail",
    "workflow": "workflow_rule",
    "code": "code_reference",
    "config": "config_reference",
    "log": "log_reference",
    "lore_rule": "lore_rule",
    "limitation": "lore_rule",
    "relationship": "lore_relationship",
    "event": "lore_event",
    "myth": "lore_myth",
}

# These are intentionally broader than import types. Retrieval budgets use this
# normalized vocabulary across assistant memory, client memory, project docs, and lore.
ASSISTANT_CHUNK_TYPE_WEIGHTS = {
    "canon_guard": 1.24,
    "identity_record": 1.18,
    "definition_record": 1.16,
    "structured_record": 1.18,
    "structured_reference": 1.08,
    "lore_record": 1.12,
    "character_record": 1.12,
    "creature_record": 1.10,
    "organization_record": 1.10,
    "lore_rule": 1.18,
    "lore_event": 1.10,
    "lore_condition": 1.12,
    "lore_relationship": 1.12,
    "lore_myth": 1.04,
    "client_brief": 1.18,
    "client_profile": 1.16,
    "scope_requirement": 1.18,
    "deliverable_spec": 1.16,
    "pricing_rule": 1.15,
    "timeline_record": 1.10,
    "communication_thread": 1.12,
    "communication_template": 1.10,
    "project_documentation": 1.12,
    "implementation_decision": 1.18,
    "workflow_rule": 1.14,
    "guardrail": 1.22,
    "code_reference": 1.06,
    "config_reference": 1.08,
    "log_reference": 1.02,
    "note_record": 1.03,
    "reference_material": 0.98,
    "summary_record": 0.82,
}

ASSISTANT_CHUNK_TYPE_LIMITS = {
    "canon_guard": 4,
    "identity_record": 3,
    "definition_record": 3,
    "structured_record": 5,
    "structured_reference": 5,
    "lore_record": 5,
    "character_record": 4,
    "creature_record": 4,
    "organization_record": 4,
    "lore_rule": 5,
    "lore_event": 4,
    "lore_condition": 4,
    "lore_relationship": 4,
    "lore_myth": 3,
    "client_brief": 5,
    "client_profile": 4,
    "scope_requirement": 5,
    "deliverable_spec": 5,
    "pricing_rule": 4,
    "timeline_record": 3,
    "communication_thread": 5,
    "communication_template": 4,
    "project_documentation": 5,
    "implementation_decision": 4,
    "workflow_rule": 4,
    "guardrail": 4,
    "code_reference": 4,
    "config_reference": 4,
    "log_reference": 3,
    "note_record": 4,
    "reference_material": 4,
    "summary_record": 2,
    # Guard against legacy/generic chunk types before migration.
    "text": 4,
    "txt": 4,
    "md": 4,
    "markdown": 4,
    "csv": 4,
    "json": 4,
    "yaml": 4,
    "yml": 4,
    "log": 3,
    "knowledge": 4,
}


def _clean(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _section_title_hint(title: str) -> str:
    clean = _clean(title)
    if not clean:
        return ""
    for needle, chunk_type in (
        ("identity", "identity_record"),
        ("definition", "definition_record"),
        ("summary", "summary_record"),
        ("requirement", "scope_requirement"),
        ("scope", "scope_requirement"),
        ("deliverable", "deliverable_spec"),
        ("pricing", "pricing_rule"),
        ("price", "pricing_rule"),
        ("timeline", "timeline_record"),
        ("deadline", "timeline_record"),
        ("relationship", "lore_relationship"),
        ("bond", "lore_relationship"),
        ("law", "lore_rule"),
        ("rule", "lore_rule"),
        ("limit", "lore_rule"),
        ("event", "lore_event"),
        ("myth", "lore_myth"),
        ("apocrypha", "lore_myth"),
        ("guardrail", "guardrail"),
        ("workflow", "workflow_rule"),
        ("decision", "implementation_decision"),
        ("code", "code_reference"),
        ("config", "config_reference"),
        ("log", "log_reference"),
    ):
        if needle in clean:
            return chunk_type
    return ""


def normalize_chunk_type(
    *,
    raw_chunk_type: Any = "",
    import_type: str = "",
    assistant_domain: str = "",
    document_kind: str = "",
    section_role: str = "",
    section_title: str = "",
    structured_record_kind: str = "",
    project_type: str = "general",
) -> ChunkTypeResult:
    """Return a stable global chunk type for storage/retrieval.

    Priority:
    1. Explicit canon guard/special project type.
    2. Structured record kind and section role.
    3. Non-generic document kind.
    4. Import type/domain fallback.
    5. Reference material, never limit=1 generic fallback.
    """

    reasons: list[str] = []
    raw = _clean(raw_chunk_type)
    imp = _clean(import_type)
    domain = _clean(assistant_domain)
    kind = _clean(document_kind)
    role = _clean(section_role)
    record_kind = _clean(structured_record_kind)
    title_hint = _section_title_hint(str(section_title or ""))

    if raw == "canon_guard":
        return ChunkTypeResult("canon_guard", "canon", 0.98, ["explicit_canon_guard"])

    if record_kind and record_kind in STRUCTURED_KIND_TO_CHUNK_TYPE:
        reasons.append(f"structured_record_kind:{record_kind}")
        return ChunkTypeResult(STRUCTURED_KIND_TO_CHUNK_TYPE[record_kind], "structured", 0.88, reasons)

    if role and role in SECTION_ROLE_TO_CHUNK_TYPE:
        reasons.append(f"section_role:{role}")
        return ChunkTypeResult(SECTION_ROLE_TO_CHUNK_TYPE[role], "section", 0.84, reasons)

    if title_hint:
        reasons.append(f"section_title_hint:{title_hint}")
        return ChunkTypeResult(title_hint, "section", 0.76, reasons)

    if kind and kind not in GENERIC_FILE_TYPES:
        if kind in STRUCTURED_KIND_TO_CHUNK_TYPE:
            reasons.append(f"document_kind:{kind}")
            return ChunkTypeResult(STRUCTURED_KIND_TO_CHUNK_TYPE[kind], "document_kind", 0.82, reasons)
        # Unknown but semantic document kind: keep stable by domain fallback below,
        # but preserve the reason for diagnostics.
        reasons.append(f"unmapped_document_kind:{kind}")

    if raw and raw not in GENERIC_FILE_TYPES and raw in ASSISTANT_CHUNK_TYPE_WEIGHTS:
        reasons.append(f"known_raw_chunk_type:{raw}")
        return ChunkTypeResult(raw, "raw_known", 0.80, reasons)

    if imp and imp in IMPORT_TYPE_TO_CHUNK_TYPE:
        reasons.append(f"import_type:{imp}")
        return ChunkTypeResult(IMPORT_TYPE_TO_CHUNK_TYPE[imp], "import_type", 0.72, reasons)

    if domain and domain in DOMAIN_TO_CHUNK_TYPE:
        reasons.append(f"assistant_domain:{domain}")
        return ChunkTypeResult(DOMAIN_TO_CHUNK_TYPE[domain], "domain", 0.66, reasons)

    if project_type == "universe":
        reasons.append("project_type:universe")
        return ChunkTypeResult("lore_record", "project_type", 0.58, reasons)

    reasons.append("fallback:reference_material")
    return ChunkTypeResult("reference_material", "fallback", 0.52, reasons)


def normalize_metadata_chunk_type(metadata: dict[str, Any]) -> dict[str, Any]:
    clean_meta = dict(metadata or {})
    result = normalize_chunk_type(
        raw_chunk_type=clean_meta.get("chunk_type") or "",
        import_type=clean_meta.get("import_type") or "",
        assistant_domain=clean_meta.get("assistant_domain") or "",
        document_kind=clean_meta.get("document_kind") or clean_meta.get("entity_type") or "",
        section_role=clean_meta.get("section_role") or "",
        section_title=clean_meta.get("section_title") or "",
        structured_record_kind=clean_meta.get("structured_record_kind") or "",
        project_type=clean_meta.get("project_type") or "general",
    )
    original = str(clean_meta.get("chunk_type") or "").strip()
    clean_meta.update(result.to_metadata())
    if original and original != result.chunk_type:
        clean_meta.setdefault("original_chunk_type", original)
    return clean_meta
