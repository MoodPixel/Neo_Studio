from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.kobold import clamp_float, clamp_int
from ..utils.roleplay_packet_builder import build_runtime_roleplay_bundle
from .common import json_error

router = APIRouter()


@router.post('/api/roleplay/packet-preview')
async def api_roleplay_packet_preview(
    scenario: str = Form(''),
    user_name: str = Form(''),
    partner_name: str = Form(''),
    tone: str = Form(''),
    custom_tone: str = Form(''),
    style: str = Form('Immersive dialogue'),
    scene_notes: str = Form(''),
    memory_notes: str = Form(''),
    author_note: str = Form(''),
    canon_mode: str = Form('what_if'),
    output_preset: str = Form('roleplay'),
    max_tokens: int = Form(320),
    temperature: float = Form(0.82),
    top_p: float = Form(0.92),
    top_k: int = Form(60),
):
    try:
        packet = build_runtime_roleplay_bundle(
            scenario=scenario,
            user_name=user_name,
            partner_name=partner_name,
            tone=tone,
            custom_tone=custom_tone,
            style=style,
            scene_notes=scene_notes,
            memory_notes=memory_notes,
            author_note=author_note,
            canon_mode=canon_mode,
            output_preset=output_preset,
            max_tokens=clamp_int(max_tokens, 96, 1200, 320),
            temperature=clamp_float(temperature, 0.0, 1.5, 0.82),
            top_p=clamp_float(top_p, 0.0, 1.0, 0.92),
            top_k=clamp_int(top_k, 0, 200, 60),
        )
        return JSONResponse({'ok': True, 'packet': packet})
    except Exception as exc:
        return json_error(str(exc), 500)
