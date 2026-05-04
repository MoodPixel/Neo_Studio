from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from ..utils.roleplay_library_imports import build_import_preview, commit_import_preview
from ..utils.roleplay_library_exports import build_record_export_payload, build_template_payload, export_filename
from ..utils.roleplay_builder_assist import generate_builder_assist
from ..utils.roleplay_library_ai_drafts import draft_library_json
from ..utils.roleplay_library_store import delete_record, get_record, library_state, save_record
from .common import json_error

router = APIRouter()




def _download_json(payload: dict, filename: str) -> Response:
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

def _json_list(raw: str):
    try:
        data = json.loads(raw or '[]')
        return data if isinstance(data, list) else []
    except Exception:
        return []




def _lookup_names(kind: str, ids: list[str]) -> list[str]:
    names: list[str] = []
    for record_id in ids:
        rec = get_record(kind, str(record_id or '').strip())
        if not rec:
            continue
        label = str(rec.get('display_name') or rec.get('name') or rec.get('title') or '').strip()
        if label:
            names.append(label)
    return names


def _lookup_name(kind: str, record_id: str) -> str:
    rec = get_record(kind, str(record_id or '').strip())
    if not rec:
        return ''
    return str(rec.get('display_name') or rec.get('name') or rec.get('title') or '').strip()


@router.get('/api/roleplay/library/state')
async def api_roleplay_library_state():
    return JSONResponse({'ok': True, **library_state()})


@router.get('/api/roleplay/library/record')
async def api_roleplay_library_record(kind: str = '', record_id: str = ''):
    record = get_record(kind, record_id)
    if not record:
        return json_error('Library record not found.', 404)
    return JSONResponse({'ok': True, 'record': record})


@router.post('/api/roleplay/library/import-preview')
async def api_roleplay_library_import_preview(target_kind: str = Form(''), file: UploadFile | None = File(None)):
    if file is None:
        return json_error('Choose a JSON, Markdown, or TXT file first.', 400)
    try:
        content = await file.read()
        preview = build_import_preview(file.filename or 'roleplay_import', content, target_kind)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **preview, 'message': f"Preview ready for {preview['summary']['record_count']} {preview['summary']['import_kind_label']}."})


@router.post('/api/roleplay/library/import-commit')
async def api_roleplay_library_import_commit(preview_id: str = Form('')):
    clean_preview_id = str(preview_id or '').strip()
    if not clean_preview_id:
        return json_error('Import preview ID is required.', 400)
    try:
        result = commit_import_preview(clean_preview_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    first_record = result['saved_records'][0] if result.get('saved_records') else None
    return JSONResponse({'ok': True, **result, 'record': first_record, **library_state(), 'message': f"Imported {result['saved_count']} {result['import_kind_label']}."})


@router.get('/api/roleplay/library/export-template')
async def api_roleplay_library_export_template(kind: str = ''):
    try:
        payload = build_template_payload(kind)
        filename = export_filename(kind, template=True)
    except Exception as exc:
        return json_error(str(exc), 400)
    return _download_json(payload, filename)


@router.get('/api/roleplay/library/export-record')
async def api_roleplay_library_export_record(kind: str = '', record_id: str = ''):
    try:
        payload = build_record_export_payload(kind, record_id)
        filename = export_filename(kind, payload)
    except Exception as exc:
        return json_error(str(exc), 400)
    return _download_json(payload, filename)


@router.post('/api/roleplay/library/import-preview-text')
async def api_roleplay_library_import_preview_text(
    target_kind: str = Form(''),
    source_text: str = Form(''),
    source_name: str = Form('editor_draft.json'),
):
    clean_text = str(source_text or '').strip()
    if not clean_text:
        return json_error('Paste or generate JSON in the editor first.', 400)
    try:
        preview = build_import_preview(source_name or 'editor_draft.json', clean_text.encode('utf-8'), target_kind)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **preview, 'message': f"Preview ready for {preview['summary']['record_count']} {preview['summary']['import_kind_label']}."})


@router.post('/api/roleplay/library/ai-draft-preview')
async def api_roleplay_library_ai_draft_preview(
    target_kind: str = Form(''),
    brief: str = Form(''),
    draft_mode: str = Form('draft_scratch'),
    draft_style: str = Form('balanced'),
    model: str = Form('default'),
    current_json: str = Form(''),
    universe_id: str = Form(''),
    world_id: str = Form(''),
    region_id: str = Form(''),
    city_id: str = Form(''),
    location_id: str = Form(''),
    scenario_id: str = Form(''),
    species_hint: str = Form(''),
    organization_ids_json: str = Form('[]'),
):
    try:
        draft = await draft_library_json(
            kind=target_kind,
            brief=brief,
            mode=draft_mode,
            draft_style=draft_style,
            current_json=current_json,
            model=model,
            context={
                'universe_id': universe_id,
                'world_id': world_id,
                'region_id': region_id,
                'city_id': city_id,
                'location_id': location_id,
                'scenario_id': scenario_id,
                'species_hint': species_hint,
                'organization_ids': _json_list(organization_ids_json),
            },
        )
        preview = build_import_preview(f'ai_{draft["kind"]}.json', str(draft.get('draft_json') or '').encode('utf-8'), target_kind)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({
        'ok': True,
        **preview,
        'draft_json': draft.get('draft_json', ''),
        'draft_mode': draft.get('mode', draft_mode),
        'draft_style': draft.get('draft_style', draft_style),
        'context_packet': draft.get('context_packet', {}),
        'message': f"AI draft ready for {preview['summary']['import_kind_label']}. Review the JSON editor and preview before committing."
    })


@router.post('/api/roleplay/library/builder-assist')
async def api_roleplay_library_builder_assist(
    kind: str = Form(''),
    brief: str = Form(''),
    mode: str = Form('fill_missing'),
    model: str = Form('default'),
    current_record_json: str = Form('{}'),
):
    try:
        current_record = json.loads(current_record_json or '{}') if current_record_json else {}
    except Exception:
        current_record = {}
    try:
        result = await generate_builder_assist(kind=kind, brief=brief, current_record=current_record if isinstance(current_record, dict) else {}, mode=mode, model=model)
    except Exception as exc:
        return json_error(str(exc), 400)
    field_count = len(result.get('updated_fields') or [])
    return JSONResponse({'ok': True, **result, 'message': f"Builder assist drafted {field_count} field{'s' if field_count != 1 else ''} for {result['kind']}. Review before saving."})


@router.post('/api/roleplay/library/save')
async def api_roleplay_library_save(
    kind: str = Form(''),
    record_id: str = Form(''),
    name: str = Form(''),
    display_name: str = Form(''),
    gender: str = Form(''),
    pronouns: str = Form(''),
    role_tier: str = Form(''),
    species: str = Form(''),
    designation: str = Form(''),
    occupation: str = Form(''),
    student_details: str = Form(''),
    hobbies: str = Form(''),
    affiliations: str = Form(''),
    origin_world_id: str = Form(''),
    current_world_id: str = Form(''),
    origin_region_id: str = Form(''),
    current_region_id: str = Form(''),
    origin_city_id: str = Form(''),
    current_city_id: str = Form(''),
    origin_location_id: str = Form(''),
    current_location_id: str = Form(''),
    current_location_label: str = Form(''),
    world_id: str = Form(''),
    summary: str = Form(''),
    appearance: str = Form(''),
    personality: str = Form(''),
    speech_style: str = Form(''),
    relationship_notes: str = Form(''),
    canon_notes: str = Form(''),
    private_notes: str = Form(''),
    relationships_json: str = Form('[]'),
    abilities_json: str = Form('[]'),
    wardrobes_json: str = Form('[]'),
    story_hooks_json: str = Form('[]'),
    lore: str = Form(''),
    rules: str = Form(''),
    realm_type: str = Form(''),
    calendar_notes: str = Form(''),
    geography_notes: str = Form(''),
    society_notes: str = Form(''),
    faith_notes: str = Form(''),
    people_notes: str = Form(''),
    inhabitant_species_ids_json: str = Form('[]'),
    creature_fauna_ids_json: str = Form('[]'),
    parent_region_id: str = Form(''),
    region_type: str = Form(''),
    region_id: str = Form(''),
    city_type: str = Form(''),
    anchor_type: str = Form(''),
    city_id: str = Form(''),
    parent_location_id: str = Form(''),
    function_label: str = Form(''),
    location_type: str = Form(''),
    atmosphere: str = Form(''),
    scene_uses_json: str = Form('[]'),
    access_notes: str = Form(''),
    hazards: str = Form(''),
    public_notes: str = Form(''),
    hidden_truth: str = Form(''),
    group_type: str = Form(''),
    base_location_id: str = Form(''),
    parent_organization_id: str = Form(''),
    leadership: str = Form(''),
    beliefs: str = Form(''),
    goals: str = Form(''),
    reputation: str = Form(''),
    resources: str = Form(''),
    membership_rules: str = Form(''),
    public_face: str = Form(''),
    item_type: str = Form(''),
    rarity: str = Form(''),
    state_value: str = Form(''),
    source_tradition: str = Form(''),
    effects: str = Form(''),
    costs: str = Form(''),
    activation: str = Form(''),
    lawful_status: str = Form(''),
    current_holder_character_id: str = Form(''),
    ritual_type: str = Form(''),
    school: str = Form(''),
    effect_summary: str = Form(''),
    requirements: str = Form(''),
    risks: str = Form(''),
    cycle_type: str = Form(''),
    scope_type: str = Form(''),
    affected_species: str = Form(''),
    affected_designation: str = Form(''),
    cadence: str = Form(''),
    trigger: str = Form(''),
    stages: str = Form(''),
    safeguards: str = Form(''),
    artifact_ids_json: str = Form('[]'),
    ritual_ids_json: str = Form('[]'),
    cycle_ids_json: str = Form('[]'),
    organization_ids_json: str = Form('[]'),
    ally_organization_ids_json: str = Form('[]'),
    rival_organization_ids_json: str = Form('[]'),
    category: str = Form(''),
    sentience: str = Form(''),
    universe_id: str = Form(''),
    scope: str = Form(''),
    legend_type: str = Form(''),
    truth_status: str = Form(''),
    public_version: str = Form(''),
    hidden_version: str = Form(''),
    pack_type: str = Form(''),
    content: str = Form(''),
    title: str = Form(''),
    premise: str = Form(''),
    opening_beat: str = Form(''),
    tone: str = Form(''),
    location_label: str = Form(''),
    location_region_id: str = Form(''),
    location_city_id: str = Form(''),
    location_id: str = Form(''),
    objective: str = Form(''),
    scene_notes: str = Form(''),
    cast_json: str = Form('[]'),
):
    inhabitant_ids = _json_list(inhabitant_species_ids_json)
    creature_ids = _json_list(creature_fauna_ids_json)
    scene_use_items = _json_list(scene_uses_json)
    artifact_ids = _json_list(artifact_ids_json)
    ritual_ids = _json_list(ritual_ids_json)
    cycle_ids = _json_list(cycle_ids_json)
    organization_ids = _json_list(organization_ids_json)
    ally_organization_ids = _json_list(ally_organization_ids_json)
    rival_organization_ids = _json_list(rival_organization_ids_json)
    try:
        record = save_record(
            kind,
            record_id,
            name=name,
            display_name=display_name,
            gender=gender,
            pronouns=pronouns,
            role_tier=role_tier,
            species=species,
            designation=designation,
            occupation=occupation,
            student_details=student_details,
            hobbies=hobbies,
            affiliations=affiliations,
            origin_world_id=origin_world_id,
            current_world_id=current_world_id,
            origin_region_id=origin_region_id,
            current_region_id=current_region_id,
            origin_city_id=origin_city_id,
            current_city_id=current_city_id,
            origin_location_id=origin_location_id,
            current_location_id=current_location_id,
            origin_location_label=_lookup_name('location', origin_location_id) or _lookup_name('city', origin_city_id),
            current_location_label=current_location_label or _lookup_name('location', current_location_id) or _lookup_name('city', current_city_id) or _lookup_name('region', current_region_id),
            world_id=world_id,
            summary=summary,
            appearance=appearance,
            personality=personality,
            speech_style=speech_style,
            relationship_notes=relationship_notes,
            canon_notes=canon_notes,
            private_notes=private_notes,
            relationships=_json_list(relationships_json),
            abilities=_json_list(abilities_json),
            wardrobes=_json_list(wardrobes_json),
            story_hooks=_json_list(story_hooks_json),
            artifact_ids=artifact_ids,
            artifact_names=_lookup_names('artifact', artifact_ids),
            ritual_ids=ritual_ids,
            ritual_names=_lookup_names('ritual', ritual_ids),
            cycle_ids=cycle_ids,
            cycle_names=_lookup_names('cycle', cycle_ids),
            organization_ids=organization_ids,
            organization_names=_lookup_names('organization', organization_ids),
            ally_organization_ids=ally_organization_ids,
            ally_organization_names=_lookup_names('organization', ally_organization_ids),
            rival_organization_ids=rival_organization_ids,
            rival_organization_names=_lookup_names('organization', rival_organization_ids),
            lore=lore,
            rules=rules,
            realm_type=realm_type,
            calendar_notes=calendar_notes,
            geography_notes=geography_notes,
            society_notes=society_notes,
            faith_notes=faith_notes,
            people_notes=people_notes,
            inhabitant_species_ids=inhabitant_ids,
            inhabitant_species_names=_lookup_names('creature', inhabitant_ids),
            creature_fauna_ids=creature_ids,
            creature_fauna_names=_lookup_names('creature', creature_ids),
            parent_region_id=parent_region_id,
            region_type=region_type,
            region_id=region_id,
            city_type=city_type,
            anchor_type=anchor_type,
            city_id=city_id,
            parent_location_id=parent_location_id,
            function_label=function_label,
            location_type=location_type,
            atmosphere=atmosphere,
            scene_uses=scene_use_items,
            access_notes=access_notes,
            hazards=hazards,
            public_notes=public_notes,
            hidden_truth=hidden_truth,
            group_type=group_type,
            base_location_id=base_location_id,
            parent_organization_id=parent_organization_id,
            leadership=leadership,
            beliefs=beliefs,
            goals=goals,
            reputation=reputation,
            resources=resources,
            membership_rules=membership_rules,
            public_face=public_face,
            item_type=item_type,
            rarity=rarity,
            state=state_value,
            source_tradition=source_tradition,
            effects=effects,
            costs=costs,
            activation=activation,
            lawful_status=lawful_status,
            current_holder_character_id=current_holder_character_id,
            ritual_type=ritual_type,
            school=school,
            effect_summary=effect_summary,
            requirements=requirements,
            risks=risks,
            cycle_type=cycle_type,
            scope_type=scope_type,
            affected_species=affected_species,
            affected_designation=affected_designation,
            cadence=cadence,
            trigger=trigger,
            stages=stages,
            safeguards=safeguards,
            category=category,
            sentience=sentience,
            universe_id=universe_id,
            scope=scope,
            legend_type=legend_type,
            truth_status=truth_status,
            public_version=public_version,
            hidden_version=hidden_version,
            pack_type=pack_type,
            content=content,
            title=title,
            premise=premise,
            opening_beat=opening_beat,
            tone=tone,
            location_label=location_label or _lookup_name('location', location_id) or _lookup_name('city', location_city_id) or _lookup_name('region', location_region_id),
            location_region_id=location_region_id,
            location_city_id=location_city_id,
            location_id=location_id,
            objective=objective,
            scene_notes=scene_notes,
            cast=_json_list(cast_json),
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    label = record.get('display_name') or record.get('name') or record.get('title') or 'Record'
    return JSONResponse({'ok': True, 'record': record, **library_state(), 'message': f'Saved {kind}: {label}'})


@router.post('/api/roleplay/library/delete')
async def api_roleplay_library_delete(kind: str = Form(''), record_id: str = Form('')):
    ok = delete_record(kind, record_id)
    if not ok:
        return json_error('Library record not found.', 404)
    return JSONResponse({'ok': True, **library_state(), 'message': f'Deleted {kind}.'})
