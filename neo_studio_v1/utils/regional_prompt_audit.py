from __future__ import annotations

from typing import Any

from ..contracts.regional_prompting import build_regional_prompt_contract, build_regional_promotion_gate


def build_regional_prompt_sprint1_audit(catalog: dict[str, Any] | None) -> dict[str, Any]:
    catalog = catalog if isinstance(catalog, dict) else {}
    caps = catalog.get('regional_backend_capabilities') if isinstance(catalog.get('regional_backend_capabilities'), dict) else {}
    native = caps.get('native') if isinstance(caps.get('native'), dict) else {}
    node = caps.get('node') if isinstance(caps.get('node'), dict) else {}
    dense = caps.get('dense_diffusion') if isinstance(caps.get('dense_diffusion'), dict) else {}

    observations: list[dict[str, Any]] = [
        {
            'id': 'txt2img_only_runtime_gate',
            'severity': 'info',
            'finding': 'Current regional compiler path is txt2img-first only.',
            'evidence': 'Regional Composer currently exits early for non-txt2img modes.',
            'action': 'Keep Dense Diffusion v1 scoped to txt2img during the first compiler pass.',
        },
        {
            'id': 'backend_choices_currently_native_or_node',
            'severity': 'info',
            'finding': 'Current regional backend resolver only actively compiles native or node/Impact Pack paths.',
            'evidence': 'Dense Diffusion is a planned backend contract, not an active compiler branch yet.',
            'action': 'Do not expose Dense Diffusion as selectable until Sprint 2 compiler work lands.',
        },
        {
            'id': 'mask_upload_limit_mismatch',
            'severity': 'warn',
            'finding': 'Regional asset upload prep only processes the first three region masks.',
            'evidence': 'Current upload prep slices rows[:3] even though workflow normalization can accept up to five rows.',
            'action': 'Keep v1 contract honest around three practical regions, then expand later with backend parity.',
        },
        {
            'id': 'node_backend_feature_gaps',
            'severity': 'warn',
            'finding': 'Impact Pack regional routing has reduced feature parity compared with the native mask-conditioning backend.',
            'evidence': {
                'supports_mask_regions': bool(node.get('supports_mask_regions')),
                'supports_negative_regions': bool(node.get('supports_negative_regions')),
                'supports_priority_order': bool(node.get('supports_priority_order')),
                'supports_overlap_blend': bool(node.get('supports_overlap_blend')),
                'supports_falloff': bool(node.get('supports_falloff')),
            },
            'action': 'Dense Diffusion contract should target stronger region adherence without inheriting the current Impact Pack feature gaps.',
        },
    ]

    if not native.get('available', False):
        observations.append({
            'id': 'native_backend_unavailable',
            'severity': 'error',
            'finding': 'Native regional backend dependencies are missing on the live backend.',
            'evidence': native.get('missing_components') or [],
            'action': 'Repair the baseline native regional stack before promoting any advanced backend work.',
        })

    if dense.get('available', False):
        observations.append({
            'id': 'dense_diffusion_nodes_detected',
            'severity': 'info',
            'finding': 'Dense Diffusion node dependencies were detected on the live backend.',
            'evidence': {
                'required_components': dense.get('required_components') or [],
                'missing_components': dense.get('missing_components') or [],
            },
            'action': 'Good sign for Sprint 2, but keep the backend disabled until compiler and truth UI work exist.',
        })
    else:
        observations.append({
            'id': 'dense_diffusion_not_ready',
            'severity': 'info',
            'finding': 'Dense Diffusion dependencies are not fully available yet on the live backend.',
            'evidence': dense.get('missing_components') or [],
            'action': 'Install only the required Dense Diffusion + smZ nodes before starting compiler work.',
        })

    return {
        'contract': build_regional_prompt_contract(),
        'current_runtime': {
            'native': native,
            'node': node,
            'dense_diffusion': dense,
        },
        'audit_observations': observations,
        'recommended_required_nodes': list((dense.get('required_components') or [])),
        'recommended_optional_nodes': list((dense.get('optional_components') or [])),
        'summary': {
            'ship_now': 'Keep current native regional backend as default.',
            'next_backend': 'Add Dense Diffusion as an SDXL-only experimental secondary backend.',
            'keep_out_of_scope': ['Qwen regional backend', 'Flux regional backend', 'detailers/upscalers/auto-detection lanes'],
        },
    }



def build_regional_prompt_sprint4_gate(catalog: dict[str, Any] | None) -> dict[str, Any]:
    catalog = catalog if isinstance(catalog, dict) else {}
    caps = catalog.get('regional_backend_capabilities') if isinstance(catalog.get('regional_backend_capabilities'), dict) else {}
    gate = build_regional_promotion_gate()
    runtime = {}
    for backend_id in ('native', 'node', 'dense_diffusion'):
        runtime_caps = caps.get(backend_id) if isinstance(caps.get(backend_id), dict) else {}
        gate_meta = gate['gate'].get(backend_id, {}) if isinstance(gate.get('gate'), dict) else {}
        runtime[backend_id] = {
            **runtime_caps,
            'promotion_gate': gate_meta,
        }
    dense = runtime.get('dense_diffusion', {})
    native = runtime.get('native', {})
    observations = []
    if not native.get('available'):
        observations.append({
            'severity': 'error',
            'finding': 'Native backend is not ready, so the promoted baseline is currently broken.',
            'action': 'Fix the baseline regional stack before any advanced promotion discussion.',
        })
    if dense.get('available') and dense.get('compiler_ready'):
        observations.append({
            'severity': 'info',
            'finding': 'Dense Diffusion is runnable but still behind the promotion gate.',
            'action': 'Run the required four-case SDXL txt2img separation matrix before changing its promoted state.',
        })
    else:
        observations.append({
            'severity': 'warn',
            'finding': 'Dense Diffusion cannot enter the promotion gate yet because required nodes or compiler readiness are missing.',
            'action': 'Install the required nodes and confirm the Sprint 2 compiler branch is reachable before running the test matrix.',
        })
    return {
        'promotion_gate': gate,
        'runtime': runtime,
        'observations': observations,
    }
