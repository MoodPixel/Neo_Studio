"""Compatibility bridge for the built-in Scene Director extension.

Phase 20 moved the real Scene Director implementation to:
    neo_extensions/installed/neo_scene_director/

Existing generation code may still import:
    neo_studio_v1.extensions.image.scene_director.adapter

Keep this tiny bridge until all internal imports are pointed directly at the
extension runtime. Do not add new Scene Director logic here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT_DIR = Path(__file__).resolve().parents[4]
_EXTENSION_ADAPTER = _ROOT_DIR / 'neo_extensions' / 'installed' / 'neo_scene_director' / 'adapter.py'
_loaded_module: ModuleType | None = None


def _load_extension_adapter() -> ModuleType:
    global _loaded_module
    if _loaded_module is not None:
        return _loaded_module
    if not _EXTENSION_ADAPTER.exists():
        raise ImportError(f'Neo Scene Director extension adapter was not found: {_EXTENSION_ADAPTER}')
    spec = importlib.util.spec_from_file_location('neo_scene_director_builtin_adapter', _EXTENSION_ADAPTER)
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load Neo Scene Director extension adapter: {_EXTENSION_ADAPTER}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _loaded_module = module
    return module


def __getattr__(name: str) -> Any:
    return getattr(_load_extension_adapter(), name)


def normalize_scene_director_state(*args: Any, **kwargs: Any) -> Any:
    return _load_extension_adapter().normalize_scene_director_state(*args, **kwargs)


def scene_director_to_regional_payload(*args: Any, **kwargs: Any) -> Any:
    return _load_extension_adapter().scene_director_to_regional_payload(*args, **kwargs)


def patch_workflow(*args: Any, **kwargs: Any) -> Any:
    return _load_extension_adapter().patch_workflow(*args, **kwargs)
