from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import traceback
import zipfile
from urllib.parse import urlencode
from pathlib import Path
from PIL import Image, ImageOps
from uuid import uuid4
from typing import Any

import cv2
import httpx
import numpy as np
import websockets
from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response

from ..utils.backend_manager import get_profile, get_manager_state
from ..utils.comfy_adapter import ComfyBackendAdapter
from ..utils.image_workflow_core import build_image_workflow, detect_image_workflow_command
from ..extensions.image.scene_director.adapter import scene_director_to_regional_payload
from ..extensions.runtime.external_workflow_executor import apply_external_workflow_injection
from ..contracts.job_records import infer_generation_family
from ..contracts.output_records import build_generation_output_sidecar
from ..contracts.generation_families import normalize_generation_mode, normalize_inpaint_backend, validate_generation_support
from ..contracts.inpaint_payloads import get_shared_inpaint_payload, merge_shared_inpaint_payload
from ..contracts.image_payloads import flatten_image_payload_envelope, build_image_payload_envelope
from ..contracts.external_extension_payloads import build_external_extension_output_metadata_shell, stamp_external_extension_payload_contract
from ..contracts.retired_image_sections import sanitize_image_payload_for_retired_sections
from ..contracts.image_output_selection import require_preview_source_lock
from ..utils.generation_jobs import (
    GENERATION_INPUT_DIR,
    create_generation_job,
    ensure_generation_dirs,
    get_generation_job,
    list_generation_jobs,
    update_generation_job,
)
from ..utils.generation_output_settings import (
    DEFAULT_OUTPUT_ROOT,
    add_generation_category,
    category_display_name,
    category_slug,
    ensure_category_dir,
    ensure_output_root,
    load_generation_output_settings,
    next_category_index,
    save_generation_output_settings,
)
from ..utils.generation_styles import (
    delete_generation_style,
    duplicate_generation_style,
    export_generation_styles_path,
    import_generation_styles_csv,
    load_generation_styles,
    upsert_generation_style,
)
from ..utils.generation_workspace_presets import load_workspace_presets, save_workspace_presets
from ..utils.extension_registry import build_external_extension_registry, rebuild_extension_registry
from ..utils.library_common import safe_name
from ..utils.library_settings_store import get_library_root
from ..utils.detailer_models import download_sam_model, list_generation_detailer_models, prepare_detailer_assets_for_payload
from ..utils.detailer_preview import preview_detailer_detections
from ..utils.generation_dependency_audit import build_generation_dependency_audit
from ..utils.logging_utils import get_logger
from ..utils.config import LOGS_DIR
from ..utils.storage_io import atomic_write_json
from ..utils.draft_store import load_draft, save_draft
from ..utils.long_task_jobs import create_long_task, get_long_task, update_long_task
from ..utils.shared_data_paths import studio_data_path
from .common import json_error, json_exception

router = APIRouter()
logger = get_logger(__name__)

# Phase C1: runtime generation crash guard + focused logs.
GENERATION_RUNTIME_LOG_PATH = LOGS_DIR / 'neo_generation_runtime.log'
GENERATION_BACKEND_HEALTH_LOG_PATH = LOGS_DIR / 'neo_backend_health.log'
GENERATION_LAST_PAYLOAD_PATH = LOGS_DIR / 'neo_last_payload.json'
GENERATION_LAST_WORKFLOW_PATH = LOGS_DIR / 'neo_last_workflow.json'


@router.get('/api/generation/workspace-presets')
async def api_generation_workspace_presets():
    try:
        return JSONResponse({'ok': True, **load_workspace_presets()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load workspace presets.', default_status=500)


@router.put('/api/generation/workspace-presets')
async def api_save_generation_workspace_presets(request: Request):
    try:
        payload = await request.json()
        return JSONResponse({'ok': True, **save_workspace_presets(payload if isinstance(payload, dict) else {})})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save workspace presets.', default_status=500)
GENERATION_LAST_ERROR_PATH = LOGS_DIR / 'neo_last_generation_error.txt'


def _append_generation_log(message: str, *, path: Path | None = None, exc: Exception | None = None, context: dict | None = None) -> None:
    try:
        target = path or GENERATION_RUNTIME_LOG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"]
        if context:
            try:
                lines.append(json.dumps(context, ensure_ascii=False, default=str))
            except Exception:
                lines.append(str(context))
        if exc is not None:
            lines.append(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        with target.open('a', encoding='utf-8') as fh:
            fh.write('\n'.join(lines).rstrip() + '\n')
    except Exception:
        # Logging must never become the reason Neo closes.
        pass


def _safe_write_generation_debug_json(path: Path, payload: object) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    except Exception as exc:
        _append_generation_log(f'Could not write generation debug JSON: {path}', exc=exc)


def _generation_runtime_error_update(job: dict | None, target_job_id: str, text: str, exc: Exception, *, phase: str = 'runtime_guard_failed') -> dict | None:
    context = {
        'job_id': target_job_id,
        'prompt_id': (job or {}).get('prompt_id') if isinstance(job, dict) else '',
        'phase': phase,
    }
    _append_generation_log(text, exc=exc, context=context)
    try:
        GENERATION_LAST_ERROR_PATH.write_text(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)), encoding='utf-8')
    except Exception:
        pass
    meta = _with_finalization(job or {}, phase=phase, last_error=str(exc))
    return update_generation_job(target_job_id, _job_state_update(
        'error',
        text,
        progress=100,
        finalization=meta,
        error=f'{type(exc).__name__}: {exc}',
    )) if target_job_id else job
GENERATION_DRAFT_PATH = studio_data_path('generation_draft.json', legacy_rel='generation_draft.json', default_json={})
GENERATION_REJECTED_WORKFLOW_PATH = studio_data_path('debug_last_rejected_workflow.json', legacy_rel='debug_last_rejected_workflow.json', default_json={})
_OUTPUT_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
_MODE_OUTPUT_DIRS = {'txt2img': 'txt2img-images', 'img2img': 'img2img-images', 'inpaint': 'inpaint-images', 'outpaint': 'outpaint-images'}
CONTROLNET_MAP_NAMESPACE = 'controlnet_map_builder'
TAG_ASSIST_NAMESPACE = 'tag_assist'
CONTROLNET_BATCH_MAP_NAMESPACE = 'controlnet_batch_map_builder'

# Phase 9: Image tab workflow presets for practical ControlNet stacks.
CONTROLNET_IMAGE_WORKFLOW_PRESETS = [
    {'id':'character_pose_transfer','title':'Character pose transfer','category':'Character / pose','description':'Keep the reference body pose while changing style, outfit, lighting, or scene.','mode':'img2img','recommended_size':'832x1216','prompt_helper':'full body portrait, clean anatomy, strong silhouette, cinematic lighting, detailed clothing, natural pose','negative_helper':'bad anatomy, broken hands, extra fingers, twisted limbs, duplicate body, distorted face','controlnet_units':[{'unit':'OpenPose / DWPose','preprocessor':'OpenPose / DWPose','model_kind':'openpose','strength':0.78,'start_percent':0.0,'end_percent':0.85,'detect_resolution':1024,'fit_mode':'contain','openpose_body':True,'openpose_hand':True,'openpose_face':False}]},
    {'id':'product_redraw_edges','title':'Product redraw','category':'Product / object','description':'Keep product silhouette and object edges while changing background, lighting, or ad style.','mode':'img2img','recommended_size':'1024x1024','prompt_helper':'premium product shot, clean studio lighting, sharp details, commercial advertising style, realistic materials','negative_helper':'warped logo, unreadable text, melted object, extra parts, blurry edges','controlnet_units':[{'unit':'Canny','preprocessor':'Canny / Aux Edge node','model_kind':'canny','strength':0.55,'start_percent':0.0,'end_percent':0.8,'detect_resolution':1024,'fit_mode':'contain','canny_low':80,'canny_high':180}]},
    {'id':'room_interior_redesign','title':'Room / interior redesign','category':'Architecture / interior','description':'Preserve room layout and camera angle while redesigning style, decor, and mood.','mode':'img2img','recommended_size':'1216x832','prompt_helper':'modern interior design, clean architecture, realistic lighting, cohesive decor, wide angle room photo','negative_helper':'warped room, broken perspective, floating furniture, distorted walls, clutter','controlnet_units':[{'unit':'Depth / DepthAnythingV2','preprocessor':'Depth / DepthAnythingV2 Base','model_kind':'depth','strength':0.62,'start_percent':0.0,'end_percent':0.85,'detect_resolution':1024,'fit_mode':'contain'},{'unit':'Canny','preprocessor':'Canny / Aux Edge node','model_kind':'canny','strength':0.32,'start_percent':0.0,'end_percent':0.55,'detect_resolution':1024,'fit_mode':'contain','canny_low':100,'canny_high':200}]},
    {'id':'anime_style_conversion','title':'Anime / illustration conversion','category':'Style conversion','description':'Convert photo reference into anime or illustration while keeping pose and major shapes.','mode':'img2img','recommended_size':'832x1216','prompt_helper':'anime illustration, clean linework, expressive eyes, soft cel shading, detailed character design, polished artwork','negative_helper':'photorealistic, messy linework, bad anatomy, extra limbs, deformed hands','controlnet_units':[{'unit':'Lineart Anime','preprocessor':'Lineart Anime','model_kind':'lineart','strength':0.68,'start_percent':0.0,'end_percent':0.85,'detect_resolution':1024,'fit_mode':'contain','lineart_coarse':False},{'unit':'Depth / DepthAnythingV2','preprocessor':'Depth / DepthAnythingV2 Base','model_kind':'depth','strength':0.35,'start_percent':0.0,'end_percent':0.6,'detect_resolution':1024,'fit_mode':'contain'}]},
    {'id':'logo_edge_preservation','title':'Logo / graphic edge preservation','category':'Graphic / logo','description':'Preserve logo, emblem, or graphic silhouette for stylized treatments and mockups.','mode':'img2img','recommended_size':'1024x1024','prompt_helper':'clean vector-inspired graphic, premium brand mark, crisp edges, polished lighting, high contrast','negative_helper':'warped logo, unreadable text, extra letters, messy edges, blurry','controlnet_units':[{'unit':'Lineart','preprocessor':'Lineart','model_kind':'lineart','strength':0.75,'start_percent':0.0,'end_percent':0.9,'detect_resolution':1024,'fit_mode':'contain','lineart_coarse':True},{'unit':'Canny','preprocessor':'Canny / Aux Edge node','model_kind':'canny','strength':0.45,'start_percent':0.0,'end_percent':0.65,'detect_resolution':1024,'fit_mode':'contain','canny_low':80,'canny_high':160}]},
    {'id':'ai_upscale_detail_polish','title':'AI upscale + detail polish','category':'Upscale / refine','description':'Use Tile guidance to preserve structure while improving texture and detail.','mode':'img2img','recommended_size':'match source / upscale pass','prompt_helper':'highly detailed, clean texture, sharp but natural details, realistic lighting, refined finish','negative_helper':'oversharpened, noisy, waxy skin, artifacts, duplicate details','controlnet_units':[{'unit':'Tile / Detail','preprocessor':'None / use current map directly','model_kind':'tile','strength':0.42,'start_percent':0.0,'end_percent':1.0,'detect_resolution':768,'fit_mode':'contain'}]},
    {'id':'photo_to_cinematic','title':'Photo-to-cinematic look','category':'Cinematic / realism','description':'Keep source composition while pushing lighting, mood, and production value.','mode':'img2img','recommended_size':'source ratio','prompt_helper':'cinematic photo, dramatic lighting, shallow depth of field, film still, rich color grading, natural skin texture','negative_helper':'plastic skin, overprocessed, bad anatomy, deformed face, harsh outlines','controlnet_units':[{'unit':'Depth / DepthAnythingV2','preprocessor':'Depth / DepthAnythingV2 Base','model_kind':'depth','strength':0.52,'start_percent':0.0,'end_percent':0.8,'detect_resolution':1024,'fit_mode':'contain'},{'unit':'Soft Edge / HED','preprocessor':'SoftEdge / HED','model_kind':'softedge','strength':0.36,'start_percent':0.0,'end_percent':0.6,'detect_resolution':1024,'fit_mode':'contain','safe_mode':True}]},
]


def _controlnet_model_kind_from_name(name: str) -> str:
    value = str(name or '').lower()
    if 'union' in value or 'promax' in value:
        return 'union'
    if 'openpose' in value or 'dwpose' in value or 'pose' in value:
        return 'openpose'
    if 'depth' in value or 'midas' in value or 'zoe' in value or 'leres' in value:
        return 'depth'
    if 'canny' in value:
        return 'canny'
    if 'lineart' in value or 'line' in value:
        return 'lineart'
    if 'softedge' in value or 'hed' in value or 'pidinet' in value:
        return 'softedge'
    if 'scribble' in value or 'sketch' in value:
        return 'scribble'
    if 'normal' in value or 'bae' in value:
        return 'normal'
    if 'tile' in value:
        return 'tile'
    return 'generic'


def _pick_controlnet_model_for_kind(models: list, kind: str) -> str:
    names = [str(m).strip() for m in models or [] if str(m).strip()]
    kind = str(kind or '').lower().strip()
    exact = [n for n in names if _controlnet_model_kind_from_name(n) == kind]
    if exact:
        return exact[0]
    union = [n for n in names if _controlnet_model_kind_from_name(n) == 'union']
    if union:
        return union[0]
    return names[0] if names else ''


def _materialize_image_workflow_presets(controlnet_models: list | None = None) -> list[dict]:
    presets = json.loads(json.dumps(CONTROLNET_IMAGE_WORKFLOW_PRESETS))
    models = controlnet_models or []
    for preset in presets:
        for unit in preset.get('controlnet_units') or []:
            unit['enabled'] = True
            unit.setdefault('save_intermediate', True)
            unit.setdefault('invert_map', False)
            unit.setdefault('advanced_apply_mode', 'auto')
            unit.setdefault('weight_preset', 'default')
            unit.setdefault('strength_schedule', 'flat')
            unit.setdefault('model', _pick_controlnet_model_for_kind(models, unit.get('model_kind') or ''))
    return presets


def _sanitize_generation_draft_removed_features(draft: dict | None) -> dict:
    """Phase 10.3: remove retired Image Tab section state from saved/restored drafts."""
    if not isinstance(draft, dict):
        return {}
    removed_prefixes = (
        'regional_',
        'regionalPrompt',
        'expression_',
        'expression_editor_',
        'expressionEditor',
        'reference_match_',
        'referenceMatch',
        'cleanup_prep_',
        'cleanupPrep',
    )
    removed_exact = {
        'regionalBackendCapabilities',
        'regional_prompt_regions',
        'regional_backend_capabilities',
        'expression_editor_pass',
        'expression_editor_enabled',
        'expression_pass',
        'expression_enabled',
        'reference_match_enabled',
        'cleanup_prep_enabled',
    }

    def clean(value):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text in removed_exact or any(key_text.startswith(prefix) for prefix in removed_prefixes):
                    continue
                out[key] = clean(item)
            return out
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    cleaned = clean(draft)
    if not isinstance(cleaned, dict):
        cleaned = {}
    try:
        cleaned['version'] = max(int(cleaned.get('version') or 0), 7)
    except Exception:
        cleaned['version'] = 7
    cleaned['_neo_draft_sanitized'] = True
    cleaned['_neo_draft_sanitizer_version'] = 'phase10.3'
    return cleaned


def _extract_required_combo_values(schema_entry) -> list[str]:
    values = []
    if isinstance(schema_entry, (list, tuple)) and schema_entry:
        head = schema_entry[0]
        if isinstance(head, (list, tuple)):
            values.extend(str(item or '').strip() for item in head if str(item or '').strip())
        elif head == 'COMBO' and len(schema_entry) > 1 and isinstance(schema_entry[1], (list, tuple)):
            values.extend(str(item or '').strip() for item in schema_entry[1] if str(item or '').strip())
    elif isinstance(schema_entry, dict):
        options = schema_entry.get('choices') or schema_entry.get('values') or schema_entry.get('options') or []
        if isinstance(options, (list, tuple)):
            values.extend(str(item or '').strip() for item in options if str(item or '').strip())
    return values


def _object_required_inputs(info: dict | None) -> dict:
    if not isinstance(info, dict):
        return {}
    input_block = info.get('input')
    if isinstance(input_block, dict):
        required = input_block.get('required')
        if isinstance(required, dict):
            return required
    required = info.get('required')
    return required if isinstance(required, dict) else {}


def _catalog_choice_values(catalog: dict | None, *keys: str) -> list[str]:
    if not isinstance(catalog, dict):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for key in keys:
        value = catalog.get(key)
        if isinstance(value, dict):
            value = value.get('models') or value.get('items') or value.get('files') or value.get('choices') or value.get('options') or value.get('names') or []
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            raw = item.get('value') or item.get('id') or item.get('name') or item.get('label') if isinstance(item, dict) else item
            name = str(raw or '').strip()
            if name and name not in seen:
                seen.add(name)
                rows.append(name)
    return rows


def _values_matching_needles(values: list[str], needles: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    lowered_needles = tuple(str(item or '').lower() for item in needles if str(item or '').strip())
    for value in values:
        name = str(value or '').strip()
        lower = name.lower()
        if not name or name in seen:
            continue
        if lower in lowered_needles or any(needle in lower for needle in lowered_needles):
            seen.add(name)
            found.append(name)
    return found


async def _detect_res4lyf_catalog(adapter: ComfyBackendAdapter, catalog: dict | None) -> dict:
    """Passive RES4LYF capability probe for the UI catalog."""
    samplers = _catalog_choice_values(catalog, 'samplers')
    schedulers = _catalog_choice_values(catalog, 'schedulers')
    res_samplers = _values_matching_needles(samplers, ('res_2m', 'res_3s', 'res_5s'))
    res_schedulers = _values_matching_needles(schedulers, ('beta57',))
    has_clownshark_sampler = False
    detected_nodes: list[str] = []
    probe_errors: list[str] = []
    try:
        object_info = await adapter.get_object_info()
        if isinstance(object_info, dict):
            for node_name in object_info.keys():
                lower = str(node_name or '').lower()
                if 'clownshark' in lower or 'res4lyf' in lower or lower.startswith('res4'):
                    detected_nodes.append(str(node_name))
                if lower == 'clownsharksampler' or 'clownsharksampler' in lower:
                    has_clownshark_sampler = True
    except Exception as exc:
        probe_errors.append(str(exc))
    installed = bool(res_samplers or res_schedulers or has_clownshark_sampler or detected_nodes)
    ready = bool(res_samplers)
    return {
        'installed': installed,
        'ready': ready,
        'status': 'ready' if ready else ('partial' if installed else 'not_installed'),
        'samplers': res_samplers,
        'schedulers': res_schedulers,
        'has_clownshark_sampler': has_clownshark_sampler,
        'detected_nodes': detected_nodes[:24],
        'probe_errors': probe_errors[:3],
        'note': 'Passive detection only. Neo still uses the existing KSampler workflow path.',
    }


RES4LYF_ADVANCED_ENGINE_KEYS = {'clownshark', 'clownsharksampler', 'res4lyf', 'res4lyf_clownshark'}

def _res4lyf_sampler_engine(payload: dict) -> str:
    raw = str(payload.get('res4lyf_sampler_engine') or payload.get('sampler_engine') or payload.get('advanced_sampler_engine') or 'core').strip().lower()
    if raw in {'', 'auto', 'default', 'core', 'ksampler', 'standard'}:
        return 'core'
    if raw in RES4LYF_ADVANCED_ENGINE_KEYS:
        return 'clownshark'
    return raw

def _extract_object_info_schema(object_info: object, node_name: str) -> dict:
    if not isinstance(object_info, dict):
        return {}
    if node_name in object_info and isinstance(object_info.get(node_name), dict):
        return object_info.get(node_name) or {}
    if 'input' in object_info or 'output' in object_info:
        return object_info
    for key, value in object_info.items():
        if str(key).strip().lower() == node_name.strip().lower() and isinstance(value, dict):
            return value
    return {}

def _schema_input_names(schema: dict) -> set[str]:
    inputs = schema.get('input') if isinstance(schema, dict) else {}
    names: set[str] = set()
    if isinstance(inputs, dict):
        for bucket in ('required', 'optional', 'hidden'):
            bucket_value = inputs.get(bucket)
            if isinstance(bucket_value, dict):
                names.update(str(key) for key in bucket_value.keys())
    return names


def _schema_required_inputs(schema: dict) -> dict:
    inputs = schema.get('input') if isinstance(schema, dict) else {}
    required = inputs.get('required') if isinstance(inputs, dict) else {}
    return required if isinstance(required, dict) else {}

def _schema_default_for(definition):
    if isinstance(definition, (list, tuple)) and len(definition) > 1 and isinstance(definition[1], dict) and 'default' in definition[1]:
        return definition[1].get('default')
    if isinstance(definition, dict) and 'default' in definition:
        return definition.get('default')
    return None

def _apply_clownshark_input_aliases(inputs: dict, accepted_inputs: set[str]) -> dict:
    out = dict(inputs or {})
    if 'seed' in out and 'seed' not in accepted_inputs and 'noise_seed' in accepted_inputs and 'noise_seed' not in out:
        out['noise_seed'] = out.pop('seed')
    return out

def _coerce_res4lyf_advanced_options(payload: dict, accepted_inputs: set[str]) -> dict:
    raw = payload.get('res4lyf_advanced_options') or payload.get('res4lyf_options') or {}
    if not isinstance(raw, dict):
        return {}
    allowed_keys = {
        'sampler_mode',
        'implicit_steps',
        'implicit_sampler_name',
        'noise_type_init',
        'noise_type_sde',
        'noise_mode_sde',
        'eta',
        'denoise_alt',
    }
    out: dict = {}
    for key in allowed_keys:
        if key not in raw or key not in accepted_inputs:
            continue
        value = raw.get(key)
        if value is None:
            continue
        if key == 'implicit_steps':
            try:
                out[key] = max(0, min(100, int(value)))
            except Exception:
                continue
        elif key in {'eta', 'denoise_alt'}:
            try:
                number = float(value)
            except Exception:
                continue
            if key == 'denoise_alt':
                number = max(0.0, min(1.0, number))
            else:
                number = max(0.0, min(2.0, number))
            out[key] = number
        else:
            cleaned = str(value).strip()
            if cleaned:
                out[key] = cleaned
    return out

def _fill_clownshark_safe_defaults(inputs: dict, accepted_inputs: set[str], required_inputs: dict) -> dict:
    out = dict(inputs or {})
    for name, definition in required_inputs.items():
        if name in out or name not in accepted_inputs:
            continue
        default = _schema_default_for(definition)
        if default is not None:
            out[name] = default
    denoise_value = out.get('denoise', 1.0)
    safe_defaults = {
        'noise_seed': out.get('seed', 0),
        'control_after_generate': 'fixed',
        'sampler_mode': 'standard',
        'implicit_steps': 0,
        'implicit_sampler_name': out.get('sampler_name', 'res_2m'),
        'denoise_alt': denoise_value,
        'noise_type_init': 'gaussian',
        'noise_type_sde': 'gaussian',
        'noise_mode_sde': 'hard',
        'eta': 0.0,
    }
    for name, value in safe_defaults.items():
        if name in accepted_inputs and name not in out:
            out[name] = value
    return out

async def _apply_res4lyf_advanced_sampler_lane(adapter: ComfyBackendAdapter, payload: dict, workflow: dict) -> tuple[dict, list[str]]:
    engine = _res4lyf_sampler_engine(payload)
    if engine != 'clownshark':
        return workflow, []
    mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')
    backend = normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard')
    family = str(payload.get('family') or '').strip().lower()
    if family == 'qwen_image_edit' or (mode in RES4LYF_GUARDED_MODES and backend in RES4LYF_BLOCKED_BACKENDS):
        raise ValueError('RES4LYF Advanced Lane is disabled here because this route uses Qwen/LanPaint sampling instead of the RES4LYF ClownsharKSampler path.')
    if mode not in {'txt2img', 'img2img'}:
        raise ValueError(f"RES4LYF Advanced Lane is currently limited to txt2img/img2img. Current mode: {mode}.")
    if _payload_truthy(payload, 'refine_enabled', 'enable_refine', 'hires_fix', 'highres_fix', 'upscale_lab_enabled', 'detailer_enabled', 'adetailer_enabled', 'enable_detailer'):
        raise ValueError('RES4LYF Advanced Lane is blocked when Refine/Highres/Detailer chaining is enabled. Test the base lane first.')
    catalog = {}
    try:
        catalog = await adapter.get_catalog()
    except Exception:
        catalog = {}
    res4lyf = await _detect_res4lyf_catalog(adapter, catalog if isinstance(catalog, dict) else {})
    if not res4lyf.get('has_clownshark_sampler'):
        raise ValueError('RES4LYF Advanced Lane requested, but ClownsharKSampler was not detected in ComfyUI object_info.')
    node_name = 'ClownsharKSampler'
    try:
        object_info = await adapter.get_object_info(node_name)
    except Exception as exc:
        raise ValueError(f"Could not inspect ClownsharKSampler schema: {exc}") from exc
    schema = _extract_object_info_schema(object_info, node_name)
    accepted_inputs = _schema_input_names(schema)
    required_inputs = _schema_required_inputs(schema)
    if not accepted_inputs:
        raise ValueError('ClownsharKSampler schema did not expose input metadata. Neo refused to queue an unsafe experimental graph.')
    mutated = 0
    rejected: list[str] = []
    for node_id, node in (workflow or {}).items():
        if not isinstance(node, dict) or str(node.get('class_type') or '') != 'KSampler':
            continue
        original_inputs = node.get('inputs') or {}
        if not isinstance(original_inputs, dict):
            original_inputs = {}
        remapped_inputs = _apply_clownshark_input_aliases(original_inputs, accepted_inputs)
        remapped_inputs = _fill_clownshark_safe_defaults(remapped_inputs, accepted_inputs, required_inputs)
        remapped_inputs.update(_coerce_res4lyf_advanced_options(payload, accepted_inputs))
        node_inputs = set(remapped_inputs.keys())
        missing = sorted(name for name in node_inputs if name not in accepted_inputs)
        if missing:
            rejected.append(f"{node_id}: unsupported inputs {', '.join(missing[:8])}")
            continue
        node['inputs'] = remapped_inputs
        node['class_type'] = node_name
        mutated += 1
    if rejected:
        raise ValueError('RES4LYF Advanced Lane found KSampler nodes that are not drop-in compatible with ClownsharKSampler: ' + '; '.join(rejected[:3]))
    if not mutated:
        raise ValueError('RES4LYF Advanced Lane requested, but no base KSampler node was found to replace.')
    applied_options = sorted(_coerce_res4lyf_advanced_options(payload, accepted_inputs).keys())
    option_note = f" Advanced controls applied: {', '.join(applied_options)}." if applied_options else ""
    return workflow, [f"RES4LYF Advanced Lane active: replaced {mutated} KSampler node(s) with ClownsharKSampler. Experimental route; verify output and do not batch blindly.{option_note}"]


RES4LYF_SAFE_SAMPLERS = {'res_2m', 'res_3s', 'res_5s'}
RES4LYF_GUARDED_MODES = {'inpaint', 'outpaint'}
RES4LYF_BLOCKED_BACKENDS = {'lanpaint', 'qwen', 'qwen_lanpaint'}


def _is_res4lyf_sampler(value: object) -> bool:
    key = str(value or '').strip().lower()
    return key in RES4LYF_SAFE_SAMPLERS or key.startswith('res_')


def _payload_truthy(payload: dict, *keys: str) -> bool:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            if value:
                return True
        elif isinstance(value, (int, float)):
            if value != 0:
                return True
        elif isinstance(value, str):
            if value.strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'enable'}:
                return True
        elif value:
            return True
    return False


async def _validate_res4lyf_preset_compatibility(adapter: ComfyBackendAdapter, payload: dict) -> list[str]:
    """Phase 5 guardrail: RES presets stay inside known-safe KSampler routes."""
    sampler = str(payload.get('sampler') or '').strip()
    if not _is_res4lyf_sampler(sampler):
        return []

    catalog = {}
    try:
        catalog = await adapter.get_catalog()
    except Exception:
        catalog = {}
    res4lyf = await _detect_res4lyf_catalog(adapter, catalog if isinstance(catalog, dict) else {})
    detected = {str(item or '').strip().lower() for item in (res4lyf.get('samplers') or [])}
    if sampler.lower() not in detected:
        raise ValueError(f"RES4LYF sampler '{sampler}' is not available in the live ComfyUI catalog. Refresh the backend catalog or choose a standard sampler.")

    mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')
    backend = normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard')
    family = str(payload.get('family') or '').strip().lower()
    model_source = str(payload.get('model_source') or '').strip().lower()
    gguf_clip_type = str(payload.get('gguf_clip_type') or '').strip().lower()
    gguf_unet = str(payload.get('gguf_unet') or '').strip()

    # LanPaint is only a sampler-route concern for inpaint/outpaint. Keep txt2img/img2img
    # safe even if the UI has a stale inpaint backend value from a previous Qwen session.
    uses_lanpaint_route = mode in RES4LYF_GUARDED_MODES and backend in RES4LYF_BLOCKED_BACKENDS

    # Do not trust the family tab alone. Draft restores / stale tab state can briefly say
    # qwen_image_edit while the actual queued route is still checkpoint SDXL/SD.
    # Treat Qwen as a RES-blocked route only when the payload is really using the Qwen GGUF lane
    # or when Qwen inpaint is explicitly going through LanPaint.
    uses_qwen_route = (
        family == 'qwen_image_edit'
        and (
            model_source == 'gguf'
            or gguf_clip_type == 'qwen_image'
            or bool(gguf_unet)
            or uses_lanpaint_route
        )
    )
    if uses_qwen_route or uses_lanpaint_route:
        raise ValueError('RES4LYF safe sampler presets are disabled here because this route uses LanPaint_KSampler or Qwen sampling, not the normal KSampler preset path. Check _neo_lanpaint_sampler_policy for requested/effective sampler, scheduler, and LanPaint thinking depth.')

    if mode in RES4LYF_GUARDED_MODES and backend != 'standard':
        raise ValueError('RES4LYF safe sampler presets are only allowed on the standard inpaint/outpaint backend for now.')

    if _payload_truthy(payload, 'refine_enabled', 'enable_refine', 'hires_fix', 'highres_fix', 'upscale_lab_enabled'):
        raise ValueError('RES4LYF safe sampler presets are temporarily blocked when Refine/Upscale/Highres chaining is enabled. Test the base pass first, then refine with a standard sampler.')

    if _payload_truthy(payload, 'detailer_enabled', 'adetailer_enabled', 'enable_detailer'):
        raise ValueError('RES4LYF safe sampler presets are temporarily blocked when Detailer/ADetailer is enabled. Run the base RES pass first, then detail with a standard sampler.')

    if mode not in {'txt2img', 'img2img', 'inpaint', 'outpaint'}:
        raise ValueError(f"RES4LYF safe sampler presets are not enabled for mode '{mode}' yet.")

    note = f"RES4LYF compatibility guard passed: {sampler} on {mode} via existing KSampler path."
    if mode in RES4LYF_GUARDED_MODES:
        note += ' Mask/boundary behavior is still treated as guarded; review output edges before batch use.'
    return [note]




def _payload_uses_res4lyf(payload: dict) -> bool:
    return _res4lyf_sampler_engine(payload) == 'clownshark' or _is_res4lyf_sampler(payload.get('sampler') or payload.get('sampler_name'))

def _build_res4lyf_core_fallback_payload(payload: dict) -> dict:
    fallback = dict(payload or {})
    fallback['res4lyf_sampler_engine'] = 'core'
    fallback['res4lyf_advanced_lane_requested'] = False
    fallback.pop('res4lyf_advanced_options', None)
    fallback.pop('res4lyf_options', None)
    fallback['sampler'] = 'euler'
    fallback['sampler_name'] = 'euler'
    fallback['scheduler'] = 'normal'
    fallback['requires_extensions'] = [item for item in (fallback.get('requires_extensions') or []) if str(item).strip().lower() != 'res4lyf']
    fallback['res4lyf_fallback_applied'] = True
    return fallback


_APPEARANCE_LOCK_ALLOWED_MODES = {'off', 'none', 'disabled', 'hair_focus_soft', 'hair_focus_strong'}
_APPEARANCE_LOCK_DEFAULTS = {
    'enabled': False,
    'mode': 'hair_focus_soft',
    'gain': 0.35,
    'height': 0.34,
    'feather': 18,
}

_APPEARANCE_LOCK_MODE_LABELS = {
    'hair_focus_soft': 'Appearance Focus Soft',
    'hair_focus_strong': 'Appearance Focus Strong',
    'off': 'Off',
}
_APPEARANCE_LOCK_SUPPORTED_GENERATION_MODES = {'txt2img', 'img2img', 'inpaint'}



def _coerce_optional_bool(value, default=None):
    if value is None:
        return default
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {'1', 'true', 'yes', 'on', 'enabled'}:
            return True
        if raw in {'0', 'false', 'no', 'off', 'disabled', 'none'}:
            return False
        return default
    return bool(value)


def _coerce_float_range(value, default: float, min_value: float, max_value: float) -> tuple[float, bool]:
    try:
        parsed = float(value)
    except Exception:
        return float(default), value is not None
    clamped = max(min_value, min(max_value, parsed))
    return float(clamped), clamped != parsed


def _coerce_int_range(value, default: int, min_value: int, max_value: int) -> tuple[int, bool]:
    try:
        parsed = int(float(value))
    except Exception:
        return int(default), value is not None
    clamped = max(min_value, min(max_value, parsed))
    return int(clamped), clamped != parsed


def _normalize_scene_director_appearance_lock_payload(payload: dict) -> list[str]:
    """Normalize Appearance Lock payload keys before node selection.

    This is Phase 2 payload work only: it makes raw/effective state explicit and
    keeps V053 selection driven by visible payload keys. It does not enable UI
    controls and does not inject negatives or mutate scene_json traits.
    """
    notes: list[str] = []
    if not isinstance(payload, dict):
        return notes

    raw = {
        'enabled': payload.get('scene_director_appearance_lock_enabled'),
        'mode': payload.get('scene_director_appearance_lock_mode'),
        'gain': payload.get('scene_director_appearance_lock_gain'),
        'height': payload.get('scene_director_appearance_lock_height'),
        'feather': payload.get('scene_director_appearance_lock_feather'),
    }

    # Backward-compatible aliases are accepted for direct API/workflow tests, but
    # the canonical Scene Director payload keys are always written back below.
    if raw['mode'] is None and payload.get('appearance_lock_mode') is not None:
        raw['mode'] = payload.get('appearance_lock_mode')
    if raw['gain'] is None and payload.get('appearance_lock_gain') is not None:
        raw['gain'] = payload.get('appearance_lock_gain')
    if raw['height'] is None and payload.get('appearance_lock_height') is not None:
        raw['height'] = payload.get('appearance_lock_height')
    if raw['feather'] is None and payload.get('appearance_lock_feather') is not None:
        raw['feather'] = payload.get('appearance_lock_feather')

    scene_director_enabled = _coerce_optional_bool(payload.get('scene_director_enabled'), default=False)
    workflow_mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')

    explicit_enabled = _coerce_optional_bool(raw.get('enabled'), default=None)
    raw_mode = str(raw.get('mode') or '').strip().lower()
    if not raw_mode:
        raw_mode = _APPEARANCE_LOCK_DEFAULTS['mode']
    mode = raw_mode
    if mode not in _APPEARANCE_LOCK_ALLOWED_MODES:
        notes.append(f"Scene Director Appearance Lock mode '{raw_mode}' is not supported; using Appearance Focus Soft.")
        mode = 'hair_focus_soft'

    mode_disables = mode in {'off', 'none', 'disabled'}
    enabled = bool(explicit_enabled) if explicit_enabled is not None else False
    if mode_disables:
        enabled = False
        mode = 'off'

    guardrails: list[dict[str, str]] = []
    if enabled and not scene_director_enabled:
        enabled = False
        guardrails.append({
            'code': 'appearance_lock_disabled_without_scene_director',
            'action': 'auto_fixed',
            'message': 'Appearance Lock was turned off because Scene Director is disabled.',
        })
        notes.append('Appearance Lock was turned off because Scene Director is disabled.')
    if enabled and workflow_mode not in _APPEARANCE_LOCK_SUPPORTED_GENERATION_MODES:
        enabled = False
        guardrails.append({
            'code': 'appearance_lock_unsupported_generation_mode',
            'action': 'auto_fixed',
            'message': f'Appearance Lock is only supported for txt2img, img2img, and inpaint. It was disabled for {workflow_mode}.',
        })
        notes.append(f'Appearance Lock is only supported for txt2img, img2img, and inpaint. It was disabled for {workflow_mode}.')

    gain, gain_clamped = _coerce_float_range(raw.get('gain'), _APPEARANCE_LOCK_DEFAULTS['gain'], 0.0, 1.0)
    height, height_clamped = _coerce_float_range(raw.get('height'), _APPEARANCE_LOCK_DEFAULTS['height'], 0.05, 0.80)
    feather, feather_clamped = _coerce_int_range(raw.get('feather'), _APPEARANCE_LOCK_DEFAULTS['feather'], 0, 128)
    if gain_clamped:
        notes.append('Scene Director Appearance Lock gain was clamped to the supported 0.0–1.0 range.')
    if height_clamped:
        notes.append('Scene Director Appearance Lock height was clamped to the supported 0.05–0.80 range.')
    if feather_clamped:
        notes.append('Scene Director Appearance Lock feather was clamped to the supported 0–128 px range.')

    if gain_clamped:
        guardrails.append({'code': 'appearance_lock_gain_clamped', 'action': 'auto_fixed', 'message': 'Gain was clamped to 0.0–1.0.'})
    if height_clamped:
        guardrails.append({'code': 'appearance_lock_height_clamped', 'action': 'auto_fixed', 'message': 'Height focus was clamped to 0.05–0.80.'})
    if feather_clamped:
        guardrails.append({'code': 'appearance_lock_feather_clamped', 'action': 'auto_fixed', 'message': 'Feather was clamped to 0–128 px.'})

    effective = {
        'enabled': enabled,
        'mode': mode,
        'mode_label': _APPEARANCE_LOCK_MODE_LABELS.get(mode, mode),
        'gain': gain,
        'height': height,
        'feather': feather,
        'node_required': 'NeoSceneDirectorV053' if enabled else 'NeoSceneDirectorV052',
        'source': 'scene_director_payload',
        'workflow_mode': workflow_mode,
        'guardrails': guardrails,
    }
    payload['_neo_scene_director_appearance_lock_raw'] = raw
    payload['_neo_scene_director_appearance_lock_effective'] = effective
    payload['_neo_scene_director_appearance_lock_payload_policy'] = {
        'canonical_keys': [
            'scene_director_appearance_lock_enabled',
            'scene_director_appearance_lock_mode',
            'scene_director_appearance_lock_gain',
            'scene_director_appearance_lock_height',
            'scene_director_appearance_lock_feather',
        ],
        'raw_vs_effective_recorded': True,
        'hidden_negative_injection': False,
        'guardrails': guardrails,
    }

    # Canonical flat mirrors consumed by the workflow builder and sidecar. These
    # are effective values, not raw UI values; raw values remain preserved above.
    payload['scene_director_appearance_lock_enabled'] = enabled
    payload['scene_director_appearance_lock_mode'] = mode
    payload['scene_director_appearance_lock_gain'] = gain
    payload['scene_director_appearance_lock_height'] = height
    payload['scene_director_appearance_lock_feather'] = feather
    return notes


async def _comfy_node_exists(adapter: ComfyBackendAdapter, node_name: str) -> bool:
    """Return True when ComfyUI object_info exposes a node class.

    Some portable ComfyUI builds return either {node_name: schema} for a single
    probe or the full object_info map. Keep this probe permissive and side-effect
    free; ComfyUI remains the final runtime validator.
    """
    try:
        info = await adapter.get_object_info(node_name)
    except Exception:
        return False
    if not isinstance(info, dict):
        return False
    if node_name in info:
        return True
    if 'input' in info or 'output' in info:
        return True
    wanted = node_name.strip().lower()
    return any(str(key).strip().lower() == wanted for key in info.keys())


def _scene_director_appearance_lock_requested(payload: dict) -> bool:
    effective = payload.get('_neo_scene_director_appearance_lock_effective')
    if isinstance(effective, dict):
        return bool(effective.get('enabled'))
    enabled = _coerce_optional_bool(payload.get('scene_director_appearance_lock_enabled'), default=False)
    return bool(enabled)


async def _configure_scene_director_node_selection(adapter: ComfyBackendAdapter, payload: dict) -> list[str]:
    """Select NeoSceneDirectorV053 only when Appearance Lock is explicitly active.

    V052 remains the stable default. If V053 is requested but unavailable, this
    falls back to V052 and records a visible compile note + payload warning.
    """
    notes: list[str] = []
    if not bool(payload.get('scene_director_enabled')):
        return notes
    backend_mode = str(payload.get('scene_director_backend_mode') or payload.get('regional_backend_mode') or '').strip().lower()
    if backend_mode and backend_mode not in {'v052_node', 'v053_node', 'scene_director_node'}:
        payload['scene_director_backend_mode'] = 'v052_node'
        payload['_neo_scene_director_backend_mode_warning'] = f"Unsupported Scene Director backend mode '{backend_mode}' was reset to V052."
        notes.append(payload['_neo_scene_director_backend_mode_warning'])
    if not str(payload.get('scene_director_v052_scene_json') or '').strip():
        if _scene_director_appearance_lock_requested(payload):
            payload['_neo_scene_director_appearance_lock_active'] = False
            payload['_neo_scene_director_appearance_lock_warning'] = 'Appearance Lock requires Scene Director regions/scene JSON. Add at least one Scene Director region first.'
            notes.append(payload['_neo_scene_director_appearance_lock_warning'])
        return notes
    wants_v053 = _scene_director_appearance_lock_requested(payload)
    if not wants_v053:
        payload.setdefault('scene_director_backend_mode', 'v052_node')
        payload['_neo_scene_director_node_class'] = 'NeoSceneDirectorV052'
        payload['_neo_scene_director_node_selection'] = 'v052_default'
        payload['_neo_scene_director_appearance_lock_active'] = False
        return notes

    v053_ok = await _comfy_node_exists(adapter, 'NeoSceneDirectorV053')
    if v053_ok:
        payload['scene_director_backend_mode'] = 'v053_node'
        payload['_neo_scene_director_node_class'] = 'NeoSceneDirectorV053'
        payload['_neo_scene_director_node_selection'] = 'v053_appearance_lock'
        payload['_neo_scene_director_appearance_lock_active'] = True
        notes.append('Scene Director Appearance Lock requested: using NeoSceneDirectorV053.')
        return notes

    payload['scene_director_backend_mode'] = 'v052_node'
    payload['_neo_scene_director_node_class'] = 'NeoSceneDirectorV052'
    payload['_neo_scene_director_node_selection'] = 'v053_missing_fallback_v052'
    payload['_neo_scene_director_appearance_lock_active'] = False
    payload['_neo_scene_director_appearance_lock_warning'] = 'Appearance Lock requires NeoSceneDirectorV053. Falling back to NeoSceneDirectorV052.'
    notes.append(payload['_neo_scene_director_appearance_lock_warning'])
    return notes


def _finalize_scene_director_appearance_lock_state_metadata(payload: dict) -> dict:
    """Record raw/effective Appearance Lock state after node selection/build.

    Phase 5 save/metadata contract: keep raw UI intent, normalized effective
    values, selected node, fallback status, and guardrail policy together so a
    saved output can be audited without re-running the workflow builder.
    """
    if not isinstance(payload, dict):
        return {}
    raw = payload.get('_neo_scene_director_appearance_lock_raw')
    if not isinstance(raw, dict):
        raw = {
            'enabled': payload.get('scene_director_appearance_lock_enabled'),
            'mode': payload.get('scene_director_appearance_lock_mode'),
            'gain': payload.get('scene_director_appearance_lock_gain'),
            'height': payload.get('scene_director_appearance_lock_height'),
            'feather': payload.get('scene_director_appearance_lock_feather'),
        }
    effective = payload.get('_neo_scene_director_appearance_lock_effective')
    if not isinstance(effective, dict):
        effective = {
            'enabled': bool(payload.get('scene_director_appearance_lock_enabled')),
            'mode': str(payload.get('scene_director_appearance_lock_mode') or 'hair_focus_soft'),
            'gain': payload.get('scene_director_appearance_lock_gain', 0.35),
            'height': payload.get('scene_director_appearance_lock_height', 0.34),
            'feather': payload.get('scene_director_appearance_lock_feather', 18),
            'source': 'scene_director_payload',
        }
    node_class = str(payload.get('_neo_scene_director_node_class') or '').strip()
    node_selection = str(payload.get('_neo_scene_director_node_selection') or '').strip()
    version_used = str(payload.get('_neo_scene_director_version_used') or '').strip()
    requested_enabled = bool(effective.get('enabled'))
    active = bool(payload.get('_neo_scene_director_appearance_lock_active'))
    fallback_warning = str(payload.get('_neo_scene_director_appearance_lock_warning') or '').strip()
    metadata = {
        'schema_version': 1,
        'feature': 'scene_director_appearance_lock',
        'raw_state': raw,
        'effective_state': {
            **effective,
            'active': active,
            'node_class': node_class,
            'node_selection': node_selection,
            'version_used': version_used,
            'fallback_applied': bool(requested_enabled and not active),
            'warning': fallback_warning,
        },
        'policy': {
            'source': 'scene_director_live_generation_payload',
            'output_policy': 'generation_output_metadata_only',
            'batch_behavior': str(payload.get('_neo_scene_director_batch_policy') or 'preserve_user_batch_unless_guarded_elsewhere'),
            'context_usage': 'appearance/head/hair/color conditioning inside Scene Director regions',
            'hidden_negative_injection': False,
            'raw_vs_effective_recorded': True,
            'guardrails': effective.get('guardrails') if isinstance(effective, dict) else [],
        },
    }
    payload['_neo_scene_director_appearance_lock_state_metadata'] = metadata
    payload['_neo_scene_director_appearance_lock_fallback_applied'] = bool(metadata['effective_state']['fallback_applied'])
    return metadata

async def _build_res4lyf_core_fallback_workflow(payload: dict, reason: Exception | str) -> tuple[dict, dict, list[str]]:
    fallback_payload = _build_res4lyf_core_fallback_payload(payload)
    fallback_workflow, fallback_normalized, fallback_notes = build_image_workflow(fallback_payload, command=detect_image_workflow_command(fallback_payload))
    note = f"RES4LYF fallback applied: {reason}. Rebuilt with Core KSampler / euler / normal."
    fallback_notes = [note, *list(fallback_notes or [])]
    return fallback_workflow, fallback_normalized, fallback_notes

async def _validate_generation_runtime_compatibility(adapter: ComfyBackendAdapter, payload: dict) -> list[str]:
    notes: list[str] = []
    family = str(payload.get('family') or '').strip().lower()
    mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')
    inpaint_backend = normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard')

    if family == 'sdxl_sd':
        inpaint_payload = get_shared_inpaint_payload(payload)
        source_images = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
        mask_row = (inpaint_payload.get('mask') or {}) if isinstance(inpaint_payload, dict) else {}
        outpaint_row = (inpaint_payload.get('outpaint') or {}) if isinstance(inpaint_payload, dict) else {}
        base_image_name = str(source_images.get('base_image_name') or payload.get('source_image_name') or '').strip()
        mask_image_name = str(mask_row.get('mask_image_name') or payload.get('mask_image_name') or '').strip()
        if mode == 'inpaint':
            if not base_image_name:
                raise ValueError('SDXL inpaint needs a source image first. Upload the base image before queueing.')
            if not mask_image_name:
                raise ValueError('SDXL inpaint needs a mask image. Paint the mask area first, then queue again.')
            context = str(payload.get('inpaint_context') or 'full_image').strip().lower() or 'full_image'
            target = str(payload.get('inpaint_target') or 'masked').strip().lower() or 'masked'
            grow_mask_by = mask_row.get('grow_mask_by') if isinstance(mask_row, dict) else None
            if grow_mask_by in (None, ''):
                grow_mask_by = payload.get('grow_mask_by') or 6
            if inpaint_backend == 'lanpaint':
                notes.append(f'SDXL validation: LanPaint inpaint is using the {context.replace("_", " ")} context on the {target.replace("_", " ")} region.')
            else:
                notes.append(f'SDXL validation: standard inpaint is using the {context.replace("_", " ")} context on the {target.replace("_", " ")} region.')
            notes.append(f'SDXL validation: grow_mask_by {int(grow_mask_by)} will be used when masked-focus encoding is selected.')
        elif mode == 'outpaint':
            if not base_image_name:
                raise ValueError('SDXL outpaint needs a source image first. Upload the base image before queueing.')
            left = int(outpaint_row.get('left') if outpaint_row.get('left') is not None else payload.get('outpaint_left') or 0)
            top = int(outpaint_row.get('top') if outpaint_row.get('top') is not None else payload.get('outpaint_top') or 0)
            right = int(outpaint_row.get('right') if outpaint_row.get('right') is not None else payload.get('outpaint_right') or 0)
            bottom = int(outpaint_row.get('bottom') if outpaint_row.get('bottom') is not None else payload.get('outpaint_bottom') or 0)
            if left + top + right + bottom <= 0:
                raise ValueError('SDXL outpaint needs padding on at least one side before queueing.')
            notes.append(f'SDXL validation: standard outpaint padding is left {left}, top {top}, right {right}, bottom {bottom}.')
        if not (mode == 'inpaint' and inpaint_backend == 'lanpaint'):
            return notes

    if family != 'qwen_image_edit' and not (family == 'sdxl_sd' and mode == 'inpaint' and inpaint_backend == 'lanpaint'):
        return notes
    if mode != 'inpaint':
        return notes

    inpaint_payload = get_shared_inpaint_payload(payload)
    source_images = (inpaint_payload.get('source_images') or {}) if isinstance(inpaint_payload, dict) else {}
    composition = (inpaint_payload.get('composition') or {}) if isinstance(inpaint_payload, dict) else {}
    mask_row = (inpaint_payload.get('mask') or {}) if isinstance(inpaint_payload, dict) else {}

    base_image_name = str(source_images.get('base_image_name') or payload.get('source_image_name') or '').strip()
    reference_image_2_name = str(source_images.get('reference_image_2_name') or payload.get('source_image__2_name') or '').strip()
    composition_image_name = str(source_images.get('composition_image_name') or payload.get('source_image__3_name') or '').strip()
    composition_source_mode = str(composition.get('source_mode') or payload.get('composition_source_mode') or 'source_image').strip().lower()
    composition_guide_type = str(composition.get('guide_type') or payload.get('composition_guide_type') or 'none').strip().lower()
    mask_image_name = str(mask_row.get('mask_image_name') or payload.get('mask_image_name') or '').strip()

    if not base_image_name:
        raise ValueError(('Qwen' if family == 'qwen_image_edit' else 'SDXL') + ' inpaint needs image1 first. Upload the base source image before queueing.')
    if not mask_image_name:
        raise ValueError(('Qwen' if family == 'qwen_image_edit' else 'SDXL') + ' inpaint needs a mask image. Paint the mask area first, then queue again.')

    if family == 'sdxl_sd' and inpaint_backend == 'lanpaint':
        lanpaint_info = await adapter.get_object_info('LanPaint_KSampler')
        if isinstance(lanpaint_info, dict) and 'LanPaint_KSampler' in lanpaint_info:
            lanpaint_info = lanpaint_info.get('LanPaint_KSampler')
        required = _object_required_inputs(lanpaint_info if isinstance(lanpaint_info, dict) else {})
        all_inputs = _object_all_inputs(lanpaint_info if isinstance(lanpaint_info, dict) else {})
        if all_inputs:
            payload['_neo_lanpaint_supported_inputs'] = sorted(str(key) for key in all_inputs.keys())
        allowed_samplers = _extract_required_combo_values(required.get('sampler_name'))
        allowed_schedulers = _extract_required_combo_values(required.get('scheduler'))
        chosen_sampler = str(payload.get('sampler') or 'euler').strip() or 'euler'
        chosen_scheduler = str(payload.get('scheduler') or 'simple').strip() or 'simple'
        if allowed_samplers and chosen_sampler not in allowed_samplers:
            preview = ', '.join(allowed_samplers[:6])
            suffix = '…' if len(allowed_samplers) > 6 else ''
            raise ValueError(f"LanPaint sampler mismatch: '{chosen_sampler}' is not compatible with this LanPaint_KSampler route. Change Sampling Method to a compatible option: {preview}{suffix}. Recommended realistic SDXL default: heun / normal.")
        if allowed_schedulers and chosen_scheduler not in allowed_schedulers:
            preview = ', '.join(allowed_schedulers[:6])
            suffix = '…' if len(allowed_schedulers) > 6 else ''
            raise ValueError(f"LanPaint scheduler mismatch: '{chosen_scheduler}' is not compatible with this LanPaint_KSampler route. Change Scheduler to a compatible option: {preview}{suffix}. Recommended realistic SDXL default: heun / normal.")
        notes.append('SDXL validation: LanPaint sampler pair passed live node schema compatibility.')
        return notes
    if composition_source_mode == 'composition_image' and not composition_image_name:
        raise ValueError('Composition source is set to image3, but no composition image is loaded. Add image3 or switch the source back to image1.')
    if composition_guide_type in {'depth', 'pose'} and composition_source_mode == 'composition_image' and not composition_image_name:
        raise ValueError(f'Composition guide {composition_guide_type} needs image3 because the source is set to the dedicated composition image.')

    if reference_image_2_name:
        notes.append('Qwen validation: image2 reference is loaded for the inpaint pass.')
    if composition_image_name:
        notes.append(f'Qwen validation: image3 is loaded and composition source is set to {composition_source_mode.replace("_", " ")}.')
    elif composition_source_mode == 'source_image':
        notes.append('Qwen validation: image3 is falling back to image1 because no dedicated composition image is loaded.')

    if inpaint_backend == 'lanpaint':
        lanpaint_info = await adapter.get_object_info('LanPaint_KSampler')
        if isinstance(lanpaint_info, dict) and 'LanPaint_KSampler' in lanpaint_info:
            lanpaint_info = lanpaint_info.get('LanPaint_KSampler')
        required = _object_required_inputs(lanpaint_info if isinstance(lanpaint_info, dict) else {})
        all_inputs = _object_all_inputs(lanpaint_info if isinstance(lanpaint_info, dict) else {})
        if all_inputs:
            payload['_neo_lanpaint_supported_inputs'] = sorted(str(key) for key in all_inputs.keys())
        allowed_samplers = _extract_required_combo_values(required.get('sampler_name'))
        allowed_schedulers = _extract_required_combo_values(required.get('scheduler'))
        chosen_sampler = str(payload.get('sampler') or 'euler').strip() or 'euler'
        chosen_scheduler = str(payload.get('scheduler') or 'simple').strip() or 'simple'
        if allowed_samplers and chosen_sampler not in allowed_samplers:
            preview = ', '.join(allowed_samplers[:6])
            suffix = '…' if len(allowed_samplers) > 6 else ''
            raise ValueError(f"LanPaint sampler mismatch: '{chosen_sampler}' is not compatible with this LanPaint_KSampler route. Change Sampling Method to a compatible option: {preview}{suffix}. Recommended realistic SDXL default: heun / normal.")
        if allowed_schedulers and chosen_scheduler not in allowed_schedulers:
            preview = ', '.join(allowed_schedulers[:6])
            suffix = '…' if len(allowed_schedulers) > 6 else ''
            raise ValueError(f"LanPaint scheduler mismatch: '{chosen_scheduler}' is not compatible with this LanPaint_KSampler route. Change Scheduler to a compatible option: {preview}{suffix}. Recommended realistic SDXL default: heun / normal.")
        if chosen_sampler == 'euler' and chosen_scheduler == 'simple':
            notes.append(('Qwen' if family == 'qwen_image_edit' else 'SDXL') + ' validation: LanPaint sampler pair passed live node schema compatibility.')

    if composition_guide_type == 'depth':
        depth_class = str(payload.get('composition_depth_node_class') or 'DepthAnythingV2Preprocessor').strip() or 'DepthAnythingV2Preprocessor'
        depth_info = await adapter.get_object_info(depth_class)
        if not (isinstance(depth_info, dict) and ((depth_info.get(depth_class) if depth_class in depth_info else depth_info))):
            raise ValueError(f'Composition guide mismatch: Neo could not find the selected depth preprocessor ({depth_class}) on this backend.')
        notes.append(f'Qwen validation: depth composition guide will use {depth_class}.')
    elif composition_guide_type == 'pose':
        pose_class = str(payload.get('composition_pose_node_class') or 'DWPreprocessor').strip() or 'DWPreprocessor'
        pose_info = await adapter.get_object_info(pose_class)
        if not (isinstance(pose_info, dict) and ((pose_info.get(pose_class) if pose_class in pose_info else pose_info))):
            raise ValueError(f'Composition guide mismatch: Neo could not find the selected pose preprocessor ({pose_class}) on this backend.')
        notes.append(f'Qwen validation: pose composition guide will use {pose_class}.')

    return notes


def _output_settings_response(settings: dict | None = None) -> dict:
    settings = settings or load_generation_output_settings()
    output_root = str(settings.get('output_root') or DEFAULT_OUTPUT_ROOT)
    selected_category = category_display_name(str(settings.get('selected_category') or 'Uncategorized'))
    save_dir = str(Path(output_root) / selected_category)
    slug = category_slug(selected_category)
    padding = max(2, min(8, int(settings.get('filename_padding') or 4)))
    try:
        next_index = next_category_index(Path(save_dir), slug)
    except Exception:
        next_index = 1
    return {
        'output_root': output_root,
        'categories': list(settings.get('categories') or ['Uncategorized']),
        'selected_category': selected_category,
        'filename_padding': padding,
        'save_directory': save_dir,
        'next_index': next_index,
        'filename_example': f"{slug}_{str(next_index).zfill(padding)}_[seed].png",
    }


def _mode_output_dir_name(mode: str) -> str:
    return _MODE_OUTPUT_DIRS.get(str(mode or '').strip().lower(), 'generated-images')


def _source_output_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get('filename') or ''),
        str(item.get('subfolder') or ''),
        str(item.get('type') or 'output'),
    )


def _guess_output_suffix(item: dict) -> str:
    suffix = Path(str(item.get('filename') or '')).suffix.lower()
    if suffix in _OUTPUT_IMAGE_EXTS:
        return suffix
    return '.png'


def _output_metadata_root_for_mode(mode_name: str) -> Path:
    root = get_library_root() / 'output_metadata' / (str(mode_name or 'txt2img').strip().lower() or 'txt2img')
    root.mkdir(parents=True, exist_ok=True)
    return root


def _mode_relative_name(mode_root: Path, candidate_path: Path) -> str:
    try:
        rel = candidate_path.resolve().relative_to(mode_root.resolve())
    except Exception:
        rel = Path(candidate_path.name)
    return str(rel).replace('\\', '/')


def _extract_node_input_keys(node_info) -> list[str]:
    if isinstance(node_info, dict) and len(node_info) == 1:
        only_value = next(iter(node_info.values()))
        if isinstance(only_value, dict) and 'input' in only_value:
            node_info = only_value
    if not isinstance(node_info, dict):
        return []
    input_block = node_info.get('input') or {}
    if not isinstance(input_block, dict):
        return []
    keys: list[str] = []
    for section_name in ('required', 'optional'):
        section = input_block.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        for key in section.keys():
            key_text = str(key or '').strip()
            if key_text and key_text not in keys:
                keys.append(key_text)
    return keys


async def _inject_refine_ultimate_runtime_hints(adapter: ComfyBackendAdapter, payload: dict) -> list[str]:
    notes: list[str] = []
    refine_enabled = bool(payload.get('refine_enabled'))
    refine_mode = str(payload.get('refine_mode') or '').strip().lower()
    if not (refine_enabled and refine_mode == 'image_upscale'):
        return notes

    upscale_model_name = str(payload.get('refine_upscaler') or '').strip()
    if not upscale_model_name:
        notes.append('Upscale Lab image mode is active without an upscaler model, so Neo will use the fallback image-upscale refine path instead of Ultimate SD Upscale.')
        return notes

    try:
        ultimate_info = await adapter.get_object_info('UltimateSDUpscale')
        input_keys = _extract_node_input_keys(ultimate_info)
        if input_keys:
            payload['_neo_refine_use_ultimate_upscale'] = True
            payload['_neo_ultimate_input_keys'] = input_keys
            notes.append('Upscale Lab preserve mode will compile through Ultimate SD Upscale.')
        else:
            notes.append('Ultimate SD Upscale node was not available on this backend, so Neo will use the fallback image-upscale refine path.')
            return notes
    except Exception as exc:
        notes.append(f'Ultimate SD Upscale validation failed, so Neo will use the fallback image-upscale refine path ({exc}).')
        return notes

    try:
        catalog = await adapter.get_catalog()
    except Exception:
        catalog = {}
    controlnet_list = catalog.get('controlnet') if isinstance(catalog, dict) else []
    if isinstance(controlnet_list, list):
        try:
            controlnet_loader = await adapter.get_object_info('ControlNetLoader')
            controlnet_apply = await adapter.get_object_info('ControlNetApply')
            controlnet_ready = bool(_extract_node_input_keys(controlnet_loader) and _extract_node_input_keys(controlnet_apply))
        except Exception:
            controlnet_ready = False
        tile_model = next((str(name).strip() for name in controlnet_list if 'tile' in str(name).lower()), '') if controlnet_ready else ''
        if tile_model:
            payload['_neo_refine_tile_controlnet_model'] = tile_model
            notes.append(f'Upscale Lab preserve mode will use tile ControlNet guidance: {tile_model}.')
        elif controlnet_ready:
            notes.append('No tile ControlNet model was found in the backend catalog, so Ultimate SD Upscale will run without tile guidance.')
        else:
            notes.append('ControlNet apply nodes are not ready on this backend, so Ultimate SD Upscale will run without tile guidance.')
    return notes


def _build_generation_sidecar(job: dict, payload: dict, source: dict, candidate_path: Path, mode_root: Path, mode_name: str, category: str, slug: str, next_index: int) -> tuple[dict, Path]:
    relative_name = _mode_relative_name(mode_root, candidate_path)
    sidecar_path = (_output_metadata_root_for_mode(mode_name) / Path(relative_name)).with_suffix('.json')
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)

    width = str(payload.get('width') or '').strip()
    height = str(payload.get('height') or '').strip()
    size_value = f"{width}x{height}" if width and height else ''

    control_units = list(payload.get('controlnet_units') or []) if isinstance(payload.get('controlnet_units'), list) else []
    ipadapter_units = list(payload.get('ipadapter_units') or []) if isinstance(payload.get('ipadapter_units'), list) else []
    lora_units = list(payload.get('loras') or []) if isinstance(payload.get('loras'), list) else []
    if not lora_units and str(payload.get('lora_name') or '').strip():
        lora_units = [{
            'name': str(payload.get('lora_name') or '').strip(),
            'strength': payload.get('lora_strength') if payload.get('lora_strength') is not None else 0.8,
        }]

    generation_summary = {
        'Checkpoint': str(payload.get('checkpoint') or '').strip(),
        'Seed': payload.get('seed') if payload.get('seed') is not None else '',
        'Steps': payload.get('steps') if payload.get('steps') is not None else '',
        'CFG scale': payload.get('cfg') if payload.get('cfg') is not None else '',
        'Sampler': str(payload.get('sampler') or '').strip(),
        'Scheduler': str(payload.get('scheduler') or '').strip(),
        'Size': size_value,
        'Denoising strength': payload.get('denoise') if payload.get('denoise') is not None else '',
        'VAE': str(payload.get('vae') or '').strip(),
        'Batch size': payload.get('batch_size') if payload.get('batch_size') is not None else '',
        'Mode': str(payload.get('mode') or '').strip(),
    }

    extra_generation_params = {
        'refine_enabled': bool(payload.get('refine_enabled')),
        'refine_strategy': str(payload.get('refine_strategy') or '').strip(),
        'refine_mode': str(payload.get('refine_mode') or '').strip(),
        'refine_resize_method': str(payload.get('refine_resize_method') or '').strip(),
        'refine_scale': payload.get('refine_scale') if payload.get('refine_scale') is not None else '',
        'refine_steps': payload.get('refine_steps') if payload.get('refine_steps') is not None else '',
        'refine_denoise': payload.get('refine_denoise') if payload.get('refine_denoise') is not None else '',
        'refine_cfg': payload.get('refine_cfg') if payload.get('refine_cfg') is not None else '',
        'refine_sampler': str(payload.get('refine_sampler') or '').strip(),
        'refine_scheduler': str(payload.get('refine_scheduler') or '').strip(),
        'refine_tiled_vae': payload.get('refine_tiled_vae') if payload.get('refine_tiled_vae') is not None else '',
        'refine_tile_size': payload.get('refine_tile_size') if payload.get('refine_tile_size') is not None else '',
        'refine_tile_overlap': payload.get('refine_tile_overlap') if payload.get('refine_tile_overlap') is not None else '',
        'refine_upscaler': str(payload.get('refine_upscaler') or '').strip(),
        'supir_enabled': bool(payload.get('supir_enabled')),
        'supir_model': str(payload.get('supir_model') or '').strip(),
        'supir_sdxl_model': str(payload.get('supir_sdxl_model') or '').strip(),
        'supir_scale': payload.get('supir_scale') if payload.get('supir_scale') is not None else '',
        'supir_steps': payload.get('supir_steps') if payload.get('supir_steps') is not None else '',
        'supir_restoration_scale': payload.get('supir_restoration_scale') if payload.get('supir_restoration_scale') is not None else '',
        'supir_cfg_scale': payload.get('supir_cfg_scale') if payload.get('supir_cfg_scale') is not None else '',
        'supir_control_scale': payload.get('supir_control_scale') if payload.get('supir_control_scale') is not None else '',
        'supir_color_fix_type': str(payload.get('supir_color_fix_type') or '').strip(),
        'inpaint_target': str(payload.get('inpaint_target') or '').strip(),
        'inpaint_context': str(payload.get('inpaint_context') or '').strip(),
        'grow_mask_by': payload.get('grow_mask_by') if payload.get('grow_mask_by') is not None else '',
        'mask_feather': payload.get('mask_feather') if payload.get('mask_feather') is not None else '',
        'outpaint_left': payload.get('outpaint_left') if payload.get('outpaint_left') is not None else '',
        'outpaint_top': payload.get('outpaint_top') if payload.get('outpaint_top') is not None else '',
        'outpaint_right': payload.get('outpaint_right') if payload.get('outpaint_right') is not None else '',
        'outpaint_bottom': payload.get('outpaint_bottom') if payload.get('outpaint_bottom') is not None else '',
        'outpaint_feather': payload.get('outpaint_feather') if payload.get('outpaint_feather') is not None else '',
        'style_positive': str(payload.get('style_positive') or '').strip(),
        'style_negative': str(payload.get('style_negative') or '').strip(),
        'scene_director_version_used': str(payload.get('_neo_scene_director_version_used') or '').strip(),
        'scene_director_node_class': str(payload.get('_neo_scene_director_node_class') or '').strip(),
        'scene_director_node_selection': str(payload.get('_neo_scene_director_node_selection') or '').strip(),
        'scene_director_appearance_lock_raw': payload.get('_neo_scene_director_appearance_lock_raw') if isinstance(payload.get('_neo_scene_director_appearance_lock_raw'), dict) else {},
        'scene_director_appearance_lock_effective': payload.get('_neo_scene_director_appearance_lock_effective') if isinstance(payload.get('_neo_scene_director_appearance_lock_effective'), dict) else {},
        'scene_director_appearance_lock_state': payload.get('_neo_scene_director_appearance_lock_state_metadata') if isinstance(payload.get('_neo_scene_director_appearance_lock_state_metadata'), dict) else {},
        'scene_director_appearance_lock_fallback_applied': bool(payload.get('_neo_scene_director_appearance_lock_fallback_applied')),
        'scene_director_appearance_lock_warning': str(payload.get('_neo_scene_director_appearance_lock_warning') or '').strip(),
        'loras': lora_units,
        'textual_inversions': list(payload.get('textual_inversions') or []) if isinstance(payload.get('textual_inversions'), list) else [],
        'ipadapter_units': ipadapter_units,
    }
    external_extension_metadata = build_external_extension_output_metadata_shell(payload)
    extra_generation_params['external_extensions'] = external_extension_metadata
    extra_generation_params = {k: v for k, v in extra_generation_params.items() if v not in ('', None, [], {})}

    raw_lines = []
    if str(payload.get('positive') or '').strip():
        raw_lines.append(str(payload.get('positive') or '').strip())
    if str(payload.get('negative') or '').strip():
        raw_lines.append(f"Negative prompt: {str(payload.get('negative') or '').strip()}")
    settings_parts = []
    for key in ('Steps', 'Sampler', 'Scheduler', 'CFG scale', 'Seed', 'Size', 'Checkpoint', 'VAE', 'Denoising strength', 'Batch size', 'Mode'):
        value = generation_summary.get(key)
        if value not in ('', None):
            label = 'Model' if key == 'Checkpoint' else key
            settings_parts.append(f"{label}: {value}")
    if settings_parts:
        raw_lines.append(', '.join(settings_parts))

    output_id = f"out_{str(job.get('id') or '').strip() or 'job'}_{str(next_index).zfill(4)}"
    base_sidecar = {
        'schema_version': 2,
        'saved_from_job_id': job.get('id') or '',
        'saved_at': job.get('updated_at') or job.get('created_at') or '',
        'main': {
            'positive_box': str(payload.get('positive') or '').strip(),
            'negative_box': str(payload.get('negative') or '').strip(),
        },
        'generation': generation_summary,
        'controlnet': {
            'units': control_units,
        },
        'ipadapter': {
            'units': ipadapter_units,
        },
        'extra_generation_params': extra_generation_params,
        'scene_director': {
            'version_used': str(payload.get('_neo_scene_director_version_used') or '').strip(),
            'node_class': str(payload.get('_neo_scene_director_node_class') or '').strip(),
            'node_selection': str(payload.get('_neo_scene_director_node_selection') or '').strip(),
            'appearance_lock': payload.get('_neo_scene_director_appearance_lock_state_metadata') if isinstance(payload.get('_neo_scene_director_appearance_lock_state_metadata'), dict) else {},
        },
        'external_extensions': external_extension_metadata,
        '_neo_external_extensions': external_extension_metadata,
        'raw_parameters': '\n'.join([line for line in raw_lines if line]),
        'save': {
            'output_root': str(mode_root.parent),
            'mode_folder': _mode_output_dir_name(mode_name),
            'category': category,
            'category_slug': slug,
            'directory': str(candidate_path.parent),
            'filename': candidate_path.name,
            'relative_name': relative_name,
            'path': str(candidate_path),
            'index': next_index,
        },
        'backend': {
            'name': job.get('backend_name') or '',
            'type': job.get('backend_type') or '',
            'base_url': job.get('backend_url') or '',
        },
        'comfy': {
            'prompt_id': job.get('prompt_id') or '',
            'queue_number': job.get('queue_number'),
            'source_output': source,
        },
        'payload': payload,
        'compile_notes': list(job.get('compile_notes') or []),
        'workflow_graph': job.get('workflow_graph') or {},
    }
    sidecar = build_generation_output_sidecar(
        base_sidecar=base_sidecar,
        job=job,
        payload=payload,
        source_output=source,
        candidate_path=str(candidate_path),
        relative_name=relative_name,
        output_id=output_id,
        category=category,
        category_slug=slug,
        mode_name=_mode_output_dir_name(mode_name),
        next_index=next_index,
    )
    return sidecar, sidecar_path


def _build_local_generation_output_url(filename: str, subfolder: str = '', file_type: str = 'output') -> str:
    params = {'filename': str(filename or ''), 'file_type': str(file_type or 'output')}
    if subfolder:
        params['subfolder'] = str(subfolder or '')
    return '/api/generation/output-download?' + urlencode(params)


def _build_remote_generation_output_url(adapter: ComfyBackendAdapter | None, filename: str, subfolder: str = '', file_type: str = 'output') -> str:
    if adapter is None:
        return ''
    try:
        return adapter.build_view_url(str(filename or ''), str(subfolder or ''), str(file_type or 'output'))
    except Exception:
        return ''


def _build_download_generation_output_url(adapter: ComfyBackendAdapter | None, filename: str, subfolder: str = '', file_type: str = 'output') -> str:
    # Server-side httpx cannot fetch Neo's relative /api/... URL.
    # For backend map jobs, download directly from ComfyUI /view with a full http(s) URL.
    remote_url = _build_remote_generation_output_url(adapter, filename, subfolder, file_type)
    if remote_url:
        return remote_url
    return _build_local_generation_output_url(filename, subfolder, file_type)


def _normalize_generation_history_outputs(history_entry: dict | None, adapter: ComfyBackendAdapter | None = None) -> list[dict]:
    outputs: list[dict] = []
    for image in _extract_history_images(history_entry):
        filename = str(image.get('filename') or '').strip()
        if not filename:
            continue
        subfolder = str(image.get('subfolder') or '').strip()
        file_type = str(image.get('type') or 'output').strip() or 'output'
        outputs.append({
            'filename': filename,
            'subfolder': subfolder,
            'type': file_type,
            'view_url': _build_local_generation_output_url(filename, subfolder, file_type),
            'remote_view_url': _build_remote_generation_output_url(adapter, filename, subfolder, file_type),
        })
    return outputs


def _history_entry_completed(history_entry: dict | None) -> bool:
    if not isinstance(history_entry, dict):
        return False
    status = history_entry.get('status')
    if isinstance(status, dict):
        return bool(status.get('completed', False))
    return True


async def _download_output_bytes(url: str, timeout_sec: int = 60) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_sec) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def _persist_generation_outputs(job: dict, source_outputs: list[dict], adapter: ComfyBackendAdapter) -> list[dict]:
    if not source_outputs:
        return []

    payload = job.get('payload') or {}
    settings = load_generation_output_settings()
    output_root = str(payload.get('output_root') or settings.get('output_root') or DEFAULT_OUTPUT_ROOT).strip() or str(DEFAULT_OUTPUT_ROOT)
    category = category_display_name(str(payload.get('output_category') or settings.get('selected_category') or 'Uncategorized'))
    try:
        padding = max(2, min(8, int(payload.get('output_filename_padding') or settings.get('filename_padding') or 4)))
    except Exception:
        padding = 4
    mode_name = str(payload.get('save_mode_override') or payload.get('output_mode_override') or payload.get('mode') or job.get('mode') or 'txt2img').strip().lower()
    mode_root = Path(output_root) / _mode_output_dir_name(mode_name)
    category_dir = ensure_category_dir(mode_root, category)
    slug = category_slug(category)
    seed = str(payload.get('seed') or '0').strip() or '0'

    existing_outputs = list(job.get('outputs') or [])
    existing_by_key = {}
    for item in existing_outputs:
        if not isinstance(item, dict):
            continue
        key = _source_output_key(item)
        saved_path_raw = str(item.get('saved_path') or '').strip()
        # Important: Path('') resolves to the current working directory and
        # exists(), which made raw ComfyUI output refs look already persisted.
        # Only treat an output as persisted when it has a real saved_path.
        if key and saved_path_raw and Path(saved_path_raw).exists():
            existing_by_key[key] = item

    next_index = next_category_index(category_dir, slug)
    merged_outputs: list[dict] = []
    for idx, source in enumerate(source_outputs, start=1):
        key = _source_output_key(source)
        if key in existing_by_key:
            merged = dict(source)
            merged.update(existing_by_key[key])
            merged_outputs.append(merged)
            continue

        ext = _guess_output_suffix(source)
        source_url = str(source.get('remote_view_url') or source.get('view_url') or '').strip()
        if source_url.startswith('/api/generation/output-download'):
            source_url = _build_remote_generation_output_url(
                adapter,
                str(source.get('filename') or ''),
                str(source.get('subfolder') or ''),
                str(source.get('type') or 'output'),
            )
        if not source_url:
            raise ValueError('Could not resolve a generation output download URL for persistence.')
        data = await _download_output_bytes(source_url, timeout_sec=max(20, int(adapter.timeout_sec or 30)))
        while True:
            candidate_name = f"{slug}_{str(next_index).zfill(padding)}_{seed}{ext}"
            candidate_path = category_dir / candidate_name
            if not candidate_path.exists():
                break
            next_index += 1
        candidate_path.write_bytes(data)
        sidecar, sidecar_path = _build_generation_sidecar(job, payload, source, candidate_path, mode_root, mode_name, category, slug, next_index)
        atomic_write_json(sidecar_path, sidecar)
        merged_outputs.append({
            **source,
            'schema_version': 1,
            'record_type': 'job_output_ref',
            'job_id': str(job.get('job_id') or job.get('id') or ''),
            'output_id': str(sidecar.get('output_id') or ''),
            'media_type': 'image',
            'status': 'saved',
            'family': infer_generation_family(payload),
            'lineage': sidecar.get('lineage') or {},
            'saved_filename': candidate_name,
            'saved_path': str(candidate_path),
            'save_directory': str(category_dir),
            'mode_folder': _mode_output_dir_name(mode_name),
            'sidecar_path': str(sidecar_path),
            'category': category,
            'category_slug': slug,
        })
        next_index += 1
    return merged_outputs



_FINALIZATION_ACTIVE_STATES = {'queued', 'running', 'processing', 'executing', 'finalizing_output', 'outputs_registered', 'persisting_outputs'}
_FINALIZATION_TERMINAL_STATES = {'completed', 'error', 'failed', 'cancelled'}
_FINALIZATION_MISSING_HISTORY_LIMIT = 8


def _now_unix() -> int:
    try:
        return int(time.time())
    except Exception:
        return 0


def _finalization_meta(job: dict | None) -> dict:
    source = (job or {}).get('finalization') if isinstance((job or {}).get('finalization'), dict) else {}
    return {
        'schema_version': 1,
        'phase': str(source.get('phase') or 'queued'),
        'history_seen': bool(source.get('history_seen', False)),
        'history_completed': bool(source.get('history_completed', False)),
        'outputs_normalized': bool(source.get('outputs_normalized', False)),
        'outputs_persisted': bool(source.get('outputs_persisted', False)),
        'ui_finalized': bool(source.get('ui_finalized', False)),
        'missing_history_checks': int(source.get('missing_history_checks') or 0),
        'last_prompt_state': str(source.get('last_prompt_state') or ''),
        'last_error': str(source.get('last_error') or ''),
        'updated_at_unix': int(source.get('updated_at_unix') or 0),
    }


def _with_finalization(job: dict | None, **updates) -> dict:
    meta = _finalization_meta(job)
    meta.update(updates or {})
    meta['updated_at_unix'] = _now_unix()
    return meta


def _job_has_persisted_outputs(job: dict | None) -> bool:
    """Return true only when Neo has a real persisted output record."""
    for item in (job or {}).get('outputs') or []:
        if not isinstance(item, dict):
            continue
        saved_path_raw = str(item.get('saved_path') or '').strip()
        save_directory_raw = str(item.get('save_directory') or '').strip()
        if not saved_path_raw or not save_directory_raw:
            continue
        try:
            if Path(saved_path_raw).exists():
                return True
        except Exception:
            continue
    return False


def _job_needs_finalization(job: dict | None) -> bool:
    """Single predicate used by /job, /state, and background finalization."""
    if not isinstance(job, dict):
        return False
    state = str(job.get('state') or job.get('status') or '').strip().lower()
    if state in {'error', 'failed', 'cancelled'}:
        return False
    if state in _FINALIZATION_ACTIVE_STATES:
        return True
    if state == 'completed' and not _job_has_persisted_outputs(job):
        return True
    return False


def _job_state_update(state: str, text: str, *, progress: int | None = None, finalization: dict | None = None, outputs: list[dict] | None = None, error: str = '') -> dict:
    update = {'state': state, 'status_text': text, 'error': error}
    if progress is not None:
        update['progress'] = {'percent': max(0, min(100, int(progress))), 'detail': text}
    if finalization is not None:
        update['finalization'] = finalization
    if outputs is not None:
        update['outputs'] = outputs
    return update

async def _refresh_generation_job_from_backend(job_id: str) -> dict | None:
    """Refresh one generation job and persist backend outputs into Neo.

    This is the single finalization path used by /job polling, /state refresh,
    and the background finalizer. Keeping the persistence logic here prevents the
    ComfyUI-only save regression where a job completes but Neo never copies the
    final image into its configured output folder.
    """
    job = get_generation_job(job_id)
    if not job:
        return None

    adapter, _session, _error = _image_profile_or_error()
    prompt_id = str(job.get('prompt_id') or '').strip()
    target_job_id = str(job.get('id') or job.get('job_id') or job_id)
    if not adapter or not prompt_id:
        return job

    try:
        history = await adapter.get_history(prompt_id)
        data = history.get(prompt_id) if isinstance(history, dict) else None

        if not data:
            try:
                full_history = await adapter.get_history(None)
                if isinstance(full_history, dict):
                    data = full_history.get(prompt_id)
            except Exception as exc:
                logger.debug('Generation full-history fallback failed for %s | %s', target_job_id, exc)

        if data:
            comfy_error = _extract_comfy_error_message(data)
            if comfy_error:
                logger.error('Generation failed in ComfyUI | job_id=%s | prompt_id=%s | error=%s', target_job_id, prompt_id, comfy_error)
                return _generation_comfy_error_update(job, target_job_id, prompt_id, comfy_error, data) or job

            completed = _history_entry_completed(data)
            outputs = _normalize_generation_history_outputs(data, adapter)
            logger.info(
                'Generation history outputs found | job_id=%s | prompt_id=%s | completed=%s | count=%s',
                target_job_id,
                prompt_id,
                bool(completed),
                len(outputs),
            )
            meta = _with_finalization(
                job,
                phase='history_complete' if completed else 'backend_running',
                history_seen=True,
                history_completed=bool(completed),
                outputs_normalized=bool(outputs),
                missing_history_checks=0,
                last_prompt_state='history',
                last_error='',
            )
            if completed and outputs:
                job = update_generation_job(target_job_id, _job_state_update(
                    'outputs_registered',
                    f'Registered {len(outputs)} backend output(s); saving to Neo library…',
                    progress=96,
                    finalization=meta,
                    outputs=outputs,
                )) or job
                try:
                    meta = _with_finalization(job, phase='persisting_outputs', outputs_normalized=True, last_error='')
                    job = update_generation_job(target_job_id, _job_state_update(
                        'persisting_outputs',
                        'Saving generated output files and metadata…',
                        progress=98,
                        finalization=meta,
                        outputs=outputs,
                    )) or job
                    persisted_outputs = await _persist_generation_outputs(job, outputs, adapter)
                except Exception as exc:
                    logger.exception('Could not persist generation outputs for %s', target_job_id)
                    meta = _with_finalization(job, phase='persist_failed', last_error=str(exc))
                    return update_generation_job(target_job_id, _job_state_update(
                        'error',
                        'Could not persist generated outputs.',
                        progress=100,
                        finalization=meta,
                        outputs=outputs,
                        error=str(exc),
                    )) or job

                meta = _with_finalization(
                    job,
                    phase='ui_finalized',
                    history_seen=True,
                    history_completed=True,
                    outputs_normalized=True,
                    outputs_persisted=True,
                    ui_finalized=True,
                    last_error='',
                )
                return update_generation_job(target_job_id, _job_state_update(
                    'completed',
                    'Completed.',
                    progress=100,
                    finalization=meta,
                    outputs=persisted_outputs,
                )) or job

            if completed and not outputs:
                prior_meta = _finalization_meta(job)
                checks = int(prior_meta.get('missing_history_checks') or 0) + 1
                if checks < _FINALIZATION_MISSING_HISTORY_LIMIT:
                    meta = _with_finalization(
                        job,
                        phase='awaiting_outputs',
                        history_seen=True,
                        history_completed=True,
                        outputs_normalized=False,
                        missing_history_checks=checks,
                        last_error='Backend history completed without image outputs yet.',
                    )
                    return update_generation_job(target_job_id, _job_state_update(
                        'finalizing_output',
                        f'Backend completed; waiting for image outputs to appear in history ({checks}/{_FINALIZATION_MISSING_HISTORY_LIMIT})…',
                        progress=95,
                        finalization=meta,
                    )) or job
                meta = _with_finalization(
                    job,
                    phase='history_completed_without_images',
                    history_seen=True,
                    history_completed=True,
                    outputs_normalized=False,
                    missing_history_checks=checks,
                    last_error='Backend history completed without image outputs.',
                )
                return update_generation_job(target_job_id, _job_state_update(
                    'error',
                    'ComfyUI finished, but no image output was returned in history.',
                    progress=100,
                    finalization=meta,
                    error='The backend history entry exists and is completed, but it has no image outputs. Check the workflow final Save Image / output node and ComfyUI console for node errors.',
                )) or job

            # If ComfyUI has a history entry but it is not completed, make sure the
            # prompt is still actually present in queue/running. A killed/cleared backend
            # prompt can otherwise stay forever as completed=False/count=0 and keep
            # polluting /api/generation/state with stale refresh noise.
            prompt_state = ''
            try:
                queue_state = await adapter.get_queue()
                prompt_state = _queue_prompt_state(queue_state, prompt_id)
            except Exception as exc:
                logger.debug('Generation queue check while history incomplete failed for %s | %s', target_job_id, exc)

            if not outputs and not prompt_state:
                prior_meta = _finalization_meta(job)
                checks = int(prior_meta.get('missing_history_checks') or 0) + 1
                if checks < _FINALIZATION_MISSING_HISTORY_LIMIT:
                    meta = _with_finalization(
                        job,
                        phase='stale_history_wait',
                        history_seen=True,
                        history_completed=False,
                        outputs_normalized=False,
                        missing_history_checks=checks,
                        last_prompt_state='history_incomplete_not_queued',
                        last_error='Backend history entry is incomplete and the prompt is no longer queued/running.',
                    )
                    return update_generation_job(target_job_id, _job_state_update(
                        'finalizing_output',
                        f'Backend history is incomplete; checking whether this old prompt is stale ({checks}/{_FINALIZATION_MISSING_HISTORY_LIMIT})…',
                        progress=95,
                        finalization=meta,
                        outputs=outputs,
                    )) or job
                meta = _with_finalization(
                    job,
                    phase='stale_history_abandoned',
                    history_seen=True,
                    history_completed=False,
                    outputs_normalized=False,
                    missing_history_checks=checks,
                    last_prompt_state='history_incomplete_not_queued',
                    last_error='Prompt disappeared from queue and never produced outputs.',
                )
                logger.info('Generation stale job archived | job_id=%s | prompt_id=%s | checks=%s', target_job_id, prompt_id, checks)
                return update_generation_job(target_job_id, _job_state_update(
                    'cancelled',
                    'Old backend prompt was archived because it never produced outputs.',
                    progress=100,
                    finalization=meta,
                    outputs=outputs,
                    error='ComfyUI kept an incomplete history entry for this prompt, but it was no longer queued/running and had no image outputs.',
                )) or job

            meta = _with_finalization(job, phase=prompt_state or 'backend_running', history_seen=True, history_completed=False, outputs_normalized=bool(outputs), missing_history_checks=0, last_prompt_state=prompt_state or 'history_running', last_error='')
            return update_generation_job(target_job_id, _job_state_update(
                prompt_state or 'running',
                'Running in ComfyUI.' if (prompt_state or 'running') == 'running' else 'Queued in ComfyUI.',
                progress=65 if (prompt_state or 'running') == 'running' else 5,
                finalization=meta,
                outputs=outputs,
            )) or job

        try:
            queue_state = await adapter.get_queue()
            prompt_state = _queue_prompt_state(queue_state, prompt_id)
            if prompt_state:
                meta = _with_finalization(job, phase=prompt_state, last_prompt_state=prompt_state, missing_history_checks=0, last_error='')
                return update_generation_job(target_job_id, _job_state_update(
                    prompt_state,
                    'Running in ComfyUI.' if prompt_state == 'running' else 'Queued in ComfyUI.',
                    progress=35 if prompt_state == 'running' else 5,
                    finalization=meta,
                )) or job

            meta = _finalization_meta(job)
            checks = int(meta.get('missing_history_checks') or 0) + 1
            prior_state = str(job.get('state') or '').strip().lower()
            has_saved_outputs = _job_has_persisted_outputs(job)
            if checks < _FINALIZATION_MISSING_HISTORY_LIMIT and prior_state not in _FINALIZATION_TERMINAL_STATES:
                meta = _with_finalization(
                    job,
                    phase='history_wait',
                    missing_history_checks=checks,
                    last_prompt_state='missing',
                    last_error='Prompt is not in queue yet history is not available.',
                )
                return update_generation_job(target_job_id, _job_state_update(
                    'finalizing_output',
                    f'ComfyUI finished queueing this prompt; waiting for history/output registration ({checks}/{_FINALIZATION_MISSING_HISTORY_LIMIT})…',
                    progress=95,
                    finalization=meta,
                )) or job
            if prior_state == 'completed' and has_saved_outputs:
                return job
            meta = _with_finalization(
                job,
                phase='history_missing_failed',
                missing_history_checks=checks,
                last_prompt_state='missing',
                last_error='Prompt was not found in queue or history after repeated checks.',
            )
            return update_generation_job(target_job_id, _job_state_update(
                'error',
                'Generation finished in the backend, but Neo could not resolve the final output record.',
                progress=100,
                finalization=meta,
                error='The Image Backend no longer reports this prompt in queue/history. Neo waited for history/output registration and then stopped polling this job.',
            )) or job
        except Exception as exc:
            logger.warning('Could not refresh generation queue state for %s | %s', target_job_id, exc)
            return job
    except Exception as exc:
        logger.exception('Could not refresh generation job %s', target_job_id)
        _append_generation_log('Could not refresh generation job from backend.', exc=exc, context={'job_id': target_job_id, 'prompt_id': prompt_id})
        meta = _with_finalization(job, phase='refresh_failed', last_error=str(exc))
        return update_generation_job(target_job_id, _job_state_update(
            'error',
            'Could not refresh generation job.',
            progress=100,
            finalization=meta,
            error=str(exc),
        )) or job


async def _background_finalize_generation_job(job_id: str, *, max_checks: int = 240, interval_sec: float = 2.0) -> None:
    """Keep finalizing a queued generation even if the frontend polling path stops.

    Phase C1: this background task must never bubble an exception to the ASGI
    runtime. A failed history/output fetch should mark the job failed safely and
    write a focused runtime log instead of taking Neo down after generation.
    """
    target = str(job_id or '').strip()
    if not target:
        return
    try:
        for _ in range(max(1, int(max_checks))):
            await asyncio.sleep(max(0.5, float(interval_sec)))
            job = get_generation_job(target)
            if not _job_needs_finalization(job):
                return
            try:
                refreshed = await _refresh_generation_job_from_backend(target)
            except Exception as exc:
                _generation_runtime_error_update(
                    job,
                    target,
                    'Generation background finalizer crashed safely. Neo stayed open; check neo_generation_runtime.log.',
                    exc,
                    phase='background_finalizer_failed',
                )
                return
            if not _job_needs_finalization(refreshed):
                return
    except Exception as exc:
        job = get_generation_job(target)
        _generation_runtime_error_update(
            job,
            target,
            'Generation finalizer loop crashed safely. Neo stayed open; check neo_generation_runtime.log.',
            exc,
            phase='background_finalizer_loop_failed',
        )


def _default_wildcard_root() -> Path:
    root = get_library_root() / 'wildcards'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_wildcard_root(raw: str = '') -> Path:
    value = str(raw or '').strip()
    root = Path(value).expanduser() if value else _default_wildcard_root()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _wildcard_token_for_path(root: Path, fp: Path) -> str:
    rel = fp.resolve().relative_to(root.resolve())
    return str(rel.with_suffix('')).replace('\\', '/')


def _load_wildcard_values_file(fp: Path) -> list[str]:
    suffix = fp.suffix.lower()
    if suffix == '.txt':
        values = []
        for line in fp.read_text(encoding='utf-8', errors='ignore').splitlines():
            item = line.strip()
            if item and not item.startswith('#'):
                values.append(item)
        return values
    if suffix == '.json':
        payload = json.loads(fp.read_text(encoding='utf-8'))
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
        if isinstance(payload, dict):
            items = payload.get('items') if isinstance(payload.get('items'), list) else []
            if items:
                return [str(item).strip() for item in items if str(item).strip()]
            values = []
            for key, value in payload.items():
                if isinstance(value, list):
                    values.extend(str(item).strip() for item in value if str(item).strip())
                elif isinstance(value, str) and value.strip():
                    values.append(value.strip())
            return values
    if suffix in {'.yaml', '.yml'}:
        try:
            import yaml  # type: ignore
            payload = yaml.safe_load(fp.read_text(encoding='utf-8'))
        except Exception:
            payload = None
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
        if isinstance(payload, dict):
            items = payload.get('items') if isinstance(payload.get('items'), list) else []
            if items:
                return [str(item).strip() for item in items if str(item).strip()]
    return []


def _queue_prompt_state(queue_payload, prompt_id: str) -> str | None:
    target = str(prompt_id or '').strip()
    if not target:
        return None

    def _contains_prompt(rows) -> bool:
        for row in rows or []:
            if isinstance(row, (list, tuple)):
                for item in row:
                    if str(item or '') == target:
                        return True
            elif isinstance(row, dict):
                if str(row.get('prompt_id') or '') == target:
                    return True
            elif str(row or '') == target:
                return True
        return False

    if isinstance(queue_payload, dict):
        if _contains_prompt(queue_payload.get('queue_running')):
            return 'running'
        if _contains_prompt(queue_payload.get('queue_pending')):
            return 'queued'
    return None




def _iter_requested_external_extension_ids_from_payload(payload: dict[str, Any] | None) -> set[str]:
    """Return extension ids requested by the generation payload.

    The frontend state store can be ahead of the backend registry cache after a
    user copies an extension folder into neo_extensions/installed. Generation
    must verify those requested ids against a freshly hydrated backend registry
    before stamping validation, otherwise valid extensions are falsely marked
    not_registered and never reach the external workflow executor.
    """
    payload = payload if isinstance(payload, dict) else {}
    candidates: list[Any] = []
    raw = payload.get('external_extensions')
    if isinstance(raw, dict):
        candidates.append(raw)
    image_state = payload.get('image_state') if isinstance(payload.get('image_state'), dict) else {}
    modules = image_state.get('modules') if isinstance(image_state.get('modules'), dict) else {}
    module_exts = modules.get('external_extensions')
    if isinstance(module_exts, dict):
        candidates.append(module_exts)
    ids: set[str] = set()
    for block in candidates:
        for key, value in block.items():
            extension_id = str(key or '').strip()
            if not extension_id and isinstance(value, dict):
                extension_id = str(value.get('extension_id') or value.get('id') or '').strip()
            if extension_id:
                ids.add(extension_id)
    return ids


def _external_registry_ids(registry: dict[str, Any] | None) -> set[str]:
    registry = registry if isinstance(registry, dict) else {}
    ids: set[str] = set()
    for bucket in ('enabled', 'installed', 'disabled', 'invalid'):
        for item in registry.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            extension_id = str(item.get('extension_id') or item.get('id') or '').strip()
            if extension_id:
                ids.add(extension_id)
            slug = str(item.get('slug') or '').strip()
            surface = str(item.get('surface') or item.get('target_surface') or '').strip()
            if surface and slug:
                ids.add(f'{surface}.{slug}')
    return ids


def _build_external_registry_for_generation_payload(payload: dict[str, Any] | None, *, surface: str = 'image') -> dict[str, Any]:
    """Build an external registry snapshot that is safe for generation stamping.

    Normal registry routes may show frontend hooks while the generation-time
    payload validator still sees a stale cache. This helper forces one rebuild
    when the payload asks for an extension id that is missing from the current
    backend snapshot. It is global behavior for all external extensions.
    """
    registry = build_external_extension_registry(surface=surface)
    requested = _iter_requested_external_extension_ids_from_payload(payload)
    if not requested:
        return registry
    if requested.issubset(_external_registry_ids(registry)):
        return registry
    try:
        rebuild_extension_registry()
        registry = build_external_extension_registry(surface=surface)
    except Exception:
        # Preserve guardrail behavior: if rebuild fails, validation will keep the
        # requested extension disabled with a visible reason instead of running it.
        return registry
    return registry

def _image_profile_or_error():
    manager_state = get_manager_state()
    session = (manager_state.get('session') or {}).get('image') or {}
    if not session.get('connected'):
        return None, session, json_error('Connect the Image Backend first.', 400)
    profile = get_profile('image', session.get('profile_id') or None)
    if not profile:
        return None, session, json_error('Active Image Backend profile was not found.', 404)
    adapter = ComfyBackendAdapter(profile.get('base_url') or session.get('base_url') or '', timeout_sec=int(profile.get('timeout_sec') or 30))
    return adapter, session, None


async def _save_upload(upload: UploadFile | None, prefix: str) -> dict | None:
    if not upload:
        return None
    raw = await upload.read()
    if not raw:
        return None
    ensure_generation_dirs()
    filename = safe_name(Path(upload.filename or prefix).stem) + Path(upload.filename or '').suffix[:12]
    target = GENERATION_INPUT_DIR / f'{prefix}_{filename}'
    target.write_bytes(raw)
    return {
        'path': target,
        'filename': target.name,
        'content': raw,
    }



def _normalize_source_resize_mode(raw: str | None) -> str:
    clean = str(raw or 'native').strip().lower()
    return clean if clean in {'native', 'fit', 'crop', 'stretch'} else 'native'


def _target_size_from_payload(payload: dict | None) -> tuple[int, int]:
    payload = payload or {}
    try:
        width = int(float(payload.get('width') or 0) or 0)
    except Exception:
        width = 0
    try:
        height = int(float(payload.get('height') or 0) or 0)
    except Exception:
        height = 0
    return max(0, width), max(0, height)


def _image_size_from_bytes(raw: bytes | None) -> tuple[int, int]:
    if not raw:
        return 0, 0
    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        return int(width or 0), int(height or 0)
    except Exception:
        return 0, 0


def _is_detailer_output_pass(payload: dict | None) -> bool:
    return bool((payload or {}).get('detailer_output_pass'))


def _lock_detailer_output_source_to_native(payload: dict, saved_source: dict | None) -> list[str]:
    """Preserve preview-derived Highres outputs for Selective Repair-only passes.

    Preview ADetailer queues as img2img and can inherit source_resize_mode='crop'
    from the main workspace. That is correct for normal img2img/inpaint, but
    destructive for a later detailer pass: the selected Highres output gets copied
    back to a source upload and cropped down to the base canvas before FaceDetailer
    sees it. For detailer_output_pass the source image itself is the canvas.
    """
    if not _is_detailer_output_pass(payload):
        return []
    notes = ['Selective Repair later pass is source-native: source_resize_mode was forced to native so Highres outputs are not cropped back to the base canvas.']
    payload['source_resize_mode'] = 'native'
    width, height = _image_size_from_bytes((saved_source or {}).get('content') if saved_source else None)
    if width > 0 and height > 0:
        previous_width, previous_height = _target_size_from_payload(payload)
        payload['width'] = width
        payload['height'] = height
        if (previous_width, previous_height) != (width, height):
            notes.append(f'Selective Repair later pass is using the active source dimensions {width}×{height} instead of the workspace canvas {previous_width or "?"}×{previous_height or "?"}.')
    return notes


def _prepare_image_bytes_for_target(raw: bytes, fallback_name: str, *, width: int, height: int, resize_mode: str = 'native', is_mask: bool = False) -> tuple[bytes, str, list[str]]:
    mode = _normalize_source_resize_mode(resize_mode)
    if not raw or mode == 'native' or width <= 0 or height <= 0:
        return raw, fallback_name, []
    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
    except Exception:
        return raw, fallback_name, [f'Could not decode the {"mask" if is_mask else "source"} image for {mode} resize, so the original file was kept.']

    original_size = tuple(int(v) for v in image.size)
    if original_size == (width, height):
        return raw, fallback_name, []

    if is_mask:
        if image.mode not in {'1', 'L', 'LA', 'RGBA'}:
            image = image.convert('L')
        elif image.mode == 'LA':
            image = image.convert('L')
    else:
        if image.mode == 'P':
            image = image.convert('RGBA')
        elif image.mode not in {'RGB', 'RGBA'}:
            image = image.convert('RGB')

    resample = Image.Resampling.NEAREST if is_mask else Image.Resampling.LANCZOS
    target = (int(width), int(height))
    if mode == 'crop':
        prepared = ImageOps.fit(image, target, method=resample, centering=(0.5, 0.5))
        note = f'Applied center-crop resize to match {width}×{height} before upload.'
    elif mode == 'fit':
        if is_mask:
            prepared = ImageOps.pad(image, target, method=resample, color=0, centering=(0.5, 0.5))
        else:
            pad_color = (0, 0, 0, 0) if 'A' in prepared_mode(image) else (0, 0, 0)
            prepared = ImageOps.pad(image, target, method=resample, color=pad_color, centering=(0.5, 0.5))
        note = f'Applied fit-to-target resize with padding to match {width}×{height} before upload.'
    elif mode == 'stretch':
        prepared = image.resize(target, resample=resample)
        note = f'Applied stretch resize to match {width}×{height} before upload.'
    else:
        return raw, fallback_name, []

    output = io.BytesIO()
    save_kwargs = {}
    if is_mask and prepared.mode not in {'1', 'L'}:
        prepared = prepared.convert('L')
    prepared.save(output, format='PNG', **save_kwargs)
    stem = safe_name(Path(fallback_name or ('mask' if is_mask else 'source')).stem) or ('mask' if is_mask else 'source')
    next_name = f'{stem}_{mode}_{width}x{height}.png'
    prefix = 'Mask' if is_mask else 'Source image'
    return output.getvalue(), next_name, [f'{prefix}: {note}']


def prepared_mode(image: Image.Image) -> str:
    try:
        return str(image.mode or '')
    except Exception:
        return ''


async def _prepare_generation_source_assets(payload: dict, saved_source: dict | None, saved_mask: dict | None) -> tuple[dict | None, dict | None, list[str]]:
    notes: list[str] = []
    if _is_detailer_output_pass(payload):
        notes.extend(_lock_detailer_output_source_to_native(payload, saved_source))
        return saved_source, saved_mask, notes
    mode = str(payload.get('mode') or payload.get('workflow_type') or 'txt2img').strip().lower()
    resize_mode = _normalize_source_resize_mode(payload.get('source_resize_mode') or 'native')
    width, height = _target_size_from_payload(payload)
    if resize_mode == 'native' or width <= 0 or height <= 0:
        return saved_source, saved_mask, notes
    if mode not in {'img2img', 'inpaint'}:
        return saved_source, saved_mask, notes
    if saved_source:
        source_content, source_name, source_notes = _prepare_image_bytes_for_target(
            saved_source.get('content') or b'',
            str(saved_source.get('filename') or 'source.png'),
            width=width,
            height=height,
            resize_mode=resize_mode,
            is_mask=False,
        )
        saved_source = {
            **saved_source,
            'content': source_content,
            'filename': source_name,
            'path': GENERATION_INPUT_DIR / source_name,
        }
        try:
            saved_source['path'].write_bytes(source_content)
        except Exception:
            pass
        notes.extend(source_notes)
    if saved_mask:
        mask_content, mask_name, mask_notes = _prepare_image_bytes_for_target(
            saved_mask.get('content') or b'',
            str(saved_mask.get('filename') or 'mask.png'),
            width=width,
            height=height,
            resize_mode=resize_mode,
            is_mask=True,
        )
        saved_mask = {
            **saved_mask,
            'content': mask_content,
            'filename': mask_name,
            'path': GENERATION_INPUT_DIR / mask_name,
        }
        try:
            saved_mask['path'].write_bytes(mask_content)
        except Exception:
            pass
        notes.extend(mask_notes)
    return saved_source, saved_mask, notes



def _remote_path_from_upload_result(remote: dict, fallback_filename: str) -> str:
    remote_name = str(remote.get('name') or fallback_filename)
    remote_subfolder = str(remote.get('subfolder') or 'neo_studio').strip('/')
    return f'{remote_subfolder}/{remote_name}' if remote_subfolder else remote_name


async def _upload_saved(adapter: ComfyBackendAdapter, saved: dict | None):
    if not saved:
        return ''
    remote = await adapter.upload_image(saved['content'], saved['filename'])
    return _remote_path_from_upload_result(remote, saved['filename'])


def _preprocess_control_image(raw: bytes, preprocessor: str, fallback_name: str) -> tuple[bytes, str, list[str]]:
    mode = str(preprocessor or 'none').strip().lower()
    if mode in {'', 'none'}:
        return raw, fallback_name, []
    if mode in {'openpose', 'depth'}:
        return raw, fallback_name, [f'Using the prebuilt {mode} control map as-is.']
    image_array = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        return raw, fallback_name, [f'Preprocessor {mode} was skipped because the control image could not be decoded.']

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    stem = safe_name(Path(fallback_name or 'control').stem) or 'control'
    note = ''
    output = None

    try:
        if mode == 'canny':
            output = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 100, 200)
            note = 'Applied built-in Canny preprocessor before upload.'
        elif mode == 'softedge':
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            sx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
            sy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
            mag = cv2.magnitude(sx, sy)
            output = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            note = 'Applied built-in Soft Edge preprocessor before upload.'
        elif mode == 'lineart':
            filtered = cv2.bilateralFilter(gray, 7, 30, 30)
            output = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            note = 'Applied built-in Lineart preprocessor before upload.'
        elif mode == 'lineart_anime':
            filtered = cv2.medianBlur(gray, 5)
            output = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 3)
            note = 'Applied built-in Lineart Anime preprocessor before upload.'
        elif mode == 'scribble':
            filtered = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(filtered, 64, 160)
            output = cv2.bitwise_not(edges)
            note = 'Applied built-in Scribble preprocessor before upload.'
        elif mode == 'threshold':
            _ret, output = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            note = 'Applied built-in Threshold preprocessor before upload.'
        elif mode == 'invert':
            output = cv2.bitwise_not(gray)
            note = 'Applied built-in Invert preprocessor before upload.'
        else:
            return raw, fallback_name, [f'Preprocessor {mode} is not supported yet in the legacy shell, so the original control image was used.']
    except Exception:
        return raw, fallback_name, [f'Preprocessor {mode} failed, so the original control image was used.']

    encoded_ok, encoded = cv2.imencode('.png', output)
    if not encoded_ok:
        return raw, fallback_name, [f'{mode} preprocessing failed during PNG encode, so the original control image was used.']
    return encoded.tobytes(), f'{stem}_{mode}.png', [note]


def _extract_history_images(history_entry: dict | None) -> list[dict]:
    images: list[dict] = []
    if not isinstance(history_entry, dict):
        return images
    for node_data in (history_entry.get('outputs') or {}).values():
        if not isinstance(node_data, dict):
            continue
        for image in node_data.get('images') or []:
            if isinstance(image, dict) and image.get('filename'):
                images.append(image)
    return images


def _extract_history_texts(history_entry: dict | None) -> list[str]:
    texts: list[str] = []
    if not isinstance(history_entry, dict):
        return texts
    outputs = history_entry.get('outputs') or {}
    if not isinstance(outputs, dict):
        return texts
    for node_data in outputs.values():
        if not isinstance(node_data, dict):
            continue
        for key, value in node_data.items():
            key_lower = str(key or '').strip().lower()
            if key_lower in {'images', 'gifs', 'audio', 'videos', 'filename'}:
                continue
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        texts.append(item.strip())
    return texts


def _parse_tag_caption(caption: str | None) -> list[str]:
    raw = str(caption or '').strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.replace('\n', ',').split(','):
        tag = str(part or '').strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(tag)
    return out


def _tag_assist_output_inputs(required: dict[str, object], text_ref: list[object]) -> dict[str, object]:
    inputs: dict[str, object] = {}
    options = options if isinstance(options, dict) else {}
    detect_resolution = _clamp_int(options.get('detect_resolution'), 768, 256, 2048)
    canny_low = _clamp_int(options.get('canny_low'), 100, 0, 255)
    canny_high = _clamp_int(options.get('canny_high'), 200, 0, 255)
    if canny_high < canny_low:
        canny_low, canny_high = canny_high, canny_low
    safe_mode = _boolish(options.get('safe_mode'), True)
    openpose_body = _boolish(options.get('openpose_body'), True)
    openpose_hand = _boolish(options.get('openpose_hand'), True)
    openpose_face = _boolish(options.get('openpose_face'), False)
    for key, spec in required.items():
        key_lower = str(key or '').strip().lower()
        input_type = ''
        meta = {}
        choices: list[object] = []
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, str):
                input_type = first
            elif isinstance(first, (list, tuple)):
                choices = list(first)
            if len(spec) > 1 and isinstance(spec[1], dict):
                meta = spec[1]
        if input_type in {'STRING', 'TEXT'} or key_lower in {'text', 'string', 'source', 'value', 'input'}:
            inputs[key] = list(text_ref)
            continue
        if 'default' in meta:
            inputs[key] = meta.get('default')
            continue
        if input_type == 'BOOLEAN':
            if 'body' in key_lower:
                inputs[key] = openpose_body
            elif 'hand' in key_lower:
                inputs[key] = openpose_hand
            elif 'face' in key_lower:
                inputs[key] = openpose_face
            elif 'safe' in key_lower:
                inputs[key] = safe_mode
            else:
                inputs[key] = True
            continue
        if input_type == 'INT':
            inputs[key] = 0
            continue
        if input_type == 'FLOAT':
            inputs[key] = 0.0
            continue
        if choices:
            inputs[key] = choices[0]
            continue
        if input_type == 'STRING':
            inputs[key] = ''
    return inputs


def _tag_assist_inputs(required: dict[str, object], image_ref: list[object], threshold: float, filter_tags: str) -> dict[str, object]:
    inputs: dict[str, object] = {}
    parsed_filter = str(filter_tags or '').strip()
    for key, spec in required.items():
        key_lower = str(key or '').strip().lower()
        input_type = ''
        meta = {}
        choices: list[object] = []
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, str):
                input_type = first
            elif isinstance(first, (list, tuple)):
                choices = list(first)
            if len(spec) > 1 and isinstance(spec[1], dict):
                meta = spec[1]
        if key_lower in {'image', 'images'} or input_type == 'IMAGE':
            inputs[key] = list(image_ref)
            continue
        if key_lower == 'threshold':
            inputs[key] = float(threshold)
            continue
        if key_lower in {'sort_alpha', 'sortalphabetically'}:
            inputs[key] = False
            continue
        if key_lower in {'use_spaces', 'replace_underscore'}:
            inputs[key] = True
            continue
        if key_lower in {'escape', 'escape_bracket'}:
            inputs[key] = False
            continue
        if key_lower in {'filter_tags', 'filter'}:
            inputs[key] = parsed_filter
            continue
        if key_lower in {'prefix', 'suffix'}:
            inputs[key] = ''
            continue
        if key_lower in {'enabled', 'enable'}:
            inputs[key] = True
            continue
        if key_lower in {'device_mode', 'device'} and choices:
            preferred = next((item for item in choices if str(item or '').strip().upper() in {'AUTO', 'DEFAULT', 'CUDA'}), None)
            inputs[key] = preferred if preferred is not None else choices[0]
            continue
        if 'default' in meta:
            inputs[key] = meta.get('default')
            continue
        if input_type == 'BOOLEAN':
            inputs[key] = False
            continue
        if input_type == 'INT':
            inputs[key] = 0
            continue
        if input_type == 'FLOAT':
            inputs[key] = 0.0
            continue
        if choices:
            inputs[key] = choices[0]
            continue
        if input_type == 'STRING':
            inputs[key] = ''
    return inputs


def _object_required_inputs(node_info: dict | None) -> dict[str, object]:
    if not isinstance(node_info, dict):
        return {}
    input_info = node_info.get('input') if isinstance(node_info.get('input'), dict) else {}
    return (input_info.get('required') or {}) if isinstance(input_info, dict) else {}


def _object_all_inputs(node_info: dict | None) -> dict[str, object]:
    """Return required + optional Comfy node inputs.

    Some comfyui_controlnet_aux nodes mark important params such as
    HED `safe` and Lineart `coarse` as optional, but their wrappers still
    read them directly from kwargs. If Neo only sends required inputs, those
    nodes crash with KeyError.
    """
    if not isinstance(node_info, dict):
        return {}
    input_info = node_info.get('input') if isinstance(node_info.get('input'), dict) else {}
    merged: dict[str, object] = {}
    for group in ('required', 'optional'):
        values = input_info.get(group) or {}
        if isinstance(values, dict):
            merged.update(values)
    return merged


def _clamp_int(value, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except Exception:
        n = int(default)
    return max(low, min(high, n))


def _boolish(value, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'on', 'enabled'}:
        return True
    if text in {'0', 'false', 'no', 'off', 'disabled'}:
        return False
    return bool(default)



def _maybe_invert_image_bytes(raw: bytes, enabled: bool = False) -> bytes:
    if not enabled:
        return raw
    try:
        with Image.open(BytesIO(raw)) as img:
            if img.mode == 'RGBA':
                rgb = img.convert('RGB')
                inv = ImageOps.invert(rgb).convert('RGBA')
                inv.putalpha(img.getchannel('A'))
            else:
                inv = ImageOps.invert(img.convert('RGB'))
            out = BytesIO()
            inv.save(out, format='PNG')
            return out.getvalue()
    except Exception:
        return raw


def _encode_preview_data_url(raw: bytes) -> str:
    return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')


def _resize_for_map(raw: bytes, detect_resolution: int = 768) -> Image.Image:
    """Load image and resize longest side for local fallback preprocessors."""
    img = Image.open(BytesIO(raw)).convert('RGB')
    w, h = img.size
    longest = max(w, h) or 1
    target = max(64, min(2048, int(detect_resolution or 768)))
    if longest > target:
        scale = target / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return img


def _local_controlnet_map_bytes(raw: bytes, mode: str, options: dict | None = None) -> tuple[bytes, str, list[str]]:
    """Small local fallback map builders used only when Aux fails/missing."""
    opts = options or {}
    mode = str(mode or '').strip().lower()
    detect_resolution = _clamp_int(opts.get('detect_resolution'), 768, 64, 2048)
    img = _resize_for_map(raw, detect_resolution)
    rgb = np.array(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    notes: list[str] = []

    if mode == 'canny':
        low = _clamp_int(opts.get('canny_low'), 100, 0, 255)
        high = _clamp_int(opts.get('canny_high'), 200, 0, 255)
        if high < low:
            low, high = high, low
        result = cv2.Canny(gray, low, high)
        backend_name = 'OpenCV Canny fallback'
    elif mode in {'softedge', 'scribble'}:
        edges = cv2.Canny(gray, 64, 160)
        result = cv2.GaussianBlur(edges, (0, 0), 1.25 if mode == 'softedge' else 0.6)
        if mode == 'scribble':
            _, result = cv2.threshold(result, 24, 255, cv2.THRESH_BINARY)
        backend_name = 'OpenCV soft-edge fallback' if mode == 'softedge' else 'OpenCV scribble fallback'
    elif mode in {'lineart', 'lineart_anime'}:
        smooth = cv2.bilateralFilter(gray, 7, 50, 50)
        result = cv2.adaptiveThreshold(smooth, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        result = 255 - result
        if mode == 'lineart_anime':
            kernel = np.ones((2, 2), np.uint8)
            result = cv2.morphologyEx(result, cv2.MORPH_OPEN, kernel)
        backend_name = 'OpenCV lineart fallback'
    elif mode == 'depth':
        blur = cv2.GaussianBlur(gray, (0, 0), 2.0)
        result = cv2.normalize(blur, None, 0, 255, cv2.NORM_MINMAX)
        backend_name = 'OpenCV luminance-depth fallback'
        notes.append('Local depth fallback is only an emergency silhouette map. Use MiDaS/DepthAnything/DepthAnythingV2 for production depth.')
    elif mode == 'normalbae':
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        nz = np.ones_like(gx) * 255.0
        normal = np.dstack((gx, gy, nz))
        norm = np.linalg.norm(normal, axis=2, keepdims=True)
        normal = normal / np.maximum(norm, 1e-6)
        result_rgb = ((normal + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
        out = BytesIO()
        Image.fromarray(result_rgb, 'RGB').save(out, format='PNG')
        notes.append('NormalBae fallback uses Sobel normals; install NormalBae for accurate maps.')
        return out.getvalue(), 'normalbae_local_fallback.png', [f'Built normalbae map with OpenCV Sobel-normal fallback.'] + notes
    elif mode == 'openpose':
        raise ValueError('OpenPose/DWPose cannot be generated locally. Install/update comfyui_controlnet_aux and make sure DWPreprocessor or OpenPosePreprocessor is visible in ComfyUI.')
    else:
        raise ValueError(f'No local fallback exists for {mode or "this"} map type.')

    out = BytesIO()
    Image.fromarray(result).convert('RGB').save(out, format='PNG')
    notes.insert(0, f'Built {mode} map with {backend_name}.')
    return out.getvalue(), f'{mode}_local_fallback.png', notes


def _friendly_controlnet_error(exc: Exception | str, mode: str = '', node_name: str = '') -> str:
    text = str(exc or '')
    low = text.lower()
    mode_label = str(mode or 'ControlNet').strip() or 'ControlNet'
    prefix = f'{mode_label.title()} map failed'
    if 'repository not found' in low or '404 client error' in low:
        return f'{prefix}: the selected preprocessor tried to download a missing/private Hugging Face checkpoint. Pick another depth model/checkpoint or install the model manually, then retry.'
    if "keyerror: 'safe'" in low or low.strip() == "'safe'":
        return f'{prefix}: the SoftEdge/HED node requires the safe parameter. Neo will try fallback if available.'
    if "keyerror: 'coarse'" in low or low.strip() == "'coarse'":
        return f'{prefix}: the Lineart node requires the coarse parameter. Neo will try fallback if available.'
    if 'no such file' in low or 'cannot find the file' in low or 'failed to find' in low:
        return f'{prefix}: a required model file is missing. Check the model path/download folder, or use fallback if available.'
    if 'not detected' in low and 'preprocessor' in low:
        return f'{prefix}: no matching preprocessor node was detected in ComfyUI. Run the audit, update/install comfyui_controlnet_aux, or use a fallback-capable map type.'
    if 'timeout' in low or 'not finish' in low or 'longer than usual' in low:
        return f'{prefix}: ComfyUI did not finish in time. First runs can download/warm models; check the ComfyUI console.'
    if 'connection' in low or 'connect' in low:
        return f'{prefix}: Neo could not reach ComfyUI. Start ComfyUI and verify the backend URL.'
    return f'{prefix}: {text}'


def _extract_comfy_error_message(history_entry: dict | None) -> str:
    """Return a compact ComfyUI execution error from a history entry.

    ComfyUI normally stores runtime crashes under status.messages as an
    execution_error event. Earlier Neo builds only waited for completed=True or
    image outputs, so a crashed prompt could remain completed=False/count=0 and
    poll forever. This extractor is deliberately tolerant because different
    ComfyUI/custom-node versions shape the payload slightly differently.
    """
    if not isinstance(history_entry, dict):
        return ''
    status = history_entry.get('status')
    if not isinstance(status, dict):
        return ''

    def _compact(payload) -> str:
        if not isinstance(payload, dict):
            return str(payload or '').strip()
        parts = []
        node_id = str(payload.get('node_id') or payload.get('node') or '').strip()
        node_type = str(payload.get('node_type') or payload.get('class_type') or '').strip()
        exc_type = str(payload.get('exception_type') or '').strip()
        exc_message = str(payload.get('exception_message') or payload.get('message') or payload.get('error') or '').strip()
        if node_id:
            parts.append(f'node {node_id}')
        if node_type:
            parts.append(node_type)
        prefix = ' / '.join(parts)
        if exc_type and exc_message and exc_type not in exc_message:
            body = f'{exc_type}: {exc_message}'
        else:
            body = exc_message or exc_type
        if prefix and body:
            return f'{prefix}: {body}'
        return body or prefix

    messages = status.get('messages') or []
    for item in messages:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                event, payload = item[0], item[1]
                if str(event).lower() in {'execution_error', 'error'}:
                    found = _compact(payload)
                    if found:
                        return found
            elif isinstance(item, dict):
                event = str(item.get('type') or item.get('event') or '').lower()
                if event in {'execution_error', 'error'}:
                    found = _compact(item.get('data') if isinstance(item.get('data'), dict) else item)
                    if found:
                        return found
        except Exception:
            continue

    status_str = str(status.get('status_str') or '').lower()
    if status_str in {'error', 'failed'}:
        return str(status.get('status_str') or 'ComfyUI reported an execution error.').strip()
    return ''



def _format_lanpaint_sampler_guidance(payload: dict | None, raw_error: str = '') -> str:
    """Build an actionable LanPaint sampler/scheduler message for queue-time failures.

    ComfyUI/custom LanPaint nodes can reject sampler combinations at execution time.
    Neo should not surface that as a generic generation failure because the user can
    fix it by choosing a compatible LanPaint sampler pair.
    """
    data = payload if isinstance(payload, dict) else {}
    mode = str(data.get('mode') or data.get('workflow_type') or '').strip().lower()
    backend = str(data.get('inpaint_backend') or data.get('_neo_effective_inpaint_backend') or '').strip().lower()
    route = bool(data.get('_neo_effective_lanpaint_route')) or (mode == 'inpaint' and backend == 'lanpaint')
    if not route:
        return str(raw_error or '').strip()
    policy = data.get('_neo_lanpaint_sampler_policy') if isinstance(data.get('_neo_lanpaint_sampler_policy'), dict) else {}
    family = str(policy.get('family') or data.get('family') or data.get('_neo_effective_family') or '').strip().lower()
    requested_sampler = str(policy.get('requested_sampler') or data.get('sampler') or data.get('sampler_name') or '').strip()
    requested_scheduler = str(policy.get('requested_scheduler') or data.get('scheduler') or '').strip()
    effective_sampler = str(policy.get('effective_sampler') or requested_sampler or '').strip()
    effective_scheduler = str(policy.get('effective_scheduler') or requested_scheduler or '').strip()
    allowed_samplers = policy.get('allowed_samplers') if isinstance(policy.get('allowed_samplers'), list) else []
    allowed_schedulers = policy.get('allowed_schedulers') if isinstance(policy.get('allowed_schedulers'), list) else []
    if not allowed_samplers:
        if family == 'qwen_image_edit':
            allowed_samplers = ['euler']
        elif family == 'sdxl_sd':
            allowed_samplers = ['heun', 'euler', 'euler_ancestral', 'heunpp2', 'dpm_2', 'dpm_2_ancestral', 'ddim']
        else:
            allowed_samplers = ['euler']
    if not allowed_schedulers:
        allowed_schedulers = ['normal', 'simple', 'ddim_uniform'] if family == 'sdxl_sd' else ['simple']
    preferred_sampler = effective_sampler or ('heun' if family == 'sdxl_sd' else 'euler')
    preferred_scheduler = effective_scheduler or ('normal' if family == 'sdxl_sd' else 'simple')
    sampler_preview = ', '.join(str(x) for x in allowed_samplers[:8] if x)
    scheduler_preview = ', '.join(str(x) for x in allowed_schedulers[:8] if x)
    base = (
        f"LanPaint sampler mismatch: the selected sampler/scheduler is not compatible with this LanPaint_KSampler route. "
        f"Change Sampling Method to {preferred_sampler} and Scheduler to {preferred_scheduler}. "
        f"Compatible LanPaint samplers: {sampler_preview or preferred_sampler}. "
        f"Compatible schedulers: {scheduler_preview or preferred_scheduler}."
    )
    raw = str(raw_error or '').strip()
    return f"{base} Backend detail: {raw}" if raw else base

def _generation_comfy_error_update(job: dict | None, target_job_id: str, prompt_id: str, message: str, history_entry: dict | None = None) -> dict | None:
    """Mark a generation job failed after ComfyUI reports execution_error."""
    raw_clean = str(message or 'ComfyUI reported an execution error.').strip()
    clean = _format_lanpaint_sampler_guidance((job or {}).get('payload') if isinstance(job, dict) else {}, raw_clean)
    context = {
        'job_id': target_job_id,
        'prompt_id': prompt_id,
        'phase': 'comfy_execution_error',
        'comfy_error': clean,
    }
    _append_generation_log('ComfyUI execution error detected for generation job.', context=context)
    try:
        payload = {
            'message': clean,
            'job_id': target_job_id,
            'prompt_id': prompt_id,
            'history_status': (history_entry or {}).get('status') if isinstance(history_entry, dict) else {},
        }
        GENERATION_LAST_ERROR_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    except Exception:
        pass
    meta = _with_finalization(
        job or {},
        phase='comfy_execution_error',
        history_seen=True,
        history_completed=False,
        outputs_normalized=False,
        outputs_persisted=False,
        ui_finalized=True,
        missing_history_checks=0,
        last_prompt_state='execution_error',
        last_error=clean,
    )
    return update_generation_job(target_job_id, _job_state_update(
        'failed',
        'Generation failed in ComfyUI.',
        progress=100,
        finalization=meta,
        outputs=[],
        error=clean,
    )) if target_job_id else job


def _create_completed_local_controlnet_job(raw: bytes, mode: str, fallback_name: str, uid: str, options: dict | None, reason: str) -> dict:
    output_bytes, _filename, notes = _local_controlnet_map_bytes(raw, mode, options)
    output_bytes = _maybe_invert_image_bytes(output_bytes, _boolish((options or {}).get('invert_map'), False))
    ensure_generation_dirs()
    out_name = f'neo_local_{mode}_{safe_name(Path(fallback_name or mode).stem)[:48]}_{uuid4().hex[:8]}.png'
    out_path = GENERATION_INPUT_DIR / out_name
    out_path.write_bytes(output_bytes)
    job_id = f'controlmap_{uuid4().hex}'
    return create_long_task(CONTROLNET_MAP_NAMESPACE, {
        'job_id': job_id,
        'uid': str(uid or 'primary'),
        'mode': mode,
        'node_name': 'local_fallback',
        'prompt_id': '',
        'started_at': time.time(),
        'state': 'completed',
        'filename': out_name,
        'output_filename': out_name,
        'output_subfolder': '',
        'output_type': 'input',
        'output_url': f'/api/generation/input/{out_name}',
        'preview_data_url': _encode_preview_data_url(output_bytes),
        'message': f'Built {mode} map with local fallback.',
        'notes': [reason] + notes,
        'backend': 'local_fallback',
        'fallback': True,
        'settings': options or {},
    }, prefix='controlmap')


def _pick_depth_anything_v2_ckpt(choices: list[object], depth_model: str = ''):
    """Avoid broken Depth Anything V2 Giant defaults; prefer Large/Base/Small."""
    if not choices:
        return None
    normalized = [(item, str(item).strip().lower()) for item in choices]
    safe = [(item, text) for item, text in normalized if 'giant' not in text and 'vitg' not in text]
    pool = safe or normalized
    dm = str(depth_model or '').strip().lower()
    if any(x in dm for x in ('base', 'vitb')):
        priority = ('vitb', 'base', 'vitl', 'large', 'vits', 'small')
    elif any(x in dm for x in ('small', 'vits')):
        priority = ('vits', 'small', 'vitb', 'base', 'vitl', 'large')
    else:
        priority = ('vitl', 'large', 'vitb', 'base', 'vits', 'small')
    for token in priority:
        for item, text in pool:
            if token in text:
                return item
    return pool[0][0]


def _depth_choice_preference(choices: list[object], depth_model: str):
    if not choices:
        return None
    dm = str(depth_model or '').strip().lower().replace('-', '_').replace(' ', '_')
    texts = [(item, str(item).strip().lower()) for item in choices]
    if dm in {'depth_anything_v2', 'depth_anything_v2_large', 'depth_anything_v2_base', 'depth_anything_v2_small', 'depthanythingv2'}:
        return _pick_depth_anything_v2_ckpt(choices, dm)
    token_sets = {
        'depth_midas': ('midas',),
        'midas': ('midas',),
        'depth_anything': ('depth_anything', 'anything'),
        'depth_zoe': ('zoe',),
        'zoe': ('zoe',),
        'depth_leres': ('leres',),
        'depth_leres++': ('leres++', 'lerespp'),
        'depth_lerespp': ('leres++', 'lerespp'),
    }
    for token in token_sets.get(dm, (dm.replace('_', ''),)):
        compact_token = token.replace('_', '').replace('-', '').replace('+', 'plus')
        for item, text in texts:
            compact_text = text.replace('_', '').replace('-', '').replace('+', 'plus')
            if compact_token and compact_token in compact_text:
                return item
    return None
def _build_aux_node_inputs(required: dict[str, object], image_ref: list[object], mode: str, options: dict | None = None) -> dict[str, object]:
    options = options or {}
    detect_resolution = _clamp_int(options.get('detect_resolution'), 768, 64, 2048)
    canny_low = _clamp_int(options.get('canny_low'), 100, 0, 255)
    canny_high = _clamp_int(options.get('canny_high'), 200, 0, 255)
    if canny_high < canny_low:
        canny_low, canny_high = canny_high, canny_low
    safe_mode = _boolish(options.get('safe_mode'), True)
    lineart_coarse = _boolish(options.get('lineart_coarse'), False)
    openpose_body = _boolish(options.get('openpose_body'), True)
    openpose_hand = _boolish(options.get('openpose_hand'), True)
    openpose_face = _boolish(options.get('openpose_face'), False)
    depth_model = str(options.get('depth_model') or 'auto').strip().lower()

    def _choice_enabled(choices: list[object], enabled: bool):
        wanted = {'enable', 'enabled', 'true', 'yes', 'on'} if enabled else {'disable', 'disabled', 'false', 'no', 'off'}
        return next((item for item in choices if str(item).strip().lower() in wanted), choices[0] if choices else enabled)

    inputs: dict[str, object] = {}
    for key, spec in required.items():
        key_lower = str(key or '').strip().lower()
        input_type = ''
        meta = {}
        choices: list[object] = []
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, str):
                input_type = first
            elif isinstance(first, (list, tuple)):
                choices = list(first)
            if len(spec) > 1 and isinstance(spec[1], dict):
                meta = spec[1]

        if key_lower in {'image', 'images'} or input_type == 'IMAGE':
            inputs[key] = list(image_ref)
            continue
        if key_lower in {'resolution', 'detect_resolution', 'detect_res'}:
            inputs[key] = detect_resolution
            continue
        if key_lower in {'low_threshold', 'lowthreshold', 'threshold_low', 'low'}:
            inputs[key] = canny_low
            continue
        if key_lower in {'high_threshold', 'highthreshold', 'threshold_high', 'high'}:
            inputs[key] = canny_high
            continue

        # comfyui_controlnet_aux has nodes where these are optional enum inputs,
        # but the wrapper directly indexes kwargs['safe'] / kwargs['coarse'].
        if key_lower in {'safe', 'safe_mode'}:
            inputs[key] = _choice_enabled(choices, safe_mode) if choices else safe_mode
            continue
        if key_lower in {'coarse', 'coarse_mode'}:
            inputs[key] = _choice_enabled(choices, lineart_coarse) if choices else lineart_coarse
            continue

        if mode == 'openpose' and key_lower in {'detect_body', 'body', 'enable_body'}:
            inputs[key] = _choice_enabled(choices, openpose_body) if choices else openpose_body
            continue
        if mode == 'openpose' and key_lower in {'detect_hand', 'detect_hands', 'hand', 'hands', 'enable_hand'}:
            inputs[key] = _choice_enabled(choices, openpose_hand) if choices else openpose_hand
            continue
        if mode == 'openpose' and key_lower in {'detect_face', 'face', 'enable_face'}:
            inputs[key] = _choice_enabled(choices, openpose_face) if choices else openpose_face
            continue

        if choices:
            preferred = None
            if mode == 'openpose' and key_lower in {'bbox_detector', 'pose_estimator'}:
                preferred = next((item for item in choices if 'dw' in str(item).strip().lower()), None)
            if mode == 'depth' and key_lower in {'model', 'ckpt_name', 'model_name', 'depth_model'}:
                preferred = _depth_choice_preference(choices, depth_model)
            inputs[key] = preferred if preferred is not None else choices[0]
            continue

        if 'default' in meta:
            inputs[key] = meta.get('default')
            continue
        if input_type == 'BOOLEAN':
            inputs[key] = True
            continue
        if input_type == 'INT':
            inputs[key] = 0
            continue
        if input_type == 'FLOAT':
            inputs[key] = 0.0
            continue
        if input_type == 'STRING':
            inputs[key] = ''
    return inputs


def _depth_aux_candidates(options: dict | None = None) -> list[str]:
    opts = options or {}
    requested = str(opts.get('depth_model') or opts.get('mode') or 'auto').strip().lower()
    requested = requested.replace('-', '_').replace(' ', '_')
    by_model = {
        'depth_midas': ['MiDaS-DepthMapPreprocessor', 'MiDaS-DepthMapPreprocessor', 'MiDaSDepthMapPreprocessor', 'MIDASDepthMapPreprocessor', 'MiDaS_DepthMapPreprocessor', 'MIDASPreprocessor', 'MidasDetectorProvider'],
        'midas': ['MiDaS-DepthMapPreprocessor', 'MiDaS-DepthMapPreprocessor', 'MiDaSDepthMapPreprocessor', 'MIDASDepthMapPreprocessor', 'MiDaS_DepthMapPreprocessor', 'MIDASPreprocessor', 'MidasDetectorProvider'],
        'depth_anything_v2': ['DepthAnythingV2Preprocessor', 'DepthAnythingV2PreprocessorProvider'],
        'depth_anything_v2_large': ['DepthAnythingV2Preprocessor', 'DepthAnythingV2PreprocessorProvider'],
        'depth_anything_v2_base': ['DepthAnythingV2Preprocessor', 'DepthAnythingV2PreprocessorProvider'],
        'depth_anything_v2_small': ['DepthAnythingV2Preprocessor', 'DepthAnythingV2PreprocessorProvider'],
        'depth_anything': ['DepthAnythingPreprocessor', 'DepthAnythingPreprocessorProvider'],
        'depth_zoe': ['Zoe_DepthMapPreprocessor', 'ZoeDepthMapPreprocessor', 'ZoeDepthPreprocessor', 'ZoeDepthAnythingPreprocessor'],
        'zoe': ['Zoe_DepthMapPreprocessor', 'ZoeDepthMapPreprocessor', 'ZoeDepthPreprocessor', 'ZoeDepthAnythingPreprocessor'],
        'depth_leres': ['LeReSDepthMapPreprocessor', 'LERESDepthMapPreprocessor', 'LeReS_DepthMapPreprocessor'],
        'depth_leres++': ['LeReS++DepthMapPreprocessor', 'LeReS_DepthMap_Preprocessor', 'LeReSDepthMapPreprocessor'],
        'depth_lerespp': ['LeReS++DepthMapPreprocessor', 'LeReS_DepthMap_Preprocessor', 'LeReSDepthMapPreprocessor'],
    }
    fallback = [
        'MiDaS-DepthMapPreprocessor', 'MiDaSDepthMapPreprocessor', 'MIDASDepthMapPreprocessor', 'MiDaS_DepthMapPreprocessor', 'MIDASPreprocessor',
        'DepthAnythingV2Preprocessor', 'DepthAnythingPreprocessor',
        'Zoe_DepthMapPreprocessor', 'ZoeDepthMapPreprocessor', 'ZoeDepthPreprocessor', 'ZoeDepthAnythingPreprocessor',
        'LeReSDepthMapPreprocessor', 'LERESDepthMapPreprocessor', 'LeReS_DepthMapPreprocessor',
        'LeReS++DepthMapPreprocessor',
    ]
    if requested in by_model:
        # If the user picked a specific depth preprocessor, do not silently fall
        # through to DepthAnythingV2. That produced confusing 404s when MiDaS
        # was selected but the backend picked a V2 Giant checkpoint instead.
        return by_model[requested]
    return fallback




def _compact_node_text(value: object) -> str:
    return str(value or '').strip().lower().replace('-', '').replace('_', '').replace(' ', '').replace('+', 'plus')


def _aux_node_matches_mode(node_name: str, mode: str, options: dict | None = None) -> bool:
    text = _compact_node_text(node_name)
    opts = options or {}
    depth_model = str(opts.get('depth_model') or 'auto').strip().lower().replace('-', '_').replace(' ', '_')
    if 'preprocessor' not in text and 'processor' not in text and 'midas' not in text and 'dwpose' not in text:
        return False
    if mode == 'depth':
        if depth_model in {'depth_midas', 'midas'}:
            return 'midas' in text and 'depth' in text
        if depth_model.startswith('depth_anything_v2') or depth_model in {'depthanythingv2'}:
            return 'depthanythingv2' in text
        if depth_model in {'depth_anything', 'depthanything'}:
            return 'depthanything' in text and 'depthanythingv2' not in text
        if depth_model in {'depth_zoe', 'zoe'}:
            return 'zoe' in text and 'depth' in text
        if depth_model in {'depth_leres++', 'depth_lerespp'}:
            return 'leres' in text and 'plus' in text
        if depth_model in {'depth_leres'}:
            return 'leres' in text
        return any(token in text for token in ('midasdepth', 'depthanythingv2', 'depthanything', 'zoedepth', 'leresdepth'))
    if mode == 'canny':
        return 'canny' in text
    if mode == 'softedge':
        return any(token in text for token in ('hed', 'pidinet', 'teed', 'softedge'))
    if mode == 'lineart':
        return 'lineart' in text and 'anime' not in text
    if mode == 'lineart_anime':
        return 'lineart' in text and 'anime' in text
    if mode == 'scribble':
        return 'scribble' in text or 'xdog' in text
    if mode == 'openpose':
        return any(token in text for token in ('dwpreprocessor', 'dwpose', 'openpose'))
    if mode == 'normalbae':
        return 'normal' in text and ('bae' in text or 'map' in text)
    return False


async def _select_aux_preprocessor_node(adapter: ComfyBackendAdapter, candidates: list[str], mode: str, options: dict | None = None) -> tuple[str, dict | None]:
    """Find an Aux node by exact class first, then fuzzy-search ComfyUI /object_info.

    Different comfyui_controlnet_aux versions use slightly different class names
    (for example MiDaS-DepthMapPreprocessor vs MiDaSDepthMapPreprocessor). Exact
    probing alone made Neo think no MiDaS node existed even when the extension had it.
    """
    for node_name in candidates:
        try:
            info = await adapter.get_object_info(node_name)
        except Exception:
            info = {}
        if isinstance(info, dict) and node_name in info:
            info = info.get(node_name)
        if isinstance(info, dict) and info:
            return node_name, info

    try:
        all_info = await adapter.get_object_info()
    except Exception:
        all_info = {}
    if not isinstance(all_info, dict):
        return '', None

    candidate_keys = [str(key) for key in all_info.keys() if _aux_node_matches_mode(str(key), mode, options)]
    # Put exact-ish / preferred candidates first if fuzzy search found several.
    preferred_compact = [_compact_node_text(item) for item in candidates]
    def _rank(name: str):
        c = _compact_node_text(name)
        for idx, pref in enumerate(preferred_compact):
            if pref and (c == pref or pref in c or c in pref):
                return (0, idx, len(name))
        if mode == 'depth' and str((options or {}).get('depth_model') or '').lower() in {'depth_midas', 'midas'} and 'midas' in c:
            return (0, 0, len(name))
        return (1, 999, len(name))
    candidate_keys.sort(key=_rank)
    for node_name in candidate_keys:
        info = all_info.get(node_name)
        if isinstance(info, dict) and info:
            return node_name, info
    return '', None

def _openpose_aux_candidates(options: dict | None = None) -> list[str]:
    opts = options or {}
    body = _boolish(opts.get('openpose_body'), True)
    hand = _boolish(opts.get('openpose_hand'), True)
    face = _boolish(opts.get('openpose_face'), False)
    # Prefer the same DWPreprocessor because modern comfyui_controlnet_aux exposes
    # body/hand/face as inputs. Keep variants as fallback for older installs.
    if body and hand and face:
        variants = ['DWPreprocessor', 'DWPose_Preprocessor', 'OpenposePreprocessor', 'OpenPosePreprocessor']
    elif (not body) and hand and (not face):
        variants = ['DWPreprocessor', 'DWPose_Preprocessor', 'OpenPoseHandPreprocessor', 'OpenposeHandPreprocessor']
    elif (not body) and (not hand) and face:
        variants = ['DWPreprocessor', 'DWPose_Preprocessor', 'OpenPoseFacePreprocessor', 'OpenposeFacePreprocessor']
    else:
        variants = ['DWPreprocessor', 'DWPose_Preprocessor', 'OpenposePreprocessor', 'OpenPosePreprocessor']
    return variants

def _normalize_controlnet_map_mode(mode: str, options: dict | None = None) -> tuple[str, dict]:
    opts = dict(options or {})
    raw = str(mode or '').strip().lower()
    # Accept both compact values from Neo and human-ish labels that may leak
    # from custom select rendering, e.g. "Depth / MiDaS (Forge-style)".
    raw = raw.replace('forge_style', 'midas')
    raw = raw.replace('forge-style', 'midas')
    raw = raw.replace('/', ' ')
    raw = raw.replace('-', '_').replace(' ', '_')
    raw = raw.strip('_')
    if raw in {'depth_midas_forge_style', 'depth_midas', 'depth_midas_midas'} or ('depth' in raw and 'midas' in raw):
        opts['depth_model'] = 'depth_midas'
        return 'depth', opts
    if 'depth' in raw and 'zoe' in raw:
        opts['depth_model'] = 'depth_zoe'
        return 'depth', opts
    if 'depth' in raw and 'leres++' in raw:
        opts['depth_model'] = 'depth_leres++'
        return 'depth', opts
    if 'depth' in raw and 'leres' in raw:
        opts['depth_model'] = 'depth_leres'
        return 'depth', opts
    if 'depth' in raw and 'anythingv2' in raw:
        opts['depth_model'] = 'depth_anything_v2'
        return 'depth', opts
    if raw in {'depth_midas', 'midas', 'depth_anything_v2', 'depth_anything_v2_large', 'depth_anything_v2_base', 'depth_anything_v2_small', 'depth_anything', 'depth_zoe', 'zoe', 'depth_leres', 'depth_leres++', 'depth_lerespp'}:
        opts['depth_model'] = raw
        return 'depth', opts
    if raw in {'canny_edge', 'canny_aux'}:
        opts['preferred_node'] = 'CannyEdgePreprocessor'
        return 'canny', opts
    if raw in {'canny_standard', 'canny_preprocessor'}:
        opts['preferred_node'] = 'CannyPreprocessor'
        return 'canny', opts
    return raw, opts

async def _run_controlnet_aux_map(adapter: ComfyBackendAdapter, raw: bytes, mode: str, fallback_name: str) -> tuple[bytes, str, list[str]]:
    mode, options = _normalize_controlnet_map_mode(mode, {})
    supported_modes = {'canny', 'softedge', 'lineart', 'lineart_anime', 'scribble', 'openpose', 'depth', 'normalbae'}
    if mode not in supported_modes:
        raise ValueError('Pick a supported ControlNet Aux map type: Canny, SoftEdge, Lineart, Lineart Anime, Scribble, OpenPose, Depth, or NormalBae.')

    candidates = {
        'canny': ['CannyEdgePreprocessor', 'CannyPreprocessor'],
        'softedge': ['HEDPreprocessor', 'HEDPreprocessor_safe', 'PiDiNetPreprocessor', 'PiDiNetPreprocessor_safe', 'TEEDPreprocessor'],
        'lineart': ['LineArtPreprocessor', 'LineartPreprocessor', 'LineartStandardPreprocessor'],
        'lineart_anime': ['AnimeLineArtPreprocessor', 'LineartAnimePreprocessor', 'LineArtAnimePreprocessor'],
        'scribble': ['ScribblePreprocessor', 'Scribble_XDoG_Preprocessor', 'Scribble_PiDiNet_Preprocessor', 'FakeScribblePreprocessor'],
        'openpose': _openpose_aux_candidates(options),
        'depth': _depth_aux_candidates(options),
        'normalbae': ['NormalBaePreprocessor', 'BAE-NormalMapPreprocessor', 'NormalMapPreprocessor'],
    }.get(mode, [])
    preferred_node = str((options or {}).get('preferred_node') or '').strip()
    if preferred_node:
        candidates = [preferred_node] + [item for item in candidates if item != preferred_node]

    selected_name, selected_info = await _select_aux_preprocessor_node(adapter, candidates, mode, options)
    if not selected_name:
        requested = str((options or {}).get('depth_model') or mode).strip()
        reason = _friendly_controlnet_error(
            f'No {mode} preprocessor node was detected in the connected ComfyUI backend. Requested: {requested}.',
            mode,
        )
        try:
            output_bytes, filename, notes = _local_controlnet_map_bytes(raw, mode, options)
            return output_bytes, filename, [reason] + notes
        except Exception as fallback_exc:
            raise ValueError(reason + ' Local fallback also failed: ' + str(fallback_exc)) from fallback_exc

    ensure_generation_dirs()
    source_name = f'controlmap_{mode}_{safe_name(Path(fallback_name or mode).stem)[:48]}.png'
    local_path = GENERATION_INPUT_DIR / source_name
    local_path.write_bytes(raw)
    remote = await adapter.upload_image(raw, local_path.name)
    remote_name = _remote_path_from_upload_result(remote, local_path.name)

    graph = {
        '1': {
            'class_type': 'LoadImage',
            'inputs': {
                'image': remote_name,
                'upload': 'image',
            },
        },
    }
    aux_inputs = _build_aux_node_inputs(_object_all_inputs(selected_info), ['1', 0], mode, options)
    graph['2'] = {
        'class_type': selected_name,
        'inputs': aux_inputs,
    }
    graph['3'] = {
        'class_type': 'SaveImage',
        'inputs': {
            'filename_prefix': f'neo_studio/control_maps/{mode}',
            'images': ['2', 0],
        },
    }

    queued = await adapter.queue_prompt(graph)
    prompt_id = str(queued.get('prompt_id') or '').strip()
    if not prompt_id:
        raise ValueError('ComfyUI did not return a prompt id for the ControlNet map build.')

    deadline = time.monotonic() + 45.0
    history_entry = None
    while time.monotonic() < deadline:
        history = await adapter.get_history(prompt_id)
        history_entry = history.get(prompt_id) if isinstance(history, dict) else None
        images = _extract_history_images(history_entry)
        if images:
            image = images[0]
            view_url = _build_download_generation_output_url(adapter, image.get('filename') or '', image.get('subfolder') or '', image.get('type') or 'output')
            if not view_url:
                break
            output_bytes = await _download_output_bytes(view_url, timeout_sec=45)
            filename = image.get('filename') or f'{mode}_map.png'
            note = f'Built {mode} map with {selected_name}.'
            return output_bytes, filename, [note]
        await asyncio.sleep(0.5)

    raise ValueError(f'ComfyUI did not finish building the {mode} map in time.')


async def _neo_advanced_controlnet_available(adapter: ComfyBackendAdapter) -> tuple[bool, str]:
    candidates = [
        'ACN_AdvancedControlNetApply',
        'ACN_ControlNetApplyAdvanced',
        'AdvancedControlNetApply',
        'ControlNetApplyAdvanced',
        'ControlNetApplyAdvanced_ACN',
        'ACN_ApplyAdvancedControlNet',
    ]
    for node_name in candidates:
        try:
            node_info = await adapter.get_object_info(node_name)
            if isinstance(node_info, dict) and (node_info.get(node_name) or _extract_node_input_keys(node_info)):
                return True, node_name
        except Exception:
            continue
    return False, ''


async def _prepare_controlnet_units(adapter: ComfyBackendAdapter, payload: dict, uploads: dict[str, UploadFile | None]) -> list[str]:
    compile_notes: list[str] = []
    units = payload.get('controlnet_units')
    if not isinstance(units, list):
        units = []
    advanced_requested = any(
        isinstance(unit, dict) and (
            bool(unit.get('advanced_enabled'))
            or str(unit.get('advanced_engine') or '').strip().lower() == 'advanced'
            or str(unit.get('strength_schedule') or 'constant').strip().lower() != 'constant'
            or str(unit.get('mask_mode') or 'none').strip().lower() != 'none'
            or bool(unit.get('sliding_context'))
        )
        for unit in units
    )
    advanced_available = False
    advanced_node = ''
    if advanced_requested:
        advanced_available, advanced_node = await _neo_advanced_controlnet_available(adapter)
        if advanced_available:
            compile_notes.append(f'Advanced-ControlNet mode available: {advanced_node}.')
        else:
            compile_notes.append('Advanced-ControlNet was requested, but Neo could not find an Advanced-ControlNet apply node. Units will fall back to standard ControlNetApply.')

    normalized_units = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        model_name = str(unit.get('model') or unit.get('controlnet_name') or '').strip()
        if not model_name:
            continue
        uid = str(unit.get('uid') or f'unit_{index + 1}').strip() or f'unit_{index + 1}'
        upload_key = str(unit.get('image_field') or f'control_image__{uid}')
        upload = uploads.get(upload_key)
        remote_name = ''
        if upload:
            raw = await upload.read()
            if raw:
                processed_raw, processed_name, notes = _preprocess_control_image(raw, unit.get('preprocessor') or 'none', upload.filename or f'{uid}.png')
                compile_notes.extend(notes)
                ensure_generation_dirs()
                target = GENERATION_INPUT_DIR / f'control_{uid}_{safe_name(Path(processed_name).stem)}{Path(processed_name).suffix[:12]}'
                target.write_bytes(processed_raw)
                remote = await adapter.upload_image(processed_raw, target.name)
                remote_name = _remote_path_from_upload_result(remote, target.name)

        mask_field = str(unit.get('mask_field') or f'control_mask__{uid}')
        mask_upload = uploads.get(mask_field)
        mask_remote_name = ''
        if mask_upload:
            mask_raw = await mask_upload.read()
            if mask_raw:
                ensure_generation_dirs()
                mask_target = GENERATION_INPUT_DIR / f'control_mask_{uid}_{safe_name(Path(mask_upload.filename or uid).stem)}{Path(mask_upload.filename or "mask.png").suffix[:12]}'
                mask_target.write_bytes(mask_raw)
                mask_remote = await adapter.upload_image(mask_raw, mask_target.name)
                mask_remote_name = _remote_path_from_upload_result(mask_remote, mask_target.name)

        advanced_enabled = bool(unit.get('advanced_enabled')) or str(unit.get('advanced_engine') or '').strip().lower() == 'advanced'
        normalized_units.append({
            'uid': uid,
            'enabled': bool(unit.get('enabled', True)),
            'unit': str(unit.get('unit') or unit.get('type') or 'auto').strip().lower() or 'auto',
            'model': model_name,
            'preprocessor': str(unit.get('preprocessor') or 'none').strip().lower() or 'none',
            'strength': unit.get('strength') if unit.get('strength') is not None else 1.0,
            'start_percent': unit.get('start_percent') if unit.get('start_percent') is not None else unit.get('start_at', 0.0),
            'end_percent': unit.get('end_percent') if unit.get('end_percent') is not None else unit.get('end_at', 1.0),
            'fit_mode': str(unit.get('fit_mode') or 'contain').strip().lower() or 'contain',
            'detect_resolution': unit.get('detect_resolution') if unit.get('detect_resolution') is not None else 768,
            'safe_mode': bool(unit.get('safe_mode', True)),
            'canny_low': unit.get('canny_low') if unit.get('canny_low') is not None else 100,
            'canny_high': unit.get('canny_high') if unit.get('canny_high') is not None else 200,
            'openpose_body': bool(unit.get('openpose_body', True)),
            'openpose_hand': bool(unit.get('openpose_hand', True)),
            'openpose_face': bool(unit.get('openpose_face', False)),
            'invert_map': bool(unit.get('invert_map', False)),
            'save_intermediate': bool(unit.get('save_intermediate', True)),
            'image_field': upload_key,
            'image_name': remote_name,
            'advanced_enabled': advanced_enabled,
            'advanced_engine': str(unit.get('advanced_engine') or 'auto').strip().lower() or 'auto',
            'advanced_available': bool(advanced_available),
            'advanced_node': advanced_node,
            'advanced_apply_mode': 'advanced' if (advanced_enabled and advanced_available) else 'standard',
            'strength_schedule': str(unit.get('strength_schedule') or 'constant').strip().lower() or 'constant',
            'weight_preset': str(unit.get('weight_preset') or 'default').strip().lower() or 'default',
            'mask_mode': str(unit.get('mask_mode') or 'none').strip().lower() or 'none',
            'mask_field': mask_field,
            'mask_image_name': mask_remote_name,
            'batch_mode': str(unit.get('batch_mode') or 'single').strip().lower() or 'single',
            'sliding_context': bool(unit.get('sliding_context', False)),
        })
    if normalized_units and payload.get('control_image_name') and not normalized_units[0].get('image_name'):
        normalized_units[0]['image_name'] = str(payload.get('control_image_name') or '').strip()
    payload['controlnet_units'] = normalized_units
    payload['advanced_controlnet_active'] = any(unit.get('advanced_apply_mode') == 'advanced' for unit in normalized_units)
    payload['advanced_controlnet_node'] = advanced_node
    if normalized_units:
        first = normalized_units[0]
        payload['controlnet_name'] = first.get('model') or payload.get('controlnet_name') or ''
        payload['control_image_name'] = first.get('image_name') or payload.get('control_image_name') or ''
        payload['controlnet_strength'] = first.get('strength') if first.get('strength') is not None else payload.get('controlnet_strength')
    return compile_notes


async def _prepare_ipadapter_units(adapter: ComfyBackendAdapter, payload: dict, uploads: dict[str, UploadFile | list[UploadFile] | None]) -> list[str]:
    compile_notes: list[str] = []
    units = payload.get('ipadapter_units')
    if not isinstance(units, list):
        units = []
    normalized_units = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
        model_name = str(unit.get('model') or unit.get('ipadapter_name') or '').strip()
        clip_vision = str(unit.get('clip_vision') or unit.get('clip_vision_name') or '').strip()
        if not clip_vision or (mode != 'faceid' and not model_name):
            continue
        uid = str(unit.get('uid') or f'unit_{index + 1}').strip() or f'unit_{index + 1}'
        upload_key = str(unit.get('image_field') or f'ipadapter_image__{uid}')
        upload_value = uploads.get(upload_key)
        upload_list = upload_value if isinstance(upload_value, list) else ([upload_value] if upload_value else [])
        remote_names: list[str] = []
        for upload_index, upload in enumerate(upload_list):
            if not upload:
                continue
            raw = await upload.read()
            if not raw:
                continue
            ensure_generation_dirs()
            suffix = Path(upload.filename or f'{uid}_{upload_index + 1}.png').suffix or '.png'
            target = GENERATION_INPUT_DIR / f'ipadapter_{uid}_{upload_index + 1}_{safe_name(Path(upload.filename or f"{uid}_{upload_index + 1}").stem)}{suffix[:12]}'
            target.write_bytes(raw)
            remote = await adapter.upload_image(raw, target.name)
            remote_name = _remote_path_from_upload_result(remote, target.name)
            if remote_name:
                remote_names.append(remote_name)
        remote_name = remote_names[0] if remote_names else ''
        normalized_units.append({
            'uid': uid,
            'mode': mode,
            'model': model_name,
            'clip_vision': clip_vision,
            'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
            'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
            'start_at': unit.get('start_at') if unit.get('start_at') is not None else 0.0,
            'end_at': unit.get('end_at') if unit.get('end_at') is not None else 1.0,
            'weight': unit.get('weight') if unit.get('weight') is not None else 1.0,
            'weight_faceidv2': unit.get('weight_faceidv2') if unit.get('weight_faceidv2') is not None else (unit.get('weight') if unit.get('weight') is not None else 1.0),
            'faceid_preset': str(unit.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
            'faceid_provider': str(unit.get('faceid_provider') or 'CUDA').strip() or 'CUDA',
            'faceid_lora_strength': unit.get('faceid_lora_strength') if unit.get('faceid_lora_strength') is not None else 0.75,
            'image_name': remote_name,
            'image_names': remote_names,
        })
    if normalized_units and payload.get('ipadapter_image_name') and not normalized_units[0].get('image_name'):
        normalized_units[0]['image_name'] = str(payload.get('ipadapter_image_name') or '').strip()
        if not normalized_units[0].get('image_names'):
            normalized_units[0]['image_names'] = [normalized_units[0]['image_name']] if normalized_units[0].get('image_name') else []
    bound_slots_raw = payload.get('scene_director_ipadapter_bound_slots')
    bound_slots = set()
    if isinstance(bound_slots_raw, list):
        for item in bound_slots_raw:
            try:
                slot = int(item)
            except Exception:
                slot = 0
            if slot > 0:
                bound_slots.add(slot)
    suppress_global_scene_ip = bool(payload.get('scene_director_suppress_global_ipadapter'))
    if bound_slots or suppress_global_scene_ip:
        payload['scene_director_bound_ipadapter_units_source'] = [dict(unit, _neo_slot_index=index + 1) for index, unit in enumerate(normalized_units)]
        if suppress_global_scene_ip:
            suppressed_count = len(normalized_units)
            normalized_units = []
            if suppressed_count:
                compile_notes.append(f"Scene Director suppressed {suppressed_count} global IPAdapter slot(s); only region-bound IPAdapter slots will be applied.")
        else:
            normalized_units = [unit for index, unit in enumerate(normalized_units) if (index + 1) not in bound_slots]
            if normalized_units:
                compile_notes.append(f"Scene Director moved {len(bound_slots)} bound IPAdapter slot(s) out of the global IPAdapter stack for masked regional use.")
            else:
                compile_notes.append(f"Scene Director moved {len(bound_slots)} bound IPAdapter slot(s) out of the global IPAdapter stack; no global IPAdapter slots remain.")
    payload['ipadapter_units'] = normalized_units
    if normalized_units:
        first = normalized_units[0]
        payload['ipadapter_mode'] = first.get('mode') or payload.get('ipadapter_mode') or 'standard'
        payload['ipadapter_name'] = first.get('model') or payload.get('ipadapter_name') or ''
        payload['ipadapter_clip_vision'] = first.get('clip_vision') or payload.get('ipadapter_clip_vision') or ''
        payload['ipadapter_image_name'] = first.get('image_name') or payload.get('ipadapter_image_name') or ''
        payload['ipadapter_image_names'] = first.get('image_names') or payload.get('ipadapter_image_names') or ([] if not payload.get('ipadapter_image_name') else [payload.get('ipadapter_image_name')])
        payload['ipadapter_weight'] = first.get('weight') if first.get('weight') is not None else payload.get('ipadapter_weight')
        payload['ipadapter_weight_faceidv2'] = first.get('weight_faceidv2') if first.get('weight_faceidv2') is not None else payload.get('ipadapter_weight_faceidv2')
        payload['ipadapter_weight_type'] = first.get('weight_type') or payload.get('ipadapter_weight_type') or 'linear'
        payload['ipadapter_combine_embeds'] = first.get('combine_embeds') or payload.get('ipadapter_combine_embeds') or 'concat'
        payload['ipadapter_embeds_scaling'] = first.get('embeds_scaling') or payload.get('ipadapter_embeds_scaling') or 'V only'
        payload['ipadapter_faceid_preset'] = first.get('faceid_preset') or payload.get('ipadapter_faceid_preset') or 'FACEID PLUS V2'
        payload['ipadapter_faceid_provider'] = first.get('faceid_provider') or payload.get('ipadapter_faceid_provider') or 'CUDA'
        payload['ipadapter_faceid_lora_strength'] = first.get('faceid_lora_strength') if first.get('faceid_lora_strength') is not None else payload.get('ipadapter_faceid_lora_strength')
        payload['ipadapter_start_at'] = first.get('start_at') if first.get('start_at') is not None else payload.get('ipadapter_start_at')
        payload['ipadapter_end_at'] = first.get('end_at') if first.get('end_at') is not None else payload.get('ipadapter_end_at')
    return compile_notes


async def _prepare_scene_director_ipadapter_units(adapter: ComfyBackendAdapter, payload: dict, uploads: dict[str, UploadFile | list[UploadFile] | None]) -> list[str]:
    compile_notes: list[str] = []

    # Phase 10.3.2 hard bridge: Identity Profiles must not depend on the main
    # Neo IPAdapter toggle. The Scene Director UI emits scene_director_identity_units;
    # here we convert those profile-backed units into the exact
    # scene_director_ipadapter_units shape consumed by the Comfy graph builder.
    identity_units = payload.get('scene_director_identity_units')
    if not isinstance(identity_units, list):
        identity_units = payload.get('identity_profile_units') if isinstance(payload.get('identity_profile_units'), list) else []
    bridged_identity_units: list[dict] = []
    guardrails = payload.get('scene_director_ipadapter_guardrails') if isinstance(payload.get('scene_director_ipadapter_guardrails'), list) else []
    auto_fix_actions = payload.get('scene_director_ipadapter_auto_fix_actions') if isinstance(payload.get('scene_director_ipadapter_auto_fix_actions'), list) else []
    faceid_nodes_ok: bool | None = None
    for idx, unit in enumerate(identity_units or []):
        if not isinstance(unit, dict):
            continue
        if unit.get('missing_reference_image'):
            label = str(unit.get('profile_name') or unit.get('label') or idx + 1)
            guardrails.append({'level': 'warning', 'reason': 'profile_missing_image', 'label': label, 'region_id': unit.get('region_id') or '', 'message': f'Scene Director Identity Profile skipped {label}: no reference image filename/path was provided.'})
            compile_notes.append(f'Scene Director Identity Profile skipped {label}: no reference image filename/path was provided.')
            continue
        mode = str(unit.get('mode') or unit.get('ipadapter_mode') or 'faceid').strip().lower() or 'faceid'
        if mode == 'ipadapter':
            mode = 'standard'
        if mode not in {'standard', 'faceid'}:
            mode = 'standard'
        image_names = unit.get('image_names') if isinstance(unit.get('image_names'), list) else unit.get('reference_images')
        if not isinstance(image_names, list):
            image_names = []
        image_names = [str(item or '').strip() for item in image_names if str(item or '').strip()]
        image_name = str(unit.get('image_name') or '').strip()
        if image_name and image_name not in image_names:
            image_names.insert(0, image_name)
        if not image_names:
            compile_notes.append(f"Scene Director Identity Profile skipped {str(unit.get('profile_name') or unit.get('label') or idx + 1)}: no reference image filename/path was provided.")
            continue
        clip_vision = str(unit.get('clip_vision') or unit.get('clip_vision_model') or '').strip()
        if not clip_vision or clip_vision.lower() == 'auto':
            clip_vision = str(payload.get('ipadapter_clip_vision') or 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors').strip()
        model_name = str(unit.get('model') or unit.get('ipadapter_model') or '').strip()
        # Character Profile used to silently default to FaceID. On installs without the
        # FaceID preset model, ComfyUI_IPAdapter_plus raises "IPAdapter model not found".
        # Default profile routing now uses the same standard IPAdapter model lane as the
        # working native Scene Builder slot, unless the profile explicitly provides FaceID.
        explicit_mode = str(unit.get('mode') or unit.get('ipadapter_mode') or '').strip().lower()
        if mode == 'faceid':
            if faceid_nodes_ok is None:
                try:
                    loader_info = await adapter.get_object_info('IPAdapterUnifiedLoaderFaceID')
                    apply_info = await adapter.get_object_info('IPAdapterFaceID')
                    faceid_nodes_ok = bool(isinstance(loader_info, dict) and (loader_info.get('IPAdapterUnifiedLoaderFaceID') or loader_info) and isinstance(apply_info, dict) and (apply_info.get('IPAdapterFaceID') or apply_info))
                except Exception:
                    faceid_nodes_ok = False
            if not faceid_nodes_ok:
                fallback_model = model_name or str(payload.get('ipadapter_name') or payload.get('ipadapter_model') or '').strip()
                if fallback_model:
                    auto_fix_actions.append({'action': 'faceid_unavailable_fallback_to_standard_ipadapter', 'profile_id': unit.get('profile_id') or '', 'label': unit.get('profile_name') or unit.get('label') or '', 'fallback_model': fallback_model})
                    compile_notes.append(f"Scene Director Identity Profile {str(unit.get('profile_name') or unit.get('label') or idx + 1)} requested FaceID, but FaceID nodes were not reported; falling back to standard masked IPAdapter.")
                    mode = 'standard'
                    model_name = fallback_model
                else:
                    guardrails.append({'level': 'warning', 'reason': 'faceid_unavailable_no_fallback_model', 'profile_id': unit.get('profile_id') or '', 'label': unit.get('profile_name') or unit.get('label') or '', 'message': 'FaceID nodes/model were unavailable and no standard IPAdapter model was selected.'})
                    compile_notes.append(f"Scene Director Identity Profile skipped {str(unit.get('profile_name') or unit.get('label') or idx + 1)}: FaceID unavailable and no standard IPAdapter model was selected.")
                    continue
        if mode == 'faceid' and not model_name and explicit_mode != 'faceid':
            mode = 'standard'
        if mode != 'faceid' and not model_name:
            model_name = str(payload.get('ipadapter_name') or payload.get('ipadapter_model') or '').strip()
        if mode != 'faceid' and not model_name:
            label = str(unit.get('profile_name') or unit.get('label') or idx + 1)
            guardrails.append({'level': 'warning', 'reason': 'no_ipadapter_model_loaded', 'label': label, 'profile_id': unit.get('profile_id') or '', 'message': 'No IPAdapter model was selected, so regional IPAdapter was disabled for this profile.'})
            compile_notes.append(f"Scene Director Identity Profile skipped {label}: no IPAdapter model was selected. Enable/select the working native IPAdapter model once, then Character Profile can reuse it for regional masking.")
            continue
        try:
            region_index = int(unit.get('region_index') or idx + 1)
        except Exception:
            region_index = idx + 1
        region_index = max(1, min(4, region_index))
        bridged_identity_units.append({
            'uid': str(unit.get('uid') or unit.get('profile_id') or unit.get('region_id') or f'identity_profile_{idx + 1}'),
            'mode': mode,
            'model': model_name,
            'clip_vision': clip_vision,
            'faceid_preset': str(unit.get('faceid_preset') or payload.get('ipadapter_faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
            'faceid_provider': str(unit.get('faceid_provider') or payload.get('ipadapter_faceid_provider') or 'CUDA').strip() or 'CUDA',
            'faceid_lora_strength': unit.get('faceid_lora_strength') if unit.get('faceid_lora_strength') is not None else payload.get('ipadapter_faceid_lora_strength', 0.75),
            'weight_faceidv2': unit.get('weight_faceidv2') if unit.get('weight_faceidv2') is not None else unit.get('weight', 0.45),
            'image_name': image_names[0],
            'image_names': image_names,
            'weight': unit.get('weight') if unit.get('weight') is not None else 0.45,
            'weight_type': str(unit.get('weight_type') or 'linear').strip() or 'linear',
            'combine_embeds': str(unit.get('combine_embeds') or 'concat').strip() or 'concat',
            'start_at': unit.get('start_at') if unit.get('start_at') is not None else 0.0,
            'end_at': unit.get('end_at') if unit.get('end_at') is not None else 0.65,
            'embeds_scaling': str(unit.get('embeds_scaling') or 'V only').strip() or 'V only',
            'region_id': str(unit.get('region_id') or ''),
            'region_index': region_index,
            'label': str(unit.get('profile_name') or unit.get('label') or f'Identity Profile {idx + 1}'),
            'attn_mask_output_index': int(unit.get('attn_mask_output_index') or (5 + region_index)),
            'source': 'scene_director_identity_profile_bridge',
            'composer_mode': 'identity_profile',
        })
    if bridged_identity_units:
        existing_scene_units = payload.get('scene_director_ipadapter_units') if isinstance(payload.get('scene_director_ipadapter_units'), list) else []
        existing_keys = {str(item.get('uid') or '') for item in existing_scene_units if isinstance(item, dict)}
        merged = list(existing_scene_units)
        for unit in bridged_identity_units:
            if str(unit.get('uid') or '') not in existing_keys:
                merged.append(unit)
        payload['scene_director_ipadapter_units'] = merged
        compile_notes.append(f"Scene Director bridged {len(bridged_identity_units)} Identity Profile(s) into masked IPAdapter/FaceID unit(s).")
    payload['scene_director_ipadapter_guardrails'] = guardrails
    payload['scene_director_ipadapter_auto_fix_actions'] = auto_fix_actions
    bindings = payload.get('scene_director_ipadapter_bindings')
    if isinstance(bindings, list) and bindings:
        source_units = payload.get('scene_director_bound_ipadapter_units_source')
        if not isinstance(source_units, list):
            source_units = payload.get('ipadapter_units') if isinstance(payload.get('ipadapter_units'), list) else []
        normalized_units = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            try:
                slot = int(binding.get('slot') or 0)
            except Exception:
                slot = 0
            if slot < 1 or slot > len(source_units):
                guardrails.append({'level': 'warning', 'reason': 'ipadapter_slot_unavailable', 'slot': slot, 'message': f"Scene Director IPAdapter binding skipped: slot {slot or '?'} is not available."})
                compile_notes.append(f"Scene Director IPAdapter binding skipped: slot {slot or '?'} is not available.")
                continue
            source = source_units[slot - 1]
            if not isinstance(source, dict):
                continue
            mode = str(source.get('mode') or 'standard').strip().lower() or 'standard'
            if mode not in {'standard', 'faceid'}:
                mode = 'standard'
            model_name = str(source.get('model') or source.get('ipadapter_name') or '').strip()
            clip_vision = str(source.get('clip_vision') or source.get('clip_vision_name') or '').strip()
            image_names = source.get('image_names') if isinstance(source.get('image_names'), list) else []
            image_names = [str(item or '').strip() for item in image_names if str(item or '').strip()]
            image_name = str(source.get('image_name') or '').strip()
            if image_name and image_name not in image_names:
                image_names.insert(0, image_name)
            if not clip_vision or not image_names or (mode != 'faceid' and not model_name):
                missing = 'CLIP Vision/reference image' if mode == 'faceid' else 'model, CLIP Vision, or reference image'
                guardrails.append({'level': 'warning', 'reason': 'no_ipadapter_model_loaded' if mode != 'faceid' and not model_name else 'ipadapter_reference_or_clip_missing', 'slot': slot, 'region_id': binding.get('region_id') or '', 'label': binding.get('label') or '', 'message': f'Scene Director IPAdapter binding skipped slot {slot}: missing {missing}.'})
                compile_notes.append(f"Scene Director IPAdapter binding skipped slot {slot}: missing {missing}.")
                continue
            region_index = int(binding.get('region_index') or len(normalized_units) + 1)
            use_slot_weight = str(binding.get('weight_mode') or 'slot_default').strip().lower() != 'custom'
            normalized_units.append({
                'uid': str(binding.get('uid') or f'scene_slot_{slot}_region_{region_index}'),
                'mode': mode,
                'model': model_name,
                'clip_vision': clip_vision,
                'faceid_preset': str(source.get('faceid_preset') or 'FACEID PLUS V2').strip() or 'FACEID PLUS V2',
                'faceid_provider': str(source.get('faceid_provider') or 'CUDA').strip() or 'CUDA',
                'faceid_lora_strength': source.get('faceid_lora_strength'),
                'weight_faceidv2': source.get('weight_faceidv2') if use_slot_weight else binding.get('weight_faceidv2'),
                'image_name': image_names[0],
                'image_names': image_names,
                'weight': source.get('weight') if use_slot_weight else binding.get('weight'),
                'weight_type': str(source.get('weight_type') or 'linear').strip() or 'linear',
                'combine_embeds': str(source.get('combine_embeds') or 'concat').strip() or 'concat',
                'start_at': source.get('start_at') if use_slot_weight else binding.get('start_at'),
                'end_at': source.get('end_at') if use_slot_weight else binding.get('end_at'),
                'embeds_scaling': str(source.get('embeds_scaling') or 'V only').strip() or 'V only',
                'region_id': str(binding.get('region_id') or ''),
                'region_index': region_index,
                'label': str(binding.get('label') or f'Region {region_index}'),
                'slot': slot,
                'attn_mask_output_index': int(binding.get('attn_mask_output_index') or (5 + region_index)),
                'source': 'scene_director_existing_ipadapter_slot',
            })
        # Preserve Identity Profile units already bridged above. Manual slot bindings
        # should add to the Scene Director stack, not wipe character-profile units.
        existing_scene_units = payload.get('scene_director_ipadapter_units') if isinstance(payload.get('scene_director_ipadapter_units'), list) else []
        existing_keys = {str(item.get('uid') or '') for item in existing_scene_units if isinstance(item, dict)}
        merged_scene_units = list(existing_scene_units)
        for unit in normalized_units:
            key = str(unit.get('uid') or '')
            if key and key in existing_keys:
                continue
            merged_scene_units.append(unit)
        payload['scene_director_ipadapter_units'] = merged_scene_units
        if normalized_units:
            faceid_bound = sum(1 for unit in normalized_units if str(unit.get('mode') or '').lower() == 'faceid')
            if faceid_bound:
                compile_notes.append(f"Scene Director bound {faceid_bound} FaceID slot(s) to region masks.")
            compile_notes.append(f"Scene Director bound {len(normalized_units)} region(s) to existing Neo IPAdapter slot(s).")
        if bridged_identity_units and normalized_units:
            compile_notes.append("Scene Director preserved Identity Profile unit(s) while adding manual IPAdapter region binding(s).")
        payload['scene_director_ipadapter_count'] = len(payload.get('scene_director_ipadapter_units') or [])
        payload['scene_director_suppress_global_ipadapter'] = payload['scene_director_ipadapter_count'] > 0
        return compile_notes

    units = payload.get('scene_director_ipadapter_units')
    if not isinstance(units, list):
        return compile_notes
    normalized_units = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        mode = str(unit.get('mode') or 'standard').strip().lower() or 'standard'
        if mode not in {'standard', 'faceid'}:
            mode = 'standard'
        model_name = str(unit.get('model') or unit.get('ipadapter_name') or '').strip()
        clip_vision = str(unit.get('clip_vision') or unit.get('clip_vision_name') or '').strip()
        if not clip_vision or (mode != 'faceid' and not model_name):
            continue
        uid = str(unit.get('uid') or f'scene_region_{index + 1}').strip() or f'scene_region_{index + 1}'
        upload_key = str(unit.get('image_field') or f'ipadapter_image__{uid}')
        upload_value = uploads.get(upload_key)
        upload_list = upload_value if isinstance(upload_value, list) else ([upload_value] if upload_value else [])
        remote_names: list[str] = []
        for upload_index, upload in enumerate(upload_list):
            if not upload:
                continue
            raw = await upload.read()
            if not raw:
                continue
            ensure_generation_dirs()
            suffix = Path(upload.filename or f'{uid}_{upload_index + 1}.png').suffix or '.png'
            target = GENERATION_INPUT_DIR / f'ipadapter_{uid}_{upload_index + 1}_{safe_name(Path(upload.filename or f"{uid}_{upload_index + 1}").stem)}{suffix[:12]}'
            target.write_bytes(raw)
            remote = await adapter.upload_image(raw, target.name)
            remote_name = _remote_path_from_upload_result(remote, target.name)
            if remote_name:
                remote_names.append(remote_name)
        existing_names = unit.get('image_names') if isinstance(unit.get('image_names'), list) else []
        existing_names = [str(item or '').strip() for item in existing_names if str(item or '').strip()]
        existing_name = str(unit.get('image_name') or '').strip()
        if existing_name and existing_name not in existing_names:
            existing_names.insert(0, existing_name)
        final_names = remote_names or existing_names
        normalized = dict(unit)
        normalized.update({
            'uid': uid,
            'model': model_name,
            'clip_vision': clip_vision,
            'image_name': final_names[0] if final_names else '',
            'image_names': final_names,
            'image_field': upload_key,
        })
        normalized_units.append(normalized)
    payload['scene_director_ipadapter_units'] = normalized_units
    payload['scene_director_ipadapter_count'] = len(normalized_units)
    payload['scene_director_suppress_global_ipadapter'] = payload['scene_director_ipadapter_count'] > 0
    if normalized_units:
        with_images = sum(1 for unit in normalized_units if unit.get('image_name'))
        profile_units = sum(1 for unit in normalized_units if str(unit.get('composer_mode') or '') == 'identity_profile')
        compile_notes.append(f'Scene Director prepared {with_images}/{len(normalized_units)} per-region IPAdapter reference image(s).')
        if profile_units:
            compile_notes.append(f'Scene Director Identity Profiles active: {profile_units} profile-backed IPAdapter unit(s).')
    return compile_notes


@router.get('/api/generation/styles')
async def api_generation_styles_get():
    return JSONResponse({'ok': True, 'styles': load_generation_styles()})


@router.post('/api/generation/styles/save')
async def api_generation_styles_save(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        styles = upsert_generation_style(
            name=str(payload.get('name') or '').strip(),
            prompt=str(payload.get('prompt') or '').strip(),
            negative_prompt=str(payload.get('negative_prompt') or '').strip(),
            original_name=str(payload.get('original_name') or '').strip(),
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'styles': styles})


@router.post('/api/generation/styles/delete')
async def api_generation_styles_delete(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        styles = delete_generation_style(str(payload.get('name') or '').strip())
    except ValueError as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'styles': styles})


@router.post('/api/generation/styles/duplicate')
async def api_generation_styles_duplicate(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        styles = duplicate_generation_style(
            str(payload.get('source_name') or '').strip(),
            str(payload.get('new_name') or '').strip(),
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    return JSONResponse({'ok': True, 'styles': styles})


@router.post('/api/generation/styles/import')
async def api_generation_styles_import(style_pack: UploadFile | None = File(None)):
    if not style_pack:
        return json_error('Pick a CSV style pack first.', 400)
    raw = await style_pack.read()
    if not raw:
        return json_error('The uploaded style pack was empty.', 400)
    styles = import_generation_styles_csv(raw)
    return JSONResponse({'ok': True, 'styles': styles})


@router.get('/api/generation/styles/export')
async def api_generation_styles_export():
    path = export_generation_styles_path()
    return FileResponse(path, media_type='text/csv', filename='generation_styles.csv')


@router.get('/api/generation/wildcards')
async def api_generation_wildcards(root: str = ''):
    try:
        wildcard_root = _resolve_wildcard_root(root)
        entries = []
        for fp in sorted(wildcard_root.rglob('*')):
            if not fp.is_file() or fp.suffix.lower() not in {'.txt', '.json', '.yaml', '.yml'}:
                continue
            token = _wildcard_token_for_path(wildcard_root, fp)
            count = 0
            try:
                count = len(_load_wildcard_values_file(fp))
            except Exception:
                count = 0
            entries.append({
                'token': token,
                'label': f'__{token}__',
                'relative_path': str(fp.relative_to(wildcard_root)).replace('\\', '/'),
                'count': count,
            })
        return JSONResponse({'ok': True, 'root': str(wildcard_root), 'entries': entries})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load wildcard files.', default_status=500, logger_override=logger, context='generation wildcard load')


@router.get('/api/generation/wildcard-values')
async def api_generation_wildcard_values(root: str = '', token: str = ''):
    try:
        wildcard_root = _resolve_wildcard_root(root)
        clean_token = str(token or '').strip().strip('/')
        if not clean_token:
            return json_error('Pick a wildcard token first.', 400)
        candidate = None
        for suffix in ('.txt', '.json', '.yaml', '.yml'):
            fp = (wildcard_root / clean_token).with_suffix(suffix)
            if fp.exists() and fp.is_file():
                candidate = fp
                break
        if candidate is None:
            return json_error('Wildcard file not found.', 404)
        values = _load_wildcard_values_file(candidate)
        return JSONResponse({
            'ok': True,
            'root': str(wildcard_root),
            'token': clean_token,
            'label': f'__{clean_token}__',
            'relative_path': str(candidate.relative_to(wildcard_root)).replace('\\', '/'),
            'count': len(values),
            'values': values,
        })
    except Exception as exc:
        return json_exception(exc, default_message='Could not read wildcard file.', default_status=500, logger_override=logger, context='generation wildcard read')


@router.get('/api/generation/detailer-models')
async def api_generation_detailer_models(detector_root: str = '', sam_root: str = ''):
    payload = list_generation_detailer_models(detector_root=detector_root, sam_root=sam_root)
    payload['ok'] = True
    payload['message'] = 'Detailer model scan complete.'
    return JSONResponse(payload)


@router.post('/api/generation/detailer-download-sam')
async def api_generation_detailer_download_sam(payload: dict):
    model_key = str((payload or {}).get('model_key') or '').strip()
    sam_root = str((payload or {}).get('sam_root') or '').strip()
    if not model_key:
        return json_error('Pick a SAM preset first.', 400)
    try:
        download = download_sam_model(model_key, target_root=sam_root)
        state = list_generation_detailer_models(detector_root=str((payload or {}).get('detector_root') or '').strip(), sam_root=sam_root)
        return JSONResponse({'ok': True, 'message': f'SAM model downloaded: {download.get("filename")}', 'download': download, **state})
    except Exception as exc:
        return json_exception(exc, default_status=500, logger_override=logger)


@router.post('/api/generation/detailer-preview-detections')
async def api_generation_detailer_preview_detections(
    image: UploadFile = File(...),
    provider: str = Form('ultralytics'),
    mode: str = Form('face'),
    detector_type: str = Form('bbox'),
    detector_model: str = Form(''),
    confidence: float = Form(0.35),
    top_k: int = Form(0),
    bbox_grow: int = Form(12),
    order_mode: str = Form('auto'),
    start_index: int = Form(1),
    count: int = Form(1),
    min_area: int = Form(0),
    max_area: int = Form(0),
    custom_classes: str = Form(''),
    custom_detector_root: str = Form(''),
    priority_preset: str = Form('respect_pass'),
    auto_suppress_tiny_faces: str = Form('1'),
    cluster_merge: str = Form('1'),
    foreground_bias: str = Form('off'),
    pinned_boxes: str = Form('[]'),
    history_boxes: str = Form('[]'),
    tiny_face_main_ratio: float = Form(0.18),
    tiny_face_image_floor_pct: float = Form(0.25),
):
    try:
        raw = await image.read()
        preview = preview_detailer_detections(raw, {
            'provider': provider,
            'mode': mode,
            'detector_type': detector_type,
            'detector_model': detector_model,
            'confidence': confidence,
            'top_k': top_k,
            'bbox_grow': bbox_grow,
            'order_mode': order_mode,
            'start_index': start_index,
            'count': count,
            'min_area': min_area,
            'max_area': max_area,
            'custom_classes': custom_classes,
            'custom_detector_root': custom_detector_root,
            'priority_preset': priority_preset,
            'auto_suppress_tiny_faces': auto_suppress_tiny_faces,
            'cluster_merge': cluster_merge,
            'foreground_bias': foreground_bias,
            'pinned_boxes': pinned_boxes,
            'history_boxes': history_boxes,
            'tiny_face_main_ratio': tiny_face_main_ratio,
            'tiny_face_image_floor_pct': tiny_face_image_floor_pct,
        })
        return JSONResponse(preview)
    except Exception as exc:
        return json_exception(exc, default_message='Could not build the detailer preview detections.', default_status=500, logger_override=logger, context='generation detailer preview')


@router.get('/api/generation/output-download')
async def api_generation_output_download(filename: str, subfolder: str = '', file_type: str = 'output'):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        url = adapter.build_view_url(filename, subfolder or '', file_type or 'output')
        async with httpx.AsyncClient(follow_redirects=True, timeout=max(20, int(adapter.timeout_sec or 30))) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get('content-type') or 'application/octet-stream'
        return Response(content=response.content, media_type=content_type)
    except Exception as exc:
        return json_error(f'Could not load the generated output: {exc}', 502)


@router.get('/api/generation/output-settings')
async def api_generation_output_settings_get():
    settings = load_generation_output_settings()
    ensure_output_root(settings.get('output_root'))
    ensure_category_dir(settings.get('output_root') or DEFAULT_OUTPUT_ROOT, settings.get('selected_category') or 'Uncategorized')
    return JSONResponse({'ok': True, 'settings': _output_settings_response(settings)})


@router.post('/api/generation/output-settings')
async def api_generation_output_settings_save(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    settings = save_generation_output_settings(payload)
    ensure_output_root(settings.get('output_root'))
    ensure_category_dir(settings.get('output_root') or DEFAULT_OUTPUT_ROOT, settings.get('selected_category') or 'Uncategorized')
    return JSONResponse({'ok': True, 'settings': _output_settings_response(settings)})


@router.post('/api/generation/output-settings/category')
async def api_generation_output_settings_add_category(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    name = str(payload.get('name') or '').strip()
    if not name:
        return json_error('Add a category name first.', 400)
    output_root = str(payload.get('output_root') or '').strip() or None
    settings = add_generation_category(name, output_root=output_root)
    root = str(settings.get('output_root') or DEFAULT_OUTPUT_ROOT)
    category = str(settings.get('selected_category') or 'Uncategorized')
    for folder_name in _MODE_OUTPUT_DIRS.values():
        ensure_category_dir(Path(root) / folder_name, category)
    return JSONResponse({'ok': True, 'settings': _output_settings_response(settings)})


@router.get('/api/generation/state')
async def api_generation_state(limit: int = 12):
    manager_state = get_manager_state()
    image_session = (manager_state.get('session') or {}).get('image') or {}
    jobs = list_generation_jobs(limit=limit)
    refreshed_jobs = []
    # Phase 10.8: /state uses the same finalization predicate as /job polling
    # and the background finalizer. No separate persistence rescue path.
    for job in jobs:
        if _job_needs_finalization(job):
            target_job_id = str((job or {}).get('id') or (job or {}).get('job_id') or '')
            try:
                refreshed = await _refresh_generation_job_from_backend(target_job_id)
            except Exception as exc:
                refreshed = _generation_runtime_error_update(
                    job,
                    target_job_id,
                    'Generation state refresh failed safely. Neo stayed open; check neo_generation_runtime.log.',
                    exc,
                    phase='state_refresh_failed',
                )
            refreshed_jobs.append(refreshed or job)
        else:
            refreshed_jobs.append(job)
    return JSONResponse({
        'ok': True,
        'session': image_session,
        'jobs': refreshed_jobs,
        'low_vram_mode': bool((((manager_state.get('settings') or {}).get('settings') or {}).get('low_vram_mode', True))),
    })



@router.websocket('/api/generation/progress/ws')
async def ws_generation_progress(websocket: WebSocket):
    await websocket.accept()
    client_id = str(websocket.query_params.get('clientId') or '').strip()
    adapter, session, error_response = _image_profile_or_error()
    if error_response:
        await websocket.send_json({'type': 'error', 'data': {'message': 'Image backend is not connected.'}})
        await websocket.close(code=1011)
        return
    base_url = (adapter.base_url or '').rstrip('/')
    if not base_url:
        await websocket.send_json({'type': 'error', 'data': {'message': 'Image backend URL is missing.'}})
        await websocket.close(code=1011)
        return

    ws_url = base_url.replace('https://', 'wss://').replace('http://', 'ws://') + f'/ws?clientId={client_id or "neo_studio"}'
    proxy_started = time.time()
    stats = {
        'client_id': client_id or 'neo_studio',
        'upstream': ws_url,
        'text_frames': 0,
        'binary_frames': 0,
        'forwarded_binary_frames': 0,
        'binary_bytes': 0,
        'json_types': {},
        'last_json_type': '',
        'last_binary_bytes': 0,
        'upstream_closed': False,
        'close_reason': '',
    }
    logger.info('Generation progress proxy connecting | upstream=%s', ws_url)
    _append_generation_log('Generation progress proxy connecting.', context={'client_id': stats['client_id'], 'upstream': ws_url})
    upstream = None

    async def _send_proxy_diag(reason: str):
        payload = dict(stats)
        payload['reason'] = reason
        payload['elapsed_sec'] = round(time.time() - proxy_started, 3)
        try:
            await websocket.send_json({'type': 'proxy_diag', 'data': payload})
        except Exception:
            pass

    try:
        upstream = await websockets.connect(ws_url, max_size=None, ping_interval=20, ping_timeout=20)
        await websocket.send_json({'type': 'proxy_open', 'data': {'client_id': stats['client_id'], 'upstream': ws_url}})
        await _send_proxy_diag('open')
        while True:
            try:
                message = await upstream.recv()
            except websockets.ConnectionClosed as exc:
                stats['upstream_closed'] = True
                stats['close_reason'] = f'{getattr(exc, "code", "")}: {getattr(exc, "reason", "")}'.strip()
                await _send_proxy_diag('upstream_closed')
                break
            if isinstance(message, bytes):
                stats['binary_frames'] += 1
                stats['forwarded_binary_frames'] += 1
                stats['last_binary_bytes'] = len(message)
                stats['binary_bytes'] += len(message)
                # Log the first few binary frames and then occasional totals. This proves whether Comfy emits previews.
                if stats['binary_frames'] <= 3 or stats['binary_frames'] % 25 == 0:
                    _append_generation_log('Generation progress proxy binary frame forwarded.', context={
                        'client_id': stats['client_id'],
                        'binary_frames': stats['binary_frames'],
                        'last_binary_bytes': stats['last_binary_bytes'],
                        'binary_bytes': stats['binary_bytes'],
                    })
                    await _send_proxy_diag('binary_frame')
                await websocket.send_bytes(message)
            else:
                stats['text_frames'] += 1
                parsed_type = ''
                try:
                    parsed = json.loads(message) if isinstance(message, str) else {}
                    parsed_type = str((parsed or {}).get('type') or '')
                except Exception:
                    parsed_type = 'non_json_text'
                if parsed_type:
                    stats['last_json_type'] = parsed_type
                    stats['json_types'][parsed_type] = int(stats['json_types'].get(parsed_type, 0)) + 1
                if stats['text_frames'] <= 3 or stats['text_frames'] % 25 == 0:
                    await _send_proxy_diag('text_frame')
                await websocket.send_text(message)
    except WebSocketDisconnect:
        stats['close_reason'] = 'frontend_disconnected'
        _append_generation_log('Generation progress proxy frontend disconnected.', context=stats)
    except Exception as exc:
        logger.warning('Generation progress proxy failed | %s', exc)
        _append_generation_log('Generation progress websocket proxy failed safely.', exc=exc, context=stats)
        try:
            await websocket.send_json({'type': 'error', 'data': {'message': f'Progress proxy failed: {exc}', 'proxy_stats': stats}})
        except Exception:
            pass
    finally:
        _append_generation_log('Generation progress proxy closed.', context=stats)
        try:
            if upstream is not None:
                await upstream.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.get('/api/generation/draft')
async def api_generation_draft_get():
    try:
        record = load_draft(GENERATION_DRAFT_PATH, surface='generation', default=None)
        draft = (record or {}).get('payload') if isinstance(record, dict) else None
        clean_draft = _sanitize_generation_draft_removed_features(draft) if isinstance(draft, dict) else None
        if isinstance(record, dict) and clean_draft is not None:
            record = dict(record)
            record['payload'] = clean_draft
        return JSONResponse({'ok': True, 'draft': clean_draft, 'record': record})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load generation draft.', default_status=500, logger_override=logger, context='generation draft load')


@router.post('/api/generation/draft')
async def api_generation_draft_save(request: Request):
    try:
        payload = await request.json()
        draft = payload.get('draft') if isinstance(payload, dict) else None
        if not isinstance(draft, dict):
          return json_error('Draft payload was invalid.', 400)
        draft = _sanitize_generation_draft_removed_features(draft)
        record = save_draft(GENERATION_DRAFT_PATH, surface='generation', payload=draft, family=str(draft.get('family') or ''), draft_id='generation:draft')
        return JSONResponse({'ok': True, 'record': record})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save generation draft.', default_status=500, logger_override=logger, context='generation draft save')



@router.get('/api/generation/regional/sprint1')
async def api_generation_regional_sprint1():
    return JSONResponse({'ok': False, 'removed': True, 'message': 'Regional Prompter was removed in Phase 9.'}, status_code=410)


@router.get('/api/generation/regional/sprint4')
async def api_generation_regional_sprint4():
    return JSONResponse({'ok': False, 'removed': True, 'message': 'Regional Prompter was removed in Phase 9.'}, status_code=410)




# Phase 10: Batch ControlNet map generation helpers.
def _controlnet_batch_output_dir(batch_id: str) -> Path:
    ensure_generation_dirs()
    root = GENERATION_INPUT_DIR.parent / 'controlnet_batch_maps'
    root.mkdir(parents=True, exist_ok=True)
    out = root / safe_name(batch_id or f'batch_{uuid4().hex}')
    out.mkdir(parents=True, exist_ok=True)
    return out


def _controlnet_batch_manifest_path(batch_id: str) -> Path:
    return _controlnet_batch_output_dir(batch_id) / 'manifest.json'


def _controlnet_batch_zip_path(batch_id: str) -> Path:
    return _controlnet_batch_output_dir(batch_id) / 'controlnet_maps.zip'


def _guess_image_ext(filename: str, content_type: str = '') -> str:
    ext = Path(filename or '').suffix.lower()
    if ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
        return ext
    ctype = (content_type or '').lower()
    if 'jpeg' in ctype or 'jpg' in ctype:
        return '.jpg'
    if 'webp' in ctype:
        return '.webp'
    if 'bmp' in ctype:
        return '.bmp'
    return '.png'


def _write_controlnet_batch_manifest(batch_id: str, job: dict) -> None:
    try:
        manifest = {
            'batch_id': batch_id,
            'state': job.get('state') or '',
            'mode': job.get('mode') or '',
            'settings': job.get('settings') or {},
            'total': job.get('total') or 0,
            'completed': job.get('completed') or 0,
            'failed': job.get('failed') or 0,
            'skipped': job.get('skipped') or 0,
            'entries': job.get('entries') or [],
            'notes': job.get('notes') or [],
        }
        atomic_write_json(_controlnet_batch_manifest_path(batch_id), manifest)
    except Exception:
        logger.exception('Could not write ControlNet batch manifest')


async def _run_controlnet_batch_map_job(batch_id: str) -> None:
    job = get_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id)
    if not job:
        return
    adapter, _session, error = _image_profile_or_error()
    if error:
        job.update({'state': 'error', 'message': 'Could not connect to the active image backend for batch map generation.'})
        update_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id, job)
        return
    entries = list(job.get('entries') or [])
    out_dir = _controlnet_batch_output_dir(batch_id)
    mode = str(job.get('mode') or '').strip()
    options = dict(job.get('settings') or {})
    skip_existing = _boolish(options.get('skip_existing'), True)
    build_zip = _boolish(options.get('build_zip'), True)
    completed = failed = skipped = 0
    notes = list(job.get('notes') or [])
    job.update({'state': 'running', 'message': f'Batch map generation started for {len(entries)} image(s).'})
    update_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id, job)
    for index, entry in enumerate(entries, start=1):
        src_path = Path(entry.get('source_path') or '')
        original_name = str(entry.get('original_name') or src_path.name or f'image_{index}.png')
        stem = safe_name(Path(original_name).stem)[:72] or f'image_{index:04d}'
        map_name = f'{stem}_{safe_name(mode or "map")}.png'
        map_path = out_dir / map_name
        entry.update({'state': 'running', 'message': 'Building map…', 'map_filename': map_name})
        job.update({'current_index': index, 'current_name': original_name, 'entries': entries})
        update_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id, job)
        try:
            if skip_existing and map_path.exists() and map_path.stat().st_size > 0:
                skipped += 1
                entry.update({'state': 'skipped', 'message': 'Skipped existing map.', 'map_path': str(map_path)})
                continue
            raw = src_path.read_bytes()
            norm_mode, norm_options = _normalize_controlnet_map_mode(mode, dict(options))
            if norm_mode in {'none', 'direct'} or 'none' in str(mode).lower():
                output_bytes = raw
                backend = 'direct'
                node_name = 'None / use current image directly'
            else:
                child_job = await _start_controlnet_aux_map_job(adapter, raw, norm_mode, original_name, uid=f'{batch_id}_{index}', options=norm_options)
                child_started = time.time()
                while True:
                    if str(child_job.get('state') or '') != 'completed':
                        child_job = await _resolve_controlnet_aux_map_job(adapter, child_job)
                    state = str(child_job.get('state') or '')
                    if state == 'completed':
                        if child_job.get('preview_data_url'):
                            output_bytes = base64.b64decode(str(child_job.get('preview_data_url')).split(',', 1)[-1])
                        else:
                            output_bytes = await _download_output_bytes(child_job.get('output_url') or '', timeout_sec=60)
                        backend = child_job.get('backend') or 'comfy_aux'
                        node_name = child_job.get('node_name') or ''
                        break
                    if state in {'error', 'timeout'}:
                        raise ValueError(child_job.get('message') or f'{norm_mode} map build failed.')
                    if time.time() - child_started > 600:
                        raise TimeoutError(f'{norm_mode} map build timed out for {original_name}.')
                    await asyncio.sleep(0.8)
            map_path.write_bytes(output_bytes)
            completed += 1
            entry.update({'state': 'completed', 'message': 'Map generated.', 'map_path': str(map_path), 'map_filename': map_name, 'backend': backend, 'node_name': node_name})
        except Exception as exc:
            failed += 1
            entry.update({'state': 'error', 'message': str(exc)})
            logger.exception('ControlNet batch map item failed: %s', original_name)
        finally:
            job.update({'entries': entries, 'completed': completed, 'failed': failed, 'skipped': skipped, 'message': f'Batch progress: {completed} completed, {failed} failed, {skipped} skipped / {len(entries)}.'})
            _write_controlnet_batch_manifest(batch_id, job)
            update_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id, job)
    if build_zip:
        try:
            zip_path = _controlnet_batch_zip_path(batch_id)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                manifest_path = _controlnet_batch_manifest_path(batch_id)
                if manifest_path.exists():
                    zf.write(manifest_path, 'manifest.json')
                for entry in entries:
                    p = Path(entry.get('map_path') or '')
                    if p.exists() and p.is_file():
                        zf.write(p, p.name)
            job['zip_path'] = str(zip_path)
            job['zip_url'] = f'/api/generation/controlnet/batch-maps/download/{batch_id}'
        except Exception as exc:
            notes.append(f'Could not create ZIP: {exc}')
            logger.exception('Could not create ControlNet batch map ZIP')
    final_state = 'completed' if failed == 0 else ('partial' if completed or skipped else 'error')
    job.update({'state': final_state, 'completed': completed, 'failed': failed, 'skipped': skipped, 'notes': notes, 'message': f'Batch map generation finished: {completed} completed, {failed} failed, {skipped} skipped.'})
    _write_controlnet_batch_manifest(batch_id, job)
    update_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, batch_id, job)

@router.get('/api/generation/controlnet/workflow-presets')
async def api_generation_controlnet_workflow_presets():
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        catalog = await adapter.get_catalog()
    except Exception:
        catalog = {}
    controlnet_models = catalog.get('controlnet') if isinstance(catalog, dict) else []
    return JSONResponse({
        'ok': True,
        'presets': _materialize_image_workflow_presets(controlnet_models if isinstance(controlnet_models, list) else []),
        'notes': [
            'Apply a preset to create the recommended ControlNet stack, then build preview maps before final generation.',
            'Union models are treated as valid fallback models for multi-control presets.',
        ],
    })

@router.get('/api/generation/catalog')
async def api_generation_catalog():
    adapter, session, error = _image_profile_or_error()
    if error:
        return error
    try:
        catalog = await adapter.get_catalog()
        stats = await adapter.get_system_stats()
    except Exception as exc:
        return json_exception(exc, default_message='Could not load ComfyUI catalog.', default_status=502, logger_override=logger, context='generation catalog load')
    fallback_samplers = [
        'euler', 'euler_ancestral', 'dpmpp_2m', 'dpmpp_sde', 'dpmpp_2m_sde', 'dpmpp_3m_sde',
        'lcm', 'lms', 'heun', 'dpm_2', 'res_multistep', 'uni_pc', 'ddim', 'plms',
    ]
    fallback_schedulers = [
        'normal', 'karras', 'exponential', 'polyexponential', 'simple', 'sgm_uniform',
        'linear_quadratic', 'kl_optimal', 'ddim_uniform', 'beta', 'turbo',
    ]
    catalog = catalog if isinstance(catalog, dict) else {}
    samplers = catalog.get('samplers') or fallback_samplers
    schedulers = catalog.get('schedulers') or fallback_schedulers
    enriched_catalog = {
        **catalog,
        'upscale_models': catalog.get('upscale_models') or catalog.get('upscalers') or [],
        'upscalers': catalog.get('upscale_models') or catalog.get('upscalers') or [],
        'facerestore_models': catalog.get('facerestore_models') or [],
        'samplers': samplers,
        'schedulers': schedulers,
        'controlnet_workflow_presets': _materialize_image_workflow_presets(catalog.get('controlnet') or []),
    }
    res4lyf = await _detect_res4lyf_catalog(adapter, enriched_catalog)

    # Phase 4: scheduler dropdown expansion. Keep this passive: only append
    # RES4LYF schedulers that the live ComfyUI catalog/detection already reported.
    # Do not make beta57 a default and do not expose it when RES4LYF is absent.
    res4lyf_schedulers = [str(item).strip() for item in (res4lyf.get('schedulers') or []) if str(item).strip()]
    if res4lyf_schedulers:
        existing_scheduler_keys = {str(item).strip().casefold() for item in (enriched_catalog.get('schedulers') or [])}
        expanded_schedulers = list(enriched_catalog.get('schedulers') or [])
        for scheduler_name in res4lyf_schedulers:
            key = scheduler_name.casefold()
            if key and key not in existing_scheduler_keys:
                expanded_schedulers.append(scheduler_name)
                existing_scheduler_keys.add(key)
        enriched_catalog['schedulers'] = expanded_schedulers

    features = enriched_catalog.get('features') if isinstance(enriched_catalog.get('features'), dict) else {}
    enriched_catalog['features'] = {
        **features,
        'res4lyf': bool(res4lyf.get('installed')),
        'res4lyf_ready': bool(res4lyf.get('ready')),
        'res4lyf_clownshark_sampler': bool(res4lyf.get('has_clownshark_sampler')),
        'res4lyf_advanced_lane': bool(res4lyf.get('has_clownshark_sampler')),
    }
    enriched_catalog['res4lyf'] = res4lyf
    return JSONResponse({
        'ok': True,
        'catalog': enriched_catalog,
        'system_stats': stats,
        'session': session,
    })


async def _start_controlnet_aux_map_job(adapter: ComfyBackendAdapter, raw: bytes, mode: str, fallback_name: str, uid: str = 'primary', options: dict | None = None) -> dict:
    mode, options = _normalize_controlnet_map_mode(mode, options)
    supported_modes = {'canny', 'softedge', 'lineart', 'lineart_anime', 'scribble', 'openpose', 'depth', 'normalbae'}
    if mode not in supported_modes:
        raise ValueError('Pick a supported ControlNet Aux map type: Canny, SoftEdge, Lineart, Lineart Anime, Scribble, OpenPose, Depth, or NormalBae.')

    candidates = {
        'canny': ['CannyEdgePreprocessor', 'CannyPreprocessor'],
        'softedge': ['HEDPreprocessor', 'HEDPreprocessor_safe', 'PiDiNetPreprocessor', 'PiDiNetPreprocessor_safe', 'TEEDPreprocessor'],
        'lineart': ['LineArtPreprocessor', 'LineartPreprocessor', 'LineartStandardPreprocessor'],
        'lineart_anime': ['AnimeLineArtPreprocessor', 'LineartAnimePreprocessor', 'LineArtAnimePreprocessor'],
        'scribble': ['ScribblePreprocessor', 'Scribble_XDoG_Preprocessor', 'Scribble_PiDiNet_Preprocessor', 'FakeScribblePreprocessor'],
        'openpose': _openpose_aux_candidates(options),
        'depth': _depth_aux_candidates(options),
        'normalbae': ['NormalBaePreprocessor', 'BAE-NormalMapPreprocessor', 'NormalMapPreprocessor'],
    }.get(mode, [])
    preferred_node = str((options or {}).get('preferred_node') or '').strip()
    if preferred_node:
        candidates = [preferred_node] + [item for item in candidates if item != preferred_node]

    selected_name, selected_info = await _select_aux_preprocessor_node(adapter, candidates, mode, options)
    if not selected_name:
        requested = str((options or {}).get('depth_model') or mode).strip()
        reason = _friendly_controlnet_error(
            f'No {mode} preprocessor node was detected in the connected ComfyUI backend. Requested: {requested}.',
            mode,
        )
        try:
            return _create_completed_local_controlnet_job(raw, mode, fallback_name, uid, options, reason)
        except Exception as fallback_exc:
            raise ValueError(reason + ' Local fallback also failed: ' + str(fallback_exc)) from fallback_exc

    ensure_generation_dirs()
    source_name = f'controlmap_{mode}_{safe_name(Path(fallback_name or mode).stem)[:48]}.png'
    local_path = GENERATION_INPUT_DIR / source_name
    local_path.write_bytes(raw)
    remote = await adapter.upload_image(raw, local_path.name)
    remote_name = _remote_path_from_upload_result(remote, local_path.name)

    graph = {
        '1': {
            'class_type': 'LoadImage',
            'inputs': {
                'image': remote_name,
                'upload': 'image',
            },
        },
        '2': {
            'class_type': selected_name,
            'inputs': _build_aux_node_inputs(_object_all_inputs(selected_info), ['1', 0], mode, options),
        },
        '3': {
            'class_type': 'SaveImage',
            'inputs': {
                'filename_prefix': f'neo_studio/control_maps/{mode}',
                'images': ['2', 0],
            },
        },
    }

    try:
        queued = await adapter.queue_prompt(graph)
    except Exception as exc:
        reason = _friendly_controlnet_error(exc, mode, selected_name)
        try:
            return _create_completed_local_controlnet_job(raw, mode, fallback_name, uid, options, reason)
        except Exception as fallback_exc:
            raise ValueError(reason + ' Local fallback also failed: ' + str(fallback_exc)) from fallback_exc
    prompt_id = str(queued.get('prompt_id') or '').strip()
    if not prompt_id:
        reason = 'ComfyUI did not return a prompt id for the ControlNet map build.'
        try:
            return _create_completed_local_controlnet_job(raw, mode, fallback_name, uid, options, reason)
        except Exception as fallback_exc:
            raise ValueError(reason + ' Local fallback also failed: ' + str(fallback_exc)) from fallback_exc

    job_id = f'controlmap_{uuid4().hex}'
    job = create_long_task(CONTROLNET_MAP_NAMESPACE, {
        'job_id': job_id,
        'uid': str(uid or 'primary'),
        'mode': mode,
        'node_name': selected_name,
        'prompt_id': prompt_id,
        'started_at': time.time(),
        'state': 'queued',
        'message': f'Queued {mode} map build. First run may download or warm the backend model.',
        'notes': [f'Queued {mode} map build with {selected_name}.'],
        'backend': 'comfy_aux',
        'node_name': selected_name,
        'fallback': False,
        'settings': options or {},
        'source_path': str(local_path),
    }, prefix='controlmap')
    return job


async def _resolve_controlnet_aux_map_job(adapter: ComfyBackendAdapter, job: dict) -> dict:
    prompt_id = str(job.get('prompt_id') or '').strip()
    mode = str(job.get('mode') or '').strip().lower()
    node_name = str(job.get('node_name') or '').strip()
    elapsed = max(0.0, time.time() - float(job.get('started_at') or time.time()))

    history = await adapter.get_history(prompt_id)
    history_entry = history.get(prompt_id) if isinstance(history, dict) else None
    images = _extract_history_images(history_entry)
    comfy_error = _extract_comfy_error_message(history_entry)
    if comfy_error:
        friendly = _friendly_controlnet_error(comfy_error, mode, node_name)
        source_path = Path(str(job.get('source_path') or ''))
        if source_path.exists():
            try:
                raw = source_path.read_bytes()
                fallback_job = _create_completed_local_controlnet_job(raw, mode, source_path.name, str(job.get('uid') or 'primary'), job.get('settings') or {}, friendly)
                job.update(fallback_job)
                job['notes'] = [friendly, 'ComfyUI failed, so Neo used the local fallback map builder.'] + list(fallback_job.get('notes') or [])
                job['elapsed'] = elapsed
                return job
            except Exception as fallback_exc:
                friendly = friendly + ' Local fallback also failed: ' + str(fallback_exc)
        job.update({'state': 'error', 'message': friendly, 'error': comfy_error, 'elapsed': elapsed, 'backend': job.get('backend') or 'comfy_aux', 'fallback': False})
        return job
    if images:
        image = images[0]
        view_url = _build_download_generation_output_url(adapter, image.get('filename') or '', image.get('subfolder') or '', image.get('type') or 'output')
        output_bytes = await _download_output_bytes(view_url, timeout_sec=60)
        output_bytes = _maybe_invert_image_bytes(output_bytes, _boolish((job.get('settings') or {}).get('invert_map'), False))
        preview_data_url = 'data:image/png;base64,' + base64.b64encode(output_bytes).decode('ascii')
        job.update({
            'state': 'completed',
            'filename': image.get('filename') or f'{mode}_map.png',
            'output_filename': image.get('filename') or f'{mode}_map.png',
            'output_subfolder': image.get('subfolder') or 'neo_studio/control_maps',
            'output_type': image.get('type') or 'output',
            'output_url': view_url,
            'preview_data_url': preview_data_url,
            'message': f'Built {mode} map with {node_name}.',
            'notes': [f"Built {mode} map with {node_name}. Saved to ComfyUI output/{image.get('subfolder') or 'neo_studio/control_maps'}."],
            'backend': 'comfy_aux',
            'node_name': node_name,
            'fallback': False,
        })
        return job

    queue_state = await adapter.get_queue()
    prompt_state = _queue_prompt_state(queue_state, prompt_id) or ''
    if prompt_state == 'queued':
        state = 'queued'
        message = f'{mode.title()} map is queued in ComfyUI…'
    elif prompt_state == 'running':
        state = 'running'
        message = f'Building {mode} map…'
    else:
        state = 'running'
        message = f'Building {mode} map…'

    if elapsed >= 45:
        message = f'{mode.title()} map is still running. ComfyUI may be downloading or warming the required model on first run.'
        state = 'warming'
    if elapsed >= 150:
        message = f'{mode.title()} map is taking longer than usual. The backend may still be downloading the model or preparing the node.'
        state = 'long_running'
    if elapsed >= 420:
        message = f'{mode.title()} map is still not ready. Neo stopped waiting, but ComfyUI may still be working in the background.'
        state = 'timeout'

    job.update({'state': state, 'message': message, 'elapsed': elapsed})
    return job



@router.post('/api/generation/controlnet/batch-maps/start')
async def api_generation_controlnet_batch_maps_start(
    mode: str = Form(...),
    detect_resolution: str = Form('768'),
    safe_mode: str = Form('true'),
    canny_low: str = Form('100'),
    canny_high: str = Form('200'),
    openpose_body: str = Form('true'),
    openpose_hand: str = Form('true'),
    openpose_face: str = Form('false'),
    depth_model: str = Form('auto'),
    invert_map: str = Form('false'),
    fit_mode: str = Form('contain'),
    skip_existing: str = Form('true'),
    build_zip: str = Form('true'),
    images: list[UploadFile] = File(...),
):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        if not images:
            return json_error('Upload at least one image for batch map generation.', 400)
        batch_id = f'controlbatch_{uuid4().hex}'
        out_dir = _controlnet_batch_output_dir(batch_id)
        source_dir = out_dir / 'source'
        source_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for index, image in enumerate(images, start=1):
            raw = await image.read()
            if not raw:
                continue
            original = image.filename or f'image_{index}.png'
            ext = _guess_image_ext(original, image.content_type or '')
            src_name = f'{index:04d}_{safe_name(Path(original).stem)[:72]}{ext}'
            src_path = source_dir / src_name
            src_path.write_bytes(raw)
            entries.append({'index': index, 'original_name': original, 'source_filename': src_name, 'source_path': str(src_path), 'state': 'queued'})
        if not entries:
            return json_error('No readable image files were uploaded.', 400)
        options = {
            'detect_resolution': detect_resolution,
            'safe_mode': safe_mode,
            'canny_low': canny_low,
            'canny_high': canny_high,
            'openpose_body': openpose_body,
            'openpose_hand': openpose_hand,
            'openpose_face': openpose_face,
            'depth_model': depth_model,
            'invert_map': invert_map,
            'fit_mode': fit_mode,
            'skip_existing': skip_existing,
            'build_zip': build_zip,
        }
        norm_mode, norm_options = _normalize_controlnet_map_mode(mode, dict(options))
        job = create_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, {
            'job_id': batch_id,
            'batch_id': batch_id,
            'mode': norm_mode,
            'requested_mode': mode,
            'settings': norm_options,
            'state': 'queued',
            'message': f'Queued batch map generation for {len(entries)} image(s).',
            'total': len(entries),
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'entries': entries,
            'notes': ['Batch maps are saved beside a JSON manifest and optional ZIP.'],
        }, prefix='controlbatch')
        _write_controlnet_batch_manifest(batch_id, job)
        asyncio.create_task(_run_controlnet_batch_map_job(batch_id))
        return JSONResponse({'ok': True, 'batch_id': batch_id, 'job_id': batch_id, 'state': job.get('state') or 'queued', 'message': job.get('message') or '', 'total': len(entries), 'status_url': f'/api/generation/controlnet/batch-maps/status/{batch_id}'})
    except Exception as exc:
        logger.exception('Could not start ControlNet batch map generation')
        return json_error(f'Could not start ControlNet batch map generation: {exc}', 500)


@router.get('/api/generation/controlnet/batch-maps/status/{batch_id}')
async def api_generation_controlnet_batch_maps_status(batch_id: str):
    job = get_long_task(CONTROLNET_BATCH_MAP_NAMESPACE, str(batch_id or '').strip())
    if not job:
        return json_error('ControlNet batch map job not found.', 404)
    zip_path = Path(str(job.get('zip_path') or ''))
    return JSONResponse({
        'ok': True,
        'batch_id': job.get('batch_id') or batch_id,
        'job_id': job.get('job_id') or batch_id,
        'state': job.get('state') or 'running',
        'message': job.get('message') or '',
        'mode': job.get('mode') or '',
        'settings': job.get('settings') or {},
        'total': job.get('total') or 0,
        'completed': job.get('completed') or 0,
        'failed': job.get('failed') or 0,
        'skipped': job.get('skipped') or 0,
        'current_index': job.get('current_index') or 0,
        'current_name': job.get('current_name') or '',
        'entries': job.get('entries') or [],
        'notes': job.get('notes') or [],
        'zip_url': job.get('zip_url') or (f'/api/generation/controlnet/batch-maps/download/{batch_id}' if zip_path.exists() else ''),
        'manifest_url': f'/api/generation/controlnet/batch-maps/manifest/{batch_id}',
    })


@router.get('/api/generation/controlnet/batch-maps/manifest/{batch_id}')
async def api_generation_controlnet_batch_maps_manifest(batch_id: str):
    path = _controlnet_batch_manifest_path(str(batch_id or '').strip())
    if not path.exists():
        return json_error('ControlNet batch manifest not found.', 404)
    return FileResponse(path, media_type='application/json', filename='manifest.json')


@router.get('/api/generation/controlnet/batch-maps/download/{batch_id}')
async def api_generation_controlnet_batch_maps_download(batch_id: str):
    path = _controlnet_batch_zip_path(str(batch_id or '').strip())
    if not path.exists():
        return json_error('ControlNet batch ZIP is not ready yet.', 404)
    return FileResponse(path, media_type='application/zip', filename=f'{safe_name(batch_id)}_controlnet_maps.zip')

@router.post('/api/generation/controlnet/build-map/start')
async def api_generation_controlnet_build_map_start(
    mode: str = Form(...),
    uid: str = Form('primary'),
    detect_resolution: str = Form('768'),
    safe_mode: str = Form('true'),
    canny_low: str = Form('100'),
    canny_high: str = Form('200'),
    openpose_body: str = Form('true'),
    openpose_hand: str = Form('true'),
    openpose_face: str = Form('false'),
    depth_model: str = Form('auto'),
    invert_map: str = Form('false'),
    save_intermediate: str = Form('true'),
    fit_mode: str = Form('contain'),
    start_percent: str = Form('0'),
    end_percent: str = Form('1'),
    image: UploadFile = File(...),
):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        raw = await image.read()
        if not raw:
            return json_error('Upload an image first.', 400)
        options = {
            'detect_resolution': detect_resolution,
            'safe_mode': safe_mode,
            'canny_low': canny_low,
            'canny_high': canny_high,
            'openpose_body': openpose_body,
            'openpose_hand': openpose_hand,
            'openpose_face': openpose_face,
            'depth_model': depth_model,
            'invert_map': invert_map,
            'save_intermediate': save_intermediate,
            'fit_mode': fit_mode,
            'start_percent': start_percent,
            'end_percent': end_percent,
        }
        mode, options = _normalize_controlnet_map_mode(mode, options)
        job = await _start_controlnet_aux_map_job(adapter, raw, mode, image.filename or f'{uid or mode}.png', uid=uid, options=options)
        return JSONResponse({
            'ok': True,
            'job_id': job.get('job_id') or '',
            'uid': job.get('uid') or 'primary',
            'mode': job.get('mode') or '',
            'state': job.get('state') or 'queued',
            'message': job.get('message') or '',
            'notes': job.get('notes') or [],
            'backend': job.get('backend') or 'comfy_aux',
            'node_name': job.get('node_name') or '',
            'fallback': bool(job.get('fallback') or False),
            'settings': job.get('settings') or {},
        })
    except Exception as exc:
        logger.exception('Could not start ControlNet map build')
        return json_error(f'Could not start ControlNet map build: {exc}', 500)


@router.get('/api/generation/controlnet/build-map/status/{job_id}')
async def api_generation_controlnet_build_map_status(job_id: str):
    job = get_long_task(CONTROLNET_MAP_NAMESPACE, str(job_id or '').strip())
    if not job:
        return json_error('ControlNet map job not found.', 404)
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        if str(job.get('state') or '') != 'completed':
            job = await _resolve_controlnet_aux_map_job(adapter, job)
        return JSONResponse({
            'ok': True,
            'job_id': job.get('job_id') or '',
            'uid': job.get('uid') or 'primary',
            'mode': job.get('mode') or '',
            'state': job.get('state') or 'running',
            'message': job.get('message') or '',
            'notes': job.get('notes') or [],
            'filename': job.get('filename') or '',
            'output_filename': job.get('output_filename') or job.get('filename') or '',
            'output_subfolder': job.get('output_subfolder') or '',
            'output_type': job.get('output_type') or '',
            'output_url': job.get('output_url') or '',
            'preview_data_url': job.get('preview_data_url') or '',
            'elapsed': job.get('elapsed') or 0,
            'backend': job.get('backend') or 'comfy_aux',
            'node_name': job.get('node_name') or '',
            'fallback': bool(job.get('fallback') or False),
            'settings': job.get('settings') or {},
        })
    except Exception as exc:
        logger.exception('Could not poll ControlNet map job')
        job.update({'state': 'error', 'message': f'Could not poll ControlNet map job: {exc}'})
        return json_error(job.get('message') or 'Could not poll ControlNet map job.', 500)


async def _start_tag_assist_job(adapter: ComfyBackendAdapter, raw: bytes, threshold: float, filter_tags: str, fallback_name: str) -> dict:
    candidates = ['DeepDanbooruCaption']
    selected_name = ''
    selected_info = None
    for node_name in candidates:
        try:
            info = await adapter.get_object_info(node_name)
        except Exception:
            info = {}
        if isinstance(info, dict) and node_name in info:
            info = info.get(node_name)
        if isinstance(info, dict) and info:
            selected_name = node_name
            selected_info = info
            break
    if not selected_name:
        raise ValueError('DeepDanbooruCaption was not detected in the connected ComfyUI backend.')

    preview_node_name = ''
    preview_node_info = None
    for node_name in ['PreviewAny', 'PreviewTextNode', 'ShowText|pysssss', 'Show Text', 'ShowText']:
        try:
            info = await adapter.get_object_info(node_name)
        except Exception:
            info = {}
        if isinstance(info, dict) and node_name in info:
            info = info.get(node_name)
        if isinstance(info, dict) and info:
            preview_node_name = node_name
            preview_node_info = info
            break
    if not preview_node_name:
        raise ValueError('Neo could not find a text preview/output node in ComfyUI for Tag Assist. Update ComfyUI so PreviewAny is available, or install a text preview node.')

    ensure_generation_dirs()
    source_name = f'tagassist_{safe_name(Path(fallback_name or "tagassist").stem)[:48]}.png'
    local_path = GENERATION_INPUT_DIR / source_name
    local_path.write_bytes(raw)
    remote = await adapter.upload_image(raw, local_path.name)
    remote_name = _remote_path_from_upload_result(remote, local_path.name)

    graph = {
        '1': {
            'class_type': 'LoadImage',
            'inputs': {
                'image': remote_name,
                'upload': 'image',
            },
        },
        '2': {
            'class_type': selected_name,
            'inputs': _tag_assist_inputs(_object_required_inputs(selected_info), ['1', 0], float(threshold), filter_tags),
        },
    }
    if preview_node_name:
        graph['3'] = {
            'class_type': preview_node_name,
            'inputs': _tag_assist_output_inputs(_object_required_inputs(preview_node_info), ['2', 0]),
        }

    queued = await adapter.queue_prompt(graph)
    prompt_id = str(queued.get('prompt_id') or '').strip()
    if not prompt_id:
        raise ValueError('ComfyUI did not return a prompt id for Tag Assist.')

    return create_long_task(TAG_ASSIST_NAMESPACE, {
        'job_id': f'tagassist_{uuid4().hex}',
        'prompt_id': prompt_id,
        'started_at': time.time(),
        'state': 'queued',
        'threshold': float(threshold),
        'filter_tags': str(filter_tags or '').strip(),
        'node_name': selected_name,
        'message': 'Queued Tag Assist. First run may download or warm the caption model.',
        'notes': [f'Queued Tag Assist with {selected_name}.'],
        'preview_node_name': preview_node_name,
    }, prefix='tagassist')


async def _resolve_tag_assist_job(adapter: ComfyBackendAdapter, job: dict) -> dict:
    prompt_id = str(job.get('prompt_id') or '').strip()
    node_name = str(job.get('node_name') or '').strip()
    elapsed = max(0.0, time.time() - float(job.get('started_at') or time.time()))

    history = await adapter.get_history(prompt_id)
    history_entry = history.get(prompt_id) if isinstance(history, dict) else None
    texts = _extract_history_texts(history_entry)
    caption = next((item for item in texts if str(item or '').strip()), '')
    if caption:
        tags = _parse_tag_caption(caption)
        job.update({
            'state': 'completed',
            'caption': caption,
            'tags': tags,
            'message': f'Tag Assist finished with {len(tags)} tag{"s" if len(tags) != 1 else ""}.',
            'notes': [f'Tag Assist finished with {node_name}.'],
            'elapsed': elapsed,
        })
        return job
    if isinstance(history_entry, dict) and isinstance(history_entry.get('outputs'), dict):
        job.update({
            'state': 'completed',
            'caption': '',
            'tags': [],
            'message': 'Tag Assist finished, but the backend did not return any clean tags.',
            'notes': [f'Tag Assist finished with {node_name}, but no clean tags were returned.'],
            'elapsed': elapsed,
        })
        return job

    queue_state = await adapter.get_queue()
    prompt_state = _queue_prompt_state(queue_state, prompt_id) or ''
    if prompt_state == 'queued':
        state = 'queued'
        message = 'Tag Assist is queued in ComfyUI…'
    else:
        state = 'running'
        message = 'Analyzing image tags…'

    if elapsed >= 45:
        message = 'Tag Assist is still running. ComfyUI may be downloading or warming the caption model on first run.'
        state = 'warming'
    if elapsed >= 150:
        message = 'Tag Assist is taking longer than usual. The backend may still be downloading the tagger model or preparing the node.'
        state = 'long_running'
    if elapsed >= 420:
        message = 'Tag Assist is still not ready. Neo stopped waiting, but ComfyUI may still be working in the background.'
        state = 'timeout'

    job.update({'state': state, 'message': message, 'elapsed': elapsed})
    return job


@router.post('/api/generation/tag-assist/start')
async def api_generation_tag_assist_start(
    threshold: float = Form(0.35),
    filter_tags: str = Form(''),
    image: UploadFile = File(...),
):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        raw = await image.read()
        if not raw:
            return json_error('Upload an image first.', 400)
        job = await _start_tag_assist_job(adapter, raw, float(threshold), filter_tags, image.filename or 'tagassist.png')
        return JSONResponse({
            'ok': True,
            'job_id': job.get('job_id') or '',
            'state': job.get('state') or 'queued',
            'message': job.get('message') or '',
            'notes': job.get('notes') or [],
        })
    except Exception as exc:
        logger.exception('Could not start Tag Assist')
        return json_error(f'Could not start Tag Assist: {exc}', 500)


@router.get('/api/generation/tag-assist/status/{job_id}')
async def api_generation_tag_assist_status(job_id: str):
    job = get_long_task(TAG_ASSIST_NAMESPACE, str(job_id or '').strip())
    if not job:
        return json_error('Tag Assist job not found.', 404)
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        if str(job.get('state') or '') != 'completed':
            job = await _resolve_tag_assist_job(adapter, job)
        return JSONResponse({
            'ok': True,
            'job_id': job.get('job_id') or '',
            'state': job.get('state') or 'running',
            'message': job.get('message') or '',
            'notes': job.get('notes') or [],
            'caption': job.get('caption') or '',
            'tags': job.get('tags') or [],
            'elapsed': job.get('elapsed') or 0,
        })
    except Exception as exc:
        logger.exception('Could not poll Tag Assist job')
        job.update({'state': 'error', 'message': f'Could not poll Tag Assist job: {exc}'})
        return json_error(job.get('message') or 'Could not poll Tag Assist job.', 500)


@router.post('/api/generation/dependency-audit')
async def api_generation_dependency_audit(request: Request):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    draft = payload.get('draft') if isinstance(payload, dict) and isinstance(payload.get('draft'), dict) else {}
    try:
        audit = await build_generation_dependency_audit(adapter, draft)
    except Exception as exc:
        logger.exception('Could not build generation dependency audit')
        return json_error(f'Could not build dependency audit: {exc}', 500)
    return JSONResponse(audit)


@router.get('/api/generation/job/{job_id}')
async def api_generation_job(job_id: str):
    job = get_generation_job(job_id)
    if not job:
        return json_error('Generation job not found.', 404)
    if _job_needs_finalization(job):
        try:
            refreshed = await _refresh_generation_job_from_backend(job_id)
        except Exception as exc:
            refreshed = _generation_runtime_error_update(
                job,
                job_id,
                'Generation job refresh failed safely. Neo stayed open; check neo_generation_runtime.log.',
                exc,
                phase='job_refresh_failed',
            )
    else:
        refreshed = job
    return JSONResponse({'ok': True, 'job': refreshed or job})


@router.get('/api/generation/history')
async def api_generation_history(limit: int = 12):
    return JSONResponse({'ok': True, 'jobs': list_generation_jobs(limit=limit)})




_RETIRED_GENERATION_FEATURE_PREFIXES = (
    'regional_',
    'regionalPrompt',
    'expression_',
    'expression_editor_',
    'expressionEditor',
    'expression_sample_',
    'reference_match_',
    'referenceMatch',
    'cleanup_prep_',
    'cleanupPrep',
)

_RETIRED_GENERATION_FEATURE_KEYS = {
    'regionalBackendCapabilities',
    'regional_prompt_regions',
    'regional_backend_capabilities',
    'regional_prompt_enabled',
    'expression_editor_pass',
    'expression_editor_enabled',
    'expression_pass',
    'expression_enabled',
    'expression_editor',
    'expressionEditor',
    'reference_match_enabled',
    'reference_match',
    'referenceMatch',
    'cleanup_prep_enabled',
    'cleanup_prep',
    'cleanupPrep',
}

_RETIRED_PREVIEW_ACTION_TYPES = {
    'expression',
    'expression_editor',
    'reference_match',
    'cleanup_prep',
    'regional',
    'regional_prompt',
}


def _is_retired_generation_key(key: object) -> bool:
    key_text = str(key)
    return key_text in _RETIRED_GENERATION_FEATURE_KEYS or any(
        key_text.startswith(prefix) for prefix in _RETIRED_GENERATION_FEATURE_PREFIXES
    )


def _strip_retired_generation_fields(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if _is_retired_generation_key(key):
                continue
            cleaned[key] = _strip_retired_generation_fields(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_retired_generation_fields(item) for item in value]
    return value


def _sanitize_preview_action_contract(payload: dict) -> None:
    preview_action = payload.get('_neo_preview_action')
    if not isinstance(preview_action, dict):
        return
    action_type = str(preview_action.get('action_type') or '').strip().lower()
    if action_type in _RETIRED_PREVIEW_ACTION_TYPES:
        payload.pop('_neo_preview_action', None)
        if action_type in {'expression', 'expression_editor'}:
            payload['detailer_output_pass'] = False
        return
    payload['_neo_preview_action'] = _strip_retired_generation_fields(preview_action)


def _sanitize_builder_contract(payload: dict) -> None:
    contract = payload.get('_neo_builder_contract')
    if not isinstance(contract, dict):
        return
    contract = _strip_retired_generation_fields(contract)
    preview_action = contract.get('preview_action')
    if isinstance(preview_action, dict):
        action_type = str(preview_action.get('action_type') or '').strip().lower()
        if action_type in _RETIRED_PREVIEW_ACTION_TYPES:
            contract.pop('preview_action', None)
        else:
            contract['preview_action'] = _strip_retired_generation_fields(preview_action)
    payload['_neo_builder_contract'] = contract



def _sanitize_generation_payload_removed_features(payload: dict | None) -> dict:
    """Stage 6 backend guardrail for retired Image Tab sections.

    Retired UI sections are stripped at the route boundary before Scene
    Director adaptation or workflow compilation. The sanitizer is centralized
    in contracts/retired_image_sections.py so frontend payload envelopes,
    draft save/load, and backend queue routes follow one retirement map.
    """
    payload, removed = sanitize_image_payload_for_retired_sections(payload if isinstance(payload, dict) else {})
    payload['_neo_payload_sanitized'] = True
    payload['_neo_payload_sanitizer_version'] = 'stage6_retired_sections_v1'
    payload['_neo_backend_builder_cleanup'] = True
    payload['_neo_stage6_removed_retired_sections_count'] = len(set(removed))
    return payload


@router.post('/api/generation/image-upscale')
async def api_generation_image_upscale(request: Request, background_tasks: BackgroundTasks):
    adapter, session, error = _image_profile_or_error()
    if error:
        return error

    form = await request.form()
    settings_json = str(form.get('settings_json') or '{}')
    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a JSON object.')
    except Exception as exc:
        return json_error(f'Invalid image-upscale payload: {exc}', 400)

    payload, image_command_envelope = flatten_image_payload_envelope(payload)
    payload = stamp_external_extension_payload_contract(payload, external_registry=_build_external_registry_for_generation_payload(payload, surface='image'))
    payload = _sanitize_generation_payload_removed_features(payload)
    if image_command_envelope:
        payload['_neo_command_envelope'] = image_command_envelope.get('_neo_command_envelope') or payload.get('_neo_command_envelope')

    image_files = []
    for key, value in form.multi_items():
        if key == 'image_files' and hasattr(value, 'filename'):
            image_files.append(value)
    if not image_files:
        single_image = form.get('image_file')
        if hasattr(single_image, 'filename'):
            image_files.append(single_image)
    if not image_files:
        return json_error('Pick at least one source image for Image Upscale.', 400)

    restore_assist = str(payload.get('image_upscale_restore_assist') or 'off').strip().lower()
    restore_model = str(payload.get('image_upscale_restore_model') or '').strip()

    if restore_assist == 'codeformer':
        if not restore_model:
            return json_error('Choose a CodeFormer restore model or turn restore assist off.', 400)
        try:
            restore_loader = await adapter.get_object_info('FaceRestoreModelLoader')
            restore_apply = await adapter.get_object_info('FaceRestoreCFWithModel')
            restore_loader_ok = isinstance(restore_loader, dict) and (restore_loader.get('FaceRestoreModelLoader') or restore_loader)
            restore_apply_ok = isinstance(restore_apply, dict) and (restore_apply.get('FaceRestoreCFWithModel') or restore_apply)
            if not (restore_loader_ok and restore_apply_ok):
                raise ValueError('CodeFormer restore nodes are not available in this ComfyUI backend yet.')
        except ValueError as exc:
            return json_error(str(exc), 400)
        except Exception as exc:
            return json_error(f'Could not validate CodeFormer restore support: {exc}', 502)

    profile = get_profile('image', session.get('profile_id') or None) or {
        'backend_type': 'comfyui',
        'name': session.get('profile_name') or 'ComfyUI',
        'base_url': session.get('base_url') or '',
    }

    queued_jobs = []
    errors = []
    for index, upload in enumerate(image_files, start=1):
        try:
            saved_source = await _save_upload(upload if hasattr(upload, 'filename') else None, f'upscale_{index}')
            if not saved_source:
                raise ValueError('Could not read one of the source images.')
            item_payload = dict(payload)
            item_payload['source_image_name'] = await _upload_saved(adapter, saved_source)
            workflow, normalized_payload, compile_notes = build_image_workflow(item_payload, command='image_upscale')
            queued = await adapter.queue_prompt(workflow)
            job = create_generation_job(
                payload=normalized_payload,
                backend_profile=profile,
                prompt_id=str(queued.get('prompt_id') or ''),
                queue_number=queued.get('number'),
                compile_notes=compile_notes,
                workflow_graph=workflow,
            )
            if queued.get('node_errors'):
                job = update_generation_job(job['id'], {
                    'state': 'error',
                    'status_text': 'ComfyUI reported node validation errors.',
                    'error': json.dumps(queued.get('node_errors'), ensure_ascii=False),
                }) or job
            else:
                background_tasks.add_task(_background_finalize_generation_job, str(job.get('id') or job.get('job_id') or ''))
            queued_jobs.append(job)
        except Exception as exc:
            logger.exception('Could not queue Image Upscale item %s', index)
            errors.append({'index': index, 'name': getattr(upload, 'filename', f'image_{index}'), 'error': str(exc)})

    if not queued_jobs:
        return json_error(errors[0]['error'] if errors else 'Could not queue Image Upscale.', 502)

    suffix = '' if len(queued_jobs) == 1 else 's'
    return JSONResponse({
        'ok': True,
        'jobs': queued_jobs,
        'queued_count': len(queued_jobs),
        'failed': errors,
        'message': f'Queued Image Upscale for {len(queued_jobs)} image{suffix}.',
    })


def _sync_scene_director_preview_execution_state(payload: dict, request_mode: str) -> list[str]:
    """Keep Scene Director raw state and preview-action execution state explicit.

    Preview actions can originate from a txt2img image while executing as img2img.
    The old payload left scene_director_state.mode as txt2img, which made later
    workflow/debug reads ambiguous. Preserve the source mode, but publish the
    effective execution mode visibly.
    """
    if not isinstance(payload, dict):
        return []
    notes: list[str] = []
    state = payload.get('scene_director_state')
    if not isinstance(state, dict):
        return notes
    raw_mode = normalize_generation_mode(state.get('mode') or request_mode)
    effective_mode = normalize_generation_mode(request_mode)
    preview_action = payload.get('_neo_preview_action') if isinstance(payload.get('_neo_preview_action'), dict) else {}
    execution_mode = normalize_generation_mode(preview_action.get('execution_mode') or payload.get('_neo_effective_mode') or effective_mode)
    source_mode = normalize_generation_mode(preview_action.get('save_lane') or payload.get('save_mode_override') or raw_mode)
    state['_neo_source_mode'] = source_mode
    state['_neo_execution_mode'] = execution_mode
    state['_neo_mode_sync_policy'] = 'source_preserved_execution_visible'
    if raw_mode != execution_mode:
        state['_neo_raw_mode'] = raw_mode
        state['mode'] = execution_mode
        payload['_neo_scene_director_source_mode'] = source_mode
        payload['_neo_scene_director_execution_mode'] = execution_mode
        payload['_neo_scene_director_mode_sync'] = f'{raw_mode}->{execution_mode}'
        notes.append(f'Scene Director mode sync: preserved source {source_mode}, compiled execution {execution_mode}.')
    else:
        payload['_neo_scene_director_execution_mode'] = execution_mode
    return notes


async def _first_available_object_info(adapter, aliases: list[str]) -> str:
    for alias in aliases:
        try:
            info = await adapter.get_object_info(alias)
            if isinstance(info, dict) and (info.get(alias) or info):
                return alias
        except Exception:
            continue
    return ''

async def _validate_gguf_workflow_guardrails(adapter, payload: dict, request_mode: str) -> list[str]:
    """Phase 9 guardrails: block invalid Flux/Qwen GGUF states before workflow compile."""
    if not isinstance(payload, dict):
        return []
    family = str(payload.get('family') or payload.get('_neo_effective_family') or '').strip().lower()
    if family in {'qwen', 'qwen_image'}:
        family = 'qwen_image_edit'
    model_source = str(payload.get('model_source') or payload.get('_neo_effective_model_source') or '').strip().lower()
    is_flux = family == 'flux'
    is_qwen = family == 'qwen_image_edit'
    is_gguf = model_source == 'gguf' or is_flux or is_qwen
    if not is_gguf:
        return []

    clip_type = 'qwen_image' if is_qwen else ('flux' if is_flux else str(payload.get('gguf_clip_type') or '').strip().lower())
    clip_mode = 'single' if clip_type == 'qwen_image' else ('single' if str(payload.get('gguf_clip_mode') or '').strip().lower() == 'single' else 'dual')
    label = 'Qwen' if is_qwen else ('Flux' if is_flux else 'GGUF')
    blockers: list[str] = []
    notes: list[str] = []

    if not str(payload.get('gguf_unet') or payload.get('_neo_effective_gguf_unet') or '').strip():
        blockers.append(f'{label} GGUF needs a GGUF model before queueing.')
    if not str(payload.get('gguf_clip_primary') or payload.get('_neo_effective_gguf_clip_primary') or '').strip():
        blockers.append(f'{label} GGUF needs the primary encoder before queueing.')
    if clip_mode == 'dual' and not str(payload.get('gguf_clip_secondary') or payload.get('_neo_effective_gguf_clip_secondary') or '').strip():
        blockers.append('Flux GGUF needs the second encoder before queueing.')
    if not str(payload.get('vae') or '').strip():
        blockers.append(f'{label} GGUF needs a VAE before queueing.')

    unet_loader = await _first_available_object_info(adapter, ['UnetLoaderGGUF', 'LoaderGGUF'])
    if not unet_loader:
        blockers.append('ComfyUI did not expose LoaderGGUF/UnetLoaderGGUF. Install or enable the GGUF node pack before queueing.')
    clip_loader = await _first_available_object_info(adapter, ['DualCLIPLoaderGGUF'] if clip_mode == 'dual' else ['CLIPLoaderGGUF', 'ClipLoaderGGUF'])
    if not clip_loader:
        if clip_mode == 'dual':
            blockers.append('Flux GGUF needs DualCLIPLoaderGGUF from ComfyUI before queueing.')
        else:
            blockers.append('Qwen GGUF needs CLIPLoaderGGUF/ClipLoaderGGUF from ComfyUI before queueing.')
    vae_loader = await _first_available_object_info(adapter, ['VaeGGUF', 'VAELoaderGGUF'])
    if vae_loader:
        notes.append(f'GGUF guardrail: using {unet_loader or "missing UNet loader"} + {clip_loader or "missing CLIP loader"} + {vae_loader}.')
    else:
        notes.append('GGUF guardrail warning: no GGUF VAE loader alias was reported; compiler may use fallback VAE behavior if available.')

    source_fields = payload.get('source_image_fields') if isinstance(payload.get('source_image_fields'), list) else []
    has_uploaded_qwen_source = bool(str(payload.get('source_image__2_name') or payload.get('source_image__3_name') or '').strip())
    qwen_uses_image_context = is_qwen and (request_mode in {'img2img', 'inpaint'} or bool(source_fields) or has_uploaded_qwen_source)
    mmproj = str(payload.get('gguf_mmproj') or payload.get('_neo_effective_gguf_mmproj') or '').strip()
    if qwen_uses_image_context and not mmproj:
        blockers.append('Qwen image/reference workflows need a matching mmproj sidecar. Put it in ComfyUI models/mmproj or text_encoders, then refresh the catalog.')
    if is_qwen and str(payload.get('gguf_clip_mode') or '').strip().lower() == 'dual':
        notes.append('Qwen guardrail auto-scope: Qwen uses the single-encoder GGUF path; secondary encoder state is ignored.')

    if (is_qwen or is_flux) and (payload.get('ipadapter_units') or payload.get('scene_director_ipadapter_units')):
        blockers.append(f'{label} GGUF currently blocks IP-Adapter. Disable IP-Adapter or switch to an SDXL checkpoint workflow.')

    if blockers:
        payload['_neo_gguf_guardrail_status'] = 'blocked'
        payload['_neo_gguf_guardrail_blockers'] = blockers
        payload['_neo_gguf_guardrail_version'] = 'phase9_backend_guardrails'
        raise ValueError(blockers[0])
    payload['_neo_gguf_guardrail_status'] = 'pass'
    payload['_neo_gguf_guardrail_family'] = family
    payload['_neo_gguf_guardrail_version'] = 'phase9_backend_guardrails'
    return notes


@router.post('/api/generation/queue')
async def api_generation_queue(request: Request, background_tasks: BackgroundTasks):
    adapter, session, error = _image_profile_or_error()
    if error:
        return error

    form = await request.form()
    settings_json = str(form.get('settings_json') or '{}')
    source_image = form.get('source_image')
    mask_image = form.get('mask_image')
    control_image = form.get('control_image')
    ipadapter_image = form.get('ipadapter_image')
    dynamic_uploads = {}
    for key, value in form.multi_items():
        if key.startswith('ipadapter_image__') and hasattr(value, 'filename'):
            existing = dynamic_uploads.get(key)
            if existing is None:
                dynamic_uploads[key] = [value]
            elif isinstance(existing, list):
                existing.append(value)
            else:
                dynamic_uploads[key] = [existing, value]
        elif key.startswith('control_image__') and hasattr(value, 'filename'):
            dynamic_uploads[key] = value
        elif key.startswith('source_image__') and hasattr(value, 'filename'):
            dynamic_uploads[key] = value

    try:
        payload = json.loads(settings_json or '{}')
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a JSON object.')
    except Exception as exc:
        return json_error(f'Invalid generation payload: {exc}', 400)

    payload, image_command_envelope = flatten_image_payload_envelope(payload)
    payload = stamp_external_extension_payload_contract(payload, external_registry=_build_external_registry_for_generation_payload(payload, surface='image'))
    payload = _sanitize_generation_payload_removed_features(payload)
    if image_command_envelope:
        payload['_neo_command_envelope'] = image_command_envelope.get('_neo_command_envelope') or payload.get('_neo_command_envelope')
    payload, scene_director_notes = scene_director_to_regional_payload(payload)

    request_mode = normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img')
    scene_director_notes = list(scene_director_notes or [])
    scene_director_notes.extend(_sync_scene_director_preview_execution_state(payload, request_mode))
    request_backend = normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard')
    # Phase 9 hygiene: LanPaint/inpaint backend is only compiled for true inpaint.
    # Raw UI state can keep its previous selection, but non-inpaint workflows must not inherit it.
    if request_mode in {'txt2img', 'img2img', 'outpaint'} and request_backend != 'standard':
        logger.info(
            'Generation payload cleanup | phase=9 | mode=%s forced inpaint_backend=%s -> standard',
            request_mode,
            payload.get('inpaint_backend') or '',
        )
        payload['inpaint_backend'] = 'standard'
        nested_payload = payload.get('inpaint_payload')
        if isinstance(nested_payload, dict):
            nested_payload['backend'] = 'standard'
        if request_mode == 'txt2img':
            payload.pop('inpaint_payload', None)

    logger.info(
        'Generation queue request received | mode=%s | family=%s | model_source=%s | inpaint_backend=%s | checkpoint=%s | gguf=%s | sampler=%s | scheduler=%s | batch_size=%s | prompt_chars=%s',
        payload.get('mode') or payload.get('workflow_type') or 'txt2img',
        payload.get('family') or '',
        payload.get('model_source') or '',
        payload.get('inpaint_backend') or '',
        payload.get('checkpoint') or '',
        payload.get('gguf_unet') or '',
        payload.get('sampler') or '',
        payload.get('scheduler') or '',
        payload.get('batch_size') or 1,
        len(str(payload.get('positive') or '')),
    )

    workflow = None
    normalized_payload = None
    compile_notes: list[str] = []
    pre_compile_notes: list[str] = list(scene_director_notes or [])

    try:
        if str(payload.get('client_id') or '').strip():
            adapter.client_id = str(payload.get('client_id')).strip()

        # Phase 10.7: retired feature payloads are stripped before workflow
        # compilation; legacy upload-only fields are ignored here as well.
        dynamic_uploads = {k: v for k, v in dynamic_uploads.items() if not str(k).startswith('regional_mask__')}

        saved_source = await _save_upload(source_image if hasattr(source_image, 'filename') else None, 'source')
        saved_mask = await _save_upload(mask_image if hasattr(mask_image, 'filename') else None, 'mask')
        saved_control = await _save_upload(control_image if hasattr(control_image, 'filename') else None, 'control')
        saved_ipadapter = await _save_upload(ipadapter_image if hasattr(ipadapter_image, 'filename') else None, 'ipadapter')
        require_preview_source_lock(payload, has_source_upload=bool(saved_source))
        saved_source, saved_mask, resize_notes = await _prepare_generation_source_assets(payload, saved_source, saved_mask)

        if saved_source:
            payload['source_image_name'] = await _upload_saved(adapter, saved_source)
        for source_key in ('source_image__2', 'source_image__3'):
            source_upload = dynamic_uploads.get(source_key)
            saved_extra_source = await _save_upload(source_upload if hasattr(source_upload, 'filename') else None, source_key.replace('__', '_'))
            if saved_extra_source:
                payload[f'{source_key}_name'] = await _upload_saved(adapter, saved_extra_source)
        if saved_mask:
            payload['mask_image_name'] = await _upload_saved(adapter, saved_mask)
        if saved_control:
            payload['control_image_name'] = await _upload_saved(adapter, saved_control)
        if saved_ipadapter:
            payload['ipadapter_image_name'] = await _upload_saved(adapter, saved_ipadapter)

        payload = merge_shared_inpaint_payload(payload)
        inpaint_payload = payload.get('inpaint_payload') if isinstance(payload.get('inpaint_payload'), dict) else {}
        if inpaint_payload and normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img') in {'inpaint', 'outpaint'}:
            composition = inpaint_payload.get('composition') or {}
            pre_compile_notes.append(
                f"Shared inpaint payload staged · backend {inpaint_payload.get('backend') or 'standard'} · guide {composition.get('guide_type') or 'none'} · source {composition.get('source_mode') or 'source_image'}."
            )

        if not pre_compile_notes:
            pre_compile_notes = list(resize_notes)
        else:
            pre_compile_notes = [*resize_notes, *pre_compile_notes]
        pre_compile_notes.extend(await _prepare_controlnet_units(adapter, payload, dynamic_uploads))
        pre_compile_notes.extend(await _prepare_ipadapter_units(adapter, payload, dynamic_uploads))
        pre_compile_notes.extend(await _prepare_scene_director_ipadapter_units(adapter, payload, dynamic_uploads))
        pre_compile_notes.extend(_normalize_scene_director_appearance_lock_payload(payload))
        pre_compile_notes.extend(await _configure_scene_director_node_selection(adapter, payload))
        pre_compile_notes.extend(prepare_detailer_assets_for_payload(payload))
        pre_compile_notes.extend(await _validate_gguf_workflow_guardrails(adapter, payload, request_mode))

        support_check = validate_generation_support(
            payload.get('family') or '',
            normalize_generation_mode(payload.get('mode') or payload.get('workflow_type') or 'txt2img'),
            normalize_inpaint_backend(payload.get('inpaint_backend') or 'standard'),
        )
        if not support_check.get('ok'):
            raise ValueError(str(support_check.get('message') or 'This family / mode combo is not available in this build.'))

        pre_compile_notes.extend(await _validate_generation_runtime_compatibility(adapter, payload))
        pre_compile_notes.extend(await _validate_res4lyf_preset_compatibility(adapter, payload))
        pre_compile_notes.extend(await _inject_refine_ultimate_runtime_hints(adapter, payload))

        if payload.get('ipadapter_units') or payload.get('scene_director_ipadapter_units'):
            try:
                clip_vision_loader = await adapter.get_object_info('CLIPVisionLoader')
                clip_vision_ok = isinstance(clip_vision_loader, dict) and (clip_vision_loader.get('CLIPVisionLoader') or clip_vision_loader)
                ip_units = [unit for unit in (payload.get('ipadapter_units') or []) if isinstance(unit, dict)]
                scene_ip_units = [unit for unit in (payload.get('scene_director_ipadapter_units') or []) if isinstance(unit, dict)]
                ip_units = [*ip_units, *scene_ip_units]
                has_faceid = any(str((unit or {}).get('mode') or 'standard').strip().lower() == 'faceid' for unit in ip_units)
                has_standard = any(str((unit or {}).get('mode') or 'standard').strip().lower() != 'faceid' for unit in ip_units)
                if has_faceid:
                    # Phase 10.3.8 hotfix:
                    # Do not hard-block FaceID just because ComfyUI object_info/capability cache
                    # fails to report one of the IPAdapter+ FaceID nodes. Some working portable
                    # ComfyUI installs expose FaceID nodes at queue/runtime but return incomplete
                    # object_info until the IPAdapter/Identity lane has been staged once.
                    # The graph builder uses IPAdapterUnifiedLoaderFaceID like the working Prep Identity Preset lane; let ComfyUI validate
                    # the graph and report the real node/model error instead of Neo rejecting a
                    # working setup up front.
                    faceid_probe_notes: list[str] = []
                    try:
                        ip_faceid_loader = await adapter.get_object_info('IPAdapterUnifiedLoaderFaceID')
                        if not (isinstance(ip_faceid_loader, dict) and (ip_faceid_loader.get('IPAdapterUnifiedLoaderFaceID') or ip_faceid_loader)):
                            faceid_probe_notes.append('IPAdapterUnifiedLoaderFaceID was not reported by object_info')
                    except Exception as probe_exc:
                        faceid_probe_notes.append(f'IPAdapterUnifiedLoaderFaceID probe failed: {probe_exc}')
                    try:
                        ip_faceid_apply = await adapter.get_object_info('IPAdapterFaceID')
                        if not (isinstance(ip_faceid_apply, dict) and (ip_faceid_apply.get('IPAdapterFaceID') or ip_faceid_apply)):
                            faceid_probe_notes.append('IPAdapterFaceID was not reported by object_info')
                    except Exception as probe_exc:
                        faceid_probe_notes.append(f'IPAdapterFaceID probe failed: {probe_exc}')
                    # The unified FaceID route is the source of truth. Do not require a separate
                    # IPAdapterInsightFaceLoader node because some working IPAdapter Plus installs hide it
                    # while IPAdapterUnifiedLoaderFaceID still works through the Identity Preset lane.
                    if not clip_vision_ok:
                        raise ValueError('FaceID mode is enabled, but CLIP Vision support is not available in this ComfyUI backend.')
                    if faceid_probe_notes:
                        pre_compile_notes.append('FaceID backend probe warning: ' + '; '.join(faceid_probe_notes) + '. Neo will still queue the graph because FaceID worked on this backend before; ComfyUI will report the exact runtime issue if a node/model is truly missing.')
                if has_standard:
                    ip_model_loader = await adapter.get_object_info('IPAdapterModelLoader')
                    ip_advanced = await adapter.get_object_info('IPAdapterAdvanced')
                    if not (clip_vision_ok and isinstance(ip_model_loader, dict) and (ip_model_loader.get('IPAdapterModelLoader') or ip_model_loader) and isinstance(ip_advanced, dict) and (ip_advanced.get('IPAdapterAdvanced') or ip_advanced)):
                        raise ValueError('IPAdapter custom nodes are not available in this ComfyUI backend yet. Install ComfyUI_IPAdapter_plus (or comfyorg/comfyui-ipadapter), add the IP-Adapter models + CLIP Vision models, then restart ComfyUI.')
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f'IPAdapter custom nodes are not ready on this backend: {exc}') from exc

        workflow, normalized_payload, compile_notes = build_image_workflow(payload, command=detect_image_workflow_command(payload))
        workflow, advanced_lane_notes = await _apply_res4lyf_advanced_sampler_lane(adapter, payload, workflow)
        workflow, normalized_payload, external_workflow_notes = apply_external_workflow_injection(workflow, normalized_payload)
        compile_notes = [*pre_compile_notes, *compile_notes, *advanced_lane_notes, *external_workflow_notes]
        _finalize_scene_director_appearance_lock_state_metadata(normalized_payload)
        _safe_write_generation_debug_json(GENERATION_LAST_PAYLOAD_PATH, normalized_payload)
        _safe_write_generation_debug_json(GENERATION_LAST_WORKFLOW_PATH, workflow)
        logger.info(
            'Generation workflow compiled | mode=%s | family=%s | model_source=%s | inpaint_backend=%s | checkpoint=%s | sampler=%s | scheduler=%s | batch_size=%s | size=%sx%s',
            normalized_payload.get('mode') or '',
            normalized_payload.get('family') or '',
            normalized_payload.get('model_source') or '',
            normalized_payload.get('inpaint_backend') or '',
            normalized_payload.get('checkpoint') or '',
            normalized_payload.get('sampler') or '',
            normalized_payload.get('scheduler') or '',
            normalized_payload.get('_neo_effective_batch_size') or normalized_payload.get('batch_size') or 1,
            normalized_payload.get('width') or '',
            normalized_payload.get('height') or '',
        )
        logger.info(
            'Generation effective workflow contract | mode=%s | family=%s | model_source=%s | backend=%s | lanpaint=%s | qwen=%s | scene_director_applied=%s | scene_skip=%s',
            normalized_payload.get('_neo_effective_mode') or normalized_payload.get('mode') or '',
            normalized_payload.get('_neo_effective_family') or normalized_payload.get('family') or '',
            normalized_payload.get('_neo_effective_model_source') or normalized_payload.get('model_source') or '',
            normalized_payload.get('_neo_effective_inpaint_backend') or normalized_payload.get('inpaint_backend') or '',
            bool(normalized_payload.get('_neo_effective_lanpaint_route')),
            bool(normalized_payload.get('_neo_effective_qwen_route')),
            bool(normalized_payload.get('_neo_scene_director_applied')),
            normalized_payload.get('_neo_scene_director_skip_reason') or '',
        )
        if normalized_payload.get('_neo_batch_guard_reason'):
            logger.info(
                'Generation batch guard | applied=%s | reason=%s | requested=%s | effective=%s | scene_director=%s',
                bool(normalized_payload.get('_neo_batch_guard_applied')),
                normalized_payload.get('_neo_batch_guard_reason') or '',
                normalized_payload.get('_neo_requested_batch_size') or normalized_payload.get('batch_size') or 1,
                normalized_payload.get('_neo_effective_batch_size') or normalized_payload.get('batch_size') or 1,
                bool(normalized_payload.get('scene_director_enabled')),
            )
        _append_generation_log('Generation workflow compiled and debug payload written.', context={
            'mode': normalized_payload.get('mode') or '',
            'family': normalized_payload.get('family') or '',
            'checkpoint': normalized_payload.get('checkpoint') or '',
            'sampler': normalized_payload.get('sampler') or '',
            'width': normalized_payload.get('width') or '',
            'height': normalized_payload.get('height') or '',
            'effective_mode': normalized_payload.get('_neo_effective_mode') or '',
            'effective_backend': normalized_payload.get('_neo_effective_inpaint_backend') or '',
            'scene_director_applied': bool(normalized_payload.get('_neo_scene_director_applied')),
        })
        try:
            queued = await adapter.queue_prompt(workflow)
        except Exception as queue_exc:
            if not _payload_uses_res4lyf(payload) or (isinstance(normalized_payload, dict) and normalized_payload.get('_neo_external_workflow_replaced')):
                raise
            logger.warning('RES4LYF workflow queue failed; attempting Core KSampler fallback: %s', queue_exc)
            _append_generation_log('RES4LYF workflow failed; falling back to Core KSampler.', exc=queue_exc, context={
                'sampler': payload.get('sampler') or payload.get('sampler_name') or '',
                'engine': _res4lyf_sampler_engine(payload),
                'action': 'fallback_to_core_ksampler',
            })
            workflow, normalized_payload, fallback_notes = await _build_res4lyf_core_fallback_workflow(payload, queue_exc)
            compile_notes = [*compile_notes, *fallback_notes]
            _finalize_scene_director_appearance_lock_state_metadata(normalized_payload)
            _safe_write_generation_debug_json(GENERATION_LAST_PAYLOAD_PATH, normalized_payload)
            _safe_write_generation_debug_json(GENERATION_LAST_WORKFLOW_PATH, workflow)
            queued = await adapter.queue_prompt(workflow)
        logger.info('Generation prompt queued in ComfyUI | prompt_id=%s | queue_number=%s | node_errors=%s', queued.get('prompt_id') or '', queued.get('number'), bool(queued.get('node_errors')))
    except ValueError as exc:
        logger.warning('Generation validation failed: %s', exc)
        return json_error(str(exc), 400)
    except Exception as exc:
        logger.exception('Could not queue the ComfyUI workflow')
        _append_generation_log('Could not queue the ComfyUI workflow.', exc=exc, context={'phase': 'queue_prompt_failed'})
        try:
            atomic_write_json(GENERATION_REJECTED_WORKFLOW_PATH, {
                'error': str(exc),
                'normalized_payload': normalized_payload,
                'compile_notes': pre_compile_notes + compile_notes,
                'workflow_graph': workflow,
            })
        except Exception:
            logger.exception('Could not save the rejected ComfyUI workflow debug payload')
        return json_error(f'Could not queue the ComfyUI workflow: {exc}', 502)

    profile = get_profile('image', session.get('profile_id') or None) or {
        'backend_type': 'comfyui',
        'name': session.get('profile_name') or 'ComfyUI',
        'base_url': session.get('base_url') or '',
    }
    job = create_generation_job(
        payload=normalized_payload,
        backend_profile=profile,
        prompt_id=str(queued.get('prompt_id') or ''),
        queue_number=queued.get('number'),
        compile_notes=compile_notes,
        workflow_graph=workflow,
    )
    if queued.get('node_errors'):
        job = update_generation_job(job['id'], {
            'state': 'error',
            'status_text': 'ComfyUI reported node validation errors.',
            'error': json.dumps(queued.get('node_errors'), ensure_ascii=False),
        }) or job
    else:
        background_tasks.add_task(_background_finalize_generation_job, str(job.get('id') or job.get('job_id') or ''))
    return JSONResponse({
        'ok': True,
        'job': job,
        'queued': queued,
        'message': f"Queued {normalized_payload.get('mode') or 'workflow'} in ComfyUI.",
    })


@router.post('/api/generation/pause')
async def api_generation_pause():
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        result = await adapter.clear_queue()
    except Exception as exc:
        return json_exception(exc, default_message='Could not clear the pending ComfyUI queue.', default_status=502, logger_override=logger, context='generation queue clear')
    return JSONResponse({
        'ok': True,
        'message': 'Pending queue cleared. The current run keeps going because this backend only supports interrupt, not true pause.',
        'result': result,
    })


@router.post('/api/generation/cancel')
async def api_generation_cancel(job_id: str = Form(''), prompt_id: str = Form('')):
    adapter, _session, error = _image_profile_or_error()
    if error:
        return error
    try:
        result = await adapter.interrupt(str(prompt_id or '').strip() or None)
    except Exception as exc:
        return json_exception(exc, default_message='Could not interrupt ComfyUI.', default_status=502, logger_override=logger, context='generation interrupt')

    queue_result = None
    try:
        queue_result = await adapter.clear_queue()
    except Exception:
        queue_result = None

    if str(job_id or '').strip():
        update_generation_job(job_id, {
            'state': 'cancelled',
            'status_text': 'Stopped from Neo Studio.',
        })
    return JSONResponse({
        'ok': True,
        'message': 'Stop sent to ComfyUI. Current run interrupted and pending queue cleared.',
        'result': result,
        'queue_result': queue_result,
    })
