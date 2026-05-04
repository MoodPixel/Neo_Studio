(function(){
  const KEY = 'neo-voice-setup-shell-open';
  const STYLE_TONES = { clean:'primary', warm:'success', character:'specialty', ad:'warning' };
  const JOB_TONES = { tts:'primary', preview:'recovery', pack:'specialty' };
  function $(id){ return document.getElementById(id); }
  function chip(label, value, tone='neutral'){ return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`; }
  function currentBackendState(){ const c=$('surface-backend-voice-state'); const cls=Array.from(c?.classList||[]); const sc=cls.find(n=>n.startsWith('state-'))||'state-offline'; return sc.replace('state-',''); }
  function currentStyleValue(){ return $('voice-style')?.value || 'clean'; }
  function currentStyleLabel(){ return $('voice-style')?.selectedOptions?.[0]?.textContent?.trim() || 'Clean narrator'; }
  function currentJobValue(){ return $('voice-job-type')?.value || 'tts'; }
  function currentJobLabel(){ return $('voice-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Text to speech'; }
  function currentPresetLabel(){ return $('voice-shell-preset-select')?.selectedOptions?.[0]?.textContent?.trim() || 'Manual setup'; }
  function currentPresetTone(){ return $('voice-preset-active-badge')?.dataset.uiTone || 'neutral'; }
  function renderSummary(){ const strip=$('voice-setup-shell-summary-strip'); if(!strip) return; const state=currentBackendState(); const label=$('surface-backend-voice-state')?.textContent?.trim()||'Offline'; strip.innerHTML=`<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${state}">${label}</span>${chip('Engine', currentStyleLabel(), STYLE_TONES[currentStyleValue()]||'neutral')}${chip('Workspace', currentJobLabel(), JOB_TONES[currentJobValue()]||'neutral')}${chip('Preset', currentPresetLabel(), currentPresetTone())}`; }
  function apply(open){ const h=$('voice-setup-shell-header'), c=$('voice-setup-shell-content'), p=$('voice-setup-shell-panel'), s=$('voice-setup-shell-summary-strip'), t=$('voice-setup-shell-toggle-copy'); if(!c||!p) return; const o=!!open; renderSummary(); c.style.display=o?'':'none'; p.classList.toggle('is-collapsed',!o); h?.setAttribute('aria-expanded',o?'true':'false'); s?.classList.toggle('hidden',o); if(t) t.textContent=o?'Collapse setup':'Expand setup'; try{window.sessionStorage.setItem(KEY,o?'true':'false');}catch(_){} }
  function toggle(){ const c=$('voice-setup-shell-content'); apply(!!(c&&c.style.display==='none')); }
  function bind(){ const h=$('voice-setup-shell-header'); const saved=(()=>{try{return window.sessionStorage.getItem(KEY);}catch(_){return null;}})(); apply(saved===null?true:saved==='true'); h?.addEventListener('click',toggle); h?.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); }}); document.addEventListener('neo-backend-state',renderSummary); document.addEventListener('neo-voice-style-changed',renderSummary); document.addEventListener('neo-voice-job-changed',renderSummary); document.addEventListener('neo-voice-preset-changed',renderSummary); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
