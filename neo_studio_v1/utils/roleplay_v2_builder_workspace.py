from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..contracts.roleplay_v2_builder_record_contract import build_shared_record_contract
from ..contracts.roleplay_v2_builder_link_contract import build_shared_link_contract
from ..contracts.roleplay_v2_builder_memory_contract import build_shared_memory_hints_contract
from ..contracts.roleplay_v2_hierarchy_contract import build_roleplay_v2_authoring_hierarchy_contract, build_roleplay_v2_hierarchy_context
from ..contracts.roleplay_v2_records import build_entity_record, canonical_entity_kind
from .roleplay_v2_graph_normalizer import allocate_entity_id, refresh_graph_views
from .roleplay_v2_builder_normalizer import normalize_builder_payload
from .roleplay_v2_sqlite_store import ensure_roleplay_v2_sqlite_backbone, upsert_rp2_entity_record, fetch_rp2_sqlite_overview, sync_rp2_entities_from_directory
from .logging_utils import get_logger
from .library_constants import DEFAULT_ROOT
from .storage_io import atomic_write_json, read_json_object

logger = get_logger(__name__)

BUILDER_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / 'contracts' / 'builder_templates'
ROLEPLAY_V2_ENTITIES_DIR = DEFAULT_ROOT / 'roleplay_v2' / 'entities'
BUILDER_TEMPLATE_JSON_DIR = BUILDER_TEMPLATE_ROOT / 'json'
BUILDER_TEMPLATE_MD_DIR = BUILDER_TEMPLATE_ROOT / 'md'
BUILDER_IMPLEMENTATION_ORDER = [
    'universe',
    'world',
    'region',
    'city',
    'location',
    'character',
    'organization',
    'artifact',
    'ritual',
    'cycle',
    'creature',
    'legend',
    'scenario',
]
BUILDER_IMPLEMENTATION_STATUS = {
    'universe': 'phase_124a_ready',
    'world': 'phase_124a_ready',
    'region': 'phase_124a_ready',
    'city': 'phase_124b_ready',
    'location': 'phase_124b_ready',
    'character': 'phase_124b_ready',
    'organization': 'phase_124c_ready',
    'artifact': 'phase_124c_ready',
    'ritual': 'phase_124c_ready',
    'cycle': 'phase_124d_ready',
    'creature': 'phase_124d_ready',
    'legend': 'phase_124d_ready',
    'scenario': 'phase_124d_ready',
}



FIRST_IMPLEMENTED_BUILDERS = ('universe', 'world', 'region', 'city', 'location', 'character', 'organization', 'artifact', 'ritual', 'cycle', 'creature', 'legend', 'scenario')
BUILDER_REQUIRED_PATHS = {
    'universe': [
        'label', 'summary', 'fields.identity.universe_type', 'fields.cosmology.cosmology_summary',
        'fields.cosmology.structure_of_existence', 'fields.cosmology.public_origin_story',
        'fields.core_laws.universal_laws', 'fields.core_laws.metaphysical_rules', 'fields.core_laws.time_rules',
        'fields.core_laws.magic_or_power_source_model', 'fields.timeline.timeline_summary',
        'fields.travel.interworld_travel_status', 'fields.truth_layers.public_cosmology',
        'fields.truth_layers.canon_hierarchy_rules',
    ],
    'world': [
        'label', 'summary', 'links.scope.universe_id', 'fields.identity.realm_type', 'fields.identity.world_role',
        'fields.calendar_chronology.calendar_summary', 'fields.calendar_chronology.timeline_summary',
        'fields.geography_environment.macro_geography', 'fields.geography_environment.environmental_identity',
        'fields.governance_law_diplomacy.governance_overview', 'fields.governance_law_diplomacy.law_overview',
        'fields.society_institutions.society_overview', 'fields.faith_magic_craft.faith_and_belief_overview',
        'fields.faith_magic_craft.magic_or_power_overview', 'fields.travel_access_hazards.travel_systems_overview',
        'fields.peoples_species_creatures.people_and_species_overview', 'fields.myths_truths.known_myths_vs_truth',
    ],
    'region': [
        'label', 'summary', 'links.scope.world_id', 'fields.identity.region_type',
        'fields.governance_ruling_power.governance_overview', 'fields.geography_places.regional_geography',
        'fields.travel_access_security.travel_access_overview', 'fields.politics_law_diplomacy.regional_law_overview',
        'fields.politics_law_diplomacy.diplomacy_overview', 'fields.society_culture_education.society_overview',
        'fields.society_culture_education.cultural_identity', 'fields.mythic_hidden_legacy.public_region_story',
    ],
    'city': [
        'label', 'summary', 'links.scope.world_id', 'fields.identity.settlement_type', 'fields.governance_control.governance_overview',
        'fields.layout_districts.layout_overview', 'fields.access_safety_restrictions.access_notes',
        'fields.society_local_culture.society_overview', 'fields.society_local_culture.local_culture_identity',
        'fields.rumors_truths.public_city_story', 'fields.scene_utility.scene_use_overview',
    ],
    'location': [
        'label', 'summary', 'fields.identity.location_type', 'fields.identity.anchor_type',
        'fields.access_entry.access_notes', 'fields.spatial_layout.layout_overview', 'fields.atmosphere_sensory.atmosphere',
        'fields.rules_behavior_logic.rules_overview', 'fields.hazards_pressure.hazards_overview',
        'fields.public_hidden_truth.public_notes', 'fields.scene_utility.scene_uses',
    ],
    'character': [
        'label', 'summary', 'fields.appearance_presence.appearance_summary', 'fields.personality_behavior_speech.personality_overview',
        'fields.personality_behavior_speech.speech_style', 'fields.goals_desire_fear_wounds.personal_goals',
        'fields.goals_desire_fear_wounds.wounds_fears_triggers', 'fields.story_roleplay_use.story_hooks',
        'fields.story_roleplay_use.scene_use_overview',
    ],
    'organization': [
        'label', 'summary', 'fields.identity.group_type', 'fields.leadership_structure.leadership_overview',
        'fields.beliefs_doctrine_mission.core_beliefs', 'fields.beliefs_doctrine_mission.goals',
        'fields.public_hidden_truth.public_face', 'fields.public_hidden_truth.hidden_truth',
        'fields.membership_recruitment.membership_rules', 'fields.resources_assets_territory.resources_overview',
        'fields.story_roleplay_use.scene_use_overview',
    ],
    'artifact': [
        'label', 'summary', 'fields.identity.artifact_type', 'fields.classification_state.rarity',
        'fields.classification_state.state', 'fields.appearance_presence.appearance_summary',
        'fields.function_effects_use.effects', 'fields.function_effects_use.activation',
        'fields.function_effects_use.costs', 'fields.law_safety_restriction.lawful_status',
        'fields.public_hidden_truth.public_story', 'fields.scene_utility.scene_use_overview',
    ],
    'ritual': [
        'label', 'summary', 'fields.identity.practice_type', 'fields.classification_school_state.state',
        'fields.function_effects.effect_summary', 'fields.requirements_conditions.requirements',
        'fields.activation_procedure.activation', 'fields.risks_costs_consequences.risks',
        'fields.law_ethics_restriction.lawful_status', 'fields.public_hidden_truth.public_story',
        'fields.scene_utility.scene_use_overview',
    ],
    'cycle': [
        'label', 'summary', 'fields.identity.system_type', 'fields.scope_reach.scope_type',
        'fields.trigger_cadence_onset.trigger', 'fields.trigger_cadence_onset.cadence',
        'fields.effects_outcomes.effects', 'fields.safeguards_resistance_management.safeguards',
        'fields.public_hidden_truth.public_story', 'fields.scene_utility.scene_use_overview',
    ],
    'creature': [
        'label', 'summary', 'fields.identity.category', 'fields.sentience_social_pattern.sentience',
        'fields.physicality_appearance_presence.appearance_summary', 'fields.diet_behavior_instinct.diet_and_behavior',
        'fields.danger_threat_utility.danger_level', 'fields.public_hidden_truth.public_story',
        'fields.role_in_world_society_scene.world_role_notes', 'fields.role_in_world_society_scene.scene_use_overview',
    ],
    'legend': [
        'label', 'summary', 'fields.identity.legend_type', 'fields.identity.truth_status',
        'fields.scope_placement_anchor.scope_type', 'fields.public_hidden_versions.public_version',
        'fields.public_hidden_versions.hidden_version', 'fields.consequences_stakes.consequences_if_true',
        'fields.scene_utility.scene_use_overview',
    ],
    'scenario': [
        'label', 'summary', 'fields.premise_objective_stakes.premise', 'fields.premise_objective_stakes.objective',
        'fields.opening_state_trigger_beat.opening_beat', 'fields.tone_emotional_logic_pressure.emotional_tone_overview',
        'fields.scene_runtime_use.scene_use_overview',
    ],
}


def _value_at_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in str(path or '').split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _link_target_kinds(slot: str) -> list[str]:
    clean = str(slot or '').strip().lower()
    if not clean or clean == 'source_container_id':
        return []
    if clean.endswith('_ids'):
        clean = clean[:-4]
    elif clean.endswith('_id'):
        clean = clean[:-3]
    for prefix in ('origin_', 'current_', 'featured_', 'source_', 'cast_', 'linked_', 'focus_', 'primary_', 'base_', 'seat_', 'member_', 'leader_', 'ally_', 'rival_', 'anchor_'):
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


def _inspect_link_value(slot: str, value: Any) -> dict[str, Any] | None:
    clean_value = str(value or '').strip()
    if not clean_value:
        return None
    target_path = ROLEPLAY_V2_ENTITIES_DIR / f'{clean_value}.json'
    if not target_path.exists():
        return {
            'slot': slot,
            'value': clean_value,
            'status': 'unresolved_text',
            'target_kinds': _link_target_kinds(slot),
            'message': 'No saved builder record exists for this linked value.',
        }
    payload = read_json_object(target_path, None)
    if not isinstance(payload, dict) or payload.get('record_type') != 'entity_record':
        return {
            'slot': slot,
            'value': clean_value,
            'status': 'unresolved_text',
            'target_kinds': _link_target_kinds(slot),
            'message': 'Linked record file exists but is not a valid entity record.',
        }
    record_status = str(payload.get('meta', {}).get('status') or 'draft').strip().lower()
    if record_status == 'draft_stub':
        return {
            'slot': slot,
            'value': clean_value,
            'status': 'stub',
            'target_kinds': _link_target_kinds(slot),
            'message': 'Linked target is still a draft stub.',
        }
    return None


def _collect_link_issues(links: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    raw = links if isinstance(links, dict) else {}
    issues: list[dict[str, Any]] = []
    candidates: list[tuple[str, Any]] = []
    if isinstance(raw.get('scope'), dict):
        candidates.extend((slot, value) for slot, value in raw.get('scope', {}).items())
    if isinstance(raw.get('related'), dict):
        candidates.extend((slot, value) for slot, value in raw.get('related', {}).items())
    if not candidates:
        candidates.extend((slot, value) for slot, value in raw.items() if slot not in {'reverse_links', 'source_container_id'})
    for slot, value in candidates:
        if isinstance(value, list):
            for item in value:
                issue = _inspect_link_value(slot, item)
                if issue:
                    issues.append(issue)
        else:
            issue = _inspect_link_value(slot, value)
            if issue:
                issues.append(issue)
    return issues


def validate_builder_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    required_paths = list(BUILDER_REQUIRED_PATHS.get(clean_kind) or [])
    missing = [path for path in required_paths if _is_blank(_value_at_path(payload, path))]
    links = payload.get('links') if isinstance(payload.get('links'), dict) else {}
    link_issues = _collect_link_issues(links)
    status_value = str((payload.get('meta') or {}).get('status') or 'draft').strip().lower()
    blocking_statuses = {'approved', 'runtime_ready'}
    should_block = status_value in blocking_statuses and (missing or link_issues)
    severity = 'ok'
    if should_block:
        severity = 'error'
    elif missing or link_issues:
        severity = 'warning' if status_value in {'draft', 'draft_stub'} else 'warning'
    return {
        'ok': not should_block,
        'severity': severity,
        'record_status': status_value,
        'required_paths': required_paths,
        'missing_paths': missing,
        'link_issues': link_issues,
        'warning_count': len(missing) + len(link_issues),
        'approval_ready': not missing and not link_issues,
        'should_block_save': should_block,
        'status_rule': (
            'draft_soft' if status_value in {'draft', 'draft_stub'} else
            'review_warning' if status_value == 'reviewed' else
            'approval_hard_stop' if status_value in blocking_statuses else
            'general_warning'
        ),
    }




def _flatten_links(links: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = links if isinstance(links, dict) else {}
    flat: dict[str, Any] = {}
    if isinstance(raw.get('scope'), dict):
        flat.update({key: value for key, value in raw.get('scope', {}).items()})
    if isinstance(raw.get('related'), dict):
        flat.update({key: list(value or []) for key, value in raw.get('related', {}).items()})
    if raw.get('source_container_id'):
        flat['source_container_id'] = raw.get('source_container_id')
    for key, value in raw.items():
        if key in {'scope', 'related', 'reverse_links', 'source_container_id'}:
            continue
        flat[key] = value
    return flat

def build_builder_payload_from_record(record: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = record if isinstance(record, dict) else {}
    return {
        'id': raw.get('id') or '',
        'kind': raw.get('kind') or '',
        'schema_version': 1,
        'source_container_id': raw.get('links', {}).get('source_container_id') or '',
        'label': raw.get('label') or '',
        'display_label': raw.get('display_label') or '',
        'summary': raw.get('summary') or '',
        'canon_status': raw.get('canon_status') or 'primary_canon',
        'visibility': raw.get('visibility') or 'author_private',
        'tags': list(raw.get('tags') or []),
        'tone_tags': list(raw.get('tone_tags') or []),
        'links': deepcopy(raw.get('links')) if isinstance(raw.get('links'), dict) else {},
        'fields': raw.get('fields') if isinstance(raw.get('fields'), dict) else {},
        'memory_hints': raw.get('memory_hints') if isinstance(raw.get('memory_hints'), dict) else {},
        'meta': raw.get('meta') if isinstance(raw.get('meta'), dict) else {},
    }


def list_builder_records(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    items: list[dict[str, Any]] = []
    hierarchy_entry = build_roleplay_v2_authoring_hierarchy_contract().get('kinds', {}).get(clean_kind, {})
    subcategory = hierarchy_entry.get('subcategory') if isinstance(hierarchy_entry, dict) else None
    subcategory_path = str(subcategory.get('field_path') or '').strip() if isinstance(subcategory, dict) else ''
    for path in sorted(ROLEPLAY_V2_ENTITIES_DIR.glob('*.json')):
        payload = read_json_object(path, None)
        if not isinstance(payload, dict) or payload.get('record_type') != 'entity_record':
            continue
        if canonical_entity_kind(payload.get('kind') or '') != clean_kind:
            continue
        graph = payload.get('graph') if isinstance(payload.get('graph'), dict) else {}
        edge_summary = graph.get('edge_summary') if isinstance(graph.get('edge_summary'), dict) else {}
        id_policy = graph.get('id_policy') if isinstance(graph.get('id_policy'), dict) else {}
        links = payload.get('links') if isinstance(payload.get('links'), dict) else {}
        scope_values = links.get('scope') if isinstance(links.get('scope'), dict) else {}
        items.append({
            'id': payload.get('id') or '',
            'kind': payload.get('kind') or '',
            'label': payload.get('label') or '',
            'display_label': payload.get('display_label') or '',
            'summary': payload.get('summary') or '',
            'status': payload.get('meta', {}).get('status') or 'draft',
            'path': str(path),
            'edge_count': int(edge_summary.get('edge_count') or 0),
            'reverse_edge_count': int(edge_summary.get('reverse_edge_count') or 0),
            'id_strategy': id_policy.get('strategy') or '',
            'scope_values': deepcopy(scope_values),
            'subcategory_field_path': subcategory_path,
            'subcategory_value': _value_at_path(payload, subcategory_path) if subcategory_path else '',
        })
    return {
        'ok': True,
        'kind': clean_kind,
        'records': items,
    }


def load_builder_record(record_id: str) -> dict[str, Any]:
    clean_id = str(record_id or '').strip()
    if not clean_id:
        raise ValueError('record_id is required.')
    path = ROLEPLAY_V2_ENTITIES_DIR / f'{clean_id}.json'
    payload = read_json_object(path, None)
    if not isinstance(payload, dict):
        raise ValueError('Builder record not found.')
    builder_payload = build_builder_payload_from_record(payload)
    normalized = normalize_builder_payload(kind=payload.get('kind') or clean_id.split('_', 1)[0], payload=builder_payload)
    builder_payload = normalized.get('normalized_payload') or builder_payload
    validation = validate_builder_payload(builder_payload.get('kind') or '', builder_payload)
    sqlite_sync = upsert_rp2_entity_record(record=payload, source_json_path=str(path))
    sqlite_overview = fetch_rp2_sqlite_overview()
    return {
        'ok': True,
        'record': payload,
        'builder_payload': builder_payload,
        'validation': validation,
        'normalization': normalized.get('normalization') or {},
        'sqlite_sync': sqlite_sync,
        'sqlite_overview': sqlite_overview,
        'path': str(path),
        'hierarchy_context': build_roleplay_v2_hierarchy_context(payload.get('kind') or clean_id.split('_', 1)[0], builder_payload),
    }


def save_builder_record(*, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    if clean_kind not in FIRST_IMPLEMENTED_BUILDERS:
        raise ValueError('This builder is not in the first implemented slice yet.')
    raw_payload = payload if isinstance(payload, dict) else {}
    normalized = normalize_builder_payload(kind=clean_kind, payload=raw_payload)
    clean_payload = normalized.get('normalized_payload') or {}
    label = str(clean_payload.get('label') or '').strip()
    if not label:
        raise ValueError('label is required.')
    links = clean_payload.get('links') if isinstance(clean_payload.get('links'), dict) else {}
    fields = clean_payload.get('fields') if isinstance(clean_payload.get('fields'), dict) else {}
    memory_hints = clean_payload.get('memory_hints') if isinstance(clean_payload.get('memory_hints'), dict) else {}
    data = {
        'display_label': clean_payload.get('display_label') or '',
        'summary': clean_payload.get('summary') or '',
        'canon_status': clean_payload.get('canon_status') or 'primary_canon',
        'visibility': clean_payload.get('visibility') or 'author_private',
        'tags': clean_payload.get('tags') or [],
        'tone_tags': clean_payload.get('tone_tags') or [],
        'fields': fields,
        'memory_hints': memory_hints,
    }
    entity_id = allocate_entity_id(
        kind=clean_kind,
        label=label,
        entities_dir=ROLEPLAY_V2_ENTITIES_DIR,
        provided_id=clean_payload.get('id') or '',
    )
    record = build_entity_record(
        kind=clean_kind,
        label=label,
        entity_id=entity_id,
        data=data,
        links=links,
        meta=clean_payload.get('meta') if isinstance(clean_payload.get('meta'), dict) else {'status': 'draft'},
    )
    record['normalization'] = normalized.get('normalization') or {}
    path = ROLEPLAY_V2_ENTITIES_DIR / f'{record["id"]}.json'
    atomic_write_json(path, record)
    refresh_graph_views(ROLEPLAY_V2_ENTITIES_DIR)
    record = read_json_object(path, record)
    sqlite_sync = upsert_rp2_entity_record(record=record, source_json_path=str(path))
    sqlite_overview = fetch_rp2_sqlite_overview()
    builder_payload = build_builder_payload_from_record(record)
    validation = validate_builder_payload(clean_kind, builder_payload)
    if validation.get('should_block_save'):
        missing_text = ', '.join(validation.get('missing_paths') or [])
        link_text = ', '.join(f"{issue.get('slot')}: {issue.get('value')} ({issue.get('status')})" for issue in (validation.get('link_issues') or []))
        problems = '; '.join(part for part in [f"missing required paths: {missing_text}" if missing_text else '', f"link issues: {link_text}" if link_text else ''] if part)
        raise ValueError(f"Cannot save {clean_kind} as {validation.get('record_status')} until validation issues are cleared: {problems}.")
    return {
        'ok': True,
        'record': record,
        'builder_payload': builder_payload,
        'validation': validation,
        'normalization': normalized.get('normalization') or {},
        'sqlite_sync': sqlite_sync,
        'sqlite_overview': sqlite_overview,
        'path': str(path),
        'hierarchy_context': build_roleplay_v2_hierarchy_context(clean_kind, builder_payload),
    }



def delete_builder_record(record_id: str) -> dict[str, Any]:
    clean_id = str(record_id or '').strip()
    if not clean_id:
        raise ValueError('record_id is required.')
    path = ROLEPLAY_V2_ENTITIES_DIR / f'{clean_id}.json'
    payload = read_json_object(path, None)
    if not isinstance(payload, dict) or payload.get('record_type') != 'entity_record':
        raise ValueError('Builder record not found.')
    deleted = {
        'id': clean_id,
        'kind': canonical_entity_kind(payload.get('kind') or clean_id.split('_', 1)[0]),
        'label': str(payload.get('label') or payload.get('display_label') or clean_id).strip(),
        'path': str(path),
    }
    try:
        path.unlink()
    except FileNotFoundError:
        raise ValueError('Builder record not found.')
    refresh_graph_views(ROLEPLAY_V2_ENTITIES_DIR)
    sqlite_sync = sync_rp2_entities_from_directory(entities_dir=ROLEPLAY_V2_ENTITIES_DIR, prune_missing=True)
    sqlite_overview = fetch_rp2_sqlite_overview()
    return {
        'ok': True,
        'deleted': deleted,
        'sqlite_sync': sqlite_sync,
        'sqlite_overview': sqlite_overview,
    }

def _template_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return ''


def list_builder_templates() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for kind in BUILDER_IMPLEMENTATION_ORDER:
        json_path = BUILDER_TEMPLATE_JSON_DIR / f'{kind}.template.json'
        md_path = BUILDER_TEMPLATE_MD_DIR / f'{kind}.template.md'
        items.append({
            'kind': kind,
            'hierarchy_entry': build_roleplay_v2_hierarchy_context(kind, {}),
            'json_template_path': str(json_path),
            'md_template_path': str(md_path),
            'has_json_template': json_path.exists(),
            'has_md_template': md_path.exists(),
            'implementation_status': BUILDER_IMPLEMENTATION_STATUS.get(kind, 'planned'),
        })
    return items


def get_builder_template_payload(kind: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    json_path = BUILDER_TEMPLATE_JSON_DIR / f'{clean_kind}.template.json'
    md_path = BUILDER_TEMPLATE_MD_DIR / f'{clean_kind}.template.md'
    json_text = _template_text(json_path)
    md_text = _template_text(md_path)
    json_payload = None
    if json_text:
        try:
            json_payload = json.loads(json_text)
        except Exception:
            json_payload = None
    return {
        'kind': clean_kind,
        'hierarchy_entry': build_roleplay_v2_hierarchy_context(clean_kind, json_payload if isinstance(json_payload, dict) else {}),
        'json_template_path': str(json_path),
        'md_template_path': str(md_path),
        'json_template_text': json_text,
        'md_template_text': md_text,
        'json_template_payload': json_payload,
        'implementation_status': BUILDER_IMPLEMENTATION_STATUS.get(clean_kind, 'planned'),
    }


def get_builder_forge_state() -> dict[str, Any]:
    sqlite_path = ensure_roleplay_v2_sqlite_backbone()
    sqlite_overview = fetch_rp2_sqlite_overview()
    records_by_kind = {
        kind: list_builder_records(kind).get('records') or []
        for kind in FIRST_IMPLEMENTED_BUILDERS
    }
    return {
        'ok': True,
        'implementation_phase': 'phase_123b_124a',
        'sqlite_backbone': {
            'db_path': str(sqlite_path),
            'overview': sqlite_overview,
        },
        'shared_contracts': {
            'record': build_shared_record_contract(),
            'links': build_shared_link_contract(),
            'memory_hints': build_shared_memory_hints_contract(),
        },
        'builders': list_builder_templates(),
        'authoring_hierarchy': build_roleplay_v2_authoring_hierarchy_contract(),
        'records_by_kind': records_by_kind,
        'record_counts': {kind: len(records) for kind, records in records_by_kind.items()},
        'templates': {
            kind: get_builder_template_payload(kind)
            for kind in FIRST_IMPLEMENTED_BUILDERS
        },
        'notes': {
            'forge_status': 'shared_shell_and_first_three_templates_ready',
            'implemented_builders': list(FIRST_IMPLEMENTED_BUILDERS),
            'stub_policy': 'prefer_real_draft_stub_records_over_unresolved_text',
            'json_md_rule': 'both_normalize_to_same_saved_builder_record',
            'hierarchy_rule': 'authoring_scope_contract_locked_for_universe_world_region_city_location_people_orgs_arcana_and_story_seeds',
        },
    }


def create_entity_stub(*, kind: str, label: str, source_container_id: str = '', payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    clean_label = str(label or '').strip()
    if not clean_label:
        raise ValueError('Label is required for stub creation.')
    proposed_id = allocate_entity_id(kind=clean_kind, label=clean_label, entities_dir=ROLEPLAY_V2_ENTITIES_DIR)
    target = ROLEPLAY_V2_ENTITIES_DIR / f'{proposed_id}.json'
    seed_payload = _deep_merge_template({
        'id': proposed_id,
        'kind': clean_kind,
        'label': clean_label,
        'source_container_id': source_container_id,
        'meta': {'status': 'draft_stub'},
    }, payload if isinstance(payload, dict) else {})
    seed_payload['id'] = proposed_id
    seed_payload['kind'] = clean_kind
    seed_payload['label'] = clean_label
    if source_container_id and not str(seed_payload.get('source_container_id') or '').strip():
        seed_payload['source_container_id'] = source_container_id
    if not isinstance(seed_payload.get('meta'), dict):
        seed_payload['meta'] = {'status': 'draft_stub'}
    elif not str(seed_payload['meta'].get('status') or '').strip():
        seed_payload['meta']['status'] = 'draft_stub'
    normalized = normalize_builder_payload(kind=clean_kind, payload=seed_payload)
    clean_payload = normalized.get('normalized_payload') or {}
    record = build_entity_record(
        kind=clean_kind,
        label=clean_label,
        entity_id=proposed_id,
        data={
            'display_label': clean_payload.get('display_label') or '',
            'summary': clean_payload.get('summary') or '',
            'canon_status': clean_payload.get('canon_status') or 'primary_canon',
            'visibility': clean_payload.get('visibility') or 'author_private',
            'tags': clean_payload.get('tags') or [],
            'tone_tags': clean_payload.get('tone_tags') or [],
            'fields': clean_payload.get('fields') if isinstance(clean_payload.get('fields'), dict) else {},
            'memory_hints': clean_payload.get('memory_hints') if isinstance(clean_payload.get('memory_hints'), dict) else {},
        },
        links=clean_payload.get('links') if isinstance(clean_payload.get('links'), dict) else {'source_container_id': source_container_id},
        meta=clean_payload.get('meta') if isinstance(clean_payload.get('meta'), dict) else {'status': 'draft_stub'},
    )
    record['normalization'] = normalized.get('normalization') or {}
    atomic_write_json(target, record)
    refresh_graph_views(ROLEPLAY_V2_ENTITIES_DIR)
    record = read_json_object(target, record)
    sqlite_sync = upsert_rp2_entity_record(record=record, source_json_path=str(target))
    sqlite_overview = fetch_rp2_sqlite_overview()
    logger.info('Created roleplay V2 %s stub at %s', clean_kind, target)
    return {
        'ok': True,
        'record': record,
        'sqlite_sync': sqlite_sync,
        'sqlite_overview': sqlite_overview,
        'path': str(target),
    }



def _deep_merge_template(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = {key: _deep_merge_template(base.get(key), patch.get(key)) if key in patch else deepcopy(value) for key, value in base.items()}
        for key, value in patch.items():
            if key not in merged:
                merged[key] = deepcopy(value)
        return merged
    if isinstance(base, list) and isinstance(patch, list):
        return deepcopy(patch)
    return deepcopy(patch) if patch is not None else deepcopy(base)


def _pretty_label_python(value: str) -> str:
    text = str(value or '').replace('_', ' ').strip()
    parts = []
    for word in text.split():
        lower = word.lower()
        if lower == 'id':
            parts.append('ID')
        elif lower == 'ids':
            parts.append('IDs')
        elif lower == 'md':
            parts.append('MD')
        elif lower == 'json':
            parts.append('JSON')
        else:
            parts.append(lower[:1].upper() + lower[1:])
    return ' '.join(parts)


def _section_field_map(template: dict[str, Any]) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    fields = template.get('fields') if isinstance(template.get('fields'), dict) else {}
    for section_key, section_value in fields.items():
        if not isinstance(section_value, dict):
            continue
        section_label = _pretty_label_python(section_key)
        mapping[section_label] = {}
        for field_key in section_value.keys():
            mapping[section_label][_pretty_label_python(field_key)] = f'fields.{section_key}.{field_key}'
    return mapping


def _coerce_markdown_value(raw: str) -> Any:
    value = str(raw or '').strip()
    if not value:
        return ''
    lower = value.lower()
    if lower in {'true', 'false'}:
        return lower == 'true'
    if value.isdigit():
        try:
            return int(value)
        except Exception:
            return value
    return value


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in str(path or '').split('.') if part]
    cursor: Any = target
    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        if is_last:
            cursor[part] = value
            return
        if part not in cursor or not isinstance(cursor.get(part), dict):
            cursor[part] = {}
        cursor = cursor[part]


def _normalize_markdown_payload(kind: str, payload_text: str, template: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(template)
    section_map = _section_field_map(template)
    current_section = 'Metadata'
    pending_path = ''
    pending_list: list[str] = []
    metadata_map = {
        'Name': 'label',
        'Title': 'label',
        'Display Name': 'display_label',
        'Display Title': 'display_label',
        'Summary': 'summary',
        'Canon Status': 'canon_status',
        'Visibility': 'visibility',
        'Tags': 'tags',
        'Tone Tags': 'tone_tags',
        'Source Container ID': 'source_container_id',
        'Slug': 'slug',
    }
    raw_links = template.get('links') if isinstance(template.get('links'), dict) else {}
    links_map: dict[str, str] = {}
    if isinstance(raw_links.get('scope'), dict):
        links_map.update({_pretty_label_python(key): f'links.scope.{key}' for key in raw_links.get('scope', {}).keys()})
    if isinstance(raw_links.get('related'), dict):
        links_map.update({_pretty_label_python(key): f'links.related.{key}' for key in raw_links.get('related', {}).keys()})
    if not links_map:
        links_map = {_pretty_label_python(key): f'links.{key}' for key in raw_links.keys()}

    def flush_pending() -> None:
        nonlocal pending_path, pending_list
        if not pending_path:
            return
        value: Any = [item for item in pending_list if str(item).strip()]
        if len(value) == 1:
            value = value[0]
        elif not value:
            value = ''
        _set_path(result, pending_path, value)
        pending_path = ''
        pending_list = []

    for raw_line in str(payload_text or '').splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('# '):
            continue
        if stripped.startswith('## '):
            flush_pending()
            current_section = stripped[3:].strip()
            continue
        if stripped.startswith('### '):
            flush_pending()
            continue
        if pending_path and stripped.startswith('- '):
            pending_list.append(stripped[2:].strip())
            continue
        if ':' in stripped:
            flush_pending()
            field_label, raw_value = stripped.split(':', 1)
            field_label = field_label.strip()
            value = raw_value.strip()
            path = ''
            if current_section == 'Metadata':
                path = metadata_map.get(field_label, '')
            elif current_section == 'Links':
                path = links_map.get(field_label, '')
            else:
                path = section_map.get(current_section, {}).get(field_label, '')
            if not path:
                continue
            if value:
                _set_path(result, path, _coerce_markdown_value(value))
            else:
                pending_path = path
                pending_list = []
    flush_pending()
    if isinstance(result.get('tags'), str):
        result['tags'] = [chunk.strip() for chunk in result['tags'].split(',') if chunk.strip()]
    if isinstance(result.get('tone_tags'), str):
        result['tone_tags'] = [chunk.strip() for chunk in result['tone_tags'].split(',') if chunk.strip()]
    return result


def normalize_import_payload(*, kind: str, import_format: str, payload_text: str) -> dict[str, Any]:
    clean_kind = canonical_entity_kind(kind)
    fmt = str(import_format or '').strip().lower()
    template_payload = deepcopy(get_builder_template_payload(clean_kind).get('json_template_payload') or {})
    if not template_payload:
        raise ValueError('Template payload is not available for this builder yet.')
    if fmt == 'json':
        parsed = json.loads(payload_text or '{}')
        if not isinstance(parsed, dict):
            raise ValueError('JSON import must be an object payload.')
        if not any(key in parsed for key in ('links', 'fields', 'memory_hints', 'label', 'summary')):
            parsed = {'fields': parsed}
        normalized_result = normalize_builder_payload(kind=clean_kind, payload=parsed)
        normalized = normalized_result.get('normalized_payload') or template_payload
    elif fmt in {'md', 'markdown'}:
        markdown_payload = _normalize_markdown_payload(clean_kind, payload_text, template_payload)
        normalized_result = normalize_builder_payload(kind=clean_kind, payload=markdown_payload)
        normalized = normalized_result.get('normalized_payload') or template_payload
    else:
        raise ValueError('Unsupported import format.')
    normalized['kind'] = clean_kind
    validation = validate_builder_payload(clean_kind, normalized)
    return {
        'ok': True,
        'kind': clean_kind,
        'normalized_payload': normalized,
        'validation': validation,
        'normalization': normalized_result.get('normalization') or {},
    }


def get_builder_library_state() -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    visible_statuses = {'runtime_ready'}
    for kind in FIRST_IMPLEMENTED_BUILDERS:
        records = list_builder_records(kind).get('records') or []
        filtered = [
            record for record in records
            if str(record.get('status') or '').strip().lower() in visible_statuses
        ]
        groups[kind] = filtered
        counts[kind] = len(filtered)
    return {
        'ok': True,
        'groups': groups,
        'counts': counts,
        'implemented_builders': list(FIRST_IMPLEMENTED_BUILDERS),
        'visible_statuses': sorted(visible_statuses),
    }


