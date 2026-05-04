async function previewBatch() {
  const fd = new FormData();
  fd.append('folder_path', $('batch-folder').value || '');
  fd.append('recursive', $('batch-recursive').checked ? 'true' : 'false');
  fd.append('include_exts', $('batch-extensions').value || '');
  setBusy('btn-batch-preview', true, 'Previewing...');
  setStatus('batch-status', 'Scanning folder...');
  try {
    const data = await safeFetchJson('/api/caption-batch-preview', { method:'POST', body:fd });
    const lines = [data.message || `Found ${data.count || 0} files.`];
    (data.sample || []).forEach(x => lines.push(x));
    $('batch-log').value = lines.join('\n');
    setStatus('batch-status', data.message || 'Preview ready.');
  } catch (e) {
    setStatus('batch-status', e.message, 'error');
  } finally {
    setBusy('btn-batch-preview', false);
  }
}

function buildBatchFormData() {
  const fd = new FormData();
  const batchMode = $('batch-mode').value;
  fd.append('model', currentModel());
  fd.append('mode', batchMode);
  fd.append('folder_path', $('batch-folder').value || '');
  fd.append('category', resolveCategory('batch-category', 'batch-category-new'));
  fd.append('base_name', $('batch-base-name').value || 'Batch_Caption');
  fd.append('numbering_start', (batchMode === 'library' ? $('batch-library-number-start')?.value : $('batch-number-start')?.value) || '1');
  fd.append('overwrite_existing', $('batch-overwrite').checked ? 'true' : 'false');
  fd.append('skip_existing_txt', $('batch-skip-existing').checked ? 'true' : 'false');
  fd.append('skip_duplicates', $('batch-skip-duplicates').checked ? 'true' : 'false');
  fd.append('recursive', $('batch-recursive').checked ? 'true' : 'false');
  fd.append('include_exts', $('batch-extensions').value || '');
  fd.append('prompt_style', $('caption-style').value);
  fd.append('caption_length', $('caption-length').value);
  fd.append('custom_prompt', $('caption-custom').value);
  fd.append('max_new_tokens', $('caption-max-tokens').value);
  fd.append('temperature', $('caption-temperature').value);
  fd.append('top_p', $('caption-top-p').value);
  fd.append('top_k', $('caption-top-k').value);
  fd.append('prefix', $('caption-prefix').value);
  fd.append('suffix', $('caption-suffix').value);
  fd.append('output_style', $('caption-output-style').value);
  fd.append('output_folder', $('batch-output-folder').value || '');
  fd.append('component_type', $('caption-component-type')?.value || '');
  fd.append('caption_mode', $('caption-mode')?.value || 'full_image');
  fd.append('detail_level', $('caption-detail-level')?.value || 'detailed');
  fd.append('post_task_action', $('batch-post-action').value || 'none');
  fd.append('dataset_caption_images', $('batch-dataset-caption-images')?.checked ? 'true' : 'false');
  fd.append('dataset_save_txt', $('batch-dataset-save-txt')?.checked ? 'true' : 'false');
  fd.append('dataset_rename_images', $('batch-dataset-rename-images')?.checked ? 'true' : 'false');
  fd.append('dataset_transfer_mode', $('batch-dataset-transfer-mode')?.value || 'copy');
  fd.append('dataset_skip_processed', $('batch-skip-existing')?.checked ? 'true' : 'false');
  fd.append('dataset_name_prefix', $('batch-dataset-prefix')?.value || 'character');
  fd.append('dataset_name_pattern', $('batch-dataset-pattern')?.value || '{prefix}_{num}');
  fd.append('dataset_number_padding', $('batch-dataset-number-padding')?.value || '4');
  fd.append('dataset_log_format', $('batch-dataset-log-format')?.value || 'csv');
  return fd;
}

async function runBatchCaption() {
  if (!requireBackendRole('text', 'batch-status', 'Connect a Text Backend first. Batch captioning uses the active text model.')) return;
  const mode = $('caption-mode')?.value || 'full_image';
  if (mode === 'custom_crop') {
    setStatus('batch-status', 'Batch captioning does not support Custom crop mode. Switch Caption mode to Full image, Face only, Person / character, Outfit, Pose, or Location.', 'warn');
    return;
  }
  const batchMode = $('batch-mode')?.value || 'dataset';
  if (batchMode === 'dataset' && !trim($('batch-output-folder')?.value || '')) {
    setStatus('batch-status', 'Dataset Preparation needs an output folder.', 'warn');
    return;
  }
  const fd = buildBatchFormData();
  setBusy('btn-run-batch', true, 'Starting...');
  setStatus('batch-status', 'Starting batch captioning...');
  resetBatchDisplay();
  stopBatchPolling();
  try {
    const data = await safeFetchJson('/api/caption-batch-start', { method:'POST', body:fd });
    currentBatchJobId = data.job_id || '';
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || 'Batch started.');
    batchPollHandle = setInterval(pollBatchStatus, 700);
    pollBatchStatus();
  } catch (e) {
    setBusy('btn-run-batch', false);
    setStatus('batch-status', e.message, 'error');
  }
}

async function cancelBatchCaption() {
  if (!currentBatchJobId) {
    setStatus('batch-status', 'No active batch job selected.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('job_id', currentBatchJobId);
  try {
    const data = await safeFetchJson('/api/caption-batch-cancel', { method:'POST', body:fd });
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || 'Cancel requested.');
  } catch (e) {
    setStatus('batch-status', e.message, 'error');
  }
}

async function resumeBatchCaption() {
  if (!requireBackendRole('text', 'batch-status', 'Connect a Text Backend first. Resume uses the active text model.')) return;
  const jobId = $('batch-session-select').value || currentBatchJobId;
  if (!jobId) {
    setStatus('batch-status', 'Choose a saved batch session first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('job_id', jobId);
  setBusy('btn-run-batch', true, 'Resuming...');
  try {
    const data = await safeFetchJson('/api/caption-batch-resume', { method:'POST', body:fd });
    currentBatchJobId = data.job_id || '';
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || 'Batch resumed.');
    stopBatchPolling();
    batchPollHandle = setInterval(pollBatchStatus, 700);
    pollBatchStatus();
  } catch (e) {
    setBusy('btn-run-batch', false);
    setStatus('batch-status', e.message, 'error');
  }
}

async function retryFailedBatchCaption() {
  if (!requireBackendRole('text', 'batch-status', 'Connect a Text Backend first. Retry uses the active text model.')) return;
  const jobId = $('batch-session-select').value || currentBatchJobId;
  if (!jobId) {
    setStatus('batch-status', 'Choose a saved batch session first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('job_id', jobId);
  setBusy('btn-run-batch', true, 'Retrying...');
  try {
    const data = await safeFetchJson('/api/caption-batch-retry-failed', { method:'POST', body:fd });
    currentBatchJobId = data.job_id || '';
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || 'Retry batch started.');
    stopBatchPolling();
    batchPollHandle = setInterval(pollBatchStatus, 700);
    pollBatchStatus();
  } catch (e) {
    setBusy('btn-run-batch', false);
    setStatus('batch-status', e.message, 'error');
  }
}

async function exportBatchLog() {
  const jobId = $('batch-session-select').value || currentBatchJobId;
  if (!jobId) {
    setStatus('batch-status', 'Choose a saved batch session first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/caption-batch-export-log?job_id=${encodeURIComponent(jobId)}`);
    const blob = new Blob([data.content || ''], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = data.filename || `neo_batch_${jobId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    setStatus('batch-status', data.message || 'Batch log exported.');
  } catch (e) {
    setStatus('batch-status', e.message, 'error');
  }
}

async function cancelBatchPostAction() {
  if (!currentBatchJobId) {
    setStatus('batch-status', 'No batch selected.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('job_id', currentBatchJobId);
  try {
    const data = await safeFetchJson('/api/caption-batch-cancel-post-action', { method:'POST', body:fd });
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || 'Post-task action cancelled.');
  } catch (e) {
    setStatus('batch-status', e.message, 'error');
  }
}

async function saveSettings() {
  const fd = new FormData();
  fd.append('library_root', $('library-root').value || '');
  try {
    const data = await safeFetchJson('/api/save-settings', { method:'POST', body:fd });
    updateStats(data.stats);
    setStatus('settings-status', 'Saved library root.');
  } catch (e) {
    setStatus('settings-status', e.message, 'error');
  }
}

// Legacy transfer helpers below are retained for compatibility with inactive transfer UI paths.
// Active library transfer lives in Admin via generation-library-* controls and generation_library_tools.js.

async function exportPresets() {
  try {
    const data = await safeFetchJson('/api/export-presets');
    const blob = new Blob([JSON.stringify(data.payload || {}, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'neo_studio_presets.json';
    a.click();
    URL.revokeObjectURL(url);
    setStatus('preset-transfer-status', 'Preset export ready.');
  } catch (e) {
    setStatus('preset-transfer-status', e.message, 'error');
  }
}

async function importPresets() {
  const file = $('import-presets-file').files[0];
  if (!file) {
    setStatus('preset-transfer-status', 'Choose a preset JSON file first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('mode', $('import-presets-mode').value || 'merge');
  try {
    const data = await safeFetchJson('/api/import-presets', { method:'POST', body:fd });
    promptPresets = data.prompt_presets || promptPresets;
    captionPresets = data.caption_presets || captionPresets;
    populatePresetSelect('prompt-preset', promptPresets, $('prompt-preset').value || initialLastPromptPreset);
    populatePresetSelect('caption-preset', captionPresets, $('caption-preset').value || initialLastCaptionPreset);
    setStatus('preset-transfer-status', data.message || 'Preset import complete.');
  } catch (e) {
    setStatus('preset-transfer-status', e.message, 'error');
  }
}


function normalizeMainSurfaceShell() {
  const shell = document.getElementById('main-surface-shell');
  if (!shell) return;
  const registry = window.NeoSurfaceRegistry;
  const orderedSectionIds = registry?.listSurfaces
    ? registry.listSurfaces().map(surface => registry.resolveSectionId ? registry.resolveSectionId(surface.id) : `tab-${surface.id}`)
    : Array.from(document.querySelectorAll('.section')).map(sec => sec.id).filter(Boolean);
  const seen = new Set();
  orderedSectionIds.forEach(sectionId => {
    if (!sectionId || seen.has(sectionId)) return;
    seen.add(sectionId);
    const sec = document.getElementById(sectionId);
    if (!sec) return;
    if (sec.parentElement !== shell) shell.appendChild(sec);
  });
}

function switchManagerSubTab(tab) {
  const target = tab || 'prompt';
  document.querySelectorAll('#tab-manager [data-manager-subtab]').forEach(btn => btn.classList.toggle('active', btn.dataset.managerSubtab === target));
  document.querySelectorAll('.sub-section').forEach(sec => sec.classList.toggle('active', sec.id === `tab-${target}`));
  document.dispatchEvent(new CustomEvent('neo-manager-lane-changed', { detail: { lane: target } }));
}

function switchMainTab(tab) {
  const target = tab || 'generate';
  const registry = window.NeoSurfaceRegistry;
  const targetSectionId = registry?.resolveSectionId ? registry.resolveSectionId(target) : `tab-${target}`;
  document.querySelectorAll('[data-main-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.mainTab === target));
  document.querySelectorAll('.section').forEach(sec => sec.classList.toggle('active', sec.id === targetSectionId));
  document.body.dataset.activeSurface = target;
  document.documentElement.dataset.activeSurface = target;
  registry?.runActivation?.(target);
}


function switchTab(tab) {
  const managerTabs = ['prompt', 'caption', 'library', 'settings'];
  if (managerTabs.includes(tab)) {
    switchMainTab('manager');
    switchManagerSubTab(tab);
    return;
  }
  if (tab === 'generate') {
    switchMainTab('generate');
    return;
  }
  switchMainTab(tab);
}

function initializeStudioAccordions() {
  document.querySelectorAll('.accordion-block[data-accordion-id]').forEach(block => {
    const accordionId = block.dataset.accordionId;
    if (!accordionId) return;
    const storageKey = `neo-studio-accordion:${accordionId}`;
    const saved = window.sessionStorage.getItem(storageKey);
    const defaultOpen = String(block.dataset.defaultOpen || '').toLowerCase() === 'true';
    block.open = saved === null ? defaultOpen : saved === 'true';
    block.addEventListener('toggle', () => {
      window.sessionStorage.setItem(storageKey, block.open ? 'true' : 'false');
    });
  });
}

function datasetExampleBaseName() {
  const renameEnabled = !!$('batch-dataset-rename-images')?.checked;
  if (!renameEnabled) return 'original_filename';
  const prefix = trim($('batch-dataset-prefix')?.value || 'character') || 'character';
  const pattern = trim($('batch-dataset-pattern')?.value || '{prefix}_{num}') || '{prefix}_{num}';
  const start = Math.max(1, Number($('batch-number-start')?.value || 1));
  const padding = Math.max(1, Number($('batch-dataset-number-padding')?.value || 4));
  const num = String(start).padStart(padding, '0');
  return pattern
    .replaceAll('{prefix}', prefix)
    .replaceAll('{num}', num)
    .replaceAll('{n}', num)
    .replaceAll('{index}', String(start));
}

function updateDatasetPreparationPreview() {
  const note = $('batch-dataset-example-note');
  if (!note) return;
  const base = datasetExampleBaseName();
  const saveTxt = !!$('batch-dataset-save-txt')?.checked && !!$('batch-dataset-caption-images')?.checked;
  note.textContent = saveTxt ? `Example output: ${base}.png + ${base}.txt` : `Example output: ${base}.png`;
}

function syncDatasetPreparationControls() {
  const captionEnabled = !!$('batch-dataset-caption-images')?.checked;
  if ($('batch-dataset-save-txt')) {
    $('batch-dataset-save-txt').disabled = !captionEnabled;
    if (!captionEnabled) $('batch-dataset-save-txt').checked = false;
  }
  const renameEnabled = !!$('batch-dataset-rename-images')?.checked;
  ['batch-dataset-prefix', 'batch-dataset-pattern', 'batch-number-start', 'batch-dataset-number-padding'].forEach(id => {
    if ($(id)) $(id).disabled = !renameEnabled;
  });
  updateDatasetPreparationPreview();
}

function toggleBatchMode() {
  const mode = $('batch-mode').value;
  $('batch-dataset-panel').classList.toggle('hidden', mode !== 'dataset');
  $('batch-library-panel').classList.toggle('hidden', mode !== 'library');
  syncDatasetPreparationControls();
}

function copyText(id, statusId) {
  const value = $(id).value || '';
  if (!value) { setStatus(statusId, 'Nothing to copy.', 'warn'); return; }
  navigator.clipboard.writeText(value).then(() => setStatus(statusId, 'Copied to clipboard.')).catch(() => setStatus(statusId, 'Copy failed.', 'error'));
}

async function browseForFolder(targetId, statusId='batch-status') {
  const fd = new FormData();
  fd.append('initial_path', $(targetId).value || '');
  try {
    const data = await safeFetchJson('/api/pick-folder', { method:'POST', body:fd });
    if (data.path) {
      $(targetId).value = data.path;
      setStatus(statusId, 'Folder selected.');
    }
  } catch (e) {
    setStatus(statusId, e.message || 'Could not open the folder picker.', 'error');
  }
}


function populateLibraryExportCategories(categories) {
  const selectIds = ['library-export-categories-select', 'generation-library-export-categories-select'];
  selectIds.forEach(id => {
    const sel = $(id);
    if (!sel) return;
    const current = new Set(Array.from(sel.selectedOptions || []).map(o => o.value));
    sel.innerHTML = '';
    (categories || []).forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      if (current.has(cat)) opt.selected = true;
      sel.appendChild(opt);
    });
  });
}

function renderLibraryImportSummary(summary) {
  const legacyBox = $('library-transfer-summary');
  const legacyList = $('library-transfer-conflicts');
  const generationBox = $('generation-library-import-summary');
  if (!legacyBox && !generationBox) return;
  if (!summary) {
    if (legacyBox) legacyBox.textContent = 'No import has been run yet.';
    if (legacyList) legacyList.innerHTML = '';
    if (generationBox) generationBox.textContent = 'No import has been run yet.';
    return;
  }
  const totals = summary.totals || {};
  const lines = [];
  Object.entries(totals).forEach(([key, value]) => {
    if (!value) return;
    lines.push(`${key.replace(/_/g, ' ')}: ${value}`);
  });
  const summaryText = lines.length ? `Mode: ${summary.mode || 'merge'} · ${lines.join(' · ')}` : `Mode: ${summary.mode || 'merge'} · Nothing changed.`;
  if (legacyBox) legacyBox.textContent = summaryText;
  if (generationBox) generationBox.textContent = summaryText;
  if (!legacyList) return;
  legacyList.innerHTML = '';
  const preview = summary.conflicts_preview || [];
  if (!preview.length) {
    const item = document.createElement('div');
    item.className = 'mini-note';
    item.textContent = 'No conflicts or renames to review.';
    legacyList.appendChild(item);
    return;
  }
  preview.forEach(row => {
    const item = document.createElement('div');
    item.className = 'search-result-card';
    const title = document.createElement('div');
    title.className = 'result-title';
    title.textContent = `${row.kind || 'item'} · ${row.name || '(unnamed)'}`;
    const meta = document.createElement('div');
    meta.className = 'result-meta';
    const bits = [`action: ${row.action || 'updated'}`];
    if (row.category) bits.push(`category: ${row.category}`);
    if (row.new_name) bits.push(`new: ${row.new_name}`);
    meta.textContent = bits.join(' · ');
    item.appendChild(title);
    item.appendChild(meta);
    legacyList.appendChild(item);
  });
}

async function exportLibraryPack() {
  const fd = new FormData();
  fd.append('include_prompts', $('library-export-prompts').checked ? 'true' : 'false');
  fd.append('include_captions', $('library-export-captions').checked ? 'true' : 'false');
  fd.append('include_characters', $('library-export-characters').checked ? 'true' : 'false');
  fd.append('include_presets', $('library-export-presets').checked ? 'true' : 'false');
  fd.append('include_categories', $('library-export-categories').checked ? 'true' : 'false');
  fd.append('include_metadata', $('library-export-metadata').checked ? 'true' : 'false');
  fd.append('include_bundles', $('library-export-bundles').checked ? 'true' : 'false');
  fd.append('full_snapshot', $('library-export-full-snapshot').checked ? 'true' : 'false');
  const selectedCategories = Array.from(($('library-export-categories-select').selectedOptions || [])).map(o => o.value);
  fd.append('selected_categories_json', JSON.stringify(selectedCategories));
  setBusy('btn-export-library', true, 'Exporting...');
  try {
    const resp = await fetch('/api/export-library', { method:'POST', body:fd });
    if (!resp.ok) {
      let data = null;
      try { data = await resp.json(); } catch (e) {}
      throw new Error(data?.message || `Request failed (${resp.status})`);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const dispo = resp.headers.get('Content-Disposition') || '';
    const match = dispo.match(/filename="?([^";]+)"?/i);
    a.href = url;
    a.download = match ? match[1] : 'neo_studio_library.zip';
    a.click();
    URL.revokeObjectURL(url);
    setStatus('library-transfer-export-status', 'Library export ready.');
  } catch (e) {
    setStatus('library-transfer-export-status', e.message, 'error');
  } finally {
    setBusy('btn-export-library', false);
  }
}

async function importLibraryPack() {
  const file = $('import-library-file').files[0];
  if (!file) {
    setStatus('library-transfer-import-status', 'Choose a library zip first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('mode', $('import-library-mode').value || 'merge');
  setBusy('btn-import-library', true, 'Importing...');
  try {
    const data = await safeFetchJson('/api/import-library', { method:'POST', body:fd });
    promptPresets = data.prompt_presets || promptPresets;
    captionPresets = data.caption_presets || captionPresets;
    populatePresetSelect('prompt-preset', promptPresets, $('prompt-preset').value || initialLastPromptPreset);
    populatePresetSelect('caption-preset', captionPresets, $('caption-preset').value || initialLastCaptionPreset);
    if (Array.isArray(data.categories)) {
      refreshCategoryList(data.categories);
      populateLibraryExportCategories(data.categories);
    }
    if (data.stats) updateStats(data.stats);
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    if (typeof refreshSavedPromptNames === 'function') refreshSavedPromptNames();
    if (typeof refreshCaptionBrowser === 'function') refreshCaptionBrowser();
    if (typeof refreshBundleRecords === 'function') refreshBundleRecords();
    renderLibraryImportSummary(data.summary || null);
    setStatus('library-transfer-import-status', data.message || 'Library import complete.');
  } catch (e) {
    setStatus('library-transfer-import-status', e.message, 'error');
  } finally {
    setBusy('btn-import-library', false);
  }
}
