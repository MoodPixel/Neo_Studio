from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .config import ROOT_DIR

PHASE0_GOVERNANCE_PATH = ROOT_DIR / 'neo_studio_v1' / 'docs' / 'phase00_governance_map.json'
PHASE1_GOAL_MAP_PATH = ROOT_DIR / 'neo_studio_v1' / 'docs' / 'phase01_generation_goal_map.json'
PHASE1_JOURNEYS_MD_PATH = ROOT_DIR / 'docs' / 'phases' / 'phase01_canonical_user_journeys.md'
PHASE1_DONE_PATH = ROOT_DIR / 'docs' / 'phases' / 'phase01_done_checklist.md'

REQUIRED_JOURNEY_FIELDS = {
    'label',
    'owner_surface',
    'entry_points',
    'summary',
    'required_inputs',
    'optional_inputs',
    'primary_sections',
    'secondary_sections',
    'hidden_by_default',
    'success_output',
    'next_journeys',
}


@dataclass
class AuditResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


EXPECTED_JOURNEYS = {
    'create_from_scratch',
    'match_reference',
    'fix_image_region',
    'remove_object_or_background',
    'finalize_and_upscale',
    'recover_from_previous_output',
}


def run_phase1_journey_audit(project_root: Path | None = None) -> AuditResult:
    root = Path(project_root).resolve() if project_root else ROOT_DIR
    result = AuditResult()

    phase0_path = root / 'neo_studio_v1' / 'docs' / 'phase00_governance_map.json'
    phase1_json_path = root / 'neo_studio_v1' / 'docs' / 'phase01_generation_goal_map.json'
    phase1_md_path = root / 'docs' / 'phases' / 'phase01_canonical_user_journeys.md'
    phase1_done_path = root / 'docs' / 'phases' / 'phase01_done_checklist.md'

    for required in (phase0_path, phase1_json_path, phase1_md_path, phase1_done_path):
        if not required.exists():
            result.errors.append(f'Missing required Phase 1 artifact: {required.relative_to(root).as_posix()}')

    if result.errors:
        return result

    try:
        phase0 = json.loads(phase0_path.read_text(encoding='utf-8'))
    except Exception as exc:
        result.errors.append(f'Could not parse Phase 0 governance map: {exc}')
        return result

    try:
        phase1 = json.loads(phase1_json_path.read_text(encoding='utf-8'))
    except Exception as exc:
        result.errors.append(f'Could not parse Phase 1 goal map: {exc}')
        return result

    surfaces = set((phase0.get('surface_ownership') or {}).keys())
    governed_section_map = phase0.get('generation_sections') or {}
    governed_sections = set(governed_section_map.keys())
    journeys = phase1.get('journeys') or {}

    if not journeys:
        result.errors.append('Phase 1 goal map is missing journeys.')
        return result

    missing_expected = sorted(EXPECTED_JOURNEYS - set(journeys.keys()))
    for key in missing_expected:
        result.errors.append(f'Canonical journey missing from goal map: {key}')

    unexpected = sorted(set(journeys.keys()) - EXPECTED_JOURNEYS)
    for key in unexpected:
        result.warnings.append(f'Goal map includes an extra journey not in the canonical set: {key}')

    section_usage: dict[str, list[str]] = {}

    for journey_id, payload in journeys.items():
        missing_fields = sorted(REQUIRED_JOURNEY_FIELDS - set((payload or {}).keys()))
        if missing_fields:
            result.errors.append(f'Journey {journey_id} is missing fields: {", ".join(missing_fields)}')
            continue

        owner_surface = str(payload.get('owner_surface') or '').strip()
        if owner_surface not in surfaces:
            result.errors.append(f'Journey {journey_id} points to unknown owner surface: {owner_surface}')

        entry_points = payload.get('entry_points') or []
        if not isinstance(entry_points, list) or not entry_points:
            result.errors.append(f'Journey {journey_id} must declare at least one entry point.')
        else:
            for entry in entry_points:
                if entry not in surfaces:
                    result.errors.append(f'Journey {journey_id} references unknown entry surface: {entry}')

        primary_sections = payload.get('primary_sections') or []
        secondary_sections = payload.get('secondary_sections') or []
        hidden_sections = payload.get('hidden_by_default') or []

        if not primary_sections:
            result.errors.append(f'Journey {journey_id} must declare at least one primary section.')

        for section_id in list(primary_sections) + list(secondary_sections) + list(hidden_sections):
            if section_id not in governed_sections:
                result.errors.append(f'Journey {journey_id} references unknown governed section: {section_id}')

        for section_id in list(primary_sections) + list(secondary_sections):
            if section_id in governed_sections:
                section_usage.setdefault(section_id, []).append(journey_id)

        next_journeys = payload.get('next_journeys') or []
        for next_id in next_journeys:
            if next_id not in journeys and next_id not in EXPECTED_JOURNEYS:
                result.errors.append(f'Journey {journey_id} references unknown next journey: {next_id}')

    unused_sections = sorted(
        section_id
        for section_id in governed_sections - set(section_usage.keys())
        if str((governed_section_map.get(section_id) or {}).get('management_mode') or '').strip().lower() != 'support'
    )
    for section_id in unused_sections:
        result.warnings.append(f'Governed Generation section is not assigned to any canonical journey yet: {section_id}')

    heavily_shared_primary = []
    for section_id, owners in section_usage.items():
        unique_owners = sorted(set(owners))
        if len(unique_owners) >= 4:
            heavily_shared_primary.append((section_id, unique_owners))
    for section_id, owners in heavily_shared_primary:
        result.warnings.append(f'Section {section_id} appears across many journeys and may still be too generic: {", ".join(owners)}')

    result.info.append(f'Canonical journeys declared: {len(journeys)}')
    result.info.append(f'Governed Generation sections available from Phase 0: {len(governed_sections)}')
    result.info.append(f'Governed Generation sections referenced by journeys: {len(section_usage)}')
    result.info.append(f'Journey coverage gap count: {len(unused_sections)}')
    return result


__all__ = ['AuditResult', 'run_phase1_journey_audit']
