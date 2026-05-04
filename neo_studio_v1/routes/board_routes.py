from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..utils.board_store import clear_board_recovery, create_board, delete_board, ensure_board_foundation, list_boards, load_board, load_board_recovery, rename_board, resolve_board_media_path, save_board, save_board_audio_upload, save_board_image_upload, save_board_recovery, save_board_video_upload
from .common import json_error

router = APIRouter()
ensure_board_foundation()


async def _json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


@router.get('/api/board/boards')
async def api_board_list():
    return JSONResponse({'ok': True, 'boards': list_boards()})


@router.post('/api/board/boards')
async def api_board_create(request: Request):
    payload = await _json_payload(request)
    try:
        board = create_board(str(payload.get('name') or 'Untitled Board'))
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'board': board, 'boards': list_boards()})


@router.get('/api/board/boards/{board_id}')
async def api_board_load(board_id: str):
    try:
        board = load_board(board_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    if not board:
        return json_error('Board not found.', 404)
    return JSONResponse({'ok': True, 'board': board})


@router.put('/api/board/boards/{board_id}')
async def api_board_save(board_id: str, request: Request):
    payload = await _json_payload(request)
    board_payload = payload.get('board') if isinstance(payload.get('board'), dict) else payload
    try:
        board = save_board(board_id, board_payload)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'board': board, 'boards': list_boards()})


@router.get('/api/board/boards/{board_id}/recovery')
async def api_board_recovery_load(board_id: str):
    try:
        recovery = load_board_recovery(board_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'recovery': recovery})


@router.post('/api/board/boards/{board_id}/recovery')
async def api_board_recovery_save(board_id: str, request: Request):
    payload = await _json_payload(request)
    board_payload = payload.get('board') if isinstance(payload.get('board'), dict) else payload
    try:
        recovery = save_board_recovery(board_id, board_payload)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'recovery': recovery})


@router.delete('/api/board/boards/{board_id}/recovery')
async def api_board_recovery_clear(board_id: str):
    try:
        clear_board_recovery(board_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True})



@router.patch('/api/board/boards/{board_id}/rename')
async def api_board_rename(board_id: str, request: Request):
    payload = await _json_payload(request)
    try:
        board = rename_board(board_id, str(payload.get('name') or ''))
    except FileNotFoundError:
        return json_error('Board not found.', 404)
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'board': board, 'boards': list_boards()})



@router.post('/api/board/media/images')
async def api_board_upload_image(file: UploadFile = File(...)):
    try:
        saved = save_board_image_upload(file.file, file.filename or '', file.content_type or '')
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'media': saved})



@router.post('/api/board/media/audio')
async def api_board_upload_audio(file: UploadFile = File(...)):
    try:
        saved = save_board_audio_upload(file.file, file.filename or '', file.content_type or '')
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'media': saved})



@router.post('/api/board/media/videos')
async def api_board_upload_video(file: UploadFile = File(...)):
    try:
        saved = save_board_video_upload(file.file, file.filename or '', file.content_type or '')
    except Exception as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'media': saved})

@router.get('/api/board/media/{media_kind}/{filename}')
async def api_board_media_file(media_kind: str, filename: str):
    path = resolve_board_media_path(media_kind, filename)
    if not path:
        return json_error('Board media not found.', 404)
    return FileResponse(path)

@router.delete('/api/board/boards/{board_id}')
async def api_board_delete(board_id: str):
    try:
        existed = delete_board(board_id)
    except Exception as exc:
        return json_error(str(exc), 400)
    if not existed:
        return json_error('Board not found.', 404)
    return JSONResponse({'ok': True, 'boards': list_boards()})
