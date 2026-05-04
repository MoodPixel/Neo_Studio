from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .config import ROOT_DIR

TEMPLATE_PATH = ROOT_DIR / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
REGISTRY_PATH = ROOT_DIR / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_registry.js'
CONTRACT_RUNTIME_PATH = ROOT_DIR / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_contracts.js'


@dataclass
class AuditResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


REQUIRED_CONTRACT_FIELDS = {
    'owner_surface',
    'level',
    'management_mode',
    'cost_level',
    'goal_categories',
    'host_tab',
    'visibility_mode',
    'owner_module',
}

KNOWN_NON_TEMPLATE_REGISTRY_IDS = {
    'generation-output-settings-wrap',
    'generation-workflow-wrap',
    'generation-reliability-wrap',
    'generation-smart-wrap',
    'generation-power-wrap',
}


def _extract_generate_section_ids(template_text: str) -> list[str]:
    match = re.search(r'<section\b[^>]*\bid=["\']tab-generate["\'][^>]*>(.*?)</section>', template_text, flags=re.DOTALL)
    if not match:
        return []
    block = match.group(0)
    return sorted(set(re.findall(r'data-accordion-id="([^"]+)"', block)))


def _extract_registry_blocks(registry_text: str) -> Dict[str, str]:
    pattern = re.compile(r"^\s{4}\{\n\s{6}id:\s*'([^']+)'(.*?)^\s{4}\},?", re.MULTILINE | re.DOTALL)
    return {match.group(1): match.group(0) for match in pattern.finditer(registry_text)}


def run_phase6_contract_audit(project_root: Path | None = None) -> AuditResult:
    root = Path(project_root).resolve() if project_root else ROOT_DIR
    template_path = root / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
    registry_path = root / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_registry.js'
    contract_runtime_path = root / 'neo_studio_v1' / 'static' / 'js' / 'generation_section_contracts.js'

    result = AuditResult()

    if not template_path.exists():
        result.errors.append(f'Missing template: {template_path.relative_to(root).as_posix()}')
        return result
    if not registry_path.exists():
        result.errors.append(f'Missing section registry: {registry_path.relative_to(root).as_posix()}')
        return result
    if not contract_runtime_path.exists():
        result.errors.append(f'Missing contract runtime: {contract_runtime_path.relative_to(root).as_posix()}')
        return result

    template_ids = set(_extract_generate_section_ids(template_path.read_text(encoding='utf-8')))
    registry_text = registry_path.read_text(encoding='utf-8')
    registry_blocks = _extract_registry_blocks(registry_text)
    registry_ids = set(registry_blocks.keys())

    missing_registry = sorted(template_ids - registry_ids)
    for section_id in missing_registry:
        result.errors.append(f'Generation template accordion is missing a registry contract: {section_id}')

    unexpected_registry = sorted(registry_ids - template_ids - KNOWN_NON_TEMPLATE_REGISTRY_IDS)
    for section_id in unexpected_registry:
        result.warnings.append(f'Registry contains a section not found in the template or wrapper allowlist: {section_id}')

    for section_id, block in sorted(registry_blocks.items()):
        missing_fields = [field for field in sorted(REQUIRED_CONTRACT_FIELDS) if not re.search(rf"\b{re.escape(field)}\s*:", block)]
        if missing_fields:
            result.errors.append(f'Registry contract missing fields for {section_id}: {", ".join(missing_fields)}')
            continue

        owner_module_match = re.search(r"owner_module:\s*'([^']+)'", block)
        if owner_module_match:
            owner_module_rel = owner_module_match.group(1)
            candidate_paths = [root / owner_module_rel, root / 'neo_studio_v1' / owner_module_rel]
            if not any(path.exists() for path in candidate_paths):
                result.errors.append(f'Registry owner_module does not exist for {section_id}: {owner_module_rel}')

        goal_categories_match = re.search(r'goal_categories:\s*\[(.*?)\]', block, flags=re.DOTALL)
        if goal_categories_match:
            items = [item.strip().strip("'") for item in goal_categories_match.group(1).split(',') if item.strip()]
            if not items:
                result.warnings.append(f'Registry goal_categories is empty for {section_id}')

    result.info.append(f'Generation template accordions found: {len(template_ids)}')
    result.info.append(f'Registry contracts found: {len(registry_ids)}')
    result.info.append(f'Contract runtime present: {contract_runtime_path.relative_to(root).as_posix()}')
    return result


__all__ = ['AuditResult', 'run_phase6_contract_audit']
