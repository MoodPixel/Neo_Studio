from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts.roleplay_v2_intake_records import build_creator_draft_record, build_helper_output_record
from .roleplay_v2_foundation import ROLEPLAY_V2_CREATOR_DRAFTS_DIR, ROLEPLAY_V2_HELPER_OUTPUTS_DIR
from .roleplay_v2_preview_store import write_intake_preview, read_intake_preview
from .roleplay_v2_validation import clean_text, infer_source_format, infer_kind, parse_json_maybe, summarize_source, validate_intake_payload
from .storage_io import atomic_write_json, read_json_object


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _draft_path(draft_id: str) -> Path:
    return ROLEPLAY_V2_CREATOR_DRAFTS_DIR / f'{draft_id}.json'



def _helper_output_path(helper_output_id: str) -> Path:
    return ROLEPLAY_V2_HELPER_OUTPUTS_DIR / f'{helper_output_id}.json'



def _structured_payload_for_preview(*, intake_mode: str, parsed_payload: Any, kind: str, source_text: str, source_format: str) -> dict[str, Any]:
    if intake_mode == 'direct_import' and isinstance(parsed_payload, dict):
        return deepcopy(parsed_payload)
    if intake_mode == 'direct_import' and isinstance(parsed_payload, list):
        return {'items': deepcopy(parsed_payload), 'item_count': len(parsed_payload)}
    text = clean_text(source_text, limit=12000)
    summary = text.split('\n', 1)[0][:240] if text else ''
    return {
        'kind': kind,
        'source_format': source_format,
        'raw_summary': summary,
        'raw_excerpt': text[:1500],
    }



def _build_helper_output(*, draft_id: str, kind: str, source_text: str, structured_payload: dict[str, Any], warnings: list[str], validation_state: str) -> dict[str, Any]:
    return build_helper_output_record(
        draft_id=draft_id,
        kind=kind,
        cleaned_text=clean_text(source_text, limit=200000),
        structured_payload=structured_payload,
        warnings=warnings,
        meta={
            'status': 'draft',
            'approved': False,
            'notes': f'preview_validation_state:{validation_state}',
        },
    )



def preview_creator_input(*, intake_mode: str, helper_mode: str = 'structure_only', target_kind: str = '', source_name: str = '', source_text: str = '', target_id: str = '') -> dict[str, Any]:
    source_format = infer_source_format(source_name, source_text)
    parsed_payload, parse_state = parse_json_maybe(source_text) if source_format == 'json' else (None, 'not_json')
    detected_kind = infer_kind(target_kind, parsed_payload, source_text)
    validation = validate_intake_payload(
        intake_mode=intake_mode,
        source_name=source_name,
        source_text=source_text,
        target_kind=detected_kind,
        parsed_payload=parsed_payload,
    )
    structured_payload = _structured_payload_for_preview(
        intake_mode=intake_mode,
        parsed_payload=parsed_payload,
        kind=detected_kind,
        source_text=source_text,
        source_format=source_format,
    )
    draft = build_creator_draft_record(
        kind=detected_kind or target_kind,
        intake_mode=intake_mode,
        helper_mode=helper_mode,
        source_name=source_name,
        source_text=source_text,
        target_id=target_id,
        parsed_payload=structured_payload,
        meta={'validation_state': validation['validation_state']},
    )
    helper_output = _build_helper_output(
        draft_id=draft['id'],
        kind=detected_kind or target_kind,
        source_text=source_text,
        structured_payload=structured_payload,
        warnings=validation['warnings'],
        validation_state=validation['validation_state'],
    )
    preview_id = f'intake_preview_{uuid4().hex[:10]}'
    payload = {
        'preview_id': preview_id,
        'record_type': 'roleplay_v2_intake_preview',
        'created_at': _now_iso(),
        'intake_mode': str(intake_mode or '').strip().lower() or 'helper_assisted',
        'helper_mode': str(helper_mode or '').strip().lower() or 'structure_only',
        'target_kind': str(target_kind or '').strip().lower(),
        'detected_kind': detected_kind,
        'source_format': source_format,
        'parse_state': parse_state,
        'summary': summarize_source(source_name=source_name, source_text=source_text, parsed_payload=parsed_payload),
        'validation': validation,
        'draft_record': draft,
        'helper_output': helper_output,
        'next_actions': [
            'review_preview',
            'save_draft',
            'compile_to_canon_later_phase',
        ],
    }
    write_intake_preview(payload)
    return payload



def save_preview_as_draft(preview_id: str, *, approved: bool = False) -> dict[str, Any]:
    preview = read_intake_preview(preview_id)
    draft = deepcopy(preview.get('draft_record') or {})
    helper_output = deepcopy(preview.get('helper_output') or {})
    if not draft or not helper_output:
        raise ValueError('Preview is missing draft data.')
    draft_meta = draft.get('meta') if isinstance(draft.get('meta'), dict) else {}
    draft_meta['status'] = 'approved_draft' if approved else 'draft'
    draft_meta['updated_at'] = _now_iso()
    draft['meta'] = draft_meta
    helper_meta = helper_output.get('meta') if isinstance(helper_output.get('meta'), dict) else {}
    helper_meta['status'] = 'approved_draft' if approved else 'draft'
    helper_meta['approved'] = bool(approved)
    helper_meta['updated_at'] = _now_iso()
    helper_output['meta'] = helper_meta
    ROLEPLAY_V2_CREATOR_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_HELPER_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_draft_path(str(draft.get('id') or '')), draft)
    atomic_write_json(_helper_output_path(str(helper_output.get('id') or '')), helper_output)
    return {
        'ok': True,
        'preview_id': preview_id,
        'draft_id': draft.get('id', ''),
        'helper_output_id': helper_output.get('id', ''),
        'approved': bool(approved),
        'draft_record': draft,
        'helper_output': helper_output,
    }



def get_saved_draft(draft_id: str) -> dict[str, Any] | None:
    return read_json_object(_draft_path(draft_id), None)
