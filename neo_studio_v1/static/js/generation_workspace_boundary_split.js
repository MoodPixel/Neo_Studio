(function () {
  function makeEl(tag, className = '', html = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html) el.innerHTML = html;
    return el;
  }

  function insertAfter(anchor, node) {
    if (!anchor || !node || !anchor.parentElement) return;
    if (anchor.nextSibling) anchor.parentElement.insertBefore(node, anchor.nextSibling);
    else anchor.parentElement.appendChild(node);
  }

  function openBoundaryTarget(tab, focusId = '') {
    if (typeof switchTab === 'function') switchTab(tab);
    else {
      const main = ['prompt', 'caption', 'library', 'settings'].includes(tab) ? 'manager' : tab;
      document.querySelector(`[data-main-tab="${main}"]`)?.click();
      if (['prompt', 'caption', 'library', 'settings'].includes(tab)) {
        document.querySelector(`#tab-manager [data-manager-subtab="${tab}"]`)?.click();
      }
    }
    if (focusId) {
      window.setTimeout(() => document.getElementById(focusId)?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 140);
    }
  }

  function ensureBoundaryPanel(parent, { id, badge = 'Quick use', title = '', copy = '', actions = [], insertAfterNode = null } = {}) {
    if (!parent || !id) return null;
    let panel = document.getElementById(id);
    if (!panel) {
      panel = makeEl('div', 'card-lite generation-boundary-panel');
      panel.id = id;
      panel.style.marginTop = '12px';
      panel.style.padding = '12px';
      panel.style.border = '1px solid rgba(59,130,246,0.18)';
      panel.style.background = 'rgba(15,23,42,0.18)';
      panel.innerHTML = `
        <div class="row-between" style="gap:12px; align-items:flex-start; flex-wrap:wrap;">
          <div>
            <div class="badge generation-boundary-badge"></div>
            <div class="accordion-title generation-boundary-title" style="font-size:14px; margin-top:8px;"></div>
            <div class="mini-note generation-boundary-copy" style="margin-top:6px;"></div>
          </div>
          <div class="row generation-boundary-actions" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;"></div>
        </div>`;
    }
    if (insertAfterNode) insertAfter(insertAfterNode, panel);
    else if (panel.parentElement !== parent) parent.insertBefore(panel, parent.firstChild || null);
    panel.querySelector('.generation-boundary-badge').textContent = badge;
    panel.querySelector('.generation-boundary-title').textContent = title;
    panel.querySelector('.generation-boundary-copy').textContent = copy;
    const actionHost = panel.querySelector('.generation-boundary-actions');
    if (actionHost) {
      actionHost.innerHTML = '';
      (actions || []).forEach(action => {
        const btn = makeEl('button', `btn btn-small${action.secondary ? ' btn-secondary' : ''}`);
        btn.type = 'button';
        btn.textContent = action.label || 'Open';
        if (action.title) btn.title = action.title;
        btn.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          action.onClick?.(event);
        });
        actionHost.appendChild(btn);
      });
    }
    return panel;
  }

  function applyPromptBoundarySplit(deps) {
    const { getRoot, $ } = deps;
    const promptCard = getRoot()?.querySelector('.generation-prompt-card');
    const header = promptCard?.querySelector(':scope > .row-between');
    if (!promptCard || !header) return;
    ensureBoundaryPanel(promptCard, {
      id: 'generation-prompt-boundary-panel',
      badge: 'Working copy',
      title: 'Generation keeps a live prompt draft here.',
      copy: 'Load or save from this shell, then open Prompt Studio, Caption Studio, or Library when you need full record editing, compare tools, or broader cleanup.',
      insertAfterNode: header,
      actions: [
        { label: 'Open Prompt Studio', onClick: () => openBoundaryTarget('prompt', 'tab-prompt') },
        { label: 'Open Caption Studio', secondary: true, onClick: () => openBoundaryTarget('caption', 'tab-caption') },
        { label: 'Open Library', secondary: true, onClick: () => openBoundaryTarget('library', 'tab-library') },
      ],
    });
    const quickBrowserBtn = $('btn-generation-prompt-manager-open');
    if (quickBrowserBtn) {
      quickBrowserBtn.title = 'Open quick prompt browser';
      quickBrowserBtn.setAttribute('aria-label', 'Open quick prompt browser');
    }
  }

  function applyResultsBoundarySplit() {
    const outputHost = document.getElementById('generation-output-tab-host');
    if (!outputHost) return;
    ensureBoundaryPanel(outputHost, {
      id: 'generation-results-boundary-panel',
      badge: 'Review + replay',
      title: 'Results stays focused on the active run.',
      copy: 'Inspect the selected output, replay metadata, and send images back into the workflow here. Open Library when you need the full Output Reuse archive or record maintenance.',
      actions: [
        { label: 'Open Output Reuse', onClick: () => openBoundaryTarget('library', 'neo-library-output-mode') },
        { label: 'Open Prompt Studio', secondary: true, onClick: () => openBoundaryTarget('prompt', 'tab-prompt') },
      ],
    });
  }

  function applyStyleQuickUseSplit(deps) {
    const { $, queryAccordion, updateAccordionText, ensureSubsectionShell, moveInto } = deps;
    const block = queryAccordion('generation-style-addons');
    const body = block?.querySelector(':scope > .accordion-body');
    if (!block || !body || body.dataset.neoQuickUseSplit === '1') return;
    updateAccordionText(block, 'Style Stack', 'Search the style library, add styles to the active stack, and open library tools only when you need to edit or import styles.');
    const actions = body.querySelector('.style-library-actions');
    const addBtn = $('btn-generation-style-add-selected');
    const management = ensureSubsectionShell(body, {
      id: 'generation-style-library-tools',
      title: 'Manage Style Library',
      hint: 'Edit the selected style, save new styles, duplicate or delete records, and handle CSV import / export only when you are maintaining the library.',
      open: false,
    });
    const searchRow = body.querySelector('.style-library-bar.grid.grid-2');
    const nameField = $('generation-style-name')?.closest('div');
    if (searchRow && nameField && nameField.parentElement === searchRow) {
      management.body.appendChild(nameField);
      searchRow.classList.remove('grid-2');
      searchRow.classList.add('grid-1');
    }
    const editState = $('generation-style-editing-state');
    const styleFields = $('generation-style-positive')?.closest('.grid.grid-1');
    moveInto(editState, management.body);
    moveInto(styleFields, management.body);
    if (actions && management.body) {
      const managementRow = makeEl('div', 'row style-library-actions');
      managementRow.style.marginTop = '10px';
      managementRow.style.flexWrap = 'wrap';
      managementRow.style.gap = '8px';
      ['btn-generation-style-apply', 'btn-generation-style-save', 'btn-generation-style-update', 'btn-generation-style-duplicate', 'btn-generation-style-delete', 'btn-generation-style-import', 'btn-generation-style-export']
        .map(id => $(id))
        .filter(Boolean)
        .forEach(btn => managementRow.appendChild(btn));
      const importFile = $('generation-style-import-file');
      moveInto(managementRow, management.body);
      moveInto(importFile, management.body);
      if (actions.children.length === 0) actions.remove();
    }
    if (addBtn) addBtn.textContent = 'Add to stack';
    body.dataset.neoQuickUseSplit = '1';
  }

  function applyKeywordQuickUseSplit(deps) {
    const { $, queryAccordion, updateAccordionText, setHidden } = deps;
    const block = document.querySelector('[data-generated-shell-for="generation-inline-keyword-tool"]') || queryAccordion('generation-keyword-insert');
    if (!block || block.dataset.neoQuickUseSplit === '1') return;
    updateAccordionText(block, 'Keyword Browser', 'Browse saved keywords and insert them into the prompt. Open the keyword manager only when you need library edits.');
    const manageBtn = $('btn-generation-keyword-manager-open');
    if (manageBtn) manageBtn.textContent = 'Open keyword manager';
    setHidden($('generation-keyword-manager-inline'), true);
    const advanced = document.querySelector('#generation-keyword-tool-host details.mini-advanced') || block.querySelector('details.mini-advanced');
    if (advanced) {
      advanced.open = false;
      const summary = advanced.querySelector(':scope > summary');
      if (summary) summary.textContent = 'Extra snippet sources';
    }
    block.dataset.neoQuickUseSplit = '1';
  }

  function applyLoraQuickUseSplit(deps) {
    const { $, queryAccordion, updateAccordionText, ensureSubsectionShell, moveInto } = deps;
    const block = queryAccordion('generation-lora-settings');
    const body = block?.querySelector(':scope > .accordion-body');
    const libraryShell = $('generation-lora-library-shell');
    if (!block || !body || !libraryShell || libraryShell.dataset.neoQuickUseSplit === '1') return;
    updateAccordionText(block, 'LoRA Stack', 'Search the library, add LoRAs to the active stack, and open selected-item details only when you need deeper metadata or maintenance tools.');
    const topbar = libraryShell.querySelector('.generation-lora-library-topbar');
    const topTitle = topbar?.querySelector('.generation-unit-title');
    const topHint = topbar?.querySelector('.accordion-hint');
    if (topTitle) topTitle.textContent = 'LoRA library quick add';
    if (topHint) topHint.textContent = 'Search the scanned library, pick a LoRA, and add it to the active stack.';
    const details = ensureSubsectionShell(libraryShell, {
      id: 'generation-lora-library-details-shell',
      title: 'Selected LoRA details',
      hint: 'Inspect previews, trigger words, sample prompts, scan paths, and metadata tools only when you need them.',
      open: false,
    });
    const topbarActions = topbar?.querySelector('.generation-lora-library-actions');
    const dirField = $('generation-lora-library-dir')?.closest('div');
    const scanBtn = $('btn-generation-lora-library-scan');
    const libraryGrid = libraryShell.querySelector('.generation-lora-library-grid');
    const optionShell = libraryShell.querySelector('.generation-lora-library-option-shell');
    const progressShell = $('generation-lora-library-progress-shell');
    const status = $('generation-lora-library-status');
    const maintenanceRow = makeEl('div', 'row generation-lora-library-actions generation-lora-library-actions-compact');
    maintenanceRow.style.marginTop = '0';
    maintenanceRow.style.flexWrap = 'wrap';
    maintenanceRow.style.gap = '8px';
    [topbarActions, scanBtn].filter(Boolean).forEach(node => maintenanceRow.appendChild(node));
    if (maintenanceRow.children.length) details.body.appendChild(maintenanceRow);
    moveInto(dirField, details.body);
    moveInto(libraryGrid, details.body);
    moveInto(optionShell, details.body);
    moveInto(progressShell, details.body);
    moveInto(status, details.body);
    const addBtn = $('btn-generation-lora-library-add-to-workflow');
    const refreshBtn = $('btn-generation-lora-library-refresh');
    if (addBtn) addBtn.textContent = 'Add to stack';
    if (refreshBtn) refreshBtn.textContent = 'Refresh';
    libraryShell.dataset.neoQuickUseSplit = '1';
  }

  function applyTiQuickUseSplit(deps) {
    const { $, queryAccordion, updateAccordionText, ensureSubsectionShell, moveInto } = deps;
    const block = queryAccordion('generation-ti-settings');
    const body = block?.querySelector(':scope > .accordion-body');
    if (!block || !body || body.dataset.neoQuickUseSplitTi === '1') return;
    updateAccordionText(block, 'Embeddings (TI Tokens)', 'Search scanned textual inversions, pick one, and append its token into the prompt. Open metadata and scan-path tools only when you need deeper details.');
    const topGrid = body.querySelector(':scope > .grid.grid-4');
    const dirField = $('generation-ti-library-dir')?.closest('div');
    const searchField = $('generation-ti-library-search')?.closest('div');
    const selectField = $('generation-ti-library-select')?.closest('div');
    const toolbar = $('btn-generation-ti-library-scan')?.parentElement;
    const previewGrid = body.querySelector('.generation-lora-library-grid');
    const status = $('generation-ti-library-status');
    const helperRow = $('btn-generation-ti-append-positive')?.parentElement;
    const scanBtn = $('btn-generation-ti-library-scan');
    const refreshBtn = $('btn-generation-ti-library-refresh');
    if (refreshBtn) refreshBtn.textContent = 'Refresh';
    if (scanBtn) scanBtn.textContent = 'Scan';
    const details = ensureSubsectionShell(body, {
      id: 'generation-ti-library-details-shell',
      title: 'Selected embedding details',
      hint: 'Inspect the preview, token metadata, example prompt, and scan-path settings only when you need to maintain the embedding library.',
      open: false,
    });
    if (topGrid && dirField && dirField.parentElement === topGrid) {
      details.body.appendChild(dirField);
      topGrid.classList.remove('grid-4');
      topGrid.classList.add('grid-3');
    }
    const quickActions = makeEl('div', 'row generation-lora-library-actions generation-lora-library-actions-compact');
    quickActions.style.marginTop = '12px';
    quickActions.style.justifyContent = 'flex-start';
    quickActions.style.flexWrap = 'wrap';
    quickActions.style.gap = '8px';
    [refreshBtn, $('btn-generation-ti-append-positive'), $('btn-generation-ti-append-negative')]
      .filter(Boolean)
      .forEach(btn => quickActions.appendChild(btn));
    if (quickActions.children.length && quickActions.parentElement !== body) body.insertBefore(quickActions, details.shell);
    const maintenanceRow = makeEl('div', 'row generation-lora-library-actions generation-lora-library-actions-compact');
    maintenanceRow.style.marginTop = '0';
    maintenanceRow.style.justifyContent = 'flex-start';
    maintenanceRow.style.flexWrap = 'wrap';
    maintenanceRow.style.gap = '8px';
    [scanBtn].filter(Boolean).forEach(btn => maintenanceRow.appendChild(btn));
    if (maintenanceRow.children.length) details.body.insertBefore(maintenanceRow, details.body.firstChild || null);
    moveInto(previewGrid, details.body);
    moveInto(status, details.body);
    if (toolbar && toolbar.children.length === 0) toolbar.remove();
    if (helperRow && helperRow !== quickActions && helperRow.children.length === 0) helperRow.remove();
    if (searchField && selectField && topGrid) {
      searchField.style.minWidth = '0';
      selectField.style.minWidth = '0';
    }
    body.dataset.neoQuickUseSplitTi = '1';
  }

  function applyCharacterQuickUseSplit(deps) {
    const { $, updateAccordionText, ensureSubsectionShell, moveInto } = deps;
    const block = document.querySelector('[data-generated-shell-for="generation-inline-character-tool"]');
    const body = block?.querySelector(':scope > .accordion-body');
    const host = $('generation-character-tool-host');
    const card = host?.querySelector(':scope > .card-lite');
    if (!block || !body || !host || !card || card.dataset.neoQuickUseSplit === '1') return;
    updateAccordionText(block, 'Character Builder', 'Build the active character block here and open saved-character controls only when you need to load, save, or delete library entries.');
    const management = ensureSubsectionShell(card, {
      id: 'generation-character-library-tools',
      title: 'Manage saved characters',
      hint: 'Save the current slot, load a saved character, or delete old entries only when you are maintaining the character library.',
      open: false,
    });
    const topActions = $('btn-neo-library-composer-character-refresh')?.parentElement;
    const linkBtn = $('btn-neo-library-composer-character-link');
    const savedGrid = $('neo-library-composer-character-name')?.closest('.grid.grid-2');
    const savedActionRow = $('btn-neo-library-composer-character-save')?.parentElement;
    const status = $('neo-library-composer-character-status');
    if (linkBtn) {
      linkBtn.textContent = 'Open bundle';
      linkBtn.classList.add('btn-secondary');
      management.body.appendChild(linkBtn);
    }
    ensureBoundaryPanel(management.body, {
      id: 'generation-character-library-boundary',
      badge: 'Manager surface',
      title: 'Saved characters live in Library.',
      copy: 'Use this inline builder to shape the active prompt slot. Jump to Library when you need broader browsing, cleanup, or bundle-level maintenance.',
      actions: [
        { label: 'Open Library', onClick: () => openBoundaryTarget('library', 'neo-library-composer-character-name') },
      ],
    });
    moveInto(savedGrid, management.body);
    moveInto(savedActionRow, management.body);
    moveInto(status, management.body);
    if (topActions && topActions.children.length === 0) topActions.remove();
    card.dataset.neoQuickUseSplit = '1';
  }

  function applyCaptionQuickUseSplit(deps) {
    const { $, queryAccordion, updateAccordionText, ensureSubsectionShell, moveInto } = deps;
    const outerBlock = document.querySelector('[data-generated-shell-for="generation-inline-captions"]');
    const innerBlock = queryAccordion('neo-library-caption-browser');
    const body = innerBlock?.querySelector(':scope > .accordion-body');
    const layout = body?.querySelector('.neo-library-caption-layout');
    const previewCard = layout?.querySelector('.neo-library-preview-card');
    const editorCard = layout?.querySelector('.card-lite:nth-child(2)');
    if (!outerBlock || !innerBlock || !body || !layout || !previewCard || !editorCard || editorCard.dataset.neoQuickUseSplit === '1') return;
    updateAccordionText(outerBlock, 'Caption Browser', 'Pick a saved caption, preview it, and send it back into Generation. Open record editing only when you need to maintain the caption library.');
    updateAccordionText(innerBlock, 'Caption Browser', 'Select a saved caption, preview the asset, and route prompt text or images into Generation without dragging full record editing into the main flow.');
    const management = ensureSubsectionShell(body, {
      id: 'generation-caption-browser-management',
      title: 'Manage saved caption',
      hint: 'Edit record metadata, notes, and library fields only when you need to maintain saved captions.',
      open: false,
    });
    const nameGrid = $('neo-library-caption-editor-name')?.closest('.grid.grid-2');
    const metaGrid = $('neo-library-caption-editor-style')?.closest('.grid.grid-4');
    const updatedNote = $('neo-library-caption-updated');
    const notesLabel = editorCard.querySelector('label[for="neo-library-caption-notes"]');
    const notesField = $('neo-library-caption-notes');
    const metaLabel = editorCard.querySelector('label[for="neo-library-caption-meta"]');
    const metaField = $('neo-library-caption-meta');
    const actionRow = $('btn-neo-library-caption-preview')?.parentElement;
    const updateBtn = $('btn-neo-library-caption-update');
    const deleteBtn = $('btn-neo-library-caption-delete');
    const managementActions = makeEl('div', 'row');
    managementActions.style.marginTop = '12px';
    managementActions.style.flexWrap = 'wrap';
    managementActions.style.gap = '8px';
    [updateBtn, deleteBtn].filter(Boolean).forEach(btn => managementActions.appendChild(btn));
    ensureBoundaryPanel(management.body, {
      id: 'generation-caption-library-boundary',
      badge: 'Manager surface',
      title: 'Saved captions live in Caption Studio and Library.',
      copy: 'Use this browser to preview, select, and route captions back into Generation. Jump out only when you need broader caption editing or archive cleanup.',
      actions: [
        { label: 'Open Caption Studio', onClick: () => openBoundaryTarget('caption', 'tab-caption') },
        { label: 'Open Library', secondary: true, onClick: () => openBoundaryTarget('library', 'tab-library') },
      ],
    });
    moveInto(nameGrid, management.body);
    moveInto(metaGrid, management.body);
    moveInto(updatedNote, management.body);
    moveInto(notesLabel, management.body);
    moveInto(notesField, management.body);
    moveInto(metaLabel, management.body);
    moveInto(metaField, management.body);
    if (managementActions.children.length) management.body.appendChild(managementActions);
    if (management.shell.parentElement !== body) body.appendChild(management.shell);
    layout.style.alignItems = 'start';
    previewCard.style.minHeight = '0';
    previewCard.style.height = '320px';
    previewCard.style.maxHeight = '320px';
    if (actionRow) {
      actionRow.style.flexWrap = 'wrap';
      actionRow.style.gap = '8px';
    }
    editorCard.dataset.neoQuickUseSplit = '1';
  }

  function applyQuickUseManagementSplit(deps) {
    const { getRoot } = deps;
    const root = getRoot();
    if (!root) return;
    applyPromptBoundarySplit(deps);
    applyStyleQuickUseSplit(deps);
    applyKeywordQuickUseSplit(deps);
    applyLoraQuickUseSplit(deps);
    applyTiQuickUseSplit(deps);
    applyCharacterQuickUseSplit(deps);
    applyCaptionQuickUseSplit(deps);
    applyResultsBoundarySplit(deps);
  }

  window.NeoGenerationWorkspaceBoundary = {
    applyQuickUseManagementSplit,
  };
})();
