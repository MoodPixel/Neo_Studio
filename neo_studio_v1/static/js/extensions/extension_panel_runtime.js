(function () {
  'use strict';

  const MANAGER_SLOT = 'image.extensions.manager';
  const SHELL_VERSION = 'standard-extension-shell-all-mount-paths-v2-section-mounts';
  const SHELL_SELECTOR = '[data-neo-standard-extension-shell="true"]';
  const RUNTIME_ROOT_SELECTOR = '[data-neo-extension-panel-runtime-root="true"]';
  const WRAPPABLE_PANEL_SELECTOR = [
    '[data-neo-external-extension-panel]',
    '[data-extension-id]',
    '[data-neo-extension-id]',
    '.neo-extension-panel',
    '.neo-extension-schema-card',
    '.layerdiffuse-panel'
  ].join(',');

  function asArray(value) { return Array.isArray(value) ? value.slice() : []; }
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function text(value) { return String(value == null ? '' : value).trim(); }
  function safeId(value) { return text(value).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'extension'; }
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function cssEscape(value) {
    const raw = text(value);
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(raw);
    return raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  function titleCase(value) {
    const cleaned = text(value).replace(/[._-]+/g, ' ');
    return cleaned ? cleaned.replace(/\b\w/g, c => c.toUpperCase()) : 'Extension';
  }

  function registrySnapshot() {
    return window.NeoExternalExtensionState && typeof window.NeoExternalExtensionState.getRegistrySnapshot === 'function'
      ? window.NeoExternalExtensionState.getRegistrySnapshot()
      : { installed: [] };
  }

  function coreSnapshot() {
    return window.NeoExternalExtensionState && typeof window.NeoExternalExtensionState.getSnapshot === 'function'
      ? window.NeoExternalExtensionState.getSnapshot()
      : {};
  }

  function findRecord(extensionId, panelId) {
    const wantedId = text(extensionId).toLowerCase();
    const wantedPanel = text(panelId);
    const registry = registrySnapshot();
    const records = asArray(registry.installed).concat(asArray(registry.enabled), asArray(registry.disabled), asArray(registry.invalid));
    return records.find(record => {
      const src = asObject(record);
      const id = text(src.extension_id || src.id).toLowerCase();
      const schema = asObject(src.ui_schema);
      const frontend = asObject(src.frontend);
      return (wantedId && id === wantedId)
        || (wantedPanel && (text(schema.panel_id) === wantedPanel || text(frontend.mount_id) === wantedPanel));
    }) || null;
  }

  function getStoreEntry(extensionId) {
    const store = window.NeoExtensionStateStore;
    return store && typeof store.getExtension === 'function' ? store.getExtension(extensionId) : null;
  }


  function activeImageWorkflowMode() {
    const api = window.NeoImageState;
    if (api && typeof api.getState === 'function') {
      try {
        const snapshot = asObject(api.getState());
        return text(snapshot.workflow_type || snapshot.mode || '');
      } catch (_) {}
    }
    return text(document.getElementById('generation-workflow-type')?.value || '');
  }


  function compatibilityMeta(extensionId, validation, effective) {
    const core = coreSnapshot();
    const id = text(extensionId).toLowerCase();
    const fromCore = asObject(asObject(asObject(core.compatibility).results)[id]);
    return asObject(effective.compatibility || validation.compatibility || fromCore);
  }

  function compatibilityForRecord(record) {
    const core = coreSnapshot();
    const id = text(asObject(record).extension_id || asObject(record).id).toLowerCase();
    return asObject(asObject(asObject(core.compatibility).results)[id]);
  }

  function slotFromMountMeta(meta) {
    const mount = asObject(meta);
    return text(mount.slot || mount.mount || mount.mount_point || '');
  }

  function sectionMountForRecord(record) {
    const src = asObject(record);
    const compat = compatibilityForRecord(src);
    const primarySlot = slotFromMountMeta(compat.primary_mount);
    if (primarySlot) return primarySlot;
    const schema = asObject(src.ui_schema);
    const schemaMount = text(schema.mount || src.mount_point || src.mount);
    return schemaMount || MANAGER_SLOT;
  }

  function messageList(value) {
    return asArray(value).map(item => typeof item === 'string' ? item : text(item.message || item.code)).filter(Boolean);
  }

  function resolveExtensionId(panel) {
    if (!panel) return '';
    const explicit = text(panel.dataset.extensionId || panel.dataset.neoExtensionId || panel.dataset.neoExternalExtensionPanel || panel.getAttribute('data-extension-id'));
    if (explicit) return explicit.toLowerCase();
    const panelId = text(panel.id);
    const record = findRecord('', panelId);
    return text(record?.extension_id || record?.id).toLowerCase();
  }

  function resolveShellMeta(extensionId, panel) {
    const record = findRecord(extensionId, panel?.id) || {};
    const storeEntry = getStoreEntry(extensionId) || {};
    const core = coreSnapshot();
    const raw = asObject(core.raw && core.raw[extensionId] || storeEntry.raw_state);
    const effective = asObject(core.effective && core.effective[extensionId] || storeEntry.effective_state);
    const validation = asObject(storeEntry.validation || core.validation_state?.[extensionId] || effective.workflow_validation);
    const compat = compatibilityMeta(extensionId, validation, effective);
    const warnings = asArray(validation.warnings).concat(asArray(record.warnings), asArray(effective.warnings), messageList(compat.warnings));
    const compatReason = text(compat.disabled_message || compat.disabled_reason || '');
    const errors = asArray(validation.errors).concat(validation.disabled_reason ? [validation.disabled_reason] : []).concat(effective.disabled_reason ? [effective.disabled_reason] : []).concat(compat.blocked && compatReason ? [compatReason] : []);
    const enabled = !!raw.enabled || !!storeEntry.enabled || !!effective.enabled || !!effective.effective_enabled || !!record.enabled;
    const active = !!effective.effective_enabled || (!!enabled && !errors.length && text(record.status).toLowerCase() !== 'invalid');
    const activeWorkflow = text(effective.active_image_workflow?.workflow_type || effective.active_image_workflow?.mode || activeImageWorkflowMode());
    const workflowMode = text(effective.workflow_mode || effective.workflow || raw.workflow_mode || compat.workflow || record.workflow_mode || record.workflow?.mode || '');
    const outputPolicy = text(effective.output_policy || raw.output_policy || record.output_policy?.[0] || record.output?.policy || '');
    const target = text(effective.output_target || raw.output_target || asArray(compat.targets).join(', ') || record.output_target || record.target_surface || record.surface || '');
    const primary = text(effective.primary_output_type || record.output?.primary_type || record.output_visibility?.primary_type || '');
    const batch = text(effective.batch_policy || record.batch_policy || '');
    return {
      extensionId,
      title: text(record.panel_title || record.title || record.name || panel?.getAttribute('aria-label') || titleCase(extensionId)),
      subtitle: extensionId,
      enabled,
      active,
      dirty: !!storeEntry.dirty,
      status: errors.length ? 'Blocked' : compat.status ? titleCase(compat.status) : active ? 'Ready' : enabled ? 'Pending' : 'Disabled',
      disabledReason: text(validation.disabled_reason || effective.disabled_reason || compatReason || record.disabled_reason || ''),
      warnings: [...new Set(warnings.map(text).filter(Boolean))],
      errors: [...new Set(errors.map(text).filter(Boolean))],
      chips: [
        enabled ? 'Enabled' : 'Disabled',
        errors.length ? 'Blocked' : active ? 'Ready' : '',
        target ? `Target: ${target}` : '',
        outputPolicy ? `Output: ${outputPolicy}` : '',
        activeWorkflow ? `Active: ${activeWorkflow}` : '',
        workflowMode ? `Ext mode: ${workflowMode}` : '',
        compat.family ? `Family: ${compat.family}` : '',
        compat.status ? `Compat: ${compat.status}` : '',
        primary ? `Primary: ${primary}` : '',
        batch ? `Batch: ${batch}` : '',
        storeEntry.dirty ? 'Dirty' : ''
      ].filter(Boolean)
    };
  }

  function renderShellHeader(shell, panel) {
    const extensionId = text(shell.dataset.neoExtensionId || resolveExtensionId(panel));
    if (!extensionId) return;
    const meta = resolveShellMeta(extensionId, panel);
    shell.dataset.neoExtensionId = extensionId;
    shell.dataset.neoStandardExtensionShellVersion = SHELL_VERSION;
    shell.dataset.neoExtensionEnabled = meta.enabled ? 'true' : 'false';
    shell.dataset.neoExtensionStatus = safeId(meta.status);
    const header = shell.querySelector(':scope > .neo-extension-standard-shell__header');
    if (!header) return;
    const notices = [];
    if (meta.errors.length) notices.push(`<div class="neo-extension-standard-shell__notice is-error">${escapeHtml(meta.errors[0])}</div>`);
    else if (meta.disabledReason) notices.push(`<div class="neo-extension-standard-shell__notice is-error">${escapeHtml(meta.disabledReason)}</div>`);
    if (meta.warnings.length) notices.push(`<div class="neo-extension-standard-shell__notice is-warning">${escapeHtml(meta.warnings[0])}</div>`);
    if (meta.dirty) notices.push('<div class="neo-extension-standard-shell__notice is-info">Settings changed. Refresh validation before running.</div>');
    header.innerHTML = `
      <button class="neo-extension-standard-shell__toggle" type="button" aria-expanded="${shell.dataset.neoShellCollapsed === 'true' ? 'false' : 'true'}" aria-controls="${escapeHtml(shell.querySelector(':scope > .neo-extension-standard-shell__body')?.id || '')}">
        <span class="neo-extension-standard-shell__chevron" aria-hidden="true"></span>
        <span class="neo-extension-standard-shell__title-group">
          <span class="neo-extension-standard-shell__title">${escapeHtml(meta.title)}</span>
          <span class="neo-extension-standard-shell__subtitle">${escapeHtml(meta.subtitle)}</span>
        </span>
      </button>
      <div class="neo-extension-standard-shell__chips">${meta.chips.map(chip => `<span class="neo-extension-standard-shell__chip">${escapeHtml(chip)}</span>`).join('')}</div>
      ${notices.length ? `<div class="neo-extension-standard-shell__notices">${notices.join('')}</div>` : ''}
    `;
    const toggle = header.querySelector('.neo-extension-standard-shell__toggle');
    toggle?.addEventListener('click', () => toggleShell(shell));
  }

  function collapseKey(extensionId) {
    return `neo.extension.shell.collapsed.${safeId(extensionId)}`;
  }

  function setCollapsed(shell, collapsed) {
    const extensionId = text(shell.dataset.neoExtensionId);
    shell.dataset.neoShellCollapsed = collapsed ? 'true' : 'false';
    shell.classList.toggle('is-collapsed', !!collapsed);
    const body = shell.querySelector(':scope > .neo-extension-standard-shell__body');
    const toggle = shell.querySelector(':scope > .neo-extension-standard-shell__header .neo-extension-standard-shell__toggle');
    if (body) body.hidden = !!collapsed;
    if (toggle) toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    if (extensionId) {
      try { window.localStorage.setItem(collapseKey(extensionId), collapsed ? 'true' : 'false'); } catch (_) {}
    }
  }

  function toggleShell(shell) {
    setCollapsed(shell, shell.dataset.neoShellCollapsed !== 'true');
  }

  function initialCollapsed(extensionId) {
    try {
      const stored = window.localStorage.getItem(collapseKey(extensionId));
      if (stored === 'true') return true;
      if (stored === 'false') return false;
    } catch (_) {}
    return false;
  }

  function shouldWrap(child) {
    if (!child || child.nodeType !== 1) return false;
    if (child.matches(SHELL_SELECTOR) || child.matches(RUNTIME_ROOT_SELECTOR)) return false;
    if (['SCRIPT', 'STYLE', 'TEMPLATE', 'LINK'].includes(child.tagName)) return false;
    if (!child.matches(WRAPPABLE_PANEL_SELECTOR)) return false;
    if (child.closest(SHELL_SELECTOR)) return false;
    return !!resolveExtensionId(child);
  }

  function wrapPanel(panel) {
    if (!shouldWrap(panel)) return null;
    const extensionId = resolveExtensionId(panel);
    const parent = panel.parentElement;
    if (!parent) return null;
    const shell = document.createElement('section');
    shell.className = 'neo-extension-standard-shell';
    shell.dataset.neoStandardExtensionShell = 'true';
    shell.dataset.neoExtensionId = extensionId;
    shell.dataset.neoExtensionShellSource = 'forced_mount_path';
    const bodyId = `neo-extension-shell-body-${safeId(extensionId)}`;
    const header = document.createElement('header');
    header.className = 'neo-extension-standard-shell__header';
    const body = document.createElement('div');
    body.className = 'neo-extension-standard-shell__body';
    body.id = bodyId;
    parent.insertBefore(shell, panel);
    body.appendChild(panel);
    shell.appendChild(header);
    shell.appendChild(body);
    renderShellHeader(shell, panel);
    setCollapsed(shell, initialCollapsed(extensionId));
    return shell;
  }

  function refreshShell(shell) {
    if (!shell || !shell.matches(SHELL_SELECTOR)) return;
    const panel = shell.querySelector(':scope > .neo-extension-standard-shell__body > *');
    renderShellHeader(shell, panel);
    setCollapsed(shell, shell.dataset.neoShellCollapsed === 'true');
  }

  function forceStandardShells(root = document) {
    const candidates = [];
    if (root && root.nodeType === 1 && shouldWrap(root)) candidates.push(root);
    const searchRoot = root && (root.querySelectorAll ? root : document);
    searchRoot.querySelectorAll?.(WRAPPABLE_PANEL_SELECTOR).forEach(node => {
      if (shouldWrap(node)) candidates.push(node);
    });
    candidates.forEach(wrapPanel);
    document.querySelectorAll(SHELL_SELECTOR).forEach(refreshShell);
  }

  function findMount(schema, record = {}) {
    const mount = sectionMountForRecord(record) || text(asObject(schema).mount || MANAGER_SLOT);
    const safeMount = cssEscape(mount);
    return document.querySelector(`[data-neo-external-extension-slot="${safeMount}"], [data-neo-extension-slot="${safeMount}"]`)
      || document.getElementById('neo-ext-slot-image-extensions-manager');
  }

  function getPanelRoot(mountEl) {
    if (!mountEl) return null;
    let root = mountEl.querySelector(':scope > [data-neo-extension-panel-runtime-root="true"]');
    if (!root) {
      root = document.createElement('div');
      root.dataset.neoExtensionPanelRuntimeRoot = 'true';
      root.className = 'neo-extension-panel-runtime-root';
      root.style.marginTop = '12px';
      mountEl.appendChild(root);
    }
    return root;
  }

  function recordsWithSchemas() {
    const registry = registrySnapshot();
    if (window.NeoExtensionStateStore && typeof window.NeoExtensionStateStore.applyRegistry === 'function') {
      window.NeoExtensionStateStore.applyRegistry(registry, { silent: true });
    }
    return asArray(registry.installed).filter(record => {
      const schema = asObject(record.ui_schema);
      return schema && Array.isArray(schema.sections) && schema.sections.length;
    });
  }

  function render() {
    const renderer = window.NeoExtensionUiSchemaRenderer;
    const grouped = new Map();
    if (renderer && typeof renderer.render === 'function') {
      recordsWithSchemas().forEach(record => {
        const schema = asObject(record.ui_schema);
        const mountEl = findMount(schema, record);
        if (!mountEl) return;
        if (!grouped.has(mountEl)) grouped.set(mountEl, []);
        grouped.get(mountEl).push(record);
      });
      grouped.forEach((records, mountEl) => {
        const root = getPanelRoot(mountEl);
        if (!root) return;
        root.innerHTML = '';
        records.forEach(record => renderer.render(record, root));
        mountEl.dataset.neoSlotEmpty = records.length ? 'false' : 'true';
      });
    }
    forceStandardShells(document);
  }

  function refreshSoon() {
    window.clearTimeout(refreshSoon._timer);
    refreshSoon._timer = window.setTimeout(render, 60);
  }

  function observeMountPaths() {
    const observer = new MutationObserver(mutations => {
      let shouldRefresh = false;
      mutations.forEach(mutation => {
        mutation.addedNodes.forEach(node => {
          if (node && node.nodeType === 1) {
            if (shouldWrap(node) || node.querySelector?.(WRAPPABLE_PANEL_SELECTOR)) shouldRefresh = true;
          }
        });
      });
      if (shouldRefresh) refreshSoon();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  window.NeoExtensionPanelRuntime = {
    render,
    refresh: refreshSoon,
    forceStandardShells,
    SHELL_VERSION
  };

  ready(() => {
    render();
    observeMountPaths();
    window.addEventListener('neo:external-extensions:registry-refreshed', refreshSoon);
    window.addEventListener('neo:external-extensions:state-changed', refreshSoon);
    window.addEventListener('neo:external-extensions:validated', refreshSoon);
    window.addEventListener('neo:external-extension-store:changed', refreshSoon);
    window.addEventListener('neo:generation-workspace-changed', refreshSoon);
  });
})();
