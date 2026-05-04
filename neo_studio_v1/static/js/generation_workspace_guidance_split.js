(function () {
  function makeEl(tag, className = '', html = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html) el.innerHTML = html;
    return el;
  }

  function setFieldValue(id, value, eventName = 'change', deps) {
    const el = deps.$(id);
    if (!el) return;
    el.value = value;
    el.dispatchEvent(new Event(eventName, { bubbles: true }));
  }

  function openAccordionById(id, deps) {
    const target = deps.queryAccordion(id) || document.querySelector(`[data-generated-shell-for="${id}"]`);
    if (!target) return;
    const host = target.parentElement;
    if (host) {
      host.querySelectorAll(':scope > details.accordion-block').forEach(detail => {
        if (detail !== target) detail.open = false;
      });
    }
    target.open = true;
    try {
      target.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } catch (_) {
      target.scrollIntoView();
    }
  }

  function setFieldValueWithEvents(id, value, deps) {
    const el = deps.$(id);
    if (!el) return;
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function setNumericPair(id, value, deps) {
    setFieldValueWithEvents(id, value, deps);
    setFieldValueWithEvents(`${id}-range`, value, deps);
  }

  function applyStarterDefaults({ mode = 'txt2img', setupTab = 'core', width = null, height = null, steps = null, cfg = null, denoise = null, accordionId = null } = {}, deps) {
    deps.syncMode(mode);
    deps.syncSetupTab(setupTab);
    if (width !== null) setFieldValueWithEvents('generation-width', width, deps);
    if (height !== null) setFieldValueWithEvents('generation-height', height, deps);
    if (width !== null || height !== null) setFieldValueWithEvents('generation-size-preset', 'custom', deps);
    if (steps !== null) setNumericPair('generation-steps', steps, deps);
    if (cfg !== null) setNumericPair('generation-cfg', cfg, deps);
    if (denoise !== null) setNumericPair('generation-denoise', denoise, deps);
    setFieldValueWithEvents('generation-batch-size', 1, deps);
    if (accordionId) window.setTimeout(() => openAccordionById(accordionId, deps), 60);
  }

  function scrollNodeIntoView(node) {
    if (!node) return;
    try {
      node.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } catch (_) {
      node.scrollIntoView();
    }
  }

  function createHintStrip({ id, title, copy, actions = [] } = {}, deps) {
    let panel = deps.$(id);
    if (!panel) {
      panel = makeEl('div', 'generation-guidance-strip');
      panel.id = id;
      panel.innerHTML = `
        <div class="generation-guidance-main">
          <div class="generation-guidance-title"></div>
          <div class="generation-guidance-copy"></div>
        </div>
        <div class="generation-guidance-actions"></div>`;
    }
    const titleNode = panel.querySelector('.generation-guidance-title');
    const copyNode = panel.querySelector('.generation-guidance-copy');
    const actionsNode = panel.querySelector('.generation-guidance-actions');
    if (titleNode) titleNode.textContent = title || '';
    if (copyNode) copyNode.textContent = copy || '';
    if (actionsNode) {
      actionsNode.innerHTML = '';
      actions.forEach(action => {
        const btn = makeEl('button', `generation-guidance-chip${action.disabled ? ' is-disabled' : ''}${action.kind === 'status' ? ' is-status' : ''}`);
        btn.type = 'button';
        btn.textContent = action.label || 'Open';
        if (action.title) btn.title = action.title;
        if (action.disabled) {
          btn.disabled = true;
          btn.setAttribute('aria-disabled', 'true');
        } else {
          btn.addEventListener('click', event => {
            event.preventDefault();
            action.onClick?.();
          });
        }
        actionsNode.appendChild(btn);
      });
    }
    return panel;
  }

  function createDecisionPanel({ id, title, copy, options = [] } = {}, deps) {
    let panel = deps.$(id);
    if (!panel) {
      panel = makeEl('div', 'generation-decision-panel');
      panel.id = id;
      panel.innerHTML = `
        <div class="generation-decision-head">
          <div class="generation-decision-title"></div>
          <div class="generation-decision-copy"></div>
        </div>
        <div class="generation-decision-grid"></div>`;
    }
    const titleNode = panel.querySelector('.generation-decision-title');
    const copyNode = panel.querySelector('.generation-decision-copy');
    const grid = panel.querySelector('.generation-decision-grid');
    if (titleNode) titleNode.textContent = title || '';
    if (copyNode) copyNode.textContent = copy || '';
    if (grid && !grid.dataset.neoBound) {
      options.forEach(option => {
        const button = makeEl('button', 'generation-decision-option');
        button.type = 'button';
        button.innerHTML = `
          <span class="generation-decision-kicker">${option.kicker || 'Route'}</span>
          <span class="generation-decision-label">${option.label || ''}</span>
          <span class="generation-decision-note">${option.note || ''}</span>`;
        button.addEventListener('click', event => {
          event.preventDefault();
          option.onClick?.();
        });
        grid.appendChild(button);
      });
      grid.dataset.neoBound = '1';
    }
    return panel;
  }

  function applyPresetFirstOnboarding(deps) {
    const workflowHost = deps.$('generation-workflow-host');
    if (!workflowHost) return;
    const panel = createDecisionPanel({
      id: 'generation-starter-panel',
      title: 'Starter presets',
      copy: 'Use these safe first clicks when you want a calmer starting point before touching the deeper controls. They bias toward lighter settings and the right tab for the job.',
      options: [
        {
          kicker: 'Build',
          label: 'Safe portrait start',
          note: 'Text → Image, portrait framing, lighter CFG, and a simple first-pass setup.',
          onClick: () => applyStarterDefaults({ mode: 'txt2img', setupTab: 'core', width: 896, height: 1344, steps: 28, cfg: 4.5, accordionId: 'generation-workflow-wrap' }, deps),
        },
        {
          kicker: 'Guide',
          label: 'IP-Adapter match start',
          note: 'Jump to Reference, keep a safe base setup, and open IP-Adapter identity presets first.',
          onClick: () => applyStarterDefaults({ mode: 'txt2img', setupTab: 'guide', width: 896, height: 1344, steps: 28, cfg: 4.5, accordionId: 'generation-ipadapter-settings' }, deps),
        },
        {
          kicker: 'Repair',
          label: 'Repair area start',
          note: 'Switch to inpaint, lower denoise a bit, and open Inpaint controls first.',
          onClick: () => applyStarterDefaults({ mode: 'inpaint', setupTab: 'guide', steps: 24, cfg: 4.0, denoise: 0.6, accordionId: 'generation-inpaint-controls' }, deps),
        },
        {
          kicker: 'Finish',
          label: 'Finish / upscale start',
          note: 'Jump to Finish and open the preserve-first upscale path before heavier polish tools.',
          onClick: () => {
            setFieldValueWithEvents('generation-image-upscale-profile', 'preserve_2x', deps);
            applyStarterDefaults({ mode: deps.$('generation-workflow-type')?.value || 'txt2img', setupTab: 'enhance', accordionId: 'generation-image-upscale-settings' }, deps);
          },
        },
      ],
    }, deps);
    if (workflowHost.firstElementChild !== panel) workflowHost.insertBefore(panel, workflowHost.firstChild);
  }

  function applyModeAwareGuidance(deps) {
    const workflowHost = deps.$('generation-workflow-host');
    if (!workflowHost) return;
    const mode = deps.$('generation-workflow-type')?.value || 'txt2img';
    const sourceLoaded = !!(deps.$('generation-source-image')?.files?.length);
    const maskLoaded = !!(deps.$('generation-mask-image')?.files?.length);
    const lowVram = !!(deps.$('backend-low-vram-toggle')?.checked);

    const modeCopy = {
      txt2img: 'Prompt + size first. Use Reference only when the prompt alone is not enough.',
      img2img: 'Load a source image first, then keep denoise modest for softer changes.',
      inpaint: 'Source image + mask first, then use Inpaint controls or Selective Repair for the exact area you want to change.',
      outpaint: 'Source image first, then expand the canvas before adding heavier guidance.',
    };

    let copy = modeCopy[mode] || modeCopy.txt2img;
    if (mode !== 'txt2img' && !sourceLoaded) copy = `Needs a source image on the right. ${copy}`;
    if (mode === 'inpaint' && !maskLoaded) copy += ' Add a mask before queueing.';
    if (mode === 'outpaint') {
      const totalPad = Number(deps.$('generation-outpaint-left')?.value || 0) + Number(deps.$('generation-outpaint-top')?.value || 0) + Number(deps.$('generation-outpaint-right')?.value || 0) + Number(deps.$('generation-outpaint-bottom')?.value || 0);
      if (sourceLoaded && !(totalPad > 0)) copy += ' Add padding on at least one side before queueing.';
    }
    if (lowVram) copy += ' Low VRAM is on, so lighter sizes are safer.';

    const blockers = [];
    if (mode === 'img2img' && !sourceLoaded) blockers.push('Generate is locked until you load a source image for Image → Image.');
    if (mode === 'inpaint' && !sourceLoaded) blockers.push('Generate is locked until you load a source image for Repair Area.');
    if (mode === 'inpaint' && sourceLoaded && !maskLoaded) blockers.push('Generate is locked until you add a mask for Repair Area.');
    if (mode === 'outpaint' && !sourceLoaded) blockers.push('Generate is locked until you load a source image for Expand Canvas.');
    if (mode === 'outpaint' && sourceLoaded) {
      const totalPad = Number(deps.$('generation-outpaint-left')?.value || 0) + Number(deps.$('generation-outpaint-top')?.value || 0) + Number(deps.$('generation-outpaint-right')?.value || 0) + Number(deps.$('generation-outpaint-bottom')?.value || 0);
      if (!(totalPad > 0)) blockers.push('Generate is locked until you add padding on at least one side for Expand Canvas.');
    }

    const recommendedAction = {
      txt2img: { label: 'Open Reference', onClick: () => deps.syncSetupTab('guide') },
      img2img: !sourceLoaded
        ? { label: 'Load source first', onClick: () => scrollNodeIntoView(deps.$('generation-source-wrap')) }
        : { label: 'Open Finish', onClick: () => deps.syncSetupTab('enhance') },
      inpaint: (!sourceLoaded || !maskLoaded)
        ? { label: 'Load source + mask', onClick: () => scrollNodeIntoView(deps.$('generation-source-wrap')) }
        : { label: 'Open Inpaint controls', onClick: () => deps.syncSetupTab('core') },
      outpaint: !sourceLoaded
        ? { label: 'Load source first', onClick: () => scrollNodeIntoView(deps.$('generation-source-wrap')) }
        : { label: 'Set padding', onClick: () => deps.syncSetupTab('core') },
    }[mode] || { label: 'Open Reference', onClick: () => deps.syncSetupTab('guide') };

    const strip = createHintStrip({
      id: 'generation-next-step-strip',
      title: 'Live hint',
      copy,
      actions: [
        blockers.length
          ? { label: 'Generate locked', disabled: true, kind: 'status', title: blockers[0] }
          : { label: 'Ready to queue', disabled: true, kind: 'status', title: 'No launch blockers right now.' },
        {
          label: mode === 'txt2img' ? 'Preview' : 'Source area',
          onClick: () => scrollNodeIntoView(mode === 'txt2img' ? deps.$('generation-live-workspace') : deps.$('generation-source-wrap')),
        },
        recommendedAction,
        {
          label: 'Assets',
          onClick: () => deps.syncSetupTab('assets'),
        },
      ],
    }, deps);

    const legacyPanel = deps.$('generation-next-step-panel');
    if (legacyPanel) legacyPanel.remove();
    const starterPanel = deps.$('generation-starter-panel');
    if (starterPanel?.nextElementSibling !== strip) workflowHost.insertBefore(strip, starterPanel ? starterPanel.nextSibling : workflowHost.firstChild);
  }

  function applyGoalRecipe(recipeId, deps) {
    if (!recipeId) return;
    if (recipeId === 'create_portrait_safe') {
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'core', width: 896, height: 1344, steps: 28, cfg: 4.5, accordionId: 'generation-workflow-wrap' }, deps);
      return;
    }
    if (recipeId === 'create_square_safe') {
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'core', width: 1024, height: 1024, steps: 28, cfg: 4.5, accordionId: 'generation-workflow-wrap' }, deps);
      return;
    }
    if (recipeId === 'create_landscape_safe') {
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'core', width: 1344, height: 896, steps: 28, cfg: 4.5, accordionId: 'generation-workflow-wrap' }, deps);
      return;
    }
    if (recipeId === 'reference_same_face') {
      setFieldValueWithEvents('generation-identity-goal', 'same_face', deps);
      setFieldValueWithEvents('generation-identity-route', 'ipadapter_faceid', deps);
      setFieldValueWithEvents('generation-identity-strength', '0.9', deps);
      setFieldValueWithEvents('generation-identity-faceid-lora', '0.75', deps);
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'guide', width: 896, height: 1344, steps: 28, cfg: 4.5, accordionId: 'generation-ipadapter-settings' }, deps);
      return;
    }
    if (recipeId === 'reference_same_character') {
      setFieldValueWithEvents('generation-identity-goal', 'same_character', deps);
      setFieldValueWithEvents('generation-identity-route', 'ipadapter_standard', deps);
      setFieldValueWithEvents('generation-identity-strength', '0.8', deps);
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'guide', width: 896, height: 1344, steps: 28, cfg: 4.5, accordionId: 'generation-ipadapter-settings' }, deps);
      return;
    }
    if (recipeId === 'reference_style_carry') {
      setFieldValueWithEvents('generation-identity-goal', 'style_reference', deps);
      setFieldValueWithEvents('generation-identity-route', 'ipadapter_standard', deps);
      setFieldValueWithEvents('generation-identity-strength', '0.65', deps);
      applyStarterDefaults({ mode: 'txt2img', setupTab: 'guide', width: 896, height: 1344, steps: 26, cfg: 4.2, accordionId: 'generation-ipadapter-settings' }, deps);
      return;
    }
    if (recipeId === 'repair_small_area') {
      applyStarterDefaults({ mode: 'inpaint', setupTab: 'guide', steps: 24, cfg: 4.0, denoise: 0.45, accordionId: 'generation-inpaint-controls' }, deps);
      return;
    }
    if (recipeId === 'repair_face_hands') {
      setFieldValueWithEvents('generation-detailer-enabled', true, deps);
      applyStarterDefaults({ mode: 'inpaint', setupTab: 'enhance', steps: 24, cfg: 4.0, denoise: 0.5, accordionId: 'generation-detailer-settings' }, deps);
      return;
    }
    if (recipeId === 'cleanup_remove_object') {
      if (deps.$('generation-inpaint-target')) setFieldValueWithEvents('generation-inpaint-target', 'masked', deps);
      if (deps.$('generation-inpaint-context')) setFieldValueWithEvents('generation-inpaint-context', 'full_image', deps);
      applyStarterDefaults({ mode: 'inpaint', setupTab: 'core', steps: 24, cfg: 4.0, denoise: 0.55, accordionId: 'generation-inpaint-controls' }, deps);
      return;
    }
    if (recipeId === 'cleanup_cut_out_subject') {
      if (deps.$('generation-inpaint-target')) setFieldValueWithEvents('generation-inpaint-target', 'masked', deps);
      if (deps.$('generation-inpaint-context')) setFieldValueWithEvents('generation-inpaint-context', 'full_image', deps);
      applyStarterDefaults({ mode: 'inpaint', setupTab: 'core', steps: 22, cfg: 4.0, denoise: 0.4, accordionId: 'generation-inpaint-controls' }, deps);
      return;
    }
    if (recipeId === 'finish_preserve_2x') {
      setFieldValueWithEvents('generation-image-upscale-profile', 'preserve_2x', deps);
      applyStarterDefaults({ mode: deps.$('generation-workflow-type')?.value || 'txt2img', setupTab: 'enhance', accordionId: 'generation-image-upscale-settings' }, deps);
      return;
    }
    if (recipeId === 'finish_portrait_restore') {
      setFieldValueWithEvents('generation-image-upscale-profile', 'portrait_restore_2x', deps);
      applyStarterDefaults({ mode: deps.$('generation-workflow-type')?.value || 'txt2img', setupTab: 'enhance', accordionId: 'generation-image-upscale-settings' }, deps);
      return;
    }
    if (recipeId === 'finish_heavy_rescue') {
      applyStarterDefaults({ mode: deps.$('generation-workflow-type')?.value || 'txt2img', setupTab: 'enhance', accordionId: 'generation-supir-settings' }, deps);
      return;
    }
    if (recipeId === 'recover_output_rebuild') {
      deps.syncSetupTab('output');
      window.setTimeout(() => openAccordionById('generation-output-settings-wrap', deps), 60);
      return;
    }
    if (recipeId === 'recover_output_inspect') {
      deps.syncSetupTab('output');
      window.setTimeout(() => openAccordionById('neo-library-output-inspector', deps), 60);
      return;
    }
  }

  function applyGoalHandoff(goalId, deps) {
    if (!goalId) return;
    if (goalId === 'create_from_scratch') return applyGoalRecipe('create_portrait_safe', deps);
    if (goalId === 'match_reference') return applyGoalRecipe('reference_same_face', deps);
    if (goalId === 'fix_image_region') return applyGoalRecipe('repair_small_area', deps);
    if (goalId === 'remove_object_or_background') return applyGoalRecipe('repair_small_area', deps);
    if (goalId === 'finalize_and_upscale') return applyGoalRecipe('finish_preserve_2x', deps);
    if (goalId === 'recover_from_previous_output') return applyGoalRecipe('recover_output_rebuild', deps);
  }

  function applyDecisionFirstCopy(deps) {
    deps.updateAccordionText(deps.queryAccordion('generation-controlnet-settings'), 'ControlNet', 'Use this when the main job is pose, edge, depth, or composition guidance — not identity matching.');
    deps.updateAccordionText(deps.queryAccordion('generation-ipadapter-settings'), 'IP-Adapter / Identity Controls', 'Start here for same-face, same-character, style-reference, or manual reference control. Identity presets live inside this lane.');
    deps.updateAccordionText(deps.queryAccordion('generation-inpaint-controls'), 'Inpaint controls', 'Use this when you want to remove an object, isolate a subject, or repair a local region with the Mask Editor.');
    deps.updateAccordionText(deps.queryAccordion('generation-image-upscale-settings'), 'Image Upscale', 'Choose this when you want a preserve-first size boost without another full redraw pass.');
    deps.updateAccordionText(deps.queryAccordion('generation-hires-settings'), 'Upscale Lab', 'Choose this when the base image already works and you want a cleaner larger redraw finish.');
    deps.updateAccordionText(deps.queryAccordion('generation-supir-settings'), 'SUPIR', 'Choose this when the image is rough and needs a heavier rescue pass than the normal finish tools.');
    deps.updateAccordionText(deps.queryAccordion('generation-detailer-settings'), 'Selective Repair (ADetailer)', 'Choose this for local fixes like faces, hands, or small repair passes after the main image already works.');
  }

  function applyDecisionFirstLaneRewrite(deps) {
    const root = deps.getRoot();
    if (!root) return;
    applyDecisionFirstCopy(deps);

    const matchHost = deps.$('generation-match-tab-host');
    const enhanceHost = deps.$('generation-enhance-tab-host');
    if (matchHost) {
      const panel = createDecisionPanel({
        id: 'generation-reference-decision-panel',
        title: 'What kind of match do you need?',
        copy: 'Pick the job first so Neo can steer you to the right reference tool instead of making you decode every advanced setting up front.',
        options: [
          {
            kicker: 'Identity',
            label: 'Same face / same person',
            note: 'Use IP-Adapter identity presets with face-first defaults.',
            onClick: () => {
              setFieldValue('generation-identity-goal', 'same_face', 'change', deps);
              openAccordionById('generation-ipadapter-settings', deps);
            },
          },
          {
            kicker: 'Identity',
            label: 'Same character / look',
            note: 'Keep visual consistency without forcing the exact same face every time.',
            onClick: () => {
              setFieldValue('generation-identity-goal', 'same_character', 'change', deps);
              openAccordionById('generation-ipadapter-settings', deps);
            },
          },
          {
            kicker: 'Style',
            label: 'Style / vibe carry-over',
            note: 'Use a reference image mainly for mood, finish, or visual direction.',
            onClick: () => {
              setFieldValue('generation-identity-goal', 'style_reference', 'change', deps);
              openAccordionById('generation-ipadapter-settings', deps);
            },
          },
          {
            kicker: 'Structure',
            label: 'Match pose / edges / layout',
            note: 'Jump straight to ControlNet for stronger structure guidance.',
            onClick: () => openAccordionById('generation-controlnet-settings', deps),
          },
          {
            kicker: 'Advanced',
            label: 'Deep manual reference tuning',
            note: 'Open IP-Adapter Controls only when the main match lane is not enough.',
            onClick: () => openAccordionById('generation-ipadapter-settings', deps),
          },
        ],
      }, deps);
      if (matchHost.firstElementChild !== panel) matchHost.insertBefore(panel, matchHost.firstChild);
    }



    if (enhanceHost) {
      const panel = createDecisionPanel({
        id: 'generation-finish-decision-panel',
        title: 'How do you want to finish this image?',
        copy: 'Choose the outcome first: preserve, polish, rescue, or repair. Then Neo can put you in the right finish tool without backend jargon overload.',
        options: [
          {
            kicker: 'Preserve',
            label: 'Clean size boost',
            note: 'Use Image Upscale when you want a preserve-first export boost.',
            onClick: () => {
              setFieldValue('generation-image-upscale-profile', 'preserve_2x', 'change', deps);
              openAccordionById('generation-image-upscale-settings', deps);
            },
          },
          {
            kicker: 'Polish',
            label: 'Redraw and refine',
            note: 'Use Upscale Lab when the image already works and just needs a stronger finish.',
            onClick: () => {
              setFieldValue('generation-refine-profile', 'balanced_finish', 'change', deps);
              openAccordionById('generation-hires-settings', deps);
            },
          },
          {
            kicker: 'Repair',
            label: 'Fix faces / hands / small areas',
            note: 'Use Selective Repair for targeted cleanup instead of a full finish reroute.',
            onClick: () => openAccordionById('generation-detailer-settings', deps),
          },
          {
            kicker: 'Rescue',
            label: 'Heavy rescue pass',
            note: 'Use SUPIR only when the image is rough enough to need a bigger recovery step.',
            onClick: () => openAccordionById('generation-supir-settings', deps),
          },
        ],
      }, deps);
      if (enhanceHost.firstElementChild !== panel) enhanceHost.insertBefore(panel, enhanceHost.firstChild);
    }
  }

  window.NeoGenerationWorkspaceGuidance = {
    applyPresetFirstOnboarding,
    applyModeAwareGuidance,
    applyGoalRecipe,
    applyGoalHandoff,
    applyDecisionFirstLaneRewrite,
  };
})();
