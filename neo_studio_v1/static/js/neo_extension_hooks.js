(function () {
  'use strict';

  const state = {
    panels: new Map(),
    toolbarButtons: new Map(),
    sidebarItems: new Map(),
    loadedScripts: new Set(),
    loadedStyles: new Set(),
    mounted: new Set(),
  };

  function slug(value) {
    return String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  }

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function findSlot(surface, mountType, mountPoint) {
    const normalizedSurface = slug(surface);
    const normalizedMount = slug(mountType);
    const selectors = [];
    if (mountPoint) {
      selectors.push(`[data-neo-extension-slot="${mountPoint}"]`);
      selectors.push(`#${CSS.escape(mountPoint)}`);
    }
    selectors.push(`[data-neo-extension-slot="${normalizedSurface}.${normalizedMount}"]`);
    selectors.push(`[data-neo-extension-slot="${normalizedSurface}_${normalizedMount}"]`);
    selectors.push(`[data-neo-surface="${normalizedSurface}"][data-neo-extension-mount="${normalizedMount}"]`);
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (node) return node;
    }
    return null;
  }

  function createFallbackSlot(surface, mountType) {
    const id = `neo-extension-${slug(surface || 'global')}-${slug(mountType || 'panel')}-slot`;
    let node = document.getElementById(id);
    if (node) return node;
    node = document.createElement('section');
    node.id = id;
    node.className = 'neo-extension-slot neo-extension-slot--fallback';
    node.dataset.neoExtensionSlot = `${slug(surface || 'global')}.${slug(mountType || 'panel')}`;
    node.innerHTML = `<div class="neo-extension-slot__header">Extensions</div>`;
    document.body.appendChild(node);
    return node;
  }

  function makePanelShell(config) {
    const shell = document.createElement('section');
    shell.className = 'neo-extension-panel';
    shell.dataset.extensionId = config.extension_id || config.id || '';
    shell.dataset.mountType = config.mount_type || 'panel';
    shell.innerHTML = `
      <header class="neo-extension-panel__header">
        <strong>${config.panel_title || config.name || config.id || 'Extension'}</strong>
        <span>${config.version || ''}</span>
      </header>
      <div class="neo-extension-panel__body" data-neo-extension-body></div>
    `;
    return shell;
  }

  function normalizeConfig(config) {
    return Object.assign({
      id: config.extension_id || config.id,
      extension_id: config.extension_id || config.id,
      mount_type: config.mount_type || 'panel',
      target_surface: config.target_surface || 'global',
      mount_point: config.mount_point || '',
    }, config || {});
  }

  function registerPanel(id, config) {
    const panel = normalizeConfig(Object.assign({}, config || {}, { id, extension_id: id }));
    state.panels.set(id, panel);
    mountPanel(panel);
    emit('neo:extension-panel-registered', panel);
    return panel;
  }

  function registerToolbarButton(id, config) {
    const button = normalizeConfig(Object.assign({}, config || {}, { id, extension_id: id, mount_type: 'toolbar' }));
    state.toolbarButtons.set(id, button);
    mountToolbarButton(button);
    emit('neo:extension-toolbar-registered', button);
    return button;
  }

  function registerSidebarItem(id, config) {
    const item = normalizeConfig(Object.assign({}, config || {}, { id, extension_id: id, mount_type: 'sidebar' }));
    state.sidebarItems.set(id, item);
    mountSidebarItem(item);
    emit('neo:extension-sidebar-registered', item);
    return item;
  }

  function mountPanel(config) {
    const key = `panel:${config.extension_id}`;
    if (state.mounted.has(key)) return;
    const slot = findSlot(config.target_surface, 'panel', config.mount_point) || createFallbackSlot(config.target_surface, 'panel');
    const shell = makePanelShell(config);
    const body = shell.querySelector('[data-neo-extension-body]');
    slot.appendChild(shell);
    state.mounted.add(key);
    if (typeof config.render === 'function') {
      config.render(body, { config, NeoExtensions: window.NeoExtensions });
    }
    emit('neo:extension-panel-mounted', { config, shell, body });
  }

  function mountToolbarButton(config) {
    const key = `toolbar:${config.extension_id}`;
    if (state.mounted.has(key)) return;
    const slot = findSlot(config.target_surface, 'toolbar', config.mount_point) || createFallbackSlot(config.target_surface, 'toolbar');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'neo-extension-toolbar-button';
    button.textContent = config.label || config.name || config.extension_id;
    button.addEventListener('click', () => {
      if (typeof config.onClick === 'function') config.onClick({ config, NeoExtensions: window.NeoExtensions });
      emit('neo:extension-toolbar-click', { config });
    });
    slot.appendChild(button);
    state.mounted.add(key);
  }

  function mountSidebarItem(config) {
    const key = `sidebar:${config.extension_id}`;
    if (state.mounted.has(key)) return;
    const slot = findSlot(config.target_surface, 'sidebar', config.mount_point) || createFallbackSlot(config.target_surface, 'sidebar');
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'neo-extension-sidebar-item';
    item.textContent = config.label || config.name || config.extension_id;
    item.addEventListener('click', () => {
      if (typeof config.onClick === 'function') config.onClick({ config, NeoExtensions: window.NeoExtensions });
      emit('neo:extension-sidebar-click', { config });
    });
    slot.appendChild(item);
    state.mounted.add(key);
  }

  function loadStyle(url) {
    if (!url || state.loadedStyles.has(url)) return Promise.resolve();
    state.loadedStyles.add(url);
    return new Promise((resolve, reject) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = url;
      link.onload = resolve;
      link.onerror = reject;
      document.head.appendChild(link);
    });
  }

  function loadScript(url) {
    if (!url || state.loadedScripts.has(url)) return Promise.resolve();
    state.loadedScripts.add(url);
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = url;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async function loadSurface(surface) {
    const query = surface ? `?target_surface=${encodeURIComponent(surface)}&enabled_only=true` : '?enabled_only=true';
    const response = await fetch(`/api/extensions/frontend-hooks${query}`);
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.message || 'Could not load extension hooks');
    for (const hook of payload.hooks || []) {
      await loadStyle(hook.entry_css_url);
      await loadScript(hook.entry_js_url);
      emit('neo:extension-hook-loaded', hook);
    }
    return payload;
  }

  window.NeoExtensions = Object.assign(window.NeoExtensions || {}, {
    state,
    registerPanel,
    registerToolbarButton,
    registerSidebarItem,
    mountPanel,
    mountToolbarButton,
    mountSidebarItem,
    loadSurface,
    loadScript,
    loadStyle,
  });

  document.addEventListener('DOMContentLoaded', () => {
    const boot = window.NEO_BOOT_DATA || window.__NEO_BOOT_DATA__ || {};
    const surface = document.body && document.body.dataset ? document.body.dataset.neoSurface : '';
    if (boot.autoLoadExtensionHooks !== false) {
      loadSurface(surface || '').catch((error) => {
        console.warn('[NeoExtensions] frontend hook load failed', error);
      });
    }
  });
})();
