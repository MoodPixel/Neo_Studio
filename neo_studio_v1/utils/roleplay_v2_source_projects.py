from __future__ import annotations

from collections import Counter
from typing import Any

from ..contracts.roleplay_v2_records import build_novel_project_record, build_source_document_record
from .roleplay_v2_foundation import ROLEPLAY_V2_NOVEL_PROJECTS_DIR, ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR
from .storage_io import atomic_write_json, read_json_object


def _project_path(project_id: str):
    return ROLEPLAY_V2_NOVEL_PROJECTS_DIR / f'{str(project_id or "").strip()}.json'



def _source_document_path(document_id: str):
    return ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR / f'{str(document_id or "").strip()}.json'





def _document_extra(doc: dict[str, Any] | None = None) -> dict[str, Any]:
    return doc.get('extra') if isinstance((doc or {}).get('extra'), dict) else {}



def _document_outline(doc: dict[str, Any] | None = None) -> dict[str, Any]:
    extra = _document_extra(doc)
    return {
        'part_arc': str(extra.get('part_arc') or '').strip(),
        'pov': str(extra.get('pov') or '').strip(),
        'tense': str(extra.get('tense') or '').strip(),
        'chapter_goal': str(extra.get('chapter_goal') or '').strip(),
        'author_notes': str(extra.get('author_notes') or '').strip(),
        'draft_status': str(extra.get('draft_status') or '').strip() or 'draft',
    }



def _workspace_stats(docs: list[dict[str, Any]]) -> dict[str, Any]:
    part_arcs = {outline['part_arc'] for outline in (_document_outline(doc) for doc in docs) if outline['part_arc']}
    povs = {outline['pov'] for outline in (_document_outline(doc) for doc in docs) if outline['pov']}
    draft_counter = Counter(outline['draft_status'] for outline in (_document_outline(doc) for doc in docs) if outline['draft_status'])
    chapter_slots = {int(doc.get('chapter_number') or 0) for doc in docs if int(doc.get('chapter_number') or 0) > 0}
    section_slots = {(int(doc.get('chapter_number') or 0), int(doc.get('scene_number') or 0)) for doc in docs if int(doc.get('scene_number') or 0) > 0}
    return {
        'document_count': len(docs),
        'total_characters': sum(len(str(doc.get('raw_text') or '')) for doc in docs),
        'chapter_count': len(chapter_slots),
        'section_count': len(section_slots),
        'part_count': len(part_arcs),
        'pov_count': len(povs),
        'draft_status_counts': dict(sorted(draft_counter.items())),
    }


def create_novel_project(*, title: str, author: str = '', source_language: str = 'en', linked_world_id: str = '', linked_universe_id: str = '', extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = build_novel_project_record(
        title=title,
        author=author,
        source_language=source_language,
        linked_world_id=linked_world_id,
        linked_universe_id=linked_universe_id,
        extra=extra or {},
    )
    ROLEPLAY_V2_NOVEL_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_project_path(str(record.get('id') or '')), record)
    return record



def get_novel_project(project_id: str) -> dict[str, Any] | None:
    return read_json_object(_project_path(project_id), None)



def list_novel_projects() -> list[dict[str, Any]]:
    ROLEPLAY_V2_NOVEL_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_NOVEL_PROJECTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        items.append({
            'id': str(row.get('id') or '').strip(),
            'title': str(row.get('title') or '').strip(),
            'author': str(row.get('author') or '').strip(),
            'chapter_count': int(row.get('chapter_count') or 0),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
            'linked_world_id': str(row.get('linked_world_id') or '').strip(),
            'linked_universe_id': str(row.get('linked_universe_id') or '').strip(),
        })
    items.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    return items



def _list_project_documents(project_id: str) -> list[dict[str, Any]]:
    ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    docs: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        if str(row.get('project_id') or '').strip() != str(project_id or '').strip():
            continue
        docs.append(row)
    docs.sort(key=lambda row: (int(row.get('order_index') or 0), int(row.get('chapter_number') or 0), str(row.get('title') or '')))
    return docs



def save_source_document(*, project_id: str, title: str = '', source_name: str = '', raw_text: str, cleaned_text: str = '', source_format: str = 'text', document_type: str = 'novel_chapter', order_index: int = 0, chapter_number: int = 0, scene_number: int = 0, linked_entity_ids: list[str] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    project = get_novel_project(project_id)
    if not project:
        raise ValueError('Novel project not found.')
    record = build_source_document_record(
        project_id=project_id,
        document_type=document_type,
        title=title,
        source_name=source_name,
        source_format=source_format,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        order_index=order_index,
        chapter_number=chapter_number,
        scene_number=scene_number,
        linked_entity_ids=linked_entity_ids or [],
        extra=extra or {},
    )
    ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_source_document_path(str(record.get('id') or '')), record)
    docs = _list_project_documents(project_id)
    project['chapter_ids'] = [str(doc.get('id') or '').strip() for doc in docs]
    project['chapter_count'] = len(project['chapter_ids'])
    meta = project.get('meta') if isinstance(project.get('meta'), dict) else {}
    meta['updated_at'] = str(record.get('meta', {}).get('updated_at') or meta.get('updated_at') or '')
    project['meta'] = meta
    atomic_write_json(_project_path(project_id), project)
    return record



def get_source_document(document_id: str) -> dict[str, Any] | None:
    return read_json_object(_source_document_path(document_id), None)



def get_project_workspace(project_id: str) -> dict[str, Any]:
    project = get_novel_project(project_id)
    if not project:
        raise ValueError('Novel project not found.')
    docs = _list_project_documents(project_id)
    workspace_docs = []
    for doc in docs:
        outline = _document_outline(doc)
        workspace_docs.append({
            'id': str(doc.get('id') or '').strip(),
            'title': str(doc.get('title') or '').strip(),
            'source_name': str(doc.get('source_name') or '').strip(),
            'document_type': str(doc.get('document_type') or '').strip(),
            'source_format': str(doc.get('source_format') or '').strip(),
            'order_index': int(doc.get('order_index') or 0),
            'chapter_number': int(doc.get('chapter_number') or 0),
            'scene_number': int(doc.get('scene_number') or 0),
            'char_count': len(str(doc.get('raw_text') or '')),
            'updated_at': str((doc.get('meta') or {}).get('updated_at') or ''),
            'part_arc': outline['part_arc'],
            'pov': outline['pov'],
            'tense': outline['tense'],
            'chapter_goal': outline['chapter_goal'],
            'author_notes': outline['author_notes'],
            'draft_status': outline['draft_status'],
        })
    return {
        'project': project,
        'documents': workspace_docs,
        'stats': _workspace_stats(docs),
    }
