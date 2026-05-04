(function(){
  const KEY = 'neo-manager-setup-shell-open';
  function $(id){ return document.getElementById(id); }
  function chip(label, value, tone='neutral'){ return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`; }
  function currentBackendState(){ const c=$('surface-backend-manager-state'); const cls=Array.from(c?.classList||[]); const sc=cls.find(n=>n.startsWith('state-'))||'state-offline'; return sc.replace('state-',''); }
  function truncate(label, max=28){ const text=String(label||'').trim(); if(!text) return 'default'; return text.length>max?`${text.slice(0,max-1)}…`:text; }
  function currentModelLabel(){ return $('model-select')?.selectedOptions?.[0]?.textContent?.trim() || $('model-select')?.value || 'default'; }
  function currentModelTone(){ const clean=String(currentModelLabel()).toLowerCase(); return ['vision','vl','llava','qwen2.5-vl','qwen-vl','pixtral','molmo','omni','multimodal'].some(h=>clean.includes(h)) ? 'specialty' : 'primary'; }
  function currentLaneValue(){ return document.querySelector('#tab-manager [data-manager-subtab].active')?.dataset.managerSubtab || 'prompt'; }
  function currentPresetLabel(){ return $('manager-shell-preset-select')?.selectedOptions?.[0]?.textContent?.trim() || 'Manual setup'; }
  function currentPresetTone(){ return $('manager-preset-active-badge')?.dataset.uiTone || 'neutral'; }
  function currentLaneLabel(){ return document.querySelector('#tab-manager [data-manager-subtab].active')?.textContent?.trim() || 'Prompt Studio'; }
  function currentLaneTone(){ const lane=currentLaneValue(); if(lane==='prompt') return 'primary'; if(lane==='caption') return 'specialty'; if(lane==='library') return 'recovery'; if(lane==='settings') return 'warning'; return 'neutral'; }
  function renderSummary(){ const strip=$('manager-setup-shell-summary-strip'); if(!strip) return; const state=currentBackendState(); const label=$('surface-backend-manager-state')?.textContent?.trim()||'Offline'; strip.innerHTML=`<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${state}">${label}</span>${chip('Engine', truncate(currentModelLabel()), currentModelTone())}${chip('Workspace', currentLaneLabel(), currentLaneTone())}${chip('Preset', currentPresetLabel(), currentPresetTone())}`; }
  function apply(open){ const h=$('manager-setup-shell-header'), c=$('manager-setup-shell-content'), p=$('manager-setup-shell-panel'), s=$('manager-setup-shell-summary-strip'), t=$('manager-setup-shell-toggle-copy'); if(!c||!p) return; const o=!!open; renderSummary(); c.style.display=o?'':'none'; p.classList.toggle('is-collapsed',!o); h?.setAttribute('aria-expanded',o?'true':'false'); s?.classList.toggle('hidden',o); if(t) t.textContent=o?'Collapse setup':'Expand setup'; try{window.sessionStorage.setItem(KEY,o?'true':'false');}catch(_){} }
  function toggle(){ const c=$('manager-setup-shell-content'); apply(!!(c&&c.style.display==='none')); }
  function bind(){ const h=$('manager-setup-shell-header'); const saved=(()=>{try{return window.sessionStorage.getItem(KEY);}catch(_){return null;}})(); apply(saved===null?true:saved==='true'); h?.addEventListener('click',toggle); h?.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); }}); document.addEventListener('neo-backend-state',renderSummary); document.addEventListener('neo-manager-model-changed',renderSummary); document.addEventListener('neo-manager-lane-changed',renderSummary); document.addEventListener('neo-manager-preset-changed',renderSummary); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
