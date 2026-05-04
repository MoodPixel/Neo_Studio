from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..contracts.roleplay_v2_records import ROLEPLAY_V2_ENTITY_KINDS, ROLEPLAY_V2_RECORD_TYPES
from ..contracts.roleplay_v2_package_records import ROLEPLAY_V2_PACKAGE_EXTENSIONS

SUPPORTED_TEXT_SUFFIXES = {'.json', '.txt', '.md'}
SUPPORTED_PACKAGE_SUFFIXES = set(ROLEPLAY_V2_PACKAGE_EXTENSIONS.values())
SUPPORTED_UPLOAD_SUFFIXES = SUPPORTED_TEXT_SUFFIXES | SUPPORTED_PACKAGE_SUFFIXES | {'.zip'}


def clean_text(value: Any, *, limit: int = 0) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if limit > 0:
        text = text[:limit]
    return text



def infer_source_format(source_name: str = '', source_text: str = '') -> str:
    suffix = Path(str(source_name or '').strip()).suffix.lower()
    if suffix in SUPPORTED_PACKAGE_SUFFIXES or suffix == '.zip':
        return 'package'
    if suffix == '.json':
        return 'json'
    if suffix == '.md':
        return 'markdown'
    if suffix == '.txt':
        return 'text'
    text = clean_text(source_text)
    if not text:
        return 'unknown'
    if text.startswith('{') or text.startswith('['):
        return 'json'
    if text.startswith('#') or '\n#' in text or '```' in text:
        return 'markdown'
    return 'text'



def parse_json_maybe(source_text: str) -> tuple[Any | None, str]:
    text = clean_text(source_text)
    if not text:
        return None, 'empty'
    try:
        return json.loads(text), 'valid_json'
    except Exception:
        fenced = re.search(r'```(?:json)?\s*(\{.*\}|\[.*\])\s*```', text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                return json.loads(fenced.group(1)), 'valid_fenced_json'
            except Exception:
                return None, 'invalid_json'
        return None, 'invalid_json'



def infer_kind(target_kind: str = '', parsed_payload: Any = None, fallback_text: str = '') -> str:
    clean_target = str(target_kind or '').strip().lower()
    if clean_target in ROLEPLAY_V2_ENTITY_KINDS:
        return clean_target
    if isinstance(parsed_payload, dict):
        for key in ('kind', 'entity_kind'):
            value = str(parsed_payload.get(key) or '').strip().lower()
            if value in ROLEPLAY_V2_ENTITY_KINDS:
                return value
        record_type = str(parsed_payload.get('record_type') or '').strip().lower()
        if record_type == 'novel_project':
            return 'novel_project'
    text = clean_text(fallback_text, limit=400).lower()
    hint_map = {
        'character': ['character', 'protagonist', 'hero', 'villain', 'oc'],
        'world': ['world', 'setting', 'realm'],
        'universe': ['universe', 'cosmos', 'multiverse'],
        'scenario': ['scenario', 'scene', 'premise'],
        'organization': ['organization', 'faction', 'guild', 'cult'],
        'location': ['location', 'place', 'room'],
        'artifact': ['artifact', 'relic', 'weapon', 'item'],
        'ritual': ['ritual', 'spell', 'ceremony'],
        'creature': ['creature', 'monster', 'beast'],
    }
    for kind, needles in hint_map.items():
        if any(needle in text for needle in needles):
            return kind
    return clean_target



def validate_intake_payload(*, intake_mode: str, source_name: str, source_text: str, target_kind: str, parsed_payload: Any = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    info: list[str] = []
    clean_mode = str(intake_mode or '').strip().lower() or 'helper_assisted'
    source_format = infer_source_format(source_name, source_text)
    kind = infer_kind(target_kind, parsed_payload, source_text)
    clean_text_value = clean_text(source_text)
    if not clean_text_value and source_format != 'package':
        errors.append('Source text is empty.')
    if source_format == 'package' and clean_mode != 'package_import':
        warnings.append('Source looks like a package file but intake mode is not package_import.')
    if clean_mode == 'package_import':
        if source_format != 'package':
            warnings.append('Package import mode is selected, but the source does not look like a package yet.')
            info.append('Phase 3 will expand package restore beyond manifest-level validation.')
        else:
            info.append('Package import is accepted at preview level in Phase 2; full restore arrives in Phase 3.')
    if clean_mode == 'direct_import':
        if parsed_payload is None:
            errors.append('Direct import expects valid JSON or structured payload.')
        elif isinstance(parsed_payload, dict):
            record_type = str(parsed_payload.get('record_type') or '').strip().lower()
            if record_type and record_type not in ROLEPLAY_V2_RECORD_TYPES:
                warnings.append(f'Unknown record_type: {record_type}. It will be treated as generic structured input for now.')
        elif isinstance(parsed_payload, list):
            info.append(f'Structured list detected with {len(parsed_payload)} item(s).')
        else:
            warnings.append('Structured payload parsed, but it is not a dict or list.')
    if clean_mode == 'helper_assisted' and len(clean_text_value) < 20:
        warnings.append('Source text is very short. Helper output will likely be thin.')
    if kind and kind not in ROLEPLAY_V2_ENTITY_KINDS:
        warnings.append(f'Kind {kind} is not yet a registered entity kind in Roleplay V2.')
    return {
        'kind': kind,
        'source_format': source_format,
        'warnings': warnings,
        'errors': errors,
        'info': info,
        'validation_state': 'invalid' if errors else 'valid_with_warnings' if warnings else 'valid',
    }



def summarize_source(*, source_name: str, source_text: str, parsed_payload: Any = None) -> dict[str, Any]:
    text = clean_text(source_text)
    return {
        'source_name': clean_text(source_name, limit=200),
        'char_count': len(text),
        'line_count': len(text.splitlines()) if text else 0,
        'has_structured_payload': parsed_payload is not None,
        'structured_type': type(parsed_payload).__name__ if parsed_payload is not None else '',
        'record_count': len(parsed_payload) if isinstance(parsed_payload, list) else 1 if isinstance(parsed_payload, dict) else 0,
    }
