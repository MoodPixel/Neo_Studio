window.bindAppGenerationWorkspaceControls = function bindAppGenerationWorkspaceControls() {
  ['generation-positive','generation-negative'].forEach(id => $(id)?.addEventListener('input', () => { refreshGenerationCounters(); renderGenerationPromptConditioning(); if (id === 'generation-positive') renderGenerationLoraMetaChips(); updateGenerationTiPromptPresence(); scheduleGenerationDraftSave(); }));
  ['generation-width','generation-height'].forEach(id => {
    $(id)?.addEventListener('input', () => { syncGenerationSizePresetSelectionFromInputs(); renderGenerationImagePreflight(); scheduleGenerationDraftSave(); });
    $(id)?.addEventListener('change', () => { syncGenerationSizePresetSelectionFromInputs(); renderGenerationImagePreflight(); scheduleGenerationDraftSave(); });
  });
  $('generation-size-preset')?.addEventListener('change', () => applyGenerationSizePreset($('generation-size-preset')?.value || 'custom'));
  $('generation-source-resize-mode')?.addEventListener('change', () => { renderGenerationImagePreflight(); scheduleGenerationDraftSave(); });
  $('btn-generation-preflight-fit')?.addEventListener('click', () => applyGenerationPreflightResizeMode('fit'));
  $('btn-generation-preflight-crop')?.addEventListener('click', () => applyGenerationPreflightResizeMode('crop'));
  $('btn-generation-preflight-outpaint')?.addEventListener('click', prepareGenerationOutpaintFromSource);
  $('btn-generation-preflight-controlnet')?.addEventListener('click', () => { sendGenerationSourceToReferenceLane('controlnet').catch(() => {}); });
  $('btn-generation-preflight-output')?.addEventListener('click', activateGenerationSourceAsOutputPreview);
  $('btn-generation-size-preset-add')?.addEventListener('click', addCurrentGenerationSizePreset);
  $('btn-generation-size-swap')?.addEventListener('click', swapGenerationDimensions);
  $('generation-checkpoint')?.addEventListener('change', () => { applyGenerationLoraCompatibilityFilter({ refreshLibrary:true, force:true }).catch(() => {}); scheduleGenerationDraftSave(); });
  ['generation-lora-enabled','generation-lora-name'].forEach(id => $(id)?.addEventListener('change', () => {
    updatePrimaryGenerationLoraSummary();
    if (id === 'generation-lora-name') {
      const select = $('generation-lora-name');
      const selectedValue = trim(select?.value || '');
      const selectedLabel = trim(select?.selectedOptions?.[0]?.textContent || '');
      const candidates = [selectedLabel, selectedValue].filter(Boolean);
      if (candidates.length) inspectGenerationLoraByName(candidates).catch(() => {});
    }
    scheduleGenerationDraftSave();
  }));
  $('generation-lora-strength')?.addEventListener('input', () => { updatePrimaryGenerationLoraSummary(); scheduleGenerationDraftSave(); });
  $('generation-lora-library-search')?.addEventListener('input', () => { refreshGenerationLoraLibraryBrowser({ keepSelection:false }).catch(() => {}); });
  $('generation-lora-library-select')?.addEventListener('change', () => { loadGenerationLoraLibraryRecord($('generation-lora-library-select')?.value || '').catch(() => {}); });
  $('btn-generation-lora-library-refresh')?.addEventListener('click', () => { refreshGenerationLoraLibraryBrowser({ keepSelection:true }).catch(() => {});
  refreshGenerationTiLibraryBrowser({ keepSelection:true }).catch(() => {}); });
  $('btn-generation-lora-library-scan')?.addEventListener('click', () => { scanGenerationLoraLibrary().catch(() => {}); });
  $('btn-generation-lora-library-add-to-workflow')?.addEventListener('click', addSelectedLibraryLoraToWorkflow);
  $('btn-generation-lora-library-edit')?.addEventListener('click', () => {
    if (!trim(generationLoraLibraryState.currentLid || '')) return setStatus('generation-lora-library-status', 'Pick a saved LoRA first.', 'warn');
    setGenerationLoraLibraryEditMode(!generationLoraLibraryState.editMode);
    setStatus('generation-lora-library-status', generationLoraLibraryState.editMode ? 'Edit mode enabled. Pulling + updates are now unlocked.' : 'Edit mode disabled. Chips are live again.');
  });
  $('btn-generation-lora-library-save')?.addEventListener('click', () => { saveGenerationLoraLibraryRecord().catch(() => {}); });
  $('btn-generation-lora-library-pull')?.addEventListener('click', () => { pullGenerationLoraLibraryFromCivitai().catch(() => {}); });
  $('btn-generation-lora-library-append-example')?.addEventListener('click', () => appendGenerationLoraLibraryExample(false));
  $('btn-generation-lora-library-replace-example')?.addEventListener('click', () => appendGenerationLoraLibraryExample(true));
  $('btn-generation-lora-library-preview')?.addEventListener('click', () => {
    const src = $('generation-lora-library-preview')?.getAttribute('src') || '';
    if (src) openGenerationZoomModalForSrc(src);
  });
  $('btn-generation-lora-library-preview-prev')?.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); shiftGenerationLoraPreview(-1); });
  $('btn-generation-lora-library-preview-next')?.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); shiftGenerationLoraPreview(1); });
  $('generation-lora-library-prompt-option-select')?.addEventListener('change', () => {
    generationLoraLibraryState.selectedPromptOptionId = trim($('generation-lora-library-prompt-option-select')?.value || '__default__') || '__default__';
    loadSelectedGenerationLoraPromptOption();
  });
  $('btn-generation-lora-library-prompt-load')?.addEventListener('click', () => loadSelectedGenerationLoraPromptOption());
  $('btn-generation-lora-library-prompt-save-option')?.addEventListener('click', () => saveGenerationLoraPromptOption(false));
  $('btn-generation-lora-library-prompt-update-option')?.addEventListener('click', () => saveGenerationLoraPromptOption(true));
  $('btn-generation-lora-library-prompt-delete-option')?.addEventListener('click', () => deleteSelectedGenerationLoraPromptOption());
  const debouncedGenerationTiSearch = window.NeoGenerationPerf?.debounce ? window.NeoGenerationPerf.debounce(() => { refreshGenerationTiLibraryBrowser({ keepSelection:false }).catch(() => {}); }, 180) : (() => { refreshGenerationTiLibraryBrowser({ keepSelection:false }).catch(() => {}); });
  $('generation-ti-library-search')?.addEventListener('input', debouncedGenerationTiSearch);
  $('generation-ti-library-select')?.addEventListener('change', () => { loadGenerationTiLibraryRecord($('generation-ti-library-select')?.value || '').catch(() => {}); });
  $('btn-generation-ti-library-refresh')?.addEventListener('click', () => { refreshGenerationTiLibraryBrowser({ keepSelection:true }).catch(() => {}); });
  $('btn-generation-ti-library-scan')?.addEventListener('click', () => { scanGenerationTiLibrary().catch(() => {}); });
  $('btn-generation-ti-append-positive')?.addEventListener('click', () => appendGenerationTiToken('positive'));
  $('btn-generation-ti-append-negative')?.addEventListener('click', () => appendGenerationTiToken('negative'));
  ['generation-ti-helper-target','generation-ti-base-positive','generation-ti-base-negative','generation-ti-finish-positive','generation-ti-finish-negative'].forEach(id => $(id)?.addEventListener(id === 'generation-ti-helper-target' ? 'change' : 'input', () => { updateGenerationTiPromptPresence(); scheduleGenerationDraftSave(); }));
  mountGenerationKeywordManagerInline();
  $('btn-generation-keyword-manager-open')?.addEventListener('click', openGenerationKeywordManagerModal);
  $('btn-close-generation-keyword-manager')?.addEventListener('click', closeGenerationKeywordManagerModal);
  $('generation-keyword-manager-modal')?.addEventListener('click', e => { if (e.target?.id === 'generation-keyword-manager-modal') closeGenerationKeywordManagerModal(); });
  $('btn-generation-keyword-modal-new')?.addEventListener('click', () => clearGenerationKeywordManagerForm('Ready to add a new keyword.'));
  $('btn-generation-keyword-modal-save')?.addEventListener('click', () => saveGenerationKeywordManagerRecord().catch(() => {}));
  $('btn-generation-keyword-modal-delete')?.addEventListener('click', () => deleteGenerationKeywordManagerRecord().catch(() => {}));
  $('generation-keyword-modal-search')?.addEventListener('input', () => refreshGenerationKeywordManagerBrowser(true).catch(() => {}));
  ['generation-keyword-modal-filter-cat','generation-keyword-modal-filter-sub'].forEach(id => $(id)?.addEventListener('change', () => refreshGenerationKeywordManagerBrowser(false).catch(() => {})));
  $('generation-keyword-modal-select')?.addEventListener('change', () => loadGenerationKeywordManagerRecord().catch(() => {}));
  $('btn-generation-library-export')?.addEventListener('click', exportGenerationLibraryPack);
  $('btn-generation-library-import')?.addEventListener('click', () => importGenerationLibraryPack().catch(() => {}));
  const syncGenerationLibraryExportSnapshotToggle = () => {
    const fullSnapshot = $('generation-library-export-full-snapshot');
    if (!fullSnapshot) return;
    const disabled = !!fullSnapshot.checked;
    [
      'generation-library-export-prompts',
      'generation-library-export-captions',
      'generation-library-export-characters',
      'generation-library-export-presets',
      'generation-library-export-categories',
      'generation-library-export-metadata',
      'generation-library-export-bundles',
      'generation-library-export-categories-select',
    ].forEach(id => {
      if ($(id)) $(id).disabled = disabled;
    });
  };
  $('generation-library-export-full-snapshot')?.addEventListener('change', syncGenerationLibraryExportSnapshotToggle);
  syncGenerationLibraryExportSnapshotToggle();
  $('btn-generation-ti-library-preview')?.addEventListener('click', () => {
    const src = $('generation-ti-library-preview')?.getAttribute('src') || '';
    if (src) openGenerationZoomModalForSrc(src);
  });
  const neoGenerationApp = window.NeoStudioApp?.generation || null;
  neoGenerationApp?.register('library', {
    inspectLoraFromSelect: inspectGenerationLoraFromSelect,
    loadLoraLibraryRecordBySelect: selectEl => loadGenerationLoraLibraryRecord(selectEl?.value || ''),
    addSelectedLibraryLoraToWorkflow: () => { addSelectedLibraryLoraToWorkflow().catch(() => {}); },
  });
  neoGenerationApp?.installLegacyAliases({
    inspectGenerationLoraFromSelect: neoGenerationApp?.library?.inspectLoraFromSelect || inspectGenerationLoraFromSelect,
    loadGenerationLoraLibraryRecordBySelect: neoGenerationApp?.library?.loadLoraLibraryRecordBySelect || (selectEl => loadGenerationLoraLibraryRecord(selectEl?.value || '')),
    addSelectedLibraryLoraToWorkflow: neoGenerationApp?.library?.addSelectedLibraryLoraToWorkflow || (() => { addSelectedLibraryLoraToWorkflow().catch(() => {}); }),
  });
  ['generation-controlnet-enabled','generation-controlnet-unit','generation-controlnet-preprocessor','generation-controlnet-name'].forEach(id => $(id)?.addEventListener('change', () => {
    if (id === 'generation-controlnet-unit') {
      refreshPrimaryGenerationControlnetPreprocessorFilter();
      refreshPrimaryGenerationControlnetModelFilter();
    } else if (id === 'generation-controlnet-preprocessor') {
      refreshPrimaryGenerationControlnetModelFilter();
    }
    updatePrimaryGenerationControlnetSummary();
    scheduleGenerationDraftSave();
  }));
  $('generation-controlnet-strength')?.addEventListener('input', () => { updatePrimaryGenerationControlnetSummary(); scheduleGenerationDraftSave(); });
  $('generation-control-image')?.addEventListener('change', () => { updatePrimaryGenerationControlnetSummary(); scheduleGenerationDraftSave(); });
  $('btn-generation-controlnet-build-map')?.addEventListener('click', () => { buildGenerationControlnetMap().catch(() => {}); });
  $('btn-generation-tagassist-run')?.addEventListener('click', () => { runGenerationTagAssist().catch(() => {}); });
  $('btn-generation-tagassist-positive')?.addEventListener('click', () => { appendGenerationTagAssistSelection('positive'); });
  $('btn-generation-tagassist-negative')?.addEventListener('click', () => { appendGenerationTagAssistSelection('negative'); });
  $('btn-generation-tagassist-copy')?.addEventListener('click', () => { copyGenerationTagAssistTags().catch(() => {}); });
  ['generation-ipadapter-enabled','generation-ipadapter-mode','generation-ipadapter-name','generation-ipadapter-clip-vision','generation-ipadapter-faceid-preset','generation-ipadapter-faceid-provider','generation-ipadapter-weight-type','generation-ipadapter-combine-embeds','generation-ipadapter-embeds-scaling'].forEach(id => $(id)?.addEventListener('change', () => {
    updatePrimaryGenerationIpAdapterSummary();
    scheduleGenerationDraftSave();
  }));
  ['generation-ipadapter-weight','generation-ipadapter-weight-faceidv2','generation-ipadapter-faceid-lora-strength','generation-ipadapter-start-at','generation-ipadapter-end-at'].forEach(id => $(id)?.addEventListener('input', () => {
    updatePrimaryGenerationIpAdapterSummary();
    scheduleGenerationDraftSave();
  }));
  $('generation-ipadapter-image')?.addEventListener('change', () => { updatePrimaryGenerationIpAdapterSummary(); scheduleGenerationDraftSave(); });
  updateGenerationIpAdapterOptionExplainer($('generation-ipadapter-option-explainer'), 'mode', $('generation-ipadapter-mode')?.value || 'standard');
  $('generation-workflow-type')?.addEventListener('change', () => { syncGenerationModeUI(); updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'); syncGenerationActionZoneFromShell(); scheduleGenerationDraftSave(); });
  $('generation-model-source')?.addEventListener('change', () => { syncGenerationGGUFUI(); renderGenerationRuntimeProfileAndCapabilities(); renderGenerationPromptConditioning(); scheduleGenerationDraftSave(); });
  $('generation-family')?.addEventListener('change', () => { window.NeoGenerationFamilyRouter?.setActiveFamily($('generation-family')?.value || 'sdxl_sd'); scheduleGenerationSectionBadgeRefresh(); });
  $('generation-family')?.addEventListener('change', syncGenerationPreviewQwenUnsupportedActions);
  document.addEventListener('neo-generation-family-changed', syncGenerationPreviewQwenUnsupportedActions);
document.addEventListener('neo-generation-family-changed', () => { scheduleGenerationSectionBadgeRefresh(); });
  syncGenerationPreviewQwenUnsupportedActions();
  $('generation-runtime-profile')?.addEventListener('change', () => { renderGenerationRuntimeProfileAndCapabilities(); scheduleGenerationDraftSave(); });
  ['generation-experimental-mode','generation-advanced-slot-a','generation-advanced-slot-b'].forEach(id => $(id)?.addEventListener('change', () => { renderGenerationExperimentalMode(); scheduleGenerationDraftSave(); }));
  ['generation-prompt-conditioning-mode','generation-clip-skip','generation-gguf-clip-mode','generation-gguf-clip-type'].forEach(id => $(id)?.addEventListener('change', () => { renderGenerationPromptConditioning(); renderGenerationExperimentalMode(); scheduleGenerationDraftSave(); }));
  $('generation-gguf-unet')?.addEventListener('change', () => { renderGenerationGGUFValidator(); if (typeof window.NeoGenerationRuntimeShell?.applyGenerationFamilyDefaults === 'function') window.NeoGenerationRuntimeShell.applyGenerationFamilyDefaults(($('generation-family')?.value || $('generation-gguf-clip-type')?.value || ''), { force:true }); scheduleGenerationDraftSave(); fetchGenerationDependencyAudit({ silent:true }).catch(() => {}); });
  $('generation-gguf-clip-mode')?.addEventListener('change', () => {
    if ((window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '') === 'qwen_image_edit' && $('generation-gguf-clip-mode')) {
      $('generation-gguf-clip-mode').value = 'single';
    }
    syncGenerationGGUFUI();
    scheduleGenerationDraftSave();
  });
  $('generation-gguf-clip-type')?.addEventListener('change', () => {
    const requestedFamily = String($('generation-gguf-clip-type')?.value || '').trim().toLowerCase();
    if (requestedFamily === 'qwen_image' && $('generation-gguf-clip-mode')) {
      $('generation-gguf-clip-mode').value = 'single';
    }
    syncGenerationGGUFUI();
    const modelSource = String($('generation-model-source')?.value || 'checkpoint').trim().toLowerCase();
    const family = String($('generation-gguf-clip-type')?.value || '').trim().toLowerCase();
    if (modelSource === 'gguf' && typeof window.NeoGenerationRuntimeShell?.applyGenerationFamilyDefaults === 'function' && ['flux', 'qwen_image'].includes(family)) {
      window.NeoGenerationRuntimeShell.applyGenerationFamilyDefaults(family, { force:true });
    }
    scheduleGenerationDraftSave();
  });
  ['generation-gguf-clip-primary','generation-gguf-clip-secondary','generation-vae','generation-batch-size','generation-refine-enabled','generation-supir-enabled'].forEach(id => $(id)?.addEventListener('change', () => { renderGenerationGGUFValidator(); renderGenerationRuntimeProfileAndCapabilities(); renderGenerationPromptConditioning(); scheduleGenerationDraftSave(); fetchGenerationDependencyAudit({ silent:true }).catch(() => {}); }));
  $('generation-refine-profile')?.addEventListener('change', () => {
    const profile = $('generation-refine-profile')?.value || 'custom';
    if (profile === 'custom') {
      updateGenerationUpscaleLabSummary();
      scheduleGenerationDraftSave();
      return;
    }
    applyGenerationUpscaleLabProfile(profile);
  });
  $('generation-refine-enabled')?.addEventListener('change', () => { syncGenerationRefineUI(); markGenerationUpscaleLabCustom(); scheduleGenerationDraftSave(); });
  $('generation-refine-strategy')?.addEventListener('change', () => { syncGenerationRefineUI(); markGenerationUpscaleLabCustom(); scheduleGenerationDraftSave(); });
  $('generation-refine-mode')?.addEventListener('change', () => { syncGenerationRefineUI(); markGenerationUpscaleLabCustom(); scheduleGenerationDraftSave(); });
  $('generation-refine-tiled-vae')?.addEventListener('change', () => { syncGenerationRefineUI(); markGenerationUpscaleLabCustom(); scheduleGenerationDraftSave(); });
  ['generation-refine-resize-method','generation-refine-upscaler','generation-refine-scale','generation-refine-scale-range','generation-refine-steps','generation-refine-steps-range','generation-refine-denoise','generation-refine-denoise-range','generation-refine-cfg','generation-refine-sampler','generation-refine-scheduler','generation-refine-tile-size','generation-refine-tile-overlap'].forEach(id => $(id)?.addEventListener(id.endsWith('range') ? 'input' : ($(id)?.tagName === 'SELECT' ? 'change' : 'input'), () => { markGenerationUpscaleLabCustom(); scheduleGenerationDraftSave(); }));
  $('btn-generation-image-upscale-selected')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    runGenerationSelectedImageUpscale().catch(err => setStatus('generation-status', err?.message || 'Could not queue Image Upscale from the selected result.', 'error'));
  });
  $('btn-generation-image-upscale-batch')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    runGenerationBatchImageUpscale().catch(err => setStatus('generation-status', err?.message || 'Could not queue Image Upscale batch.', 'error'));
  });
  $('generation-image-upscale-profile')?.addEventListener('change', () => {
    const profile = $('generation-image-upscale-profile')?.value || 'custom';
    if (profile === 'custom') {
      syncGenerationImageUpscaleUI();
      scheduleGenerationDraftSave();
      scheduleGenerationSectionBadgeRefresh();
      return;
    }
    applyGenerationImageUpscaleProfile(profile);
    scheduleGenerationSectionBadgeRefresh();
  });
  ['generation-image-upscale-model','generation-image-upscale-scale','generation-image-upscale-resize-method','generation-image-upscale-restore-assist','generation-image-upscale-restore-model','generation-image-upscale-restore-fidelity','generation-image-upscale-restore-detection'].forEach(id => $(id)?.addEventListener($(id)?.tagName === 'SELECT' ? 'change' : 'input', () => { markGenerationImageUpscaleCustom(); scheduleGenerationDraftSave(); scheduleGenerationSectionBadgeRefresh(); }));
  $('generation-image-upscale-batch-files')?.addEventListener('change', () => { syncGenerationImageUpscaleUI(); scheduleGenerationDraftSave(); scheduleGenerationSectionBadgeRefresh(); });
  $('generation-supir-enabled')?.addEventListener('change', () => { syncGenerationSupirUI(); scheduleGenerationDraftSave(); });
  $('generation-supir-tiled-vae')?.addEventListener('change', () => { syncGenerationSupirUI(); scheduleGenerationDraftSave(); });
  $('btn-generation-seed-randomize')?.addEventListener('click', () => { $('generation-seed').value = generationRandomSeed(); updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'); scheduleGenerationDraftSave(); });
  $('btn-generation-seed-reuse')?.addEventListener('click', () => { if (generationLastUsedSeed) { $('generation-seed').value = generationLastUsedSeed; updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'); scheduleGenerationDraftSave(); } });
  $('btn-generation-seed-lock')?.addEventListener('click', () => { const nextLocked = !($('btn-generation-seed-lock')?.dataset.locked === 'true'); setGenerationSeedLock(nextLocked); scheduleGenerationDraftSave(); });
  document.querySelector('.generation-shell-panel')?.addEventListener('input', e => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if ((target.id && target.id.startsWith('generation-')) || String(target.className || '').includes('generation-')) scheduleGenerationDraftSave();
  });
  document.querySelector('.generation-shell-panel')?.addEventListener('change', e => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if ((target.id && target.id.startsWith('generation-')) || String(target.className || '').includes('generation-')) scheduleGenerationDraftSave();
  });
  $('generation-seed')?.addEventListener('input', () => updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'));
  $('generation-output-root')?.addEventListener('input', () => updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'));
  $('generation-output-root')?.addEventListener('change', async () => { updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'); await saveGenerationOutputSettings(); });
  $('generation-output-category')?.addEventListener('change', async () => { updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]'); await saveGenerationOutputSettings(); });
  
function syncGenerationPreviewQwenUnsupportedActions() {
  const family = String($('generation-family')?.value || window.NeoGenerationFamilyRouter?.getActiveFamily?.() || '').trim();
  const isQwen = family === 'qwen_image_edit';
  const overrides = [
    {
      id: 'btn-generation-preview-ipadapter',
      blockedTitle: 'IP-Adapter reference is disabled for Qwen Image because this family uses Qwen multi-source references instead.',
    },
    {
      id: 'btn-generation-preview-identity',
      blockedTitle: 'Identity Rescue / Face ID is disabled for Qwen Image because this finish pass is not supported on this family.',
    },
  ];
  overrides.forEach(({ id, blockedTitle }) => {
    const btn = $(id);
    if (!btn) return;
    if (!btn.dataset.defaultTitle) btn.dataset.defaultTitle = btn.getAttribute('title') || '';
    btn.disabled = isQwen;
    btn.classList.toggle('is-disabled-by-family', isQwen);
    btn.setAttribute('aria-disabled', isQwen ? 'true' : 'false');
    btn.setAttribute('title', isQwen ? blockedTitle : (btn.dataset.defaultTitle || ''));
  });
}

$('btn-generation-output-root-browse')?.addEventListener('click', browseGenerationOutputRoot);
  $('btn-generation-output-root-open')?.addEventListener('click', openGenerationOutputRoot);
  $('btn-generation-output-category-add')?.addEventListener('click', addGenerationOutputCategory);
  $('generation-output-category-new')?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addGenerationOutputCategory(); } });
  $('generation-live-preview')?.addEventListener('click', openGenerationZoomModal);
  $('btn-close-generation-zoom')?.addEventListener('click', closeGenerationZoomModal);
  $('generation-image-zoom-modal')?.addEventListener('click', e => { if (e.target?.id === 'generation-image-zoom-modal') closeGenerationZoomModal(); });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) handleGenerationQueueClick(e);
      else handleGenerationRunClick(e);
      return;
    }
    if (e.key === 'Escape') { closeGenerationZoomModal(); closeGenerationMaskEditor(); closeGenerationKeywordManagerModal(); }
  });
  const bindGenerationPreviewActionButton = (id, handler, options={}) => {
    const btn = $(id);
    if (!btn) return;
    btn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
      if (typeof handler !== 'function') {
        setStatus('generation-status', options.missingMessage || 'This preview action is not available in this build.', 'warn');
        return;
      }
      handler();
    });
  };
  // Phase 10.9: preview actions are bound through the active registry only.
  bindGenerationPreviewActionButton('btn-generation-preview-hires', () => runGenerationPreviewHiresFix());
  bindGenerationPreviewActionButton('btn-generation-preview-detailer', () => runGenerationPreviewDetailerPass());
  bindGenerationPreviewActionButton('btn-generation-preview-identity', () => runGenerationPreviewIdentityRescuePass());
  bindGenerationPreviewActionButton('btn-generation-preview-img2img', () => sendGenerationPreviewToMode('img2img'));
  bindGenerationPreviewActionButton('btn-generation-preview-inpaint', () => sendGenerationPreviewToMode('inpaint'));
  bindGenerationPreviewActionButton('btn-generation-preview-outpaint', () => sendGenerationPreviewToMode('outpaint'));
  bindGenerationPreviewActionButton('btn-generation-preview-controlnet', () => sendGenerationPreviewToReferenceLane('controlnet'));
  bindGenerationPreviewActionButton('btn-generation-preview-ipadapter', () => sendGenerationPreviewToReferenceLane('ipadapter'));
  $('generation-finish-stack-foundation-host')?.addEventListener('click', e => {
    const btn = e.target instanceof HTMLElement ? e.target.closest('[data-finish-foundation-action]') : null;
    if (!btn) return;
    const action = btn.getAttribute('data-finish-foundation-action') || '';
    if (action === 'open-results') {
      focusGenerationSetupTab('output');
      return;
    }
    if (action === 'open-accordion') {
      const target = btn.getAttribute('data-finish-foundation-target') || '';
      const tab = btn.getAttribute('data-finish-foundation-tab') || 'enhance';
      if (target) focusGenerationSetupTab(tab, target);
    }
  });
  const debouncedGenerationStyleSearch = window.NeoGenerationPerf?.debounce ? window.NeoGenerationPerf.debounce(() => {
    generationStyleSearchQuery = $('generation-style-search')?.value || '';
    populateGenerationStyleSelect(true);
  }, 160) : (() => { generationStyleSearchQuery = $('generation-style-search')?.value || ''; populateGenerationStyleSelect(true); });
  $('generation-style-search')?.addEventListener('input', debouncedGenerationStyleSearch);
  $('generation-style-enabled')?.addEventListener('change', () => { refreshGenerationSectionStateBadges(); scheduleGenerationDraftSave(); });
  $('generation-style-pass-target')?.addEventListener('change', () => { renderGenerationActiveStyles(); scheduleGenerationDraftSave(); });
  $('generation-style-select')?.addEventListener('change', () => {
    const selected = trim($('generation-style-select')?.value || '');
    if (generationStyleEditingName && normalizeGenerationStyleName(selected) !== normalizeGenerationStyleName(generationStyleEditingName)) clearGenerationStyleEditingState();
    syncGenerationStyleEditingUI();
  });
  $('btn-generation-style-apply')?.addEventListener('click', editSelectedGenerationStyle);
  $('btn-generation-style-add-selected')?.addEventListener('click', addSelectedGenerationStyle);
  $('btn-generation-style-save')?.addEventListener('click', () => saveGenerationStyle(false));
  $('btn-generation-style-update')?.addEventListener('click', () => saveGenerationStyle(true));
  $('btn-generation-style-duplicate')?.addEventListener('click', duplicateGenerationStyle);
  $('btn-generation-style-delete')?.addEventListener('click', deleteGenerationStyle);
  $('btn-generation-style-import')?.addEventListener('click', () => $('generation-style-import-file')?.click());
  $('btn-generation-style-export')?.addEventListener('click', exportGenerationStylePack);
  $('generation-style-import-file')?.addEventListener('change', e => { const file = e.target?.files?.[0]; importGenerationStylePack(file); e.target.value = ''; });
  $('btn-generation-detailer-refresh')?.addEventListener('click', () => loadGenerationDetailerModels(true));
  $('btn-generation-detailer-download-sam')?.addEventListener('click', () => { downloadGenerationDetailerSamPreset(); });
  $('btn-generation-detailer-add-pass')?.addEventListener('click', () => addGenerationDetailerRow({}));
  $('btn-generation-detailer-editor-open')?.addEventListener('click', () => { if (!generationDetailerScopeUsesManualBoxes('primary')) return; setGenerationDetailerEditorScope('primary'); openGenerationDetailerEditor().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not open the visual box drawer.', 'error')); });
  $('btn-generation-detailer-editor-load-source')?.addEventListener('click', () => { openGenerationDetailerEditorFromSource().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not load the source image into the box drawer.', 'error')); });
  $('btn-generation-detailer-editor-load-preview')?.addEventListener('click', () => { openGenerationDetailerEditorFromPreview().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not load the current output preview into the box drawer.', 'error')); });
  $('btn-generation-detailer-editor-preview-source')?.addEventListener('click', () => { runGenerationDetailerDetectionPreviewFromSource().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not preview detections from the source image.', 'error')); });
  $('btn-generation-detailer-editor-preview-output')?.addEventListener('click', () => { runGenerationDetailerDetectionPreviewFromPreview().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not preview detections from the current output.', 'error')); });
  $('btn-generation-detailer-preview-active')?.addEventListener('click', () => {
    const hasPreview = !!String(document.getElementById('generation-live-preview')?.getAttribute('src') || '').trim();
    const runner = hasPreview ? runGenerationDetailerDetectionPreviewFromPreview : runGenerationDetailerDetectionPreviewFromSource;
    runner().catch(err => setStatus('generation-detailer-status', err?.message || 'Could not preview detailer targets.', 'error'));
  });
  $('btn-generation-detailer-editor-export')?.addEventListener('click', () => { try { exportGenerationDetailerSnapshot(); } catch (err) { setStatus('generation-detailer-status', err?.message || 'Could not export the detection snapshot.', 'error'); } });
  $('btn-generation-detailer-editor-import')?.addEventListener('click', () => { $('generation-detailer-editor-import-file')?.click(); });
  $('btn-generation-detailer-editor-restore-history')?.addEventListener('click', () => { try { restoreGenerationDetailerHistoryEntry(Number($('generation-detailer-editor-history-select')?.value || 0)); } catch (err) { setStatus('generation-detailer-status', err?.message || 'Could not restore the saved target history.', 'error'); } });
  $('btn-generation-detailer-tuning-lenient')?.addEventListener('click', () => applyGenerationDetailerThresholdTuningPreset('lenient'));
  $('btn-generation-detailer-tuning-balanced')?.addEventListener('click', () => applyGenerationDetailerThresholdTuningPreset('balanced'));
  $('btn-generation-detailer-tuning-strict')?.addEventListener('click', () => applyGenerationDetailerThresholdTuningPreset('strict'));
  $('generation-detailer-editor-import-file')?.addEventListener('change', (event) => { const file = event?.target?.files?.[0] || null; importGenerationDetailerSnapshot(file).catch(err => setStatus('generation-detailer-status', err?.message || 'Could not import the detection snapshot.', 'error')).finally(() => { try { event.target.value = ''; } catch (_) {} }); });
  $('btn-generation-detailer-editor-sync-text')?.addEventListener('click', () => { hydrateGenerationDetailerBoxesFromTextarea(); saveGenerationDetailerHistoryEntry('sync_text'); setGenerationDetailerEditorNote('Synced the current manual-box text into the visual target picker.'); });
  $('btn-generation-detailer-editor-clear')?.addEventListener('click', () => { generationDetailerBoxEditorState.boxes = []; generationDetailerBoxEditorState.activeIndex = -1; resetGenerationDetailerPreviewState('manual'); syncGenerationDetailerBoxesToTextarea(); saveGenerationDetailerEditorScopeSnapshot(); saveGenerationDetailerHistoryEntry('clear'); renderGenerationDetailerBoxList(); renderGenerationDetailerEditorCanvas(); setGenerationDetailerEditorNote('Cleared the current visual targets.'); });
  $('btn-generation-detailer-editor-close')?.addEventListener('click', () => showGenerationDetailerEditor(false));
  ['generation-detailer-editor-priority-preset','generation-detailer-editor-auto-suppress-tiny','generation-detailer-editor-confidence-heat','generation-detailer-editor-cluster-merge','generation-detailer-editor-foreground-bias'].forEach(id => $(id)?.addEventListener('change', () => { saveGenerationDetailerEditorScopeSnapshot(); renderGenerationDetailerBoxList(); renderGenerationDetailerEditorCanvas(); }));
  $('generation-detailer-target-mode')?.addEventListener('change', () => { syncGenerationPrimaryDetailerManualUi(); scheduleGenerationDraftSave(); });
  syncGenerationPrimaryDetailerManualUi();
  ['generation-detailer-editor-tiny-main-ratio','generation-detailer-editor-tiny-image-floor'].forEach(id => $(id)?.addEventListener('input', () => { updateGenerationDetailerSuppressionSliderLabels(); saveGenerationDetailerEditorScopeSnapshot(); }));
  updateGenerationDetailerSuppressionSliderLabels();
  $('generation-detailer-manual-boxes')?.addEventListener('change', () => { if (generationDetailerBoxEditorState.scopeType === 'primary' && $('generation-detailer-box-editor')?.style.display !== 'none') hydrateGenerationDetailerBoxesFromTextarea(); });
  bindGenerationDetailerEditorCanvas();
  ['generation-detailer-provider','generation-detailer-mode','generation-detailer-detector-type'].forEach(id => $(id)?.addEventListener('change', () => { populateGenerationDetailerModelSelect(true); scheduleGenerationDraftSave(); renderGenerationFinishFoundation(); }));
  ['generation-detailer-enabled','generation-detailer-model','generation-detailer-sam-model','generation-detailer-use-main-prompt','generation-detailer-force-inpaint','generation-detailer-sam-preset','generation-detailer-order','generation-detailer-reference-lock','generation-detailer-target-mode'].forEach(id => $(id)?.addEventListener('change', () => { renderGenerationFinishFoundation(); scheduleGenerationDraftSave(); }));
  $('generation-detailer-manual-boxes')?.addEventListener('input', () => { renderGenerationFinishFoundation(); scheduleGenerationDraftSave(); });
  ['generation-detailer-custom-classes','generation-detailer-confidence','generation-detailer-topk','generation-detailer-bbox-grow','generation-detailer-mask-blur','generation-detailer-denoise','generation-detailer-steps','generation-detailer-positive','generation-detailer-negative','generation-detailer-start-index','generation-detailer-count','generation-detailer-min-area','generation-detailer-max-area'].forEach(id => $(id)?.addEventListener('input', () => { renderGenerationFinishFoundation(); scheduleGenerationDraftSave(); }));
  ['generation-detailer-custom-detector-root','generation-detailer-custom-sam-root'].forEach(id => $(id)?.addEventListener('change', () => { loadGenerationDetailerModels(true).catch(() => {}); scheduleGenerationDraftSave(); }));
  $('generation-wildcard-enabled')?.addEventListener('change', () => { refreshGenerationSectionStateBadges(); scheduleGenerationDraftSave(); });
  $('btn-generation-wildcard-refresh')?.addEventListener('click', () => loadGenerationWildcardCatalog(true));
  $('generation-wildcard-file')?.addEventListener('change', () => { previewSelectedGenerationWildcardFile().catch(() => {}); scheduleGenerationDraftSave(); });
  $('btn-generation-wildcard-insert')?.addEventListener('click', insertSelectedGenerationWildcardToken);
  $('btn-generation-wildcard-preview')?.addEventListener('click', () => previewGenerationWildcardResolution().catch(() => {}));
  $('btn-generation-wildcard-apply-first')?.addEventListener('click', applyFirstGenerationWildcardResult);
  $('btn-generation-wildcard-queue-variants')?.addEventListener('click', () => queueGenerationWildcardVariants().catch(err => setStatus('generation-wildcard-status', err?.message || 'Could not queue wildcard variants.', 'error')));
  const debouncedGenerationWildcardRootRefresh = window.NeoGenerationPerf?.debounce ? window.NeoGenerationPerf.debounce(() => { generationWildcardValueCache.clear(); loadGenerationWildcardCatalog(false).catch(() => {}); }, 180) : (() => { generationWildcardValueCache.clear(); loadGenerationWildcardCatalog(false).catch(() => {}); });
  $('generation-wildcard-root')?.addEventListener('change', () => { debouncedGenerationWildcardRootRefresh(); scheduleGenerationDraftSave(); });
  $('generation-wildcard-target')?.addEventListener('change', scheduleGenerationDraftSave);
  $('generation-wildcard-auto-resolve')?.addEventListener('change', scheduleGenerationDraftSave);
  $('generation-wildcard-use-seed')?.addEventListener('change', scheduleGenerationDraftSave);
  $('generation-wildcard-preview-count')?.addEventListener('input', scheduleGenerationDraftSave);
  $('generation-wildcard-queue-count')?.addEventListener('input', scheduleGenerationDraftSave);
  $('generation-source-resize-mode')?.addEventListener('change', scheduleGenerationDraftSave);
  ['generation-identity-goal','generation-identity-route'].forEach(id => $(id)?.addEventListener('change', () => { syncGenerationIdentityUI(); scheduleGenerationDraftSave(); }));
  ['generation-identity-strength','generation-identity-faceid-lora','generation-identity-start','generation-identity-end','generation-identity-notes'].forEach(id => $(id)?.addEventListener('input', () => { syncGenerationIdentityUI(); scheduleGenerationDraftSave(); }));
  $('btn-generation-identity-prep')?.addEventListener('click', () => { prepareGenerationIdentityWorkflow().catch(err => setStatus('generation-status', err?.message || 'Could not prepare the IP-Adapter identity preset lane.', 'error')); });
  $('btn-generation-identity-use-source')?.addEventListener('click', () => { useGenerationSourceAsIdentityReference().catch(err => setStatus('generation-status', err?.message || 'Could not copy the source image into IP-Adapter.', 'error')); });
  $('generation-inpaint-target')?.addEventListener('change', scheduleGenerationDraftSave);
  $('generation-inpaint-context')?.addEventListener('change', scheduleGenerationDraftSave);
  $('generation-grow-mask-by')?.addEventListener('input', scheduleGenerationDraftSave);
  $('generation-mask-feather')?.addEventListener('input', scheduleGenerationDraftSave);
  ['generation-outpaint-left','generation-outpaint-top','generation-outpaint-right','generation-outpaint-bottom'].forEach(id => $(id)?.addEventListener('input', () => { if (!generationOutpaintPresetApplying && $('generation-outpaint-preset')) $('generation-outpaint-preset').value = 'custom'; renderGenerationOutpaintSummary(); scheduleGenerationDraftSave(); }));
  $('generation-outpaint-feather')?.addEventListener('input', () => { renderGenerationOutpaintSummary(); scheduleGenerationDraftSave(); });
  $('generation-outpaint-preset')?.addEventListener('change', () => { if (($('generation-outpaint-preset')?.value || 'custom') === 'custom') { renderGenerationOutpaintSummary(); scheduleGenerationDraftSave(); } else { applyGenerationOutpaintPreset().catch(() => {}); } });
  $('generation-outpaint-anchor')?.addEventListener('change', () => { if (($('generation-outpaint-preset')?.value || 'custom') === 'custom') { renderGenerationOutpaintSummary(); scheduleGenerationDraftSave(); } else { applyGenerationOutpaintPreset().catch(() => {}); } });
  $('btn-generation-mask-edit')?.addEventListener('click', openGenerationMaskEditor);
  $('btn-generation-source-edit-mask')?.addEventListener('click', openGenerationMaskEditor);
  $('btn-close-generation-mask-editor')?.addEventListener('click', closeGenerationMaskEditor);
  $('generation-mask-editor-modal')?.addEventListener('click', e => { if (e.target?.id === 'generation-mask-editor-modal') closeGenerationMaskEditor(); });
  $('btn-generation-mask-clear-editor')?.addEventListener('click', clearMaskEditor);
  $('btn-generation-mask-invert-editor')?.addEventListener('click', invertMaskEditor);
  $('btn-generation-mask-save-editor')?.addEventListener('click', () => { saveMaskEditorToInput().catch(err => setStatus('generation-status', err?.message || 'Could not save the mask.', 'error')); });
  $('btn-generation-source-clear-mask')?.addEventListener('click', e => { e.preventDefault(); clearGenerationImageInput('generation-mask-image'); setStatus('generation-status', 'Cleared the inpaint mask.', 'success'); scheduleGenerationDraftSave(); });
  $('generation-mask-brush-size')?.addEventListener('input', updateMaskBrushLabel);
  $('btn-generation-mask-fit')?.addEventListener('click', resetMaskEditorZoom);
  $('btn-generation-mask-100')?.addEventListener('click', () => applyMaskEditorZoom(1));
  $('generation-mask-draw-canvas')?.addEventListener('wheel', handleMaskEditorWheel, { passive:false });
  $('generation-mask-draw-canvas')?.addEventListener('dblclick', resetMaskEditorZoom);
  window.addEventListener('keydown', e => { if (e.code === 'Space' && $('generation-mask-editor-modal') && !$('generation-mask-editor-modal').classList.contains('hidden')) { generationMaskEditorState.spaceDown = true; } });
  window.addEventListener('keyup', e => { if (e.code === 'Space') generationMaskEditorState.spaceDown = false; });
  $('generation-mask-draw-canvas')?.addEventListener('contextmenu', e => e.preventDefault());
  $('generation-mask-draw-canvas')?.addEventListener('pointerenter', e => { updateMaskBrushCursor(e); });
  $('generation-mask-draw-canvas')?.addEventListener('pointerdown', e => { e.preventDefault(); startMaskEditorStroke(e); });
  $('generation-mask-draw-canvas')?.addEventListener('pointermove', e => { e.preventDefault(); moveMaskEditorStroke(e); });
  $('generation-mask-draw-canvas')?.addEventListener('pointerup', endMaskEditorStroke);
  $('generation-mask-draw-canvas')?.addEventListener('pointercancel', () => { endMaskEditorStroke(); hideMaskBrushCursor(); });
  $('generation-mask-draw-canvas')?.addEventListener('pointerleave', () => { if (generationMaskEditorState.panning) endMaskEditorStroke(); hideMaskBrushCursor(); });
  bindGenerationImagePanel({ inputId:'generation-source-image', dropzoneId:'generation-source-dropzone', replaceBtnId:'btn-generation-source-replace', clearBtnId:'btn-generation-source-clear', previewId:'generation-source-preview', emptyId:'generation-source-empty', metaId:'generation-source-meta', emptyText:'No source image selected.' });
  bindGenerationImagePanel({ inputId:'generation-mask-image', dropzoneId:'generation-mask-dropzone', replaceBtnId:'btn-generation-mask-replace', clearBtnId:'btn-generation-mask-clear', previewId:'generation-mask-preview', emptyId:'generation-mask-empty', metaId:'generation-mask-meta', emptyText:'No mask image selected.' });
  ['generation-workflow-type','generation-source-image','generation-mask-image','generation-outpaint-left','generation-outpaint-top','generation-outpaint-right','generation-outpaint-bottom'].forEach(id => {
    const eventName = id === 'generation-workflow-type' ? 'change' : 'input';
    $(id)?.addEventListener(eventName, () => window.setTimeout(syncGenerationLaunchAvailability, 0));
    if (id === 'generation-source-image' || id === 'generation-mask-image') {
      $(id)?.addEventListener('change', () => window.setTimeout(syncGenerationLaunchAvailability, 0));
    }
  });
  window.setTimeout(syncGenerationLaunchAvailability, 0);
  updateGenerationSourceMaskOverlay();
  refreshGenerationSourceImageInfo();
  renderGenerationOutpaintSummary();
  syncGenerationIdentityUI();
  populateGenerationSizePresetSelect('builtin:sdxl_square_1024');
  syncGenerationSizePresetSelectionFromInputs();
  updatePrimaryGenerationLoraSummary();
  updatePrimaryGenerationControlnetSummary();
  updateGenerationUnitIndices();
  updateGenerationPreviewActionState();
};
