(function(){
  function addLauncher(){
    if(document.getElementById('neo-scene-director-launcher')) return;
    const a=document.createElement('a');
    a.id='neo-scene-director-launcher';
    a.href='/scene-director';
    a.textContent='Scene Director';
    a.title='Open Neo Scene Director v0.5.2';
    a.style.cssText='position:fixed;right:18px;bottom:18px;z-index:9999;background:#61a8ff;color:#07111f;padding:10px 14px;border-radius:999px;font:700 13px system-ui;text-decoration:none;box-shadow:0 10px 30px rgba(0,0,0,.35)';
    document.body.appendChild(a);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', addLauncher); else addLauncher();
})();
