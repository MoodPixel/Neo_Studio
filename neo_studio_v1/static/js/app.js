document.addEventListener('DOMContentLoaded', () => {
  if (typeof normalizeMainSurfaceShell === 'function') normalizeMainSurfaceShell();
  document.addEventListener('neo-backend-state', updateBackendDependentUI);
  updateBackendDependentUI();
  refreshCategoryList(initialCategories);
  fillCategorySelect('prompt-category', initialCategories, initialLastPromptCategory);
  fillCategorySelect('caption-category', initialCategories, initialLastCaptionCategory);
  fillCategorySelect('batch-category', initialCategories, initialLastCaptionCategory);
  fillCategorySelect('saved-prompt-category', initialPromptCategoryList, initialLastPromptCategory);
  fillCategorySelect('caption-browser-category', ['all', ...initialCategories.filter(x => x !== 'all')], 'all');
  fillCategorySelect('component-browser-category', ['all', ...initialCategories.filter(x => x !== 'all')], 'all');
  fillCategorySelect('caption-editor-category', initialCategories, initialLastCaptionCategory);
  fillCategorySelect('metadata-save-category', initialCategories, initialLastPromptCategory);
  fillSavedPromptEntries(initialPromptEntries || [], '');
  fillSavedCharacterEntries(initialCharacterEntries || [], '');
  populatePresetSelect('prompt-preset', promptPresets, initialLastPromptPreset);
  populatePresetSelect('caption-preset', captionPresets, initialLastCaptionPreset);
  applyPromptPreset($('prompt-preset').value, false);
  applyCaptionPreset($('caption-preset').value, false);
  refreshPromptPresetAux($('prompt-preset').value);
  refreshCaptionPresetAux($('caption-preset').value);
  toggleBatchMode();
  if (typeof syncDatasetPreparationControls === 'function') syncDatasetPreparationControls();
  renderVariationInputs();
  syncPromptOutputVisibility();
  resetBatchDisplay();
  resetTimer('prompt-elapsed');
  resetTimer('caption-elapsed');
  resetTimer('character-elapsed');
  refreshCaptionBrowser();
  refreshComponentBrowser();
  applyCaptionModeDefaults(true);
  refreshRecentItems();
  if (typeof initializeStudioAccordions === 'function') initializeStudioAccordions();
  if (typeof initializeBackendManager === 'function') initializeBackendManager();
  refreshRecentBatchJobs();
  const batchAccordion = document.querySelector('[data-accordion-id="caption-batch-captioning"]');
  if (batchAccordion) batchAccordion.addEventListener('toggle', () => { if (batchAccordion.open) refreshRecentBatchJobs(); });
  if ($('saved-bundle-id') || $('bundle-name')) {
    fillBundleEntries(initialBundleEntries || [], '');
    refreshBundleSupportData();
  }
  document.querySelectorAll('[data-main-tab]').forEach(btn => btn.addEventListener('click', () => {
    const target = btn.dataset.mainTab;
    switchMainTab(target);
  }));
  document.querySelectorAll('#tab-manager [data-manager-subtab]').forEach(btn => btn.addEventListener('click', () => switchManagerSubTab(btn.dataset.managerSubtab)));
  $('btn-node-manager-save-settings')?.addEventListener('click', saveNodeManagerSettingsUI);
  $('btn-node-manager-refresh')?.addEventListener('click', () => fetchNodeManagerState(false));
  $('btn-node-manager-open-root')?.addEventListener('click', () => openNodeManagerFolder(false));
  $('btn-node-manager-reconnect-image')?.addEventListener('click', reconnectNodeManagerImageBackend);
  $('btn-node-manager-install')?.addEventListener('click', installNodeManagerRepo);
  $('node-manager-node-select')?.addEventListener('change', renderNodeManagerSelectedDetails);
  $('btn-node-manager-open-selected')?.addEventListener('click', () => openNodeManagerFolder(true));
  $('btn-node-manager-update-selected')?.addEventListener('click', updateSelectedNodeManagerRepo);
  ['prompt-idea','prompt-output','caption-output','character-content'].forEach(id => $(id).addEventListener('input', () => { updateCounter(id, `${id}-counter`); if (id === 'prompt-output') $('prompt-raw').value = $('prompt-output').value || ''; }));
  window.bindAppGenerationWorkspaceControls?.();
  updateCounter('prompt-idea','prompt-idea-counter');
  updateCounter('prompt-output','prompt-output-counter');
  updateCounter('caption-output','caption-output-counter');
  updateCounter('character-content','character-content-counter');
  refreshGenerationCounters();
  loadGenerationRecentRuns();
  renderGenerationHistoryPanel();
  bindSyncedInputs('generation-steps', 'generation-steps-range');
  bindSyncedInputs('generation-cfg', 'generation-cfg-range');
  bindSyncedInputs('generation-denoise', 'generation-denoise-range');
  bindSyncedInputs('generation-tagassist-threshold', 'generation-tagassist-threshold-range');
  bindSyncedInputs('generation-gguf-guidance', 'generation-gguf-guidance-range');
  bindSyncedInputs('generation-refine-scale', 'generation-refine-scale-range');
  bindSyncedInputs('generation-refine-steps', 'generation-refine-steps-range');
  bindSyncedInputs('generation-refine-denoise', 'generation-refine-denoise-range');
  const safeGenerationBootStep = (label, fn) => {
    try {
      return typeof fn === 'function' ? fn() : undefined;
    } catch (error) {
      console.error(`[Neo Studio] Generation boot step failed: ${label}`, error);
      if (typeof setStatus === 'function') {
        setStatus('generation-status', `Generation setup warning: ${label} failed. Check console for details.`, 'warn');
      }
      return undefined;
    }
  };
  safeGenerationBootStep('refine UI sync', () => syncGenerationRefineUI());
  safeGenerationBootStep('image upscale UI sync', () => syncGenerationImageUpscaleUI());
  safeGenerationBootStep('SUPIR UI sync', () => syncGenerationSupirUI());
  safeGenerationBootStep('GGUF UI sync', () => syncGenerationGGUFUI());
  safeGenerationBootStep('generation family router init', () => { if (window.NeoGenerationFamilyRouter?.init) window.NeoGenerationFamilyRouter.init(); });
  safeGenerationBootStep('generation mode UI sync', () => syncGenerationModeUI());
  safeGenerationBootStep('generation progress reset', () => resetGenerationProgress('Idle'));
  safeGenerationBootStep('generation dynamic options', () => refreshGenerationDynamicOptions());
  safeGenerationBootStep('image upscale starter preset apply', () => { if (($('generation-image-upscale-profile')?.value || 'preserve_2x') !== 'custom') applyGenerationImageUpscaleProfile($('generation-image-upscale-profile')?.value || 'preserve_2x', { silent:true }); });
  safeGenerationBootStep('runtime profile render', () => renderGenerationRuntimeProfileAndCapabilities());
  safeGenerationBootStep('prompt conditioning render', () => renderGenerationPromptConditioning());
  safeGenerationBootStep('experimental mode render', () => renderGenerationExperimentalMode());
  safeGenerationBootStep('image preflight render', () => renderGenerationImagePreflight());
  safeGenerationBootStep('workspace preset select render', () => renderGenerationShellSnapshotSelect());
  safeGenerationBootStep('default workspace preset autoload', () => autoLoadDefaultGenerationShellSnapshot({ silent:true }));
  safeGenerationBootStep('generation state hydrate', () => fetchGenerationState(true));
  safeGenerationBootStep('generation catalog hydrate', () => {
    if (typeof getRoleSession === 'function' && getRoleSession('image')?.connected && typeof refreshGenerationCatalog === 'function') {
      return refreshGenerationCatalog(true).catch(error => {
        console.error('[Neo Studio] Generation catalog hydrate failed', error);
        if (typeof setStatus === 'function') setStatus('generation-status', error?.message || 'Could not load generation catalog.', 'warn');
      });
    }
    return undefined;
  });
  if ($('generation-lora-library-dir') && !$('generation-lora-library-dir').value && $('neo-library-vault-lora-dir')?.value) $('generation-lora-library-dir').value = $('neo-library-vault-lora-dir').value;
  refreshGenerationLoraLibraryBrowser({ keepSelection:true }).catch(() => {});
  Promise.all([loadGenerationOutputSettings(), loadGenerationStyles()]).finally(() => {
    if (window.NeoGenerationPerf?.lazyInitAccordion) {
      window.NeoGenerationPerf.lazyInitAccordion('generation-wildcards', () => loadGenerationWildcardCatalog(true).catch(() => {}));
      window.NeoGenerationPerf.lazyInitAccordion('generation-detailer-settings', () => loadGenerationDetailerModels(true).catch(() => {}));
      window.NeoGenerationPerf.lazyInitAccordion('generation-ti-settings', () => refreshGenerationTiLibraryBrowser({ keepSelection:true }).catch(() => {}));
    }
    refreshGenerationSectionStateBadges();
    scheduleGenerationSectionBadgeRefresh([0, 180, 420, 900]);
    syncGenerationActionZoneFromShell();
    });
  document.addEventListener('neo-generation-layout-mounted', () => scheduleGenerationSectionBadgeRefresh([120, 320, 720]));
  document.addEventListener('neo-generation-contracts-mounted', () => scheduleGenerationSectionBadgeRefresh([80, 260]));
  window.addEventListener('load', () => scheduleGenerationSectionBadgeRefresh([120, 480]));
  $('prompt-preset').addEventListener('change', e => applyPromptPreset(e.target.value));
  $('caption-preset').addEventListener('change', e => applyCaptionPreset(e.target.value));
  $('prompt-preset-recent').addEventListener('change', e => { if (e.target.value) { $('prompt-preset').value = e.target.value; applyPromptPreset(e.target.value); } });
  $('caption-preset-recent').addEventListener('change', e => { if (e.target.value) { $('caption-preset').value = e.target.value; applyCaptionPreset(e.target.value); } });
  $('saved-prompt-category').addEventListener('change', refreshSavedPromptNames);
  $('batch-mode').addEventListener('change', () => { toggleBatchMode(); refreshRecentBatchJobs(); });
  ['batch-dataset-caption-images','batch-dataset-save-txt','batch-dataset-rename-images'].forEach(id => $(id)?.addEventListener('change', () => syncDatasetPreparationControls()));
  ['batch-dataset-prefix','batch-dataset-pattern','batch-number-start','batch-dataset-number-padding'].forEach(id => $(id)?.addEventListener('input', () => updateDatasetPreparationPreview()));
  $('prompt-enable-variations').addEventListener('change', renderVariationInputs);
  $('prompt-variation-count').addEventListener('input', renderVariationInputs);
  $('saved-character-name').addEventListener('change', loadSavedCharacter);
  $('global-search-query').addEventListener('keydown', e => { if (e.key === 'Enter') runGlobalSearch(); });
  ['caption-browser-query','caption-browser-model','caption-browser-style'].forEach(id => $(id).addEventListener('input', () => scheduleCaptionBrowserRefresh(true)));
  ['caption-browser-date-from','caption-browser-date-to'].forEach(id => $(id).addEventListener('change', () => refreshCaptionBrowser({ resetPage:true })));
  $('caption-browser-category').addEventListener('change', () => refreshCaptionBrowser({ resetPage:true }));
  $('caption-browser-component').addEventListener('change', () => refreshCaptionBrowser({ resetPage:true }));
  $('caption-browser-sort').addEventListener('change', () => refreshCaptionBrowser({ resetPage:true }));
  $('caption-browser-page-size').addEventListener('change', () => refreshCaptionBrowser({ resetPage:true }));
  ['component-browser-query','component-browser-type'].forEach(id => $(id).addEventListener('change', refreshComponentBrowser));
  $('component-browser-category').addEventListener('change', refreshComponentBrowser);
  $('caption-mode').addEventListener('change', () => applyCaptionModeDefaults());
  if ($('caption-detail-level')) $('caption-detail-level').addEventListener('change', () => refreshCaptionGuidance());
  $('caption-component-type').addEventListener('change', () => { captionAutoComponentValue = $('caption-component-type').value || ''; $('caption-save-component-type').value = $('caption-component-type').value || ''; });
  $('caption-save-component-type').addEventListener('change', () => { captionAutoComponentValue = $('caption-save-component-type').value || captionAutoComponentValue; });
  $('caption-image').addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    setCaptionPreviewFile(file);
  });
  $('caption-preview-wrap').addEventListener('mousedown', startCaptionCropDrag);
  window.addEventListener('mousemove', moveCaptionCropDrag);
  window.addEventListener('mouseup', endCaptionCropDrag);
  window.addEventListener('resize', updateCaptionCropOverlay);
  applyCaptionModeDefaults();
  if (typeof refreshCaptionGuidance === 'function') refreshCaptionGuidance();
  $('btn-generate-prompt').addEventListener('click', generatePrompt);
  $('btn-generation-pull-from-prompt')?.addEventListener('click', pullPromptStudioIntoGeneration);
  $('btn-generation-manage-backend')?.addEventListener('click', () => { if (typeof openBackendManager === 'function') openBackendManager('image'); });
  $('btn-generation-note-manage-backend')?.addEventListener('click', () => { if (typeof openBackendManager === 'function') openBackendManager('image'); });
  $('btn-generation-save-snapshot')?.addEventListener('click', () => saveCurrentGenerationShellSnapshot({ updateSelected:false }));
  $('generation-shell-snapshot-select')?.addEventListener('change', syncGenerationShellSnapshotActions);
  $('btn-generation-set-default-snapshot')?.addEventListener('click', setSelectedGenerationShellSnapshotAsDefault);
  $('btn-generation-clear-default-snapshot')?.addEventListener('click', clearDefaultGenerationShellSnapshot);
  $('btn-generation-load-snapshot')?.addEventListener('click', loadSelectedGenerationShellSnapshot);
  $('btn-generation-update-snapshot')?.addEventListener('click', () => saveCurrentGenerationShellSnapshot({ updateSelected:true }));
  $('btn-generation-rename-snapshot')?.addEventListener('click', renameSelectedGenerationShellSnapshot);
  $('btn-generation-duplicate-snapshot')?.addEventListener('click', duplicateSelectedGenerationShellSnapshot);
  $('btn-generation-export-snapshot')?.addEventListener('click', exportSelectedGenerationShellSnapshot);
  $('btn-generation-import-snapshot')?.addEventListener('click', triggerGenerationShellSnapshotImport);
  $('generation-shell-snapshot-import-file')?.addEventListener('change', handleGenerationShellSnapshotImportSelection);
  $('btn-generation-delete-snapshot')?.addEventListener('click', deleteSelectedGenerationShellSnapshot);
  $('btn-generation-pull-recovered')?.addEventListener('click', pullRecoveredMetadataIntoGeneration);
  $('btn-generation-clear-prompts')?.addEventListener('click', clearGenerationPrompts);
  $('btn-generation-copy-payload')?.addEventListener('click', copyGenerationPayload);
  $('btn-generation-refresh-status')?.addEventListener('click', refreshGenerationBackendState);
  $('btn-generation-history-rerun-last')?.addEventListener('click', () => { runGenerationHistoryEntry(generationRecentRuns[0] || null, { watch:true }).catch(err => announceGenerationStatus(err?.message || 'Could not rerun the last payload.', 'error')); });
  $('btn-generation-history-queue-last')?.addEventListener('click', () => { runGenerationHistoryEntry(generationRecentRuns[0] || null, { watch:false }).catch(err => announceGenerationStatus(err?.message || 'Could not queue the last payload.', 'error')); });
  $('btn-generation-history-restore')?.addEventListener('click', () => restoreGenerationHistoryEntry(getSelectedGenerationHistoryEntry()));
  $('btn-generation-pause')?.addEventListener('click', pauseGenerationQueue);
  $('btn-generation-cancel')?.addEventListener('click', cancelGenerationJob);
  const generationApp = window.NeoStudioApp?.generation || null;
  generationApp?.register('actions', {
    runShell: runGenerationShell,
    queueShell: queueGenerationShell,
    queueWildcardVariants: queueGenerationWildcardVariants,
    applyDraft: applyGenerationDraft,
    runTagAssist: runGenerationTagAssist,
    activateOutput: activateGenerationOutput,
  });
  generationApp?.register('workflow', {
    addLoraRow: addGenerationLoraRow,
    addControlnetRow: addGenerationControlnetRow,
    addIpAdapterRow: addGenerationIpAdapterRow,
    refreshLoraApplyTargets: (typeof refreshGenerationLoraApplyTargets === 'function') ? refreshGenerationLoraApplyTargets : (() => {}),
  });
  generationApp?.register('handlers', {
    runClick: handleGenerationRunClick,
    pauseClick: e => { if (e) { e.preventDefault?.(); e.stopPropagation?.(); } return pauseGenerationQueue(); },
    cancelClick: e => { if (e) { e.preventDefault?.(); e.stopPropagation?.(); } return cancelGenerationJob(); },
    queueClick: handleGenerationQueueClick,
    resetShellClick: handleGenerationResetShellClick,
  });
  generationApp?.register('preview', {
    sendToMode: sendGenerationPreviewToMode,
    runHiresFix: runGenerationPreviewHiresFix,
    runDetailerPass: runGenerationPreviewDetailerPass,
    runIdentityRescuePass: runGenerationPreviewIdentityRescuePass,
  });
  generationApp?.register('queue', {
    pause: pauseGenerationQueue,
    cancel: cancelGenerationJob,
  });
  generationApp?.installLegacyAliases({
    runGenerationShell: generationApp?.actions?.runShell || runGenerationShell,
    queueGenerationShell: generationApp?.actions?.queueShell || queueGenerationShell,
    queueGenerationWildcardVariants: generationApp?.actions?.queueWildcardVariants || queueGenerationWildcardVariants,
    addGenerationLoraRow: generationApp?.workflow?.addLoraRow || addGenerationLoraRow,
    addGenerationControlnetRow: generationApp?.workflow?.addControlnetRow || addGenerationControlnetRow,
    addGenerationIpAdapterRow: generationApp?.workflow?.addIpAdapterRow || addGenerationIpAdapterRow,
    refreshGenerationLoraApplyTargets: generationApp?.workflow?.refreshLoraApplyTargets || ((typeof refreshGenerationLoraApplyTargets === 'function') ? refreshGenerationLoraApplyTargets : (() => {})),
    handleGenerationRunClick: generationApp?.handlers?.runClick || handleGenerationRunClick,
    handleGenerationPauseClick: generationApp?.handlers?.pauseClick || (e => { if (e) { e.preventDefault?.(); e.stopPropagation?.(); } return pauseGenerationQueue(); }),
    handleGenerationCancelClick: generationApp?.handlers?.cancelClick || (e => { if (e) { e.preventDefault?.(); e.stopPropagation?.(); } return cancelGenerationJob(); }),
    handleGenerationQueueClick: generationApp?.handlers?.queueClick || handleGenerationQueueClick,
    handleGenerationResetShellClick: generationApp?.handlers?.resetShellClick || handleGenerationResetShellClick,
    applyGenerationDraft: generationApp?.actions?.applyDraft || applyGenerationDraft,
    runGenerationTagAssist: generationApp?.actions?.runTagAssist || runGenerationTagAssist,
    sendGenerationPreviewToMode: generationApp?.preview?.sendToMode || sendGenerationPreviewToMode,
    runGenerationPreviewHiresFix: generationApp?.preview?.runHiresFix || runGenerationPreviewHiresFix,
    runGenerationPreviewDetailerPass: generationApp?.preview?.runDetailerPass || runGenerationPreviewDetailerPass,
    runGenerationPreviewIdentityRescuePass: generationApp?.preview?.runIdentityRescuePass || runGenerationPreviewIdentityRescuePass,
    activateGenerationOutput: generationApp?.actions?.activateOutput || activateGenerationOutput,
    pauseGenerationQueue: generationApp?.queue?.pause || pauseGenerationQueue,
    cancelGenerationJob: generationApp?.queue?.cancel || cancelGenerationJob,
  });
  renderGenerationFinishFoundation();
  generationApp?.setRuntime({
    getCatalogState: () => generationCatalogState,
    getDetailerCatalog: () => generationDetailerModelCatalog,
    getSystemStats: () => generationSystemStats,
    getDependencyAuditState: () => generationDependencyAuditState,
    getImageSession: () => getRoleSession('image'),
    getLatestJob: () => generationLatestJobSnapshot,
    getSelectedOutput: () => (typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : generationSelectedOutputSnapshot),
    getActiveOutput: () => (typeof getGenerationActiveOutputSnapshot === 'function' ? getGenerationActiveOutputSnapshot() : generationSelectedOutputSnapshot),
    getCurrentDraft: () => collectGenerationDraft(),
    applyDraft: draft => applyGenerationDraft(draft),
    activateOutput: (item, options={}) => activateGenerationOutput(item, options),
    sendPreviewToMode: mode => sendGenerationPreviewToMode(mode),
    runPreviewHiresFix: () => runGenerationPreviewHiresFix(),
    runPreviewDetailerPass: () => runGenerationPreviewDetailerPass(),
    runPreviewIdentityRescuePass: () => runGenerationPreviewIdentityRescuePass(),
    refreshCatalog: force => refreshGenerationCatalog(!!force),
    refreshDetailerModels: keepValue => loadGenerationDetailerModels(keepValue !== false),
    refreshState: silent => fetchGenerationState(!!silent),
    refreshDependencyAudit: options => fetchGenerationDependencyAudit(options || {}),
  });
  $('btn-cancel-prompt-run').addEventListener('click', () => { if (promptAbortController) promptAbortController.abort(); });
  $('btn-continue-prompt').addEventListener('click', continuePrompt);
  $('btn-save-prompt-preset').addEventListener('click', () => savePromptPreset(false));
  $('btn-update-prompt-preset').addEventListener('click', () => savePromptPreset(true));
  $('btn-delete-prompt-preset').addEventListener('click', deletePromptPreset);
  $('btn-toggle-prompt-preset-favorite').addEventListener('click', togglePromptPresetFavorite);
  $('btn-duplicate-prompt-preset').addEventListener('click', duplicatePromptPreset);
  $('btn-compare-prompt-preset').addEventListener('click', comparePromptPresets);
  $('btn-export-prompt-preset').addEventListener('click', exportSinglePromptPreset);
  $('btn-save-prompt').addEventListener('click', savePromptEntry);
  // Legacy prompt-bundle controls were removed from the active shell.
  // Keep the prompt bundle helpers available for compatibility paths, but do not
  // bind removed DOM controls from the main app runtime.
  $('btn-load-prompt').addEventListener('click', loadSavedPrompt);
  $('btn-update-loaded').addEventListener('click', updateLoadedPrompt);
  $('btn-delete-loaded').addEventListener('click', deleteLoadedPrompt);
  $('btn-improve-loaded').addEventListener('click', improveLoadedPrompt);
  $('btn-copy-prompt').addEventListener('click', () => copyText('prompt-output', 'prompt-run-status'));
  $('btn-analyze-prompt').addEventListener('click', () => runPromptQA('manual'));
  $('prompt-output').addEventListener('input', () => { updateCounter('prompt-output','prompt-output-counter'); schedulePromptQAAuto(); });
  $('prompt-qa-auto').addEventListener('change', () => { if ($('prompt-qa-auto').checked) schedulePromptQAAuto(); else setStatus('prompt-qa-status', 'Auto-run disabled.'); });
  $('btn-clear-prompt').addEventListener('click', () => { promptSingleOutputForcedVisible = false; $('prompt-idea').value=''; $('prompt-output').value=''; $('prompt-raw').value=''; renderVariationResults([]); syncPromptOutputVisibility(); updateCounter('prompt-idea','prompt-idea-counter'); updateCounter('prompt-output','prompt-output-counter'); $('prompt-qa-summary').textContent = 'Run Prompt QA to catch messy structure before you save or send the prompt.'; $('prompt-qa-stats').innerHTML=''; $('prompt-qa-list').innerHTML=''; setStatus('prompt-qa-status',''); });
  $('prompt-variation-results').addEventListener('click', async (e) => {
    const loadBtn = e.target.closest('[data-variation-load]');
    const copyBtn = e.target.closest('[data-variation-copy]');
    if (loadBtn) {
      const item = variationResultsState[Number(loadBtn.dataset.variationLoad || -1)];
      if (!item) return;
      $('prompt-output').value = item.prompt || '';
      $('prompt-raw').value = item.prompt || '';
      currentPromptFinishReason = item.finish_reason || '';
      $('prompt-finish-reason').textContent = `finish: ${currentPromptFinishReason || 'stop'}`;
      promptSingleOutputForcedVisible = true;
      syncPromptOutputVisibility();
      updateCounter('prompt-output', 'prompt-output-counter');
      maybeRunPromptQA('auto');
      setStatus('prompt-run-status', 'Selected variation moved into final output.');
    }
    if (copyBtn) {
      const item = variationResultsState[Number(copyBtn.dataset.variationCopy || -1)];
      if (!item) return;
      try { await navigator.clipboard.writeText(item.prompt || ''); setStatus('prompt-run-status', 'Variation copied to clipboard.'); } catch (_) { setStatus('prompt-run-status', 'Copy failed.', 'error'); }
    }
  });
  $('btn-dedupe-tags').addEventListener('click', () => {
    $('prompt-output').value = uniqueTags($('prompt-output').value || '');
    updateCounter('prompt-output','prompt-output-counter');
    maybeRunPromptQA('auto');
    setStatus('prompt-qa-status', 'Duplicate tags removed.');
  });
  $('btn-sort-tags').addEventListener('click', () => runImprove('Sort tags by importance'));
  $('btn-shorten-prompt').addEventListener('click', () => runImprove('Tighten / shorten'));
  $('btn-expand-prompt').addEventListener('click', () => runImprove('Expand details'));
  $('btn-fix-contradictions').addEventListener('click', () => runImprove('Fix contradictions'));
  $('btn-convert-style').addEventListener('click', () => {
    const src = $('prompt-output').value || '';
    const mode = (src.includes(',') && src.split(',').length >= 4) ? 'Convert to descriptive prose' : 'Convert to SD tags';
    runImprove(mode);
  });
  $('btn-caption-image').addEventListener('click', () => captionImage(false));
  $('btn-caption-selected-area').addEventListener('click', () => captionImage(true));
  $('btn-reset-caption-crop').addEventListener('click', resetCaptionCrop);
  $('btn-use-auto-caption-crop').addEventListener('click', useAutoCaptionCrop);
  $('btn-load-character').addEventListener('click', loadSavedCharacter);
  $('btn-save-character').addEventListener('click', saveCharacter);
  $('btn-delete-character').addEventListener('click', deleteCharacter);
  $('btn-improve-character').addEventListener('click', improveCharacter);
  $('btn-character-to-idea').addEventListener('click', () => { $('prompt-idea').value = $('character-content').value || ''; updateCounter('prompt-idea','prompt-idea-counter'); setStatus('character-status', 'Character copied into prompt idea.'); });
  $('btn-save-caption-preset').addEventListener('click', () => saveCaptionPreset(false));
  $('btn-update-caption-preset').addEventListener('click', () => saveCaptionPreset(true));
  $('btn-delete-caption-preset').addEventListener('click', deleteCaptionPreset);
  $('btn-toggle-caption-preset-favorite').addEventListener('click', toggleCaptionPresetFavorite);
  $('btn-duplicate-caption-preset').addEventListener('click', duplicateCaptionPreset);
  $('btn-compare-caption-preset').addEventListener('click', compareCaptionPresets);
  $('btn-export-caption-preset').addEventListener('click', exportSingleCaptionPreset);
  $('btn-save-caption').addEventListener('click', saveCaptionEntry);
  $('btn-copy-caption').addEventListener('click', () => copyText('caption-output', 'caption-run-status'));
  $('btn-clear-caption').addEventListener('click', () => { $('caption-output').value=''; $('caption-notes').value=''; updateCounter('caption-output','caption-output-counter'); setWarning('caption-warning',''); setStatus('caption-run-status',''); });
  $('btn-refresh-caption-browser').addEventListener('click', () => refreshCaptionBrowser({ resetPage:false }));
  $('btn-refresh-components').addEventListener('click', refreshComponentBrowser);
  $('btn-clear-components').addEventListener('click', () => { $('component-browser-query').value=''; $('component-browser-type').value=''; fillCategorySelect('component-browser-category', ['all', ...initialCategories.filter(x => x !== 'all')], 'all'); refreshComponentBrowser(); });
  $('btn-build-component-draft').addEventListener('click', buildComponentDraftFromSelection);
  $('btn-send-component-draft').addEventListener('click', sendComponentDraftToPromptStudio);
  $('btn-clear-component-selection').addEventListener('click', clearComponentSelection);
  $('btn-clear-caption-browser').addEventListener('click', () => {
    $('caption-browser-query').value = '';
    $('caption-browser-model').value = '';
    $('caption-browser-style').value = '';
    $('caption-browser-date-from').value = '';
    $('caption-browser-date-to').value = '';
    $('caption-browser-component').value = '';
    if (typeof resetCaptionBrowserControls === 'function') resetCaptionBrowserControls();
    fillCategorySelect('caption-browser-category', ['all', ...initialCategories.filter(x => x !== 'all')], 'all');
    refreshCaptionBrowser({ resetPage:true });
  });
  $('btn-caption-browser-prev').addEventListener('click', () => changeCaptionBrowserPage(-1));
  $('btn-caption-browser-next').addEventListener('click', () => changeCaptionBrowserPage(1));
  $('caption-browser-grid').addEventListener('click', async (e) => {
    const editBtn = e.target.closest('[data-caption-edit]');
    const previewBtn = e.target.closest('[data-caption-preview]');
    const sendBtn = e.target.closest('[data-caption-send]');
    if (editBtn) await loadCaptionRecord(editBtn.dataset.captionEdit);
    if (previewBtn) openLightbox(previewBtn.dataset.captionPreview);
    if (sendBtn) { await loadCaptionRecord(sendBtn.dataset.captionSend); sendCaptionEditorToPrompt(); }
  });
  $('component-browser-list').addEventListener('change', e => {
    const box = e.target.closest('[data-component-id]');
    if (!box) return;
    const id = box.getAttribute('data-component-id');
    if (box.checked) captionSelectedComponentIds.add(id); else captionSelectedComponentIds.delete(id);
  });
  $('btn-preview-caption-image').addEventListener('click', () => openLightbox($('caption-editor-image-url').value || ''));
  $('btn-send-caption-to-prompt').addEventListener('click', sendCaptionEditorToPrompt);
  $('btn-caption-to-prompt').addEventListener('click', captionEditorToPromptRecord);
  $('btn-update-caption-record').addEventListener('click', updateCaptionRecord);
  $('btn-delete-caption-record').addEventListener('click', deleteCaptionRecord);
  $('btn-run-global-search').addEventListener('click', runGlobalSearch);
  $('btn-clear-global-search').addEventListener('click', clearGlobalSearchResults);
  $('global-search-results').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-search-open]');
    if (!btn) return;
    await openSearchResult(btn.dataset.searchOpen, btn.dataset.searchId, btn.dataset.searchName);
  });
  $('recent-items-grid').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-recent-open]');
    if (!btn) return;
    const [kind, id] = recentKindToSearchKind(btn.dataset.recentOpen, btn.dataset.recentName || '');
    if (!kind) return;
    await openSearchResult(kind, id || btn.dataset.recentId || '', btn.dataset.recentName || '');
  });
  $('btn-refresh-recent-items').addEventListener('click', refreshRecentItems);
  $('btn-batch-preview').addEventListener('click', previewBatch);
  $('btn-run-batch').addEventListener('click', runBatchCaption);
  $('btn-batch-cancel').addEventListener('click', cancelBatchCaption);
  $('btn-batch-resume').addEventListener('click', resumeBatchCaption);
  $('btn-batch-retry').addEventListener('click', retryFailedBatchCaption);
  $('btn-batch-export-log').addEventListener('click', exportBatchLog);
  $('btn-batch-cancel-post-action').addEventListener('click', cancelBatchPostAction);
  if ($('btn-interrupted-batch-resume')) $('btn-interrupted-batch-resume').addEventListener('click', () => handleInterruptedBatchAction('resume'));
  if ($('btn-interrupted-batch-start-fresh')) $('btn-interrupted-batch-start-fresh').addEventListener('click', () => handleInterruptedBatchAction('start_fresh'));
  if ($('btn-interrupted-batch-open-log')) $('btn-interrupted-batch-open-log').addEventListener('click', () => handleInterruptedBatchAction('open_log'));
  if ($('btn-interrupted-batch-cancel')) $('btn-interrupted-batch-cancel').addEventListener('click', () => handleInterruptedBatchAction('cancel'));
  $('batch-session-select').addEventListener('change', async e => {
    if (!e.target.value) return;
    currentBatchJobId = e.target.value;
    await pollBatchStatus();
  });
  $('btn-batch-input-folder').addEventListener('click', () => browseForFolder('batch-folder'));
  $('btn-batch-output-folder').addEventListener('click', () => browseForFolder('batch-output-folder'));
  $('btn-save-settings').addEventListener('click', saveSettings);
  if (typeof populateLibraryExportCategories === 'function') populateLibraryExportCategories(initialCategories);
  $('btn-close-lightbox').addEventListener('click', closeLightbox);
  $('image-lightbox').addEventListener('click', e => { if (e.target.id === 'image-lightbox') closeLightbox(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
});
