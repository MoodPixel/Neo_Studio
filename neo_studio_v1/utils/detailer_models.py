from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Dict
from urllib.request import urlretrieve

from .node_manager import load_node_manager_settings

MODEL_EXTS = {'.pt', '.pth', '.onnx', '.safetensors'}
SAM_PRESETS = {
    'vit_b': {
        'filename': 'sam_vit_b_01ec64.pth',
        'url': 'https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth',
        'label': 'SAM ViT-B',
    },
    'vit_l': {
        'filename': 'sam_vit_l_0b3195.pth',
        'url': 'https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth',
        'label': 'SAM ViT-L',
    },
    'vit_h': {
        'filename': 'sam_vit_h_4b8939.pth',
        'url': 'https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth',
        'label': 'SAM ViT-H',
    },
}


def _comfy_root_from_node_manager() -> Path | None:
    settings = load_node_manager_settings()
    custom_nodes = str(settings.get('custom_nodes_path') or '').strip()
    if not custom_nodes:
        return None
    path = Path(custom_nodes)
    if path.name.lower() == 'custom_nodes':
        return path.parent
    return path


def _scan_model_dir(path: Path | None) -> list[str]:
    if not path or not path.exists() or not path.is_dir():
        return []
    rows: list[str] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file() and child.suffix.lower() in MODEL_EXTS:
            rows.append(child.name)
    return rows


def _classify_custom_detector_files(path: Path | None) -> tuple[list[str], list[str]]:
    if not path or not path.exists() or not path.is_dir():
        return [], []
    bbox: list[str] = []
    segm: list[str] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file() or child.suffix.lower() not in MODEL_EXTS:
            continue
        name = child.name.lower()
        if 'seg' in name or 'mask' in name:
            segm.append(child.name)
        else:
            bbox.append(child.name)
    return bbox, segm


def _dedupe(rows: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in rows:
        key = str(item or '').strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def default_detailer_roots() -> Dict[str, str]:
    comfy_root = _comfy_root_from_node_manager()
    models_root = comfy_root / 'models' if comfy_root else None
    bbox_dir = models_root / 'ultralytics' / 'bbox' if models_root else None
    segm_dir = models_root / 'ultralytics' / 'segm' if models_root else None
    sam_dir = models_root / 'sams' if models_root else None
    return {
        'comfy_root': str(comfy_root) if comfy_root else '',
        'bbox_dir': str(bbox_dir) if bbox_dir else '',
        'segm_dir': str(segm_dir) if segm_dir else '',
        'sam_dir': str(sam_dir) if sam_dir else '',
    }


def list_generation_detailer_models(detector_root: str = '', sam_root: str = '') -> Dict[str, Any]:
    roots = default_detailer_roots()
    bbox_models = _scan_model_dir(Path(roots['bbox_dir'])) if roots.get('bbox_dir') else []
    segm_models = _scan_model_dir(Path(roots['segm_dir'])) if roots.get('segm_dir') else []
    sam_models = _scan_model_dir(Path(roots['sam_dir'])) if roots.get('sam_dir') else []

    custom_detector_root = str(detector_root or '').strip()
    custom_sam_root = str(sam_root or '').strip()
    if custom_detector_root:
        custom_bbox, custom_segm = _classify_custom_detector_files(Path(custom_detector_root))
        bbox_models = _dedupe(bbox_models + custom_bbox)
        segm_models = _dedupe(segm_models + custom_segm)
    if custom_sam_root:
        sam_models = _dedupe(sam_models + _scan_model_dir(Path(custom_sam_root)))

    return {
        **roots,
        'custom_detector_root': custom_detector_root,
        'custom_sam_root': custom_sam_root,
        'bbox_models': bbox_models,
        'segm_models': segm_models,
        'sam_models': sam_models,
        'sam_presets': [{'key': key, **value} for key, value in SAM_PRESETS.items()],
    }



def _copy_if_missing(source: Path, target_dir: Path) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source.name
    if not target_path.exists() or target_path.stat().st_size == 0:
        shutil.copy2(str(source), str(target_path))
    return target_path.name


def prepare_detailer_assets_for_payload(payload: Dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if not isinstance(payload, dict):
        return notes
    roots = default_detailer_roots()
    bbox_dir = Path(roots['bbox_dir']) if roots.get('bbox_dir') else None
    segm_dir = Path(roots['segm_dir']) if roots.get('segm_dir') else None
    sam_dir = Path(roots['sam_dir']) if roots.get('sam_dir') else None
    custom_detector_root = Path(str(payload.get('detailer_custom_detector_root') or '').strip()) if str(payload.get('detailer_custom_detector_root') or '').strip() else None
    custom_sam_root = Path(str(payload.get('detailer_custom_sam_root') or '').strip()) if str(payload.get('detailer_custom_sam_root') or '').strip() else None

    raw_passes = payload.get('detailer_passes')
    if not isinstance(raw_passes, list):
        raw_passes = []
        detailer = payload.get('detailer')
        if isinstance(detailer, dict):
            raw_passes.append(detailer)

    for unit in raw_passes:
        if not isinstance(unit, dict) or not bool(unit.get('enabled', True)):
            continue
        detector_name = str(unit.get('detector_model') or unit.get('model') or '').strip()
        detector_type = str(unit.get('detector_type') or 'bbox').strip().lower() or 'bbox'
        if detector_name:
            target_dir = segm_dir if detector_type == 'segm' else bbox_dir
            target_path = (target_dir / detector_name) if target_dir else None
            if target_dir and target_path and not target_path.exists() and custom_detector_root and (custom_detector_root / detector_name).exists():
                copied_name = _copy_if_missing(custom_detector_root / detector_name, target_dir)
                notes.append(f'Staged detailer detector into ComfyUI models: {copied_name}')
                unit['detector_model'] = copied_name
                if 'model' in unit:
                    unit['model'] = copied_name

        sam_name = str(unit.get('sam_model') or '').strip()
        if sam_name and sam_dir:
            target_path = sam_dir / sam_name
            if not target_path.exists() and custom_sam_root and (custom_sam_root / sam_name).exists():
                copied_name = _copy_if_missing(custom_sam_root / sam_name, sam_dir)
                notes.append(f'Staged SAM model into ComfyUI models: {copied_name}')
                unit['sam_model'] = copied_name

    return notes

def download_sam_model(model_key: str, target_root: str = '') -> Dict[str, Any]:
    preset = SAM_PRESETS.get(str(model_key or '').strip())
    if not preset:
        raise ValueError('Pick a SAM preset first.')
    roots = default_detailer_roots()
    root_text = str(target_root or '').strip() or roots.get('sam_dir') or ''
    if not root_text:
        raise ValueError('No SAM target path is configured yet.')
    target_dir = Path(root_text)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / preset['filename']
    if not target_path.exists() or target_path.stat().st_size == 0:
        urlretrieve(preset['url'], str(target_path))
    return {
        'key': model_key,
        'label': preset['label'],
        'filename': preset['filename'],
        'path': str(target_path),
        'target_root': str(target_dir),
    }
