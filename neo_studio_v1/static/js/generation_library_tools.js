async function inspectGenerationLoraByName(name='') {
  const rawList = Array.isArray(name) ? name : [name];
  const targetNames = rawList.map(value => trim(value || '')).filter(Boolean);
  const preferredName = targetNames[0] || '';
  if (!preferredName) return;
  const currentEntries = Array.isArray(generationLoraLibraryState.entries) ? generationLoraLibraryState.entries : [];
  const localMatch = bestMatchGenerationLoraEntry(currentEntries, targetNames);
  if (localMatch?.id) {
    if ($('generation-lora-library-select')) $('generation-lora-library-select').value = localMatch.id;
    await loadGenerationLoraLibraryRecord(localMatch.id, { silent:true });
    return;
  }
  let entries = [];
  let match = null;
  for (const candidate of targetNames) {
    entries = await refreshGenerationLoraLibraryBrowser({ keepSelection:false, preferredName, query:candidate });
    match = bestMatchGenerationLoraEntry(entries, targetNames);
    if (match?.id) break;
  }
  if (!match?.id) {
    entries = await refreshGenerationLoraLibraryBrowser({ keepSelection:false, preferredName, query:'' });
    match = bestMatchGenerationLoraEntry(entries, targetNames);
  }
  if (!match?.id) {
    setStatus('generation-lora-library-status', `No saved metadata match for ${preferredName}. Scan the folder if this LoRA is new.`, 'warn');
    return;
  }
  if ($('generation-lora-library-search')) $('generation-lora-library-search').value = preferredName;
  await loadGenerationLoraLibraryRecord(match.id, { silent:true });
}

async function scanGenerationLoraLibrary() {
  const loraDir = trim($('generation-lora-library-dir')?.value || $('neo-library-vault-lora-dir')?.value || '');
  if (!loraDir) return setStatus('generation-lora-library-status', 'Enter the LoRA folder path first.', 'warn');
  const fd = new FormData();
  fd.append('lora_dir', loraDir);
  fd.append('embed_dir', '');
  fd.append('include_ti', 'false');
  try {
    setGenerationLoraLibraryBusy(true, 'Scanning LoRA folder…', 'Reading files and metadata into the registry');
    const data = await safeFetchJson('/api/neo-library/lora-scan', { method:'POST', body:fd });
    if ($('neo-library-vault-lora-dir')) $('neo-library-vault-lora-dir').value = loraDir;
    setStatus('generation-lora-library-status', data.message || 'LoRA scan complete.', 'success');
    await refreshGenerationLoraLibraryBrowser({ keepSelection:true });
  } catch (e) {
    setStatus('generation-lora-library-status', e.message || 'Could not scan the LoRA folder.', 'error');
  } finally {
    setGenerationLoraLibraryBusy(false);
  }
}

function findBestGenerationLoraSelectValue(rec={}) {
  const options = (Array.isArray(generationCatalogState.loras) ? generationCatalogState.loras : []).map(item => ({
    value: generationSelectItemValue(item),
    label: generationSelectItemLabel(item),
  }));
  if (!options.length) return '';
  const candidates = [];
  const pushCandidate = value => {
    const raw = trim(value || '');
    if (!raw) return;
    if (!candidates.includes(raw)) candidates.push(raw);
    const base = raw.split(/[\/]/).pop();
    if (base && !candidates.includes(base)) candidates.push(base);
    const noExt = raw.replace(/\.[a-z0-9]+$/i, '');
    if (noExt && !candidates.includes(noExt)) candidates.push(noExt);
  };
  pushCandidate(rec?.file || '');
  pushCandidate(rec?.name || '');
  pushCandidate(rec?.provider_label || '');
  const normalized = value => trim(value || '').toLowerCase().replace(/\.[a-z0-9]+$/i, '');
  for (const candidate of candidates) {
    const exact = options.find(opt => normalized(opt.value) === normalized(candidate) || normalized(opt.label) === normalized(candidate));
    if (exact?.value) return exact.value;
  }
  for (const candidate of candidates) {
    const match = options.find(opt => normalized(opt.value).includes(normalized(candidate)) || normalized(opt.label).includes(normalized(candidate)));
    if (match?.value) return match.value;
  }
  return '';
}

async function addSelectedLibraryLoraToWorkflow() {
  const rec = generationLoraLibraryState.currentRecord || null;
  if (!rec) {
    setStatus('generation-lora-library-status', 'Pick a saved LoRA first, then add it into the workflow.', 'warn');
    return;
  }
  let selectedValue = findBestGenerationLoraSelectValue(rec || {});
  if (!selectedValue && typeof refreshGenerationCatalog === 'function') {
    try {
      await refreshGenerationCatalog(false);
      selectedValue = findBestGenerationLoraSelectValue(rec || {});
    } catch (_) {}
  }
  const primarySelect = $('generation-lora-name');
  if (!selectedValue) {
    const fallback = trim(rec?.file || rec?.name || '');
    if (fallback && primarySelect) {
      const existingOption = Array.from(primarySelect.options || []).find(opt => trim(opt.value || '') === fallback || trim(opt.textContent || '') === fallback);
      if (!existingOption) primarySelect.appendChild(new Option(fallback, fallback));
      selectedValue = fallback;
    }
  }
  if (!selectedValue) {
    setStatus('generation-lora-library-status', 'Could not map this library LoRA into the workflow slot list yet. Refresh the generation catalog and try again.', 'warn');
    return;
  }
  const strength = Number($('generation-lora-library-strength')?.value || rec?.default_strength || 0.8);
  const normalize = value => trim(String(value || '')).toLowerCase().replace(/\.[a-z0-9]+$/i, '').split(/[\/]/).pop();
  const selectedKey = normalize(selectedValue);
  const activeValues = Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-name')).map(el => trim(el.value || '')).filter(Boolean);
  const hasDuplicate = activeValues.some(value => normalize(value) === selectedKey);
  if (hasDuplicate) {
    setStatus('generation-lora-library-status', 'This LoRA is already added to the workflow stack.', 'warn');
    return;
  }
  addGenerationLoraRow({ name:selectedValue, strength:Number.isFinite(strength) ? strength : 0.8, enabled:true });
  scheduleGenerationDraftSave();
  inspectGenerationLoraByName([selectedValue, rec?.name || '', rec?.file || '']).catch(() => {});
  setStatus('generation-lora-library-status', `Added ${selectedValue} to the workflow LoRA stack.`, 'success');
}

async function saveGenerationLoraLibraryRecord() {
  const lid = trim(generationLoraLibraryState.currentLid || $('generation-lora-library-id')?.value || '');
  if (!lid) return setStatus('generation-lora-library-status', 'Select a saved LoRA first.', 'warn');
  const fd = new FormData();
  fd.append('lid', lid);
  fd.append('default_strength', $('generation-lora-library-strength')?.value || '0.8');
  fd.append('min_strength', $('generation-lora-library-min-strength')?.value || '0.6');
  fd.append('max_strength', $('generation-lora-library-max-strength')?.value || '1.0');
  fd.append('triggers', $('generation-lora-library-triggers')?.value || '');
  fd.append('keywords', $('generation-lora-library-keywords')?.value || '');
  fd.append('style_category', $('generation-lora-library-style-category')?.value || '');
  fd.append('base_model', $('generation-lora-library-base-model')?.value || '');
  fd.append('example_prompt', $('generation-lora-library-example')?.value || '');
  fd.append('preview_image', generationLoraLibraryState.currentRecord?.preview_image || '');
  fd.append('caution_notes', generationLoraLibraryState.currentRecord?.caution_notes || '');
  fd.append('notes', generationLoraLibraryState.currentRecord?.notes || '');
  fd.append('prompt_options_json', JSON.stringify(generationLoraLibraryState.promptOptions || []));
  fd.append('enabled', 'true');
  try {
    setGenerationLoraLibraryBusy(true, 'Saving LoRA metadata…', 'Writing your edits and prompt options');
    const data = await safeFetchJson('/api/neo-library/lora-save', { method:'POST', body:fd });
    renderGenerationLoraLibraryRecord(data.record || {}, lid);
    await refreshGenerationLoraLibraryBrowser({ keepSelection:true, query:$('generation-lora-library-search')?.value || '' });
    setStatus('generation-lora-library-status', data.message || 'LoRA metadata updated.', 'success');
  } catch (e) {
    setStatus('generation-lora-library-status', e.message || 'Could not update the LoRA metadata.', 'error');
  } finally {
    setGenerationLoraLibraryBusy(false);
  }
}

async function pullGenerationLoraLibraryFromCivitai() {
  const lid = trim(generationLoraLibraryState.currentLid || $('generation-lora-library-id')?.value || '');
  const civitaiUrl = trim($('generation-lora-library-civitai-url')?.value || '');
  if (!lid) return setStatus('generation-lora-library-status', 'Select a saved LoRA first.', 'warn');
  if (!civitaiUrl) return setStatus('generation-lora-library-status', 'Paste the CivitAI link first.', 'warn');
  const fd = new FormData();
  fd.append('lid', lid);
  fd.append('civitai_url', civitaiUrl);
  fd.append('merge_mode', 'smart_merge');
  fd.append('overwrite_fields_csv', 'triggers,keywords,base_model,example_prompt,preview_image,previews');
  try {
    setGenerationLoraLibraryBusy(true, 'Pulling from CivitAI…', 'Fetching tags, prompts, and previews');
    const data = await safeFetchJson('/api/neo-library/lora-civitai-import', { method:'POST', body:fd });
    renderGenerationLoraLibraryRecord(data.record || {}, lid);
    setGenerationLoraLibraryEditMode(true);
    setStatus('generation-lora-library-status', data.message || 'Pulled CivitAI metadata + preview data.', 'success');
  } catch (e) {
    setStatus('generation-lora-library-status', e.message || 'Could not pull data from CivitAI.', 'error');
  } finally {
    setGenerationLoraLibraryBusy(false);
  }
}

function appendGenerationLoraLibraryExample(replace=false) {
  const text = trim($('generation-lora-library-example')?.value || '');
  if (!text) return setStatus('generation-lora-library-status', 'No example prompt is loaded yet.', 'warn');
  const field = $('generation-positive');
  if (!field) return;
  if (replace) field.value = text;
  else appendTextToGenerationPromptField('generation-positive', text, ', ');
  field.dispatchEvent(new Event('input', { bubbles:true }));
  field.dispatchEvent(new Event('change', { bubbles:true }));
  renderGenerationLoraMetaChips();
  setStatus('generation-lora-library-status', replace ? 'Main prompt replaced with the example prompt.' : 'Example prompt appended to the main prompt.', 'success');
}

function openGenerationZoomModalForSrc(source='') {
  const src = trim(source || '');
  if (!src) return;
  if (typeof hydrateGenerationZoomModal === 'function') {
    hydrateGenerationZoomModal(src, { beforeUrl: '' });
    return;
  }
  const modal = $('generation-image-zoom-modal');
  const img = $('generation-image-zoom');
  if (!modal || !img) return;
  img.src = src;
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
}


function generationTiPromptTokenFromRecord(rec={}) {
  const raw = trim(rec?.name || rec?.rel || rec?.file || '');
  const stem = raw ? raw.split(/[\\/]/).pop().replace(/\.[a-z0-9]+$/i, '') : '';
  return stem ? `embedding:${stem}` : '';
}

function clearGenerationTiLibraryDetails(message='Choose a scanned TI to show its metadata here.') {
  generationTiLibraryState.currentLid = '';
  generationTiLibraryState.currentRecord = null;
  generationTiLibraryState.previewUrls = [];
  generationTiLibraryState.previewIndex = 0;
  if ($('generation-ti-library-id')) $('generation-ti-library-id').value = '';
  if ($('generation-ti-library-name')) $('generation-ti-library-name').value = '';
  if ($('generation-ti-library-token')) $('generation-ti-library-token').value = '';
  if ($('generation-ti-library-base-model')) $('generation-ti-library-base-model').value = '';
  if ($('generation-ti-library-file')) $('generation-ti-library-file').value = '';
  if ($('generation-ti-library-keywords')) $('generation-ti-library-keywords').value = '';
  if ($('generation-ti-library-example')) $('generation-ti-library-example').value = '';
  const preview = $('generation-ti-library-preview');
  const empty = $('generation-ti-library-preview-empty');
  if (preview) { preview.removeAttribute('src'); preview.classList.remove('is-ready'); }
  if (empty) empty.classList.remove('hidden');
  if ($('generation-ti-library-preview-note')) $('generation-ti-library-preview-note').textContent = message;
  updateGenerationTiPromptPresence();
}

function renderGenerationTiLibraryRecord(rec, lid='') {
  generationTiLibraryState.currentLid = lid || '';
  generationTiLibraryState.currentRecord = rec || null;
  generationTiLibraryState.previewUrls = Array.isArray(rec?.preview_urls) ? rec.preview_urls.slice() : [];
  generationTiLibraryState.previewIndex = 0;
  if ($('generation-ti-library-id')) $('generation-ti-library-id').value = lid || '';
  if ($('generation-ti-library-name')) $('generation-ti-library-name').value = rec?.name || '';
  if ($('generation-ti-library-token')) $('generation-ti-library-token').value = generationTiPromptTokenFromRecord(rec || {});
  if ($('generation-ti-library-base-model')) $('generation-ti-library-base-model').value = rec?.base_model || '';
  if ($('generation-ti-library-file')) $('generation-ti-library-file').value = rec?.file || rec?.rel || '';
  const tiNotes = [generationLoraCsv(rec?.triggers || []), generationLoraCsv(rec?.keywords || []), trim(rec?.notes || '')].filter(Boolean).join('\n');
  if ($('generation-ti-library-keywords')) $('generation-ti-library-keywords').value = tiNotes;
  if ($('generation-ti-library-example')) $('generation-ti-library-example').value = rec?.example_prompt || '';
  const preview = $('generation-ti-library-preview');
  const empty = $('generation-ti-library-preview-empty');
  const firstPreview = generationTiLibraryState.previewUrls[0] || null;
  if (preview && firstPreview?.url) { preview.src = firstPreview.url; preview.classList.add('is-ready'); }
  else if (preview) { preview.removeAttribute('src'); preview.classList.remove('is-ready'); }
  if (empty) empty.classList.toggle('hidden', !!firstPreview?.url);
  if ($('generation-ti-library-preview-note')) $('generation-ti-library-preview-note').textContent = [trim(rec?.base_model || ''), trim(rec?.provider_label || ''), trim(rec?.rel || '')].filter(Boolean).join(' · ') || 'Embedding metadata ready.';
  updateGenerationTiPromptPresence();
}

async function loadGenerationTiLibraryRecord(lid='', options={}) {
  const target = trim(lid || $('generation-ti-library-select')?.value || '');
  if (!target) { clearGenerationTiLibraryDetails(); return null; }
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-record?lid=${encodeURIComponent(target)}`, { cache:'no-store' });
    renderGenerationTiLibraryRecord(data.record || {}, target);
    if ($('generation-ti-library-select')) $('generation-ti-library-select').value = target;
    if (!options.silent) setStatus('generation-ti-library-status', 'TI metadata loaded.', 'success');
    return data.record || null;
  } catch (e) {
    setStatus('generation-ti-library-status', e.message || 'Could not load the selected TI metadata.', 'error');
    return null;
  }
}

async function refreshGenerationTiLibraryBrowser(options={}) {
  const keepSelection = options.keepSelection !== false;
  const previous = keepSelection ? trim($('generation-ti-library-select')?.value || generationTiLibraryState.currentLid || '') : '';
  const params = new URLSearchParams();
  params.set('kind', 'ti');
  params.set('query', Object.prototype.hasOwnProperty.call(options, 'query') ? String(options.query || '') : ($('generation-ti-library-search')?.value || ''));
  params.set('category', 'all');
  params.set('base_model', generationLoraCompatibilityState.baseModelFilter || 'all');
  params.set('style_category', 'all');
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-browser?${params.toString()}`, { cache:'no-store' });
    const entries = Array.isArray(data.entries) ? data.entries : [];
    generationTiLibraryState.entries = entries;
    const el = $('generation-ti-library-select');
    if (el) {
      el.innerHTML = '<option value="">Pick a scanned TI</option>';
      entries.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.id || '';
        opt.textContent = item.label || item.id || '';
        if (previous && previous === opt.value) opt.selected = true;
        el.appendChild(opt);
      });
    }
    const active = previous || trim($('generation-ti-library-select')?.value || '');
    if (active) await loadGenerationTiLibraryRecord(active, { silent:true });
    else clearGenerationTiLibraryDetails(entries.length ? 'Choose a saved TI to show its metadata here.' : 'No TI metadata matched the current search yet.');
    return entries;
  } catch (e) {
    setStatus('generation-ti-library-status', e.message || 'Could not load the TI browser.', 'error');
    return [];
  }
}

async function scanGenerationTiLibrary() {
  const embedDir = trim($('generation-ti-library-dir')?.value || '');
  if (!embedDir) return setStatus('generation-ti-library-status', 'Enter the embeddings folder path first.', 'warn');
  const fd = new FormData();
  fd.append('lora_dir', '');
  fd.append('embed_dir', embedDir);
  fd.append('include_ti', 'true');
  try {
    const data = await safeFetchJson('/api/neo-library/lora-scan', { method:'POST', body:fd });
    setStatus('generation-ti-library-status', data.message || 'TI scan complete.', 'success');
    await refreshGenerationTiLibraryBrowser({ keepSelection:true });
  } catch (e) {
    setStatus('generation-ti-library-status', e.message || 'Could not scan the embeddings folder.', 'error');
  }
}

function updateGenerationTiPromptPresence() {
  const token = trim($('generation-ti-library-token')?.value || generationTiPromptTokenFromRecord(generationTiLibraryState.currentRecord || {}));
  const inBasePositive = !!token && promptContainsGenerationToken($('generation-ti-base-positive')?.value || '', token);
  const inBaseNegative = !!token && promptContainsGenerationToken($('generation-ti-base-negative')?.value || '', token);
  const inFinishPositive = !!token && promptContainsGenerationToken($('generation-ti-finish-positive')?.value || '', token);
  const inFinishNegative = !!token && promptContainsGenerationToken($('generation-ti-finish-negative')?.value || '', token);
  const locations = [];
  if (inBasePositive) locations.push('Base +');
  if (inBaseNegative) locations.push('Base -');
  if (inFinishPositive) locations.push('Finish +');
  if (inFinishNegative) locations.push('Finish -');
  if ($('generation-ti-library-presence')) {
    $('generation-ti-library-presence').textContent = !token ? 'Detected in: Not used' : `Detected in: ${locations.length ? locations.join(' · ') : 'Not used'}`;
  }
  const positiveSent = inBasePositive || inFinishPositive;
  const negativeSent = inBaseNegative || inFinishNegative;
  $('btn-generation-ti-append-positive')?.classList.toggle('is-sent', positiveSent);
  $('btn-generation-ti-append-negative')?.classList.toggle('is-sent', negativeSent);
}

function appendGenerationTiToken(target='positive') {
  const token = trim($('generation-ti-library-token')?.value || generationTiPromptTokenFromRecord(generationTiLibraryState.currentRecord || {}));
  if (!token) {
    setStatus('generation-ti-library-status', 'Pick a TI first.', 'warn');
    return;
  }
  const helperTarget = normalizeGenerationPassTarget($('generation-ti-helper-target')?.value || 'both');
  const fieldIds = [];
  if (helperTarget !== 'finish') fieldIds.push(target === 'negative' ? 'generation-ti-base-negative' : 'generation-ti-base-positive');
  if (helperTarget !== 'base') fieldIds.push(target === 'negative' ? 'generation-ti-finish-negative' : 'generation-ti-finish-positive');
  fieldIds.forEach(id => {
    const field = $(id);
    if (!field) return;
    const current = trim(field.value || '');
    field.value = current ? `${current}, ${token}` : token;
  });
  updateGenerationTiPromptPresence();
  scheduleGenerationDraftSave();
  const targetLabel = helperTarget === 'both' ? 'base and finish passes' : helperTarget === 'base' ? 'the base pass' : 'the finish pass';
  setStatus('generation-ti-library-status', `Added ${token} to ${target === 'negative' ? 'negative' : 'positive'} TI for ${targetLabel}.`, 'success');
}


function fillGenerationKeywordManagerSelect(id, entries=[], current='', placeholder='Select keyword') {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  el.appendChild(first);
  (entries || []).forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.value ?? item.id ?? '';
    opt.textContent = item.label ?? item.name ?? item.value ?? item.id ?? '';
    if (current && current === opt.value) opt.selected = true;
    el.appendChild(opt);
  });
}

function mountGenerationKeywordManagerInline() {
  const host = $('generation-keyword-manager-inline-host');
  const modalBody = $('generation-keyword-manager-modal')?.querySelector('.modal-body');
  if (!host || !modalBody || host.dataset.managerMounted === '1') return;
  while (modalBody.firstChild) host.appendChild(modalBody.firstChild);
  host.dataset.managerMounted = '1';
}

function openGenerationKeywordManagerModal() {
  mountGenerationKeywordManagerInline();
  const inlineWrap = $('generation-keyword-manager-inline');
  if (inlineWrap) {
    inlineWrap.classList.remove('generation-workspace-hidden');
    inlineWrap.removeAttribute('aria-hidden');
    inlineWrap.open = true;
  }
  syncGenerationKeywordManagerExportOptions();
  refreshGenerationKeywordManagerBrowser(true).catch(() => {});
  inlineWrap?.scrollIntoView({ block:'nearest', behavior:'smooth' });
}

function closeGenerationKeywordManagerModal() {
  const inlineWrap = $('generation-keyword-manager-inline');
  if (inlineWrap) inlineWrap.open = false;
  const modal = $('generation-keyword-manager-modal');
  if (modal) modal.classList.add('hidden');
  if ($('backend-manager-modal')?.classList.contains('hidden') !== false && $('generation-image-zoom-modal')?.classList.contains('hidden') !== false && $('generation-mask-editor-modal')?.classList.contains('hidden') !== false) {
    document.body.classList.remove('modal-open');
  }
}

function clearGenerationKeywordManagerForm(message='Ready to add a new keyword.') {
  if ($('generation-keyword-modal-id')) $('generation-keyword-modal-id').value = '';
  if ($('generation-keyword-modal-category')) $('generation-keyword-modal-category').value = '';
  if ($('generation-keyword-modal-subcategory')) $('generation-keyword-modal-subcategory').value = '';
  if ($('generation-keyword-modal-name')) $('generation-keyword-modal-name').value = '';
  if ($('generation-keyword-modal-aliases')) $('generation-keyword-modal-aliases').value = '';
  if ($('generation-keyword-modal-desc')) $('generation-keyword-modal-desc').value = '';
  if ($('generation-keyword-modal-enabled')) $('generation-keyword-modal-enabled').checked = true;
  setStatus('generation-keyword-modal-status', message);
}

async function refreshGenerationKeywordManagerBrowser(keepSelection=true) {
  const prev = keepSelection ? trim($('generation-keyword-modal-select')?.value || '') : '';
  const params = new URLSearchParams();
  params.set('category', $('generation-keyword-modal-filter-cat')?.value || 'all');
  params.set('subcategory', $('generation-keyword-modal-filter-sub')?.value || 'all');
  params.set('query', trim($('generation-keyword-modal-search')?.value || ''));
  try {
    const data = await safeFetchJson(`/api/neo-library/keyword-browser?${params.toString()}`);
    fillGenerationKeywordManagerSelect('generation-keyword-modal-filter-cat', (data.categories || []).map(v => ({ value:v, label:v })), data.selected_category || 'all', 'Filter category');
    fillGenerationKeywordManagerSelect('generation-keyword-modal-filter-sub', (data.subcategories || []).map(v => ({ value:v, label:v })), data.selected_subcategory || 'all', 'Filter subcategory');
    fillGenerationKeywordManagerSelect('generation-keyword-modal-select', (data.entries || []).map(v => ({ value:v.id || '', label:v.label || v.id || '' })), prev || '', 'Saved keywords');
    setStatus('generation-keyword-modal-status', (data.entries || []).length ? `${data.entries.length} keyword(s) found.` : 'No keywords match the current filters.', (data.entries || []).length ? '' : 'warn');
    return data;
  } catch (e) {
    setStatus('generation-keyword-modal-status', e.message || 'Could not load keywords.', 'error');
    return null;
  }
}

async function loadGenerationKeywordManagerRecord() {
  const tid = trim($('generation-keyword-modal-select')?.value || '');
  if (!tid) { clearGenerationKeywordManagerForm('Pick a saved keyword or create a new one.'); return; }
  try {
    const data = await safeFetchJson(`/api/neo-library/keyword-record?tid=${encodeURIComponent(tid)}`);
    const rec = data.record || {};
    if ($('generation-keyword-modal-id')) $('generation-keyword-modal-id').value = rec.id || tid;
    if ($('generation-keyword-modal-category')) $('generation-keyword-modal-category').value = rec.category || '';
    if ($('generation-keyword-modal-subcategory')) $('generation-keyword-modal-subcategory').value = rec.subcategory || '';
    if ($('generation-keyword-modal-name')) $('generation-keyword-modal-name').value = rec.name || '';
    if ($('generation-keyword-modal-aliases')) $('generation-keyword-modal-aliases').value = Array.isArray(rec.aliases) ? rec.aliases.join(', ') : (rec.aliases || '');
    if ($('generation-keyword-modal-desc')) $('generation-keyword-modal-desc').value = rec.desc || '';
    if ($('generation-keyword-modal-enabled')) $('generation-keyword-modal-enabled').checked = rec.enabled !== false;
    setStatus('generation-keyword-modal-status', 'Keyword loaded.', 'success');
  } catch (e) {
    setStatus('generation-keyword-modal-status', e.message || 'Could not load the selected keyword.', 'error');
  }
}

async function saveGenerationKeywordManagerRecord() {
  const fd = new FormData();
  fd.append('tid', $('generation-keyword-modal-id')?.value || '');
  fd.append('category', $('generation-keyword-modal-category')?.value || '');
  fd.append('subcategory', $('generation-keyword-modal-subcategory')?.value || 'general');
  fd.append('name', $('generation-keyword-modal-name')?.value || '');
  fd.append('aliases', $('generation-keyword-modal-aliases')?.value || '');
  fd.append('desc', $('generation-keyword-modal-desc')?.value || '');
  fd.append('enabled', $('generation-keyword-modal-enabled')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/keyword-save', { method:'POST', body:fd });
    await refreshGenerationKeywordManagerBrowser(true);
    if ($('generation-keyword-modal-select')) $('generation-keyword-modal-select').value = data.tid || '';
    await loadGenerationKeywordManagerRecord();
    if (typeof refreshNeoLibraryKeywordInsert === 'function') refreshNeoLibraryKeywordInsert(true);
    if (typeof refreshNeoLibraryVaultKeywords === 'function') refreshNeoLibraryVaultKeywords(true);
    if (typeof refreshNeoLibraryVaultSummary === 'function') refreshNeoLibraryVaultSummary();
    setStatus('generation-keyword-modal-status', data.message || 'Keyword saved.', 'success');
  } catch (e) {
    setStatus('generation-keyword-modal-status', e.message || 'Could not save keyword.', 'error');
  }
}

async function deleteGenerationKeywordManagerRecord() {
  const tid = trim($('generation-keyword-modal-id')?.value || $('generation-keyword-modal-select')?.value || '');
  if (!tid) { setStatus('generation-keyword-modal-status', 'Pick a saved keyword first.', 'warn'); return; }
  const fd = new FormData();
  fd.append('tid', tid);
  try {
    const data = await safeFetchJson('/api/neo-library/keyword-delete', { method:'POST', body:fd });
    clearGenerationKeywordManagerForm('Keyword deleted.');
    await refreshGenerationKeywordManagerBrowser(false);
    if (typeof refreshNeoLibraryKeywordInsert === 'function') refreshNeoLibraryKeywordInsert(true);
    if (typeof refreshNeoLibraryVaultKeywords === 'function') refreshNeoLibraryVaultKeywords(true);
    if (typeof refreshNeoLibraryVaultSummary === 'function') refreshNeoLibraryVaultSummary();
    setStatus('generation-keyword-modal-status', data.message || 'Keyword deleted.', 'success');
  } catch (e) {
    setStatus('generation-keyword-modal-status', e.message || 'Could not delete keyword.', 'error');
  }
}

function syncGenerationKeywordManagerExportOptions() {
  const src = $('library-export-categories-select');
  const dst = $('generation-library-export-categories-select');
  if (src && dst) {
    dst.innerHTML = '';
    Array.from(src.options || []).forEach(opt => {
      const clone = document.createElement('option');
      clone.value = opt.value;
      clone.textContent = opt.textContent;
      clone.selected = opt.selected;
      dst.appendChild(clone);
    });
  }
}

async function exportGenerationLibraryPack() {
  const fd = new FormData();
  fd.append('include_prompts', $('generation-library-export-prompts')?.checked ? 'true' : 'false');
  fd.append('include_captions', $('generation-library-export-captions')?.checked ? 'true' : 'false');
  fd.append('include_characters', $('generation-library-export-characters')?.checked ? 'true' : 'false');
  fd.append('include_presets', $('generation-library-export-presets')?.checked ? 'true' : 'false');
  fd.append('include_categories', $('generation-library-export-categories')?.checked ? 'true' : 'false');
  fd.append('include_metadata', $('generation-library-export-metadata')?.checked ? 'true' : 'false');
  fd.append('include_bundles', $('generation-library-export-bundles')?.checked ? 'true' : 'false');
  fd.append('full_snapshot', $('generation-library-export-full-snapshot')?.checked ? 'true' : 'false');
  const selectedCategories = Array.from(($('generation-library-export-categories-select')?.selectedOptions || [])).map(o => o.value);
  fd.append('selected_categories_json', JSON.stringify(selectedCategories));
  setBusy('btn-generation-library-export', true, 'Exporting...');
  try {
    const resp = await fetch('/api/export-library', { method:'POST', body:fd });
    if (!resp.ok) {
      let data = null;
      try { data = await resp.json(); } catch (_) {}
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
    setStatus('generation-library-export-status', 'Library export ready.');
  } catch (e) {
    setStatus('generation-library-export-status', e.message || 'Could not export library.', 'error');
  } finally {
    setBusy('btn-generation-library-export', false);
  }
}

async function importGenerationLibraryPack() {
  const file = $('generation-library-import-file')?.files?.[0];
  if (!file) { setStatus('generation-library-import-status', 'Choose a library zip first.', 'warn'); return; }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('mode', $('generation-library-import-mode')?.value || 'merge');
  setBusy('btn-generation-library-import', true, 'Importing...');
  try {
    const data = await safeFetchJson('/api/import-library', { method:'POST', body:fd });
    if (typeof refreshCategoryList === 'function' && Array.isArray(data.categories)) refreshCategoryList(data.categories);
    if (typeof populateLibraryExportCategories === 'function' && Array.isArray(data.categories)) populateLibraryExportCategories(data.categories);
    if (typeof updateStats === 'function' && data.stats) updateStats(data.stats);
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    if (typeof refreshSavedPromptNames === 'function') refreshSavedPromptNames();
    if (typeof refreshCaptionBrowser === 'function') refreshCaptionBrowser();
    if (typeof refreshBundleRecords === 'function') refreshBundleRecords();
    if (typeof refreshNeoLibraryKeywordInsert === 'function') refreshNeoLibraryKeywordInsert(true);
    if (typeof refreshNeoLibraryVaultKeywords === 'function') refreshNeoLibraryVaultKeywords(true);
    if (typeof refreshNeoLibraryVaultSummary === 'function') refreshNeoLibraryVaultSummary();
    syncGenerationKeywordManagerExportOptions();
    setStatus('generation-library-import-status', data.message || 'Library import complete.');
    if (typeof renderLibraryImportSummary === 'function') renderLibraryImportSummary(data.summary || null);
  } catch (e) {
    setStatus('generation-library-import-status', e.message || 'Could not import library.', 'error');
  } finally {
    setBusy('btn-generation-library-import', false);
  }
}

/* Phase 5 split: ControlNet / IP-Adapter / Detailer helpers moved to generation_reference_finish_tools.js. */

function getGenerationWildcardRoot() {
  return trim($('generation-wildcard-root')?.value || '');
}

function generationWildcardTargetFieldId() {
  return ($('generation-wildcard-target')?.value || 'positive') === 'negative' ? 'generation-negative' : 'generation-positive';
}

function normalizeGenerationWildcardCount(rawValue, fallback=3) {
  const numeric = Math.floor(Number(rawValue));
  return Number.isFinite(numeric) && numeric >= 1 ? numeric : Math.max(1, Math.floor(Number(fallback) || 1));
}

function generationWildcardLargeCountMessage(count, mode='preview') {
  if (!(count >= 20)) return '';
  return mode === 'queue'
    ? `You are about to queue ${count} wildcard variants as separate jobs. This can take a while and flood the queue.`
    : `Previewing ${count} wildcard variants can get noisy and may feel a bit heavy.`;
}

function populateGenerationWildcardSelect(keepValue=true) {
  const select = $('generation-wildcard-file');
  if (!select) return;
  const current = keepValue ? String(select.value || '') : '';
  select.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = generationWildcardCatalog.length ? 'Select a wildcard file…' : 'No wildcard files found';
  select.appendChild(placeholder);
  generationWildcardCatalog.forEach(entry => {
    const opt = document.createElement('option');
    opt.value = entry.token || '';
    opt.textContent = `${entry.label || `__${entry.token || ''}__`}${entry.count ? ` (${entry.count})` : ''}`;
    if (current && current === opt.value) opt.selected = true;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
}

async function loadGenerationWildcardCatalog(keepValue=true) {
  const root = getGenerationWildcardRoot();
  try {
    const qs = new URLSearchParams();
    if (root) qs.set('root', root);
    const data = await safeFetchJson(`/api/generation/wildcards?${qs.toString()}&_=${Date.now()}`, { cache:'no-store' });
    generationWildcardCatalog = Array.isArray(data?.entries) ? data.entries : [];
    if ($('generation-wildcard-root') && data?.root) $('generation-wildcard-root').value = data.root;
    populateGenerationWildcardSelect(keepValue);
    const selected = trim($('generation-wildcard-file')?.value || '');
    if (selected) await previewSelectedGenerationWildcardFile();
    setStatus('generation-wildcard-status', generationWildcardCatalog.length ? `${generationWildcardCatalog.length} wildcard file(s) loaded.` : 'No wildcard files found yet.', generationWildcardCatalog.length ? '' : 'warn');
  } catch (e) {
    setStatus('generation-wildcard-status', e.message || 'Could not load wildcard files.', 'error');
  }
}

async function loadGenerationWildcardValues(token, { force=false } = {}) {
  const cleanToken = trim(token || '');
  if (!cleanToken) return [];
  if (!force && generationWildcardValueCache.has(cleanToken)) return generationWildcardValueCache.get(cleanToken) || [];
  const qs = new URLSearchParams();
  if (getGenerationWildcardRoot()) qs.set('root', getGenerationWildcardRoot());
  qs.set('token', cleanToken);
  const data = await safeFetchJson(`/api/generation/wildcard-values?${qs.toString()}&_=${Date.now()}`, { cache:'no-store' });
  const values = Array.isArray(data?.values) ? data.values.map(v => String(v || '')).filter(Boolean) : [];
  generationWildcardValueCache.set(cleanToken, values);
  return values;
}

async function previewSelectedGenerationWildcardFile() {
  const token = trim($('generation-wildcard-file')?.value || '');
  if (!token) {
    if ($('generation-wildcard-file-preview')) $('generation-wildcard-file-preview').value = '';
    return;
  }
  try {
    const values = await loadGenerationWildcardValues(token);
    if ($('generation-wildcard-file-preview')) $('generation-wildcard-file-preview').value = values.join('\n');
    setStatus('generation-wildcard-status', values.length ? `Loaded ${values.length} value(s) for __${token}__.` : `__${token}__ is empty.`, values.length ? '' : 'warn');
  } catch (e) {
    setStatus('generation-wildcard-status', e.message || 'Could not read wildcard file.', 'error');
  }
}

function parseGenerationWildcardTokens(text) {
  const found = new Set();
  String(text || '').replace(/__([A-Za-z0-9_\-\/]+)__/g, (_m, token) => {
    const clean = String(token || '').trim().replace(/^\/+|\/+$/g, '');
    if (clean) found.add(clean);
    return _m;
  });
  return Array.from(found);
}

async function ensureGenerationWildcardValuesForText(text) {
  const tokens = parseGenerationWildcardTokens(text);
  for (const token of tokens) {
    try {
      await loadGenerationWildcardValues(token);
    } catch (_) {}
  }
}

function generationWildcardSeedNumber(seedLike) {
  const raw = String(seedLike ?? '').trim();
  const numeric = Number(raw);
  if (Number.isFinite(numeric) && numeric >= 0) return numeric >>> 0;
  let hash = 2166136261;
  const source = raw || String(Date.now());
  for (let i = 0; i < source.length; i += 1) {
    hash ^= source.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function generationWildcardRng(seed) {
  let t = (Number(seed) || 0) >>> 0;
  return () => {
    t += 0x6D2B79F5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function resolveInlineChoicesOnce(text, rng) {
  let out = String(text || '');
  for (let i = 0; i < 24; i += 1) {
    let replaced = false;
    out = out.replace(/\{([^{}]+)\}/g, (match, inner) => {
      const options = String(inner || '').split('|').map(part => part.trim()).filter(Boolean);
      if (!options.length) return match;
      replaced = true;
      const pick = options[Math.floor(rng() * options.length)] || options[0];
      return pick;
    });
    if (!replaced) break;
  }
  return out;
}

function resolveFileWildcardsOnce(text, rng) {
  return String(text || '').replace(/__([A-Za-z0-9_\-\/]+)__/g, (match, token) => {
    const clean = String(token || '').trim().replace(/^\/+|\/+$/g, '');
    const values = generationWildcardValueCache.get(clean) || [];
    if (!values.length) return match;
    return values[Math.floor(rng() * values.length)] || values[0] || match;
  });
}

function resolveGenerationWildcardText(text, { seed=0, variantOffset=0 } = {}) {
  const rng = generationWildcardRng((generationWildcardSeedNumber(seed) + Number(variantOffset || 0)) >>> 0);
  let out = String(text || '');
  for (let i = 0; i < 24; i += 1) {
    const next = resolveInlineChoicesOnce(resolveFileWildcardsOnce(out, rng), rng);
    if (next === out) break;
    out = next;
  }
  return out;
}

async function previewGenerationWildcardResolution() {
  const fieldId = generationWildcardTargetFieldId();
  const source = $(fieldId)?.value || '';
  if (!trim(source)) {
    setStatus('generation-wildcard-status', 'Add some wildcard syntax to the selected prompt first.', 'warn');
    return;
  }
  await ensureGenerationWildcardValuesForText(source);
  const count = normalizeGenerationWildcardCount($('generation-wildcard-preview-count')?.value || 3, 3);
  const seedBase = $('generation-wildcard-use-seed')?.checked ? ($('generation-seed')?.value || '-1') : Date.now();
  generationWildcardPreviewResults = [];
  for (let i = 0; i < count; i += 1) {
    generationWildcardPreviewResults.push(resolveGenerationWildcardText(source, { seed: seedBase, variantOffset: i }));
  }
  if ($('generation-wildcard-resolved-preview')) $('generation-wildcard-resolved-preview').value = generationWildcardPreviewResults.map((item, idx) => `#${idx + 1}\n${item}`).join('\n\n');
  const countWarning = generationWildcardLargeCountMessage(count, 'preview');
  setStatus('generation-wildcard-status', countWarning ? `${countWarning} Previewed ${generationWildcardPreviewResults.length} wildcard variation(s).` : `Previewed ${generationWildcardPreviewResults.length} wildcard variation(s).`, countWarning ? 'warn' : 'success');
}

function applyFirstGenerationWildcardResult() {
  const first = String(generationWildcardPreviewResults[0] || '').trim();
  if (!first) {
    setStatus('generation-wildcard-status', 'Preview some wildcard results first.', 'warn');
    return;
  }
  const fieldId = generationWildcardTargetFieldId();
  if ($(fieldId)) {
    $(fieldId).value = first;
    $(fieldId).dispatchEvent(new Event('input', { bubbles:true }));
    $(fieldId).dispatchEvent(new Event('change', { bubbles:true }));
  }
  setStatus('generation-wildcard-status', 'Applied the first resolved wildcard result.', 'success');
  scheduleGenerationDraftSave();
}

function insertSelectedGenerationWildcardToken() {
  const token = trim($('generation-wildcard-file')?.value || '');
  if (!token) {
    setStatus('generation-wildcard-status', 'Pick a wildcard file first.', 'warn');
    return;
  }
  appendTextToGenerationPromptField(generationWildcardTargetFieldId(), `__${token}__`, ', ');
  setStatus('generation-wildcard-status', `Inserted __${token}__.`, 'success');
}

async function applyGenerationWildcardResolution(payload, options={}) {
  if (!payload || typeof payload !== 'object') return payload;
  const wildcardsEnabled = isGenerationWildcardsEnabled();
  const autoResolve = wildcardsEnabled && !!$('generation-wildcard-auto-resolve')?.checked;
  const variantOffset = Number(options?.variantOffset || 0) || 0;
  payload.wildcard_enabled = wildcardsEnabled;
  payload.wildcard_root = getGenerationWildcardRoot();
  payload.wildcard_auto_resolve = autoResolve;
  payload.wildcard_use_seed = wildcardsEnabled && !!$('generation-wildcard-use-seed')?.checked;
  payload.wildcard_variant_offset = variantOffset;
  payload.wildcard_source_positive = payload.positive || '';
  payload.wildcard_source_negative = payload.negative || '';
  if (!wildcardsEnabled || !autoResolve) return payload;
  await ensureGenerationWildcardValuesForText(payload.positive || '');
  await ensureGenerationWildcardValuesForText(payload.negative || '');
  const seedBase = payload.wildcard_use_seed ? payload.seed : Date.now();
  payload.positive = resolveGenerationWildcardText(payload.positive || '', { seed: seedBase, variantOffset: variantOffset * 2 });
  payload.negative = resolveGenerationWildcardText(payload.negative || '', { seed: seedBase, variantOffset: (variantOffset * 2) + 1 });
  payload.wildcard_last_resolved_positive = payload.positive || '';
  payload.wildcard_last_resolved_negative = payload.negative || '';
  if ($('generation-wildcard-resolved-preview')) $('generation-wildcard-resolved-preview').value = [payload.positive, payload.negative ? `Negative\n${payload.negative}` : ''].filter(Boolean).join('\n\n');
  return payload;
}

async function queueGenerationWildcardVariants() {
  if (!isGenerationWildcardsEnabled()) {
    setStatus('generation-wildcard-status', 'Enable Wildcards first if you want them to affect generation.', 'warn');
    return;
  }
  const count = normalizeGenerationWildcardCount($('generation-wildcard-queue-count')?.value || 3, 3);
  const largeWarning = generationWildcardLargeCountMessage(count, 'queue');
  if (largeWarning && !window.confirm(`${largeWarning}\n\nContinue?`)) return;
  if (!$('generation-wildcard-auto-resolve')?.checked) {
    const ok = window.confirm('Auto-resolve on queue is off. Queueing variants like this will keep reusing the same prompt text unless you resolve manually. Continue anyway?');
    if (!ok) return;
  }
  const queueBtn = $('btn-generation-wildcard-queue-variants');
  const prevText = queueBtn?.textContent || 'Queue Variants';
  if (queueBtn) {
    queueBtn.setAttribute('disabled', 'disabled');
    queueBtn.textContent = 'Queueing…';
  }
  const jobs = [];
  try {
    announceGenerationStatus(`Queueing ${count} wildcard variant${count === 1 ? '' : 's'}…`);
    for (let i = 0; i < count; i += 1) {
      const job = await queueGenerationShell({ watch:false, wildcardVariantOffset:i, suppressInitialStatus:true, suppressSuccessStatus:true });
      if (!job) throw new Error(`Stopped while queueing variant ${i + 1}.`);
      jobs.push(job);
      setStatus('generation-wildcard-status', `Queued wildcard variant ${i + 1} / ${count}.`, i + 1 === count ? 'success' : '');
    }
    announceGenerationStatus(`Queued ${jobs.length} wildcard variant${jobs.length === 1 ? '' : 's'} as separate jobs.`, 'success');
  } catch (e) {
    announceGenerationStatus(e.message || 'Could not queue wildcard variants.', 'error');
  } finally {
    if (queueBtn) {
      queueBtn.removeAttribute('disabled');
      queueBtn.textContent = prevText;
    }
  }
}


function getGenerationDetailerSharedDefaults() {
  return {
    provider: $('generation-detailer-provider')?.value || 'ultralytics',
    sam_model: trim($('generation-detailer-sam-model')?.value || ''),
    custom_classes: trim($('generation-detailer-custom-classes')?.value || ''),
    confidence: Number($('generation-detailer-confidence')?.value || 0.35),
    top_k: Number($('generation-detailer-topk')?.value || 0),
    bbox_grow: Number($('generation-detailer-bbox-grow')?.value || 12),
    mask_blur: Number($('generation-detailer-mask-blur')?.value || 4),
    denoise: Number($('generation-detailer-denoise')?.value || 0.12),
    steps: Number($('generation-detailer-steps')?.value || 12),
    use_main_prompt: !!$('generation-detailer-use-main-prompt')?.checked,
    force_inpaint: !!$('generation-detailer-force-inpaint')?.checked,
  };
}

function collectGenerationDetailerPasses() {
  const passes = [];
  const shared = getGenerationDetailerSharedDefaults();
  if ($('generation-detailer-enabled')?.checked) {
    passes.push({
      uid: 'primary',
      enabled: true,
      provider: shared.provider,
      mode: $('generation-detailer-mode')?.value || 'face',
      detector_type: $('generation-detailer-detector-type')?.value || 'bbox',
      detector_model: trim($('generation-detailer-model')?.value || ''),
      sam_model: shared.sam_model,
      custom_classes: trim($('generation-detailer-custom-classes')?.value || ''),
      confidence: shared.confidence,
      top_k: shared.top_k,
      bbox_grow: shared.bbox_grow,
      mask_blur: shared.mask_blur,
      denoise: shared.denoise,
      steps: shared.steps,
      use_main_prompt: shared.use_main_prompt,
      force_inpaint: shared.force_inpaint,
      order_mode: $('generation-detailer-order')?.value || 'auto',
      start_index: Number($('generation-detailer-start-index')?.value || 1),
      count: Number($('generation-detailer-count')?.value || 1),
      min_area: Number($('generation-detailer-min-area')?.value || 0),
      max_area: Number($('generation-detailer-max-area')?.value || 0),
      reference_lock: $('generation-detailer-reference-lock')?.value || 'none',
      target_mode: $('generation-detailer-target-mode')?.value || 'auto_detect',
      manual_boxes: $('generation-detailer-manual-boxes')?.value || '',
      positive: $('generation-detailer-positive')?.value || '',
      negative: $('generation-detailer-negative')?.value || '',
    });
  }
  document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row').forEach(row => {
    passes.push({
      uid: row.dataset.uid || '',
      enabled: isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled')),
      provider: shared.provider,
      mode: row.querySelector('.generation-detailer-mode')?.value || 'face',
      detector_type: row.querySelector('.generation-detailer-detector-type')?.value || 'bbox',
      detector_model: trim(row.querySelector('.generation-detailer-model')?.value || ''),
      sam_model: shared.sam_model,
      custom_classes: trim($('generation-detailer-custom-classes')?.value || ''),
      confidence: shared.confidence,
      top_k: shared.top_k,
      bbox_grow: shared.bbox_grow,
      mask_blur: shared.mask_blur,
      denoise: shared.denoise,
      steps: shared.steps,
      use_main_prompt: shared.use_main_prompt && !trim(row.querySelector('.generation-detailer-positive')?.value || '') && !trim(row.querySelector('.generation-detailer-negative')?.value || ''),
      force_inpaint: shared.force_inpaint,
      order_mode: row.querySelector('.generation-detailer-order')?.value || 'auto',
      start_index: Number(row.querySelector('.generation-detailer-start-index')?.value || 1),
      count: Number(row.querySelector('.generation-detailer-count')?.value || 1),
      min_area: Number(row.querySelector('.generation-detailer-min-area')?.value || 0),
      max_area: Number(row.querySelector('.generation-detailer-max-area')?.value || 0),
      reference_lock: row.querySelector('.generation-detailer-reference-lock')?.value || 'none',
      target_mode: row.querySelector('.generation-detailer-target-mode')?.value || 'auto_detect',
      manual_boxes: row.querySelector('.generation-detailer-manual-boxes')?.value || '',
      positive: row.querySelector('.generation-detailer-positive')?.value || '',
      negative: row.querySelector('.generation-detailer-negative')?.value || '',
    });
  });
  return passes;
}

async function downloadGenerationDetailerSamPreset() {
  const modelKey = trim($('generation-detailer-sam-preset')?.value || '');
  if (!modelKey) {
    setStatus('generation-detailer-status', 'Pick a SAM preset first.', 'warn');
    return;
  }
  const btn = $('btn-generation-detailer-download-sam');
  const previousLabel = btn?.textContent || 'Download SAM';
  if (btn) {
    btn.setAttribute('disabled', 'disabled');
    btn.textContent = 'Downloading…';
  }
  try {
    const data = await safeFetchJson('/api/generation/detailer-download-sam', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_key: modelKey,
        detector_root: $('generation-detailer-custom-detector-root')?.value || '',
        sam_root: $('generation-detailer-custom-sam-root')?.value || '',
      }),
    });
    generationDetailerModelCatalog = {
      ...generationDetailerModelCatalog,
      bbox_models: Array.isArray(data?.bbox_models) ? data.bbox_models : generationDetailerModelCatalog.bbox_models,
      segm_models: Array.isArray(data?.segm_models) ? data.segm_models : generationDetailerModelCatalog.segm_models,
      sam_models: Array.isArray(data?.sam_models) ? data.sam_models : generationDetailerModelCatalog.sam_models,
      sam_presets: Array.isArray(data?.sam_presets) ? data.sam_presets : generationDetailerModelCatalog.sam_presets,
      custom_detector_root: data?.custom_detector_root || $('generation-detailer-custom-detector-root')?.value || '',
      custom_sam_root: data?.custom_sam_root || $('generation-detailer-custom-sam-root')?.value || '',
      comfy_root: data?.comfy_root || generationDetailerModelCatalog.comfy_root,
      bbox_dir: data?.bbox_dir || generationDetailerModelCatalog.bbox_dir,
      segm_dir: data?.segm_dir || generationDetailerModelCatalog.segm_dir,
      sam_dir: data?.sam_dir || generationDetailerModelCatalog.sam_dir,
    };
    populateGenerationDetailerSamSelect(true);
    if ($('generation-detailer-sam-model') && data?.download?.filename) $('generation-detailer-sam-model').value = data.download.filename;
    document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row').forEach(row => populateGenerationDetailerRowModelSelect(row, true));
    updateGenerationDetailerMeta();
    window.dispatchEvent(new CustomEvent('neo:generation-detailer-models-refreshed', { detail: { detailer: generationDetailerModelCatalog, found: true } }));
    setStatus('generation-detailer-status', data?.message || 'SAM model downloaded.', 'success');
    scheduleGenerationDraftSave();
  } catch (e) {
    setStatus('generation-detailer-status', e.message || 'Could not download the SAM model.', 'error');
  } finally {
    if (btn) {
      btn.removeAttribute('disabled');
      btn.textContent = previousLabel;
    }
  }
}


// Phase 10.3.3: Region Prompt Strength bridge.
// Forge/A1111 prompt attention is parsed from `(text:weight)`.
// Scene Director stores region.strength already; this helper makes the value actually affect
// the prompt sent to the Scene Director JSON without forcing users to hand-wrap every region.
function neoClampRegionPromptStrength(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  // Keep the UI expressive, but avoid extreme attention values that can melt faces/composition.
  return Math.max(0, Math.min(2, Math.round(n * 100) / 100));
}

function neoFormatStrengthValue(value) {
  const n = neoClampRegionPromptStrength(value);
  return Number.isInteger(n) ? String(n) : String(n).replace(/0+$/, '').replace(/\.$/, '');
}

function neoApplyRegionPromptStrength(prompt, strength) {
  const text = String(prompt || '').trim();
  if (!text) return '';
  const safeStrength = neoClampRegionPromptStrength(strength);
  if (!Number.isFinite(safeStrength) || Math.abs(safeStrength - 1) < 0.001 || safeStrength <= 0) return text;
  const value = neoFormatStrengthValue(safeStrength);
  // If the whole region prompt is already manually weighted, replace the outer weight instead
  // of creating ugly nested wrappers like `((prompt:1.8):2)`.
  const weightedWhole = text.match(/^\(([\s\S]*):\s*([0-9]*\.?[0-9]+)\)$/);
  if (weightedWhole && weightedWhole[1] && !weightedWhole[1].includes('\n\n')) {
    return `(${weightedWhole[1].trim()}:${value})`;
  }
  return `(${text}:${value})`;
}


// Phase 10.2: strip removed Image Tab feature state from newly queued payloads.
// Keep this narrow: do not touch surviving owner systems such as IP-Adapter,
// ControlNet, Inpaint/Mask, ADetailer, Upscale Lab, SUPIR, Wildcards, or styles.


// Phase 10.3.14: final Scene Director DOM rescue at generation-payload boundary.
// This is intentionally placed in generation_library_tools.js because this file
// owns the payload that reaches the backend. If the extension's in-memory region
// array is stale/empty after preset removal, but the user can visibly see region
// boxes/cards, collect the live DOM state here instead of sending zero regions.
function collectSceneDirectorLiveDomStateForGeneration(existingState = {}) {
  const state = (existingState && typeof existingState === 'object') ? existingState : {};
  const enabled = !!document.getElementById('neo-scene-director-enabled')?.checked || !!state.enabled;
  const layer = document.getElementById('neo-scene-director-region-layer');
  const frame = document.getElementById('neo-scene-director-canvas-frame');
  const boxes = layer ? Array.from(layer.querySelectorAll('.neo-scene-director-region-box[data-region-id]')) : [];
  const cards = Array.from(document.querySelectorAll('#neo-scene-director-regions-host .neo-scene-director-region-card[data-region-id]'));
  const ids = [];
  const addId = (id) => { const value = String(id || '').trim(); if (value && !ids.includes(value)) ids.push(value); };
  boxes.forEach(box => addId(box.dataset.regionId));
  cards.forEach(card => addId(card.dataset.regionId));

  const cssEscape = (value) => {
    try { return CSS && CSS.escape ? CSS.escape(String(value || '')) : String(value || '').replace(/"/g, '\\"'); }
    catch (_) { return String(value || '').replace(/"/g, '\\"'); }
  };
  const readValue = (selector, fallback = '') => {
    const node = document.querySelector(selector);
    return node ? String(node.value ?? fallback) : fallback;
  };
  const readChecked = (selector, fallback = true) => {
    const node = document.querySelector(selector);
    return node ? !!node.checked : fallback;
  };
  const parsePct = (value, fallback) => {
    const text = String(value || '').trim();
    if (text.endsWith('%')) {
      const n = Number(text.slice(0, -1));
      return Number.isFinite(n) ? n / 100 : fallback;
    }
    const n = Number(text);
    return Number.isFinite(n) ? n : fallback;
  };
  const normalizeRect = (rect = {}) => {
    let x = Number(rect.x ?? 0);
    let y = Number(rect.y ?? 0);
    let w = Number(rect.w ?? 0.3);
    let h = Number(rect.h ?? 0.7);
    if (!Number.isFinite(x)) x = 0;
    if (!Number.isFinite(y)) y = 0;
    if (!Number.isFinite(w) || w <= 0) w = 0.3;
    if (!Number.isFinite(h) || h <= 0) h = 0.7;
    w = Math.max(0.01, Math.min(1, w));
    h = Math.max(0.01, Math.min(1, h));
    x = Math.max(0, Math.min(1 - w, x));
    y = Math.max(0, Math.min(1 - h, y));
    return { x, y, w, h };
  };
  const readRectFromBox = (box, fallbackIndex = 0) => {
    if (!box) return normalizeRect({ x: Math.min(0.7, fallbackIndex * 0.22), y: 0.1, w: 0.3, h: 0.7 });
    const style = box.style || {};
    const styled = {
      x: parsePct(style.left, NaN),
      y: parsePct(style.top, NaN),
      w: parsePct(style.width, NaN),
      h: parsePct(style.height, NaN),
    };
    if ([styled.x, styled.y, styled.w, styled.h].every(Number.isFinite)) return normalizeRect(styled);
    try {
      const fb = frame?.getBoundingClientRect?.();
      const bb = box.getBoundingClientRect?.();
      if (fb && bb && fb.width > 0 && fb.height > 0) {
        return normalizeRect({ x: (bb.left - fb.left) / fb.width, y: (bb.top - fb.top) / fb.height, w: bb.width / fb.width, h: bb.height / fb.height });
      }
    } catch (_) {}
    return normalizeRect({ x: Math.min(0.7, fallbackIndex * 0.22), y: 0.1, w: 0.3, h: 0.7 });
  };

  const existingById = new Map();
  if (Array.isArray(state.regions)) {
    state.regions.forEach((region) => { if (region && region.id) existingById.set(String(region.id), region); });
  }

  const regions = ids.map((id, index) => {
    const escaped = cssEscape(id);
    const old = existingById.get(id) || {};
    const box = boxes.find(item => item.dataset.regionId === id);
    const label = readValue(`[data-region-label="${escaped}"]`, old.label || `Region ${index + 1}`);
    const type = readValue(`[data-region-type="${escaped}"]`, old.type || 'character') || 'character';
    const prompt = readValue(`[data-region-prompt="${escaped}"]`, old.prompt || '');
    const negative = readValue(`[data-region-negative="${escaped}"]`, old.negative_prompt || '');
    const strength = Number(readValue(`[data-region-strength="${escaped}"]`, old.strength ?? '1')) || 1;
    const profileId = readValue(`[data-region-profile="${escaped}"]`, old.identity_profile_id || '');
    return {
      ...old,
      id,
      label,
      type,
      enabled: readChecked(`[data-region-enabled="${escaped}"]`, old.enabled !== false),
      visible: old.visible === false ? false : true,
      locked: old.locked === true,
      prompt,
      negative_prompt: negative,
      strength,
      rect: readRectFromBox(box, index),
      identity_profile_id: profileId,
      identity_profile_name: old.identity_profile_name || profileId || '',
      ipadapter: readChecked(`[data-region-ipadapter="${escaped}"]`, !!old.ipadapter),
      ipadapter_slot: Number(readValue(`[data-region-ip-slot="${escaped}"]`, old.ipadapter_slot ?? (index + 1))) || (index + 1),
      ipadapter_weight: Number(readValue(`[data-region-ip-weight="${escaped}"]`, old.ipadapter_weight ?? '0.52')) || 0.52,
      ipadapter_weight_mode: readValue(`[data-region-ip-weight-mode="${escaped}"]`, old.ipadapter_weight_mode || 'slot_default') || 'slot_default',
      ipadapter_use_region_mask: readChecked(`[data-region-ip-mask="${escaped}"]`, old.ipadapter_use_region_mask !== false),
    };
  });

  if (!regions.length) return { ...state, enabled };
  const active = regions.filter(region => region.enabled !== false && region.visible !== false);
  return {
    ...state,
    enabled,
    regions,
    active_region_count: active.length,
    state_source: 'generation_payload_dom_rescue',
    coordinate_source: 'generation_payload_dom_rescue',
  };
}

function sanitizeGenerationPayload(payload) {
  const source = (payload && typeof payload === 'object') ? payload : {};
  const cleaned = JSON.parse(JSON.stringify(source));
  const removedPrefixes = [
    'regional_',
    'regionalPrompt',
    'expression_editor_',
    'expressionEditor',
    'expression_sample_',
    'reference_match_',
    'referenceMatch',
    'cleanup_prep_',
    'cleanupPrep',
  ];
  const removedExactKeys = new Set([
    'expression_editor_pass',
    'expression_editor_enabled',
    'expression_pass',
    'expression_enabled',
    'reference_match_enabled',
    'cleanup_prep_enabled',
  ]);
  Object.keys(cleaned).forEach(key => {
    const normalized = String(key || '');
    if (removedExactKeys.has(normalized) || removedPrefixes.some(prefix => normalized.startsWith(prefix))) {
      delete cleaned[key];
    }
  });
  // Explicit compatibility sentinel only. Backend should never see active regional data.
  cleaned.regional_prompt_enabled = false;
  cleaned.regional_prompt_regions = [];
  cleaned._neo_payload_sanitized = true;
  cleaned._neo_payload_sanitizer_version = 'phase10.2';
  return cleaned;
}

function clampGenerationNumber(value, fallback, min=null, max=null) {
  const n = Number(value);
  let out = Number.isFinite(n) ? n : fallback;
  if (min !== null && Number.isFinite(min)) out = Math.max(min, out);
  if (max !== null && Number.isFinite(max)) out = Math.min(max, out);
  return out;
}

function normalizeGenerationLanPaintPromptMode(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[_-]+/g, ' ');
  if (raw === 'prompt first' || raw === 'prompt') return 'Prompt First';
  return 'Image First';
}

function getGenerationLanPaintDefaults() {
  return {
    enabled: false,
    num_steps: 5,
    prompt_mode: 'Image First',
    lambda: 6.0,
    step_size: 0.25,
    beta: 1.0,
    friction: 12.0,
    early_stop: 2,
    info: 'Configured from Neo Studio LanPaint settings panel.',
  };
}

function collectGenerationLanPaintSettings(workflowMode=null, inpaintBackend=null) {
  const mode = String(workflowMode || $('generation-workflow-type')?.value || 'txt2img').trim().toLowerCase();
  const backend = String(inpaintBackend || $('generation-inpaint-backend')?.value || 'standard').trim().toLowerCase();
  const defaults = getGenerationLanPaintDefaults();
  const active = mode === 'inpaint' && backend === 'lanpaint';
  return {
    enabled: active,
    num_steps: Math.round(clampGenerationNumber($('generation-lanpaint-num-steps')?.value, defaults.num_steps, 1, 20)),
    prompt_mode: normalizeGenerationLanPaintPromptMode($('generation-lanpaint-prompt-mode')?.value || defaults.prompt_mode),
    lambda: clampGenerationNumber($('generation-lanpaint-lambda')?.value, defaults.lambda, 0, 50),
    step_size: clampGenerationNumber($('generation-lanpaint-step-size')?.value, defaults.step_size, 0, 10),
    beta: clampGenerationNumber($('generation-lanpaint-beta')?.value, defaults.beta, 0, 50),
    friction: clampGenerationNumber($('generation-lanpaint-friction')?.value, defaults.friction, 0, 100),
    early_stop: Math.round(clampGenerationNumber($('generation-lanpaint-early-stop')?.value, defaults.early_stop, 0, 20)),
    info: defaults.info,
  };
}

function buildGenerationPayload() {
  const stylePayload = composeGenerationStylePayload();
  const loras = [];
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const name = trim(row.querySelector('.generation-lora-name')?.value || '');
    const strength = Number(row.querySelector('.generation-lora-strength')?.value || 0.8);
    const target = normalizeGenerationPassTarget(row.querySelector('.generation-lora-target')?.value || 'both');
    const apply_to = (typeof normalizeGenerationLoraApplyTo === 'function') ? normalizeGenerationLoraApplyTo(row.querySelector('.generation-lora-apply-to')?.value || 'global') : 'global';
    if (enabled && name) loras.push({ uid: row.dataset.uid || '', name, strength, target, apply_to, enabled:true });
  });

  const controlnetUnits = [];
  const primaryControlEnabled = isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled'));
  const primaryControlName = trim($('generation-controlnet-name')?.value || '');
  const primaryControlUnit = trim($('generation-controlnet-unit')?.value || 'auto') || 'auto';
  const primaryControlPreprocessor = trim($('generation-controlnet-preprocessor')?.value || 'none') || 'none';
  const primaryControlStrength = Number($('generation-controlnet-strength')?.value || 1.0);
  if (primaryControlEnabled && primaryControlName) {
    controlnetUnits.push({
      uid:'primary',
      unit: primaryControlUnit,
      model: primaryControlName,
      preprocessor: primaryControlPreprocessor,
      strength: primaryControlStrength,
      image_field: 'control_image__primary',
      enabled:true,
    });
  }
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const model = trim(row.querySelector('.generation-controlnet-name')?.value || '');
    const unit = trim(row.querySelector('.generation-controlnet-unit')?.value || 'auto') || 'auto';
    const preprocessor = trim(row.querySelector('.generation-controlnet-preprocessor')?.value || 'none') || 'none';
    const strength = Number(row.querySelector('.generation-controlnet-strength')?.value || 1.0);
    if (enabled && model) {
      const uid = row.dataset.uid || '';
      controlnetUnits.push({ uid, unit, model, preprocessor, strength, image_field: `control_image__${uid}`, enabled:true });
    }
  });

  const detailerPasses = collectGenerationDetailerPasses();

  const ipadapterUnits = [];
  const primaryIpAdapterEnabled = isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled'));
  const primaryIpAdapterMode = trim($('generation-ipadapter-mode')?.value || 'standard') || 'standard';
  const primaryIpAdapterName = trim($('generation-ipadapter-name')?.value || '');
  const primaryIpAdapterClipVision = trim($('generation-ipadapter-clip-vision')?.value || '');
  const primaryIpAdapterFacePreset = trim($('generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2') || 'FACEID PLUS V2';
  const primaryIpAdapterFaceProvider = trim($('generation-ipadapter-faceid-provider')?.value || 'CUDA') || 'CUDA';
  const globalFaceIdLoraStrength = Number($('generation-identity-faceid-lora')?.value || $('generation-ipadapter-faceid-lora-strength')?.value || 0.75);
  const primaryIpAdapterFaceLoraStrength = globalFaceIdLoraStrength;
  const primaryIpAdapterWeight = Number($('generation-ipadapter-weight')?.value || 1.0);
  const primaryIpAdapterWeightFaceId = Number($('generation-ipadapter-weight-faceidv2')?.value || 1.0);
  const primaryIpAdapterWeightType = trim($('generation-ipadapter-weight-type')?.value || 'linear') || 'linear';
  const primaryIpAdapterCombineEmbeds = trim($('generation-ipadapter-combine-embeds')?.value || 'concat') || 'concat';
  const primaryIpAdapterEmbedsScaling = trim($('generation-ipadapter-embeds-scaling')?.value || 'V only') || 'V only';
  const primaryIpAdapterStartAt = Number($('generation-ipadapter-start-at')?.value || 0.0);
  const primaryIpAdapterEndAt = Number($('generation-ipadapter-end-at')?.value || 1.0);
  const primaryIpAdapterImageCount = getGenerationIpAdapterRefCount($('generation-ipadapter-image'));
  if (primaryIpAdapterEnabled && primaryIpAdapterClipVision && (primaryIpAdapterMode === 'faceid' || primaryIpAdapterName)) {
    ipadapterUnits.push({
      uid:'primary',
      mode: primaryIpAdapterMode,
      model: primaryIpAdapterName,
      clip_vision: primaryIpAdapterClipVision,
      faceid_preset: primaryIpAdapterFacePreset,
      faceid_provider: primaryIpAdapterFaceProvider,
      faceid_lora_strength: primaryIpAdapterFaceLoraStrength,
      weight: primaryIpAdapterWeight,
      weight_faceidv2: primaryIpAdapterWeightFaceId,
      weight_type: primaryIpAdapterWeightType,
      combine_embeds: primaryIpAdapterCombineEmbeds,
      embeds_scaling: primaryIpAdapterEmbedsScaling,
      start_at: primaryIpAdapterStartAt,
      end_at: primaryIpAdapterEndAt,
      image_field: 'ipadapter_image__primary',
      image_count: primaryIpAdapterImageCount,
      enabled:true,
    });
  }
  document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const mode = trim(row.querySelector('.generation-ipadapter-mode')?.value || 'standard') || 'standard';
    const model = trim(row.querySelector('.generation-ipadapter-name')?.value || '');
    const clipVision = trim(row.querySelector('.generation-ipadapter-clip-vision')?.value || '');
    const facePreset = trim(row.querySelector('.generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2') || 'FACEID PLUS V2';
    const faceProvider = trim(row.querySelector('.generation-ipadapter-faceid-provider')?.value || 'CUDA') || 'CUDA';
    const faceLoraStrength = globalFaceIdLoraStrength;
    const weight = Number(row.querySelector('.generation-ipadapter-weight')?.value || 1.0);
    const weightFaceId = Number(row.querySelector('.generation-ipadapter-weight-faceidv2')?.value || 1.0);
    const weightType = trim(row.querySelector('.generation-ipadapter-weight-type')?.value || 'linear') || 'linear';
    const combineEmbeds = trim(row.querySelector('.generation-ipadapter-combine-embeds')?.value || 'concat') || 'concat';
    const embedsScaling = trim(row.querySelector('.generation-ipadapter-embeds-scaling')?.value || 'V only') || 'V only';
    const startAt = Number(row.querySelector('.generation-ipadapter-start-at')?.value || 0.0);
    const endAt = Number(row.querySelector('.generation-ipadapter-end-at')?.value || 1.0);
    const imageCount = getGenerationIpAdapterRefCount(row.querySelector('.generation-ipadapter-image'));
    if (enabled && clipVision && (mode === 'faceid' || model)) {
      const uid = row.dataset.uid || '';
      ipadapterUnits.push({ uid, mode, model, clip_vision: clipVision, faceid_preset: facePreset, faceid_provider: faceProvider, faceid_lora_strength: faceLoraStrength, weight, weight_faceidv2: weightFaceId, weight_type: weightType, combine_embeds: combineEmbeds, embeds_scaling: embedsScaling, start_at: startAt, end_at: endAt, image_field: `ipadapter_image__${uid}`, image_count: imageCount, enabled:true });
    }
  });

  const qwenSourceImageFields = [];
  ['generation-source-image-2', 'generation-source-image-3'].forEach((id, index) => {
    const file = $(id)?.files?.[0] || null;
    if (file) qwenSourceImageFields.push(`source_image__${index + 2}`);
  });

  const activeButtonFamily = String(document.querySelector('[data-generation-family].active')?.getAttribute('data-generation-family') || '').trim();
  const routerFamily = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '').trim();
  const hiddenFamily = String($('generation-family')?.value || '').trim();
  const family = activeButtonFamily || routerFamily || hiddenFamily || 'sdxl_sd';
  if ($('generation-family') && $('generation-family').value !== family) $('generation-family').value = family;
  const familyForcesGguf = family === 'flux' || family === 'qwen_image_edit';
  const requestedModelSource = ($('generation-model-source')?.value || 'checkpoint');
  const resolvedModelSource = familyForcesGguf ? 'gguf' : (requestedModelSource === 'gguf' ? 'checkpoint' : requestedModelSource);

  const workflowMode = $('generation-workflow-type')?.value || 'txt2img';
  const selectedInpaintBackend = workflowMode === 'inpaint' ? ($('generation-inpaint-backend')?.value || 'standard') : 'standard';
  const lanpaintSettings = collectGenerationLanPaintSettings(workflowMode, selectedInpaintBackend);
  const payload = {
    workflow_type: workflowMode,
    mode: workflowMode,
    family,
    model_source: resolvedModelSource,
    checkpoint: trim($('generation-checkpoint')?.value || ''),
    gguf_unet: trim($('generation-gguf-unet')?.value || ''),
    gguf_clip_mode: $('generation-gguf-clip-mode')?.value || 'dual',
    gguf_clip_type: family === 'qwen_image_edit' ? 'qwen_image' : (family === 'flux' ? 'flux' : ($('generation-gguf-clip-type')?.value || 'flux')),
    gguf_clip_primary: trim($('generation-gguf-clip-primary')?.value || ''),
    gguf_clip_secondary: trim($('generation-gguf-clip-secondary')?.value || ''),
    gguf_guidance: Number($('generation-gguf-guidance')?.value || 3.5),
    vae: trim($('generation-vae')?.value || ''),
    sampler: $('generation-sampler')?.value || 'euler',
    scheduler: $('generation-scheduler')?.value || 'normal',
    width: Number($('generation-width')?.value || 1024),
    height: Number($('generation-height')?.value || 1024),
    steps: Number($('generation-steps')?.value || 28),
    batch_size: Number($('generation-batch-size')?.value || 1),
    cfg: Number($('generation-cfg')?.value || 5.2),
    dynamic_thresholding: (typeof readGenerationDynamicThresholding === 'function') ? readGenerationDynamicThresholding() : { enabled:false, preset:'off' },
    denoise: Number($('generation-denoise')?.value || 1.0),
    source_image_fields: qwenSourceImageFields,
    seed: trim($('generation-seed')?.value || '-1'),
    positive: $('generation-positive')?.value || '',
    negative: $('generation-negative')?.value || '',
    prompt_conditioning_mode: $('generation-prompt-conditioning-mode')?.value || 'raw',
    clip_skip: Number($('generation-clip-skip')?.value || 1),
    experimental_mode: $('generation-experimental-mode')?.value || 'off',
    advanced_slot_a: $('generation-advanced-slot-a')?.value || 'none',
    advanced_slot_b: $('generation-advanced-slot-b')?.value || 'none',
    style_enabled: isGenerationStyleAddonsEnabled(),
    style_pass_target: stylePayload.target,
    style_positive: stylePayload.base_positive,
    style_negative: stylePayload.base_negative,
    refine_style_positive: stylePayload.refine_positive,
    refine_style_negative: stylePayload.refine_negative,
    ti_base_positive: trim($('generation-ti-base-positive')?.value || ''),
    ti_base_negative: trim($('generation-ti-base-negative')?.value || ''),
    ti_finish_positive: trim($('generation-ti-finish-positive')?.value || ''),
    ti_finish_negative: trim($('generation-ti-finish-negative')?.value || ''),
    ti_helper_target: normalizeGenerationPassTarget($('generation-ti-helper-target')?.value || 'both'),
    lora_name: loras[0]?.name || '',
    lora_strength: Number(loras[0]?.strength || 0.8),
    loras,
    detailer: detailerPasses[0] || {
      enabled: !!$('generation-detailer-enabled')?.checked,
      ...getGenerationDetailerSharedDefaults(),
      mode: $('generation-detailer-mode')?.value || 'face',
      detector_type: $('generation-detailer-detector-type')?.value || 'bbox',
      detector_model: trim($('generation-detailer-model')?.value || ''),
      order_mode: $('generation-detailer-order')?.value || 'auto',
      start_index: Number($('generation-detailer-start-index')?.value || 1),
      count: Number($('generation-detailer-count')?.value || 1),
      min_area: Number($('generation-detailer-min-area')?.value || 0),
      max_area: Number($('generation-detailer-max-area')?.value || 0),
      reference_lock: $('generation-detailer-reference-lock')?.value || 'none',
      target_mode: $('generation-detailer-target-mode')?.value || 'auto_detect',
      manual_boxes: $('generation-detailer-manual-boxes')?.value || '',
      positive: $('generation-detailer-positive')?.value || '',
      negative: $('generation-detailer-negative')?.value || '',
    },
    detailer_passes: detailerPasses,
    detailer_custom_detector_root: trim($('generation-detailer-custom-detector-root')?.value || ''),
    detailer_custom_sam_root: trim($('generation-detailer-custom-sam-root')?.value || ''),
    detailer_sam_preset: trim($('generation-detailer-sam-preset')?.value || ''),
    controlnet_name: primaryControlEnabled ? primaryControlName : '',
    controlnet_preprocessor: primaryControlPreprocessor,
    controlnet_strength: primaryControlStrength,
    controlnet_units: controlnetUnits,
    ipadapter_mode: primaryIpAdapterMode,
    ipadapter_name: primaryIpAdapterEnabled ? primaryIpAdapterName : '',
    ipadapter_clip_vision: primaryIpAdapterClipVision,
    ipadapter_faceid_preset: primaryIpAdapterFacePreset,
    ipadapter_faceid_provider: primaryIpAdapterFaceProvider,
    ipadapter_faceid_lora_strength: primaryIpAdapterFaceLoraStrength,
    ipadapter_weight: primaryIpAdapterWeight,
    ipadapter_weight_faceidv2: primaryIpAdapterWeightFaceId,
    ipadapter_weight_type: primaryIpAdapterWeightType,
    ipadapter_combine_embeds: primaryIpAdapterCombineEmbeds,
    ipadapter_embeds_scaling: primaryIpAdapterEmbedsScaling,
    ipadapter_start_at: primaryIpAdapterStartAt,
    ipadapter_end_at: primaryIpAdapterEndAt,
    ipadapter_units: ipadapterUnits,
    ...collectGenerationRegionalPromptSettings(),
    refine_enabled: String($('generation-refine-enabled')?.value || 'false') === 'true',
    refine_strategy: $('generation-refine-strategy')?.value || 'standard',
    refine_mode: $('generation-refine-mode')?.value || 'latent',
    refine_resize_method: $('generation-refine-resize-method')?.value || 'lanczos',
    refine_upscaler: trim($('generation-refine-upscaler')?.value || ''),
    refine_scale: Number($('generation-refine-scale')?.value || 1.5),
    refine_steps: Number($('generation-refine-steps')?.value || Math.max(12, Math.round(Number($('generation-steps')?.value || 28) * 0.45))),
    refine_denoise: Number($('generation-refine-denoise')?.value || 0.12),
    refine_cfg: Number($('generation-refine-cfg')?.value || $('generation-cfg')?.value || 5.2),
    refine_sampler: trim($('generation-refine-sampler')?.value || ''),
    refine_scheduler: trim($('generation-refine-scheduler')?.value || ''),
    refine_tiled_vae: String($('generation-refine-tiled-vae')?.value || 'true') === 'true',
    refine_tile_size: Number($('generation-refine-tile-size')?.value || 512),
    refine_tile_overlap: Number($('generation-refine-tile-overlap')?.value || 64),
    supir_enabled: String($('generation-supir-enabled')?.value || 'false') === 'true',
    supir_model: trim($('generation-supir-model')?.value || ''),
    supir_sdxl_model: trim($('generation-supir-sdxl-model')?.value || ''),
    supir_scale: Number($('generation-supir-scale')?.value || 1.5),
    supir_steps: Number($('generation-supir-steps')?.value || 45),
    supir_restoration_scale: Number($('generation-supir-restoration-scale')?.value || -1),
    supir_cfg_scale: Number($('generation-supir-cfg-scale')?.value || 4.0),
    supir_control_scale: Number($('generation-supir-control-scale')?.value || 1.0),
    supir_color_fix_type: $('generation-supir-color-fix-type')?.value || 'Wavelet',
    supir_tiled_vae: String($('generation-supir-tiled-vae')?.value || 'true') === 'true',
    supir_encoder_tile_size: Number($('generation-supir-encoder-tile-size')?.value || 512),
    supir_decoder_tile_size: Number($('generation-supir-decoder-tile-size')?.value || 64),
    supir_a_prompt: $('generation-supir-a-prompt')?.value || 'high quality, detailed',
    supir_n_prompt: $('generation-supir-n-prompt')?.value || 'bad quality, blurry, messy',
    output_root: trim($('generation-output-root')?.value || ''),
    output_category: trim($('generation-output-category')?.value || 'Uncategorized') || 'Uncategorized',
    wildcard_enabled: isGenerationWildcardsEnabled(),
    output_filename_padding: 4,
    source_resize_mode: $('generation-source-resize-mode')?.value || 'native',
    inpaint_target: $('generation-inpaint-target')?.value || 'masked',
    inpaint_context: $('generation-inpaint-context')?.value || 'full_image',
    inpaint_backend: selectedInpaintBackend,
    lanpaint: lanpaintSettings,
    lanpaint_enabled: lanpaintSettings.enabled,
    lanpaint_num_steps: lanpaintSettings.num_steps,
    lanpaint_prompt_mode: lanpaintSettings.prompt_mode,
    lanpaint_lambda: lanpaintSettings.lambda,
    lanpaint_step_size: lanpaintSettings.step_size,
    lanpaint_beta: lanpaintSettings.beta,
    lanpaint_friction: lanpaintSettings.friction,
    lanpaint_early_stop: lanpaintSettings.early_stop,
    lanpaint_info: lanpaintSettings.info,
    composition_guide_type: $('generation-composition-guide-type')?.value || 'none',
    composition_source_mode: $('generation-composition-source-mode')?.value || 'source_image',
    grow_mask_by: Number($('generation-grow-mask-by')?.value || 6),
    outpaint_left: Number($('generation-outpaint-left')?.value || 0),
    outpaint_top: Number($('generation-outpaint-top')?.value || 0),
    outpaint_right: Number($('generation-outpaint-right')?.value || 0),
    outpaint_bottom: Number($('generation-outpaint-bottom')?.value || 0),
    outpaint_feather: Number($('generation-outpaint-feather')?.value || 24),
    notes: $('generation-workflow-notes')?.value || '',
  };
  try {
    if (window.NeoSceneDirectorExtension && (typeof window.NeoSceneDirectorExtension.getGenerationPayload === 'function' || typeof window.NeoSceneDirectorExtension.getState === 'function')) {
      const rawSceneState = typeof window.NeoSceneDirectorExtension.getGenerationPayload === 'function'
        ? window.NeoSceneDirectorExtension.getGenerationPayload('generation_payload_collect')
        : window.NeoSceneDirectorExtension.getState();
      const sceneState = collectSceneDirectorLiveDomStateForGeneration(rawSceneState);
      payload.scene_director_state = sceneState;
      payload.scene_director_enabled = !!sceneState.enabled;
      // Phase 10.3 hotfix: build generation-time Scene Director data from the LIVE canvas regions,
      // not from whichever layout preset button was last clicked.
      const sceneRegions = Array.isArray(sceneState.regions) ? sceneState.regions : [];
      const activeSceneRegions = sceneRegions.filter((region) => region && region.enabled !== false && region.visible !== false);
      payload._neo_scene_director_frontend_region_count = sceneRegions.length;
      payload._neo_scene_director_frontend_active_region_count = activeSceneRegions.length;
      payload._neo_scene_director_frontend_state_source = sceneState.state_source || sceneState.coordinate_source || 'live_generation_payload';
      if (payload.scene_director_enabled) {
        payload.scene_director_backend_mode = 'v052_node';
        // Phase 3: Scene Director regional txt2img is batch-compatible.
        // Keep the user-selected batch size intact here; backend guards should only
        // clamp explicit unsafe tools such as detailer, preview actions, FaceID, or unsupported modes.
        payload._neo_scene_director_batch_policy = 'preserve_txt2img_batch';
        const identityUnits = sceneState.scene_director_identity_units || sceneState.identity_profile_units || [];
        const isObjectRegion = (region) => String(region?.type || 'character').toLowerCase() === 'object';
        const characterRegions = activeSceneRegions.filter(region => !isObjectRegion(region));
        const objectRegions = activeSceneRegions.filter(region => isObjectRegion(region));
        payload.scene_director_v052_max_subject_slots = characterRegions.length || 1;
        payload.scene_director_v052_global_prompt_override = payload.positive || '';
        payload.scene_director_regional_units = activeSceneRegions.map((region, index) => {
          const rect = region.rect || {};
          const characterIndex = characterRegions.findIndex(item => item && item.id === region.id) + 1;
          const identityUnit = identityUnits.find((unit) => unit && (unit.region_id === region.id || (characterIndex > 0 && Number(unit.region_index || 0) === characterIndex)));
          const identityHint = identityUnit ? [identityUnit.trigger_words, identityUnit.profile_name].filter(Boolean).join(', ') : '';
          const rawRegionPrompt = [region.prompt || '', identityHint].filter(Boolean).join(', ');
          const regionPrompt = neoApplyRegionPromptStrength(rawRegionPrompt, region.strength);
          return {
            index: index + 1,
            id: region.id || `region_${index + 1}`,
            label: region.label || `Region ${index + 1}`,
            type: region.type || 'character',
            prompt: regionPrompt,
            negative_prompt: region.negative_prompt || '',
            strength: Number(region.strength ?? 1) || 1,
            x: Number(rect.x ?? 0),
            y: Number(rect.y ?? 0),
            w: Number(rect.w ?? 0.3),
            h: Number(rect.h ?? 0.7),
            falloff: Number(region.falloff ?? 0) || 0,
            enabled: region.enabled !== false,
            composer_mode: 'scene_director',
          };
        });
        const sceneJson = {
          version: '0.5.2-neo-ui-live-regions',
          enabled: true,
          mode: characterRegions.length >= 3 ? 'count_locked' : 'relation_focused',
          canvas: { width: Number(payload.width || 1024), height: Number(payload.height || 1024) },
          camera: { framing: 'scene director live canvas', angle: 'eye level', lens: '50mm' },
          global_style: payload.positive || '',
          subjects: characterRegions.map((region, index) => {
            const rect = region.rect || {};
            const x = Number(rect.x ?? 0), y = Number(rect.y ?? 0), w = Number(rect.w ?? 0.3), h = Number(rect.h ?? 0.7);
            const identityUnit = identityUnits.find((unit) => unit && (unit.region_id === region.id || Number(unit.region_index || 0) === index + 1));
            const identityHint = identityUnit ? [identityUnit.trigger_words, identityUnit.profile_name].filter(Boolean).join(', ') : '';
            return {
              id: region.id || `person_${index + 1}`,
              prompt: neoApplyRegionPromptStrength([region.prompt || '', identityHint, region.label || `Person ${index + 1}`].filter(Boolean).join(', '), region.strength),
              bbox: [x, y, Math.min(1, x + w), Math.min(1, y + h)],
              pose_type: region.pose || 'guided by region prompt',
              facing: 'camera',
              required: region.enabled !== false,
              identity: identityUnit ? {
                profile_id: identityUnit.profile_id || '',
                profile_name: identityUnit.profile_name || '',
                mode: identityUnit.mode || 'faceid',
                reference_images: identityUnit.reference_images || identityUnit.image_names || [],
                weight: identityUnit.weight ?? 0.45,
                start_at: identityUnit.start_at ?? 0,
                end_at: identityUnit.end_at ?? 0.65,
              } : {},
            };
          }),
          objects: objectRegions.map((region, index) => {
            const rect = region.rect || {};
            const x = Number(rect.x ?? 0), y = Number(rect.y ?? 0), w = Number(rect.w ?? 0.2), h = Number(rect.h ?? 0.2);
            return {
              id: region.id || `object_${index + 1}`,
              prompt: neoApplyRegionPromptStrength([region.prompt || region.label || `Object ${index + 1}`, 'keep this object inside its assigned box'].filter(Boolean).join(', '), region.strength),
              bbox: [x, y, Math.min(1, x + w), Math.min(1, y + h)],
              bound_to: region.bound_to || region.owner || '',
              relation: region.relation || '',
              required: region.enabled !== false,
            };
          }),
          relations: [],
          negative: payload.negative || '',
        };
        payload.scene_director_v052_scene_json = JSON.stringify(sceneJson);
      }
      payload.scene_director_identity_units = sceneState.scene_director_identity_units || sceneState.identity_profile_units || [];
      // Phase 10.3.12 rescue guard: keep Identity Profile metadata in
      // scene_director_identity_units only. Do not mirror it into
      // scene_director_ipadapter_units on the browser side; the server is the
      // source of truth for future safe/staged FaceID routing.
    }
  } catch (error) {
    payload._neo_scene_director_frontend_sync_error = error && error.message ? error.message : 'Scene Director frontend sync failed.';
  }
  return sanitizeGenerationPayload(payload);
}

function refreshGenerationCounters() {
  updateCounter('generation-positive', 'generation-positive-counter');
  updateCounter('generation-negative', 'generation-negative-counter');
}

