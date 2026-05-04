// Neo Studio Generation Feature Availability Registry
// Phase 6: single source of truth for per-family feature gates.
(function () {
  const FAMILY_FEATURES = Object.freeze({
    sdxl_sd: Object.freeze({
      checkpoint_model: true,
      gguf_model: false,
      dynamic_thresholding: true,
      controlnet: true,
      ipadapter: true,
      detailer: true,
      qwen_multi_source: false,
      qwen_lanpaint: false,
      launch_enabled: true,
    }),
    flux: Object.freeze({
      checkpoint_model: false,
      gguf_model: true,
      dynamic_thresholding: false,
      controlnet: true,
      ipadapter: false,
      detailer: true,
      qwen_multi_source: false,
      qwen_lanpaint: false,
      launch_enabled: true,
    }),
    qwen_image_edit: Object.freeze({
      checkpoint_model: false,
      gguf_model: true,
      dynamic_thresholding: false,
      controlnet: true,
      ipadapter: false,
      detailer: true,
      qwen_multi_source: true,
      qwen_lanpaint: true,
      launch_enabled: true,
    }),
    zimage: Object.freeze({
      checkpoint_model: false,
      gguf_model: false,
      dynamic_thresholding: false,
      controlnet: false,
      ipadapter: false,
      detailer: false,
      qwen_multi_source: false,
      qwen_lanpaint: false,
      launch_enabled: false,
    }),
  });

  let activeFamily = 'sdxl_sd';

  function normalizeFamily(family) {
    const raw = String(family || activeFamily || 'sdxl_sd').trim().toLowerCase();
    if (FAMILY_FEATURES[raw]) return raw;
    if (raw === 'sdxl' || raw === 'sd') return 'sdxl_sd';
    if (raw === 'qwen' || raw === 'qwen_image') return 'qwen_image_edit';
    return 'sdxl_sd';
  }

  function getFamilyFeatures(family) {
    return Object.assign({}, FAMILY_FEATURES[normalizeFamily(family)] || FAMILY_FEATURES.sdxl_sd);
  }

  function isFeatureAllowed(feature, family) {
    const features = getFamilyFeatures(family);
    return features[String(feature || '').trim()] === true;
  }

  function setActiveFamily(family) {
    activeFamily = normalizeFamily(family);
    document.documentElement.dataset.neoGenerationFamily = activeFamily;
    return activeFamily;
  }

  function getActiveFamily() {
    return activeFamily;
  }

  function featureSummary(family) {
    const features = getFamilyFeatures(family);
    return Object.keys(features).filter(key => features[key] === true).sort();
  }

  window.NeoGenerationFeatureAvailability = Object.freeze({
    families: FAMILY_FEATURES,
    normalizeFamily,
    getFamilyFeatures,
    isFeatureAllowed,
    setActiveFamily,
    getActiveFamily,
    featureSummary,
  });
})();
