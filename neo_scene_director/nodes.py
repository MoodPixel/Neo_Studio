
"""
Neo Scene Director v0.5.2 — IPAdapter Region Prep / Phase 7.6 Prompt Contracts Patch
Built on Neo Regional Prompter v0.4.4 Quality First.

Built from the v0.3 REAL masking/attention base.

New in v0.5.2:
- appends per-subject MASK outputs for IPAdapter masked/attention workflows
- appends identity_plan JSON for reference-image routing
- keeps v0.5.1 count-locked scene behavior untouched

Kept from v0.5.1:
- count_locked mode for 3+ visible subjects
- stronger exact-count global contract without overcooking quality
- subject slot contracts compiled from the v0.4.4 stable behavior
- mode switch: relation_focused for 1-2 subjects, count_locked for 3+ subjects
- keeps v0.5 scene JSON, relation composer, camera composer, and legacy compatibility

For harder pose locking, feed layout_preview or a proper pose/depth map into ControlNet.
"""

import json
import math
from typing import Any, Dict, List, Tuple
import torch
import torch.nn.functional as F
from torch.nn.functional import interpolate


def _safe_float(value, default=0.0):
    if value is None:
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "" or text.lower() == "none":
        return float(default)
    try:
        return float(text)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    if value is None:
        return int(default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if text == "" or text.lower() == "none":
        return int(default)
    try:
        return int(float(text))
    except Exception:
        return int(default)


def _safe_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "off", "")


def _clean_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _repeat_div(value: int, iterations: int) -> int:
    for _ in range(iterations):
        value = math.ceil(value / 2)
    return value


def _clip_encode_crossattn(clip: Any, text: str) -> torch.Tensor:
    tokens = clip.tokenize(text)

    try:
        encoded = clip.encode_from_tokens(tokens, return_pooled=True, return_dict=True)
        if isinstance(encoded, dict):
            if "cond" in encoded:
                return encoded["cond"]
            if "crossattn" in encoded:
                return encoded["crossattn"]
    except TypeError:
        pass

    encoded = clip.encode_from_tokens(tokens)

    if isinstance(encoded, dict):
        value = encoded.get("cond", None)
        if value is None:
            value = encoded.get("crossattn", None)
        if value is not None:
            return value

    if isinstance(encoded, (tuple, list)):
        first = encoded[0]
        if torch.is_tensor(first):
            return first
        if isinstance(first, (tuple, list)) and first and torch.is_tensor(first[0]):
            return first[0]

    if torch.is_tensor(encoded):
        return encoded

    raise RuntimeError("Could not extract CLIP cross-attention tensor from this ComfyUI version.")


def _pad_context_to_tokens(t: torch.Tensor, token_count: int) -> torch.Tensor:
    if t.shape[1] == token_count:
        return t
    if t.shape[1] > token_count:
        return t[:, :token_count, :]
    pad = torch.zeros((t.shape[0], token_count - t.shape[1], t.shape[2]), device=t.device, dtype=t.dtype)
    return torch.cat([t, pad], dim=1)


def _rect_to_pixels(mask_data: Dict, width: int, height: int):
    x = float(mask_data.get("x", 0))
    y = float(mask_data.get("y", 0))
    w = float(mask_data.get("w", 1))
    h = float(mask_data.get("h", 1))

    if abs(x) <= 1 and abs(w) <= 1:
        x1 = int(width * x)
        x2 = int(width * (x + w))
    else:
        x1 = int(x)
        x2 = int(x + w)

    if abs(y) <= 1 and abs(h) <= 1:
        y1 = int(height * y)
        y2 = int(height * (y + h))
    else:
        y1 = int(y)
        y2 = int(y + h)

    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid/empty rect mask: {mask_data}")
    return x1, y1, x2, y2


def _mask_anchor(mask_data: Dict):
    x = float(mask_data.get("x", 0))
    w = float(mask_data.get("w", 1))
    center = x + w * 0.5
    if center < 0.18:
        return "far left side of frame"
    if center < 0.38:
        return "left side of frame"
    if center < 0.62:
        return "center of frame"
    if center < 0.82:
        return "right side of frame"
    return "far right side of frame"


def _make_rect_mask(mask_data: Dict, width: int, height: int, weight: float = 1.0) -> torch.Tensor:
    x1, y1, x2, y2 = _rect_to_pixels(mask_data, width, height)
    mask = torch.zeros((height, width), dtype=torch.float32)
    mask[y1:y2, x1:x2] = max(0.0, float(weight))
    return mask.unsqueeze(0)


def _feather_mask(mask: torch.Tensor, feather_px: int) -> torch.Tensor:
    feather_px = int(feather_px)
    if feather_px <= 0:
        return mask
    k = max(3, feather_px * 2 + 1)
    if k % 2 == 0:
        k += 1
    pad = k // 2
    m = F.avg_pool2d(mask.unsqueeze(0), kernel_size=k, stride=1, padding=pad)
    return m.squeeze(0).clamp(0, 1)


def _region_type(region):
    return str(region.get("region_type", region.get("type", region.get("_kind", "region")))).lower()


def _enabled_regions(all_regions):
    return [r for r in all_regions if _safe_bool(r.get("enabled", True), True)]


def _subject_slots_for_region(region, max_subject_slots):
    # v0.4: one character region = one visible subject.
    # Repeating character branches caused v0.3.1 multi-person prompts to collapse.
    return 1

def _compile_entity_count_text(entity_count: int):
    if entity_count <= 0:
        return ""
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    word = words.get(entity_count, str(entity_count))
    return (
        f"(exactly {entity_count} visible subjects:1.35), ({word} separate subjects:1.30), "
        f"one subject per region, natural spacing, clean anatomy, coherent details, realistic proportions"
    )


def _compile_count_locked_contract(all_regions, entity_count: int, mode: str):
    if entity_count <= 0:
        return ""
    chars = [r for r in _enabled_regions(all_regions) if _region_type(r) == "character"]
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    word = words.get(entity_count, str(entity_count))
    slot_parts = []
    for idx, r in enumerate(chars, 1):
        rid = str(r.get("id", r.get("name", f"person_{idx}"))).strip()
        mask_data = r.get("mask") or {"x": r.get("x", 0), "y": r.get("y", 0), "w": r.get("w", 1), "h": r.get("h", 1)}
        anchor = _mask_anchor(mask_data)
        prompt = str(r.get("prompt", "")).strip()
        slot_parts.append(f"PERSON {idx} / {rid}: one complete subject locked on the {anchor}, separate from all others, {prompt}")

    if mode == "count_locked" or entity_count >= 3:
        return (
            f"COUNT-LOCKED SCENE MODE: the final image must show exactly {entity_count} subjects, {word} subjects total, "
            f"not two, not three unless exactly three requested, no missing people, no simplified pair composition, "
            f"no background extras, no split screen panels, no collapsed subjects; "
            f"left-to-right required subject slots: " + "; ".join(slot_parts)
        )
    return (
        f"RELATION-FOCUSED SCENE MODE: preserve exactly {entity_count} visible subjects while prioritizing the object/action relation; "
        + "; ".join(slot_parts)
    )


def _compile_spatial_contract(all_regions):
    parts = []
    for r in _enabled_regions(all_regions):
        if _region_type(r) not in ("character", "object"):
            continue
        rid = str(r.get("id", r.get("name", "region"))).strip()
        mask_data = r.get("mask") or {"x": r.get("x", 0), "y": r.get("y", 0), "w": r.get("w", 1), "h": r.get("h", 1)}
        anchor = _mask_anchor(mask_data)
        if rid:
            parts.append(f"{rid} positioned on the {anchor}")
    return ", ".join(parts)


def _compile_object_ownership(all_regions):
    parts = []
    for r in _enabled_regions(all_regions):
        rid = str(r.get("id", r.get("name", "region"))).strip()
        tokens = _clean_list(r.get("tokens", [])) + _clean_list(r.get("owns", []))
        if tokens:
            parts.append(f"{rid} contains " + ", ".join(tokens))
    return ", ".join(parts)



def _compile_region_summary(all_regions):
    parts = []
    subject_index = 0
    for r in _enabled_regions(all_regions):
        if _region_type(r) != "character":
            continue
        subject_index += 1
        rid = str(r.get("id", r.get("name", "region"))).strip()
        prompt = str(r.get("prompt", "")).strip()
        mask_data = r.get("mask") or {"x": r.get("x", 0), "y": r.get("y", 0), "w": r.get("w", 1), "h": r.get("h", 1)}
        anchor = _mask_anchor(mask_data)
        parts.append(
            f"PERSON {subject_index} slot {rid}: exactly one isolated separate subject on the {anchor}, "
            f"standing inside only this slot, not merged with neighbors, empty space around this person, {prompt}"
        )
    if not parts:
        return ""
    return "count anchor regional layout: " + "; ".join(parts)

def _compile_relation_contract(all_regions):
    parts = []
    for r in _enabled_regions(all_regions):
        rid = str(r.get("id", r.get("name", "region"))).strip()
        bound_to = str(r.get("bound_to", r.get("owner", ""))).strip()
        relation = str(r.get("relation", "")).strip()
        if bound_to:
            if relation:
                parts.append(f"{rid} is {relation} {bound_to}; keep {rid} visually attached to {bound_to}")
            else:
                parts.append(f"{rid} belongs to {bound_to}; keep {rid} visually attached to {bound_to}")
    return ", ".join(parts)


def _compile_negative(base_negative: str, all_regions, entity_count: int):
    negatives = [
        base_negative,
        "nude",
        "naked",
        "nsfw",
        "explicit",
        "topless",
        "bare chest",
        "bare breasts",
        "underwear",
        "lingerie",
        "bikini",
        "swimsuit",
        "transparent clothing",
        "wrong number of subjects",
        "missing character",
        "hidden character",
        "cropped character",
        "solo",
        "single subject",
        "one subject",
        "merged bodies",
        "fused faces",
        "fused bodies",
        "fused clothing",
        "mixed outfits",
        "object on wrong person",
        "props assigned to wrong character",
        "duplicated important object",
        "same outfit on all characters",
        "same face on all characters",
        "crowd",
        "background extra subjects",
        "low quality",
        "blurry",
        "deformed",
    ]
    if entity_count >= 3:
        negatives.extend(["only two characters", "two people only", "missing third character"])
    if entity_count >= 4:
        negatives.extend(["only three characters", "three people only", "missing fourth character"])

    for r in _enabled_regions(all_regions):
        rid = str(r.get("id", r.get("name", ""))).strip()
        for token in _clean_list(r.get("tokens", [])) + _clean_list(r.get("owns", [])):
            if rid:
                negatives.append(f"{token} outside {rid}")
                negatives.append(f"{token} on wrong side")
                negatives.append(f"{token} on wrong character")

    seen, out = set(), []
    for n in negatives:
        n = str(n).strip()
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return ", ".join(out)


def _compile_region_prompt(region: Dict):
    rid = str(region.get("id", region.get("name", "region"))).strip()
    rtype = _region_type(region)
    prompt = str(region.get("prompt", "")).strip()
    tokens = _clean_list(region.get("tokens", [])) + _clean_list(region.get("owns", []))
    priority = _safe_float(region.get("priority", 1.0), 1.0)
    presence = _safe_float(region.get("presence_boost", region.get("presence", 1.0)), 1.0)
    mask_data = region.get("mask") or {"x": region.get("x", 0), "y": region.get("y", 0), "w": region.get("w", 1), "h": region.get("h", 1)}
    anchor = _mask_anchor(mask_data)

    prefix = []
    if rid:
        prefix.append(rid)
    if rtype:
        prefix.append(f"{rtype} region")
    prefix.append(anchor)

    if rtype == "character":
        subject_required = _safe_bool(region.get("subject_required", True), True)
        min_body = _safe_float(region.get("min_body_presence", 0.85), 0.85)
        prefix.extend([
            "(visible character or subject:1.35)",
            "(single separate subject:1.45)",
            "(complete visible subject details:1.25)",
            "(isolated from other people:1.25)",
            "(must exist as its own subject:1.45)",
            "one complete subject placed inside this region",
            "do not merge with neighbor regions",
            "clear spacing between nearby people",
            f"minimum visible body presence {min_body:.2f}"
        ])
        if subject_required:
            prefix.append("subject_required true")
    elif rtype == "object":
        prefix.append("(clearly visible assigned object:1.25)")
        bound_to = str(region.get("bound_to", region.get("owner", ""))).strip()
        relation = str(region.get("relation", "")).strip()
        if bound_to:
            prefix.append(f"object bound_to {bound_to}")
        if relation:
            prefix.append(f"relation {relation}")
    elif rtype == "interaction":
        prefix.append("(shared interaction zone:1.05)")

    if priority >= 1.3:
        prefix.append(f"(high priority region:{min(priority, 1.5):.1f})")
    if presence >= 1.3:
        prefix.append(f"(must be visible:{min(presence, 1.6):.1f})")

    compiled = ", ".join(prefix + [prompt])
    if tokens:
        compiled += ", assigned objects/tokens: " + ", ".join(tokens)
        compiled += ", keep assigned objects inside this region"
    return compiled



def _bbox_to_mask(item: Dict):
    bbox = item.get("bbox", None)
    if bbox is None:
        return item.get("mask") or {"type": "rect", "x": item.get("x", 0), "y": item.get("y", 0), "w": item.get("w", 1), "h": item.get("h", 1)}
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError(f"bbox must be [x1,y1,x2,y2], got: {bbox}")
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return {"type": "rect", "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}


def _compile_camera_prompt(camera: Dict):
    if not isinstance(camera, dict):
        return ""
    parts = []
    for key in ("framing", "angle", "lens", "depth", "style"):
        val = str(camera.get(key, "")).strip()
        if val:
            parts.append(f"{key}: {val}")
    return ", ".join(parts)


def _relation_phrase(rel: Dict):
    if not isinstance(rel, dict):
        return ""
    source = str(rel.get("from", rel.get("source", ""))).strip()
    target = str(rel.get("to", rel.get("target", ""))).strip()
    rtype = str(rel.get("type", rel.get("relation", ""))).strip().lower()
    obj = str(rel.get("object", rel.get("item", ""))).strip()
    if not source or not rtype:
        return ""
    if rtype == "facing" and target:
        return f"{source} is facing {target}"
    if rtype == "looking_at" and target:
        return f"{source} is looking at {target}"
    if rtype == "holding" and obj:
        return f"{source} is holding {obj}"
    if rtype == "handing_to" and target and obj:
        return f"{source} is handing {obj} to {target}; {target} is receiving {obj}; hands meet naturally at {obj}"
    if rtype == "talking_to" and target:
        return f"{source} is talking to {target}; natural conversational body language"
    if rtype == "standing_beside" and target:
        return f"{source} is standing beside {target} with clean separation"
    if rtype == "standing_behind" and target:
        return f"{source} is standing behind {target} with visible full body separation"
    if rtype == "protecting" and target:
        return f"{source} is protectively positioned near {target}"
    if rtype == "chasing" and target:
        return f"{source} is chasing {target} with dynamic motion"
    if rtype == "sitting_on" and obj:
        return f"{source} is sitting on {obj}"
    if rtype == "leaning_on" and obj:
        return f"{source} is leaning on {obj}"
    if rtype == "surrounding" and target:
        return f"{source} and the other subjects are surrounding {target}"
    pieces = [source, rtype]
    if target:
        pieces.append(target)
    if obj:
        pieces.append(obj)
    return " ".join(pieces)


def _compile_scene_relations(relations: List[Dict]):
    phrases = [_relation_phrase(r) for r in relations or []]
    return "; ".join([p for p in phrases if p])


def _normalize_scene_v05(data: Dict, width: int, height: int):
    """Convert v0.5 Scene Director schema into the existing regional engine format."""
    if not any(k in data for k in ("subjects", "objects", "camera", "global_style", "relations", "canvas")):
        return data, [], {}, "0.4-legacy"

    camera = data.get("camera", {}) if isinstance(data.get("camera", {}), dict) else {}
    global_style = str(data.get("global_style", "")).strip()
    global_prompt = str(data.get("prompt", "")).strip()
    old_global = data.get("global", {}) if isinstance(data.get("global", {}), dict) else {}
    if not global_prompt:
        global_prompt = str(old_global.get("prompt", "")).strip()
    if global_style:
        global_prompt = f"{global_prompt}, {global_style}" if global_prompt else global_style
    cam_text = _compile_camera_prompt(camera)
    if cam_text:
        global_prompt = f"{global_prompt}, {cam_text}" if global_prompt else cam_text
    if not global_prompt:
        global_prompt = "cinematic realistic full body composition, masterpiece, best quality"

    subjects = data.get("subjects", []) or []
    objects = data.get("objects", []) or []
    relations = data.get("relations", []) or []

    regions = []
    for i, s in enumerate(subjects):
        sid = str(s.get("id", f"person_{i+1}")).strip()
        prompt_bits = [str(s.get("prompt", "")).strip()]
        pose = str(s.get("pose_type", s.get("pose", ""))).strip()
        facing = str(s.get("facing", "")).strip()
        action = str(s.get("action", "")).strip()
        if pose:
            prompt_bits.append(f"pose: {pose}")
        if facing:
            prompt_bits.append(f"facing {facing}")
        if action:
            prompt_bits.append(action)
        prompt_bits.append("one separate fully clothed subject, clean anatomy, natural proportions")
        prompt_bits.append(f"this is {sid}, exactly one unique subject in this slot only, not merged, not duplicated, not missing")
        r = {
            "id": sid,
            "region_type": "character",
            "mask": _bbox_to_mask(s),
            "prompt": ", ".join([p for p in prompt_bits if p]),
            "tokens": s.get("tokens", []),
            "strength": s.get("strength", 1.12),
            "priority": s.get("priority", 1.08),
            "presence_boost": s.get("presence_boost", 1.12),
            "subject_required": s.get("required", s.get("subject_required", True)),
            "min_body_presence": s.get("min_body_presence", 0.72),
            "feather": s.get("feather", 28),
            "pose_type": pose,
            "facing": facing,
        }
        regions.append(r)

    object_regions = []
    for i, o in enumerate(objects):
        oid = str(o.get("id", f"object_{i+1}")).strip()
        r = {
            "id": oid,
            "region_type": "object",
            "mask": _bbox_to_mask(o),
            "prompt": str(o.get("prompt", "")).strip() or oid.replace("_", " "),
            "tokens": o.get("tokens", []),
            "bound_to": o.get("bound_to", o.get("owner", "")),
            "relation": o.get("relation", ""),
            "strength": o.get("strength", 0.90),
            "priority": o.get("priority", 0.88),
            "presence_boost": o.get("presence_boost", 0.88),
            "feather": o.get("feather", 34),
        }
        object_regions.append(r)

    shared_regions = []
    for rel in relations:
        obj_id = str(rel.get("object", "")).strip()
        obj = next((o for o in objects if str(o.get("id", "")).strip() == obj_id), None)
        phrase = _relation_phrase(rel)
        if obj and phrase:
            shared_regions.append({
                "id": f"relation_{str(rel.get('type','interaction'))}_{obj_id}",
                "region_type": "interaction",
                "mask": _bbox_to_mask(obj),
                "prompt": phrase,
                "tokens": [obj_id],
                "strength": rel.get("strength", 0.42),
                "priority": rel.get("priority", 0.45),
                "presence_boost": rel.get("presence_boost", 0.45),
                "feather": rel.get("feather", 64),
            })

    negative = str(data.get("negative", old_global.get("negative", ""))).strip()
    entity_count = int(data.get("entity_count", old_global.get("entity_count", len(subjects))))
    mode = str(data.get("multi_subject_mode", data.get("mode", ""))).strip().lower()
    if not mode:
        mode = "count_locked" if entity_count >= 3 else "relation_focused"
    rel_text = _compile_scene_relations(relations)
    if rel_text:
        global_prompt = f"{global_prompt}, directed scene relations: {rel_text}"

    regional = {
        "global": {"entity_count": entity_count, "prompt": global_prompt, "negative": negative, "multi_subject_mode": mode},
        "regions": regions,
        "object_regions": object_regions,
        "shared_regions": shared_regions,
        "relations": relations,
        "camera": camera,
        "canvas": data.get("canvas", {"width": width, "height": height}),
        "multi_subject_mode": mode,
    }
    return regional, relations, camera, "0.5"

def _parse_scene_schema(scene_json: str, width: int, height: int, global_prompt_override: str, enable_auto_prompts: bool, max_subject_slots: int):
    data = json.loads(scene_json)
    if not isinstance(data, dict):
        raise ValueError("scene_json must be an object.")

    data, scene_relations, scene_camera, scene_schema_version = _normalize_scene_v05(data, width, height)

    global_data = data.get("global", {})
    global_prompt = str(global_data.get("prompt", "")).strip()
    if str(global_prompt_override).strip():
        global_prompt = str(global_prompt_override).strip()
    if not global_prompt:
        global_prompt = "masterpiece, best quality, full composition"

    base_negative = str(global_data.get("negative", "")).strip()

    regions = data.get("regions", [])
    shared_regions = data.get("shared_regions", [])
    object_regions = data.get("object_regions", [])

    all_regions = []
    for item in regions:
        r = dict(item); r["_kind"] = "region"; r.setdefault("region_type", "character"); all_regions.append(r)
    for item in object_regions:
        r = dict(item); r["_kind"] = "object"; r.setdefault("region_type", "object"); all_regions.append(r)
    for item in shared_regions:
        r = dict(item); r["_kind"] = "shared"; r.setdefault("region_type", "interaction"); all_regions.append(r)

    if len(all_regions) < 1:
        raise ValueError("scene_json needs at least one region/shared_region/object_region.")

    enabled = _enabled_regions(all_regions)
    auto_entity_count = sum(1 for r in enabled if _region_type(r) == "character")
    entity_count = _safe_int(global_data.get("entity_count", data.get("entity_count", auto_entity_count)), auto_entity_count)
    multi_subject_mode = str(global_data.get("multi_subject_mode", data.get("multi_subject_mode", ""))).strip().lower()
    if not multi_subject_mode:
        multi_subject_mode = "count_locked" if entity_count >= 3 else "relation_focused"

    compiled_global_parts = [global_prompt]
    if enable_auto_prompts:
        compiled_global_parts.append(_compile_entity_count_text(entity_count))
        compiled_global_parts.append(_compile_count_locked_contract(all_regions, entity_count, multi_subject_mode))
        compiled_global_parts.append(_compile_spatial_contract(all_regions))
        compiled_global_parts.append(_compile_region_summary(all_regions))
        compiled_global_parts.append(_compile_object_ownership(all_regions))
        compiled_global_parts.append(_compile_relation_contract(all_regions))
        compiled_global_parts.append(_compile_scene_relations(data.get("relations", [])))
        if multi_subject_mode == "count_locked":
            compiled_global_parts.append("COUNT-LOCKED DIRECTED SCENE MODE, preserve the exact requested number of visible subjects above cinematic background/style, each character region contains exactly one separate subject, every subject slot must be filled, visible subject structure in every person slot, simple clean lineup when 3 or more subjects are requested")
        else:
            compiled_global_parts.append("RELATION-FOCUSED DIRECTED SCENE MODE, layout locked composition, relations control facing/action/object exchange, keep object interaction natural, preserve subject count")

    compiled_global = ", ".join([p for p in compiled_global_parts if p.strip()])
    compiled_negative = _compile_negative(base_negative, all_regions, entity_count) if enable_auto_prompts else base_negative

    branch_prompts = []
    branch_masks = []
    debug_meta = []

    for idx, region in enumerate(all_regions):
        rid = str(region.get("id", region.get("name", f"region_{idx}")))
        prompt = str(region.get("prompt", "")).strip()
        if not prompt:
            raise ValueError(f"Region '{rid}' is missing prompt.")
        if not _safe_bool(region.get("enabled", True), True):
            continue

        strength = _safe_float(region.get("strength", region.get("weight", 1.0)), 1.0)
        priority = _safe_float(region.get("priority", 1.0), 1.0)
        presence = _safe_float(region.get("presence_boost", region.get("presence", 1.0)), 1.0)
        feather = int(_safe_float(region.get("feather", 0), 0))
        rtype = _region_type(region)
        slots = _subject_slots_for_region(region, max_subject_slots)

        mask_strength = strength * max(0.25, min(priority, 3.0)) * max(0.25, min(presence, 3.0))

        mask_data = region.get("mask") or {"type": "rect", "x": region.get("x", 0), "y": region.get("y", 0), "w": region.get("w", 1), "h": region.get("h", 1)}
        if str(mask_data.get("type", "rect")).lower() != "rect":
            raise ValueError("v0.3.1 supports only rect masks.")

        mask = _make_rect_mask(mask_data, width, height, mask_strength)
        mask = _feather_mask(mask, feather)
        compiled_prompt = _compile_region_prompt(region)

        # Multi-subject conditioning:
        # Repeat character regions as independent branches. Each branch shares same mask,
        # but gets a slightly different textual contract to avoid branch collapse.
        for slot in range(slots):
            slot_prompt = compiled_prompt
            if slots > 1:
                slot_prompt += f", subject existence branch {slot + 1} for {rid}, preserve this character"
            branch_prompts.append(slot_prompt)
            branch_masks.append(mask / float(slots))

        debug_meta.append({
            "id": rid,
            "type": rtype,
            "compiled_prompt": compiled_prompt,
            "subject_slots": slots,
            "strength": strength,
            "priority": priority,
            "presence_boost": presence,
            "mask_strength": mask_strength,
            "feather": feather,
            "tokens": _clean_list(region.get("tokens", [])) + _clean_list(region.get("owns", [])),
        })

    if len(branch_prompts) < 1:
        raise ValueError("No enabled regions found.")

    debug_json = json.dumps({
        "version": "0.5.2",
        "schema": scene_schema_version,
        "multi_subject_mode": multi_subject_mode,
        "entity_count": entity_count,
        "branch_count": len(branch_prompts),
        "compiled_global": compiled_global,
        "compiled_negative": compiled_negative,
        "regions": debug_meta,
    }, indent=2)

    layout_preview = _make_layout_preview(all_regions, width, height, data.get("relations", []))
    return compiled_global, compiled_negative, branch_prompts, branch_masks, debug_json, layout_preview


def _normalize_masks(masks: List[torch.Tensor], base_weight: float, normalize: bool):
    base = torch.ones_like(masks[0]) * max(0.0, float(base_weight))
    stack = torch.stack([base] + masks, dim=0)
    total = stack.sum(dim=0, keepdim=True)
    if total.min().item() <= 0.0:
        raise ValueError("Masks do not cover full canvas. Increase base_weight or add coverage regions.")
    if normalize:
        stack = stack / total
    return stack


def _downsample_masks(mask_stack: torch.Tensor, batch_size: int, token_count: int, original_shape: Tuple[int, ...], out: torch.Tensor):
    width, height = original_shape[3], original_shape[2]
    scale = math.ceil(math.log2(math.sqrt(height * width / max(1, token_count))))
    size = (_repeat_div(height, scale), _repeat_div(width, scale))
    mask_downsample = interpolate(mask_stack.to(device=out.device, dtype=out.dtype), size=size, mode="nearest")
    mask_downsample = mask_downsample.view(mask_downsample.shape[0], token_count, 1)
    mask_downsample = mask_downsample.unsqueeze(1).repeat(1, batch_size, 1, 1)
    return mask_downsample


def _make_preview(mask_stack: torch.Tensor):
    region_masks = mask_stack[1:]
    if region_masks.shape[0] == 0:
        h, w = mask_stack.shape[-2], mask_stack.shape[-1]
        return torch.zeros((1, h, w, 3), dtype=torch.float32)

    colors = torch.tensor([
        [1.0, 0.1, 0.1],
        [0.1, 0.3, 1.0],
        [0.1, 1.0, 0.2],
        [1.0, 0.8, 0.1],
        [1.0, 0.1, 1.0],
        [0.1, 1.0, 1.0],
        [1.0, 0.5, 0.1],
        [0.6, 0.2, 1.0],
    ], dtype=torch.float32)

    h, w = region_masks.shape[-2], region_masks.shape[-1]
    out = torch.zeros((h, w, 3), dtype=torch.float32)

    for i in range(region_masks.shape[0]):
        color = colors[i % colors.shape[0]]
        m = region_masks[i, 0].clamp(0, 1).unsqueeze(-1)
        out = out * (1.0 - m * 0.70) + color * (m * 0.70)

    return out.unsqueeze(0).clamp(0, 1)



def _draw_rect_border(img, x1, y1, x2, y2, color, thickness=3):
    h, w, _ = img.shape
    x1, x2 = max(0, x1), min(w - 1, x2)
    y1, y2 = max(0, y1), min(h - 1, y2)
    t = max(1, int(thickness))
    img[y1:min(h, y1+t), x1:x2+1] = color
    img[max(0, y2-t+1):y2+1, x1:x2+1] = color
    img[y1:y2+1, x1:min(w, x1+t)] = color
    img[y1:y2+1, max(0, x2-t+1):x2+1] = color


def _draw_line(img, x0, y0, x1, y1, color, thickness=2):
    h, w, _ = img.shape
    steps = max(abs(x1-x0), abs(y1-y0), 1)
    for i in range(steps + 1):
        t = i / steps
        x = int(round(x0 + (x1-x0) * t))
        y = int(round(y0 + (y1-y0) * t))
        r = max(1, int(thickness))
        img[max(0,y-r):min(h,y+r+1), max(0,x-r):min(w,x+r+1)] = color


def _draw_circle(img, cx, cy, radius, color, thickness=2):
    h, w, _ = img.shape
    r = max(2, int(radius))
    yy, xx = torch.meshgrid(torch.arange(h), torch.arange(w), indexing="ij")
    dist = torch.sqrt((xx - int(cx)).float() ** 2 + (yy - int(cy)).float() ** 2)
    ring = (dist >= r - thickness) & (dist <= r + thickness)
    img[ring] = color


def _draw_filled_circle(img, cx, cy, radius, color):
    h, w, _ = img.shape
    r = max(2, int(radius))
    yy, xx = torch.meshgrid(torch.arange(h), torch.arange(w), indexing="ij")
    dist = torch.sqrt((xx - int(cx)).float() ** 2 + (yy - int(cy)).float() ** 2)
    mask = dist <= r
    img[mask] = color


def _draw_filled_rect(img, x1, y1, x2, y2, color):
    h, w, _ = img.shape
    x1, x2 = max(0, int(x1)), min(w, int(x2))
    y1, y2 = max(0, int(y1)), min(h, int(y2))
    if x2 > x1 and y2 > y1:
        img[y1:y2, x1:x2] = color


def _draw_label_bars(img, x1, y1, label_index, color):
    # Tiny barcode-style label: readable as a visual anchor even without font dependencies.
    bar_w = max(4, (x1 + 1) // 80)
    for i in range(label_index):
        _draw_filled_rect(img, x1 + 8 + i * (bar_w + 3), y1 + 8, x1 + 8 + i * (bar_w + 3) + bar_w, y1 + 28, color)


def _make_layout_preview(all_regions, width: int, height: int, relations=None):
    """v0.4.3 Balanced Count layout guide.

    This is intentionally not pretty. It is a high-contrast control image:
    white canvas, strong region boxes, and mandatory body anchors for every subject.
    Feed this to ControlNet Scribble/Lineart/SoftEdge when possible.
    """
    img = torch.ones((height, width, 3), dtype=torch.float32) * 0.96
    colors = torch.tensor([
        [0.95, 0.05, 0.04], [0.04, 0.18, 0.95], [0.02, 0.62, 0.12], [0.95, 0.62, 0.02],
        [0.75, 0.05, 0.85], [0.02, 0.70, 0.70], [0.95, 0.35, 0.02], [0.35, 0.12, 0.85]
    ], dtype=torch.float32)
    subject_i = 0
    for i, r in enumerate(_enabled_regions(all_regions)):
        mask_data = r.get("mask") or {"x": r.get("x", 0), "y": r.get("y", 0), "w": r.get("w", 1), "h": r.get("h", 1)}
        try:
            x1, y1, x2, y2 = _rect_to_pixels(mask_data, width, height)
        except Exception:
            continue
        color = colors[i % colors.shape[0]]
        black = torch.tensor([0.0, 0.0, 0.0], dtype=torch.float32)
        dark = color * 0.35
        rtype = _region_type(r)

        # region tint + hard border
        overlay = torch.zeros_like(img); overlay[y1:y2, x1:x2] = color
        alpha = 0.045 if rtype == "character" else (0.035 if rtype == "object" else 0.025)
        m = (overlay.sum(-1, keepdim=True) > 0).float()
        img = img * (1.0 - m * alpha) + overlay * alpha
        _draw_rect_border(img, x1, y1, x2, y2, color, thickness=3 if rtype == "character" else 2)

        if rtype == "character":
            subject_i += 1
            # full-body count anchor silhouette: head, torso block, arms, legs, feet
            cx = (x1 + x2) // 2
            box_w = max(1, x2 - x1)
            box_h = max(1, y2 - y1)
            head_r = max(8, int(min(box_w, box_h) * 0.065))
            head_cy = y1 + int(box_h * 0.16)
            shoulder_y = y1 + int(box_h * 0.30)
            torso_top = y1 + int(box_h * 0.26)
            torso_bot = y1 + int(box_h * 0.56)
            hip_y = y1 + int(box_h * 0.60)
            knee_y = y1 + int(box_h * 0.76)
            foot_y = y1 + int(box_h * 0.92)
            shoulder = max(12, int(box_w * 0.22))
            torso_w = max(12, int(box_w * 0.18))
            hip_w = max(10, int(box_w * 0.13))

            # Label bars = PERSON number anchor
            _draw_label_bars(img, x1, y1, subject_i, color)

            # soft count anchor silhouette: visible enough for guide, not strong enough to destroy quality
            guide_col = torch.tensor([0.12, 0.12, 0.12], dtype=torch.float32)
            _draw_filled_circle(img, cx, head_cy, head_r, guide_col)
            _draw_circle(img, cx, head_cy, head_r + 3, color, thickness=3)
            _draw_filled_rect(img, cx - torso_w, torso_top, cx + torso_w, torso_bot, guide_col)
            _draw_rect_border(img, cx - torso_w, torso_top, cx + torso_w, torso_bot, color, thickness=3)
            _draw_line(img, cx - shoulder, shoulder_y, cx + shoulder, shoulder_y, guide_col, 3)
            _draw_line(img, cx - shoulder, shoulder_y, x1 + int(box_w * 0.18), y1 + int(box_h * 0.50), guide_col, 3)
            _draw_line(img, cx + shoulder, shoulder_y, x1 + int(box_w * 0.82), y1 + int(box_h * 0.50), guide_col, 3)
            _draw_line(img, cx - hip_w, hip_y, cx - int(box_w * 0.13), knee_y, guide_col, 3)
            _draw_line(img, cx + hip_w, hip_y, cx + int(box_w * 0.13), knee_y, guide_col, 3)
            _draw_line(img, cx - int(box_w * 0.13), knee_y, cx - int(box_w * 0.20), foot_y, guide_col, 3)
            _draw_line(img, cx + int(box_w * 0.13), knee_y, cx + int(box_w * 0.20), foot_y, guide_col, 3)
            _draw_line(img, cx - int(box_w * 0.27), foot_y, cx - int(box_w * 0.12), foot_y, guide_col, 3)
            _draw_line(img, cx + int(box_w * 0.12), foot_y, cx + int(box_w * 0.27), foot_y, guide_col, 3)

            # separation rails at subject boundaries to discourage merging
            _draw_line(img, x1 + 3, y1 + int(box_h*0.10), x1 + 3, y2 - int(box_h*0.08), color, 3)
            _draw_line(img, x2 - 3, y1 + int(box_h*0.10), x2 - 3, y2 - int(box_h*0.08), color, 3)
        elif rtype == "object":
            cx = (x1+x2)//2; cy=(y1+y2)//2
            _draw_line(img, x1, y1, x2, y2, color, 3)
            _draw_line(img, x1, y2, x2, y1, color, 3)
            _draw_filled_circle(img, cx, cy, max(4, min(x2-x1, y2-y1)//9), color)
            _draw_circle(img, cx, cy, max(6, min(x2-x1, y2-y1)//6), black, 2)
        elif rtype == "interaction":
            # interaction should guide, not dominate
            midx, midy = (x1+x2)//2, (y1+y2)//2
            _draw_line(img, x1, midy, x2, midy, color, 2)
            _draw_line(img, midx, y1, midx, y2, color, 2)
    # v0.5 relation/facing arrows. Keep them soft; this is a guide, not a final drawing.
    id_centers = {}
    for r in _enabled_regions(all_regions):
        rid = str(r.get("id", r.get("name", ""))).strip()
        if not rid:
            continue
        try:
            md = r.get("mask") or {"x": r.get("x",0), "y": r.get("y",0), "w": r.get("w",1), "h": r.get("h",1)}
            x1,y1,x2,y2 = _rect_to_pixels(md, width, height)
            id_centers[rid] = ((x1+x2)//2, (y1+y2)//2, x1,y1,x2,y2)
        except Exception:
            pass
    arrow_col = torch.tensor([0.05, 0.05, 0.05], dtype=torch.float32)
    for rel in relations or []:
        if not isinstance(rel, dict):
            continue
        src = str(rel.get("from", rel.get("source", ""))).strip()
        dst = str(rel.get("to", rel.get("target", rel.get("object", "")))).strip()
        obj = str(rel.get("object", "")).strip()
        target = obj if obj in id_centers else dst
        if src in id_centers and target in id_centers:
            x0,y0,_,_,_,_ = id_centers[src]
            x1,y1,_,_,_,_ = id_centers[target]
            _draw_line(img, x0, y0, x1, y1, arrow_col, 2)
            dx = x1 - x0; dy = y1 - y0
            mag = max(1.0, float((dx*dx + dy*dy) ** 0.5))
            ux, uy = dx / mag, dy / mag
            ah = 18
            _draw_line(img, x1, y1, int(x1 - ux*ah - uy*ah*0.45), int(y1 - uy*ah + ux*ah*0.45), arrow_col, 2)
            _draw_line(img, x1, y1, int(x1 - ux*ah + uy*ah*0.45), int(y1 - uy*ah - ux*ah*0.45), arrow_col, 2)
    return img.unsqueeze(0).clamp(0, 1)


def _patch_director(model: Any, region_conds: List[torch.Tensor], masks: List[torch.Tensor], base_weight: float, normalize_masks: bool, region_gain: float):
    m = model.clone()
    masks = [mask * max(0.1, float(region_gain)) for mask in masks]
    mask_stack = _normalize_masks(masks, base_weight, normalize_masks)
    region_count_total = len(region_conds) + 1

    state = {"batch_size": 1, "expanded_positive": False, "region_count_total": region_count_total}

    @torch.inference_mode()
    def attn2_patch(n, context_attn2, value_attn2, extra_options):
        cond_or_unconds = extra_options.get("cond_or_uncond", [0])
        chunks = len(cond_or_unconds) or 1

        n_chunks = n.chunk(chunks, dim=0)
        ctx_chunks = context_attn2.chunk(chunks, dim=0)
        val_chunks = value_attn2.chunk(chunks, dim=0) if value_attn2 is not None else ctx_chunks

        out_n, out_ctx, out_val = [], [], []
        state["expanded_positive"] = False

        for i, cond_or_uncond in enumerate(cond_or_unconds):
            n_i, ctx_i, val_i = n_chunks[i], ctx_chunks[i], val_chunks[i]

            if cond_or_uncond == 1:
                out_n.append(n_i); out_ctx.append(ctx_i); out_val.append(val_i)
                continue

            batch_size = n_i.shape[0]
            state["batch_size"] = batch_size
            state["expanded_positive"] = True
            token_count, ctx_dim = ctx_i.shape[1], ctx_i.shape[2]

            contexts = [ctx_i]
            values = [val_i]

            for cond in region_conds:
                cond_local = cond.to(device=ctx_i.device, dtype=ctx_i.dtype)
                if cond_local.shape[-1] != ctx_dim:
                    raise RuntimeError(f"Regional context dim {cond_local.shape[-1]} does not match current context dim {ctx_dim}.")
                cond_local = _pad_context_to_tokens(cond_local, token_count)
                cond_local = cond_local.repeat(batch_size, 1, 1)
                contexts.append(cond_local)
                values.append(cond_local)

            out_n.append(n_i.repeat(region_count_total, 1, 1))
            out_ctx.append(torch.cat(contexts, dim=0))
            out_val.append(torch.cat(values, dim=0))

        return torch.cat(out_n, dim=0).to(n), torch.cat(out_ctx, dim=0).to(context_attn2), torch.cat(out_val, dim=0).to(value_attn2)

    @torch.inference_mode()
    def attn2_output_patch(out, extra_options):
        cond_or_unconds = extra_options.get("cond_or_uncond", [0])
        original_shape = extra_options.get("original_shape", None)

        if original_shape is None or not state.get("expanded_positive", False):
            return out

        batch_size = int(state.get("batch_size", 1))
        token_count = out.shape[1]
        masks_down = _downsample_masks(mask_stack, batch_size, token_count, original_shape, out)

        outputs, pos = [], 0

        for cond_or_uncond in cond_or_unconds:
            if cond_or_uncond == 1:
                outputs.append(out[pos:pos + batch_size])
                pos += batch_size
            else:
                count = region_count_total * batch_size
                block = out[pos:pos + count]
                pos += count
                block = block.view(region_count_total, batch_size, out.shape[1], out.shape[2])
                blended = (block * masks_down).sum(dim=0)
                outputs.append(blended)

        return torch.cat(outputs, dim=0)

    m.set_model_attn2_patch(attn2_patch)
    m.set_model_attn2_output_patch(attn2_output_patch)

    return m, _make_preview(mask_stack)


def _empty_mask(width: int, height: int) -> torch.Tensor:
    # ComfyUI MASK can be HxW, but IPAdapter Plus expects batched masks.
    # Return 1xHxW so IPAdapterAdvanced can safely do mask.unsqueeze(1) -> Nx1xHxW.
    return torch.zeros((1, height, width), dtype=torch.float32)


def _extract_subject_masks_and_identity(scene_json: str, width: int, height: int, max_subjects: int = 4):
    """Return fixed subject MASK outputs and an identity routing plan for external IPAdapter nodes.

    This node does not vendor or call any specific IPAdapter extension. It outputs clean ComfyUI MASKs
    that can be connected to whichever IPAdapter implementation the user already has installed.
    """
    try:
        data = json.loads(scene_json)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    subjects = data.get("subjects", None)
    if not isinstance(subjects, list):
        # Legacy fallback: use character regions.
        regions = []
        for key in ("regions", "object_regions", "shared_regions"):
            value = data.get(key, [])
            if isinstance(value, list):
                regions.extend(value)
        subjects = []
        for i, r in enumerate(regions):
            if isinstance(r, dict) and _region_type(r) == "character":
                subjects.append({
                    "id": r.get("id", r.get("name", f"person_{i+1}")),
                    "bbox": None,
                    "mask": r.get("mask", None),
                    "prompt": r.get("prompt", ""),
                    "identity": r.get("identity", {}),
                })

    identity_root = data.get("identity", {}) if isinstance(data.get("identity", {}), dict) else {}
    ipadapter_root = identity_root.get("ipadapter", {}) if isinstance(identity_root.get("ipadapter", {}), dict) else {}

    masks = []
    entries = []
    for idx in range(max_subjects):
        if idx < len(subjects) and isinstance(subjects[idx], dict):
            s = subjects[idx]
            sid = str(s.get("id", f"person_{idx+1}")).strip() or f"person_{idx+1}"
            try:
                md = _bbox_to_mask(s)
                mask = _make_rect_mask(md, width, height, 1.0).clamp(0, 1)
            except Exception:
                mask = _empty_mask(width, height)
            # Slightly softer masks tend to behave better in masked IPAdapter workflows.
            feather = int(_safe_float(s.get("identity_mask_feather", s.get("feather", 18)), 18))
            if feather > 0 and mask.max().item() > 0:
                mask = _feather_mask(mask, feather).clamp(0, 1)

            identity_data = s.get("identity", {}) if isinstance(s.get("identity", {}), dict) else {}
            ipa_data = ipadapter_root.get(sid, {}) if isinstance(ipadapter_root.get(sid, {}), dict) else {}
            merged = dict(identity_data)
            merged.update(ipa_data)
            entries.append({
                "slot": idx + 1,
                "subject_id": sid,
                "mask_output": f"subject_{idx+1}_mask",
                "prompt": str(s.get("prompt", "")).strip(),
                "recommended_ipadapter_weight": _safe_float(merged.get("weight", 0.62), 0.62),
                "recommended_start_at": _safe_float(merged.get("start_at", 0.0), 0.0),
                "recommended_end_at": _safe_float(merged.get("end_at", 0.75), 0.75),
                "reference_image": str(merged.get("image", merged.get("reference_image", ""))).strip(),
                "notes": "Connect this subject mask to a masked IPAdapter node. Keep weights moderate first: 0.45-0.70."
            })
            masks.append(mask)
        else:
            masks.append(_empty_mask(width, height))

    plan = {
        "version": "0.5.2",
        "purpose": "Regional IPAdapter prep. This node outputs subject masks; external IPAdapter nodes apply the reference images.",
        "subject_count_detected": len([s for s in subjects if isinstance(s, dict)]),
        "entries": entries,
        "recommended_order": ["Run v0.5.2 with no IPAdapter first", "Add IPAdapter one subject at a time", "Use 0.45-0.70 weight", "If count breaks, lower IPAdapter weight before changing region_gain"],
    }
    return masks, json.dumps(plan, indent=2)


class NeoSceneDirector:
    @classmethod
    def INPUT_TYPES(cls):
        default_scene = json.dumps({
            "version": "0.5.2",
            "multi_subject_mode": "count_locked",
            "canvas": {"width": 1344, "height": 768},
            "camera": {"framing": "wide full body", "angle": "eye level", "lens": "50mm", "depth": "studio portrait"},
            "global_style": "realistic cinematic studio lighting, clean grey background, sharp details, high quality full body photo",
            "subjects": [
                {"id": "person_1", "bbox": [0.05, 0.08, 0.30, 0.92], "prompt": "fesci-fi soldier in white armor", "pose_type": "standing relaxed", "facing": "person_2", "required": True},
                {"id": "person_2", "bbox": [0.36, 0.08, 0.61, 0.92], "prompt": "sci-fi soldier in black armor", "pose_type": "turning slightly left", "facing": "person_1", "required": True},
                {"id": "person_3", "bbox": [0.70, 0.08, 0.95, 0.92], "prompt": "sci-fi medic in blue armor", "pose_type": "standing alert", "facing": "person_2", "required": True}
            ],
            "objects": [
                {"id": "energy_core", "bbox": [0.30, 0.38, 0.42, 0.52], "prompt": "small glowing blue energy core", "bound_to": ["person_1", "person_2"], "relation": "held between them"}
            ],
            "relations": [
                {"from": "person_1", "to": "person_2", "type": "handing_to", "object": "energy_core"},
                {"from": "person_3", "to": "person_2", "type": "looking_at"}
            ],
            "negative": "extra subjects, missing person, merged bodies, bad hands, deformed anatomy, nude, nsfw, text, watermark"
        }, indent=2)

        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "width": ("INT", {"default": 1344, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 768, "min": 64, "max": 8192, "step": 8}),
                "global_prompt_override": ("STRING", {"multiline": True, "default": ""}),
                "base_weight": ("STRING", {"default": "0.55"}),
                "region_gain": ("STRING", {"default": "0.45"}),
                "max_subject_slots": ("INT", {"default": 1, "min": 1, "max": 1, "step": 1}),
                "normalize_masks": ("BOOLEAN", {"default": True}),
                "enable_auto_prompts": ("BOOLEAN", {"default": True}),
                "scene_json": ("STRING", {"multiline": True, "default": default_scene}),
            }
        }

    RETURN_TYPES = ("MODEL", "IMAGE", "IMAGE", "STRING", "STRING", "STRING", "MASK", "MASK", "MASK", "MASK", "STRING")
    RETURN_NAMES = ("patched_model", "mask_preview", "layout_preview", "global_prompt", "negative_prompt", "debug_json", "subject_1_mask", "subject_2_mask", "subject_3_mask", "subject_4_mask", "identity_plan_json")
    FUNCTION = "patch"
    CATEGORY = "Neo Studio/Scene Director"

    def patch(self, model, clip, width, height, global_prompt_override, base_weight, region_gain, max_subject_slots, normalize_masks, enable_auto_prompts, scene_json):
        width = int(width)
        height = int(height)
        base_weight_value = _safe_float(base_weight, 0.55)
        region_gain_value = _safe_float(region_gain, 0.45)
        max_subject_slots = int(max_subject_slots)

        global_prompt, negative, branch_prompts, branch_masks, debug_json, layout_preview = _parse_scene_schema(
            scene_json=scene_json,
            width=width,
            height=height,
            global_prompt_override=global_prompt_override,
            enable_auto_prompts=bool(enable_auto_prompts),
            max_subject_slots=max_subject_slots,
        )

        region_conds = [_clip_encode_crossattn(clip, p) for p in branch_prompts]

        patched_model, preview = _patch_director(
            model=model,
            region_conds=region_conds,
            masks=branch_masks,
            base_weight=base_weight_value,
            normalize_masks=bool(normalize_masks),
            region_gain=region_gain_value,
        )

        subject_masks, identity_plan_json = _extract_subject_masks_and_identity(scene_json, width, height, max_subjects=4)

        return (
            patched_model, preview, layout_preview, global_prompt, negative, debug_json,
            subject_masks[0], subject_masks[1], subject_masks[2], subject_masks[3], identity_plan_json
        )


NODE_CLASS_MAPPINGS = {
    "NeoSceneDirectorV052": NeoSceneDirector,
    "NeoSceneDirectorV051": NeoSceneDirector,
    "NeoSceneDirectorV05": NeoSceneDirector,
    "NeoRegionalPrompterV044": NeoSceneDirector,
    "NeoRegionalPrompterV043": NeoSceneDirector,
    "NeoRegionalPrompterV042": NeoSceneDirector,
    "NeoRegionalPrompterV041": NeoSceneDirector,
    "NeoRegionalPrompterV04": NeoSceneDirector,
    "NeoCompositionDirector": NeoSceneDirector,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NeoSceneDirectorV052": "Neo Scene Director v0.5.2 (IPAdapter Region Prep)",
    "NeoSceneDirectorV051": "Neo Scene Director v0.5.2 (v0.5.1 compatible)",
    "NeoSceneDirectorV05": "Neo Scene Director v0.5.1 (v0.5 compatible)",
    "NeoRegionalPrompterV044": "Neo Scene Director v0.5 (v0.4.4 compatible)",
    "NeoRegionalPrompterV043": "Neo Scene Director v0.5 (v0.4.3 compatible)",
    "NeoRegionalPrompterV042": "Neo Scene Director v0.5 (v0.4.2 compatible)",
    "NeoRegionalPrompterV041": "Neo Scene Director v0.5 (v0.4.1 compatible)",
    "NeoRegionalPrompterV04": "Neo Scene Director v0.5 (v0.4 compatible)",
    "NeoCompositionDirector": "Neo Scene Director v0.5 (legacy compatible)",
}
