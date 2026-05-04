from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .roleplay_foundation import ROLEPLAY_EXPORTS_DIR, slugify
from .roleplay_session_store import build_story_reader_payload


MEDIA_TYPES: dict[str, str] = {
    'json': 'application/json',
    'jsonl': 'application/x-ndjson',
    'txt': 'text/plain; charset=utf-8',
    'md': 'text/markdown; charset=utf-8',
    'html': 'text/html; charset=utf-8',
}

EXTENSIONS: dict[str, str] = {
    'json': 'json',
    'jsonl': 'jsonl',
    'txt': 'txt',
    'md': 'md',
    'html': 'html',
}

EXPORT_MODES = {'archive', 'readable', 'reimportable'}
EXPORT_FORMATS = set(MEDIA_TYPES)


def _clean_mode(export_mode: str) -> str:
    mode = str(export_mode or 'readable').strip().lower()
    return mode if mode in EXPORT_MODES else 'readable'


def _clean_format(export_format: str) -> str:
    fmt = str(export_format or 'md').strip().lower()
    return fmt if fmt in EXPORT_FORMATS else 'md'


def _safe_story_slug(payload: dict[str, Any]) -> str:
    story = payload.get('story') or {}
    return slugify(str(story.get('title') or 'story'), 'story')


def _story_meta_lines(story: dict[str, Any], parts: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"Title: {story.get('title') or 'Untitled story'}",
        f"Story ID: {story.get('id') or ''}",
    ]
    if story.get('universe_label'):
        lines.append(f"Universe: {story.get('universe_label')}")
    if story.get('world_label'):
        lines.append(f"World: {story.get('world_label')}")
    if story.get('lead_character_names'):
        lines.append(f"Cast: {', '.join(story.get('lead_character_names') or [])}")
    if (story.get('meta') or {}).get('status'):
        lines.append(f"Status: {(story.get('meta') or {}).get('status')}")
    lines.append(f"Part count: {len(parts)}")
    if story.get('summary'):
        lines.append(f"Summary: {story.get('summary')}")
    return lines



def _strip_readable_speaker_prefixes(text: str) -> str:
    lines = str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    cleaned: list[str] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            cleaned.append('')
            continue
        if index + 1 < len(lines) and re.fullmatch(r"(?:[A-Z][A-Za-z0-9'’_-]{0,20})(?: [A-Z][A-Za-z0-9'’_-]{0,20}){0,3}", line):
            continue
        cleaned.append(re.sub(r"^\s*(?:You|Partner|(?:[A-Z][A-Za-z0-9'’_-]{0,20})(?: [A-Z][A-Za-z0-9'’_-]{0,20}){0,3})\s*:\s*", '', raw))
    return re.sub(r"\n{3,}", '\n\n', '\n'.join(cleaned)).strip()


def _readable_scene_text(part: dict[str, Any]) -> str:
    scene_text = _strip_readable_speaker_prefixes(str(part.get('scene_text') or '').strip())
    if scene_text:
        return scene_text
    transcript = part.get('transcript') or []
    if not isinstance(transcript, list):
        return ''
    return '\n\n'.join(
        cleaned
        for cleaned in (
            _strip_readable_speaker_prefixes(str((entry or {}).get('content') or '').strip())
            for entry in transcript if isinstance(entry, dict)
        )
        if cleaned
    ).strip()

def _story_bundle(story_id: str, export_mode: str) -> dict[str, Any]:
    payload = build_story_reader_payload(story_id)
    story = payload.get('story') or {}
    parts = payload.get('parts') or []
    bundle: dict[str, Any] = {
        'schema_version': story.get('schema_version') or 4,
        'kind': 'story_export',
        'export_mode': export_mode,
        'story': story,
        'parts': parts,
        'summary': {
            'story_id': story.get('id', ''),
            'title': story.get('title', ''),
            'part_count': len(parts),
            'status': (story.get('meta') or {}).get('status', ''),
        },
    }
    if export_mode == 'readable':
        bundle['readable'] = {
            'title': story.get('title', ''),
            'summary': story.get('summary', ''),
            'chapters': [
                {
                    'title': part.get('title', ''),
                    'summary': part.get('summary', ''),
                    'text': _readable_scene_text(part),
                }
                for part in parts
            ],
        }
    elif export_mode == 'reimportable':
        bundle['reimportable_kind'] = 'story_bundle'
    return bundle


def story_export_filename(payload: dict[str, Any], export_format: str, export_mode: str) -> str:
    slug = _safe_story_slug(payload)
    fmt = _clean_format(export_format)
    mode = _clean_mode(export_mode)
    return f"{slug}_{mode}.{EXTENSIONS[fmt]}"


def story_export_media_type(export_format: str) -> str:
    return MEDIA_TYPES[_clean_format(export_format)]


def _render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _render_jsonl(payload: dict[str, Any], export_mode: str) -> str:
    story = payload.get('story') or {}
    parts = payload.get('parts') or []
    lines = [json.dumps({'kind': 'story_export_meta', 'export_mode': export_mode, 'title': story.get('title', ''), 'story_id': story.get('id', '')}, ensure_ascii=False)]
    lines.append(json.dumps({'kind': 'story', 'record': story}, ensure_ascii=False))
    for part in parts:
        entry = {'kind': 'story_part', 'record': part}
        if export_mode == 'readable':
            entry['readable_text'] = _readable_scene_text(part)
        lines.append(json.dumps(entry, ensure_ascii=False))
    return '\n'.join(lines)


def _render_txt(payload: dict[str, Any], export_mode: str) -> str:
    story = payload.get('story') or {}
    parts = payload.get('parts') or []
    blocks: list[str] = []
    blocks.append('\n'.join(_story_meta_lines(story, parts)))
    if story.get('summary') and export_mode != 'readable':
        blocks.append(story.get('summary', ''))
    for idx, part in enumerate(parts, start=1):
        chapter_lines = [f"CHAPTER {idx}: {part.get('title') or f'Part {idx}'}"]
        if export_mode != 'readable':
            if part.get('summary'):
                chapter_lines.append(f"Summary: {part.get('summary')}")
            if part.get('scene_notes'):
                chapter_lines.append(f"Scene notes: {part.get('scene_notes')}")
            if part.get('pinned_canon'):
                chapter_lines.append(f"Pinned canon: {part.get('pinned_canon')}")
        text = (_readable_scene_text(part) if export_mode == 'readable' else str(part.get('scene_text') or '').strip()) or 'No scene text saved for this part yet.'
        chapter_lines.append(text)
        blocks.append('\n\n'.join(chapter_lines))
    separator = f"\n\n{'=' * 72}\n\n"
    return separator.join(blocks) if blocks else ''


def _render_md(payload: dict[str, Any], export_mode: str) -> str:
    story = payload.get('story') or {}
    parts = payload.get('parts') or []
    lines = [f"# {story.get('title') or 'Untitled story'}", '']
    for line in _story_meta_lines(story, parts):
        key, _, value = line.partition(': ')
        lines.append(f"- **{key}**: {value}")
    lines.append('')
    if story.get('summary'):
        lines.extend(['## Story summary', '', story.get('summary', ''), ''])
    for idx, part in enumerate(parts, start=1):
        lines.extend([f"## Part {idx} · {part.get('title') or f'Part {idx}'}", ''])
        if export_mode != 'readable':
            if part.get('summary'):
                lines.extend([f"> {part.get('summary')}", ''])
            if part.get('scene_notes'):
                lines.extend(['**Scene notes**', '', part.get('scene_notes', ''), ''])
            if part.get('pinned_canon'):
                lines.extend(['**Pinned canon**', '', part.get('pinned_canon', ''), ''])
        text = (_readable_scene_text(part) if export_mode == 'readable' else str(part.get('scene_text') or '').strip()) or 'No scene text saved for this part yet.'
        lines.append(text)
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


def _render_html(payload: dict[str, Any], export_mode: str) -> str:
    story = payload.get('story') or {}
    parts = payload.get('parts') or []
    meta_items = ''.join(
        f"<li><strong>{html.escape(key)}</strong>: {html.escape(value)}</li>"
        for key, _, value in (line.partition(': ') for line in _story_meta_lines(story, parts))
    )
    sections: list[str] = []
    for idx, part in enumerate(parts, start=1):
        readable_source = _readable_scene_text(part) if export_mode == 'readable' else str(part.get('scene_text') or '').strip()
        prose = '<br><br>'.join(html.escape(block) for block in readable_source.split('\n\n') if block.strip()) or '<em>No scene text saved for this part yet.</em>'
        extras = ''
        if export_mode != 'readable':
            if part.get('summary'):
                extras += f"<p class=\"lede\">{html.escape(part.get('summary') or '')}</p>"
            if part.get('scene_notes'):
                extras += f"<div class=\"meta-card\"><h4>Scene notes</h4><p>{html.escape(part.get('scene_notes') or '')}</p></div>"
            if part.get('pinned_canon'):
                extras += f"<div class=\"meta-card\"><h4>Pinned canon</h4><p>{html.escape(part.get('pinned_canon') or '')}</p></div>"
        sections.append(
            f"<section class=\"chapter\"><h2>Part {idx} · {html.escape(part.get('title') or f'Part {idx}')}</h2>{extras}<div class=\"prose\">{prose}</div></section>"
        )
    summary_html = f"<section><h2>Story summary</h2><p>{html.escape(story.get('summary') or 'No story summary yet.')}</p></section>"
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(story.get('title') or 'Story export')}</title>
<style>
body {{ font-family: Georgia, "Times New Roman", serif; margin: 0; background: #111; color: #f5f2ea; }}
main {{ max-width: 860px; margin: 0 auto; padding: 40px 24px 72px; }}
h1, h2, h3, h4 {{ font-family: Inter, Arial, sans-serif; }}
h1 {{ margin-bottom: 10px; }}
.meta {{ color: #c9c1af; padding-left: 20px; }}
.chapter {{ padding: 24px 0; border-top: 1px solid rgba(255,255,255,0.14); }}
.prose {{ line-height: 1.9; font-size: 1rem; }}
.lede {{ font-style: italic; color: #ded6c5; }}
.meta-card {{ margin: 14px 0; padding: 12px 14px; border: 1px solid rgba(255,255,255,0.14); border-radius: 12px; background: rgba(255,255,255,0.04); }}
</style>
</head>
<body>
<main>
<h1>{html.escape(story.get('title') or 'Untitled story')}</h1>
<ul class="meta">{meta_items}</ul>
{summary_html}
{''.join(sections)}
</main>
</body>
</html>'''


def render_story_export(story_id: str, export_format: str = 'md', export_mode: str = 'readable') -> tuple[str, str, str]:
    fmt = _clean_format(export_format)
    mode = _clean_mode(export_mode)
    payload = _story_bundle(story_id, mode)
    filename = story_export_filename(payload, fmt, mode)
    media_type = story_export_media_type(fmt)
    if fmt == 'json':
        content = _render_json(payload)
    elif fmt == 'jsonl':
        content = _render_jsonl(payload, mode)
    elif fmt == 'txt':
        content = _render_txt(payload, mode)
    elif fmt == 'html':
        content = _render_html(payload, mode)
    else:
        content = _render_md(payload, mode)
    return content, filename, media_type


def persist_story_export(story_id: str, export_format: str = 'md', export_mode: str = 'readable') -> Path:
    content, filename, _ = render_story_export(story_id, export_format, export_mode)
    ROLEPLAY_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ROLEPLAY_EXPORTS_DIR / filename
    atomic_write_text(path, content)
    return path
