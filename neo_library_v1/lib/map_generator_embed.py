import os
import sys
import json
import subprocess
import shutil
import datetime
import uuid
import urllib.request
from pathlib import Path

try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path
import gradio as gr

# Optional: integrate with Vault MapSets (for one-click saving)
try:
    from vault_store import VaultStore
except Exception:
    VaultStore = None

EXT_ROOT = Path(__file__).resolve().parents[1]  # .../extensions/prompt_suite_bridge
DEFAULT_SCRIPT = str(EXT_ROOT / "tools" / "batch_hints.py")
SETTINGS_PATH = library_data_path('mapgen_settings.json', legacy_rel='mapgen_settings.json', default_json={})


def _open_folder(path: str) -> str:
    """Best-effort open folder in OS file explorer."""
    p = (path or "").strip()
    if not p:
        return "⚠️ No folder path."
    try:
        if not os.path.exists(p):
            return f"⚠️ Folder not found: {p}"
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
        return f"✅ Opened: {p}"
    except Exception as e:
        return f"⚠️ Could not open folder: {e}"


def _norm_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("_", " ")
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace() or ch in "-+")
    s = " ".join(s.split())
    return s


def _gather_maps_from_out(out_eff: str) -> dict:
    """Collect generated maps under out_eff/<type>/** (type in canny/openpose/depth)."""
    base = Path((out_eff or "").strip())
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    out = {"canny": [], "openpose": [], "depth": []}
    if not base.exists():
        return out
    for t in ("canny", "openpose", "depth"):
        root = base / t
        if not root.exists():
            continue
        for fp in root.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in exts:
                out[t].append(str(fp))
    return out


def _register_out_as_mapset(out_eff: str, mapset_title: str, enforce_suffix: bool = True) -> str:
    if VaultStore is None:
        return "⚠️ VaultStore not available. (Import failed)"
    out_eff = (out_eff or "").strip()
    if not out_eff:
        return "⚠️ No output folder."
    if not os.path.exists(out_eff):
        return f"⚠️ Output folder not found: {out_eff}"
    title = (mapset_title or "").strip() or Path(out_eff).name

    s = VaultStore()
    # Try reuse existing mapset by title (normalized match)
    mid = ""
    want = _norm_title(title)
    for m in (s.data.get("mapsets") or []):
        if _norm_title(m.get("title") or "") == want:
            mid = m.get("id") or ""
            break
    if not mid:
        mid = s.create_mapset(title, "")

    files_by_type = _gather_maps_from_out(out_eff)
    total = 0
    # Classify by folder, not filename.
    for t, files in files_by_type.items():
        if not files:
            continue
        total += s.add_maps_to_mapset(mid, files, map_type=t, auto_detect=False, enforce_suffix=enforce_suffix)

    if total == 0:
        return "⚠️ No maps found to import. Make sure you generated maps first."
    return f"✅ Registered output as mapset: **{title}** (imported {total} map(s))"


# -------------------------
# Settings helpers
# -------------------------

def _load_settings():
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass

    # Defaults (mirrors tools/batch_hints.py defaults as much as possible)
    return {
        "python_exe": "",
        "script_path": DEFAULT_SCRIPT,
        "in_dir": "",
        "out_dir": "",
        "mapset_name": "",

        # Core
        "mode": "cover",
        "detect": 512,
        "portrait_size": "896x1344",
        "landscape_size": "1344x896",
        "name_suffix": True,

        # What to generate
        "do_canny": True,
        "do_openpose": True,
        "do_depth": False,
        "do_lineart": False,
        "do_lineart_anime": False,
        "do_softedge": False,
        "do_scribble": False,
        "do_normalbae": False,

        # Canny
        "canny_low": 150,
        "canny_high": 300,
        "blur": 3,
        "clahe": False,
        "sharpen": False,
        "denoise": False,
        "canny_invert": False,
        "canny_thickness": "none",
        "canny_adaptive": False,
        "canny_clean_bg": False,
        "canny_clean_thresh": 128,
        "canny_speckle": "none",

        # OpenPose
        "device": "cpu",
        "hands": False,
        "face": False,

        # Depth
        "depth_device": "cpu",
        "depth_invert": False,

        # Scan
        "recursive": False,
        "skip_existing": True,

        # Overlay
        "overlay_png": "",
        "overlay_png_pos": "bottom-right",
        "overlay_png_scale": 0.25,
        "overlay_png_opacity": 1.0,
        "overlay_png_offx": 0,
        "overlay_png_offy": 0,
        "overlay_text": "",
        "overlay_text_size": 28,
        "overlay_text_color": "#FFFFFF",
        "overlay_text_outline": False,
        "overlay_text_outline_color": "#000000",
        "overlay_text_pos": "bottom-right",
        "overlay_text_offx": 0,
        "overlay_text_offy": 0,

        # ComfyUI / ControlNet audit + Phase 2 preprocessor backend
        "backend": "auto",
        "comfy_url": "http://127.0.0.1:8188",
        "comfy_root": "",

        # CN mapping (Single outputs → ControlNet)
        "weight_canny": 1.0,
        "weight_pose": 1.0,
        "weight_depth": 1.0,
        "unit_canny": 0,
        "unit_pose": 1,
        "unit_depth": 2,
    }


def _save_settings(d: dict):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(SETTINGS_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(str(tmp), str(SETTINGS_PATH))
        except Exception:
            SETTINGS_PATH.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


# -------------------------
# Phase 1: ComfyUI / ControlNet audit helpers
# -------------------------

def _as_base_url(url: str) -> str:
    url = (url or "").strip() or "http://127.0.0.1:8188"
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def _fetch_comfy_json(base_url: str, endpoint: str, timeout: float = 6.0):
    url = _as_base_url(base_url) + endpoint
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NeoStudio-ControlNet-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def _find_first_node(nodes: set[str], candidates: list[str]) -> str:
    for name in candidates:
        if name in nodes:
            return name
    return ""


def _find_matching_nodes(nodes: set[str], keywords: list[str], limit: int = 18) -> list[str]:
    out = []
    for n in sorted(nodes, key=str.lower):
        low = n.lower()
        if all(k.lower() in low for k in keywords):
            out.append(n)
            if len(out) >= limit:
                break
    return out


def _scan_model_files(root: str) -> dict:
    result = {"root_exists": False, "controlnet_models": [], "depthanything_models": [], "notes": []}
    root = (root or "").strip().strip('"')
    if not root:
        result["notes"].append("ComfyUI root not set; model folder scan skipped.")
        return result
    base = Path(root)
    if not base.exists():
        result["notes"].append(f"ComfyUI root not found: {base}")
        return result
    result["root_exists"] = True
    model_exts = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
    for key, folder in [("controlnet_models", base / "models" / "controlnet"), ("depthanything_models", base / "models" / "depthanything")]:
        if not folder.exists():
            result["notes"].append(f"Missing folder: {folder}")
            continue
        found = []
        for fp in folder.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in model_exts:
                try:
                    found.append(str(fp.relative_to(folder)).replace("\\", "/"))
                except Exception:
                    found.append(fp.name)
            if len(found) >= 60:
                break
        result[key] = sorted(found, key=str.lower)
    return result


def _audit_controlnet_stack(comfy_url: str, comfy_root: str = "") -> tuple[str, str]:
    report = {
        "ok": False,
        "checked_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "comfy_url": _as_base_url(comfy_url),
        "comfy_root": (comfy_root or "").strip(),
        "server": {},
        "nodes": {},
        "extensions": {},
        "preprocessors": {},
        "controlnet_apply": {},
        "models": {},
        "recommendations": [],
        "errors": [],
    }
    try:
        object_info = _fetch_comfy_json(report["comfy_url"], "/object_info")
        nodes = set(object_info.keys()) if isinstance(object_info, dict) else set()
        report["ok"] = True
        report["server"]["object_info_nodes"] = len(nodes)
    except Exception as exc:
        report["errors"].append(f"Could not read ComfyUI /object_info: {exc}")
        md = "### 🧪 ControlNet Audit\n\n❌ **ComfyUI not reachable.** Start ComfyUI, confirm the URL, then run the audit again.\n\n" + f"URL checked: `{report['comfy_url']}`"
        return md, json.dumps(report, indent=2, ensure_ascii=False)

    aux_matches = _find_matching_nodes(nodes, ["preprocessor"], 80) + _find_matching_nodes(nodes, ["aux"], 30)
    standard_apply = _find_first_node(nodes, ["ControlNetApply", "ControlNetApplyAdvanced", "Apply ControlNet"])
    advanced_apply = _find_first_node(nodes, ["ACN_AdvancedControlNetApply", "ACN_AdvancedControlNetApplySingle", "AdvancedControlNetApply", "ControlNetApplyAdvanced", "Apply Advanced ControlNet"])
    preprocessors = {
        "canny": _find_first_node(nodes, ["CannyEdgePreprocessor", "CannyPreprocessor", "Canny", "AIO Aux Preprocessor"]),
        "openpose": _find_first_node(nodes, ["DWPreprocessor", "OpenposePreprocessor", "OpenPosePreprocessor", "AIO Aux Preprocessor"]),
        "depth": _find_first_node(nodes, ["DepthAnythingV2Preprocessor", "DepthAnythingPreprocessor", "MiDaSDepthMapPreprocessor", "Zoe_DepthAnythingPreprocessor", "AIO Aux Preprocessor"]),
        "lineart": _find_first_node(nodes, ["LineArtPreprocessor", "LineartPreprocessor", "LineartAnimePreprocessor", "AIO Aux Preprocessor"]),
        "softedge": _find_first_node(nodes, ["HEDPreprocessor", "SoftEdgePreprocessor", "AnyLinePreprocessor", "AIO Aux Preprocessor"]),
        "normalbae": _find_first_node(nodes, ["BAE-NormalMapPreprocessor", "NormalBaePreprocessor", "AIO Aux Preprocessor"]),
    }
    report["nodes"] = {
        "canny_matches": _find_matching_nodes(nodes, ["canny"], 50),
        "openpose_matches": _find_matching_nodes(nodes, ["pose"], 80),
        "depth_matches": _find_matching_nodes(nodes, ["depth"], 80),
        "lineart_matches": _find_matching_nodes(nodes, ["lineart"], 50),
        "preprocessor_matches": sorted(set(aux_matches), key=str.lower)[:120],
    }
    report["extensions"] = {
        "controlnet_aux_likely": bool(aux_matches or any(preprocessors.values())),
        "advanced_controlnet_likely": bool(advanced_apply or _find_matching_nodes(nodes, ["advanced", "controlnet"], 10) or _find_matching_nodes(nodes, ["acn"], 10)),
        "depthanything_v2_likely": bool(preprocessors["depth"] == "DepthAnythingV2Preprocessor" or _find_matching_nodes(nodes, ["depthanythingv2"], 10) or _find_matching_nodes(nodes, ["depth", "anything", "v2"], 10)),
    }
    report["preprocessors"] = preprocessors
    report["controlnet_apply"] = {"standard": standard_apply, "advanced": advanced_apply}
    report["models"] = _scan_model_files(comfy_root)
    if not report["extensions"]["controlnet_aux_likely"]:
        report["recommendations"].append("Install/enable comfyui_controlnet_aux for proper Canny, OpenPose, Lineart, SoftEdge, Scribble, and depth preprocessors.")
    if not report["extensions"]["depthanything_v2_likely"]:
        report["recommendations"].append("Install/enable ComfyUI-DepthAnythingV2 for better depth maps than MiDaS fallback.")
    if not report["extensions"]["advanced_controlnet_likely"]:
        report["recommendations"].append("Advanced-ControlNet not detected. Fine for Phase 1-6; add it later for masked/scheduled ControlNet.")
    if not standard_apply and not advanced_apply:
        report["recommendations"].append("No ControlNet apply node detected. Install ControlNet support/models before generation workflows.")
    def status_icon(v):
        return "✅" if v else "⚠️"
    rows = ["### 🧪 ControlNet Audit", "", f"ComfyUI: **reachable** at `{report['comfy_url']}`  ", f"Detected nodes: **{len(nodes)}**", "", "| Area | Status | Detected |", "|---|---:|---|"]
    rows.append(f"| ControlNet Aux | {status_icon(report['extensions']['controlnet_aux_likely'])} | `{', '.join([v for v in preprocessors.values() if v][:6]) or 'not found'}` |")
    rows.append(f"| DepthAnythingV2 | {status_icon(report['extensions']['depthanything_v2_likely'])} | `{preprocessors['depth'] or 'not found'}` |")
    rows.append(f"| Advanced-ControlNet | {status_icon(report['extensions']['advanced_controlnet_likely'])} | `{advanced_apply or 'not found'}` |")
    rows.append(f"| Standard ControlNet apply | {status_icon(bool(standard_apply))} | `{standard_apply or 'not found'}` |")
    rows += ["", "| Preprocessor | Best node Neo can use now |", "|---|---|"]
    for key in ["canny", "openpose", "depth", "lineart", "softedge", "normalbae"]:
        rows.append(f"| {key} | `{preprocessors.get(key) or 'fallback / missing'}` |")
    if report["models"].get("root_exists"):
        rows += ["", f"ControlNet models found: **{len(report['models'].get('controlnet_models') or [])}**  ", f"DepthAnything models found: **{len(report['models'].get('depthanything_models') or [])}**"]
    if report["recommendations"]:
        rows += ["", "**Next fixes:**"]
        for rec in report["recommendations"][:6]:
            rows.append(f"- {rec}")
    rows += ["", "Raw JSON below is useful for debugging node-name differences."]
    return "\n".join(rows), json.dumps(report, indent=2, ensure_ascii=False)


# -------------------------
# Path helpers
# -------------------------

def _sanitize_name(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\\", "/").strip("/")
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", " "):
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out).strip()
    s = s.replace("  ", " ").replace(" ", "_")
    return s[:80]


def _effective_out_dir(out_dir: str, mapset_name: str) -> str:
    base = Path((out_dir or "").strip())
    name = _sanitize_name(mapset_name)
    if not name:
        return str(base)
    return str((base / name))


def _run_cmd(py: str, args: list) -> tuple[int, str]:
    try:
        if not py:
            py = sys.executable
        p = subprocess.run([py] + args, capture_output=True, text=True)
        out = (p.stdout or "")
        if p.stderr:
            out += ("\n" if out else "") + p.stderr
        return p.returncode, out.strip()
    except Exception as e:
        return 1, f"Exception: {e}"


def _list_images(in_dir: str):
    p = Path((in_dir or "").strip())
    if not p.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    files = []
    for fp in p.rglob("*"):
        if fp.is_file() and fp.suffix.lower() in exts:
            try:
                rel = fp.relative_to(p)
                files.append(str(rel).replace("\\", "/"))
            except Exception:
                files.append(fp.name)
    files.sort()
    return files[:5000]


def _find_single_outputs(out_dir_eff: str, input_rel: str, want_suffix: bool = True):
    base = Path(out_dir_eff)
    stem = Path(str(Path(input_rel).with_suffix("")).replace("\\", "/"))
    key_name = stem.name
    key_parent = stem.parent

    def pick(kind: str, suf: str):
        for orient in ("vertical", "landscape"):
            p = base / kind / orient / key_parent
            if want_suffix:
                fp = p / f"{key_name}{suf}.png"
            else:
                fp = p / f"{key_name}.png"
            if fp.exists():
                return str(fp)
        return ""

    return {
        "canny": pick("canny", "_canny"),
        "openpose": pick("openpose", "_openpose"),
        "depth": pick("depth", "_depth"),
    }


# -------------------------
# UI
# -------------------------

def build_map_generator_ui(queue_cb, clear_queue_cb):
    """
    Builds UI inside the current gradio Blocks context.

    queue_cb(kind:str, unit_idx:int, path:str, weight:float) -> str
    clear_queue_cb() -> str
    """

    s = _load_settings()

    # Size templates (SDXL-friendly)
    PORTRAIT_TEMPLATES = [
        "768x1152",
        "832x1216",
        "896x1344",
        "1024x1536",
        "1152x1728",
        "1216x1824",
    ]
    LANDSCAPE_TEMPLATES = [
        "1152x768",
        "1216x832",
        "1344x896",
        "1536x1024",
        "1728x1152",
        "1824x1216",
    ]

    gr.Markdown("## 🧪 Map Generator")
    gr.Markdown("Generate **Canny / OpenPose / Depth** maps and feed them to ControlNet.")

    # -------------------------
    # Settings
    # -------------------------
    with gr.Accordion("Settings", open=True):
        python_exe = gr.Textbox(
            value=s.get("python_exe", ""),
            label="Worker Python exe (recommended)",
            placeholder=r"F:\\MyTools\\cn_hints\\cn_hints_env\\Scripts\\python.exe",
        )
        script_path = gr.Textbox(value=s.get("script_path", DEFAULT_SCRIPT), label="Worker script path", interactive=False)
        backend = gr.Dropdown(
            choices=["auto", "local", "comfy"],
            value=str(s.get("backend", "auto")),
            label="Phase 2 map backend",
            info="auto = legacy local for Canny/OpenPose/Depth, ComfyUI Aux for extra maps; comfy = use ComfyUI preprocessors for all selected maps.",
        )

        with gr.Accordion("Phase 1 — ControlNet node audit", open=False):
            gr.Markdown("Checks ComfyUI `/object_info`, detects ControlNet Aux / DepthAnythingV2 / Advanced-ControlNet nodes, and optionally scans local model folders.")
            with gr.Row():
                comfy_url = gr.Textbox(value=s.get("comfy_url", "http://127.0.0.1:8188"), label="ComfyUI URL", placeholder="http://127.0.0.1:8188")
                comfy_root = gr.Textbox(value=s.get("comfy_root", ""), label="ComfyUI root folder (optional, for model scan)", placeholder=r"F:\ComfyUI")
            btn_audit_cn = gr.Button("🧪 Run ControlNet audit", variant="secondary")
            audit_summary = gr.Markdown(value="Run the audit after ComfyUI is open.")
            audit_json = gr.Code(value="{}", language="json", label="Audit JSON report")

        with gr.Row():
            in_dir = gr.Textbox(value=s.get("in_dir", ""), label="Input folder (in_dir)", placeholder=r"F:\\datasets\\images")
            out_dir = gr.Textbox(value=s.get("out_dir", ""), label="Output root (out_dir)", placeholder=r"F:\\maps_library")

        mapset_name = gr.Textbox(value=s.get("mapset_name", ""), label="MapSet name (optional)", placeholder="piggyback_pose_a")

        eff_out_dir = gr.Textbox(
            value=_effective_out_dir(s.get("out_dir", ""), s.get("mapset_name", "")),
            label="Effective output folder (out_dir/MapSet name)",
            interactive=False,
        )

        with gr.Row():
            btn_open_eff = gr.Button("📁 Open effective output folder", scale=0)
            btn_register_eff = gr.Button("💾 Register output as Vault Mapset", scale=0)
        register_status = gr.Textbox(value="", label="Register status", lines=2, interactive=False)

        with gr.Row():
            mode = gr.Dropdown(choices=["cover", "contain"], value=s.get("mode", "cover"), label="Fit mode")
            detect = gr.Slider(64, 2048, value=int(s.get("detect", 512)), step=64, label="Detect resolution")
            name_suffix = gr.Checkbox(value=bool(s.get("name_suffix", True)), label="Append _canny/_openpose/_depth")

        # Size templates + custom fields
        with gr.Row():
            portrait_tpl = gr.Dropdown(
                choices=PORTRAIT_TEMPLATES + ["Custom"],
                value=s.get("portrait_size", "896x1344") if s.get("portrait_size", "896x1344") in PORTRAIT_TEMPLATES else "Custom",
                label="Portrait size template",
            )
            landscape_tpl = gr.Dropdown(
                choices=LANDSCAPE_TEMPLATES + ["Custom"],
                value=s.get("landscape_size", "1344x896") if s.get("landscape_size", "1344x896") in LANDSCAPE_TEMPLATES else "Custom",
                label="Landscape size template",
            )

        with gr.Row():
            portrait_size = gr.Textbox(value=s.get("portrait_size", "896x1344"), label="Portrait size (WxH)")
            landscape_size = gr.Textbox(value=s.get("landscape_size", "1344x896"), label="Landscape size (WxH)")

        with gr.Row():
            do_canny = gr.Checkbox(value=bool(s.get("do_canny", True)), label="Generate Canny")
            do_openpose = gr.Checkbox(value=bool(s.get("do_openpose", True)), label="Generate OpenPose")
            do_depth = gr.Checkbox(value=bool(s.get("do_depth", False)), label="Generate Depth")

        with gr.Row():
            do_lineart = gr.Checkbox(value=bool(s.get("do_lineart", False)), label="Generate Lineart")
            do_lineart_anime = gr.Checkbox(value=bool(s.get("do_lineart_anime", False)), label="Generate Lineart Anime")
            do_softedge = gr.Checkbox(value=bool(s.get("do_softedge", False)), label="Generate SoftEdge / HED")

        with gr.Row():
            do_scribble = gr.Checkbox(value=bool(s.get("do_scribble", False)), label="Generate Scribble")
            do_normalbae = gr.Checkbox(value=bool(s.get("do_normalbae", False)), label="Generate NormalBae")

        with gr.Row():
            recursive = gr.Checkbox(value=bool(s.get("recursive", False)), label="Recursive scan")
            skip_existing = gr.Checkbox(value=bool(s.get("skip_existing", True)), label="Skip existing outputs")

        save_status = gr.Textbox(value="", label="Status", interactive=False)

    # Template → textbox wiring
    def _apply_tpl(p_tpl, l_tpl, p_val, l_val):
        if p_tpl and p_tpl != "Custom":
            p_val = p_tpl
        if l_tpl and l_tpl != "Custom":
            l_val = l_tpl
        return gr.update(value=p_val), gr.update(value=l_val)

    portrait_tpl.change(fn=_apply_tpl, inputs=[portrait_tpl, landscape_tpl, portrait_size, landscape_size], outputs=[portrait_size, landscape_size])
    landscape_tpl.change(fn=_apply_tpl, inputs=[portrait_tpl, landscape_tpl, portrait_size, landscape_size], outputs=[portrait_size, landscape_size])

    def _update_eff_out(out_dir_v, mapset_name_v):
        return gr.update(value=_effective_out_dir(out_dir_v, mapset_name_v))

    out_dir.change(fn=_update_eff_out, inputs=[out_dir, mapset_name], outputs=[eff_out_dir])
    mapset_name.change(fn=_update_eff_out, inputs=[out_dir, mapset_name], outputs=[eff_out_dir])

    btn_open_eff.click(fn=_open_folder, inputs=[eff_out_dir], outputs=[register_status])
    btn_register_eff.click(fn=lambda p, t: _register_out_as_mapset(p, t, True), inputs=[eff_out_dir, mapset_name], outputs=[register_status])
    btn_audit_cn.click(fn=_audit_controlnet_stack, inputs=[comfy_url, comfy_root], outputs=[audit_summary, audit_json])

    # -------------------------
    # Advanced settings
    # -------------------------
    with gr.Accordion("Canny settings", open=False):
        with gr.Row():
            canny_low = gr.Slider(1, 500, value=int(s.get("canny_low", 150)), step=1, label="Low threshold")
            canny_high = gr.Slider(1, 800, value=int(s.get("canny_high", 300)), step=1, label="High threshold")
            blur = gr.Dropdown(choices=[0, 3, 5, 7, 9], value=int(s.get("blur", 3)), label="Pre-blur kernel (odd)")

        with gr.Row():
            clahe = gr.Checkbox(value=bool(s.get("clahe", False)), label="CLAHE")
            sharpen = gr.Checkbox(value=bool(s.get("sharpen", False)), label="Sharpen")
            denoise = gr.Checkbox(value=bool(s.get("denoise", False)), label="Denoise")

        gr.Markdown("### ✨ Canny cleanup")
        with gr.Row():
            canny_invert = gr.Checkbox(value=bool(s.get("canny_invert", False)), label="Invert")
            canny_thickness = gr.Dropdown(
                choices=["none", "thin", "thick", "extra_thick"],
                value=str(s.get("canny_thickness", "none")),
                label="Edge thickness",
            )
            canny_speckle = gr.Dropdown(
                choices=["none", "median3", "median5"],
                value=str(s.get("canny_speckle", "none")),
                label="Speckle filter",
            )

        with gr.Row():
            canny_adaptive = gr.Checkbox(value=bool(s.get("canny_adaptive", False)), label="Adaptive threshold")
            canny_clean_bg = gr.Checkbox(value=bool(s.get("canny_clean_bg", False)), label="Clean background (pure B/W)")
            canny_clean_thresh = gr.Slider(0, 255, value=int(s.get("canny_clean_thresh", 128)), step=1, label="Clean threshold")

    with gr.Accordion("OpenPose settings", open=False):
        with gr.Row():
            device = gr.Dropdown(choices=["cpu", "cuda"], value=str(s.get("device", "cpu")), label="Device")
            hands = gr.Checkbox(value=bool(s.get("hands", False)), label="Include hands")
            face = gr.Checkbox(value=bool(s.get("face", False)), label="Include face")

    with gr.Accordion("Depth settings", open=False):
        with gr.Row():
            depth_device = gr.Dropdown(choices=["cpu", "cuda"], value=str(s.get("depth_device", "cpu")), label="Depth device")
            depth_invert = gr.Checkbox(value=bool(s.get("depth_invert", False)), label="Invert depth (optional)")

    with gr.Accordion("Overlay before detection (optional)", open=False):
        gr.Markdown("Paste a file path (no Browse button here). Overlay is applied **before** detection.")
        with gr.Row():
            overlay_png = gr.Textbox(value=s.get("overlay_png", ""), label="Overlay PNG path (optional)", placeholder=r"F:\\assets\\stamp.png")
        with gr.Row():
            overlay_png_pos = gr.Dropdown(
                choices=["top-left", "top-right", "top-center", "center", "bottom-left", "bottom-right", "bottom-center"],
                value=str(s.get("overlay_png_pos", "bottom-right")),
                label="PNG position",
            )
            overlay_png_scale = gr.Slider(0.05, 1.5, value=float(s.get("overlay_png_scale", 0.25)), step=0.01, label="PNG scale")
            overlay_png_opacity = gr.Slider(0.0, 1.0, value=float(s.get("overlay_png_opacity", 1.0)), step=0.01, label="PNG opacity")

        with gr.Row():
            overlay_png_offx = gr.Slider(-1024, 1024, value=int(s.get("overlay_png_offx", 0)), step=1, label="PNG offset X")
            overlay_png_offy = gr.Slider(-1024, 1024, value=int(s.get("overlay_png_offy", 0)), step=1, label="PNG offset Y")

        gr.Markdown("### Text overlay")
        with gr.Row():
            overlay_text = gr.Textbox(value=s.get("overlay_text", ""), label="Text (optional)", placeholder="e.g. CENSOR")
            overlay_text_size = gr.Slider(6, 256, value=int(s.get("overlay_text_size", 28)), step=1, label="Text size")

        with gr.Row():
            overlay_text_color = gr.Textbox(value=str(s.get("overlay_text_color", "#FFFFFF")), label="Text color (hex)")
            overlay_text_outline = gr.Checkbox(value=bool(s.get("overlay_text_outline", False)), label="Outline")
            overlay_text_outline_color = gr.Textbox(value=str(s.get("overlay_text_outline_color", "#000000")), label="Outline color (hex)")

        with gr.Row():
            overlay_text_pos = gr.Dropdown(
                choices=["top-left", "top-right", "top-center", "center", "bottom-left", "bottom-right", "bottom-center"],
                value=str(s.get("overlay_text_pos", "bottom-right")),
                label="Text position",
            )
            overlay_text_offx = gr.Slider(-1024, 1024, value=int(s.get("overlay_text_offx", 0)), step=1, label="Text offset X")
            overlay_text_offy = gr.Slider(-1024, 1024, value=int(s.get("overlay_text_offy", 0)), step=1, label="Text offset Y")

    # -------------------------
    # Batch generation
    # -------------------------
    with gr.Accordion("Batch generation", open=False):
        gr.Markdown("Batch-generate maps for every image inside **in_dir** into **out_dir/(MapSet name)**.")
        gr.Markdown("Optional: upload batch images (will copy them into a temp in_dir).")
        with gr.Row():
            batch_upload = gr.File(label="Batch images (optional)", file_count="multiple")
            btn_use_batch_upload = gr.Button("📂 Use uploaded batch as in_dir")

        refresh_list = gr.Button("🔄 Refresh file list")
        file_list = gr.Dropdown(choices=[], value=None, label="Images in in_dir (preview only)")
        run_batch = gr.Button("🚀 Run batch", variant="primary")
        batch_log = gr.Textbox(value="", label="Batch log", lines=14, interactive=False)

    # -------------------------
    # Single image generation
    # -------------------------
    with gr.Accordion("Single image (solo) generation", open=True):
        gr.Markdown("Run **one image**. Outputs go to **out_dir/(MapSet name)**.")
        with gr.Row():
            single_mode = gr.Radio(choices=["Pick from in_dir", "Manual path"], value="Pick from in_dir", label="Single input source")
            single_refresh = gr.Button("🔄 Refresh list", scale=0)
            single_upload = gr.File(label="Pick single image", file_count="single")

        single_src_dd = gr.Dropdown(choices=[], value=None, label="Source from in_dir (relative path)")
        single_file = gr.Textbox(value="", label="Manual file path (if not using in_dir)", placeholder=r"F:\\pics\\img001.png")

        def _paths_from_gr_files(x):
            """Gradio File/Files can return str, dict, list[dict]/list[str]."""
            if not x:
                return []
            if isinstance(x, str):
                return [x]
            if isinstance(x, dict):
                p = x.get("name") or x.get("path")
                return [p] if p else []
            if isinstance(x, list):
                out = []
                for it in x:
                    if isinstance(it, str):
                        out.append(it)
                    elif isinstance(it, dict):
                        p = it.get("name") or it.get("path")
                        if p:
                            out.append(p)
                return [p for p in out if p]
            return []

        def _make_upload_dir(kind: str) -> Path:
            base = library_data_path('mapgen_uploads', kind, legacy_rel=f'mapgen_uploads/{kind}')
            base.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            d = base / f"{stamp}_{uuid.uuid4().hex[:8]}"
            d.mkdir(parents=True, exist_ok=True)
            return d

        def use_uploaded_batch_cb(files):
            paths = _paths_from_gr_files(files)
            if not paths:
                return gr.update(value=in_dir.value), "⚠️ No batch files selected."
            d = _make_upload_dir("batch")
            ok = 0
            for p in paths:
                try:
                    src = Path(p)
                    if src.exists():
                        shutil.copy2(src, d / src.name)
                        ok += 1
                except Exception:
                    pass
            if ok == 0:
                return gr.update(value=in_dir.value), "⚠️ Could not copy files."
            return gr.update(value=str(d)), f"✅ Using uploaded batch: {ok} file(s) → {d}"

        def use_uploaded_single_cb(f):
            paths = _paths_from_gr_files(f)
            if not paths:
                return gr.update(value=single_mode.value), gr.update(value=single_file.value), "⚠️ No file selected."
            p = paths[0]
            return gr.update(value="Manual path"), gr.update(value=p), f"✅ Selected single file: {p}"

        run_single = gr.Button("🚀 Run single", variant="primary")
        single_run_log = gr.Textbox(value="", label="Single run log", lines=6, interactive=False)

        with gr.Accordion("Single outputs → ControlNet", open=True):
            gr.Markdown(
                "Preview generated maps, then either **send directly** into ControlNet (txt2img/img2img) or **queue** them for the next **Generate**."
            )
            with gr.Row():
                prev_canny = gr.Image(value=None, label="Canny preview", type="pil", elem_id="ps_map_prev_canny")
                prev_pose = gr.Image(value=None, label="OpenPose preview", type="pil", elem_id="ps_map_prev_pose")
                prev_depth = gr.Image(value=None, label="Depth preview", type="pil", elem_id="ps_map_prev_depth")

            with gr.Row():
                info_canny = gr.Textbox(value="", label="Canny path", lines=2, interactive=False)
                info_pose = gr.Textbox(value="", label="OpenPose path", lines=2, interactive=False)
                info_depth = gr.Textbox(value="", label="Depth path", lines=2, interactive=False)

            with gr.Row():
                unit_canny = gr.Slider(0, 7, value=int(s.get("unit_canny", 0)), step=1, label="Canny → CN unit")
                unit_pose = gr.Slider(0, 7, value=int(s.get("unit_pose", 1)), step=1, label="Pose → CN unit")
                unit_depth = gr.Slider(0, 7, value=int(s.get("unit_depth", 2)), step=1, label="Depth → CN unit")

            with gr.Row():
                w_canny = gr.Slider(0, 2, value=float(s.get("weight_canny", 1.0)), step=0.05, label="Canny weight")
                w_pose = gr.Slider(0, 2, value=float(s.get("weight_pose", 1.0)), step=0.05, label="Pose weight")
                w_depth = gr.Slider(0, 2, value=float(s.get("weight_depth", 1.0)), step=0.05, label="Depth weight")

            with gr.Row():
                btn_refresh_out = gr.Button("🔄 Refresh outputs", scale=0)
                btn_clear_queue = gr.Button("🧹 Clear queued maps", scale=0)

            with gr.Row():
                auto_cfg = gr.Checkbox(value=True, label="Auto-config CN (best effort)")

            with gr.Row():
                btn_send_all_t2i = gr.Button("⚡ Send ALL (txt2img)", variant="primary")
                btn_send_all_i2i = gr.Button("⚡ Send ALL (img2img)", variant="primary")
                btn_queue_all = gr.Button("📌 Queue ALL (next Generate)")

            send_status = gr.Textbox(value="", label="Send status", lines=2, interactive=False)

    # -------------------------
    # Save settings (auto)
    # -------------------------
    def save_settings_cb(
        python_exe_v,
        backend_v,
        comfy_url_v,
        comfy_root_v,
        in_dir_v,
        out_dir_v,
        mapset_name_v,
        mode_v,
        detect_v,
        portrait_v,
        landscape_v,
        name_suffix_v,
        do_canny_v,
        do_openpose_v,
        do_depth_v,
        do_lineart_v,
        do_lineart_anime_v,
        do_softedge_v,
        do_scribble_v,
        do_normalbae_v,
        recursive_v,
        skip_existing_v,
        # canny
        canny_low_v,
        canny_high_v,
        blur_v,
        clahe_v,
        sharpen_v,
        denoise_v,
        canny_invert_v,
        canny_thickness_v,
        canny_adaptive_v,
        canny_clean_bg_v,
        canny_clean_thresh_v,
        canny_speckle_v,
        # openpose
        device_v,
        hands_v,
        face_v,
        # depth
        depth_device_v,
        depth_invert_v,
        # overlay
        overlay_png_v,
        overlay_png_pos_v,
        overlay_png_scale_v,
        overlay_png_opacity_v,
        overlay_png_offx_v,
        overlay_png_offy_v,
        overlay_text_v,
        overlay_text_size_v,
        overlay_text_color_v,
        overlay_text_outline_v,
        overlay_text_outline_color_v,
        overlay_text_pos_v,
        overlay_text_offx_v,
        overlay_text_offy_v,
        # cn mapping
        unit_canny_v,
        unit_pose_v,
        unit_depth_v,
        w_canny_v,
        w_pose_v,
        w_depth_v,
    ):
        d = _load_settings()
        d.update(
            {
                "python_exe": (python_exe_v or "").strip(),
                "script_path": DEFAULT_SCRIPT,
                "backend": str(backend_v or "auto"),
                "comfy_url": _as_base_url(comfy_url_v),
                "comfy_root": (comfy_root_v or "").strip(),
                "in_dir": (in_dir_v or "").strip(),
                "out_dir": (out_dir_v or "").strip(),
                "mapset_name": (mapset_name_v or "").strip(),
                "mode": mode_v,
                "detect": int(detect_v),
                "portrait_size": (portrait_v or "896x1344").strip(),
                "landscape_size": (landscape_v or "1344x896").strip(),
                "name_suffix": bool(name_suffix_v),
                "do_canny": bool(do_canny_v),
                "do_openpose": bool(do_openpose_v),
                "do_depth": bool(do_depth_v),
                "do_lineart": bool(do_lineart_v),
                "do_lineart_anime": bool(do_lineart_anime_v),
                "do_softedge": bool(do_softedge_v),
                "do_scribble": bool(do_scribble_v),
                "do_normalbae": bool(do_normalbae_v),
                "recursive": bool(recursive_v),
                "skip_existing": bool(skip_existing_v),
                "canny_low": int(canny_low_v),
                "canny_high": int(canny_high_v),
                "blur": int(blur_v),
                "clahe": bool(clahe_v),
                "sharpen": bool(sharpen_v),
                "denoise": bool(denoise_v),
                "canny_invert": bool(canny_invert_v),
                "canny_thickness": str(canny_thickness_v or "none"),
                "canny_adaptive": bool(canny_adaptive_v),
                "canny_clean_bg": bool(canny_clean_bg_v),
                "canny_clean_thresh": int(canny_clean_thresh_v),
                "canny_speckle": str(canny_speckle_v or "none"),
                "device": str(device_v or "cpu"),
                "hands": bool(hands_v),
                "face": bool(face_v),
                "depth_device": str(depth_device_v or "cpu"),
                "depth_invert": bool(depth_invert_v),
                "overlay_png": (overlay_png_v or "").strip(),
                "overlay_png_pos": str(overlay_png_pos_v or "bottom-right"),
                "overlay_png_scale": float(overlay_png_scale_v),
                "overlay_png_opacity": float(overlay_png_opacity_v),
                "overlay_png_offx": int(overlay_png_offx_v),
                "overlay_png_offy": int(overlay_png_offy_v),
                "overlay_text": (overlay_text_v or "").strip(),
                "overlay_text_size": int(overlay_text_size_v),
                "overlay_text_color": str(overlay_text_color_v or "#FFFFFF"),
                "overlay_text_outline": bool(overlay_text_outline_v),
                "overlay_text_outline_color": str(overlay_text_outline_color_v or "#000000"),
                "overlay_text_pos": str(overlay_text_pos_v or "bottom-right"),
                "overlay_text_offx": int(overlay_text_offx_v),
                "overlay_text_offy": int(overlay_text_offy_v),
                "unit_canny": int(unit_canny_v),
                "unit_pose": int(unit_pose_v),
                "unit_depth": int(unit_depth_v),
                "weight_canny": float(w_canny_v),
                "weight_pose": float(w_pose_v),
                "weight_depth": float(w_depth_v),
            }
        )
        _save_settings(d)
        return "✅ Saved settings."

    _SAVE_INPUTS = [
        python_exe,
        backend,
        comfy_url,
        comfy_root,
        in_dir,
        out_dir,
        mapset_name,
        mode,
        detect,
        portrait_size,
        landscape_size,
        name_suffix,
        do_canny,
        do_openpose,
        do_depth,
        do_lineart,
        do_lineart_anime,
        do_softedge,
        do_scribble,
        do_normalbae,
        recursive,
        skip_existing,
        canny_low,
        canny_high,
        blur,
        clahe,
        sharpen,
        denoise,
        canny_invert,
        canny_thickness,
        canny_adaptive,
        canny_clean_bg,
        canny_clean_thresh,
        canny_speckle,
        device,
        hands,
        face,
        depth_device,
        depth_invert,
        overlay_png,
        overlay_png_pos,
        overlay_png_scale,
        overlay_png_opacity,
        overlay_png_offx,
        overlay_png_offy,
        overlay_text,
        overlay_text_size,
        overlay_text_color,
        overlay_text_outline,
        overlay_text_outline_color,
        overlay_text_pos,
        overlay_text_offx,
        overlay_text_offy,
        unit_canny,
        unit_pose,
        unit_depth,
        w_canny,
        w_pose,
        w_depth,
    ]

    for comp in _SAVE_INPUTS:
        comp.change(fn=save_settings_cb, inputs=_SAVE_INPUTS, outputs=[save_status])

    # -------------------------
    # Events
    # -------------------------

    def refresh_files_cb(in_dir_v):
        return gr.update(choices=_list_images(in_dir_v), value=None)

    refresh_list.click(fn=refresh_files_cb, inputs=[in_dir], outputs=[file_list])
    single_refresh.click(fn=refresh_files_cb, inputs=[in_dir], outputs=[single_src_dd])
    btn_use_batch_upload.click(fn=use_uploaded_batch_cb, inputs=[batch_upload], outputs=[in_dir, save_status])
    single_upload.change(fn=use_uploaded_single_cb, inputs=[single_upload], outputs=[single_mode, single_file, single_run_log])

    def _py_default(py_v):
        return (py_v or "").strip() or sys.executable

    def _build_args(
        script_v,
        backend_v,
        comfy_url_v,
        comfy_root_v,
        in_dir_v,
        out_dir_v,
        mapset_name_v,
        mode_v,
        detect_v,
        portrait_v,
        landscape_v,
        do_canny_v,
        do_openpose_v,
        do_depth_v,
        do_lineart_v,
        do_lineart_anime_v,
        do_softedge_v,
        do_scribble_v,
        do_normalbae_v,
        name_suffix_v,
        recursive_v,
        skip_existing_v,
        # canny
        canny_low_v,
        canny_high_v,
        blur_v,
        clahe_v,
        sharpen_v,
        denoise_v,
        canny_invert_v,
        canny_thickness_v,
        canny_adaptive_v,
        canny_clean_bg_v,
        canny_clean_thresh_v,
        canny_speckle_v,
        # openpose
        device_v,
        hands_v,
        face_v,
        # depth
        depth_device_v,
        depth_invert_v,
        # overlay
        overlay_png_v,
        overlay_png_pos_v,
        overlay_png_scale_v,
        overlay_png_opacity_v,
        overlay_png_offx_v,
        overlay_png_offy_v,
        overlay_text_v,
        overlay_text_size_v,
        overlay_text_color_v,
        overlay_text_outline_v,
        overlay_text_outline_color_v,
        overlay_text_pos_v,
        overlay_text_offx_v,
        overlay_text_offy_v,
    ):
        out_eff = _effective_out_dir(out_dir_v, mapset_name_v)

        args = [
            script_v,
            "--backend",
            str(backend_v or "auto"),
            "--comfy_url",
            _as_base_url(comfy_url_v),
            "--comfy_root",
            (comfy_root_v or ""),
            "--in_dir",
            (in_dir_v or ""),
            "--out_dir",
            out_eff,
            "--mode",
            mode_v,
            "--detect",
            str(int(detect_v)),
            "--portrait_size",
            (portrait_v or "896x1344"),
            "--landscape_size",
            (landscape_v or "1344x896"),
            "--canny_low",
            str(int(canny_low_v)),
            "--canny_high",
            str(int(canny_high_v)),
            "--blur",
            str(int(blur_v)),
            "--canny_thickness",
            str(canny_thickness_v or "none"),
            "--canny_clean_thresh",
            str(int(canny_clean_thresh_v)),
            "--canny_speckle",
            str(canny_speckle_v or "none"),
            "--device",
            str(device_v or "cpu"),
            "--depth_device",
            str(depth_device_v or "cpu"),
        ]

        # Overlay args (only when set)
        if (overlay_png_v or "").strip():
            args += [
                "--overlay_png",
                (overlay_png_v or "").strip(),
                "--overlay_png_pos",
                str(overlay_png_pos_v or "bottom-right"),
                "--overlay_png_scale",
                str(float(overlay_png_scale_v)),
                "--overlay_png_opacity",
                str(float(overlay_png_opacity_v)),
                "--overlay_png_offx",
                str(int(overlay_png_offx_v)),
                "--overlay_png_offy",
                str(int(overlay_png_offy_v)),
            ]

        if (overlay_text_v or "").strip():
            args += [
                "--overlay_text",
                (overlay_text_v or "").strip(),
                "--overlay_text_size",
                str(int(overlay_text_size_v)),
                "--overlay_text_color",
                str(overlay_text_color_v or "#FFFFFF"),
                "--overlay_text_outline_color",
                str(overlay_text_outline_color_v or "#000000"),
                "--overlay_text_pos",
                str(overlay_text_pos_v or "bottom-right"),
                "--overlay_text_offx",
                str(int(overlay_text_offx_v)),
                "--overlay_text_offy",
                str(int(overlay_text_offy_v)),
            ]
            if bool(overlay_text_outline_v):
                args.append("--overlay_text_outline")

        # Which maps
        if do_canny_v:
            args.append("--canny")
        if do_openpose_v:
            args.append("--openpose")
        if do_depth_v:
            args.append("--depth")
        if do_lineart_v:
            args.append("--lineart")
        if do_lineart_anime_v:
            args.append("--lineart_anime")
        if do_softedge_v:
            args.append("--softedge")
        if do_scribble_v:
            args.append("--scribble")
        if do_normalbae_v:
            args.append("--normalbae")

        # Toggles
        if bool(name_suffix_v):
            args.append("--name_suffix")
        if bool(recursive_v):
            args.append("--recursive")
        if bool(skip_existing_v):
            args.append("--skip_existing")

        # Canny boosters
        if bool(clahe_v):
            args.append("--clahe")
        if bool(sharpen_v):
            args.append("--sharpen")
        if bool(denoise_v):
            args.append("--denoise")
        if bool(canny_invert_v):
            args.append("--canny_invert")
        if bool(canny_adaptive_v):
            args.append("--canny_adaptive")
        if bool(canny_clean_bg_v):
            args.append("--canny_clean_bg")

        # OpenPose extras
        if bool(hands_v):
            args.append("--hands")
        if bool(face_v):
            args.append("--face")

        # Depth extras
        if bool(depth_invert_v):
            args.append("--depth_invert")

        return args, out_eff

    def run_batch_cb(*vals):
        (
            py_v,
            script_v,
            backend_v,
            comfy_url_v,
            comfy_root_v,
            in_dir_v,
            out_dir_v,
            mapset_name_v,
            mode_v,
            detect_v,
            portrait_v,
            landscape_v,
            do_canny_v,
            do_openpose_v,
            do_depth_v,
            do_lineart_v,
            do_lineart_anime_v,
            do_softedge_v,
            do_scribble_v,
            do_normalbae_v,
            name_suffix_v,
            recursive_v,
            skip_existing_v,
            canny_low_v,
            canny_high_v,
            blur_v,
            clahe_v,
            sharpen_v,
            denoise_v,
            canny_invert_v,
            canny_thickness_v,
            canny_adaptive_v,
            canny_clean_bg_v,
            canny_clean_thresh_v,
            canny_speckle_v,
            device_v,
            hands_v,
            face_v,
            depth_device_v,
            depth_invert_v,
            overlay_png_v,
            overlay_png_pos_v,
            overlay_png_scale_v,
            overlay_png_opacity_v,
            overlay_png_offx_v,
            overlay_png_offy_v,
            overlay_text_v,
            overlay_text_size_v,
            overlay_text_color_v,
            overlay_text_outline_v,
            overlay_text_outline_color_v,
            overlay_text_pos_v,
            overlay_text_offx_v,
            overlay_text_offy_v,
        ) = vals

        py = _py_default(py_v)
        args, _out_eff = _build_args(
            script_v,
            backend_v,
            comfy_url_v,
            comfy_root_v,
            in_dir_v,
            out_dir_v,
            mapset_name_v,
            mode_v,
            detect_v,
            portrait_v,
            landscape_v,
            do_canny_v,
            do_openpose_v,
            do_depth_v,
            do_lineart_v,
            do_lineart_anime_v,
            do_softedge_v,
            do_scribble_v,
            do_normalbae_v,
            name_suffix_v,
            recursive_v,
            skip_existing_v,
            canny_low_v,
            canny_high_v,
            blur_v,
            clahe_v,
            sharpen_v,
            denoise_v,
            canny_invert_v,
            canny_thickness_v,
            canny_adaptive_v,
            canny_clean_bg_v,
            canny_clean_thresh_v,
            canny_speckle_v,
            device_v,
            hands_v,
            face_v,
            depth_device_v,
            depth_invert_v,
            overlay_png_v,
            overlay_png_pos_v,
            overlay_png_scale_v,
            overlay_png_opacity_v,
            overlay_png_offx_v,
            overlay_png_offy_v,
            overlay_text_v,
            overlay_text_size_v,
            overlay_text_color_v,
            overlay_text_outline_v,
            overlay_text_outline_color_v,
            overlay_text_pos_v,
            overlay_text_offx_v,
            overlay_text_offy_v,
        )

        code, out = _run_cmd(py, args)
        return ("✅ Batch done" if code == 0 else "❌ Batch failed") + ("\n" + out if out else "")

    run_batch.click(
        fn=run_batch_cb,
        inputs=[
            python_exe,
            script_path,
            backend,
            comfy_url,
            comfy_root,
            in_dir,
            out_dir,
            mapset_name,
            mode,
            detect,
            portrait_size,
            landscape_size,
            do_canny,
            do_openpose,
            do_depth,
            do_lineart,
            do_lineart_anime,
            do_softedge,
            do_scribble,
            do_normalbae,
            name_suffix,
            recursive,
            skip_existing,
            canny_low,
            canny_high,
            blur,
            clahe,
            sharpen,
            denoise,
            canny_invert,
            canny_thickness,
            canny_adaptive,
            canny_clean_bg,
            canny_clean_thresh,
            canny_speckle,
            device,
            hands,
            face,
            depth_device,
            depth_invert,
            overlay_png,
            overlay_png_pos,
            overlay_png_scale,
            overlay_png_opacity,
            overlay_png_offx,
            overlay_png_offy,
            overlay_text,
            overlay_text_size,
            overlay_text_color,
            overlay_text_outline,
            overlay_text_outline_color,
            overlay_text_pos,
            overlay_text_offx,
            overlay_text_offy,
        ],
        outputs=[batch_log],
    )

    def _resolve_single_input(single_mode_v, single_rel_v, single_file_v, in_dir_v):
        if single_mode_v == "Pick from in_dir":
            if not single_rel_v:
                return "", ""
            abs_path = str((Path(in_dir_v) / single_rel_v).resolve())
            input_rel = single_rel_v
            return abs_path, input_rel
        fp = (single_file_v or "").strip()
        if not fp:
            return "", ""
        p = Path(fp)
        return str(p.resolve()), p.name

    def run_single_cb(
        py_v,
        script_v,
        backend_v,
        comfy_url_v,
        comfy_root_v,
        single_mode_v,
        single_rel_v,
        single_file_v,
        in_dir_v,
        out_dir_v,
        mapset_name_v,
        mode_v,
        detect_v,
        portrait_v,
        landscape_v,
        do_canny_v,
        do_openpose_v,
        do_depth_v,
        do_lineart_v,
        do_lineart_anime_v,
        do_softedge_v,
        do_scribble_v,
        do_normalbae_v,
        name_suffix_v,
        recursive_v,
        skip_existing_v,
        canny_low_v,
        canny_high_v,
        blur_v,
        clahe_v,
        sharpen_v,
        denoise_v,
        canny_invert_v,
        canny_thickness_v,
        canny_adaptive_v,
        canny_clean_bg_v,
        canny_clean_thresh_v,
        canny_speckle_v,
        device_v,
        hands_v,
        face_v,
        depth_device_v,
        depth_invert_v,
        overlay_png_v,
        overlay_png_pos_v,
        overlay_png_scale_v,
        overlay_png_opacity_v,
        overlay_png_offx_v,
        overlay_png_offy_v,
        overlay_text_v,
        overlay_text_size_v,
        overlay_text_color_v,
        overlay_text_outline_v,
        overlay_text_outline_color_v,
        overlay_text_pos_v,
        overlay_text_offx_v,
        overlay_text_offy_v,
    ):
        py = _py_default(py_v)
        abs_in, input_rel = _resolve_single_input(single_mode_v, single_rel_v, single_file_v, in_dir_v)
        if not abs_in:
            return "⚠️ No input selected."

        args, _out_eff = _build_args(
            script_v,
            backend_v,
            comfy_url_v,
            comfy_root_v,
            in_dir_v,
            out_dir_v,
            mapset_name_v,
            mode_v,
            detect_v,
            portrait_v,
            landscape_v,
            do_canny_v,
            do_openpose_v,
            do_depth_v,
            do_lineart_v,
            do_lineart_anime_v,
            do_softedge_v,
            do_scribble_v,
            do_normalbae_v,
            name_suffix_v,
            recursive_v,
            skip_existing_v,
            canny_low_v,
            canny_high_v,
            blur_v,
            clahe_v,
            sharpen_v,
            denoise_v,
            canny_invert_v,
            canny_thickness_v,
            canny_adaptive_v,
            canny_clean_bg_v,
            canny_clean_thresh_v,
            canny_speckle_v,
            device_v,
            hands_v,
            face_v,
            depth_device_v,
            depth_invert_v,
            overlay_png_v,
            overlay_png_pos_v,
            overlay_png_scale_v,
            overlay_png_opacity_v,
            overlay_png_offx_v,
            overlay_png_offy_v,
            overlay_text_v,
            overlay_text_size_v,
            overlay_text_color_v,
            overlay_text_outline_v,
            overlay_text_outline_color_v,
            overlay_text_pos_v,
            overlay_text_offx_v,
            overlay_text_offy_v,
        )

        # Remove in_dir args for single, replace with --input + --input_rel
        # Find '--in_dir' and value index
        try:
            idx = args.index("--in_dir")
            # Remove flag + value
            args.pop(idx)
            args.pop(idx)
        except Exception:
            pass

        args += ["--input", abs_in, "--input_rel", input_rel]

        code, out = _run_cmd(py, args)
        status = "✅ Single done" if code == 0 else "❌ Single failed"
        return status + ("\n" + out if out else "")

    run_single.click(
        fn=run_single_cb,
        inputs=[
            python_exe,
            script_path,
            backend,
            comfy_url,
            comfy_root,
            single_mode,
            single_src_dd,
            single_file,
            in_dir,
            out_dir,
            mapset_name,
            mode,
            detect,
            portrait_size,
            landscape_size,
            do_canny,
            do_openpose,
            do_depth,
            do_lineart,
            do_lineart_anime,
            do_softedge,
            do_scribble,
            do_normalbae,
            name_suffix,
            recursive,
            skip_existing,
            canny_low,
            canny_high,
            blur,
            clahe,
            sharpen,
            denoise,
            canny_invert,
            canny_thickness,
            canny_adaptive,
            canny_clean_bg,
            canny_clean_thresh,
            canny_speckle,
            device,
            hands,
            face,
            depth_device,
            depth_invert,
            overlay_png,
            overlay_png_pos,
            overlay_png_scale,
            overlay_png_opacity,
            overlay_png_offx,
            overlay_png_offy,
            overlay_text,
            overlay_text_size,
            overlay_text_color,
            overlay_text_outline,
            overlay_text_outline_color,
            overlay_text_pos,
            overlay_text_offx,
            overlay_text_offy,
        ],
        outputs=[single_run_log],
    )

    def refresh_single_out_cb(out_dir_v, mapset_name_v, name_suffix_v, single_mode_v, single_rel_v, single_file_v, in_dir_v):
        _, input_rel = _resolve_single_input(single_mode_v, single_rel_v, single_file_v, in_dir_v)
        if not input_rel:
            return (None, None, None, "", "", "")
        out_eff = _effective_out_dir(out_dir_v, mapset_name_v)
        paths = _find_single_outputs(out_eff, input_rel, bool(name_suffix_v))
        return (
            paths["canny"] or None,
            paths["openpose"] or None,
            paths["depth"] or None,
            paths["canny"],
            paths["openpose"],
            paths["depth"],
        )

    btn_refresh_out.click(
        fn=refresh_single_out_cb,
        inputs=[out_dir, mapset_name, name_suffix, single_mode, single_src_dd, single_file, in_dir],
        outputs=[prev_canny, prev_pose, prev_depth, info_canny, info_pose, info_depth],
    )

    def clear_queue_ui():
        try:
            return clear_queue_cb()
        except Exception:
            return "🧹 Cleared queued maps."

    btn_clear_queue.click(fn=clear_queue_ui, inputs=[], outputs=[send_status])

    def send_all_cb(info_canny_v, info_pose_v, info_depth_v, unit_canny_v, unit_pose_v, unit_depth_v, w_canny_v, w_pose_v, w_depth_v):
        msgs = []
        for kind, unit_idx, path, weight in [
            ("canny", unit_canny_v, (info_canny_v or "").strip(), w_canny_v),
            ("openpose", unit_pose_v, (info_pose_v or "").strip(), w_pose_v),
            ("depth", unit_depth_v, (info_depth_v or "").strip(), w_depth_v),
        ]:
            if not path:
                continue
            try:
                msgs.append(queue_cb(kind, int(unit_idx), path, float(weight)))
            except Exception as e:
                msgs.append(f"❌ Failed queue {kind}: {e}")

        return "\n".join(msgs) if msgs else "⚠️ Nothing to send (refresh outputs first)."

    # Queue (python-side, applied on next Generate)
    btn_queue_all.click(
        fn=send_all_cb,
        inputs=[info_canny, info_pose, info_depth, unit_canny, unit_pose, unit_depth, w_canny, w_pose, w_depth],
        outputs=[send_status],
    )

    # Direct send (browser-side) into ControlNet file inputs
    _JS_SEND_ALL_T2I = r"""
(uc, up, ud, auto) => {
  const root = (() => { try { return (typeof gradioApp === 'function') ? gradioApp() : document; } catch(e) { return document; } })();
  const hasImg = (id) => {
    const host = root.querySelector('#' + id);
    if (!host) return false;
    const img = host.querySelector('img');
    return !!(img && img.src);
  };

  if (typeof cnbridgeSendFromPreview !== 'function') {
    alert('Prompt Suite: missing cnbridgeSendFromPreview(). Make sure javascript/cnbridge_send.js exists in the extension.');
    return [uc, up, ud, auto];
  }

  const run = async () => {
    const tab = 'txt2img';
    if (hasImg('ps_map_prev_canny')) await cnbridgeSendFromPreview(tab, uc, 'canny', auto, 'ps_map_prev_canny');
    if (hasImg('ps_map_prev_pose')) await cnbridgeSendFromPreview(tab, up, 'openpose', auto, 'ps_map_prev_pose');
    if (hasImg('ps_map_prev_depth')) await cnbridgeSendFromPreview(tab, ud, 'depth', auto, 'ps_map_prev_depth');
  };
  run();
  return [uc, up, ud, auto];
}
"""

    _JS_SEND_ALL_I2I = r"""
(uc, up, ud, auto) => {
  const root = (() => { try { return (typeof gradioApp === 'function') ? gradioApp() : document; } catch(e) { return document; } })();
  const hasImg = (id) => {
    const host = root.querySelector('#' + id);
    if (!host) return false;
    const img = host.querySelector('img');
    return !!(img && img.src);
  };

  if (typeof cnbridgeSendFromPreview !== 'function') {
    alert('Prompt Suite: missing cnbridgeSendFromPreview(). Make sure javascript/cnbridge_send.js exists in the extension.');
    return [uc, up, ud, auto];
  }

  const run = async () => {
    const tab = 'img2img';
    if (hasImg('ps_map_prev_canny')) await cnbridgeSendFromPreview(tab, uc, 'canny', auto, 'ps_map_prev_canny');
    if (hasImg('ps_map_prev_pose')) await cnbridgeSendFromPreview(tab, up, 'openpose', auto, 'ps_map_prev_pose');
    if (hasImg('ps_map_prev_depth')) await cnbridgeSendFromPreview(tab, ud, 'depth', auto, 'ps_map_prev_depth');
  };
  run();
  return [uc, up, ud, auto];
}
"""

    btn_send_all_t2i.click(fn=lambda *x: x, inputs=[unit_canny, unit_pose, unit_depth, auto_cfg], outputs=[unit_canny, unit_pose, unit_depth, auto_cfg], js=_JS_SEND_ALL_T2I)
    btn_send_all_i2i.click(fn=lambda *x: x, inputs=[unit_canny, unit_pose, unit_depth, auto_cfg], outputs=[unit_canny, unit_pose, unit_depth, auto_cfg], js=_JS_SEND_ALL_I2I)

