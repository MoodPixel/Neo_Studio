function updatePrimaryGenerationControlnetSummary() {
  const enabled = isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled'));
  const model = trim($('generation-controlnet-name')?.value || '');
  const unit = trim($('generation-controlnet-unit')?.value || 'auto') || 'auto';
  const preprocessor = trim($('generation-controlnet-preprocessor')?.value || 'none') || 'none';
  const strength = Number($('generation-controlnet-strength')?.value || 1.0);
  const file = $('generation-control-image')?.files?.[0] || null;
  const summary = $('generation-controlnet-primary-summary');
  toggleGenerationUnitDisabledState(document.querySelector('.generation-unit-card-controlnet[data-primary="true"]'), enabled);
  updateGenerationPreviewImage($('generation-control-image'), $('generation-controlnet-primary-preview'), $('generation-controlnet-primary-preview-empty'));
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This primary ControlNet unit will be skipped.';
    return;
  }
  if (!model) {
    summary.innerHTML = 'Primary ControlNet unit is idle.';
    return;
  }
  const unitChip = unit && unit !== 'auto' ? `<span class="generation-chip">${escapeHtml(unit)}</span>` : '';
  const fileLabel = file ? ` · ${escapeHtml(file.name || 'control image')}` : ' · no control image yet';
  summary.innerHTML = `${unitChip}<span class="generation-chip">${escapeHtml(preprocessor)}</span><strong>${escapeHtml(model)}</strong> · strength ${Number.isFinite(strength) ? strength.toFixed(2) : '1.00'}${fileLabel}`;
}

function updateGenerationControlnetRowSummary(row) {
  if (!row) return;
  const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
  const model = trim(row.querySelector('.generation-controlnet-name')?.value || '');
  const unit = trim(row.querySelector('.generation-controlnet-unit')?.value || 'auto') || 'auto';
  const preprocessor = trim(row.querySelector('.generation-controlnet-preprocessor')?.value || 'none') || 'none';
  const strength = Number(row.querySelector('.generation-controlnet-strength')?.value || 1.0);
  const fileInput = row.querySelector('.generation-control-image');
  const file = fileInput?.files?.[0] || null;
  toggleGenerationUnitDisabledState(row, enabled);
  updateGenerationPreviewImage(fileInput, row.querySelector('.generation-unit-preview-image'), row.querySelector('.generation-unit-preview-empty'));
  const summary = row.querySelector('.generation-unit-summary');
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This ControlNet row stays here but will not be sent.';
    return;
  }
  if (!model) {
    summary.innerHTML = 'Pick a ControlNet model for this unit.';
    return;
  }
  const unitChip = unit && unit !== 'auto' ? `<span class="generation-chip">${escapeHtml(unit)}</span>` : '';
  const fileLabel = file ? ` · ${escapeHtml(file.name || 'control image')}` : ' · no control image yet';
  summary.innerHTML = `${unitChip}<span class="generation-chip">${escapeHtml(preprocessor)}</span><strong>${escapeHtml(model)}</strong> · strength ${Number.isFinite(strength) ? strength.toFixed(2) : '1.00'}${fileLabel}`;
}

function normalizeGenerationControlnetModelName(value='') {
  return String(value || '').trim().toLowerCase();
}

function getGenerationFilteredPreprocessorOptions(unit='auto') {
  const mode = String(unit || 'auto').trim().toLowerCase() || 'auto';
  if (mode === 'auto') return generationPreprocessorOptions.slice();
  const allowedByUnit = {
    canny: ['none', 'canny', 'threshold', 'invert'],
    softedge: ['none', 'softedge', 'threshold', 'invert'],
    lineart: ['none', 'lineart', 'threshold', 'invert'],
    lineart_anime: ['none', 'lineart_anime', 'threshold', 'invert'],
    scribble: ['none', 'scribble', 'threshold', 'invert'],
    openpose: ['none', 'openpose'],
    depth: ['none', 'depth'],
  };
  const allowed = allowedByUnit[mode] || ['none'];
  return generationPreprocessorOptions.filter(option => allowed.includes(String(option?.value || '').trim().toLowerCase()));
}

function applyGenerationControlnetPreprocessorFilter(select, unit, keepValue=true) {
  if (!select) return;
  const current = keepValue ? String(select.value || '') : '';
  const filtered = getGenerationFilteredPreprocessorOptions(unit);
  setSelectOptionsForElement(select, filtered, 'Select preprocessor', false, true);
  const values = filtered.map(item => generationSelectItemValue(item));
  if (current && values.includes(current)) select.value = current;
  else select.value = values.includes('none') ? 'none' : (values[0] || '');
}

function getGenerationFilteredControlnetModels(unit='auto', preprocessor='none') {
  const allModels = Array.isArray(generationCatalogState.controlnet) ? generationCatalogState.controlnet.slice() : [];
  const selectedUnit = String(unit || 'auto').trim().toLowerCase() || 'auto';
  const selectedPreprocessor = String(preprocessor || 'none').trim().toLowerCase() || 'none';
  if (!allModels.length) return allModels;
  const keywordsByMode = {
    canny: ['canny', 'edge'],
    softedge: ['softedge', 'soft_edge', 'hed', 'pidi', 'edge'],
    lineart: ['lineart', 'line-art', 'anyline'],
    lineart_anime: ['lineart_anime', 'lineart anime', 'anime', 'manga', 'anyline'],
    scribble: ['scribble', 'sketch'],
    openpose: ['openpose', 'dwpose', 'pose'],
    depth: ['depth', 'depth_anything', 'zoe', 'midas', 'leres'],
    threshold: ['canny', 'edge', 'lineart', 'scribble', 'softedge', 'hed', 'pidi'],
    invert: ['canny', 'edge', 'lineart', 'scribble', 'softedge', 'hed', 'pidi'],
  };
  const universal = ['union', 'promax', 'mistoline', 'anyline'];
  const mode = selectedUnit !== 'auto' ? selectedUnit : selectedPreprocessor;
  if (!mode || mode === 'none') return allModels;
  const keywords = keywordsByMode[mode] || keywordsByMode[selectedPreprocessor] || [];
  const filtered = allModels.filter(model => {
    const name = normalizeGenerationControlnetModelName(model);
    return keywords.some(keyword => name.includes(keyword)) || universal.some(keyword => name.includes(keyword));
  });
  return filtered.length ? filtered : allModels;
}

function applyGenerationControlnetModelFilter(select, unit, preprocessor, keepValue=true) {
  if (!select) return;
  const current = keepValue ? String(select.value || '') : '';
  const filtered = getGenerationFilteredControlnetModels(unit, preprocessor);
  setSelectOptionsForElement(select, filtered, 'None', false);
  if (current && filtered.includes(current)) select.value = current;
  else if (current && !filtered.includes(current)) select.value = '';
}

function refreshPrimaryGenerationControlnetPreprocessorFilter() {
  applyGenerationControlnetPreprocessorFilter($('generation-controlnet-preprocessor'), $('generation-controlnet-unit')?.value || 'auto');
}

function refreshPrimaryGenerationControlnetModelFilter() {
  applyGenerationControlnetModelFilter($('generation-controlnet-name'), $('generation-controlnet-unit')?.value || 'auto', $('generation-controlnet-preprocessor')?.value || 'none');
}

function refreshGenerationControlnetPreprocessorFilterForRow(row) {
  if (!row) return;
  applyGenerationControlnetPreprocessorFilter(row.querySelector('.generation-controlnet-preprocessor'), row.querySelector('.generation-controlnet-unit')?.value || 'auto');
}

function refreshGenerationControlnetModelFilterForRow(row) {
  if (!row) return;
  applyGenerationControlnetModelFilter(row.querySelector('.generation-controlnet-name'), row.querySelector('.generation-controlnet-unit')?.value || 'auto', row.querySelector('.generation-controlnet-preprocessor')?.value || 'none');
}

function updatePrimaryGenerationIpAdapterSummary() {
  const enabled = isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled'));
  const mode = trim($('generation-ipadapter-mode')?.value || 'standard') || 'standard';
  const model = trim($('generation-ipadapter-name')?.value || '');
  const clipVision = trim($('generation-ipadapter-clip-vision')?.value || '');
  const weight = Number($('generation-ipadapter-weight')?.value || 1.0);
  const weightFaceId = Number($('generation-ipadapter-weight-faceidv2')?.value || 1.0);
  const weightType = trim($('generation-ipadapter-weight-type')?.value || 'linear') || 'linear';
  const facePreset = trim($('generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2') || 'FACEID PLUS V2';
  const faceProvider = trim($('generation-ipadapter-faceid-provider')?.value || 'CUDA') || 'CUDA';
  const fileInput = $('generation-ipadapter-image');
  const file = fileInput?.files?.[0] || null;
  const refCount = getGenerationIpAdapterRefCount(fileInput);
  const summary = $('generation-ipadapter-primary-summary');
  const ipadapterReady = generationCatalogState?.features?.ipadapter_ready !== false;
  const ipadapterFaceIdReady = generationCatalogState?.features?.ipadapter_faceid_ready !== false;
  toggleGenerationUnitDisabledState(document.querySelector('.generation-unit-card-ipadapter[data-primary="true"]'), enabled);
  updateGenerationPreviewImage(fileInput, $('generation-ipadapter-primary-preview'), $('generation-ipadapter-primary-preview-empty'));
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This primary IP-Adapter unit will be skipped.';
    return;
  }
  if (mode === 'faceid') {
    if (!ipadapterFaceIdReady) {
      summary.innerHTML = '<strong>Missing FaceID backend support.</strong> Install the FaceID IP-Adapter nodes, insightface, matching FaceID models/LoRA, and a CLIP Vision model.';
      return;
    }
    if (!clipVision) {
      summary.innerHTML = 'Primary FaceID unit is waiting for a CLIP Vision model.';
      return;
    }
    const fileLabel = refCount ? ` · ${escapeHtml(formatGenerationIpAdapterRefLabel(fileInput))}` : ' · no reference image yet';
    const clipLabel = clipVision ? `<span class="generation-chip">${escapeHtml(clipVision)}</span>` : '<span class="generation-chip">clip vision missing</span>';
    summary.innerHTML = `${clipLabel}<span class="generation-chip">${escapeHtml(faceProvider)}</span><span class="generation-chip">${escapeHtml(weightType)}</span><strong>${escapeHtml(facePreset)}</strong> · weight ${Number.isFinite(weight) ? weight.toFixed(2) : '1.00'} · face v2 ${Number.isFinite(weightFaceId) ? weightFaceId.toFixed(2) : '1.00'}${fileLabel}`;
    return;
  }
  if (!ipadapterReady) {
    summary.innerHTML = '<strong>Missing backend support.</strong> Install the IP-Adapter custom nodes plus a CLIP Vision model, then restart ComfyUI.';
    return;
  }
  if (!model) {
    summary.innerHTML = 'Primary IP-Adapter unit is idle.';
    return;
  }
  const fileLabel = refCount ? ` · ${escapeHtml(formatGenerationIpAdapterRefLabel(fileInput))}` : ' · no reference image yet';
  const clipLabel = clipVision ? `<span class="generation-chip">${escapeHtml(clipVision)}</span>` : '<span class="generation-chip">clip vision missing</span>';
  summary.innerHTML = `${clipLabel}<span class="generation-chip">${escapeHtml(weightType)}</span><strong>${escapeHtml(model)}</strong> · weight ${Number.isFinite(weight) ? weight.toFixed(2) : '1.00'}${fileLabel}`;
}

function updateGenerationIpAdapterRowSummary(row) {
  if (!row) return;
  const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
  const mode = trim(row.querySelector('.generation-ipadapter-mode')?.value || 'standard') || 'standard';
  const model = trim(row.querySelector('.generation-ipadapter-name')?.value || '');
  const clipVision = trim(row.querySelector('.generation-ipadapter-clip-vision')?.value || '');
  const weight = Number(row.querySelector('.generation-ipadapter-weight')?.value || 1.0);
  const weightFaceId = Number(row.querySelector('.generation-ipadapter-weight-faceidv2')?.value || 1.0);
  const weightType = trim(row.querySelector('.generation-ipadapter-weight-type')?.value || 'linear') || 'linear';
  const facePreset = trim(row.querySelector('.generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2') || 'FACEID PLUS V2';
  const faceProvider = trim(row.querySelector('.generation-ipadapter-faceid-provider')?.value || 'CUDA') || 'CUDA';
  const fileInput = row.querySelector('.generation-ipadapter-image');
  const file = fileInput?.files?.[0] || null;
  const refCount = getGenerationIpAdapterRefCount(fileInput);
  const ipadapterReady = generationCatalogState?.features?.ipadapter_ready !== false;
  const ipadapterFaceIdReady = generationCatalogState?.features?.ipadapter_faceid_ready !== false;
  toggleGenerationUnitDisabledState(row, enabled);
  updateGenerationPreviewImage(fileInput, row.querySelector('.generation-unit-preview-image'), row.querySelector('.generation-unit-preview-empty'));
  const summary = row.querySelector('.generation-unit-summary');
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This IP-Adapter row stays here but will not be sent.';
    return;
  }
  if (mode === 'faceid') {
    if (!ipadapterFaceIdReady) {
      summary.innerHTML = '<strong>Missing FaceID backend support.</strong> Install the FaceID IP-Adapter nodes, insightface, matching FaceID models/LoRA, and a CLIP Vision model.';
      return;
    }
    if (!clipVision) {
      summary.innerHTML = 'Pick a CLIP Vision model for this FaceID unit.';
      return;
    }
    const fileLabel = refCount ? ` · ${escapeHtml(formatGenerationIpAdapterRefLabel(fileInput))}` : ' · no reference image yet';
    const clipLabel = clipVision ? `<span class="generation-chip">${escapeHtml(clipVision)}</span>` : '<span class="generation-chip">clip vision missing</span>';
    summary.innerHTML = `${clipLabel}<span class="generation-chip">${escapeHtml(faceProvider)}</span><span class="generation-chip">${escapeHtml(weightType)}</span><strong>${escapeHtml(facePreset)}</strong> · weight ${Number.isFinite(weight) ? weight.toFixed(2) : '1.00'} · face v2 ${Number.isFinite(weightFaceId) ? weightFaceId.toFixed(2) : '1.00'}${fileLabel}`;
    return;
  }
  if (!ipadapterReady) {
    summary.innerHTML = '<strong>Missing backend support.</strong> Install the IP-Adapter custom nodes plus a CLIP Vision model, then restart ComfyUI.';
    return;
  }
  if (!model) {
    summary.innerHTML = 'Pick an IP-Adapter model for this unit.';
    return;
  }
  const fileLabel = refCount ? ` · ${escapeHtml(formatGenerationIpAdapterRefLabel(fileInput))}` : ' · no reference image yet';
  const clipLabel = clipVision ? `<span class="generation-chip">${escapeHtml(clipVision)}</span>` : '<span class="generation-chip">clip vision missing</span>';
  summary.innerHTML = `${clipLabel}<span class="generation-chip">${escapeHtml(weightType)}</span><strong>${escapeHtml(model)}</strong> · weight ${Number.isFinite(weight) ? weight.toFixed(2) : '1.00'}${fileLabel}`;
}

function refreshGenerationIpAdapterPrimaryOptions() {
  bindGenerationIpAdapterExplainers(document, $('generation-ipadapter-option-explainer'));
  setSelectOptionsForElement($('generation-ipadapter-mode'), generationIpAdapterModeOptions, 'Mode', false, true);
  setSelectOptionsForElement($('generation-ipadapter-name'), generationCatalogState.ipadapter || [], 'None');
  setSelectOptionsForElement($('generation-ipadapter-clip-vision'), generationCatalogState.clip_vision || [], 'None');
  setSelectOptionsForElement($('generation-ipadapter-faceid-preset'), generationIpAdapterFaceIdPresetOptions, 'FaceID preset', false, true);
  setSelectOptionsForElement($('generation-ipadapter-faceid-provider'), generationIpAdapterFaceIdProviderOptions, 'Provider', false, true);
  setSelectOptionsForElement($('generation-ipadapter-weight-type'), generationIpAdapterWeightTypeOptions, 'Weight type', false, true);
  setSelectOptionsForElement($('generation-ipadapter-combine-embeds'), generationIpAdapterCombineOptions, 'Combine embeds', false, true);
  setSelectOptionsForElement($('generation-ipadapter-embeds-scaling'), generationIpAdapterEmbedScalingOptions, 'Embeds scaling', false, true);
}

function refreshGenerationIpAdapterRowOptions(row) {
  if (!row) return;
  bindGenerationIpAdapterExplainers(row, row.querySelector('.generation-option-explainer'));
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-mode'), generationIpAdapterModeOptions, 'Mode', false, true);
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-name'), generationCatalogState.ipadapter || [], 'None');
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-clip-vision'), generationCatalogState.clip_vision || [], 'None');
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-faceid-preset'), generationIpAdapterFaceIdPresetOptions, 'FaceID preset', false, true);
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-faceid-provider'), generationIpAdapterFaceIdProviderOptions, 'Provider', false, true);
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-weight-type'), generationIpAdapterWeightTypeOptions, 'Weight type', false, true);
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-combine-embeds'), generationIpAdapterCombineOptions, 'Combine embeds', false, true);
  setSelectOptionsForElement(row.querySelector('.generation-ipadapter-embeds-scaling'), generationIpAdapterEmbedScalingOptions, 'Embeds scaling', false, true);
}

let generationDetailerModelCatalog = { bbox_models:[], segm_models:[], sam_models:[], comfy_root:'', bbox_dir:'', segm_dir:'', sam_dir:'', custom_detector_root:'', custom_sam_root:'', sam_presets:[] };
let generationDetailerRowCounter = 0;
let generationDetailerTrackCounter = 0;

function currentGenerationDetailerModelPool() {
  const detectorType = $('generation-detailer-detector-type')?.value || 'bbox';
  const mode = $('generation-detailer-mode')?.value || 'face';
  const pool = detectorType === 'segm' ? [...(generationDetailerModelCatalog.segm_models || [])] : [...(generationDetailerModelCatalog.bbox_models || [])];
  if (mode === 'custom') return pool;
  const keywords = mode === 'hands' ? ['hand'] : mode === 'person' ? ['person', 'people', 'body'] : ['face'];
  const filtered = pool.filter(name => keywords.some(keyword => String(name || '').toLowerCase().includes(keyword)));
  return filtered.length ? filtered : pool;
}

function populateGenerationDetailerModelSelect(keepValue=true) {
  const select = $('generation-detailer-model');
  if (!select) return;
  const current = keepValue ? trim(select.value || '') : '';
  const pool = currentGenerationDetailerModelPool();
  select.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = pool.length ? 'Select detector model…' : 'No detector models found';
  select.appendChild(placeholder);
  pool.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    if (current && current === name) opt.selected = true;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
}

function populateGenerationDetailerSamSelect(keepValue=true) {
  const select = $('generation-detailer-sam-model');
  if (!select) return;
  const current = keepValue ? trim(select.value || '') : '';
  select.innerHTML = '';
  const noneOpt = document.createElement('option');
  noneOpt.value = '';
  noneOpt.textContent = 'None';
  select.appendChild(noneOpt);
  (generationDetailerModelCatalog.sam_models || []).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    if (current && current === name) opt.selected = true;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
}

function updateGenerationDetailerMeta() {
  const meta = $('generation-detailer-model-meta');
  if (!meta) return;
  const bboxCount = (generationDetailerModelCatalog.bbox_models || []).length;
  const segmCount = (generationDetailerModelCatalog.segm_models || []).length;
  const samCount = (generationDetailerModelCatalog.sam_models || []).length;
  meta.textContent = `${bboxCount} bbox · ${segmCount} segm · ${samCount} SAM models${generationDetailerModelCatalog.comfy_root ? ` · ${generationDetailerModelCatalog.comfy_root}` : ''}`;
}

async function loadGenerationDetailerModels(keepValue=true) {
  try {
    const qs = new URLSearchParams();
    const detectorRoot = trim($('generation-detailer-custom-detector-root')?.value || '');
    const samRoot = trim($('generation-detailer-custom-sam-root')?.value || '');
    if (detectorRoot) qs.set('detector_root', detectorRoot);
    if (samRoot) qs.set('sam_root', samRoot);
    const data = await safeFetchJson(`/api/generation/detailer-models?${qs.toString()}&_=${Date.now()}`, { cache:'no-store' });
    generationDetailerModelCatalog = {
      bbox_models: Array.isArray(data?.bbox_models) ? data.bbox_models : [],
      segm_models: Array.isArray(data?.segm_models) ? data.segm_models : [],
      sam_models: Array.isArray(data?.sam_models) ? data.sam_models : [],
      sam_presets: Array.isArray(data?.sam_presets) ? data.sam_presets : [],
      comfy_root: data?.comfy_root || '',
      bbox_dir: data?.bbox_dir || '',
      segm_dir: data?.segm_dir || '',
      sam_dir: data?.sam_dir || '',
      custom_detector_root: data?.custom_detector_root || detectorRoot,
      custom_sam_root: data?.custom_sam_root || samRoot,
    };
    if ($('generation-detailer-custom-detector-root') && generationDetailerModelCatalog.custom_detector_root) $('generation-detailer-custom-detector-root').value = generationDetailerModelCatalog.custom_detector_root;
    if ($('generation-detailer-custom-sam-root') && generationDetailerModelCatalog.custom_sam_root) $('generation-detailer-custom-sam-root').value = generationDetailerModelCatalog.custom_sam_root;
    populateGenerationDetailerModelSelect(keepValue);
    populateGenerationDetailerSamSelect(keepValue);
    document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row').forEach(row => populateGenerationDetailerRowModelSelect(row, true));
    updateGenerationDetailerMeta();
    const found = generationDetailerModelCatalog.bbox_models.length || generationDetailerModelCatalog.segm_models.length || generationDetailerModelCatalog.sam_models.length;
    window.dispatchEvent(new CustomEvent('neo:generation-detailer-models-refreshed', { detail: { detailer: generationDetailerModelCatalog, found: !!found } }));
    setStatus('generation-detailer-status', found ? 'Detailer model scan complete.' : 'No detailer models found in the scanned folders yet.', found ? 'success' : 'warn');
  } catch (e) {
    setStatus('generation-detailer-status', e.message || 'Could not scan detailer models.', 'error');
  }
}

function populateGenerationDetailerRowModelSelect(row, keepValue=true) {
  if (!row) return;
  const select = row.querySelector('.generation-detailer-model');
  if (!select) return;
  const current = keepValue ? trim(select.value || '') : '';
  const detectorType = row.querySelector('.generation-detailer-detector-type')?.value || 'bbox';
  const mode = row.querySelector('.generation-detailer-mode')?.value || 'face';
  const pool = detectorType === 'segm' ? [...(generationDetailerModelCatalog.segm_models || [])] : [...(generationDetailerModelCatalog.bbox_models || [])];
  const keywords = mode === 'hands' ? ['hand'] : mode === 'person' ? ['person', 'people', 'body'] : mode === 'custom' ? [] : ['face'];
  const filtered = keywords.length ? pool.filter(name => keywords.some(keyword => String(name || '').toLowerCase().includes(keyword))) : pool;
  const finalPool = filtered.length ? filtered : pool;
  select.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = finalPool.length ? 'Select detector model…' : 'No detector models found';
  select.appendChild(placeholder);
  finalPool.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    if (current && current === name) opt.selected = true;
    select.appendChild(opt);
  });
  if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
}


function generationDetailerScopeUsesManualBoxes(scopeType='primary', row=null) {
  if (scopeType === 'row' && row instanceof HTMLElement) return (row.querySelector('.generation-detailer-target-mode')?.value || 'auto_detect') === 'manual_boxes';
  return ($('generation-detailer-target-mode')?.value || 'auto_detect') === 'manual_boxes';
}

function syncGenerationPrimaryDetailerManualUi() {
  const usesManual = generationDetailerScopeUsesManualBoxes('primary');
  const manualWrap = $('generation-detailer-primary-manual-boxes-wrap');
  const pickerRow = $('generation-detailer-primary-picker-row');
  const editor = $('generation-detailer-box-editor');
  if (manualWrap) manualWrap.style.display = usesManual ? '' : 'none';
  if (pickerRow) pickerRow.style.display = usesManual ? '' : 'none';
  if (!usesManual && editor && generationDetailerBoxEditorState.scopeType === 'primary') {
    editor.style.display = 'none';
  }
}

function syncGenerationDetailerRowManualUi(row) {
  if (!(row instanceof HTMLElement)) return;
  const usesManual = generationDetailerScopeUsesManualBoxes('row', row);
  const manualWrap = row.querySelector('.generation-detailer-manual-boxes')?.closest('div[style*="grid-column:1 / -1"]');
  const pickerBtn = row.querySelector('.generation-detailer-row-picker');
  if (manualWrap) manualWrap.style.display = usesManual ? '' : 'none';
  if (pickerBtn) pickerBtn.style.display = usesManual ? '' : 'none';
  if (!usesManual && generationDetailerBoxEditorState.scopeType === 'row' && generationDetailerBoxEditorState.scopeRowUid === row.dataset.uid) {
    $('generation-detailer-box-editor')?.style && ($('generation-detailer-box-editor').style.display = 'none');
    setGenerationDetailerEditorScope('primary');
  }
}

function generationDetailerReferenceLockLabel(value) {
  const map = {
    none: 'off',
    soft_identity: 'soft identity',
    strong_identity: 'strong identity',
    face_only: 'face only',
    style_only: 'style only',
    controlnet: 'controlnet',
    ipadapter: 'legacy ipadapter',
    both: 'legacy both'
  };
  return map[String(value || 'none')] || String(value || 'none').replace(/_/g, ' ');
}

function updateGenerationDetailerReferenceLockHint() {
  const select = $('generation-detailer-reference-lock');
  const hint = $('generation-detailer-reference-lock-hint');
  if (!select || !hint) return;
  const value = select.value || 'none';
  const hints = {
    none: 'Off: no extra reference lock for the detail pass.',
    soft_identity: 'Soft identity: reuse an available FaceID/IP-Adapter reference gently, best for preserving character feel without overfitting.',
    strong_identity: 'Strong identity: prefers a FaceID reference and applies a stricter identity note. Best when likeness matters.',
    face_only: 'Face only: identity-focused reference mode for face repair passes. Requires an IP-Adapter FaceID/reference unit to be configured.',
    style_only: 'Style only: reuse a standard IP-Adapter/image reference for lighting, color, and texture while avoiding strong identity pressure.',
    controlnet: 'Follow ControlNet: keep the detail pass aligned with configured ControlNet guidance when available.',
    ipadapter: 'Legacy IP-Adapter / FaceID: old compatibility mode. Soft/Strong/Face/Style modes are clearer for new workflows.',
    both: 'Legacy both: old compatibility mode that requests ControlNet + IP-Adapter reuse when configured.'
  };
  hint.textContent = hints[value] || hints.none;
}

function updateGenerationDetailerRowSummary(row) {
  if (!row) return;
  const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
  const mode = row.querySelector('.generation-detailer-mode')?.value || 'face';
  const detectorType = row.querySelector('.generation-detailer-detector-type')?.value || 'bbox';
  const model = trim(row.querySelector('.generation-detailer-model')?.value || '');
  const orderMode = row.querySelector('.generation-detailer-order')?.value || 'auto';
  const count = Math.max(0, Number(row.querySelector('.generation-detailer-count')?.value || 1));
  const referenceLock = row.querySelector('.generation-detailer-reference-lock')?.value || 'none';
  const targetMode = row.querySelector('.generation-detailer-target-mode')?.value || 'auto_detect';
  const manualCount = trim(row.querySelector('.generation-detailer-manual-boxes')?.value || '').split(/\n+/).map(line => line.trim()).filter(Boolean).length;
  const summary = row.querySelector('.generation-unit-summary');
  toggleGenerationUnitDisabledState(row, enabled);
  syncGenerationDetailerRowManualUi(row);
  if (!summary) { renderGenerationFinishFoundation(); return; }
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This detailer pass will be skipped.';
    renderGenerationFinishFoundation();
    return;
  }
  if (targetMode === 'manual_boxes') {
    const refLabel = referenceLock === 'none' ? '' : ` · ref ${escapeHtml(generationDetailerReferenceLockLabel(referenceLock))}`;
    summary.innerHTML = `<span class="generation-chip">${escapeHtml(mode)}</span><strong>manual boxes</strong> · ${manualCount || 0} region(s) · detail-only repair${refLabel}`;
    renderGenerationFinishFoundation();
    return;
  }
  if (!model) {
    summary.innerHTML = 'Pick a detector model for this detailer pass.';
    renderGenerationFinishFoundation();
    return;
  }
  const orderLabel = orderMode === 'auto' ? 'auto order' : orderMode.replace(/_/g, ' ');
  const refLabel = referenceLock === 'none' ? '' : ` · ref ${escapeHtml(generationDetailerReferenceLockLabel(referenceLock))}`;
  summary.innerHTML = `<span class="generation-chip">${escapeHtml(mode)}</span><strong>${escapeHtml(model)}</strong> · ${escapeHtml(detectorType)} · ${escapeHtml(orderLabel)} · count ${Number.isFinite(count) ? count : 1}${refLabel}`;
  renderGenerationFinishFoundation();
}

function createGenerationDetailerRow(values={}) {
  generationDetailerRowCounter += 1;
  const row = document.createElement('div');
  row.className = 'grid grid-5 generation-dynamic-row generation-detailer-row generation-unit-card';
  row.dataset.uid = values.uid || `detailer_${generationDetailerRowCounter}`;
  row.innerHTML = `
    <div class="generation-unit-topbar" style="grid-column:1 / -1;">
      <div class="generation-unit-heading">
        <span class="generation-unit-index">00</span>
        <div>
          <div class="generation-unit-title">Detailer pass</div>
          <div class="accordion-hint">Pass-specific target selection. Shared repair defaults live above this stack.</div>
        </div>
      </div>
      <div class="generation-unit-actions">
        <label class="generation-toggle-pill"><input class="generation-unit-enabled" type="checkbox" ${values.enabled === false ? '' : 'checked'} /> Enabled</label>
        <button class="btn btn-small generation-detailer-row-picker" type="button" title="Open the visual picker for this detailer pass">🧩 Picker</button>
        <button class="btn btn-small generation-row-move-up" type="button" title="Move this detailer pass up">↑</button>
        <button class="btn btn-small generation-row-move-down" type="button" title="Move this detailer pass down">↓</button>
        <button class="btn btn-small generation-remove-row" type="button" title="Remove this detailer pass">Remove</button>
      </div>
    </div>
    <div>
      <label>Target</label>
      <select class="generation-detailer-mode">
        <option value="face">Face</option>
        <option value="hands">Hands</option>
        <option value="person">Person</option>
        <option value="custom">Custom</option>
      </select>
    </div>
    <div>
      <label>Detector type</label>
      <select class="generation-detailer-detector-type">
        <option value="bbox">BBox</option>
        <option value="segm">Segmentation</option>
      </select>
    </div>
    <div>
      <label>Detector model</label>
      <select class="generation-detailer-model"><option value="">Load detector models…</option></select>
    </div>
    <div>
      <label>Target order</label>
      <select class="generation-detailer-order">
        <option value="auto">Auto</option>
        <option value="left_to_right">Left → Right</option>
        <option value="right_to_left">Right → Left</option>
        <option value="top_to_bottom">Top → Bottom</option>
        <option value="bottom_to_top">Bottom → Top</option>
        <option value="largest_first">Largest first</option>
        <option value="smallest_first">Smallest first</option>
        <option value="center_first">Center first</option>
      </select>
    </div>
    <div>
      <label>Start at</label>
      <input class="generation-detailer-start-index" type="number" min="1" step="1" value="${Number(values.start_index ?? 1)}" />
    </div>
    <div>
      <label>Count</label>
      <input class="generation-detailer-count" type="number" min="0" step="1" value="${Number(values.count ?? 1)}" />
    </div>
    <div>
      <label>Min area</label>
      <input class="generation-detailer-min-area" type="number" min="0" step="1" value="${Number(values.min_area ?? 0)}" />
    </div>
    <div>
      <label>Max area</label>
      <input class="generation-detailer-max-area" type="number" min="0" step="1" value="${Number(values.max_area ?? 0)}" />
    </div>
    <div>
      <label>Reference lock</label>
      <select class="generation-detailer-reference-lock">
        <option value="none">Off</option>
        <option value="soft_identity">Soft identity</option>
        <option value="strong_identity">Strong identity</option>
        <option value="face_only">Face only</option>
        <option value="style_only">Style only</option>
        <option value="controlnet">Follow ControlNet</option>
        <option value="ipadapter">Legacy IP-Adapter / FaceID</option>
        <option value="both">Legacy both</option>
      </select>
    </div>
    <div>
      <label>Target mode</label>
      <select class="generation-detailer-target-mode">
        <option value="auto_detect">Auto detect</option>
        <option value="manual_boxes">Manual boxes</option>
      </select>
    </div>
    <div class="mini-note" style="display:flex; align-items:end;">Use min/max area to skip tiny blurred background detections.</div>
    <div style="grid-column:1 / -1;">
      <label>Manual boxes</label>
      <textarea class="generation-detailer-manual-boxes" rows="3" placeholder="One box per line. Examples: xywh:120,80,300,300 or xyxy:120,80,420,380 or 12%,10%,28%,28%">${escapeHtml(values.manual_boxes || '')}</textarea>
    </div>
    <div style="grid-column:1 / -1;">
      <label>Prompt override</label>
      <input class="generation-detailer-positive" type="text" value="${escapeHtml(values.positive || '')}" placeholder="Leave blank to reuse the shared/main positive prompt." />
    </div>
    <div style="grid-column:1 / -1;">
      <label>Negative override</label>
      <input class="generation-detailer-negative" type="text" value="${escapeHtml(values.negative || '')}" placeholder="Leave blank to reuse the shared/main negative prompt." />
    </div>
    <div class="generation-unit-summary" style="grid-column:1 / -1;">Pick a detector model for this detailer pass.</div>`;
  row.querySelector('.generation-remove-row')?.addEventListener('click', () => { if (generationDetailerBoxEditorState.scopeType === 'row' && generationDetailerBoxEditorState.scopeRowUid === row.dataset.uid) setGenerationDetailerEditorScope('primary'); row.remove(); updateGenerationUnitIndices(); scheduleGenerationDraftSave(); renderGenerationFinishFoundation(); });
  row.querySelector('.generation-detailer-row-picker')?.addEventListener('click', () => { if (!generationDetailerScopeUsesManualBoxes('row', row)) return; setGenerationDetailerEditorScope('row', row); openGenerationDetailerEditor().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not open the pass picker.', 'error')); });
  row.querySelector('.generation-row-move-up')?.addEventListener('click', () => moveGenerationUnitRow(row, -1));
  row.querySelector('.generation-row-move-down')?.addEventListener('click', () => moveGenerationUnitRow(row, 1));
  if (values.mode) row.querySelector('.generation-detailer-mode').value = values.mode;
  if (values.detector_type) row.querySelector('.generation-detailer-detector-type').value = values.detector_type;
  populateGenerationDetailerRowModelSelect(row, false);
  const detailerModelValue = values.detector_model || values.model || '';
  if (detailerModelValue) row.querySelector('.generation-detailer-model').value = detailerModelValue;
  if (values.order_mode || values.order) row.querySelector('.generation-detailer-order').value = values.order_mode || values.order;
  if (values.reference_lock) row.querySelector('.generation-detailer-reference-lock').value = values.reference_lock;
  if (values.target_mode) row.querySelector('.generation-detailer-target-mode').value = values.target_mode;
  if (typeof values.manual_boxes === 'string') row.querySelector('.generation-detailer-manual-boxes').value = values.manual_boxes;
  row.querySelectorAll('input, select, textarea').forEach(el => {
    const eventName = el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input';
    el.addEventListener(eventName, () => {
      if (el.classList?.contains('generation-detailer-mode') || el.classList?.contains('generation-detailer-detector-type')) populateGenerationDetailerRowModelSelect(row, true);
      updateGenerationDetailerRowSummary(row);
      scheduleGenerationDraftSave();
    });
    if (eventName !== 'change') el.addEventListener('change', () => { updateGenerationDetailerRowSummary(row); scheduleGenerationDraftSave(); if (el.classList?.contains('generation-detailer-manual-boxes') && generationDetailerBoxEditorState.scopeType === 'row' && generationDetailerBoxEditorState.scopeRowUid === row.dataset.uid && $('generation-detailer-box-editor')?.style.display !== 'none') hydrateGenerationDetailerBoxesFromTextarea(); });
  });
  updateGenerationDetailerRowSummary(row);
  return row;
}

function addGenerationDetailerRow(values={}) {
  $('generation-detailer-extra-list')?.appendChild(createGenerationDetailerRow(values));
  updateGenerationUnitIndices();
  scheduleGenerationDraftSave();
}

let generationWildcardCatalog = [];
const generationWildcardValueCache = new Map();
let generationWildcardPreviewResults = [];

