(function () {
  const VIEW_KEY = 'neo_generation_view_mode';
  const HELP_KEY = 'neo_generation_help_mode';
  const ROOT_SELECTOR = '#tab-generate';

  const state = {
    view: 'advanced',
    help: true,
  };

  const sectionGuides = {
    'core generation': {
      badge: 'Beginner-safe',
      tags: ['Core flow', 'Start here'],
      what: 'This is the main image workspace. Pick the mode, model, size, prompts, and source image here before you touch advanced add-ons.',
      when: 'Use this first for every generation, even if you plan to add LoRA, ControlNet, or cleanup passes later.',
      defaults: ['Txt2img for fresh images', '1024 square or a built-in size preset', '20–32 steps', 'CFG around 5–7 for SDXL-style checkpoints'],
      mistakes: ['Changing too many things at once', 'Using img2img or inpaint without checking source size', 'Forgetting that source image modes usually need denoise tuning'],
      needs: ['Connected image backend', 'Checkpoint selected'],
      best: 'First-pass generation and clean baseline testing.'
    },
    'prompt payload': {
      badge: 'Creative-first',
      tags: ['Prompting', 'Reuse'],
      what: 'This is where your final generation prompt lives. It should be the cleaned-up version of whatever came from Prompt Studio, captions, styles, keywords, or character inserts.',
      when: 'Use this when you are shaping the actual final wording that gets sent to the workflow.',
      defaults: ['Keep the main idea near the front', 'Use the negative prompt only for issues you actually want to avoid', 'Save a good prompt once it starts working'],
      mistakes: ['Stuffing every idea into one prompt', 'Using giant negative prompts without testing', 'Changing prompt, model, and add-ons all at the same time'],
      needs: ['A working positive prompt'],
      best: 'Turning ideas into a reusable generation recipe.'
    },
    'advanced raw mask override': {
      badge: 'Expert',
      tags: ['Masking', 'Manual'],
      what: 'This lets you override the normal mask flow with a prepared mask file that already matches the source image.',
      when: 'Use it only when you already created a precise mask outside Neo or need exact repeatable mask alignment.',
      defaults: ['Leave this off unless you know why you need it'],
      mistakes: ['Using a mask that does not match the source image dimensions', 'Forgetting that inverted masks can target the wrong region'],
      needs: ['Source image', 'Prepared black/white mask'],
      best: 'Precise repair workflows and externally prepared masks.'
    },
    'upscale lab': {
      badge: 'Advanced',
      tags: ['Upscale', 'Polish'],
      what: 'This adds a second pass after the first generation so you can upscale and redraw details instead of relying on the first pass alone.',
      when: 'Use it when the base image is good but needs more detail, sharper structure, or a larger output size.',
      defaults: ['Latent mode first', '1.5x to 2x upscale', 'Denoise around 0.10–0.14 for latent preserve work', 'Keep second-pass steps moderate'],
      mistakes: ['Using too much denoise and changing the image identity', 'Jumping to huge upscale sizes too early', 'Stacking this with every other heavy feature at once'],
      needs: ['A solid base generation', 'Optional upscale model for image-upscale mode'],
      best: 'Final polish after you already like the base composition.'
    },
    'supir restoration': {
      badge: 'Experimental',
      tags: ['Heavy', 'Restoration'],
      what: 'This is a more opinionated restoration and upscale pass that runs after the normal generation pipeline.',
      when: 'Use it when you need aggressive cleanup or restoration and you already know the basic hires pass is not enough.',
      defaults: ['Keep it off for first-pass work', 'Use moderate upscale and steps until you trust the result'],
      mistakes: ['Using it as the first fix for every image', 'Running it without the required models', 'Forgetting it is heavier and slower than normal hires'],
      needs: ['SUPIR node installed', 'SUPIR model', 'SDXL model'],
      best: 'Late-stage cleanup on strong images, not early exploration.'
    },
    'lora settings': {
      badge: 'Advanced',
      tags: ['Style', 'Character'],
      what: 'LoRAs let you inject a learned style, subject, look, or behavior into the generation.',
      when: 'Use them when the checkpoint alone cannot hit the look or character consistency you need.',
      defaults: ['Start with one LoRA', 'Use moderate strength first', 'Only stack more after you confirm the first one behaves well'],
      mistakes: ['Stacking too many LoRAs immediately', 'Using mismatched base-model families', 'Ignoring trigger words or recommended strength ranges'],
      needs: ['Compatible LoRA', 'Main model family that matches it'],
      best: 'Style shifts, branded looks, and repeatable character flavor.'
    },
    'embeddings': {
      badge: 'Advanced',
      tags: ['Prompt token', 'Cleanup'],
      what: 'Textual inversions are prompt tokens trained to represent a concept, style, or corrective embedding.',
      when: 'Use them when a specific token gives you a better or cleaner result than normal prompt wording alone.',
      defaults: ['Only add tokens you trust', 'Keep them separate from LoRAs mentally'],
      mistakes: ['Treating TI like a LoRA', 'Forgetting whether the token belongs in positive or negative'],
      needs: ['Compatible embedding token'],
      best: 'Small targeted prompt boosts or corrective embeddings.'
    },
    'selective repair': {
      badge: 'Experimental',
      tags: ['Repair', 'Detection'],
      what: 'This runs a detector-guided detail pass to repair or refine specific regions like faces, hands, or selected classes.',
      when: 'Use it after the base image is close but has localized issues.',
      defaults: ['Use moderate confidence', 'Small denoise', 'Use main prompt first'],
      mistakes: ['Trying to fix a weak base image with detailer only', 'Using oversized bbox growth', 'Forgetting detector/model dependencies'],
      needs: ['Detailer-compatible nodes', 'Detector model', 'Optional SAM refinement'],
      best: 'Fixing localized weak spots after a good first pass.'
    },
    'controlnet settings': {
      badge: 'Advanced',
      tags: ['Structure', 'Guidance'],
      what: 'ControlNet uses an extra control image to guide pose, edges, depth, layout, or structure without rewriting the whole prompt.',
      when: 'Use it when composition or structure matters more than free exploration.',
      defaults: ['One unit first', 'Start with moderate strength', 'Use the simplest valid preprocessor'],
      mistakes: ['Turning strength too high and choking creativity', 'Using the wrong preprocessor/model combo', 'Forgetting to supply a control image'],
      needs: ['ControlNet model', 'Optional preprocessor', 'Control image'],
      best: 'Pose matching, edge guidance, layout anchoring, and composition control.'
    },
    'advanced reference controls': {
      badge: 'Advanced',
      tags: ['Reference', 'Identity'],
      what: 'IP-Adapter uses one or more reference images to guide look, identity, or style without turning the whole workflow into img2img.',
      when: 'Use it when you want stronger reference-image influence or FaceID-style consistency.',
      defaults: ['Start with Standard mode', 'Use one clean reference image', 'Keep weight moderate'],
      mistakes: ['Using the wrong model or CLIP Vision combo', 'Overweighting the reference', 'Mixing FaceID and standard assumptions'],
      needs: ['IP-Adapter node path', 'IP-Adapter model', 'CLIP Vision model', 'Reference image'],
      best: 'Reference-led consistency and identity steering.'
    },
    'character creator': {
      badge: 'Creative-first',
      tags: ['Character', 'Library'],
      what: 'This lets you build a reusable character block from Library pieces and insert it directly into the generation prompt.',
      when: 'Use it when you want repeatable character setup without hand-writing the whole block every time.',
      defaults: ['Keep one character slot focused', 'Use description after keyword only when it helps clarity'],
      mistakes: ['Overloading a character block with unrelated traits', 'Appending too many fragments without cleanup'],
      needs: ['Library character data'],
      best: 'Repeatable character prompts and quick creative assembly.'
    },
    'keyword snippets': {
      badge: 'Creative-first',
      tags: ['Library', 'Prompt assist'],
      what: 'This browses saved keyword libraries and snippets so you can insert good prompt pieces without leaving the generation tab.',
      when: 'Use it when you know the vibe you want but do not want to type everything from scratch.',
      defaults: ['Insert only the pieces you really need', 'Preview before inserting'],
      mistakes: ['Stuffing too many keyword blocks into one prompt', 'Mixing unrelated snippet styles'],
      needs: ['Library entries'],
      best: 'Fast ideation and prompt reuse.'
    },
    'style add-ons': {
      badge: 'Creative-first',
      tags: ['Style stack', 'Reusable'],
      what: 'This lets you stack reusable style presets on top of the main prompt without rewriting the whole prompt by hand.',
      when: 'Use it when you want to keep a base prompt stable but swap mood, finish, or visual language.',
      defaults: ['Start with one style', 'Stack carefully and read the positive/negative text'],
      mistakes: ['Stacking conflicting styles', 'Forgetting that style negatives can fight your prompt'],
      needs: ['Saved generation styles'],
      best: 'Fast style iteration without rewriting the core concept.'
    },
    'wildcards': {
      badge: 'Expert',
      tags: ['Automation', 'Variants'],
      what: 'Wildcards let Neo generate prompt variants from inline choices or file-based token lists.',
      when: 'Use them when you want structured prompt variation or batch idea exploration.',
      defaults: ['Preview before queue', 'Keep the wildcard set focused'],
      mistakes: ['Generating too many variations without reviewing the resolved prompt', 'Using noisy wildcard files with mixed concepts'],
      needs: ['Wildcard files or inline tokens'],
      best: 'Variant testing and structured batch prompt exploration.'
    }
  };

  const optionExplainers = [
    { selector: '#generation-workflow-type', resolve: value => ({
      txt2img: 'Start from text only. Best for fresh images and early exploration.',
      img2img: 'Use a source image and redraw it with prompt guidance. Great for controlled changes.',
      inpaint: 'Repair or replace a masked region while keeping the rest of the image grounded.',
      outpaint: 'Expand beyond the current canvas using a source image and padding.'
    }[String(value || '').trim()] || 'Choose how much the workflow should rely on a source image.') },
    { selector: '#generation-sampler', resolve: value => samplerHelp(value) },
    { selector: '#generation-scheduler', resolve: value => schedulerHelp(value) },
    { selector: '#generation-source-resize-mode', resolve: value => ({
      native: 'Keeps the source image size as-is. Safest when you want minimal surprise.',
      fit: 'Fits the source into the target size without stretching. Good default for most cases.',
      crop: 'Fills the target frame by cropping overflow. Use when framing matters more than full coverage.',
      stretch: 'Forces the source to match the target size. Only use when distortion is acceptable.'
    }[String(value || '').trim()] || 'Controls how the source image is prepared before generation.') },
    { selector: '#generation-inpaint-target', resolve: value => ({
      masked: 'Only the masked area is treated as the editable target. Best normal choice.',
      unmasked: 'Edits everything except the masked area. Useful for protecting a subject while changing the surroundings.'
    }[String(value || '').trim()] || 'Controls which region is considered editable.') },
    { selector: '#generation-inpaint-context', resolve: value => ({
      full_image: 'The whole image helps guide the inpaint pass. Best for keeping global consistency.',
      masked_focus: 'Focuses more tightly on the masked region. Better for smaller local repairs.'
    }[String(value || '').trim()] || 'Controls how much surrounding image context is used during inpainting.') },
    { selector: '#generation-refine-mode', resolve: value => ({
      latent: 'Upscales in latent space before redraw. Usually the best first choice for normal hires work.',
      image_upscale: 'Upscales the current image through a preserve-first refine pass. Best when you want a specific upscaler model involved without rebuilding the whole composition.'
    }[String(value || '').trim()] || 'Controls how the hires pass prepares the second-stage image.') },
    { selector: '#generation-supir-color-fix-type', resolve: value => ({
      Wavelet: 'Stronger color correction with a more corrective feel. Good when restoration drifts color.',
      AdaIn: 'Softer style-aware color alignment. Good when you want a gentler correction.',
      None: 'No color correction. Use only if the raw SUPIR result already looks right.'
    }[String(value || '').trim()] || 'Controls how the restoration pass tries to stabilize color.') },
    { selector: '#generation-detailer-provider', resolve: value => ({
      ultralytics: 'Uses Ultralytics-style detectors. Usually the more common setup for detection-based repair.',
      onnx: 'Uses ONNX-based detectors. Handy when your setup is built around ONNX detector assets.'
    }[String(value || '').trim()] || 'Chooses which detector backend the detailer should use.') },
    { selector: '#generation-detailer-detector-type', resolve: value => ({
      bbox: 'Detects boxes first, then builds the repair region from those boxes. Good for faces and simple targets.',
      segm: 'Uses segmentation-style masks when supported. Better when you need tighter region isolation.'
    }[String(value || '').trim()] || 'Controls how the detailer defines the repair region.') },
    { selector: '#generation-controlnet-preprocessor, .generation-controlnet-preprocessor', resolve: value => controlnetPreprocessorHelp(value) },
    { selector: '#generation-ipadapter-mode, .generation-ipadapter-mode', resolve: value => ({
      standard: 'Uses reference-image guidance for look or style without FaceID-specific identity logic.',
      faceid: 'Uses FaceID-style identity guidance and extra provider settings for stronger face consistency.'
    }[String(value || '').trim()] || 'Controls how the reference image is interpreted by IP-Adapter.') },
    { selector: '#generation-ipadapter-weight-type, .generation-ipadapter-weight-type', resolve: value => ipAdapterWeightHelp(value) },
    { selector: '#generation-ipadapter-combine-embeds, .generation-ipadapter-combine-embeds', resolve: value => ipAdapterCombineHelp(value) },
    { selector: '#generation-ipadapter-embeds-scaling, .generation-ipadapter-embeds-scaling', resolve: value => ipAdapterEmbedHelp(value) },
  ];

  const staticFieldHelpers = [
    { selector: '#generation-ipadapter-image, .generation-ipadapter-image', title: 'Reference image guide', items: [
      { label: 'Standard mode', text: 'Uses the selected IP-Adapter model plus CLIP Vision and one or more reference images.' },
      { label: 'FaceID mode', text: 'Uses the FaceID preset + provider + CLIP Vision + one or more reference images.' }
    ] }
  ];

  const quickHiddenTitles = new Set([]);

  const expertOnlyTitles = new Set([]);

  const quickHideSelectors = [];

  function $(id) {
    return document.getElementById(id);
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function normalizeTitle(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function loadState() {
    const savedView = String(localStorage.getItem(VIEW_KEY) || '').trim().toLowerCase();
    if (savedView === 'quick' || savedView === 'advanced' || savedView === 'expert') state.view = savedView;
    const savedHelp = String(localStorage.getItem(HELP_KEY) || '').trim().toLowerCase();
    if (savedHelp === 'off') state.help = false;
    if (savedHelp === 'on') state.help = true;
  }

  function saveState() {
    try {
      localStorage.setItem(VIEW_KEY, state.view);
      localStorage.setItem(HELP_KEY, state.help ? 'on' : 'off');
    } catch (_) {}
  }

  function viewSummary(view) {
    if (view === 'quick') return 'Quick keeps the core creative flow visible and hides the heavier stacks.';
    if (view === 'expert') return 'Expert shows every layer, including the more niche or risky controls.';
    return 'Advanced keeps the full working workspace visible without pushing every niche option to the front.';
  }

  function foundationBarTemplate() {
    return `
      <div class="neo-ux-foundation-bar" id="generation-ux-foundation-bar">
        <div class="neo-ux-foundation-main">
          <div>
            <div class="neo-ux-foundation-label">Workspace view</div>
            <div class="neo-ux-segmented" role="tablist" aria-label="Image workspace view">
              <button class="neo-ux-segment-btn" type="button" data-view-mode="quick">Quick</button>
              <button class="neo-ux-segment-btn" type="button" data-view-mode="advanced">Advanced</button>
              <button class="neo-ux-segment-btn" type="button" data-view-mode="expert">Expert</button>
            </div>
          </div>
          <div class="neo-ux-help-wrap">
            <div class="neo-ux-foundation-label">Guided help</div>
            <button class="btn neo-ux-help-toggle" id="btn-generation-help-mode" type="button">Help mode</button>
          </div>
        </div>
        <div class="neo-ux-foundation-note" id="generation-ux-foundation-note"></div>
      </div>`;
  }

  function injectFoundationBar() {
    const header = document.querySelector('#tab-generate .generation-global-panel .row-between');
    if (!header || $('generation-ux-foundation-bar')) return;
    header.insertAdjacentHTML('afterend', foundationBarTemplate());
    document.querySelectorAll('[data-view-mode]').forEach(btn => {
      btn.addEventListener('click', () => setViewMode(btn.dataset.viewMode || 'advanced'));
    });
    $('btn-generation-help-mode')?.addEventListener('click', () => setHelpMode(!state.help));
    syncFoundationBar();
  }

  function syncFoundationBar() {
    const note = $('generation-ux-foundation-note');
    if (note) note.textContent = viewSummary(state.view);
    document.querySelectorAll('[data-view-mode]').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.viewMode === state.view);
    });
    const helpBtn = $('btn-generation-help-mode');
    if (helpBtn) {
      helpBtn.classList.toggle('is-on', !!state.help);
      helpBtn.textContent = state.help ? 'Help mode: On' : 'Help mode: Off';
    }
  }

  function setViewMode(view) {
    const next = String(view || '').trim().toLowerCase();
    if (!next || !['quick', 'advanced', 'expert'].includes(next)) return;
    state.view = next;
    applyViewMode();
    syncFoundationBar();
    saveState();
  }

  function setHelpMode(enabled) {
    state.help = !!enabled;
    applyHelpMode();
    syncFoundationBar();
    saveState();
  }

  function applyHelpMode() {
    document.body.dataset.neoGenerationHelp = state.help ? 'on' : 'off';
    document.querySelectorAll('.neo-guide-button').forEach(btn => btn.classList.toggle('is-help-on', !!state.help));
  }

  function annotateSectionLevels() {
    document.querySelectorAll(`${ROOT_SELECTOR} details.accordion-block`).forEach(block => {
      const title = normalizeTitle(block.querySelector('.accordion-title')?.textContent || '');
      let level = 'base';
      if (quickHiddenTitles.has(title)) level = 'advanced';
      if (expertOnlyTitles.has(title)) level = 'expert';
      block.dataset.genLevel = level;
      block.classList.toggle('neo-ux-quick-hidden', level !== 'base');
      block.classList.toggle('neo-ux-expert-only', level === 'expert');
    });
    quickHideSelectors.forEach(selector => {
      document.querySelectorAll(`${ROOT_SELECTOR} ${selector}`).forEach(el => {
        el.dataset.genLevel = 'advanced';
      });
    });
  }

  function shouldHideForView(level) {
    if (state.view === 'expert') return false;
    if (state.view === 'advanced') return level === 'expert';
    return level === 'advanced' || level === 'expert';
  }

  function applyViewMode() {
    annotateSectionLevels();
    document.body.dataset.neoGenerationView = state.view;
    document.querySelectorAll(`${ROOT_SELECTOR} [data-gen-level]`).forEach(el => {
      const hidden = shouldHideForView(String(el.dataset.genLevel || 'base').trim().toLowerCase());
      el.classList.toggle('neo-ux-view-hidden', hidden);
      if (hidden && el.tagName === 'DETAILS') el.open = false;
    });
    if (state.view === 'quick') {
      ensureDetailsOpen('character creator', false);
      ensureDetailsOpen('style add-ons', false);
      ensureDetailsOpen('keyword snippets', false);
    }
  }

  function ensureDetailsOpen(title, openState) {
    const target = Array.from(document.querySelectorAll(`${ROOT_SELECTOR} details.accordion-block`)).find(block => normalizeTitle(block.querySelector('.accordion-title')?.textContent || '') === normalizeTitle(title));
    if (target) target.open = !!openState;
  }

  function guideContentHtml(meta) {
    const defaults = Array.isArray(meta.defaults) ? meta.defaults.map(item => `<li>${escapeHtml(item)}</li>`).join('') : '';
    const mistakes = Array.isArray(meta.mistakes) ? meta.mistakes.map(item => `<li>${escapeHtml(item)}</li>`).join('') : '';
    const needs = Array.isArray(meta.needs) ? meta.needs.map(item => `<li>${escapeHtml(item)}</li>`).join('') : '';
    return `
      <div class="neo-guide-grid">
        <div class="neo-guide-block">
          <div class="neo-guide-title">What it does</div>
          <div class="neo-guide-copy">${escapeHtml(meta.what || '')}</div>
        </div>
        <div class="neo-guide-block">
          <div class="neo-guide-title">When to use it</div>
          <div class="neo-guide-copy">${escapeHtml(meta.when || '')}</div>
        </div>
        <div class="neo-guide-block">
          <div class="neo-guide-title">Safe defaults</div>
          <ul class="neo-guide-list">${defaults || '<li>Use the section default values first.</li>'}</ul>
        </div>
        <div class="neo-guide-block">
          <div class="neo-guide-title">Common mistakes</div>
          <ul class="neo-guide-list">${mistakes || '<li>Avoid changing too many variables at once.</li>'}</ul>
        </div>
        <div class="neo-guide-block">
          <div class="neo-guide-title">Needs</div>
          <ul class="neo-guide-list">${needs || '<li>No extra dependencies listed.</li>'}</ul>
        </div>
        <div class="neo-guide-block">
          <div class="neo-guide-title">Best for</div>
          <div class="neo-guide-copy">${escapeHtml(meta.best || '')}</div>
        </div>
      </div>`;
  }

  let guideModalRefs = null;

  function ensureGuideModal() {
    if (guideModalRefs) return guideModalRefs;
    const backdrop = document.createElement('div');
    backdrop.id = 'neo-generation-guide-modal';
    backdrop.className = 'modal-backdrop hidden';
    backdrop.innerHTML = `
      <div class="modal-shell modal-sm neo-guide-modal-shell">
        <div class="modal-header">
          <div>
            <div class="stat-title">Guide</div>
            <div class="generation-support-title" id="neo-generation-guide-modal-title">Section guide</div>
          </div>
          <button class="modal-close" type="button" aria-label="Close guide">×</button>
        </div>
        <div class="modal-body" id="neo-generation-guide-modal-body"></div>
      </div>`;
    document.body.appendChild(backdrop);
    const title = backdrop.querySelector('#neo-generation-guide-modal-title');
    const body = backdrop.querySelector('#neo-generation-guide-modal-body');
    const closeButton = backdrop.querySelector('.modal-close');
    const close = () => {
      backdrop.classList.add('hidden');
      document.body.classList.remove('modal-open');
      if (guideModalRefs?.activeButton) guideModalRefs.activeButton.classList.remove('is-open');
      if (guideModalRefs) guideModalRefs.activeButton = null;
    };
    closeButton?.addEventListener('click', close);
    backdrop.addEventListener('click', event => {
      if (event.target === backdrop) close();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !backdrop.classList.contains('hidden')) close();
    });
    guideModalRefs = { backdrop, title, body, close, activeButton: null };
    return guideModalRefs;
  }

  function openGuideModal(titleText, meta, button) {
    const modal = ensureGuideModal();
    if (modal.activeButton) modal.activeButton.classList.remove('is-open');
    modal.activeButton = button || null;
    modal.title.textContent = String(titleText || 'Section guide');
    modal.body.innerHTML = guideContentHtml(meta);
    modal.backdrop.classList.remove('hidden');
    document.body.classList.add('modal-open');
    modal.activeButton?.classList.add('is-open');
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function resolveFieldLabel(field) {
    if (!field) return null;
    if (field.id) {
      const byFor = document.querySelector(`label[for="${field.id}"]`);
      if (byFor) return byFor;
    }
    return field.parentElement?.querySelector(':scope > label') || null;
  }

  function renderHelpItems(button, titleText, items) {
    if (!button) return;
    const popover = button.querySelector('.neo-field-help-popover');
    if (!popover) return;
    const titleNode = popover.querySelector('.neo-field-help-popover-title');
    const content = popover.querySelector('.neo-field-help-list');
    if (titleNode) titleNode.textContent = String(titleText || 'Field guide').trim() || 'Field guide';
    if (!content) return;
    content.innerHTML = (Array.isArray(items) ? items : []).map(item => `
      <div class="neo-field-help-item${item.active ? ' is-active' : ''}">
        <div class="neo-field-help-item-label">${escapeHtml(item.label)}</div>
        <div class="neo-field-help-item-text">${escapeHtml(item.text)}</div>
      </div>`).join('');
  }

  function injectGuideIntoAccordion(block, titleKey, meta) {
    const summary = block.querySelector(':scope > summary.accordion-summary');
    if (!summary || summary.querySelector('.neo-guide-button')) return;
    const actionWrap = document.createElement('div');
    actionWrap.className = 'neo-guide-actions neo-guide-actions-accordion';
    actionWrap.innerHTML = `
      <button class="btn btn-small neo-guide-button" type="button">? Guide</button>
      <div class="neo-guide-chip-row">${[meta.badge, ...(meta.tags || []).slice(0, 2)].filter(Boolean).map(tag => `<span class="neo-guide-chip">${escapeHtml(tag)}</span>`).join('')}</div>`;
    const content = summary.querySelector(':scope > div');
    (content || summary).appendChild(actionWrap);
    const button = actionWrap.querySelector('.neo-guide-button');
    const titleText = block.querySelector('.accordion-title')?.textContent || titleKey;
    button?.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      openGuideModal(titleText, meta, button);
    });
  }

  function injectGuideIntoCard(card, titleKey, meta) {
    const header = card.querySelector(':scope > .row-between');
    if (!header || header.querySelector('.neo-guide-button')) return;
    const wrap = document.createElement('div');
    wrap.className = 'neo-guide-actions neo-guide-actions-card';
    wrap.innerHTML = `
      <div class="neo-guide-chip-row">${[meta.badge, ...(meta.tags || []).slice(0, 2)].filter(Boolean).map(tag => `<span class="neo-guide-chip">${escapeHtml(tag)}</span>`).join('')}</div>
      <button class="btn btn-small neo-guide-button" type="button">? Guide</button>`;
    header.appendChild(wrap);
    const button = wrap.querySelector('.neo-guide-button');
    const titleText = card.querySelector('.accordion-title')?.textContent || titleKey;
    button?.addEventListener('click', event => {
      event.preventDefault();
      openGuideModal(titleText, meta, button);
    });
  }

  function injectGuides() {
    document.querySelectorAll(`${ROOT_SELECTOR} details.accordion-block`).forEach(block => {
      const titleKey = normalizeTitle(block.querySelector('.accordion-title')?.textContent || '');
      const meta = sectionGuides[titleKey];
      if (meta) injectGuideIntoAccordion(block, titleKey, meta);
    });
    document.querySelectorAll(`${ROOT_SELECTOR} .generation-shell-card`).forEach(card => {
      const titleKey = normalizeTitle(card.querySelector('.accordion-title')?.textContent || '');
      const meta = sectionGuides[titleKey];
      if (meta) injectGuideIntoCard(card, titleKey, meta);
    });
  }

  function renderSelectHelpTooltip(button, select, resolver, titleText) {
    const options = Array.from(select?.options || []).filter(opt => !opt.disabled && String(opt.value || '').trim() !== '');
    const seen = new Set();
    const items = [];
    options.forEach(opt => {
      const key = `${opt.value}::${String(opt.textContent || '').trim()}`;
      if (seen.has(key)) return;
      seen.add(key);
      const helpText = String(resolver(opt.value, select) || '').trim();
      if (!helpText) return;
      items.push({
        label: String(opt.textContent || opt.value || 'Option').trim(),
        text: helpText,
        active: String(opt.value) === String(select?.value || '')
      });
    });
    if (!items.length) {
      items.push({
        label: String(select?.selectedOptions?.[0]?.textContent || select?.value || 'Current option').trim(),
        text: String(resolver(select?.value, select) || 'This option changes how this part of the workflow behaves.').trim(),
        active: true
      });
    }
    renderHelpItems(button, titleText || 'Option guide', items);
  }

  function bindSelectExplainer(select, resolver) {
    if (!select || select.dataset.neoExplainerBound === '1') return;
    const label = resolveFieldLabel(select);
    if (!label) return;
    const oldExplainer = select.parentElement?.querySelector(':scope > .neo-inline-explainer');
    if (oldExplainer) oldExplainer.remove();
    if (label.querySelector('.neo-field-help-button')) {
      const existing = label.querySelector('.neo-field-help-button');
      renderSelectHelpTooltip(existing, select, resolver);
      select.dataset.neoExplainerBound = '1';
      return;
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'neo-field-help-button';
    const labelText = label.textContent.trim();
    button.setAttribute('aria-label', `Show help for ${labelText}`);
    button.innerHTML = '<span class="neo-field-help-icon" aria-hidden="true">?</span><span class="neo-field-help-popover" role="tooltip"><span class="neo-field-help-popover-title">Option guide</span><span class="neo-field-help-list"></span></span>';
    const updatePlacement = () => {
      const popover = button.querySelector('.neo-field-help-popover');
      if (!popover) return;
      const buttonRect = button.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      const width = Math.min(popoverRect.width || 340, window.innerWidth - 24);
      const height = popoverRect.height || 180;
      const x = Math.max(12, Math.min(buttonRect.left, window.innerWidth - width - 12));
      let y = buttonRect.bottom + 8;
      if (y + height > window.innerHeight - 12 && buttonRect.top - height - 8 > 12) y = buttonRect.top - height - 8;
      y = Math.max(12, Math.min(y, window.innerHeight - height - 12));
      popover.style.left = `${x}px`;
      popover.style.top = `${y}px`;
      popover.style.right = 'auto';
      popover.style.bottom = 'auto';
    };
    const show = () => {
      renderSelectHelpTooltip(button, select, resolver, labelText);
      button.classList.add('is-open');
      window.requestAnimationFrame(updatePlacement);
    };
    const hide = () => button.classList.remove('is-open');
    button.addEventListener('mouseenter', show);
    button.addEventListener('focus', show);
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if (button.classList.contains('is-open')) hide();
      else show();
    });
    button.addEventListener('mouseleave', hide);
    button.addEventListener('blur', hide);
    const update = () => { renderSelectHelpTooltip(button, select, resolver, labelText); if (button.classList.contains('is-open')) window.requestAnimationFrame(updatePlacement); };
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    label.appendChild(button);
    select.addEventListener('change', update);
    select.addEventListener('input', update);
    const observer = new MutationObserver(update);
    observer.observe(select, { childList: true, subtree: true, attributes: true });
    select.dataset.neoExplainerBound = '1';
    update();
  }

  function bindStaticFieldHelper(field, meta) {
    if (!field || field.dataset.neoStaticHelpBound === '1') return;
    const label = resolveFieldLabel(field);
    if (!label || label.querySelector('.neo-field-help-button')) return;
    const labelText = label.textContent.trim();
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'neo-field-help-button';
    button.setAttribute('aria-label', `Show help for ${labelText}`);
    button.innerHTML = '<span class="neo-field-help-icon" aria-hidden="true">?</span><span class="neo-field-help-popover" role="tooltip"><span class="neo-field-help-popover-title">Field guide</span><span class="neo-field-help-list"></span></span>';
    const updatePlacement = () => {
      const popover = button.querySelector('.neo-field-help-popover');
      if (!popover) return;
      const buttonRect = button.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      const width = Math.min(popoverRect.width || 340, window.innerWidth - 24);
      const height = popoverRect.height || 180;
      const x = Math.max(12, Math.min(buttonRect.left, window.innerWidth - width - 12));
      let y = buttonRect.bottom + 8;
      if (y + height > window.innerHeight - 12 && buttonRect.top - height - 8 > 12) y = buttonRect.top - height - 8;
      y = Math.max(12, Math.min(y, window.innerHeight - height - 12));
      popover.style.left = `${x}px`;
      popover.style.top = `${y}px`;
      popover.style.right = 'auto';
      popover.style.bottom = 'auto';
    };
    const update = () => { renderHelpItems(button, meta.title || labelText, meta.items || []); if (button.classList.contains('is-open')) window.requestAnimationFrame(updatePlacement); };
    const show = () => { update(); button.classList.add('is-open'); window.requestAnimationFrame(updatePlacement); };
    const hide = () => button.classList.remove('is-open');
    button.addEventListener('mouseenter', show);
    button.addEventListener('focus', show);
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if (button.classList.contains('is-open')) hide();
      else show();
    });
    button.addEventListener('mouseleave', hide);
    button.addEventListener('blur', hide);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    label.appendChild(button);
    field.dataset.neoStaticHelpBound = '1';
    update();
  }

  function refreshStaticFieldHelpers() {
    staticFieldHelpers.forEach(meta => {
      document.querySelectorAll(meta.selector).forEach(field => bindStaticFieldHelper(field, meta));
    });
  }

  function refreshSelectExplainers() {
    optionExplainers.forEach(rule => {
      document.querySelectorAll(rule.selector).forEach(select => bindSelectExplainer(select, rule.resolve));
    });
    refreshStaticFieldHelpers();
  }

  function samplerHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key) return 'Chooses the denoising sampler used during generation.';
    if (key.includes('euler')) return 'Fast and direct. Good for quick testing and many normal generations.';
    if (key.includes('dpmpp') || key.includes('dpm++')) return 'Usually smoother and more stable for higher-quality work. Great default family for many checkpoints.';
    if (key.includes('heun')) return 'Can preserve structure well but is often slower than basic quick-test samplers.';
    if (key.includes('uni_pc') || key.includes('unipc')) return 'A modern sampler family often used for balanced quality and speed.';
    if (key.includes('lcm')) return 'Made for very fast low-step workflows, not normal high-step generation.';
    return 'Sampler choice changes the denoising behavior, texture feel, and sometimes speed.';
  }

  function schedulerHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key) return 'Controls how noise is distributed across the denoising steps.';
    if (key.includes('normal')) return 'Standard schedule. Safest default when you are unsure.';
    if (key.includes('karras')) return 'Popular quality-focused schedule for many sampler setups.';
    if (key.includes('exponential')) return 'Can feel more aggressive in how the noise schedule falls off.';
    if (key.includes('sgm')) return 'Often used for models or workflows tuned around SGM-style schedules.';
    if (key.includes('simple')) return 'A simpler schedule that can work for testing but is not always the best-quality choice.';
    return 'Scheduler choice changes how the same sampler behaves across the full step range.';
  }

  function controlnetPreprocessorHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key || key === 'none') return 'No preprocessing. Use this when the model expects a ready-made control image or a direct union-style workflow.';
    if (key.includes('canny')) return 'Extracts strong edges. Great for keeping major shapes and outlines.';
    if (key.includes('softedge') || key.includes('hed')) return 'Extracts softer edges than canny. Better when you want structure without harsh line control.';
    if (key.includes('lineart')) return 'Builds a line-art style control map. Good for drawings, stylized structure, or cleaner outlines.';
    if (key.includes('scribble')) return 'Creates a scribble-like control map. Useful for loose composition guidance.';
    if (key.includes('openpose') || key.includes('pose')) return 'Extracts pose landmarks. Best for body pose and character placement.';
    if (key.includes('depth')) return 'Uses depth structure to guide near/far layout and spatial consistency.';
    if (key.includes('normal')) return 'Uses normal-map style surface guidance. Good for shape and surface direction cues.';
    if (key.includes('tile')) return 'Tile-style control is useful for detail reinforcement and upscale workflows.';
    if (key.includes('shuffle')) return 'Shuffle-based preprocessors give looser style/texture guidance rather than precise structure.';
    if (key.includes('seg')) return 'Segmentation-based control maps separate regions by class for coarse scene structure.';
    if (key.includes('mlsd')) return 'Line segment detection is useful for architecture or straight-edge scenes.';
    return 'This preprocessor converts your control image into the kind of map the ControlNet model expects.';
  }

  function ipAdapterCombineHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key || key === 'concat') return 'Concat keeps multiple references more distinct instead of flattening them into one blend. Best default for most multi-reference runs.';
    if (key === 'add') return 'Add blends references together more aggressively. Useful for stronger fusion, but it can overpower fast.';
    if (key === 'subtract') return 'Subtract uses one reference against the others. More experimental than normal-purpose reference mixing.';
    if (key === 'average') return 'Average blends references evenly into one shared embedding. Good when you want a softer mixed identity.';
    if (key.includes('norm')) return 'Normalized average evens out the references first so one image is less likely to dominate.';
    return 'Controls how multiple reference embeddings are mixed together before IP-Adapter uses them.';
  }

  function ipAdapterWeightHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key || key === 'linear') return 'Linear is the plain predictable weighting mode. Best default unless you have a reason to experiment.';
    if (key.includes('ease') || key.includes('soft')) return 'This weighting mode changes how strongly the reference pushes during denoising, usually with a gentler curve.';
    if (key.includes('strong')) return 'This tends to push the reference harder. Good only when you deliberately want stronger influence.';
    return 'Weight type changes how the reference influence is distributed across the denoising process.';
  }

  function ipAdapterEmbedHelp(value) {
    const key = String(value || '').trim().toLowerCase();
    if (!key || key === 'v only') return 'Uses the visual embedding path only. Good default for many reference-image workflows.';
    if (key.includes('k+v') || key.includes('kv')) return 'Uses more embedding channels for stronger reference influence, but can be heavier or more opinionated.';
    if (key.includes('mean')) return 'Averages or stabilizes multiple embeddings for a smoother combined reference effect.';
    return 'Embed scaling changes how the reference-image information is mixed into the IP-Adapter guidance.';
  }

  function initMutationRefresh() {
    const root = document.querySelector(ROOT_SELECTOR);
    if (!root) return;
    const observer = new MutationObserver(() => {
      refreshSelectExplainers();
      annotateSectionLevels();
    });
    observer.observe(root, { childList: true, subtree: true });
  }

  function init() {
    loadState();
    injectFoundationBar();
    injectGuides();
    refreshSelectExplainers();
    annotateSectionLevels();
    applyHelpMode();
    applyViewMode();
    initMutationRefresh();
    window.NeoGenerationUX = {
      state,
      setViewMode,
      setHelpMode,
      refreshSelectExplainers,
    };
  }

  ready(init);
})();
