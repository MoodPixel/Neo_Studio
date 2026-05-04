import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

_EXT_ROOT = Path(__file__).resolve().parents[1]
_SERVER_PATH = _EXT_ROOT / "tools" / "llm_session_server.py"

_LOCK = threading.Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {
    "prompt": {"proc": None, "pyexe": "", "lock": threading.RLock()},
    "caption": {"proc": None, "pyexe": "", "lock": threading.RLock()},
}


def _norm_pyexe(pyexe: Optional[str]) -> str:
    pyexe = (pyexe or "").strip().strip('"')
    return pyexe or sys.executable


def _session_entry(kind: str) -> Dict[str, Any]:
    if kind not in _SESSIONS:
        raise ValueError(f"Unknown session kind: {kind}")
    return _SESSIONS[kind]


def _start_server(pyexe: str):
    return subprocess.Popen(
        [pyexe, str(_SERVER_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )


def _kill_proc(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _ensure_process(kind: str, pyexe: Optional[str]):
    pyexe = _norm_pyexe(pyexe)
    entry = _session_entry(kind)
    proc = entry.get("proc")
    if proc is not None and proc.poll() is None and entry.get("pyexe") == pyexe:
        return proc

    if proc is not None:
        _kill_proc(proc)

    proc = _start_server(pyexe)
    entry["proc"] = proc
    entry["pyexe"] = pyexe

    # handshake
    resp = _rpc(kind, pyexe, {"op": "ping"}, allow_restart=False)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "Failed to start LLM session server")
    return proc


def _rpc(kind: str, pyexe: Optional[str], payload: Dict[str, Any], allow_restart: bool = True) -> Dict[str, Any]:
    entry = _session_entry(kind)
    with entry["lock"]:
        proc = _ensure_process(kind, pyexe)
        try:
            if proc.stdin is None or proc.stdout is None:
                raise RuntimeError("LLM session pipes are unavailable")
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("No response from LLM session server")
            data = json.loads(line)
            return data if isinstance(data, dict) else {"ok": False, "error": "invalid_server_response"}
        except Exception as e:
            if allow_restart:
                _kill_proc(entry.get("proc"))
                entry["proc"] = None
                return _rpc(kind, pyexe, payload, allow_restart=False)
            return {"ok": False, "error": str(e)}


def prompt_load(pyexe: str, model_path: str, n_ctx: int, n_gpu_layers: int, n_threads: int) -> Dict[str, Any]:
    return _rpc("prompt", pyexe, {
        "op": "load_text",
        "model_path": model_path,
        "n_ctx": int(n_ctx),
        "n_gpu_layers": int(n_gpu_layers),
        "n_threads": int(n_threads),
    })


def prompt_status(pyexe: str) -> Dict[str, Any]:
    return _rpc("prompt", pyexe, {"op": "status_text"})


def prompt_unload(pyexe: str) -> Dict[str, Any]:
    return _rpc("prompt", pyexe, {"op": "unload_text"})


def prompt_run(pyexe: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _rpc("prompt", pyexe, {"op": "run_prompt", "payload": payload})


def caption_load(pyexe: str, kind: str, model_path: str, mmproj_path: str, n_ctx: int, n_gpu_layers: int, n_threads: int) -> Dict[str, Any]:
    return _rpc("caption", pyexe, {
        "op": "load_vision",
        "kind": kind,
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "n_ctx": int(n_ctx),
        "n_gpu_layers": int(n_gpu_layers),
        "n_threads": int(n_threads),
    })


def caption_status(pyexe: str) -> Dict[str, Any]:
    return _rpc("caption", pyexe, {"op": "status_vision"})


def caption_unload(pyexe: str) -> Dict[str, Any]:
    return _rpc("caption", pyexe, {"op": "unload_vision"})


def caption_run(pyexe: str, image_path: str, system_prompt: str, user_prompt: str, max_new_tokens: int, temperature: float, top_p: float, top_k: int) -> Dict[str, Any]:
    return _rpc("caption", pyexe, {
        "op": "caption_single",
        "image_path": image_path,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "max_new_tokens": int(max_new_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
        "top_k": int(top_k),
    })


def shutdown_all() -> None:
    for kind, entry in _SESSIONS.items():
        with entry["lock"]:
            proc = entry.get("proc")
            if proc is None:
                continue
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write(json.dumps({"op": "shutdown"}) + "\n")
                    proc.stdin.flush()
            except Exception:
                pass
            _kill_proc(proc)
            entry["proc"] = None
            entry["pyexe"] = ""
