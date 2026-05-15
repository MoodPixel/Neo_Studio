from __future__ import annotations

"""Global retrieval test-question generator for Assistant knowledge imports.

Phase 10 purpose:
- Generate domain-aware test questions after a knowledge import/conversion.
- Run lightweight retrieval probes against Assistant memory.
- Surface weak recall before the user trusts the imported context.

This module is intentionally global. Lore/worldbuilding is one supported domain,
but client briefs, communication threads, project docs, code/config/logs, notes,
and raw references all receive test questions too.
"""

import json
import re
from pathlib import Path
from typing import Any

from .assistant_knowledge_ingestion import IMPORTS_DIR, _safe_slug
from .memory_service.retriever import build_memory_pack


MAX_GENERATED_QUESTIONS = 14
DEFAULT_RUN_LIMIT = 10


def _clean(value: Any, limit: int = 240) -> str:
    return ' '.join(str(value or '').split())[:max(20, limit)].strip()


def _slugish(value: Any) -> str:
    raw = str(value or '').strip().lower()
    raw = re.sub(r'[^a-z0-9]+', '_', raw).strip('_')
    return raw[:80] or 'question'


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_import_report(project_id: str, import_id: str) -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    clean_import_id = str(import_id or '').strip()
    if not clean_project_id:
        raise ValueError('No assistant project selected.')
    if not clean_import_id:
        raise ValueError('No import selected for retrieval tests.')
    path = IMPORTS_DIR / _safe_slug(clean_project_id, 'project') / f'{_safe_slug(clean_import_id)}.json'
    if not path.exists():
        raise ValueError('Could not find the selected import report.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Import report is not readable.')
    return data


def _record_labels(report: dict[str, Any], limit: int = 8) -> list[str]:
    records = ((report.get('structured_record_report') or {}).get('records') if isinstance(report.get('structured_record_report'), dict) else [])
    labels: list[str] = []
    for record in _as_list(records):
        if not isinstance(record, dict):
            continue
        label = _clean(record.get('label') or record.get('title') or record.get('id'), 120)
        if label and label.lower() not in {x.lower() for x in labels}:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _section_titles(report: dict[str, Any], limit: int = 8) -> list[str]:
    sections = ((report.get('preparse_report') or {}).get('sections') if isinstance(report.get('preparse_report'), dict) else [])
    titles: list[str] = []
    for section in _as_list(sections):
        if not isinstance(section, dict):
            continue
        title = _clean(section.get('title') or section.get('section_role'), 120)
        if title and title.lower() not in {x.lower() for x in titles}:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def _entity_labels(report: dict[str, Any], limit: int = 8) -> list[str]:
    candidates = []
    candidates.extend(_as_list(report.get('entities')))
    graph = report.get('entity_graph') if isinstance(report.get('entity_graph'), dict) else {}
    candidates.extend(_as_list(graph.get('entities')))
    labels: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get('label') or item.get('display_label') or item.get('id') or item.get('entity_id'), 120)
        if label and label.lower() not in {x.lower() for x in labels}:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _domain_question_templates(domain: str, import_type: str, document_kind: str) -> list[dict[str, Any]]:
    domain = str(domain or 'reference').strip().lower()
    import_type = str(import_type or '').strip().lower()
    document_kind = str(document_kind or '').strip().lower()

    if domain in {'worldbuilding', 'lore', 'universe'} or import_type in {'raw_creative_lore', 'markdown_lore'}:
        return [
            {'kind': 'definition', 'question': 'What is the main concept or entity in this import?', 'expected_chunk_types': ['lore_record', 'structured_record', 'reference_material']},
            {'kind': 'rules', 'question': 'What are the core rules, laws, or limits stated in this lore?', 'expected_chunk_types': ['lore_record', 'project_documentation']},
            {'kind': 'relationships', 'question': 'Which bonds, relationships, factions, or counterpart links are important here?', 'expected_chunk_types': ['lore_record']},
            {'kind': 'conflicts', 'question': 'What warnings, myths, contradictions, or failure cases are mentioned?', 'expected_chunk_types': ['lore_record', 'reference_material']},
        ]
    if domain in {'client_work', 'freelance_business', 'client'} or import_type == 'client_project_data':
        return [
            {'kind': 'brief', 'question': 'What does the client need and what is the requested deliverable?', 'expected_chunk_types': ['client_brief']},
            {'kind': 'scope', 'question': 'What scope, platform, duration, budget, deadline, or assets are mentioned?', 'expected_chunk_types': ['client_brief']},
            {'kind': 'boundaries', 'question': 'What should be clarified before responding or starting work?', 'expected_chunk_types': ['client_brief', 'communication_thread']},
            {'kind': 'response', 'question': 'What facts should be used when writing a reply to this client?', 'expected_chunk_types': ['client_brief', 'communication_thread']},
        ]
    if domain in {'communication', 'email', 'message'} or import_type == 'email_or_message_data':
        return [
            {'kind': 'thread_summary', 'question': 'Who is involved in this conversation and what do they want?', 'expected_chunk_types': ['communication_thread']},
            {'kind': 'latest_ask', 'question': 'What is the latest request or decision in this message thread?', 'expected_chunk_types': ['communication_thread']},
            {'kind': 'reply_context', 'question': 'What context should be preserved when drafting a reply?', 'expected_chunk_types': ['communication_thread']},
            {'kind': 'open_questions', 'question': 'What questions or missing details still need to be clarified?', 'expected_chunk_types': ['communication_thread']},
        ]
    if domain in {'project_docs', 'project_documentation', 'software'} or import_type == 'project_docs':
        return [
            {'kind': 'summary', 'question': 'What is this project document about?', 'expected_chunk_types': ['project_documentation']},
            {'kind': 'requirements', 'question': 'What requirements, guardrails, or implementation rules does it define?', 'expected_chunk_types': ['project_documentation']},
            {'kind': 'workflow', 'question': 'What workflow, phase, or validation steps are listed?', 'expected_chunk_types': ['project_documentation']},
            {'kind': 'risks', 'question': 'What risks, warnings, or mandatory checks are mentioned?', 'expected_chunk_types': ['project_documentation']},
        ]
    if domain in {'technical', 'code', 'logs'} or import_type == 'code_or_config':
        return [
            {'kind': 'purpose', 'question': 'What does this code, config, or log appear to be for?', 'expected_chunk_types': ['code_reference']},
            {'kind': 'paths', 'question': 'What file paths, settings, commands, or keys are important?', 'expected_chunk_types': ['code_reference']},
            {'kind': 'errors', 'question': 'What errors, warnings, or failure signals are present?', 'expected_chunk_types': ['code_reference']},
            {'kind': 'next_step', 'question': 'What should be checked or changed next based on this technical text?', 'expected_chunk_types': ['code_reference']},
        ]
    if domain in {'notes', 'planning'} or import_type == 'conversation_notes':
        return [
            {'kind': 'summary', 'question': 'What are the main notes or decisions in this import?', 'expected_chunk_types': ['note_record']},
            {'kind': 'tasks', 'question': 'What tasks, next steps, or phases are mentioned?', 'expected_chunk_types': ['note_record', 'project_documentation']},
            {'kind': 'decisions', 'question': 'What decisions should be remembered from these notes?', 'expected_chunk_types': ['note_record']},
        ]
    return [
        {'kind': 'summary', 'question': 'What is this imported text mainly about?', 'expected_chunk_types': ['reference_material']},
        {'kind': 'facts', 'question': 'What are the key facts or claims in this import?', 'expected_chunk_types': ['reference_material']},
        {'kind': 'details', 'question': 'What specific names, dates, rules, or requirements are mentioned?', 'expected_chunk_types': ['reference_material']},
        {'kind': 'use', 'question': 'How should this reference be used in future Assistant answers?', 'expected_chunk_types': ['reference_material']},
    ]


def _specific_questions(report: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for label in _record_labels(report, 5):
        questions.append({
            'kind': 'record_lookup',
            'question': f'What does the import say about {label}?',
            'expected_terms': [label],
            'expected_record_label': label,
        })
    for title in _section_titles(report, 4):
        if title.lower() in {'document overview', 'chunk 1', 'section'}:
            continue
        questions.append({
            'kind': 'section_lookup',
            'question': f'What details are stored under the {title} section?',
            'expected_terms': [title],
            'expected_section_title': title,
        })
    for label in _entity_labels(report, 4):
        questions.append({
            'kind': 'entity_lookup',
            'question': f'What context is available for {label}?',
            'expected_terms': [label],
            'expected_entity_label': label,
        })
    return questions


def generate_retrieval_test_questions_from_report(report: dict[str, Any], *, limit: int = MAX_GENERATED_QUESTIONS) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError('Import report is required.')
    domain = str(report.get('assistant_domain') or 'reference').strip() or 'reference'
    import_type = str(report.get('import_type') or 'raw_reference_text').strip() or 'raw_reference_text'
    document_kind = str(report.get('document_kind') or 'knowledge').strip() or 'knowledge'
    base = _domain_question_templates(domain, import_type, document_kind)
    specific = _specific_questions(report)

    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, rows in [('domain_template', base), ('import_specific', specific)]:
        for row in rows:
            if not isinstance(row, dict):
                continue
            q = _clean(row.get('question'), 400)
            if not q:
                continue
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            questions.append({
                'id': f"rtq_{len(questions) + 1:02d}_{_slugish(row.get('kind') or q)}",
                'question': q,
                'kind': str(row.get('kind') or 'general').strip() or 'general',
                'source': source,
                'expected_chunk_types': _as_list(row.get('expected_chunk_types')),
                'expected_terms': _as_list(row.get('expected_terms')),
                'expected_section_title': str(row.get('expected_section_title') or '').strip(),
                'expected_record_label': str(row.get('expected_record_label') or '').strip(),
                'expected_entity_label': str(row.get('expected_entity_label') or '').strip(),
            })
            if len(questions) >= max(1, int(limit or MAX_GENERATED_QUESTIONS)):
                break
        if len(questions) >= max(1, int(limit or MAX_GENERATED_QUESTIONS)):
            break

    return {
        'schema': 'assistant_retrieval_tests.v1',
        'project_id': report.get('project_id') or '',
        'import_id': report.get('import_id') or '',
        'filename': report.get('filename') or '',
        'assistant_domain': domain,
        'import_type': import_type,
        'document_kind': document_kind,
        'question_count': len(questions),
        'questions': questions,
        'notes': [
            'These are retrieval probes, not answer-generation tests.',
            'Run them after import/conversion to verify the right chunks are selected before trusting Assistant answers.',
        ],
    }


def generate_retrieval_test_questions(project_id: str, import_id: str, *, limit: int = MAX_GENERATED_QUESTIONS) -> dict[str, Any]:
    report = _load_import_report(project_id, import_id)
    return generate_retrieval_test_questions_from_report(report, limit=limit)


def _hit_quality(question: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    expected_chunk_types = {str(x).strip() for x in _as_list(question.get('expected_chunk_types')) if str(x).strip()}
    expected_terms = [str(x).strip().lower() for x in _as_list(question.get('expected_terms')) if str(x).strip()]
    selected_types = []
    selected_text = []
    top_score = 0.0
    for item in items[:6]:
        meta = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
        selected_types.append(str(meta.get('chunk_type') or '').strip())
        selected_text.append(str(item.get('document') or ''))
        try:
            top_score = max(top_score, float(item.get('score') or 0.0))
        except Exception:
            pass
    text_blob = '\n'.join(selected_text).lower()
    type_hit = bool(expected_chunk_types & set(selected_types)) if expected_chunk_types else True
    term_hits = [term for term in expected_terms if term and term in text_blob]
    term_hit = bool(term_hits) if expected_terms else True
    item_count = len(items)
    if item_count <= 0:
        status = 'fail'
    elif type_hit and term_hit and item_count >= 2:
        status = 'pass'
    elif type_hit or term_hit:
        status = 'weak'
    else:
        status = 'weak'
    return {
        'status': status,
        'item_count': item_count,
        'top_score': round(top_score, 4),
        'expected_chunk_types': sorted(expected_chunk_types),
        'selected_chunk_types': selected_types[:6],
        'type_hit': type_hit,
        'expected_terms': expected_terms,
        'term_hits': term_hits,
        'term_hit': term_hit,
    }


def run_retrieval_tests(project_id: str, import_id: str, *, questions: list[dict[str, Any]] | None = None, limit: int = DEFAULT_RUN_LIMIT) -> dict[str, Any]:
    report = _load_import_report(project_id, import_id)
    generated = generate_retrieval_test_questions_from_report(report, limit=max(MAX_GENERATED_QUESTIONS, int(limit or DEFAULT_RUN_LIMIT)))
    test_questions = questions if isinstance(questions, list) and questions else generated.get('questions') or []
    test_questions = test_questions[:max(1, int(limit or DEFAULT_RUN_LIMIT))]
    scope = {
        'project_id': str(project_id or '').strip(),
        'project_title': report.get('project_title') or '',
        'project_brief': f"Import {report.get('filename') or ''} / {report.get('import_type') or ''} / {report.get('assistant_domain') or ''}",
        'retrieval_mode': 'focused',
    }
    results: list[dict[str, Any]] = []
    for question in test_questions:
        if not isinstance(question, dict):
            continue
        q = _clean(question.get('question'), 500)
        if not q:
            continue
        pack = build_memory_pack('assistant', scope=scope, query_text=q, retrieval_mode='focused')
        items = pack.get('items') if isinstance(pack.get('items'), list) else []
        quality = _hit_quality(question, items)
        results.append({
            'id': question.get('id') or f'rtq_{len(results) + 1:02d}',
            'question': q,
            'kind': question.get('kind') or 'general',
            'status': quality['status'],
            'quality': quality,
            'selected': [
                {
                    'id': str(item.get('id') or '').strip(),
                    'chunk_type': str(((item.get('metadata') or {}).get('chunk_type') if isinstance(item.get('metadata'), dict) else '') or '').strip(),
                    'section_title': str(((item.get('metadata') or {}).get('section_title') if isinstance(item.get('metadata'), dict) else '') or '').strip(),
                    'structured_record_id': str(((item.get('metadata') or {}).get('structured_record_id') if isinstance(item.get('metadata'), dict) else '') or '').strip(),
                    'score': round(float(item.get('score') or 0.0), 4),
                    'snippet': _clean(item.get('document'), 260),
                }
                for item in items[:4]
            ],
        })
    pass_count = sum(1 for row in results if row.get('status') == 'pass')
    weak_count = sum(1 for row in results if row.get('status') == 'weak')
    fail_count = sum(1 for row in results if row.get('status') == 'fail')
    total = len(results)
    score = round((pass_count + weak_count * 0.45) / max(1, total), 3)
    return {
        'schema': 'assistant_retrieval_tests.v1',
        'project_id': project_id,
        'import_id': import_id,
        'filename': report.get('filename') or '',
        'assistant_domain': report.get('assistant_domain') or 'reference',
        'import_type': report.get('import_type') or 'raw_reference_text',
        'question_count': total,
        'pass_count': pass_count,
        'weak_count': weak_count,
        'fail_count': fail_count,
        'retrieval_health_score': score,
        'status': 'pass' if score >= 0.78 and fail_count == 0 else ('weak' if score >= 0.45 else 'fail'),
        'results': results,
        'recommendations': _recommendations(score=score, weak_count=weak_count, fail_count=fail_count, report=report),
    }


def _recommendations(*, score: float, weak_count: int, fail_count: int, report: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if fail_count:
        out.append('Some probes returned no useful chunks. Re-run conversion or improve section headings/metadata before relying on this import.')
    if weak_count:
        out.append('Some probes are weak. Check chunk type, aliases, and retrieval tags for the imported records.')
    if float(report.get('structured_record_count') or 0) <= 0:
        out.append('No structured records were created. Use Preview records / Convert to records for better recall.')
    if float((report.get('chunk_metadata_quality') or {}).get('average') or 0) < 0.55:
        out.append('Metadata quality is low. Add title, import type, canon/status, and clearer sections.')
    if score >= 0.78 and not fail_count:
        out.append('Retrieval looks healthy. This import is safe to use as grounded Assistant context.')
    return out[:5]
