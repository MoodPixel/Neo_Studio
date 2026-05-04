from __future__ import annotations

from copy import deepcopy

CAPABILITY_SCHEMA_VERSION = 1

CAPABILITY_DEFINITIONS = {
    'workspace_setup': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'workspace_setup',
        'label': 'Workspace setup',
        'ui_kind': 'context_strip',
        'description': 'Surface-level setup, guardrails, and quick state for the current workspace.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'build': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'build',
        'label': 'Build',
        'ui_kind': 'primary_panel',
        'description': 'Primary working controls for the active family or mode.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'assets': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'assets',
        'label': 'Assets / Reuse',
        'ui_kind': 'lane',
        'description': 'Reusable assets, prompt helpers, and supporting resources.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'reference': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'reference',
        'label': 'Reference / Match',
        'ui_kind': 'lane',
        'description': 'Reference-driven control, matching, and structural guidance.',
        'surface_scope': 'generation',
        'dev_only': False,
    },
    'finish': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'finish',
        'label': 'Finish / Polish',
        'ui_kind': 'lane',
        'description': 'Post-build enhancement, cleanup, and polish actions.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'helper': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'helper',
        'label': 'Helper',
        'ui_kind': 'assistant_bridge',
        'description': 'Cross-surface assistant handoff and guided help actions.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'results': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'results',
        'label': 'Results / Metadata',
        'ui_kind': 'result_shell',
        'description': 'Saved outputs, metadata, reuse, and lineage-aware result handling.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'preview': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'preview',
        'label': 'Preview',
        'ui_kind': 'preview_shell',
        'description': 'Current output preview and focused review controls.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'presets': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'presets',
        'label': 'Presets',
        'ui_kind': 'preset_shell',
        'description': 'Reusable scoped presets for surfaces, families, and tools.',
        'surface_scope': 'global',
        'dev_only': False,
    },
    'guides': {
        'schema_version': CAPABILITY_SCHEMA_VERSION,
        'id': 'guides',
        'label': 'Guides',
        'ui_kind': 'guide_shell',
        'description': 'Guide text, support text, and explainers tied to schema-driven fields.',
        'surface_scope': 'global',
        'dev_only': False,
    },
}


def list_capability_definitions() -> list[dict]:
    return [deepcopy(CAPABILITY_DEFINITIONS[key]) for key in CAPABILITY_DEFINITIONS]
