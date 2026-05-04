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
DEFAULT_ROOT = CENTRAL_ROOT
OUTPUT_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}


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


def get_output_dirs() -> Dict[str, Path]:
    out = {}
    try:
        from modules import shared  # type: ignore
        txt = str(getattr(shared.opts, 'outdir_txt2img_samples', '') or '').strip()
        img = str(getattr(shared.opts, 'outdir_img2img_samples', '') or '').strip()
        if txt:
            out['txt2img'] = Path(txt)
        if img:
            out['img2img'] = Path(img)
    except Exception:
        pass
    root = _webui_root()
    out.setdefault('txt2img', root / 'outputs' / 'txt2img-images')
    out.setdefault('img2img', root / 'outputs' / 'img2img-images')
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

    return {
        'main_positive': _to_multiline(main.get('positive_box') or main.get('positive') or data.get('prompt') or ''),
        'main_negative': _to_multiline(main.get('negative_box') or main.get('negative') or data.get('negative_prompt') or ''),
        'adetailer_positive': '\n'.join(ad_pos),
        'adetailer_negative': '\n'.join(ad_neg),
        'generation': generation,
        'controlnet': controlnet,
        'extra': extra,
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
        'sidecar_found': False,
        'sidecar_path': '',
    }
