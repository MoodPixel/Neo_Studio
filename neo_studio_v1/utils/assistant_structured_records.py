from __future__ import annotations

"""Assistant structured-record builder.

Phase 3 introduced structured lore records; Phase 9 expands the same builder into
a global assistant record layer. It creates reviewable records for lore, client
briefs, communication threads, project docs, technical/code references, notes,
and general references without hardcoding sample content.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class StructuredRecord:
    id: str
    kind: str
    label: str
    assistant_domain: str
    import_type: str
    summary: str = ""
    aliases: list[str] = field(default_factory=list)
    canon_status: str = "draft"
    visibility: str = "project_private"
    tags: list[str] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)
    links: dict[str, Any] = field(default_factory=dict)
    source_section_indexes: list[int] = field(default_factory=list)
    confidence: float = 0.65
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = _safe_id(data.get("id") or data.get("label") or "record")
        data["label"] = _clean_inline(data.get("label") or data["id"], 200)
        data["summary"] = _clean_text(data.get("summary") or "", 1200)
        data["aliases"] = _dedupe([_clean_inline(x, 120) for x in data.get("aliases") or [] if _clean_inline(x)])[:30]
        data["tags"] = _dedupe([_safe_id(x, "tag") for x in data.get("tags") or [] if str(x or "").strip()])[:40]
        return data


LORE_KIND_BY_ROLE = {
    "identity": "concept",
    "rules": "law_or_rule",
    "abilities": "capability",
    "limitations": "limitation",
    "relationship": "bond_or_relationship",
    "history": "event_or_history",
    "misconception": "myth_or_misconception",
}

LORE_KEYWORD_KIND_PATTERNS: list[tuple[str, str]] = [
    (r"\bveil\b|\bbefore\b|\bafter\b|\bhistory\b|\bevent\b", "event_or_history"),
    (r"\blaw\b|\brule\b|\bmust\b|\bcannot\b|\bnever\b|\balways\b|\bforbidden\b", "law_or_rule"),
    (r"\bcondition\b|\bburden\b|\bcurse\b|\bsickness\b|\bcontaminant\b", "condition"),
    (r"\bbond\b|\bcounterpart\b|\blink\b|\brelationship\b|\bpair\b", "bond_or_relationship"),
    (r"\britual\b|\brite\b|\btoken\b|\bnotice\b|\bseal\b", "ritual_or_marker"),
    (r"\bmyth\b|\bapocrypha\b|\brumou?r\b|\blie\b|\bmisconception\b", "myth_or_misconception"),
    (r"\bfailure\b|\bcrack\b|\bshatter\b|\bcollapse\b|\boveruse\b", "failure_mode"),
    (r"\bability\b|\bpower\b|\bcan\b|\bmay\b|\bskill\b|\bcapability\b", "capability"),
]

ALIAS_MARKERS = ["also called", "named", "known as", "aliases", "some call", "some named", "title"]


def _clean_text(value: Any, limit: int = 20000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()[:max(100, limit)]


def _clean_inline(value: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max(20, limit)]


def _safe_id(value: Any, fallback: str = "record") -> str:
    text = _clean_inline(value, 180).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or fallback)[:120]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(value.strip())
    return out


def _first_sentence(text: str, limit: int = 360) -> str:
    clean = _clean_inline(text, 2000)
    if not clean:
        return ""
    match = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)
    return (match[0] or clean)[:limit].strip()


def _infer_doc_label(filename: str, sections: list[dict[str, Any]]) -> str:
    for section in sections[:3]:
        title = _clean_inline(section.get("title") or "", 160)
        if title and title.lower() not in {"document overview", "fact index", "chunk 1"}:
            return title.strip("#[] ")
    return Path(filename or "Imported lore").stem.replace("_", " ").replace("-", " ").strip() or "Imported lore"


def _extract_aliases(text: str, label: str) -> list[str]:
    aliases: list[str] = []
    if label:
        aliases.extend([part.strip() for part in re.split(r"\s*/\s*|\s+—\s+", label) if len(part.strip()) >= 2])
    # Key/value alias lines.
    for match in re.finditer(r"^\s*(?:aliases|also known as|known as):\s*(.+)$", text, flags=re.I | re.M):
        aliases.extend([part.strip(" .'\"“”") for part in re.split(r",|/|;|\bor\b", match.group(1)) if len(part.strip()) >= 2])
    # Prose alias phrases: "they are written as Catalysts ... named Omegas".
    for marker in ALIAS_MARKERS:
        if marker in text.lower():
            window_match = re.search(re.escape(marker) + r"(.{0,240})", text, flags=re.I | re.S)
            if window_match:
                window = window_match.group(1)
                aliases.extend(re.findall(r"\b[A-Z][A-Za-z][A-Za-z\- ]{1,42}\b", window))
    # Quoted/lore names in first paragraphs.
    head = "\n".join(text.splitlines()[:30])[:2500]
    for quoted in re.findall(r"[“\"]([^”\"]{3,48})[”\"]", head):
        # Quoted sayings are often not aliases; keep only compact title-like names.
        if len(quoted.split()) <= 4 and not re.search(r"\b(is|are|when|how|the|a|an)\b", quoted, flags=re.I):
            aliases.append(quoted)
    return _dedupe([a for a in aliases if len(a) <= 80 and not a.lower().startswith(("chapter", "section", "some call")) and not re.search(r"[.!?]", a)])


def _infer_lore_kind(section: dict[str, Any]) -> str:
    role = str(section.get("section_role") or "body").strip().lower()
    if role in LORE_KIND_BY_ROLE:
        return LORE_KIND_BY_ROLE[role]
    hay = f"{section.get('title') or ''}\n{section.get('content') or ''}".lower()
    for pattern, kind in LORE_KEYWORD_KIND_PATTERNS:
        if re.search(pattern, hay, flags=re.I):
            return kind
    return "lore_note"


def _section_record_label(section: dict[str, Any], root_label: str, idx: int) -> str:
    title = _clean_inline(section.get("title") or "", 120)
    if title and not title.lower().startswith("paragraph "):
        return title
    role = str(section.get("section_role") or "body").replace("_", " ").title()
    return f"{root_label} — {role or 'Section'} {idx + 1}"


def _field_bucket_for_kind(kind: str) -> str:
    if kind in {"law_or_rule", "ritual_or_marker"}:
        return "rules_and_protocols"
    if kind in {"capability", "limitation", "failure_mode", "condition"}:
        return "mechanics"
    if kind in {"bond_or_relationship"}:
        return "relationships"
    if kind in {"event_or_history"}:
        return "history"
    if kind in {"myth_or_misconception"}:
        return "misconceptions"
    return "notes"


DOMAIN_RECORD_CONFIG = {
    "creative_lore": {"root_kind": "lore_source_record", "section_prefix": "lore", "tag": "structured_lore"},
    "client_work": {"root_kind": "client_source_record", "section_prefix": "client", "tag": "structured_client_work"},
    "communication": {"root_kind": "communication_source_record", "section_prefix": "communication", "tag": "structured_communication"},
    "project_system": {"root_kind": "project_documentation_record", "section_prefix": "project_doc", "tag": "structured_project_doc"},
    "project_documentation": {"root_kind": "project_documentation_record", "section_prefix": "project_doc", "tag": "structured_project_doc"},
    "technical": {"root_kind": "technical_reference_record", "section_prefix": "technical", "tag": "structured_technical_reference"},
    "technical_reference": {"root_kind": "technical_reference_record", "section_prefix": "technical", "tag": "structured_technical_reference"},
    "notes": {"root_kind": "notes_source_record", "section_prefix": "notes", "tag": "structured_notes"},
    "reference": {"root_kind": "reference_source_record", "section_prefix": "reference", "tag": "structured_reference"},
}

GLOBAL_ROLE_KIND_BY_DOMAIN = {
    "client_work": {
        "identity": "client_profile", "summary": "client_brief_summary", "requirements": "client_requirement",
        "scope": "project_scope", "deliverables": "deliverable", "pricing": "pricing_note",
        "timeline": "timeline_note", "constraints": "client_constraint", "body": "client_note",
    },
    "communication": {
        "identity": "contact_or_thread", "summary": "communication_summary", "requirements": "message_requirement",
        "scope": "message_scope", "deliverables": "deliverable_note", "pricing": "pricing_note",
        "timeline": "timeline_note", "constraints": "communication_constraint", "body": "message_thread_note",
    },
    "project_system": {
        "identity": "project_doc_identity", "summary": "project_doc_summary", "requirements": "project_requirement",
        "scope": "project_scope", "rules": "project_rule", "implementation": "implementation_note",
        "timeline": "phase_or_timeline", "constraints": "project_constraint", "body": "project_doc_note",
    },
    "project_documentation": {
        "identity": "project_doc_identity", "summary": "project_doc_summary", "requirements": "project_requirement",
        "scope": "project_scope", "rules": "project_rule", "implementation": "implementation_note",
        "timeline": "phase_or_timeline", "constraints": "project_constraint", "body": "project_doc_note",
    },
    "technical": {
        "identity": "technical_reference_identity", "summary": "technical_summary", "requirements": "technical_requirement",
        "code": "code_or_config_reference", "errors": "error_or_log_note", "constraints": "technical_constraint",
        "body": "technical_note",
    },
    "technical_reference": {
        "identity": "technical_reference_identity", "summary": "technical_summary", "requirements": "technical_requirement",
        "code": "code_or_config_reference", "errors": "error_or_log_note", "constraints": "technical_constraint",
        "body": "technical_note",
    },
    "notes": {
        "identity": "notes_identity", "summary": "notes_summary", "requirements": "task_requirement",
        "timeline": "timeline_note", "constraints": "constraint_note", "body": "working_note",
    },
    "reference": {
        "identity": "reference_identity", "summary": "reference_summary", "requirements": "reference_requirement",
        "constraints": "reference_constraint", "body": "reference_note",
    },
}

def _domain_config(domain: str) -> dict[str, str]:
    return DOMAIN_RECORD_CONFIG.get(domain or "", DOMAIN_RECORD_CONFIG["reference"])

def _infer_global_kind(section: dict[str, Any], assistant_domain: str) -> str:
    if assistant_domain == "creative_lore":
        return _infer_lore_kind(section)
    role = str(section.get("section_role") or "body").strip().lower()
    mapping = GLOBAL_ROLE_KIND_BY_DOMAIN.get(assistant_domain or "", GLOBAL_ROLE_KIND_BY_DOMAIN["reference"])
    if role in mapping:
        return mapping[role]
    hay = f"{section.get('title') or ''}\n{section.get('content') or ''}".lower()
    if any(x in hay for x in ["price", "budget", "quote", "cost", "$"]):
        return "pricing_note"
    if any(x in hay for x in ["deadline", "turnaround", "timeline", "delivery", "due"]):
        return "timeline_note"
    if any(x in hay for x in ["deliverable", "video", "edit", "asset", "output"]):
        return "deliverable_note"
    if any(x in hay for x in ["must", "required", "requirement", "need", "scope"]):
        return "requirement_note"
    if any(x in hay for x in ["error", "traceback", "exception", "failed", "warning"]):
        return "error_or_log_note"
    return mapping.get("body", "reference_note")

def _field_bucket_for_global_kind(kind: str, assistant_domain: str) -> str:
    if assistant_domain == "creative_lore":
        return _field_bucket_for_kind(kind)
    if "pricing" in kind:
        return "pricing"
    if "timeline" in kind or "phase" in kind:
        return "timeline"
    if "deliverable" in kind:
        return "deliverables"
    if "requirement" in kind or "constraint" in kind or "scope" in kind:
        return "requirements_and_scope"
    if "error" in kind or "code" in kind or "technical" in kind:
        return "technical_details"
    if "communication" in kind or "message" in kind or "thread" in kind:
        return "conversation"
    return "notes"




STOP_LORE_PHRASES = {
    "Chapter", "Some", "The", "After", "Before", "Because", "Where", "This", "These",
    "What", "And", "But", "So", "There", "Many", "Rarely", "Apocrypha",
}


def _sentences(text: str) -> list[str]:
    clean = _clean_inline(text, 500_000)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if len(s.strip()) >= 30]


def _extract_candidate_lore_terms(text: str, aliases: list[str]) -> list[str]:
    terms: list[str] = []
    terms.extend(aliases)
    # Multiword title-case terms, including hyphen compounds.
    for match in re.finditer(r"\b([A-Z][A-Za-z]+(?:[- ][A-Z][A-Za-z]+){0,4})\b", text):
        phrase = _clean_inline(match.group(1), 90).strip(" ,.;:()[]{}“”\"")
        if not phrase or phrase in STOP_LORE_PHRASES:
            continue
        if re.search(r"[.!?]", phrase) or phrase.lower().startswith(("some call", "chapter ")):
            continue
        if len(phrase) < 4 or len(phrase.split()) > 5:
            continue
        # Keep lore-ish names; avoid every sentence-start noun by requiring nearby signal or multiword/hyphen.
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 120)
        window = text[start:end].lower()
        signal = any(word in window for word in ["called", "named", "known", "record", "law", "rite", "notice", "token", "veil", "bond", "burden", "shard", "alpha", "omega", "order", "pillar", "myth"])
        if signal or "-" in phrase or len(phrase.split()) >= 2:
            terms.append(phrase)
    # Explicit key-value style names.
    for match in re.finditer(r"\b(?:the|a|an)\s+([A-Z][A-Za-z]+(?:[- ][A-Z][A-Za-z]+){1,4})\b", text):
        terms.append(_clean_inline(match.group(1), 90))
    cleaned_terms: list[str] = []
    for term in terms:
        term = _clean_inline(term, 90).strip(" ,.;:()[]{}“”\"")
        if not term or term in STOP_LORE_PHRASES:
            continue
        if re.search(r"[.!?]", term) or term.lower().startswith(("some call", "chapter ")):
            continue
        if len(term.split()) > 5:
            continue
        cleaned_terms.append(term)
    return _dedupe(cleaned_terms)[:80]


def _context_for_term(text: str, term: str, max_sentences: int = 3) -> str:
    selected: list[str] = []
    lower_term = term.lower()
    for sentence in _sentences(text):
        if lower_term in sentence.lower():
            selected.append(sentence)
            if len(selected) >= max_sentences:
                break
    return _clean_text(" ".join(selected), 1600)


def _kind_for_named_lore_record(term: str, context: str) -> str:
    pseudo_section = {"title": term, "content": context, "section_role": "body"}
    return _infer_lore_kind(pseudo_section)


def build_structured_records_from_import(*, parsed: dict[str, Any], import_id: str = "", source_ref: str = "", canon_status: str = "draft", visibility: str = "project_private") -> dict[str, Any]:
    """Build structured records from parsed import data.

    This is global by design. Creative lore receives richer named-term mining;
    other Assistant domains receive source + section records that preserve
    scope, client/project/message details, requirements, and evidence links.
    """
    import_type = str(parsed.get("import_type") or "").strip()
    assistant_domain = str(parsed.get("assistant_domain") or "reference").strip() or "reference"
    filename = str(parsed.get("filename") or "").strip()
    sections = [s for s in (parsed.get("sections") or []) if isinstance(s, dict)]
    raw_text = _clean_text(parsed.get("text") or "", 500_000)
    source_canon = parsed.get("source_canon") if isinstance(parsed.get("source_canon"), dict) else {}
    if not sections:
        return {"ok": True, "record_count": 0, "records": [], "domain": assistant_domain, "reason": "no_sections"}

    config = _domain_config(assistant_domain)
    root_label = _infer_doc_label(filename, sections)
    root_prefix = config["section_prefix"]
    root_id = f"{root_prefix}_{_safe_id(root_label, 'source')}"
    aliases = _extract_aliases(raw_text, root_label) if assistant_domain == "creative_lore" else _extract_aliases(raw_text[:5000], root_label)
    summary = ""
    for section in sections:
        if str(section.get("section_role") or "").lower() in {"identity", "summary", "body", "requirements", "scope"}:
            summary = _first_sentence(section.get("content") or "")
            if summary:
                break
    if not summary:
        summary = _first_sentence(raw_text)

    records: list[StructuredRecord] = []
    root_fields: dict[str, Any] = {
        "identity": {
            "source_label": root_label,
            "aliases": aliases,
            "source_filename": filename,
            "assistant_domain": assistant_domain,
            "import_type": import_type,
        },
        "summary": summary,
        "section_index": [
            {
                "section_index": idx,
                "title": _clean_inline(section.get("title") or f"Section {idx + 1}", 140),
                "section_role": section.get("section_role") or "body",
            }
            for idx, section in enumerate(sections[:100])
        ],
    }
    root = StructuredRecord(
        id=root_id,
        kind=config["root_kind"],
        label=root_label,
        assistant_domain=assistant_domain,
        import_type=import_type or "raw_reference_text",
        summary=summary,
        aliases=aliases,
        canon_status=canon_status,
        visibility=visibility,
        tags=[config["tag"], "source_record", assistant_domain],
        fields=root_fields,
        links={"source_ref": source_ref, "source_doc_id": source_canon.get("source_doc_id") or "", "derived_record_ids": []},
        source_section_indexes=list(range(len(sections))),
        confidence=0.72,
        metadata={"builder": "assistant_structured_records.phase9_global", "import_id": import_id, "source_canon": source_canon},
    )
    records.append(root)

    for idx, section in enumerate(sections):
        content = _clean_text(section.get("content") or "", 12000)
        if len(content) < 40:
            continue
        kind = _infer_global_kind(section, assistant_domain)
        label = _section_record_label(section, root_label, idx)
        record_id = f"{_safe_id(kind)}_{_safe_id(label, 'section')}"
        bucket = _field_bucket_for_global_kind(kind, assistant_domain)
        section_aliases = _extract_aliases(content[:2500], label) if assistant_domain == "creative_lore" else []
        record = StructuredRecord(
            id=record_id,
            kind=kind,
            label=label,
            assistant_domain=assistant_domain,
            import_type=import_type or "raw_reference_text",
            summary=_first_sentence(content, 420),
            aliases=section_aliases,
            canon_status=canon_status,
            visibility=visibility,
            tags=[config["tag"], bucket, str(section.get("section_role") or "body")],
            fields={
                bucket: content,
                "section": {
                    "title": section.get("title") or label,
                    "role": section.get("section_role") or "body",
                    "confidence": section.get("confidence") or 0,
                    "metadata": section.get("metadata") if isinstance(section.get("metadata"), dict) else {},
                },
            },
            links={"source_ref": source_ref, "source_doc_id": source_canon.get("source_doc_id") or "", "parent_record_id": root_id},
            source_section_indexes=[idx],
            confidence=float(section.get("confidence") or 0.6),
            metadata={"builder": "assistant_structured_records.phase9_global", "import_id": import_id, "source_canon": source_canon},
        )
        records.append(record)
        root.links.setdefault("derived_record_ids", []).append(record.id)

    if assistant_domain == "creative_lore":
        existing_labels = {str(rec.label).lower() for rec in records}
        for term in _extract_candidate_lore_terms(raw_text, aliases):
            if term.lower() in existing_labels:
                continue
            context = _context_for_term(raw_text, term)
            if len(context) < 80:
                continue
            kind = _kind_for_named_lore_record(term, context)
            bucket = _field_bucket_for_kind(kind)
            records.append(StructuredRecord(
                id=f"{_safe_id(kind)}_{_safe_id(term, 'term')}",
                kind=kind,
                label=term,
                assistant_domain=assistant_domain,
                import_type=import_type or "raw_creative_lore",
                summary=_first_sentence(context, 420),
                aliases=_extract_aliases(context, term),
                canon_status=canon_status,
                visibility=visibility,
                tags=[config["tag"], bucket, "named_lore_term"],
                fields={bucket: context, "term": {"name": term, "extraction": "named_lore_term"}},
                links={"source_ref": source_ref, "source_doc_id": source_canon.get("source_doc_id") or "", "parent_record_id": root_id},
                source_section_indexes=[],
                confidence=0.58,
                metadata={"builder": "assistant_structured_records.phase9_global", "import_id": import_id, "source_canon": source_canon, "extraction": "named_lore_term"},
            ))

    merged: dict[str, StructuredRecord] = {}
    for rec in records:
        key = _safe_id(rec.id)
        if key in merged:
            old = merged[key]
            old.source_section_indexes = sorted(set(old.source_section_indexes + rec.source_section_indexes))
            if rec.summary and not old.summary:
                old.summary = rec.summary
            old.aliases = _dedupe(old.aliases + rec.aliases)
            old.tags = _dedupe(old.tags + rec.tags)
            continue
        rec.id = key
        merged[key] = rec
    out = [rec.to_dict() for rec in merged.values()]
    return {
        "ok": True,
        "record_count": len(out),
        "records": out,
        "domain": assistant_domain,
        "root_record_id": _safe_id(root_id),
        "builder_version": "phase9_global_raw_text_to_records_v1",
    }

