from __future__ import annotations

from typing import Any
import json

SUPPORTED_FAMILIES = {'sd', 'sdxl', 'sdxl_sd', 'sd15', 'sd1.5', 'sd_1_5', 'sd1_5'}
BLOCKED_FAMILIES = {'flux', 'qwen', 'qwen_image_edit', 'zimage'}

DEFAULT_CONTRACTS = {
    'enabled': True,
    'use_node_auto_prompts': False,
    'count_contract': 'exactly {count} visible subjects, one subject per enabled region, no extra subjects',
    'subject_contract': 'one complete subject inside this region, not merged, not duplicated',
    'negative_contract': 'extra people, missing subject, wrong number of subjects, merged bodies, fused faces',
    'style_merge': 'use Neo main prompt as the scene style and composition intent',
}


def _clamp_float(value: Any, default: float = 0.0, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(lo, min(hi, parsed))


def _infer_checkpoint_variant(checkpoint_name: Any, family: Any = '') -> str:
    family_value = str(family or '').strip().lower()
    checkpoint = str(checkpoint_name or '').strip().lower()
    if family_value in {'sd15', 'sd1.5', 'sd_1_5', 'sd1_5', 'sd'}:
        return 'sd15'
    if family_value == 'sdxl':
        return 'sdxl'
    sd15_markers = ('sd15', 'sd1.5', 'sd_1_5', '1.5', 'v1-5', 'v1_5', 'anything', 'dreamshaper', 'deliberate', 'revanimated', 'majicmix', 'realisticvision')
    sdxl_markers = ('sdxl', 'xl', 'pony', 'juggernautxl', 'realvisxl', 'albedobase', 'animagine-xl')
    if any(marker in checkpoint for marker in sd15_markers):
        return 'sd15'
    if any(marker in checkpoint for marker in sdxl_markers):
        return 'sdxl'
    return 'checkpoint_sd'


def _render_contract(template: Any, count: int) -> str:
    text = str(template or '').strip()
    return text.replace('{count}', str(count))


def _contracts_from_scene(scene: dict[str, Any]) -> dict[str, Any]:
    raw = scene.get('contracts') if isinstance(scene.get('contracts'), dict) else {}
    contracts = dict(DEFAULT_CONTRACTS)
    contracts.update({k: v for k, v in raw.items() if k in contracts})
    contracts['enabled'] = raw.get('enabled', contracts['enabled']) is not False
    contracts['use_node_auto_prompts'] = bool(raw.get('use_node_auto_prompts', contracts.get('use_node_auto_prompts', False)))
    return contracts


def _unique_csv(parts: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for chunk in str(part or '').split(','):
            item = chunk.strip()
            key = item.lower()
            if item and key not in seen:
                seen.add(key)
                out.append(item)
    return ', '.join(out)




def _region_has_identity_reference(region: dict[str, Any]) -> bool:
    if not isinstance(region, dict):
        return False
    if bool(region.get('ipadapter')) or bool(region.get('character_profile_enabled')):
        return True
    if str(region.get('reference') or 'off').strip().lower() not in {'', 'off', 'none', 'false'}:
        return True
    profile = region.get('character_profile') or region.get('identity_profile') or region.get('profile')
    if isinstance(profile, dict) and (profile.get('image_name') or profile.get('image_names') or profile.get('reference_images')):
        return True
    for key in ('character_profile_id', 'character_profile_name', 'identity_profile_id', 'identity_profile_name', 'profile_id', 'profile_name', 'image_name', 'reference_image'):
        if str(region.get(key) or '').strip():
            return True
    images = region.get('image_names') or region.get('reference_images')
    return isinstance(images, list) and any(str(item or '').strip() for item in images)


def _identity_unit_from_region(region: dict[str, Any], region_index: int) -> dict[str, Any] | None:
    if not isinstance(region, dict) or not _region_has_identity_reference(region):
        return None
    profile = region.get('character_profile') or region.get('identity_profile') or region.get('profile')
    if not isinstance(profile, dict):
        profile = {}
    image_names = profile.get('image_names') if isinstance(profile.get('image_names'), list) else profile.get('reference_images')
    if not isinstance(image_names, list):
        image_names = region.get('image_names') if isinstance(region.get('image_names'), list) else region.get('reference_images')
    if not isinstance(image_names, list):
        image_names = []
    image_names = [str(item or '').strip() for item in image_names if str(item or '').strip()]
    image_name = str(profile.get('image_name') or region.get('image_name') or region.get('reference_image') or region.get('reference_note') or '').strip()
    if image_name and image_name not in image_names and not image_name.startswith('BOUND_TO_NEO_IPADAPTER_SLOT_'):
        image_names.insert(0, image_name)
    if not image_names:
        return None
    mode = str(profile.get('mode') or region.get('ipadapter_mode') or region.get('mode') or 'standard').strip().lower() or 'faceid'
    if mode == 'ipadapter':
        mode = 'standard'
    if mode not in {'standard', 'faceid'}:
        mode = 'standard'
    return {
        'uid': str(profile.get('uid') or profile.get('id') or region.get('character_profile_id') or region.get('identity_profile_id') or region.get('id') or f'scene_identity_region_{region_index}'),
        'profile_id': str(profile.get('id') or region.get('character_profile_id') or region.get('identity_profile_id') or ''),
        'profile_name': str(profile.get('name') or region.get('character_profile_name') or region.get('identity_profile_name') or region.get('label') or f'Region {region_index} Profile'),
        'mode': mode,
        'model': str(profile.get('model') or region.get('ipadapter_model') or region.get('ipadapter_name') or '').strip(),
        'clip_vision': str(profile.get('clip_vision') or region.get('ipadapter_clip_vision') or region.get('clip_vision') or '').strip(),
        'faceid_preset': str(profile.get('faceid_preset') or region.get('faceid_preset') or '').strip(),
        'faceid_provider': str(profile.get('faceid_provider') or region.get('faceid_provider') or '').strip(),
        'faceid_lora_strength': profile.get('faceid_lora_strength', region.get('faceid_lora_strength')),
        'weight_faceidv2': profile.get('weight_faceidv2', region.get('weight_faceidv2', region.get('ipadapter_weight'))),
        'weight': profile.get('weight', region.get('ipadapter_weight')),
        'start_at': profile.get('start_at', region.get('ipadapter_start_at')),
        'end_at': profile.get('end_at', region.get('ipadapter_end_at')),
        'image_name': image_names[0],
        'image_names': image_names,
        'region_id': str(region.get('id') or ''),
        'region_index': region_index,
        'label': str(region.get('label') or f'Region {region_index}'),
        'attn_mask_output_index': 5 + region_index,
        'source': 'scene_director_character_profile_region',
    }


def normalize_scene_director_state(extension_state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = extension_state if isinstance(extension_state, dict) else {}
    regions = state.get('regions') if isinstance(state.get('regions'), list) else []
    active_regions: list[dict[str, Any]] = []
    for index, raw in enumerate(regions):
        if not isinstance(raw, dict):
            continue
        rect = raw.get('rect') if isinstance(raw.get('rect'), dict) else {}
        x = _clamp_float(rect.get('x'), 0.0, 0.0, 1.0)
        y = _clamp_float(rect.get('y'), 0.0, 0.0, 1.0)
        w = _clamp_float(rect.get('w'), 0.33, 0.02, 1.0)
        h = _clamp_float(rect.get('h'), 1.0, 0.02, 1.0)
        if x + w > 1.0:
            x = max(0.0, 1.0 - w)
        if y + h > 1.0:
            y = max(0.0, 1.0 - h)
        region = {
            'id': str(raw.get('id') or f'region_{index + 1}'),
            'label': str(raw.get('label') or f'Region {index + 1}'),
            'type': str(raw.get('type') or 'character'),
            'enabled': raw.get('enabled') is not False,
            'visible': raw.get('visible') is not False,
            'prompt': str(raw.get('prompt') or '').strip(),
            'negative_prompt': str(raw.get('negative_prompt') or '').strip(),
            'strength': _clamp_float(raw.get('strength'), 1.0, 0.0, 2.0),
            'reference': str(raw.get('reference') or 'off'),
            'reference_note': str(raw.get('reference_note') or raw.get('reference_image') or raw.get('image_name') or ''),
            'image_name': str(raw.get('image_name') or raw.get('reference_image') or '').strip(),
            'image_names': raw.get('image_names') if isinstance(raw.get('image_names'), list) else (raw.get('reference_images') if isinstance(raw.get('reference_images'), list) else []),
            'character_profile': raw.get('character_profile') if isinstance(raw.get('character_profile'), dict) else (raw.get('identity_profile') if isinstance(raw.get('identity_profile'), dict) else {}),
            'character_profile_id': str(raw.get('character_profile_id') or raw.get('identity_profile_id') or raw.get('profile_id') or '').strip(),
            'character_profile_name': str(raw.get('character_profile_name') or raw.get('identity_profile_name') or raw.get('profile_name') or '').strip(),
            'character_profile_enabled': bool(raw.get('character_profile_enabled') or raw.get('identity_profile_enabled')),
            'ipadapter_model': str(raw.get('ipadapter_model') or raw.get('ipadapter_name') or ''),
            'ipadapter_clip_vision': str(raw.get('ipadapter_clip_vision') or raw.get('clip_vision') or 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
            'ipadapter_weight': _clamp_float(raw.get('ipadapter_weight'), 0.52, 0.0, 2.0),
            'ipadapter_start_at': _clamp_float(raw.get('ipadapter_start_at'), 0.05, 0.0, 1.0),
            'ipadapter_end_at': _clamp_float(raw.get('ipadapter_end_at'), 0.75, 0.0, 1.0),
            'pose': str(raw.get('pose') or 'off'),
            'ipadapter': bool(raw.get('ipadapter')),
            'ipadapter_slot': max(1, min(8, int(_clamp_float(raw.get('ipadapter_slot') or raw.get('ipadapterSlot') or (index + 1), index + 1, 1.0, 8.0)))),
            'ipadapter_use_region_mask': raw.get('ipadapter_use_region_mask') is not False,
            'ipadapter_weight_mode': str(raw.get('ipadapter_weight_mode') or 'slot_default').strip() or 'slot_default',
            'lora': bool(raw.get('lora')),
            'lora_slot': max(1, min(8, int(_clamp_float(raw.get('lora_slot') or raw.get('loraSlot') or (index + 1), index + 1, 1.0, 8.0)))),
            'lora_weight_mode': str(raw.get('lora_weight_mode') or 'slot_default').strip() or 'slot_default',
            'lora_strength': _clamp_float(raw.get('lora_strength'), 0.8, -4.0, 4.0),
            'rect': {'x': x, 'y': y, 'w': w, 'h': h},
            'loras': raw.get('loras') if isinstance(raw.get('loras'), list) else [],
        }
        if region['enabled'] and region['visible'] and (region['prompt'] or _region_has_identity_reference(region)):
            active_regions.append(region)
    return {
        'enabled': bool(state.get('enabled')),
        'family': str(state.get('family') or '').strip().lower(),
        'size': state.get('size') if isinstance(state.get('size'), dict) else {},
        'global': state.get('global') if isinstance(state.get('global'), dict) else {},
        'contracts': state.get('contracts') if isinstance(state.get('contracts'), dict) else {},
        'regions': regions,
        'active_regions': active_regions,
        'active_region_count': len(active_regions),
    }


def build_v052_scene_json(scene: dict[str, Any], width: int, height: int) -> tuple[str, dict[str, Any]]:
    active = scene.get('active_regions') if isinstance(scene.get('active_regions'), list) else []
    count = len(active)
    global_data = scene.get('global') if isinstance(scene.get('global'), dict) else {}
    contracts = _contracts_from_scene(scene)
    contracts_enabled = contracts.get('enabled') is not False
    main_prompt = str(global_data.get('prompt') or '').strip()
    main_negative = str(global_data.get('negative_prompt') or '').strip()

    global_parts = [main_prompt]
    if contracts_enabled:
        global_parts.extend([
            _render_contract(contracts.get('style_merge'), count),
            _render_contract(contracts.get('count_contract'), count),
        ])
    global_style = _unique_csv(global_parts)

    subjects: list[dict[str, Any]] = []
    ipadapter: dict[str, Any] = {}
    subject_contract = _render_contract(contracts.get('subject_contract'), count) if contracts_enabled else ''
    for index, region in enumerate(active, start=1):
        rect = region.get('rect') if isinstance(region.get('rect'), dict) else {}
        x = _clamp_float(rect.get('x'), 0.0, 0.0, 1.0)
        y = _clamp_float(rect.get('y'), 0.0, 0.0, 1.0)
        w = _clamp_float(rect.get('w'), 0.33, 0.02, 1.0)
        h = _clamp_float(rect.get('h'), 0.8, 0.02, 1.0)
        region_id = str(region.get('id') or f'region_{index}').strip() or f'region_{index}'
        label = str(region.get('label') or f'Region {index}').strip()
        prompt_parts = []
        if label:
            prompt_parts.append(label)
        region_prompt = str(region.get('prompt') or '').strip()
        if region_prompt:
            prompt_parts.append(region_prompt)
        if subject_contract:
            prompt_parts.append(subject_contract)
        subjects.append({
            'id': region_id,
            'bbox': [round(x, 4), round(y, 4), round(min(1.0, x + w), 4), round(min(1.0, y + h), 4)],
            'prompt': _unique_csv(prompt_parts),
            'pose_type': str(region.get('pose') or '').strip(),
            'facing': '',
            'required': True,
            'strength': round(_clamp_float(region.get('strength'), 1.0, 0.0, 2.0), 4),
            'priority': 1.0,
            'presence_boost': 1.0,
            'min_body_presence': 0.0,
            'feather': 18,
        })
        if bool(region.get('ipadapter')) or str(region.get('reference') or 'off') != 'off':
            slot = max(1, min(8, int(_clamp_float(region.get('ipadapter_slot') or index, index, 1.0, 8.0))))
            ipadapter[region_id] = {
                'image': f'BOUND_TO_NEO_IPADAPTER_SLOT_{slot}',
                'slot': slot,
                'weight': _clamp_float(region.get('ipadapter_weight'), 0.52, 0.0, 2.0),
                'weight_mode': str(region.get('ipadapter_weight_mode') or 'slot_default'),
                'start_at': _clamp_float(region.get('ipadapter_start_at'), 0.05, 0.0, 1.0),
                'end_at': _clamp_float(region.get('ipadapter_end_at'), 0.75, 0.0, 1.0),
            }

    negative_parts = [main_negative]
    if contracts_enabled:
        negative_parts.append(_render_contract(contracts.get('negative_contract'), count))
    scene_json = {
        'version': '0.5.2',
        'canvas': {'width': int(width), 'height': int(height)},
        'camera': {
            'framing': 'vertical scene' if height >= width else 'wide scene',
            'angle': '',
            'lens': '',
            'depth': '',
        },
        'global_style': global_style,
        'subjects': subjects,
        'relations': [],
        'negative': _unique_csv(negative_parts),
        'multi_subject_mode': 'count_locked' if count > 1 else 'single_subject',
        'entity_count': count,
        'identity': {'ipadapter': ipadapter},
    }
    return json.dumps(scene_json, ensure_ascii=False, indent=2), contracts


def scene_director_to_regional_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    if not isinstance(payload, dict):
        return payload, notes
    state = payload.get('scene_director_state')
    if not isinstance(state, dict):
        state = payload.get('scene_director') if isinstance(payload.get('scene_director'), dict) else {}
    scene = normalize_scene_director_state(state)
    if not scene.get('enabled'):
        return payload, notes

    family = str(payload.get('family') or scene.get('family') or '').strip().lower()
    if family in BLOCKED_FAMILIES or family not in SUPPORTED_FAMILIES:
        notes.append('Scene Director skipped: only SD / SDXL model families are supported.')
        return payload, notes

    variant = _infer_checkpoint_variant(payload.get('checkpoint') or payload.get('checkpoint_name') or payload.get('ckpt_name'), family)
    mode = str(payload.get('mode') or payload.get('workflow_type') or 'txt2img').strip().lower()
    if mode != 'txt2img':
        notes.append('Scene Director skipped: Phase 7.6 supports SDXL / SD 1.5 txt2img first.')
        return payload, notes

    active = scene.get('active_regions') if isinstance(scene.get('active_regions'), list) else []
    if not active:
        notes.append('Scene Director enabled but no active prompt/profile regions were found.')
        return payload, notes

    size = scene.get('size') if isinstance(scene.get('size'), dict) else {}
    width = int(float(payload.get('width') or size.get('width') or 1024))
    height = int(float(payload.get('height') or size.get('height') or 1024))
    scene_json, contracts = build_v052_scene_json(scene, width, height)

    units: list[dict[str, Any]] = []
    for index, region in enumerate(active, start=1):
        rect = region.get('rect') if isinstance(region.get('rect'), dict) else {}
        strength = _clamp_float(region.get('strength'), 1.0, 0.0, 2.0)
        units.append({
            'source': 'scene_director',
            'id': str(region.get('id') or f'scene_region_{index}'),
            'index': index,
            'enabled': True,
            'label': str(region.get('label') or f'Region {index}'),
            'type': str(region.get('type') or 'character'),
            'prompt': str(region.get('prompt') or '').strip(),
            'negative_prompt': str(region.get('negative_prompt') or '').strip(),
            'mask_source': 'rect',
            'mask_channel': 'alpha',
            'x': _clamp_float(rect.get('x'), 0.0, 0.0, 1.0),
            'y': _clamp_float(rect.get('y'), 0.0, 0.0, 1.0),
            'w': _clamp_float(rect.get('w'), 0.33, 0.02, 1.0),
            'h': _clamp_float(rect.get('h'), 1.0, 0.02, 1.0),
            'positive_strength': strength,
            'negative_strength': strength,
            'strength': strength,
            'falloff': 0.0,
            'priority': index,
            'composer_mode': 'scene_director',
            'overlap_mode': 'blend',
            'backend_mode': 'v052_node',
            'model_variant': variant,
            'reference': str(region.get('reference') or 'off'),
            'reference_note': str(region.get('reference_note') or ''),
            'image_name': str(region.get('image_name') or '').strip(),
            'image_names': region.get('image_names') if isinstance(region.get('image_names'), list) else [],
            'character_profile': region.get('character_profile') if isinstance(region.get('character_profile'), dict) else {},
            'character_profile_id': str(region.get('character_profile_id') or '').strip(),
            'character_profile_name': str(region.get('character_profile_name') or '').strip(),
            'character_profile_enabled': bool(region.get('character_profile_enabled')),
            'pose': str(region.get('pose') or 'off'),
            'ipadapter': bool(region.get('ipadapter')),
            'ipadapter_model': str(region.get('ipadapter_model') or ''),
            'ipadapter_clip_vision': str(region.get('ipadapter_clip_vision') or 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
            'ipadapter_weight': _clamp_float(region.get('ipadapter_weight'), 0.52, 0.0, 2.0),
            'ipadapter_start_at': _clamp_float(region.get('ipadapter_start_at'), 0.05, 0.0, 1.0),
            'ipadapter_end_at': _clamp_float(region.get('ipadapter_end_at'), 0.75, 0.0, 1.0),
            'ipadapter_slot': max(1, min(8, int(_clamp_float(region.get('ipadapter_slot') or index, index, 1.0, 8.0)))),
            'ipadapter_use_region_mask': region.get('ipadapter_use_region_mask') is not False,
            'ipadapter_weight_mode': str(region.get('ipadapter_weight_mode') or 'slot_default').strip() or 'slot_default',
            'lora': bool(region.get('lora')),
            'lora_slot': max(1, min(8, int(_clamp_float(region.get('lora_slot') or index, index, 1.0, 8.0)))),
            'lora_weight_mode': str(region.get('lora_weight_mode') or 'slot_default').strip() or 'slot_default',
            'lora_strength': _clamp_float(region.get('lora_strength'), 0.8, -4.0, 4.0),
            'loras': region.get('loras') if isinstance(region.get('loras'), list) else [],
        })


    scene_ipadapter_bindings: list[dict[str, Any]] = []
    bound_slots: list[int] = []
    for unit in units:
        if not bool(unit.get('ipadapter')):
            continue
        region_index = int(unit.get('index') or (len(scene_ipadapter_bindings) + 1))
        slot = max(1, min(8, int(_clamp_float(unit.get('ipadapter_slot') or region_index, region_index, 1.0, 8.0))))
        if slot not in bound_slots:
            bound_slots.append(slot)
        scene_ipadapter_bindings.append({
            'uid': f"scene_bind_{unit.get('id') or region_index}",
            'region_id': str(unit.get('id') or ''),
            'region_index': region_index,
            'label': str(unit.get('label') or f'Region {region_index}'),
            'slot': slot,
            'use_region_mask': bool(unit.get('ipadapter_use_region_mask', True)),
            'weight_mode': str(unit.get('ipadapter_weight_mode') or 'slot_default').strip() or 'slot_default',
            'weight': _clamp_float(unit.get('ipadapter_weight'), 0.52, 0.0, 2.0),
            'start_at': _clamp_float(unit.get('ipadapter_start_at'), 0.05, 0.0, 1.0),
            'end_at': _clamp_float(unit.get('ipadapter_end_at'), 0.75, 0.0, 1.0),
            'attn_mask_output_index': 5 + region_index,
            'source': 'scene_director_slot_binding',
        })

    # Phase 9.3: LoRA targeting is owned by the main Neo LoRA stack.
    # A LoRA row with apply_to="global" stays global. A row with
    # apply_to="scene_region_N" is removed from the global stack and routed
    # into the masked regional LoRA pass for subject N.
    scene_lora_bindings: list[dict[str, Any]] = []
    bound_lora_slots: list[int] = []
    source_loras = []
    raw_loras = payload.get('loras')
    if isinstance(raw_loras, list):
        source_loras = [dict(item, _neo_lora_slot_index=index + 1) for index, item in enumerate(raw_loras) if isinstance(item, dict)]
    elif str(payload.get('lora_name') or '').strip():
        source_loras = [{
            '_neo_lora_slot_index': 1,
            'name': str(payload.get('lora_name') or '').strip(),
            'strength': payload.get('lora_strength') if payload.get('lora_strength') is not None else 0.8,
            'target': payload.get('lora_target') or 'both',
            'apply_to': payload.get('lora_apply_to') or 'global',
        }]

    region_label_by_index = {int(unit.get('index') or i + 1): str(unit.get('label') or f'Region {i + 1}') for i, unit in enumerate(units)}
    region_id_by_index = {int(unit.get('index') or i + 1): str(unit.get('id') or '') for i, unit in enumerate(units)}
    for slot_index, lora_unit in enumerate(source_loras, 1):
        apply_to = str(lora_unit.get('apply_to') or lora_unit.get('applyTo') or 'global').strip().lower()
        if not apply_to.startswith('scene_region_'):
            continue
        try:
            region_index = int(apply_to.replace('scene_region_', '', 1))
        except Exception:
            region_index = 0
        if region_index <= 0 or region_index > 4:
            continue
        if region_index not in region_label_by_index:
            continue
        slot = int(lora_unit.get('_neo_lora_slot_index') or slot_index)
        if slot not in bound_lora_slots:
            bound_lora_slots.append(slot)
        scene_lora_bindings.append({
            'uid': f"scene_lora_stack_target_{slot}_region_{region_index}",
            'region_id': region_id_by_index.get(region_index, ''),
            'region_index': region_index,
            'label': region_label_by_index.get(region_index, f'Region {region_index}'),
            'slot': slot,
            'weight_mode': 'slot_default',
            'strength': _clamp_float(lora_unit.get('strength') or lora_unit.get('lora_strength'), 0.8, -4.0, 4.0),
            'source': 'neo_lora_stack_apply_to_targeting',
        })

    # Scene Director owns IPAdapter globally while enabled. Non-region-bound IPAdapters are suppressed
    # to avoid face/identity leakage into other regions.
    payload['scene_director_suppress_global_ipadapter'] = True

    if bound_lora_slots:
        payload['scene_director_bound_lora_units_source'] = source_loras
        bound_set = set(bound_lora_slots)
        payload['loras'] = [unit for index, unit in enumerate(source_loras) if (index + 1) not in bound_set]
        if 1 in bound_set:
            payload['lora_name'] = ''
            payload['lora_strength'] = ''
            payload['lora_enabled'] = False


    payload['scene_director_state'] = state
    payload['scene_director_enabled'] = True
    payload['scene_director_phase'] = '9.3'
    payload['scene_director_backend_mode'] = 'v052_node'
    payload['scene_director_model_variant'] = variant
    payload['scene_director_model_profile'] = 'sd15_v052_ipadapter_slot_binding' if variant == 'sd15' else 'sdxl_v052_ipadapter_slot_binding'
    payload['scene_director_regional_units'] = units
    payload['scene_director_v052_global_prompt_override'] = ''
    payload['scene_director_v052_prompt_contracts'] = contracts
    payload['scene_director_v052_scene_json'] = scene_json
    payload['scene_director_v052_base_weight'] = 0.55
    payload['scene_director_v052_region_gain'] = 0.42 if len(units) >= 3 else 0.40
    payload['scene_director_v052_max_subject_slots'] = 1
    payload['scene_director_v052_normalize_masks'] = True
    payload['scene_director_v052_enable_auto_prompts'] = bool(contracts.get('use_node_auto_prompts'))
    region_identity_units = []
    for unit in units:
        identity_unit = _identity_unit_from_region(unit, int(unit.get('index') or (len(region_identity_units) + 1)))
        if identity_unit:
            region_identity_units.append(identity_unit)
    if region_identity_units:
        existing_identity_units = payload.get('scene_director_identity_units') if isinstance(payload.get('scene_director_identity_units'), list) else []
        existing_keys = {str(item.get('uid') or item.get('profile_id') or '') for item in existing_identity_units if isinstance(item, dict)}
        merged_identity_units = list(existing_identity_units)
        for unit in region_identity_units:
            key = str(unit.get('uid') or unit.get('profile_id') or '')
            if key and key in existing_keys:
                continue
            merged_identity_units.append(unit)
        payload['scene_director_identity_units'] = merged_identity_units

    payload['scene_director_ipadapter_bindings'] = scene_ipadapter_bindings
    payload['scene_director_ipadapter_bound_slots'] = bound_slots
    existing_scene_ipadapter_units = payload.get('scene_director_ipadapter_units') if isinstance(payload.get('scene_director_ipadapter_units'), list) else []
    payload['scene_director_ipadapter_units'] = existing_scene_ipadapter_units
    payload['scene_director_ipadapter_count'] = len(scene_ipadapter_bindings) + len(existing_scene_ipadapter_units) + len(region_identity_units)
    payload['scene_director_lora_bindings'] = scene_lora_bindings
    payload['scene_director_lora_bound_slots'] = bound_lora_slots
    payload['scene_director_lora_count'] = len(scene_lora_bindings)
    payload['scene_director_regional_lora_backend'] = True
    payload['regional_prompt_enabled'] = True
    payload['regional_prompt_profile'] = 'scene_director'
    payload['regional_composer_mode'] = 'scene_director'
    payload['regional_backend_mode'] = 'v052_node'
    payload['regional_overlap_mode'] = 'blend'
    payload['regional_count'] = len(units)
    payload['regional_prompt_regions'] = units
    readable_variant = 'SD 1.5' if variant == 'sd15' else ('SDXL' if variant == 'sdxl' else 'SD checkpoint')
    notes.append(f'Scene Director Phase 9.2 staged {len(units)} {readable_variant} region(s) with editable prompt contracts, IPAdapter slot binding, and LoRA binding foundation metadata.')
    if scene_ipadapter_bindings:
        notes.append(f'Scene Director bound {len(scene_ipadapter_bindings)} region(s) to existing Neo IPAdapter slot(s): ' + ', '.join(str(slot) for slot in bound_slots) + '. Global IPAdapter is suppressed while Scene Director is on.')
    if region_identity_units:
        notes.append(f'Scene Director routed {len(region_identity_units)} Character Profile region(s) into masked IPAdapter/FaceID units.')
    if scene_lora_bindings:
        notes.append(f'Scene Director Phase 9.2 bound {len(scene_lora_bindings)} region(s) to existing Neo LoRA slot(s): ' + ', '.join(str(slot) for slot in bound_lora_slots) + '. These LoRAs are removed from the global stack and applied later as masked low-denoise regional LoRA passes.')
    return payload, notes


def patch_workflow(workflow: dict[str, Any], neo_settings: dict[str, Any] | None = None, extension_state: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = neo_settings or {}
    family = str(settings.get('family') or settings.get('model_family') or '').strip().lower()
    if family in BLOCKED_FAMILIES or (family and family not in SUPPORTED_FAMILIES):
        return workflow
    normalize_scene_director_state(extension_state)
    return workflow
