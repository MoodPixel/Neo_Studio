from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import httpx

from .config import DEFAULT_BASE_URL
from .logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_BY_ROLE = {
    'text': 8,
    'image': 12,
    'video': 20,
    'voice': 20,
    'audio': 30,
}


def normalize_url(url: str) -> str:
    text = str(url or '').strip()
    if not text:
        return ''
    if not text.startswith('http://') and not text.startswith('https://'):
        text = 'http://' + text
    return text.rstrip('/')


async def probe_koboldcpp(profile: Dict[str, Any]) -> Dict[str, Any]:
    base_url = normalize_url(profile.get('base_url') or DEFAULT_BASE_URL)
    models_url = base_url + '/v1/models'
    payload: Dict[str, Any] = {
        'ok': False,
        'backend_type': 'koboldcpp',
        'base_url': base_url,
        'state': 'error',
        'message': 'Could not reach KoboldCpp.',
        'latency_ms': None,
        'details': {'models_url': models_url},
        'capabilities': [],
        'models': [],
    }
    started = datetime.utcnow()
    timeout_sec = int(profile.get('timeout_sec') or DEFAULT_TIMEOUT_BY_ROLE['text'])
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(models_url, timeout=timeout_sec)
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['details']['status_code'] = response.status_code
        if response.status_code == 200:
            data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            models = [str(item.get('id') or '').strip() for item in data.get('data', []) if isinstance(item, dict) and item.get('id')]
            payload['ok'] = True
            payload['state'] = 'connected'
            payload['message'] = f'Connected to KoboldCpp · {len(models)} model(s) visible.'
            payload['capabilities'] = ['text generation', 'prompt cleanup', 'captioning support']
            payload['models'] = models
        else:
            payload['message'] = f'KoboldCpp probe failed with status {response.status_code}.'
    except Exception as exc:
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['message'] = f'KoboldCpp probe failed: {exc}'
        payload['details']['error'] = str(exc)
        payload['dynamic_thresholding'] = dynamic_thresholding
        logger.warning('KoboldCpp probe failed for %s: %s', base_url, exc)
    return payload


async def probe_comfyui(profile: Dict[str, Any], *, role: str = 'image') -> Dict[str, Any]:
    base_url = normalize_url(profile.get('base_url') or 'http://127.0.0.1:8188')
    timeout_sec = int(profile.get('timeout_sec') or DEFAULT_TIMEOUT_BY_ROLE.get(role, DEFAULT_TIMEOUT_BY_ROLE['image']))
    payload: Dict[str, Any] = {
        'ok': False,
        'backend_type': 'comfyui',
        'base_url': base_url,
        'state': 'error',
        'message': 'Could not reach ComfyUI.',
        'latency_ms': None,
        'details': {},
        'capabilities': [],
    }
    started = datetime.utcnow()
    endpoints = {
        'system_stats': base_url + '/system_stats',
        'queue': base_url + '/queue',
        'history': base_url + '/history',
    }
    dynamic_thresholding = {
        'available': False,
        'nodes': [],
        'simple': False,
        'full': False,
        'install_hint': 'Install mcmonkeyprojects/sd-dynamic-thresholding in ComfyUI/custom_nodes, then restart ComfyUI.',
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            system_resp = await client.get(endpoints['system_stats'], timeout=timeout_sec)
            queue_resp = await client.get(endpoints['queue'], timeout=timeout_sec)
            history_resp = await client.get(endpoints['history'], timeout=timeout_sec)
            dynamic_nodes = []
            for node_name in ('DynamicThresholdingSimple', 'DynamicThresholdingFull'):
                try:
                    node_resp = await client.get(base_url + f'/object_info/{node_name}', timeout=timeout_sec)
                    if node_resp.status_code == 200:
                        node_data = node_resp.json() if node_resp.headers.get('content-type', '').startswith('application/json') else {}
                        if isinstance(node_data, dict) and (node_name in node_data or node_data.get('input')):
                            dynamic_nodes.append(node_name)
                except Exception:
                    pass
        if dynamic_nodes:
            dynamic_thresholding = {
                'available': True,
                'nodes': dynamic_nodes,
                'simple': 'DynamicThresholdingSimple' in dynamic_nodes,
                'full': 'DynamicThresholdingFull' in dynamic_nodes,
                'install_hint': '',
            }
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['details'] = {
            'system_stats_status': system_resp.status_code,
            'queue_status': queue_resp.status_code,
            'history_status': history_resp.status_code,
            'dynamic_thresholding': dynamic_thresholding,
        }
        ok_codes = {200}
        if system_resp.status_code in ok_codes or queue_resp.status_code in ok_codes:
            payload['ok'] = True
            caps = []
            if system_resp.status_code in ok_codes:
                caps.append('system stats')
            if queue_resp.status_code in ok_codes:
                caps.append('queue polling')
            if history_resp.status_code in ok_codes:
                caps.append('history lookup')
            caps.append('workflow submission')
            if role == 'video':
                caps.extend(['video queue', 'graph execution'])
            else:
                caps.extend(['image queue', 'graph execution'])
            if dynamic_thresholding.get('available'):
                caps.append('dynamic thresholding')
            payload['capabilities'] = caps
            payload['dynamic_thresholding'] = dynamic_thresholding
            payload['state'] = 'connected' if system_resp.status_code in ok_codes and queue_resp.status_code in ok_codes else 'degraded'
            payload['message'] = 'Connected to ComfyUI.' if payload['state'] == 'connected' else 'ComfyUI reachable, but some endpoints look degraded.'
        else:
            payload['dynamic_thresholding'] = dynamic_thresholding
            payload['message'] = 'ComfyUI endpoints did not respond as expected.'
    except Exception as exc:
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['message'] = f'ComfyUI probe failed: {exc}'
        payload['details']['error'] = str(exc)
        payload['dynamic_thresholding'] = dynamic_thresholding
        logger.warning('ComfyUI probe failed for %s: %s', base_url, exc)
    return payload


async def probe_generic_service(profile: Dict[str, Any], *, adapter: str, role: str, capabilities: list[str]) -> Dict[str, Any]:
    base_url = normalize_url(profile.get('base_url') or '')
    payload: Dict[str, Any] = {
        'ok': False,
        'backend_type': adapter,
        'base_url': base_url,
        'state': 'error',
        'message': f'Could not reach {adapter}.',
        'latency_ms': None,
        'details': {},
        'capabilities': [],
    }
    if not base_url:
        payload['message'] = f'No base URL set for {role} backend.'
        return payload
    timeout_sec = int(profile.get('timeout_sec') or DEFAULT_TIMEOUTS.get(role, 15))
    started = datetime.utcnow()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            health_resp = await client.get(base_url + '/health', timeout=timeout_sec)
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['details'] = {'health_status': health_resp.status_code}
        if health_resp.status_code == 200:
            payload['ok'] = True
            payload['state'] = 'connected'
            payload['message'] = f'Connected to {adapter}.'
            payload['capabilities'] = list(capabilities)
            return payload
    except Exception:
        pass
    started = datetime.utcnow()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            root_resp = await client.get(base_url, timeout=timeout_sec)
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['details'] = {'root_status': root_resp.status_code}
        if root_resp.status_code < 500:
            payload['ok'] = True
            payload['state'] = 'connected'
            payload['message'] = f'{adapter} reachable.'
            payload['capabilities'] = list(capabilities)
        else:
            payload['message'] = f'{adapter} responded with status {root_resp.status_code}.'
    except Exception as exc:
        payload['latency_ms'] = round((datetime.utcnow() - started).total_seconds() * 1000, 1)
        payload['details']['error'] = str(exc)
        payload['dynamic_thresholding'] = dynamic_thresholding
        payload['message'] = f'{adapter} probe failed: {exc}'
        logger.warning('%s probe failed for %s: %s', adapter, base_url, exc)
    return payload


