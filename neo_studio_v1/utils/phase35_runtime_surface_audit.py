from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .config import ROOT_DIR


@dataclass
class AuditResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


TEMPLATE_PATH = ROOT_DIR / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
LAYOUT_PATH = ROOT_DIR / 'neo_studio_v1' / 'static' / 'js' / 'generation_layout.js'
WORKSPACE_ROUTER_PATH = ROOT_DIR / 'neo_studio_v1' / 'static' / 'js' / 'generation_workspace_router.js'
SMOKE_CHECKLIST_PATH = ROOT_DIR / 'docs' / 'phases' / 'generation_smoke_test_checklist.md'
PHASE35_CONTRACT_PATH = ROOT_DIR / 'docs' / 'phases' / 'phase35_runtime_surface_contract.md'
PHASE35_SMOKE_PATH = ROOT_DIR / 'docs' / 'phases' / 'phase35_stability_smoke_checklist.md'


TEMPLATE_REQUIRED_IDS = [
    'tab-generate',
    'generation-setup-rail',
    'generation-live-workspace',
    'generation-source-wrap',
    'generation-output-settings-host',
    'generation-output-inspector-host',
]

LAYOUT_REQUIRED_SNIPPETS = {
    'workspace actions card is mounted into the live workspace': "actionsCard.classList.add('generation-actions-card--workspace')",
    'workflow host is created by the layout layer': "workflowHost.id = 'generation-workflow-host'",
    'workflow notes are promoted inline inside the workflow card': 'promoteWorkflowNotesBlock(workflowCard);',
}

ROUTER_REQUIRED_SNIPPETS = {
    'core tab host is controlled by syncSetupTab': "setHidden($('generation-workflow-host'), next !== 'core');",
    'assets tab host is controlled by syncSetupTab': "setHidden(assetsHost, next !== 'assets');",
    'reference tab host is controlled by syncSetupTab': "setHidden(matchHost, next !== 'guide');",
    'finish tab host is controlled by syncSetupTab': "setHidden(enhanceHost, next !== 'enhance');",
    'results tab host is controlled by syncSetupTab': "setHidden(outputHost, next !== 'output');",
    'main generation actions card is placed above the shell': 'root.insertBefore(actionsCard, shellPanel);',
    'prompt stack stays in the right working column': 'topRight.appendChild(promptCard);',
    'live output stays in the right working column': 'topRight.appendChild(liveWorkspace);',
    'source controls stay in the right working column': 'topRight.appendChild(sourceWrap);',
    'assets lane is rendered into its canonical host': "renderTabLane('assets', 'generation-assets-tab-host');",
    'reference lane is rendered into its canonical host': "renderTabLane('guide', 'generation-match-tab-host');",
    'finish lane is rendered into its canonical host': "renderTabLane('enhance', 'generation-enhance-tab-host');",
    'results lane is rendered into its canonical host': "renderTabLane('output', 'generation-output-tab-host');",
}

SETUP_TAB_BUTTON_SNIPPETS = [
    'data-generation-setup-tab="core"',
    'data-generation-setup-tab="assets"',
    'data-generation-setup-tab="guide"',
    'data-generation-setup-tab="enhance"',
    'data-generation-setup-tab="output"',
]


def _require_contains(result: AuditResult, haystack: str, needle: str, message: str) -> None:
    if needle not in haystack:
        result.errors.append(message)


def run_phase35_runtime_surface_audit(project_root: Path | None = None) -> AuditResult:
    root = Path(project_root).resolve() if project_root else ROOT_DIR
    template_path = root / 'neo_studio_v1' / 'templates' / 'partials' / 'surfaces' / 'generation_surface.html'
    layout_path = root / 'neo_studio_v1' / 'static' / 'js' / 'generation_layout.js'
    router_path = root / 'neo_studio_v1' / 'static' / 'js' / 'generation_workspace_router.js'
    smoke_checklist_path = root / 'docs' / 'phases' / 'generation_smoke_test_checklist.md'
    phase35_contract_path = root / 'docs' / 'phases' / 'phase35_runtime_surface_contract.md'
    phase35_smoke_path = root / 'docs' / 'phases' / 'phase35_stability_smoke_checklist.md'

    result = AuditResult()

    for path in [template_path, layout_path, router_path, smoke_checklist_path, phase35_contract_path, phase35_smoke_path]:
        if not path.exists():
            result.errors.append(f'Missing required Phase 35 file: {path.relative_to(root).as_posix()}')

    if result.errors:
        return result

    template_text = template_path.read_text(encoding='utf-8')
    layout_text = layout_path.read_text(encoding='utf-8')
    router_text = router_path.read_text(encoding='utf-8')

    for element_id in TEMPLATE_REQUIRED_IDS:
        _require_contains(
            result,
            template_text,
            f'id="{element_id}"',
            f'Generation template is missing required runtime anchor id: {element_id}',
        )

    for message, snippet in LAYOUT_REQUIRED_SNIPPETS.items():
        _require_contains(result, layout_text, snippet, f'Generation layout contract missing: {message}')

    for message, snippet in ROUTER_REQUIRED_SNIPPETS.items():
        _require_contains(result, router_text, snippet, f'Workspace router contract missing: {message}')

    for snippet in SETUP_TAB_BUTTON_SNIPPETS:
        _require_contains(result, router_text, snippet, f'Setup tab button is missing from workspace router: {snippet}')

    if 'generation-lane-parking' in router_text or 'function renderLane(' in router_text:
        result.errors.append('Legacy lane parking / renderLane path still exists in generation_workspace_router.js.')

    if 'moveWorkflowAddonsToLeftRail(' in layout_text or 'movePromptCreativeToolsToRightRail(' in layout_text:
        result.errors.append('Legacy left/right rail extraction helpers still exist in generation_layout.js.')

    if 'generation-left-addon-host' in layout_text or 'generation-right-creative-host' in layout_text or 'generation-top-support-stack' in layout_text or 'generation-left-addon-host' in router_text or 'generation-right-creative-host' in router_text or 'generation-top-support-stack' in router_text:
        result.errors.append('Legacy hidden host ids still exist in the active layout/router sources.')

    result.info.append(f'Required runtime anchors checked: {len(TEMPLATE_REQUIRED_IDS)}')
    result.info.append(f'Layout contract checks passed: {len(LAYOUT_REQUIRED_SNIPPETS)}')
    result.info.append(f'Workspace router contract checks passed: {len(ROUTER_REQUIRED_SNIPPETS) + len(SETUP_TAB_BUTTON_SNIPPETS)}')
    result.info.append('Phase 0 and Phase 6 audits now read the real Generation section markup order-insensitively.')
    return result


__all__ = ['AuditResult', 'run_phase35_runtime_surface_audit']
