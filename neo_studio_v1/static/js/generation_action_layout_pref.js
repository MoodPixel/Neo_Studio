(function(){
  function $(id){ return document.getElementById(id); }
  function currentOrder(){ return String(window.NeoAppSettingsCache?.ui?.generation_action_order || $('admin-setting-generation-action-order')?.value || 'left').trim().toLowerCase() === 'right' ? 'right' : 'left'; }
  function apply(){ const root=$('tab-generate'); if(!root) return; root.dataset.actionOrder = currentOrder(); }
  function bind(){ apply(); document.addEventListener('neo-settings-updated', apply); $('admin-setting-generation-action-order')?.addEventListener('change', apply); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
