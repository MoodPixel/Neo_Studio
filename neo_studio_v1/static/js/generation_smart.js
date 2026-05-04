(function () {
  const ROOT_SELECTOR = '#tab-generate';

  const familyProfiles = {
    sdxl: {
      key: 'sdxl',
      label: 'SDXL family',
      size: { width: 1024, height: 1024 },
      portrait: { width: 1024, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      steps: 28,
      cfg: 5.5,
      note: 'Strong default for modern XL checkpoints. Likes 1024-ish generation and moderate CFG.'
    },
    pony: {
      key: 'pony',
      label: 'Pony / Illustrious family',
      size: { width: 1024, height: 1024 },
      portrait: { width: 1024, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      steps: 28,
      cfg: 5.0,
      note: 'Treat this like an XL workflow first: moderate CFG, 1024-ish canvas, then tune style with add-ons.'
    },
    sd15: {
      key: 'sd15',
      label: 'SD 1.5 family',
      size: { width: 768, height: 768 },
      portrait: { width: 768, height: 1152 },
      landscape: { width: 1152, height: 768 },
      steps: 26,
      cfg: 7.0,
      note: 'Usually happier on smaller first-pass sizes than XL models. Great when paired with the right LoRAs.'
    },
    flux: {
      key: 'flux',
      label: 'Flux family',
      size: { width: 1024, height: 1024 },
      portrait: { width: 1024, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      steps: 24,
      cfg: 3.5,
      note: 'Flux-style setups usually prefer lower CFG than SDXL or 1.5-style checkpoints.'
    },
    sd3: {
      key: 'sd3',
      label: 'SD3 family',
      size: { width: 1024, height: 1024 },
      portrait: { width: 1024, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      steps: 28,
      cfg: 4.5,
      note: 'Use moderate CFG and keep the first pass clean before layering extra systems.'
    },
    unknown: {
      key: 'unknown',
      label: 'Unknown / custom family',
      size: { width: 1024, height: 1024 },
      portrait: { width: 1024, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      steps: 28,
      cfg: 6.0,
      note: 'No strong family detection yet. Start conservative and test the checkpoint before stacking extras.'
    }
  };

  const recipeDefinitions = [
    {
      id: 'portrait_clean',
      title: 'Portrait clean',
      summary: 'Quick portrait-friendly starter with sane defaults and heavy extras off.',
      mode: 'quick',
      apply: () => {
        const profile = currentProfile();
        setMode('txt2img');
        applyDimensions(profile.portrait.width, profile.portrait.height);
        setNumber('generation-steps', profile.steps);
        setNumber('generation-cfg', profile.cfg);
        setSelectValue('generation-refine-enabled', 'false');
        setSelectValue('generation-supir-enabled', 'false');
        setCheckbox('generation-ipadapter-enabled', false);
        setCheckbox('generation-controlnet-enabled', false);
        setStatusNote('Portrait clean loaded. Start with a strong prompt, then add one style or character block only if needed.', 'success');
      }
    },
    {
      id: 'character_consistency',
      title: 'Character consistency',
      summary: 'Pushes Neo toward repeatable character flow with Character Creator and optional reference guidance.',
      mode: 'advanced',
      apply: () => {
        const profile = currentProfile();
        setMode('txt2img');
        applyDimensions(profile.portrait.width, profile.portrait.height);
        setNumber('generation-steps', profile.steps);
        setNumber('generation-cfg', profile.cfg);
        openSection('character creator');
        openSection('style add-ons');
        openSection('advanced reference controls');
        const hasRef = hasFiles('generation-ipadapter-image');
        setCheckbox('generation-ipadapter-enabled', hasRef);
        setStatusNote(hasRef
          ? 'Character consistency loaded. Character Builder + Style Stack are ready, and IP-Adapter was enabled because a reference image already exists.'
          : 'Character consistency loaded. Build the character block first, then add a reference image in IP-Adapter only if you need stronger identity locking.', 'success');
      }
    },
    {
      id: 'stylized_anime',
      title: 'Stylized anime',
      summary: 'Opens the creative style path instead of the repair path.',
      mode: 'advanced',
      apply: () => {
        const profile = currentProfile();
        setMode('txt2img');
        applyDimensions(profile.size.width, profile.size.height);
        setNumber('generation-steps', profile.steps);
        setNumber('generation-cfg', profile.key === 'sd15' ? 7.0 : 5.0);
        setSelectValue('generation-refine-enabled', 'false');
        setSelectValue('generation-supir-enabled', 'false');
        openSection('style add-ons');
        openSection('lora settings');
        setStatusNote('Stylized anime loaded. Start with style stacks or one compatible LoRA before adding structural tools.', 'success');
      }
    },
    {
      id: 'product_promo',
      title: 'Product / promo',
      summary: 'Cleaner commercial starting point with landscape framing and fewer chaotic extras.',
      mode: 'advanced',
      apply: () => {
        const profile = currentProfile();
        setMode(hasFiles('generation-source-image') ? 'img2img' : 'txt2img');
        applyDimensions(profile.landscape.width, profile.landscape.height);
        setNumber('generation-steps', Math.max(20, profile.steps - 2));
        setNumber('generation-cfg', profile.key === 'flux' ? 3.5 : 5.5);
        setSelectValue('generation-refine-enabled', 'false');
        setCheckbox('generation-controlnet-enabled', false);
        openSection('style add-ons');
        setStatusNote('Product / promo loaded. Keep the prompt clean, use fewer style layers, and only bring in ControlNet if framing really needs it.', 'success');
      }
    },
    {
      id: 'inpaint_repair',
      title: 'Inpaint repair',
      summary: 'Routes the workspace into mask-led local repair with focused defaults.',
      mode: 'advanced',
      apply: () => {
        setMode('inpaint');
        setNumber('generation-denoise', 0.55);
        setNumber('generation-grow-mask-by', 6);
        setNumber('generation-mask-feather', 2);
        openSection('advanced raw mask override', false);
        setStatusNote(hasFiles('generation-source-image')
          ? 'Inpaint repair loaded. Use Edit Mask now, then keep the prompt focused on just the repaired change.'
          : 'Inpaint repair loaded, but you still need a source image before it becomes usable.', 'warn');
      }
    },
    {
      id: 'outpaint_expand',
      title: 'Outpaint expand',
      summary: 'Moves into canvas expansion with seam-friendly defaults.',
      mode: 'advanced',
      apply: () => {
        setMode('outpaint');
        setNumber('generation-outpaint-feather', 24);
        openMaskPanel();
        setStatusNote(hasFiles('generation-source-image')
          ? 'Outpaint expand loaded. Pick a target preset or fill the padding manually before queue.'
          : 'Outpaint expand loaded, but you still need a source image before padding matters.', 'warn');
      }
    },
    {
      id: 'hires_polish',
      title: 'Hires polish',
      summary: 'Turns on the lighter upscale path, not the heaviest cleanup stack.',
      mode: 'advanced',
      apply: () => {
        setSelectValue('generation-refine-enabled', 'true');
        setSelectValue('generation-refine-mode', 'latent');
        setNumber('generation-refine-scale', 1.5);
        setNumber('generation-refine-denoise', 0.3);
        setSelectValue('generation-supir-enabled', 'false');
        openSection('upscale lab');
        setStatusNote('Hires polish loaded. Use this after the base image already feels right.', 'success');
      }
    },
    {
      id: 'reference_faceid',
      title: 'Reference-led FaceID',
      summary: 'Preps the workspace for reference-image identity guidance when you actually have a reference ready.',
      mode: 'advanced',
      apply: () => {
        openSection('advanced reference controls');
        setCheckbox('generation-ipadapter-enabled', hasFiles('generation-ipadapter-image'));
        setSelectValue('generation-ipadapter-mode', 'faceid');
        setStatusNote(hasFiles('generation-ipadapter-image')
          ? 'Reference-led FaceID loaded. Check the model, CLIP Vision, and provider before queue.'
          : 'Reference-led FaceID loaded. Add a clean face reference image first, otherwise keep IP-Adapter off for now.', 'warn');
      }
    }
  ];

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) { return document.getElementById(id); }

  function runtime() { return window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null; }

  function currentCheckpoint() { return String($('generation-checkpoint')?.value || '').trim(); }

  function detectModelFamily(name) {
    const key = String(name || '').trim().toLowerCase();
    if (!key) return familyProfiles.unknown;
    if (key.includes('pony') || key.includes('illustrious')) return familyProfiles.pony;
    if (key.includes('flux')) return familyProfiles.flux;
    if (key.includes('sd3') || key.includes('stable-diffusion-3') || key.includes('stable diffusion 3')) return familyProfiles.sd3;
    if (key.includes('sdxl') || key.includes('xl') || key.includes('juggernautxl') || key.includes('realvisxl') || key.includes('albedo xl')) return familyProfiles.sdxl;
    if (key.includes('1.5') || key.includes('sd15') || key.includes('v1-5') || key.includes('anything') || key.includes('dreamshaper') || key.includes('revanimated') || key.includes('deliberate')) return familyProfiles.sd15;
    return familyProfiles.unknown;
  }

  function currentProfile() {
    return detectModelFamily(currentCheckpoint());
  }

  function hasFiles(id) {
    return !!($(id)?.files && $(id).files.length);
  }

  function createSmartPanel() {
    const warningPanel = $('generation-ux-warning-panel');
    const foundation = $('generation-ux-foundation-bar');
    const anchor = warningPanel || foundation;
    if (!anchor || $('generation-smart-panel')) return;
    anchor.insertAdjacentHTML('afterend', `
      <div class="neo-smart-panel" id="generation-smart-panel">
        <div class="neo-smart-grid">
          <div class="neo-smart-card" id="generation-model-intel-card">
            <div class="neo-smart-card-header">
              <div>
                <div class="neo-smart-title">Model intelligence</div>
                <div class="neo-smart-subtitle">Neo reads the selected checkpoint name, detects a likely model family, and suggests safer starter settings.</div>
              </div>
              <div class="neo-smart-actions">
                <button class="btn btn-small" id="btn-generation-apply-model-size" type="button">Use recommended size</button>
                <button class="btn btn-small" id="btn-generation-apply-model-defaults" type="button">Apply starter defaults</button>
              </div>
            </div>
            <div id="generation-model-intel-body" class="neo-smart-card-body"></div>
          </div>
          <div class="neo-smart-card" id="generation-recipes-card">
            <div class="neo-smart-card-header">
              <div>
                <div class="neo-smart-title">Creative recipes</div>
                <div class="neo-smart-subtitle">One-click guided starting points for real workflows, not raw parameter soup.</div>
              </div>
            </div>
            <div id="generation-recipe-list" class="neo-recipe-grid"></div>
            <div id="generation-recipe-note" class="neo-recipe-note">Pick a recipe to push Neo toward a smarter starting layout.</div>
          </div>
        </div>
      </div>`);
    $('btn-generation-apply-model-size')?.addEventListener('click', applyRecommendedSize);
    $('btn-generation-apply-model-defaults')?.addEventListener('click', applyStarterDefaults);
  }

  function renderRecipes() {
    const host = $('generation-recipe-list');
    if (!host) return;
    host.innerHTML = recipeDefinitions.map(recipe => `
      <button class="neo-recipe-card" type="button" data-recipe-id="${recipe.id}">
        <span class="neo-recipe-title">${escapeHtml(recipe.title)}</span>
        <span class="neo-recipe-summary">${escapeHtml(recipe.summary)}</span>
      </button>`).join('');
    host.querySelectorAll('[data-recipe-id]').forEach(btn => {
      btn.addEventListener('click', () => applyRecipe(btn.dataset.recipeId || ''));
    });
  }

  function collectActiveLoras() {
    return Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-name')).map(el => String(el.value || '').trim()).filter(Boolean);
  }

  function modelIntelWarnings(profile) {
    const warnings = [];
    const width = Number($('generation-width')?.value || 0);
    const height = Number($('generation-height')?.value || 0);
    const loras = collectActiveLoras();
    const familyGroup = profile.key === 'pony' ? 'sdxl' : profile.key;
    if ((profile.key === 'sdxl' || profile.key === 'pony' || profile.key === 'flux' || profile.key === 'sd3') && (width < 768 || height < 768)) {
      warnings.push('Current canvas is unusually small for this model family. Start closer to a 1024-ish short side unless you know the checkpoint likes smaller sizes.');
    }
    if (profile.key === 'sd15' && (width > 1024 || height > 1024)) {
      warnings.push('Current canvas is quite large for a first SD 1.5 pass. A smaller first render plus hires often behaves better.');
    }
    loras.forEach(name => {
      const loraProfile = detectModelFamily(name);
      const loraGroup = loraProfile.key === 'pony' ? 'sdxl' : loraProfile.key;
      if (loraGroup !== 'unknown' && familyGroup !== 'unknown' && loraGroup !== familyGroup) {
        warnings.push(`LoRA mismatch warning: “${name}” looks more like ${loraProfile.label}, but the checkpoint looks like ${profile.label}.`);
      }
    });
    return warnings;
  }

  function renderModelIntel() {
    const host = $('generation-model-intel-body');
    if (!host) return;
    const checkpoint = currentCheckpoint();
    if (!checkpoint) {
      host.innerHTML = '<div class="neo-smart-empty">Pick a checkpoint first. Neo will then suggest a family, starter size, and safer defaults.</div>';
      return;
    }
    const profile = currentProfile();
    const warnings = modelIntelWarnings(profile);
    host.innerHTML = `
      <div class="neo-model-intel-top">
        <span class="neo-family-chip family-${profile.key}">${escapeHtml(profile.label)}</span>
        <div class="neo-model-name">${escapeHtml(checkpoint)}</div>
      </div>
      <div class="neo-model-intel-grid">
        <div class="neo-model-intel-block">
          <div class="neo-model-intel-label">Starter size</div>
          <div class="neo-model-intel-value">${profile.size.width} × ${profile.size.height}</div>
        </div>
        <div class="neo-model-intel-block">
          <div class="neo-model-intel-label">Starter steps</div>
          <div class="neo-model-intel-value">${profile.steps}</div>
        </div>
        <div class="neo-model-intel-block">
          <div class="neo-model-intel-label">Starter CFG</div>
          <div class="neo-model-intel-value">${profile.cfg}</div>
        </div>
        <div class="neo-model-intel-block">
          <div class="neo-model-intel-label">Good portrait size</div>
          <div class="neo-model-intel-value">${profile.portrait.width} × ${profile.portrait.height}</div>
        </div>
      </div>
      <div class="neo-model-intel-note">${escapeHtml(profile.note)}</div>
      ${warnings.length ? `<div class="neo-model-warning-list">${warnings.map(item => `<div class="neo-model-warning">${escapeHtml(item)}</div>`).join('')}</div>` : '<div class="neo-model-ok">No obvious family or size mismatch detected right now.</div>'}`;
  }

  function dispatchField(el, kind='change') {
    if (!el) return;
    el.dispatchEvent(new Event(kind, { bubbles: true }));
  }

  function setSelectValue(id, value) {
    const el = $(id);
    if (!el) return;
    el.value = String(value);
    dispatchField(el, 'change');
  }

  function setNumber(id, value) {
    const el = $(id);
    if (!el) return;
    el.value = String(value);
    dispatchField(el, 'input');
    dispatchField(el, 'change');
    const range = $(`${id}-range`);
    if (range) {
      range.value = String(value);
      dispatchField(range, 'input');
      dispatchField(range, 'change');
    }
  }

  function setCheckbox(id, checked) {
    const el = $(id);
    if (!el) return;
    el.checked = !!checked;
    dispatchField(el, 'change');
  }

  function setMode(mode) {
    const select = $('generation-workflow-type');
    if (!select) return;
    select.value = mode;
    dispatchField(select, 'change');
  }

  function applyDimensions(width, height) {
    const preset = $('generation-size-preset');
    if (preset) {
      const match = Array.from(preset.options).find(opt => String(opt.value || '') === `${width}x${height}`);
      if (match) {
        preset.value = match.value;
        dispatchField(preset, 'change');
        return;
      }
    }
    setNumber('generation-width', width);
    setNumber('generation-height', height);
  }

  function openSection(title, forceOpen=true) {
    const match = Array.from(document.querySelectorAll(`${ROOT_SELECTOR} details.accordion-block`)).find(block => normalizeTitle(block.querySelector('.accordion-title')?.textContent || '') === normalizeTitle(title));
    if (match && forceOpen !== false) {
      match.open = true;
      match.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function openMaskPanel() {
    document.getElementById('generation-mask-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function setStatusNote(message, tone='info') {
    const note = $('generation-recipe-note');
    if (note) {
      note.textContent = message;
      note.className = `neo-recipe-note tone-${tone}`;
    }
    const status = $('generation-status');
    if (status) {
      status.textContent = message;
      status.className = tone === 'success' ? 'status success' : tone === 'warn' ? 'status warn' : tone === 'error' ? 'status error' : 'status';
    }
  }

  function applyRecommendedSize() {
    const profile = currentProfile();
    applyDimensions(profile.size.width, profile.size.height);
    setStatusNote(`Recommended size applied for ${profile.label}.`, 'success');
  }

  function applyStarterDefaults() {
    const profile = currentProfile();
    applyDimensions(profile.size.width, profile.size.height);
    setNumber('generation-steps', profile.steps);
    setNumber('generation-cfg', profile.cfg);
    setStatusNote(`Starter defaults applied for ${profile.label}.`, 'success');
  }

  function applyRecipe(id) {
    const recipe = recipeDefinitions.find(item => item.id === id);
    if (!recipe) return;
    if (window.NeoGenerationUX?.setViewMode) window.NeoGenerationUX.setViewMode(recipe.mode || 'advanced');
    recipe.apply();
  }

  function normalizeTitle(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function bindRefreshes() {
    const ids = ['generation-checkpoint','generation-width','generation-height','generation-steps','generation-cfg'];
    ids.forEach(id => {
      const el = $(id);
      if (!el || el.dataset.neoSmartBound === '1') return;
      const refresh = () => renderModelIntel();
      el.addEventListener('change', refresh);
      el.addEventListener('input', refresh);
      el.dataset.neoSmartBound = '1';
    });
    document.addEventListener('change', event => {
      if (event.target && event.target.closest('#generation-lora-extra-list')) renderModelIntel();
    });
  }

  function init() {
    createSmartPanel();
    renderRecipes();
    renderModelIntel();
    bindRefreshes();
    window.addEventListener('neo:generation-catalog-refreshed', renderModelIntel);
  }

  ready(init);
})();
