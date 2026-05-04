from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts.roleplay_v2_package_records import build_portable_package_manifest, ROLEPLAY_V2_PACKAGE_EXTENSIONS
from .roleplay_v2_package_store import clone_record, export_file_path, load_saved_record, save_package_manifest


def _slugify(text: str, fallback: str = 'bundle') -> str:
    clean = re.sub(r'[^a-z0-9]+', '-', str(text or '').strip().lower()).strip('-')
    return clean or fallback



def _clean_list(value: Any) -> list[str]:
    out: list[str] = []
    for item in value or []:
        text = str(item or '').strip()
        if text:
            out.append(text)
    return out



def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()



def _linked_records(record_type: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if record_type == 'creator_draft':
        draft_id = str(record.get('id') or '').strip()
        from .roleplay_v2_package_store import load_saved_record  # local import to avoid circular feeling
        helper_dir_candidates = []
        # direct helper pair by scanning likely file names is not available here; try matching by helper_output draft_id via directory scan later if needed.
        # phase 3 keeps it lean: include directly linked helper output if caller already exported it separately.
        _ = helper_dir_candidates
    return out



def export_record_json(record_type: str, record_id: str) -> tuple[dict[str, Any], str]:
    record = load_saved_record(record_type, record_id)
    if not record:
        raise ValueError('Saved Roleplay V2 record not found.')
    base = clone_record(record)
    title = str(base.get('label') or base.get('title') or base.get('id') or 'record').strip()
    filename = f'roleplay_v2_{record_type}_{_slugify(title, str(record_id or "record"))}.json'
    return base, filename



def _infer_package_extension(records: list[dict[str, Any]]) -> str:
    if len(records) == 1 and isinstance(records[0], dict):
        kind = str(records[0].get('kind') or '').strip().lower()
        return ROLEPLAY_V2_PACKAGE_EXTENSIONS.get(kind, ROLEPLAY_V2_PACKAGE_EXTENSIONS['bundle'])
    return ROLEPLAY_V2_PACKAGE_EXTENSIONS['bundle']



def build_package_from_saved_records(*, sources: list[tuple[str, str]], title: str = '', package_type: str = 'bundle', asset_paths: list[str] | None = None) -> tuple[Path, dict[str, Any]]:
    if not sources:
        raise ValueError('Choose at least one saved Roleplay V2 record.')
    records: list[dict[str, Any]] = []
    for record_type, record_id in sources:
        rec = load_saved_record(record_type, record_id)
        if not rec:
            raise ValueError(f'Saved record not found: {record_type}:{record_id}')
        records.append(clone_record(rec))
    primary = records[0]
    primary_record_type = str(primary.get('record_type') or '').strip().lower()
    primary_record_id = str(primary.get('id') or '').strip()
    package_title = str(title or primary.get('label') or primary.get('title') or primary_record_id or 'Roleplay Bundle').strip()
    package_id = f'pkg_{uuid4().hex[:10]}'
    extension = _infer_package_extension(records)
    filename = f'{_slugify(package_title, package_id)}{extension}'
    path = export_file_path(filename)
    checksums: dict[str, Any] = {}
    assets = []
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for record in records:
            record_id = str(record.get('id') or '').strip()
            record_type = str(record.get('record_type') or '').strip().lower()
            rel_path = f'records/{record_type}/{record_id}.json'
            raw = json.dumps(record, indent=2, ensure_ascii=False).encode('utf-8')
            archive.writestr(rel_path, raw)
            checksums[rel_path] = _sha256_bytes(raw)
        for raw_asset in _clean_list(asset_paths or []):
            asset_path = Path(raw_asset)
            if not asset_path.exists() or not asset_path.is_file():
                continue
            rel_path = f'assets/{asset_path.name}'
            data = asset_path.read_bytes()
            archive.writestr(rel_path, data)
            checksums[rel_path] = _sha256_bytes(data)
            assets.append(rel_path)
        manifest = build_portable_package_manifest(
            package_id=package_id,
            package_type=package_type,
            title=package_title,
            primary_record_type=primary_record_type,
            primary_record_id=primary_record_id,
            included_record_ids=[str(record.get('id') or '').strip() for record in records],
            asset_paths=assets,
            schema_versions={
                'package': 1,
                'records': {str(record.get('id') or '').strip(): int(record.get('schema_version') or 1) for record in records},
            },
            checksums=checksums,
        )
        archive.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8'))
    save_package_manifest(manifest)
    return path, manifest
