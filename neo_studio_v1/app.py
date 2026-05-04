from __future__ import annotations

import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import (
    admin_router,
    extension_router,
    assistant_router,
    backend_router,
    board_router,
    batch_router,
    bundle_router,
    caption_router,
    character_router,
    generation_router,
    library_transfer_router,
    neo_library_router,
    node_manager_router,
    preset_router,
    prompt_router,
    scene_director_router,
    roleplay_v2_foundation_router,
    roleplay_v2_intake_router,
    roleplay_v2_package_router,
    roleplay_v2_source_router,
    roleplay_v2_breakdown_router,
    roleplay_v2_canon_router,
    roleplay_v2_memory_router,
    roleplay_v2_retrieval_router,
    roleplay_v2_runtime_router,
    roleplay_v2_scene_router,
    roleplay_v2_story_router,
    roleplay_v2_builder_router,
    roleplay_library_router,
    settings_router,
    video_router,
    support_router,
    system_router,
)
from .utils.characters import character_entries
from .utils.config import STATIC_DIR, TEMPLATES_DIR
from .utils.kobold import get_models
from .utils.library_presets import (
    get_caption_presets,
    get_last_used_caption_preset,
    get_last_used_prompt_preset,
    get_prompt_presets,
)
from .utils.library_prompts import prompt_categories, prompt_entries
from .utils.library_settings_store import get_last_used_category, list_categories
from .utils.library_stats import stats
from .utils.library_storage import cleanup_temp_uploads
from .utils.roleplay_foundation import ensure_roleplay_foundation
from .utils.roleplay_v2_foundation import ensure_roleplay_v2_foundation
from .utils.assistant_store import ensure_assistant_foundation
from .utils.board_store import ensure_board_foundation
from .utils.memory_service import ensure_chroma_foundation, ensure_memory_foundation
from .utils.product_goal_map import load_phase01_goal_map
from .utils.guide_registry import ensure_support_guides_foundation
from .utils.extension_registry import ensure_extension_registry, build_frontend_hook_registry
from .utils.extension_backend_hooks import mount_enabled_extension_backend_routes
from .utils.prompt_bundles import bundle_entries
from .utils.app_settings import load_app_settings
from .utils.system_summary import get_recent_totals
from .contracts import list_surface_definitions, build_surface_boot_registry, build_video_contract_boot_payload

STATIC_DIR.mkdir(parents=True, exist_ok=True)
cleanup_temp_uploads()
ensure_roleplay_foundation()
ensure_roleplay_v2_foundation()
ensure_assistant_foundation()
ensure_memory_foundation()
ensure_chroma_foundation()
ensure_support_guides_foundation()
ensure_extension_registry()
ensure_board_foundation()

APP_HOST = '0.0.0.0'
APP_PORT = 8000
BROWSER_HOST = '127.0.0.1'
BROWSER_URL = f'http://{BROWSER_HOST}:{APP_PORT}'
READINESS_URL = f'{BROWSER_URL}/health'
READINESS_TIMEOUT_SECONDS = 30.0
READINESS_POLL_INTERVAL_SECONDS = 0.25

app = FastAPI(title='Neo Studio')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

for router in (
    system_router,
    admin_router,
    extension_router,
    assistant_router,
    backend_router,
    board_router,
    prompt_router,
    bundle_router,
    character_router,
    caption_router,
    generation_router,
    batch_router,
    library_transfer_router,
    neo_library_router,
    node_manager_router,
    settings_router,
    video_router,
    preset_router,
    scene_director_router,
    support_router,
    roleplay_v2_foundation_router,
    roleplay_v2_intake_router,
    roleplay_v2_package_router,
    roleplay_v2_source_router,
    roleplay_v2_breakdown_router,
    roleplay_v2_canon_router,
    roleplay_v2_memory_router,
    roleplay_v2_retrieval_router,
    roleplay_v2_runtime_router,
    roleplay_v2_scene_router,
    roleplay_v2_story_router,
    roleplay_v2_builder_router,
    roleplay_library_router,
):
    app.include_router(router)

mount_enabled_extension_backend_routes(app)


@app.get('/health')
async def health():
    return {'ok': True, 'app': 'Neo Studio'}


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    models = await get_models()
    categories = list_categories()
    prompt_category_list = prompt_categories()
    last_prompt_category = get_last_used_category('prompt')
    last_caption_category = get_last_used_category('caption')
    prompt_presets = get_prompt_presets()
    caption_presets = get_caption_presets()
    phase01_goal_map = load_phase01_goal_map()
    app_settings = load_app_settings()
    recent_totals = get_recent_totals()
    surface_definitions = list_surface_definitions(include_disabled=False)
    return templates.TemplateResponse(
        request,
        'index.html',
        {
            'request': request,
            'models': models,
            'categories': categories,
            'stats': stats(),
            'last_prompt_category': last_prompt_category,
            'last_caption_category': last_caption_category,
            'caption_presets': caption_presets,
            'last_caption_preset': get_last_used_caption_preset(),
            'prompt_presets': prompt_presets,
            'last_prompt_preset': get_last_used_prompt_preset(),
            'prompt_categories': prompt_category_list,
            'saved_prompt_entries': prompt_entries(last_prompt_category),
            'saved_character_entries': character_entries(),
            'boot_data': {
                'initialCategories': categories,
                'initialPromptPresets': prompt_presets,
                'initialCaptionPresets': caption_presets,
                'initialPromptEntries': prompt_entries(last_prompt_category),
                'initialCharacterEntries': character_entries(),
                'lastPromptCategory': last_prompt_category,
                'lastCaptionCategory': last_caption_category,
                'promptCategories': prompt_category_list,
                'lastPromptPreset': get_last_used_prompt_preset(),
                'lastCaptionPreset': get_last_used_caption_preset(),
                'initialBundleEntries': bundle_entries(),
                'phase01GoalMap': phase01_goal_map,
                'appSettings': app_settings,
                'recentTotals': recent_totals,
                'surfaceDefinitions': build_surface_boot_registry(include_disabled=False),
                'videoContract': build_video_contract_boot_payload(),
                'extensionFrontendHooks': build_frontend_hook_registry(),
            },
            'phase01_goal_map': phase01_goal_map,
            'surface_definitions': surface_definitions,
        },
    )


def wait_for_server_ready(url: str = READINESS_URL, timeout_seconds: float = READINESS_TIMEOUT_SECONDS, poll_interval_seconds: float = READINESS_POLL_INTERVAL_SECONDS) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 1.0)
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.6) as response:
                status = getattr(response, 'status', 200) or 200
                if 200 <= status < 500:
                    return True
        except (OSError, URLError):
            pass
        time.sleep(max(poll_interval_seconds, 0.05))
    return False


def open_browser_when_ready():
    if wait_for_server_ready():
        webbrowser.open_new(BROWSER_URL)


if __name__ == '__main__':
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    import uvicorn

    uvicorn.run('neo_studio_v1.app:app', host=APP_HOST, port=APP_PORT, reload=True)
