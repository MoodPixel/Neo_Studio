import os
import sys
import subprocess
from pathlib import Path

import gradio as gr

from llm_session_bridge import caption_load, caption_unload, caption_status, caption_run


IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
BACKENDS = ["JoyCaption GGUF (llama.cpp)", "ToriiGate GGUF (llama.cpp)"]


def _pick_folder(initial_dir: str = "") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        if initial_dir and os.path.isdir(initial_dir):
            return filedialog.askdirectory(initialdir=initial_dir) or ""
        return filedialog.askdirectory() or ""
    except Exception:
        return ""


def _run_subprocess(py_exe: str, args: list[str]) -> tuple[str, str]:
    if not py_exe:
        py_exe = sys.executable
    cmd = [py_exe] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0 and not err:
            err = f"Process exited with code {proc.returncode}"
        return out, err
    except Exception as e:
        return "", f"Failed to run: {e}"


def _tool_path(filename: str) -> str:
    ext_root = Path(__file__).resolve().parents[1]
    return str(ext_root / "tools" / filename)


def _default_models_hint() -> str:
    return (
        "Tip: your GGUF caption models can live anywhere.\n"
        "Example: C:\\ComfyUI\\models\\LLM\\GGUF\\"
    )


def _visible_backend_updates(backend: str):
    backend = (backend or "").strip()
    joy_visible = backend == "JoyCaption GGUF (llama.cpp)"
    torii_visible = backend == "ToriiGate GGUF (llama.cpp)"
    button_label = "🟢 Load JoyCaption GGUF" if joy_visible else "🟢 Load ToriiGate GGUF"
    return (
        gr.update(visible=True),
        gr.update(visible=joy_visible),
        gr.update(visible=torii_visible),
        gr.update(value=button_label),
    )


def _build_joy_prompts(style: str, length: str, custom_prompt: str, prefix: str, suffix: str):
    system_prompt = "You are an assistant that captions images accurately and helpfully."
    length_hint = ""
    if length == "short":
        length_hint = "Keep it short (one sentence)."
    elif length == "long":
        length_hint = "Be detailed."

    if style == "Descriptive":
        user = f"Describe the image. {length_hint}".strip()
    elif style == "Stable Diffusion Prompt":
        user = (
            "Write a Stable Diffusion prompt describing the image. "
            "Output a comma-separated list of concise tags. "
            "Don't guess brands or names. "
            f"{length_hint}"
        ).strip()
    else:
        user = (custom_prompt or "Describe the image.").strip()
        if length_hint and "{length}" not in user.lower():
            user = f"{user}\n\n{length_hint}".strip()

    if prefix:
        user = f"{prefix}{user}"
    if suffix:
        user = f"{user}{suffix}"
    return system_prompt, user


def _build_torii_prompts(style: str, length: str, custom_prompt: str, prefix: str, suffix: str):
    system_prompt = "You are an assistant that captions images accurately and helpfully. Handle both anime and realistic styles."
    length_hint = ""
    if length == "short":
        length_hint = "Keep it short (one sentence)."
    elif length == "long":
        length_hint = "Be detailed."

    if style == "Descriptive":
        user = f"Describe the image. {length_hint}".strip()
    elif style == "Stable Diffusion Prompt":
        user = (
            "Write a Stable Diffusion prompt describing the image. "
            "Output a comma-separated list of concise tags. "
            "Don't guess brands or names. "
            "Include appearance, clothing, pose, lighting, style, and mood. "
            f"{length_hint}"
        ).strip()
    else:
        user = (custom_prompt or "Describe the image.").strip()
        if length_hint and "{length}" not in user.lower():
            user = f"{user}\n\n{length_hint}".strip()

    if prefix:
        user = f"{prefix}{user}"
    if suffix:
        user = f"{user}{suffix}"
    return system_prompt, user


def _format_session_msg(resp: dict, loaded_label: str, idle_label: str) -> str:
    if not isinstance(resp, dict):
        return idle_label
    if resp.get("ok") and resp.get("loaded"):
        key = resp.get("key") or {}
        model_name = os.path.basename(str(key.get("model_path") or "")) or "model"
        return f"✅ {loaded_label}: `{model_name}`"
    if resp.get("ok"):
        return idle_label
    return f"⚠️ {(resp.get('error') or 'Session unavailable.')}"


def _vision_key_for_backend(
    backend,
    model_path,
    mmproj_path,
    n_ctx,
    n_gpu_layers,
    n_threads,
    torii_model_path,
    torii_mmproj_path,
    torii_n_ctx,
    torii_n_gpu_layers,
    torii_n_threads,
):
    backend = (backend or "").strip()
    if backend == "JoyCaption GGUF (llama.cpp)":
        return {
            "kind": "joy",
            "model_path": (model_path or "").strip().strip('"'),
            "mmproj_path": (mmproj_path or "").strip().strip('"'),
            "n_ctx": int(n_ctx),
            "n_gpu_layers": int(n_gpu_layers),
            "n_threads": int(n_threads),
        }
    return {
        "kind": "torii",
        "model_path": (torii_model_path or "").strip().strip('"'),
        "mmproj_path": (torii_mmproj_path or "").strip().strip('"'),
        "n_ctx": int(torii_n_ctx),
        "n_gpu_layers": int(torii_n_gpu_layers),
        "n_threads": int(torii_n_threads),
    }


def _session_caption_request(
    backend,
    style,
    length,
    custom_prompt,
    max_new_tokens,
    temperature,
    top_p,
    top_k,
    prefix,
    suffix,
    torii_style,
    torii_length,
    torii_custom_prompt,
    torii_max_new_tokens,
    torii_temperature,
    torii_top_p,
    torii_top_k,
    torii_prefix,
    torii_suffix,
    torii_output_style,
):
    backend = (backend or "").strip()
    if backend == "JoyCaption GGUF (llama.cpp)":
        system_prompt, user_prompt = _build_joy_prompts(style, length, custom_prompt, prefix or "", suffix or "")
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_new_tokens": int(max_new_tokens),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "top_k": int(top_k),
        }

    t_suffix = torii_suffix or ""
    if torii_output_style == "Realistic":
        t_suffix += ", realistic photography, photorealistic, high detail, no cartoon"
    elif torii_output_style == "Anime":
        t_suffix += ", anime style, detailed illustration, vibrant colors, manga art, no photo"
    system_prompt, user_prompt = _build_torii_prompts(torii_style, torii_length, torii_custom_prompt, torii_prefix or "", t_suffix)
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "max_new_tokens": int(torii_max_new_tokens),
        "temperature": float(torii_temperature),
        "top_p": float(torii_top_p),
        "top_k": int(torii_top_k),
    }


def build_caption_supporter_ui():
    with gr.Column():
        gr.Markdown("## 🏷️ Caption Supporter (Forge tab) — **no ComfyUI**")
        gr.Markdown("This tab runs captioning models *from inside Forge UI*. Available backends: **JoyCaption GGUF** and **ToriiGate GGUF**.")

        with gr.Accordion("Environment", open=True):
            py_exe = gr.Textbox(
                label="Python executable (recommended: caption_env python.exe)",
                placeholder=r"D:\AI\caption_env\Scripts\python.exe",
                value="",
            )
            gr.Markdown(_default_models_hint())

        with gr.Accordion("Mode", open=True):
            backend = gr.Dropdown(label="Caption backend", choices=BACKENDS, value=BACKENDS[0])
            backend_hint = gr.Markdown("✅ Active backend: **JoyCaption GGUF**. Only that model path will be used when you load the session.")

        with gr.Accordion("🟢 Loaded GGUF session", open=True, visible=True) as gguf_session_acc:
            gr.Markdown("Load a Joy/Torii GGUF once, do your captioning, then unload it so Forge gets the VRAM back.")
            with gr.Row():
                load_session_btn = gr.Button("🟢 Load JoyCaption GGUF")
                unload_session_btn = gr.Button("🔴 Unload GGUF model", variant="secondary")
            session_msg = gr.Markdown("ℹ️ One-shot mode is active until you load a Joy/Torii GGUF session.")

        with gr.Accordion("JoyCaption GGUF settings", open=True, visible=True) as joy_settings_acc:
            model_path = gr.Textbox(label="Model GGUF path", placeholder=r"C:\...\llama-joycaption-....Q6_K.gguf")
            mmproj_path = gr.Textbox(label="mmproj GGUF path", placeholder=r"C:\...\llava-mmproj-model-f16.gguf")
            with gr.Row():
                n_ctx = gr.Slider(1024, 8192, value=4096, step=256, label="Context (n_ctx)")
                n_gpu_layers = gr.Slider(-1, 120, value=-1, step=1, label="GPU layers (-1 = auto/all)")
                n_threads = gr.Slider(1, 32, value=8, step=1, label="CPU threads")
            with gr.Row():
                style = gr.Dropdown(label="Prompt style", choices=["Descriptive", "Stable Diffusion Prompt", "Custom"], value="Stable Diffusion Prompt")
                length = gr.Dropdown(label="Caption length", choices=["short", "any", "long"], value="long")
            custom_prompt = gr.Textbox(label="Custom prompt (only used if style=Custom)", lines=3)
            with gr.Row():
                max_new_tokens = gr.Slider(16, 512, value=256, step=16, label="Max new tokens")
                temperature = gr.Slider(0.0, 2.0, value=0.6, step=0.05, label="Temperature")
                top_p = gr.Slider(0.0, 1.0, value=0.9, step=0.01, label="Top-p")
                top_k = gr.Slider(0, 200, value=0, step=1, label="Top-k (0=disabled)")
            with gr.Row():
                prefix = gr.Textbox(label="Prefix (optional)", placeholder="e.g., photo of ")
                suffix = gr.Textbox(label="Suffix (optional)", placeholder="e.g., , best quality")

        with gr.Accordion("ToriiGate GGUF settings", open=False, visible=False) as torii_settings_acc:
            torii_model_path = gr.Textbox(label="Model GGUF path", placeholder=r"C:\...\ToriiGate-v0.4-7B.Q8_0.gguf")
            torii_mmproj_path = gr.Textbox(label="mmproj GGUF path", placeholder=r"C:\...\ToriiGate-v0.4-7B.mmproj-fp16.gguf")
            with gr.Row():
                torii_n_ctx = gr.Slider(1024, 8192, value=4096, step=256, label="Context (n_ctx)")
                torii_n_gpu_layers = gr.Slider(-1, 120, value=-1, step=1, label="GPU layers (-1 = auto/all)")
                torii_n_threads = gr.Slider(1, 32, value=8, step=1, label="CPU threads")
            with gr.Row():
                torii_style = gr.Dropdown(label="Prompt style", choices=["Descriptive", "Stable Diffusion Prompt", "Custom"], value="Stable Diffusion Prompt")
                torii_length = gr.Dropdown(label="Caption length", choices=["short", "any", "long"], value="long")
            torii_custom_prompt = gr.Textbox(label="Custom prompt (only used if style=Custom)", lines=3)
            with gr.Row():
                torii_max_new_tokens = gr.Slider(16, 512, value=256, step=16, label="Max new tokens")
                torii_temperature = gr.Slider(0.0, 2.0, value=0.6, step=0.05, label="Temperature")
                torii_top_p = gr.Slider(0.0, 1.0, value=0.9, step=0.01, label="Top-p")
                torii_top_k = gr.Slider(0, 200, value=0, step=1, label="Top-k (0=disabled)")
            with gr.Row():
                torii_prefix = gr.Textbox(label="Prefix (optional)", placeholder="e.g., photo of ")
                torii_suffix = gr.Textbox(label="Suffix (optional)", placeholder="e.g., , best quality")
            torii_output_style = gr.Dropdown(label="Output style", choices=["Auto (match input)", "Realistic", "Anime"], value="Auto (match input)")

        with gr.Accordion("Batch processing", open=True):
            with gr.Row():
                in_dir = gr.Textbox(label="Input folder", placeholder=r"F:\images")
                pick_in = gr.Button("📁 Pick input")
            with gr.Row():
                out_dir = gr.Textbox(label="Output folder (leave empty = sidecar .txt next to image)", value="")
                pick_out = gr.Button("📁 Pick output")
            with gr.Row():
                recursive = gr.Checkbox(label="Recursive (include subfolders)", value=False)
                skip_existing = gr.Checkbox(label="Skip if .txt exists", value=True)
                start_from = gr.Number(label="Start from index", value=0, precision=0)
            sort_method = gr.Dropdown(label="Sort method", choices=["sequential", "alphabetical"], value="sequential")
            run_batch = gr.Button("🚀 Run batch captioning")

        with gr.Accordion("Single image", open=False):
            single_img = gr.File(label="Drop image (jpg/png/webp)", file_types=[".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"], type="filepath", file_count="single")
            run_single = gr.Button("✨ Caption this image")
            single_caption = gr.Textbox(label="Caption result", lines=6)

        log = gr.Textbox(label="Log", lines=14)

        pick_in.click(lambda cur: _pick_folder(cur), inputs=[in_dir], outputs=[in_dir])
        pick_out.click(lambda cur: _pick_folder(cur), inputs=[out_dir], outputs=[out_dir])

        def _caption_session_msg(resp: dict) -> str:
            return _format_session_msg(resp, "Loaded GGUF session ready", "ℹ️ One-shot mode is active until you load a Joy/Torii GGUF session.")

        def _load_session_cb(py_exe, backend, model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads, torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads):
            key = _vision_key_for_backend(backend, model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads, torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads)
            resp = caption_load(py_exe, key["kind"], key["model_path"], key["mmproj_path"], key["n_ctx"], key["n_gpu_layers"], key["n_threads"])
            return _caption_session_msg(resp)

        def _unload_session_cb(py_exe):
            return _caption_session_msg(caption_unload(py_exe))

        def _backend_note_cb(backend_name):
            backend_name = (backend_name or "").strip()
            if backend_name == "JoyCaption GGUF (llama.cpp)":
                note = "✅ Active backend: **JoyCaption GGUF**. Clicking load will use only the Joy model + mmproj paths."
            else:
                note = "✅ Active backend: **ToriiGate GGUF**. Clicking load will use only the Torii model + mmproj paths."
            return (note, *_visible_backend_updates(backend_name))

        def _run_batch(
            py_exe,
            backend,
            model_path,
            mmproj_path,
            n_ctx,
            n_gpu_layers,
            n_threads,
            style,
            length,
            custom_prompt,
            max_new_tokens,
            temperature,
            top_p,
            top_k,
            torii_model_path,
            torii_mmproj_path,
            torii_n_ctx,
            torii_n_gpu_layers,
            torii_n_threads,
            torii_style,
            torii_length,
            torii_custom_prompt,
            torii_max_new_tokens,
            torii_temperature,
            torii_top_p,
            torii_top_k,
            torii_prefix,
            torii_suffix,
            torii_output_style,
            prefix,
            suffix,
            in_dir,
            out_dir,
            recursive,
            skip_existing,
            start_from,
            sort_method,
        ):
            images = []
            try:
                images = [str(p) for p in _list_images_local(in_dir, recursive, sort_method)]
            except Exception as e:
                return f"❌ Could not scan folder: {e}"
            if not images:
                return "⚠️ No images found."
            try:
                start_index = max(0, int(start_from or 0))
            except Exception:
                start_index = 0
            images = images[start_index:]
            if not images:
                return "⚠️ Start index is beyond the available image count."

            if backend == "JoyCaption GGUF (llama.cpp)":
                tool = _tool_path("joy_gguf_caption_cli.py")
                args = [
                    tool,
                    "--in_dir", in_dir,
                    "--model", model_path,
                    "--mmproj", mmproj_path,
                    "--n_ctx", str(int(n_ctx)),
                    "--n_gpu_layers", str(int(n_gpu_layers)),
                    "--n_threads", str(int(n_threads)),
                    "--style", style,
                    "--length", length,
                    "--max_new_tokens", str(int(max_new_tokens)),
                    "--temperature", str(float(temperature)),
                    "--top_p", str(float(top_p)),
                    "--top_k", str(int(top_k)),
                    "--prefix", prefix or "",
                    "--suffix", suffix or "",
                ]
                if style == "Custom" and (custom_prompt or "").strip():
                    args += ["--custom_prompt", custom_prompt.strip()]
            else:
                tool = _tool_path("toriigate_gguf_caption_cli.py")
                final_suffix = torii_suffix or ""
                if torii_output_style == "Realistic":
                    final_suffix += ", realistic photography, photorealistic, high detail, no cartoon"
                elif torii_output_style == "Anime":
                    final_suffix += ", anime style, detailed illustration, vibrant colors, manga art, no photo"
                args = [
                    tool,
                    "--in_dir", in_dir,
                    "--model", torii_model_path,
                    "--mmproj", torii_mmproj_path,
                    "--n_ctx", str(int(torii_n_ctx)),
                    "--n_gpu_layers", str(int(torii_n_gpu_layers)),
                    "--n_threads", str(int(torii_n_threads)),
                    "--style", torii_style,
                    "--length", torii_length,
                    "--max_new_tokens", str(int(torii_max_new_tokens)),
                    "--temperature", str(float(torii_temperature)),
                    "--top_p", str(float(torii_top_p)),
                    "--top_k", str(int(torii_top_k)),
                    "--prefix", torii_prefix or "",
                    "--suffix", final_suffix,
                ]
                if torii_style == "Custom" and (torii_custom_prompt or "").strip():
                    args += ["--custom_prompt", torii_custom_prompt.strip()]

            if out_dir:
                args += ["--out_dir", out_dir]
            if recursive:
                args += ["--recursive"]
            if skip_existing:
                args += ["--skip_existing"]

            out, err = _run_subprocess(py_exe, args)
            return (out + ("\n\n" + err if err else "")).strip()

        def _run_single(
            py_exe,
            backend,
            model_path,
            mmproj_path,
            n_ctx,
            n_gpu_layers,
            n_threads,
            style,
            length,
            custom_prompt,
            max_new_tokens,
            temperature,
            top_p,
            top_k,
            torii_model_path,
            torii_mmproj_path,
            torii_n_ctx,
            torii_n_gpu_layers,
            torii_n_threads,
            torii_style,
            torii_length,
            torii_custom_prompt,
            torii_max_new_tokens,
            torii_temperature,
            torii_top_p,
            torii_top_k,
            torii_prefix,
            torii_suffix,
            torii_output_style,
            prefix,
            suffix,
            file_obj,
        ):
            if file_obj is None:
                return "", "No file uploaded."
            img_path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", "") or getattr(file_obj, "path", "")
            if not img_path or not os.path.exists(img_path):
                return "", f"Invalid or missing image path: {file_obj}"

            desired_key = _vision_key_for_backend(backend, model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads, torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads)
            st = caption_status(py_exe)
            if st.get("ok") and st.get("loaded") and (st.get("key") or {}) == desired_key:
                req = _session_caption_request(
                    backend,
                    style,
                    length,
                    custom_prompt,
                    max_new_tokens,
                    temperature,
                    top_p,
                    top_k,
                    prefix,
                    suffix,
                    torii_style,
                    torii_length,
                    torii_custom_prompt,
                    torii_max_new_tokens,
                    torii_temperature,
                    torii_top_p,
                    torii_top_k,
                    torii_prefix,
                    torii_suffix,
                    torii_output_style,
                )
                resp = caption_run(py_exe, img_path, req["system_prompt"], req["user_prompt"], req["max_new_tokens"], req["temperature"], req["top_p"], req["top_k"])
                if resp.get("ok"):
                    return (resp.get("caption") or "").strip(), "🟢 Used loaded GGUF session."
                return "", f"❌ Loaded session error: {resp.get('error') or 'caption failed'}"

            if backend == "JoyCaption GGUF (llama.cpp)":
                tool = _tool_path("joy_gguf_caption_cli.py")
                args = [
                    tool,
                    "--single", img_path,
                    "--model", model_path,
                    "--mmproj", mmproj_path,
                    "--n_ctx", str(int(n_ctx)),
                    "--n_gpu_layers", str(int(n_gpu_layers)),
                    "--n_threads", str(int(n_threads)),
                    "--style", style,
                    "--length", length,
                    "--max_new_tokens", str(int(max_new_tokens)),
                    "--temperature", str(float(temperature)),
                    "--top_p", str(float(top_p)),
                    "--top_k", str(int(top_k)),
                    "--prefix", prefix or "",
                    "--suffix", suffix or "",
                ]
                if style == "Custom" and (custom_prompt or "").strip():
                    args += ["--custom_prompt", custom_prompt.strip()]
            else:
                tool = _tool_path("toriigate_gguf_caption_cli.py")
                final_suffix = torii_suffix or ""
                if torii_output_style == "Realistic":
                    final_suffix += ", realistic photography, photorealistic, high detail, no cartoon"
                elif torii_output_style == "Anime":
                    final_suffix += ", anime style, detailed illustration, vibrant colors, manga art, no photo"
                args = [
                    tool,
                    "--single", img_path,
                    "--model", torii_model_path,
                    "--mmproj", torii_mmproj_path,
                    "--n_ctx", str(int(torii_n_ctx)),
                    "--n_gpu_layers", str(int(torii_n_gpu_layers)),
                    "--n_threads", str(int(torii_n_threads)),
                    "--style", torii_style,
                    "--length", torii_length,
                    "--max_new_tokens", str(int(torii_max_new_tokens)),
                    "--temperature", str(float(torii_temperature)),
                    "--top_p", str(float(torii_top_p)),
                    "--top_k", str(int(torii_top_k)),
                    "--prefix", torii_prefix or "",
                    "--suffix", final_suffix,
                ]
                if torii_style == "Custom" and (torii_custom_prompt or "").strip():
                    args += ["--custom_prompt", torii_custom_prompt.strip()]

            out, err = _run_subprocess(py_exe, args)
            return out.strip(), (err or ("✅ Done." if out.strip() else "⚠️ No caption returned."))

        backend.change(
            _backend_note_cb,
            inputs=[backend],
            outputs=[backend_hint, gguf_session_acc, joy_settings_acc, torii_settings_acc, load_session_btn],
            queue=False,
        )
        load_session_btn.click(
            _load_session_cb,
            inputs=[py_exe, backend, model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads, torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads],
            outputs=[session_msg],
            queue=False,
        )
        unload_session_btn.click(_unload_session_cb, inputs=[py_exe], outputs=[session_msg], queue=False)
        run_batch.click(
            _run_batch,
            inputs=[
                py_exe,
                backend,
                model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads,
                style, length, custom_prompt, max_new_tokens, temperature, top_p, top_k,
                torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads,
                torii_style, torii_length, torii_custom_prompt, torii_max_new_tokens, torii_temperature, torii_top_p, torii_top_k,
                torii_prefix, torii_suffix, torii_output_style,
                prefix, suffix,
                in_dir, out_dir, recursive, skip_existing, start_from, sort_method,
            ],
            outputs=[log],
        )
        run_single.click(
            _run_single,
            inputs=[
                py_exe,
                backend,
                model_path, mmproj_path, n_ctx, n_gpu_layers, n_threads,
                style, length, custom_prompt, max_new_tokens, temperature, top_p, top_k,
                torii_model_path, torii_mmproj_path, torii_n_ctx, torii_n_gpu_layers, torii_n_threads,
                torii_style, torii_length, torii_custom_prompt, torii_max_new_tokens, torii_temperature, torii_top_p, torii_top_k,
                torii_prefix, torii_suffix, torii_output_style,
                prefix, suffix,
                single_img,
            ],
            outputs=[single_caption, log],
        )
