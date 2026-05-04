from __future__ import annotations

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from ..utils.caption_contract import normalize_caption_mode
from ..utils.kobold import clamp_float, clamp_int
from ..utils.library_captions import image_files_in_folder
from ..utils.logging_utils import get_logger
from .batch_runtime import (
    batch_status_payload,
    cancel_post_action,
    create_batch_job,
    create_resume_batch_job,
    create_retry_batch_job,
    export_batch_log_payload,
    list_saved_batch_jobs,
    normalized_batch_params,
    request_batch_cancel,
)
from .common import json_error, parse_bool, parse_exts

logger = get_logger(__name__)
router = APIRouter()


@router.get('/api/caption-batch-recent')
async def api_caption_batch_recent():
    return JSONResponse({'ok': True, 'jobs': list_saved_batch_jobs()})


@router.post('/api/caption-batch-preview')
async def api_caption_batch_preview(
    folder_path: str = Form(...),
    recursive: str = Form('false'),
    include_exts: str = Form(''),
):
    try:
        images = image_files_in_folder(folder_path, recursive=parse_bool(recursive), include_exts=parse_exts(include_exts))
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    sample = [str(p) for p in images[:20]]
    return JSONResponse({'ok': True, 'count': len(images), 'sample': sample, 'message': f'Found {len(images)} matching image files.'})


@router.post('/api/caption-batch-start')
async def api_caption_batch_start(
    model: str = Form('default'),
    mode: str = Form('dataset'),
    folder_path: str = Form(...),
    category: str = Form('uncategorized'),
    base_name: str = Form('Batch_Caption'),
    numbering_start: int = Form(1),
    overwrite_existing: str = Form('false'),
    skip_existing_txt: str = Form('true'),
    skip_duplicates: str = Form('true'),
    recursive: str = Form('false'),
    include_exts: str = Form(''),
    prompt_style: str = Form('Stable Diffusion Prompt'),
    caption_length: str = Form('any'),
    custom_prompt: str = Form(''),
    max_new_tokens: int = Form(160),
    temperature: float = Form(0.2),
    top_p: float = Form(0.9),
    top_k: int = Form(40),
    prefix: str = Form(''),
    suffix: str = Form(''),
    output_style: str = Form('Auto (match input)'),
    output_folder: str = Form(''),
    component_type: str = Form(''),
    caption_mode: str = Form('full_image'),
    detail_level: str = Form('detailed'),
    post_task_action: str = Form('none'),
    dataset_caption_images: str = Form('true'),
    dataset_save_txt: str = Form('true'),
    dataset_rename_images: str = Form('true'),
    dataset_transfer_mode: str = Form('copy'),
    dataset_skip_processed: str = Form('true'),
    dataset_name_prefix: str = Form('character'),
    dataset_name_pattern: str = Form('{prefix}_{num}'),
    dataset_number_padding: int = Form(4),
    dataset_log_format: str = Form('csv'),
):
    try:
        images = image_files_in_folder(folder_path, recursive=parse_bool(recursive), include_exts=parse_exts(include_exts))
    except Exception as e:
        logger.exception('Validation error in API request')
        return json_error(str(e), 400)
    if not images:
        return json_error('No supported image files found in that folder.', 400)
    if (mode or 'dataset').strip().lower() == 'dataset' and not str(output_folder or '').strip():
        return json_error('Dataset Preparation needs an output folder.', 400)
    if normalize_caption_mode(caption_mode) == 'custom_crop':
        return json_error('Batch captioning does not support Custom crop mode. Use Full image, Face only, Person / character, Outfit, Pose, or Location for batch runs.', 400)

    params = normalized_batch_params(
        model=model,
        mode=mode,
        folder_path=folder_path,
        category=category,
        base_name=base_name,
        numbering_start=numbering_start,
        overwrite_existing=overwrite_existing,
        skip_existing_txt=skip_existing_txt,
        skip_duplicates=skip_duplicates,
        recursive=recursive,
        include_exts=include_exts,
        prompt_style=prompt_style,
        caption_length=caption_length,
        custom_prompt=custom_prompt,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        prefix=prefix,
        suffix=suffix,
        output_style=output_style,
        output_folder=output_folder,
        component_type=component_type,
        caption_mode=caption_mode,
        detail_level=detail_level,
        post_task_action=post_task_action,
        dataset_caption_images=dataset_caption_images,
        dataset_save_txt=dataset_save_txt,
        dataset_rename_images=dataset_rename_images,
        dataset_transfer_mode=dataset_transfer_mode,
        dataset_skip_processed=dataset_skip_processed,
        dataset_name_prefix=dataset_name_prefix,
        dataset_name_pattern=dataset_name_pattern,
        dataset_number_padding=dataset_number_padding,
        dataset_log_format=dataset_log_format,
        clamp_int=clamp_int,
        clamp_float=clamp_float,
    )
    if params['mode'] == 'dataset' and params.get('dataset_rename_images'):
        params['dataset_sequence_map'] = {str(img): params['numbering_start'] + idx for idx, img in enumerate(images)}
    return JSONResponse(create_batch_job(params, len(images)))


@router.get('/api/caption-batch-status')
async def api_caption_batch_status(job_id: str = Query('')):
    payload = batch_status_payload((job_id or '').strip())
    if not payload:
        return json_error('Batch job not found.', 404)
    return JSONResponse(payload)


@router.post('/api/caption-batch-cancel')
async def api_caption_batch_cancel(job_id: str = Form(...)):
    payload = request_batch_cancel((job_id or '').strip())
    if not payload:
        return json_error('Batch job not found.', 404)
    return JSONResponse(payload)


@router.post('/api/caption-batch-resume')
async def api_caption_batch_resume(job_id: str = Form(...)):
    payload = create_resume_batch_job((job_id or '').strip())
    if not payload:
        return json_error('No remaining files were found for that batch.', 400)
    return JSONResponse(payload)


@router.post('/api/caption-batch-retry-failed')
async def api_caption_batch_retry_failed(job_id: str = Form(...)):
    payload = create_retry_batch_job((job_id or '').strip())
    if not payload:
        return json_error('No failed files were found for that batch.', 400)
    return JSONResponse(payload)


@router.get('/api/caption-batch-export-log')
async def api_caption_batch_export_log(job_id: str = Query('')):
    payload = export_batch_log_payload((job_id or '').strip())
    if not payload:
        return json_error('Batch job not found.', 404)
    return JSONResponse(payload)


@router.post('/api/caption-batch-cancel-post-action')
async def api_caption_batch_cancel_post_action(job_id: str = Form(...)):
    payload = cancel_post_action((job_id or '').strip())
    if not payload:
        return json_error('Batch job not found.', 404)
    return JSONResponse(payload)


@router.post('/api/caption-batch')
async def api_caption_batch_legacy(**kwargs):
    return json_error('The legacy one-shot batch endpoint has been retired. Use /api/caption-batch-start instead.', 410)
