from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..utils.library_settings_store import list_categories, set_library_root
from ..utils.library_stats import stats
from ..utils.logging_utils import get_logger
from .common import json_error

logger = get_logger(__name__)
router = APIRouter()


def _pick_folder_dialog(initial_path: str = '') -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes('-topmost', True)
        root.lift()
    except Exception:
        pass
    start_dir = str(initial_path or '').strip()
    if start_dir and Path(start_dir).exists():
        path = filedialog.askdirectory(parent=root, initialdir=start_dir, mustexist=False) or ''
    else:
        path = filedialog.askdirectory(parent=root, mustexist=False) or ''
    try:
        root.destroy()
    except Exception:
        pass
    return path


@router.post('/api/pick-folder')
async def api_pick_folder(initial_path: str = Form('')):
    try:
        path = await asyncio.to_thread(_pick_folder_dialog, initial_path)
    except Exception as e:
        logger.exception('Folder picker failed')
        return json_error(f'Folder picker failed: {e}', 500)
    return JSONResponse({'ok': True, 'path': path})


@router.post('/api/open-folder')
async def api_open_folder(path: str = Form('')):
    folder = str(path or '').strip()
    if not folder:
        return json_error('No folder path provided.', 400)
    try:
        if not os.path.exists(folder):
            return json_error(f'Folder not found: {folder}', 404)
        if sys.platform.startswith('win'):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
    except Exception as e:
        logger.exception('Open folder failed')
        return json_error(f'Could not open folder: {e}', 500)
    return JSONResponse({'ok': True, 'message': f'Opened: {folder}'})


@router.post('/api/save-settings')
async def api_save_settings(library_root: str = Form(...)):
    try:
        set_library_root(library_root)
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    return JSONResponse({'ok': True, 'stats': stats(), 'categories': list_categories()})
