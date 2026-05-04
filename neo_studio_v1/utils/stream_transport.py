from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable

import httpx


def extract_content_from_delta(delta: Any) -> str:
    if isinstance(delta, str):
        return delta
    if isinstance(delta, list):
        parts: list[str] = []
        for item in delta:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get('text') or item.get('content') or ''
                if isinstance(value, str):
                    parts.append(value)
        return ''.join(parts)
    if isinstance(delta, dict):
        value = delta.get('content') or delta.get('text') or ''
        return value if isinstance(value, str) else ''
    return ''


async def stream_chat_events(
    *,
    url: str,
    request_payload: dict[str, Any],
    timeout: float,
    strip_visible_reasoning: Callable[..., dict[str, Any]],
    partner_name: str = '',
    first_token_timeout: float | None = None,
    idle_chunk_timeout: float = 18.0,
    recover_partial_timeout: bool = False,
    partial_timeout_warning: str = '',
    require_stream_payload: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    content_accum = ''
    visible_accum = ''
    finish_reason = ''
    reasoning_stripped = False
    stream_stalled = False
    fallback_warning = ''
    first_token_timeout = first_token_timeout if first_token_timeout is not None else min(float(timeout), 90.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream('POST', url, json=request_payload) as resp:
            resp.raise_for_status()
            content_type = str(resp.headers.get('content-type') or '').lower()
            if 'application/json' in content_type:
                raw_bytes = await asyncio.wait_for(resp.aread(), timeout=first_token_timeout)
                data = json.loads(raw_bytes.decode('utf-8', errors='ignore') or '{}')
                choice = (data.get('choices', [{}]) or [{}])[0] or {}
                message = str((choice.get('message', {}) or {}).get('content') or '').strip()
                finish_reason = str(choice.get('finish_reason') or '').strip()
                reasoning = strip_visible_reasoning(message, partner_name=partner_name)
                visible = str(reasoning.get('content') or '')
                reasoning_stripped = bool(reasoning.get('had_reasoning'))
                content_accum = message
                visible_accum = visible
                if visible:
                    yield {'type': 'delta', 'delta': visible, 'text': visible}
            else:
                line_iter = resp.aiter_lines().__aiter__()
                saw_stream_payload = False
                try:
                    while True:
                        wait_timeout = idle_chunk_timeout if (content_accum or visible_accum) else first_token_timeout
                        try:
                            line = await asyncio.wait_for(line_iter.__anext__(), timeout=wait_timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            if recover_partial_timeout and visible_accum.strip():
                                stream_stalled = True
                                finish_reason = finish_reason or 'length'
                                fallback_warning = partial_timeout_warning or 'Upstream stream stalled after partial output. Partial reply recovered.'
                                break
                            raise TimeoutError('Streaming timed out before any visible output arrived.')
                        raw_line = str(line or '').strip()
                        if not raw_line or raw_line.startswith(':') or not raw_line.startswith('data:'):
                            continue
                        payload_text = raw_line[5:].strip()
                        if not payload_text:
                            continue
                        if payload_text == '[DONE]':
                            saw_stream_payload = True
                            break
                        try:
                            data = json.loads(payload_text)
                        except Exception:
                            continue
                        saw_stream_payload = True
                        choice = (data.get('choices', [{}]) or [{}])[0] or {}
                        finish_reason = str(choice.get('finish_reason') or finish_reason or '').strip()
                        delta = choice.get('delta') or {}
                        piece = extract_content_from_delta(delta.get('content') if isinstance(delta, dict) else delta)
                        if not piece:
                            continue
                        content_accum += piece
                        reasoning = strip_visible_reasoning(content_accum, partner_name=partner_name)
                        visible = str(reasoning.get('content') or '')
                        reasoning_stripped = reasoning_stripped or bool(reasoning.get('had_reasoning'))
                        if visible.startswith(visible_accum):
                            delta_visible = visible[len(visible_accum):]
                        else:
                            delta_visible = visible
                        visible_accum = visible
                        if delta_visible:
                            yield {'type': 'delta', 'delta': delta_visible, 'text': visible_accum}
                finally:
                    aclose = getattr(line_iter, 'aclose', None)
                    if callable(aclose):
                        try:
                            await aclose()
                        except Exception:
                            pass
                if require_stream_payload and not saw_stream_payload and not visible_accum.strip():
                    raise RuntimeError('Streaming reply ended without any SSE payloads.')

    yield {
        'type': 'complete',
        'content_accum': content_accum,
        'visible_text': visible_accum,
        'finish_reason': finish_reason,
        'reasoning_stripped': reasoning_stripped,
        'stream_stalled': stream_stalled,
        'fallback_warning': fallback_warning,
    }
