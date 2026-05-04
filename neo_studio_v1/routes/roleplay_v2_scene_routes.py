from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import StreamingResponse

from ..contracts.roleplay_v2_mode_model import normalize_mode_model
from ..contracts.roleplay_v2_scene_state import normalize_scene_state, scene_state_summary
from ..utils.kobold import clamp_float, clamp_int, generate_branch_options, generate_roleplay_reply, stream_roleplay_reply
from ..utils.roleplay_v2_package_store import load_saved_record
from ..utils.roleplay_v2_runtime_bundle import get_runtime_bundle
from ..utils.roleplay_v2_scene_continuity import save_scene_continuity_snapshot
from ..utils.roleplay_v2_turn_writeback import writeback_scene_turn
from ..utils.roleplay_v2_story_store import get_story_checkpoint, get_story_session, get_storyline
from .common import json_error, json_exception

router = APIRouter()


def _parse_transcript(raw: str) -> list[dict]:
    try:
        value = json.loads(raw or '[]')
        if not isinstance(value, list):
            return []
        out: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            role = str(item.get('role') or '').strip().lower()
            content = str(item.get('content') or '').strip()
            if role in {'user', 'assistant', 'system'} and content:
                out.append({'role': role, 'content': content})
        return out
    except Exception:
        return []


def _parse_scene_state(raw: str, bundle: dict) -> dict:
    try:
        value = json.loads(raw or '{}')
        payload = value if isinstance(value, dict) else {}
    except Exception:
        payload = {}
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    seed = packet.get('scene_state_seed') if isinstance(packet.get('scene_state_seed'), dict) else {}
    merged = dict(seed)
    merged.update(payload)
    return normalize_scene_state(merged)


def _text_list(items, key: str = 'text', limit: int = 3) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or item.get('summary') or item.get('title') or '').strip()
        if value:
            out.append(value)
        if len(out) >= limit:
            break
    return out


def _first_text(items, key: str = 'text') -> str:
    values = _text_list(items, key=key, limit=1)
    return values[0] if values else ''


def _section_block(title: str, lines: list[str]) -> str:
    clean_lines = [str(line or '').strip() for line in (lines or []) if str(line or '').strip()]
    if not clean_lines:
        return ''
    return f"{title}\n" + '\n'.join(f"- {line}" for line in clean_lines)


def _packet_memory_sections(packet: dict, *, scene_summary: dict, cast_labels: list[str], output_preset: str, interaction_mode: str) -> dict[str, str]:
    working_memory = packet.get('working_memory') if isinstance(packet.get('working_memory'), dict) else {}
    mode_profile = working_memory.get('mode_profile') if isinstance(working_memory.get('mode_profile'), dict) else {}
    closed_loop_guardrails = working_memory.get('closed_loop_guardrails') if isinstance(working_memory.get('closed_loop_guardrails'), dict) else {}
    session_pressure = working_memory.get('session_pressure_profile') if isinstance(working_memory.get('session_pressure_profile'), dict) else {}
    saturation_guardrails = working_memory.get('saturation_guardrails') if isinstance(working_memory.get('saturation_guardrails'), dict) else {}
    context_blocks = packet.get('context_blocks') if isinstance(packet.get('context_blocks'), dict) else {}
    entity_focus = packet.get('entity_focus') if isinstance(packet.get('entity_focus'), dict) else {}
    identity_lines = [str(entity_focus.get('label') or entity_focus.get('id') or '').strip(), str(entity_focus.get('kind') or '').strip()]
    if str(context_blocks.get('identity_block') or '').strip():
        identity_lines.append(str(context_blocks.get('identity_block') or '').strip())
    return {
        'mode_profile': _section_block('Mode-aware memory profile', [
            f"output preset: {str(output_preset or packet.get('mode') or 'roleplay').strip()}",
            f"interaction mode: {str(interaction_mode or 'roleplay').strip()}",
            f"focus: {str(mode_profile.get('focus') or '').strip()}",
            f"selection policy: {str(working_memory.get('selection_policy') or '').strip()}",
            f"packet budgets: {json.dumps(working_memory.get('packet_budgets') or {}, ensure_ascii=False)}",
            f"mode drift: {'yes' if bool(closed_loop_guardrails.get('mode_drift_detected')) else 'no'}",
        ]),
        'closed_loop_guardrails': _section_block('Closed-loop guardrails', [
            f"dominant writeback mode: {str(closed_loop_guardrails.get('dominant_writeback_mode') or '').strip()}",
            *[str(item or '').strip() for item in (closed_loop_guardrails.get('warnings') or [])[:4]],
            *[f"suggestion: {str(item or '').strip()}" for item in (closed_loop_guardrails.get('suggestions') or [])[:4]],
        ]),
        'session_pressure': _section_block('Session-long continuity pressure', [
            f"focus tags: {', '.join([str(item or '').strip() for item in (session_pressure.get('focus_tags') or []) if str(item or '').strip()])}",
            f"unresolved threads: {int(session_pressure.get('unresolved_thread_count') or 0)}",
            f"relationship pressure rows: {int(session_pressure.get('relationship_pressure_count') or 0)}",
            *[f"suggestion: {str(item or '').strip()}" for item in (session_pressure.get('suggestions') or [])[:3]],
        ]),
        'saturation_guardrails': _section_block('Recovery saturation guardrails', [
            f"dominant recovery tag: {str(saturation_guardrails.get('dominant_recovery_tag') or '').strip()}",
            *[str(item or '').strip() for item in (saturation_guardrails.get('warnings') or [])[:4]],
            *[f"suggestion: {str(item or '').strip()}" for item in (saturation_guardrails.get('suggestions') or [])[:3]],
        ]),
        'scene_state': _section_block('Scene state', [scene_summary.get('summary_text') or '']),
        'cast': _section_block('Cast focus', cast_labels[:4]),
        'identity': _section_block('Identity focus', identity_lines),
        'retrieval_query': _section_block('Retrieval query', [str(working_memory.get('retrieval_query') or '').strip()]),
        'world_facts': _section_block('World facts', _text_list(packet.get('world_facts'), key='text', limit=4)),
        'episodic_memories': _section_block('Episodic memories', _text_list(packet.get('episodic_memories'), key='text', limit=6)),
        'canon_guards': _section_block('Canon guards', _text_list(packet.get('canon_guards'), key='text', limit=4)),
        'callback_anchors': _section_block('Callback anchors', _text_list(packet.get('callback_anchors'), key='text', limit=4)),
        'relationship_beliefs': _section_block('Relationship beliefs', _text_list(packet.get('relationship_beliefs'), key='text', limit=4)),
        'shared_memories': _section_block('Shared memories', _text_list(packet.get('shared_memories'), key='summary', limit=4)),
    }


def _entity_label(entity_id: str) -> str:
    clean_id = str(entity_id or '').strip()
    if not clean_id:
        return ''
    record = load_saved_record('entity_record', clean_id) or {}
    return str(record.get('label') or clean_id).strip()


def _scene_cast_labels(scene_state: dict) -> list[str]:
    labels: list[str] = []
    for entity_id in scene_state.get('focus_stack') or scene_state.get('cast_entity_ids') or []:
        label = _entity_label(entity_id)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= 4:
            break
    return labels


def _build_scene_handoff(
    bundle: dict,
    *,
    scene_state: dict,
    scene_premise: str = '',
    scene_notes: str = '',
    tone: str = '',
    style: str = '',
    output_preset: str = '',
    interaction_mode: str = '',
) -> dict:
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    entity_focus = packet.get('entity_focus') if isinstance(packet.get('entity_focus'), dict) else {}
    working_memory = packet.get('working_memory') if isinstance(packet.get('working_memory'), dict) else {}
    continuity_guard = packet.get('continuity_guard') if isinstance(packet.get('continuity_guard'), dict) else {}
    context_blocks = packet.get('context_blocks') if isinstance(packet.get('context_blocks'), dict) else {}
    scene_summary = scene_state_summary(scene_state)
    mode_model = normalize_mode_model(
        output_preset=output_preset or scene_state.get('output_preset') or bundle.get('mode') or 'roleplay',
        interaction_mode=interaction_mode or scene_state.get('interaction_mode') or bundle.get('interaction_mode') or 'roleplay',
        prefer='output',
    )

    cast_labels = _scene_cast_labels(scene_state)
    partner_name = cast_labels[0] if cast_labels else str(entity_focus.get('label') or '').strip() or 'Scene partner'
    user_name = 'You'

    scenario = str(scene_premise or '').strip()
    if not scenario:
        scenario = str(scene_state.get('scene_goal') or '').strip()
    if not scenario:
        scenario = str(working_memory.get('retrieval_query') or '').strip()
    if not scenario:
        scenario = _first_text(packet.get('episodic_memories'))
    if not scenario:
        scenario = f'Scene with {partner_name}.'

    memory_bits: list[str] = []
    for title, key in [
        ('Identity', 'identity_block'),
        ('Relationships', 'relationship_block'),
        ('World', 'world_block'),
        ('Episodic memories', 'episodic_block'),
        ('Shared memories', 'shared_block'),
        ('Canon guards', 'guard_block'),
    ]:
        value = str(context_blocks.get(key) or '').strip()
        if value:
            memory_bits.append(f'{title}\n{value}')
    memory_bits.append(f"Scene state\n{scene_summary['summary_text']}")
    if cast_labels:
        cast_block = "\n- ".join(cast_labels)
        memory_bits.append(f"Cast\n- {cast_block}")
    memory_notes = '\n\n'.join([item for item in memory_bits if item]).strip()
    explicit_sections = _packet_memory_sections(packet, scene_summary=scene_summary, cast_labels=cast_labels, output_preset=str(mode_model.get('output_preset') or 'roleplay').strip(), interaction_mode=str(mode_model.get('interaction_mode') or 'roleplay').strip())

    note_bits: list[str] = []
    if str(scene_notes or '').strip():
        note_bits.append(str(scene_notes).strip())
    if str(scene_state.get('scene_notes') or '').strip():
        note_bits.append(str(scene_state.get('scene_notes')).strip())
    if str(continuity_guard.get('note') or '').strip():
        note_bits.append(str(continuity_guard.get('note')).strip())
    if str(working_memory.get('retrieval_query') or '').strip():
        note_bits.append(f"Runtime query: {str(working_memory.get('retrieval_query')).strip()}")
    derived_scene_notes = '\n'.join(note_bits).strip()

    combined_packet = '\n\n'.join([
        f"Mode: {str(bundle.get('mode') or 'roleplay').strip()}",
        f"Source scope: {str(bundle.get('source_scope') or '').strip()}",
        f"Source id: {str(bundle.get('source_id') or '').strip()}",
        f"Project id: {str(packet.get('project_id') or bundle.get('project_id') or '').strip()}",
        f"Narrator posture: {str(scene_state.get('narrator_posture') or '').strip()}",
        f"Continuity mode: {str(scene_state.get('continuity_mode') or '').strip()}",
        memory_notes,
    ]).strip()

    memory_pack = {
        'summary': memory_notes,
        'sections': explicit_sections,
        'selection_policy': str(working_memory.get('selection_policy') or '').strip(),
        'mode_profile': working_memory.get('mode_profile') if isinstance(working_memory.get('mode_profile'), dict) else {},
        'item_count': sum(len(packet.get(key) or []) for key in ['world_facts', 'episodic_memories', 'canon_guards', 'callback_anchors', 'relationship_beliefs']),
    }

    cast_focus = ', '.join(cast_labels[:2]) if cast_labels else partner_name
    return {
        'scenario': scenario,
        'user_name': user_name,
        'partner_name': partner_name,
        'tone': str(tone or '').strip() or 'Warm tension',
        'style': str(style or '').strip() or 'Immersive dialogue',
        'output_preset': str(mode_model.get('output_preset') or 'roleplay').strip(),
        'interaction_mode': str(mode_model.get('interaction_mode') or 'roleplay').strip(),
        'scene_notes': derived_scene_notes,
        'memory_notes': memory_notes,
        'author_note': str(continuity_guard.get('note') or '').strip(),
        'story_scope_notes': f"V2 source scope: {str(bundle.get('source_scope') or '').strip()} · {str(bundle.get('source_id') or '').strip()}",
        'part_scope_notes': f"Runtime bundle: {str(bundle.get('id') or '').strip()} · posture {str(scene_state.get('narrator_posture') or '').strip()}",
        'story_linked_context_text': str(context_blocks.get('world_block') or '').strip(),
        'part_linked_context_text': str(context_blocks.get('episodic_block') or '').strip(),
        'packet_bundle': {'combined_packet': combined_packet, 'explicit_sections': explicit_sections, 'mode_profile': working_memory.get('mode_profile') if isinstance(working_memory.get('mode_profile'), dict) else {}, 'selection_policy': str(working_memory.get('selection_policy') or '').strip()},
        'memory_pack': memory_pack,
        'active_pov': cast_focus,
        'active_cast_focus': cast_focus,
        'beat_focus': _first_text(packet.get('callback_anchors')),
        'part_objective': str(scene_state.get('scene_goal') or '').strip() or _first_text(packet.get('relationship_beliefs')),
        'scene_state_summary': scene_summary,
    }


def _build_continuity_payload(*, bundle: dict, handoff: dict, transcript: list[dict], user_message: str, reply_text: str, scene_state: dict) -> dict:
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    transcript_turns = max(0, len([item for item in transcript if isinstance(item, dict) and str(item.get('role') or '').strip().lower() == 'user']))
    summary = scene_state_summary(scene_state)
    return {
        'runtime_bundle_id': str(bundle.get('id') or '').strip(),
        'project_id': str(bundle.get('project_id') or packet.get('project_id') or '').strip(),
        'focus_label': str((packet.get('entity_focus') or {}).get('label') or (packet.get('entity_focus') or {}).get('id') or '').strip(),
        'retrieval_query': str((packet.get('working_memory') or {}).get('retrieval_query') or '').strip(),
        'continuity_note': str((packet.get('continuity_guard') or {}).get('note') or handoff.get('author_note') or '').strip(),
        'transcript_turns': transcript_turns,
        'last_user_turn': str(user_message or '').strip(),
        'last_assistant_turn': str(reply_text or '').strip(),
        'scene_state': summary['scene_state'],
        'scene_state_summary': summary['summary_text'],
        'output_preset': str(summary['scene_state'].get('output_preset') or 'roleplay').strip(),
        'interaction_mode': str(summary['scene_state'].get('interaction_mode') or 'roleplay').strip(),
    }


def _should_offer_choice_assist(*, output_preset: str = '', interaction_mode: str = '', turn_input_style: str = '') -> bool:
    clean_output = str(output_preset or '').strip().lower() or 'roleplay'
    clean_interaction = str(interaction_mode or '').strip().lower() or 'roleplay'
    clean_style = str(turn_input_style or '').strip().lower() or 'free_typing'
    return clean_output == 'roleplay' and clean_interaction == 'roleplay' and clean_style in {'choice_assist', 'hybrid'}


def _normalize_choice_assist_actions(options: list[dict] | None = None, *, tone: str = '') -> list[dict]:
    actions: list[dict] = []
    for idx, item in enumerate(options or [], start=1):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get('text') or item.get('prompt') or '').strip()
        if not prompt:
            continue
        actions.append({
            'id': str(item.get('id') or f'choice_{idx}').strip() or f'choice_{idx}',
            'label': str(item.get('label') or f'Choice {idx}').strip() or f'Choice {idx}',
            'prompt': prompt,
            'intent': 'scene_turn',
            'tone': str(tone or '').strip(),
        })
    return actions[:5]


def _resolve_story_scope(*, bundle: dict, storyline_id: str = '', session_id: str = '', checkpoint_id: str = '') -> dict:
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    storyline = get_storyline(str(storyline_id or '').strip()) if str(storyline_id or '').strip() else None
    session = get_story_session(str(session_id or '').strip()) if str(session_id or '').strip() else None
    checkpoint = get_story_checkpoint(str(checkpoint_id or '').strip()) if str(checkpoint_id or '').strip() else None
    if checkpoint and not session:
        session = get_story_session(str(checkpoint.get('session_id') or '').strip())
    if session and not storyline:
        storyline = get_storyline(str(session.get('storyline_id') or '').strip())
    if checkpoint and session and not storyline:
        storyline = get_storyline(str(session.get('storyline_id') or '').strip())
    return {
        'project_id': str((storyline or {}).get('project_id') or (session or {}).get('project_id') or packet.get('project_id') or bundle.get('project_id') or '').strip(),
        'storyline_id': str((storyline or {}).get('id') or '').strip(),
        'session_id': str((session or {}).get('id') or '').strip(),
        'checkpoint_id': str((checkpoint or {}).get('id') or '').strip(),
        'source_snapshot_id': str((checkpoint or {}).get('source_snapshot_id') or (session or {}).get('source_snapshot_id') or (storyline or {}).get('source_snapshot_id') or '').strip(),
        'canon_snapshot_id': str((checkpoint or {}).get('canon_snapshot_id') or (session or {}).get('canon_snapshot_id') or (storyline or {}).get('canon_snapshot_id') or '').strip(),
        'sandbox_id': str((checkpoint or {}).get('sandbox_id') or (session or {}).get('sandbox_id') or (storyline or {}).get('active_sandbox_id') or '').strip(),
        'branch_id': str((checkpoint or {}).get('branch_id') or (session or {}).get('branch_id') or (storyline or {}).get('root_branch_id') or '').strip(),
        'memory_scope': str((checkpoint or {}).get('memory_scope') or (session or {}).get('memory_scope') or 'sandbox').strip() or 'sandbox',
        'promotion_scope': str((checkpoint or {}).get('promotion_scope') or (session or {}).get('promotion_scope') or 'sandbox_only').strip() or 'sandbox_only',
    }


@router.post('/api/roleplay/v2/scene/turn')
async def api_roleplay_v2_scene_turn(
    bundle_id: str = Form(''),
    user_message: str = Form(''),
    transcript_json: str = Form('[]'),
    scene_state_json: str = Form('{}'),
    scene_premise: str = Form(''),
    scene_notes: str = Form(''),
    tone: str = Form('Warm tension'),
    style: str = Form('Immersive dialogue'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    model: str = Form('default'),
    mode: str = Form('reply'),
    turn_input_style: str = Form('free_typing'),
    storyline_id: str = Form(''),
    session_id: str = Form(''),
    checkpoint_id: str = Form(''),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(60),
    max_tokens: int = Form(320),
):
    try:
        prepared = await _prepare_scene_turn_inputs(
            bundle_id=bundle_id,
            user_message=user_message,
            transcript_json=transcript_json,
            scene_state_json=scene_state_json,
            scene_premise=scene_premise,
            scene_notes=scene_notes,
            tone=tone,
            style=style,
            output_preset=output_preset,
            interaction_mode=interaction_mode,
            mode=mode,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except LookupError as exc:
        return json_error(str(exc), 404)

    try:
        result = await generate_roleplay_reply(
            model=model,
            mode=prepared['clean_mode'],
            scenario=prepared['handoff']['scenario'],
            user_name=prepared['handoff']['user_name'],
            partner_name=prepared['handoff']['partner_name'],
            tone=prepared['handoff']['tone'],
            style=prepared['handoff']['style'],
            scene_notes=prepared['handoff']['scene_notes'],
            memory_notes=prepared['handoff']['memory_notes'],
            author_note=prepared['handoff']['author_note'],
            output_preset=prepared['handoff']['output_preset'],
            interaction_mode=prepared['handoff']['interaction_mode'],
            transcript=prepared['transcript'],
            user_message=prepared['clean_user_message'],
            story_scope_notes=prepared['handoff']['story_scope_notes'],
            part_scope_notes=prepared['handoff']['part_scope_notes'],
            beat_focus=prepared['handoff']['beat_focus'],
            active_pov=prepared['handoff']['active_pov'],
            active_cast_focus=prepared['handoff']['active_cast_focus'],
            part_objective=prepared['handoff']['part_objective'],
            story_linked_context_text=prepared['handoff']['story_linked_context_text'],
            part_linked_context_text=prepared['handoff']['part_linked_context_text'],
            packet_bundle=prepared['handoff']['packet_bundle'],
            memory_pack=prepared['handoff']['memory_pack'],
            temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
            top_k=clamp_int(top_k, 0, 200, 60),
            max_tokens=clamp_int(max_tokens, 96, 1200, 320),
        )
        return await _finalize_scene_turn_payload(
            bundle=prepared['bundle'],
            handoff=prepared['handoff'],
            transcript=prepared['transcript'],
            scene_state=prepared['scene_state'],
            clean_user_message=prepared['clean_user_message'],
            clean_mode=prepared['clean_mode'],
            storyline_id=storyline_id,
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            turn_input_style=turn_input_style,
            model=model,
            reply_text=str(result.get('text') or '').strip(),
            finish_reason=str(result.get('finish_reason') or '').strip(),
            reasoning_stripped=bool(result.get('reasoning_stripped')),
        )
    except Exception as exc:
        return json_exception(exc, default_message='Could not run the V2 scene turn.', default_status=500)


async def _prepare_scene_turn_inputs(
    *,
    bundle_id: str = '',
    user_message: str = '',
    transcript_json: str = '[]',
    scene_state_json: str = '{}',
    scene_premise: str = '',
    scene_notes: str = '',
    tone: str = 'Warm tension',
    style: str = 'Immersive dialogue',
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
    mode: str = 'reply',
):
    clean_bundle_id = str(bundle_id or '').strip()
    clean_user_message = str(user_message or '').strip()
    clean_mode = str(mode or 'reply').strip().lower() or 'reply'
    if not clean_bundle_id:
        raise ValueError('Select a runtime bundle first.')
    if clean_mode == 'reply' and not clean_user_message:
        raise ValueError('Type a scene turn before sending.')
    bundle = get_runtime_bundle(clean_bundle_id)
    if not bundle:
        raise LookupError('Runtime bundle not found.')
    transcript = _parse_transcript(transcript_json)
    scene_state = _parse_scene_state(scene_state_json, bundle)
    handoff = _build_scene_handoff(
        bundle,
        scene_state=scene_state,
        scene_premise=scene_premise,
        scene_notes=scene_notes,
        tone=tone,
        style=style,
        output_preset=output_preset,
        interaction_mode=interaction_mode,
    )
    return {
        'bundle': bundle,
        'transcript': transcript,
        'scene_state': scene_state,
        'handoff': handoff,
        'clean_user_message': clean_user_message,
        'clean_mode': clean_mode,
    }


async def _finalize_scene_turn_payload(
    *,
    bundle: dict,
    handoff: dict,
    transcript: list[dict],
    scene_state: dict,
    clean_user_message: str,
    clean_mode: str,
    storyline_id: str = '',
    session_id: str = '',
    checkpoint_id: str = '',
    turn_input_style: str = 'free_typing',
    model: str = 'default',
    reply_text: str = '',
    finish_reason: str = '',
    reasoning_stripped: bool = False,
    warning: str = '',
):
    reply_text = str(reply_text or '').strip()
    finish_reason = str(finish_reason or '').strip()
    warning = str(warning or '').strip()
    updated_transcript = list(transcript)
    if clean_user_message:
        updated_transcript.append({'role': 'user', 'content': clean_user_message})
    if reply_text:
        updated_transcript.append({'role': 'assistant', 'content': reply_text})
    if not reply_text and not warning:
        warning = 'The backend returned an empty scene reply.'
    elif clean_mode == 'continue' and not finish_reason and not warning:
        warning = 'Scene continued without an explicit finish reason from the backend.'

    story_scope = _resolve_story_scope(bundle=bundle, storyline_id=storyline_id, session_id=session_id, checkpoint_id=checkpoint_id)
    continuity = _build_continuity_payload(
        bundle=bundle,
        handoff=handoff,
        transcript=updated_transcript,
        user_message=clean_user_message,
        reply_text=reply_text,
        scene_state=scene_state,
    )
    continuity_saved = save_scene_continuity_snapshot(bundle=bundle, continuity=continuity, transcript=updated_transcript, scene_state=scene_state, story_scope=story_scope) if reply_text else {'ok': False, 'reason': 'empty_reply'}
    continuity = {
        **continuity,
        'saved_memory_fragment_id': str(((continuity_saved.get('memory_fragment') or {}) if isinstance(continuity_saved, dict) else {}).get('id') or '').strip(),
        'saved_shared_memory_id': str(((continuity_saved.get('shared_memory') or {}) if isinstance(continuity_saved, dict) else {}).get('id') or '').strip(),
        'saved_memory_fragment': ({
            'id': str(((continuity_saved.get('memory_fragment') or {}) if isinstance(continuity_saved, dict) else {}).get('id') or '').strip(),
            'title': str(((continuity_saved.get('memory_fragment') or {}) if isinstance(continuity_saved, dict) else {}).get('title') or '').strip(),
            'summary': str(((continuity_saved.get('memory_fragment') or {}) if isinstance(continuity_saved, dict) else {}).get('scene_ready_text') or ((continuity_saved.get('memory_fragment') or {}) if isinstance(continuity_saved, dict) else {}).get('canonical_text') or '').strip()[:360],
        } if isinstance(continuity_saved, dict) and isinstance(continuity_saved.get('memory_fragment'), dict) else {}),
        'saved_shared_memory': ({
            'id': str(((continuity_saved.get('shared_memory') or {}) if isinstance(continuity_saved, dict) else {}).get('id') or '').strip(),
            'title': str(((continuity_saved.get('shared_memory') or {}) if isinstance(continuity_saved, dict) else {}).get('title') or '').strip(),
            'summary': str(((continuity_saved.get('shared_memory') or {}) if isinstance(continuity_saved, dict) else {}).get('summary') or '').strip()[:360],
        } if isinstance(continuity_saved, dict) and isinstance(continuity_saved.get('shared_memory'), dict) else {}),
    }
    writeback = writeback_scene_turn(
        bundle=bundle,
        transcript=updated_transcript,
        scene_state=scene_state,
        continuity=continuity,
        user_message=clean_user_message,
        reply_text=reply_text,
        output_preset=handoff['output_preset'],
        interaction_mode=handoff['interaction_mode'],
        finish_reason=finish_reason,
        story_scope=story_scope,
    ) if reply_text else {'ok': False, 'reason': 'empty_reply'}
    continuity = {
        **continuity,
        'writeback_source_ref': str((writeback.get('source_ref') if isinstance(writeback, dict) else '') or '').strip(),
        'turn_summary_id': str(((writeback.get('turn_summary') or {}) if isinstance(writeback, dict) else {}).get('id') or '').strip(),
        'turn_summary_text': str(((writeback.get('turn_summary') or {}) if isinstance(writeback, dict) else {}).get('summary') or '').strip(),
        'writeback_episodic_memory': ((writeback.get('episodic_memory') or {}) if isinstance(writeback, dict) else {}),
        'writeback_relationship_drift': ((writeback.get('relationship_drift') or {}) if isinstance(writeback, dict) else {}),
        'writeback_relationship_state': ((writeback.get('relationship_state') or {}) if isinstance(writeback, dict) else {}),
        'writeback_callback_anchor': ((writeback.get('callback_anchor') or {}) if isinstance(writeback, dict) else {}),
        'writeback_unresolved_thread': ((writeback.get('unresolved_thread') or {}) if isinstance(writeback, dict) else {}),
        'writeback_shared_memory': ((writeback.get('shared_memory') or {}) if isinstance(writeback, dict) else {}),
        'writeback_promotion': ((writeback.get('promotion_report') or {}) if isinstance(writeback, dict) else {}),
        'writeback_skipped': ((writeback.get('skipped') or []) if isinstance(writeback, dict) else []),
        'writeback_sqlite_sync': ((writeback.get('sqlite_sync') or {}) if isinstance(writeback, dict) else {}),
        'writeback_scope': ((writeback.get('writeback_scope') or {}) if isinstance(writeback, dict) else {}),
    }
    suggested_actions: list[dict] = []
    suggested_actions_warning = ''
    if reply_text and _should_offer_choice_assist(output_preset=handoff['output_preset'], interaction_mode=handoff['interaction_mode'], turn_input_style=turn_input_style):
        try:
            assist = await generate_branch_options(
                model=model,
                scenario=handoff['scenario'],
                user_name=handoff['user_name'],
                partner_name=handoff['partner_name'],
                tone=handoff['tone'],
                style=handoff['style'],
                scene_notes=handoff['scene_notes'],
                memory_notes=handoff['memory_notes'],
                author_note=handoff['author_note'],
                output_preset=handoff['output_preset'],
                interaction_mode=handoff['interaction_mode'],
                story_mode='branching',
                transcript=updated_transcript,
                story_scope_notes=handoff['story_scope_notes'],
                part_scope_notes=handoff['part_scope_notes'],
                beat_focus=handoff['beat_focus'],
                active_pov=handoff['active_pov'],
                active_cast_focus=handoff['active_cast_focus'],
                part_objective=handoff['part_objective'],
                story_linked_context_text=handoff['story_linked_context_text'],
                part_linked_context_text=handoff['part_linked_context_text'],
                option_count=4,
                allow_custom_option=True,
                packet_bundle=handoff['packet_bundle'],
                memory_pack=handoff['memory_pack'],
            )
            suggested_actions = _normalize_choice_assist_actions((assist or {}).get('options') or [], tone=handoff['tone'])
        except Exception as exc:
            suggested_actions_warning = f'Choice assist could not generate suggestions: {str(exc or "unknown error").strip() or "unknown error"}'

    return {
        'ok': True,
        'message': 'Scene turn ready.',
        'reply_mode': clean_mode,
        'reply_text': reply_text,
        'transcript': updated_transcript,
        'finish_reason': finish_reason,
        'reasoning_stripped': bool(reasoning_stripped),
        'continuity': continuity,
        'scene_state': scene_state,
        'warning': warning,
        'continuity_saved': continuity_saved,
        'writeback': writeback,
        'turn_input_style': str(turn_input_style or 'free_typing').strip() or 'free_typing',
        'suggested_actions': suggested_actions,
        'suggested_actions_warning': suggested_actions_warning,
    }


@router.post('/api/roleplay/v2/scene/turn-stream')
async def api_roleplay_v2_scene_turn_stream(
    bundle_id: str = Form(''),
    user_message: str = Form(''),
    transcript_json: str = Form('[]'),
    scene_state_json: str = Form('{}'),
    scene_premise: str = Form(''),
    scene_notes: str = Form(''),
    tone: str = Form('Warm tension'),
    style: str = Form('Immersive dialogue'),
    output_preset: str = Form('roleplay'),
    interaction_mode: str = Form('roleplay'),
    model: str = Form('default'),
    mode: str = Form('reply'),
    turn_input_style: str = Form('free_typing'),
    storyline_id: str = Form(''),
    session_id: str = Form(''),
    checkpoint_id: str = Form(''),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(60),
    max_tokens: int = Form(320),
):
    try:
        prepared = await _prepare_scene_turn_inputs(
            bundle_id=bundle_id,
            user_message=user_message,
            transcript_json=transcript_json,
            scene_state_json=scene_state_json,
            scene_premise=scene_premise,
            scene_notes=scene_notes,
            tone=tone,
            style=style,
            output_preset=output_preset,
            interaction_mode=interaction_mode,
            mode=mode,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except LookupError as exc:
        return json_error(str(exc), 404)

    async def event_stream():
        visible_text = ''
        try:
            async for event in stream_roleplay_reply(
                model=model,
                mode=prepared['clean_mode'],
                scenario=prepared['handoff']['scenario'],
                user_name=prepared['handoff']['user_name'],
                partner_name=prepared['handoff']['partner_name'],
                tone=prepared['handoff']['tone'],
                style=prepared['handoff']['style'],
                scene_notes=prepared['handoff']['scene_notes'],
                memory_notes=prepared['handoff']['memory_notes'],
                author_note=prepared['handoff']['author_note'],
                output_preset=prepared['handoff']['output_preset'],
                interaction_mode=prepared['handoff']['interaction_mode'],
                transcript=prepared['transcript'],
                user_message=prepared['clean_user_message'],
                story_scope_notes=prepared['handoff']['story_scope_notes'],
                part_scope_notes=prepared['handoff']['part_scope_notes'],
                beat_focus=prepared['handoff']['beat_focus'],
                active_pov=prepared['handoff']['active_pov'],
                active_cast_focus=prepared['handoff']['active_cast_focus'],
                part_objective=prepared['handoff']['part_objective'],
                story_linked_context_text=prepared['handoff']['story_linked_context_text'],
                part_linked_context_text=prepared['handoff']['part_linked_context_text'],
                packet_bundle=prepared['handoff']['packet_bundle'],
                memory_pack=prepared['handoff']['memory_pack'],
                temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
                top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
                top_k=clamp_int(top_k, 0, 200, 60),
                max_tokens=clamp_int(max_tokens, 96, 1200, 320),
            ):
                event_type = str(event.get('type') or 'message')
                if event_type == 'delta':
                    visible_text = str(event.get('text') or visible_text)
                    payload_json = json.dumps({'delta': str(event.get('delta') or ''), 'text': visible_text}, ensure_ascii=False)
                    yield f'event: delta\ndata: {payload_json}\n\n'
                    continue
                if event_type == 'final':
                    visible_text = str(event.get('reply') or visible_text).strip()
                    payload = await _finalize_scene_turn_payload(
                        bundle=prepared['bundle'],
                        handoff=prepared['handoff'],
                        transcript=prepared['transcript'],
                        scene_state=prepared['scene_state'],
                        clean_user_message=prepared['clean_user_message'],
                        clean_mode=prepared['clean_mode'],
                        storyline_id=storyline_id,
                        session_id=session_id,
                        checkpoint_id=checkpoint_id,
                        turn_input_style=turn_input_style,
                        model=model,
                        reply_text=visible_text,
                        finish_reason=str(event.get('finish_reason') or '').strip(),
                        reasoning_stripped=bool(event.get('reasoning_stripped')),
                        warning=str(event.get('warning') or '').strip(),
                    )
                    payload_json = json.dumps(payload, ensure_ascii=False)
                    yield f'event: final\ndata: {payload_json}\n\n'
                    return
            payload = await _finalize_scene_turn_payload(
                bundle=prepared['bundle'],
                handoff=prepared['handoff'],
                transcript=prepared['transcript'],
                scene_state=prepared['scene_state'],
                clean_user_message=prepared['clean_user_message'],
                clean_mode=prepared['clean_mode'],
                storyline_id=storyline_id,
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                turn_input_style=turn_input_style,
                model=model,
                reply_text=visible_text,
                finish_reason='',
                reasoning_stripped=False,
                warning='The live scene stream ended without a final marker. Recovered the visible reply.' if visible_text else 'The live scene stream ended before any visible output arrived.',
            )
            payload_json = json.dumps(payload, ensure_ascii=False)
            yield f'event: final\ndata: {payload_json}\n\n'
        except Exception as exc:
            payload_json = json.dumps({'error': str(exc or 'Scene streaming failed.') or 'Scene streaming failed.'}, ensure_ascii=False)
            yield f'event: error\ndata: {payload_json}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
