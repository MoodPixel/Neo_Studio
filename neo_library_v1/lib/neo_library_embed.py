import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import gradio as gr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from neo_library_store import (
    categories,
    names_for_category,
    images_for_category,
    find_prompt,
    find_caption,
    resolve_media_path,
    stats,
    set_library_root,
    delete_prompt_record,
    delete_caption_record,
    get_output_dirs,
    output_image_names,
    load_output_record,
)


from neo_studio_v1.utils.output_metadata import (
    clean_rebuild_prompt as rebuild_clean_prompt,
    compare_output_metadata as compare_uploaded_output_metadata,
    parse_output_metadata_bytes,
    save_metadata_as_character as save_uploaded_metadata_as_character,
    save_metadata_as_prompt as save_uploaded_metadata_as_prompt,
)

TARGET_CHOICES = ['canny', 'openpose', 'depth', 'composition', 'ip-adapter']
TAB_CHOICES = ['txt2img', 'img2img']


def _dropdown_update(choices, value=None, allow_custom=False):
    if value is None and choices:
        value = choices[0]
    return gr.update(choices=choices, value=value, allow_custom_value=allow_custom)


def _replace_positive(prompt_text: str):
    return prompt_text or '', '✅ Sent to Prompt Composer.'


def _output_lora_markdown(parsed: Dict[str, Any] | None) -> str:
    rows = []
    for item in (parsed or {}).get('loras') or []:
        name = str(item.get('registry_name') or item.get('name') or '').strip() or 'unknown'
        weight = item.get('weight')
        category = str(item.get('registry_category') or '').strip()
        trigger_bits = item.get('triggers') or item.get('keywords') or []
        trigger_text = ', '.join(str(x).strip() for x in trigger_bits if str(x).strip())
        bits = [f'`{name}`']
        if weight not in (None, ''):
            bits.append(f'weight: **{weight}**')
        if category:
            bits.append(f'category: *{category}*')
        if trigger_text:
            bits.append(f'triggers: {trigger_text}')
        if item.get('matched'):
            bits.append('matched in registry ✅')
        rows.append('- ' + ' · '.join(bits))
    tis = (parsed or {}).get('textual_inversions') or []
    for item in tis:
        name = str(item.get('name') or '').strip() or 'unknown'
        weight = item.get('weight')
        bits = [f'`{name}`', 'type: *embedding*']
        if weight not in (None, ''):
            bits.append(f'weight: **{weight}**')
        rows.append('- ' + ' · '.join(bits))
    return '\n'.join(rows) if rows else 'No LoRAs or embeddings detected.'


def _read_uploaded_file(upload_value):
    if not upload_value:
        return None, ''
    path_value = upload_value
    if isinstance(upload_value, list):
        path_value = upload_value[0] if upload_value else None
    if hasattr(path_value, 'name'):
        path_value = path_value.name
    if isinstance(path_value, dict):
        path_value = path_value.get('name') or path_value.get('path') or path_value.get('orig_name')
    if not path_value:
        return None, ''
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return None, path.name
    return path.read_bytes(), path.name


def _inspect_uploaded_output(upload_value, category_value: str = 'uncategorized'):
    content, filename = _read_uploaded_file(upload_value)
    if not content:
        return None, '', '', 'No metadata loaded yet.', '', 'No LoRAs or embeddings detected.', '', '', filename or '', gr.update(value=category_value or 'uncategorized'), '', '⚠️ Upload an output image first.'
    parsed = parse_output_metadata_bytes(content, filename or 'output.png')
    save_name = Path(filename or 'output.png').stem
    return (
        parsed,
        str(parsed.get('positive_prompt') or ''),
        str(parsed.get('negative_prompt') or ''),
        str(parsed.get('settings_summary') or 'No generation summary found.'),
        str(parsed.get('clean_rebuild_prompt') or ''),
        _output_lora_markdown(parsed),
        str(parsed.get('raw_metadata') or ''),
        json.dumps(parsed, indent=2, ensure_ascii=False),
        save_name,
        gr.update(value=category_value or 'uncategorized'),
        '',
        f'✅ Parsed metadata from `{filename}`.',
    )


def _compare_uploaded_outputs(primary_upload, secondary_upload):
    primary_content, primary_name = _read_uploaded_file(primary_upload)
    if not primary_content:
        return None, '', '', 'No metadata loaded yet.', '', 'No LoRAs or embeddings detected.', '', '', '', '⚠️ Upload a primary output image first.'
    secondary_content, secondary_name = _read_uploaded_file(secondary_upload)
    if not secondary_content:
        parsed = parse_output_metadata_bytes(primary_content, primary_name or 'output.png')
        return parsed, str(parsed.get('positive_prompt') or ''), str(parsed.get('negative_prompt') or ''), str(parsed.get('settings_summary') or 'No generation summary found.'), str(parsed.get('clean_rebuild_prompt') or ''), _output_lora_markdown(parsed), str(parsed.get('raw_metadata') or ''), '', '', '⚠️ Upload a second output image to compare.'
    primary = parse_output_metadata_bytes(primary_content, primary_name or 'output.png')
    secondary = parse_output_metadata_bytes(secondary_content, secondary_name or 'compare.png')
    diff = compare_uploaded_output_metadata(primary, secondary)
    lines = []
    if diff.get('positive_changed'):
        lines.append('- Positive prompt changed')
    if diff.get('negative_changed'):
        lines.append('- Negative prompt changed')
    settings_diff = diff.get('settings_diff') or []
    if settings_diff:
        lines.append('- Settings differences:')
        lines.extend([f"  - {row.get('key')}: `{row.get('primary')}` → `{row.get('secondary')}`" for row in settings_diff[:12]])
        if len(settings_diff) > 12:
            lines.append(f'  - ...and {len(settings_diff) - 12} more')
    only_primary = diff.get('loras_only_primary') or []
    only_secondary = diff.get('loras_only_secondary') or []
    if only_primary:
        lines.append('- Only in primary: ' + ', '.join(only_primary))
    if only_secondary:
        lines.append('- Only in secondary: ' + ', '.join(only_secondary))
    weight_diff = diff.get('lora_weight_diff') or []
    if weight_diff:
        lines.append('- LoRA weight differences:')
        lines.extend([f"  - {row.get('name')}: `{row.get('primary_weight')}` → `{row.get('secondary_weight')}`" for row in weight_diff[:12]])
    compare_note = '\n'.join(lines) if lines else 'No major metadata differences detected.'
    return primary, str(primary.get('positive_prompt') or ''), str(primary.get('negative_prompt') or ''), str(primary.get('settings_summary') or 'No generation summary found.'), str(primary.get('clean_rebuild_prompt') or ''), _output_lora_markdown(primary), str(primary.get('raw_metadata') or ''), compare_note, json.dumps(primary, indent=2, ensure_ascii=False), f'✅ Compared `{primary_name}` with `{secondary_name}`.'


def _rebuild_uploaded_prompt(positive_prompt: str, parsed: Dict[str, Any] | None):
    if parsed and isinstance(parsed, dict):
        rebuilt = rebuild_clean_prompt(parsed)
    else:
        rebuilt = rebuild_clean_prompt({'positive_prompt': positive_prompt or ''})
    if not rebuilt:
        return '', '⚠️ Nothing to rebuild yet.'
    return rebuilt, '🧼 Rebuilt prompt cleaned up.'


def _send_uploaded_prompt_to_composer(rebuilt_prompt: str, positive_prompt: str):
    final_prompt = (rebuilt_prompt or '').strip() or (positive_prompt or '').strip()
    if not final_prompt:
        return '', '⚠️ Nothing to send yet.'
    return final_prompt, '✅ Sent recovered prompt to Prompt Composer.'


def _save_uploaded_prompt_record(parsed: Dict[str, Any] | None, name: str, category_value: str, new_category: str, notes: str):
    if not parsed or not isinstance(parsed, dict):
        return '⚠️ Inspect an output image before saving.', gr.update()
    final_name = (name or '').strip() or Path(str(parsed.get('source_filename') or 'output')).stem or 'Recovered Prompt'
    final_category = (new_category or '').strip() or (category_value or '').strip() or 'uncategorized'
    save_uploaded_metadata_as_prompt(name=final_name, category=final_category, parsed=parsed, notes=(notes or '').strip())
    cats = categories('prompt')
    if final_category not in cats:
        cats = sorted(set(cats + [final_category]), key=str.lower)
    return f'✅ Saved `{final_name}` as a prompt record in `{final_category}`.', gr.update(choices=cats, value=final_category)


def _save_uploaded_character_record(parsed: Dict[str, Any] | None, name: str, notes: str):
    if not parsed or not isinstance(parsed, dict):
        return '⚠️ Inspect an output image before saving.',
    final_name = (name or '').strip() or Path(str(parsed.get('source_filename') or 'output')).stem or 'Recovered Character'
    save_uploaded_metadata_as_character(name=final_name, parsed=parsed, notes=(notes or '').strip())
    return f'✅ Saved `{final_name}` as a character base.'


JS_COMMON = r"""
const hostDoc = (() => {
  try {
    if (window.parent && window.parent !== window && window.parent.document) return window.parent.document;
  } catch (e) {}
  return document;
})();
const app = (() => { try { return (typeof gradioApp === 'function') ? gradioApp() : document; } catch(e) { return document; } })();
const q = (sel, root=app) => (root && root.querySelector) ? root.querySelector(sel) : null;
const qa = (sel, root=app) => (root && root.querySelectorAll) ? Array.from(root.querySelectorAll(sel)) : [];
const qHost = (sel) => (hostDoc && hostDoc.querySelector) ? hostDoc.querySelector(sel) : null;
const qaHost = (sel) => (hostDoc && hostDoc.querySelectorAll) ? Array.from(hostDoc.querySelectorAll(sel)) : [];
const fire = (el) => {
  if (!el) return;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
};
const setValue = (el, v) => {
  if (!el) return false;
  el.value = v == null ? '' : String(v);
  fire(el);
  return true;
};
const setCheckbox = (el, v) => {
  if (!el) return false;
  el.checked = !!v;
  fire(el);
  return true;
};
const findTabPanel = (name) => {
  let panel = q(`#tab_${name}`) || q(`#${name}`) || q(`[id*="tab_${name}"]`);
  if (!panel && name === 'txt2img') panel = qHost('#tab-prompt');
  if (!panel && name === 'img2img') panel = qHost('#tab-generate') || qHost('#tab-image');
  if (panel) return panel;
  const btn = qa('[role="tab"]').find(b => {
    const txt = (b.textContent||'').trim().toLowerCase();
    const id = (b.id||'').toLowerCase();
    return txt === name || id.includes(name);
  });
  if (btn) {
    const ctl = btn.getAttribute('aria-controls');
    if (ctl) panel = q(`#${ctl}`);
    try { btn.click(); } catch(e) {}
    if (panel) return panel;
  }
  return null;
};
const findTextareaByLabel = (panel, labelExact) => {
  if (!panel) return null;
  const target = labelExact.trim().toLowerCase();
  const labels = qa('label', panel);
  const lab = labels.find(l => (l.textContent||'').trim().toLowerCase() === target)
           || labels.find(l => (l.textContent||'').trim().toLowerCase().startsWith(target));
  if (!lab) return null;
  let el = lab;
  for (let i=0; i<8; i++) {
    el = el.parentElement;
    if (!el) break;
    const ta = q('textarea', el);
    if (ta) return ta;
  }
  return q('textarea', panel);
};
const findInputByLabel = (panel, labelStarts, wantsTextarea=false) => {
  if (!panel) return null;
  const target = labelStarts.trim().toLowerCase();
  const labels = qa('label', panel);
  const lab = labels.find(l => (l.textContent||'').trim().toLowerCase().startsWith(target));
  if (!lab) return null;
  let el = lab;
  for (let i=0; i<8; i++) {
    el = el.parentElement;
    if (!el) break;
    const found = wantsTextarea ? q('textarea', el) : q('input, textarea, select, [role="combobox"]', el);
    if (found) return found;
  }
  return null;
};
const findLabeledContainer = (root, labelKeywords) => {
  const labels = qa('label, span, div, p', root);
  for (const el of labels) {
    const t = ((el && (el.textContent || el.innerText)) || '').trim().toLowerCase();
    if (!t) continue;
    if (!labelKeywords.some((k) => t.includes(k))) continue;
    let node = el;
    for (let i = 0; i < 4 && node; i += 1) {
      const hasCombo = node.querySelector && node.querySelector('select, [role="combobox"], input, button');
      if (hasCombo) return node;
      node = node.parentElement;
    }
  }
  return null;
};
const optionMatches = (text, wants) => {
  const t = (text || '').trim().toLowerCase();
  return wants.some((w) => t.includes(w));
};
const setSelectFirstMatch = (selectEl, wants) => {
  if (!selectEl || !selectEl.options) return false;
  for (const opt of Array.from(selectEl.options)) {
    if (optionMatches(opt.textContent || opt.value || '', wants)) {
      selectEl.value = opt.value;
      fire(selectEl);
      return true;
    }
  }
  return false;
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const selectCustomDropdown = async (container, wants) => {
  if (!container) return false;
  const native = container.querySelector('select');
  if (native) return setSelectFirstMatch(native, wants);
  const combo = container.querySelector('[role="combobox"], input, button');
  if (!combo) return false;
  try { combo.click(); } catch(e) {}
  combo.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  await sleep(120);
  const options = qa('[role="option"], li, button, div');
  const match = options.find((el) => optionMatches((el.textContent||el.innerText||''), wants));
  if (!match) {
    if (combo.blur) combo.blur();
    return false;
  }
  try { match.click(); } catch(e) {}
  match.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  match.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  await sleep(80);
  return true;
};
const findPromptTA = (panel) => q('#txt2img_prompt textarea') || q('textarea#txt2img_prompt') || q('#txt2img_prompt') || qHost('#prompt-output') || qHost('#prompt-idea') || findTextareaByLabel(panel, 'Prompt') || (panel ? (qa('textarea', panel).find(t => ((t.id||'') + (t.name||'')).toLowerCase().includes('prompt')) || qa('textarea', panel)[0]) : null);
const findNegativeTA = (panel) => q('#txt2img_neg_prompt textarea') || q('textarea#txt2img_neg_prompt') || q('#txt2img_neg_prompt') || qHost('#negative-prompt') || findTextareaByLabel(panel, 'Negative prompt') || (panel ? qa('textarea', panel).find(t => ((t.id||'') + (t.name||'')).toLowerCase().includes('neg')) : null);
"""


JS_FORGE_SET_POSITIVE = r"""
(text) => {
""" + JS_COMMON + r"""
  const panel = findTabPanel('txt2img');
  const ta = findPromptTA(panel);
  if (!setValue(ta, text || '')) {
    alert('Neo Library: could not find the main Forge Positive prompt box.');
  }
  return [text];
}
"""


JS_FORGE_APPEND_POSITIVE = r"""
(text) => {
""" + JS_COMMON + r"""
  const panel = findTabPanel('txt2img');
  const ta = findPromptTA(panel);
  if (!ta) {
    alert('Neo Library: could not find the main Forge Positive prompt box.');
    return [text];
  }
  const current = (ta.value || '').trim();
  const addition = (text || '').trim();
  const next = !addition ? current : (!current ? addition : current + (current.endsWith(',') ? ' ' : ', ') + addition);
  setValue(ta, next);
  return [text];
}
"""


JS_FORGE_SEND_SELECTED_SETTINGS = r"""
(targetTab, mainPos, mainNeg, genJson, usePos, useNeg, useSteps, useCfg, useSeed, useSampler, useScheduler, useSize, useCheckpoint, useVae) => {
""" + JS_COMMON + r"""
  const panel = findTabPanel((targetTab || 'txt2img').toLowerCase());
  if (!panel) {
    alert('Neo Library: target Forge panel not found.');
    return [targetTab, mainPos, mainNeg, genJson, usePos, useNeg, useSteps, useCfg, useSeed, useSampler, useScheduler, useSize, useCheckpoint, useVae];
  }
  const promptTA = findPromptTA(panel) || findTextareaByLabel(panel, 'Prompt');
  const negTA = findNegativeTA(panel);
  if (usePos) setValue(promptTA, mainPos || '');
  if (useNeg) setValue(negTA, mainNeg || '');
  let gen = {};
  try { gen = JSON.parse(genJson || '{}') || {}; } catch(e) { gen = {}; }
  const stepsInput = findInputByLabel(panel, 'Steps');
  const cfgInput = findInputByLabel(panel, 'CFG');
  const seedInput = findInputByLabel(panel, 'Seed');
  const widthInput = findInputByLabel(panel, 'Width');
  const heightInput = findInputByLabel(panel, 'Height');
  if (useSteps && gen['Steps'] != null && gen['Steps'] !== '') setValue(stepsInput, gen['Steps']);
  if (useCfg && gen['CFG scale'] != null && gen['CFG scale'] !== '') setValue(cfgInput, gen['CFG scale']);
  if (useSeed && gen['Seed'] != null && gen['Seed'] !== '') setValue(seedInput, gen['Seed']);
  if (useSize && gen['Size']) {
    const bits = String(gen['Size']).toLowerCase().split('x');
    if (bits.length === 2) {
      setValue(widthInput, bits[0].trim());
      setValue(heightInput, bits[1].trim());
    }
  }
  if (useSampler && gen['Sampler']) {
    const wants = [String(gen['Sampler']).toLowerCase()];
    setSelectFirstMatch(findInputByLabel(panel, 'Sampling method'), wants);
    selectCustomDropdown(findLabeledContainer(panel, ['sampling method', 'sampler']), wants);
  }
  if (useScheduler && (gen['Schedule type'] || gen['Scheduler'])) {
    const wants = [String(gen['Schedule type'] || gen['Scheduler']).toLowerCase()];
    setSelectFirstMatch(findInputByLabel(panel, 'Schedule type'), wants);
    selectCustomDropdown(findLabeledContainer(panel, ['schedule type', 'scheduler']), wants);
  }
  if (useCheckpoint && gen['Model']) {
    const wants = [String(gen['Model']).toLowerCase()];
    setSelectFirstMatch(findInputByLabel(panel, 'Checkpoint'), wants);
    selectCustomDropdown(findLabeledContainer(panel, ['checkpoint']), wants);
  }
  if (useVae && gen['VAE']) {
    const wants = [String(gen['VAE']).toLowerCase()];
    setSelectFirstMatch(findInputByLabel(panel, 'VAE'), wants);
    selectCustomDropdown(findLabeledContainer(panel, ['vae']), wants);
  }
  return [targetTab, mainPos, mainNeg, genJson, usePos, useNeg, useSteps, useCfg, useSeed, useSampler, useScheduler, useSize, useCheckpoint, useVae];
}
"""


def _prompt_category_changed(category: str):
    names = names_for_category('prompt', category)
    prompt = ''
    notes = ''
    if names:
        rec = find_prompt(category, names[0])
        if rec:
            prompt = rec.get('prompt') or rec.get('raw_prompt') or ''
            notes = rec.get('notes') or ''
    return _dropdown_update(names), prompt, notes


def _prompt_name_changed(category: str, name: str):
    rec = find_prompt(category, name)
    if not rec:
        return '', ''
    return rec.get('prompt') or rec.get('raw_prompt') or '', rec.get('notes') or ''


def _caption_meta(rec: Dict[str, Any] | None) -> str:
    if not rec:
        return ''
    return json.dumps({
        'model': rec.get('model') or '',
        'created_at': rec.get('created_at') or '',
        'tags': rec.get('tags') or [],
    }, indent=2, ensure_ascii=False)


def _caption_category_changed(category: str):
    names = names_for_category('caption', category)
    imgs = images_for_category('caption', category)
    rec = find_caption(category, names[0] if names else '', imgs[0] if imgs else '')
    return (
        _dropdown_update(names),
        _dropdown_update(imgs),
        (resolve_media_path(rec.get('image_path') or '') if rec else None),
        (rec.get('caption') or '') if rec else '',
        _caption_meta(rec),
    )


def _caption_selection_changed(category: str, name: str, image_name: str):
    rec = find_caption(category, name, image_name)
    if not rec:
        return None, '', ''
    return resolve_media_path(rec.get('image_path') or '') or None, rec.get('caption') or '', _caption_meta(rec)


def _caption_name_changed(category: str, name: str):
    imgs = images_for_category('caption', category)
    rec = find_caption(category, name, '')
    selected_image = Path(rec.get('image_path') or '').name if rec else (imgs[0] if imgs else None)
    return (
        _dropdown_update(imgs, selected_image),
        resolve_media_path(rec.get('image_path') or '') if rec else None,
        (rec.get('caption') or '') if rec else '',
        _caption_meta(rec),
    )


def _caption_image_changed(category: str, name: str, image_name: str):
    names = names_for_category('caption', category)
    rec = find_caption(category, '', image_name) or find_caption(category, name, '')
    selected_name = (rec.get('name') or '').strip() if rec else ''
    if not selected_name:
        selected_name = name if name in names else (names[0] if names else None)
    return (
        _dropdown_update(names, selected_name),
        resolve_media_path(rec.get('image_path') or '') if rec else None,
        (rec.get('caption') or '') if rec else '',
        _caption_meta(rec),
    )


def _prompt_refresh_payload() -> List[Any]:
    s2 = stats()
    cats_local = categories('prompt')
    first_cat = cats_local[0] if cats_local else None
    first_names = names_for_category('prompt', first_cat or '')
    first_name = first_names[0] if first_names else None
    rec = find_prompt(first_cat or '', first_name or '') if first_cat and first_name else None
    return [
        _dropdown_update(cats_local, first_cat),
        _dropdown_update(first_names, first_name),
        (rec.get('prompt') or rec.get('raw_prompt') or '') if rec else '',
        (rec.get('notes') or '') if rec else '',
        f"**Library root:** `{s2['root']}`  \n**Saved prompts:** {s2['prompt_count']}",
    ]


def _caption_refresh_payload() -> List[Any]:
    s2 = stats()
    cats_local = categories('caption')
    first_cat_local = cats_local[0] if cats_local else None
    names_local = names_for_category('caption', first_cat_local or '')
    imgs_local = images_for_category('caption', first_cat_local or '')
    rec = find_caption(first_cat_local or '', names_local[0] if names_local else '', imgs_local[0] if imgs_local else '')
    return [
        _dropdown_update(cats_local, first_cat_local),
        _dropdown_update(names_local, names_local[0] if names_local else None),
        _dropdown_update(imgs_local, imgs_local[0] if imgs_local else None),
        resolve_media_path(rec.get('image_path') or '') if rec else None,
        (rec.get('caption') or '') if rec else '',
        _caption_meta(rec),
        f"**Library root:** `{s2['root']}`  \n**Saved captions:** {s2['caption_count']}",
    ]


def build_prompt_library_ui(positive_out):
    prompt_stats = stats()
    cats = categories('prompt')
    with gr.Column():
        gr.Markdown('### 🗂️ Prompt Library')
        gr.Markdown('Browse prompts saved by **Neo Studio**, send them either to the main Forge Positive prompt or into **Prompt Composer** for editing, and delete entries you no longer need.')
        with gr.Row():
            refresh = gr.Button('🔄 Refresh prompt library')
            info = gr.Markdown(f"**Library root:** `{prompt_stats['root']}`  \n**Saved prompts:** {prompt_stats['prompt_count']}")
        with gr.Row():
            prompt_category = gr.Dropdown(label='Category', choices=cats, value=(cats[0] if cats else None), allow_custom_value=False)
            prompt_name = gr.Dropdown(label='Name', choices=names_for_category('prompt', cats[0] if cats else ''), value=None, allow_custom_value=False)
        prompt_text = gr.Textbox(label='Saved prompt', lines=8)
        with gr.Row():
            send_forge_btn = gr.Button('Send to Forge Positive')
            send_composer_btn = gr.Button('Send to Prompt Composer', variant='secondary')
            append_forge_btn = gr.Button('Append to Forge Positive', variant='secondary')
        prompt_notes = gr.Textbox(label='Notes', lines=3)
        with gr.Row():
            delete_btn = gr.Button('Delete selected prompt', variant='stop')
            status = gr.Markdown('')

        def _refresh():
            return (*_prompt_refresh_payload(), '✅ Prompt library refreshed.')

        def _delete(category: str, name: str):
            ok, msg = delete_prompt_record(category, name)
            return (*_prompt_refresh_payload(), ('✅ ' + msg) if ok else ('⚠️ ' + msg))

        refresh.click(_refresh, outputs=[prompt_category, prompt_name, prompt_text, prompt_notes, info, status], queue=False)
        prompt_category.change(_prompt_category_changed, inputs=[prompt_category], outputs=[prompt_name, prompt_text, prompt_notes], queue=False)
        prompt_name.change(_prompt_name_changed, inputs=[prompt_category, prompt_name], outputs=[prompt_text, prompt_notes], queue=False)
        send_forge_btn.click(lambda text: '✅ Sent to Forge Positive.', inputs=[prompt_text], outputs=[status], queue=False, js=JS_FORGE_SET_POSITIVE)
        send_composer_btn.click(_replace_positive, inputs=[prompt_text], outputs=[positive_out, status], queue=False)
        append_forge_btn.click(lambda text: '✅ Appended to Forge Positive.', inputs=[prompt_text], outputs=[status], queue=False, js=JS_FORGE_APPEND_POSITIVE)
        delete_btn.click(_delete, inputs=[prompt_category, prompt_name], outputs=[prompt_category, prompt_name, prompt_text, prompt_notes, info, status], queue=False)


def build_caption_library_ui(positive_out):
    s = stats()
    cats = categories('caption')
    first_cat = cats[0] if cats else None
    first_names = names_for_category('caption', first_cat or '')
    first_imgs = images_for_category('caption', first_cat or '')
    first_rec = find_caption(first_cat or '', first_names[0] if first_names else '', first_imgs[0] if first_imgs else '')
    preview_path = resolve_media_path(first_rec.get('image_path') or '') if first_rec else None

    js_send = r"""
(targetTab, unitIdx, kind, auto) => {
  if (typeof cnbridgeSendFromPreview !== 'function') {
    alert('Neo Library: missing cnbridgeSendFromPreview().');
    return [targetTab, unitIdx, kind, auto];
  }
  const run = async () => {
    await cnbridgeSendFromPreview(targetTab, unitIdx, kind, auto, 'neo_library_caption_preview', 'source');
  };
  run();
  return [targetTab, unitIdx, kind, auto];
}
"""

    with gr.Column():
        gr.Markdown('### 🖼️ Caption Library')
        gr.Markdown('Select a saved caption entry, preview the image, send that image to ControlNet / IP-Adapter, send the caption text into the prompt boxes, or delete the entry when you no longer need it.')
        with gr.Row():
            refresh = gr.Button('🔄 Refresh caption library')
            info = gr.Markdown(f"**Library root:** `{s['root']}`  \n**Saved captions:** {s['caption_count']}")
        with gr.Row():
            cap_category = gr.Dropdown(label='Category', choices=cats, value=first_cat, allow_custom_value=False)
            cap_name = gr.Dropdown(label='Name', choices=first_names, value=(first_names[0] if first_names else None), allow_custom_value=False)
            cap_image = gr.Dropdown(label='Image', choices=first_imgs, value=(first_imgs[0] if first_imgs else None), allow_custom_value=False)
        preview = gr.Image(label='Image preview', value=preview_path, elem_id='neo_library_caption_preview', type='filepath', interactive=False, height=320)
        caption_box = gr.Textbox(label='Saved caption', value=(first_rec.get('caption') or '') if first_rec else '', lines=8)
        with gr.Row():
            cap_send_forge_btn = gr.Button('Send to Forge Positive')
            cap_send_composer_btn = gr.Button('Send to Prompt Composer', variant='secondary')
            cap_append_forge_btn = gr.Button('Append to Forge Positive', variant='secondary')
        meta_box = gr.Textbox(label='Metadata', value=_caption_meta(first_rec), lines=6)
        with gr.Row():
            target_tab = gr.Dropdown(label='Target workspace', choices=TAB_CHOICES, value='txt2img')
            target_kind = gr.Dropdown(label='Send target', choices=TARGET_CHOICES, value='canny')
            unit_idx = gr.Slider(label='ControlNet unit index', minimum=0, maximum=7, step=1, value=0)
            auto_cfg = gr.Checkbox(label='Try auto-config', value=True)
        with gr.Row():
            send_btn = gr.Button('Send image')
            delete_btn = gr.Button('Delete selected caption', variant='stop')
        action_status = gr.Markdown('')

        def _refresh():
            return (*_caption_refresh_payload(), '✅ Caption library refreshed.')

        def _delete(category: str, name: str, image_name: str):
            ok, msg = delete_caption_record(category, name, image_name)
            return (*_caption_refresh_payload(), ('✅ ' + msg) if ok else ('⚠️ ' + msg))

        refresh.click(_refresh, outputs=[cap_category, cap_name, cap_image, preview, caption_box, meta_box, info, action_status], queue=False)
        cap_category.change(_caption_category_changed, inputs=[cap_category], outputs=[cap_name, cap_image, preview, caption_box, meta_box], queue=False)
        cap_name.change(_caption_name_changed, inputs=[cap_category, cap_name], outputs=[cap_image, preview, caption_box, meta_box], queue=False)
        cap_image.change(_caption_image_changed, inputs=[cap_category, cap_name, cap_image], outputs=[cap_name, preview, caption_box, meta_box], queue=False)
        cap_send_forge_btn.click(lambda text: '✅ Sent to Forge Positive.', inputs=[caption_box], outputs=[action_status], queue=False, js=JS_FORGE_SET_POSITIVE)
        cap_send_composer_btn.click(_replace_positive, inputs=[caption_box], outputs=[positive_out, action_status], queue=False)
        cap_append_forge_btn.click(lambda text: '✅ Appended to Forge Positive.', inputs=[caption_box], outputs=[action_status], queue=False, js=JS_FORGE_APPEND_POSITIVE)
        send_btn.click(fn=lambda *x: x, inputs=[target_tab, unit_idx, target_kind, auto_cfg], outputs=[target_tab, unit_idx, target_kind, auto_cfg], js=js_send)
        delete_btn.click(_delete, inputs=[cap_category, cap_name, cap_image], outputs=[cap_category, cap_name, cap_image, preview, caption_box, meta_box, info, action_status], queue=False)


def _output_mode_changed(mode: str):
    names = output_image_names(mode)
    first = names[0] if names else None
    rec = load_output_record(mode, first or '') if first else None
    return (
        _dropdown_update(names, first),
        rec.get('image_path') if rec else None,
        rec.get('main_positive') if rec else '',
        rec.get('main_negative') if rec else '',
        rec.get('adetailer_positive') if rec else '',
        rec.get('adetailer_negative') if rec else '',
        rec.get('generation_json') if rec else '{}',
        rec.get('controlnet_json') if rec else '{}',
        rec.get('extra_json') if rec else '{}',
        rec.get('raw_parameters') if rec else '',
        f"Output folder: `{get_output_dirs().get(mode)}`  \nImages found: {len(names)}  \nSidecar found: {'Yes' if rec and rec.get('sidecar_found') else 'No'}",
    )


def _output_name_changed(mode: str, name: str):
    rec = load_output_record(mode, name)
    return (
        rec.get('image_path'),
        rec.get('main_positive'),
        rec.get('main_negative'),
        rec.get('adetailer_positive'),
        rec.get('adetailer_negative'),
        rec.get('generation_json'),
        rec.get('controlnet_json'),
        rec.get('extra_json'),
        rec.get('raw_parameters'),
        f"Output folder: `{get_output_dirs().get(mode)}`  \nSelected image: `{name}`  \nSidecar found: {'Yes' if rec.get('sidecar_found') else 'No'}",
    )


def build_output_inspector_ui(positive_out):
    modes = get_output_dirs()
    mode_names = list(modes.keys())
    mode = 'txt2img' if 'txt2img' in modes else (mode_names[0] if mode_names else 'txt2img')
    image_names = output_image_names(mode)
    first_name = image_names[0] if image_names else None
    first = load_output_record(mode, first_name or '') if first_name else None
    prompt_categories = categories('prompt')

    js_send_image = r"""
(targetTab, unitIdx, kind, auto) => {
  if (typeof cnbridgeSendFromPreview !== 'function') {
    alert('Neo Library: missing cnbridgeSendFromPreview().');
    return [targetTab, unitIdx, kind, auto];
  }
  const run = async () => {
    await cnbridgeSendFromPreview(targetTab, unitIdx, kind, auto, 'neo_output_preview', 'source');
  };
  run();
  return [targetTab, unitIdx, kind, auto];
}
"""

    js_copy_rebuilt = r"""
(prompt) => {
  const text = (prompt || '').toString();
  if (!text.trim()) {
    alert('Neo Library: nothing to copy yet.');
    return [prompt];
  }
  const run = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      console.warn('Neo Library copy failed', e);
    }
  };
  run();
  return [prompt];
}
"""

    with gr.Column():
        gr.Markdown('### 🧾 Output Inspector')
        gr.Markdown('Browse txt2img/img2img outputs, recover prompt data from uploaded output images, inspect structured metadata from sidecar JSON when available, send chosen settings back to the main Forge UI, or send the image to ControlNet / IP-Adapter.')

        uploaded_state = gr.State(None)
        compare_state = gr.State(None)
        with gr.Accordion('Recover from uploaded output image', open=True):
            with gr.Row():
                metadata_upload = gr.File(label='Inspect output image', file_count='single', file_types=['image'])
                metadata_compare_upload = gr.File(label='Compare with another output (optional)', file_count='single', file_types=['image'])
            with gr.Row():
                inspect_metadata_btn = gr.Button('Inspect metadata', variant='primary')
                compare_metadata_btn = gr.Button('Compare outputs')
                metadata_send_prompt_btn = gr.Button('Send to Prompt Composer')
                metadata_clean_rebuild_btn = gr.Button('Clean rebuild prompt')
                metadata_copy_rebuild_btn = gr.Button('Copy rebuilt prompt')
            metadata_status = gr.Markdown('')
            metadata_compare_note = gr.Markdown('')
            with gr.Row():
                metadata_positive = gr.Textbox(label='Positive prompt', lines=6, placeholder='Positive prompt extracted from metadata...')
                metadata_negative = gr.Textbox(label='Negative prompt', lines=6, placeholder='Negative prompt extracted from metadata...')
            with gr.Row():
                metadata_save_name = gr.Textbox(label='Save name', placeholder='Recovered Prompt / Character name')
                metadata_save_category = gr.Dropdown(label='Prompt category', choices=prompt_categories, value=(prompt_categories[0] if prompt_categories else 'uncategorized'), allow_custom_value=True)
                metadata_save_category_new = gr.Textbox(label='New prompt category', placeholder='Optional new category')
            metadata_notes = gr.Textbox(label='Metadata notes', lines=3, placeholder='Optional notes before saving...')
            with gr.Row():
                save_metadata_prompt_btn = gr.Button('Save as Prompt Record', variant='secondary')
                save_metadata_character_btn = gr.Button('Save as Character Base', variant='secondary')
            with gr.Row():
                metadata_settings_summary = gr.Markdown('No metadata loaded yet.')
                metadata_lora_list = gr.Markdown('No LoRAs or embeddings detected.')
            metadata_clean_rebuild = gr.Textbox(label='Clean rebuild prompt', lines=5, elem_id='neo_library_rebuilt_prompt', placeholder='Clean rebuilt prompt appears here...')
            metadata_raw = gr.Textbox(label='Raw metadata', lines=10, placeholder='Raw metadata text appears here...')
            metadata_json = gr.Textbox(label='Metadata JSON', visible=False)

        with gr.Row():
            out_mode = gr.Dropdown(label='Output folder', choices=mode_names, value=mode)
            out_name = gr.Dropdown(label='Image file', choices=image_names, value=first_name)
            refresh_btn = gr.Button('🔄 Refresh outputs')
        out_info = gr.Markdown(f"Output folder: `{modes.get(mode)}`  \nImages found: {len(image_names)}  \nSidecar found: {'Yes' if first and first.get('sidecar_found') else 'No'}")
        preview = gr.Image(label='Output preview', value=(first.get('image_path') if first else None), elem_id='neo_output_preview', type='filepath', interactive=False, height=420)

        with gr.Accordion('Prompt fields', open=True):
            main_positive = gr.Textbox(label='Positive', value=(first.get('main_positive') if first else ''), lines=6)
            main_negative = gr.Textbox(label='Negative', value=(first.get('main_negative') if first else ''), lines=4)
        with gr.Accordion('ADetailer prompts', open=False):
            adetailer_positive = gr.Textbox(label='ADetailer positive', value=(first.get('adetailer_positive') if first else ''), lines=4)
            adetailer_negative = gr.Textbox(label='ADetailer negative', value=(first.get('adetailer_negative') if first else ''), lines=4)
        with gr.Accordion('Generation data', open=True):
            generation_json = gr.Textbox(label='Generation settings', value=(first.get('generation_json') if first else '{}'), lines=10)
            controlnet_json = gr.Textbox(label='ControlNet summary', value=(first.get('controlnet_json') if first else '{}'), lines=6)
            extra_json = gr.Textbox(label='Extra params', value=(first.get('extra_json') if first else '{}'), lines=6)
            raw_parameters = gr.Textbox(label='Raw PNG parameters', value=(first.get('raw_parameters') if first else ''), lines=8)

        with gr.Accordion('Send selected settings to Forge UI', open=False):
            restore_target = gr.Dropdown(label='Target workspace', choices=TAB_CHOICES, value='txt2img')
            with gr.Row():
                use_pos = gr.Checkbox(label='Positive', value=True)
                use_neg = gr.Checkbox(label='Negative', value=False)
            with gr.Row():
                use_steps = gr.Checkbox(label='Steps', value=True)
                use_cfg = gr.Checkbox(label='CFG', value=True)
                use_seed = gr.Checkbox(label='Seed', value=True)
                use_sampler = gr.Checkbox(label='Sampler', value=False)
                use_scheduler = gr.Checkbox(label='Scheduler', value=False)
            with gr.Row():
                use_size = gr.Checkbox(label='Width / Height', value=True)
                use_checkpoint = gr.Checkbox(label='Checkpoint', value=False)
                use_vae = gr.Checkbox(label='VAE', value=False)
            restore_btn = gr.Button('Send selected settings')

        with gr.Accordion('Send image to ControlNet / IP-Adapter', open=False):
            with gr.Row():
                target_tab = gr.Dropdown(label='Target workspace', choices=TAB_CHOICES, value='txt2img')
                target_kind = gr.Dropdown(label='Send target', choices=TARGET_CHOICES, value='canny')
                unit_idx = gr.Slider(label='ControlNet unit index', minimum=0, maximum=7, step=1, value=0)
                auto_cfg = gr.Checkbox(label='Try auto-config', value=True)
            send_img_btn = gr.Button('Send image')
        output_status = gr.Markdown('')

        def _refresh(mode_value: str):
            return (*_output_mode_changed(mode_value), '✅ Output list refreshed.')

        inspect_metadata_btn.click(
            _inspect_uploaded_output,
            inputs=[metadata_upload, metadata_save_category],
            outputs=[uploaded_state, metadata_positive, metadata_negative, metadata_settings_summary, metadata_clean_rebuild, metadata_lora_list, metadata_raw, metadata_json, metadata_save_name, metadata_save_category, metadata_compare_note, metadata_status],
            queue=False,
        )
        compare_metadata_btn.click(
            _compare_uploaded_outputs,
            inputs=[metadata_upload, metadata_compare_upload],
            outputs=[uploaded_state, metadata_positive, metadata_negative, metadata_settings_summary, metadata_clean_rebuild, metadata_lora_list, metadata_raw, metadata_compare_note, metadata_json, metadata_status],
            queue=False,
        )
        metadata_clean_rebuild_btn.click(
            _rebuild_uploaded_prompt,
            inputs=[metadata_positive, uploaded_state],
            outputs=[metadata_clean_rebuild, metadata_status],
            queue=False,
        )
        metadata_send_prompt_btn.click(
            _send_uploaded_prompt_to_composer,
            inputs=[metadata_clean_rebuild, metadata_positive],
            outputs=[positive_out, metadata_status],
            queue=False,
        )
        metadata_copy_rebuild_btn.click(
            fn=lambda prompt: prompt,
            inputs=[metadata_clean_rebuild],
            outputs=[metadata_clean_rebuild],
            queue=False,
            js=js_copy_rebuilt,
        )
        save_metadata_prompt_btn.click(
            _save_uploaded_prompt_record,
            inputs=[uploaded_state, metadata_save_name, metadata_save_category, metadata_save_category_new, metadata_notes],
            outputs=[metadata_status, metadata_save_category],
            queue=False,
        )
        save_metadata_character_btn.click(
            _save_uploaded_character_record,
            inputs=[uploaded_state, metadata_save_name, metadata_notes],
            outputs=[metadata_status],
            queue=False,
        )

        out_mode.change(_output_mode_changed, inputs=[out_mode], outputs=[out_name, preview, main_positive, main_negative, adetailer_positive, adetailer_negative, generation_json, controlnet_json, extra_json, raw_parameters, out_info], queue=False)
        out_name.change(_output_name_changed, inputs=[out_mode, out_name], outputs=[preview, main_positive, main_negative, adetailer_positive, adetailer_negative, generation_json, controlnet_json, extra_json, raw_parameters, out_info], queue=False)
        refresh_btn.click(_refresh, inputs=[out_mode], outputs=[out_name, preview, main_positive, main_negative, adetailer_positive, adetailer_negative, generation_json, controlnet_json, extra_json, raw_parameters, out_info, output_status], queue=False)
        restore_btn.click(
            lambda *_: '✅ Tried to send selected settings to Forge UI.',
            inputs=[restore_target, main_positive, main_negative, generation_json, use_pos, use_neg, use_steps, use_cfg, use_seed, use_sampler, use_scheduler, use_size, use_checkpoint, use_vae],
            outputs=[output_status],
            queue=False,
            js=JS_FORGE_SEND_SELECTED_SETTINGS,
        )
        send_img_btn.click(fn=lambda *x: x, inputs=[target_tab, unit_idx, target_kind, auto_cfg], outputs=[target_tab, unit_idx, target_kind, auto_cfg], js=js_send_image)


def build_library_settings_ui():
    s = stats()
    with gr.Column():
        gr.Markdown('### ⚙️ Library Settings')
        gr.Markdown('Point **Neo Library** at the same shared data folder used by **Neo Studio**.')
        root_box = gr.Textbox(label='Shared library root', value=s['root'])
        counts = gr.Markdown(f"**Saved prompts:** {s['prompt_count']}  \n**Saved captions:** {s['caption_count']}  \n**Categories:** {', '.join(s['categories']) if s['categories'] else 'None yet'}")
        with gr.Row():
            save_btn = gr.Button('Save library root')
            refresh_btn = gr.Button('Refresh counts', variant='secondary')
        status = gr.Markdown('')

        def _save(path: str):
            target = (path or '').strip()
            if not target:
                return gr.update(), gr.update(), '⚠️ Enter a folder path first.'
            set_library_root(target)
            s2 = stats()
            return s2['root'], f"**Saved prompts:** {s2['prompt_count']}  \n**Saved captions:** {s2['caption_count']}  \n**Categories:** {', '.join(s2['categories']) if s2['categories'] else 'None yet'}", '✅ Saved Neo Library root.'

        def _refresh_only():
            s2 = stats()
            return s2['root'], f"**Saved prompts:** {s2['prompt_count']}  \n**Saved captions:** {s2['caption_count']}  \n**Categories:** {', '.join(s2['categories']) if s2['categories'] else 'None yet'}", '✅ Refreshed library stats.'

        save_btn.click(_save, inputs=[root_box], outputs=[root_box, counts, status], queue=False)
        refresh_btn.click(_refresh_only, outputs=[root_box, counts, status], queue=False)
