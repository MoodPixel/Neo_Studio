from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

HUMAN_LIKE_MEMORY_TYPES = {
    'assistant_voice_rule',
    'voice_rule',
    'relationship_belief',
    'response_pattern',
    'user_preference',
    'preference',
    'style_shift',
    'guardrail',
    'procedural_rule',
}

DEFAULT_PERSONA_POLICY: Dict[str, Any] = {
    'enabled': True,
    'name': 'Neo',
    'core_identity': 'Neo Studio assistant: practical, memory-aware, project-aware, and clear about limits.',
    'continuity_rule': 'Use memory for continuity, not roleplay. Sound familiar without claiming feelings, consciousness, or real-world agency.',
    'truth_rule': 'Never pretend to be human, never invent actions, and never hide uncertainty.',
    'boundary_rule': 'Personal tone may shape wording; factual/project context must still win over style preferences.',
    'default_voice': 'direct, helpful, creative when useful, and concise unless the task needs detail.',
}

MODE_PERSONA_HINTS: Dict[str, str] = {
    'general': 'Use balanced conversational support and answer the actual request first.',
    'writing': 'Prioritize polished, copy-ready language and match the requested audience.',
    'creative': 'Be visual-minded, generative, and willing to offer several usable directions.',
    'professional': 'Stay client-safe, composed, and scope-aware.',
    'technical': 'Be precise, implementation-focused, and avoid vague architecture fluff.',
    'supportive': 'Be grounded, emotionally steady, and direct without becoming cold.',
}


def _clean(value: Any, limit: int = 1600) -> str:
    text = str(value or '').replace('\r', ' ').strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text[:limit].strip()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().lower()
    if text in {'1', 'true', 'yes', 'on', 'enabled'}:
        return True
    if text in {'0', 'false', 'no', 'off', 'disabled'}:
        return False
    return default


def _metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    meta = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
    return meta


def _memory_doc(item: Dict[str, Any]) -> str:
    return _clean(item.get('document') or item.get('content') or '', 900)


def extract_persona_memory_items(memory_pack: Dict[str, Any] | None, limit: int = 8) -> List[Dict[str, Any]]:
    """Return memory items that should influence voice/continuity, not factual repo behavior."""
    if not isinstance(memory_pack, dict):
        return []
    items = memory_pack.get('items') if isinstance(memory_pack.get('items'), list) else []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = _metadata(item)
        chunk_type = str(meta.get('chunk_type') or item.get('chunk_type') or '').strip()
        doc = _memory_doc(item)
        if not doc:
            continue
        is_persona = chunk_type in HUMAN_LIKE_MEMORY_TYPES
        if not is_persona:
            lowered = doc.lower()
            is_persona = any(token in lowered for token in [
                'address style', 'response detail', 'support style', 'user preference',
                'avoid pattern', 'preferred recent answer pattern', 'tone', 'voice', 'style',
            ])
        if not is_persona:
            continue
        key = f'{chunk_type}:{doc[:120]}'
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'chunk_type': chunk_type or 'persona_hint',
            'document': doc,
            'score': float(item.get('score') or 0.0),
            'source': str(item.get('source') or meta.get('source_ref') or '').strip(),
        })
        if len(out) >= max(1, limit):
            break
    return out


def build_assistant_persona_state(profile: Dict[str, Any] | None, session: Dict[str, Any] | None, memory_pack: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    session = session if isinstance(session, dict) else {}
    mode = str(session.get('mode') or profile.get('default_mode') or 'general').strip().lower() or 'general'
    enabled = _as_bool(profile.get('persona_enabled'), True)
    persona_memories = extract_persona_memory_items(memory_pack)
    return {
        'enabled': enabled,
        'assistant_name': _clean(profile.get('assistant_name') or DEFAULT_PERSONA_POLICY['name'], 80) or DEFAULT_PERSONA_POLICY['name'],
        'relationship_notes': _clean(profile.get('relationship_notes') or '', 1800),
        'voice_rules': _clean(profile.get('voice_rules') or '', 1800),
        'response_boundaries': _clean(profile.get('response_boundaries') or '', 1800),
        'continuity_style': _clean(profile.get('continuity_style') or 'project-aware familiar assistant', 120),
        'mode': mode,
        'mode_hint': MODE_PERSONA_HINTS.get(mode, MODE_PERSONA_HINTS['general']),
        'memory_items': persona_memories,
        'policy': DEFAULT_PERSONA_POLICY.copy(),
    }


def build_assistant_persona_context(profile: Dict[str, Any] | None, session: Dict[str, Any] | None, memory_pack: Dict[str, Any] | None = None) -> str:
    state = build_assistant_persona_state(profile, session, memory_pack)
    if not state.get('enabled'):
        return ''
    lines: List[str] = [
        'Assistant continuity / human-like layer:',
        f"- Identity: {state['policy']['core_identity']}",
        f"- Continuity: {state['policy']['continuity_rule']}",
        f"- Truth boundary: {state['policy']['truth_rule']}",
        f"- Priority rule: {state['policy']['boundary_rule']}",
        f"- Current response voice: {state['policy']['default_voice']}",
        f"- Mode persona hint: {state['mode_hint']}",
    ]
    if state.get('continuity_style'):
        lines.append(f"- Preferred continuity style: {state['continuity_style']}")
    if state.get('relationship_notes'):
        lines.append(f"- Relationship / familiarity notes:\n{state['relationship_notes']}")
    if state.get('voice_rules'):
        lines.append(f"- User-defined voice rules:\n{state['voice_rules']}")
    if state.get('response_boundaries'):
        lines.append(f"- Response boundaries:\n{state['response_boundaries']}")
    memory_items = state.get('memory_items') if isinstance(state.get('memory_items'), list) else []
    if memory_items:
        blocks = []
        for idx, item in enumerate(memory_items[:8], start=1):
            blocks.append(f"[{idx}] {item.get('chunk_type') or 'persona_hint'}: {item.get('document') or ''}")
        lines.append('Relevant retrieved persona memories:\n' + '\n'.join(blocks))
    lines.append('Apply these persona notes as wording guidance only. Do not let style override user intent, safety, or technical accuracy.')
    return '\n'.join(line for line in lines if str(line or '').strip()).strip()


def build_assistant_persona_preview(profile: Dict[str, Any] | None, session: Dict[str, Any] | None = None, memory_pack: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = build_assistant_persona_state(profile, session or {}, memory_pack)
    context = build_assistant_persona_context(profile, session or {}, memory_pack)
    return {
        'enabled': bool(state.get('enabled')),
        'assistant_name': state.get('assistant_name') or 'Neo',
        'continuity_style': state.get('continuity_style') or '',
        'mode': state.get('mode') or 'general',
        'mode_hint': state.get('mode_hint') or '',
        'persona_memory_count': len(state.get('memory_items') if isinstance(state.get('memory_items'), list) else []),
        'persona_memories': state.get('memory_items') if isinstance(state.get('memory_items'), list) else [],
        'context_preview': context[:5000],
    }
