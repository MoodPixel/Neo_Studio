from __future__ import annotations

from copy import deepcopy
from typing import Any

_STAGE4_VERSION = 'image-output-selection-v1'
_PREVIEW_COMMANDS = {'preview_action', 'preview_upscale', 'preview_adetailer'}


def _clean_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        try:
            return deepcopy(value)
        except Exception:
            return dict(value)
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ''


def is_preview_command(command_type: Any) -> bool:
    return str(command_type or '').strip().lower() in _PREVIEW_COMMANDS


def resolve_locked_output_source(envelope: dict[str, Any] | None, legacy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve the Stage 4 explicit source-selection contract.

    This does not open files or mutate output lineage. It only decides whether a
    preview command has an explicitly selected source, instead of silently
    falling back to the most recent output/job.
    """
    envelope = _clean_dict(envelope)
    legacy = _clean_dict(legacy_payload or envelope.get('legacy_payload') or envelope.get('settings'))
    source = _clean_dict(envelope.get('source'))
    image_state = _clean_dict(envelope.get('image_state'))
    state_source = _clean_dict(image_state.get('source'))
    preview_action = _clean_dict(envelope.get('preview_action') or legacy.get('preview_action'))
    target = _clean_dict(preview_action.get('target') or source.get('preview_action_target') or legacy.get('generationPreviewActionTarget'))
    selected_snapshot = _clean_dict(source.get('selected_output_snapshot') or state_source.get('selected_output_snapshot') or legacy.get('generationSelectedOutputSnapshot'))

    explicit_source_type = _first_text(source.get('explicit_source_type'), source.get('source_type'), preview_action.get('source_type'))
    active_source_image = _first_text(source.get('active_source_image'), state_source.get('active_source_image'), legacy.get('source_image_name'))
    source_image_name = _first_text(legacy.get('source_image_name'), active_source_image)
    output_id = _first_text(source.get('selected_output_id'), state_source.get('selected_output_id'), target.get('output_id'), selected_snapshot.get('output_id'), selected_snapshot.get('id'))
    job_id = _first_text(source.get('selected_job_id'), state_source.get('selected_job_id'), target.get('job_id'), selected_snapshot.get('job_id'))
    filename = _first_text(target.get('filename'), target.get('name'), selected_snapshot.get('filename'), selected_snapshot.get('name'), selected_snapshot.get('image'), selected_snapshot.get('path'))

    has_explicit = bool(source_image_name or active_source_image or output_id or filename or target or selected_snapshot)
    selection = {
        'version': _STAGE4_VERSION,
        'locked': has_explicit,
        'source_type': explicit_source_type or ('selected_output' if (output_id or filename or target or selected_snapshot) else ('uploaded_source' if active_source_image else 'none')),
        'source_image_name': source_image_name,
        'active_source_image': active_source_image,
        'selected_output_id': output_id,
        'selected_job_id': job_id,
        'filename': filename,
        'target': target,
        'selected_output_snapshot': selected_snapshot,
        'reason': 'explicit_source_resolved' if has_explicit else 'missing_explicit_source',
    }
    return selection


def stamp_output_selection_contract(payload: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    command = str(payload.get('_neo_image_command_type') or (envelope or {}).get('command_type') or '').strip().lower()
    selection = resolve_locked_output_source(envelope or {}, payload)
    payload['_neo_output_selection_contract'] = selection
    payload['_neo_output_selection_contract_version'] = _STAGE4_VERSION
    if selection.get('locked'):
        payload['_neo_source_selection_locked'] = True
        if selection.get('selected_output_id') and not payload.get('selected_output_id'):
            payload['selected_output_id'] = selection.get('selected_output_id')
        if selection.get('selected_job_id') and not payload.get('selected_job_id'):
            payload['selected_job_id'] = selection.get('selected_job_id')
    elif is_preview_command(command):
        payload['_neo_source_selection_locked'] = False
        payload['_neo_source_selection_missing'] = True
    return payload


def require_preview_source_lock(payload: dict[str, Any], *, has_source_upload: bool = False) -> None:
    if not isinstance(payload, dict):
        return
    command = str(payload.get('_neo_image_command_type') or '').strip().lower()
    if not is_preview_command(command):
        return
    if has_source_upload:
        payload['_neo_source_selection_locked'] = True
        return
    selection = _clean_dict(payload.get('_neo_output_selection_contract'))
    if selection.get('locked') or payload.get('source_image_name') or payload.get('generationPreviewActionTarget') or payload.get('generationSelectedOutputSnapshot'):
        payload['_neo_source_selection_locked'] = True
        return
    label = command.replace('_', ' ')
    raise ValueError(f'{label} needs an explicit selected output or uploaded source image. Select the exact result to use, then run the preview action again.')
