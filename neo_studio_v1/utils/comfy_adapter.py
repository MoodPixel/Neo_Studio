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
        mmproj_models = []
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
            ('mmproj', 'mmproj_models'),
            ('mmproj_models', 'mmproj_models'),
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
            elif target == 'mmproj_models':
                mmproj_models = self._merge_string_lists(mmproj_models, values)
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

        async def _first_existing_node_name(*node_names: str) -> str:
            for node_name in node_names:
                if await _node_exists(node_name):
                    return node_name
            return ''

        async def _existing_node_aliases(*node_names: str) -> list[str]:
            aliases = []
            for node_name in node_names:
                if await _node_exists(node_name):
                    aliases.append(node_name)
            return aliases

        # GGUF loader nodes on some Comfy builds expose the real model choices only
        # through object_info, not through /models/* catalog endpoints. Phase 3 keeps
        # the alias map explicit so Flux/Qwen compile can use the detected node name
        # instead of hardcoding one Comfy custom-node spelling.
        gguf_unet_loader_aliases = ('UnetLoaderGGUF', 'LoaderGGUF')
        gguf_single_clip_loader_aliases = ('CLIPLoaderGGUF', 'ClipLoaderGGUF')
        gguf_dual_clip_loader_aliases = ('DualCLIPLoaderGGUF',)
        gguf_vae_loader_aliases = ('VaeGGUF', 'VAELoaderGGUF')

        gguf_unet_available_aliases = await _existing_node_aliases(*gguf_unet_loader_aliases)
        gguf_single_clip_available_aliases = await _existing_node_aliases(*gguf_single_clip_loader_aliases)
        gguf_dual_clip_available_aliases = await _existing_node_aliases(*gguf_dual_clip_loader_aliases)
        gguf_vae_available_aliases = await _existing_node_aliases(*gguf_vae_loader_aliases)

        gguf_unet_loader_node = gguf_unet_available_aliases[0] if gguf_unet_available_aliases else ''
        gguf_single_clip_loader_node = gguf_single_clip_available_aliases[0] if gguf_single_clip_available_aliases else ''
        gguf_dual_clip_loader_node = gguf_dual_clip_available_aliases[0] if gguf_dual_clip_available_aliases else ''
        gguf_vae_loader_node = gguf_vae_available_aliases[0] if gguf_vae_available_aliases else ''

        gguf_loader_alias_status = {
            'unet': {
                'candidates': list(gguf_unet_loader_aliases),
                'available': gguf_unet_available_aliases,
                'effective': gguf_unet_loader_node,
            },
            'clip_single': {
                'candidates': list(gguf_single_clip_loader_aliases),
                'available': gguf_single_clip_available_aliases,
                'effective': gguf_single_clip_loader_node,
            },
            'clip_dual': {
                'candidates': list(gguf_dual_clip_loader_aliases),
                'available': gguf_dual_clip_available_aliases,
                'effective': gguf_dual_clip_loader_node,
            },
            'vae': {
                'candidates': list(gguf_vae_loader_aliases),
                'available': gguf_vae_available_aliases,
                'effective': gguf_vae_loader_node,
            },
        }

        gguf_unet_info = await _get_node_info(gguf_unet_loader_node) if gguf_unet_loader_node else {}
        gguf_dual_clip_info = await _get_node_info(gguf_dual_clip_loader_node) if gguf_dual_clip_loader_node else {}
        gguf_single_clip_info = await _get_node_info(gguf_single_clip_loader_node) if gguf_single_clip_loader_node else {}
        gguf_vae_info = await _get_node_info(gguf_vae_loader_node) if gguf_vae_loader_node else {}

        gguf_unet_choices = self._extract_node_required_choices(gguf_unet_info, 'unet_name', 'gguf_name')
        gguf_clip_dual_choices = self._extract_node_required_choices(gguf_dual_clip_info, 'clip_name1', 'clip_name2')
        gguf_clip_single_choices = self._extract_node_required_choices(gguf_single_clip_info, 'clip_name')
        gguf_clip_choices = self._merge_string_lists(gguf_clip_dual_choices, gguf_clip_single_choices)
        gguf_vae_choices = self._extract_node_required_choices(gguf_vae_info, 'vae_name')

        def _is_mmproj_asset(value: str) -> bool:
            lowered = str(value or '').casefold()
            if not lowered:
                return False
            return bool(
                'mmproj' in lowered
                or 'mm_proj' in lowered
                or 'mm-proj' in lowered
                or ('vision' in lowered and ('qwen' in lowered or 'image' in lowered))
                or ('projector' in lowered and ('qwen' in lowered or 'image' in lowered))
            )

        def _is_qwen_text_encoder_asset(value: str) -> bool:
            lowered = str(value or '').casefold()
            return bool(('qwen' in lowered or 'qw' in lowered) and not _is_mmproj_asset(value))

        def _qwen_mmproj_match_score(encoder: str, mmproj: str) -> int:
            encoder_key = str(encoder or '').casefold().replace('\\', '/').split('/')[-1]
            mmproj_key = str(mmproj or '').casefold().replace('\\', '/').split('/')[-1]
            if not encoder_key or not mmproj_key:
                return 0
            score = 0
            for token in ('qwen', 'qwen2', 'qwen2.5', 'qwen_image', 'image', 'edit', 'vl'):
                token_key = token.casefold()
                if token_key in encoder_key and token_key in mmproj_key:
                    score += 8
            for token in ('fp8', 'f16', 'bf16', 'gguf', '4bit', '8bit'):
                token_key = token.casefold()
                if token_key in encoder_key and token_key in mmproj_key:
                    score += 2
            encoder_stem = encoder_key.rsplit('.', 1)[0]
            mmproj_stem = mmproj_key.rsplit('.', 1)[0]
            if encoder_stem and encoder_stem in mmproj_stem:
                score += 20
            if mmproj_stem and mmproj_stem in encoder_stem:
                score += 20
            return score

        def _build_qwen_mmproj_matches(encoders: list[str], mmprojs: list[str]) -> dict:
            matches = {}
            for encoder in self._clean_string_list(encoders):
                ranked = sorted(
                    (
                        {
                            'name': mmproj,
                            'score': _qwen_mmproj_match_score(encoder, mmproj),
                            'source': 'catalog_match',
                        }
                        for mmproj in self._clean_string_list(mmprojs)
                    ),
                    key=lambda item: (-int(item.get('score') or 0), str(item.get('name') or '').casefold()),
                )
                positive = [item for item in ranked if int(item.get('score') or 0) > 0]
                matches[encoder] = {
                    'auto': positive[0]['name'] if positive else '',
                    'candidates': positive or ranked[:5],
                    'status': 'auto_detected' if positive else ('available_unmatched' if ranked else 'missing'),
                }
            return matches

        mmproj_source_candidates = self._merge_string_lists(
            mmproj_models,
            gguf_clip_single_choices,
            gguf_clip_choices,
            text_encoders,
            clip,
            clip_vision,
        )
        gguf_mmproj_choices = [item for item in mmproj_source_candidates if _is_mmproj_asset(item)]
        qwen_text_encoder_choices = [item for item in self._merge_string_lists(gguf_clip_single_choices, text_encoders, gguf_clip_choices) if _is_qwen_text_encoder_asset(item)]
        qwen_preferred_vae_choices = [item for item in self._merge_string_lists(gguf_vae_choices, vae) if 'qwen' in str(item or '').casefold() or 'pig_qwen_image_vae' in str(item or '').casefold()]
        qwen_mmproj_matches = _build_qwen_mmproj_matches(qwen_text_encoder_choices, gguf_mmproj_choices)

        gguf_catalog = {
            'unet': self._clean_string_list(gguf_unet_choices),
            'clip': self._clean_string_list(gguf_clip_choices),
            'clip_single': self._clean_string_list(gguf_clip_single_choices),
            'clip_dual': self._clean_string_list(gguf_clip_dual_choices),
            'mmproj': self._clean_string_list(gguf_mmproj_choices),
            'mmproj_sources': {
                'mmproj_folder': self._clean_string_list(mmproj_models),
                'clip_loader_choices': self._clean_string_list(gguf_clip_choices),
                'text_encoders_folder': self._clean_string_list(text_encoders),
                'clip_folder': self._clean_string_list(clip),
                'clip_vision_folder': self._clean_string_list(clip_vision),
            },
            'vae': self._clean_string_list(gguf_vae_choices),
            'loader_nodes': {
                'unet': gguf_unet_loader_node,
                'clip_single': gguf_single_clip_loader_node,
                'clip_dual': gguf_dual_clip_loader_node,
                'vae': gguf_vae_loader_node,
            },
            'loader_aliases': gguf_loader_alias_status,
            'loader_available': {
                'unet': bool(gguf_unet_loader_node),
                'clip_single': bool(gguf_single_clip_loader_node),
                'clip_dual': bool(gguf_dual_clip_loader_node),
                'vae': bool(gguf_vae_loader_node),
            },
            'source': 'comfy_object_info',
            'legacy_merged_into': ['unet', 'clip', 'vae'],
        }
        qwen_base_missing = []
        if not gguf_unet_loader_node:
            qwen_base_missing.append('GGUF UNet loader node')
        if not gguf_single_clip_loader_node:
            qwen_base_missing.append('GGUF single CLIP loader node')
        if not gguf_unet_choices:
            qwen_base_missing.append('Qwen GGUF model choice')
        if not qwen_text_encoder_choices:
            qwen_base_missing.append('Qwen text encoder GGUF')

        qwen_mmproj_missing = []
        if not gguf_mmproj_choices:
            qwen_mmproj_missing.append('Qwen mmproj sidecar')

        qwen_base_ready = bool(
            gguf_unet_loader_node
            and gguf_single_clip_loader_node
            and gguf_unet_choices
            and qwen_text_encoder_choices
        )
        qwen_image_workflow_ready = bool(qwen_base_ready and gguf_mmproj_choices)
        qwen_missing = self._clean_string_list(qwen_base_missing + qwen_mmproj_missing)
        qwen_blockers = self._clean_string_list(qwen_base_missing)
        qwen_warnings = []
        if qwen_base_ready and not gguf_mmproj_choices:
            qwen_warnings.append('Qwen base GGUF assets are available, but mmproj is missing; image/reference/img2img/inpaint workflows must stay blocked until mmproj is selected or detected.')
        if gguf_mmproj_choices and qwen_text_encoder_choices and not any((entry.get('best_match') or {}).get('name') for entry in qwen_mmproj_matches.values() if isinstance(entry, dict)):
            qwen_warnings.append('Qwen mmproj files are available, but no strong encoder match was detected; UI should expose manual selection before launch.')

        qwen_readiness = {
            'base_ready': qwen_base_ready,
            'image_workflow_ready': qwen_image_workflow_ready,
            'ready': qwen_image_workflow_ready,
            'mmproj_ready': bool(gguf_mmproj_choices),
            'mmproj_status': 'available' if gguf_mmproj_choices else 'missing',
            'required': {
                'gguf_unet_loader': bool(gguf_unet_loader_node),
                'gguf_single_clip_loader': bool(gguf_single_clip_loader_node),
                'gguf_unet_model': bool(gguf_unet_choices),
                'qwen_text_encoder': bool(qwen_text_encoder_choices),
                'qwen_mmproj': bool(gguf_mmproj_choices),
            },
            'missing': qwen_missing,
            'blockers': qwen_blockers,
            'warnings': self._clean_string_list(qwen_warnings),
            'route_ready': {
                'txt2img': qwen_base_ready,
                'img2img': qwen_image_workflow_ready,
                'inpaint': qwen_image_workflow_ready,
                'reference_image': qwen_image_workflow_ready,
                'multi_source_reference': qwen_image_workflow_ready,
            },
            'route_blockers': {
                'txt2img': self._clean_string_list(qwen_base_missing),
                'img2img': self._clean_string_list(qwen_base_missing + qwen_mmproj_missing),
                'inpaint': self._clean_string_list(qwen_base_missing + qwen_mmproj_missing),
                'reference_image': self._clean_string_list(qwen_base_missing + qwen_mmproj_missing),
                'multi_source_reference': self._clean_string_list(qwen_base_missing + qwen_mmproj_missing),
            },
            'source': 'comfy_object_info',
        }

        qwen_image_catalog = {
            'text_encoders': self._clean_string_list(qwen_text_encoder_choices),
            'mmproj': self._clean_string_list(gguf_mmproj_choices),
            'mmproj_matches': qwen_mmproj_matches,
            'mmproj_required_for': ['img2img', 'inpaint', 'reference_image', 'multi_source_reference'],
            'mmproj_status': qwen_readiness['mmproj_status'],
            'preferred_vae': self._clean_string_list(qwen_preferred_vae_choices),
            'ready': qwen_readiness['ready'],
            'base_ready': qwen_readiness['base_ready'],
            'image_workflow_ready': qwen_readiness['image_workflow_ready'],
            'missing': qwen_missing,
            'blockers': qwen_blockers,
            'warnings': qwen_readiness['warnings'],
            'readiness': qwen_readiness,
            'loader_nodes': {
                'unet': gguf_unet_loader_node,
                'clip_single': gguf_single_clip_loader_node,
                'vae': gguf_vae_loader_node,
            },
            'source': 'comfy_object_info',
        }
        flux_missing = []
        if not gguf_unet_loader_node:
            flux_missing.append('GGUF UNet loader node')
        if not gguf_dual_clip_loader_node:
            flux_missing.append('GGUF dual CLIP loader node')
        if not gguf_unet_choices:
            flux_missing.append('Flux GGUF model choice')
        if not gguf_clip_dual_choices:
            flux_missing.append('Flux dual encoder choices')
        flux_gguf_catalog = {
            'unet': self._clean_string_list(gguf_unet_choices),
            'clip': self._clean_string_list(gguf_clip_dual_choices),
            'vae': self._clean_string_list(gguf_vae_choices),
            'ready': bool(gguf_unet_loader_node and gguf_dual_clip_loader_node and gguf_unet_choices and gguf_clip_dual_choices),
            'missing': flux_missing,
            'loader_nodes': {
                'unet': gguf_unet_loader_node,
                'clip_dual': gguf_dual_clip_loader_node,
                'vae': gguf_vae_loader_node,
            },
            'source': 'comfy_object_info',
        }

        # Backward compatibility: older UI code still reads the normal model lists.
        # Keep merging GGUF choices there while also exposing the new separated catalog.
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
            'gguf_unet_loader': bool(gguf_unet_loader_node),
            'gguf_dual_clip_loader': bool(gguf_dual_clip_loader_node),
            'gguf_clip_loader': bool(gguf_single_clip_loader_node),
            'gguf_vae_loader': bool(gguf_vae_loader_node),
            'gguf_loader_aliases': gguf_loader_alias_status,
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
            'mmproj_models': mmproj_models if isinstance(mmproj_models, list) else [],
            'upscale_models': upscale_models if isinstance(upscale_models, list) else [],
            'facerestore_models': facerestore_models if isinstance(facerestore_models, list) else [],
            'samplers': samplers,
            'schedulers': schedulers,
            'features': features,
            'gguf': gguf_catalog,
            'qwen_image': qwen_image_catalog,
            'flux_gguf': flux_gguf_catalog,
            'res4lyf': res4lyf,
            'dynamic_thresholding': dynamic_thresholding,
            'regional_backend_capabilities': regional_backend_capabilities,
        }
