from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


DIAGNOSTIC_SCHEMA = 'assistant_import_diagnostics.v1'


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any, fallback: str = '') -> str:
    return str(value if value is not None else fallback).strip()


def _pct(value: Any) -> int:
    try:
        number = float(value or 0)
    except Exception:
        number = 0.0
    if number <= 1:
        number *= 100
    return max(0, min(100, int(round(number))))


def _quality_label(score: float) -> str:
    if score >= 0.82:
        return 'strong'
    if score >= 0.62:
        return 'usable'
    if score >= 0.42:
        return 'needs_review'
    return 'weak'


def _domain_label(domain: str) -> str:
    labels = {
        'worldbuilding': 'Worldbuilding / lore',
        'client_work': 'Client / freelance work',
        'communication': 'Email / chat communication',
        'project_docs': 'Project documentation',
        'code': 'Code / config / logs',
        'notes': 'Notes / planning',
        'reference': 'Reference material',
        'structured_data': 'Structured data',
    }
    return labels.get(_clean(domain).lower(), _clean(domain, 'General').replace('_', ' ').title())


def _recommended_actions(*, import_type: str, assistant_domain: str, structured_count: int, warnings: list[str], avg_quality: float, entity_count: int) -> list[str]:
    import_type = _clean(import_type).lower()
    assistant_domain = _clean(assistant_domain).lower()
    actions: list[str] = []
    if import_type in {'raw_lore_text', 'markdown_lore'} and structured_count <= 0:
        actions.append('Review extraction: no structured lore records were created from this creative/source text.')
    if assistant_domain == 'client_work' and entity_count <= 0:
        actions.append('Check client/project names: no clear client entities were detected.')
    if assistant_domain == 'communication' and import_type != 'json_schema':
        actions.append('Verify sender/recipient context before relying on this for replies.')
    if assistant_domain == 'code':
        actions.append('Use this as technical reference; do not treat logs/config as user preference memory.')
    if avg_quality < 0.62:
        actions.append('Metadata quality is low; consider re-uploading as structured Markdown or JSON.')
    if warnings:
        actions.append('Open warnings before trusting the import in answers.')
    if not actions:
        actions.append('Import looks usable. Run a quick retrieval test question to confirm answer grounding.')
    return actions[:5]


def build_import_diagnostics(*, report: dict[str, Any], chunks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a compact UI-friendly diagnostics object for an Assistant knowledge import.

    This layer is intentionally domain-global: lore, client briefs, email/chat threads,
    project docs, code/config/logs, notes, references, and JSON/schema imports all use
    the same diagnostic contract so the UI can show consistent evidence quality.
    """
    chunks = chunks or []
    warnings = [str(item) for item in _as_list(report.get('warnings')) if str(item).strip()]
    entities = _as_list(report.get('entities'))
    preparse = report.get('preparse_report') if isinstance(report.get('preparse_report'), dict) else {}
    record_report = report.get('structured_record_report') if isinstance(report.get('structured_record_report'), dict) else {}
    import_type_report = report.get('import_type_report') if isinstance(report.get('import_type_report'), dict) else {}
    priority = report.get('priority_summary') if isinstance(report.get('priority_summary'), dict) else {}
    metadata_quality = report.get('chunk_metadata_quality') if isinstance(report.get('chunk_metadata_quality'), dict) else {}

    avg_quality = float(metadata_quality.get('average') or 0)
    confidence = _pct(report.get('import_confidence') or import_type_report.get('confidence') or 0)
    structured_count = int(report.get('structured_record_count') or len(_as_list(record_report.get('records'))))
    section_count = int(report.get('section_count') or 0)
    chunk_count = int(report.get('chunk_count') or len(chunks))
    entity_count = int(report.get('entity_graph_count') or len(entities))
    relation_count = int(report.get('relationship_graph_count') or 0)

    section_roles: dict[str, int] = {}
    chunk_types: dict[str, int] = {}
    evidence_tiers: dict[str, int] = {}
    for chunk in chunks:
        meta = chunk.get('metadata') if isinstance(chunk, dict) else {}
        if not isinstance(meta, dict):
            continue
        role = _clean(meta.get('section_role') or meta.get('section_role_normalized') or 'body') or 'body'
        ctype = _clean(meta.get('chunk_type') or 'knowledge') or 'knowledge'
        tier = _clean(meta.get('evidence_tier') or 'unknown') or 'unknown'
        section_roles[role] = section_roles.get(role, 0) + 1
        chunk_types[ctype] = chunk_types.get(ctype, 0) + 1
        evidence_tiers[tier] = evidence_tiers.get(tier, 0) + 1

    if not evidence_tiers:
        for tier in _as_list(priority.get('evidence_tiers')):
            key = _clean(tier, 'unknown')
            evidence_tiers[key] = evidence_tiers.get(key, 0) + 1

    import_type = _clean(report.get('import_type') or 'raw_reference_text')
    assistant_domain = _clean(report.get('assistant_domain') or 'reference')
    quality_label = _quality_label(avg_quality)
    risk_flags: list[str] = []
    if confidence < 60:
        risk_flags.append('low_import_confidence')
    if avg_quality < 0.62:
        risk_flags.append('low_metadata_quality')
    if warnings:
        risk_flags.append('warnings_present')
    if chunk_count <= 1 and section_count > 2:
        risk_flags.append('possible_under_chunking')
    if structured_count <= 0 and import_type in {'raw_lore_text', 'markdown_lore', 'client_brief', 'conversation_notes'}:
        risk_flags.append('no_structured_records')

    return {
        'schema': DIAGNOSTIC_SCHEMA,
        'summary': {
            'filename': report.get('filename') or 'Knowledge import',
            'detected_import_type': import_type,
            'detected_domain': assistant_domain,
            'domain_label': _domain_label(assistant_domain),
            'document_kind': report.get('document_kind') or 'knowledge',
            'chunking_strategy': report.get('chunking_strategy') or 'paragraph_chunking',
            'confidence_percent': confidence,
            'quality_label': quality_label,
            'created_at': report.get('created_at') or '',
        },
        'counts': {
            'sections': section_count,
            'chunks': chunk_count,
            'structured_records': structured_count,
            'entities': entity_count,
            'relationships': relation_count,
            'warnings': len(warnings),
        },
        'breakdown': {
            'section_roles': section_roles,
            'chunk_types': chunk_types,
            'evidence_tiers': evidence_tiers,
            'detected_aliases': _as_list(preparse.get('aliases'))[:20],
            'detected_section_titles': _as_list(preparse.get('section_titles'))[:20],
            'detected_record_kinds': _as_list(record_report.get('record_kinds'))[:20],
        },
        'quality': {
            'metadata_quality_average': avg_quality,
            'complete_provenance_count': metadata_quality.get('complete_provenance_count') or 0,
            'with_structured_record_count': metadata_quality.get('with_structured_record_count') or 0,
            'average_truth_priority_rank': priority.get('average_truth_priority_rank') or 0,
            'highest_truth_priority_rank': priority.get('highest_truth_priority_rank') or 0,
            'strict_conflict_count': priority.get('strict_conflict_count') or 0,
        },
        'warnings': warnings[:20],
        'risk_flags': risk_flags,
        'recommended_actions': _recommended_actions(
            import_type=import_type,
            assistant_domain=assistant_domain,
            structured_count=structured_count,
            warnings=warnings,
            avg_quality=avg_quality,
            entity_count=entity_count,
        ),
    }
