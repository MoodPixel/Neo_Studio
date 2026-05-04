from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import APP_DIR, ROOT_DIR

SCENE_DIRECTOR_EXTENSION_DIR = ROOT_DIR / 'neo_extensions' / 'installed' / 'neo_scene_director'
SCENE_DIRECTOR_PACK_ZIP = SCENE_DIRECTOR_EXTENSION_DIR / 'Neo_Scene_Director_v0_5_2_IPAdapter_Region_Prep.zip'
SCENE_DIRECTOR_WORKFLOW_DIR = SCENE_DIRECTOR_EXTENSION_DIR / 'workflows' / 'test_workflows'
SCENE_DIRECTOR_NODE_DIR = SCENE_DIRECTOR_EXTENSION_DIR / 'ComfyUI' / 'custom_nodes' / 'neo_scene_director'


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def list_scene_director_workflows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not SCENE_DIRECTOR_WORKFLOW_DIR.exists():
        return rows
    for path in sorted(SCENE_DIRECTOR_WORKFLOW_DIR.glob('*.json')):
        name = path.name
        lower = name.lower()
        rows.append({
            'name': name,
            'stem': path.stem,
            'size_bytes': path.stat().st_size,
            'kind': 'gguf_vae' if 'gguf_vae' in lower else 'checkpoint',
            'subject_case': '4_people' if '4_people' in lower else ('3_people' if '3_people' in lower else 'pose_interaction'),
            'path': str(path),
        })
    return rows


def build_scene_director_status() -> dict[str, Any]:
    workflows = list_scene_director_workflows()
    return {
        'ok': True,
        'version': '0.5.2',
        'title': 'Neo Scene Director',
        'subtitle': 'Count-locked multi-subject regional scene prep with IPAdapter-ready masks.',
        'node_pack_available': SCENE_DIRECTOR_PACK_ZIP.exists(),
        'node_file_available': (SCENE_DIRECTOR_NODE_DIR / 'nodes.py').exists(),
        'workflow_count': len(workflows),
        'workflows': workflows,
        'recommended_order': [
            'Install/copy the bundled ComfyUI custom node first.',
            'Run the v0.5.2 workflows without IPAdapter to confirm count lock and quality.',
            'Add regular IPAdapter first, one subject mask at a time.',
            'Use FaceID only after InsightFace is installed and detected.',
            'Add LoRA region planning after identity masking is stable.',
        ],
        'ipadapter_notes': {
            'regular_model': 'ip-adapter-plus_sdxl_vit-h.safetensors',
            'clip_vision': 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors',
            'safe_weight_range': '0.45 - 0.60',
            'safe_start_end': '0.05 - 0.75',
            'faceid_warning': 'FaceID IPAdapter models require InsightFace. Regular IPAdapter does not.',
        },
        'outputs': [
            'positive conditioning',
            'negative conditioning',
            'layout control image',
            'mask preview',
            'subject_1_mask through subject_4_mask',
            'identity_plan_json',
            'scene_report',
        ],
    }


def workflow_path_by_name(name: str) -> Path | None:
    clean = Path(str(name or '')).name
    path = SCENE_DIRECTOR_WORKFLOW_DIR / clean
    if path.exists() and path.suffix.lower() == '.json':
        return path
    return None


def default_scene_json(case: str = 'pose_interaction') -> dict[str, Any]:
    case = str(case or 'pose_interaction').strip().lower()
    if case == '4_people':
        subjects = [
            {'id': 'person_1', 'bbox': [0.03, 0.08, 0.23, 0.92], 'prompt': 'adult black armored sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
            {'id': 'person_2', 'bbox': [0.27, 0.08, 0.47, 0.92], 'prompt': 'adult white armored sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
            {'id': 'person_3', 'bbox': [0.53, 0.08, 0.73, 0.92], 'prompt': 'adult blue armored sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
            {'id': 'person_4', 'bbox': [0.77, 0.08, 0.97, 0.92], 'prompt': 'adult white futuristic robot armor, full body', 'pose_type': 'standing relaxed', 'required': True},
        ]
        mode = 'count_locked'
    elif case == '3_people':
        subjects = [
            {'id': 'person_1', 'bbox': [0.05, 0.08, 0.30, 0.92], 'prompt': 'adult white armored sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
            {'id': 'person_2', 'bbox': [0.375, 0.08, 0.625, 0.92], 'prompt': 'adult black armored sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
            {'id': 'person_3', 'bbox': [0.70, 0.08, 0.95, 0.92], 'prompt': 'adult black tactical sci-fi soldier, full body', 'pose_type': 'standing relaxed', 'required': True},
        ]
        mode = 'count_locked'
    else:
        subjects = [
            {'id': 'person_1', 'bbox': [0.18, 0.10, 0.48, 0.92], 'prompt': 'adult woman in red hoodie and black skirt, full body', 'pose_type': 'standing, facing person_2', 'facing': 'person_2', 'required': True},
            {'id': 'person_2', 'bbox': [0.52, 0.10, 0.82, 0.92], 'prompt': 'adult man in grey hoodie and jeans, full body', 'pose_type': 'standing, facing person_1', 'facing': 'person_1', 'required': True},
        ]
        mode = 'relation_focused'
    objects = []
    relations = []
    if case == 'pose_interaction':
        objects = [{'id': 'gift_box', 'bbox': [0.43, 0.42, 0.57, 0.56], 'prompt': 'small red gift box', 'bound_to': ['person_1', 'person_2'], 'relation': 'held between them'}]
        relations = [{'from': 'person_1', 'to': 'person_2', 'type': 'handing_to', 'object': 'gift_box'}]
    return {
        'version': '0.5.2',
        'mode': mode,
        'canvas': {'width': 1344, 'height': 768},
        'camera': {'framing': 'wide full body' if mode == 'count_locked' else 'vertical full body', 'angle': 'eye level', 'lens': '50mm'},
        'global_style': 'realistic studio photo, clean grey background, full body, sharp details',
        'subjects': subjects,
        'objects': objects,
        'relations': relations,
        'negative': 'extra people, missing person, merged bodies, duplicate body, bad hands, deformed anatomy, nude, nsfw',
    }
