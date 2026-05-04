from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from .backend_manager import normalize_url
from ..contracts.regional_prompting import build_regional_promotion_gate
from ..config.feature_flags import REGIONAL_ENABLE_NODE_BACKEND, REGIONAL_ENABLE_DENSE_DIFFUSION, REGIONAL_ENABLE_EXPERIMENTAL


class ComfyBackendAdapter:
    def __init__(self, base_url: str, timeout_sec: int = 30):
        self.base_url = normalize_url(base_url)
        self.timeout_sec = max(5, int(timeout_sec or 30))
        self.client_id = str(uuid4())

    def _url(self, path: str) -> str:
        path = '/' + str(path or '').lstrip('/')
        return f'{self.base_url}{path}'

    async def _get_json(self, path: str):
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_sec) as client:
            response = await client.get(self._url(path))
            response.raise_for_status()
            return response.json()

    async def _post_json(self, path: str, payload: Dict[str, Any]):
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_sec) as client:
            response = await client.post(self._url(path), json=payload)
            if response.is_error:
                detail = ''
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        detail = str(data.get('error') or data.get('message') or data.get('detail') or '').strip()
                    elif data not in (None, ''):
                        detail = str(data).strip()
                except Exception:
                    detail = ''
                if not detail:
                    detail = str(response.text or '').strip()
                message = f"Client error '{response.status_code} {response.reason_phrase}' for url '{response.url}'"
                if detail:
                    message = f"{message}: {detail}"
                raise httpx.HTTPStatusError(message, request=response.request, response=response)
            if response.status_code == 204 or not response.content or not response.text.strip():
                return {'ok': True, 'status_code': response.status_code}
            try:
                return response.json()
            except ValueError:
                return {
                    'ok': True,
                    'status_code': response.status_code,
                    'text': response.text,
                }

    async def get_system_stats(self):
        return await self._get_json('/system_stats')

    async def get_queue(self):
        return await self._get_json('/queue')

    async def get_prompt_status(self):
        return await self._get_json('/prompt')

    async def get_history(self, prompt_id: str | None = None):
        if prompt_id:
            return await self._get_json(f'/history/{prompt_id}')
        return await self._get_json('/history')

    async def get_features(self):
        return await self._get_json('/features')

    async def get_object_info(self, node_name: str | None = None):
        if node_name:
            try:
                return await self._get_json(f'/object_info/{node_name}')
            except Exception:
                pass
        return await self._get_json('/object_info')

    async def get_models(self, folder: str):
        return await self._get_json(f'/models/{folder}')

    async def get_model_folders(self):
        return await self._get_json('/models')

    async def queue_prompt(self, prompt_graph: Dict[str, Any], prompt_id: str | None = None):
        payload: Dict[str, Any] = {
            'prompt': prompt_graph,
            'client_id': self.client_id,
        }
        if prompt_id:
            payload['prompt_id'] = prompt_id
        return await self._post_json('/prompt', payload)

    async def interrupt(self, prompt_id: str | None = None):
        payload: Dict[str, Any] = {}
        if prompt_id:
            payload['prompt_id'] = str(prompt_id)
        return await self._post_json('/interrupt', payload)

    async def clear_queue(self):
        return await self._post_json('/queue', {'clear': True})

    async def upload_image(self, content: bytes, filename: str, *, subfolder: str = 'neo_studio', file_type: str = 'input', overwrite: bool = True):
        data = {
            'overwrite': 'true' if overwrite else 'false',
            'type': file_type,
            'subfolder': subfolder,
        }
        files = {
            'image': (filename, content),
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_sec) as client:
            response = await client.post(self._url('/upload/image'), data=data, files=files)
            response.raise_for_status()
            return response.json()

    async def upload_mask(self, content: bytes, filename: str, *, subfolder: str = 'neo_studio', file_type: str = 'input', overwrite: bool = True):
        data = {
            'overwrite': 'true' if overwrite else 'false',
            'type': file_type,
            'subfolder': subfolder,
        }
        files = {
            'image': (filename, content),
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_sec) as client:
            response = await client.post(self._url('/upload/mask'), data=data, files=files)
            response.raise_for_status()
            return response.json()

    def build_view_url(self, filename: str, subfolder: str = '', file_type: str = 'output') -> str:
        params = {'filename': filename, 'type': file_type}
        if subfolder:
            params['subfolder'] = subfolder
        return self._url('/view') + '?' + urlencode(params)

    @staticmethod
    def _clean_string_list(values):
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
        return []

    @classmethod
    def _normalize_model_list_payload(cls, payload):
        if isinstance(payload, list):
            return cls._clean_string_list(payload)
        if isinstance(payload, dict):
            for key in ('models', 'items', 'files', 'choices', 'options', 'names'):
                values = payload.get(key)
                if isinstance(values, list):
                    normalized = []
                    for item in values:
                        if isinstance(item, dict):
                            normalized.append(str(item.get('name') or item.get('filename') or item.get('path') or item.get('value') or '').strip())
                        else:
                            normalized.append(str(item).strip())
                    return cls._clean_string_list(normalized)
        return []

    @classmethod
    def _merge_string_lists(cls, *groups):
        merged = []
        seen = set()
        for group in groups:
            for item in cls._clean_string_list(group):
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    @classmethod
    def _extract_combo_values(cls, raw):
        if isinstance(raw, dict):
            for key in ('choices', 'options', 'enum', 'values'):
                if key in raw:
                    found = cls._extract_combo_values(raw.get(key))
                    if found:
                        return found
            return []
        if isinstance(raw, (list, tuple)):
            if raw and isinstance(raw[0], (list, tuple)):
                return cls._clean_string_list(list(raw[0]))
            if raw and all(isinstance(item, str) for item in raw):
                return cls._clean_string_list(list(raw))
        return []

    @classmethod
    def _extract_node_required_choices(cls, object_info: Any, *field_names: str):
        if not isinstance(object_info, dict):
            return []
        input_meta = object_info.get('input')
        if not isinstance(input_meta, dict):
            return []
        required = input_meta.get('required')
        if not isinstance(required, dict):
            return []
        merged = []
        for field_name in field_names:
            merged = cls._merge_string_lists(merged, cls._extract_combo_values(required.get(field_name)))
        return merged

    async def get_catalog(self):
        checkpoints = []
        unet = []
        diffusion_models = []
        clip = []
        text_encoders = []
        loras = []
        vae = []
        controlnet = []
        ipadapter = []
        clip_vision = []
        upscale_models = []
        facerestore_models = []
        samplers = []
        schedulers = []
        folders = []
        try:
            folders = await self.get_model_folders()
        except Exception:
            folders = []
        for folder_name, target in (
            ('checkpoints', 'checkpoints'),
            ('unet', 'unet'),
            ('diffusion_models', 'diffusion_models'),
            ('clip', 'clip'),
            ('text_encoders', 'text_encoders'),
            ('loras', 'loras'),
            ('vae', 'vae'),
            ('controlnet', 'controlnet'),
            ('ipadapter', 'ipadapter'),
            ('clip_vision', 'clip_vision'),
            ('upscale_models', 'upscale_models'),
            ('facerestore_models', 'facerestore_models'),
        ):
            try:
                values = self._normalize_model_list_payload(await self.get_models(folder_name))
            except Exception:
                values = []
            if target == 'checkpoints':
                checkpoints = values
            elif target == 'unet':
                unet = values
            elif target == 'diffusion_models':
                diffusion_models = values
            elif target == 'clip':
                clip = values
            elif target == 'text_encoders':
                text_encoders = values
            elif target == 'loras':
                loras = values
            elif target == 'vae':
                vae = values
            elif target == 'controlnet':
                controlnet = values
            elif target == 'ipadapter':
                ipadapter = values
            elif target == 'clip_vision':
                clip_vision = values
            elif target == 'upscale_models':
                upscale_models = values
            elif target == 'facerestore_models':
                facerestore_models = values

        merged_unet = self._merge_string_lists(unet, diffusion_models)
        merged_clip = self._merge_string_lists(clip, text_encoders)

        async def _get_node_info(node_name: str) -> dict:
            try:
                info = await self.get_object_info(node_name)
            except Exception:
                return {}
            if isinstance(info, dict) and node_name in info:
                info = info.get(node_name)
            return info if isinstance(info, dict) else {}

        async def _node_exists(node_name: str) -> bool:
            info = await _get_node_info(node_name)
            return bool(info)

        async def _first_node_info(*node_names: str) -> dict:
            for node_name in node_names:
                info = await _get_node_info(node_name)
                if info:
                    return info
            return {}

        async def _node_exists_any(*node_names: str) -> bool:
            for node_name in node_names:
                if await _node_exists(node_name):
                    return True
            return False

        # GGUF loader nodes on some Comfy builds expose the real model choices only
        # through object_info, not through /models/* catalog endpoints.
        gguf_unet_info = await _first_node_info('UnetLoaderGGUF', 'LoaderGGUF')
        gguf_dual_clip_info = await _get_node_info('DualCLIPLoaderGGUF')
        gguf_single_clip_info = await _first_node_info('CLIPLoaderGGUF', 'ClipLoaderGGUF')
        gguf_vae_info = await _get_node_info('VaeGGUF')

        gguf_unet_choices = self._extract_node_required_choices(gguf_unet_info, 'unet_name', 'gguf_name')
        gguf_clip_choices = self._merge_string_lists(
            self._extract_node_required_choices(gguf_dual_clip_info, 'clip_name1', 'clip_name2'),
            self._extract_node_required_choices(gguf_single_clip_info, 'clip_name'),
        )
        gguf_vae_choices = self._extract_node_required_choices(gguf_vae_info, 'vae_name')

        merged_unet = self._merge_string_lists(merged_unet, gguf_unet_choices)
        merged_clip = self._merge_string_lists(merged_clip, gguf_clip_choices)
        vae = self._merge_string_lists(vae, gguf_vae_choices)

        rgthree_lora_choices = []
        try:
            all_object_info = await self.get_object_info()
        except Exception:
            all_object_info = {}
        if isinstance(all_object_info, dict):
            for node_name, info in all_object_info.items():
                lowered = str(node_name or '').casefold()
                if 'lora' not in lowered:
                    continue
                if 'rgthree' not in lowered and 'power lora' not in lowered:
                    continue
                rgthree_lora_choices = self._merge_string_lists(
                    rgthree_lora_choices,
                    self._extract_node_required_choices(
                        info,
                        'lora', 'lora_name', 'lora_1', 'lora_01', 'lora1', 'lora_a',
                        'lora_2', 'lora_02', 'lora2', 'lora_b', 'lora_3', 'lora_03', 'lora3',
                        'lora_4', 'lora_04', 'lora4', 'lora_5', 'lora_05', 'lora5',
                    ),
                )
        loras = self._merge_string_lists(loras, rgthree_lora_choices)

        try:
            object_info = await self.get_object_info('KSampler')
        except Exception:
            object_info = {}
        node_info = object_info.get('KSampler') if isinstance(object_info, dict) and 'KSampler' in object_info else object_info
        if isinstance(node_info, dict):
            required = ((node_info.get('input') or {}).get('required') or {}) if isinstance(node_info.get('input'), dict) else {}
            samplers = self._extract_combo_values(required.get('sampler_name'))
            schedulers = self._extract_combo_values(required.get('scheduler'))

        # Phase 1 RES4LYF detection: expose capability only. Do not mutate
        # workflow graphs here. The Image tab can safely opt into RES sampler
        # names only when ComfyUI reports them through object_info/catalog.
        res4lyf_sampler_candidates = ['res_2m', 'res_3s', 'res_5s', 'res_2s']
        res4lyf_scheduler_candidates = ['beta57']
        res4lyf_node_candidates = [
            'ClownsharKSampler',
            'ClownsharKSampler_Beta',
            'Legacy2_ClownsharKSampler',
            'ClownSampler',
            'SharkSampler',
        ]
        res4lyf_nodes = []
        if isinstance(all_object_info, dict):
            for _node_name in all_object_info.keys():
                _node_text = str(_node_name or '')
                _node_lower = _node_text.casefold()
                if (
                    _node_text in res4lyf_node_candidates
                    or 'clownshark' in _node_lower
                    or 'clownshar' in _node_lower
                    or 'res4lyf' in _node_lower
                ):
                    res4lyf_nodes.append(_node_text)
        res4lyf_nodes = self._clean_string_list(res4lyf_nodes)
        sampler_set = set(samplers or [])
        scheduler_set = set(schedulers or [])
        res4lyf_samplers = [item for item in res4lyf_sampler_candidates if item in sampler_set]
        res4lyf_schedulers = [item for item in res4lyf_scheduler_candidates if item in scheduler_set]
        res4lyf = {
            'installed': bool(res4lyf_nodes or res4lyf_samplers or res4lyf_schedulers),
            'status': 'ready' if (res4lyf_samplers or res4lyf_nodes) else 'missing',
            'nodes': res4lyf_nodes,
            'has_clownshark_sampler': any('clownshark' in str(item).casefold() or 'clownshar' in str(item).casefold() for item in res4lyf_nodes),
            'samplers': res4lyf_samplers,
            'schedulers': res4lyf_schedulers,
            'recommended_presets': [
                {'id': 'res_balanced', 'label': 'RES Balanced', 'sampler': 'res_2m', 'scheduler': 'beta57' if 'beta57' in res4lyf_schedulers else '', 'available': 'res_2m' in res4lyf_samplers},
                {'id': 'res_detail_slow', 'label': 'RES Detail Slow', 'sampler': 'res_5s', 'scheduler': 'beta57' if 'beta57' in res4lyf_schedulers else '', 'available': 'res_5s' in res4lyf_samplers},
                {'id': 'res_experimental', 'label': 'RES Experimental', 'sampler': 'res_3s', 'scheduler': 'beta57' if 'beta57' in res4lyf_schedulers else '', 'available': 'res_3s' in res4lyf_samplers},
            ],
            'notes': [
                'RES4LYF detection is passive in this phase; Neo still builds the existing KSampler workflows.',
                'Only expose RES presets in the UI when the listed sampler/scheduler values are available in this catalog.',
                'Keep ClownsharKSampler support behind a later experimental workflow lane.',
            ],
        }

        dynamic_thresholding_nodes = []
        for _dt_node in ('DynamicThresholdingSimple', 'DynamicThresholdingFull'):
            if await _node_exists(_dt_node):
                dynamic_thresholding_nodes.append(_dt_node)
        dynamic_thresholding = {
            'available': bool(dynamic_thresholding_nodes),
            'nodes': dynamic_thresholding_nodes,
            'simple': 'DynamicThresholdingSimple' in dynamic_thresholding_nodes,
            'full': 'DynamicThresholdingFull' in dynamic_thresholding_nodes,
            'recommended_injection_point': 'after model patches / before sampler',
            'install_hint': '' if dynamic_thresholding_nodes else 'Install mcmonkeyprojects/sd-dynamic-thresholding in ComfyUI/custom_nodes, then restart ComfyUI.',
        }

        features = {
            'dynamic_thresholding': bool(dynamic_thresholding_nodes),
            'dynamic_thresholding_simple': 'DynamicThresholdingSimple' in dynamic_thresholding_nodes,
            'dynamic_thresholding_full': 'DynamicThresholdingFull' in dynamic_thresholding_nodes,
            'controlnet_loader': await _node_exists('ControlNetLoader'),
            'controlnet_apply_advanced': await _node_exists('ControlNetApplyAdvanced'),
            'clip_vision_loader': await _node_exists('CLIPVisionLoader'),
            'ipadapter_model_loader': await _node_exists('IPAdapterModelLoader'),
            'ipadapter_advanced': await _node_exists('IPAdapterAdvanced'),
            'ipadapter_unified_loader_faceid': await _node_exists('IPAdapterUnifiedLoaderFaceID'),
            'ipadapter_faceid': await _node_exists('IPAdapterFaceID'),
            'supir_upscale': await _node_exists('SUPIR_Upscale'),
            'gguf_unet_loader': await _node_exists_any('UnetLoaderGGUF', 'LoaderGGUF'),
            'gguf_dual_clip_loader': await _node_exists('DualCLIPLoaderGGUF'),
            'gguf_clip_loader': await _node_exists_any('CLIPLoaderGGUF', 'ClipLoaderGGUF'),
            'gguf_vae_loader': await _node_exists('VaeGGUF'),
            'qwen_text_encode_plus': await _node_exists('TextEncodeQwenImageEditPlus'),
            'qwen_model_sampling': await _node_exists('ModelSamplingAuraFlow'),
            'qwen_cfgnorm': await _node_exists('CFGNorm'),
            'controlnet_aux_openpose': bool(await _node_exists('OpenposePreprocessor') or await _node_exists('DWPreprocessor')),
            'controlnet_aux_depth': bool(await _node_exists('DepthAnythingV2Preprocessor') or await _node_exists('DepthAnythingPreprocessor') or await _node_exists('MiDaS-DepthMapPreprocessor') or await _node_exists('MiDaSDepthMapPreprocessor') or await _node_exists('Zoe-DepthMapPreprocessor') or await _node_exists('ZoeDepthMapPreprocessor')),
            'deepbooru_tagger': await _node_exists('DeepDanbooruCaption'),
            'face_restore_loader': await _node_exists('FaceRestoreModelLoader'),
            'face_restore_cf': await _node_exists('FaceRestoreCFWithModel'),
            'regional_image_to_mask': await _node_exists('ImageToMask'),
            'regional_conditioning_set_mask': await _node_exists('ConditioningSetMask'),
            'regional_conditioning_combine': await _node_exists('ConditioningCombine'),
            'regional_solid_mask': await _node_exists('SolidMask'),
            'regional_mask_composite': await _node_exists('MaskComposite'),
            'regional_dense_add_cond': await _node_exists('DenseDiffusionAddCondNode'),
            'regional_dense_apply': await _node_exists('DenseDiffusionApplyNode'),
            'regional_smz_normalize': await _node_exists('smZ Conditioning Normalize'),
            'regional_smz_clip_text_encode': await _node_exists('smZ CLIPTextEncode'),
            'res4lyf': bool(res4lyf.get('installed')),
            'res4lyf_ready': bool(res4lyf.get('status') == 'ready'),
            'res4lyf_clownshark_sampler': bool(res4lyf.get('has_clownshark_sampler')),
        }
        features['ipadapter_ready'] = bool(features['clip_vision_loader'] and features['ipadapter_model_loader'] and features['ipadapter_advanced'])
        features['ipadapter_faceid_ready'] = bool(features['clip_vision_loader'] and features['ipadapter_unified_loader_faceid'] and features['ipadapter_faceid'])
        features['supir_ready'] = bool(features['supir_upscale'])
        features['qwen_image_edit_ready'] = bool(features['gguf_unet_loader'] and features['gguf_clip_loader'] and features['qwen_text_encode_plus'])
        features['face_restore_ready'] = bool(features['face_restore_loader'] and features['face_restore_cf'])
        features['regional_native_ready'] = bool(features['regional_image_to_mask'] and features['regional_conditioning_set_mask'] and features['regional_conditioning_combine'] and features['regional_solid_mask'] and features['regional_mask_composite'])
        features['regional_impact_prompt'] = await _node_exists('RegionalPrompt')
        features['regional_impact_combine'] = await _node_exists('CombineRegionalPrompts')
        features['regional_impact_sampler'] = bool(await _node_exists('RegionalSampler') or await _node_exists('RegionalSamplerAdvanced'))
        features['regional_node_backend_ready'] = bool(features['regional_impact_prompt'] and features['regional_impact_combine'] and features['regional_impact_sampler'])
        regional_promotion_gate = build_regional_promotion_gate().get('gate', {})
        node_detected = bool(features['regional_node_backend_ready'])
        dense_detected = bool(features['regional_dense_add_cond'] and features['regional_dense_apply'] and features['regional_smz_normalize'])
        node_enabled = bool(node_detected and REGIONAL_ENABLE_NODE_BACKEND and REGIONAL_ENABLE_EXPERIMENTAL)
        dense_enabled = bool(dense_detected and REGIONAL_ENABLE_DENSE_DIFFUSION and REGIONAL_ENABLE_EXPERIMENTAL)
        regional_backend_capabilities = {
            'native': {
                'available': bool(features['regional_native_ready']),
                'backend_name': 'native_mask_conditioning',
                'supports_box_regions': bool(features['regional_native_ready']),
                'supports_mask_regions': bool(features['regional_native_ready']),
                'supports_negative_regions': bool(features['regional_native_ready']),
                'supports_priority_order': True,
                'supports_overlap_blend': True,
                'supports_falloff': True,
                'promotion_gate': regional_promotion_gate.get('native', {}),
            },
            'node': {
                'available': node_enabled,
                'detected': node_detected,
                'backend_name': 'impact_pack_regional' if node_detected else '',
                'supports_box_regions': bool(node_detected),
                'supports_mask_regions': False,
                'supports_negative_regions': False,
                'supports_priority_order': False,
                'supports_overlap_blend': False,
                'supports_falloff': False,
                'status': 'available' if node_enabled else 'missing_dependencies',
                'disabled_reason': 'Node backend dependencies are missing, so Neo will fall back to Native until Impact Pack regional nodes are available.',
                'required_components': ['RegionalPrompt', 'CombineRegionalPrompts', 'RegionalSampler|RegionalSamplerAdvanced'],
                'compiler_nodes': ['ToBasicPipe', 'KSamplerAdvancedProvider', 'RegionalPrompt', 'CombineRegionalPrompts', 'RegionalSamplerAdvanced'],
                'missing_components': [
                    *([] if features['regional_impact_prompt'] else ['RegionalPrompt']),
                    *([] if features['regional_impact_combine'] else ['CombineRegionalPrompts']),
                    *([] if features['regional_impact_sampler'] else ['RegionalSampler or RegionalSamplerAdvanced']),
                ],
                'promotion_gate': regional_promotion_gate.get('node', {}),
            },
            'dense_diffusion': {
                'available': False,
                'detected': dense_detected,
                'backend_name': 'dense_diffusion_regional' if dense_detected else '',
                'experimental': True,
                'status': 'hidden',
                'disabled_reason': 'Dense Diffusion is hidden in this build because the current environment still fails compatibility checks.',
                'supported_families': ['sdxl_sd'],
                'supported_modes_v1': ['txt2img'],
                'supported_modes_future': ['txt2img', 'img2img'],
                'supports_box_regions': True,
                'supports_mask_regions': True,
                'supports_negative_regions': False,
                'supports_priority_order': True,
                'supports_overlap_blend': True,
                'supports_falloff': True,
                'compiler_ready': False,
                'required_components': ['DenseDiffusionAddCondNode', 'DenseDiffusionApplyNode', 'smZ Conditioning Normalize'],
                'preferred_components': ['smZ CLIPTextEncode'],
                'optional_components': ['ControlNetLoader', 'DepthAnythingV2Preprocessor', 'ControlNetApplyAdvanced', 'UltralyticsDetectorProvider', 'BboxDetectorSEGS', 'ImpactSEGSOrderedFilter', 'MaskToSEGS', 'ZML_YoloToMask', 'ZML_MaskSeparateDistance', 'UltimateSDUpscale', 'rgthree utility nodes'],
                'compiler_nodes': ['smZ CLIPTextEncode|CLIPTextEncode', 'smZ Conditioning Normalize', 'DenseDiffusionAddCondNode', 'DenseDiffusionApplyNode'],
                'missing_components': [
                    *([] if features['regional_dense_add_cond'] else ['DenseDiffusionAddCondNode']),
                    *([] if features['regional_dense_apply'] else ['DenseDiffusionApplyNode']),
                    *([] if features['regional_smz_normalize'] else ['smZ Conditioning Normalize']),
                ],
                'missing_preferred_components': [
                    *([] if features['regional_smz_clip_text_encode'] else ['smZ CLIPTextEncode']),
                ],
                'notes': [
                    'Dense Diffusion is intentionally hidden in normal UI while the team focuses on the working Node backend path.',
                    'Per-region negatives stay intentionally limited; keep the global negative prompt as the main safety rail.',
                    'smZ CLIPTextEncode is preferred for closer workflow parity, but the minimal compiler can fall back to standard CLIPTextEncode once the backend is re-enabled.',
                ],
                'promotion_gate': regional_promotion_gate.get('dense_diffusion', {}),
            },
        }

        return {
            'folders': folders,
            'checkpoints': checkpoints if isinstance(checkpoints, list) else [],
            'unet': merged_unet,
            'diffusion_models': self._clean_string_list(diffusion_models),
            'clip': merged_clip,
            'text_encoders': self._clean_string_list(text_encoders),
            'loras': loras if isinstance(loras, list) else [],
            'vae': vae if isinstance(vae, list) else [],
            'controlnet': controlnet if isinstance(controlnet, list) else [],
            'ipadapter': ipadapter if isinstance(ipadapter, list) else [],
            'clip_vision': clip_vision if isinstance(clip_vision, list) else [],
            'upscale_models': upscale_models if isinstance(upscale_models, list) else [],
            'facerestore_models': facerestore_models if isinstance(facerestore_models, list) else [],
            'samplers': samplers,
            'schedulers': schedulers,
            'features': features,
            'res4lyf': res4lyf,
            'dynamic_thresholding': dynamic_thresholding,
            'regional_backend_capabilities': regional_backend_capabilities,
        }
