window.NeoGenerationRuntimeShell = window.NeoGenerationRuntimeShell || {};

window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey = function normalizeGenerationFamilyKey(raw='') {
  const clean = String(raw || '').trim().toLowerCase();
  if (clean === 'qwen_image_edit' || clean === 'qwen_image') return 'qwen_image';
  if (clean === 'flux') return 'flux';
  return clean || 'sdxl_sd';
}

window.NeoGenerationRuntimeShell.generationFamilyDefaults = function generationFamilyDefaults(raw='') {
  const family = window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey(raw);
  const currentUnet = String($('generation-gguf-unet')?.value || '').trim().toLowerCase();
  const qwenFast = family === 'qwen_image' && ['rapid', 'lightning', 'turbo', 'aio'].some(token => currentUnet.includes(token));
  if (family === 'flux') {
    return {
      sampler: 'euler',
      scheduler: 'simple',
      steps: '25',
      cfg: '1.0',
    };
  }
  if (family === 'qwen_image') {
    return {
      sampler: qwenFast ? 'sa_solver' : 'euler',
      scheduler: qwenFast ? 'beta' : 'simple',
      steps: qwenFast ? '4' : '25',
      cfg: '1.0',
    };
  }
  return {
    sampler: 'euler',
    scheduler: 'normal',
    steps: '28',
    cfg: '5.5',
  };
}

window.NeoGenerationRuntimeShell.pickGenerationPreferredVae = function pickGenerationPreferredVae(raw='', rows=null) {
  const family = window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey(raw);
  const catalogRows = Array.isArray(rows) ? rows : (Array.isArray(window.generationCatalogState?.vae) ? window.generationCatalogState.vae : []);
  const values = catalogRows.map(item => String(typeof generationSelectItemValue === 'function' ? generationSelectItemValue(item) : item || '').trim()).filter(Boolean);
  if (!values.length) return '';
  const lowered = values.map(value => ({ value, lower: value.toLowerCase() }));
  const matchers = family === 'qwen_image'
    ? [
        value => value === 'pig_qwen_image_vae_fp32-f16.gguf',
        value => value.includes('pig_qwen') && value.includes('vae') && value.endsWith('.gguf'),
        value => value === 'qwen_image_vae.safetensors',
        value => value.includes('qwen_image') && value.includes('vae'),
        value => value.includes('qwen') && value.includes('vae'),
        value => value.includes('diffusion_pytorch_model.safetensors') && value.includes('vae'),
      ]
    : family === 'flux'
      ? [
          value => value === 'ae.safetensors',
          value => value === 'ae',
          value => value.endsWith('/ae.safetensors'),
          value => value.includes('flux') && value.includes('vae') && !value.endsWith('.gguf'),
          value => value.startsWith('ae.') || value.startsWith('ae_'),
        ]
      : [];
  for (const matcher of matchers) {
    const found = lowered.find(item => matcher(item.lower));
    if (found) return found.value;
  }
  return '';
}


window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue = function normalizeGenerationCatalogValue(item) {
  return String(typeof generationSelectItemValue === 'function' ? generationSelectItemValue(item) : item || '').trim();
}

window.NeoGenerationRuntimeShell.qwenCompanionBaseKey = function qwenCompanionBaseKey(raw='') {
  let clean = String(raw || '').trim().toLowerCase();
  if (!clean) return '';
  clean = clean.split(/[\\/]/).pop() || clean;
  clean = clean.replace(/\.(gguf|safetensors|pt|pth|bin)$/i, '');
  clean = clean.replace(/[._-]mmproj(?:[._-]?(fp\d+|f\d+|bf16|q\d(?:_[a-z0-9]+)*))?$/i, '');
  clean = clean.replace(/[._-](q\d(?:_[a-z0-9]+)*|f\d+|fp\d+|bf16)$/i, '');
  return clean.replace(/[._-]+$/g, '');
}

window.NeoGenerationRuntimeShell.findGenerationQwenMmproj = function findGenerationQwenMmproj(selectedEncoder='', rows=null) {
  const selected = String(selectedEncoder || '').trim();
  if (!selected) return '';
  const baseKey = window.NeoGenerationRuntimeShell.qwenCompanionBaseKey(selected);
  if (!baseKey) return '';
  const qwenCatalog = generationCatalogState?.qwen_image || {};
  const ggufCatalog = generationCatalogState?.gguf || {};
  const catalogRows = Array.isArray(rows) ? rows : mergeGenerationCatalogLists(
    qwenCatalog?.mmproj,
    ggufCatalog?.mmproj,
    generationCatalogState?.clip,
    generationCatalogState?.text_encoders
  );
  const values = catalogRows.map(item => window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue(item)).filter(Boolean);
  if (!values.length) return '';
  const lowered = values.map(value => ({ value, lower: String(value || '').trim().toLowerCase() }));
  const exact = lowered.find(item => item.lower.includes('mmproj') && window.NeoGenerationRuntimeShell.qwenCompanionBaseKey(item.lower) === baseKey);
  if (exact) return exact.value;
  const prefix = lowered.find(item => item.lower.includes('mmproj') && (item.lower.startsWith(baseKey) || item.lower.includes(`${baseKey}.mmproj`) || item.lower.includes(`${baseKey}-mmproj`) || item.lower.includes(`${baseKey}_mmproj`)));
  if (prefix) return prefix.value;
  const firstQwen = lowered.find(item => item.lower.includes('mmproj') && item.lower.includes('qwen'));
  return firstQwen ? firstQwen.value : '';
}

window.NeoGenerationRuntimeShell.getGenerationGgufDropdownSources = function getGenerationGgufDropdownSources(family='') {
  const active = window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey(family || $('generation-family')?.value || $('generation-gguf-clip-type')?.value || '');
  const catalog = (typeof generationCatalogState !== 'undefined' && generationCatalogState) ? generationCatalogState : {};
  const gguf = (catalog.gguf && typeof catalog.gguf === 'object') ? catalog.gguf : {};
  const qwen = (catalog.qwen_image && typeof catalog.qwen_image === 'object') ? catalog.qwen_image : {};
  const flux = (catalog.flux_gguf && typeof catalog.flux_gguf === 'object') ? catalog.flux_gguf : {};
  const unetFallback = mergeGenerationCatalogLists(catalog.unet, catalog.diffusion_models);
  const clipFallback = mergeGenerationCatalogLists(catalog.clip, catalog.text_encoders);
  const unet = mergeGenerationCatalogLists(gguf.unet, flux.unet, unetFallback);
  const qwenText = mergeGenerationCatalogLists(qwen.text_encoders, gguf.clip_single, gguf.clip, clipFallback);
  const fluxClip = mergeGenerationCatalogLists(flux.clip, gguf.clip_dual, gguf.clip, clipFallback);
  const genericClip = mergeGenerationCatalogLists(gguf.clip, gguf.clip_single, gguf.clip_dual, clipFallback);
  const mmproj = mergeGenerationCatalogLists(qwen.mmproj, gguf.mmproj, clipFallback).filter(item => String(window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue(item)).toLowerCase().includes('mmproj'));
  const vae = mergeGenerationCatalogLists(
    active === 'qwen_image' ? qwen.preferred_vae : [],
    active === 'flux' ? flux.vae : [],
    gguf.vae,
    catalog.vae
  );
  return {
    unet,
    primary: active === 'qwen_image' ? qwenText : (active === 'flux' ? fluxClip : genericClip),
    secondary: active === 'qwen_image' ? [] : (active === 'flux' ? fluxClip : genericClip),
    mmproj,
    vae,
  };
}

window.NeoGenerationRuntimeShell.refreshGenerationGgufDropdownsForFamily = function refreshGenerationGgufDropdownsForFamily(family='') {
  if (typeof populateGenerationSelect !== 'function') return false;
  const active = window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey(family || $('generation-family')?.value || $('generation-gguf-clip-type')?.value || '');
  const sources = window.NeoGenerationRuntimeShell.getGenerationGgufDropdownSources(active);
  populateGenerationSelect('generation-gguf-unet', sources.unet, 'Choose GGUF model');
  populateGenerationSelect('generation-gguf-clip-primary', sources.primary, active === 'qwen_image' ? 'Choose Qwen text encoder' : 'Choose encoder A');
  populateGenerationSelect('generation-gguf-clip-secondary', sources.secondary, active === 'qwen_image' ? 'Qwen uses single encoder' : 'Choose encoder B');
  if (sources.vae.length) populateGenerationSelect('generation-vae', sources.vae, 'Use checkpoint VAE');
  return true;
}

window.NeoGenerationRuntimeShell.applyGenerationFamilyDefaults = function applyGenerationFamilyDefaults(raw='', options={}) {
  const family = window.NeoGenerationRuntimeShell.normalizeGenerationFamilyKey(raw || $('generation-family')?.value || $('generation-gguf-clip-type')?.value || '');
  if (!family || family === 'sdxl_sd' || family === 'zimage') return false;
  const force = options && options.force === true;
  const defaults = window.NeoGenerationRuntimeShell.generationFamilyDefaults(family);
  const setValue = (id, value) => {
    const el = $(id);
    if (!el || value == null) return false;
    const next = String(value);
    if (!force && String(el.value || '').trim()) return false;
    if (String(el.value || '') === next) return false;
    el.value = next;
    el.dispatchEvent(new Event('change', { bubbles:true }));
    return true;
  };
  const setPaired = (inputId, rangeId, value) => {
    const changed = setValue(inputId, value);
    const range = $(rangeId);
    if (range && value != null) range.value = String(value);
    return changed;
  };

  let changed = false;
  changed = setValue('generation-sampler', defaults.sampler) || changed;
  changed = setValue('generation-scheduler', defaults.scheduler) || changed;
  changed = setPaired('generation-steps', 'generation-steps-range', defaults.steps) || changed;
  changed = setPaired('generation-cfg', 'generation-cfg-range', defaults.cfg) || changed;
  if (family === 'qwen_image') {
    changed = setValue('generation-refine-strategy', 'qwen_reedit') || changed;
    changed = setValue('generation-refine-mode', 'image_upscale') || changed;
    changed = setPaired('generation-refine-steps', 'generation-refine-steps-range', defaults.steps) || changed;
    changed = setValue('generation-refine-cfg', defaults.cfg) || changed;
    changed = setValue('generation-refine-sampler', defaults.sampler) || changed;
    changed = setValue('generation-refine-scheduler', defaults.scheduler) || changed;
    changed = setPaired('generation-refine-denoise', 'generation-refine-denoise-range', '0.2') || changed;
    changed = setPaired('generation-refine-scale', 'generation-refine-scale-range', '1.5') || changed;
    changed = setValue('generation-refine-resize-method', 'lanczos') || changed;
  }

  const preferredVae = window.NeoGenerationRuntimeShell.pickGenerationPreferredVae(family);
  if (preferredVae) {
    const vaeEl = $('generation-vae');
    const currentVae = String(vaeEl?.value || '').trim();
    const shouldReplace = force || !currentVae;
    if (vaeEl && shouldReplace && currentVae !== preferredVae) {
      vaeEl.value = preferredVae;
      vaeEl.dispatchEvent(new Event('change', { bubbles:true }));
      changed = true;
    }
  }
  if (changed) {
    if (typeof renderGenerationGGUFValidator === 'function') renderGenerationGGUFValidator();
    if (typeof renderGenerationRuntimeProfileAndCapabilities === 'function') renderGenerationRuntimeProfileAndCapabilities();
    if (typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
  }
  return changed;
}

window.NeoGenerationRuntimeShell.renderGenerationGGUFValidator = function renderGenerationGGUFValidator() {
  const card = $('generation-gguf-validator');
  const summary = $('generation-gguf-validator-summary');
  const badge = $('generation-gguf-validator-badge');
  const linesHost = $('generation-gguf-validator-lines');
  if (!card || !summary || !badge || !linesHost) return;
  const isGguf = String($('generation-model-source')?.value || 'checkpoint').trim().toLowerCase() === 'gguf';
  card.classList.toggle('hidden', !isGguf);
  card.classList.toggle('is-hidden', !isGguf);
  if (!isGguf) return;

  const clipMode = String($('generation-gguf-clip-mode')?.value || 'dual').trim().toLowerCase() === 'single' ? 'single' : 'dual';
  const family = normalizeGenerationGgufClipTypeForMode(clipMode, $('generation-gguf-clip-type')?.value || '');
  const modelName = trim($('generation-gguf-unet')?.value || '');
  const encoderA = trim($('generation-gguf-clip-primary')?.value || '');
  const encoderB = trim($('generation-gguf-clip-secondary')?.value || '');
  const vae = trim($('generation-vae')?.value || '');
  const sources = typeof window.NeoGenerationRuntimeShell.getGenerationGgufDropdownSources === 'function'
    ? window.NeoGenerationRuntimeShell.getGenerationGgufDropdownSources(family)
    : { unet: mergeGenerationCatalogLists(generationCatalogState?.unet, generationCatalogState?.diffusion_models), primary: mergeGenerationCatalogLists(generationCatalogState?.clip, generationCatalogState?.text_encoders), secondary: mergeGenerationCatalogLists(generationCatalogState?.clip, generationCatalogState?.text_encoders), mmproj: [] };
  const unetCatalog = sources.unet || [];
  const clipCatalog = mergeGenerationCatalogLists(sources.primary, sources.secondary);
  const qwenMmproj = family === 'qwen_image' ? window.NeoGenerationRuntimeShell.findGenerationQwenMmproj(encoderA, sources.mmproj) : '';
  const aliasPieces = [];
  if (Array.isArray(generationCatalogState?.diffusion_models) && generationCatalogState.diffusion_models.length) aliasPieces.push('diffusion_models');
  if (Array.isArray(generationCatalogState?.text_encoders) && generationCatalogState.text_encoders.length) aliasPieces.push('text_encoders');

  const checks = [
    { ok: !!modelName && unetCatalog.some(item => String(window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue(item) || item || '').toLowerCase() === modelName.toLowerCase()), label: 'GGUF model', detail: modelName || 'Pick a GGUF model' },
    { ok: !!encoderA && clipCatalog.some(item => String(window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue(item) || item || '').toLowerCase() === encoderA.toLowerCase()), label: family === 'qwen_image' ? 'Text encoder' : 'Encoder A', detail: encoderA || (family === 'qwen_image' ? 'Pick the Qwen text encoder' : 'Pick the primary encoder') },
  ];
  if (clipMode === 'dual') {
    checks.push({ ok: !!encoderB && clipCatalog.some(item => String(window.NeoGenerationRuntimeShell.normalizeGenerationCatalogValue(item) || item || '').toLowerCase() === encoderB.toLowerCase()), label: 'Encoder B', detail: encoderB || 'Pick the second encoder' });
  }
  if (family === 'qwen_image') {
    checks.push({
      ok: true,
      label: 'mmproj sidecar',
      detail: qwenMmproj
        ? `Detected companion: ${qwenMmproj}`
        : 'Neo could not confirm a matching mmproj from the current catalog. If Qwen runs correctly, this is likely a catalog-detection false alarm.'
    });
  }
  checks.push({ ok: !!vae, label: 'VAE', detail: vae || 'Pick a VAE for GGUF runs' });

  let guardrailReport = { blockers: [], warnings: [], mmproj_required: false };
  if (window.NeoGenerationGgufGuardrails && typeof window.NeoGenerationGgufGuardrails.collectReport === 'function') {
    guardrailReport = window.NeoGenerationGgufGuardrails.collectReport({
      workflow_type: $('generation-workflow-type')?.value || 'txt2img',
      mode: $('generation-workflow-type')?.value || 'txt2img',
      family: family === 'qwen_image' ? 'qwen_image_edit' : family,
      model_source: 'gguf',
      gguf_unet: modelName,
      gguf_clip_mode: clipMode,
      gguf_clip_type: family,
      gguf_clip_primary: encoderA,
      gguf_clip_secondary: encoderB,
      gguf_mmproj: qwenMmproj,
      vae,
      source_image_fields: ['generation-source-image-2', 'generation-source-image-3'].filter(id => !!$(id)?.files?.[0]).map((_, i) => `source_image__${i + 2}`),
    }, { queueContext:'validator_card' });
  }
  const guardrailBlockers = Array.isArray(guardrailReport.blockers) ? guardrailReport.blockers : [];
  const guardrailWarnings = Array.isArray(guardrailReport.warnings) ? guardrailReport.warnings : [];
  if (guardrailBlockers.length) {
    checks.push({ ok:false, label:'Workflow guardrail', detail: guardrailBlockers[0] });
  } else if (guardrailWarnings.length) {
    checks.push({ ok:true, label:'Workflow guardrail', detail: `Ready with warning: ${guardrailWarnings[0]}` });
  } else {
    checks.push({ ok:true, label:'Workflow guardrail', detail:'No Flux/Qwen GGUF guardrail blockers detected.' });
  }

  const readyCount = checks.filter(item => item.ok).length;
  const missingCount = checks.length - readyCount;
  const familyLabel = family === 'qwen_image' ? 'Qwen Image' : family.toUpperCase();
  summary.textContent = guardrailBlockers.length
    ? `${familyLabel} blocked: ${guardrailBlockers[0]}`
    : (missingCount === 0
      ? `${familyLabel} bundle looks complete. Ready to queue once the rest of the workflow is set.`
      : `${familyLabel} still needs ${missingCount} bundle piece${missingCount === 1 ? '' : 's'} before queueing.`);
  badge.textContent = guardrailBlockers.length ? 'Blocked' : (missingCount === 0 ? 'Ready' : (readyCount > 0 ? 'Needs pieces' : 'Incomplete'));
  linesHost.innerHTML = checks.map(item => {
    const icon = item.ok ? '✓' : '•';
    const badgeClass = item.ok ? 'badge ok' : 'badge';
    return `<div style="display:flex; gap:8px; align-items:flex-start; margin-top:6px;"><span class="${badgeClass}" style="min-width:26px; justify-content:center;">${icon}</span><div><strong>${escapeHtml(item.label)}:</strong> ${escapeHtml(item.detail)}</div></div>`;
  }).join('') + `<div style="margin-top:8px; opacity:0.85;">${escapeHtml(aliasPieces.length ? `Alias-aware catalog merge active: ${aliasPieces.join(' + ')}.` : 'Using the live ComfyUI GGUF catalog for this check.')}</div>` + (family === 'qwen_image' ? `<div style="margin-top:6px; opacity:0.85;">Qwen Image stays on the single-encoder path here. Select the main text encoder GGUF only; its matching mmproj file should live beside it in ComfyUI/models/text_encoders or models/mmproj. ${qwenMmproj ? `Detected mmproj companion: ${escapeHtml(qwenMmproj)}.` : 'Neo could not confirm the mmproj companion yet from the current catalog.'} Neo will prefer the pig_qwen_image_vae_fp32-f16.gguf VAE when it is available, and can still fall back to compatible Qwen safetensors VAEs.</div>` : '') + (guardrailWarnings.length ? `<div style="margin-top:6px; opacity:0.85;">Guardrail warning: ${escapeHtml(guardrailWarnings[0])}</div>` : '');
}

window.NeoGenerationRuntimeShell.currentGenerationRuntimeProfile = function currentGenerationRuntimeProfile() {
  return $('backend-low-vram-toggle')?.checked ? 'low_vram' : 'mid_vram';
}

window.NeoGenerationRuntimeShell.estimateGenerationBackendVramGiB = function estimateGenerationBackendVramGiB() {
  const devices = Array.isArray(generationSystemStats?.devices) ? generationSystemStats.devices : [];
  const first = devices.find(dev => Number(dev?.vram_total || 0) > 0) || devices[0] || null;
  const raw = Number(first?.vram_total || 0);
  return raw > 0 ? (raw / (1024 * 1024 * 1024)) : 0;
}

window.NeoGenerationRuntimeShell.renderGenerationRuntimeProfileAndCapabilities = function renderGenerationRuntimeProfileAndCapabilities() {
  const note = $('generation-runtime-profile-note');
  const strip = $('generation-runtime-capability-strip');
  if (!note || !strip) return;
  const profileKey = currentGenerationRuntimeProfile();
  const profile = generationRuntimeProfiles[profileKey] || generationRuntimeProfiles.mid_vram;
  const modelSource = String($('generation-model-source')?.value || 'checkpoint').trim().toLowerCase();
  const ggufMode = String($('generation-gguf-clip-mode')?.value || 'dual').trim().toLowerCase() === 'single' ? 'single' : 'dual';
  const ggufFamily = normalizeGenerationGgufClipTypeForMode(ggufMode, $('generation-gguf-clip-type')?.value || '');
  const features = (generationCatalogState && typeof generationCatalogState.features === 'object' && generationCatalogState.features) ? generationCatalogState.features : {};
  const vramGiB = estimateGenerationBackendVramGiB();
  const batchSize = Number($('generation-batch-size')?.value || 1);
  const refineEnabled = String($('generation-refine-enabled')?.value || 'false') === 'true';
  const supirEnabled = String($('generation-supir-enabled')?.value || 'false') === 'true';
  const isHeavyFamily = modelSource === 'gguf' && (ggufFamily === 'qwen_image' || ggufFamily === 'flux');
  const pressureBits = [];
  if (batchSize > 1) pressureBits.push(`batch ${batchSize}`);
  if (refineEnabled) pressureBits.push('redraw');
  if (supirEnabled) pressureBits.push('SUPIR');
  if (isHeavyFamily) pressureBits.push(ggufFamily === 'qwen_image' ? 'Qwen Image' : 'Flux GGUF');
  const pressureLabel = pressureBits.length ? `Current load: ${pressureBits.join(' · ')}` : 'Current load: baseline shell';
  const vramLabel = vramGiB > 0 ? `Backend VRAM ${Math.round(vramGiB * 10) / 10} GB` : 'Backend VRAM unknown';
  note.textContent = `${profile.note} ${profile.hint} ${vramLabel}. ${pressureLabel}.`;

  const chips = [];
  chips.push({ text: profile.label, ok:true });
  chips.push({ text: modelSource === 'gguf' ? `GGUF · ${ggufFamily === 'qwen_image' ? 'Qwen Image' : ggufFamily.toUpperCase()}` : 'Checkpoint workflow', ok:true });
  chips.push({ text: features.gguf_unet_loader ? 'GGUF ready' : 'GGUF loader missing', ok: !!features.gguf_unet_loader });
  chips.push({ text: features.controlnet_loader ? 'ControlNet ready' : 'ControlNet missing', ok: !!features.controlnet_loader });
  chips.push({ text: features.ipadapter_ready ? 'IP-Adapter ready' : 'IP-Adapter missing', ok: !!features.ipadapter_ready });
  chips.push({ text: features.ipadapter_faceid_ready ? 'FaceID ready' : 'FaceID missing', ok: !!features.ipadapter_faceid_ready });
  chips.push({ text: features.supir_ready ? 'SUPIR ready' : 'SUPIR missing', ok: !!features.supir_ready });
  if (vramGiB > 0) {
    const memoryTone = vramGiB < 8 ? 'Tighter memory budget' : (vramGiB < 16 ? 'Mid memory budget' : 'Open memory budget');
    chips.push({ text: memoryTone, ok: vramGiB >= 8 });
  }
  if (pressureBits.length) chips.push({ text: pressureLabel, ok: pressureBits.length < 3 && !(supirEnabled && refineEnabled) });
  strip.innerHTML = chips.map(chip => `<span class="badge${chip.ok ? ' ok' : ''}">${escapeHtml(chip.text)}</span>`).join('');
}

window.NeoGenerationRuntimeShell.syncGenerationGGUFUI = function syncGenerationGGUFUI() {
  const source = $('generation-model-source')?.value || 'checkpoint';
  const activeFamily = window.NeoGenerationFamilyRouter?.getActiveFamily?.() || String($('generation-family')?.value || '').trim();
  const modeSelect = $('generation-gguf-clip-mode');
  let clipMode = String(modeSelect?.value || 'dual').trim().toLowerCase() === 'single' ? 'single' : 'dual';
  const currentType = $('generation-gguf-clip-type')?.value || '';
  if (activeFamily === 'qwen_image_edit' || String(currentType || '').trim().toLowerCase() === 'qwen_image') {
    clipMode = 'single';
    if (modeSelect && modeSelect.value !== 'single') modeSelect.value = 'single';
  }
  const nextType = activeFamily === 'qwen_image_edit' ? 'qwen_image' : normalizeGenerationGgufClipTypeForMode(clipMode, currentType);
  const typeSelect = $('generation-gguf-clip-type');
  const desiredOptions = clipMode === 'single'
    ? [
        ['stable_diffusion', 'Stable Diffusion'],
        ['sdxl', 'SDXL'],
        ['sd3', 'SD3'],
        ['flux', 'Flux'],
        ['qwen_image', 'Qwen Image'],
      ]
    : [
        ['flux', 'Flux'],
        ['sd3', 'SD3'],
        ['sdxl', 'SDXL'],
      ];
  if (typeSelect) {
    const before = Array.from(typeSelect.options || []).map(opt => `${opt.value}:${opt.textContent}`).join('|');
    const after = desiredOptions.map(row => `${row[0]}:${row[1]}`).join('|');
    if (before !== after) {
      typeSelect.innerHTML = '';
      desiredOptions.forEach(([value, label]) => {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        typeSelect.appendChild(opt);
      });
    }
    typeSelect.value = nextType;
  }
  const isGguf = source === 'gguf';
  const isFlux = nextType === 'flux';
  const isQwenImage = nextType === 'qwen_image';
  if (isGguf && typeof window.NeoGenerationRuntimeShell.refreshGenerationGgufDropdownsForFamily === 'function') {
    window.NeoGenerationRuntimeShell.refreshGenerationGgufDropdownsForFamily(nextType);
  }
  $('generation-checkpoint-wrap')?.classList.toggle('is-hidden', isGguf);
  $('generation-gguf-wrap')?.classList.toggle('hidden', !isGguf);
  $('generation-gguf-wrap')?.classList.toggle('is-hidden', !isGguf);
  $('generation-gguf-clip-secondary-wrap')?.classList.toggle('is-hidden', !isGguf || clipMode !== 'dual');
  $('generation-gguf-guidance-wrap')?.classList.toggle('is-hidden', !isGguf || !isFlux);
  if ($('generation-gguf-clip-primary-label')) $('generation-gguf-clip-primary-label').textContent = isQwenImage ? 'Text encoder (.gguf)' : 'Encoder A';
  const note = $('generation-gguf-note');
  if (note) {
    note.textContent = isFlux
      ? 'Flux GGUF uses the dual-encoder route by default. Pick a GGUF model, its encoder pair, and a separate VAE before queueing.'
      : (isQwenImage
          ? 'Qwen Image uses the single-encoder GGUF path. Pick the main Qwen encoder GGUF here, keep its matching mmproj beside it in ComfyUI/models/text_encoders, and use the pig_qwen_image_vae_fp32-f16.gguf VAE when it is available.'
          : (clipMode === 'single'
              ? 'Single-encoder GGUF keeps the simpler prompt path. Make sure the architecture matches the encoder you picked.'
              : 'Dual-encoder GGUF is ready for SDXL / SD3 style paired encoders. Match the architecture to the encoder pair.'));
  }
  renderGenerationGGUFValidator();
  renderGenerationRuntimeProfileAndCapabilities();
  renderGenerationPromptConditioning();
  renderGenerationExperimentalMode();
}

