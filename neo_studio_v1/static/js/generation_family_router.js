window.NeoGenerationFamilyRouter = window.NeoGenerationFamilyRouter || (() => {
  const defs = {
    sdxl_sd: {
      id: 'sdxl_sd',
      label: 'SDXL / SD',
      kicker: 'Core family',
      modelSource: 'checkpoint',
      allowedModes: ['txt2img', 'img2img', 'inpaint', 'outpaint'],
      capabilities: ['Checkpoint core', 'Standard inpaint', 'Standard outpaint', 'Refine'],
      note: 'Checkpoint-first family for the main SDXL / SD workspace. The cleanup pass now keeps standard inpaint / outpaint explicit: SDXL stays on the classic latent mask-aware branch, while LanPaint remains staged separately until it is actually wired.',
      lockLaunch: false,
      hideSelectors: [],
      showSelectors: ['#generation-checkpoint-wrap', '[data-accordion-id="generation-controlnet-settings"]', '[data-accordion-id="generation-ipadapter-settings"]', '[data-accordion-id="generation-detailer-settings"]'],
    },
    flux: {
      id: 'flux',
      label: 'Flux',
      kicker: 'Dedicated GGUF family',
      modelSource: 'gguf',
      ggufClipMode: 'dual',
      ggufClipType: 'flux',
      allowedModes: ['txt2img', 'img2img', 'inpaint'],
      capabilities: ['Flux GGUF', 'Dual encoder', 'Low CFG', 'Shared preview'],
      note: 'Flux now owns the existing GGUF runtime instead of living behind a generic model-source toggle. That keeps the SDXL / SD path cleaner and gives Flux its own validator + launch logic.',
      lockLaunch: false,
      hideSelectors: ['[data-accordion-id="generation-ipadapter-settings"]'],
      showSelectors: ['#generation-gguf-wrap', '[data-accordion-id="generation-controlnet-settings"]', '[data-accordion-id="generation-detailer-settings"]'],
    },
    qwen_image_edit: {
      id: 'qwen_image_edit',
      label: 'Qwen Image Edit',
      kicker: 'Dedicated GGUF family',
      modelSource: 'gguf',
      ggufClipMode: 'single',
      ggufClipType: 'qwen_image',
      allowedModes: ['txt2img', 'img2img', 'inpaint'],
      capabilities: ['Qwen Image GGUF', 'LanPaint inpaint', 'Multi-image refs', 'Single-encoder lane'],
      note: 'Qwen Image Edit uses the Rapid AIO GGUF lane with TextEncodeQwenImageEditPlus. Neo now exposes the base LanPaint inpaint lane plus image2 / image3 conditioning and composition-source wiring. Depth / pose guidance are now live in the Qwen inpaint lane. Outpaint stays staged for a later phase.',
      lockLaunch: false,
      warningTitle: 'Qwen base inpaint is live',
      warningBody: 'Txt2img, img2img, and Qwen LanPaint inpaint are available. Multi-image refs plus depth / pose composition guidance are live here. Outpaint still stays staged.',
      warningBadge: 'Experimental',
      hideSelectors: ['[data-accordion-id="generation-ipadapter-settings"]'],
      showSelectors: ['#generation-gguf-wrap', '[data-accordion-id="generation-controlnet-settings"]', '[data-accordion-id="generation-detailer-settings"]'],
    },
    zimage: {
      id: 'zimage',
      label: 'Zimage',
      kicker: 'Family shell staged',
      modelSource: 'checkpoint',
      allowedModes: ['txt2img', 'img2img'],
      capabilities: ['Alt family shell', 'Shared results', 'Shared helper'],
      note: 'Zimage now has a proper family slot instead of being forced into the checkpoint / GGUF split. This pass creates the lane cleanly first, then deeper workflow wiring can happen later without wrecking the core shell again.',
      lockLaunch: true,
      launchBlocker: 'Zimage has its own family shell now, but the dedicated workflow is still staged only.',
      warningTitle: 'Zimage family staged',
      warningBody: 'The family boundary is ready. Shared preview, helper, and results stay usable, but launch stays locked until the dedicated workflow path lands.',
      warningBadge: 'Staged',
      hideSelectors: ['#generation-checkpoint-wrap', '#generation-gguf-wrap', '[data-accordion-id="generation-controlnet-settings"]', '[data-accordion-id="generation-ipadapter-settings"]', '[data-accordion-id="generation-detailer-settings"]'],
      showSelectors: [],
    },
  };

  let didBind = false;

  function getDef(key='') {
    return defs[key] || defs.sdxl_sd;
  }

  function inferFamilyFromCurrentState() {
    const explicit = String($('generation-family')?.value || '').trim();
    if (defs[explicit]) return explicit;
    const source = String($('generation-model-source')?.value || 'checkpoint').trim().toLowerCase();
    const ggufType = String($('generation-gguf-clip-type')?.value || '').trim().toLowerCase();
    if (source === 'gguf') return ggufType === 'qwen_image' ? 'qwen_image_edit' : 'flux';
    return 'sdxl_sd';
  }

  function renderButtons(activeKey) {
    document.querySelectorAll('[data-generation-family]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.generationFamily === activeKey);
    });
  }

  function renderSummary(def) {
    if ($('generation-family-kicker')) $('generation-family-kicker').textContent = def.kicker || 'Family';
    if ($('generation-family-title')) $('generation-family-title').textContent = def.label || 'Generation family';
    if ($('generation-family-note')) $('generation-family-note').textContent = def.note || '';
    const host = $('generation-family-capability-strip');
    if (host) {
      host.innerHTML = (def.capabilities || []).map(item => `<span class="generation-action-chip is-detail">${escapeHtml(item)}</span>`).join('');
    }
    const warningCard = $('generation-family-warning-card');
    if (warningCard) warningCard.classList.toggle('hidden', !(def.lockLaunch || def.warningTitle || def.warningBody));
    if ($('generation-family-warning-title')) $('generation-family-warning-title').textContent = def.warningTitle || 'Family staging note';
    if ($('generation-family-warning-body')) $('generation-family-warning-body').textContent = def.warningBody || 'This family is staged separately so Neo can keep shared previews, results, and helper flows without lying about workflow support.';
    if ($('generation-family-warning-badge')) $('generation-family-warning-badge').textContent = def.warningBadge || (def.lockLaunch ? 'Staged' : 'Ready');
  }

  function syncWorkflowModes(def) {
    const select = $('generation-workflow-type');
    if (!select) return;
    const allowed = Array.isArray(def.allowedModes) && def.allowedModes.length ? def.allowedModes : ['txt2img'];
    Array.from(select.options).forEach(opt => {
      const enabled = allowed.includes(opt.value);
      opt.hidden = !enabled;
      opt.disabled = !enabled;
    });
    if (!allowed.includes(select.value)) select.value = allowed[0];
  }

  function setVisibility(selector, visible) {
    document.querySelectorAll(selector).forEach(el => {
      el.classList.toggle('hidden', !visible);
      el.classList.toggle('is-hidden', !visible);
    });
  }

  function syncCapabilityVisibility(def) {
    const registry = window.NeoGenerationFeatureAvailability;
    const features = registry?.getFamilyFeatures ? registry.getFamilyFeatures(def.id) : {};
    const hasExplicitRegistry = !!registry?.getFamilyFeatures;
    setVisibility('#generation-model-source-wrap', false);
    setVisibility('#generation-checkpoint-wrap', hasExplicitRegistry ? !!features.checkpoint_model : def.modelSource === 'checkpoint');
    setVisibility('#generation-gguf-wrap', hasExplicitRegistry ? !!features.gguf_model : def.modelSource === 'gguf');
    setVisibility('[data-accordion-id="generation-controlnet-settings"]', hasExplicitRegistry ? !!features.controlnet : true);
    setVisibility('[data-accordion-id="generation-ipadapter-settings"]', hasExplicitRegistry ? !!features.ipadapter : true);
    setVisibility('[data-accordion-id="generation-detailer-settings"]', hasExplicitRegistry ? !!features.detailer : true);
    (def.hideSelectors || []).forEach(sel => setVisibility(sel, false));
    (def.showSelectors || []).forEach(sel => setVisibility(sel, true));
  }

  function syncSourceModel(def) {
    if ($('generation-model-source')) $('generation-model-source').value = def.modelSource || 'checkpoint';
    if ($('generation-model-source-note')) $('generation-model-source-note').textContent = def.modelSource === 'gguf'
      ? 'This family owns the GGUF runtime directly. The old generic GGUF toggle is no longer the main entry point.'
      : 'Family tabs now manage whether Neo uses the checkpoint path or the dedicated Flux GGUF runtime.';
    if (def.modelSource === 'gguf') {
      if ($('generation-gguf-clip-mode')) $('generation-gguf-clip-mode').value = def.ggufClipMode || 'dual';
      if ($('generation-gguf-clip-type')) $('generation-gguf-clip-type').value = def.ggufClipType || 'flux';
      if (def.id === 'qwen_image_edit' && $('generation-gguf-clip-secondary')) $('generation-gguf-clip-secondary').value = '';
    }
  }

  function setActiveFamily(key='', options={}) {
    const familyKey = defs[key] ? key : inferFamilyFromCurrentState();
    const def = getDef(familyKey);
    if ($('generation-family')) $('generation-family').value = def.id;
    if (window.NeoGenerationFeatureAvailability?.setActiveFamily) {
      window.NeoGenerationFeatureAvailability.setActiveFamily(def.id);
    }
    renderButtons(def.id);
    renderSummary(def);
    syncWorkflowModes(def);
    syncCapabilityVisibility(def);
    syncSourceModel(def);
    if (typeof syncGenerationGGUFUI === 'function') syncGenerationGGUFUI();

    // Phase 2: family switches must immediately re-render SDXL-only CFG Fix / Dynamic Thresholding.
    // Without this, Qwen can leave the card hidden when returning to SDXL until a hard refresh.
    if (typeof window.renderGenerationDynamicThresholding === 'function') {
      window.renderGenerationDynamicThresholding();
    }
    if (typeof window.syncGenerationDynamicThresholdingState === 'function') {
      window.syncGenerationDynamicThresholdingState('family-router-switch');
    }

    if (typeof window.syncGenerationQwenSourceImages === 'function') window.syncGenerationQwenSourceImages();
    if (!options.silent && typeof window.NeoGenerationRuntimeShell?.applyGenerationFamilyDefaults === 'function') {
      window.NeoGenerationRuntimeShell.applyGenerationFamilyDefaults(def.id, { force:true });
    }
    if (typeof syncGenerationModeUI === 'function') syncGenerationModeUI();
    if (typeof renderGenerationRuntimeProfileAndCapabilities === 'function') renderGenerationRuntimeProfileAndCapabilities();
    if (typeof renderGenerationPromptConditioning === 'function') renderGenerationPromptConditioning();
    if (typeof renderGenerationExperimentalMode === 'function') renderGenerationExperimentalMode();
    if (typeof syncGenerationLaunchAvailability === 'function') syncGenerationLaunchAvailability();
    document.dispatchEvent(new CustomEvent('neo-generation-family-changed', { detail: { family: def.id, def } }));
    if (!options.silent && typeof scheduleGenerationDraftSave === 'function') scheduleGenerationDraftSave();
    return def;
  }

  function getLaunchBlocker() {
    const familyKey = String($('generation-family')?.value || inferFamilyFromCurrentState()).trim();
    const def = getDef(familyKey);
    return def.lockLaunch ? (def.launchBlocker || 'This generation family is staged only right now.') : '';
  }

  function bind() {
    if (didBind) return;
    didBind = true;
    document.querySelectorAll('[data-generation-family]').forEach(btn => {
      btn.addEventListener('click', () => setActiveFamily(btn.dataset.generationFamily || 'sdxl_sd'));
    });
  }

  function init() {
    if (!$('generation-family-tabbar')) return;
    bind();
    setActiveFamily(inferFamilyFromCurrentState(), { silent:true });
  }

  return { init, setActiveFamily, getActiveFamily: () => String($('generation-family')?.value || inferFamilyFromCurrentState()), getLaunchBlocker, defs };
})();

window.NeoGenerationFamilyRouter.init();
