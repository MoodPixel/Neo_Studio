from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..utils.config import TEMPLATES_DIR
from ..utils.shared_data_paths import studio_data_path
from ..utils.scene_director import (
    SCENE_DIRECTOR_PACK_ZIP,
    build_scene_director_status,
    default_scene_json,
    workflow_path_by_name,
)
from .common import json_error, json_exception

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PRESET_DIR = studio_data_path('scene_presets', legacy_rel='scene_presets')
IDENTITY_PROFILE_DIR = studio_data_path('identity_profiles', legacy_rel='identity_profiles')
PRESET_VERSION = 1
IDENTITY_PROFILE_VERSION = 1


class ScenePresetSaveRequest(BaseModel):
    name: str
    preset: dict


class IdentityProfileSaveRequest(BaseModel):
    name: str
    profile: dict



def _safe_identity_slug(name: str) -> str:
    value = re.sub(r'[^a-zA-Z0-9._ -]+', '', str(name or '').strip())
    value = re.sub(r'\s+', '_', value).strip('._- ')
    return value[:80] or 'identity_profile'


def _identity_profile_path(name: str) -> Path:
    slug = _safe_identity_slug(name)
    root = IDENTITY_PROFILE_DIR.resolve()
    path = (IDENTITY_PROFILE_DIR / f'{slug}.json').resolve()
    if root not in path.parents and path != root:
        raise ValueError('Invalid identity profile name.')
    return path


def _find_identity_profile_path(name: str) -> Path | None:
    direct = _identity_profile_path(name)
    if direct.exists():
        return direct
    slug = _safe_identity_slug(name)
    if not IDENTITY_PROFILE_DIR.exists():
        return None
    for path in IDENTITY_PROFILE_DIR.glob('*.json'):
        if path.stem == slug or path.name == name:
            return path
    return None


def _identity_profile_summary(path: Path) -> dict:
    data: dict = {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        data = {}
    profile = data.get('profile') if isinstance(data.get('profile'), dict) else data
    name = str(data.get('name') or profile.get('profile_name') or profile.get('name') or path.stem)
    refs = profile.get('reference_images') if isinstance(profile, dict) else []
    return {
        'name': name,
        'profile_name': name,
        'id': str(profile.get('id') or path.stem) if isinstance(profile, dict) else path.stem,
        'slug': path.stem,
        'filename': path.name,
        'updated_at': data.get('updated_at') or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        'mode': str(profile.get('ipadapter_mode') or profile.get('mode') or 'faceid') if isinstance(profile, dict) else 'faceid',
        'reference_count': len(refs or []) if isinstance(refs, list) else 0,
        'has_lora': bool((profile.get('lora') or {}).get('name')) if isinstance(profile.get('lora'), dict) else False,
    }

def _safe_preset_slug(name: str) -> str:
    value = re.sub(r'[^a-zA-Z0-9._ -]+', '', str(name or '').strip())
    value = re.sub(r'\s+', '_', value).strip('._- ')
    return value[:80] or 'scene_preset'


def _preset_path(name: str) -> Path:
    slug = _safe_preset_slug(name)
    root = PRESET_DIR.resolve()
    path = (PRESET_DIR / f'{slug}.json').resolve()
    if root not in path.parents and path != root:
        raise ValueError('Invalid preset name.')
    return path


def _find_preset_path(name: str) -> Path | None:
    direct = _preset_path(name)
    if direct.exists():
        return direct
    slug = _safe_preset_slug(name)
    if not PRESET_DIR.exists():
        return None
    for path in PRESET_DIR.glob('*.json'):
        if path.stem == slug or path.name == name:
            return path
    return None


def _preset_summary(path: Path) -> dict:
    data: dict = {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        data = {}
    preset = data.get('preset') if isinstance(data.get('preset'), dict) else data
    name = str(data.get('name') or preset.get('name') or path.stem)
    return {
        'name': name,
        'slug': path.stem,
        'filename': path.name,
        'updated_at': data.get('updated_at') or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        'region_count': len((preset.get('regions') if isinstance(preset, dict) else []) or []),
    }


@router.get('/scene-director', response_class=HTMLResponse)
async def scene_director_page(request: Request):
    status = build_scene_director_status()
    return templates.TemplateResponse(request, 'scene_director.html', {'request': request, 'status': status})


@router.get('/api/scene-director/status')
async def api_scene_director_status():
    try:
        return JSONResponse(build_scene_director_status())
    except Exception as exc:
        return json_exception(exc, default_message='Could not load Scene Director status.', default_status=500)


@router.get('/api/scene-director/default-scene')
async def api_scene_director_default_scene(case: str = 'pose_interaction'):
    try:
        return JSONResponse({'ok': True, 'scene': default_scene_json(case)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not build default scene JSON.', default_status=500)


@router.get('/api/scene-director/workflows/{workflow_name}')
async def api_scene_director_workflow(workflow_name: str):
    try:
        path = workflow_path_by_name(workflow_name)
        if not path:
            return json_error('Workflow was not found.', 404)
        return FileResponse(str(path), filename=path.name, media_type='application/json')
    except Exception as exc:
        return json_exception(exc, default_message='Could not return workflow file.', default_status=500)


@router.get('/api/scene-director/download-node-pack')
async def api_scene_director_download_node_pack():
    try:
        if not SCENE_DIRECTOR_PACK_ZIP.exists():
            return json_error('Scene Director node pack is missing from Neo Studio.', 404)
        return FileResponse(str(SCENE_DIRECTOR_PACK_ZIP), filename=SCENE_DIRECTOR_PACK_ZIP.name, media_type='application/zip')
    except Exception as exc:
        return json_exception(exc, default_message='Could not download Scene Director node pack.', default_status=500)


@router.get('/api/scene-director/presets')
async def api_scene_director_list_presets():
    try:
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        presets = [_preset_summary(path) for path in sorted(PRESET_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)]
        return JSONResponse({'ok': True, 'presets': presets})
    except Exception as exc:
        return json_exception(exc, default_message='Could not list Scene Director presets.', default_status=500)


@router.get('/api/scene-director/presets/{preset_name}')
async def api_scene_director_load_preset(preset_name: str):
    try:
        path = _find_preset_path(preset_name)
        if not path:
            return json_error('Scene preset was not found.', 404)
        data = json.loads(path.read_text(encoding='utf-8'))
        preset = data.get('preset') if isinstance(data.get('preset'), dict) else data
        return JSONResponse({'ok': True, 'name': data.get('name') or preset.get('name') or path.stem, 'preset': preset, 'meta': _preset_summary(path)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load Scene Director preset.', default_status=500)


@router.post('/api/scene-director/presets')
async def api_scene_director_save_preset(payload: ScenePresetSaveRequest):
    try:
        name = str(payload.name or '').strip()
        if not name:
            return json_error('Preset name is required.', 400)
        preset = payload.preset if isinstance(payload.preset, dict) else {}
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        preset = {**preset, 'name': preset.get('name') or name, 'version': preset.get('version') or PRESET_VERSION}
        path = _preset_path(name)
        path.write_text(json.dumps({'ok': True, 'version': PRESET_VERSION, 'name': name, 'updated_at': now, 'preset': preset}, indent=2, ensure_ascii=False), encoding='utf-8')
        return JSONResponse({'ok': True, 'preset': _preset_summary(path)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save Scene Director preset.', default_status=500)


@router.delete('/api/scene-director/presets/{preset_name}')
async def api_scene_director_delete_preset(preset_name: str):
    try:
        path = _find_preset_path(preset_name)
        if not path:
            return json_error('Scene preset was not found.', 404)
        path.unlink()
        return JSONResponse({'ok': True})
    except Exception as exc:
        return json_exception(exc, default_message='Could not delete Scene Director preset.', default_status=500)


@router.get('/api/scene-director/identity-profiles')
async def api_scene_director_list_identity_profiles():
    try:
        IDENTITY_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        profiles = [_identity_profile_summary(path) for path in sorted(IDENTITY_PROFILE_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)]
        return JSONResponse({'ok': True, 'profiles': profiles})
    except Exception as exc:
        return json_exception(exc, default_message='Could not list Identity Profiles.', default_status=500)


@router.get('/api/scene-director/identity-profiles/{profile_name}')
async def api_scene_director_load_identity_profile(profile_name: str):
    try:
        path = _find_identity_profile_path(profile_name)
        if not path:
            return json_error('Identity profile was not found.', 404)
        data = json.loads(path.read_text(encoding='utf-8'))
        profile = data.get('profile') if isinstance(data.get('profile'), dict) else data
        name = data.get('name') or profile.get('profile_name') or profile.get('name') or path.stem
        return JSONResponse({'ok': True, 'name': name, 'profile': profile, 'meta': _identity_profile_summary(path)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load Identity Profile.', default_status=500)


@router.post('/api/scene-director/identity-profiles')
async def api_scene_director_save_identity_profile(payload: IdentityProfileSaveRequest):
    try:
        name = str(payload.name or '').strip()
        if not name:
            return json_error('Identity profile name is required.', 400)
        profile = payload.profile if isinstance(payload.profile, dict) else {}
        IDENTITY_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        slug = _safe_identity_slug(name)
        profile = {
            **profile,
            'id': str(profile.get('id') or slug),
            'profile_name': str(profile.get('profile_name') or profile.get('name') or name),
            'name': str(profile.get('name') or profile.get('profile_name') or name),
            'version': profile.get('version') or IDENTITY_PROFILE_VERSION,
            'ipadapter_mode': str(profile.get('ipadapter_mode') or profile.get('mode') or 'faceid'),
            'reference_images': profile.get('reference_images') if isinstance(profile.get('reference_images'), list) else [],
        }
        path = _identity_profile_path(name)
        path.write_text(json.dumps({'ok': True, 'version': IDENTITY_PROFILE_VERSION, 'name': name, 'updated_at': now, 'profile': profile}, indent=2, ensure_ascii=False), encoding='utf-8')
        return JSONResponse({'ok': True, 'profile': _identity_profile_summary(path)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save Identity Profile.', default_status=500)


@router.delete('/api/scene-director/identity-profiles/{profile_name}')
async def api_scene_director_delete_identity_profile(profile_name: str):
    try:
        path = _find_identity_profile_path(profile_name)
        if not path:
            return json_error('Identity profile was not found.', 404)
        path.unlink()
        return JSONResponse({'ok': True})
    except Exception as exc:
        return json_exception(exc, default_message='Could not delete Identity Profile.', default_status=500)
