
# Prompt Suite Injector (Forge-safe)
# - Queues precomputed maps (canny/depth/openpose) to ControlNet units
# - Applies on next Generate via scripts.Script.process()

import os
from typing import Any, Dict

import gradio as gr
import modules.scripts as scripts

# ControlNet bridge (Forge integrated or classic)
cn_ext = None
try:
    from internal_controlnet import external_code as cn_ext  # Forge integrated CN
except Exception:
    try:
        from scripts import external_code as cn_ext  # classic CN extension
    except Exception:
        cn_ext = None

np = None
Image = None
try:
    import numpy as np
    from PIL import Image
except Exception:
    np = None
    Image = None

# Pending ControlNet injections.
# Keys are integer unit indices (0..N). This keeps UI routing flexible.
PENDING: Dict[Any, Any] = {
    "armed": False,
}


def _iter_pending_unit_indices() -> list[int]:
    keys = []
    for k in PENDING.keys():
        if isinstance(k, int):
            keys.append(k)
    keys.sort()
    return keys

def queue_cn(unit_idx: int, kind: str, path: str, weight: float = 1.0):
    path = (path or "").strip()
    if not path:
        return
    try:
        w = float(weight)
    except Exception:
        w = 1.0
    PENDING[unit_idx] = {"kind": kind, "path": path, "weight": w}
    PENDING["armed"] = True

def clear_queue():
    for i in _iter_pending_unit_indices():
        PENDING.pop(i, None)
    PENDING["armed"] = False

def _load_rgb_np(path: str):
    im = Image.open(path).convert("RGB")
    return np.array(im, dtype=np.uint8)

def apply_pending_to_controlnet(p):
    """Called from Script.process() right before generation work starts."""
    if cn_ext is None or np is None or Image is None:
        return
    if not PENDING.get("armed"):
        return
    if not hasattr(cn_ext, "get_all_units_in_processing") or not hasattr(cn_ext, "update_cn_script_in_processing"):
        return

    try:
        units = cn_ext.get_all_units_in_processing(p)

        # Determine how many units we can/should touch.
        try:
            max_models = int(cn_ext.get_max_models_num())
        except Exception:
            max_models = max(3, len(units))

        pending_idxs = _iter_pending_unit_indices()
        if not pending_idxs:
            return
        need = min(max_models, max(pending_idxs) + 1)

        while len(units) < need:
            try:
                units.append(cn_ext.ControlNetUnit(enabled=False))
            except Exception:
                break

        for unit_idx in pending_idxs:
            item = PENDING.get(unit_idx, {})
            path = (item.get("path") or "").strip()
            if not path or not os.path.exists(path):
                continue
            if unit_idx >= len(units):
                continue

            img = _load_rgb_np(path)
            u = units[unit_idx]

            # Precomputed maps => module "none"
            try:
                u.enabled = True
                u.module = "none"
                u.image = {"image": img}
            except Exception:
                try:
                    u.image = img
                    u.enabled = True
                except Exception:
                    pass

            # Optional strength/weight
            try:
                w = float(item.get("weight", 1.0) or 1.0)
            except Exception:
                w = 1.0
            for attr in ("weight", "control_weight"):
                if hasattr(u, attr):
                    try:
                        setattr(u, attr, w)
                    except Exception:
                        pass

        cn_ext.update_cn_script_in_processing(p, units)

    finally:
        clear_queue()


class Script(scripts.Script):
    def title(self):
        return "Prompt Suite Injector"

    def show(self, is_img2img):
        try:
            return scripts.AlwaysVisible
        except Exception:
            return True

    def ui(self, is_img2img):
        enabled = gr.Checkbox(value=True, label="Prompt Suite Injector", visible=False)
        return [enabled]

    def process(self, p, enabled=True, *args, **kwargs):
        if not enabled:
            return
        apply_pending_to_controlnet(p)
