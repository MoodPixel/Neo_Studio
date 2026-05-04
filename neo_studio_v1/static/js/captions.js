let captionCropState = null;
let captionCropDrag = null;
let captionImageObjectUrl = '';
let captionSelectedComponentIds = new Set();
let captionAutoComponentValue = '';
let captionBrowserEntries = [];
let captionBrowserPage = 1;
let captionBrowserRefreshHandle = null;

function componentTypeForMode(mode) {
  return {
    full_image: '',
    face_only: 'face',
    person_only: 'person',
    outfit_only: 'outfit',
    pose_only: 'pose',
    location_only: 'location',
    custom_crop: 'custom',
  }[mode || 'full_image'] || '';
}

function modeDefaultCrop(mode) {
  if (mode === 'face_only') return { x:0.18, y:0.02, w:0.64, h:0.42 };
  if (mode === 'person_only') return { x:0.10, y:0.03, w:0.80, h:0.92 };
  if (mode === 'outfit_only') return { x:0.18, y:0.18, w:0.64, h:0.62 };
  if (mode === 'pose_only') return { x:0.08, y:0.03, w:0.84, h:0.92 };
  return null;
}

function cropSummaryText(crop) {
  if (!crop) return 'No crop selected. Full image will be used unless the chosen mode applies a default crop.';
  const x = Math.round((crop.x || 0) * 100);
  const y = Math.round((crop.y || 0) * 100);
  const w = Math.round((crop.w || 0) * 100);
  const h = Math.round((crop.h || 0) * 100);
  return `Crop active — x ${x}%, y ${y}%, w ${w}%, h ${h}%.`;
}

function cropJsonValue() {
  return captionCropState ? JSON.stringify(captionCropState) : '';
}


function detailLevelLabel(level) {
  return {
    basic: 'basic',
    detailed: 'detailed',
    attribute_rich: 'attribute-rich',
  }[level || 'detailed'] || 'detailed';
}

function modeGuidanceText(mode, detailLevel) {
  const detail = detailLevelLabel(detailLevel);
  const base = {
    full_image: 'Describe the whole image in a grounded way. Keep the main subject first, then add visible appearance, outfit, pose, and setting.',
    face_only: 'Describe only the visible face and hair. Attribute-rich mode should break down brows, eyes, nose, lips, jawline, chin, hair, and expression.',
    person_only: 'Describe the visible person or character only. Attribute-rich mode should cover build, posture, pose, outfit pieces, colors, materials, accessories, hair, and visible face details.',
    outfit_only: 'Describe only the outfit, layers, fabrics, accessories, and footwear. Ignore face and location unless unavoidable.',
    pose_only: 'Describe body pose, gesture, stance, and limb placement. Ignore detailed outfit and background description unless unavoidable.',
    location_only: 'Describe only the location, props, architecture, lighting, and atmosphere. Ignore people except for minimal foreground mentions when unavoidable.',
    custom_crop: 'Describe only the selected crop area. Attribute-rich mode should squeeze as much grounded detail as possible from that region.',
  }[mode || 'full_image'] || 'Describe only what is visible.';
  return `${base} Detail level: ${detail}. Only include visible details; do not invent hidden traits.`;
}

function refreshCaptionGuidance() {
  const mode = $('caption-mode')?.value || 'full_image';
  const detailLevel = $('caption-detail-level')?.value || 'detailed';
  const node = $('caption-mode-guidance');
  if (node) node.textContent = modeGuidanceText(mode, detailLevel);
  const saveNode = $('caption-save-mode-summary');
  if (saveNode) saveNode.textContent = `Current mode: ${mode.replace(/_/g, ' ')}. Detail level: ${detailLevelLabel(detailLevel)}. Saved captions keep the mode, detail level, and crop metadata.`;
}

function updateCaptionCropOverlay() {
  const wrap = $('caption-preview-wrap');
  const box = $('caption-crop-box');
  if (!wrap || !box) return;
  if (!captionCropState) {
    box.classList.add('hidden');
    return;
  }
  const rect = wrap.getBoundingClientRect();
  box.style.left = `${captionCropState.x * rect.width}px`;
  box.style.top = `${captionCropState.y * rect.height}px`;
  box.style.width = `${captionCropState.w * rect.width}px`;
  box.style.height = `${captionCropState.h * rect.height}px`;
  box.classList.remove('hidden');
  const summary = cropSummaryText(captionCropState);
  $('caption-crop-summary').textContent = summary;
  $('caption-save-mode-summary').textContent = `This save will remember ${$('caption-mode').value.replace(/_/g, ' ')} (${detailLevelLabel($('caption-detail-level')?.value || 'detailed')}) and the active crop.`;
}

function resetCaptionCrop() {
  captionCropState = null;
  captionCropDrag = null;
  $('caption-crop-summary').textContent = cropSummaryText(null);
  $('caption-save-mode-summary').textContent = 'This save will remember the current caption mode, detail level, and crop, if used.';
  updateCaptionCropOverlay();
}

function setCaptionCropState(crop) {
  captionCropState = crop ? {
    x: Math.max(0, Math.min(1, Number(crop.x || 0))),
    y: Math.max(0, Math.min(1, Number(crop.y || 0))),
    w: Math.max(0.01, Math.min(1, Number(crop.w || 0))),
    h: Math.max(0.01, Math.min(1, Number(crop.h || 0))),
  } : null;
  if (captionCropState) {
    captionCropState.w = Math.min(captionCropState.w, 1 - captionCropState.x);
    captionCropState.h = Math.min(captionCropState.h, 1 - captionCropState.y);
  }
  updateCaptionCropOverlay();
}

function applyCaptionModeDefaults(force=false) {
  const mode = $('caption-mode')?.value || 'full_image';
  const suggested = componentTypeForMode(mode);
  const current = $('caption-component-type')?.value || '';
  if ($('caption-component-type') && (force || !current || current === captionAutoComponentValue)) {
    $('caption-component-type').value = suggested;
    captionAutoComponentValue = suggested;
  }
  if ($('caption-save-component-type') && (force || !$('caption-save-component-type').value || $('caption-save-component-type').value === captionAutoComponentValue)) {
    $('caption-save-component-type').value = suggested;
  }
  if (mode === 'custom_crop') {
    $('caption-crop-summary').textContent = captionCropState ? cropSummaryText(captionCropState) : 'Custom crop mode requires a selected crop box.';
  } else if (!captionCropState) {
    const def = modeDefaultCrop(mode);
    $('caption-crop-summary').textContent = def ? `${cropSummaryText(def)} Default crop preview only; drag manually to override.` : cropSummaryText(null);
  }
  refreshCaptionGuidance();
  updateCaptionCropOverlay();
}

function pointerCropPos(event) {
  const wrap = $('caption-preview-wrap');
  if (!wrap) return null;
  const rect = wrap.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
  };
}

function startCaptionCropDrag(event) {
  if (!$('caption-preview-wrap') || $('caption-preview-wrap').classList.contains('hidden')) return;
  if (event.button !== undefined && event.button !== 0) return;
  const pos = pointerCropPos(event);
  if (!pos) return;
  captionCropDrag = { startX: pos.x, startY: pos.y };
  setCaptionCropState({ x: pos.x, y: pos.y, w: 0.01, h: 0.01 });
  event.preventDefault();
}

function moveCaptionCropDrag(event) {
  if (!captionCropDrag) return;
  const pos = pointerCropPos(event);
  if (!pos) return;
  const x = Math.min(captionCropDrag.startX, pos.x);
  const y = Math.min(captionCropDrag.startY, pos.y);
  const w = Math.abs(captionCropDrag.startX - pos.x);
  const h = Math.abs(captionCropDrag.startY - pos.y);
  setCaptionCropState({ x, y, w: Math.max(w, 0.01), h: Math.max(h, 0.01) });
  event.preventDefault();
}

function endCaptionCropDrag() {
  captionCropDrag = null;
}

function useAutoCaptionCrop() {
  const mode = $('caption-mode')?.value || 'full_image';
  const def = modeDefaultCrop(mode);
  if (!def) {
    setStatus('caption-run-status', 'This mode has no default crop. Drag on the image or use full image mode.', 'warn');
    return;
  }
  setCaptionCropState(def);
  setStatus('caption-run-status', 'Mode default crop applied.');
}

function setCaptionPreviewFile(file) {
  const wrap = $('caption-preview-wrap');
  const img = $('caption-preview');
  if (!file || !wrap || !img) return;
  if (captionImageObjectUrl) URL.revokeObjectURL(captionImageObjectUrl);
  captionImageObjectUrl = URL.createObjectURL(file);
  img.src = captionImageObjectUrl;
  img.style.display = 'block';
  wrap.classList.remove('hidden');
  img.onload = () => updateCaptionCropOverlay();
  resetCaptionCrop();
  applyCaptionModeDefaults(true);
  refreshCaptionGuidance();
}

function componentBrowserParams() {
  const params = new URLSearchParams();
  const q = trim($('component-browser-query')?.value || '');
  const category = $('component-browser-category')?.value || '';
  const componentType = $('component-browser-type')?.value || '';
  if (q) params.set('query', q);
  if (category && category !== 'all') params.set('category', category);
  if (componentType) params.set('component_type', componentType);
  params.set('component_only', 'true');
  params.set('limit', '80');
  return params;
}

function captionBrowserParams() {
  const params = new URLSearchParams();
  const q = trim($('caption-browser-query')?.value || '');
  const category = $('caption-browser-category')?.value || '';
  const model = trim($('caption-browser-model')?.value || '');
  const style = trim($('caption-browser-style')?.value || '');
  const dateFrom = $('caption-browser-date-from')?.value || '';
  const dateTo = $('caption-browser-date-to')?.value || '';
  const componentType = $('caption-browser-component')?.value || '';
  if (q) params.set('query', q);
  if (category && category !== 'all') params.set('category', category);
  if (model) params.set('model', model);
  if (style) params.set('prompt_style', style);
  if (componentType) params.set('component_type', componentType);
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo);
  params.set('sort', captionBrowserSortMode());
  params.set('page', String(Math.max(1, Number(captionBrowserPage) || 1)));
  params.set('page_size', String(captionBrowserPerPage()));
  return params;
}

function captionBrowserPerPage() {
  const value = Number($('caption-browser-page-size')?.value || 20);
  return [10, 20, 50].includes(value) ? value : 20;
}

function captionBrowserSortMode() {
  return $('caption-browser-sort')?.value || 'newest';
}

function captionBrowserTimestamp(entry) {
  return String(entry?.updated_at || entry?.created_at || '');
}

function renderCaptionBrowserPagination(totalCount, shownCount, totalPages) {
  const indicator = $('caption-browser-page-indicator');
  const summary = $('caption-browser-result-summary');
  const prev = $('btn-caption-browser-prev');
  const next = $('btn-caption-browser-next');
  const safePage = totalCount ? Math.min(Math.max(1, captionBrowserPage), totalPages) : 1;
  if (indicator) indicator.textContent = `Page ${safePage} of ${totalPages}`;
  if (summary) {
    if (!totalCount) {
      summary.textContent = 'Showing 0-0 of 0';
    } else {
      const start = ((safePage - 1) * captionBrowserPerPage()) + 1;
      const end = start + shownCount - 1;
      summary.textContent = `Showing ${start}-${end} of ${totalCount}`;
    }
  }
  if (prev) prev.disabled = safePage <= 1 || !totalCount;
  if (next) next.disabled = safePage >= totalPages || !totalCount;
}

function setCaptionBrowserPage(page) {
  captionBrowserPage = Math.max(1, Number(page) || 1);
  refreshCaptionBrowser();
}

function changeCaptionBrowserPage(delta) {
  setCaptionBrowserPage(captionBrowserPage + (Number(delta) || 0));
}

function resetCaptionBrowserControls() {
  if ($('caption-browser-sort')) $('caption-browser-sort').value = 'newest';
  if ($('caption-browser-page-size')) $('caption-browser-page-size').value = '20';
  captionBrowserPage = 1;
}

function scheduleCaptionBrowserRefresh(resetPage=true) {
  window.clearTimeout(captionBrowserRefreshHandle);
  captionBrowserRefreshHandle = window.setTimeout(() => refreshCaptionBrowser({ resetPage }), 220);
}


function captionPresetRecentNames(limit=8) {
  return Object.entries(captionPresets || {})
    .sort((a, b) => {
      const aa = String(a[1]?.last_used || '');
      const bb = String(b[1]?.last_used || '');
      if (aa === bb) return a[0].localeCompare(b[0], undefined, { sensitivity:'base' });
      return bb.localeCompare(aa);
    })
    .slice(0, limit)
    .map(([name]) => name);
}

function refreshCaptionPresetAux(selectedName='') {
  const current = selectedName || $('caption-preset')?.value || '';
  const names = Object.keys(captionPresets || {}).sort((a, b) => a.localeCompare(b, undefined, { sensitivity:'base' }));
  fillNamedSelect('caption-preset-recent', captionPresetRecentNames(), '', 'Recent presets');
  fillNamedSelect('caption-preset-compare', names.filter(name => name !== current), '', 'Choose preset');
  const preset = captionPresets[current] || {};
  if ($('caption-preset-group')) $('caption-preset-group').value = preset.group || '';
  if ($('caption-preset-notes')) $('caption-preset-notes').value = preset.notes || '';
  if ($('caption-preset-favorite')) $('caption-preset-favorite').checked = !!preset.favorite;
  if ($('caption-preset-meta')) $('caption-preset-meta').textContent = presetMetaSummary(preset);
  if ($('caption-preset-compare-output')) {
    $('caption-preset-compare-output').classList.add('hidden');
    $('caption-preset-compare-output').textContent = '';
  }
}

function renderCaptionPresetComparison(comparison) {
  const wrap = $('caption-preset-compare-output');
  if (!wrap) return;
  const diffs = comparison?.differences || [];
  if (!diffs.length) {
    wrap.textContent = 'No differences found between the selected caption presets.';
    wrap.classList.remove('hidden');
    return;
  }
  const lines = [`${comparison.title_a} vs ${comparison.title_b}`];
  diffs.forEach(row => lines.push(`${row.field}: ${row.a ?? '—'} → ${row.b ?? '—'}`));
  wrap.textContent = lines.join('\n');
  wrap.classList.remove('hidden');
}

function openLightbox(url) {
  const wrap = $('image-lightbox');
  const img = $('lightbox-image');
  if (!wrap || !img || !url) return;
  img.src = url;
  wrap.classList.remove('hidden');
}

function closeLightbox() {
  const wrap = $('image-lightbox');
  const img = $('lightbox-image');
  if (!wrap || !img) return;
  wrap.classList.add('hidden');
  img.src = '';
}

function renderCaptionBrowser(entries) {
  const wrap = $('caption-browser-grid');
  wrap.innerHTML = '';
  if (!entries || !entries.length) {
    wrap.innerHTML = '<div class="card-lite"><div class="muted">No saved captions match the current filters.</div></div>';
    return;
  }
  entries.forEach(entry => {
    const card = document.createElement('div');
    card.className = 'caption-card';
    const updated = (entry.updated_at || entry.created_at || '').replace('T', ' ');
    const componentBits = [];
    if (entry.component_type) componentBits.push(entry.component_type);
    if (entry.caption_mode) componentBits.push(String(entry.caption_mode || '').replace(/_/g, ' '));
    if (entry.detail_level) componentBits.push(String(entry.detail_level || '').replace(/_/g, '-'));
    const componentMeta = componentBits.join(' · ');
    card.innerHTML = `
      <img src="${entry.thumb_url}" alt="${escapeHtml(entry.name || 'caption')}" loading="lazy" />
      <div class="caption-card-body">
        <div class="caption-card-title">${escapeHtml(entry.name || '(untitled)')}</div>
        <div class="caption-card-meta">${escapeHtml(entry.category || 'uncategorized')} · ${escapeHtml(entry.model || 'default')}</div>
        <div class="caption-card-meta">${escapeHtml(entry.prompt_style || '—')} · ${escapeHtml(updated || '—')}</div>
        ${componentMeta ? `<div class="caption-card-meta">${escapeHtml(componentMeta)}</div>` : ''}
        <div class="caption-card-snippet">${escapeHtml(entry.caption_preview || '')}</div>
        <div class="row" style="margin-top:auto;">
          <button class="btn" type="button" data-caption-edit="${entry.id}">Edit</button>
          <button class="btn" type="button" data-caption-preview="${entry.image_url}">Preview</button>
          <button class="btn" type="button" data-caption-send="${entry.id}">To Prompt</button>
        </div>
      </div>
    `;
    wrap.appendChild(card);
  });
}

async function refreshCaptionBrowser(options={}) {
  const { resetPage=false } = options || {};
  if (resetPage) captionBrowserPage = 1;
  try {
    setStatus('caption-browser-status', 'Loading saved captions...');
    const data = await safeFetchJson(`/api/caption-records?${captionBrowserParams().toString()}`);
    refreshCategoryList(data.categories || initialCategories);
    captionBrowserEntries = data.entries || [];
    captionBrowserPage = Math.max(1, Number(data.page) || captionBrowserPage || 1);
    renderCaptionBrowser(captionBrowserEntries);
    renderCaptionBrowserPagination(Number(data.total || 0), captionBrowserEntries.length, Math.max(1, Number(data.total_pages) || 1));
    setStatus('caption-browser-status', Number(data.total || 0) ? `${data.total} saved caption(s) found.` : 'No saved captions match the current filters.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-browser-status', e.message, 'error');
  }
}

function renderComponentBrowser(entries) {
  const wrap = $('component-browser-list');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!entries || !entries.length) {
    wrap.innerHTML = '<div class="card-lite"><div class="muted">No saved components match the current filters.</div></div>';
    return;
  }
  entries.forEach(entry => {
    const row = document.createElement('label');
    row.className = 'component-item';
    row.setAttribute('data-caption', entry.caption || '');
    row.innerHTML = `
      <input type="checkbox" data-component-id="${entry.id}" ${captionSelectedComponentIds.has(entry.id) ? 'checked' : ''} />
      <img src="${entry.thumb_url}" alt="${escapeHtml(entry.name || 'component')}" loading="lazy" />
      <div>
        <div class="component-item-title">${escapeHtml(entry.name || '(untitled)')}</div>
        <div class="component-item-meta">${escapeHtml(entry.component_type || 'component')} · ${escapeHtml((entry.category || 'uncategorized'))} · ${escapeHtml(String(entry.caption_mode || '').replace(/_/g, ' '))} · ${escapeHtml(String(entry.detail_level || 'detailed').replace(/_/g, '-'))}</div>
        <div class="component-item-snippet">${escapeHtml(entry.caption_preview || '')}</div>
      </div>
    `;
    wrap.appendChild(row);
  });
}

async function refreshComponentBrowser() {
  try {
    const data = await safeFetchJson(`/api/caption-records?${componentBrowserParams().toString()}`);
    if ($('component-browser-category')) fillCategorySelect('component-browser-category', ['all', ...(data.categories || initialCategories).filter(x => x !== 'all')], $('component-browser-category').value || 'all');
    renderComponentBrowser(data.entries || []);
    setStatus('component-browser-status', `${(data.entries || []).length} component(s) found.`);
  } catch (e) {
    setStatus('component-browser-status', e.message, 'error');
  }
}

function buildComponentDraftFromSelection() {
  const checked = Array.from(document.querySelectorAll('#component-browser-list [data-component-id]:checked')).map(el => el.getAttribute('data-component-id'));
  captionSelectedComponentIds = new Set(checked);
  const snippets = Array.from(document.querySelectorAll('#component-browser-list [data-component-id]:checked')).map(el => {
    const parent = el.closest('.component-item');
    return parent ? parent.getAttribute('data-caption') || '' : '';
  }).filter(Boolean);
  const unique = [];
  const seen = new Set();
  snippets.forEach(text => {
    const clean = trim(text.replace(/\s+/g, ' '));
    const key = clean.toLowerCase();
    if (!clean || seen.has(key)) return;
    seen.add(key);
    unique.push(clean);
  });
  $('component-draft-output').value = unique.join(', ');
  setStatus('component-browser-status', unique.length ? `${unique.length} component(s) merged into a new draft.` : 'Select one or more components first.', unique.length ? '' : 'warn');
}

function sendComponentDraftToPromptStudio() {
  const text = $('component-draft-output').value || '';
  if (!text) {
    setStatus('component-browser-status', 'Build a component draft first.', 'warn');
    return;
  }
  $('prompt-idea').value = text;
  $('prompt-output').value = text;
  $('prompt-raw').value = text;
  updateCounter('prompt-idea', 'prompt-idea-counter');
  updateCounter('prompt-output', 'prompt-output-counter');
  if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
  switchTab('prompt');
  setStatus('component-browser-status', 'Combined component draft sent to Prompt Studio.');
}

function clearComponentSelection() {
  captionSelectedComponentIds = new Set();
  document.querySelectorAll('#component-browser-list [data-component-id]').forEach(el => { el.checked = false; });
  $('component-draft-output').value = '';
  setStatus('component-browser-status', 'Component selection cleared.');
}

function loadCaptionRecordIntoEditor(rec) {
  loadedCaptionId = rec.id || '';
  $('caption-editor-id').value = rec.id || '';
  $('caption-editor-name').value = rec.name || '';
  fillCategorySelect('caption-editor-category', [rec.category || 'uncategorized'], rec.category || 'uncategorized');
  $('caption-editor-model').value = rec.model || '';
  $('caption-editor-style').value = rec.prompt_style || '';
  $('caption-editor-mode').value = String(rec.caption_mode || 'full_image').replace(/_/g, ' ');
  $('caption-editor-component-type').value = rec.component_type || '';
  if ($('caption-editor-detail-level')) $('caption-editor-detail-level').value = String(rec.detail_level || 'detailed').replace(/_/g, '-');
  $('caption-editor-updated').value = (rec.updated_at || rec.created_at || '').replace('T', ' ');
  $('caption-editor-caption').value = rec.caption || '';
  $('caption-editor-notes').value = rec.notes || '';
  $('caption-editor-image-url').value = rec.image_url || '';
  $('caption-editor-crop-summary').textContent = rec.crop_meta ? cropSummaryText(rec.crop_meta) : 'No crop metadata saved.';
  $('caption-editor-wrap').classList.remove('hidden');
}

async function loadCaptionRecord(captionId, statusId='caption-browser-status') {
  if (!captionId) return;
  try {
    const data = await safeFetchJson(`/api/caption-record?caption_id=${encodeURIComponent(captionId)}`);
    loadCaptionRecordIntoEditor(data.record || {});
    setStatus(statusId, 'Loaded saved caption.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus(statusId, e.message, 'error');
  }
}

async function updateCaptionRecord() {
  if (!loadedCaptionId) {
    setStatus('caption-editor-status', 'Pick a saved caption first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('caption_id', loadedCaptionId);
  fd.append('name', $('caption-editor-name').value || 'Untitled Caption');
  fd.append('category', $('caption-editor-category').value || 'uncategorized');
  fd.append('caption', $('caption-editor-caption').value || '');
  fd.append('notes', $('caption-editor-notes').value || '');
  fd.append('model', $('caption-editor-model').value || '');
  fd.append('prompt_style', $('caption-editor-style').value || '');
  fd.append('component_type', $('caption-editor-component-type').value || '');
  fd.append('detail_level', $('caption-editor-detail-level')?.value?.replace(/-/g, '_') || '');
  try {
    const data = await safeFetchJson('/api/update-caption', { method:'POST', body:fd });
    updateStats(data.stats);
    loadCaptionRecordIntoEditor(data.record || {});
    setStatus('caption-editor-status', data.message || 'Updated caption.');
    refreshCaptionBrowser();
    refreshComponentBrowser();
  } catch (e) {
    setStatus('caption-editor-status', e.message, 'error');
  }
}

async function deleteCaptionRecord() {
  if (!loadedCaptionId) {
    setStatus('caption-editor-status', 'Pick a saved caption first.', 'warn');
    return;
  }
  if (!confirm('Delete this saved caption and its image?')) return;
  const fd = new FormData();
  fd.append('caption_id', loadedCaptionId);
  try {
    const data = await safeFetchJson('/api/delete-caption', { method:'POST', body:fd });
    updateStats(data.stats);
    refreshCategoryList(data.categories || initialCategories);
    $('caption-editor-wrap').classList.add('hidden');
    $('caption-editor-id').value = '';
    loadedCaptionId = '';
    setStatus('caption-browser-status', data.message || 'Deleted caption.');
    refreshCaptionBrowser();
    refreshComponentBrowser();
  } catch (e) {
    setStatus('caption-editor-status', e.message, 'error');
  }
}

function sendCaptionEditorToPrompt() {
  const text = $('caption-editor-caption').value || '';
  if (!text) {
    setStatus('caption-editor-status', 'Nothing to send.', 'warn');
    return;
  }
  $('prompt-idea').value = text;
  $('prompt-output').value = text;
  $('prompt-raw').value = text;
  updateCounter('prompt-idea', 'prompt-idea-counter');
  updateCounter('prompt-output', 'prompt-output-counter');
  if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
  switchTab('prompt');
  setStatus('caption-editor-status', 'Caption sent to Prompt Studio.');
}

async function captionEditorToPromptRecord() {
  if (!loadedCaptionId) {
    setStatus('caption-editor-status', 'Pick a saved caption first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('caption_id', loadedCaptionId);
  fd.append('category', $('caption-editor-category').value || 'uncategorized');
  fd.append('prompt_name', `${$('caption-editor-name').value || 'Caption'} Prompt`);
  try {
    const data = await safeFetchJson('/api/caption-to-prompt', { method:'POST', body:fd });
    updateStats(data.stats);
    if (data.prompt_categories) fillCategorySelect('saved-prompt-category', data.prompt_categories, $('caption-editor-category').value || 'uncategorized');
    setStatus('caption-editor-status', data.message || 'Created prompt record from caption.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-editor-status', e.message, 'error');
  }
}

function renderMetadataLoras(loras) {
  const wrap = $('metadata-lora-list');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!loras || !loras.length) {
    wrap.innerHTML = '<div class="mini-note">No LoRA or embedding tokens detected.</div>';
    return;
  }
  loras.forEach(item => {
    const chip = document.createElement('div');
    chip.className = 'metadata-lora-chip';
    const details = [];
    if (item.weight !== '' && item.weight !== undefined) details.push(`weight ${item.weight}`);
    if (item.matched) details.push(`matched ${item.registry_name || item.name}`);
    if (item.default_strength !== undefined && item.default_strength !== null && item.default_strength !== '') details.push(`default ${item.default_strength}`);
    if (item.triggers && item.triggers.length) details.push(`triggers: ${item.triggers.join(', ')}`);
    chip.textContent = `${item.name || 'unknown'}${details.length ? ' — ' + details.join(' · ') : ''}`;
    wrap.appendChild(chip);
  });
}

async function loadMetadataRecord(recordId) {
  if (!recordId) return;
  try {
    const data = await safeFetchJson(`/api/output-metadata-record?record_id=${encodeURIComponent(recordId)}`);
    const record = data.record || {};
    setMetadataPayload(record.data || {}, `Loaded metadata record: ${record.name || recordId}`);
    if ($('metadata-save-name')) $('metadata-save-name').value = record.name || $('metadata-save-name').value || '';
    if ($('metadata-notes')) $('metadata-notes').value = record.notes || '';
    switchTab('caption');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('metadata-status', e.message, 'error');
  }
}

function setMetadataPayload(parsed, message='Metadata ready.') {
  currentMetadataPayload = parsed || null;
  if (!$('metadata-json')) return;
  $('metadata-json').value = currentMetadataPayload ? JSON.stringify(currentMetadataPayload) : '';
  $('metadata-positive').value = currentMetadataPayload?.positive_prompt || '';
  $('metadata-negative').value = currentMetadataPayload?.negative_prompt || '';
  $('metadata-raw').value = currentMetadataPayload?.raw_metadata || '';
  $('metadata-clean-rebuild').value = currentMetadataPayload?.clean_rebuild_prompt || '';
  $('metadata-settings-summary').textContent = currentMetadataPayload?.settings_summary || 'No summary extracted.';
  $('metadata-save-name').value = currentMetadataPayload?.source_filename ? currentMetadataPayload.source_filename.replace(/\.[^.]+$/, '') : ($('metadata-save-name').value || 'Recovered Prompt');
  renderMetadataLoras(currentMetadataPayload?.loras || []);
  setStatus('metadata-status', message);
}

async function inspectOutputMetadata() {
  const file = $('metadata-image')?.files?.[0];
  if (!file) {
    setStatus('metadata-status', 'Choose an image first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('image', file);
  setBusy('btn-inspect-metadata', true, 'Inspecting...');
  try {
    const data = await safeFetchJson('/api/inspect-output-metadata', { method:'POST', body:fd });
    setMetadataPayload(data.parsed || {}, 'Metadata loaded.');
    setWarning('metadata-compare-note', '');
  } catch (e) {
    setStatus('metadata-status', e.message, 'error');
  } finally {
    setBusy('btn-inspect-metadata', false);
  }
}

async function compareOutputMetadata() {
  const primary = $('metadata-image')?.files?.[0];
  const secondary = $('metadata-compare-image')?.files?.[0];
  if (!primary || !secondary) {
    setStatus('metadata-status', 'Pick both output images to compare.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('primary_image', primary);
  fd.append('secondary_image', secondary);
  setBusy('btn-compare-metadata', true, 'Comparing...');
  try {
    const data = await safeFetchJson('/api/compare-output-metadata', { method:'POST', body:fd });
    setMetadataPayload(data.primary || {}, 'Primary metadata loaded.');
    const diff = data.diff || {};
    const lines = [];
    if (diff.positive_changed) lines.push('Positive prompt changed.');
    if (diff.negative_changed) lines.push('Negative prompt changed.');
    (diff.settings_diff || []).slice(0, 8).forEach(row => lines.push(`${row.key}: ${row.primary || '—'} → ${row.secondary || '—'}`));
    if ((diff.loras_only_primary || []).length) lines.push(`Only in primary: ${diff.loras_only_primary.join(', ')}`);
    if ((diff.loras_only_secondary || []).length) lines.push(`Only in secondary: ${diff.loras_only_secondary.join(', ')}`);
    if ((diff.lora_weight_diff || []).length) {
      (diff.lora_weight_diff || []).slice(0, 6).forEach(row => lines.push(`${row.name}: ${row.primary_weight} → ${row.secondary_weight}`));
    }
    setWarning('metadata-compare-note', lines.join('\n') || 'No major differences detected.');
  } catch (e) {
    setStatus('metadata-status', e.message, 'error');
  } finally {
    setBusy('btn-compare-metadata', false);
  }
}

function sendMetadataToPromptStudio() {
  const text = $('metadata-clean-rebuild')?.value || $('metadata-positive')?.value || '';
  if (!text) {
    setStatus('metadata-status', 'Inspect metadata first.', 'warn');
    return;
  }
  $('prompt-idea').value = text;
  $('prompt-output').value = text;
  $('prompt-raw').value = $('metadata-raw').value || text;
  $('prompt-notes').value = $('metadata-negative').value ? `Negative prompt: ${$('metadata-negative').value}` : $('prompt-notes').value;
  updateCounter('prompt-idea', 'prompt-idea-counter');
  updateCounter('prompt-output', 'prompt-output-counter');
  if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
  switchTab('prompt');
  setStatus('metadata-status', 'Metadata prompt sent to Prompt Studio.');
}

function rebuildMetadataPrompt() {
  if (!currentMetadataPayload) {
    setStatus('metadata-status', 'Inspect metadata first.', 'warn');
    return;
  }
  const source = $('metadata-positive').value || currentMetadataPayload.positive_prompt || '';
  const parts = source.replace(/\n+/g, ', ').split(',').map(x => x.trim()).filter(Boolean);
  const seen = new Set();
  const cleaned = [];
  parts.forEach(part => {
    const key = part.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    cleaned.push(part.replace(/\s{2,}/g, ' '));
  });
  $('metadata-clean-rebuild').value = cleaned.join(', ');
  if (currentMetadataPayload) currentMetadataPayload.clean_rebuild_prompt = $('metadata-clean-rebuild').value;
  $('metadata-json').value = JSON.stringify(currentMetadataPayload || {});
  setStatus('metadata-status', 'Clean rebuild prompt updated.');
}

async function saveMetadataAsPromptRecord() {
  if (!currentMetadataPayload) {
    setStatus('metadata-status', 'Inspect metadata first.', 'warn');
    return;
  }
  currentMetadataPayload.positive_prompt = $('metadata-positive').value || currentMetadataPayload.positive_prompt || '';
  currentMetadataPayload.negative_prompt = $('metadata-negative').value || currentMetadataPayload.negative_prompt || '';
  currentMetadataPayload.clean_rebuild_prompt = $('metadata-clean-rebuild').value || currentMetadataPayload.clean_rebuild_prompt || '';
  $('metadata-json').value = JSON.stringify(currentMetadataPayload);
  const fd = new FormData();
  fd.append('metadata_json', $('metadata-json').value);
  fd.append('name', $('metadata-save-name').value || 'Recovered Prompt');
  fd.append('category', resolveCategory('metadata-save-category', 'metadata-save-category-new'));
  fd.append('notes', $('metadata-notes').value || '');
  fd.append('model', currentModel());
  try {
    const data = await safeFetchJson('/api/save-output-metadata-prompt', { method:'POST', body:fd });
    updateStats(data.stats);
    refreshCategoryList(data.categories || initialCategories);
    if (data.prompt_categories) fillCategorySelect('saved-prompt-category', data.prompt_categories, fd.get('category'));
    setStatus('metadata-status', data.message || 'Saved as prompt record.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('metadata-status', e.message, 'error');
  }
}

async function saveMetadataAsCharacterBase() {
  if (!currentMetadataPayload) {
    setStatus('metadata-status', 'Inspect metadata first.', 'warn');
    return;
  }
  currentMetadataPayload.positive_prompt = $('metadata-positive').value || currentMetadataPayload.positive_prompt || '';
  currentMetadataPayload.negative_prompt = $('metadata-negative').value || currentMetadataPayload.negative_prompt || '';
  currentMetadataPayload.clean_rebuild_prompt = $('metadata-clean-rebuild').value || currentMetadataPayload.clean_rebuild_prompt || '';
  $('metadata-json').value = JSON.stringify(currentMetadataPayload);
  const fd = new FormData();
  fd.append('metadata_json', $('metadata-json').value);
  fd.append('name', $('metadata-save-name').value || 'Recovered Character');
  fd.append('notes', $('metadata-notes').value || '');
  try {
    const data = await safeFetchJson('/api/save-output-metadata-character', { method:'POST', body:fd });
    const chars = await safeFetchJson('/api/character-records');
    fillSavedCharacterEntries(chars.entries || [], data.record?.name || '');
    setStatus('metadata-status', data.message || 'Saved as character base.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('metadata-status', e.message, 'error');
  }
}

async function captionImage(selectedAreaOnly=false) {
  if (!requireBackendRole('text', 'caption-run-status', 'Connect a Text Backend first. Caption image uses the active text model.')) return;
  const file = $('caption-image').files[0];
  if (!file) {
    setStatus('caption-run-status', 'Pick an image first.', 'warn');
    return;
  }
  const mode = $('caption-mode').value || 'full_image';
  if (selectedAreaOnly && !captionCropState) {
    setStatus('caption-run-status', 'Draw a crop box first, then use selected area captioning.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('model', currentModel());
  fd.append('image', file);
  fd.append('preset_name', $('caption-preset').value || '');
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
  fd.append('caption_mode', mode);
  fd.append('component_type', $('caption-component-type').value || componentTypeForMode(mode));
  fd.append('detail_level', $('caption-detail-level')?.value || 'detailed');
  fd.append('crop_json', cropJsonValue());
  fd.append('output_folder', $('batch-output-folder').value || '');
  setBusy('btn-caption-image', true, 'Captioning...');
  setStatus('caption-run-status', 'Captioning image...');
  setWarning('caption-warning', '');
  startTimer('caption', 'caption-elapsed');
  try {
    const data = await safeFetchJson('/api/caption-image', { method:'POST', body:fd });
    $('caption-output').value = data.caption || '';
    $('temp-image-id').value = data.temp_image_id || '';
    currentCaptionFinishReason = data.finish_reason || '';
    $('caption-finish-reason').textContent = `finish: ${currentCaptionFinishReason || 'stop'}`;
    if (data.effective_crop) setCaptionCropState(data.effective_crop);
    if (data.component_type && $('caption-save-component-type')) $('caption-save-component-type').value = data.component_type;
    if (data.detail_level && $('caption-detail-level')) $('caption-detail-level').value = data.detail_level;
    applyCaptionModeDefaults();
    setWarning('caption-warning', data.warning || '');
    setStatus('caption-run-status', data.caption ? 'Caption ready.' : 'No caption returned.', data.warning ? 'warn' : '');
    updateCounter('caption-output', 'caption-output-counter');
  } catch (e) {
    setStatus('caption-run-status', e.message, 'error');
  } finally {
    stopTimer('caption');
    setBusy('btn-caption-image', false);
  }
}

async function saveCaptionPreset(overwriteSelected=false) {
  let name = $('caption-preset').value;
  if (!overwriteSelected || !name || (captionPresets[name] && captionPresets[name].kind !== 'custom')) {
    name = prompt('Preset name:', overwriteSelected && name ? name : '');
  }
  name = trim(name);
  if (!name) return;
  const fd = new FormData();
  fd.append('name', name);
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
  fd.append('caption_mode', $('caption-mode')?.value || 'full_image');
  fd.append('component_type', $('caption-component-type')?.value || '');
  fd.append('detail_level', $('caption-detail-level')?.value || 'detailed');
  fd.append('group', $('caption-preset-group')?.value || '');
  fd.append('notes', $('caption-preset-notes')?.value || '');
  fd.append('favorite', $('caption-preset-favorite')?.checked ? 'true' : 'false');
  try {
    const data = await safeFetchJson('/api/save-caption-preset', { method:'POST', body:fd });
    captionPresets = data.presets || captionPresets;
    populatePresetSelect('caption-preset', captionPresets, data.last_preset || name);
    applyCaptionPreset(data.last_preset || name, false);
    refreshCaptionPresetAux(data.last_preset || name);
    setStatus('caption-preset-status', data.message || 'Preset saved.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-preset-status', e.message, 'error');
  }
}

async function deleteCaptionPreset() {
  const name = $('caption-preset').value;
  if (!name) return;
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/delete-caption-preset', { method:'POST', body:fd });
    captionPresets = data.presets || captionPresets;
    populatePresetSelect('caption-preset', captionPresets, data.last_preset || 'Tags');
    applyCaptionPreset($('caption-preset').value, false);
    refreshCaptionPresetAux($('caption-preset').value);
    setStatus('caption-preset-status', data.message || 'Preset deleted.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-preset-status', e.message, 'error');
  }
}

async function duplicateCaptionPreset() {
  const source = $('caption-preset').value || '';
  if (!source) {
    setStatus('caption-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  const newName = trim(prompt('New preset name:', `${source} Copy`) || '');
  if (!newName) return;
  const fd = new FormData();
  fd.append('source_name', source);
  fd.append('new_name', newName);
  try {
    const data = await safeFetchJson('/api/duplicate-caption-preset', { method:'POST', body:fd });
    captionPresets = data.presets || captionPresets;
    populatePresetSelect('caption-preset', captionPresets, data.last_preset || newName);
    applyCaptionPreset(data.last_preset || newName, false);
    refreshCaptionPresetAux(data.last_preset || newName);
    setStatus('caption-preset-meta-status', data.message || 'Preset duplicated.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-preset-meta-status', e.message, 'error');
  }
}

async function toggleCaptionPresetFavorite() {
  const name = $('caption-preset').value || '';
  if (!name) {
    setStatus('caption-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/toggle-caption-preset-favorite', { method:'POST', body:fd });
    captionPresets = data.presets || captionPresets;
    populatePresetSelect('caption-preset', captionPresets, data.last_preset || name);
    applyCaptionPreset(data.last_preset || name, false);
    refreshCaptionPresetAux(data.last_preset || name);
    setStatus('caption-preset-meta-status', data.favorite ? 'Preset marked as favorite.' : 'Preset favorite removed.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('caption-preset-meta-status', e.message, 'error');
  }
}

async function compareCaptionPresets() {
  const nameA = $('caption-preset').value || '';
  const nameB = $('caption-preset-compare').value || '';
  if (!nameA || !nameB) {
    setStatus('caption-preset-meta-status', 'Choose two presets to compare.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/compare-caption-presets?name_a=${encodeURIComponent(nameA)}&name_b=${encodeURIComponent(nameB)}`);
    renderCaptionPresetComparison(data.comparison || {});
    setStatus('caption-preset-meta-status', 'Preset comparison ready.');
  } catch (e) {
    setStatus('caption-preset-meta-status', e.message, 'error');
  }
}

async function exportSingleCaptionPreset() {
  const name = $('caption-preset').value || '';
  if (!name) {
    setStatus('caption-preset-meta-status', 'Select a preset first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/export-single-preset?kind=caption&name=${encodeURIComponent(name)}`);
    downloadJsonPayload(`neo_caption_preset_${name.replace(/[^a-z0-9_-]+/gi, '_')}.json`, data.payload || {});
    setStatus('caption-preset-meta-status', 'Preset export ready.');
  } catch (e) {
    setStatus('caption-preset-meta-status', e.message, 'error');
  }
}

async function saveCaptionEntry() {
  const fd = new FormData();
  const finalCategory = resolveCategory('caption-category', 'caption-category-new');
  fd.append('name', $('caption-name').value || 'Untitled Caption');
  fd.append('category', finalCategory);
  fd.append('caption', $('caption-output').value || '');
  fd.append('temp_image_id', $('temp-image-id').value || '');
  fd.append('model', currentModel());
  fd.append('notes', $('caption-notes').value || '');
  fd.append('raw_caption', $('caption-output').value || '');
  fd.append('preset_name', $('caption-preset').value || '');
  fd.append('prompt_style', $('caption-style').value || '');
  fd.append('finish_reason', currentCaptionFinishReason || '');
  fd.append('settings_json', captionSettingsJson());
  fd.append('component_type', $('caption-save-component-type').value || $('caption-component-type').value || '');
  fd.append('caption_mode', $('caption-mode').value || 'full_image');
  fd.append('detail_level', $('caption-detail-level')?.value || 'detailed');
  fd.append('crop_json', cropJsonValue());
  try {
    const data = await safeFetchJson('/api/save-caption', { method:'POST', body:fd });
    updateStats(data.stats);
    fillCategorySelect('caption-category', data.categories || initialCategories, finalCategory);
    $('caption-category-new').value = '';
    setStatus('caption-save-status', data.message || 'Caption saved.');
    refreshCaptionBrowser();
    refreshComponentBrowser();
  } catch (e) {
    setStatus('caption-save-status', e.message, 'error');
  }
}
