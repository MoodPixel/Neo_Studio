from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from ..utils.library_presets import get_caption_presets, get_prompt_presets
from ..utils.library_settings_store import list_categories
from ..utils.library_stats import stats
from ..utils.library_transfer import build_library_export_zip, import_library_archive
from ..utils.prompt_bundles import bundle_entries
from ..utils.characters import character_entries
from ..utils.library_prompts import prompt_entries, prompt_categories
from ..utils.logging_utils import get_logger
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


@router.get('/api/library-transfer-support')
async def api_library_transfer_support():
    return JSONResponse({
        'ok': True,
        'categories': list_categories(),
        'prompt_presets': get_prompt_presets(),
        'caption_presets': get_caption_presets(),
        'prompt_categories': prompt_categories(),
    })


@router.post('/api/export-library')
async def api_export_library(
    include_prompts: str = Form('true'),
    include_captions: str = Form('true'),
    include_characters: str = Form('true'),
    include_presets: str = Form('true'),
    include_categories: str = Form('true'),
    include_metadata: str = Form('true'),
    include_bundles: str = Form('true'),
    selected_categories_json: str = Form('[]'),
    full_snapshot: str = Form('false'),
):
    try:
        import json
        selected_categories = json.loads(selected_categories_json or '[]')
        zip_bytes, filename, summary = build_library_export_zip(
            include_prompts=str(include_prompts).lower() in {'1', 'true', 'yes', 'on'},
            include_captions=str(include_captions).lower() in {'1', 'true', 'yes', 'on'},
            include_characters=str(include_characters).lower() in {'1', 'true', 'yes', 'on'},
            include_presets=str(include_presets).lower() in {'1', 'true', 'yes', 'on'},
            include_categories=str(include_categories).lower() in {'1', 'true', 'yes', 'on'},
            include_metadata=str(include_metadata).lower() in {'1', 'true', 'yes', 'on'},
            include_bundles=str(include_bundles).lower() in {'1', 'true', 'yes', 'on'},
            selected_categories=selected_categories,
            full_snapshot=str(full_snapshot).lower() in {'1', 'true', 'yes', 'on'},
        )
    except Exception as e:
        logger.exception('Library export failed')
        return json_error(str(e), 400)
    headers = {'Content-Disposition': f'attachment; filename="{filename}"', 'X-Neo-Export-Summary': str(summary)}
    return Response(content=zip_bytes, media_type='application/zip', headers=headers)


@router.post('/api/import-library')
async def api_import_library(file: UploadFile = File(...), mode: str = Form('merge')):
    try:
        content = await file.read()
        summary = import_library_archive(content, mode=mode)
    except Exception as e:
        logger.exception('Library import failed')
        return json_error(str(e), 400)
    return JSONResponse({
        'ok': True,
        'message': 'Library import complete.',
        'summary': summary,
        'stats': stats(),
        'categories': list_categories(),
        'prompt_presets': get_prompt_presets(),
        'caption_presets': get_caption_presets(),
        'prompt_entries': prompt_entries(stats().get('last_prompt_category') or ''),
        'characters': character_entries(),
        'bundles': bundle_entries(),
    })
