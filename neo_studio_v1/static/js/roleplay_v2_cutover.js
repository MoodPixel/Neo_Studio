(function () {
  const state = { status: null };

  function $(id) { return document.getElementById(id); }
  function text(value) { return String(value || '').trim(); }
  async function getJson(url) {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Request failed.');
    return data;
  }

  function isActive() {
    return !!(state.status?.state?.soft_cutover_active);
  }

  function clickV2() {
    document.querySelector('[data-main-tab="roleplay_v2"]')?.click();
  }

  function hasLegacySurfaceInDom() {
    return !!($('tab-roleplay') || document.querySelector('[data-main-tab="roleplay"]'));
  }

  function applyLegacyBanner(active) {
    const root = $('tab-roleplay');
    if (!root) return;
    let banner = $('roleplay-v1-cutover-banner');
    if (!active) {
      if (banner) banner.remove();
      return;
    }
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'roleplay-v1-cutover-banner';
      banner.className = 'panel';
      banner.style.marginBottom = '12px';
      banner.style.padding = '12px';
      banner.style.border = '1px solid rgba(255,255,255,0.10)';
      banner.style.background = 'rgba(255,255,255,0.04)';
      banner.innerHTML = '<div class="row-between" style="gap:12px; align-items:flex-start;"><div><div class="stat-title">Legacy Roleplay is in read-only soft cutover</div><div class="mini-note">New story work should happen in Roleplay V2. V1 stays loaded only for transition safety while migration validation finishes.</div></div><button class="btn btn-small btn-primary" id="btn-roleplay-v1-cutover-open-v2" type="button" data-v1-cutover-allow="1">Open Roleplay V2</button></div>';
      root.insertBefore(banner, root.firstChild);
      banner.querySelector('#btn-roleplay-v1-cutover-open-v2')?.addEventListener('click', clickV2);
    }
  }

  function applyLegacyReadOnly(active) {
    const root = $('tab-roleplay');
    if (!root) return;
    root.dataset.softCutoverReadOnly = active ? 'true' : 'false';
    root.querySelectorAll('button, input, textarea, select').forEach(el => {
      if (el.closest('#roleplay-v1-cutover-banner') || el.dataset.v1CutoverAllow === '1') return;
      if (active) {
        el.dataset.wasDisabledByCutover = el.disabled ? '1' : '0';
        el.disabled = true;
      } else if (el.dataset.wasDisabledByCutover === '0') {
        el.disabled = false;
      }
    });
  }

  function applyLegacyNav(active) {
    const btn = document.querySelector('[data-main-tab="roleplay"]');
    if (btn) btn.style.display = active ? 'none' : '';
    if (active && document.body?.dataset?.activeSurface === 'roleplay') clickV2();
  }

  function applyStatus(status) {
    state.status = status || null;
    if (!hasLegacySurfaceInDom()) return;
    const active = isActive();
    applyLegacyNav(active);
    applyLegacyBanner(active);
    applyLegacyReadOnly(active);
  }

  async function refresh() {
    const status = await getJson('/api/roleplay/v2/cutover/status');
    applyStatus(status);
    return status;
  }

  window.neoRoleplayV2Cutover = {
    refresh,
    applyStatus,
    isActive,
    hasLegacySurfaceInDom,
    getState: () => state.status,
  };

  if (!hasLegacySurfaceInDom()) return;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { refresh().catch(() => {}); }, { once: true });
  else refresh().catch(() => {});
})();
