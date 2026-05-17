window.NeoGenerationDraftState = window.NeoGenerationDraftState || {};

// Phase 10.3: sanitize saved/restored generation drafts so retired sections cannot
// revive removed UI/backend paths from old localStorage/server draft data.
function sanitizeGenerationDraftState(draft) {
  if (!draft || typeof draft !== 'object') return draft;
  const removedPrefixes = [
    'regional_',
    'regionalPrompt',
    'expression_',
    'expression_editor_',
    'expressionEditor',
    'reference_match_',
    'referenceMatch',
    'cleanup_prep_',
    'cleanupPrep',
  ];
  const removedExactKeys = new Set([
    'regionalBackendCapabilities',
    'regional_prompt_regions',
    'regional_backend_capabilities',
    'expression_editor_pass',
    'expression_editor_enabled',
    'expression_pass',
    'expression_enabled',
    'reference_match_enabled',
    'cleanup_prep_enabled',
  ]);
  const cleanValue = (value) => {
    if (Array.isArray(value)) return value.map(cleanValue).filter(item => item !== undefined);
    if (!value || typeof value !== 'object') return value;
    const out = {};
    Object.keys(value).forEach(key => {
      const normalized = String(key || '');
      if (removedExactKeys.has(normalized) || removedPrefixes.some(prefix => normalized.startsWith(prefix))) return;
      out[key] = cleanValue(value[key]);
    });
    return out;
  };
  const cleaned = cleanValue(draft) || {};
  cleaned.version = Math.max(Number(cleaned.version || 0) || 0, 7);
  cleaned._neo_draft_sanitized = true;
  cleaned._neo_draft_sanitizer_version = 'phase10.3';
  return cleaned;
}
window.sanitizeGenerationDraftState = sanitizeGenerationDraftState;


function getGenerationPromptMergeLockForDraftApply() {
  const lock = window.__neoGenerationPromptMergeLock || null;
  if (!lock || !lock.positive || !lock.expiresAt || Date.now() > Number(lock.expiresAt || 0)) return null;
  return lock;
}

function mergeGenerationPromptForDraftApply(base, incoming) {
  const current = String(base || '').trim();
  const prompt = String(incoming || '').trim();
  if (!prompt) return current;
  if (!current) return prompt;
  if (current.toLowerCase().includes(prompt.toLowerCase())) return current;
  return `${current}, ${prompt}`;
}

const NEO_RES4LYF_SAFE_SAMPLERS = new Set(['res_2m', 'res_3s', 'res_5s']);
const NEO_RES4LYF_SAMPLER_PRESET_KEYS = {
  res_2m: 'balanced',
  res_5s: 'detail_slow',
  res_3s: 'experimental',
};

function normalizeGenerationRES4LYFName(value) {
  return String(value || '').trim().toLowerCase();
}

function isGenerationRES4LYFSamplerName(value) {
  const key = normalizeGenerationRES4LYFName(value);
  return NEO_RES4LYF_SAFE_SAMPLERS.has(key) || key.startsWith('res_');
}

function getGenerationCatalogSnapshotForPersistence() {
  return (typeof generationCatalogState !== 'undefined' && generationCatalogState)
    ? generationCatalogState
    : (window.generationCatalogState || {});
}

function getGenerationRES4LYFPersistenceCatalog() {
  const catalog = getGenerationCatalogSnapshotForPersistence() || {};
  const res = (catalog && typeof catalog.res4lyf === 'object' && catalog.res4lyf) ? catalog.res4lyf : {};
  const features = (catalog && typeof catalog.features === 'object' && catalog.features) ? catalog.features : {};
  const samplers = Array.isArray(res.samplers) ? res.samplers.map(item => String(item || '').trim()).filter(Boolean) : [];
  const schedulers = Array.isArray(res.schedulers) ? res.schedulers.map(item => String(item || '').trim()).filter(Boolean) : [];
  return { ready: !!(res.ready || features.res4lyf_ready), installed: !!(res.installed || features.res4lyf), samplers, schedulers };
}

function getGenerationSelectOptionValueByName(id, value) {
  const el = $(id);
  const target = String(value || '').trim().toLowerCase();
  if (!el || !target) return '';
  const match = Array.from(el.options || []).find(opt => String(opt.value || '').trim().toLowerCase() === target);
  return match ? String(match.value || '').trim() : '';
}

function getFirstGenerationSelectOptionValue(id) {
  const el = $(id);
  if (!el) return '';
  const match = Array.from(el.options || []).find(opt => String(opt.value || '').trim());
  return match ? String(match.value || '').trim() : '';
}

function getGenerationFallbackSamplerValue() {
  return getGenerationSelectOptionValueByName('generation-sampler', 'euler') || getFirstGenerationSelectOptionValue('generation-sampler') || 'euler';
}

function getGenerationFallbackSchedulerValue() {
  return getGenerationSelectOptionValueByName('generation-scheduler', 'normal') || getFirstGenerationSelectOptionValue('generation-scheduler') || 'normal';
}

function buildGenerationRES4LYFPersistenceMeta(sampler, scheduler) {
  const samplerKey = normalizeGenerationRES4LYFName(sampler);
  if (!isGenerationRES4LYFSamplerName(samplerKey)) return null;
  return {
    enabled: true,
    requires_extensions: ['RES4LYF'],
    sampler: String(sampler || '').trim(),
    scheduler: String(scheduler || '').trim(),
    preset_key: NEO_RES4LYF_SAMPLER_PRESET_KEYS[samplerKey] || 'custom_res_sampler',
    compatibility_mode: 'safe_ksampler',
    fallback_sampler: 'euler',
    fallback_scheduler: 'normal',
    version: 'phase6',
  };
}

function resolveGenerationPersistedSamplerSettings(draft) {
  const requestedSampler = String(draft?.sampler || 'euler').trim() || 'euler';
  const requestedScheduler = String(draft?.scheduler || 'normal').trim() || 'normal';
  const result = { sampler: requestedSampler, scheduler: requestedScheduler, fallbackApplied: false, message: '' };
  if (!isGenerationRES4LYFSamplerName(requestedSampler)) return result;

  const catalog = getGenerationRES4LYFPersistenceCatalog();
  const catalogSamplers = new Set(catalog.samplers.map(item => normalizeGenerationRES4LYFName(item)));
  const catalogSchedulers = new Set(catalog.schedulers.map(item => normalizeGenerationRES4LYFName(item)));
  const samplerOption = getGenerationSelectOptionValueByName('generation-sampler', requestedSampler);
  const schedulerOption = getGenerationSelectOptionValueByName('generation-scheduler', requestedScheduler);
  const samplerAvailable = catalog.ready && catalogSamplers.has(normalizeGenerationRES4LYFName(requestedSampler)) && !!samplerOption;

  if (!samplerAvailable) {
    result.sampler = String(draft?.res4lyf?.fallback_sampler || '').trim() || getGenerationFallbackSamplerValue();
    result.scheduler = String(draft?.res4lyf?.fallback_scheduler || '').trim() || getGenerationFallbackSchedulerValue();
    result.fallbackApplied = true;
    result.message = `RES4LYF sampler '${requestedSampler}' was saved in this draft, but it is not available in the current ComfyUI catalog. Reverted to ${result.sampler} / ${result.scheduler}.`;
    return result;
  }

  result.sampler = samplerOption;
  if (requestedScheduler && schedulerOption) {
    result.scheduler = schedulerOption;
  } else if (requestedScheduler && normalizeGenerationRES4LYFName(requestedScheduler) === 'beta57' && !catalogSchedulers.has('beta57')) {
    result.scheduler = getGenerationFallbackSchedulerValue();
    result.fallbackApplied = true;
    result.message = `RES4LYF scheduler '${requestedScheduler}' was saved in this draft, but it is not available now. Kept ${result.sampler} and reverted scheduler to ${result.scheduler}.`;
  }
  return result;
}
window.isGenerationRES4LYFSamplerName = isGenerationRES4LYFSamplerName;
window.buildGenerationRES4LYFPersistenceMeta = buildGenerationRES4LYFPersistenceMeta;
window.resolveGenerationPersistedSamplerSettings = resolveGenerationPersistedSamplerSettings;


window.NeoGenerationDraftState.collectGenerationDraft = function collectGenerationDraft() {
  const draft = {
    version: 5,
    updated_at: Date.now(),
    workflow_type: $('generation-workflow-type')?.value || 'txt2img',
    family: $('generation-family')?.value || 'sdxl_sd',
    model_source: $('generation-model-source')?.value || 'checkpoint',
    checkpoint: trim($('generation-checkpoint')?.value || ''),
    gguf_unet: trim($('generation-gguf-unet')?.value || ''),
    gguf_clip_mode: $('generation-gguf-clip-mode')?.value || 'dual',
    gguf_clip_type: $('generation-gguf-clip-type')?.value || 'flux',
    gguf_clip_primary: trim($('generation-gguf-clip-primary')?.value || ''),
    gguf_clip_secondary: trim($('generation-gguf-clip-secondary')?.value || ''),
    gguf_guidance: $('generation-gguf-guidance')?.value || '3.5',
    vae: trim($('generation-vae')?.value || ''),
    sampler: $('generation-sampler')?.value || 'euler',
    scheduler: $('generation-scheduler')?.value || 'normal',
    width: $('generation-width')?.value || '1024',
    height: $('generation-height')?.value || '1024',
    size_preset: $('generation-size-preset')?.value || 'custom',
    steps: $('generation-steps')?.value || '28',
    batch_size: $('generation-batch-size')?.value || '1',
    cfg: $('generation-cfg')?.value || '5.2',
    dynamic_thresholding: (typeof readGenerationDynamicThresholding === 'function') ? readGenerationDynamicThresholding() : { enabled:false, preset:'off' },
    denoise: $('generation-denoise')?.value || '1.0',
    seed: $('generation-seed')?.value || '-1',
    seed_locked: $('btn-generation-seed-lock')?.dataset.locked === 'true',
    positive: $('generation-positive')?.value || '',
    negative: $('generation-negative')?.value || '',
    prompt_conditioning_mode: $('generation-prompt-conditioning-mode')?.value || 'raw',
    clip_skip: $('generation-clip-skip')?.value || '1',
    experimental_mode: $('generation-experimental-mode')?.value || 'off',
    advanced_slot_a: $('generation-advanced-slot-a')?.value || 'none',
    advanced_slot_b: $('generation-advanced-slot-b')?.value || 'none',
    tagassist_threshold: $('generation-tagassist-threshold')?.value || '0.35',
    tagassist_filter: $('generation-tagassist-filter')?.value || '',
    selected_style: $('generation-style-select')?.value || '',
    style_enabled: $('generation-style-enabled') ? !!$('generation-style-enabled').checked : true,
    style_pass_target: $('generation-style-pass-target')?.value || 'both',
    active_styles: generationActiveStyles.slice(),
    style_name: $('generation-style-name')?.value || '',
    style_positive: $('generation-style-positive')?.value || '',
    style_negative: $('generation-style-negative')?.value || '',
    ti_helper_target: $('generation-ti-helper-target')?.value || 'both',
    ti_base_positive: $('generation-ti-base-positive')?.value || '',
    ti_base_negative: $('generation-ti-base-negative')?.value || '',
    ti_finish_positive: $('generation-ti-finish-positive')?.value || '',
    ti_finish_negative: $('generation-ti-finish-negative')?.value || '',
    source_resize_mode: $('generation-source-resize-mode')?.value || 'native',
    inpaint_target: $('generation-inpaint-target')?.value || 'masked',
    inpaint_context: $('generation-inpaint-context')?.value || 'full_image',
    inpaint_backend: $('generation-inpaint-backend')?.value || 'standard',
    composition_guide_type: $('generation-composition-guide-type')?.value || 'none',
    composition_source_mode: $('generation-composition-source-mode')?.value || 'source_image',
    grow_mask_by: $('generation-grow-mask-by')?.value || '6',
    mask_feather: $('generation-mask-feather')?.value || '0',
    outpaint_left: $('generation-outpaint-left')?.value || '0',
    outpaint_top: $('generation-outpaint-top')?.value || '0',
    outpaint_right: $('generation-outpaint-right')?.value || '0',
    outpaint_bottom: $('generation-outpaint-bottom')?.value || '0',
    outpaint_feather: $('generation-outpaint-feather')?.value || '24',
    outpaint_preset: $('generation-outpaint-preset')?.value || 'custom',
    outpaint_anchor: $('generation-outpaint-anchor')?.value || 'center',
    identity_goal: $('generation-identity-goal')?.value || 'off',
    identity_route: $('generation-identity-route')?.value || 'auto',
    identity_strength: $('generation-identity-strength')?.value || '0.85',
    identity_faceid_lora: $('generation-identity-faceid-lora')?.value || '0.75',
    identity_start: $('generation-identity-start')?.value || '0',
    identity_end: $('generation-identity-end')?.value || '1',
    identity_notes: $('generation-identity-notes')?.value || '',
    detailer_enabled: !!$('generation-detailer-enabled')?.checked,
    detailer_provider: $('generation-detailer-provider')?.value || 'ultralytics',
    detailer_mode: $('generation-detailer-mode')?.value || 'face',
    detailer_detector_type: $('generation-detailer-detector-type')?.value || 'bbox',
    detailer_model: $('generation-detailer-model')?.value || '',
    detailer_sam_model: $('generation-detailer-sam-model')?.value || '',
    detailer_custom_classes: $('generation-detailer-custom-classes')?.value || '',
    detailer_confidence: $('generation-detailer-confidence')?.value || '0.35',
    detailer_topk: $('generation-detailer-topk')?.value || '0',
    detailer_bbox_grow: $('generation-detailer-bbox-grow')?.value || '12',
    detailer_mask_blur: $('generation-detailer-mask-blur')?.value || '4',
    detailer_denoise: $('generation-detailer-denoise')?.value || '0.12',
    detailer_steps: $('generation-detailer-steps')?.value || '12',
    detailer_use_main_prompt: !!$('generation-detailer-use-main-prompt')?.checked,
    detailer_force_inpaint: !!$('generation-detailer-force-inpaint')?.checked,
    detailer_positive: $('generation-detailer-positive')?.value || '',
    detailer_negative: $('generation-detailer-negative')?.value || '',
    detailer_order: $('generation-detailer-order')?.value || 'auto',
    detailer_start_index: $('generation-detailer-start-index')?.value || '1',
    detailer_count: $('generation-detailer-count')?.value || '1',
    detailer_min_area: $('generation-detailer-min-area')?.value || '0',
    detailer_max_area: $('generation-detailer-max-area')?.value || '0',
    detailer_reference_lock: $('generation-detailer-reference-lock')?.value || 'none',
    detailer_target_mode: $('generation-detailer-target-mode')?.value || 'auto_detect',
    detailer_manual_boxes: $('generation-detailer-manual-boxes')?.value || '',
    detailer_custom_detector_root: $('generation-detailer-custom-detector-root')?.value || '',
    detailer_custom_sam_root: $('generation-detailer-custom-sam-root')?.value || '',
    detailer_sam_preset: $('generation-detailer-sam-preset')?.value || '',
    detailer_passes: Array.from(document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row')).map(row => ({
      uid: row.dataset.uid || '',
      enabled: isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled')),
      mode: row.querySelector('.generation-detailer-mode')?.value || 'face',
      detector_type: row.querySelector('.generation-detailer-detector-type')?.value || 'bbox',
      detector_model: row.querySelector('.generation-detailer-model')?.value || '',
      order_mode: row.querySelector('.generation-detailer-order')?.value || 'auto',
      start_index: row.querySelector('.generation-detailer-start-index')?.value || '1',
      count: row.querySelector('.generation-detailer-count')?.value || '1',
      min_area: row.querySelector('.generation-detailer-min-area')?.value || '0',
      max_area: row.querySelector('.generation-detailer-max-area')?.value || '0',
      reference_lock: row.querySelector('.generation-detailer-reference-lock')?.value || 'none',
      target_mode: row.querySelector('.generation-detailer-target-mode')?.value || 'auto_detect',
      manual_boxes: row.querySelector('.generation-detailer-manual-boxes')?.value || '',
      positive: row.querySelector('.generation-detailer-positive')?.value || '',
      negative: row.querySelector('.generation-detailer-negative')?.value || '',
    })),
    lora_enabled: true,
    lora_name: (Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row .generation-lora-name'))[0]?.value || ''),
    lora_strength: (Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row .generation-lora-strength'))[0]?.value || '0.8'),
    loras: Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row')).map(row => ({
      uid: row.dataset.uid || '',
      enabled: isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled')),
      name: row.querySelector('.generation-lora-name')?.value || '',
      strength: row.querySelector('.generation-lora-strength')?.value || '0.8',
      target: row.querySelector('.generation-lora-target')?.value || 'both',
      apply_to: row.querySelector('.generation-lora-apply-to')?.value || 'global',
    })),
    controlnet_enabled: isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled')),
    controlnet_name: $('generation-controlnet-name')?.value || '',
    controlnet_unit: $('generation-controlnet-unit')?.value || 'auto',
    controlnet_preprocessor: $('generation-controlnet-preprocessor')?.value || 'none',
    controlnet_strength: $('generation-controlnet-strength')?.value || '1.0',
    controlnet_units: Array.from(document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row')).map(row => ({
      uid: row.dataset.uid || '',
      enabled: isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled')),
      unit: row.querySelector('.generation-controlnet-unit')?.value || 'auto',
      preprocessor: row.querySelector('.generation-controlnet-preprocessor')?.value || 'none',
      model: row.querySelector('.generation-controlnet-name')?.value || '',
      strength: row.querySelector('.generation-controlnet-strength')?.value || '1.0',
    })),
    ipadapter_enabled: isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled')),
    ipadapter_mode: $('generation-ipadapter-mode')?.value || 'standard',
    ipadapter_name: $('generation-ipadapter-name')?.value || '',
    ipadapter_clip_vision: $('generation-ipadapter-clip-vision')?.value || '',
    ipadapter_faceid_preset: $('generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2',
    ipadapter_faceid_provider: $('generation-ipadapter-faceid-provider')?.value || 'CUDA',
    ipadapter_faceid_lora_strength: $('generation-identity-faceid-lora')?.value || $('generation-ipadapter-faceid-lora-strength')?.value || '0.75',
    ipadapter_weight: $('generation-ipadapter-weight')?.value || '1.0',
    ipadapter_weight_faceidv2: $('generation-ipadapter-weight-faceidv2')?.value || '1.0',
    ipadapter_weight_type: $('generation-ipadapter-weight-type')?.value || 'linear',
    ipadapter_combine_embeds: $('generation-ipadapter-combine-embeds')?.value || 'concat',
    ipadapter_embeds_scaling: $('generation-ipadapter-embeds-scaling')?.value || 'V only',
    ipadapter_start_at: $('generation-ipadapter-start-at')?.value || '0',
    ipadapter_end_at: $('generation-ipadapter-end-at')?.value || '1',
    ipadapter_units: Array.from(document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row')).map(row => ({
      uid: row.dataset.uid || '',
      enabled: isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled')),
      mode: row.querySelector('.generation-ipadapter-mode')?.value || 'standard',
      model: row.querySelector('.generation-ipadapter-name')?.value || '',
      clip_vision: row.querySelector('.generation-ipadapter-clip-vision')?.value || '',
      faceid_preset: row.querySelector('.generation-ipadapter-faceid-preset')?.value || 'FACEID PLUS V2',
      faceid_provider: row.querySelector('.generation-ipadapter-faceid-provider')?.value || 'CUDA',
      faceid_lora_strength: $('generation-identity-faceid-lora')?.value || $('generation-ipadapter-faceid-lora-strength')?.value || '0.75',
      weight: row.querySelector('.generation-ipadapter-weight')?.value || '1.0',
      weight_faceidv2: row.querySelector('.generation-ipadapter-weight-faceidv2')?.value || '1.0',
      weight_type: row.querySelector('.generation-ipadapter-weight-type')?.value || 'linear',
      combine_embeds: row.querySelector('.generation-ipadapter-combine-embeds')?.value || 'concat',
      embeds_scaling: row.querySelector('.generation-ipadapter-embeds-scaling')?.value || 'V only',
      start_at: row.querySelector('.generation-ipadapter-start-at')?.value || '0',
      end_at: row.querySelector('.generation-ipadapter-end-at')?.value || '1',
    })),
    refine_profile: $('generation-refine-profile')?.value || 'custom',
    refine_enabled: $('generation-refine-enabled')?.value || 'false',
    refine_strategy: $('generation-refine-strategy')?.value || 'standard',
    refine_mode: $('generation-refine-mode')?.value || 'latent',
    refine_resize_method: $('generation-refine-resize-method')?.value || 'lanczos',
    refine_upscaler: $('generation-refine-upscaler')?.value || '',
    refine_scale: $('generation-refine-scale')?.value || '1.5',
    refine_steps: $('generation-refine-steps')?.value || '12',
    refine_denoise: $('generation-refine-denoise')?.value || '0.12',
    refine_cfg: $('generation-refine-cfg')?.value || '5.2',
    refine_sampler: $('generation-refine-sampler')?.value || '',
    refine_scheduler: $('generation-refine-scheduler')?.value || '',
    refine_tiled_vae: $('generation-refine-tiled-vae')?.value || 'true',
    refine_tile_size: $('generation-refine-tile-size')?.value || '512',
    refine_tile_overlap: $('generation-refine-tile-overlap')?.value || '64',
    image_upscale_profile: $('generation-image-upscale-profile')?.value || 'preserve_2x',
    image_upscale_model: $('generation-image-upscale-model')?.value || '',
    image_upscale_scale: $('generation-image-upscale-scale')?.value || '2.0',
    image_upscale_resize_method: $('generation-image-upscale-resize-method')?.value || 'lanczos',
    image_upscale_restore_assist: $('generation-image-upscale-restore-assist')?.value || 'off',
    image_upscale_restore_model: $('generation-image-upscale-restore-model')?.value || '',
    image_upscale_restore_fidelity: $('generation-image-upscale-restore-fidelity')?.value || '0.65',
    image_upscale_restore_detection: $('generation-image-upscale-restore-detection')?.value || 'retinaface_resnet50',
    supir_enabled: $('generation-supir-enabled')?.value || 'false',
    supir_model: $('generation-supir-model')?.value || '',
    supir_sdxl_model: $('generation-supir-sdxl-model')?.value || '',
    supir_scale: $('generation-supir-scale')?.value || '1.5',
    supir_steps: $('generation-supir-steps')?.value || '45',
    supir_restoration_scale: $('generation-supir-restoration-scale')?.value || '-1',
    supir_cfg_scale: $('generation-supir-cfg-scale')?.value || '4.0',
    supir_control_scale: $('generation-supir-control-scale')?.value || '1.0',
    supir_color_fix_type: $('generation-supir-color-fix-type')?.value || 'Wavelet',
    supir_tiled_vae: $('generation-supir-tiled-vae')?.value || 'true',
    supir_encoder_tile_size: $('generation-supir-encoder-tile-size')?.value || '512',
    supir_decoder_tile_size: $('generation-supir-decoder-tile-size')?.value || '64',
    supir_a_prompt: $('generation-supir-a-prompt')?.value || 'high quality, detailed',
    supir_n_prompt: $('generation-supir-n-prompt')?.value || 'bad quality, blurry, messy',
    output_root: $('generation-output-root')?.value || '',
    output_category: $('generation-output-category')?.value || 'Uncategorized',
    wildcard_root: $('generation-wildcard-root')?.value || '',
    wildcard_enabled: $('generation-wildcard-enabled') ? !!$('generation-wildcard-enabled').checked : true,
    wildcard_selected_file: $('generation-wildcard-file')?.value || '',
    wildcard_target: $('generation-wildcard-target')?.value || 'positive',
    wildcard_auto_resolve: !!$('generation-wildcard-auto-resolve')?.checked,
    wildcard_use_seed: !!$('generation-wildcard-use-seed')?.checked,
    wildcard_preview_count: $('generation-wildcard-preview-count')?.value || '3',
    wildcard_queue_count: $('generation-wildcard-queue-count')?.value || '3',
    notes: $('generation-workflow-notes')?.value || '',
  };
  draft.workflow_state = window.NeoImageState?.buildPersistedWorkflowState
    ? window.NeoImageState.buildPersistedWorkflowState({
        reason: 'draft_save',
        output_policy: draft.output_policy || draft._neo_output_policy || 'new_current_run',
        batch_size: draft.batch_size,
        outpaintExpansion: {
          left: draft.outpaint_left,
          top: draft.outpaint_top,
          right: draft.outpaint_right,
          bottom: draft.outpaint_bottom,
        },
      })
    : {
        schema_version: 1,
        owner: 'legacy_dom_fallback',
        raw_state: { mode: draft.workflow_type || 'txt2img', workflow_type: draft.workflow_type || 'txt2img' },
        effective_state: { mode: draft.workflow_type || 'txt2img', workflow_type: draft.workflow_type || 'txt2img' },
        transition: { switch_reason: 'draft_save' },
        version: 'phase_i_save_restore_metadata_v1',
      };
  draft._neo_workflow_state = draft.workflow_state?.workflow_state || draft.workflow_state;
  draft.res4lyf = buildGenerationRES4LYFPersistenceMeta(draft.sampler, draft.scheduler);
  return sanitizeGenerationDraftState(draft);
}

window.NeoGenerationDraftState.buildGenerationSectionStatusPayload = function buildGenerationSectionStatusPayload(specOrId) {
  const spec = typeof specOrId === 'string' ? (window.getNeoGenerationSectionSpec?.(specOrId) || { id: specOrId }) : (specOrId || {});
  const id = String(spec?.id || '');

  if (id === 'generation-style-addons') {
    const styleEnabled = $('generation-style-enabled') ? !!$('generation-style-enabled').checked : true;
    sanitizeGenerationActiveStyles();
    const count = generationActiveStyles.length;
    const manualPositive = trim($('generation-style-positive')?.value || '');
    const manualNegative = trim($('generation-style-negative')?.value || '');
    const singleName = count === 1 ? String(generationActiveStyles[0] || '').trim() : '';
    return {
      active: styleEnabled,
      count,
      countLabel: 'selected',
      singleName,
      maxNameLength: 24,
      detailText: styleEnabled && count === 0 && (manualPositive || manualNegative) ? 'Manual' : '',
    };
  }

  if (id === 'generation-wildcards') {
    const wildcardEnabled = $('generation-wildcard-enabled') ? !!$('generation-wildcard-enabled').checked : true;
    const selectedLabel = getGenerationSelectedOptionLabel('generation-wildcard-file');
    const detailText = wildcardEnabled && selectedLabel && !/^select/i.test(selectedLabel) && selectedLabel.length <= 22 ? selectedLabel : '';
    return { active: wildcardEnabled, detailText };
  }


  if (id === 'generation-hires-settings') {
    const hiresOn = String($('generation-refine-enabled')?.value || 'false') === 'true';
    const hiresMode = trim(($('generation-refine-mode')?.value || '') === 'image_upscale' ? 'Image upscale' : 'Latent');
    return { active: hiresOn, modeLabel: hiresMode };
  }

  if (id === 'generation-supir-settings') {
    const supirOn = String($('generation-supir-enabled')?.value || 'false') === 'true';
    return { active: supirOn };
  }

  if (id === 'generation-lora-settings') {
    const count = countGenerationEnabledLoras();
    return { active: count > 0, count, countLabel: 'selected', zeroLabel: 'No LoRA' };
  }

  if (id === 'generation-ti-settings') {
    const count = countGenerationSelectedTiTokens();
    return { active: count > 0, count, countLabel: 'selected', zeroLabel: 'No TI' };
  }

  if (id === 'generation-detailer-settings') {
    const count = countGenerationEnabledDetailers();
    return { active: count > 0, count, countLabel: 'enabled' };
  }

  if (id === 'generation-controlnet-settings') {
    const count = countGenerationEnabledControlnets();
    return { active: count > 0, count, countLabel: 'enabled' };
  }

  if (id === 'generation-ipadapter-settings') {
    const count = countGenerationEnabledIpAdapters();
    return { active: count > 0, count, countLabel: 'enabled' };
  }

  if (id === 'generation-image-upscale-settings') {
    const model = trim($('generation-image-upscale-model')?.value || '');
    const batchCount = $('generation-image-upscale-batch-files')?.files?.length || 0;
    const scale = Number($('generation-image-upscale-scale')?.value || 2.0);
    return {
      active: !!model || scale > 1,
      primaryText: model ? 'Ready' : (scale > 1 ? 'Resize only' : 'Idle'),
      detailText: batchCount ? `${batchCount} batch` : `${scale}×`,
      detailTone: 'detail',
    };
  }

  return null;
}

window.NeoGenerationDraftState.applyGenerationDraft = function applyGenerationDraft(draft) {
  if (!draft || typeof draft !== 'object') return;
  draft = sanitizeGenerationDraftState(draft) || {};
  generationDraftApplyInProgress = true;
  try {
    if ($('generation-family')) $('generation-family').value = draft.family || 'sdxl_sd';
    if ($('generation-model-source')) $('generation-model-source').value = draft.model_source || 'checkpoint';
    if (window.NeoGenerationFamilyRouter?.setActiveFamily) window.NeoGenerationFamilyRouter.setActiveFamily(draft.family || '', { silent:true });
    const resolvedDef = window.NeoGenerationFamilyRouter?.defs?.[$('generation-family')?.value || draft.family || 'sdxl_sd'];
    const allowedModes = Array.isArray(resolvedDef?.allowedModes) && resolvedDef.allowedModes.length ? resolvedDef.allowedModes : ['txt2img'];
    const requestedMode = String(draft.workflow_state?.effective_state?.mode || draft.workflow_state?.raw_state?.mode || draft.workflow_type || 'txt2img').trim();
    const restoredUnsupportedMode = !allowedModes.includes(requestedMode);
    const restoredMode = restoredUnsupportedMode ? allowedModes[0] : requestedMode;
    if (window.NeoImageState?.restoreWorkflowState && draft.workflow_state) {
      window.NeoImageState.restoreWorkflowState(draft.workflow_state, { mode: restoredMode, reason: restoredUnsupportedMode ? 'draft_restore_family_guardrail' : 'draft_restore' });
    } else if (window.setGenerationWorkflowMode) {
      window.setGenerationWorkflowMode(restoredMode, { reason: restoredUnsupportedMode ? 'draft_restore_family_guardrail' : 'draft_restore', validate: true, forceReveal: true });
    } else {
      if ($('generation-workflow-type')) $('generation-workflow-type').value = restoredMode;
      if (window.NeoImageState?.setWorkflowMode) window.NeoImageState.setWorkflowMode(restoredMode, { reason: restoredUnsupportedMode ? 'draft_restore_family_guardrail' : 'draft_restore', force_event: true });
    }
    if ($('generation-workflow-type')) $('generation-workflow-type').value = restoredMode;
    if ($('generation-checkpoint')) $('generation-checkpoint').value = draft.checkpoint || '';
    if ($('generation-gguf-unet')) $('generation-gguf-unet').value = draft.gguf_unet || '';
    if ($('generation-gguf-clip-mode')) $('generation-gguf-clip-mode').value = draft.gguf_clip_mode || 'dual';
    if ($('generation-gguf-clip-type')) $('generation-gguf-clip-type').value = draft.gguf_clip_type || 'flux';
    if ($('generation-gguf-clip-primary')) $('generation-gguf-clip-primary').value = draft.gguf_clip_primary || '';
    if ($('generation-gguf-clip-secondary')) $('generation-gguf-clip-secondary').value = draft.gguf_clip_secondary || '';
    if ($('generation-gguf-guidance')) $('generation-gguf-guidance').value = draft.gguf_guidance || '3.5';
    if ($('generation-gguf-guidance-range')) $('generation-gguf-guidance-range').value = draft.gguf_guidance || '3.5';
    if ($('generation-vae')) $('generation-vae').value = draft.vae || '';
    const persistedSamplerSettings = resolveGenerationPersistedSamplerSettings(draft);
    if ($('generation-sampler')) $('generation-sampler').value = persistedSamplerSettings.sampler || 'euler';
    if ($('generation-scheduler')) $('generation-scheduler').value = persistedSamplerSettings.scheduler || 'normal';
    if (persistedSamplerSettings.fallbackApplied && persistedSamplerSettings.message) {
      setTimeout(() => {
        try { setStatus('generation-status', persistedSamplerSettings.message, 'warn'); } catch (_) {}
        try { if (typeof renderGenerationRES4LYFStatus === 'function') renderGenerationRES4LYFStatus(); } catch (_) {}
      }, 80);
    }
    if ($('generation-width')) $('generation-width').value = draft.width || '1024';
    if ($('generation-height')) $('generation-height').value = draft.height || '1024';
    if ($('generation-steps')) $('generation-steps').value = draft.steps || '28';
    if ($('generation-steps-range')) $('generation-steps-range').value = draft.steps || '28';
    if ($('generation-batch-size')) $('generation-batch-size').value = draft.batch_size || '1';
    if ($('generation-cfg')) $('generation-cfg').value = draft.cfg || '5.2';
    if ($('generation-cfg-range')) $('generation-cfg-range').value = draft.cfg || '5.2';
    if (draft.dynamic_thresholding) {
      if ($('generation-dynamic-thresholding-preset')) $('generation-dynamic-thresholding-preset').value = draft.dynamic_thresholding.preset || 'off';
      if ($('generation-dynamic-thresholding-mode')) $('generation-dynamic-thresholding-mode').value = draft.dynamic_thresholding.mode || 'simple';
      if ($('generation-dynamic-thresholding-mimic')) $('generation-dynamic-thresholding-mimic').value = draft.dynamic_thresholding.mimic_scale || '7.0';
      if ($('generation-dynamic-thresholding-percentile')) $('generation-dynamic-thresholding-percentile').value = draft.dynamic_thresholding.threshold_percentile || '1.0';
      if ($('generation-dynamic-thresholding-customize')) $('generation-dynamic-thresholding-customize').checked = !!draft.dynamic_thresholding.custom_values || draft.dynamic_thresholding.preset === 'advanced';
      if (typeof renderGenerationDynamicThresholding === 'function') renderGenerationDynamicThresholding();
    }
    if ($('generation-denoise')) $('generation-denoise').value = draft.denoise || '1.0';
    if ($('generation-denoise-range')) $('generation-denoise-range').value = draft.denoise || '1.0';
    if ($('generation-seed')) $('generation-seed').value = draft.seed || '-1';
    const promptMergeLock = getGenerationPromptMergeLockForDraftApply();
    if ($('generation-positive')) {
      const restoredPositive = draft.positive || '';
      $('generation-positive').value = promptMergeLock
        ? mergeGenerationPromptForDraftApply(restoredPositive, promptMergeLock.positive)
        : restoredPositive;
    }
    if ($('generation-negative')) $('generation-negative').value = draft.negative || '';
    if ($('generation-prompt-conditioning-mode')) $('generation-prompt-conditioning-mode').value = draft.prompt_conditioning_mode || 'raw';
    if ($('generation-clip-skip')) $('generation-clip-skip').value = draft.clip_skip || '1';
    if ($('generation-experimental-mode')) $('generation-experimental-mode').value = draft.experimental_mode || 'off';
    if ($('generation-advanced-slot-a')) $('generation-advanced-slot-a').value = draft.advanced_slot_a || 'none';
    if ($('generation-advanced-slot-b')) $('generation-advanced-slot-b').value = draft.advanced_slot_b || 'none';
    if ($('generation-tagassist-threshold')) $('generation-tagassist-threshold').value = draft.tagassist_threshold || '0.35';
    if ($('generation-tagassist-threshold-range')) $('generation-tagassist-threshold-range').value = draft.tagassist_threshold || '0.35';
    if ($('generation-tagassist-filter')) $('generation-tagassist-filter').value = draft.tagassist_filter || '';
    if ($('generation-style-select')) $('generation-style-select').value = draft.selected_style || '';
    if ($('generation-style-enabled')) $('generation-style-enabled').checked = draft.style_enabled !== false;
    if ($('generation-style-pass-target')) $('generation-style-pass-target').value = draft.style_pass_target || 'both';
    generationActiveStyles = Array.isArray(draft.active_styles) ? draft.active_styles.slice() : [];
    if ($('generation-style-name')) $('generation-style-name').value = draft.style_name || draft.selected_style || '';
    if ($('generation-style-positive')) $('generation-style-positive').value = draft.style_positive || '';
    if ($('generation-style-negative')) $('generation-style-negative').value = draft.style_negative || '';
    if ($('generation-ti-helper-target')) $('generation-ti-helper-target').value = draft.ti_helper_target || 'both';
    if ($('generation-ti-base-positive')) $('generation-ti-base-positive').value = draft.ti_base_positive || '';
    if ($('generation-ti-base-negative')) $('generation-ti-base-negative').value = draft.ti_base_negative || '';
    if ($('generation-ti-finish-positive')) $('generation-ti-finish-positive').value = draft.ti_finish_positive || '';
    if ($('generation-ti-finish-negative')) $('generation-ti-finish-negative').value = draft.ti_finish_negative || '';
    if ($('generation-source-resize-mode')) $('generation-source-resize-mode').value = draft.source_resize_mode || 'native';
    if ($('generation-inpaint-target')) $('generation-inpaint-target').value = draft.inpaint_target || 'masked';
    if ($('generation-inpaint-context')) $('generation-inpaint-context').value = draft.inpaint_context || 'full_image';
    if ($('generation-inpaint-backend')) $('generation-inpaint-backend').value = draft.inpaint_backend || 'standard';
    if ($('generation-composition-guide-type')) $('generation-composition-guide-type').value = draft.composition_guide_type || 'none';
    if ($('generation-composition-source-mode')) $('generation-composition-source-mode').value = draft.composition_source_mode || 'source_image';
    if ($('generation-grow-mask-by')) $('generation-grow-mask-by').value = draft.grow_mask_by || '6';
    if ($('generation-mask-feather')) $('generation-mask-feather').value = draft.mask_feather || '0';
    if ($('generation-outpaint-left')) $('generation-outpaint-left').value = draft.outpaint_left || '0';
    if ($('generation-outpaint-top')) $('generation-outpaint-top').value = draft.outpaint_top || '0';
    if ($('generation-outpaint-right')) $('generation-outpaint-right').value = draft.outpaint_right || '0';
    if ($('generation-outpaint-bottom')) $('generation-outpaint-bottom').value = draft.outpaint_bottom || '0';
    if ($('generation-outpaint-feather')) $('generation-outpaint-feather').value = draft.outpaint_feather || '24';
    if ($('generation-outpaint-preset')) $('generation-outpaint-preset').value = draft.outpaint_preset || 'custom';
    if ($('generation-outpaint-anchor')) $('generation-outpaint-anchor').value = draft.outpaint_anchor || 'center';
    if ($('generation-identity-goal')) $('generation-identity-goal').value = draft.identity_goal || 'off';
    if ($('generation-identity-route')) $('generation-identity-route').value = draft.identity_route || 'auto';
    if ($('generation-identity-strength')) $('generation-identity-strength').value = draft.identity_strength || '0.85';
    if ($('generation-identity-faceid-lora')) $('generation-identity-faceid-lora').value = draft.identity_faceid_lora || '0.75';
    if ($('generation-identity-start')) $('generation-identity-start').value = draft.identity_start || '0';
    if ($('generation-identity-end')) $('generation-identity-end').value = draft.identity_end || '1';
    if ($('generation-identity-notes')) $('generation-identity-notes').value = draft.identity_notes || '';
    if ($('generation-detailer-enabled')) $('generation-detailer-enabled').checked = !!draft.detailer_enabled;
    if ($('generation-detailer-provider')) $('generation-detailer-provider').value = draft.detailer_provider || 'ultralytics';
    if ($('generation-detailer-mode')) $('generation-detailer-mode').value = draft.detailer_mode || 'face';
    if ($('generation-detailer-detector-type')) $('generation-detailer-detector-type').value = draft.detailer_detector_type || 'bbox';
    if ($('generation-detailer-model')) $('generation-detailer-model').value = draft.detailer_model || '';
    if ($('generation-detailer-sam-model')) $('generation-detailer-sam-model').value = draft.detailer_sam_model || '';
    if ($('generation-detailer-custom-classes')) $('generation-detailer-custom-classes').value = draft.detailer_custom_classes || '';
    if ($('generation-detailer-confidence')) $('generation-detailer-confidence').value = draft.detailer_confidence || '0.35';
    if ($('generation-detailer-topk')) $('generation-detailer-topk').value = draft.detailer_topk || '0';
    if ($('generation-detailer-bbox-grow')) $('generation-detailer-bbox-grow').value = draft.detailer_bbox_grow || '12';
    if ($('generation-detailer-mask-blur')) $('generation-detailer-mask-blur').value = draft.detailer_mask_blur || '4';
    if ($('generation-detailer-denoise')) $('generation-detailer-denoise').value = draft.detailer_denoise || '0.12';
    if ($('generation-detailer-steps')) $('generation-detailer-steps').value = draft.detailer_steps || '12';
    if ($('generation-detailer-use-main-prompt')) $('generation-detailer-use-main-prompt').checked = draft.detailer_use_main_prompt !== false;
    if ($('generation-detailer-force-inpaint')) $('generation-detailer-force-inpaint').checked = draft.detailer_force_inpaint !== false;
    if ($('generation-detailer-positive')) $('generation-detailer-positive').value = draft.detailer_positive || '';
    if ($('generation-detailer-negative')) $('generation-detailer-negative').value = draft.detailer_negative || '';
    if ($('generation-detailer-order')) $('generation-detailer-order').value = draft.detailer_order || 'auto';
    if ($('generation-detailer-start-index')) $('generation-detailer-start-index').value = draft.detailer_start_index || '1';
    if ($('generation-detailer-count')) $('generation-detailer-count').value = draft.detailer_count || '1';
    if ($('generation-detailer-min-area')) $('generation-detailer-min-area').value = draft.detailer_min_area || '0';
    if ($('generation-detailer-max-area')) $('generation-detailer-max-area').value = draft.detailer_max_area || '0';
    if ($('generation-detailer-reference-lock')) $('generation-detailer-reference-lock').value = draft.detailer_reference_lock || 'none';
    if ($('generation-detailer-target-mode')) $('generation-detailer-target-mode').value = draft.detailer_target_mode || 'auto_detect';
    if ($('generation-detailer-manual-boxes')) $('generation-detailer-manual-boxes').value = draft.detailer_manual_boxes || '';
    if ($('generation-detailer-custom-detector-root')) $('generation-detailer-custom-detector-root').value = draft.detailer_custom_detector_root || '';
    if ($('generation-detailer-custom-sam-root')) $('generation-detailer-custom-sam-root').value = draft.detailer_custom_sam_root || '';
    if ($('generation-detailer-sam-preset')) $('generation-detailer-sam-preset').value = draft.detailer_sam_preset || '';
    const detailerWrap = $('generation-detailer-extra-list');
    if (detailerWrap) {
      detailerWrap.innerHTML = '';
      (Array.isArray(draft.detailer_passes) ? draft.detailer_passes : []).forEach(item => detailerWrap.appendChild(createGenerationDetailerRow({
        uid: item.uid || '',
        enabled: item.enabled !== false,
        mode: item.mode || 'face',
        detector_type: item.detector_type || 'bbox',
        model: item.detector_model || item.model || '',
        order_mode: item.order_mode || item.order || 'auto',
        start_index: item.start_index || '1',
        count: item.count || '1',
        min_area: item.min_area || '0',
        max_area: item.max_area || '0',
        reference_lock: item.reference_lock || 'none',
        target_mode: item.target_mode || 'auto_detect',
        manual_boxes: item.manual_boxes || '',
        positive: item.positive || '',
        negative: item.negative || '',
      })));
    }
    renderGenerationActiveStyles();
    if (typeof syncGenerationModeUI === 'function') syncGenerationModeUI();
    if (typeof syncGenerationLaunchAvailability === 'function') syncGenerationLaunchAvailability();
    if (restoredUnsupportedMode) setStatus('generation-status', `Draft restored, but ${requestedMode} is not available on ${resolvedDef?.label || $('generation-family')?.value || 'this family'} in this build. Neo switched back to ${allowedModes[0]}.`, 'warn');
    if ($('generation-lora-enabled')) $('generation-lora-enabled').checked = false;
    if ($('generation-lora-name')) $('generation-lora-name').value = '';
    if ($('generation-lora-strength')) $('generation-lora-strength').value = '0.8';
    if ($('generation-controlnet-enabled')) $('generation-controlnet-enabled').checked = draft.controlnet_enabled !== false;
    if ($('generation-controlnet-unit')) $('generation-controlnet-unit').value = draft.controlnet_unit || 'auto';
    if ($('generation-controlnet-name')) $('generation-controlnet-name').value = draft.controlnet_name || '';
    if ($('generation-controlnet-preprocessor')) $('generation-controlnet-preprocessor').value = draft.controlnet_preprocessor || 'none';
    if ($('generation-controlnet-strength')) $('generation-controlnet-strength').value = draft.controlnet_strength || '1.0';
    if ($('generation-ipadapter-enabled')) $('generation-ipadapter-enabled').checked = !!draft.ipadapter_enabled;
    if ($('generation-ipadapter-mode')) $('generation-ipadapter-mode').value = draft.ipadapter_mode || 'standard';
    if ($('generation-ipadapter-name')) $('generation-ipadapter-name').value = draft.ipadapter_name || '';
    if ($('generation-ipadapter-clip-vision')) $('generation-ipadapter-clip-vision').value = draft.ipadapter_clip_vision || '';
    if ($('generation-ipadapter-faceid-preset')) $('generation-ipadapter-faceid-preset').value = draft.ipadapter_faceid_preset || 'FACEID PLUS V2';
    if ($('generation-ipadapter-faceid-provider')) $('generation-ipadapter-faceid-provider').value = draft.ipadapter_faceid_provider || 'CUDA';
    if ($('generation-ipadapter-faceid-lora-strength')) $('generation-ipadapter-faceid-lora-strength').value = draft.ipadapter_faceid_lora_strength || '0.75';
    if ($('generation-ipadapter-weight')) $('generation-ipadapter-weight').value = draft.ipadapter_weight || '1.0';
    if ($('generation-ipadapter-weight-faceidv2')) $('generation-ipadapter-weight-faceidv2').value = draft.ipadapter_weight_faceidv2 || '1.0';
    if ($('generation-ipadapter-weight-type')) $('generation-ipadapter-weight-type').value = draft.ipadapter_weight_type || 'linear';
    if ($('generation-ipadapter-combine-embeds')) $('generation-ipadapter-combine-embeds').value = draft.ipadapter_combine_embeds || 'concat';
    if ($('generation-ipadapter-embeds-scaling')) $('generation-ipadapter-embeds-scaling').value = draft.ipadapter_embeds_scaling || 'V only';
    if ($('generation-ipadapter-start-at')) $('generation-ipadapter-start-at').value = draft.ipadapter_start_at || '0';
    if ($('generation-ipadapter-end-at')) $('generation-ipadapter-end-at').value = draft.ipadapter_end_at || '1';
    if ($('generation-refine-profile')) $('generation-refine-profile').value = draft.refine_profile || 'custom';
    if ($('generation-refine-enabled')) $('generation-refine-enabled').value = draft.refine_enabled || 'false';
    if ($('generation-refine-strategy')) $('generation-refine-strategy').value = draft.refine_strategy || 'standard';
    if ($('generation-refine-mode')) $('generation-refine-mode').value = draft.refine_mode || 'latent';
    if ($('generation-refine-resize-method')) $('generation-refine-resize-method').value = draft.refine_resize_method || 'lanczos';
    if ($('generation-refine-upscaler')) $('generation-refine-upscaler').value = draft.refine_upscaler || '';
    if ($('generation-refine-scale')) $('generation-refine-scale').value = draft.refine_scale || '1.5';
    if ($('generation-refine-scale-range')) $('generation-refine-scale-range').value = draft.refine_scale || '1.5';
    if ($('generation-refine-steps')) $('generation-refine-steps').value = draft.refine_steps || '12';
    if ($('generation-refine-steps-range')) $('generation-refine-steps-range').value = draft.refine_steps || '12';
    if ($('generation-refine-denoise')) $('generation-refine-denoise').value = draft.refine_denoise || '0.12';
    if ($('generation-refine-denoise-range')) $('generation-refine-denoise-range').value = draft.refine_denoise || '0.12';
    if ($('generation-refine-cfg')) $('generation-refine-cfg').value = draft.refine_cfg || '5.2';
    if ($('generation-refine-sampler')) $('generation-refine-sampler').value = draft.refine_sampler || '';
    if ($('generation-refine-scheduler')) $('generation-refine-scheduler').value = draft.refine_scheduler || '';
    if ($('generation-refine-tiled-vae')) $('generation-refine-tiled-vae').value = draft.refine_tiled_vae || 'true';
    if ($('generation-refine-tile-size')) $('generation-refine-tile-size').value = draft.refine_tile_size || '512';
    if ($('generation-refine-tile-overlap')) $('generation-refine-tile-overlap').value = draft.refine_tile_overlap || '64';
    if ($('generation-image-upscale-profile')) $('generation-image-upscale-profile').value = draft.image_upscale_profile || 'preserve_2x';
    if ($('generation-image-upscale-model')) $('generation-image-upscale-model').value = draft.image_upscale_model || '';
    if ($('generation-image-upscale-scale')) $('generation-image-upscale-scale').value = draft.image_upscale_scale || '2.0';
    if ($('generation-image-upscale-resize-method')) $('generation-image-upscale-resize-method').value = draft.image_upscale_resize_method || 'lanczos';
    if ($('generation-image-upscale-restore-assist')) $('generation-image-upscale-restore-assist').value = draft.image_upscale_restore_assist || 'off';
    if ($('generation-image-upscale-restore-model')) $('generation-image-upscale-restore-model').value = draft.image_upscale_restore_model || '';
    if ($('generation-image-upscale-restore-fidelity')) $('generation-image-upscale-restore-fidelity').value = draft.image_upscale_restore_fidelity || '0.65';
    if ($('generation-image-upscale-restore-detection')) $('generation-image-upscale-restore-detection').value = draft.image_upscale_restore_detection || 'retinaface_resnet50';
    if ($('generation-supir-enabled')) $('generation-supir-enabled').value = draft.supir_enabled || 'false';
    if ($('generation-supir-model')) $('generation-supir-model').value = draft.supir_model || '';
    if ($('generation-supir-sdxl-model')) $('generation-supir-sdxl-model').value = draft.supir_sdxl_model || '';
    if ($('generation-supir-scale')) $('generation-supir-scale').value = draft.supir_scale || '1.5';
    if ($('generation-supir-steps')) $('generation-supir-steps').value = draft.supir_steps || '45';
    if ($('generation-supir-restoration-scale')) $('generation-supir-restoration-scale').value = draft.supir_restoration_scale || '-1';
    if ($('generation-supir-cfg-scale')) $('generation-supir-cfg-scale').value = draft.supir_cfg_scale || '4.0';
    if ($('generation-supir-control-scale')) $('generation-supir-control-scale').value = draft.supir_control_scale || '1.0';
    if ($('generation-supir-color-fix-type')) $('generation-supir-color-fix-type').value = draft.supir_color_fix_type || 'Wavelet';
    if ($('generation-supir-tiled-vae')) $('generation-supir-tiled-vae').value = draft.supir_tiled_vae || 'true';
    if ($('generation-supir-encoder-tile-size')) $('generation-supir-encoder-tile-size').value = draft.supir_encoder_tile_size || '512';
    if ($('generation-supir-decoder-tile-size')) $('generation-supir-decoder-tile-size').value = draft.supir_decoder_tile_size || '64';
    if ($('generation-supir-a-prompt')) $('generation-supir-a-prompt').value = draft.supir_a_prompt || 'high quality, detailed';
    if ($('generation-supir-n-prompt')) $('generation-supir-n-prompt').value = draft.supir_n_prompt || 'bad quality, blurry, messy';
    if ($('generation-output-root')) $('generation-output-root').value = draft.output_root || $('generation-output-root').value || '';
    if ($('generation-output-category') && draft.output_category) $('generation-output-category').value = draft.output_category;
    if ($('generation-wildcard-root')) $('generation-wildcard-root').value = draft.wildcard_root || $('generation-wildcard-root').value || '';
    if ($('generation-wildcard-enabled')) $('generation-wildcard-enabled').checked = draft.wildcard_enabled !== false;
    if ($('generation-wildcard-file')) $('generation-wildcard-file').value = draft.wildcard_selected_file || '';
    if ($('generation-wildcard-target')) $('generation-wildcard-target').value = draft.wildcard_target || 'positive';
    if ($('generation-wildcard-auto-resolve')) $('generation-wildcard-auto-resolve').checked = draft.wildcard_auto_resolve !== false;
    if ($('generation-wildcard-use-seed')) $('generation-wildcard-use-seed').checked = !!draft.wildcard_use_seed;
    if ($('generation-wildcard-preview-count')) $('generation-wildcard-preview-count').value = draft.wildcard_preview_count || '3';
    if ($('generation-wildcard-queue-count')) $('generation-wildcard-queue-count').value = draft.wildcard_queue_count || '3';
    if ($('generation-workflow-notes')) $('generation-workflow-notes').value = draft.notes || '';

    const loraWrap = $('generation-lora-extra-list');
    if (loraWrap) {
      loraWrap.innerHTML = '';
      const mergedLoras = [];
      const incomingLoras = Array.isArray(draft.loras) ? draft.loras : [];
      if (incomingLoras.length) {
        incomingLoras.forEach(item => mergedLoras.push(item));
      } else if (trim(draft.lora_name || '')) {
        mergedLoras.push({ uid:'legacy_primary', enabled:draft.lora_enabled !== false, name:draft.lora_name || '', strength:draft.lora_strength || '0.8', target:draft.lora_target || 'both' });
      }
      const seenLoras = new Set();
      mergedLoras.forEach(item => {
        const name = item?.name || '';
        const strength = item?.strength || 0.8;
        const target = item?.target || 'both';
        const apply_to = item?.apply_to || item?.applyTo || 'global';
        const key = `${String(name).trim().toLowerCase()}::${String(strength)}::${String(target)}::${String(apply_to)}`;
        if (!String(name).trim() || seenLoras.has(key)) return;
        seenLoras.add(key);
        loraWrap.appendChild(createGenerationLoraRow({ uid:item.uid || '', enabled:item.enabled !== false, name, strength, target, apply_to }));
      });
    }
    const controlWrap = $('generation-controlnet-extra-list');
    if (controlWrap) {
      controlWrap.innerHTML = '';
      (Array.isArray(draft.controlnet_units) ? draft.controlnet_units : []).forEach(item => controlWrap.appendChild(createGenerationControlnetRow({ uid:item.uid || '', enabled:item.enabled !== false, unit:item.unit || 'auto', preprocessor:item.preprocessor || 'none', model:item.model || '', strength:item.strength || 1.0 })));
    }
    const ipadapterWrap = $('generation-ipadapter-extra-list');
    if (ipadapterWrap) {
      ipadapterWrap.innerHTML = '';
      (Array.isArray(draft.ipadapter_units) ? draft.ipadapter_units : []).forEach(item => ipadapterWrap.appendChild(createGenerationIpAdapterRow({ uid:item.uid || '', enabled:item.enabled !== false, mode:item.mode || 'standard', model:item.model || '', clip_vision:item.clip_vision || '', faceid_preset:item.faceid_preset || 'FACEID PLUS V2', faceid_provider:item.faceid_provider || 'CUDA', faceid_lora_strength:item.faceid_lora_strength || 0.75, weight:item.weight || 1.0, weight_faceidv2:item.weight_faceidv2 || 1.0, weight_type:item.weight_type || 'linear', combine_embeds:item.combine_embeds || 'concat', embeds_scaling:item.embeds_scaling || 'V only', start_at:item.start_at || 0, end_at:item.end_at || 1 })));
    }

    populateGenerationSizePresetSelect(draft.size_preset || 'custom');
    if (window.NeoImageState?.restoreWorkflowState && draft.workflow_state) {
      window.NeoImageState.restoreWorkflowState(draft.workflow_state, { reason: 'draft_restore_final_sync' });
    }
    syncGenerationSizePresetSelectionFromInputs();
    setGenerationSeedLock(!!draft.seed_locked);
    refreshGenerationDynamicOptions();
    syncGenerationModeUI();
    syncGenerationRefineUI();
    syncGenerationImageUpscaleUI();
    updateGenerationOutputDestinationPreview(trim($('generation-seed')?.value || '') || '[seed]');
    refreshGenerationCounters();
    renderGenerationPromptConditioning();
    renderGenerationExperimentalMode();
    refreshGenerationSourceImageInfo();
    renderGenerationOutpaintSummary();
    syncGenerationIdentityUI();
    updatePrimaryGenerationLoraSummary();
    applyGenerationLoraCompatibilityFilter({ refreshLibrary:true, force:true }).catch(() => {});
    const restoredLoraName = trim(document.querySelector('#generation-lora-extra-list .generation-lora-name')?.value || '');
    if (restoredLoraName) inspectGenerationLoraByName(restoredLoraName).catch(() => {});
    updatePrimaryGenerationControlnetSummary();
    updateGenerationUnitIndices();
    loadGenerationWildcardCatalog(true).catch(() => {});
    loadGenerationDetailerModels(true).catch(() => {});
    refreshGenerationSectionStateBadges();
    scheduleGenerationSectionBadgeRefresh();
  } finally {
    generationDraftApplyInProgress = false;
  }
}

window.NeoGenerationDraftState.buildGenerationResetDraft = function buildGenerationResetDraft({ preserveOutput=true } = {}) {
  const draft = {
    version: 6,
    updated_at: Date.now(),
    workflow_type: 'txt2img',
    checkpoint: '',
    vae: '',
    sampler: 'euler',
    scheduler: 'normal',
    width: '1024',
    height: '1024',
    size_preset: 'builtin:sdxl_square_1024',
    steps: '28',
    batch_size: '1',
    cfg: '5.2',
    denoise: '1.0',
    seed: '-1',
    seed_locked: false,
    positive: '',
    negative: '',
    prompt_conditioning_mode: 'raw',
    clip_skip: '1',
    experimental_mode: 'off',
    advanced_slot_a: 'none',
    advanced_slot_b: 'none',
    selected_style: '',
    style_enabled: true,
    active_styles: [],
    style_name: '',
    style_positive: '',
    style_negative: '',
    source_resize_mode: 'native',
    inpaint_target: 'masked',
    inpaint_context: 'full_image',
    inpaint_backend: 'standard',
    composition_guide_type: 'none',
    composition_source_mode: 'source_image',
    grow_mask_by: '6',
    mask_feather: '0',
    outpaint_left: '0',
    outpaint_top: '0',
    outpaint_right: '0',
    outpaint_bottom: '0',
    outpaint_feather: '24',
    outpaint_preset: 'custom',
    outpaint_anchor: 'center',
    detailer_enabled: false,
    detailer_provider: 'ultralytics',
    detailer_mode: 'face',
    detailer_detector_type: 'bbox',
    detailer_model: '',
    detailer_sam_model: '',
    detailer_custom_classes: '',
    detailer_confidence: '0.35',
    detailer_topk: '0',
    detailer_bbox_grow: '12',
    detailer_mask_blur: '4',
    detailer_denoise: '0.12',
    detailer_steps: '12',
    detailer_use_main_prompt: true,
    detailer_force_inpaint: true,
    detailer_positive: '',
    detailer_negative: '',
    detailer_order: 'auto',
    detailer_start_index: '1',
    detailer_count: '1',
    detailer_min_area: '0',
    detailer_max_area: '0',
    detailer_reference_lock: 'none',
    detailer_target_mode: 'auto_detect',
    detailer_manual_boxes: '',
    detailer_custom_detector_root: '',
    detailer_custom_sam_root: '',
    detailer_sam_preset: '',
    detailer_passes: [],
    lora_enabled: true,
    lora_name: '',
    lora_strength: '0.8',
    loras: [],
    controlnet_enabled: true,
    controlnet_name: '',
    controlnet_unit: 'auto',
    controlnet_preprocessor: 'none',
    controlnet_strength: '1.0',
    controlnet_units: [],
    ipadapter_enabled: false,
    ipadapter_mode: 'standard',
    ipadapter_name: '',
    ipadapter_clip_vision: '',
    ipadapter_faceid_preset: 'FACEID PLUS V2',
    ipadapter_faceid_provider: 'CUDA',
    ipadapter_faceid_lora_strength: '0.75',
    ipadapter_weight: '1.0',
    ipadapter_weight_faceidv2: '1.0',
    ipadapter_weight_type: 'linear',
    ipadapter_combine_embeds: 'concat',
    ipadapter_embeds_scaling: 'V only',
    ipadapter_start_at: '0',
    ipadapter_end_at: '1',
    ipadapter_units: [],
    refine_enabled: 'false',
    refine_strategy: 'standard',
    refine_mode: 'latent',
    refine_resize_method: 'lanczos',
    refine_upscaler: '',
    refine_scale: '1.5',
    refine_steps: '12',
    refine_denoise: '0.12',
    refine_cfg: '5.2',
    refine_sampler: '',
    refine_scheduler: '',
    refine_tiled_vae: 'true',
    refine_tile_size: '512',
    refine_tile_overlap: '64',
    image_upscale_profile: 'preserve_2x',
    image_upscale_model: '',
    image_upscale_scale: '2.0',
    image_upscale_resize_method: 'lanczos',
    image_upscale_restore_assist: 'off',
    image_upscale_restore_model: '',
    image_upscale_restore_fidelity: '0.65',
    image_upscale_restore_detection: 'retinaface_resnet50',
    supir_enabled: 'false',
    supir_model: '',
    supir_sdxl_model: '',
    supir_scale: '1.5',
    supir_steps: '45',
    supir_restoration_scale: '-1',
    supir_cfg_scale: '4.0',
    supir_control_scale: '1.0',
    supir_color_fix_type: 'Wavelet',
    supir_tiled_vae: 'true',
    supir_encoder_tile_size: '512',
    supir_decoder_tile_size: '64',
    supir_a_prompt: 'high quality, detailed',
    supir_n_prompt: 'bad quality, blurry, messy',
    output_root: preserveOutput ? ($('generation-output-root')?.value || '') : '',
    output_category: preserveOutput ? ($('generation-output-category')?.value || 'Uncategorized') : 'Uncategorized',
    wildcard_root: $('generation-wildcard-root')?.value || '',
    wildcard_enabled: true,
    wildcard_selected_file: '',
    wildcard_target: 'positive',
    wildcard_auto_resolve: true,
    wildcard_use_seed: false,
    wildcard_preview_count: '3',
    wildcard_queue_count: '3',
    notes: '',
  };
  draft.workflow_state = {
    schema_version: 1,
    owner: 'NeoImageState',
    raw_state: { mode: 'txt2img', workflow_type: 'txt2img', source_kind: 'none', source_id: '', output_policy: 'new_current_run' },
    effective_state: { mode: 'txt2img', workflow_type: 'txt2img', source_kind: 'none', source_id: '', output_policy: 'new_current_run', validation_status: 'valid' },
    transition: { switch_reason: 'reset_draft', restored_by: 'setGenerationWorkflowMode' },
    version: 'phase_i_save_restore_metadata_v1',
  };
  draft._neo_workflow_state = draft.workflow_state;
  return sanitizeGenerationDraftState(draft);
}

