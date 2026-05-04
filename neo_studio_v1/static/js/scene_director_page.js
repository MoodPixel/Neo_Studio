(function(){
  async function loadScene(kind){
    const box = document.getElementById('scene-json');
    if(!box) return;
    try{
      const res = await fetch('/api/scene-director/default-scene?case=' + encodeURIComponent(kind || 'pose_interaction'));
      const data = await res.json();
      box.value = JSON.stringify(data.scene || data, null, 2);
    }catch(err){ box.value = 'Could not load scene JSON: ' + err; }
  }
  document.querySelectorAll('[data-case]').forEach(btn=>btn.addEventListener('click',()=>loadScene(btn.dataset.case)));
  loadScene('pose_interaction');
})();
