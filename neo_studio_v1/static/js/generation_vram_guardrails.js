(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const FALLBACK_COST_BY_SECTION = {
    'generation-hires-settings': 'medium',
    'generation-supir-settings': 'heavy',
    'generation-detailer-settings': 'medium',
    'generation-controlnet-settings': 'medium',
    'generation-ipadapter-settings': 'medium',
    'generation-lora-settings': 'medium',
    'generation-ti-settings': 'light',
    'generation-inpaint-controls': 'light',
    'generation-outpaint-controls': 'medium',
    'generation-mask-raw-upload': 'expert',
    'generation-tagassist': 'light',
    'generation-character-creator': 'light',
    'generation-keyword-insert': 'light',
    'generation-style-addons': 'light',
    'generation-wildcards': 'light'
  };

  const RECIPE_MAP = {
    portrait_lite: {
      label: 'Portrait Lite',
      goal: 'create_from_scratch',
      setupTab: 'prompt',
      mode: 'txt2img',
      width: 768,
      height: 1024,
      steps: 24,
      cfg: 6.0,
      denoise: null,
      refineEnabled: 'false',
      supirEnabled: 'false',
      detailerEnabled: false,
      controlnetEnabled: false,
      ipadapterEnabled: false,
      note: 'Fresh low-VRAM portrait starting point.'
    },
    reference_lite: {
      label: 'IP-Adapter Identity Presets',
      goal: 'match_reference',
      setupTab: 'guide',
      mode: '',
      width: 768,
      height: 1024,
      steps: 22,
      cfg: 5.5,
      denoise: 0.45,
      refineEnabled: 'false',
      supirEnabled: 'false',
      detailerEnabled: false,
      controlnetEnabled: false,
      ipadapterEnabled: true,
      note: 'Reference-led setup without stacking heavy extras immediately.'
    },
    cleanup_lite: {
      label: 'Cleanup Lite',
      goal: 'remove_object_or_background',
      setupTab: 'guide',
      mode: 'inpaint',
      width: 768,
      height: 1024,
      steps: 20,
      cfg: 5.5,
      denoise: 0.55,
      refineEnabled: 'false',
      supirEnabled: 'false',
      detailerEnabled: false,
      controlnetEnabled: false,
      ipadapterEnabled: false,
      note: 'Removal / cleanup path with the heavy finish stack kept off.'
    },
    finish_lite: {
      label: 'Finish Lite',
      goal: 'finalize_and_upscale',
      setupTab: 'enhance',
      mode: '',
      width: null,
      height: null,
      steps: null,
      cfg: null,
      denoise: null,
      refineEnabled: 'true',
      refineMode: 'latent',
      refineScale: 1.5,
      supirEnabled: 'false',
      detailerEnabled: false,
      controlnetEnabled: false,
      ipadapterEnabled: false,
      note: 'Late-stage polish without turning on SUPIR.'
    }
  };

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function root() {
    return document.querySelector(ROOT_SELECTOR);
  }

  function lowVramEnabled() {
    return !!$('backend-low-vram-toggle')?.checked;
  }

  function accordion(id) {
    return document.querySelector(`${ROOT_SELECTOR} [data-accordion-id="${id}"]`);
  }

  function getCostMap() {
    const registry = Array.isArray(window.NeoGenerationSectionRegistry) ? window.NeoGenerationSectionRegistry : [];
    if (!registry.length) return FALLBACK_COST_BY_SECTION;
    const derived = {};
    registry.forEach(spec => {
      if (spec?.id && spec?.cost_level) derived[spec.id] = spec.cost_level;
    });
    return Object.keys(derived).length ? derived : FALLBACK_COST_BY_SECTION;
  }

  function ensureCostBadges() {
    Object.entries(getCostMap()).forEach(([id, cost]) => {
      const node = accordion(id);
      const summary = node?.querySelector(':scope > summary');
      const titleBlock = summary?.querySelector(':scope > div');
      if (!summary || !titleBlock) return;
      let rail = summary.querySelector('.generation-cost-badge-rail');
      if (!rail) {
        rail = document.createElement('div');
        rail.className = 'generation-cost-badge-rail';
        titleBlock.appendChild(rail);
      }
      let badge = rail.querySelector('.generation-cost-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'generation-cost-badge';
        rail.appendChild(badge);
      }
      badge.className = `generation-cost-badge is-${String(cost).toLowerCase()}`;
      badge.textContent = cost === 'expert' ? 'Manual' : cost.charAt(0).toUpperCase() + cost.slice(1);
      badge.title = `${badge.textContent} VRAM cost`;
    });
  }

  function ensureGuardrailsPanel() {
    const panelRoot = root();
    const anchor = $('generation-setup-guardrails-anchor');
    if (!panelRoot || !anchor) return null;
    const host = anchor;
    let panel = $('generation-vram-guardrails');
    let created = false;
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'generation-vram-guardrails';
      panel.className = 'panel generation-vram-guardrails';
      panel.innerHTML = `
        <div class="generation-vram-head row-between">
          <div>
            <h3 style="margin:0;">Low VRAM guardrails</h3>
            <div class="muted small" id="generation-vram-copy">Keep sizes, finish tools, and stacked helpers inside a safer range when you want lighter local runs.</div>
          </div>
          <div class="generation-vram-status-wrap">
            <span class="generation-cost-badge is-light" id="generation-vram-risk-badge">Light</span>
            <span class="badge" id="generation-vram-mode-badge">Low VRAM mode: Off</span>
          </div>
        </div>
        <div class="generation-vram-summary" id="generation-vram-summary"></div>
        <div class="generation-vram-actions" id="generation-vram-actions"></div>
        <div class="generation-vram-recipes" id="generation-vram-recipes"></div>`;
      created = true;
    }
    if (panel.parentElement !== anchor) anchor.appendChild(panel);
    panel.dataset.generationShellRegion = 'top-shell';
    if (created) document.dispatchEvent(new CustomEvent('neo-generation-vram-panel-mounted'));
    return panel;
  }

  function renderRecipeButtons() {
    const host = $('generation-vram-recipes');
    if (!host) return;
    host.innerHTML = '';
    Object.entries(RECIPE_MAP).forEach(([key, recipe]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-small generation-vram-recipe-btn';
      button.textContent = recipe.label;
      button.title = recipe.note || recipe.label;
      button.addEventListener('click', event => {
        event.preventDefault();
        applyRecipe(key);
      });
      host.appendChild(button);
    });
  }

  function setValue(id, value, eventNames = ['input', 'change']) {
    const node = $(id);
    if (!node || value === undefined || value === null || value === '') return;
    node.value = String(value);
    eventNames.forEach(name => node.dispatchEvent(new Event(name, { bubbles: true })));
  }

  function setCheckbox(id, enabled) {
    const node = $(id);
    if (!node || typeof enabled !== 'boolean') return;
    node.checked = enabled;
    node.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function clickIfPresent(selector) {
    const node = document.querySelector(selector);
    if (node) node.click();
  }

  function setModeBadgeTone(node, riskLabel) {
    if (!node) return;
    node.classList.remove('is-light', 'is-medium', 'is-heavy');
    node.classList.add(`is-${riskLabel.toLowerCase()}`);
  }

  function applyRecipe(key) {
    const recipe = RECIPE_MAP[key];
    if (!recipe) return;
    if (recipe.goal) clickIfPresent(`[data-generation-goal="${recipe.goal}"]`);
    if (recipe.setupTab) clickIfPresent(`[data-generation-setup-tab="${recipe.setupTab}"]`);
    if (recipe.mode) clickIfPresent(`[data-generation-mode="${recipe.mode}"]`);

    setValue('generation-width', recipe.width);
    setValue('generation-height', recipe.height);
    setValue('generation-steps', recipe.steps);
    setValue('generation-cfg', recipe.cfg);
    setValue('generation-denoise', recipe.denoise);
    setValue('generation-refine-enabled', recipe.refineEnabled);
    setValue('generation-refine-mode', recipe.refineMode);
    setValue('generation-refine-scale', recipe.refineScale);
    setValue('generation-supir-enabled', recipe.supirEnabled);
    setCheckbox('generation-detailer-enabled', recipe.detailerEnabled);
    setCheckbox('generation-controlnet-enabled', recipe.controlnetEnabled);
    setCheckbox('generation-ipadapter-enabled', recipe.ipadapterEnabled);

    updateGuardrails();
    const status = $('generation-status');
    if (status) {
      status.textContent = `${recipe.label} applied. ${recipe.note || ''}`.trim();
      status.className = 'status success';
    }
  }

  function trimToSafeSize() {
    const width = Number($('generation-width')?.value || 0);
    const height = Number($('generation-height')?.value || 0);
    if (!width || !height) return;
    if (width >= height) {
      setValue('generation-width', 1024);
      setValue('generation-height', Math.max(512, Math.round((height / width) * 1024 / 64) * 64));
    } else {
      setValue('generation-height', 1024);
      setValue('generation-width', Math.max(512, Math.round((width / height) * 1024 / 64) * 64));
    }
    updateGuardrails();
    const status = $('generation-status');
    if (status) {
      status.textContent = 'Trimmed the current canvas back to a safer size for low/medium VRAM systems.';
      status.className = 'status';
    }
  }

  function countDynamicItems(id) {
    const wrap = $(id);
    if (!wrap) return 0;
    return wrap.querySelectorAll(':scope > *').length;
  }

  function currentRisk() {
    const width = Number($('generation-width')?.value || 0);
    const height = Number($('generation-height')?.value || 0);
    const steps = Number($('generation-steps')?.value || 0);
    const pixels = width * height;
    let score = 0;

    if (pixels > 1048576) score += 3;
    else if (pixels > 786432) score += 2;
    else if (pixels > 0) score += 1;

    if (steps >= 32) score += 2;
    else if (steps >= 24) score += 1;

    if (($('generation-refine-enabled')?.value || '') === 'true') score += 2;
    if (($('generation-supir-enabled')?.value || '') === 'true') score += 4;
    if ($('generation-detailer-enabled')?.checked) score += 1;
    if ($('generation-controlnet-enabled')?.checked) score += 1;
    if ($('generation-ipadapter-enabled')?.checked) score += 1;
    if (countDynamicItems('generation-lora-extra-list') > 1) score += 1;

    let label = 'Light';
    if (score >= 7) label = 'Heavy';
    else if (score >= 4) label = 'Medium';

    return { score, label, width, height, steps, pixels };
  }

  function currentSuggestions(risk) {
    const suggestions = [];
    if (risk.pixels > 1048576) suggestions.push('Drop the long side closer to 768–1024 before stacking extras.');
    if (($('generation-supir-enabled')?.value || '') === 'true') suggestions.push('Leave SUPIR for the last cleanup pass only.');
    if (($('generation-refine-enabled')?.value || '') === 'true' && $('generation-detailer-enabled')?.checked) suggestions.push('Use Upscale Lab first, then try Selective Repair (ADetailer) only if a local area still looks weak.');
    if ($('generation-controlnet-enabled')?.checked && $('generation-ipadapter-enabled')?.checked) suggestions.push('Avoid turning on both structure and reference systems immediately unless the base image truly needs both.');
    if (countDynamicItems('generation-lora-extra-list') > 1) suggestions.push('Start with one LoRA, then stack more only after the base image behaves well.');
    if (!$('backend-low-vram-toggle')?.checked) suggestions.push('Low VRAM mode is off. Turn it on if you want the app to keep steering you toward lighter routes.');
    if (!suggestions.length) suggestions.push('Current setup looks manageable. Keep the base pass simple before adding heavier finish tools.');
    return suggestions.slice(0, 3);
  }

  function renderActions(risk) {
    const host = $('generation-vram-actions');
    if (!host) return;
    host.innerHTML = '';

    const actions = [];
    if (lowVramEnabled() && risk.pixels > 1048576) {
      actions.push({
        label: 'Trim to safe size',
        title: 'Reduce the current canvas to a safer size for low/medium VRAM use.',
        handler: trimToSafeSize
      });
    }
    if (risk.label === 'Heavy') {
      actions.push({
        label: 'Apply Finish Lite',
        title: 'Switch to a lighter finish recipe.',
        handler: () => applyRecipe('finish_lite')
      });
    }
    if (risk.label !== 'Light' && $('generation-supir-enabled')?.value === 'true') {
      actions.push({
        label: 'Turn off SUPIR',
        title: 'Keep SUPIR for the very last pass only.',
        handler: () => {
          setValue('generation-supir-enabled', 'false');
          updateGuardrails();
        }
      });
    }

    if (!actions.length) {
      const note = document.createElement('div');
      note.className = 'generation-vram-action-note';
      note.textContent = 'No trim needed right now. Use the lite recipes above when you want a safer starting stack.';
      host.appendChild(note);
      return;
    }

    actions.forEach(action => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-small generation-vram-action-btn';
      button.textContent = action.label;
      button.title = action.title || action.label;
      button.addEventListener('click', event => {
        event.preventDefault();
        action.handler();
      });
      host.appendChild(button);
    });
  }

  function updateGuardrails() {
    ensureCostBadges();
    ensureGuardrailsPanel();
    renderRecipeButtons();

    const badge = $('generation-vram-risk-badge');
    const modeBadge = $('generation-vram-mode-badge');
    const summary = $('generation-vram-summary');
    if (!badge || !modeBadge || !summary) return;

    const risk = currentRisk();
    badge.className = `generation-cost-badge is-${risk.label.toLowerCase()}`;
    badge.textContent = risk.label;
    modeBadge.textContent = `Low VRAM mode: ${lowVramEnabled() ? 'On' : 'Off'}`;
    setModeBadgeTone(modeBadge, risk.label);

    const suggestions = currentSuggestions(risk);
    summary.innerHTML = `
      <div class="generation-vram-stat-row">
        <span class="generation-vram-stat">Size: ${risk.width || '—'} × ${risk.height || '—'}</span>
        <span class="generation-vram-stat">Steps: ${risk.steps || '—'}</span>
        <span class="generation-vram-stat">Risk score: ${risk.score}</span>
      </div>
      <div class="generation-vram-tip-row">${suggestions.map(item => `<span class="generation-vram-tip">${item}</span>`).join('')}</div>`;

    renderActions(risk);
  }

  function bindInputs() {
    [
      'backend-low-vram-toggle',
      'generation-width',
      'generation-height',
      'generation-steps',
      'generation-refine-enabled',
      'generation-supir-enabled',
      'generation-detailer-enabled',
      'generation-controlnet-enabled',
      'generation-ipadapter-enabled',
      'generation-refine-scale'
    ].forEach(id => {
      const node = $(id);
      if (!node || node.dataset.vramBound === '1') return;
      const evt = node.tagName === 'INPUT' && node.type === 'number' ? 'input' : 'change';
      node.addEventListener(evt, updateGuardrails);
      node.addEventListener('change', updateGuardrails);
      node.dataset.vramBound = '1';
    });

    const loraWrap = $('generation-lora-extra-list');
    if (loraWrap && loraWrap.dataset.vramObserved !== '1') {
      const observer = new MutationObserver(() => updateGuardrails());
      observer.observe(loraWrap, { childList: true, subtree: true });
      loraWrap.dataset.vramObserved = '1';
    }
  }

  function boot(attempt = 0) {
    const goalShell = $('generation-goal-shell');
    const workflowWrap = document.querySelector(`${ROOT_SELECTOR} [data-accordion-id="generation-workflow-wrap"]`);
    if (!goalShell || !workflowWrap) {
      if (attempt < 40) window.setTimeout(() => boot(attempt + 1), 150);
      return;
    }
    bindInputs();
    updateGuardrails();
  }

  document.addEventListener('neo-generation-layout-mounted', () => window.setTimeout(() => boot(0), 120));
  ready(() => boot(0));
})();
