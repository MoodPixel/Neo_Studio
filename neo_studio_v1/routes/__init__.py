from .admin_routes import router as admin_router
from .extension_routes import router as extension_router
from .assistant_routes import router as assistant_router
from .backend_routes import router as backend_router
from .board_routes import router as board_router
from .batch_routes import router as batch_router
from .bundle_routes import router as bundle_router
from .caption_routes import router as caption_router
from .character_routes import router as character_router
from .generation_routes import router as generation_router
from .library_transfer_routes import router as library_transfer_router
from .neo_library_routes import router as neo_library_router
from .node_manager_routes import router as node_manager_router
from .preset_routes import router as preset_router
from .roleplay_v2_foundation_routes import router as roleplay_v2_foundation_router
from .roleplay_v2_intake_routes import router as roleplay_v2_intake_router
from .roleplay_v2_package_routes import router as roleplay_v2_package_router
from .roleplay_v2_source_routes import router as roleplay_v2_source_router
from .roleplay_v2_breakdown_routes import router as roleplay_v2_breakdown_router
from .roleplay_v2_canon_routes import router as roleplay_v2_canon_router
from .roleplay_v2_memory_routes import router as roleplay_v2_memory_router
from .roleplay_v2_retrieval_routes import router as roleplay_v2_retrieval_router
from .roleplay_v2_runtime_routes import router as roleplay_v2_runtime_router
from .roleplay_v2_scene_routes import router as roleplay_v2_scene_router
from .roleplay_v2_story_routes import router as roleplay_v2_story_router
from .roleplay_v2_builder_routes import router as roleplay_v2_builder_router
from .roleplay_library_routes import router as roleplay_library_router
from .prompt_routes import router as prompt_router
from .scene_director_routes import router as scene_director_router
from .settings_routes import router as settings_router
from .video_routes import router as video_router
from .support_routes import router as support_router
from .system_routes import router as system_router

__all__ = [
    'admin_router',
    'assistant_router',
    'extension_router',
    'backend_router',
    'board_router',
    'batch_router',
    'bundle_router',
    'caption_router',
    'character_router',
    'generation_router',
    'library_transfer_router',
    'neo_library_router',
    'node_manager_router',
    'preset_router',
    'roleplay_v2_foundation_router',
    'roleplay_v2_intake_router',
    'roleplay_v2_package_router',
    'roleplay_v2_source_router',
    'roleplay_v2_breakdown_router',
    'roleplay_v2_canon_router',
    'roleplay_v2_memory_router',
    'roleplay_v2_retrieval_router',
    'roleplay_v2_runtime_router',
    'roleplay_v2_scene_router',
    'roleplay_v2_story_router',
    'roleplay_v2_builder_router',
    'roleplay_library_router',
    'prompt_router',
    'scene_director_router',
    'settings_router',
    'video_router',
    'support_router',
    'system_router',
]
