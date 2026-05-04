(function () {
  const ROOT_SELECTOR = '#tab-generate';

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function makeSupportShell(title, copy, bodyEl, extraClass = '') {
    if (!bodyEl) return null;
    const shell = document.createElement('div');
    shell.className = `generation-support-card ${extraClass}`.trim();
    shell.innerHTML = `
      <div class="generation-support-card-header">
        <div>
          <div class="generation-support-title">${title}</div>
          <div class="generation-support-copy">${copy}</div>
        </div>
      </div>`;
    shell.appendChild(bodyEl);
    return shell;
  }

  function makeThumbRail(resultList) {
    if (!resultList) return null;
    const shell = document.createElement('div');
    shell.className = 'generation-live-thumbs-card';
    shell.innerHTML = `
      <div class="generation-live-strip-head">
        <div>
          <div class="generation-support-title">Current run outputs</div>
          <div class="generation-live-strip-note">Click a thumb to swap the main preview. Zoom stays on the main preview only.</div>
        </div>
      </div>`;
    shell.appendChild(resultList);
    return shell;
  }

  function markPromptCard(promptCard) {
    if (!promptCard) return;
    promptCard.classList.add('generation-prompt-card');
    const header = promptCard.querySelector(':scope > .row-between');
    if (header) header.classList.add('generation-prompt-card-header');
  }

  function moveNode(node, host) {
    if (node && host) host.appendChild(node);
  }

  function wrapHostInAccordion(host, { id='', title='', hint='', open=false } = {}) {
    if (!host || host.dataset.wrappedAccordion === 'true' || !host.children.length) return;
    const details = document.createElement('details');
    details.className = 'accordion-block generation-support-accordion';
    if (id) details.dataset.accordionId = id;
    details.dataset.defaultOpen = open ? 'true' : 'false';
    if (open) details.open = true;
    details.innerHTML = `
      <summary class="accordion-summary">
        <div>
          <div class="accordion-title">${title}</div>
          <div class="accordion-hint">${hint}</div>
        </div>
        <span class="accordion-chevron" aria-hidden="true">▾</span>
      </summary>`;
    const body = document.createElement('div');
    body.className = 'accordion-body';
    while (host.firstChild) body.appendChild(host.firstChild);
    details.appendChild(body);
    host.appendChild(details);
    host.dataset.wrappedAccordion = 'true';
    if (id === 'generation-workflow-wrap') {
      details.open = true;
      try { window.sessionStorage.setItem(`neo-studio-accordion:${id}`, 'true'); } catch (_) {}
    }
  }

  function promoteWorkflowNotesBlock(workflowCard) {
    if (!workflowCard || workflowCard.dataset.neoWorkflowNotesPromoted === '1') return;
    const label = workflowCard.querySelector('label[for="generation-workflow-notes"]');
    const textarea = $('generation-workflow-notes');
    const note = textarea?.nextElementSibling && textarea.nextElementSibling.classList?.contains('mini-note')
      ? textarea.nextElementSibling
      : null;
    if (!label || !textarea) return;
    const details = document.createElement('details');
    details.className = 'accordion-block generation-inline-accordion';
    details.dataset.accordionId = 'generation-workflow-notes-wrap';
    details.dataset.defaultOpen = 'false';
    details.style.marginTop = '14px';
    details.innerHTML = `
      <summary class="accordion-summary">
        <div>
          <div class="accordion-title">Workflow notes</div>
          <div class="accordion-hint">Project notes, reminders, future JSON ideas, and workflow-specific context.</div>
        </div>
        <span class="accordion-chevron" aria-hidden="true">▾</span>
      </summary>`;
    const body = document.createElement('div');
    body.className = 'accordion-body';
    label.remove();
    textarea.remove();
    body.appendChild(textarea);
    if (note) {
      note.remove();
      body.appendChild(note);
    }
    details.appendChild(body);
    workflowCard.appendChild(details);
    workflowCard.dataset.neoWorkflowNotesPromoted = '1';
  }

  function bindToolModal(buttonId, modalId, closeId) {
    const openBtn = $(buttonId);
    const modal = $(modalId);
    const closeBtn = $(closeId);
    if (!openBtn || !modal || openBtn.dataset.modalBound === '1') return;
    const open = () => {
      modal.classList.remove('hidden');
      modal.querySelectorAll('#generation-caption-browser-host').forEach(host => {
        host.style.display = '';
        host.style.marginTop = '0';
      });
      modal.querySelectorAll('details.accordion-block').forEach(block => {
        block.open = true;
        block.style.marginTop = '0';
      });
      document.body.classList.add('modal-open');
    };
    const close = () => {
      modal.classList.add('hidden');
      const anyOpen = Array.from(document.querySelectorAll('.modal-backdrop')).some(node => !node.classList.contains('hidden'));
      document.body.classList.toggle('modal-open', anyOpen);
    };
    openBtn.addEventListener('click', open);
    closeBtn?.addEventListener('click', close);
    modal.addEventListener('click', event => { if (event.target === modal) close(); });
    window.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
    openBtn.dataset.modalBound = '1';
  }

  function moveNodeToHost(node, host) {
    if (!node || !host) return;
    node.style.marginTop = '0';
    if (node.tagName === 'DETAILS') node.open = true;
    host.appendChild(node);
  }

  function moveAccordionBodyChildrenToHost(node, host) {
    if (!node || !host) return;
    const body = node.matches('details') ? node.querySelector(':scope > .accordion-body') : node;
    if (!body) return;
    while (body.firstChild) host.appendChild(body.firstChild);
    node.remove();
  }

  function mountPromptToolModals(promptCard) {
    if (!promptCard || promptCard.dataset.neoPromptToolModalsMounted === '1') return;
    moveAccordionBodyChildrenToHost(promptCard.querySelector('[data-accordion-id="generation-character-creator"]'), $('generation-character-tool-host'));
    moveAccordionBodyChildrenToHost(promptCard.querySelector('[data-accordion-id="generation-keyword-insert"]'), $('generation-keyword-tool-host'));
    bindToolModal('btn-generation-open-character-tool', 'generation-character-tool-modal', 'btn-close-generation-character-tool');
    bindToolModal('btn-generation-open-keyword-tool', 'generation-keyword-tool-modal', 'btn-close-generation-keyword-tool');
    bindToolModal('btn-generation-open-caption-tool', 'generation-caption-tool-modal', 'btn-close-generation-caption-tool');
    promptCard.dataset.neoPromptToolModalsMounted = '1';
  }

  function mountLayout() {
    const root = document.querySelector(ROOT_SELECTOR);
    if (!root || root.dataset.neoGenerationLayoutMounted === 'true') return;

    const setupRail = $('generation-setup-rail');
    const liveWorkspace = $('generation-live-workspace');
    const supportColumn = $('generation-support-column');
    const sessionColumn = $('generation-session-column');
    if (!setupRail || !liveWorkspace || !supportColumn || !sessionColumn) return;

    const globalPanel = root.querySelector('.generation-global-panel');
    const overviewGrid = globalPanel?.querySelector(':scope > .grid.grid-2');
    const summaryCard = globalPanel?.querySelector('.generation-summary-card');
    const actionsCard = globalPanel?.querySelector('.generation-actions-card');

    const foundationBar = $('generation-ux-foundation-bar');
    const headerAnchor = foundationBar && foundationBar.parentElement === globalPanel
      ? foundationBar
      : globalPanel?.querySelector(':scope > .row-between');
    const runtimeSummaryAnchor = $('generation-runtime-summary-anchor');

    if (summaryCard && globalPanel) {
      summaryCard.classList.add('generation-summary-card--compact');
      let compactHost = runtimeSummaryAnchor?.querySelector(':scope > .generation-header-meta-row') || null;
      if (!compactHost) {
        compactHost = document.createElement('div');
        compactHost.className = 'generation-header-meta-row';
      }
      compactHost.innerHTML = '';
      compactHost.appendChild(summaryCard);
      if (runtimeSummaryAnchor) runtimeSummaryAnchor.appendChild(compactHost);
      else if (headerAnchor) headerAnchor.insertAdjacentElement('afterend', compactHost);
      else globalPanel.appendChild(compactHost);
    }

    if (actionsCard) {
      actionsCard.classList.add('generation-actions-card--workspace');
      liveWorkspace.appendChild(actionsCard);
    }
    if (overviewGrid) overviewGrid.remove();

    const shellGrid = root.querySelector('.generation-shell-grid');
    const workflowCard = shellGrid?.children?.[0] || null;
    const promptCard = shellGrid?.children?.[1] || null;
    const workflowHost = document.createElement('div');
    workflowHost.id = 'generation-workflow-host';
    workflowHost.className = 'generation-support-host';

    moveNode(promptCard, setupRail);
    markPromptCard(promptCard);
    promoteWorkflowNotesBlock(workflowCard);

    const previewPanel = promptCard?.querySelector('.generation-preview-panel') || null;
    const previewLayout = previewPanel?.querySelector('.generation-preview-layout') || null;
    const outputSettings = previewLayout?.querySelector('.generation-output-settings') || null;
    const previewCard = previewLayout?.querySelector('.generation-preview-card') || null;
    const resultList = outputSettings?.querySelector('#generation-result-list') || null;

    if (previewCard) {
      previewCard.classList.add('generation-live-main-preview-card');
      liveWorkspace.appendChild(previewCard);
    }

    if (resultList) {
      const rail = makeThumbRail(resultList);
      if (rail) liveWorkspace.appendChild(rail);
    }

    if (outputSettings) {
      const wrapped = makeSupportShell(
        'Results & save details',
        'Choose the save folder and category, then keep the selected file path and metadata details nearby.',
        outputSettings,
        'generation-output-settings-card'
      );
      const host = $('generation-output-settings-host');
      if (wrapped && host) host.appendChild(wrapped);
    }

    if (previewPanel) previewPanel.remove();

    const outputSettingsHost = $('generation-output-settings-host');
    if (workflowCard && supportColumn) {
      workflowCard.classList.add('generation-workflow-card--relocated');
      workflowHost.appendChild(workflowCard);
      if (outputSettingsHost && supportColumn.contains(outputSettingsHost)) supportColumn.insertBefore(workflowHost, outputSettingsHost.nextSibling);
      else supportColumn.prepend(workflowHost);
    }

    const inspectorHost = $('generation-output-inspector-host');
    const reliabilityHost = $('generation-support-reliability-host');
    const smartHost = $('generation-support-smart-host');
    const powerHost = $('generation-support-power-host');
    if (outputSettingsHost && outputSettingsHost.parentElement === supportColumn) {
      if (reliabilityHost) supportColumn.insertBefore(reliabilityHost, outputSettingsHost);
      if (smartHost) supportColumn.insertBefore(smartHost, outputSettingsHost);
      if (powerHost) supportColumn.insertBefore(powerHost, outputSettingsHost);
    } else {
      moveNode(reliabilityHost, supportColumn);
      moveNode(smartHost, supportColumn);
      moveNode(powerHost, supportColumn);
    }
    moveNode(inspectorHost, supportColumn);

    moveNode($('generation-ux-warning-panel'), $('generation-support-reliability-host'));
    moveNode($('generation-smart-panel'), $('generation-support-smart-host'));
    moveNode($('generation-power-panel'), $('generation-support-power-host'));

    wrapHostInAccordion($('generation-workflow-host'), {
      id: 'generation-workflow-wrap',
      title: 'Core Generation',
      hint: 'Mode, model, size, prompts, and source setup.',
      open: true,
    });
    wrapHostInAccordion($('generation-output-settings-host'), {
      id: 'generation-output-settings-wrap',
      title: 'Results & save details',
      hint: 'Save path, category, and selected-file metadata.' ,
      open: false,
    });
    wrapHostInAccordion($('generation-support-reliability-host'), {
      id: 'generation-reliability-wrap',
      title: 'Reliability & clarity',
      hint: 'Warnings, checks, and safer setup guidance.',
      open: false,
    });
    wrapHostInAccordion($('generation-support-smart-host'), {
      id: 'generation-smart-wrap',
      title: 'Model intelligence & recipes',
      hint: 'Starter defaults, recipes, and guided setup.',
      open: false,
    });
    wrapHostInAccordion($('generation-support-power-host'), {
      id: 'generation-power-wrap',
      title: 'Compare & advanced tools',
      hint: 'A/B tests, compare sessions, and advanced reuse.',
      open: false,
    });

    mountPromptToolModals(promptCard);

    if (supportColumn && sessionColumn) {
      while (supportColumn.firstChild) sessionColumn.appendChild(supportColumn.firstChild);
      supportColumn.remove();
    }

    if (shellGrid) shellGrid.remove();
    root.classList.add('generation-layout-ready');
    root.dataset.neoGenerationLayoutMounted = 'true';
    document.dispatchEvent(new CustomEvent('neo-generation-layout-mounted', { detail: { rootSelector: ROOT_SELECTOR } }));
  }

  ready(() => {
    mountLayout();
    window.requestAnimationFrame(() => mountLayout());
    window.setTimeout(() => mountLayout(), 0);
  });
})();
