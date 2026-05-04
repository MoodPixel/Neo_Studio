from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

ROLEPLAY_V2_PACKAGE_SCHEMA_VERSION = 1
ROLEPLAY_V2_PACKAGE_EXTENSIONS = {
    'character': '.neochar',
    'world': '.neoworld',
    'universe': '.neouniverse',
    'bundle': '.neobundle',
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _clean(value: Any, *, lower: bool = False, limit: int = 0) -> str:
    text = str(value or '').strip()
    if lower:
        text = text.lower()
    if limit > 0:
        text = text[:limit]
    return text



def _clean_list(values: Any, *, limit: int = 0) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = _clean(item, limit=limit)
        if text:
            out.append(text)
    return out



def _json_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}



def build_portable_package_manifest(*, package_id: str = '', package_type: str = 'bundle', title: str = '', primary_record_type: str = '', primary_record_id: str = '', included_record_ids: list[str] | None = None, asset_paths: list[str] | None = None, schema_versions: dict[str, Any] | None = None, checksums: dict[str, Any] | None = None, created_with: str = 'neo_studio_v1', meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_PACKAGE_SCHEMA_VERSION,
        'record_type': 'portable_package_manifest',
        'id': _clean(package_id) or f'pkg_{uuid4().hex[:10]}',
        'package_type': _clean(package_type or 'bundle', lower=True, limit=40),
        'title': _clean(title, limit=200),
        'primary_record_type': _clean(primary_record_type, lower=True, limit=80),
        'primary_record_id': _clean(primary_record_id, limit=120),
        'included_record_ids': _clean_list(included_record_ids or [], limit=120),
        'asset_paths': _clean_list(asset_paths or [], limit=400),
        'schema_versions': _json_dict(schema_versions),
        'checksums': _json_dict(checksums),
        'created_with': _clean(created_with, limit=120),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'ready', lower=True),
            'notes': _clean(meta_row.get('notes'), limit=4000),
        },
    }
