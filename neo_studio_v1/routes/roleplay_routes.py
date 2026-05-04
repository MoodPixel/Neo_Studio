from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse

from ..utils.kobold import (
    clamp_float,
    clamp_int,
    generate_branch_options,
    generate_roleplay_reply,
    stream_roleplay_reply,
)
from ..utils.logging_utils import get_logger
from ..utils.memory_service.chroma_store import ROLEPLAY_COLLECTION, delete_memory_chunk_ids, get_embedding_backend_status
from ..utils.memory_service.roleplay_adapter import sync_roleplay_part_summary, sync_roleplay_session_snapshot, sync_roleplay_story
from ..utils.memory_service.sqlite_store import (
    delete_summary_record_ids,
    execute,
    fetch_memory_chunks,
    fetch_memory_write_logs,
    fetch_summary_records,
    mark_memory_chunk_ids_deleted,
    record_memory_write,
)
from ..utils.memory_service.retriever import build_memory_pack
from ..utils.roleplay_library_store import get_record
from ..utils.roleplay_packet_builder import build_runtime_roleplay_bundle
from ..utils.roleplay_story_store import linked_context_summary, normalize_linked_context, get_story_record
from ..utils.roleplay_session_store import get_part_record, list_story_parts, load_latest_session_snapshot
from .common import json_exception

logger = get_logger(__name__)
router = APIRouter()


def _parse_json_list(raw: str) -> list:
    try:
        value = json.loads(raw or '[]')
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _parse_linked_context(raw: str) -> dict:
    try:
        value = normalize_linked_context(raw or '{}')
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _resolve_support_records(cast_items: list, user_character_id: str, partner_character_id: str) -> list[dict]:
    support_character_records = []
    seen_support_ids = set()
    for row in cast_items:
        if not isinstance(row, dict):
            continue
        cid = str(row.get('character_id') or '').strip()
        if not cid or cid in seen_support_ids or cid in {str(user_character_id or '').strip(), str(partner_character_id or '').strip()}:
            continue
        seen_support_ids.add(cid)
        rec = get_record('character', cid)
        if rec:
            support_character_records.append(rec)
    return support_character_records


def _roleplay_related_chunks(story_id: str, part_id: str, limit: int = 120) -> list[dict]:
    rows = fetch_memory_chunks(lane='roleplay', limit=max(12, limit))
    out = []
    seen = set()
    snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
    for row in rows:
        chunk_id = str(row.get('chunk_id') or '').strip()
        if not chunk_id or chunk_id in seen:
            continue
        scope_type = str(row.get('scope_type') or '').strip()
        scope_id = str(row.get('scope_id') or '').strip()
        entity_id = str(row.get('entity_id') or '').strip()
        keep = False
        if story_id and (entity_id == story_id or scope_id == story_id):
            keep = True
        if part_id and (entity_id == part_id or (scope_type == 'part' and scope_id == part_id)):
            keep = True
        if snapshot_id and entity_id == snapshot_id:
            keep = True
        if keep:
            out.append(row)
            seen.add(chunk_id)
        if len(out) >= max(8, limit):
            break
    return out


def _roleplay_related_summaries(story_id: str, part_id: str) -> list[dict]:
    rows = fetch_summary_records(lane='roleplay', limit=120)
    out = []
    seen = set()
    snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
    for row in rows:
        rid = str(row.get('summary_record_id') or '').strip()
        if not rid or rid in seen:
            continue
        scope_type = str(row.get('scope_type') or '').strip()
        scope_id = str(row.get('scope_id') or '').strip()
        if (story_id and scope_type == 'story' and scope_id == story_id) or (part_id and scope_type == 'part' and scope_id == part_id) or (snapshot_id and scope_type == 'snapshot' and scope_id == snapshot_id):
            out.append(row)
            seen.add(rid)
        if len(out) >= 8:
            break
    return out


def _roleplay_related_writes(story_id: str, part_id: str) -> list[dict]:
    rows = fetch_memory_write_logs(lane='roleplay', limit=120)
    out = []
    snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
    for row in rows:
        entity_id = str(row.get('entity_id') or '').strip()
        if entity_id in {story_id, part_id, snapshot_id}:
            out.append(row)
        if len(out) >= 8:
            break
    return out


def _roleplay_continuity_payload(story_id: str = '', part_id: str = '', preview_text: str = '') -> dict:
    clean_story_id = str(story_id or '').strip()
    clean_part_id = str(part_id or '').strip()
    story = get_story_record(clean_story_id) if clean_story_id else None
    part = get_part_record(clean_part_id) if clean_part_id else None
    snapshot = load_latest_session_snapshot() or {}
    if not clean_story_id and isinstance(snapshot, dict):
        clean_story_id = str(snapshot.get('story_id') or '').strip()
        story = get_story_record(clean_story_id) if clean_story_id else story
    if not clean_part_id and isinstance(snapshot, dict):
        clean_part_id = str(snapshot.get('part_id') or '').strip()
        part = get_part_record(clean_part_id) if clean_part_id else part
    if not clean_story_id and not clean_part_id:
        raise ValueError('No active story or part is linked yet.')
    if not part and clean_part_id:
        raise ValueError('Roleplay part not found.')
    if not story and clean_story_id:
        raise ValueError('Roleplay story not found.')
    transcript = snapshot.get('transcript') if isinstance(snapshot.get('transcript'), list) else []
    memory_pack = _build_roleplay_memory_pack(
        story_id=clean_story_id,
        part_id=clean_part_id,
        scenario=str((snapshot or {}).get('scenario') or '').strip(),
        story_title=str((story or {}).get('title') or '').strip(),
        part_title=str((part or {}).get('title') or '').strip(),
        user_name=str((snapshot or {}).get('user_name') or '').strip(),
        partner_name=str((snapshot or {}).get('partner_name') or '').strip(),
        scene_notes=str((snapshot or {}).get('scene_notes') or '').strip(),
        memory_notes=str((snapshot or {}).get('memory_notes') or '').strip(),
        author_note=str((snapshot or {}).get('author_note') or '').strip(),
        story_scope_notes=str((snapshot or {}).get('story_scope_notes') or '').strip(),
        chapter_scope_notes=str((snapshot or {}).get('chapter_scope_notes') or '').strip(),
        part_scope_notes=str((snapshot or {}).get('part_scope_notes') or '').strip(),
        transcript=transcript,
        user_message=str(preview_text or '').strip(),
    )
    return {
        'story_id': clean_story_id,
        'part_id': clean_part_id,
        'backend': get_embedding_backend_status(),
        'retrieval_preview': {
            'summary': str(memory_pack.get('summary') or '').strip(),
            'item_count': int(memory_pack.get('item_count') or 0),
            'candidate_count': int(memory_pack.get('candidate_count') or 0),
            'diagnostics': memory_pack.get('diagnostics') if isinstance(memory_pack.get('diagnostics'), dict) else {},
            'items': [{
                'id': str(item.get('id') or '').strip(),
                'document': str(item.get('document') or '').strip(),
                'score': float(item.get('score') or 0.0),
                'overlap': float(item.get('overlap') or 0.0),
                'source': str(item.get('source') or '').strip(),
                'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
                'diagnostics': item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {},
            } for item in (memory_pack.get('items') if isinstance(memory_pack.get('items'), list) else [])],
        },
        'recent_chunks': _roleplay_related_chunks(clean_story_id, clean_part_id)[:8],
        'summaries': _roleplay_related_summaries(clean_story_id, clean_part_id)[:8],
        'recent_writes': _roleplay_related_writes(clean_story_id, clean_part_id)[:8],
    }


def _roleplay_scope_chunk_ids(scope_type: str, story_id: str, part_id: str, chunk_type: str = '') -> list[str]:
    rows = fetch_memory_chunks(lane='roleplay', include_deleted=False, limit=5000)
    ids: list[str] = []
    snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
    part_ids = {str(item.get('id') or '').strip() for item in (list_story_parts(story_id) if story_id else []) if str(item.get('id') or '').strip()}
    for row in rows:
        chunk_id = str(row.get('chunk_id') or '').strip()
        if not chunk_id:
            continue
        entity_id = str(row.get('entity_id') or '').strip()
        scope_id = str(row.get('scope_id') or '').strip()
        row_scope_type = str(row.get('scope_type') or '').strip()
        row_chunk_type = str(row.get('chunk_type') or '').strip()
        if chunk_type and row_chunk_type != chunk_type:
            continue
        if scope_type == 'story':
            if (story_id and (entity_id == story_id or scope_id == story_id or entity_id in part_ids or entity_id == snapshot_id)):
                ids.append(chunk_id)
        elif scope_type == 'part':
            if part_id and (entity_id == part_id or (row_scope_type == 'part' and scope_id == part_id) or entity_id == snapshot_id):
                ids.append(chunk_id)
        elif scope_type == 'snapshot':
            if snapshot_id and entity_id == snapshot_id:
                ids.append(chunk_id)
    return ids


def _build_roleplay_memory_pack(
    *,
    story_id: str = '',
    part_id: str = '',
    scenario: str = '',
    story_title: str = '',
    part_title: str = '',
    user_name: str = '',
    partner_name: str = '',
    scene_notes: str = '',
    memory_notes: str = '',
    author_note: str = '',
    story_scope_notes: str = '',
    chapter_scope_notes: str = '',
    part_scope_notes: str = '',
    transcript: list | None = None,
    user_message: str = '',
) -> dict:
    latest_user = str(user_message or '').strip()
    if not latest_user:
        for item in reversed(transcript or []):
            if isinstance(item, dict) and str(item.get('role') or '').strip().lower() == 'user':
                latest_user = str(item.get('content') or '').strip()
                if latest_user:
                    break
    scope = {
        'campaign_id': str(story_id or '').strip(),
        'story_id': str(story_id or '').strip(),
        'part_id': str(part_id or '').strip(),
        'scenario': str(scenario or '').strip(),
        'story_title': str(story_title or '').strip(),
        'part_title': str(part_title or '').strip(),
        'user_name': str(user_name or '').strip(),
        'partner_name': str(partner_name or '').strip(),
        'scene_notes': str(scene_notes or '').strip(),
        'memory_notes': str(memory_notes or '').strip(),
        'author_note': str(author_note or '').strip(),
        'story_scope_notes': str(story_scope_notes or '').strip(),
        'chapter_scope_notes': str(chapter_scope_notes or '').strip(),
        'part_scope_notes': str(part_scope_notes or '').strip(),
    }
    query_bits = [
        latest_user,
        scope['story_title'],
        scope['part_title'],
        scope['scenario'],
        scope['scene_notes'],
        scope['memory_notes'],
        scope['author_note'],
        scope['story_scope_notes'],
        scope['chapter_scope_notes'],
        scope['part_scope_notes'],
        scope['partner_name'],
    ]
    return build_memory_pack('roleplay', scope=scope, query_text='\n'.join(bit for bit in query_bits if bit))


@router.post('/api/roleplay-reply-stream')
async def api_roleplay_reply_stream(
    model: str = Form('default'),
    mode: str = Form('reply'),
    scenario: str = Form(''),
    user_name: str = Form(''),
    partner_name: str = Form(''),
    tone: str = Form(''),
    custom_tone: str = Form(''),
    style: str = Form('Immersive dialogue'),
    user_character_id: str = Form(''),
    partner_character_id: str = Form(''),
    world_id: str = Form(''),
    scenario_id: str = Form(''),
    story_id: str = Form(''),
    part_id: str = Form(''),
    cast_json: str = Form('[]'),
    scene_notes: str = Form(''),
    memory_notes: str = Form(''),
    author_note: str = Form(''),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    input_intent: str = Form('auto'),
    continuous_scene_mode: bool = Form(False),
    story_mode: str = Form('linear'),
    option_count: int = Form(3),
    allow_custom_option: bool = Form(True),
    transcript_json: str = Form('[]'),
    user_message: str = Form(''),
    story_scope_notes: str = Form(''),
    chapter_scope_notes: str = Form(''),
    part_scope_notes: str = Form(''),
    chapter_index: int = Form(1),
    chapter_label: str = Form(''),
    part_index: int = Form(1),
    beat_focus: str = Form(''),
    active_pov: str = Form(''),
    active_location: str = Form(''),
    active_cast_focus: str = Form(''),
    part_objective: str = Form(''),
    tension_level: str = Form('medium'),
    pacing_target: str = Form('steady'),
    story_linked_context_json: str = Form('{}'),
    part_linked_context_json: str = Form('{}'),
    story_linked_context_text: str = Form(''),
    part_linked_context_text: str = Form(''),
    max_tokens: int = Form(320),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(60),
):
    transcript = _parse_json_list(transcript_json)
    cast_items = _parse_json_list(cast_json)
    story_linked_context = _parse_linked_context(story_linked_context_json)
    part_linked_context = _parse_linked_context(part_linked_context_json)
    story_linked_context_text = str(story_linked_context_text or '').strip() or linked_context_summary(story_linked_context, 'Story linked context')
    part_linked_context_text = str(part_linked_context_text or '').strip() or linked_context_summary(part_linked_context, 'Part linked context')

    try:
        user_character = get_record('character', user_character_id)
        partner_character = get_record('character', partner_character_id)
        world_record = get_record('world', world_id)
        scenario_record = get_record('scenario', scenario_id)
        location_record = None
        if isinstance(scenario_record, dict):
            location_record = get_record('location', str(scenario_record.get('location_id') or '').strip())
        if not location_record and isinstance(user_character, dict):
            location_record = get_record('location', str(user_character.get('current_location_id') or '').strip())
        support_character_records = _resolve_support_records(cast_items, user_character_id, partner_character_id)
        packet = build_runtime_roleplay_bundle(
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            user_character_record=user_character,
            partner_character_record=partner_character,
            world_record=world_record,
            scenario_record=scenario_record,
            location_record=location_record,
            support_character_records=support_character_records,
            cast_items=cast_items,
            max_tokens=clamp_int(max_tokens, 96, 1200, 320),
            temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
            top_k=clamp_int(top_k, 0, 200, 60),
        )
        memory_pack = _build_roleplay_memory_pack(
            story_id=story_id,
            part_id=part_id,
            scenario=scenario,
            story_title=str((packet.get('story_header') or {}).get('title') or '').strip(),
            part_title=str((packet.get('part_header') or {}).get('title') or '').strip(),
            user_name=user_name,
            partner_name=partner_name,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            story_scope_notes=story_scope_notes,
            chapter_scope_notes=chapter_scope_notes,
            part_scope_notes=part_scope_notes,
            transcript=transcript,
            user_message=user_message,
        )
    except Exception as exc:
        return json_exception(exc, default_message='Could not prepare the roleplay stream.', default_status=500, logger_override=logger, context='roleplay streaming setup')

    async def event_stream():
        yield 'event: ready\ndata: {"type": "ready"}\n\n'
        try:
            async for event in stream_roleplay_reply(
                model=model,
                mode=mode,
                scenario=scenario,
                user_name=user_name,
                partner_name=partner_name,
                tone=tone,
                custom_tone=custom_tone,
                style=style,
                scene_notes=scene_notes,
                memory_notes=memory_notes,
                author_note=author_note,
                canon_mode=canon_mode,
                output_preset=output_preset,
                interaction_mode=interaction_mode,
                input_intent=input_intent,
                continuous_scene_mode=continuous_scene_mode,
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
                user_character_record=user_character,
                partner_character_record=partner_character,
                world_record=world_record,
                scenario_record=scenario_record,
                location_record=location_record,
                support_character_records=support_character_records,
                cast_items=cast_items,
                transcript=transcript,
                user_message=user_message,
                max_tokens=clamp_int(max_tokens, 96, 1200, 320),
                temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
                top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
                top_k=clamp_int(top_k, 0, 200, 60),
                packet_bundle=packet,
                memory_pack=memory_pack,
            ):
                event_type = str(event.get('type') or 'message')
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {payload}\n\n"
        except Exception as exc:
            logger.exception('Roleplay stream failed mid-flight')
            payload = json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@router.post('/api/roleplay-branch-options')
async def api_roleplay_branch_options(
    model: str = Form('default'),
    scenario: str = Form(''),
    user_name: str = Form(''),
    partner_name: str = Form(''),
    tone: str = Form(''),
    custom_tone: str = Form(''),
    style: str = Form('Immersive dialogue'),
    user_character_id: str = Form(''),
    partner_character_id: str = Form(''),
    world_id: str = Form(''),
    scenario_id: str = Form(''),
    story_id: str = Form(''),
    part_id: str = Form(''),
    cast_json: str = Form('[]'),
    scene_notes: str = Form(''),
    memory_notes: str = Form(''),
    author_note: str = Form(''),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    story_mode: str = Form('branching'),
    transcript_json: str = Form('[]'),
    story_scope_notes: str = Form(''),
    chapter_scope_notes: str = Form(''),
    part_scope_notes: str = Form(''),
    chapter_index: int = Form(1),
    chapter_label: str = Form(''),
    part_index: int = Form(1),
    beat_focus: str = Form(''),
    active_pov: str = Form(''),
    active_location: str = Form(''),
    active_cast_focus: str = Form(''),
    part_objective: str = Form(''),
    tension_level: str = Form('medium'),
    pacing_target: str = Form('steady'),
    story_linked_context_json: str = Form('{}'),
    part_linked_context_json: str = Form('{}'),
    story_linked_context_text: str = Form(''),
    part_linked_context_text: str = Form(''),
    option_count: int = Form(3),
    allow_custom_option: bool = Form(True),
):
    transcript = _parse_json_list(transcript_json)
    cast_items = _parse_json_list(cast_json)
    story_linked_context = _parse_linked_context(story_linked_context_json)
    part_linked_context = _parse_linked_context(part_linked_context_json)
    story_linked_context_text = str(story_linked_context_text or '').strip() or linked_context_summary(story_linked_context, 'Story linked context')
    part_linked_context_text = str(part_linked_context_text or '').strip() or linked_context_summary(part_linked_context, 'Part linked context')
    try:
        user_character = get_record('character', user_character_id)
        partner_character = get_record('character', partner_character_id)
        world_record = get_record('world', world_id)
        scenario_record = get_record('scenario', scenario_id)
        location_record = None
        if isinstance(scenario_record, dict):
            location_record = get_record('location', str(scenario_record.get('location_id') or '').strip())
        support_character_records = _resolve_support_records(cast_items, user_character_id, partner_character_id)
        packet = build_runtime_roleplay_bundle(
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            user_character_record=user_character,
            partner_character_record=partner_character,
            world_record=world_record,
            scenario_record=scenario_record,
            location_record=location_record,
            support_character_records=support_character_records,
            cast_items=cast_items,
        )
        memory_pack = _build_roleplay_memory_pack(
            story_id=story_id,
            part_id=part_id,
            scenario=scenario,
            story_title=str((packet.get('story_header') or {}).get('title') or '').strip(),
            part_title=str((packet.get('part_header') or {}).get('title') or '').strip(),
            user_name=user_name,
            partner_name=partner_name,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            story_scope_notes=story_scope_notes,
            chapter_scope_notes=chapter_scope_notes,
            part_scope_notes=part_scope_notes,
            transcript=transcript,
        )
        data = await generate_branch_options(
            model=model,
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            user_character_record=user_character,
            partner_character_record=partner_character,
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
            story_mode=story_mode,
            transcript=transcript,
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
            option_count=option_count,
            allow_custom_option=allow_custom_option,
            packet_bundle=packet,
            memory_pack=memory_pack,
        )
        return JSONResponse({'ok': True, **data})
    except Exception as exc:
        return json_exception(exc, default_status=400, logger_override=logger, context='roleplay branch options')


@router.post('/api/roleplay-reply')
async def api_roleplay_reply(
    model: str = Form('default'),
    mode: str = Form('reply'),
    scenario: str = Form(''),
    user_name: str = Form(''),
    partner_name: str = Form(''),
    tone: str = Form(''),
    custom_tone: str = Form(''),
    style: str = Form('Immersive dialogue'),
    user_character_id: str = Form(''),
    partner_character_id: str = Form(''),
    world_id: str = Form(''),
    scenario_id: str = Form(''),
    story_id: str = Form(''),
    part_id: str = Form(''),
    cast_json: str = Form('[]'),
    scene_notes: str = Form(''),
    memory_notes: str = Form(''),
    author_note: str = Form(''),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    input_intent: str = Form('auto'),
    continuous_scene_mode: bool = Form(False),
    story_mode: str = Form('linear'),
    option_count: int = Form(3),
    allow_custom_option: bool = Form(True),
    transcript_json: str = Form('[]'),
    user_message: str = Form(''),
    story_scope_notes: str = Form(''),
    chapter_scope_notes: str = Form(''),
    part_scope_notes: str = Form(''),
    chapter_index: int = Form(1),
    chapter_label: str = Form(''),
    part_index: int = Form(1),
    beat_focus: str = Form(''),
    active_pov: str = Form(''),
    active_location: str = Form(''),
    active_cast_focus: str = Form(''),
    part_objective: str = Form(''),
    tension_level: str = Form('medium'),
    pacing_target: str = Form('steady'),
    story_linked_context_json: str = Form('{}'),
    part_linked_context_json: str = Form('{}'),
    story_linked_context_text: str = Form(''),
    part_linked_context_text: str = Form(''),
    max_tokens: int = Form(320),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(60),
):
    transcript = _parse_json_list(transcript_json)
    cast_items = _parse_json_list(cast_json)
    story_linked_context = _parse_linked_context(story_linked_context_json)
    part_linked_context = _parse_linked_context(part_linked_context_json)
    story_linked_context_text = str(story_linked_context_text or '').strip() or linked_context_summary(story_linked_context, 'Story linked context')
    part_linked_context_text = str(part_linked_context_text or '').strip() or linked_context_summary(part_linked_context, 'Part linked context')
    try:
        user_character = get_record('character', user_character_id)
        partner_character = get_record('character', partner_character_id)
        world_record = get_record('world', world_id)
        scenario_record = get_record('scenario', scenario_id)
        location_record = None
        if isinstance(scenario_record, dict):
            location_record = get_record('location', str(scenario_record.get('location_id') or '').strip())
        if not location_record and isinstance(user_character, dict):
            location_record = get_record('location', str(user_character.get('current_location_id') or '').strip())
        support_character_records = _resolve_support_records(cast_items, user_character_id, partner_character_id)
        packet = build_runtime_roleplay_bundle(
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            user_character_record=user_character,
            partner_character_record=partner_character,
            world_record=world_record,
            scenario_record=scenario_record,
            location_record=location_record,
            support_character_records=support_character_records,
            cast_items=cast_items,
            max_tokens=clamp_int(max_tokens, 96, 1200, 320),
            temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
            top_k=clamp_int(top_k, 0, 200, 60),
        )
        memory_pack = _build_roleplay_memory_pack(
            story_id=story_id,
            part_id=part_id,
            scenario=scenario,
            story_title=str((packet.get('story_header') or {}).get('title') or '').strip(),
            part_title=str((packet.get('part_header') or {}).get('title') or '').strip(),
            user_name=user_name,
            partner_name=partner_name,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            story_scope_notes=story_scope_notes,
            chapter_scope_notes=chapter_scope_notes,
            part_scope_notes=part_scope_notes,
            transcript=transcript,
            user_message=user_message,
        )
        result = await generate_roleplay_reply(
            model=model,
            mode=mode,
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            interaction_mode=interaction_mode,
            input_intent=input_intent,
            continuous_scene_mode=continuous_scene_mode,
            story_mode=story_mode,
            option_count=option_count,
            allow_custom_option=allow_custom_option,
            user_character_record=user_character,
            partner_character_record=partner_character,
            world_record=world_record,
            scenario_record=scenario_record,
            location_record=location_record,
            support_character_records=support_character_records,
            cast_items=cast_items,
            transcript=transcript,
            user_message=user_message,
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
            max_tokens=clamp_int(max_tokens, 96, 1200, 320),
            temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
            top_k=clamp_int(top_k, 0, 200, 60),
            packet_bundle=packet,
            memory_pack=memory_pack,
        )
    except Exception as exc:
        return json_exception(exc, default_message='Could not prepare the roleplay request.', default_status=500, logger_override=logger, context='roleplay reply')

    finish_reason = str(result.get('finish_reason') or '').strip()
    reasoning_stripped = bool(result.get('reasoning_stripped'))
    warning = ''
    if reasoning_stripped and not result.get('text', '').strip():
        warning = 'Visible reasoning was stripped, but no final in-scene reply came back. Raise max tokens or use a non-thinking preset.'
    elif finish_reason == 'length':
        warning = 'That turn may have clipped. Regenerate, Continue scene, or raise max tokens.'
    elif reasoning_stripped:
        warning = 'Visible reasoning was stripped automatically. Showing the in-scene reply only.'

    return JSONResponse({
        'ok': True,
        'reply': result.get('text', ''),
        'finish_reason': finish_reason,
        'warning': warning,
        'reasoning_stripped': reasoning_stripped,
        'memory_item_count': int(result.get('memory_item_count') or 0),
        'message': 'Roleplay turn ready.',
    })


@router.get('/api/roleplay/continuity-inspect')
async def api_roleplay_continuity_inspect(story_id: str = '', part_id: str = '', q: str = ''):
    try:
        payload = _roleplay_continuity_payload(story_id=story_id, part_id=part_id, preview_text=q)
        return JSONResponse({'ok': True, **payload})
    except ValueError as exc:
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse({'ok': False, 'error': str(exc) or 'Could not inspect Roleplay continuity.'}, status_code=500)


@router.post('/api/roleplay/continuity-repair')
async def api_roleplay_continuity_repair(payload: dict):
    story_id = str((payload or {}).get('story_id') or '').strip()
    part_id = str((payload or {}).get('part_id') or '').strip()
    story = get_story_record(story_id) if story_id else None
    part = get_part_record(part_id) if part_id else None
    snapshot = load_latest_session_snapshot() or {}
    if story:
        sync_roleplay_story(story, source_json_path='')
    if part:
        sync_roleplay_part_summary(part, source_json_path='', summary_type='part_save')
    if isinstance(snapshot, dict) and ((story_id and str(snapshot.get('story_id') or '').strip() == story_id) or (part_id and str(snapshot.get('part_id') or '').strip() == part_id)):
        sync_roleplay_session_snapshot(snapshot, source_json_path='')
    result = _roleplay_continuity_payload(story_id=story_id, part_id=part_id, preview_text=str((payload or {}).get('q') or '').strip())
    return JSONResponse({'ok': True, **result, 'message': 'Roleplay continuity memory rebuilt for the active scope.'})


@router.post('/api/roleplay/continuity-reset')
async def api_roleplay_continuity_reset(payload: dict):
    scope_type = str((payload or {}).get('scope_type') or '').strip().lower()
    story_id = str((payload or {}).get('story_id') or '').strip()
    part_id = str((payload or {}).get('part_id') or '').strip()
    chunk_type = str((payload or {}).get('chunk_type') or '').strip().lower()
    if chunk_type in {'all', 'any'}:
        chunk_type = ''
    if scope_type not in {'story', 'part', 'snapshot'}:
        return JSONResponse({'ok': False, 'error': 'Pick a valid continuity scope to reset.'}, status_code=400)
    if scope_type == 'story' and not story_id:
        return JSONResponse({'ok': False, 'error': 'No story is selected.'}, status_code=400)
    if scope_type == 'part' and not part_id:
        return JSONResponse({'ok': False, 'error': 'No part is selected.'}, status_code=400)
    chunk_ids = _roleplay_scope_chunk_ids(scope_type, story_id, part_id, chunk_type=chunk_type)
    sqlite_deleted = mark_memory_chunk_ids_deleted(chunk_ids)
    delete_memory_chunk_ids(ROLEPLAY_COLLECTION, chunk_ids)
    summary_deleted = 0
    if not chunk_type or chunk_type == 'summary':
        if scope_type == 'story':
            part_ids = {str(item.get('id') or '').strip() for item in list_story_parts(story_id)}
            snapshot_prefix = f'{story_id}::'
            summary_rows = [row for row in fetch_summary_records(lane='roleplay', limit=2000) if (str(row.get('scope_type') or '').strip() == 'story' and str(row.get('scope_id') or '').strip() == story_id) or (str(row.get('scope_type') or '').strip() == 'part' and str(row.get('scope_id') or '').strip() in part_ids) or (str(row.get('scope_type') or '').strip() == 'snapshot' and str(row.get('scope_id') or '').strip().startswith(snapshot_prefix))]
            summary_deleted = delete_summary_record_ids([str(row.get('summary_record_id') or '').strip() for row in summary_rows])
            execute('DELETE FROM roleplay_session_summaries WHERE story_id=?', (story_id,))
        elif scope_type == 'part':
            snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
            summary_rows = [row for row in fetch_summary_records(lane='roleplay', limit=1000) if (str(row.get('scope_type') or '').strip() == 'part' and str(row.get('scope_id') or '').strip() == part_id) or (snapshot_id and str(row.get('scope_type') or '').strip() == 'snapshot' and str(row.get('scope_id') or '').strip() == snapshot_id)]
            summary_deleted = delete_summary_record_ids([str(row.get('summary_record_id') or '').strip() for row in summary_rows])
            execute('DELETE FROM roleplay_session_summaries WHERE part_id=?', (part_id,))
        else:
            snapshot_id = f'{story_id}::{part_id}' if story_id or part_id else ''
            summary_rows = [row for row in fetch_summary_records(lane='roleplay', scope_type='snapshot', limit=200) if str(row.get('scope_id') or '').strip() == snapshot_id]
            summary_deleted = delete_summary_record_ids([str(row.get('summary_record_id') or '').strip() for row in summary_rows])
            execute('DELETE FROM roleplay_session_summaries WHERE story_id=? AND part_id=? AND summary_type=?', (story_id, part_id, 'autosave'))
    record_memory_write(write_log_id=f'rwl_reset_{scope_type}_{story_id}_{part_id}_{chunk_type or "all"}', lane='roleplay', entity_type=scope_type, entity_id=part_id if scope_type != 'story' else story_id, operation='reset', details={'chunk_type': chunk_type or 'all', 'sqlite_chunks_deleted': sqlite_deleted, 'summary_records_deleted': summary_deleted})
    scope_label = f"{scope_type} {chunk_type.replace('_', ' ')}" if chunk_type else scope_type
    response = {'ok': True, 'message': f'Roleplay {scope_label} continuity reset.'}
    try:
        response.update(_roleplay_continuity_payload(story_id=story_id, part_id=part_id))
    except Exception:
        pass
    return JSONResponse(response)
