let neoLibraryPromptPage = 1;
let neoLibraryPromptTotalPages = 1;
let neoLibraryPromptRefreshHandle = null;
let neoLibraryLoadedPromptId = '';
let neoLibraryCaptionSyncHandle = null;
let neoLibraryOutputPage = 1;
let neoLibraryOutputTotalPages = 1;
let neoLibraryCurrentOutputRecord = null;
let neoLibraryCurrentOutputMode = '';
let neoLibraryCurrentOutputName = '';
let neoLibraryOutputParsed = null;
let neoLibraryComposerLibraryRefreshHandle = null;
let neoLibraryComposerCharacterItems = [];
let neoLibraryComposerCharacterState = { chr1:'', chr2:'', chr3:'', chr4:'' };
let neoLibraryComposerPresetSelectedId = '';
let neoLibraryVaultKeywordRefreshHandle = null;
let neoLibraryVaultMapsetRefreshHandle = null;

function neoLibrarySetSummary(summary) {
  if (!summary) return;
  if ($('neo-library-root-card')) $('neo-library-root-card').textContent = summary.library_root || summary.root || '';
  if ($('neo-library-prompt-count')) $('neo-library-prompt-count').textContent = summary.prompt_count ?? '0';
  if ($('neo-library-caption-count')) $('neo-library-caption-count').textContent = summary.caption_count ?? '0';
  updateStats(summary);
}

function renderStorageCompat(snapshot) {
  const grid = $('library-storage-compat-grid');
  const details = $('library-storage-compat-details');
  if (grid) {
    grid.innerHTML = '';
    (snapshot.cards || []).forEach(card => {
      const el = document.createElement('div');
      el.className = 'card-lite storage-compat-card';
      const existsClass = card.exists ? 'good' : 'warn';
      const writeClass = card.writable ? 'good' : 'warn';
      el.innerHTML = `
        <div class="row-between">
          <h3 style="margin:0;">${escapeHtml(card.label || '')}</h3>
          ${card.shared ? '<span class="badge">Shared path</span>' : ''}
        </div>
        <div class="mini-note">${escapeHtml(card.purpose || '')}</div>
        <div class="storage-compat-path">${escapeHtml(card.path || '')}</div>
        <div class="storage-compat-flags">
          <span class="storage-compat-flag ${existsClass}">${card.exists ? 'Exists' : 'Missing'}</span>
          <span class="storage-compat-flag ${writeClass}">${card.writable ? 'Writable' : 'Read only / unavailable'}</span>
        </div>
      `;
      grid.appendChild(el);
    });
  }
  if (details) {
    const lines = [];
    lines.push(snapshot.policy || '');
    lines.push('');
    const counts = snapshot.counts || {};
    lines.push(`Prompt records: ${counts.prompt_records ?? 0}`);
    lines.push(`Caption records: ${counts.caption_records ?? 0}`);
    lines.push(`Bundle records: ${counts.bundle_records ?? 0}`);
    lines.push(`Composer libraries: ${counts.composer_libraries ?? 0}`);
    lines.push(`Characters: ${counts.characters ?? 0}`);
    lines.push(`Vault LoRAs: ${counts.vault_loras ?? 0}`);
    lines.push(`Vault mapsets: ${counts.vault_mapsets ?? 0}`);
    lines.push(`Legacy prompt presets: ${counts.legacy_prompt_presets ?? 0}`);
    lines.push('');
    const outputDirs = snapshot.output_dirs || {};
    lines.push('Output directories:');
    if (Object.keys(outputDirs).length) {
      Object.entries(outputDirs).forEach(([key, value]) => lines.push(`- ${key}: ${value}`));
    } else {
      lines.push('- No output dirs configured in legacy settings yet.');
    }
    lines.push('');
    lines.push('LoRA parent folders:');
    if ((snapshot.legacy_lora_parent_dirs || []).length) {
      snapshot.legacy_lora_parent_dirs.forEach(path => lines.push(`- ${path}`));
    } else {
      lines.push('- No LoRA file entries registered in vault_db.json yet.');
    }
    lines.push('');
    lines.push('Notes:');
    (snapshot.notes || []).forEach(note => lines.push(`- ${note}`));
    details.value = lines.join('\n');
  }
}

async function refreshStorageCompatSnapshot() {
  try {
    setStatus('library-storage-compat-status', 'Reading legacy path snapshot...');
    const data = await safeFetchJson('/api/neo-library/storage-compat');
    renderStorageCompat(data || {});
    setStatus('library-storage-compat-status', 'Legacy path snapshot refreshed.');
  } catch (e) {
    setStatus('library-storage-compat-status', e.message, 'error');
  }
}

async function refreshNeoLibrarySummary() {
  try {
    const data = await safeFetchJson('/api/neo-library/summary');
    neoLibrarySetSummary(data.summary || {});
    fillCategorySelect('neo-library-output-save-category', initialPromptCategoryList.length ? initialPromptCategoryList : ['uncategorized'], $('neo-library-output-save-category')?.value || initialLastPromptCategory || 'uncategorized');
    setStatus('neo-library-summary-status', 'Library snapshot refreshed.');
  } catch (e) {
    setStatus('neo-library-summary-status', e.message, 'error');
  }
}

function neoLibraryPromptParams() {
  const params = new URLSearchParams();
  params.set('query', trim($('neo-library-prompt-query')?.value || ''));
  const category = trim($('neo-library-prompt-category')?.value || '');
  if (category && category !== 'all') params.set('category', category);
  params.set('model', trim($('neo-library-prompt-model')?.value || ''));
  params.set('prompt_style', trim($('neo-library-prompt-style')?.value || ''));
  params.set('sort', $('neo-library-prompt-sort')?.value || 'newest');
  params.set('page', String(neoLibraryPromptPage));
  params.set('page_size', $('neo-library-prompt-page-size')?.value || '12');
  return params;
}

function renderNeoLibraryPromptCards(entries) {
  const wrap = $('neo-library-prompt-grid');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!entries || !entries.length) {
    wrap.innerHTML = '<div class="card-lite"><div class="muted">No saved prompts match the current filters.</div></div>';
    return;
  }
  entries.forEach(entry => {
    const card = document.createElement('div');
    card.className = 'neo-library-card';
    const updated = String(entry.updated_at || entry.created_at || '').replace('T', ' ');
    card.innerHTML = `
      <div class="neo-library-card-head">
        <div>
          <div class="neo-library-card-title">${escapeHtml(entry.name || '(untitled)')}</div>
          <div class="neo-library-card-meta">${escapeHtml(entry.category || 'uncategorized')} · ${escapeHtml(entry.model || 'default')}</div>
        </div>
        <span class="badge">${escapeHtml(entry.style || '—')}</span>
      </div>
      <div class="neo-library-card-meta" style="margin-top:6px;">${escapeHtml(updated || '—')}</div>
      <div class="neo-library-card-snippet">${escapeHtml(entry.prompt_preview || '')}</div>
      <div class="row" style="margin-top:auto;">
        <button class="btn" type="button" data-neo-prompt-open="${escapeHtml(entry.id || '')}">Edit</button>
        <button class="btn" type="button" data-neo-prompt-send="${escapeHtml(entry.id || '')}">To Prompt</button>
      </div>
    `;
    wrap.appendChild(card);
  });
}

function renderNeoLibraryPromptPagination(total, shown, totalPages) {
  neoLibraryPromptTotalPages = Math.max(1, Number(totalPages) || 1);
  if ($('neo-library-prompt-page')) $('neo-library-prompt-page').textContent = `Page ${neoLibraryPromptPage} of ${neoLibraryPromptTotalPages}`;
  const start = total ? ((neoLibraryPromptPage - 1) * Number($('neo-library-prompt-page-size')?.value || 12)) + 1 : 0;
  const end = total ? start + Math.max(0, shown - 1) : 0;
  if ($('neo-library-prompt-summary')) $('neo-library-prompt-summary').textContent = `Showing ${start}-${end} of ${total}`;
  if ($('btn-neo-library-prompt-prev')) $('btn-neo-library-prompt-prev').disabled = neoLibraryPromptPage <= 1;
  if ($('btn-neo-library-prompt-next')) $('btn-neo-library-prompt-next').disabled = neoLibraryPromptPage >= neoLibraryPromptTotalPages;
}


function moveNeoLibraryPromptManagerToGeneration() {
  moveNeoLibraryPanelToGeneration('generation-prompt-manager-host', 'neo-library-prompt-browser');
}

function syncGenerationModalBodyLock() {
  const openModalIds = [
    'generation-prompt-manager-modal',
    'generation-save-prompt-modal',
    'backend-manager-modal',
    'generation-image-zoom-modal',
    'generation-mask-editor-modal',
    'generation-keyword-manager-modal'
  ];
  const hasOpenModal = openModalIds.some(id => !$(id)?.classList.contains('hidden'));
  document.body.classList.toggle('modal-open', hasOpenModal);
}

function deriveGenerationPromptSaveName() {
  const positive = trim($('generation-positive')?.value || '');
  if (!positive) return 'Untitled Generation Prompt';
  return positive.split(',').map(part => trim(part)).filter(Boolean).slice(0, 3).join(', ').slice(0, 72) || 'Untitled Generation Prompt';
}

function buildGenerationPromptHelperNotes() {
  const lines = [];
  const negative = trim($('generation-negative')?.value || '');
  if (negative) lines.push(`Negative prompt:\n${negative}`);
  const stylePositive = trim($('generation-style-positive')?.value || '');
  const styleNegative = trim($('generation-style-negative')?.value || '');
  if (stylePositive || styleNegative) {
    lines.push(['Style helper:', stylePositive ? `Positive: ${stylePositive}` : '', styleNegative ? `Negative: ${styleNegative}` : ''].filter(Boolean).join('\n'));
  }
  const workflowNotes = trim($('generation-workflow-notes')?.value || '');
  if (workflowNotes) lines.push(`Workflow notes:\n${workflowNotes}`);
  return lines.join('\n\n');
}

function openGenerationSavePromptModal() {
  const modal = $('generation-save-prompt-modal');
  if (!modal) return;
  const categories = Array.isArray(initialPromptCategoryList) && initialPromptCategoryList.length ? initialPromptCategoryList : ['uncategorized'];
  fillCategorySelect('generation-save-prompt-category', categories, $('generation-save-prompt-category')?.value || initialLastPromptCategory || 'uncategorized');
  if ($('generation-save-prompt-name')) $('generation-save-prompt-name').value = deriveGenerationPromptSaveName();
  if ($('generation-save-prompt-notes')) $('generation-save-prompt-notes').value = buildGenerationPromptHelperNotes();
  if ($('generation-save-prompt-positive-preview')) $('generation-save-prompt-positive-preview').value = $('generation-positive')?.value || '';
  if ($('generation-save-prompt-negative-preview')) $('generation-save-prompt-negative-preview').value = $('generation-negative')?.value || '';
  setStatus('generation-save-prompt-status', '');
  modal.classList.remove('hidden');
  syncGenerationModalBodyLock();
}

function closeGenerationSavePromptModal() {
  const modal = $('generation-save-prompt-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  syncGenerationModalBodyLock();
}

async function saveGenerationPromptEntry() {
  const positive = trim($('generation-positive')?.value || '');
  if (!positive) {
    setStatus('generation-save-prompt-status', 'Add a positive prompt first.', 'warn');
    return;
  }
  const category = trim($('generation-save-prompt-category')?.value || '') || 'uncategorized';
  const name = trim($('generation-save-prompt-name')?.value || '') || deriveGenerationPromptSaveName();
  const notesInput = trim($('generation-save-prompt-notes')?.value || '');
  const composedNotes = [notesInput, buildGenerationPromptHelperNotes()].filter(Boolean).join('\n\n');
  const fd = new FormData();
  fd.append('name', name);
  fd.append('category', category);
  fd.append('prompt', $('generation-positive')?.value || '');
  fd.append('raw_prompt', $('generation-positive')?.value || '');
  fd.append('model', typeof currentModel === 'function' ? currentModel() : '');
  fd.append('notes', composedNotes);
  fd.append('preset_name', '');
  fd.append('style', trim($('generation-style-name')?.value || ''));
  fd.append('finish_reason', 'generation-shell-save');
  fd.append('settings_json', JSON.stringify({
    source: 'generation-shell',
    negative_prompt: $('generation-negative')?.value || '',
    style_positive: $('generation-style-positive')?.value || '',
    style_negative: $('generation-style-negative')?.value || '',
    workflow_notes: $('generation-workflow-notes')?.value || ''
  }));
  fd.append('generation_mode', 'generate');
  try {
    setStatus('generation-save-prompt-status', 'Saving prompt...');
    const data = await safeFetchJson('/api/save-prompt', { method:'POST', body:fd });
    if (Array.isArray(data.prompt_categories) && data.prompt_categories.length) {
      fillCategorySelect('generation-save-prompt-category', data.prompt_categories, category);
    }
    if (Array.isArray(data.prompt_categories) && typeof initialPromptCategoryList !== 'undefined') {
      initialPromptCategoryList.splice(0, initialPromptCategoryList.length, ...data.prompt_categories);
    }
    await refreshGenerationSavedPromptSelect(false);
    const newId = data.record?.id || '';
    if (newId && $('generation-saved-prompt-select')) $('generation-saved-prompt-select').value = newId;
    if (typeof refreshNeoLibraryPromptBrowser === 'function') refreshNeoLibraryPromptBrowser().catch(() => {});
    if (typeof refreshSavedPromptNames === 'function') refreshSavedPromptNames().catch(() => {});
    setStatus('generation-status', data.message || 'Generation prompt saved.', 'success');
    setStatus('generation-save-prompt-status', data.message || 'Generation prompt saved.', 'success');
    window.setTimeout(() => closeGenerationSavePromptModal(), 300);
  } catch (e) {
    setStatus('generation-save-prompt-status', e.message || 'Could not save the generation prompt.', 'error');
  }
}

function openGenerationPromptManagerModal() {
  const modal = $('generation-prompt-manager-modal');
  if (!modal) return;
  moveNeoLibraryPromptManagerToGeneration();
  modal.classList.remove('hidden');
  syncGenerationModalBodyLock();
  refreshNeoLibraryPromptBrowser().catch(() => {});
}

function closeGenerationPromptManagerModal() {
  const modal = $('generation-prompt-manager-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  syncGenerationModalBodyLock();
}

async function refreshGenerationSavedPromptSelect(keepSelection=true) {
  const prev = keepSelection ? trim($('generation-saved-prompt-select')?.value || '') : '';
  try {
    const data = await safeFetchJson('/api/neo-library/prompt-browser?sort=newest&page=1&page_size=200');
    const select = $('generation-saved-prompt-select');
    if (!select) return;
    select.innerHTML = '<option value="">Choose a saved prompt</option>';
    (data.entries || []).forEach(rec => {
      const opt = document.createElement('option');
      opt.value = rec.id || '';
      const category = rec.category || 'uncategorized';
      const name = rec.name || '(untitled)';
      opt.textContent = `${category} · ${name}`;
      if (prev && prev === opt.value) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (_) {}
}

async function applySavedGenerationPrompt(append=false) {
  const promptId = trim($('generation-saved-prompt-select')?.value || '');
  if (!promptId) {
    setStatus('generation-status', 'Pick a saved prompt first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/prompt-record?prompt_id=${encodeURIComponent(promptId)}`);
    const textValue = String((data.record || {}).prompt || '');
    if (!textValue.trim()) {
      setStatus('generation-status', 'That saved prompt is empty.', 'warn');
      return;
    }
    const current = $('generation-positive')?.value || '';
    $('generation-positive').value = append && current.trim() ? `${current.trim()}, ${textValue.trim()}` : textValue;
    neoLibraryDispatchGenerationInput?.('generation-positive');
    setStatus('generation-status', append ? 'Saved prompt appended to Generation.' : 'Saved prompt loaded into Generation.', 'success');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not load the saved prompt.', 'error');
  }
}

async function refreshNeoLibraryPromptBrowser(options={}) {
  const { resetPage=false } = options || {};
  if (resetPage) neoLibraryPromptPage = 1;
  try {
    setStatus('neo-library-prompt-status', 'Loading prompts...');
    const data = await safeFetchJson(`/api/neo-library/prompt-browser?${neoLibraryPromptParams().toString()}`);
    const cats = ['all', ...((data.categories || []).filter(cat => cat !== 'all'))];
    fillCategorySelect('neo-library-prompt-category', cats, $('neo-library-prompt-category')?.value || 'all');
    renderNeoLibraryPromptCards(data.entries || []);
    neoLibraryPromptPage = Math.max(1, Number(data.page) || neoLibraryPromptPage || 1);
    renderNeoLibraryPromptPagination(Number(data.total || 0), (data.entries || []).length, Number(data.total_pages || 1));
    setStatus('neo-library-prompt-status', Number(data.total || 0) ? `${data.total} saved prompt(s) found.` : 'No saved prompts match the current filters.');
  } catch (e) {
    setStatus('neo-library-prompt-status', e.message, 'error');
  }
}

function scheduleNeoLibraryPromptRefresh(resetPage=false) {
  if (neoLibraryPromptRefreshHandle) window.clearTimeout(neoLibraryPromptRefreshHandle);
  neoLibraryPromptRefreshHandle = window.setTimeout(() => refreshNeoLibraryPromptBrowser({ resetPage }), 180);
}

function loadNeoLibraryPromptEditor(rec, categories=[]) {
  if (!rec) return;
  neoLibraryLoadedPromptId = rec.id || '';
  $('neo-library-prompt-id').value = rec.id || '';
  $('neo-library-prompt-editor-name').value = rec.name || '';
  fillCategorySelect('neo-library-prompt-editor-category', categories.length ? categories : [rec.category || 'uncategorized'], rec.category || 'uncategorized');
  $('neo-library-prompt-editor-model').value = rec.model || '';
  $('neo-library-prompt-editor-style').value = rec.style || '';
  $('neo-library-prompt-editor-text').value = rec.prompt || '';
  $('neo-library-prompt-editor-notes').value = rec.notes || '';
  $('neo-library-prompt-editor-raw').value = rec.raw_prompt || rec.prompt || '';
  $('neo-library-prompt-editor-updated').textContent = `Updated ${String(rec.updated_at || rec.created_at || '—').replace('T', ' ')}`;
  $('neo-library-prompt-editor-wrap').classList.remove('hidden');
}

async function openNeoLibraryPrompt(promptId, action='edit') {
  if (!promptId) return;
  try {
    const data = await safeFetchJson(`/api/neo-library/prompt-record?prompt_id=${encodeURIComponent(promptId)}`);
    loadNeoLibraryPromptEditor(data.record || {}, data.categories || []);
    setStatus('neo-library-prompt-editor-status', 'Loaded prompt record.');
    if (action === 'send') sendNeoLibraryPromptToStudio(false);
  } catch (e) {
    setStatus('neo-library-prompt-status', e.message, 'error');
  }
}

function sendNeoLibraryPromptToStudio(append=false) {
  const text = $('neo-library-prompt-editor-text')?.value || '';
  if (!text) {
    setStatus('neo-library-prompt-editor-status', 'Load a prompt first.', 'warn');
    return;
  }
  const current = $('generation-positive')?.value || '';
  $('generation-positive').value = append && current.trim() ? `${current.trim()}, ${text.trim()}` : text;
  neoLibraryDispatchGenerationInput?.('generation-positive');
  neoLibraryOpenGenerationTab?.();
  setStatus('neo-library-prompt-editor-status', append ? 'Prompt appended into Generation.' : 'Prompt loaded into Generation.');
  refreshGenerationSavedPromptSelect(true).catch(() => {});
}

async function updateNeoLibraryPrompt() {
  const promptId = $('neo-library-prompt-id')?.value || neoLibraryLoadedPromptId || '';
  if (!promptId) {
    setStatus('neo-library-prompt-editor-status', 'Load a prompt first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('prompt_id', promptId);
  fd.append('category', $('neo-library-prompt-editor-category').value || 'uncategorized');
  fd.append('name', $('neo-library-prompt-editor-name').value || 'Untitled Prompt');
  fd.append('prompt', $('neo-library-prompt-editor-text').value || '');
  fd.append('model', $('neo-library-prompt-editor-model').value || '');
  fd.append('notes', $('neo-library-prompt-editor-notes').value || '');
  fd.append('raw_prompt', $('neo-library-prompt-editor-raw').value || $('neo-library-prompt-editor-text').value || '');
  fd.append('style', $('neo-library-prompt-editor-style').value || '');
  try {
    const data = await safeFetchJson('/api/update-prompt', { method:'POST', body:fd });
    refreshCategoryList(data.categories || initialCategories);
    neoLibrarySetSummary(data.stats || {});
    loadNeoLibraryPromptEditor(data.record || {}, data.prompt_categories || []);
    await refreshNeoLibraryPromptBrowser();
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    setStatus('neo-library-prompt-editor-status', data.message || 'Prompt updated.');
  } catch (e) {
    setStatus('neo-library-prompt-editor-status', e.message, 'error');
  }
}

async function deleteNeoLibraryPrompt() {
  const promptId = $('neo-library-prompt-id')?.value || neoLibraryLoadedPromptId || '';
  if (!promptId) {
    setStatus('neo-library-prompt-editor-status', 'Load a prompt first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('prompt_id', promptId);
  fd.append('category', $('neo-library-prompt-editor-category').value || '');
  fd.append('name', $('neo-library-prompt-editor-name').value || '');
  try {
    const data = await safeFetchJson('/api/delete-prompt', { method:'POST', body:fd });
    neoLibraryLoadedPromptId = '';
    $('neo-library-prompt-editor-wrap').classList.add('hidden');
    refreshCategoryList(data.categories || initialCategories);
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
    await refreshNeoLibrarySummary();
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    setStatus('neo-library-prompt-status', data.message || 'Prompt deleted.');
  } catch (e) {
    setStatus('neo-library-prompt-editor-status', e.message, 'error');
  }
}


function neoLibraryOpenComposerSection() {
  const block = document.querySelector('[data-accordion-id="neo-library-prompt-composer"]');
  if (block && !block.open) block.open = true;
}

function sendNeoLibraryComposerToPromptStudio(append=false) {
  const text = trim($('bundle-positive')?.value || '');
  if (!text) {
    setStatus('bundle-status', 'The composer positive prompt is empty.', 'warn');
    return;
  }
  const currentIdea = $('prompt-idea')?.value || '';
  const currentOutput = $('prompt-output')?.value || '';
  const next = append && currentOutput ? `${currentOutput.trim()}, ${text}` : text;
  if ($('prompt-idea')) $('prompt-idea').value = append && currentIdea ? `${currentIdea.trim()}, ${text}` : text;
  if ($('prompt-output')) $('prompt-output').value = next;
  if ($('prompt-raw')) $('prompt-raw').value = next;
  updateCounter('prompt-idea', 'prompt-idea-counter');
  updateCounter('prompt-output', 'prompt-output-counter');
  if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
  switchTab('prompt');
  setStatus('bundle-status', append ? 'Composer prompt appended into Prompt Studio.' : 'Composer prompt sent to Prompt Studio.');
}

function openNeoLibraryPromptInComposer() {
  const text = $('neo-library-prompt-editor-text')?.value || '';
  if (!text) {
    setStatus('neo-library-prompt-editor-status', 'Load a prompt first.', 'warn');
    return;
  }
  neoLibraryOpenComposerSection();
  if ($('bundle-positive')) $('bundle-positive').value = text;
  if ($('bundle-name') && !$('bundle-name').value) $('bundle-name').value = $('neo-library-prompt-editor-name')?.value || 'Prompt Composer Draft';
  if ($('bundle-style-notes') && !$('bundle-style-notes').value) $('bundle-style-notes').value = $('neo-library-prompt-editor-notes')?.value || '';
  setStatus('bundle-status', 'Loaded prompt into Prompt Composer.');
}

function fillSimpleSelect(id, values, selected='', emptyLabel='Select item') {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = emptyLabel;
  el.appendChild(first);
  (values || []).forEach(value => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    if (value === selected) opt.selected = true;
    el.appendChild(opt);
  });
}

async function refreshNeoLibraryComposerLibraries(options={}) {
  const { keepItem=false } = options || {};
  const params = new URLSearchParams();
  params.set('library', $('neo-library-composer-library')?.value || '');
  params.set('query', trim($('neo-library-composer-library-search')?.value || ''));
  const previousItem = keepItem ? ($('neo-library-composer-library-item')?.value || '') : '';
  try {
    setStatus('neo-library-composer-status', 'Loading Prompt Suite libraries...');
    const data = await safeFetchJson(`/api/neo-library/composer-library-browser?${params.toString()}`);
    fillSimpleSelect('neo-library-composer-library', data.libraries || [], data.selected_library || '', 'Select library');
    const items = data.items || [];
    const selectedItem = previousItem && items.includes(previousItem) ? previousItem : (items[0] || '');
    fillSimpleSelect('neo-library-composer-library-item', items, selectedItem, items.length ? 'Select library item' : 'No snippets found');
    if ($('neo-library-composer-library-preview')) $('neo-library-composer-library-preview').value = selectedItem || '';
    setStatus('neo-library-composer-status', items.length ? `${data.total || items.length} snippet(s) available.` : 'No snippets matched this library/search.', items.length ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-composer-status', e.message, 'error');
  }
}

function scheduleNeoLibraryComposerLibraryRefresh() {
  if (neoLibraryComposerLibraryRefreshHandle) window.clearTimeout(neoLibraryComposerLibraryRefreshHandle);
  neoLibraryComposerLibraryRefreshHandle = window.setTimeout(() => refreshNeoLibraryComposerLibraries({ keepItem:false }), 180);
}

function syncNeoLibraryComposerLibraryPreview() {
  if ($('neo-library-composer-library-preview')) $('neo-library-composer-library-preview').value = $('neo-library-composer-library-item')?.value || '';
}

function insertNeoLibraryComposerSnippet() {
  const snippet = trim($('neo-library-composer-library-item')?.value || '');
  if (!snippet) {
    setStatus('neo-library-composer-status', 'Choose a library item first.', 'warn');
    return;
  }
  const target = $('neo-library-keyword-target')?.value || $('neo-library-composer-target')?.value || 'positive';
  try {
    neoLibraryAppendGenerationPromptText(target, snippet, ', ');
    setStatus('neo-library-composer-status', target === 'negative' ? 'Snippet inserted into the generation negative prompt.' : 'Snippet inserted into the main generation prompt.');
  } catch (e) {
    setStatus('neo-library-composer-status', e.message || 'Could not find the generation prompt box.', 'error');
  }
}
window.insertNeoLibraryComposerSnippet = insertNeoLibraryComposerSnippet;

function neoLibraryCaptionMeta(rec) {
  if (!rec) return '';
  const rows = [];
  rows.push(`Category: ${rec.category || 'uncategorized'}`);
  rows.push(`Model: ${rec.model || 'default'}`);
  rows.push(`Style: ${rec.prompt_style || '—'}`);
  rows.push(`Component: ${rec.component_type || '—'}`);
  rows.push(`Mode: ${String(rec.caption_mode || 'full_image').replace(/_/g, ' ')}`);
  rows.push(`Detail: ${String(rec.detail_level || 'detailed').replace(/_/g, '-')}`);
  if (rec.crop_meta) rows.push(`Crop: x ${Math.round((rec.crop_meta.x || 0) * 100)}%, y ${Math.round((rec.crop_meta.y || 0) * 100)}%, w ${Math.round((rec.crop_meta.w || 0) * 100)}%, h ${Math.round((rec.crop_meta.h || 0) * 100)}%`);
  return rows.join('\n');
}

function fillSelectFromList(id, values, selected='', placeholder='—') {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  el.appendChild(first);
  (values || []).forEach(value => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    if (value === selected) opt.selected = true;
    el.appendChild(opt);
  });
}

function loadNeoLibraryCaptionRecord(rec) {
  if (!rec) {
    $('neo-library-caption-preview').removeAttribute('src');
    $('neo-library-caption-id').value = '';
    $('neo-library-caption-image-url').value = '';
    $('neo-library-caption-editor-name').value = '';
    $('neo-library-caption-editor-model').value = '';
    $('neo-library-caption-editor-style').value = '';
    $('neo-library-caption-editor-component').value = '';
    $('neo-library-caption-editor-mode').value = '';
    $('neo-library-caption-editor-detail').value = '';
    $('neo-library-caption-text').value = '';
    $('neo-library-caption-notes').value = '';
    $('neo-library-caption-meta').value = '';
    $('neo-library-caption-updated').textContent = 'Updated —';
    return;
  }
  $('neo-library-caption-id').value = rec.id || '';
  $('neo-library-caption-image-url').value = rec.image_url || '';
  $('neo-library-caption-preview').src = rec.thumb_url || rec.image_url || '';
  $('neo-library-caption-editor-name').value = rec.name || '';
  $('neo-library-caption-editor-model').value = rec.model || '';
  $('neo-library-caption-editor-style').value = rec.prompt_style || '';
  $('neo-library-caption-editor-component').value = rec.component_type || '';
  $('neo-library-caption-editor-mode').value = String(rec.caption_mode || 'full_image').replace(/_/g, ' ');
  $('neo-library-caption-editor-detail').value = String(rec.detail_level || 'detailed').replace(/_/g, '-');
  $('neo-library-caption-text').value = rec.caption || '';
  $('neo-library-caption-notes').value = rec.notes || '';
  $('neo-library-caption-meta').value = neoLibraryCaptionMeta(rec);
  $('neo-library-caption-updated').textContent = `Updated ${String(rec.updated_at || rec.created_at || '—').replace('T', ' ')}`;
}

async function refreshNeoLibraryCaptionSync(options={}) {
  const { category='', name='', image='' } = options || {};
  const hasExplicitName = Object.prototype.hasOwnProperty.call(options || {}, 'name');
  const hasExplicitImage = Object.prototype.hasOwnProperty.call(options || {}, 'image');
  if (neoLibraryCaptionSyncHandle) window.clearTimeout(neoLibraryCaptionSyncHandle);
  try {
    const params = new URLSearchParams();
    const resolvedName = hasExplicitName ? (name || '') : ($('neo-library-caption-name')?.value || '');
    const resolvedImage = hasExplicitImage ? (image || '') : ($('neo-library-caption-image')?.value || '');
    params.set('category', category || $('neo-library-caption-category')?.value || '');
    params.set('name', resolvedName);
    params.set('image_name', resolvedImage);
    setStatus('neo-library-caption-status', 'Loading caption record...');
    const data = await safeFetchJson(`/api/neo-library/caption-sync?${params.toString()}`);
    fillCategorySelect('neo-library-caption-category', data.categories || ['uncategorized'], data.selected_category || 'uncategorized');
    const record = data.record || null;
    fillSelectFromList('neo-library-caption-name', data.names || [], record?.name || name || '', 'Select name');
    fillSelectFromList('neo-library-caption-image', data.images || [], record?.image_path ? record.image_path.split('/').pop() : (record?.image_url || image || ''), 'Select image');
    if (record?.image_path) {
      const selectedImage = String(record.image_path || '').split('/').pop();
      if ($('neo-library-caption-image')) $('neo-library-caption-image').value = selectedImage;
    }
    loadNeoLibraryCaptionRecord(record);
    setStatus('neo-library-caption-status', record ? 'Caption record loaded.' : 'No caption records found in this category.', record ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-caption-status', e.message, 'error');
  }
}


function moveNeoLibraryPanelToGeneration(hostId, accordionId) {
  const host = $(hostId);
  const panel = document.querySelector(`[data-accordion-id="${accordionId}"]`);
  if (!host || !panel) return;
  const prev = panel.previousElementSibling;
  if (prev && prev.classList.contains('divider')) prev.remove();
  host.appendChild(panel);
}

function mountNeoLibraryGenerationPanels() {
  moveNeoLibraryPanelToGeneration('generation-output-inspector-host', 'neo-library-output-inspector');
  moveNeoLibraryPanelToGeneration('generation-caption-browser-host', 'neo-library-caption-browser');
}

async function neoLibraryFetchImageAsFile(source, fallbackName='reference.png') {
  if (!source) return null;
  if (source instanceof File) return source;
  const response = await fetch(String(source), { cache:'no-store' });
  if (!response.ok) throw new Error(`Could not load the selected image (${response.status}).`);
  const blob = await response.blob();
  return new File([blob], fallbackName, { type: blob.type || 'image/png' });
}

function neoLibraryOpenGenerationTab() {
  if (typeof switchMainTab === 'function') switchMainTab('generate');
  else document.querySelector('[data-main-tab="generate"]')?.click();
}

function neoLibraryDispatchGenerationInput(id) {
  const el = $(id);
  if (!el) return;
  el.dispatchEvent(new Event('input', { bubbles:true }));
  el.dispatchEvent(new Event('change', { bubbles:true }));
}

function neoLibraryNormalizePromptText(value) {
  return String(value || '').trim();
}

function neoLibraryPromptAlreadyContains(base, insert) {
  const haystack = neoLibraryNormalizePromptText(base).toLowerCase();
  const needle = neoLibraryNormalizePromptText(insert).toLowerCase();
  return !!needle && haystack === needle || (!!needle && haystack.includes(needle));
}

function neoLibraryMergePromptText(base, insert, separator=', ') {
  const current = neoLibraryNormalizePromptText(base);
  const incoming = neoLibraryNormalizePromptText(insert);
  if (!incoming) return current;
  if (!current) return incoming;
  if (neoLibraryPromptAlreadyContains(current, incoming)) return current;
  return `${current}${separator}${incoming}`;
}

function neoLibraryAcquireGenerationPromptMergeLock(promptText='', ttlMs=6500) {
  const prompt = neoLibraryNormalizePromptText(promptText);
  if (!prompt) return null;
  const lock = {
    source: 'caption_browser',
    target: 'generation-positive',
    positive: prompt,
    mode: 'merge_append',
    createdAt: Date.now(),
    expiresAt: Date.now() + Math.max(1000, Number(ttlMs) || 6500),
  };
  window.__neoGenerationPromptMergeLock = lock;
  window.__neoPendingGenerationPositive = prompt;
  window.__neoPendingGenerationPositiveExpiresAt = lock.expiresAt;
  return lock;
}

function neoLibraryGetGenerationPromptMergeLock() {
  const lock = window.__neoGenerationPromptMergeLock || null;
  if (!lock || !lock.positive || !lock.expiresAt || Date.now() > Number(lock.expiresAt || 0)) {
    window.__neoGenerationPromptMergeLock = null;
    return null;
  }
  return lock;
}

function neoLibraryClearGenerationPromptMergeLockIfSatisfied() {
  const lock = neoLibraryGetGenerationPromptMergeLock();
  if (!lock) return;
  const current = $('generation-positive')?.value || '';
  if (neoLibraryPromptAlreadyContains(current, lock.positive)) {
    window.__neoGenerationPromptMergeLock = null;
    neoLibraryClearPendingGenerationPrompt();
  }
}

function neoLibraryAppendToGenerationPositive(text) {
  const prompt = neoLibraryNormalizePromptText(text || '');
  if (!prompt) return false;
  const el = $('generation-positive');
  if (!el) throw new Error('Could not find the generation positive prompt box.');
  neoLibraryAcquireGenerationPromptMergeLock(prompt);
  el.value = neoLibraryMergePromptText(el.value || '', prompt, ', ');
  neoLibraryDispatchGenerationInput('generation-positive');
  try {
    document.dispatchEvent(new CustomEvent('neo-caption-browser-prompt-handoff', {
      detail: { source:'caption_browser', target:'generation-positive', mode:'merge_append' }
    }));
  } catch (_) {}
  return neoLibraryPromptAlreadyContains(el.value || '', prompt);
}

function neoLibraryGetPendingGenerationPromptState() {
  const lock = neoLibraryGetGenerationPromptMergeLock();
  const text = trim((lock?.positive || window.__neoPendingGenerationPositive) || '');
  const expiresAt = Number((lock?.expiresAt || window.__neoPendingGenerationPositiveExpiresAt) || 0);
  if (!text || !expiresAt || Date.now() > expiresAt) {
    window.__neoPendingGenerationPositive = '';
    window.__neoPendingGenerationPositiveExpiresAt = 0;
    window.__neoGenerationPromptMergeLock = null;
    return null;
  }
  return { text, expiresAt };
}

function neoLibraryClearPendingGenerationPrompt() {
  window.__neoPendingGenerationPositive = '';
  window.__neoPendingGenerationPositiveExpiresAt = 0;
}

function neoLibraryEnsurePendingGenerationPrompt(promptText='', attempts=8, delayMs=120) {
  const prompt = trim(promptText || '');
  if (!prompt) return;
  const state = neoLibraryGetPendingGenerationPromptState() || { text: prompt, expiresAt: Date.now() + 5000 };
  let remaining = Math.max(1, Number(attempts) || 1);
  const applyPrompt = () => {
    const active = neoLibraryGetPendingGenerationPromptState();
    if (!active || active.text !== prompt) return;
    try {
      const ok = neoLibraryAppendToGenerationPositive(prompt);
      const current = trim($('generation-positive')?.value || '');
      if (ok || neoLibraryPromptAlreadyContains(current, prompt)) {
        window.setTimeout(() => {
          const latest = trim($('generation-positive')?.value || '');
          const pending = neoLibraryGetPendingGenerationPromptState();
          if (!pending || pending.text !== prompt) return;
          if (neoLibraryPromptAlreadyContains(latest, prompt)) { neoLibraryClearPendingGenerationPrompt(); window.__neoGenerationPromptMergeLock = null; }
        }, Math.max(180, Number(delayMs) || 120));
        return;
      }
    } catch (_) {}
    remaining -= 1;
    if (remaining > 0) window.setTimeout(applyPrompt, Math.max(60, Number(delayMs) || 120));
  };
  window.__neoPendingGenerationPositive = prompt;
  window.__neoPendingGenerationPositiveExpiresAt = state.expiresAt;
  applyPrompt();
}

function neoLibraryFlushPendingGenerationPrompt(promptText='', attempts=8) {
  const prompt = trim(promptText || '');
  if (!prompt) return;
  neoLibraryAcquireGenerationPromptMergeLock(prompt, 7000);
  neoLibraryEnsurePendingGenerationPrompt(prompt, attempts, 120);
}

async function neoLibraryRouteImageToGeneration(file, target='img2img') {
  if (!file) throw new Error('No image is available to send.');
  if (typeof assignFileToInput !== 'function') throw new Error('Image routing helper is not available yet.');
  const controlUnitMap = {
    control_canny: 'canny',
    control_softedge: 'softedge',
    control_lineart: 'lineart',
    control_scribble: 'scribble',
  };
  const targetMode = window.NeoImageState?.normalizeWorkflowMode ? window.NeoImageState.normalizeWorkflowMode(target, 'img2img') : String(target || '').trim().toLowerCase();
  if (targetMode === 'img2img' || targetMode === 'inpaint' || targetMode === 'outpaint') {
    assignFileToInput('generation-source-image', file);
    const sourceName = file?.name || 'library_image.png';
    if (window.NeoImageState?.lockUploadedSource) {
      window.NeoImageState.lockUploadedSource(sourceName, 'neo-library-image-route');
    } else if (window.NeoImageState?.updateSource) {
      window.NeoImageState.updateSource({
        active_source_image: sourceName,
        explicit_source_type: 'library_image',
        source_route_state: {
          source_kind: 'library_image',
          source_name: sourceName,
          routed_at: new Date().toISOString(),
          route_source: 'neo-library-image-route',
        },
      }, 'neo-library-image-route');
    }
    if (window.setGenerationWorkflowMode) {
      window.setGenerationWorkflowMode(targetMode, {
        source: 'neo-library-image-route',
        reason: 'library_send_to_generation_mode',
        sourceKind: 'library_image',
        sourceName,
        outputPolicy: 'new_current_run',
        forceReveal: targetMode === 'outpaint' ? 'assets' : 'core',
        validate: true,
      });
    } else if ($('generation-workflow-type')) {
      $('generation-workflow-type').value = targetMode;
      if (typeof syncGenerationModeUI === 'function') syncGenerationModeUI();
    }
    if (targetMode === 'inpaint' || targetMode === 'outpaint') {
      try { if (typeof clearGenerationImageInput === 'function') clearGenerationImageInput('generation-mask-image'); } catch (_) {}
    }
    if (targetMode === 'outpaint') {
      try { if (typeof focusGenerationSetupTab === 'function') focusGenerationSetupTab('assets', 'generation-outpaint-settings'); } catch (_) {}
    } else {
      try { if (typeof focusGenerationSetupTab === 'function') focusGenerationSetupTab('core'); } catch (_) {}
    }
    return;
  }
  if (target === 'control_current' || controlUnitMap[target]) {
    if ($('generation-controlnet-enabled')) $('generation-controlnet-enabled').checked = true;
    if (controlUnitMap[target] && $('generation-controlnet-unit')) $('generation-controlnet-unit').value = controlUnitMap[target];
    if (controlUnitMap[target] && $('generation-controlnet-preprocessor')) $('generation-controlnet-preprocessor').value = controlUnitMap[target];
    assignFileToInput('generation-control-image', file);
    neoLibraryDispatchGenerationInput('generation-controlnet-unit');
    neoLibraryDispatchGenerationInput('generation-controlnet-preprocessor');
    return;
  }
  throw new Error('That image destination is not wired yet in this build.');
}

function bindNeoLibraryGenerationHandoffGuards() {
  if (window.__neoLibraryGenerationHandoffBound) return;
  window.__neoLibraryGenerationHandoffBound = true;
  const replay = () => {
    const pending = neoLibraryGetPendingGenerationPromptState();
    if (!pending) return;
    neoLibraryEnsurePendingGenerationPrompt(pending.text, 10, 140);
  };
  [
    'neo-generation-layout-mounted',
    'neo-generation-workspace-changed',
    'neo-generation-preset-changed',
    'neo-generation-family-changed',
    'neo-generation-goal-changed',
    'neo-active-surface-changed',
  ].forEach(name => document.addEventListener(name, () => {
    window.setTimeout(replay, 60);
    window.requestAnimationFrame(replay);
    window.setTimeout(replay, 220);
  }));
  document.addEventListener('input', (event) => {
    const target = event?.target;
    if (!target || target.id !== 'generation-positive') return;
    const pending = neoLibraryGetPendingGenerationPromptState();
    if (!pending) return;
    const current = trim(target.value || '');
    if (neoLibraryPromptAlreadyContains(current, pending.text)) { neoLibraryClearPendingGenerationPrompt(); window.__neoGenerationPromptMergeLock = null; }
  }, true);
}

bindNeoLibraryGenerationHandoffGuards();

window.NeoLibraryGenerationPromptHandoff = window.NeoLibraryGenerationPromptHandoff || {};
window.NeoLibraryGenerationPromptHandoff.getLock = neoLibraryGetGenerationPromptMergeLock;
window.NeoLibraryGenerationPromptHandoff.mergePromptText = neoLibraryMergePromptText;

async function neoLibraryUseGenerationPayload(options={}) {
  const promptText = trim(options.promptText || '');
  const usePrompt = !!options.usePrompt;
  const useImage = !!options.useImage;
  const imageTarget = options.imageTarget || 'img2img';
  const statusId = options.statusId || 'neo-library-caption-status';
  if (!usePrompt && !useImage) {
    setStatus(statusId, 'Pick Prompt, Image, or both first.', 'warn');
    return;
  }
  neoLibraryOpenGenerationTab();
  if (usePrompt && !promptText) {
    setStatus(statusId, 'There is no prompt text loaded to send.', 'warn');
    return;
  }
  if (useImage) {
    if (!options.imageSource) {
      setStatus(statusId, 'Pick an image destination and load an image first.', 'warn');
      return;
    }
    const file = await neoLibraryFetchImageAsFile(options.imageSource, options.imageName || 'reference.png');
    await neoLibraryRouteImageToGeneration(file, imageTarget);
  }
  if (usePrompt) {
    neoLibraryFlushPendingGenerationPrompt(promptText, 12);
    window.requestAnimationFrame(() => {
      try { neoLibraryEnsurePendingGenerationPrompt(promptText, 10, 90); } catch (_) {}
    });
    window.setTimeout(() => {
      try { neoLibraryEnsurePendingGenerationPrompt(promptText, 8, 120); } catch (_) {}
    }, 220);
    window.setTimeout(() => {
      try { neoLibraryEnsurePendingGenerationPrompt(promptText, 8, 140); } catch (_) {}
    }, 520);
    window.setTimeout(() => {
      try { neoLibraryEnsurePendingGenerationPrompt(promptText, 6, 180); } catch (_) {}
    }, 1100);
  }
  const summary = usePrompt && useImage ? 'Prompt and image sent to Generation.' : (usePrompt ? 'Prompt sent to Generation.' : 'Image sent to Generation.');
  setStatus(statusId, summary, 'success');
}

async function sendNeoLibraryCaptionToPromptStudio() {
  const text = $('neo-library-caption-text')?.value || '';
  await neoLibraryUseGenerationPayload({
    promptText: text,
    usePrompt: !!$('neo-library-caption-send-prompt')?.checked,
    useImage: !!$('neo-library-caption-send-image')?.checked,
    imageTarget: $('neo-library-caption-image-target')?.value || 'img2img',
    imageSource: $('neo-library-caption-image-url')?.value || $('neo-library-caption-preview')?.getAttribute('src') || '',
    imageName: (($('neo-library-caption-image')?.value || 'caption_reference').split(/[\/]/).pop()),
    statusId: 'neo-library-caption-status',
  });
}

async function duplicateNeoLibraryCaptionAsPrompt() {
  const captionId = $('neo-library-caption-id')?.value || '';
  if (!captionId) {
    setStatus('neo-library-caption-status', 'Load a caption first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('caption_id', captionId);
  fd.append('category', $('neo-library-caption-category').value || 'uncategorized');
  fd.append('prompt_name', `${$('neo-library-caption-editor-name').value || 'Caption'} Prompt`);
  try {
    const data = await safeFetchJson('/api/caption-to-prompt', { method:'POST', body:fd });
    await refreshNeoLibrarySummary();
    await refreshNeoLibraryPromptBrowser();
    if (typeof refreshSavedPromptNames === 'function') refreshSavedPromptNames();
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    setStatus('neo-library-caption-status', data.message || 'Prompt duplicated from caption.');
  } catch (e) {
    setStatus('neo-library-caption-status', e.message, 'error');
  }
}

async function updateNeoLibraryCaption() {
  const captionId = $('neo-library-caption-id')?.value || '';
  if (!captionId) {
    setStatus('neo-library-caption-status', 'Load a caption first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('caption_id', captionId);
  fd.append('category', $('neo-library-caption-category').value || 'uncategorized');
  fd.append('name', $('neo-library-caption-editor-name').value || 'Untitled Caption');
  fd.append('caption', $('neo-library-caption-text').value || '');
  fd.append('notes', $('neo-library-caption-notes').value || '');
  fd.append('model', $('neo-library-caption-editor-model').value || '');
  fd.append('prompt_style', $('neo-library-caption-editor-style').value || '');
  fd.append('component_type', $('neo-library-caption-editor-component').value || '');
  fd.append('detail_level', $('neo-library-caption-editor-detail').value || 'detailed');
  try {
    const data = await safeFetchJson('/api/update-caption', { method:'POST', body:fd });
    neoLibrarySetSummary(data.stats || {});
    await refreshNeoLibraryCaptionSync({ category: $('neo-library-caption-category').value || 'uncategorized', name: $('neo-library-caption-editor-name').value || '' });
    if (typeof refreshCaptionBrowser === 'function') refreshCaptionBrowser();
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    setStatus('neo-library-caption-status', data.message || 'Caption updated.');
  } catch (e) {
    setStatus('neo-library-caption-status', e.message, 'error');
  }
}

async function deleteNeoLibraryCaption() {
  const captionId = $('neo-library-caption-id')?.value || '';
  if (!captionId) {
    setStatus('neo-library-caption-status', 'Load a caption first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('caption_id', captionId);
  fd.append('category', $('neo-library-caption-category').value || '');
  fd.append('name', $('neo-library-caption-editor-name').value || '');
  try {
    const data = await safeFetchJson('/api/delete-caption', { method:'POST', body:fd });
    neoLibrarySetSummary(data.stats || {});
    refreshCategoryList(data.categories || initialCategories);
    await refreshNeoLibraryCaptionSync({ category: $('neo-library-caption-category').value || '' });
    if (typeof refreshCaptionBrowser === 'function') refreshCaptionBrowser();
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
    setStatus('neo-library-caption-status', data.message || 'Caption deleted.');
  } catch (e) {
    setStatus('neo-library-caption-status', e.message, 'error');
  }
}


function neoLibraryParseJsonObject(value, fallback={}) {
  if (!value) return fallback;
  if (typeof value === 'object') return value;
  try {
    const parsed = JSON.parse(String(value));
    return parsed && typeof parsed === 'object' ? parsed : fallback;
  } catch (_) {
    return fallback;
  }
}

function neoLibraryFirstPresent(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return '';
}

function neoLibraryDisplayValue(value, fallback='—') {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (Array.isArray(value)) return value.length ? `${value.length} item${value.length === 1 ? '' : 's'}` : fallback;
  if (typeof value === 'object') return Object.keys(value).length ? JSON.stringify(value) : fallback;
  return String(value);
}

function neoLibraryMetadataRows(rows) {
  return rows
    .filter(row => row && row[1] !== undefined && row[1] !== null && row[1] !== '')
    .map(([label, value]) => `<div class="neo-library-output-meta-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(neoLibraryDisplayValue(value))}</strong></div>`)
    .join('') || '<div class="mini-note">No visible metadata for this block.</div>';
}

function renderNeoLibraryOutputReuseMetadata(rec={}) {
  let target = $('neo-library-output-reuse-summary');
  if (!target) {
    const previewPane = document.querySelector('.neo-library-output-reuse-preview-pane') || document.querySelector('.neo-library-output-reuse-card');
    if (!previewPane) return;
    target = document.createElement('div');
    target.id = 'neo-library-output-reuse-summary';
    target.className = 'card-lite neo-library-output-reuse-summary';
    const lineageNode = $('neo-library-output-lineage');
    if (lineageNode && lineageNode.parentElement === previewPane) {
      previewPane.insertBefore(target, lineageNode);
    } else {
      previewPane.appendChild(target);
    }
  }
  const reuse = neoLibraryParseJsonObject(rec.reuse_metadata_json || rec.reuse_metadata || '{}');
  const workflow = neoLibraryParseJsonObject(rec.workflow_state_json || rec.workflow_state || reuse.workflow_state || '{}');
  const model = neoLibraryParseJsonObject(rec.model_family_json || rec.model_family_state || reuse.model_family_state || '{}');
  const generation = neoLibraryParseJsonObject(rec.generation_json || reuse.generation || '{}');
  const source = neoLibraryParseJsonObject(rec.source_metadata_json || rec.source_metadata || reuse.source || '{}');
  const extensions = neoLibraryParseJsonObject(rec.extension_metadata_json || rec.extension_metadata || reuse.external_extensions || '{}');
  const notesRaw = neoLibraryParseJsonObject(rec.compile_notes_json || rec.compile_notes || reuse.compile_notes || '[]', []);
  const notes = Array.isArray(notesRaw) ? notesRaw : [];
  const workflowBlock = neoLibraryParseJsonObject(workflow.workflow_state || workflow || '{}');
  const payload = neoLibraryParseJsonObject(rec.payload_json || rec.payload || reuse.payload || '{}');
  const main = neoLibraryParseJsonObject(rec.main_json || rec.main || reuse.main || '{}');
  const prompt = neoLibraryFirstPresent(
    rec.main_positive,
    reuse.prompt,
    reuse.positive_prompt,
    main.positive_box,
    main.prompt,
    payload.prompt,
    payload.positive_prompt,
    payload.main_positive
  );
  const negative = neoLibraryFirstPresent(
    rec.main_negative,
    reuse.negative_prompt,
    main.negative_box,
    main.negative_prompt,
    payload.negative_prompt,
    payload.main_negative
  );
  const familyLabel = neoLibraryFirstPresent(model.effective_family, model.raw_family, reuse.family, payload.family);
  const workflowMode = neoLibraryFirstPresent(workflowBlock.effective_mode, workflowBlock.raw_mode, workflowBlock.mode, generation.Mode);
  const modelRows = [
    ['Family', familyLabel],
    ['Model source', model.model_source],
    ['Family source', model.family_inference_source],
    ['Checkpoint', neoLibraryFirstPresent(generation.Checkpoint, generation.checkpoint, model.checkpoint)],
    ['GGUF UNet', model.gguf_unet],
    ['GGUF CLIP type', model.gguf_clip_type],
    ['CLIP mode', model.gguf_clip_mode],
    ['Primary CLIP', model.gguf_clip_primary],
    ['Secondary CLIP', model.gguf_clip_secondary],
    ['Qwen MMProj', model.gguf_mmproj],
    ['MMProj required', model.mmproj_required],
    ['MMProj source', model.mmproj_source],
    ['Qwen base size', model.qwen_outpaint_base_size],
    ['Qwen padding', model.qwen_outpaint_padding],
    ['Qwen effective size', model.qwen_outpaint_effective_size],
  ];
  const workflowRows = [
    ['Workflow', workflowMode],
    ['Raw mode', workflowBlock.raw_mode],
    ['Switch reason', workflowBlock.switch_reason],
    ['Source kind', workflowBlock.source_kind],
    ['Source ID', workflowBlock.source_id],
    ['Output policy', workflowBlock.output_policy],
    ['Validation', workflowBlock.validation_status],
  ];
  const generationRows = [
    ['Seed', neoLibraryFirstPresent(generation.Seed, generation.seed)],
    ['Sampler', neoLibraryFirstPresent(generation.Sampler, generation.sampler)],
    ['Scheduler', neoLibraryFirstPresent(generation.Scheduler, generation.scheduler)],
    ['Steps', neoLibraryFirstPresent(generation.Steps, generation.steps)],
    ['CFG', neoLibraryFirstPresent(generation['CFG scale'], generation.cfg)],
    ['Size', neoLibraryFirstPresent(generation.Size, generation.size)],
    ['Effective size', generation.effective_size],
    ['Denoise', neoLibraryFirstPresent(generation['Denoising strength'], generation.denoise)],
    ['VAE', neoLibraryFirstPresent(generation.VAE, generation.vae)],
  ];
  const sourceRows = [
    ['Source output ID', source.source_output_id],
    ['Source output', source.source_output ? 'recorded' : ''],
    ['Source image fields', source.source_image_fields ? Object.keys(source.source_image_fields || {}).length : ''],
    ['Extensions', Object.keys(extensions || {}).length ? `${Object.keys(extensions).length} block${Object.keys(extensions).length === 1 ? '' : 's'}` : ''],
  ];
  target.innerHTML = `
    <div class="neo-library-output-meta-head">
      <div>
        <div class="stat-title">Output reuse metadata</div>
        <div class="mini-note">Prompt, workflow, model-family, source, and extension metadata recovered from the output sidecar.</div>
      </div>
      <span class="timer-pill">${escapeHtml(familyLabel || 'metadata')}</span>
    </div>
    <div class="neo-library-output-meta-prompts">
      <div class="neo-library-output-meta-block neo-library-output-meta-block--prompt"><div class="neo-library-output-meta-title">Prompt</div><div class="neo-library-output-prompt-preview">${prompt ? escapeHtml(String(prompt).slice(0, 900)) + (String(prompt).length > 900 ? '…' : '') : '<span class="mini-note">No prompt recovered for this output.</span>'}</div></div>
      <div class="neo-library-output-meta-block neo-library-output-meta-block--prompt"><div class="neo-library-output-meta-title">Negative prompt</div><div class="neo-library-output-prompt-preview">${negative ? escapeHtml(String(negative).slice(0, 600)) + (String(negative).length > 600 ? '…' : '') : '<span class="mini-note">No negative prompt recovered.</span>'}</div></div>
    </div>
    <div class="neo-library-output-meta-grid">
      <div class="neo-library-output-meta-block"><div class="neo-library-output-meta-title">Workflow</div>${neoLibraryMetadataRows(workflowRows)}</div>
      <div class="neo-library-output-meta-block"><div class="neo-library-output-meta-title">Model family</div>${neoLibraryMetadataRows(modelRows)}</div>
      <div class="neo-library-output-meta-block"><div class="neo-library-output-meta-title">Generation</div>${neoLibraryMetadataRows(generationRows)}</div>
      <div class="neo-library-output-meta-block"><div class="neo-library-output-meta-title">Reuse source</div>${neoLibraryMetadataRows(sourceRows)}</div>
    </div>
    ${notes.length ? `<details class="neo-library-output-meta-block"><summary>Compile notes</summary><div class="neo-library-output-prompt-preview">${escapeHtml(notes.slice(0, 12).join('\n'))}</div></details>` : ''}
  `;
}

function renderNeoLibraryOutputPagination(total, shown, totalPages) {
  neoLibraryOutputTotalPages = Math.max(1, Number(totalPages) || 1);
  if ($('neo-library-output-page')) $('neo-library-output-page').textContent = `Page ${neoLibraryOutputPage} of ${neoLibraryOutputTotalPages}`;
  const pageSize = Number($('neo-library-output-page-size')?.value || 25);
  const start = total ? ((neoLibraryOutputPage - 1) * pageSize) + 1 : 0;
  const end = total ? start + Math.max(0, shown - 1) : 0;
  if ($('neo-library-output-summary')) $('neo-library-output-summary').textContent = `Showing ${start}-${end} of ${total}`;
  if ($('btn-neo-library-output-prev')) $('btn-neo-library-output-prev').disabled = neoLibraryOutputPage <= 1;
  if ($('btn-neo-library-output-next')) $('btn-neo-library-output-next').disabled = neoLibraryOutputPage >= neoLibraryOutputTotalPages;
}

function loadNeoLibraryOutputRecord(record, mode='', name='') {
  const rec = record || {};
  neoLibraryCurrentOutputRecord = rec;
  neoLibraryCurrentOutputMode = mode || neoLibraryCurrentOutputMode || '';
  neoLibraryCurrentOutputName = name || neoLibraryCurrentOutputName || '';
  if ($('neo-library-output-preview')) {
    if (rec.image_url) $('neo-library-output-preview').src = rec.image_url;
    else $('neo-library-output-preview').removeAttribute('src');
  }
  $('neo-library-output-positive').value = rec.main_positive || '';
  $('neo-library-output-negative').value = rec.main_negative || '';
  $('neo-library-output-adetailer-positive').value = rec.adetailer_positive || '';
  $('neo-library-output-adetailer-negative').value = rec.adetailer_negative || '';
  $('neo-library-output-generation').value = rec.generation_json || '{}';
  $('neo-library-output-controlnet').value = rec.controlnet_json || '{}';
  $('neo-library-output-extra').value = rec.extra_json || '{}';
  $('neo-library-output-raw').value = rec.raw_parameters || '';
  if ($('neo-library-output-workflow-state')) $('neo-library-output-workflow-state').value = rec.workflow_state_json || '{}';
  if ($('neo-library-output-model-family')) $('neo-library-output-model-family').value = rec.model_family_json || '{}';
  if ($('neo-library-output-reuse-metadata')) $('neo-library-output-reuse-metadata').value = rec.reuse_metadata_json || '{}';
  if ($('neo-library-output-source-metadata')) $('neo-library-output-source-metadata').value = rec.source_metadata_json || '{}';
  if ($('neo-library-output-extension-metadata')) $('neo-library-output-extension-metadata').value = rec.extension_metadata_json || '{}';
  if ($('neo-library-output-compile-notes')) $('neo-library-output-compile-notes').value = rec.compile_notes_json || '[]';
  renderNeoLibraryOutputReuseMetadata(rec);
  $('neo-library-output-preview').dataset.imageUrl = rec.image_url || '';
  const replayNote = $('neo-library-output-replay-note');
  if (replayNote) {
    const bits = [];
    if (String(rec.generation_json || '').trim() && String(rec.generation_json || '').trim() !== '{}') bits.push('generation metadata ready');
    if (String(rec.extra_json || '').trim() && String(rec.extra_json || '').trim() !== '{}') bits.push('finish metadata ready');
    if (String(rec.controlnet_json || '').trim() && String(rec.controlnet_json || '').trim() !== '{}') bits.push('control/reference metadata ready');
    replayNote.textContent = bits.length
      ? `Replay from this output: ${bits.join(' · ')}.`
      : 'This output has prompts and preview data, but no richer metadata blocks were detected yet.';
  }
  if (name && $('neo-library-output-name')) $('neo-library-output-name').value = name;
  renderNeoLibraryOutputLineage();
}


function buildNeoLibraryOutputPreviewItem() {
  const imageUrl = $('neo-library-output-preview')?.dataset.imageUrl || $('neo-library-output-preview')?.getAttribute('src') || '';
  const rawName = neoLibraryCurrentOutputName || $('neo-library-output-name')?.value || 'library_output.png';
  const prettyName = String(rawName || 'library_output.png').split(/[\/]/).pop() || 'library_output.png';
  if (!imageUrl) return null;
  return {
    filename: prettyName,
    saved_filename: prettyName,
    saved_path: neoLibraryCurrentOutputRecord?.saved_path || rawName || prettyName,
    view_url: imageUrl,
    imported: true,
    source: 'library',
  };
}

function parseNeoLibraryOutputJson(text) {
  const raw = String(text || '').trim();
  if (!raw || raw === '{}' || raw === 'null') return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_) {
    return {};
  }
}

function openGenerationWorkspaceForReplay(tab='core') {
  document.querySelector('[data-main-tab="generation"]')?.click();
  try {
    if (typeof window.neoGenerationSetSetupTab === 'function') window.neoGenerationSetSetupTab(tab);
  } catch (_) {}
}

function buildNeoLibraryOutputReplayPatch(kind='generation') {
  const generationMeta = parseNeoLibraryOutputJson($('neo-library-output-generation')?.value || '');
  const controlnetMeta = parseNeoLibraryOutputJson($('neo-library-output-controlnet')?.value || '');
  const extraMeta = parseNeoLibraryOutputJson($('neo-library-output-extra')?.value || '');
  const patch = {};
  if (kind === 'generation' || kind === 'rebuild') {
    Object.assign(patch, generationMeta || {});
    patch.positive = $('neo-library-output-positive')?.value || patch.positive || '';
    patch.negative = $('neo-library-output-negative')?.value || patch.negative || '';
  }
  if (kind === 'finish' || kind === 'rebuild') {
    Object.assign(patch, controlnetMeta || {}, extraMeta || {});
    if ($('neo-library-output-adetailer-positive')) patch.detailer_positive = $('neo-library-output-adetailer-positive').value || patch.detailer_positive || '';
    if ($('neo-library-output-adetailer-negative')) patch.detailer_negative = $('neo-library-output-adetailer-negative').value || patch.detailer_negative || '';
  }
  return patch;
}

function applyNeoLibraryOutputReplay(kind='generation') {
  const rt = window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null;
  if (!rt?.getCurrentDraft || !rt?.applyDraft) {
    setStatus('neo-library-output-status', 'Generation workspace is not ready for metadata replay right now.', 'warn');
    return false;
  }
  const patch = buildNeoLibraryOutputReplayPatch(kind);
  const hasData = Object.keys(patch || {}).length > 0;
  if (!hasData) {
    setStatus('neo-library-output-status', 'No reusable metadata was found on this output yet.', 'warn');
    return false;
  }
  const draft = rt.getCurrentDraft() || {};
  const merged = { ...draft, ...patch };
  rt.applyDraft(merged);
  if (kind === 'finish') {
    openGenerationWorkspaceForReplay('enhance');
    setStatus('neo-library-output-status', 'Applied finish / restore metadata into Generation.', 'success');
  } else if (kind === 'rebuild') {
    loadNeoLibraryOutputIntoPreview();
    openGenerationWorkspaceForReplay('core');
    setStatus('neo-library-output-status', 'Rebuilt the Generation draft from this output metadata and loaded the image into preview.', 'success');
  } else {
    openGenerationWorkspaceForReplay('core');
    setStatus('neo-library-output-status', 'Applied generation settings from this output metadata.', 'success');
  }
  return true;
}

function setNeoLibraryOutputDebug(message, tone='') {
  const host = $('neo-library-output-debug');
  if (host) host.textContent = `Debug trace: ${String(message || '').trim() || 'idle'}`;
  console.log('[Neo Output Reuse]', message);
  if (tone) setStatus('neo-library-output-status', String(message || ''), tone);
}
window.neoLibraryDebugLoadOutputPreview = function() {
  setNeoLibraryOutputDebug('Inline click handler reached. Starting load…');
  loadNeoLibraryOutputIntoPreview();
};

function renderNeoLibraryOutputLineage() {
  const host = $('neo-library-output-lineage');
  if (!host) return;
  const rt = window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null;
  const output = buildNeoLibraryOutputPreviewItem();
  if (!output || !rt?.getOutputLineage) {
    host.textContent = 'No lineage recorded for this output yet.';
    return;
  }
  const lineage = rt.getOutputLineage(output) || { chain: [], children: [] };
  const chain = Array.isArray(lineage.chain) ? lineage.chain : [];
  const children = Array.isArray(lineage.children) ? lineage.children : [];
  if (!chain.length && !children.length) {
    host.textContent = 'No lineage recorded for this output yet.';
    return;
  }
  const chainBits = chain.length ? chain.map((entry, index) => `${index === 0 ? 'Base' : (entry.stage || 'Pass')} · ${entry.output?.saved_filename || entry.output?.filename || 'Output'}`).join(' → ') : 'No ancestry recorded';
  const childBits = children.length ? children.map(entry => `${entry.stage || 'Derived pass'} · ${entry.output?.saved_filename || entry.output?.filename || 'Output'}`).join(' | ') : 'No child passes yet';
  host.textContent = `Lineage: ${chainBits} — Children: ${childBits}`;
}

function forceNeoLibraryOutputPreviewIntoShell(output) {
  if (!output?.view_url) return;
  const img = $('generation-live-preview');
  if (img) {
    img.src = output.view_url;
    img.style.display = '';
    img.classList.remove('hidden');
  }
  const details = $('generation-output-details');
  if (details) {
    details.innerHTML = `<div class="mini-note">${escapeHtml(output.saved_filename || output.filename || 'Output')}</div>${output.saved_path ? `<div class="mini-note generation-path-chip">${escapeHtml(output.saved_path)}</div>` : ''}`;
  }
}

function loadNeoLibraryOutputIntoPreview() {
  try {
    setNeoLibraryOutputDebug('Load as output preview clicked. Building preview item…');
    const output = buildNeoLibraryOutputPreviewItem();
    const rt = window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null;
    if (!output?.view_url) {
      setNeoLibraryOutputDebug('Stopped early because the selected Output Reuse record has no image URL.', 'warn');
      return;
    }
    setNeoLibraryOutputDebug(`Preview item ready: ${output.saved_filename || output.filename || 'output'} | runtime ${rt?.activateOutput ? 'found' : 'missing'}`);
    if (rt?.activateOutput) {
      rt.activateOutput({ ...output, imported: true }, { label: `Library output · ${output.saved_filename || output.filename || 'Output'}` });
      setNeoLibraryOutputDebug('Runtime activateOutput() fired. Applying direct shell preview fallback too…');
    }
    forceNeoLibraryOutputPreviewIntoShell(output);
    renderNeoLibraryOutputLineage();
    if (typeof window.neoGenerationSetSetupTab === 'function') {
      window.neoGenerationSetSetupTab('output');
      setNeoLibraryOutputDebug('Switched to Results through neoGenerationSetSetupTab().', 'success');
    } else {
      document.querySelector('[data-generation-setup-tab="output"]')?.click();
      setNeoLibraryOutputDebug('Switched to Results through direct tab click fallback.', 'success');
    }
  } catch (e) {
    console.error('[Neo Output Reuse] load preview failed', e);
    setNeoLibraryOutputDebug(e?.message || 'Load as output preview failed unexpectedly.', 'error');
  }
}

async function refreshNeoLibraryOutputBrowser(options={}) {
  const { resetPage=false, keepSelection=false } = options || {};
  if (resetPage) neoLibraryOutputPage = 1;
  const mode = $('neo-library-output-mode')?.value || 'txt2img';
  const pageSize = $('neo-library-output-page-size')?.value || '25';
  const params = new URLSearchParams({ mode, page: String(neoLibraryOutputPage), page_size: String(pageSize) });
  try {
    setStatus('neo-library-output-status', 'Loading outputs...');
    const data = await safeFetchJson(`/api/neo-library/output-browser?${params.toString()}`);
    const selectedName = keepSelection ? ($('neo-library-output-name')?.value || '') : '';
    const entries = data.entries || [];
    fillSelectFromList('neo-library-output-name', entries, selectedName && entries.includes(selectedName) ? selectedName : (entries[0] || ''), 'Select output image');
    neoLibraryOutputPage = Math.max(1, Number(data.page) || neoLibraryOutputPage || 1);
    renderNeoLibraryOutputPagination(Number(data.total || 0), entries.length, Number(data.total_pages || 1));
    if ($('neo-library-output-folder-note')) $('neo-library-output-folder-note').textContent = `Output folder: ${data.output_root || '—'}`;
    setStatus('neo-library-output-status', Number(data.total || 0) ? `${data.total} output image(s) found.` : 'No output images found in this folder.', Number(data.total || 0) ? '' : 'warn');
    const name = $('neo-library-output-name')?.value || '';
    if (name) await openNeoLibraryOutputRecord(mode, name);
    else loadNeoLibraryOutputRecord(null);
  } catch (e) {
    setStatus('neo-library-output-status', e.message, 'error');
  }
}

async function openNeoLibraryOutputRecord(mode, name) {
  if (!name) {
    loadNeoLibraryOutputRecord(null);
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/output-record?mode=${encodeURIComponent(mode)}&name=${encodeURIComponent(name)}`);
    loadNeoLibraryOutputRecord(data.record || {}, mode, name);
  } catch (e) {
    setStatus('neo-library-output-status', e.message, 'error');
  }
}

function neoLibraryLoraSummary(parsed) {
  const rows = [];
  (parsed?.loras || []).forEach(item => {
    const bits = [item.registry_name || item.name || 'unknown'];
    if (item.weight !== undefined && item.weight !== null && item.weight !== '') bits.push(`weight ${item.weight}`);
    if (item.registry_category) bits.push(item.registry_category);
    rows.push(bits.join(' · '));
  });
  (parsed?.textual_inversions || []).forEach(item => {
    const bits = [item.name || 'unknown', 'embedding'];
    if (item.weight !== undefined && item.weight !== null && item.weight !== '') bits.push(`weight ${item.weight}`);
    rows.push(bits.join(' · '));
  });
  return rows.join('\n') || 'No LoRAs or embeddings detected.';
}

function applyNeoLibraryParsedMetadata(parsed, compareNote='') {
  neoLibraryOutputParsed = parsed || null;
  $('neo-library-output-upload-positive').value = parsed?.positive_prompt || '';
  $('neo-library-output-upload-negative').value = parsed?.negative_prompt || '';
  $('neo-library-output-settings-summary').value = parsed?.settings_summary || 'No generation summary found.';
  $('neo-library-output-loras').value = neoLibraryLoraSummary(parsed || {});
  $('neo-library-output-rebuilt').value = parsed?.clean_rebuild_prompt || '';
  $('neo-library-output-compare-note').value = compareNote || '';
  $('neo-library-output-metadata-json').value = parsed ? JSON.stringify(parsed) : '';
  if (!$('neo-library-output-save-name').value) {
    const stem = String(parsed?.source_filename || 'Recovered Prompt').replace(/\.[^.]+$/, '');
    $('neo-library-output-save-name').value = stem;
  }
}

function summarizeMetadataDiff(diff) {
  if (!diff) return '';
  const lines = [];
  if (diff.positive_changed) lines.push('- Positive prompt changed');
  if (diff.negative_changed) lines.push('- Negative prompt changed');
  (diff.settings_diff || []).slice(0, 12).forEach(row => lines.push(`- ${row.key}: ${row.primary} → ${row.secondary}`));
  if ((diff.settings_diff || []).length > 12) lines.push(`- ...and ${(diff.settings_diff || []).length - 12} more setting differences`);
  if ((diff.loras_only_primary || []).length) lines.push(`- Only in primary: ${(diff.loras_only_primary || []).join(', ')}`);
  if ((diff.loras_only_secondary || []).length) lines.push(`- Only in secondary: ${(diff.loras_only_secondary || []).join(', ')}`);
  (diff.lora_weight_diff || []).slice(0, 12).forEach(row => lines.push(`- ${row.name}: ${row.primary_weight} → ${row.secondary_weight}`));
  return lines.join('\n') || 'No major metadata differences detected.';
}

async function inspectNeoLibraryUploadedOutput(compare=false) {
  const primary = $('neo-library-output-upload')?.files?.[0];
  const secondary = $('neo-library-output-compare-upload')?.files?.[0];
  if (!primary) {
    setStatus('neo-library-output-upload-status', 'Choose a primary output image first.', 'warn');
    return;
  }
  try {
    if (compare) {
      if (!secondary) {
        setStatus('neo-library-output-upload-status', 'Choose a second output image to compare.', 'warn');
        return;
      }
      const fd = new FormData();
      fd.append('primary_image', primary);
      fd.append('secondary_image', secondary);
      const data = await safeFetchJson('/api/compare-output-metadata', { method:'POST', body:fd });
      applyNeoLibraryParsedMetadata(data.primary || {}, summarizeMetadataDiff(data.diff || {}));
      setStatus('neo-library-output-upload-status', 'Compared both output images.');
    } else {
      const fd = new FormData();
      fd.append('image', primary);
      const data = await safeFetchJson('/api/inspect-output-metadata', { method:'POST', body:fd });
      applyNeoLibraryParsedMetadata(data.parsed || {}, '');
      setStatus('neo-library-output-upload-status', 'Metadata parsed from uploaded image.');
    }
  } catch (e) {
    setStatus('neo-library-output-upload-status', e.message, 'error');
  }
}

function cleanNeoLibraryOutputPrompt() {
  const rebuilt = trim($('neo-library-output-rebuilt')?.value || '') || trim($('neo-library-output-upload-positive')?.value || '');
  if (!rebuilt) {
    setStatus('neo-library-output-upload-status', 'Inspect an output image first.', 'warn');
    return;
  }
  const cleaned = rebuilt.split(',').map(x => trim(x)).filter(Boolean).filter((item, idx, arr) => arr.findIndex(v => v.toLowerCase() === item.toLowerCase()) === idx).join(', ');
  $('neo-library-output-rebuilt').value = cleaned;
  setStatus('neo-library-output-upload-status', 'Rebuilt prompt cleaned up.');
}

async function sendNeoLibraryRebuiltToPromptStudio() {
  const text = trim($('neo-library-output-rebuilt')?.value || '') || trim($('neo-library-output-upload-positive')?.value || '');
  const uploadFile = $('neo-library-output-upload')?.files?.[0] || null;
  await neoLibraryUseGenerationPayload({
    promptText: text,
    usePrompt: !!$('neo-library-output-upload-send-prompt')?.checked,
    useImage: !!$('neo-library-output-upload-send-image')?.checked,
    imageTarget: $('neo-library-output-upload-image-target')?.value || 'img2img',
    imageSource: uploadFile,
    imageName: uploadFile?.name || 'uploaded_output.png',
    statusId: 'neo-library-output-upload-status',
  });
}

async function sendNeoLibraryOutputPositiveToPromptStudio() {
  const text = trim($('neo-library-output-positive')?.value || '');
  const imageUrl = $('neo-library-output-preview')?.dataset.imageUrl || $('neo-library-output-preview')?.getAttribute('src') || '';
  await neoLibraryUseGenerationPayload({
    promptText: text,
    usePrompt: !!$('neo-library-output-send-prompt')?.checked,
    useImage: !!$('neo-library-output-send-image')?.checked,
    imageTarget: $('neo-library-output-image-target')?.value || 'img2img',
    imageSource: imageUrl,
    imageName: (($('neo-library-output-name')?.value || 'output_image').split(/[\/]/).pop()),
    statusId: 'neo-library-output-status',
  });
}

async function saveNeoLibraryOutputPrompt() {
  const payload = $('neo-library-output-metadata-json')?.value || '';
  if (!payload) {
    setStatus('neo-library-output-upload-status', 'Inspect an output image first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('metadata_json', payload);
  fd.append('name', $('neo-library-output-save-name')?.value || 'Recovered Prompt');
  fd.append('category', $('neo-library-output-save-category')?.value || 'uncategorized');
  fd.append('notes', $('neo-library-output-save-notes')?.value || '');
  fd.append('model', currentModel());
  try {
    const data = await safeFetchJson('/api/save-output-metadata-prompt', { method:'POST', body:fd });
    await refreshNeoLibrarySummary();
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
    if (typeof refreshSavedPromptNames === 'function') refreshSavedPromptNames();
    setStatus('neo-library-output-upload-status', data.message || 'Saved metadata as prompt.');
  } catch (e) {
    setStatus('neo-library-output-upload-status', e.message, 'error');
  }
}

async function saveNeoLibraryOutputCharacter() {
  const payload = $('neo-library-output-metadata-json')?.value || '';
  if (!payload) {
    setStatus('neo-library-output-upload-status', 'Inspect an output image first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('metadata_json', payload);
  fd.append('name', $('neo-library-output-save-name')?.value || 'Recovered Character');
  fd.append('notes', $('neo-library-output-save-notes')?.value || '');
  try {
    const data = await safeFetchJson('/api/save-output-metadata-character', { method:'POST', body:fd });
    setStatus('neo-library-output-upload-status', data.message || 'Saved metadata as character base.');
  } catch (e) {
    setStatus('neo-library-output-upload-status', e.message, 'error');
  }
}


function neoLibraryFillSimpleSelect(id, rows=[], selected='') {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  (rows || []).forEach(row => {
    const opt = document.createElement('option');
    if (typeof row === 'string') {
      opt.value = row;
      opt.textContent = row;
    } else {
      opt.value = row.value ?? row.id ?? row.label ?? '';
      opt.textContent = row.label ?? row.name ?? row.value ?? row.id ?? '';
    }
    el.appendChild(opt);
  });
  if (selected) el.value = selected;
  if (!el.value && el.options.length) el.value = el.options[0].value;
}

function neoLibraryAppendComposerText(id, addText, separator=', ') {
  const el = $(id);
  const add = trim(addText || '');
  if (!el || !add) return;
  const cur = trim(el.value || '');
  if (!cur) {
    el.value = add;
    el.dispatchEvent(new Event('input', { bubbles:true }));
    el.dispatchEvent(new Event('change', { bubbles:true }));
    return;
  }
  if (cur.toLowerCase().includes(add.toLowerCase())) return;
  el.value = `${cur}${separator}${add}`;
  el.dispatchEvent(new Event('input', { bubbles:true }));
  el.dispatchEvent(new Event('change', { bubbles:true }));
}

function neoLibraryAppendGenerationPromptText(target='positive', addText='', separator=', ') {
  const fieldId = String(target || 'positive').toLowerCase() === 'negative' ? 'generation-negative' : 'generation-positive';
  const el = $(fieldId);
  const add = trim(addText || '');
  if (!el) {
    throw new Error(`Could not find ${fieldId} in the Generation tab.`);
  }
  if (!add) return;
  const cur = trim(el.value || '');
  if (!cur) el.value = add;
  else if (!cur.toLowerCase().includes(add.toLowerCase())) el.value = `${cur}${separator}${add}`;
  el.dispatchEvent(new Event('input', { bubbles:true }));
  el.dispatchEvent(new Event('change', { bubbles:true }));
}

async function refreshNeoLibraryComposerCharacters(selectedName='') {
  try {
    const data = await safeFetchJson('/api/character-records');
    const entries = data.entries || [];
    neoLibraryFillSimpleSelect('neo-library-composer-character-select', entries.map(entry => ({ value: entry.label || entry.name || '', label: entry.label || entry.name || '' })), selectedName || $('neo-library-composer-character-select')?.value || '');
    if (!$('neo-library-composer-character-name')?.value && $('neo-library-composer-character-select')?.value) {
      $('neo-library-composer-character-name').value = $('neo-library-composer-character-select').value || '';
    }
    setStatus('neo-library-composer-character-status', entries.length ? `${entries.length} saved character(s) ready.` : 'No saved characters yet.');
  } catch (e) {
    setStatus('neo-library-composer-character-status', e.message, 'error');
  }
}

function neoLibraryCurrentCharacterSlot() {
  return $('neo-library-composer-character-slot')?.value || 'chr1';
}

function neoLibrarySetCharacterSlotContent(value) {
  const slot = neoLibraryCurrentCharacterSlot();
  neoLibraryComposerCharacterState[slot] = value || '';
  if ($('neo-library-composer-character-content')) $('neo-library-composer-character-content').value = value || '';
}

function neoLibraryCharacterSlotChanged() {
  const slot = neoLibraryCurrentCharacterSlot();
  if ($('neo-library-composer-character-content')) $('neo-library-composer-character-content').value = neoLibraryComposerCharacterState[slot] || '';
}

function neoLibraryCharacterContentEdited() {
  neoLibraryComposerCharacterState[neoLibraryCurrentCharacterSlot()] = $('neo-library-composer-character-content')?.value || '';
}

function neoLibraryNormalizePiece(s) {
  return String(s || '').trim().toLowerCase().replace(/[\s_-]+/g, '').replace(/[^a-z0-9]+/g, '');
}

function neoLibrarySplitCsv(s) {
  return String(s || '').split(',').map(v => v.trim()).filter(Boolean);
}

function neoLibraryAppendUniqueCsv(buf, add) {
  const bufItems = neoLibrarySplitCsv(buf);
  const addItems = neoLibrarySplitCsv(add);
  const seen = new Set(bufItems.map(neoLibraryNormalizePiece));
  const out = [...bufItems];
  addItems.forEach(it => {
    const n = neoLibraryNormalizePiece(it);
    if (!n || seen.has(n)) return;
    seen.add(n);
    out.push(it);
  });
  return out.join(', ').replace(/^,\s*|\s*,$/g, '').trim();
}

function neoLibraryComposerInsertCharacterIntoPositive(posPrompt, slot, insertMode, charText) {
  slot = (slot || 'chr1').trim().toLowerCase();
  insertMode = (insertMode || 'chrblock').trim().toLowerCase();
  charText = String(charText || '').trim().replace(/^,+|,+$/g, '');
  if (!charText) return { prompt: posPrompt || '', message: '⚠️ Nothing to insert.' };
  const marker = `((${slot}))`;
  const p = String(posPrompt || '');
  const injectAfterBreak = which => {
    const tokens = p.split(/(\bBREAK\b)/);
    const idxs = [];
    tokens.forEach((t, i) => { if (t === 'BREAK') idxs.push(i); });
    if (!idxs.length) return neoLibraryAppendUniqueCsv(p, charText);
    const idx = which === 'first' ? idxs[0] : idxs[idxs.length - 1];
    if (idx + 1 >= tokens.length) tokens.push('');
    const seg = String(tokens[idx + 1] || '').trim();
    const segNew = seg ? neoLibraryAppendUniqueCsv(charText, seg) : charText;
    tokens[idx + 1] = ` ${segNew.trim().replace(/^,+|,+$/g, '')} `;
    return tokens.join('');
  };
  let newp = p;
  if (insertMode === 'after_first_break' || insertMode === 'after_first') newp = injectAfterBreak('first');
  else if (insertMode === 'after_last_break' || insertMode === 'after_last') newp = injectAfterBreak('last');
  else if (insertMode === 'append_end' || insertMode === 'append') newp = neoLibraryAppendUniqueCsv(p, charText);
  else {
    if (p.includes(marker)) {
      const i = p.indexOf(marker) + marker.length;
      const rest = p.slice(i);
      const m = rest.search(/\bBREAK\b/);
      const j = i + (m >= 0 ? m : rest.length);
      const seg = p.slice(i, j);
      const segNew = neoLibraryAppendUniqueCsv(seg, charText);
      newp = `${p.slice(0, i)}${segNew && !segNew.startsWith(' ') ? ' ' : ''}${segNew.trim()}${p.slice(j)}`;
    } else {
      const block = `${marker} ${charText} BREAK`;
      newp = p.trim() ? `${p.replace(/\s+$/, '')}
${block}` : block;
    }
  }
  newp = newp.replace(/\s+,/g, ',').replace(/,\s*,+/g, ', ').replace(/\s{2,}/g, ' ').trim();
  return { prompt: newp, message: '✅ Inserted.' };
}

function neoLibrarySelectedCharacterItem() {
  const raw = $('neo-library-composer-character-item')?.value || '';
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function neoLibraryRenderCharacterItemPreview() {
  const rec = neoLibrarySelectedCharacterItem();
  const box = $('neo-library-composer-character-item-preview');
  if (!box) return;
  if (!rec || !rec.name) {
    box.textContent = '';
    return;
  }
  const bits = [rec.name];
  if (rec.subcategory) bits.push(`Subcategory: ${rec.subcategory}`);
  if ((rec.aliases || []).length) bits.push(`Aliases: ${(rec.aliases || []).join(', ')}`);
  if (rec.desc) bits.push(rec.desc);
  box.textContent = bits.join(' • ');
}

async function refreshNeoLibraryComposerCharacterBuilder(options={}) {
  const { keepSelection=true } = options || {};
  const previousItem = keepSelection ? ($('neo-library-composer-character-item')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('gender', $('neo-library-composer-character-gender')?.value || 'male');
    params.set('era', $('neo-library-composer-character-era')?.value || 'any');
    params.set('show_restricted', $('neo-library-composer-character-show-restricted')?.checked ? 'true' : 'false');
    params.set('section', $('neo-library-composer-character-section')?.value || '');
    params.set('library', $('neo-library-composer-character-library')?.value || '');
    params.set('query', trim($('neo-library-composer-character-search')?.value || ''));
    const data = await safeFetchJson(`/api/neo-library/composer-character-builder-data?${params.toString()}`);
    neoLibraryFillSimpleSelect('neo-library-composer-character-section', (data.sections || []).map(v => ({ value:v, label:v.replace(/_/g, ' ') })), data.selected_section || '');
    neoLibraryFillSimpleSelect('neo-library-composer-character-library', (data.libraries || []).map(v => ({ value:v, label:v.replace(/_/g, ' ') })), data.selected_library || '');
    neoLibraryComposerCharacterItems = data.items || [];
    neoLibraryFillSimpleSelect('neo-library-composer-character-item', neoLibraryComposerCharacterItems.map(item => ({ value:item.value, label:item.label })), previousItem || '');
    neoLibraryRenderCharacterItemPreview();
    setStatus('neo-library-composer-character-status', neoLibraryComposerCharacterItems.length ? `${data.total || neoLibraryComposerCharacterItems.length} item(s) available.` : 'No items matched this character library/search.', neoLibraryComposerCharacterItems.length ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-composer-character-status', e.message, 'error');
  }
}

function addNeoLibraryComposerCharacterItem() {
  const rec = neoLibrarySelectedCharacterItem();
  if (!rec || !rec.name) {
    setStatus('neo-library-composer-character-status', 'Pick an item first.', 'warn');
    return;
  }
  const includeDesc = !!$('neo-library-composer-character-include-desc')?.checked;
  const rep = includeDesc && rec.desc ? `${rec.name}, ${rec.desc}` : rec.name;
  const current = $('neo-library-composer-character-content')?.value || '';
  const mode = $('neo-library-composer-character-pick-mode')?.value || 'add';
  const out = mode === 'replace' || !trim(current) ? rep : neoLibraryAppendUniqueCsv(current, rep);
  neoLibrarySetCharacterSlotContent(out);
  setStatus('neo-library-composer-character-status', 'Added to the current character slot.');
}

function clearNeoLibraryComposerCharacterSlot() {
  neoLibrarySetCharacterSlotContent('');
  setStatus('neo-library-composer-character-status', 'Cleared the current character slot.');
}

async function loadNeoLibraryComposerCharacter() {
  const name = trim($('neo-library-composer-character-select')?.value || $('neo-library-composer-character-name')?.value || '');
  if (!name) {
    setStatus('neo-library-composer-character-status', 'Pick a saved character first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/character-record?name=${encodeURIComponent(name)}`);
    const rec = data.record || {};
    if ($('neo-library-composer-character-select')) $('neo-library-composer-character-select').value = rec.name || name;
    if ($('neo-library-composer-character-name')) $('neo-library-composer-character-name').value = rec.name || name;
    neoLibrarySetCharacterSlotContent(rec.content || '');
    setStatus('neo-library-composer-character-status', `Loaded '${rec.name || name}' into ${neoLibraryCurrentCharacterSlot()}.`);
  } catch (e) {
    setStatus('neo-library-composer-character-status', e.message, 'error');
  }
}

async function saveNeoLibraryComposerCharacter() {
  const name = trim($('neo-library-composer-character-name')?.value || $('neo-library-composer-character-select')?.value || '');
  const content = $('neo-library-composer-character-content')?.value || '';
  if (!name) {
    setStatus('neo-library-composer-character-status', 'Enter a character name first.', 'warn');
    return;
  }
  if (!trim(content)) {
    setStatus('neo-library-composer-character-status', 'Nothing to save.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('name', name);
  fd.append('content', content);
  try {
    const data = await safeFetchJson('/api/save-character', { method:'POST', body:fd });
    const finalName = data.record?.name || name;
    if ($('neo-library-composer-character-name')) $('neo-library-composer-character-name').value = finalName;
    await refreshNeoLibraryComposerCharacters(finalName);
    if (typeof refreshSavedCharacters === 'function') refreshSavedCharacters(finalName);
    if (typeof refreshBundleSupportData === 'function') refreshBundleSupportData();
    setStatus('neo-library-composer-character-status', data.message || `Saved '${finalName}'.`);
  } catch (e) {
    setStatus('neo-library-composer-character-status', e.message, 'error');
  }
}

async function deleteNeoLibraryComposerCharacter() {
  const name = trim($('neo-library-composer-character-select')?.value || $('neo-library-composer-character-name')?.value || '');
  if (!name) {
    setStatus('neo-library-composer-character-status', 'Pick a saved character first.', 'warn');
    return;
  }
  if (!confirm('Delete the selected character?')) return;
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/delete-character', { method:'POST', body:fd });
    if ($('neo-library-composer-character-name')) $('neo-library-composer-character-name').value = '';
    neoLibrarySetCharacterSlotContent('');
    await refreshNeoLibraryComposerCharacters('');
    if (typeof refreshSavedCharacters === 'function') refreshSavedCharacters('');
    if (typeof refreshBundleSupportData === 'function') refreshBundleSupportData();
    setStatus('neo-library-composer-character-status', data.message || 'Character deleted.');
  } catch (e) {
    setStatus('neo-library-composer-character-status', e.message, 'error');
  }
}

function useNeoLibraryComposerCharacterInPositive() {
  const content = trim($('neo-library-composer-character-content')?.value || '');
  if (!content) {
    setStatus('neo-library-composer-character-status', 'No character content to insert.', 'warn');
    return;
  }
  const basePrompt = $('generation-positive')?.value || '';
  const result = neoLibraryComposerInsertCharacterIntoPositive(
    basePrompt,
    neoLibraryCurrentCharacterSlot(),
    $('neo-library-composer-character-insert-mode')?.value || 'chrblock',
    content,
  );
  const target = $('generation-positive');
  if (!target) {
    setStatus('neo-library-composer-character-status', 'Could not find the main generation prompt box.', 'error');
    return;
  }
  target.value = result.prompt || '';
  target.dispatchEvent(new Event('input', { bubbles:true }));
  target.dispatchEvent(new Event('change', { bubbles:true }));
  setStatus('neo-library-composer-character-status', result.message || 'Character inserted into the main generation prompt.');
}
window.useNeoLibraryComposerCharacterInPositive = useNeoLibraryComposerCharacterInPositive;

function linkNeoLibraryComposerCharacterToBundle() {
  const name = trim($('neo-library-composer-character-name')?.value || $('neo-library-composer-character-select')?.value || '');
  if (!name) {
    setStatus('neo-library-composer-character-status', 'Pick or save a character first.', 'warn');
    return;
  }
  if ($('bundle-character')) $('bundle-character').value = name;
  setStatus('neo-library-composer-character-status', 'Bundle linked to the selected character.');
}

async function refreshNeoLibraryComposerPresetBrowser(options={}) {
  const { keepSelection=true } = options || {};
  const previous = keepSelection ? (neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('query', trim($('neo-library-composer-preset-search')?.value || ''));
    params.set('browse_cat', $('neo-library-composer-preset-browse-category')?.value || 'all');
    const data = await safeFetchJson(`/api/neo-library/composer-prompt-presets?${params.toString()}`);
    neoLibraryFillSimpleSelect('neo-library-composer-preset-browse-category', (data.categories || []).map(v => ({ value:v, label:v })), $('neo-library-composer-preset-browse-category')?.value || 'all');
    neoLibraryFillSimpleSelect('neo-library-composer-preset-select', data.entries || [], previous || '');
    neoLibraryFillSimpleSelect('neo-library-composer-preset-compare', data.compare_entries || [], $('neo-library-composer-preset-compare')?.value || '');
    neoLibraryFillSimpleSelect('neo-library-composer-preset-category', (data.categories || []).filter(v => v !== 'all').map(v => ({ value:v, label:v })), $('neo-library-composer-preset-category')?.value || 'uncategorized');
    if ((data.entries || []).length) {
      const current = $('neo-library-composer-preset-select')?.value || '';
      if (current) {
        neoLibraryComposerPresetSelectedId = current;
        await loadNeoLibraryComposerPresetRecord(current);
      }
    } else {
      neoLibraryComposerPresetSelectedId = '';
      setStatus('neo-library-composer-preset-status', 'No saved prompts matched the current filters.', 'warn');
    }
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function loadNeoLibraryComposerPresetRecord(pid) {
  const selected = pid || $('neo-library-composer-preset-select')?.value || '';
  if (!selected) return;
  try {
    const data = await safeFetchJson(`/api/neo-library/composer-prompt-preset-record?pid=${encodeURIComponent(selected)}`);
    const rec = data.record || {};
    neoLibraryComposerPresetSelectedId = selected;
    if ($('neo-library-composer-preset-title')) $('neo-library-composer-preset-title').value = rec.title || '';
    neoLibraryFillSimpleSelect('neo-library-composer-preset-category', (data.categories || []).map(v => ({ value:v, label:v })), rec.category || 'uncategorized');
    if ($('neo-library-composer-preset-category-new')) $('neo-library-composer-preset-category-new').value = '';
    if ($('neo-library-composer-preset-notes')) $('neo-library-composer-preset-notes').value = rec.notes || '';
    if ($('neo-library-composer-preset-group')) $('neo-library-composer-preset-group').value = rec.group || '';
    if ($('neo-library-composer-preset-favorite')) $('neo-library-composer-preset-favorite').checked = !!rec.favorite;
    if ($('neo-library-composer-preset-meta')) $('neo-library-composer-preset-meta').textContent = rec.meta_text || '';
    setStatus('neo-library-composer-preset-status', 'Saved prompt loaded.');
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

function neoLibraryComposerPresetFormData(includePid=false) {
  const fd = new FormData();
  if (includePid) fd.append('pid', neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '');
  fd.append('title', $('neo-library-composer-preset-title')?.value || 'Untitled');
  fd.append('positive', $('bundle-positive')?.value || '');
  fd.append('negative', $('bundle-negative')?.value || '');
  fd.append('category', $('neo-library-composer-preset-category')?.value || 'uncategorized');
  fd.append('new_category', $('neo-library-composer-preset-category-new')?.value || '');
  fd.append('notes', $('neo-library-composer-preset-notes')?.value || '');
  fd.append('group', $('neo-library-composer-preset-group')?.value || '');
  fd.append('favorite', $('neo-library-composer-preset-favorite')?.checked ? 'true' : 'false');
  return fd;
}

async function saveNeoLibraryComposerPresetNew() {
  try {
    const data = await safeFetchJson('/api/neo-library/composer-prompt-preset-save-new', { method:'POST', body: neoLibraryComposerPresetFormData(false) });
    setStatus('neo-library-composer-preset-status', data.message || 'Saved new prompt.');
    await refreshNeoLibraryComposerPresetBrowser({ keepSelection:false });
    if (data.pid) await loadNeoLibraryComposerPresetRecord(data.pid);
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function updateNeoLibraryComposerPreset() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson('/api/neo-library/composer-prompt-preset-update', { method:'POST', body: neoLibraryComposerPresetFormData(true) });
    setStatus('neo-library-composer-preset-status', data.message || 'Updated saved prompt.');
    await refreshNeoLibraryComposerPresetBrowser({ keepSelection:true });
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function deleteNeoLibraryComposerPreset() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  if (!confirm('Delete the selected saved prompt?')) return;
  const fd = new FormData();
  fd.append('pid', pid);
  try {
    const data = await safeFetchJson('/api/neo-library/composer-prompt-preset-delete', { method:'POST', body: fd });
    neoLibraryComposerPresetSelectedId = '';
    if ($('neo-library-composer-preset-meta')) $('neo-library-composer-preset-meta').textContent = '';
    if ($('neo-library-composer-preset-compare-output')) $('neo-library-composer-preset-compare-output').classList.add('hidden');
    setStatus('neo-library-composer-preset-status', data.message || 'Deleted saved prompt.');
    await refreshNeoLibraryComposerPresetBrowser({ keepSelection:false });
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function duplicateNeoLibraryComposerPreset() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('pid', pid);
  try {
    const data = await safeFetchJson('/api/neo-library/composer-prompt-preset-duplicate', { method:'POST', body: fd });
    setStatus('neo-library-composer-preset-status', data.message || 'Duplicated preset.');
    await refreshNeoLibraryComposerPresetBrowser({ keepSelection:false });
    if (data.pid) await loadNeoLibraryComposerPresetRecord(data.pid);
    await refreshNeoLibraryPromptBrowser({ resetPage:true });
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function toggleFavoriteNeoLibraryComposerPreset() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('pid', pid);
  try {
    const data = await safeFetchJson('/api/neo-library/composer-prompt-preset-toggle-favorite', { method:'POST', body: fd });
    if ($('neo-library-composer-preset-favorite')) $('neo-library-composer-preset-favorite').checked = !!data.favorite;
    if ($('neo-library-composer-preset-meta')) $('neo-library-composer-preset-meta').textContent = data.meta_text || '';
    setStatus('neo-library-composer-preset-status', data.favorite ? 'Favorited.' : 'Removed from favorites.');
    await refreshNeoLibraryComposerPresetBrowser({ keepSelection:true });
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function compareNeoLibraryComposerPresets() {
  const pidA = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  const pidB = $('neo-library-composer-preset-compare')?.value || '';
  if (!pidA || !pidB) {
    setStatus('neo-library-composer-preset-status', 'Pick two saved prompts to compare.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/composer-prompt-preset-compare?pid_a=${encodeURIComponent(pidA)}&pid_b=${encodeURIComponent(pidB)}`);
    const cmp = data.comparison || {};
    const box = $('neo-library-composer-preset-compare-output');
    if (box) {
      if (!cmp.ok) {
        box.textContent = cmp.message || 'Compare failed.';
      } else if (!(cmp.differences || []).length) {
        box.textContent = `${cmp.title_a || 'A'} and ${cmp.title_b || 'B'} match on tracked fields.`;
      } else {
        box.textContent = `${cmp.title_a || 'A'} vs ${cmp.title_b || 'B'}\n` + (cmp.differences || []).slice(0, 8).map(row => `- ${row.field}: differs`).join('\n');
      }
      box.classList.remove('hidden');
    }
    setStatus('neo-library-composer-preset-status', cmp.ok ? 'Compare complete.' : (cmp.message || 'Compare failed.'), cmp.ok ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function exportNeoLibraryComposerPreset() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/composer-prompt-preset-export?pid=${encodeURIComponent(pid)}`);
    const payload = data.payload || {};
    const title = ((payload.prompt_preset || {}).title || 'preset').replace(/[\/]+/g, '_');
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.slice(0,80)}__single_preset.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setStatus('neo-library-composer-preset-status', 'Preset exported.');
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

async function loadNeoLibraryComposerPresetIntoComposer() {
  const pid = neoLibraryComposerPresetSelectedId || $('neo-library-composer-preset-select')?.value || '';
  if (!pid) {
    setStatus('neo-library-composer-preset-status', 'Select a saved prompt first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/composer-prompt-preset-record?pid=${encodeURIComponent(pid)}`);
    const rec = data.record || {};
    if ($('bundle-positive')) $('bundle-positive').value = rec.positive || '';
    if ($('bundle-negative')) $('bundle-negative').value = rec.negative || '';
    if ($('bundle-name') && !trim($('bundle-name').value || '')) $('bundle-name').value = rec.title || 'Prompt Composer Draft';
    if ($('bundle-style-notes') && !trim($('bundle-style-notes').value || '') && rec.notes) $('bundle-style-notes').value = rec.notes || '';
    if ($('neo-library-composer-preset-title')) $('neo-library-composer-preset-title').value = rec.title || '';
    if ($('neo-library-composer-preset-notes')) $('neo-library-composer-preset-notes').value = rec.notes || '';
    setStatus('neo-library-composer-preset-status', 'Saved prompt loaded into Prompt Composer.');
  } catch (e) {
    setStatus('neo-library-composer-preset-status', e.message, 'error');
  }
}

function syncNeoLibraryComposerLoraStrength() {
  const kind = $('neo-library-composer-lora-kind')?.value || 'lora';
  if ($('neo-library-composer-lora-strength')) $('neo-library-composer-lora-strength').disabled = kind === 'ti';
}

async function refreshNeoLibraryComposerLoraBrowser(options={}) {
  const { keepSelection=false } = options || {};
  const previousId = keepSelection ? ($('neo-library-composer-lora-item')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('kind', $('neo-library-composer-lora-kind')?.value || 'lora');
    params.set('query', trim($('neo-library-composer-lora-search')?.value || ''));
    params.set('category', $('neo-library-composer-lora-category')?.value || 'all');
    params.set('base_model', $('neo-library-composer-lora-base-model')?.value || 'all');
    params.set('style_category', $('neo-library-composer-lora-style')?.value || 'all');
    setStatus('neo-library-composer-lora-status', 'Reading LoRA / TI registry...');
    const data = await safeFetchJson(`/api/neo-library/lora-browser?${params.toString()}`);
    neoLibraryFillSimpleSelect('neo-library-composer-lora-category', (data.categories || ['all']).map(v => ({ value:v, label:v })), $('neo-library-composer-lora-category')?.value || 'all');
    neoLibraryFillSimpleSelect('neo-library-composer-lora-base-model', (data.base_models || ['all']).map(v => ({ value:v, label:v })), $('neo-library-composer-lora-base-model')?.value || 'all');
    neoLibraryFillSimpleSelect('neo-library-composer-lora-style', (data.style_categories || ['all']).map(v => ({ value:v, label:v })), $('neo-library-composer-lora-style')?.value || 'all');
    neoLibraryFillSimpleSelect('neo-library-composer-lora-item', (data.entries || []).map(entry => ({ value: entry.id || '', label: entry.label || entry.id || '' })), previousId || '');
    syncNeoLibraryComposerLoraStrength();
    await loadNeoLibraryComposerLoraRecord();
    setStatus('neo-library-composer-lora-status', (data.entries || []).length ? `${data.entries.length} ${data.kind === 'ti' ? 'TI' : 'LoRA'} item(s) found.` : `No ${data.kind === 'ti' ? 'TI' : 'LoRA'} items match the current filters.`);
  } catch (e) {
    setStatus('neo-library-composer-lora-status', e.message, 'error');
  }
}

async function loadNeoLibraryComposerLoraRecord() {
  const lid = $('neo-library-composer-lora-item')?.value || '';
  if (!lid) {
    if ($('neo-library-composer-lora-preview')) $('neo-library-composer-lora-preview').value = '';
    return;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-record?lid=${encodeURIComponent(lid)}`);
    const rec = data.record || {};
    if ($('neo-library-composer-lora-triggers')) {
      $('neo-library-composer-lora-triggers').value = (rec.triggers || []).join(', ');
    }
    await refreshNeoLibraryComposerLoraInsertPreview();
  } catch (e) {
    setStatus('neo-library-composer-lora-status', e.message, 'error');
  }
}

async function refreshNeoLibraryComposerLoraInsertPreview() {
  const lid = $('neo-library-composer-lora-item')?.value || '';
  if (!lid) {
    if ($('neo-library-composer-lora-preview')) $('neo-library-composer-lora-preview').value = '';
    return '';
  }
  try {
    const params = new URLSearchParams();
    params.set('lid', lid);
    params.set('strength', $('neo-library-composer-lora-strength')?.value || '0.80');
    params.set('include_triggers', $('neo-library-composer-lora-include-triggers')?.checked ? 'true' : 'false');
    params.set('selected_triggers', $('neo-library-composer-lora-triggers')?.value || '');
    const data = await safeFetchJson(`/api/neo-library/lora-insert-block?${params.toString()}`);
    const rec = data.record || {};
    const lines = [];
    lines.push(data.block || '');
    lines.push('');
    lines.push(`Name: ${rec.name || rec.rel || '—'}`);
    if (rec.category) lines.push(`Category: ${rec.category}`);
    if (rec.base_model) lines.push(`Base model: ${rec.base_model}`);
    if (rec.style_category) lines.push(`Style: ${rec.style_category}`);
    if ((rec.triggers || []).length) lines.push(`Saved triggers: ${(rec.triggers || []).join(', ')}`);
    if (rec.notes) lines.push(`Notes: ${rec.notes}`);
    if ($('neo-library-composer-lora-preview')) $('neo-library-composer-lora-preview').value = lines.filter(Boolean).join('\n');
    return data.block || '';
  } catch (e) {
    setStatus('neo-library-composer-lora-status', e.message, 'error');
    return '';
  }
}

async function insertNeoLibraryComposerLoraBlock() {
  const block = await refreshNeoLibraryComposerLoraInsertPreview();
  if (!trim(block || '')) {
    setStatus('neo-library-composer-lora-status', 'Nothing to insert yet.', 'warn');
    return;
  }
  const target = $('neo-library-composer-lora-target')?.value || 'positive';
  if (target === 'bundle-loras') {
    neoLibraryAppendComposerText('bundle-loras', block, ', ');
  } else if (target === 'negative') {
    neoLibraryAppendComposerText('bundle-negative', block, ', ');
  } else {
    neoLibraryAppendComposerText('bundle-positive', block, ', ');
  }
  setStatus('neo-library-composer-lora-status', 'LoRA / TI block inserted into Prompt Composer.');
}



function setNeoMiniTab(groupSelector, target) {
  document.querySelectorAll(groupSelector).forEach(btn => btn.classList.toggle('is-active', btn.dataset.neoSubtab === target));
  document.querySelectorAll('[data-neo-subtab-panel]').forEach(panel => panel.classList.toggle('is-active', panel.dataset.neoSubtabPanel === target));
}

function fillSelectRaw(id, values, selected='', placeholder='Select') {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  el.appendChild(first);
  (values || []).forEach(v => {
    const opt = document.createElement('option');
    if (typeof v === 'string') { opt.value = v; opt.textContent = v; }
    else { opt.value = v.value ?? ''; opt.textContent = v.label ?? v.value ?? ''; }
    el.appendChild(opt);
  });
  const want = selected || '';
  if ([...el.options].some(o => o.value === want)) el.value = want;
}

async function refreshNeoLibraryKeywordInsert(keepSelection=false) {
  const prev = keepSelection ? ($('neo-library-keyword-item')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('category', $('neo-library-keyword-category')?.value || 'all');
    params.set('subcategory', $('neo-library-keyword-subcategory')?.value || 'all');
    params.set('query', trim($('neo-library-keyword-search')?.value || ''));
    const data = await safeFetchJson(`/api/neo-library/keyword-browser?${params.toString()}`);
    fillSelectRaw('neo-library-keyword-category', (data.categories || []).map(v => ({value:v,label:v})), data.selected_category || 'all', 'Select category');
    fillSelectRaw('neo-library-keyword-subcategory', (data.subcategories || []).map(v => ({value:v,label:v})), data.selected_subcategory || 'all', 'Select subcategory');
    fillSelectRaw('neo-library-keyword-item', (data.entries || []).map(v => ({value:v.id || '', label:v.label || v.id || ''})), prev || '', 'Select keyword');
    await loadNeoLibraryKeywordPreview();
    setStatus('neo-library-keyword-status', (data.entries || []).length ? `${data.entries.length} keyword(s) found.` : 'No keywords match the current filters.');
  } catch (e) {
    setStatus('neo-library-keyword-status', e.message, 'error');
  }
}

async function loadNeoLibraryKeywordPreview() {
  const tid = $('neo-library-keyword-item')?.value || '';
  if (!tid) {
    if ($('neo-library-keyword-preview')) $('neo-library-keyword-preview').value = '';
    return '';
  }
  try {
    const params = new URLSearchParams();
    params.set('tid', tid);
    params.set('include_desc', $('neo-library-keyword-include-desc')?.checked ? 'true' : 'false');
    const data = await safeFetchJson(`/api/neo-library/keyword-insert-text?${params.toString()}`);
    const rec = data.record || {};
    const lines = [data.text || ''];
    if (rec.category) lines.push(`Category: ${rec.category}`);
    if (rec.subcategory) lines.push(`Subcategory: ${rec.subcategory}`);
    if (rec.desc) lines.push(`Description: ${rec.desc}`);
    if ($('neo-library-keyword-preview')) $('neo-library-keyword-preview').value = lines.filter(Boolean).join('\n');
    return data.text || '';
  } catch (e) {
    setStatus('neo-library-keyword-status', e.message, 'error');
    return '';
  }
}

async function insertNeoLibraryKeyword() {
  const text = await loadNeoLibraryKeywordPreview();
  if (!trim(text || '')) {
    setStatus('neo-library-keyword-status', 'Nothing to insert yet.', 'warn');
    return;
  }
  const target = $('neo-library-keyword-target')?.value || 'positive';
  try {
    neoLibraryAppendGenerationPromptText(target, text, ', ');
    setStatus('neo-library-keyword-status', target === 'negative' ? 'Keyword inserted into the generation negative prompt.' : 'Keyword inserted into the main generation prompt.');
  } catch (e) {
    setStatus('neo-library-keyword-status', e.message || 'Could not find the generation prompt box.', 'error');
  }
}
window.insertNeoLibraryKeyword = insertNeoLibraryKeyword;

function scheduleNeoLibraryVaultKeywordRefresh() {
  if (neoLibraryVaultKeywordRefreshHandle) window.clearTimeout(neoLibraryVaultKeywordRefreshHandle);
  neoLibraryVaultKeywordRefreshHandle = window.setTimeout(() => refreshNeoLibraryVaultKeywords({ keepSelection:true }), 180);
}

async function refreshNeoLibraryVaultOverview() {
  try {
    const data = await safeFetchJson('/api/neo-library/vault-overview');
    if ($('neo-library-vault-keyword-count')) $('neo-library-vault-keyword-count').textContent = String(data.keyword_count ?? 0);
    if ($('neo-library-vault-lora-count')) $('neo-library-vault-lora-count').textContent = String(data.lora_count ?? 0);
    if ($('neo-library-vault-ti-count')) $('neo-library-vault-ti-count').textContent = String(data.ti_count ?? 0);
    if ($('neo-library-vault-mapset-count')) $('neo-library-vault-mapset-count').textContent = String(data.mapset_count ?? 0);
    if ($('neo-library-vault-assets-root')) $('neo-library-vault-assets-root').textContent = data.assets_root || '—';
    if ($('neo-library-vault-lora-dir') && !$('neo-library-vault-lora-dir').value) $('neo-library-vault-lora-dir').value = data.default_lora_dir || '';
    if ($('neo-library-vault-embed-dir') && !$('neo-library-vault-embed-dir').value) $('neo-library-vault-embed-dir').value = data.default_embed_dir || '';
  } catch (e) {
    setStatus('neo-library-vault-status', e.message, 'error');
  }
}

async function refreshNeoLibraryVaultKeywords(options={}) {
  const { keepSelection=false } = options || {};
  const prev = keepSelection ? ($('neo-library-vault-kw-select')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('category', $('neo-library-vault-kw-filter-cat')?.value || 'all');
    params.set('subcategory', $('neo-library-vault-kw-filter-sub')?.value || 'all');
    params.set('query', trim($('neo-library-vault-kw-search')?.value || ''));
    const data = await safeFetchJson(`/api/neo-library/keyword-browser?${params.toString()}`);
    fillSelectRaw('neo-library-vault-kw-filter-cat', (data.categories || []).map(v => ({value:v,label:v})), data.selected_category || 'all', 'Filter category');
    fillSelectRaw('neo-library-vault-kw-filter-sub', (data.subcategories || []).map(v => ({value:v,label:v})), data.selected_subcategory || 'all', 'Filter subcategory');
    fillSelectRaw('neo-library-vault-kw-select', (data.entries || []).map(v => ({value:v.id || '', label:v.label || v.id || ''})), prev || '', 'Saved keywords');
    if (prev || $('neo-library-vault-kw-select')?.value) await loadNeoLibraryVaultKeywordRecord($('neo-library-vault-kw-select')?.value || prev || '');
    setStatus('neo-library-vault-kw-status', (data.entries || []).length ? `${data.entries.length} keyword(s) found.` : 'No keywords found.');
  } catch (e) {
    setStatus('neo-library-vault-kw-status', e.message, 'error');
  }
}

async function loadNeoLibraryVaultKeywordRecord(tid) {
  if (!tid) return;
  try {
    const data = await safeFetchJson(`/api/neo-library/keyword-record?tid=${encodeURIComponent(tid)}`);
    const rec = data.record || {};
    $('neo-library-vault-kw-id').value = tid;
    $('neo-library-vault-kw-category').value = rec.category || '';
    $('neo-library-vault-kw-subcategory').value = rec.subcategory || 'general';
    $('neo-library-vault-kw-name').value = rec.name || '';
    $('neo-library-vault-kw-aliases').value = (rec.aliases || []).join(', ');
    $('neo-library-vault-kw-desc').value = rec.desc || '';
    $('neo-library-vault-kw-enabled').checked = !!rec.enabled;
    setStatus('neo-library-vault-kw-status', 'Keyword loaded.');
  } catch (e) {
    setStatus('neo-library-vault-kw-status', e.message, 'error');
  }
}

function clearNeoLibraryVaultKeywordEditor() {
  $('neo-library-vault-kw-id').value = '';
  $('neo-library-vault-kw-category').value = '';
  $('neo-library-vault-kw-subcategory').value = '';
  $('neo-library-vault-kw-name').value = '';
  $('neo-library-vault-kw-aliases').value = '';
  $('neo-library-vault-kw-desc').value = '';
  $('neo-library-vault-kw-enabled').checked = true;
  setStatus('neo-library-vault-kw-status', 'New keyword.');
}

async function saveNeoLibraryVaultKeyword() {
  const fd = new FormData();
  fd.append('tid', $('neo-library-vault-kw-id')?.value || '');
  fd.append('category', $('neo-library-vault-kw-category')?.value || '');
  fd.append('subcategory', $('neo-library-vault-kw-subcategory')?.value || 'general');
  fd.append('name', $('neo-library-vault-kw-name')?.value || '');
  fd.append('aliases', $('neo-library-vault-kw-aliases')?.value || '');
  fd.append('desc', $('neo-library-vault-kw-desc')?.value || '');
  fd.append('enabled', $('neo-library-vault-kw-enabled')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/keyword-save', { method:'POST', body:fd });
    $('neo-library-vault-kw-id').value = data.tid || '';
    await refreshNeoLibraryVaultKeywords({ keepSelection:false });
    fillSelectRaw('neo-library-vault-kw-select', $('neo-library-vault-kw-select') ? [...$('neo-library-vault-kw-select').options].slice(1).map(o => ({value:o.value,label:o.textContent})) : [], data.tid || '', 'Saved keywords');
    await refreshNeoLibraryKeywordInsert(true);
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-vault-kw-status', data.message || 'Keyword saved.');
  } catch (e) {
    setStatus('neo-library-vault-kw-status', e.message, 'error');
  }
}

async function deleteNeoLibraryVaultKeyword() {
  const tid = $('neo-library-vault-kw-id')?.value || $('neo-library-vault-kw-select')?.value || '';
  if (!tid) return setStatus('neo-library-vault-kw-status', 'Nothing selected.', 'warn');
  const fd = new FormData(); fd.append('tid', tid);
  try {
    const data = await safeFetchJson('/api/neo-library/keyword-delete', { method:'POST', body:fd });
    clearNeoLibraryVaultKeywordEditor();
    await refreshNeoLibraryVaultKeywords({ keepSelection:false });
    await refreshNeoLibraryKeywordInsert(true);
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-vault-kw-status', data.message || 'Keyword deleted.');
  } catch (e) {
    setStatus('neo-library-vault-kw-status', e.message, 'error');
  }
}

async function refreshNeoLibraryVaultLoraBrowser(options={}) {
  const { keepSelection=false } = options || {};
  const prev = keepSelection ? ($('neo-library-vault-lora-select')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('kind', $('neo-library-vault-lora-kind')?.value || 'lora');
    params.set('query', trim($('neo-library-vault-lora-search')?.value || ''));
    params.set('category', $('neo-library-vault-lora-filter-cat')?.value || 'all');
    params.set('base_model', $('neo-library-vault-lora-filter-base')?.value || 'all');
    params.set('style_category', $('neo-library-vault-lora-filter-style')?.value || 'all');
    const data = await safeFetchJson(`/api/neo-library/lora-browser?${params.toString()}`);
    fillSelectRaw('neo-library-vault-lora-filter-cat', (data.categories || []).map(v => ({value:v,label:v})), $('neo-library-vault-lora-filter-cat')?.value || 'all', 'Filter category');
    fillSelectRaw('neo-library-vault-lora-filter-base', (data.base_models || []).map(v => ({value:v,label:v})), $('neo-library-vault-lora-filter-base')?.value || 'all', 'Base model');
    fillSelectRaw('neo-library-vault-lora-filter-style', (data.style_categories || []).map(v => ({value:v,label:v})), $('neo-library-vault-lora-filter-style')?.value || 'all', 'Style/category');
    fillSelectRaw('neo-library-vault-lora-select', (data.entries || []).map(v => ({value:v.id || '', label:v.label || v.id || ''})), prev || '', 'Registered');
    if (prev || $('neo-library-vault-lora-select')?.value) await loadNeoLibraryVaultLoraRecord($('neo-library-vault-lora-select')?.value || prev || '');
    setStatus('neo-library-vault-lora-status', (data.entries || []).length ? `${data.entries.length} item(s) found.` : 'No LoRA / TI items found.');
  } catch (e) {
    setStatus('neo-library-vault-lora-status', e.message, 'error');
  }
}

function neoLibrarySelectedValues(id) {
  const el = $(id);
  if (!el) return [];
  return Array.from(el.selectedOptions || []).map(opt => opt.value).filter(Boolean);
}

function setNeoLibraryVaultLoraPreviewImages(rec) {
  const primaryUrl = rec?.preview_url || '';
  if ($('neo-library-vault-lora-preview-img')) {
    if (primaryUrl) $('neo-library-vault-lora-preview-img').src = primaryUrl;
    else $('neo-library-vault-lora-preview-img').removeAttribute('src');
  }
  if ($('neo-library-vault-lora-provider-badge')) {
    const provider = rec?.provider ? String(rec.provider).toUpperCase() : '';
    const label = rec?.provider_label || rec?.name || '';
    const url = rec?.provider_url || '';
    $('neo-library-vault-lora-provider-badge').textContent = provider ? `${provider}${label ? ` · ${label}` : ''}${url ? ` · ${url}` : ''}` : '';
  }
  const options = (rec?.preview_urls || []).map(row => ({ value: row.path || '', label: row.name || row.path || '' }));
  fillSelectRaw('neo-library-vault-lora-remote-preview-select', options, rec?.preview_image || '', 'Fetched / saved previews');
  refreshNeoLibraryVaultLoraRemotePreview();
  if ($('neo-library-vault-civitai-url')) $('neo-library-vault-civitai-url').value = rec?.provider_url || $('neo-library-vault-civitai-url').value || '';
}

function refreshNeoLibraryVaultLoraRemotePreview() {
  const select = $('neo-library-vault-lora-remote-preview-select');
  const path = select?.value || '';
  if ($('neo-library-vault-lora-remote-preview-img')) {
    if (path) $('neo-library-vault-lora-remote-preview-img').src = `/api/neo-library/lora-preview-file?path=${encodeURIComponent(path)}`;
    else $('neo-library-vault-lora-remote-preview-img').removeAttribute('src');
  }
}

async function loadNeoLibraryVaultLoraRecord(lid) {
  if (!lid) return;
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-record?lid=${encodeURIComponent(lid)}`);
    const rec = data.record || {};
    $('neo-library-vault-lora-id').value = lid;
    $('neo-library-vault-lora-file').value = rec.file || '';
    $('neo-library-vault-lora-rel').value = rec.rel || '';
    $('neo-library-vault-lora-category').value = rec.category || '';
    $('neo-library-vault-lora-name').value = rec.name || '';
    $('neo-library-vault-lora-strength').value = rec.default_strength ?? 0.8;
    $('neo-library-vault-lora-min-strength').value = rec.min_strength ?? 0.6;
    $('neo-library-vault-lora-max-strength').value = rec.max_strength ?? 1.0;
    $('neo-library-vault-lora-triggers').value = (rec.triggers || []).join(', ');
    $('neo-library-vault-lora-keywords').value = (rec.keywords || []).join(', ');
    $('neo-library-vault-lora-style-category').value = rec.style_category || '';
    $('neo-library-vault-lora-base-model').value = rec.base_model || '';
    $('neo-library-vault-lora-example').value = rec.example_prompt || '';
    $('neo-library-vault-lora-preview-path').value = rec.preview_image || '';
    $('neo-library-vault-lora-caution').value = rec.caution_notes || '';
    $('neo-library-vault-lora-notes').value = rec.notes || '';
    $('neo-library-vault-lora-enabled').checked = !!rec.enabled;
    setNeoLibraryVaultLoraPreviewImages(rec);
    const prev = await safeFetchJson(`/api/neo-library/lora-insert-block?lid=${encodeURIComponent(lid)}&strength=${encodeURIComponent(String(rec.default_strength ?? 0.8))}&include_triggers=true&selected_triggers=${encodeURIComponent((rec.triggers||[]).join(', '))}`);
    if ($('neo-library-vault-lora-insert-preview')) $('neo-library-vault-lora-insert-preview').value = prev.block || '';
    setStatus('neo-library-vault-lora-status', 'LoRA / TI loaded.');
  } catch (e) {
    setStatus('neo-library-vault-lora-status', e.message, 'error');
  }
}

async function fetchNeoLibraryVaultLoraFromCivitai() {
  const lid = $('neo-library-vault-lora-id')?.value || $('neo-library-vault-lora-select')?.value || '';
  if (!lid) return setStatus('neo-library-vault-civitai-status', 'Select a LoRA / TI entry first.', 'warn');
  const fd = new FormData();
  fd.append('lid', lid);
  fd.append('civitai_url', $('neo-library-vault-civitai-url')?.value || '');
  fd.append('merge_mode', $('neo-library-vault-civitai-merge-mode')?.value || 'fill_missing');
  fd.append('overwrite_fields_csv', neoLibrarySelectedValues('neo-library-vault-civitai-overwrite-fields').join(','));
  try {
    setStatus('neo-library-vault-civitai-status', 'Pulling metadata + previews from CivitAI...');
    const data = await safeFetchJson('/api/neo-library/lora-civitai-import', { method:'POST', body:fd });
    await refreshNeoLibraryVaultLoraBrowser({ keepSelection:true });
    await refreshNeoLibraryComposerLoraBrowser({ keepSelection:true });
    await loadNeoLibraryVaultLoraRecord(lid);
    setStatus('neo-library-vault-civitai-status', data.message || 'CivitAI import complete.');
  } catch (e) {
    setStatus('neo-library-vault-civitai-status', e.message, 'error');
  }
}

async function applyNeoLibraryVaultLoraSelectedPreview() {
  const lid = $('neo-library-vault-lora-id')?.value || $('neo-library-vault-lora-select')?.value || '';
  const previewPath = $('neo-library-vault-lora-remote-preview-select')?.value || '';
  if (!lid || !previewPath) return setStatus('neo-library-vault-civitai-status', 'Pick a fetched preview first.', 'warn');
  const fd = new FormData();
  fd.append('lid', lid);
  fd.append('preview_path', previewPath);
  try {
    const data = await safeFetchJson('/api/neo-library/lora-set-primary-preview', { method:'POST', body:fd });
    await loadNeoLibraryVaultLoraRecord(lid);
    setStatus('neo-library-vault-civitai-status', data.message || 'Primary preview updated.');
  } catch (e) {
    setStatus('neo-library-vault-civitai-status', e.message, 'error');
  }
}

async function scanNeoLibraryVaultLoras() {
  const fd = new FormData();
  fd.append('lora_dir', $('neo-library-vault-lora-dir')?.value || '');
  fd.append('embed_dir', $('neo-library-vault-embed-dir')?.value || '');
  fd.append('include_ti', $('neo-library-vault-include-ti')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/lora-scan', { method:'POST', body:fd });
    await refreshNeoLibraryVaultLoraBrowser({ keepSelection:false });
    await refreshNeoLibraryComposerLoraBrowser({ keepSelection:false });
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-vault-lora-status', data.message || 'Scan complete.');
  } catch (e) {
    setStatus('neo-library-vault-lora-status', e.message, 'error');
  }
}

async function saveNeoLibraryVaultLora() {
  const fd = new FormData();
  ['lid','default_strength','min_strength','max_strength','triggers','keywords','style_category','base_model','example_prompt','preview_image','caution_notes','notes','enabled'].forEach(() => {});
  fd.append('lid', $('neo-library-vault-lora-id')?.value || '');
  fd.append('default_strength', $('neo-library-vault-lora-strength')?.value || '0.8');
  fd.append('min_strength', $('neo-library-vault-lora-min-strength')?.value || '0.6');
  fd.append('max_strength', $('neo-library-vault-lora-max-strength')?.value || '1.0');
  fd.append('triggers', $('neo-library-vault-lora-triggers')?.value || '');
  fd.append('keywords', $('neo-library-vault-lora-keywords')?.value || '');
  fd.append('style_category', $('neo-library-vault-lora-style-category')?.value || '');
  fd.append('base_model', $('neo-library-vault-lora-base-model')?.value || '');
  fd.append('example_prompt', $('neo-library-vault-lora-example')?.value || '');
  fd.append('preview_image', $('neo-library-vault-lora-preview-path')?.value || '');
  fd.append('caution_notes', $('neo-library-vault-lora-caution')?.value || '');
  fd.append('notes', $('neo-library-vault-lora-notes')?.value || '');
  fd.append('enabled', $('neo-library-vault-lora-enabled')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/lora-save', { method:'POST', body:fd });
    await refreshNeoLibraryVaultLoraBrowser({ keepSelection:true });
    await refreshNeoLibraryComposerLoraBrowser({ keepSelection:true });
    setStatus('neo-library-vault-lora-status', data.message || 'LoRA / TI metadata saved.');
  } catch (e) {
    setStatus('neo-library-vault-lora-status', e.message, 'error');
  }
}

async function deleteNeoLibraryVaultLora() {
  const lid = $('neo-library-vault-lora-id')?.value || $('neo-library-vault-lora-select')?.value || '';
  if (!lid) return setStatus('neo-library-vault-lora-status', 'Nothing selected.', 'warn');
  const fd = new FormData(); fd.append('lid', lid);
  try {
    const data = await safeFetchJson('/api/neo-library/lora-delete', { method:'POST', body:fd });
    await refreshNeoLibraryVaultLoraBrowser({ keepSelection:false });
    await refreshNeoLibraryComposerLoraBrowser({ keepSelection:false });
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-vault-lora-status', data.message || 'LoRA / TI deleted.');
  } catch (e) {
    setStatus('neo-library-vault-lora-status', e.message, 'error');
  }
}

function renderMapList(id, rows) {
  if (!$(id)) return;
  $(id).value = (rows || []).map(r => `${r.label || ''} -> ${r.path || ''}`).join('\n');
}

async function refreshNeoLibraryMapsetBrowser(keepSelection=false) {
  const prev = keepSelection ? ($('neo-library-mapset-select')?.value || '') : '';
  try {
    const params = new URLSearchParams();
    params.set('query', trim($('neo-library-mapset-search')?.value || ''));
    const data = await safeFetchJson(`/api/neo-library/mapset-browser?${params.toString()}`);
    fillSelectRaw('neo-library-mapset-select', (data.entries || []).map(v => ({value:v.id || '', label:v.label || v.id || ''})), prev || '', 'Saved mapsets');
    if (prev || $('neo-library-mapset-select')?.value) await loadNeoLibraryMapsetRecord($('neo-library-mapset-select')?.value || prev || '');
    setStatus('neo-library-mapset-status', (data.entries || []).length ? `${data.entries.length} mapset(s) found.` : 'No mapsets found.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function loadNeoLibraryMapsetRecord(mid) {
  if (!mid) return;
  try {
    const data = await safeFetchJson(`/api/neo-library/mapset-record?mid=${encodeURIComponent(mid)}`);
    const rec = data.record || {};
    $('neo-library-mapset-select').value = mid;
    $('neo-library-mapset-title').value = rec.title || '';
    $('neo-library-mapset-tags').value = (rec.tags || []).join(', ');
    $('neo-library-mapset-folder').value = data.folder || '';
    renderMapList('neo-library-mapset-canny-list', data.maps?.canny || []);
    renderMapList('neo-library-mapset-depth-list', data.maps?.depth || []);
    renderMapList('neo-library-mapset-openpose-list', data.maps?.openpose || []);
    setStatus('neo-library-mapset-status', 'Mapset loaded.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function createNeoLibraryMapset() {
  const fd = new FormData();
  fd.append('title', $('neo-library-mapset-title')?.value || 'New Mapset');
  fd.append('tags_csv', $('neo-library-mapset-tags')?.value || '');
  try {
    const data = await safeFetchJson('/api/neo-library/mapset-create', { method:'POST', body:fd });
    await refreshNeoLibraryMapsetBrowser(false);
    await refreshNeoLibraryVaultOverview();
    const id = data.record?.id || '';
    if (id) await loadNeoLibraryMapsetRecord(id);
    setStatus('neo-library-mapset-status', data.message || 'Mapset created.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function saveNeoLibraryMapset() {
  const mid = $('neo-library-mapset-select')?.value || '';
  if (!mid) return setStatus('neo-library-mapset-status', 'Select a mapset first.', 'warn');
  const fd = new FormData();
  fd.append('mid', mid);
  fd.append('title', $('neo-library-mapset-title')?.value || '');
  fd.append('tags_csv', $('neo-library-mapset-tags')?.value || '');
  try {
    const data = await safeFetchJson('/api/neo-library/mapset-save', { method:'POST', body:fd });
    await refreshNeoLibraryMapsetBrowser(true);
    await loadNeoLibraryMapsetRecord(mid);
    setStatus('neo-library-mapset-status', data.message || 'Mapset saved.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function deleteNeoLibraryMapset() {
  const mid = $('neo-library-mapset-select')?.value || '';
  if (!mid) return setStatus('neo-library-mapset-status', 'Nothing selected.', 'warn');
  const fd = new FormData(); fd.append('mid', mid);
  try {
    const data = await safeFetchJson('/api/neo-library/mapset-delete', { method:'POST', body:fd });
    $('neo-library-mapset-title').value = '';
    $('neo-library-mapset-tags').value = '';
    $('neo-library-mapset-folder').value = '';
    renderMapList('neo-library-mapset-canny-list', []);
    renderMapList('neo-library-mapset-depth-list', []);
    renderMapList('neo-library-mapset-openpose-list', []);
    await refreshNeoLibraryMapsetBrowser(false);
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-mapset-status', data.message || 'Mapset deleted.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function importNeoLibraryMapsetFolder() {
  const mid = $('neo-library-mapset-select')?.value || '';
  if (!mid) return setStatus('neo-library-mapset-status', 'Select a mapset first.', 'warn');
  const fd = new FormData();
  fd.append('mid', mid);
  fd.append('folder', $('neo-library-mapset-import-folder')?.value || '');
  fd.append('recursive', $('neo-library-mapset-recursive')?.checked ? 'true' : 'false');
  fd.append('import_mode', $('neo-library-mapset-import-mode')?.value || 'auto-detect by filename');
  fd.append('enforce_suffix', $('neo-library-mapset-enforce-suffix')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/mapset-import-folder', { method:'POST', body:fd });
    await loadNeoLibraryMapsetRecord(mid);
    setStatus('neo-library-mapset-status', data.message || 'Map folder imported.');
  } catch (e) {
    setStatus('neo-library-mapset-status', e.message, 'error');
  }
}

async function openNeoLibraryFolder(path, statusId='neo-library-vault-status') {
  const fd = new FormData(); fd.append('path', path || '');
  try {
    const data = await safeFetchJson('/api/neo-library/open-folder', { method:'POST', body:fd });
    setStatus(statusId, data.message || 'Open request sent.');
  } catch (e) {
    setStatus(statusId, e.message, 'error');
  }
}

function collectNeoLibraryMapgenSettings() {
  return {
    python_exe: $('neo-library-mapgen-python')?.value || '',
    script_path: $('neo-library-mapgen-script')?.value || '',
    in_dir: $('neo-library-mapgen-input')?.value || '',
    out_dir: $('neo-library-mapgen-output')?.value || '',
    mapset_name: $('neo-library-mapgen-mapset-name')?.value || '',
    mode: $('neo-library-mapgen-mode')?.value || 'cover',
    detect: Number($('neo-library-mapgen-detect')?.value || 512),
    portrait_size: $('neo-library-mapgen-portrait')?.value || '896x1344',
    landscape_size: $('neo-library-mapgen-landscape')?.value || '1344x896',
    name_suffix: !!$('neo-library-mapgen-name-suffix')?.checked,
    do_canny: !!$('neo-library-mapgen-do-canny')?.checked,
    do_openpose: !!$('neo-library-mapgen-do-openpose')?.checked,
    do_depth: !!$('neo-library-mapgen-do-depth')?.checked,
    canny_low: Number($('neo-library-mapgen-canny-low')?.value || 150),
    canny_high: Number($('neo-library-mapgen-canny-high')?.value || 300),
    blur: Number($('neo-library-mapgen-blur')?.value || 3),
    clahe: !!$('neo-library-mapgen-clahe')?.checked,
    sharpen: !!$('neo-library-mapgen-sharpen')?.checked,
    denoise: !!$('neo-library-mapgen-denoise')?.checked,
    canny_invert: !!$('neo-library-mapgen-canny-invert')?.checked,
    canny_thickness: $('neo-library-mapgen-canny-thickness')?.value || 'none',
    canny_adaptive: !!$('neo-library-mapgen-canny-adaptive')?.checked,
    canny_clean_bg: !!$('neo-library-mapgen-canny-clean-bg')?.checked,
    device: $('neo-library-mapgen-device')?.value || 'cpu',
    hands: !!$('neo-library-mapgen-hands')?.checked,
    face: !!$('neo-library-mapgen-face')?.checked,
    depth_device: $('neo-library-mapgen-depth-device')?.value || 'cpu',
    depth_invert: !!$('neo-library-mapgen-depth-invert')?.checked,
    recursive: !!$('neo-library-mapgen-recursive')?.checked,
    skip_existing: !!$('neo-library-mapgen-skip-existing')?.checked,
  };
}

function applyNeoLibraryMapgenSettings(cfg) {
  if (!cfg) return;
  const map = {
    'neo-library-mapgen-python':'python_exe', 'neo-library-mapgen-script':'script_path', 'neo-library-mapgen-input':'in_dir', 'neo-library-mapgen-output':'out_dir',
    'neo-library-mapgen-mapset-name':'mapset_name', 'neo-library-mapgen-mode':'mode', 'neo-library-mapgen-detect':'detect', 'neo-library-mapgen-portrait':'portrait_size',
    'neo-library-mapgen-landscape':'landscape_size', 'neo-library-mapgen-canny-low':'canny_low', 'neo-library-mapgen-canny-high':'canny_high', 'neo-library-mapgen-blur':'blur',
    'neo-library-mapgen-canny-thickness':'canny_thickness', 'neo-library-mapgen-device':'device', 'neo-library-mapgen-depth-device':'depth_device', 'neo-library-mapgen-effective-output':'effective_out_dir'
  };
  Object.entries(map).forEach(([id,key]) => { if ($(id) && cfg[key] !== undefined) $(id).value = cfg[key]; });
  const checks = {
    'neo-library-mapgen-name-suffix':'name_suffix','neo-library-mapgen-do-canny':'do_canny','neo-library-mapgen-do-openpose':'do_openpose','neo-library-mapgen-do-depth':'do_depth',
    'neo-library-mapgen-clahe':'clahe','neo-library-mapgen-sharpen':'sharpen','neo-library-mapgen-denoise':'denoise','neo-library-mapgen-canny-invert':'canny_invert',
    'neo-library-mapgen-canny-adaptive':'canny_adaptive','neo-library-mapgen-canny-clean-bg':'canny_clean_bg','neo-library-mapgen-hands':'hands','neo-library-mapgen-face':'face',
    'neo-library-mapgen-depth-invert':'depth_invert','neo-library-mapgen-recursive':'recursive','neo-library-mapgen-skip-existing':'skip_existing'
  };
  Object.entries(checks).forEach(([id,key]) => { if ($(id)) $(id).checked = !!cfg[key]; });
}

async function loadNeoLibraryMapgenSettings() {
  try {
    const data = await safeFetchJson('/api/neo-library/mapgen-settings');
    applyNeoLibraryMapgenSettings(data.settings || {});
    setStatus('neo-library-mapgen-status', 'Map Generator settings loaded.');
  } catch (e) {
    setStatus('neo-library-mapgen-status', e.message, 'error');
  }
}

async function saveNeoLibraryMapgenSettings() {
  try {
    const data = await safeFetchJson('/api/neo-library/mapgen-settings-save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(collectNeoLibraryMapgenSettings()) });
    applyNeoLibraryMapgenSettings(data.settings || {});
    setStatus('neo-library-mapgen-status', data.message || 'Map Generator settings saved.');
  } catch (e) {
    setStatus('neo-library-mapgen-status', e.message, 'error');
  }
}

async function runNeoLibraryMapgen() {
  try {
    setStatus('neo-library-mapgen-status', 'Running map generation...');
    const data = await safeFetchJson('/api/neo-library/mapgen-run', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(collectNeoLibraryMapgenSettings()) });
    if ($('neo-library-mapgen-log')) $('neo-library-mapgen-log').value = data.log || '';
    if ($('neo-library-mapgen-command')) $('neo-library-mapgen-command').textContent = data.command ? `Command: ${data.command}` : '';
    if ($('neo-library-mapgen-effective-output')) $('neo-library-mapgen-effective-output').value = data.effective_out_dir || '';
    setStatus('neo-library-mapgen-status', data.ok ? 'Map generation finished.' : `Map generation returned code ${data.returncode}.`, data.ok ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-mapgen-status', e.message, 'error');
  }
}

async function registerNeoLibraryMapgenOutput() {
  const fd = new FormData();
  fd.append('out_dir', $('neo-library-mapgen-effective-output')?.value || $('neo-library-mapgen-output')?.value || '');
  fd.append('mapset_name', $('neo-library-mapgen-mapset-name')?.value || '');
  fd.append('enforce_suffix', $('neo-library-mapset-enforce-suffix')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/neo-library/mapgen-register-output', { method:'POST', body:fd });
    await refreshNeoLibraryMapsetBrowser(false);
    await refreshNeoLibraryVaultOverview();
    setStatus('neo-library-mapgen-status', data.message || 'Register request finished.', data.ok ? '' : 'warn');
  } catch (e) {
    setStatus('neo-library-mapgen-status', e.message, 'error');
  }
}


document.addEventListener('DOMContentLoaded', () => {
  if (!$('tab-library')) return;
  refreshNeoLibrarySummary();
  refreshStorageCompatSnapshot();
  refreshNeoLibraryPromptBrowser({ resetPage:true });
  refreshNeoLibraryCaptionSync();
  refreshNeoLibraryOutputBrowser({ resetPage:true });
  refreshNeoLibraryComposerLibraries({ keepItem:false });
  refreshNeoLibraryKeywordInsert(false);
  refreshNeoLibraryVaultOverview();
  refreshNeoLibraryVaultKeywords({ keepSelection:false });
  refreshNeoLibraryVaultLoraBrowser({ keepSelection:false });
  refreshNeoLibraryMapsetBrowser(false);
  loadNeoLibraryMapgenSettings();
  refreshNeoLibraryComposerCharacters();
  refreshNeoLibraryComposerCharacterBuilder({ keepSelection:false });
  refreshNeoLibraryComposerPresetBrowser({ keepSelection:false });
  refreshNeoLibraryComposerLoraBrowser({ keepSelection:false });

  $('btn-refresh-neo-library-summary')?.addEventListener('click', refreshNeoLibrarySummary);
  $('btn-refresh-storage-compat')?.addEventListener('click', refreshStorageCompatSnapshot);
  $('btn-neo-library-open-prompt-studio')?.addEventListener('click', () => switchTab('prompt'));
  $('btn-neo-library-open-caption-studio')?.addEventListener('click', () => switchTab('caption'));
  $('btn-neo-library-open-settings')?.addEventListener('click', () => switchTab('settings'));
  $('btn-neo-library-composer-send')?.addEventListener('click', () => sendNeoLibraryComposerToPromptStudio(false));
  $('btn-neo-library-composer-append')?.addEventListener('click', () => sendNeoLibraryComposerToPromptStudio(true));
  $('btn-refresh-neo-library-composer-library')?.addEventListener('click', () => refreshNeoLibraryComposerLibraries({ keepItem:true }));
  document.querySelectorAll('[data-neo-subtab]').forEach(btn => btn.addEventListener('click', () => setNeoMiniTab('[data-neo-subtab]', btn.dataset.neoSubtab || 'vault-keywords')));
  $('btn-neo-library-keyword-refresh')?.addEventListener('click', () => refreshNeoLibraryKeywordInsert(true));
  $('neo-library-keyword-search')?.addEventListener('input', () => refreshNeoLibraryKeywordInsert(true));
  ['neo-library-keyword-category','neo-library-keyword-subcategory'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryKeywordInsert(false)));
  $('neo-library-keyword-item')?.addEventListener('change', loadNeoLibraryKeywordPreview);
  $('neo-library-keyword-include-desc')?.addEventListener('change', loadNeoLibraryKeywordPreview);
  $('btn-neo-library-keyword-insert')?.addEventListener('click', insertNeoLibraryKeyword);
  ['neo-library-vault-kw-filter-cat','neo-library-vault-kw-filter-sub'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryVaultKeywords({ keepSelection:false })));
  $('neo-library-vault-kw-search')?.addEventListener('input', scheduleNeoLibraryVaultKeywordRefresh);
  $('neo-library-vault-kw-select')?.addEventListener('change', () => loadNeoLibraryVaultKeywordRecord($('neo-library-vault-kw-select')?.value || ''));
  $('btn-neo-library-vault-kw-new')?.addEventListener('click', clearNeoLibraryVaultKeywordEditor);
  $('btn-neo-library-vault-kw-save')?.addEventListener('click', saveNeoLibraryVaultKeyword);
  $('btn-neo-library-vault-kw-delete')?.addEventListener('click', deleteNeoLibraryVaultKeyword);
  $('btn-neo-library-vault-lora-scan')?.addEventListener('click', scanNeoLibraryVaultLoras);
  $('neo-library-vault-lora-kind')?.addEventListener('change', () => refreshNeoLibraryVaultLoraBrowser({ keepSelection:false }));
  $('neo-library-vault-lora-search')?.addEventListener('input', () => refreshNeoLibraryVaultLoraBrowser({ keepSelection:true }));
  ['neo-library-vault-lora-filter-cat','neo-library-vault-lora-filter-base','neo-library-vault-lora-filter-style'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryVaultLoraBrowser({ keepSelection:false })));
  $('neo-library-vault-lora-select')?.addEventListener('change', () => loadNeoLibraryVaultLoraRecord($('neo-library-vault-lora-select')?.value || ''));
  $('neo-library-vault-lora-remote-preview-select')?.addEventListener('change', refreshNeoLibraryVaultLoraRemotePreview);
  $('btn-neo-library-vault-civitai-fetch')?.addEventListener('click', fetchNeoLibraryVaultLoraFromCivitai);
  $('btn-neo-library-vault-lora-apply-preview')?.addEventListener('click', applyNeoLibraryVaultLoraSelectedPreview);
  $('btn-neo-library-vault-lora-save')?.addEventListener('click', saveNeoLibraryVaultLora);
  $('btn-neo-library-vault-lora-delete')?.addEventListener('click', deleteNeoLibraryVaultLora);
  $('neo-library-mapset-search')?.addEventListener('input', () => refreshNeoLibraryMapsetBrowser(true));
  $('neo-library-mapset-select')?.addEventListener('change', () => loadNeoLibraryMapsetRecord($('neo-library-mapset-select')?.value || ''));
  $('btn-neo-library-mapset-new')?.addEventListener('click', createNeoLibraryMapset);
  $('btn-neo-library-mapset-save')?.addEventListener('click', saveNeoLibraryMapset);
  $('btn-neo-library-mapset-delete')?.addEventListener('click', deleteNeoLibraryMapset);
  $('btn-neo-library-mapset-refresh')?.addEventListener('click', () => loadNeoLibraryMapsetRecord($('neo-library-mapset-select')?.value || ''));
  $('btn-neo-library-mapset-import-folder')?.addEventListener('click', importNeoLibraryMapsetFolder);
  $('btn-neo-library-mapset-open-folder')?.addEventListener('click', () => openNeoLibraryFolder($('neo-library-mapset-folder')?.value || '', 'neo-library-mapset-status'));
  $('btn-neo-library-mapgen-load')?.addEventListener('click', loadNeoLibraryMapgenSettings);
  $('btn-neo-library-mapgen-save')?.addEventListener('click', saveNeoLibraryMapgenSettings);
  $('btn-neo-library-mapgen-run')?.addEventListener('click', runNeoLibraryMapgen);
  $('btn-neo-library-mapgen-open-output')?.addEventListener('click', () => openNeoLibraryFolder($('neo-library-mapgen-effective-output')?.value || $('neo-library-mapgen-output')?.value || '', 'neo-library-mapgen-status'));
  $('btn-neo-library-mapgen-register')?.addEventListener('click', registerNeoLibraryMapgenOutput);
  $('saved-bundle-id')?.addEventListener('change', loadSelectedBundle);
  $('neo-library-composer-library')?.addEventListener('change', () => refreshNeoLibraryComposerLibraries({ keepItem:false }));
  $('neo-library-composer-library-search')?.addEventListener('input', scheduleNeoLibraryComposerLibraryRefresh);
  $('neo-library-composer-library-item')?.addEventListener('change', syncNeoLibraryComposerLibraryPreview);
  $('btn-neo-library-composer-insert')?.addEventListener('click', insertNeoLibraryComposerSnippet);
  $('btn-neo-library-composer-character-refresh')?.addEventListener('click', () => { refreshNeoLibraryComposerCharacters($('neo-library-composer-character-select')?.value || ''); refreshNeoLibraryComposerCharacterBuilder({ keepSelection:true }); });
  $('btn-neo-library-composer-character-load')?.addEventListener('click', loadNeoLibraryComposerCharacter);
  $('btn-neo-library-composer-character-save')?.addEventListener('click', saveNeoLibraryComposerCharacter);
  $('btn-neo-library-composer-character-add')?.addEventListener('click', addNeoLibraryComposerCharacterItem);
  $('btn-neo-library-composer-character-clear')?.addEventListener('click', clearNeoLibraryComposerCharacterSlot);
  $('btn-neo-library-composer-character-use')?.addEventListener('click', useNeoLibraryComposerCharacterInPositive);
  $('btn-neo-library-composer-character-link')?.addEventListener('click', linkNeoLibraryComposerCharacterToBundle);
  $('btn-neo-library-composer-character-delete')?.addEventListener('click', deleteNeoLibraryComposerCharacter);
  $('neo-library-composer-character-select')?.addEventListener('change', () => { if ($('neo-library-composer-character-name')) $('neo-library-composer-character-name').value = $('neo-library-composer-character-select').value || ''; });
  $('neo-library-composer-character-slot')?.addEventListener('change', neoLibraryCharacterSlotChanged);
  $('neo-library-composer-character-content')?.addEventListener('input', neoLibraryCharacterContentEdited);
  $('neo-library-composer-character-item')?.addEventListener('change', neoLibraryRenderCharacterItemPreview);
  $('neo-library-composer-character-search')?.addEventListener('input', () => refreshNeoLibraryComposerCharacterBuilder({ keepSelection:true }));
  ['neo-library-composer-character-gender','neo-library-composer-character-era','neo-library-composer-character-section','neo-library-composer-character-library'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryComposerCharacterBuilder({ keepSelection:false })));
  $('neo-library-composer-character-show-restricted')?.addEventListener('change', () => refreshNeoLibraryComposerCharacterBuilder({ keepSelection:false }));
  $('neo-library-composer-lora-kind')?.addEventListener('change', () => refreshNeoLibraryComposerLoraBrowser({ keepSelection:false }));
  $('neo-library-composer-lora-search')?.addEventListener('input', () => refreshNeoLibraryComposerLoraBrowser({ keepSelection:true }));
  ['neo-library-composer-lora-category','neo-library-composer-lora-base-model','neo-library-composer-lora-style'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryComposerLoraBrowser({ keepSelection:false })));
  $('neo-library-composer-lora-item')?.addEventListener('change', loadNeoLibraryComposerLoraRecord);
  $('neo-library-composer-lora-strength')?.addEventListener('input', refreshNeoLibraryComposerLoraInsertPreview);
  $('neo-library-composer-lora-triggers')?.addEventListener('input', refreshNeoLibraryComposerLoraInsertPreview);
  $('neo-library-composer-lora-include-triggers')?.addEventListener('change', refreshNeoLibraryComposerLoraInsertPreview);
  $('btn-neo-library-composer-lora-refresh')?.addEventListener('click', () => refreshNeoLibraryComposerLoraBrowser({ keepSelection:true }));
  $('btn-neo-library-composer-lora-insert')?.addEventListener('click', insertNeoLibraryComposerLoraBlock);

  $('btn-neo-library-composer-preset-refresh')?.addEventListener('click', () => refreshNeoLibraryComposerPresetBrowser({ keepSelection:true }));
  $('neo-library-composer-preset-search')?.addEventListener('input', () => refreshNeoLibraryComposerPresetBrowser({ keepSelection:false }));
  $('neo-library-composer-preset-browse-category')?.addEventListener('change', () => refreshNeoLibraryComposerPresetBrowser({ keepSelection:false }));
  $('neo-library-composer-preset-select')?.addEventListener('change', () => loadNeoLibraryComposerPresetRecord($('neo-library-composer-preset-select')?.value || ''));
  $('btn-neo-library-composer-preset-load')?.addEventListener('click', loadNeoLibraryComposerPresetIntoComposer);
  $('btn-neo-library-composer-preset-save-new')?.addEventListener('click', saveNeoLibraryComposerPresetNew);
  $('btn-neo-library-composer-preset-update')?.addEventListener('click', updateNeoLibraryComposerPreset);
  $('btn-neo-library-composer-preset-delete')?.addEventListener('click', deleteNeoLibraryComposerPreset);
  $('btn-neo-library-composer-preset-duplicate')?.addEventListener('click', duplicateNeoLibraryComposerPreset);
  $('btn-neo-library-composer-preset-toggle-favorite')?.addEventListener('click', toggleFavoriteNeoLibraryComposerPreset);
  $('btn-neo-library-composer-preset-compare')?.addEventListener('click', compareNeoLibraryComposerPresets);
  $('btn-neo-library-composer-preset-export')?.addEventListener('click', exportNeoLibraryComposerPreset);

  ['neo-library-prompt-query','neo-library-prompt-model','neo-library-prompt-style'].forEach(id => $(id)?.addEventListener('input', () => scheduleNeoLibraryPromptRefresh(true)));
  ['neo-library-prompt-category','neo-library-prompt-sort','neo-library-prompt-page-size'].forEach(id => $(id)?.addEventListener('change', () => refreshNeoLibraryPromptBrowser({ resetPage:true })));
  $('btn-refresh-neo-library-prompts')?.addEventListener('click', () => refreshNeoLibraryPromptBrowser());
  $('btn-clear-neo-library-prompts')?.addEventListener('click', () => {
    $('neo-library-prompt-query').value = '';
    $('neo-library-prompt-model').value = '';
    $('neo-library-prompt-style').value = '';
    fillCategorySelect('neo-library-prompt-category', ['all', ...initialPromptCategoryList.filter(x => x !== 'all')], 'all');
    $('neo-library-prompt-sort').value = 'newest';
    $('neo-library-prompt-page-size').value = '12';
    refreshNeoLibraryPromptBrowser({ resetPage:true });
  });
  $('btn-neo-library-prompt-prev')?.addEventListener('click', () => { if (neoLibraryPromptPage > 1) { neoLibraryPromptPage -= 1; refreshNeoLibraryPromptBrowser(); } });
  $('btn-neo-library-prompt-next')?.addEventListener('click', () => { if (neoLibraryPromptPage < neoLibraryPromptTotalPages) { neoLibraryPromptPage += 1; refreshNeoLibraryPromptBrowser(); } });
  $('neo-library-prompt-grid')?.addEventListener('click', async e => {
    const openBtn = e.target.closest('[data-neo-prompt-open]');
    const sendBtn = e.target.closest('[data-neo-prompt-send]');
    if (openBtn) await openNeoLibraryPrompt(openBtn.dataset.neoPromptOpen, 'edit');
    if (sendBtn) await openNeoLibraryPrompt(sendBtn.dataset.neoPromptSend, 'send');
  });
  $('btn-generation-prompt-manager-open')?.addEventListener('click', openGenerationPromptManagerModal);
  $('btn-close-generation-prompt-manager')?.addEventListener('click', closeGenerationPromptManagerModal);
  $('generation-prompt-manager-modal')?.addEventListener('click', e => { if (e.target?.id === 'generation-prompt-manager-modal') closeGenerationPromptManagerModal(); });
  $('btn-generation-saved-prompt-load')?.addEventListener('click', () => applySavedGenerationPrompt(false).catch(() => {}));
  $('btn-generation-saved-prompt-append')?.addEventListener('click', () => applySavedGenerationPrompt(true).catch(() => {}));
  $('btn-generation-saved-prompt-save')?.addEventListener('click', openGenerationSavePromptModal);
  $('btn-close-generation-save-prompt')?.addEventListener('click', closeGenerationSavePromptModal);
  $('btn-cancel-generation-save-prompt')?.addEventListener('click', closeGenerationSavePromptModal);
  $('btn-submit-generation-save-prompt')?.addEventListener('click', () => saveGenerationPromptEntry().catch(() => {}));
  $('generation-save-prompt-modal')?.addEventListener('click', e => { if (e.target?.id === 'generation-save-prompt-modal') closeGenerationSavePromptModal(); });
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!$('generation-save-prompt-modal')?.classList.contains('hidden')) closeGenerationSavePromptModal();
  });
  $('btn-neo-library-prompt-send')?.addEventListener('click', () => sendNeoLibraryPromptToStudio(false));
  $('btn-neo-library-prompt-append')?.addEventListener('click', () => sendNeoLibraryPromptToStudio(true));
  $('btn-neo-library-prompt-open-composer')?.addEventListener('click', openNeoLibraryPromptInComposer);
  $('btn-neo-library-prompt-update')?.addEventListener('click', updateNeoLibraryPrompt);
  $('btn-neo-library-prompt-delete')?.addEventListener('click', deleteNeoLibraryPrompt);

  mountNeoLibraryGenerationPanels();
  moveNeoLibraryPromptManagerToGeneration();
  refreshGenerationSavedPromptSelect(true).catch(() => {});
  $('btn-refresh-neo-library-caption')?.addEventListener('click', () => refreshNeoLibraryCaptionSync());
  $('neo-library-caption-category')?.addEventListener('change', () => refreshNeoLibraryCaptionSync({ category: $('neo-library-caption-category').value || '', name: '', image: '' }));
  $('neo-library-caption-name')?.addEventListener('change', () => refreshNeoLibraryCaptionSync({ category: $('neo-library-caption-category').value || '', name: $('neo-library-caption-name').value || '', image: '' }));
  $('neo-library-caption-image')?.addEventListener('change', () => refreshNeoLibraryCaptionSync({ category: $('neo-library-caption-category').value || '', image: $('neo-library-caption-image').value || '', name: '' }));
  $('btn-neo-library-caption-preview')?.addEventListener('click', () => openLightbox($('neo-library-caption-image-url')?.value || ''));
  $('btn-neo-library-caption-send')?.addEventListener('click', () => sendNeoLibraryCaptionToPromptStudio().catch(() => {}));
  $('btn-neo-library-caption-duplicate')?.addEventListener('click', duplicateNeoLibraryCaptionAsPrompt);
  $('btn-neo-library-caption-update')?.addEventListener('click', updateNeoLibraryCaption);
  $('btn-neo-library-caption-delete')?.addEventListener('click', deleteNeoLibraryCaption);

  $('neo-library-output-mode')?.addEventListener('change', () => refreshNeoLibraryOutputBrowser({ resetPage:true }));
  $('neo-library-output-page-size')?.addEventListener('change', () => refreshNeoLibraryOutputBrowser({ resetPage:true }));
  $('btn-refresh-neo-library-output')?.addEventListener('click', () => refreshNeoLibraryOutputBrowser({ keepSelection:true }));
  $('neo-library-output-name')?.addEventListener('change', () => openNeoLibraryOutputRecord($('neo-library-output-mode').value || 'txt2img', $('neo-library-output-name').value || ''));
  $('btn-neo-library-output-prev')?.addEventListener('click', () => { if (neoLibraryOutputPage > 1) { neoLibraryOutputPage -= 1; refreshNeoLibraryOutputBrowser(); } });
  $('btn-neo-library-output-next')?.addEventListener('click', () => { if (neoLibraryOutputPage < neoLibraryOutputTotalPages) { neoLibraryOutputPage += 1; refreshNeoLibraryOutputBrowser(); } });
  window.addEventListener('neo:generation-output-selected', () => { renderNeoLibraryOutputLineage(); });
  window.addEventListener('neo:generation-job-updated', () => { renderNeoLibraryOutputLineage(); });
  $('btn-neo-library-output-preview-full')?.addEventListener('click', () => openLightbox($('neo-library-output-preview')?.dataset.imageUrl || ''));
  $('btn-neo-library-output-load-preview')?.addEventListener('click', loadNeoLibraryOutputIntoPreview);
  $('btn-neo-library-output-apply-generation')?.addEventListener('click', () => applyNeoLibraryOutputReplay('generation'));
  $('btn-neo-library-output-apply-finish')?.addEventListener('click', () => applyNeoLibraryOutputReplay('finish'));
  $('btn-neo-library-output-rebuild-draft')?.addEventListener('click', () => applyNeoLibraryOutputReplay('rebuild'));
  $('btn-neo-library-output-send-positive')?.addEventListener('click', () => sendNeoLibraryOutputPositiveToPromptStudio().catch(() => {}));
  $('btn-neo-library-output-inspect-upload')?.addEventListener('click', () => inspectNeoLibraryUploadedOutput(false));
  $('btn-neo-library-output-compare-upload')?.addEventListener('click', () => inspectNeoLibraryUploadedOutput(true));
  $('btn-neo-library-output-clean')?.addEventListener('click', cleanNeoLibraryOutputPrompt);
  $('btn-neo-library-output-send-rebuilt')?.addEventListener('click', () => sendNeoLibraryRebuiltToPromptStudio().catch(() => {}));
  $('btn-neo-library-output-save-prompt')?.addEventListener('click', saveNeoLibraryOutputPrompt);
  $('btn-neo-library-output-save-character')?.addEventListener('click', saveNeoLibraryOutputCharacter);
});
