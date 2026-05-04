from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _lock_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def _lock_for_path(path: Path) -> threading.RLock:
    key = _lock_key(path)
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextmanager
def path_lock(path: Path) -> Iterator[None]:
    lock = _lock_for_path(path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        with path_lock(path):
            text = path.read_text(encoding='utf-8')
        return json.loads(text)
    except Exception:
        return default


def read_json_object(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = read_json(path, default)
    if isinstance(data, dict):
        return data
    return default


def atomic_write_text(path: Path, text: str, *, encoding: str = 'utf-8', ensure_trailing_newline: bool = False, use_lock: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if ensure_trailing_newline and text and not text.endswith('\n'):
        text += '\n'
    lock_cm = path_lock(path) if use_lock else nullcontext()
    tmp = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    with lock_cm:
        try:
            tmp.write_text(text, encoding=encoding)
            os.replace(str(tmp), str(path))
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2, ensure_ascii: bool = False, ensure_trailing_newline: bool = True, use_lock: bool = True) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii),
        ensure_trailing_newline=ensure_trailing_newline,
        use_lock=use_lock,
    )
