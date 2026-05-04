from __future__ import annotations

from typing import Any, Dict

from ..contracts.settings_schema import DEFAULT_APP_SETTINGS, normalize_app_settings_payload
from .library_common import atomic_write_json, read_json_dict
from .library_constants import SETTINGS_PATH


def load_app_settings() -> Dict[str, Any]:
    data = read_json_dict(SETTINGS_PATH)
    return normalize_app_settings_payload(data)


def save_app_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = normalize_app_settings_payload(data)
    atomic_write_json(SETTINGS_PATH, payload)
    return payload
