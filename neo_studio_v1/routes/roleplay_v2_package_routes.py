from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from ..utils.roleplay_v2_package_exports import build_package_from_saved_records, export_record_json
from ..utils.roleplay_v2_package_imports import preview_package_upload, commit_package_preview, read_package_preview
from .common import json_error

router = APIRouter()


def _download_json(payload: dict, filename: str) -> Response:
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )



def _json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw or '[]')
        return data if isinstance(data, list) else []
    except Exception:
        return []


@router.get('/api/roleplay/v2/package/export-json')
async def api_roleplay_v2_package_export_json(record_type: str = '', record_id: str = ''):
    try:
        payload, filename = export_record_json(record_type, record_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return _download_json(payload, filename)


@router.post('/api/roleplay/v2/package/export-records')
async def api_roleplay_v2_package_export_records(
    sources_json: str = Form('[]'),
    title: str = Form(''),
    package_type: str = Form('bundle'),
    asset_paths_json: str = Form('[]'),
):
    try:
        raw_sources = json.loads(sources_json or '[]') if sources_json else []
    except Exception:
        raw_sources = []
    sources: list[tuple[str, str]] = []
    for item in raw_sources if isinstance(raw_sources, list) else []:
        if not isinstance(item, dict):
            continue
        record_type = str(item.get('record_type') or '').strip().lower()
        record_id = str(item.get('record_id') or item.get('id') or '').strip()
        if record_type and record_id:
            sources.append((record_type, record_id))
    if not sources:
        return json_error('Provide at least one saved Roleplay V2 source record.', 400)
    try:
        path, manifest = build_package_from_saved_records(
            sources=sources,
            title=title,
            package_type=package_type,
            asset_paths=_json_list(asset_paths_json),
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    return FileResponse(
        path=str(path),
        media_type='application/zip',
        filename=path.name,
        headers={'X-Roleplay-V2-Package-Id': str(manifest.get('id') or '')},
    )


@router.post('/api/roleplay/v2/package/import-preview')
async def api_roleplay_v2_package_import_preview(file: UploadFile | None = File(None)):
    if file is None:
        return json_error('Choose a package file first.', 400)
    try:
        content = await file.read()
        preview = preview_package_upload(file.filename or 'roleplay_v2_bundle.neobundle', content)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **preview, 'message': f"Preview ready for {preview['record_count']} package record(s)."})


@router.post('/api/roleplay/v2/package/import-commit')
async def api_roleplay_v2_package_import_commit(preview_id: str = Form(''), import_mode: str = Form('replace_existing')):
    clean_preview_id = str(preview_id or '').strip()
    if not clean_preview_id:
        return json_error('Preview id is required.', 400)
    try:
        result = commit_package_preview(clean_preview_id, import_mode=import_mode)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, **result, 'message': f"Imported {result['saved_count']} package record(s)."})


@router.get('/api/roleplay/v2/package/preview')
async def api_roleplay_v2_package_preview(preview_id: str = ''):
    clean_preview_id = str(preview_id or '').strip()
    if not clean_preview_id:
        return json_error('Preview id is required.', 400)
    try:
        preview = read_package_preview(clean_preview_id)
    except Exception as exc:
        return json_error(str(exc), 404)
    return JSONResponse({'ok': True, **preview})
