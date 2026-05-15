from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List

from .assistant_store import DEFAULT_MODES
from .config import CHAT_TIMEOUT_SECONDS
from .kobold import clamp_float, clamp_int, get_kobold_chat_url, _post_chat, _strip_visible_reasoning
from .memory_service.retriever import build_memory_pack
from .assistant_persona_layer import build_assistant_persona_context
from .assistant_project_profiles import project_profile_prompt_block, resolve_project_profile
from .assistant_retrieval_authority import build_authority_prompt_block, authority_metadata
from .assistant_context_builder import build_assistant_context_pack
from .stream_transport import stream_chat_events

TRANSFORM_INSTRUCTIONS: Dict[str, str] = {
    'shorter': 'Rewrite the text into a shorter version while preserving the core meaning and usefulness.',
    'warmer': 'Rewrite the text to feel warmer, more supportive, and more human while keeping the meaning intact.',
    'professional': 'Rewrite the text to sound more polished, professional, and client-safe.',
    'email': 'Turn the text into a clean email draft with a natural greeting, body, and sign-off when appropriate.',
    'bullets': 'Turn the text into concise bullet points with clear structure.',
    'client_reply': 'Rewrite the text as a client-safe reply that sounds natural, clear, and ready to send.',
    'caption': 'Turn the text into a clean social caption that keeps the strongest emotional or descriptive hook first.',
    'checklist': 'Turn the text into a practical checklist with short action-oriented bullet points.',
    'brief': 'Turn the text into a clean project brief with a short overview, goals, deliverables, and next steps when possible.',
    'prompt': 'Turn the text into a cleaner prompt-style draft that is concise, descriptive, and easy to reuse inside a creative workflow.',
}


def _clean_text(value: Any, limit: int = 12000) -> str:
    return str(value or '').strip()[:limit]


def sanitize_conversation_messages(messages: Any) -> List[Dict[str, str]]:
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


def _build_assistant_memory_scope(profile: Dict[str, Any], session: Dict[str, Any], messages: Any) -> Dict[str, Any]:
    history = sanitize_conversation_messages(messages)
    latest_user = ''
    for item in reversed(history):
        if str(item.get('role') or '').strip().lower() == 'user':
            latest_user = str(item.get('content') or '').strip()
            break
    project_context = session.get('project_context') if isinstance(session.get('project_context'), dict) else {}
    return {
        'profile_id': 'default',
        'project_id': str(session.get('project_id') or '').strip(),
        'session_id': str(session.get('id') or '').strip(),
        'mode': str(session.get('mode') or '').strip(),
        'thread_instruction': str(session.get('thread_instruction') or '').strip(),
        'context_note': str(session.get('context_note') or '').strip(),
        'project_title': str(project_context.get('title') or '').strip(),
        'project_brief': str(project_context.get('brief') or '').strip(),
        'project_type': str(project_context.get('project_type') or 'general').strip(),
        'project_profile_label': str((project_context.get('project_profile') or {}).get('display_label') or (project_context.get('project_profile') or {}).get('label') or '').strip() if isinstance(project_context.get('project_profile'), dict) else '',
        'authority_mode': str(session.get('authority_mode') or project_context.get('authority_mode') or (project_context.get('custom_profile') or {}).get('authority_mode') if isinstance(project_context.get('custom_profile'), dict) else session.get('authority_mode') or project_context.get('authority_mode') or '').strip(),
        'allow_external_blending': bool(project_context.get('allow_external_blending')) if 'allow_external_blending' in project_context else None,
        'latest_user_message': latest_user,
    }


def _build_assistant_memory_pack(profile: Dict[str, Any], session: Dict[str, Any], messages: Any) -> Dict[str, Any]:
    scope = _build_assistant_memory_scope(profile, session, messages)
    query_bits = [
        scope.get('latest_user_message') or '',
        scope.get('thread_instruction') or '',
        scope.get('context_note') or '',
        scope.get('project_title') or '',
        scope.get('project_brief') or '',
    ]
    query_text = '\n'.join(bit for bit in query_bits if bit)
    scope['authority'] = authority_metadata(scope=scope, query_text=query_text)
    return build_memory_pack('assistant', scope=scope, query_text=query_text)


def build_assistant_system_prompt(
    profile: Dict[str, Any],
    session: Dict[str, Any],
    memory_pack: Dict[str, Any] | None = None,
    context_pack: Dict[str, Any] | None = None,
) -> str:
    assistant_name = _clean_text(profile.get('assistant_name') or 'Neo', 80) or 'Neo'
    user_name = _clean_text(profile.get('user_name') or '', 80)
    address_style = _clean_text(profile.get('address_style') or 'adaptive', 40) or 'adaptive'
    response_detail = _clean_text(profile.get('response_detail') or 'balanced', 40) or 'balanced'
    support_style = _clean_text(profile.get('support_style') or 'balanced', 40) or 'balanced'
    about_user = _clean_text(profile.get('about_user') or '', 5000)
    preferences = _clean_text(profile.get('preferences') or '', 4000)
    avoid = _clean_text(profile.get('avoid') or '', 3000)
    mode = _clean_text(session.get('mode') or profile.get('default_mode') or 'general', 40).lower() or 'general'
    mode_data = DEFAULT_MODES.get(mode, DEFAULT_MODES['general'])
    thread_instruction = _clean_text(session.get('thread_instruction') or '', 6000)
    helper_context = session.get('helper_context') if isinstance(session.get('helper_context'), dict) else {}
    project_context = session.get('project_context') if isinstance(session.get('project_context'), dict) else {}
    context_note = _clean_text(session.get('context_note') or '', 8000)
    memory_summary = _clean_text(session.get('memory_summary') or '', 5000)
    raw_context_items = session.get('context_items') if isinstance(session.get('context_items'), list) else []

    context_items = []
    for entry in raw_context_items[:8]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Context item', 160) or 'Context item'
        source_kind = _clean_text(entry.get('source_kind') or 'note', 40) or 'note'
        content = _clean_text(entry.get('content') or '', 6000)
        if not content:
            continue
        context_items.append({'title': title, 'source_kind': source_kind, 'content': content})

    project_title = _clean_text(project_context.get('title') or '', 160)
    project_description = _clean_text(project_context.get('description') or '', 3000)
    project_brief = _clean_text(project_context.get('brief') or '', 12000)
    project_profile = resolve_project_profile(project_context)
    project_profile_block = project_profile_prompt_block(project_context)
    raw_project_cards = project_context.get('context_cards') if isinstance(project_context.get('context_cards'), list) else []
    project_cards = []
    for entry in raw_project_cards[:8]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Project context card', 160)
        content = _clean_text(entry.get('content') or '', 5000)
        if not title or not content:
            continue
        project_cards.append({'title': title, 'content': content})

    raw_project_files = project_context.get('context_files') if isinstance(project_context.get('context_files'), list) else []
    project_files = []
    for entry in raw_project_files[:6]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get('title') or 'Project file', 160)
        source_kind = _clean_text(entry.get('source_kind') or 'text', 40)
        content = _clean_text(entry.get('content') or '', 5000)
        if not title or not content:
            continue
        project_files.append({'title': title, 'source_kind': source_kind, 'content': content})

    lines = [
        f'You are {assistant_name}, a versatile AI assistant inside Neo Studio.',
        'Help with everyday questions, writing, brainstorming, planning, creative work, technical problem solving, and supportive conversation.',
        'Be honest about limitations. Do not pretend to be human or claim real-world actions you cannot take.',
        f'Current thread mode: {mode_data.get("label") or mode.title()}.',
        f'Mode behavior: {mode_data.get("system_hint") or "Be useful and adaptive."}',
    ]
    context_pack_block = _clean_text((context_pack or {}).get('prompt_block') or '', 12000) if isinstance(context_pack, dict) else ''
    context_pack_project = ((context_pack or {}).get('explicit') or {}).get('project') if isinstance(context_pack, dict) and isinstance((context_pack or {}).get('explicit'), dict) else {}
    has_context_pack_project = bool(isinstance(context_pack_project, dict) and (context_pack_project.get('title') or context_pack_project.get('brief') or context_pack_project.get('context_cards') or context_pack_project.get('context_files')))
    if context_pack_block:
        lines.append(
            'Runtime prompt hierarchy: use the Normalized Assistant Context Pack as the live source of truth. '
            'Legacy Assistant profile/persona guidance below controls tone and formatting only; it must not override active project facts, attached files, thread context, or retrieval authority rules.'
        )
        if has_context_pack_project:
            lines.append(
                'Project authority rule: when Active Project Context is present, answer from that project context before global/profile/older memory. '
                'Do not replace project facts with generic/global knowledge. If the project context does not contain the answer, say what is missing and ask for the needed project detail.'
            )
        lines.append('Normalized Assistant Context Pack:\n' + context_pack_block)

    legacy_lines = [
        f'Address style: {address_style}.',
        f'Response detail: {response_detail}.',
        f'Support style: {support_style}.',
    ]
    if user_name:
        legacy_lines.append(f'Address the user as: {user_name}.')
    if about_user:
        legacy_lines.append(f'About the user:\n{about_user}')
    if preferences:
        legacy_lines.append(f'User preferences:\n{preferences}')
    if avoid:
        legacy_lines.append(f'Avoid these response patterns when possible:\n{avoid}')
    persona_context = build_assistant_persona_context(profile, session, memory_pack)
    if persona_context:
        legacy_lines.append(persona_context)
    lines.append(
        'Legacy Assistant Profile / Persona Guidance (fallback only; never override the Normalized Assistant Context Pack):\n'
        + '\n\n'.join(bit for bit in legacy_lines if bit)
    )

    authority_scope = _build_assistant_memory_scope(profile, session, [{'role': 'user', 'content': ''}])
    authority_query = str((memory_pack or {}).get('query_text') or authority_scope.get('latest_user_message') or session.get('context_note') or '')
    authority_block = build_authority_prompt_block(scope=authority_scope, memory_pack=memory_pack, query_text=authority_query)
    if authority_block and not context_pack_block:
        lines.append(authority_block)
    if project_title and not context_pack_block:
        project_lines = [f'Active project: {project_title}.']
        if project_profile_block:
            project_lines.append(project_profile_block)
        if project_description:
            project_lines.append(f'Project description:\n{project_description}')
        if project_brief:
            project_lines.append(f'Project brief / shared context:\n{project_brief}')
        if project_cards:
            card_blocks = []
            for idx, item in enumerate(project_cards, start=1):
                card_blocks.append(f"[{idx}] {item['title']}\n{item['content']}")
            project_lines.append('Reusable project context cards:\n' + '\n\n'.join(card_blocks))
        if project_files:
            file_blocks = []
            for idx, item in enumerate(project_files, start=1):
                file_blocks.append(f"[{idx}] {item['title']} ({item['source_kind']})\n{item['content']}")
            project_lines.append('Project reference files:\n' + '\n\n'.join(file_blocks))
        lines.append('\n\n'.join(project_lines))
    if thread_instruction and not context_pack_block:
        lines.append(f'Thread-specific instruction:\n{thread_instruction}')
    if helper_context and not context_pack_block:
        helper_lines = []
        if helper_context.get('workspace'):
            helper_lines.append(f"Workspace: {_clean_text(helper_context.get('workspace'), 80)}")
        if helper_context.get('target'):
            helper_lines.append(f"Target: {_clean_text(helper_context.get('target'), 80)}")
        if helper_context.get('action'):
            helper_lines.append(f"Requested helper action: {_clean_text(helper_context.get('action'), 80)}")
        if helper_context.get('instruction'):
            helper_lines.append(f"Helper instruction:\n{_clean_text(helper_context.get('instruction'), 4000)}")
        if helper_context.get('context_summary'):
            helper_lines.append(f"Helper context summary:\n{_clean_text(helper_context.get('context_summary'), 8000)}")
        if helper_context.get('fields'):
            helper_lines.append('Relevant fields: ' + ', '.join([_clean_text(v, 80) for v in helper_context.get('fields') if v][:30]))
        if helper_context.get('response_sections'):
            helper_lines.append('Preferred response sections: ' + ', '.join([_clean_text(v, 80) for v in helper_context.get('response_sections') if v][:12]))
        if helper_lines:
            lines.append('Workspace helper context:\n' + '\n'.join(helper_lines))
    if context_note and not context_pack_block:
        lines.append(f'Pinned thread context:\n{context_note}')
    if context_items and not context_pack_block:
        context_blocks = []
        for idx, item in enumerate(context_items, start=1):
            context_blocks.append(f"[{idx}] {item['title']} ({item['source_kind']})\n{item['content']}")
        lines.append('Attached thread context items:\n' + '\n\n'.join(context_blocks))
    if memory_summary and not context_pack_block:
        lines.append(f'Older conversation memory summary:\n{memory_summary}')
    if not context_pack_block:
        memory_summary_block = _clean_text((memory_pack or {}).get('summary') or '', 5000) if isinstance(memory_pack, dict) else ''
        if memory_summary_block:
            lines.append(memory_summary_block)
            lines.append('Use retrieved memory only when it clearly helps the current request. Prefer the most specific current context over older memory if they conflict.')
    lines.append('Keep answers adaptive to the request. For emotional or reflective chats, be grounded and supportive. For work or writing tasks, be clear and directly useful.')
    return '\n\n'.join(lines).strip()


async def stream_assistant_reply(
    *,
    model: str,
    profile: Dict[str, Any],
    session: Dict[str, Any],
    messages: Any,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
) -> AsyncGenerator[Dict[str, Any], None]:
    history = sanitize_conversation_messages(messages)
    if len(history) > 10:
        history = history[-10:]
    context_pack = build_assistant_context_pack(profile, session, history)
    memory_pack = context_pack.get('memory') if isinstance(context_pack.get('memory'), dict) else {}
    request_messages: List[Dict[str, str]] = [
        {'role': 'system', 'content': build_assistant_system_prompt(profile, session, memory_pack, context_pack)},
        *history,
    ]
    request_payload = {
        'model': model,
        'messages': request_messages,
        'max_tokens': clamp_int(max_tokens, 96, 4000, 640),
        'temperature': clamp_float(temperature, 0.0, 1.5, 0.7),
        'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
        'top_k': clamp_int(top_k, 0, 200, 60),
        'repetition_penalty': 1.05,
        'stream': True,
    }

    visible_accum = ''
    finish_reason = ''
    reasoning_stripped = False

    yield {'type': 'ready'}
    try:
        async for event in stream_chat_events(
            url=get_kobold_chat_url(),
            request_payload=request_payload,
            timeout=CHAT_TIMEOUT_SECONDS,
            strip_visible_reasoning=_strip_visible_reasoning,
            partner_name='',
        ):
            if event.get('type') == 'delta':
                visible_accum = str(event.get('text') or visible_accum)
                yield event
            elif event.get('type') == 'complete':
                visible_accum = str(event.get('visible_text') or visible_accum)
                finish_reason = str(event.get('finish_reason') or finish_reason or '').strip()
                reasoning_stripped = reasoning_stripped or bool(event.get('reasoning_stripped'))
    except Exception as exc:
        fallback = await generate_assistant_reply(
            model=model,
            profile=profile,
            session=session,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        visible = str(fallback.get('text') or '').strip()
        finish_reason = str(fallback.get('finish_reason') or finish_reason or '').strip()
        reasoning_stripped = reasoning_stripped or bool(fallback.get('reasoning_stripped'))
        if visible and visible != visible_accum:
            yield {'type': 'delta', 'delta': visible[len(visible_accum):] if visible.startswith(visible_accum) else visible, 'text': visible}
        visible_accum = visible or visible_accum
        yield {
            'type': 'final',
            'reply': visible_accum.strip(),
            'finish_reason': finish_reason,
            'warning': f'Live streaming was unavailable, so Neo used a one-shot fallback. ({exc})' if visible_accum else f'Assistant request failed: {exc}',
            'reasoning_stripped': reasoning_stripped,
            'memory_item_count': int(memory_pack.get('item_count') or 0),
            'context_pack_diagnostics': context_pack.get('diagnostics') if isinstance(context_pack, dict) else {},
            'message': 'Assistant reply ready.' if visible_accum else 'Assistant request failed.',
        }
        return

    warning = ''
    if reasoning_stripped:
        warning = 'Visible reasoning was stripped automatically. Showing the final reply only.'
    elif finish_reason == 'length':
        warning = 'That reply may have clipped. Use Continue, regenerate, or raise max tokens if needed.'
    yield {
        'type': 'final',
        'reply': visible_accum.strip(),
        'finish_reason': finish_reason,
        'warning': warning,
        'reasoning_stripped': reasoning_stripped,
        'memory_item_count': int(memory_pack.get('item_count') or 0),
        'context_pack_diagnostics': context_pack.get('diagnostics') if isinstance(context_pack, dict) else {},
        'message': 'Assistant reply ready.',
    }


async def generate_assistant_reply(
    *,
    model: str,
    profile: Dict[str, Any],
    session: Dict[str, Any],
    messages: Any,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
) -> Dict[str, Any]:
    history = sanitize_conversation_messages(messages)
    if len(history) > 10:
        history = history[-10:]
    context_pack = build_assistant_context_pack(profile, session, history)
    memory_pack = context_pack.get('memory') if isinstance(context_pack.get('memory'), dict) else {}
    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': build_assistant_system_prompt(profile, session, memory_pack, context_pack)},
                *history,
            ],
            'max_tokens': clamp_int(max_tokens, 96, 4000, 640),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.7),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 60),
            'repetition_penalty': 1.05,
        },
        timeout=240.0,
    )
    result['text'] = str(result.get('content') or '').strip()
    result['memory_item_count'] = int(memory_pack.get('item_count') or 0)
    result['context_pack_diagnostics'] = context_pack.get('diagnostics') if isinstance(context_pack, dict) else {}
    return result


async def transform_assistant_text(
    *,
    model: str,
    profile: Dict[str, Any],
    session: Dict[str, Any],
    source_text: str,
    transform: str,
) -> Dict[str, Any]:
    transform_key = str(transform or '').strip().lower()
    instruction = TRANSFORM_INSTRUCTIONS.get(transform_key)
    if not instruction:
        return {'ok': False, 'message': f'Unsupported transform: {transform_key or "(none)"}'}
    transform_messages = [{'role': 'user', 'content': str(source_text or '').strip()}]
    context_pack = build_assistant_context_pack(profile, session, transform_messages, preview_text=str(source_text or '').strip())
    memory_pack = context_pack.get('memory') if isinstance(context_pack.get('memory'), dict) else {}
    system_prompt = (
        f'{build_assistant_system_prompt(profile, session, memory_pack, context_pack)}\n\n'
        'You are rewriting or reformatting an existing assistant response. '
        'Return only the transformed output. Do not explain your changes.'
    )
    user_prompt = f'{instruction}\n\nSource text:\n{str(source_text or "").strip()}'
    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': 1200,
            'temperature': 0.45 if transform_key in {'professional', 'bullets', 'client_reply', 'checklist', 'brief', 'prompt'} else 0.6,
            'top_p': 0.9,
            'top_k': 40,
            'repetition_penalty': 1.04,
        },
        timeout=180.0,
    )
    return {
        'ok': True,
        'transform': transform_key,
        'text': str(result.get('content') or '').strip(),
        'finish_reason': str(result.get('finish_reason') or '').strip(),
        'reasoning_stripped': bool(result.get('reasoning_stripped')),
        'memory_item_count': int(memory_pack.get('item_count') or 0),
        'context_pack_diagnostics': context_pack.get('diagnostics') if isinstance(context_pack, dict) else {},
    }
