from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_breakdown_helper import generate_breakdown_for_document, get_breakdown_output
from ..utils.roleplay_v2_review_actions import update_breakdown
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/v2/breakdown/from-document')
async def api_roleplay_v2_breakdown_from_document(document_id: str = Form('')):
    clean_document_id = str(document_id or '').strip()
    if not clean_document_id:
        return json_error('Source document id is required.', 400)
    try:
        helper_output = generate_breakdown_for_document(clean_document_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    title = ((helper_output.get('structured_payload') or {}).get('title') or helper_output.get('id') or 'document').strip()
    return JSONResponse({'ok': True, 'helper_output': helper_output, 'message': f'Breakdown ready for {title}.'})


@router.get('/api/roleplay/v2/breakdown/output')
async def api_roleplay_v2_breakdown_output(helper_output_id: str = ''):
    output = get_breakdown_output(helper_output_id)
    if not output:
        return json_error('Breakdown output not found.', 404)
    return JSONResponse({'ok': True, 'helper_output': output})


@router.post('/api/roleplay/v2/breakdown/review-save')
async def api_roleplay_v2_breakdown_review_save(
    helper_output_id: str = Form(''),
    cleaned_text: str = Form(''),
    structured_payload_json: str = Form('{}'),
    approved: str = Form('false'),
    review_notes: str = Form(''),
):
    clean_helper_output_id = str(helper_output_id or '').strip()
    if not clean_helper_output_id:
        return json_error('Helper output id is required.', 400)
    try:
        structured_payload = json.loads(structured_payload_json or '{}') if structured_payload_json else {}
    except Exception:
        return json_error('structured_payload_json must be valid JSON.', 400)
    try:
        updated = update_breakdown(
            helper_output_id=clean_helper_output_id,
            cleaned_text=cleaned_text,
            structured_payload=structured_payload if isinstance(structured_payload, dict) else None,
            approved=str(approved or '').strip().lower() in {'1', 'true', 'yes', 'on'},
            review_notes=review_notes,
        )
    except Exception as exc:
        return json_error(str(exc), 400)
    status = ((updated.get('meta') or {}).get('status') or 'reviewed').strip()
    return JSONResponse({'ok': True, 'helper_output': updated, 'message': f'Breakdown saved with status {status}.'})
