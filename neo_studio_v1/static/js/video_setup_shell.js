(function(){
  const KEY = 'neo-video-setup-shell-open';
  const PROFILE_TONES = {
    wan22_5b_balanced: 'primary',
    wan22_14b_t2v_quality: 'warning',
    wan22_14b_i2v_quality: 'specialty',
  };
  const LANE_TONES = { t2v:'primary', i2v:'specialty' };

  function $(id){ return document.getElementById(id); }
  function chip(label, value, tone='neutral'){ return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`; }
  function currentBackendState(){ const c=$('surface-backend-video-state'); const cls=Array.from(c?.classList||[]); const sc=cls.find(n=>n.startsWith('state-'))||'state-offline'; return sc.replace('state-',''); }
  function currentProfileValue(){ return $('video-profile')?.value || 'wan22_5b_balanced'; }
  function currentProfileLabel(){ return $('video-profile')?.selectedOptions?.[0]?.textContent?.trim() || 'Balanced / Low VRAM'; }
  function currentModeValue(){ return $('video-mode')?.value || 't2v'; }
  function currentModeLabel(){ return $('video-mode')?.selectedOptions?.[0]?.textContent?.trim() || 'Text to Video'; }
  function currentPresetLabel(){ return $('video-shell-preset-select')?.selectedOptions?.[0]?.textContent?.trim() || 'Manual setup'; }
  function currentPresetTone(){ return $('video-preset-active-badge')?.dataset.uiTone || 'neutral'; }
  function renderSummary(){
    const strip=$('video-setup-shell-summary-strip'); if(!strip) return;
    const state=currentBackendState();
    const label=$('surface-backend-video-state')?.textContent?.trim() || 'Offline';
    strip.innerHTML=`<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${state}">${label}</span>${chip('Profile', currentProfileLabel(), PROFILE_TONES[currentProfileValue()]||'neutral')}${chip('Workspace', currentModeLabel(), LANE_TONES[currentModeValue()]||'neutral')}${chip('Preset', currentPresetLabel(), currentPresetTone())}`;
  }
  function apply(open){ const h=$('video-setup-shell-header'), c=$('video-setup-shell-content'), p=$('video-setup-shell-panel'), s=$('video-setup-shell-summary-strip'), t=$('video-setup-shell-toggle-copy'); if(!c||!p) return; const o=!!open; renderSummary(); c.style.display=o?'':'none'; p.classList.toggle('is-collapsed',!o); h?.setAttribute('aria-expanded',o?'true':'false'); s?.classList.toggle('hidden',o); if(t) t.textContent=o?'Collapse setup':'Expand setup'; try{window.sessionStorage.setItem(KEY,o?'true':'false');}catch(_){} }
  function toggle(){ const c=$('video-setup-shell-content'); apply(!!(c&&c.style.display==='none')); }
  function bind(){ const h=$('video-setup-shell-header'); const saved=(()=>{try{return window.sessionStorage.getItem(KEY);}catch(_){return null;}})(); apply(saved===null?true:saved==='true'); h?.addEventListener('click',toggle); h?.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); }}); document.addEventListener('neo-backend-state',renderSummary); document.addEventListener('neo-video-profile-changed',renderSummary); document.addEventListener('neo-video-mode-changed',renderSummary); document.addEventListener('neo-video-preset-changed',renderSummary); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
