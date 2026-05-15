from __future__ import annotations

import re
from typing import Any

_MAX_SUMMARY_LEN = 4000


def _clean(value: Any, limit: int = 600) -> str:
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def _join_unique(items: list[str], *, limit: int = 8) -> str:
    seen: list[str] = []
    for item in items:
        clean = _clean(item, 120)
        if clean and clean not in seen:
            seen.append(clean)
        if len(seen) >= limit:
            break
    return ', '.join(seen)


def _message_excerpt(messages: Any, *, limit: int = 4) -> str:
    rows = []
    source = messages if isinstance(messages, list) else []
    for entry in source[-limit:]:
        if not isinstance(entry, dict):
            continue
        role = 'User' if str(entry.get('role') or '').strip() == 'user' else 'Assistant'
        content = _clean(entry.get('content') or '', 220)
        if content:
            rows.append(f'{role}: {content}')
    return ' | '.join(rows)


def build_assistant_profile_summary(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    lines = [
        f"Assistant name: {_clean(profile.get('assistant_name') or 'Neo', 80)}",
        f"User name: {_clean(profile.get('user_name') or '', 80)}",
        f"Address style: {_clean(profile.get('address_style') or 'adaptive', 40)}",
        f"Default mode: {_clean(profile.get('default_mode') or 'general', 40)}",
        f"Response detail: {_clean(profile.get('response_detail') or 'balanced', 40)}",
        f"Support style: {_clean(profile.get('support_style') or 'balanced', 40)}",
    ]
    if _clean(profile.get('about_user')):
        lines.append(f"About user: {_clean(profile.get('about_user'), 700)}")
    if _clean(profile.get('preferences')):
        lines.append(f"Preferences: {_clean(profile.get('preferences'), 700)}")
    if _clean(profile.get('avoid')):
        lines.append(f"Avoid: {_clean(profile.get('avoid'), 500)}")
    return '\n'.join([line for line in lines if line.strip()])[:_MAX_SUMMARY_LEN]


def build_assistant_project_summary(project: dict[str, Any] | None) -> str:
    project = project or {}
    context_cards = project.get('context_cards') if isinstance(project.get('context_cards'), list) else []
    context_files = project.get('context_files') if isinstance(project.get('context_files'), list) else []
    linked_records = project.get('linked_records') if isinstance(project.get('linked_records'), list) else []
    project_profile = project.get('project_profile') if isinstance(project.get('project_profile'), dict) else {}
    custom_profile = project.get('custom_profile') if isinstance(project.get('custom_profile'), dict) else {}
    profile_label = _clean(project_profile.get('display_label') or project_profile.get('label') or project.get('project_type') or 'General', 160)
    lines = [
        f"Project: {_clean(project.get('title') or 'Project', 160)}",
        f"Project type: {profile_label}",
        f"Description: {_clean(project.get('description') or '', 700)}",
        f"Brief: {_clean(project.get('brief') or '', 1200)}",
    ]
    if _clean(custom_profile.get('description')):
        lines.append(f"Custom profile: {_clean(custom_profile.get('description'), 700)}")
    if isinstance(project_profile.get('memory_focus'), list) and project_profile.get('memory_focus'):
        lines.append('Memory focus: ' + _join_unique([str(item) for item in project_profile.get('memory_focus')], limit=12))
    if context_cards:
        lines.append('Context cards: ' + _join_unique([str(item.get('title') or '') for item in context_cards], limit=10))
    if context_files:
        lines.append('Context files: ' + _join_unique([str(item.get('title') or '') for item in context_files], limit=8))
    if linked_records:
        lines.append('Linked records: ' + _join_unique([str(item.get('title') or '') for item in linked_records], limit=10))
    lines.append(f"Thread count: {int(project.get('thread_count') or 0)}")
    return '\n'.join([line for line in lines if _clean(line)])[:_MAX_SUMMARY_LEN]


def build_assistant_session_summary(session: dict[str, Any] | None) -> str:
    session = session or {}
    helper = session.get('helper_context') if isinstance(session.get('helper_context'), dict) else {}
    context_items = session.get('context_items') if isinstance(session.get('context_items'), list) else []
    lines = [
        f"Session: {_clean(session.get('title') or 'Assistant chat', 160)}",
        f"Mode: {_clean(session.get('mode') or 'general', 40)}",
        f"Project ID: {_clean(session.get('project_id') or '', 120)}",
        f"Thread instruction: {_clean(session.get('thread_instruction') or '', 800)}",
        f"Pinned context note: {_clean(session.get('context_note') or '', 1000)}",
    ]
    if helper:
        fields = helper.get('fields') if isinstance(helper.get('fields'), list) else []
        lines.append('Helper context: ' + ' | '.join([part for part in [
            f"workspace={_clean(helper.get('workspace') or '', 60)}",
            f"target={_clean(helper.get('target') or '', 60)}",
            f"action={_clean(helper.get('action') or '', 60)}",
            f"fields={_join_unique([str(v) for v in fields], limit=10)}",
        ] if _clean(part)]))
        if _clean(helper.get('instruction')):
            lines.append(f"Helper instruction: {_clean(helper.get('instruction'), 900)}")
    if context_items:
        lines.append('Thread attachments: ' + _join_unique([str(item.get('title') or '') for item in context_items], limit=8))
    if _clean(session.get('memory_summary')):
        lines.append(f"Older memory summary: {_clean(session.get('memory_summary'), 1400)}")
    excerpt = _message_excerpt(session.get('messages'))
    if excerpt:
        lines.append(f"Recent turns: {excerpt}")
    lines.append(f"Message count: {int(session.get('message_count') or len(session.get('messages') or []))}")
    return '\n'.join([line for line in lines if _clean(line)])[:_MAX_SUMMARY_LEN]


def build_roleplay_story_summary(story: dict[str, Any] | None) -> str:
    story = story or {}
    linked_context = story.get('linked_context') if isinstance(story.get('linked_context'), dict) else {}
    linked_bits = []
    for key, values in linked_context.items():
        if isinstance(values, list) and values:
            linked_bits.append(f"{key.replace('_ids', '')}={len(values)}")
    lines = [
        f"Story: {_clean(story.get('title') or 'Story', 160)}",
        f"Summary: {_clean(story.get('summary') or '', 1000)}",
        f"Universe: {_clean(story.get('universe_label') or '', 160)}",
        f"World: {_clean(story.get('world_label') or '', 160)}",
        f"Story mode: {_clean(story.get('story_mode') or 'linear', 40)}",
        f"Pinned canon: {_clean(story.get('pinned_canon') or '', 900)}",
        f"Lead characters: {_join_unique([str(v) for v in (story.get('lead_character_names') or [])], limit=8)}",
    ]
    if linked_bits:
        lines.append('Linked context counts: ' + ', '.join(linked_bits[:10]))
    lines.append(f"Part count: {len(story.get('part_ids') or [])}")
    return '\n'.join([line for line in lines if _clean(line)])[:_MAX_SUMMARY_LEN]


def build_roleplay_part_summary(part: dict[str, Any] | None) -> str:
    part = part or {}
    progression = part.get('progression') if isinstance(part.get('progression'), dict) else {}
    transcript = part.get('transcript') if isinstance(part.get('transcript'), list) else []
    lines = [
        f"Part: {_clean(part.get('title') or 'Part', 160)}",
        f"Summary: {_clean(part.get('summary') or '', 1000)}",
        f"Scene notes: {_clean(part.get('scene_notes') or '', 900)}",
        f"Pinned canon: {_clean(part.get('pinned_canon') or '', 900)}",
        f"Beat focus: {_clean(progression.get('beat_focus') or '', 160)}",
        f"Location: {_clean(progression.get('active_location') or '', 160)}",
        f"POV: {_clean(progression.get('active_pov') or '', 160)}",
        f"Objective: {_clean(progression.get('part_objective') or '', 240)}",
        f"Tension: {_clean(progression.get('tension_level') or 'medium', 40)}",
        f"Pacing: {_clean(progression.get('pacing_target') or 'steady', 40)}",
    ]
    excerpt = _message_excerpt(transcript, limit=4)
    if excerpt:
        lines.append(f"Recent turns: {excerpt}")
    lines.append(f"Turn count: {len(transcript)}")
    return '\n'.join([line for line in lines if _clean(line)])[:_MAX_SUMMARY_LEN]


def build_roleplay_snapshot_summary(snapshot: dict[str, Any] | None) -> str:
    snapshot = snapshot or {}
    progression = snapshot.get('progression') if isinstance(snapshot.get('progression'), dict) else {}
    turns = snapshot.get('recent_turns') if isinstance(snapshot.get('recent_turns'), list) else snapshot.get('transcript') if isinstance(snapshot.get('transcript'), list) else []
    lines = [
        f"Story ID: {_clean(snapshot.get('story_id') or '', 120)}",
        f"Part ID: {_clean(snapshot.get('part_id') or '', 120)}",
        f"Rolling summary: {_clean(snapshot.get('rolling_summary') or snapshot.get('summary') or '', 1200)}",
        f"Beat focus: {_clean(progression.get('beat_focus') or '', 160)}",
        f"Location: {_clean(progression.get('active_location') or '', 160)}",
        f"POV: {_clean(progression.get('active_pov') or '', 160)}",
    ]
    excerpt = _message_excerpt(turns, limit=4)
    if excerpt:
        lines.append(f"Recent turns: {excerpt}")
    return '\n'.join([line for line in lines if _clean(line)])[:_MAX_SUMMARY_LEN]
