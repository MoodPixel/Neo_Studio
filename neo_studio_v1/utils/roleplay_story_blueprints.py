from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .roleplay_foundation import ROLEPLAY_PARTS_DIR, now_iso, story_part_template
from .roleplay_story_store import _story_path, _write_story, normalize_linked_context, save_story_record
from .storage_io import atomic_write_json


HEADING_RE = re.compile(r'^\s*(?:#{1,6}\s+)?(?:(chapter|scene|part)\s+[\w.-]+(?:\s*[:\-—]\s*.*)?)\s*$', re.IGNORECASE)
SCENE_HEADING_RE = re.compile(r'^\s*(?:INT|EXT|INT\.?/EXT|EXT\.?/INT)\b.*$', re.IGNORECASE)
SUBTITLE_TIMESTAMP_RE = re.compile(r'^\s*\d{1,2}:\d{2}:\d{2}[,.:]\d{1,3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.:]\d{1,3}\s*$')
SPEAKER_RE = re.compile(r'^\s*([A-Z][A-Za-z0-9\'’._-]{1,30}(?: [A-Z][A-Za-z0-9\'’._-]{1,30}){0,2})\s*:\s*(.+)$')
UPPER_SPEAKER_RE = re.compile(r'^\s*([A-Z][A-Z0-9\'’._-]{1,30}(?: [A-Z][A-Z0-9\'’._-]{1,30}){0,2})\s*$')


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(path, payload)
    return payload


def _normalize_text(text: str) -> str:
    return str(text or '').replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n').strip()


def _guess_source_kind(text: str, filename: str = '') -> str:
    clean = _normalize_text(text)
    lowered_name = str(filename or '').lower()
    if lowered_name.endswith('.srt') or lowered_name.endswith('.vtt'):
        return 'subtitle'
    lines = [line.strip() for line in clean.split('\n') if line.strip()]
    if not lines:
        return 'notes'
    subtitle_hits = sum(1 for line in lines[:120] if SUBTITLE_TIMESTAMP_RE.match(line))
    scene_hits = sum(1 for line in lines[:120] if SCENE_HEADING_RE.match(line))
    speaker_hits = sum(1 for line in lines[:160] if SPEAKER_RE.match(line))
    upper_hits = sum(1 for line in lines[:160] if UPPER_SPEAKER_RE.match(line) and len(line.split()) <= 3)
    if subtitle_hits >= 2:
        return 'subtitle'
    if scene_hits >= 2 or upper_hits >= 6:
        return 'screenplay'
    if speaker_hits >= 4:
        return 'transcript'
    if any(HEADING_RE.match(line) for line in lines[:40]):
        return 'prose'
    return 'prose' if clean.count('\n\n') >= 2 else 'notes'


def _infer_title(text: str, fallback: str = '') -> str:
    if str(fallback or '').strip():
        return str(fallback).strip()
    for line in _normalize_text(text).split('\n')[:12]:
        candidate = line.strip().lstrip('#').strip()
        if not candidate:
            continue
        if SUBTITLE_TIMESTAMP_RE.match(candidate) or SPEAKER_RE.match(candidate):
            continue
        if len(candidate) <= 90:
            return candidate
    return 'Imported story blueprint'


def _extract_lead_characters(text: str) -> list[str]:
    counts: Counter[str] = Counter()
    for raw in _normalize_text(text).split('\n')[:500]:
        line = raw.strip()
        match = SPEAKER_RE.match(line)
        if match:
            counts[match.group(1).strip().title()] += 1
            continue
        if UPPER_SPEAKER_RE.match(line) and len(line.split()) <= 3:
            counts[line.title()] += 1
    return [name for name, _count in counts.most_common(6)]


def _summarize_block(text: str, limit: int = 220) -> str:
    clean = re.sub(r'\s+', ' ', str(text or '').strip())
    if len(clean) <= limit:
        return clean
    return clean[: max(40, limit - 1)].rstrip() + '…'


def _chunk_blocks(blocks: list[str], *, max_blocks: int = 6, max_chars: int = 2200) -> list[str]:
    chunks: list[str] = []
    bucket: list[str] = []
    chars = 0
    for block in [str(item or '').strip() for item in blocks if str(item or '').strip()]:
        projected = chars + len(block) + (2 if bucket else 0)
        if bucket and (len(bucket) >= max_blocks or projected > max_chars):
            chunks.append('\n\n'.join(bucket).strip())
            bucket = []
            chars = 0
        bucket.append(block)
        chars += len(block) + (2 if bucket else 0)
    if bucket:
        chunks.append('\n\n'.join(bucket).strip())
    return chunks


def _parse_subtitle(text: str) -> list[dict[str, Any]]:
    lines = _normalize_text(text).split('\n')
    blocks: list[str] = []
    current: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            if current:
                blocks.append(' '.join(current).strip())
                current = []
            continue
        if line.isdigit() or SUBTITLE_TIMESTAMP_RE.match(line):
            continue
        current.append(line)
    if current:
        blocks.append(' '.join(current).strip())
    chunks = _chunk_blocks(blocks, max_blocks=10, max_chars=1800)
    return [
        {
            'title': f'Part {idx}',
            'text': chunk,
            'summary': _summarize_block(chunk),
            'chapter_index': 1,
            'chapter_label': 'Imported subtitles',
            'part_index': idx,
            'beat_focus': 'Subtitle sequence',
        }
        for idx, chunk in enumerate(chunks, start=1)
    ]


def _parse_transcript_like(text: str, *, chapter_label: str = 'Imported transcript') -> list[dict[str, Any]]:
    blocks = [block.strip() for block in _normalize_text(text).split('\n\n') if block.strip()]
    chunks = _chunk_blocks(blocks, max_blocks=6, max_chars=2200)
    return [
        {
            'title': f'Part {idx}',
            'text': chunk,
            'summary': _summarize_block(chunk),
            'chapter_index': 1,
            'chapter_label': chapter_label,
            'part_index': idx,
            'beat_focus': 'Dialogue beat',
        }
        for idx, chunk in enumerate(chunks, start=1)
    ]


def _parse_screenplay(text: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    current_heading = ''
    current_lines: list[str] = []
    chapter_index = 1
    part_index = 0

    def flush() -> None:
        nonlocal current_lines, current_heading, part_index
        body = '\n'.join(line for line in current_lines if line.strip()).strip()
        if not body:
            current_lines = []
            return
        part_index += 1
        label = current_heading or f'Scene {part_index}'
        units.append({
            'title': label[:120],
            'text': body,
            'summary': _summarize_block(body),
            'chapter_index': chapter_index,
            'chapter_label': 'Imported screenplay',
            'part_index': part_index,
            'beat_focus': label[:120],
        })
        current_lines = []

    for raw in _normalize_text(text).split('\n'):
        line = raw.rstrip()
        if SCENE_HEADING_RE.match(line.strip()):
            flush()
            current_heading = line.strip()
            continue
        current_lines.append(line)
    flush()
    return units or _parse_transcript_like(text, chapter_label='Imported screenplay')


def _parse_prose_or_notes(text: str) -> list[dict[str, Any]]:
    lines = _normalize_text(text).split('\n')
    units: list[dict[str, Any]] = []
    chapter_index = 1
    chapter_label = ''
    chapter_parts: list[str] = []

    def flush_chapter() -> None:
        nonlocal chapter_parts, chapter_index
        chunks = _chunk_blocks(chapter_parts, max_blocks=5, max_chars=2600)
        if not chunks:
            return
        label = chapter_label or f'Chapter {chapter_index}'
        for idx, chunk in enumerate(chunks, start=1):
            units.append({
                'title': f'{label} · Part {idx}' if len(chunks) > 1 else label,
                'text': chunk,
                'summary': _summarize_block(chunk),
                'chapter_index': chapter_index,
                'chapter_label': label,
                'part_index': idx,
                'beat_focus': label,
            })
        chapter_parts = []
        chapter_index += 1

    buffer: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            if buffer:
                chapter_parts.append('\n'.join(buffer).strip())
                buffer = []
            flush_chapter()
            chapter_label = stripped.lstrip('#').strip()
            continue
        if not stripped:
            if buffer:
                chapter_parts.append('\n'.join(buffer).strip())
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        chapter_parts.append('\n'.join(buffer).strip())
    flush_chapter()
    return units or [{
        'title': 'Part 1',
        'text': _normalize_text(text),
        'summary': _summarize_block(text),
        'chapter_index': 1,
        'chapter_label': chapter_label or 'Imported text',
        'part_index': 1,
        'beat_focus': chapter_label or 'Imported text',
    }]


def build_story_blueprint(source_text: str, *, source_kind: str = 'auto', title: str = '', filename: str = '') -> dict[str, Any]:
    clean_text = _normalize_text(source_text)
    if not clean_text:
        raise ValueError('Add source text or upload a text file first.')
    kind = str(source_kind or 'auto').strip().lower() or 'auto'
    if kind == 'auto':
        kind = _guess_source_kind(clean_text, filename)
    if kind == 'subtitle':
        units = _parse_subtitle(clean_text)
    elif kind == 'screenplay':
        units = _parse_screenplay(clean_text)
    elif kind == 'transcript':
        units = _parse_transcript_like(clean_text)
    else:
        units = _parse_prose_or_notes(clean_text)
    inferred_title = _infer_title(clean_text, title or Path(filename or '').stem)
    summary = _summarize_block(' '.join(unit.get('summary', '') for unit in units[:2]), limit=320)
    leads = _extract_lead_characters(clean_text)
    return {
        'source_kind': kind,
        'title': inferred_title,
        'summary': summary,
        'lead_characters': leads,
        'parts': units,
    }


def import_story_blueprint(
    source_text: str,
    *,
    source_kind: str = 'auto',
    title: str = '',
    filename: str = '',
    status: str = 'draft',
    canon_mode: str = 'what_if',
    output_preset: str = 'novel',
    linked_context: Any = None,
    story_mode: str = 'linear',
    option_count: int = 3,
    allow_custom_option: bool = True,
) -> dict[str, Any]:
    blueprint = build_story_blueprint(source_text, source_kind=source_kind, title=title, filename=filename)
    story = save_story_record(
        title=blueprint['title'],
        summary=blueprint['summary'],
        lead_characters=', '.join(blueprint.get('lead_characters') or []),
        status=status,
        canon_mode=canon_mode,
        output_preset=output_preset,
        linked_context=normalize_linked_context(linked_context),
        story_mode=story_mode,
        option_count=option_count,
        allow_custom_option=allow_custom_option,
    )
    story['part_ids'] = []
    story_meta = story.get('meta') or {}
    story_meta['updated_at'] = now_iso()
    story['meta'] = story_meta

    part_ids: list[str] = []
    for idx, unit in enumerate(blueprint.get('parts') or [], start=1):
        part = story_part_template(story_id=story['id'], title=str(unit.get('title') or f'Part {idx}').strip(), order_index=idx)
        part['summary'] = str(unit.get('summary') or '').strip()
        part['scene_text'] = str(unit.get('text') or '').strip()
        part['scene_notes'] = f"Imported from {blueprint.get('source_kind', 'text')} source"
        part['linked_context'] = normalize_linked_context(story.get('linked_context'))
        progression = part.get('progression') or {}
        progression['chapter_index'] = int(unit.get('chapter_index') or 1)
        progression['chapter_label'] = str(unit.get('chapter_label') or '').strip()
        progression['part_index'] = int(unit.get('part_index') or idx)
        progression['beat_focus'] = str(unit.get('beat_focus') or part['title']).strip()
        progression['part_objective'] = str(unit.get('summary') or '').strip()
        part['progression'] = progression
        branching = part.get('branching') or {}
        branching.update({
            'story_mode': 'branching' if str(story_mode or '').strip().lower() == 'branching' else 'linear',
            'option_count': max(2, min(6, int(option_count or 3))),
            'allow_custom_option': bool(allow_custom_option),
            'latest_options': [],
            'choice_history': [],
        })
        part['branching'] = branching
        advanced = part.get('advanced_controls') or {}
        advanced['output_preset'] = str(output_preset or 'novel').strip() or 'novel'
        advanced['canon_mode'] = str(canon_mode or 'what_if').strip() or 'what_if'
        advanced['scenario'] = story.get('title', '')
        part['advanced_controls'] = advanced
        meta = part.get('meta') or {}
        meta['status'] = 'imported'
        meta['updated_at'] = now_iso()
        part['meta'] = meta
        _write_json(ROLEPLAY_PARTS_DIR / f"{part['id']}.json", part)
        part_ids.append(part['id'])

    story['part_ids'] = part_ids
    _write_story(story)
    return {
        'story': story,
        'parts_count': len(part_ids),
        'first_part_id': part_ids[0] if part_ids else '',
        'source_kind': blueprint.get('source_kind', 'auto'),
        'lead_characters': blueprint.get('lead_characters') or [],
    }
