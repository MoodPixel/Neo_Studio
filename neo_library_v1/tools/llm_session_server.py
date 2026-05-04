# -*- coding: utf-8 -*-
import base64
import gc
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

from llm_prompt_cli import SYSTEM_PROMPT as TEXT_SYSTEM_PROMPT, build_user_prompt, build_completion_prompt, _extract_json, _looks_like_failed_output
from joy_gguf_caption_cli import build_prompts as joy_build_prompts
from toriigate_gguf_caption_cli import build_prompts as torii_build_prompts

TEXT_STATE = {"llm": None, "key": None}
VISION_STATE = {"llm": None, "chat_handler": None, "key": None, "kind": None}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _cleanup_cuda():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _safe_close(obj):
    if obj is None:
        return
    try:
        close_fn = getattr(obj, "close", None)
        if callable(close_fn):
            close_fn()
    except Exception:
        pass


def _strip_reasoning_markup(text):
    text = (text or "")
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S|re.I)
    text = re.sub(r"^\s*</?think>\s*$", " ", text, flags=re.I|re.M)
    text = text.replace("<think>", " ").replace("</think>", " ")
    return text.strip()


def _unload_text():
    global TEXT_STATE
    _safe_close(TEXT_STATE.get("llm"))
    TEXT_STATE = {"llm": None, "key": None}
    _cleanup_cuda()


def _unload_vision():
    global VISION_STATE
    _safe_close(VISION_STATE.get("llm"))
    _safe_close(VISION_STATE.get("chat_handler"))
    VISION_STATE = {"llm": None, "chat_handler": None, "key": None, "kind": None}
    _cleanup_cuda()


def _image_path_to_data_uri(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _caption_once(llm, image_path: str, system_prompt: str, user_prompt: str, max_new_tokens: int, temperature: float, top_p: float, top_k: int) -> str:
    data_uri = _image_path_to_data_uri(image_path)
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
    try:
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        try:
            return resp["choices"][0]["text"].strip()
        except Exception:
            return str(resp).strip()


def _load_text(cmd):
    from llama_cpp import Llama

    model_path = (cmd.get("model_path") or "").strip().strip('"')
    if not model_path or not os.path.exists(model_path):
        return {"ok": False, "error": f"Model not found: {model_path}"}

    key = {
        "model_path": model_path,
        "n_ctx": int(cmd.get("n_ctx", 4096)),
        "n_gpu_layers": int(cmd.get("n_gpu_layers", 0)),
        "n_threads": int(cmd.get("n_threads", 8)),
    }

    if TEXT_STATE.get("llm") is not None and TEXT_STATE.get("key") == key:
        return {"ok": True, "message": "Text model already loaded.", "loaded": True, "key": key}

    _unload_text()
    llm = Llama(
        model_path=model_path,
        n_ctx=key["n_ctx"],
        n_gpu_layers=key["n_gpu_layers"],
        n_threads=key["n_threads"],
        verbose=False,
    )
    TEXT_STATE["llm"] = llm
    TEXT_STATE["key"] = key
    return {"ok": True, "message": "Text model loaded.", "loaded": True, "key": key}


def _run_prompt(cmd):
    llm = TEXT_STATE.get("llm")
    if llm is None:
        return {"ok": False, "error": "No text model loaded."}

    payload = cmd.get("payload") or {}
    temperature = float(payload.get("temperature", 0.7))
    top_p = float(payload.get("top_p", 0.9))
    max_tokens = int(payload.get("max_tokens", 512))
    repeat_penalty = float(payload.get("repeat_penalty", 1.10))
    user_prompt = build_user_prompt(payload)

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
                    {"role": "system", "content": TEXT_SYSTEM_PROMPT},
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
            return {"ok": False, "error": f"generation_failed: {e}"}

    positive = (data.get("positive") or "").strip()
    negative = (data.get("negative") or "").strip()
    if not negative:
        negative = (payload.get("current_negative") or "").strip()

    if _looks_like_failed_output(clean_text, {"positive": positive, "negative": negative}, payload):
        return {
            "ok": False,
            "error": "The model did not produce a usable rewritten/generated prompt.",
            "raw": (clean_text or out_text)[:5000],
        }

    return {"ok": True, "positive": positive, "negative": negative, "raw": (clean_text or out_text)[:5000]}

def _load_vision(cmd):
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    kind = (cmd.get("kind") or "joy").strip().lower()
    model_path = (cmd.get("model_path") or "").strip().strip('"')
    mmproj_path = (cmd.get("mmproj_path") or "").strip().strip('"')
    if not model_path or not os.path.exists(model_path):
        return {"ok": False, "error": f"Model not found: {model_path}"}
    if not mmproj_path or not os.path.exists(mmproj_path):
        return {"ok": False, "error": f"mmproj not found: {mmproj_path}"}

    key = {
        "kind": kind,
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "n_ctx": int(cmd.get("n_ctx", 4096)),
        "n_gpu_layers": int(cmd.get("n_gpu_layers", -1)),
        "n_threads": int(cmd.get("n_threads", 8)),
    }

    if VISION_STATE.get("llm") is not None and VISION_STATE.get("key") == key:
        return {"ok": True, "message": "Vision model already loaded.", "loaded": True, "key": key}

    _unload_vision()
    chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
    llm = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=key["n_ctx"],
        logits_all=True,
        n_gpu_layers=key["n_gpu_layers"],
        n_threads=key["n_threads"],
        verbose=False,
    )
    VISION_STATE["llm"] = llm
    VISION_STATE["chat_handler"] = chat_handler
    VISION_STATE["key"] = key
    VISION_STATE["kind"] = kind
    return {"ok": True, "message": "Vision model loaded.", "loaded": True, "key": key}


def _run_caption(cmd):
    llm = VISION_STATE.get("llm")
    if llm is None:
        return {"ok": False, "error": "No vision model loaded."}
    image_path = (cmd.get("image_path") or "").strip()
    if not image_path or not os.path.exists(image_path):
        return {"ok": False, "error": f"Image not found: {image_path}"}

    caption = _caption_once(
        llm,
        image_path,
        cmd.get("system_prompt") or "Describe the image.",
        cmd.get("user_prompt") or "Describe the image.",
        int(cmd.get("max_new_tokens", 256)),
        float(cmd.get("temperature", 0.6)),
        float(cmd.get("top_p", 0.9)),
        int(cmd.get("top_k", 0)),
    )
    return {"ok": True, "caption": caption}


def _status_text():
    return {"ok": True, "loaded": TEXT_STATE.get("llm") is not None, "key": TEXT_STATE.get("key")}


def _status_vision():
    return {"ok": True, "loaded": VISION_STATE.get("llm") is not None, "key": VISION_STATE.get("key")}


def main():
    for raw in sys.stdin:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            cmd = json.loads(raw)
        except Exception as e:
            _send({"ok": False, "error": f"Invalid JSON: {e}"})
            continue

        op = (cmd.get("op") or "").strip()
        try:
            if op == "ping":
                _send({"ok": True, "message": "pong"})
            elif op == "shutdown":
                _unload_text()
                _unload_vision()
                _send({"ok": True, "message": "bye"})
                break
            elif op == "load_text":
                _send(_load_text(cmd))
            elif op == "run_prompt":
                _send(_run_prompt(cmd))
            elif op == "status_text":
                _send(_status_text())
            elif op == "unload_text":
                _unload_text()
                _send({"ok": True, "message": "Text model unloaded.", "loaded": False})
            elif op == "load_vision":
                _send(_load_vision(cmd))
            elif op == "caption_single":
                _send(_run_caption(cmd))
            elif op == "status_vision":
                _send(_status_vision())
            elif op == "unload_vision":
                _unload_vision()
                _send({"ok": True, "message": "Vision model unloaded.", "loaded": False})
            else:
                _send({"ok": False, "error": f"Unknown op: {op}"})
        except Exception as e:
            _send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
