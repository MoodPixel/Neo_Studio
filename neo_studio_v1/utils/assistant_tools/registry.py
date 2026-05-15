from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .schemas import AssistantToolSpec, int_property, text_property
from .tools import (
    tool_extension_inspect,
    tool_extension_list,
    tool_repo_index_rebuild,
    tool_repo_inspect_path,
    tool_repo_read_file,
    tool_repo_search,
    tool_workflow_patch_validate,
    tool_patch_plan_validate,
    tool_patch_plan_preview,
    tool_patch_plan_apply,
)
from ..assistant_local_pc_control import (
    tool_local_action_catalog,
    tool_local_action_preview,
    tool_local_action_execute,
)


def _object_schema(properties: Dict[str, Any], *, required: List[str] | None = None) -> Dict[str, Any]:
    return {'type': 'object', 'properties': properties, 'required': required or [], 'additionalProperties': False}


_TOOL_SPECS: Dict[str, AssistantToolSpec] = {}


def register_tool(spec: AssistantToolSpec) -> AssistantToolSpec:
    if not spec.id or '__' in spec.id:
        raise ValueError('Assistant tool IDs must be non-empty and must not use double-underscore routing syntax.')
    if spec.id in _TOOL_SPECS:
        raise ValueError(f'Duplicate Assistant tool ID: {spec.id}')
    _TOOL_SPECS[spec.id] = spec
    return spec


def _register_defaults() -> None:
    if _TOOL_SPECS:
        return
    register_tool(AssistantToolSpec(
        id='repo.search',
        name='Search Repo Index',
        description='Search the local Neo Studio repo index and return relevant file summaries.',
        category='repo',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'query': text_property('Search query.', max_length=600), 'limit': int_property('Maximum result count.', default=8, maximum=30)}, required=['query']),
        output_schema=_object_schema({'results': {'type': 'array'}, 'file_count': {'type': 'integer'}}),
        tags=['repo', 'search', 'index'],
        handler=tool_repo_search,
    ))
    register_tool(AssistantToolSpec(
        id='repo.index_rebuild',
        name='Rebuild Repo Index',
        description='Rebuild the read-only Assistant repo index from local text files.',
        category='repo',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'max_files': int_property('Maximum files to index.', default=1200, maximum=5000)}),
        output_schema=_object_schema({'file_count': {'type': 'integer'}, 'kind_counts': {'type': 'object'}}),
        tags=['repo', 'index', 'diagnostic'],
        handler=tool_repo_index_rebuild,
    ))
    register_tool(AssistantToolSpec(
        id='repo.read_file',
        name='Read Repo File',
        description='Read a small repository-relative text file for inspection.',
        category='repo',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'path': text_property('Repository-relative file path.', max_length=600)}, required=['path']),
        output_schema=_object_schema({'path': {'type': 'string'}, 'content': {'type': 'string'}, 'line_count': {'type': 'integer'}}),
        tags=['repo', 'file', 'read'],
        handler=tool_repo_read_file,
    ))
    register_tool(AssistantToolSpec(
        id='repo.inspect_path',
        name='Inspect Repo Path',
        description='Inspect a repository-relative file or directory without editing it.',
        category='repo',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'path': text_property('Repository-relative path.', max_length=600)}, required=['path']),
        output_schema=_object_schema({'path': {'type': 'string'}, 'exists': {'type': 'boolean'}}),
        tags=['repo', 'file', 'directory'],
        handler=tool_repo_inspect_path,
    ))
    register_tool(AssistantToolSpec(
        id='extension.list',
        name='List Installed Extensions',
        description='List installed Neo extensions and manifest-level capabilities.',
        category='extension',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({}),
        output_schema=_object_schema({'extensions': {'type': 'array'}, 'count': {'type': 'integer'}}),
        tags=['extension', 'manifest'],
        handler=tool_extension_list,
    ))
    register_tool(AssistantToolSpec(
        id='extension.inspect',
        name='Inspect Extension',
        description='Read one installed extension manifest and README preview.',
        category='extension',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'extension_id': text_property('Extension ID or installed folder name.', max_length=160)}, required=['extension_id']),
        output_schema=_object_schema({'id': {'type': 'string'}, 'manifest': {'type': 'object'}}),
        tags=['extension', 'manifest', 'read'],
        handler=tool_extension_inspect,
    ))

    register_tool(AssistantToolSpec(
        id='patch.plan_validate',
        name='Validate Patch Plan',
        description='Validate an Assistant patch plan without producing full diffs or writing files.',
        category='patch',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'plan': {'type': 'object', 'description': 'Assistant patch plan object with title, summary, and changes.'}}, required=['plan']),
        output_schema=_object_schema({'ok': {'type': 'boolean'}, 'plan_id': {'type': 'string'}, 'risk': {'type': 'string'}}),
        tags=['patch', 'validate', 'plan'],
        handler=tool_patch_plan_validate,
    ))
    register_tool(AssistantToolSpec(
        id='patch.plan_preview',
        name='Preview Patch Plan',
        description='Generate a guarded diff preview for an Assistant patch plan without writing files.',
        category='patch',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'plan': {'type': 'object', 'description': 'Assistant patch plan object with title, summary, and changes.'}}, required=['plan']),
        output_schema=_object_schema({'ok': {'type': 'boolean'}, 'plan_id': {'type': 'string'}, 'changes': {'type': 'array'}}),
        tags=['patch', 'preview', 'diff'],
        handler=tool_patch_plan_preview,
    ))
    register_tool(AssistantToolSpec(
        id='patch.plan_apply',
        name='Apply Patch Plan',
        description='Apply a confirmed Assistant patch plan with backup snapshots. Delete actions are blocked unless explicitly allowed.',
        category='patch',
        risk='medium',
        requires_confirmation=True,
        read_only=False,
        input_schema=_object_schema({'plan': {'type': 'object', 'description': 'Assistant patch plan object.'}, 'allow_delete': {'type': 'boolean', 'description': 'Allow explicit delete actions.'}}, required=['plan']),
        output_schema=_object_schema({'ok': {'type': 'boolean'}, 'backup_id': {'type': 'string'}, 'applied': {'type': 'array'}}),
        tags=['patch', 'apply', 'backup'],
        handler=tool_patch_plan_apply,
    ))

    register_tool(AssistantToolSpec(
        id='local.action_catalog',
        name='List Local PC Actions',
        description='List guarded local PC action presets and safety rules.',
        category='local_pc',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({}),
        output_schema=_object_schema({'actions': {'type': 'array'}, 'guardrails': {'type': 'object'}}),
        tags=['local', 'pc', 'guardrails', 'catalog'],
        handler=tool_local_action_catalog,
    ))
    register_tool(AssistantToolSpec(
        id='local.action_preview',
        name='Preview Local PC Action',
        description='Preview a guarded local PC action without executing it.',
        category='local_pc',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({
            'action_type': text_property('open_path, reveal_path, launch_app, or run_command_preset.', max_length=80),
            'arguments': {'type': 'object', 'description': 'Arguments for the selected local action.'},
        }, required=['action_type']),
        output_schema=_object_schema({'risk': {'type': 'string'}, 'requires_confirmation': {'type': 'boolean'}, 'details': {'type': 'object'}}),
        tags=['local', 'pc', 'preview'],
        handler=tool_local_action_preview,
    ))
    register_tool(AssistantToolSpec(
        id='local.action_execute',
        name='Execute Local PC Action',
        description='Execute a guarded local PC action. Medium-risk actions require explicit confirmation.',
        category='local_pc',
        risk='medium',
        requires_confirmation=True,
        read_only=False,
        input_schema=_object_schema({
            'action_type': text_property('open_path, reveal_path, launch_app, or run_command_preset.', max_length=80),
            'arguments': {'type': 'object', 'description': 'Arguments for the selected local action.'},
            'session_id': text_property('Optional Assistant session ID for action memory.', max_length=180),
            'project_id': text_property('Optional Assistant project ID for action memory.', max_length=180),
        }, required=['action_type']),
        output_schema=_object_schema({'ok': {'type': 'boolean'}, 'executed': {'type': 'boolean'}, 'details': {'type': 'object'}}),
        tags=['local', 'pc', 'execute', 'confirmation'],
        handler=tool_local_action_execute,
    ))

    register_tool(AssistantToolSpec(
        id='workflow.patch_validate',
        name='Validate Workflow Patch',
        description='Validate an external extension workflow patch contract without executing it.',
        category='workflow',
        risk='safe',
        read_only=True,
        input_schema=_object_schema({'patch': {'description': 'Patch dict or JSON string.'}, 'patches': {'description': 'Patch list or JSON string.'}, 'extension_id': text_property('Optional extension ID for diagnostics.', max_length=160)}),
        output_schema=_object_schema({'ok': {'type': 'boolean'}}),
        tags=['workflow', 'validator', 'extension'],
        handler=tool_workflow_patch_validate,
    ))


def list_assistant_tools(*, category: str = '') -> List[Dict[str, Any]]:
    _register_defaults()
    clean_category = str(category or '').strip().lower()
    specs: Iterable[AssistantToolSpec] = _TOOL_SPECS.values()
    if clean_category:
        specs = [spec for spec in specs if spec.category.lower() == clean_category]
    return [spec.public_dict(include_handler=True) for spec in sorted(specs, key=lambda item: item.id)]


def get_assistant_tool(tool_id: str) -> AssistantToolSpec | None:
    _register_defaults()
    return _TOOL_SPECS.get(str(tool_id or '').strip())


def get_assistant_tool_catalog() -> Dict[str, Any]:
    tools = list_assistant_tools()
    categories = sorted({str(tool.get('category') or '') for tool in tools if str(tool.get('category') or '')})
    return {'version': 'assistant_tool_registry_v1', 'count': len(tools), 'categories': categories, 'tools': tools}
