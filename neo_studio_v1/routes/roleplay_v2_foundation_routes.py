from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..utils.roleplay_v2_foundation import get_roleplay_v2_foundation_state
from .common import json_error

router = APIRouter()


@router.get('/api/roleplay/v2/foundation-state')
async def api_roleplay_v2_foundation_state():
    try:
        return JSONResponse(get_roleplay_v2_foundation_state())
    except Exception as exc:
        return json_error(str(exc), 500)
