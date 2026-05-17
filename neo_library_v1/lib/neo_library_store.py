import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:
    from .shared_data_paths import CENTRAL_ROOT, library_data_path, studio_data_path
except ImportError:
    from shared_data_paths import CENTRAL_ROOT, library_data_path, studio_data_path

EXT_ROOT = Path(__file__).resolve().parents[1]
USER_DATA_DIR = library_data_path('', legacy_rel='')
SETTINGS_PATH = library_data_path('neo_library_settings.json', legacy_rel='neo_library_settings.json', default_json={})
NEO_STUDIO_SETTINGS_PATH = studio_data_path('neo_studio_settings.json', legacy_rel='neo_studio_settings.json', default_json={})
GENERATION_OUTPUT_SETTINGS_PATH = studio_data_path('generation_output_settings.json', legacy_rel='generation_output_settings.json', default_json={})
DEFAULT_ROOT = CENTRAL_ROOT
DEFAULT_GENERATION_OUTPUT_ROOT = studio_data_path('generated_outputs', legacy_rel='generated_outputs')
OUTPUT_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_MODE_OUTPUT_DIRS = {
    'txt2img': 'txt2img-images',
    'img2img': 'img2img-images',
    'inpaint': 'inpaint-images',
    'outpaint': 'outpaint-images',
}


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _sync_library_root_to_shared_settings(value: str) -> None:
    target = (value or '').strip()
    for settings_path in (SETTINGS_PATH, NEO_STUDIO_SETTINGS_PATH):
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = _read_json_dict(settings_path)
            data['library_root'] = target
            settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            continue


def _load_settings() -> Dict[str, Any]:
    data = _read_json_dict(SETTINGS_PATH)
    fallback = _read_json_dict(NEO_STUDIO_SETTINGS_PATH)
    shared_root = str(fallback.get('library_root') or '').strip()
    if shared_root:
        data['library_root'] = shared_root
    return data


def _save_settings(data: Dict[str, Any]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    if 'library_root' in data:
        _sync_library_root_to_shared_settings(str(data.get('library_root') or ''))


def get_library_root() -> Path:
    override = str(_load_settings().get('library_root') or '').strip()
    root = Path(override) if override else DEFAULT_ROOT
    _ensure_dir(root)
    for name in ('captions', 'prompts', 'images', 'thumbs', 'output_metadata'):
        _ensure_dir(root / name)
    return root


def get_output_metadata_root() -> Path:
    root = get_library_root() / 'output_metadata'
    _ensure_dir(root)
    return root


def set_library_root(path: str) -> str:
    data = _load_settings()
    data['library_root'] = str(path or '').strip()
    _save_settings(data)
    return data['library_root']


def _safe_json_load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _record_dir(kind: str) -> Path:
    root = get_library_root()
    return root / ('prompts' if kind == 'prompt' else 'captions')


def _scan_kind(kind: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fp in sorted(_record_dir(kind).glob('*.json')):
        data = _safe_json_load(fp)
        if not data:
            continue
        if (data.get('kind') or '').strip() != kind:
            continue
        data['_record_path'] = str(fp)
        out.append(data)
    out.sort(key=lambda r: ((r.get('category') or 'uncategorized').lower(), (r.get('name') or '').lower(), (r.get('created_at') or '')), reverse=False)
    return out


def scan_prompts() -> List[Dict[str, Any]]:
    return _scan_kind('prompt')


def scan_captions() -> List[Dict[str, Any]]:
    return _scan_kind('caption')


def categories(kind: str) -> List[str]:
    vals = {(r.get('category') or 'uncategorized').strip() or 'uncategorized' for r in _scan_kind(kind)}
    fp = get_library_root() / 'categories.json'
    try:
        stored = json.loads(fp.read_text(encoding='utf-8'))
        if isinstance(stored, list):
            vals.update((str(x or '').strip() or 'uncategorized') for x in stored)
    except Exception:
        pass
    if not vals:
        vals.add('uncategorized')
    return sorted(vals, key=str.lower)


def records_for_category(kind: str, category: str) -> List[Dict[str, Any]]:
    cat = (category or '').strip()
    rows = _scan_kind(kind)
    if not cat:
        return rows
    return [r for r in rows if ((r.get('category') or 'uncategorized').strip() or 'uncategorized') == cat]


def names_for_category(kind: str, category: str) -> List[str]:
    vals = []
    seen = set()
    for row in records_for_category(kind, category):
        name = (row.get('name') or '').strip() or '(untitled)'
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        vals.append(name)
    return vals


def images_for_category(kind: str, category: str) -> List[str]:
    vals = []
    seen = set()
    for row in records_for_category(kind, category):
        name = Path(row.get('image_path') or '').name or ''
        if not name:
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        vals.append(name)
    return vals


def find_prompt(category: str, name: str) -> Optional[Dict[str, Any]]:
    cat = (category or '').strip()
    target_name = (name or '').strip().lower()
    for row in records_for_category('prompt', cat):
        if ((row.get('name') or '').strip().lower() == target_name):
            return row
    return None


def find_caption(category: str, name: str = '', image_name: str = '') -> Optional[Dict[str, Any]]:
    cat = (category or '').strip()
    target_name = (name or '').strip().lower()
    target_image = (image_name or '').strip().lower()
    rows = records_for_category('caption', cat)
    if target_image:
        for row in rows:
            if Path(row.get('image_path') or '').name.lower() == target_image:
                return row
    if target_name:
        for row in rows:
            if ((row.get('name') or '').strip().lower() == target_name):
                return row
    return rows[0] if rows else None


def delete_prompt_record(category: str, name: str) -> Tuple[bool, str]:
    rec = find_prompt(category, name)
    if not rec:
        return False, 'Prompt not found.'
    try:
        Path(rec.get('_record_path') or '').unlink(missing_ok=True)
    except Exception as e:
        return False, f'Could not delete prompt: {e}'
    return True, f"Deleted prompt: {rec.get('name') or name}"


def delete_caption_record(category: str, name: str = '', image_name: str = '') -> Tuple[bool, str]:
    rec = find_caption(category, name, image_name)
    if not rec:
        return False, 'Caption not found.'
    root = get_library_root()
    try:
        Path(rec.get('_record_path') or '').unlink(missing_ok=True)
        for key in ('image_path', 'thumb_path'):
            rel = rec.get(key) or ''
            if rel:
                (root / rel).unlink(missing_ok=True)
    except Exception as e:
        return False, f'Could not delete caption: {e}'
    return True, f"Deleted caption: {rec.get('name') or image_name or name}"


def resolve_media_path(rel_path: str) -> str:
    if not rel_path:
        return ''
    root = get_library_root()
    fp = (root / rel_path).resolve()
    return str(fp) if fp.exists() else ''


def stats() -> Dict[str, Any]:
    prompt_rows = scan_prompts()
    caption_rows = scan_captions()
    return {
        'root': str(get_library_root()),
        'prompt_count': len(prompt_rows),
        'caption_count': len(caption_rows),
        'categories': sorted({*(r.get('category') or 'uncategorized' for r in prompt_rows), *(r.get('category') or 'uncategorized' for r in caption_rows)}, key=str.lower),
    }


def _webui_root() -> Path:
    try:
        import modules.paths as mp  # type: ignore
        p = getattr(mp, 'script_path', '') or getattr(mp, 'models_path', '')
        if p:
            return Path(p).resolve()
    except Exception:
        pass
    return EXT_ROOT.parent


def _mode_output_dir_name(mode: str) -> str:
    return _MODE_OUTPUT_DIRS.get((mode or '').strip().lower(), 'txt2img-images')


def _generation_output_root() -> Path:
    """Return the Image Results output root selected in Neo Studio.

    The Results > Output reuse browser must scan the same root that
    Rescue and save details uses. Do not fall back to the legacy WebUI
    outputs folder here, otherwise manually selected Neo output roots are
    ignored and stale files appear in the reuse browser.
    """
    data = _read_json_dict(GENERATION_OUTPUT_SETTINGS_PATH)
    configured = str(data.get('output_root') or '').strip()
    return Path(configured).expanduser() if configured else DEFAULT_GENERATION_OUTPUT_ROOT


def get_output_dirs() -> Dict[str, Path]:
    root = _generation_output_root()
    out = {mode: root / folder for mode, folder in _MODE_OUTPUT_DIRS.items()}
    for p in out.values():
        _ensure_dir(p)
    return out


def output_image_names(mode: str) -> List[str]:
    root = get_output_dirs().get(mode)
    if not root or not root.exists():
        return []
    files = [p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in OUTPUT_EXTS]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    names = []
    for fp in files:
        try:
            names.append(str(fp.relative_to(root)).replace('\\', '/'))
        except Exception:
            names.append(fp.name)
    return names


def resolve_output_path(mode: str, name: str) -> str:
    root = get_output_dirs().get(mode)
    if not root or not name:
        return ''
    fp = (root / name).resolve()
    if fp.exists():
        return str(fp)
    return ''


def _to_multiline(v: Any) -> str:
    if not v:
        return ''
    if isinstance(v, list):
        return '\n'.join(str(x) for x in v if x is not None)
    return str(v)




def _clean_output_reuse_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in ('', None, [], {}):
            return value
    return ''


def _collect_compact_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {k: _clean_output_reuse_value(v) for k, v in row.items() if v not in ('', None, [], {})}


def _normalize_output_reuse_workflow_state(data: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = data.get('workflow_state') if isinstance(data.get('workflow_state'), dict) else {}
    mirror = data.get('_neo_workflow_state') if isinstance(data.get('_neo_workflow_state'), dict) else {}
    payload_state = payload.get('workflow_state') if isinstance(payload.get('workflow_state'), dict) else {}
    source = raw or payload_state or mirror
    effective = source.get('effective_state') if isinstance(source.get('effective_state'), dict) else {}
    raw_state = source.get('raw_state') if isinstance(source.get('raw_state'), dict) else {}
    transition = source.get('transition') if isinstance(source.get('transition'), dict) else {}
    batch_policy = source.get('batch_policy') if isinstance(source.get('batch_policy'), dict) else payload_state.get('batch_policy') if isinstance(payload_state.get('batch_policy'), dict) else {}
    workflow_flat = source.get('workflow_state') if isinstance(source.get('workflow_state'), dict) else {}
    mode = _first_present(
        effective.get('mode'),
        effective.get('effective_mode'),
        workflow_flat.get('effective_mode'),
        payload_state.get('effective_mode'),
        payload.get('mode'),
        payload.get('workflow'),
        data.get('mode'),
    )
    source_kind = _first_present(
        effective.get('source_kind'), workflow_flat.get('source_kind'), payload_state.get('source_kind'),
        payload.get('_neo_source_kind'), payload.get('source_kind'),
    )
    source_id = _first_present(
        effective.get('source_id'), workflow_flat.get('source_id'), payload_state.get('source_id'),
        payload.get('_neo_source_id'), payload.get('source_id'),
    )
    output_policy = _first_present(
        effective.get('output_policy'), workflow_flat.get('output_policy_effective'), workflow_flat.get('output_policy'),
        payload_state.get('output_policy_effective'), payload_state.get('output_policy'),
        payload.get('_neo_output_policy_effective'), payload.get('output_policy'),
    )
    return _collect_compact_dict({
        'raw_mode': _first_present(raw_state.get('mode'), workflow_flat.get('raw_mode'), payload_state.get('raw_mode'), mode),
        'effective_mode': mode,
        'switch_reason': _first_present(transition.get('reason'), workflow_flat.get('switch_reason'), payload_state.get('switch_reason')),
        'source_kind': source_kind,
        'source_id': source_id,
        'output_policy': output_policy,
        'validation_status': _first_present(effective.get('validation_status'), workflow_flat.get('validation_status'), payload_state.get('validation_status')),
        'batch_requested': _first_present(batch_policy.get('requested'), payload.get('_neo_requested_batch_size')),
        'batch_effective': _first_present(batch_policy.get('effective'), payload.get('_neo_effective_batch_size')),
        'batch_reason': _first_present(batch_policy.get('reason'), payload.get('_neo_batch_guard_reason')),
    })


def _normalize_output_reuse_model_family_state(data: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    state = data.get('model_family_state') if isinstance(data.get('model_family_state'), dict) else {}
    if not state:
        state = data.get('_neo_model_family_state') if isinstance(data.get('_neo_model_family_state'), dict) else {}
    extra = data.get('extra_generation_params') if isinstance(data.get('extra_generation_params'), dict) else {}
    if not state and isinstance(extra.get('model_family_state'), dict):
        state = extra.get('model_family_state')
    raw_family = _first_present(state.get('raw_family'), payload.get('family'), payload.get('model_family'), data.get('family'))
    effective_family = _first_present(state.get('effective_family'), data.get('family'), payload.get('family'), payload.get('model_family'), 'sdxl_sd')
    model_source = _first_present(state.get('model_source'), payload.get('model_source'), payload.get('_neo_model_source'))
    return _collect_compact_dict({
        'raw_family': raw_family,
        'effective_family': effective_family,
        'model_source': model_source,
        'family_inference_source': state.get('family_inference_source'),
        'gguf_clip_type': _first_present(state.get('gguf_clip_type'), payload.get('gguf_clip_type'), payload.get('_neo_effective_gguf_clip_type')),
        'gguf_clip_mode': _first_present(state.get('gguf_clip_mode'), payload.get('gguf_clip_mode'), payload.get('_neo_effective_gguf_clip_mode')),
        'gguf_unet': _first_present(state.get('gguf_unet'), payload.get('gguf_unet'), payload.get('_neo_effective_gguf_unet')),
        'gguf_clip_primary': _first_present(state.get('gguf_clip_primary'), payload.get('gguf_clip_primary'), payload.get('_neo_effective_gguf_clip_primary')),
        'gguf_clip_secondary': _first_present(state.get('gguf_clip_secondary'), payload.get('gguf_clip_secondary'), payload.get('_neo_effective_gguf_clip_secondary')),
        'mmproj_required': _first_present(state.get('mmproj_required'), payload.get('_neo_effective_mmproj_required'), payload.get('mmproj_required')),
        'mmproj_source': _first_present(state.get('mmproj_source'), payload.get('_neo_effective_mmproj_source'), payload.get('mmproj_source')),
        'gguf_mmproj': _first_present(state.get('gguf_mmproj'), payload.get('gguf_mmproj'), payload.get('_neo_effective_mmproj')),
        'qwen_outpaint_base_size': _first_present(state.get('qwen_outpaint_base_size'), payload.get('_neo_qwen_outpaint_base_size')),
        'qwen_outpaint_padding': _first_present(state.get('qwen_outpaint_padding'), payload.get('_neo_qwen_outpaint_padding')),
        'qwen_outpaint_effective_size': _first_present(state.get('qwen_outpaint_effective_size'), payload.get('_neo_qwen_outpaint_effective_size')),
    })


def _normalize_output_reuse_generation_details(data: Dict[str, Any], payload: Dict[str, Any], generation: Dict[str, Any]) -> Dict[str, Any]:
    width = _first_present(payload.get('width'), generation.get('Width'))
    height = _first_present(payload.get('height'), generation.get('Height'))
    size = _first_present(generation.get('Size'), f'{width}x{height}' if width and height else '')
    qwen_effective_size = payload.get('_neo_qwen_outpaint_effective_size') if isinstance(payload.get('_neo_qwen_outpaint_effective_size'), dict) else {}
    return _collect_compact_dict({
        'checkpoint': _first_present(generation.get('Checkpoint'), generation.get('Model'), payload.get('checkpoint')),
        'seed': _first_present(generation.get('Seed'), payload.get('seed')),
        'steps': _first_present(generation.get('Steps'), payload.get('steps')),
        'cfg': _first_present(generation.get('CFG scale'), generation.get('CFG'), payload.get('cfg')),
        'sampler': _first_present(generation.get('Sampler'), payload.get('sampler')),
        'scheduler': _first_present(generation.get('Scheduler'), generation.get('Schedule type'), payload.get('scheduler')),
        'size': size,
        'width': width,
        'height': height,
        'effective_size': f"{qwen_effective_size.get('width')}x{qwen_effective_size.get('height')}" if qwen_effective_size.get('width') and qwen_effective_size.get('height') else '',
        'effective_width': qwen_effective_size.get('width'),
        'effective_height': qwen_effective_size.get('height'),
        'denoise': _first_present(generation.get('Denoising strength'), payload.get('denoise')),
        'vae': _first_present(generation.get('VAE'), payload.get('vae')),
        'clip_skip': _first_present(generation.get('Clip skip'), payload.get('clip_skip')),
        'guidance': _first_present(generation.get('Guidance'), payload.get('guidance'), payload.get('flux_guidance')),
    })


def _normalize_output_reuse_source_state(data: Dict[str, Any], payload: Dict[str, Any], workflow_state: Dict[str, Any]) -> Dict[str, Any]:
    source_output = data.get('source_output') if isinstance(data.get('source_output'), dict) else {}
    comfy = data.get('comfy') if isinstance(data.get('comfy'), dict) else {}
    source_images = payload.get('source_image_fields') if isinstance(payload.get('source_image_fields'), list) else []
    return _collect_compact_dict({
        'source_kind': _first_present(workflow_state.get('source_kind'), payload.get('source_kind'), payload.get('_neo_source_kind')),
        'source_id': _first_present(workflow_state.get('source_id'), payload.get('source_id'), payload.get('_neo_source_id')),
        'source_image_count': len(source_images) if source_images else '',
        'source_output_id': _first_present(source_output.get('output_id'), (comfy.get('source_output') or {}).get('output_id') if isinstance(comfy.get('source_output'), dict) else ''),
        'source_filename': _first_present(source_output.get('filename'), source_output.get('saved_filename')),
    })


def _normalize_output_reuse_metadata(data: Dict[str, Any], *, main: Dict[str, Any], generation: Dict[str, Any], controlnet: Any, extra: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    workflow_state = _normalize_output_reuse_workflow_state(data, payload)
    model_family_state = _normalize_output_reuse_model_family_state(data, payload)
    generation_details = _normalize_output_reuse_generation_details(data, payload, generation if isinstance(generation, dict) else {})
    source_state = _normalize_output_reuse_source_state(data, payload, workflow_state)
    compile_notes = data.get('compile_notes') if isinstance(data.get('compile_notes'), list) else []
    scene_director = data.get('scene_director') if isinstance(data.get('scene_director'), dict) else {}
    external_extensions = data.get('external_extensions') if isinstance(data.get('external_extensions'), dict) else {}
    ipadapter = data.get('ipadapter') if isinstance(data.get('ipadapter'), (dict, list)) else payload.get('ipadapter_units') if isinstance(payload.get('ipadapter_units'), list) else {}
    family = str(model_family_state.get('effective_family') or data.get('family') or '').strip()
    family_label = {
        'sdxl_sd': 'SDXL / SD',
        'flux': 'Flux GGUF',
        'qwen_image_edit': 'Qwen Image Edit GGUF',
    }.get(family, family or 'Unknown')
    return {
        'schema_version': 1,
        'record_type': 'output_reuse_metadata',
        'prompt': _to_multiline(main.get('positive_box') or main.get('positive') or data.get('prompt') or payload.get('prompt') or payload.get('positive') or ''),
        'negative_prompt': _to_multiline(main.get('negative_box') or main.get('negative') or data.get('negative_prompt') or payload.get('negative') or payload.get('negative_prompt') or ''),
        'family': family,
        'family_label': family_label,
        'workflow_state': workflow_state,
        'model_family_state': model_family_state,
        'generation': generation_details,
        'source_state': source_state,
        'controlnet': controlnet if isinstance(controlnet, (dict, list)) else {},
        'ipadapter': ipadapter,
        'scene_director': scene_director,
        'external_extensions': external_extensions,
        'compile_notes': compile_notes,
        'raw_sidecar_keys': sorted(str(k) for k in data.keys()),
    }


def _parse_parameters_block(parameters: str) -> Dict[str, Any]:
    text = (parameters or '').strip()
    out: Dict[str, Any] = {
        'main_positive': '',
        'main_negative': '',
        'adetailer_positive': '',
        'adetailer_negative': '',
        'generation': {},
        'controlnet': {},
        'extra': {},
        'raw_parameters': text,
    }
    if not text:
        return out

    lines = text.splitlines()
    param_start = None
    for i, line in enumerate(lines):
        if line.startswith('Steps:'):
            param_start = i
            break
    body_lines = lines[:param_start] if param_start is not None else lines
    param_line = '\n'.join(lines[param_start:]) if param_start is not None else ''

    positive_lines = []
    negative_lines = []
    seen_negative = False
    for line in body_lines:
        if line.startswith('Negative prompt:'):
            seen_negative = True
            negative_lines.append(line[len('Negative prompt:'):].strip())
            continue
        if seen_negative:
            negative_lines.append(line)
        else:
            positive_lines.append(line)

    out['main_positive'] = '\n'.join(positive_lines).strip()
    out['main_negative'] = '\n'.join(negative_lines).strip()

    params: Dict[str, str] = {}
    for part in [p.strip() for p in param_line.split(',') if p.strip()]:
        if ':' in part:
            k, v = part.split(':', 1)
            params[k.strip()] = v.strip()
    out['generation'] = {
        'Steps': params.get('Steps', ''),
        'Sampler': params.get('Sampler', ''),
        'Schedule type': params.get('Schedule type', params.get('Scheduler', '')),
        'CFG scale': params.get('CFG scale', ''),
        'Seed': params.get('Seed', ''),
        'Size': params.get('Size', ''),
        'Model': params.get('Model', params.get('Model hash', '')),
        'VAE': params.get('VAE', ''),
        'Denoising strength': params.get('Denoising strength', ''),
        'Clip skip': params.get('Clip skip', ''),
    }
    extra = {}
    adetailer_pos = []
    adetailer_neg = []
    controlnet = {}
    generation_keys = set(out['generation'].keys())
    for k, v in params.items():
        kl = k.lower()
        if kl.startswith('adetailer'):
            extra[k] = v
            if 'negative prompt' in kl:
                adetailer_neg.append(f'{k}: {v}')
            elif 'prompt' in kl:
                adetailer_pos.append(f'{k}: {v}')
        elif 'controlnet' in kl:
            controlnet[k] = v
        elif k not in generation_keys:
            extra[k] = v
    out['adetailer_positive'] = '\n'.join(adetailer_pos)
    out['adetailer_negative'] = '\n'.join(adetailer_neg)
    out['controlnet'] = controlnet
    out['extra'] = extra
    return out



def _stringify_clean(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value).strip()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in ('', None, [], {}):
            return value
    return ''


def _nested_dict(row: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    cur: Any = row
    for key in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key)
    return cur if isinstance(cur, dict) else {}


def _compact_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in (row or {}).items() if v not in ('', None, [], {})}


def _normalize_workflow_state_for_reuse(data: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    state = data.get('workflow_state') if isinstance(data.get('workflow_state'), dict) else {}
    if not state:
        state = data.get('_neo_workflow_state') if isinstance(data.get('_neo_workflow_state'), dict) else {}
    if not state:
        state = payload.get('workflow_state') if isinstance(payload.get('workflow_state'), dict) else {}
    flat = state.get('workflow_state') if isinstance(state.get('workflow_state'), dict) else {}
    raw = state.get('raw_state') if isinstance(state.get('raw_state'), dict) else {}
    effective = state.get('effective_state') if isinstance(state.get('effective_state'), dict) else {}
    transition = state.get('transition') if isinstance(state.get('transition'), dict) else {}
    batch_policy = state.get('batch_policy') if isinstance(state.get('batch_policy'), dict) else {}
    if not batch_policy:
        batch_policy = flat.get('batch_policy') if isinstance(flat.get('batch_policy'), dict) else {}

    effective_mode = _stringify_clean(_first_present(
        effective.get('mode'), effective.get('effective_mode'), flat.get('effective_mode'),
        state.get('effective_mode'), payload.get('_neo_effective_mode'), payload.get('mode')
    ))
    raw_mode = _stringify_clean(_first_present(
        raw.get('mode'), raw.get('raw_mode'), flat.get('raw_mode'), state.get('raw_mode'), payload.get('mode')
    ))
    source_kind = _stringify_clean(_first_present(
        effective.get('source_kind'), flat.get('source_kind'), state.get('source_kind'), payload.get('_neo_source_kind')
    ))
    source_id = _stringify_clean(_first_present(
        effective.get('source_id'), flat.get('source_id'), state.get('source_id'), payload.get('_neo_source_id')
    ))
    output_policy = _stringify_clean(_first_present(
        effective.get('output_policy_effective'), effective.get('output_policy'), flat.get('output_policy_effective'),
        flat.get('output_policy'), state.get('output_policy_effective'), state.get('output_policy'), payload.get('_neo_output_policy_effective')
    ))
    validation_status = _stringify_clean(_first_present(
        effective.get('validation_status'), flat.get('validation_status'), state.get('validation_status'), payload.get('_neo_workflow_validation_status')
    ))

    normalized = {
        'raw_mode': raw_mode,
        'effective_mode': effective_mode or raw_mode,
        'switch_reason': _stringify_clean(_first_present(
            transition.get('reason'), flat.get('switch_reason'), state.get('switch_reason'), payload.get('_neo_workflow_switch_reason')
        )),
        'source_kind': source_kind,
        'source_id': source_id,
        'output_policy': output_policy,
        'validation_status': validation_status,
        'batch_policy': batch_policy,
        'raw_state': raw,
        'effective_state': effective,
        'transition': transition,
    }
    return _compact_dict(normalized)


def _normalize_model_family_for_reuse(data: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    state = data.get('model_family_state') if isinstance(data.get('model_family_state'), dict) else {}
    if not state:
        state = data.get('_neo_model_family_state') if isinstance(data.get('_neo_model_family_state'), dict) else {}
    if not state:
        state = _nested_dict(data, 'toolchain', 'model_family_state')
    if not state:
        state = _nested_dict(data, 'extra_generation_params', 'model_family_state')
    family = _stringify_clean(_first_present(state.get('effective_family'), data.get('family'), payload.get('family')))
    model_source = _stringify_clean(_first_present(state.get('model_source'), payload.get('model_source')))
    normalized = {
        'raw_family': _stringify_clean(_first_present(state.get('raw_family'), payload.get('family'))),
        'effective_family': family,
        'model_source': model_source,
        'family_inference_source': _stringify_clean(state.get('family_inference_source')),
        'checkpoint': _stringify_clean(_first_present(payload.get('checkpoint'), _nested_dict(data, 'toolchain').get('checkpoint'))),
        'vae': _stringify_clean(_first_present(payload.get('vae'), _nested_dict(data, 'toolchain').get('vae'))),
        'gguf_unet': _stringify_clean(_first_present(state.get('gguf_unet'), payload.get('gguf_unet'), payload.get('_neo_effective_gguf_unet'))),
        'gguf_clip_type': _stringify_clean(_first_present(state.get('gguf_clip_type'), payload.get('gguf_clip_type'))),
        'gguf_clip_mode': _stringify_clean(_first_present(state.get('gguf_clip_mode'), payload.get('gguf_clip_mode'))),
        'gguf_clip_primary': _stringify_clean(_first_present(state.get('gguf_clip_primary'), payload.get('gguf_clip_primary'), payload.get('_neo_effective_gguf_clip_primary'))),
        'gguf_clip_secondary': _stringify_clean(_first_present(state.get('gguf_clip_secondary'), payload.get('gguf_clip_secondary'), payload.get('_neo_effective_gguf_clip_secondary'))),
        'gguf_mmproj': _stringify_clean(_first_present(state.get('gguf_mmproj'), payload.get('gguf_mmproj'))),
        'mmproj_required': _first_present(state.get('mmproj_required'), payload.get('_neo_effective_mmproj_required')),
        'mmproj_source': _stringify_clean(_first_present(state.get('mmproj_source'), payload.get('_neo_effective_mmproj_source'))),
    }
    return _compact_dict(normalized)


def _build_reuse_metadata_summary(data: Dict[str, Any], payload: Dict[str, Any], generation: Dict[str, Any], controlnet: Any, extra: Dict[str, Any], workflow_state: Dict[str, Any], model_family_state: Dict[str, Any]) -> Dict[str, Any]:
    source_output = data.get('source_output') if isinstance(data.get('source_output'), dict) else {}
    source_image_fields = payload.get('source_image_fields') if isinstance(payload.get('source_image_fields'), dict) else {}
    ipadapter = data.get('ipadapter') if isinstance(data.get('ipadapter'), (dict, list)) else payload.get('ipadapter_units')
    scene_director = data.get('scene_director') if isinstance(data.get('scene_director'), dict) else payload.get('scene_director')
    extensions = data.get('external_extensions') if isinstance(data.get('external_extensions'), dict) else data.get('_neo_external_extensions')
    compile_notes = data.get('compile_notes') if isinstance(data.get('compile_notes'), (list, dict, str)) else []
    workflow_graph = data.get('workflow_graph') if isinstance(data.get('workflow_graph'), dict) else {}

    summary = {
        'schema_version': 1,
        'prompt': _to_multiline(_first_present(_nested_dict(data, 'main').get('positive_box'), _nested_dict(data, 'main').get('positive'), payload.get('positive'), payload.get('positive_prompt'), payload.get('prompt'), data.get('prompt'))),
        'negative_prompt': _to_multiline(_first_present(_nested_dict(data, 'main').get('negative_box'), _nested_dict(data, 'main').get('negative'), payload.get('negative'), payload.get('negative_prompt'), data.get('negative_prompt'))),
        'workflow_state': workflow_state,
        'model_family_state': model_family_state,
        'generation': generation,
        'source': _compact_dict({
            'source_output_id': _stringify_clean(_nested_dict(data, 'lineage').get('source_output_id')),
            'source_output': source_output,
            'source_image_fields': source_image_fields,
        }),
        'controlnet': controlnet,
        'ipadapter': ipadapter if ipadapter not in (None, [], {}) else {},
        'scene_director': scene_director if scene_director not in (None, [], {}) else {},
        'external_extensions': extensions if extensions not in (None, [], {}) else {},
        'compile_notes': compile_notes,
        'workflow_graph': workflow_graph,
        'payload_keys': sorted([str(k) for k in payload.keys()]) if payload else [],
    }
    return _compact_dict(summary)

def _normalize_sidecar(data: Dict[str, Any]) -> Dict[str, Any]:
    main = data.get('main') if isinstance(data.get('main'), dict) else {}
    generation = data.get('generation') if isinstance(data.get('generation'), dict) else {}
    controlnet = data.get('controlnet') if isinstance(data.get('controlnet'), (list, dict)) else {}
    adetailer = data.get('adetailer') if isinstance(data.get('adetailer'), list) else []
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else {}

    if not main and payload:
        main = {
            'positive_box': payload.get('positive') or payload.get('positive_prompt') or payload.get('prompt') or '',
            'negative_box': payload.get('negative') or payload.get('negative_prompt') or '',
        }

    if not generation and payload:
        width = str(payload.get('width') or '').strip()
        height = str(payload.get('height') or '').strip()
        generation = {
            'Checkpoint': payload.get('checkpoint') or '',
            'Seed': payload.get('seed') if payload.get('seed') is not None else '',
            'Steps': payload.get('steps') if payload.get('steps') is not None else '',
            'CFG scale': payload.get('cfg') if payload.get('cfg') is not None else '',
            'Sampler': payload.get('sampler') or '',
            'Scheduler': payload.get('scheduler') or '',
            'Size': f'{width}x{height}' if width and height else '',
            'Denoising strength': payload.get('denoise') if payload.get('denoise') is not None else '',
            'VAE': payload.get('vae') or '',
            'Mode': payload.get('mode') or '',
        }

    if not controlnet and payload:
        units = payload.get('controlnet_units') if isinstance(payload.get('controlnet_units'), list) else []
        if units:
            controlnet = {'units': units}

    extra = data.get('extra_generation_params') if isinstance(data.get('extra_generation_params'), dict) else {}
    if not extra and payload:
        extra = {
            'refine_enabled': payload.get('refine_enabled'),
            'refine_mode': payload.get('refine_mode') or '',
            'refine_scale': payload.get('refine_scale') if payload.get('refine_scale') is not None else '',
            'refine_steps': payload.get('refine_steps') if payload.get('refine_steps') is not None else '',
            'refine_denoise': payload.get('refine_denoise') if payload.get('refine_denoise') is not None else '',
            'refine_upscaler': payload.get('refine_upscaler') or '',
            'inpaint_target': payload.get('inpaint_target') or '',
            'inpaint_context': payload.get('inpaint_context') or '',
            'outpaint_left': payload.get('outpaint_left') if payload.get('outpaint_left') is not None else '',
            'outpaint_top': payload.get('outpaint_top') if payload.get('outpaint_top') is not None else '',
            'outpaint_right': payload.get('outpaint_right') if payload.get('outpaint_right') is not None else '',
            'outpaint_bottom': payload.get('outpaint_bottom') if payload.get('outpaint_bottom') is not None else '',
            'outpaint_feather': payload.get('outpaint_feather') if payload.get('outpaint_feather') is not None else '',
            'loras': payload.get('loras') if isinstance(payload.get('loras'), list) else [],
        }
        extra = {k: v for k, v in extra.items() if v not in ('', None, [], {})}

    ad_pos = []
    ad_neg = []
    for idx, row in enumerate(adetailer, start=1):
        if not isinstance(row, dict):
            continue
        name = row.get('name') or f'pass_{idx}'
        if row.get('positive'):
            ad_pos.append(f"{name}: {row.get('positive')}")
        if row.get('negative'):
            ad_neg.append(f"{name}: {row.get('negative')}")

    raw_parameters = _to_multiline(data.get('raw_parameters') or '')
    if not raw_parameters and payload:
        lines = []
        positive = str(main.get('positive_box') or main.get('positive') or '').strip()
        negative = str(main.get('negative_box') or main.get('negative') or '').strip()
        if positive:
            lines.append(positive)
        if negative:
            lines.append(f'Negative prompt: {negative}')
        settings_parts = []
        for key in ('Steps', 'Sampler', 'Scheduler', 'CFG scale', 'Seed', 'Size', 'Checkpoint', 'VAE', 'Denoising strength', 'Mode'):
            value = generation.get(key)
            if value not in ('', None):
                label = 'Model' if key == 'Checkpoint' else key
                settings_parts.append(f'{label}: {value}')
        if settings_parts:
            lines.append(', '.join(settings_parts))
        raw_parameters = '\n'.join(lines)

    model_family_state = _normalize_model_family_for_reuse(data, payload)
    workflow_state = _normalize_workflow_state_for_reuse(data, payload)
    reuse_metadata = _build_reuse_metadata_summary(
        data, payload, generation, controlnet, extra, workflow_state, model_family_state
    )
    prompt = _to_multiline(_first_present(
        main.get('positive_box'), main.get('positive'), payload.get('positive'),
        payload.get('positive_prompt'), payload.get('prompt'), data.get('prompt')
    ))
    negative_prompt = _to_multiline(_first_present(
        main.get('negative_box'), main.get('negative'), payload.get('negative'),
        payload.get('negative_prompt'), data.get('negative_prompt')
    ))

    return {
        'main_positive': prompt,
        'main_negative': negative_prompt,
        'adetailer_positive': '\n'.join(ad_pos),
        'adetailer_negative': '\n'.join(ad_neg),
        'generation': generation,
        'controlnet': controlnet,
        'extra': extra,
        'workflow_state': workflow_state,
        'model_family_state': model_family_state,
        'reuse_metadata': reuse_metadata,
        'source_metadata': reuse_metadata.get('source') if isinstance(reuse_metadata.get('source'), dict) else {},
        'extension_metadata': reuse_metadata.get('external_extensions') if isinstance(reuse_metadata.get('external_extensions'), dict) else {},
        'compile_notes': reuse_metadata.get('compile_notes') or [],
        'workflow_graph': reuse_metadata.get('workflow_graph') if isinstance(reuse_metadata.get('workflow_graph'), dict) else {},
        'raw_parameters': raw_parameters,
    }


def load_output_record(mode: str, name: str) -> Dict[str, Any]:
    image_path = resolve_output_path(mode, name)
    empty = {
        'image_path': None,
        'main_positive': '',
        'main_negative': '',
        'adetailer_positive': '',
        'adetailer_negative': '',
        'generation_json': '{}',
        'controlnet_json': '{}',
        'extra_json': '{}',
        'raw_parameters': '',
        'workflow_state_json': '{}',
        'model_family_json': '{}',
        'reuse_metadata_json': '{}',
        'source_metadata_json': '{}',
        'extension_metadata_json': '{}',
        'compile_notes_json': '[]',
        'workflow_graph_json': '{}',
        'sidecar_found': False,
        'sidecar_path': '',
    }
    if not image_path:
        return empty

    fp = Path(image_path)
    parameters = ''
    try:
        with Image.open(fp) as im:
            parameters = str(im.info.get('parameters') or '')
    except Exception:
        parameters = ''

    parsed_png = _parse_parameters_block(parameters)
    sidecar_path = (get_output_metadata_root() / mode / Path(name)).with_suffix('.json')
    fallback_sidecar = fp.with_suffix('.json')
    sidecar_data = None
    actual_sidecar_path = None
    for candidate in (sidecar_path, fallback_sidecar):
        if candidate.exists():
            data = _safe_json_load(candidate)
            if data:
                sidecar_data = data
                actual_sidecar_path = candidate
                break

    if sidecar_data:
        meta = _normalize_sidecar(sidecar_data)
        return {
            'image_path': image_path,
            'main_positive': meta['main_positive'] or parsed_png['main_positive'],
            'main_negative': meta['main_negative'] or parsed_png['main_negative'],
            'adetailer_positive': meta['adetailer_positive'] or parsed_png['adetailer_positive'],
            'adetailer_negative': meta['adetailer_negative'] or parsed_png['adetailer_negative'],
            'generation_json': json.dumps(meta['generation'] or parsed_png['generation'], indent=2, ensure_ascii=False),
            'controlnet_json': json.dumps(meta['controlnet'] or parsed_png['controlnet'], indent=2, ensure_ascii=False),
            'extra_json': json.dumps(meta['extra'] or parsed_png['extra'], indent=2, ensure_ascii=False),
            'raw_parameters': parameters or meta.get('raw_parameters', ''),
            'workflow_state_json': json.dumps(meta.get('workflow_state') or {}, indent=2, ensure_ascii=False),
            'model_family_json': json.dumps(meta.get('model_family_state') or {}, indent=2, ensure_ascii=False),
            'reuse_metadata_json': json.dumps(meta.get('reuse_metadata') or {}, indent=2, ensure_ascii=False),
            'source_metadata_json': json.dumps(meta.get('source_metadata') or {}, indent=2, ensure_ascii=False),
            'extension_metadata_json': json.dumps(meta.get('extension_metadata') or {}, indent=2, ensure_ascii=False),
            'compile_notes_json': json.dumps(meta.get('compile_notes') or [], indent=2, ensure_ascii=False),
            'workflow_graph_json': json.dumps(meta.get('workflow_graph') or {}, indent=2, ensure_ascii=False),
            'sidecar_found': True,
            'sidecar_path': str(actual_sidecar_path),
        }

    return {
        'image_path': image_path,
        'main_positive': parsed_png['main_positive'],
        'main_negative': parsed_png['main_negative'],
        'adetailer_positive': parsed_png['adetailer_positive'],
        'adetailer_negative': parsed_png['adetailer_negative'],
        'generation_json': json.dumps(parsed_png['generation'], indent=2, ensure_ascii=False),
        'controlnet_json': json.dumps(parsed_png['controlnet'], indent=2, ensure_ascii=False),
        'extra_json': json.dumps(parsed_png['extra'], indent=2, ensure_ascii=False),
        'raw_parameters': parsed_png['raw_parameters'],
        'workflow_state_json': '{}',
        'model_family_json': '{}',
        'reuse_metadata_json': '{}',
        'source_metadata_json': '{}',
        'extension_metadata_json': '{}',
        'compile_notes_json': '[]',
        'workflow_graph_json': '{}',
        'sidecar_found': False,
        'sidecar_path': '',
    }
