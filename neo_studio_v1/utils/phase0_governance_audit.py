from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .config import ROOT_DIR

DOCS_DIR = ROOT_DIR / 'neo_studio_v1' / 'docs'
TEMPLATE_PATH = ROOT_DIR / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
REGISTRY_PATH = ROOT_DIR / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_registry.js'
GOVERNANCE_PATH = DOCS_DIR / 'phase00_governance_map.json'


@dataclass
class AuditResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


REQUIRED_SECTION_FIELDS = {
    'title',
    'source',
    'owner_surface',
    'user_goal',
    'management_mode',
    'level',
    'owner_module_hint',
    'registry_expected',
}


def _extract_generate_section_ids(template_text: str) -> list[str]:
    match = re.search(r'<section\b[^>]*\bid=["\']tab-generate["\'][^>]*>(.*?)</section>', template_text, flags=re.DOTALL)
    if not match:
        return []
    block = match.group(0)
    return sorted(set(re.findall(r'data-accordion-id="([^"]+)"', block)))


def _extract_registry_ids(registry_text: str) -> list[str]:
    return sorted(set(re.findall(r"\bid:\s*'([^']+)'", registry_text)))


def run_phase0_governance_audit(project_root: Path | None = None) -> AuditResult:
    root = Path(project_root).resolve() if project_root else ROOT_DIR
    docs_dir = root / 'neo_studio_v1' / 'docs'
    template_path = root / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
    registry_path = root / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_registry.js'
    governance_path = docs_dir / 'phase00_governance_map.json'

    result = AuditResult()

    if not governance_path.exists():
        result.errors.append(f'Missing governance map: {governance_path.relative_to(root).as_posix()}')
        return result

    try:
        governance = json.loads(governance_path.read_text(encoding='utf-8'))
    except Exception as exc:
        result.errors.append(f'Could not parse governance map: {exc}')
        return result

    required_docs = governance.get('required_docs') or []
    if not required_docs:
        result.errors.append('Governance map is missing required_docs.')

    for rel in required_docs:
        if not (root / rel).exists():
            result.errors.append(f'Missing required Phase 0 document: {rel}')

    surfaces = governance.get('surface_ownership') or {}
    entities = governance.get('entity_ownership') or {}
    sections = governance.get('generation_sections') or {}

    if not surfaces:
        result.errors.append('Governance map is missing surface_ownership.')
    if not entities:
        result.errors.append('Governance map is missing entity_ownership.')
    if not sections:
        result.errors.append('Governance map is missing generation_sections.')

    surface_keys = set(surfaces.keys())
    for entity_name, payload in entities.items():
        owner_surface = str((payload or {}).get('owner_surface') or '').strip()
        if not owner_surface:
            result.errors.append(f'Entity ownership missing owner_surface: {entity_name}')
        elif owner_surface not in surface_keys:
            result.errors.append(f'Entity ownership points to unknown surface: {entity_name} -> {owner_surface}')

    for section_id, payload in sections.items():
        missing = sorted(REQUIRED_SECTION_FIELDS - set((payload or {}).keys()))
        if missing:
            result.errors.append(f'Generation section governance missing fields for {section_id}: {", ".join(missing)}')
            continue
        owner_surface = str(payload.get('owner_surface') or '').strip()
        if owner_surface not in surface_keys:
            result.errors.append(f'Generation section points to unknown surface: {section_id} -> {owner_surface}')

    if template_path.exists():
        template_ids = _extract_generate_section_ids(template_path.read_text(encoding='utf-8'))
    else:
        template_ids = []
        result.errors.append(f'Missing template: {template_path.relative_to(root).as_posix()}')

    if registry_path.exists():
        registry_ids = _extract_registry_ids(registry_path.read_text(encoding='utf-8'))
    else:
        registry_ids = []
        result.errors.append(f'Missing section registry: {registry_path.relative_to(root).as_posix()}')

    governance_ids = set(sections.keys())
    template_id_set = set(template_ids)
    registry_id_set = set(registry_ids)

    missing_governance_for_template = sorted(template_id_set - governance_ids)
    for section_id in missing_governance_for_template:
        result.errors.append(f'Template Generation accordion is missing governance ownership: {section_id}')

    unreferenced_governance = sorted(governance_ids - template_id_set - {
        'generation-workflow-wrap',
        'generation-output-settings-wrap',
        'generation-reliability-wrap',
        'generation-smart-wrap',
        'generation-power-wrap',
    })
    for section_id in unreferenced_governance:
        result.warnings.append(f'Governance map contains a Generation section not found in the template: {section_id}')

    for section_id, payload in sections.items():
        if bool(payload.get('registry_expected')) and section_id not in registry_id_set:
            result.warnings.append(f'Section is marked registry_expected but is not in generation_section_registry.js: {section_id}')

    template_missing_from_registry = sorted(template_id_set - registry_id_set)
    if template_missing_from_registry:
        result.info.append(
            'Template Generation accordions not yet represented in generation_section_registry.js: '
            + ', '.join(template_missing_from_registry)
        )

    result.info.append(f'Surfaces declared: {len(surface_keys)}')
    result.info.append(f'Entities declared: {len(entities)}')
    result.info.append(f'Governed Generation sections: {len(sections)}')
    result.info.append(f'Generation template accordions found: {len(template_ids)}')
    result.info.append(f'Generation registry entries found: {len(registry_ids)}')
    return result


__all__ = ['AuditResult', 'run_phase0_governance_audit']
