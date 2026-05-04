from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts.roleplay_v2_records import (
    ROLEPLAY_V2_SCHEMA_VERSION,
    ROLEPLAY_V2_ENTITY_KINDS,
    ROLEPLAY_V2_SOURCE_CONTAINER_KINDS,
    ROLEPLAY_V2_ENTITY_SPECS,
    ROLEPLAY_V2_BUILDER_SCHEMA_VERSION,
    build_entity_record,
    build_entity_contract,
    build_novel_project_record,
    build_source_document_record,
    build_canon_record,
)
from ..contracts.roleplay_v2_intake_records import (
    ROLEPLAY_V2_INTAKE_SCHEMA_VERSION,
    ROLEPLAY_V2_INTAKE_MODES,
    ROLEPLAY_V2_HELPER_MODES,
    build_creator_draft_record,
    build_helper_output_record,
)
from ..contracts.roleplay_v2_memory_records import (
    ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
    ROLEPLAY_V2_MEMORY_TYPES,
    build_memory_fragment_record,
    build_relationship_record,
    build_runtime_bundle_record,
    build_shared_memory_record,
    build_timeline_event_record,
)
from ..contracts.roleplay_v2_package_records import (
    ROLEPLAY_V2_PACKAGE_SCHEMA_VERSION,
    ROLEPLAY_V2_PACKAGE_EXTENSIONS,
    build_portable_package_manifest,
)
from ..contracts.roleplay_v2_scene_state import build_scene_state
from ..contracts.roleplay_v2_story_records import (
    ROLEPLAY_V2_STORY_SCHEMA_VERSION,
    ROLEPLAY_V2_STORY_RECORD_TYPES,
    build_storyline_record,
    build_story_session_record,
    build_story_checkpoint_record,
    build_story_draft_snapshot,
)
from ..contracts.roleplay_v2_builder_record_contract import build_shared_record_contract
from ..contracts.roleplay_v2_builder_link_contract import build_shared_link_contract
from ..contracts.roleplay_v2_builder_memory_contract import build_shared_memory_hints_contract
from .roleplay_v2_builder_workspace import list_builder_templates
from .library_constants import DEFAULT_ROOT
from .logging_utils import get_logger
from .storage_io import atomic_write_json, read_json_object

logger = get_logger(__name__)

ROLEPLAY_V2_ROOT = DEFAULT_ROOT / 'roleplay_v2'
ROLEPLAY_V2_FOUNDATION_PATH = ROLEPLAY_V2_ROOT / 'foundation_manifest.json'
ROLEPLAY_V2_ENTITIES_DIR = ROLEPLAY_V2_ROOT / 'entities'
ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR = ROLEPLAY_V2_ROOT / 'source_documents'
ROLEPLAY_V2_CREATOR_DRAFTS_DIR = ROLEPLAY_V2_ROOT / 'creator_drafts'
ROLEPLAY_V2_HELPER_OUTPUTS_DIR = ROLEPLAY_V2_ROOT / 'helper_outputs'
ROLEPLAY_V2_CANON_RECORDS_DIR = ROLEPLAY_V2_ROOT / 'canon_records'
ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR = ROLEPLAY_V2_ROOT / 'memory_fragments'
ROLEPLAY_V2_TIMELINE_EVENTS_DIR = ROLEPLAY_V2_ROOT / 'timeline_events'
ROLEPLAY_V2_RELATIONSHIPS_DIR = ROLEPLAY_V2_ROOT / 'relationships'
ROLEPLAY_V2_SHARED_MEMORIES_DIR = ROLEPLAY_V2_ROOT / 'shared_memories'
ROLEPLAY_V2_RUNTIME_BUNDLES_DIR = ROLEPLAY_V2_ROOT / 'runtime_bundles'
ROLEPLAY_V2_PACKAGES_DIR = ROLEPLAY_V2_ROOT / 'packages'
ROLEPLAY_V2_IMPORTS_DIR = ROLEPLAY_V2_ROOT / 'imports'
ROLEPLAY_V2_EXPORTS_DIR = ROLEPLAY_V2_ROOT / 'exports'
ROLEPLAY_V2_NOVEL_PROJECTS_DIR = ROLEPLAY_V2_ROOT / 'novel_projects'
ROLEPLAY_V2_RETRIEVAL_DIR = ROLEPLAY_V2_ROOT / 'retrieval'
ROLEPLAY_V2_STORYLINES_DIR = ROLEPLAY_V2_ROOT / 'storylines'
ROLEPLAY_V2_STORY_SESSIONS_DIR = ROLEPLAY_V2_ROOT / 'story_sessions'
ROLEPLAY_V2_STORY_CHECKPOINTS_DIR = ROLEPLAY_V2_ROOT / 'story_checkpoints'
ROLEPLAY_V2_STORY_DRAFTS_DIR = ROLEPLAY_V2_ROOT / 'story_drafts'
ROLEPLAY_V2_STORY_SNAPSHOTS_DIR = ROLEPLAY_V2_ROOT / 'story_snapshots'

ROLEPLAY_V2_DIRS = [
    ROLEPLAY_V2_ROOT,
    ROLEPLAY_V2_ENTITIES_DIR,
    ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR,
    ROLEPLAY_V2_CREATOR_DRAFTS_DIR,
    ROLEPLAY_V2_HELPER_OUTPUTS_DIR,
    ROLEPLAY_V2_CANON_RECORDS_DIR,
    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR,
    ROLEPLAY_V2_TIMELINE_EVENTS_DIR,
    ROLEPLAY_V2_RELATIONSHIPS_DIR,
    ROLEPLAY_V2_SHARED_MEMORIES_DIR,
    ROLEPLAY_V2_RUNTIME_BUNDLES_DIR,
    ROLEPLAY_V2_PACKAGES_DIR,
    ROLEPLAY_V2_IMPORTS_DIR,
    ROLEPLAY_V2_EXPORTS_DIR,
    ROLEPLAY_V2_NOVEL_PROJECTS_DIR,
    ROLEPLAY_V2_RETRIEVAL_DIR,
    ROLEPLAY_V2_STORYLINES_DIR,
    ROLEPLAY_V2_STORY_SESSIONS_DIR,
    ROLEPLAY_V2_STORY_CHECKPOINTS_DIR,
    ROLEPLAY_V2_STORY_DRAFTS_DIR,
    ROLEPLAY_V2_STORY_SNAPSHOTS_DIR,
]



def _build_manifest() -> dict[str, Any]:
    return {
        'schema_version': ROLEPLAY_V2_SCHEMA_VERSION,
        'record_type': 'roleplay_v2_foundation_manifest',
        'status': 'ready',
        'storage_root': str(ROLEPLAY_V2_ROOT),
        'directories': {path.name: str(path) for path in ROLEPLAY_V2_DIRS if path != ROLEPLAY_V2_ROOT},
        'entity_kinds': list(ROLEPLAY_V2_ENTITY_KINDS),
        'source_container_kinds': list(ROLEPLAY_V2_SOURCE_CONTAINER_KINDS),
        'builder_schema_version': ROLEPLAY_V2_BUILDER_SCHEMA_VERSION,
        'intake_modes': sorted(ROLEPLAY_V2_INTAKE_MODES),
        'helper_modes': sorted(ROLEPLAY_V2_HELPER_MODES),
        'memory_types': sorted(ROLEPLAY_V2_MEMORY_TYPES),
        'package_extensions': dict(ROLEPLAY_V2_PACKAGE_EXTENSIONS),
        'schema_versions': {
            'roleplay_v2': ROLEPLAY_V2_SCHEMA_VERSION,
            'intake': ROLEPLAY_V2_INTAKE_SCHEMA_VERSION,
            'memory': ROLEPLAY_V2_MEMORY_SCHEMA_VERSION,
            'package': ROLEPLAY_V2_PACKAGE_SCHEMA_VERSION,
            'story': ROLEPLAY_V2_STORY_SCHEMA_VERSION,
        },
        'story_record_types': sorted(ROLEPLAY_V2_STORY_RECORD_TYPES),
        'entity_specs': {kind: build_entity_contract(kind) for kind in ROLEPLAY_V2_ENTITY_KINDS},
        'shared_builder_contracts': {
            'record': build_shared_record_contract(),
            'links': build_shared_link_contract(),
            'memory_hints': build_shared_memory_hints_contract(),
        },
        'builder_templates': list_builder_templates(),
        'template_payloads': {
            'entity_record': build_entity_record(kind='character', label='Example Character'),
            'novel_project': build_novel_project_record(title='Example Novel Project'),
            'source_document': build_source_document_record(title='Example Chapter', project_id='novel_project_example'),
            'canon_record': build_canon_record(label='Example Canon', scope_type='source_document', scope_id='source_document_example'),
            'creator_draft': build_creator_draft_record(kind='character', source_name='draft.txt'),
            'helper_output': build_helper_output_record(draft_id='draft_example', kind='character'),
            'memory_fragment': build_memory_fragment_record(memory_type='semantic_fact', title='Example Memory'),
            'timeline_event': build_timeline_event_record(title='Example Event'),
            'relationship_record': build_relationship_record(relationship_type='ally'),
            'shared_memory': build_shared_memory_record(title='Example Shared Memory'),
            'runtime_bundle': build_runtime_bundle_record(mode='roleplay'),
            'scene_state': build_scene_state(),
            'storyline': build_storyline_record(title='Example Storyline'),
            'story_session': build_story_session_record(storyline_id='storyline_example'),
            'story_checkpoint': build_story_checkpoint_record(storyline_id='storyline_example', session_id='story_session_example', title='Example Checkpoint'),
            'story_draft_snapshot': build_story_draft_snapshot(storyline_id='storyline_example', session_id='story_session_example'),
            'portable_package_manifest': build_portable_package_manifest(title='Example Bundle'),
        },
        'implementation_notes': {
            'phase': 'phase_1_foundation',
            'design_rule': 'parallel_v2_lane_keep_v1_stable',
            'entity_contract_rule': 'source_containers_separate_from_world_entities',
            'reverse_link_rule': 'derive_reverse_views_do_not_manually_author_every_backlink',
            'helper_optional_validation_mandatory': True,
            'models_required_for_phase_1': False,
        },
    }



def ensure_roleplay_v2_foundation() -> dict[str, Any]:
    for path in ROLEPLAY_V2_DIRS:
        path.mkdir(parents=True, exist_ok=True)
    existing = read_json_object(ROLEPLAY_V2_FOUNDATION_PATH, None)
    if isinstance(existing, dict) and existing.get('record_type') == 'roleplay_v2_foundation_manifest':
        existing_schema_versions = existing.get('schema_versions') if isinstance(existing.get('schema_versions'), dict) else {}
        existing_story_record_types = existing.get('story_record_types') if isinstance(existing.get('story_record_types'), list) else []
        existing_directories = existing.get('directories') if isinstance(existing.get('directories'), dict) else {}
        template_payloads = existing.get('template_payloads') if isinstance(existing.get('template_payloads'), dict) else {}
        if (
            int(existing.get('schema_version') or 0) >= ROLEPLAY_V2_SCHEMA_VERSION
            and int(existing.get('builder_schema_version') or 0) >= ROLEPLAY_V2_BUILDER_SCHEMA_VERSION
            and isinstance(existing.get('shared_builder_contracts'), dict)
            and isinstance(existing.get('builder_templates'), list)
            and int(existing_schema_versions.get('story') or 0) >= ROLEPLAY_V2_STORY_SCHEMA_VERSION
            and {'storyline', 'story_session', 'story_checkpoint'}.issubset(set(existing_story_record_types))
            and {'storylines', 'story_sessions', 'story_checkpoints', 'story_drafts', 'story_snapshots'}.issubset(set(existing_directories.keys()))
            and {'storyline', 'story_session', 'story_checkpoint', 'story_draft_snapshot'}.issubset(set(template_payloads.keys()))
        ):
            return existing
    payload = _build_manifest()
    atomic_write_json(ROLEPLAY_V2_FOUNDATION_PATH, payload)
    logger.info('Roleplay V2 foundation ready at %s', ROLEPLAY_V2_ROOT)
    return payload



def get_roleplay_v2_foundation_state() -> dict[str, Any]:
    manifest = ensure_roleplay_v2_foundation()
    return {
        'ok': True,
        'foundation': manifest,
        'directory_exists': {path.name: path.exists() for path in ROLEPLAY_V2_DIRS},
        'directory_counts': {
            'entities': len(list(ROLEPLAY_V2_ENTITIES_DIR.glob('*.json'))),
            'source_documents': len(list(ROLEPLAY_V2_SOURCE_DOCUMENTS_DIR.glob('*.json'))),
            'creator_drafts': len(list(ROLEPLAY_V2_CREATOR_DRAFTS_DIR.glob('*.json'))),
            'helper_outputs': len(list(ROLEPLAY_V2_HELPER_OUTPUTS_DIR.glob('*.json'))),
            'canon_records': len(list(ROLEPLAY_V2_CANON_RECORDS_DIR.glob('*.json'))),
            'memory_fragments': len(list(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json'))),
            'timeline_events': len(list(ROLEPLAY_V2_TIMELINE_EVENTS_DIR.glob('*.json'))),
            'relationships': len(list(ROLEPLAY_V2_RELATIONSHIPS_DIR.glob('*.json'))),
            'shared_memories': len(list(ROLEPLAY_V2_SHARED_MEMORIES_DIR.glob('*.json'))),
            'runtime_bundles': len(list(ROLEPLAY_V2_RUNTIME_BUNDLES_DIR.glob('*.json'))),
            'packages': len(list(ROLEPLAY_V2_PACKAGES_DIR.glob('*.json'))),
            'novel_projects': len(list(ROLEPLAY_V2_NOVEL_PROJECTS_DIR.glob('*.json'))),
            'storylines': len(list(ROLEPLAY_V2_STORYLINES_DIR.glob('*.json'))),
            'story_sessions': len(list(ROLEPLAY_V2_STORY_SESSIONS_DIR.glob('*.json'))),
            'story_checkpoints': len(list(ROLEPLAY_V2_STORY_CHECKPOINTS_DIR.glob('*.json'))),
            'story_drafts': len(list(ROLEPLAY_V2_STORY_DRAFTS_DIR.glob('*.json'))),
            'story_snapshots': len(list(ROLEPLAY_V2_STORY_SNAPSHOTS_DIR.glob('*.json'))),
        },
    }
