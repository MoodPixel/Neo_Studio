function populateGenerationSelect(id, items, placeholder, keepValue=true) {
  const el = $(id);
  if (!el) return;
  const current = keepValue ? String(el.value || '') : '';
  const rows = Array.isArray(items) ? items : [];
  el.innerHTML = '';
  const placeholderOpt = document.createElement('option');
  placeholderOpt.value = '';
  placeholderOpt.textContent = placeholder;
  el.appendChild(placeholderOpt);
  rows.forEach(item => {
    const opt = document.createElement('option');
    opt.value = generationSelectItemValue(item);
    opt.textContent = generationSelectItemLabel(item);
    if (current && current === opt.value) opt.selected = true;
    el.appendChild(opt);
  });
  if (!current && rows.length && ['generation-checkpoint', 'generation-sampler', 'generation-scheduler'].includes(id)) {
    el.value = generationSelectItemValue(rows[0]);
  }
}

function firstFilledOptionValue(id) {
  const el = $(id);
  if (!el) return '';
  const match = Array.from(el.options || []).find(opt => String(opt.value || '').trim());
  return match ? String(match.value || '').trim() : '';
}

function ensureGenerationCheckpointSelected() {
  const el = $('generation-checkpoint');
  if (!el) return '';
  let value = trim(el.value || '');
  if (!value) {
    const fallback = firstFilledOptionValue('generation-checkpoint');
    if (fallback) {
      el.value = fallback;
      value = fallback;
    }
  }
  return value;
}

function announceGenerationStatus(text, level='') {
  setStatus('generation-status', text, level);
  const el = $('generation-status');
  if (el) el.scrollIntoView({ behavior:'smooth', block:'nearest' });
}


function makeGenerationClientId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `neo_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function setGenerationProgress(percent, label='', etaText='ETA —') {
  const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
  if ($('generation-progress-bar')) $('generation-progress-bar').style.width = `${clamped}%`;
  if ($('generation-progress-label')) $('generation-progress-label').textContent = label || `${Math.round(clamped)}%`;
  if ($('generation-progress-eta')) $('generation-progress-eta').textContent = etaText || 'ETA —';
  if ($('generation-progress-percent')) $('generation-progress-percent').textContent = `${Math.round(clamped)}%`;
  if ($('generation-progress-detail')) $('generation-progress-detail').textContent = label || (clamped > 0 ? 'Working…' : 'No active job');
  const elapsedText = generationProgressStartedAt > 0 && clamped > 0
    ? `Elapsed ${formatElapsed(Math.max(0, Math.round((Date.now() - generationProgressStartedAt) / 1000)))}`
    : 'Elapsed —';
  if ($('generation-progress-elapsed')) $('generation-progress-elapsed').textContent = elapsedText;
}

function resetGenerationProgress(label='Idle') {
  generationProgressStartedAt = 0;
  generationLastProgressPercent = 0;
  if ($('generation-progress-job-id')) $('generation-progress-job-id').textContent = 'Job —';
  setGenerationProgress(0, label, 'ETA —');
}

function updateGenerationPreviewActionState() {
  // Phase 10.3 preview-action hotfix: recover from selected/latest/visible output
  // before disabling finish buttons. Scene Director patches may clear the action
  // target while a job is running, but the rendered final output is still valid.
  let target = generationPreviewActionTarget && generationPreviewActionTarget.view_url ? generationPreviewActionTarget : null;
  if (!target && typeof getGenerationActiveOutputSnapshot === 'function') {
    const active = getGenerationActiveOutputSnapshot();
    if (active?.view_url) target = active;
  }
  if (!target && generationSelectedOutputSnapshot?.view_url) target = generationSelectedOutputSnapshot;
  if (!target && Array.isArray(generationLatestJobSnapshot?.outputs)) {
    target = generationLatestJobSnapshot.outputs.find(item => item && item.view_url) || null;
  }
  if (!target) {
    const liveSrc = String($('generation-live-preview')?.getAttribute('src') || '').trim();
    if (liveSrc) target = { view_url: liveSrc, filename: 'generated_image.png', source_kind: 'visible_preview' };
  }
  if (target?.view_url && !generationPreviewActionTarget?.view_url) {
    generationPreviewActionTarget = { ...target };
  }
  const hasTarget = !!(target && target.view_url);
  const wrap = $('generation-preview-actions');
  if (wrap) wrap.classList.toggle('is-visible', hasTarget);
  ['btn-generation-preview-hires', 'btn-generation-preview-detailer', 'btn-generation-preview-img2img', 'btn-generation-preview-inpaint', 'btn-generation-preview-outpaint'].forEach(id => {
    const el = $(id);
    if (!el) return;
    if (hasTarget) el.removeAttribute('disabled');
    else el.setAttribute('disabled', 'disabled');
  });
}

function setGenerationPreviewActionTarget(target) {
  generationPreviewActionTarget = target && target.view_url ? { ...target } : null;
  updateGenerationPreviewActionState();
}

function getGenerationPreviewLifecycleState() {
  if (!window.__neoPreviewLifecycleState) {
    window.__neoPreviewLifecycleState = {
      active: false,
      finalizing: false,
      failed: false,
      socket_open: false,
      binary_frames: 0,
      preview_frames: 0,
      dropped_binary_frames: 0,
      last_event_type: '',
      last_error: '',
      client_id: '',
      prompt_id: ''
    };
  }
  return window.__neoPreviewLifecycleState;
}

function beginGenerationPreviewLifecycle(meta={}) {
  const state = getGenerationPreviewLifecycleState();
  state.active = true;
  state.finalizing = false;
  state.failed = false;
  state.client_id = String(meta?.client_id || state.client_id || generationProgressClientId || '').trim();
  state.prompt_id = String(meta?.prompt_id || state.prompt_id || generationProgressPromptId || '').trim();
}

function markGenerationPreviewFinalizing() {
  const state = getGenerationPreviewLifecycleState();
  state.active = true;
  state.finalizing = true;
}

function markGenerationPreviewTerminal(failed=false) {
  const state = getGenerationPreviewLifecycleState();
  state.active = false;
  state.finalizing = false;
  state.failed = !!failed;
  state.socket_open = false;
}

function shouldHoldGenerationPreview() {
  const state = getGenerationPreviewLifecycleState();
  return !!(state.active || state.finalizing);
}

function clearGenerationLivePreview(resetText=false, options={}) {
  const img = $('generation-live-preview');
  if (!img) return;

  if (!options.force && shouldHoldGenerationPreview()) {
    return;
  }
  if (generationLivePreviewUrl && generationLivePreviewUrl.startsWith('blob:')) {
    try { URL.revokeObjectURL(generationLivePreviewUrl); } catch (_) {}
  }
  generationLivePreviewUrl = '';
  img.removeAttribute('src');
  img.style.display = 'none';
  clearGenerationActiveOutputSnapshot?.({ syncPreviewTarget:true });
  if (resetText && $('generation-preview-state')) {
    $('generation-preview-state').textContent = 'No live preview yet for this run.';
  }
}

function showGenerationLivePreview(sourceUrl, label='Live preview updating…') {
  const img = $('generation-live-preview');
  if (!img || !sourceUrl) return;
  img.src = sourceUrl;
  img.style.display = 'block';
  generationLivePreviewUrl = sourceUrl;
  if ($('generation-preview-state')) $('generation-preview-state').textContent = label;
}

function detectGenerationPreviewImagePayload(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 4) return null;
  const bytes = new Uint8Array(buffer);
  const isPngAt = offset => bytes.length >= offset + 8
    && bytes[offset] === 0x89
    && bytes[offset + 1] === 0x50
    && bytes[offset + 2] === 0x4e
    && bytes[offset + 3] === 0x47
    && bytes[offset + 4] === 0x0d
    && bytes[offset + 5] === 0x0a
    && bytes[offset + 6] === 0x1a
    && bytes[offset + 7] === 0x0a;
  const isJpegAt = offset => bytes.length >= offset + 3
    && bytes[offset] === 0xff
    && bytes[offset + 1] === 0xd8
    && bytes[offset + 2] === 0xff;
  const isWebpAt = offset => bytes.length >= offset + 12
    && bytes[offset] === 0x52
    && bytes[offset + 1] === 0x49
    && bytes[offset + 2] === 0x46
    && bytes[offset + 3] === 0x46
    && bytes[offset + 8] === 0x57
    && bytes[offset + 9] === 0x45
    && bytes[offset + 10] === 0x42
    && bytes[offset + 11] === 0x50;

  // ComfyUI preview frames normally use an 8-byte binary header:
  // uint32 event_type + uint32 image_type + raw image bytes. Some builds/plugins
  // can forward raw image bytes or slightly different frame headers, so keep the
  // parser permissive instead of silently dropping valid preview frames.
  try {
    if (buffer.byteLength > 8) {
      const view = new DataView(buffer);
      const frameType = view.getUint32(0, false);
      const imageType = view.getUint32(4, false);
      if (frameType === 1) {
        const offset = 8;
        let mime = imageType === 2 ? 'image/png' : 'image/jpeg';
        if (isPngAt(offset)) mime = 'image/png';
        else if (isJpegAt(offset)) mime = 'image/jpeg';
        else if (isWebpAt(offset)) mime = 'image/webp';
        return { offset, mime };
      }
    }
  } catch (_) {}

  const offsets = [0, 4, 8, 12, 16];
  for (const offset of offsets) {
    if (isPngAt(offset)) return { offset, mime: 'image/png' };
    if (isJpegAt(offset)) return { offset, mime: 'image/jpeg' };
    if (isWebpAt(offset)) return { offset, mime: 'image/webp' };
  }
  return null;
}

function applyGenerationPreviewBuffer(buffer) {
  const state = getGenerationPreviewLifecycleState();
  state.binary_frames = Number(state.binary_frames || 0) + 1;
  const payload = detectGenerationPreviewImagePayload(buffer);
  if (!payload) {
    state.dropped_binary_frames = Number(state.dropped_binary_frames || 0) + 1;
    return;
  }
  state.preview_frames = Number(state.preview_frames || 0) + 1;
  const blob = new Blob([buffer.slice(payload.offset)], { type: payload.mime || 'image/jpeg' });
  const objectUrl = URL.createObjectURL(blob);
  if (generationLivePreviewUrl && generationLivePreviewUrl.startsWith('blob:')) {
    try { URL.revokeObjectURL(generationLivePreviewUrl); } catch (_) {}
  }
  showGenerationLivePreview(objectUrl, 'Live preview updating…');
}

function buildGenerationWsUrl(baseUrl, clientId) {
  const url = new URL('/api/generation/progress/ws', window.location.href);
  url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  url.search = `clientId=${encodeURIComponent(clientId)}`;
  return url.toString();
}

function closeGenerationProgressSocket() {
  if (generationProgressSocket) {
    try { generationProgressSocket.close(); } catch (_) {}
  }
  generationProgressSocket = null;
  generationProgressClientId = '';
  generationProgressPromptId = '';
}

function ensureGenerationFinalizationPoll(reason='finalizing') {
  const jobId = String(lastGenerationJobId || generationLatestJobSnapshot?.id || generationLatestJobSnapshot?.job_id || '').trim();
  if (!jobId || typeof pollGenerationJob !== 'function') return;
  if (!generationActivePollJobId || generationActivePollJobId !== jobId) {
    pollGenerationJob(jobId, { intervalMs: 1500, maxAttempts: 300 });
  }
  if (reason) setStatus('generation-status', reason === 'socket_close' ? 'Backend finished. Finalizing output registration…' : 'Finalizing output registration…');
}

function handleGenerationProgressMessage(message) {
  const type = String(message?.type || '').toLowerCase();
  const state = getGenerationPreviewLifecycleState();
  state.last_event_type = type || state.last_event_type || '';
  const rawData = (message && typeof message.data === 'object' && message.data) ? message.data : message || {};
  if (type === 'proxy_diag' || type === 'proxy_open') {
    const diag = rawData || {};
    state.proxy_diag = diag;
    state.proxy_text_frames = Number(diag.text_frames || state.proxy_text_frames || 0);
    state.proxy_binary_frames = Number(diag.binary_frames || state.proxy_binary_frames || 0);
    state.proxy_forwarded_binary_frames = Number(diag.forwarded_binary_frames || state.proxy_forwarded_binary_frames || 0);
    state.proxy_json_types = diag.json_types || state.proxy_json_types || {};
    state.ws_mode = 'proxy';
    if (diag.client_id) state.client_id = String(diag.client_id || '');
    if ($('generation-preview-state') && type === 'proxy_diag' && state.proxy_binary_frames <= 0) {
      $('generation-preview-state').textContent = `Live preview proxy connected — text ${state.proxy_text_frames || 0}, binary ${state.proxy_binary_frames || 0}`;
    }
    return;
  }
  const promptId = String(rawData?.prompt_id || message?.prompt_id || '');
  if (generationProgressPromptId && promptId && promptId !== generationProgressPromptId) return;

  if (type === 'status') {
    const remaining = Number(rawData?.exec_info?.queue_remaining ?? rawData?.status?.exec_info?.queue_remaining ?? 0);
    const currentPct = Math.max(2, generationLastProgressPercent || 0);
    const queueLabel = remaining > 0 ? `Queued… ${remaining} job(s) ahead/remaining` : 'Queued…';
    setGenerationProgress(currentPct || 2, queueLabel, remaining > 0 ? 'ETA waiting in queue…' : 'ETA calculating…');
    return;
  }
  if (type === 'execution_start') {
    beginGenerationPreviewLifecycle({ prompt_id: promptId });
    generationProgressStartedAt = Date.now();
    if (promptId) generationProgressPromptId = promptId;
    generationLastProgressPercent = 3;
    setGenerationProgress(3, 'Starting generation…', 'ETA calculating…');
    return;
  }
  if (type === 'progress') {
    const value = Number(rawData?.value ?? message?.value ?? 0);
    const max = Number(rawData?.max ?? message?.max ?? 0);
    const pct = max > 0 ? Math.min(96, (value / max) * 100) : Math.max(8, generationLastProgressPercent || 0);
    generationLastProgressPercent = pct;
    let etaText = 'ETA calculating…';
    if (generationProgressStartedAt && value > 0 && max > value) {
      const elapsedSec = Math.max(1, (Date.now() - generationProgressStartedAt) / 1000);
      const etaSec = Math.max(0, Math.round((elapsedSec / value) * (max - value)));
      etaText = `ETA ${formatElapsed(etaSec)}`;
    } else if (max > 0 && value >= max) {
      etaText = 'ETA 00:00';
    }
    setGenerationProgress(pct, `Generating… ${value}/${max || '?'}`, etaText);
    return;
  }
  if (type === 'executing') {
    if (generationProgressStartedAt <= 0) generationProgressStartedAt = Date.now();
    const node = rawData?.node ?? null;
    if (node === null || node === undefined) {
      generationLastProgressPercent = Math.max(97, generationLastProgressPercent || 0);
      setGenerationProgress(generationLastProgressPercent, 'Finalizing output…', 'ETA 00:01');
      ensureGenerationFinalizationPoll('finalizing');
    } else {
      generationLastProgressPercent = Math.max(12, generationLastProgressPercent || 0);
      setGenerationProgress(generationLastProgressPercent, `Executing node ${node}…`, 'ETA calculating…');
    }
    return;
  }
  if (type === 'executed') {
    generationLastProgressPercent = Math.max(90, generationLastProgressPercent || 0);
    setGenerationProgress(generationLastProgressPercent, 'Writing output…', 'ETA 00:01');
    return;
  }
  if (type === 'execution_success') {
    markGenerationPreviewFinalizing();
    setGenerationProgress(99, 'Finishing…', 'ETA 00:00');
    ensureGenerationFinalizationPoll('finalizing');
    return;
  }
  if (type === 'execution_error') {
    markGenerationPreviewTerminal(true);
    setGenerationProgress(100, 'Generation failed', 'ETA —');
    closeGenerationProgressSocket();
    return;
  }
  if (type === 'execution_interrupted') {
    markGenerationPreviewTerminal(true);
    setGenerationProgress(0, 'Generation interrupted', 'ETA —');
    closeGenerationProgressSocket();
    return;
  }
}
function startGenerationProgressSocket(clientId, promptId='') {
  const imageSession = getRoleSession('image');
  if (!imageSession?.connected || !imageSession.base_url || !clientId) return;
  closeGenerationProgressSocket();
  generationProgressClientId = clientId;
  generationProgressPromptId = String(promptId || '').trim();
  generationProgressStartedAt = Date.now();
  beginGenerationPreviewLifecycle({ client_id: clientId, prompt_id: generationProgressPromptId });
  setGenerationProgress(2, 'Connecting to Comfy live preview…', 'ETA calculating…');
  try {
    generationProgressSocket = new WebSocket(buildGenerationWsUrl(imageSession.base_url, clientId));
    generationProgressSocket.binaryType = 'arraybuffer';
  } catch (_) {
    generationProgressSocket = null;
    setGenerationProgress(5, 'Queued. Waiting for progress updates…', 'ETA —');
    return;
  }
  generationProgressSocket.addEventListener('open', () => {
    const state = getGenerationPreviewLifecycleState();
    state.socket_open = true;
    state.last_error = '';
    setGenerationProgress(4, 'Connected to Comfy live preview stream…', 'ETA calculating…');
  });
  generationProgressSocket.addEventListener('message', async event => {
    try {
      if (typeof event.data === 'string') {
        handleGenerationProgressMessage(JSON.parse(event.data || '{}'));
        return;
      }
      if (event.data instanceof ArrayBuffer) {
        applyGenerationPreviewBuffer(event.data);
        return;
      }
      if (event.data instanceof Blob) {
        applyGenerationPreviewBuffer(await event.data.arrayBuffer());
        return;
      }
    } catch (_) {}
  });
  generationProgressSocket.addEventListener('close', () => {
    const state = getGenerationPreviewLifecycleState();
    state.socket_open = false;
    generationProgressSocket = null;
    const pct = Number(generationLastProgressPercent || 0);
    if (pct >= 90 && pct < 100) ensureGenerationFinalizationPoll('socket_close');
  });
  generationProgressSocket.addEventListener('error', () => {
    const state = getGenerationPreviewLifecycleState();
    state.socket_open = false;
    state.last_error = 'Live preview websocket error';
    setGenerationProgress(Math.max(5, Number($('generation-progress-bar')?.style.width?.replace('%','') || 0)), 'Queued. Waiting for live preview/progress updates…', 'ETA —');
  });
}

window.getNeoGenerationPreviewDebugState = function getNeoGenerationPreviewDebugState() {
  try { return JSON.parse(JSON.stringify(getGenerationPreviewLifecycleState())); }
  catch (_) { return getGenerationPreviewLifecycleState(); }
};

function setSelectOptionsForElement(el, items, placeholder='None', keepValue=true, forceFirst=false) {
  if (!el) return;
  const current = keepValue ? String(el.value || '') : '';
  const rows = Array.isArray(items) ? items : [];
  el.innerHTML = '';
  const placeholderOpt = document.createElement('option');
  placeholderOpt.value = '';
  placeholderOpt.textContent = placeholder;
  el.appendChild(placeholderOpt);
  rows.forEach(item => {
    const opt = document.createElement('option');
    opt.value = generationSelectItemValue(item);
    opt.textContent = generationSelectItemLabel(item);
    if (current && current === opt.value) opt.selected = true;
    el.appendChild(opt);
  });
  if (!current && rows.length && forceFirst) el.value = generationSelectItemValue(rows[0]);
}


function getGenerationControlnetModelItems() {
  const state = (typeof generationCatalogState !== 'undefined' && generationCatalogState) ? generationCatalogState : (window.generationCatalogState || window.NeoGenerationCatalog || {});
  const candidates = [state.controlnet, state.controlnets, state.control_net, state.controlNet, state.controlnet_models, state.controlnetModels];
  for (const item of candidates) {
    if (Array.isArray(item) && item.length) return item;
  }
  try {
    const nested = state.models || {};
    const nestedCandidates = [nested.controlnet, nested.controlnets, nested.control_net, nested.controlnet_models];
    for (const item of nestedCandidates) {
      if (Array.isArray(item) && item.length) return item;
    }
  } catch (_) {}
  return [];
}

function refreshGenerationControlnetModelSelect(selectEl, placeholder='None') {
  if (!selectEl) return;
  const models = getGenerationControlnetModelItems();
  setSelectOptionsForElement(selectEl, models, placeholder, true, false);
}

function refreshGenerationDynamicOptions() {
  setGenerationCompatibleLoraOptionsForElement($('generation-lora-name'), 'None');
  setSelectOptionsForElement($('generation-controlnet-unit'), generationControlnetUnitOptions, 'Select unit');
  refreshPrimaryGenerationControlnetPreprocessorFilter();
  refreshPrimaryGenerationControlnetModelFilter();
  refreshGenerationIpAdapterPrimaryOptions();
  setSelectOptionsForElement($('generation-refine-resize-method'), generationResizeMethodOptions, 'Resize method', false, true);
  setSelectOptionsForElement($('generation-refine-upscaler'), generationCatalogState.upscalers, 'Interpolation only');
  setSelectOptionsForElement($('generation-image-upscale-model'), generationCatalogState.upscalers, 'Interpolation only');
  setSelectOptionsForElement($('generation-image-upscale-restore-model'), (generationCatalogState.facerestore_models || []).filter(item => String(generationSelectItemValue(item)).toLowerCase().includes('codeformer')), 'Choose CodeFormer model');
  setSelectOptionsForElement($('generation-refine-sampler'), generationCatalogState.samplers || generationFallbackSamplers, 'Reuse main sampler');
  setSelectOptionsForElement($('generation-refine-scheduler'), generationCatalogState.schedulers || generationFallbackSchedulers, 'Reuse main scheduler');
  setSelectOptionsForElement($('generation-supir-model'), generationCatalogState.checkpoints || [], 'Choose SUPIR checkpoint');
  setSelectOptionsForElement($('generation-supir-sdxl-model'), generationCatalogState.checkpoints || [], 'Choose SDXL checkpoint');
  setSelectOptionsForElement($('generation-supir-color-fix-type'), generationSupirColorFixOptions, 'Color fix', false, true);
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-name').forEach(el => setGenerationCompatibleLoraOptionsForElement(el, 'None'));
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-unit').forEach(el => setSelectOptionsForElement(el, generationControlnetUnitOptions, 'Select unit'));
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => {
    refreshGenerationControlnetPreprocessorFilterForRow(row);
    refreshGenerationControlnetModelFilterForRow(row);
  });
  document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row').forEach(row => {
    refreshGenerationIpAdapterRowOptions(row);
  });
  updatePrimaryGenerationLoraSummary();
  updatePrimaryGenerationControlnetSummary();
  updatePrimaryGenerationIpAdapterSummary();
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-row').forEach(row => updateGenerationLoraRowSummary(row));
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => updateGenerationControlnetRowSummary(row));
  document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row').forEach(row => updateGenerationIpAdapterRowSummary(row));
  updateGenerationUnitIndices();
}



const generationRES4LYFSafePresets = {
  balanced: { label:'RES Balanced', sampler:'res_2m', scheduler:'beta57', fallbackScheduler:'' },
  detail_slow: { label:'RES Detail Slow', sampler:'res_5s', scheduler:'beta57', fallbackScheduler:'' },
  experimental: { label:'RES Experimental', sampler:'res_3s', scheduler:'beta57', fallbackScheduler:'' },
};

function getGenerationRES4LYFCatalog() {
  const catalog = (typeof generationCatalogState !== 'undefined' && generationCatalogState) ? generationCatalogState : (window.generationCatalogState || {});
  const res = (catalog && typeof catalog.res4lyf === 'object' && catalog.res4lyf) ? catalog.res4lyf : {};
  const features = (catalog && typeof catalog.features === 'object' && catalog.features) ? catalog.features : {};
  const samplers = Array.isArray(res.samplers) ? res.samplers.map(item => String(item || '').trim()).filter(Boolean) : [];
  const schedulers = Array.isArray(res.schedulers) ? res.schedulers.map(item => String(item || '').trim()).filter(Boolean) : [];
  return { catalog, res, features, samplers, schedulers };
}

function setGenerationSelectValueIfAvailable(id, value) {
  const el = $(id);
  const target = String(value || '').trim();
  if (!el || !target) return false;
  const match = Array.from(el.options || []).find(opt => String(opt.value || '').trim().toLowerCase() === target.toLowerCase());
  if (!match) return false;
  el.value = match.value;
  el.dispatchEvent(new Event('change', { bubbles:true }));
  return true;
}

function getGenerationActiveFamilyForRES4LYF() {
  const activeButtonFamily = String(document.querySelector('[data-generation-family].active')?.getAttribute('data-generation-family') || '').trim();
  if (activeButtonFamily) return activeButtonFamily;
  const routerFamily = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '').trim();
  if (routerFamily) return routerFamily;
  return String($('generation-family')?.value || 'sdxl_sd').trim();
}

function getGenerationLanPaintRouteSummaryForRES4LYF(mode, family, inpaintBackend) {
  const usesLanPaintRoute = (mode === 'inpaint' || mode === 'outpaint') && inpaintBackend === 'lanpaint';
  if (!usesLanPaintRoute) return null;
  const sampler = String($('generation-sampler')?.value || '').trim() || 'auto';
  const scheduler = String($('generation-scheduler')?.value || '').trim() || 'auto';
  const settings = (typeof readGenerationLanPaintUISettings === 'function')
    ? readGenerationLanPaintUISettings()
    : { num_steps: 5, prompt_mode: 'Image First' };
  const familyLabel = family === 'qwen_image_edit' ? 'Qwen' : (family === 'flux' ? 'Flux' : 'SDXL/SD');
  return {
    sampler,
    scheduler,
    numSteps: settings.num_steps ?? 5,
    promptMode: settings.prompt_mode || 'Image First',
    familyLabel,
    reason: `RES4LYF presets are disabled because this route uses LanPaint_KSampler, not the normal KSampler preset path. LanPaint route: ${familyLabel}; sampler ${sampler} / ${scheduler}; thinking depth ${settings.num_steps ?? 5}; prompt mode ${settings.prompt_mode || 'Image First'}.`
  };
}

function getGenerationRES4LYFCompatibilityState() {
  const mode = String($('generation-workflow-type')?.value || 'txt2img').trim().toLowerCase();
  const family = getGenerationActiveFamilyForRES4LYF().trim().toLowerCase();
  const inpaintBackend = String($('generation-inpaint-backend')?.value || 'standard').trim().toLowerCase();
  const refineEnabled = String($('generation-refine-enabled')?.value || 'off').trim().toLowerCase();
  const detailerEnabled = !!$('generation-detailer-enabled')?.checked;
  const guarded = mode === 'inpaint' || mode === 'outpaint';
  const reasons = [];
  let allowed = true;

  if (!['txt2img', 'img2img', 'inpaint', 'outpaint'].includes(mode)) {
    allowed = false;
    reasons.push(`unsupported mode ${mode || 'unknown'}`);
  }
  // LanPaint is only relevant to mask routes. Do not let a stale LanPaint selector
  // from a previous Qwen session disable RES presets on normal SDXL txt2img/img2img.
  const usesLanPaintRoute = (mode === 'inpaint' || mode === 'outpaint') && inpaintBackend === 'lanpaint';
  const lanpaintSummary = getGenerationLanPaintRouteSummaryForRES4LYF(mode, family, inpaintBackend);
  const modelSource = String($('generation-model-source')?.value || '').trim().toLowerCase();
  const ggufClipType = String($('generation-gguf-clip-type')?.value || '').trim().toLowerCase();
  const ggufUnet = String($('generation-gguf-unet')?.value || '').trim();
  const usesQwenRoute = family === 'qwen_image_edit' && (modelSource === 'gguf' || ggufClipType === 'qwen_image' || !!ggufUnet || usesLanPaintRoute);
  if (usesLanPaintRoute && lanpaintSummary) {
    allowed = false;
    reasons.push(lanpaintSummary.reason);
  } else if (usesQwenRoute) {
    allowed = false;
    reasons.push('RES4LYF presets are disabled because this Qwen route does not use the normal KSampler preset path.');
  }
  if (refineEnabled && !['off', 'false', '0', 'none', ''].includes(refineEnabled)) {
    allowed = false;
    reasons.push('Refine/Upscale Lab is enabled');
  }
  if (detailerEnabled) {
    allowed = false;
    reasons.push('Detailer/ADetailer is enabled');
  }

  return {
    allowed,
    guarded,
    mode,
    family,
    inpaintBackend,
    lanpaintSummary,
    reasons,
    message: allowed
      ? (guarded ? 'Allowed, but guarded for mask/boundary review.' : 'Allowed on the base KSampler path.')
      : `Blocked for this route: ${reasons.join('; ')}`
  };
}

function getAvailableGenerationRES4LYFPresets() {
  const { samplers } = getGenerationRES4LYFCatalog();
  const compat = getGenerationRES4LYFCompatibilityState();
  const samplerSet = new Set(samplers.map(item => item.toLowerCase()));
  if (!compat.allowed) return [];
  return Object.entries(generationRES4LYFSafePresets).filter(([, preset]) => samplerSet.has(String(preset.sampler || '').toLowerCase()));
}

function applyGenerationRES4LYFPreset(key) {
  const preset = generationRES4LYFSafePresets[String(key || '').trim()];
  if (!preset) return false;
  const compat = getGenerationRES4LYFCompatibilityState();
  if (!compat.allowed) {
    announceGenerationStatus(`${preset.label} is blocked by the compatibility matrix: ${compat.reasons.join('; ')}`, 'warning');
    return false;
  }
  const { samplers, schedulers } = getGenerationRES4LYFCatalog();
  const samplerSet = new Set(samplers.map(item => item.toLowerCase()));
  const schedulerSet = new Set(schedulers.map(item => item.toLowerCase()));
  const sampler = String(preset.sampler || '').trim();
  if (!sampler || !samplerSet.has(sampler.toLowerCase())) {
    announceGenerationStatus(`${preset.label} is unavailable because ${sampler || 'its sampler'} was not detected in ComfyUI.`, 'warning');
    return false;
  }
  const samplerApplied = setGenerationSelectValueIfAvailable('generation-sampler', sampler);
  let schedulerApplied = false;
  const preferredScheduler = String(preset.scheduler || '').trim();
  if (preferredScheduler && schedulerSet.has(preferredScheduler.toLowerCase())) {
    schedulerApplied = setGenerationSelectValueIfAvailable('generation-scheduler', preferredScheduler);
  }
  if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
  const schedulerText = schedulerApplied ? ` + ${preferredScheduler}` : ' + current scheduler';
  const guardText = compat.guarded ? ' Guarded mode: review mask/boundary edges before batching.' : '';
  announceGenerationStatus(`${preset.label} applied: ${sampler}${schedulerText}. Existing KSampler workflow unchanged.${guardText}`, 'success');
  return samplerApplied;
}

function refreshGenerationRES4LYFPresetButtons() {
  const wrap = $('generation-res4lyf-presets');
  const note = $('generation-res4lyf-preset-note');
  const compat = getGenerationRES4LYFCompatibilityState();
  const available = new Set(getAvailableGenerationRES4LYFPresets().map(([key]) => key));
  const { samplers } = getGenerationRES4LYFCatalog();
  const hasDetectedSampler = samplers.length > 0;
  const hasAny = hasDetectedSampler;
  if (wrap) wrap.style.display = hasAny ? '' : 'none';
  if (note) {
    note.style.display = hasAny ? '' : 'none';
    note.textContent = compat.allowed
      ? (compat.guarded
        ? 'Compatibility: guarded on inpaint/outpaint. Presets only switch sampler/scheduler; review mask edges before batch use.'
        : 'Compatibility: safe on base txt2img/img2img KSampler path. Presets only switch sampler/scheduler.')
      : `Compatibility: ${compat.reasons.join('; ')}`;
  }
  Object.keys(generationRES4LYFSafePresets).forEach(key => {
    const btn = document.querySelector(`[data-res4lyf-preset="${key}"]`);
    if (!btn) return;
    const detected = samplers.map(item => item.toLowerCase()).includes(String(generationRES4LYFSafePresets[key].sampler || '').toLowerCase());
    const enabled = available.has(key);
    btn.disabled = !enabled;
    btn.classList.toggle('is-disabled', !enabled);
    btn.title = enabled
      ? `${compat.message} Applies ${generationRES4LYFSafePresets[key].sampler} through the existing KSampler path.`
      : (detected ? compat.message : `${generationRES4LYFSafePresets[key].sampler} was not detected in ComfyUI.`);
  });
}

function bindGenerationRES4LYFPresetButtons() {
  document.querySelectorAll('[data-res4lyf-preset]').forEach(btn => {
    if (btn.dataset.res4lyfBound === '1') return;
    btn.dataset.res4lyfBound = '1';
    btn.addEventListener('click', () => applyGenerationRES4LYFPreset(btn.dataset.res4lyfPreset || ''));
  });
}

function renderGenerationRES4LYFStatus() {
  const badge = $('generation-res4lyf-badge');
  const summary = $('generation-res4lyf-summary');
  const details = $('generation-res4lyf-details');
  const { res, features, samplers, schedulers } = getGenerationRES4LYFCatalog();
  const installed = !!(res.installed || features.res4lyf);
  const ready = !!(res.ready || features.res4lyf_ready);
  const hasClown = !!(res.has_clownshark_sampler || features.res4lyf_clownshark_sampler);
  const presetCount = getAvailableGenerationRES4LYFPresets().length;
  let label = 'Not installed';
  let tone = 'is-disabled';
  let note = 'Optional RES4LYF sampler support was not detected in the current ComfyUI catalog.';
  if (ready) {
    label = 'Ready';
    tone = 'is-enabled';
    note = presetCount ? `Detected RES sampler support. ${presetCount} safe preset(s) available.` : 'RES4LYF sampler support detected.';
  } else if (installed) {
    label = 'Partial';
    tone = 'is-warning';
    note = 'RES4LYF-related nodes were detected, but no safe RES sampler names were exposed yet.';
  }
  if (badge) {
    badge.textContent = `RES4LYF: ${label}`;
    badge.classList.remove('is-enabled', 'is-disabled', 'is-warning');
    badge.classList.add(tone);
    badge.title = note;
  }
  if (summary) summary.textContent = note;
  if (details) {
    const bits = [];
    if (samplers.length) bits.push(`samplers ${samplers.join(', ')}`);
    if (schedulers.length) bits.push(`schedulers ${schedulers.join(', ')}`);
    if (hasClown) bits.push('ClownsharKSampler detected');
    details.textContent = bits.length ? bits.join(' Â· ') : 'No workflow changes applied. Existing KSampler path remains active.';
  }
  refreshGenerationRES4LYFPresetButtons();
  refreshGenerationRES4LYFRecoveryPanel();
}
window.renderGenerationRES4LYFStatus = renderGenerationRES4LYFStatus;
window.applyGenerationRES4LYFPreset = applyGenerationRES4LYFPreset;


function ensureGenerationRES4LYFRecoveryPanel() {
  const card = $('generation-res4lyf-status');
  if (!card || $('generation-res4lyf-recovery-panel')) return;
  const panel = document.createElement('div');
  panel.id = 'generation-res4lyf-recovery-panel';
  panel.style.cssText = 'margin-top:10px; display:grid; gap:8px;';
  panel.innerHTML = `
    <details id="generation-res4lyf-help" class="card-lite" style="padding:8px 10px; border:1px solid rgba(148,163,184,.16); background:rgba(15,23,42,.18);">
      <summary style="cursor:pointer; font-weight:700; font-size:12px;">RES4LYF help + recovery</summary>
      <div class="mini-note" style="margin-top:8px; line-height:1.5;">
        <strong>Optional extension.</strong> Install RES4LYF in <code>ComfyUI/custom_nodes</code>, restart ComfyUI, then refresh Neo's catalog.<br>
        Safe presets use the existing KSampler path. Advanced Lane is experimental and should be tested with one txt2img render first.<br>
        If RES4LYF is missing or fails at queue time, Neo can fall back to <strong>Core KSampler / euler / normal</strong> instead of hard-crashing.
      </div>
    </details>
    <details id="generation-res4lyf-debug" class="card-lite" style="padding:8px 10px; border:1px solid rgba(148,163,184,.16); background:rgba(15,23,42,.18);">
      <summary style="cursor:pointer; font-weight:700; font-size:12px;">RES4LYF debug info</summary>
      <pre id="generation-res4lyf-debug-output" style="white-space:pre-wrap; margin:8px 0 0; font-size:11px; line-height:1.45; max-height:220px; overflow:auto;">Waiting for catalog...</pre>
    </details>
  `;
  card.appendChild(panel);
}

function getGenerationRES4LYFDebugText() {
  const { res, features, samplers, schedulers } = getGenerationRES4LYFCatalog();
  const compat = getGenerationRES4LYFCompatibilityState();
  const engine = String($('generation-res4lyf-engine')?.value || 'core');
  const hasClown = !!(res.has_clownshark_sampler || features.res4lyf_clownshark_sampler || features.res4lyf_advanced_lane);
  const detectedNodes = Array.isArray(res.detected_nodes) ? res.detected_nodes : [];
  const probeErrors = Array.isArray(res.probe_errors) ? res.probe_errors : [];
  const fallbackApplied = window.__neoRES4LYFFallbackApplied || false;
  return [
    `Installed: ${res.installed || features.res4lyf ? 'Yes' : 'No'}`,
    `Ready: ${res.ready || features.res4lyf_ready ? 'Yes' : 'No'}`,
    `ClownsharKSampler: ${hasClown ? 'Yes' : 'No'}`,
    `Active Engine: ${engine === 'clownshark' ? 'RES4LYF ClownsharKSampler' : 'Core KSampler'}`,
    `Compatibility: ${compat.allowed ? 'Allowed' : 'Blocked'}${compat.reasons?.length ? ' · ' + compat.reasons.join('; ') : ''}`,
    `Fallback Applied: ${fallbackApplied ? 'Yes' : 'No'}`,
    '',
    `Detected Samplers: ${samplers.length ? samplers.join(', ') : 'None'}`,
    `Detected Schedulers: ${schedulers.length ? schedulers.join(', ') : 'None'}`,
    `Detected Nodes: ${detectedNodes.length ? detectedNodes.join(', ') : 'None'}`,
    probeErrors.length ? `Probe Errors: ${probeErrors.join(' | ')}` : 'Probe Errors: None',
  ].join('\n');
}

function refreshGenerationRES4LYFRecoveryPanel() {
  ensureGenerationRES4LYFRecoveryPanel();
  const out = $('generation-res4lyf-debug-output');
  if (out) out.textContent = getGenerationRES4LYFDebugText();
}

window.refreshGenerationRES4LYFRecoveryPanel = refreshGenerationRES4LYFRecoveryPanel;
window.addEventListener('neo:generation-catalog-refreshed', () => renderGenerationRES4LYFStatus());
document.addEventListener('DOMContentLoaded', () => { bindGenerationRES4LYFPresetButtons(); renderGenerationRES4LYFStatus(); });

function readGenerationSceneDirectorStateForTargets() {
  const candidates = [];
  try {
    const liveState = window.NeoSceneDirectorExtension?.state;
    if (liveState && typeof liveState === 'object') candidates.push(liveState);
  } catch (_) {}
  try {
    const extState = window.NeoSceneDirectorExtension?.getState?.();
    if (extState && typeof extState === 'object') {
      candidates.push(extState);
      if (extState.scene_director_state && typeof extState.scene_director_state === 'object') candidates.push(extState.scene_director_state);
    }
  } catch (_) {}
  try {
    const stateNode = document.getElementById('neo-scene-director-state');
    const raw = stateNode?.value || stateNode?.textContent || '';
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') candidates.push(parsed);
    }
  } catch (_) {}
  try {
    const payloadNode = document.getElementById('generation-last-payload') || document.getElementById('neo-last-payload');
    const raw = payloadNode?.value || payloadNode?.textContent || '';
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.scene_director_state && typeof parsed.scene_director_state === 'object') candidates.push(parsed.scene_director_state);
    }
  } catch (_) {}
  return candidates.find(item => Array.isArray(item?.regions)) || null;
}

function sceneDirectorRegionsToLoraTargets(state) {
  const regions = Array.isArray(state?.regions) ? state.regions : [];
  return regions
    .map((region, index) => {
      const enabled = region?.enabled !== false;
      const visible = region?.visible !== false;
      if (!enabled || !visible) return null;
      const regionIndex = Number(region?.index || region?.region_index || index + 1) || (index + 1);
      return {
        value: `scene_region_${regionIndex}`,
        label: String(region?.label || region?.name || `Region ${regionIndex}`).trim() || `Region ${regionIndex}`,
        region_index: regionIndex,
        id: String(region?.id || '').trim(),
        source: 'scene_director_state_fallback'
      };
    })
    .filter(Boolean);
}

function dedupeGenerationLoraTargets(targets) {
  const seen = new Set();
  return targets.filter(item => {
    const value = String(item?.value || '').trim();
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

function getGenerationSceneDirectorLoraTargets() {
  const targets = [{ value: 'global', label: 'Global' }];
  try {
    const sceneTargets = window.NeoSceneDirectorExtension?.getRegionTargets?.() || [];
    sceneTargets.forEach((item, index) => {
      const value = String(item?.value || ('scene_region_' + (index + 1))).trim();
      const label = String(item?.label || ('Scene Region ' + (index + 1))).trim();
      if (value) targets.push({ value, label, region_index: item?.region_index || index + 1, id: item?.id || '', source: 'scene_director_live_registry' });
    });
  } catch (_) {}
  if (targets.length <= 1) {
    const fallbackState = readGenerationSceneDirectorStateForTargets();
    sceneDirectorRegionsToLoraTargets(fallbackState).forEach(item => targets.push(item));
  }
  return dedupeGenerationLoraTargets(targets);
}

function normalizeGenerationLoraApplyTo(value) {
  const key = String(value || 'global').trim().toLowerCase();
  if (key === 'global') return 'global';
  if (/^scene_region_\d+$/.test(key)) return key;
  return 'global';
}

function generationLoraApplyToLabel(value) {
  const key = normalizeGenerationLoraApplyTo(value);
  if (key === 'global') return 'Global';
  const found = getGenerationSceneDirectorLoraTargets().find(item => item.value === key);
  return found ? found.label : key.replace('scene_region_', 'Scene Region ');
}

function buildGenerationLoraApplyToOptions(selected='global') {
  const current = normalizeGenerationLoraApplyTo(selected);
  return getGenerationSceneDirectorLoraTargets()
    .map(item => '<option value="' + escapeHtml(item.value) + '" ' + (item.value === current ? 'selected' : '') + '>' + escapeHtml(item.label) + '</option>')
    .join('');
}

function refreshGenerationLoraApplyTargets() {
  const targets = getGenerationSceneDirectorLoraTargets();
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-apply-to').forEach(select => {
    const current = normalizeGenerationLoraApplyTo(select.value || select.dataset.value || 'global');
    const hasCurrent = targets.some(item => item.value === current);
    const visibleTargets = targets.slice();
    if (current !== 'global' && !hasCurrent) {
      visibleTargets.push({ value: current, label: generationLoraApplyToLabel(current) + ' (waiting for Scene Director)', source: 'preserved_selection' });
    }
    select.innerHTML = visibleTargets.map(item => '<option value="' + escapeHtml(item.value) + '" ' + (item.value === current ? 'selected' : '') + '>' + escapeHtml(item.label) + '</option>').join('');
    select.value = current;
    select.dataset.value = current;
  });
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-row').forEach(row => updateGenerationLoraRowSummary(row));
}
window.addEventListener('neo-scene-director-regions-updated', () => refreshGenerationLoraApplyTargets());
window.addEventListener('neo-scene-director-state-updated', () => refreshGenerationLoraApplyTargets());
window.addEventListener('neo:generation-draft-applied', () => window.setTimeout(refreshGenerationLoraApplyTargets, 0));
document.addEventListener('DOMContentLoaded', () => {
  refreshGenerationLoraApplyTargets();
  window.setTimeout(refreshGenerationLoraApplyTargets, 250);
  window.setTimeout(refreshGenerationLoraApplyTargets, 1000);
});

function createGenerationLoraRow(values={}) {
  generationLoraRowCounter += 1;
  const row = document.createElement('div');
  row.className = 'grid grid-4 generation-dynamic-row generation-lora-row generation-unit-card';
  row.dataset.uid = values.uid || `lora_${generationLoraRowCounter}`;
  const target = normalizeGenerationPassTarget(values.target || 'both');
  const applyTo = normalizeGenerationLoraApplyTo(values.apply_to || values.applyTo || 'global');
  row.innerHTML = `
    <div class="generation-unit-topbar" style="grid-column:1 / -1;">
      <div class="generation-unit-heading">
        <span class="generation-unit-index">00</span>
        <div>
          <div class="generation-unit-title">LoRA stack row</div>
          <div class="accordion-hint">Order matters. Move rows up or down to change the chain.</div>
        </div>
      </div>
      <div class="generation-unit-actions">
        <label class="generation-toggle-pill"><input class="generation-unit-enabled" type="checkbox" ${values.enabled === false ? '' : 'checked'} /> Enabled</label>
        <button class="btn btn-small generation-row-move-up" type="button" title="Move this LoRA row up">↑</button>
        <button class="btn btn-small generation-row-move-down" type="button" title="Move this LoRA row down">↓</button>
        <button class="btn btn-small generation-remove-row" type="button" title="Remove this LoRA row">Remove</button>
      </div>
    </div>
    <div>
      <label>LoRA</label>
      <select class="generation-lora-name"><option value="">None</option></select>
    </div>
    <div>
      <label>LoRA strength</label>
      <input class="generation-lora-strength" type="number" step="0.05" value="${Number(values.strength ?? 0.8)}" />
    </div>
    <div>
      <label>Apply to</label>
      <select class="generation-lora-apply-to" data-value="${escapeHtml(applyTo)}">
        ${buildGenerationLoraApplyToOptions(applyTo)}
      </select>
    </div>
    <div>
      <label>Pass target</label>
      <select class="generation-lora-target">
        <option value="both" ${target === 'both' ? 'selected' : ''}>Both passes</option>
        <option value="base" ${target === 'base' ? 'selected' : ''}>Base pass only</option>
        <option value="finish" ${target === 'finish' ? 'selected' : ''}>Finish / redraw only</option>
      </select>
    </div>
    <div class="generation-unit-summary" style="grid-column:1 / -1;">Pick a LoRA for this stack slot.</div>`;
  row.querySelector('.generation-remove-row')?.addEventListener('click', () => { row.remove(); updateGenerationUnitIndices(); scheduleGenerationDraftSave(); });
  row.querySelector('.generation-row-move-up')?.addEventListener('click', () => moveGenerationUnitRow(row, -1));
  row.querySelector('.generation-row-move-down')?.addEventListener('click', () => moveGenerationUnitRow(row, 1));
  row.querySelector('.generation-controlnet-build-map')?.addEventListener('click', () => buildGenerationControlnetMap({ row }));
  row.querySelector('.generation-controlnet-apply-map')?.addEventListener('click', () => applyPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelector('.generation-controlnet-download-map')?.addEventListener('click', () => downloadPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelectorAll('input, select, textarea').forEach(el => {
    const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(eventName, () => { updateGenerationLoraRowSummary(row); scheduleGenerationDraftSave(); });
    if (el.type === 'checkbox') el.addEventListener('change', () => { updateGenerationLoraRowSummary(row); scheduleGenerationDraftSave(); });
  });
  setSelectOptionsForElement(row.querySelector('.generation-lora-name'), generationCatalogState.loras, 'None');
  refreshGenerationLoraApplyTargets();
  if (values.name) row.querySelector('.generation-lora-name').value = values.name;
  row.querySelector('.generation-lora-name')?.addEventListener('change', () => {
    const select = row.querySelector('.generation-lora-name');
    const selectedValue = trim(select?.value || '');
    const selectedLabel = trim(select?.selectedOptions?.[0]?.textContent || '');
    const candidates = [selectedLabel, selectedValue].filter(Boolean);
    if (candidates.length) inspectGenerationLoraByName(candidates).catch(() => {});
  });
  updateGenerationLoraRowSummary(row);
  return row;
}


function normalizeGenerationControlnetExtraLayout(row=null) {
  const list = $('generation-controlnet-extra-list');
  if (list) {
    list.style.width = '100%';
    list.style.maxWidth = 'none';
    list.style.minWidth = '0';
    list.style.display = 'flex';
    list.style.flexDirection = 'column';
    list.style.alignItems = 'stretch';
    list.style.gap = '12px';
    list.style.gridColumn = '1 / -1';
    list.style.clear = 'both';
    if (list.parentElement) {
      list.parentElement.style.minWidth = list.parentElement.style.minWidth || '0';
    }
  }
  const addBtn = $('btn-generation-add-controlnet');
  const addRow = addBtn?.closest?.('.row');
  if (addRow) {
    addRow.style.gridColumn = '1 / -1';
    addRow.style.width = '100%';
    addRow.style.clear = 'both';
    addRow.style.justifyContent = 'flex-start';
  }
  const rows = row ? [row] : Array.from(document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row'));
  rows.filter(Boolean).forEach(unit => {
    unit.classList.add('generation-unit-card-controlnet');
    unit.style.width = '100%';
    unit.style.maxWidth = 'none';
    unit.style.minWidth = '0';
    unit.style.boxSizing = 'border-box';
    unit.style.alignSelf = 'stretch';
    unit.style.gridColumn = '1 / -1';
    unit.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))';
    unit.querySelectorAll('.generation-unit-topbar, .generation-controlnet-build-lane, .generation-unit-summary').forEach(el => {
      el.style.gridColumn = '1 / -1';
      el.style.minWidth = '0';
      el.style.width = el.classList.contains('generation-unit-topbar') ? '' : '100%';
    });
    unit.querySelectorAll('.generation-controlnet-preset-wrap').forEach(wrap => {
      wrap.style.gridColumn = '1 / -1';
      wrap.style.width = '100%';
      wrap.style.minWidth = '0';
      wrap.style.display = 'grid';
      wrap.style.gridTemplateColumns = 'minmax(min(100%, 220px), 360px) minmax(0, 1fr)';
      wrap.querySelectorAll('.generation-controlnet-preset-hint, .mini-note').forEach(note => {
        note.style.minWidth = '0';
        note.style.maxWidth = '100%';
        note.style.whiteSpace = 'normal';
        note.style.overflowWrap = 'break-word';
      });
    });
    unit.querySelectorAll('.generation-controlnet-preview-panel > .grid').forEach(grid => {
      grid.classList.add('generation-controlnet-preview-grid');
      grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))';
      grid.style.width = '100%';
      grid.style.minWidth = '0';
    });
  });
}

function createGenerationControlnetRow(values={}) {
  generationControlnetRowCounter += 1;
  const uid = values.uid || `control_${generationControlnetRowCounter}`;
  const row = document.createElement('div');
  row.className = 'grid grid-5 generation-dynamic-row generation-controlnet-row generation-unit-card generation-unit-card-controlnet';
  row.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))';
  row.dataset.uid = uid;
  row.innerHTML = `
    <div class="generation-unit-topbar" style="grid-column:1 / -1;">
      <div class="generation-unit-heading">
        <span class="generation-unit-index">00</span>
        <div>
          <div class="generation-unit-title">ControlNet unit</div>
          <div class="accordion-hint">Each row can carry its own preprocessor, control model, and image.</div>
        </div>
      </div>
      <div class="generation-unit-actions">
        <label class="generation-toggle-pill"><input class="generation-unit-enabled" type="checkbox" ${values.enabled === false ? '' : 'checked'} /> Enabled</label>
        <button class="btn btn-small generation-row-move-up" type="button" title="Move this ControlNet row up">↑</button>
        <button class="btn btn-small generation-row-move-down" type="button" title="Move this ControlNet row down">↓</button>
        <button class="btn btn-small generation-remove-row" type="button" title="Remove this ControlNet row">Remove</button>
      </div>
    </div>
    <div>
      <label>Unit</label>
      <select class="generation-controlnet-unit"><option value="auto">Auto</option></select>
    </div>
    <div>
      <label>Preprocessor</label>
      <select class="generation-controlnet-preprocessor"><option value="none">None</option></select>
    </div>
    <div>
      <label>ControlNet model</label>
      <select class="generation-controlnet-name"><option value="">None</option></select>
    </div>
    <div>
      <label>Strength</label>
      <input class="generation-controlnet-strength" type="number" step="0.05" value="${Number(values.strength ?? 1.0)}" />
    </div>
    <div class="generation-controlnet-build-lane" style="grid-column:1 / -1;">
      <label>Control image</label>
      <input class="generation-control-image" type="file" accept="image/*" />
      <div class="generation-controlnet-preview-first" style="display:block; margin-top:10px; width:100%;">
        <div class="generation-controlnet-controls-panel" style="width:100%; max-width:none;">
          <div class="row" style="gap:8px; flex-wrap:wrap;">
            <button class="btn btn-small generation-controlnet-build-map" type="button">🧭 Build preview map</button>
            <button class="btn btn-small generation-controlnet-apply-map" type="button" disabled>Send map to this ControlNet unit</button>
            <button class="btn btn-small generation-controlnet-download-map" type="button" disabled>Download preview map</button>
          </div>
          <div class="generation-controlnet-backend-note accordion-hint" style="margin-top:8px;">Last map backend: not built yet</div>
          <div class="mini-note generation-controlnet-save-note" style="margin-top:6px;">Generated maps are saved to ComfyUI output when Comfy Aux is used.</div>
          <div class="generation-controlnet-map-settings generation-controlnet-real-settings" style="margin-top:10px; display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; align-items:end;">
            <div data-cn-setting="quality"><label>Detect res</label><select class="generation-controlnet-detect-resolution"><option value="512">512 fast</option><option value="768" selected>768 balanced</option><option value="1024">1024 sharper</option><option value="1280">1280 max</option></select></div>
            <div data-cn-setting="timing"><label>Start percent</label><input class="generation-controlnet-start-percent" type="number" min="0" max="1" step="0.01" value="0" /></div>
            <div data-cn-setting="timing"><label>End percent</label><input class="generation-controlnet-end-percent" type="number" min="0" max="1" step="0.01" value="1" /></div>
            <div data-cn-setting="fit"><label>Control image fit</label><select class="generation-controlnet-fit-mode"><option value="contain" selected>Contain / no crop</option><option value="cover">Cover / fill frame</option><option value="stretch">Stretch exact</option><option value="source">Keep source size</option></select></div>
            <div data-cn-setting="quality"><label>Safe mode</label><select class="generation-controlnet-safe-mode"><option value="true" selected>On</option><option value="false">Off</option></select></div>
            <div data-cn-setting="canny"><label>Canny low</label><input class="generation-controlnet-canny-low" type="number" min="0" max="255" step="1" value="100" /></div>
            <div data-cn-setting="canny"><label>Canny high</label><input class="generation-controlnet-canny-high" type="number" min="0" max="255" step="1" value="200" /></div>
            <label class="generation-toggle-pill" data-cn-setting="openpose" style="justify-content:center;"><input class="generation-controlnet-openpose-body" type="checkbox" checked /> Body</label>
            <label class="generation-toggle-pill" data-cn-setting="openpose" style="justify-content:center;"><input class="generation-controlnet-openpose-hand" type="checkbox" checked /> Hands</label>
            <label class="generation-toggle-pill" data-cn-setting="openpose" style="justify-content:center;"><input class="generation-controlnet-openpose-face" type="checkbox" /> Face</label>
            <label class="generation-toggle-pill" data-cn-setting="output" style="justify-content:center;"><input class="generation-controlnet-invert-map" type="checkbox" /> Invert map</label>
            <label class="generation-toggle-pill" data-cn-setting="output" style="justify-content:center;"><input class="generation-controlnet-save-intermediate" type="checkbox" checked /> Save map</label>
          </div>
          <div class="mini-note generation-controlnet-settings-hint" style="margin-top:8px;">Real map controls: timing affects generation, detect/Canny/OpenPose affects preview map quality, fit controls how the image is prepared for ControlNet.</div>
        </div>
        <div class="generation-controlnet-preview-panel" style="width:100%; margin-top:14px; overflow:hidden;">
          <div class="grid grid-2 generation-controlnet-preview-grid" style="gap:14px; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); align-items:stretch;">
            <div class="generation-unit-preview-card" style="min-height:460px; overflow:hidden; display:flex; align-items:center; justify-content:center;">
              <div class="generation-unit-preview-empty generation-controlnet-source-preview-empty">No source preview yet.</div>
              <img class="generation-unit-preview-image generation-controlnet-source-preview hidden" alt="ControlNet source preview" style="width:100%; max-height:620px; object-fit:contain;" />
            </div>
            <div class="generation-unit-preview-card" style="min-height:460px; overflow:hidden; display:flex; align-items:center; justify-content:center;">
              <div class="generation-unit-preview-empty generation-controlnet-map-preview-empty">No generated map preview yet.</div>
              <img class="generation-unit-preview-image generation-controlnet-map-preview hidden" alt="Generated ControlNet map preview" style="width:100%; max-height:620px; object-fit:contain;" />
            </div>
          </div>
          <div class="generation-unit-summary" style="margin-top:8px;">Pick a ControlNet model for this unit.</div>
        </div>
      </div>
    </div>`;
  row.querySelector('.generation-remove-row')?.addEventListener('click', () => { row.remove(); updateGenerationUnitIndices(); scheduleGenerationDraftSave(); });
  row.querySelector('.generation-row-move-up')?.addEventListener('click', () => moveGenerationUnitRow(row, -1));
  row.querySelector('.generation-row-move-down')?.addEventListener('click', () => moveGenerationUnitRow(row, 1));
  row.querySelector('.generation-controlnet-build-map')?.addEventListener('click', () => buildGenerationControlnetMap({ row }));
  row.querySelector('.generation-controlnet-apply-map')?.addEventListener('click', () => applyPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelector('.generation-controlnet-download-map')?.addEventListener('click', () => downloadPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelectorAll('input, select, textarea').forEach(el => {
    const eventName = el.tagName === 'SELECT' ? 'change' : (el.type === 'file' ? 'change' : 'input');
    el.addEventListener(eventName, () => {
      if (el.classList?.contains('generation-controlnet-unit')) {
        refreshGenerationControlnetPreprocessorFilterForRow(row);
        refreshGenerationControlnetModelFilterForRow(row);
      } else if (el.classList?.contains('generation-controlnet-preprocessor')) {
        refreshGenerationControlnetModelFilterForRow(row);
      } else if (el.classList?.contains('generation-control-image')) {
        const context = getGenerationControlnetContext(row);
        const currentFile = context.fileInput?.files?.[0] || null;
        if (context.fileInput?._neoPendingMapFile && currentFile !== context.fileInput._neoPendingMapFile) {
          context.fileInput._neoLastMapSourceFile = null;
        }
        refreshGenerationControlnetSourcePreview(context);
      }
      updateGenerationControlnetRowSummary(row);
      scheduleGenerationDraftSave();
    });
    if (el.type === 'checkbox') el.addEventListener('change', () => { updateGenerationControlnetRowSummary(row); scheduleGenerationDraftSave(); });
  });
  setSelectOptionsForElement(row.querySelector('.generation-controlnet-unit'), generationControlnetUnitOptions, 'Select unit');
  if (values.unit) row.querySelector('.generation-controlnet-unit').value = values.unit;
  refreshGenerationControlnetPreprocessorFilterForRow(row);
  if (values.preprocessor) row.querySelector('.generation-controlnet-preprocessor').value = values.preprocessor;
  refreshGenerationControlnetModelFilterForRow(row);
  if (values.model) row.querySelector('.generation-controlnet-name').value = values.model;
  updateGenerationControlnetRowSummary(row);
  normalizeGenerationControlnetExtraLayout(row);
  return row;
}

function collectGenerationControlFiles() {
  const rows = [];
  const primaryEnabled = isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled'));
  const primaryFile = $('generation-control-image')?.files?.[0] || null;
  if (primaryEnabled && primaryFile) rows.push({ uid:'primary', file: primaryFile });
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => {
    if (!isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'))) return;
    const file = row.querySelector('.generation-control-image')?.files?.[0] || null;
    if (file) rows.push({ uid: row.dataset.uid || '', file });
  });
  return rows.filter(item => item.uid && item.file);
}

function getGenerationControlnetContext(row=null) {
  if (row) {
    return {
      uid: row.dataset.uid || '',
      preprocessor: row.querySelector('.generation-controlnet-preprocessor')?.value || 'none',
      fileInput: row.querySelector('.generation-control-image'),
      summary: row.querySelector('.generation-unit-summary'),
      note: row.querySelector('.generation-controlnet-backend-note'),
      sourcePreview: row.querySelector('.generation-controlnet-source-preview'),
      sourcePreviewEmpty: row.querySelector('.generation-controlnet-source-preview-empty'),
      mapPreview: row.querySelector('.generation-controlnet-map-preview'),
      mapPreviewEmpty: row.querySelector('.generation-controlnet-map-preview-empty'),
      applyButton: row.querySelector('.generation-controlnet-apply-map'),
      downloadButton: row.querySelector('.generation-controlnet-download-map'),
      saveNote: row.querySelector('.generation-controlnet-save-note'),
      row,
    };
  }
  return {
    uid: 'primary',
    preprocessor: $('generation-controlnet-preprocessor')?.value || 'none',
    fileInput: $('generation-control-image'),
    summary: $('generation-controlnet-primary-summary'),
    note: $('generation-controlnet-build-map-note'),
    sourcePreview: $('generation-controlnet-primary-source-preview'),
    sourcePreviewEmpty: $('generation-controlnet-primary-source-preview-empty'),
    mapPreview: $('generation-controlnet-primary-map-preview'),
    mapPreviewEmpty: $('generation-controlnet-primary-map-preview-empty'),
    applyButton: $('btn-generation-controlnet-apply-map'),
    downloadButton: $('btn-generation-controlnet-download-map'),
    saveNote: $('generation-controlnet-save-map-note'),
    row: null,
  };
}

function fileFromBase64DataUrl(dataUrl, filename='control_map.png') {
  const match = String(dataUrl || '').match(/^data:([^;]+);base64,(.+)$/);
  if (!match) throw new Error('Invalid preview image payload.');
  const mime = match[1] || 'image/png';
  const bytes = atob(match[2] || '');
  const array = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) array[i] = bytes.charCodeAt(i);
  return new File([array], filename, { type: mime });
}

function setGenerationPreviewImage(img, empty, src, emptyText='No preview yet.') {
  if (!img || !empty) return;
  if (src) {
    img.src = src;
    img.classList.remove('hidden');
    empty.classList.add('hidden');
  } else {
    img.removeAttribute('src');
    img.classList.add('hidden');
    empty.textContent = emptyText;
    empty.classList.remove('hidden');
  }
}

function fileToObjectUrl(file) {
  try { return file ? URL.createObjectURL(file) : ''; } catch (_) { return ''; }
}

function getGenerationControlnetSourcePreviewFile(context) {
  const fileInput = context?.fileInput || null;
  const controlFile = fileInput?.files?.[0] || null;
  const sourceFile = $('generation-source-image')?.files?.[0] || null;
  const pendingSource = fileInput?._neoLastMapSourceFile || null;
  return pendingSource || controlFile || sourceFile || null;
}

function refreshGenerationControlnetSourcePreview(context) {
  if (!context) return;
  const fileInput = context.fileInput || null;
  const currentFile = fileInput?.files?.[0] || null;
  if (fileInput?._neoLastMapSourceFile && fileInput?._neoPendingMapFile && currentFile && currentFile !== fileInput._neoPendingMapFile) {
    fileInput._neoLastMapSourceFile = null;
  }
  const sourceFile = getGenerationControlnetSourcePreviewFile(context);
  setGenerationPreviewImage(
    context.sourcePreview,
    context.sourcePreviewEmpty,
    fileToObjectUrl(sourceFile),
    'No source preview yet.'
  );
}

function refreshAllGenerationControlnetSourcePreviews() {
  refreshGenerationControlnetSourcePreview(getGenerationControlnetContext(null));
  document.querySelectorAll('.generation-controlnet-row').forEach(row => refreshGenerationControlnetSourcePreview(getGenerationControlnetContext(row)));
}

function renderGenerationControlnetPreviewFirst(context, sourceFile, status, mappedFile) {
  if (context?.fileInput) context.fileInput._neoLastMapSourceFile = sourceFile || null;
  const sourceUrl = fileToObjectUrl(sourceFile);
  const mapUrl = String(status.preview_data_url || '');
  setGenerationPreviewImage(context.sourcePreview, context.sourcePreviewEmpty, sourceUrl, 'No source preview yet.');
  setGenerationPreviewImage(context.mapPreview, context.mapPreviewEmpty, mapUrl, 'No generated map preview yet.');
  if (context.fileInput) {
    context.fileInput._neoPendingMapFile = mappedFile;
    context.fileInput._neoPendingMapDataUrl = mapUrl;
    context.fileInput._neoPendingMapStatus = status || {};
  }
  if (context.applyButton) context.applyButton.disabled = !mappedFile;
  if (context.downloadButton) context.downloadButton.disabled = !mapUrl;
  if (context.saveNote) {
    const folder = String(status.output_subfolder || 'neo_studio/control_maps').trim();
    const name = String(status.filename || mappedFile?.name || 'control_map.png').trim();
    context.saveNote.textContent = `Preview ready. Saved in ComfyUI output/${folder}${name ? ` as ${name}` : ''}.`;
  }
}

function applyPendingGenerationControlnetMap(context) {
  const fileInput = context?.fileInput;
  const mappedFile = fileInput?._neoPendingMapFile;
  if (!fileInput || !mappedFile) {
    setStatus('generation-status', 'Generate a map preview first, then send it to the ControlNet unit.', 'warn');
    return;
  }
  const dt = new DataTransfer();
  dt.items.add(mappedFile);
  fileInput.files = dt.files;
  fileInput.dispatchEvent(new Event('change', { bubbles:true }));
  const prepSelect = context?.row
    ? context.row.querySelector('.generation-controlnet-preprocessor')
    : document.getElementById('generation-controlnet-preprocessor');
  if (prepSelect) {
    prepSelect.value = 'none';
    prepSelect.dispatchEvent(new Event('change', { bubbles:true }));
  }
  const backendMessage = formatGenerationMapBackend(fileInput._neoPendingMapStatus || {});
  const message = `Map sent to ControlNet unit. Preprocessor switched to None so Neo uses this generated map directly. · ${backendMessage}`;
  if (context.summary) context.summary.textContent = message;
  setStatus('generation-status', message, 'success');
}

function downloadPendingGenerationControlnetMap(context) {
  const fileInput = context?.fileInput;
  const dataUrl = String(fileInput?._neoPendingMapDataUrl || '');
  const mappedFile = fileInput?._neoPendingMapFile;
  if (!dataUrl) {
    setStatus('generation-status', 'Generate a map preview first before downloading.', 'warn');
    return;
  }
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = mappedFile?.name || 'control_map.png';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function parseGenerationTagAssistCaption(text='') {
  const seen = new Set();
  return String(text || '')
    .replace(/\n+/g, ',')
    .split(',')
    .map(item => String(item || '').trim())
    .filter(Boolean)
    .filter(tag => {
      const key = tag.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function generationTagAssistSelectionIndexes() {
  return Array.from(generationTagAssistState.selected || []).map(value => Number(value)).filter(Number.isFinite);
}

function generationTagAssistSelectedTags() {
  return generationTagAssistSelectionIndexes()
    .map(index => generationTagAssistState.tags[index])
    .filter(Boolean);
}

function setGenerationTagAssistStatus(message, tone='') {
  const el = $('generation-tagassist-status');
  if (el) {
    el.textContent = message || 'No Tag Assist run yet.';
    el.className = `mini-note${tone ? ` status-${tone}` : ''}`;
  }
}

function renderGenerationTagAssistResults() {
  const wrap = $('generation-tagassist-results');
  if (!wrap) return;
  wrap.innerHTML = '';
  const tags = Array.isArray(generationTagAssistState.tags) ? generationTagAssistState.tags : [];
  if (!tags.length) {
    const empty = document.createElement('div');
    empty.className = 'mini-note';
    empty.textContent = generationTagAssistState.caption ? 'Tag Assist finished, but no clean tags were detected.' : 'No Tag Assist results yet.';
    wrap.appendChild(empty);
    return;
  }
  tags.forEach((tag, index) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-small';
    btn.textContent = tag;
    const active = generationTagAssistState.selected instanceof Set && generationTagAssistState.selected.has(index);
    if (active) btn.classList.add('btn-primary');
    btn.addEventListener('click', () => {
      if (!(generationTagAssistState.selected instanceof Set)) generationTagAssistState.selected = new Set();
      if (generationTagAssistState.selected.has(index)) generationTagAssistState.selected.delete(index);
      else generationTagAssistState.selected.add(index);
      renderGenerationTagAssistResults();
    });
    wrap.appendChild(btn);
  });
  const selectedCount = generationTagAssistSelectedTags().length;
  setGenerationTagAssistStatus(selectedCount
    ? `${selectedCount} tag${selectedCount === 1 ? '' : 's'} selected.`
    : `${tags.length} tag${tags.length === 1 ? '' : 's'} ready. Click tags to choose what gets inserted.`, selectedCount ? 'success' : '');
}

function appendGenerationTagAssistSelection(target='positive') {
  const tags = generationTagAssistSelectedTags().length ? generationTagAssistSelectedTags() : (Array.isArray(generationTagAssistState.tags) ? generationTagAssistState.tags.slice() : []);
  if (!tags.length) {
    setStatus('generation-status', 'Run Tag Assist first so Neo has tags to insert.', 'warn');
    return;
  }
  const field = target === 'negative' ? $('generation-negative') : $('generation-positive');
  if (!field) return;
  const existing = String(field.value || '').trim();
  const merged = existing ? `${existing}${existing.endsWith(',') ? '' : ','} ${tags.join(', ')}` : tags.join(', ');
  field.value = merged;
  field.dispatchEvent(new Event('input', { bubbles:true }));
  setGenerationTagAssistStatus(`Inserted ${tags.length} tag${tags.length === 1 ? '' : 's'} into the ${target} prompt.`, 'success');
  scheduleGenerationDraftSave();
}

async function copyGenerationTagAssistTags() {
  const tags = generationTagAssistSelectedTags().length ? generationTagAssistSelectedTags() : (Array.isArray(generationTagAssistState.tags) ? generationTagAssistState.tags.slice() : []);
  if (!tags.length) {
    setStatus('generation-status', 'Run Tag Assist first so there is something to copy.', 'warn');
    return;
  }
  const text = tags.join(', ');
  try {
    await navigator.clipboard.writeText(text);
    setGenerationTagAssistStatus(`Copied ${tags.length} tag${tags.length === 1 ? '' : 's'} to the clipboard.`, 'success');
  } catch (_) {
    setGenerationTagAssistStatus('Could not copy the tags automatically. Select and copy them manually.', 'warn');
  }
}

async function runGenerationTagAssist() {
  const helperFile = $('generation-tagassist-image')?.files?.[0] || null;
  const sourceFile = $('generation-source-image')?.files?.[0] || null;
  const file = helperFile || sourceFile;
  if (!file) {
    setStatus('generation-status', 'Load a helper image or source image first so Tag Assist has something to analyze.', 'warn');
    return;
  }
  const threshold = String($('generation-tagassist-threshold')?.value || '0.35').trim() || '0.35';
  const filterTags = String($('generation-tagassist-filter')?.value || '').trim();
  const longTaskRunner = window.NeoGenerationLongTasks?.runPollingTask;
  if (typeof longTaskRunner !== 'function') {
    setStatus('generation-status', 'The long-task runner is not available yet. Reload Neo and try again.', 'error');
    return;
  }
  const fd = new FormData();
  fd.append('threshold', threshold);
  fd.append('filter_tags', filterTags);
  fd.append('image', file, file.name || 'tagassist.png');

  generationTagAssistState = { caption:'', tags:[], selected: new Set(), lastImageName: file.name || '' };
  renderGenerationTagAssistResults();
  $('btn-generation-tagassist-run') && ($('btn-generation-tagassist-run').disabled = true);

  const setProgressMessage = (message, tone='') => {
    $('generation-tagassist-note') && ($('generation-tagassist-note').textContent = helperFile
      ? `Using helper image: ${file.name || 'image'}`
      : `Using the current source image: ${file.name || 'image'}`);
    setGenerationTagAssistStatus(message, tone);
    setStatus('generation-status', message, tone);
  };

  try {
    setProgressMessage('Starting Tag Assist…');
    await longTaskRunner({
      startUrl: '/api/generation/tag-assist/start',
      buildStatusUrl: jobId => `/api/generation/tag-assist/status/${encodeURIComponent(jobId)}`,
      startOptions: { method:'POST', body: fd },
      pollFetch: safeFetchJson,
      startFetch: safeFetchJson,
      pollIntervalMs: 1200,
      onProgress: message => setProgressMessage(message),
      onCompleted: async status => {
        const caption = String(status.caption || '').trim();
        const tags = Array.isArray(status.tags) && status.tags.length ? status.tags : parseGenerationTagAssistCaption(caption);
        generationTagAssistState = {
          caption,
          tags,
          selected: new Set(tags.map((_, index) => index)),
          lastImageName: file.name || '',
        };
        renderGenerationTagAssistResults();
        setGenerationTagAssistStatus(`Tag Assist finished with ${tags.length} tag${tags.length === 1 ? '' : 's'}.`, 'success');
      },
      onSoftTimeout: async status => {
        const message = String(status.message || 'Tag Assist is still running in the backend.').trim();
        setProgressMessage(message, 'warn');
      },
      onError: async (error, payload) => {
        const message = String(payload?.message || error?.message || 'Could not run Tag Assist.').trim();
        setProgressMessage(message, 'error');
      },
    });
  } catch (e) {
    const message = e?.message || 'Could not run Tag Assist.';
    setProgressMessage(message, 'error');
    throw e;
  } finally {
    $('btn-generation-tagassist-run') && ($('btn-generation-tagassist-run').disabled = false);
  }
}



// Phase 3.1 ControlNet UI correction: specific depth models live in Preprocessor.
const neoDepthPreprocessorItems = [
  { value: 'depth_midas', label: 'Depth / MiDaS (Forge-style)' },
  { value: 'depth_anything_v2', label: 'Depth / DepthAnythingV2' },
  { value: 'depth_anything', label: 'Depth / DepthAnything' },
  { value: 'depth_zoe', label: 'Depth / ZoeDepth' },
  { value: 'depth_leres', label: 'Depth / LeReS' },
  { value: 'depth_leres++', label: 'Depth / LeReS++' },
];
const neoControlnetPreprocessorItemsByUnit = {
  auto: [
    { value: 'none', label: 'None' },
    { value: 'canny', label: 'Canny' },
    { value: 'softedge', label: 'SoftEdge / HED' },
    { value: 'lineart', label: 'Lineart' },
    { value: 'lineart_anime', label: 'Lineart Anime' },
    { value: 'scribble', label: 'Scribble / Sketch' },
    { value: 'openpose', label: 'OpenPose / DWPose' },
    ...neoDepthPreprocessorItems,
    { value: 'normalbae', label: 'NormalBae' },
    { value: 'tile', label: 'Tile / Detail' },
  ],
  canny: [
    { value: 'none', label: 'None / use current map directly' },
    { value: 'canny', label: 'Canny / Auto' },
    { value: 'canny_edge', label: 'Canny / Aux Edge node' },
    { value: 'canny_standard', label: 'Canny / Standard node' },
  ],
  softedge: [{ value: 'none', label: 'None / use current map directly' }, { value: 'softedge', label: 'SoftEdge / HED' }],
  lineart: [{ value: 'none', label: 'None / use current map directly' }, { value: 'lineart', label: 'Lineart' }, { value: 'lineart_anime', label: 'Lineart Anime' }],
  scribble: [{ value: 'none', label: 'None / use current map directly' }, { value: 'scribble', label: 'Scribble / Sketch' }],
  openpose: [{ value: 'none', label: 'None / use current map directly' }, { value: 'openpose', label: 'OpenPose / DWPose' }],
  depth: [{ value: 'none', label: 'None / use current map directly' }, ...neoDepthPreprocessorItems],
  normalbae: [{ value: 'none', label: 'None / use current map directly' }, { value: 'normalbae', label: 'NormalBae' }],
  tile: [{ value: 'tile', label: 'Tile / Detail' }, { value: 'none', label: 'None / use image directly' }],
};
function neoControlnetUnitKey(value) {
  const key = String(value || 'auto').trim().toLowerCase();
  if (key.includes('depth')) return 'depth';
  if (key.includes('openpose') || key.includes('dwpose') || key.includes('pose')) return 'openpose';
  if (key.includes('soft') || key.includes('hed')) return 'softedge';
  if (key.includes('lineart') || key.includes('line')) return 'lineart';
  if (key.includes('scribble') || key.includes('sketch')) return 'scribble';
  if (key.includes('normal')) return 'normalbae';
  if (key.includes('tile')) return 'tile';
  if (key.includes('canny')) return 'canny';
  return key || 'auto';
}
function neoSetPreprocessorOptions(select, unitValue) {
  if (!select) return;
  const current = String(select.value || '').trim();
  const rows = neoControlnetPreprocessorItemsByUnit[neoControlnetUnitKey(unitValue)] || neoControlnetPreprocessorItemsByUnit.auto;
  select.innerHTML = '';
  rows.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.value;
    opt.textContent = item.label;
    if (current && current === item.value) opt.selected = true;
    select.appendChild(opt);
  });
  if (!select.value && rows.length) select.value = rows[0].value;
}
function neoHideLegacyDepthModelFields(root=document) {
  root.querySelectorAll('.generation-controlnet-depth-model, #generation-controlnet-depth-model').forEach(el => {
    const wrap = el.closest('div') || el.parentElement;
    if (wrap) wrap.style.display = 'none';
  });
}
function refreshPrimaryGenerationControlnetPreprocessorFilter() {
  neoSetPreprocessorOptions($('generation-controlnet-preprocessor'), $('generation-controlnet-unit')?.value || 'auto');
  neoHideLegacyDepthModelFields(document);
}
function refreshGenerationControlnetPreprocessorFilterForRow(row) {
  if (!row) return;
  neoSetPreprocessorOptions(row.querySelector('.generation-controlnet-preprocessor'), row.querySelector('.generation-controlnet-unit')?.value || 'auto');
  neoHideLegacyDepthModelFields(row);
}
function refreshPrimaryGenerationControlnetModelFilter() { try { updatePrimaryGenerationControlnetSummary(); } catch (_) {} }
function refreshGenerationControlnetModelFilterForRow(row) { try { updateGenerationControlnetRowSummary(row); } catch (_) {} }
document.addEventListener('change', event => {
  const target = event.target;
  if (!target?.matches?.('#generation-controlnet-unit, .generation-controlnet-unit')) return;
  const row = target.closest('.generation-controlnet-row');
  if (row) refreshGenerationControlnetPreprocessorFilterForRow(row);
  else refreshPrimaryGenerationControlnetPreprocessorFilter();
});
setTimeout(() => {
  refreshPrimaryGenerationControlnetPreprocessorFilter();
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(refreshGenerationControlnetPreprocessorFilterForRow);
  neoHideLegacyDepthModelFields(document);
}, 0);

async function buildGenerationControlnetMap({ row=null } = {}) {
  const context = getGenerationControlnetContext(row);
  const mode = String(context.preprocessor || 'none').trim().toLowerCase();
  const buildableModes = ['canny', 'canny_edge', 'canny_standard', 'softedge', 'lineart', 'lineart_anime', 'scribble', 'openpose', 'depth', 'depth_midas', 'depth_anything_v2', 'depth_anything', 'depth_zoe', 'depth_leres', 'depth_leres++', 'normalbae'];
  if (!buildableModes.includes(mode)) {
    setStatus('generation-status', 'Pick a buildable Aux preprocessor first: Canny, SoftEdge, Lineart, Lineart Anime, Scribble, OpenPose, Depth, or NormalBae. Tile uses the source image directly.', 'warn');
    return;
  }
  const controlFile = context.fileInput?.files?.[0] || null;
  const sourceFile = $('generation-source-image')?.files?.[0] || null;
  const file = controlFile || sourceFile;
  if (!file) {
    setStatus('generation-status', 'Load a source image or control image first so Neo has something to turn into a map.', 'warn');
    return;
  }
  const longTaskRunner = window.NeoGenerationLongTasks?.runPollingTask;
  if (typeof longTaskRunner !== 'function') {
    setStatus('generation-status', 'The long-task runner is not available yet. Reload Neo and try again.', 'error');
    return;
  }
  const fd = new FormData();
  // Send the exact selected preprocessor value. The backend normalizes aliases,
  // but keeping depth_midas/depth_zoe/etc. prevents Neo from silently falling
  // back to DepthAnythingV2 when the user picked a specific depth mode.
  fd.append('mode', mode);
  fd.append('image', file, file.name || `${mode}.png`);
  if (context.uid) fd.append('uid', context.uid);
  const settingsRoot = context.row || document;
  const readSetting = (selector, fallback='') => {
    const el = settingsRoot.querySelector ? settingsRoot.querySelector(selector) : null;
    return el ? String(el.value ?? fallback) : String(fallback);
  };
  const readChecked = (selector, fallback=true) => {
    const el = settingsRoot.querySelector ? settingsRoot.querySelector(selector) : null;
    return el ? (el.checked ? 'true' : 'false') : (fallback ? 'true' : 'false');
  };
  fd.append('detect_resolution', readSetting('.generation-controlnet-detect-resolution, #generation-controlnet-detect-resolution', '768'));
  fd.append('safe_mode', readSetting('.generation-controlnet-safe-mode, #generation-controlnet-safe-mode', 'true'));
  fd.append('canny_low', readSetting('.generation-controlnet-canny-low, #generation-controlnet-canny-low', '100'));
  fd.append('canny_high', readSetting('.generation-controlnet-canny-high, #generation-controlnet-canny-high', '200'));
  fd.append('openpose_body', readChecked('.generation-controlnet-openpose-body, #generation-controlnet-openpose-body', true));
  fd.append('openpose_hand', readChecked('.generation-controlnet-openpose-hand, #generation-controlnet-openpose-hand', true));
  fd.append('openpose_face', readChecked('.generation-controlnet-openpose-face, #generation-controlnet-openpose-face', false));
  fd.append('invert_map', readChecked('.generation-controlnet-invert-map, #generation-controlnet-invert-map', false));
  fd.append('save_intermediate', readChecked('.generation-controlnet-save-intermediate, #generation-controlnet-save-intermediate', true));
  fd.append('fit_mode', readSetting('.generation-controlnet-fit-mode, #generation-controlnet-fit-mode', 'contain'));
  fd.append('start_percent', readSetting('.generation-controlnet-start-percent, #generation-controlnet-start-percent', '0'));
  fd.append('end_percent', readSetting('.generation-controlnet-end-percent, #generation-controlnet-end-percent', '1'));
  fd.append('depth_model', mode.startsWith('depth_') ? mode : 'auto');

  const setProgressMessage = (message, tone='') => {
    if (context.note) context.note.textContent = message;
    if (context.summary) context.summary.textContent = message;
    setStatus('generation-status', message, tone);
  };

  try {
    setProgressMessage(`Starting ${mode} map build…`);
    await longTaskRunner({
      startUrl: '/api/generation/controlnet/build-map/start',
      buildStatusUrl: jobId => `/api/generation/controlnet/build-map/status/${encodeURIComponent(jobId)}`,
      startOptions: { method:'POST', body: fd },
      pollFetch: safeFetchJson,
      startFetch: safeFetchJson,
      pollIntervalMs: 1200,
      onProgress: message => setProgressMessage(message),
      onCompleted: async status => {
        const fileInput = context.fileInput;
        if (!fileInput) throw new Error('Control image input is missing.');
        const mappedFile = fileFromBase64DataUrl(String(status.preview_data_url || ''), status.filename || `${mode}_map.png`);
        renderGenerationControlnetPreviewFirst(context, file, status, mappedFile);
        const finalMessage = Array.isArray(status.notes) && status.notes.length ? String(status.notes[0] || '') : `${mode} map preview built.`;
        const backendMessage = formatGenerationMapBackend(status);
        if (context.note) context.note.textContent = backendMessage;
        if (context.summary) context.summary.textContent = `${finalMessage} · Preview ready — review it, then click “Send map to this ControlNet unit”. · ${backendMessage}`;
        setStatus('generation-status', `${finalMessage} Review the before/after preview, then send it to the ControlNet unit. · ${backendMessage}`, 'success');
      },
      onSoftTimeout: async status => {
        const message = String(status.message || `${mode} map is still running in the backend.`).trim();
        setProgressMessage(message, 'warn');
      },
      onError: async (error, payload) => {
        const message = String(payload?.message || error?.message || `Could not build ${mode} map.`).trim();
        setProgressMessage(message, 'error');
      },
    });
  } catch (e) {
    const message = e?.message || `Could not build ${mode} map.`;
    setProgressMessage(message, 'error');
    throw e;
  }
}


function formatGenerationMapBackend(status={}) {
  const backend = String(status.backend || '').trim().toLowerCase();
  const node = String(status.node_name || '').trim();
  const fallback = !!status.fallback;
  if (backend === 'comfy_aux') return `Last map backend: ComfyUI Aux${node ? ` (${node})` : ''}${fallback ? ' fallback' : ''}`;
  if (backend === 'opencv' || backend === 'local_opencv') return `Last map backend: OpenCV fallback${node ? ` (${node})` : ''}`;
  if (backend === 'local') return `Last map backend: Local fallback${node ? ` (${node})` : ''}`;
  return node ? `Last map backend: ${node}` : 'Last map backend: unknown';
}

function createGenerationIpAdapterRow(values={}) {
  generationIpAdapterRowCounter += 1;
  const uid = values.uid || `ipadapter_${generationIpAdapterRowCounter}`;
  const row = document.createElement('div');
  row.className = 'grid grid-5 generation-dynamic-row generation-ipadapter-row generation-unit-card generation-unit-card-ipadapter';
  row.dataset.uid = uid;
  row.innerHTML = `
    <div class="generation-unit-topbar" style="grid-column:1 / -1;">
      <div class="generation-unit-heading">
        <span class="generation-unit-index">00</span>
        <div>
          <div class="generation-unit-title">IP-Adapter unit</div>
          <div class="accordion-hint">Each row carries its own reference image, CLIP Vision encoder, and either a standard IP-Adapter model or a FaceID preset.</div>
        </div>
      </div>
      <div class="generation-unit-actions">
        <label class="generation-toggle-pill"><input class="generation-unit-enabled" type="checkbox" ${values.enabled === false ? '' : 'checked'} /> Enabled</label>
        <button class="btn btn-small generation-row-move-up" type="button" title="Move this IP-Adapter row up">↑</button>
        <button class="btn btn-small generation-row-move-down" type="button" title="Move this IP-Adapter row down">↓</button>
        <button class="btn btn-small generation-remove-row" type="button" title="Remove this IP-Adapter row">Remove</button>
      </div>
    </div>
    <div>
      <label>Mode</label>
      <select class="generation-ipadapter-mode"><option value="standard">Standard</option><option value="faceid">FaceID / FaceID Plus</option></select>
    </div>
    <div>
      <label>IP-Adapter model</label>
      <select class="generation-ipadapter-name"><option value="">None</option></select>
    </div>
    <div>
      <label>CLIP Vision</label>
      <select class="generation-ipadapter-clip-vision"><option value="">None</option></select>
    </div>
    <div>
      <label>FaceID preset</label>
      <select class="generation-ipadapter-faceid-preset"><option value="FACEID PLUS V2">FACEID PLUS V2</option></select>
    </div>
    <div>
      <label>InsightFace provider</label>
      <select class="generation-ipadapter-faceid-provider"><option value="CUDA">CUDA</option></select>
    </div>
    <div class="generation-faceid-lora-global-note">
      <label>FaceID LoRA strength</label>
      <div class="mini-note">Uses Identity Presets global value.</div>
      <input class="generation-ipadapter-faceid-lora-strength" type="hidden" value="${Number(values.faceid_lora_strength ?? 0.75)}" />
    </div>
    <div>
      <label>Weight</label>
      <input class="generation-ipadapter-weight" type="number" step="0.05" value="${Number(values.weight ?? 1.0)}" />
    </div>
    <div>
      <label>FaceID V2 weight</label>
      <input class="generation-ipadapter-weight-faceidv2" type="number" step="0.05" value="${Number(values.weight_faceidv2 ?? 1.0)}" />
    </div>
    <div>
      <label>Weight type</label>
      <select class="generation-ipadapter-weight-type"><option value="linear">Linear</option></select>
    </div>
    <div>
      <label>Reference image</label>
      <input class="generation-ipadapter-image" type="file" accept="image/*" multiple />
    </div>
    <div>
      <label>Combine embeds</label>
      <select class="generation-ipadapter-combine-embeds"><option value="concat">Concat</option></select>
    </div>
    <div>
      <label>Embeds scaling</label>
      <select class="generation-ipadapter-embeds-scaling"><option value="V only">V only</option></select>
    </div>
    <div>
      <label>Start at</label>
      <input class="generation-ipadapter-start-at" type="number" min="0" max="1" step="0.01" value="${Number(values.start_at ?? 0.0)}" />
    </div>
    <div>
      <label>End at</label>
      <input class="generation-ipadapter-end-at" type="number" min="0" max="1" step="0.01" value="${Number(values.end_at ?? 1.0)}" />
    </div>
    <div class="mini-note">Standard mode needs model + clip vision + one or more reference images. FaceID mode needs preset + provider + clip vision + one or more reference images.</div>
    
    <div class="generation-unit-preview-wrap" style="grid-column:1 / -1;">
      <div class="generation-unit-preview-card">
        <div class="generation-unit-preview-empty">No reference image yet for this unit.</div>
        <img class="generation-unit-preview-image hidden" alt="IP-Adapter unit preview" />
      </div>
      <div class="generation-unit-summary">Pick an IP-Adapter model or switch to FaceID mode.</div>
    </div>`;
  row.querySelector('.generation-remove-row')?.addEventListener('click', () => { row.remove(); updateGenerationUnitIndices(); scheduleGenerationDraftSave(); });
  row.querySelector('.generation-row-move-up')?.addEventListener('click', () => moveGenerationUnitRow(row, -1));
  row.querySelector('.generation-row-move-down')?.addEventListener('click', () => moveGenerationUnitRow(row, 1));
  row.querySelector('.generation-controlnet-build-map')?.addEventListener('click', () => buildGenerationControlnetMap({ row }));
  row.querySelector('.generation-controlnet-apply-map')?.addEventListener('click', () => applyPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelector('.generation-controlnet-download-map')?.addEventListener('click', () => downloadPendingGenerationControlnetMap(getGenerationControlnetContext(row)));
  row.querySelectorAll('input, select, textarea').forEach(el => {
    const eventName = el.tagName === 'SELECT' ? 'change' : (el.type === 'file' ? 'change' : 'input');
    el.addEventListener(eventName, () => {
      updateGenerationIpAdapterRowSummary(row);
      scheduleGenerationDraftSave();
    });
    if (el.type === 'checkbox') el.addEventListener('change', () => { updateGenerationIpAdapterRowSummary(row); scheduleGenerationDraftSave(); });
  });
  bindGenerationIpAdapterExplainers(row, row.querySelector('.generation-option-explainer'));
  refreshGenerationIpAdapterRowOptions(row);
  if (values.mode) row.querySelector('.generation-ipadapter-mode').value = values.mode;
  if (values.model) row.querySelector('.generation-ipadapter-name').value = values.model;
  if (values.clip_vision) row.querySelector('.generation-ipadapter-clip-vision').value = values.clip_vision;
  if (values.faceid_preset) row.querySelector('.generation-ipadapter-faceid-preset').value = values.faceid_preset;
  if (values.faceid_provider) row.querySelector('.generation-ipadapter-faceid-provider').value = values.faceid_provider;
  if (values.weight_type) row.querySelector('.generation-ipadapter-weight-type').value = values.weight_type;
  if (values.combine_embeds) row.querySelector('.generation-ipadapter-combine-embeds').value = values.combine_embeds;
  if (values.embeds_scaling) row.querySelector('.generation-ipadapter-embeds-scaling').value = values.embeds_scaling;
  updateGenerationIpAdapterOptionExplainer(row.querySelector('.generation-option-explainer'), 'mode', row.querySelector('.generation-ipadapter-mode')?.value || 'standard');
  updateGenerationIpAdapterRowSummary(row);
  return row;
}

function collectGenerationIpAdapterFiles() {
  const rows = [];
  const primaryEnabled = isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled'));
  const primaryFiles = Array.from($('generation-ipadapter-image')?.files || []);
  if (primaryEnabled && primaryFiles.length) primaryFiles.forEach(file => rows.push({ uid:'primary', file }));
  document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row').forEach(row => {
    if (!isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'))) return;
    const files = Array.from(row.querySelector('.generation-ipadapter-image')?.files || []);
    files.forEach(file => rows.push({ uid: row.dataset.uid || '', file }));
  });
  return rows.filter(item => item.uid && item.file);
}

function setGenerationSeedLock(locked) {
  const btn = $('btn-generation-seed-lock');
  if (!btn) return;
  const state = !!locked;
  btn.dataset.locked = state ? 'true' : 'false';
  btn.classList.toggle('is-active', state);
  btn.textContent = state ? '🔒' : '🔓';
  const label = state
    ? 'Seed is locked. Click to unlock it.'
    : 'Seed is unlocked. Click to lock the current seed.';
  btn.title = label;
  btn.setAttribute('aria-label', label);
  if (state) {
    const current = trim($('generation-seed')?.value || '');
    if (!current || current === '-1') $('generation-seed').value = generationLastUsedSeed || generationRandomSeed();
  }
}

function bindSyncedInputs(numberId, rangeId) {
  const num = $(numberId);
  const range = $(rangeId);
  if (!num || !range) return;
  const syncFrom = source => {
    const value = source.value;
    if (source !== num) num.value = value;
    if (source !== range) range.value = value;
  };
  num.addEventListener('input', () => syncFrom(num));
  range.addEventListener('input', () => syncFrom(range));
  syncFrom(num);
}

function addGenerationLoraRow(values={}) {
  $('generation-lora-extra-list')?.appendChild(createGenerationLoraRow(values));
  updateGenerationUnitIndices();
  scheduleGenerationDraftSave();
}

function addGenerationControlnetRow(values={}) {
  const list = $('generation-controlnet-extra-list');
  const row = createGenerationControlnetRow(values);
  list?.appendChild(row);
  normalizeGenerationControlnetExtraLayout(row);
  updateGenerationUnitIndices();
  scheduleGenerationDraftSave();
}

function addGenerationIpAdapterRow(values={}) {
  $('generation-ipadapter-extra-list')?.appendChild(createGenerationIpAdapterRow(values));
  updateGenerationUnitIndices();
  scheduleGenerationDraftSave();
}

function syncGenerationModeUI() {
  const mode = $('generation-workflow-type')?.value || 'txt2img';
  const source = $('generation-source-image');
  const mask = $('generation-mask-image');
  const usesSource = mode !== 'txt2img';
  const isInpaint = mode === 'inpaint';
  const isOutpaint = mode === 'outpaint';
  const usesMaskPanel = isInpaint || isOutpaint;
  if (source) source.disabled = !usesSource;
  if (mask) mask.disabled = !isInpaint;
  $('generation-source-wrap')?.classList.toggle('is-hidden', !usesSource);
  $('generation-mask-wrap')?.classList.toggle('is-hidden', !usesMaskPanel);
  $('generation-denoise-wrap')?.classList.toggle('is-hidden', mode === 'txt2img');
  $('generation-batch-size-wrap')?.classList.toggle('is-hidden', mode !== 'txt2img');
  $('generation-source-resize-mode')?.closest('div')?.classList.toggle('is-hidden', !usesSource);
  $('generation-inpaint-settings-wrap')?.classList.toggle('is-hidden', !isInpaint);
  $('generation-outpaint-wrap')?.classList.toggle('is-hidden', !isOutpaint);
  $('generation-mask-raw-accordion')?.classList.toggle('is-hidden', !isInpaint);
  $('btn-generation-source-edit-mask')?.classList.toggle('is-hidden', !isInpaint);
  $('btn-generation-source-clear-mask')?.classList.toggle('is-hidden', !isInpaint);
  updateGenerationSourceMaskOverlay();
  syncGenerationInpaintBackendUI();
}

const generationLanPaintUIPresets = {
  fast: { label:'Fast test', num_steps:2, prompt_mode:'Image First', lambda:4.0, step_size:0.25, beta:1.0, friction:10.0, early_stop:1, note:'Fast test: depth 2 for quick mask checks.' },
  balanced: { label:'Balanced', num_steps:5, prompt_mode:'Image First', lambda:6.0, step_size:0.25, beta:1.0, friction:12.0, early_stop:2, note:'Balanced: depth 5, Image First, lambda 6, friction 12.' },
  hard_repair: { label:'Hard repair', num_steps:8, prompt_mode:'Image First', lambda:8.0, step_size:0.22, beta:1.0, friction:16.0, early_stop:3, note:'Hard repair: deeper thinking with stronger content alignment and stability.' },
  character_match: { label:'Character match', num_steps:5, prompt_mode:'Prompt First', lambda:6.0, step_size:0.22, beta:1.0, friction:14.0, early_stop:2, note:'Character match: Prompt First with steadier friction for identity/detail prompts.' },
};

function applyGenerationLanPaintPreset(key) {
  const preset = generationLanPaintUIPresets[String(key || '').trim()];
  if (!preset) return false;
  const mapping = {
    'generation-lanpaint-num-steps': preset.num_steps,
    'generation-lanpaint-prompt-mode': preset.prompt_mode,
    'generation-lanpaint-lambda': preset.lambda,
    'generation-lanpaint-step-size': preset.step_size,
    'generation-lanpaint-beta': preset.beta,
    'generation-lanpaint-friction': preset.friction,
    'generation-lanpaint-early-stop': preset.early_stop,
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const el = $(id);
    if (!el) return;
    el.value = String(value);
  });
  return true;
}

function readGenerationLanPaintUISettings() {
  const readNumber = (id, fallback) => {
    const value = Number($(id)?.value);
    return Number.isFinite(value) ? value : fallback;
  };
  return {
    num_steps: Math.round(readNumber('generation-lanpaint-num-steps', 5)),
    prompt_mode: $('generation-lanpaint-prompt-mode')?.value || 'Image First',
    lambda: readNumber('generation-lanpaint-lambda', 6.0),
    step_size: readNumber('generation-lanpaint-step-size', 0.25),
    beta: readNumber('generation-lanpaint-beta', 1.0),
    friction: readNumber('generation-lanpaint-friction', 12.0),
    early_stop: Math.round(readNumber('generation-lanpaint-early-stop', 2)),
  };
}

function syncGenerationLanPaintPanelUI() {
  const mode = String($('generation-workflow-type')?.value || 'txt2img').trim().toLowerCase();
  const family = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || 'sdxl_sd').trim().toLowerCase();
  const backend = String($('generation-inpaint-backend')?.value || 'standard').trim().toLowerCase();
  const panel = $('generation-lanpaint-settings-panel');
  const badge = $('generation-lanpaint-active-badge');
  const status = $('generation-lanpaint-status-note');
  const effective = $('generation-lanpaint-effective-note');
  const active = mode === 'inpaint' && backend === 'lanpaint' && (family === 'sdxl_sd' || family === 'qwen_image_edit');
  panel?.classList.toggle('is-hidden', !active);
  if (badge) {
    badge.textContent = active ? 'Active' : 'Inactive';
    badge.classList.toggle('is-disabled', !active);
  }
  if (status) {
    if (!active) status.textContent = 'LanPaint settings are hidden until Inpaint + LanPaint is active.';
    else if (family === 'qwen_image_edit') status.textContent = 'Qwen LanPaint route active. These controls are payload-ready; sampler node wiring lands in the next integration phase.';
    else status.textContent = 'SDXL LanPaint route active. These controls are payload-ready; workflow node wiring lands in the next integration phase.';
  }
  if (effective) {
    const v = readGenerationLanPaintUISettings();
    effective.textContent = active
      ? `Effective UI state: depth ${v.num_steps}, ${v.prompt_mode}, lambda ${v.lambda}, step size ${v.step_size}, beta ${v.beta}, friction ${v.friction}, early stop ${v.early_stop}.`
      : 'Balanced defaults stay staged until LanPaint is selected.';
  }
}

function syncGenerationInpaintBackendUI() {
  const mode = $('generation-workflow-type')?.value || 'txt2img';
  const family = window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || 'sdxl_sd';
  const backend = $('generation-inpaint-backend');
  const backendNote = $('generation-inpaint-backend-note');
  const guideWrap = $('generation-composition-guide-wrap');
  const guideSourceWrap = $('generation-composition-source-wrap');
  const guideType = $('generation-composition-guide-type');
  const guideNote = $('generation-composition-guide-note');
  const isInpaint = mode === 'inpaint';
  const isQwen = family === 'qwen_image_edit';
  const lanpaintOption = backend?.querySelector('option[value="lanpaint"]');
  const standardOption = backend?.querySelector('option[value="standard"]');
  if (backend) {
    backend.closest('.grid')?.classList.toggle('is-hidden', !isInpaint);
    backend.disabled = !isInpaint;
    if (!isInpaint && backend.value !== 'standard') {
      backend.value = 'standard';
    }
    if (standardOption) standardOption.disabled = isQwen && isInpaint;
    if (lanpaintOption) lanpaintOption.disabled = !(family === 'sdxl_sd' || family === 'qwen_image_edit');
    if (isQwen && isInpaint) {
      backend.value = 'lanpaint';
      backend.disabled = true;
      if (backendNote) backendNote.textContent = 'Qwen inpaint now runs through the base LanPaint branch. Composition guides are live here. Outpaint still stays staged for a later phase.';
    } else if (family === 'sdxl_sd' && isInpaint) {
      if (backendNote) backendNote.textContent = 'SDXL inpaint supports Standard and LanPaint. Standard uses the classic latent mask path; LanPaint uses the live LanPaint_KSampler branch and will validate sampler compatibility before queueing.';
    } else if (backendNote) {
      backendNote.textContent = 'Inpaint backend only matters on a live inpaint-capable family.';
    }
  }
  const showGuide = isInpaint && isQwen;
  guideWrap?.classList.toggle('is-hidden', !showGuide);
  guideSourceWrap?.classList.toggle('is-hidden', !showGuide);
  if (guideNote) {
    const sourceMode = $('generation-composition-source-mode')?.value || 'source_image';
    const guideKind = guideType?.value || 'none';
    if (showGuide && guideKind === 'none') {
      guideNote.textContent = sourceMode === 'composition_image'
        ? 'Qwen inpaint will feed image3 directly into the composition slot with no depth / pose preprocessing.'
        : 'Qwen inpaint will keep image3 tied to the base image unless you switch the source to the dedicated composition image.';
    } else {
      guideNote.textContent = showGuide
        ? 'Qwen inpaint can route image3 through a raw composition image, a depth map, or a pose map before prompting.'
        : 'Composition guides stay hidden until a real backend branch exposes them.';
    }
  }
  if (!showGuide && guideType) guideType.value = 'none';
  syncGenerationLanPaintPanelUI();
}

function generationUpscaleLabProfileLabel(profileId='custom') {
  const key = String(profileId || 'custom').trim();
  if (key === 'custom') return 'Custom';
  return generationUpscaleLabProfiles[key]?.label || 'Custom';
}

function inferGenerationUpscalerNativeScale(name='') {
  const match = String(name || '').trim().toLowerCase().match(/(^|[^\d])(\d+(?:\.\d+)?)x(?!\d)/);
  if (!match) return 1;
  const value = Number(match[2]);
  if (!Number.isFinite(value) || value <= 0) return 1;
  return Math.max(0.1, Math.min(value, 16));
}

function updateGenerationUpscaleLabSummary() {
  const target = $('generation-refine-lab-summary');
  if (!target) return;
  const enabled = String($('generation-refine-enabled')?.value || 'false') === 'true';
  const profile = $('generation-refine-profile')?.value || 'custom';
  const strategy = $('generation-refine-strategy')?.value || 'standard';
  const mode = $('generation-refine-mode')?.value || 'latent';
  const scale = String($('generation-refine-scale')?.value || '1.5').trim() || '1.5';
  const steps = String($('generation-refine-steps')?.value || '12').trim() || '12';
  const denoise = String($('generation-refine-denoise')?.value || '0.12').trim() || '0.12';
  const upscaler = trim($('generation-refine-upscaler')?.selectedOptions?.[0]?.textContent || $('generation-refine-upscaler')?.value || '');
  if (!enabled) {
    target.textContent = 'Upscale Lab is off. Turn it on when the base image already works and you just want a cleaner larger finish.';
    return;
  }
  const modeLabel = strategy === 'qwen_reedit' ? 'Qwen re-edit' : (mode === 'image_upscale' ? 'Image upscale + preserve' : 'Latent upscale + refine');
  const bits = [generationUpscaleLabProfileLabel(profile), modeLabel, `${scale}×`, `${steps} steps`, `denoise ${denoise}`];
  if (strategy !== 'qwen_reedit' && mode === 'image_upscale' && upscaler) {
    const nativeScale = inferGenerationUpscalerNativeScale(upscaler);
    bits.push(nativeScale > 1 ? `${upscaler} (${nativeScale}× native → target ${scale}×)` : upscaler);
  }
  target.textContent = bits.join(' · ');
}

function applyGenerationUpscaleLabProfile(profileId, options={}) {
  const key = String(profileId || 'custom').trim();
  if (key === 'custom' || !generationUpscaleLabProfiles[key]) {
    updateGenerationUpscaleLabSummary();
    return;
  }
  const profile = generationUpscaleLabProfiles[key];
  if ($('generation-refine-profile')) $('generation-refine-profile').value = key;
  if ($('generation-refine-enabled')) $('generation-refine-enabled').value = profile.enabled;
  const activeFamily = window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '';
  if ($('generation-refine-strategy')) $('generation-refine-strategy').value = activeFamily === 'qwen_image_edit' ? 'qwen_reedit' : 'standard';
  if ($('generation-refine-mode')) $('generation-refine-mode').value = activeFamily === 'qwen_image_edit' ? 'image_upscale' : profile.mode;
  if ($('generation-refine-resize-method')) $('generation-refine-resize-method').value = profile.resize_method;
  if ($('generation-refine-scale')) $('generation-refine-scale').value = profile.scale;
  if ($('generation-refine-scale-range')) $('generation-refine-scale-range').value = profile.scale;
  if ($('generation-refine-steps')) $('generation-refine-steps').value = profile.steps;
  if ($('generation-refine-steps-range')) $('generation-refine-steps-range').value = profile.steps;
  if ($('generation-refine-denoise')) $('generation-refine-denoise').value = profile.denoise;
  if ($('generation-refine-denoise-range')) $('generation-refine-denoise-range').value = profile.denoise;
  if ($('generation-refine-cfg')) $('generation-refine-cfg').value = profile.cfg;
  if ($('generation-refine-sampler')) $('generation-refine-sampler').value = profile.sampler;
  if ($('generation-refine-scheduler')) $('generation-refine-scheduler').value = profile.scheduler;
  if ($('generation-refine-tiled-vae')) $('generation-refine-tiled-vae').value = profile.tiled_vae;
  if ($('generation-refine-tile-size')) $('generation-refine-tile-size').value = profile.tile_size;
  if ($('generation-refine-tile-overlap')) $('generation-refine-tile-overlap').value = profile.tile_overlap;
  if ($('generation-refine-upscaler')) $('generation-refine-upscaler').value = profile.upscaler;
  syncGenerationRefineUI();
  updateGenerationUpscaleLabSummary();
  if (!options.silent) scheduleGenerationDraftSave();
}

function markGenerationUpscaleLabCustom() {
  if ($('generation-refine-profile') && $('generation-refine-profile').value !== 'custom') $('generation-refine-profile').value = 'custom';
  updateGenerationUpscaleLabSummary();
  renderGenerationFinishFoundation();
}

function updateGenerationCleanupSummary() {
  // Cleanup workflows are owned by Inpaint controls and the Mask Editor.
}

function prepareGenerationCleanupWorkflow() {
  if ($('generation-workflow-type')) $('generation-workflow-type').value = 'inpaint';
  if ($('generation-inpaint-target')) $('generation-inpaint-target').value = 'masked';
  if ($('generation-inpaint-context')) $('generation-inpaint-context').value = 'full_image';
  syncGenerationModeUI();
  scheduleGenerationDraftSave();
  setStatus('generation-status', 'Inpaint controls and the Mask Editor are ready for object removal or local repair.', 'info');
}

function syncGenerationCleanupUI() {
  // Compatibility shim for older call sites; intentionally no UI side effects.
}

function updateGenerationIdentitySummary() {
  const target = $('generation-identity-summary');
  if (!target) return;
  const goal = $('generation-identity-goal')?.value || 'off';
  const route = $('generation-identity-route')?.value || 'auto';
  const strength = String($('generation-identity-strength')?.value || '0.85').trim() || '0.85';
  const faceidLora = String($('generation-identity-faceid-lora')?.value || '0.75').trim() || '0.75';
  const startAt = String($('generation-identity-start')?.value || '0').trim() || '0';
  const endAt = String($('generation-identity-end')?.value || '1').trim() || '1';
  if (goal === 'off') {
    target.textContent = 'Identity presets are off. Pick a goal to stage IP-Adapter / FaceID reference routing.';
    return;
  }
  const goalLabel = goal === 'same_face'
    ? 'Same face'
    : (goal === 'same_character' ? 'Same character' : 'Style reference');
  const resolvedRoute = route === 'auto'
    ? (goal === 'same_face' ? 'ipadapter_faceid' : 'ipadapter_standard')
    : route;
  const routeLabel = resolvedRoute === 'ipadapter_faceid' ? 'IP-Adapter FaceID' : 'IP-Adapter standard';
  const extras = [];
  extras.push(`strength ${strength}`);
  if (resolvedRoute === 'ipadapter_faceid') extras.push(`FaceID LoRA ${faceidLora}`);
  extras.push(`window ${startAt} → ${endAt}`);
  target.textContent = `${goalLabel} · ${routeLabel} · ${extras.join(' · ')}`;
}

function ensureGenerationAssignFileToInput(inputId, file) {
  const input = $(inputId);
  if (!input || !file) return false;
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles:true }));
  return true;
}

if (typeof window.assignFileToInput !== 'function' && typeof assignFileToInput === 'undefined') {
  window.assignFileToInput = ensureGenerationAssignFileToInput;
}

async function useGenerationSourceAsIdentityReference() {
  const sourceInput = $('generation-source-image');
  const targetInput = $('generation-ipadapter-image');
  const file = sourceInput?.files?.[0];
  if (!sourceInput || !targetInput || !file) {
    setStatus('generation-status', 'Load a source image first so Neo has something to copy into the identity/reference lane.', 'warn');
    return false;
  }
  assignFileToInput('generation-ipadapter-image', file);
  updatePrimaryGenerationIpAdapterSummary();
  scheduleGenerationDraftSave();
  setStatus('generation-status', 'Copied the current source image into the primary IP-Adapter reference slot.', 'success');
  return true;
}

async function prepareGenerationIdentityWorkflow() {
  const goal = $('generation-identity-goal')?.value || 'off';
  if (goal === 'off') {
    setStatus('generation-status', 'Pick an identity preset goal first so Neo knows whether to stage same-face, same-character, or style-reference routing.', 'warn');
    return;
  }
  const requestedRoute = $('generation-identity-route')?.value || 'auto';
  const route = requestedRoute === 'auto'
    ? (goal === 'same_face' ? 'ipadapter_faceid' : 'ipadapter_standard')
    : requestedRoute;
  const strength = String($('generation-identity-strength')?.value || '0.85').trim() || '0.85';
  const faceidLora = String($('generation-identity-faceid-lora')?.value || '0.75').trim() || '0.75';
  const startAt = String($('generation-identity-start')?.value || '0').trim() || '0';
  const endAt = String($('generation-identity-end')?.value || '1').trim() || '1';

  if ($('generation-ipadapter-enabled')) $('generation-ipadapter-enabled').checked = true;
  if ($('generation-ipadapter-mode')) $('generation-ipadapter-mode').value = route === 'ipadapter_faceid' ? 'faceid' : 'standard';
  if ($('generation-ipadapter-weight')) $('generation-ipadapter-weight').value = strength;
  if ($('generation-ipadapter-weight-faceidv2')) $('generation-ipadapter-weight-faceidv2').value = strength;
  if ($('generation-ipadapter-faceid-lora-strength')) $('generation-ipadapter-faceid-lora-strength').value = faceidLora;
  if ($('generation-ipadapter-start-at')) $('generation-ipadapter-start-at').value = startAt;
  if ($('generation-ipadapter-end-at')) $('generation-ipadapter-end-at').value = endAt;
  if ($('generation-ipadapter-weight-type')) $('generation-ipadapter-weight-type').value = goal === 'style_reference' ? 'style transfer' : 'linear';

  const hasReference = !!($('generation-ipadapter-image')?.files?.[0]);
  if (!hasReference) {
    try {
      await useGenerationSourceAsIdentityReference();
    } catch (_) {}
  }

  updatePrimaryGenerationIpAdapterSummary();
  updateGenerationIdentitySummary();
  scheduleGenerationDraftSave();

  const goalLabel = goal === 'same_face'
    ? 'same-face'
    : (goal === 'same_character' ? 'same-character' : 'style-reference');
  const routeLabel = route === 'ipadapter_faceid' ? 'IP-Adapter FaceID' : 'IP-Adapter standard';
  setStatus('generation-status', `Prepared the ${goalLabel} lane using ${routeLabel}. Next: confirm the reference image + model choices in IP-Adapter, then run the generation.`, 'success');
}


function syncGenerationIdentityUI() {
  updateGenerationIdentitySummary();
}

function syncGenerationRefineUI() {
  const enabled = String($('generation-refine-enabled')?.value || 'false') === 'true';
  const activeFamily = window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '';
  const qwenFamily = activeFamily === 'qwen_image_edit';
  const strategyEl = $('generation-refine-strategy');
  if (qwenFamily && strategyEl && !strategyEl.value) strategyEl.value = 'qwen_reedit';
  const strategy = strategyEl?.value || 'standard';
  if (qwenFamily && strategyEl) strategyEl.value = strategy || 'qwen_reedit';
  const modeEl = $('generation-refine-mode');
  const mode = strategy === 'qwen_reedit' ? 'image_upscale' : (modeEl?.value || 'latent');
  if (strategy === 'qwen_reedit' && modeEl) modeEl.value = 'image_upscale';
  $('generation-refine-upscaler-wrap')?.classList.toggle('is-hidden', !enabled || mode !== 'image_upscale');
  ['generation-refine-resize-method','generation-refine-scale','generation-refine-scale-range','generation-refine-steps','generation-refine-steps-range','generation-refine-denoise','generation-refine-denoise-range','generation-refine-cfg','generation-refine-sampler','generation-refine-scheduler','generation-refine-tiled-vae','generation-refine-tile-size','generation-refine-tile-overlap','generation-refine-strategy'].forEach(id => $(id)?.closest('div')?.classList.toggle('is-hidden', !enabled));
  if (qwenFamily && strategy === 'qwen_reedit') {
    $('generation-refine-mode')?.closest('div')?.classList.add('is-hidden');
    $('generation-refine-upscaler-wrap')?.classList.remove('is-hidden');
  }
  updateGenerationUpscaleLabSummary();
  renderGenerationFinishFoundation();
}

function syncGenerationSupirUI() {
  const enabled = String($('generation-supir-enabled')?.value || 'false') === 'true';
  const tiled = String($('generation-supir-tiled-vae')?.value || 'true') === 'true';
  ['generation-supir-model','generation-supir-sdxl-model','generation-supir-scale','generation-supir-steps','generation-supir-restoration-scale','generation-supir-cfg-scale','generation-supir-control-scale','generation-supir-color-fix-type','generation-supir-tiled-vae'].forEach(id => $(id)?.closest('div')?.classList.toggle('is-hidden', !enabled));
  ['generation-supir-encoder-tile-size','generation-supir-decoder-tile-size'].forEach(id => $(id)?.closest('div')?.classList.toggle('is-hidden', !enabled || !tiled));
  ['generation-supir-a-prompt','generation-supir-n-prompt'].forEach(id => $(id)?.closest('div')?.classList.toggle('is-hidden', !enabled));
  renderGenerationFinishFoundation();
}

function normalizeGenerationGgufClipTypeForMode(mode, current='') {
  const clipMode = String(mode || 'dual').trim().toLowerCase() === 'single' ? 'single' : 'dual';
  const value = String(current || '').trim() || (clipMode === 'single' ? 'stable_diffusion' : 'flux');
  const allowed = clipMode === 'single' ? ['stable_diffusion', 'sdxl', 'sd3', 'flux', 'qwen_image'] : ['flux', 'sd3', 'sdxl'];
  return allowed.includes(value) ? value : allowed[0];
}

function mergeGenerationCatalogLists(...groups) {
  const merged = [];
  const seen = new Set();
  groups.forEach(group => {
    if (!Array.isArray(group)) return;
    group.forEach(item => {
      const value = String(item || '').trim();
      if (!value) return;
      const key = value.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(value);
    });
  });
  return merged;
}

function renderGenerationGGUFValidator() {
  return window.NeoGenerationRuntimeShell.renderGenerationGGUFValidator.apply(this, arguments);
}

function currentGenerationRuntimeProfile() {
  return window.NeoGenerationRuntimeShell.currentGenerationRuntimeProfile.apply(this, arguments);
}

function estimateGenerationBackendVramGiB() {
  return window.NeoGenerationRuntimeShell.estimateGenerationBackendVramGiB.apply(this, arguments);
}

function renderGenerationRuntimeProfileAndCapabilities() {
  return window.NeoGenerationRuntimeShell.renderGenerationRuntimeProfileAndCapabilities.apply(this, arguments);
}

function generationPromptConditioningSupportsClipSkip() {
  const modelSource = String($('generation-model-source')?.value || 'checkpoint').trim().toLowerCase();
  if (modelSource === 'checkpoint') return true;
  if (modelSource !== 'gguf') return false;
  const ggufMode = String($('generation-gguf-clip-mode')?.value || 'dual').trim().toLowerCase() === 'single' ? 'single' : 'dual';
  const ggufFamily = normalizeGenerationGgufClipTypeForMode(ggufMode, $('generation-gguf-clip-type')?.value || '');
  return !['flux', 'qwen_image'].includes(ggufFamily);
}

function analyzeGenerationPromptConditioning() {
  const modeKey = String($('generation-prompt-conditioning-mode')?.value || 'raw').trim() || 'raw';
  const mode = generationPromptConditioningModes[modeKey] || generationPromptConditioningModes.raw;
  const positive = String($('generation-positive')?.value || '');
  const negative = String($('generation-negative')?.value || '');
  const clipSkip = Math.max(1, Math.min(4, Number($('generation-clip-skip')?.value || 1) || 1));
  const clipSkipSupported = generationPromptConditioningSupportsClipSkip();
  const weightMatches = Array.from(positive.matchAll(/[\(\[]\s*([^\(\)\[\]]+?)\s*:\s*(-?\d*\.?\d+)\s*[\)\]]/g));
  const weightedCount = weightMatches.length;
  const extremeWeights = weightMatches.filter(match => {
    const value = Number(match[2] || 1);
    return value > 1.6 || value < 0.4;
  }).length;
  const repeatedMap = new Map();
  positive.split(/[,\n]+/).map(part => part.trim().toLowerCase()).filter(part => part.length >= 4).forEach(part => {
    repeatedMap.set(part, (repeatedMap.get(part) || 0) + 1);
  });
  const repeatedCount = Array.from(repeatedMap.values()).filter(count => count > 1).length;
  const longPositive = positive.length >= 1200 ? 'heavy' : (positive.length >= 700 ? 'watch' : 'clean');
  const longNegative = negative.length >= 700 ? 'watch' : 'clean';
  let health = 'Clean';
  if (extremeWeights || (clipSkip > 1 && !clipSkipSupported) || longPositive === 'heavy') {
    health = 'Heavy';
  } else if (weightedCount >= 4 || repeatedCount || longPositive === 'watch' || longNegative === 'watch' || clipSkip > 1 || modeKey !== 'raw') {
    health = 'Watch';
  }
  const warnings = [];
  if (weightedCount) warnings.push(`${weightedCount} weighted tag${weightedCount === 1 ? '' : 's'}`);
  if (extremeWeights) warnings.push(`${extremeWeights} extreme weight${extremeWeights === 1 ? '' : 's'}`);
  if (repeatedCount) warnings.push(`${repeatedCount} repeated prompt chunk${repeatedCount === 1 ? '' : 's'}`);
  if (longPositive !== 'clean') warnings.push(longPositive === 'heavy' ? 'long positive prompt' : 'dense positive prompt');
  if (longNegative !== 'clean') warnings.push('dense negative prompt');
  if (clipSkip > 1 && !clipSkipSupported) warnings.push('clip skip ignored for current family');
  return { modeKey, mode, positive, negative, weightedCount, extremeWeights, repeatedCount, longPositive, longNegative, clipSkip, clipSkipSupported, health, warnings };
}

function renderGenerationPromptConditioning() {
  const note = $('generation-prompt-conditioning-note');
  const badge = $('generation-prompt-conditioning-badge');
  const healthField = $('generation-prompt-conditioning-health');
  const strip = $('generation-prompt-conditioning-strip');
  const warning = $('generation-prompt-conditioning-warning');
  const clipSkipSelect = $('generation-clip-skip');
  if (!note || !badge || !healthField || !strip || !warning || !clipSkipSelect) return;
  const analysis = analyzeGenerationPromptConditioning();
  badge.textContent = analysis.mode.label;
  badge.classList.toggle('ok', analysis.health === 'Clean');
  healthField.value = analysis.health;
  clipSkipSelect.disabled = !analysis.clipSkipSupported;
  note.textContent = analysis.clipSkipSupported
    ? `${analysis.mode.note} Clip skip is available for the current family.`
    : `${analysis.mode.note} Clip skip is unavailable for the current family, so Neo will ignore it here.`;
  const chips = [
    { text: analysis.mode.label, ok:true },
    { text: analysis.clipSkip > 1 ? `Clip skip ${analysis.clipSkip}` : 'Clip skip off', ok: analysis.clipSkipSupported || analysis.clipSkip === 1 },
  ];
  if (analysis.weightedCount) chips.push({ text: `${analysis.weightedCount} weighted tag${analysis.weightedCount === 1 ? '' : 's'}`, ok: analysis.extremeWeights === 0 });
  if (analysis.extremeWeights) chips.push({ text: `${analysis.extremeWeights} extreme weight${analysis.extremeWeights === 1 ? '' : 's'}`, ok:false });
  if (analysis.repeatedCount) chips.push({ text: `${analysis.repeatedCount} repeated chunk${analysis.repeatedCount === 1 ? '' : 's'}`, ok:false });
  if (analysis.longPositive !== 'clean') chips.push({ text: analysis.longPositive === 'heavy' ? 'Long positive prompt' : 'Dense positive prompt', ok:false });
  if (analysis.longNegative !== 'clean') chips.push({ text:'Dense negative prompt', ok:false });
  if (!analysis.weightedCount && analysis.longPositive === 'clean' && analysis.longNegative === 'clean') {
    chips.push({ text:'Prompt stack looks clean', ok:true });
  }
  strip.innerHTML = chips.map(chip => `<span class="badge${chip.ok ? ' ok' : ''}">${escapeHtml(chip.text)}</span>`).join('');
  if (!analysis.warnings.length) {
    warning.textContent = analysis.modeKey === 'raw'
      ? 'Prompt conditioning is idle. Neo will encode the prompt as written.'
      : 'Prompt conditioning is active. Neo will steady the prompt before it is encoded.';
  } else {
    warning.textContent = `${analysis.health} · ${analysis.warnings.join(' · ')}.`;
  }
}

function renderGenerationExperimentalMode() {
  const modeSelect = $('generation-experimental-mode');
  const slotA = $('generation-advanced-slot-a');
  const slotB = $('generation-advanced-slot-b');
  const note = $('generation-experimental-mode-note');
  const badge = $('generation-experimental-mode-badge');
  const strip = $('generation-experimental-capability-strip');
  if (!modeSelect || !slotA || !slotB || !note || !badge || !strip) return;
  const modeKey = String(modeSelect.value || 'off').trim() || 'off';
  const mode = generationExperimentalModes[modeKey] || generationExperimentalModes.off;
  const selectedA = String(slotA.value || 'none').trim() || 'none';
  const selectedB = String(slotB.value || 'none').trim() || 'none';
  const features = (generationCatalogState && typeof generationCatalogState.features === 'object' && generationCatalogState.features) ? generationCatalogState.features : {};
  badge.textContent = mode.label;
  badge.classList.toggle('ok', modeKey !== 'open_experimental');
  const notes = [mode.note];
  if (modeKey === 'off' && (selectedA !== 'none' || selectedB !== 'none')) notes.push('Slots stay as planning placeholders until you deliberately arm sandbox mode.');
  note.textContent = notes.join(' ');
  const chips = [
    { text: mode.label, ok: modeKey !== 'open_experimental' },
    { text: selectedA === 'none' ? 'Slot A empty' : `Slot A · ${selectedA.replace(/_/g, ' ')}`, ok: selectedA === 'none' },
    { text: selectedB === 'none' ? 'Slot B empty' : `Slot B · ${selectedB.replace(/_/g, ' ')}`, ok:true },
  ];
  if (selectedA === 'qwen_image_edit') chips.push({ text:'Qwen edit lane active', ok: !!features.qwen_image_edit_ready });
  if (modeKey === 'safe_sandbox') chips.push({ text:'Core workflow protected', ok:true });
  if (modeKey === 'open_experimental') chips.push({ text:'Experimental path armed', ok:false });
  strip.innerHTML = chips.map(chip => `<span class="badge${chip.ok ? ' ok' : ''}">${escapeHtml(chip.text)}</span>`).join('');
}

function syncGenerationGGUFUI() {
  return window.NeoGenerationRuntimeShell.syncGenerationGGUFUI.apply(this, arguments);
}

function clearGenerationImageInput(inputId) {
  const input = $(inputId);
  if (!input) return;
  try { input.value = ''; } catch (_) {}
  input.dispatchEvent(new Event('change', { bubbles:true }));
}

function updateGenerationImagePanel(inputId, previewId, emptyId, metaId, emptyText) {
  const input = $(inputId);
  const preview = $(previewId);
  const empty = $(emptyId);
  const meta = $(metaId);
  const previewStack = preview?.closest('.generation-preview-stack') || null;
  if (!input || !preview || !empty || !meta) return;
  const file = input.files?.[0] || null;
  const oldUrl = preview.dataset.objectUrl || '';
  if (oldUrl) { try { URL.revokeObjectURL(oldUrl); } catch (_) {} preview.dataset.objectUrl = ''; }
  if (!file) {
    preview.removeAttribute('src');
    preview.classList.add('hidden');
    previewStack?.classList.add('hidden');
    empty.classList.remove('hidden');
    meta.textContent = emptyText;
    return;
  }
  const objectUrl = URL.createObjectURL(file);
  preview.src = objectUrl;
  preview.dataset.objectUrl = objectUrl;
  preview.classList.remove('hidden');
  previewStack?.classList.remove('hidden');
  empty.classList.add('hidden');
  const sizeKb = Math.max(1, Math.round((Number(file.size || 0) || 0) / 1024));
  meta.textContent = `${file.name} · ${sizeKb} KB`;
}

function updateGenerationSourceMaskOverlay() {
  const overlay = $('generation-source-mask-overlay');
  const mode = $('generation-workflow-type')?.value || 'txt2img';
  const maskInput = $('generation-mask-image');
  if (!overlay) return;
  const oldUrl = overlay.dataset.objectUrl || '';
  if (oldUrl) { try { URL.revokeObjectURL(oldUrl); } catch (_) {} overlay.dataset.objectUrl = ''; }
  const file = maskInput?.files?.[0] || null;
  if (mode !== 'inpaint' || !file) {
    overlay.removeAttribute('src');
    overlay.classList.add('hidden');
    return;
  }
  const url = URL.createObjectURL(file);
  overlay.src = url;
  overlay.dataset.objectUrl = url;
  overlay.classList.remove('hidden');
}

function bindGenerationImagePanel({ inputId, dropzoneId, replaceBtnId, clearBtnId, previewId, emptyId, metaId, emptyText }) {
  const input = $(inputId);
  const dropzone = $(dropzoneId);
  const replaceBtn = $(replaceBtnId);
  const clearBtn = $(clearBtnId);
  if (!input || !dropzone) return;
  const openPicker = () => input.click();
  dropzone.addEventListener('click', openPicker);
  dropzone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPicker();
    }
  });
  input.addEventListener('change', () => {
    updateGenerationImagePanel(inputId, previewId, emptyId, metaId, emptyText);
    updateGenerationSourceMaskOverlay();
    if (inputId === 'generation-source-image') refreshGenerationSourceImageInfo();
    else renderGenerationOutpaintSummary();
    scheduleGenerationDraftSave();
  });
  replaceBtn?.addEventListener('click', e => { e.preventDefault(); openPicker(); });
  clearBtn?.addEventListener('click', e => { e.preventDefault(); clearGenerationImageInput(inputId); scheduleGenerationDraftSave(); });
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('is-dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('is-dragover'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('is-dragover');
    const file = e.dataTransfer?.files?.[0] || null;
    if (!file) return;
    if (!String(file.type || '').startsWith('image/')) {
      setStatus('generation-status', 'Only image files can be dropped here.', 'warn');
      return;
    }
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles:true }));
  });
  updateGenerationImagePanel(inputId, previewId, emptyId, metaId, emptyText);
}


const generationQwenSourceSlots = [
  {
    uid: '2',
    inputId: 'generation-source-image-2',
    dropzoneId: 'generation-source-dropzone-2',
    replaceBtnId: 'btn-generation-source-replace-2',
    clearBtnId: 'btn-generation-source-clear-2',
    removeBtnId: 'btn-generation-source-remove-2',
    previewId: 'generation-source-preview-2',
    emptyId: 'generation-source-empty-2',
    metaId: 'generation-source-meta-2',
    wrapId: 'generation-qwen-source-wrap-2',
    label: 'Source image 2',
    hint: 'Use this as a secondary subject, outfit donor, prop donor, or composition helper for Qwen.',
    emptyText: 'Drop an extra Qwen source image here or click to browse.',
  },
  {
    uid: '3',
    inputId: 'generation-source-image-3',
    dropzoneId: 'generation-source-dropzone-3',
    replaceBtnId: 'btn-generation-source-replace-3',
    clearBtnId: 'btn-generation-source-clear-3',
    removeBtnId: 'btn-generation-source-remove-3',
    previewId: 'generation-source-preview-3',
    emptyId: 'generation-source-empty-3',
    metaId: 'generation-source-meta-3',
    wrapId: 'generation-qwen-source-wrap-3',
    label: 'Source image 3',
    hint: 'Use this for a third subject, background character, scene cue, or extra donor reference in Qwen.',
    emptyText: 'Drop a third Qwen source image here or click to browse.',
  },
];

function getGenerationActiveFamily() {
  return String($('generation-family')?.value || window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '').trim() || 'sdxl_sd';
}

function isGenerationQwenFamily() {
  return getGenerationActiveFamily() === 'qwen_image_edit';
}


const generationQwenRoleOptions = [
  { value:'main_subject', label:'Main subject' },
  { value:'secondary_subject', label:'Secondary subject' },
  { value:'outfit_donor', label:'Outfit donor' },
  { value:'style_donor', label:'Style donor' },
  { value:'background_character', label:'Background character' },
  { value:'scene_reference', label:'Scene reference' },
  { value:'object_reference', label:'Object / prop reference' },
];

const generationQwenRoleTextMap = {
  main_subject: 'main subject',
  secondary_subject: 'secondary subject',
  outfit_donor: 'outfit donor',
  style_donor: 'style donor',
  background_character: 'background character',
  scene_reference: 'scene reference',
  object_reference: 'object or prop reference',
};

function getGenerationQwenRoleText(value) {
  return generationQwenRoleTextMap[String(value || '').trim()] || 'reference';
}

function getGenerationQwenSourceRoleValue(uid='1') {
  return trim($(`generation-qwen-source-role-${uid}`)?.value || '') || (uid === '1' ? 'main_subject' : 'secondary_subject');
}

function buildGenerationQwenRoleSummary() {
  const parts = [`image1 = ${getGenerationQwenRoleText(getGenerationQwenSourceRoleValue('1'))}`];
  generationQwenSourceSlots.forEach(spec => {
    if (!$(spec.wrapId) || $(spec.wrapId)?.classList.contains('hidden') || !$(spec.inputId)?.files?.[0]) return;
    parts.push(`image${spec.uid} = ${getGenerationQwenRoleText(getGenerationQwenSourceRoleValue(spec.uid))}`);
  });
  return parts.join(', ');
}

function buildGenerationQwenSamplePromptText() {
  const lines = [];
  const source1Role = getGenerationQwenSourceRoleValue('1');
  if ($('generation-source-image')?.files?.[0]) {
    if (source1Role === 'main_subject') lines.push('Use the subject from image1 as the main subject.');
    else if (source1Role === 'secondary_subject') lines.push('Use the subject from image1 as the secondary subject.');
    else if (source1Role === 'outfit_donor') lines.push('Use the outfit from image1.');
    else if (source1Role === 'style_donor') lines.push('Use the visual style and styling cues from image1.');
    else if (source1Role === 'background_character') lines.push('Place the subject from image1 in the background.');
    else if (source1Role === 'scene_reference') lines.push('Use image1 as the main scene and composition reference.');
    else if (source1Role === 'object_reference') lines.push('Use the main object or prop from image1.');
  }
  generationQwenSourceSlots.forEach(spec => {
    if (!$(spec.inputId)?.files?.[0] || $(spec.wrapId)?.classList.contains('hidden')) return;
    const role = getGenerationQwenSourceRoleValue(spec.uid);
    if (role === 'main_subject') lines.push(`Use the subject from image${spec.uid} as the main subject.`);
    else if (role === 'secondary_subject') lines.push(`Include the subject from image${spec.uid} as a second character.`);
    else if (role === 'outfit_donor') lines.push(`Use the outfit or clothing details from image${spec.uid}.`);
    else if (role === 'style_donor') lines.push(`Borrow the styling and visual vibe from image${spec.uid}.`);
    else if (role === 'background_character') lines.push(`Place the subject from image${spec.uid} in the background.`);
    else if (role === 'scene_reference') lines.push(`Use image${spec.uid} as a scene or composition cue.`);
    else if (role === 'object_reference') lines.push(`Use the object or prop from image${spec.uid}.`);
  });
  lines.push('Keep realistic anatomy, clear faces, coherent composition, and natural lighting.');
  return lines.join(' ');
}


const generationQwenPresetTemplates = {
  two_character_scene: {
    title: 'Two-character scene',
    summary: 'Main subject + second character with clean relationship wording.',
    prompt: 'Use the subject from image1 as the main subject. Include the subject from image2 as a second character interacting naturally with image1. Keep both faces recognizable, preserve clear body language, and place them in one coherent scene with realistic anatomy, natural lighting, and balanced composition.',
  },
  face_outfit_transfer: {
    title: 'Face + outfit transfer',
    summary: 'Identity from image1, clothing or style donor from image2.',
    prompt: 'Use the face, identity, and overall likeness from image1 as the main subject. Use the outfit, clothing details, and styling cues from image2. Keep the final character consistent, realistic, and fully coherent with natural lighting, clean anatomy, and sharp facial detail.',
  },
  subject_background_witness: {
    title: 'Subject + background witness',
    summary: 'Main subject foreground, extra subject watching in background.',
    prompt: 'Use the subject from image1 as the main foreground subject. Place the subject from image3 in the background watching or reacting naturally. Keep image1 as the clear focus, maintain depth separation, realistic faces, natural pose flow, and cinematic but believable lighting.',
  },
  character_prop_reference: {
    title: 'Character + prop reference',
    summary: 'Main subject with an important prop or object donor.',
    prompt: 'Use the subject from image1 as the main character. Use the object or prop from image2 and integrate it naturally into the scene. Keep the prop readable, correctly scaled, and clearly connected to the character while preserving realistic anatomy, natural interaction, and detailed composition.',
  },
};

function getGenerationQwenSelectedPresetKey() {
  return trim($('generation-qwen-prompt-preset')?.value || '');
}

function getGenerationQwenPresetTemplate(key='') {
  return generationQwenPresetTemplates[String(key || '').trim()] || null;
}

function getGenerationQwenLoadedImageIds() {
  const loaded = [];
  if ($('generation-source-image')?.files?.[0]) loaded.push('1');
  generationQwenSourceSlots.forEach(spec => {
    if ($(spec.inputId)?.files?.[0] && !$(spec.wrapId)?.classList.contains('hidden')) loaded.push(spec.uid);
  });
  return loaded;
}

function getGenerationQwenSmartSuggestion() {
  const loaded = getGenerationQwenLoadedImageIds();
  const has2 = loaded.includes('2');
  const has3 = loaded.includes('3');
  const role1 = getGenerationQwenSourceRoleValue('1');
  const role2 = getGenerationQwenSourceRoleValue('2');
  const role3 = getGenerationQwenSourceRoleValue('3');
  if (!loaded.includes('1')) {
    return {
      key: '',
      title: 'Add a main source image',
      summary: 'Load image1 first. Qwen multi-image prompting works best when image1 is the anchor subject or scene.',
      recommendation: 'Start with image1 as your anchor, then add image2 or image3 only when they have a clear job.',
      refs: 'Suggested refs: image1',
    };
  }
  if (has2 && role2 === 'object_reference') {
    return {
      key: 'character_prop_reference',
      title: 'Best match: Character + prop reference',
      summary: 'image2 looks like a prop/object donor, so use a subject + prop structure.',
      recommendation: 'Keep image1 as the character anchor and tell Qwen exactly how the prop from image2 should be held, worn, or placed.',
      refs: 'Suggested refs: image1 = character, image2 = prop/object',
    };
  }
  if (has2 && (role2 === 'outfit_donor' || role2 === 'style_donor' || role1 === 'outfit_donor' || role1 === 'style_donor')) {
    return {
      key: 'face_outfit_transfer',
      title: 'Best match: Face + outfit transfer',
      summary: 'One loaded image is acting like an outfit/style donor, so identity-transfer wording is the cleaner play.',
      recommendation: 'Keep identity and face wording tied to image1. Treat image2 as the clothing or style donor instead of letting both fight for subject priority.',
      refs: 'Suggested refs: image1 = identity, image2 = outfit/style',
    };
  }
  if (has3 && role3 === 'background_character') {
    return {
      key: 'subject_background_witness',
      title: 'Best match: Subject + background witness',
      summary: 'image3 is loaded as a background character, so use a foreground/background relationship.',
      recommendation: 'Make image1 the clear focus. Tell Qwen to keep image3 smaller or deeper in frame so the scene does not split into two competing leads.',
      refs: 'Suggested refs: image1 = foreground lead, image3 = background watcher',
    };
  }
  if (has2 && (role2 === 'secondary_subject' || role2 === 'main_subject')) {
    return {
      key: 'two_character_scene',
      title: 'Best match: Two-character scene',
      summary: 'image2 is behaving like a second character, so use a clean two-person composition prompt.',
      recommendation: 'Describe who is doing what. Qwen handles two-person scenes better when the action and spatial relationship are explicit.',
      refs: 'Suggested refs: image1 = lead, image2 = second character',
    };
  }
  if (has3 && role3 === 'scene_reference') {
    return {
      key: 'subject_background_witness',
      title: 'Best match: Subject + scene cue',
      summary: 'image3 is acting like a scene cue, so keep image1 as the subject and treat image3 as composition/background guidance.',
      recommendation: 'Reference image3 for environment, placement, or framing only. Avoid describing it like a competing subject unless that is intentional.',
      refs: 'Suggested refs: image1 = subject, image3 = environment cue',
    };
  }
  if (has2) {
    return {
      key: 'two_character_scene',
      title: 'Best match: Multi-image scene starter',
      summary: 'With image1 + image2 loaded, a structured two-image prompt is the safest default.',
      recommendation: 'Give each image one job. Qwen gets messy when multiple loaded images all sound like they are supposed to be the same main subject.',
      refs: 'Suggested refs: image1, image2',
    };
  }
  return {
    key: '',
    title: 'Single-image mode active',
    summary: 'Only image1 is loaded right now, so multi-image presets are optional.',
    recommendation: 'Use image1 as the anchor. Add image2 or image3 only when you need a second subject, donor outfit, prop, or scene cue.',
    refs: 'Suggested refs: image1',
  };
}

function updateGenerationQwenPresetSummary() {
  const preset = getGenerationQwenPresetTemplate(getGenerationQwenSelectedPresetKey());
  const summaryEl = $('generation-qwen-preset-summary');
  if (!summaryEl) return;
  if (!preset) {
    summaryEl.textContent = 'Pick a preset to get a structured starter prompt for common Qwen multi-image setups.';
    return;
  }
  summaryEl.textContent = `${preset.title}: ${preset.summary}`;
}

function updateGenerationQwenSmartSuggestionUI() {
  const suggestion = getGenerationQwenSmartSuggestion();
  const titleEl = $('generation-qwen-smart-title');
  const summaryEl = $('generation-qwen-smart-summary');
  const recommendationEl = $('generation-qwen-smart-recommendation');
  const refsEl = $('generation-qwen-smart-refs');
  const autoBtn = $('btn-generation-qwen-apply-smart-preset');
  if (titleEl) titleEl.textContent = suggestion.title;
  if (summaryEl) summaryEl.textContent = suggestion.summary;
  if (recommendationEl) recommendationEl.textContent = suggestion.recommendation;
  if (refsEl) refsEl.textContent = suggestion.refs;
  if (autoBtn) {
    autoBtn.disabled = !suggestion.key;
    autoBtn.title = suggestion.key ? 'Auto-select the suggested preset for the currently loaded image slots' : 'No smart preset suggestion yet';
  }
}

function buildGenerationQwenPresetPromptText() {
  const preset = getGenerationQwenPresetTemplate(getGenerationQwenSelectedPresetKey());
  if (!preset) return buildGenerationQwenSamplePromptText();
  const base = preset.prompt;
  const roleSummary = buildGenerationQwenRoleSummary();
  return `${base} Prompt role map: ${roleSummary}.`;
}

function appendGenerationPositivePrompt(snippet) {
  const promptEl = $('generation-positive');
  if (!promptEl) return;
  const raw = String(snippet || '').trim();
  if (!raw) return;
  const current = String(promptEl.value || '').trim();
  promptEl.value = current ? `${current}${current.endsWith('\n') ? '' : '\n'}${raw}` : raw;
  promptEl.dispatchEvent(new Event('input', { bubbles:true }));
  refreshGenerationCounters?.();
  scheduleGenerationDraftSave();
}

function updateGenerationQwenPromptHelperNote() {
  const roleSummary = buildGenerationQwenRoleSummary();
  const summaryEl = $('generation-qwen-source-role-summary');
  if (summaryEl) summaryEl.textContent = `Sample role map: ${roleSummary}.`;
  const noteEl = $('generation-qwen-prompt-helper-note');
  if (noteEl) noteEl.textContent = `Current helper idea: ${buildGenerationQwenSamplePromptText()}`;
  updateGenerationQwenPresetSummary();
  updateGenerationQwenSmartSuggestionUI();
}

function bindGenerationQwenPromptHelpers() {
  const refsBtn = $('btn-generation-qwen-insert-image-refs');
  if (refsBtn && !refsBtn.dataset.boundQwenHelper) {
    refsBtn.dataset.boundQwenHelper = '1';
    refsBtn.addEventListener('click', e => {
      e.preventDefault();
      appendGenerationPositivePrompt('Use image1 as the main reference. If needed, also use image2 and image3 only for the roles described in the prompt.');
    });
  }
  const sampleBtn = $('btn-generation-qwen-build-sample-prompt');
  if (sampleBtn && !sampleBtn.dataset.boundQwenHelper) {
    sampleBtn.dataset.boundQwenHelper = '1';
    sampleBtn.addEventListener('click', e => {
      e.preventDefault();
      appendGenerationPositivePrompt(buildGenerationQwenSamplePromptText());
    });
  }
  const presetSelect = $('generation-qwen-prompt-preset');
  if (presetSelect && !presetSelect.dataset.boundQwenPreset) {
    presetSelect.dataset.boundQwenPreset = '1';
    presetSelect.addEventListener('change', () => {
      updateGenerationQwenPresetSummary();
      scheduleGenerationDraftSave();
    });
  }
  const presetBtn = $('btn-generation-qwen-build-preset-prompt');
  if (presetBtn && !presetBtn.dataset.boundQwenPreset) {
    presetBtn.dataset.boundQwenPreset = '1';
    presetBtn.addEventListener('click', e => {
      e.preventDefault();
      appendGenerationPositivePrompt(buildGenerationQwenPresetPromptText());
    });
  }
  const autoPresetBtn = $('btn-generation-qwen-apply-smart-preset');
  if (autoPresetBtn && !autoPresetBtn.dataset.boundQwenPreset) {
    autoPresetBtn.dataset.boundQwenPreset = '1';
    autoPresetBtn.addEventListener('click', e => {
      e.preventDefault();
      const suggestion = getGenerationQwenSmartSuggestion();
      if (!suggestion.key) return;
      const presetSelect = $('generation-qwen-prompt-preset');
      if (presetSelect) {
        presetSelect.value = suggestion.key;
        updateGenerationQwenPresetSummary();
        updateGenerationQwenSmartSuggestionUI();
        scheduleGenerationDraftSave();
      }
    });
  }
  ['1', '2', '3'].forEach(uid => {
    const select = $(`generation-qwen-source-role-${uid}`);
    if (select && !select.dataset.boundQwenRole) {
      select.dataset.boundQwenRole = '1';
      select.addEventListener('change', () => {
        updateGenerationQwenPromptHelperNote();
        scheduleGenerationDraftSave();
      });
    }
  });
  ['generation-source-image', 'generation-source-image-2', 'generation-source-image-3'].forEach(id => {
    const input = $(id);
    if (input && !input.dataset.boundQwenRoleRefresh) {
      input.dataset.boundQwenRoleRefresh = '1';
      input.addEventListener('change', () => syncGenerationQwenSourceImages());
    }
  });
  updateGenerationQwenPromptHelperNote();
}

function ensureGenerationQwenSourceSlot(spec) {
  let wrap = $(spec.wrapId);
  if (wrap) return wrap;
  const host = $('generation-qwen-source-extra-list');
  if (!host) return null;
  wrap = document.createElement('div');
  wrap.id = spec.wrapId;
  wrap.className = 'generation-image-panel';
  wrap.innerHTML = `
    <div class="row-between" style="margin-bottom:8px;align-items:flex-start;">
      <div style="flex:1 1 240px;">
        <label for="${spec.inputId}">${spec.label}</label>
        <div class="mini-note">${spec.hint}</div>
        <div style="margin-top:8px;">
          <label for="generation-qwen-source-role-${spec.uid}">Role</label>
          <select id="generation-qwen-source-role-${spec.uid}">
            ${generationQwenRoleOptions.map(option => `<option value="${option.value}" ${option.value === (spec.uid === '2' ? 'secondary_subject' : 'background_character') ? 'selected' : ''}>${option.label}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="row" style="gap:6px;flex-wrap:wrap;">
        <button class="btn btn-small" id="${spec.replaceBtnId}" type="button">Replace</button>
        <button class="btn btn-small" id="${spec.clearBtnId}" type="button">Clear Image</button>
        <button class="btn btn-small" id="${spec.removeBtnId}" type="button">Remove</button>
      </div>
    </div>
    <input accept="image/*" class="hidden" id="${spec.inputId}" type="file"/>
    <div aria-label="Select ${spec.label.toLowerCase()}" class="generation-image-dropzone" id="${spec.dropzoneId}" role="button" tabindex="0">
      <div class="generation-image-empty" id="${spec.emptyId}">${spec.emptyText}</div>
      <img alt="${spec.label} preview" class="generation-image-preview hidden" id="${spec.previewId}"/>
    </div>
    <div class="mini-note generation-image-meta" id="${spec.metaId}" style="margin-top:8px;">No extra source image selected.</div>
  `;
  host.appendChild(wrap);
  bindGenerationImagePanel({
    inputId: spec.inputId,
    dropzoneId: spec.dropzoneId,
    replaceBtnId: spec.replaceBtnId,
    clearBtnId: spec.clearBtnId,
    previewId: spec.previewId,
    emptyId: spec.emptyId,
    metaId: spec.metaId,
    emptyText: spec.emptyText,
  });
  $(`generation-qwen-source-role-${spec.uid}`)?.addEventListener('change', () => {
    updateGenerationQwenPromptHelperNote();
    scheduleGenerationDraftSave();
  });
  $(spec.inputId)?.addEventListener('change', () => {
    syncGenerationQwenSourceImages();
  });
  $(spec.removeBtnId)?.addEventListener('click', e => {
    e.preventDefault();
    clearGenerationImageInput(spec.inputId);
    wrap.dataset.revealed = '0';
    wrap.classList.add('hidden');
    syncGenerationQwenSourceImages();
    scheduleGenerationDraftSave();
  });
  return wrap;
}

function getGenerationQwenSourceSlotSpecsAll() {
  return [{ uid:'1', inputId:'generation-source-image', wrapId:'generation-source-wrap' }, ...generationQwenSourceSlots];
}

function getGenerationQwenLoadedSlots() {
  return getGenerationQwenSourceSlotSpecsAll().filter(spec => !!($(spec.inputId)?.files?.[0]));
}

function getGenerationQwenVisibleExtraCount() {
  return generationQwenSourceSlots.filter(spec => !!$(spec.wrapId) && !$(spec.wrapId).classList.contains('hidden')).length;
}

function getGenerationQwenRevealedExtraCount() {
  return generationQwenSourceSlots.filter(spec => $(spec.wrapId)?.dataset?.revealed === '1').length;
}

function swapGenerationQwenSlotState(uidA='1', uidB='2') {
  if (uidA === uidB) return;
  const inputA = $(uidA === '1' ? 'generation-source-image' : `generation-source-image-${uidA}`);
  const inputB = $(uidB === '1' ? 'generation-source-image' : `generation-source-image-${uidB}`);
  if (!inputA || !inputB) return;
  const fileA = inputA.files?.[0] || null;
  const fileB = inputB.files?.[0] || null;
  const roleAEl = $(`generation-qwen-source-role-${uidA}`);
  const roleBEl = $(`generation-qwen-source-role-${uidB}`);
  const roleA = roleAEl ? roleAEl.value : '';
  const roleB = roleBEl ? roleBEl.value : '';

  const setFile = (input, file) => {
    const dt = new DataTransfer();
    if (file) dt.items.add(file);
    input.files = dt.files;
  };
  setFile(inputA, fileB);
  setFile(inputB, fileA);
  if (roleAEl && roleBEl) {
    roleAEl.value = roleB || roleAEl.value;
    roleBEl.value = roleA || roleBEl.value;
  }
  inputA.dispatchEvent(new Event('change', { bubbles:true }));
  inputB.dispatchEvent(new Event('change', { bubbles:true }));
}

function reorderGenerationQwenSlots(sourceUid='2', targetUid='1') {
  const order = getGenerationQwenLoadedSlots().map(spec => spec.uid);
  const sourceIndex = order.indexOf(String(sourceUid));
  const targetIndex = order.indexOf(String(targetUid));
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return;
  const nextOrder = order.slice();
  const [moved] = nextOrder.splice(sourceIndex, 1);
  nextOrder.splice(targetIndex, 0, moved);
  const original = getGenerationQwenSourceSlotSpecsAll().map(spec => ({ uid: spec.uid, file: $(spec.inputId)?.files?.[0] || null, role: $(`generation-qwen-source-role-${spec.uid}`)?.value || '' }));
  const loadedMap = new Map(original.filter(item => item.file).map(item => [item.uid, item]));
  const orderedLoaded = nextOrder.map(uid => loadedMap.get(uid)).filter(Boolean);
  const targets = getGenerationQwenSourceSlotSpecsAll();
  targets.forEach((spec, index) => {
    const input = $(spec.inputId);
    if (!input) return;
    const item = orderedLoaded[index] || null;
    const dt = new DataTransfer();
    if (item?.file) dt.items.add(item.file);
    input.files = dt.files;
    const roleEl = $(`generation-qwen-source-role-${spec.uid}`);
    if (roleEl && item?.role) roleEl.value = item.role;
    input.dispatchEvent(new Event('change', { bubbles:true }));
  });
}

function renderGenerationQwenSourceThumbStrip() {
  const host = $('generation-qwen-source-thumb-strip');
  if (!host) return;
  const isQwen = isGenerationQwenFamily();
  const loaded = getGenerationQwenLoadedSlots();
  host.innerHTML = '';
  $('generation-qwen-thumb-card')?.classList.toggle('hidden', !isQwen);
  if (!isQwen) return;
  if (!loaded.length) {
    host.innerHTML = '<div class="mini-note">Load image1 first, then add image2 and image3. Dragging here changes the Qwen image1/image2/image3 priority order.</div>';
    return;
  }
  loaded.forEach((spec, index) => {
    const file = $(spec.inputId)?.files?.[0] || null;
    if (!file) return;
    const objectUrl = URL.createObjectURL(file);
    const roleText = getGenerationQwenRoleText(getGenerationQwenSourceRoleValue(spec.uid));
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'card-lite generation-qwen-thumb-card';
    card.draggable = true;
    card.dataset.uid = spec.uid;
    card.style.cssText = 'width:132px; padding:8px; text-align:left; border:1px solid rgba(59,130,246,0.18); background:rgba(2,6,23,0.22); cursor:grab;';
    card.innerHTML = `
      <div style="font-size:11px; opacity:.8; margin-bottom:6px;">image${index + 1} · slot ${spec.uid}</div>
      <img src="${objectUrl}" alt="Qwen source ${index + 1}" style="width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:10px; display:block;" />
      <div style="margin-top:6px; font-weight:600; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(file.name || `image${index + 1}`)}</div>
      <div class="mini-note" style="margin-top:4px; font-size:11px;">${escapeHtml(roleText)}</div>
      <div class="mini-note" style="margin-top:4px; font-size:11px;">Drag to reprioritize</div>`;
    card.addEventListener('click', () => $(spec.inputId)?.click());
    card.addEventListener('dragstart', event => {
      event.dataTransfer?.setData('text/plain', spec.uid);
      event.dataTransfer.effectAllowed = 'move';
      card.style.opacity = '0.45';
    });
    card.addEventListener('dragend', () => { card.style.opacity = '1'; });
    card.addEventListener('dragover', event => { event.preventDefault(); card.style.outline = '2px dashed rgba(96,165,250,0.8)'; });
    card.addEventListener('dragleave', () => { card.style.outline = ''; });
    card.addEventListener('drop', event => {
      event.preventDefault();
      card.style.outline = '';
      const sourceUid = String(event.dataTransfer?.getData('text/plain') || '');
      if (!sourceUid || sourceUid === spec.uid) return;
      reorderGenerationQwenSlots(sourceUid, spec.uid);
      syncGenerationQwenSourceImages();
      scheduleGenerationDraftSave();
      setStatus('generation-status', `Reordered Qwen source priority. image1 now follows the new thumbnail order.`, 'success');
    });
    host.appendChild(card);
  });
}

function syncGenerationQwenSourceImages() {
  const isQwen = isGenerationQwenFamily();
  $('generation-qwen-multi-source-card')?.classList.toggle('hidden', !isQwen);
  $('generation-qwen-source-role-card')?.classList.toggle('hidden', !isQwen);
  $('generation-qwen-thumb-card')?.classList.toggle('hidden', !isQwen);
  $('btn-generation-add-qwen-source-image')?.classList.toggle('hidden', !isQwen);
  generationQwenSourceSlots.forEach(spec => {
    const wrap = ensureGenerationQwenSourceSlot(spec);
    if (!wrap) return;
    if (!isQwen) {
      wrap.classList.add('hidden');
      return;
    }
    const revealed = wrap.dataset.revealed === '1';
    wrap.classList.toggle('hidden', !revealed);
  });
  const addBtn = $('btn-generation-add-qwen-source-image');
  if (addBtn) {
    const revealedCount = getGenerationQwenRevealedExtraCount();
    addBtn.disabled = !isQwen || !$('generation-source-image')?.files?.[0] || revealedCount >= generationQwenSourceSlots.length;
    addBtn.title = !$('generation-source-image')?.files?.[0]
      ? 'Load image1 first.'
      : (revealedCount >= generationQwenSourceSlots.length ? 'Qwen supports up to 3 source images here.' : 'Add one more Qwen source image');
  }
  renderGenerationQwenSourceThumbStrip();
  updateGenerationQwenPromptHelperNote();
}

window.syncGenerationQwenSourceImages = syncGenerationQwenSourceImages;
window.syncGenerationLanPaintPanelUI = syncGenerationLanPaintPanelUI;

function bindGenerationQwenSourceImageControls() {
  bindGenerationQwenPromptHelpers();
  const addBtn = $('btn-generation-add-qwen-source-image');
  if (addBtn && !addBtn.dataset.boundQwenSource) {
    addBtn.dataset.boundQwenSource = '1';
    addBtn.addEventListener('click', e => {
      e.preventDefault();
      if (!$('generation-source-image')?.files?.[0]) {
        setStatus('generation-status', 'Load image1 first, then add image2 or image3 for Qwen multi-source.', 'warn');
        return;
      }
      const nextSlot = generationQwenSourceSlots.find(spec => {
        const wrap = ensureGenerationQwenSourceSlot(spec);
        return !!wrap && wrap.dataset.revealed !== '1';
      });
      if (nextSlot) {
        const wrap = ensureGenerationQwenSourceSlot(nextSlot);
        if (wrap) wrap.dataset.revealed = '1';
        syncGenerationQwenSourceImages();
        scheduleGenerationDraftSave();
        $(nextSlot.inputId)?.click();
      }
    });
  }
  syncGenerationQwenSourceImages();
}

document.addEventListener('neo-generation-family-changed', () => { syncGenerationQwenSourceImages(); syncGenerationInpaintBackendUI(); if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus(); });
document.addEventListener('DOMContentLoaded', () => {
  bindGenerationQwenSourceImageControls();
  $('generation-inpaint-backend')?.addEventListener('change', () => { syncGenerationInpaintBackendUI(); if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus(); scheduleGenerationDraftSave(); });
  $('generation-refine-enabled')?.addEventListener('change', () => { if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus(); scheduleGenerationDraftSave(); });
  $('generation-detailer-enabled')?.addEventListener('change', () => { if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus(); scheduleGenerationDraftSave(); });
  $('generation-composition-guide-type')?.addEventListener('change', () => { syncGenerationInpaintBackendUI(); scheduleGenerationDraftSave(); });
  $('generation-composition-source-mode')?.addEventListener('change', () => scheduleGenerationDraftSave());
  $('generation-lanpaint-preset')?.addEventListener('change', event => {
    if (event.target.value !== 'custom') applyGenerationLanPaintPreset(event.target.value);
    syncGenerationLanPaintPanelUI();
    scheduleGenerationDraftSave();
  });
  ['generation-lanpaint-num-steps','generation-lanpaint-prompt-mode','generation-lanpaint-lambda','generation-lanpaint-step-size','generation-lanpaint-beta','generation-lanpaint-friction','generation-lanpaint-early-stop'].forEach(id => {
    $(id)?.addEventListener('input', () => {
      const preset = $('generation-lanpaint-preset');
      if (preset) preset.value = 'custom';
      syncGenerationLanPaintPanelUI();
      scheduleGenerationDraftSave();
    });
    $(id)?.addEventListener('change', () => { syncGenerationLanPaintPanelUI(); scheduleGenerationDraftSave(); });
  });
});
bindGenerationQwenSourceImageControls();
syncGenerationInpaintBackendUI();

function loadFileAsImage(file) {
  return new Promise((resolve, reject) => {
    if (!file) return reject(new Error('No file selected.'));
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Could not load the image.'));
    };
    img.src = url;
  });
}
function formatOutpaintSizeLabel(width, height) {
  const w = Number(width || 0) || 0;
  const h = Number(height || 0) || 0;
  return w > 0 && h > 0 ? `${w} × ${h}` : '—';
}

function parseOutpaintPreset(value='custom') {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw || raw === 'custom') return null;
  const match = raw.match(/^(\d+)x(\d+)$/);
  if (!match) return null;
  return { width: Number(match[1] || 0), height: Number(match[2] || 0), value: raw };
}

function splitOutpaintDiff(diff=0) {
  const total = Math.max(0, Number(diff || 0) || 0);
  const first = Math.floor(total / 2);
  return [first, total - first];
}

function computeOutpaintPadding(sourceWidth, sourceHeight, targetWidth, targetHeight, anchor='center') {
  const sw = Math.max(0, Number(sourceWidth || 0) || 0);
  const sh = Math.max(0, Number(sourceHeight || 0) || 0);
  const tw = Math.max(0, Number(targetWidth || 0) || 0);
  const th = Math.max(0, Number(targetHeight || 0) || 0);
  if (!(sw > 0 && sh > 0 && tw > 0 && th > 0)) return { ok:false, reason:'missing_size' };
  if (tw < sw || th < sh) {
    return { ok:false, reason:'target_smaller', sourceWidth:sw, sourceHeight:sh, targetWidth:tw, targetHeight:th };
  }
  const diffW = tw - sw;
  const diffH = th - sh;
  let [left, right] = splitOutpaintDiff(diffW);
  let [top, bottom] = splitOutpaintDiff(diffH);
  const mode = String(anchor || 'center').trim().toLowerCase();
  if (mode === 'keep_bottom') {
    top = diffH;
    bottom = 0;
  } else if (mode === 'keep_top') {
    top = 0;
    bottom = diffH;
  } else if (mode === 'keep_left') {
    left = 0;
    right = diffW;
  } else if (mode === 'keep_right') {
    left = diffW;
    right = 0;
  }
  return { ok:true, left, right, top, bottom, targetWidth:tw, targetHeight:th, sourceWidth:sw, sourceHeight:sh };
}

function getCurrentOutpaintPadding() {
  return {
    left: Math.max(0, Number($('generation-outpaint-left')?.value || 0) || 0),
    top: Math.max(0, Number($('generation-outpaint-top')?.value || 0) || 0),
    right: Math.max(0, Number($('generation-outpaint-right')?.value || 0) || 0),
    bottom: Math.max(0, Number($('generation-outpaint-bottom')?.value || 0) || 0),
  };
}

function renderGenerationOutpaintSummary() {
  const summary = $('generation-outpaint-size-summary');
  const warning = $('generation-outpaint-size-warning');
  if (!summary || !warning) return;
  const sourceW = Number(generationSourceImageInfo.width || 0) || 0;
  const sourceH = Number(generationSourceImageInfo.height || 0) || 0;
  const preset = parseOutpaintPreset($('generation-outpaint-preset')?.value || 'custom');
  const anchor = $('generation-outpaint-anchor')?.value || 'center';
  const pads = getCurrentOutpaintPadding();
  warning.textContent = '';
  if (!(sourceW > 0 && sourceH > 0)) {
    summary.textContent = 'Load a source image, then pick a target preset to auto-calculate padding.';
    return;
  }
  const currentTargetW = sourceW + pads.left + pads.right;
  const currentTargetH = sourceH + pads.top + pads.bottom;
  if (preset) {
    const calc = computeOutpaintPadding(sourceW, sourceH, preset.width, preset.height, anchor);
    if (!calc.ok) {
      summary.textContent = `Source ${formatOutpaintSizeLabel(sourceW, sourceH)} · preset ${formatOutpaintSizeLabel(preset.width, preset.height)}`;
      if (calc.reason === 'target_smaller') {
        warning.textContent = 'Preset is smaller than the source image on at least one side. Pick a larger target or resize/crop first.';
      }
      return;
    }
    summary.textContent = `Source ${formatOutpaintSizeLabel(sourceW, sourceH)} → Target ${formatOutpaintSizeLabel(calc.targetWidth, calc.targetHeight)} · Pads L${calc.left} R${calc.right} T${calc.top} B${calc.bottom}`;
    return;
  }
  summary.textContent = `Source ${formatOutpaintSizeLabel(sourceW, sourceH)} → Custom target ${formatOutpaintSizeLabel(currentTargetW, currentTargetH)} · Pads L${pads.left} R${pads.right} T${pads.top} B${pads.bottom}`;
}

function renderGenerationImagePreflight() {
  return window.NeoGenerationImageShell.renderGenerationImagePreflight.apply(this, arguments);
}

async function sendGenerationSourceToReferenceLane(kind='controlnet') {
  const file = $('generation-source-image')?.files?.[0] || null;
  if (!file) {
    setStatus('generation-status', 'Load a source image first so Neo has something to route into that prep lane.', 'warn');
    return false;
  }
  if (kind === 'ipadapter') {
    assignFileToInput('generation-ipadapter-image', file);
    if ($('generation-ipadapter-enabled')) $('generation-ipadapter-enabled').checked = true;
    try { updatePrimaryGenerationIpAdapterSummary(); } catch (_) {}
    focusGenerationSetupTab('guide', 'generation-ipadapter-settings');
    scheduleGenerationDraftSave();
    setStatus('generation-status', 'Source image sent to IP-Adapter reference.', 'success');
    return true;
  }
  assignFileToInput('generation-control-image', file);
  refreshGenerationControlnetSourcePreview(getGenerationControlnetContext(null));
  if ($('generation-controlnet-enabled')) $('generation-controlnet-enabled').checked = true;
  try { updatePrimaryGenerationControlnetSummary(); } catch (_) {}
  focusGenerationSetupTab('guide', 'generation-controlnet-settings');
  scheduleGenerationDraftSave();
  setStatus('generation-status', 'Source image sent to ControlNet reference.', 'success');
  return true;
}

function activateGenerationSourceAsOutputPreview() {
  const file = $('generation-source-image')?.files?.[0] || null;
  if (!file) {
    setStatus('generation-status', 'Load a source image first so Neo can stage it as the current output preview.', 'warn');
    return false;
  }
  const viewUrl = URL.createObjectURL(file);
  activateGenerationOutput({
    filename: file.name || 'source-image',
    view_url: viewUrl,
    imported: true,
    library_source: true,
    source_kind: 'generation_source_image',
  }, { label:'Source image preview' });
  try {
    if (typeof window.neoGenerationSetSetupTab === 'function') window.neoGenerationSetSetupTab('output');
  } catch (_) {}
  setStatus('generation-status', 'Loaded the current source image into the output preview so you can test finish passes without queueing a new run first.', 'success');
  return true;
}

function applyGenerationPreflightResizeMode(mode='fit') {
  const next = ['fit', 'crop', 'native', 'stretch'].includes(String(mode || '').trim()) ? String(mode || '').trim() : 'fit';
  if ($('generation-source-resize-mode')) $('generation-source-resize-mode').value = next;
  renderGenerationImagePreflight();
  scheduleGenerationDraftSave();
  const label = next === 'crop' ? 'Crop to target' : (next === 'fit' ? 'Fit to target' : next);
  setStatus('generation-status', `${label} is now staged as the source resize behavior.`, 'success');
}

function prepareGenerationOutpaintFromSource() {
  if (!$('generation-source-image')?.files?.[0]) {
    setStatus('generation-status', 'Load a source image first so Neo can prep the outpaint lane around it.', 'warn');
    return false;
  }
  if ($('generation-workflow-type')) $('generation-workflow-type').value = 'outpaint';
  syncGenerationModeUI();
  focusGenerationSetupTab('assets', 'generation-outpaint-settings');
  renderGenerationOutpaintSummary();
  scheduleGenerationDraftSave();
  setStatus('generation-status', 'Outpaint prep opened. Pick a target preset or padding directions next.', 'success');
  return true;
}

async function refreshGenerationSourceImageInfo() {
  const file = $('generation-source-image')?.files?.[0] || null;
  if (!file) {
    generationSourceImageInfo = { width:0, height:0, name:'', size:0 };
    renderGenerationOutpaintSummary();
    renderGenerationImagePreflight();
    syncGenerationCleanupUI();
    return;
  }
  try {
    const img = await loadFileAsImage(file);
    generationSourceImageInfo = {
      width: Number(img.naturalWidth || img.width || 0) || 0,
      height: Number(img.naturalHeight || img.height || 0) || 0,
      name: file.name || '',
      size: Number(file.size || 0) || 0,
    };
  } catch (_) {
    generationSourceImageInfo = { width:0, height:0, name:file.name || '', size:Number(file.size || 0) || 0 };
  }
  const meta = $('generation-source-meta');
  if (meta && generationSourceImageInfo.width > 0 && generationSourceImageInfo.height > 0) {
    const sizeKb = Math.max(1, Math.round((Number(file.size || 0) || 0) / 1024));
    meta.textContent = `${file.name} · ${sizeKb} KB · ${generationSourceImageInfo.width} × ${generationSourceImageInfo.height}`;
  }
  if (($('generation-outpaint-preset')?.value || 'custom') !== 'custom') {
    await applyGenerationOutpaintPreset({ quiet:true });
  } else {
    renderGenerationOutpaintSummary();
    syncGenerationCleanupUI();
  }
  renderGenerationImagePreflight();
}

async function applyGenerationOutpaintPreset({ quiet=false } = {}) {
  const presetValue = $('generation-outpaint-preset')?.value || 'custom';
  const preset = parseOutpaintPreset(presetValue);
  if (!preset) {
    renderGenerationOutpaintSummary();
  syncGenerationCleanupUI();
    return true;
  }
  const sourceW = Number(generationSourceImageInfo.width || 0) || 0;
  const sourceH = Number(generationSourceImageInfo.height || 0) || 0;
  if (!(sourceW > 0 && sourceH > 0)) {
    renderGenerationOutpaintSummary();
  syncGenerationCleanupUI();
    if (!quiet) setStatus('generation-status', 'Load a source image first so Neo can calculate the outpaint padding.', 'warn');
    return false;
  }
  const calc = computeOutpaintPadding(sourceW, sourceH, preset.width, preset.height, $('generation-outpaint-anchor')?.value || 'center');
  if (!calc.ok) {
    renderGenerationOutpaintSummary();
  syncGenerationCleanupUI();
    if (!quiet) setStatus('generation-status', 'That preset is smaller than the current source image. Pick a larger target or resize/crop first.', 'warn');
    return false;
  }
  generationOutpaintPresetApplying = true;
  try {
    if ($('generation-outpaint-left')) $('generation-outpaint-left').value = String(calc.left);
    if ($('generation-outpaint-right')) $('generation-outpaint-right').value = String(calc.right);
    if ($('generation-outpaint-top')) $('generation-outpaint-top').value = String(calc.top);
    if ($('generation-outpaint-bottom')) $('generation-outpaint-bottom').value = String(calc.bottom);
  } finally {
    generationOutpaintPresetApplying = false;
  }
  renderGenerationOutpaintSummary();
  syncGenerationCleanupUI();
  scheduleGenerationDraftSave();
  return true;
}

function maskEditorBrushRadius() {
  return Math.max(2, Number($('generation-mask-brush-size')?.value || 26) || 26);
}


function clampMaskEditorZoom(value) {
  const minZoom = generationMaskEditorState.minZoom || 1;
  const maxZoom = generationMaskEditorState.maxZoom || 8;
  return Math.min(maxZoom, Math.max(minZoom, Number(value) || 1));
}

function updateMaskEditorZoomLabel() {
  const label = $('generation-mask-zoom-label');
  if (label) label.textContent = `${Math.round((generationMaskEditorState.zoom || 1) * 100)}%`;
}

function applyMaskEditorZoom(value, anchorEvent=null) {
  const baseCanvas = $('generation-mask-base-canvas');
  const drawCanvas = $('generation-mask-draw-canvas');
  const stage = document.querySelector('.generation-mask-editor-stage');
  if (!baseCanvas || !drawCanvas) return;
  const oldZoom = generationMaskEditorState.zoom || 1;
  const nextZoom = clampMaskEditorZoom(value);
  generationMaskEditorState.zoom = nextZoom;
  const baseW = generationMaskEditorState.displayWidth || baseCanvas.width || 1;
  const baseH = generationMaskEditorState.displayHeight || baseCanvas.height || 1;
  const width = Math.max(1, Math.round(baseW * nextZoom));
  const height = Math.max(1, Math.round(baseH * nextZoom));
  const anchor = stage && anchorEvent ? {
    x: anchorEvent.clientX - stage.getBoundingClientRect().left + stage.scrollLeft,
    y: anchorEvent.clientY - stage.getBoundingClientRect().top + stage.scrollTop,
  } : null;
  baseCanvas.style.width = `${width}px`;
  baseCanvas.style.height = `${height}px`;
  drawCanvas.style.width = `${width}px`;
  drawCanvas.style.height = `${height}px`;
  if (stage) {
    stage.style.width = `${Math.min(width, Math.round(window.innerWidth * 0.9))}px`;
    stage.style.height = `${Math.min(height, Math.round(window.innerHeight * 0.72))}px`;
    if (anchor && oldZoom > 0) {
      const ratio = nextZoom / oldZoom;
      stage.scrollLeft = Math.max(0, anchor.x * ratio - (anchorEvent.clientX - stage.getBoundingClientRect().left));
      stage.scrollTop = Math.max(0, anchor.y * ratio - (anchorEvent.clientY - stage.getBoundingClientRect().top));
    }
  }
  updateMaskBrushCursorSize();
  updateMaskEditorZoomLabel();
}

function resetMaskEditorZoom() {
  applyMaskEditorZoom(1);
  const stage = document.querySelector('.generation-mask-editor-stage');
  if (stage) { stage.scrollLeft = 0; stage.scrollTop = 0; }
}

function handleMaskEditorWheel(event) {
  if (!$('generation-mask-editor-modal') || $('generation-mask-editor-modal').classList.contains('hidden')) return;
  event.preventDefault();
  const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  applyMaskEditorZoom((generationMaskEditorState.zoom || 1) * factor, event);
}

function startMaskEditorPan(event) {
  const stage = document.querySelector('.generation-mask-editor-stage');
  if (!stage) return false;
  if (!(event.button === 1 || event.buttons === 4 || generationMaskEditorState.spaceDown || event.shiftKey)) return false;
  event.preventDefault();
  generationMaskEditorState.panning = true;
  generationMaskEditorState.panLast = { x:event.clientX, y:event.clientY, scrollLeft:stage.scrollLeft, scrollTop:stage.scrollTop };
  stage.classList.add('is-panning');
  hideMaskBrushCursor();
  return true;
}

function moveMaskEditorPan(event) {
  const stage = document.querySelector('.generation-mask-editor-stage');
  const last = generationMaskEditorState.panLast;
  if (!stage || !generationMaskEditorState.panning || !last) return false;
  event.preventDefault();
  stage.scrollLeft = last.scrollLeft - (event.clientX - last.x);
  stage.scrollTop = last.scrollTop - (event.clientY - last.y);
  return true;
}

function endMaskEditorPan() {
  generationMaskEditorState.panning = false;
  generationMaskEditorState.panLast = null;
  document.querySelector('.generation-mask-editor-stage')?.classList.remove('is-panning');
}

function updateMaskBrushLabel() {
  const radius = maskEditorBrushRadius();
  if ($('generation-mask-brush-size-label')) $('generation-mask-brush-size-label').textContent = `${radius} px`;
  updateMaskBrushCursorSize();
}

function getMaskEditorCanvases() {
  return {
    base: $('generation-mask-base-canvas'),
    draw: $('generation-mask-draw-canvas'),
    exportCanvas: generationMaskEditorState.exportCanvas,
  };
}

function fillMaskCanvasBlack(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function clearMaskPreviewCanvas(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function drawPreviewMaskDot(x, y, mode='paint') {
  const draw = $('generation-mask-draw-canvas');
  if (!draw) return;
  const ctx = draw.getContext('2d');
  const r = maskEditorBrushRadius();
  ctx.save();
  ctx.globalCompositeOperation = mode === 'erase' ? 'destination-out' : 'source-over';
  ctx.fillStyle = 'rgba(255, 72, 72, 0.45)';
  ctx.beginPath();
  ctx.arc(x, y, r / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawPreviewMaskLine(from, to, mode='paint') {
  const draw = $('generation-mask-draw-canvas');
  if (!draw || !from || !to) return;
  const ctx = draw.getContext('2d');
  const r = maskEditorBrushRadius();
  ctx.save();
  ctx.globalCompositeOperation = mode === 'erase' ? 'destination-out' : 'source-over';
  ctx.strokeStyle = 'rgba(255, 72, 72, 0.45)';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = r;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  ctx.restore();
}

function drawExportMaskDot(x, y, mode='paint') {
  const exportCanvas = generationMaskEditorState.exportCanvas;
  if (!exportCanvas) return;
  const ctx = exportCanvas.getContext('2d');
  const scale = generationMaskEditorState.displayScale || 1;
  const r = maskEditorBrushRadius();
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = mode === 'erase' ? '#000' : '#fff';
  ctx.beginPath();
  ctx.arc(x / scale, y / scale, (r / scale) / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawExportMaskLine(from, to, mode='paint') {
  const exportCanvas = generationMaskEditorState.exportCanvas;
  if (!exportCanvas || !from || !to) return;
  const ctx = exportCanvas.getContext('2d');
  const scale = generationMaskEditorState.displayScale || 1;
  const r = maskEditorBrushRadius();
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.strokeStyle = mode === 'erase' ? '#000' : '#fff';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = r / scale;
  ctx.beginPath();
  ctx.moveTo(from.x / scale, from.y / scale);
  ctx.lineTo(to.x / scale, to.y / scale);
  ctx.stroke();
  ctx.restore();
}

function drawMaskDot(x, y, mode='paint') {
  drawPreviewMaskDot(x, y, mode);
  drawExportMaskDot(x, y, mode);
}

function drawMaskLine(from, to, mode='paint') {
  drawPreviewMaskLine(from, to, mode);
  drawExportMaskLine(from, to, mode);
}

function pointerPosInCanvas(canvas, event) {
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) * ((canvas.width || rect.width || 1) / (rect.width || canvas.width || 1));
  const y = (event.clientY - rect.top) * ((canvas.height || rect.height || 1) / (rect.height || canvas.height || 1));
  return { x, y };
}

function invertMaskEditorCanvas(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const v = 255 - data[i];
    data[i] = v; data[i+1] = v; data[i+2] = v; data[i+3] = 255;
  }
  ctx.putImageData(imageData, 0, 0);
}

function syncMaskPreviewFromExport() {
  const drawCanvas = $('generation-mask-draw-canvas');
  const exportCanvas = generationMaskEditorState.exportCanvas;
  if (!drawCanvas || !exportCanvas) return;
  const ctx = drawCanvas.getContext('2d');
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
  ctx.drawImage(exportCanvas, 0, 0, drawCanvas.width, drawCanvas.height);
  const imageData = ctx.getImageData(0, 0, drawCanvas.width, drawCanvas.height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const v = data[i];
    if (v > 8) {
      data[i] = 255;
      data[i + 1] = 72;
      data[i + 2] = 72;
      data[i + 3] = Math.min(220, Math.max(80, Math.round(v * 0.58)));
    } else {
      data[i] = 0;
      data[i + 1] = 0;
      data[i + 2] = 0;
      data[i + 3] = 0;
    }
  }
  ctx.putImageData(imageData, 0, 0);
  ctx.restore();
}

function getMaskBrushModeFromEvent(event) {
  if (!event) return 'paint';
  if (event.button === 2 || (typeof event.buttons === 'number' && (event.buttons & 2))) return 'erase';
  if (event.altKey || event.ctrlKey || event.metaKey) return 'erase';
  return 'paint';
}

function updateMaskBrushCursorSize() {
  const cursor = $('generation-mask-brush-cursor');
  if (!cursor) return;
  const size = Math.max(6, maskEditorBrushRadius() * (generationMaskEditorState.zoom || 1));
  cursor.style.width = `${size}px`;
  cursor.style.height = `${size}px`;
}

function updateMaskBrushCursor(event) {
  const drawCanvas = $('generation-mask-draw-canvas');
  const cursor = $('generation-mask-brush-cursor');
  if (!drawCanvas || !cursor) return;
  const rect = drawCanvas.getBoundingClientRect();
  const stage = document.querySelector('.generation-mask-editor-stage');
  const stageRect = stage ? stage.getBoundingClientRect() : rect;
  const renderedX = event.clientX - stageRect.left + (stage ? stage.scrollLeft : 0);
  const renderedY = event.clientY - stageRect.top + (stage ? stage.scrollTop : 0);
  cursor.classList.remove('hidden');
  cursor.style.left = `${renderedX}px`;
  cursor.style.top = `${renderedY}px`;
  const mode = generationMaskEditorState.drawing ? generationMaskEditorState.brushMode : getMaskBrushModeFromEvent(event);
  cursor.classList.toggle('is-erasing', mode === 'erase');
}



function bindGenerationControlnetPreviewFirstButtons() {
  const primaryBuild = $('btn-generation-controlnet-build-map');
  if (primaryBuild && !primaryBuild.dataset.neoPreviewFirstBound) {
    primaryBuild.dataset.neoPreviewFirstBound = '1';
    primaryBuild.addEventListener('click', () => buildGenerationControlnetMap({ row: null }));
  }
  const primaryApply = $('btn-generation-controlnet-apply-map');
  if (primaryApply && !primaryApply.dataset.neoPreviewFirstBound) {
    primaryApply.dataset.neoPreviewFirstBound = '1';
    primaryApply.addEventListener('click', () => applyPendingGenerationControlnetMap(getGenerationControlnetContext(null)));
  }
  const primaryDownload = $('btn-generation-controlnet-download-map');
  if (primaryDownload && !primaryDownload.dataset.neoPreviewFirstBound) {
    primaryDownload.dataset.neoPreviewFirstBound = '1';
    primaryDownload.addEventListener('click', () => downloadPendingGenerationControlnetMap(getGenerationControlnetContext(null)));
  }
  const primaryControlImage = $('generation-control-image');
  if (primaryControlImage && !primaryControlImage.dataset.neoPreviewFirstImageBound) {
    primaryControlImage.dataset.neoPreviewFirstImageBound = '1';
    primaryControlImage.addEventListener('change', () => refreshGenerationControlnetSourcePreview(getGenerationControlnetContext(null)));
  }
  const primarySourceImage = $('generation-source-image');
  if (primarySourceImage && !primarySourceImage.dataset.neoControlnetSourcePreviewBound) {
    primarySourceImage.dataset.neoControlnetSourcePreviewBound = '1';
    primarySourceImage.addEventListener('change', refreshAllGenerationControlnetSourcePreviews);
  }
  refreshGenerationControlnetSourcePreview(getGenerationControlnetContext(null));
}

bindGenerationControlnetPreviewFirstButtons();
document.addEventListener('DOMContentLoaded', bindGenerationControlnetPreviewFirstButtons);
setTimeout(bindGenerationControlnetPreviewFirstButtons, 250);


/* Neo Studio Patch 63: ControlNet model dropdown + enabled badge sync real fix */
(function neoControlnetPhase63Fix(){
  const $neo = (id) => document.getElementById(id);

  function neoSelectItemValue(item) {
    try {
      if (typeof generationSelectItemValue === 'function') return generationSelectItemValue(item);
    } catch (_) {}
    if (item && typeof item === 'object') return String(item.value || item.name || item.filename || item.path || item.title || '').trim();
    return String(item || '').trim();
  }

  function neoSelectItemLabel(item) {
    try {
      if (typeof generationSelectItemLabel === 'function') return generationSelectItemLabel(item);
    } catch (_) {}
    if (item && typeof item === 'object') return String(item.label || item.name || item.filename || item.value || item.path || item.title || '').trim();
    return String(item || '').trim();
  }

  function neoNormalizeModelList(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value.filter(Boolean);
    if (typeof value === 'object') {
      const keys = ['controlnet','controlnets','control_net','controlnet_models','controlnetModels','models','items','files','names'];
      for (const key of keys) {
        const nested = value[key];
        if (Array.isArray(nested) && nested.length) return nested.filter(Boolean);
      }
    }
    return [];
  }

  function neoFindControlnetModelsInObject(root, seen=new Set()) {
    if (!root || typeof root !== 'object' || seen.has(root)) return [];
    seen.add(root);
    const direct = neoNormalizeModelList(root);
    if (direct.length) return direct;
    const preferredKeys = ['catalog','models','model_catalog','data','payload','result'];
    for (const key of preferredKeys) {
      const found = neoFindControlnetModelsInObject(root[key], seen);
      if (found.length) return found;
    }
    for (const [key, value] of Object.entries(root)) {
      if (String(key).toLowerCase().includes('control') && String(key).toLowerCase().includes('net')) {
        const found = neoNormalizeModelList(value);
        if (found.length) return found;
      }
    }
    return [];
  }

  window.NeoGenerationControlnetModels = window.NeoGenerationControlnetModels || [];

  window.neoGetGenerationControlnetModelItems = function neoGetGenerationControlnetModelItems() {
    const pooled = [];
    if (Array.isArray(window.NeoGenerationControlnetModels)) pooled.push(...window.NeoGenerationControlnetModels);
    try {
      if (typeof generationCatalogState !== 'undefined' && generationCatalogState) {
        const found = neoFindControlnetModelsInObject(generationCatalogState);
        if (found.length) pooled.push(...found);
      }
    } catch (_) {}
    const globals = [window.generationCatalogState, window.NeoGenerationCatalog, window.NeoStudioGenerationCatalog, window.NeoGenerationCatalogState];
    globals.forEach(obj => {
      const found = neoFindControlnetModelsInObject(obj);
      if (found.length) pooled.push(...found);
    });
    const seen = new Set();
    return pooled.filter(item => {
      const value = neoSelectItemValue(item);
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  };

  function neoFillControlnetModelSelect(selectEl, placeholder='None') {
    if (!selectEl) return;
    const current = String(selectEl.value || '').trim();
    const models = window.neoGetGenerationControlnetModelItems();
    selectEl.innerHTML = '';
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = models.length ? placeholder : 'Loading ControlNet models…';
    selectEl.appendChild(opt0);
    models.forEach(item => {
      const opt = document.createElement('option');
      opt.value = neoSelectItemValue(item);
      opt.textContent = neoSelectItemLabel(item) || opt.value;
      if (current && current === opt.value) opt.selected = true;
      selectEl.appendChild(opt);
    });
    if (current && !selectEl.value) {
      const missing = document.createElement('option');
      missing.value = current;
      missing.textContent = current;
      missing.selected = true;
      selectEl.appendChild(missing);
    }
  }

  window.refreshGenerationControlnetModelSelect = function refreshGenerationControlnetModelSelect(selectEl, placeholder='None') {
    neoFillControlnetModelSelect(selectEl, placeholder);
  };

  window.refreshPrimaryGenerationControlnetModelFilter = function refreshPrimaryGenerationControlnetModelFilter() {
    neoFillControlnetModelSelect($neo('generation-controlnet-name'), 'None');
    try { updatePrimaryGenerationControlnetSummary(); } catch (_) {}
    neoSyncControlnetEnabledBadges();
  };

  window.refreshGenerationControlnetModelFilterForRow = function refreshGenerationControlnetModelFilterForRow(row) {
    if (!row) return;
    neoFillControlnetModelSelect(row.querySelector('.generation-controlnet-name'), 'None');
    try { updateGenerationControlnetRowSummary(row); } catch (_) {}
    neoSyncControlnetEnabledBadges();
  };

  function neoRefreshAllControlnetModelDropdowns() {
    window.refreshPrimaryGenerationControlnetModelFilter();
    document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => window.refreshGenerationControlnetModelFilterForRow(row));
  }

  async function neoLoadControlnetCatalogFallback() {
    if (window.NeoGenerationControlnetModels && window.NeoGenerationControlnetModels.length) {
      neoRefreshAllControlnetModelDropdowns();
      return;
    }
    try {
      const res = await fetch('/api/generation/catalog', { cache: 'no-store' });
      if (!res.ok) throw new Error('catalog HTTP ' + res.status);
      const data = await res.json();
      const found = neoFindControlnetModelsInObject(data);
      if (found.length) {
        window.NeoGenerationControlnetModels = found;
      }
    } catch (err) {
      console.warn('[Neo] ControlNet catalog fallback failed:', err);
    }
    neoRefreshAllControlnetModelDropdowns();
  }

  function neoControlnetEnabledCount() {
    let count = 0;
    const primary = $neo('generation-controlnet-enabled');
    if (primary && primary.checked) count += 1;
    document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => {
      const box = row.querySelector('.generation-unit-enabled');
      if (!box || box.checked) count += 1;
    });
    return count;
  }

  function neoFindControlnetSection() {
    const primary = $neo('generation-controlnet-enabled') || $neo('generation-controlnet-name') || $neo('generation-controlnet-unit');
    let node = primary;
    while (node && node !== document.body) {
      const text = String(node.textContent || '');
      if (text.includes('ControlNet') && node.querySelector && node.querySelector('#generation-controlnet-enabled')) return node;
      node = node.parentElement;
    }
    return primary?.closest?.('section, .card, .panel, .accordion-card, .generation-card') || document;
  }

  window.neoSyncControlnetEnabledBadges = function neoSyncControlnetEnabledBadges() {
    const section = neoFindControlnetSection();
    if (!section || !section.querySelector) return;
    const count = neoControlnetEnabledCount();
    const enabled = count > 0;
    const leaves = Array.from(section.querySelectorAll('span, div, strong, b')).filter(el => {
      if (el.children && el.children.length) return false;
      const text = String(el.textContent || '').trim();
      return /^(Disabled|Enabled|\d+\s+enabled)$/i.test(text);
    });
    const statusEl = leaves.find(el => /^(Disabled|Enabled)$/i.test(String(el.textContent || '').trim()));
    if (statusEl) {
      statusEl.textContent = enabled ? 'Enabled' : 'Disabled';
      statusEl.classList.toggle('is-enabled', enabled);
      statusEl.classList.toggle('is-disabled', !enabled);
    }
    const countEl = leaves.find(el => /^\d+\s+enabled$/i.test(String(el.textContent || '').trim()));
    if (countEl) countEl.textContent = `${count} enabled`;
  };

  function neoBindControlnetPhase63() {
    const primary = $neo('generation-controlnet-enabled');
    if (primary && !primary.dataset.neoBadgeSyncBound) {
      primary.dataset.neoBadgeSyncBound = '1';
      primary.addEventListener('change', () => {
        try { updatePrimaryGenerationControlnetSummary(); } catch (_) {}
        neoSyncControlnetEnabledBadges();
      });
    }
    document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row .generation-unit-enabled').forEach(box => {
      if (box.dataset.neoBadgeSyncBound) return;
      box.dataset.neoBadgeSyncBound = '1';
      box.addEventListener('change', neoSyncControlnetEnabledBadges);
    });
    neoRefreshAllControlnetModelDropdowns();
    neoSyncControlnetEnabledBadges();
  }

  document.addEventListener('change', event => {
    const target = event.target;
    if (target && target.matches && target.matches('#generation-controlnet-enabled, #generation-controlnet-extra-list .generation-unit-enabled')) {
      setTimeout(neoSyncControlnetEnabledBadges, 0);
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    neoBindControlnetPhase63();
    neoLoadControlnetCatalogFallback();
  });
  setTimeout(() => { neoBindControlnetPhase63(); neoLoadControlnetCatalogFallback(); }, 100);
  setTimeout(() => { neoBindControlnetPhase63(); neoLoadControlnetCatalogFallback(); }, 900);
})();

/* Neo Studio Patch 64: Phase 4 — Smart Control Type presets */
(function(){
  'use strict';
  if (window.__neoControlNetPhase4PresetsInstalled) return;
  window.__neoControlNetPhase4PresetsInstalled = true;

  const PRESETS = {
    none: {
      label: 'No preset / manual',
      hint: 'Manual ControlNet setup. Choose unit, preprocessor, model, and strength yourself.',
    },
    keep_pose: {
      label: 'Keep character pose',
      unit: 'openpose', preprocessor: 'openpose', strength: 0.85, detect: 768,
      openpose: { body:true, hand:true, face:false },
      modelKeywords: ['openpose', 'pose', 'union'],
      hint: 'Best for preserving body pose while allowing outfit, style, lighting, and background changes.',
    },
    keep_scene_layout: {
      label: 'Keep scene / camera layout',
      unit: 'depth', preprocessor: 'depth_midas', strength: 0.70, detect: 1024,
      modelKeywords: ['depth', 'union'],
      hint: 'Best for keeping room/camera composition and subject silhouette. MiDaS gives a Forge-like depth map.',
    },
    keep_edges: {
      label: 'Keep object edges',
      unit: 'canny', preprocessor: 'canny', strength: 0.60, detect: 768,
      canny: { low:100, high:200 },
      modelKeywords: ['canny', 'union'],
      hint: 'Best for products, props, vehicles, logos, and hard outlines. Can be too rigid on faces.',
    },
    anime_redraw: {
      label: 'Anime / illustration redraw',
      unit: 'lineart', preprocessor: 'lineart_anime', strength: 0.75, detect: 1024,
      modelKeywords: ['lineart', 'anime', 'union'],
      hint: 'Best for anime-style redraws. Pair with Depth if you need stronger composition lock.',
    },
    realistic_redraw: {
      label: 'Realistic redraw / soft structure',
      unit: 'softedge', preprocessor: 'softedge', strength: 0.55, detect: 768,
      modelKeywords: ['softedge', 'hed', 'union'],
      hint: 'Good balance for realistic edits where Canny feels too sharp or crunchy.',
    },
    face_body_consistency: {
      label: 'Face/body composition lock',
      unit: 'openpose', preprocessor: 'openpose', strength: 0.75, detect: 768,
      openpose: { body:true, hand:true, face:true },
      modelKeywords: ['openpose', 'pose', 'union'],
      hint: 'Keeps pose with face landmarks enabled. Use with IP-Adapter/FaceID for actual identity matching.',
    },
    upscale_refine: {
      label: 'Upscale / detail preservation',
      unit: 'tile', preprocessor: 'none', strength: 0.35, detect: 768,
      modelKeywords: ['tile', 'union'],
      hint: 'Uses source/control image directly. Best for upscales, redraw polish, and detail preservation.',
    },
    strong_composition: {
      label: 'Strong composition lock',
      unit: 'depth', preprocessor: 'depth_midas', strength: 0.85, detect: 1024,
      modelKeywords: ['depth', 'union'],
      hint: 'Locks composition harder with depth. Add Canny/OpenPose as extra units if needed.',
    },
  };

  function qs(root, selector){ return (root || document).querySelector(selector); }
  function qsa(root, selector){ return Array.from((root || document).querySelectorAll(selector)); }
  function norm(v){ return String(v || '').trim().toLowerCase(); }
  function titleOf(preset){ return PRESETS[preset]?.label || PRESETS.none.label; }

  function getControlRoot(row){ return row || qs(document, '.generation-unit-card-controlnet[data-primary="true"]') || document; }
  function getField(root, cls, id){ return root ? (qs(root, cls) || (id ? document.getElementById(id) : null)) : (id ? document.getElementById(id) : null); }
  function isPrimaryRoot(root){ return !!(root && root.matches && root.matches('.generation-unit-card-controlnet[data-primary="true"]')); }

  function setSelectValue(select, wanted){
    if (!select) return false;
    const target = norm(wanted);
    const options = Array.from(select.options || []);
    let match = options.find(o => norm(o.value) === target);
    if (!match) match = options.find(o => norm(o.textContent).includes(target));
    if (!match && target === 'softedge') match = options.find(o => norm(o.value).includes('soft') || norm(o.textContent).includes('soft'));
    if (!match && target === 'lineart_anime') match = options.find(o => norm(o.value).includes('anime') || norm(o.textContent).includes('anime'));
    if (!match && target === 'depth_midas') match = options.find(o => norm(o.value).includes('midas') || norm(o.textContent).includes('midas'));
    if (!match && target === 'tile') match = options.find(o => norm(o.value).includes('tile') || norm(o.textContent).includes('tile'));
    if (!match) return false;
    select.value = match.value;
    select.dispatchEvent(new Event('change', { bubbles:true }));
    return true;
  }

  function allModelOptions(select){ return Array.from(select?.options || []).filter(o => String(o.value || '').trim()); }
  function modelScore(option, keywords){
    const text = norm(`${option.textContent || ''} ${option.value || ''}`);
    let score = 0;
    (keywords || []).forEach((kw, idx) => {
      const k = norm(kw);
      if (!k) return;
      if (text.includes(k)) score += 100 - idx * 5;
    });
    if (text.includes('xl') || text.includes('sdxl')) score += 12;
    if (text.includes('promax') || text.includes('union')) score += 10;
    if (text.includes('sd15')) score -= 2;
    return score;
  }

  function pickBestModel(select, keywords){
    if (!select) return false;
    const options = allModelOptions(select);
    if (!options.length) return false;
    const ranked = options.map(o => ({ o, score:modelScore(o, keywords) })).sort((a,b) => b.score - a.score);
    if (!ranked.length || ranked[0].score <= 0) return false;
    select.value = ranked[0].o.value;
    select.dispatchEvent(new Event('change', { bubbles:true }));
    return true;
  }

  function setInputValue(input, value){
    if (!input || value === undefined || value === null) return;
    input.value = String(value);
    input.dispatchEvent(new Event('input', { bubbles:true }));
    input.dispatchEvent(new Event('change', { bubbles:true }));
  }
  function setCheck(input, checked){
    if (!input || checked === undefined) return;
    input.checked = !!checked;
    input.dispatchEvent(new Event('change', { bubbles:true }));
  }

  function applyPresetToRoot(root, key){
    const preset = PRESETS[key] || PRESETS.none;
    if (!root || key === 'none') {
      updatePresetHint(root, key);
      return;
    }
    const primary = isPrimaryRoot(root);
    const unit = getField(root, '.generation-controlnet-unit', primary ? 'generation-controlnet-unit' : null);
    const prep = getField(root, '.generation-controlnet-preprocessor', primary ? 'generation-controlnet-preprocessor' : null);
    const model = getField(root, '.generation-controlnet-name', primary ? 'generation-controlnet-name' : null);
    const strength = getField(root, '.generation-controlnet-strength', primary ? 'generation-controlnet-strength' : null);

    if (preset.unit) setSelectValue(unit, preset.unit);
    // Preprocessor options are filtered after unit change; defer one tick so the target option exists.
    setTimeout(() => {
      if (preset.preprocessor) setSelectValue(prep, preset.preprocessor);
      if (preset.strength !== undefined) setInputValue(strength, preset.strength);
      if (preset.detect) setSelectValue(getField(root, '.generation-controlnet-detect-resolution', primary ? 'generation-controlnet-detect-resolution' : null), String(preset.detect));
      if (preset.canny) {
        setInputValue(getField(root, '.generation-controlnet-canny-low', primary ? 'generation-controlnet-canny-low' : null), preset.canny.low);
        setInputValue(getField(root, '.generation-controlnet-canny-high', primary ? 'generation-controlnet-canny-high' : null), preset.canny.high);
      }
      if (preset.openpose) {
        setCheck(getField(root, '.generation-controlnet-openpose-body', primary ? 'generation-controlnet-openpose-body' : null), preset.openpose.body);
        setCheck(getField(root, '.generation-controlnet-openpose-hand', primary ? 'generation-controlnet-openpose-hand' : null), preset.openpose.hand);
        setCheck(getField(root, '.generation-controlnet-openpose-face', primary ? 'generation-controlnet-openpose-face' : null), preset.openpose.face);
      }
      if (!pickBestModel(model, preset.modelKeywords || [])) {
        const hint = qs(root, '.generation-controlnet-preset-hint');
        if (hint) hint.textContent = `${preset.hint || ''} Model auto-match did not find a clear model; choose the matching ControlNet model manually.`;
      }
      updatePresetHint(root, key);
      try { if (typeof updatePrimaryGenerationControlnetSummary === 'function') updatePrimaryGenerationControlnetSummary(); } catch(_) {}
      try { if (typeof updateGenerationControlnetRowSummary === 'function' && !primary) updateGenerationControlnetRowSummary(root); } catch(_) {}
      try { if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave(); } catch(_) {}
    }, 60);
  }

  function updatePresetHint(root, key){
    const hint = qs(root, '.generation-controlnet-preset-hint');
    if (!hint) return;
    const preset = PRESETS[key] || PRESETS.none;
    hint.textContent = preset.hint || '';
  }

  function buildPresetOptions(selected='none'){
    return Object.entries(PRESETS).map(([key, preset]) => `<option value="${key}" ${key === selected ? 'selected' : ''}>${preset.label}</option>`).join('');
  }

  function injectPresetControls(root){
    root = getControlRoot(root);
    if (!root || root.dataset.neoPhase4PresetReady === '1') return;
    const unitField = qs(root, '.generation-controlnet-unit')?.closest('div');
    if (!unitField) return;
    const wrap = document.createElement('div');
    wrap.className = 'generation-controlnet-preset-wrap';
    wrap.style.cssText = 'grid-column:1 / -1; display:grid; grid-template-columns:minmax(220px,360px) 1fr; gap:10px; align-items:end; margin-bottom:2px;';
    wrap.innerHTML = `
      <div>
        <label>Smart control preset</label>
        <select class="generation-controlnet-smart-preset">${buildPresetOptions('none')}</select>
      </div>
      <div class="mini-note generation-controlnet-preset-hint" style="align-self:center;">Pick a task preset to auto-fill unit, preprocessor, strength, map settings, and best-match model.</div>`;
    unitField.parentNode.insertBefore(wrap, unitField);
    const select = qs(wrap, '.generation-controlnet-smart-preset');
    select?.addEventListener('change', () => applyPresetToRoot(root, select.value));
    root.dataset.neoPhase4PresetReady = '1';
  }

  function injectAll(){
    injectPresetControls(qs(document, '.generation-unit-card-controlnet[data-primary="true"]'));
    qsa(document, '#generation-controlnet-extra-list .generation-controlnet-row').forEach(injectPresetControls);
    try { if (typeof normalizeGenerationControlnetExtraLayout === 'function') normalizeGenerationControlnetExtraLayout(); } catch(_) {}
  }

  // Add a compact preset API for later workflow buttons / Scene Director hooks.
  window.NeoControlNetPresets = {
    list: () => Object.entries(PRESETS).map(([value, item]) => ({ value, label:item.label, hint:item.hint })),
    applyToPrimary: key => applyPresetToRoot(qs(document, '.generation-unit-card-controlnet[data-primary="true"]'), key),
    applyToRow: (row, key) => applyPresetToRoot(row, key),
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', injectAll);
  else setTimeout(injectAll, 0);

  const observer = new MutationObserver(() => injectAll());
  observer.observe(document.documentElement, { childList:true, subtree:true });
})();


// Phase 5 — Real ControlNet settings panel polish
(function(){
  function q(root, sel){ return (root || document).querySelector(sel); }
  function qa(root, sel){ return Array.from((root || document).querySelectorAll(sel)); }
  function rootOf(el){ return el?.closest?.('.generation-controlnet-row, .generation-unit-card-controlnet') || document; }
  function prepValue(root){ return (q(root, '.generation-controlnet-preprocessor') || q(document, '#generation-controlnet-preprocessor'))?.value || 'none'; }
  function showSetting(el, show){ if (!el) return; el.style.display = show ? '' : 'none'; }
  window.NeoPhase5ControlNetRefreshSettings = function(root=document){
    root = rootOf(root === document ? q(document, '#generation-controlnet-preprocessor') : root) || document;
    const prep = String(prepValue(root)).toLowerCase();
    const isCanny = prep.includes('canny');
    const isPose = prep.includes('pose') || prep.includes('openpose') || prep.includes('dwpose');
    const isNone = prep === 'none' || prep === '';
    qa(root, '[data-cn-setting="canny"]').forEach(el => showSetting(el, isCanny));
    qa(root, '[data-cn-setting="openpose"]').forEach(el => showSetting(el, isPose));
    qa(root, '[data-cn-setting="quality"]').forEach(el => showSetting(el, !isNone));
    qa(root, '[data-cn-setting="output"]').forEach(el => showSetting(el, !isNone));
    const hint = q(root, '.generation-controlnet-settings-hint');
    if (hint) {
      if (isCanny) hint.textContent = 'Canny settings are active. Lower thresholds catch more edges; higher thresholds keep only stronger edges.';
      else if (isPose) hint.textContent = 'OpenPose/DWPose settings are active. Enable hands/face only when you need those details; they can slow the map build.';
      else if (prep.includes('depth')) hint.textContent = 'Depth settings are active. Detect res changes depth quality; MiDaS usually gives Forge-style silhouettes.';
      else if (isNone) hint.textContent = 'No preprocessor selected. Timing/fit still apply when using a direct uploaded control image.';
      else hint.textContent = 'Map quality settings are active for this preprocessor. Higher detect res can improve structure but runs slower.';
    }
  };
  function refreshAll(){
    window.NeoPhase5ControlNetRefreshSettings(document);
    qa(document, '#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => window.NeoPhase5ControlNetRefreshSettings(row));
  }
  document.addEventListener('change', (event) => {
    const target = event.target;
    if (target?.matches?.('#generation-controlnet-preprocessor, .generation-controlnet-preprocessor, #generation-controlnet-unit, .generation-controlnet-unit')) {
      setTimeout(() => window.NeoPhase5ControlNetRefreshSettings(rootOf(target)), 0);
    }
  }, true);
  document.addEventListener('DOMContentLoaded', () => setTimeout(refreshAll, 300));
  setTimeout(refreshAll, 1200);
})();

// Phase 6 — Multi-ControlNet stack hardening (non-blocking loader fix)
(function(){
  if (window.__neoControlNetPhase6StackInstalled) return;
  window.__neoControlNetPhase6StackInstalled = true;

  const $ = id => document.getElementById(id);
  const qa = (root, sel) => Array.from((root || document).querySelectorAll(sel));
  const q = (root, sel) => (root || document).querySelector(sel);
  const trim = value => String(value ?? '').trim();
  const bool = el => !!el && !el.disabled && !!el.checked;
  const num = (el, fallback) => {
    const value = Number(el?.value);
    return Number.isFinite(value) ? value : fallback;
  };
  const primaryRoot = () => q(document, '.generation-unit-card-controlnet[data-primary="true"]');
  const rowRoots = () => [primaryRoot(), ...qa(document, '#generation-controlnet-extra-list .generation-controlnet-row')].filter(Boolean);
  const isPrimary = root => !!root?.matches?.('.generation-unit-card-controlnet[data-primary="true"]');
  const enabledForRoot = root => isPrimary(root) ? bool($('generation-controlnet-enabled')) : bool(q(root, '.generation-unit-enabled'));
  const uidForRoot = root => isPrimary(root) ? 'primary' : (root?.dataset?.uid || `control_${Math.random().toString(36).slice(2, 8)}`);
  const field = (root, cls, id) => isPrimary(root) ? ($(id) || q(root, cls)) : q(root, cls);
  const fileForRoot = root => field(root, '.generation-control-image', 'generation-control-image')?.files?.[0] || null;

  function readUnit(root){
    if (!root) return null;
    const primary = isPrimary(root);
    const uid = uidForRoot(root);
    const fileInput = field(root, '.generation-control-image', 'generation-control-image');
    return {
      uid,
      enabled: enabledForRoot(root),
      image_field: primary ? 'control_image' : `control_image__${uid}`,
      has_image: !!(fileInput?.files?.[0]),
      unit: trim(field(root, '.generation-controlnet-unit', 'generation-controlnet-unit')?.value || 'auto'),
      preprocessor: trim(field(root, '.generation-controlnet-preprocessor', 'generation-controlnet-preprocessor')?.value || 'none'),
      model: trim(field(root, '.generation-controlnet-name', 'generation-controlnet-name')?.value || ''),
      strength: num(field(root, '.generation-controlnet-strength', 'generation-controlnet-strength'), 1.0),
      start_percent: num(field(root, '.generation-controlnet-start-percent', 'generation-controlnet-start-percent'), 0.0),
      end_percent: num(field(root, '.generation-controlnet-end-percent', 'generation-controlnet-end-percent'), 1.0),
      fit_mode: trim(field(root, '.generation-controlnet-fit-mode', 'generation-controlnet-fit-mode')?.value || 'contain'),
      detect_resolution: num(field(root, '.generation-controlnet-detect-resolution', 'generation-controlnet-detect-resolution'), 768),
      safe_mode: trim(field(root, '.generation-controlnet-safe-mode', 'generation-controlnet-safe-mode')?.value || 'true') !== 'false',
      canny_low: num(field(root, '.generation-controlnet-canny-low', 'generation-controlnet-canny-low'), 100),
      canny_high: num(field(root, '.generation-controlnet-canny-high', 'generation-controlnet-canny-high'), 200),
      openpose_body: bool(field(root, '.generation-controlnet-openpose-body', 'generation-controlnet-openpose-body')),
      openpose_hand: bool(field(root, '.generation-controlnet-openpose-hand', 'generation-controlnet-openpose-hand')),
      openpose_face: bool(field(root, '.generation-controlnet-openpose-face', 'generation-controlnet-openpose-face')),
      invert_map: bool(field(root, '.generation-controlnet-invert-map', 'generation-controlnet-invert-map')),
      save_intermediate: bool(field(root, '.generation-controlnet-save-intermediate', 'generation-controlnet-save-intermediate')),
    };
  }

  function collectUnits({ enabledOnly=true } = {}){
    return rowRoots()
      .map(readUnit)
      .filter(unit => unit && (!enabledOnly || unit.enabled))
      .filter(unit => unit.model || unit.has_image || unit.preprocessor !== 'none');
  }

  function unitLabel(unit, index){
    const prep = unit.preprocessor && unit.preprocessor !== 'none' ? unit.preprocessor : 'direct image';
    const model = unit.model ? unit.model.split(/[\\/]/).pop() : 'no model';
    const state = unit.enabled ? 'on' : 'off';
    return `${String(index + 1).padStart(2, '0')} · ${state} · ${unit.unit || 'auto'} / ${prep} · ${model} · strength ${unit.strength}`;
  }

  let lastSummaryHtml = '';
  function renderSummary(){
    const host = $('generation-controlnet-stack-summary');
    const countBadge = $('generation-controlnet-stack-count');
    const units = collectUnits({ enabledOnly:false });
    const enabled = units.filter(u => u.enabled);
    const countText = `${enabled.length} enabled`;
    const html = units.length
      ? units.map((unit, index) => `<div>${unitLabel(unit, index)}</div>`).join('')
      : '<div>No ControlNet units configured yet.</div>';
    if (countBadge && countBadge.textContent !== countText) countBadge.textContent = countText;
    if (host && html !== lastSummaryHtml) {
      host.innerHTML = html;
      lastSummaryHtml = html;
    }
    const headerEnabled = document.querySelector('[data-controlnet-phase6-enabled-count]');
    if (headerEnabled && headerEnabled.textContent !== countText) headerEnabled.textContent = countText;
    try { if (typeof window.neoSyncControlnetEnabledBadges === 'function') window.neoSyncControlnetEnabledBadges(); } catch(_) {}
  }

  function ensurePhase6Panel(){
    const body = q(document, '[data-accordion-id="generation-controlnet-settings"] .accordion-body');
    if (!body || $('generation-controlnet-stack-summary')) return;
    const panel = document.createElement('div');
    panel.className = 'card-lite generation-controlnet-stack-panel';
    panel.style.cssText = 'margin-bottom:12px; padding:12px; border:1px solid rgba(96,165,250,.24); background:rgba(96,165,250,.055);';
    panel.innerHTML = `
      <div class="row-between" style="gap:10px; align-items:flex-start; flex-wrap:wrap;">
        <div>
          <div class="accordion-title" style="font-size:14px;">Multi-ControlNet stack</div>
          <div class="accordion-hint">Stack depth, pose, edges, lineart, tile, or direct maps. Every unit has its own image, model, strength, timing, and preview map.</div>
        </div>
        <span class="backend-chip" id="generation-controlnet-stack-count">0 enabled</span>
      </div>
      <div class="mini-note" id="generation-controlnet-stack-summary" style="margin-top:8px; line-height:1.55;">No ControlNet units configured yet.</div>`;
    body.insertBefore(panel, body.firstElementChild);
  }

  function addDuplicateButton(row){
    if (!row || row.dataset.neoPhase6DuplicateReady === '1') return;
    const actions = q(row, '.generation-unit-actions');
    if (!actions) return;
    const btn = document.createElement('button');
    btn.className = 'btn btn-small generation-controlnet-duplicate-row';
    btn.type = 'button';
    btn.textContent = 'Duplicate';
    btn.title = 'Duplicate this ControlNet unit without copying the browser file selection';
    const remove = q(actions, '.generation-remove-row');
    actions.insertBefore(btn, remove || null);
    btn.addEventListener('click', () => {
      const unit = readUnit(row) || {};
      const values = { unit: unit.unit, preprocessor: unit.preprocessor, model: unit.model, strength: unit.strength, enabled: unit.enabled };
      if (typeof window.NeoStudioApp?.generation?.workflow?.addControlnetRow === 'function') {
        window.NeoStudioApp.generation.workflow.addControlnetRow(values);
      } else if (typeof addGenerationControlnetRow === 'function') {
        addGenerationControlnetRow(values);
      }
      setTimeout(() => { decorateRows(); renderSummary(); }, 80);
    });
    row.dataset.neoPhase6DuplicateReady = '1';
  }

  function decorateRows(){
    rowRoots().forEach((root, index) => {
      const indexText = String(index + 1).padStart(2, '0');
      const indexEl = q(root, '.generation-unit-index');
      if (indexEl && indexEl.textContent !== indexText) indexEl.textContent = indexText;
      if (!isPrimary(root)) addDuplicateButton(root);
      const title = q(root, '.generation-unit-title');
      const nextTitle = isPrimary(root) ? 'Primary ControlNet unit' : `ControlNet unit ${index + 1}`;
      if (title && title.textContent !== nextTitle) title.textContent = nextTitle;
    });
  }

  function injectSettingsIntoFormData(input, init){
    const body = init?.body || input?.body;
    if (!(body instanceof FormData)) return;
    const url = String(input?.url || input || '');
    if (!url.includes('/api/generation/queue')) return;
    let payload = {};
    try { payload = JSON.parse(String(body.get('settings_json') || '{}')) || {}; } catch(_) { payload = {}; }
    const units = collectUnits({ enabledOnly:true });
    payload.controlnet_units = units;
    payload.controlnet_stack_enabled = units.length > 0;
    payload.controlnet_stack_count = units.length;
    body.set('settings_json', JSON.stringify(payload));
    rowRoots().forEach(root => {
      if (isPrimary(root) || !enabledForRoot(root)) return;
      const uid = uidForRoot(root);
      const file = fileForRoot(root);
      const key = `control_image__${uid}`;
      if (file && !body.has(key)) body.append(key, file, file.name || `${uid}.png`);
    });
  }

  if (!window.__neoPhase6FetchPatched) {
    window.__neoPhase6FetchPatched = true;
    const originalFetch = window.fetch;
    window.fetch = function(input, init){
      try { injectSettingsIntoFormData(input, init); } catch(err) { console.warn('[Neo] Phase 6 ControlNet payload injection failed:', err); }
      return originalFetch.apply(this, arguments);
    };
  }

  window.NeoControlNetStack = { collect: collectUnits, renderSummary, decorateRows, enabledCount: () => collectUnits({ enabledOnly:true }).length };

  let scheduled = false;
  function scheduleSync(delay=0){
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      ensurePhase6Panel();
      decorateRows();
      renderSummary();
    }, delay);
  }

  document.addEventListener('change', event => { if (event.target?.closest?.('[data-accordion-id="generation-controlnet-settings"]')) scheduleSync(0); }, true);
  document.addEventListener('input', event => { if (event.target?.closest?.('[data-accordion-id="generation-controlnet-settings"]')) scheduleSync(0); }, true);
  document.addEventListener('click', event => {
    if (event.target?.closest?.('#btn-generation-add-controlnet, .generation-remove-row, .generation-row-move-up, .generation-row-move-down')) scheduleSync(120);
  }, true);

  const observerRoot = document.body || document.documentElement;
  const observer = new MutationObserver((mutations) => {
    const relevant = mutations.some(m => Array.from(m.addedNodes || []).concat(Array.from(m.removedNodes || [])).some(node => {
      if (!node || node.nodeType !== 1) return false;
      return node.matches?.('#generation-controlnet-extra-list, .generation-controlnet-row, .generation-unit-card-controlnet, [data-accordion-id="generation-controlnet-settings"]') ||
             node.querySelector?.('#generation-controlnet-extra-list, .generation-controlnet-row, .generation-unit-card-controlnet, [data-accordion-id="generation-controlnet-settings"]');
    }));
    if (relevant) scheduleSync(60);
  });
  if (observerRoot) observer.observe(observerRoot, { childList:true, subtree:true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => scheduleSync(100));
  else scheduleSync(100);
})();


/* Neo Studio Patch 68: Phase 7 — Advanced-ControlNet mode */
(function(){
  if (window.__neoControlNetPhase7AdvancedInstalled) return;
  window.__neoControlNetPhase7AdvancedInstalled = true;
  const $ = id => document.getElementById(id);
  const q = (root, sel) => (root || document).querySelector(sel);
  const qa = (root, sel) => Array.from((root || document).querySelectorAll(sel));
  const trim = value => String(value ?? '').trim();
  const bool = el => !!(el && el.checked);
  const num = (el, fallback) => { const value = Number(el?.value); return Number.isFinite(value) ? value : fallback; };
  const isPrimary = root => !!root?.matches?.('.generation-unit-card-controlnet[data-primary="true"]');
  const rowRoots = () => [q(document, '.generation-unit-card-controlnet[data-primary="true"]'), ...qa(document, '#generation-controlnet-extra-list .generation-controlnet-row')].filter(Boolean);
  const uidForRoot = root => isPrimary(root) ? 'primary' : (root?.dataset?.uid || 'control_unknown');

  function ensureAdvancedPanel(root){
    if (!root || q(root, '.generation-controlnet-advanced-panel')) return;
    const settings = q(root, '.generation-controlnet-real-settings') || q(root, '.generation-controlnet-map-settings');
    if (!settings) return;
    const panel = document.createElement('details');
    panel.className = 'mini-advanced generation-controlnet-advanced-panel';
    panel.style.cssText = 'grid-column:1 / -1; margin-top:10px; padding:10px; border:1px solid rgba(168,85,247,.22); background:rgba(168,85,247,.055); border-radius:14px;';
    panel.innerHTML = `
      <summary style="cursor:pointer; font-weight:700;">Phase 7 · Advanced-ControlNet mode</summary>
      <div class="accordion-hint" style="margin-top:6px;">Optional power-user controls for Advanced-ControlNet installs. Leave off for normal ControlNetApply.</div>
      <div class="generation-controlnet-advanced-grid" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; align-items:end; margin-top:10px;">
        <label class="generation-toggle-pill" style="justify-content:center;"><input class="generation-controlnet-advanced-enabled" type="checkbox" /> Use Advanced-ControlNet</label>
        <div><label>Apply engine</label><select class="generation-controlnet-advanced-engine"><option value="auto" selected>Auto</option><option value="advanced">Force advanced</option><option value="standard">Force standard</option></select></div>
        <div><label>Strength schedule</label><select class="generation-controlnet-strength-schedule"><option value="constant" selected>Constant</option><option value="fade_in">Fade in</option><option value="fade_out">Fade out</option><option value="early_strong">Early strong</option><option value="late_strong">Late strong</option><option value="pulse_mid">Pulse middle</option></select></div>
        <div><label>Weight preset</label><select class="generation-controlnet-weight-preset"><option value="default" selected>Default</option><option value="balanced">Balanced</option><option value="composition">Composition lock</option><option value="detail">Detail/edge lock</option><option value="soft">Soft guidance</option></select></div>
        <div><label>Mask mode</label><select class="generation-controlnet-mask-mode"><option value="none" selected>No mask</option><option value="white_control">White = controlled</option><option value="black_control">Black = controlled</option></select></div>
        <div><label>Control mask</label><input class="generation-controlnet-mask-image" type="file" accept="image/*" /></div>
        <div><label>Batch behavior</label><select class="generation-controlnet-batch-mode"><option value="single" selected>Single image</option><option value="repeat">Repeat map across batch</option><option value="match">Match map sequence</option></select></div>
        <label class="generation-toggle-pill" style="justify-content:center;"><input class="generation-controlnet-sliding-context" type="checkbox" /> Sliding context ready</label>
      </div>
      <div class="mini-note generation-controlnet-advanced-note" style="margin-top:8px;">Advanced mode is best for masked ControlNet, timed guidance, batches, and later video consistency. If Advanced-ControlNet is missing, Neo will fall back to standard mode.</div>`;
    settings.insertAdjacentElement('afterend', panel);
  }

  function readAdvanced(root){
    const uid = uidForRoot(root);
    return {
      advanced_enabled: bool(q(root, '.generation-controlnet-advanced-enabled')),
      advanced_engine: trim(q(root, '.generation-controlnet-advanced-engine')?.value || 'auto'),
      strength_schedule: trim(q(root, '.generation-controlnet-strength-schedule')?.value || 'constant'),
      weight_preset: trim(q(root, '.generation-controlnet-weight-preset')?.value || 'default'),
      mask_mode: trim(q(root, '.generation-controlnet-mask-mode')?.value || 'none'),
      mask_field: `control_mask__${uid}`,
      has_mask: !!q(root, '.generation-controlnet-mask-image')?.files?.[0],
      batch_mode: trim(q(root, '.generation-controlnet-batch-mode')?.value || 'single'),
      sliding_context: bool(q(root, '.generation-controlnet-sliding-context')),
    };
  }

  function decorate(){ rowRoots().forEach(ensureAdvancedPanel); }

  function patchPayload(body){
    if (!(body instanceof FormData)) return;
    let payload = {};
    try { payload = JSON.parse(String(body.get('settings_json') || '{}')) || {}; } catch(_) { payload = {}; }
    const units = Array.isArray(payload.controlnet_units) ? payload.controlnet_units : [];
    rowRoots().forEach((root, index) => {
      const adv = readAdvanced(root);
      if (units[index]) Object.assign(units[index], adv);
      const mask = q(root, '.generation-controlnet-mask-image')?.files?.[0];
      if (mask && adv.mask_field && !body.has(adv.mask_field)) body.append(adv.mask_field, mask, mask.name || `${adv.mask_field}.png`);
    });
    payload.controlnet_units = units;
    payload.advanced_controlnet_requested = units.some(u => !!u.advanced_enabled || u.advanced_engine === 'advanced' || (u.mask_mode && u.mask_mode !== 'none') || (u.strength_schedule && u.strength_schedule !== 'constant'));
    body.set('settings_json', JSON.stringify(payload));
  }

  if (!window.__neoPhase7FetchPatched) {
    window.__neoPhase7FetchPatched = true;
    const previousFetch = window.fetch;
    window.fetch = function(input, init){
      try {
        const body = init?.body || input?.body;
        const url = String(input?.url || input || '');
        if (url.includes('/api/generation/queue')) patchPayload(body);
      } catch(err) { console.warn('[Neo] Phase 7 Advanced-ControlNet payload patch failed:', err); }
      return previousFetch.apply(this, arguments);
    };
  }

  document.addEventListener('change', event => {
    if (event.target?.matches?.('.generation-controlnet-advanced-enabled, .generation-controlnet-advanced-engine, .generation-controlnet-strength-schedule, .generation-controlnet-weight-preset, .generation-controlnet-mask-mode')) {
      const root = event.target.closest('.generation-unit-card-controlnet, .generation-controlnet-row');
      const note = q(root, '.generation-controlnet-advanced-note');
      if (note) {
        const adv = readAdvanced(root);
        const bits = [];
        if (adv.advanced_enabled) bits.push('advanced apply requested');
        if (adv.strength_schedule !== 'constant') bits.push(`${adv.strength_schedule.replaceAll('_',' ')} schedule`);
        if (adv.mask_mode !== 'none') bits.push('mask control active');
        note.textContent = bits.length ? `Advanced-ControlNet: ${bits.join(' · ')}.` : 'Advanced mode is best for masked ControlNet, timed guidance, batches, and later video consistency. If Advanced-ControlNet is missing, Neo will fall back to standard mode.';
      }
      try { window.NeoControlNetStack?.renderSummary?.(); } catch(_) {}
    }
  }, true);

  const observer = new MutationObserver(() => setTimeout(decorate, 60));
  if (document.body) observer.observe(document.body, { childList:true, subtree:true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(decorate, 120));
  else setTimeout(decorate, 120);
  window.NeoControlNetAdvanced = { decorate, readAdvanced };
})();

/* Neo Studio Patch 69: ControlNet preprocessor + relevant model filtering */
(function(){
  function $neo(id){ return document.getElementById(id); }
  function val(item){ return String((item && typeof item === 'object') ? (item.value || item.name || item.filename || item.title || item.label || '') : (item || '')).trim(); }
  function label(item){ return String((item && typeof item === 'object') ? (item.label || item.name || item.filename || item.title || item.value || '') : (item || '')).trim(); }
  function allModels(){
    try { if (typeof window.neoGetGenerationControlnetModelItems === 'function') return window.neoGetGenerationControlnetModelItems(); } catch(_) {}
    try { if (typeof getGenerationControlnetModelItems === 'function') return getGenerationControlnetModelItems(); } catch(_) {}
    return window.NeoGenerationControlnetModels || [];
  }
  function unitKey(unit, prep){
    const raw = String(prep || unit || 'auto').toLowerCase();
    if (raw.includes('depth')) return 'depth';
    if (raw.includes('pose')) return 'openpose';
    if (raw.includes('soft') || raw.includes('hed')) return 'softedge';
    if (raw.includes('lineart') || raw.includes('line')) return 'lineart';
    if (raw.includes('scribble') || raw.includes('sketch')) return 'scribble';
    if (raw.includes('normal')) return 'normalbae';
    if (raw.includes('tile')) return 'tile';
    if (raw.includes('canny')) return 'canny';
    return 'auto';
  }
  function isUnion(t){ return /\bunion\b|promax|qwen-image-controlnet-union/i.test(t); }
  function isRelevantModel(item, key){
    const t = (val(item) + ' ' + label(item)).toLowerCase();
    if (!t) return false;
    if (isUnion(t)) return true;
    const has = (...words) => words.some(w => t.includes(w));
    if (key === 'canny') return has('canny') && !has('depth');
    if (key === 'depth') return has('depth','midas','zoe','leres') && !has('canny');
    if (key === 'openpose') return has('openpose','dwpose','pose');
    if (key === 'softedge') return has('softedge','soft-edge','hed','pidinet','teed');
    if (key === 'lineart') return has('lineart','line-art','anime-line','line_anime');
    if (key === 'scribble') return has('scribble','sketch');
    if (key === 'normalbae') return has('normal','bae');
    if (key === 'tile') return has('tile');
    return true;
  }
  function fillFiltered(selectEl, unitEl, prepEl, placeholder='None'){
    if (!selectEl) return;
    const current = String(selectEl.value || '').trim();
    const key = unitKey(unitEl && unitEl.value, prepEl && prepEl.value);
    const models = allModels();
    const filtered = key === 'auto' ? models : models.filter(m => isRelevantModel(m, key));
    const rows = filtered.length ? filtered : models;
    selectEl.innerHTML = '';
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = rows.length ? placeholder : 'No ControlNet models found';
    selectEl.appendChild(opt0);
    rows.forEach(item => {
      const opt = document.createElement('option');
      opt.value = val(item);
      opt.textContent = label(item) || opt.value;
      if (current && current === opt.value) opt.selected = true;
      selectEl.appendChild(opt);
    });
    selectEl.title = `Filtered for ${key}. Union models are shown because they support multiple ControlNet types.`;
  }
  function primaryFilter(){
    fillFiltered($neo('generation-controlnet-name'), $neo('generation-controlnet-unit'), $neo('generation-controlnet-preprocessor'), 'None');
    try { updatePrimaryGenerationControlnetSummary(); } catch(_) {}
    try { window.neoSyncControlnetEnabledBadges && window.neoSyncControlnetEnabledBadges(); } catch(_) {}
  }
  function rowFilter(row){
    if (!row) return;
    fillFiltered(row.querySelector('.generation-controlnet-name'), row.querySelector('.generation-controlnet-unit'), row.querySelector('.generation-controlnet-preprocessor'), 'None');
    try { updateGenerationControlnetRowSummary(row); } catch(_) {}
    try { window.neoSyncControlnetEnabledBadges && window.neoSyncControlnetEnabledBadges(); } catch(_) {}
  }
  window.refreshPrimaryGenerationControlnetModelFilter = primaryFilter;
  window.refreshGenerationControlnetModelFilterForRow = rowFilter;
  window.refreshGenerationControlnetModelSelect = function(selectEl){
    const row = selectEl && selectEl.closest && selectEl.closest('.generation-controlnet-row');
    if (row) rowFilter(row); else primaryFilter();
  };
  function applyCannyPreset(select){
    const root = select.closest('.generation-controlnet-row') || document;
    const low = root.querySelector('.generation-controlnet-canny-low, #generation-controlnet-canny-low');
    const high = root.querySelector('.generation-controlnet-canny-high, #generation-controlnet-canny-high');
    const mode = String(select.value || '').toLowerCase();
    if (!low || !high) return;
    if (mode === 'canny_edge') { low.value = '80'; high.value = '180'; }
    if (mode === 'canny_standard') { low.value = '100'; high.value = '200'; }
  }
  document.addEventListener('change', event => {
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches('#generation-controlnet-unit, #generation-controlnet-preprocessor')) {
      if (t.id === 'generation-controlnet-preprocessor') applyCannyPreset(t);
      setTimeout(primaryFilter, 0);
    }
    if (t.matches('.generation-controlnet-unit, .generation-controlnet-preprocessor')) {
      const row = t.closest('.generation-controlnet-row');
      if (t.classList.contains('generation-controlnet-preprocessor')) applyCannyPreset(t);
      setTimeout(() => rowFilter(row), 0);
    }
  });
  setTimeout(() => { primaryFilter(); document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(rowFilter); }, 200);
  setTimeout(() => { primaryFilter(); document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(rowFilter); }, 1200);
})();

/* Neo Studio Patch 74: Phase 8 — ControlNet model matching helper */
(function(){
  function $neo(id){ return document.getElementById(id); }
  function textOf(item){
    return String((item && typeof item === 'object') ? [item.value,item.name,item.filename,item.title,item.label].filter(Boolean).join(' ') : (item || '')).toLowerCase();
  }
  function valueOf(item){
    return String((item && typeof item === 'object') ? (item.value || item.name || item.filename || item.title || item.label || '') : (item || '')).trim();
  }
  function labelOf(item){
    return String((item && typeof item === 'object') ? (item.label || item.name || item.filename || item.title || item.value || '') : (item || '')).trim();
  }
  function allModels(){
    try { if (typeof window.neoGetGenerationControlnetModelItems === 'function') return window.neoGetGenerationControlnetModelItems(); } catch(_) {}
    try { if (typeof getGenerationControlnetModelItems === 'function') return getGenerationControlnetModelItems(); } catch(_) {}
    return window.NeoGenerationControlnetModels || [];
  }
  function controlType(unitValue, prepValue){
    const raw = String(prepValue || unitValue || 'auto').toLowerCase();
    if (raw === 'none') return 'direct';
    if (raw.includes('depth')) return 'depth';
    if (raw.includes('openpose') || raw.includes('dwpose') || raw.includes('pose')) return 'openpose';
    if (raw.includes('soft') || raw.includes('hed') || raw.includes('pidinet') || raw.includes('teed')) return 'softedge';
    if (raw.includes('lineart') || raw.includes('line')) return 'lineart';
    if (raw.includes('scribble') || raw.includes('sketch')) return 'scribble';
    if (raw.includes('normal')) return 'normalbae';
    if (raw.includes('tile')) return 'tile';
    if (raw.includes('canny')) return 'canny';
    return 'auto';
  }
  function isUnion(t){ return /\bunion\b|promax|qwen-image-controlnet-union|controlnet-union/i.test(t); }
  function scoreModelForType(item, type){
    const t = textOf(item);
    if (!t) return -999;
    let score = 0;
    if (isUnion(t)) score += 45;
    const has = (...words) => words.some(w => t.includes(w));
    if (type === 'direct' || type === 'auto') score += 5;
    if (type === 'canny') { if (has('canny')) score += 100; if (has('depth','openpose','pose','tile')) score -= 60; }
    if (type === 'depth') { if (has('depth','midas','zoe','leres')) score += 100; if (has('canny','tile','pose')) score -= 50; }
    if (type === 'openpose') { if (has('openpose','dwpose','pose')) score += 100; if (has('depth','canny','tile')) score -= 45; }
    if (type === 'softedge') { if (has('softedge','soft-edge','hed','pidinet','teed')) score += 100; if (has('canny','depth')) score -= 35; }
    if (type === 'lineart') { if (has('lineart','line-art','anime-line','line_anime')) score += 100; if (has('depth','tile')) score -= 35; }
    if (type === 'scribble') { if (has('scribble','sketch')) score += 100; }
    if (type === 'normalbae') { if (has('normal','bae')) score += 100; }
    if (type === 'tile') { if (has('tile')) score += 100; if (has('depth','canny','pose')) score -= 40; }
    if (has('xl','sdxl')) score += 12;
    if (has('diffusers_xl','xl union','union promax','qwen')) score += 8;
    return score;
  }
  function bestModelForType(type){
    const models = allModels();
    let best = null;
    let bestScore = -999;
    models.forEach(item => {
      const score = scoreModelForType(item, type);
      if (score > bestScore) { best = item; bestScore = score; }
    });
    return best && bestScore > 20 ? { item: best, score: bestScore } : null;
  }
  function selectedModelLooksWrong(selectedText, type){
    if (!selectedText || type === 'auto') return false;
    if (type === 'direct') return false;
    return scoreModelForType(selectedText, type) < 35;
  }
  function ensureHelper(modelSelect){
    if (!modelSelect) return null;
    let helper = modelSelect.parentElement && modelSelect.parentElement.querySelector('.generation-controlnet-model-helper');
    if (!helper) {
      helper = document.createElement('div');
      helper.className = 'generation-controlnet-model-helper mini-note';
      helper.style.cssText = 'margin-top:6px; line-height:1.35; color:#9fc8ff;';
      modelSelect.insertAdjacentElement('afterend', helper);
    }
    return helper;
  }
  function ensureButton(modelSelect){
    if (!modelSelect) return null;
    let button = modelSelect.parentElement && modelSelect.parentElement.querySelector('.generation-controlnet-auto-match-model');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-small generation-controlnet-auto-match-model';
      button.textContent = 'Auto-pick best match';
      button.style.cssText = 'margin-top:6px; width:100%;';
      modelSelect.parentElement.appendChild(button);
      button.addEventListener('click', () => {
        const ctx = getContextFromModelSelect(modelSelect);
        const type = controlType(ctx.unit && ctx.unit.value, ctx.prep && ctx.prep.value);
        const best = bestModelForType(type);
        if (!best) return;
        const v = valueOf(best.item);
        if ([...modelSelect.options].some(opt => opt.value === v)) {
          modelSelect.value = v;
        } else {
          const opt = document.createElement('option');
          opt.value = v;
          opt.textContent = labelOf(best.item) || v;
          modelSelect.appendChild(opt);
          modelSelect.value = v;
        }
        modelSelect.dispatchEvent(new Event('change', { bubbles:true }));
        refreshOne(modelSelect);
      });
    }
    return button;
  }
  function getContextFromModelSelect(modelSelect){
    const row = modelSelect && modelSelect.closest && modelSelect.closest('.generation-controlnet-row');
    if (row) return {
      row,
      unit: row.querySelector('.generation-controlnet-unit'),
      prep: row.querySelector('.generation-controlnet-preprocessor'),
      model: modelSelect,
    };
    return {
      row: null,
      unit: $neo('generation-controlnet-unit'),
      prep: $neo('generation-controlnet-preprocessor'),
      model: modelSelect,
    };
  }
  function refreshOne(modelSelect){
    if (!modelSelect) return;
    const ctx = getContextFromModelSelect(modelSelect);
    const type = controlType(ctx.unit && ctx.unit.value, ctx.prep && ctx.prep.value);
    const selected = String(modelSelect.value || '').trim();
    const helper = ensureHelper(modelSelect);
    const button = ensureButton(modelSelect);
    const best = bestModelForType(type);
    const bestName = best ? (labelOf(best.item) || valueOf(best.item)) : '';
    if (button) button.disabled = !best;
    if (!helper) return;
    if (selected && selectedModelLooksWrong(selected, type)) {
      helper.textContent = `⚠️ Model mismatch: selected model does not look ideal for ${type}. Suggested: ${bestName || 'install a matching ControlNet model'}.`;
      helper.style.color = '#ffcf8a';
      return;
    }
    if (!selected && bestName) {
      helper.textContent = `Suggested for ${type}: ${bestName}`;
      helper.style.color = '#9fc8ff';
      return;
    }
    if (selected && bestName && selected !== valueOf(best.item)) {
      helper.textContent = `Selected model is usable. Best detected match for ${type}: ${bestName}`;
      helper.style.color = '#9fc8ff';
      return;
    }
    if (selected) {
      helper.textContent = `✅ Model matches ${type}.`;
      helper.style.color = '#9ee6a8';
      return;
    }
    helper.textContent = `No matching ControlNet model detected for ${type}. Union models can still work if available.`;
    helper.style.color = '#ffcf8a';
  }
  function refreshAll(){
    refreshOne($neo('generation-controlnet-name'));
    document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row .generation-controlnet-name').forEach(refreshOne);
  }
  const oldPrimary = window.refreshPrimaryGenerationControlnetModelFilter;
  const oldRow = window.refreshGenerationControlnetModelFilterForRow;
  window.refreshPrimaryGenerationControlnetModelFilter = function(){
    if (typeof oldPrimary === 'function') oldPrimary();
    setTimeout(() => refreshOne($neo('generation-controlnet-name')), 0);
  };
  window.refreshGenerationControlnetModelFilterForRow = function(row){
    if (typeof oldRow === 'function') oldRow(row);
    setTimeout(() => refreshOne(row && row.querySelector('.generation-controlnet-name')), 0);
  };
  document.addEventListener('change', event => {
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches('#generation-controlnet-unit, #generation-controlnet-preprocessor, #generation-controlnet-name, .generation-controlnet-unit, .generation-controlnet-preprocessor, .generation-controlnet-name')) {
      setTimeout(refreshAll, 0);
    }
  }, true);
  const observer = new MutationObserver(() => setTimeout(refreshAll, 80));
  if (document.body) observer.observe(document.body, { childList:true, subtree:true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(refreshAll, 250));
  else setTimeout(refreshAll, 250);
  setTimeout(refreshAll, 1500);
  window.NeoControlNetModelMatcher = { refreshAll, bestModelForType, scoreModelForType, controlType };
})();

/* Neo Studio Phase 1 ownership fix — Dynamic Thresholding is owned by generation_catalog_state.js.
   Do not define window.renderGenerationDynamicThresholding or window.readGenerationDynamicThresholding here.
   This file is workspace-form plumbing only; the canonical controller handles family gating,
   visibility, state sync, and payload reads for SDXL-only Dynamic Thresholding. */
(function(){
  if (window.__neoDynamicThresholdingWorkspaceFormsShimInstalled) return;
  window.__neoDynamicThresholdingWorkspaceFormsShimInstalled = true;

  function reportMissingCanonicalOwner(){
    const hasCanonicalRender = typeof window.renderGenerationDynamicThresholding === 'function';
    const hasCanonicalRead = typeof window.readGenerationDynamicThresholding === 'function';
    if (!hasCanonicalRender || !hasCanonicalRead) {
      console.warn('[Neo Studio] Dynamic Thresholding canonical owner is not ready yet. Expected generation_catalog_state.js to install render/read handlers.');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(reportMissingCanonicalOwner, 0), { once: true });
  } else {
    setTimeout(reportMissingCanonicalOwner, 0);
  }
})();


/* Neo Studio Patch: RES4LYF Phase 8 — Optional Advanced Sampler Lane */
(function(){
  if (window.__neoRES4LYFPhase8AdvancedLaneInstalled) return;
  window.__neoRES4LYFPhase8AdvancedLaneInstalled = true;
  const $ = id => document.getElementById(id);
  const trim = value => String(value ?? '').trim();

  function getCatalog(){
    const catalog = (typeof generationCatalogState !== 'undefined' && generationCatalogState) ? generationCatalogState : (window.generationCatalogState || {});
    const res = (catalog && typeof catalog.res4lyf === 'object' && catalog.res4lyf) ? catalog.res4lyf : {};
    const features = (catalog && typeof catalog.features === 'object' && catalog.features) ? catalog.features : {};
    return { catalog, res, features };
  }

  function hasClownshark(){
    const { res, features } = getCatalog();
    return !!(res.has_clownshark_sampler || features.res4lyf_clownshark_sampler || features.res4lyf_advanced_lane);
  }

  function routeIsAdvancedSafe(){
    const mode = trim($('generation-workflow-type')?.value || 'txt2img').toLowerCase();
    const family = trim(document.querySelector('[data-generation-family].active')?.getAttribute('data-generation-family') || window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || 'sdxl_sd').toLowerCase();
    const inpaintBackend = trim($('generation-inpaint-backend')?.value || 'standard').toLowerCase();
    const refineEnabled = trim($('generation-refine-enabled')?.value || 'off').toLowerCase();
    const detailerEnabled = !!$('generation-detailer-enabled')?.checked;
    const reasons = [];
    let allowed = true;
    if (!['txt2img', 'img2img'].includes(mode)) { allowed = false; reasons.push('txt2img/img2img only'); }
    const modelSource = trim($('generation-model-source')?.value || '').toLowerCase();
    const ggufClipType = trim($('generation-gguf-clip-type')?.value || '').toLowerCase();
    const ggufUnet = trim($('generation-gguf-unet')?.value || '');
    const usesLanPaintRoute = (mode === 'inpaint' || mode === 'outpaint') && inpaintBackend === 'lanpaint';
    const usesQwenRoute = family === 'qwen_image_edit' && (modelSource === 'gguf' || ggufClipType === 'qwen_image' || !!ggufUnet || usesLanPaintRoute);
    if (usesQwenRoute || usesLanPaintRoute) { allowed = false; reasons.push('Route uses Qwen/LanPaint sampling, not the RES4LYF Advanced Lane path'); }
    if (refineEnabled && !['off', 'false', '0', 'none', ''].includes(refineEnabled)) { allowed = false; reasons.push('refine/highres chaining enabled'); }
    if (detailerEnabled) { allowed = false; reasons.push('Detailer/ADetailer enabled'); }
    return { allowed, reasons, mode, family };
  }

  function ensurePanel(){
    const card = $('generation-res4lyf-status');
    if (!card || $('generation-res4lyf-engine')) return;
    const panel = document.createElement('div');
    panel.id = 'generation-res4lyf-advanced-lane-panel';
    panel.className = 'card-lite';
    panel.style.cssText = 'margin-top:10px; padding:10px; border:1px solid rgba(168,85,247,.22); background:rgba(168,85,247,.055);';
    panel.innerHTML = `
      <div class="row-between" style="gap:10px; align-items:flex-start; flex-wrap:wrap;">
        <div style="min-width:220px; flex:1 1 260px;">
          <label for="generation-res4lyf-engine">Sampler engine</label>
          <select id="generation-res4lyf-engine">
            <option value="core" selected>Core KSampler</option>
            <option value="clownshark">RES4LYF ClownsharKSampler · Experimental</option>
          </select>
        </div>
        <span class="badge is-disabled" id="generation-res4lyf-engine-badge">Advanced: Checking</span>
      </div>
      <div class="mini-note" id="generation-res4lyf-engine-note" style="margin-top:6px; line-height:1.45;">Advanced lane is optional. Core KSampler remains the default.</div>
      <details id="generation-res4lyf-advanced-controls" style="display:none; margin-top:10px;">
        <summary style="cursor:pointer; font-weight:700;">Advanced RES4LYF controls</summary>
        <div class="mini-note" style="margin:6px 0 10px; line-height:1.45;">These values are passed only when ClownsharKSampler supports the matching input. Unsupported fields are ignored by the backend.</div>
        <div class="form-grid compact" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px;">
          <label>Sampler mode
            <select id="generation-res4lyf-sampler-mode"><option value="standard" selected>standard</option><option value="unsample">unsample</option><option value="resample">resample</option></select>
          </label>
          <label>Implicit steps
            <input id="generation-res4lyf-implicit-steps" type="number" min="0" max="100" step="1" value="0">
          </label>
          <label>Implicit sampler
            <select id="generation-res4lyf-implicit-sampler"><option value="">Reuse current sampler</option><option value="res_2m">res_2m</option><option value="res_5s">res_5s</option><option value="res_3s">res_3s</option></select>
          </label>
          <label>Noise type init
            <select id="generation-res4lyf-noise-type-init"><option value="gaussian" selected>gaussian</option><option value="brownian">brownian</option><option value="fractal">fractal</option></select>
          </label>
          <label>Noise type SDE
            <select id="generation-res4lyf-noise-type-sde"><option value="gaussian" selected>gaussian</option><option value="brownian">brownian</option><option value="fractal">fractal</option></select>
          </label>
          <label>Noise mode SDE
            <select id="generation-res4lyf-noise-mode-sde"><option value="hard" selected>hard</option><option value="soft">soft</option><option value="default">default</option></select>
          </label>
          <label>ETA
            <input id="generation-res4lyf-eta" type="number" min="0" max="2" step="0.01" value="0">
          </label>
          <label>Alt denoise
            <input id="generation-res4lyf-denoise-alt" type="number" min="0" max="1" step="0.01" placeholder="auto">
          </label>
        </div>
      </details>`;
    card.appendChild(panel);
    $('generation-res4lyf-engine')?.addEventListener('change', () => {
      refreshPanel();
      if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
    });
    ['generation-res4lyf-sampler-mode','generation-res4lyf-implicit-steps','generation-res4lyf-implicit-sampler','generation-res4lyf-noise-type-init','generation-res4lyf-noise-type-sde','generation-res4lyf-noise-mode-sde','generation-res4lyf-eta','generation-res4lyf-denoise-alt'].forEach(id => {
      $(id)?.addEventListener('change', () => { if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave(); });
    });
  }

  function refreshPanel(){
    ensurePanel();
    const select = $('generation-res4lyf-engine');
    const badge = $('generation-res4lyf-engine-badge');
    const note = $('generation-res4lyf-engine-note');
    if (!select) return;
    const clown = hasClownshark();
    const compat = routeIsAdvancedSafe();
    const advancedOption = Array.from(select.options || []).find(opt => opt.value === 'clownshark');
    const enabled = clown && compat.allowed;
    if (advancedOption) advancedOption.disabled = !enabled;
    if (!enabled && select.value === 'clownshark') select.value = 'core';
    if (badge) {
      badge.classList.remove('is-enabled', 'is-disabled', 'is-warning');
      if (enabled) { badge.textContent = 'Advanced: Ready'; badge.classList.add('is-enabled'); }
      else if (clown) { badge.textContent = 'Advanced: Guarded'; badge.classList.add('is-warning'); }
      else { badge.textContent = 'Advanced: Missing'; badge.classList.add('is-disabled'); }
    }
    if (note) {
      if (!clown) note.textContent = 'ClownsharKSampler was not detected. Install/enable RES4LYF in ComfyUI and refresh the catalog.';
      else if (!compat.allowed) note.textContent = `Advanced lane disabled here: ${compat.reasons.join('; ')}`;
      else note.textContent = 'Experimental lane ready. When selected, Neo will replace compatible base KSampler node(s) with ClownsharKSampler at queue time. Use one-off tests first.';
    }
    const controls = $('generation-res4lyf-advanced-controls');
    if (controls) controls.style.display = (enabled && select.value === 'clownshark') ? '' : 'none';
  }

  function collectAdvancedOptions(){
    const out = {};
    const mode = trim($('generation-res4lyf-sampler-mode')?.value || '');
    const implicitStepsRaw = trim($('generation-res4lyf-implicit-steps')?.value || '');
    const implicitSampler = trim($('generation-res4lyf-implicit-sampler')?.value || '');
    const noiseInit = trim($('generation-res4lyf-noise-type-init')?.value || '');
    const noiseSde = trim($('generation-res4lyf-noise-type-sde')?.value || '');
    const noiseModeSde = trim($('generation-res4lyf-noise-mode-sde')?.value || '');
    const etaRaw = trim($('generation-res4lyf-eta')?.value || '');
    const denoiseAltRaw = trim($('generation-res4lyf-denoise-alt')?.value || '');
    if (mode) out.sampler_mode = mode;
    if (implicitStepsRaw !== '') out.implicit_steps = Math.max(0, parseInt(implicitStepsRaw, 10) || 0);
    if (implicitSampler) out.implicit_sampler_name = implicitSampler;
    if (noiseInit) out.noise_type_init = noiseInit;
    if (noiseSde) out.noise_type_sde = noiseSde;
    if (noiseModeSde) out.noise_mode_sde = noiseModeSde;
    if (etaRaw !== '') out.eta = Math.max(0, Number(etaRaw) || 0);
    if (denoiseAltRaw !== '') out.denoise_alt = Math.min(1, Math.max(0, Number(denoiseAltRaw) || 0));
    return out;
  }

  function patchQueuePayload(body){
    if (!(body instanceof FormData)) return;
    const engine = trim($('generation-res4lyf-engine')?.value || 'core').toLowerCase();
    let payload = {};
    try { payload = JSON.parse(String(body.get('settings_json') || '{}')) || {}; } catch(_) { payload = {}; }
    payload.res4lyf_sampler_engine = engine === 'clownshark' ? 'clownshark' : 'core';
    payload.res4lyf_advanced_lane_requested = payload.res4lyf_sampler_engine === 'clownshark';
    if (payload.res4lyf_advanced_lane_requested) payload.res4lyf_advanced_options = collectAdvancedOptions();
    else delete payload.res4lyf_advanced_options;
    body.set('settings_json', JSON.stringify(payload));
  }

  if (!window.__neoRES4LYFPhase8FetchPatched) {
    window.__neoRES4LYFPhase8FetchPatched = true;
    const previousFetch = window.fetch;
    window.fetch = function(input, init){
      try {
        const url = String(input?.url || input || '');
        const body = init?.body || input?.body;
        if (url.includes('/api/generation/queue')) patchQueuePayload(body);
      } catch(err) { console.warn('[Neo] RES4LYF Phase 8 payload patch failed:', err); }
      const result = previousFetch.apply(this, arguments);
      try {
        if (url.includes('/api/generation/queue') && result && typeof result.then === 'function') {
          return result.then(resp => {
            try {
              const clone = resp.clone();
              clone.json().then(data => {
                const notes = Array.isArray(data?.notes) ? data.notes.join(' ') : JSON.stringify(data || {});
                window.__neoRES4LYFFallbackApplied = /RES4LYF fallback applied/i.test(notes || '');
                refreshGenerationRES4LYFRecoveryPanel();
              }).catch(() => {});
            } catch(_) {}
            return resp;
          });
        }
      } catch(_) {}
      return result;
    };
  }

  const oldRender = window.renderGenerationRES4LYFStatus;
  window.renderGenerationRES4LYFStatus = function(){
    try { if (typeof oldRender === 'function') oldRender.apply(this, arguments); } catch(err) { console.warn('[Neo] RES4LYF status render failed:', err); }
    refreshPanel();
    refreshGenerationRES4LYFRecoveryPanel();
  };
  window.refreshGenerationRES4LYFAdvancedLane = refreshPanel;
  window.addEventListener('neo:generation-catalog-refreshed', () => { refreshPanel(); refreshGenerationRES4LYFRecoveryPanel(); });
  document.addEventListener('neo-generation-family-changed', refreshPanel);
  document.addEventListener('change', event => {
    if (event.target?.matches?.('#generation-workflow-type, #generation-inpaint-backend, #generation-refine-enabled, #generation-detailer-enabled, #generation-family')) refreshPanel();
  }, true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(refreshPanel, 120));
  else setTimeout(refreshPanel, 120);
})();

/* Neo Studio Phase 2B: Restore proper visual Outpaint Canvas Editor with side handles */
(function neoPhase2BOutpaintCanvasEditor(){
  if (window.__neoPhase2BOutpaintCanvasEditorInstalled) return;
  window.__neoPhase2BOutpaintCanvasEditorInstalled = true;

  const state = {
    file: null,
    image: null,
    sourceW: 0,
    sourceH: 0,
    targetW: 0,
    targetH: 0,
    pad: { left:0, top:0, right:0, bottom:0 },
    scale: 1,
    dragging: false,
    dragMode: null,
    dragStart: null,
    dragPadStart: null,
    hoverMode: null,
  };

  const HANDLE_HIT_PX = 18;
  const MIN_CANVAS_SIDE = 64;

  function n(value, fallback=0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function readPadding() {
    return {
      left: Math.max(0, Math.round(n($('generation-outpaint-left')?.value, 0))),
      top: Math.max(0, Math.round(n($('generation-outpaint-top')?.value, 0))),
      right: Math.max(0, Math.round(n($('generation-outpaint-right')?.value, 0))),
      bottom: Math.max(0, Math.round(n($('generation-outpaint-bottom')?.value, 0))),
    };
  }

  function writePadding(pad, { quiet=false } = {}) {
    const clean = {
      left: Math.max(0, Math.round(n(pad.left, 0))),
      top: Math.max(0, Math.round(n(pad.top, 0))),
      right: Math.max(0, Math.round(n(pad.right, 0))),
      bottom: Math.max(0, Math.round(n(pad.bottom, 0))),
    };
    if ($('generation-outpaint-left')) $('generation-outpaint-left').value = String(clean.left);
    if ($('generation-outpaint-top')) $('generation-outpaint-top').value = String(clean.top);
    if ($('generation-outpaint-right')) $('generation-outpaint-right').value = String(clean.right);
    if ($('generation-outpaint-bottom')) $('generation-outpaint-bottom').value = String(clean.bottom);
    if ($('generation-outpaint-preset')) $('generation-outpaint-preset').value = 'custom';
    state.pad = clean;
    state.targetW = Math.max(MIN_CANVAS_SIDE, state.sourceW + clean.left + clean.right);
    state.targetH = Math.max(MIN_CANVAS_SIDE, state.sourceH + clean.top + clean.bottom);
    try { renderGenerationOutpaintSummary(); } catch (_) {}
    try { syncGenerationCleanupUI(); } catch (_) {}
    if (!quiet) {
      try { scheduleGenerationDraftSave(); } catch (_) {}
    }
    updateOutpaintCanvasEditorStateLabel();
  }

  function hasSourceImage() {
    return Boolean($('generation-source-image')?.files?.[0]);
  }

  function updateOutpaintCanvasEditorStateLabel() {
    const label = $('generation-outpaint-canvas-editor-state');
    const sourceLoaded = hasSourceImage();
    if (label) {
      label.textContent = sourceLoaded
        ? 'Ready: drag canvas handles to adjust each side independently.'
        : 'Load a source image first to use the visual canvas editor.';
    }
    const buttons = [
      $('btn-generation-outpaint-canvas-editor'),
      $('btn-generation-source-outpaint-canvas'),
    ].filter(Boolean);
    buttons.forEach(btn => {
      btn.disabled = !sourceLoaded;
      btn.title = sourceLoaded ? 'Open the visual outpaint canvas editor' : 'Load a source image first';
      btn.classList.toggle('is-disabled', !sourceLoaded);
    });
    try {
      console.debug('[Neo] outpaint_canvas_editor_visible=%s reason=%s', String(!!$('btn-generation-outpaint-canvas-editor')), sourceLoaded ? 'source_image_loaded' : 'no_source_image');
    } catch (_) {}
  }

  function getCanvasPoint(event) {
    const canvas = $('generation-outpaint-canvas-editor-canvas');
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * ((canvas.width || rect.width || 1) / (rect.width || canvas.width || 1));
    const y = (event.clientY - rect.top) * ((canvas.height || rect.height || 1) / (rect.height || canvas.height || 1));
    return { x, y };
  }

  function computeScale() {
    const stage = $('generation-outpaint-canvas-editor-stage');
    const maxW = Math.max(420, Math.min(1180, (stage?.clientWidth || 1040) - 32));
    const maxH = 760;
    if (!(state.targetW > 0 && state.targetH > 0)) return 1;
    return Math.min(1, maxW / state.targetW, maxH / state.targetH);
  }

  function getRects() {
    const s = state.scale || 1;
    return {
      canvas: { x:0, y:0, w: state.targetW * s, h: state.targetH * s },
      image: {
        x: state.pad.left * s,
        y: state.pad.top * s,
        w: state.sourceW * s,
        h: state.sourceH * s,
      },
    };
  }

  function modeToCursor(mode) {
    if (!mode) return 'default';
    if (mode === 'move') return 'grab';
    if (mode === 'left' || mode === 'right') return 'ew-resize';
    if (mode === 'top' || mode === 'bottom') return 'ns-resize';
    if (mode === 'top-left' || mode === 'bottom-right') return 'nwse-resize';
    if (mode === 'top-right' || mode === 'bottom-left') return 'nesw-resize';
    return 'default';
  }

  function hitTest(point) {
    const { canvas, image } = getRects();
    const x = point.x;
    const y = point.y;
    const edge = HANDLE_HIT_PX;
    const nearLeft = x <= edge;
    const nearRight = x >= canvas.w - edge;
    const nearTop = y <= edge;
    const nearBottom = y >= canvas.h - edge;
    if (nearLeft && nearTop) return 'top-left';
    if (nearRight && nearTop) return 'top-right';
    if (nearLeft && nearBottom) return 'bottom-left';
    if (nearRight && nearBottom) return 'bottom-right';
    if (nearLeft) return 'left';
    if (nearRight) return 'right';
    if (nearTop) return 'top';
    if (nearBottom) return 'bottom';
    const insideImage = x >= image.x && x <= image.x + image.w && y >= image.y && y <= image.y + image.h;
    if (insideImage) return 'move';
    return null;
  }

  function drawHandleLabel(ctx, text, x, y, align='center') {
    ctx.save();
    ctx.font = '12px system-ui, -apple-system, Segoe UI, sans-serif';
    const w = Math.ceil(ctx.measureText(text).width + 14);
    const h = 22;
    const bx = align === 'left' ? x : align === 'right' ? x - w : x - w / 2;
    ctx.fillStyle = 'rgba(15,23,42,0.78)';
    ctx.strokeStyle = 'rgba(148,163,184,0.32)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect?.(bx, y - h / 2, w, h, 8);
    if (ctx.roundRect) { ctx.fill(); ctx.stroke(); }
    else { ctx.fillRect(bx, y - h / 2, w, h); ctx.strokeRect(bx, y - h / 2, w, h); }
    ctx.fillStyle = 'rgba(226,232,240,0.96)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, bx + w / 2, y);
    ctx.restore();
  }

  function drawEditor() {
    const canvas = $('generation-outpaint-canvas-editor-canvas');
    const ctx = canvas?.getContext?.('2d');
    if (!canvas || !ctx || !state.image) return;
    state.scale = computeScale();
    const cw = Math.max(1, Math.round(state.targetW * state.scale));
    const ch = Math.max(1, Math.round(state.targetH * state.scale));
    canvas.width = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);

    const imgX = state.pad.left * state.scale;
    const imgY = state.pad.top * state.scale;
    const imgW = state.sourceW * state.scale;
    const imgH = state.sourceH * state.scale;

    ctx.save();
    ctx.fillStyle = 'rgba(15,23,42,0.94)';
    ctx.fillRect(0, 0, cw, ch);

    // Padding zones.
    ctx.fillStyle = 'rgba(59,130,246,0.16)';
    ctx.fillRect(0, 0, cw, imgY);
    ctx.fillRect(0, imgY + imgH, cw, Math.max(0, ch - (imgY + imgH)));
    ctx.fillRect(0, imgY, imgX, imgH);
    ctx.fillRect(imgX + imgW, imgY, Math.max(0, cw - (imgX + imgW)), imgH);

    // Canvas border and handle bands.
    ctx.strokeStyle = 'rgba(96,165,250,0.85)';
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, cw - 2, ch - 2);
    const active = state.dragMode || state.hoverMode;
    const bands = [
      ['left', 0, 0, HANDLE_HIT_PX, ch],
      ['right', cw - HANDLE_HIT_PX, 0, HANDLE_HIT_PX, ch],
      ['top', 0, 0, cw, HANDLE_HIT_PX],
      ['bottom', 0, ch - HANDLE_HIT_PX, cw, HANDLE_HIT_PX],
    ];
    bands.forEach(([mode, x, y, w, h]) => {
      ctx.fillStyle = active && String(active).includes(mode) ? 'rgba(250,204,21,0.22)' : 'rgba(96,165,250,0.10)';
      ctx.fillRect(x, y, w, h);
    });

    ctx.drawImage(state.image, imgX, imgY, imgW, imgH);
    ctx.strokeStyle = 'rgba(250,204,21,0.95)';
    ctx.lineWidth = Math.max(1, Math.round(2 * state.scale));
    ctx.setLineDash([Math.max(4, 8 * state.scale), Math.max(3, 6 * state.scale)]);
    ctx.strokeRect(imgX, imgY, imgW, imgH);
    ctx.setLineDash([]);

    // Drag handles / labels for each side.
    drawHandleLabel(ctx, `← L ${state.pad.left}`, 12, Math.max(36, ch / 2), 'left');
    drawHandleLabel(ctx, `R ${state.pad.right} →`, cw - 12, Math.max(36, ch / 2), 'right');
    drawHandleLabel(ctx, `↑ T ${state.pad.top}`, Math.max(70, cw / 2), 18);
    drawHandleLabel(ctx, `B ${state.pad.bottom} ↓`, Math.max(70, cw / 2), ch - 18);

    // Info badge.
    ctx.fillStyle = 'rgba(2,6,23,0.82)';
    ctx.fillRect(10, 10, Math.min(cw - 20, 450), 58);
    ctx.fillStyle = 'rgba(226,232,240,0.96)';
    ctx.font = '13px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.fillText(`Canvas ${state.targetW}×${state.targetH} · Source ${state.sourceW}×${state.sourceH}`, 22, 32);
    ctx.fillText(`Drag edges/corners to resize · Drag image to reposition`, 22, 53);
    ctx.restore();

    const title = $('generation-outpaint-canvas-editor-title');
    const summary = $('generation-outpaint-canvas-editor-summary');
    if (title) title.textContent = `Canvas ${state.targetW} × ${state.targetH}`;
    if (summary) summary.textContent = `Pads L${state.pad.left} R${state.pad.right} T${state.pad.top} B${state.pad.bottom} · drag each blue edge to adjust one side`;
  }

  async function loadFileAsImage(file) {
    if (typeof window.loadFileAsImage === 'function') return window.loadFileAsImage(file);
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = err => { URL.revokeObjectURL(url); reject(err); };
      img.src = url;
    });
  }

  async function loadEditorSource() {
    const file = $('generation-source-image')?.files?.[0] || null;
    if (!file) throw new Error('Load a source image first.');
    const image = await loadFileAsImage(file);
    state.file = file;
    state.image = image;
    state.sourceW = Number(image.naturalWidth || image.width || 0) || 1;
    state.sourceH = Number(image.naturalHeight || image.height || 0) || 1;
    const pads = readPadding();
    state.pad = pads;
    state.targetW = Math.max(MIN_CANVAS_SIDE, state.sourceW + pads.left + pads.right);
    state.targetH = Math.max(MIN_CANVAS_SIDE, state.sourceH + pads.top + pads.bottom);
  }

  async function openEditor() {
    try {
      await loadEditorSource();
    } catch (err) {
      setStatus('generation-status', err?.message || 'Load a source image first to open the outpaint canvas editor.', 'warn');
      updateOutpaintCanvasEditorStateLabel();
      return false;
    }
    if ($('generation-workflow-type') && ['inpaint', 'outpaint'].includes($('generation-workflow-type').value || '') === false) {
      $('generation-workflow-type').value = 'outpaint';
      try { syncGenerationModeUI(); } catch (_) {}
    }
    const modal = $('generation-outpaint-canvas-editor-modal');
    if (!modal) return false;
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    drawEditor();
    setStatus('generation-status', 'Outpaint canvas editor opened. Drag edges/corners to resize each side, or drag the source image to reposition.', 'success');
    return true;
  }

  function closeEditor() {
    const modal = $('generation-outpaint-canvas-editor-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
    state.dragging = false;
    state.dragMode = null;
  }

  function padAll(amount) {
    const next = {
      left: state.pad.left + amount,
      right: state.pad.right + amount,
      top: state.pad.top + amount,
      bottom: state.pad.bottom + amount,
    };
    writePadding(next);
    drawEditor();
  }

  function centerSource() {
    const extraW = Math.max(0, state.targetW - state.sourceW);
    const extraH = Math.max(0, state.targetH - state.sourceH);
    const left = Math.round(extraW / 2);
    const top = Math.round(extraH / 2);
    writePadding({ left, right: extraW - left, top, bottom: extraH - top });
    drawEditor();
  }

  function applyAndClose() {
    writePadding(state.pad);
    closeEditor();
    setStatus('generation-status', `Outpaint canvas padding applied: L${state.pad.left} R${state.pad.right} T${state.pad.top} B${state.pad.bottom}.`, 'success');
  }

  function updateCursorForMode(mode) {
    const canvas = $('generation-outpaint-canvas-editor-canvas');
    if (!canvas) return;
    canvas.style.cursor = state.dragging && mode === 'move' ? 'grabbing' : modeToCursor(mode);
  }

  function resizeFromDrag(mode, dx, dy) {
    const start = state.dragPadStart || state.pad;
    const next = { ...start };
    const ux = dx / (state.scale || 1);
    const uy = dy / (state.scale || 1);
    if (mode.includes('left')) next.left = Math.max(0, Math.round(start.left - ux));
    if (mode.includes('right')) next.right = Math.max(0, Math.round(start.right + ux));
    if (mode.includes('top')) next.top = Math.max(0, Math.round(start.top - uy));
    if (mode.includes('bottom')) next.bottom = Math.max(0, Math.round(start.bottom + uy));
    return next;
  }

  function moveSourceFromDrag(dx, dy) {
    const start = state.dragPadStart || state.pad;
    const ux = dx / (state.scale || 1);
    const uy = dy / (state.scale || 1);
    const extraW = Math.max(0, start.left + start.right);
    const extraH = Math.max(0, start.top + start.bottom);
    const left = Math.round(clamp(start.left + ux, 0, extraW));
    const top = Math.round(clamp(start.top + uy, 0, extraH));
    return {
      left,
      top,
      right: Math.max(0, extraW - left),
      bottom: Math.max(0, extraH - top),
    };
  }

  function handlePointerDown(event) {
    if (!state.image) return;
    const point = getCanvasPoint(event);
    const mode = hitTest(point);
    if (!mode) return;
    event.preventDefault();
    state.dragging = true;
    state.dragMode = mode;
    state.dragStart = point;
    state.dragPadStart = { ...state.pad };
    updateCursorForMode(mode);
  }

  function handlePointerMove(event) {
    if (!state.image) return;
    const point = getCanvasPoint(event);
    if (!state.dragging) {
      const mode = hitTest(point);
      if (mode !== state.hoverMode) {
        state.hoverMode = mode;
        updateCursorForMode(mode);
        drawEditor();
      } else {
        updateCursorForMode(mode);
      }
      return;
    }
    if (!state.dragStart || !state.dragPadStart || !state.dragMode) return;
    event.preventDefault();
    const dx = point.x - state.dragStart.x;
    const dy = point.y - state.dragStart.y;
    const next = state.dragMode === 'move'
      ? moveSourceFromDrag(dx, dy)
      : resizeFromDrag(state.dragMode, dx, dy);
    writePadding(next, { quiet:true });
    drawEditor();
  }

  function handlePointerUp() {
    if (!state.dragging) return;
    state.dragging = false;
    state.dragMode = null;
    state.dragStart = null;
    state.dragPadStart = null;
    const canvas = $('generation-outpaint-canvas-editor-canvas');
    if (canvas) canvas.style.cursor = modeToCursor(state.hoverMode);
    try { scheduleGenerationDraftSave(); } catch (_) {}
  }

  function bindEditor() {
    const openButtons = [$('btn-generation-outpaint-canvas-editor'), $('btn-generation-source-outpaint-canvas')].filter(Boolean);
    openButtons.forEach(btn => {
      if (btn.dataset.neoOutpaintCanvasBound) return;
      btn.dataset.neoOutpaintCanvasBound = '1';
      btn.addEventListener('click', event => { event.preventDefault(); openEditor(); });
    });
    const closeBtn = $('btn-close-generation-outpaint-canvas-editor');
    if (closeBtn && !closeBtn.dataset.neoOutpaintCanvasBound) {
      closeBtn.dataset.neoOutpaintCanvasBound = '1';
      closeBtn.addEventListener('click', closeEditor);
    }
    const modal = $('generation-outpaint-canvas-editor-modal');
    if (modal && !modal.dataset.neoOutpaintCanvasBound) {
      modal.dataset.neoOutpaintCanvasBound = '1';
      modal.addEventListener('click', e => { if (e.target?.id === 'generation-outpaint-canvas-editor-modal') closeEditor(); });
    }
    const canvas = $('generation-outpaint-canvas-editor-canvas');
    if (canvas && !canvas.dataset.neoOutpaintCanvasBound) {
      canvas.dataset.neoOutpaintCanvasBound = '1';
      canvas.addEventListener('pointerdown', handlePointerDown);
      canvas.addEventListener('pointermove', handlePointerMove);
      canvas.addEventListener('pointerleave', () => { if (!state.dragging) { state.hoverMode = null; updateCursorForMode(null); drawEditor(); } });
      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
    }
    const pad128 = $('btn-generation-outpaint-canvas-pad-128');
    if (pad128 && !pad128.dataset.neoOutpaintCanvasBound) {
      pad128.dataset.neoOutpaintCanvasBound = '1';
      pad128.addEventListener('click', () => padAll(128));
    }
    const pad256 = $('btn-generation-outpaint-canvas-pad-256');
    if (pad256 && !pad256.dataset.neoOutpaintCanvasBound) {
      pad256.dataset.neoOutpaintCanvasBound = '1';
      pad256.addEventListener('click', () => padAll(256));
    }
    const center = $('btn-generation-outpaint-canvas-center');
    if (center && !center.dataset.neoOutpaintCanvasBound) {
      center.dataset.neoOutpaintCanvasBound = '1';
      center.addEventListener('click', centerSource);
    }
    const apply = $('btn-generation-outpaint-canvas-apply');
    if (apply && !apply.dataset.neoOutpaintCanvasBound) {
      apply.dataset.neoOutpaintCanvasBound = '1';
      apply.addEventListener('click', applyAndClose);
    }
    updateOutpaintCanvasEditorStateLabel();
  }

  window.openGenerationOutpaintCanvasEditor = openEditor;
  window.closeGenerationOutpaintCanvasEditor = closeEditor;
  window.refreshGenerationOutpaintCanvasEditorVisibility = updateOutpaintCanvasEditorStateLabel;

  document.addEventListener('change', event => {
    if (event.target?.id === 'generation-source-image' || event.target?.id === 'generation-workflow-type') {
      setTimeout(updateOutpaintCanvasEditorStateLabel, 20);
    }
  }, true);
  document.addEventListener('input', event => {
    if (/^generation-outpaint-(left|right|top|bottom)$/.test(event.target?.id || '')) {
      if (!$('generation-outpaint-canvas-editor-modal')?.classList.contains('hidden')) {
        state.pad = readPadding();
        state.targetW = Math.max(MIN_CANVAS_SIDE, state.sourceW + state.pad.left + state.pad.right);
        state.targetH = Math.max(MIN_CANVAS_SIDE, state.sourceH + state.pad.top + state.pad.bottom);
        drawEditor();
      }
      updateOutpaintCanvasEditorStateLabel();
    }
  }, true);
  window.addEventListener('resize', () => {
    if (!$('generation-outpaint-canvas-editor-modal')?.classList.contains('hidden')) drawEditor();
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(bindEditor, 80));
  else setTimeout(bindEditor, 80);
})();
