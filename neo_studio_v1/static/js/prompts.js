async function refreshSavedPromptNames() {
  try {
    const category = $('saved-prompt-category').value || '';
    const data = await safeFetchJson(`/api/prompt-records?category=${encodeURIComponent(category)}`);
    fillSavedPromptEntries(data.entries || [], loadedPromptId);
  } catch (e) {
    setStatus('saved-prompt-status', e.message, 'error');
  }
}

function uniqueTags(text) {
  const parts = (text || '').split(',').map(x => x.trim()).filter(Boolean);
  const seen = new Set();
  const out = [];
  parts.forEach(tag => {
    const key = tag.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(tag);
    }
  });
  return out.join(', ');
}

function promptPresetRecentNames(limit=8) {
  return Object.entries(promptPresets || {})
    .sort((a, b) => {
      const aa = String(a[1]?.last_used || '');
      const bb = String(b[1]?.last_used || '');
      if (aa === bb) return a[0].localeCompare(b[0], undefined, { sensitivity:'base' });
      return bb.localeCompare(aa);
    })
    .slice(0, limit)
    .map(([name]) => name);
}

function refreshPromptPresetAux(selectedName='') {
  const current = selectedName || $('prompt-preset')?.value || '';
  const names = Object.keys(promptPresets || {}).sort((a, b) => a.localeCompare(b, undefined, { sensitivity:'base' }));
  fillNamedSelect('prompt-preset-recent', promptPresetRecentNames(), '', 'Recent presets');
  fillNamedSelect('prompt-preset-compare', names.filter(name => name !== current), '', 'Choose preset');
  const preset = promptPresets[current] || {};
  if ($('prompt-preset-group')) $('prompt-preset-group').value = preset.group || '';
  if ($('prompt-preset-notes')) $('prompt-preset-notes').value = preset.notes || '';
  if ($('prompt-preset-favorite')) $('prompt-preset-favorite').checked = !!preset.favorite;
  if ($('prompt-preset-meta')) $('prompt-preset-meta').textContent = presetMetaSummary(preset);
  if ($('prompt-preset-compare-output')) {
    $('prompt-preset-compare-output').classList.add('hidden');
    $('prompt-preset-compare-output').textContent = '';
  }
}

function renderPromptPresetComparison(comparison) {
  const wrap = $('prompt-preset-compare-output');
  if (!wrap) return;
  const diffs = comparison?.differences || [];
  if (!diffs.length) {
    wrap.textContent = 'No differences found between the selected prompt presets.';
    wrap.classList.remove('hidden');
    return;
  }
  const lines = [`${comparison.title_a} vs ${comparison.title_b}`];
  diffs.forEach(row => lines.push(`${row.field}: ${row.a ?? '—'} → ${row.b ?? '—'}`));
  wrap.textContent = lines.join('\n');
  wrap.classList.remove('hidden');
}

function downloadJsonPayload(filename, payload) {
  const blob = new Blob([JSON.stringify(payload || {}, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function runImprove(mode, targetStatus='prompt-qa-status') {
  if (!requireBackendRole('text', targetStatus, 'Connect a Text Backend first. Prompt cleanup and rewrite actions use it.')) return;
  const prompt = trim($('prompt-output').value);
  if (!prompt) {
    setStatus(targetStatus, 'Nothing to improve yet.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('model', currentModel());
  fd.append('prompt', prompt);
  fd.append('mode', mode);
  setStatus(targetStatus, 'Running prompt improvement...');
  try {
    const data = await safeFetchJson('/api/improve-prompt', { method:'POST', body:fd });
    $('prompt-output').value = data.prompt || prompt;
    updateCounter('prompt-output', 'prompt-output-counter');
    maybeRunPromptQA('auto');
    setStatus(targetStatus, 'Prompt updated.');
  } catch (e) {
    setStatus(targetStatus, e.message, 'error');
  }
}


let promptQATimer = null;

function renderPromptQA(result) {
  const summaryEl = $('prompt-qa-summary');
  const statsEl = $('prompt-qa-stats');
  const listEl = $('prompt-qa-list');
  if (!summaryEl || !statsEl || !listEl) return;
  const warnings = result?.warnings || [];
  summaryEl.textContent = result?.summary || 'No QA result yet.';
  const stats = result?.stats || {};
  const statBits = [];
  if (typeof stats.chars === 'number') statBits.push(`<span class="kbd">${stats.chars} chars</span>`);
  if (typeof stats.words === 'number') statBits.push(`<span class="kbd">${stats.words} words</span>`);
  if (typeof stats.tags === 'number' && stats.tags) statBits.push(`<span class="kbd">${stats.tags} tags</span>`);
  if (typeof result?.warning_count === 'number') statBits.push(`<span class="kbd">${result.warning_count} flags</span>`);
  statsEl.innerHTML = statBits.join('');
  if (!warnings.length) {
    listEl.innerHTML = `<div class="prompt-qa-item"><div class="prompt-qa-item-title">Looks clean <span class="badge">ready</span></div><div class="prompt-qa-item-detail">No major structure issues were flagged. You can still use the cleanup buttons below if you want a tighter version.</div></div>`;
    return;
  }
  listEl.innerHTML = warnings.map(item => `
    <div class="prompt-qa-item ${escapeHtml(item.severity || 'warn')}">
      <div class="prompt-qa-item-title">${escapeHtml(item.title || 'Prompt QA warning')} <span class="badge">${escapeHtml(item.kind || 'qa')}</span></div>
      <div class="prompt-qa-item-detail">${escapeHtml(item.detail || '')}</div>
      <div class="prompt-qa-item-suggestion">Fix: ${escapeHtml(item.suggestion || 'Tighten the prompt and keep the subject clearer up front.')}</div>
    </div>
  `).join('');
}

async function runPromptQA(trigger='manual') {
  const prompt = trim($('prompt-output').value || '');
  if (!prompt) {
    $('prompt-qa-summary').textContent = 'Add or generate a prompt first.';
    $('prompt-qa-stats').innerHTML = '';
    $('prompt-qa-list').innerHTML = '';
    if (trigger === 'manual') setStatus('prompt-qa-status', 'Nothing to analyze yet.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('prompt', prompt);
  if (trigger === 'manual') setStatus('prompt-qa-status', 'Analyzing prompt...');
  try {
    const data = await safeFetchJson('/api/prompt-qa', { method:'POST', body:fd });
    renderPromptQA(data || {});
    if (trigger === 'manual') {
      setStatus('prompt-qa-status', data.warning_count ? `Found ${data.warning_count} prompt QA flag${data.warning_count === 1 ? '' : 's'}.` : 'Prompt looks clean.');
    } else {
      setStatus('prompt-qa-status', data.warning_count ? `Auto QA: ${data.warning_count} flag${data.warning_count === 1 ? '' : 's'}.` : 'Auto QA: clean.');
    }
  } catch (e) {
    setStatus('prompt-qa-status', e.message, 'error');
  }
}

function schedulePromptQAAuto() {
  if (!$('prompt-qa-auto')?.checked) return;
  clearTimeout(promptQATimer);
  promptQATimer = window.setTimeout(() => runPromptQA('auto'), 350);
}

function maybeRunPromptQA(trigger='auto') {
  if (!$('prompt-qa-auto')?.checked) return;
  clearTimeout(promptQATimer);
  promptQATimer = window.setTimeout(() => runPromptQA(trigger), 50);
}

async function generatePrompt() {
  if (!requireBackendRole('text', 'prompt-run-status', 'Connect a Text Backend first. Generate Prompt uses the active text model.')) return;
  const multiEnabled = $('prompt-enable-variations').checked;
  if (multiEnabled) {
    const count = Math.max(2, Math.min(8, Number($('prompt-variation-count').value || 2)));
    const results = [];
    setBusy('btn-generate-prompt', true, 'Generating...');
    setPromptRunControls(true);
    setStatus('prompt-run-status', `Generating ${count} variations...`);
    setWarning('prompt-warning', '');
    startTimer('prompt', 'prompt-elapsed');
    promptSingleOutputForcedVisible = false;
    syncPromptOutputVisibility();
    $('prompt-output').value = '';
    $('prompt-raw').value = '';
    renderVariationResults([]);
    try {
      for (let i = 1; i <= count; i++) {
        const tweak = trim($(`variation-input-${i}`)?.value || '');
        const fd = new FormData();
        fd.append('model', currentModel());
        fd.append('idea', $('prompt-idea').value);
        fd.append('style', $('prompt-style').value);
        const extra = [$('prompt-custom').value || '', tweak ? `Variation direction: ${tweak}` : ''].filter(Boolean).join('\n\n');
        fd.append('custom_instructions', extra);
        fd.append('max_tokens', $('prompt-max-tokens').value);
        fd.append('temperature', $('prompt-temperature').value);
        fd.append('top_p', $('prompt-top-p').value);
        fd.append('top_k', $('prompt-top-k').value);
        promptAbortController = new AbortController();
        const started = performance.now();
        setStatus('prompt-run-status', `Running variation ${i} / ${count}...`);
        const data = await safeFetchJson('/api/generate-prompt', { method:'POST', body:fd, signal: promptAbortController.signal });
        const elapsedSeconds = (performance.now() - started) / 1000;
        results.push({ tweak, prompt: data.prompt || '', finish_reason: data.finish_reason || '', status: data.prompt ? 'ready' : 'empty', elapsed_seconds: elapsedSeconds });
        currentPromptFinishReason = data.finish_reason || currentPromptFinishReason;
        renderVariationResults(results);
      }
      setStatus('prompt-run-status', `Generated ${results.length} variations.`);
    } catch (e) {
      setStatus('prompt-run-status', (e.name === 'AbortError') ? 'Run cancelled.' : (e.message || 'Variation run failed.'), (e.name === 'AbortError') ? 'warn' : 'error');
    } finally {
      promptAbortController = null;
      stopTimer('prompt');
      setPromptRunControls(false);
      setBusy('btn-generate-prompt', false);
    }
    return;
  }

  promptSingleOutputForcedVisible = false;
  syncPromptOutputVisibility();
  const fd = new FormData();
  fd.append('model', currentModel());
  fd.append('idea', $('prompt-idea').value);
  fd.append('style', $('prompt-style').value);
  fd.append('custom_instructions', $('prompt-custom').value);
  fd.append('max_tokens', $('prompt-max-tokens').value);
  fd.append('temperature', $('prompt-temperature').value);
  fd.append('top_p', $('prompt-top-p').value);
  fd.append('top_k', $('prompt-top-k').value);
  promptAbortController = new AbortController();
  setBusy('btn-generate-prompt', true, 'Generating...');
  setPromptRunControls(true);
  setStatus('prompt-run-status', 'Generating prompt...');
  setWarning('prompt-warning', '');
  startTimer('prompt', 'prompt-elapsed');
  renderVariationResults([]);
  try {
    const data = await safeFetchJson('/api/generate-prompt', { method:'POST', body:fd, signal: promptAbortController.signal });
    $('prompt-output').value = data.prompt || '';
    $('prompt-raw').value = data.prompt || '';
    currentPromptFinishReason = data.finish_reason || '';
    $('prompt-finish-reason').textContent = `finish: ${currentPromptFinishReason || 'stop'}`;
    setWarning('prompt-warning', data.warning || '');
    setStatus('prompt-run-status', data.prompt ? 'Prompt ready.' : 'No prompt returned.', data.warning ? 'warn' : '');
    updateCounter('prompt-output', 'prompt-output-counter');
    maybeRunPromptQA('auto');
  } catch (e) {
    setStatus('prompt-run-status', (e.name === 'AbortError') ? 'Run cancelled.' : e.message, (e.name === 'AbortError') ? 'warn' : 'error');
  } finally {
    promptAbortController = null;
    stopTimer('prompt');
    setPromptRunControls(false);
    setBusy('btn-generate-prompt', false);
  }
}

async function continuePrompt() {
  if (!requireBackendRole('text', 'prompt-run-status', 'Connect a Text Backend first. Continue uses the active text model.')) return;
  const currentOutput = trim($('prompt-output').value);
  if (!currentOutput) {
    setStatus('prompt-run-status', 'Generate something first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('model', currentModel());
  fd.append('idea', $('prompt-idea').value);
  fd.append('current_output', currentOutput);
  fd.append('style', $('prompt-style').value);
  fd.append('custom_instructions', $('prompt-custom').value);
  fd.append('max_tokens', $('prompt-max-tokens').value);
  fd.append('temperature', $('prompt-temperature').value);
  fd.append('top_p', $('prompt-top-p').value);
  fd.append('top_k', $('prompt-top-k').value);
  setBusy('btn-continue-prompt', true, 'Continuing...');
  setPromptRunControls(true);
  setStatus('prompt-run-status', 'Continuing cut-off output...');
  startTimer('prompt', 'prompt-elapsed');
  try {
    const data = await safeFetchJson('/api/continue-prompt', { method:'POST', body:fd });
    $('prompt-output').value = data.prompt || currentOutput;
    $('prompt-raw').value = data.prompt || currentOutput;
    currentPromptFinishReason = data.finish_reason || '';
    $('prompt-finish-reason').textContent = `finish: ${currentPromptFinishReason || 'stop'}`;
    setWarning('prompt-warning', data.warning || '');
    setStatus('prompt-run-status', data.continuation ? 'Continuation added.' : 'No continuation returned.', data.warning ? 'warn' : '');
    updateCounter('prompt-output', 'prompt-output-counter');
    maybeRunPromptQA('auto');
  } catch (e) {
    setStatus('prompt-run-status', (e.name === 'AbortError') ? 'Run cancelled.' : e.message, (e.name === 'AbortError') ? 'warn' : 'error');
  } finally {
    stopTimer('prompt');
    setBusy('btn-continue-prompt', false);
  }
}

async function savePromptPreset(overwriteSelected=false) {
  let name = $('prompt-preset').value;
  if (!overwriteSelected || !name || (promptPresets[name] && promptPresets[name].kind !== 'custom')) {
    name = prompt('Preset name:', overwriteSelected && name ? name : '');
  }
  name = trim(name);
  if (!name) return;
  const fd = new FormData();
  fd.append('name', name);
  fd.append('style', $('prompt-style').value);
  fd.append('custom_instructions', $('prompt-custom').value);
  fd.append('max_tokens', $('prompt-max-tokens').value);
  fd.append('temperature', $('prompt-temperature').value);
  fd.append('top_p', $('prompt-top-p').value);
  fd.append('top_k', $('prompt-top-k').value);
  fd.append('group', $('prompt-preset-group')?.value || '');
  fd.append('notes', $('prompt-preset-notes')?.value || '');
  fd.append('favorite', $('prompt-preset-favorite')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/save-prompt-preset', { method:'POST', body:fd });
    promptPresets = data.presets || promptPresets;
    populatePresetSelect('prompt-preset', promptPresets, data.last_preset || name);
    applyPromptPreset(data.last_preset || name, false);
    refreshPromptPresetAux(data.last_preset || name);
    setStatus('prompt-preset-status', data.message || 'Preset saved.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('prompt-preset-status', e.message, 'error');
  }
}

async function deletePromptPreset() {
  const name = $('prompt-preset').value;
  if (!name) return;
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/delete-prompt-preset', { method:'POST', body:fd });
    promptPresets = data.presets || promptPresets;
    populatePresetSelect('prompt-preset', promptPresets, data.last_preset || 'Descriptive');
    applyPromptPreset($('prompt-preset').value, false);
    refreshPromptPresetAux($('prompt-preset').value);
    setStatus('prompt-preset-status', data.message || 'Preset deleted.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('prompt-preset-status', e.message, 'error');
  }
}

async function duplicatePromptPreset() {
  const source = $('prompt-preset').value || '';
  if (!source) {
    setStatus('prompt-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  const newName = trim(prompt('New preset name:', `${source} Copy`) || '');
  if (!newName) return;
  const fd = new FormData();
  fd.append('source_name', source);
  fd.append('new_name', newName);
  try {
    const data = await safeFetchJson('/api/duplicate-prompt-preset', { method:'POST', body:fd });
    promptPresets = data.presets || promptPresets;
    populatePresetSelect('prompt-preset', promptPresets, data.last_preset || newName);
    applyPromptPreset(data.last_preset || newName, false);
    refreshPromptPresetAux(data.last_preset || newName);
    setStatus('prompt-preset-meta-status', data.message || 'Preset duplicated.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('prompt-preset-meta-status', e.message, 'error');
  }
}

async function togglePromptPresetFavorite() {
  const name = $('prompt-preset').value || '';
  if (!name) {
    setStatus('prompt-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/toggle-prompt-preset-favorite', { method:'POST', body:fd });
    promptPresets = data.presets || promptPresets;
    populatePresetSelect('prompt-preset', promptPresets, data.last_preset || name);
    applyPromptPreset(data.last_preset || name, false);
    refreshPromptPresetAux(data.last_preset || name);
    setStatus('prompt-preset-meta-status', data.favorite ? 'Preset marked as favorite.' : 'Preset favorite removed.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('prompt-preset-meta-status', e.message, 'error');
  }
}

async function comparePromptPresets() {
  const nameA = $('prompt-preset').value || '';
  const nameB = $('prompt-preset-compare').value || '';
  if (!nameA || !nameB) {
    setStatus('prompt-preset-meta-status', 'Choose two presets to compare.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/compare-prompt-presets?name_a=${encodeURIComponent(nameA)}&name_b=${encodeURIComponent(nameB)}`);
    renderPromptPresetComparison(data.comparison || {});
    setStatus('prompt-preset-meta-status', 'Preset comparison ready.');
  } catch (e) {
    setStatus('prompt-preset-meta-status', e.message, 'error');
  }
}

async function exportSinglePromptPreset() {
  const name = $('prompt-preset').value || '';
  if (!name) {
    setStatus('prompt-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/export-single-preset?kind=prompt&name=${encodeURIComponent(name)}`);
    downloadJsonPayload(`neo_prompt_preset_${name.replace(/[^a-z0-9_-]+/gi, '_')}.json`, data.payload || {});
    setStatus('prompt-preset-meta-status', 'Preset export ready.');
  } catch (e) {
    setStatus('prompt-preset-meta-status', e.message, 'error');
  }
}

async function savePromptEntry() {
  const fd = new FormData();
  const finalCategory = resolveCategory('prompt-category', 'prompt-category-new');
  fd.append('name', $('prompt-name').value || 'Untitled Prompt');
  fd.append('category', finalCategory);
  fd.append('prompt', $('prompt-output').value || '');
  fd.append('raw_prompt', $('prompt-raw').value || $('prompt-output').value || '');
  fd.append('model', currentModel());
  fd.append('notes', $('prompt-notes').value || '');
  fd.append('preset_name', $('prompt-preset').value || '');
  fd.append('style', $('prompt-style').value || '');
  fd.append('finish_reason', currentPromptFinishReason || '');
  fd.append('settings_json', promptSettingsJson());
  fd.append('generation_mode', 'generate');
  try {
    const data = await safeFetchJson('/api/save-prompt', { method:'POST', body:fd });
    updateStats(data.stats);
    if (data.prompt_categories) fillCategorySelect('saved-prompt-category', data.prompt_categories, finalCategory);
    if (data.entries) fillSavedPromptEntries(data.entries, data.record?.id || '');
    fillCategorySelect('prompt-category', data.categories || initialCategories, finalCategory);
    $('prompt-category-new').value = '';
    $('prompt-name').value = data.record?.name || $('prompt-name').value;
    loadedPromptId = data.record?.id || loadedPromptId;
    setStatus('prompt-save-status', data.message || 'Prompt saved.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('prompt-save-status', e.message, 'error');
  }
}

async function loadSavedPrompt() {
  const promptId = $('saved-prompt-id').value || '';
  if (!promptId) return;
  try {
    const data = await safeFetchJson(`/api/prompt-record?prompt_id=${encodeURIComponent(promptId)}`);
    const rec = data.record || {};
    loadedPromptId = rec.id || promptId;
    $('prompt-name').value = rec.name || '';
    fillCategorySelect('prompt-category', [$('saved-prompt-category').value || 'uncategorized'], rec.category || 'uncategorized');
    $('prompt-output').value = rec.prompt || rec.raw_prompt || '';
    $('prompt-raw').value = rec.raw_prompt || rec.prompt || '';
    $('prompt-notes').value = rec.notes || '';
    $('prompt-style').value = rec.style || $('prompt-style').value;
    currentPromptFinishReason = rec.finish_reason || '';
    $('prompt-finish-reason').textContent = `finish: ${currentPromptFinishReason || '—'}`;
    updateCounter('prompt-output', 'prompt-output-counter');
    maybeRunPromptQA('auto');
    setStatus('saved-prompt-status', 'Loaded prompt.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('saved-prompt-status', e.message, 'error');
  }
}

async function updateLoadedPrompt() {
  if (!loadedPromptId) {
    setStatus('saved-prompt-status', 'Pick a saved prompt first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('prompt_id', loadedPromptId);
  fd.append('category', $('saved-prompt-category').value || '');
  fd.append('prompt', $('prompt-output').value || '');
  fd.append('raw_prompt', $('prompt-raw').value || $('prompt-output').value || '');
  fd.append('model', currentModel());
  fd.append('notes', $('prompt-notes').value || '');
  try {
    const data = await safeFetchJson('/api/update-prompt', { method:'POST', body:fd });
    if (data.entries) fillSavedPromptEntries(data.entries, loadedPromptId);
    setStatus('saved-prompt-status', data.message || 'Updated.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('saved-prompt-status', e.message, 'error');
  }
}

async function deleteLoadedPrompt() {
  if (!loadedPromptId) {
    setStatus('saved-prompt-status', 'Pick a saved prompt first.', 'warn');
    return;
  }
  if (!confirm('Delete the loaded prompt?')) return;
  const fd = new FormData();
  fd.append('prompt_id', loadedPromptId);
  fd.append('category', $('saved-prompt-category').value || '');
  try {
    const data = await safeFetchJson('/api/delete-prompt', { method:'POST', body:fd });
    fillSavedPromptEntries(data.entries || [], '');
    loadedPromptId = '';
    setStatus('saved-prompt-status', data.message || 'Deleted.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('saved-prompt-status', e.message, 'error');
  }
}

async function improveLoadedPrompt() {
  if (!requireBackendRole('text', 'saved-prompt-status', 'Connect a Text Backend first. Improving a saved prompt uses it.')) return;
  await runImprove($('prompt-improve-mode').value, 'saved-prompt-status');
}


let bundleEntries = (boot.initialBundleEntries || []);
let loadedBundleId = '';
let bundleSupportCache = { characters: [], metadata_records: [] };

function fillBundleEntries(entries, selected='') {
  bundleEntries = Array.isArray(entries) ? entries : [];
  const select = $('saved-bundle-id');
  if (!select) return;
  select.innerHTML = '';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = bundleEntries.length ? 'Select a bundle…' : 'No bundles yet';
  select.appendChild(empty);
  bundleEntries.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.id || '';
    opt.textContent = item.label || item.name || '(untitled)';
    select.appendChild(opt);
  });
  select.value = selected || '';
}

function fillBundleSupportData(characters=[], metadataRecords=[]) {
  bundleSupportCache = { characters: characters || [], metadata_records: metadataRecords || [] };
  const charSelect = $('bundle-character');
  if (charSelect) {
    charSelect.innerHTML = '<option value="">None</option>';
    (characters || []).forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.name || item.id || '';
      opt.textContent = item.label || item.name || '(unnamed)';
      charSelect.appendChild(opt);
    });
  }
  const metaSelect = $('bundle-metadata-record');
  if (metaSelect) {
    metaSelect.innerHTML = '<option value="">None</option>';
    (metadataRecords || []).forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id || '';
      opt.textContent = item.label || item.name || '(unnamed)';
      metaSelect.appendChild(opt);
    });
  }
}

function bundleFormData(includeFile=true) {
  const fd = new FormData();
  fd.append('name', $('bundle-name').value || 'Untitled Bundle');
  fd.append('positive_prompt', $('bundle-positive').value || '');
  fd.append('negative_prompt', $('bundle-negative').value || '');
  fd.append('character_name', $('bundle-character').value || '');
  fd.append('loras_text', $('bundle-loras').value || '');
  fd.append('model_default', $('bundle-model-default').value || '');
  fd.append('checkpoint_default', $('bundle-checkpoint-default').value || '');
  fd.append('cfg_default', $('bundle-cfg-default').value || '');
  fd.append('steps_default', $('bundle-steps-default').value || '');
  fd.append('sampler_default', $('bundle-sampler-default').value || '');
  fd.append('style_notes', $('bundle-style-notes').value || '');
  fd.append('metadata_record_id', $('bundle-metadata-record').value || '');
  fd.append('clear_reference_image', $('bundle-clear-reference').checked ? 'true' : 'false');
  const file = $('bundle-reference-image').files?.[0];
  if (includeFile && file) fd.append('reference_image', file, file.name || 'reference.png');
  return fd;
}

function renderBundleMeta(rec={}) {
  const meta = $('bundle-meta');
  if (!meta) return;
  if (!rec || !rec.id) {
    meta.textContent = 'No bundle loaded.';
    $('bundle-reference-preview-wrap')?.classList.add('hidden');
    return;
  }
  const pills = [];
  if (rec.character_name) pills.push(`<span class="bundle-meta-pill">Character: ${escapeHtml(rec.character_name)}</span>`);
  if (rec.model_default) pills.push(`<span class="bundle-meta-pill">Model: ${escapeHtml(rec.model_default)}</span>`);
  if (rec.checkpoint_default) pills.push(`<span class="bundle-meta-pill">Checkpoint: ${escapeHtml(rec.checkpoint_default)}</span>`);
  if (rec.metadata_record_id) pills.push(`<span class="bundle-meta-pill">Metadata snapshot linked</span>`);
  if ((rec.loras || []).length) pills.push(`<span class="bundle-meta-pill">LoRAs: ${escapeHtml(String((rec.loras || []).length))}</span>`);
  meta.innerHTML = `<div><strong>${escapeHtml(rec.name || '(untitled)')}</strong></div><div class="mini-note" style="margin-top:6px;">Updated: ${escapeHtml(String(rec.updated_at || '').replace('T',' '))}</div><div class="bundle-meta-list">${pills.join(' ')}</div>`;
  const wrap = $('bundle-reference-preview-wrap');
  const img = $('bundle-reference-preview');
  if (rec.reference_image_url && img && wrap) {
    img.src = rec.reference_image_url + `&v=${Date.now()}`;
    wrap.classList.remove('hidden');
  } else if (wrap) {
    wrap.classList.add('hidden');
  }
}

function applyBundleToForm(rec={}) {
  loadedBundleId = rec.id || '';
  if (!$('bundle-name')) {
    if (rec && rec.id) applyBundleToWorkspace(rec);
    return;
  }
  $('bundle-name').value = rec.name || '';
  $('bundle-positive').value = rec.positive_prompt || '';
  $('bundle-negative').value = rec.negative_prompt || '';
  $('bundle-character').value = rec.character_name || '';
  $('bundle-loras').value = Array.isArray(rec.loras) ? rec.loras.join(', ') : (rec.loras || '');
  $('bundle-model-default').value = rec.model_default || '';
  $('bundle-checkpoint-default').value = rec.checkpoint_default || '';
  $('bundle-cfg-default').value = rec.cfg_default || '';
  $('bundle-steps-default').value = rec.steps_default || '';
  $('bundle-sampler-default').value = rec.sampler_default || '';
  $('bundle-style-notes').value = rec.style_notes || '';
  $('bundle-metadata-record').value = rec.metadata_record_id || '';
  $('bundle-clear-reference').checked = false;
  $('bundle-reference-image').value = '';
  renderBundleMeta(rec);
  if ($('saved-bundle-id')) $('saved-bundle-id').value = rec.id || '';
}

function applyBundleToWorkspace(rec={}) {
  switchTab('prompt');
  $('prompt-output').value = rec.positive_prompt || '';
  $('prompt-raw').value = rec.positive_prompt || '';
  $('prompt-notes').value = [rec.style_notes || '', rec.negative_prompt ? `Negative prompt: ${rec.negative_prompt}` : '', (rec.loras || []).length ? `Attached LoRAs/TI: ${(rec.loras || []).join(', ')}` : '', rec.checkpoint_default ? `Checkpoint: ${rec.checkpoint_default}` : '', rec.cfg_default ? `CFG: ${rec.cfg_default}` : '', rec.steps_default ? `Steps: ${rec.steps_default}` : '', rec.sampler_default ? `Sampler: ${rec.sampler_default}` : ''].filter(Boolean).join('\n');
  if (rec.character_name && $('saved-character-name')) $('saved-character-name').value = rec.character_name;
  updateCounter('prompt-output', 'prompt-output-counter');
  maybeRunPromptQA('auto');
  setStatus('bundle-status', 'Bundle opened in Prompt Studio.');
}


async function refreshBundleSupportData() {
  try {
    const data = await safeFetchJson('/api/bundle-support-data');
    fillBundleSupportData(data.characters || [], data.metadata_records || []);
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function refreshBundleRecords(selectId='') {
  try {
    const data = await safeFetchJson('/api/bundle-records');
    fillBundleEntries(data.entries || [], selectId || loadedBundleId || '');
    fillBundleSupportData(data.characters || [], data.metadata_records || []);
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function saveBundleRecord() {
  const fd = bundleFormData(true);
  try {
    const data = await safeFetchJson('/api/save-bundle', { method:'POST', body:fd });
    fillBundleEntries(data.entries || [], data.record?.id || '');
    applyBundleToForm(data.record || {});
    setStatus('bundle-status', data.message || 'Bundle saved.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function updateBundleRecord() {
  if (!loadedBundleId) {
    setStatus('bundle-status', 'Load a bundle first.', 'warn');
    return;
  }
  const fd = bundleFormData(true);
  fd.append('bundle_id', loadedBundleId);
  try {
    const data = await safeFetchJson('/api/update-bundle', { method:'POST', body:fd });
    fillBundleEntries(data.entries || [], data.record?.id || loadedBundleId);
    applyBundleToForm(data.record || {});
    setStatus('bundle-status', data.message || 'Bundle updated.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function loadSelectedBundle() {
  const id = $('saved-bundle-id').value || loadedBundleId || '';
  if (!id) {
    setStatus('bundle-status', 'Pick a saved bundle first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/bundle-record?bundle_id=${encodeURIComponent(id)}`);
    applyBundleToForm(data.record || {});
    setStatus('bundle-status', 'Bundle loaded.');
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function deleteSelectedBundle() {
  if (!loadedBundleId) {
    setStatus('bundle-status', 'Load a bundle first.', 'warn');
    return;
  }
  if (!confirm('Delete the loaded bundle?')) return;
  const fd = new FormData();
  fd.append('bundle_id', loadedBundleId);
  try {
    const data = await safeFetchJson('/api/delete-bundle', { method:'POST', body:fd });
    fillBundleEntries(data.entries || [], '');
    loadedBundleId = '';
    applyBundleToForm({});
    $('bundle-name').value = '';
    $('bundle-positive').value = '';
    $('bundle-negative').value = '';
    $('bundle-loras').value = '';
    $('bundle-style-notes').value = '';
    setStatus('bundle-status', data.message || 'Bundle deleted.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

async function duplicateSelectedBundle() {
  if (!loadedBundleId) {
    setStatus('bundle-status', 'Load a bundle first.', 'warn');
    return;
  }
  const newName = trim(prompt('New bundle name:', `${$('bundle-name').value || 'Bundle'} Copy`) || '');
  if (!newName) return;
  const fd = new FormData();
  fd.append('bundle_id', loadedBundleId);
  fd.append('new_name', newName);
  try {
    const data = await safeFetchJson('/api/duplicate-bundle', { method:'POST', body:fd });
    fillBundleEntries(data.entries || [], data.record?.id || '');
    applyBundleToForm(data.record || {});
    setStatus('bundle-status', data.message || 'Bundle duplicated.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('bundle-status', e.message, 'error');
  }
}

function pullCurrentPromptIntoBundle() {
  $('bundle-positive').value = $('prompt-output').value || $('prompt-idea').value || '';
  const notes = $('prompt-notes').value || '';
  if (notes && !$('bundle-style-notes').value) $('bundle-style-notes').value = notes;
  const promptName = trim($('prompt-name').value || '');
  if (promptName && !$('bundle-name').value) $('bundle-name').value = promptName;
  setStatus('bundle-status', 'Current prompt copied into bundle editor.');
}
