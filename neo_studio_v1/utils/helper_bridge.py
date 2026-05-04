from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts.helper_packets import normalize_helper_packet
from .shared_data_paths import studio_data_path
from .storage_io import atomic_write_json, read_json_object

HELPER_PACKET_STORE_PATH = studio_data_path('helper_packets.json', legacy_rel='helper_packets.json', default_json={'packets': []})


def _normalize_store(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    packets = raw.get('packets') if isinstance(raw.get('packets'), list) else []
    return {
        'schema_version': 1,
        'packets': [normalize_helper_packet(item) for item in packets if isinstance(item, dict)],
    }


def load_helper_packets() -> dict[str, Any]:
    return _normalize_store(read_json_object(HELPER_PACKET_STORE_PATH, {'packets': []}))


def list_helper_packets(*, source_surface: str = '', target_mode: str = '', limit: int = 20) -> list[dict[str, Any]]:
    payload = load_helper_packets()
    source_surface = str(source_surface or '').strip().lower()
    target_mode = str(target_mode or '').strip().lower()
    out = []
    for item in reversed(payload.get('packets') or []):
        if source_surface and str(item.get('source_surface') or '').strip().lower() != source_surface:
            continue
        if target_mode and str(item.get('target_mode') or '').strip().lower() != target_mode:
            continue
        out.append(item)
        if len(out) >= max(1, int(limit or 20)):
            break
    return out


def create_helper_packet(record: dict[str, Any]) -> dict[str, Any]:
    payload = load_helper_packets()
    clean = normalize_helper_packet(record)
    packets = payload.get('packets') or []
    packets.append(clean)
    store = {'schema_version': 1, 'packets': packets}
    HELPER_PACKET_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(HELPER_PACKET_STORE_PATH, store)
    return clean
