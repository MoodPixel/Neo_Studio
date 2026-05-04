from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

FILE_GROWTH_SCHEMA_VERSION = 2

FILE_GROWTH_RULES = {
    'jinja_templates': {
        'label': 'Jinja templates',
        'patterns': ['neo_studio_v1/templates/**/*.html'],
        'max_lines': 1200,
        'warn_at': 900,
    },
    'javascript_modules': {
        'label': 'JavaScript modules',
        'patterns': ['neo_studio_v1/static/js/**/*.js'],
        'max_lines': 800,
        'warn_at': 600,
    },
    'route_files': {
        'label': 'Route files',
        'patterns': ['neo_studio_v1/routes/**/*.py'],
        'max_lines': 600,
        'warn_at': 450,
    },
    'service_and_domain_files': {
        'label': 'Service / domain / utility Python files',
        'patterns': [
            'neo_studio_v1/utils/**/*.py',
            'neo_studio_v1/services/**/*.py',
            'neo_studio_v1/domain/**/*.py',
            'neo_studio_v1/adapters/**/*.py',
            'neo_studio_v1/repositories/**/*.py',
        ],
        'max_lines': 500,
        'warn_at': 375,
    },
}

LEGACY_FILE_GROWTH_EXCLUSIONS = [
    'neo_studio_v1/templates/partials/surfaces/roleplay_surface.html',
    'neo_studio_v1/static/js/roleplay_surface.js',
    'neo_studio_v1/static/js/roleplay_setup_shell.js',
    'neo_studio_v1/static/js/roleplay_shell_tones.js',
    'neo_studio_v1/routes/roleplay_routes.py',
    'neo_studio_v1/routes/roleplay_session_routes.py',
    'neo_studio_v1/routes/roleplay_story_routes.py',
    'neo_studio_v1/routes/roleplay_packet_routes.py',
    'neo_studio_v1/routes/roleplay_asset_routes.py',
    'neo_studio_v1/routes/roleplay_foundation_routes.py',
]

FILE_GROWTH_DEBT_BASELINE = {
    'neo_studio_v1/templates/partials/surfaces/generation_surface.html': 2735,
    'neo_studio_v1/templates/partials/surfaces/manager_surface.html': 1755,
    'neo_studio_v1/static/js/assistant_surface.js': 2393,
    'neo_studio_v1/static/js/captions.js': 1005,
    'neo_studio_v1/static/js/generation_catalog_state.js': 1194,
    'neo_studio_v1/static/js/generation_draft_state.js': 808,
    'neo_studio_v1/static/js/generation_library_tools.js': 1220,
    'neo_studio_v1/static/js/generation_mask_output_style.js': 2000,
    'neo_studio_v1/static/js/generation_power.js': 969,
    'neo_studio_v1/static/js/generation_regional_admin.js': 2063,
    'neo_studio_v1/static/js/generation_workspace_forms.js': 2009,
    'neo_studio_v1/static/js/neo_library.js': 2614,
    'neo_studio_v1/static/js/roleplay_library_manager.js': 1955,
    'neo_studio_v1/static/js/roleplay_story_manager.js': 1209,
    'neo_studio_v1/static/js/roleplay_v2_forge.js': 3047,
    'neo_studio_v1/static/js/roleplay_v2_scene.js': 1130,
    'neo_studio_v1/static/js/roleplay_v2_stories.js': 1432,
    'neo_studio_v1/static/js/roleplay_v2_studio.js': 1694,
    'neo_studio_v1/routes/assistant_routes.py': 825,
    'neo_studio_v1/routes/batch_runtime.py': 1120,
    'neo_studio_v1/routes/generation_routes.py': 2080,
    'neo_studio_v1/routes/neo_library_routes.py': 1361,
    'neo_studio_v1/routes/roleplay_v2_scene_routes.py': 738,
    'neo_studio_v1/utils/assistant_store.py': 680,
    'neo_studio_v1/utils/comfy_workflows.py': 2550,
    'neo_studio_v1/utils/detailer_preview.py': 809,
    'neo_studio_v1/utils/generation_dependency_audit.py': 689,
    'neo_studio_v1/utils/kobold.py': 1538,
    'neo_studio_v1/utils/library_transfer.py': 663,
    'neo_studio_v1/utils/roleplay_foundation.py': 838,
    'neo_studio_v1/utils/roleplay_library_ai_drafts.py': 522,
    'neo_studio_v1/utils/roleplay_library_imports.py': 698,
    'neo_studio_v1/utils/roleplay_session_store.py': 739,
    'neo_studio_v1/utils/roleplay_v2_builder_ai_drafts.py': 658,
    'neo_studio_v1/utils/roleplay_v2_builder_workspace.py': 844,
    'neo_studio_v1/utils/roleplay_v2_memory_compiler.py': 562,
    'neo_studio_v1/utils/roleplay_v2_runtime_bundle.py': 2026,
    'neo_studio_v1/utils/roleplay_v2_sqlite_store.py': 3650,
    'neo_studio_v1/utils/roleplay_v2_story_store.py': 1136,
    'neo_studio_v1/utils/roleplay_v2_turn_writeback.py': 733,
    'neo_studio_v1/utils/memory_service/sqlite_store.py': 666,
}

EARLY_SPLIT_TRIGGERS = [
    'the file handles two different domains',
    'the file mixes shared runtime logic with family- or surface-specific logic',
    'the file mixes rendering with state orchestration',
    'the file relies on comment banners to remain understandable',
    'the file has become append-only during feature work or audits',
]


def iter_file_growth_rules():
    for key, rule in FILE_GROWTH_RULES.items():
        row = dict(rule)
        row['id'] = key
        yield row


def is_legacy_budget_excluded(path: str | Path) -> bool:
    text = str(path)
    return any(fnmatch(text, pattern) for pattern in LEGACY_FILE_GROWTH_EXCLUSIONS)


def get_file_growth_baseline_cap(path: str | Path) -> int | None:
    return FILE_GROWTH_DEBT_BASELINE.get(str(path))
