from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .library_common import atomic_write_json, ensure_dir, read_json_dict
from .library_constants import DEFAULT_ROOT
from ..contracts.memory_records import build_memory_manifest, normalize_session_index_entry
from .assistant_project_profiles import clean_project_type, resolve_project_profile, sanitize_custom_profile
from .memory_service.assistant_adapter import (
    mark_assistant_project_deleted,
    mark_assistant_session_deleted,
    sync_assistant_profile,
    sync_assistant_project,
    sync_assistant_session,
)

ASSISTANT_ROOT = DEFAULT_ROOT / 'assistant'
SESSIONS_DIR = ASSISTANT_ROOT / 'sessions'
PROJECTS_DIR = ASSISTANT_ROOT / 'projects'
PROFILE_PATH = ASSISTANT_ROOT / 'assistant_profile.json'
SESSIONS_INDEX_PATH = ASSISTANT_ROOT / 'assistant_sessions_index.json'
PROJECTS_INDEX_PATH = ASSISTANT_ROOT / 'assistant_projects_index.json'

DEFAULT_MODES: Dict[str, Dict[str, Any]] = {
    'general': {
        'label': 'General',
        'description': 'Balanced day-to-day help for questions, planning, writing, and conversation.',
        'system_hint': 'Be broadly useful, practical, and adaptive to the user intent.',
        'max_tokens': 640,
        'temperature': 0.70,
        'top_p': 0.92,
        'top_k': 60,
    },
    'writing': {
        'label': 'Writing Help',
        'description': 'Drafting, rewriting, editing, and communication support.',
        'system_hint': 'Prioritize clarity, polish, structure, and audience awareness. Offer stronger rewrites when helpful.',
        'max_tokens': 720,
        'temperature': 0.68,
        'top_p': 0.92,
        'top_k': 55,
    },
    'creative': {
        'label': 'Creative',
        'description': 'Brainstorming, ideation, storytelling, naming, and concept support.',
        'system_hint': 'Be imaginative, generative, and visually minded while staying usable.',
        'max_tokens': 840,
        'temperature': 0.84,
        'top_p': 0.94,
        'top_k': 70,
    },
    'professional': {
        'label': 'Professional',
        'description': 'Client communication, business replies, planning, and presentable writing.',
        'system_hint': 'Stay composed, polished, and business-appropriate. Keep the user credible and clear.',
        'max_tokens': 680,
        'temperature': 0.58,
        'top_p': 0.90,
        'top_k': 50,
    },
    'technical': {
        'label': 'Technical',
        'description': 'Debugging, architecture, implementation thinking, and structured problem solving.',
        'system_hint': 'Favor precise diagnosis, implementation detail, trade-offs, and ordered next steps.',
        'max_tokens': 720,
        'temperature': 0.48,
        'top_p': 0.90,
        'top_k': 45,
    },
    'supportive': {
        'label': 'Supportive',
        'description': 'Warm conversation, venting support, reflection, and low-pressure emotional processing.',
        'system_hint': 'Be warm, grounded, and emotionally steady. Do not pretend to be human or overclaim certainty.',
        'max_tokens': 760,
        'temperature': 0.74,
        'top_p': 0.93,
        'top_k': 60,
    },
}

DEFAULT_PROFILE: Dict[str, Any] = {
    'assistant_name': 'Neo',
    'user_name': '',
    'address_style': 'adaptive',
    'default_mode': 'general',
    'response_detail': 'balanced',
    'support_style': 'balanced',
    'about_user': '',
    'preferences': '',
    'avoid': '',
    'persona_enabled': True,
    'continuity_style': 'project-aware familiar assistant',
    'voice_rules': '',
    'relationship_notes': '',
    'response_boundaries': '',
    'updated_at': '',
}


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _new_id(prefix: str) -> str:
    return f'{prefix}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:8]}'


def ensure_assistant_foundation() -> None:
    ensure_dir(ASSISTANT_ROOT)
    ensure_dir(SESSIONS_DIR)
    ensure_dir(PROJECTS_DIR)
    if not PROFILE_PATH.exists():
        atomic_write_json(PROFILE_PATH, _sanitize_profile({**DEFAULT_PROFILE, 'updated_at': _now_iso()}))
    if not SESSIONS_INDEX_PATH.exists():
        atomic_write_json(SESSIONS_INDEX_PATH, {'sessions': []})
    if not PROJECTS_INDEX_PATH.exists():
        atomic_write_json(PROJECTS_INDEX_PATH, {'projects': []})


def list_modes() -> Dict[str, Dict[str, Any]]:
    return deepcopy(DEFAULT_MODES)


def _sanitize_profile(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    src = data or {}
    mode = str(src.get('default_mode') or DEFAULT_PROFILE['default_mode']).strip().lower()
    if mode not in DEFAULT_MODES:
        mode = DEFAULT_PROFILE['default_mode']
    detail = str(src.get('response_detail') or DEFAULT_PROFILE['response_detail']).strip().lower()
    if detail not in {'concise', 'balanced', 'detailed'}:
        detail = 'balanced'
    address_style = str(src.get('address_style') or DEFAULT_PROFILE['address_style']).strip().lower()
    if address_style not in {'adaptive', 'casual', 'professional', 'friendly', 'minimal'}:
        address_style = 'adaptive'
    support_style = str(src.get('support_style') or DEFAULT_PROFILE['support_style']).strip().lower()
    if support_style not in {'gentle', 'balanced', 'direct'}:
        support_style = 'balanced'
    return {
        'assistant_name': str(src.get('assistant_name') or DEFAULT_PROFILE['assistant_name']).strip()[:80] or DEFAULT_PROFILE['assistant_name'],
        'user_name': str(src.get('user_name') or '').strip()[:80],
        'address_style': address_style,
        'default_mode': mode,
        'response_detail': detail,
        'support_style': support_style,
        'about_user': str(src.get('about_user') or '').strip()[:5000],
        'preferences': str(src.get('preferences') or '').strip()[:4000],
        'avoid': str(src.get('avoid') or '').strip()[:3000],
        'persona_enabled': bool(src.get('persona_enabled')) if isinstance(src.get('persona_enabled'), bool) else str(src.get('persona_enabled') or 'true').strip().lower() not in {'0', 'false', 'no', 'off', 'disabled'},
        'continuity_style': str(src.get('continuity_style') or DEFAULT_PROFILE['continuity_style']).strip()[:120] or DEFAULT_PROFILE['continuity_style'],
        'voice_rules': str(src.get('voice_rules') or '').strip()[:3000],
        'relationship_notes': str(src.get('relationship_notes') or '').strip()[:3000],
        'response_boundaries': str(src.get('response_boundaries') or '').strip()[:3000],
        'updated_at': str(src.get('updated_at') or _now_iso()).strip() or _now_iso(),
    }


def _sanitize_helper_context(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    src = data if isinstance(data, dict) else {}
    fields = [str(item).strip()[:120] for item in (src.get('fields') if isinstance(src.get('fields'), list) else []) if str(item).strip()]
    sections = [str(item).strip()[:120] for item in (src.get('response_sections') if isinstance(src.get('response_sections'), list) else []) if str(item).strip()]
    payload = {
        'workspace': str(src.get('workspace') or '').strip()[:80],
        'target': str(src.get('target') or '').strip()[:80],
        'action': str(src.get('action') or '').strip()[:80],
        'label': str(src.get('label') or '').strip()[:120],
        'instruction': str(src.get('instruction') or '').strip()[:4000],
        'context_summary': str(src.get('context_summary') or '').strip()[:8000],
        'fields': fields[:30],
        'response_sections': sections[:12],
    }
    return payload if any(payload.values()) else {}


def load_profile() -> Dict[str, Any]:
    ensure_assistant_foundation()
    raw = read_json_dict(PROFILE_PATH)
    if not raw:
        raw = _sanitize_profile({**DEFAULT_PROFILE, 'updated_at': _now_iso()})
        atomic_write_json(PROFILE_PATH, raw)
    return _sanitize_profile(raw)


def save_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_assistant_foundation()
    existing = read_json_dict(PROFILE_PATH) or DEFAULT_PROFILE
    payload = _sanitize_profile({**existing, **(data or {}), 'updated_at': _now_iso()})
    atomic_write_json(PROFILE_PATH, payload)
    sync_assistant_profile(payload, source_json_path=str(PROFILE_PATH))
    return payload


def _project_path(project_id: str) -> Path:
    clean = str(project_id or '').strip()
    return PROJECTS_DIR / f'{clean}.json'


def _sanitize_project_context_card(data: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    src = data if isinstance(data, dict) else {}
    title = str(src.get('title') or '').strip()[:160]
    content = str(src.get('content') or '').strip()[:8000]
    if not title or not content:
        return None
    return {
        'id': str(src.get('id') or _new_id('project_ctx')).strip() or _new_id('project_ctx'),
        'title': title,
        'content': content,
        'created_at': str(src.get('created_at') or _now_iso()).strip() or _now_iso(),
        'char_count': len(content),
    }


def _sanitize_project_context_file(data: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    src = data if isinstance(data, dict) else {}
    title = str(src.get('title') or src.get('name') or 'Project file').strip()[:160]
    source_kind = str(src.get('source_kind') or 'text').strip().lower()[:40] or 'text'
    content = str(src.get('content') or '').strip()[:18000]
    if not title or not content:
        return None
    return {
        'id': str(src.get('id') or _new_id('project_file')).strip() or _new_id('project_file'),
        'title': title,
        'source_kind': source_kind,
        'content': content,
        'created_at': str(src.get('created_at') or _now_iso()).strip() or _now_iso(),
        'char_count': len(content),
    }


def _sanitize_project_linked_record(data: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    src = data if isinstance(data, dict) else {}
    title = str(src.get('title') or '').strip()[:160]
    record_type = str(src.get('record_type') or src.get('type') or 'other').strip().lower()[:40] or 'other'
    note = str(src.get('note') or '').strip()[:1200]
    source = str(src.get('source') or '').strip()[:120]
    if not title:
        return None
    return {
        'id': str(src.get('id') or _new_id('project_record')).strip() or _new_id('project_record'),
        'title': title,
        'record_type': record_type,
        'note': note,
        'source': source,
        'created_at': str(src.get('created_at') or _now_iso()).strip() or _now_iso(),
    }


def _sanitize_project(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    src = data if isinstance(data, dict) else {}
    created_at = str(src.get('created_at') or _now_iso()).strip() or _now_iso()
    updated_at = str(src.get('updated_at') or created_at).strip() or created_at
    raw_context_cards = src.get('context_cards') if isinstance(src.get('context_cards'), list) else []
    context_cards = [item for item in (_sanitize_project_context_card(entry) for entry in raw_context_cards if isinstance(entry, dict)) if item][:12]
    raw_context_files = src.get('context_files') if isinstance(src.get('context_files'), list) else []
    context_files = [item for item in (_sanitize_project_context_file(entry) for entry in raw_context_files if isinstance(entry, dict)) if item][:10]
    raw_linked_records = src.get('linked_records') if isinstance(src.get('linked_records'), list) else []
    linked_records = [item for item in (_sanitize_project_linked_record(entry) for entry in raw_linked_records if isinstance(entry, dict)) if item][:40]
    project_type = clean_project_type(src.get('project_type'))
    custom_profile = sanitize_custom_profile(src.get('custom_profile'))
    project = {
        'id': str(src.get('id') or _new_id('assistant_project')).strip() or _new_id('assistant_project'),
        'title': str(src.get('title') or 'New project').strip()[:160] or 'New project',
        'description': str(src.get('description') or '').strip()[:3000],
        'brief': str(src.get('brief') or '').strip()[:12000],
        'project_type': project_type,
        'custom_profile': custom_profile,
        'context_cards': context_cards,
        'context_files': context_files,
        'linked_records': linked_records,
        'created_at': created_at,
        'updated_at': updated_at,
        'thread_count': int(src.get('thread_count') or 0),
    }
    project['project_profile'] = resolve_project_profile(project)
    return project


def _project_thread_counts() -> Dict[str, int]:
    ensure_assistant_foundation()
    index = read_json_dict(SESSIONS_INDEX_PATH)
    rows = index.get('sessions') if isinstance(index.get('sessions'), list) else []
    counts: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        project_id = str(row.get('project_id') or '').strip()
        if not project_id:
            continue
        counts[project_id] = counts.get(project_id, 0) + 1
    return counts


def _write_project(project: Dict[str, Any]) -> Dict[str, Any]:
    counts = _project_thread_counts()
    payload = _sanitize_project({**project, 'updated_at': _now_iso(), 'thread_count': counts.get(str(project.get('id') or '').strip(), 0)})
    project_path = _project_path(payload['id'])
    atomic_write_json(project_path, payload)
    _upsert_project_index(payload)
    sync_assistant_project(payload, source_json_path=str(project_path))
    return payload


def _upsert_project_index(project: Dict[str, Any]) -> None:
    ensure_assistant_foundation()
    index = read_json_dict(PROJECTS_INDEX_PATH)
    rows = index.get('projects') if isinstance(index.get('projects'), list) else []
    counts = _project_thread_counts()
    slim = {
        'id': project['id'],
        'title': project['title'],
        'description': project.get('description') or '',
        'brief': project.get('brief') or '',
        'project_type': project.get('project_type') or 'general',
        'custom_profile': project.get('custom_profile') if isinstance(project.get('custom_profile'), dict) else {},
        'project_profile': project.get('project_profile') if isinstance(project.get('project_profile'), dict) else resolve_project_profile(project),
        'created_at': project['created_at'],
        'updated_at': project['updated_at'],
        'thread_count': counts.get(project['id'], int(project.get('thread_count') or 0)),
    }
    replaced = False
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get('id') or '') == slim['id']:
            out.append(slim)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(slim)
    out.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    atomic_write_json(PROJECTS_INDEX_PATH, {'projects': out})


def _remove_project_index(project_id: str) -> None:
    ensure_assistant_foundation()
    index = read_json_dict(PROJECTS_INDEX_PATH)
    rows = index.get('projects') if isinstance(index.get('projects'), list) else []
    out = [row for row in rows if isinstance(row, dict) and str(row.get('id') or '').strip() != str(project_id or '').strip()]
    atomic_write_json(PROJECTS_INDEX_PATH, {'projects': out})


def list_projects() -> List[Dict[str, Any]]:
    ensure_assistant_foundation()
    index = read_json_dict(PROJECTS_INDEX_PATH)
    rows = index.get('projects') if isinstance(index.get('projects'), list) else []
    counts = _project_thread_counts()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        project = _sanitize_project(row)
        project['thread_count'] = counts.get(project['id'], int(project.get('thread_count') or 0))
        out.append(project)
    return out


def create_project(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_assistant_foundation()
    project = _sanitize_project(data)
    return _write_project(project)


def load_project(project_id: str) -> Dict[str, Any] | None:
    ensure_assistant_foundation()
    path = _project_path(project_id)
    if not path.exists():
        return None
    return _sanitize_project(read_json_dict(path))


def update_project(project_id: str, data: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    ensure_assistant_foundation()
    existing = load_project(project_id)
    if not existing:
        return None
    merged = {**existing, **(data or {}), 'id': existing['id']}
    return _write_project(merged)


def rename_project(project_id: str, title: str, description: str | None = None) -> Dict[str, Any] | None:
    ensure_assistant_foundation()
    path = _project_path(project_id)
    if not path.exists():
        return None
    project = _sanitize_project(read_json_dict(path))
    project['title'] = str(title or '').strip()[:160] or project['title']
    if description is not None:
        project['description'] = str(description or '').strip()[:3000]
    return _write_project(project)


def delete_project(project_id: str) -> bool:
    ensure_assistant_foundation()
    clean_id = str(project_id or '').strip()
    if not clean_id:
        return False
    try:
        for row in list_sessions():
            if str(row.get('project_id') or '').strip() != clean_id:
                continue
            session = load_session(str(row.get('id') or '').strip())
            if not session:
                continue
            session['project_id'] = ''
            _write_session(session)
        path = _project_path(clean_id)
        if path.exists():
            path.unlink()
        _remove_project_index(clean_id)
        mark_assistant_project_deleted(clean_id, source_json_path=str(path))
        return True
    except Exception:
        return False


def _session_path(session_id: str) -> Path:
    clean = str(session_id or '').strip()
    return SESSIONS_DIR / f'{clean}.json'


def _normalize_message(item: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    src = item or {}
    role = str(src.get('role') or 'user').strip().lower()
    if role not in {'user', 'assistant'}:
        return None
    content = str(src.get('content') or '').strip()
    if not content:
        return None
    return {
        'id': str(src.get('id') or _new_id('msg')).strip(),
        'role': role,
        'content': content[:50000],
        'created_at': str(src.get('created_at') or _now_iso()).strip() or _now_iso(),
        'meta': src.get('meta') if isinstance(src.get('meta'), dict) else {},
    }


def _sanitize_context_item(data: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    src = data if isinstance(data, dict) else {}
    content = str(src.get('content') or '').strip()
    if not content:
        return None
    title = str(src.get('title') or src.get('name') or 'Context item').strip()[:160] or 'Context item'
    source_kind = str(src.get('source_kind') or 'note').strip().lower()[:40] or 'note'
    return {
        'id': str(src.get('id') or _new_id('ctx')).strip() or _new_id('ctx'),
        'title': title,
        'source_kind': source_kind,
        'content': content[:18000],
        'created_at': str(src.get('created_at') or _now_iso()).strip() or _now_iso(),
        'char_count': len(content[:18000]),
    }


def _default_session(mode: str = 'general', title: str = 'New assistant chat') -> Dict[str, Any]:
    mode_clean = mode if mode in DEFAULT_MODES else 'general'
    preset = DEFAULT_MODES[mode_clean]
    return {
        'id': _new_id('assistant_session'),
        'title': title,
        'mode': mode_clean,
        'thread_instruction': '',
        'project_id': '',
        'helper_context': {},
        'context_note': '',
        'context_items': [],
        'messages': [],
        'memory_summary': '',
        'memory_updated_at': '',
        'draft': '',
        'params': {
            'max_tokens': int(preset['max_tokens']),
            'temperature': float(preset['temperature']),
            'top_p': float(preset['top_p']),
            'top_k': int(preset['top_k']),
        },
        'created_at': _now_iso(),
        'updated_at': _now_iso(),
    }


def _summarize_session_memory(messages: List[Dict[str, Any]], keep_recent: int = 8) -> str:
    rows = [msg for msg in messages if isinstance(msg, dict) and str(msg.get('content') or '').strip()]
    if len(rows) <= keep_recent:
        return ''
    older = rows[:-keep_recent]
    if not older:
        return ''
    selected: List[Dict[str, Any]] = []
    if len(older) > 10:
        selected.extend(older[:4])
        selected.append({'role': 'system', 'content': f'… {len(older) - 8} earlier messages compressed …'})
        selected.extend(older[-4:])
    else:
        selected.extend(older)
    bullets: List[str] = []
    for entry in selected:
        role = str(entry.get('role') or 'note').strip().lower()
        content = str(entry.get('content') or '').replace('\r', ' ').replace('\n', ' ')
        content = ' '.join(content.split()).strip()
        if not content:
            continue
        if role == 'system':
            bullets.append(content)
            continue
        label = 'User' if role == 'user' else 'Assistant'
        bullets.append(f'- {label}: {content[:220]}{"…" if len(content) > 220 else ""}')
    return '\n'.join(bullets)[:5000]


def _sanitize_session(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    src = data or {}
    mode = str(src.get('mode') or 'general').strip().lower()
    if mode not in DEFAULT_MODES:
        mode = 'general'
    defaults = DEFAULT_MODES[mode]
    raw_messages = src.get('messages') if isinstance(src.get('messages'), list) else []
    messages = [msg for msg in (_normalize_message(item if isinstance(item, dict) else {}) for item in raw_messages) if msg]
    memory_summary = str(src.get('memory_summary') or '').strip()
    if len(messages) > 10:
        memory_summary = _summarize_session_memory(messages)
    else:
        memory_summary = ''
    title = str(src.get('title') or 'New assistant chat').strip()[:160] or 'New assistant chat'
    created_at = str(src.get('created_at') or _now_iso()).strip() or _now_iso()
    updated_at = str(src.get('updated_at') or created_at).strip() or created_at
    preview = ''
    if messages:
        preview = str(messages[-1].get('content') or '').replace('\n', ' ').strip()[:180]
    else:
        preview = str(src.get('draft') or '').replace('\n', ' ').strip()[:180]
    params = src.get('params') if isinstance(src.get('params'), dict) else {}
    helper_context = _sanitize_helper_context(src.get('helper_context'))
    raw_context_items = src.get('context_items') if isinstance(src.get('context_items'), list) else []
    context_items = [item for item in (_sanitize_context_item(entry) for entry in raw_context_items if isinstance(entry, dict)) if item][:8]
    session_id = str(src.get('id') or _new_id('assistant_session')).strip() or _new_id('assistant_session')
    return {
        'id': session_id,
        'title': title,
        'mode': mode,
        'thread_instruction': str(src.get('thread_instruction') or '').strip()[:6000],
        'project_id': str(src.get('project_id') or '').strip()[:160],
        'helper_context': helper_context,
        'context_note': str(src.get('context_note') or '').strip()[:8000],
        'context_items': context_items,
        'messages': messages,
        'draft': str(src.get('draft') or '').rstrip()[:12000],
        'params': {
            'max_tokens': int(float(params.get('max_tokens') or defaults['max_tokens'])),
            'temperature': float(params.get('temperature') if params.get('temperature') is not None else defaults['temperature']),
            'top_p': float(params.get('top_p') if params.get('top_p') is not None else defaults['top_p']),
            'top_k': int(float(params.get('top_k') or defaults['top_k'])),
        },
        'created_at': created_at,
        'updated_at': updated_at,
        'message_count': len(messages),
        'preview': preview,
        'memory_summary': memory_summary,
        'memory_updated_at': _now_iso() if memory_summary else '',
        'memory_manifest': build_memory_manifest(
            lane='assistant',
            scope_type='session',
            scope_id=session_id,
            summary_text=memory_summary,
            message_count=len(messages),
            updated_at=updated_at,
            extra={
                'mode': mode,
                'project_id': str(src.get('project_id') or '').strip(),
            },
        ),
        'pending_continue': bool(src.get('pending_continue')),
        'pending_continue_reason': str(src.get('pending_continue_reason') or '').strip()[:80],
    }


def _write_session(session: Dict[str, Any]) -> Dict[str, Any]:
    payload = _sanitize_session({**session, 'updated_at': _now_iso()})
    session_path = _session_path(payload['id'])
    atomic_write_json(session_path, payload)
    _upsert_session_index(payload)
    sync_assistant_session(payload, source_json_path=str(session_path))
    return payload


def _upsert_session_index(session: Dict[str, Any]) -> None:
    ensure_assistant_foundation()
    index = read_json_dict(SESSIONS_INDEX_PATH)
    rows = index.get('sessions') if isinstance(index.get('sessions'), list) else []
    slim = normalize_session_index_entry('assistant', {
        'id': session['id'],
        'title': session['title'],
        'mode': session['mode'],
        'updated_at': session['updated_at'],
        'created_at': session['created_at'],
        'message_count': int(session.get('message_count') or len(session.get('messages') or [])),
        'preview': str(session.get('preview') or '').strip()[:180],
        'project_id': str(session.get('project_id') or '').strip(),
        'helper_label': str((session.get('helper_context') or {}).get('label') or '').strip()[:120],
        'context_count': int(len(session.get('context_items') or [])),
    })
    replaced = False
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get('id') or '') == slim['id']:
            out.append(slim)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(slim)
    out.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    atomic_write_json(SESSIONS_INDEX_PATH, {'schema_version': 1, 'sessions': out})


def _remove_session_index(session_id: str) -> None:
    ensure_assistant_foundation()
    index = read_json_dict(SESSIONS_INDEX_PATH)
    rows = index.get('sessions') if isinstance(index.get('sessions'), list) else []
    out = [row for row in rows if isinstance(row, dict) and str(row.get('id') or '') != str(session_id or '').strip()]
    atomic_write_json(SESSIONS_INDEX_PATH, {'schema_version': 1, 'sessions': out})


def list_sessions() -> List[Dict[str, Any]]:
    ensure_assistant_foundation()
    index = read_json_dict(SESSIONS_INDEX_PATH)
    rows = index.get('sessions') if isinstance(index.get('sessions'), list) else []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clean = normalize_session_index_entry('assistant', row)
        out.append({
            'id': str(clean.get('id') or '').strip(),
            'title': str(clean.get('title') or 'New assistant chat').strip() or 'New assistant chat',
            'mode': str(clean.get('mode') or 'general').strip() or 'general',
            'updated_at': str(clean.get('updated_at') or '').strip(),
            'created_at': str(clean.get('created_at') or '').strip(),
            'message_count': int(clean.get('message_count') or 0),
            'preview': str(clean.get('preview') or '').strip(),
            'project_id': str(clean.get('project_id') or '').strip(),
            'helper_label': str(clean.get('helper_label') or '').strip(),
            'context_count': int(clean.get('context_count') or 0),
        })
    return out


def load_session(session_id: str) -> Dict[str, Any] | None:
    ensure_assistant_foundation()
    path = _session_path(session_id)
    if not path.exists():
        return None
    return _sanitize_session(read_json_dict(path))


def create_session(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_assistant_foundation()
    profile = load_profile()
    base = _default_session(mode=str((data or {}).get('mode') or profile.get('default_mode') or 'general').strip().lower(), title=str((data or {}).get('title') or 'New assistant chat').strip() or 'New assistant chat')
    merged = _sanitize_session({**base, **(data or {})})
    return _write_session(merged)


def save_session(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_assistant_foundation()
    session_id = str((data or {}).get('id') or '').strip()
    existing = load_session(session_id) if session_id else None
    if existing:
        merged = {**existing, **(data or {})}
    else:
        merged = {**_default_session(mode=str((data or {}).get('mode') or 'general').strip().lower()), **(data or {})}
    return _write_session(merged)


def rename_session(session_id: str, title: str) -> Dict[str, Any] | None:
    session = load_session(session_id)
    if not session:
        return None
    session['title'] = str(title or '').strip()[:160] or session['title']
    return _write_session(session)


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    try:
        if path.exists():
            path.unlink()
        _remove_session_index(session_id)
        mark_assistant_session_deleted(session_id, source_json_path=str(path))
        return True
    except Exception:
        return False
