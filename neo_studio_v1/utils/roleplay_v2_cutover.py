from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .roleplay_v2_migration import build_phase14_migration_status
from .storage_io import atomic_write_json

CUTOVER_STATE_PATH = Path(__file__).resolve().parents[2] / 'devtools' / 'migrations' / 'roleplay_v2_soft_cutover_state.json'
REPO_ROOT = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_roleplay_v2_cutover_state() -> dict[str, Any]:
    if not CUTOVER_STATE_PATH.exists():
        return {
            'ok': True,
            'soft_cutover_active': False,
            'hide_legacy_surface': False,
            'legacy_read_only': False,
            'force_v2_label': False,
            'updated_at': '',
        }
    try:
        payload = json.loads(CUTOVER_STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        payload = {}
    return {
        'ok': True,
        'soft_cutover_active': bool(payload.get('soft_cutover_active')),
        'hide_legacy_surface': bool(payload.get('hide_legacy_surface')),
        'legacy_read_only': bool(payload.get('legacy_read_only')),
        'force_v2_label': bool(payload.get('force_v2_label')),
        'updated_at': str(payload.get('updated_at') or '').strip(),
    }


def _contains(relative_path: str, needle: str) -> bool:
    path = REPO_ROOT / relative_path
    if not path.exists():
        return False
    try:
        return needle in path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return False


def _contains_all(relative_path: str, needles: list[str] | tuple[str, ...]) -> bool:
    path = REPO_ROOT / relative_path
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return False
    return all(needle in content for needle in needles)


def _validation_check(label: str, *, ok: bool, detail: str) -> dict[str, Any]:
    return {
        'label': label,
        'ok': bool(ok),
        'detail': str(detail or '').strip(),
    }


def _dependency_snapshot() -> dict[str, Any]:
    return {
        'legacy_surface_registered': _contains('neo_studio_v1/contracts/surfaces.py', "'id': 'roleplay'"),
        'legacy_surface_template_loaded': _contains('neo_studio_v1/templates/index.html', 'partials/surfaces/roleplay_surface.html'),
        'legacy_surface_script_loaded': _contains('neo_studio_v1/templates/index.html', 'js/roleplay_surface.js'),
        'legacy_story_manager_script_loaded': _contains('neo_studio_v1/templates/index.html', 'js/roleplay_story_manager.js'),
        'legacy_library_manager_script_loaded': _contains('neo_studio_v1/templates/index.html', 'js/roleplay_library_manager.js'),
        'v2_shell_uses_legacy_backend_mirror': _contains('neo_studio_v1/static/js/roleplay_v2_shell.js', 'surface-backend-roleplay-state'),
        'v2_library_bridge_has_legacy_open_hook': _contains('neo_studio_v1/static/js/roleplay_v2_libraries_bridge.js', 'openLegacyRoleplay'),
        'surface_registry_has_v2_activation_hook': _contains('neo_studio_v1/static/js/surface_registry.js', 'roleplay_v2()'),
        'surface_registry_focus_target_current': _contains('neo_studio_v1/static/js/surface_registry.js', "roleplay-v2-scene-user-input") and not _contains('neo_studio_v1/static/js/surface_registry.js', "roleplay-v2-scene-input"),
        'roleplay_v2_surface_loaded': _contains('neo_studio_v1/templates/index.html', 'partials/surfaces/roleplay_v2_surface.html'),
        'roleplay_v2_cutover_script_loaded': _contains('neo_studio_v1/templates/index.html', 'js/roleplay_v2_cutover.js'),
    }


def _validation_snapshot() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        _validation_check(
            'mode_model_locked',
            ok=_contains_all(
                'neo_studio_v1/contracts/roleplay_v2_mode_model.py',
                [
                    "VALID_OUTPUT_PRESETS = {'roleplay', 'short_story', 'novel', 'cinematic'}",
                    "VALID_INTERACTION_MODES = {'roleplay', 'authoring'}",
                    "goal_labels = {",
                    "'novel': 'Novel authoring'",
                ],
            ),
            detail='Canonical mode matrix is centralized in the shared V2 mode model.',
        ),
        _validation_check(
            'forge_crud_routes_present',
            ok=_contains_all(
                'neo_studio_v1/routes/roleplay_v2_builder_routes.py',
                [
                    "/api/roleplay/v2/builders/forge-state",
                    "/api/roleplay/v2/builders/records",
                    "/api/roleplay/v2/builders/save",
                    "/api/roleplay/v2/builders/delete",
                ],
            ),
            detail='Forge CRUD endpoints are present for state, list, save, and delete.',
        ),
        _validation_check(
            'source_ingest_routes_present',
            ok=_contains_all(
                'neo_studio_v1/routes/roleplay_v2_source_routes.py',
                [
                    "/api/roleplay/v2/source/project/workspace",
                    "/api/roleplay/v2/source/document/save-text",
                    "/api/roleplay/v2/source/document",
                ],
            ),
            detail='Source project workspace and document save/load routes are present.',
        ),
        _validation_check(
            'runtime_build_routes_present',
            ok=_contains_all(
                'neo_studio_v1/routes/roleplay_v2_runtime_routes.py',
                [
                    "/api/roleplay/v2/runtime/build",
                    "/api/roleplay/v2/runtime/bundle",
                    "/api/roleplay/v2/runtime/project",
                ],
            ),
            detail='Runtime build and bundle inspection routes are present.',
        ),
        _validation_check(
            'scene_turn_route_present',
            ok=_contains('neo_studio_v1/routes/roleplay_v2_scene_routes.py', "/api/roleplay/v2/scene/turn"),
            detail='Scene turn route is present for live continuation.',
        ),
        _validation_check(
            'stories_resume_routes_present',
            ok=_contains_all(
                'neo_studio_v1/routes/roleplay_v2_story_routes.py',
                [
                    "/api/roleplay/v2/storyline/create",
                    "/api/roleplay/v2/story-session/create",
                    "/api/roleplay/v2/story-checkpoint/save",
                    "/api/roleplay/v2/story-resume",
                ],
            ),
            detail='Storyline, session, checkpoint, and resume routes are present.',
        ),
        _validation_check(
            'studio_guide_ui_present',
            ok=_contains_all(
                'neo_studio_v1/templates/partials/surfaces/roleplay_v2_surface.html',
                ['id="roleplay-v2-studio-subtabbar"', 'data-roleplay-v2-studio-tab="guide"', 'id="roleplay-v2-user-path-summary"'],
            ),
            detail='Studio guide path anchors are present in the surface.',
        ),
        _validation_check(
            'forge_layout_workspace_present',
            ok=_contains_all(
                'neo_studio_v1/templates/partials/surfaces/roleplay_v2_surface.html',
                ['id="roleplay-v2-forge-bottom-workspace"', 'id="roleplay-v2-forge-utility-shell"'],
            ),
            detail='Forge bottom row keeps records below while Inspector/SQLite share one utility shell.',
        ),
        _validation_check(
            'stories_ui_present',
            ok=_contains_all(
                'neo_studio_v1/templates/partials/surfaces/roleplay_v2_surface.html',
                [
                    'id="roleplay-v2-stories-form-title"',
                    'id="roleplay-v2-stories-session-summary"',
                    'id="roleplay-v2-stories-restore-note"',
                ],
            ),
            detail='Stories has real storyline/session forms plus restore preview guidance.',
        ),
        _validation_check(
            'roleplay_choice_assist_present',
            ok=_contains_all(
                'neo_studio_v1/templates/partials/surfaces/roleplay_v2_surface.html',
                ['id="roleplay-v2-scene-turn-input-style"', 'id="roleplay-v2-scene-choice-list"'],
            ) and _contains('neo_studio_v1/routes/roleplay_v2_scene_routes.py', 'generate_branch_options'),
            detail='Roleplay-only choice assist UI and route-side suggestion generation are present.',
        ),
        _validation_check(
            'novel_authoring_metadata_chain_present',
            ok=_contains_all(
                'neo_studio_v1/static/js/roleplay_v2_studio.js',
                ['roleplay-v2-doc-part-arc', 'roleplay-v2-doc-pov', 'roleplay-v2-doc-tense', 'roleplay-v2-doc-author-notes'],
            ) and _contains('neo_studio_v1/utils/roleplay_v2_breakdown_helper.py', 'source_metadata') and _contains('neo_studio_v1/utils/roleplay_v2_canon_compiler.py', 'source_metadata'),
            detail='Novel-authoring metadata survives source ingest, breakdown, and canon compile.',
        ),
    ]
    passed = sum(1 for item in checks if item.get('ok'))
    failed = [item['label'] for item in checks if not item.get('ok')]
    return {
        'ok': not failed,
        'checks': checks,
        'counts': {
            'total': len(checks),
            'passed': passed,
            'failed': len(failed),
        },
        'failed_checks': failed,
        'validation_mode': 'code_and_structure',
        'note': 'This validation snapshot checks current V2 routes, UI surfaces, mode contracts, and transition hooks in the codebase. It is not a browser-driven QA run.',
    }


def _classify_migration(migration: dict[str, Any]) -> dict[str, list[str]]:
    gaps = [str(item).strip() for item in list(migration.get('gaps') or []) if str(item).strip()]
    blockers: list[str] = []
    warnings: list[str] = []
    for gap in gaps:
        if gap in {'sqlite_relationship_scope_columns_missing'}:
            blockers.append(gap)
        else:
            warnings.append(gap)
    return {'blockers': blockers, 'warnings': warnings}


def build_roleplay_v2_cutover_status() -> dict[str, Any]:
    state = load_roleplay_v2_cutover_state()
    migration = build_phase14_migration_status()
    dependencies = _dependency_snapshot()
    validation = _validation_snapshot()
    migration_state = _classify_migration(migration)

    blockers: list[str] = []
    warnings: list[str] = []
    validation_warnings: list[str] = []
    transition_warnings: list[str] = []

    blockers.extend(migration_state.get('blockers') or [])
    if not dependencies.get('surface_registry_has_v2_activation_hook'):
        blockers.append('roleplay_v2_activation_hook_missing')
    if not validation.get('ok'):
        blockers.append('validation_snapshot_failed')
        validation_warnings.extend(list(validation.get('failed_checks') or []))

    validation_warnings.extend(migration_state.get('warnings') or [])
    if dependencies.get('v2_shell_uses_legacy_backend_mirror'):
        transition_warnings.append('v2_shell_still_mirrors_legacy_backend_dom')
    if dependencies.get('legacy_surface_script_loaded'):
        transition_warnings.append('legacy_roleplay_scripts_still_load_for_transition_safety')
    if dependencies.get('v2_library_bridge_has_legacy_open_hook'):
        transition_warnings.append('v2_libraries_still_contain_legacy_open_bridge')
    if not dependencies.get('surface_registry_focus_target_current'):
        transition_warnings.append('surface_registry_focus_target_stale')

    warnings.extend(validation_warnings)
    warnings.extend(transition_warnings)

    ready_for_soft_cutover = not blockers
    no_legacy_transition_load = not any(
        dependencies.get(key)
        for key in (
            'legacy_surface_registered',
            'legacy_surface_template_loaded',
            'legacy_surface_script_loaded',
            'legacy_story_manager_script_loaded',
            'legacy_library_manager_script_loaded',
            'v2_shell_uses_legacy_backend_mirror',
            'v2_library_bridge_has_legacy_open_hook',
        )
    )
    ready_for_hard_removal = bool(state.get('soft_cutover_active')) and ready_for_soft_cutover and no_legacy_transition_load

    recommendations: list[str] = []
    if ready_for_soft_cutover and not state.get('soft_cutover_active'):
        recommendations.append('apply_soft_cutover')
    if state.get('soft_cutover_active'):
        recommendations.append('validate_real_project_sessions_under_v2_only_nav')
    if validation_warnings:
        recommendations.append('run_phase14_backfill_and_environment_validation')
    if transition_warnings:
        recommendations.append('remove_remaining_transition_scaffolding_after_validation')
    if ready_for_hard_removal:
        recommendations.append('legacy_transition_dependencies_clear')

    summary = {
        'surface_maturity': 'stable',
        'soft_cutover_active': bool(state.get('soft_cutover_active')),
        'legacy_transition_dependencies_remaining': not no_legacy_transition_load,
        'validation_passed': bool(validation.get('ok')),
        'validation_scope': validation.get('validation_mode'),
        'environment_notes': list((migration.get('cleanup_profile') or {}).get('notes') or []),
    }

    return {
        'ok': True,
        'state': state,
        'summary': summary,
        'migration': migration,
        'dependencies': dependencies,
        'validation': validation,
        'blockers': blockers,
        'warnings': warnings,
        'validation_warnings': validation_warnings,
        'transition_warnings': transition_warnings,
        'ready_for_soft_cutover': ready_for_soft_cutover,
        'ready_for_hard_removal': ready_for_hard_removal,
        'recommended_actions': recommendations,
        'cutover_state_path': str(CUTOVER_STATE_PATH),
    }


def apply_roleplay_v2_soft_cutover(*, enabled: bool = True, force: bool = False) -> dict[str, Any]:
    status = build_roleplay_v2_cutover_status()
    blockers = list(status.get('blockers') or [])
    if enabled and blockers and not force:
        return {
            'ok': False,
            'error': 'Soft cutover is blocked until the remaining validation blockers are cleared.',
            'blockers': blockers,
            'status': status,
        }
    payload = {
        'soft_cutover_active': bool(enabled),
        'hide_legacy_surface': bool(enabled),
        'legacy_read_only': bool(enabled),
        'force_v2_label': bool(enabled),
        'updated_at': _now_iso(),
    }
    CUTOVER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(CUTOVER_STATE_PATH, payload)
    refreshed = build_roleplay_v2_cutover_status()
    return {
        'ok': True,
        'message': 'Soft cutover applied.' if enabled else 'Soft cutover disabled.',
        'status': refreshed,
        'cutover_state_path': str(CUTOVER_STATE_PATH),
    }
