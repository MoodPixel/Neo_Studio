from __future__ import annotations

"""Global assistant import classification.

This module is intentionally domain-wide. It does not assume imports are only
worldbuilding/lore. The assistant memory layer can receive client briefs,
email/chat drafts, project documentation, code/config, research/reference text,
creative lore, and general notes. Phase 1 only classifies the import and exposes
routing metadata; later phases can plug specialized parsers into the strategies.
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImportTypeResult:
    import_type: str
    assistant_domain: str
    chunking_strategy: str
    confidence: float
    reasons: list[str]
    warnings: list[str]
    parsed_json: Any | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "import_type": self.import_type,
            "assistant_domain": self.assistant_domain,
            "chunking_strategy": self.chunking_strategy,
            "import_confidence": round(float(self.confidence), 3),
            "import_reasons": "; ".join(self.reasons[:8]),
            "import_warnings": "; ".join(self.warnings[:8]),
        }

    def to_report(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("parsed_json", None)
        return data


IMPORT_TYPES = {
    "json_schema",             # structured records / exported assistant data
    "markdown_structured",     # headings with stable sections
    "raw_creative_lore",       # prose lore/worldbuilding/story bible text
    "client_project_data",     # briefs, pricing, deliverables, client context
    "email_or_message_data",   # emails, chat logs, reply templates, message threads
    "project_docs",            # Neo docs, specs, implementation records
    "code_or_config",          # code/config/logs that should not be lore-parsed
    "conversation_notes",      # meeting/chat notes, phase notes, todo notes
    "raw_reference_text",      # articles, copied docs, general reference
}

ASSISTANT_DOMAINS = {
    "structured_data",
    "creative_lore",
    "client_work",
    "communication",
    "project_system",
    "technical",
    "notes",
    "reference",
}

CHUNKING_STRATEGY_BY_IMPORT_TYPE = {
    "json_schema": "field_path_chunking",
    "markdown_structured": "heading_section_chunking",
    "raw_creative_lore": "semantic_section_chunking",
    "client_project_data": "brief_section_chunking",
    "email_or_message_data": "message_thread_chunking",
    "project_docs": "heading_section_chunking",
    "code_or_config": "code_block_chunking",
    "conversation_notes": "topic_note_chunking",
    "raw_reference_text": "paragraph_chunking",
}

DOMAIN_BY_IMPORT_TYPE = {
    "json_schema": "structured_data",
    "markdown_structured": "reference",
    "raw_creative_lore": "creative_lore",
    "client_project_data": "client_work",
    "email_or_message_data": "communication",
    "project_docs": "project_system",
    "code_or_config": "technical",
    "conversation_notes": "notes",
    "raw_reference_text": "reference",
}

# Retrieval multipliers are deliberately modest. Canon/status/scope should still
# matter more than a guessed import classifier.
RETRIEVAL_WEIGHT_BY_IMPORT_TYPE = {
    "json_schema": 1.18,
    "markdown_structured": 1.08,
    "raw_creative_lore": 1.05,
    "client_project_data": 1.14,
    "email_or_message_data": 1.12,
    "project_docs": 1.12,
    "code_or_config": 1.04,
    "conversation_notes": 1.03,
    "raw_reference_text": 0.96,
}

RETRIEVAL_LIMIT_BY_IMPORT_TYPE = {
    "json_schema": 5,
    "markdown_structured": 5,
    "raw_creative_lore": 5,
    "client_project_data": 5,
    "email_or_message_data": 4,
    "project_docs": 5,
    "code_or_config": 4,
    "conversation_notes": 4,
    "raw_reference_text": 3,
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".json", ".json5", ".yaml", ".yml", ".toml", ".ini", ".env", ".bat",
    ".ps1", ".sh", ".sql", ".xml", ".csv", ".log",
}


def _clean_text(text: Any, limit: int = 500_000) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return value.strip()[:limit]


def try_parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _count_matches(text: str, patterns: list[str]) -> int:
    lower = text.lower()
    return sum(1 for pattern in patterns if pattern.lower() in lower)


def _has_key_value_density(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    kv = sum(1 for line in lines[:120] if re.match(r"^[A-Za-z][A-Za-z0-9 _/().-]{1,48}:\s*\S+", line))
    return kv >= 4 and kv / max(1, min(len(lines), 120)) >= 0.12


def looks_like_markdown_structured(text: str) -> bool:
    lines = text.splitlines()
    heading_count = sum(1 for line in lines if re.match(r"^#{1,6}\s+\S+", line.strip()))
    bullet_count = sum(1 for line in lines if re.match(r"^\s*[-*+]\s+\S+", line))
    return heading_count >= 2 or (heading_count >= 1 and bullet_count >= 3)


def looks_like_project_docs(filename: str, text: str) -> bool:
    lower_name = filename.lower()
    lower_text = text.lower()
    name_signals = [
        "neo_system_records", "ai_mandatory_protocol", "validation_checklist",
        "workflow_registry", "feature_implementation_template", "dynamic_workflow_validator",
        "assistant_backend_map", "assistant_memory_map", "change_execution_log",
    ]
    text_signals = [
        "mandatory protocol", "validation checklist", "workflow registry", "implementation phase",
        "system record", "backend map", "ui map", "workflow matrix", "change execution log",
    ]
    return any(signal in lower_name for signal in name_signals) or _count_matches(lower_text, text_signals) >= 2


def looks_like_client_project_data(text: str) -> bool:
    signals = [
        "client", "brief", "scope of work", "deliverable", "delivery", "timeline", "budget",
        "pricing", "revision", "portfolio", "platform", "tiktok", "instagram", "youtube",
        "fiverr", "upwork", "fixed price", "hourly", "turnaround", "brand", "assets",
    ]
    return _count_matches(text, signals) >= 4 or bool(re.search(r"\$\s?\d+|\b\d+\s?(clips|videos|reels|shorts)\b", text, re.I))


def looks_like_email_or_message_data(text: str) -> bool:
    header_signals = ["from:", "to:", "subject:", "cc:", "bcc:", "sent:", "received:"]
    body_signals = ["dear ", "hello ", "hi ", "thanks,", "regards,", "best,", "message:", "profile image"]
    header_score = _count_matches(text, header_signals)
    body_score = _count_matches(text, body_signals)
    # Chat exports usually alternate human names/usernames, not generic planning labels.
    speaker_lines = 0
    for match in re.finditer(r"^\s*([A-Za-z][A-Za-z0-9_. @-]{1,38}):\s+\S+", text, flags=re.M):
        name = match.group(1).strip().lower()
        if name not in {"todo", "phase", "decision", "notes", "summary", "next step", "action items"}:
            speaker_lines += 1
    return header_score >= 2 or (header_score >= 1 and body_score >= 1) or speaker_lines >= 3


def looks_like_raw_creative_lore(text: str, project_type: str = "") -> bool:
    signals = [
        "chapter ", "canon", "lore", "world", "realm", "kingdom", "region", "city",
        "character", "creature", "faction", "order", "ritual", "myth", "apocrypha",
        "bloodline", "magic", "pillar", "veil", "shard", "bond", "prophecy",
    ]
    long_paragraphs = [p for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 350]
    score = _count_matches(text, signals)
    return (project_type == "universe" and score >= 2) or (score >= 4 and len(long_paragraphs) >= 1)


def looks_like_conversation_notes(text: str) -> bool:
    signals = ["todo", "next step", "phase ", "decision:", "notes:", "summary:", "action items", "follow up"]
    speaker_lines = len(re.findall(r"^\s*(user|assistant|me|client|bro):\s+", text, flags=re.I | re.M))
    return _count_matches(text, signals) >= 2 or speaker_lines >= 2


def detect_import_type(filename: str, text: str, *, project_type: str = "general", parsed_json: Any | None = None) -> ImportTypeResult:
    clean_filename = str(filename or "")
    suffix = Path(clean_filename).suffix.lower()
    body = _clean_text(text)
    reasons: list[str] = []
    warnings: list[str] = []
    parsed = parsed_json if parsed_json is not None else try_parse_json(body)

    if parsed is not None:
        reasons.append("valid_json")
        return ImportTypeResult("json_schema", DOMAIN_BY_IMPORT_TYPE["json_schema"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["json_schema"], 0.98, reasons, warnings, parsed)

    if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".yaml", ".yml", ".toml", ".ini", ".env", ".bat", ".ps1", ".sh", ".sql", ".xml", ".log"}:
        reasons.append(f"technical_extension:{suffix}")
        if suffix == ".log":
            warnings.append("log_file_imported_as_technical_reference")
        return ImportTypeResult("code_or_config", DOMAIN_BY_IMPORT_TYPE["code_or_config"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["code_or_config"], 0.9, reasons, warnings, None)

    if looks_like_project_docs(clean_filename, body):
        reasons.append("project_doc_signals")
        return ImportTypeResult("project_docs", DOMAIN_BY_IMPORT_TYPE["project_docs"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["project_docs"], 0.88, reasons, warnings, None)

    # Client briefs often contain lines like "Client:" or copied chat snippets.
    # Prefer client_project_data when scope/budget/deliverable signals are present;
    # reserve email_or_message_data for real message threads or email headers.
    if looks_like_client_project_data(body):
        reasons.append("client_project_signals")
        return ImportTypeResult("client_project_data", DOMAIN_BY_IMPORT_TYPE["client_project_data"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["client_project_data"], 0.84, reasons, warnings, None)

    if looks_like_email_or_message_data(body):
        reasons.append("email_or_message_signals")
        return ImportTypeResult("email_or_message_data", DOMAIN_BY_IMPORT_TYPE["email_or_message_data"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["email_or_message_data"], 0.84, reasons, warnings, None)

    if looks_like_raw_creative_lore(body, project_type=project_type):
        reasons.append("creative_lore_signals")
        return ImportTypeResult("raw_creative_lore", DOMAIN_BY_IMPORT_TYPE["raw_creative_lore"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["raw_creative_lore"], 0.82, reasons, warnings, None)

    if looks_like_markdown_structured(body):
        reasons.append("markdown_headings")
        return ImportTypeResult("markdown_structured", DOMAIN_BY_IMPORT_TYPE["markdown_structured"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["markdown_structured"], 0.78, reasons, warnings, None)

    if looks_like_conversation_notes(body):
        reasons.append("conversation_note_signals")
        return ImportTypeResult("conversation_notes", DOMAIN_BY_IMPORT_TYPE["conversation_notes"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["conversation_notes"], 0.72, reasons, warnings, None)

    if _has_key_value_density(body):
        reasons.append("key_value_density")
        return ImportTypeResult("markdown_structured", DOMAIN_BY_IMPORT_TYPE["markdown_structured"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["markdown_structured"], 0.68, reasons, warnings, None)

    reasons.append("fallback_raw_reference")
    warnings.append("low_confidence_import_type")
    return ImportTypeResult("raw_reference_text", DOMAIN_BY_IMPORT_TYPE["raw_reference_text"], CHUNKING_STRATEGY_BY_IMPORT_TYPE["raw_reference_text"], 0.55, reasons, warnings, None)


__all__ = [
    "ImportTypeResult",
    "IMPORT_TYPES",
    "ASSISTANT_DOMAINS",
    "CHUNKING_STRATEGY_BY_IMPORT_TYPE",
    "DOMAIN_BY_IMPORT_TYPE",
    "RETRIEVAL_WEIGHT_BY_IMPORT_TYPE",
    "RETRIEVAL_LIMIT_BY_IMPORT_TYPE",
    "detect_import_type",
    "try_parse_json",
]
