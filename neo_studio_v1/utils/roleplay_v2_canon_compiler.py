from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from ..contracts.roleplay_v2_memory_records import build_relationship_record, build_timeline_event_record
from ..contracts.roleplay_v2_records import build_canon_record, build_entity_record
from .roleplay_v2_breakdown_helper import get_breakdown_output
from .roleplay_v2_foundation import (
    ROLEPLAY_V2_CANON_RECORDS_DIR,
    ROLEPLAY_V2_ENTITIES_DIR,
    ROLEPLAY_V2_RELATIONSHIPS_DIR,
    ROLEPLAY_V2_TIMELINE_EVENTS_DIR,
)
from .roleplay_v2_source_projects import get_novel_project
from .storage_io import atomic_write_json, read_json_object

ORG_HINTS = {'guild', 'order', 'council', 'house', 'company', 'clan', 'cult', 'faction'}
CITY_HINTS = {'city', 'town', 'village', 'harbor', 'port', 'settlement'}
LOCATION_HINTS = {'forest', 'castle', 'tower', 'street', 'room', 'harbor', 'bay', 'temple', 'school'}
WORLD_HINTS = {'realm', 'kingdom', 'world', 'empire', 'continent'}
LEGEND_HINTS = {'legend', 'myth', 'prophecy'}
CYCLE_HINTS = {'cycle', 'condition', 'curse', 'system'}
CREATURE_HINTS = {'beast', 'dragon', 'wolf', 'creature', 'fauna', 'animal'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _canon_path(canon_id: str):
    return ROLEPLAY_V2_CANON_RECORDS_DIR / f'{str(canon_id or "").strip()}.json'



def _entity_path(entity_id: str):
    return ROLEPLAY_V2_ENTITIES_DIR / f'{str(entity_id or "").strip()}.json'



def _timeline_path(event_id: str):
    return ROLEPLAY_V2_TIMELINE_EVENTS_DIR / f'{str(event_id or "").strip()}.json'



def _relationship_path(rel_id: str):
    return ROLEPLAY_V2_RELATIONSHIPS_DIR / f'{str(rel_id or "").strip()}.json'



def _guess_entity_kind(label: str) -> str:
    lower = str(label or '').strip().lower()
    words = set(lower.split())
    if words & LEGEND_HINTS:
        return 'legend'
    if words & CYCLE_HINTS:
        return 'cycle'
    if words & ORG_HINTS:
        return 'organization'
    if words & WORLD_HINTS:
        return 'world'
    if words & CITY_HINTS:
        return 'city'
    if words & LOCATION_HINTS:
        return 'location'
    if words & CREATURE_HINTS:
        return 'creature'
    return 'character'



def _entity_label(entity_candidate: dict[str, Any]) -> str:
    return str(entity_candidate.get('label') or '').strip()



def _project_scope_label(project_id: str) -> str:
    project = get_novel_project(project_id)
    return str((project or {}).get('title') or project_id or 'source project').strip()



def _compiled_summary(payload: dict[str, Any]) -> str:
    chapter_summary = str(payload.get('chapter_summary') or '').strip()
    entity_count = len(payload.get('entity_candidates') or [])
    scene_count = len(payload.get('scene_breakdown') or [])
    return f'{chapter_summary} Structured from {scene_count} scene(s) with {entity_count} entity candidate(s).'.strip()



def compile_approved_breakdown(helper_output_id: str, *, allow_unapproved: bool = False) -> dict[str, Any]:
    helper_output = get_breakdown_output(helper_output_id)
    if not helper_output:
        raise ValueError('Breakdown output not found.')
    meta = helper_output.get('meta') if isinstance(helper_output.get('meta'), dict) else {}
    if not allow_unapproved and not bool(meta.get('approved')):
        raise ValueError('Breakdown must be approved before canon compile.')
    payload = helper_output.get('structured_payload') if isinstance(helper_output.get('structured_payload'), dict) else {}
    project_id = str(payload.get('project_id') or '').strip()
    document_id = str(payload.get('document_id') or '').strip()
    title = str(payload.get('title') or helper_output.get('id') or '').strip()
    project = get_novel_project(project_id) or {}

    ROLEPLAY_V2_ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_TIMELINE_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_RELATIONSHIPS_DIR.mkdir(parents=True, exist_ok=True)
    ROLEPLAY_V2_CANON_RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    entity_records: list[dict[str, Any]] = []
    for candidate in payload.get('entity_candidates') or []:
        label = _entity_label(candidate)
        if not label:
            continue
        entity = build_entity_record(
            kind=_guess_entity_kind(label),
            label=label,
            data={
                'kind_hint': str(candidate.get('kind') or 'candidate').strip(),
                'mentions': int(candidate.get('mentions') or 0),
                'project_id': project_id,
                'compiled_from_helper_output_id': helper_output_id,
            },
            links={
                'source_container_id': project_id,
                'scope': {
                    'world_id': str(project.get('linked_world_id') or '').strip(),
                    'universe_id': str(project.get('linked_universe_id') or '').strip(),
                },
            },
            source_refs=[document_id, helper_output_id],
            meta={'status': 'compiled'},
        )
        atomic_write_json(_entity_path(str(entity.get('id') or '')), entity)
        entity_records.append(entity)
    entity_lookup = {str(entity.get('label') or '').strip(): str(entity.get('id') or '').strip() for entity in entity_records}

    timeline_records: list[dict[str, Any]] = []
    for candidate in payload.get('timeline_candidates') or []:
        event = build_timeline_event_record(
            entity_id=document_id,
            title=str(candidate.get('title') or '').strip(),
            summary=str(candidate.get('summary') or '').strip(),
            event_order=int(candidate.get('event_order') or 0),
            chapter_ref=str(payload.get('title') or '').strip(),
            scene_ref=f"scene_{int(candidate.get('scene_index') or 0)}",
            participants=list(entity_lookup.values())[:6],
            source_ref=document_id,
            extra={'project_id': project_id, 'compiled_from_helper_output_id': helper_output_id},
            meta={'status': 'compiled'},
        )
        atomic_write_json(_timeline_path(str(event.get('id') or '')), event)
        timeline_records.append(event)

    relationship_records: list[dict[str, Any]] = []
    for candidate in payload.get('relationship_shift_candidates') or []:
        participants = [str(item or '').strip() for item in (candidate.get('participants') or []) if str(item or '').strip()]
        if len(participants) < 2:
            continue
        rel = build_relationship_record(
            source_entity_id=entity_lookup.get(participants[0], participants[0]),
            target_entity_id=entity_lookup.get(participants[1], participants[1]),
            relationship_type=str(candidate.get('shift_hint') or 'interaction').strip().lower(),
            summary=str(candidate.get('evidence') or '').strip(),
            trust_level=0.5,
            tension_level=0.5 if str(candidate.get('shift_hint') or '').strip().lower() in {'hate', 'betray', 'fear', 'jealous'} else 0.25,
            bond_tags=[str(candidate.get('shift_hint') or '').strip().lower()],
            source_ref=document_id,
            extra={'project_id': project_id, 'compiled_from_helper_output_id': helper_output_id},
            meta={'status': 'compiled'},
        )
        atomic_write_json(_relationship_path(str(rel.get('id') or '')), rel)
        relationship_records.append(rel)

    canon_record = build_canon_record(
        label=f"{title} canon",
        scope_type='source_document',
        scope_id=document_id,
        project_id=project_id,
        summary=_compiled_summary(payload),
        linked_entity_ids=[str(entity.get('id') or '').strip() for entity in entity_records],
        source_refs=[document_id, helper_output_id],
        data={
            'project_label': _project_scope_label(project_id),
            'chapter_summary': str(payload.get('chapter_summary') or '').strip(),
            'source_metadata': copy.deepcopy(payload.get('source_metadata') or {}),
            'canon_rule_candidates': copy.deepcopy(payload.get('canon_rule_candidates') or []),
            'memory_candidates': copy.deepcopy(payload.get('memory_candidates') or []),
            'scene_count': len(payload.get('scene_breakdown') or []),
            'timeline_event_ids': [str(item.get('id') or '').strip() for item in timeline_records],
            'relationship_ids': [str(item.get('id') or '').strip() for item in relationship_records],
            'compiled_from_helper_output_id': helper_output_id,
            'compiled_at': _now_iso(),
        },
        meta={'status': 'compiled'},
    )
    atomic_write_json(_canon_path(str(canon_record.get('id') or '')), canon_record)

    meta['compiled'] = True
    meta['compiled_at'] = _now_iso()
    meta['compiled_canon_id'] = str(canon_record.get('id') or '').strip()
    meta['compiled_entity_ids'] = [str(entity.get('id') or '').strip() for entity in entity_records]
    meta['compiled_timeline_ids'] = [str(item.get('id') or '').strip() for item in timeline_records]
    meta['compiled_relationship_ids'] = [str(item.get('id') or '').strip() for item in relationship_records]
    helper_output['meta'] = meta
    from .roleplay_v2_breakdown_helper import _helper_output_path  # local import to avoid circular top import
    atomic_write_json(_helper_output_path(helper_output_id), helper_output)

    return {
        'canon_record': canon_record,
        'entity_records': entity_records,
        'timeline_records': timeline_records,
        'relationship_records': relationship_records,
        'compiled_counts': {
            'entities': len(entity_records),
            'timeline_events': len(timeline_records),
            'relationships': len(relationship_records),
        },
    }



def get_canon_record(canon_id: str) -> dict[str, Any] | None:
    return read_json_object(_canon_path(canon_id), None)



def list_project_canon(project_id: str) -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    canon_records: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_CANON_RECORDS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        if str(row.get('project_id') or '').strip() != clean_project_id:
            continue
        canon_records.append({
            'id': str(row.get('id') or '').strip(),
            'label': str(row.get('label') or '').strip(),
            'summary': str(row.get('summary') or '').strip(),
            'scope_id': str(row.get('scope_id') or '').strip(),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
            'linked_entity_ids': list(row.get('linked_entity_ids') or []),
        })
    return {'project_id': clean_project_id, 'canon_records': canon_records, 'count': len(canon_records)}
