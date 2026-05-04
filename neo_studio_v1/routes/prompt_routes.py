from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.kobold import clamp_float, clamp_int, continue_prompt_text, generate_prompt_text
from ..utils.library_prompts import (
    delete_prompt_record,
    get_prompt_record,
    prompt_categories,
    prompt_entries,
    save_prompt,
    update_prompt_record,
)
from ..utils.library_settings_store import list_categories
from ..utils.library_stats import stats
from ..utils.logging_utils import get_logger
from ..utils.prompt_qa import lint_prompt
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


@router.post('/api/generate-prompt')
async def api_generate_prompt(
    model: str = Form('default'),
    idea: str = Form(...),
    style: str = Form('Stable Diffusion Prompt'),
    custom_instructions: str = Form(''),
    max_tokens: int = Form(220),
    temperature: float = Form(0.35),
    top_p: float = Form(0.9),
    top_k: int = Form(40),
):
    try:
        max_tokens = clamp_int(max_tokens, 32, 1200, 220)
        temperature = clamp_float(temperature, 0.0, 1.5, 0.35)
        top_p = clamp_float(top_p, 0.0, 1.0, 0.9)
        top_k = clamp_int(top_k, 0, 200, 40)
        result = await generate_prompt_text(
            idea=idea,
            model=model,
            style=style,
            custom_instructions=custom_instructions,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
    except Exception as e:
        logger.exception('Unhandled API exception')
        return json_error(str(e), 500)
    prompt = result.get('text', '')
    finish_reason = result.get('finish_reason', '')
    reasoning_stripped = bool(result.get('reasoning_stripped'))
    if reasoning_stripped and not prompt:
        warning = 'Visible reasoning was stripped, but the model never reached a final answer. Raise max tokens or use a non-reasoning / no-think model setting.'
    elif finish_reason == 'length':
        warning = 'Output likely got cut off. Use Continue or increase max tokens.'
    elif reasoning_stripped:
        warning = 'Visible reasoning was stripped automatically. Showing final answer only.'
    else:
        warning = ''
    return JSONResponse({'ok': True, 'prompt': prompt, 'finish_reason': finish_reason, 'warning': warning, 'reasoning_stripped': reasoning_stripped})


@router.post('/api/continue-prompt')
async def api_continue_prompt(
    model: str = Form('default'),
    idea: str = Form(...),
    current_output: str = Form(...),
    style: str = Form('Stable Diffusion Prompt'),
    custom_instructions: str = Form(''),
    max_tokens: int = Form(220),
    temperature: float = Form(0.35),
    top_p: float = Form(0.9),
    top_k: int = Form(40),
):
    try:
        result = await continue_prompt_text(
            idea=idea,
            current_output=current_output,
            model=model,
            style=style,
            custom_instructions=custom_instructions,
            max_tokens=clamp_int(max_tokens, 32, 1200, 220),
            temperature=clamp_float(temperature, 0.0, 1.5, 0.35),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.9),
            top_k=clamp_int(top_k, 0, 200, 40),
        )
    except Exception as e:
        logger.exception('Unhandled API exception')
        return json_error(str(e), 500)
    finish_reason = result.get('finish_reason', '')
    reasoning_stripped = bool(result.get('reasoning_stripped'))
    if reasoning_stripped and not result.get('text', ''):
        warning = 'Visible reasoning was stripped, but the model still did not reach a final answer. Raise max tokens or use a non-reasoning / no-think model setting.'
    elif finish_reason == 'length':
        warning = 'Still looks truncated. Continue again or raise max tokens.'
    elif reasoning_stripped:
        warning = 'Visible reasoning was stripped automatically. Showing final answer only.'
    else:
        warning = ''
    return JSONResponse({'ok': True, 'prompt': result.get('text', ''), 'continuation': result.get('continuation', ''), 'finish_reason': finish_reason, 'warning': warning, 'reasoning_stripped': reasoning_stripped})


@router.get('/api/prompt-records')
async def api_prompt_records(category: str = ''):
    entries = prompt_entries(category)
    return JSONResponse({'ok': True, 'categories': prompt_categories(), 'entries': entries, 'names': [e['label'] for e in entries]})


@router.get('/api/prompt-record')
async def api_prompt_record(category: str = '', name: str = '', prompt_id: str = ''):
    rec = get_prompt_record(category=category, name=name, prompt_id=prompt_id)
    if not rec:
        return json_error('Prompt not found.', 404)
    clean = {k: v for k, v in rec.items() if not str(k).startswith('_')}
    return JSONResponse({'ok': True, 'record': clean})


@router.post('/api/update-prompt')
async def api_update_prompt(
    category: str = Form(''),
    name: str = Form(''),
    prompt_id: str = Form(''),
    prompt: str = Form(...),
    model: str = Form('default'),
    notes: str = Form(''),
    raw_prompt: str = Form(''),
    style: str = Form(''),
):
    try:
        rec = update_prompt_record(category=category, name=name, prompt_id=prompt_id, prompt=prompt, model=model, notes=notes, raw_prompt=raw_prompt, style=style)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Updated prompt: {rec['name']}", 'categories': list_categories(), 'prompt_categories': prompt_categories(), 'entries': prompt_entries(category), 'record': rec})


@router.post('/api/delete-prompt')
async def api_delete_prompt(category: str = Form(''), name: str = Form(''), prompt_id: str = Form('')):
    ok = delete_prompt_record(category=category, name=name, prompt_id=prompt_id)
    if not ok:
        return json_error('Prompt not found.', 404)
    return JSONResponse({'ok': True, 'message': 'Deleted prompt.', 'categories': list_categories(), 'prompt_categories': prompt_categories(), 'entries': prompt_entries(category)})


@router.post('/api/improve-prompt')
async def api_improve_prompt(
    model: str = Form('default'),
    prompt: str = Form(...),
    mode: str = Form('Enhance clarity'),
):
    mode = (mode or '').strip()
    mode_map = {
        'Enhance clarity': 'Make this prompt clearer and better structured while preserving the meaning.',
        'Make more descriptive': 'Expand this prompt with more clear, visible details while keeping the same meaning.',
        'Convert to SD tags': 'Convert this into a concise comma-separated Stable Diffusion style prompt.',
        'Convert to descriptive prose': 'Convert this into one clean natural-language image prompt.',
        'Make more cinematic': 'Make this prompt feel more cinematic with camera, lighting, mood, and composition improvements.',
        'Tighten / shorten': 'Shorten this prompt, remove fluff, and keep only the strongest useful details.',
        'Preserve meaning, improve wording': 'Preserve the exact meaning but improve wording and flow.',
        'Expand details': 'Expand the visible details in a useful way without inventing new core elements.',
        'Fix contradictions': 'Remove contradictions and conflicting details. Return one coherent prompt only.',
        'Sort tags by importance': 'Sort the tags so the most important subject and composition tags come first, then clothing, pose, lighting, environment, and style.',
    }
    try:
        improved = await generate_prompt_text(
            idea=prompt,
            model=model,
            style='Custom',
            custom_instructions=mode_map.get(mode, mode or 'Improve this prompt while preserving meaning.'),
            max_tokens=480,
            temperature=0.28,
            top_p=0.9,
            top_k=40,
        )
    except Exception as e:
        logger.exception('Unhandled API exception')
        return json_error(str(e), 500)
    return JSONResponse({'ok': True, 'prompt': improved.get('text', ''), 'finish_reason': improved.get('finish_reason', '')})


@router.post('/api/prompt-qa')
async def api_prompt_qa(prompt: str = Form(...)):
    try:
        return JSONResponse(lint_prompt(prompt))
    except Exception as e:
        logger.exception('Unhandled API exception')
        return json_error(str(e), 500)


@router.post('/api/save-prompt')
async def api_save_prompt(
    name: str = Form(...),
    category: str = Form('uncategorized'),
    prompt: str = Form(...),
    model: str = Form('default'),
    notes: str = Form(''),
    raw_prompt: str = Form(''),
    preset_name: str = Form(''),
    style: str = Form(''),
    finish_reason: str = Form(''),
    settings_json: str = Form(''),
    generation_mode: str = Form('generate'),
):
    try:
        settings = json.loads(settings_json) if settings_json else {}
        rec = save_prompt(
            name=name,
            category=category,
            prompt=prompt,
            model=model,
            notes=notes,
            raw_prompt=raw_prompt,
            preset_name=preset_name,
            style=style,
            finish_reason=finish_reason,
            settings=settings if isinstance(settings, dict) else {},
            generation_mode=generation_mode,
        )
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Saved prompt as {rec['name']} in {rec['category']}.", 'categories': list_categories(), 'prompt_categories': prompt_categories(), 'entries': prompt_entries(category), 'stats': stats(), 'record': rec})
