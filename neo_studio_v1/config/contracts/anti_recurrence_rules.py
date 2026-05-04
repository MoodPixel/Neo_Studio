from __future__ import annotations

ANTI_RECURRENCE_SCHEMA_VERSION = 1

PROTECTED_CLUSTERS = {
    'image_shell_runtime': {
        'label': 'Image shell / runtime cluster',
        'files': [
            'neo_studio_v1/templates/partials/surfaces/generation_surface.html',
            'neo_studio_v1/static/js/generation_workspace_router.js',
            'neo_studio_v1/static/js/generation_layout.js',
            'neo_studio_v1/static/js/generation_goal_router.js',
            'neo_studio_v1/static/js/generation_vram_guardrails.js',
            'neo_studio_v1/static/js/app.js',
        ],
        'edit_protocol': 'Review the full cluster before changing shell structure, mount order, or workspace boundaries.',
    },
    'surface_truth': {
        'label': 'Canonical surface-truth cluster',
        'files': [
            'neo_studio_v1/contracts/surfaces.py',
            'neo_studio_v1/templates/index.html',
            'neo_studio_v1/templates/partials/welcome_board.html',
            'neo_studio_v1/static/js/surface_registry.js',
            'neo_studio_v1/static/js/welcome_board.js',
            'neo_studio_v1/static/js/workspace_helper_foundation.js',
        ],
        'edit_protocol': 'Do not add secondary label maps, manual tab order, or hardcoded maturity/backend truth in consumers.',
    },
    'backend_admin': {
        'label': 'Backend / admin cluster',
        'files': [
            'neo_studio_v1/utils/backend_manager.py',
            'neo_studio_v1/contracts/backend_profiles.py',
            'neo_studio_v1/templates/partials/surfaces/admin_surface.html',
            'neo_studio_v1/static/js/admin_panel.js',
            'neo_studio_v1/static/js/backend_manager.js',
        ],
        'edit_protocol': 'Review backend profile contracts, admin UI, and runtime manager together before changing backend-facing flows.',
    },
}

SOURCE_OF_TRUTH_OWNERS = {
    'surface_identity': {
        'owner': 'neo_studio_v1/contracts/surfaces.py',
        'governs': ['visible label', 'internal id', 'nav order', 'maturity', 'backend expectations', 'helper visibility', 'enabled state'],
    },
    'file_growth_limits': {
        'owner': 'neo_studio_v1/contracts/file_growth_rules.py',
        'governs': ['line budgets', 'early split triggers'],
    },
    'phase0_baseline_protection': {
        'owner': 'neo_studio_v1/docs/phase00_governance_map.json',
        'governs': ['protected files', 'sensitive files', 'dependency clusters', 'unsafe edit patterns'],
    },
}

CANONICAL_SURFACE_CONSUMER_CHECKS = {
    'neo_studio_v1/templates/index.html': {
        'must_contain': [
            '{% for surface in surface_definitions %}',
            'data-main-tab="{{ surface.id }}"',
            '{{ surface.label }}',
        ],
        'must_not_contain': [
            'data-main-tab="generate"',
        ],
    },
    'neo_studio_v1/templates/partials/welcome_board.html': {
        'must_contain': [
            '{% for surface in surface_definitions %}',
            'data-switch-tab="{{ surface.id }}"',
            '{{ surface.label }}',
            '{{ surface.launch_board_copy',
        ],
        'must_not_contain': [
            '<div class="welcome-card-title">Generation</div>',
            '<div class="welcome-card-title">Video</div>',
            'data-switch-tab="prompt"',
        ],
    },
    'neo_studio_v1/static/js/welcome_board.js': {
        'must_contain': [
            'function resolveSurfaceLabel(surfaceId)',
            'boot.surfaceDefinitions',
            'window.NeoSurfaceRegistry?.getSurface?.(target)?.label',
            'Last surface: ${resolveSurfaceLabel(lastSurface)}',
        ],
        'must_not_contain': [
            "generate: 'Generation'",
            "video: 'Video Generation'",
            "|| 'Generation'",
        ],
    },
    'neo_studio_v1/static/js/workspace_helper_foundation.js': {
        'must_contain': [
            "resolveSurfaceLabel('generate', 'Image')",
        ],
        'must_not_contain': [
            "label: 'Generation helper'",
            "(Generation workspace is still mostly empty.)",
        ],
    },
}

GOVERNANCE_PROTOCOL_DOC_CHECKS = {
    'docs/ai_assist/change_preflight_checklist.md': {
        'must_contain': [
            '## Step 0 — baseline protection check',
            '## Step 5A — protected file gate',
            'neo_studio_v1/docs/phase00_governance_map.json',
        ],
    },
    'docs/ai_assist/neo_studio_copilot_prompt.txt': {
        'must_contain': [
            'neo_studio_v1/docs/phase00_freeze_rules.md',
            'neo_studio_v1/docs/phase00_product_rules.md',
            'neo_studio_v1/docs/phase00_governance_map.json',
            'If a target file is protected or part of a protected cluster',
        ],
    },
    'docs/ai_assist/protected_file_edit_protocol.md': {
        'must_contain': [
            '# Protected File Edit Protocol',
            'shell-only',
            'workspace-only',
            'cross-boundary',
        ],
    },
}

REQUIRED_GOVERNANCE_DOCS = [
    'docs/architecture/current_product_decisions.md',
    'docs/architecture/file_ownership_map.md',
    'docs/architecture/phase0_baseline_protection.md',
    'docs/architecture/phase1_surface_source_of_truth.md',
    'docs/architecture/phase2_anti_recurrence_governance.md',
    'docs/ai_assist/change_preflight_checklist.md',
    'docs/ai_assist/neo_studio_copilot_prompt.txt',
    'docs/ai_assist/protected_file_edit_protocol.md',
    'neo_studio_v1/docs/phase00_governance_map.json',
]

BANNED_EDIT_PATTERNS = [
    'Adding wrapper divs inside runtime-sensitive Image layout zones without dependency review.',
    'Reusing lower workspace classes for new shell UI.',
    'Adding a second source of truth for labels, order, maturity, backend roles, or dev-only visibility.',
    'Changing a protected file without stating the owning cluster and boundary being touched.',
    'Moving developer-only controls into normal user-facing surfaces.',
]


def iter_cluster_rows():
    for key, payload in PROTECTED_CLUSTERS.items():
        row = dict(payload)
        row['id'] = key
        yield row


def iter_consumer_checks():
    for key, payload in CANONICAL_SURFACE_CONSUMER_CHECKS.items():
        row = dict(payload)
        row['path'] = key
        yield row


def iter_protocol_doc_checks():
    for key, payload in GOVERNANCE_PROTOCOL_DOC_CHECKS.items():
        row = dict(payload)
        row['path'] = key
        yield row


__all__ = [
    'ANTI_RECURRENCE_SCHEMA_VERSION',
    'PROTECTED_CLUSTERS',
    'SOURCE_OF_TRUTH_OWNERS',
    'CANONICAL_SURFACE_CONSUMER_CHECKS',
    'GOVERNANCE_PROTOCOL_DOC_CHECKS',
    'REQUIRED_GOVERNANCE_DOCS',
    'BANNED_EDIT_PATTERNS',
    'iter_cluster_rows',
    'iter_consumer_checks',
    'iter_protocol_doc_checks',
]
