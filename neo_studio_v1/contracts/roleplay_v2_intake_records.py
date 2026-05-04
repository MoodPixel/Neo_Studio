from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

ROLEPLAY_V2_INTAKE_SCHEMA_VERSION = 1
ROLEPLAY_V2_INTAKE_MODES = {'helper_assisted', 'direct_import', 'package_import'}
ROLEPLAY_V2_HELPER_MODES = {'clean_only', 'structure_only', 'fill_gaps_carefully', 'creative_expansion'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _clean(value: Any, *, lower: bool = False, limit: int = 0) -> str:
    text = str(value or '').strip()
    if lower:
        text = text.lower()
    if limit > 0:
        text = text[:limit]
    return text



def _json_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}



def _clean_list(values: Any, *, limit: int = 0) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = _clean(item, limit=limit)
        if text:
            out.append(text)
    return out



def build_creator_draft_record(*, kind: str, intake_mode: str = 'helper_assisted', helper_mode: str = 'structure_only', draft_id: str = '', source_name: str = '', source_text: str = '', source_path: str = '', target_id: str = '', parsed_payload: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_intake = _clean(intake_mode, lower=True) or 'helper_assisted'
    if clean_intake not in ROLEPLAY_V2_INTAKE_MODES:
        raise ValueError('Unsupported roleplay V2 intake mode.')
    clean_helper = _clean(helper_mode, lower=True) or 'structure_only'
    if clean_helper not in ROLEPLAY_V2_HELPER_MODES:
        raise ValueError('Unsupported roleplay V2 helper mode.')
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_INTAKE_SCHEMA_VERSION,
        'record_type': 'creator_draft',
        'id': _clean(draft_id) or f'draft_{uuid4().hex[:10]}',
        'kind': _clean(kind, lower=True),
        'intake_mode': clean_intake,
        'helper_mode': clean_helper,
        'source_name': _clean(source_name, limit=200),
        'source_text': _clean(source_text, limit=200000),
        'source_path': _clean(source_path, limit=500),
        'target_id': _clean(target_id, limit=120),
        'parsed_payload': _json_dict(parsed_payload),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'draft', lower=True),
            'validation_state': _clean(meta_row.get('validation_state') or 'pending', lower=True),
            'notes': _clean(meta_row.get('notes'), limit=4000),
        },
    }



def build_helper_output_record(*, draft_id: str, kind: str, helper_output_id: str = '', cleaned_text: str = '', structured_payload: dict[str, Any] | None = None, warnings: list[str] | None = None, contradictions: list[str] | None = None, inferred_fields: list[str] | None = None, source_refs: list[str] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    meta_row = _json_dict(meta)
    return {
        'schema_version': ROLEPLAY_V2_INTAKE_SCHEMA_VERSION,
        'record_type': 'helper_output',
        'id': _clean(helper_output_id) or f'helper_{uuid4().hex[:10]}',
        'draft_id': _clean(draft_id, limit=120),
        'kind': _clean(kind, lower=True),
        'cleaned_text': _clean(cleaned_text, limit=200000),
        'structured_payload': _json_dict(structured_payload),
        'warnings': _clean_list(warnings or [], limit=300),
        'contradictions': _clean_list(contradictions or [], limit=300),
        'inferred_fields': _clean_list(inferred_fields or [], limit=120),
        'source_refs': _clean_list(source_refs or [], limit=240),
        'meta': {
            'created_at': _clean(meta_row.get('created_at')) or now,
            'updated_at': _clean(meta_row.get('updated_at')) or now,
            'status': _clean(meta_row.get('status') or 'draft', lower=True),
            'approved': bool(meta_row.get('approved', False)),
            'notes': _clean(meta_row.get('notes'), limit=4000),
        },
    }
