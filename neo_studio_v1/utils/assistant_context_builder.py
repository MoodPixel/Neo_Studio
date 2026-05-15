from __future__ import annotations

from typing import Any, Dict, List

from .memory_service.retriever import build_memory_pack
from .assistant_repo_indexer import format_repo_context, search_repo_index
from .assistant_project_profiles import project_profile_prompt_block, resolve_project_profile, should_use_repo_index
from .assistant_entity_registry import format_entity_graph_context
from .assistant_retrieval_authority import build_authority_prompt_block, authority_metadata

CONTEXT_PACK_VERSION = 'assistant_context_pack_v2_repo_index'
DEFAULT_NEO_PROJECT_ID = 'neo_studio'


def _clean_text(value: Any, limit: int = 12000) -> str:
    return ' '.join(str(value or '').replace('\r', '\n').split())[:limit].strip()


def _raw_text(value: Any, limit: int = 12000) -> str:
    return str(value or '').strip()[:limit]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _sanitize_messages(messages: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get('role') or 'user').strip().lower()
        if role not in {'user', 'assistant'}:
            continue
        content = str(item.get('content') or '').strip()
        if not content:
            continue
        out.append({'role': role, 'content': content[:50000]})
    return out


def _latest_user_message(messages: Any) -> str:
    for item in reversed(_sanitize_messages(messages)):
        if item.get('role') == 'user':
            return str(item.get('content') or '').strip()
    return ''


def _assistant_scope(profile: Dict[str, Any], session: Dict[str, Any], messages: Any) -> Dict[str, Any]:
    project_context = _safe_dict(session.get('project_context'))
    return {
        'profile_id': str(profile.get('id') or 'default').strip() or 'default',
        'project_id': str(session.get('project_id') or '').strip(),
        'session_id': str(session.get('id') or '').strip(),
        'mode': str(session.get('mode') or profile.get('default_mode') or '').strip(),
        'thread_instruction': str(session.get('thread_instruction') or '').strip(),
        'context_note': str(session.get('context_note') or '').strip(),
        'project_title': str(project_context.get('title') or '').strip(),
        'project_brief': str(project_context.get('brief') or '').strip(),
        'project_type': str(project_context.get('project_type') or 'general').strip(),
        'project_profile_label': str((project_context.get('project_profile') or {}).get('display_label') or (project_context.get('project_profile') or {}).get('label') or '').strip() if isinstance(project_context.get('project_profile'), dict) else '',
        'authority_mode': str(session.get('authority_mode') or project_context.get('authority_mode') or (project_context.get('custom_profile') or {}).get('authority_mode') if isinstance(project_context.get('custom_profile'), dict) else session.get('authority_mode') or project_context.get('authority_mode') or '').strip(),
        'latest_user_message': _latest_user_message(messages),
    }


def _query_text(scope: Dict[str, Any], preview_text: str = '') -> str:
    bits = [
        preview_text,
        scope.get('latest_user_message') or '',
        scope.get('thread_instruction') or '',
        scope.get('context_note') or '',
        scope.get('project_title') or '',
        scope.get('project_brief') or '',
    ]
    return '\n'.join(str(bit).strip() for bit in bits if str(bit or '').strip())


def _context_items(session: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for entry in _safe_list(session.get('context_items'))[:8]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Context item', 160) or 'Context item'
        source_kind = _clean_text(entry.get('source_kind') or 'note', 40) or 'note'
        content = _raw_text(entry.get('content') or '', 6000)
        if content:
            out.append({'title': title, 'source_kind': source_kind, 'content': content})
    return out


def _project_context(session: Dict[str, Any]) -> Dict[str, Any]:
    project_context = _safe_dict(session.get('project_context'))
    cards: List[Dict[str, str]] = []
    for entry in _safe_list(project_context.get('context_cards'))[:8]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Project context card', 160)
        content = _raw_text(entry.get('content') or '', 5000)
        if title and content:
            cards.append({'title': title, 'content': content})
    files: List[Dict[str, str]] = []
    for entry in _safe_list(project_context.get('context_files'))[:6]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Project file', 160)
        source_kind = _clean_text(entry.get('source_kind') or 'text', 40)
        content = _raw_text(entry.get('content') or '', 5000)
        if title and content:
            files.append({'title': title, 'source_kind': source_kind, 'content': content})
    clean_project = {
        'title': _clean_text(project_context.get('title') or '', 160),
        'description': _raw_text(project_context.get('description') or '', 3000),
        'brief': _raw_text(project_context.get('brief') or '', 12000),
        'project_type': _clean_text(project_context.get('project_type') or 'general', 80) or 'general',
        'custom_profile': project_context.get('custom_profile') if isinstance(project_context.get('custom_profile'), dict) else {},
        'context_cards': cards,
        'context_files': files,
    }
    clean_project['project_profile'] = resolve_project_profile(clean_project)
    return clean_project


def _helper_context(session: Dict[str, Any]) -> Dict[str, Any]:
    helper = _safe_dict(session.get('helper_context'))
    if not helper:
        return {}
    return {
        'workspace': _clean_text(helper.get('workspace') or '', 80),
        'target': _clean_text(helper.get('target') or '', 80),
        'action': _clean_text(helper.get('action') or '', 80),
        'instruction': _raw_text(helper.get('instruction') or '', 4000),
        'context_summary': _raw_text(helper.get('context_summary') or '', 8000),
        'fields': [_clean_text(v, 80) for v in _safe_list(helper.get('fields')) if _clean_text(v, 80)][:30],
        'response_sections': [_clean_text(v, 80) for v in _safe_list(helper.get('response_sections')) if _clean_text(v, 80)][:12],
    }


def _section(title: str, content: str, *, priority: int = 50, kind: str = 'context') -> Dict[str, Any] | None:
    clean_title = _clean_text(title, 120)
    clean_content = _raw_text(content, 12000)
    if not clean_title or not clean_content:
        return None
    return {'title': clean_title, 'content': clean_content, 'priority': int(priority), 'kind': kind}


def _format_items(title: str, items: List[Dict[str, str]]) -> str:
    blocks: List[str] = []
    for idx, item in enumerate(items, start=1):
        label = _clean_text(item.get('title') or f'Item {idx}', 160)
        source = _clean_text(item.get('source_kind') or '', 40)
        source_suffix = f' ({source})' if source else ''
        content = _raw_text(item.get('content') or '', 6000)
        if label and content:
            blocks.append(f'[{idx}] {label}{source_suffix}\n{content}')
    return f'{title}:\n' + '\n\n'.join(blocks) if blocks else ''


def _memory_prompt_block(memory_pack: Dict[str, Any]) -> str:
    summary = _raw_text(memory_pack.get('summary') or '', 6000)
    if not summary:
        return ''
    return (
        'Retrieved Assistant Memory and Neo Project Memory:\n'
        f'{summary}\n\n'
        'Use retrieved memory only when it clearly helps the current request. Prefer current thread/project context over older memory when they conflict. '
        'Treat Neo Project memory as technical context, not personal preference.'
    )


def _assemble_prompt_sections(
    *,
    profile: Dict[str, Any],
    session: Dict[str, Any],
    explicit: Dict[str, Any],
    memory_pack: Dict[str, Any],
) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    project = _safe_dict(explicit.get('project'))
    project_lines: List[str] = []
    if project.get('title'):
        project_lines.append(f"Active project: {project.get('title')}.")
    profile_block = project_profile_prompt_block(project)
    if profile_block:
        project_lines.append(profile_block)
    if project.get('description'):
        project_lines.append(f"Project description:\n{project.get('description')}")
    if project.get('brief'):
        project_lines.append(f"Project brief / shared context:\n{project.get('brief')}")
    if project.get('context_cards'):
        project_lines.append(_format_items('Reusable project context cards', project.get('context_cards') or []))
    if project.get('context_files'):
        project_lines.append(_format_items('Project reference files', project.get('context_files') or []))
    project_id = str(session.get('project_id') or '').strip()
    project_type = str(project.get('project_type') or '').strip()
    if project_id and project_type in {'universe', 'custom', 'general'}:
        graph_context = format_entity_graph_context(project_id, q=str(explicit.get('latest_user_message') or ''), limit=14)
        if graph_context:
            project_lines.append(graph_context)
    item = _section('Active Project Context', '\n\n'.join(bit for bit in project_lines if bit), priority=20, kind='project')
    if item:
        sections.append(item)
    authority_scope = _assistant_scope(profile, session, [{'role': 'user', 'content': str(explicit.get('latest_user_message') or '')}])
    authority_block = build_authority_prompt_block(scope=authority_scope, memory_pack=memory_pack, query_text=str(explicit.get('latest_user_message') or ''))
    authority_item = _section('Retrieval Authority Policy', authority_block, priority=22, kind='authority')
    if authority_item:
        sections.append(authority_item)

    helper = _safe_dict(explicit.get('helper'))
    helper_lines: List[str] = []
    for key, label in (('workspace', 'Workspace'), ('target', 'Target'), ('action', 'Requested helper action')):
        if helper.get(key):
            helper_lines.append(f'{label}: {helper.get(key)}')
    if helper.get('instruction'):
        helper_lines.append(f"Helper instruction:\n{helper.get('instruction')}")
    if helper.get('context_summary'):
        helper_lines.append(f"Helper context summary:\n{helper.get('context_summary')}")
    if helper.get('fields'):
        helper_lines.append('Relevant fields: ' + ', '.join(helper.get('fields') or []))
    if helper.get('response_sections'):
        helper_lines.append('Preferred response sections: ' + ', '.join(helper.get('response_sections') or []))
    item = _section('Workspace Helper Context', '\n'.join(helper_lines), priority=25, kind='helper')
    if item:
        sections.append(item)

    context_note = _raw_text(explicit.get('context_note') or '', 8000)
    item = _section('Pinned Thread Context', context_note, priority=30, kind='thread')
    if item:
        sections.append(item)

    context_items = _safe_list(explicit.get('context_items'))
    item = _section('Attached Thread Context Items', _format_items('Attached thread context items', context_items), priority=35, kind='attachment')
    if item:
        sections.append(item)

    older_summary = _raw_text(explicit.get('memory_summary') or '', 5000)
    item = _section('Older Conversation Memory Summary', older_summary, priority=45, kind='summary')
    if item:
        sections.append(item)

    repo_index = _safe_dict(explicit.get('repo_index'))
    repo_block = _raw_text(repo_index.get('prompt_block') or '', 4500)
    item = _section('Relevant Repo Index', repo_block, priority=48, kind='repo_index')
    if item:
        sections.append(item)

    item = _section('Retrieved Memory', _memory_prompt_block(memory_pack), priority=50, kind='retrieval')
    if item:
        sections.append(item)

    sections.sort(key=lambda section: int(section.get('priority') or 50))
    return sections


def assemble_context_prompt_block(context_pack: Dict[str, Any] | None, *, max_chars: int = 9000) -> str:
    if not isinstance(context_pack, dict):
        return ''
    sections = context_pack.get('prompt_sections') if isinstance(context_pack.get('prompt_sections'), list) else []
    blocks: List[str] = []
    used = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = _clean_text(section.get('title') or 'Context', 120)
        content = _raw_text(section.get('content') or '', max_chars)
        if not title or not content:
            continue
        block = f'{title}:\n{content}'
        if used + len(block) + 2 > max_chars:
            remaining = max_chars - used - len(title) - 4
            if remaining <= 200:
                break
            block = f'{title}:\n{content[:remaining].rstrip()}\n[Context clipped]'
        blocks.append(block)
        used += len(block) + 2
        if used >= max_chars:
            break
    return '\n\n'.join(blocks).strip()


def build_assistant_context_pack(
    profile: Dict[str, Any],
    session: Dict[str, Any],
    messages: Any,
    *,
    preview_text: str = '',
) -> Dict[str, Any]:
    """Build the normalized Assistant context pack used before model calls.

    This is intentionally dependency-light and fallback-safe: if memory retrieval
    fails, the explicit thread/project context still flows through the pack.
    """
    clean_profile = profile if isinstance(profile, dict) else {}
    clean_session = session if isinstance(session, dict) else {}
    history = _sanitize_messages(messages)
    scope = _assistant_scope(clean_profile, clean_session, history)
    query_text = _query_text(scope, preview_text=preview_text)
    scope['authority'] = authority_metadata(scope=scope, query_text=query_text)
    active_project = _project_context(clean_session)
    active_project_profile = resolve_project_profile(active_project)

    assistant_pack: Dict[str, Any]
    neo_project_pack: Dict[str, Any]
    retrieval_error = ''
    try:
        assistant_pack = build_memory_pack('assistant', scope=scope, query_text=query_text)
    except Exception as exc:  # defensive: chat must not die because memory is unavailable
        retrieval_error = str(exc)
        assistant_pack = {'summary': '', 'items': [], 'item_count': 0, 'candidate_count': 0, 'diagnostics': {'error': retrieval_error}}
    if bool(active_project_profile.get('repo_index_enabled')):
        try:
            neo_project_scope = {
                **scope,
                'project_id': str(active_project.get('neo_project_id') or DEFAULT_NEO_PROJECT_ID).strip() or DEFAULT_NEO_PROJECT_ID,
                'active_tab': 'assistant',
                'component': 'assistant',
                'project_type': active_project_profile.get('project_type') or 'software',
            }
            neo_project_pack = build_memory_pack('neo_project', scope=neo_project_scope, query_text=query_text)
        except Exception as exc:
            if retrieval_error:
                retrieval_error = f'{retrieval_error}; {exc}'
            else:
                retrieval_error = str(exc)
            neo_project_pack = {'summary': '', 'items': [], 'item_count': 0, 'candidate_count': 0, 'diagnostics': {'error': str(exc)}}
    else:
        neo_project_pack = {'summary': '', 'items': [], 'item_count': 0, 'candidate_count': 0, 'diagnostics': {'skipped': 'project profile does not use software repo memory'}}

    summaries = []
    if assistant_pack.get('summary'):
        summaries.append(str(assistant_pack.get('summary') or '').strip())
    if neo_project_pack.get('summary'):
        summaries.append(str(neo_project_pack.get('summary') or '').strip())
    memory_pack = {
        **assistant_pack,
        'summary': '\n\n'.join(summary for summary in summaries if summary),
        'assistant_memory': assistant_pack,
        'neo_project_memory': neo_project_pack,
        'item_count': int(assistant_pack.get('item_count') or 0) + int(neo_project_pack.get('item_count') or 0),
        'candidate_count': int(assistant_pack.get('candidate_count') or 0) + int(neo_project_pack.get('candidate_count') or 0),
    }

    explicit = {
        'context_note': _raw_text(clean_session.get('context_note') or '', 8000),
        'memory_summary': _raw_text(clean_session.get('memory_summary') or '', 5000),
        'context_items': _context_items(clean_session),
        'project': _project_context(clean_session),
        'helper': _helper_context(clean_session),
    }
    repo_index_payload: Dict[str, Any]
    repo_index_error = ''
    if bool(active_project_profile.get('repo_index_enabled')):
        try:
            repo_index_payload = search_repo_index(query_text, limit=8)
            repo_index_payload['prompt_block'] = format_repo_context(repo_index_payload)
        except Exception as exc:
            repo_index_error = str(exc)
            repo_index_payload = {'version': 'assistant_repo_index_unavailable', 'query': query_text, 'file_count': 0, 'result_count': 0, 'results': [], 'prompt_block': '', 'error': repo_index_error}
    else:
        repo_index_payload = {'version': 'assistant_repo_index_skipped', 'query': query_text, 'file_count': 0, 'result_count': 0, 'results': [], 'prompt_block': '', 'skipped': 'active project profile does not use repo index'}
    explicit['repo_index'] = repo_index_payload
    explicit['project_profile'] = active_project_profile

    prompt_sections = _assemble_prompt_sections(profile=clean_profile, session=clean_session, explicit=explicit, memory_pack=memory_pack)
    project_payload = explicit.get('project') if isinstance(explicit.get('project'), dict) else {}
    project_cards = _safe_list(project_payload.get('context_cards'))
    project_files = _safe_list(project_payload.get('context_files'))
    section_titles = [str(section.get('title') or '').strip() for section in prompt_sections if isinstance(section, dict) and str(section.get('title') or '').strip()]
    context_pack = {
        'version': CONTEXT_PACK_VERSION,
        'scope': scope,
        'project_profile': active_project_profile,
        'query_text': query_text,
        'explicit': explicit,
        'memory': memory_pack,
        'repo_index': repo_index_payload,
        'assistant_memory': assistant_pack,
        'neo_project_memory': neo_project_pack,
        'prompt_sections': prompt_sections,
        'prompt_block': '',
        'diagnostics': {
            'context_pack_version': CONTEXT_PACK_VERSION,
            'retrieval_error': retrieval_error,
            'assistant_items': int(assistant_pack.get('item_count') or 0),
            'assistant_candidate_count': int(assistant_pack.get('candidate_count') or 0),
            'neo_project_items': int(neo_project_pack.get('item_count') or 0),
            'neo_project_candidate_count': int(neo_project_pack.get('candidate_count') or 0),
            'total_memory_items': int(memory_pack.get('item_count') or 0),
            'total_candidate_count': int(memory_pack.get('candidate_count') or 0),
            'section_count': len(prompt_sections),
            'section_titles': section_titles,
            'repo_index_error': repo_index_error,
            'project_profile': active_project_profile.get('display_label') or active_project_profile.get('label') or '',
            'project_type': active_project_profile.get('project_type') or 'general',
            'repo_index_enabled': bool(active_project_profile.get('repo_index_enabled')),
            'repo_index_file_count': int(repo_index_payload.get('file_count') or 0),
            'repo_index_result_count': int(repo_index_payload.get('result_count') or 0),
            'profile_id': scope.get('profile_id') or '',
            'session_id': scope.get('session_id') or '',
            'project_id': scope.get('project_id') or '',
            'project_title': project_payload.get('title') or '',
            'has_active_project_context': bool(project_payload.get('title') or project_payload.get('brief') or project_cards or project_files),
            'context_item_count': len(explicit.get('context_items') or []),
            'project_card_count': len(project_cards),
            'project_file_count': len(project_files),
            'project_card_titles': [str(item.get('title') or '').strip() for item in project_cards if isinstance(item, dict) and str(item.get('title') or '').strip()][:8],
            'project_file_titles': [str(item.get('title') or '').strip() for item in project_files if isinstance(item, dict) and str(item.get('title') or '').strip()][:6],
            'project_file_chars': sum(len(str(item.get('content') or '')) for item in project_files if isinstance(item, dict)),
            'query_chars': len(query_text),
            'prompt_block_chars': 0,
        },
        'summary': memory_pack.get('summary') or '',
        'item_count': memory_pack.get('item_count') or 0,
        'candidate_count': memory_pack.get('candidate_count') or 0,
    }
    context_pack['prompt_block'] = assemble_context_prompt_block(context_pack)
    context_pack['diagnostics']['prompt_block_chars'] = len(str(context_pack.get('prompt_block') or ''))
    context_pack['diagnostics']['prompt_block_present'] = bool(str(context_pack.get('prompt_block') or '').strip())
    return context_pack
