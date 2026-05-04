
import asyncio
import base64
import json
import mimetypes
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List

import httpx

from .backend_manager import get_effective_base_url
from .config import (
    BACKEND_TIMEOUT_SECONDS,
    CHAT_TIMEOUT_SECONDS,
    DEFAULT_BASE_URL,
    DEFAULT_CHAT_PATH,
    DEFAULT_MODELS_PATH,
)
from .logging_utils import get_logger
from .stream_transport import stream_chat_events

logger = get_logger(__name__)

_LAST_MODELS_FALLBACK_WARNING: dict[str, Any] = {'key': '', 'at': 0.0}


def _normalized_base_url() -> str:
    managed = get_effective_base_url('text')
    if managed:
        return managed.rstrip('/')
    return os.getenv('KOBOLDCPP_BASE_URL', DEFAULT_BASE_URL).strip().rstrip('/') or DEFAULT_BASE_URL


def _build_backend_url(path_value: str, default_path: str) -> str:
    base_url = _normalized_base_url()
    path_value = (path_value or '').strip() or default_path
    if path_value.startswith('http://') or path_value.startswith('https://'):
        return path_value.rstrip('/')
    if not path_value.startswith('/'):
        path_value = '/' + path_value
    return base_url + path_value


def get_kobold_chat_url() -> str:
    return _build_backend_url(os.getenv('KOBOLDCPP_CHAT_PATH', DEFAULT_CHAT_PATH), DEFAULT_CHAT_PATH)


def get_kobold_models_url() -> str:
    return _build_backend_url(os.getenv('KOBOLDCPP_MODELS_PATH', DEFAULT_MODELS_PATH), DEFAULT_MODELS_PATH)


def _should_log_models_fallback(url: str, exc: Exception, window_seconds: float = 600.0) -> bool:
    now = time.time()
    key = f"{url}::{type(exc).__name__}::{str(exc)}"
    if _LAST_MODELS_FALLBACK_WARNING.get('key') == key and (now - float(_LAST_MODELS_FALLBACK_WARNING.get('at') or 0.0)) < float(window_seconds):
        return False
    _LAST_MODELS_FALLBACK_WARNING['key'] = key
    _LAST_MODELS_FALLBACK_WARNING['at'] = now
    return True


async def get_models() -> List[str]:
    models_url = get_kobold_models_url()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(models_url, timeout=BACKEND_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return [m['id'] for m in response.json().get('data', []) if m.get('id')]
            if _should_log_models_fallback(models_url, RuntimeError(f'HTTP {response.status_code}')):
                logger.info('Text backend model list unavailable at %s. Falling back to the default model list. Status: %s', models_url, response.status_code)
    except Exception as exc:
        if _should_log_models_fallback(models_url, exc):
            logger.info('Text backend model list unavailable at %s. Falling back to the default model list. Error: %s', models_url, exc)
    return ['default']


async def probe_backend_status() -> Dict[str, Any]:
    started = time.perf_counter()
    payload: Dict[str, Any] = {
        'base_url': _normalized_base_url(),
        'chat_url': get_kobold_chat_url(),
        'models_url': get_kobold_models_url(),
        'reachable': False,
        'status_code': None,
        'latency_ms': None,
        'models': [],
        'error': '',
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(payload['models_url'], timeout=BACKEND_TIMEOUT_SECONDS)
            payload['status_code'] = response.status_code
            payload['latency_ms'] = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code == 200:
                data = response.json()
                payload['models'] = [m['id'] for m in data.get('data', []) if m.get('id')]
                payload['reachable'] = True
            else:
                payload['error'] = f'Unexpected status code: {response.status_code}'
    except Exception as exc:
        payload['latency_ms'] = round((time.perf_counter() - started) * 1000, 1)
        payload['error'] = str(exc)
        logger.warning('Backend probe failed: %s', exc)
    return payload


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        ivalue = int(float(value))
    except Exception:
        ivalue = default
    return max(minimum, min(maximum, ivalue))



def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        fvalue = float(value)
    except Exception:
        fvalue = default
    return max(minimum, min(maximum, fvalue))


_REASONING_TAGS = ('think', 'analysis', 'reasoning', 'thought', 'scratchpad')


def _truncate_dangling_reasoning_fragment(text: str) -> tuple[str, bool]:
    cleaned = text or ''
    lowered = cleaned.lower()
    last_lt = lowered.rfind('<')
    if last_lt < 0:
        return cleaned, False
    tail = lowered[last_lt:]
    normalized_tail = re.sub(r'\s+', '', tail)
    prefixes = ['<', '</']
    for tag in _REASONING_TAGS:
        prefixes.extend(f'<{tag[:i]}' for i in range(1, len(tag) + 1))
        prefixes.extend(f'</{tag[:i]}' for i in range(1, len(tag) + 1))
    if any(prefix.startswith(normalized_tail) or normalized_tail.startswith(prefix) for prefix in prefixes):
        return cleaned[:last_lt], True
    return cleaned, False


def _sanitize_roleplay_visible_reply(text: str, partner_name: str = '') -> str:
    cleaned = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    cleaned = re.sub(r'<\s*/?\s*(?:' + '|'.join(_REASONING_TAGS) + r')\b[^>]*>', '', cleaned, flags=re.I)
    if (partner_name or '').strip():
        name = re.escape((partner_name or '').strip())
        cleaned = re.sub(rf'^\s*(?:{name})\s*:?[ 	]*\n+', '', cleaned, flags=re.I)
        cleaned = re.sub(rf'^\s*(?:{name})\s*:[ 	]*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'^(?:\s*[A-Z][^\n:]{1,80}:\s*)', '', cleaned, count=1)
    cleaned = re.sub(r'^\s*(?:final\s+answer|answer|final\s+prompt|prompt)\s*:\s*', '', cleaned.strip(), flags=re.I)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _strip_visible_reasoning(text: str, partner_name: str = '') -> Dict[str, Any]:
    raw = text or ''
    cleaned = raw
    had_reasoning = False

    for tag in _REASONING_TAGS:
        pattern = rf'<\s*{tag}\b[^>]*>.*?<\s*/\s*{tag}\s*>'
        updated, count = re.subn(pattern, '', cleaned, flags=re.I | re.S)
        if count:
            had_reasoning = True
            cleaned = updated

    if re.search(r'<\s*(?:' + '|'.join(_REASONING_TAGS) + r')\b', cleaned, flags=re.I):
        had_reasoning = True
        cleaned = re.split(r'<\s*(?:' + '|'.join(_REASONING_TAGS) + r')\b', cleaned, maxsplit=1, flags=re.I)[0]

    cleaned, had_dangling = _truncate_dangling_reasoning_fragment(cleaned)
    had_reasoning = had_reasoning or had_dangling

    if had_reasoning and not cleaned.strip():
        marker = re.search(
            r'(?:^|\n)\s*(?:final\s+answer|answer|final\s+prompt|prompt)\s*:\s*(.+)$',
            raw,
            flags=re.I | re.S,
        )
        if marker:
            cleaned = marker.group(1).strip()

    cleaned = _sanitize_roleplay_visible_reply(cleaned, partner_name=partner_name)
    return {
        'content': cleaned.strip(),
        'had_reasoning': had_reasoning,
        'raw_content': raw,
    }


async def _post_chat(payload: dict, timeout: float = CHAT_TIMEOUT_SECONDS) -> Dict[str, str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(get_kobold_chat_url(), json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get('choices', [{}]) or [{}])[0] or {}
        message = (choice.get('message', {}) or {}).get('content', '').strip()
        finish_reason = str(choice.get('finish_reason') or '').strip()
        reasoning = _strip_visible_reasoning(message, partner_name='')
        return {
            'content': reasoning['content'],
            'finish_reason': finish_reason,
            'raw': data,
            'raw_content': reasoning['raw_content'],
            'reasoning_stripped': reasoning['had_reasoning'],
        }



def _looks_like_sd_tags(text: str) -> bool:
    text = (text or '').strip()
    if not text:
        return False
    if ',' in text and text.count(',') >= 3:
        sentence_punct = len(re.findall(r'[.!?]', text))
        return sentence_punct <= 1
    return False



def _build_prompt_request(idea: str, style: str, custom_instructions: str) -> Dict[str, str]:
    system_prompt = (
        'You write only the final positive image-generation prompt. '
        'Do not output JSON. Do not output a negative prompt. '
        'Do not explain your choices. Never reveal chain-of-thought, scratch work, or <think> tags. '
        'If you reason internally, keep it hidden and output only the final prompt. '
        'Keep it usable immediately.'
    )
    style = (style or 'Stable Diffusion Prompt').strip()
    if style == 'Descriptive':
        style_rule = 'Write a concise, vivid natural-language prompt suitable for an image model.'
    elif style == 'Custom':
        style_rule = 'Follow the user instructions exactly and output only the final positive prompt.'
    elif style == 'Style Convert':
        if _looks_like_sd_tags(idea):
            style_rule = 'Convert the input Stable Diffusion tags into one clean, vivid natural-language prompt. Preserve content and do not invent new elements.'
        else:
            style_rule = 'Convert the input prose into one concise comma-separated Stable Diffusion style prompt. Preserve content and do not invent new elements.'
    else:
        style_rule = 'Write a single-line Stable Diffusion style prompt using concise comma-separated tags.'
    user_prompt = (
        f'Idea: {(idea or "").strip()}\n\n'
        f'{style_rule}\n'
        'Focus on visible subject, clothing, pose, mood, lighting, camera/composition, environment, and style. '
        'Keep it grounded and production-ready.'
    )
    if (custom_instructions or '').strip():
        user_prompt += f"\n\nExtra instructions: {custom_instructions.strip()}"
    return {'system_prompt': system_prompt, 'user_prompt': user_prompt}


_CHARACTER_CARD_LABELS = [
    'Name/Label',
    'Core Traits',
    'Visual Traits',
    'Style Notes',
    'Prompt-Ready Description',
]


def _cleanup_character_card_value(value: str) -> str:
    value = (value or '').replace('\r\n', '\n').replace('\r', '\n').strip().strip('"“”').strip()
    value = re.sub(r'^[\-*•]+\s*', '', value, flags=re.M)
    value = re.sub(r'\n{3,}', '\n\n', value)
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r' *\n *', '\n', value)
    return value.strip()


def _extract_character_card_section(text: str, labels: List[str], aliases: List[str]) -> str:
    escaped_aliases = '|'.join(re.escape(a) for a in aliases)
    escaped_labels = '|'.join(re.escape(l) for l in labels)
    pattern = (
        rf'(?:^|\n)\s*(?:{escaped_aliases})\s*:\s*(.*?)'
        rf'(?=\n\s*(?:{escaped_labels})\s*:|$)'
    )
    match = re.search(pattern, text, flags=re.I | re.S)
    return _cleanup_character_card_value(match.group(1)) if match else ''


def _normalize_character_card_text(text: str) -> str:
    raw = (text or '').strip()
    if not raw:
        return (
            'Name/Label:\nRefined Character\n\n'
            'Core Traits:\n\n'
            'Visual Traits:\n\n'
            'Style Notes:\n\n'
            'Prompt-Ready Description:\n'
        )

    cleaned = raw.replace('\r\n', '\n').replace('\r', '\n')
    cleaned = re.sub(r'^```[a-zA-Z0-9_-]*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```$', '', cleaned)
    cleaned = re.sub(r'^\s*[*#>`-]+\s*', '', cleaned, flags=re.M)
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
    cleaned = re.sub(r"(?im)^here(?: is|'s) my revised prompt\s*:\s*", 'Prompt-Ready Description:\n', cleaned)
    cleaned = re.sub(r'(?im)^revised prompt\s*:\s*', 'Prompt-Ready Description:\n', cleaned)
    cleaned = re.sub(r'(?im)^final prompt\s*:\s*', 'Prompt-Ready Description:\n', cleaned)
    cleaned = re.sub(r'(?im)^prompt\s*:\s*', 'Prompt-Ready Description:\n', cleaned)

    alias_map = {
        'Name/Label': ['Name/Label', 'Name', 'Label', 'Character Name'],
        'Core Traits': ['Core Traits', 'Traits', 'Personality', 'Personality Traits'],
        'Visual Traits': ['Visual Traits', 'Appearance', 'Visual Details', 'Appearance Details'],
        'Style Notes': ['Style Notes', 'Style', 'Mood', 'Style Cues'],
        'Prompt-Ready Description': ['Prompt-Ready Description', 'Prompt Ready Description', 'Revised Prompt', 'Final Prompt', 'Prompt'],
    }

    values: Dict[str, str] = {}
    for label in _CHARACTER_CARD_LABELS:
        values[label] = _extract_character_card_section(cleaned, _CHARACTER_CARD_LABELS, alias_map[label])

    if not values['Prompt-Ready Description']:
        quoted = re.search(r'["“](.+?)["”]', cleaned, flags=re.S)
        if quoted:
            values['Prompt-Ready Description'] = _cleanup_character_card_value(quoted.group(1))

    if not values['Prompt-Ready Description']:
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned) if p.strip()]
        filtered = [
            p for p in paragraphs
            if not re.match(r'(?i)^(the image shows|overall impression|this description captures|let me know if)', p)
        ]
        if filtered:
            values['Prompt-Ready Description'] = _cleanup_character_card_value(filtered[-1])

    if not values['Name/Label']:
        values['Name/Label'] = 'Refined Character'

    return '\n\n'.join(f'{label}:\n{values.get(label, "")}' for label in _CHARACTER_CARD_LABELS).strip()


async def improve_character_card(
    content: str,
    model: str,
    mode: str = '',
    max_tokens: int = 420,
    temperature: float = 0.22,
    top_p: float = 0.9,
    top_k: int = 40,
) -> Dict[str, str]:
    mode_text = (mode or 'Refine this character card while preserving the same identity.').strip()
    system_prompt = (
        'You rewrite character descriptions into a clean reusable character card for image-prompt workflows. '
        'Return only plain text using exactly these section headers in this order: '
        'Name/Label, Core Traits, Visual Traits, Style Notes, Prompt-Ready Description. '
        'Do not output markdown bullets unless they are part of the value text. '
        'Do not explain the image. Do not say "the image shows". '
        'Do not add commentary, introductions, closing lines, or quotes around the final description.'
    )
    user_prompt = (
        'Rewrite the source character content into this exact format:\n\n'
        'Name/Label:\n'
        '<short reusable label>\n\n'
        'Core Traits:\n'
        '<comma-separated personality / vibe traits>\n\n'
        'Visual Traits:\n'
        '<concise visible appearance details>\n\n'
        'Style Notes:\n'
        '<concise style / mood / rendering notes>\n\n'
        'Prompt-Ready Description:\n'
        '<one clean reusable natural-language character description>\n\n'
        f'Extra instruction: {mode_text}\n\n'
        'Rules:\n'
        '- keep the same character identity\n'
        '- keep it reusable for future prompts\n'
        '- no assistant chatter\n'
        '- no "here is" or "let me know" text\n'
        '- no analysis paragraphs\n\n'
        f'Source character content:\n{(content or "").strip()}'
    )
    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 64, 1200, 420),
            'temperature': clamp_float(temperature, 0.0, 1.2, 0.22),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'repetition_penalty': 1.1,
        },
        timeout=180.0,
    )
    result['text'] = _normalize_character_card_text(result.get('content', ''))
    return result



def _sanitize_roleplay_messages(transcript: Any) -> List[Dict[str, str]]:
    clean: List[Dict[str, str]] = []
    for entry in transcript if isinstance(transcript, list) else []:
        role = 'assistant' if str((entry or {}).get('role') or '').strip().lower() == 'assistant' else 'user'
        content = str((entry or {}).get('content') or '').strip()
        if not content:
            continue
        clean.append({'role': role, 'content': content})
    return clean[-16:]


def _is_continuous_scene_mode(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'on', 'yes'}




def _output_shape_contract(output_preset: str = 'roleplay', interaction_mode: str = 'roleplay', *, concise: bool = False) -> str:
    preset = str(output_preset or 'roleplay').strip().lower() or 'roleplay'
    mode = str(interaction_mode or 'roleplay').strip().lower() or 'roleplay'
    contracts = {
        'roleplay': {
            'full': 'Keep the output dialogue-first with light narration. Usually write 1 to 3 short paragraphs or tightly grouped dialogue beats. Keep actions and reactions immediate. Do not drift into broad summary, essay-like exposition, or screenplay formatting.',
            'concise': 'Keep it dialogue-first with light narration, usually 1 to 3 short in-scene paragraphs.',
        },
        'short_story': {
            'full': 'Write compact scene prose with a clear beat arc. Usually write 2 to 4 medium paragraphs with dialogue woven into narration. Keep it shaped and readable, but do not over-expand into chapter-like density.',
            'concise': 'Write compact scene prose in roughly 2 to 4 medium paragraphs with a clear beat arc.',
        },
        'novel': {
            'full': 'Write richer long-form prose with stronger interiority and connective tissue. Usually write 3 to 6 paragraphs with layered description, thought, and dialogue integration. Keep continuity visible and avoid screenplay formatting or abrupt summary compression.',
            'concise': 'Write richer long-form prose in roughly 3 to 6 paragraphs with interiority and continuity carry.',
        },
        'cinematic': {
            'full': 'Write visually staged scene prose with strong blocking, body language, and sensory beats. Prefer short-to-medium paragraphs that feel watchable. Keep interior monologue lighter than novel mode. Do not switch into screenplay sluglines or script formatting unless explicitly asked.',
            'concise': 'Write visually staged scene prose with short-to-medium paragraphs, strong blocking, and lighter interior monologue.',
        },
    }
    contract = contracts.get(preset) or contracts['roleplay']
    base = str(contract.get('concise' if concise else 'full') or '').strip()
    if mode == 'authoring' and base:
        return f'As authored scene text, {base[0].lower() + base[1:]}'
    return base

def _build_roleplay_system_prompt(partner_name: str, style: str, tone: str, interaction_mode: str = 'roleplay', output_preset: str = 'roleplay', continuous_scene_mode: bool = False) -> str:
    partner = (partner_name or 'the scene partner').strip()
    prose_style = (style or 'Immersive dialogue').strip()
    tone_text = (tone or 'Keep the emotional tone grounded and coherent.').strip()
    mode = (interaction_mode or 'roleplay').strip().lower()
    preset = (output_preset or 'roleplay').strip().lower()
    shape_contract = _output_shape_contract(preset, mode, concise=True)
    continuous_rule = ''
    if _is_continuous_scene_mode(continuous_scene_mode):
        continuous_rule = (
            ' Stay inside the current beat and continue moment-by-moment. '
            'Avoid summary transitions, off-screen skips, scene-closing shorthand, or jumping ahead to later outcomes. '
            'Keep actions, reactions, and cause-and-effect visible in sequence.'
        )
    if mode == 'authoring':
        return (
            'You are writing the next part of an ongoing story or scene. '
            'Treat user guidance as author direction unless the input intent explicitly says the text is in-scene material. '
            'Do not quote or mirror author instructions as dialogue unless asked. '
            'Do not explain what you are doing. Do not output JSON. Never reveal chain-of-thought, scratch work, or <think> tags. '
            f'Preferred output style: {prose_style}. Tone target: {tone_text}. Output preset: {preset}. Output-shape contract: {shape_contract}. '
            'Keep continuity with prior text, respect established facts, and continue the current part cleanly.'
            f'{continuous_rule}'
        )
    return (
        f'You are roleplaying as {partner}. Stay in-scene and write only the next in-world reply. '
        'Do not explain what you are doing. Do not output JSON. Do not write as the user. '
        'Never reveal chain-of-thought, scratch work, or <think> tags. '
        f'Preferred reply style: {prose_style}. '
        f'Tone target: {tone_text}. '
        f'Output-shape contract: {shape_contract}. '
        'Keep continuity with prior turns, respect established facts, and keep the pacing natural.'
        f'{continuous_rule}'
    )


def _build_roleplay_setup_block(
    scenario: str,
    user_name: str,
    partner_name: str,
    tone: str,
    style: str,
    scene_notes: str,
    memory_notes: str,
    author_note: str,
    canon_mode: str = '',
    output_preset: str = '',
    interaction_mode: str = 'roleplay',
    input_intent: str = 'auto',
    story_mode: str = 'linear',
    option_count: int = 3,
    allow_custom_option: bool = True,
    story_scope_notes: str = '',
    chapter_scope_notes: str = '',
    part_scope_notes: str = '',
    chapter_index: int = 1,
    chapter_label: str = '',
    part_index: int = 1,
    beat_focus: str = '',
    active_pov: str = '',
    active_location: str = '',
    active_cast_focus: str = '',
    part_objective: str = '',
    tension_level: str = 'medium',
    pacing_target: str = 'steady',
    story_linked_context_text: str = '',
    part_linked_context_text: str = '',
    continuous_scene_mode: bool = False,
) -> str:
    lines = [
        f'Scenario: {(scenario or "").strip() or "Open-ended scene."}',
        f'User character: {(user_name or "You").strip()}',
        f'Scene partner / narrator: {(partner_name or "Scene partner").strip()}',
        f'Tone: {(tone or "Natural and immersive").strip()}',
        f'Reply style: {(style or "Immersive dialogue").strip()}',
    ]
    if (scene_notes or '').strip():
        lines.append(f'Scene notes: {scene_notes.strip()}')
    if (memory_notes or '').strip():
        lines.append(f'Memory / canon notes: {memory_notes.strip()}')
    if (author_note or '').strip():
        lines.append(f'Author note: {author_note.strip()}')
    if (canon_mode or '').strip():
        lines.append(f'Canon guidance: {canon_mode.strip()}')
    if (output_preset or '').strip():
        lines.append(f'Output preset: {output_preset.strip()}')
        lines.append(f'Output-shape contract: {_output_shape_contract(output_preset, interaction_mode, concise=False)}')
    if (interaction_mode or '').strip():
        lines.append(f'Interaction mode: {interaction_mode.strip()}')
    if (input_intent or '').strip():
        lines.append(f'Latest input intent: {input_intent.strip()}')
    if (story_mode or '').strip():
        lines.append(f'Story mode: {story_mode.strip()}')
        if str(story_mode).strip().lower() == 'branching':
            lines.append(f'Branch choices requested per beat: {max(2, min(6, int(option_count or 3)))}')
            lines.append(f'Custom branch choice allowed: {bool(allow_custom_option)}')
    if (story_scope_notes or '').strip():
        lines.append(f'Story scope notes: {story_scope_notes.strip()}')
    if (chapter_scope_notes or '').strip():
        lines.append(f'Chapter scope notes: {chapter_scope_notes.strip()}')
    if (part_scope_notes or '').strip():
        lines.append(f'Part / beat scope notes: {part_scope_notes.strip()}')
    chapter_suffix = f" — {chapter_label.strip()}" if str(chapter_label or '').strip() else ''
    lines.append(f'Current chapter: {max(1, int(chapter_index or 1))}{chapter_suffix}')
    lines.append(f'Current part index: {max(1, int(part_index or 1))}')
    if (beat_focus or '').strip():
        lines.append(f'Beat focus: {beat_focus.strip()}')
    if (active_pov or '').strip():
        lines.append(f'Active POV: {active_pov.strip()}')
    if (active_location or '').strip():
        lines.append(f'Active location focus: {active_location.strip()}')
    if (active_cast_focus or '').strip():
        lines.append(f'Active cast focus: {active_cast_focus.strip()}')
    if (part_objective or '').strip():
        lines.append(f'Part objective: {part_objective.strip()}')
    if (tension_level or '').strip():
        lines.append(f'Tension target: {str(tension_level).strip()}')
    if (pacing_target or '').strip():
        lines.append(f'Pacing target: {str(pacing_target).strip()}')
    if (story_linked_context_text or '').strip():
        lines.append(str(story_linked_context_text).strip())
    if (part_linked_context_text or '').strip():
        lines.append(str(part_linked_context_text).strip())
    if _is_continuous_scene_mode(continuous_scene_mode):
        lines.append('Continuous scene mode: stay on the current beat, avoid summary jumps or off-screen skips, and keep the immediate sequence visible.')
    lines.append('Stay coherent with the active mode, avoid meta commentary, and do not write dialogue for the user unless the input intent asks for it.')
    return '\n'.join(lines)


def _resolve_input_intent(mode: str, interaction_mode: str, input_intent: str) -> str:
    explicit = str(input_intent or '').strip().lower()
    if explicit and explicit != 'auto':
        return explicit
    if str(interaction_mode or '').strip().lower() == 'authoring':
        return 'author_direction'
    return 'in_scene_turn' if str(mode or 'reply').strip().lower() == 'reply' else 'auto'


def _roleplay_task_line(mode: str, interaction_mode: str, resolved_intent: str, canon_mode: str, output_preset: str, continuous_scene_mode: bool = False) -> str:
    mode_clean = (mode or 'reply').strip().lower()
    interaction_clean = (interaction_mode or 'roleplay').strip().lower()
    canon_rule = {
        'follow_exact': 'Stay on canon rails and do not invent major deviations.',
        'follow_until_divergence': 'Stay faithful to canon until a clear divergence point appears.',
        'self_insert': 'Treat the user as an inserted participant inside the canon setup.',
        'what_if': 'Allow altered outcomes while preserving character truth and setting logic.',
    }.get((canon_mode or 'what_if').strip().lower(), '')
    preset_rule = {
        'roleplay': 'Favor dialogue-first turns with tight scene momentum.',
        'short_story': 'Write fuller but still compact scene prose with clearer narrative shape.',
        'novel': 'Lean into richer prose, slower pacing, and stronger interior continuity.',
        'cinematic': 'Favor atmosphere, body language, staging, and visual beats.',
    }.get((output_preset or 'roleplay').strip().lower(), '')
    shape_rule = _output_shape_contract(output_preset, interaction_mode, concise=True)
    if interaction_clean == 'authoring':
        if mode_clean == 'start':
            task_line = 'Open the scene now as the first part of a written scene, following the selected output preset.'
        elif mode_clean == 'continue':
            task_line = 'Continue the current part naturally. Treat any latest user text as author guidance unless the input intent says it is in-scene material.'
        elif resolved_intent in {'story_text', 'in_scene_turn'}:
            task_line = 'Continue the current part and integrate the latest user text as in-scene material.'
        elif resolved_intent == 'canon_update':
            task_line = 'Continue the current part while applying the latest canon update cleanly to continuity.'
        elif resolved_intent == 'rewrite_instruction':
            task_line = 'Continue or lightly revise the current part according to the latest rewrite instruction.'
        else:
            task_line = 'Continue the current part and treat the latest user text as author direction, not spoken dialogue.'
    else:
        if mode_clean == 'start':
            task_line = 'Open the scene now with the first immersive in-character turn.'
        elif mode_clean == 'continue':
            task_line = 'Continue the scene naturally from the current moment. Push it forward without repeating prior lines.'
        else:
            task_line = 'Reply to the latest user turn in character and keep the scene moving.'
    extra_rule = ''
    if _is_continuous_scene_mode(continuous_scene_mode):
        extra_rule = 'Stay on the current beat. Avoid summary jumps, off-screen skips, or fast-forwarded outcomes. Render the next immediate sequence in order.'
    if canon_rule or preset_rule or shape_rule or extra_rule:
        task_line = ' '.join(
            part for part in [
                task_line,
                canon_rule,
                preset_rule,
                f'Output shape: {shape_rule}' if shape_rule else '',
                extra_rule,
            ] if part
        )
    return task_line


def _compiled_packet_text(packet_bundle: dict[str, Any] | None = None) -> str:
    if not isinstance(packet_bundle, dict):
        return ''
    explicit_sections = packet_bundle.get('explicit_sections') if isinstance(packet_bundle.get('explicit_sections'), dict) else {}
    if explicit_sections:
        ordered = [
            str(explicit_sections.get('mode_profile') or '').strip(),
            str(explicit_sections.get('identity') or '').strip(),
            str(explicit_sections.get('scene_state') or '').strip(),
            str(explicit_sections.get('cast') or '').strip(),
            str(explicit_sections.get('retrieval_query') or '').strip(),
            str(explicit_sections.get('world_facts') or '').strip(),
            str(explicit_sections.get('episodic_memories') or '').strip(),
            str(explicit_sections.get('canon_guards') or '').strip(),
            str(explicit_sections.get('callback_anchors') or '').strip(),
            str(explicit_sections.get('relationship_beliefs') or '').strip(),
            str(explicit_sections.get('shared_memories') or '').strip(),
        ]
        rendered = '\n\n'.join(part for part in ordered if part)
        if rendered:
            return rendered[:7000]
    return str(packet_bundle.get('combined_packet') or '').strip()[:7000]


def _retrieved_memory_text(memory_pack: dict[str, Any] | None = None) -> str:
    if not isinstance(memory_pack, dict):
        return ''
    sections = memory_pack.get('sections') if isinstance(memory_pack.get('sections'), dict) else {}
    if sections:
        ordered = [
            str(sections.get('mode_profile') or '').strip(),
            str(sections.get('callback_anchors') or '').strip(),
            str(sections.get('relationship_beliefs') or '').strip(),
            str(sections.get('shared_memories') or '').strip(),
            str(sections.get('episodic_memories') or '').strip(),
            str(sections.get('canon_guards') or '').strip(),
            str(sections.get('world_facts') or '').strip(),
        ]
        rendered = '\n\n'.join(part for part in ordered if part)
        if rendered:
            return rendered[:6000]
    return str(memory_pack.get('summary') or '').strip()[:5000]


def _append_guidance_message(messages: List[Dict[str, str]], user_message: str, resolved_intent: str) -> None:
    prompt = str(user_message or '').strip()
    if not prompt:
        return
    if resolved_intent in {'in_scene_turn', 'story_text'}:
        messages.append({'role': 'user', 'content': prompt})
        return
    if resolved_intent == 'canon_update':
        messages.append({'role': 'user', 'content': f'Canon update / continuity instruction\n{prompt}'})
    elif resolved_intent == 'rewrite_instruction':
        messages.append({'role': 'user', 'content': f'Rewrite / revision instruction\n{prompt}'})
    else:
        messages.append({'role': 'user', 'content': f'Author direction (instruction only; not dialogue)\n{prompt}'})


async def generate_roleplay_reply(
    model: str,
    mode: str,
    scenario: str = '',
    user_name: str = '',
    partner_name: str = '',
    tone: str = '',
    custom_tone: str = '',
    style: str = 'Immersive dialogue',
    user_character_record: Any = None,
    partner_character_record: Any = None,
    world_record: Any = None,
    scenario_record: Any = None,
    location_record: Any = None,
    support_character_records: Any = None,
    cast_items: Any = None,
    scene_notes: str = '',
    memory_notes: str = '',
    author_note: str = '',
    canon_mode: str = 'what_if',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    input_intent: str = 'auto',
    continuous_scene_mode: bool = False,
    story_mode: str = 'linear',
    option_count: int = 3,
    allow_custom_option: bool = True,
    transcript: Any = None,
    user_message: str = '',
    story_scope_notes: str = '',
    chapter_scope_notes: str = '',
    part_scope_notes: str = '',
    chapter_index: int = 1,
    chapter_label: str = '',
    part_index: int = 1,
    beat_focus: str = '',
    active_pov: str = '',
    active_location: str = '',
    active_cast_focus: str = '',
    part_objective: str = '',
    tension_level: str = 'medium',
    pacing_target: str = 'steady',
    story_linked_context_text: str = '',
    part_linked_context_text: str = '',
    max_tokens: int = 320,
    packet_bundle: dict[str, Any] | None = None,
    memory_pack: dict[str, Any] | None = None,
    temperature: float = 0.82,
    top_p: float = 0.92,
    top_k: int = 60,
) -> Dict[str, Any]:
    clean_history = _sanitize_roleplay_messages(transcript)
    effective_tone = (custom_tone or '').strip() if str(tone or '').strip().lower() == 'custom' else (tone or '').strip()
    resolved_intent = _resolve_input_intent(mode, interaction_mode, input_intent)
    continuous_scene_mode = _is_continuous_scene_mode(continuous_scene_mode)
    setup_block = _build_roleplay_setup_block(
        scenario=scenario,
        user_name=user_name,
        partner_name=partner_name,
        tone=effective_tone,
        style=style,
        scene_notes=scene_notes,
        memory_notes=memory_notes,
        author_note=author_note,
        canon_mode=canon_mode,
        output_preset=output_preset,
        interaction_mode=interaction_mode,
        input_intent=resolved_intent,
        story_mode=story_mode,
        option_count=option_count,
        allow_custom_option=allow_custom_option,
        story_scope_notes=story_scope_notes,
        chapter_scope_notes=chapter_scope_notes,
        part_scope_notes=part_scope_notes,
        chapter_index=chapter_index,
        chapter_label=chapter_label,
        part_index=part_index,
        beat_focus=beat_focus,
        active_pov=active_pov,
        active_location=active_location,
        active_cast_focus=active_cast_focus,
        part_objective=part_objective,
        tension_level=tension_level,
        pacing_target=pacing_target,
        story_linked_context_text=story_linked_context_text,
        part_linked_context_text=part_linked_context_text,
    )
    compiled_bundle = packet_bundle or {}
    compiled_context = _compiled_packet_text(compiled_bundle)
    retrieved_memory = _retrieved_memory_text(memory_pack)

    mode_clean = (mode or 'reply').strip().lower()
    task_line = _roleplay_task_line(mode_clean, interaction_mode, resolved_intent, canon_mode, output_preset, continuous_scene_mode=continuous_scene_mode)

    messages: List[Dict[str, str]] = [
        {'role': 'system', 'content': _build_roleplay_system_prompt(partner_name=partner_name, style=style, tone=effective_tone, interaction_mode=interaction_mode, output_preset=output_preset, continuous_scene_mode=continuous_scene_mode)},
        {
            'role': 'user',
            'content': (
                f'Roleplay setup:\n{setup_block}\n\n'
                f'Mode-aware packet sections:\n{compiled_context or setup_block}\n\n'
                f'Retrieved continuity memory sections:\n{retrieved_memory or "(none)"}\n\n'
                f'Task: {task_line}'
            ),
        },
    ]
    messages.extend(clean_history)
    if (user_message or '').strip() and mode_clean in {'reply', 'continue', 'start'}:
        _append_guidance_message(messages, user_message, resolved_intent)
    elif mode_clean == 'continue' and not clean_history:
        messages.append({'role': 'user', 'content': 'No previous transcript exists yet. Start with a brief opening beat that fits the setup.'})

    result = await _post_chat(
        {
            'model': model,
            'messages': messages,
            'max_tokens': clamp_int(max_tokens, 96, 1200, 320),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.82),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
            'top_k': clamp_int(top_k, 0, 200, 60),
            'repetition_penalty': 1.08,
        },
        timeout=180.0,
    )
    result['text'] = (result.get('content') or '').strip()
    result['memory_item_count'] = int((memory_pack or {}).get('item_count') or 0)
    return result



def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or '').strip()
    if not text:
        return None
    candidates = [text]
    if '```' in text:
        parts = text.split('```')
        candidates.extend(part.strip() for idx, part in enumerate(parts) if idx % 2 == 1)
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate.lower().startswith('json'):
            candidate = candidate[4:].strip()
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        start = candidate.find('{')
        end = candidate.rfind('}')
        if start >= 0 and end > start:
            try:
                data = json.loads(candidate[start:end+1])
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


def _fallback_branch_options(raw: str, option_count: int) -> list[dict[str, str]]:
    items = []
    lines = [line.strip(' -*0123456789.)') for line in str(raw or '').splitlines()]
    for line in lines:
        clean = str(line or '').strip()
        if not clean:
            continue
        items.append(clean)
        if len(items) >= option_count:
            break
    return [{'id': f'opt_{idx}', 'label': f'Option {idx}', 'text': text} for idx, text in enumerate(items, start=1)]


async def generate_branch_options(
    model: str,
    scenario: str = '',
    user_name: str = '',
    partner_name: str = '',
    tone: str = '',
    custom_tone: str = '',
    style: str = 'Immersive dialogue',
    user_character_record: Any = None,
    partner_character_record: Any = None,
    world_record: Any = None,
    scenario_record: Any = None,
    location_record: Any = None,
    support_character_records: Any = None,
    cast_items: Any = None,
    scene_notes: str = '',
    memory_notes: str = '',
    author_note: str = '',
    canon_mode: str = 'what_if',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    story_mode: str = 'branching',
    transcript: Any = None,
    story_scope_notes: str = '',
    chapter_scope_notes: str = '',
    part_scope_notes: str = '',
    chapter_index: int = 1,
    chapter_label: str = '',
    part_index: int = 1,
    beat_focus: str = '',
    active_pov: str = '',
    active_location: str = '',
    active_cast_focus: str = '',
    part_objective: str = '',
    tension_level: str = 'medium',
    pacing_target: str = 'steady',
    story_linked_context_text: str = '',
    part_linked_context_text: str = '',
    option_count: int = 3,
    allow_custom_option: bool = True,
    packet_bundle: dict[str, Any] | None = None,
    memory_pack: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    option_count = clamp_int(option_count, 2, 6, 3)
    clean_history = _sanitize_roleplay_messages(transcript)
    effective_tone = (custom_tone or '').strip() if str(tone or '').strip().lower() == 'custom' else (tone or '').strip()
    setup_block = _build_roleplay_setup_block(
        scenario=scenario,
        user_name=user_name,
        partner_name=partner_name,
        tone=effective_tone,
        style=style,
        scene_notes=scene_notes,
        memory_notes=memory_notes,
        author_note=author_note,
        canon_mode=canon_mode,
        output_preset=output_preset,
        interaction_mode=interaction_mode,
        input_intent='branch_options',
        story_mode='branching',
        option_count=option_count,
        allow_custom_option=allow_custom_option,
        story_scope_notes=story_scope_notes,
        chapter_scope_notes=chapter_scope_notes,
        part_scope_notes=part_scope_notes,
        chapter_index=chapter_index,
        chapter_label=chapter_label,
        part_index=part_index,
        beat_focus=beat_focus,
        active_pov=active_pov,
        active_location=active_location,
        active_cast_focus=active_cast_focus,
        part_objective=part_objective,
        tension_level=tension_level,
        pacing_target=pacing_target,
        story_linked_context_text=story_linked_context_text,
        part_linked_context_text=part_linked_context_text,
    )
    compiled_bundle = packet_bundle or {}
    compiled_context = _compiled_packet_text(compiled_bundle)
    retrieved_memory = _retrieved_memory_text(memory_pack)
    messages: List[Dict[str, str]] = [
        {
            'role': 'system',
            'content': 'You generate branching next-step choices for an interactive fiction scene. Return only JSON with shape {"options":[{"id":"opt_1","label":"Option 1","text":"..."}]}. Each option must be short, actionable, distinct, and fit the current canon and beat. Do not include explanations.'
        },
        {
            'role': 'user',
            'content': (
                f'Scene setup:\n{setup_block}\n\n'
                f'Compiled packet:\n{compiled_context or setup_block}\n\n'
                f'Retrieved continuity memory:\n{retrieved_memory or "(none)"}\n\n'
                f'Generate exactly {option_count} distinct next-step choices for the user after the latest assistant reply. Keep them concise and vivid.'
            ),
        },
    ]
    messages.extend(clean_history)
    result = await _post_chat(
        {
            'model': model,
            'messages': messages,
            'max_tokens': 220,
            'temperature': 0.75,
            'top_p': 0.92,
            'top_k': 40,
            'repetition_penalty': 1.04,
        },
        timeout=120.0,
    )
    raw = str(result.get('content') or '').strip()
    parsed = _extract_json_object(raw) or {}
    options = []
    if isinstance(parsed.get('options'), list):
        for idx, item in enumerate(parsed.get('options')[:option_count], start=1):
            if not isinstance(item, dict):
                continue
            text_val = str(item.get('text') or '').strip()
            if not text_val:
                continue
            options.append({
                'id': str(item.get('id') or f'opt_{idx}').strip() or f'opt_{idx}',
                'label': str(item.get('label') or f'Option {idx}').strip() or f'Option {idx}',
                'text': text_val,
            })
    if not options:
        options = _fallback_branch_options(raw, option_count)
    return {'options': options[:option_count], 'raw': raw, 'memory_item_count': int((memory_pack or {}).get('item_count') or 0)}


async def stream_roleplay_reply(
    model: str,
    mode: str,
    scenario: str = '',
    user_name: str = '',
    partner_name: str = '',
    tone: str = '',
    custom_tone: str = '',
    style: str = 'Immersive dialogue',
    user_character_record: Any = None,
    partner_character_record: Any = None,
    world_record: Any = None,
    scenario_record: Any = None,
    location_record: Any = None,
    support_character_records: Any = None,
    cast_items: Any = None,
    scene_notes: str = '',
    memory_notes: str = '',
    author_note: str = '',
    canon_mode: str = 'what_if',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    input_intent: str = 'auto',
    continuous_scene_mode: bool = False,
    story_mode: str = 'linear',
    option_count: int = 3,
    allow_custom_option: bool = True,
    transcript: Any = None,
    user_message: str = '',
    story_scope_notes: str = '',
    chapter_scope_notes: str = '',
    part_scope_notes: str = '',
    chapter_index: int = 1,
    chapter_label: str = '',
    part_index: int = 1,
    beat_focus: str = '',
    active_pov: str = '',
    active_location: str = '',
    active_cast_focus: str = '',
    part_objective: str = '',
    tension_level: str = 'medium',
    pacing_target: str = 'steady',
    story_linked_context_text: str = '',
    part_linked_context_text: str = '',
    max_tokens: int = 320,
    packet_bundle: dict[str, Any] | None = None,
    memory_pack: dict[str, Any] | None = None,
    temperature: float = 0.82,
    top_p: float = 0.92,
    top_k: int = 60,
) -> AsyncGenerator[Dict[str, Any], None]:
    clean_history = _sanitize_roleplay_messages(transcript)
    effective_tone = (custom_tone or '').strip() if str(tone or '').strip().lower() == 'custom' else (tone or '').strip()
    resolved_intent = _resolve_input_intent(mode, interaction_mode, input_intent)
    continuous_scene_mode = _is_continuous_scene_mode(continuous_scene_mode)
    setup_block = _build_roleplay_setup_block(
        scenario=scenario,
        user_name=user_name,
        partner_name=partner_name,
        tone=effective_tone,
        style=style,
        scene_notes=scene_notes,
        memory_notes=memory_notes,
        author_note=author_note,
        canon_mode=canon_mode,
        output_preset=output_preset,
        interaction_mode=interaction_mode,
        input_intent=resolved_intent,
        story_mode=story_mode,
        option_count=option_count,
        allow_custom_option=allow_custom_option,
        story_scope_notes=story_scope_notes,
        chapter_scope_notes=chapter_scope_notes,
        part_scope_notes=part_scope_notes,
        chapter_index=chapter_index,
        chapter_label=chapter_label,
        part_index=part_index,
        beat_focus=beat_focus,
        active_pov=active_pov,
        active_location=active_location,
        active_cast_focus=active_cast_focus,
        part_objective=part_objective,
        tension_level=tension_level,
        pacing_target=pacing_target,
        story_linked_context_text=story_linked_context_text,
        part_linked_context_text=part_linked_context_text,
        continuous_scene_mode=continuous_scene_mode,
    )
    compiled_bundle = packet_bundle or {}
    compiled_context = _compiled_packet_text(compiled_bundle)
    retrieved_memory = _retrieved_memory_text(memory_pack)

    mode_clean = (mode or 'reply').strip().lower()
    task_line = _roleplay_task_line(mode_clean, interaction_mode, resolved_intent, canon_mode, output_preset, continuous_scene_mode=continuous_scene_mode)

    messages: List[Dict[str, str]] = [
        {'role': 'system', 'content': _build_roleplay_system_prompt(partner_name=partner_name, style=style, tone=effective_tone, interaction_mode=interaction_mode, output_preset=output_preset, continuous_scene_mode=continuous_scene_mode)},
        {
            'role': 'user',
            'content': (
                f'Roleplay setup:\n{setup_block}\n\n'
                f'Compiled packet:\n{compiled_context or setup_block}\n\n'
                f'Retrieved continuity memory:\n{retrieved_memory or "(none)"}\n\n'
                f'Task: {task_line}'
            ),
        },
    ]
    messages.extend(clean_history)
    if (user_message or '').strip() and mode_clean in {'reply', 'continue', 'start'}:
        _append_guidance_message(messages, user_message, resolved_intent)
    elif mode_clean == 'continue' and not clean_history:
        messages.append({'role': 'user', 'content': 'No previous transcript exists yet. Start with a brief opening beat that fits the setup.'})

    request_payload = {
        'model': model,
        'messages': messages,
        'max_tokens': clamp_int(max_tokens, 96, 1200, 320),
        'temperature': clamp_float(temperature, 0.0, 1.5, 0.82),
        'top_p': clamp_float(top_p, 0.0, 1.0, 0.92),
        'top_k': clamp_int(top_k, 0, 200, 60),
        'repetition_penalty': 1.08,
        'stream': True,
    }

    visible_accum = ''
    finish_reason = ''
    reasoning_stripped = False
    stream_stalled = False
    fallback_warning = ''

    try:
        async for event in stream_chat_events(
            url=get_kobold_chat_url(),
            request_payload=request_payload,
            timeout=CHAT_TIMEOUT_SECONDS,
            strip_visible_reasoning=_strip_visible_reasoning,
            partner_name=partner_name,
            recover_partial_timeout=True,
            partial_timeout_warning='Upstream stream stalled after partial output. Partial reply recovered.',
            require_stream_payload=True,
        ):
            if event.get('type') == 'delta':
                visible_accum = str(event.get('text') or visible_accum)
                yield event
            elif event.get('type') == 'complete':
                visible_accum = str(event.get('visible_text') or visible_accum)
                finish_reason = str(event.get('finish_reason') or finish_reason or '').strip()
                reasoning_stripped = reasoning_stripped or bool(event.get('reasoning_stripped'))
                stream_stalled = bool(event.get('stream_stalled'))
                fallback_warning = str(event.get('fallback_warning') or fallback_warning)
                if stream_stalled:
                    logger.warning('Roleplay streaming stalled after partial output; finalizing recovered text.')
    except Exception as exc:
        logger.warning('Streaming roleplay reply unavailable, falling back to one-shot reply: %s', exc)
        fallback = await generate_roleplay_reply(
            model=model,
            mode=mode,
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            user_character_record=user_character_record,
            partner_character_record=partner_character_record,
            world_record=world_record,
            scenario_record=scenario_record,
            location_record=location_record,
            support_character_records=support_character_records,
            cast_items=cast_items,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            interaction_mode=interaction_mode,
            input_intent=input_intent,
            continuous_scene_mode=continuous_scene_mode,
            transcript=transcript,
            user_message=user_message,
            story_scope_notes=story_scope_notes,
            chapter_scope_notes=chapter_scope_notes,
            part_scope_notes=part_scope_notes,
            story_linked_context_text=story_linked_context_text,
            part_linked_context_text=part_linked_context_text,
            max_tokens=max_tokens,
            packet_bundle=packet_bundle,
            memory_pack=memory_pack,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        visible_accum = _sanitize_roleplay_visible_reply(str(fallback.get('text') or '').strip(), partner_name=partner_name)
        finish_reason = str(fallback.get('finish_reason') or '').strip()
        reasoning_stripped = bool(fallback.get('reasoning_stripped'))
        if visible_accum:
            yield {'type': 'delta', 'delta': visible_accum, 'text': visible_accum}

    warning = fallback_warning
    if reasoning_stripped and not visible_accum.strip():
        warning = 'Visible reasoning was stripped, but no final in-scene reply came back. Raise max tokens or use a non-thinking preset.'
    elif stream_stalled and visible_accum.strip() and not warning:
        warning = 'Upstream stream stalled after partial output. Continue cut-off to keep going from the recovered reply.'
    elif finish_reason == 'length' and not warning:
        warning = 'That turn may have clipped. Regenerate, Continue cut-off, or raise max tokens.'
    elif reasoning_stripped and not warning:
        warning = 'Visible reasoning was stripped automatically. Showing the in-scene reply only.'

    yield {
        'type': 'final',
        'reply': visible_accum.strip(),
        'finish_reason': finish_reason,
        'warning': warning,
        'reasoning_stripped': reasoning_stripped,
        'memory_item_count': int((memory_pack or {}).get('item_count') or 0),
        'message': 'Roleplay turn ready.',
    }


async def generate_prompt_text(
    idea: str,
    model: str,
    style: str = 'Stable Diffusion Prompt',
    custom_instructions: str = '',
    max_tokens: int = 220,
    temperature: float = 0.35,
    top_p: float = 0.9,
    top_k: int = 40,
) -> Dict[str, str]:
    req = _build_prompt_request(idea=idea, style=style, custom_instructions=custom_instructions)
    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': req['system_prompt']},
                {'role': 'user', 'content': req['user_prompt']},
            ],
            'max_tokens': clamp_int(max_tokens, 32, 1200, 220),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.35),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'repetition_penalty': 1.12,
        },
        timeout=180.0,
    )
    result['text'] = _cleanup_prompt_text(result.get('content', ''), style)
    return result


async def continue_prompt_text(
    idea: str,
    current_output: str,
    model: str,
    style: str = 'Stable Diffusion Prompt',
    custom_instructions: str = '',
    max_tokens: int = 220,
    temperature: float = 0.35,
    top_p: float = 0.9,
    top_k: int = 40,
) -> Dict[str, str]:
    req = _build_prompt_request(idea=idea, style=style, custom_instructions=custom_instructions)
    user_prompt = (
        f"{req['user_prompt']}\n\n"
        'The previous output was cut off. Continue from exactly where it stopped. '
        'Do not restart from the beginning. Do not repeat the existing text. '
        'Return only the continuation text.\n\n'
        f'Existing partial output:\n{(current_output or "").strip()}'
    )
    result = await _post_chat(
        {
            'model': model,
            'messages': [
                {'role': 'system', 'content': req['system_prompt']},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': clamp_int(max_tokens, 32, 1200, 220),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.35),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'repetition_penalty': 1.1,
        },
        timeout=180.0,
    )
    continuation = _cleanup_prompt_text(result.get('content', ''), style)
    combined = _merge_continuation(current_output, continuation, style)
    result['text'] = combined
    result['continuation'] = continuation
    return result



def _merge_continuation(existing: str, continuation: str, style: str) -> str:
    existing = (existing or '').rstrip()
    continuation = (continuation or '').lstrip(' ,\n')
    if not existing:
        return continuation
    if not continuation:
        return existing
    if style == 'Stable Diffusion Prompt':
        joiner = ', ' if not existing.endswith(',') else ' '
    else:
        joiner = '' if existing.endswith((' ', '\n', ',', ';', ':', '-')) else ' '
    return _cleanup_prompt_text(existing + joiner + continuation, style)



def _cleanup_prompt_text(text: str, style: str) -> str:
    text = (text or '').strip()
    text = re.sub(r'^assistant\s*:\s*', '', text, flags=re.I)
    if style in {'Stable Diffusion Prompt', 'Style Convert'} and _looks_like_sd_tags(text):
        text = text.replace('\n', ', ')
        text = re.sub(r'(?:^|,\s*)(?:\d+\.|\d+\)|[-*•])\s*', ', ', text)
        parts = [re.sub(r'\s+', ' ', p.strip()) for p in text.split(',') if p.strip()]
        seen = set()
        clean = []
        for part in parts:
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            clean.append(part)
        text = ', '.join(clean)
    else:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'\s+([,.;:])', r'\1', text)
    return text or 'No prompt generated.'


PROMPT_STYLE_MAP = {
    'Stable Diffusion Prompt': 'sd',
    'Descriptive': 'descriptive',
    'Style Convert': 'style_convert',
    'Custom': 'custom',
}



def _guess_mime_type(image_path: str) -> str:
    mime, _ = mimetypes.guess_type(image_path)
    if mime and mime.startswith('image/'):
        return mime
    return 'image/jpeg'



def _caption_length_hint(length: str) -> str:
    length = (length or 'any').strip().lower()
    if length == 'short':
        return 'Keep it short.'
    if length == 'medium':
        return 'Keep it medium length.'
    if length == 'long':
        return 'Be detailed, but stay literal.'
    return 'Length is flexible, but stay concise.'



def _caption_detail_level_hint(detail_level: str) -> str:
    level = (detail_level or 'detailed').strip().lower().replace('-', '_').replace(' ', '_')
    if level == 'basic':
        return 'Keep it concise and useful. Mention only the strongest visible traits.'
    if level == 'attribute_rich':
        return (
            'Be richly specific and cover as many visible attributes as possible. '
            'For face-focused captions, include visible facial structure, eyebrow shape, eye shape and color when visible, eyelids, nose, lips, jawline, chin, skin tone or texture, hair color, hairstyle, hair length, bangs, facial hair, accessories, and expression. '
            'For person-focused captions, include visible body build, posture, pose, outfit pieces, colors, fabrics, fit, accessories, footwear, hairstyle, and overall archetype or vibe. '
            'Only mention details that are actually visible. Do not invent hidden or uncertain traits.'
        )
    return 'Be clearly detailed and cover important visible attributes without padding.'



def _caption_mode_hint(caption_mode: str, detail_level: str = 'detailed') -> str:
    mode = (caption_mode or 'full_image').strip().lower()
    detail_hint = _caption_detail_level_hint(detail_level)
    if mode == 'face_only':
        base = 'Focus only on the visible face, head, hair, expression, age cues, and facial accessories. Ignore clothing, pose, and background unless unavoidable.'
        extra = 'Describe all visible facial attributes such as face shape, forehead, eyebrow shape or thickness, eye shape, eye color when visible, eyelashes, nose shape, lips, jawline, chin, cheek structure, skin tone or texture, hairstyle, hair color, hair length, bangs, and visible accessories.'
        return f'{base} {extra} {detail_hint}'
    if mode == 'person_only':
        base = 'Focus on the main visible person or character only. Ignore most background details unless they are required to understand the visible subject.'
        extra = 'Describe the visible person in detail, including body build, posture, pose, framing, outfit pieces, layering, materials, colors, hairstyle, face if visible, accessories, footwear, and the overall character vibe or archetype.'
        return f'{base} {extra} {detail_hint}'
    if mode == 'outfit_only':
        base = 'Focus only on clothing, outfit layers, fabrics, footwear, and accessories worn by the main visible subject. Ignore face, body proportions, pose, and location unless unavoidable.'
        extra = 'Break down visible garment types, layering, fit, colors, patterns, textures, fabrics, closures, jewelry, and shoes.'
        return f'{base} {extra} {detail_hint}'
    if mode == 'pose_only':
        base = 'Focus only on the body pose, stance, gesture, limb placement, balance, and framing of the subject. Ignore clothing details, facial features, and environment unless unavoidable.'
        extra = 'Describe body orientation, head angle, arm placement, hand gesture, leg position, weight distribution, and silhouette clearly.'
        return f'{base} {extra} {detail_hint}'
    if mode == 'location_only':
        base = 'Focus only on the environment, background, setting, architecture, props, lighting, and atmosphere. Ignore people and outfits except for minimal generic foreground mentions when impossible to avoid.'
        extra = 'Describe the location with concrete visual details, materials, scale cues, weather, time-of-day cues, and mood lighting when visible.'
        return f'{base} {extra} {detail_hint}'
    if mode == 'custom_crop':
        return f'Describe only what is visible inside the selected crop region. Ignore everything outside the crop. {detail_hint}'
    return f'Describe the full visible image. Cover the main subject first, then visible appearance, outfit, pose, and setting as needed. {detail_hint}'


def build_caption_user_prompt(
    prompt_style: str,
    caption_length: str,
    custom_prompt: str,
    prefix: str,
    suffix: str,
    output_style: str,
    caption_mode: str = 'full_image',
    detail_level: str = 'detailed',
) -> str:
    prompt_style = (prompt_style or 'Stable Diffusion Prompt').strip()
    length_hint = _caption_length_hint(caption_length)
    custom_prompt = (custom_prompt or '').strip()
    prefix = (prefix or '').strip()
    suffix = (suffix or '').strip()
    output_style = (output_style or 'Auto (match input)').strip()

    mode_hint = _caption_mode_hint(caption_mode, detail_level)

    if prompt_style == 'Custom' and custom_prompt:
        user = f"{custom_prompt.strip()} {mode_hint}".strip()
    elif prompt_style == 'Descriptive':
        user = (
            'Describe only what is clearly visible in the image. '
            'Write plain factual text only. '
            'Do not invent extra people, relationships, props, or off-camera details. '
            'Count visible people exactly. '
            'If gender is unclear, use neutral words like person or adult. '
            f'{length_hint} '
            f'{mode_hint}'
        )
    elif prompt_style == 'Style Convert':
        user = (
            'Describe the image in the opposite output style. '
            'If the visible content looks photorealistic, describe it as anime / illustration friendly text. '
            'If it already looks illustrated, describe it as realistic / photographic text. '
            'Use only visible details and do not invent extra people or props. '
            'Output plain text only. '
            f'{mode_hint}'
        )
    else:
        user = (
            'Return exactly one single line of comma-separated Stable Diffusion tags. '
            'Use only visible details. '
            'Do not add people or objects that are not present. '
            'Count visible people exactly. '
            'Do not number anything. Do not use bullet points. Do not write explanations. '
            f'{length_hint} '
            f'{mode_hint}'
        )

    if output_style == 'Realistic':
        user += ' Bias the wording toward realistic photography.'
    elif output_style == 'Anime':
        user += ' Bias the wording toward anime / illustrated style.'
    if prefix:
        user += f' Prefix the final output with: {prefix}.'
    if suffix:
        user += f' Suffix the final output with: {suffix}.'
    return user


async def caption_image_with_settings(
    image_path: str,
    model: str,
    prompt_style: str = 'Stable Diffusion Prompt',
    caption_length: str = 'any',
    custom_prompt: str = '',
    max_tokens: int = 160,
    temperature: float = 0.2,
    top_p: float = 0.9,
    top_k: int = 40,
    prefix: str = '',
    suffix: str = '',
    output_style: str = 'Auto (match input)',
    caption_mode: str = 'full_image',
    detail_level: str = 'detailed',
) -> Dict[str, str]:
    if not os.path.isfile(image_path):
        return {'text': 'Invalid image file.', 'content': 'Invalid image file.', 'finish_reason': 'error'}
    mime_type = _guess_mime_type(image_path)
    system_prompt = (
        'You are a literal vision captioning assistant. '
        'Describe only directly visible details. '
        'Never invent extra people, genders, relationships, objects, or background elements. '
        'Never reveal chain-of-thought, scratch work, or <think> tags. '
        'If you reason internally, keep it hidden and output only the final caption. '
        'Count visible people exactly. If a detail is unclear, say less rather than guessing.'
    )
    user_prompt = build_caption_user_prompt(prompt_style, caption_length, custom_prompt, prefix, suffix, output_style, caption_mode, detail_level)

    try:
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': user_prompt},
                        {'type': 'image_url', 'image_url': {'url': f'data:{mime_type};base64,{b64}'}},
                    ],
                },
            ],
            'max_tokens': clamp_int(max_tokens, 24, 1000, 160),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.2),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'repetition_penalty': 1.12,
        }
        result = await _post_chat(payload, timeout=240.0)
        result['text'] = _cleanup_caption_text(result.get('content', ''), prompt_style)
        return result
    except Exception as e:
        return {'text': f'Vision error: {e}', 'content': f'Vision error: {e}', 'finish_reason': 'error'}



def _cleanup_caption_text(text: str, prompt_style: str) -> str:
    text = (text or '').strip()
    text = text.replace('<br>', ' ')
    text = re.sub(r'^assistant\s*:\s*', '', text, flags=re.I)
    if prompt_style == 'Stable Diffusion Prompt':
        text = text.replace('\n', ', ')
        text = re.sub(r'(?:^|,\s*)(?:\d+\.|\d+\)|[-*•])\s*', ', ', text)
        raw_tags = [re.sub(r'\s+', ' ', tag.strip()) for tag in text.split(',')]
        seen = set()
        cleaned = []
        for tag in raw_tags:
            if not tag:
                continue
            low = tag.lower()
            if low not in seen:
                seen.add(low)
                cleaned.append(tag)
        text = ', '.join(cleaned[:40])
    elif prompt_style == 'Custom':
        text = re.sub(r'\n{3,}', '\n\n', text)
    else:
        text = re.sub(r'\n{3,}', '\n\n', text)
    return text or 'No description generated.'
