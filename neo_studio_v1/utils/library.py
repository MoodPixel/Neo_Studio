from __future__ import annotations

"""Compatibility shim for the split Neo Studio library helpers.

This module preserves the original import surface while the implementation now
lives in smaller focused modules.
"""

from .library_captions import dataset_txt_output_path, image_files_in_folder, save_caption, save_caption_from_path
from .library_constants import BUILTIN_CAPTION_PRESETS, BUILTIN_PROMPT_PRESETS, DEFAULT_ROOT, FORMAT_TO_SUFFIX, IMAGE_EXTS, MAX_TEMP_AGE_HOURS, MAX_UPLOAD_BYTES, NEO_LIBRARY_SETTINGS_PATH, SETTINGS_PATH, TEMP_DIR, USER_DATA_DIR
from .library_presets import delete_caption_preset, delete_prompt_preset, export_presets_payload, get_caption_presets, get_last_used_caption_preset, get_last_used_prompt_preset, get_prompt_presets, import_presets_payload, save_caption_preset, save_prompt_preset, set_last_used_caption_preset, set_last_used_prompt_preset
from .library_prompts import delete_prompt_record, get_prompt_record, prompt_categories, prompt_entries, prompt_names, save_prompt, unique_prompt_name, update_prompt_record
from .library_settings_store import get_last_used_category, get_library_root, list_categories, set_last_used_category, set_library_root
from .library_stats import stats
from .library_storage import cleanup_temp_uploads, delete_temp_upload, save_temp_upload, temp_path_from_id

__all__ = [
    'BUILTIN_CAPTION_PRESETS',
    'BUILTIN_PROMPT_PRESETS',
    'DEFAULT_ROOT',
    'FORMAT_TO_SUFFIX',
    'IMAGE_EXTS',
    'MAX_TEMP_AGE_HOURS',
    'MAX_UPLOAD_BYTES',
    'NEO_LIBRARY_SETTINGS_PATH',
    'SETTINGS_PATH',
    'TEMP_DIR',
    'USER_DATA_DIR',
    'cleanup_temp_uploads',
    'dataset_txt_output_path',
    'delete_caption_preset',
    'delete_prompt_preset',
    'delete_prompt_record',
    'delete_temp_upload',
    'export_presets_payload',
    'get_caption_presets',
    'get_last_used_caption_preset',
    'get_last_used_category',
    'get_last_used_prompt_preset',
    'get_library_root',
    'get_prompt_presets',
    'get_prompt_record',
    'image_files_in_folder',
    'import_presets_payload',
    'list_categories',
    'prompt_categories',
    'prompt_entries',
    'prompt_names',
    'save_caption',
    'save_caption_from_path',
    'save_caption_preset',
    'save_prompt',
    'save_prompt_preset',
    'save_temp_upload',
    'set_last_used_caption_preset',
    'set_last_used_category',
    'set_last_used_prompt_preset',
    'set_library_root',
    'stats',
    'temp_path_from_id',
    'unique_prompt_name',
    'update_prompt_record',
]

cleanup_temp_uploads()
