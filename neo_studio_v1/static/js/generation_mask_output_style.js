function hideMaskBrushCursor() {
  $('generation-mask-brush-cursor')?.classList.add('hidden');
}

async function openGenerationMaskEditor() {
  return window.NeoGenerationImageShell.openGenerationMaskEditor.apply(this, arguments);
}

function closeGenerationMaskEditor() {
  const modal = $('generation-mask-editor-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  generationMaskEditorState.drawing = false;
  generationMaskEditorState.lastPoint = null;
  generationMaskEditorState.brushMode = 'paint';
  endMaskEditorPan();
  hideMaskBrushCursor();
  if ($('backend-manager-modal')?.classList.contains('hidden') !== false && $('generation-image-zoom-modal')?.classList.contains('hidden') !== false) document.body.classList.remove('modal-open');
}

function startMaskEditorStroke(event) {
  const drawCanvas = $('generation-mask-draw-canvas');
  if (!drawCanvas) return;
  if (startMaskEditorPan(event)) return;
  generationMaskEditorState.drawing = true;
  generationMaskEditorState.brushMode = getMaskBrushModeFromEvent(event);
  const point = pointerPosInCanvas(drawCanvas, event);
  generationMaskEditorState.lastPoint = point;
  updateMaskBrushCursor(event);
  drawMaskDot(point.x, point.y, generationMaskEditorState.brushMode);
}

function moveMaskEditorStroke(event) {
  const drawCanvas = $('generation-mask-draw-canvas');
  if (!drawCanvas) return;
  if (moveMaskEditorPan(event)) return;
  updateMaskBrushCursor(event);
  if (!generationMaskEditorState.drawing) return;
  const point = pointerPosInCanvas(drawCanvas, event);
  drawMaskLine(generationMaskEditorState.lastPoint || point, point, generationMaskEditorState.brushMode);
  generationMaskEditorState.lastPoint = point;
}

function endMaskEditorStroke() {
  endMaskEditorPan();
  generationMaskEditorState.drawing = false;
  generationMaskEditorState.lastPoint = null;
  generationMaskEditorState.brushMode = 'paint';
}

function clearMaskEditor() {
  clearMaskPreviewCanvas($('generation-mask-draw-canvas'));
  fillMaskCanvasBlack(generationMaskEditorState.exportCanvas);
}

function invertMaskEditor() {
  invertMaskEditorCanvas(generationMaskEditorState.exportCanvas);
  syncMaskPreviewFromExport();
}

async function saveMaskEditorToInput() {
  const exportCanvas = generationMaskEditorState.exportCanvas;
  if (!exportCanvas) return;
  const feather = Math.max(0, Number($('generation-mask-feather')?.value || 0) || 0);
  let finalCanvas = exportCanvas;
  if (feather > 0) {
    const softCanvas = document.createElement('canvas');
    softCanvas.width = exportCanvas.width;
    softCanvas.height = exportCanvas.height;
    const sctx = softCanvas.getContext('2d');
    sctx.fillStyle = '#000';
    sctx.fillRect(0, 0, softCanvas.width, softCanvas.height);
    sctx.filter = `blur(${feather}px)`;
    sctx.drawImage(exportCanvas, 0, 0);
    sctx.filter = 'none';
    finalCanvas = softCanvas;
  }
  const blob = await new Promise(resolve => finalCanvas.toBlob(resolve, 'image/png'));
  if (!blob) {
    setStatus('generation-status', 'Could not save the mask image.', 'error');
    return;
  }
  const file = new File([blob], `mask_${Date.now()}.png`, { type:'image/png' });
  assignFileToInput('generation-mask-image', file);
  closeGenerationMaskEditor();
  setStatus('generation-status', feather > 0 ? `Mask saved with ${feather}px feather.` : 'Mask saved to the inpaint slot.', 'success');
}

function generationModeOutputFolder(mode='txt2img') {
  const value = String(mode || '').toLowerCase();
  if (value === 'img2img') return 'img2img-images';
  if (value === 'inpaint') return 'inpaint-images';
  if (value === 'outpaint') return 'outpaint-images';
  return 'txt2img-images';
}

function generationModeFromFolderName(folder='') {
  const value = String(folder || '').trim().toLowerCase();
  if (value === 'img2img-images') return 'img2img';
  if (value === 'inpaint-images') return 'inpaint';
  if (value === 'outpaint-images') return 'outpaint';
  return 'txt2img';
}

function inferGenerationPreviewSaveMode(output=null) {
  const row = output && typeof output === 'object' ? output : null;
  const explicit = String(row?.save_mode_override || row?.output_mode || row?.mode || '').trim().toLowerCase();
  if (['txt2img','img2img','inpaint','outpaint'].includes(explicit)) return explicit;
  const fromFolder = generationModeFromFolderName(row?.mode_folder || row?.save?.mode_folder || '');
  if (fromFolder) return fromFolder;
  const savedPath = String(row?.saved_path || '').replace(/\\/g, '/').toLowerCase();
  if (savedPath.includes('/img2img-images/')) return 'img2img';
  if (savedPath.includes('/inpaint-images/')) return 'inpaint';
  if (savedPath.includes('/outpaint-images/')) return 'outpaint';
  if (savedPath.includes('/txt2img-images/')) return 'txt2img';
  return 'txt2img';
}

function collectGenerationOutputSettings() {
  return {
    output_root: trim($('generation-output-root')?.value || ''),
    selected_category: $('generation-output-category')?.value || 'Uncategorized',
    filename_padding: 4,
  };
}

function updateGenerationOutputDestinationPreview(seedHint='[seed]') {
  const root = trim($('generation-output-root')?.value || '');
  const category = trim($('generation-output-category')?.value || 'Uncategorized') || 'Uncategorized';
  const mode = $('generation-workflow-type')?.value || 'txt2img';
  const modeFolder = generationModeOutputFolder(mode);
  const el = $('generation-output-destination');
  if (!el) return;
  const slug = category.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'uncategorized';
  const folder = root ? `${root.replace(/[\/]+$/, '')}\${modeFolder}\${category}` : `${modeFolder}\${category}`;
  const nextIndex = String(Number(generationOutputNextIndex || 1) || 1).padStart(4, '0');
  el.textContent = `Save destination: ${folder}\${slug}_${nextIndex}_${seedHint}.png`;
}

function applyGenerationOutputSettings(settings) {
  if (!settings || typeof settings !== 'object') return;
  generationOutputSettingsLoaded = true;
  generationOutputNextIndex = Number(settings.next_index || 1) || 1;
  if ($('generation-output-root')) $('generation-output-root').value = settings.output_root || '';
  const select = $('generation-output-category');
  if (select) {
    const categories = Array.isArray(settings.categories) && settings.categories.length ? settings.categories : ['Uncategorized'];
    const current = String(settings.selected_category || select.value || 'Uncategorized');
    select.innerHTML = '';
    categories.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item;
      if (item === current) opt.selected = true;
      select.appendChild(opt);
    });
    select.value = current;
  }
  updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]');
}

async function loadGenerationOutputSettings() {
  try {
    const data = await safeFetchJson(`/api/generation/output-settings?_=${Date.now()}`, { cache:'no-store' });
    applyGenerationOutputSettings(data?.settings || {});
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not load output settings.', 'error');
  }
}

async function saveGenerationOutputSettings(partial={}) {
  const payload = { ...collectGenerationOutputSettings(), ...(partial || {}) };
  try {
    const data = await safeFetchJson('/api/generation/output-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    applyGenerationOutputSettings(data?.settings || payload);
    return data?.settings || payload;
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not save generation output settings.', 'error');
    return null;
  }
}

async function addGenerationOutputCategory() {
  const input = $('generation-output-category-new');
  const name = trim(input?.value || '');
  if (!name) {
    setStatus('generation-status', 'Type a category name first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson('/api/generation/output-settings/category', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, output_root: trim($('generation-output-root')?.value || '') }),
    });
    applyGenerationOutputSettings(data?.settings || {});
    if (input) input.value = '';
    scheduleGenerationDraftSave();
    setStatus('generation-status', `Category added: ${data?.settings?.selected_category || name}`);
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not add output category.', 'error');
  }
}

async function browseGenerationOutputRoot() {
  const formData = new FormData();
  formData.append('initial_path', trim($('generation-output-root')?.value || ''));
  try {
    setStatus('generation-status', 'Opening folder picker…');
    const res = await fetch('/api/pick-folder', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    if (data.path && $('generation-output-root')) {
      $('generation-output-root').value = data.path;
      updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]');
      await saveGenerationOutputSettings();
      scheduleGenerationDraftSave();
      setStatus('generation-status', `Output folder set: ${data.path}`);
      return;
    }
    setStatus('generation-status', 'Folder picker closed without selecting a folder.', 'warn');
  } catch (e) {
    setStatus('generation-status', e.message || 'Folder browse failed.', 'error');
  }
}

async function openGenerationOutputRoot() {
  const path = trim($('generation-output-root')?.value || '');
  if (!path) {
    setStatus('generation-status', 'Pick an output folder first.', 'warn');
    return;
  }
  const formData = new FormData();
  formData.append('path', path);
  try {
    const res = await fetch('/api/open-folder', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    setStatus('generation-status', data.message || `Opened: ${path}`);
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not open the output folder.', 'error');
  }
}

function getFilteredGenerationStyles() {
  const query = String(generationStyleSearchQuery || '').trim().toLowerCase();
  if (!query) return generationStyleLibrary.slice();
  return generationStyleLibrary.filter(style => String(style?.name || '').toLowerCase().includes(query));
}

function updateGenerationStyleSearchMeta() {
  const meta = $('generation-style-search-meta');
  if (!meta) return;
  const total = generationStyleLibrary.length;
  const shown = getFilteredGenerationStyles().length;
  if (!total) {
    meta.textContent = 'No saved styles yet.';
    return;
  }
  if (!String(generationStyleSearchQuery || '').trim()) {
    meta.textContent = `Showing all styles (${total}).`;
    return;
  }
  meta.textContent = `Showing ${shown} of ${total} styles.`;
}

function syncGenerationStyleEditingUI() {
  const note = $('generation-style-editing-state');
  const updateBtn = $('btn-generation-style-update');
  const editingName = trim(generationStyleEditingName || '');
  if (note) note.textContent = editingName ? `Editing style: ${editingName}` : 'No style loaded for editing.';
  if (updateBtn) updateBtn.toggleAttribute('disabled', !editingName);
}

function clearGenerationStyleEditingState({ clearFields=false } = {}) {
  generationStyleEditingName = '';
  if (clearFields) {
    if ($('generation-style-name')) $('generation-style-name').value = '';
    if ($('generation-style-positive')) $('generation-style-positive').value = '';
    if ($('generation-style-negative')) $('generation-style-negative').value = '';
  }
  syncGenerationStyleEditingUI();
}

function populateGenerationStyleSelect(keepValue=true) {
  const select = $('generation-style-select');
  if (!select) return;
  const current = keepValue ? String(select.value || '') : '';
  const styles = getFilteredGenerationStyles();
  select.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = styles.length ? 'Select a style…' : (generationStyleLibrary.length ? 'No styles match this search' : 'No styles loaded yet');
  select.appendChild(placeholder);
  styles.forEach(style => {
    const opt = document.createElement('option');
    opt.value = style.name || '';
    opt.textContent = style.name || '(unnamed style)';
    if (current && current === opt.value) opt.selected = true;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
  else select.value = '';
  updateGenerationStyleSearchMeta();
  syncGenerationStyleEditingUI();
}

function findGenerationStyle(name) {
  const key = String(name || '').trim().toLowerCase();
  return generationStyleLibrary.find(style => String(style.name || '').trim().toLowerCase() === key) || null;
}

function normalizeGenerationStyleName(name) {
  return String(name || '').trim().toLowerCase();
}

function sanitizeGenerationActiveStyles() {
  const seen = new Set();
  generationActiveStyles = (Array.isArray(generationActiveStyles) ? generationActiveStyles : []).filter(name => {
    const key = normalizeGenerationStyleName(name);
    if (!key || seen.has(key) || !findGenerationStyle(name)) return false;
    seen.add(key);
    return true;
  });
}

function isGenerationStyleAddonsEnabled() {
  return $('generation-style-enabled') ? !!$('generation-style-enabled').checked : true;
}

function isGenerationWildcardsEnabled() {
  return $('generation-wildcard-enabled') ? !!$('generation-wildcard-enabled').checked : true;
}

function composeGenerationStylePayload() {
  if (!isGenerationStyleAddonsEnabled()) return { target:'both', base_positive:'', base_negative:'', refine_positive:'', refine_negative:'' };
  const positiveParts = [];
  const negativeParts = [];
  sanitizeGenerationActiveStyles();
  generationActiveStyles.forEach(name => {
    const style = findGenerationStyle(name);
    if (!style) return;
    const pos = trim(style.prompt || '');
    const neg = trim(style.negative_prompt || '');
    if (pos) positiveParts.push(pos);
    if (neg) negativeParts.push(neg);
  });
  const manualPositive = trim($('generation-style-positive')?.value || '');
  const manualNegative = trim($('generation-style-negative')?.value || '');
  if (manualPositive) positiveParts.push(manualPositive);
  if (manualNegative) negativeParts.push(manualNegative);
  const mergedPositive = Array.from(new Set(positiveParts)).join(', ');
  const mergedNegative = Array.from(new Set(negativeParts)).join(', ');
  const target = normalizeGenerationPassTarget($('generation-style-pass-target')?.value || 'both');
  return {
    target,
    base_positive: target === 'finish' ? '' : mergedPositive,
    base_negative: target === 'finish' ? '' : mergedNegative,
    refine_positive: target === 'base' ? '' : mergedPositive,
    refine_negative: target === 'base' ? '' : mergedNegative,
  };
}

function renderGenerationActiveStyles() {
  const wrap = $('generation-style-active-list');
  if (!wrap) return;
  sanitizeGenerationActiveStyles();
  wrap.innerHTML = '';
  if (!generationActiveStyles.length) {
    const empty = document.createElement('div');
    empty.className = 'mini-note';
    empty.textContent = 'No active styles stacked yet.';
    wrap.appendChild(empty);
    return;
  }
  generationActiveStyles.forEach(name => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'generation-style-chip is-active';
    chip.title = `Remove style: ${name}`;
    chip.innerHTML = `<span class="generation-style-chip-mark">✓</span><span>${escapeHtml(name)}</span><span class="generation-style-chip-x">×</span>`;
    chip.addEventListener('click', () => removeGenerationActiveStyle(name));
    wrap.appendChild(chip);
  });
}

function removeGenerationActiveStyle(name) {
  const key = normalizeGenerationStyleName(name);
  generationActiveStyles = generationActiveStyles.filter(item => normalizeGenerationStyleName(item) !== key);
  renderGenerationActiveStyles();
  scheduleGenerationDraftSave();
  setStatus('generation-status', `Removed style: ${name}`);
}

function addSelectedGenerationStyle() {
  const selectedName = trim($('generation-style-select')?.value || '');
  const style = findGenerationStyle(selectedName);
  if (!style) {
    setStatus('generation-status', 'Pick a style first.', 'warn');
    return;
  }
  const key = normalizeGenerationStyleName(style.name || '');
  if (generationActiveStyles.some(item => normalizeGenerationStyleName(item) === key)) {
    setStatus('generation-status', `Style already added: ${style.name}`);
    return;
  }
  generationActiveStyles.push(style.name || selectedName);
  renderGenerationActiveStyles();
  scheduleGenerationDraftSave();
  setStatus('generation-status', `Style added: ${style.name}`);
}

function applyGenerationStyleToFields(style, { useName=true } = {}) {
  if (!style) return;
  if ($('generation-style-positive')) $('generation-style-positive').value = style.prompt || '';
  if ($('generation-style-negative')) $('generation-style-negative').value = style.negative_prompt || '';
  if (useName && $('generation-style-name')) $('generation-style-name').value = style.name || '';
  scheduleGenerationDraftSave();
}

function editSelectedGenerationStyle() {
  const selectedName = trim($('generation-style-select')?.value || '');
  const style = findGenerationStyle(selectedName);
  if (!style) {
    setStatus('generation-status', 'Pick a style first.', 'warn');
    return;
  }
  generationStyleEditingName = style.name || selectedName;
  applyGenerationStyleToFields(style);
  syncGenerationStyleEditingUI();
  setStatus('generation-status', `Loaded style for editing: ${generationStyleEditingName}`, 'success');
}

async function loadGenerationStyles(keepValue=true) {
  try {
    const data = await safeFetchJson(`/api/generation/styles?_=${Date.now()}`, { cache:'no-store' });
    generationStyleLibrary = Array.isArray(data?.styles) ? data.styles : [];
    populateGenerationStyleSelect(keepValue);
    sanitizeGenerationActiveStyles();
    renderGenerationActiveStyles();
    syncGenerationStyleEditingUI();
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not load style library.', 'error');
  }
}

async function saveGenerationStyle(isUpdate=false) {
  const name = trim($('generation-style-name')?.value || '');
  const prompt = $('generation-style-positive')?.value || '';
  const negativePrompt = $('generation-style-negative')?.value || '';
  const originalName = isUpdate ? trim(generationStyleEditingName || $('generation-style-select')?.value || '') : '';
  if (isUpdate && !originalName) {
    setStatus('generation-status', 'Click Edit Selected first, then update the loaded style.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson('/api/generation/styles/save', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ name, prompt, negative_prompt: negativePrompt, original_name: originalName }),
    });
    generationStyleLibrary = Array.isArray(data?.styles) ? data.styles : [];
    if ($('generation-style-select')) $('generation-style-select').value = name;
    if ($('generation-style-search')) generationStyleSearchQuery = $('generation-style-search').value || '';
    populateGenerationStyleSelect(false);
    if ($('generation-style-select')) $('generation-style-select').value = name;
    generationStyleEditingName = isUpdate ? name : '';
    sanitizeGenerationActiveStyles();
    renderGenerationActiveStyles();
    syncGenerationStyleEditingUI();
    setStatus('generation-status', isUpdate ? 'Style updated.' : 'Style saved.', 'success');
    scheduleGenerationDraftSave();
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not save the style.', 'error');
  }
}

async function duplicateGenerationStyle() {
  const sourceName = trim($('generation-style-select')?.value || '');
  const newName = trim($('generation-style-name')?.value || '') || `${sourceName} Copy`;
  try {
    const data = await safeFetchJson('/api/generation/styles/duplicate', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ source_name: sourceName, new_name: newName }),
    });
    generationStyleLibrary = Array.isArray(data?.styles) ? data.styles : [];
    populateGenerationStyleSelect(false);
    if ($('generation-style-select')) $('generation-style-select').value = newName;
    const style = findGenerationStyle(newName);
    if (style) {
      generationStyleEditingName = style.name || newName;
      applyGenerationStyleToFields(style);
    }
    syncGenerationStyleEditingUI();
    setStatus('generation-status', 'Style duplicated.', 'success');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not duplicate the style.', 'error');
  }
}

async function deleteGenerationStyle() {
  const name = trim($('generation-style-select')?.value || '');
  try {
    const data = await safeFetchJson('/api/generation/styles/delete', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ name }),
    });
    generationStyleLibrary = Array.isArray(data?.styles) ? data.styles : [];
    populateGenerationStyleSelect(false);
    clearGenerationStyleEditingState({ clearFields:true });
    sanitizeGenerationActiveStyles();
    renderGenerationActiveStyles();
    setStatus('generation-status', 'Style deleted.', 'success');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not delete the style.', 'error');
  }
}

async function importGenerationStylePack(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append('style_pack', file);
  try {
    const res = await fetch('/api/generation/styles/import', { method:'POST', body: formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    generationStyleLibrary = Array.isArray(data?.styles) ? data.styles : [];
    populateGenerationStyleSelect(false);
    sanitizeGenerationActiveStyles();
    renderGenerationActiveStyles();
    setStatus('generation-status', 'Style pack imported.', 'success');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not import the style pack.', 'error');
  }
}

function exportGenerationStylePack() {
  window.location.href = '/api/generation/styles/export';
}


function getGenerationDetailerEditorCanvases() {
  return {
    base: $('generation-detailer-editor-base'),
    overlay: $('generation-detailer-editor-overlay'),
    panel: $('generation-detailer-box-editor'),
    list: $('generation-detailer-editor-box-list'),
    note: $('generation-detailer-editor-note'),
  };
}

function findGenerationDetailerRowByUid(uid='') {
  const clean = String(uid || '').trim();
  if (!clean) return null;
  return document.querySelector(`#generation-detailer-extra-list .generation-detailer-row[data-uid="${clean.replace(/"/g, '\"')}"]`);
}

function getGenerationDetailerEditorActiveRow() {
  return generationDetailerBoxEditorState.scopeType === 'row'
    ? findGenerationDetailerRowByUid(generationDetailerBoxEditorState.scopeRowUid)
    : null;
}


function getGenerationDetailerScopeRow() {
  if (generationDetailerBoxEditorState.scopeType !== 'row' || !generationDetailerBoxEditorState.scopeRowUid) return null;
  return document.querySelector(`#generation-detailer-extra-list .generation-detailer-row[data-uid="${generationDetailerBoxEditorState.scopeRowUid}"]`);
}

function describeGenerationDetailerEditorScope() {
  const row = getGenerationDetailerEditorActiveRow();
  if (row) {
    const title = row.querySelector('.generation-unit-title')?.textContent?.trim() || 'Detailer pass';
    const index = row.querySelector('.generation-unit-index')?.textContent?.trim() || '';
    return `${title}${index ? ` ${index}` : ''}`.trim();
  }
  return 'Primary detailer pass';
}

function updateGenerationDetailerEditorScopeLabel() {
  const label = $('generation-detailer-editor-scope');
  if (label) label.textContent = `Editing ${describeGenerationDetailerEditorScope()}.`;
}

function setGenerationDetailerEditorScope(scope='primary', row=null) {
  saveGenerationDetailerEditorScopeSnapshot();
  if (scope === 'row' && row instanceof HTMLElement) {
    generationDetailerBoxEditorState.scopeType = 'row';
    generationDetailerBoxEditorState.scopeRowUid = row.dataset.uid || '';
  } else {
    generationDetailerBoxEditorState.scopeType = 'primary';
    generationDetailerBoxEditorState.scopeRowUid = '';
  }
  updateGenerationDetailerEditorScopeLabel();
  const snapshot = loadGenerationDetailerEditorScopeSnapshot();
  if (snapshot?.editorControls) applyGenerationDetailerEditorControlState(snapshot.editorControls);
  else applyGenerationDetailerEditorControlState();
  refreshGenerationDetailerHistoryUI();
  if ($('generation-detailer-box-editor')?.style.display !== 'none') hydrateGenerationDetailerBoxesFromTextarea();
}

function getGenerationDetailerEditorTargetTextarea() {
  const row = getGenerationDetailerEditorActiveRow();
  return row?.querySelector('.generation-detailer-manual-boxes') || $('generation-detailer-manual-boxes');
}

function getGenerationDetailerEditorScopeKey() {
  return generationDetailerBoxEditorState.scopeType === 'row'
    ? `row:${generationDetailerBoxEditorState.scopeRowUid || ''}`
    : 'primary';
}

function cloneGenerationDetailerBoxes(boxes=[]) {
  return (Array.isArray(boxes) ? boxes : []).map(box => ({ ...box }));
}

function createGenerationDetailerTrackId() {
  generationDetailerTrackCounter += 1;
  return `subject-${generationDetailerTrackCounter}`;
}

function ensureGenerationDetailerBoxTrackId(box) {
  if (!box || typeof box !== 'object') return '';
  if (!box.track_id) box.track_id = createGenerationDetailerTrackId();
  return String(box.track_id || '');
}

function buildGenerationDetailerHistoryBoxes() {
  return (generationDetailerBoxEditorState.boxes || [])
    .filter(box => box && box.ignored !== true)
    .map(box => ({
      x: Number(box.x || 0),
      y: Number(box.y || 0),
      w: Number(box.w || 0),
      h: Number(box.h || 0),
      track_id: ensureGenerationDetailerBoxTrackId(box),
      pinned: !!box.pinned,
      locked: !!box.locked,
    }))
    .filter(box => box.w > 0 && box.h > 0);
}

function getGenerationDetailerScopeHistory() {
  const key = getGenerationDetailerEditorScopeKey();
  const snapshot = generationDetailerBoxEditorState.snapshots[key] || {};
  return Array.isArray(snapshot.history) ? snapshot.history : [];
}

function buildGenerationDetailerHistoryEntry(reason='manual') {
  const textarea = getGenerationDetailerEditorTargetTextarea();
  return {
    reason: String(reason || 'manual'),
    createdAt: new Date().toISOString(),
    imageName: generationDetailerBoxEditorState.imageName || '',
    boxes: cloneGenerationDetailerBoxes(generationDetailerBoxEditorState.boxes || []),
    previewSource: generationDetailerBoxEditorState.previewSource || 'manual',
    previewMeta: generationDetailerBoxEditorState.previewMeta ? JSON.parse(JSON.stringify(generationDetailerBoxEditorState.previewMeta)) : null,
    manualText: textarea?.value || '',
    editorControls: getGenerationDetailerEditorControlState(),
  };
}

function buildGenerationDetailerHistoryLabel(entry, index) {
  const time = entry?.createdAt ? String(entry.createdAt).slice(11, 19) : '--:--:--';
  const reason = String(entry?.reason || 'manual').replace(/_/g, ' ');
  const count = Array.isArray(entry?.boxes) ? entry.boxes.length : 0;
  return `${index + 1}. ${reason} · ${count} target${count === 1 ? '' : 's'} · ${time}`;
}

function refreshGenerationDetailerHistoryUI() {
  const select = $('generation-detailer-editor-history-select');
  if (!select) return;
  const history = getGenerationDetailerScopeHistory();
  select.innerHTML = '';
  if (!history.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No pass history yet';
    select.appendChild(option);
    select.value = '';
    return;
  }
  history.forEach((entry, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = buildGenerationDetailerHistoryLabel(entry, index);
    select.appendChild(option);
  });
  select.value = '0';
}

function saveGenerationDetailerHistoryEntry(reason='manual') {
  const key = getGenerationDetailerEditorScopeKey();
  const snapshot = generationDetailerBoxEditorState.snapshots[key] || { history: [] };
  const history = Array.isArray(snapshot.history) ? snapshot.history.slice() : [];
  const entry = buildGenerationDetailerHistoryEntry(reason);
  const signature = JSON.stringify({
    reason: entry.reason,
    manualText: entry.manualText,
    boxes: entry.boxes.map(box => ({ x:box.x, y:box.y, w:box.w, h:box.h, pinned:!!box.pinned, keep:box.keep !== false, ignored:!!box.ignored, track_id:box.track_id || '' })),
  });
  const last = history[0];
  const lastSignature = last ? JSON.stringify({
    reason: last.reason,
    manualText: last.manualText,
    boxes: (Array.isArray(last.boxes) ? last.boxes : []).map(box => ({ x:box.x, y:box.y, w:box.w, h:box.h, pinned:!!box.pinned, keep:box.keep !== false, ignored:!!box.ignored, track_id:box.track_id || '' })),
  }) : '';
  if (signature !== lastSignature) history.unshift(entry);
  generationDetailerBoxEditorState.snapshots[key] = { ...snapshot, history: history.slice(0, 8) };
  refreshGenerationDetailerHistoryUI();
}

function restoreGenerationDetailerHistoryEntry(index=0) {
  const history = getGenerationDetailerScopeHistory();
  const entry = history[Number(index)];
  if (!entry) throw new Error('Pick a saved history state first.');
  generationDetailerBoxEditorState.boxes = cloneGenerationDetailerBoxes(entry.boxes || []);
  generationDetailerBoxEditorState.previewSource = entry.previewSource || 'manual';
  generationDetailerBoxEditorState.previewMeta = entry.previewMeta ? JSON.parse(JSON.stringify(entry.previewMeta)) : null;
  if (entry.editorControls) applyGenerationDetailerEditorControlState(entry.editorControls);
  const textarea = getGenerationDetailerEditorTargetTextarea();
  if (textarea) textarea.value = String(entry.manualText || '');
  generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.findIndex(box => box.pinned === true && box.ignored !== true);
  if (generationDetailerBoxEditorState.activeIndex < 0) generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length ? 0 : -1;
  saveGenerationDetailerEditorScopeSnapshot();
  saveGenerationDetailerHistoryEntry('restore_history');
  renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
  setGenerationDetailerEditorNote(`Restored ${buildGenerationDetailerHistoryLabel(entry, Number(index))} for ${describeGenerationDetailerEditorScope()}.`);
}

function getGenerationDetailerEditorControlState() {
  return {
    priorityPreset: $('generation-detailer-editor-priority-preset')?.value || 'respect_pass',
    autoSuppressTiny: !!$('generation-detailer-editor-auto-suppress-tiny')?.checked,
    confidenceHeat: !!$('generation-detailer-editor-confidence-heat')?.checked,
    clusterMerge: !!$('generation-detailer-editor-cluster-merge')?.checked,
    foregroundBias: $('generation-detailer-editor-foreground-bias')?.value || 'off',
    tinyMainRatio: Number($('generation-detailer-editor-tiny-main-ratio')?.value || 0.18),
    tinyImageFloor: Number($('generation-detailer-editor-tiny-image-floor')?.value || 0.25),
  };
}

function updateGenerationDetailerSuppressionSliderLabels() {
  const ratio = Number($('generation-detailer-editor-tiny-main-ratio')?.value || 0.18);
  const floor = Number($('generation-detailer-editor-tiny-image-floor')?.value || 0.25);
  if ($('generation-detailer-editor-tiny-main-ratio-label')) $('generation-detailer-editor-tiny-main-ratio-label').textContent = `${ratio.toFixed(2)}×`;
  if ($('generation-detailer-editor-tiny-image-floor-label')) $('generation-detailer-editor-tiny-image-floor-label').textContent = `${floor.toFixed(2)}%`;
}

function applyGenerationDetailerThresholdTuningPreset(kind='balanced') {
  const presets = {
    lenient: { ratio:0.10, floor:0.10 },
    balanced: { ratio:0.18, floor:0.25 },
    strict: { ratio:0.26, floor:0.45 },
  };
  const preset = presets[String(kind || 'balanced').toLowerCase()] || presets.balanced;
  if ($('generation-detailer-editor-tiny-main-ratio')) $('generation-detailer-editor-tiny-main-ratio').value = String(preset.ratio);
  if ($('generation-detailer-editor-tiny-image-floor')) $('generation-detailer-editor-tiny-image-floor').value = String(preset.floor);
  updateGenerationDetailerSuppressionSliderLabels();
  saveGenerationDetailerEditorScopeSnapshot();
  setGenerationDetailerEditorNote(`Applied the ${String(kind || 'balanced')} threshold tuning preset for ${describeGenerationDetailerEditorScope()}.`);
}

function applyGenerationDetailerEditorControlState(state=null) {
  const values = state && typeof state === 'object' ? state : {};
  if ($('generation-detailer-editor-priority-preset')) $('generation-detailer-editor-priority-preset').value = values.priorityPreset || 'respect_pass';
  if ($('generation-detailer-editor-auto-suppress-tiny')) $('generation-detailer-editor-auto-suppress-tiny').checked = values.autoSuppressTiny !== false;
  if ($('generation-detailer-editor-confidence-heat')) $('generation-detailer-editor-confidence-heat').checked = values.confidenceHeat !== false;
  if ($('generation-detailer-editor-cluster-merge')) $('generation-detailer-editor-cluster-merge').checked = values.clusterMerge !== false;
  if ($('generation-detailer-editor-foreground-bias')) $('generation-detailer-editor-foreground-bias').value = values.foregroundBias || 'off';
  if ($('generation-detailer-editor-tiny-main-ratio')) $('generation-detailer-editor-tiny-main-ratio').value = String(values.tinyMainRatio ?? 0.18);
  if ($('generation-detailer-editor-tiny-image-floor')) $('generation-detailer-editor-tiny-image-floor').value = String(values.tinyImageFloor ?? 0.25);
  updateGenerationDetailerSuppressionSliderLabels();
}

function saveGenerationDetailerEditorScopeSnapshot() {
  const key = getGenerationDetailerEditorScopeKey();
  const textarea = getGenerationDetailerEditorTargetTextarea();
  const existing = generationDetailerBoxEditorState.snapshots[key] || {};
  generationDetailerBoxEditorState.snapshots[key] = {
    ...existing,
    boxes: cloneGenerationDetailerBoxes(generationDetailerBoxEditorState.boxes || []),
    previewSource: generationDetailerBoxEditorState.previewSource || 'manual',
    previewMeta: generationDetailerBoxEditorState.previewMeta ? JSON.parse(JSON.stringify(generationDetailerBoxEditorState.previewMeta)) : null,
    manualText: textarea?.value || '',
    editorControls: getGenerationDetailerEditorControlState(),
    history: Array.isArray(existing.history) ? existing.history : [],
  };
  refreshGenerationDetailerHistoryUI();
}

function loadGenerationDetailerEditorScopeSnapshot() {
  const key = getGenerationDetailerEditorScopeKey();
  return generationDetailerBoxEditorState.snapshots[key] || null;
}

function resetGenerationDetailerPreviewState(source='manual') {
  generationDetailerBoxEditorState.previewSource = source;
  generationDetailerBoxEditorState.previewMeta = null;
}

function getGenerationDetailerPreviewMergeMode() {
  const value = $('generation-detailer-editor-preview-merge')?.value || 'replace';
  return value === 'append' ? 'append' : 'replace';
}

function getGenerationDetailerBoxIoU(a, b) {
  if (!a || !b) return 0;
  const ax2 = Number(a.x || 0) + Number(a.w || 0);
  const ay2 = Number(a.y || 0) + Number(a.h || 0);
  const bx2 = Number(b.x || 0) + Number(b.w || 0);
  const by2 = Number(b.y || 0) + Number(b.h || 0);
  const interW = Math.max(0, Math.min(ax2, bx2) - Math.max(Number(a.x || 0), Number(b.x || 0)));
  const interH = Math.max(0, Math.min(ay2, by2) - Math.max(Number(a.y || 0), Number(b.y || 0)));
  if (!interW || !interH) return 0;
  const inter = interW * interH;
  const areaA = Math.max(1, Number(a.w || 0) * Number(a.h || 0));
  const areaB = Math.max(1, Number(b.w || 0) * Number(b.h || 0));
  return inter / Math.max(1, areaA + areaB - inter);
}

function mergeGenerationDetailerPreviewBoxes(existingBoxes=[], incomingBoxes=[], mode='replace') {
  const existing = cloneGenerationDetailerBoxes(existingBoxes);
  const incoming = cloneGenerationDetailerBoxes(incomingBoxes);
  const protectedExisting = existing.filter(box => (box.locked === true || box.pinned === true) && box.ignored !== true);
  const working = mode === 'append' ? existing.slice() : protectedExisting.slice();
  let added = 0;
  let skipped = 0;
  let refreshed = 0;

  incoming.forEach(box => {
    const duplicateIndex = working.findIndex(current => getGenerationDetailerBoxIoU(current, box) >= 0.72);
    if (duplicateIndex >= 0) {
      // Refresh pinned/locked duplicates with current detector selected/target_index data.
      const current = working[duplicateIndex] || {};
      working[duplicateIndex] = {
        ...box,
        locked: !!current.locked,
        pinned: !!current.pinned || !!box.pinned,
        ignored: current.ignored === true ? true : !!box.ignored,
        keep: current.ignored === true ? false : box.keep !== false,
        suppressed: current.ignored === true ? !!current.suppressed : !!box.suppressed,
        suppressed_reason: current.ignored === true ? (current.suppressed_reason || box.suppressed_reason || '') : (box.suppressed_reason || ''),
        track_id: current.track_id || box.track_id || '',
        reacquired: !!box.reacquired || !!current.reacquired,
        cluster_size: Number(box.cluster_size || current.cluster_size || 1),
      };
      skipped += 1;
      refreshed += 1;
      return;
    }
    working.push({
      ...box,
      locked: false,
      pinned: !!box.pinned,
      ignored: !!box.ignored,
      keep: box.ignored ? false : box.keep !== false,
      suppressed: !!box.suppressed,
      cluster_size: Number(box.cluster_size || 1),
    });
    added += 1;
  });
  return {
    boxes: working,
    added,
    skipped,
    refreshed,
    keptLocked: mode === 'append' ? 0 : protectedExisting.filter(box => box.locked === true).length,
    keptPinned: mode === 'append' ? 0 : protectedExisting.filter(box => box.pinned === true).length,
  };
}


function collectGenerationDetailerEditorPreviewConfig() {
  const row = getGenerationDetailerEditorActiveRow();
  return {
    provider: $('generation-detailer-provider')?.value || 'ultralytics',
    mode: row?.querySelector('.generation-detailer-mode')?.value || $('generation-detailer-mode')?.value || 'face',
    detector_type: row?.querySelector('.generation-detailer-detector-type')?.value || $('generation-detailer-detector-type')?.value || 'bbox',
    detector_model: trim(row?.querySelector('.generation-detailer-model')?.value || $('generation-detailer-model')?.value || ''),
    confidence: String($('generation-detailer-confidence')?.value || 0.35),
    top_k: String($('generation-detailer-topk')?.value || 0),
    bbox_grow: String($('generation-detailer-bbox-grow')?.value || 12),
    order_mode: row?.querySelector('.generation-detailer-order')?.value || $('generation-detailer-order')?.value || 'auto',
    start_index: String(row?.querySelector('.generation-detailer-start-index')?.value || $('generation-detailer-start-index')?.value || 1),
    count: String(row?.querySelector('.generation-detailer-count')?.value || $('generation-detailer-count')?.value || 1),
    min_area: String(row?.querySelector('.generation-detailer-min-area')?.value || $('generation-detailer-min-area')?.value || 0),
    max_area: String(row?.querySelector('.generation-detailer-max-area')?.value || $('generation-detailer-max-area')?.value || 0),
    custom_classes: trim($('generation-detailer-custom-classes')?.value || ''),
    custom_detector_root: trim($('generation-detailer-custom-detector-root')?.value || ''),
    priority_preset: $('generation-detailer-editor-priority-preset')?.value || 'respect_pass',
    auto_suppress_tiny_faces: $('generation-detailer-editor-auto-suppress-tiny')?.checked ? '1' : '0',
    cluster_merge: $('generation-detailer-editor-cluster-merge')?.checked ? '1' : '0',
    foreground_bias: $('generation-detailer-editor-foreground-bias')?.value || 'off',
    tiny_face_main_ratio: String($('generation-detailer-editor-tiny-main-ratio')?.value || 0.18),
    tiny_face_image_floor_pct: String($('generation-detailer-editor-tiny-image-floor')?.value || 0.25),
    pinned_boxes: JSON.stringify((generationDetailerBoxEditorState.boxes || []).filter(box => box?.pinned === true && box?.ignored !== true).map(box => ({ x:Number(box.x || 0), y:Number(box.y || 0), w:Number(box.w || 0), h:Number(box.h || 0) }))),
    history_boxes: JSON.stringify(buildGenerationDetailerHistoryBoxes()),
  };
}

function setGenerationDetailerEditorNote(message='') {
  const note = $('generation-detailer-editor-note');
  if (note) note.textContent = message || 'Load a source image or current output preview, drag to add boxes, or preview auto detections and keep only the targets you want Neo to repair. Subject-priority presets help focus on the main people first, while tiny-face suppression keeps background blur junk out of the sync.';
}

function showGenerationDetailerEditor(show=true) {
  const panel = $('generation-detailer-box-editor');
  if (panel) panel.style.display = show ? '' : 'none';
}

function parseGenerationDetailerManualBoxesText(raw='') {
  const boxes = [];
  String(raw || '').split(/\n+/).forEach(line => {
    const cleaned = line.trim();
    if (!cleaned) return;
    let mode = 'xywh';
    let body = cleaned;
    const lower = cleaned.toLowerCase();
    if (lower.startsWith('xyxy:')) { mode = 'xyxy'; body = cleaned.split(':', 2)[1] || ''; }
    else if (lower.startsWith('xywh:')) { body = cleaned.split(':', 2)[1] || ''; }
    const parts = body.split(',').map(part => part.trim()).filter(Boolean);
    if (parts.length !== 4) return;
    const nums = parts.map(part => Number(String(part).replace(/%$/, '')));
    if (nums.some(num => !Number.isFinite(num))) return;
    let x = 0, y = 0, w = 0, h = 0;
    if (mode === 'xyxy') {
      x = Math.min(nums[0], nums[2]);
      y = Math.min(nums[1], nums[3]);
      w = Math.abs(nums[2] - nums[0]);
      h = Math.abs(nums[3] - nums[1]);
    } else {
      [x, y, w, h] = nums;
    }
    if (w <= 0 || h <= 0) return;
    boxes.push({ x, y, w, h, keep:true, selected:true, source:'manual', label:`Box ${boxes.length + 1}`, locked:false, pinned:false, ignored:false, suppressed:false, suppressed_reason:'', group_key:'manual', group_label:'Manual targets', priority_rank:0, cluster_size:1, track_id:'', reacquired:false });
  });
  return boxes;
}

function syncGenerationDetailerBoxesToTextarea() {
  const textarea = getGenerationDetailerEditorTargetTextarea();
  if (!textarea) return;
  const lines = generationDetailerBoxEditorState.boxes
    .filter(box => box.keep !== false && box.ignored !== true)
    .map(box => `xywh:${Math.round(box.x)},${Math.round(box.y)},${Math.round(box.w)},${Math.round(box.h)}`);
  textarea.value = lines.join('\n');
  scheduleGenerationDraftSave();
  saveGenerationDetailerEditorScopeSnapshot();
}

function hydrateGenerationDetailerBoxesFromTextarea() {
  const textarea = getGenerationDetailerEditorTargetTextarea();
  const currentText = textarea?.value || '';
  const snapshot = loadGenerationDetailerEditorScopeSnapshot();
  if (snapshot && String(snapshot.manualText || '') === String(currentText || '')) {
    generationDetailerBoxEditorState.boxes = cloneGenerationDetailerBoxes(snapshot.boxes || []);
    generationDetailerBoxEditorState.previewSource = snapshot.previewSource || 'manual';
    generationDetailerBoxEditorState.previewMeta = snapshot.previewMeta ? JSON.parse(JSON.stringify(snapshot.previewMeta)) : null;
    if (snapshot.editorControls) applyGenerationDetailerEditorControlState(snapshot.editorControls);
  } else {
    resetGenerationDetailerPreviewState('manual');
    generationDetailerBoxEditorState.boxes = parseGenerationDetailerManualBoxesText(currentText);
  }
  generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length ? 0 : -1;
  renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
  saveGenerationDetailerEditorScopeSnapshot();
  refreshGenerationDetailerHistoryUI();
}

function getGenerationDetailerBoxGroupMeta(box) {
  if (!box) return { key:'active', label:'Active targets', order:30 };
  if (box.pinned) return { key:'pinned', label:'Pinned subjects', order:5 };
  if (box.ignored || box.suppressed) {
    const reason = String(box.suppressed_reason || '').trim();
    if (reason === 'tiny_background_face') return { key:'suppressed', label:'Suppressed tiny background faces', order:50 };
    return { key:'suppressed', label:'Suppressed / ignored targets', order:50 };
  }
  if (box.source === 'manual') {
    return { key:'manual', label:'Manual targets', order:10 };
  }
  if (box.group_key === 'primary' || box.priority_rank === 1) {
    return { key:'primary', label: box.group_label || 'Primary subject', order:10 };
  }
  if (box.group_key === 'secondary' || (box.priority_rank > 1 && box.priority_rank <= 3)) {
    return { key:'secondary', label: box.group_label || 'Secondary targets', order:20 };
  }
  if (box.selected === false) {
    return { key:'skipped', label: box.group_label || 'Skipped by current filters', order:40 };
  }
  return { key:'active', label: box.group_label || 'Additional active targets', order:30 };
}

function renderGenerationDetailerBoxList() {
  const list = $('generation-detailer-editor-box-list');
  if (!list) return;
  const boxes = generationDetailerBoxEditorState.boxes || [];
  if (!boxes.length) {
    list.innerHTML = '<div class="mini-note">No targets yet. Drag on the canvas, sync from the manual-box textarea, or preview auto detections from the source / current output image.</div>';
    return;
  }
  list.innerHTML = '';
  const groups = [];
  const groupMap = new Map();
  boxes.forEach((box, index) => {
    const meta = getGenerationDetailerBoxGroupMeta(box);
    const key = meta.key || 'active';
    if (!groupMap.has(key)) {
      const entry = { key, label: meta.label, order: meta.order, items: [] };
      groupMap.set(key, entry);
      groups.push(entry);
    }
    groupMap.get(key).items.push({ box, index });
  });
  groups.sort((a, b) => (a.order - b.order) || a.label.localeCompare(b.label));
  groups.forEach(group => {
    const section = document.createElement('div');
    section.style.display = 'flex';
    section.style.flexDirection = 'column';
    section.style.gap = '8px';
    const heading = document.createElement('div');
    heading.className = 'mini-note';
    heading.style.fontWeight = '700';
    heading.style.letterSpacing = '.01em';
    heading.textContent = `${group.label} · ${group.items.length}`;
    section.appendChild(heading);
    group.items.forEach(({ box, index }) => {
      const item = document.createElement('div');
      item.className = 'card-lite';
      item.style.padding = '10px';
      item.style.border = generationDetailerBoxEditorState.activeIndex === index ? '1px solid rgba(99,179,237,.85)' : '1px solid rgba(255,255,255,.08)';
      const sourceLabel = box.source === 'auto' ? 'auto' : 'manual';
      const confidenceLabel = Number.isFinite(Number(box.confidence)) && Number(box.confidence) > 0 ? ` · conf ${Number(box.confidence).toFixed(2)}` : '';
      const tagLabel = box.label ? ` · ${escapeHtml(String(box.label))}` : '';
      const clusterLabel = Number(box.cluster_size || 1) > 1 ? ` · cluster ${Math.max(1, Number(box.cluster_size || 1))}` : '';
      const trackLabel = box.track_id ? ` · ${escapeHtml(String(box.track_id))}` : '';
      const flagParts = [];
      if (box.selected === false && !box.ignored) flagParts.push('Skipped by current filters');
      else if (!box.ignored) flagParts.push('Selected by current filters');
      if (box.target_index > 0) flagParts.push(`Target #${box.target_index}`);
      if (box.prompt_index > 0) flagParts.push(`Prompt ${box.prompt_index}`);
      if (box.priority_rank > 0) flagParts.push(`Priority ${box.priority_rank}`);
      if (box.locked) flagParts.push('Locked');
      if (box.pinned) flagParts.push('Pinned');
      if (box.reacquired) flagParts.push('Reacquired');
      if (box.suppressed_reason === 'tiny_background_face') flagParts.push('Tiny background face');
      else if (box.ignored) flagParts.push('Ignored');
      const selectionLabel = flagParts.join(' · ');
      item.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:center;">
          <div>
            <div style="font-weight:600;">${box.target_index > 0 ? `#${box.target_index}` : `Target ${index + 1}`} <span class="badge${box.keep !== false && box.ignored !== true ? ' ok' : ''}" style="margin-left:6px;">${escapeHtml(sourceLabel)}</span>${box.locked ? '<span class="badge ok" style="margin-left:6px;">lock</span>' : ''}${box.pinned ? '<span class="badge ok" style="margin-left:6px;">pin</span>' : ''}${box.ignored ? '<span class="badge" style="margin-left:6px;">ignore</span>' : ''}</div>
            <div class="mini-note">x ${Math.round(box.x)} · y ${Math.round(box.y)} · w ${Math.round(box.w)} · h ${Math.round(box.h)}${tagLabel}${confidenceLabel}${clusterLabel}${trackLabel}</div>
            ${box.source === 'auto' && Number.isFinite(Number(box.confidence)) && Number(box.confidence) > 0 ? `<div style="margin-top:4px; width:160px; max-width:100%; height:6px; border-radius:999px; background:rgba(255,255,255,.08); overflow:hidden;"><div style="height:100%; width:${Math.max(0, Math.min(100, Number(box.confidence) * 100)).toFixed(1)}%; background:hsl(${Math.round(Math.max(0, Math.min(1, Number(box.confidence))) * 120)} 92% 58%);"></div></div>` : ''}
            <div class="mini-note">${escapeHtml(selectionLabel || group.label)}</div>
          </div>
          <div class="row" style="gap:8px; align-items:center; flex-wrap:wrap; justify-content:flex-end;">
            <label class="generation-toggle-pill"><input class="generation-detailer-editor-keep" type="checkbox" ${box.keep !== false && box.ignored !== true ? 'checked' : ''}/> Keep</label>
            <button class="btn btn-small generation-detailer-editor-lock" type="button">${box.locked ? 'Unlock' : 'Lock'}</button>
            <button class="btn btn-small generation-detailer-editor-pin" type="button">${box.pinned ? 'Unpin' : 'Pin'}</button>
            <button class="btn btn-small generation-detailer-editor-ignore" type="button">${box.ignored ? 'Unignore' : 'Ignore'}</button>
            <button class="btn btn-small generation-detailer-editor-remove" type="button">Remove</button>
          </div>
        </div>`;
      item.addEventListener('click', (event) => {
        if (event.target.closest('button') || event.target.closest('input')) return;
        generationDetailerBoxEditorState.activeIndex = index;
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      item.querySelector('.generation-detailer-editor-keep')?.addEventListener('change', (event) => {
        box.keep = !!event.target.checked;
        if (box.keep) box.ignored = false;
        generationDetailerBoxEditorState.activeIndex = index;
        syncGenerationDetailerBoxesToTextarea();
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      item.querySelector('.generation-detailer-editor-lock')?.addEventListener('click', (event) => {
        event.preventDefault();
        box.locked = !box.locked;
        generationDetailerBoxEditorState.activeIndex = index;
        saveGenerationDetailerEditorScopeSnapshot();
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      item.querySelector('.generation-detailer-editor-pin')?.addEventListener('click', (event) => {
        event.preventDefault();
        box.pinned = !box.pinned;
        if (box.pinned) {
          ensureGenerationDetailerBoxTrackId(box);
          box.keep = true;
          box.ignored = false;
        }
        generationDetailerBoxEditorState.activeIndex = index;
        saveGenerationDetailerEditorScopeSnapshot();
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      item.querySelector('.generation-detailer-editor-ignore')?.addEventListener('click', (event) => {
        event.preventDefault();
        box.ignored = !box.ignored;
        box.suppressed = box.ignored && box.suppressed_reason === 'tiny_background_face';
        if (box.ignored) box.keep = false;
        generationDetailerBoxEditorState.activeIndex = index;
        syncGenerationDetailerBoxesToTextarea();
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      item.querySelector('.generation-detailer-editor-remove')?.addEventListener('click', (event) => {
        event.preventDefault();
        generationDetailerBoxEditorState.boxes.splice(index, 1);
        if (generationDetailerBoxEditorState.activeIndex >= generationDetailerBoxEditorState.boxes.length) generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length - 1;
        syncGenerationDetailerBoxesToTextarea();
        renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      });
      section.appendChild(item);
    });
    list.appendChild(section);
  });
}


function getGenerationDetailerConfidenceHeatStyle(box, isActive=false) {
  const confidence = Number(box?.confidence || 0);
  if ($('generation-detailer-editor-confidence-heat')?.checked !== true || box?.source !== 'auto' || !Number.isFinite(confidence) || confidence <= 0) return null;
  const clamped = Math.max(0, Math.min(1, confidence));
  const hue = Math.round(clamped * 120);
  return {
    stroke: `hsla(${hue}, 92%, 58%, ${isActive ? 0.98 : 0.92})`,
    fill: `hsla(${hue}, 92%, 58%, ${isActive ? 0.22 : 0.14})`,
  };
}

function getGenerationDetailerCanvasScales(base, overlay, image) {
  return {
    scaleX: (base?.width || overlay?.width || 1) / (image?.naturalWidth || base?.width || overlay?.width || 1),
    scaleY: (base?.height || overlay?.height || 1) / (image?.naturalHeight || base?.height || overlay?.height || 1),
  };
}

function getGenerationDetailerDisplayRect(box, scaleX, scaleY) {
  return {
    x: Number(box?.x || 0) * scaleX,
    y: Number(box?.y || 0) * scaleY,
    w: Number(box?.w || 0) * scaleX,
    h: Number(box?.h || 0) * scaleY,
  };
}

function getGenerationDetailerHandleAtPoint(point, rect) {
  const size = 9;
  const handles = {
    nw: { x: rect.x, y: rect.y },
    ne: { x: rect.x + rect.w, y: rect.y },
    sw: { x: rect.x, y: rect.y + rect.h },
    se: { x: rect.x + rect.w, y: rect.y + rect.h },
  };
  return Object.entries(handles).find(([, pos]) => Math.abs(point.x - pos.x) <= size && Math.abs(point.y - pos.y) <= size)?.[0] || '';
}

function findGenerationDetailerHitTarget(point, scaleX, scaleY) {
  const boxes = generationDetailerBoxEditorState.boxes || [];
  if (generationDetailerBoxEditorState.activeIndex >= 0 && boxes[generationDetailerBoxEditorState.activeIndex]) {
    const activeRect = getGenerationDetailerDisplayRect(boxes[generationDetailerBoxEditorState.activeIndex], scaleX, scaleY);
    const handle = getGenerationDetailerHandleAtPoint(point, activeRect);
    if (handle) return { type:'resize', index:generationDetailerBoxEditorState.activeIndex, handle };
  }
  for (let index = boxes.length - 1; index >= 0; index -= 1) {
    const rect = getGenerationDetailerDisplayRect(boxes[index], scaleX, scaleY);
    if (point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h) {
      return { type:'move', index };
    }
  }
  return null;
}

function renderGenerationDetailerEditorCanvas() {
  const { base, overlay } = getGenerationDetailerEditorCanvases();
  const image = generationDetailerBoxEditorState.image;
  if (!base || !overlay) return;
  const displayWidth = generationDetailerBoxEditorState.displayWidth || image?.naturalWidth || 0;
  const displayHeight = generationDetailerBoxEditorState.displayHeight || image?.naturalHeight || 0;
  if (!displayWidth || !displayHeight) {
    const bctx = base.getContext('2d');
    const octx = overlay.getContext('2d');
    bctx?.clearRect(0, 0, base.width, base.height);
    octx?.clearRect(0, 0, overlay.width, overlay.height);
    return;
  }
  if (base.width !== displayWidth || base.height !== displayHeight) { base.width = displayWidth; base.height = displayHeight; }
  if (overlay.width !== displayWidth || overlay.height !== displayHeight) { overlay.width = displayWidth; overlay.height = displayHeight; }
  const displayWidthPx = `${displayWidth}px`;
  const displayHeightPx = `${displayHeight}px`;
  if (base.style.width !== displayWidthPx) base.style.width = displayWidthPx;
  if (base.style.height !== displayHeightPx) base.style.height = displayHeightPx;
  if (overlay.style.width !== displayWidthPx) overlay.style.width = displayWidthPx;
  if (overlay.style.height !== displayHeightPx) overlay.style.height = displayHeightPx;
  const stage = base.parentElement;
  if (stage) {
    if (stage.style.width !== displayWidthPx) stage.style.width = displayWidthPx;
    if (stage.style.maxWidth !== '100%') stage.style.maxWidth = '100%';
  }
  const bctx = base.getContext('2d');
  const octx = overlay.getContext('2d');
  if (!bctx || !octx) return;
  bctx.clearRect(0, 0, base.width, base.height);
  if (image) bctx.drawImage(image, 0, 0, base.width, base.height);
  octx.clearRect(0, 0, overlay.width, overlay.height);
  const { scaleX, scaleY } = getGenerationDetailerCanvasScales(base, overlay, image);
  (generationDetailerBoxEditorState.boxes || []).forEach((box, index) => {
    const { x, y, w, h } = getGenerationDetailerDisplayRect(box, scaleX, scaleY);
    const isActive = generationDetailerBoxEditorState.activeIndex === index;
    const isIgnored = box.ignored === true || box.keep === false;
    const isLocked = box.locked === true;
    octx.save();
    octx.lineWidth = isActive ? 3 : 2;
    const heatStyle = getGenerationDetailerConfidenceHeatStyle(box, isActive);
    octx.strokeStyle = isIgnored ? 'rgba(255,120,120,0.95)' : isLocked ? 'rgba(99,179,237,0.95)' : (heatStyle?.stroke || 'rgba(255,214,102,0.95)');
    octx.fillStyle = isIgnored ? 'rgba(255,120,120,0.14)' : isLocked ? 'rgba(99,179,237,0.14)' : (heatStyle?.fill || 'rgba(255,214,102,0.14)');
    octx.fillRect(x, y, w, h);
    octx.strokeRect(x, y, w, h);
    const primaryNumber = Number(box.target_index || box.priority_rank || 0);
    const overlayParts = [primaryNumber > 0 ? `#${primaryNumber}` : String(index + 1)];
    if (box.track_id) overlayParts.push(String(box.track_id));
    if (box.source === 'auto' && box.label) overlayParts.push(String(box.label));
    else if (box.source !== 'auto') overlayParts.push('manual');
    if (box.locked) overlayParts.push('lock');
    if (box.pinned) overlayParts.push('pin');
    if (box.reacquired) overlayParts.push('re');
    if (Number(box.cluster_size || 1) > 1) overlayParts.push(`c${Math.max(1, Number(box.cluster_size || 1))}`);
    if (box.suppressed_reason === 'tiny_background_face') overlayParts.push('tiny-bg');
    else if (box.ignored) overlayParts.push('ignore');
    if (Number.isFinite(Number(box.confidence)) && Number(box.confidence) > 0) overlayParts.push(Number(box.confidence).toFixed(2));
    const overlayText = overlayParts.join(' · ');
    octx.font = 'bold 16px sans-serif';
    const metrics = octx.measureText(overlayText);
    const badgeWidth = Math.min(base.width - x, Math.max(64, Math.ceil(metrics.width) + 22));
    octx.fillStyle = 'rgba(12,18,30,0.92)';
    octx.fillRect(x, Math.max(0, y - 26), badgeWidth, 24);
    octx.fillStyle = '#fff';
    octx.fillText(overlayText, x + 10, Math.max(17, y - 9));
    if (isActive) {
      const handles = [
        [x, y],
        [x + w, y],
        [x, y + h],
        [x + w, y + h],
      ];
      handles.forEach(([hx, hy]) => {
        octx.fillStyle = 'rgba(12,18,30,0.95)';
        octx.fillRect(hx - 4, hy - 4, 8, 8);
        octx.strokeStyle = '#ffffff';
        octx.strokeRect(hx - 4, hy - 4, 8, 8);
      });
    }
    octx.restore();
  });
  if (generationDetailerBoxEditorState.drawing && generationDetailerBoxEditorState.dragMode === 'draw') {
    const x = Math.min(generationDetailerBoxEditorState.startX, generationDetailerBoxEditorState.currentX);
    const y = Math.min(generationDetailerBoxEditorState.startY, generationDetailerBoxEditorState.currentY);
    const w = Math.abs(generationDetailerBoxEditorState.currentX - generationDetailerBoxEditorState.startX);
    const h = Math.abs(generationDetailerBoxEditorState.currentY - generationDetailerBoxEditorState.startY);
    octx.save();
    octx.setLineDash([6, 4]);
    octx.lineWidth = 2;
    octx.strokeStyle = 'rgba(99,179,237,1)';
    octx.strokeRect(x, y, w, h);
    octx.restore();
  }
}

function getGenerationDetailerCanvasPoint(event) {
  const overlay = $('generation-detailer-editor-overlay');
  if (!overlay) return null;
  const rect = overlay.getBoundingClientRect();
  const width = Math.max(1, overlay.clientWidth || rect.width || overlay.width || 1);
  const height = Math.max(1, overlay.clientHeight || rect.height || overlay.height || 1);
  return {
    x: Math.max(0, Math.min(width, event.clientX - rect.left)),
    y: Math.max(0, Math.min(height, event.clientY - rect.top)),
  };
}

function commitGenerationDetailerDrawBox() {
  const overlay = $('generation-detailer-editor-overlay');
  const image = generationDetailerBoxEditorState.image;
  if (!overlay || !image) return;
  const x = Math.min(generationDetailerBoxEditorState.startX, generationDetailerBoxEditorState.currentX);
  const y = Math.min(generationDetailerBoxEditorState.startY, generationDetailerBoxEditorState.currentY);
  const w = Math.abs(generationDetailerBoxEditorState.currentX - generationDetailerBoxEditorState.startX);
  const h = Math.abs(generationDetailerBoxEditorState.currentY - generationDetailerBoxEditorState.startY);
  if (w < 8 || h < 8) return;
  const canvasWidth = Math.max(1, overlay.clientWidth || overlay.width || 1);
  const canvasHeight = Math.max(1, overlay.clientHeight || overlay.height || 1);
  const scaleX = (image.naturalWidth || canvasWidth || 1) / canvasWidth;
  const scaleY = (image.naturalHeight || canvasHeight || 1) / canvasHeight;
  generationDetailerBoxEditorState.boxes.push({
    x: Math.round(x * scaleX),
    y: Math.round(y * scaleY),
    w: Math.round(w * scaleX),
    h: Math.round(h * scaleY),
    keep: true,
    selected: true,
    source: 'manual',
    label: `Box ${generationDetailerBoxEditorState.boxes.length + 1}` ,
    locked: false,
    ignored: false,
  });
  generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length - 1;
  syncGenerationDetailerBoxesToTextarea();
  renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
}

async function loadGenerationDetailerEditorFromFile(file, label='image') {
  if (!(file instanceof File)) throw new Error('No image file is available for the visual box drawer.');
  const url = URL.createObjectURL(file);
  const image = new Image();
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = reject;
    image.src = url;
  });
  if (generationDetailerBoxEditorState.imageUrl) {
    try { URL.revokeObjectURL(generationDetailerBoxEditorState.imageUrl); } catch (_) {}
  }
  generationDetailerBoxEditorState.imageUrl = url;
  generationDetailerBoxEditorState.image = image;
  generationDetailerBoxEditorState.imageName = file.name || label;
  const maxWidth = 720;
  const ratio = image.naturalWidth > maxWidth ? (maxWidth / image.naturalWidth) : 1;
  generationDetailerBoxEditorState.displayWidth = Math.max(1, Math.round(image.naturalWidth * ratio));
  generationDetailerBoxEditorState.displayHeight = Math.max(1, Math.round(image.naturalHeight * ratio));
  showGenerationDetailerEditor(true);
  updateGenerationDetailerEditorScopeLabel();
  setGenerationDetailerEditorNote(`Loaded ${label}: ${file.name || 'image'} for ${describeGenerationDetailerEditorScope()}. Drag on the canvas to add targets, move boxes, pull resize handles, or preview auto detections and uncheck any row you want Neo to skip.`);
  hydrateGenerationDetailerBoxesFromTextarea();
  refreshGenerationDetailerHistoryUI();
}

async function openGenerationDetailerEditorFromSource() {
  const file = $('generation-source-image')?.files?.[0] || null;
  if (!file) throw new Error('Load a source image first or use the current output preview.');
  await loadGenerationDetailerEditorFromFile(file, 'source image');
}

async function openGenerationDetailerEditorFromPreview() {
  const file = await fetchGenerationPreviewFile();
  await loadGenerationDetailerEditorFromFile(file, 'current output preview');
}

function bindGenerationDetailerEditorCanvas() {
  const overlay = $('generation-detailer-editor-overlay');
  if (!overlay || overlay.dataset.drawerBound === 'true') return;
  overlay.dataset.drawerBound = 'true';
  overlay.addEventListener('pointerdown', (event) => {
    if (!generationDetailerBoxEditorState.image) return;
    const point = getGenerationDetailerCanvasPoint(event);
    if (!point) return;
    const { scaleX, scaleY } = getGenerationDetailerCanvasScales(overlay, overlay, generationDetailerBoxEditorState.image);
    const hit = findGenerationDetailerHitTarget(point, scaleX, scaleY);
    if (hit) {
      generationDetailerBoxEditorState.activeIndex = hit.index;
      generationDetailerBoxEditorState.drawing = true;
      generationDetailerBoxEditorState.dragMode = hit.type;
      generationDetailerBoxEditorState.activeHandle = hit.handle || '';
      generationDetailerBoxEditorState.dragStartX = point.x;
      generationDetailerBoxEditorState.dragStartY = point.y;
      generationDetailerBoxEditorState.boxStart = { ...(generationDetailerBoxEditorState.boxes[hit.index] || {}) };
      generationDetailerBoxEditorState.dragPointerId = event.pointerId;
      overlay.setPointerCapture?.(event.pointerId);
      renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
      return;
    }
    generationDetailerBoxEditorState.drawing = true;
    generationDetailerBoxEditorState.dragMode = 'draw';
    generationDetailerBoxEditorState.dragPointerId = event.pointerId;
    generationDetailerBoxEditorState.startX = point.x;
    generationDetailerBoxEditorState.startY = point.y;
    generationDetailerBoxEditorState.currentX = point.x;
    generationDetailerBoxEditorState.currentY = point.y;
    overlay.setPointerCapture?.(event.pointerId);
    renderGenerationDetailerEditorCanvas();
  });
  overlay.addEventListener('pointermove', (event) => {
    if (!generationDetailerBoxEditorState.drawing) return;
    const point = getGenerationDetailerCanvasPoint(event);
    if (!point) return;
    if (generationDetailerBoxEditorState.dragMode === 'draw') {
      generationDetailerBoxEditorState.currentX = point.x;
      generationDetailerBoxEditorState.currentY = point.y;
      renderGenerationDetailerEditorCanvas();
      return;
    }
    const activeBox = generationDetailerBoxEditorState.boxes[generationDetailerBoxEditorState.activeIndex];
    const image = generationDetailerBoxEditorState.image;
    if (!activeBox || !image || !generationDetailerBoxEditorState.boxStart) return;
    const canvasWidth = Math.max(1, overlay.clientWidth || overlay.width || 1);
    const canvasHeight = Math.max(1, overlay.clientHeight || overlay.height || 1);
    const scaleX = (image.naturalWidth || canvasWidth || 1) / canvasWidth;
    const scaleY = (image.naturalHeight || canvasHeight || 1) / canvasHeight;
    const deltaX = (point.x - generationDetailerBoxEditorState.dragStartX) * scaleX;
    const deltaY = (point.y - generationDetailerBoxEditorState.dragStartY) * scaleY;
    const start = generationDetailerBoxEditorState.boxStart;
    if (generationDetailerBoxEditorState.dragMode === 'move') {
      activeBox.x = Math.max(0, Math.min((image.naturalWidth || 1) - start.w, Math.round(start.x + deltaX)));
      activeBox.y = Math.max(0, Math.min((image.naturalHeight || 1) - start.h, Math.round(start.y + deltaY)));
    } else if (generationDetailerBoxEditorState.dragMode === 'resize') {
      let left = start.x;
      let top = start.y;
      let right = start.x + start.w;
      let bottom = start.y + start.h;
      if (generationDetailerBoxEditorState.activeHandle.includes('n')) top = Math.round(Math.min(bottom - 12, Math.max(0, start.y + deltaY)));
      if (generationDetailerBoxEditorState.activeHandle.includes('s')) bottom = Math.round(Math.max(top + 12, Math.min(image.naturalHeight || bottom, start.y + start.h + deltaY)));
      if (generationDetailerBoxEditorState.activeHandle.includes('w')) left = Math.round(Math.min(right - 12, Math.max(0, start.x + deltaX)));
      if (generationDetailerBoxEditorState.activeHandle.includes('e')) right = Math.round(Math.max(left + 12, Math.min(image.naturalWidth || right, start.x + start.w + deltaX)));
      activeBox.x = left;
      activeBox.y = top;
      activeBox.w = Math.max(12, right - left);
      activeBox.h = Math.max(12, bottom - top);
    }
    renderGenerationDetailerEditorCanvas();
    renderGenerationDetailerBoxList();
  });
  const finish = (event) => {
    if (!generationDetailerBoxEditorState.drawing) return;
    if (event && generationDetailerBoxEditorState.dragPointerId != null) {
      try { overlay.releasePointerCapture?.(generationDetailerBoxEditorState.dragPointerId); } catch (_) {}
    }
    const mode = generationDetailerBoxEditorState.dragMode;
    generationDetailerBoxEditorState.drawing = false;
    generationDetailerBoxEditorState.dragMode = '';
    generationDetailerBoxEditorState.activeHandle = '';
    generationDetailerBoxEditorState.boxStart = null;
    if (mode === 'draw') {
      commitGenerationDetailerDrawBox();
      return;
    }
    syncGenerationDetailerBoxesToTextarea();
    renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
  };
  overlay.addEventListener('pointerup', finish);
  overlay.addEventListener('pointercancel', finish);
}

async function openGenerationDetailerEditor() {
  if (!generationDetailerScopeUsesManualBoxes(generationDetailerBoxEditorState.scopeType, generationDetailerBoxEditorState.scopeType === 'row' ? getGenerationDetailerScopeRow() : null)) {
    showGenerationDetailerEditor(false);
    setGenerationDetailerEditorNote('Manual target boxes are disabled for this pass because Target mode is set to Auto detect. Switch the pass to Manual boxes to use the visual box drawer.');
    return;
  }
  showGenerationDetailerEditor(true);
  bindGenerationDetailerEditorCanvas();
  if (generationDetailerBoxEditorState.image) {
    hydrateGenerationDetailerBoxesFromTextarea();
    setGenerationDetailerEditorNote(`Editing ${describeGenerationDetailerEditorScope()} on ${generationDetailerBoxEditorState.imageName || 'manual targets'}. Drag to add more boxes, preview auto detections, or toggle any row off.`);
    return;
  }
  if ($('generation-source-image')?.files?.[0]) {
    await openGenerationDetailerEditorFromSource();
    return;
  }
  if (generationPreviewActionTarget) {
    await openGenerationDetailerEditorFromPreview();
    return;
  }
  hydrateGenerationDetailerBoxesFromTextarea();
  setGenerationDetailerEditorNote(`Load a source image or current output preview for ${describeGenerationDetailerEditorScope()}, then drag on the canvas to add boxes or preview auto detections.`);
}

function buildGenerationDetailerPreviewFormData(file) {
  const config = collectGenerationDetailerEditorPreviewConfig();
  const formData = new FormData();
  formData.append('image', file);
  Object.entries(config).forEach(([key, value]) => {
    formData.append(key, String(value ?? ''));
  });
  return formData;
}

function sanitizeGenerationDetailerSnapshotFilename(name='detailer_snapshot') {
  return String(name || 'detailer_snapshot').toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'detailer_snapshot';
}

function buildGenerationDetailerSnapshotPayload() {
  const textarea = getGenerationDetailerEditorTargetTextarea();
  return {
    kind: 'neo_studio_detailer_detection_snapshot_v1',
    exported_at: new Date().toISOString(),
    scope_key: getGenerationDetailerEditorScopeKey(),
    scope_label: describeGenerationDetailerEditorScope(),
    image_name: generationDetailerBoxEditorState.imageName || '',
    preview_source: generationDetailerBoxEditorState.previewSource || 'manual',
    preview_meta: generationDetailerBoxEditorState.previewMeta ? JSON.parse(JSON.stringify(generationDetailerBoxEditorState.previewMeta)) : null,
    manual_boxes: textarea?.value || '',
    editor_controls: getGenerationDetailerEditorControlState(),
    boxes: cloneGenerationDetailerBoxes(generationDetailerBoxEditorState.boxes || []),
  };
}

function exportGenerationDetailerSnapshot() {
  const payload = buildGenerationDetailerSnapshotPayload();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type:'application/json' });
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = `${sanitizeGenerationDetailerSnapshotFilename(payload.scope_label || 'detailer_snapshot')}.json`;
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(href);
  }, 0);
  setStatus('generation-detailer-status', 'Detection snapshot exported.', 'success');
}

function normalizeImportedGenerationDetailerBoxes(boxes=[]) {
  return (Array.isArray(boxes) ? boxes : []).map((box, index) => ({
    x: Number(box?.x || 0),
    y: Number(box?.y || 0),
    w: Number(box?.w || 0),
    h: Number(box?.h || 0),
    keep: box?.keep !== false,
    selected: box?.selected !== false,
    source: box?.source || 'manual',
    label: box?.label || `Imported ${index + 1}`,
    confidence: Number(box?.confidence || 0),
    id: box?.id || `import_${index + 1}`,
    locked: !!box?.locked,
    pinned: !!box?.pinned,
    ignored: !!box?.ignored,
    suppressed: !!box?.suppressed,
    suppressed_reason: box?.suppressed_reason || '',
    group_key: box?.group_key || '',
    group_label: box?.group_label || '',
    priority_rank: Number(box?.priority_rank || 0),
    cluster_size: Number(box?.cluster_size || 1),
    track_id: box?.track_id || '',
    reacquired: !!box?.reacquired,
    ordered_index: Number(box?.ordered_index || 0),
    target_index: Number(box?.target_index || 0),
    prompt_index: Number(box?.prompt_index || 0),
    number_label: box?.number_label || '',
  })).filter(box => Number.isFinite(box.x) && Number.isFinite(box.y) && Number.isFinite(box.w) && Number.isFinite(box.h) && box.w > 0 && box.h > 0);
}

async function importGenerationDetailerSnapshot(file) {
  if (!(file instanceof File)) throw new Error('Pick a snapshot JSON file first.');
  const raw = await file.text();
  let payload = {};
  try {
    payload = JSON.parse(raw);
  } catch (_) {
    throw new Error('Neo could not parse the detection snapshot JSON.');
  }
  if (String(payload?.kind || '') !== 'neo_studio_detailer_detection_snapshot_v1') throw new Error('This file is not a Neo detailer detection snapshot.');
  generationDetailerBoxEditorState.boxes = normalizeImportedGenerationDetailerBoxes(payload?.boxes || []);
  generationDetailerBoxEditorState.previewSource = payload?.preview_source || 'manual';
  generationDetailerBoxEditorState.previewMeta = payload?.preview_meta || null;
  if (payload?.editor_controls) applyGenerationDetailerEditorControlState(payload.editor_controls);
  generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length ? 0 : -1;
  const textarea = getGenerationDetailerEditorTargetTextarea();
  if (textarea) {
    textarea.value = String(payload?.manual_boxes || '');
    if (!textarea.value.trim()) {
      syncGenerationDetailerBoxesToTextarea();
    }
  }
  saveGenerationDetailerEditorScopeSnapshot();
  saveGenerationDetailerHistoryEntry('import');
  renderGenerationDetailerBoxList();
  renderGenerationDetailerEditorCanvas();
  setGenerationDetailerEditorNote(`Imported detection snapshot into ${describeGenerationDetailerEditorScope()}. Lock/ignore tags, preview metadata, and pass-local preview controls were restored.`);
  setStatus('generation-detailer-status', 'Detection snapshot imported.', 'success');
}

function normalizeGenerationDetailerPreviewBoxes(detections=[]) {
  return (Array.isArray(detections) ? detections : []).map((item, index) => ({
    x: Number(item?.x || 0),
    y: Number(item?.y || 0),
    w: Number(item?.w || 0),
    h: Number(item?.h || 0),
    keep: item?.selected !== false && item?.ignored !== true,
    selected: item?.selected !== false,
    source: 'auto',
    label: item?.label || `Detection ${index + 1}`,
    confidence: Number(item?.confidence || 0),
    id: item?.id || `auto_${index + 1}` ,
    locked: !!item?.locked,
    pinned: !!item?.pinned,
    ignored: !!item?.ignored,
    suppressed: !!item?.suppressed,
    suppressed_reason: item?.suppressed_reason || '',
    group_key: item?.group_key || '',
    group_label: item?.group_label || '',
    priority_rank: Number(item?.priority_rank || 0),
    cluster_size: Number(item?.cluster_size || 1),
    track_id: item?.track_id || '',
    reacquired: !!item?.reacquired,
    ordered_index: Number(item?.ordered_index || 0),
    target_index: Number(item?.target_index || 0),
    prompt_index: Number(item?.prompt_index || 0),
    number_label: item?.number_label || '',
  })).filter(box => Number.isFinite(box.x) && Number.isFinite(box.y) && Number.isFinite(box.w) && Number.isFinite(box.h) && box.w > 0 && box.h > 0);
}

function renderGenerationDetailerPreviewSummary(data, incoming=[]) {
  const list = $('generation-detailer-editor-box-list');
  if (!list || !data) return;
  const selected = incoming.filter(box => box.target_index > 0 && box.ignored !== true && box.suppressed !== true);
  const order = data?.target_order || data?.effective_filters?.order_mode || $('generation-detailer-order')?.value || 'auto';
  const summary = document.createElement('div');
  summary.className = 'card-lite';
  summary.style.padding = '10px';
  summary.style.border = '1px solid rgba(99,179,237,.35)';
  summary.style.background = 'rgba(99,179,237,.08)';
  const selectedLine = selected.length
    ? selected.map(box => `#${box.target_index}: ${escapeHtml(box.label || 'target')} · ${Math.round(box.x)},${Math.round(box.y)} · ${Math.round(box.w)}×${Math.round(box.h)}`).join('<br>')
    : 'No selected targets with current filters.';
  summary.innerHTML = `
    <div style="font-weight:700;">🎯 Numbered Detection Preview</div>
    <div class="mini-note" style="margin-top:4px;">Order: <strong>${escapeHtml(order)}</strong> · Detected: ${Number(data?.detections?.length || incoming.length || 0)} · Selected: ${Number(data?.selected_count || selected.length || 0)} · Suppressed: ${Number(data?.suppressed_count || 0)}</div>
    <div class="mini-note" style="margin-top:6px; line-height:1.5;">${selectedLine}</div>
    <div class="mini-note" style="margin-top:6px;">Use these # numbers for [SEP] prompt order. Example: prompt for #1 [SEP] prompt for #2.</div>`;
  list.prepend(summary);
}

async function runGenerationDetailerDetectionPreview(file, label='image') {
  if (!file) throw new Error('Load an image first.');
  await loadGenerationDetailerEditorFromFile(file, label);
  const response = await fetch('/api/generation/detailer-preview-detections', {
    method:'POST',
    body: buildGenerationDetailerPreviewFormData(file),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
  const incoming = normalizeGenerationDetailerPreviewBoxes(data?.detections || []);
  const mergeMode = getGenerationDetailerPreviewMergeMode();
  const merge = mergeGenerationDetailerPreviewBoxes(generationDetailerBoxEditorState.boxes || [], incoming, mergeMode);
  generationDetailerBoxEditorState.previewSource = 'auto';
  generationDetailerBoxEditorState.previewMeta = data || null;
  generationDetailerBoxEditorState.boxes = merge.boxes;
  generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.findIndex(box => box.pinned === true && box.ignored !== true);
  if (generationDetailerBoxEditorState.activeIndex < 0) generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.findIndex(box => box.keep !== false && box.ignored !== true);
  if (generationDetailerBoxEditorState.activeIndex < 0) generationDetailerBoxEditorState.activeIndex = generationDetailerBoxEditorState.boxes.length ? 0 : -1;
  syncGenerationDetailerBoxesToTextarea();
  renderGenerationDetailerBoxList();
  renderGenerationDetailerPreviewSummary(data, incoming);
  renderGenerationDetailerEditorCanvas();
  if (typeof renderGenerationDetailerPromptMap === 'function') renderGenerationDetailerPromptMap();
  saveGenerationDetailerEditorScopeSnapshot();
  saveGenerationDetailerHistoryEntry('preview');
  const warnings = Array.isArray(data?.warnings) ? data.warnings.filter(Boolean) : [];
  const strategy = data?.preview_mode ? ` (${data.preview_mode})` : '';
  const refreshNote = Number(merge.refreshed || 0) > 0 ? ` Refreshed ${Number(merge.refreshed)} pinned/locked duplicate target${Number(merge.refreshed) === 1 ? '' : 's'} with current ordering.` : '';
  const mergeNote = mergeMode === 'append'
    ? ` Appended ${merge.added} target(s)${merge.skipped ? ` and skipped/refreshed ${merge.skipped} near-duplicate box(es)` : ''}.${refreshNote}`
    : ` Replaced the current target list with ${incoming.length} detection(s).${refreshNote}`;
  const presetLabel = data?.priority_preset_label ? ` Preset: ${data.priority_preset_label}.` : '';
  const biasLabel = data?.foreground_bias_label ? ` Foreground bias: ${data.foreground_bias_label}.` : '';
  const suppressedNote = Number(data?.suppressed_count || 0) > 0 ? ` Auto-suppressed ${Number(data.suppressed_count)} tiny background face${Number(data.suppressed_count) === 1 ? '' : 's'}.` : '';
  const clusterNote = Number(data?.merged_cluster_count || 0) > 0 ? ` Cluster-merged ${Number(data.merged_cluster_count)} extra detection${Number(data.merged_cluster_count) === 1 ? '' : 's'}.` : '';
  const reacquireNote = Number(data?.reacquired_pinned_count || 0) > 0 ? ` Reacquired ${Number(data.reacquired_pinned_count)} pinned subject track${Number(data.reacquired_pinned_count) === 1 ? '' : 's'}.` : '';
  const tuningHint = Array.isArray(data?.tuning_hints) && data.tuning_hints.length ? ` ${data.tuning_hints[0]}` : '';
  setGenerationDetailerEditorNote(`${data?.message || 'Detector preview updated.'}${strategy}${mergeNote}${presetLabel}${biasLabel}${suppressedNote}${clusterNote}${reacquireNote}${tuningHint}${warnings.length ? ` ${warnings.join(' ')}` : ''}`);
  setStatus('generation-detailer-status', data?.message || 'Detector preview updated.', generationDetailerBoxEditorState.boxes.length ? 'success' : 'warn');
}

async function runGenerationDetailerDetectionPreviewFromSource() {
  const file = $('generation-source-image')?.files?.[0] || null;
  if (!file) throw new Error('Load a source image first.');
  await runGenerationDetailerDetectionPreview(file, 'source image');
}

async function runGenerationDetailerDetectionPreviewFromPreview() {
  const file = await fetchGenerationPreviewFile();
  await runGenerationDetailerDetectionPreview(file, 'current output preview');
}

function getGenerationActivePreviewOutput() {
  const cloneOut = (item) => (cloneGenerationOutputSnapshot?.(item) || (item ? { ...item } : null));
  const active = typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : null;
  if (active?.view_url) return cloneOut(active);
  if (generationSelectedOutputSnapshot?.view_url) return cloneOut(generationSelectedOutputSnapshot);
  if (generationPreviewActionTarget?.view_url) return cloneOut(generationPreviewActionTarget);

  // Phase 10.3 preview-action hotfix: recover from the latest job output or the
  // visible preview image when previous UI patches cleared the locked target.
  const latestOutputs = Array.isArray(generationLatestJobSnapshot?.outputs) ? generationLatestJobSnapshot.outputs : [];
  const latest = latestOutputs.find(item => item && item.view_url) || null;
  if (latest?.view_url) {
    const recovered = cloneOut({ ...latest, job_id: generationLatestJobSnapshot?.id || latest.job_id || '' });
    if (recovered?.view_url) {
      generationPreviewActionTarget = { ...recovered };
      generationSelectedOutputSnapshot = { ...recovered };
      if (typeof updateGenerationPreviewActionState === 'function') updateGenerationPreviewActionState();
      return recovered;
    }
  }

  const liveSrc = String(document.getElementById('generation-live-preview')?.getAttribute('src') || '').trim();
  if (liveSrc) {
    const recovered = cloneOut({
      view_url: liveSrc,
      filename: 'generated_image.png',
      saved_filename: 'generated_image.png',
      source_kind: 'visible_preview',
      source: 'visible_preview',
    });
    if (recovered?.view_url) {
      generationPreviewActionTarget = { ...recovered };
      generationSelectedOutputSnapshot = { ...recovered };
      if (typeof updateGenerationPreviewActionState === 'function') updateGenerationPreviewActionState();
      return recovered;
    }
  }
  return null;
}

async function fetchGenerationPreviewFile() {
  const activePreview = getGenerationActivePreviewOutput();
  const livePreviewUrl = String(document.getElementById('generation-live-preview')?.getAttribute('src') || '').trim();
  if (!activePreview?.view_url) throw new Error('Pick an active output first. Neo now locks preview actions to the selected result instead of guessing from stale previews.');

  const filename = activePreview?.filename || activePreview?.saved_filename || '';
  const subfolder = activePreview?.subfolder || '';
  const fileType = activePreview?.type || 'output';

  let targetUrl = '';
  const isImported = !!activePreview?.imported;
  const isLibrary = String(activePreview?.source || '').toLowerCase() === 'library';
  const rawViewUrl = String(activePreview?.view_url || '').trim();

  const buildProxyUrl = (name='', folder='', type='output') => {
    if (!String(name || '').trim()) return '';
    return `/api/generation/output-download?filename=${encodeURIComponent(String(name || '').trim())}&subfolder=${encodeURIComponent(String(folder || '').trim())}&file_type=${encodeURIComponent(String(type || 'output').trim() || 'output')}`;
  };

  const extractProxyUrl = (candidate='') => {
    if (!candidate) return '';
    try {
      const parsed = new URL(candidate, window.location.origin);
      const rawFilename = parsed.searchParams.get('filename') || '';
      const rawSubfolder = parsed.searchParams.get('subfolder') || '';
      const rawType = parsed.searchParams.get('type') || parsed.searchParams.get('file_type') || fileType || 'output';
      if (rawFilename) return buildProxyUrl(rawFilename, rawSubfolder, rawType);
    } catch (_) {}
    const match = String(candidate).match(/[?&]filename=([^&]+)/i);
    if (match && match[1]) {
      const folderMatch = String(candidate).match(/[?&]subfolder=([^&]*)/i);
      const typeMatch = String(candidate).match(/[?&](?:type|file_type)=([^&]*)/i);
      try {
        return buildProxyUrl(decodeURIComponent(match[1]), decodeURIComponent(folderMatch?.[1] || ''), decodeURIComponent(typeMatch?.[1] || fileType || 'output'));
      } catch (_) {
        return buildProxyUrl(match[1], folderMatch?.[1] || '', typeMatch?.[1] || fileType || 'output');
      }
    }
    return '';
  };

  const resolveSameOriginUrl = (candidate='') => {
    if (!candidate) return '';
    if (candidate.startsWith('blob:')) return candidate;
    try {
      const parsed = new URL(candidate, window.location.origin);
      if (parsed.origin === window.location.origin) return parsed.toString();
      throw new Error('Neo could not proxy this preview image yet. Re-open the latest output so Neo refreshes it through the local output route.');
    } catch (error) {
      if (error instanceof Error) throw error;
      return '';
    }
  };

  if (rawViewUrl) {
    targetUrl = extractProxyUrl(rawViewUrl) || resolveSameOriginUrl(rawViewUrl);
  }
  if (!targetUrl && !isImported && !isLibrary && filename) {
    targetUrl = buildProxyUrl(filename, subfolder, fileType);
  }
  if (!targetUrl && !isImported && !isLibrary) {
    targetUrl = extractProxyUrl(rawViewUrl);
  }
  if (!targetUrl && livePreviewUrl && livePreviewUrl === rawViewUrl) {
    targetUrl = resolveSameOriginUrl(livePreviewUrl);
  }

  if (!targetUrl) throw new Error('Neo could not resolve a safe local download route for this preview image.');

  const response = await fetch(targetUrl, { cache:'no-store' });
  if (!response.ok) throw new Error(`Could not load the generated image (${response.status}).`);
  const blob = await response.blob();
  const fileName = activePreview?.saved_filename || activePreview?.filename || 'generated_image.png';
  return new File([blob], fileName, { type: blob.type || 'image/png' });
}

function assignFileToInput(inputId, file) {
  const input = $(inputId);
  if (!input || !file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles:true }));
}

function focusGenerationSetupTab(tab='core', accordionId='') {
  const next = ['core','assets','guide','enhance','helper','output'].includes(String(tab || '').trim()) ? String(tab || '').trim() : 'core';
  try {
    if (typeof window.neoGenerationSetSetupTab === 'function') window.neoGenerationSetSetupTab(next);
    else document.querySelector(`[data-generation-setup-tab="${next}"]`)?.click();
  } catch (_) {}
  if (!accordionId) return;
  window.setTimeout(() => {
    const target = document.querySelector(`[data-accordion-id="${accordionId}"]`);
    if (!target) return;
    const host = target.parentElement;
    if (host) {
      host.querySelectorAll(':scope > details.accordion-block').forEach(detail => {
        if (detail !== target) detail.open = false;
      });
    }
    target.open = true;
    try {
      target.scrollIntoView({ block:'start', behavior:'smooth' });
    } catch (_) {
      try { target.scrollIntoView(); } catch (_) {}
    }
  }, 90);
}

function getGenerationPreviewFamilyBlocker(kind='') {
  const family = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || '').trim();
  const lane = String(kind || '').trim().toLowerCase();
  if (lane === 'ipadapter' && family === 'qwen_image_edit') return 'IP-Adapter reference is disabled for Qwen Image because this family uses Qwen multi-source references instead.';
  if (lane === 'ipadapter' && family === 'flux') return 'IP-Adapter reference is disabled for Flux GGUF until a compatible Flux IP-Adapter graph is registered.';
  return '';
}

async function sendGenerationPreviewToReferenceLane(kind='controlnet') {
  try {
    const blockedReason = getGenerationPreviewFamilyBlocker(kind);
    if (blockedReason) {
      setStatus('generation-status', blockedReason, 'warn');
      return;
    }
    const file = await fetchGenerationPreviewFile();
    if (kind === 'ipadapter') {
      assignFileToInput('generation-ipadapter-image', file);
      if ($('generation-ipadapter-enabled')) $('generation-ipadapter-enabled').checked = true;
      try { updatePrimaryGenerationIpAdapterSummary(); } catch (_) {}
      focusGenerationSetupTab('guide', 'generation-ipadapter-settings');
      scheduleGenerationDraftSave();
      setStatus('generation-status', 'Image sent to IP-Adapter reference. Confirm the mode, model, and CLIP Vision settings next.', 'success');
      return;
    }
    assignFileToInput('generation-control-image', file);
    if ($('generation-controlnet-enabled')) $('generation-controlnet-enabled').checked = true;
    try { updatePrimaryGenerationControlnetSummary(); } catch (_) {}
    focusGenerationSetupTab('guide', 'generation-controlnet-settings');
    scheduleGenerationDraftSave();
    setStatus('generation-status', 'Image sent to ControlNet reference. Confirm the model, preprocessor, and strength next.', 'success');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not move the generated image into that reference lane.', 'error');
  }
}

async function sendGenerationPreviewToMode(mode='img2img') {
  try {
    const file = await fetchGenerationPreviewFile();
    assignFileToInput('generation-source-image', file);
    if ($('generation-workflow-type')) $('generation-workflow-type').value = mode;
    if ((mode === 'inpaint' || mode === 'outpaint') && $('generation-mask-image')) {
      clearGenerationImageInput('generation-mask-image');
    }
    if (mode === 'inpaint') {
      setStatus('generation-status', 'Image sent to Inpaint. Add or draw a mask next.', 'success');
    } else if (mode === 'outpaint') {
      setStatus('generation-status', 'Image sent to Outpaint. Set the padding directions and queue it.', 'success');
    } else {
      setStatus('generation-status', `Image sent to ${mode}.`, 'success');
    }
    syncGenerationModeUI();
    focusGenerationSetupTab('core');
    updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]');
    scheduleGenerationDraftSave();
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not move the generated image into that mode.', 'error');
  }
}

function buildGenerationPreviewActionContract(actionType, options={}) {
  const activeOutput = getGenerationActivePreviewOutput() || generationSelectedOutputSnapshot || null;
  const action = String(actionType || 'derived').trim().toLowerCase() || 'derived';
  const sourceKind = activeOutput?.source_kind || activeOutput?.source || (activeOutput?.imported ? 'imported' : 'generated');
  const saveLane = options.saveLane || inferGenerationPreviewSaveMode(activeOutput);
  const family = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || '').trim();
  const modelSource = String($('generation-model-source')?.value || '').trim();
  return {
    schema_version: 1,
    action_type: action,
    source_output_id: activeOutput?.output_id || activeOutput?.id || '',
    source_output_key: generationOutputKey?.(activeOutput) || activeOutput?.output_key || '',
    source_job_id: activeOutput?.job_id || activeOutput?.jobId || '',
    source_kind: String(sourceKind || 'generated').toLowerCase(),
    source_filename: activeOutput?.filename || '',
    source_saved_filename: activeOutput?.saved_filename || '',
    source_saved_path: activeOutput?.saved_path || '',
    source_view_url: activeOutput?.view_url || '',
    execution_mode: options.executionMode || 'img2img',
    workflow_variant: options.workflowVariant || 'preview_action',
    source_family: family,
    source_model_source: family === 'flux' || family === 'qwen_image_edit' ? 'gguf' : (modelSource || 'checkpoint'),
    save_lane: saveLane,
    derived_stage: options.stage || options.derivedStage || action,
    parent_output_id: activeOutput?.output_id || activeOutput?.id || '',
    parent_output_key: generationOutputKey?.(activeOutput) || activeOutput?.output_key || '',
    parent_job_id: activeOutput?.job_id || activeOutput?.jobId || '',
    preserve_prompt_context: options.preservePromptContext !== false,
    preserve_reference_context: options.preserveReferenceContext !== false,
    requires_active_output: true,
    created_at: new Date().toISOString(),
  };
}

function applyGenerationPreviewActionContractToPayload(payload, contract, options={}) {
  const next = payload && typeof payload === 'object' ? payload : {};
  const executionMode = String(contract?.execution_mode || options.executionMode || 'img2img').toLowerCase();
  next.workflow_type = executionMode;
  next.mode = executionMode;
  next.batch_size = 1;
  next.save_mode_override = contract?.save_lane || inferGenerationPreviewSaveMode(getGenerationActivePreviewOutput());
  next._neo_preview_action = JSON.parse(JSON.stringify(contract || {}));
  next._neo_derived_action_type = contract?.action_type || options.actionType || 'derived';
  next._neo_source_output_id = contract?.source_output_id || '';
  next._neo_source_output_key = contract?.source_output_key || '';
  next._neo_source_job_id = contract?.source_job_id || '';
  next._neo_parent_output_id = contract?.parent_output_id || '';
  next._neo_parent_output_key = contract?.parent_output_key || '';
  next._neo_save_lane = contract?.save_lane || next.save_mode_override || '';
  next._neo_preview_action_family = next.family || contract?.source_family || '';
  next._neo_preview_action_model_source = next.model_source || contract?.source_model_source || '';
  next._neo_preview_action_preserved_context = {
    family: next.family || '',
    model_source: next.model_source || '',
    gguf_unet: next.gguf_unet || '',
    gguf_clip_primary: next.gguf_clip_primary || '',
    gguf_clip_secondary: next.gguf_clip_secondary || '',
    gguf_clip_mode: next.gguf_clip_mode || '',
    gguf_clip_type: next.gguf_clip_type || '',
    gguf_mmproj: next.gguf_mmproj || next._neo_effective_gguf_mmproj || '',
    effective_gguf_unet_loader: next._neo_effective_gguf_unet_loader || '',
    effective_gguf_clip_loader: next._neo_effective_gguf_clip_loader || '',
    effective_mmproj_source: next._neo_effective_mmproj_source || '',
  };
  if (options.patch && typeof options.patch === 'object') {
    Object.entries(options.patch).forEach(([key, value]) => { next[key] = value; });
  }
  return next;
}

async function queueGenerationPreviewAction(actionType, options={}) {
  const contract = buildGenerationPreviewActionContract(actionType, options);
  const file = await fetchGenerationPreviewFile();
  const payload = applyGenerationPreviewActionContractToPayload(buildGenerationPayload(), contract, options);
  const stage = options.stage || contract.derived_stage || actionType || 'Derived pass';
  if (typeof options.beforeQueue === 'function') {
    const result = await options.beforeQueue({ payload, contract, file });
    if (result === false) return null;
  }
  if (options.focusTab || options.focusAccordion) {
    focusGenerationSetupTab(options.focusTab || 'enhance', options.focusAccordion || '');
  }
  if (options.statusMessage) setStatus('generation-status', options.statusMessage, options.statusTone || undefined);
  const job = await queueGenerationShell({
    watch: options.watch !== false,
    suppressSuccessStatus: !!options.suppressSuccessStatus,
    fallbackPrompt: options.fallbackPrompt || 'masterpiece, best quality, cinematic portrait, dramatic lighting, highly detailed',
    overridePayload: payload,
    overrideSourceFile: file,
    lineageHint: { parentOutput: getGenerationActivePreviewOutput() || generationSelectedOutputSnapshot || null, stage },
    previewActionContract: contract,
  });
  if (job?.id && options.successMessage) announceGenerationStatus(options.successMessage);
  return job;
}

async function runGenerationPreviewHiresFix() {
  try {
    const refineSteps = Number($('generation-refine-steps')?.value || 12);
    const refineDenoise = Number($('generation-refine-denoise')?.value || 0.12);
    let refineScale = Number($('generation-refine-scale')?.value || 1.5);
    let refineMode = $('generation-refine-mode')?.value || 'latent';
    const selectedUpscaler = trim($('generation-refine-upscaler')?.value || '');
    if (!(refineScale > 1)) refineScale = 1.5;
    if (refineMode === 'image_upscale' && !selectedUpscaler) refineMode = 'latent';

    await queueGenerationPreviewAction('hires_fix', {
      stage: 'Upscale Lab',
      focusTab: 'enhance',
      focusAccordion: 'generation-hires-settings',
      statusMessage: `Running Upscale Lab on the active output without switching your visible workspace mode… ${refineMode === 'image_upscale' ? 'Image upscaler + preserve' : 'Latent upscale + refine'}`,
      successMessage: 'Upscale Lab queued from the active output. The visible workspace mode was left untouched.',
      patch: {
        refine_enabled: true,
        refine_scale: refineScale,
        refine_mode: refineMode,
        refine_steps: refineSteps,
        refine_denoise: refineDenoise,
        upscale_lab_source_only: true,
      },
    });
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not start Upscale Lab from the generated image.', 'error');
  }
}

async function runGenerationPreviewDetailerPass() {
  try {
    await queueGenerationPreviewAction('selective_repair', {
      stage: 'Selective Repair',
      focusTab: 'enhance',
      focusAccordion: 'generation-detailer-settings',
      statusMessage: 'Running Selective Repair on the active output without switching your visible workspace mode…',
      successMessage: 'Selective Repair queued from the active output. The visible workspace mode was left untouched.',
      beforeQueue: ({ payload }) => {
        const detailerConfigured = !!payload.detailer?.enabled || (Array.isArray(payload.detailer_passes) && payload.detailer_passes.some(pass => pass?.enabled !== false));
        if (!detailerConfigured) {
          focusGenerationSetupTab('enhance', 'generation-detailer-settings');
          setStatus('generation-status', 'Enable and configure Selective Repair first so Neo knows what to run.', 'warn');
          return false;
        }
        renderGenerationDetailerReport('selective-repair-queued');
        return true;
      },
      patch: {
        refine_enabled: false,
        supir_enabled: false,
        detailer_output_pass: true,
      },
    });
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not start Selective Repair from the generated image.', 'error');
  }
}

async function runGenerationPreviewIdentityRescuePass() {
  try {
    await queueGenerationPreviewAction('identity_rescue', {
      stage: 'Identity Rescue',
      statusMessage: 'Running Identity Rescue on the active output without switching your visible workspace mode…',
      successMessage: 'Identity Rescue queued from the active output. The visible workspace mode was left untouched.',
      beforeQueue: ({ payload }) => {
        const faceIdUnits = (Array.isArray(payload.ipadapter_units) ? payload.ipadapter_units : []).filter(unit => String(unit?.mode || 'standard').toLowerCase() === 'faceid');
        if (!faceIdUnits.length) {
          focusGenerationSetupTab('reference', 'generation-ipadapter-settings');
          setStatus('generation-status', 'Enable at least one FaceID IP-Adapter setup first so Neo knows which identity to rescue.', 'warn');
          return false;
        }
        payload.denoise = Math.max(0.12, Math.min(Number(payload.denoise || 0.28) || 0.28, 0.35));
        return true;
      },
      patch: {
        refine_enabled: false,
        supir_enabled: false,
      },
    });
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not start Identity Rescue from the generated image.', 'error');
  }
}


// Phase 4: ADetailer per-target prompt mapper. This is deliberately UI-only:
// it compiles mapped prompt rows back into the existing Forge-style [SEP]
// prompt fields, so the already-tested backend path remains unchanged.
function splitGenerationDetailerSepText(value='') {
  return String(value || '').split(/\s*\[SEP\]\s*/i).map(part => part.trim());
}

function joinGenerationDetailerSepText(parts=[]) {
  return (Array.isArray(parts) ? parts : []).map(part => String(part || '').trim()).join(' [SEP] ');
}

function getGenerationDetailerOrderedPromptTargets() {
  const boxes = Array.isArray(generationDetailerBoxEditorState?.boxes) ? generationDetailerBoxEditorState.boxes : [];
  const selected = boxes
    .filter(box => box && box.keep !== false && box.ignored !== true && box.suppressed !== true && (box.selected !== false || box.pinned === true || Number(box.target_index || 0) > 0))
    .map((box, index) => ({ ...box, __fallbackIndex: index + 1 }))
    .sort((a, b) => {
      const ai = Number(a.target_index || 0);
      const bi = Number(b.target_index || 0);
      if (ai && bi) return ai - bi;
      if (ai) return -1;
      if (bi) return 1;
      const ao = Number(a.ordered_index || a.priority_rank || a.__fallbackIndex || 0);
      const bo = Number(b.ordered_index || b.priority_rank || b.__fallbackIndex || 0);
      return ao - bo;
    });
  const candidates = selected.length ? selected : boxes
    .filter(box => box && box.ignored !== true && box.suppressed !== true && Number(box.w || 0) > 0 && Number(box.h || 0) > 0)
    .map((box, index) => ({ ...box, __fallbackIndex: index + 1 }))
    .sort((a, b) => {
      const ao = Number(a.ordered_index || a.priority_rank || a.__fallbackIndex || 0);
      const bo = Number(b.ordered_index || b.priority_rank || b.__fallbackIndex || 0);
      return ao - bo;
    });
  return candidates.map((box, index) => ({
    index: Number(box.target_index || 0) || index + 1,
    label: box.label || (box.source === 'manual' ? 'Manual target' : 'Target'),
    confidence: Number(box.confidence || 0),
    x: Number(box.x || 0),
    y: Number(box.y || 0),
    w: Number(box.w || 0),
    h: Number(box.h || 0),
  }));
}

function getGenerationDetailerPromptMapRows() {
  const list = $('generation-detailer-prompt-map-list');
  if (!list) return [];
  return Array.from(list.querySelectorAll('[data-detailer-prompt-target]')).map(row => ({
    index: Number(row.getAttribute('data-detailer-prompt-target') || 0),
    positive: row.querySelector('.generation-detailer-map-positive')?.value || '',
    negative: row.querySelector('.generation-detailer-map-negative')?.value || '',
  }));
}

function setGenerationDetailerPromptMapStatus(message='', tone='') {
  const el = $('generation-detailer-prompt-map-status');
  if (!el) return;
  el.textContent = message || 'Run Detect targets to create #1/#2/#3 prompt rows.';
  el.style.color = tone === 'warn' ? '#ffd166' : tone === 'error' ? '#ff8c8c' : '';
}

function renderGenerationDetailerPromptMap(targets=null, positiveParts=null, negativeParts=null) {
  const list = $('generation-detailer-prompt-map-list');
  if (!list) return;
  const detected = Array.isArray(targets) ? targets : getGenerationDetailerOrderedPromptTargets();
  const posParts = Array.isArray(positiveParts) ? positiveParts : splitGenerationDetailerSepText($('generation-detailer-positive')?.value || '');
  const negParts = Array.isArray(negativeParts) ? negativeParts : splitGenerationDetailerSepText($('generation-detailer-negative')?.value || '');
  list.innerHTML = '';
  if (!detected.length) {
    const meta = generationDetailerBoxEditorState?.previewMeta || {};
    const detCount = Array.isArray(meta.detections) ? meta.detections.length : 0;
    const extra = detCount
      ? ` Detected ${detCount} candidate(s), but none are selected by the current Start/Count/area filters.`
      : ' No usable detections came back from the detector.';
    setGenerationDetailerPromptMapStatus(`No selected targets found.${extra} Try lowering confidence, set Count to 0/all, switch Target order, or add manual boxes in the picker.`, 'warn');
    return;
  }
  detected.forEach((target, i) => {
    const card = document.createElement('div');
    card.className = 'card-lite';
    card.setAttribute('data-detailer-prompt-target', String(target.index || i + 1));
    card.style.padding = '10px';
    card.style.border = '1px solid rgba(255,255,255,.12)';
    const conf = Number(target.confidence || 0) > 0 ? ` · conf ${Number(target.confidence).toFixed(2)}` : '';
    card.innerHTML = `
      <div class="row-between" style="gap:10px; align-items:center; flex-wrap:wrap;">
        <div style="font-weight:700; min-width:120px;">#${target.index || i + 1} ${escapeHtml(target.label || 'Target')}${conf}</div>
        <div class="mini-note">${Math.round(target.x || 0)},${Math.round(target.y || 0)} · ${Math.round(target.w || 0)}×${Math.round(target.h || 0)}</div>
      </div>
      <div style="display:grid; grid-template-columns:minmax(110px,140px) 1fr; gap:8px 10px; align-items:start; margin-top:8px; width:100%;">
        <label style="padding-top:8px;">Positive #${target.index || i + 1}</label>
        <textarea class="generation-detailer-map-positive" rows="2" style="width:100%;" placeholder="Prompt chunk for this target">${escapeHtml(posParts[i] || posParts[posParts.length - 1] || '')}</textarea>
        <label style="padding-top:8px;">Negative #${target.index || i + 1}</label>
        <textarea class="generation-detailer-map-negative" rows="2" style="width:100%;" placeholder="Negative chunk for this target">${escapeHtml(negParts[i] || negParts[negParts.length - 1] || '')}</textarea>
      </div>`;
    list.appendChild(card);
  });
  setGenerationDetailerPromptMapStatus(`Detected ${detected.length} target${detected.length === 1 ? '' : 's'}. Edit rows, then click Apply → Main Prompt.`, '');
  renderGenerationDetailerReport('prompt-map');
}

function exportGenerationDetailerPromptMapToSep() {
  const rows = getGenerationDetailerPromptMapRows();
  if (!rows.length) {
    renderGenerationDetailerPromptMap();
    if (!getGenerationDetailerPromptMapRows().length) return;
  }
  const nextRows = getGenerationDetailerPromptMapRows();
  const pos = nextRows.map(row => row.positive || '').filter((_, i, arr) => arr.length > 1 || String(arr[0] || '').trim());
  const neg = nextRows.map(row => row.negative || '').filter((_, i, arr) => arr.length > 1 || String(arr[0] || '').trim());
  if ($('generation-detailer-positive')) $('generation-detailer-positive').value = joinGenerationDetailerSepText(pos);
  if ($('generation-detailer-negative')) $('generation-detailer-negative').value = joinGenerationDetailerSepText(neg);
  if (typeof renderGenerationFinishFoundation === 'function') renderGenerationFinishFoundation();
  if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
  setGenerationDetailerPromptMapStatus(`Applied ${nextRows.length} mapped row${nextRows.length === 1 ? '' : 's'} into the main [SEP] prompt fields.`, '');
  renderGenerationDetailerReport('prompt-map-applied');
  setStatus('generation-detailer-status', 'Per-target prompts applied to the main [SEP] fields.', 'success');
}

function importGenerationDetailerPromptMapFromSep() {
  renderGenerationDetailerPromptMap(
    getGenerationDetailerOrderedPromptTargets(),
    splitGenerationDetailerSepText($('generation-detailer-positive')?.value || ''),
    splitGenerationDetailerSepText($('generation-detailer-negative')?.value || '')
  );
}

function copyFirstGenerationDetailerPromptToAll() {
  const rows = getGenerationDetailerPromptMapRows();
  if (!rows.length) return;
  const list = $('generation-detailer-prompt-map-list');
  const firstPos = list.querySelector('.generation-detailer-map-positive')?.value || '';
  const firstNeg = list.querySelector('.generation-detailer-map-negative')?.value || '';
  list.querySelectorAll('.generation-detailer-map-positive').forEach(el => { el.value = firstPos; });
  list.querySelectorAll('.generation-detailer-map-negative').forEach(el => { el.value = firstNeg; });
  setGenerationDetailerPromptMapStatus('Copied target #1 prompts to all mapped targets.', '');
}

function clearGenerationDetailerPromptMap() {
  const list = $('generation-detailer-prompt-map-list');
  if (list) list.innerHTML = '';
  setGenerationDetailerPromptMapStatus('Prompt rows cleared. Existing main [SEP] fields were left unchanged.', '');
  renderGenerationDetailerReport('prompt-map-cleared');
}

async function detectGenerationDetailerPromptMapTargets() {
  const btn = $('btn-generation-detailer-prompt-map-detect');
  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Detecting...';
    }
    setGenerationDetailerPromptMapStatus('Detecting targets from the current preview/source image...', '');
    const hasPreview = !!String(document.getElementById('generation-live-preview')?.getAttribute('src') || '').trim();
    const runner = hasPreview ? runGenerationDetailerDetectionPreviewFromPreview : runGenerationDetailerDetectionPreviewFromSource;
    await runner();
    renderGenerationDetailerPromptMap(
      getGenerationDetailerOrderedPromptTargets(),
      splitGenerationDetailerSepText($('generation-detailer-positive')?.value || ''),
      splitGenerationDetailerSepText($('generation-detailer-negative')?.value || '')
    );
  } catch (err) {
    const msg = err?.message || 'Could not detect ADetailer targets.';
    setGenerationDetailerPromptMapStatus(msg, 'error');
    setStatus('generation-detailer-status', msg, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🎯 Detect targets';
    }
  }
}


function getGenerationDetailerReferenceLockLabel(value) {
  const map = {
    none: 'Off',
    soft_identity: 'Soft identity',
    strong_identity: 'Strong identity',
    face_only: 'Face only',
    style_only: 'Style only',
    controlnet: 'Follow ControlNet',
    ipadapter: 'Legacy IP-Adapter / FaceID',
    both: 'Legacy both'
  };
  return map[String(value || 'none')] || String(value || 'none').replace(/_/g, ' ');
}

function getGenerationDetailerReferenceReadiness(lockValue) {
  const mode = String(lockValue || 'none');
  const ipUnits = Array.from(document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row'));
  const hasPrimaryIp = !!(($('generation-ipadapter-name')?.value || '').trim() || ($('generation-ipadapter-clip-vision')?.value || '').trim() || ($('generation-ipadapter-image-name')?.value || '').trim());
  const hasFaceId = (($('generation-ipadapter-mode')?.value || '').toLowerCase() === 'faceid') || ipUnits.some(row => (row.querySelector('.generation-ipadapter-mode')?.value || '').toLowerCase() === 'faceid');
  const hasIp = hasPrimaryIp || ipUnits.some(row => (row.querySelector('.generation-ipadapter-name')?.value || '').trim() || (row.querySelector('.generation-ipadapter-clip-vision')?.value || '').trim());
  const cnUnits = Array.from(document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row'));
  const hasCn = !!(($('generation-controlnet-name')?.value || '').trim()) || cnUnits.some(row => (row.querySelector('.generation-controlnet-name')?.value || row.querySelector('.generation-controlnet-model')?.value || '').trim());
  if (mode === 'none') return { ok: true, message: 'Reference lock is off.' };
  if (mode === 'controlnet') return hasCn ? { ok: true, message: 'ControlNet guidance found.' } : { ok: false, message: 'Needs a configured ControlNet unit.' };
  if (mode === 'both') return (hasCn && hasIp) ? { ok: true, message: 'ControlNet + IP-Adapter/FaceID references found.' } : { ok: false, message: 'Needs both ControlNet and IP-Adapter/FaceID references.' };
  if (mode === 'strong_identity' || mode === 'face_only') return hasFaceId ? { ok: true, message: 'FaceID reference found.' } : (hasIp ? { ok: true, message: 'No FaceID found; will fall back to available IP-Adapter reference.' } : { ok: false, message: 'Needs a FaceID/IP-Adapter reference image.' });
  if (mode === 'soft_identity') return hasIp || hasFaceId ? { ok: true, message: 'IP-Adapter/FaceID reference found.' } : { ok: false, message: 'Needs an IP-Adapter or FaceID reference image.' };
  if (mode === 'style_only') return hasIp ? { ok: true, message: 'IP-Adapter style reference found.' } : (hasFaceId ? { ok: true, message: 'Only FaceID found; style-only will use it cautiously.' } : { ok: false, message: 'Needs an IP-Adapter image reference.' });
  if (mode === 'ipadapter') return hasIp || hasFaceId ? { ok: true, message: 'Legacy IP-Adapter/FaceID reference found.' } : { ok: false, message: 'Needs an IP-Adapter/FaceID reference.' };
  return { ok: true, message: 'Reference lock mode staged.' };
}

function renderGenerationDetailerReport(source='') {
  const el = $('generation-detailer-report-content');
  if (!el) return;
  const boxes = Array.isArray(generationDetailerBoxEditorState?.boxes) ? generationDetailerBoxEditorState.boxes : [];
  const targets = getGenerationDetailerOrderedPromptTargets();
  const rows = getGenerationDetailerPromptMapRows();
  const posParts = splitGenerationDetailerSepText($('generation-detailer-positive')?.value || '').filter(part => part || part === '');
  const negParts = splitGenerationDetailerSepText($('generation-detailer-negative')?.value || '').filter(part => part || part === '');
  const lock = $('generation-detailer-reference-lock')?.value || 'none';
  const ready = getGenerationDetailerReferenceReadiness(lock);
  const detector = $('generation-detailer-model')?.value || 'not selected';
  const detectorType = $('generation-detailer-detector-type')?.value || 'bbox';
  const order = $('generation-detailer-order')?.value || 'auto';
  const start = $('generation-detailer-start-index')?.value || '1';
  const count = $('generation-detailer-count')?.value || '1';
  const selectedList = targets.length ? targets.map(t => `#${t.index} ${escapeHtml(t.label || 'target')} ${t.confidence ? `(conf ${Number(t.confidence).toFixed(2)})` : ''}`).join('<br>') : 'No selected targets yet.';
  const warnings = [];
  if (!boxes.length) warnings.push('Run Detect targets to populate detection data.');
  if (boxes.length && !targets.length) warnings.push('Detections exist, but current filters selected zero targets. Check Start/Count/min/max area.');
  if (rows.length && targets.length && rows.length !== targets.length) warnings.push(`Prompt rows (${rows.length}) do not match selected targets (${targets.length}).`);
  if (lock !== 'none' && !ready.ok) warnings.push(ready.message);
  if (posParts.length > targets.length && targets.length) warnings.push(`Positive [SEP] has ${posParts.length} chunks but only ${targets.length} target(s) are selected.`);
  el.innerHTML = `
    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px;"> 
      <div><strong>Detected</strong><br>${boxes.length}</div>
      <div><strong>Selected</strong><br>${targets.length}</div>
      <div><strong>Prompt rows</strong><br>${rows.length}</div>
      <div><strong>Reference lock</strong><br>${escapeHtml(getGenerationDetailerReferenceLockLabel(lock))}</div>
    </div>
    <div style="margin-top:10px;"><strong>Detector</strong>: ${escapeHtml(detectorType)} · ${escapeHtml(detector)} · order ${escapeHtml(order.replace(/_/g, ' '))} · start ${escapeHtml(start)} · count ${escapeHtml(count)}</div>
    <div style="margin-top:8px;"><strong>Reference readiness</strong>: ${ready.ok ? '✅' : '⚠️'} ${escapeHtml(ready.message)}</div>
    <div style="margin-top:8px;"><strong>[SEP]</strong>: positive ${posParts.length} chunk(s) · negative ${negParts.length} chunk(s)</div>
    <div style="margin-top:8px;"><strong>Selected target order</strong><br>${selectedList}</div>
    ${warnings.length ? `<div style="margin-top:10px; color:#ffd166;"><strong>Warnings</strong><br>${warnings.map(escapeHtml).join('<br>')}</div>` : ''}
    <div class="mini-note" style="margin-top:8px; opacity:.75;">Updated by ${escapeHtml(source || 'report')}.</div>`;
}

function copyGenerationDetailerReport() {
  const el = $('generation-detailer-report-content');
  if (!el) return;
  const text = el.innerText || el.textContent || '';
  navigator.clipboard?.writeText(text).then(() => {
    setStatus('generation-detailer-status', 'ADetailer report copied.', 'success');
  }).catch(() => {
    setStatus('generation-detailer-status', 'Could not copy report automatically. Select the report text manually.', 'warn');
  });
}


const generationDetailerSmartPresetStorageKey = 'neo_generation_detailer_smart_presets_v1';

const generationDetailerBuiltInSmartPresets = {
  face_clean: {
    label: 'Face Clean',
    hint: 'Subtle face cleanup with low denoise. Good for already-good faces.',
    values: {
      enabled: true, mode: 'face', detectorType: 'bbox', modelKeywords: ['face'], order: 'left_to_right',
      start: 1, count: 1, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.35, topK: 0, bboxGrow: 12, maskBlur: 4, denoise: 0.12, steps: 12,
      useMainPrompt: true, forceInpaint: true, customClasses: ''
    }
  },
  face_rebuild: {
    label: 'Face Rebuild',
    hint: 'Stronger face repair for warped or soft faces. Use carefully; identity can drift.',
    values: {
      enabled: true, mode: 'face', detectorType: 'bbox', modelKeywords: ['face'], order: 'left_to_right',
      start: 1, count: 1, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.28, topK: 0, bboxGrow: 18, maskBlur: 6, denoise: 0.28, steps: 18,
      useMainPrompt: true, forceInpaint: true, customClasses: ''
    }
  },
  hands_fix: {
    label: 'Hands Fix',
    hint: 'Hand-focused repair with a wider crop and stronger denoise.',
    values: {
      enabled: true, mode: 'hands', detectorType: 'bbox', modelKeywords: ['hand'], order: 'largest_first',
      start: 1, count: 2, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.25, topK: 0, bboxGrow: 24, maskBlur: 6, denoise: 0.32, steps: 20,
      useMainPrompt: true, forceInpaint: true, customClasses: ''
    }
  },
  eyes_polish: {
    label: 'Eyes Polish',
    hint: 'Gentle face pass tuned for eyes/skin polish, not a full rebuild.',
    values: {
      enabled: true, mode: 'face', detectorType: 'bbox', modelKeywords: ['face'], order: 'left_to_right',
      start: 1, count: 2, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.4, topK: 0, bboxGrow: 8, maskBlur: 3, denoise: 0.09, steps: 10,
      useMainPrompt: true, forceInpaint: true, customClasses: ''
    }
  },
  anime_face: {
    label: 'Anime Face',
    hint: 'Anime/illustration face repair. Uses face bbox models and a slightly cleaner mask edge.',
    values: {
      enabled: true, mode: 'face', detectorType: 'bbox', modelKeywords: ['face'], order: 'left_to_right',
      start: 1, count: 2, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.3, topK: 0, bboxGrow: 14, maskBlur: 3, denoise: 0.18, steps: 16,
      useMainPrompt: true, forceInpaint: true, customClasses: 'anime face, face'
    }
  },
  product_logo: {
    label: 'Product / Logo Repair',
    hint: 'Custom/object-focused repair. Best with manual boxes or custom detector notes.',
    values: {
      enabled: true, mode: 'custom', detectorType: 'bbox', modelKeywords: [], order: 'largest_first',
      start: 1, count: 1, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'manual_boxes',
      confidence: 0.3, topK: 0, bboxGrow: 10, maskBlur: 2, denoise: 0.2, steps: 16,
      useMainPrompt: true, forceInpaint: true, customClasses: 'product, logo, object'
    }
  },
  clothing_detail: {
    label: 'Clothing Detail',
    hint: 'Person/clothing cleanup. Useful for jackets, outfits, uniforms, fabric details.',
    values: {
      enabled: true, mode: 'person', detectorType: 'bbox', modelKeywords: ['person', 'people', 'body'], order: 'largest_first',
      start: 1, count: 1, minArea: 0, maxArea: 0, referenceLock: 'none', targetMode: 'auto_detect',
      confidence: 0.3, topK: 0, bboxGrow: 18, maskBlur: 5, denoise: 0.18, steps: 16,
      useMainPrompt: true, forceInpaint: true, customClasses: 'clothing, outfit, fabric'
    }
  }
};

function setGenerationDetailerSmartPresetStatus(message='', tone='') {
  const el = $('generation-detailer-smart-preset-status');
  if (!el) return;
  el.textContent = message || 'Pick a preset as a starting point. Built-ins are safe defaults; saved presets are stored in this browser.';
  el.style.color = tone === 'warn' ? '#ffd166' : tone === 'error' ? '#ff8c8c' : tone === 'success' ? '#8ff0a4' : '';
}

function getGenerationDetailerSavedPresets() {
  try {
    const raw = localStorage.getItem(generationDetailerSmartPresetStorageKey);
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed) ? parsed.filter(item => item && item.name && item.values) : [];
  } catch (_) { return []; }
}

function saveGenerationDetailerSavedPresets(items) {
  try { localStorage.setItem(generationDetailerSmartPresetStorageKey, JSON.stringify(Array.isArray(items) ? items : [])); } catch (_) {}
}

function refreshGenerationDetailerSavedPresetSelect() {
  const select = $('generation-detailer-user-preset-select');
  if (!select) return;
  const current = select.value || '';
  select.innerHTML = '<option value="">Saved presets…</option>';
  getGenerationDetailerSavedPresets().forEach((item, index) => {
    const opt = document.createElement('option');
    opt.value = String(index);
    opt.textContent = item.name;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
}

function generationDetailerDispatchInput(el) {
  if (!el) return;
  el.dispatchEvent(new Event('input', { bubbles:true }));
  el.dispatchEvent(new Event('change', { bubbles:true }));
}

function generationDetailerSetValue(id, value) {
  const el = $(id);
  if (!el) return;
  el.value = String(value);
  generationDetailerDispatchInput(el);
}

function generationDetailerSetChecked(id, value) {
  const el = $(id);
  if (!el) return;
  el.checked = !!value;
  generationDetailerDispatchInput(el);
}

function generationDetailerPickModelByKeywords(keywords=[]) {
  const select = $('generation-detailer-model');
  if (!select) return '';
  const opts = Array.from(select.options).filter(opt => opt.value);
  if (!opts.length) return '';
  const keys = (Array.isArray(keywords) ? keywords : []).map(k => String(k || '').toLowerCase()).filter(Boolean);
  if (!keys.length) return select.value || opts[0].value;
  const exactish = opts.find(opt => keys.some(key => String(opt.value || '').toLowerCase().includes(key)));
  return (exactish || opts[0]).value;
}

function collectGenerationDetailerCurrentPresetValues() {
  return {
    enabled: !!$('generation-detailer-enabled')?.checked,
    mode: $('generation-detailer-mode')?.value || 'face',
    detectorType: $('generation-detailer-detector-type')?.value || 'bbox',
    model: $('generation-detailer-model')?.value || '',
    order: $('generation-detailer-order')?.value || 'auto',
    start: Number($('generation-detailer-start-index')?.value || 1),
    count: Number($('generation-detailer-count')?.value || 1),
    minArea: Number($('generation-detailer-min-area')?.value || 0),
    maxArea: Number($('generation-detailer-max-area')?.value || 0),
    referenceLock: $('generation-detailer-reference-lock')?.value || 'none',
    targetMode: $('generation-detailer-target-mode')?.value || 'auto_detect',
    confidence: Number($('generation-detailer-confidence')?.value || 0.35),
    topK: Number($('generation-detailer-topk')?.value || 0),
    bboxGrow: Number($('generation-detailer-bbox-grow')?.value || 12),
    maskBlur: Number($('generation-detailer-mask-blur')?.value || 4),
    denoise: Number($('generation-detailer-denoise')?.value || 0.12),
    steps: Number($('generation-detailer-steps')?.value || 12),
    useMainPrompt: !!$('generation-detailer-use-main-prompt')?.checked,
    forceInpaint: !!$('generation-detailer-force-inpaint')?.checked,
    customClasses: $('generation-detailer-custom-classes')?.value || ''
  };
}

function applyGenerationDetailerSmartPresetValues(values={}, label='Preset') {
  if (!values || typeof values !== 'object') return;
  generationDetailerSetChecked('generation-detailer-enabled', values.enabled !== false);
  if (values.mode) generationDetailerSetValue('generation-detailer-mode', values.mode);
  if (values.detectorType) generationDetailerSetValue('generation-detailer-detector-type', values.detectorType);
  if (typeof populateGenerationDetailerModelSelect === 'function') populateGenerationDetailerModelSelect(false);
  const wantedModel = values.model || generationDetailerPickModelByKeywords(values.modelKeywords || []);
  if (wantedModel) generationDetailerSetValue('generation-detailer-model', wantedModel);
  if (values.order) generationDetailerSetValue('generation-detailer-order', values.order);
  generationDetailerSetValue('generation-detailer-start-index', values.start ?? 1);
  generationDetailerSetValue('generation-detailer-count', values.count ?? 1);
  generationDetailerSetValue('generation-detailer-min-area', values.minArea ?? 0);
  generationDetailerSetValue('generation-detailer-max-area', values.maxArea ?? 0);
  if (values.referenceLock) generationDetailerSetValue('generation-detailer-reference-lock', values.referenceLock);
  if (values.targetMode) generationDetailerSetValue('generation-detailer-target-mode', values.targetMode);
  generationDetailerSetValue('generation-detailer-confidence', values.confidence ?? 0.35);
  generationDetailerSetValue('generation-detailer-topk', values.topK ?? 0);
  generationDetailerSetValue('generation-detailer-bbox-grow', values.bboxGrow ?? 12);
  generationDetailerSetValue('generation-detailer-mask-blur', values.maskBlur ?? 4);
  generationDetailerSetValue('generation-detailer-denoise', values.denoise ?? 0.12);
  generationDetailerSetValue('generation-detailer-steps', values.steps ?? 12);
  generationDetailerSetChecked('generation-detailer-use-main-prompt', values.useMainPrompt !== false);
  generationDetailerSetChecked('generation-detailer-force-inpaint', values.forceInpaint !== false);
  if (typeof values.customClasses === 'string') generationDetailerSetValue('generation-detailer-custom-classes', values.customClasses);
  if (typeof syncGenerationPrimaryDetailerManualUi === 'function') syncGenerationPrimaryDetailerManualUi();
  if (typeof renderGenerationFinishFoundation === 'function') renderGenerationFinishFoundation();
  if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
  if (typeof renderGenerationDetailerReport === 'function') renderGenerationDetailerReport('smart-preset');
  const modelNote = wantedModel ? ` · model: ${wantedModel}` : ' · pick/refresh detector model if needed';
  setGenerationDetailerSmartPresetStatus(`${label} applied${modelNote}. Fine-tune before running if needed.`, 'success');
  setStatus('generation-detailer-status', `${label} smart preset applied.`, 'success');
}

function applyGenerationDetailerBuiltInSmartPreset(key) {
  const preset = generationDetailerBuiltInSmartPresets[key];
  if (!preset) return;
  applyGenerationDetailerSmartPresetValues(preset.values, preset.label);
}

function saveGenerationDetailerCurrentSmartPreset() {
  const name = window.prompt('Name this ADetailer preset:', 'My ADetailer preset');
  const clean = String(name || '').trim();
  if (!clean) return;
  const items = getGenerationDetailerSavedPresets();
  const existingIndex = items.findIndex(item => String(item.name || '').toLowerCase() === clean.toLowerCase());
  const item = { name: clean, values: collectGenerationDetailerCurrentPresetValues(), saved_at: new Date().toISOString() };
  if (existingIndex >= 0) items[existingIndex] = item;
  else items.push(item);
  saveGenerationDetailerSavedPresets(items.slice(-30));
  refreshGenerationDetailerSavedPresetSelect();
  setGenerationDetailerSmartPresetStatus(`Saved preset: ${clean}`, 'success');
}

function applyGenerationDetailerSavedSmartPreset() {
  const select = $('generation-detailer-user-preset-select');
  const index = Number(select?.value || -1);
  const item = getGenerationDetailerSavedPresets()[index];
  if (!item) return;
  applyGenerationDetailerSmartPresetValues(item.values, item.name);
}

function deleteGenerationDetailerSavedSmartPreset() {
  const select = $('generation-detailer-user-preset-select');
  const index = Number(select?.value || -1);
  const items = getGenerationDetailerSavedPresets();
  const item = items[index];
  if (!item) {
    setGenerationDetailerSmartPresetStatus('Choose a saved preset to delete.', 'warn');
    return;
  }
  if (!window.confirm(`Delete saved ADetailer preset "${item.name}"?`)) return;
  items.splice(index, 1);
  saveGenerationDetailerSavedPresets(items);
  refreshGenerationDetailerSavedPresetSelect();
  setGenerationDetailerSmartPresetStatus(`Deleted preset: ${item.name}`, 'success');
}

function bindGenerationDetailerSmartPresetControls() {
  document.querySelectorAll('.generation-detailer-preset-chip').forEach(btn => {
    if (btn.dataset.neoPresetBound === '1') return;
    btn.dataset.neoPresetBound = '1';
    btn.addEventListener('click', () => applyGenerationDetailerBuiltInSmartPreset(btn.getAttribute('data-detailer-preset')));
  });
  $('btn-generation-detailer-save-preset')?.addEventListener('click', () => saveGenerationDetailerCurrentSmartPreset());
  $('btn-generation-detailer-delete-preset')?.addEventListener('click', () => deleteGenerationDetailerSavedSmartPreset());
  $('generation-detailer-user-preset-select')?.addEventListener('change', () => applyGenerationDetailerSavedSmartPreset());
  refreshGenerationDetailerSavedPresetSelect();
}

function bindGenerationDetailerPromptMapperControls() {
  bindGenerationDetailerSmartPresetControls();
  if (typeof updateGenerationDetailerReferenceLockHint === 'function') updateGenerationDetailerReferenceLockHint();
  $('generation-detailer-reference-lock')?.addEventListener('change', () => { if (typeof updateGenerationDetailerReferenceLockHint === 'function') updateGenerationDetailerReferenceLockHint(); renderGenerationDetailerReport('reference-lock'); });
  $('btn-generation-detailer-prompt-map-detect')?.addEventListener('click', () => detectGenerationDetailerPromptMapTargets());
  $('btn-generation-detailer-prompt-map-apply')?.addEventListener('click', () => exportGenerationDetailerPromptMapToSep());
  $('btn-generation-detailer-prompt-map-same')?.addEventListener('click', () => copyFirstGenerationDetailerPromptToAll());
  $('btn-generation-detailer-prompt-map-clear')?.addEventListener('click', () => clearGenerationDetailerPromptMap());
  $('btn-generation-detailer-report-refresh')?.addEventListener('click', () => renderGenerationDetailerReport('manual-refresh'));
  $('btn-generation-detailer-report-copy')?.addEventListener('click', () => copyGenerationDetailerReport());
  renderGenerationDetailerReport('initial');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bindGenerationDetailerPromptMapperControls);
} else {
  bindGenerationDetailerPromptMapperControls();
}
