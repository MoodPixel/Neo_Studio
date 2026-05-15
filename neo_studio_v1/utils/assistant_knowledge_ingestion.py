from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .assistant_project_profiles import resolve_project_profile
from .assistant_store import ASSISTANT_ROOT, load_project, update_project
from .logging_utils import get_logger
from .memory_service.chroma_store import ASSISTANT_COLLECTION, upsert_memory_chunks
from .memory_service.sqlite_store import ensure_memory_foundation, record_memory_write, upsert_memory_chunks_sqlite
from .assistant_entity_registry import build_entities_from_import
from .assistant_import_types import CHUNKING_STRATEGY_BY_IMPORT_TYPE, detect_import_type
from .assistant_raw_text_preparser import preparse_raw_text
from .assistant_structured_records import build_structured_records_from_import
from .assistant_source_canon import preserve_source_document
from .assistant_chunk_types import normalize_chunk_type
from .assistant_chunk_metadata import build_chunk_metadata
from .assistant_import_diagnostics import build_import_diagnostics
from .assistant_memory_reindex import refresh_after_memory_write

logger = get_logger(__name__)

MAX_KNOWLEDGE_UPLOAD_BYTES = 3 * 1024 * 1024
SUPPORTED_KNOWLEDGE_SUFFIXES = {
    '.txt', '.md', '.markdown', '.json', '.json5', '.csv', '.log', '.yaml', '.yml'
}

IMPORTS_DIR = ASSISTANT_ROOT / 'knowledge_imports'


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _safe_slug(value: str, fallback: str = 'knowledge') -> str:
    clean = re.sub(r'[^a-zA-Z0-9._-]+', '-', str(value or '').strip()).strip('-._')
    return (clean or fallback)[:90]


def _clean_text(value: Any, limit: int = 20000) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[\t ]+', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()[:max(100, limit)]


def _decode_upload(raw: bytes) -> str:
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='ignore') or raw.decode('latin-1', errors='ignore')


def _split_long_text(text: str, *, max_chars: int = 3600, overlap: int = 240) -> list[str]:
    text = _clean_text(text, 500000)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        slice_text = text[start:end]
        if end < len(text):
            # Prefer paragraph or sentence boundary near the end.
            boundary = max(slice_text.rfind('\n\n'), slice_text.rfind('. '), slice_text.rfind('\n'))
            if boundary > max_chars * 0.55:
                end = start + boundary + (2 if slice_text[boundary:boundary + 2] == '\n\n' else 1)
                slice_text = text[start:end]
        cleaned = slice_text.strip()
        if cleaned:
            chunks.append(cleaned)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _heading_sections(text: str) -> list[dict[str, Any]]:
    lines = _clean_text(text, 500000).split('\n')
    sections: list[dict[str, Any]] = []
    title = 'Document overview'
    buf: list[str] = []
    heading_re = re.compile(r'^(#{1,6}\s+|[🗺️🌍🗓️🪶🗃️🧩🕯️🏛️🤝🧭🌋🧠🌾🛠️🕰️👥🐾🕳️🐉🗝️💰📨👑📖💬]+\s+|[A-Z][A-Za-z0-9 &/,:;()\-]{3,80}$)')

    def flush() -> None:
        nonlocal buf, title
        content = '\n'.join(buf).strip()
        if content:
            sections.append({'title': title.strip('# ').strip() or 'Section', 'content': content})
        buf = []

    for line in lines:
        stripped = line.strip()
        is_heading = bool(stripped and heading_re.match(stripped) and len(stripped) <= 110)
        # Avoid treating every short data line as a heading.
        if is_heading and (stripped.startswith('#') or any(ch in stripped for ch in '🗺️🌍🗓️🪶🗃️🧩🕯️🏛️🤝🧭🌋🧠🌾🛠️🕰️👥🐾🕳️🐉🗝️💰📨👑📖💬') or stripped.isupper()):
            flush()
            title = stripped.strip('# ').strip()
        else:
            buf.append(line)
    flush()
    if not sections:
        sections = [{'title': f'Chunk {idx + 1}', 'content': chunk} for idx, chunk in enumerate(_split_long_text(text))]
    return sections


def _flatten_json(value: Any, prefix: str = '') -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            if isinstance(item, (dict, list)):
                rows.extend(_flatten_json(item, path))
            else:
                rows.append((path, item))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            path = f'{prefix}[{idx}]' if prefix else f'[{idx}]'
            if isinstance(item, (dict, list)):
                rows.extend(_flatten_json(item, path))
            else:
                rows.append((path, item))
    else:
        rows.append((prefix or 'value', value))
    return rows


def _json_section_chunks(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return [{'title': 'JSON document', 'content': json.dumps(data, ensure_ascii=False, indent=2)}]
    chunks: list[dict[str, Any]] = []
    # Keep top-level identity as a high-value chunk when present.
    identity_bits = []
    for key in ('id', 'kind', 'label', 'display_label', 'summary', 'canon_status', 'visibility'):
        if key in data:
            identity_bits.append(f'{key}: {data.get(key)}')
    if identity_bits:
        chunks.append({'title': 'Identity', 'content': '\n'.join(identity_bits)})
    for key, value in data.items():
        if key in {'id', 'kind', 'label', 'display_label', 'summary', 'canon_status', 'visibility'}:
            continue
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                title = f'{key}.{sub_key}'
                content = json.dumps(sub_value, ensure_ascii=False, indent=2) if isinstance(sub_value, (dict, list)) else str(sub_value)
                for idx, part in enumerate(_split_long_text(content)):
                    chunks.append({'title': title if idx == 0 else f'{title} part {idx + 1}', 'content': part})
        elif isinstance(value, list):
            content = json.dumps(value, ensure_ascii=False, indent=2)
            for idx, part in enumerate(_split_long_text(content)):
                chunks.append({'title': key if idx == 0 else f'{key} part {idx + 1}', 'content': part})
        else:
            chunks.append({'title': key, 'content': str(value)})
    return [row for row in chunks if _clean_text(row.get('content'), 100000)]


def _csv_chunks(text: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if rows and reader.fieldnames:
            chunks = []
            for idx, row in enumerate(rows[:500]):
                bits = [f'{key}: {value}' for key, value in row.items() if str(value or '').strip()]
                chunks.append({'title': f'CSV row {idx + 1}', 'content': '\n'.join(bits)})
            return chunks
    except Exception:
        pass
    return [{'title': f'Chunk {idx + 1}', 'content': chunk} for idx, chunk in enumerate(_split_long_text(text))]


def _detect_document_kind(*, suffix: str, text: str, parsed_json: Any, project_type: str) -> str:
    if isinstance(parsed_json, dict):
        kind = str(parsed_json.get('kind') or '').strip().lower()
        if kind:
            return kind
        if {'fields', 'links', 'schema_version'} & set(parsed_json.keys()):
            return 'structured_record'
    lower = text[:2000].lower()
    if project_type == 'universe':
        if 'world profile' in lower or 'world name:' in lower:
            return 'world'
        if 'kingdom' in lower:
            return 'kingdom_or_region'
        if 'character' in lower:
            return 'character'
    return suffix.lstrip('.') or 'text'


def _extract_entities_for_report(parsed_json: Any, text: str, project_type: str) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    if isinstance(parsed_json, dict):
        if parsed_json.get('id') or parsed_json.get('label') or parsed_json.get('display_label'):
            entities.append({
                'id': str(parsed_json.get('id') or '').strip(),
                'kind': str(parsed_json.get('kind') or 'record').strip(),
                'label': str(parsed_json.get('display_label') or parsed_json.get('label') or parsed_json.get('id') or 'Structured record').strip(),
            })
        related = ((parsed_json.get('links') or {}).get('related') if isinstance(parsed_json.get('links'), dict) else {})
        if isinstance(related, dict):
            for key, values in related.items():
                if isinstance(values, list):
                    for value in values[:30]:
                        if str(value or '').strip():
                            entities.append({'id': str(value).strip(), 'kind': key.rstrip('s'), 'label': str(value).strip()})
    if project_type == 'universe' and text:
        for match in re.finditer(r'^(World Name|Universe|World|Kingdom|Region|City|Location|Organization|Creature|Character):\s*(.+)$', text, flags=re.I | re.M):
            entities.append({'id': '', 'kind': match.group(1).lower(), 'label': match.group(2).strip()[:120]})
    seen = set()
    out = []
    for item in entities:
        key = (item.get('kind') or '', item.get('id') or '', item.get('label') or '')
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:80]


def parse_knowledge_document(*, filename: str, raw: bytes, project: dict[str, Any]) -> dict[str, Any]:
    suffix = Path(filename or '').suffix.lower()
    text = _decode_upload(raw).strip()
    parsed_json: Any = None
    json_error = ''
    if suffix in {'.json', '.json5'}:
        try:
            parsed_json = json.loads(text)
        except Exception as exc:
            json_error = str(exc)
    project_profile = resolve_project_profile(project)
    project_type = str(project_profile.get('project_type') or project.get('project_type') or 'general').strip() or 'general'
    import_result = detect_import_type(filename, text, project_type=project_type, parsed_json=parsed_json)
    if parsed_json is None and import_result.parsed_json is not None:
        parsed_json = import_result.parsed_json
    doc_kind = _detect_document_kind(suffix=suffix, text=text, parsed_json=parsed_json, project_type=project_type)
    if doc_kind in {'txt', 'md', 'markdown', 'text'}:
        doc_kind = import_result.import_type
    preparse_report: dict[str, Any] = {}
    extra_entities: list[dict[str, str]] = []
    if parsed_json is not None:
        sections = _json_section_chunks(parsed_json)
    elif suffix == '.csv':
        sections = _csv_chunks(text)
    else:
        preparse = preparse_raw_text(
            text=text,
            filename=filename,
            import_type=import_result.import_type,
            chunking_strategy=import_result.chunking_strategy,
            assistant_domain=import_result.assistant_domain,
            project_type=project_type,
        )
        sections = [section.to_dict() for section in preparse.sections]
        preparse_report = preparse.to_report()
        extra_entities = preparse.entities
    entities = _extract_entities_for_report(parsed_json, text, project_type)
    entities.extend(extra_entities)
    return {
        'filename': filename,
        'suffix': suffix,
        'document_kind': doc_kind,
        'project_type': project_type,
        'project_profile': project_profile,
        'parsed_json': parsed_json,
        'json_error': json_error,
        'text': text,
        'sections': sections,
        'entities': entities,
        'preparse_report': preparse_report,
        'import_type': import_result.import_type,
        'assistant_domain': import_result.assistant_domain,
        'chunking_strategy': import_result.chunking_strategy,
        'import_confidence': import_result.confidence,
        'import_reasons': import_result.reasons,
        'import_warnings': import_result.warnings,
        'import_type_report': import_result.to_report(),
        'structured_records': [],
        'structured_record_report': {},
    }


def ingest_knowledge_document(*, project_id: str, filename: str, raw: bytes, canon_status: str = 'draft', visibility: str = '', import_mode: str = 'memory') -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        raise ValueError('No project selected for knowledge import.')
    project = load_project(clean_project_id)
    if not project:
        raise ValueError('Assistant project not found.')
    suffix = Path(filename or '').suffix.lower()
    if suffix not in SUPPORTED_KNOWLEDGE_SUFFIXES:
        raise ValueError('Unsupported knowledge file type. Use TXT, MD, JSON, CSV, YAML, or LOG for now.')
    if not raw:
        raise ValueError('That upload was empty.')
    if len(raw) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise ValueError('That knowledge file is too large. Keep imports under 3 MB for now.')
    parsed = parse_knowledge_document(filename=filename, raw=raw, project=project)
    if not parsed.get('sections'):
        raise ValueError('That file did not contain readable importable text.')
    now = _now_iso()
    import_id = f'knowledge_import_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:8]}'
    source_ref = f'assistant_project_import:{clean_project_id}:{import_id}:{filename}'
    canonical_status = str(canon_status or '').strip().lower() or 'draft'
    if canonical_status not in {'draft', 'active', 'primary_canon', 'secondary_canon', 'deprecated', 'archived', 'speculative'}:
        canonical_status = 'draft'
    visibility_clean = str(visibility or '').strip().lower()[:80]
    if not visibility_clean:
        visibility_clean = 'project_private'
    source_canon = preserve_source_document(
        project_id=clean_project_id,
        import_id=import_id,
        filename=filename,
        raw=raw,
        text=parsed.get('text') or '',
        source_ref=source_ref,
        import_type=parsed.get('import_type') or '',
        assistant_domain=parsed.get('assistant_domain') or '',
        document_kind=parsed.get('document_kind') or '',
        canon_status=canonical_status,
        visibility=visibility_clean,
    )
    parsed['source_canon'] = source_canon
    structured_record_report = build_structured_records_from_import(
        parsed={**parsed, 'filename': filename},
        import_id=import_id,
        source_ref=source_ref,
        canon_status=canonical_status,
        visibility=visibility_clean,
    )
    structured_records = structured_record_report.get('records') if isinstance(structured_record_report, dict) else []
    parsed['structured_records'] = structured_records if isinstance(structured_records, list) else []
    parsed['structured_record_report'] = structured_record_report if isinstance(structured_record_report, dict) else {}
    section_record_map: dict[int, dict[str, Any]] = {}
    for record in parsed.get('structured_records') or []:
        if not isinstance(record, dict):
            continue
        for section_index in record.get('source_section_indexes') or []:
            try:
                idx_int = int(section_index)
            except Exception:
                continue
            if idx_int not in section_record_map or record.get('kind') != 'lore_source_record':
                section_record_map[idx_int] = record

    chunks: list[dict[str, Any]] = []
    for idx, section in enumerate(parsed.get('sections') or []):
        content = _clean_text(section.get('content') or '', 12000)
        if not content:
            continue
        title = _clean_text(section.get('title') or f'Section {idx + 1}', 240)
        doc = f"Project: {project.get('title') or clean_project_id}\nImport: {filename}\nSection: {title}\nCanon status: {canonical_status}\nVisibility: {visibility_clean}\n\n{content}"
        raw_chunk_type = str(parsed.get('document_kind') or parsed.get('import_type') or 'knowledge')
        import_type = str(parsed.get('import_type') or '').strip()
        assistant_domain = str(parsed.get('assistant_domain') or '').strip()
        chunking_strategy = str(parsed.get('chunking_strategy') or CHUNKING_STRATEGY_BY_IMPORT_TYPE.get(import_type, 'paragraph_chunking'))
        section_record = section_record_map.get(idx) or {}
        if parsed.get('project_type') == 'universe' and title.lower() in {'identity', 'fields.core_laws', 'fields.truth_layers'}:
            raw_chunk_type = 'canon_guard'
        chunk_type_result = normalize_chunk_type(
            raw_chunk_type=raw_chunk_type,
            import_type=import_type,
            assistant_domain=assistant_domain,
            document_kind=parsed.get('document_kind') or 'knowledge',
            section_role=section.get('section_role') or 'body',
            section_title=title,
            structured_record_kind=section_record.get('kind') or '',
            project_type=parsed.get('project_type') or 'general',
        )
        chunk_type = chunk_type_result.chunk_type
        chunk_id = f"assistant::{clean_project_id}::{import_id}::{idx:04d}"
        chunk_metadata, chunk_metadata_report = build_chunk_metadata(
            chunk_id=chunk_id,
            project_id=clean_project_id,
            project=project,
            import_id=import_id,
            filename=filename,
            suffix=suffix,
            source_ref=source_ref,
            source_canon=source_canon,
            parsed=parsed,
            section=section,
            section_index=idx,
            section_count=len(parsed.get('sections') or []),
            title=title,
            content=content,
            canonical_status=canonical_status,
            visibility=visibility_clean,
            raw_chunk_type=raw_chunk_type,
            chunk_type_result=chunk_type_result,
            section_record=section_record,
            now=now,
        )
        chunks.append({
            'id': chunk_id,
            'document': doc,
            'metadata': chunk_metadata,
        })
    ensure_memory_foundation()
    sqlite_count = upsert_memory_chunks_sqlite(lane='assistant', collection_name=ASSISTANT_COLLECTION, chunks=chunks)
    chroma_ok = upsert_memory_chunks(ASSISTANT_COLLECTION, chunks)
    project_title = str(project.get('title') or clean_project_id).strip()
    linked = list(project.get('linked_records') if isinstance(project.get('linked_records'), list) else [])
    linked.append({
        'id': f'project_record_{uuid4().hex[:12]}',
        'title': f'Knowledge import: {Path(filename).stem or filename}',
        'record_type': 'knowledge_import',
        'note': f"Imported {len(chunks)} memory chunk(s) as {parsed.get('document_kind') or 'knowledge'} / {parsed.get('import_type') or 'unknown'} for {project_title}.",
        'source': source_ref,
        'source_doc_id': source_canon.get('source_doc_id') or '',
        'source_hash_sha256': source_canon.get('source_hash_sha256') or '',
        'created_at': now,
    })
    updated_project = update_project(clean_project_id, {'linked_records': linked}) or project
    entity_graph = build_entities_from_import(project_id=clean_project_id, parsed=parsed, report={
        'import_id': import_id,
        'project_id': clean_project_id,
        'filename': filename,
        'source_ref': source_ref,
        'source_canon': source_canon,
        'canon_status': canonical_status,
        'visibility': visibility_clean,
    })
    chunk_ids = [str(chunk.get('id') or '').strip() for chunk in chunks if str(chunk.get('id') or '').strip()]
    memory_refresh = refresh_after_memory_write(
        lane='assistant',
        project_id=clean_project_id,
        reason='knowledge_import',
        chunk_ids=chunk_ids,
        auto_refresh=True,
    )
    report = {
        'ok': True,
        'import_id': import_id,
        'project_id': clean_project_id,
        'project_title': project_title,
        'project_type': parsed.get('project_type') or 'general',
        'document_kind': parsed.get('document_kind') or 'knowledge',
        'import_type': parsed.get('import_type') or 'raw_reference_text',
        'assistant_domain': parsed.get('assistant_domain') or 'reference',
        'chunking_strategy': parsed.get('chunking_strategy') or 'paragraph_chunking',
        'import_confidence': parsed.get('import_confidence') or 0,
        'import_type_report': parsed.get('import_type_report') or {},
        'preparse_report': parsed.get('preparse_report') or {},
        'structured_record_report': parsed.get('structured_record_report') or {},
        'structured_record_count': len(parsed.get('structured_records') or []),
        'filename': filename,
        'source_ref': source_ref,
        'source_canon': source_canon,
        'canon_status': canonical_status,
        'visibility': visibility_clean,
        'section_count': len(parsed.get('sections') or []),
        'chunk_count': len(chunks),
        'chunk_metadata_schema': 'assistant_chunk_metadata.v1',
        'chunk_metadata_quality': {
            'average': round(sum(float((chunk.get('metadata') or {}).get('metadata_quality_score') or 0) for chunk in chunks) / max(1, len(chunks)), 3),
            'complete_provenance_count': sum(1 for chunk in chunks if (chunk.get('metadata') or {}).get('source_doc_id') and (chunk.get('metadata') or {}).get('source_hash_sha256')),
            'with_structured_record_count': sum(1 for chunk in chunks if (chunk.get('metadata') or {}).get('structured_record_id')),
        },
        'priority_schema': 'assistant_canon_priority.v1',
        'priority_summary': {
            'average_truth_priority_rank': round(sum(float((chunk.get('metadata') or {}).get('truth_priority_rank') or 0) for chunk in chunks) / max(1, len(chunks)), 2),
            'highest_truth_priority_rank': max([int(float((chunk.get('metadata') or {}).get('truth_priority_rank') or 0)) for chunk in chunks] or [0]),
            'strict_conflict_count': sum(1 for chunk in chunks if (chunk.get('metadata') or {}).get('requires_source_check_for_conflict')),
            'evidence_tiers': sorted({str((chunk.get('metadata') or {}).get('evidence_tier') or 'unknown') for chunk in chunks}),
        },
        'sqlite_chunk_count': sqlite_count,
        'chroma_upserted': bool(chroma_ok),
        'memory_index_state': memory_refresh.get('index_state') if isinstance(memory_refresh, dict) else {},
        'memory_refresh': memory_refresh,
        'entities': parsed.get('entities') or [],
        'entity_graph': entity_graph,
        'entity_graph_count': int((entity_graph or {}).get('entity_count') or 0),
        'relationship_graph_count': int((entity_graph or {}).get('relationship_count') or 0),
        'warnings': (
            ([f'JSON parse failed: {parsed.get("json_error")}'] if parsed.get('json_error') else [])
            + list((parsed.get('preparse_report') or {}).get('warnings') or [])
            + ([f'Structured record issue: {(parsed.get("structured_record_report") or {}).get("error")}'] if isinstance(parsed.get('structured_record_report'), dict) and (parsed.get('structured_record_report') or {}).get('error') else [])
            + ([f'Entity graph import issue: {(entity_graph or {}).get("error")}'] if isinstance(entity_graph, dict) and entity_graph.get('error') else [])
        ),
        'created_at': now,
    }
    report['import_diagnostics'] = build_import_diagnostics(report=report, chunks=chunks)
    project_dir = IMPORTS_DIR / _safe_slug(clean_project_id, 'project')
    project_dir.mkdir(parents=True, exist_ok=True)
    report_path = project_dir / f'{_safe_slug(import_id)}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    record_memory_write(
        write_log_id=f'awl_{uuid4().hex}',
        lane='assistant',
        entity_type='project_knowledge_import',
        entity_id=import_id,
        operation='ingest',
        source_ref=source_ref,
        details={**report, 'report_path': str(report_path)},
        created_at=now,
    )
    return {**report, 'project': updated_project, 'report_path': str(report_path)}


def list_project_import_reports(project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return []
    folder = IMPORTS_DIR / _safe_slug(clean_project_id, 'project')
    if not folder.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob('*.json'), key=lambda item: item.stat().st_mtime, reverse=True)[:max(1, limit)]:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                rows.append(data)
        except Exception:
            logger.warning('Could not read Assistant knowledge import report: %s', path)
    return rows
