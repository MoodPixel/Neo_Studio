(function(){
  const KEY = 'neo-assistant-setup-shell-open';
  function $(id){ return document.getElementById(id); }
  function chip(label, value, tone='neutral'){ return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`; }
  function currentBackendState(){ const c=$('surface-backend-assistant-state'); const cls=Array.from(c?.classList||[]); const sc=cls.find(n=>n.startsWith('state-'))||'state-offline'; return sc.replace('state-',''); }
  function truncate(label, max=26){ const text=String(label||'').trim(); if(!text) return 'default'; return text.length>max?`${text.slice(0,max-1)}…`:text; }
  function currentModelLabel(){ return $('assistant-active-model')?.textContent?.trim() || 'default'; }
  function currentModelTone(){ const clean=String(currentModelLabel()).toLowerCase(); return ['vision','vl','llava','qwen2.5-vl','qwen-vl','pixtral','molmo','omni','multimodal'].some(h=>clean.includes(h)) ? 'specialty' : 'primary'; }
  function currentModeValue(){ return $('assistant-mode')?.value || 'general'; }
  function currentPresetLabel(){ return $('assistant-shell-preset-select')?.selectedOptions?.[0]?.textContent?.trim() || 'Manual setup'; }
  function currentPresetTone(){ return $('assistant-preset-active-badge')?.dataset.uiTone || 'neutral'; }
  function currentModeLabel(){ return $('assistant-mode')?.selectedOptions?.[0]?.textContent?.trim() || 'General'; }
  function currentModeTone(){ const v=currentModeValue(); if(v==='general') return 'primary'; if(v==='support') return 'success'; if(v==='creative') return 'specialty'; if(v==='analysis') return 'recovery'; if(v==='system') return 'warning'; return 'primary'; }
  function renderSummary(){ const strip=$('assistant-setup-shell-summary-strip'); if(!strip) return; const state=currentBackendState(); const label=$('surface-backend-assistant-state')?.textContent?.trim()||'Offline'; strip.innerHTML=`<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${state}">${label}</span>${chip('Engine', truncate(currentModelLabel()), currentModelTone())}${chip('Workspace', truncate(currentModeLabel(),30), currentModeTone())}${chip('Preset', currentPresetLabel(), currentPresetTone())}`; }
  function apply(open){ const h=$('assistant-setup-shell-header'), c=$('assistant-setup-shell-content'), p=$('assistant-setup-shell-panel'), s=$('assistant-setup-shell-summary-strip'), t=$('assistant-setup-shell-toggle-copy'); if(!c||!p) return; const o=!!open; renderSummary(); c.style.display=o?'':'none'; p.classList.toggle('is-collapsed',!o); h?.setAttribute('aria-expanded',o?'true':'false'); s?.classList.toggle('hidden',o); if(t) t.textContent=o?'Collapse setup':'Expand setup'; try{window.sessionStorage.setItem(KEY,o?'true':'false');}catch(_){} }
  function toggle(){ const c=$('assistant-setup-shell-content'); apply(!!(c&&c.style.display==='none')); }
  function bind(){ const h=$('assistant-setup-shell-header'); const saved=(()=>{try{return window.sessionStorage.getItem(KEY);}catch(_){return null;}})(); apply(saved===null?true:saved==='true'); h?.addEventListener('click',toggle); h?.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); }}); document.addEventListener('neo-backend-state',renderSummary); document.addEventListener('neo-manager-model-changed',renderSummary); document.addEventListener('neo-assistant-mode-changed',renderSummary); document.addEventListener('neo-assistant-preset-changed',renderSummary); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
