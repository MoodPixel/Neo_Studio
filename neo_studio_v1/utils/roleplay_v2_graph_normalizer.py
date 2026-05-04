from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..contracts.roleplay_v2_records import canonical_entity_kind, get_entity_spec, normalize_entity_links
from .storage_io import atomic_write_json, read_json_object

_CANONICAL_SLOT_SEMANTICS: dict[str, dict[str, Any]] = {
    'universe_id': {'family': 'scope', 'relation': 'scoped_to_universe', 'reverse_relation': 'contains_record', 'target_kind': 'universe', 'cardinality': 'one'},
    'world_id': {'family': 'scope', 'relation': 'scoped_to_world', 'reverse_relation': 'contains_record', 'target_kind': 'world', 'cardinality': 'one'},
    'region_id': {'family': 'scope', 'relation': 'scoped_to_region', 'reverse_relation': 'contains_record', 'target_kind': 'region', 'cardinality': 'one'},
    'city_id': {'family': 'scope', 'relation': 'scoped_to_city', 'reverse_relation': 'contains_record', 'target_kind': 'city', 'cardinality': 'one'},
    'location_id': {'family': 'scope', 'relation': 'scoped_to_location', 'reverse_relation': 'contains_record', 'target_kind': 'location', 'cardinality': 'one'},
    'parent_region_id': {'family': 'parent', 'relation': 'child_of_region', 'reverse_relation': 'parent_of', 'target_kind': 'region', 'cardinality': 'one'},
    'parent_city_id': {'family': 'parent', 'relation': 'child_of_city', 'reverse_relation': 'parent_of', 'target_kind': 'city', 'cardinality': 'one'},
    'parent_location_id': {'family': 'parent', 'relation': 'child_of_location', 'reverse_relation': 'parent_of', 'target_kind': 'location', 'cardinality': 'one'},
    'parent_organization_id': {'family': 'parent', 'relation': 'child_of_organization', 'reverse_relation': 'parent_of', 'target_kind': 'organization', 'cardinality': 'one'},
    'origin_world_id': {'family': 'state', 'relation': 'origin_world', 'reverse_relation': 'origin_for', 'target_kind': 'world', 'cardinality': 'one'},
    'current_world_id': {'family': 'state', 'relation': 'current_world', 'reverse_relation': 'current_scope_for', 'target_kind': 'world', 'cardinality': 'one'},
    'origin_region_id': {'family': 'state', 'relation': 'origin_region', 'reverse_relation': 'origin_for', 'target_kind': 'region', 'cardinality': 'one'},
    'current_region_id': {'family': 'state', 'relation': 'current_region', 'reverse_relation': 'current_scope_for', 'target_kind': 'region', 'cardinality': 'one'},
    'origin_city_id': {'family': 'state', 'relation': 'origin_city', 'reverse_relation': 'origin_for', 'target_kind': 'city', 'cardinality': 'one'},
    'current_city_id': {'family': 'state', 'relation': 'current_city', 'reverse_relation': 'current_scope_for', 'target_kind': 'city', 'cardinality': 'one'},
    'origin_location_id': {'family': 'state', 'relation': 'origin_location', 'reverse_relation': 'origin_for', 'target_kind': 'location', 'cardinality': 'one'},
    'current_location_id': {'family': 'state', 'relation': 'current_location', 'reverse_relation': 'current_scope_for', 'target_kind': 'location', 'cardinality': 'one'},
    'base_location_id': {'family': 'state', 'relation': 'based_in', 'reverse_relation': 'base_for', 'target_kind': 'location', 'cardinality': 'one'},
    'capital_city_id': {'family': 'state', 'relation': 'capital_city', 'reverse_relation': 'capital_of', 'target_kind': 'city', 'cardinality': 'one'},
    'capital_of_region_id': {'family': 'state', 'relation': 'capital_of_region', 'reverse_relation': 'has_capital', 'target_kind': 'region', 'cardinality': 'one'},
    'seat_location_id': {'family': 'state', 'relation': 'seat_of_power', 'reverse_relation': 'seat_for', 'target_kind': 'location', 'cardinality': 'one'},
    'primary_world_id': {'family': 'scope', 'relation': 'primary_world', 'reverse_relation': 'primary_scope_for', 'target_kind': 'world', 'cardinality': 'one'},
    'current_holder_id': {'family': 'state', 'relation': 'held_by', 'reverse_relation': 'holds', 'target_kind_candidates': ['character', 'organization'], 'cardinality': 'one'},
    'source_organization_id': {'family': 'state', 'relation': 'sourced_from_organization', 'reverse_relation': 'source_for', 'target_kind': 'organization', 'cardinality': 'one'},
    'source_ritual_id': {'family': 'state', 'relation': 'sourced_from_ritual', 'reverse_relation': 'source_for', 'target_kind': 'ritual', 'cardinality': 'one'},
    'source_legend_id': {'family': 'state', 'relation': 'sourced_from_legend', 'reverse_relation': 'source_for', 'target_kind': 'legend', 'cardinality': 'one'},
    'source_artifact_id': {'family': 'state', 'relation': 'sourced_from_artifact', 'reverse_relation': 'source_for', 'target_kind': 'artifact', 'cardinality': 'one'},
    'source_cycle_id': {'family': 'state', 'relation': 'sourced_from_cycle', 'reverse_relation': 'source_for', 'target_kind': 'cycle', 'cardinality': 'one'},
    'world_ids': {'family': 'related', 'relation': 'linked_world', 'reverse_relation': 'linked_to_record', 'target_kind': 'world', 'cardinality': 'many'},
    'region_ids': {'family': 'related', 'relation': 'linked_region', 'reverse_relation': 'linked_to_record', 'target_kind': 'region', 'cardinality': 'many'},
    'city_ids': {'family': 'related', 'relation': 'linked_city', 'reverse_relation': 'linked_to_record', 'target_kind': 'city', 'cardinality': 'many'},
    'location_ids': {'family': 'related', 'relation': 'linked_location', 'reverse_relation': 'linked_to_record', 'target_kind': 'location', 'cardinality': 'many'},
    'character_ids': {'family': 'related', 'relation': 'linked_character', 'reverse_relation': 'linked_to_record', 'target_kind': 'character', 'cardinality': 'many'},
    'organization_ids': {'family': 'related', 'relation': 'linked_organization', 'reverse_relation': 'linked_to_record', 'target_kind': 'organization', 'cardinality': 'many'},
    'artifact_ids': {'family': 'related', 'relation': 'linked_artifact', 'reverse_relation': 'linked_to_record', 'target_kind': 'artifact', 'cardinality': 'many'},
    'ritual_ids': {'family': 'related', 'relation': 'linked_ritual', 'reverse_relation': 'linked_to_record', 'target_kind': 'ritual', 'cardinality': 'many'},
    'cycle_ids': {'family': 'related', 'relation': 'linked_cycle', 'reverse_relation': 'linked_to_record', 'target_kind': 'cycle', 'cardinality': 'many'},
    'creature_ids': {'family': 'related', 'relation': 'linked_creature', 'reverse_relation': 'linked_to_record', 'target_kind': 'creature', 'cardinality': 'many'},
    'legend_ids': {'family': 'related', 'relation': 'linked_legend', 'reverse_relation': 'linked_to_record', 'target_kind': 'legend', 'cardinality': 'many'},
    'scenario_ids': {'family': 'related', 'relation': 'linked_scenario', 'reverse_relation': 'linked_to_record', 'target_kind': 'scenario', 'cardinality': 'many'},
    'cast_character_ids': {'family': 'cast', 'relation': 'features_cast', 'reverse_relation': 'cast_in', 'target_kind': 'character', 'cardinality': 'many'},
    'leader_character_ids': {'family': 'leadership', 'relation': 'led_by', 'reverse_relation': 'leads', 'target_kind': 'character', 'cardinality': 'many'},
    'member_character_ids': {'family': 'membership', 'relation': 'has_member', 'reverse_relation': 'member_of', 'target_kind': 'character', 'cardinality': 'many'},
    'ally_organization_ids': {'family': 'alliance', 'relation': 'allied_with', 'reverse_relation': 'allied_with', 'target_kind': 'organization', 'cardinality': 'many'},
    'rival_organization_ids': {'family': 'rivalry', 'relation': 'rival_of', 'reverse_relation': 'rival_of', 'target_kind': 'organization', 'cardinality': 'many'},
    'linked_character_ids': {'family': 'association', 'relation': 'linked_character', 'reverse_relation': 'linked_to_record', 'target_kind': 'character', 'cardinality': 'many'},
    'linked_organization_ids': {'family': 'association', 'relation': 'linked_organization', 'reverse_relation': 'linked_to_record', 'target_kind': 'organization', 'cardinality': 'many'},
    'linked_location_ids': {'family': 'association', 'relation': 'linked_location', 'reverse_relation': 'linked_to_record', 'target_kind': 'location', 'cardinality': 'many'},
    'linked_artifact_ids': {'family': 'association', 'relation': 'linked_artifact', 'reverse_relation': 'linked_to_record', 'target_kind': 'artifact', 'cardinality': 'many'},
    'linked_ritual_ids': {'family': 'association', 'relation': 'linked_ritual', 'reverse_relation': 'linked_to_record', 'target_kind': 'ritual', 'cardinality': 'many'},
    'linked_cycle_ids': {'family': 'association', 'relation': 'linked_cycle', 'reverse_relation': 'linked_to_record', 'target_kind': 'cycle', 'cardinality': 'many'},
    'linked_creature_ids': {'family': 'association', 'relation': 'linked_creature', 'reverse_relation': 'linked_to_record', 'target_kind': 'creature', 'cardinality': 'many'},
    'anchor_entity_id': {'family': 'anchor', 'relation': 'anchored_to', 'reverse_relation': 'anchor_for', 'target_kind_candidates': ['character', 'world', 'universe', 'region', 'city', 'location', 'organization', 'scenario', 'artifact', 'ritual', 'cycle', 'creature', 'legend'], 'cardinality': 'one'},
}

_RELATIONSHIP_REVERSE_RELATIONS = {
    'ally': 'ally',
    'allied_with': 'allied_with',
    'rival': 'rival_of',
    'rival_of': 'rival_of',
    'member': 'member_of',
    'member_of': 'has_member',
    'leader': 'led_by',
    'led_by': 'leads',
    'parent': 'child_of',
    'child': 'parent_of',
    'mentor': 'mentored_by',
    'student': 'mentors',
    'owner': 'owned_by',
    'owned_by': 'owner_of',
}


def slug_text(value: str) -> str:
    parts: list[str] = []
    for chunk in str(value or '').lower().replace('/', ' ').replace('_', ' ').split():
        clean = ''.join(ch for ch in chunk if ch.isalnum() or ch == '-')
        if clean:
            parts.append(clean)
    return '-'.join(parts)[:80]


def _clean_id(value: Any) -> str:
    return str(value or '').strip()


def build_base_entity_id(kind: str, label: str) -> str:
    clean_kind = canonical_entity_kind(kind)
    slug = slug_text(label)
    return f'{clean_kind}_{slug or "untitled"}'


def allocate_entity_id(*, kind: str, label: str, entities_dir: Path, provided_id: str = '') -> str:
    clean_provided = _clean_id(provided_id)
    if clean_provided:
        return clean_provided
    base = build_base_entity_id(kind, label)
    candidate = base
    suffix = 2
    while (entities_dir / f'{candidate}.json').exists():
        candidate = f'{base}_{suffix}'
        suffix += 1
    return candidate


def _fallback_target_kind_candidates(slot: str) -> list[str]:
    clean = str(slot or '').strip().lower()
    if not clean or clean == 'source_container_id':
        return []
    if clean.endswith('_ids'):
        clean = clean[:-4]
    elif clean.endswith('_id'):
        clean = clean[:-3]
    for prefix in (
        'origin_', 'current_', 'cast_', 'linked_', 'focus_', 'primary_', 'base_', 'seat_',
        'member_', 'leader_', 'ally_', 'rival_', 'anchor_', 'parent_', 'source_',
    ):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    if clean.startswith('capital_of_'):
        clean = 'region'
    elif clean == 'capital':
        clean = 'city'
    mapping = {
        'universe': ['universe'],
        'world': ['world'],
        'region': ['region'],
        'city': ['city'],
        'location': ['location'],
        'character': ['character'],
        'organization': ['organization'],
        'artifact': ['artifact'],
        'ritual': ['ritual'],
        'cycle': ['cycle'],
        'creature': ['creature'],
        'legend': ['legend'],
        'scenario': ['scenario'],
        'holder': ['character', 'organization'],
        'entity': ['character', 'world', 'universe', 'region', 'city', 'location', 'organization', 'scenario', 'artifact', 'ritual', 'cycle', 'creature', 'legend'],
    }
    return list(mapping.get(clean, []))


def _fallback_slot_family(slot: str, spec: dict[str, Any]) -> str:
    clean = str(slot or '').strip()
    scope_slots = set(spec.get('link_ownership', {}).get('scope') or [])
    related_slots = set(spec.get('link_ownership', {}).get('related') or [])
    if clean in scope_slots:
        return 'scope'
    if clean in related_slots:
        return 'related'
    if clean.startswith('parent_'):
        return 'parent'
    if clean.startswith(('origin_', 'current_', 'base_', 'capital_', 'seat_', 'primary_', 'source_')) or clean.endswith('_holder_id'):
        return 'state'
    return 'related'


def _fallback_edge_relation(slot: str) -> str:
    clean = str(slot or '').strip().lower()
    if clean.endswith('_ids'):
        clean = clean[:-4]
    elif clean.endswith('_id'):
        clean = clean[:-3]
    for prefix in ('origin_', 'current_', 'linked_', 'cast_', 'member_', 'leader_', 'ally_', 'rival_', 'anchor_', 'parent_', 'primary_', 'base_', 'seat_', 'source_'):
        if clean.startswith(prefix):
            rel = prefix[:-1]
            if rel:
                return rel
    return clean or 'related'


def _slot_semantics(slot: str, spec: dict[str, Any]) -> dict[str, Any]:
    clean = str(slot or '').strip()
    if clean in _CANONICAL_SLOT_SEMANTICS:
        semantics = deepcopy(_CANONICAL_SLOT_SEMANTICS[clean])
        candidates = list(semantics.get('target_kind_candidates') or ([] if not semantics.get('target_kind') else [semantics['target_kind']]))
        semantics['target_kind_candidates'] = candidates
        return semantics
    candidates = _fallback_target_kind_candidates(clean)
    return {
        'family': _fallback_slot_family(clean, spec),
        'relation': _fallback_edge_relation(clean),
        'reverse_relation': 'linked_to_record',
        'target_kind_candidates': candidates,
        'cardinality': 'many' if clean.endswith('_ids') else 'one',
    }


def _relationship_reverse_relation(relation: str) -> str:
    clean = str(relation or '').strip().lower()
    return _RELATIONSHIP_REVERSE_RELATIONS.get(clean, clean or 'related_to')


def _as_id_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in (_clean_id(v) for v in value) if item]
    clean = _clean_id(value)
    return [clean] if clean else []


def build_normalized_edges(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = record if isinstance(record, dict) else {}
    source_id = _clean_id(payload.get('id'))
    source_kind = canonical_entity_kind(payload.get('kind') or '')
    if not source_id or not source_kind:
        return []
    spec = get_entity_spec(source_kind)
    links = normalize_entity_links(source_kind, payload.get('links'))
    edges: list[dict[str, Any]] = []

    for family_key in ('scope', 'related'):
        raw = links.get(family_key)
        if not isinstance(raw, dict):
            continue
        for slot, value in raw.items():
            values = _as_id_list(value)
            if not values:
                continue
            semantics = _slot_semantics(slot, spec)
            cardinality = semantics.get('cardinality') or ('many' if slot.endswith('_ids') or len(values) > 1 else 'one')
            target_candidates = list(semantics.get('target_kind_candidates') or [])
            target_kind = semantics.get('target_kind') or (target_candidates[0] if len(target_candidates) == 1 else '')
            for target_id in values:
                edges.append({
                    'edge_id': f'{source_id}:{slot}:{target_id}',
                    'source_id': source_id,
                    'source_kind': source_kind,
                    'family': semantics.get('family') or family_key,
                    'slot': slot,
                    'relation': semantics.get('relation') or 'related_to',
                    'reverse_relation': semantics.get('reverse_relation') or 'linked_to_record',
                    'target_id': target_id,
                    'target_kind': target_kind,
                    'target_kind_candidates': target_candidates,
                    'cardinality': cardinality,
                    'status': 'active',
                    'visibility': 'public',
                    'source_mode': 'manual',
                    'notes': '',
                })

    for section_path in spec.get('edge_sections') or []:
        current: Any = payload
        for part in str(section_path).split('.'):
            current = current.get(part) if isinstance(current, dict) else None
        if not isinstance(current, list):
            continue
        for idx, entry in enumerate(current):
            if not isinstance(entry, dict):
                continue
            target_id = _clean_id(entry.get('target_entity_id'))
            if not target_id:
                continue
            target_kind = canonical_entity_kind(entry.get('target_entity_kind') or '')
            relation = _clean_id(entry.get('relationship_type') or 'relationship').lower() or 'relationship'
            edges.append({
                'edge_id': f'{source_id}:relationship:{target_id}:{idx}',
                'source_id': source_id,
                'source_kind': source_kind,
                'family': 'relationship',
                'slot': section_path,
                'relation': relation,
                'reverse_relation': _relationship_reverse_relation(relation),
                'target_id': target_id,
                'target_kind': target_kind,
                'target_kind_candidates': [target_kind] if target_kind else _fallback_target_kind_candidates('entity_id'),
                'cardinality': 'many',
                'status': _clean_id(entry.get('status')) or 'active',
                'visibility': _clean_id(entry.get('visibility')) or 'public',
                'source_mode': 'manual',
                'notes': _clean_id(entry.get('public_summary') or entry.get('history_summary') or entry.get('scene_behavior_notes')),
                'relationship_payload': deepcopy(entry),
            })
    return edges


def build_graph_projection(record: dict[str, Any] | None, reverse_materialized: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = record if isinstance(record, dict) else {}
    clean_kind = canonical_entity_kind(payload.get('kind') or '')
    label = str(payload.get('label') or '').strip()
    edges = build_normalized_edges(payload)
    family_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}
    target_kind_counts: dict[str, int] = {}
    for edge in edges:
        family = str(edge.get('family') or 'related')
        relation = str(edge.get('relation') or 'related_to')
        target_kind = str(edge.get('target_kind') or 'unknown')
        family_counts[family] = family_counts.get(family, 0) + 1
        relation_counts[relation] = relation_counts.get(relation, 0) + 1
        target_kind_counts[target_kind] = target_kind_counts.get(target_kind, 0) + 1
    reverse = deepcopy(reverse_materialized) if isinstance(reverse_materialized, dict) else {}
    incoming_count = sum(len(values) for values in reverse.values() if isinstance(values, list))
    return {
        'id_policy': {
            'strategy': 'kind_slug_with_collision_suffix',
            'kind_prefix': clean_kind,
            'slug': slug_text(label),
            'stable_id': _clean_id(payload.get('id')),
            'label_basis': label,
            'id_locked': bool(_clean_id(payload.get('id'))),
        },
        'edge_summary': {
            'edge_count': len(edges),
            'by_family': family_counts,
            'by_relation': relation_counts,
            'by_target_kind': target_kind_counts,
            'reverse_edge_count': incoming_count,
        },
        'edges': edges,
    }


def _incoming_from_edges(records: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    incoming: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        for edge in build_normalized_edges(record):
            target_id = _clean_id(edge.get('target_id'))
            if not target_id:
                continue
            reverse_relation = _clean_id(edge.get('reverse_relation')) or 'linked_to_record'
            incoming[target_id][reverse_relation].append({
                'source_id': _clean_id(edge.get('source_id')),
                'source_kind': _clean_id(edge.get('source_kind')),
                'relation': _clean_id(edge.get('relation')),
                'slot': _clean_id(edge.get('slot')),
                'family': _clean_id(edge.get('family')),
                'status': _clean_id(edge.get('status')) or 'active',
            })
    return {target_id: dict(slot_map) for target_id, slot_map in incoming.items()}


def refresh_graph_views(entity_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for path in sorted(entity_dir.glob('*.json')):
        payload = read_json_object(path, None)
        if not isinstance(payload, dict) or payload.get('record_type') != 'entity_record':
            continue
        clean_id = _clean_id(payload.get('id'))
        if not clean_id:
            continue
        records.append(payload)
        paths[clean_id] = path

    incoming = _incoming_from_edges(records)
    writes = 0
    for record in records:
        record_id = _clean_id(record.get('id'))
        reverse_materialized = incoming.get(record_id, {})
        links = normalize_entity_links(record.get('kind') or '', record.get('links'))
        links['reverse_links'] = {
            'strategy': 'derived',
            'materialized': reverse_materialized,
        }
        record['links'] = links
        record['graph'] = build_graph_projection(record, reverse_materialized)
        atomic_write_json(paths[record_id], record)
        writes += 1
    return {
        'ok': True,
        'record_count': len(records),
        'writes': writes,
    }
