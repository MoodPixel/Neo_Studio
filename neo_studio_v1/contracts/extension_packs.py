from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or '').strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def normalize_extension_pack(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    extension_id = str(raw.get('extension_id') or '').strip()
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'extension_pack',
        'extension_id': extension_id,
        'title': str(raw.get('title') or extension_id).strip(),
        'description': str(raw.get('description') or '').strip(),
        'author': str(raw.get('author') or '').strip(),
        'mount_type': str(raw.get('mount_type') or '').strip().lower(),
        'permissions': _string_list(raw.get('permissions') or []),
        'surface': str(raw.get('surface') or raw.get('target_surface') or '').strip().lower(),
        'target_surface': str(raw.get('target_surface') or raw.get('surface') or '').strip().lower(),
        'target_tab': str(raw.get('target_tab') or raw.get('workspace') or raw.get('target_subtab') or '').strip().lower(),
        'target_subtab': str(raw.get('target_subtab') or raw.get('workspace') or raw.get('target_tab') or '').strip().lower(),
        'workspace': str(raw.get('workspace') or raw.get('target_subtab') or raw.get('target_tab') or '').strip().lower(),
        'families': _string_list(raw.get('families') or raw.get('allowed_families') or []),
        'allowed_families': _string_list(raw.get('allowed_families') or raw.get('families') or []),
        'blocked_families': _string_list(raw.get('blocked_families') or raw.get('disabled_families') or []),
        'disabled_families': _string_list(raw.get('disabled_families') or raw.get('blocked_families') or []),
        'requires_backends': _string_list(raw.get('requires_backends') or []),
        'requires_nodes': _string_list(raw.get('requires_nodes') or raw.get('required_nodes') or []),
        'required_nodes': _string_list(raw.get('required_nodes') or raw.get('requires_nodes') or []),
        'injects_sections': _string_list(raw.get('injects_sections') or []),
        'injects_actions': _string_list(raw.get('injects_actions') or []),
        'injects_guides': _string_list(raw.get('injects_guides') or []),
        'ui_entry': str(raw.get('ui_entry') or raw.get('entry_js') or '').strip(),
        'entry_css': str(raw.get('entry_css') or '').strip(),
        'backend_routes': str(raw.get('backend_routes') or '').strip(),
        'adapter': str(raw.get('adapter') or raw.get('adapter_path') or '').strip(),
        'adapter_path': str(raw.get('adapter_path') or raw.get('adapter') or '').strip(),
        'manifest_path': str(raw.get('manifest_path') or '').strip(),
        'source': str(raw.get('source') or 'system').strip().lower(),
        'version': str(raw.get('version') or '1.0').strip(),
        'min_neo_version': str(raw.get('min_neo_version') or '').strip(),
        'max_neo_version': str(raw.get('max_neo_version') or '').strip(),
        'manifest_valid': bool(raw.get('manifest_valid', False)),
        'manifest_warnings': _string_list(raw.get('manifest_warnings') or []),
        'dev_only': bool(raw.get('dev_only', False)),
        'enabled': bool(raw.get('enabled', True)),
        'updated_at': str(raw.get('updated_at') or _now_iso()).strip(),
    }


def normalize_workflow_pack(record: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    raw = {**(record or {}), **overrides}
    workflow_id = str(raw.get('workflow_id') or '').strip()
    return {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'workflow_pack',
        'workflow_id': workflow_id,
        'title': str(raw.get('title') or workflow_id).strip(),
        'description': str(raw.get('description') or '').strip(),
        'extension_id': str(raw.get('extension_id') or raw.get('extension') or '').strip(),
        'surface': str(raw.get('surface') or raw.get('target_surface') or '').strip().lower(),
        'family': str(raw.get('family') or '').strip().lower(),
        'families': _string_list(raw.get('families') or raw.get('allowed_families') or ([] if not raw.get('family') else [raw.get('family')])),
        'allowed_families': _string_list(raw.get('allowed_families') or raw.get('families') or ([] if not raw.get('family') else [raw.get('family')])),
        'blocked_families': _string_list(raw.get('blocked_families') or raw.get('disabled_families') or []),
        'disabled_families': _string_list(raw.get('disabled_families') or raw.get('blocked_families') or []),
        'mode': str(raw.get('mode') or '').strip().lower(),
        'backend_role': str(raw.get('backend_role') or raw.get('backend') or '').strip().lower(),
        'target_surface': str(raw.get('target_surface') or raw.get('surface') or '').strip().lower(),
        'target_tab': str(raw.get('target_tab') or raw.get('workspace') or '').strip().lower(),
        'workflow_path': str(raw.get('workflow_path') or raw.get('path') or raw.get('file') or '').strip(),
        'workflow_file': str(raw.get('workflow_file') or '').strip(),
        'workflow_kind': str(raw.get('workflow_kind') or raw.get('kind') or 'workflow').strip().lower(),
        'imported_from': str(raw.get('imported_from') or '').strip(),
        'requires_nodes': _string_list(raw.get('requires_nodes') or raw.get('required_nodes') or []),
        'required_nodes': _string_list(raw.get('required_nodes') or raw.get('requires_nodes') or []),
        'optional_nodes': _string_list(raw.get('optional_nodes') or []),
        'requires_extensions': _string_list(raw.get('requires_extensions') or []),
        'sections': _string_list(raw.get('sections') or []),
        'host_tabs': _string_list(raw.get('host_tabs') or raw.get('sections') or []),
        'tags': _string_list(raw.get('tags') or []),
        'feature_key': str(raw.get('feature_key') or raw.get('workflow_id') or '').strip(),
        'payload_key': str(raw.get('payload_key') or '').strip(),
        'module_payload_key': str(raw.get('module_payload_key') or '').strip(),
        'ui_card': str(raw.get('ui_card') or '').strip(),
        'owner_module': str(raw.get('owner_module') or '').strip(),
        'staged': bool(raw.get('staged', False)),
        'dev_only': bool(raw.get('dev_only', False)),
        'enabled': bool(raw.get('enabled', True)),
        'source': str(raw.get('source') or 'system').strip().lower(),
        'version': str(raw.get('version') or '1.0').strip(),
        'updated_at': str(raw.get('updated_at') or _now_iso()).strip(),
    }
