from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from PIL import ExifTags, Image

from ..contracts.output_records import build_output_metadata_record, normalize_output_metadata_record
from .characters import save_character_record
from .library_common import new_id, read_json_dict, safe_name, sha256_file
from .library_settings_store import get_library_root
from .library_storage import iter_records
from .shared_data_paths import library_data_path
from .library_prompts import save_prompt

_A1111_NEG_MARKER = '\nNegative prompt:'
_A1111_SETTINGS_MARKER = '\nSteps:'
_LORA_RE = re.compile(r'<lora:([^:>]+):([0-9.\-]+)>', re.IGNORECASE)
_TI_RE = re.compile(r'<(?:emb|embedding):([^:>]+):?([^>]*)>', re.IGNORECASE)
_KEYVAL_RE = re.compile(r'\s*([^:,]+):\s*(.+?)\s*$')
_MULTISPACE_RE = re.compile(r'\s{2,}')


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _image_for_bytes(content: bytes) -> Image.Image:
    bio = BytesIO(content)
    return Image.open(bio)


def _to_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        for enc in ('utf-8', 'utf-16', 'latin-1'):
            try:
                return value.decode(enc, errors='ignore').strip('\x00').strip()
            except Exception:
                continue
        return ''
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return ''
    return str(value).strip()


def _extract_exif_strings(img: Image.Image) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        exif = img.getexif()
    except Exception:
        exif = None
    if not exif:
        return out
    for key, value in exif.items():
        name = ExifTags.TAGS.get(key, str(key))
        text = _to_text(value)
        if text:
            out[name] = text
    return out


def _collect_metadata_strings(img: Image.Image) -> Dict[str, str]:
    collected: Dict[str, str] = {}
    for key, value in (getattr(img, 'info', {}) or {}).items():
        text = _to_text(value)
        if text:
            collected[str(key)] = text
    for key, value in _extract_exif_strings(img).items():
        collected.setdefault(key, value)
    return collected


def _pick_raw_parameters(collected: Dict[str, str]) -> str:
    priority = [
        'parameters', 'Parameters', 'prompt', 'Prompt', 'comment', 'Comment',
        'description', 'Description', 'UserComment', 'workflow', 'prompt_json',
    ]
    for key in priority:
        value = collected.get(key)
        if value:
            return value
    if len(collected) == 1:
        return next(iter(collected.values()))
    for value in collected.values():
        if 'Negative prompt:' in value or 'Steps:' in value or '<lora:' in value:
            return value
    return ''


def _parse_settings_text(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not text:
        return out
    parts = [p.strip() for p in text.split(',') if p.strip()]
    buffer = ''
    for part in parts:
        candidate = part if not buffer else f'{buffer}, {part}'
        match = _KEYVAL_RE.match(candidate)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            out[key] = value
            buffer = ''
        else:
            buffer = candidate
    if buffer and ':' in buffer:
        key, value = buffer.split(':', 1)
        out[key.strip()] = value.strip()
    return out


def extract_lora_tokens(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for match in _LORA_RE.finditer(text or ''):
        raw_name = match.group(1).strip()
        raw_weight = match.group(2).strip()
        try:
            weight = float(raw_weight)
        except Exception:
            weight = raw_weight
        out.append({'name': raw_name, 'weight': weight, 'token': match.group(0), 'kind': 'lora'})
    return out


def extract_ti_tokens(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for match in _TI_RE.finditer(text or ''):
        raw_name = match.group(1).strip()
        raw_weight = (match.group(2) or '').strip()
        try:
            weight = float(raw_weight) if raw_weight else ''
        except Exception:
            weight = raw_weight
        out.append({'name': raw_name, 'weight': weight, 'token': match.group(0), 'kind': 'ti'})
    return out


def _load_lora_registry() -> List[Dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    vault_db_path = library_data_path('vault_db.json', legacy_rel='vault_db.json', default_json={'tags': [], 'packs': [], 'mapsets': [], 'loras': []})
    data = read_json_dict(vault_db_path)
    rows = data.get('loras') or []
    return [row for row in rows if isinstance(row, dict)]


def match_loras_to_registry(found: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    registry = _load_lora_registry()
    matched: List[Dict[str, Any]] = []
    for item in found:
        name = str(item.get('name') or '').strip()
        key = name.lower()
        reg = next((row for row in registry if str(row.get('name') or '').strip().lower() == key or str(row.get('rel') or '').strip().lower() == key), None)
        merged = dict(item)
        if reg:
            merged['matched'] = True
            merged['registry_name'] = reg.get('name') or name
            merged['registry_category'] = reg.get('category') or ''
            merged['default_strength'] = reg.get('default_strength')
            merged['triggers'] = reg.get('triggers') or []
            merged['keywords'] = reg.get('keywords') or []
            merged['notes'] = reg.get('notes') or ''
            merged['file'] = reg.get('file') or ''
        else:
            merged['matched'] = False
        matched.append(merged)
    return matched


def parse_a1111_parameters(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or '').strip()
    positive = ''
    negative = ''
    settings: Dict[str, str] = {}
    if not text:
        return {'positive_prompt': '', 'negative_prompt': '', 'settings': {}, 'format': 'empty'}
    if _A1111_NEG_MARKER in text or _A1111_SETTINGS_MARKER in text:
        if _A1111_NEG_MARKER in text:
            positive, rest = text.split(_A1111_NEG_MARKER, 1)
            if _A1111_SETTINGS_MARKER in rest:
                negative, settings_text = rest.split(_A1111_SETTINGS_MARKER, 1)
                settings = _parse_settings_text('Steps:' + settings_text)
            else:
                negative = rest
        elif _A1111_SETTINGS_MARKER in text:
            positive, settings_text = text.split(_A1111_SETTINGS_MARKER, 1)
            settings = _parse_settings_text('Steps:' + settings_text)
        return {
            'positive_prompt': positive.strip(),
            'negative_prompt': negative.strip(),
            'settings': settings,
            'format': 'a1111',
        }
    if text.startswith('{') and text.endswith('}'):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                positive = _to_text(payload.get('prompt') or payload.get('positive_prompt') or payload.get('positive'))
                negative = _to_text(payload.get('negative_prompt') or payload.get('negative'))
                settings = {str(k): _to_text(v) for k, v in payload.items() if k not in {'prompt', 'positive_prompt', 'positive', 'negative_prompt', 'negative', 'workflow'}}
                return {
                    'positive_prompt': positive,
                    'negative_prompt': negative,
                    'settings': settings,
                    'format': 'json',
                }
        except Exception:
            pass
    return {'positive_prompt': text, 'negative_prompt': '', 'settings': {}, 'format': 'plain'}


def clean_rebuild_prompt(parsed: Dict[str, Any]) -> str:
    positive = str(parsed.get('positive_prompt') or '').strip()
    if not positive:
        return ''
    parts = [p.strip() for p in positive.replace('\n', ',').split(',') if p.strip()]
    seen = set()
    cleaned: List[str] = []
    for part in parts:
        norm = _MULTISPACE_RE.sub(' ', part).lower()
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(_MULTISPACE_RE.sub(' ', part))
    if cleaned:
        return ', '.join(cleaned)
    return positive


def parse_output_metadata_bytes(content: bytes, filename: str = 'output.png') -> Dict[str, Any]:
    img = _image_for_bytes(content)
    collected = _collect_metadata_strings(img)
    raw_parameters = _pick_raw_parameters(collected)
    parsed = parse_a1111_parameters(raw_parameters)
    positive_prompt = str(parsed.get('positive_prompt') or '').strip()
    negative_prompt = str(parsed.get('negative_prompt') or '').strip()
    settings = parsed.get('settings') or {}
    raw_text = raw_parameters or '\n\n'.join(f'{k}: {v}' for k, v in collected.items())
    loras = extract_lora_tokens(positive_prompt + '\n' + negative_prompt)
    tis = extract_ti_tokens(positive_prompt + '\n' + negative_prompt)
    matched_loras = match_loras_to_registry(loras)
    summary_lines = []
    for key in ('Steps', 'Sampler', 'CFG scale', 'Seed', 'Size', 'Model', 'VAE', 'Denoising strength'):
        if key in settings:
            summary_lines.append(f'{key}: {settings[key]}')
    return {
        'schema_version': 1,
        'kind': 'output_metadata',
        'source_filename': Path(filename).name,
        'image_format': getattr(img, 'format', '') or '',
        'size': {'width': img.width, 'height': img.height},
        'positive_prompt': positive_prompt,
        'negative_prompt': negative_prompt,
        'settings': settings,
        'settings_summary': ' · '.join(summary_lines),
        'metadata_fields': collected,
        'raw_metadata': raw_text,
        'parse_format': parsed.get('format') or 'plain',
        'loras': matched_loras,
        'textual_inversions': tis,
        'clean_rebuild_prompt': clean_rebuild_prompt({'positive_prompt': positive_prompt}),
    }


def compare_output_metadata(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    p_settings = primary.get('settings') or {}
    s_settings = secondary.get('settings') or {}
    keys = sorted(set(p_settings.keys()) | set(s_settings.keys()), key=str.lower)
    settings_diff = []
    for key in keys:
        pv = str(p_settings.get(key) or '')
        sv = str(s_settings.get(key) or '')
        if pv != sv:
            settings_diff.append({'key': key, 'primary': pv, 'secondary': sv})
    p_loras = {str(x.get('name') or '').lower(): x for x in (primary.get('loras') or [])}
    s_loras = {str(x.get('name') or '').lower(): x for x in (secondary.get('loras') or [])}
    only_primary = [x['name'] for key, x in p_loras.items() if key not in s_loras]
    only_secondary = [x['name'] for key, x in s_loras.items() if key not in p_loras]
    common = []
    for key in sorted(set(p_loras) & set(s_loras)):
        pw = p_loras[key].get('weight')
        sw = s_loras[key].get('weight')
        if pw != sw:
            common.append({'name': p_loras[key].get('name') or s_loras[key].get('name') or key, 'primary_weight': pw, 'secondary_weight': sw})
    return {
        'positive_changed': str(primary.get('positive_prompt') or '') != str(secondary.get('positive_prompt') or ''),
        'negative_changed': str(primary.get('negative_prompt') or '') != str(secondary.get('negative_prompt') or ''),
        'settings_diff': settings_diff,
        'loras_only_primary': only_primary,
        'loras_only_secondary': only_secondary,
        'lora_weight_diff': common,
    }



def save_output_metadata_record(name: str, parsed: Dict[str, Any], source_filename: str = '', notes: str = '', source_job_id: str = '', source_output_id: str = '', parent_output_id: str = '') -> Dict[str, Any]:
    root = get_library_root()
    record_id = new_id('meta')
    final_name = safe_name(name or Path(source_filename or 'output').stem)
    record = build_output_metadata_record(
        record_id=record_id,
        name=final_name,
        parsed=parsed,
        source_filename=source_filename,
        notes=notes,
        source_job_id=source_job_id,
        source_output_id=source_output_id,
        parent_output_id=parent_output_id,
    )
    fp = root / 'output_metadata' / f'{record_id}.json'
    atomic_write_json(fp, record)
    return record



def iter_output_metadata_records() -> List[Dict[str, Any]]:
    root = get_library_root()
    out: List[Dict[str, Any]] = []
    for fp in sorted((root / 'output_metadata').glob('*.json')):
        try:
            data = read_json_object(fp, None)
            if isinstance(data, dict):
                normalized = normalize_output_metadata_record(data)
                normalized['_record_path'] = str(fp)
                out.append(normalized)
        except Exception:
            continue
    return out


def save_metadata_as_prompt(name: str, category: str, parsed: Dict[str, Any], model: str = '', notes: str = '') -> Dict[str, Any]:
    positive = str(parsed.get('positive_prompt') or '').strip()
    negative = str(parsed.get('negative_prompt') or '').strip()
    prompt_text = positive
    notes_parts = [part for part in [notes.strip() if notes else '', f'Negative prompt: {negative}' if negative else '', parsed.get('settings_summary') or ''] if part]
    record = save_prompt(
        name=name,
        category=category,
        prompt=prompt_text,
        model=model or str((parsed.get('settings') or {}).get('Model') or ''),
        notes='\n'.join(notes_parts),
        raw_prompt=str(parsed.get('raw_metadata') or positive),
        preset_name='Output Metadata',
        style='Imported Metadata',
        finish_reason='metadata_import',
        settings={
            'negative_prompt': negative,
            'metadata_settings': parsed.get('settings') or {},
            'loras': parsed.get('loras') or [],
        },
        generation_mode='metadata_import',
    )
    save_output_metadata_record(name=name, parsed=parsed, source_filename=str(parsed.get('source_filename') or ''), notes=notes, source_job_id=str(parsed.get('source_job_id') or ''), source_output_id=str(parsed.get('source_output_id') or ''), parent_output_id=str((parsed.get('lineage') or {}).get('parent_output_id') or ''))
    return record


def save_metadata_as_character(name: str, parsed: Dict[str, Any], notes: str = '') -> Dict[str, Any]:
    positive = str(parsed.get('positive_prompt') or '').strip()
    settings_summary = str(parsed.get('settings_summary') or '').strip()
    content_parts = [positive]
    if settings_summary:
        content_parts.append(f'Generation context: {settings_summary}')
    if notes:
        content_parts.append(f'Notes: {notes.strip()}')
    character = save_character_record(name=name, content='\n\n'.join([part for part in content_parts if part]))
    save_output_metadata_record(name=name, parsed=parsed, source_filename=str(parsed.get('source_filename') or ''), notes=notes, source_job_id=str(parsed.get('source_job_id') or ''), source_output_id=str(parsed.get('source_output_id') or ''), parent_output_id=str((parsed.get('lineage') or {}).get('parent_output_id') or ''))
    return character



def get_output_metadata_record(record_id: str = '') -> Dict[str, Any] | None:
    target = (record_id or '').strip()
    if not target:
        return None
    for rec in iter_output_metadata_records():
        if str(rec.get('id') or '').strip() == target:
            return normalize_output_metadata_record(rec)
    return None
