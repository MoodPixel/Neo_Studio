from __future__ import annotations

import json
import re
from typing import Any

from .kobold import _post_chat, clamp_float, clamp_int

ASSIST_SCHEMAS: dict[str, dict[str, Any]] = {
    'character': {
        'label': 'Character',
        'fields': {
            'name': 'Primary character name.',
            'display_name': 'Friendly display name if different from the base name.',
            'gender': 'Gender label if relevant.',
            'pronouns': 'Pronouns such as he/him, she/her, they/them.',
            'role_tier': 'Story role: main, secondary, or npc.',
            'species': 'Species or race.',
            'designation': 'Archetype, title, or label.',
            'occupation': 'Job, role, or social function.',
            'student_details': 'School or training context if relevant.',
            'hobbies': 'Short comma-separated hobbies or interests.',
            'affiliations': 'Groups, factions, or social ties.',
            'summary': 'One compact overview of who this person is.',
            'appearance': 'Visible appearance details only.',
            'personality': 'Behavioral and emotional traits.',
            'speech_style': 'How they speak.',
            'relationship_notes': 'High-level relationship dynamics only.',
            'canon_notes': 'Continuity notes worth preserving.',
        },
        'mode_guidance': {
            'fill_missing': 'Prioritize empty or weak fields. Do not rewrite strong existing details unless the brief clearly asks for it.',
            'rewrite_current': 'Rewrite and strengthen the current draft while preserving the same core identity and intent.',
        },
    },
    'world': {
        'label': 'World',
        'fields': {
            'name': 'World name.',
            'summary': 'One compact world overview.',
            'realm_type': 'World type or fantasy / sci-fi / modern frame.',
            'calendar_notes': 'Timekeeping or seasonal notes.',
            'lore': 'Core lore foundations.',
            'rules': 'Hard rules, social rules, or system rules.',
            'geography_notes': 'Terrain, regions, climate, travel feel.',
            'society_notes': 'Culture, class, institutions, norms.',
            'faith_notes': 'Belief systems or major spiritual structure.',
            'people_notes': 'Who lives here and how they move through the world.',
            'canon_notes': 'Continuity notes worth preserving.',
        },
        'mode_guidance': {
            'fill_missing': 'Fill gaps and sharpen weak areas while respecting the current concept.',
            'rewrite_current': 'Rewrite the world draft into cleaner, more coherent structured field text while keeping the same core premise.',
        },
    },
    'location': {
        'label': 'Location',
        'fields': {
            'name': 'Location name.',
            'display_name': 'Friendly display label if different from name.',
            'function_label': 'What this place is used for.',
            'location_type': 'Place type such as building, district, shrine, room, alley, campus.',
            'summary': 'One compact overview of the place.',
            'atmosphere': 'Immediate mood and sensory tone.',
            'access_notes': 'Who can enter, reach, or use it.',
            'hazards': 'Risks or danger factors.',
            'rules': 'Place-specific rules or constraints.',
            'public_notes': 'What is obvious to most people.',
            'hidden_truth': 'What is concealed or not immediately visible.',
            'canon_notes': 'Continuity notes worth preserving.',
        },
        'mode_guidance': {
            'fill_missing': 'Add only useful missing structure and avoid disturbing already good details.',
            'rewrite_current': 'Rewrite the place into cleaner, stronger, more scene-usable field text while preserving its identity.',
        },
    },
    'scenario': {
        'label': 'Scenario',
        'fields': {
            'title': 'Scenario title.',
            'tone': 'Tone or emotional flavor.',
            'location_label': 'Human-readable location label only. Do not invent IDs.',
            'objective': 'What the scene is trying to achieve.',
            'premise': 'Core setup for the scenario.',
            'opening_beat': 'First beat that kicks the scene open.',
            'scene_notes': 'Extra scene guidance, escalation, or framing notes.',
        },
        'mode_guidance': {
            'fill_missing': 'Fill missing setup and sharpen weak beats without changing the scenario premise too much.',
            'rewrite_current': 'Rewrite the current scenario into cleaner, more playable field text while preserving the same premise and intent.',
        },
    },
}


def _clean_kind(kind: str) -> str:
    clean = re.sub(r'[^a-z]+', '', str(kind or '').strip().lower())
    if clean not in ASSIST_SCHEMAS:
        raise ValueError('Builder assist is only available for Characters, Worlds, Locations, and Scenarios right now.')
    return clean


def _clean_mode(mode: str) -> str:
    clean = re.sub(r'[^a-z_]+', '', str(mode or '').strip().lower())
    return clean if clean in {'fill_missing', 'rewrite_current'} else 'fill_missing'


def _strip_code_fences(text: str) -> str:
    cleaned = str(text or '').strip()
    cleaned = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    return cleaned.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError('Builder assist returned an empty response.')
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('Builder assist did not return valid JSON.')
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception as exc:
        raise ValueError(f'Builder assist JSON parse failed: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError('Builder assist must return a JSON object.')
    return data


def _normalize_current_record(kind: str, current_record: Any) -> dict[str, Any]:
    allowed = ASSIST_SCHEMAS[kind]['fields']
    current = current_record if isinstance(current_record, dict) else {}
    cleaned: dict[str, Any] = {}
    for key in list(allowed.keys()) + ['id', 'record_id', 'world_id', 'region_id', 'city_id', 'location_id', 'universe_id', 'anchor_type', 'current_location_label']:
        value = current.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = str(value).strip()
    return cleaned


def _sanitize_suggestion(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    allowed = ASSIST_SCHEMAS[kind]['fields']
    clean: dict[str, str] = {}
    for key in allowed:
        value = payload.get(key, '')
        if isinstance(value, list):
            value = ', '.join(str(part).strip() for part in value if str(part).strip())
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value or '').strip()
        clean[key] = value.strip()
    return clean


def _schema_prompt(kind: str) -> str:
    parts = []
    for key, description in ASSIST_SCHEMAS[kind]['fields'].items():
        parts.append(f'- {key}: {description}')
    return '\n'.join(parts)


async def generate_builder_assist(
    kind: str,
    brief: str,
    current_record: dict[str, Any] | None = None,
    *,
    mode: str = 'fill_missing',
    model: str = 'default',
    max_tokens: int = 700,
    temperature: float = 0.35,
    top_p: float = 0.9,
    top_k: int = 40,
) -> dict[str, Any]:
    clean_kind = _clean_kind(kind)
    clean_mode = _clean_mode(mode)
    schema = ASSIST_SCHEMAS[clean_kind]
    current = _normalize_current_record(clean_kind, current_record)
    brief_text = str(brief or '').strip()
    if not brief_text and not current:
        raise ValueError('Add a short brief or load a draft before using builder assist.')

    system_prompt = (
        'You are a structured roleplay builder assistant. '
        'Return only one valid JSON object. '
        'No markdown. No code fences. No commentary. No explanations. '
        'Never invent database IDs, record IDs, or link IDs. '
        'Only use the allowed keys. '
        'If something is unknown, return an empty string for that field. '
        'Write concise but vivid field text that is ready to drop into a form. '
        'Preserve the core concept from the brief and current draft.'
    )
    user_prompt = (
        f"Builder kind: {schema['label']}\n"
        f"Mode: {clean_mode}\n\n"
        "Allowed JSON keys and field intent:\n"
        f"{_schema_prompt(clean_kind)}\n\n"
        "Hard rules:\n"
        "- output valid JSON only\n"
        "- do not include keys outside the allowed list\n"
        "- do not invent IDs or linked record references\n"
        "- do not output arrays unless a value is naturally comma-separated text\n"
        f"- {schema['mode_guidance'][clean_mode]}\n"
        "- keep field text structured and reusable, not chatty\n\n"
        f"Current draft JSON:\n{json.dumps(current, ensure_ascii=False, indent=2)}\n\n"
        f"User brief:\n{brief_text or '(no extra brief provided)'}\n\n"
        "Return JSON now."
    )

    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 160, 1400, 700),
            'temperature': clamp_float(temperature, 0.0, 1.2, 0.35),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'repetition_penalty': 1.08,
        },
        timeout=180.0,
    )
    raw = result.get('content', '')
    parsed = _extract_json_object(raw)
    suggestion = _sanitize_suggestion(clean_kind, parsed)
    updated_fields = [key for key, value in suggestion.items() if str(value or '').strip()]
    return {
        'kind': clean_kind,
        'mode': clean_mode,
        'suggestion': suggestion,
        'updated_fields': updated_fields,
        'finish_reason': result.get('finish_reason', ''),
        'reasoning_stripped': bool(result.get('reasoning_stripped')),
        'raw_content': raw,
    }
