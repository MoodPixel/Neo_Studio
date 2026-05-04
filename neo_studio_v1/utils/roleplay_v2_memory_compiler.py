from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
import hashlib
import re

from ..contracts.roleplay_v2_memory_records import build_memory_fragment_record, build_shared_memory_record, build_relationship_record
from .roleplay_v2_canon_compiler import get_canon_record
from .roleplay_v2_package_store import load_saved_record, save_record
from .roleplay_v2_foundation import ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR, ROLEPLAY_V2_SHARED_MEMORIES_DIR
from .storage_io import atomic_write_json, read_json_object
from .roleplay_v2_sqlite_store import upsert_rp2_memory_outputs, fetch_rp2_sqlite_overview, sync_rp2_memory_to_chroma


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _memory_path(fragment_id: str):
    return ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR / f'{str(fragment_id or "").strip()}.json'



def _shared_path(shared_id: str):
    return ROLEPLAY_V2_SHARED_MEMORIES_DIR / f'{str(shared_id or "").strip()}.json'



def _primary_entity_id(canon_record: dict[str, Any]) -> str:
    linked = canon_record.get('linked_entity_ids') if isinstance(canon_record.get('linked_entity_ids'), list) else []
    return str(linked[0] if linked else '').strip()



def _save_memory(record: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(_memory_path(str(record.get('id') or '')), record)
    return record



def _save_shared(record: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(_shared_path(str(record.get('id') or '')), record)
    return record



def _safe_unlink_json(path) -> bool:
    try:
        if path and path.exists() and path.suffix.lower() == '.json':
            path.unlink()
            return True
    except Exception:
        return False
    return False


def _prune_builder_compiled_files(entity_id: str, previous_meta: dict[str, Any] | None = None) -> dict[str, int]:
    """
    Remove stale file-backed compiled memory for a builder/entity record before
    recompiling. Fragment ids include a text fingerprint, so edited text creates
    new ids; without this cleanup, old JSON fragments still appear in record
    memory lists even after SQLite is pruned.
    """
    clean_entity_id = str(entity_id or '').strip()
    if not clean_entity_id:
        return {'memory_fragments': 0, 'shared_memories': 0}
    removed_fragments = 0
    removed_shared = 0
    previous_meta = previous_meta if isinstance(previous_meta, dict) else {}

    for fid in previous_meta.get('memory_fragment_ids') or []:
        clean = str(fid or '').strip()
        if clean and _safe_unlink_json(_memory_path(clean)):
            removed_fragments += 1
    for sid in previous_meta.get('shared_memory_ids') or []:
        clean = str(sid or '').strip()
        if clean and _safe_unlink_json(_shared_path(clean)):
            removed_shared += 1

    # Safety sweep for older builds where meta may not have tracked every id.
    if ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.exists():
        for path in ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json'):
            row = read_json_object(path, None)
            if not isinstance(row, dict):
                continue
            extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
            if str(extra.get('builder_record_id') or '').strip() == clean_entity_id or str(row.get('source_ref') or '').strip() == clean_entity_id:
                if _safe_unlink_json(path):
                    removed_fragments += 1
    if ROLEPLAY_V2_SHARED_MEMORIES_DIR.exists():
        for path in ROLEPLAY_V2_SHARED_MEMORIES_DIR.glob('*.json'):
            row = read_json_object(path, None)
            if not isinstance(row, dict):
                continue
            extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
            if str(extra.get('builder_record_id') or '').strip() == clean_entity_id or str(row.get('source_ref') or '').strip() == clean_entity_id:
                if _safe_unlink_json(path):
                    removed_shared += 1
    return {'memory_fragments': removed_fragments, 'shared_memories': removed_shared}


def _slug(value: Any, limit: int = 48) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', str(value or '').lower()).strip('-')
    return text[:limit] or 'item'


def _fingerprint(value: Any, limit: int = 10) -> str:
    return hashlib.sha1(str(value or '').encode('utf-8')).hexdigest()[:limit]


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                bits = []
                for key in ('name', 'title', 'summary', 'label', 'status', 'notes'):
                    part = str(item.get(key) or '').strip()
                    if part:
                        bits.append(part)
                if bits:
                    out.append(' · '.join(bits[:3]))
        return '\n'.join(out).strip()
    if isinstance(value, dict):
        bits = []
        for key, item in value.items():
            part = _stringify(item)
            if part:
                bits.append(f"{key}: {part}")
        return '\n'.join(bits[:6]).strip()
    return ''


def _iter_builder_scalars(value: Any, prefix: str = ''):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _iter_builder_scalars(item, child)
    elif isinstance(value, list):
        if all(not isinstance(item, dict) for item in value):
            rendered = _stringify(value)
            if rendered:
                yield prefix, rendered
        else:
            for idx, item in enumerate(value):
                child = f"{prefix}[{idx}]"
                if isinstance(item, dict):
                    summary = ''
                    for key in ('name', 'title', 'summary', 'public_summary', 'hidden_truth', 'history_summary'):
                        summary = str(item.get(key) or '').strip()
                        if summary:
                            break
                    if summary:
                        yield child, summary
                    yield from _iter_builder_scalars(item, child)
                else:
                    rendered = _stringify(item)
                    if rendered:
                        yield child, rendered
    else:
        rendered = _stringify(value)
        if rendered:
            yield prefix, rendered


def _builder_fragment_type(path: str) -> str:
    lower = str(path or '').lower()
    if 'memory_hints.callback_anchors' in lower or 'memory_hints.recurring_omens' in lower:
        return 'callback_anchor'
    if 'relationships[' in lower and ('.hidden_truth' in lower or '.public_summary' in lower or '.history_summary' in lower):
        return 'relationship_belief'
    if any(token in lower for token in ['runtime_guard_notes', 'canon_guard_notes', 'taboo', 'lawful_status', 'forbidden', 'scene_constraints', 'truth_reveal_limitations', 'moral_lines', 'rules_overview', 'ritual_rules', 'public_behavior_rules']):
        return 'canon_guard'
    if any(token in lower for token in ['belief_seeds', 'belief_statements', 'worldview', 'self_justification_style']):
        return 'self_belief'
    if any(token in lower for token in ['hidden_truth', 'hidden_version', 'secrets', 'lies_they_believe', 'lies_they_tell', 'secret_information', 'suppressed_history']):
        return 'episodic_memory'
    return 'semantic_fact'


def _builder_fragment_title(label: str, path: str) -> str:
    leaf = re.sub(r'^[^.]+\.', '', str(path or ''))
    leaf = leaf.replace('[', ' ').replace(']', ' ').replace('.', ' ').replace('_', ' ')
    leaf = ' '.join(word for word in leaf.split() if word)
    return f"{label} · {leaf[:72].strip() or 'memory'}"[:180]


def _dedupe_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen = []
    for row in rows:
        clean = str(row.get('id') or '').strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen


def compile_memory_from_builder_record(record_id: str) -> dict[str, Any]:
    row = load_saved_record('entity_record', record_id)
    if not row:
        raise ValueError('Builder record not found.')
    project_id = str(((row.get('links') or {}).get('source_container_id') or '')).strip()
    entity_id = str(row.get('id') or record_id).strip()
    label = str(row.get('label') or entity_id).strip()
    kind = str(row.get('kind') or '').strip()
    world_id = str((((row.get('links') or {}).get('scope') or {}).get('world_id') or '')).strip()
    universe_id = str((((row.get('links') or {}).get('scope') or {}).get('universe_id') or '')).strip()
    fields = row.get('fields') if isinstance(row.get('fields'), dict) else {}
    memory_hints = row.get('memory_hints') if isinstance(row.get('memory_hints'), dict) else {}
    summary = str(row.get('summary') or '').strip()

    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_SHARED_MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
    previous_meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
    file_prune = _prune_builder_compiled_files(entity_id, previous_meta)

    fragments = []
    shared_rows = []
    relationship_rows = []

    def save_fragment(memory_type: str, path: str, text: str, *, tags=None, scene_ready_text: str = '', relationship_targets=None, salience: float = 0.72, emotional_valence: str = 'neutral', visibility: str = 'public'):
        text = str(text or '').strip()
        if not text:
            return
        fid = f"mem_{entity_id}_{_slug(path)}_{_fingerprint(text)}"
        record = build_memory_fragment_record(
            memory_type=memory_type,
            fragment_id=fid,
            entity_id=entity_id,
            title=_builder_fragment_title(label, path),
            canonical_text=text,
            scene_ready_text=scene_ready_text or text,
            source_ref=entity_id,
            world_id=world_id,
            universe_id=universe_id,
            relationship_target_ids=relationship_targets or [],
            tags=list(tags or []),
            salience=salience,
            emotional_valence=emotional_valence,
            extra={'project_id': project_id, 'builder_record_id': entity_id, 'builder_kind': kind, 'field_path': path, 'visibility': visibility},
            meta={'status': 'compiled'},
        )
        fragments.append(_save_memory(record))

    if summary:
        save_fragment('semantic_fact', 'summary', summary, tags=[kind, 'summary'], salience=0.82)

    priority = memory_hints.get('priority') if isinstance(memory_hints.get('priority'), dict) else {}
    emotional = str(priority.get('emotional_salience') or 'medium').strip().lower()
    emotional_valence = 'charged' if emotional == 'high' else 'neutral'

    field_count = 0
    for path, value in _iter_builder_scalars(fields, 'fields'):
        lower = path.lower()
        if any(skip in lower for skip in ['author_only_notes', 'internal_notes']):
            continue
        if len(str(value or '')) < 10 and 'relationships[' not in lower:
            continue
        if not any(token in lower for token in ['summary', 'overview', 'story', 'version', 'truth', 'goal', 'objective', 'premise', 'opening_beat', 'effects', 'stakes', 'notes', 'behavior', 'appearance', 'atmosphere', 'role', 'history', 'consequences', 'scene_use', 'law', 'rules', 'constraints', 'public_', 'hidden_', 'ritual', 'danger', 'hazards', 'belief', 'secret', 'relationship', 'speech', 'goal', 'fear', 'wound', 'tension']):
            continue
        memory_type = _builder_fragment_type(path)
        tags = [kind, path.split('.')[-1]]
        salience = 0.9 if memory_type == 'canon_guard' else 0.8 if memory_type in {'callback_anchor', 'relationship_belief'} else 0.7
        if 'scene_use' in lower or 'opening_beat' in lower or 'premise' in lower:
            salience = max(salience, 0.82)
        visibility = 'hidden' if 'hidden' in lower or 'secret' in lower else 'public'
        save_fragment(memory_type, path, value, tags=tags, salience=salience, emotional_valence=emotional_valence, visibility=visibility)
        field_count += 1
        if field_count >= 28:
            break

    for idx, anchor in enumerate(memory_hints.get('callback_anchors') or []):
        save_fragment('callback_anchor', f'memory_hints.callback_anchors[{idx}]', anchor, tags=[kind, 'callback_anchor'], salience=0.78)
    for idx, omen in enumerate(memory_hints.get('recurring_omens') or []):
        save_fragment('callback_anchor', f'memory_hints.recurring_omens[{idx}]', omen, tags=[kind, 'omen'], salience=0.76)
    for idx, belief in enumerate(memory_hints.get('belief_seeds') or []):
        save_fragment('self_belief', f'memory_hints.belief_seeds[{idx}]', belief, tags=[kind, 'belief_seed'], salience=0.74, emotional_valence='charged')
    runtime_guard = str(memory_hints.get('runtime_guard_notes') or '').strip()
    if runtime_guard:
        save_fragment('canon_guard', 'memory_hints.runtime_guard_notes', runtime_guard, tags=[kind, 'runtime_guard'], salience=0.91)

    relationships = fields.get('relationships') if isinstance(fields.get('relationships'), list) else []
    for idx, rel in enumerate(relationships):
        if not isinstance(rel, dict):
            continue
        target_id = str(rel.get('target_entity_id') or '').strip()
        rel_type = str(rel.get('relationship_type') or 'relationship').strip().lower()
        rel_summary = str(rel.get('public_summary') or rel.get('history_summary') or rel.get('hidden_truth') or '').strip()
        if not target_id:
            continue
        rel_id = f"rel_{entity_id}_{_slug(target_id, 28)}"
        relationship_record = build_relationship_record(
            relationship_id=rel_id,
            source_entity_id=entity_id,
            target_entity_id=target_id,
            relationship_type=rel_type,
            summary=rel_summary,
            trust_level=float(rel.get('trust_level') or 0) / 10.0 if float(rel.get('trust_level') or 0) > 1 else float(rel.get('trust_level') or 0.5),
            tension_level=float(rel.get('conflict_level') or 0) / 10.0 if float(rel.get('conflict_level') or 0) > 1 else float(rel.get('conflict_level') or 0.0),
            bond_tags=[str(rel.get('subtype') or '').strip(), str(rel.get('attachment_valence') or '').strip()],
            source_ref=entity_id,
            extra={'project_id': project_id, 'builder_record_id': entity_id, 'builder_kind': kind},
            meta={'status': 'compiled'},
        )
        save_record(relationship_record)
        relationship_rows.append(relationship_record)
        if rel_summary:
            save_fragment('relationship_belief', f'fields.relationships[{idx}]', rel_summary, tags=['relationship', rel_type], relationship_targets=[target_id], salience=0.84, emotional_valence='charged')
        hidden_truth = str(rel.get('hidden_truth') or '').strip()
        if hidden_truth:
            sid = f"shared_{entity_id}_{_slug(target_id, 28)}"
            shared = build_shared_memory_record(
                shared_memory_id=sid,
                participant_ids=[entity_id, target_id],
                title=f"{label} shared memory",
                summary=hidden_truth,
                source_ref=entity_id,
                salience=0.73,
                extra={'project_id': project_id, 'builder_record_id': entity_id, 'builder_kind': kind, 'relationship_type': rel_type},
                meta={'status': 'compiled'},
            )
            shared_rows.append(_save_shared(shared))

    updated = copy.deepcopy(row)
    meta = updated.get('meta') if isinstance(updated.get('meta'), dict) else {}
    meta['memory_compiled'] = True
    meta['memory_compiled_at'] = _now_iso()
    meta['memory_fragment_ids'] = _dedupe_ids(fragments)
    meta['shared_memory_ids'] = _dedupe_ids(shared_rows)
    meta['relationship_record_ids'] = _dedupe_ids(relationship_rows)
    updated['meta'] = meta
    save_record(updated)
    sqlite_sync = upsert_rp2_memory_outputs(
        memory_fragments=fragments,
        shared_memories=shared_rows,
        builder_record_id=entity_id,
        source_ref=entity_id,
        prune_existing=True,
    )
    chroma_sync = sync_rp2_memory_to_chroma(project_id=project_id, entity_id=entity_id, limit=400)
    sqlite_overview = fetch_rp2_sqlite_overview()

    return {
        'builder_record': updated,
        'memory_fragments': fragments,
        'shared_memories': shared_rows,
        'relationship_records': relationship_rows,
        'compiled_counts': {
            'memory_fragments': len(fragments),
            'shared_memories': len(shared_rows),
            'relationship_records': len(relationship_rows),
        },
        'sqlite_sync': sqlite_sync,
        'chroma_sync': chroma_sync,
        'file_prune': file_prune,
        'sqlite_overview': sqlite_overview,
    }



def compile_memory_from_canon(canon_id: str) -> dict[str, Any]:
    canon_record = get_canon_record(canon_id)
    if not canon_record:
        raise ValueError('Canon record not found.')
    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_SHARED_MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

    project_id = str(canon_record.get('project_id') or '').strip()
    source_ref = str(canon_record.get('scope_id') or '').strip()
    entity_id = _primary_entity_id(canon_record)
    data = canon_record.get('data') if isinstance(canon_record.get('data'), dict) else {}

    memory_fragments: list[dict[str, Any]] = []
    shared_memories: list[dict[str, Any]] = []

    chapter_summary = str(data.get('chapter_summary') or canon_record.get('summary') or '').strip()
    if chapter_summary:
        memory_fragments.append(_save_memory(build_memory_fragment_record(
            memory_type='semantic_fact',
            entity_id=entity_id,
            title=f"{canon_record.get('label') or 'canon'} summary",
            canonical_text=chapter_summary,
            scene_ready_text=chapter_summary,
            source_ref=source_ref,
            world_id='',
            universe_id='',
            tags=['canon', 'summary'],
            salience=0.8,
            emotional_valence='neutral',
            extra={'project_id': project_id, 'canon_id': canon_id},
            meta={'status': 'compiled'},
        )))

    for item in data.get('memory_candidates') or []:
        canonical_text = str(item.get('canonical_text') or '').strip()
        if not canonical_text:
            continue
        memory_fragments.append(_save_memory(build_memory_fragment_record(
            memory_type='episodic_memory',
            entity_id=entity_id,
            title=str(item.get('title') or canonical_text[:80]).strip(),
            canonical_text=canonical_text,
            scene_ready_text=canonical_text,
            source_ref=source_ref,
            tags=['candidate', 'episodic'],
            salience=0.75,
            emotional_valence='charged',
            extra={'project_id': project_id, 'canon_id': canon_id, 'confidence': item.get('confidence')},
            meta={'status': 'compiled'},
        )))

    for item in data.get('canon_rule_candidates') or []:
        rule_text = str(item.get('rule_text') or '').strip()
        if not rule_text:
            continue
        memory_fragments.append(_save_memory(build_memory_fragment_record(
            memory_type='canon_guard',
            entity_id=entity_id,
            title=rule_text[:80],
            canonical_text=rule_text,
            scene_ready_text=rule_text,
            source_ref=source_ref,
            tags=['rule', 'canon_guard'],
            salience=0.9,
            emotional_valence='neutral',
            extra={'project_id': project_id, 'canon_id': canon_id},
            meta={'status': 'compiled'},
        )))

    for timeline_id in data.get('timeline_event_ids') or []:
        event = load_saved_record('timeline_event', timeline_id)
        if not event:
            continue
        summary = str(event.get('summary') or event.get('title') or '').strip()
        if not summary:
            continue
        memory_fragments.append(_save_memory(build_memory_fragment_record(
            memory_type='callback_anchor',
            entity_id=entity_id,
            title=str(event.get('title') or summary[:80]).strip(),
            canonical_text=summary,
            scene_ready_text=summary,
            source_ref=str(event.get('source_ref') or source_ref).strip(),
            chapter_ref=str(event.get('chapter_ref') or '').strip(),
            scene_ref=str(event.get('scene_ref') or '').strip(),
            tags=['timeline', 'callback_anchor'],
            salience=0.7,
            emotional_valence='neutral',
            extra={'project_id': project_id, 'canon_id': canon_id, 'timeline_event_id': timeline_id},
            meta={'status': 'compiled'},
        )))

    for relationship_id in data.get('relationship_ids') or []:
        rel = load_saved_record('relationship_record', relationship_id)
        if not rel:
            continue
        summary = str(rel.get('summary') or '').strip()
        if summary:
            memory_fragments.append(_save_memory(build_memory_fragment_record(
                memory_type='relationship_belief',
                entity_id=str(rel.get('source_entity_id') or entity_id).strip(),
                title=f"{rel.get('relationship_type') or 'relationship'} belief",
                canonical_text=summary,
                scene_ready_text=summary,
                source_ref=str(rel.get('source_ref') or source_ref).strip(),
                relationship_target_ids=[str(rel.get('target_entity_id') or '').strip()],
                tags=['relationship', str(rel.get('relationship_type') or '').strip().lower()],
                salience=0.72,
                emotional_valence='charged',
                extra={'project_id': project_id, 'canon_id': canon_id, 'relationship_id': relationship_id},
                meta={'status': 'compiled'},
            )))
        shared_memories.append(_save_shared(build_shared_memory_record(
            participant_ids=[str(rel.get('source_entity_id') or '').strip(), str(rel.get('target_entity_id') or '').strip()],
            title=f"Shared memory from {canon_record.get('label') or 'canon'}",
            summary=summary or str(rel.get('relationship_type') or 'interaction').strip(),
            source_ref=str(rel.get('source_ref') or source_ref).strip(),
            salience=0.68,
            extra={'project_id': project_id, 'canon_id': canon_id, 'relationship_id': relationship_id},
            meta={'status': 'compiled'},
        )))

    updated_canon = copy.deepcopy(canon_record)
    meta = updated_canon.get('meta') if isinstance(updated_canon.get('meta'), dict) else {}
    meta['memory_compiled'] = True
    meta['memory_compiled_at'] = _now_iso()
    meta['memory_fragment_ids'] = [str(item.get('id') or '').strip() for item in memory_fragments]
    meta['shared_memory_ids'] = [str(item.get('id') or '').strip() for item in shared_memories]
    updated_canon['meta'] = meta
    from .roleplay_v2_canon_compiler import _canon_path  # local import to avoid cross import at top
    atomic_write_json(_canon_path(canon_id), updated_canon)
    sqlite_sync = upsert_rp2_memory_outputs(
        memory_fragments=memory_fragments,
        shared_memories=shared_memories,
        canon_id=canon_id,
        source_ref=source_ref,
        prune_existing=True,
    )
    chroma_sync = sync_rp2_memory_to_chroma(project_id=project_id, entity_id=entity_id, limit=500)
    sqlite_overview = fetch_rp2_sqlite_overview()

    return {
        'canon_record': updated_canon,
        'memory_fragments': memory_fragments,
        'shared_memories': shared_memories,
        'compiled_counts': {
            'memory_fragments': len(memory_fragments),
            'shared_memories': len(shared_memories),
        },
        'sqlite_sync': sqlite_sync,
        'chroma_sync': chroma_sync,
        'sqlite_overview': sqlite_overview,
    }



def get_memory_fragment(fragment_id: str) -> dict[str, Any] | None:
    return read_json_object(_memory_path(fragment_id), None)





def list_memory_for_record(record_id: str, limit: int = 24) -> dict[str, Any]:
    clean_record_id = str(record_id or '').strip()
    fragments: list[dict[str, Any]] = []
    shared_rows: list[dict[str, Any]] = []
    if not clean_record_id:
        return {'record_id': clean_record_id, 'memory_fragments': [], 'shared_memories': [], 'count': 0, 'shared_count': 0, 'compile_status': {}}

    builder_row = load_saved_record('entity_record', clean_record_id)
    builder_meta = builder_row.get('meta') if isinstance(builder_row, dict) and isinstance(builder_row.get('meta'), dict) else {}

    for path in sorted(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        if str(row.get('entity_id') or '').strip() != clean_record_id and str(extra.get('builder_record_id') or '').strip() != clean_record_id:
            continue
        summary = str(row.get('scene_ready_text') or row.get('canonical_text') or '').strip()
        fragments.append({
            'id': str(row.get('id') or '').strip(),
            'memory_type': str(row.get('memory_type') or '').strip(),
            'title': str(row.get('title') or '').strip(),
            'summary': summary[:360],
            'source_ref': str(row.get('source_ref') or '').strip(),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
        })

    for path in sorted(ROLEPLAY_V2_SHARED_MEMORIES_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        participants = [str(item or '').strip() for item in (row.get('participant_ids') or []) if str(item or '').strip()]
        if clean_record_id not in participants:
            continue
        shared_rows.append({
            'id': str(row.get('id') or '').strip(),
            'title': str(row.get('title') or '').strip(),
            'summary': str(row.get('summary') or '').strip()[:360],
            'participant_ids': participants[:6],
            'source_ref': str(row.get('source_ref') or '').strip(),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
        })

    def _sort_key(item: dict[str, Any]) -> str:
        return str(item.get('updated_at') or '')

    fragments.sort(key=_sort_key, reverse=True)
    shared_rows.sort(key=_sort_key, reverse=True)
    record_updated_at = str(builder_meta.get('updated_at') or '').strip()
    memory_compiled_at = str(builder_meta.get('memory_compiled_at') or '').strip()
    compile_status = {
        'record_id': clean_record_id,
        'record_label': str((builder_row or {}).get('label') or (builder_row or {}).get('display_label') or clean_record_id).strip(),
        'record_kind': str((builder_row or {}).get('kind') or '').strip(),
        'record_updated_at': record_updated_at,
        'memory_compiled': bool(builder_meta.get('memory_compiled')),
        'memory_compiled_at': memory_compiled_at,
        'fragment_id_count': len(builder_meta.get('memory_fragment_ids') or []),
        'shared_id_count': len(builder_meta.get('shared_memory_ids') or []),
        'relationship_id_count': len(builder_meta.get('relationship_record_ids') or []),
        'needs_memory_recompile': (not memory_compiled_at) or (bool(record_updated_at and memory_compiled_at and record_updated_at > memory_compiled_at)),
    }
    return {
        'record_id': clean_record_id,
        'memory_fragments': fragments[:max(1, int(limit or 24))],
        'shared_memories': shared_rows[:max(1, int(limit or 12))],
        'count': len(fragments),
        'shared_count': len(shared_rows),
        'compile_status': compile_status,
    }
def list_project_memory(project_id: str) -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    fragments: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        if str(extra.get('project_id') or '').strip() != clean_project_id:
            continue
        fragments.append({
            'id': str(row.get('id') or '').strip(),
            'memory_type': str(row.get('memory_type') or '').strip(),
            'title': str(row.get('title') or '').strip(),
            'entity_id': str(row.get('entity_id') or '').strip(),
            'source_ref': str(row.get('source_ref') or '').strip(),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
        })
    return {'project_id': clean_project_id, 'memory_fragments': fragments, 'count': len(fragments)}
