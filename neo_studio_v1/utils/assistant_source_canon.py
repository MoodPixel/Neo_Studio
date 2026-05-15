from __future__ import annotations

"""Assistant source-canon preservation.

Phase 4 keeps the original uploaded bytes/text as an immutable source snapshot.
Structured records, memory chunks, entity graph rows, and import reports should
link back to this source instead of treating summaries as the only evidence.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .assistant_store import ASSISTANT_ROOT
from .memory_service.sqlite_store import ensure_memory_foundation, sqlite_conn

SOURCE_CANON_DIR = ASSISTANT_ROOT / "source_canon"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_slug(value: str, fallback: str = "source") -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return (clean or fallback)[:100]


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


@dataclass
class SourceCanonRecord:
    source_doc_id: str
    project_id: str
    import_id: str
    source_filename: str
    source_format: str
    source_hash_sha256: str
    source_size_bytes: int
    snapshot_path: str
    source_ref: str
    preserved_as: str
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_source_canon_foundation() -> None:
    ensure_memory_foundation()
    with sqlite_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assistant_source_documents (
                source_doc_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                import_id TEXT NOT NULL DEFAULT '',
                source_filename TEXT NOT NULL DEFAULT '',
                source_format TEXT NOT NULL DEFAULT '',
                source_hash_sha256 TEXT NOT NULL DEFAULT '',
                source_size_bytes INTEGER NOT NULL DEFAULT 0,
                snapshot_path TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                preserved_as TEXT NOT NULL DEFAULT 'immutable_raw_upload',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                is_deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_source_documents_project ON assistant_source_documents(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_source_documents_import ON assistant_source_documents(project_id, import_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_source_documents_hash ON assistant_source_documents(project_id, source_hash_sha256)")


def preserve_source_document(
    *,
    project_id: str,
    import_id: str,
    filename: str,
    raw: bytes,
    text: str = "",
    source_ref: str = "",
    import_type: str = "",
    assistant_domain: str = "",
    document_kind: str = "",
    canon_status: str = "draft",
    visibility: str = "project_private",
) -> dict[str, Any]:
    """Persist the original upload as source canon and return link metadata.

    The original bytes are written exactly as received. If callers already decoded
    text, that text is stored only as searchable preview metadata; it does not
    replace the byte snapshot.
    """
    ensure_source_canon_foundation()
    clean_project_id = str(project_id or "").strip()
    clean_import_id = str(import_id or "").strip()
    safe_name = _safe_slug(Path(filename or "upload.txt").name, "upload.txt")
    suffix = Path(filename or "").suffix.lower().lstrip(".") or "txt"
    digest = hashlib.sha256(raw or b"").hexdigest()
    source_doc_id = f"source_doc_{digest[:12]}_{clean_import_id[-8:] if clean_import_id else 'manual'}"
    project_dir = SOURCE_CANON_DIR / _safe_slug(clean_project_id, "project")
    project_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = project_dir / f"{source_doc_id}__{safe_name}"
    if not snapshot_path.exists():
        snapshot_path.write_bytes(raw or b"")
    now = _now_iso()
    resolved_source_ref = source_ref or f"assistant_source_canon:{clean_project_id}:{source_doc_id}:{safe_name}"
    metadata = {
        "import_type": import_type,
        "assistant_domain": assistant_domain,
        "document_kind": document_kind,
        "canon_status": canon_status,
        "visibility": visibility,
        "text_preview": (text or "")[:1200],
        "snapshot_policy": "preserve_original_bytes_do_not_mutate",
    }
    with sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO assistant_source_documents(source_doc_id, project_id, import_id, source_filename, source_format, source_hash_sha256, source_size_bytes, snapshot_path, source_ref, preserved_as, metadata_json, created_at, is_deleted)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(source_doc_id) DO UPDATE SET
                project_id=excluded.project_id,
                import_id=excluded.import_id,
                source_filename=excluded.source_filename,
                source_format=excluded.source_format,
                source_hash_sha256=excluded.source_hash_sha256,
                source_size_bytes=excluded.source_size_bytes,
                snapshot_path=excluded.snapshot_path,
                source_ref=excluded.source_ref,
                preserved_as=excluded.preserved_as,
                metadata_json=excluded.metadata_json,
                is_deleted=0
            """,
            (
                source_doc_id,
                clean_project_id,
                clean_import_id,
                str(filename or ""),
                suffix,
                digest,
                len(raw or b""),
                str(snapshot_path),
                resolved_source_ref,
                "immutable_raw_upload",
                _safe_json(metadata),
                now,
            ),
        )
    return SourceCanonRecord(
        source_doc_id=source_doc_id,
        project_id=clean_project_id,
        import_id=clean_import_id,
        source_filename=str(filename or ""),
        source_format=suffix,
        source_hash_sha256=digest,
        source_size_bytes=len(raw or b""),
        snapshot_path=str(snapshot_path),
        source_ref=resolved_source_ref,
        preserved_as="immutable_raw_upload",
        created_at=now,
        metadata=metadata,
    ).to_dict()
