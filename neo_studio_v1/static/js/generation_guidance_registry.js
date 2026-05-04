(function () {
  const REGISTRY = {
    page_intro: 'Prep image workflows first, then connect an image backend only when you want to run jobs.',
    summary_card_help: 'Build prompts, stage workflow values, and queue jobs from Neo Studio without opening a separate backend UI.',
    action_zone_help: 'Main launch controls live here so the workspace starts with the part you use first: run, pause, stop, queue, and watch progress.',
    sections: {
      'generation-output-settings-wrap': { hint: 'Choose where outputs save and how Neo stores metadata for rebuilds and browsing later.' },
      'generation-workflow-wrap': { hint: 'Core generation settings: mode, model, prompt, size, seed, and the values that define the main render.' },
      'generation-hires-settings': { hint: 'Add a second pass for upscale + refine when the base image is good and you want a cleaner final render.' },
      'generation-image-upscale-settings': { hint: 'Use Image Upscale after generation or after Upscale Lab when you want a preserve-first export upscale with optional CodeFormer face cleanup.' },
      'generation-supir-settings': { hint: 'Use SUPIR only when you want stronger restoration or upscale behavior than the standard Upscale Lab pass.' },
      'generation-lora-settings': { hint: 'Stack LoRAs, control strengths, and keep the active rows readable before they hit the final payload.' },
      'generation-ti-settings': { hint: 'Browse Embeddings, preview trigger tokens, and keep prompt-level inserts easy to manage.' },
      'generation-detailer-settings': { hint: 'Use Selective Repair (ADetailer) for faces, hands, or other targeted repair steps after the main generation.' },
      'generation-controlnet-settings': { hint: 'Guide pose, structure, or composition with ControlNet only when you need stronger image conditioning.' },
      'generation-ipadapter-settings': { hint: 'Use advanced reference controls when reference images should steer identity, mood, or composition without rebuilding the whole prompt.' },
      'generation-style-addons': { hint: 'Stack saved styles, trim them as chips, or load one back into the editor fields for cleanup.' },
      'generation-wildcards': { hint: 'Resolve prompt variations in Neo first so queued jobs stay readable and reproducible before they hit ComfyUI.' },
      'generation-reliability-wrap': { hint: 'Quick checks that call out risky combinations, missing pieces, or expensive settings before you queue.' },
      'generation-smart-wrap': { hint: 'Recipe helpers and smart defaults live here so you can reuse stronger setups without rebuilding them every time.' },
      'generation-power-wrap': { hint: 'Use compare tools, rebuild helpers, and advanced inspection only when you want to go beyond the main workspace.' },
    },
  };

  function applyGenerationGuidance() {
    const intro = document.getElementById('generation-tab-intro');
    if (intro && REGISTRY.page_intro) intro.textContent = REGISTRY.page_intro;
    const summaryHelp = document.getElementById('generation-shell-summary-help');
    if (summaryHelp && REGISTRY.summary_card_help) summaryHelp.textContent = REGISTRY.summary_card_help;
    const actionHelp = document.getElementById('generation-action-help');
    if (actionHelp && REGISTRY.action_zone_help) actionHelp.textContent = REGISTRY.action_zone_help;
    Object.entries(REGISTRY.sections || {}).forEach(([accordionId, section]) => {
      const block = document.querySelector(`[data-accordion-id="${accordionId}"]`);
      const hint = block?.querySelector(':scope > summary .accordion-hint') || block?.querySelector('.accordion-hint');
      if (hint && section?.hint) hint.textContent = section.hint;
    });
  }

  window.NeoGenerationGuidanceRegistry = Object.freeze(REGISTRY);
  window.applyNeoGenerationGuidance = applyGenerationGuidance;
  document.addEventListener('DOMContentLoaded', applyGenerationGuidance);
})();
