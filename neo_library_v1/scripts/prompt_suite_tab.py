import json
import os
import sys
from pathlib import Path

import gradio as gr
from modules import script_callbacks

# Add extension lib/ to path (so we can keep big modules out of scripts/)
EXT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIB_DIR = os.path.join(EXT_ROOT, 'lib')
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

# Add scripts/ to path so sibling modules can be imported reliably in Forge
SCRIPTS_DIR = os.path.dirname(__file__)
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

from prompt_builder_embed import build_prompt_builder_ui
from vault_embed import build_vault_ui
from neo_library_embed import (
    build_caption_library_ui,
    build_library_settings_ui,
    build_output_inspector_ui,
)
from map_generator_embed import build_map_generator_ui

from prompt_suite_injector import queue_cn, clear_queue, cn_ext
from neo_library_store import get_output_dirs, get_output_metadata_root

EXT_NAME = 'Neo Library'
EXT_SLUG = 'neo_library'


def _queue_ui(kind: str, unit_idx: int, path: str, weight: float = 1.0) -> str:
    path = (path or '').strip()
    if not path:
        return f'⚠️ No {kind} selected.'
    queue_cn(unit_idx, kind, path, weight)
    if cn_ext is None:
        return f'✅ Queued {kind} → CN Unit {unit_idx}. (ControlNet bridge not found)'
    return f'✅ Queued {kind} → CN Unit {unit_idx}. Now hit **Generate**.'


def _clear_queue_ui() -> str:
    clear_queue()
    return '🧹 Cleared queued maps.'


def _safe_extra_generation_params(p) -> dict:
    data = getattr(p, 'extra_generation_params', None)
    return data if isinstance(data, dict) else {}


def _adetailer_rows(extra: dict) -> list:
    rows = []
    passes = {}
    for k, v in extra.items():
        kl = str(k).lower()
        if not kl.startswith('adetailer'):
            continue
        idx = 1
        for token in kl.replace(':', ' ').split():
            if token.isdigit():
                idx = int(token)
                break
        row = passes.setdefault(idx, {'name': f'pass_{idx}', 'positive': '', 'negative': '', 'settings': {}})
        if 'negative prompt' in kl:
            row['negative'] = str(v)
        elif 'prompt' in kl:
            row['positive'] = str(v)
        else:
            row['settings'][k] = v
    return [passes[i] for i in sorted(passes)]


def _controlnet_summary(extra: dict) -> list:
    items = []
    grouped = {}
    for k, v in extra.items():
        kl = str(k).lower()
        if 'controlnet' not in kl:
            continue
        idx = 0
        for token in kl.replace(':', ' ').replace('-', ' ').split():
            if token.isdigit():
                idx = int(token)
                break
        row = grouped.setdefault(idx, {'unit': idx, 'settings': {}})
        row['settings'][k] = v
    for idx in sorted(grouped):
        items.append(grouped[idx])
    return items




def _extract_prompt_pair(raw_parameters: str) -> tuple[str, str]:
    text = (raw_parameters or '').strip()
    if not text:
        return '', ''
    lines = text.splitlines()
    param_start = None
    for i, line in enumerate(lines):
        if line.startswith('Steps:'):
            param_start = i
            break
    body_lines = lines[:param_start] if param_start is not None else lines
    positive_lines = []
    negative_lines = []
    seen_negative = False
    for line in body_lines:
        if line.startswith('Negative prompt:'):
            seen_negative = True
            negative_lines.append(line[len('Negative prompt:'):].strip())
            continue
        if seen_negative:
            negative_lines.append(line)
        else:
            positive_lines.append(line)
    return '\n'.join(positive_lines).strip(), '\n'.join(negative_lines).strip()


def _detect_output_mode_and_rel(path: Path) -> tuple[str, Path]:
    outputs = get_output_dirs()
    resolved = path.resolve()
    for mode, root in outputs.items():
        try:
            rel = resolved.relative_to(root.resolve())
            return mode, rel
        except Exception:
            continue
    mode = 'img2img' if 'img2img' in str(path).lower() else 'txt2img'
    return mode, Path(path.name)


def _write_sidecar(params):
    filename = getattr(params, 'filename', '') or ''
    if not filename:
        return
    path = Path(filename)
    if not path.exists():
        return
    p = getattr(params, 'p', None)
    pnginfo = getattr(params, 'pnginfo', None)
    pnginfo = pnginfo if isinstance(pnginfo, dict) else {}
    extra = _safe_extra_generation_params(p) if p is not None else {}

    prompt = getattr(p, 'prompt', '') if p is not None else ''
    negative = getattr(p, 'negative_prompt', '') if p is not None else ''
    styles = list(getattr(p, 'styles', []) or []) if p is not None else []
    sampler = getattr(p, 'sampler_name', '') if p is not None else ''
    scheduler = getattr(p, 'scheduler', '') if p is not None else ''
    steps = getattr(p, 'steps', '') if p is not None else ''
    cfg = getattr(p, 'cfg_scale', '') if p is not None else ''
    seed = getattr(p, 'seed', '') if p is not None else ''
    width = getattr(p, 'width', '') if p is not None else ''
    height = getattr(p, 'height', '') if p is not None else ''
    denoise = getattr(p, 'denoising_strength', '') if p is not None else ''

    checkpoint = ''
    vae = ''
    try:
        from modules import shared  # type: ignore
        checkpoint = str(getattr(shared.opts, 'sd_model_checkpoint', '') or '')
        vae = str(getattr(shared.opts, 'sd_vae', '') or '')
    except Exception:
        pass

    payload = {
        'schema_version': 1,
        'image_file': path.name,
        'mode': 'img2img' if 'img2img' in str(path).lower() else 'txt2img',
        'main': {
            # Best effort: Forge does not always expose pre-style prompt separately.
            'positive_box': prompt,
            'negative_box': negative,
        },
        'style': {
            'positive_applied': ', '.join(styles),
            'negative_applied': '',
        },
        'final': {
            'positive_sent': prompt,
            'negative_sent': negative,
        },
        'generation': {
            'Steps': steps,
            'Sampler': sampler,
            'Schedule type': scheduler,
            'CFG scale': cfg,
            'Seed': seed,
            'Size': f'{width}x{height}' if width and height else '',
            'Model': checkpoint,
            'VAE': vae,
            'Denoising strength': denoise,
        },
        'adetailer': _adetailer_rows(extra),
        'controlnet': _controlnet_summary(extra),
        'extra_generation_params': extra,
        'raw_parameters': pnginfo.get('parameters', ''),
    }
    sidecar_path = path.with_suffix('.json')
    try:
        sidecar_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        return


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as ui:
        gr.Markdown('## 🧩 Neo Library')
        gr.Markdown(
            '- **Prompt Composer** = manual prompt building inside Forge Neo\n'
            '- **Caption Library** = browse saved captioned images and send one selected image to the target you choose\n'
            '- **Output Inspector** = browse txt2img/img2img outputs, read structured metadata, recover prompts from uploaded outputs, and reuse settings\n'
            '- **Vault + Maps / Map Generator** = keep your existing asset + map workflows intact\n'
        )

        with gr.Tabs():
            with gr.Tab('🧱 Prompt Composer'):
                positive_out, negative_out = build_prompt_builder_ui(
                    queue_cb=_queue_ui,
                    clear_queue_cb=_clear_queue_ui,
                )

            with gr.Tab('🖼️ Caption Library'):
                build_caption_library_ui(positive_out)

            with gr.Tab('🧾 Output Inspector'):
                build_output_inspector_ui(positive_out)

            with gr.Tab('🗃️ Vault + Maps'):
                build_vault_ui()

            with gr.Tab('🧪 Map Generator'):
                build_map_generator_ui(queue_cb=_queue_ui, clear_queue_cb=_clear_queue_ui)

            with gr.Tab('⚙️ Library Settings'):
                build_library_settings_ui()

    return [(ui, EXT_NAME, EXT_SLUG)]


script_callbacks.on_ui_tabs(on_ui_tabs)
try:
    script_callbacks.on_image_saved(_write_sidecar)
except Exception:
    pass
