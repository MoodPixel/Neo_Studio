from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..utils.characters import character_entries
from ..utils.library_storage import save_temp_upload
from ..utils.logging_utils import get_logger
from ..utils.output_metadata import iter_output_metadata_records
from ..utils.prompt_bundles import (
    bundle_entries,
    delete_bundle_record,
    duplicate_bundle_record,
    get_bundle_record,
    save_bundle,
    update_bundle_record,
)
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


def _metadata_entries():
    rows = []
    for rec in sorted(iter_output_metadata_records(), key=lambda r: str(r.get('updated_at') or r.get('created_at') or ''), reverse=True):
        rows.append({
            'id': rec.get('id') or '',
            'name': rec.get('name') or '(unnamed)',
            'label': f"{rec.get('name') or '(unnamed)'} — {str(rec.get('updated_at') or rec.get('created_at') or '')[:19].replace('T', ' ')}",
        })
    return rows


@router.get('/api/bundle-support-data')
async def api_bundle_support_data():
    return JSONResponse({'ok': True, 'characters': character_entries(), 'metadata_records': _metadata_entries()})


@router.get('/api/bundle-records')
async def api_bundle_records():
    return JSONResponse({'ok': True, 'entries': bundle_entries(), 'metadata_records': _metadata_entries(), 'characters': character_entries()})


@router.get('/api/bundle-record')
async def api_bundle_record(bundle_id: str = '', name: str = ''):
    rec = get_bundle_record(bundle_id=bundle_id, name=name)
    if not rec:
        return json_error('Bundle not found.', 404)
    return JSONResponse({'ok': True, 'record': rec})


@router.get('/api/bundle-reference-image')
async def api_bundle_reference_image(bundle_id: str = ''):
    rec = get_bundle_record(bundle_id=bundle_id)
    if not rec or not rec.get('reference_image_rel'):
        return json_error('Reference image not found.', 404)
    fp = Path(__file__).resolve().parents[2] / 'neo_library_data'
    # always resolve through current library root by record url generated in util
    from ..utils.library_settings_store import get_library_root
    path = get_library_root() / str(rec.get('reference_image_rel'))
    if not path.exists():
        return json_error('Reference image file missing.', 404)
    return FileResponse(path)


@router.post('/api/save-bundle')
async def api_save_bundle(
    name: str = Form(...),
    positive_prompt: str = Form(''),
    negative_prompt: str = Form(''),
    character_name: str = Form(''),
    loras_text: str = Form(''),
    model_default: str = Form(''),
    checkpoint_default: str = Form(''),
    cfg_default: str = Form(''),
    steps_default: str = Form(''),
    sampler_default: str = Form(''),
    style_notes: str = Form(''),
    metadata_record_id: str = Form(''),
    reference_image: UploadFile | None = File(None),
):
    temp = None
    try:
        if reference_image and reference_image.filename:
            content = await reference_image.read()
            temp = save_temp_upload(content, Path(reference_image.filename).suffix)
        rec = save_bundle(
            name=name,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            character_name=character_name,
            loras=loras_text,
            model_default=model_default,
            checkpoint_default=checkpoint_default,
            cfg_default=cfg_default,
            steps_default=steps_default,
            sampler_default=sampler_default,
            style_notes=style_notes,
            metadata_record_id=metadata_record_id,
            reference_temp_image_id=(temp or {}).get('temp_image_id', ''),
            reference_image_name=reference_image.filename if reference_image else '',
        )
    except Exception as e:
        logger.exception('Failed to save bundle')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Saved bundle: {rec['name']}", 'entries': bundle_entries(), 'record': rec})


@router.post('/api/update-bundle')
async def api_update_bundle(
    bundle_id: str = Form(...),
    name: str = Form(...),
    positive_prompt: str = Form(''),
    negative_prompt: str = Form(''),
    character_name: str = Form(''),
    loras_text: str = Form(''),
    model_default: str = Form(''),
    checkpoint_default: str = Form(''),
    cfg_default: str = Form(''),
    steps_default: str = Form(''),
    sampler_default: str = Form(''),
    style_notes: str = Form(''),
    metadata_record_id: str = Form(''),
    clear_reference_image: str = Form('false'),
    reference_image: UploadFile | None = File(None),
):
    temp = None
    try:
        if reference_image and reference_image.filename:
            content = await reference_image.read()
            temp = save_temp_upload(content, Path(reference_image.filename).suffix)
        rec = update_bundle_record(
            bundle_id=bundle_id,
            name=name,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            character_name=character_name,
            loras=loras_text,
            model_default=model_default,
            checkpoint_default=checkpoint_default,
            cfg_default=cfg_default,
            steps_default=steps_default,
            sampler_default=sampler_default,
            style_notes=style_notes,
            metadata_record_id=metadata_record_id,
            reference_temp_image_id=(temp or {}).get('temp_image_id', ''),
            reference_image_name=reference_image.filename if reference_image else '',
            clear_reference_image=str(clear_reference_image).strip().lower() in {'1','true','yes','on'},
        )
    except Exception as e:
        logger.exception('Failed to update bundle')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Updated bundle: {rec['name']}", 'entries': bundle_entries(), 'record': rec})


@router.post('/api/delete-bundle')
async def api_delete_bundle(bundle_id: str = Form(...)):
    if not delete_bundle_record(bundle_id):
        return json_error('Bundle not found.', 404)
    return JSONResponse({'ok': True, 'message': 'Deleted bundle.', 'entries': bundle_entries()})


@router.post('/api/duplicate-bundle')
async def api_duplicate_bundle(bundle_id: str = Form(...), new_name: str = Form('')):
    try:
        rec = duplicate_bundle_record(bundle_id=bundle_id, new_name=new_name)
    except Exception as e:
        logger.exception('Failed to duplicate bundle')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Duplicated bundle: {rec['name']}", 'entries': bundle_entries(), 'record': rec})
