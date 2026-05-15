from __future__ import annotations

"""Global raw-text pre-parser for Assistant knowledge imports.

Phase 2 is intentionally assistant-wide. It converts messy non-JSON uploads into
retrieval-friendly sections for worldbuilding/lore, client briefs, messages,
project notes, docs, logs, and generic references. It does not hardcode any one
sample document; sample lore text is only a test case for the creative-lore path.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedSection:
    title: str
    content: str
    section_role: str = "body"
    confidence: float = 0.6
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["title"] = _clean_inline(data.get("title") or "Section")[:160]
        data["content"] = _clean_text(data.get("content") or "", 200_000)
        return data


@dataclass
class PreparseResult:
    sections: list[ParsedSection]
    entities: list[dict[str, str]] = field(default_factory=list)
    detected_topics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    strategy_used: str = "paragraph_chunking"

    def to_report(self) -> dict[str, Any]:
        return {
            "section_count": len(self.sections),
            "entity_count": len(self.entities),
            "detected_topics": self.detected_topics[:40],
            "warnings": self.warnings[:20],
            "strategy_used": self.strategy_used,
        }


ROLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("identity", ["identity", "profile", "overview", "who", "definition", "what is", "summary"]),
    ("scope", ["scope", "deliverable", "requirement", "objective", "goal", "task"]),
    ("pricing", ["price", "pricing", "budget", "$", "rate", "fixed price", "hourly"]),
    ("timeline", ["timeline", "turnaround", "deadline", "delivery", "due", "schedule"]),
    ("rules", ["rule", "law", "policy", "must", "cannot", "never", "always", "guardrail"]),
    ("abilities", ["ability", "power", "can ", "may ", "skill", "feature", "capability"]),
    ("limitations", ["limit", "limitation", "constraint", "weakness", "risk", "warning", "failure"]),
    ("relationship", ["relationship", "bond", "link", "connection", "counterpart", "client"]),
    ("history", ["history", "origin", "before", "after", "event", "chapter", "record"]),
    ("misconception", ["myth", "apocrypha", "false", "rumor", "misconception", "lie"]),
    ("action_items", ["todo", "next step", "action", "phase", "implement", "fix"]),
    ("message", ["from:", "to:", "subject:", "hello", "hi ", "thanks", "regards"]),
    ("technical", ["error", "traceback", "exception", "config", "yaml", "python", "function"]),
]

ENTITY_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*(Client|Customer|Brand|Company|Project|Campaign):\s*(.+)$", "client_project"),
    (r"^\s*(World|Universe|Region|City|Location|Organization|Faction|Creature|Character|Event|Ritual|Law|Condition|Bond|Concept):\s*(.+)$", "creative_lore"),
    (r"^\s*(From|To|Subject):\s*(.+)$", "communication"),
    (r"^\s*(File|Module|Function|Class|Endpoint|Route):\s*(.+)$", "technical"),
]


def _clean_text(value: Any, limit: int = 20000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()[:max(100, limit)]


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _role_for(title: str, content: str = "") -> str:
    hay = f"{title}\n{content[:600]}".lower()
    scores: dict[str, int] = {}
    for role, words in ROLE_KEYWORDS:
        scores[role] = sum(1 for word in words if word in hay)
    role, score = max(scores.items(), key=lambda item: item[1])
    return role if score > 0 else "body"


def _split_long_text(text: str, *, max_chars: int = 3000, overlap: int = 160) -> list[str]:
    text = _clean_text(text, 500_000)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        block = text[start:end]
        if end < len(text):
            boundary = max(block.rfind("\n\n"), block.rfind(". "), block.rfind("\n"))
            if boundary > max_chars * 0.55:
                end = start + boundary + (2 if block[boundary:boundary + 2] == "\n\n" else 1)
                block = text[start:end]
        if block.strip():
            chunks.append(block.strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _extract_entities(text: str, *, import_type: str, filename: str = "") -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    for pattern, domain in ENTITY_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I | re.M):
            kind = _clean_inline(match.group(1)).lower().replace(" ", "_")
            label = _clean_inline(match.group(2).split("—")[0])[:160]
            if label:
                entities.append({"id": "", "kind": kind, "label": label, "domain": domain})
    # Conversation/client exports often expose usernames as standalone lines.
    if import_type in {"email_or_message_data", "client_project_data"}:
        for match in re.finditer(r"^\s*([A-Za-z][A-Za-z0-9_.-]{2,40})\s*$", text, flags=re.M):
            label = match.group(1).strip()
            if label.lower() not in {"profile", "image", "thanks", "hello", "message"}:
                entities.append({"id": "", "kind": "person_or_handle", "label": label, "domain": "communication"})
    if not entities and filename:
        entities.append({"id": "", "kind": "source_document", "label": Path(filename).stem or filename, "domain": "reference"})
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in entities:
        key = (item.get("kind", ""), item.get("label", "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:80]


def _heading_sections(text: str) -> list[ParsedSection]:
    lines = _clean_text(text, 500_000).split("\n")
    sections: list[ParsedSection] = []
    title = "Document overview"
    buf: list[str] = []
    heading_re = re.compile(r"^(#{1,6}\s+|\[[^\]]{2,90}\]\s*$|[A-Z][A-Za-z0-9 &/,:;()'\-]{3,100}$)")

    def flush() -> None:
        nonlocal buf, title
        content = "\n".join(buf).strip()
        if content:
            for idx, part in enumerate(_split_long_text(content)):
                section_title = title if idx == 0 else f"{title} part {idx + 1}"
                sections.append(ParsedSection(section_title, part, _role_for(section_title, part), 0.78, {"source": "heading"}))
        buf = []

    for line in lines:
        stripped = line.strip()
        is_heading = bool(stripped and heading_re.match(stripped) and len(stripped) <= 120)
        if is_heading and (stripped.startswith("#") or (stripped.startswith("[") and stripped.endswith("]")) or stripped.isupper()):
            flush()
            title = stripped.strip("#[] ").strip() or "Section"
        else:
            buf.append(line)
    flush()
    return sections


def _key_value_sections(text: str) -> list[ParsedSection]:
    lines = [line.rstrip() for line in _clean_text(text, 500_000).split("\n")]
    sections: list[ParsedSection] = []
    current_title = "Document facts"
    current: list[str] = []
    current_role = "facts"
    kv_re = re.compile(r"^([A-Za-z][A-Za-z0-9 _/().-]{1,54}):\s*(.*)$")
    for line in lines:
        match = kv_re.match(line.strip())
        if match and len(current) > 0 and len("\n".join(current)) > 500:
            content = "\n".join(current).strip()
            sections.append(ParsedSection(current_title, content, current_role, 0.72, {"source": "key_value"}))
            current = []
        if match and not current:
            current_title = match.group(1).strip()
            current_role = _role_for(current_title, match.group(2))
        current.append(line)
    if current:
        sections.append(ParsedSection(current_title, "\n".join(current).strip(), current_role, 0.72, {"source": "key_value"}))
    return sections


def _paragraph_sections(text: str) -> list[ParsedSection]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", _clean_text(text, 500_000)) if p.strip()]
    sections: list[ParsedSection] = []
    for idx, para in enumerate(paragraphs):
        title = _infer_paragraph_title(para, idx)
        for part_idx, part in enumerate(_split_long_text(para)):
            section_title = title if part_idx == 0 else f"{title} part {part_idx + 1}"
            sections.append(ParsedSection(section_title, part, _role_for(section_title, part), 0.62, {"source": "paragraph", "paragraph_index": idx}))
    return sections


def _infer_paragraph_title(paragraph: str, idx: int) -> str:
    first = _clean_inline(paragraph.split("\n", 1)[0])
    if len(first) <= 100 and (first.lower().startswith("chapter ") or first.endswith(":") or "—" in first[:80]):
        return first.strip(":")
    sentence = re.split(r"(?<=[.!?])\s+", _clean_inline(paragraph))[0]
    return (sentence[:86] + "…") if len(sentence) > 90 else (sentence or f"Paragraph {idx + 1}")


def _creative_lore_sections(text: str) -> list[ParsedSection]:
    base = _heading_sections(text) or _paragraph_sections(text)
    if not base:
        return []
    # Add a compact fact index from strongly signaled lines/paragraphs.
    fact_lines: list[str] = []
    patterns = [
        r"\b(?:is|are)\s+(?:not\s+)?(?:a|an|the)?\s*[^.]{8,160}\.",
        r"\b(?:must|cannot|never|always|may|can)\b[^.]{8,180}\.",
        r"\b(?:after|before|because|when|if)\b[^.]{12,180}\.",
    ]
    for para in re.split(r"\n\s*\n", text):
        for pat in patterns:
            for match in re.finditer(pat, para, flags=re.I):
                line = _clean_inline(match.group(0))
                if line and line not in fact_lines:
                    fact_lines.append(f"- {line}")
                if len(fact_lines) >= 18:
                    break
            if len(fact_lines) >= 18:
                break
        if len(fact_lines) >= 18:
            break
    if fact_lines:
        base.insert(0, ParsedSection("Extracted canon facts", "\n".join(fact_lines), "rules", 0.72, {"source": "fact_index"}))
    return base


def _client_brief_sections(text: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    labels = {
        "Client / brand context": ["client", "brand", "company", "founder", "business"],
        "Scope and deliverables": ["scope", "deliver", "clips", "videos", "reels", "shorts", "edit"],
        "Platforms and format": ["platform", "tiktok", "instagram", "youtube", "facebook", "vertical", "9:16"],
        "Budget and pricing": ["budget", "price", "pricing", "$", "hourly", "fixed"],
        "Timeline and turnaround": ["timeline", "turnaround", "deadline", "days", "weekly", "ongoing"],
        "Assets and references": ["asset", "footage", "logo", "reference", "style", "script"],
        "Questions / unknowns": ["question", "clarify", "need", "not sure", "ask"],
    }
    lines = [line.strip() for line in _clean_text(text, 500_000).split("\n") if line.strip()]
    used: set[int] = set()
    for title, words in labels.items():
        picked: list[str] = []
        for i, line in enumerate(lines):
            if i in used:
                continue
            lower = line.lower()
            if any(word in lower for word in words):
                picked.append(line)
                used.add(i)
        if picked:
            sections.append(ParsedSection(title, "\n".join(picked), _role_for(title, "\n".join(picked)), 0.76, {"source": "client_brief_classifier"}))
    remainder = [line for i, line in enumerate(lines) if i not in used]
    if remainder:
        sections.append(ParsedSection("Additional client context", "\n".join(remainder), "body", 0.58, {"source": "client_brief_remainder"}))
    return sections or _heading_sections(text) or _paragraph_sections(text)


def _message_sections(text: str) -> list[ParsedSection]:
    clean = _clean_text(text, 500_000)
    msg_boundary = re.compile(r"^\s*(From|To|Subject|Sent|Received):\s+.*$|^\s*[A-Za-z][A-Za-z0-9_. @-]{1,42}\s*$", re.I | re.M)
    starts = [m.start() for m in msg_boundary.finditer(clean)]
    if len(starts) < 2:
        return _heading_sections(clean) or _paragraph_sections(clean)
    starts.append(len(clean))
    sections: list[ParsedSection] = []
    for idx in range(len(starts) - 1):
        block = clean[starts[idx]:starts[idx + 1]].strip()
        if len(block) < 20:
            continue
        first = _clean_inline(block.split("\n", 1)[0])[:80]
        title = f"Message {len(sections) + 1}: {first}"
        sections.append(ParsedSection(title, block, "message", 0.74, {"source": "message_boundary"}))
    return sections or _paragraph_sections(clean)


def _code_or_log_sections(text: str, filename: str = "") -> list[ParsedSection]:
    chunks = _split_long_text(text, max_chars=4200, overlap=120)
    stem = Path(filename).name or "Technical text"
    return [ParsedSection(f"{stem} chunk {idx + 1}", chunk, "technical", 0.7, {"source": "technical_chunk"}) for idx, chunk in enumerate(chunks)]


def _topics_from_sections(sections: list[ParsedSection]) -> list[str]:
    topics: list[str] = []
    for section in sections:
        role = section.section_role
        if role and role not in topics:
            topics.append(role)
        title = section.title.strip()
        if title and title.lower() not in {"document overview", "section"} and title not in topics:
            topics.append(title[:80])
    return topics[:40]


def preparse_raw_text(*, text: str, filename: str = "", import_type: str = "raw_reference_text", chunking_strategy: str = "paragraph_chunking", assistant_domain: str = "reference", project_type: str = "general") -> PreparseResult:
    clean = _clean_text(text, 500_000)
    warnings: list[str] = []
    if not clean:
        return PreparseResult([], [], [], ["empty_text"], chunking_strategy)

    if chunking_strategy == "semantic_section_chunking" or import_type == "raw_creative_lore":
        sections = _creative_lore_sections(clean)
    elif chunking_strategy == "brief_section_chunking" or import_type == "client_project_data":
        sections = _client_brief_sections(clean)
    elif chunking_strategy == "message_thread_chunking" or import_type == "email_or_message_data":
        sections = _message_sections(clean)
    elif chunking_strategy == "code_block_chunking" or import_type == "code_or_config":
        sections = _code_or_log_sections(clean, filename)
    elif chunking_strategy in {"heading_section_chunking", "topic_note_chunking"} or import_type in {"markdown_structured", "project_docs", "conversation_notes"}:
        sections = _heading_sections(clean) or _key_value_sections(clean) or _paragraph_sections(clean)
    else:
        sections = _key_value_sections(clean) if _looks_key_value_dense(clean) else _paragraph_sections(clean)

    if not sections:
        sections = [ParsedSection(f"Chunk {idx + 1}", chunk, _role_for("", chunk), 0.5, {"source": "fallback_split"}) for idx, chunk in enumerate(_split_long_text(clean))]
        warnings.append("fallback_split_used")

    sections = [ParsedSection(s.title, s.content, s.section_role or _role_for(s.title, s.content), s.confidence, {**(s.metadata or {}), "assistant_domain": assistant_domain, "import_type": import_type}) for s in sections if _clean_text(s.content, 500_000)]
    entities = _extract_entities(clean, import_type=import_type, filename=filename)
    return PreparseResult(sections=sections, entities=entities, detected_topics=_topics_from_sections(sections), warnings=warnings, strategy_used=chunking_strategy)


def _looks_key_value_dense(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    kv = sum(1 for line in lines[:160] if re.match(r"^[A-Za-z][A-Za-z0-9 _/().-]{1,54}:\s*\S+", line))
    return kv >= 4 and kv / max(1, min(len(lines), 160)) >= 0.1


__all__ = ["ParsedSection", "PreparseResult", "preparse_raw_text"]
