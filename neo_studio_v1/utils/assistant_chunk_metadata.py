from __future__ import annotations

"""Global assistant chunk metadata contract.

Phase 6 makes chunk metadata explicit and consistent across assistant memory:
worldbuilding, client briefs, email/message data, project docs, code/config,
notes, and generic references.

The key rule: every chunk must be traceable back to the preserved source and,
when available, to a structured record/entity. Retrieval should never have to
infer basic provenance from prose inside the document body.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .assistant_canon_priority import apply_priority_metadata
from .assistant_memory_sandbox import infer_memory_scope_for_import


CHUNK_METADATA_SCHEMA_VERSION = "assistant_chunk_metadata.v1"

CANON_RANK = {
    "primary_canon": 100,
    "active": 88,
    "secondary_canon": 78,
    "draft": 55,
    "speculative": 42,
    "deprecated": 18,
    "archived": 10,
}

DOMAIN_ANSWER_CONTEXT_ROLE = {
    "creative_lore": "canon_evidence",
    "client_work": "client_context",
    "communication": "communication_context",
    "project_system": "implementation_context",
    "technical": "technical_reference",
    "notes": "working_note",
    "reference": "reference_evidence",
    "structured_data": "structured_evidence",
}

IMPORTANT_SECTION_ROLES = {
    "identity",
    "definition",
    "summary",
    "requirements",
    "deliverables",
    "pricing",
    "timeline",
    "decision",
    "guardrail",
    "workflow",
    "lore_rule",
    "limitation",
    "relationship",
    "event",
    "myth",
    "client",
    "message",
    "email",
    "code",
    "config",
    "log",
}


@dataclass(frozen=True)
class ChunkMetadataReport:
    chunk_id: str
    metadata_schema_version: str
    metadata_quality_score: float
    provenance_complete: bool
    retrieval_tag_count: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_str(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, limit)]


def _slug(value: Any, fallback: str = "item") -> str:
    raw = _clean_str(value, 160).lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return raw[:90] or fallback


def _tokenize(value: Any) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_'-]{1,48}", str(value or "").lower())


def _unique(values: list[Any], limit: int = 30) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = _clean_str(value, 120)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _section_path(section: dict[str, Any], index: int) -> str:
    metadata = section.get("metadata") if isinstance(section.get("metadata"), dict) else {}
    explicit = metadata.get("field_path") or metadata.get("path") or metadata.get("source_path")
    if explicit:
        return _clean_str(explicit, 240)
    role = _clean_str(section.get("section_role") or "body", 80)
    title = _slug(section.get("title") or f"section_{index + 1}", "section")
    return f"{role}.{title}" if role else title


def _extract_aliases(parsed: dict[str, Any], section_record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for source in (section_record, parsed):
        if not isinstance(source, dict):
            continue
        for key in ("aliases", "labels", "names"):
            raw = source.get(key)
            if isinstance(raw, list):
                values.extend(raw)
            elif raw:
                values.append(raw)
    import_report = parsed.get("import_type_report") if isinstance(parsed.get("import_type_report"), dict) else {}
    raw_aliases = import_report.get("aliases")
    if isinstance(raw_aliases, list):
        values.extend(raw_aliases)
    return _unique(values, 24)


def _extract_entity_links(parsed: dict[str, Any], section_record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for entity in parsed.get("entities") or []:
        if isinstance(entity, dict):
            values.append(entity.get("id") or entity.get("label"))
        else:
            values.append(entity)
    for key in ("entity_id", "id", "label"):
        if section_record.get(key):
            values.append(section_record.get(key))
    return _unique(values, 40)


def _build_retrieval_tags(
    *,
    title: str,
    content: str,
    import_type: str,
    assistant_domain: str,
    document_kind: str,
    chunk_type: str,
    section_role: str,
    section_record: dict[str, Any],
    aliases: list[str],
    entity_links: list[str],
) -> list[str]:
    candidates: list[Any] = [
        import_type,
        assistant_domain,
        document_kind,
        chunk_type,
        section_role,
        title,
        section_record.get("kind"),
        section_record.get("label"),
    ]
    candidates.extend(aliases)
    candidates.extend(entity_links[:12])

    # Add a small set of meaningful content tokens. This is intentionally
    # conservative so tags stay useful, not noisy.
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "they", "them",
        "their", "where", "when", "what", "then", "than", "only", "also", "because",
        "have", "will", "would", "should", "could", "there", "which", "while", "about",
    }
    title_tokens = [t for t in _tokenize(title) if t not in stop]
    content_tokens = [t for t in _tokenize(content[:2400]) if t not in stop]
    candidates.extend(title_tokens[:12])
    candidates.extend(content_tokens[:18])
    return _unique(candidates, 48)


def _quality_score(metadata: dict[str, Any]) -> tuple[float, list[str]]:
    required = [
        "source_doc_id",
        "source_hash_sha256",
        "source_ref",
        "project_id",
        "import_type",
        "assistant_domain",
        "chunk_type",
        "section_title",
        "section_role",
        "canon_status",
    ]
    warnings: list[str] = []
    present = sum(1 for key in required if _clean_str(metadata.get(key), 200))
    score = present / max(1, len(required))
    if not metadata.get("structured_record_id"):
        warnings.append("missing_structured_record_link")
    if not metadata.get("source_snapshot_path"):
        warnings.append("missing_source_snapshot_path")
    if not metadata.get("retrieval_tags"):
        warnings.append("missing_retrieval_tags")
    return round(min(1.0, score), 3), warnings


def build_chunk_metadata(
    *,
    chunk_id: str,
    project_id: str,
    project: dict[str, Any],
    import_id: str,
    filename: str,
    suffix: str,
    source_ref: str,
    source_canon: dict[str, Any],
    parsed: dict[str, Any],
    section: dict[str, Any],
    section_index: int,
    section_count: int,
    title: str,
    content: str,
    canonical_status: str,
    visibility: str,
    raw_chunk_type: str,
    chunk_type_result: Any,
    section_record: dict[str, Any] | None,
    now: str,
) -> tuple[dict[str, Any], ChunkMetadataReport]:
    """Build stable, serializable chunk metadata for assistant memory."""

    section_record = section_record if isinstance(section_record, dict) else {}
    import_type = _clean_str(parsed.get("import_type") or "raw_reference_text", 120)
    assistant_domain = _clean_str(parsed.get("assistant_domain") or "reference", 120)
    chunking_strategy = _clean_str(parsed.get("chunking_strategy") or "paragraph_chunking", 140)
    section_role = _clean_str(section.get("section_role") or "body", 120)
    project_type = _clean_str(parsed.get("project_type") or "general", 100)
    document_kind = _clean_str(parsed.get("document_kind") or "knowledge", 120)
    chunk_type = _clean_str(getattr(chunk_type_result, "chunk_type", "") or "reference_material", 120)
    retrieval_family = _clean_str(getattr(chunk_type_result, "retrieval_family", "") or "fallback", 120)
    chunk_type_confidence = float(getattr(chunk_type_result, "confidence", 0.0) or 0.0)
    chunk_type_reasons = getattr(chunk_type_result, "reasons", []) or []

    aliases = _extract_aliases(parsed, section_record)
    entity_links = _extract_entity_links(parsed, section_record)
    retrieval_tags = _build_retrieval_tags(
        title=title,
        content=content,
        import_type=import_type,
        assistant_domain=assistant_domain,
        document_kind=document_kind,
        chunk_type=chunk_type,
        section_role=section_role,
        section_record=section_record,
        aliases=aliases,
        entity_links=entity_links,
    )

    canon_rank = CANON_RANK.get(_clean_str(canonical_status, 80).lower(), 50)
    has_structured_record = bool(section_record.get("id"))
    has_source_snapshot = bool(source_canon.get("snapshot_path") or source_canon.get("source_doc_id"))
    important_section = section_role.lower() in IMPORTANT_SECTION_ROLES or chunk_type in {
        "canon_guard", "definition_record", "scope_requirement", "pricing_rule", "guardrail", "lore_rule",
    }
    evidence_rank = canon_rank
    if has_structured_record:
        evidence_rank += 8
    if important_section:
        evidence_rank += 6
    if chunk_type == "summary_record":
        evidence_rank -= 15
    evidence_rank = max(0, min(120, evidence_rank))

    section_meta = section.get("metadata") if isinstance(section.get("metadata"), dict) else {}
    content_words = len(_tokenize(content))
    answer_context_role = DOMAIN_ANSWER_CONTEXT_ROLE.get(assistant_domain, "reference_evidence")
    sandbox_meta = infer_memory_scope_for_import(
        project_id=project_id,
        visibility=visibility,
        assistant_domain=assistant_domain,
        import_type=import_type,
    )

    metadata: dict[str, Any] = {
        "metadata_schema_version": CHUNK_METADATA_SCHEMA_VERSION,
        "lane": "assistant",
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "entity_type": "project_knowledge",
        "entity_id": import_id,
        "scope_type": "project" if sandbox_meta.get("memory_scope") == "project" else sandbox_meta.get("memory_scope") or "project",
        "scope_id": project_id if sandbox_meta.get("memory_scope") == "project" else sandbox_meta.get("memory_project_id") or project_id,
        "project_id": project_id,
        "memory_scope": sandbox_meta.get("memory_scope") or "project",
        "memory_project_id": sandbox_meta.get("memory_project_id") or project_id,
        "bleed_policy": sandbox_meta.get("bleed_policy") or "deny_global",
        "sandbox_policy": sandbox_meta.get("sandbox_policy") or "project_boxed",
        "project_title": _clean_str(project.get("title") or project_id, 180),
        "project_type": project_type,
        "source_ref": source_ref,
        "source_doc_id": source_canon.get("source_doc_id") or "",
        "source_hash_sha256": source_canon.get("source_hash_sha256") or "",
        "source_snapshot_path": source_canon.get("snapshot_path") or "",
        "source_preserved_as": source_canon.get("preserved_as") or "immutable_raw_upload",
        "source_filename": filename,
        "source_format": Path(filename or suffix).suffix.lower().lstrip(".") or str(suffix or "").lstrip("."),
        "source_anchor": f"{source_canon.get('source_doc_id') or import_id}#section-{section_index + 1}",
        "import_id": import_id,
        "import_type": import_type,
        "assistant_domain": assistant_domain,
        "chunking_strategy": chunking_strategy,
        "import_confidence": float(parsed.get("import_confidence") or 0),
        "document_kind": document_kind,
        "original_chunk_type": raw_chunk_type,
        "retrieval_family": retrieval_family,
        "chunk_type_confidence": chunk_type_confidence,
        "chunk_type_reasons": "; ".join(str(x) for x in chunk_type_reasons[:8]),
        "section_index": section_index,
        "section_number": section_index + 1,
        "section_count": section_count,
        "section_title": title,
        "section_role": section_role,
        "section_path": _section_path(section, section_index),
        "section_confidence": float(section.get("confidence") or 0),
        "section_metadata": section_meta,
        "content_char_count": len(content),
        "content_word_count": content_words,
        "structured_record_id": section_record.get("id") or "",
        "structured_record_kind": section_record.get("kind") or "",
        "structured_record_label": section_record.get("label") or "",
        "structured_record_confidence": float(section_record.get("confidence") or 0) if section_record.get("confidence") is not None else 0,
        "has_structured_record": has_structured_record,
        "entity_links": entity_links,
        "aliases": aliases,
        "retrieval_tags": retrieval_tags,
        "retrieval_query_hints": _unique([title, section_role, chunk_type, *aliases[:8], *entity_links[:8]], 24),
        "answer_context_role": answer_context_role,
        "canon_status": canonical_status,
        "canon_rank": canon_rank,
        "visibility": visibility,
        "evidence_rank": evidence_rank,
        "provenance_chain": [
            source_canon.get("source_doc_id") or "source_upload",
            import_id,
            section_record.get("id") or f"section_{section_index + 1}",
            chunk_id,
        ],
        "requires_source_citation": assistant_domain in {"creative_lore", "client_work", "project_system", "reference", "structured_data"},
        "source_disclosure_required": False,
        "source_disclosure_label": "",
        "source_context_policy": "normal_context",
        "is_summary_chunk": chunk_type == "summary_record" or section_role == "summary",
        "is_source_backed": has_source_snapshot,
        "importance": 0.88 if chunk_type == "canon_guard" else (0.76 if important_section else 0.68),
        "created_at": now,
        "updated_at": now,
    }

    quality, warnings = _quality_score(metadata)
    metadata["metadata_quality_score"] = quality
    metadata["metadata_warnings"] = warnings
    metadata = apply_priority_metadata(metadata)

    report = ChunkMetadataReport(
        chunk_id=chunk_id,
        metadata_schema_version=CHUNK_METADATA_SCHEMA_VERSION,
        metadata_quality_score=quality,
        provenance_complete=bool(metadata.get("source_doc_id") and metadata.get("source_hash_sha256") and metadata.get("source_ref")),
        retrieval_tag_count=len(retrieval_tags),
        warnings=warnings,
    )
    return metadata, report
