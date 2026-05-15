from __future__ import annotations

from copy import deepcopy
from typing import Any

from .workflow_template_loader import ExternalWorkflowTemplateError, load_extension_workflow_template


class ExternalWorkflowPatchError(ValueError):
    """Raised when an external workflow patch is invalid for runtime application."""


def _copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _string(value: Any) -> str:
    return str(value or '').strip()


def _bool_from_state(state: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if bool(state.get(key)):
            return True
    return False


def build_external_workflow_context(payload: dict[str, Any] | None, normalized_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source = normalized_payload if isinstance(normalized_payload, dict) else payload if isinstance(payload, dict) else {}
    return {
        'prompt': _string(source.get('positive') or source.get('prompt')),
        'negative': _string(source.get('negative') or source.get('negative_prompt')),
        'model': _string(source.get('checkpoint') or source.get('model') or source.get('unet_name')),
        'model_family': _string(source.get('_neo_effective_family') or source.get('family')),
        'workflow': _string(source.get('_neo_effective_mode') or source.get('mode') or source.get('workflow_type') or 'txt2img'),
        'source_image': _string(source.get('source_image_name') or source.get('image') or ''),
        'mask_image': _string(source.get('mask_image_name') or ''),
        'width': source.get('width'),
        'height': source.get('height'),
        'seed': source.get('seed'),
        'payload': _copy(source),
    }


def resolve_external_patch_inputs(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith('$context.'):
        key = value.split('.', 1)[1]
        return _copy(context.get(key))
    if isinstance(value, dict):
        return {k: resolve_external_patch_inputs(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_external_patch_inputs(v, context) for v in value]
    return _copy(value)


def inject_template_inputs(graph: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Attach resolved inputs without guessing node-specific schemas.

    Phase E does not rewrite arbitrary node internals. Extension templates can
    consume this metadata via future explicit mappers. This keeps the bridge
    safe while making the execution plan traceable.
    """
    out = _copy(graph) if isinstance(graph, dict) else {}
    meta = out.setdefault('_neo_external_extension_inputs', {})
    if isinstance(meta, dict):
        meta.update(_copy(inputs))
    return out


def merge_append_nodes(base_graph: dict[str, Any], nodes: dict[str, Any]) -> dict[str, Any]:
    graph = _copy(base_graph) if isinstance(base_graph, dict) else {}
    patch_nodes = _copy(nodes) if isinstance(nodes, dict) else {}
    collisions = sorted(str(key) for key in patch_nodes if key in graph)
    if collisions:
        raise ExternalWorkflowPatchError('append_nodes patch collides with existing graph node ids: ' + ', '.join(collisions[:8]))
    graph.update(patch_nodes)
    return graph


def apply_workflow_patch(
    *,
    base_graph: dict[str, Any],
    patch: dict[str, Any],
    extension_record: dict[str, Any],
    extension_state: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    strategy = _string(patch.get('strategy')).lower()
    resolved_inputs = resolve_external_patch_inputs(patch.get('inputs') or {}, context)
    report = {
        'patch_id': _string(patch.get('id')),
        'extension_id': _string(patch.get('extension_id')),
        'strategy': strategy,
        'template': _string(patch.get('template')),
        'applied': False,
        'queued_as_sidecar': False,
        'warnings': [],
        'errors': [],
        'outputs_declared': _copy(patch.get('outputs') or []),
    }

    if not patch.get('enabled', True):
        report['warnings'].append('Workflow patch is disabled.')
        return base_graph, report

    if strategy == 'metadata_only':
        report['applied'] = True
        report['warnings'].append('metadata_only patch recorded; graph unchanged.')
        return base_graph, report

    if strategy == 'append_nodes':
        graph = merge_append_nodes(base_graph, patch.get('nodes') or {})
        report['applied'] = True
        return graph, report

    if strategy == 'replace_workflow':
        effective = extension_state.get('effective_state') if isinstance(extension_state.get('effective_state'), dict) else {}
        raw = extension_state.get('raw_state') if isinstance(extension_state.get('raw_state'), dict) else {}
        confirmed = _bool_from_state(effective, 'replace_confirmed', 'confirmed_replace_workflow') or _bool_from_state(raw, 'replace_confirmed', 'confirmed_replace_workflow')
        if patch.get('requires_confirmation', True) and not confirmed:
            raise ExternalWorkflowPatchError('replace_workflow requires visible user confirmation before Neo replaces the base graph.')
        template_graph = load_extension_workflow_template(extension_record, patch.get('template') or '')
        graph = inject_template_inputs(template_graph, resolved_inputs if isinstance(resolved_inputs, dict) else {})
        report['applied'] = True
        return graph, report

    if strategy in {'sidecar_run', 'preprocess_source', 'postprocess_output'}:
        # Phase E creates the bridge and safe execution plan. Actual sidecar and
        # pre/post process queue orchestration stays isolated for later phases so
        # this step cannot silently run extra graphs or alter output policy.
        if patch.get('template'):
            # Validate the template path now so missing files block early.
            load_extension_workflow_template(extension_record, patch.get('template') or '')
        report['queued_as_sidecar'] = strategy == 'sidecar_run'
        report['warnings'].append(f'{strategy} patch validated and recorded for the external workflow executor; base graph unchanged in Phase E.')
        return base_graph, report

    raise ExternalWorkflowPatchError(f"Unsupported workflow patch strategy at runtime: {strategy}")
