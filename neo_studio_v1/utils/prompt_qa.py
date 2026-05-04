from __future__ import annotations

import re
from collections import Counter
from typing import Any

_WORD_RE = re.compile(r"[a-zA-Z0-9_./:-]+")
_TAG_SPLIT_RE = re.compile(r"\s*,\s*")
_MULTI_SPACE_RE = re.compile(r"\s+")

STYLE_TERMS = {
    'cinematic', 'photorealistic', 'realistic', 'stylized', 'anime', 'illustration',
    'painterly', 'digital painting', 'watercolor', 'comic', 'manga', 'film still',
    'editorial', 'fashion', 'fantasy art', 'concept art', '3d render', 'cg', 'cel shaded',
    'hyperreal', 'semi-realistic', 'oil painting', 'pixel art'
}
CAMERA_TERMS = {
    'close-up', 'close up', 'medium shot', 'wide shot', 'long shot', 'full body', 'portrait',
    'low angle', 'high angle', 'dutch angle', 'overhead', 'bird eye', 'birds eye', 'macro',
    'bokeh', 'depth of field', '35mm', '50mm', '85mm', 'telephoto', 'fisheye', 'f/1.8', 'f1.8',
    'f/2.8', 'f2.8', 'cinematic lighting'
}
FILLER_PHRASES = {
    'masterpiece', 'best quality', 'high quality', 'ultra detailed', 'very detailed', 'extremely detailed',
    'beautiful', 'amazing', 'epic', 'award winning', 'stunning', 'detailed', 'highly detailed'
}
SUBJECT_TERMS = {
    'man', 'woman', 'boy', 'girl', 'person', 'character', 'portrait', 'couple', 'male', 'female',
    'subject', 'face', 'model', 'warrior', 'mage', 'dragon', 'creature', 'cat', 'dog', 'car',
    'room', 'city', 'street', 'building', 'landscape', 'forest', 'beach', 'castle', 'robot',
    'android', 'knight', 'outfit', 'dress', 'jacket', 'house', 'bedroom', 'office', 'market'
}
CONTRADICTION_PAIRS = [
    ('day', 'night'),
    ('indoors', 'outdoors'),
    ('indoor', 'outdoor'),
    ('sunrise', 'sunset'),
    ('standing', 'sitting'),
    ('summer', 'winter'),
    ('smiling', 'crying'),
    ('solo', 'crowd'),
    ('empty street', 'crowded street'),
    ('clean shave', 'full beard'),
]


def _normalize_space(text: str) -> str:
    return _MULTI_SPACE_RE.sub(' ', (text or '').strip())


def _normalize_tag(tag: str) -> str:
    tag = _normalize_space(tag).strip(' ,;')
    tag = tag.replace('_', ' ').lower()
    return tag


def _split_tags(prompt: str) -> list[str]:
    if ',' not in prompt:
        return []
    parts = [_normalize_tag(p) for p in _TAG_SPLIT_RE.split(prompt) if _normalize_tag(p)]
    return parts


def _tokenize_words(prompt: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(prompt or '')]


def _contains_phrase(normalized_prompt: str, phrase: str) -> bool:
    if not phrase:
        return False
    if ' ' in phrase:
        return phrase in normalized_prompt
    return bool(re.search(rf'\b{re.escape(phrase)}\b', normalized_prompt))


def _looks_subject_like(tag: str) -> bool:
    tag_n = _normalize_tag(tag)
    if not tag_n:
        return False
    if any(term in tag_n for term in SUBJECT_TERMS):
        return True
    # keep style/camera-only fragments from counting as subject anchors
    if any(term in tag_n for term in STYLE_TERMS) or any(term in tag_n for term in CAMERA_TERMS):
        return False
    words = [w for w in tag_n.split() if w]
    return len(words) >= 2 and not all(w in {'cinematic', 'dramatic', 'beautiful', 'detailed', 'moody'} for w in words)


def lint_prompt(prompt: str) -> dict[str, Any]:
    original = prompt or ''
    cleaned = _normalize_space(original)
    normalized_prompt = _normalize_tag(cleaned)
    tags = _split_tags(cleaned)
    words = _tokenize_words(cleaned)
    warnings: list[dict[str, Any]] = []

    def add_warning(kind: str, title: str, detail: str, suggestion: str, severity: str = 'warn') -> None:
        warnings.append({
            'kind': kind,
            'title': title,
            'detail': detail,
            'suggestion': suggestion,
            'severity': severity,
        })

    # repeated tags / phrases
    normalized_parts = tags or [_normalize_tag(p) for p in re.split(r'[\n;]+', cleaned) if _normalize_tag(p)]
    repeated: list[str] = []
    if tags:
        counts = Counter(normalized_parts)
        repeated = [tag for tag, count in counts.items() if count > 1]
        if repeated:
            sample = ', '.join(repeated[:6])
            add_warning(
                'repeated_tags',
                'Repeated tags detected',
                f'Repeated tags can waste space and dilute emphasis: {sample}.',
                'Keep one strong version of each tag unless repetition is intentional.',
            )

    # contradictions
    contradictions: list[str] = []
    for a, b in CONTRADICTION_PAIRS:
        if _contains_phrase(normalized_prompt, a) and _contains_phrase(normalized_prompt, b):
            contradictions.append(f'{a} ↔ {b}')
    if contradictions:
        add_warning(
            'contradictions',
            'Possible contradictions found',
            'These pairs may fight each other: ' + ', '.join(contradictions[:5]) + '.',
            'Pick one clear direction or split conflicting ideas into separate versions.',
            severity='error',
        )

    # filler / low-value phrases
    filler_hits = [phrase for phrase in FILLER_PHRASES if _contains_phrase(normalized_prompt, phrase)]
    if len(filler_hits) >= 2:
        add_warning(
            'filler_terms',
            'Low-value quality filler is piling up',
            'These phrases rarely add concrete visual control: ' + ', '.join(sorted(filler_hits)[:6]) + '.',
            'Swap generic quality terms for visible details like fabric, lighting, pose, mood, or composition.',
        )

    # overloaded style / camera
    style_hits = [term for term in STYLE_TERMS if _contains_phrase(normalized_prompt, term)]
    if len(style_hits) >= 5:
        add_warning(
            'style_overload',
            'Too many style terms',
            'The prompt mixes a lot of style labels: ' + ', '.join(sorted(style_hits)[:7]) + '.',
            'Keep two or three style anchors max so the look stays coherent.',
        )
    camera_hits = [term for term in CAMERA_TERMS if _contains_phrase(normalized_prompt, term)]
    if len(camera_hits) >= 4:
        add_warning(
            'camera_overload',
            'Too many camera / lens instructions',
            'Camera terms are stacking up: ' + ', '.join(sorted(camera_hits)[:7]) + '.',
            'Keep the strongest one or two framing ideas and cut the rest.',
        )

    # length warning
    char_count = len(cleaned)
    word_count = len(words)
    tag_count = len(tags)
    if char_count >= 700 or word_count >= 120 or tag_count >= 58:
        detail_bits = [f'{char_count} chars', f'{word_count} words']
        if tag_count:
            detail_bits.append(f'{tag_count} tags')
        add_warning(
            'length',
            'Prompt looks heavy',
            'This prompt may be harder to control cleanly at ' + ', '.join(detail_bits) + '.',
            'Trim duplicates, cut filler, and front-load only the most important subject details.',
        )

    # subject clarity + ordering
    subject_anchor_index = None
    if tags:
        for idx, tag in enumerate(tags[:8]):
            if _looks_subject_like(tag):
                subject_anchor_index = idx
                break
        if subject_anchor_index is None:
            add_warning(
                'subject_clarity',
                'Main subject is not obvious',
                'The prompt starts with style or mood, but the subject never lands clearly in the first tags.',
                'Move the main subject or scene into the first 1–3 tags.',
            )
        elif subject_anchor_index > 2:
            add_warning(
                'ordering',
                'Subject shows up late',
                'Important subject details appear after style / camera terms.',
                'Put subject, pose, clothing, and environment before style polish.',
            )
    else:
        first_chunk = normalized_prompt[:180]
        subject_hits = [term for term in SUBJECT_TERMS if _contains_phrase(first_chunk, term)]
        if not subject_hits and word_count >= 10:
            add_warning(
                'subject_clarity',
                'Main subject is vague',
                'The opening reads more like mood or style than a clear subject statement.',
                'Start with who or what is in frame, then add style and camera details after that.',
            )

    # weak ordering even without tags
    if not tags and word_count >= 18:
        starts_with_style = any(_contains_phrase(_normalize_tag(' '.join(words[:12])), term) for term in STYLE_TERMS | CAMERA_TERMS)
        if starts_with_style and not any(_contains_phrase(_normalize_tag(' '.join(words[:12])), term) for term in SUBJECT_TERMS):
            add_warning(
                'ordering',
                'Prompt starts with polish before subject',
                'Style or camera language appears before the scene is anchored.',
                'Lead with subject + action + setting, then add style and lens choices.',
            )

    summary = 'Looks clean. No major prompt issues flagged.'
    if warnings:
        errors = sum(1 for item in warnings if item['severity'] == 'error')
        warns = len(warnings) - errors
        parts = []
        if errors:
            parts.append(f'{errors} contradiction risk')
        if warns:
            parts.append(f'{warns} cleanup suggestion' + ('s' if warns != 1 else ''))
        summary = ' · '.join(parts).capitalize() + '.'

    return {
        'ok': True,
        'summary': summary,
        'warning_count': len(warnings),
        'warnings': warnings,
        'stats': {
            'chars': char_count,
            'words': word_count,
            'tags': tag_count,
            'repeated_tags': repeated,
            'style_hits': sorted(style_hits),
            'camera_hits': sorted(camera_hits),
            'filler_hits': sorted(filler_hits),
        },
    }
