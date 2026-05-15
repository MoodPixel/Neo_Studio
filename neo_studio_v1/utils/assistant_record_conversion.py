from __future__ import annotations

"""Assistant raw-text to structured-record conversion tool.

Phase 9 adds an explicit preview/confirm workflow. It does not replace normal
knowledge import; it gives the user a reviewable record plan before committing
raw text into memory/source-canon/records.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

from .assistant_import_types import CHUNKING_STRATEGY_BY_IMPORT_TYPE, detect_import_type
from .assistant_raw_text_preparser import preparse_raw_text
from .assistant_structured_records import build_structured_records_from_import


def _clean_text(value: Any, limit: int = 240000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[: max(100, limit)]


def _record_preview(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    links = record.get("links") if isinstance(record.get("links"), dict) else {}
    return {
        "id": record.get("id") or "",
        "kind": record.get("kind") or "record",
        "label": record.get("label") or record.get("id") or "Record",
        "summary": record.get("summary") or "",
        "aliases": list(record.get("aliases") or [])[:12],
        "tags": list(record.get("tags") or [])[:12],
        "field_keys": list(fields.keys())[:12],
        "source_section_indexes": list(record.get("source_section_indexes") or [])[:12],
        "parent_record_id": links.get("parent_record_id") or "",
        "confidence": float(record.get("confidence") or 0),
    }


def preview_raw_text_record_conversion(
    *,
    project_id: str,
    filename: str,
    text: str,
    canon_status: str = "draft",
    visibility: str = "project_private",
    requested_import_type: str = "",
) -> dict[str, Any]:
    """Return a reviewable structured-record conversion plan for raw text."""
    clean_text = _clean_text(text)
    clean_filename = str(filename or "pasted_raw_text.txt").strip() or "pasted_raw_text.txt"
    if not clean_text:
        raise ValueError("Add raw text before previewing record conversion.")

    detection = detect_import_type(clean_filename, clean_text)
    import_type = requested_import_type.strip() if requested_import_type else str(detection.get("import_type") or "raw_reference_text")
    assistant_domain = str(detection.get("assistant_domain") or "reference")
    chunking_strategy = str(detection.get("chunking_strategy") or CHUNKING_STRATEGY_BY_IMPORT_TYPE.get(import_type, "paragraph_chunking"))
    parsed = preparse_raw_text(
        text=clean_text,
        filename=clean_filename,
        import_type=import_type,
        assistant_domain=assistant_domain,
        chunking_strategy=chunking_strategy,
    )
    parsed.update({
        "text": clean_text,
        "filename": clean_filename,
        "project_id": project_id,
        "import_type": import_type,
        "assistant_domain": assistant_domain,
        "chunking_strategy": chunking_strategy,
        "import_confidence": detection.get("confidence") or 0,
        "import_type_report": detection,
        "conversion_mode": "preview_only",
    })
    preview_import_id = f"preview_{uuid4().hex[:12]}"
    record_report = build_structured_records_from_import(
        parsed=parsed,
        import_id=preview_import_id,
        source_ref=f"assistant_record_conversion_preview:{project_id}:{Path(clean_filename).name}",
        canon_status=canon_status,
        visibility=visibility,
    )
    records = [r for r in (record_report.get("records") or []) if isinstance(r, dict)] if isinstance(record_report, dict) else []
    sections = [s for s in (parsed.get("sections") or []) if isinstance(s, dict)]
    warnings: list[str] = []
    if not records:
        warnings.append("No structured records were produced. Import can still preserve source text, but review detection/settings first.")
    if import_type in {"raw_reference_text", "raw_reference"} and len(records) <= 1:
        warnings.append("This looks like general reference material; record extraction may stay broad unless headings or key/value labels are added.")
    if len(sections) <= 1 and len(clean_text) > 3500:
        warnings.append("Only one section was detected from a long source. Add headings for cleaner records.")
    return {
        "ok": True,
        "mode": "preview",
        "project_id": project_id,
        "filename": clean_filename,
        "detected_import_type": import_type,
        "assistant_domain": assistant_domain,
        "chunking_strategy": chunking_strategy,
        "confidence": detection.get("confidence") or 0,
        "section_count": len(sections),
        "record_count": len(records),
        "records": [_record_preview(r) for r in records[:80]],
        "record_report": {k: v for k, v in (record_report or {}).items() if k != "records"},
        "sections": [
            {
                "index": idx,
                "title": s.get("title") or f"Section {idx + 1}",
                "section_role": s.get("section_role") or "body",
                "confidence": s.get("confidence") or 0,
                "preview": _clean_text(s.get("content") or "", 260),
            }
            for idx, s in enumerate(sections[:30])
        ],
        "warnings": warnings + list((parsed.get("preparse_report") or {}).get("warnings") or []),
        "recommended_action": "Review record labels/kinds, then commit conversion if the preview matches the source intent.",
    }
