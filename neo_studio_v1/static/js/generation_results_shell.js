window.NeoGenerationResultsShell = window.NeoGenerationResultsShell || {};


function isGenerationDerivedPreviewJob(job) {
  const payload = job && typeof job.payload === 'object' ? job.payload : {};
  const action = payload?._neo_preview_action || null;
  return !!(
    action ||
    payload?._neo_derived_action_type ||
    payload?._neo_source_job_id ||
    payload?._neo_parent_output_id ||
    payload?._neo_image_command_type === 'preview_upscale' ||
    payload?._neo_workflow_command === 'preview_action'
  );
}



function getGenerationDerivedActionType(job) {
  const payload = job && typeof job.payload === 'object' ? job.payload : {};
  const action = payload?._neo_preview_action || {};
  return String(action.action_type || payload?._neo_derived_action_type || payload?._neo_image_command_type || '').trim().toLowerCase();
}

function shouldGenerationDerivedOutputReplaceParent(job) {
  const actionType = getGenerationDerivedActionType(job);
  return [
    'hires_fix',
    'highres_fix',
    'upscale_lab',
    'selective_repair',
    'detailer',
    'adetailer',
    'face_detailer',
    'identity_rescue',
    'local_repair',
  ].includes(actionType);
}

function rememberGenerationRunGalleryJob(job) {
  const outputs = Array.isArray(job?.outputs) ? job.outputs : [];
  if (!outputs.length) return;
  if (isGenerationDerivedPreviewJob(job)) return;
  window.NeoGenerationResultsShell.currentRunGalleryJob = JSON.parse(JSON.stringify(job));
}

function getGenerationRunGalleryJobFor(job) {
  const outputs = Array.isArray(job?.outputs) ? job.outputs : [];
  if (!isGenerationDerivedPreviewJob(job)) return job;
  const payload = job && typeof job.payload === 'object' ? job.payload : {};
  const action = payload?._neo_preview_action || {};
  const parentJobId = String(action.parent_job_id || action.source_job_id || payload?._neo_source_job_id || '').trim();
  const parentKey = String(
    action.parent_output_key ||
    action.source_output_key ||
    payload?._neo_parent_output_key ||
    payload?._neo_source_output_key ||
    ''
  ).trim();
  const stored = window.NeoGenerationResultsShell.currentRunGalleryJob || null;
  const storedId = String(stored?.id || '').trim();
  const storedDisplayId = String(stored?.__display_job_id || '').trim();
  const storedOutputs = Array.isArray(stored?.outputs) ? stored.outputs : [];
  const parentMatchesStoredOutput = !!(parentKey && storedOutputs.some(existing => {
    const key = generationOutputKey(existing);
    return key === parentKey || String(existing?.__original_output_key || '') === parentKey || String(existing?.derived_from_output_id || '') === parentKey;
  }));
  const parentMatchesStoredJob = !parentJobId || storedId === parentJobId || storedDisplayId === parentJobId;
  if (stored && storedOutputs.length > 1 && (parentMatchesStoredJob || parentMatchesStoredOutput)) {
    const merged = JSON.parse(JSON.stringify(stored));
    merged.outputs = Array.isArray(merged.outputs) ? merged.outputs.map(item => ({ ...item, job_id: item.job_id || storedId })) : [];
    const replaceParent = shouldGenerationDerivedOutputReplaceParent(job);
    outputs.forEach((item, idx) => {
      const derivedItem = {
        ...item,
        __derived_output: true,
        __replaces_parent_output: replaceParent,
        stage: item.stage || payload?._neo_derived_action_type || action.derived_stage || 'Derived pass',
        job_id: String(job?.id || ''),
        parent_output_key: parentKey || item.parent_output_key || '',
        derived_from_output_id: parentKey || item.derived_from_output_id || '',
      };
      const key = generationOutputKey(derivedItem) || `derived_${idx}`;
      if (replaceParent && parentKey) {
        const parentIndex = merged.outputs.findIndex(existing => generationOutputKey(existing) === parentKey);
        if (parentIndex >= 0) {
          merged.outputs[parentIndex] = {
            ...derivedItem,
            __batch_replacement: true,
            __original_output_key: parentKey,
            original_filename: merged.outputs[parentIndex]?.saved_filename || merged.outputs[parentIndex]?.filename || '',
          };
          return;
        }
      }
      if (parentKey) {
        const parentIndex = merged.outputs.findIndex(existing => generationOutputKey(existing) === parentKey || String(existing?.__original_output_key || '') === parentKey || String(existing?.derived_from_output_id || '') === parentKey);
        if (parentIndex >= 0 && shouldGenerationDerivedOutputReplaceParent(job)) {
          merged.outputs[parentIndex] = {
            ...derivedItem,
            __batch_replacement: true,
            __original_output_key: merged.outputs[parentIndex]?.__original_output_key || parentKey,
            original_filename: merged.outputs[parentIndex]?.saved_filename || merged.outputs[parentIndex]?.filename || '',
          };
          return;
        }
      }
      const seen = new Set(merged.outputs.map(existing => generationOutputKey(existing)).filter(Boolean));
      if (seen.has(key)) return;
      merged.outputs.push(derivedItem);
    });
    merged.__display_job_id = String(job?.id || '');
    merged.__derived_display = true;
    merged.__replace_parent_display = replaceParent;
    return merged;
  }
  return job;
}

window.NeoGenerationResultsShell.getGenerationFinishFoundationState = function getGenerationFinishFoundationState() {
  const active = typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : (generationSelectedOutputSnapshot ? { ...generationSelectedOutputSnapshot } : null);
  const refineEnabled = String($('generation-refine-enabled')?.value || 'false') === 'true';
  const refineMode = $('generation-refine-mode')?.value || 'latent';
  const refineScale = String($('generation-refine-scale')?.value || '1.5').trim() || '1.5';
  const imageUpscaleBatch = $('generation-image-upscale-batch-files')?.files?.length || 0;
  const imageUpscaleModel = String($('generation-image-upscale-model')?.selectedOptions?.[0]?.textContent || $('generation-image-upscale-model')?.value || '').trim();
  const imageUpscaleScale = String($('generation-image-upscale-scale')?.value || '2.0').trim() || '2.0';
  const detailerPrimary = !!$('generation-detailer-enabled')?.checked;
  const detailerExtra = Array.from(document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row')).filter(row => !!row.querySelector('.generation-unit-enabled')?.checked).length;
  const detailerEnabled = detailerPrimary || detailerExtra > 0;
  const primaryFaceIdEnabled = !!$('generation-ipadapter-enabled')?.checked && ($('generation-ipadapter-mode')?.value || 'standard') === 'faceid' && !!trim($('generation-ipadapter-clip-vision')?.value || '') && getGenerationIpAdapterRefCount($('generation-ipadapter-image')) > 0;
  const extraFaceIdEnabled = Array.from(document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row')).filter(row => !!row.querySelector('.generation-unit-enabled')?.checked && (row.querySelector('.generation-ipadapter-mode')?.value || 'standard') === 'faceid' && !!trim(row.querySelector('.generation-ipadapter-clip-vision')?.value || '') && getGenerationIpAdapterRefCount(row.querySelector('.generation-ipadapter-image')) > 0).length;
  const faceIdEnabledCount = (primaryFaceIdEnabled ? 1 : 0) + extraFaceIdEnabled;
  const faceIdRescueEnabled = faceIdEnabledCount > 0;
  const activeFamily = String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || '').trim();
  const supportsIdentityRescue = activeFamily !== 'qwen_image_edit';
  const supirEnabled = String($('generation-supir-enabled')?.value || 'false') === 'true';
  const supirScale = String($('generation-supir-scale')?.value || '2').trim() || '2';
  const stages = [
    {
      key: 'upscale_lab',
      label: 'Upscale Lab',
      accordionId: 'generation-hires-settings',
      targetTab: 'enhance',
      status: refineEnabled ? 'Armed' : 'Off',
      tone: refineEnabled ? 'tone-ok' : 'tone-info',
      active: refineEnabled,
      note: refineEnabled ? `${refineMode === 'image_upscale' ? 'Image upscale + preserve' : 'Latent upscale + refine'} · target ${refineScale}×.` : 'Turn this on when you want the active output to go through a second-pass polish step.',
      actionLabel: 'Open Upscale Lab',
    },
    {
      key: 'detailer',
      label: 'Selective Repair',
      accordionId: 'generation-detailer-settings',
      targetTab: 'enhance',
      status: detailerEnabled ? `${detailerPrimary ? 1 + detailerExtra : detailerExtra} pass${(detailerPrimary ? 1 + detailerExtra : detailerExtra) === 1 ? '' : 'es'}` : 'Off',
      tone: detailerEnabled ? 'tone-ok' : 'tone-info',
      active: detailerEnabled,
      note: detailerEnabled ? 'Detector-guided local cleanup is staged for later pass work.' : 'Enable this when the image works overall but faces, hands, or small areas still need repair.',
      actionLabel: 'Open Selective Repair',
    },
    {
      key: 'identity_rescue',
      label: 'Identity Rescue',
      accordionId: 'generation-ipadapter-settings',
      targetTab: 'guide',
      status: !supportsIdentityRescue ? 'Not supported' : (faceIdRescueEnabled ? `${faceIdEnabledCount} FaceID unit${faceIdEnabledCount === 1 ? '' : 's'}` : 'Off'),
      tone: !supportsIdentityRescue ? 'tone-info' : (faceIdRescueEnabled ? 'tone-ok' : 'tone-info'),
      active: supportsIdentityRescue && faceIdRescueEnabled,
      note: !supportsIdentityRescue ? 'Qwen Image does not use the FaceID / Identity Rescue finish lane. Keep identity on the Qwen multi-source reference lane instead.' : (faceIdRescueEnabled ? 'FaceID rescue is armed for preserve-first identity correction on the active output.' : 'Use FaceID here when the composition works but the person drifted too far from the reference.'),
      actionLabel: supportsIdentityRescue ? 'Open Identity Rescue' : 'Qwen uses source refs',
    },
    {
      key: 'supir',
      label: 'SUPIR',
      accordionId: 'generation-supir-settings',
      targetTab: 'enhance',
      status: supirEnabled ? 'Armed' : 'Off',
      tone: supirEnabled ? 'tone-ok' : 'tone-info',
      active: supirEnabled,
      note: supirEnabled ? `Heavy rescue pass ready at ${supirScale}×.` : 'Keep this for rough images that need a stronger rescue than the standard finish tools.',
      actionLabel: 'Open SUPIR',
    },
    {
      key: 'image_upscale',
      label: 'Image Upscale',
      accordionId: 'generation-image-upscale-settings',
      targetTab: 'enhance',
      status: active || imageUpscaleBatch ? 'Ready' : 'Needs output',
      tone: active || imageUpscaleBatch ? 'tone-info' : 'tone-warn',
      active: !!(active || imageUpscaleBatch),
      manual: true,
      note: active
        ? `Preserve-first pixel upscale ready on the active output${imageUpscaleModel ? ` using ${imageUpscaleModel}` : ' using interpolation only'} at ${imageUpscaleScale}×.`
        : (imageUpscaleBatch ? `Uploaded batch ready at ${imageUpscaleScale}×.` : 'Pick an active output or upload one image for a preserve-first upscale.'),
      actionLabel: active ? 'Open Image Upscale' : (imageUpscaleBatch ? 'Open Batch Upscale' : 'Open Image Upscale'),
    },
  ];
  const recommendedOrder = ['Active Output', ...stages.filter(stage => stage.active).map(stage => stage.label)];
  return { active, stages, recommendedOrder };
}

window.NeoGenerationResultsShell.renderGenerationFinishFoundation = function renderGenerationFinishFoundation() {
  const host = $('generation-finish-stack-foundation-host');
  if (!host) return;
  const state = getGenerationFinishFoundationState();
  const active = state.active;
  const ready = !!active;
  host.innerHTML = `
    <div class="generation-finish-foundation${ready ? ' is-ready' : ''}">
      <div class="generation-finish-foundation-head">
        <div>
          <div class="generation-finish-foundation-title">Finish Stack Foundation</div>
          <div class="generation-finish-foundation-note">Finish tools now point at the active output instead of pretending source-routing and polish work are the same thing. Keep source/reference routing in Results, then use this lane for the later-pass stack.</div>
        </div>
        <div class="row" style="gap:8px; flex-wrap:wrap;">
          <button class="btn btn-small" type="button" data-finish-foundation-action="open-results">${ready ? 'Open Results' : 'Pick active output'}</button>
        </div>
      </div>
      <div class="generation-finish-foundation-active">
        ${active?.view_url ? `<img src="${escapeHtml(active.view_url)}" alt="${escapeHtml(active.saved_filename || active.filename || 'Active output')}" class="generation-finish-foundation-thumb" />` : '<div class="generation-finish-foundation-empty">No active output yet.</div>'}
        <div class="generation-finish-foundation-active-copy">
          <div class="generation-finish-foundation-active-title">${active ? escapeHtml(active.saved_filename || active.filename || 'Active output') : 'Choose an output first'}</div>
          <div class="generation-finish-foundation-active-note">${active ? 'This image is the current finish target. Later polish tools should build from here instead of silently forcing a workflow mode switch.' : 'Go to Results, pick the image you want to keep, then come back here to layer finish passes on top of it.'}</div>
        </div>
      </div>
      <div class="generation-finish-foundation-order">
        ${state.recommendedOrder.map((label, idx) => `<span class="generation-finish-order-chip"><span class="generation-finish-order-chip-index">${idx + 1}</span>${escapeHtml(label)}</span>`).join('')}
      </div>
      <div class="generation-finish-stage-grid">
        ${state.stages.map(stage => `
          <div class="generation-finish-stage-card${stage.active ? ' is-active' : ''}${stage.manual ? ' is-manual' : ''}">
            <div class="generation-finish-stage-head">
              <div>
                <div class="generation-finish-stage-title">${escapeHtml(stage.label)}</div>
              </div>
              <span class="generation-finish-stage-status ${escapeHtml(stage.tone)}">${escapeHtml(stage.status)}</span>
            </div>
            <div class="generation-finish-stage-note">${escapeHtml(stage.note)}</div>
            <div class="generation-finish-stage-actions">
              <button class="btn btn-small" type="button" data-finish-foundation-action="open-accordion" data-finish-foundation-target="${escapeHtml(stage.accordionId)}" data-finish-foundation-tab="${escapeHtml(stage.targetTab || 'enhance')}">${escapeHtml(stage.actionLabel)}</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

window.NeoGenerationResultsShell.renderGenerationResults = function renderGenerationResults(job) {
  const wrap = $('generation-result-list');
  if (!wrap) return;
  rememberGenerationRunGalleryJob(job);
  const renderJob = getGenerationRunGalleryJobFor(job);
  const details = $('generation-output-details');
  const outputs = Array.isArray(renderJob?.outputs) ? renderJob.outputs : [];
  if (renderJob?.__derived_display && outputs.length > 1) {
    window.NeoGenerationResultsShell.currentRunGalleryJob = JSON.parse(JSON.stringify(renderJob));
  }
  if (!outputs.length) {
    const activeJobId = String(lastGenerationJobId || generationLatestJobSnapshot?.id || '').trim();
    const incomingJobId = String(renderJob?.__display_job_id || renderJob?.id || job?.id || '').trim();
    const hasActiveOutput = !!(typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : generationSelectedOutputSnapshot);
    // Do not let an older/stuck job with zero outputs wipe a completed batch
    // gallery/preview. This was the reason batch runs showed only the last
    // live preview while the thumbnail strip went back to empty.
    if (hasActiveOutput && activeJobId && incomingJobId && incomingJobId !== activeJobId) {
      return;
    }
    wrap.innerHTML = '<span class="muted">No rendered outputs saved yet.</span>';
    if (details) details.innerHTML = '';
    clearGenerationActiveOutputSnapshot?.({ syncPreviewTarget:true });
    renderGenerationFinishFoundation();
    return;
  }

  const currentActive = typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : (generationSelectedOutputSnapshot ? { ...generationSelectedOutputSnapshot } : null);
  const activeKey = generationOutputKey(currentActive);
  const pendingFocus = generationPendingDerivedFocus && String(generationPendingDerivedFocus.jobId || '') === String(job?.id || '')
    ? { ...generationPendingDerivedFocus }
    : null;
  const pendingChildKey = pendingFocus && Array.isArray(pendingFocus.childKeys)
    ? String(pendingFocus.childKeys.find(Boolean) || '').trim()
    : '';
  const pendingChild = pendingChildKey ? outputs.find(item => generationOutputKey(item) === pendingChildKey) : null;
  const pendingParentMatchesActive = !!(pendingFocus?.parentKey && activeKey && pendingFocus.parentKey === activeKey);
  const preserved = activeKey ? outputs.find(item => generationOutputKey(item) === activeKey || item.__original_output_key === activeKey) : null;
  // During a preview action, keep the selected parent image highlighted until
  // the derived child is actually registered. Do not jump to output #1, because
  // that makes it look like the wrong batch image is being processed.
  const baseSelection = pendingChild || preserved || (pendingParentMatchesActive ? preserved : null) || outputs[0] || null;
  const primary = baseSelection ? { ...baseSelection, __batch: outputs.length > 1, job_id: baseSelection.job_id || String(renderJob?.__display_job_id || renderJob?.id || job?.id || '') } : null;
  if (primary?.view_url) activateGenerationOutput(primary, { label: outputs.length > 1 ? `Batch preview · image ${Math.max(1, outputs.findIndex(item => generationOutputKey(item) === generationOutputKey(primary)) + 1)}` : 'Latest final output' });
  else if (primary) {
    renderGenerationOutputDetails(primary);
    clearGenerationActiveOutputSnapshot?.({ syncPreviewTarget:true });
  }

  if (pendingFocus) {
    const selectedKey = generationOutputKey(primary);
    const resolvedKey = pendingChildKey || selectedKey || '';
    if (resolvedKey) {
      generationPendingDerivedFocus = null;
    }
  }

  if (outputs.length === 1) {
    wrap.innerHTML = '';
    return;
  }

  wrap.innerHTML = `<div class="generation-result-gallery">${outputs.map((item, idx) => {
    const sourceName = item.saved_filename || item.filename || `output_${idx+1}`;
    const derivedLabel = item.__batch_replacement ? ' · repaired' : (item.__derived_output ? ' · derived' : '');
    const primaryKey = generationOutputKey(primary);
    const itemKey = generationOutputKey(item);
    const activeClass = (itemKey === primaryKey || item.__original_output_key === primaryKey || primary?.__original_output_key === itemKey) ? ' is-active' : '';
    return `<div class="generation-result-thumb-card${activeClass}" data-generation-output-index="${idx}" title="Click to zoom this image"><img src="${item.view_url || ''}" alt="${escapeHtml(sourceName)}" class="generation-result-thumb" /><div class="generation-result-thumb-name">${escapeHtml(sourceName + derivedLabel)}</div></div>`;
  }).join('')}</div>`;

  wrap.querySelectorAll('[data-generation-output-index]').forEach(card => {
    card.addEventListener('click', () => {
      const idx = Number(card.getAttribute('data-generation-output-index') || 0);
      const selected = outputs[idx];
      if (!selected) return;
      activateGenerationOutput({ ...selected, __batch: true, job_id: selected.job_id || String(renderJob?.__display_job_id || renderJob?.id || job?.id || '') }, { openZoom: false, label: `Batch preview · image ${idx + 1}` });
      wrap.querySelectorAll('.generation-result-thumb-card').forEach(row => row.classList.remove('is-active'));
      card.classList.add('is-active');
    });
  });
}

window.NeoGenerationResultsShell.pollGenerationJob = function pollGenerationJob(jobId, options={}) {
  const target = String(jobId || '').trim();
  if (!target) return;
  const intervalMs = Math.max(1200, Number(options.intervalMs || 2000));
  const maxAttempts = Math.max(10, Number(options.maxAttempts || 180));
  let attempts = 0;
  stopGenerationPolling();
  generationActivePollJobId = target;

  const tick = async () => {
    if (!generationActivePollJobId || generationActivePollJobId !== target) return;
    attempts += 1;
    const job = await fetchGenerationJob(target, { silent:true });
    const state = String(job?.state || '').toLowerCase();
    if (state === 'completed') {
      stopGenerationPolling();
      closeGenerationProgressSocket();
      // Final websocket previews only show the last image in a batch.
      // Re-hydrate the job after completion so the Results shell gets every
      // persisted backend output before rendering the thumbnail strip.
      const hydrated = await fetchGenerationJob(target, { silent:true });
      const outputCount = Array.isArray(hydrated?.outputs) ? hydrated.outputs.length : 0;
      if (outputCount <= 1) {
        window.setTimeout(() => { fetchGenerationJob(target, { silent:true }); }, 750);
      }
      setStatus('generation-status', outputCount > 1 ? `Generation finished. ${outputCount} outputs loaded.` : 'Generation finished. Output preview updated.');
      await fetchGenerationState(true);
      await fetchGenerationJob(target, { silent:true });
      return;
    }
    if (['finalizing_output', 'outputs_registered', 'persisting_outputs'].includes(state)) {
      setStatus('generation-status', job?.status_text || 'Finalizing output registration…');
    }
    if (['error', 'failed'].includes(state)) {
      stopGenerationPolling();
      closeGenerationProgressSocket();
      setStatus('generation-status', job?.error || job?.status_text || 'Generation failed.', 'error');
      await fetchGenerationState(true);
      return;
    }
    if (state === 'cancelled') {
      stopGenerationPolling();
      closeGenerationProgressSocket();
      setStatus('generation-status', job?.status_text || 'Generation interrupted.', 'warn');
      await fetchGenerationState(true);
      return;
    }
    if (attempts >= maxAttempts) {
      stopGenerationPolling();
      closeGenerationProgressSocket();
      setStatus('generation-status', 'Still waiting on ComfyUI. Use Refresh queue to check again.', 'warn');
      return;
    }
    generationPollTimer = window.setTimeout(tick, intervalMs);
  };

  generationPollTimer = window.setTimeout(tick, 600);
}

window.NeoGenerationResultsShell.refreshGenerationCatalog = async function refreshGenerationCatalog(force=false) {
  const imageSession = getRoleSession('image');
  if (!imageSession.connected) {
    generationCatalogLoaded = false;
    generationCatalogSourceKey = '';
    generationSystemStats = {};
      generationCatalogState = { checkpoints: [], unet: [], diffusion_models: [], clip: [], text_encoders: [], loras: [], controlnet: [], ipadapter: [], clip_vision: [], vae: [], upscalers: [], facerestore_models: [], samplers: generationFallbackSamplers.slice(), schedulers: generationFallbackSchedulers.slice(), features:{}, res4lyf:{ installed:false, ready:false, status:'not_installed', samplers:[], schedulers:[], has_clownshark_sampler:false } };
    populateGenerationSelect('generation-checkpoint', [], 'Connect ComfyUI to load checkpoints', false);
    populateGenerationSelect('generation-gguf-unet', [], 'Connect ComfyUI to load GGUF models', false);
    populateGenerationSelect('generation-gguf-clip-primary', [], 'Connect ComfyUI to load encoders', false);
    populateGenerationSelect('generation-gguf-clip-secondary', [], 'Choose the second encoder', false);
    populateGenerationSelect('generation-vae', [], 'Use checkpoint VAE', false);
    populateGenerationSelect('generation-sampler', generationFallbackSamplers, 'Choose sampler', false);
    populateGenerationSelect('generation-scheduler', generationFallbackSchedulers, 'Choose schedule', false);
    refreshGenerationDynamicOptions();
    if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus();
    renderGenerationGGUFValidator();
    generationSystemStats = {};
    window.dispatchEvent(new CustomEvent('neo:generation-catalog-refreshed', { detail: { catalog: generationCatalogState, system_stats: generationSystemStats, connected: false } }));
    renderGenerationRuntimeProfileAndCapabilities();
    renderGenerationPromptConditioning();
    renderGenerationExperimentalMode();
    if (typeof renderGenerationDynamicThresholding === 'function') renderGenerationDynamicThresholding();
    fetchGenerationDependencyAudit({ force:true, silent:true }).catch(() => {});
    return;
  }

  const sourceKey = getGenerationCatalogSourceKey(imageSession);
  if (force || sourceKey !== generationCatalogSourceKey) generationCatalogLoaded = false;
  generationCatalogSourceKey = sourceKey;
  if (generationCatalogLoaded && !force && !generationCheckpointLooksEmpty()) return;

  try {
    const url = `/api/generation/catalog?_=${Date.now()}`;
    const data = await safeFetchJson(url, { cache:'no-store' });
    const catalog = (data && typeof data.catalog === 'object' && data.catalog)
      ? data.catalog
      : (data && typeof data === 'object' ? data : {});
    const listFrom = (...keys) => {
      for (const key of keys) {
        const value = catalog?.[key];
        if (Array.isArray(value)) return value;
        if (value && typeof value === 'object') {
          const nested = value.models || value.items || value.files || value.choices || value.options || value.names;
          if (Array.isArray(nested)) return nested;
        }
      }
      return [];
    };
    const nestedListFrom = (obj, ...keys) => {
      if (!obj || typeof obj !== 'object') return [];
      for (const key of keys) {
        const value = obj?.[key];
        if (Array.isArray(value)) return value;
        if (value && typeof value === 'object') {
          const nested = value.models || value.items || value.files || value.choices || value.options || value.names;
          if (Array.isArray(nested)) return nested;
        }
      }
      return [];
    };
    const preferredGenerationList = (preferred, ...fallbacks) => {
      const primary = Array.isArray(preferred) ? preferred : [];
      if (primary.length) return primary;
      return mergeGenerationCatalogLists(...fallbacks);
    };
    const checkpoints = listFrom('checkpoints');
    const rawGgufUnet = listFrom('unet');
    const rawDiffusionModels = listFrom('diffusion_models');
    const rawGgufClip = listFrom('clip');
    const rawTextEncoders = listFrom('text_encoders');
    const rawVae = listFrom('vae');
    const ggufCatalog = (catalog && typeof catalog.gguf === 'object' && catalog.gguf) ? catalog.gguf : {};
    const qwenCatalog = (catalog && typeof catalog.qwen_image === 'object' && catalog.qwen_image) ? catalog.qwen_image : {};
    const fluxCatalog = (catalog && typeof catalog.flux_gguf === 'object' && catalog.flux_gguf) ? catalog.flux_gguf : {};
    const explicitGgufUnet = nestedListFrom(ggufCatalog, 'unet');
    const explicitGgufClip = nestedListFrom(ggufCatalog, 'clip');
    const explicitGgufClipSingle = nestedListFrom(ggufCatalog, 'clip_single');
    const explicitGgufClipDual = nestedListFrom(ggufCatalog, 'clip_dual');
    const explicitGgufMmproj = nestedListFrom(ggufCatalog, 'mmproj');
    const explicitGgufVae = nestedListFrom(ggufCatalog, 'vae');
    const explicitQwenTextEncoders = nestedListFrom(qwenCatalog, 'text_encoders', 'clip', 'encoders');
    const explicitQwenMmproj = nestedListFrom(qwenCatalog, 'mmproj');
    const explicitQwenVae = nestedListFrom(qwenCatalog, 'preferred_vae', 'vae');
    const explicitFluxUnet = nestedListFrom(fluxCatalog, 'unet');
    const explicitFluxClip = nestedListFrom(fluxCatalog, 'clip');
    const explicitFluxVae = nestedListFrom(fluxCatalog, 'vae');
    const ggufUnet = preferredGenerationList(
      mergeGenerationCatalogLists(explicitGgufUnet, explicitFluxUnet),
      rawGgufUnet,
      rawDiffusionModels
    );
    const ggufClip = preferredGenerationList(
      mergeGenerationCatalogLists(explicitGgufClip, explicitGgufClipSingle, explicitGgufClipDual),
      rawGgufClip,
      rawTextEncoders
    );
    const ggufClipSingle = preferredGenerationList(explicitGgufClipSingle, explicitQwenTextEncoders, ggufClip, rawTextEncoders, rawGgufClip);
    const ggufClipDual = preferredGenerationList(explicitGgufClipDual, explicitFluxClip, ggufClip, rawGgufClip, rawTextEncoders);
    const ggufMmproj = preferredGenerationList(mergeGenerationCatalogLists(explicitGgufMmproj, explicitQwenMmproj), rawTextEncoders, rawGgufClip);
    const qwenTextEncoders = preferredGenerationList(explicitQwenTextEncoders, ggufClipSingle, rawTextEncoders, rawGgufClip);
    const fluxClip = preferredGenerationList(explicitFluxClip, ggufClipDual, rawGgufClip, rawTextEncoders);
    const vaes = preferredGenerationList(mergeGenerationCatalogLists(explicitGgufVae, explicitFluxVae, explicitQwenVae), rawVae);
    const mergeGenerationUniqueChoices = (...lists) => {
      const out = [];
      const seen = new Set();
      lists.forEach(list => {
        (Array.isArray(list) ? list : []).forEach(item => {
          const value = String(generationSelectItemValue(item) || item || '').trim();
          const key = value.toLowerCase();
          if (!value || seen.has(key)) return;
          seen.add(key);
          out.push(item);
        });
      });
      return out;
    };
    const samplers = listFrom('samplers').length ? listFrom('samplers') : generationFallbackSamplers;
    const rawSchedulers = listFrom('schedulers').length ? listFrom('schedulers') : generationFallbackSchedulers;
    const catalogRES4LYF = (catalog && typeof catalog.res4lyf === 'object' && catalog.res4lyf) ? catalog.res4lyf : { installed:false, ready:false, status:'not_installed', samplers:[], schedulers:[], has_clownshark_sampler:false };
    const schedulers = mergeGenerationUniqueChoices(rawSchedulers, Array.isArray(catalogRES4LYF.schedulers) ? catalogRES4LYF.schedulers : []);
    generationCatalogState = {
      checkpoints,
      unet: ggufUnet,
      diffusion_models: rawDiffusionModels,
      clip: ggufClip,
      text_encoders: rawTextEncoders,
      gguf: {
        ...(ggufCatalog || {}),
        unet: ggufUnet,
        clip: ggufClip,
        clip_single: ggufClipSingle,
        clip_dual: ggufClipDual,
        mmproj: ggufMmproj,
        vae: explicitGgufVae.length ? explicitGgufVae : vaes,
      },
      qwen_image: {
        ...(qwenCatalog || {}),
        text_encoders: qwenTextEncoders,
        mmproj: ggufMmproj,
        preferred_vae: explicitQwenVae,
      },
      flux_gguf: {
        ...(fluxCatalog || {}),
        unet: ggufUnet,
        clip: fluxClip,
        vae: explicitFluxVae.length ? explicitFluxVae : vaes,
      },
      loras: listFrom('loras'),
      controlnet: listFrom('controlnet'),
      ipadapter: listFrom('ipadapter'),
      clip_vision: listFrom('clip_vision'),
      vae: vaes,
      upscalers: listFrom('upscale_models', 'upscalers'),
      facerestore_models: listFrom('facerestore_models'),
      samplers,
      schedulers,
      features: (catalog && typeof catalog.features === 'object' && catalog.features) ? catalog.features : {},
      dynamic_thresholding: (catalog && typeof catalog.dynamic_thresholding === 'object' && catalog.dynamic_thresholding) ? catalog.dynamic_thresholding : {},
      res4lyf: catalogRES4LYF,
    };
    populateGenerationSelect('generation-checkpoint', checkpoints, 'Choose checkpoint');
    populateGenerationSelect('generation-gguf-unet', ggufUnet, 'Choose GGUF model');
    populateGenerationSelect('generation-gguf-clip-primary', qwenTextEncoders.length ? qwenTextEncoders : ggufClip, 'Choose encoder A');
    populateGenerationSelect('generation-gguf-clip-secondary', fluxClip.length ? fluxClip : ggufClipDual, 'Choose encoder B');
    populateGenerationSelect('generation-vae', vaes, 'Use checkpoint VAE');
    populateGenerationSelect('generation-sampler', samplers, 'Choose sampler');
    populateGenerationSelect('generation-scheduler', schedulers, 'Choose schedule');
    populateGenerationSelect('generation-refine-upscaler', generationCatalogState.upscalers, 'Interpolation only');
    populateGenerationSelect('generation-image-upscale-model', generationCatalogState.upscalers, 'Interpolation only', false);
    populateGenerationSelect('generation-image-upscale-restore-model', (generationCatalogState.facerestore_models || []).filter(item => String(generationSelectItemValue(item)).toLowerCase().includes('codeformer')), 'Choose CodeFormer model', false);
    populateGenerationSelect('generation-refine-sampler', samplers, 'Reuse main sampler', false);
    populateGenerationSelect('generation-refine-scheduler', schedulers, 'Reuse main scheduler', false);
    populateGenerationSelect('generation-supir-model', checkpoints, 'Choose SUPIR checkpoint', false);
    populateGenerationSelect('generation-supir-sdxl-model', checkpoints, 'Choose SDXL checkpoint', false);
    refreshGenerationDynamicOptions();
    if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus();
    syncGenerationGGUFUI();
    if (typeof window.NeoGenerationRuntimeShell?.applyGenerationFamilyDefaults === 'function') {
      const activeFamily = String($('generation-family')?.value || $('generation-gguf-clip-type')?.value || '').trim();
      window.NeoGenerationRuntimeShell.applyGenerationFamilyDefaults(activeFamily, { force:false });
    }
    if (pendingGenerationDraft) applyGenerationDraft(pendingGenerationDraft);
    await applyGenerationLoraCompatibilityFilter({ refreshLibrary:false, force:true });
    generationCatalogLoaded = true;
    generationSystemStats = (data && typeof data.system_stats === 'object' && data.system_stats) ? data.system_stats : {};
      window.dispatchEvent(new CustomEvent('neo:generation-catalog-refreshed', { detail: { catalog: generationCatalogState, system_stats: generationSystemStats, connected: true } }));
      renderGenerationPromptConditioning();
      renderGenerationExperimentalMode();
    if (typeof renderGenerationDynamicThresholding === 'function') renderGenerationDynamicThresholding();
    fetchGenerationDependencyAudit({ silent:true }).catch(() => {});
    const devices = data.system_stats?.devices || [];
    if (devices.length && $('generation-backend-summary')) {
      const dev = devices[0];
      const vram = dev.vram_total ? ` · VRAM ${Math.round(Number(dev.vram_total || 0) / (1024*1024*1024) * 10) / 10} GB` : '';
      $('generation-backend-summary').textContent += ` · ${dev.name || dev.type || 'device'}${vram}`;
    }
    if (!checkpoints.length) {
      setStatus('generation-status', 'Connected, but no checkpoints were returned by the catalog refresh yet. Try Refresh Status once if needed.', 'warn');
    }
  } catch (e) {
    generationCatalogLoaded = false;
    setStatus('generation-status', e?.message || 'Could not load generation catalog.', 'error');
      window.dispatchEvent(new CustomEvent('neo:generation-catalog-refreshed', { detail: { catalog: generationCatalogState, system_stats: generationSystemStats, connected: !!imageSession.connected, error: e?.message || 'Could not load generation catalog.' } }));
      renderGenerationPromptConditioning();
      renderGenerationExperimentalMode();
    if (typeof renderGenerationDynamicThresholding === 'function') renderGenerationDynamicThresholding();
    setStatus('generation-status', e.message || 'Could not load generation catalog.', 'error');
  }
}

let nodeManagerNodes = [];

