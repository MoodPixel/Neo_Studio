(function(){
  const KEY = 'neo-audio-setup-shell-open';
  const FORMAT_TONES = { wav:'primary', flac:'success', mp3:'warning' };
  const JOB_TONES = { music:'primary', sfx:'specialty', ambience:'recovery' };
  function $(id){ return document.getElementById(id); }
  function chip(label, value, tone='neutral'){ return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`; }
  function currentBackendState(){ const c=$('surface-backend-audio-state'); const cls=Array.from(c?.classList||[]); const sc=cls.find(n=>n.startsWith('state-'))||'state-offline'; return sc.replace('state-',''); }
  function currentFormatValue(){ return $('audio-format')?.value || 'wav'; }
  function currentFormatLabel(){ return $('audio-format')?.selectedOptions?.[0]?.textContent?.trim() || 'WAV'; }
  function currentJobValue(){ return $('audio-job-type')?.value || 'music'; }
  function currentJobLabel(){ return $('audio-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Music'; }
  function currentPresetLabel(){ return $('audio-shell-preset-select')?.selectedOptions?.[0]?.textContent?.trim() || 'Manual setup'; }
  function currentPresetTone(){ return $('audio-preset-active-badge')?.dataset.uiTone || 'neutral'; }
  function renderSummary(){ const strip=$('audio-setup-shell-summary-strip'); if(!strip) return; const state=currentBackendState(); const label=$('surface-backend-audio-state')?.textContent?.trim()||'Offline'; strip.innerHTML=`<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${state}">${label}</span>${chip('Engine', currentFormatLabel(), FORMAT_TONES[currentFormatValue()]||'neutral')}${chip('Workspace', currentJobLabel(), JOB_TONES[currentJobValue()]||'neutral')}${chip('Preset', currentPresetLabel(), currentPresetTone())}`; }
  function apply(open){ const h=$('audio-setup-shell-header'), c=$('audio-setup-shell-content'), p=$('audio-setup-shell-panel'), s=$('audio-setup-shell-summary-strip'), t=$('audio-setup-shell-toggle-copy'); if(!c||!p) return; const o=!!open; renderSummary(); c.style.display=o?'':'none'; p.classList.toggle('is-collapsed',!o); h?.setAttribute('aria-expanded',o?'true':'false'); s?.classList.toggle('hidden',o); if(t) t.textContent=o?'Collapse setup':'Expand setup'; try{window.sessionStorage.setItem(KEY,o?'true':'false');}catch(_){} }
  function toggle(){ const c=$('audio-setup-shell-content'); apply(!!(c&&c.style.display==='none')); }
  function bind(){ const h=$('audio-setup-shell-header'); const saved=(()=>{try{return window.sessionStorage.getItem(KEY);}catch(_){return null;}})(); apply(saved===null?true:saved==='true'); h?.addEventListener('click',toggle); h?.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); }}); document.addEventListener('neo-backend-state',renderSummary); document.addEventListener('neo-audio-format-changed',renderSummary); document.addEventListener('neo-audio-job-changed',renderSummary); document.addEventListener('neo-audio-preset-changed',renderSummary); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
