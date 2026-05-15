from __future__ import annotations

"""Retrieval grounding enforcement for Assistant canon/evidence answers.

Phase 16 sits after sandboxing/source-aware retrieval and after authority-mode
selection. Authority says *which source wins*. Grounding turns selected memory
into explicit semantic locks so the LLM does not replace project-defined terms
with strong pretrained meanings from games, religion, science, mythology, etc.
"""

from dataclasses import asdict, dataclass
import re
from typing import Any

CANON_GROUNDING_MODES = {"canon_strict", "evidence_strict"}
PROJECT_TERM_FIELDS = (
    "label",
    "display_label",
    "title",
    "record_label",
    "entity_label",
    "canonical_label",
    "term",
    "name",
)
ALIAS_FIELDS = (
    "aliases",
    "alias_labels",
    "entity_aliases",
    "retrieval_aliases",
)
EXTERNAL_DRIFT_DOMAINS = (
    "franchise / fandom meanings",
    "religious or philosophical meanings",
    "scientific or dictionary meanings",
    "generic mythology meanings",
    "internet/wiki-style meanings",
)


@dataclass(frozen=True)
class GroundedTermLock:
    term: str
    canonical_definition: str
    project_id: str = ""
    project_title: str = ""
    source_label: str = "project memory"
    override_external_meanings: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\r", "\n").split()).strip()[: max(1, limit)]


def _lower(value: Any, limit: int = 500) -> str:
    return _clean(value, limit).lower()


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _split_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,;|/]", str(value or "")) if value else []
    out: list[str] = []
    for item in raw:
        label = _clean(item, 80)
        if label and label.lower() not in {x.lower() for x in out}:
            out.append(label)
    return out[:16]


def query_terms(query_text: str) -> list[str]:
    text = _clean(query_text, 500)
    quoted = re.findall(r"['\"]([^'\"]{2,80})['\"]", text)
    title_phrases = re.findall(r"\b([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,5})\b", text)
    after_what_is = re.findall(r"\b(?:what|who)\s+is\s+(?:the\s+|a\s+|an\s+)?([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*){0,5})\??", text, flags=re.I)
    candidates = quoted + title_phrases + after_what_is
    out: list[str] = []
    stop = {"what", "who", "is", "are", "the", "a", "an", "in", "of", "and", "project", "mood", "pixel"}
    for cand in candidates:
        label = _clean(cand, 80).strip(" ?:,.;")
        words = [w for w in re.split(r"\s+", label) if w]
        while words and words[0].lower() in stop:
            words.pop(0)
        while words and words[-1].lower() in stop:
            words.pop()
        label = " ".join(words)
        if len(label) < 2 or label.lower() in stop:
            continue
        if label.lower() not in {x.lower() for x in out}:
            out.append(label)
    return out[:12]


def _best_label_from_item(item: dict[str, Any], query_text: str = "") -> str:
    meta = _safe_dict(item.get("metadata"))
    query = [q.lower() for q in query_terms(query_text)]
    labels: list[str] = []
    for field in PROJECT_TERM_FIELDS:
        value = _clean(meta.get(field), 100)
        if value:
            labels.append(value)
    for field in ALIAS_FIELDS:
        labels.extend(_split_aliases(meta.get(field)))
    title = _clean(item.get("title") or item.get("source"), 100)
    if title:
        labels.append(title)
    doc = _clean(item.get("document"), 800)
    # If the user asked a named term and it appears in the chunk, lock that term.
    for q in query:
        for label in labels + [q]:
            if q and q in label.lower() or (q and q in doc.lower()):
                return _clean(label if q in label.lower() else q, 100)
    for label in labels:
        if label and not label.lower().startswith(("sqlite", "chroma", "memory")):
            return label
    if query:
        return query[0].title()
    # Fall back to first compact capitalized phrase in the document.
    match = re.search(r"\b([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,4})\b", doc)
    return _clean(match.group(1) if match else "Project-defined term", 100)


def _definition_from_item(item: dict[str, Any], term: str = "") -> str:
    meta = _safe_dict(item.get("metadata"))
    for key in ("canonical_definition", "definition", "summary", "record_summary", "entity_summary"):
        value = _clean(meta.get(key), 360)
        if value:
            return value
    doc = _clean(item.get("document"), 520)
    if not doc:
        return "Use the retrieved project memory as the authoritative meaning."
    if term and term.lower() in doc.lower():
        return doc
    return doc


def build_grounded_term_locks(
    *,
    memory_pack: dict[str, Any] | None,
    scope: dict[str, Any] | None = None,
    query_text: str = "",
    max_terms: int = 8,
) -> list[GroundedTermLock]:
    pack = memory_pack if isinstance(memory_pack, dict) else {}
    scope = scope if isinstance(scope, dict) else {}
    items = _safe_list(pack.get("items"))
    project_id = _clean(scope.get("project_id"), 120)
    project_title = _clean(scope.get("project_title"), 160) or _clean(scope.get("project_name"), 160)
    locks: list[GroundedTermLock] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = _safe_dict(item.get("metadata"))
        item_project = _clean(meta.get("memory_project_id") or meta.get("project_id") or project_id, 120)
        if project_id and item_project and item_project != project_id:
            continue
        term = _best_label_from_item(item, query_text=query_text)
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        definition = _definition_from_item(item, term)
        source_label = _clean(meta.get("source_disclosure_label") or meta.get("source_doc_id") or meta.get("source_filename") or "project memory", 160)
        locks.append(GroundedTermLock(
            term=term,
            canonical_definition=definition,
            project_id=item_project,
            project_title=_clean(meta.get("project_title"), 160) or project_title,
            source_label=source_label,
            override_external_meanings=True,
        ))
        seen.add(key)
        if len(locks) >= max_terms:
            break
    return locks


def build_grounding_prompt_block(
    *,
    authority_mode: str,
    memory_pack: dict[str, Any] | None,
    scope: dict[str, Any] | None = None,
    query_text: str = "",
) -> str:
    mode = _lower(authority_mode, 80)
    if mode not in CANON_GROUNDING_MODES:
        return ""
    locks = build_grounded_term_locks(memory_pack=memory_pack, scope=scope, query_text=query_text)
    if not locks:
        return (
            "Semantic grounding: no authoritative retrieved term lock was found. "
            "Do not replace the user's project term with an external franchise, religious, scientific, or dictionary meaning. "
            "Say the project canon/source was not found before guessing."
        )
    lines = [
        "Semantic authority lock:",
        "The following terms are defined by the active project/source evidence. Interpret them using these meanings first.",
    ]
    for lock in locks:
        project = f" ({lock.project_title})" if lock.project_title else ""
        lines.append(f"- {lock.term}{project}: {lock.canonical_definition}")
    lines.extend([
        "External meaning suppression:",
        "- Do not substitute franchise/fandom, religious/philosophical, scientific/dictionary, or generic mythology meanings for locked terms.",
        "- Do not open with real-world background for locked terms unless the user explicitly asks to compare external meanings.",
        "- If the retrieved definition is incomplete, state what canon/source says and what is missing; do not fill gaps from unrelated media or world knowledge.",
    ])
    return "\n".join(lines).strip()


def grounding_metadata(
    *,
    authority_mode: str,
    memory_pack: dict[str, Any] | None,
    scope: dict[str, Any] | None = None,
    query_text: str = "",
) -> dict[str, Any]:
    locks = build_grounded_term_locks(memory_pack=memory_pack, scope=scope, query_text=query_text)
    return {
        "grounding_mode": _lower(authority_mode, 80),
        "semantic_locks": [lock.to_dict() for lock in locks],
        "external_drift_domains_blocked": list(EXTERNAL_DRIFT_DOMAINS),
        "grounding_required": _lower(authority_mode, 80) in CANON_GROUNDING_MODES,
    }
