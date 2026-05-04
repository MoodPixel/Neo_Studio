(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const MODE_STORAGE_KEY = 'neo_generation_mode_v4';
  const SETUP_TAB_STORAGE_KEY = 'neo_generation_setup_tab_v1';
  let inlineToolShells = null;

  const MODE_LABELS = {
    txt2img: 'Text → Image',
    img2img: 'Image → Image',
    inpaint: 'Repair Area',
    outpaint: 'Expand Canvas',
  };

  const LANES = {
    assets: {
      label: 'Assets / Reuse',
      emoji: '🧰',
      title: 'Assets / Reuse',
      copy: 'Keep reusable prompt assets together: Tag Assist, styles, wildcards, LoRAs, embeddings, captions, character tools, and keyword browsing.',
      items: [
        'generation-tagassist',
        'generation-style-addons',
        'generation-wildcards',
        'generation-lora-settings',
        'generation-ti-settings',
        'host:character',
        'host:keyword',
        'host:captions',
      ],
    },
    guide: {
      label: 'Reference / Match',
      emoji: '🎯',
      title: 'Reference / Match',
      copy: 'Use reference control, structure guidance, and identity support when the image needs a stronger match instead of a freer prompt-only pass.',
      items: [
        'generation-controlnet-settings',
        'generation-ipadapter-settings',
      ],
    },
    enhance: {
      label: 'Finish / Polish',
      emoji: '✨',
      title: 'Finish / Polish',
      copy: 'Polish a result after the composition already works. Keep upscale, restoration, and repair together instead of mixing them into the base setup.',
      items: [
        'generation-hires-settings',
        'generation-image-upscale-settings',
        'generation-detailer-settings',
        'generation-supir-settings',
      ],
    },
    output: {
      label: 'Results / Metadata',
      emoji: '📦',
      title: 'Results / Metadata',
      copy: 'Handle save paths, selected-file details, metadata review, and output reuse from one place instead of scattering them across the shell.',
      items: [
        'host:output',
        'host:inspector',
      ],
    },
  };

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function setHidden(el, hidden) {
    if (!el) return;
    el.classList.toggle('generation-workspace-hidden', !!hidden);
    if (hidden) el.setAttribute('aria-hidden', 'true');
    else el.removeAttribute('aria-hidden');
  }

  function getRoot() {
    return document.querySelector(ROOT_SELECTOR);
  }

  function makeEl(tag, className = '', html = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html) el.innerHTML = html;
    return el;
  }

  function formatModeLabel(mode) {
    return MODE_LABELS[mode] || 'Txt2Img';
  }

  function queryAccordion(id) {
    return document.querySelector(`[data-accordion-id="${id}"]`);
  }

  function updateAccordionText(target, title, hint) {
    if (!target) return;
    const titleNode = target.querySelector(':scope > summary .accordion-title');
    const hintNode = target.querySelector(':scope > summary .accordion-hint');
    if (titleNode && title) titleNode.textContent = title;
    if (hintNode && hint) hintNode.textContent = hint;
  }

  function ensureHostAccordion(host, { id, title, hint }) {
    if (!host) return null;
    let shell = document.querySelector(`[data-generated-shell-for="${id}"]`);
    if (!shell) {
      shell = makeEl('details', 'accordion-block generation-inline-accordion');
      shell.dataset.generatedShellFor = id;
      shell.dataset.accordionId = id;
      shell.open = false;
      shell.innerHTML = `
        <summary class="accordion-summary">
          <div>
            <div class="accordion-title"></div>
            <div class="accordion-hint"></div>
          </div>
          <span class="accordion-chevron" aria-hidden="true">▾</span>
        </summary>
        <div class="accordion-body"></div>`;
    }
    updateAccordionText(shell, title, hint);
    const body = shell.querySelector(':scope > .accordion-body');
    if (body && host.parentElement !== body) body.appendChild(host);
    host.style.display = '';
    host.style.marginTop = '0';
    return shell;
  }

  function ensureInlineTools() {
    const promptCard = getRoot()?.querySelector('.generation-prompt-card');
    setHidden(promptCard?.querySelector('.generation-prompt-tool-row'), true);

    const characterWrap = ensureHostAccordion($('generation-character-tool-host'), {
      id: 'generation-inline-character-tool',
      title: 'Character Builder',
      hint: 'Build a character block inline and append it straight into the generation prompt.',
    });

    const keywordWrap = ensureHostAccordion($('generation-keyword-tool-host'), {
      id: 'generation-inline-keyword-tool',
      title: 'Keyword Browser',
      hint: 'Browse and insert reusable keywords directly from the current workflow.',
    });

    const captionHost = $('generation-caption-browser-host') || $('generation-caption-tool-host');
    if (captionHost) {
      captionHost.style.display = '';
      captionHost.style.marginTop = '0';
    }
    const captionWrap = ensureHostAccordion(captionHost, {
      id: 'generation-inline-captions',
      title: 'Caption Browser',
      hint: 'Browse saved captions and send them back into the current prompt workflow.',
    });

    inlineToolShells = { characterWrap, keywordWrap, captionWrap };
    return inlineToolShells;
  }



  function ensureSubsectionShell(parent, { id, title, hint, open = false } = {}) {
    if (!parent || !id) return { shell: null, body: null };
    let shell = $(id);
    if (!shell) {
      shell = makeEl('details', 'accordion-block generation-inline-accordion');
      shell.id = id;
      shell.dataset.defaultOpen = open ? 'true' : 'false';
      shell.innerHTML = `
        <summary class="accordion-summary">
          <div>
            <div class="accordion-title"></div>
            <div class="accordion-hint"></div>
          </div>
          <span class="accordion-chevron" aria-hidden="true">▾</span>
        </summary>
        <div class="accordion-body"></div>`;
      if (open) shell.open = true;
    }
    updateAccordionText(shell, title, hint);
    if (shell.parentElement !== parent) parent.appendChild(shell);
    return { shell, body: shell.querySelector(':scope > .accordion-body') };
  }

  function moveInto(node, host) {
    if (node && host && node.parentElement !== host) host.appendChild(node);
  }


  function boundarySplitDeps() {
    return {
      $,
      getRoot,
      queryAccordion,
      updateAccordionText,
      ensureSubsectionShell,
      moveInto,
      setHidden,
    };
  }

  function guidanceSplitDeps() {
    return {
      $,
      getRoot,
      queryAccordion,
      updateAccordionText,
      syncMode,
      syncSetupTab,
    };
  }

  function applyQuickUseManagementSplit() {
    window.NeoGenerationWorkspaceBoundary?.applyQuickUseManagementSplit(boundarySplitDeps());
  }

  function applyPresetFirstOnboarding() {
    window.NeoGenerationWorkspaceGuidance?.applyPresetFirstOnboarding(guidanceSplitDeps());
  }

  function applyModeAwareGuidance() {
    window.NeoGenerationWorkspaceGuidance?.applyModeAwareGuidance(guidanceSplitDeps());
  }

  function applyGoalRecipe(recipeId) {
    window.NeoGenerationWorkspaceGuidance?.applyGoalRecipe(recipeId, guidanceSplitDeps());
  }

  function applyGoalHandoff(goalId) {
    window.NeoGenerationWorkspaceGuidance?.applyGoalHandoff(goalId, guidanceSplitDeps());
  }

  function applyDecisionFirstLaneRewrite() {
    window.NeoGenerationWorkspaceGuidance?.applyDecisionFirstLaneRewrite(guidanceSplitDeps());
  }

  function updateSetupTabButtons(key) {
    document.querySelectorAll('[data-generation-setup-tab]').forEach(btn => {
      const active = btn.getAttribute('data-generation-setup-tab') === key;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function forceFinishSectionPlacement() {
    const enhanceHost = $('generation-enhance-tab-host');
    const imageUpscale = queryAccordion('generation-image-upscale-settings');
    if (enhanceHost && imageUpscale && imageUpscale.parentElement !== enhanceHost) {
      imageUpscale.style.marginTop = '0';
      enhanceHost.appendChild(imageUpscale);
    }
  }

  function forceHelperSectionPlacement() {
    const helperHost = $('generation-helper-tab-host');
    const helperPanel = $('generation-helper-status')?.closest('.workspace-helper-panel');
    const powerPanel = $('generation-power-panel');
    if (helperHost && helperPanel && helperPanel.parentElement !== helperHost) {
      helperPanel.style.marginTop = '0';
      helperHost.appendChild(helperPanel);
    }
    if (helperHost && powerPanel && powerPanel.parentElement !== helperHost) {
      powerPanel.style.marginTop = '14px';
      if (helperPanel && helperPanel.parentElement === helperHost) helperPanel.insertAdjacentElement('afterend', powerPanel);
      else helperHost.appendChild(powerPanel);
    }
  }


  function renderTabLane(laneKey, hostId) {
    const targetHost = $(hostId);
    if (!targetHost) return;
    renameLaneSpecificAccordions(laneKey);
    resolveLaneItems(laneKey).forEach(node => {
      node.style.marginTop = '0';
      setHidden(node, false);
      if (node.parentElement !== targetHost) targetHost.appendChild(node);
    });
  }

  function renderAllTabLanes() {
    renderTabLane('assets', 'generation-assets-tab-host');
    renderTabLane('guide', 'generation-match-tab-host');
    renderTabLane('enhance', 'generation-enhance-tab-host');
    renderTabLane('output', 'generation-output-tab-host');
    forceHelperSectionPlacement();
    const workflowHost = $('generation-workflow-host');
    const workflowNotes = queryAccordion('generation-workflow-notes-wrap');
    if (workflowNotes && workflowHost && workflowNotes.parentElement !== workflowHost) workflowHost.appendChild(workflowNotes);
    applyQuickUseManagementSplit();
  }

  function syncSetupTab(key) {
    const next = ['core', 'assets', 'guide', 'enhance', 'helper', 'output'].includes(key) ? key : 'core';
    const assetsHost = $('generation-assets-tab-host');
    const matchHost = $('generation-match-tab-host');
    const enhanceHost = $('generation-enhance-tab-host');
    const helperHost = $('generation-helper-tab-host');
    const outputHost = $('generation-output-tab-host');
    setHidden(getRoot()?.querySelector('.generation-prompt-card'), false);
    setHidden($('generation-workflow-host'), next !== 'core');
    setHidden(assetsHost, next !== 'assets');
    setHidden(matchHost, next !== 'guide');
    setHidden(enhanceHost, next !== 'enhance');
    setHidden(helperHost, next !== 'helper');
    setHidden(outputHost, next !== 'output');
    renderAllTabLanes();
    forceFinishSectionPlacement();
    forceHelperSectionPlacement();
    updateSetupTabButtons(next);
    persist(SETUP_TAB_STORAGE_KEY, next);
  }

  function buildSetupTabs(topLeft, workflowHost) {
    if (!topLeft || !workflowHost) return;
    let shell = $('generation-setup-tabs-shell');
    if (!shell) {
      shell = makeEl('div', 'generation-setup-tabs-shell');
      shell.id = 'generation-setup-tabs-shell';
    }
    let tabs = $('generation-setup-tabs-bar');
    if (!tabs) {
      tabs = makeEl('div', 'generation-setup-tabs-bar', `
        <button class="active" type="button" data-generation-setup-tab="core">Build</button>
        <button type="button" data-generation-setup-tab="assets">Assets</button>
        <button type="button" data-generation-setup-tab="guide">Reference</button>
        <button type="button" data-generation-setup-tab="enhance">Finish</button>
        <button type="button" data-generation-setup-tab="helper">Helper</button>
        <button type="button" data-generation-setup-tab="output">Results</button>`);
      tabs.id = 'generation-setup-tabs-bar';
    }
    let content = $('generation-setup-tabs-content');
    if (!content) {
      content = makeEl('div', 'generation-setup-tabs-content');
      content.id = 'generation-setup-tabs-content';
    }
    let assetsHost = $('generation-assets-tab-host');
    if (!assetsHost) {
      assetsHost = makeEl('div', 'generation-assets-tab-host');
      assetsHost.id = 'generation-assets-tab-host';
    }
    let matchHost = $('generation-match-tab-host');
    if (!matchHost) {
      matchHost = makeEl('div', 'generation-assets-tab-host');
      matchHost.id = 'generation-match-tab-host';
    }
    let enhanceHost = $('generation-enhance-tab-host');
    if (!enhanceHost) {
      enhanceHost = makeEl('div', 'generation-assets-tab-host');
      enhanceHost.id = 'generation-enhance-tab-host';
    }
    let helperHost = $('generation-helper-tab-host');
    if (!helperHost) {
      helperHost = makeEl('div', 'generation-assets-tab-host');
      helperHost.id = 'generation-helper-tab-host';
    }
    let outputHost = $('generation-output-tab-host');
    if (!outputHost) {
      outputHost = makeEl('div', 'generation-assets-tab-host');
      outputHost.id = 'generation-output-tab-host';
    }
    if (tabs.parentElement !== shell) shell.appendChild(tabs);
    if (content.parentElement !== shell) shell.appendChild(content);
    if (shell.parentElement !== topLeft) topLeft.appendChild(shell);
    if (workflowHost.parentElement !== content) content.appendChild(workflowHost);
    if (assetsHost.parentElement !== content) content.appendChild(assetsHost);
    if (matchHost.parentElement !== content) content.appendChild(matchHost);
    if (enhanceHost.parentElement !== content) content.appendChild(enhanceHost);
    if (helperHost.parentElement !== content) content.appendChild(helperHost);
    if (outputHost.parentElement !== content) content.appendChild(outputHost);

    const historyCard = $('generation-history-card');
    if (historyCard && outputHost && historyCard.parentElement !== outputHost) {
      outputHost.prepend(historyCard);
    }

    setHidden(workflowHost, false);
    setHidden(assetsHost, true);
    setHidden(matchHost, true);
    setHidden(enhanceHost, true);
    setHidden(helperHost, true);
    setHidden(outputHost, true);

    tabs.querySelectorAll('[data-generation-setup-tab]').forEach(btn => {
      if (btn.dataset.neoBound === '1') return;
      btn.addEventListener('click', event => {
        event.preventDefault();
        syncSetupTab(btn.getAttribute('data-generation-setup-tab') || 'core');
      });
      btn.dataset.neoBound = '1';
    });
  }

  function buildModeBar(nav) {
    if (!nav || nav.dataset.neoModeBarBuilt === '1') return;
    nav.innerHTML = `
      <div class="generation-mode-bar-head row-between">
        <div>
          <h3 style="margin:0;">Image workspace</h3>
          <div class="muted small" id="generation-mode-copy">Build the active image job below. Backend, family, workspace, and presets stay in the setup shell above.</div>
        </div>
        <div class="badge" id="generation-mode-badge">Active workspace</div>
      </div>`;
    nav.dataset.neoModeBarBuilt = '1';
  }


  function compactGlobalTopPanel() {
    const panel = getRoot()?.querySelector('.generation-global-panel');
    if (!panel) return;
    const actions = panel.querySelector('.row.u-gap-8');
    if (!actions) return;

    let tools = $('generation-top-tools-toggle');
    if (!tools) {
      tools = makeEl('details', 'generation-top-tools-toggle');
      tools.id = 'generation-top-tools-toggle';
      tools.innerHTML = `
        <summary class="btn btn-small generation-top-tools-summary">Workspace tools</summary>
        <div class="generation-top-tools-menu" id="generation-top-tools-menu"></div>`;
    }
    const menu = tools.querySelector('#generation-top-tools-menu');
    if (!menu) return;

    const keepVisible = new Set([
      'btn-generation-reset-shell',
      'btn-generation-save-snapshot',
      'generation-shell-snapshot-select',
      'btn-generation-load-snapshot',
    ]);

    Array.from(actions.children).forEach(node => {
      if (!node || node === tools) return;
      if (node.classList?.contains('badge')) return;
      const id = node.id || '';
      if (keepVisible.has(id)) return;
      if (node.parentElement !== menu) menu.appendChild(node);
    });

    const badge = actions.querySelector('.badge');
    if (tools.parentElement !== actions) {
      if (badge) actions.insertBefore(tools, badge);
      else actions.appendChild(tools);
    }

    panel.classList.add('generation-top-rail-card', 'generation-primary-surface');
    panel.dataset.neoTopCompact = '1';
  }

  function syncTopRail() {
    const root = getRoot();
    const globalPanel = root?.querySelector('.generation-global-panel');
    const goalPanel = $('generation-goal-shell');
    const vramPanel = $('generation-vram-guardrails');
    const boundary = $('generation-shell-workspace-boundary');
    const goalAnchor = $('generation-setup-goal-anchor');
    const guardrailsAnchor = $('generation-setup-guardrails-anchor');
    if (!root || !globalPanel) return;

    const staleRail = $('generation-top-rail');
    if (staleRail) {
      const nav = $('generation-workspace-nav-panel');
      if (globalPanel && globalPanel.parentElement === staleRail) {
        if (nav) root.insertBefore(globalPanel, nav);
        else root.prepend(globalPanel);
      }
      staleRail.remove();
    }

    if (goalPanel && goalAnchor && goalPanel.parentElement !== goalAnchor) {
      goalAnchor.appendChild(goalPanel);
    }
    if (vramPanel && guardrailsAnchor && vramPanel.parentElement !== guardrailsAnchor) {
      guardrailsAnchor.appendChild(vramPanel);
    }

    root.classList.add('generation-hierarchy-ui', 'generation-shell-boundary-ready');
    globalPanel.classList.remove('generation-top-rail-card', 'generation-primary-surface');
    goalPanel?.classList.remove('generation-top-rail-card', 'generation-primary-surface');
    vramPanel?.classList.remove('generation-top-rail-card', 'generation-primary-surface');
    if (boundary) boundary.dataset.boundaryReady = 'true';
  }

  function buildShellLayout() {
    const root = getRoot();
    const grid = root?.querySelector('.generation-workbench-grid');
    const setupRail = $('generation-setup-rail');
    const sessionColumn = $('generation-session-column');
    const liveWorkspace = $('generation-live-workspace');
    const actionsCard = getRoot()?.querySelector('.generation-actions-card--workspace');
    const promptCard = root?.querySelector('.generation-prompt-card');
    const workflowHost = $('generation-workflow-host');
    const outputHost = $('generation-output-settings-host');
    const inspectorHost = $('generation-output-inspector-host');
    const captionHost = $('generation-caption-browser-host') || $('generation-caption-tool-host');
    const sourceWrap = $('generation-source-wrap');
    const navPanel = $('generation-workspace-nav-panel');
    const shellPanel = root?.querySelector('.generation-shell-panel');
    if (!root || !grid || !setupRail || !sessionColumn || !liveWorkspace || !promptCard || !workflowHost) return false;

    inlineToolShells = ensureInlineTools();

    let topSplit = $('generation-top-split');
    if (!topSplit) {
      topSplit = makeEl('div', 'generation-top-split');
      topSplit.id = 'generation-top-split';
    }

    let topLeft = $('generation-top-left');
    if (!topLeft) {
      topLeft = makeEl('div', 'generation-top-left');
      topLeft.id = 'generation-top-left';
    }

    let topRight = $('generation-top-right');
    if (!topRight) {
      topRight = makeEl('div', 'generation-top-right');
      topRight.id = 'generation-top-right';
    }

    root.classList.add('generation-compact-ui', 'generation-three-column-layout', 'generation-top-bottom-shell', 'generation-no-sidebar');
    grid.classList.add('generation-three-column-grid');
    setupRail.classList.add('generation-main-scroll');
    sessionColumn.classList.add('generation-workspace-hidden');
    if (topLeft.parentElement !== topSplit) topSplit.appendChild(topLeft);
    if (topRight.parentElement !== topSplit) topSplit.appendChild(topRight);

    buildSetupTabs(topLeft, workflowHost);
    renderAllTabLanes();
    applyQuickUseManagementSplit();
    applyDecisionFirstLaneRewrite();
    applyPresetFirstOnboarding();
    applyModeAwareGuidance();
    forceFinishSectionPlacement();
    const setupShell = $('generation-setup-tabs-shell');
    if (actionsCard && navPanel && shellPanel) {
      if (actionsCard.parentElement !== root || actionsCard.nextElementSibling !== shellPanel) {
        root.insertBefore(actionsCard, shellPanel);
      }
    }
    if (setupShell && setupShell.parentElement !== topLeft) {
      topLeft.appendChild(setupShell);
    }
    if (promptCard.parentElement !== topRight) topRight.appendChild(promptCard);
    if (liveWorkspace.parentElement !== topRight) topRight.appendChild(liveWorkspace);
    if (sourceWrap && sourceWrap.parentElement !== topRight) topRight.appendChild(sourceWrap);

    if (topSplit.parentElement !== setupRail) setupRail.appendChild(topSplit);

    // Keep the caption browser host inside its generated shell so the inline accordion body does not get emptied.
    if (captionHost) {
      captionHost.style.display = '';
      captionHost.style.marginTop = '0';
    }
    const modeField = $('generation-workflow-type')?.closest('div');
    setHidden(modeField, true);

    const modeChip = $('generation-action-mode-chip');
    const statusChip = $('generation-action-status-chip');
    const backendBadge = $('generation-action-backend-badge');
    const utilityActions = root.querySelector('.generation-toolbar-utility-actions');
    setHidden(backendBadge, true);
    if (utilityActions) {
      [statusChip, modeChip].filter(Boolean).forEach(node => {
        if (node.parentElement !== utilityActions) utilityActions.appendChild(node);
      });
    }
    return true;
  }

  function updateCoreTitle(mode) {
    const workflowHost = $('generation-workflow-host');
    const wrap = workflowHost?.querySelector(':scope > details[data-accordion-id="generation-workflow-wrap"]');
    updateAccordionText(wrap, `Build - ${formatModeLabel(mode)}`, 'Shared setup for the current job type. The top bar now decides the active mode instead of a buried mode field inside the card.');
  }

  function updateModeButtons(mode) {
    document.querySelectorAll('[data-generation-mode]').forEach(btn => {
      const active = btn.getAttribute('data-generation-mode') === mode;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function persist(key, value) {
    try { window.localStorage.setItem(key, value); } catch (_) {}
  }

  function loadStored(key, fallback) {
    try {
      const value = window.localStorage.getItem(key);
      return value || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function syncMode(mode, fromUI = true) {
    const nextMode = MODE_LABELS[mode] ? mode : 'txt2img';
    const select = $('generation-workflow-type');
    if (select && select.value !== nextMode) {
      select.value = nextMode;
      if (fromUI) select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    updateCoreTitle(nextMode);
    updateModeButtons(nextMode);
    setHidden($('generation-source-wrap'), nextMode === 'txt2img');
    applyModeAwareGuidance();
    persist(MODE_STORAGE_KEY, nextMode);
  }

  function resolveLaneItems(key) {
    const lane = LANES[key] || LANES.assets;
    const items = [];
    lane.items.forEach(item => {
      if (item.startsWith('host:')) {
        if (item === 'host:output' && $('generation-output-settings-host')) items.push($('generation-output-settings-host'));
        if (item === 'host:inspector' && $('generation-output-inspector-host')) items.push($('generation-output-inspector-host'));
        if (item === 'host:character') items.push(inlineToolShells?.characterWrap || document.querySelector('[data-generated-shell-for="generation-inline-character-tool"]'));
        if (item === 'host:keyword') items.push(inlineToolShells?.keywordWrap || document.querySelector('[data-generated-shell-for="generation-inline-keyword-tool"]'));
        if (item === 'host:captions') items.push(inlineToolShells?.captionWrap || document.querySelector('[data-generated-shell-for="generation-inline-captions"]'));
        return;
      }
      items.push(queryAccordion(item));
    });
    return items.filter(Boolean);
  }

  function renameLaneSpecificAccordions(laneKey) {
    const detailer = queryAccordion('generation-detailer-settings');
    const ipadapter = queryAccordion('generation-ipadapter-settings');
    updateAccordionText(detailer, 'Selective Repair (ADetailer)', 'Use ADetailer-style targeted repair after the base image already works.');
    updateAccordionText(ipadapter, 'IP-Adapter / Identity Controls', 'Use IP-Adapter / FaceID controls and identity presets for same-face, same-character, style-reference, or reference-image guidance.');
  }

  function bindEvents() {
    document.querySelectorAll('[data-generation-mode]').forEach(btn => {
      if (btn.dataset.neoBound === '1') return;
      btn.addEventListener('click', event => {
        event.preventDefault();
        syncMode(btn.getAttribute('data-generation-mode') || 'txt2img');
      });
      btn.dataset.neoBound = '1';
    });


    const modeSelect = $('generation-workflow-type');
    if (modeSelect && modeSelect.dataset.neoModeMirrorBound !== '1') {
      modeSelect.addEventListener('change', () => syncMode(modeSelect.value || 'txt2img', false));
      modeSelect.dataset.neoModeMirrorBound = '1';
    }

    ['generation-source-image', 'generation-mask-image', 'backend-low-vram-toggle'].forEach(id => {
      const el = $(id);
      if (!el || el.dataset.neoGuidanceBound === '1') return;
      el.addEventListener('change', () => window.setTimeout(() => applyModeAwareGuidance(), 0));
      el.dataset.neoGuidanceBound = '1';
    });
  }

  function mount() {
    const root = getRoot();
    const nav = $('generation-workspace-nav-panel');
    if (!root || !nav) return false;
    buildModeBar(nav);
    if (!buildShellLayout()) return false;
    bindEvents();
    syncMode(loadStored(MODE_STORAGE_KEY, $('generation-workflow-type')?.value || 'txt2img'), false);
    syncSetupTab(loadStored(SETUP_TAB_STORAGE_KEY, 'core'));
    window.requestAnimationFrame(() => {
      renderAllTabLanes();
      syncTopRail();
    });
    window.setTimeout(() => {
      renderAllTabLanes();
      syncTopRail();
    }, 160);
    window.neoGenerationSetSetupTab = syncSetupTab;
    window.neoGenerationSetMode = syncMode;
    window.neoGenerationApplyGoalHandoff = applyGoalHandoff;
    window.neoGenerationApplyRecipe = applyGoalRecipe;
    window.neoGenerationSyncTopRail = syncTopRail;
    setHidden($('generation-bottom-shell'), true);
    root.dataset.neoGenerationWorkspaceRouterMounted = 'true';
    return true;
  }

  function boot(attempt = 0) {
    if (mount()) return;
    if (attempt < 40) window.setTimeout(() => boot(attempt + 1), 140);
  }

  document.addEventListener('neo-generation-layout-mounted', () => {
    const root = getRoot();
    if (root) root.dataset.neoGenerationWorkspaceRouterMounted = '';
    window.setTimeout(() => boot(0), 60);
  });

  document.addEventListener('neo-generation-contracts-mounted', () => {
    window.requestAnimationFrame(() => {
      renderAllTabLanes();
      syncTopRail();
    });
  });

  document.addEventListener('neo-generation-goal-shell-mounted', () => {
    window.requestAnimationFrame(() => syncTopRail());
  });

  document.addEventListener('neo-generation-vram-panel-mounted', () => {
    window.requestAnimationFrame(() => syncTopRail());
  });

  window.addEventListener('load', () => {
    window.setTimeout(() => {
      renderAllTabLanes();
      syncTopRail();
    }, 220);
  });

  ready(() => boot(0));
})();
