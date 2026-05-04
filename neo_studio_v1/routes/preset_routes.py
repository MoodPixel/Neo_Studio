from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..utils.caption_contract import normalize_caption_preset_payload
from ..utils.kobold import clamp_float, clamp_int
from ..utils.library_presets import (
    compare_caption_presets,
    compare_prompt_presets,
    delete_caption_preset,
    delete_prompt_preset,
    duplicate_caption_preset,
    duplicate_prompt_preset,
    export_presets_payload,
    export_single_preset_payload,
    get_caption_presets,
    get_last_used_caption_preset,
    get_last_used_prompt_preset,
    get_prompt_presets,
    import_presets_payload,
    save_caption_preset,
    save_prompt_preset,
    set_last_used_caption_preset,
    set_last_used_prompt_preset,
    toggle_caption_preset_favorite,
    toggle_prompt_preset_favorite,
)
from ..utils.logging_utils import get_logger
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


@router.get('/api/export-presets')
async def api_export_presets():
    return JSONResponse({'ok': True, 'payload': export_presets_payload()})


@router.get('/api/export-single-preset')
async def api_export_single_preset(kind: str = 'prompt', name: str = ''):
    try:
        payload = export_single_preset_payload(kind=kind, name=name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'payload': payload})


@router.post('/api/import-presets')
async def api_import_presets(file: UploadFile = File(...), mode: str = Form('merge')):
    try:
        content = await file.read()
        payload = json.loads(content.decode('utf-8'))
        summary = import_presets_payload(payload, mode=mode)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Imported {summary['prompt_presets']} prompt presets and {summary['caption_presets']} caption presets.", 'summary': summary, 'prompt_presets': get_prompt_presets(), 'caption_presets': get_caption_presets()})


@router.get('/api/prompt-presets')
async def api_prompt_presets():
    return JSONResponse({'ok': True, 'presets': get_prompt_presets(), 'last_preset': get_last_used_prompt_preset()})


@router.post('/api/save-prompt-preset')
async def api_save_prompt_preset(
    name: str = Form(...),
    style: str = Form('Descriptive'),
    custom_instructions: str = Form(''),
    max_tokens: int = Form(220),
    temperature: float = Form(0.35),
    top_p: float = Form(0.9),
    top_k: int = Form(40),
    group: str = Form(''),
    notes: str = Form(''),
    favorite: bool = Form(False),
):
    try:
        preset_name = save_prompt_preset(name, {
            'style': style,
            'custom_instructions': custom_instructions,
            'max_tokens': clamp_int(max_tokens, 32, 1200, 220),
            'temperature': clamp_float(temperature, 0.0, 1.5, 0.35),
            'top_p': clamp_float(top_p, 0.0, 1.0, 0.9),
            'top_k': clamp_int(top_k, 0, 200, 40),
            'group': group,
            'notes': notes,
            'favorite': bool(favorite),
        })
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Saved preset: {preset_name}', 'presets': get_prompt_presets(), 'last_preset': preset_name})


@router.post('/api/delete-prompt-preset')
async def api_delete_prompt_preset(name: str = Form(...)):
    try:
        delete_prompt_preset(name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Deleted preset: {name}', 'presets': get_prompt_presets(), 'last_preset': get_last_used_prompt_preset()})


@router.post('/api/set-prompt-preset')
async def api_set_prompt_preset(name: str = Form(...)):
    set_last_used_prompt_preset(name)
    return JSONResponse({'ok': True, 'last_preset': get_last_used_prompt_preset(), 'presets': get_prompt_presets()})


@router.post('/api/duplicate-prompt-preset')
async def api_duplicate_prompt_preset(source_name: str = Form(...), new_name: str = Form(...)):
    try:
        name = duplicate_prompt_preset(source_name, new_name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Duplicated preset: {name}', 'presets': get_prompt_presets(), 'last_preset': name})


@router.post('/api/toggle-prompt-preset-favorite')
async def api_toggle_prompt_preset_favorite(name: str = Form(...)):
    try:
        favorite = toggle_prompt_preset_favorite(name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'favorite': favorite, 'presets': get_prompt_presets(), 'last_preset': get_last_used_prompt_preset()})


@router.get('/api/compare-prompt-presets')
async def api_compare_prompt_presets(name_a: str = '', name_b: str = ''):
    try:
        result = compare_prompt_presets(name_a, name_b)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'comparison': result})


@router.get('/api/caption-presets')
async def api_caption_presets():
    return JSONResponse({'ok': True, 'presets': get_caption_presets(), 'last_preset': get_last_used_caption_preset()})


@router.post('/api/save-caption-preset')
async def api_save_caption_preset(
    name: str = Form(...),
    prompt_style: str = Form('Custom'),
    caption_length: str = Form('any'),
    custom_prompt: str = Form(''),
    max_new_tokens: int = Form(160),
    temperature: float = Form(0.2),
    top_p: float = Form(0.9),
    top_k: int = Form(40),
    prefix: str = Form(''),
    suffix: str = Form(''),
    output_style: str = Form('Auto (match input)'),
    caption_mode: str = Form('full_image'),
    component_type: str = Form(''),
    detail_level: str = Form('detailed'),
    group: str = Form(''),
    notes: str = Form(''),
    favorite: bool = Form(False),
):
    try:
        preset_payload = normalize_caption_preset_payload({
            'prompt_style': prompt_style,
            'caption_length': caption_length,
            'custom_prompt': custom_prompt,
            'max_new_tokens': max_new_tokens,
            'temperature': temperature,
            'top_p': top_p,
            'top_k': top_k,
            'prefix': prefix,
            'suffix': suffix,
            'output_style': output_style,
            'caption_mode': caption_mode,
            'component_type': component_type,
            'detail_level': detail_level,
            'group': group,
            'notes': notes,
            'favorite': bool(favorite),
        })
        preset_name = save_caption_preset(name, preset_payload)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Saved preset: {preset_name}', 'presets': get_caption_presets(), 'last_preset': preset_name})


@router.post('/api/delete-caption-preset')
async def api_delete_caption_preset(name: str = Form(...)):
    try:
        delete_caption_preset(name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Deleted preset: {name}', 'presets': get_caption_presets(), 'last_preset': get_last_used_caption_preset()})


@router.post('/api/set-caption-preset')
async def api_set_caption_preset(name: str = Form(...)):
    set_last_used_caption_preset(name)
    return JSONResponse({'ok': True, 'last_preset': get_last_used_caption_preset(), 'presets': get_caption_presets()})


@router.post('/api/duplicate-caption-preset')
async def api_duplicate_caption_preset(source_name: str = Form(...), new_name: str = Form(...)):
    try:
        name = duplicate_caption_preset(source_name, new_name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f'Duplicated preset: {name}', 'presets': get_caption_presets(), 'last_preset': name})


@router.post('/api/toggle-caption-preset-favorite')
async def api_toggle_caption_preset_favorite(name: str = Form(...)):
    try:
        favorite = toggle_caption_preset_favorite(name)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'favorite': favorite, 'presets': get_caption_presets(), 'last_preset': get_last_used_caption_preset()})


@router.get('/api/compare-caption-presets')
async def api_compare_caption_presets(name_a: str = '', name_b: str = ''):
    try:
        result = compare_caption_presets(name_a, name_b)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'comparison': result})
