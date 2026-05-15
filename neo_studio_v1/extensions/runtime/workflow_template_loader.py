from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any


class ExternalWorkflowTemplateError(ValueError):
    """Raised when an external workflow template cannot be safely loaded."""


def _safe_relative_path(value: Any) -> str:
    text = str(value or '').strip().replace('\\', '/')
    if not text or text.startswith('/'):
        return ''
    path = PurePosixPath(text)
    if '..' in path.parts:
        return ''
    return path.as_posix()


def extension_base_dir(extension_record: dict[str, Any] | None) -> Path | None:
    if not isinstance(extension_record, dict):
        return None
    raw = str(extension_record.get('extension_dir') or '').strip()
    if not raw:
        return None
    try:
        return Path(raw).resolve()
    except Exception:
        return None


def resolve_extension_template_path(extension_record: dict[str, Any], template: str) -> Path:
    safe_template = _safe_relative_path(template)
    if not safe_template:
        raise ExternalWorkflowTemplateError('Workflow patch template must be a safe extension-relative path.')
    base_dir = extension_base_dir(extension_record)
    if not base_dir:
        raise ExternalWorkflowTemplateError('Extension directory is unavailable; cannot load workflow template.')
    candidate = (base_dir / safe_template).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ExternalWorkflowTemplateError('Workflow template path escapes the extension directory.') from exc
    if not candidate.exists() or not candidate.is_file():
        raise ExternalWorkflowTemplateError(f'Workflow template is missing: {safe_template}')
    if candidate.suffix.lower() != '.json':
        raise ExternalWorkflowTemplateError('Workflow templates must be JSON files.')
    return candidate


def load_extension_workflow_template(extension_record: dict[str, Any], template: str) -> dict[str, Any]:
    path = resolve_extension_template_path(extension_record, template)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise ExternalWorkflowTemplateError(f'Could not read workflow template {path.name}: {exc}') from exc
    if not isinstance(data, dict):
        raise ExternalWorkflowTemplateError('Workflow template JSON must be an object.')
    return deepcopy(data)
