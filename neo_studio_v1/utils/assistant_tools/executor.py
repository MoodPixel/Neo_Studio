from __future__ import annotations

from typing import Any, Dict

from .registry import get_assistant_tool
from ..assistant_action_memory import record_tool_action_memory


def preview_assistant_tool_call(tool_id: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    spec = get_assistant_tool(tool_id)
    if not spec:
        raise ValueError('Assistant tool not found.')
    return {
        'tool': spec.public_dict(include_handler=True),
        'arguments': arguments if isinstance(arguments, dict) else {},
        'can_execute_without_confirmation': bool(spec.read_only and spec.risk == 'safe' and not spec.requires_confirmation),
        'guardrails': {
            'read_only': bool(spec.read_only),
            'risk': spec.risk,
            'requires_confirmation': bool(spec.requires_confirmation),
            'phase': 'Phase 6 registry execution is limited to safe read-only tools.',
        },
    }


def execute_assistant_tool(tool_id: str, arguments: Dict[str, Any] | None = None, *, confirmed: bool = False, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    spec = get_assistant_tool(tool_id)
    if not spec:
        raise ValueError('Assistant tool not found.')
    args = arguments if isinstance(arguments, dict) else {}
    if spec.risk != 'safe' or spec.requires_confirmation or not spec.read_only:
        if not confirmed:
            raise PermissionError('This Assistant tool requires explicit confirmation before execution.')
    if spec.handler is None:
        raise RuntimeError('Assistant tool has no handler.')
    call_args = dict(args)
    if confirmed:
        call_args['confirmed'] = True
    context = context if isinstance(context, dict) else {}
    try:
        result = spec.handler(call_args)
        response = {'ok': True, 'tool_id': spec.id, 'risk': spec.risk, 'read_only': bool(spec.read_only), 'result': result}
        response['action_memory'] = record_tool_action_memory(
            tool_id=spec.id,
            arguments=args,
            result=result if isinstance(result, dict) else {'value': result},
            confirmed=confirmed,
            session_id=str(context.get('session_id') or '').strip(),
            project_id=str(context.get('project_id') or '').strip(),
        )
        return response
    except Exception as exc:
        record_tool_action_memory(
            tool_id=spec.id,
            arguments=args,
            error=str(exc),
            confirmed=confirmed,
            session_id=str(context.get('session_id') or '').strip(),
            project_id=str(context.get('project_id') or '').strip(),
        )
        raise
