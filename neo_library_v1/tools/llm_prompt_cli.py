# -*- coding: utf-8 -*-
"""
Text-only GGUF LLM prompt helper for SDXL Prompt Builder.
Runs outside Forge's Python via user-provided venv python.exe.
"""

import argparse
import json
import os
import re
import sys


SYSTEM_PROMPT = (
    "You are a Stable Diffusion XL prompt engineer. "
    "Goal: produce copy-ready SDXL prompts for image generation.\n"
    "Rules:\n"
    "- Keep content non-explicit. If sensual, keep it tasteful and non-graphic (editorial / implied).\n"
    "- Prefer concrete visual nouns/adjectives over prose.\n"
    "- Do not output chain-of-thought, reasoning, analysis, markdown, or <think> tags.\n"
    "- Output STRICT JSON ONLY with keys: positive, negative.\n"
    "- positive should be a single line. negative should be a single line.\n"
)

def _safe_int(x, default):
    try:
        return int(x)
    except Exception:
        return default

def _safe_float(x, default):
    try:
        return float(x)
    except Exception:
        return default

def _strip_reasoning_markup(text):
    text = (text or "")
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S|re.I)
    text = re.sub(r"^\s*</?think>\s*$", " ", text, flags=re.I|re.M)
    text = text.replace("<think>", " ").replace("</think>", " ")
    return text.strip()

def _extract_json(text):
    text = (text or "").strip()
    # Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find first {...} block
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        blob = m.group(0)
        try:
            return json.loads(blob)
        except Exception:
            # Try to clean trailing commas
            blob2 = re.sub(r",\s*}", "}", blob)
            blob2 = re.sub(r",\s*]", "]", blob2)
            try:
                return json.loads(blob2)
            except Exception:
                return None
    return None


def _looks_like_failed_output(clean_text, data, payload):
    text = (clean_text or "").strip()
    pos = (data.get("positive") or "").strip() if isinstance(data, dict) else ""
    cur_pos = (payload.get("current_positive") or "").strip()

    if pos:
        norm_new = re.sub(r"\s+", " ", pos).strip().lower()
        norm_old = re.sub(r"\s+", " ", cur_pos).strip().lower()
        if norm_old and norm_new == norm_old:
            return True
        return False

    if not text:
        return True

    lowered = text.lower()
    bad_markers = [
        "task:",
        "rewrite/improve these sdxl prompts",
        "return json only",
        "json:",
        "positive:",
        "negative:",
        "<think>",
        "</think>",
    ]
    if any(m in lowered for m in bad_markers):
        return True

    norm_text = re.sub(r"\s+", " ", text).strip().lower()
    norm_old = re.sub(r"\s+", " ", cur_pos).strip().lower()
    if norm_old and norm_text == norm_old:
        return True
    return False


def build_completion_prompt(payload):
    mode = (payload.get("mode") or "Rewrite current prompt").strip()
    idea = (payload.get("idea") or "").strip()
    cur_pos = (payload.get("current_positive") or "").strip()
    cur_neg = (payload.get("current_negative") or "").strip()
    tag_style = (payload.get("tag_style") or "Comma tags (SDXL)").strip()
    family_safe = bool(payload.get("family_safe", False))

    if "Paragraph" in tag_style:
        style_line = "Write a single-line realistic SDXL paragraph prompt with clear visual detail."
    elif "Comma" in tag_style:
        style_line = "Write a single-line comma-separated SDXL prompt."
    else:
        style_line = "Write a concise single-line SDXL prompt."

    lines = [
        "You are writing Stable Diffusion XL prompts.",
        "Return exactly one JSON object and nothing else.",
        "Schema: {\"positive\":\"...\",\"negative\":\"...\"}",
        "Do not use <think> tags.",
        "Do not explain.",
        "Do not repeat the instruction text.",
        style_line,
    ]
    if family_safe:
        lines.append("Keep it SFW and non-explicit.")

    if mode.lower().startswith("generate"):
        lines += [
            "Task: generate a new prompt from the idea below.",
            f"IDEA: {idea or 'cinematic realistic editorial portrait'}",
        ]
    else:
        lines += [
            "Task: rewrite and improve the current prompt.",
            "The rewritten positive prompt must not be identical to the original positive prompt.",
            f"CURRENT_POSITIVE: {cur_pos or '(empty)'}",
            f"CURRENT_NEGATIVE: {cur_neg or '(empty)'}",
        ]
        if idea:
            lines.append(f"EXTRA_DIRECTION: {idea}")

    lines.append("JSON:")
    return "\n".join(lines)

def build_user_prompt(payload):
    mode = (payload.get("mode") or "Rewrite current prompt").strip()
    idea = (payload.get("idea") or "").strip()
    cur_pos = (payload.get("current_positive") or "").strip()
    cur_neg = (payload.get("current_negative") or "").strip()

    preset = (payload.get("preset") or "").strip()
    tag_style = (payload.get("tag_style") or "Comma tags (SDXL)").strip()
    family_safe = bool(payload.get("family_safe", False))

    camera = (payload.get("camera") or "").strip()
    lighting = (payload.get("lighting") or "").strip()
    extra_negative = (payload.get("extra_negative") or "").strip()

    if "Paragraph" in tag_style:
        style_line = (
            "Use a single-line natural paragraph prompt for photoreal SDXL: "
            "descriptive phrases, clear visual details, minimal comma-tag spam."
        )
    elif "Comma" in tag_style:
        style_line = "Use comma-separated tags (SDXL style)."
    else:
        style_line = "Use short bullet-ish blocks separated by ' • '."

    if mode.lower().startswith("generate"):
        if not idea:
            idea = "two male fashion models, cinematic editorial"
        parts = [
            "Task: Generate SDXL positive+negative prompts from this idea:",
            idea,
        ]
    else:
        parts = [
            "Task: Rewrite/improve these SDXL prompts (keep meaning, improve clarity, reduce redundancy):",
            "POSITIVE:",
            cur_pos if cur_pos else "(empty)",
            "NEGATIVE:",
            cur_neg if cur_neg else "(empty)",
        ]
        if idea:
            parts += ["Extra direction:", idea]

    if preset:
        parts += ["Preset context:", preset]

    if family_safe:
        parts += ["Safety: Force SFW/wholesome wording (no nudity, no erotic terms)."]

    if camera:
        parts += ["Camera tags to include (if relevant):", camera]
    if lighting:
        parts += ["Lighting tags to include (if relevant):", lighting]

    if extra_negative:
        parts += ["Extra negatives to include:", extra_negative]

    parts += [
        style_line,
        "Return JSON only: {\"positive\":\"...\",\"negative\":\"...\"}",
    ]
    return "\n".join(parts)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to GGUF model")
    ap.add_argument("--payload", required=True, help="Path to payload JSON")
    args = ap.parse_args()

    if not os.path.exists(args.payload):
        print(json.dumps({"error": "payload_not_found"}))
        return 2

    with open(args.payload, "r", encoding="utf-8") as f:
        payload = json.load(f)

    model_path = args.model
    if not os.path.exists(model_path):
        print(json.dumps({"error": "model_not_found", "model": model_path}))
        return 2

    temperature = _safe_float(payload.get("temperature", 0.7), 0.7)
    top_p = _safe_float(payload.get("top_p", 0.9), 0.9)
    max_tokens = _safe_int(payload.get("max_tokens", 512), 512)
    repeat_penalty = _safe_float(payload.get("repeat_penalty", 1.10), 1.10)
    n_ctx = _safe_int(payload.get("n_ctx", 4096), 4096)
    n_gpu_layers = _safe_int(payload.get("n_gpu_layers", 0), 0)
    n_threads = _safe_int(payload.get("n_threads", 8), 8)

    user_prompt = build_user_prompt(payload)

    try:
        from llama_cpp import Llama
    except Exception as e:
        print(json.dumps({"error": "llama_cpp_import_failed", "detail": str(e)}))
        return 3

    llm = None
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=False,
        )
    except Exception as e:
        print(json.dumps({"error": "llama_init_failed", "detail": str(e)}))
        return 4

    out_text = ""
    clean_text = ""
    data = {}

    try:
        prompt = build_completion_prompt(payload)
        resp = llm.create_completion(
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            max_tokens=max_tokens,
            stop=["</s>", "<|eot_id|>", "<|end|>"],
        )
        out_text = resp["choices"][0]["text"]
        clean_text = _strip_reasoning_markup(out_text)
        data = _extract_json(clean_text) or {}
    except Exception:
        data = {}

    if _looks_like_failed_output(clean_text, data, payload):
        try:
            resp = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                max_tokens=max_tokens,
            )
            out_text = resp["choices"][0]["message"]["content"]
            clean_text = _strip_reasoning_markup(out_text)
            data = _extract_json(clean_text) or {}
        except Exception as e:
            print(json.dumps({"error": "generation_failed", "detail": str(e)}))
            return 5

    positive = (data.get("positive") or "").strip()
    negative = (data.get("negative") or "").strip()

    if not negative:
        negative = (payload.get("current_negative") or "").strip()

    if _looks_like_failed_output(clean_text, {"positive": positive, "negative": negative}, payload):
        print(json.dumps({
            "error": "invalid_or_echo_response",
            "detail": "The model did not produce a usable rewritten/generated prompt.",
            "raw": (clean_text or out_text)[:5000],
        }))
        return 6

    print(json.dumps({"positive": positive, "negative": negative, "raw": (clean_text or out_text)[:5000]}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
