from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse

from ..utils.extension_registry import (
    ensure_extension_registry,
    get_extension_manifest_standard,
    extension_allowed_for_family,
    list_extension_packs,
    list_workflow_packs,
    registry_counts,
    set_extension_pack_enabled,
    upsert_extension_pack,
    validate_manifest_payload,
    rebuild_extension_registry,
    build_frontend_hook_registry,

    install_extension_from_zip,
    install_extension_from_git,
    update_extension,
    remove_extension,
    repair_extension_registry,
    open_extension_folder,
    get_extension_manifest,
    get_extension_log,
    build_extension_health_report,
    disable_broken_extensions,
    clear_extension_cache,
    get_workflow_pack,
    get_workflow_pack_content,
    _find_pack,
)
from ..utils.extension_backend_hooks import build_backend_hook_registry, get_backend_hook_status
from .common import json_error, json_exception

router = APIRouter()


@router.get('/api/extensions/registry')
async def api_extension_registry(surface: str = '', target_surface: str = '', family: str = '', workspace: str = ''):
    try:
        ensure_extension_registry()
        return JSONResponse({
            'ok': True,
            'counts': registry_counts(),
            'extension_packs': list_extension_packs(surface=surface, target_surface=target_surface, family=family, workspace=workspace),
            'workflow_packs': list_workflow_packs(surface=surface, family=family),
        })
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension registry.', default_status=500)




@router.post('/api/extensions/registry/rescan')
async def api_extension_registry_rescan():
    try:
        registry = rebuild_extension_registry()
        return JSONResponse({
            'ok': True,
            'counts': registry_counts(),
            'extension_packs': registry.get('extension_packs', []),
            'workflow_packs': registry.get('workflow_packs', []),
        })
    except Exception as exc:
        return json_exception(exc, default_message='Could not rescan extension registry.', default_status=500)


@router.get('/api/extensions/packs')
async def api_extension_packs(surface: str = '', target_surface: str = '', family: str = '', workspace: str = '', enabled_only: bool = False):
    try:
        return JSONResponse({
            'ok': True,
            'packs': list_extension_packs(surface=surface, target_surface=target_surface, family=family, workspace=workspace, enabled_only=enabled_only),
            'counts': registry_counts(),
        })
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension packs.', default_status=500)


@router.get('/api/extensions/workflow-packs')
async def api_workflow_packs(surface: str = '', family: str = '', enabled_only: bool = False):
    try:
        return JSONResponse({'ok': True, 'packs': list_workflow_packs(surface=surface, family=family, enabled_only=enabled_only), 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load workflow packs.', default_status=500)




@router.get('/api/extensions/workflow-packs/{workflow_id}')
async def api_workflow_pack_detail(workflow_id: str):
    try:
        result = get_workflow_pack(workflow_id)
        if not result.get('ok'):
            return json_error(result.get('error') or 'Workflow pack was not found.', 404)
        return JSONResponse(result)
    except Exception as exc:
        return json_exception(exc, default_message='Could not load workflow pack.', default_status=500)


@router.get('/api/extensions/workflow-packs/{workflow_id}/content')
async def api_workflow_pack_content(workflow_id: str):
    try:
        result = get_workflow_pack_content(workflow_id)
        if not result.get('ok'):
            return json_error(result.get('error') or 'Workflow pack content was not found.', 404)
        return JSONResponse(result)
    except Exception as exc:
        return json_exception(exc, default_message='Could not load workflow pack content.', default_status=500)

@router.get('/api/extensions/runtime')
async def api_extension_runtime(target_surface: str = 'image', family: str = '', workspace: str = '', enabled_only: bool = True):
    try:
        packs = list_extension_packs(target_surface=target_surface, family=family, workspace=workspace, enabled_only=enabled_only)
        return JSONResponse({'ok': True, 'target_surface': target_surface, 'family': family, 'workspace': workspace, 'extensions': packs, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension runtime map.', default_status=500)




@router.get('/api/extensions/frontend-hooks')
async def api_extension_frontend_hooks(target_surface: str = '', mount_type: str = '', enabled_only: bool = True):
    try:
        return JSONResponse(build_frontend_hook_registry(target_surface=target_surface, mount_type=mount_type, enabled_only=enabled_only))
    except Exception as exc:
        return json_exception(exc, default_message='Could not load frontend extension hooks.', default_status=500)


@router.get('/api/extensions/backend-hooks')
async def api_extension_backend_hooks(enabled_only: bool = True):
    try:
        return JSONResponse(build_backend_hook_registry(enabled_only=enabled_only))
    except Exception as exc:
        return json_exception(exc, default_message='Could not load backend extension hooks.', default_status=500)


@router.get('/api/extensions/backend-hooks/{extension_id}')
async def api_extension_backend_hook_status(extension_id: str):
    try:
        return JSONResponse(get_backend_hook_status(extension_id))
    except Exception as exc:
        return json_exception(exc, default_message='Could not load backend extension hook status.', default_status=500)


@router.get('/api/extensions/assets/{extension_id}/{asset_path:path}')
async def api_extension_asset(extension_id: str, asset_path: str):
    try:
        pack, _, _ = _find_pack(extension_id)
        if not pack or not pack.get('enabled', True) or pack.get('status') != 'enabled':
            return json_error('Extension asset was not found or extension is disabled.', 404)
        root_text = str(pack.get('extension_dir') or '').strip()
        if not root_text:
            return json_error('Extension folder is not registered.', 404)
        root = Path(root_text).resolve()
        requested = (root / asset_path).resolve()
        if root not in requested.parents and requested != root:
            return json_error('Extension asset path is outside the extension folder.', 400)
        if not requested.exists() or not requested.is_file():
            return json_error('Extension asset was not found.', 404)
        return FileResponse(str(requested))
    except Exception as exc:
        return json_exception(exc, default_message='Could not serve extension asset.', default_status=500)

@router.get('/api/extensions/eligibility')
async def api_extension_eligibility(extension_id: str, family: str = ''):
    try:
        return JSONResponse({'ok': True, **extension_allowed_for_family(extension_id, family)})
    except Exception as exc:
        return json_exception(exc, default_message='Could not evaluate extension eligibility.', default_status=500)


@router.post('/api/extensions/packs')
async def api_extension_pack_upsert(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Extension pack payload was invalid.', 400)
        record = upsert_extension_pack(payload)
        return JSONResponse({'ok': True, 'record': record, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not save extension pack.', default_status=500)


@router.post('/api/extensions/packs/toggle')
async def api_extension_pack_toggle(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Toggle payload was invalid.', 400)
        extension_id = str(payload.get('extension_id') or '').strip()
        if not extension_id:
            return json_error('Extension pack id is required.', 400)
        record = set_extension_pack_enabled(extension_id, bool(payload.get('enabled', True)))
        if not record:
            return json_error('Extension pack was not found.', 404)
        return JSONResponse({'ok': True, 'record': record, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not toggle extension pack.', default_status=500)


@router.get('/api/extensions/manifest-standard')
async def api_extension_manifest_standard():
    try:
        return JSONResponse({'ok': True, **get_extension_manifest_standard()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension manifest standard.', default_status=500)


@router.post('/api/extensions/manifest-validate')
async def api_extension_manifest_validate(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Manifest payload was invalid.', 400)
        return JSONResponse(validate_manifest_payload(payload))
    except Exception as exc:
        return json_exception(exc, default_message='Could not validate extension manifest.', default_status=500)


# -----------------------------
# Phase 6: Extension Manager upgrade actions
# -----------------------------

@router.post('/api/extensions/install/zip')
async def api_extension_install_zip(request: Request):
    try:
        form = await request.form()
        upload = form.get('file') or form.get('zip')
        overwrite = str(form.get('overwrite') or '').lower() in {'1', 'true', 'yes', 'on'}
        enable = str(form.get('enable') or 'true').lower() not in {'0', 'false', 'no', 'off'}
        if upload is None or not hasattr(upload, 'filename'):
            return json_error('Extension ZIP upload is required.', 400)
        suffix = Path(str(getattr(upload, 'filename', '') or 'extension.zip')).suffix or '.zip'
        with tempfile.NamedTemporaryFile(prefix='neo_ext_upload_', suffix=suffix, delete=False) as tmp:
            content = await upload.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            result = install_extension_from_zip(tmp_path, overwrite=overwrite, enable=enable)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not install extension ZIP.', default_status=500)


@router.post('/api/extensions/install/git')
async def api_extension_install_git(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return json_error('Git install payload was invalid.', 400)
        result = install_extension_from_git(
            str(payload.get('git_url') or payload.get('url') or '').strip(),
            branch=str(payload.get('branch') or '').strip(),
            overwrite=bool(payload.get('overwrite', False)),
            enable=bool(payload.get('enable', True)),
        )
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not install extension from Git.', default_status=500)


@router.post('/api/extensions/update')
async def api_extension_update(request: Request):
    try:
        payload = await request.json()
        extension_id = str((payload if isinstance(payload, dict) else {}).get('extension_id') or '').strip()
        if not extension_id:
            return json_error('Extension id is required.', 400)
        result = update_extension(extension_id)
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not update extension.', default_status=500)


@router.post('/api/extensions/remove')
async def api_extension_remove(request: Request):
    try:
        payload = await request.json()
        extension_id = str((payload if isinstance(payload, dict) else {}).get('extension_id') or '').strip()
        if not extension_id:
            return json_error('Extension id is required.', 400)
        result = remove_extension(extension_id, delete_files=bool((payload if isinstance(payload, dict) else {}).get('delete_files', True)))
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not remove extension.', default_status=500)


@router.post('/api/extensions/repair')
async def api_extension_repair(request: Request):
    try:
        payload = await request.json()
        extension_id = str((payload if isinstance(payload, dict) else {}).get('extension_id') or '').strip()
        result = repair_extension_registry(extension_id)
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not repair extension registry.', default_status=500)


@router.post('/api/extensions/open-folder')
async def api_extension_open_folder(request: Request):
    try:
        payload = await request.json()
        extension_id = str((payload if isinstance(payload, dict) else {}).get('extension_id') or '').strip()
        if not extension_id:
            return json_error('Extension id is required.', 400)
        return JSONResponse(open_extension_folder(extension_id))
    except Exception as exc:
        return json_exception(exc, default_message='Could not open extension folder.', default_status=500)


@router.get('/api/extensions/manifest/{extension_id}')
async def api_extension_manifest(extension_id: str):
    try:
        return JSONResponse(get_extension_manifest(extension_id))
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension manifest.', default_status=500)


@router.get('/api/extensions/logs/{extension_id}')
async def api_extension_logs(extension_id: str):
    try:
        return JSONResponse(get_extension_log(extension_id))
    except Exception as exc:
        return json_exception(exc, default_message='Could not load extension log.', default_status=500)

# -----------------------------
# Phase 11: Extension Health + Repair
# -----------------------------

@router.get('/api/extensions/health')
async def api_extension_health():
    try:
        return JSONResponse(build_extension_health_report())
    except Exception as exc:
        return json_exception(exc, default_message='Could not build extension health report.', default_status=500)


@router.post('/api/extensions/disable-broken')
async def api_extension_disable_broken():
    try:
        result = disable_broken_extensions()
        return JSONResponse({'ok': True, **result, 'counts': registry_counts()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not disable broken extensions.', default_status=500)


@router.post('/api/extensions/cache/clear')
async def api_extension_cache_clear():
    try:
        return JSONResponse({'ok': True, **clear_extension_cache()})
    except Exception as exc:
        return json_exception(exc, default_message='Could not clear extension cache.', default_status=500)
