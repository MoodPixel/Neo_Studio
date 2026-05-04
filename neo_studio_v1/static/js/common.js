const boot = window.NEO_STUDIO_BOOT || {};
window.NEO_STUDIO_BASE_TITLE = document.title || 'Neo Studio';

const initialCategories = boot.initialCategories || [];
const initialPromptPresets = boot.initialPromptPresets || {};
const initialCaptionPresets = boot.initialCaptionPresets || {};
const initialPromptEntries = boot.initialPromptEntries || [];
const initialCharacterEntries = boot.initialCharacterEntries || [];
const initialPromptCategoryList = boot.promptCategories || [];
const initialLastPromptCategory = boot.lastPromptCategory || 'uncategorized';
const initialLastCaptionCategory = boot.lastCaptionCategory || 'uncategorized';
const initialLastPromptPreset = boot.lastPromptPreset || '';
const initialLastCaptionPreset = boot.lastCaptionPreset || '';
const initialBundleEntries = boot.initialBundleEntries || [];

let promptPresets = initialPromptPresets || {};
let captionPresets = initialCaptionPresets || {};
let currentPromptFinishReason = '';
let currentCaptionFinishReason = '';
let loadedPromptId = '';
let loadedCharacterName = '';
let loadedCaptionId = '';
let currentMetadataPayload = null;
let promptAbortController = null;
let variationResultsState = [];
let promptSingleOutputForcedVisible = false;
let currentBatchJobId = '';
let batchPollHandle = null;
const activeTimers = {};

function $(id) { return document.getElementById(id); }
function currentModel() { return $('model-select').value || 'default'; }

function requireBackendRole(role, statusId, message='') {
  const checker = window.isBackendRoleConnected;
  if (typeof checker === 'function' && checker(role)) return true;
  const label = role === 'image' ? 'Image Backend' : 'Text Backend';
  setStatus(statusId, message || `Connect a ${label} first.`, 'warn');
  return false;
}

function trim(v) { return (v || '').toString().trim(); }

function setStatus(id, text, level='') {
  const el = $(id);
  if (!el) return;
  el.textContent = text || '';
  el.className = 'status' + (level ? ` ${level}` : '');
}

function setWarning(id, text) {
  const el = $(id);
  if (!el) return;
  el.textContent = text || '';
  el.classList.toggle('hidden', !text);
}

function setBusy(buttonId, busy, busyText='Working...') {
  const btn = $(buttonId);
  if (!btn) return;
  if (busy) {
    btn.dataset.originalText = btn.textContent;
    btn.textContent = busyText;
  } else if (btn.dataset.originalText) {
    btn.textContent = btn.dataset.originalText;
  }
  btn.disabled = !!busy;
}


function formatElapsed(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const mins = String(Math.floor(total / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return `${mins}:${secs}`;
}

function startTimer(key, targetId, label='Elapsed') {
  stopTimer(key, false);
  const started = Date.now();
  const tick = () => {
    const el = $(targetId);
    if (!el) return;
    const seconds = (Date.now() - started) / 1000;
    el.textContent = `${label}: ${formatElapsed(seconds)}`;
  };
  tick();
  activeTimers[key] = { started, targetId, label, handle: setInterval(tick, 250) };
}

function stopTimer(key, keepText=true) {
  const timer = activeTimers[key];
  if (!timer) return 0;
  clearInterval(timer.handle);
  const seconds = (Date.now() - timer.started) / 1000;
  if (keepText) {
    const el = $(timer.targetId);
    if (el) el.textContent = `Finished in: ${formatElapsed(seconds)}`;
  }
  delete activeTimers[key];
  return seconds;
}

function resetTimer(targetId, label='Elapsed') {
  const el = $(targetId);
  if (el) el.textContent = `${label}: 00:00`;
}


function setPromptRunControls(running) {
  if ($('btn-cancel-prompt-run')) $('btn-cancel-prompt-run').disabled = !running;
  if (!running) promptAbortController = null;
}

async function safeFetchJson(url, options={}) {
  const resp = await fetch(url, options);
  let data = {};
  try { data = await resp.json(); } catch (e) { data = { ok:false, message:'Invalid server response.' }; }
  if (!resp.ok || data.ok === false) {
    throw new Error(data.message || `Request failed (${resp.status})`);
  }
  return data;
}

function updateStats(data) {
  if (!data) return;
  $('stat-root').textContent = data.root || $('stat-root').textContent;
  $('stat-prompts').textContent = data.prompt_count ?? $('stat-prompts').textContent;
  $('stat-captions').textContent = data.caption_count ?? $('stat-captions').textContent;
  if (Array.isArray(data.categories)) refreshCategoryList(data.categories);
}

function refreshCategoryList(categories) {
  const vals = Array.isArray(categories) && categories.length ? categories.slice() : ['uncategorized'];
  ['prompt-category','caption-category','batch-category','saved-prompt-category','caption-editor-category','metadata-save-category','neo-library-prompt-editor-category','neo-library-caption-category'].forEach(id => { if ($(id)) fillCategorySelect(id, vals, $(id)?.value || 'uncategorized'); });
  if ($('neo-library-prompt-category')) fillCategorySelect('neo-library-prompt-category', ['all', ...vals.filter(v => v !== 'all')], $('neo-library-prompt-category').value || 'all');
  if ($('caption-browser-category')) fillCategorySelect('caption-browser-category', ['all', ...vals.filter(v => v !== 'all')], $('caption-browser-category').value || 'all');
  if (typeof populateLibraryExportCategories === 'function') populateLibraryExportCategories(vals);
}

function fillCategorySelect(id, categories, selected='uncategorized') {
  const select = $(id);
  if (!select) return;
  const vals = Array.isArray(categories) && categories.length ? categories.slice() : ['uncategorized'];
  if (!vals.includes(selected)) vals.push(selected);
  vals.sort((a,b) => a.localeCompare(b, undefined, { sensitivity:'base' }));
  select.innerHTML = '';
  vals.forEach(cat => {
    const opt = document.createElement('option');
    opt.value = cat;
    opt.textContent = cat;
    if (cat === selected) opt.selected = true;
    select.appendChild(opt);
  });
}

function resolveCategory(selectId, newId) {
  const newVal = trim($(newId).value);
  return newVal || $(selectId).value || 'uncategorized';
}

function formatPresetOptionLabel(name, preset) {
  const bits = [];
  if (preset?.favorite) bits.push('★');
  bits.push(name);
  if (preset?.group) bits.push(`· ${preset.group}`);
  if (preset?.kind === 'custom') bits.push('(custom)');
  return bits.join(' ');
}

function presetMetaSummary(preset) {
  if (!preset) return '';
  const parts = [];
  parts.push(`Kind: ${preset.kind || 'builtin'}`);
  if (preset.group) parts.push(`Group: ${preset.group}`);
  if (preset.favorite) parts.push('Favorite: yes');
  if (preset.usage_count !== undefined) parts.push(`Used: ${preset.usage_count || 0}`);
  if (preset.last_used) parts.push(`Last used: ${String(preset.last_used).replace('T', ' ')}`);
  return parts.join(' · ');
}

function fillNamedSelect(selectId, names, selected='', placeholder='—') {
  const sel = $(selectId);
  if (!sel) return;
  sel.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  sel.appendChild(first);
  (names || []).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    if (name === selected) opt.selected = true;
    sel.appendChild(opt);
  });
}

function populatePresetSelect(selectId, presets, lastPreset) {
  const sel = $(selectId);
  if (!sel) return;
  sel.innerHTML = '';
  Object.keys(presets).sort((a,b) => a.localeCompare(b, undefined, { sensitivity:'base' })).forEach(name => {
    const preset = presets[name] || {};
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = formatPresetOptionLabel(name, preset);
    if (name === lastPreset) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!sel.value && sel.options.length) sel.selectedIndex = 0;
}

function applyPromptPreset(name, remember=true) {
  const preset = promptPresets[name];
  if (!preset) return;
  $('prompt-style').value = preset.style || 'Descriptive';
  $('prompt-custom').value = preset.custom_instructions || '';
  $('prompt-max-tokens').value = preset.max_tokens ?? 220;
  $('prompt-temperature').value = preset.temperature ?? 0.35;
  $('prompt-top-p').value = preset.top_p ?? 0.9;
  $('prompt-top-k').value = preset.top_k ?? 40;
  if ($('prompt-preset-group')) $('prompt-preset-group').value = preset.group || '';
  if ($('prompt-preset-notes')) $('prompt-preset-notes').value = preset.notes || '';
  if ($('prompt-preset-favorite')) $('prompt-preset-favorite').checked = !!preset.favorite;
  if ($('prompt-preset-meta')) $('prompt-preset-meta').textContent = presetMetaSummary(preset);
  if (typeof refreshPromptPresetAux === 'function') refreshPromptPresetAux(name);
  if (remember) {
    const fd = new FormData();
    fd.append('name', name);
    fetch('/api/set-prompt-preset', { method:'POST', body:fd })
      .then(r => r.json())
      .then(data => {
        if (data?.presets) {
          promptPresets = data.presets;
          populatePresetSelect('prompt-preset', promptPresets, data.last_preset || name);
          if (typeof refreshPromptPresetAux === 'function') refreshPromptPresetAux(data.last_preset || name);
          const updated = promptPresets[data.last_preset || name] || preset;
          if ($('prompt-preset-meta')) $('prompt-preset-meta').textContent = presetMetaSummary(updated);
        }
      })
      .catch(() => {});
  }
}

function applyCaptionPreset(name, remember=true) {
  const preset = captionPresets[name];
  if (!preset) return;
  $('caption-style').value = preset.prompt_style || 'Custom';
  $('caption-length').value = preset.caption_length || 'any';
  $('caption-custom').value = preset.custom_prompt || '';
  $('caption-max-tokens').value = preset.max_new_tokens ?? 160;
  $('caption-temperature').value = preset.temperature ?? 0.2;
  $('caption-top-p').value = preset.top_p ?? 0.9;
  $('caption-top-k').value = preset.top_k ?? 40;
  $('caption-prefix').value = preset.prefix || '';
  $('caption-suffix').value = preset.suffix || '';
  $('caption-output-style').value = preset.output_style || 'Auto (match input)';
  if ($('caption-mode')) $('caption-mode').value = preset.caption_mode || 'full_image';
  if ($('caption-component-type')) $('caption-component-type').value = preset.component_type || '';
  if ($('caption-detail-level')) $('caption-detail-level').value = preset.detail_level || 'detailed';
  if ($('caption-preset-group')) $('caption-preset-group').value = preset.group || '';
  if ($('caption-preset-notes')) $('caption-preset-notes').value = preset.notes || '';
  if ($('caption-preset-favorite')) $('caption-preset-favorite').checked = !!preset.favorite;
  if ($('caption-preset-meta')) $('caption-preset-meta').textContent = presetMetaSummary(preset);
  if (typeof applyCaptionModeDefaults === 'function') applyCaptionModeDefaults(true);
  if (typeof refreshCaptionPresetAux === 'function') refreshCaptionPresetAux(name);
  if (remember) {
    const fd = new FormData();
    fd.append('name', name);
    fetch('/api/set-caption-preset', { method:'POST', body:fd })
      .then(r => r.json())
      .then(data => {
        if (data?.presets) {
          captionPresets = data.presets;
          populatePresetSelect('caption-preset', captionPresets, data.last_preset || name);
          if (typeof refreshCaptionPresetAux === 'function') refreshCaptionPresetAux(data.last_preset || name);
          const updated = captionPresets[data.last_preset || name] || preset;
          if ($('caption-preset-meta')) $('caption-preset-meta').textContent = presetMetaSummary(updated);
        }
      })
      .catch(() => {});
  }
}

function promptSettingsJson() {
  return JSON.stringify({
    max_tokens: Number($('prompt-max-tokens').value || 220),
    temperature: Number($('prompt-temperature').value || 0.35),
    top_p: Number($('prompt-top-p').value || 0.9),
    top_k: Number($('prompt-top-k').value || 40),
  });
}

function captionSettingsJson() {
  return JSON.stringify({
    max_new_tokens: Number($('caption-max-tokens').value || 160),
    temperature: Number($('caption-temperature').value || 0.2),
    top_p: Number($('caption-top-p').value || 0.9),
    top_k: Number($('caption-top-k').value || 40),
    output_style: $('caption-output-style').value,
    caption_length: $('caption-length').value,
    caption_mode: $('caption-mode') ? $('caption-mode').value : 'full_image',
    component_type: $('caption-component-type') ? $('caption-component-type').value : '',
    detail_level: $('caption-detail-level') ? $('caption-detail-level').value : 'detailed',
  });
}

function updateCounter(inputId, outputId) {
  const value = $(inputId).value || '';
  $(outputId).textContent = `${value.length} chars`;
}

function fillSavedPromptEntries(entries, selectedId='') {
  const sel = $('saved-prompt-id');
  sel.innerHTML = '';
  (entries || []).forEach(entry => {
    const opt = document.createElement('option');
    opt.value = entry.id;
    opt.textContent = entry.label || entry.name || entry.id;
    if (entry.id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!sel.value && sel.options.length) sel.selectedIndex = 0;
}


function fillSavedCharacterEntries(entries, selectedName='') {
  const sel = $('saved-character-name');
  if (!sel) return;
  sel.innerHTML = '';
  (entries || []).forEach(entry => {
    const opt = document.createElement('option');
    opt.value = entry.id || entry.name;
    opt.textContent = entry.label || entry.name || entry.id;
    if ((entry.id || entry.name) === selectedName) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!sel.value && sel.options.length) sel.selectedIndex = 0;
}

function syncPromptOutputVisibility() {
  const multiEnabled = $('prompt-enable-variations').checked;
  const wrap = $('prompt-single-output-wrap');
  const label = $('prompt-output-label');
  const shouldShow = !multiEnabled || promptSingleOutputForcedVisible;
  wrap.classList.toggle('hidden', !shouldShow);
  label.textContent = (multiEnabled && promptSingleOutputForcedVisible) ? 'Selected final output' : 'Generated output';
}

function renderVariationInputs() {
  const enabled = $('prompt-enable-variations').checked;
  const wrap = $('prompt-variation-inputs');
  const count = Math.max(2, Math.min(8, Number($('prompt-variation-count').value || 2)));
  if (enabled) {
    promptSingleOutputForcedVisible = false;
  } else {
    promptSingleOutputForcedVisible = false;
  }
  wrap.classList.toggle('hidden', !enabled);
  $('prompt-run-mode').textContent = enabled ? `${count} variation run(s)` : 'Single run';
  syncPromptOutputVisibility();
  if (!enabled) {
    wrap.innerHTML = '';
    return;
  }
  wrap.innerHTML = '';
  for (let i = 1; i <= count; i++) {
    const card = document.createElement('div');
    card.className = 'variation-card';
    card.innerHTML = `
      <h3>Variation ${i}</h3>
      <label for="variation-input-${i}">Variation ${i} direction</label>
      <textarea id="variation-input-${i}" placeholder="Extra direction for variation ${i}..."></textarea>
    `;
    wrap.appendChild(card);
  }
}

function escapeHtml(text) {
  return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderVariationResults(results) {
  const wrap = $('prompt-variation-results');
  variationResultsState = Array.isArray(results) ? results.slice() : [];
  wrap.innerHTML = '';
  wrap.classList.toggle('hidden', !variationResultsState.length);
  variationResultsState.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'variation-card';
    const elapsed = formatElapsed(item.elapsed_seconds || 0);
    card.innerHTML = `
      <div class="row-between">
        <h3>Variation ${index + 1}</h3>
        <div class="mini-note">${escapeHtml(item.status || 'done')} · ${elapsed} · finish: ${escapeHtml(item.finish_reason || 'stop')}</div>
      </div>
      <div class="mini-note" style="margin-bottom:8px;">${escapeHtml(item.tweak || 'No extra direction.')}</div>
      <textarea readonly>${escapeHtml(item.prompt || '')}</textarea>
      <div class="row" style="margin-top:10px;">
        <button class="btn" type="button" data-variation-load="${index}">Use as final output</button>
        <button class="btn" type="button" data-variation-copy="${index}">Copy variation</button>
      </div>
    `;
    wrap.appendChild(card);
  });
}
