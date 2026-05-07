// Phase 6 split: launch/runtime + recent item + backend dependency shell logic
async function queueGenerationShell(options={}) {
  const imageSession = getRoleSession('image');
  if (!imageSession.connected) {
    announceGenerationStatus('Connect an Image Backend first.', 'warn');
    return null;
  }

  if (!options.suppressInitialStatus) announceGenerationStatus(options.watch === false ? 'Submitting queue test to ComfyUI…' : 'Submitting generation test to ComfyUI…');

  if (generationCheckpointLooksEmpty()) {
    try {
      await refreshGenerationCatalog(true);
    } catch (_) {}
  }

  const fallbackPrompt = trim(options.fallbackPrompt || '');
  if (!trim($('generation-positive')?.value || '') && fallbackPrompt) {
    $('generation-positive').value = fallbackPrompt;
    refreshGenerationCounters();
  }

  const selectedCheckpoint = ensureGenerationCheckpointSelected();
  let payload = options.overridePayload ? JSON.parse(JSON.stringify(options.overridePayload)) : buildGenerationPayload();
  if (options.previewActionContract && typeof options.previewActionContract === 'object') {
    payload._neo_preview_action = JSON.parse(JSON.stringify(options.previewActionContract));
    payload._neo_derived_action_type = payload._neo_derived_action_type || options.previewActionContract.action_type || '';
    payload._neo_source_output_id = payload._neo_source_output_id || options.previewActionContract.source_output_id || '';
    payload._neo_source_output_key = payload._neo_source_output_key || options.previewActionContract.source_output_key || '';
    payload._neo_parent_output_id = payload._neo_parent_output_id || options.previewActionContract.parent_output_id || '';
    payload._neo_parent_output_key = payload._neo_parent_output_key || options.previewActionContract.parent_output_key || '';
    payload.save_mode_override = payload.save_mode_override || options.previewActionContract.save_lane || '';
  }
  payload = await applyGenerationWildcardResolution(payload, { variantOffset: options.wildcardVariantOffset || 0 });
  if (typeof sanitizeGenerationPayload === 'function') payload = sanitizeGenerationPayload(payload);
  const modelSource = String(payload.model_source || 'checkpoint').trim().toLowerCase();
  if (modelSource === 'checkpoint' && selectedCheckpoint && !trim(payload.checkpoint)) payload.checkpoint = selectedCheckpoint;
  if (!trim(payload.positive)) {
    announceGenerationStatus('Add or pull in a positive prompt first.', 'warn');
    return null;
  }
  if (modelSource === 'gguf') {
    if (!trim(payload.gguf_unet || '')) {
      announceGenerationStatus('Pick a GGUF model first.', 'warn');
      return null;
    }
    if (!trim(payload.vae || '')) {
      announceGenerationStatus('Pick a VAE for the GGUF workflow first.', 'warn');
      return null;
    }
    if (!trim(payload.gguf_clip_primary || '')) {
      announceGenerationStatus('Pick the GGUF encoder first.', 'warn');
      return null;
    }
    if (String(payload.gguf_clip_mode || 'dual') === 'dual' && !trim(payload.gguf_clip_secondary || '')) {
      announceGenerationStatus('Pick the second GGUF encoder first.', 'warn');
      return null;
    }
  } else if (!trim(payload.checkpoint)) {
    announceGenerationStatus('Pick a checkpoint first.', 'warn');
    return null;
  }

  const mode = payload.mode || payload.workflow_type || 'txt2img';
  const sourceFile = options.overrideSourceFile || $('generation-source-image')?.files?.[0] || null;
  const maskFile = options.overrideMaskFile || $('generation-mask-image')?.files?.[0] || null;
  const primaryControlEnabled = isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled'));
  const controlFile = primaryControlEnabled ? ($('generation-control-image')?.files?.[0] || null) : null;
  const controlFiles = collectGenerationControlFiles();
  const primaryIpAdapterEnabled = isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled'));
  const ipadapterFile = primaryIpAdapterEnabled ? ($('generation-ipadapter-image')?.files?.[0] || null) : null;
  const ipadapterFiles = collectGenerationIpAdapterFiles();
  if (mode === 'img2img' && !sourceFile) {
    announceGenerationStatus('Img2img needs a source image.', 'warn');
    return null;
  }
  if (mode === 'inpaint' && (!sourceFile || !maskFile)) {
    announceGenerationStatus('Inpaint needs both a source image and a mask image.', 'warn');
    return null;
  }
  if (mode === 'outpaint') {
    const totalPad = Number(payload.outpaint_left || 0) + Number(payload.outpaint_top || 0) + Number(payload.outpaint_right || 0) + Number(payload.outpaint_bottom || 0);
    if (!sourceFile) {
      announceGenerationStatus('Outpaint needs a source image.', 'warn');
      return null;
    }
    if (!(totalPad > 0)) {
      announceGenerationStatus('Outpaint needs padding on at least one side.', 'warn');
      return null;
    }
  }

  payload.client_id = makeGenerationClientId();
  setGenerationPreviewActionTarget(null);
  startGenerationProgressSocket(payload.client_id);

  const formData = new FormData();
  formData.append('settings_json', JSON.stringify(payload));
  if (sourceFile) formData.append('source_image', sourceFile);
  const extraQwenSource2 = document.getElementById('generation-source-image-2')?.files?.[0];
  const extraQwenSource3 = document.getElementById('generation-source-image-3')?.files?.[0];
  if (extraQwenSource2) formData.append('source_image__2', extraQwenSource2);
  if (extraQwenSource3) formData.append('source_image__3', extraQwenSource3);
  if (mode === 'inpaint' && maskFile) formData.append('mask_image', maskFile);
  if (controlFile) formData.append('control_image', controlFile);
  if (ipadapterFile && !ipadapterFiles.some(item => item.uid === 'primary')) formData.append('ipadapter_image', ipadapterFile);
  controlFiles.forEach(item => {
    if (item.uid !== 'primary') formData.append(`control_image__${item.uid}`, item.file);
    else formData.append('control_image__primary', item.file);
  });
  ipadapterFiles.forEach(item => {
    if (item.uid !== 'primary') formData.append(`ipadapter_image__${item.uid}`, item.file);
    else formData.append('ipadapter_image__primary', item.file);
  });
  // Regional mask uploads are not part of the active generation UI.


  const queueBtn = $('btn-generation-queue');
  const runBtn = $('btn-generation-run');
  const hadQueueDisabled = queueBtn?.hasAttribute('disabled');
  const hadRunDisabled = runBtn?.hasAttribute('disabled');
  if (queueBtn) queueBtn.setAttribute('disabled', 'disabled');
  if (runBtn) runBtn.setAttribute('disabled', 'disabled');

  try {
    const res = await fetch('/api/generation/queue', { method:'POST', body:formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    if (options.lineageHint && data.job?.id) rememberGenerationLineageHint(data.job.id, options.lineageHint.parentOutput, options.lineageHint.stage || 'Derived pass');
    renderGenerationJob(data.job || null);
    if (data.job?.payload?.seed) generationLastUsedSeed = String(data.job.payload.seed || '');
    scheduleGenerationDraftSave();
    generationProgressPromptId = String(data.job?.prompt_id || '');
    if (generationProgressSocket && generationProgressPromptId) {
      const state = typeof getGenerationPreviewLifecycleState === 'function' ? getGenerationPreviewLifecycleState() : null;
      if (state) {
        state.prompt_id = generationProgressPromptId;
        state.client_id = String(payload.client_id || state.client_id || '').trim();
      }
      setGenerationProgress(6, 'Queued in ComfyUI…', 'ETA calculating…');
    } else if (payload.client_id && typeof startGenerationProgressSocket === 'function') {
      // Fallback only: normal path opens the socket before queueing so Comfy preview frames are not missed.
      startGenerationProgressSocket(payload.client_id, generationProgressPromptId);
    }
    if (!options.suppressSuccessStatus) {
      if (Array.isArray(data.job?.compile_notes) && data.job.compile_notes.length) {
        announceGenerationStatus(`${data.message} ${data.job.compile_notes.join(' ')}`);
      } else {
        announceGenerationStatus(data.message || 'Generation job queued.');
      }
    }
    if (options.watch !== false && data.job?.id) {
      pollGenerationJob(data.job.id);
    }
    return data.job || null;
  } catch (e) {
    announceGenerationStatus(e.message || 'Could not queue generation workflow.', 'error');
    setGenerationProgress(100, 'Queue failed', 'ETA —');
    closeGenerationProgressSocket();
    return null;
  } finally {
    if (queueBtn && !hadQueueDisabled) queueBtn.removeAttribute('disabled');
    if (runBtn && !hadRunDisabled) runBtn.removeAttribute('disabled');
  }
}

async function runGenerationShell() {
  const job = await queueGenerationShell({
    watch:true,
    fallbackPrompt: 'masterpiece, best quality, cinematic portrait, dramatic lighting, highly detailed',
  });
  if (job?.id) {
    announceGenerationStatus('Generation queued. Polling ComfyUI until output lands.');
  }
}

function getGenerationLaunchBlockers() {
  const blockers = [];
  const mode = $('generation-workflow-type')?.value || 'txt2img';
  const sourceFile = $('generation-source-image')?.files?.[0] || null;
  const maskFile = $('generation-mask-image')?.files?.[0] || null;
  if (mode === 'img2img' && !sourceFile) blockers.push('Image → Image needs a source image first.');
  if (mode === 'inpaint') {
    if (!sourceFile) blockers.push('Repair Area needs a source image first.');
    if (!maskFile) blockers.push('Repair Area needs a mask before Generate now or Queue only.');
  }
  if (mode === 'outpaint') {
    const totalPad = Number($('generation-outpaint-left')?.value || 0) + Number($('generation-outpaint-top')?.value || 0) + Number($('generation-outpaint-right')?.value || 0) + Number($('generation-outpaint-bottom')?.value || 0);
    if (!sourceFile) blockers.push('Expand Canvas needs a source image first.');
    if (!(totalPad > 0)) blockers.push('Expand Canvas needs padding on at least one side before queueing.');
  }
  const familyBlocker = window.NeoGenerationFamilyRouter?.getLaunchBlocker?.();
  if (familyBlocker) blockers.unshift(familyBlocker);
  return blockers;
}

function syncGenerationLaunchAvailability() {
  const blockers = getGenerationLaunchBlockers();
  const blocked = blockers.length > 0;
  const help = $('generation-action-help');
  const runBtn = $('btn-generation-run');
  const queueBtn = $('btn-generation-queue');
  const baseHelp = 'Main launch controls stay up top so the first thing you see is what you actually need: generate, pause, stop, queue, refresh, and watch progress.';
  if (help) help.textContent = blocked ? `${blockers[0]} Fix the missing input first, then launch.` : baseHelp;
  [runBtn, queueBtn].forEach(btn => {
    if (!btn) return;
    btn.classList.toggle('generation-state-disabled', blocked);
    if (blocked) {
      btn.dataset.neoStateDisabled = '1';
      btn.setAttribute('aria-disabled', 'true');
      btn.title = blockers[0];
    } else {
      delete btn.dataset.neoStateDisabled;
      btn.removeAttribute('aria-disabled');
      if (btn.id === 'btn-generation-run') btn.title = 'Start generation';
      if (btn.id === 'btn-generation-queue') btn.title = 'Queue only';
    }
  });
}


function handleGenerationRunClick(event) {
  if (event?.preventDefault) event.preventDefault();
  const blockers = getGenerationLaunchBlockers();
  if (blockers.length) {
    syncGenerationLaunchAvailability();
    announceGenerationStatus(blockers[0], 'warn');
    return false;
  }
  announceGenerationStatus('Generate button clicked. Preparing request…');
  runGenerationShell().catch(err => announceGenerationStatus(err?.message || 'Generate button failed before queue submit.', 'error'));
  return false;
}

function handleGenerationQueueClick(event) {
  if (event?.preventDefault) event.preventDefault();
  const blockers = getGenerationLaunchBlockers();
  if (blockers.length) {
    syncGenerationLaunchAvailability();
    announceGenerationStatus(blockers[0], 'warn');
    return false;
  }
  announceGenerationStatus('Queue button clicked. Preparing request…');
  queueGenerationShell({ watch:false }).catch(err => announceGenerationStatus(err?.message || 'Queue button failed before submit.', 'error'));
  return false;
}

function handleGenerationResetShellClick(event) {
  if (event?.preventDefault) event.preventDefault();
  if (event?.stopPropagation) event.stopPropagation();
  resetGenerationShell().catch(err => announceGenerationStatus(err?.message || 'Reset workspace failed before completion.', 'error'));
  return false;
}

async function pauseGenerationQueue() {
  const imageSession = getRoleSession('image');
  if (!imageSession.connected) {
    setStatus('generation-status', 'Connect an Image Backend first.', 'warn');
    return;
  }
  try {
    const res = await fetch('/api/generation/pause', { method:'POST' });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    setStatus('generation-status', data.message || 'Pending queue cleared.');
    await fetchGenerationState(true);
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not pause the pending queue.', 'error');
  }
}


async function cancelGenerationJob() {
  stopGenerationPolling();
  closeGenerationProgressSocket();
  const imageSession = getRoleSession('image');
  if (!imageSession.connected) {
    setStatus('generation-status', 'Connect an Image Backend first.', 'warn');
    return;
  }
  const formData = new FormData();
  formData.append('job_id', lastGenerationJobId || '');
  formData.append('prompt_id', generationProgressPromptId || '');
  try {
    const res = await fetch('/api/generation/cancel', { method:'POST', body:formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    setStatus('generation-status', data.message || 'Stop sent.');
    resetGenerationProgress('Stopped');
    await fetchGenerationState(true);
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not stop the current job.', 'error');
  }
}

function recentKindToSearchKind(kind, name='') {
  const value = String(kind || '').toLowerCase();
  if (value === 'prompt') return ['prompts', ''];
  if (value === 'caption') return ['captions', ''];
  if (value === 'character') return ['characters', name || ''];
  if (value === 'metadata') return ['metadata_records', ''];
  if (value === 'bundle') return ['bundles', ''];
  if (value === 'prompt_preset') return ['presets', `prompt:${name || ''}`];
  if (value === 'caption_preset') return ['presets', `caption:${name || ''}`];
  return ['', ''];
}

function renderRecentItems(groups={}) {
  const wrap = $('recent-items-grid');
  if (!wrap) return;
  const sections = [
    ['prompts', 'Prompts'],
    ['captions', 'Captions'],
    ['characters', 'Characters'],
    ['metadata', 'Metadata'],
    ['bundles', 'Bundles'],
    ['prompt_presets', 'Prompt Presets'],
    ['caption_presets', 'Caption Presets'],
  ];
  const hasAny = sections.some(([key]) => Array.isArray(groups?.[key]) && groups[key].length);
  if (!hasAny) {
    wrap.innerHTML = '<div class="card-lite"><div class="muted">No recent items yet.</div></div>';
    return;
  }
  wrap.innerHTML = sections.map(([key, label]) => {
    const items = Array.isArray(groups?.[key]) ? groups[key] : [];
    if (!items.length) return '';
    const rows = items.map(item => {
      const metaBits = [
        item.category || '',
        item.group || '',
        item.favorite ? '★ favorite' : '',
        item.updated_at ? String(item.updated_at).replace('T', ' ') : '',
      ].filter(Boolean);
      return `
        <div class="recent-item">
          <div>
            <div class="recent-item-title">${escapeHtml(item.name || '(untitled)')}</div>
            <div class="recent-item-meta">${escapeHtml(metaBits.join(' · ') || key)}</div>
          </div>
          <div class="row">
            <button class="btn" type="button"
              data-recent-open="${escapeHtml(item.kind || key)}"
              data-recent-id="${escapeHtml(item.id || '')}"
              data-recent-name="${escapeHtml(item.name || '')}">Open</button>
          </div>
        </div>
      `;
    }).join('');
    return `<div class="recent-group"><h4>${escapeHtml(label)}</h4>${rows}</div>`;
  }).join('');
}

async function refreshRecentItems() {
  const wrap = $('recent-items-grid');
  if (wrap) wrap.innerHTML = '<div class="card-lite"><div class="muted">Loading recent items...</div></div>';
  try {
    const data = await safeFetchJson('/api/recent-items?limit=6');
    renderRecentItems(data.items || {});
    setStatus('recent-items-status', 'Recent items refreshed.');
  } catch (e) {
    if (wrap) wrap.innerHTML = '<div class="card-lite"><div class="muted">Could not load recent items.</div></div>';
    setStatus('recent-items-status', e.message || 'Could not load recent items.', 'error');
  }
}

function updateBackendDependentUI() {
  const textSession = getRoleSession('text');
  const imageSession = getRoleSession('image');
  const textConnected = !!textSession.connected;
  const imageConnected = !!imageSession.connected;
  const nextCatalogSourceKey = getGenerationCatalogSourceKey(imageSession);
  const backendChanged = nextCatalogSourceKey !== generationCatalogSourceKey;

  updateBackendRequiredNote(
    'prompt-text-backend-note',
    'prompt-text-backend-note-body',
    textConnected,
    'Text backend connected. Prompt generation, continue, and improvement tools are unlocked.',
    'Connect a Text Backend to generate prompts, continue cut-off runs, and use improvement tools. Local saves and Prompt QA still work offline.',
  );
  updateBackendRequiredNote(
    'caption-text-backend-note',
    'caption-text-backend-note-body',
    textConnected,
    'Text backend connected. Captioning, character improvement, and batch caption actions are unlocked.',
    'Connect a Text Backend to caption images, improve character sheets, and run batch caption jobs. Presets and library browsing still work offline.',
  );
  updateBackendRequiredNote(
    'batch-text-backend-note',
    'batch-text-backend-note-body',
    textConnected,
    'Active Text Backend connected. Run, resume, and retry actions are ready.',
    'Preview still works offline. Run, resume, and retry actions unlock after a Text Backend is connected.',
  );
  updateBackendRequiredNote(
    'generation-image-backend-note',
    'generation-image-backend-note-body',
    imageConnected,
    'Image backend connected. Queue, cancel, and catalog refresh are unlocked.',
    'Connect an Image Backend to wake up queue polling and generation actions. Prompt prep stays usable offline.',
  );

  setButtonsDisabled([
    'btn-generate-prompt',
    'btn-continue-prompt',
    'btn-sort-tags',
    'btn-shorten-prompt',
    'btn-expand-prompt',
    'btn-fix-contradictions',
    'btn-convert-style',
    'btn-caption-image',
    'btn-caption-selected-area',
    'btn-improve-character',
    'btn-run-batch',
    'btn-batch-resume',
    'btn-batch-retry',
  ], !textConnected);

  setButtonsDisabled([
    'btn-generation-run',
    'btn-generation-pause',
    'btn-generation-queue',
    'btn-generation-cancel',
  ], !imageConnected);

  if (!imageConnected) {
    generationCatalogLoaded = false;
    generationCatalogSourceKey = '';
  }

  updateGenerationShellSummary(imageSession);
  syncGenerationLaunchAvailability();
  if (imageConnected) {
    const shouldForceCatalogRefresh = backendChanged || generationCheckpointLooksEmpty();
    refreshGenerationCatalog(shouldForceCatalogRefresh).catch(() => {});
  }
}
