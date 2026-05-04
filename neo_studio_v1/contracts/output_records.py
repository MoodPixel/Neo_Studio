from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .job_records import infer_generation_family

OUTPUT_RECORD_SCHEMA_VERSION = 2
GENERATION_OUTPUT_SIDECAR_SCHEMA_VERSION = 3


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def infer_output_media_type(filename: str = '') -> str:
    suffix = Path(str(filename or '')).suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
        return 'image'
    if suffix in {'.mp4', '.mov', '.mkv', '.webm'}:
        return 'video'
    if suffix in {'.wav', '.mp3', '.flac', '.ogg'}:
        return 'audio'
    return 'file'


def build_output_metadata_record(*, record_id: str, name: str, parsed: Dict[str, Any], source_filename: str = '', notes: str = '', source_job_id: str = '', source_output_id: str = '', parent_output_id: str = '', surface: str = 'generate', family: str = '', tags: list[str] | None = None) -> Dict[str, Any]:
    now = _now_iso()
    media_type = infer_output_media_type(source_filename)
    resolved_family = str(family or '').strip() or infer_generation_family(parsed if isinstance(parsed, dict) else {})
    return {
        'schema_version': OUTPUT_RECORD_SCHEMA_VERSION,
        'id': record_id,
        'kind': 'output_metadata',
        'record_type': 'output_metadata',
        'name': name,
        'created_at': now,
        'updated_at': now,
        'surface': surface,
        'family': resolved_family,
        'media_type': media_type,
        'source_filename': source_filename,
        'notes': (notes or '').strip(),
        'source_job_id': str(source_job_id or '').strip(),
        'source_output_id': str(source_output_id or '').strip(),
        'lineage': {
            'job_id': str(source_job_id or '').strip(),
            'output_id': str(source_output_id or '').strip(),
            'parent_output_id': str(parent_output_id or '').strip(),
        },
        'toolchain': {
            'parse_format': str((parsed or {}).get('parse_format') or ''),
            'model': str(((parsed or {}).get('settings') or {}).get('Model') or ''),
            'sampler': str(((parsed or {}).get('settings') or {}).get('Sampler') or ''),
        },
        'tags': list(tags or []),
        'data': deepcopy(parsed if isinstance(parsed, dict) else {}),
    }


def normalize_output_metadata_record(record: Dict[str, Any] | None) -> Dict[str, Any]:
    row = deepcopy(record) if isinstance(record, dict) else {}
    data = row.get('data') if isinstance(row.get('data'), dict) else {}
    source_filename = str(row.get('source_filename') or data.get('source_filename') or '').strip()
    media_type = str(row.get('media_type') or '').strip() or infer_output_media_type(source_filename)
    lineage = row.get('lineage') if isinstance(row.get('lineage'), dict) else {}
    family = str(row.get('family') or '').strip() or infer_generation_family(data)
    normalized = {
        'schema_version': OUTPUT_RECORD_SCHEMA_VERSION,
        'id': str(row.get('id') or '').strip(),
        'kind': str(row.get('kind') or 'output_metadata'),
        'record_type': str(row.get('record_type') or 'output_metadata'),
        'name': str(row.get('name') or Path(source_filename or 'output').stem).strip(),
        'created_at': str(row.get('created_at') or _now_iso()),
        'updated_at': str(row.get('updated_at') or row.get('created_at') or _now_iso()),
        'surface': str(row.get('surface') or 'generate'),
        'family': family,
        'media_type': media_type,
        'source_filename': source_filename,
        'notes': str(row.get('notes') or '').strip(),
        'source_job_id': str(row.get('source_job_id') or lineage.get('job_id') or '').strip(),
        'source_output_id': str(row.get('source_output_id') or lineage.get('output_id') or '').strip(),
        'lineage': {
            'job_id': str(lineage.get('job_id') or row.get('source_job_id') or '').strip(),
            'output_id': str(lineage.get('output_id') or row.get('source_output_id') or '').strip(),
            'parent_output_id': str(lineage.get('parent_output_id') or '').strip(),
        },
        'toolchain': row.get('toolchain') if isinstance(row.get('toolchain'), dict) else {
            'parse_format': str(data.get('parse_format') or ''),
            'model': str((data.get('settings') or {}).get('Model') or ''),
            'sampler': str((data.get('settings') or {}).get('Sampler') or ''),
        },
        'tags': list(row.get('tags') or []),
        'data': data,
    }
    return normalized


def build_generation_output_sidecar(*, base_sidecar: Dict[str, Any], job: Dict[str, Any], payload: Dict[str, Any], source_output: Dict[str, Any], candidate_path: str, relative_name: str, output_id: str, category: str, category_slug: str, mode_name: str, next_index: int) -> Dict[str, Any]:
    row = deepcopy(base_sidecar if isinstance(base_sidecar, dict) else {})
    row['schema_version'] = GENERATION_OUTPUT_SIDECAR_SCHEMA_VERSION
    row['kind'] = 'neo_studio_generation_output'
    row['record_type'] = 'generation_output'
    row['output_id'] = output_id
    row['job_id'] = str(job.get('job_id') or job.get('id') or '').strip()
    row['surface'] = 'generate'
    row['family'] = infer_generation_family(payload)
    row['media_type'] = 'image'
    row['status'] = 'saved'
    row['lineage'] = {
        'job_id': str(job.get('job_id') or job.get('id') or '').strip(),
        'parent_job_id': str(((job.get('lineage') or {}) if isinstance(job.get('lineage'), dict) else {}).get('parent_job_id') or '').strip(),
        'retry_of_job_id': str(((job.get('lineage') or {}) if isinstance(job.get('lineage'), dict) else {}).get('retry_of_job_id') or '').strip(),
        'source_output_id': str(((job.get('lineage') or {}) if isinstance(job.get('lineage'), dict) else {}).get('source_output_id') or '').strip(),
    }
    row['toolchain'] = {
        'backend_type': str(job.get('backend_type') or ''),
        'backend_name': str(job.get('backend_name') or ''),
        'checkpoint': str(payload.get('checkpoint') or ''),
        'sampler': str(payload.get('sampler') or ''),
        'scheduler': str(payload.get('scheduler') or ''),
        'vae': str(payload.get('vae') or ''),
    }
    row['save'].update({
        'relative_name': relative_name,
        'path': candidate_path,
        'filename': Path(candidate_path).name,
        'index': next_index,
        'category': category,
        'category_slug': category_slug,
        'mode_folder': mode_name,
    })
    row.setdefault('source_output', source_output)
    return row
