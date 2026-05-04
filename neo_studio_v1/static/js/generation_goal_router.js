(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const STORAGE_KEY = 'neo_generation_workspace_mode_v1';

  const WORKSPACES = {
    txt2img: {
      title: 'Txt2img',
      badge: 'Text → Image',
      copy: 'Start from prompts only. Best for fresh image builds and clean composition planning.',
      tone: 'primary',
      setupTab: 'core',
    },
    img2img: {
      title: 'Img2img',
      badge: 'Image → Image',
      copy: 'Drive the run from a source image when you want variations, redraws, or guided rework.',
      tone: 'specialty',
      setupTab: 'core',
    },
    inpaint: {
      title: 'Inpaint',
      badge: 'Repair Area',
      copy: 'Target a masked region for repairs, cleanup, object removal, or local redraw work.',
      tone: 'warning',
      setupTab: 'guide',
    },
    outpaint: {
      title: 'Outpaint',
      badge: 'Expand Canvas',
      copy: 'Extend the image outward when you need more framing, breathing room, or scene continuation.',
      tone: 'recovery',
      setupTab: 'guide',
    },
  };

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function persist(mode) {
    try { window.localStorage.setItem(STORAGE_KEY, mode); } catch (_) {}
  }

  function loadStoredMode() {
    try { return window.localStorage.getItem(STORAGE_KEY) || ''; } catch (_) { return ''; }
  }

  function currentMode() {
    return $('generation-workflow-type')?.value || loadStoredMode() || 'txt2img';
  }

  function ensureShell() {
    const anchor = $('generation-setup-goal-anchor');
    if (!anchor) return null;
    let shell = $('generation-goal-shell');
    let created = false;
    if (!shell) {
      shell = document.createElement('div');
      shell.id = 'generation-goal-shell';
      shell.className = 'panel generation-goal-shell';
      shell.innerHTML = `
        <div class="generation-goal-head row-between">
          <div>
            <h3 style="margin:0;">Image workspace</h3>
            <div class="muted small" id="generation-goal-copy">Pick the real image mode here so the lower build area stops carrying a second visible mode selector.</div>
          </div>
          <div class="generation-goal-head-actions">
            <span class="badge" id="generation-goal-active-badge">Text → Image</span>
          </div>
        </div>
        <div class="generation-mode-tabbar generation-shell-workspace-tabbar" id="generation-shell-workspace-tabbar" role="tablist" aria-label="Image workspaces">
          <button class="active" data-generation-shell-workspace="txt2img" type="button">Text → Image</button>
          <button data-generation-shell-workspace="img2img" type="button">Image → Image</button>
          <button data-generation-shell-workspace="inpaint" type="button">Repair Area</button>
          <button data-generation-shell-workspace="outpaint" type="button">Expand Canvas</button>
        </div>
        <div class="generation-goal-summary" id="generation-goal-summary"></div>`;
      created = true;
    }
    if (shell.parentElement !== anchor) anchor.appendChild(shell);
    shell.dataset.generationShellRegion = 'top-shell';
    if (created) document.dispatchEvent(new CustomEvent('neo-generation-goal-shell-mounted'));
    return shell;
  }

  function renderSummary(mode) {
    const payload = WORKSPACES[mode] || WORKSPACES.txt2img;
    const summary = $('generation-goal-summary');
    const badge = $('generation-goal-active-badge');
    const copy = $('generation-goal-copy');
    if (badge) badge.textContent = payload.badge;
    if (copy) copy.textContent = payload.copy;
    if (summary) {
      summary.innerHTML = `
        <details class="generation-goal-summary-shell" open>
          <summary class="generation-goal-summary-bar">
            <div class="generation-goal-summary-main">
              <div class="generation-goal-summary-title">${payload.title}</div>
              <div class="generation-goal-summary-copy">${payload.copy}</div>
            </div>
            <div class="generation-goal-summary-inline">
              <span class="generation-goal-mini-pill is-primary">Workspace</span>
              <span class="generation-goal-mini-pill is-success" style="text-transform:none;">${payload.badge}</span>
            </div>
          </summary>
        </details>`;
    }
  }

  function syncButtons(mode) {
    document.querySelectorAll('[data-generation-shell-workspace]').forEach(btn => {
      const active = btn.getAttribute('data-generation-shell-workspace') === mode;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function applyWorkspace(mode, { persistMode = true, fromSync = false } = {}) {
    const next = WORKSPACES[mode] ? mode : 'txt2img';
    const payload = WORKSPACES[next];
    syncButtons(next);
    renderSummary(next);

    if (!fromSync) {
      if (typeof window.neoGenerationSetMode === 'function') window.neoGenerationSetMode(next);
      else {
        const select = $('generation-workflow-type');
        if (select && select.value !== next) {
          select.value = next;
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      if (typeof window.neoGenerationSetSetupTab === 'function' && payload.setupTab) {
        window.neoGenerationSetSetupTab(payload.setupTab);
      }
    }

    if (persistMode) persist(next);

    document.dispatchEvent(new CustomEvent('neo-generation-goal-changed', { detail: { goalId: next, mode: next, payload } }));
    document.dispatchEvent(new CustomEvent('neo-generation-workspace-changed', { detail: { mode: next, payload } }));
  }

  function bind() {
    const shell = ensureShell();
    if (!shell) return false;
    shell.querySelectorAll('[data-generation-shell-workspace]').forEach(btn => {
      if (btn.dataset.neoBound === '1') return;
      btn.addEventListener('click', event => {
        event.preventDefault();
        applyWorkspace(btn.getAttribute('data-generation-shell-workspace') || 'txt2img');
      });
      btn.dataset.neoBound = '1';
    });

    const select = $('generation-workflow-type');
    if (select && select.dataset.neoWorkspaceShellBound !== '1') {
      select.addEventListener('change', () => applyWorkspace(select.value || 'txt2img', { persistMode: true, fromSync: true }));
      select.dataset.neoWorkspaceShellBound = '1';
    }

    const initial = WORKSPACES[currentMode()] ? currentMode() : 'txt2img';
    applyWorkspace(initial, { persistMode: false, fromSync: true });
    return true;
  }

  function boot(attempt = 0) {
    if (bind()) return;
    if (attempt < 40) window.setTimeout(() => boot(attempt + 1), 120);
  }

  document.addEventListener('neo-generation-layout-mounted', () => window.setTimeout(() => boot(0), 120));
  ready(() => boot(0));
})();
