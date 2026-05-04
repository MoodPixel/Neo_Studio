from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.characters import character_entries, delete_character_record, get_character_record, save_character_record
from ..utils.kobold import improve_character_card
from ..utils.logging_utils import get_logger
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


@router.get('/api/character-records')
async def api_character_records():
    entries = character_entries()
    return JSONResponse({'ok': True, 'entries': entries, 'names': [e['label'] for e in entries]})


@router.get('/api/character-record')
async def api_character_record(name: str = ''):
    rec = get_character_record(name)
    if not rec:
        return json_error('Character not found.', 404)
    return JSONResponse({'ok': True, 'record': rec})


@router.post('/api/save-character')
async def api_save_character(name: str = Form(...), content: str = Form(...)):
    try:
        rec = save_character_record(name, content)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'message': f"Saved character: {rec['name']}", 'entries': character_entries(), 'record': rec})


@router.post('/api/delete-character')
async def api_delete_character(name: str = Form(...)):
    if not delete_character_record(name):
        return json_error('Character not found.', 404)
    return JSONResponse({'ok': True, 'message': 'Deleted character.', 'entries': character_entries()})


@router.post('/api/improve-character')
async def api_improve_character(
    model: str = Form('default'),
    content: str = Form(...),
    mode: str = Form('Enhance clarity'),
):
    mode = (mode or '').strip()
    mode_map = {
        'Enhance clarity': 'Make the character card clearer and better organized while preserving the same identity and core traits.',
        'Expand details': 'Add more visible appearance, styling, and prompt-useful details while preserving the same identity.',
        'Make more prompt-ready': 'Make the card especially reusable for future image prompts while keeping the same character identity.',
        'Make more consistent': 'Remove contradictions and keep the wording internally consistent.',
        'Create alternate version': 'Create one alternate presentation of the same character while preserving the core identity.',
        'Tighten / shorten': 'Keep the same character but make the card tighter and more concise.',
    }
    try:
        improved = await improve_character_card(
            content=content,
            model=model,
            mode=mode_map.get(mode, mode or 'Refine this character card while preserving the same identity.'),
            max_tokens=520,
            temperature=0.22,
            top_p=0.9,
            top_k=40,
        )
    except Exception as e:
        logger.exception('Unhandled API exception')
        return json_error(str(e), 500)
    return JSONResponse({'ok': True, 'content': improved.get('text', ''), 'finish_reason': improved.get('finish_reason', '')})
