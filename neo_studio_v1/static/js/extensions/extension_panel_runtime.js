(function () {
  'use strict';

  const MANAGER_SLOT = 'image.extensions.manager';

  function asArray(value) { return Array.isArray(value) ? value.slice() : []; }
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function text(value) { return String(value == null ? '' : value).trim(); }

  function cssEscape(value) {
    const raw = text(value);
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(raw);
    return raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  function findMount(schema) {
    const mount = text(schema.mount || MANAGER_SLOT);
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
    const registry = window.NeoExternalExtensionState && typeof window.NeoExternalExtensionState.getRegistrySnapshot === 'function'
      ? window.NeoExternalExtensionState.getRegistrySnapshot()
      : { installed: [] };
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
    if (!renderer || typeof renderer.render !== 'function') return;
    const grouped = new Map();
    recordsWithSchemas().forEach(record => {
      const schema = asObject(record.ui_schema);
      const mountEl = findMount(schema);
      if (!mountEl) return;
      if (!grouped.has(mountEl)) grouped.set(mountEl, []);
      grouped.get(mountEl).push(record);
    });
    grouped.forEach((records, mountEl) => {
      const root = getPanelRoot(mountEl);
      if (!root) return;
      root.innerHTML = '';
      const intro = document.createElement('div');
      intro.className = 'mini-note';
      intro.innerHTML = '<strong>Schema-rendered extension panels</strong><div class="muted small" style="margin-top:4px;">Controls below are generated from extension manifests. Extensions define schema; Neo owns the rendering, state, and visibility.</div>';
      root.appendChild(intro);
      records.forEach(record => renderer.render(record, root));
      mountEl.dataset.neoSlotEmpty = records.length ? 'false' : 'true';
    });
  }

  function refreshSoon() {
    window.clearTimeout(refreshSoon._timer);
    refreshSoon._timer = window.setTimeout(render, 60);
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  window.NeoExtensionPanelRuntime = { render, refresh: refreshSoon };

  ready(() => {
    render();
    window.addEventListener('neo:external-extensions:registry-refreshed', refreshSoon);
    window.addEventListener('neo:external-extensions:state-changed', refreshSoon);
    window.addEventListener('neo:external-extension-store:changed', refreshSoon);
    window.addEventListener('neo:generation-workspace-changed', refreshSoon);
  });
})();
