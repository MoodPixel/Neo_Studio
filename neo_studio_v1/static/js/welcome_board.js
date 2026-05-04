(function(){
  const boot = window.NEO_STUDIO_BOOT || {};
  const cache = window.NeoAppSettingsCache = window.NeoAppSettingsCache || JSON.parse(JSON.stringify(boot.appSettings || {}));
  const recentTotals = boot.recentTotals || {};
  let persistTimer = null;

  function ensureStartupShape(){
    if (!cache.startup || typeof cache.startup !== 'object') cache.startup = {};
    if (!cache.ui || typeof cache.ui !== 'object') cache.ui = {};
    if (!cache.startup.last_open_surface) cache.startup.last_open_surface = 'generate';
    if (typeof cache.startup.show_welcome_on_launch !== 'boolean') cache.startup.show_welcome_on_launch = true;
    return cache;
  }

  function welcomeModal(){ return $('welcome-board-modal'); }
  function openWelcomeBoard(){
    const modal = welcomeModal();
    if (!modal) return;
    renderWelcomeBoard();
    modal.classList.remove('hidden');
    document.body.classList.add('modal-open');
  }
  function closeWelcomeBoard(){
    const modal = welcomeModal();
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.classList.remove('modal-open');
  }


  function getBootSurface(surfaceId){
    return (Array.isArray(boot.surfaceDefinitions) ? boot.surfaceDefinitions : []).find(surface => String(surface?.id || '') === String(surfaceId || '')) || null;
  }

  function resolveSurfaceLabel(surfaceId){
    const target = String(surfaceId || 'generate');
    const registryLabel = window.NeoSurfaceRegistry?.getSurface?.(target)?.label;
    if (registryLabel) return String(registryLabel);
    const bootLabel = getBootSurface(target)?.label;
    if (bootLabel) return String(bootLabel);
    return target === 'generate' ? 'Image' : target;
  }


  function formatCountStat(label, value){
    const safe = Number.isFinite(Number(value)) ? Number(value) : 0;
    return `${label} · ${safe}`;
  }

  function getWelcomeCardStat(surfaceId){
    const target = String(surfaceId || '');
    if (target === 'generate') return formatCountStat('Metadata', recentTotals.metadata);
    if (target === 'manager') return formatCountStat('Saved presets', Number(recentTotals.prompt_presets || 0) + Number(recentTotals.caption_presets || 0));
    if (target === 'roleplay_v2') return formatCountStat('Characters', recentTotals.characters);
    if (target === 'video') return 'Simple video only';
    if (target === 'voice') return 'Coming soon';
    if (target === 'audio') return 'Coming soon';
    if (target === 'assistant') return 'Context tools ready';
    return 'Ready';
  }

  function renderWelcomeCardStats(){
    document.querySelectorAll('.welcome-card[data-switch-tab]').forEach(card => {
      const surfaceId = String(card.getAttribute('data-switch-tab') || '');
      const stat = $(`welcome-card-stat-${surfaceId}`);
      if (stat) stat.textContent = getWelcomeCardStat(surfaceId);
    });
  }

  function renderWelcomeBoard(){
    const settings = ensureStartupShape();
    const startup = settings.startup || {};
    const summary = $('welcome-board-last-surface');
    const launchToggle = $('welcome-board-show-on-launch');
    if (summary) {
      const lastSurface = String(startup.last_open_surface || 'generate');
      summary.textContent = `Last surface: ${resolveSurfaceLabel(lastSurface)}`;
    }
    if (launchToggle) launchToggle.checked = !!startup.show_welcome_on_launch;
    renderWelcomeCardStats();
  }

  async function persistWelcomeSettings(patch, statusText=''){
    ensureStartupShape();
    const mergedStartup = Object.assign({}, cache.startup || {}, patch || {});
    const data = await safeFetchJson('/api/admin/settings', {
      method: 'POST',
      headers: { 'Content-Type':'application/json' },
      body: JSON.stringify({ startup: mergedStartup }),
    });
    if (data && data.settings) {
      window.NeoAppSettingsCache = Object.assign({}, window.NeoAppSettingsCache || {}, data.settings);
      cache.startup = Object.assign({}, (data.settings.startup || {}));
      cache.ui = Object.assign({}, (data.settings.ui || {}));
    } else {
      cache.startup = mergedStartup;
    }
    if (statusText) setStatus('welcome-board-status', statusText, 'ok');
    document.dispatchEvent(new CustomEvent('neo-settings-updated', { detail: { settings: window.NeoAppSettingsCache || cache } }));
    renderWelcomeBoard();
  }

  function schedulePersistLastSurface(surface){
    ensureStartupShape();
    cache.startup.last_open_surface = surface;
    window.NeoAppSettingsCache = cache;
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      persistWelcomeSettings({ last_open_surface: surface }).catch(() => {});
    }, 500);
  }

  function bindSurfacePersistence(){
    if (typeof window.switchMainTab !== 'function' || window.switchMainTab.__welcomeWrapped) return;
    const original = window.switchMainTab;
    const wrapped = function(tab){
      const result = original(tab);
      const target = String(tab || 'generate');
      schedulePersistLastSurface(target);
      return result;
    };
    wrapped.__welcomeWrapped = true;
    window.switchMainTab = wrapped;
  }

  function activateSurface(tab, managerSubtab=''){
    const target = String(tab || 'generate');
    if (typeof window.switchMainTab === 'function') window.switchMainTab(target);
    else if (typeof window.switchTab === 'function') window.switchTab(target);
    if (target === 'manager' && managerSubtab && typeof window.switchManagerSubTab === 'function') window.switchManagerSubTab(managerSubtab);
    closeWelcomeBoard();
  }

  function applyInitialSurface(){
    const settings = ensureStartupShape();
    const surface = String(settings.startup.last_open_surface || 'generate');
    if (typeof window.switchMainTab === 'function') window.switchMainTab(surface);
  }

  function bindWelcomeBoard(){
    ensureStartupShape();
    bindSurfacePersistence();
    applyInitialSurface();
    renderWelcomeBoard();

    $('btn-open-welcome-board')?.addEventListener('click', openWelcomeBoard);
    $('btn-admin-open-welcome-board')?.addEventListener('click', openWelcomeBoard);
    $('btn-close-welcome-board')?.addEventListener('click', closeWelcomeBoard);
    $('btn-welcome-open-admin')?.addEventListener('click', () => activateSurface('admin'));
    $('btn-welcome-manage-backends')?.addEventListener('click', () => {
      closeWelcomeBoard();
      if (typeof window.openBackendManager === 'function') window.openBackendManager('text');
      else activateSurface('admin');
    });
    $('btn-welcome-resume-last')?.addEventListener('click', () => {
      const settings = ensureStartupShape();
      activateSurface(settings.startup.last_open_surface || 'generate');
    });
    $('welcome-board-modal')?.addEventListener('click', (event) => {
      if (event.target === $('welcome-board-modal')) closeWelcomeBoard();
    });
    $('welcome-board-show-on-launch')?.addEventListener('change', async (event) => {
      const checked = !!event.target.checked;
      try {
        await persistWelcomeSettings({ show_welcome_on_launch: checked }, checked ? 'Welcome board will open on launch.' : 'Welcome board hidden on launch.');
      } catch (err) {
        setStatus('welcome-board-status', err.message || 'Could not save welcome preference.', 'error');
      }
    });
    document.querySelectorAll('[data-switch-tab]').forEach(btn => {
      btn.addEventListener('click', () => activateSurface(btn.getAttribute('data-switch-tab') || 'generate', btn.getAttribute('data-manager-subtab') || ''));
    });
    document.addEventListener('neo-settings-updated', (event) => {
      const settings = event?.detail?.settings;
      if (settings && typeof settings === 'object') {
        window.NeoAppSettingsCache = Object.assign({}, settings);
        renderWelcomeBoard();
      }
    });

    if (ensureStartupShape().startup.show_welcome_on_launch) {
      setTimeout(openWelcomeBoard, 120);
    }
  }

  window.openWelcomeBoard = openWelcomeBoard;
  window.closeWelcomeBoard = closeWelcomeBoard;
  document.addEventListener('DOMContentLoaded', bindWelcomeBoard);
})();
