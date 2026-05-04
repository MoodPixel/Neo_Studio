from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .detailer_models import default_detailer_roots


_ORDER_MODES = {
    'auto',
    'left_to_right',
    'right_to_left',
    'top_to_bottom',
    'bottom_to_top',
    'largest_first',
    'smallest_first',
    'center_first',
}

_PRIORITY_PRESETS = {
    'respect_pass',
    'primary_subject',
    'primary_plus_secondary',
    'balanced',
    'crowd_scan',
}

_PRIORITY_PRESET_LABELS = {
    'respect_pass': 'Respect pass settings',
    'primary_subject': 'Main subject only',
    'primary_plus_secondary': 'Main + secondary',
    'balanced': 'Balanced',
    'crowd_scan': 'Crowd scan',
}

_FOREGROUND_BIAS_LABELS = {
    'off': 'Off',
    'center_bias': 'Center bias',
    'foreground_subjects': 'Foreground boost',
    'pinned_subjects': 'Pinned subjects',
}


def resolve_detailer_model_path(detector_model: str, detector_type: str = 'bbox', detector_root: str = '') -> Path | None:
    model_name = str(detector_model or '').strip()
    if not model_name:
        return None
    roots = default_detailer_roots()
    candidates: list[Path] = []
    custom_root = str(detector_root or '').strip()
    if custom_root:
        candidates.append(Path(custom_root) / model_name)
    default_dir_key = 'segm_dir' if str(detector_type or '').strip().lower() == 'segm' else 'bbox_dir'
    default_dir = str(roots.get(default_dir_key) or '').strip()
    if default_dir:
        candidates.append(Path(default_dir) / model_name)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return candidates[0] if candidates else None


def _decode_image(raw: bytes) -> tuple[np.ndarray, int, int]:
    if not raw:
        raise ValueError('Upload an image first.')
    arr = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError('Neo could not decode the uploaded image.')
    height, width = image.shape[:2]
    return image, int(width), int(height)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_keywords(mode: str, custom_classes: str) -> list[str]:
    mode_key = str(mode or '').strip().lower() or 'face'
    class_bits = [bit.strip().lower() for bit in str(custom_classes or '').replace(';', ',').split(',') if bit.strip()]
    if mode_key == 'person':
        return ['person', 'people', 'body', *class_bits]
    if mode_key == 'hands':
        return ['hand', 'hands', *class_bits]
    if mode_key == 'custom':
        return class_bits
    return ['face', 'head', *class_bits]


def _expand_box(x1: float, y1: float, x2: float, y2: float, grow: int, width: int, height: int) -> tuple[int, int, int, int]:
    pad = max(0, int(grow or 0))
    left = max(0, int(round(min(x1, x2))) - pad)
    top = max(0, int(round(min(y1, y2))) - pad)
    right = min(width, int(round(max(x1, x2))) + pad)
    bottom = min(height, int(round(max(y1, y2))) + pad)
    return left, top, max(0, right - left), max(0, bottom - top)


def _iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax1, ay1, ax2, ay2 = a['x'], a['y'], a['x'] + a['w'], a['y'] + a['h']
    bx1, by1, bx2, by2 = b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']
    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    union = max(1.0, float(a['area'] + b['area'] - inter))
    return float(inter / union)


def _nms(detections: list[dict[str, Any]], threshold: float = 0.35) -> list[dict[str, Any]]:
    if len(detections) <= 1:
        return detections
    ordered = sorted(detections, key=lambda item: (-float(item.get('confidence') or 0.0), -int(item.get('area') or 0)))
    kept: list[dict[str, Any]] = []
    for item in ordered:
        if any(_iou(item, existing) >= threshold for existing in kept):
            continue
        kept.append(item)
    return kept


def _filter_ultralytics_labels(detections: list[dict[str, Any]], mode: str, custom_classes: str, warnings: list[str]) -> list[dict[str, Any]]:
    keywords = _normalize_keywords(mode, custom_classes)
    if not keywords:
        return detections
    matched = [item for item in detections if any(keyword in str(item.get('label') or '').lower() for keyword in keywords)]
    if matched:
        return matched
    warnings.append('Detector preview labels did not map cleanly to the current target mode, so Neo kept the raw detections instead.')
    return detections


def _run_ultralytics_preview(image_bgr: np.ndarray, *, model_path: Path | None, confidence: float, mode: str, custom_classes: str, bbox_grow: int, width: int, height: int) -> tuple[list[dict[str, Any]], str]:
    if model_path is None:
        raise RuntimeError('No detector model path is available for preview.')
    if not model_path.exists():
        raise RuntimeError(f'Detector model not found: {model_path.name}')
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:
        raise RuntimeError('Ultralytics is not installed in this Python environment.') from exc

    model = YOLO(str(model_path))
    results = model.predict(source=image_bgr, conf=max(0.01, float(confidence or 0.35)), verbose=False)
    if not results:
        return [], 'ultralytics'
    result = results[0]
    names = getattr(result, 'names', None) or getattr(model, 'names', {}) or {}
    detections: list[dict[str, Any]] = []
    boxes = getattr(result, 'boxes', None)
    if boxes is None:
        return [], 'ultralytics'
    for index in range(len(boxes)):
        raw_xyxy = boxes.xyxy[index].tolist() if hasattr(boxes.xyxy[index], 'tolist') else list(boxes.xyxy[index])
        conf_val = float(boxes.conf[index].item() if hasattr(boxes.conf[index], 'item') else boxes.conf[index]) if getattr(boxes, 'conf', None) is not None else 0.0
        cls_id = int(boxes.cls[index].item() if hasattr(boxes.cls[index], 'item') else boxes.cls[index]) if getattr(boxes, 'cls', None) is not None else -1
        label = names.get(cls_id, f'class {cls_id}') if isinstance(names, dict) else str(cls_id)
        x, y, w, h = _expand_box(raw_xyxy[0], raw_xyxy[1], raw_xyxy[2], raw_xyxy[3], bbox_grow, width, height)
        if w <= 0 or h <= 0:
            continue
        detections.append({
            'id': index + 1,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'area': int(w * h),
            'confidence': round(conf_val, 4),
            'label': str(label or '').strip(),
            'source': 'auto',
            'selected': True,
        })
    warnings: list[str] = []
    detections = _filter_ultralytics_labels(detections, mode, custom_classes, warnings)
    return detections, 'ultralytics' + (f' · {warnings[0]}' if warnings else '')


def _run_face_fallback(image_bgr: np.ndarray, *, confidence: float, bbox_grow: int, width: int, height: int) -> list[dict[str, Any]]:
    """Local face preview fallback used when the real YOLO detector is unavailable.

    Earlier builds only used OpenCV's frontal-face cascade. That misses common
    ADetailer cases such as kissing/profile faces, glasses, turned heads, and
    stylized images. For the detection-preview UI this made the prompt mapper
    look broken even though the user clicked Detect targets correctly.

    This fallback now scans frontal + alt frontal + profile cascades, including
    mirrored profile detection, then NMS merges duplicates. It is still only a
    preview fallback; normal generation continues to use the configured detector
    model when available.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    detections: list[dict[str, Any]] = []

    conf = float(confidence or 0.35)
    # Keep the fallback intentionally more permissive than generation. The user
    # can ignore/remove bad boxes in the picker, but a missed target blocks the
    # per-target prompt mapper entirely.
    scan_plan = [
        ('haarcascade_frontalface_default.xml', False, 1.05 if conf < 0.45 else 1.08, 3 if conf < 0.45 else 4, 'face'),
        ('haarcascade_frontalface_alt2.xml', False, 1.05 if conf < 0.45 else 1.08, 3 if conf < 0.45 else 4, 'face'),
        ('haarcascade_profileface.xml', False, 1.05 if conf < 0.45 else 1.08, 3 if conf < 0.45 else 4, 'profile face'),
        ('haarcascade_profileface.xml', True, 1.05 if conf < 0.45 else 1.08, 3 if conf < 0.45 else 4, 'profile face'),
    ]

    next_id = 1
    for cascade_name, mirrored, scale_factor, min_neighbors, label in scan_plan:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
        if cascade.empty():
            continue
        scan_gray = cv2.flip(gray, 1) if mirrored else gray
        faces = cascade.detectMultiScale(
            scan_gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=(20, 20),
        )
        for (x, y, w, h) in faces:
            raw_x1 = int(width - (x + w)) if mirrored else int(x)
            raw_y1 = int(y)
            raw_x2 = int(width - x) if mirrored else int(x + w)
            raw_y2 = int(y + h)
            left, top, width_px, height_px = _expand_box(raw_x1, raw_y1, raw_x2, raw_y2, bbox_grow, width, height)
            if width_px <= 0 or height_px <= 0:
                continue
            detections.append({
                'id': next_id,
                'x': int(left),
                'y': int(top),
                'w': int(width_px),
                'h': int(height_px),
                'area': int(width_px * height_px),
                'confidence': round(min(0.99, 0.50 + (next_id * 0.01)), 4),
                'label': label,
                'source': 'auto',
                'selected': True,
            })
            next_id += 1

    return _nms(detections, threshold=0.25)

def _run_people_fallback(image_bgr: np.ndarray, *, bbox_grow: int, width: int, height: int) -> list[dict[str, Any]]:
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    rects, weights = hog.detectMultiScale(image_bgr, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections: list[dict[str, Any]] = []
    for index, (x, y, w, h) in enumerate(rects):
        left, top, width_px, height_px = _expand_box(x, y, x + w, y + h, bbox_grow, width, height)
        if width_px <= 0 or height_px <= 0:
            continue
        conf_val = 0.5
        if weights is not None and len(weights) > index:
            try:
                conf_val = float(weights[index])
            except Exception:
                conf_val = 0.5
        detections.append({
            'id': index + 1,
            'x': int(left),
            'y': int(top),
            'w': int(width_px),
            'h': int(height_px),
            'area': int(width_px * height_px),
            'confidence': round(max(0.01, min(0.99, conf_val)), 4),
            'label': 'person',
            'source': 'auto',
            'selected': True,
        })
    return _nms(detections)


def _sort_for_order(detections: list[dict[str, Any]], order_mode: str) -> list[dict[str, Any]]:
    mode = str(order_mode or 'auto').strip().lower() or 'auto'
    if mode not in _ORDER_MODES:
        mode = 'auto'
    if mode == 'left_to_right':
        return sorted(detections, key=lambda item: (item['x'], item['y'], -float(item.get('confidence') or 0.0)))
    if mode == 'right_to_left':
        return sorted(detections, key=lambda item: (-item['x'], item['y'], -float(item.get('confidence') or 0.0)))
    if mode == 'top_to_bottom':
        return sorted(detections, key=lambda item: (item['y'], item['x'], -float(item.get('confidence') or 0.0)))
    if mode == 'bottom_to_top':
        return sorted(detections, key=lambda item: (-item['y'], item['x'], -float(item.get('confidence') or 0.0)))
    if mode == 'largest_first':
        return sorted(detections, key=lambda item: (-item['area'], item['x'], item['y']))
    if mode == 'smallest_first':
        return sorted(detections, key=lambda item: (item['area'], item['x'], item['y']))
    if mode == 'center_first':
        if not detections:
            return []
        max_right = max((int(item.get('x') or 0) + int(item.get('w') or 0)) for item in detections)
        max_bottom = max((int(item.get('y') or 0) + int(item.get('h') or 0)) for item in detections)
        cx = max(1.0, float(max_right) / 2.0)
        cy = max(1.0, float(max_bottom) / 2.0)
        def center_distance(item):
            bx = float(item.get('x') or 0) + (float(item.get('w') or 0) / 2.0)
            by = float(item.get('y') or 0) + (float(item.get('h') or 0) / 2.0)
            return ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5
        return sorted(detections, key=lambda item: (center_distance(item), -float(item.get('confidence') or 0.0), -int(item.get('area') or 0)))
    return sorted(detections, key=lambda item: (-float(item.get('confidence') or 0.0), -item['area'], item['y'], item['x']))


def _parse_pinned_boxes(raw_value: Any) -> list[dict[str, int]]:
    if isinstance(raw_value, list):
        data = raw_value
    else:
        try:
            data = json.loads(str(raw_value or '[]'))
        except Exception:
            data = []
    pinned: list[dict[str, int]] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        x = int(item.get('x') or 0)
        y = int(item.get('y') or 0)
        w = int(item.get('w') or 0)
        h = int(item.get('h') or 0)
        if w > 0 and h > 0:
            pinned.append({'x': x, 'y': y, 'w': w, 'h': h, 'area': int(w * h)})
    return pinned


def _parse_history_boxes(raw_value: Any) -> list[dict[str, Any]]:
    rows = _parse_pinned_boxes(raw_value)
    try:
        data = json.loads(str(raw_value or '[]')) if not isinstance(raw_value, list) else raw_value
    except Exception:
        data = []
    enriched: list[dict[str, Any]] = []
    for index, item in enumerate(data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        x = int(item.get('x') or 0)
        y = int(item.get('y') or 0)
        w = int(item.get('w') or 0)
        h = int(item.get('h') or 0)
        if w <= 0 or h <= 0:
            continue
        enriched.append({
            'x': x, 'y': y, 'w': w, 'h': h, 'area': int(w * h),
            'track_id': str(item.get('track_id') or f'subject-h{index + 1}').strip() or f'subject-h{index + 1}',
            'pinned': bool(item.get('pinned')),
            'locked': bool(item.get('locked')),
        })
    return enriched or rows


def _expanded_history_contains(candidate: dict[str, Any], history_box: dict[str, Any], grow_ratio: float = 0.35) -> bool:
    cx = float(candidate.get('x') or 0) + (float(candidate.get('w') or 0) / 2.0)
    cy = float(candidate.get('y') or 0) + (float(candidate.get('h') or 0) / 2.0)
    pad_x = float(history_box.get('w') or 0) * grow_ratio
    pad_y = float(history_box.get('h') or 0) * grow_ratio
    left = float(history_box.get('x') or 0) - pad_x
    top = float(history_box.get('y') or 0) - pad_y
    right = float(history_box.get('x') or 0) + float(history_box.get('w') or 0) + pad_x
    bottom = float(history_box.get('y') or 0) + float(history_box.get('h') or 0) + pad_y
    return left <= cx <= right and top <= cy <= bottom


def _assign_track_ids(detections: list[dict[str, Any]], history_boxes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    rows = [dict(item) for item in detections]
    next_counter = 1
    for hist in history_boxes:
        track = str(hist.get('track_id') or '').strip()
        if track.startswith('subject-'):
            tail = track.split('subject-', 1)[1]
            if tail.isdigit():
                next_counter = max(next_counter, int(tail) + 1)
    reacquired_count = 0
    used_history: set[int] = set()
    for row in rows:
        best_index = -1
        best_score = 0.0
        for index, hist in enumerate(history_boxes):
            if index in used_history and not hist.get('pinned'):
                continue
            overlap = _iou({
                'x': int(row.get('x') or 0), 'y': int(row.get('y') or 0), 'w': int(row.get('w') or 0), 'h': int(row.get('h') or 0), 'area': max(1, int(row.get('area') or 0))
            }, hist)
            contains = _expanded_history_contains(row, hist)
            if overlap < 0.12 and not contains:
                continue
            score = overlap + (0.4 if hist.get('pinned') else 0.0) + (0.08 if contains else 0.0)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index >= 0:
            hist = history_boxes[best_index]
            row['track_id'] = str(hist.get('track_id') or f'subject-{next_counter}')
            if hist.get('pinned'):
                row['pinned'] = True
                row['reacquired'] = True
                reacquired_count += 1
            if not hist.get('pinned'):
                used_history.add(best_index)
        else:
            row['track_id'] = f'subject-{next_counter}'
            next_counter += 1
    return rows, reacquired_count


def _should_cluster_merge(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if str(a.get('label') or '').lower() and str(b.get('label') or '').lower() and str(a.get('label')).lower() != str(b.get('label')).lower():
        return False
    if _iou(a, b) >= 0.18:
        return True
    ax = float(a.get('x') or 0) + (float(a.get('w') or 0) / 2.0)
    ay = float(a.get('y') or 0) + (float(a.get('h') or 0) / 2.0)
    bx = float(b.get('x') or 0) + (float(b.get('w') or 0) / 2.0)
    by = float(b.get('y') or 0) + (float(b.get('h') or 0) / 2.0)
    dx = ax - bx
    dy = ay - by
    center_distance = float((dx * dx + dy * dy) ** 0.5)
    merge_radius = max(float(max(a.get('w') or 0, a.get('h') or 0)), float(max(b.get('w') or 0, b.get('h') or 0))) * 0.6
    return center_distance <= merge_radius


def _merge_detection_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    left = min(int(item.get('x') or 0) for item in cluster)
    top = min(int(item.get('y') or 0) for item in cluster)
    right = max(int(item.get('x') or 0) + int(item.get('w') or 0) for item in cluster)
    bottom = max(int(item.get('y') or 0) + int(item.get('h') or 0) for item in cluster)
    best = max(cluster, key=lambda item: (float(item.get('confidence') or 0.0), int(item.get('area') or 0)))
    width_px = max(1, right - left)
    height_px = max(1, bottom - top)
    return {
        'id': int(best.get('id') or 0),
        'x': int(left),
        'y': int(top),
        'w': int(width_px),
        'h': int(height_px),
        'area': int(width_px * height_px),
        'confidence': float(best.get('confidence') or 0.0),
        'label': str(best.get('label') or 'cluster').strip() or 'cluster',
        'source': 'auto',
        'selected': True,
        'cluster_size': len(cluster),
    }


def _merge_detection_clusters(detections: list[dict[str, Any]], enabled: bool) -> tuple[list[dict[str, Any]], int]:
    if not enabled or len(detections) <= 1:
        return detections, 0
    rows = sorted([dict(item) for item in detections], key=lambda item: (-int(item.get('area') or 0), -float(item.get('confidence') or 0.0)))
    used = [False] * len(rows)
    merged: list[dict[str, Any]] = []
    merged_count = 0
    for index, item in enumerate(rows):
        if used[index]:
            continue
        used[index] = True
        cluster = [item]
        changed = True
        while changed:
            changed = False
            for sub_index, candidate in enumerate(rows):
                if used[sub_index]:
                    continue
                if any(_should_cluster_merge(existing, candidate) for existing in cluster):
                    cluster.append(candidate)
                    used[sub_index] = True
                    changed = True
        merged.append(_merge_detection_cluster(cluster))
        merged_count += max(0, len(cluster) - 1)
    return merged, merged_count


def _pinned_overlap_score(box: dict[str, Any], pinned_boxes: list[dict[str, int]]) -> float:
    if not pinned_boxes:
        return 0.0
    best = 0.0
    candidate = {
        'x': int(box.get('x') or 0),
        'y': int(box.get('y') or 0),
        'w': int(box.get('w') or 0),
        'h': int(box.get('h') or 0),
        'area': max(1, int(box.get('area') or (int(box.get('w') or 0) * int(box.get('h') or 0)))),
    }
    for pin in pinned_boxes:
        overlap = _iou(candidate, pin)
        if overlap > best:
            best = overlap
    return best


def _build_tuning_hints(*, detections: list[dict[str, Any]], selected_count: int, suppressed_count: int, merged_cluster_count: int, cluster_merge: bool, auto_suppress_tiny_faces: bool) -> list[str]:
    hints: list[str] = []
    total = len(detections)
    if total == 0:
        hints.append('Tuning hint: try Crowd scan, lower confidence, or temporarily disable tiny-face suppression.')
        return hints
    if selected_count == 0 and suppressed_count > 0:
        hints.append('Tuning hint: too many faces were suppressed; try the Lenient preset or reduce the tiny/main ratio.')
    elif suppressed_count >= max(3, total // 2):
        hints.append('Tuning hint: this pass is suppressing a lot of detections; switch to Balanced or Lenient if it feels too aggressive.')
    elif total >= 6 and not cluster_merge and merged_cluster_count == 0:
        hints.append('Tuning hint: enable cluster merge if this image keeps producing duplicate subject boxes.')
    elif total >= 6 and auto_suppress_tiny_faces is False:
        hints.append('Tuning hint: enable tiny-face suppression if background blur keeps sneaking into the handoff.')
    return hints


def _apply_foreground_bias(detections: list[dict[str, Any]], *, mode: str, image_width: int, image_height: int, pinned_boxes: list[dict[str, int]]) -> tuple[list[dict[str, Any]], list[str]]:
    bias_mode = str(mode or 'off').strip().lower() or 'off'
    notes: list[str] = []
    if bias_mode not in _FOREGROUND_BIAS_LABELS:
        bias_mode = 'off'
    if bias_mode == 'off':
        for row in detections:
            row['selection_score'] = float(row.get('confidence') or 0.0) * 100.0 + float(row.get('area') or 0) / max(1.0, float(image_width * image_height)) * 40.0
        return detections, notes
    use_pins = bias_mode == 'pinned_subjects' and pinned_boxes
    if bias_mode == 'pinned_subjects' and not pinned_boxes:
        bias_mode = 'foreground_subjects'
        notes.append('Pinned-subject bias had no pinned targets yet, so Neo fell back to foreground boost.')
    image_area = max(1.0, float(image_width * image_height))
    center_x = float(image_width) / 2.0
    center_y = float(image_height) / 2.0
    max_distance = max(1.0, float((center_x ** 2 + center_y ** 2) ** 0.5))
    for row in detections:
        box_center_x = float(row.get('x') or 0) + (float(row.get('w') or 0) / 2.0)
        box_center_y = float(row.get('y') or 0) + (float(row.get('h') or 0) / 2.0)
        distance = float(((box_center_x - center_x) ** 2 + (box_center_y - center_y) ** 2) ** 0.5)
        center_score = max(0.0, 1.0 - (distance / max_distance))
        area_score = min(1.0, float(row.get('area') or 0) / image_area)
        confidence_score = max(0.0, min(1.0, float(row.get('confidence') or 0.0)))
        score = confidence_score * 100.0 + area_score * 40.0
        if bias_mode == 'center_bias':
            score += center_score * 30.0
        elif bias_mode == 'foreground_subjects':
            score += center_score * 22.0 + area_score * 55.0
        elif use_pins:
            overlap = _pinned_overlap_score(row, pinned_boxes)
            row['pinned_overlap'] = round(overlap, 4)
            score += overlap * 140.0 + center_score * 10.0 + area_score * 20.0
        row['selection_score'] = score
    return detections, notes


def _resolve_priority_filters(*, priority_preset: str, order_mode: str, start_index: int, count: int, top_k: int, min_area: int, max_area: int, mode: str) -> tuple[dict[str, int | str], list[str]]:
    preset = str(priority_preset or 'respect_pass').strip().lower() or 'respect_pass'
    if preset not in _PRIORITY_PRESETS:
        preset = 'respect_pass'
    effective: dict[str, int | str] = {
        'order_mode': order_mode,
        'start_index': start_index,
        'count': count,
        'top_k': top_k,
        'min_area': min_area,
        'max_area': max_area,
    }
    notes: list[str] = []
    if preset == 'primary_subject':
        if str(effective['order_mode']) == 'auto':
            effective['order_mode'] = 'largest_first'
        if int(effective['count']) <= 0:
            effective['count'] = 1
        if int(effective['top_k']) <= 0:
            effective['top_k'] = max(1, int(effective['count']))
        effective['start_index'] = 1
        notes.append('Priority preset focused the preview on the strongest main subject candidate.')
    elif preset == 'primary_plus_secondary':
        if str(effective['order_mode']) == 'auto':
            effective['order_mode'] = 'largest_first'
        if int(effective['count']) <= 0:
            effective['count'] = 2
        if int(effective['top_k']) <= 0:
            effective['top_k'] = max(2, int(effective['count']))
        effective['start_index'] = 1
        notes.append('Priority preset focused the preview on the main subject plus one secondary candidate.')
    elif preset == 'balanced':
        if str(effective['order_mode']) == 'auto' and str(mode or '').strip().lower() in {'face', 'person'}:
            effective['order_mode'] = 'left_to_right'
        if int(effective['count']) <= 0 and int(effective['top_k']) <= 0:
            effective['count'] = 3
        notes.append('Balanced preset spread the preview across the strongest few candidates.')
    elif preset == 'crowd_scan':
        if str(effective['order_mode']) == 'auto':
            effective['order_mode'] = 'left_to_right' if str(mode or '').strip().lower() in {'face', 'person'} else 'top_to_bottom'
        effective['start_index'] = 1
        effective['count'] = 0
        effective['top_k'] = 0
        notes.append('Crowd scan preset kept the broader candidate set visible for manual cleanup.')

    # Preview UX guardrail: Count should not be silently defeated by a lower
    # Top-K/candidate limit. If Count=2 but Top-K=1, users see two boxes in the
    # picker while the prompt mapper only gets one row. Raise Top-K to Count so
    # Start/Count remains the visible source of truth.
    if int(effective.get('count') or 0) > 0 and int(effective.get('top_k') or 0) > 0 and int(effective['top_k']) < int(effective['count']):
        effective['top_k'] = int(effective['count'])
        notes.append('Preview raised the candidate limit to match Count so all requested targets can be mapped.')
    return effective, notes


def _apply_tiny_background_face_suppression(
    detections: list[dict[str, Any]], *, enabled: bool, mode: str, image_width: int, image_height: int, main_ratio: float, image_floor_pct: float
) -> tuple[list[dict[str, Any]], int]:
    if not enabled or str(mode or '').strip().lower() != 'face' or len(detections) < 2:
        return detections, 0
    rows = [dict(item) for item in detections]
    image_area = max(1, int(image_width) * int(image_height))
    largest = max(int(item.get('area') or 0) for item in rows)
    if largest <= 0:
        return rows, 0
    clamped_main_ratio = max(0.05, min(0.5, float(main_ratio or 0.18)))
    clamped_image_floor_pct = max(0.01, min(5.0, float(image_floor_pct or 0.25)))
    tiny_threshold = max(int(largest * clamped_main_ratio), int(image_area * (clamped_image_floor_pct / 100.0)), 24 * 24)
    suppressed = 0
    for item in rows:
        area = int(item.get('area') or 0)
        if area <= 0 or area >= largest:
            continue
        if area < tiny_threshold and area < int(largest * 0.35):
            item['suppressed'] = True
            item['ignored'] = True
            item['selected'] = False
            item['suppressed_reason'] = 'tiny_background_face'
            item['group_key'] = 'suppressed'
            item['group_label'] = 'Suppressed tiny background faces'
            suppressed += 1
    return rows, suppressed


def _apply_selection_filters(
    detections: list[dict[str, Any]], *, top_k: int, order_mode: str, start_index: int, count: int, min_area: int, max_area: int
) -> tuple[list[dict[str, Any]], int]:
    eligible = [dict(item) for item in detections if item.get('ignored') is not True and item.get('suppressed') is not True]
    selected = list(eligible)
    if min_area > 0:
        selected = [item for item in selected if int(item.get('area') or 0) >= int(min_area)]
    if max_area > 0:
        selected = [item for item in selected if int(item.get('area') or 0) <= int(max_area)]
    selected = sorted(selected, key=lambda item: (-float(item.get('selection_score') or 0.0), -float(item.get('confidence') or 0.0), -int(item.get('area') or 0), item['y'], item['x']))
    if top_k > 0:
        selected = selected[:int(top_k)]
    selected = _sort_for_order(selected, order_mode)
    start_offset = max(0, int(start_index or 1) - 1)
    if start_offset:
        selected = selected[start_offset:]
    if int(count or 0) > 0:
        selected = selected[:int(count)]
    selected_ids = {int(item.get('id') or 0) for item in selected}
    final_rows: list[dict[str, Any]] = []
    for item in _sort_for_order(detections, order_mode):
        row = dict(item)
        row['selected'] = int(item.get('id') or 0) in selected_ids and row.get('ignored') is not True and row.get('suppressed') is not True
        final_rows.append(row)
    return final_rows, len(selected_ids)


def _annotate_detection_groups(rows: list[dict[str, Any]]) -> None:
    rank = 0
    for row in rows:
        if row.get('pinned'):
            row['group_key'] = 'pinned'
            row['group_label'] = 'Pinned subjects'
            row['priority_rank'] = 0
            continue
        if row.get('suppressed') or row.get('ignored'):
            row['group_key'] = row.get('group_key') or 'suppressed'
            row['group_label'] = row.get('group_label') or 'Suppressed / ignored targets'
            row['priority_rank'] = 0
            continue
        if row.get('selected'):
            rank += 1
            row['priority_rank'] = rank
            if rank == 1:
                row['group_key'] = 'primary'
                row['group_label'] = 'Primary subject'
            elif rank <= 3:
                row['group_key'] = 'secondary'
                row['group_label'] = 'Secondary targets'
            else:
                row['group_key'] = 'active'
                row['group_label'] = 'Additional active targets'
        else:
            row['priority_rank'] = 0
            row['group_key'] = 'skipped'
            row['group_label'] = 'Skipped by current filters'


def preview_detailer_detections(raw_image: bytes, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(settings or {})
    image_bgr, width, height = _decode_image(raw_image)
    provider = str(payload.get('provider') or 'ultralytics').strip().lower() or 'ultralytics'
    mode = str(payload.get('mode') or 'face').strip().lower() or 'face'
    detector_type = str(payload.get('detector_type') or 'bbox').strip().lower() or 'bbox'
    detector_model = str(payload.get('detector_model') or '').strip()
    detector_root = str(payload.get('custom_detector_root') or payload.get('detector_root') or '').strip()
    custom_classes = str(payload.get('custom_classes') or '').strip()
    confidence = max(0.01, min(0.99, float(payload.get('confidence') or 0.35)))
    top_k = max(0, int(payload.get('top_k') or 0))
    bbox_grow = max(0, int(payload.get('bbox_grow') or 0))
    order_mode = str(payload.get('order_mode') or 'auto').strip().lower() or 'auto'
    start_index = max(1, int(payload.get('start_index') or 1))
    count = max(0, int(payload.get('count') or 0))
    min_area = max(0, int(payload.get('min_area') or 0))
    max_area = max(0, int(payload.get('max_area') or 0))
    priority_preset = str(payload.get('priority_preset') or 'respect_pass').strip().lower() or 'respect_pass'
    if priority_preset not in _PRIORITY_PRESETS:
        priority_preset = 'respect_pass'
    auto_suppress_tiny_faces = _as_bool(payload.get('auto_suppress_tiny_faces'), True)
    cluster_merge = _as_bool(payload.get('cluster_merge'), True)
    foreground_bias = str(payload.get('foreground_bias') or 'off').strip().lower() or 'off'
    pinned_boxes = _parse_pinned_boxes(payload.get('pinned_boxes'))
    history_boxes = _parse_history_boxes(payload.get('history_boxes'))
    if not pinned_boxes:
        pinned_boxes = [dict(item) for item in history_boxes if item.get('pinned')]
    tiny_face_main_ratio = max(0.05, min(0.5, float(payload.get('tiny_face_main_ratio') or 0.18)))
    tiny_face_image_floor_pct = max(0.01, min(5.0, float(payload.get('tiny_face_image_floor_pct') or 0.25)))

    warnings: list[str] = []
    strategy = 'opencv-fallback'
    resolved_model = resolve_detailer_model_path(detector_model, detector_type=detector_type, detector_root=detector_root)
    detections: list[dict[str, Any]] = []

    if provider == 'ultralytics' and detector_model:
        try:
            detections, strategy = _run_ultralytics_preview(
                image_bgr,
                model_path=resolved_model,
                confidence=confidence,
                mode=mode,
                custom_classes=custom_classes,
                bbox_grow=bbox_grow,
                width=width,
                height=height,
            )
        except Exception as exc:
            warnings.append(f'Ultralytics preview fallback: {exc}')

    if not detections:
        fallback_mode = mode
        keywords = _normalize_keywords(mode, custom_classes)
        if fallback_mode == 'custom':
            if any(key in {'person', 'people', 'body'} for key in keywords):
                fallback_mode = 'person'
            else:
                fallback_mode = 'face'
        if fallback_mode == 'person':
            detections = _run_people_fallback(image_bgr, bbox_grow=bbox_grow, width=width, height=height)
            strategy = 'opencv-hog-person'
        elif fallback_mode == 'hands':
            warnings.append('Hands preview does not have a strong local fallback in this environment, so Neo is using the face preview detector as a rough stand-in.')
            detections = _run_face_fallback(image_bgr, confidence=confidence, bbox_grow=bbox_grow, width=width, height=height)
            strategy = 'opencv-face-fallback'
        else:
            detections = _run_face_fallback(image_bgr, confidence=confidence, bbox_grow=bbox_grow, width=width, height=height)
            strategy = 'opencv-face'

    detections = [item for item in detections if int(item.get('w') or 0) > 0 and int(item.get('h') or 0) > 0]
    for index, item in enumerate(detections, start=1):
        item['id'] = index
        item['area'] = int(item.get('w') or 0) * int(item.get('h') or 0)
        item['suppressed'] = bool(item.get('suppressed'))
        item['ignored'] = bool(item.get('ignored'))
        item['pinned'] = bool(item.get('pinned'))
        item['cluster_size'] = int(item.get('cluster_size') or 1)
        item['suppressed_reason'] = str(item.get('suppressed_reason') or '')

    detections, merged_cluster_count = _merge_detection_clusters(detections, cluster_merge)
    for index, item in enumerate(detections, start=1):
        item['id'] = index
        item['area'] = int(item.get('w') or 0) * int(item.get('h') or 0)
        item['pinned'] = _pinned_overlap_score(item, pinned_boxes) >= 0.65 if pinned_boxes else False
        item['cluster_size'] = int(item.get('cluster_size') or 1)
    detections, reacquired_pinned_count = _assign_track_ids(detections, history_boxes)
    detections, bias_notes = _apply_foreground_bias(
        detections,
        mode=foreground_bias,
        image_width=width,
        image_height=height,
        pinned_boxes=pinned_boxes,
    )
    warnings.extend(note for note in bias_notes if note)

    detections, suppressed_count = _apply_tiny_background_face_suppression(
        detections,
        enabled=auto_suppress_tiny_faces,
        mode=mode,
        image_width=width,
        image_height=height,
        main_ratio=tiny_face_main_ratio,
        image_floor_pct=tiny_face_image_floor_pct,
    )
    if suppressed_count:
        warnings.append(f'Neo auto-suppressed {suppressed_count} tiny background face candidate(s) during preview.')

    effective_filters, preset_notes = _resolve_priority_filters(
        priority_preset=priority_preset,
        order_mode=order_mode,
        start_index=start_index,
        count=count,
        top_k=top_k,
        min_area=min_area,
        max_area=max_area,
        mode=mode,
    )
    warnings.extend(note for note in preset_notes if note)

    detections, selected_count = _apply_selection_filters(
        detections,
        top_k=int(effective_filters['top_k']),
        order_mode=str(effective_filters['order_mode']),
        start_index=int(effective_filters['start_index']),
        count=int(effective_filters['count']),
        min_area=int(effective_filters['min_area']),
        max_area=int(effective_filters['max_area']),
    )
    _annotate_detection_groups(detections)
    target_number = 0
    for row_index, row in enumerate(detections, start=1):
        row['ordered_index'] = row_index
        if row.get('selected') and not row.get('ignored') and not row.get('suppressed'):
            target_number += 1
            row['target_index'] = target_number
            row['prompt_index'] = target_number
            row['number_label'] = f'#{target_number}'
        else:
            row['target_index'] = 0
            row['prompt_index'] = 0
            row['number_label'] = ''
    tuning_hints = _build_tuning_hints(
        detections=detections,
        selected_count=selected_count,
        suppressed_count=suppressed_count,
        merged_cluster_count=merged_cluster_count,
        cluster_merge=cluster_merge,
        auto_suppress_tiny_faces=auto_suppress_tiny_faces,
    )
    message = f'Detector preview found {len(detections)} target(s); {selected_count} currently selected for manual-box handoff.'
    if suppressed_count:
        message += f' {suppressed_count} tiny background face candidate(s) were auto-suppressed.'
    if not detections:
        message = 'Detector preview did not find any usable targets on this image.'
        warnings.append('Try lowering confidence, switching target order, or using manual boxes for exact control.')
    return {
        'ok': True,
        'image_width': width,
        'image_height': height,
        'preview_mode': strategy,
        'resolved_model_path': str(resolved_model) if resolved_model else '',
        'detections': detections,
        'selected_count': selected_count,
        'suppressed_count': suppressed_count,
        'merged_cluster_count': merged_cluster_count,
        'reacquired_pinned_count': reacquired_pinned_count,
        'priority_preset': priority_preset,
        'foreground_bias': foreground_bias,
        'foreground_bias_label': _FOREGROUND_BIAS_LABELS.get(foreground_bias, 'Off'),
        'priority_preset_label': _PRIORITY_PRESET_LABELS.get(priority_preset, 'Respect pass settings'),
        'effective_filters': effective_filters,
        'target_order': str(effective_filters.get('order_mode') or order_mode),
        'suppression_settings': {
            'auto_suppress_tiny_faces': auto_suppress_tiny_faces,
            'tiny_face_main_ratio': tiny_face_main_ratio,
            'tiny_face_image_floor_pct': tiny_face_image_floor_pct,
            'cluster_merge': cluster_merge,
            'foreground_bias': foreground_bias,
        },
        'message': message,
        'warnings': warnings,
        'tuning_hints': tuning_hints,
    }
