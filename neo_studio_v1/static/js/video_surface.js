(function(){
  const STORAGE_KEY = 'neo-studio-video-draft';
  const LEGACY_STORAGE_KEYS = ['neo-studio-video-balanced-draft', 'neo-studio-video-skeleton-draft'];
  const LEGACY_MODE_MAP = { txt2video:'t2v', img2video:'i2v', extend:'i2v' };
  const LEGACY_PROFILE_MAP = { wan:'wan22_5b_balanced', ltxv:'wan22_5b_balanced', hunyuan:'wan22_5b_balanced' };
  const FALLBACK_CONTRACT = {
    schema_version: 1,
    defaults: { mode:'t2v', profile:'wan22_5b_balanced', duration_seconds:5, fps:16, size_preset:'832x480', post_process:[], post_pipeline_template:'generate_only', seed:'' },
    modes: [
      { id:'t2v', label:'Text to Video', allowed_profiles:['wan22_5b_balanced','wan22_14b_t2v_quality','raw_free'], requires_source_image:false },
      { id:'i2v', label:'Image to Video', allowed_profiles:['wan22_5b_balanced','wan22_14b_i2v_quality','raw_free'], requires_source_image:true },
    ],
    profiles: [
      { id:'wan22_5b_balanced', label:'Balanced / Low VRAM', technical_label:'Wan 2.2 5B Balanced', quality_tier:'balanced', supports_modes:['t2v','i2v'], vram_class:'light', notes:'Default lower-VRAM path for both Text to Video and Image to Video.' },
      { id:'wan22_14b_t2v_quality', label:'High Quality · Text to Video', technical_label:'Wan 2.2 14B T2V Quality', quality_tier:'quality', supports_modes:['t2v'], vram_class:'heavy', notes:'Higher-quality Text to Video path with heavier runtime cost.' },
      { id:'wan22_14b_i2v_quality', label:'High Quality · Image to Video', technical_label:'Wan 2.2 14B I2V Quality', quality_tier:'quality', supports_modes:['i2v'], vram_class:'heavy', notes:'Higher-quality Image to Video path with heavier runtime cost.' },
      { id:'raw_free', label:'Raw / Free', technical_label:'Manual engine + asset routing', quality_tier:'flex', supports_modes:['t2v','i2v'], vram_class:'medium', notes:'Free routing profile. The selected backend engine and manual asset picks decide the workflow lane instead of the old balanced/quality presets.' },
    ],
    post_process: [
      { id:'repair', label:'Repair' },
      { id:'upscale', label:'Upscale' },
      { id:'interpolate', label:'Interpolate' },
    ],
    post_pipeline_templates: [
      { id:'generate_only', label:'Generate only', steps:[] },
      { id:'generate_upscale', label:'Generate → Upscale', steps:['upscale'] },
      { id:'generate_repair_upscale', label:'Generate → Repair → Upscale', steps:['repair','upscale'] },
      { id:'generate_repair_upscale_interpolate', label:'Generate → Repair → Upscale → Interpolate', steps:['repair','upscale','interpolate'] },
    ],
    runtime_status: [
      { id:'draft', label:'Draft' },
      { id:'validating', label:'Validating' },
      { id:'queued', label:'Queued' },
      { id:'running', label:'Running' },
      { id:'completed', label:'Completed' },
      { id:'failed', label:'Failed' },
      { id:'cancelled', label:'Cancelled' },
    ],
  };

  let activeJobId = '';
  let lastVideoJobId = '';
  let pollTimer = null;
  let requestInFlight = false;
  let lastHistory = [];
  let videoProgressSocket = null;
  let videoProgressClientId = '';
  let videoProgressPromptId = '';
  let videoProgressStartedAt = 0;
  let videoLastProgressPercent = 0;
  let savedVideoPresets = [];
  let savedVideoPresetSummaries = [];
  let defaultVideoPresetId = '';
  let activeVideoPresetId = '';
  let videoAdapterCatalog = [];
  let videoAdapterPairPresets = [];
  let adapterCatalogLoaded = false;
  let videoBackendAssetCatalog = {};
  let backendAssetCatalogLoaded = false;
  let currentVideoSupportTab = 'generate_setup';
  let videoPreviewState = { url:'', jobId:'', filename:'', title:'', source:'', note:'', loop:true };
  let videoBackendAssetWarnings = [];
  let lastKnownVideoBackendConnected = null;
  let lastKnownVideoBackendProfileId = '';
  const VIDEO_STALE_ASSET_ALIASES = {
    'umt5_xxl_fp8_e4m3fn_scaled.safetensors': ['umt5-xxl-enc-fp8_e4m3fn.safetensors'],
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': ['umt5_xxl_fp8_e4m3fn_scaled.safetensors'],
    'wan2.2_vae.safetensors': ['wan_2.1_vae.safetensors', 'ae.safetensors'],
    'wan_2.1_vae.safetensors': ['wan2.2_vae.safetensors', 'ae.safetensors'],
  };
  const VIDEO_RUN_COPY_COMPAT = ['Generate high-quality clip', 'Generate balanced clip'];
  const VIDEO_SIZE_PRESETS = { '832x480':{ width:832, height:480 }, '1024x576':{ width:1024, height:576 }, '576x1024':{ width:576, height:1024 } };
  const VIDEO_AUTO_SOURCE_FIT_LIMITS = { balanced:{ maxPixels:832*480, maxLongEdge:832 }, quality:{ maxPixels:1024*576, maxLongEdge:1024 } };
  let videoSourceImageMeta = { width:0, height:0 };

  function $(id){ return document.getElementById(id); }
  function getVideoContract(){ return window.NEO_STUDIO_BOOT?.videoContract || FALLBACK_CONTRACT; }
  function defaults(){ return getVideoContract().defaults || FALLBACK_CONTRACT.defaults; }
  function adapterSupport(){ return getVideoContract().advanced_adapter_support || { available_profiles:['wan22_5b_balanced','wan22_14b_t2v_quality','wan22_14b_i2v_quality'], single_slots:['single_adapter'], paired_slots:['high_noise_adapter','low_noise_adapter'], default_strength:0.8, supports_single_adapter:true, supports_pair_presets:true, profile_modes:{ wan22_5b_balanced:{ mode:'single', label:'Single LoRA / adapter', supports_pair_presets:false }, wan22_14b_t2v_quality:{ mode:'paired', label:'Paired LoRAs / adapters', supports_pair_presets:true }, wan22_14b_i2v_quality:{ mode:'paired', label:'Paired LoRAs / adapters', supports_pair_presets:true } } }; }
  function backendAssetDefaults(){ return getVideoContract().backend_asset_defaults || { balanced:{ unet_name:'wan2.2_ti2v_5B_fp16.safetensors', clip_name:'umt5_xxl_fp8_e4m3fn_scaled.safetensors', vae_name:'wan2.2_vae.safetensors' }, quality_t2v:{ high_noise_unet_name:'wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors', low_noise_unet_name:'wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors', clip_name:'umt5_xxl_fp8_e4m3fn_scaled.safetensors', vae_name:'wan_2.1_vae.safetensors' }, quality_i2v:{ high_noise_unet_name:'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors', low_noise_unet_name:'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors', clip_name:'umt5_xxl_fp8_e4m3fn_scaled.safetensors', vae_name:'wan_2.1_vae.safetensors' }, gguf:{ available:false, detected_unet_models:[], routing:'native_only', note:'Video can detect Wan GGUF UNET assets when the backend exposes UnetLoaderGGUF choices through object_info. Encoders and VAEs still stay on the native Wan path.' } }; }
  function backendAssetCatalog(){ return videoBackendAssetCatalog && typeof videoBackendAssetCatalog === 'object' ? videoBackendAssetCatalog : {}; }
  function defaultBalancedBackendAssets(){ return backendAssetDefaults().balanced || {}; }
  function defaultQualityBackendAssets(profileValue = currentProfileValue()){ const clean = normalizeProfile(profileValue); if (clean === 'wan22_14b_i2v_quality') return (backendAssetDefaults().quality_i2v || {}); if (clean === 'raw_free') return currentModeValue() === 'i2v' ? (backendAssetDefaults().quality_i2v || {}) : (backendAssetDefaults().quality_t2v || {}); return (backendAssetDefaults().quality_t2v || {}); }
  function assetSelection(selectId, fallback=''){ return String($(selectId)?.value || fallback || '').trim(); }
  function normalizeVideoAssetKey(value){ return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ''); }
  function resolveVideoAssetAlias(value, liveValues){
    const clean = String(value || '').trim();
    if (!clean) return '';
    const choices = Array.isArray(liveValues) ? liveValues.map(item => String(item || '').trim()).filter(Boolean) : [];
    if (!choices.length) return clean;
    if (choices.includes(clean)) return clean;
    const aliasTargets = VIDEO_STALE_ASSET_ALIASES[String(clean).toLowerCase()] || [];
    for (const candidate of aliasTargets){
      const hit = choices.find(item => item === candidate);
      if (hit) return hit;
    }
    const normalized = normalizeVideoAssetKey(clean).replace(/scaled/g, '');
    const fuzzyMatches = choices.filter(item => normalizeVideoAssetKey(item).replace(/scaled/g, '') === normalized);
    return fuzzyMatches.length === 1 ? fuzzyMatches[0] : '';
  }
  function isLiveVideoAssetChoice(value, liveValues){
    const clean = String(value || '').trim();
    return !!clean && Array.isArray(liveValues) && liveValues.some(item => String(item || '').trim() === clean);
  }
  function setStatusSafe(id, text, level=''){ if (typeof window.setStatus === 'function') window.setStatus(id, text, level); }
  function makeVideoClientId(){ try { if (window.crypto?.randomUUID) return window.crypto.randomUUID(); } catch (_) {} return `video_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`; }
  function setValue(id, value, eventNames = ['input', 'change']) { const el = $(id); if (!el) return; el.value = value == null ? '' : String(value); eventNames.forEach(name => el.dispatchEvent(new Event(name, { bubbles:true }))); }
  function escapeHtml(value){ return String(value || '').replace(/[&<>'"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[m])); }
  function normalizeMode(value){ const clean = String(value || '').trim().toLowerCase(); return LEGACY_MODE_MAP[clean] || clean || defaults().mode || 't2v'; }
  function normalizeProfile(value){ const clean = String(value || '').trim().toLowerCase(); return LEGACY_PROFILE_MAP[clean] || clean || defaults().profile || 'wan22_5b_balanced'; }
  function allModes(){ return Array.isArray(getVideoContract().modes) ? getVideoContract().modes : FALLBACK_CONTRACT.modes; }
  function allProfiles(){ return Array.isArray(getVideoContract().profiles) ? getVideoContract().profiles : FALLBACK_CONTRACT.profiles; }
  function allStatuses(){ return Array.isArray(getVideoContract().runtime_status) ? getVideoContract().runtime_status : FALLBACK_CONTRACT.runtime_status; }
  function allPostPipelineTemplates(){ return Array.isArray(getVideoContract().post_pipeline_templates) ? getVideoContract().post_pipeline_templates : FALLBACK_CONTRACT.post_pipeline_templates; }
  function findPostPipelineTemplate(id){ const clean = String(id || '').trim() || String(defaults().post_pipeline_template || 'generate_only'); return allPostPipelineTemplates().find(item => item.id === clean) || allPostPipelineTemplates()[0] || FALLBACK_CONTRACT.post_pipeline_templates[0]; }
  function currentPostPipelineTemplateId(){ return String($('video-post-pipeline-template')?.value || defaults().post_pipeline_template || 'generate_only').trim() || 'generate_only'; }
  function currentPostPipelineTemplate(){ return findPostPipelineTemplate(currentPostPipelineTemplateId()); }
  function currentPostProcessSelection(){ return Array.isArray(currentPostPipelineTemplate()?.steps) ? [...currentPostPipelineTemplate().steps] : []; }

  function setVideoSupportTab(tabId = 'generate_setup'){
    const clean = String(tabId || 'generate_setup').trim() || 'generate_setup';
    currentVideoSupportTab = clean;
    document.querySelectorAll('[data-video-support-tab]').forEach((button) => {
      const active = String(button.getAttribute('data-video-support-tab') || '').trim() === clean;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('[data-video-support-panel]').forEach((panel) => {
      const active = String(panel.getAttribute('data-video-support-panel') || '').trim() === clean;
      panel.hidden = !active;
      panel.classList.toggle('active', active);
    });
  }

  function bindVideoSupportTabs(){
    const buttons = Array.from(document.querySelectorAll('[data-video-support-tab]'));
    if (!buttons.length) return;
    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        setVideoSupportTab(button.getAttribute('data-video-support-tab') || 'generate_setup');
      });
    });
    setVideoSupportTab(currentVideoSupportTab);
  }
  function findMode(mode){ const clean = normalizeMode(mode); return allModes().find(item => item.id === clean) || allModes()[0] || FALLBACK_CONTRACT.modes[0]; }
  function currentModeValue(){ return normalizeMode($('video-mode')?.value || defaults().mode); }
  function currentModeDefinition(){ return findMode(currentModeValue()); }
  function currentModeLabel(){ return $('video-mode')?.selectedOptions?.[0]?.textContent?.trim() || currentModeDefinition().label || 'Text to Video'; }
  function allowedProfilesForMode(mode){ const current = findMode(mode); const allowed = new Set(current?.allowed_profiles || []); const rawSelected = normalizeProfile($('video-profile')?.value || '') === 'raw_free'; if (!freeAssetModeEnabled() && !rawSelected) allowed.delete('raw_free'); const profiles = allProfiles().filter(item => allowed.has(item.id)); return profiles.length ? profiles : [allProfiles()[0] || FALLBACK_CONTRACT.profiles[0]]; }
  function currentProfileValue(){ return normalizeProfile($('video-profile')?.value || defaults().profile); }
  function isRawFreeProfile(profileValue = currentProfileValue()){ return normalizeProfile(profileValue) === 'raw_free'; }
  function currentProfileDefinition(){ const allowed = allowedProfilesForMode(currentModeValue()); const current = allowed.find(item => item.id === currentProfileValue()); return current || allProfiles().find(item => item.id === currentProfileValue()) || allowed[0] || FALLBACK_CONTRACT.profiles[0]; }

  function freeAssetModeEnabled(){ return !!($('video-free-assets-mode')?.checked); }
  function selectedVideoBackendEngineOverride(){ return String($('video-backend-engine-override')?.value || 'auto').trim().toLowerCase() || 'auto'; }
  function displayProfileLabel(profile){ return String(profile?.quality_tier || '').toLowerCase() === 'quality' ? 'High Quality' : 'Balanced / Low VRAM'; }
  function currentProfileLabel(){ return $('video-profile')?.selectedOptions?.[0]?.textContent?.trim() || displayProfileLabel(currentProfileDefinition()); }
  function findStatusDefinition(state){ const clean = String(state || '').trim().toLowerCase() || 'queued'; return allStatuses().find(item => String(item?.id || '').trim().toLowerCase() === clean) || null; }
  function statusLabel(state){ return findStatusDefinition(state)?.label || (String(state || '').trim() ? String(state || '').trim().charAt(0).toUpperCase() + String(state || '').trim().slice(1) : 'Queued'); }
  function workflowTitle(workflowType){ const clean = String(workflowType || '').trim(); if (clean === 'video_upscale') return 'Upscale lane'; if (clean === 'video_repair') return 'Repair lane'; if (clean === 'video_interpolate') return 'Interpolate lane'; return 'Generation'; }
  function stageLabel(stage){ const clean = String(stage || '').trim().toLowerCase(); if (clean === 'repair') return 'Repair'; if (clean === 'upscale') return 'Upscale'; if (clean === 'interpolate') return 'Interpolate'; return 'Generate'; }
  function stateChipClass(state){ const clean = String(state || '').trim().toLowerCase() || 'queued'; if (clean === 'completed') return 'state-connected'; if (clean === 'running') return 'state-busy'; if (clean === 'failed') return 'state-error'; if (clean === 'cancelled') return 'state-degraded'; return 'state-checking'; }
  function statusSnapshot(job){
    const row = job && typeof job === 'object' ? job : {};
    const state = String(row.status || row.state || 'queued').trim().toLowerCase() || 'queued';
    const payload = row.payload && typeof row.payload === 'object' ? row.payload : {};
    const runtime = row.video_runtime && typeof row.video_runtime === 'object' ? row.video_runtime : {};
    const snap = runtime.status_snapshot && typeof runtime.status_snapshot === 'object' ? runtime.status_snapshot : {};
    const progress = row.progress && typeof row.progress === 'object' ? row.progress : {};
    const pipeline = runtime.post_pipeline && typeof runtime.post_pipeline === 'object' ? runtime.post_pipeline : { enabled:false, label:'Generate only', current_stage:'generate', current_stage_label:'Generate', next_stage_label:'' };
    const workflowType = String(payload.workflow_type || '').trim() || 'video_generation';
    const workflowLabel = String(snap.workflow_label || workflowTitle(workflowType)).trim() || workflowTitle(workflowType);
    const currentStageLabel = String(snap.current_stage_label || pipeline.current_stage_label || stageLabel(pipeline.current_stage || 'generate')).trim() || 'Generate';
    const progressLabel = String(snap.progress_label || progress.detail || '').trim() || (state === 'running' ? 'Rendering' : state === 'queued' ? 'Waiting in queue' : state === 'completed' ? 'Finished' : state === 'cancelled' ? 'Stopped' : state === 'failed' ? 'Failed' : 'Queued');
    const stateLabel = String(snap.state_label || statusLabel(state)).trim() || statusLabel(state);
    return { state, stateLabel, workflowLabel, currentStageLabel, progressLabel, chipClass: stateChipClass(state) };
  }
  function currentPresetLabel(){ return $('video-preset-active-badge')?.textContent?.trim() || 'Manual setup'; }
  function sourceImageFile(){ return $('video-source-image-file')?.files?.[0] || null; }
  function isQualityProfile(){ const tier = String(currentProfileDefinition()?.quality_tier || '').toLowerCase(); if (tier === 'quality') return true; if (isRawFreeProfile()) return selectedVideoBackendEngine() !== 'kijai_wrapper'; return false; }
  function isTerminalState(state){ return ['completed','failed','cancelled'].includes(String(state || '').trim().toLowerCase()); }
  function qualityPromptStyle(){ return $('video-quality-style')?.value || ''; }
  function qualityPromptCamera(){ return $('video-quality-camera')?.value || ''; }
  function numberOr(value, fallback){ const num = Number(value); return Number.isFinite(num) ? num : fallback; }
  function safeStorageGet(key){ try { return window.localStorage.getItem(key) || ''; } catch(_) { return ''; } }
  function savedVideoPresetSelectionId(){ return String($('video-saved-preset-select')?.value || '').trim(); }
  function currentSavedVideoPresetCategory(){ return String($('video-saved-preset-category')?.value || 'custom').trim() || 'custom'; }
  function findSavedVideoPreset(id){ const clean = String(id || '').trim(); return savedVideoPresets.find(item => String(item?.preset_id || item?.id || '').trim() === clean) || null; }
  function findSavedVideoPresetSummary(id){ const clean = String(id || '').trim(); return savedVideoPresetSummaries.find(item => String(item?.preset_id || '').trim() === clean) || null; }

  function workspacePresetStartupRef(){ return safeStorageGet('neo-video-workspace-preset-active') || safeStorageGet('neo-video-workspace-preset-default') || ''; }
  function adapterPairPresetSelectionId(){ return String($('video-adapter-preset-select')?.value || '').trim(); }
  function findAdapterPairPreset(id){ const clean = String(id || '').trim(); return videoAdapterPairPresets.find(item => String(item?.preset_id || item?.id || '').trim() === clean) || null; }
  function adapterCapability(profileValue = currentProfileValue()){
    const clean = normalizeProfile(profileValue);
    if (clean === 'raw_free') {
      const wrapper = selectedVideoBackendEngine(clean) === 'kijai_wrapper';
      return wrapper
        ? { mode:'paired', supports_pair_presets:false, unsupported_reason:'Kijai Wrapper routing in this build does not support Neo adapter injection yet.' }
        : { mode:'paired', supports_pair_presets:true };
    }
    const modes = adapterSupport().profile_modes || {};
    return modes[clean] || { mode: clean === 'wan22_5b_balanced' ? 'single' : 'paired', supports_pair_presets: clean !== 'wan22_5b_balanced' };
  }
  function adapterModeForProfile(profileValue = currentProfileValue()){ return String(adapterCapability(profileValue).mode || (normalizeProfile(profileValue) === 'wan22_5b_balanced' ? 'single' : 'paired')).trim() || 'single'; }
  function adapterUsesPairedMode(profileValue = currentProfileValue()){ return adapterModeForProfile(profileValue) === 'paired'; }
  function adapterSupportsPairPresets(profileValue = currentProfileValue()){ return !!adapterCapability(profileValue).supports_pair_presets; }
  function adapterSingleValue(){ return String($('video-adapter-single')?.value || '').trim(); }
  function adapterHighNoiseValue(){ return String($('video-adapter-high-noise')?.value || '').trim(); }
  function adapterLowNoiseValue(){ return String($('video-adapter-low-noise')?.value || '').trim(); }
  function adapterStrengthValue(){ const fallback = Number(adapterSupport().default_strength || 0.8); const qualityField = $('video-adapter-strength-quality'); const baseField = $('video-adapter-strength'); const value = Number((qualityField && !qualityField.closest('[hidden]') && qualityField.value) || baseField?.value); if (!Number.isFinite(value)) return fallback; return Math.max(0, Math.min(2, Math.round(value * 100) / 100)); }
  function rememberedAdaptersEnabled(){ return !!$('video-adapters-enabled')?.checked; }
  function supportsAdaptersForProfile(profileValue = currentProfileValue()){
    const clean = normalizeProfile(profileValue);
    if (clean === 'raw_free') return selectedVideoBackendEngine(clean) !== 'kijai_wrapper';
    return (adapterSupport().available_profiles || []).includes(clean);
  }
  function videoBackendSession(){
    return typeof window.getBackendRoleState === 'function'
      ? (window.getBackendRoleState('video') || {})
      : {};
  }
  function videoBackendConnected(){
    return !!videoBackendSession().connected;
  }
  function videoWorkflowType(job){
    const payload = job && typeof job.payload === 'object' ? job.payload : {};
    return String(payload.workflow_type || 'video_generation').trim() || 'video_generation';
  }
  function isLocalVideoLane(job){
    const type = videoWorkflowType(job);
    return type === 'video_upscale' || type === 'video_repair' || type === 'video_interpolate';
  }
  function shouldSuppressStaleRemoteVideoJob(job){
    if (!job || typeof job !== 'object') return false;
    const state = String(job.status || job.state || '').trim().toLowerCase();
    if (!state || isTerminalState(state)) return false;
    return !isLocalVideoLane(job) && !videoBackendConnected();
  }

  function effectiveAdvancedAdapters(profileValue = currentProfileValue()){
    const pairPreset = findAdapterPairPreset(adapterPairPresetSelectionId());
    const supported = supportsAdaptersForProfile(profileValue);
    const mode = adapterModeForProfile(profileValue);
    return {
      enabled: supported ? rememberedAdaptersEnabled() : false,
      mode,
      profile_mode: mode,
      pair_preset_id: supported && mode === 'paired' ? (pairPreset?.preset_id || adapterPairPresetSelectionId() || '') : '',
      pair_preset_name: supported && mode === 'paired' ? (pairPreset?.name || '') : '',
      single_adapter: supported && mode === 'single' ? adapterSingleValue() : '',
      high_noise_adapter: supported && mode === 'paired' ? adapterHighNoiseValue() : '',
      low_noise_adapter: supported && mode === 'paired' ? adapterLowNoiseValue() : '',
      strength: adapterStrengthValue(),
    };
  }
  function rememberedAdvancedAdapters(){
    const pairPreset = findAdapterPairPreset(adapterPairPresetSelectionId());
    const mode = adapterModeForProfile();
    return {
      enabled: rememberedAdaptersEnabled(),
      mode,
      profile_mode: mode,
      pair_preset_id: mode === 'paired' ? (pairPreset?.preset_id || adapterPairPresetSelectionId() || '') : '',
      pair_preset_name: mode === 'paired' ? (pairPreset?.name || '') : '',
      single_adapter: mode === 'single' ? adapterSingleValue() : '',
      high_noise_adapter: mode === 'paired' ? adapterHighNoiseValue() : '',
      low_noise_adapter: mode === 'paired' ? adapterLowNoiseValue() : '',
      strength: adapterStrengthValue(),
    };
  }

  function currentBackendAssets(profileValue = currentProfileValue()) {
    const balanced = defaultBalancedBackendAssets();
    const quality = defaultQualityBackendAssets(profileValue);
    return {
      balanced_unet_name: assetSelection('video-balanced-unet', balanced.unet_name || ''),
      balanced_clip_name: assetSelection('video-balanced-encoder', balanced.clip_name || ''),
      balanced_vae_name: assetSelection('video-balanced-vae', balanced.vae_name || ''),
      quality_high_noise_unet_name: assetSelection('video-quality-high-noise-unet', quality.high_noise_unet_name || ''),
      quality_low_noise_unet_name: assetSelection('video-quality-low-noise-unet', quality.low_noise_unet_name || ''),
      quality_clip_name: assetSelection('video-quality-encoder', quality.clip_name || ''),
      quality_vae_name: assetSelection('video-quality-vae', quality.vae_name || ''),
    };
  }

  function backendAssetsMatchDefaults(profileValue = currentProfileValue()) {
    const assets = currentBackendAssets(profileValue);
    if (isQualityProfile()) {
      const quality = defaultQualityBackendAssets(profileValue);
      return String(assets.quality_high_noise_unet_name || '') === String(quality.high_noise_unet_name || '')
        && String(assets.quality_low_noise_unet_name || '') === String(quality.low_noise_unet_name || '')
        && String(assets.quality_clip_name || '') === String(quality.clip_name || '')
        && String(assets.quality_vae_name || '') === String(quality.vae_name || '');
    }
    const balanced = defaultBalancedBackendAssets();
    return String(assets.balanced_unet_name || '') === String(balanced.unet_name || '')
      && String(assets.balanced_clip_name || '') === String(balanced.clip_name || '')
      && String(assets.balanced_vae_name || '') === String(balanced.vae_name || '');
  }

  function applyBackendAssetsToForm(assets = {}, profileValue = currentProfileValue()) {
    const row = assets && typeof assets === 'object' ? assets : {};
    const balanced = defaultBalancedBackendAssets();
    const quality = defaultQualityBackendAssets(profileValue);
    ensureSelectOption('video-balanced-unet', row.balanced_unet_name || balanced.unet_name || '');
    ensureSelectOption('video-balanced-encoder', row.balanced_clip_name || balanced.clip_name || '');
    ensureSelectOption('video-balanced-vae', row.balanced_vae_name || balanced.vae_name || '');
    ensureSelectOption('video-quality-high-noise-unet', row.quality_high_noise_unet_name || quality.high_noise_unet_name || '');
    ensureSelectOption('video-quality-low-noise-unet', row.quality_low_noise_unet_name || quality.low_noise_unet_name || '');
    ensureSelectOption('video-quality-encoder', row.quality_clip_name || quality.clip_name || '');
    ensureSelectOption('video-quality-vae', row.quality_vae_name || quality.vae_name || '');
    if ($('video-balanced-unet')) $('video-balanced-unet').value = row.balanced_unet_name || balanced.unet_name || '';
    if ($('video-balanced-encoder')) $('video-balanced-encoder').value = row.balanced_clip_name || balanced.clip_name || '';
    if ($('video-balanced-vae')) $('video-balanced-vae').value = row.balanced_vae_name || balanced.vae_name || '';
    if ($('video-quality-high-noise-unet')) $('video-quality-high-noise-unet').value = row.quality_high_noise_unet_name || quality.high_noise_unet_name || '';
    if ($('video-quality-low-noise-unet')) $('video-quality-low-noise-unet').value = row.quality_low_noise_unet_name || quality.low_noise_unet_name || '';
    if ($('video-quality-encoder')) $('video-quality-encoder').value = row.quality_clip_name || quality.clip_name || '';
    if ($('video-quality-vae')) $('video-quality-vae').value = row.quality_vae_name || quality.vae_name || '';
  }
  function ensureSelectOption(selectId, value, label = ''){
    const select = $(selectId);
    const clean = String(value || '').trim();
    if (!select || !clean) return;
    if ([...select.options].some(opt => String(opt.value || '').trim() === clean)) return;
    const opt = document.createElement('option');
    opt.value = clean;
    opt.textContent = label || `${clean} · saved`;
    select.appendChild(opt);
  }
  function captureSavedVideoPresetPayload(){
    return {
      surface:'video',
      mode: currentModeValue(),
      profile: currentProfileValue(),
      request: {
        negative_prompt: $('video-negative')?.value || '',
        duration_seconds: numberOr($('video-duration')?.value || defaults().duration_seconds || 5, defaults().duration_seconds || 5),
        fps: numberOr($('video-fps')?.value || defaults().fps || 16, defaults().fps || 16),
        size_preset: currentVideoSizePreset(),
        width: effectiveVideoSize().width,
        height: effectiveVideoSize().height,
        seed: $('video-seed')?.value || '',
      },
      creative_direction: {
        style_prompt: qualityPromptStyle(),
        camera_prompt: qualityPromptCamera(),
      },
      backend_assets: currentBackendAssets(),
      advanced_adapters: effectiveAdvancedAdapters(),
      post_pipeline_template: currentPostPipelineTemplateId(),
      post_process: currentPostProcessSelection(),
    };
  }
  function workspaceMatchesSavedVideoPreset(preset){
    const row = preset && typeof preset === 'object' ? preset : null;
    if (!row) return false;
    const request = row.request && typeof row.request === 'object' ? row.request : {};
    const creative = row.creative_direction && typeof row.creative_direction === 'object' ? row.creative_direction : {};
    const assets = row.backend_assets && typeof row.backend_assets === 'object' ? row.backend_assets : {};
    const adapters = row.advanced_adapters && typeof row.advanced_adapters === 'object' ? row.advanced_adapters : {};
    const currentAssets = currentBackendAssets(normalizeProfile(row.profile || currentProfileValue()));
    const currentAdapters = effectiveAdvancedAdapters();
    return normalizeMode(row.mode || '') === currentModeValue()
      && normalizeProfile(row.profile || '') === currentProfileValue()
      && String(request.duration_seconds ?? defaults().duration_seconds ?? 5) === String($('video-duration')?.value || defaults().duration_seconds || 5)
      && String(request.fps ?? defaults().fps ?? 16) === String($('video-fps')?.value || defaults().fps || 16)
      && String(request.size_preset || defaults().size_preset || '832x480') === String(currentVideoSizePreset())
      && String(request.width || '') === String(currentVideoSizePreset() === 'custom' || currentVideoSizePreset() === 'source_match' ? effectiveVideoSize().width : (request.width || ''))
      && String(request.height || '') === String(currentVideoSizePreset() === 'custom' || currentVideoSizePreset() === 'source_match' ? effectiveVideoSize().height : (request.height || ''))
      && String(request.negative_prompt || '').trim() === String($('video-negative')?.value || '').trim()
      && String(request.seed || '').trim() === String($('video-seed')?.value || '').trim()
      && String(creative.style_prompt || '').trim() === qualityPromptStyle().trim()
      && String(creative.camera_prompt || '').trim() === qualityPromptCamera().trim()
      && String(assets.balanced_unet_name || '').trim() === String(currentAssets.balanced_unet_name || '').trim()
      && String(assets.balanced_clip_name || '').trim() === String(currentAssets.balanced_clip_name || '').trim()
      && String(assets.balanced_vae_name || '').trim() === String(currentAssets.balanced_vae_name || '').trim()
      && String(assets.quality_high_noise_unet_name || '').trim() === String(currentAssets.quality_high_noise_unet_name || '').trim()
      && String(assets.quality_low_noise_unet_name || '').trim() === String(currentAssets.quality_low_noise_unet_name || '').trim()
      && String(assets.quality_clip_name || '').trim() === String(currentAssets.quality_clip_name || '').trim()
      && String(assets.quality_vae_name || '').trim() === String(currentAssets.quality_vae_name || '').trim()
      && String(!!adapters.enabled) === String(!!currentAdapters.enabled)
      && String(adapters.mode || adapters.profile_mode || '').trim() === String(currentAdapters.mode || currentAdapters.profile_mode || '').trim()
      && String(adapters.pair_preset_id || '').trim() === String(currentAdapters.pair_preset_id || '').trim()
      && String(adapters.single_adapter || '').trim() === String(currentAdapters.single_adapter || '').trim()
      && String(adapters.high_noise_adapter || '').trim() === String(currentAdapters.high_noise_adapter || '').trim()
      && String(adapters.low_noise_adapter || '').trim() === String(currentAdapters.low_noise_adapter || '').trim()
      && String(adapters.strength ?? adapterSupport().default_strength ?? 0.8) === String(currentAdapters.strength ?? adapterSupport().default_strength ?? 0.8)
      && String(row.post_pipeline_template || '').trim() === currentPostPipelineTemplateId().trim();
  }

  function populateModeOptions(){
    const select = $('video-mode');
    if (!select) return;
    const previous = normalizeMode(select.value || defaults().mode);
    select.innerHTML = '';
    allModes().forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = item.label;
      select.appendChild(opt);
    });
    select.value = allModes().some(item => item.id === previous) ? previous : (defaults().mode || 't2v');
  }

  function populateProfileOptions(preferred){
    const select = $('video-profile');
    if (!select) return;
    const desired = normalizeProfile(preferred || select.value || defaults().profile);
    const options = allowedProfilesForMode(currentModeValue());
    select.innerHTML = '';
    options.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = displayProfileLabel(item);
      opt.dataset.technicalLabel = item.technical_label || item.label || item.id;
      opt.dataset.qualityTier = item.quality_tier || '';
      select.appendChild(opt);
    });
    const chosen = options.some(item => item.id === desired) ? desired : (findMode(currentModeValue()).default_profile || options[0]?.id || defaults().profile);
    select.value = chosen;
    const note = $('video-profile-contract-note');
    const profile = currentProfileDefinition();
    if (note) note.textContent = `${displayProfileLabel(profile)} keeps the shell simple. Resolved backend: ${profile.technical_label || profile.label}. ${profile.notes || ''}`.trim();
  }

  function getVideoDraft(){
    try {
      const stored = [window.localStorage.getItem(STORAGE_KEY), ...LEGACY_STORAGE_KEYS.map(key => window.localStorage.getItem(key))].find(Boolean) || '{}';
      const raw = JSON.parse(stored) || {};
      if (!raw || typeof raw !== 'object') return {};
      return {
        ...raw,
        mode: normalizeMode(raw.mode || raw.workflow_mode || defaults().mode),
        profile: normalizeProfile(raw.profile || raw.family || defaults().profile),
      };
    } catch(_){
      return {};
    }
  }

  function emitVideoShellState(){
    document.dispatchEvent(new CustomEvent('neo-video-profile-changed', {
      detail: { value: currentProfileValue(), label: currentProfileLabel(), definition: currentProfileDefinition() }
    }));
    document.dispatchEvent(new CustomEvent('neo-video-mode-changed', {
      detail: { value: currentModeValue(), label: currentModeLabel(), definition: currentModeDefinition() }
    }));
  }

  function sourceVideoFile(){ return $('video-upscale-source-file')?.files?.[0] || null; }
  function getUpscaleSourceRef(){ try { return JSON.parse($('video-upscale-source-ref')?.value || '{}') || {}; } catch(_) { return {}; } }
  function currentUpscaleProfile(){ return String($('video-upscale-profile')?.value || 'fast_local').trim() || 'fast_local'; }
  function currentUpscaleTarget(){ return String($('video-upscale-target')?.value || '1920x1080').trim() || '1920x1080'; }
  function currentUpscaleFpsMode(){ return String($('video-upscale-fps-mode')?.value || 'preserve').trim() || 'preserve'; }
  function currentUpscaleContainer(){ return String($('video-upscale-container')?.value || 'mp4').trim() || 'mp4'; }
  function currentUpscaleCodec(){ return String($('video-upscale-codec')?.value || 'auto').trim() || 'auto'; }
  function sourceRepairFile(){ return $('video-repair-source-file')?.files?.[0] || null; }
  function getRepairSourceRef(){ try { return JSON.parse($('video-repair-source-ref')?.value || '{}') || {}; } catch(_) { return {}; } }
  function currentRepairStrength(){ return String($('video-repair-strength')?.value || 'balanced').trim() || 'balanced'; }
  function currentRepairFocus(){ return String($('video-repair-focus')?.value || 'general_cleanup').trim() || 'general_cleanup'; }
  function currentRepairStabilizeTemporal(){ return !!$('video-repair-stabilize')?.checked; }
  function sourceInterpolateFile(){ return $('video-interpolate-source-file')?.files?.[0] || null; }
  function getInterpolateSourceRef(){ try { return JSON.parse($('video-interpolate-source-ref')?.value || '{}') || {}; } catch(_) { return {}; } }
  function currentInterpolatePreset(){ return String($('video-interpolate-preset')?.value || '').trim(); }
  function currentInterpolateTargetFps(){ return Math.max(8, numberOr($('video-interpolate-target-fps')?.value || 30, 30)); }
  function currentInterpolateMultiplier(){ const value = Number($('video-interpolate-multiplier')?.value); if (!Number.isFinite(value)) return 2; return Math.max(1, Math.min(4, Math.round(value * 1000) / 1000)); }
  function currentInterpolateQualityMode(){ return String($('video-interpolate-quality')?.value || 'balanced').trim() || 'balanced'; }
  function currentInterpolateTimingIntent(){ return String($('video-interpolate-intent')?.value || 'preserve_timing').trim() || 'preserve_timing'; }
  function currentVideoSizePreset(){ return String($('video-size')?.value || defaults().size_preset || '832x480').trim() || '832x480'; }
  function snapVideoDimension(value, fallback){
    const num = Number(value);
    const base = Number.isFinite(num) ? num : fallback;
    const clamped = Math.max(256, Math.min(2048, Math.round(base)));
    return Math.max(256, Math.round(clamped / 16) * 16);
  }
  function currentManualVideoWidth(){ return snapVideoDimension($('video-width')?.value || 832, 832); }
  function currentManualVideoHeight(){ return snapVideoDimension($('video-height')?.value || 480, 480); }
  function currentSourceImageMeta(){ return videoSourceImageMeta && Number(videoSourceImageMeta.width) > 0 && Number(videoSourceImageMeta.height) > 0 ? { width:Number(videoSourceImageMeta.width), height:Number(videoSourceImageMeta.height) } : { width:0, height:0 }; }
  function autoSourceFitLimits(){
    const profile = normalizeProfile(currentProfileValue());
    const engine = selectedVideoBackendEngine(profile);
    const tier = (profile === 'wan22_14b_t2v_quality' || profile === 'wan22_14b_i2v_quality' || (profile === 'raw_free' && engine === 'wan_native')) ? 'quality' : 'balanced';
    return VIDEO_AUTO_SOURCE_FIT_LIMITS[tier] || VIDEO_AUTO_SOURCE_FIT_LIMITS.balanced;
  }
  function chooseAutoSourceFit(meta = currentSourceImageMeta()){
    const sourceWidth = Number(meta.width) || 0;
    const sourceHeight = Number(meta.height) || 0;
    if (!sourceWidth || !sourceHeight) {
      return { width:832, height:480, label:'Auto best fit · waiting for image' };
    }
    const limits = autoSourceFitLimits();
    const aspect = sourceWidth / Math.max(1, sourceHeight);
    let width = sourceWidth;
    let height = sourceHeight;
    const longScale = Math.min(1, limits.maxLongEdge / Math.max(width, height));
    width *= longScale;
    height *= longScale;
    const pixelScale = Math.min(1, Math.sqrt(limits.maxPixels / Math.max(1, width * height)));
    width *= pixelScale;
    height *= pixelScale;
    width = snapVideoDimension(width, aspect >= 1 ? 832 : 576);
    height = snapVideoDimension(height, aspect >= 1 ? 480 : 1024);
    const ratio = width / Math.max(1, height);
    while ((width * height > limits.maxPixels || Math.max(width, height) > limits.maxLongEdge) && width > 256 && height > 256) {
      if (ratio >= 1) {
        width = Math.max(256, width - 16);
        height = Math.max(256, snapVideoDimension(width / Math.max(ratio, 0.0001), height));
      } else {
        height = Math.max(256, height - 16);
        width = Math.max(256, snapVideoDimension(height * ratio, width));
      }
    }
    return { width, height, label:`Auto best fit · ${width} × ${height}` };
  }
  function maybeAutoSelectSourceFit(){
    if (currentModeValue() !== 'i2v' || !currentSourceImageMeta().width) return;
    const sizeEl = $('video-size');
    if (!sizeEl) return;
    const preset = currentVideoSizePreset();
    if (preset === 'custom') return;
    if (preset === 'auto_source_fit' || preset === 'source_match' || VIDEO_SIZE_PRESETS[preset]) sizeEl.value = 'auto_source_fit';
  }
  function effectiveVideoSize(){
    const preset = currentVideoSizePreset();
    if (VIDEO_SIZE_PRESETS[preset]) {
      const row = VIDEO_SIZE_PRESETS[preset];
      return { preset, width:row.width, height:row.height, label:`${row.width} × ${row.height}` };
    }
    if (preset === 'custom') {
      const width = currentManualVideoWidth();
      const height = currentManualVideoHeight();
      return { preset:'custom', width, height, label:`Custom · ${width} × ${height}` };
    }
    if (preset === 'auto_source_fit') {
      const size = chooseAutoSourceFit();
      return { preset:'auto_source_fit', width:size.width, height:size.height, label:size.label };
    }
    if (preset === 'source_match') {
      const meta = currentSourceImageMeta();
      const width = snapVideoDimension(meta.width || 832, 832);
      const height = snapVideoDimension(meta.height || 480, 480);
      return { preset:'source_match', width, height, label:(meta.width && meta.height) ? `Source match · ${width} × ${height}` : 'Source match · waiting for image' };
    }
    const fallback = VIDEO_SIZE_PRESETS['832x480'];
    return { preset:'832x480', width:fallback.width, height:fallback.height, label:`${fallback.width} × ${fallback.height}` };
  }
  function applyVideoSizeUiState(){
    const preset = currentVideoSizePreset();
    const customRow = $('video-custom-size-row');
    const sizeHelp = $('video-size-help');
    if (customRow) customRow.style.display = preset === 'custom' ? 'grid' : 'none';
    if (preset === 'custom') {
      if ($('video-width')) $('video-width').value = String(currentManualVideoWidth());
      if ($('video-height')) $('video-height').value = String(currentManualVideoHeight());
    }
    if (sizeHelp) {
      const size = effectiveVideoSize();
      if (preset === 'auto_source_fit') {
        sizeHelp.textContent = currentModeValue() === 'i2v'
          ? (currentSourceImageMeta().width ? `Auto best fit picked ${size.width} × ${size.height} from the uploaded image. Neo keeps the orientation, downsizes oversized inputs, and snaps to safe 16-pixel steps.` : 'Auto best fit needs a real source image selected in this browser so Neo can read the dimensions.')
          : 'Auto best fit only makes sense for Image to Video. Text to Video has no source frame to scale from.';
      } else if (preset === 'source_match') {
        sizeHelp.textContent = currentModeValue() === 'i2v'
          ? (currentSourceImageMeta().width ? `Source match will snap the uploaded image to ${size.width} × ${size.height} before queueing.` : 'Source match needs a real source image selected in this browser so Neo can read the dimensions.')
          : 'Source match only really makes sense for Image to Video. Text to Video has no source frame to match.';
      } else if (preset === 'custom') {
        sizeHelp.textContent = `Manual size is set to ${size.width} × ${size.height}. Neo snaps custom values to safe 16-pixel steps.`;
      } else {
        sizeHelp.textContent = 'Preset sizes stay safest. Match source image is best for I2V when the starting image already has the framing you want.';
      }
    }
  }
  async function refreshVideoSourceImageMeta(file){
    const metaNote = $('video-source-image-meta');
    if (!file) {
      videoSourceImageMeta = { width:0, height:0 };
      if (metaNote) { metaNote.style.display = 'none'; metaNote.textContent = ''; }
      applyVideoSizeUiState();
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    try {
      const dims = await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({ width:img.naturalWidth || img.width || 0, height:img.naturalHeight || img.height || 0 });
        img.onerror = () => reject(new Error('Could not read the selected image size.'));
        img.src = objectUrl;
      });
      videoSourceImageMeta = { width:Number(dims.width) || 0, height:Number(dims.height) || 0 };
      if (metaNote && videoSourceImageMeta.width && videoSourceImageMeta.height) {
        metaNote.style.display = '';
        metaNote.textContent = `Image size: ${videoSourceImageMeta.width} × ${videoSourceImageMeta.height}`;
      }
    } catch (_) {
      videoSourceImageMeta = { width:0, height:0 };
      if (metaNote) { metaNote.style.display = 'none'; metaNote.textContent = ''; }
    } finally {
      try { URL.revokeObjectURL(objectUrl); } catch (_) {}
      maybeAutoSelectSourceFit();
      applyVideoSizeUiState();
    }
  }

  function setUpscaleSourceRef(ref, label=''){
    const payload = ref && typeof ref === 'object' ? ref : {};
    if ($('video-upscale-source-ref')) $('video-upscale-source-ref').value = JSON.stringify(payload);
    if ($('video-upscale-source-label')) $('video-upscale-source-label').value = label || payload.label || payload.filename || '';
    if ($('video-upscale-source-file')) $('video-upscale-source-file').value = '';
  }

  function clearUpscaleSource({ announce=false } = {}){
    if ($('video-upscale-source-ref')) $('video-upscale-source-ref').value = '';
    if ($('video-upscale-source-label')) $('video-upscale-source-label').value = '';
    if ($('video-upscale-source-file')) $('video-upscale-source-file').value = '';
    renderUpscaleSummary();
    if (announce) setStatusSafe('video-status', 'Cleared the Upscale lane source.', 'ok');
  }

  function setRepairSourceRef(ref, label=''){
    const payload = ref && typeof ref === 'object' ? ref : {};
    if ($('video-repair-source-ref')) $('video-repair-source-ref').value = JSON.stringify(payload);
    if ($('video-repair-source-label')) $('video-repair-source-label').value = label || payload.label || payload.filename || '';
    if ($('video-repair-source-file')) $('video-repair-source-file').value = '';
  }

  function clearRepairSource({ announce=false } = {}){
    if ($('video-repair-source-ref')) $('video-repair-source-ref').value = '';
    if ($('video-repair-source-label')) $('video-repair-source-label').value = '';
    if ($('video-repair-source-file')) $('video-repair-source-file').value = '';
    renderRepairSummary();
    if (announce) setStatusSafe('video-status', 'Cleared the Repair lane source.', 'ok');
  }

  function setInterpolateSourceRef(ref, label=''){
    const payload = ref && typeof ref === 'object' ? ref : {};
    if ($('video-interpolate-source-ref')) $('video-interpolate-source-ref').value = JSON.stringify(payload);
    if ($('video-interpolate-source-label')) $('video-interpolate-source-label').value = label || payload.label || payload.filename || '';
    if ($('video-interpolate-source-file')) $('video-interpolate-source-file').value = '';
  }

  function clearInterpolateSource({ announce=false } = {}){
    if ($('video-interpolate-source-ref')) $('video-interpolate-source-ref').value = '';
    if ($('video-interpolate-source-label')) $('video-interpolate-source-label').value = '';
    if ($('video-interpolate-source-file')) $('video-interpolate-source-file').value = '';
    renderInterpolateSummary();
    if (announce) setStatusSafe('video-status', 'Cleared the Interpolate lane source.', 'ok');
  }

  function collectVideoPayload(){
    return {
      contract_schema_version: getVideoContract().schema_version || 1,
      surface: 'video',
      mode: currentModeValue(),
      profile: currentProfileValue(),
      duration_seconds: numberOr($('video-duration')?.value || defaults().duration_seconds || 5, defaults().duration_seconds || 5),
      fps: numberOr($('video-fps')?.value || defaults().fps || 16, defaults().fps || 16),
      size_preset: currentVideoSizePreset(),
        width: effectiveVideoSize().width,
        height: effectiveVideoSize().height,
      source_image: $('video-source-image')?.value || '',
      prompt: $('video-prompt')?.value || '',
      negative_prompt: $('video-negative')?.value || '',
      seed: $('video-seed')?.value || '',
      quality_style_prompt: qualityPromptStyle(),
      quality_camera_prompt: qualityPromptCamera(),
      backend_assets: currentBackendAssets(),
      unet_name: currentBackendAssets().balanced_unet_name,
      clip_name: currentBackendAssets().balanced_clip_name,
      vae_name: currentBackendAssets().balanced_vae_name,
      quality_high_noise_unet_name: currentBackendAssets().quality_high_noise_unet_name,
      quality_low_noise_unet_name: currentBackendAssets().quality_low_noise_unet_name,
      clip_name_quality: currentBackendAssets().quality_clip_name,
      vae_name_quality: currentBackendAssets().quality_vae_name,
      free_asset_mode: freeAssetModeEnabled() || isRawFreeProfile(),
      video_backend_engine_override: selectedVideoBackendEngineOverride(),
      video_backend_engine: selectedVideoBackendEngine(),
      advanced_adapters: effectiveAdvancedAdapters(),
      post_pipeline_template: currentPostPipelineTemplateId(),
      post_process: currentPostProcessSelection(),
      upscale_profile: currentUpscaleProfile(),
      upscale_target_resolution: currentUpscaleTarget(),
      upscale_fps_mode: currentUpscaleFpsMode(),
      upscale_output_fps: numberOr($('video-upscale-custom-fps')?.value || 24, 24),
      upscale_output_container: currentUpscaleContainer(),
      upscale_output_codec: currentUpscaleCodec(),
      upscale_source_ref: getUpscaleSourceRef(),
      upscale_source_label: $('video-upscale-source-label')?.value || '',
      repair_strength_preset: currentRepairStrength(),
      repair_cleanup_focus: currentRepairFocus(),
      repair_stabilize_temporal: currentRepairStabilizeTemporal(),
      repair_source_ref: getRepairSourceRef(),
      repair_source_label: $('video-repair-source-label')?.value || '',
      interpolation_preset: currentInterpolatePreset(),
      interpolate_target_fps: currentInterpolateTargetFps(),
      interpolate_multiplier: currentInterpolateMultiplier(),
      interpolate_quality_mode: currentInterpolateQualityMode(),
      interpolate_timing_intent: currentInterpolateTimingIntent(),
      interpolate_source_ref: getInterpolateSourceRef(),
      interpolate_source_label: $('video-interpolate-source-label')?.value || '',
      updated_at: new Date().toISOString(),
    };
  }

  function collectUpscalePayload(){
    const sourceRef = getUpscaleSourceRef();
    return {
      surface: 'video',
      workflow_type: 'video_upscale',
      lane: 'upscale',
      upscale_profile: currentUpscaleProfile(),
      target_resolution: currentUpscaleTarget(),
      fps_mode: currentUpscaleFpsMode(),
      output_fps: numberOr($('video-upscale-custom-fps')?.value || 24, 24),
      output_container: currentUpscaleContainer(),
      output_codec: currentUpscaleCodec(),
      source_video_label: $('video-upscale-source-label')?.value || sourceRef.label || sourceRef.filename || '',
      source_output_ref: sourceRef,
      updated_at: new Date().toISOString(),
    };
  }

  function estimateUpscaleRuntime(payload){
    const row = payload || collectUpscalePayload();
    const profile = String(row.upscale_profile || 'fast_local').trim().toLowerCase() || 'fast_local';
    const target = String(row.target_resolution || currentUpscaleTarget()).trim() || '1920x1080';
    const fpsMode = String(row.fps_mode || currentUpscaleFpsMode()).trim() || 'preserve';
    const outputFps = Math.max(8, numberOr(row.output_fps || 24, 24));
    let score = 0;
    if (profile === 'quality_conservative') score += 1;
    if (target === '1920x1080') score += 1;
    else if (target === '2560x1440') score += 2;
    if (fpsMode === 'custom' && outputFps >= 30) score += 1;
    if (fpsMode === 'custom' && outputFps >= 60) score += 1;
    const estimated_heaviness = score >= 4 ? 'heavy' : (score >= 2 ? 'medium' : 'light');
    const warnings = [];
    if (profile === 'quality_conservative') warnings.push('Quality Conservative takes longer than Fast Local, but it stays in a preserve-first upscale lane instead of a creative rerender path.');
    if (target === '2560x1440') warnings.push('1440p delivery asks more of local CPU / GPU and will be noticeably slower than 720p or 1080p.');
    if (fpsMode === 'custom' && outputFps > 30) warnings.push('Raising FPS in the Upscale lane does not invent smoother motion. Keep preserve-FPS unless you truly need a delivery override.');
    if (String(row.output_container || currentUpscaleContainer()) === 'webm') warnings.push('WebM stays on the conservative auto codec path in this first Upscale lane.');
    const slow_copy = estimated_heaviness === 'heavy'
      ? 'This Upscale request is heavy for a first conservative pass. Expect a slower local export and a larger delivery file.'
      : estimated_heaviness === 'medium'
        ? 'This Upscale request is medium-weight. It should run locally, but it will take longer than a casual draft pass.'
        : 'This Upscale request should stay in the lighter local lane.';
    return { estimated_heaviness, warnings, slow_copy };
  }

  function collectRepairPayload(){
    const sourceRef = getRepairSourceRef();
    return {
      surface: 'video',
      workflow_type: 'video_repair',
      lane: 'repair',
      repair_strength_preset: currentRepairStrength(),
      repair_cleanup_focus: currentRepairFocus(),
      stabilize_temporal: currentRepairStabilizeTemporal(),
      source_video_label: $('video-repair-source-label')?.value || sourceRef.label || sourceRef.filename || '',
      source_output_ref: sourceRef,
      updated_at: new Date().toISOString(),
    };
  }

  function collectInterpolatePayload(){
    const sourceRef = getInterpolateSourceRef();
    return {
      surface: 'video',
      workflow_type: 'video_interpolate',
      lane: 'interpolate',
      interpolation_preset: currentInterpolatePreset(),
      target_fps: currentInterpolateTargetFps(),
      interpolation_multiplier: currentInterpolateMultiplier(),
      motion_quality_mode: currentInterpolateQualityMode(),
      timing_intent: currentInterpolateTimingIntent(),
      source_video_label: $('video-interpolate-source-label')?.value || sourceRef.label || sourceRef.filename || '',
      source_output_ref: sourceRef,
      updated_at: new Date().toISOString(),
    };
  }

  function estimateInterpolateRuntime(payload){
    const row = payload || collectInterpolatePayload();
    const sourceProbe = row.source_probe && typeof row.source_probe === 'object' ? row.source_probe : {};
    const sourceFps = Number(sourceProbe.fps || 0);
    const targetFps = Math.max(8, numberOr(row.resolved_target_fps || row.target_fps || currentInterpolateTargetFps(), 30));
    const multiplier = Math.max(1, Number(row.resolved_multiplier || row.interpolation_multiplier || currentInterpolateMultiplier() || 2));
    const qualityMode = String(row.motion_quality_mode || currentInterpolateQualityMode()).trim().toLowerCase() || 'balanced';
    const timingIntent = String(row.timing_intent || currentInterpolateTimingIntent()).trim().toLowerCase() || 'preserve_timing';
    const durationSeconds = Number(row.resolved_output_duration_seconds || sourceProbe.duration_seconds || 0);
    let score = 0;
    if (qualityMode === 'smooth') score += 1;
    else if (qualityMode === 'detail_safe') score += 2;
    if (targetFps >= 30) score += 1;
    if (targetFps >= 48) score += 1;
    if (targetFps >= 60) score += 1;
    if (timingIntent === 'slow_motion') score += 1;
    if (durationSeconds >= 20) score += 1;
    if (durationSeconds >= 45) score += 1;
    const estimated_heaviness = score >= 5 ? 'heavy' : (score >= 2 ? 'medium' : 'light');
    const warnings = [];
    if (sourceFps && targetFps <= sourceFps) warnings.push(`Interpolate only helps when the target FPS is higher than the source clip (${sourceFps.toFixed(2)} FPS).`);
    if (targetFps >= 60) warnings.push('60 FPS interpolation is the heaviest delivery path in this lane. Use it when the smoother motion is worth the extra export time.');
    else if (targetFps >= 30) warnings.push('Higher target FPS adds render time fast. Stay closer to the original clip unless you really need a smoother deliverable.');
    if (timingIntent === 'slow_motion') warnings.push('Slow motion stretches the clip length. Audio is time-stretched to match, so expect a more processed result than Preserve timing.');
    if (qualityMode === 'smooth') warnings.push('Smoother motion pushes harder on synthetic in-between frames. Great for choppy clips, but watch for edge warping on fast motion.');
    else if (qualityMode === 'detail_safe') warnings.push('Detail Safe stays more conservative around cuts and texture, but it is the slowest local interpolation mode.');
    if (sourceFps && multiplier >= 2.5 && targetFps > sourceFps * 2.5) warnings.push('This target FPS is much higher than the source clip. Expect diminishing returns if the original motion is already rough.');
    const slow_copy = estimated_heaviness === 'heavy'
      ? 'This Interpolate request is heavy for a local polish pass. Expect a slower export, especially with slow motion or 60 FPS output.'
      : estimated_heaviness === 'medium'
        ? 'This Interpolate request is medium-weight. It should stay local, but higher FPS and smarter frame blending take time.'
        : 'This Interpolate request should stay in the lighter local polish lane.';
    return { estimated_heaviness, warnings, slow_copy };
  }

  function estimateRepairRuntime(payload){
    const row = payload || collectRepairPayload();
    const strength = String(row.repair_strength_preset || currentRepairStrength()).trim().toLowerCase() || 'balanced';
    const focus = String(row.repair_cleanup_focus || currentRepairFocus()).trim().toLowerCase() || 'general_cleanup';
    const stabilize = !!(row.stabilize_temporal ?? currentRepairStabilizeTemporal());
    let score = 0;
    if (strength === 'balanced') score += 1;
    else if (strength === 'aggressive') score += 2;
    if (focus === 'compression_cleanup') score += 1;
    if (stabilize) score += 1;
    const estimated_heaviness = score >= 4 ? 'heavy' : (score >= 2 ? 'medium' : 'light');
    const warnings = [];
    if (strength === 'aggressive') warnings.push('Aggressive repair can over-smooth fine texture. Use it when the clip is genuinely broken, not just a little rough.');
    if (focus === 'compression_cleanup') warnings.push('Compression cleanup leans harder into preserve-first smoothing to tame blockiness and mosquito noise.');
    if (stabilize) warnings.push('Temporal stabilization is mild on purpose, but it still adds render time and can slightly crop or shift the frame.');
    const slow_copy = estimated_heaviness === 'heavy'
      ? 'This Repair request is heavy for a local rescue pass. Expect a slower export, especially if stabilization is enabled.'
      : estimated_heaviness === 'medium'
        ? 'This Repair request is medium-weight. It should still stay local, but the preserve-first cleanup pass will take a while.'
        : 'This Repair request should stay in the lighter local cleanup lane.';
    return { estimated_heaviness, warnings, slow_copy };
  }

  function estimateRuntime(payload){
    const row = payload || collectVideoPayload();
    const mode = findMode(row.mode || currentModeValue());
    const profile = allProfiles().find(item => item.id === normalizeProfile(row.profile || currentProfileValue())) || currentProfileDefinition();
    const duration = Math.max(1, numberOr(row.duration_seconds || row.duration, defaults().duration_seconds || 5));
    const fps = Math.max(1, numberOr(row.fps, defaults().fps || 16));
    const size = row.size_preset || row.size || defaults().size_preset || '832x480';
    const quality = String(profile?.quality_tier || '').toLowerCase() === 'quality';
    const adapters = row.advanced_adapters && typeof row.advanced_adapters === 'object' ? row.advanced_adapters : {};
    const adaptersEnabled = !!adapters.enabled;
    const pairedAdaptersEnabled = adaptersEnabled && String(adapters.mode || adapters.profile_mode || '').trim() === 'paired';
    const singleAdaptersEnabled = adaptersEnabled && !pairedAdaptersEnabled;
    let score = 0;
    if (quality) score += 3;
    if (mode?.id === 'i2v') score += 1;
    if (duration >= 8) score += 1;
    if (duration >= 12) score += 1;
    if (fps >= 20) score += 1;
    if (fps >= 24) score += 1;
    if (size === '1024x576' || size === '576x1024') score += 1;
    if (quality && pairedAdaptersEnabled) score += 1;
    if (!quality && singleAdaptersEnabled) score += 1;
    const estimated_heaviness = score >= 4 ? 'heavy' : (score >= 2 ? 'medium' : 'light');
    const warnings = [];
    if (!quality && (estimated_heaviness === 'medium' || estimated_heaviness === 'heavy')) warnings.push('This balanced request is no longer low-VRAM-safe. Shorter clips, 832 × 480, and 16 FPS are safer.');
    if (quality) warnings.push('This will be slow on most single-GPU setups. Keep the clip short unless you know the backend can handle the 14B path.');
    if (quality && duration > 5) warnings.push('High Quality clips longer than 5 seconds raise runtime cost and failure risk fast.');
    else if (!quality && duration > 8) warnings.push('Balanced clips longer than 8 seconds are more likely to stall or feel slow on modest VRAM.');
    if (fps >= 24) warnings.push('24 FPS is the heaviest shell cap in this build. Use it only when you actually need the smoother motion.');
    else if (fps > 16) warnings.push('Higher FPS raises render cost. 16 FPS is the safer default for draft clips.');
    if (size === '1024x576' || size === '576x1024') warnings.push('The larger resolution preset costs more VRAM and time than 832 × 480.');
    if (mode?.id === 'i2v' && quality) warnings.push('High Quality I2V keeps the start image anchored, but the heavier expert pair makes bad input images more expensive to fix.');
    if (quality && pairedAdaptersEnabled) warnings.push('Paired adapters raise memory pressure on the 14B path. Use them only when the matched high-noise / low-noise pair is worth the extra cost.');
    if (!quality && singleAdaptersEnabled) warnings.push('Balanced first-pass LoRAs still change the runtime profile. Great for fast custom workflows, but do not pretend they are the same as the bare default 5B path.');
    const slow_copy = estimated_heaviness === 'heavy'
      ? 'This is a heavy request. Expect a slower queue, longer runtime, and less forgiveness from the backend.'
      : estimated_heaviness === 'medium'
        ? 'This is a medium-weight request. It should run, but it is no longer a casual low-VRAM draft.'
        : 'This should stay in the lighter runtime lane if the backend is actually set up for Wan 2.2.';
    return { estimated_heaviness, warnings, slow_copy };
  }

  function saveVideoDraft(showStatus=true){
    const payload = collectVideoPayload();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    if (showStatus) setStatusSafe('video-status', 'Saved the current video draft in this browser.', 'ok');
    renderVideoSummary();
  }

  function applyVideoDraft(){
    populateModeOptions();
    const draft = getVideoDraft();
    const draftAdapters = draft.advanced_adapters && typeof draft.advanced_adapters === 'object' ? draft.advanced_adapters : {};
    const draftAssets = draft.backend_assets && typeof draft.backend_assets === 'object' ? draft.backend_assets : draft;
    if ($('video-mode')) $('video-mode').value = draft.mode || defaults().mode || 't2v';
    populateProfileOptions(draft.profile || defaults().profile || 'wan22_5b_balanced');
    if ($('video-duration') && draft.duration_seconds) $('video-duration').value = draft.duration_seconds;
    if ($('video-duration') && draft.duration) $('video-duration').value = draft.duration;
    if ($('video-fps') && draft.fps) $('video-fps').value = draft.fps;
    if ($('video-size') && (draft.size_preset || draft.size)) $('video-size').value = draft.size_preset || draft.size;
    if ($('video-width') && (draft.width || (draft.request || {}).width)) $('video-width').value = String(draft.width || (draft.request || {}).width);
    if ($('video-height') && (draft.height || (draft.request || {}).height)) $('video-height').value = String(draft.height || (draft.request || {}).height);
    applyVideoSizeUiState();
    if ($('video-source-image') && draft.source_image) $('video-source-image').value = draft.source_image;
    if ($('video-prompt') && draft.prompt) $('video-prompt').value = draft.prompt;
    if ($('video-negative') && (draft.negative_prompt || draft.negative)) $('video-negative').value = draft.negative_prompt || draft.negative;
    if ($('video-seed')) $('video-seed').value = draft.seed || defaults().seed || '';
    if ($('video-free-assets-mode')) $('video-free-assets-mode').checked = !!(draft.free_asset_mode || draft.video_free_asset_mode);
    if ($('video-backend-engine-override')) $('video-backend-engine-override').value = draft.video_backend_engine_override || 'auto';
    if ($('video-quality-style')) $('video-quality-style').value = draft.quality_style_prompt || draft.quality_style || '';
    if ($('video-quality-camera')) $('video-quality-camera').value = draft.quality_camera_prompt || draft.quality_camera || '';
    applyBackendAssetsToForm(draftAssets, draft.profile || defaults().profile || 'wan22_5b_balanced');
    if ($('video-adapters-enabled')) $('video-adapters-enabled').checked = !!draftAdapters.enabled;
    ensureSelectOption('video-adapter-preset-select', draftAdapters.pair_preset_id, draftAdapters.pair_preset_name);
    if ($('video-adapter-preset-select')) $('video-adapter-preset-select').value = draftAdapters.pair_preset_id || '';
    ensureSelectOption('video-adapter-single', draftAdapters.single_adapter);
    if ($('video-adapter-single')) $('video-adapter-single').value = draftAdapters.single_adapter || '';
    ensureSelectOption('video-adapter-high-noise', draftAdapters.high_noise_adapter);
    if ($('video-adapter-high-noise')) $('video-adapter-high-noise').value = draftAdapters.high_noise_adapter || '';
    ensureSelectOption('video-adapter-low-noise', draftAdapters.low_noise_adapter);
    if ($('video-adapter-low-noise')) $('video-adapter-low-noise').value = draftAdapters.low_noise_adapter || '';
    if ($('video-adapter-strength')) $('video-adapter-strength').value = String(draftAdapters.strength ?? adapterSupport().default_strength ?? 0.8);
    if ($('video-adapter-strength-quality')) $('video-adapter-strength-quality').value = String(draftAdapters.strength ?? adapterSupport().default_strength ?? 0.8);
    if ($('video-post-pipeline-template')) $('video-post-pipeline-template').value = draft.post_pipeline_template || defaults().post_pipeline_template || 'generate_only';
    if ($('video-upscale-profile')) $('video-upscale-profile').value = draft.upscale_profile || 'fast_local';
    if ($('video-upscale-target')) $('video-upscale-target').value = draft.upscale_target_resolution || '1920x1080';
    if ($('video-upscale-fps-mode')) $('video-upscale-fps-mode').value = draft.upscale_fps_mode || 'preserve';
    if ($('video-upscale-custom-fps')) $('video-upscale-custom-fps').value = String(draft.upscale_output_fps || 24);
    if ($('video-upscale-container')) $('video-upscale-container').value = draft.upscale_output_container || 'mp4';
    if ($('video-upscale-codec')) $('video-upscale-codec').value = draft.upscale_output_codec || 'auto';
    if (draft.upscale_source_ref) setUpscaleSourceRef(draft.upscale_source_ref, draft.upscale_source_label || draft.upscale_source_ref.label || draft.upscale_source_ref.filename || '');
    else if ($('video-upscale-source-label') && draft.upscale_source_label) $('video-upscale-source-label').value = draft.upscale_source_label;
    if ($('video-repair-strength')) $('video-repair-strength').value = draft.repair_strength_preset || 'balanced';
    if ($('video-repair-focus')) $('video-repair-focus').value = draft.repair_cleanup_focus || 'general_cleanup';
    if ($('video-repair-stabilize')) $('video-repair-stabilize').checked = !!draft.repair_stabilize_temporal;
    if (draft.repair_source_ref) setRepairSourceRef(draft.repair_source_ref, draft.repair_source_label || draft.repair_source_ref.label || draft.repair_source_ref.filename || '');
    else if ($('video-repair-source-label') && draft.repair_source_label) $('video-repair-source-label').value = draft.repair_source_label;
    if ($('video-interpolate-preset')) $('video-interpolate-preset').value = draft.interpolation_preset || '';
    if ($('video-interpolate-target-fps')) $('video-interpolate-target-fps').value = String(draft.interpolate_target_fps || 30);
    if ($('video-interpolate-multiplier')) $('video-interpolate-multiplier').value = String(draft.interpolate_multiplier || 2);
    if ($('video-interpolate-quality')) $('video-interpolate-quality').value = draft.interpolate_quality_mode || 'balanced';
    if ($('video-interpolate-intent')) $('video-interpolate-intent').value = draft.interpolate_timing_intent || 'preserve_timing';
    if (draft.interpolate_source_ref) setInterpolateSourceRef(draft.interpolate_source_ref, draft.interpolate_source_label || draft.interpolate_source_ref.label || draft.interpolate_source_ref.filename || '');
    else if ($('video-interpolate-source-label') && draft.interpolate_source_label) $('video-interpolate-source-label').value = draft.interpolate_source_label;
  }

  function syncVideoMode(){
    const mode = currentModeDefinition();
    const inputCard = $('video-input-card');
    const inputNote = $('video-input-note');
    if (inputCard) inputCard.style.display = mode.requires_source_image ? '' : 'none';
    if (inputNote) {
      inputNote.textContent = mode.requires_source_image
        ? (isQualityProfile()
            ? 'High Quality I2V keeps the source image as the motion anchor. Better output, but a much heavier start-image path.'
            : 'Image to Video uses a starting image as the motion anchor.')
        : 'Text to Video does not need a source image.';
    }
    populateProfileOptions(currentProfileValue());
    renderVideoSummary();
  }

  function plainFailureMessage(job){
    const raw = String(job?.video_runtime?.failure_message || job?.error || job?.error_message || job?.status_text || '').trim();
    if (!raw) return 'The job failed before Neo got a useful backend error. Check the backend connection, model files, and the current video settings.';
    return raw;
  }

  function humanState(state){
    return statusLabel(state);
  }

  function heavinessBadge(level){
    const clean = String(level || 'light').trim().toLowerCase() || 'light';
    return clean === 'heavy' ? 'Heavy' : clean === 'medium' ? 'Medium' : 'Light';
  }

  function outputPreviewUrl(output){
    const row = output && typeof output === 'object' ? output : {};
    return String(row.view_url || row.url || '').trim();
  }

  function buildPreviewState(job, output, { source = 'latest_output', title = '', note = '' } = {}){
    const item = output && typeof output === 'object' ? output : {};
    const url = outputPreviewUrl(item);
    if (!url) return null;
    const jobId = String(job?.job_id || job?.id || '').trim();
    const filename = String(item.filename || item.output_id || 'video_output.mp4').trim() || 'video_output.mp4';
    const workflowLabel = statusSnapshot(job).workflowLabel;
    const sizeLabel = String(item.size_preset || '').trim();
    const fpsLabel = String(item.fps || '').trim();
    const metaBits = [workflowLabel, sizeLabel, fpsLabel ? `${fpsLabel} FPS` : ''].filter(Boolean);
    return {
      url,
      jobId,
      filename,
      source,
      title: title || filename,
      note: note || metaBits.join(' · '),
      loop: videoPreviewState.loop !== false,
    };
  }

  function setVideoPreview(preview, { announce = false } = {}){
    const row = preview && typeof preview === 'object' ? preview : null;
    if (!row?.url) {
      renderVideoPreview();
      return;
    }
    videoPreviewState = {
      ...videoPreviewState,
      url: String(row.url || '').trim(),
      jobId: String(row.jobId || '').trim(),
      filename: String(row.filename || '').trim(),
      title: String(row.title || row.filename || 'Video preview').trim() || 'Video preview',
      source: String(row.source || '').trim(),
      note: String(row.note || '').trim(),
      loop: row.loop == null ? videoPreviewState.loop !== false : !!row.loop,
    };
    renderVideoPreview();
    if (announce) setStatusSafe('video-status', 'Loaded the selected clip into the preview player.', 'ok');
  }

  function clearVideoPreview({ announce = false } = {}){
    videoPreviewState = { url:'', jobId:'', filename:'', title:'', source:'', note:'', loop: videoPreviewState.loop !== false };
    renderVideoPreview();
    if (announce) setStatusSafe('video-status', 'Cleared the current video preview.', 'ok');
  }

  function renderVideoPreview(){
    const card = $('video-preview-card');
    if (!card) return;
    const empty = $('video-preview-empty-copy');
    const toolbar = $('video-preview-toolbar');
    const meta = $('video-preview-meta');
    const frame = $('video-preview-frame');
    const player = $('video-preview-player');
    const note = $('video-preview-note');
    const openBtn = $('btn-video-preview-open');
    const loopBtn = $('btn-video-preview-loop');
    const hasPreview = !!String(videoPreviewState.url || '').trim();
    card.style.display = '';
    if (empty) empty.style.display = hasPreview ? 'none' : '';
    if (toolbar) toolbar.style.display = hasPreview ? '' : 'none';
    if (meta) {
      meta.style.display = hasPreview ? '' : 'none';
      meta.innerHTML = hasPreview
        ? `<strong>${escapeHtml(videoPreviewState.title || videoPreviewState.filename || 'Video preview')}</strong>${videoPreviewState.note ? `<span> · ${escapeHtml(videoPreviewState.note)}</span>` : ''}`
        : '';
    }
    if (frame) frame.style.display = hasPreview ? '' : 'none';
    if (note) note.style.display = hasPreview ? '' : 'none';
    if (openBtn) openBtn.disabled = !hasPreview;
    if (loopBtn) {
      loopBtn.disabled = !hasPreview;
      loopBtn.textContent = videoPreviewState.loop !== false ? 'Loop on' : 'Loop off';
    }
    if (player) {
      if (!hasPreview) {
        player.removeAttribute('src');
        player.load();
      } else {
        const nextUrl = String(videoPreviewState.url || '').trim();
        if (player.getAttribute('src') !== nextUrl) player.setAttribute('src', nextUrl);
        player.loop = videoPreviewState.loop !== false;
        player.muted = true;
        player.playsInline = true;
        player.load();
      }
    }
  }

  function maybeAutoPreviewJob(job, { force = false, source = 'latest_output' } = {}){
    const outputs = Array.isArray(job?.outputs) ? job.outputs.filter(item => item && typeof item === 'object') : [];
    if (!outputs.length) return;
    const preview = buildPreviewState(job, outputs[0], { source, title: outputs[0]?.filename || 'Latest output' });
    if (!preview) return;
    const currentJobId = String(videoPreviewState.jobId || '').trim();
    const currentUrl = String(videoPreviewState.url || '').trim();
    if (!force && currentUrl && currentJobId && currentJobId !== preview.jobId) return;
    setVideoPreview(preview, { announce:false });
  }

  function previewHistoryJobOutput(jobId, outputId = ''){
    const cleanJobId = String(jobId || '').trim();
    if (!cleanJobId) return;
    const job = lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === cleanJobId) || null;
    if (!job) {
      setStatusSafe('video-status', 'Could not find that history item to preview.', 'warn');
      return;
    }
    const outputs = Array.isArray(job.outputs) ? job.outputs.filter(item => item && typeof item === 'object') : [];
    const target = outputs.find(item => String(item?.output_id || item?.filename || '').trim() === String(outputId || '').trim()) || outputs[0] || null;
    const preview = buildPreviewState(job, target, { source:'history', title: target?.filename || 'History preview' });
    if (!preview) {
      setStatusSafe('video-status', 'That history item does not have a previewable output yet.', 'warn');
      return;
    }
    setVideoPreview(preview, { announce:true });
  }

  function updateActionButtons(job){
    const current = job && typeof job === 'object' ? job : actionBarJobCandidate(null);
    const state = String(current?.status || current?.state || '').trim().toLowerCase();
    const canCancel = !!(current?.video_runtime?.can_cancel || activeJobId && !isTerminalState(state));
    const canRetry = !!(current?.video_runtime?.can_retry || lastVideoJobId);
    const cancelBtn = $('btn-video-cancel');
    if (cancelBtn) {
      cancelBtn.disabled = !canCancel || requestInFlight;
      cancelBtn.textContent = 'Stop';
      cancelBtn.classList.toggle('hidden', !canCancel && !requestInFlight);
    }
    if ($('btn-video-retry')) $('btn-video-retry').disabled = !canRetry || requestInFlight;
    if ($('btn-video-refresh-history')) $('btn-video-refresh-history').disabled = requestInFlight;
    if ($('btn-video-action-save')) $('btn-video-action-save').disabled = requestInFlight;
    if ($('btn-video-action-clear')) $('btn-video-action-clear').disabled = requestInFlight || canCancel;
    renderVideoActionBar(current);
  }

  function renderVideoOutputs(outputs, job){
    const card = $('video-output-results');
    if (!card) return;
    const rows = Array.isArray(outputs) ? outputs.filter(item => item && typeof item === 'object') : [];
    const manifestUrl = job?.video_runtime?.manifest_url || '';
    const workflowType = String(job?.payload?.workflow_type || '').trim() || 'video_generation';
    if (!rows.length){
      card.style.display = '';
      card.innerHTML = `
        <div class="accordion-title">Outputs</div>
        <div class="video-empty-card-copy" style="margin-top:12px;">No outputs yet. Queue generation or finish a post lane and Neo will surface the newest deliverables, manifest links, and handoff shortcuts here.</div>
      `;
      return;
    }
    maybeAutoPreviewJob(job, { force: !String(videoPreviewState.url || '').trim(), source:'latest_output' });
    const profileValue = String(job?.payload?.profile || currentProfileValue()).trim();
    const intro = workflowType === 'video_upscale'
      ? 'Upscale lane finished. Neo saved a local delivery file, wrote a manifest, and added the run to video history.'
      : workflowType === 'video_repair'
        ? 'Repair lane finished. Neo saved a cleaned local file, wrote a manifest, and added the run to video history.'
        : workflowType === 'video_interpolate'
          ? 'Interpolate lane finished. Neo saved a smoother local file, wrote a manifest, and added the run to video history.'
          : (profileValue === 'wan22_5b_balanced'
            ? 'Balanced generation finished. Neo saved a video output manifest and added the run to local video history.'
            : 'High Quality generation finished. Neo saved a video output manifest and added the run to local video history.');
    card.style.display = '';
    card.innerHTML = `
      <div class="accordion-title">Outputs</div>
      <div class="mini-note" style="margin-top:12px;">${escapeHtml(intro)}</div>
      ${manifestUrl ? `<div class="row" style="margin-top:12px; gap:8px; flex-wrap:wrap;"><a class="btn btn-small" href="${escapeHtml(manifestUrl)}" target="_blank" rel="noopener">Open output manifest</a></div>` : ''}
      <div style="margin-top:14px; display:grid; gap:10px;">
        ${rows.map((item, index) => `
          <div class="row-between" style="gap:12px; padding:10px 0; border-top:1px solid rgba(148,163,184,.12); align-items:flex-start;">
            <div>
              <strong>Output ${index + 1}</strong>
              <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.filename || `video_${index + 1}`)}</div>
              <div class="mini-note" style="margin-top:4px;">${escapeHtml(String(item.size_preset || '').trim() || 'Unknown size')} · ${escapeHtml(String(item.fps || '—'))} FPS</div>
            </div>
            <div class="row video-output-actions" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;">
              <button class="btn btn-small" type="button" data-video-output-preview="${escapeHtml(job?.job_id || job?.id || '')}" data-video-output-id="${escapeHtml(item.output_id || item.filename || '')}">Preview</button>
              <a class="btn btn-small" href="${escapeHtml(item.view_url || '#')}" target="_blank" rel="noopener">Open output</a>
              <button class="btn btn-small" type="button" data-video-output-repair="${escapeHtml(job?.job_id || job?.id || '')}" data-video-output-id="${escapeHtml(item.output_id || item.filename || '')}">Send to Repair</button>
              <button class="btn btn-small" type="button" data-video-output-interpolate="${escapeHtml(job?.job_id || job?.id || '')}" data-video-output-id="${escapeHtml(item.output_id || item.filename || '')}">Send to Interpolate</button>
              <button class="btn btn-small" type="button" data-video-output-upscale="${escapeHtml(job?.job_id || job?.id || '')}" data-video-output-id="${escapeHtml(item.output_id || item.filename || '')}">Send to Upscale</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  function renderJobCard(job){
    const box = $('video-job-status-box');
    if (!box) return;
    if (!job || typeof job !== 'object'){
      box.style.display = 'none';
      box.innerHTML = '';
      updateActionButtons(null);
      return;
    }
    const state = String(job.status || job.state || 'queued').trim().toLowerCase() || 'queued';
    const compileNotes = Array.isArray(job.compile_notes) ? job.compile_notes.filter(Boolean) : [];
    const queueNumber = job.queue_number == null ? '—' : String(job.queue_number);
    const promptId = String(job.prompt_id || '').trim() || '—';
    const payload = job.payload && typeof job.payload === 'object' ? job.payload : {};
    const workflowType = String(payload.workflow_type || '').trim() || 'video_generation';
    const technicalProfile = workflowType === 'video_upscale'
      ? (String(payload.upscale_profile || '').trim() === 'quality_conservative' ? 'Upscale · Quality Conservative' : 'Upscale · Fast Local')
      : workflowType === 'video_repair'
        ? 'Repair · Local FFmpeg'
        : workflowType === 'video_interpolate'
          ? `Interpolate · ${String(payload.motion_quality_mode || 'balanced').trim() === 'smooth' ? 'Smoother motion' : String(payload.motion_quality_mode || 'balanced').trim() === 'detail_safe' ? 'Detail safe' : 'Balanced'}`
          : String(payload.profile || currentProfileDefinition()?.technical_label || '').trim();
    const runtime = job.video_runtime && typeof job.video_runtime === 'object' ? job.video_runtime : (workflowType === 'video_upscale' ? estimateUpscaleRuntime(payload) : workflowType === 'video_repair' ? estimateRepairRuntime(payload) : workflowType === 'video_interpolate' ? estimateInterpolateRuntime(payload) : estimateRuntime(payload));
    const pipeline = runtime.post_pipeline && typeof runtime.post_pipeline === 'object' ? runtime.post_pipeline : { enabled:false, label:'Generate only', next_stage_label:'', message:'' };
    const snapshot = statusSnapshot(job);
    const progressPercent = numberOr(job?.progress?.percent, state === 'completed' ? 100 : state === 'running' ? 65 : 5);
    const progressNote = snapshot.progressLabel || String(job?.progress?.detail || '').trim() || 'Queued';
    const manifestUrl = runtime.manifest_url || '';
    const openOutputUrl = runtime.latest_output_url || (Array.isArray(job.outputs) && job.outputs[0]?.view_url) || '';
    const retryOf = String(job?.lineage?.retry_of_job_id || '').trim();
    box.style.display = '';
    box.dataset.jobState = state;
    box.dataset.jobId = String(job.job_id || job.id || '').trim();
    box.innerHTML = `
      <div class="accordion-title">Runtime status</div>
      <div class="row" style="margin-top:12px; gap:8px; flex-wrap:wrap; align-items:center;">
        <span class="backend-chip ${escapeHtml(snapshot.chipClass)}">${escapeHtml(snapshot.stateLabel)}</span>
        <span class="badge">${escapeHtml(snapshot.workflowLabel)}</span>
        <span class="badge">${escapeHtml(heavinessBadge(runtime.estimated_heaviness))}</span>
        <span class="badge">Queue ${escapeHtml(queueNumber)}</span>
        ${technicalProfile ? `<span class="badge">${escapeHtml(technicalProfile)}</span>` : ''}
      </div>
      <div class="mini-note" style="margin-top:12px;">${escapeHtml(state === 'failed' ? plainFailureMessage(job) : (job.status_text || 'Neo is tracking the active video job.'))}</div>
      <div style="margin-top:14px; display:grid; gap:8px;">
        <div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Job id</span><strong style="text-align:right;">${escapeHtml(job.job_id || job.id || '—')}</strong></div>
        <div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Prompt id</span><strong style="text-align:right;">${escapeHtml(promptId)}</strong></div>
        <div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Current stage</span><strong style="text-align:right;">${escapeHtml(snapshot.currentStageLabel)}</strong></div>
        <div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Output count</span><strong style="text-align:right;">${escapeHtml(String(runtime.output_count || 0))}</strong></div>
        <div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Post pipeline</span><strong style="text-align:right;">${escapeHtml(pipeline.label || 'Generate only')}</strong></div>
        ${pipeline.enabled ? `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Next handoff</span><strong style="text-align:right;">${escapeHtml(pipeline.next_stage_label || (pipeline.status === 'complete' ? 'Finished' : 'Pending'))}</strong></div>` : ''}
        ${retryOf ? `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">Retry of</span><strong style="text-align:right;">${escapeHtml(retryOf)}</strong></div>` : ''}
      </div>
      <div style="margin-top:14px;">
        <div class="row-between" style="gap:12px;"><span class="mini-note">Progress</span><strong>${escapeHtml(String(progressPercent))}%</strong></div>
        <div style="height:8px; border-radius:999px; background:rgba(148,163,184,.12); overflow:hidden; margin-top:8px;"><div style="height:100%; width:${Math.max(0, Math.min(100, progressPercent))}%; background:rgba(99,102,241,.9);"></div></div>
        <div class="video-progress-note">${escapeHtml(progressNote)}</div>
      </div>
      ${pipeline.enabled ? `<div class="mini-note" style="margin-top:12px;">${escapeHtml(pipeline.message || (pipeline.next_stage_label ? `Next handoff: ${pipeline.next_stage_label}.` : 'Chained post pipeline active.'))}</div>` : ''}
      ${compileNotes.length ? `<div class="mini-note" style="margin-top:12px; display:grid; gap:6px;">${compileNotes.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}</div>` : ''}
      ${(manifestUrl || openOutputUrl) ? `<div class="row" style="margin-top:14px; gap:8px; flex-wrap:wrap;">${openOutputUrl ? `<a class="btn btn-small" href="${escapeHtml(openOutputUrl)}" target="_blank" rel="noopener">Open latest output</a>` : ''}${manifestUrl ? `<a class="btn btn-small" href="${escapeHtml(manifestUrl)}" target="_blank" rel="noopener">Open manifest</a>` : ''}</div>` : ''}
    `;
    updateActionButtons(job);
  }

  function syncSavedVideoPresetPicker(preserveSelection = true){
    const select = $('video-saved-preset-select');
    if (!select) return;
    const currentSelection = preserveSelection ? (savedVideoPresetSelectionId() || activeVideoPresetId || defaultVideoPresetId || '') : '';
    select.innerHTML = '<option value="">Saved video presets…</option>';
    savedVideoPresets.forEach(item => {
      const opt = document.createElement('option');
      opt.value = String(item.preset_id || item.id || '');
      const suffix = defaultVideoPresetId && defaultVideoPresetId === opt.value ? ' · default' : '';
      opt.textContent = `${item.name || 'Untitled video preset'}${suffix}`;
      select.appendChild(opt);
    });
    if (currentSelection && findSavedVideoPreset(currentSelection)) select.value = currentSelection;
  }

  function refreshSavedVideoPresetButtons(){
    const selectedId = savedVideoPresetSelectionId();
    const hasPreset = !!findSavedVideoPreset(selectedId);
    if ($('btn-video-load-saved-preset')) $('btn-video-load-saved-preset').disabled = !hasPreset;
    if ($('btn-video-update-video-preset')) $('btn-video-update-video-preset').disabled = !hasPreset;
    if ($('btn-video-delete-video-preset')) $('btn-video-delete-video-preset').disabled = !hasPreset;
    if ($('btn-video-set-default-video-preset')) $('btn-video-set-default-video-preset').disabled = !hasPreset;
    if ($('btn-video-clear-default-video-preset')) $('btn-video-clear-default-video-preset').disabled = !defaultVideoPresetId;
  }

  // Saved preset summaries
  function renderSavedVideoPresetSummary(){
    const card = $('video-saved-preset-summary');
    const badge = $('video-saved-preset-active-badge');
    const note = $('video-saved-preset-note');
    if (!card) return;
    const selectedId = savedVideoPresetSelectionId();
    const focusId = selectedId || activeVideoPresetId || defaultVideoPresetId || '';
    const focus = findSavedVideoPreset(focusId);
    const focusSummary = findSavedVideoPresetSummary(focusId);
    const activePreset = findSavedVideoPreset(activeVideoPresetId);
    const activeModified = activePreset ? !workspaceMatchesSavedVideoPreset(activePreset) : false;
    if (badge) {
      if (activePreset) badge.textContent = activeModified ? `${activePreset.name || 'Untitled video preset'} · modified` : (activePreset.name || 'Untitled video preset');
      else if (defaultVideoPresetId && findSavedVideoPreset(defaultVideoPresetId)) badge.textContent = 'Default preset available';
      else badge.textContent = 'No saved video preset';
    }
    if (note) {
      note.textContent = activePreset
        ? (activeModified
            ? 'This saved video preset was loaded earlier, but the current workspace config has changed since then. Saved video presets only own reusable run settings — not the main prompt or the source image file.'
            : 'This saved video preset currently matches the reusable run settings on screen. It still does not replace the main prompt or the source image file.')
        : 'Saved video presets are reusable backend config records. They load run settings like quality, duration, FPS, resolution, negative prompt, and optional quality direction. They do not replace the main prompt or the source image file.';
    }
    if (!savedVideoPresets.length) {
      card.innerHTML = '<div class="mini-note">No saved video presets yet. Save one when you land on a config you actually want to reuse.</div>';
      refreshSavedVideoPresetButtons();
      return;
    }
    const listHtml = savedVideoPresetSummaries.map(item => `
      <div style="padding:10px 0; border-top:1px solid rgba(148,163,184,.12);">
        <div class="row-between" style="gap:12px; align-items:flex-start;">
          <div>
            <strong>${escapeHtml(item.name || 'Untitled video preset')}</strong>
            <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.category_label || 'Custom')} · ${escapeHtml(item.quality_label || 'Balanced / Low VRAM')}</div>
            <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.output_label || '5s · 16 FPS · 832x480')}</div>
            <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.negative_prompt_included ? 'Negative prompt included' : 'No negative prompt')} · ${escapeHtml(item.creative_direction_included ? 'Creative direction included' : 'No creative direction')}</div>
            <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.adapter_pair_included ? 'Adapter pair included' : 'No adapter pair')}</div>
            <div class="mini-note" style="margin-top:4px;">${escapeHtml(item.post_pipeline_label || 'Generate only')}</div>
          </div>
          <div class="row" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;">
            ${defaultVideoPresetId === item.preset_id ? '<span class="badge">Default</span>' : ''}
            ${activeVideoPresetId === item.preset_id ? `<span class="badge">${activeModified && activePreset && activePreset.preset_id === item.preset_id ? 'Modified' : 'Active'}</span>` : ''}
          </div>
        </div>
      </div>
    `).join('');
    card.innerHTML = `
      <div class="accordion-title">Saved preset details</div>
      ${focusSummary
        ? `<div class="mini-note" style="margin-top:12px;">Selected preset: ${escapeHtml(focusSummary.name || 'Untitled video preset')} · ${escapeHtml(focusSummary.category_label || 'Custom')} · ${escapeHtml(focusSummary.output_label || '5s · 16 FPS · 832x480')}</div>`
        : '<div class="mini-note" style="margin-top:12px;">Pick a saved video preset to inspect it or load the reusable run settings into the current workspace.</div>'}
      <div style="margin-top:14px; display:grid; gap:0;">${listHtml}</div>
    `;
    if (focus?.category && $('video-saved-preset-category')) $('video-saved-preset-category').value = focus.category;
    refreshSavedVideoPresetButtons();
  }


  function syncVideoAdapterCatalogOptions(){
    const rows = Array.isArray(videoAdapterCatalog) ? videoAdapterCatalog.filter(Boolean) : [];
    ['video-adapter-single', 'video-adapter-high-noise', 'video-adapter-low-noise'].forEach(selectId => {
      const select = $(selectId);
      if (!select) return;
      const previous = String(select.value || '').trim();
      select.innerHTML = '<option value="">Select adapter…</option>';
      rows.forEach(item => {
        const name = typeof item === 'string' ? item : String(item?.name || item?.filename || item?.path || '').trim();
        if (!name) return;
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
      ensureSelectOption(selectId, previous);
      if (previous) select.value = previous;
    });
  }

  function syncVideoAdapterPresetPicker(preserveSelection = true){
    const select = $('video-adapter-preset-select');
    if (!select) return;
    const currentSelection = preserveSelection ? adapterPairPresetSelectionId() : '';
    select.innerHTML = '<option value="">Adapter pair presets…</option>';
    videoAdapterPairPresets.forEach(item => {
      const opt = document.createElement('option');
      opt.value = String(item.preset_id || item.id || '');
      opt.textContent = item.name || 'Untitled adapter pair';
      select.appendChild(opt);
    });
    if (currentSelection && findAdapterPairPreset(currentSelection)) select.value = currentSelection;
    else if (currentSelection) ensureSelectOption('video-adapter-preset-select', currentSelection);
  }

  function applyVideoAdapterPairPreset(presetOrId, { announce = true } = {}){
    if (!adapterUsesPairedMode()) {
      setStatusSafe('video-status', 'Adapter pair presets only apply on High Quality, where the paired high-noise / low-noise path exists.', 'warn');
      return;
    }
    const preset = typeof presetOrId === 'string' ? findAdapterPairPreset(presetOrId) : presetOrId;
    if (!preset) {
      setStatusSafe('video-status', 'Pick an adapter pair preset first.', 'warn');
      return;
    }
    ensureSelectOption('video-adapter-preset-select', preset.preset_id, preset.name);
    if ($('video-adapter-preset-select')) $('video-adapter-preset-select').value = String(preset.preset_id || '');
    if ($('video-adapters-enabled')) $('video-adapters-enabled').checked = true;
    ensureSelectOption('video-adapter-high-noise', preset.high_noise_adapter);
    if ($('video-adapter-high-noise')) $('video-adapter-high-noise').value = preset.high_noise_adapter || '';
    ensureSelectOption('video-adapter-low-noise', preset.low_noise_adapter);
    if ($('video-adapter-low-noise')) $('video-adapter-low-noise').value = preset.low_noise_adapter || '';
    if ($('video-adapter-strength')) $('video-adapter-strength').value = String(preset.strength ?? adapterSupport().default_strength ?? 0.8);
    if ($('video-adapter-strength-quality')) $('video-adapter-strength-quality').value = String(preset.strength ?? adapterSupport().default_strength ?? 0.8);
    renderVideoSummary();
    if (announce) setStatusSafe('video-status', `Loaded adapter pair preset: ${preset.name || 'Untitled adapter pair'}`, 'ok');
  }

  async function saveVideoAdapterPairPreset(updateExisting = false){
    if (!adapterUsesPairedMode()) {
      setStatusSafe('video-status', 'Adapter pair presets only belong to the High Quality paired path.', 'warn');
      return;
    }
    const selectedId = adapterPairPresetSelectionId();
    const selectedPreset = findAdapterPairPreset(selectedId);
    if (updateExisting && !selectedPreset) {
      setStatusSafe('video-status', 'Pick an adapter pair preset first if you want to update one.', 'warn');
      return;
    }
    if (!adapterHighNoiseValue() || !adapterLowNoiseValue()) {
      setStatusSafe('video-status', 'Both the high-noise and low-noise adapter slots are required.', 'warn');
      return;
    }
    const suggested = selectedPreset?.name || 'Video adapter pair';
    const nextName = String(window.prompt(updateExisting ? 'Update this adapter pair preset name if needed:' : 'Name this adapter pair preset:', suggested) || '').trim();
    if (!nextName) {
      setStatusSafe('video-status', 'Adapter pair preset action cancelled.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('name', nextName);
    form.append('high_noise_adapter', adapterHighNoiseValue());
    form.append('low_noise_adapter', adapterLowNoiseValue());
    form.append('strength', String(adapterStrengthValue()));
    if (updateExisting && selectedPreset?.preset_id) form.append('preset_id', selectedPreset.preset_id);
    try {
      const response = await fetch('/api/video/adapter-presets/save', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not save the adapter pair preset.');
      videoAdapterPairPresets = Array.isArray(data?.pair_presets) ? data.pair_presets : [];
      syncVideoAdapterPresetPicker(false);
      if ($('video-adapter-preset-select') && data?.preset?.preset_id) $('video-adapter-preset-select').value = data.preset.preset_id;
      renderVideoSummary();
      setStatusSafe('video-status', data?.message || `${updateExisting ? 'Updated' : 'Saved'} adapter pair preset.`, 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not save the adapter pair preset.', 'error');
    }
  }

  async function deleteVideoAdapterPairPreset(){
    const selectedId = adapterPairPresetSelectionId();
    const preset = findAdapterPairPreset(selectedId);
    if (!preset) {
      setStatusSafe('video-status', 'Pick an adapter pair preset first.', 'warn');
      return;
    }
    if (!window.confirm(`Delete adapter pair preset "${preset.name || 'Untitled adapter pair'}"?`)) return;
    const form = new FormData();
    form.append('preset_id', selectedId);
    try {
      const response = await fetch('/api/video/adapter-presets/delete', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not delete the adapter pair preset.');
      videoAdapterPairPresets = Array.isArray(data?.pair_presets) ? data.pair_presets : [];
      syncVideoAdapterPresetPicker(false);
      if ($('video-adapter-preset-select')) $('video-adapter-preset-select').value = '';
      renderVideoSummary();
      setStatusSafe('video-status', data?.message || 'Deleted adapter pair preset.', 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not delete the adapter pair preset.', 'error');
    }
  }

  function populateVideoBackendAssetSelect(selectId, values, currentValue, fallbackValue = '', savedLabel = '') {
    const select = $(selectId);
    if (!select) return '';
    const liveOptions = [];
    const seen = new Set();
    (Array.isArray(values) ? values : []).forEach(item => {
      const clean = String(item || '').trim();
      if (clean && !seen.has(clean)) {
        liveOptions.push(clean);
        seen.add(clean);
      }
    });
    const strictLiveCatalog = backendAssetCatalogLoaded && liveOptions.length > 0;
    const resolvedCurrent = strictLiveCatalog ? resolveVideoAssetAlias(currentValue, liveOptions) : String(currentValue || '').trim();
    const resolvedFallback = strictLiveCatalog ? resolveVideoAssetAlias(fallbackValue, liveOptions) : String(fallbackValue || '').trim();
    const selectedValue = strictLiveCatalog
      ? (resolvedCurrent || resolvedFallback || liveOptions[0] || '')
      : (resolvedCurrent || resolvedFallback || liveOptions[0] || '');
    const options = strictLiveCatalog ? liveOptions : (() => {
      const loose = [];
      const looseSeen = new Set();
      [fallbackValue, ...(Array.isArray(values) ? values : []), currentValue].forEach(item => {
        const clean = String(item || '').trim();
        if (clean && !looseSeen.has(clean)) {
          loose.push(clean);
          looseSeen.add(clean);
        }
      });
      return loose;
    })();
    select.innerHTML = '';
    options.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item === selectedValue && savedLabel && strictLiveCatalog ? `${item} · live` : item;
      select.appendChild(opt);
    });
    if (selectedValue && [...select.options].some(opt => String(opt.value || '').trim() === String(selectedValue || '').trim())) select.value = selectedValue;
    if (strictLiveCatalog) {
      const cleanCurrent = String(currentValue || '').trim();
      if (cleanCurrent && cleanCurrent !== selectedValue && !isLiveVideoAssetChoice(cleanCurrent, liveOptions)) {
        videoBackendAssetWarnings.push(`${cleanCurrent} is not in the live backend catalog for ${savedLabel || selectId}. Neo switched to ${selectedValue || 'the first available live option'}.`);
      }
      const cleanFallback = String(fallbackValue || '').trim();
      if (cleanFallback && cleanFallback !== selectedValue && !isLiveVideoAssetChoice(cleanFallback, liveOptions) && cleanFallback !== cleanCurrent) {
        videoBackendAssetWarnings.push(`${cleanFallback} is no longer a valid default for ${savedLabel || selectId}.`);
      }
    }
    return selectedValue;
  }

  function isKijaiWrapperEncoderName(value){
    const clean = String(value || '').trim().toLowerCase();
    if (!clean) return false;
    if (clean.includes('umt5-xxl-enc')) return true;
    return clean.includes('umt5') && !clean.includes('scaled') && (clean.includes('enc') || clean.includes('wanvideo'));
  }

  function videoModelLaneKind(value){
    const clean = String(value || '').trim().toLowerCase().split(/[\/]/).pop() || '';
    if (!clean) return '';
    if (/(^|[^a-z0-9])ti2v([^a-z0-9]|$)/.test(clean)) return 'ti2v';
    if (/(^|[^a-z0-9])i2v([^a-z0-9]|$)/.test(clean)) return 'i2v';
    if (/(^|[^a-z0-9])t2v([^a-z0-9]|$)/.test(clean)) return 't2v';
    return '';
  }

  function videoModeAllowsModelKind(mode, kind){
    const cleanMode = String(mode || 't2v').trim().toLowerCase() || 't2v';
    const cleanKind = String(kind || '').trim().toLowerCase();
    if (!cleanKind || cleanKind === 'ti2v') return true;
    if (cleanMode === 'i2v') return cleanKind === 'i2v';
    return cleanKind === 't2v';
  }

  function videoAssetBasename(value){
    return String(value || '').trim().toLowerCase().split(/[\/]/).pop() || '';
  }

  function nativeRequiredVaeForVideoModel(value){
    const clean = videoAssetBasename(value);
    if (!clean) return '';
    const isWan22 = clean.includes('wan2.2') || clean.includes('wan22');
    if (!isWan22) return '';
    const is5BTi2V = clean.includes('ti2v') && clean.includes('5b');
    if (is5BTi2V) return 'wan2.2_vae.safetensors';
    const is14B = clean.includes('14b') || clean.includes('a14b') || clean.includes('t2v') || clean.includes('i2v');
    if (is14B) return 'wan_2.1_vae.safetensors';
    return '';
  }

  function activeVideoModelGuardrailRows(profileValue = currentProfileValue()){
    const cleanProfile = normalizeProfile(profileValue || currentProfileValue());
    const engine = selectedVideoBackendEngine(cleanProfile);
    const assets = currentBackendAssets(cleanProfile);
    if (engine === 'kijai_wrapper' || cleanProfile === 'wan22_5b_balanced' || (cleanProfile === 'raw_free' && engine === 'kijai_wrapper')) {
      return [{ label:'Balanced model', value: String(assets.balanced_unet_name || '').trim(), selectId:'video-balanced-unet' }];
    }
    return [
      { label:'High-noise model', value: String(assets.quality_high_noise_unet_name || '').trim(), selectId:'video-quality-high-noise-unet' },
      { label:'Low-noise model', value: String(assets.quality_low_noise_unet_name || '').trim(), selectId:'video-quality-low-noise-unet' },
    ];
  }

  function activeVideoVaeGuardrailRow(profileValue = currentProfileValue()){
    const cleanProfile = normalizeProfile(profileValue || currentProfileValue());
    const engine = selectedVideoBackendEngine(cleanProfile);
    const assets = currentBackendAssets(cleanProfile);
    if (engine === 'kijai_wrapper' || cleanProfile === 'wan22_5b_balanced' || (cleanProfile === 'raw_free' && engine === 'kijai_wrapper')) {
      return { label:'Balanced VAE', value:String(assets.balanced_vae_name || '').trim(), selectId:'video-balanced-vae' };
    }
    return { label:'Quality VAE', value:String(assets.quality_vae_name || '').trim(), selectId:'video-quality-vae' };
  }

  function validateVideoWorkflowGuardrails(profileValue = currentProfileValue()){
    const mode = String(currentModeValue() || 't2v').trim().toLowerCase() || 't2v';
    const engine = selectedVideoBackendEngine(profileValue);
    const adapters = effectiveAdvancedAdapters();
    if (engine === 'kijai_wrapper' && adapters.enabled) {
      return { ok:false, message:'Kijai Wrapper + LoRAs / adapters is not supported in this build yet. Switch Backend engine to Wan Native or disable adapters before queueing.', focusId:'video-backend-engine-override' };
    }
    const expectedLabel = mode === 'i2v' ? 'Image to Video' : 'Text to Video';
    const allowedHint = mode === 'i2v' ? 'I2V or TI2V' : 'T2V or TI2V';
    const activeModels = activeVideoModelGuardrailRows(profileValue);
    for (const row of activeModels) {
      const kind = videoModelLaneKind(row.value);
      if (!row.value || !kind || videoModeAllowsModelKind(mode, kind)) continue;
      const actualLabel = kind === 'i2v' ? 'Image to Video' : (kind === 't2v' ? 'Text to Video' : 'Text/Image to Video');
      return {
        ok:false,
        message:`${row.label} "${row.value}" looks like an ${actualLabel} checkpoint, but the current mode is ${expectedLabel}. Pick a ${allowedHint} model for this lane.`,
        focusId: row.selectId,
      };
    }
    if (engine === 'wan_native') {
      const vaeRow = activeVideoVaeGuardrailRow(profileValue);
      const selectedVaeBase = videoAssetBasename(vaeRow.value);
      for (const row of activeModels) {
        const requiredVae = nativeRequiredVaeForVideoModel(row.value);
        if (!requiredVae || !selectedVaeBase || selectedVaeBase === requiredVae) continue;
        return {
          ok:false,
          message:`${row.label} "${row.value}" expects ${requiredVae} in Wan Native, but ${vaeRow.label} is set to "${vaeRow.value}". Switch the VAE to the matching native Wan file before queueing.`,
          focusId: vaeRow.selectId,
        };
      }
    }
    return { ok:true };
  }

  function selectedVideoBackendEngine(profileValue = currentProfileValue()) {
    const override = selectedVideoBackendEngineOverride();
    if (override === 'wan_native' || override === 'kijai_wrapper') return override;
    const cleanProfile = normalizeProfile(profileValue || currentProfileValue());
    if (cleanProfile !== 'wan22_5b_balanced' && cleanProfile !== 'raw_free') return 'wan_native';
    const assets = currentBackendAssets(cleanProfile);
    const encoder = String(assets.balanced_clip_name || '').trim();
    return isKijaiWrapperEncoderName(encoder) ? 'kijai_wrapper' : 'wan_native';
  }

  function currentVideoAssetValidationRows(profileValue = currentProfileValue()) {
    const cleanProfile = normalizeProfile(profileValue);
    const catalog = backendAssetCatalog();
    if (freeAssetModeEnabled() || cleanProfile === 'raw_free') {
      const all = catalog.all || {};
      if (cleanProfile === 'raw_free') {
        return selectedVideoBackendEngine(cleanProfile) === 'kijai_wrapper'
          ? [
              { label:'Balanced model', value: assetSelection('video-balanced-unet'), allowed: all.unet_models || [] },
              { label:'Balanced text encoder', value: assetSelection('video-balanced-encoder'), allowed: all.encoder_models || [] },
              { label:'Balanced VAE', value: assetSelection('video-balanced-vae'), allowed: all.vae_models || [] },
            ]
          : [
              { label:'High-noise model', value: assetSelection('video-quality-high-noise-unet'), allowed: all.unet_models || [] },
              { label:'Low-noise model', value: assetSelection('video-quality-low-noise-unet'), allowed: all.unet_models || [] },
              { label:'Quality text encoder', value: assetSelection('video-quality-encoder'), allowed: all.encoder_models || [] },
              { label:'Quality VAE', value: assetSelection('video-quality-vae'), allowed: all.vae_models || [] },
            ];
      }
      return cleanProfile === 'wan22_5b_balanced'
        ? [
            { label:'Balanced model', value: assetSelection('video-balanced-unet'), allowed: all.unet_models || [] },
            { label:'Balanced text encoder', value: assetSelection('video-balanced-encoder'), allowed: all.encoder_models || [] },
            { label:'Balanced VAE', value: assetSelection('video-balanced-vae'), allowed: all.vae_models || [] },
          ]
        : [
            { label:'High-noise model', value: assetSelection('video-quality-high-noise-unet'), allowed: all.unet_models || [] },
            { label:'Low-noise model', value: assetSelection('video-quality-low-noise-unet'), allowed: all.unet_models || [] },
            { label:'Quality text encoder', value: assetSelection('video-quality-encoder'), allowed: all.encoder_models || [] },
            { label:'Quality VAE', value: assetSelection('video-quality-vae'), allowed: all.vae_models || [] },
          ];
    }
    if (cleanProfile === 'wan22_5b_balanced') {
      const balanced = catalog.balanced || {};
      return [
        { label:'Balanced model', value: assetSelection('video-balanced-unet'), allowed: balanced.unet_models || [] },
        { label:'Balanced text encoder', value: assetSelection('video-balanced-encoder'), allowed: balanced.encoder_models || [] },
        { label:'Balanced VAE', value: assetSelection('video-balanced-vae'), allowed: balanced.vae_models || [] },
      ];
    }
    const quality = cleanProfile === 'wan22_14b_i2v_quality' ? (catalog.quality_i2v || {}) : (catalog.quality_t2v || {});
    return [
      { label:'High-noise model', value: assetSelection('video-quality-high-noise-unet'), allowed: quality.high_noise_unet_models || [] },
      { label:'Low-noise model', value: assetSelection('video-quality-low-noise-unet'), allowed: quality.low_noise_unet_models || [] },
      { label:'Quality text encoder', value: assetSelection('video-quality-encoder'), allowed: quality.encoder_models || [] },
      { label:'Quality VAE', value: assetSelection('video-quality-vae'), allowed: quality.vae_models || [] },
    ];
  }

  async function validateLiveVideoBackendAssets(profileValue = currentProfileValue()) {
    if (!backendAssetCatalogLoaded) await loadVideoBackendAssets(true);
    const catalog = backendAssetCatalog();
    const counts = catalog.counts || {};
    const hasAnyLiveAssets = Number(counts.unet || 0) || Number(counts.encoder || 0) || Number(counts.vae || 0);
    if (!backendAssetCatalogLoaded || !hasAnyLiveAssets) {
      return { ok:false, message:'Video asset validation needs a live backend catalog first. Refresh assets, then retry.' };
    }
    const engine = selectedVideoBackendEngine(profileValue);
    const wrapper = catalog.wrapper || {};
    if (engine === 'kijai_wrapper') {
      if (!['wan22_5b_balanced','raw_free'].includes(normalizeProfile(profileValue))) {
        return { ok:false, message:'Kijai Wrapper routing is currently limited to the Balanced / Low VRAM or Raw / Free video profiles in this build.' };
      }
      if (!wrapper.available) {
        const missing = Array.isArray(wrapper.missing_nodes) && wrapper.missing_nodes.length ? ` Missing wrapper nodes: ${wrapper.missing_nodes.join(', ')}.` : '';
        return { ok:false, message:`The connected ComfyUI build does not expose the required Kijai WanVideoWrapper nodes yet. Install or refresh the wrapper extension, then retry.${missing}` };
      }
      if (String(currentModeValue() || 't2v').trim().toLowerCase() === 'i2v' && !wrapper.i2v_available) {
        return { ok:false, message:'The connected ComfyUI build is missing WanVideoImageToVideoEncode, so Balanced I2V cannot use the Kijai Wrapper lane yet.' };
      }
    } else {
      const encoderLoader = catalog.encoder_loader || {};
      const wanSupported = !!encoderLoader.wan_supported;
      if (!wanSupported) {
        const advertised = Array.isArray(encoderLoader.supported_types) && encoderLoader.supported_types.length ? ` Advertised CLIPLoader types: ${encoderLoader.supported_types.join(', ')}.` : '';
        return { ok:false, message:`The connected ComfyUI build does not advertise CLIPLoader type "wan" for Wan video text encoders. Update ComfyUI, refresh Video assets, then retry.${advertised}` };
      }
    }
    const rows = currentVideoAssetValidationRows(profileValue);
    for (const row of rows) {
      const chosen = String(row.value || '').trim();
      const allowed = Array.isArray(row.allowed) ? row.allowed.map(item => String(item || '').trim()).filter(Boolean) : [];
      if (!chosen) return { ok:false, message:`${row.label} is required before queueing video generation.` };
      if (!allowed.length) return { ok:false, message:`${row.label} could not be validated because the live backend catalog did not return any choices for that field.` };
      if (!allowed.includes(chosen)) {
        const resolved = resolveVideoAssetAlias(chosen, allowed);
        if (resolved && allowed.includes(resolved)) {
          const mapping = { 'Balanced model':'video-balanced-unet', 'Balanced text encoder':'video-balanced-encoder', 'Balanced VAE':'video-balanced-vae', 'High-noise model':'video-quality-high-noise-unet', 'Low-noise model':'video-quality-low-noise-unet', 'Quality text encoder':'video-quality-encoder', 'Quality VAE':'video-quality-vae' };
          const selectId = mapping[row.label];
          if (selectId && $(selectId)) $(selectId).value = resolved;
          continue;
        }
        return { ok:false, message:`${row.label} "${chosen}" is not in the live backend catalog. Refresh assets or pick one of the current backend choices.` };
      }
    }
    return { ok:true };
  }



  function syncVideoBackendAssetSelectors(profileValue = currentProfileValue()) {
    const catalog = backendAssetCatalog();
    const allCatalog = catalog.all || {};
    const useFreeMode = freeAssetModeEnabled() || isRawFreeProfile(profileValue);
    const balancedCatalog = useFreeMode ? {
      unet_models: allCatalog.unet_models || [],
      encoder_models: allCatalog.encoder_models || [],
      vae_models: allCatalog.vae_models || [],
    } : (catalog.balanced || {});
    const qualityCatalog = useFreeMode ? {
      high_noise_unet_models: allCatalog.unet_models || [],
      low_noise_unet_models: allCatalog.unet_models || [],
      encoder_models: allCatalog.encoder_models || [],
      vae_models: allCatalog.vae_models || [],
    } : (normalizeProfile(profileValue) === 'wan22_14b_i2v_quality' ? (catalog.quality_i2v || {}) : (catalog.quality_t2v || {}));
    const assets = currentBackendAssets(profileValue);
    const balancedDefaults = defaultBalancedBackendAssets();
    const qualityDefaults = defaultQualityBackendAssets(profileValue);
    populateVideoBackendAssetSelect('video-balanced-unet', balancedCatalog.unet_models || [], assets.balanced_unet_name || balancedDefaults.unet_name || '', balancedDefaults.unet_name || '');
    populateVideoBackendAssetSelect('video-balanced-encoder', balancedCatalog.encoder_models || [], assets.balanced_clip_name || balancedDefaults.clip_name || '', balancedDefaults.clip_name || '');
    populateVideoBackendAssetSelect('video-balanced-vae', balancedCatalog.vae_models || [], assets.balanced_vae_name || balancedDefaults.vae_name || '', balancedDefaults.vae_name || '');
    populateVideoBackendAssetSelect('video-quality-high-noise-unet', qualityCatalog.high_noise_unet_models || [], assets.quality_high_noise_unet_name || qualityDefaults.high_noise_unet_name || '', qualityDefaults.high_noise_unet_name || '');
    populateVideoBackendAssetSelect('video-quality-low-noise-unet', qualityCatalog.low_noise_unet_models || [], assets.quality_low_noise_unet_name || qualityDefaults.low_noise_unet_name || '', qualityDefaults.low_noise_unet_name || '');
    populateVideoBackendAssetSelect('video-quality-encoder', qualityCatalog.encoder_models || [], assets.quality_clip_name || qualityDefaults.clip_name || '', qualityDefaults.clip_name || '');
    populateVideoBackendAssetSelect('video-quality-vae', qualityCatalog.vae_models || [], assets.quality_vae_name || qualityDefaults.vae_name || '', qualityDefaults.vae_name || '');
  }

  function renderVideoBackendAssetSummary(){
    const assetCard = $('video-backend-assets-card');
    const card = $('video-backend-assets-summary');
    const badge = $('video-backend-assets-active-badge');
    const note = $('video-backend-assets-note');
    const status = $('video-backend-assets-status');
    const ggufNote = $('video-backend-assets-gguf-note');
    if (!card) return;
    const quality = isQualityProfile();
    const profile = currentProfileValue();
    const engine = selectedVideoBackendEngine(profile);
    const assets = currentBackendAssets(profile);
    const freeMode = freeAssetModeEnabled();
    const catalog = backendAssetCatalog();
    const counts = catalog.counts || {};
    const encoderLoader = catalog.encoder_loader || {};
    const wrapper = catalog.wrapper || {};
    const rawProfile = isRawFreeProfile(profile);
    if ($('video-balanced-assets-group')) $('video-balanced-assets-group').style.display = (quality && !rawProfile) || (rawProfile && engine !== 'kijai_wrapper') ? 'none' : '';
    if ($('video-quality-assets-group')) $('video-quality-assets-group').style.display = quality || (rawProfile && engine !== 'kijai_wrapper') ? '' : 'none';
    if (badge) badge.textContent = backendAssetsMatchDefaults(profile) ? 'Using defaults' : 'Custom override';
    if (note) {
      if (rawProfile) {
        note.textContent = engine === 'kijai_wrapper'
          ? 'Raw / Free is currently routing through Kijai Wrapper, so the balanced asset trio is the active stack.'
          : 'Raw / Free is currently routing through native Wan, so the manual quality stack is the active set.';
      } else if (quality) {
        note.textContent = 'High Quality resolves a paired high-noise / low-noise Wan stack. Override it only when you actually need a different backend asset set.';
      } else if (engine === 'kijai_wrapper') {
        note.textContent = 'Balanced auto-routes through Kijai WanVideoWrapper because the selected text encoder is a wrapper encoder. Use this lane only when you intentionally need the wrapper path.';
      } else {
        note.textContent = 'Balanced resolves a single native Wan 2.2 5B stack. Override it only when the backend catalog shows a better-matched local model set.';
      }
    }
    if (status) {
      const baseStatus = backendAssetCatalogLoaded
        ? `Loaded ${Number(counts.unet || 0)} model, ${Number(counts.encoder || 0)} encoder, and ${Number(counts.vae || 0)} VAE choices from the current video backend.`
        : 'Load the video backend catalog to pick real video assets. This card stays profile-aware instead of pretending Video works like a universal checkpoint picker.';
      let engineStatus = '';
      if (backendAssetCatalogLoaded) {
        if (engine === 'kijai_wrapper') {
          engineStatus = wrapper.available
            ? ' Kijai Wrapper support is available.'
            : ` Kijai Wrapper support is missing${Array.isArray(wrapper.missing_nodes) && wrapper.missing_nodes.length ? ` (${wrapper.missing_nodes.join(', ')})` : ''}. Install or refresh the wrapper extension before queueing wrapper jobs.`;
        } else {
          engineStatus = encoderLoader.wan_supported
            ? ' Wan-native CLIPLoader support is available.'
            : ` Wan-native CLIPLoader support is missing${Array.isArray(encoderLoader.supported_types) && encoderLoader.supported_types.length ? ` (advertised types: ${encoderLoader.supported_types.join(', ')})` : ''}. Update ComfyUI before queueing Wan video jobs.`;
        }
      }
      const combinedStatus = `${baseStatus}${engineStatus}`.trim();
      status.textContent = videoBackendAssetWarnings.length ? `${combinedStatus} Cleaned stale selections: ${videoBackendAssetWarnings[0]}` : combinedStatus;
    }
    const gguf = catalog.gguf || backendAssetDefaults().gguf || {};
    const detectedGgufCount = Array.isArray(gguf.detected_unet_models) ? gguf.detected_unet_models.length : 0;
    if (ggufNote) {
      if (engine === 'kijai_wrapper') {
        ggufNote.textContent = (wrapper.note || 'Balanced can auto-route through Kijai WanVideoWrapper when the selected text encoder is wrapper-specific.') + ' Wrapper jobs do not use the native GGUF UNET routing path.';
      } else {
        ggufNote.textContent = gguf.available
          ? `GGUF-aware Wan UNET detection is active. ${detectedGgufCount || 0} GGUF UNET choice${detectedGgufCount === 1 ? '' : 's'} detected, and selected .gguf UNETs will route through UnetLoaderGGUF while the encoder + VAE stay on the native Wan path.`
          : (gguf.note || 'Video can detect Wan GGUF UNET assets when the backend exposes UnetLoaderGGUF choices through object_info. Encoders and VAEs still stay on the native Wan path.');
      }
    }
    const rows = (rawProfile ? (engine !== 'kijai_wrapper') : quality)
      ? [
          ['High-noise model', assets.quality_high_noise_unet_name || '—'],
          ['Low-noise model', assets.quality_low_noise_unet_name || '—'],
          ['Text encoder', assets.quality_clip_name || '—'],
          ['VAE', assets.quality_vae_name || '—'],
        ]
      : [
          ['Balanced model', assets.balanced_unet_name || '—'],
          ['Text encoder', assets.balanced_clip_name || '—'],
          ['VAE', assets.balanced_vae_name || '—'],
        ];
    card.innerHTML = rows.map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('');
  }


  async function loadVideoBackendAssets(silent = true){
    try {
      const response = await fetch('/api/video/assets');
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not load video backend assets.');

      const catalog = data?.catalog && typeof data.catalog === 'object' ? data.catalog : {};
      const counts = catalog?.counts || {};
      const hasLiveChoices = Boolean(
        Number(counts.unet || 0)
        || Number(counts.encoder || 0)
        || Number(counts.vae || 0)
      );

      videoBackendAssetCatalog = catalog;
      backendAssetCatalogLoaded = !!data?.connected && hasLiveChoices;
      videoBackendAssetWarnings = [];

      syncVideoBackendAssetSelectors(currentProfileValue());
      renderVideoBackendAssetSummary();

      if (!silent && !backendAssetCatalogLoaded) {
        setStatusSafe(
          'video-status',
          data?.connected
            ? 'Video backend connected, but no live video assets were returned yet.'
            : 'Connect the video backend to load live video assets.',
          'warn'
        );
        return;
      }

      if (!silent && videoBackendAssetWarnings.length) {
        setStatusSafe('video-status', `Cleaned stale video asset selections. ${videoBackendAssetWarnings[0]}`, 'warn');
      }
    } catch (error) {
      backendAssetCatalogLoaded = false;
      videoBackendAssetCatalog = {};
      videoBackendAssetWarnings = [];

      syncVideoBackendAssetSelectors(currentProfileValue());
      renderVideoBackendAssetSummary();

      if (!silent) {
        setStatusSafe('video-status', error?.message || 'Could not load video backend assets.', 'warn');
      }
    }
  }

  async function loadVideoAdapters(silent = true){
    try {
      const response = await fetch('/api/video/adapters');
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not load the video adapter catalog.');
      videoAdapterCatalog = Array.isArray(data?.loras) ? data.loras : [];
      videoAdapterPairPresets = Array.isArray(data?.pair_presets) ? data.pair_presets : [];
      adapterCatalogLoaded = !!data?.connected;
      syncVideoAdapterCatalogOptions();
      syncVideoAdapterPresetPicker(true);
      renderVideoSummary();
      if (!silent) setStatusSafe('video-status', data?.backend_ready ? 'Refreshed the video adapter catalog.' : 'Adapter catalog refreshed, but the backend is not fully ready for the selected video adapter path yet.', data?.backend_ready ? 'ok' : 'warn');
    } catch (error) {
      adapterCatalogLoaded = false;
      if (!silent) setStatusSafe('video-status', error?.message || 'Could not load the video adapter catalog.', 'warn');
      renderVideoSummary();
    }
  }

  function renderVideoAdapterSummary(){
    const card = $('video-adapter-summary');
    const badge = $('video-adapter-active-badge');
    const note = $('video-adapter-note');
    const status = $('video-adapter-status');
    const adapterCard = $('video-adapter-card');
    const singleGroup = $('video-single-adapters-group');
    const pairedGroup = $('video-paired-adapters-group');
    const pairPresetSelect = $('video-adapter-preset-select');
    const qualityStrength = $('video-adapter-strength-quality');
    const baseStrength = $('video-adapter-strength');
    if (!card) return;
    const quality = adapterUsesPairedMode();
    const adapters = rememberedAdvancedAdapters();
    const capability = adapterCapability();
    const supported = supportsAdaptersForProfile();
    const selectedPreset = findAdapterPairPreset(adapters.pair_preset_id);
    if (adapterCard) adapterCard.style.display = '';
    const disableAdapterControls = !supported;
    if (singleGroup) singleGroup.style.display = quality ? 'none' : 'grid';
    if (pairedGroup) pairedGroup.style.display = quality ? 'grid' : 'none';
    if (pairPresetSelect) pairPresetSelect.disabled = disableAdapterControls || !quality;
    ['btn-video-load-adapter-preset','btn-video-save-adapter-preset','btn-video-update-adapter-preset','btn-video-delete-adapter-preset'].forEach((id) => { const el = $(id); if (el) el.disabled = disableAdapterControls || !quality; });
    ['video-adapters-enabled','video-adapter-single','video-adapter-high-noise','video-adapter-low-noise','video-adapter-strength','video-adapter-strength-quality'].forEach((id) => { const el = $(id); if (el) el.disabled = disableAdapterControls; });
    if (qualityStrength && baseStrength && !qualityStrength.value) qualityStrength.value = baseStrength.value || String(adapterSupport().default_strength || 0.8);
    if (baseStrength && qualityStrength && quality && qualityStrength.value) baseStrength.value = qualityStrength.value;
    if (baseStrength && qualityStrength && !quality && baseStrength.value) qualityStrength.value = baseStrength.value;
    if (badge) {
      if (!supported) badge.textContent = 'Unsupported';
      else if (quality && adapters.enabled && adapters.high_noise_adapter && adapters.low_noise_adapter) badge.textContent = selectedPreset ? `${selectedPreset.name || 'Adapter pair'} · active` : 'Paired adapters active';
      else if (!quality && adapters.enabled && adapters.single_adapter) badge.textContent = 'Single adapter active';
      else if (quality && selectedPreset) badge.textContent = selectedPreset.name || 'Adapter pair preset';
      else badge.textContent = 'No adapter';
    }
    if (note) {
      note.textContent = quality
        ? 'High Quality keeps the paired high-noise / low-noise adapter path. Use it when the expert split is worth the heavier setup.'
        : 'Balanced now keeps a simple first-pass LoRA / adapter lane for fast custom workflows like lightning-style first generation.';
    }
    if (status) {
      if (!supported) status.textContent = capability.unsupported_reason || 'This profile does not expose a compatible adapter lane.';
      else if (!adapterCatalogLoaded) status.textContent = 'Load the video backend catalog to pick real LoRA / adapter names. Saved values still stay visible even when the backend is offline.';
      else if (!adapters.enabled) status.textContent = quality ? 'Paired adapters are optional. Enable them only when the matched quality pair is actually part of the plan.' : 'Single-adapter mode is optional. Enable it when you want a first-pass custom LoRA / adapter load on Balanced.';
      else if (quality && (!adapters.high_noise_adapter || !adapters.low_noise_adapter)) status.textContent = 'Both slots are required when paired adapters are enabled.';
      else if (!quality && !adapters.single_adapter) status.textContent = 'Pick a LoRA / adapter for the Balanced single-adapter lane.';
      else if (quality) status.textContent = selectedPreset ? `Using saved pair preset "${selectedPreset.name || 'Untitled adapter pair'}" at strength ${adapters.strength}.` : `Using a custom paired adapter load at strength ${adapters.strength}.`;
      else status.textContent = `Using ${adapters.single_adapter || 'the selected adapter'} on the Balanced first-pass lane at strength ${adapters.strength}.`;
    }
    const rows = [
      ['Adapter mode', quality ? 'Paired quality adapters' : 'Single first-pass adapter'],
      ['Catalog state', adapterCatalogLoaded ? (videoAdapterCatalog.length ? `${videoAdapterCatalog.length} adapters visible` : 'Connected, but no adapters listed') : 'Catalog not loaded'],
    ];
    if (quality) {
      rows.push(['Pair preset', selectedPreset ? (selectedPreset.name || 'Untitled adapter pair') : (adapters.pair_preset_id ? adapters.pair_preset_id : 'None selected')]);
      rows.push(['High-noise slot', adapters.high_noise_adapter || 'Not set']);
      rows.push(['Low-noise slot', adapters.low_noise_adapter || 'Not set']);
    } else {
      rows.push(['Balanced adapter', adapters.single_adapter || 'Not set']);
      rows.push(['Preset behavior', 'Manual override stays allowed']);
    }
    rows.push(['Strength', String(adapters.strength ?? adapterSupport().default_strength ?? 0.8)]);
    card.innerHTML = rows.map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('');
  }

  async function loadSavedVideoPresets(silent = true){
    try {
      const response = await fetch('/api/video/presets');
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not load saved video presets.');
      savedVideoPresets = Array.isArray(data?.presets) ? data.presets : [];
      savedVideoPresetSummaries = Array.isArray(data?.summaries) ? data.summaries : [];
      defaultVideoPresetId = String(data?.default_preset_id || '').trim();
      syncSavedVideoPresetPicker(true);
      if (!activeVideoPresetId && defaultVideoPresetId && !workspacePresetStartupRef()) {
        applySavedVideoPreset(defaultVideoPresetId, { announce:false, fromStartup:true });
      } else {
        renderSavedVideoPresetSummary();
      }
    } catch (error) {
      if (!silent) setStatusSafe('video-status', error?.message || 'Could not load saved video presets.', 'warn');
    }
  }

  function applySavedVideoPreset(presetOrId, { announce = true, fromStartup = false } = {}){
    const preset = typeof presetOrId === 'string' ? findSavedVideoPreset(presetOrId) : presetOrId;
    if (!preset) {
      setStatusSafe('video-status', 'Pick a saved video preset first.', 'warn');
      return;
    }
    const request = preset.request && typeof preset.request === 'object' ? preset.request : {};
    const creative = preset.creative_direction && typeof preset.creative_direction === 'object' ? preset.creative_direction : {};
    const assets = preset.backend_assets && typeof preset.backend_assets === 'object' ? preset.backend_assets : preset;
    const adapters = preset.advanced_adapters && typeof preset.advanced_adapters === 'object' ? preset.advanced_adapters : {};
    setValue('video-mode', preset.mode || 't2v');
    setValue('video-profile', preset.profile || 'wan22_5b_balanced');
    setValue('video-duration', request.duration_seconds || 5);
    setValue('video-fps', request.fps || 16);
    setValue('video-size', request.size_preset || '832x480');
    if (request.width) setValue('video-width', request.width, []);
    if (request.height) setValue('video-height', request.height, []);
    applyVideoSizeUiState();
    setValue('video-negative', request.negative_prompt || '');
    setValue('video-seed', request.seed || '');
    setValue('video-post-pipeline-template', preset.post_pipeline_template || defaults().post_pipeline_template || 'generate_only');
    setValue('video-quality-style', creative.style_prompt || '');
    setValue('video-quality-camera', creative.camera_prompt || '');
    applyBackendAssetsToForm(assets, preset.profile || 'wan22_5b_balanced');
    if ($('video-adapters-enabled')) $('video-adapters-enabled').checked = !!adapters.enabled;
    ensureSelectOption('video-adapter-preset-select', adapters.pair_preset_id, adapters.pair_preset_name);
    if ($('video-adapter-preset-select')) $('video-adapter-preset-select').value = adapters.pair_preset_id || '';
    ensureSelectOption('video-adapter-single', adapters.single_adapter);
    if ($('video-adapter-single')) $('video-adapter-single').value = adapters.single_adapter || '';
    ensureSelectOption('video-adapter-high-noise', adapters.high_noise_adapter);
    if ($('video-adapter-high-noise')) $('video-adapter-high-noise').value = adapters.high_noise_adapter || '';
    ensureSelectOption('video-adapter-low-noise', adapters.low_noise_adapter);
    if ($('video-adapter-low-noise')) $('video-adapter-low-noise').value = adapters.low_noise_adapter || '';
    if ($('video-adapter-strength')) $('video-adapter-strength').value = String(adapters.strength ?? adapterSupport().default_strength ?? 0.8);
    if ($('video-adapter-strength-quality')) $('video-adapter-strength-quality').value = String(adapters.strength ?? adapterSupport().default_strength ?? 0.8);
    activeVideoPresetId = String(preset.preset_id || preset.id || '').trim();
    if ($('video-saved-preset-select')) $('video-saved-preset-select').value = activeVideoPresetId;
    if ($('video-saved-preset-category')) $('video-saved-preset-category').value = preset.category || 'custom';
    renderVideoSummary();
    renderSavedVideoPresetSummary();
    if (announce) setStatusSafe('video-status', `${fromStartup ? 'Loaded default video preset' : 'Loaded saved video preset'}: ${preset.name || 'Untitled video preset'}`, 'ok');
  }

  async function saveVideoPresetRecord(updateExisting = false){
    const selectedId = savedVideoPresetSelectionId();
    const selectedPreset = findSavedVideoPreset(selectedId);
    if (updateExisting && !selectedPreset) {
      setStatusSafe('video-status', 'Pick a saved video preset first if you want to update one.', 'warn');
      return;
    }
    const categoryLabel = $('video-saved-preset-category')?.selectedOptions?.[0]?.textContent?.trim() || 'Custom';
    const suggested = selectedPreset?.name || `${categoryLabel} · ${currentProfileLabel()}`;
    const nextName = String(window.prompt(updateExisting ? 'Update this saved video preset name if needed:' : 'Name this saved video preset:', suggested) || '').trim();
    if (!nextName) {
      setStatusSafe('video-status', 'Saved video preset action cancelled.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('name', nextName);
    if (updateExisting && selectedPreset?.preset_id) form.append('preset_id', selectedPreset.preset_id);
    form.append('category', currentSavedVideoPresetCategory());
    form.append('settings_json', JSON.stringify(captureSavedVideoPresetPayload()));
    try {
      const response = await fetch('/api/video/presets/save', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not save the video preset.');
      savedVideoPresets = Array.isArray(data?.presets) ? data.presets : [];
      savedVideoPresetSummaries = Array.isArray(data?.summaries) ? data.summaries : [];
      defaultVideoPresetId = String(data?.default_preset_id || '').trim();
      activeVideoPresetId = String(data?.preset?.preset_id || '').trim() || activeVideoPresetId;
      syncSavedVideoPresetPicker(false);
      if ($('video-saved-preset-select') && activeVideoPresetId) $('video-saved-preset-select').value = activeVideoPresetId;
      renderSavedVideoPresetSummary();
      setStatusSafe('video-status', data?.message || `${updateExisting ? 'Updated' : 'Saved'} video preset.`, 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not save the video preset.', 'error');
    }
  }

  async function deleteVideoPresetRecord(){
    const selectedId = savedVideoPresetSelectionId();
    const preset = findSavedVideoPreset(selectedId);
    if (!preset) {
      setStatusSafe('video-status', 'Pick a saved video preset first.', 'warn');
      return;
    }
    if (!window.confirm(`Delete saved video preset "${preset.name || 'Untitled video preset'}"?`)) return;
    const form = new FormData();
    form.append('preset_id', selectedId);
    try {
      const response = await fetch('/api/video/presets/delete', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not delete the video preset.');
      savedVideoPresets = Array.isArray(data?.presets) ? data.presets : [];
      savedVideoPresetSummaries = Array.isArray(data?.summaries) ? data.summaries : [];
      defaultVideoPresetId = String(data?.default_preset_id || '').trim();
      if (activeVideoPresetId === selectedId) activeVideoPresetId = '';
      syncSavedVideoPresetPicker(false);
      renderSavedVideoPresetSummary();
      setStatusSafe('video-status', data?.message || 'Deleted video preset.', 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not delete the video preset.', 'error');
    }
  }

  async function setDefaultVideoPresetRecord(){
    const selectedId = savedVideoPresetSelectionId();
    if (!findSavedVideoPreset(selectedId)) {
      setStatusSafe('video-status', 'Pick a saved video preset first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('preset_id', selectedId);
    try {
      const response = await fetch('/api/video/presets/set-default', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not set the default video preset.');
      savedVideoPresets = Array.isArray(data?.presets) ? data.presets : [];
      savedVideoPresetSummaries = Array.isArray(data?.summaries) ? data.summaries : [];
      defaultVideoPresetId = String(data?.default_preset_id || '').trim();
      syncSavedVideoPresetPicker(true);
      renderSavedVideoPresetSummary();
      setStatusSafe('video-status', data?.message || 'Default video preset set.', 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not set the default video preset.', 'error');
    }
  }

  async function clearDefaultVideoPresetRecord(){
    try {
      const response = await fetch('/api/video/presets/clear-default', { method:'POST' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not clear the default video preset.');
      savedVideoPresets = Array.isArray(data?.presets) ? data.presets : [];
      savedVideoPresetSummaries = Array.isArray(data?.summaries) ? data.summaries : [];
      defaultVideoPresetId = '';
      syncSavedVideoPresetPicker(true);
      renderSavedVideoPresetSummary();
      setStatusSafe('video-status', data?.message || 'Default video preset cleared.', 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not clear the default video preset.', 'error');
    }
  }

  function renderVideoHistory(history){
    const card = $('video-output-history');
    if (!card) return;
    const rows = Array.isArray(history) ? history.filter(item => item && typeof item === 'object') : [];
    if (!rows.length){
      card.style.display = '';
      card.innerHTML = `
        <div class="accordion-title">Output history</div>
        <div class="video-empty-card-copy" style="margin-top:12px;">No recent video jobs yet. Once you queue generation or a post lane, Neo will keep the latest local job history, manifests, retry actions, and post-lane handoff shortcuts here.</div>
      `;
      return;
    }
    card.style.display = '';
    card.innerHTML = `
      <div class="accordion-title">Output history</div>
      <div class="mini-note" style="margin-top:12px;">Recent Video jobs Neo knows about on this machine. Use this to retry something known-good, reopen the manifest later, or send a finished clip into a post lane without rebuilding the request.</div>
      <div style="margin-top:14px; display:grid; gap:10px;">
        ${rows.map((job, index) => {
          const state = String(job.status || job.state || 'queued').trim().toLowerCase() || 'queued';
          const workflowType = String(job?.payload?.workflow_type || '').trim() || 'video_generation';
          const runtime = job.video_runtime && typeof job.video_runtime === 'object'
            ? job.video_runtime
            : (workflowType === 'video_upscale' ? estimateUpscaleRuntime(job.payload || {}) : workflowType === 'video_repair' ? estimateRepairRuntime(job.payload || {}) : workflowType === 'video_interpolate' ? estimateInterpolateRuntime(job.payload || {}) : estimateRuntime(job.payload || {}));
          const pipeline = runtime.post_pipeline && typeof runtime.post_pipeline === 'object' ? runtime.post_pipeline : { enabled:false, label:'Generate only', next_stage_label:'' };
          const snap = statusSnapshot(job);
          const latestOutputUrl = runtime.latest_output_url || (Array.isArray(job.outputs) && job.outputs[0]?.view_url) || '';
          const latestOutputId = (Array.isArray(job.outputs) && (job.outputs[0]?.output_id || job.outputs[0]?.filename)) || '';
          const title = index === 0 ? `Latest ${snap.workflowLabel}` : `${snap.workflowLabel} ${index + 1}`;
          return `
            <div style="padding:12px 0; border-top:1px solid rgba(148,163,184,.12);">
              <div class="row-between" style="gap:12px; align-items:flex-start;">
                <div>
                  <strong>${escapeHtml(title)}</strong>
                  <div class="mini-note" style="margin-top:4px;">${escapeHtml(job.job_id || job.id || '—')}</div>
                  <div class="row" style="margin-top:8px; gap:8px; flex-wrap:wrap; align-items:center;">
                    <span class="backend-chip ${escapeHtml(snap.chipClass)}">${escapeHtml(snap.stateLabel)}</span>
                    <span class="badge">${escapeHtml(heavinessBadge(runtime.estimated_heaviness))}</span>
                    <span class="badge">${escapeHtml(String(runtime.output_count || 0))} outputs</span>
                    <span class="badge">${escapeHtml(pipeline.label || 'Generate only')}</span>
                  </div>
                  <div class="mini-note" style="margin-top:8px;">${escapeHtml(state === 'failed' ? plainFailureMessage(job) : (job.status_text || snap.progressLabel || ''))}</div>
                  ${pipeline.enabled ? `<div class="mini-note" style="margin-top:4px;">Current stage: ${escapeHtml(snap.currentStageLabel)}${pipeline.next_stage_label ? ` · Next handoff: ${escapeHtml(pipeline.next_stage_label)}` : ''}</div>` : ''}
                </div>
                <div class="row video-history-actions" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;">
                  ${latestOutputId ? `<button class="btn btn-small" type="button" data-video-history-preview="${escapeHtml(job.job_id || job.id || '')}" data-video-history-output-id="${escapeHtml(latestOutputId)}">Preview</button>` : ''}
                  ${latestOutputUrl ? `<a class="btn btn-small" href="${escapeHtml(latestOutputUrl)}" target="_blank" rel="noopener">Open output</a>` : ''}
                  ${latestOutputId ? `<button class="btn btn-small" type="button" data-video-history-repair="${escapeHtml(job.job_id || job.id || '')}" data-video-history-output-id="${escapeHtml(latestOutputId)}">Send to Repair</button>` : ''}
                  ${latestOutputId ? `<button class="btn btn-small" type="button" data-video-history-interpolate="${escapeHtml(job.job_id || job.id || '')}" data-video-history-output-id="${escapeHtml(latestOutputId)}">Send to Interpolate</button>` : ''}
                  ${latestOutputId ? `<button class="btn btn-small" type="button" data-video-history-upscale="${escapeHtml(job.job_id || job.id || '')}" data-video-history-output-id="${escapeHtml(latestOutputId)}">Send to Upscale</button>` : ''}
                  ${runtime.manifest_url ? `<a class="btn btn-small" href="${escapeHtml(runtime.manifest_url)}" target="_blank" rel="noopener">Manifest</a>` : ''}
                  <button class="btn btn-small" type="button" data-video-history-retry="${escapeHtml(job.job_id || job.id || '')}">Retry</button>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function rememberVideoJobSnapshot(job){
    if (!job || typeof job !== 'object') return;
    const jobId = String(job.job_id || job.id || '').trim();
    if (!jobId) return;
    const clone = JSON.parse(JSON.stringify(job));
    const existingIndex = lastHistory.findIndex(item => String(item?.job_id || item?.id || '').trim() === jobId);
    if (existingIndex >= 0) lastHistory.splice(existingIndex, 1, clone);
    else lastHistory.unshift(clone);
    lastHistory = lastHistory.slice(0, 24);
  }

  function applyJobSnapshot(job){
    if (!job || typeof job !== 'object') return;
    rememberVideoJobSnapshot(job);
    const jobId = String(job.job_id || job.id || '').trim();
    if (jobId) {
      lastVideoJobId = jobId;
      if (!isTerminalState(job.status || job.state || 'queued')) activeJobId = jobId;
    }
    renderJobCard(job);
    renderVideoOutputs(job.outputs || [], job);
    updateActionButtons(job);
  }

  function actionBarJobCandidate(job){
    if (job && typeof job === 'object') {
      const state = String(job.status || job.state || '').trim().toLowerCase() || 'queued';
      if (!isTerminalState(state) && !shouldSuppressStaleRemoteVideoJob(job)) return job;
      return null;
    }

    const active = activeJobId
      ? lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === String(activeJobId || '').trim())
      : null;

    if (active) {
      const state = String(active.status || active.state || '').trim().toLowerCase() || 'queued';
      if (!isTerminalState(state) && !shouldSuppressStaleRemoteVideoJob(active)) {
        return active;
      }
    }

    return null;
  }

  function renderVideoActionBar(job){
    const chip = $('video-action-state-chip');
    const title = $('video-action-title');
    const copy = $('video-action-copy');
    const modeBadge = $('video-action-mode-badge');
    const profileBadge = $('video-action-profile-badge');
    const pipelineBadge = $('video-action-pipeline-badge');
    if (modeBadge) modeBadge.textContent = currentModeLabel();
    if (profileBadge) profileBadge.textContent = currentProfileLabel();
    if (pipelineBadge) pipelineBadge.textContent = currentPostPipelineTemplate()?.label || 'Generate only';
    if (!chip || !title || !copy) return;
    const current = actionBarJobCandidate(job);
    const snapshot = current ? statusSnapshot(current) : null;
    const canCancel = !!(current?.video_runtime?.can_cancel || (current && !isTerminalState(snapshot?.state || 'queued')));
    chip.className = `backend-chip ${snapshot ? snapshot.chipClass : 'state-connected'}`;
    if (requestInFlight) {
      chip.className = 'backend-chip state-checking';
      chip.textContent = 'Queueing';
      title.textContent = 'Queueing the next video job';
      copy.textContent = 'Neo is handing the current request off to the backend. Stop appears again once the queued job is active.';
    } else if (snapshot && !isTerminalState(snapshot.state)) {
      chip.textContent = snapshot.stateLabel;
      title.textContent = `${snapshot.workflowLabel} · ${snapshot.currentStageLabel}`;
      copy.textContent = String(current?.status_text || snapshot.progressLabel || 'Neo is tracking the active video job.').trim();
    } else if (snapshot?.state === 'failed') {
      chip.textContent = snapshot.stateLabel;
      title.textContent = 'Last run failed';
      copy.textContent = plainFailureMessage(current);
    } else if (snapshot?.state === 'completed') {
      chip.textContent = 'Ready';
      chip.className = 'backend-chip state-connected';
      title.textContent = 'Ready for another run';
      copy.textContent = `Latest ${snapshot.workflowLabel.toLowerCase()} finished. Generate again, retry the same config, or push the clip into a post lane.`;
    } else if (snapshot?.state === 'cancelled') {
      chip.textContent = 'Stopped';
      chip.className = 'backend-chip state-degraded';
      title.textContent = 'Run stopped';
      copy.textContent = 'The active video job was stopped. Adjust the request, then generate again when you are ready.';
    } else {
      chip.textContent = 'Ready';
      chip.className = 'backend-chip state-connected';
      title.textContent = 'Ready to generate';
      copy.textContent = canCancel
        ? 'A job is still attached to the current workspace. Stop it here if the backend looks stuck.'
        : 'Generate stays the main CTA here. Stop only appears while Neo is queueing or running an active video job.';
    }
  }

  function updateRunButton(){
    const btn = $('btn-video-run');
    if (!btn) return;
    const current = actionBarJobCandidate(null);
    const snapshot = current ? statusSnapshot(current) : null;
    if (requestInFlight){
      btn.disabled = true;
      btn.textContent = 'Queueing…';
      return;
    }
    if (activeJobId && !isTerminalState($('video-job-status-box')?.dataset.jobState || '')){
      btn.disabled = true;
      btn.textContent = snapshot?.state === 'queued' ? 'Queued…' : 'Running…';
      return;
    }
    btn.disabled = false;
    if (snapshot?.state === 'completed' || snapshot?.state === 'cancelled') btn.textContent = 'Generate again';
    else if (snapshot?.state === 'failed') btn.textContent = 'Generate new run';
    else btn.textContent = 'Generate';
  }

  function updateUpscaleButton(){
    const btn = $('btn-video-upscale-run');
    if (!btn) return;
    if (requestInFlight){
      btn.disabled = true;
      btn.textContent = 'Queueing…';
      return;
    }
    const sourceReady = !!sourceVideoFile() || !!(($('video-upscale-source-label')?.value || '').trim()) || !!getUpscaleSourceRef()?.view_url || !!getUpscaleSourceRef()?.local_path;
    btn.disabled = !sourceReady;
    btn.textContent = 'Queue Upscale';
  }

  function updateRepairButton(){
    const btn = $('btn-video-repair-run');
    if (!btn) return;
    if (requestInFlight){
      btn.disabled = true;
      btn.textContent = 'Queueing…';
      return;
    }
    const sourceReady = !!sourceRepairFile() || !!(($('video-repair-source-label')?.value || '').trim()) || !!getRepairSourceRef()?.view_url || !!getRepairSourceRef()?.local_path;
    btn.disabled = !sourceReady;
    btn.textContent = 'Queue Repair';
  }

  function updateInterpolateButton(){
    const btn = $('btn-video-interpolate-run');
    if (!btn) return;
    if (requestInFlight){
      btn.disabled = true;
      btn.textContent = 'Queueing…';
      return;
    }
    const sourceReady = !!sourceInterpolateFile() || !!(($('video-interpolate-source-label')?.value || '').trim()) || !!getInterpolateSourceRef()?.view_url || !!getInterpolateSourceRef()?.local_path;
    btn.disabled = !sourceReady;
    btn.textContent = 'Queue Interpolate';
  }

  function applyInterpolatePreset(){
    const preset = String(currentInterpolatePreset() || '').trim();
    if (!preset) return;
    if (preset === '16_to_24') { setValue('video-interpolate-target-fps', '24'); setValue('video-interpolate-multiplier', '1.5'); }
    if (preset === '16_to_30') { setValue('video-interpolate-target-fps', '30'); setValue('video-interpolate-multiplier', '1.875'); }
    if (preset === '24_to_30') { setValue('video-interpolate-target-fps', '30'); setValue('video-interpolate-multiplier', '1.25'); }
    if (preset === '30_to_60') { setValue('video-interpolate-target-fps', '60'); setValue('video-interpolate-multiplier', '2'); }
    if ($('video-interpolate-intent')) $('video-interpolate-intent').value = 'preserve_timing';
    renderInterpolateSummary();
  }

  function renderInterpolateSummary(){
    const payload = collectInterpolatePayload();
    const runtime = estimateInterpolateRuntime(payload);
    const card = $('video-interpolate-summary');
    const help = $('video-interpolate-source-help');
    const warningBox = $('video-interpolate-warning-box');
    const sourceFile = sourceInterpolateFile();
    const sourceRef = getInterpolateSourceRef();
    const sourceLabel = ($('video-interpolate-source-label')?.value || '').trim() || sourceRef.label || sourceRef.filename || '';
    const sourceReady = !!sourceFile || !!sourceLabel || !!sourceRef.view_url || !!sourceRef.local_path;
    if (help) {
      help.textContent = sourceFile
        ? `Selected local source video: ${sourceFile.name}`
        : (sourceLabel ? `Interpolate source is ready: ${sourceLabel}` : 'Use the latest generated output or upload a clip directly. This lane smooths motion and standardizes frame rate after generation.');
    }
    if (warningBox) {
      if (runtime.warnings?.length) {
        warningBox.style.display = '';
        warningBox.innerHTML = `<div class="accordion-title">Interpolate lane guardrails</div><div class="mini-note" style="margin-top:12px; display:grid; gap:6px;">${runtime.warnings.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}</div>`;
      } else {
        warningBox.style.display = 'none';
        warningBox.innerHTML = '';
      }
    }
    if (card) {
      card.innerHTML = `
        <div class="row" style="gap:8px; flex-wrap:wrap; align-items:center;">
          <span class="badge">${escapeHtml(heavinessBadge(runtime.estimated_heaviness))}</span>
          <span class="badge">${escapeHtml(currentInterpolateTimingIntent() === 'slow_motion' ? 'Slow motion' : 'Preserve timing')}</span>
          <span class="badge">${escapeHtml(String(currentInterpolateTargetFps()))} FPS target</span>
        </div>
        <div class="mini-note" style="margin-top:12px;">${escapeHtml(runtime.slow_copy)}</div>
        <div class="mini-note" style="margin-top:12px;">${sourceReady ? `Interpolate will target ${currentInterpolateTargetFps()} FPS at ${currentInterpolateMultiplier()}× using ${currentInterpolateQualityMode() === 'smooth' ? 'Smoother motion' : currentInterpolateQualityMode() === 'detail_safe' ? 'Detail safe' : 'Balanced'} mode.` : 'Pick a source clip first so Neo can queue the local Interpolate lane.'}</div>
      `;
    }
    updateInterpolateButton();
  }

  function renderUpscaleSummary(){
    const payload = collectUpscalePayload();
    const runtime = estimateUpscaleRuntime(payload);
    const card = $('video-upscale-summary');
    const help = $('video-upscale-source-help');
    const warningBox = $('video-upscale-warning-box');
    const customWrap = $('video-upscale-custom-fps-wrap');
    const sourceFile = sourceVideoFile();
    const sourceRef = getUpscaleSourceRef();
    const sourceLabel = ($('video-upscale-source-label')?.value || '').trim() || sourceRef.label || sourceRef.filename || '';
    const sourceReady = !!sourceFile || !!sourceLabel || !!sourceRef.view_url || !!sourceRef.local_path;
    if (customWrap) customWrap.style.display = currentUpscaleFpsMode() === 'custom' ? '' : 'none';
    if (help) {
      help.textContent = sourceFile
        ? `Selected local source video: ${sourceFile.name}`
        : (sourceLabel ? `Upscale source is ready: ${sourceLabel}` : 'Use the latest generated output or upload a delivery source directly. This lane does not rerun generation.');
    }
    if (warningBox) {
      if (!runtime.warnings.length) {
        warningBox.style.display = 'none';
        warningBox.innerHTML = '';
      } else {
        warningBox.style.display = '';
        warningBox.innerHTML = `
          <div class="accordion-title">Upscale warnings</div>
          <div class="mini-note" style="margin-top:12px; display:grid; gap:8px;">
            ${runtime.warnings.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}
          </div>
        `;
      }
    }
    if (card) {
      card.innerHTML = [
        ['Source', sourceLabel || (sourceReady ? 'Ready' : 'Missing')],
        ['Profile', currentUpscaleProfile() === 'quality_conservative' ? 'Quality Conservative' : 'Fast Local'],
        ['Target', currentUpscaleTarget()],
        ['FPS', currentUpscaleFpsMode() === 'custom' ? `${numberOr($('video-upscale-custom-fps')?.value || 24, 24)} FPS` : 'Preserve source FPS'],
        ['Container', currentUpscaleContainer().toUpperCase()],
        ['Codec', currentUpscaleCodec() === 'auto' ? 'Auto' : currentUpscaleCodec().toUpperCase()],
        ['Estimated runtime', heavinessBadge(runtime.estimated_heaviness)],
        ['Runtime note', runtime.slow_copy],
      ].map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('');
    }
    updateUpscaleButton();
  }

  function renderRepairSummary(){
    const payload = collectRepairPayload();
    const runtime = estimateRepairRuntime(payload);
    const card = $('video-repair-summary');
    const help = $('video-repair-source-help');
    const warningBox = $('video-repair-warning-box');
    const sourceFile = sourceRepairFile();
    const sourceRef = getRepairSourceRef();
    const sourceLabel = ($('video-repair-source-label')?.value || '').trim() || sourceRef.label || sourceRef.filename || '';
    const sourceReady = !!sourceFile || !!sourceLabel || !!sourceRef.view_url || !!sourceRef.local_path;
    if (help) {
      help.textContent = sourceFile
        ? `Selected local source video: ${sourceFile.name}`
        : (sourceLabel ? `Repair source is ready: ${sourceLabel}` : 'Use the latest generated output or upload a clip directly. This lane fixes, cleans, and stabilizes without rerunning generation.');
    }
    if (warningBox) {
      if (!runtime.warnings.length) {
        warningBox.style.display = 'none';
        warningBox.innerHTML = '';
      } else {
        warningBox.style.display = '';
        warningBox.innerHTML = `
          <div class="accordion-title">Repair warnings</div>
          <div class="mini-note" style="margin-top:12px; display:grid; gap:8px;">
            ${runtime.warnings.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}
          </div>
        `;
      }
    }
    if (card) {
      card.innerHTML = [
        ['Source', sourceLabel || (sourceReady ? 'Ready' : 'Missing')],
        ['Strength', currentRepairStrength().replace(/_/g, ' ')],
        ['Cleanup focus', currentRepairFocus() === 'compression_cleanup' ? 'Compression artifact cleanup' : 'General cleanup'],
        ['Temporal stabilization', currentRepairStabilizeTemporal() ? 'Enabled' : 'Off'],
        ['Estimated runtime', heavinessBadge(runtime.estimated_heaviness)],
        ['Runtime note', runtime.slow_copy],
      ].map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('');
    }
    updateRepairButton();
  }


  function queueUpscaleFromJobOutput(jobId, outputId){
    const cleanJobId = String(jobId || '').trim();
    const cleanOutputId = String(outputId || '').trim();
    const job = lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === cleanJobId) || null;
    const output = (job?.outputs || []).find(item => String(item?.output_id || item?.filename || '').trim() === cleanOutputId) || null;
    if (!job || !output) {
      setStatusSafe('video-status', 'That output could not be resolved into the Upscale lane source.', 'warn');
      return;
    }
    setUpscaleSourceRef({
      job_id: cleanJobId,
      output_id: output.output_id || output.filename || '',
      filename: output.filename || '',
      subfolder: output.subfolder || '',
      type: output.type || '',
      view_url: output.view_url || '',
      local_path: output.local_path || '',
      label: output.filename || `output from ${cleanJobId}`,
    }, output.filename || `output from ${cleanJobId}`);
    renderUpscaleSummary();
    setVideoSupportTab('upscale');
    $('video-upscale-card')?.scrollIntoView?.({ behavior:'smooth', block:'nearest' });
    setStatusSafe('video-status', 'Sent that output into the Upscale lane.', 'ok');
  }

  function queueRepairFromJobOutput(jobId, outputId){
    const cleanJobId = String(jobId || '').trim();
    const cleanOutputId = String(outputId || '').trim();
    const job = lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === cleanJobId) || null;
    const output = (job?.outputs || []).find(item => String(item?.output_id || item?.filename || '').trim() === cleanOutputId) || null;
    if (!job || !output) {
      setStatusSafe('video-status', 'That output could not be resolved into the Repair lane source.', 'warn');
      return;
    }
    setRepairSourceRef({
      job_id: cleanJobId,
      output_id: output.output_id || output.filename || '',
      filename: output.filename || '',
      subfolder: output.subfolder || '',
      type: output.type || '',
      view_url: output.view_url || '',
      local_path: output.local_path || '',
      label: output.filename || `output from ${cleanJobId}`,
    }, output.filename || `output from ${cleanJobId}`);
    renderRepairSummary();
    setVideoSupportTab('repair');
    $('video-repair-card')?.scrollIntoView?.({ behavior:'smooth', block:'nearest' });
    setStatusSafe('video-status', 'Sent that output into the Repair lane.', 'ok');
  }

  function renderVideoSummary(){
    const mode = currentModeDefinition();
    const profile = currentProfileDefinition();
    const payload = collectVideoPayload();
    const duration = payload.duration_seconds;
    const fps = payload.fps;
    const size = payload.size_preset;
    const source = ($('video-source-image')?.value || '').trim();
    const prompt = ($('video-prompt')?.value || '').trim();
    const negative = ($('video-negative')?.value || '').trim();
    const seed = ($('video-seed')?.value || '').trim();
    const qualityStyle = qualityPromptStyle().trim();
    const qualityCamera = qualityPromptCamera().trim();
    const adapters = rememberedAdvancedAdapters();
    const effectiveAdapters = payload.advanced_adapters && typeof payload.advanced_adapters === 'object' ? payload.advanced_adapters : {};
    const adapterPreset = findAdapterPairPreset(adapters.pair_preset_id);
    const estimatedFrames = Math.max(1, String(profile?.quality_tier || '').toLowerCase() === 'quality' ? (Math.floor(duration * fps) + 1) : (duration * fps));
    const statuses = allStatuses().map(item => item.label).join(', ');
    const preset = currentPresetLabel();
    const runtime = estimateRuntime(payload);
    const pipelineTemplate = currentPostPipelineTemplate();
    const pipelineSummary = $('video-post-pipeline-summary');
    const runtimeBadge = $('video-runtime-heaviness-badge');
    const profileBadge = $('video-runtime-profile-badge');
    const emptyNote = $('video-empty-state-note');
    const runtimeCopy = $('video-runtime-copy');
    const runtimeSummary = $('video-runtime-summary');
    const explainer = $('video-shell-explainer');
    const sourceHelp = $('video-source-image-help');
    const advancedSection = $('video-quality-prompt-section');
    const advancedNote = $('video-quality-prompt-note');
    const outputSettingsNote = $('video-output-settings-note');
    const warningBox = $('video-quality-warning-box');

    if ($('video-surface-summary')) $('video-surface-summary').textContent = `${mode.label} · ${currentProfileLabel()} · ${duration}s · ${effectiveVideoSize().label}`;
    if (runtimeBadge) runtimeBadge.textContent = heavinessBadge(runtime.estimated_heaviness);
    if (profileBadge) profileBadge.textContent = currentProfileLabel();
    if (advancedSection) advancedSection.style.display = isQualityProfile() ? '' : 'none';
    if (advancedNote) {
      advancedNote.textContent = mode.id === 'i2v'
        ? 'Use this to sharpen the motion goal and style direction around the starting frame. Keep it precise — High Quality will actually try to follow it.'
        : 'Use this to sharpen cinematic style and camera intent. High Quality responds better to disciplined direction than to a giant junk drawer prompt.';
    }
    if (explainer) {
      explainer.textContent = isQualityProfile()
        ? (mode.id === 'i2v'
            ? 'Describe how the starting frame should move, what should stay stable, and what kind of finish you want. This path is for deliberate, slower, heavier shots.'
            : 'Describe motion, framing, style, and subject clearly. High Quality now resolves to the dedicated Wan 2.2 14B T2V workflow, so tighter direction matters more.')
        : (mode.id === 'i2v'
            ? 'Describe the motion change you want from the starting frame. Neo keeps the balanced I2V shell simple here instead of pretending there is a verified motion-guidance slider already.'
            : 'Describe the motion, framing, vibe, and subject clearly. This phase keeps the default path usable without dropping users into raw node controls.');
    }
    if (runtimeCopy) runtimeCopy.textContent = runtime.slow_copy;
    if (outputSettingsNote) {
      outputSettingsNote.textContent = isQualityProfile()
        ? 'High Quality keeps the same shell controls, but the backend path is the dedicated Wan 2.2 14B stack. Expect slower queues, heavier VRAM use, and more sensitivity to clip length.'
        : 'Balanced keeps the defaults conservative for low / medium VRAM. If you keep pushing clip length, FPS, and size together, it stops being the low-VRAM-safe option.';
    }
    if (sourceHelp) {
      sourceHelp.textContent = sourceImageFile()
        ? `Selected source image: ${sourceImageFile().name}${currentSourceImageMeta().width ? ` · ${currentSourceImageMeta().width} × ${currentSourceImageMeta().height}` : ''}`
        : (isQualityProfile()
            ? 'High Quality I2V still needs a real file selected in this browser. Presets only remember the label, not the actual upload.'
            : 'Select a real source image here. Presets only remember the label — you still need to reselect the image before running.');
    }
    if (warningBox) {
      if (!runtime.warnings.length) {
        warningBox.style.display = 'none';
        warningBox.innerHTML = '';
      } else {
        warningBox.style.display = '';
        warningBox.innerHTML = `
          <div class="accordion-title">Runtime warnings</div>
          <div class="mini-note" style="margin-top:12px; display:grid; gap:8px;">
            ${runtime.warnings.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}
          </div>
        `;
      }
    }
    if (pipelineSummary) {
      const steps = Array.isArray(pipelineTemplate?.steps) ? pipelineTemplate.steps : [];
      const pipelineCopy = steps.length
        ? `${pipelineTemplate.label} will hand a finished generation into the existing ${steps.join(' → ')} lanes using the current lane settings.`
        : 'Generate only keeps the default simple: one generation job, no automatic post handoff.';
      pipelineSummary.innerHTML = `
        <div class="accordion-title">Pipeline summary</div>
        <div class="mini-note" style="margin-top:12px;">${escapeHtml(pipelineCopy)}</div>
        <div style="margin-top:14px; display:grid; gap:0;">${[
          ['Template', pipelineTemplate?.label || 'Generate only'],
          ['Auto handoff', steps.length ? 'Enabled' : 'Off'],
          ['Stages after generation', steps.length ? steps.join(' → ') : 'None'],
        ].map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('')}</div>
      `;
    }
    if (emptyNote) {
      if (!prompt && mode.requires_source_image && !source) emptyNote.textContent = 'Add the source image and the prompt before queueing this video request.';
      else if (!prompt) emptyNote.textContent = 'Start with the prompt. The runtime summary becomes useful once the clip has a real direction.';
      else if (mode.requires_source_image && !source) emptyNote.textContent = 'This Image to Video request is ready except for the source image file.';
      else emptyNote.textContent = runtime.estimated_heaviness === 'heavy'
        ? 'The request is complete, but it is heavy. Expect a slower queue and more backend pressure.'
        : runtime.estimated_heaviness === 'medium'
          ? 'The request looks complete. It should run, but it is no longer a casual low-VRAM draft.'
          : 'The request looks complete. Queue it when the Video backend is connected.';
    }
    renderSavedVideoPresetSummary();
    renderVideoAdapterSummary();
    if (runtimeSummary) {
      const rows = [
        ['Mode', mode.label],
        ['Quality', currentProfileLabel()],
        ['Resolved backend', profile.technical_label || profile.label || profile.id],
        ['Estimated runtime', heavinessBadge(runtime.estimated_heaviness)],
        ['Clip spec', `${duration}s · ${fps} FPS · ${size}`],
        ['Estimated frames', String(estimatedFrames)],
        ['Seed', seed || 'Random'],
        ['Workspace starter', preset],
        ['Backend assets', backendAssetsMatchDefaults() ? 'Defaults' : 'Custom override'],
        ['Post pipeline', pipelineTemplate?.label || 'Generate only'],
        ['Negative prompt', negative ? 'Included' : 'Not set'],
        ['Runtime states', statuses],
      ];
      if (mode.requires_source_image) rows.splice(4, 0, ['Source image', source || 'Missing']);
      if (!isQualityProfile()) rows.splice(rows.length - 1, 0,
        ['Balanced model stack', `${currentBackendAssets().balanced_unet_name || '—'} · ${currentBackendAssets().balanced_clip_name || '—'} · ${currentBackendAssets().balanced_vae_name || '—'}`],
        ['Balanced adapter', effectiveAdapters.enabled ? (effectiveAdapters.single_adapter || 'Missing') : 'Not enabled'],
        ['Adapter strength', effectiveAdapters.enabled ? String(effectiveAdapters.strength ?? adapterSupport().default_strength ?? 0.8) : '—'],
      );
      if (isQualityProfile()) {
        rows.splice(rows.length - 1, 0,
          ['Advanced style', qualityStyle || 'Not set'],
          ['Advanced camera', qualityCamera || 'Not set'],
          ['Quality model stack', `${currentBackendAssets().quality_high_noise_unet_name || '—'} · ${currentBackendAssets().quality_low_noise_unet_name || '—'}`],
          ['Quality encoder / VAE', `${currentBackendAssets().quality_clip_name || '—'} · ${currentBackendAssets().quality_vae_name || '—'}`],
          ['Adapter pair', effectiveAdapters.enabled ? (adapterPreset?.name || `${effectiveAdapters.high_noise_adapter || 'Missing'} + ${effectiveAdapters.low_noise_adapter || 'Missing'}`) : 'Not enabled'],
          ['Adapter strength', effectiveAdapters.enabled ? String(effectiveAdapters.strength ?? adapterSupport().default_strength ?? 0.8) : '—'],
        );
      }
      runtimeSummary.innerHTML = rows.map(([label, value]) => `<div class="row-between" style="gap:12px; padding:8px 0; border-top:1px solid rgba(148,163,184,.12);"><span class="mini-note">${escapeHtml(label)}</span><strong style="text-align:right;">${escapeHtml(value)}</strong></div>`).join('');
    }
    if ($('video-adapters-enabled')) $('video-adapters-enabled').disabled = !supportsAdaptersForProfile();
    if ($('btn-video-load-adapter-preset')) $('btn-video-load-adapter-preset').disabled = !adapterUsesPairedMode() || !findAdapterPairPreset(adapterPairPresetSelectionId());
    if ($('btn-video-update-adapter-preset')) $('btn-video-update-adapter-preset').disabled = !adapterUsesPairedMode() || !findAdapterPairPreset(adapterPairPresetSelectionId());
    if ($('btn-video-delete-adapter-preset')) $('btn-video-delete-adapter-preset').disabled = !adapterUsesPairedMode() || !findAdapterPairPreset(adapterPairPresetSelectionId());
    renderVideoBackendAssetSummary();
    renderUpscaleSummary();
    renderRepairSummary();
    renderInterpolateSummary();
    updateRunButton();
    renderVideoActionBar(null);
    emitVideoShellState();
    updateActionButtons(lastHistory[0] || null);
  }

  function clearVideoDraft(){
    window.localStorage.removeItem(STORAGE_KEY);
    LEGACY_STORAGE_KEYS.forEach(key => window.localStorage.removeItem(key));
    populateModeOptions();
    if ($('video-mode')) $('video-mode').value = defaults().mode || 't2v';
    populateProfileOptions(defaults().profile || 'wan22_5b_balanced');
    if ($('video-duration')) $('video-duration').value = String(defaults().duration_seconds || 5);
    if ($('video-fps')) $('video-fps').value = String(defaults().fps || 16);
    if ($('video-size')) $('video-size').value = defaults().size_preset || '832x480';
    if ($('video-width')) $('video-width').value = '832';
    if ($('video-height')) $('video-height').value = '480';
    videoSourceImageMeta = { width:0, height:0 };
    if ($('video-source-image-meta')) { $('video-source-image-meta').style.display = 'none'; $('video-source-image-meta').textContent = ''; }
    applyVideoSizeUiState();
    if ($('video-source-image')) $('video-source-image').value = '';
    if ($('video-source-image-file')) $('video-source-image-file').value = '';
    if ($('video-prompt')) $('video-prompt').value = '';
    if ($('video-negative')) $('video-negative').value = '';
    if ($('video-seed')) $('video-seed').value = defaults().seed || '';
    if ($('video-quality-style')) $('video-quality-style').value = '';
    if ($('video-quality-camera')) $('video-quality-camera').value = '';
    if ($('video-post-pipeline-template')) $('video-post-pipeline-template').value = defaults().post_pipeline_template || 'generate_only';
    if ($('video-adapters-enabled')) $('video-adapters-enabled').checked = false;
    if ($('video-adapter-preset-select')) $('video-adapter-preset-select').value = '';
    if ($('video-adapter-single')) $('video-adapter-single').value = '';
    if ($('video-adapter-high-noise')) $('video-adapter-high-noise').value = '';
    if ($('video-adapter-low-noise')) $('video-adapter-low-noise').value = '';
    if ($('video-adapter-strength')) $('video-adapter-strength').value = String(adapterSupport().default_strength ?? 0.8);
    if ($('video-adapter-strength-quality')) $('video-adapter-strength-quality').value = String(adapterSupport().default_strength ?? 0.8);
    applyBackendAssetsToForm({}, defaults().profile || 'wan22_5b_balanced');
    if ($('video-upscale-profile')) $('video-upscale-profile').value = 'fast_local';
    if ($('video-upscale-target')) $('video-upscale-target').value = '1920x1080';
    if ($('video-upscale-fps-mode')) $('video-upscale-fps-mode').value = 'preserve';
    if ($('video-upscale-custom-fps')) $('video-upscale-custom-fps').value = '24';
    if ($('video-upscale-container')) $('video-upscale-container').value = 'mp4';
    if ($('video-upscale-codec')) $('video-upscale-codec').value = 'auto';
    if ($('video-repair-strength')) $('video-repair-strength').value = 'balanced';
    if ($('video-repair-focus')) $('video-repair-focus').value = 'general_cleanup';
    if ($('video-repair-stabilize')) $('video-repair-stabilize').checked = false;
    if ($('video-interpolate-preset')) $('video-interpolate-preset').value = '';
    if ($('video-interpolate-target-fps')) $('video-interpolate-target-fps').value = '30';
    if ($('video-interpolate-multiplier')) $('video-interpolate-multiplier').value = '2';
    if ($('video-interpolate-quality')) $('video-interpolate-quality').value = 'balanced';
    if ($('video-interpolate-intent')) $('video-interpolate-intent').value = 'preserve_timing';
    clearUpscaleSource();
    clearRepairSource();
    clearInterpolateSource();
    renderVideoOutputs([], null);
    renderJobCard(null);
    renderVideoSummary();
    setStatusSafe('video-status', 'Cleared the local video draft.', 'ok');
  }

  function buildVideoWsUrl(clientId){
    const url = new URL('/api/video/progress/ws', window.location.href);
    url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    url.search = `clientId=${encodeURIComponent(clientId)}`;
    return url.toString();
  }

  function closeVideoProgressSocket(){
    if (videoProgressSocket) {
      try { videoProgressSocket.close(); } catch (_) {}
    }
    videoProgressSocket = null;
    videoProgressClientId = '';
    videoProgressPromptId = '';
    videoProgressStartedAt = 0;
    videoLastProgressPercent = 0;
  }

  function currentTrackedVideoJob(){
    const target = String(activeJobId || lastVideoJobId || '').trim();
    if (!target) return null;
    return lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === target) || null;
  }

  function upsertVideoProgressSnapshot(patch){
    const current = currentTrackedVideoJob();
    if (!current) return;
    const next = JSON.parse(JSON.stringify(current));
    Object.assign(next, patch || {});
    next.progress = { ...(current.progress || {}), ...((patch && patch.progress) || {}) };
    if (patch && patch.payload) next.payload = { ...(current.payload || {}), ...(patch.payload || {}) };
    applyJobSnapshot(next);
  }

  function videoWsErrorMessage(rawData){
    const parts = [];
    const nodeType = String(rawData?.node_type || '').trim();
    const nodeId = String(rawData?.node_id || rawData?.node || '').trim();
    const exceptionType = String(rawData?.exception_type || '').trim();
    const exceptionMessage = String(rawData?.exception_message || rawData?.message || '').trim();
    if (nodeType) parts.push(nodeType);
    else if (nodeId) parts.push(`Node ${nodeId}`);
    if (exceptionType) parts.push(exceptionType);
    if (exceptionMessage) parts.push(exceptionMessage);
    return parts.join(' | ') || 'ComfyUI reported an execution error while running the video workflow.';
  }

  function handleVideoProgressMessage(message){
    const type = String(message?.type || '').toLowerCase();
    const rawData = (message && typeof message.data === 'object' && message.data) ? message.data : message || {};
    const promptId = String(rawData?.prompt_id || message?.prompt_id || '');
    if (videoProgressPromptId && promptId && promptId !== videoProgressPromptId) return;

    if (type === 'proxy_open') return;
    if (type === 'error') {
      const messageText = String(rawData?.message || 'Video progress proxy failed.').trim() || 'Video progress proxy failed.';
      setStatusSafe('video-status', messageText, 'warn');
      return;
    }
    if (type === 'status') {
      const remaining = Number(rawData?.exec_info?.queue_remaining ?? rawData?.status?.exec_info?.queue_remaining ?? 0);
      const detail = remaining > 0 ? `Comfy queue active (${remaining} remaining)` : 'Comfy queue active';
      const tracked = currentTrackedVideoJob();
      const trackedState = String(tracked?.status || tracked?.state || '').trim().toLowerCase() || '';

      // Comfy "status" events are global queue updates, not prompt-scoped job state.
      // Keep them informational only so they cannot overwrite a tracked job snapshot.
      if ((tracked && !isTerminalState(trackedState)) || requestInFlight) {
        setStatusSafe('video-status', detail, 'ok');
      }
      return;
    }
    if (type === 'execution_start') {
      videoProgressStartedAt = Date.now();
      if (promptId) videoProgressPromptId = promptId;
      videoLastProgressPercent = Math.max(4, videoLastProgressPercent || 0);
      upsertVideoProgressSnapshot({
        prompt_id: videoProgressPromptId || promptId,
        state:'running',
        status:'running',
        status_text:'Starting video generation in ComfyUI.',
        progress:{ percent: videoLastProgressPercent, detail:'Starting generation' },
      });
      setStatusSafe('video-status', 'Starting video generation in ComfyUI…', 'ok');
      return;
    }
    if (type === 'progress') {
      const value = Number(rawData?.value ?? message?.value ?? 0);
      const max = Number(rawData?.max ?? message?.max ?? 0);
      videoLastProgressPercent = max > 0 ? Math.min(96, Math.max(8, (value / max) * 100)) : Math.max(12, videoLastProgressPercent || 0);
      upsertVideoProgressSnapshot({
        state:'running',
        status:'running',
        status_text:`Generating video in ComfyUI (${value}/${max || '?'})`,
        progress:{ percent: Math.round(videoLastProgressPercent), detail:`Generating ${value}/${max || '?'}` },
      });
      return;
    }
    if (type === 'executing') {
      const node = rawData?.node ?? null;
      if (node === null || node === undefined) {
        videoLastProgressPercent = Math.max(97, videoLastProgressPercent || 0);
        upsertVideoProgressSnapshot({
          state:'running',
          status:'running',
          status_text:'Backend execution finished. Waiting for output registration.',
          progress:{ percent: Math.round(videoLastProgressPercent), detail:'Finalizing output' },
        });
      } else {
        videoLastProgressPercent = Math.max(15, videoLastProgressPercent || 0);
        upsertVideoProgressSnapshot({
          state:'running',
          status:'running',
          status_text:`Executing backend node ${node}.`,
          progress:{ percent: Math.round(videoLastProgressPercent), detail:`Executing node ${node}` },
        });
      }
      return;
    }
    if (type === 'executed') {
      videoLastProgressPercent = Math.max(90, videoLastProgressPercent || 0);
      upsertVideoProgressSnapshot({
        state:'running',
        status:'running',
        status_text:'Backend wrote a node result. Waiting for final output registration.',
        progress:{ percent: Math.round(videoLastProgressPercent), detail:'Writing output' },
      });
      return;
    }
    if (type === 'execution_success') {
      videoLastProgressPercent = Math.max(99, videoLastProgressPercent || 0);
      upsertVideoProgressSnapshot({
        state:'running',
        status:'running',
        status_text:'Backend execution finished. Waiting for history/output registration.',
        progress:{ percent: Math.round(videoLastProgressPercent), detail:'Registering output' },
      });
      schedulePoll(750);
      return;
    }
    if (type === 'execution_error') {
      const messageText = videoWsErrorMessage(rawData);
      upsertVideoProgressSnapshot({
        state:'failed',
        status:'failed',
        status_text:'Video generation failed in ComfyUI.',
        error: messageText,
        error_message: messageText,
        progress:{ percent: Math.max(1, Math.round(videoLastProgressPercent || 1)), detail:'Execution failed' },
      });
      activeJobId = '';
      stopPolling();
      closeVideoProgressSocket();
      setStatusSafe('video-status', messageText, 'error');
      return;
    }
    if (type === 'execution_interrupted') {
      upsertVideoProgressSnapshot({
        state:'cancelled',
        status:'cancelled',
        status_text:'Video generation was interrupted in ComfyUI.',
        error:'',
        progress:{ percent: Math.round(videoLastProgressPercent || 0), detail:'Interrupted' },
      });
      activeJobId = '';
      stopPolling();
      closeVideoProgressSocket();
      setStatusSafe('video-status', 'The video job was interrupted in ComfyUI.', 'warn');
    }
  }

  function startVideoProgressSocket(clientId, promptId=''){
    // Disabled on purpose. Video tracking is polling-only in this build.
    closeVideoProgressSocket();
    videoProgressClientId = '';
    videoProgressPromptId = '';
    videoProgressStartedAt = 0;
    videoLastProgressPercent = 0;
  }

  function stopPolling(){
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function schedulePoll(delay = 2500){
    stopPolling();
    if (!activeJobId) return;
    pollTimer = window.setTimeout(() => pollVideoJob(activeJobId), delay);
  }

  async function loadVideoHistory(silent=false){
    try {
      const response = await fetch('/api/video/history?limit=8');
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not load video history.');
      lastHistory = Array.isArray(data?.jobs) ? data.jobs : [];
      if (lastHistory[0]) {
        lastVideoJobId = String(lastHistory[0].job_id || lastHistory[0].id || '').trim() || lastVideoJobId;
      }
      renderVideoHistory(lastHistory);
      if (!String(videoPreviewState.url || '').trim() && lastHistory[0]) maybeAutoPreviewJob(lastHistory[0], { force:true, source:'history_latest' });
      const active = lastHistory.find(job =>
        !isTerminalState(job?.status || job?.state || 'queued')
        && !shouldSuppressStaleRemoteVideoJob(job)
      ) || null;
      if (!active && !silent) updateActionButtons(lastHistory[0] || null);

      if (!active) {
        activeJobId = '';
        closeVideoProgressSocket();
        stopPolling();
        renderJobCard(null);
        renderVideoOutputs([], null);
        updateRunButton();
        updateInterpolateButton();
        updateActionButtons(lastHistory[0] || null);
        return;
      }

      if (!activeJobId) {
        applyJobSnapshot(active);
        activeJobId = String(active.job_id || active.id || '').trim();

        if (videoWorkflowType(active) === 'video_generation' && videoBackendConnected()) {
          await pollVideoJob(activeJobId);
          return;
        }

        schedulePoll(1200);
      }
    } catch (error) {
      if (!silent) setStatusSafe('video-status', error?.message || 'Could not load video history.', 'warn');
    }
  }

  async function pollVideoJob(jobId){
    if (!jobId) return;
    try {
      const response = await fetch(`/api/video/job/${encodeURIComponent(jobId)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not refresh the video job.');
      const job = data?.job || {};
      const nextJob = data?.next_job && typeof data.next_job === 'object' ? data.next_job : null;
      const state = String(job.status || job.state || 'queued').trim().toLowerCase() || 'queued';
      const workflowType = String(job?.payload?.workflow_type || '').trim() || 'video_generation';
      applyJobSnapshot(job);
      if (state === 'completed' && nextJob && !isTerminalState(nextJob.status || nextJob.state || 'queued')) {
        activeJobId = String(nextJob.job_id || nextJob.id || '').trim();
        lastVideoJobId = activeJobId || lastVideoJobId;
        applyJobSnapshot(nextJob);
        await loadVideoHistory(true);
        schedulePoll(1200);
        setStatusSafe('video-status', data?.message || 'Generation finished. Chained post lane queued next.', 'ok');
      } else if (state === 'completed') {
        activeJobId = '';
        closeVideoProgressSocket();
        stopPolling();
        await loadVideoHistory(true);
        setStatusSafe('video-status', data?.message || (workflowType === 'video_upscale' ? 'Upscale lane finished. Manifest saved and history updated.' : workflowType === 'video_repair' ? 'Repair lane finished. Manifest saved and history updated.' : workflowType === 'video_interpolate' ? 'Interpolate lane finished. Manifest saved and history updated.' : 'Video generation finished. Output manifest saved and history updated.'), 'ok');
      } else if (state === 'failed' || state === 'cancelled') {
        activeJobId = '';
        closeVideoProgressSocket();
        stopPolling();
        await loadVideoHistory(true);
        setStatusSafe('video-status', state === 'cancelled' ? 'The video job was cancelled.' : plainFailureMessage(job), state === 'cancelled' ? 'warn' : 'error');
      } else {
        schedulePoll(5000);
      }
      updateRunButton();
      updateInterpolateButton();
    } catch (error) {
      schedulePoll(4000);
      setStatusSafe('video-status', error?.message || 'Could not refresh the video job.', 'warn');
    }
  }

  function queueInterpolateFromJobOutput(jobId, outputId){
    const job = lastHistory.find(item => String(item?.job_id || item?.id || '').trim() === String(jobId || '').trim());
    const output = (Array.isArray(job?.outputs) ? job.outputs : []).find(item => String(item?.output_id || item?.filename || '').trim() === String(outputId || '').trim());
    if (!output) {
      setStatusSafe('video-status', 'Could not find that output to send into Interpolate.', 'warn');
      return;
    }
    setInterpolateSourceRef({
      job_id: job.job_id || job.id || '',
      output_id: output.output_id || output.filename || '',
      filename: output.filename || '',
      subfolder: output.subfolder || '',
      type: output.type || '',
      view_url: output.view_url || '',
      local_path: output.local_path || '',
      label: output.filename || output.output_id || 'Video output',
    }, output.filename || output.output_id || 'Video output');
    renderInterpolateSummary();
    setVideoSupportTab('interpolate');
    $('video-interpolate-card')?.scrollIntoView?.({ behavior:'smooth', block:'nearest' });
    setStatusSafe('video-status', 'Sent the selected output into the Interpolate lane.', 'ok');
  }

  async function runVideoGeneration(){
    if (requestInFlight) return;

    try {
      const mode = currentModeDefinition();
      const payload = collectVideoPayload();
      const freeMode = freeAssetModeEnabled();
      const qualityProfile = isQualityProfile();

      setStatusSafe('video-status', freeMode
        ? 'Validating the free-mode video request…'
        : (qualityProfile ? 'Validating the high-quality video request…' : 'Validating the balanced video request…'), 'ok');

      if (!String(payload.prompt || '').trim()) {
        setStatusSafe('video-status', 'Prompt is required before queueing video generation.', 'warn');
        $('video-prompt')?.focus?.();
        return;
      }
      if (mode.requires_source_image && !sourceImageFile()) {
        setStatusSafe('video-status', qualityProfile ? 'High Quality Image to Video needs a real source image file selected in this browser.' : 'Balanced Image to Video needs a real source image file selected in this browser.', 'warn');
        $('video-source-image-file')?.focus?.();
        return;
      }
      if ((currentVideoSizePreset() === 'source_match' || currentVideoSizePreset() === 'auto_source_fit') && !currentSourceImageMeta().width) {
        setStatusSafe('video-status', currentVideoSizePreset() === 'auto_source_fit' ? 'Auto best fit needs a real source image selected first so Neo can read the dimensions.' : 'Match source image needs a real source image selected first so Neo can read the dimensions.', 'warn');
        $('video-source-image-file')?.focus?.();
        return;
      }
      if (currentVideoSizePreset() === 'custom' && (!currentManualVideoWidth() || !currentManualVideoHeight())) {
        setStatusSafe('video-status', 'Manual size needs both width and height filled in.', 'warn');
        $('video-width')?.focus?.();
        return;
      }

      const workflowGuardrails = validateVideoWorkflowGuardrails(currentProfileValue());
      if (!workflowGuardrails.ok) {
        setStatusSafe('video-status', workflowGuardrails.message || 'Video request guardrail check failed.', 'warn');
        if (workflowGuardrails.focusId) $(workflowGuardrails.focusId)?.focus?.();
        return;
      }

      if (!freeMode) {
        const liveAssetValidation = await validateLiveVideoBackendAssets(currentProfileValue());
        if (!liveAssetValidation.ok) {
          setStatusSafe('video-status', liveAssetValidation.message || 'Video asset validation failed.', 'warn');
          return;
        }
      }

      closeVideoProgressSocket();
      payload.client_id = '';

      const form = new FormData();
      form.append('settings_json', JSON.stringify(payload));
      if (mode.requires_source_image && sourceImageFile()) form.append('source_image_file', sourceImageFile());

      requestInFlight = true;
      updateRunButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
      setStatusSafe('video-status', freeMode
        ? 'Free mode is on. Queueing the selected Video backend assets exactly as chosen…'
        : (qualityProfile ? 'Queueing high-quality video generation…' : 'Queueing balanced video generation…'), 'ok');

      const response = await fetch('/api/video/generate', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      const responseJob = data?.job && typeof data.job === 'object' ? data.job : null;
      if (!response.ok || data?.ok === false) {
        if (responseJob) {
          applyJobSnapshot(responseJob);
          await loadVideoHistory(true);
        }
        throw new Error(data?.message || 'Could not queue the video workflow.');
      }
      const job = responseJob || {};
      videoProgressPromptId = String(job.prompt_id || '').trim() || videoProgressPromptId;
      activeJobId = String(job.job_id || job.id || '').trim();
      lastVideoJobId = activeJobId || lastVideoJobId;
      applyJobSnapshot(job);
      saveVideoDraft(false);
      schedulePoll();
      await loadVideoHistory(true);
      setStatusSafe('video-status', freeMode
        ? 'Video queued in free mode. Tracking the job now.'
        : (qualityProfile ? 'High Quality video queued in ComfyUI.' : 'Balanced video queued in ComfyUI.'), 'ok');
    } catch (error) {
      closeVideoProgressSocket();
      const currentState = String($('video-job-status-box')?.dataset.jobState || '').trim().toLowerCase();
      if (!currentState || !isTerminalState(currentState)) {
        activeJobId = '';
        renderJobCard(null);
        renderVideoOutputs([], null);
      }
      setStatusSafe('video-status', error?.message || 'Could not queue the video workflow.', 'error');
      console.error('Video generate failed', error);
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }

  function runBalancedVideo(){
    return runVideoGeneration();
  }


  async function runVideoUpscale(){
    if (requestInFlight) return;
    const payload = collectUpscalePayload();
    const hasFile = !!sourceVideoFile();
    const hasRef = !!payload.source_output_ref?.view_url || !!payload.source_output_ref?.local_path;
    if (!hasFile && !hasRef) {
      setStatusSafe('video-status', 'Pick a source video or send an existing output into the Upscale lane first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('settings_json', JSON.stringify(payload));
    if (hasFile && sourceVideoFile()) form.append('source_video_file', sourceVideoFile());
    requestInFlight = true;
    updateRunButton();
    updateUpscaleButton();
    updateInterpolateButton();
    updateActionButtons(lastHistory[0] || null);
    setStatusSafe('video-status', 'Queueing local Upscale lane…', 'ok');
    try {
      const response = await fetch('/api/video/upscale', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not queue the Upscale lane.');
      const job = data?.job || {};
      activeJobId = String(job.job_id || job.id || '').trim();
      lastVideoJobId = activeJobId || lastVideoJobId;
      applyJobSnapshot(job);
      saveVideoDraft(false);
      schedulePoll();
      await loadVideoHistory(true);
      setStatusSafe('video-status', data?.message || 'Queued local Upscale lane.', 'ok');
    } catch (error) {
      activeJobId = '';
      setStatusSafe('video-status', error?.message || 'Could not queue the Upscale lane.', 'error');
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateUpscaleButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }

  async function runVideoRepair(){
    const payload = collectRepairPayload();
    const hasFile = !!sourceRepairFile();
    const sourceRef = getRepairSourceRef();
    const hasSource = hasFile || !!(($('video-repair-source-label')?.value || '').trim()) || !!sourceRef.view_url || !!sourceRef.local_path;
    if (!hasSource) {
      setStatusSafe('video-status', 'Pick a source video or send an existing output into the Repair lane first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('settings_json', JSON.stringify(payload));
    if (hasFile && sourceRepairFile()) form.append('source_video_file', sourceRepairFile());
    requestInFlight = true;
    updateRunButton();
    updateUpscaleButton();
    updateRepairButton();
    updateInterpolateButton();
    updateActionButtons(lastHistory[0] || null);
    setStatusSafe('video-status', 'Queueing local Repair lane…', 'ok');
    try {
      const response = await fetch('/api/video/repair', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not queue the Repair lane.');
      const job = data?.job || {};
      activeJobId = String(job.job_id || job.id || '').trim();
      lastVideoJobId = activeJobId || lastVideoJobId;
      applyJobSnapshot(job);
      saveVideoDraft(false);
      schedulePoll();
      await loadVideoHistory(true);
      setStatusSafe('video-status', data?.message || 'Queued local Repair lane.', 'ok');
    } catch (error) {
      activeJobId = '';
      setStatusSafe('video-status', error?.message || 'Could not queue the Repair lane.', 'error');
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateUpscaleButton();
      updateRepairButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }



  async function runVideoInterpolate(){
    if (requestInFlight) return;
    const payload = collectInterpolatePayload();
    const hasFile = !!sourceInterpolateFile();
    const sourceRef = getInterpolateSourceRef();
    const hasSource = hasFile || !!(($('video-interpolate-source-label')?.value || '').trim()) || !!sourceRef.view_url || !!sourceRef.local_path;
    if (!hasSource) {
      setStatusSafe('video-status', 'Pick a source video or send an existing output into the Interpolate lane first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('settings_json', JSON.stringify(payload));
    if (hasFile && sourceInterpolateFile()) form.append('source_video_file', sourceInterpolateFile());
    requestInFlight = true;
    updateRunButton();
    updateUpscaleButton();
    updateRepairButton();
    updateInterpolateButton();
    updateActionButtons(lastHistory[0] || null);
    setStatusSafe('video-status', 'Queueing local Interpolate lane…', 'ok');
    try {
      const response = await fetch('/api/video/interpolate', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not queue the Interpolate lane.');
      const job = data?.job || {};
      activeJobId = String(job.job_id || job.id || '').trim();
      lastVideoJobId = activeJobId || lastVideoJobId;
      applyJobSnapshot(job);
      saveVideoDraft(false);
      schedulePoll();
      await loadVideoHistory(true);
      setStatusSafe('video-status', data?.message || 'Queued local Interpolate lane.', 'ok');
    } catch (error) {
      activeJobId = '';
      setStatusSafe('video-status', error?.message || 'Could not queue the Interpolate lane.', 'error');
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateUpscaleButton();
      updateRepairButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }

  async function cancelVideoJob(jobId=''){
    const resolvedJobId = String(jobId || activeJobId || $('video-job-status-box')?.dataset.jobId || '').trim();
    const promptId = String(lastHistory.find(item => String(item.job_id || item.id || '').trim() === resolvedJobId)?.prompt_id || '').trim() || '';
    if (!resolvedJobId && !promptId) {
      setStatusSafe('video-status', 'No active video job is available to cancel.', 'warn');
      return;
    }
    requestInFlight = true;
    updateRunButton();
    updateInterpolateButton();
    updateActionButtons(lastHistory[0] || null);
    try {
      const form = new FormData();
      form.append('job_id', resolvedJobId);
      if (promptId) form.append('prompt_id', promptId);
      const response = await fetch('/api/video/cancel', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not cancel the video job.');
      activeJobId = '';
      closeVideoProgressSocket();
      if (data?.job) applyJobSnapshot(data.job);
      await loadVideoHistory(true);
      stopPolling();
      setStatusSafe('video-status', data?.message || 'Video job cancelled.', 'warn');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not cancel the video job.', 'error');
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateRepairButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }

  async function retryVideoJob(jobId=''){
    const resolvedJobId = String(jobId || lastVideoJobId || '').trim();
    if (!resolvedJobId) {
      setStatusSafe('video-status', 'There is no previous Video job to retry yet.', 'warn');
      return;
    }
    requestInFlight = true;
    updateRunButton();
    updateInterpolateButton();
    updateActionButtons(lastHistory[0] || null);
    try {
      const form = new FormData();
      form.append('job_id', resolvedJobId);
      const response = await fetch('/api/video/retry', { method:'POST', body:form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.ok === false) throw new Error(data?.message || 'Could not retry the video job.');
      const job = data?.job || {};
      activeJobId = String(job.job_id || job.id || '').trim();
      lastVideoJobId = activeJobId || lastVideoJobId;
      applyJobSnapshot(job);
      await loadVideoHistory(true);
      schedulePoll();
      setStatusSafe('video-status', data?.message || 'Queued a retry of the selected video job.', 'ok');
    } catch (error) {
      setStatusSafe('video-status', error?.message || 'Could not retry the video job.', 'error');
    } finally {
      requestInFlight = false;
      updateRunButton();
      updateRepairButton();
      updateInterpolateButton();
      updateActionButtons(lastHistory[0] || null);
    }
  }

  function bindHistoryInteractions(){
    $('video-output-history')?.addEventListener('click', (event) => {
      const previewButton = event.target?.closest?.('[data-video-history-preview]');
      if (previewButton) {
        event.preventDefault();
        const jobId = String(previewButton.getAttribute('data-video-history-preview') || '').trim();
        const outputId = String(previewButton.getAttribute('data-video-history-output-id') || '').trim();
        if (jobId) previewHistoryJobOutput(jobId, outputId);
        return;
      }
      const retryButton = event.target?.closest?.('[data-video-history-retry]');
      if (retryButton) {
        event.preventDefault();
        const jobId = String(retryButton.getAttribute('data-video-history-retry') || '').trim();
        if (jobId) retryVideoJob(jobId);
        return;
      }
      const repairButton = event.target?.closest?.('[data-video-history-repair]');
      if (repairButton) {
        event.preventDefault();
        const jobId = String(repairButton.getAttribute('data-video-history-repair') || '').trim();
        const outputId = String(repairButton.getAttribute('data-video-history-output-id') || '').trim();
        if (jobId && outputId) queueRepairFromJobOutput(jobId, outputId);
        return;
      }
      const interpolateButton = event.target?.closest?.('[data-video-history-interpolate]');
      if (interpolateButton) {
        event.preventDefault();
        const jobId = String(interpolateButton.getAttribute('data-video-history-interpolate') || '').trim();
        const outputId = String(interpolateButton.getAttribute('data-video-history-output-id') || '').trim();
        if (jobId && outputId) queueInterpolateFromJobOutput(jobId, outputId);
        return;
      }
      const upscaleButton = event.target?.closest?.('[data-video-history-upscale]');
      if (upscaleButton) {
        event.preventDefault();
        const jobId = String(upscaleButton.getAttribute('data-video-history-upscale') || '').trim();
        const outputId = String(upscaleButton.getAttribute('data-video-history-output-id') || '').trim();
        if (jobId && outputId) queueUpscaleFromJobOutput(jobId, outputId);
      }
    });
    $('video-output-results')?.addEventListener('click', (event) => {
      const previewButton = event.target?.closest?.('[data-video-output-preview]');
      if (previewButton) {
        event.preventDefault();
        const jobId = String(previewButton.getAttribute('data-video-output-preview') || '').trim();
        const outputId = String(previewButton.getAttribute('data-video-output-id') || '').trim();
        if (jobId) previewHistoryJobOutput(jobId, outputId);
        return;
      }
      const repairButton = event.target?.closest?.('[data-video-output-repair]');
      if (repairButton) {
        event.preventDefault();
        const jobId = String(repairButton.getAttribute('data-video-output-repair') || '').trim();
        const outputId = String(repairButton.getAttribute('data-video-output-id') || '').trim();
        if (jobId && outputId) queueRepairFromJobOutput(jobId, outputId);
        return;
      }
      const interpolateButton = event.target?.closest?.('[data-video-output-interpolate]');
      if (interpolateButton) {
        event.preventDefault();
        const jobId = String(interpolateButton.getAttribute('data-video-output-interpolate') || '').trim();
        const outputId = String(interpolateButton.getAttribute('data-video-output-id') || '').trim();
        if (jobId && outputId) queueInterpolateFromJobOutput(jobId, outputId);
        return;
      }
      const button = event.target?.closest?.('[data-video-output-upscale]');
      if (!button) return;
      event.preventDefault();
      const jobId = String(button.getAttribute('data-video-output-upscale') || '').trim();
      const outputId = String(button.getAttribute('data-video-output-id') || '').trim();
      if (jobId && outputId) queueUpscaleFromJobOutput(jobId, outputId);
    });
  }

  function handleVideoBackendState(event){
    const session = event?.detail?.session?.video || {};
    const connected = !!session.connected;
    const profileId = String(session.profile_id || '').trim();
    const changed = connected !== lastKnownVideoBackendConnected || profileId !== lastKnownVideoBackendProfileId;

    lastKnownVideoBackendConnected = connected;
    lastKnownVideoBackendProfileId = profileId;

    if (!changed) return;

    if (!connected) {
      activeJobId = '';
      stopPolling();
      backendAssetCatalogLoaded = false;
      adapterCatalogLoaded = false;
      videoBackendAssetCatalog = {};
      videoAdapterCatalog = [];
      videoBackendAssetWarnings = [];

      syncVideoBackendAssetSelectors(currentProfileValue());
      syncVideoAdapterCatalogOptions();
      renderVideoBackendAssetSummary();
      renderVideoAdapterSummary();
      renderJobCard(null);
      renderVideoOutputs([], null);
      updateRunButton();
      updateInterpolateButton();
      closeVideoProgressSocket();
      updateActionButtons(null);
      return;
    }

    loadVideoBackendAssets(true);
    loadVideoAdapters(true);
    loadVideoHistory(true);
  }

  function bindVideoSurface(){
    bindVideoSupportTabs();
    applyVideoDraft();
    if (isRawFreeProfile() && $('video-free-assets-mode')) $('video-free-assets-mode').checked = true;
    syncVideoMode();
    $('video-mode')?.addEventListener('change', syncVideoMode);
    $('video-profile')?.addEventListener('change', () => {
      if (isRawFreeProfile() && $('video-free-assets-mode') && !$('video-free-assets-mode').checked) $('video-free-assets-mode').checked = true;
      if (!isRawFreeProfile() && $('video-free-assets-mode')?.checked) $('video-free-assets-mode').checked = false;
      syncVideoBackendAssetSelectors(currentProfileValue());
      if (!backendAssetCatalogLoaded) loadVideoBackendAssets(true);
      if (isQualityProfile() && !adapterCatalogLoaded) loadVideoAdapters(true);
      renderVideoSummary();
    });
    $('video-free-assets-mode')?.addEventListener('change', () => {
      const enabled = !!$('video-free-assets-mode')?.checked;
      populateProfileOptions(enabled ? 'raw_free' : currentProfileValue());
      if (enabled && $('video-profile')) $('video-profile').value = 'raw_free';
      if (!enabled && isRawFreeProfile()) {
        const fallback = findMode(currentModeValue()).default_profile || defaults().profile || 'wan22_5b_balanced';
        populateProfileOptions(fallback);
        if ($('video-profile')) $('video-profile').value = fallback;
      }
      syncVideoBackendAssetSelectors(currentProfileValue());
      renderVideoBackendAssetSummary();
      renderVideoSummary();
    });
    $('video-backend-engine-override')?.addEventListener('change', () => {
      renderVideoBackendAssetSummary();
      renderVideoSummary();
    });
    ['video-duration','video-fps','video-size','video-width','video-height','video-source-image','video-prompt','video-negative','video-seed','video-post-pipeline-template','video-quality-style','video-quality-camera','video-balanced-unet','video-balanced-encoder','video-balanced-vae','video-quality-high-noise-unet','video-quality-low-noise-unet','video-quality-encoder','video-quality-vae','video-adapter-single','video-adapter-strength','video-adapter-strength-quality','video-upscale-profile','video-upscale-target','video-upscale-fps-mode','video-upscale-custom-fps','video-upscale-container','video-upscale-codec','video-repair-strength','video-repair-focus','video-interpolate-preset','video-interpolate-target-fps','video-interpolate-multiplier','video-interpolate-quality','video-interpolate-intent','video-backend-engine-override'].forEach(id => {
      $(id)?.addEventListener('input', renderVideoSummary);
      $(id)?.addEventListener('change', renderVideoSummary);
    });
    $('video-size')?.addEventListener('change', () => {
      applyVideoSizeUiState();
      renderVideoSummary();
    });
    $('video-width')?.addEventListener('input', () => {
      if (currentVideoSizePreset() === 'custom') applyVideoSizeUiState();
    });
    $('video-height')?.addEventListener('input', () => {
      if (currentVideoSizePreset() === 'custom') applyVideoSizeUiState();
    });
    $('video-source-image')?.addEventListener('input', () => {
      if (!String($('video-source-image')?.value || '').trim() && !sourceImageFile()) {
        refreshVideoSourceImageMeta(null);
      }
    });
    $('video-source-image-file')?.addEventListener('change', async () => {
      const file = sourceImageFile();
      if ($('video-source-image')) $('video-source-image').value = file ? file.name : '';
      await refreshVideoSourceImageMeta(file);
      renderVideoSummary();
    });
    $('video-upscale-source-file')?.addEventListener('change', () => {
      const file = sourceVideoFile();
      if ($('video-upscale-source-label')) $('video-upscale-source-label').value = file ? file.name : '';
      if (file && $('video-upscale-source-ref')) $('video-upscale-source-ref').value = '';
      renderUpscaleSummary();
    });
    $('video-repair-source-file')?.addEventListener('change', () => {
      const file = sourceRepairFile();
      if ($('video-repair-source-label')) $('video-repair-source-label').value = file ? file.name : '';
      if (file && $('video-repair-source-ref')) $('video-repair-source-ref').value = '';
      renderRepairSummary();
    });
    $('video-interpolate-source-file')?.addEventListener('change', () => {
      const file = sourceInterpolateFile();
      if ($('video-interpolate-source-label')) $('video-interpolate-source-label').value = file ? file.name : '';
      if (file && $('video-interpolate-source-ref')) $('video-interpolate-source-ref').value = '';
      renderInterpolateSummary();
    });
    $('video-repair-stabilize')?.addEventListener('change', renderVideoSummary);
    $('video-adapters-enabled')?.addEventListener('change', renderVideoSummary);
    $('video-adapter-single')?.addEventListener('change', renderVideoSummary);
    $('video-adapter-strength-quality')?.addEventListener('input', () => { if ($('video-adapter-strength')) $('video-adapter-strength').value = $('video-adapter-strength-quality').value || $('video-adapter-strength').value; renderVideoSummary(); });
    $('video-adapter-preset-select')?.addEventListener('change', () => {
      renderVideoSummary();
    });
    $('video-adapter-high-noise')?.addEventListener('change', renderVideoSummary);
    $('video-adapter-low-noise')?.addEventListener('change', renderVideoSummary);
    $('btn-video-load-adapter-preset')?.addEventListener('click', () => applyVideoAdapterPairPreset(adapterPairPresetSelectionId(), { announce:true }));
    $('btn-video-save-adapter-preset')?.addEventListener('click', () => saveVideoAdapterPairPreset(false));
    $('btn-video-update-adapter-preset')?.addEventListener('click', () => saveVideoAdapterPairPreset(true));
    $('btn-video-delete-adapter-preset')?.addEventListener('click', deleteVideoAdapterPairPreset);
    $('btn-video-refresh-assets')?.addEventListener('click', () => loadVideoBackendAssets(false));
    $('btn-video-refresh-adapters')?.addEventListener('click', () => loadVideoAdapters(false));
    $('btn-video-save-brief')?.addEventListener('click', () => saveVideoDraft(true));
    $('btn-video-action-save')?.addEventListener('click', () => saveVideoDraft(true));
    $('btn-video-build-summary')?.addEventListener('click', () => { renderVideoSummary(); setStatusSafe('video-status', 'Refreshed the video summary.', 'ok'); });
    $('btn-video-clear-brief')?.addEventListener('click', clearVideoDraft);
    $('btn-video-action-clear')?.addEventListener('click', clearVideoDraft);
    $('btn-video-open-admin')?.addEventListener('click', () => { if (typeof window.switchMainTab === 'function') window.switchMainTab('admin'); });
    $('btn-video-open-generation')?.addEventListener('click', () => { if (typeof window.switchMainTab === 'function') window.switchMainTab('generate'); });
    $('btn-video-run')?.addEventListener('click', runBalancedVideo);
    $('btn-video-upscale-run')?.addEventListener('click', runVideoUpscale);
    $('btn-video-upscale-clear-source')?.addEventListener('click', () => clearUpscaleSource({ announce:true }));
    $('btn-video-repair-run')?.addEventListener('click', runVideoRepair);
    $('btn-video-repair-clear-source')?.addEventListener('click', () => clearRepairSource({ announce:true }));
    $('btn-video-interpolate-run')?.addEventListener('click', runVideoInterpolate);
    $('btn-video-interpolate-clear-source')?.addEventListener('click', () => clearInterpolateSource({ announce:true }));
    $('btn-video-cancel')?.addEventListener('click', () => cancelVideoJob());
    $('btn-video-retry')?.addEventListener('click', () => retryVideoJob());
    $('btn-video-refresh-history')?.addEventListener('click', () => loadVideoHistory(false));
    $('btn-video-preview-open')?.addEventListener('click', () => { if (videoPreviewState.url) window.open(videoPreviewState.url, '_blank', 'noopener'); });
    $('btn-video-preview-clear')?.addEventListener('click', () => clearVideoPreview({ announce:true }));
    $('btn-video-preview-loop')?.addEventListener('click', () => { videoPreviewState = { ...videoPreviewState, loop: !(videoPreviewState.loop !== false) }; renderVideoPreview(); });
    $('video-saved-preset-select')?.addEventListener('change', () => { const picked = findSavedVideoPreset(savedVideoPresetSelectionId()); if (picked && $('video-saved-preset-category')) $('video-saved-preset-category').value = picked.category || 'custom'; renderSavedVideoPresetSummary(); });
    $('btn-video-load-saved-preset')?.addEventListener('click', () => applySavedVideoPreset(savedVideoPresetSelectionId(), { announce:true }));
    $('btn-video-save-video-preset')?.addEventListener('click', () => saveVideoPresetRecord(false));
    $('btn-video-update-video-preset')?.addEventListener('click', () => saveVideoPresetRecord(true));
    $('btn-video-delete-video-preset')?.addEventListener('click', deleteVideoPresetRecord);
    $('btn-video-set-default-video-preset')?.addEventListener('click', setDefaultVideoPresetRecord);
    $('btn-video-clear-default-video-preset')?.addEventListener('click', clearDefaultVideoPresetRecord);
    $('video-saved-preset-category')?.addEventListener('change', renderSavedVideoPresetSummary);
    $('video-interpolate-preset')?.addEventListener('change', applyInterpolatePreset);
    document.addEventListener('neo-backend-state', handleVideoBackendState);
    bindHistoryInteractions();
    renderVideoSummary();
    renderVideoActionBar(null);
    renderVideoPreview();
    renderUpscaleSummary();
    renderInterpolateSummary();
    loadVideoBackendAssets(true);
    loadVideoAdapters(true);
    loadSavedVideoPresets(true);
    loadVideoHistory(true);
  }

  window.neoRefreshVideoSurface = renderVideoSummary;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindVideoSurface, { once: true });
  else bindVideoSurface();
})();
