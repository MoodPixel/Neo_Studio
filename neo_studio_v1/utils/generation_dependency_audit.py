from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from .comfy_adapter import ComfyBackendAdapter
from .detailer_models import list_generation_detailer_models
from .node_manager import load_node_manager_settings, list_custom_nodes

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

CATEGORY_ALIASES = {
    'checkpoint': 'checkpoints',
    'checkpoints': 'checkpoints',
    'ckpt': 'checkpoints',
    'unet': 'unet',
    'gguf_unet': 'unet',
    'diffusion_model': 'unet',
    'diffusion_models': 'unet',
    'clip': 'clip',
    'text_encoder': 'clip',
    'text_encoders': 'clip',
    'lora': 'loras',
    'loras': 'loras',
    'vae': 'vae',
    'controlnet': 'controlnet',
    'controlnets': 'controlnet',
    'ipadapter': 'ipadapter',
    'ip-adapter': 'ipadapter',
    'clip_vision': 'clip_vision',
    'clipvision': 'clip_vision',
    'clip-vision': 'clip_vision',
    'upscaler': 'upscale_models',
    'upscalers': 'upscale_models',
    'upscale_model': 'upscale_models',
    'upscale_models': 'upscale_models',
    'sam': 'sams',
    'sams': 'sams',
    'bbox': 'ultralytics_bbox',
    'segm': 'ultralytics_segm',
    'ultralytics_bbox': 'ultralytics_bbox',
    'ultralytics_segm': 'ultralytics_segm',
}

CATEGORY_LABELS = {
    'checkpoints': 'Checkpoints',
    'unet': 'UNet / GGUF',
    'clip': 'Text encoders',
    'loras': 'LoRAs',
    'vae': 'VAE',
    'controlnet': 'ControlNet',
    'ipadapter': 'IP-Adapter',
    'clip_vision': 'CLIP Vision',
    'upscale_models': 'Upscalers',
    'sams': 'SAM',
    'ultralytics_bbox': 'Ultralytics bbox',
    'ultralytics_segm': 'Ultralytics segm',
}

EXPECTED_MODEL_DIRS = {
    'checkpoints': [('models', 'checkpoints')],
    'unet': [('models', 'unet'), ('models', 'diffusion_models')],
    'clip': [('models', 'clip'), ('models', 'text_encoders')],
    'loras': [('models', 'loras')],
    'vae': [('models', 'vae')],
    'controlnet': [('models', 'controlnet')],
    'ipadapter': [('models', 'ipadapter')],
    'clip_vision': [('models', 'clip_vision')],
    'upscale_models': [('models', 'upscale_models')],
    'sams': [('models', 'sams')],
    'ultralytics_bbox': [('models', 'ultralytics', 'bbox')],
    'ultralytics_segm': [('models', 'ultralytics', 'segm')],
}

FEATURE_NODES = {
    'controlnet': [('ControlNetLoader', 'ControlNet loader'), ('ControlNetApplyAdvanced', 'ControlNet apply advanced')],
    'ipadapter_standard': [('CLIPVisionLoader', 'CLIP Vision loader'), ('IPAdapterModelLoader', 'IP-Adapter model loader'), ('IPAdapterAdvanced', 'IP-Adapter advanced')],
    'ipadapter_faceid': [('CLIPVisionLoader', 'CLIP Vision loader'), ('IPAdapterUnifiedLoaderFaceID', 'IP-Adapter FaceID unified loader'), ('IPAdapterFaceID', 'IP-Adapter FaceID apply')],
    'detailer': [('UltralyticsDetectorProvider', 'Ultralytics detector provider'), ('SAMLoader', 'SAM loader'), ('FaceDetailer', 'FaceDetailer')],
    'supir': [('SUPIR_Upscale', 'SUPIR_Upscale')],
    'gguf': [('UnetLoaderGGUF', 'GGUF UNet loader'), ('CLIPLoaderGGUF', 'GGUF single encoder loader'), ('DualCLIPLoaderGGUF', 'GGUF dual encoder loader')],
}

FEATURE_LABELS = {
    'workflow': 'Core Generation',
    'controlnet': 'ControlNet',
    'ipadapter': 'IP-Adapter',
    'ipadapter_standard': 'IP-Adapter',
    'ipadapter_faceid': 'IP-Adapter FaceID',
    'detailer': 'ADetailer / Impact Pack',
    'supir': 'SUPIR',
    'highres': 'Upscale Lab',
    'lora': 'LoRA',
    'gguf': 'GGUF workflow',
}

PHASE_ONE_PACKS = [
    {
        'id': 'comfyui_gguf',
        'label': 'ComfyUI-GGUF',
        'purpose': 'GGUF diffusion model loading plus GGUF CLIP/T5 encoder loading.',
        'repo': 'https://github.com/city96/ComfyUI-GGUF',
        'folder_aliases': ['ComfyUI-GGUF'],
        'required_nodes': ['UnetLoaderGGUF', 'DualCLIPLoaderGGUF'],
    },
    {
        'id': 'controlnet_aux',
        'label': 'ComfyUI ControlNet Aux',
        'purpose': 'OpenPose / DWPose and depth preprocessors for reference-map building.',
        'repo': 'https://github.com/Fannovel16/comfyui_controlnet_aux',
        'folder_aliases': ['comfyui_controlnet_aux'],
        'required_nodes': ['OpenposePreprocessor', 'DWPreprocessor', 'DepthAnythingV2Preprocessor'],
    },
    {
        'id': 'deepbooru_tagger',
        'label': 'DeepDanbooru tagger backend',
        'purpose': 'Image-to-tag suggestion for the planned Tag Assist feature.',
        'repo': 'https://github.com/sipherxyz/comfyui-art-venture',
        'folder_aliases': ['comfyui-art-venture', 'ComfyUI-ART-Venture'],
        'required_nodes': ['DeepDanbooruCaption'],
    },
]


def _normalize_category(value: str) -> str:
    key = str(value or '').strip().lower().replace(' ', '_')
    return CATEGORY_ALIASES.get(key, key)


def _comfy_root_from_node_manager() -> Path | None:
    settings = load_node_manager_settings()
    custom_nodes = str(settings.get('custom_nodes_path') or '').strip()
    if not custom_nodes:
        return None
    path = Path(custom_nodes)
    if path.name.lower() == 'custom_nodes':
        return path.parent
    return path


def _normalize_path(text: Any, base_path: Path | None = None) -> str:
    raw = str(text or '').strip().strip('"')
    if not raw:
        return ''
    path = Path(raw)
    if not path.is_absolute() and base_path:
        path = base_path / path
    try:
        return str(path.expanduser().resolve())
    except Exception:
        return str(path)


def _yaml_files(comfy_root: Path | None) -> list[Path]:
    if not comfy_root or not comfy_root.exists():
        return []
    found: list[Path] = []
    patterns = ('extra_model_paths*.yaml', 'extra_model_paths*.yml', '*model_paths*.yaml', '*model_paths*.yml')
    for pattern in patterns:
        for fp in sorted(comfy_root.glob(pattern)):
            if fp.is_file() and fp not in found:
                found.append(fp)
    return found


def _coerce_path_values(raw: Any, base_path: Path | None = None) -> list[str]:
    values: list[str] = []
    if isinstance(raw, str):
        path_text = _normalize_path(raw, base_path)
        if path_text:
            values.append(path_text)
    elif isinstance(raw, list):
        for item in raw:
            values.extend(_coerce_path_values(item, base_path))
    return values


def _extract_yaml_paths(payload: Any, yaml_path: Path) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        return {}

    results: dict[str, list[str]] = {}

    def add(category: str, paths: Iterable[str]):
        normalized = _normalize_category(category)
        if normalized not in EXPECTED_MODEL_DIRS:
            return
        bucket = results.setdefault(normalized, [])
        seen = {str(item).lower() for item in bucket}
        for path_text in paths:
            key = str(path_text).lower()
            if key not in seen:
                seen.add(key)
                bucket.append(path_text)

    def walk(node: Any, inherited_base: Path | None = None):
        if not isinstance(node, dict):
            return
        local_base = inherited_base
        base_text = node.get('base_path') if isinstance(node, dict) else None
        if base_text:
            local_base = Path(_normalize_path(base_text, inherited_base))
        for key, value in node.items():
            lowered = str(key or '').strip().lower()
            if lowered in {'base_path', 'is_default', 'name', 'enabled', 'label', 'description'}:
                continue
            normalized_key = _normalize_category(lowered)
            if normalized_key in EXPECTED_MODEL_DIRS:
                add(normalized_key, _coerce_path_values(value, local_base))
                if isinstance(value, dict):
                    walk(value, local_base)
            elif isinstance(value, dict):
                walk(value, local_base)

    walk(payload, yaml_path.parent)
    return results


def _load_yaml_index(comfy_root: Path | None) -> dict[str, Any]:
    files = _yaml_files(comfy_root)
    category_paths: dict[str, list[str]] = {}
    file_rows: list[dict[str, Any]] = []
    for fp in files:
        payload = None
        if yaml is not None:
            try:
                payload = yaml.safe_load(fp.read_text(encoding='utf-8'))
            except Exception as exc:
                file_rows.append({'path': str(fp), 'ok': False, 'error': str(exc), 'categories': []})
                continue
        else:
            file_rows.append({'path': str(fp), 'ok': False, 'error': 'PyYAML is not installed in Neo Studio.', 'categories': []})
            continue
        extracted = _extract_yaml_paths(payload, fp)
        for category, paths in extracted.items():
            bucket = category_paths.setdefault(category, [])
            seen = {str(item).lower() for item in bucket}
            for path_text in paths:
                key = str(path_text).lower()
                if key not in seen:
                    seen.add(key)
                    bucket.append(path_text)
        file_rows.append({'path': str(fp), 'ok': True, 'error': '', 'categories': sorted(extracted.keys())})
    return {
        'active': bool(any(v for v in category_paths.values())),
        'files': file_rows,
        'paths_by_category': category_paths,
    }


def _model_dirs(comfy_root: Path | None, category: str) -> list[Path]:
    rels = EXPECTED_MODEL_DIRS.get(category) or []
    if not comfy_root or not rels:
        return []
    return [comfy_root.joinpath(*rel) for rel in rels]


def _model_dir(comfy_root: Path | None, category: str) -> Path | None:
    dirs = _model_dirs(comfy_root, category)
    return dirs[0] if dirs else None


def _find_named_file(directory: Path | None, filename: str) -> Path | None:
    if not directory or not directory.exists() or not filename:
        return None
    candidate = directory / filename
    if candidate.is_file():
        return candidate
    lowered = filename.lower()
    try:
        for child in directory.iterdir():
            if child.is_file() and child.name.lower() == lowered:
                return child
    except Exception:
        return None
    return None


def _find_in_external_paths(paths: list[str], filename: str) -> Path | None:
    lowered = str(filename or '').strip().lower()
    if not lowered:
        return None
    for path_text in paths:
        try:
            base = Path(path_text)
        except Exception:
            continue
        found = _find_named_file(base, filename)
        if found:
            return found
    return None


def _search_anywhere_under(root: Path | None, filename: str, limit: int = 4) -> list[Path]:
    if not root or not root.exists() or not filename:
        return []
    matches: list[Path] = []
    try:
        for fp in root.rglob(filename):
            if fp.is_file():
                matches.append(fp)
                if len(matches) >= limit:
                    break
    except Exception:
        return []
    return matches



def _first_nonempty_path(paths: list[Path]) -> str:
    return str(paths[0]) if paths else ''


def _feature_label(feature: str) -> str:
    return FEATURE_LABELS.get(str(feature or '').strip().lower(), str(feature or 'Feature').strip() or 'Feature')

def _yaml_snippet(category: str, folder_path: str) -> str:
    key = category if category not in {'ultralytics_bbox', 'ultralytics_segm'} else ('bbox' if category.endswith('bbox') else 'segm')
    return f"neo_studio_models:\n  {key}: {folder_path}"


def _detailer_catalog_from_draft(draft: dict[str, Any] | None) -> dict[str, Any]:
    draft = draft or {}
    return list_generation_detailer_models(
        detector_root=str(draft.get('detailer_custom_detector_root') or '').strip(),
        sam_root=str(draft.get('detailer_custom_sam_root') or '').strip(),
    )


def _collect_selected_models(draft: dict[str, Any] | None) -> list[dict[str, str]]:
    draft = draft or {}
    rows: list[dict[str, str]] = []

    def add(label: str, category: str, name: str, feature: str):
        text = str(name or '').strip()
        if not text:
            return
        rows.append({'label': label, 'category': _normalize_category(category), 'name': text, 'feature': feature})

    if str(draft.get('model_source') or 'checkpoint').strip().lower() == 'gguf':
        add('GGUF model', 'unet', draft.get('gguf_unet') or '', 'gguf')
        add('GGUF encoder', 'clip', draft.get('gguf_clip_primary') or '', 'gguf')
        if str(draft.get('gguf_clip_mode') or 'dual').strip().lower() == 'dual':
            add('GGUF encoder', 'clip', draft.get('gguf_clip_secondary') or '', 'gguf')
    else:
        add('Checkpoint', 'checkpoints', draft.get('checkpoint') or '', 'workflow')
    add('VAE', 'vae', draft.get('vae') or '', 'workflow')

    if str(draft.get('refine_enabled') or 'false').lower() == 'true' and str(draft.get('refine_mode') or 'latent').strip().lower() != 'latent':
        add('Highres upscaler', 'upscale_models', draft.get('refine_upscaler') or '', 'highres')

    if str(draft.get('supir_enabled') or 'false').lower() == 'true':
        add('SUPIR model', 'checkpoints', draft.get('supir_model') or '', 'supir')
        add('SUPIR SDXL model', 'checkpoints', draft.get('supir_sdxl_model') or '', 'supir')

    for unit in draft.get('loras') or []:
        if isinstance(unit, dict) and bool(unit.get('enabled', True)):
            add('LoRA', 'loras', unit.get('name') or unit.get('lora_name') or '', 'lora')

    if bool(draft.get('controlnet_enabled')):
        add('ControlNet model', 'controlnet', draft.get('controlnet_name') or '', 'controlnet')
    for unit in draft.get('controlnet_units') or []:
        if isinstance(unit, dict) and bool(unit.get('enabled', True)):
            add('ControlNet model', 'controlnet', unit.get('model') or unit.get('name') or '', 'controlnet')

    if bool(draft.get('ipadapter_enabled')):
        add('IP-Adapter model', 'ipadapter', draft.get('ipadapter_name') or '', 'ipadapter')
        add('CLIP Vision model', 'clip_vision', draft.get('ipadapter_clip_vision') or '', 'ipadapter')
    for unit in draft.get('ipadapter_units') or []:
        if isinstance(unit, dict) and bool(unit.get('enabled', True)):
            add('IP-Adapter model', 'ipadapter', unit.get('model') or '', 'ipadapter')
            add('CLIP Vision model', 'clip_vision', unit.get('clip_vision') or '', 'ipadapter')

    if bool(draft.get('detailer_enabled')):
        detector_category = 'ultralytics_segm' if str(draft.get('detailer_detector_type') or 'bbox').strip().lower() == 'segm' else 'ultralytics_bbox'
        add('Detailer detector', detector_category, draft.get('detailer_model') or '', 'detailer')
        add('Detailer SAM', 'sams', draft.get('detailer_sam_model') or '', 'detailer')
    for unit in draft.get('detailer_passes') or []:
        if isinstance(unit, dict) and bool(unit.get('enabled', True)):
            detector_category = 'ultralytics_segm' if str(unit.get('detector_type') or 'bbox').strip().lower() == 'segm' else 'ultralytics_bbox'
            add('Detailer detector', detector_category, unit.get('detector_model') or '', 'detailer')
            add('Detailer SAM', 'sams', unit.get('sam_model') or '', 'detailer')

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row['category'], row['name'].lower())
        if not row['name'] or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _required_feature_keys(draft: dict[str, Any] | None) -> list[str]:
    draft = draft or {}
    features: list[str] = []
    if bool(draft.get('controlnet_enabled')) or any(bool(unit.get('enabled', True)) for unit in (draft.get('controlnet_units') or []) if isinstance(unit, dict)):
        features.append('controlnet')
    ip_units = [unit for unit in (draft.get('ipadapter_units') or []) if isinstance(unit, dict) and bool(unit.get('enabled', True))]
    if bool(draft.get('ipadapter_enabled')) or ip_units:
        primary_mode = str(draft.get('ipadapter_mode') or 'standard').strip().lower()
        if primary_mode == 'faceid':
            features.append('ipadapter_faceid')
        else:
            features.append('ipadapter_standard')
        for unit in ip_units:
            features.append('ipadapter_faceid' if str(unit.get('mode') or 'standard').strip().lower() == 'faceid' else 'ipadapter_standard')
    if bool(draft.get('detailer_enabled')) or any(bool(unit.get('enabled', True)) for unit in (draft.get('detailer_passes') or []) if isinstance(unit, dict)):
        features.append('detailer')
    if str(draft.get('model_source') or 'checkpoint').strip().lower() == 'gguf':
        features.append('gguf')
    if str(draft.get('supir_enabled') or 'false').lower() == 'true':
        features.append('supir')
    return sorted(set(features))


async def _node_presence(adapter: ComfyBackendAdapter, node_names: list[str]) -> dict[str, bool]:
    state: dict[str, bool] = {}
    for node_name in node_names:
        try:
            info = await adapter.get_object_info(node_name)
        except Exception:
            info = {}
        if isinstance(info, dict) and node_name in info:
            info = info.get(node_name)
        state[node_name] = isinstance(info, dict) and bool(info)
    return state


def _catalog_name_set(values: Any) -> set[str]:
    if isinstance(values, list):
        return {str(item).strip().lower() for item in values if str(item).strip()}
    return set()


def _custom_node_installed(node_state: dict[str, Any], aliases: list[str], repo_url: str = '') -> bool:
    aliases_lower = {str(item or '').strip().lower() for item in aliases if str(item or '').strip()}
    repo_lower = str(repo_url or '').strip().lower()
    for row in node_state.get('nodes') or []:
        folder_name = str(row.get('folder_name') or row.get('name') or '').strip().lower()
        remote = str(row.get('remote_url') or '').strip().lower()
        if folder_name and folder_name in aliases_lower:
            return True
        if repo_lower and remote and repo_lower in remote:
            return True
    return False


def _phase_one_pack_status(node_state: dict[str, Any], node_presence: dict[str, bool]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pack in PHASE_ONE_PACKS:
        required_nodes = [str(item or '').strip() for item in (pack.get('required_nodes') or []) if str(item or '').strip()]
        present_nodes = [name for name in required_nodes if node_presence.get(name)]
        installed = _custom_node_installed(node_state, list(pack.get('folder_aliases') or []), str(pack.get('repo') or ''))
        ready = bool(installed or (required_nodes and len(present_nodes) >= max(1, min(2, len(required_nodes)))))
        rows.append({
            'id': pack.get('id') or '',
            'label': pack.get('label') or '',
            'purpose': pack.get('purpose') or '',
            'repo': pack.get('repo') or '',
            'folder_aliases': pack.get('folder_aliases') or [],
            'required_nodes': required_nodes,
            'present_nodes': present_nodes,
            'installed': bool(installed),
            'ready': ready,
            'missing_nodes': [name for name in required_nodes if name not in present_nodes],
        })
    return rows


async def build_generation_dependency_audit(adapter: ComfyBackendAdapter, draft: dict[str, Any] | None = None) -> dict[str, Any]:
    draft = draft or {}
    comfy_root = _comfy_root_from_node_manager()
    models_root = (comfy_root / 'models') if comfy_root else None
    yaml_index = _load_yaml_index(comfy_root)
    node_manager_state = list_custom_nodes()
    selected_models = _collect_selected_models(draft)
    feature_keys = _required_feature_keys(draft)

    catalog = await adapter.get_catalog()
    detailer_catalog = _detailer_catalog_from_draft(draft)
    catalog_sets = {
        'checkpoints': _catalog_name_set(catalog.get('checkpoints')),
        'unet': _catalog_name_set((catalog.get('unet') or [])) | _catalog_name_set((catalog.get('diffusion_models') or [])),
        'clip': _catalog_name_set((catalog.get('clip') or [])) | _catalog_name_set((catalog.get('text_encoders') or [])),
        'loras': _catalog_name_set(catalog.get('loras')),
        'vae': _catalog_name_set(catalog.get('vae')),
        'controlnet': _catalog_name_set(catalog.get('controlnet')),
        'ipadapter': _catalog_name_set(catalog.get('ipadapter')),
        'clip_vision': _catalog_name_set(catalog.get('clip_vision')),
        'upscale_models': _catalog_name_set(catalog.get('upscale_models') or catalog.get('upscalers')),
        'sams': _catalog_name_set(detailer_catalog.get('sam_models')),
        'ultralytics_bbox': _catalog_name_set(detailer_catalog.get('bbox_models')),
        'ultralytics_segm': _catalog_name_set(detailer_catalog.get('segm_models')),
    }

    nodes_to_check = sorted({name for feature in feature_keys for name, _label in FEATURE_NODES.get(feature, [])} | {name for pack in PHASE_ONE_PACKS for name in (pack.get('required_nodes') or [])})
    node_presence = await _node_presence(adapter, nodes_to_check)

    issues: list[dict[str, Any]] = []
    checked_nodes: list[dict[str, Any]] = []

    custom_nodes_path_exists = bool(node_manager_state.get('custom_nodes_path_exists'))
    custom_nodes_path = str(node_manager_state.get('settings', {}).get('custom_nodes_path') or '')
    if not custom_nodes_path_exists:
        issues.append({
            'kind': 'node_manager_path_missing',
            'tone': 'warn',
            'message': 'Neo could not verify the local custom_nodes path yet, so local node and model path auditing is only partial.',
            'custom_nodes_path': custom_nodes_path,
        })

    yaml_file_errors = [item for item in (yaml_index.get('files') or []) if item.get('ok') is False]
    for item in yaml_file_errors:
        issues.append({
            'kind': 'yaml_file_error',
            'tone': 'warn',
            'message': f"Could not read model path YAML: {item.get('path') or 'unknown file'}",
            'path': item.get('path') or '',
            'error': item.get('error') or '',
        })

    for feature in feature_keys:
        for node_name, label in FEATURE_NODES.get(feature, []):
            present = bool(node_presence.get(node_name))
            checked_nodes.append({'feature': feature, 'feature_label': _feature_label(feature), 'node_name': node_name, 'label': label, 'present': present})
            if not present:
                issues.append({
                    'kind': 'missing_node',
                    'tone': 'danger',
                    'feature': feature,
                    'feature_label': _feature_label(feature),
                    'node_name': node_name,
                    'label': label,
                    'message': f"{_feature_label(feature)} is missing node: {label} ({node_name}).",
                })

    checked_models: list[dict[str, Any]] = []
    misplaced_models = 0
    catalog_mismatches = 0
    yaml_warnings = len(yaml_file_errors)

    for row in selected_models:
        category = row['category']
        expected_dirs = _model_dirs(comfy_root, category)
        expected_dir = expected_dirs[0] if expected_dirs else None
        yaml_paths = list(yaml_index['paths_by_category'].get(category) or [])
        expected_match = next((match for match in (_find_named_file(directory, row['name']) for directory in expected_dirs) if match), None)
        yaml_match = None if expected_match else _find_in_external_paths(yaml_paths, row['name'])
        found_path = expected_match or yaml_match
        catalog_found = row['name'].strip().lower() in catalog_sets.get(category, set())
        elsewhere = _search_anywhere_under(models_root, row['name']) if not found_path else []
        elsewhere_paths = [str(item) for item in elsewhere]
        wrong_place = str(elsewhere[0]) if elsewhere else ''
        yaml_hint = ''
        if wrong_place:
            yaml_hint = _yaml_snippet(category, str(Path(wrong_place).parent))
        elif yaml_index.get('active') and yaml_paths:
            yaml_hint = _yaml_snippet(category, yaml_paths[0])
        elif yaml_index.get('active'):
            yaml_hint = _yaml_snippet(category, f"<PATH_TO_{category.upper()}_FOLDER>")

        status = 'missing'
        if expected_match:
            status = 'expected_dir'
        elif yaml_match:
            status = 'yaml_path'
        elif wrong_place:
            status = 'wrong_place'
        elif catalog_found:
            status = 'backend_only'

        checked_models.append({
            **row,
            'feature_label': _feature_label(row['feature']),
            'expected_dir': str(expected_dir) if expected_dir else '',
            'expected_dirs': [str(item) for item in expected_dirs],
            'yaml_paths': yaml_paths,
            'catalog_found': catalog_found,
            'found_in_expected_dir': bool(expected_match),
            'found_in_yaml_path': bool(yaml_match),
            'resolved_path': str(found_path) if found_path else '',
            'elsewhere_matches': elsewhere_paths,
            'wrong_place_path': wrong_place,
            'yaml_hint': yaml_hint,
            'status': status,
        })

        if wrong_place and not found_path:
            misplaced_models += 1
            issues.append({
                'kind': 'model_found_elsewhere',
                'tone': 'warn',
                'feature': row['feature'],
                'feature_label': _feature_label(row['feature']),
                'category': category,
                'category_label': CATEGORY_LABELS.get(category, category),
                'model_name': row['name'],
                'expected_dir': str(expected_dir) if expected_dir else '',
                'found_path': wrong_place,
                'yaml_hint': yaml_hint,
                'message': f"{row['name']} exists under {wrong_place}, but {CATEGORY_LABELS.get(category, category)} expects a different folder.",
            })
            continue

        if found_path and not catalog_found:
            catalog_mismatches += 1
            issues.append({
                'kind': 'backend_catalog_mismatch',
                'tone': 'info',
                'feature': row['feature'],
                'feature_label': _feature_label(row['feature']),
                'category': category,
                'category_label': CATEGORY_LABELS.get(category, category),
                'model_name': row['name'],
                'resolved_path': str(found_path),
                'message': f"{row['name']} exists locally, but ComfyUI did not list it in the live catalog yet.",
            })
            continue

        if not catalog_found and not found_path:
            issues.append({
                'kind': 'missing_model',
                'tone': 'warn',
                'feature': row['feature'],
                'feature_label': _feature_label(row['feature']),
                'category': category,
                'category_label': CATEGORY_LABELS.get(category, category),
                'model_name': row['name'],
                'label': row['label'],
                'expected_dir': str(expected_dir) if expected_dir else '',
                'yaml_paths': yaml_paths,
                'yaml_hint': yaml_hint,
                'message': f"Missing model: {row['name']} ({CATEGORY_LABELS.get(category, category)}).",
            })
        elif catalog_found and yaml_index.get('active') and not found_path and yaml_hint:
            yaml_warnings += 1
            issues.append({
                'kind': 'yaml_mapping_missing',
                'tone': 'info',
                'feature': row['feature'],
                'feature_label': _feature_label(row['feature']),
                'category': category,
                'category_label': CATEGORY_LABELS.get(category, category),
                'model_name': row['name'],
                'yaml_hint': yaml_hint,
                'message': f"{row['name']} is visible to the backend, but Neo could not resolve it from the local expected folder or mapped YAML paths.",
            })

    missing_node_count = sum(1 for item in issues if item.get('kind') == 'missing_node')
    missing_model_count = sum(1 for item in issues if item.get('kind') == 'missing_model')
    recommended_packs = _phase_one_pack_status(node_manager_state, node_presence)
    missing_recommended_packs = sum(1 for item in recommended_packs if not item.get('ready'))
    return {
        'ok': True,
        'comfy_root': str(comfy_root) if comfy_root else '',
        'custom_nodes_path': custom_nodes_path,
        'custom_nodes_path_exists': custom_nodes_path_exists,
        'yaml': {
            'active': bool(yaml_index.get('active')),
            'files': yaml_index.get('files') or [],
            'paths_by_category': yaml_index.get('paths_by_category') or {},
        },
        'required_features': feature_keys,
        'selected_models': selected_models,
        'checked_nodes': checked_nodes,
        'checked_models': checked_models,
        'issues': issues,
        'recommended_packs': recommended_packs,
        'summary': {
            'missing_nodes': missing_node_count,
            'missing_models': missing_model_count,
            'misplaced_models': misplaced_models,
            'catalog_mismatches': catalog_mismatches,
            'yaml_warnings': yaml_warnings,
            'yaml_active': bool(yaml_index.get('active')),
            'selected_models': len(selected_models),
            'missing_recommended_packs': missing_recommended_packs,
        },
    }
