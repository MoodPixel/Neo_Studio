import argparse
import base64
import mimetypes
import os
from pathlib import Path
from typing import List

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

def image_path_to_data_uri(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def build_prompts(style: str, length: str, custom_prompt: str, prefix: str, suffix: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_text_prompt)
    """
    system_prompt = "You are an assistant that captions images accurately and helpfully. Handle both anime and realistic styles."
    length_hint = ""
    if length == "short":
        length_hint = "Keep it short (one sentence)."
    elif length == "long":
        length_hint = "Be detailed."

    if style == "Descriptive":
        user = f"Describe the image. {length_hint}".strip()
    elif style == "Stable Diffusion Prompt":
        # tag-like output, no brand guessing
        user = (
            "Write a Stable Diffusion prompt describing the image. "
            "Output a comma-separated list of concise tags. "
            "Don't guess brands or names. "
            "Include appearance, clothing, pose, lighting, style (anime or realistic), mood. "
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

def list_images(in_dir: str, recursive: bool, sort_method: str) -> List[Path]:
    root = Path(in_dir)
    if not root.exists():
        return []
    if recursive:
        files = [p for p in root.rglob("*") if p.suffix.lower() in IMG_EXTS and p.is_file()]
    else:
        files = [p for p in root.iterdir() if p.suffix.lower() in IMG_EXTS and p.is_file()]

    if sort_method == "alphabetical":
        files.sort(key=lambda p: str(p).lower())
    else:
        # "sequential" => keep filesystem order; but rglob/iterdir already yields something deterministic-ish.
        # Still stabilize a bit by name to avoid total randomness between runs:
        files.sort(key=lambda p: (p.parent.as_posix().lower(), p.name.lower()))
    return files

def load_llava(model_path: str, mmproj_path: str, n_ctx: int, n_gpu_layers: int, n_threads: int):
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
    llm = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=n_ctx,
        logits_all=True,
        n_gpu_layers=n_gpu_layers,
        n_threads=n_threads,
    )
    return llm

def infer_one(llm, image_path: str, system_prompt: str, user_prompt: str,
              max_new_tokens: int, temperature: float, top_p: float, top_k: int) -> str:

    data_uri = image_path_to_data_uri(image_path)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": user_prompt},
        ]},
    ]

    resp = llm.create_chat_completion(
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        max_tokens=max_new_tokens,
    )

    # Try common response shapes
    try:
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        try:
            return resp["choices"][0]["text"].strip()
        except Exception:
            return str(resp).strip()

def caption_to_txt_path(img_path: Path, out_dir: str | None) -> Path:
    if out_dir:
        out_root = Path(out_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        return out_root / (img_path.stem + ".txt")
    return img_path.with_suffix(".txt")

def main():
    ap = argparse.ArgumentParser(description="ToriiGate GGUF captioner (llama-cpp-python) — batch + single.")
    ap.add_argument("--model", required=True, help="Main GGUF model path (ToriiGate).")
    ap.add_argument("--mmproj", required=True, help="mmproj GGUF path.")
    ap.add_argument("--n_ctx", type=int, default=4096)
    ap.add_argument("--n_gpu_layers", type=int, default=-1, help="-1=auto/all")
    ap.add_argument("--n_threads", type=int, default=8)

    ap.add_argument("--style", choices=["Descriptive", "Stable Diffusion Prompt", "Custom"], default="Stable Diffusion Prompt")
    ap.add_argument("--length", choices=["short", "any", "long"], default="long")
    ap.add_argument("--custom_prompt", default="")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--suffix", default="")

    ap.add_argument("--max_new_tokens", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top_p", type=float, default=0.9)
    ap.add_argument("--top_k", type=int, default=0)

    ap.add_argument("--single", default="", help="Caption a single image path (no file writing unless --write_single).")
    ap.add_argument("--write_single", action="store_true", help="If set, writes .txt for --single as well.")

    ap.add_argument("--in_dir", default="", help="Input folder for batch mode.")
    ap.add_argument("--out_dir", default="", help="Output folder for .txt captions (optional).")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--skip_existing", action="store_true")
    ap.add_argument("--start_from", type=int, default=0)
    ap.add_argument("--sort_method", choices=["sequential", "alphabetical"], default="sequential")

    args = ap.parse_args()

    if not args.single and not args.in_dir:
        raise SystemExit("Provide --single <image> or --in_dir <folder>.")

    # Validate model paths early
    if not os.path.exists(args.model):
        raise SystemExit(f"Model not found: {args.model}")
    if not os.path.exists(args.mmproj):
        raise SystemExit(f"mmproj not found: {args.mmproj}")

    system_prompt, user_prompt = build_prompts(args.style, args.length, args.custom_prompt, args.prefix, args.suffix)

    llm = load_llava(args.model, args.mmproj, args.n_ctx, args.n_gpu_layers, args.n_threads)

    if args.single:
        cap = infer_one(
            llm, args.single, system_prompt, user_prompt,
            args.max_new_tokens, args.temperature, args.top_p, args.top_k
        )
        print(cap)
        if args.write_single:
            p = Path(args.single)
            out = caption_to_txt_path(p, args.out_dir or None)
            out.write_text(cap, encoding="utf-8")
        return

    images = list_images(args.in_dir, args.recursive, args.sort_method)
    if args.start_from:
        images = images[args.start_from:]

    if not images:
        print("No images found.")
        return

    out_dir = args.out_dir.strip() if args.out_dir else None
    done = 0
    skipped = 0

    for img in images:
        txt_path = caption_to_txt_path(img, out_dir)
        if args.skip_existing and txt_path.exists():
            skipped += 1
            continue

        cap = infer_one(
            llm, str(img), system_prompt, user_prompt,
            args.max_new_tokens, args.temperature, args.top_p, args.top_k
        )
        txt_path.write_text(cap, encoding="utf-8")
        done += 1
        print(f"[{done}] {img.name} -> {txt_path.name}")

    print(f"✅ Completed. wrote={done}, skipped={skipped}, total={done+skipped}")

if __name__ == "__main__":
    main()