from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_builder_workspace import get_builder_forge_state, get_builder_template_payload, create_entity_stub, list_builder_records, load_builder_record, save_builder_record, delete_builder_record, get_builder_library_state, normalize_import_payload, ROLEPLAY_V2_ENTITIES_DIR
from ..utils.roleplay_v2_builder_ai_drafts import draft_builder_json, draft_builder_markdown
from ..contracts.roleplay_v2_hierarchy_contract import build_roleplay_v2_authoring_hierarchy_contract
from ..utils.roleplay_v2_sqlite_store import fetch_rp2_sqlite_overview, sync_rp2_entities_from_directory, fetch_rp2_entity_debug_rows, fetch_rp2_edge_debug_rows, fetch_rp2_memory_fragment_debug_rows, fetch_rp2_shared_memory_debug_rows, fetch_rp2_callback_anchor_debug_rows
from ..utils.roleplay_v2_migration import build_phase14_migration_status, run_phase14_migration
from ..utils.roleplay_v2_cutover import build_roleplay_v2_cutover_status, apply_roleplay_v2_soft_cutover
from .common import json_error, json_exception

router = APIRouter()


@router.get('/api/roleplay/v2/builders/forge-state')
async def api_roleplay_v2_builder_forge_state():
    try:
        return JSONResponse(get_builder_forge_state())
    except Exception as exc:
        return json_error(str(exc), 500)




@router.get('/api/roleplay/v2/builders/hierarchy')
async def api_roleplay_v2_builder_hierarchy():
    try:
        return JSONResponse({'ok': True, 'authoring_hierarchy': build_roleplay_v2_authoring_hierarchy_contract()})
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/builders/template')
async def api_roleplay_v2_builder_template(kind: str = ''):
    try:
        return JSONResponse({'ok': True, 'template': get_builder_template_payload(kind)})
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/builders/assist-draft')
async def api_roleplay_v2_builder_assist_draft(
    kind: str = Form(''),
    target_kind: str = Form(''),
    brief: str = Form(''),
    draft_mode: str = Form('draft_scratch'),
    draft_style: str = Form('balanced'),
    model: str = Form('default'),
    current_json: str = Form('{}'),
    universe_id: str = Form(''),
    world_id: str = Form(''),
    region_id: str = Form(''),
    city_id: str = Form(''),
    location_id: str = Form(''),
    scenario_id: str = Form(''),
    species_hint: str = Form(''),
    organization_ids_json: str = Form('[]'),
    max_tokens: int = Form(1800),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(50),
):
    try:
        import json
        organization_ids = []
        try:
            parsed_org_ids = json.loads(organization_ids_json or '[]')
            if isinstance(parsed_org_ids, list):
                organization_ids = parsed_org_ids
        except Exception:
            organization_ids = []
        clean_kind = kind or target_kind
        payload = await draft_builder_markdown(
            clean_kind,
            brief,
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
                'organization_ids': organization_ids,
            },
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        payload['message'] = f"{str(payload.get('kind') or clean_kind).title()} Forge markdown draft ready."
        return JSONResponse(payload)
    except Exception as exc:
        return json_exception(exc, default_message='Forge assist request failed.', default_status=500, context='Roleplay V2 builder assist draft')


@router.post('/api/roleplay/v2/builders/create-stub')
async def api_roleplay_v2_builder_create_stub(kind: str = Form(''), label: str = Form(''), source_container_id: str = Form(''), payload_json: str = Form('{}')):
    try:
        import json
        payload = json.loads(payload_json or '{}')
        return JSONResponse(create_entity_stub(kind=kind, label=label, source_container_id=source_container_id, payload=payload if isinstance(payload, dict) else {}))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/builders/records')
async def api_roleplay_v2_builder_records(kind: str = ''):
    try:
        return JSONResponse(list_builder_records(kind))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/builders/record')
async def api_roleplay_v2_builder_record(record_id: str = ''):
    try:
        return JSONResponse(load_builder_record(record_id))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/builders/save')
async def api_roleplay_v2_builder_save(kind: str = Form(''), payload_json: str = Form('{}')):
    try:
        import json
        payload = json.loads(payload_json or '{}')
        return JSONResponse(save_builder_record(kind=kind, payload=payload if isinstance(payload, dict) else {}))
    except Exception as exc:
        return json_error(str(exc), 400)




@router.post('/api/roleplay/v2/builders/delete')
async def api_roleplay_v2_builder_delete(record_id: str = Form('')):
    try:
        return JSONResponse(delete_builder_record(record_id))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/builders/library-state')
async def api_roleplay_v2_builder_library_state():
    try:
        return JSONResponse(get_builder_library_state())
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/builders/normalize-import')
async def api_roleplay_v2_builder_normalize_import(kind: str = Form(''), import_format: str = Form('json'), payload_text: str = Form('')):
    try:
        return JSONResponse(normalize_import_payload(kind=kind, import_format=import_format, payload_text=payload_text))
    except Exception as exc:
        return json_error(str(exc), 400)



@router.get('/api/roleplay/v2/migration/status')
async def api_roleplay_v2_migration_status():
    try:
        return JSONResponse(build_phase14_migration_status())
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/migration/run')
async def api_roleplay_v2_migration_run(sync_builders: str = Form('1'), backfill_memory: str = Form('1'), backfill_stories: str = Form('1'), sync_chroma: str = Form('1'), prune_missing: str = Form('0')):
    try:
        return JSONResponse(run_phase14_migration(
            sync_builders=str(sync_builders or '1').strip().lower() not in {'0', 'false', 'no'},
            backfill_memory=str(backfill_memory or '1').strip().lower() not in {'0', 'false', 'no'},
            backfill_stories=str(backfill_stories or '1').strip().lower() not in {'0', 'false', 'no'},
            sync_chroma=str(sync_chroma or '1').strip().lower() not in {'0', 'false', 'no'},
            prune_missing=str(prune_missing or '0').strip().lower() in {'1', 'true', 'yes'},
        ))
    except Exception as exc:
        return json_error(str(exc), 400)



@router.get('/api/roleplay/v2/cutover/status')
async def api_roleplay_v2_cutover_status():
    try:
        return JSONResponse(build_roleplay_v2_cutover_status())
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/cutover/apply')
async def api_roleplay_v2_cutover_apply(enabled: str = Form('1'), force: str = Form('0')):
    try:
        payload = apply_roleplay_v2_soft_cutover(
            enabled=str(enabled or '1').strip().lower() not in {'0', 'false', 'no'},
            force=str(force or '0').strip().lower() in {'1', 'true', 'yes'},
        )
        if payload.get('ok') is False:
            return json_error(str(payload.get('error') or 'Cutover failed.'), 400, payload)
        return JSONResponse(payload)
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/overview')
async def api_roleplay_v2_sqlite_overview():
    try:
        return JSONResponse(fetch_rp2_sqlite_overview())
    except Exception as exc:
        return json_error(str(exc), 400)


@router.post('/api/roleplay/v2/sqlite/sync-builders')
async def api_roleplay_v2_sqlite_sync_builders(prune_missing: str = Form('1')):
    try:
        return JSONResponse(sync_rp2_entities_from_directory(entities_dir=ROLEPLAY_V2_ENTITIES_DIR, prune_missing=str(prune_missing or '1').strip().lower() not in {'0', 'false', 'no'}))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/entities')
async def api_roleplay_v2_sqlite_entities(kind: str = '', query: str = '', limit: int = 20):
    try:
        return JSONResponse(fetch_rp2_entity_debug_rows(kind=kind, query=query, limit=limit))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/edges')
async def api_roleplay_v2_sqlite_edges(entity_id: str = '', relation: str = '', limit: int = 40):
    try:
        return JSONResponse(fetch_rp2_edge_debug_rows(entity_id=entity_id, relation=relation, limit=limit))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/memory-fragments')
async def api_roleplay_v2_sqlite_memory_fragments(entity_id: str = '', memory_type: str = '', query: str = '', limit: int = 24):
    try:
        return JSONResponse(fetch_rp2_memory_fragment_debug_rows(entity_id=entity_id, memory_type=memory_type, query=query, limit=limit))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/shared-memories')
async def api_roleplay_v2_sqlite_shared_memories(entity_id: str = '', query: str = '', limit: int = 16):
    try:
        return JSONResponse(fetch_rp2_shared_memory_debug_rows(entity_id=entity_id, query=query, limit=limit))
    except Exception as exc:
        return json_error(str(exc), 400)


@router.get('/api/roleplay/v2/sqlite/callback-anchors')
async def api_roleplay_v2_sqlite_callback_anchors(entity_id: str = '', query: str = '', limit: int = 24):
    try:
        return JSONResponse(fetch_rp2_callback_anchor_debug_rows(entity_id=entity_id, query=query, limit=limit))
    except Exception as exc:
        return json_error(str(exc), 400)
