from __future__ import annotations

from typing import Any, Iterable

from .roleplay_foundation import ROLEPLAY_OUTPUT_PRESETS, ROLEPLAY_CANON_MODES


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _lines(items: Iterable[tuple[str, Any]]) -> list[str]:
    out: list[str] = []
    for label, value in items:
        clean = _clean(value)
        if clean:
            out.append(f"{label}: {clean}")
    return out


def compile_named_packet(title: str, lines: list[str]) -> str:
    body = '\n'.join([line for line in lines if _clean(line)])
    if not body:
        return ''
    return f"[{title}]\n{body}"


def _summarize_items(items: Any, mapper) -> str:
    rows = []
    for item in (items if isinstance(items, list) else []):
      text = _clean(mapper(item or {}))
      if text:
        rows.append(text)
    return '; '.join(rows)


def compile_universe_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('UNIVERSE', _lines([
        ('Name', record.get('name')),
        ('Summary', record.get('summary')),
        ('Canon Notes', record.get('canon_notes')),
    ]))


def compile_world_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('WORLD', _lines([
        ('Name', record.get('name')),
        ('Realm Type', record.get('realm_type')),
        ('Summary', record.get('summary')),
        ('Calendar Notes', record.get('calendar_notes')),
        ('Lore', record.get('lore')),
        ('Rules', record.get('rules')),
        ('Macro Geography', record.get('geography_notes')),
        ('Society / Power', record.get('society_notes')),
        ('Faith / Law / Magic', record.get('faith_notes')),
        ('Peoples / Creatures / Hidden', record.get('people_notes')),
        ('Inhabitant Species', ', '.join(record.get('inhabitant_species_names') or [])),
        ('Creatures / Fauna', ', '.join(record.get('creature_fauna_names') or [])),
        ('Cycles / Systems', ', '.join(record.get('cycle_names') or [])),
        ('Organizations / Factions', ', '.join(record.get('organization_names') or [])),
        ('Canon Notes', record.get('canon_notes')),
    ]))



def compile_location_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('LOCATION', _lines([
        ('Name', record.get('display_name') or record.get('name') or record.get('function_label')),
        ('Type', record.get('location_type')),
        ('Atmosphere', record.get('atmosphere')),
        ('Summary', record.get('summary')),
        ('Access Notes', record.get('access_notes')),
        ('Hazards', record.get('hazards')),
        ('Rules / Taboos', record.get('rules')),
        ('Public Notes', record.get('public_notes')),
        ('Hidden Truth', record.get('hidden_truth')),
        ('Artifacts Here', ', '.join(record.get('artifact_names') or [])),
        ('Rituals Here', ', '.join(record.get('ritual_names') or [])),
        ('Cycles Here', ', '.join(record.get('cycle_names') or [])),
        ('Organizations Here', ', '.join(record.get('organization_names') or [])),
        ('Canon Notes', record.get('canon_notes')),
    ]))


def compile_supporting_cast_packet(records: Any) -> str:
    rows = []
    for record in (records if isinstance(records, list) else []):
        if not isinstance(record, dict):
            continue
        name = _clean(record.get('display_name') or record.get('name'))
        if not name:
            continue
        summary = _clean(record.get('summary'))
        species = _clean(record.get('species'))
        role_tier = _clean(record.get('role_tier'))
        rows.append(' — '.join([part for part in [name, role_tier, species, summary] if part]))
    return compile_named_packet('SUPPORTING CAST', _lines([('Linked Characters', '; '.join(rows))]))


def compile_relevant_links_packet(title: str, values: Any) -> str:
    cleaned = []
    seen = set()
    for value in (values if isinstance(values, list) else []):
        text = _clean(value)
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return compile_named_packet(title, _lines([('Relevant', '; '.join(cleaned))]))


def compile_organization_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('ORGANIZATION / FACTION', _lines([
        ('Name', record.get('display_name') or record.get('name')),
        ('Type', record.get('group_type')),
        ('Summary', record.get('summary')),
        ('Leadership', record.get('leadership')),
        ('Beliefs', record.get('beliefs')),
        ('Goals', record.get('goals')),
        ('Reputation', record.get('reputation')),
        ('Resources', record.get('resources')),
        ('Membership Rules', record.get('membership_rules')),
        ('Public Face', record.get('public_face')),
        ('Hidden Truth', record.get('hidden_truth')),
        ('Allies', ', '.join(record.get('ally_organization_names') or [])),
        ('Rivals', ', '.join(record.get('rival_organization_names') or [])),
        ('Canon Notes', record.get('canon_notes')),
    ]))

def compile_character_packet(record: dict[str, Any] | None, section_title: str = 'CHARACTER') -> str:
    record = record or {}
    relationships = _summarize_items(record.get('relationships'), lambda row: f"{_clean(row.get('relationship_type')).replace('_', ' ').title()}: {_clean(row.get('target_name'))} {('- ' + _clean(row.get('notes'))) if _clean(row.get('notes')) else ''}".strip())
    abilities = _summarize_items(record.get('abilities'), lambda row: f"{_clean(row.get('name'))} ({_clean(row.get('state')) or 'active'}) {('- ' + _clean(row.get('notes'))) if _clean(row.get('notes')) else ''}".strip())
    hooks = _summarize_items(record.get('story_hooks'), lambda row: f"{_clean(row.get('type')).replace('_', ' ').title()}: {_clean(row.get('title'))} {('- ' + _clean(row.get('notes'))) if _clean(row.get('notes')) else ''}".strip())
    wardrobe = _summarize_items(record.get('wardrobes'), lambda row: f"{_clean(row.get('label'))} {('- ' + _clean(row.get('notes'))) if _clean(row.get('notes')) else ''}".strip())
    return compile_named_packet(section_title, _lines([
        ('Name', record.get('display_name') or record.get('name')),
        ('Summary', record.get('summary')),
        ('Role Tier', record.get('role_tier')),
        ('Gender', record.get('gender')),
        ('Pronouns', record.get('pronouns')),
        ('Species', record.get('species')),
        ('Designation', record.get('designation')),
        ('Occupation', record.get('occupation')),
        ('Current Location', record.get('current_location_label')),
        ('Appearance', record.get('appearance')),
        ('Personality', record.get('personality')),
        ('Speech Style', record.get('speech_style')),
        ('Affiliations', record.get('affiliations')),
        ('Organizations / Factions', ', '.join(record.get('organization_names') or [])),
        ('Hobbies', record.get('hobbies')),
        ('Relationship Notes', record.get('relationship_notes')),
        ('Linked Relationships', relationships),
        ('Abilities', abilities),
        ('Weapons / Artifacts', ', '.join(record.get('artifact_names') or [])),
        ('Spells / Rituals', ', '.join(record.get('ritual_names') or [])),
        ('Cycles / Conditions', ', '.join(record.get('cycle_names') or [])),
        ('Wardrobe', wardrobe),
        ('Story Hooks', hooks),
        ('Canon Notes', record.get('canon_notes')),
    ]))


def compile_scenario_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    cast = _summarize_items(record.get('cast'), lambda row: f"{_clean(row.get('character_name')) or _clean(row.get('character_id'))}: {_clean(row.get('scene_role')).replace('_', ' ')} / {_clean(row.get('presence')).replace('_', ' ')}")
    return compile_named_packet('SCENARIO', _lines([
        ('Title', record.get('title')),
        ('Premise', record.get('premise')),
        ('Opening Beat', record.get('opening_beat')),
        ('Tone', record.get('tone')),
        ('Location', record.get('location_label')),
        ('Objective', record.get('objective')),
        ('Organizations / Factions', ', '.join(record.get('organization_names') or [])),
        ('Scene Cast', cast),
        ('Scene Notes', record.get('scene_notes')),
    ]))


def compile_story_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('STORY', _lines([
        ('Title', record.get('title')),
        ('Summary', record.get('summary')),
        ('Pinned Canon', record.get('pinned_canon')),
    ]))


def compile_part_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    return compile_named_packet('STORY PART', _lines([
        ('Title', record.get('title')),
        ('Summary', record.get('summary')),
        ('Scene Notes', record.get('scene_notes')),
        ('Pinned Canon', record.get('pinned_canon')),
    ]))


def compile_scene_cast_packet(cast_items: Any) -> str:
    cast = _summarize_items(cast_items, lambda row: f"{_clean(row.get('character_name')) or _clean(row.get('character_id'))}: {_clean(row.get('scene_role')).replace('_', ' ')} / {_clean(row.get('presence')).replace('_', ' ')} {('- ' + _clean(row.get('notes'))) if _clean(row.get('notes')) else ''}".strip())
    return compile_named_packet('SCENE CAST', _lines([('Participants', cast)]))


def compile_advanced_controls_packet(record: dict[str, Any] | None) -> str:
    record = record or {}
    generation = record.get('generation') or {}
    return compile_named_packet('ADVANCED CONTROLS', _lines([
        ('Memory / Canon Notes', record.get('memory_canon_notes')),
        ('Author Note', record.get('author_note')),
        ('Canon Mode', ROLEPLAY_CANON_MODES.get(_clean(record.get('canon_mode')), _clean(record.get('canon_mode')))),
        ('Output Preset', ROLEPLAY_OUTPUT_PRESETS.get(_clean(record.get('output_preset')), _clean(record.get('output_preset')))),
        ('Max Tokens', generation.get('max_tokens')),
        ('Temperature', generation.get('temperature')),
        ('Top P', generation.get('top_p')),
        ('Top K', generation.get('top_k')),
    ]))


def build_runtime_roleplay_bundle(*, scenario: str = '', user_name: str = '', partner_name: str = '', tone: str = '', custom_tone: str = '', style: str = '', scene_notes: str = '', memory_notes: str = '', author_note: str = '', max_tokens: int = 320, temperature: float = 0.82, top_p: float = 0.92, top_k: int = 60, canon_mode: str = 'what_if', output_preset: str = 'roleplay', user_character_record: dict[str, Any] | None = None, partner_character_record: dict[str, Any] | None = None, world_record: dict[str, Any] | None = None, scenario_record: dict[str, Any] | None = None, location_record: dict[str, Any] | None = None, support_character_records: Any = None, cast_items: Any = None) -> dict[str, str]:
    effective_tone = _clean(custom_tone) if _clean(tone).lower() == 'custom' else _clean(tone)
    scene_cast_packet = compile_scene_cast_packet(cast_items)
    live_scene_packet = compile_named_packet('LIVE SCENE', _lines([
        ('Premise', scenario),
        ('User Character', user_name or 'You'),
        ('Scene Partner / Narrator', partner_name or 'Scene partner'),
        ('Tone', effective_tone or 'Natural and immersive'),
        ('Reply Style', style or 'Immersive dialogue'),
        ('Scene Notes', scene_notes),
    ]))
    advanced_packet = compile_advanced_controls_packet({
        'memory_canon_notes': memory_notes,
        'author_note': author_note,
        'canon_mode': canon_mode,
        'output_preset': output_preset,
        'generation': {
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_p': top_p,
            'top_k': top_k,
        },
    })
    user_character_packet = compile_character_packet(user_character_record, 'USER CHARACTER')
    partner_character_packet = compile_character_packet(partner_character_record, 'PARTNER CHARACTER')
    supporting_cast_packet = compile_supporting_cast_packet(support_character_records)
    saved_world_packet = compile_world_packet(world_record)
    saved_scenario_packet = compile_scenario_packet(scenario_record)
    saved_location_packet = compile_location_packet(location_record)

    relevant_artifacts = []
    relevant_rituals = []
    relevant_cycles = []
    relevant_organizations = []
    for record in [user_character_record, partner_character_record, world_record, scenario_record, location_record, *([r for r in (support_character_records if isinstance(support_character_records, list) else []) if isinstance(r, dict)])]:
        if not isinstance(record, dict):
            continue
        relevant_artifacts.extend(record.get('artifact_names') or [])
        relevant_rituals.extend(record.get('ritual_names') or [])
        relevant_cycles.extend(record.get('cycle_names') or [])
        relevant_organizations.extend(record.get('organization_names') or [])
    relevant_artifacts_packet = compile_relevant_links_packet('RELEVANT ARTIFACTS', relevant_artifacts)
    relevant_rituals_packet = compile_relevant_links_packet('RELEVANT RITUALS', relevant_rituals)
    relevant_cycles_packet = compile_relevant_links_packet('ACTIVE CYCLES', relevant_cycles)
    relevant_organizations_packet = compile_relevant_links_packet('RELEVANT ORGANIZATIONS', relevant_organizations)

    combined = '\n\n'.join([part for part in [saved_world_packet, saved_location_packet, user_character_packet, partner_character_packet, supporting_cast_packet, saved_scenario_packet, relevant_artifacts_packet, relevant_rituals_packet, relevant_cycles_packet, relevant_organizations_packet, scene_cast_packet, live_scene_packet, advanced_packet] if part])
    return {
        'effective_tone': effective_tone or _clean(tone),
        'scene_packet': live_scene_packet,
        'scene_cast_packet': scene_cast_packet,
        'advanced_packet': advanced_packet,
        'user_character_packet': user_character_packet,
        'partner_character_packet': partner_character_packet,
        'supporting_cast_packet': supporting_cast_packet,
        'world_packet': saved_world_packet,
        'location_packet': saved_location_packet,
        'scenario_packet': saved_scenario_packet,
        'relevant_artifacts_packet': relevant_artifacts_packet,
        'relevant_rituals_packet': relevant_rituals_packet,
        'relevant_cycles_packet': relevant_cycles_packet,
        'relevant_organizations_packet': relevant_organizations_packet,
        'combined_packet': combined,
    }
