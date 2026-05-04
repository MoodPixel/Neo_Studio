from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts.roleplay_v2_package_records import build_portable_package_manifest
from .roleplay_v2_package_store import import_file_path, save_package_manifest, save_record
from .storage_io import atomic_write_json, read_json_object

PACKAGE_PREVIEW_PREFIX = 'package_preview'
SUPPORTED_IMPORT_MODES = {'replace_existing', 'copy_as_new'}


def _slugify(text: str, fallback: str = 'bundle') -> str:
    clean = re.sub(r'[^a-z0-9]+', '-', str(text or '').strip().lower()).strip('-')
    return clean or fallback



def _preview_json_path(preview_id: str) -> Path:
    return import_file_path(f'{preview_id}.json')



def _preview_package_path(preview_id: str, suffix: str) -> Path:
    return import_file_path(f'{preview_id}{suffix}')



def _replace_ids(value: Any, id_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: _replace_ids(v, id_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item, id_map) for item in value]
    if isinstance(value, str):
        return id_map.get(value, value)
    return value



def preview_package_upload(filename: str, content: bytes) -> dict[str, Any]:
    clean_name = str(filename or 'roleplay_v2_bundle.zip').strip()
    suffix = Path(clean_name).suffix.lower() or '.neobundle'
    preview_id = f'{PACKAGE_PREVIEW_PREFIX}_{uuid4().hex[:10]}'
    package_path = _preview_package_path(preview_id, suffix)
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_bytes(content)
    records: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None
    with zipfile.ZipFile(package_path, 'r') as archive:
        for name in archive.namelist():
            if name == 'manifest.json':
                try:
                    manifest = json.loads(archive.read(name).decode('utf-8'))
                except Exception:
                    manifest = None
            elif name.startswith('records/') and name.endswith('.json'):
                try:
                    records.append(json.loads(archive.read(name).decode('utf-8')))
                except Exception:
                    continue
    if not isinstance(manifest, dict):
        manifest = build_portable_package_manifest(title=Path(clean_name).stem)
    preview = {
        'preview_id': preview_id,
        'record_type': 'roleplay_v2_package_preview',
        'filename': clean_name,
        'package_path': str(package_path),
        'manifest': manifest,
        'record_count': len(records),
        'records': records,
        'next_actions': ['import_preview', 'commit_import'],
    }
    atomic_write_json(_preview_json_path(preview_id), preview)
    return preview



def read_package_preview(preview_id: str) -> dict[str, Any]:
    data = read_json_object(_preview_json_path(preview_id), None)
    if not isinstance(data, dict):
        raise ValueError('Package preview not found.')
    return data



def commit_package_preview(preview_id: str, *, import_mode: str = 'replace_existing') -> dict[str, Any]:
    clean_mode = str(import_mode or 'replace_existing').strip().lower()
    if clean_mode not in SUPPORTED_IMPORT_MODES:
        raise ValueError('Unsupported package import mode.')
    preview = read_package_preview(preview_id)
    records = copy.deepcopy(preview.get('records') or [])
    if not records:
        raise ValueError('Package preview contains no importable records.')
    id_map: dict[str, str] = {}
    if clean_mode == 'copy_as_new':
        for record in records:
            old_id = str(record.get('id') or '').strip()
            if old_id:
                id_map[old_id] = f'{old_id}_copy_{uuid4().hex[:6]}'
        records = [_replace_ids(record, id_map) for record in records]
        for record in records:
            old_id = str(record.get('id') or '').strip()
            for prev_old, new_id in id_map.items():
                if old_id == prev_old:
                    record['id'] = new_id
                    break
    saved: list[dict[str, Any]] = []
    for record in records:
        saved_record = save_record(record)
        saved.append({'record_type': saved_record.get('record_type', ''), 'id': saved_record.get('id', '')})
    manifest = copy.deepcopy(preview.get('manifest') or {})
    if isinstance(manifest, dict) and manifest.get('record_type') == 'portable_package_manifest':
        if id_map:
            manifest = _replace_ids(manifest, id_map)
            if manifest.get('id'):
                manifest['id'] = f"{manifest['id']}_imported_{uuid4().hex[:6]}"
        save_package_manifest(manifest)
    return {
        'ok': True,
        'preview_id': preview_id,
        'import_mode': clean_mode,
        'saved_count': len(saved),
        'saved_records': saved,
        'id_map': id_map,
    }
