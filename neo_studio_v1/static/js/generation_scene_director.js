(function(){
  'use strict';
  const $ = (id) => document.getElementById(id);
  const clamp = (v,min,max)=>Math.max(min,Math.min(max,v));
  const esc = (s)=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const state = {
    subjects: [],
    objects: [],
    drag: null,
  };
  const subjectDefaults = [
    'adult woman, full body, clear separate character',
    'adult man, full body, clear separate character',
    'adult character, full body, clear separate character',
    'adult character, full body, clear separate character'
  ];
  function isEnabled(){ return !!$('scene-director-enabled')?.checked; }
  function bboxForPreset(count, i){
    if(count===2) return i===0 ? [0.14,0.12,0.34,0.86] : [0.56,0.12,0.76,0.86];
    if(count===3) return [[0.06,0.10,0.29,0.90],[0.385,0.10,0.615,0.90],[0.71,0.10,0.94,0.90]][i] || [0.1,0.1,0.3,0.9];
    return [[0.03,0.10,0.23,0.90],[0.275,0.10,0.475,0.90],[0.525,0.10,0.725,0.90],[0.77,0.10,0.97,0.90]][i] || [0.1,0.1,0.3,0.9];
  }
  function applyPreset(name){
    const preset = name || $('scene-director-preset')?.value || 'two_interaction';
    const count = preset==='four_count' ? 4 : preset==='three_count' ? 3 : 2;
    state.subjects = Array.from({length: count}, (_,i)=>({
      id:`person_${i+1}`,
      label:`Person ${i+1}`,
      prompt: subjectDefaults[i] || subjectDefaults[2],
      bbox:bboxForPreset(count,i),
      pose_type: 'standing relaxed',
      facing: count===2 ? (i===0?'person_2':'person_1') : 'camera',
      required:true,
    }));
    state.objects = count===2 ? [{ id:'object_1', label:'Prop 1', prompt:'small gift box held between them', bbox:[0.42,0.40,0.58,0.56], bound_to:['person_1','person_2'], relation:'held between them' }] : [];
    if($('scene-director-mode')) $('scene-director-mode').value = count>=3 ? 'count_locked' : 'relation_focused';
    render();
  }
  function buildScene(){
    const positive = $('generation-positive')?.value || '';
    const negative = $('generation-negative')?.value || '';
    const mode = $('scene-director-mode')?.value || (state.subjects.length>=3?'count_locked':'relation_focused');
    const from = $('scene-relation-from')?.value || state.subjects[0]?.id || '';
    const to = $('scene-relation-to')?.value || state.subjects[1]?.id || '';
    const relType = $('scene-relation-type')?.value || 'facing';
    const obj = $('scene-relation-object')?.value || '';
    const relations = from && to && from!==to ? [{ from, to, type: relType, object: obj || undefined }] : [];
    return {
      version:'0.5.2-neo-ui',
      enabled: isEnabled(),
      mode,
      canvas:{ width:Number($('generation-width')?.value||1344), height:Number($('generation-height')?.value||768) },
      camera:{ framing:$('scene-director-camera-framing')?.value||'wide full body', angle:$('scene-director-camera-angle')?.value||'eye level', lens:'50mm' },
      global_style: positive,
      subjects: state.subjects.map(s=>({ id:s.id, prompt:s.prompt, bbox:s.bbox, pose_type:s.pose_type, facing:s.facing, required:!!s.required })),
      objects: state.objects.map(o=>({ id:o.id, prompt:o.prompt, bbox:o.bbox, bound_to:o.bound_to||[], relation:o.relation||'' })),
      relations,
      negative,
    };
  }
  function scenePrompt(scene){
    if(!scene.enabled) return '';
    const count = scene.subjects.length;
    const countLine = scene.mode === 'count_locked'
      ? `exactly ${count} separate full body adult people, one visible person inside each marked region, no missing people, no merged bodies`
      : `${count} separate adult people arranged according to the scene layout`;
    const cam = `${scene.camera.framing}, ${scene.camera.angle}, ${scene.camera.lens}`;
    const subs = scene.subjects.map((s,i)=>`Person ${i+1} region ${bboxText(s.bbox)}: ${s.prompt}; pose ${s.pose_type}; facing ${s.facing || 'camera'}; separate full body person`).join('. ');
    const objs = scene.objects.map((o,i)=>`Object ${i+1} region ${bboxText(o.bbox)}: ${o.prompt}; relation ${o.relation}; bound to ${(o.bound_to||[]).join(' and ')}`).join('. ');
    const rels = scene.relations.map(r=>`${r.from} ${String(r.type||'facing').replace(/_/g,' ')} ${r.to}${r.object?` using ${r.object}`:''}`).join('. ');
    return [countLine, cam, subs, objs, rels].filter(Boolean).join('. ');
  }
  function bboxText(b){ return `[x:${Math.round(b[0]*100)}%, y:${Math.round(b[1]*100)}%, x2:${Math.round(b[2]*100)}%, y2:${Math.round(b[3]*100)}%]`; }
  function applyToPayload(payload){
    const scene = buildScene();
    payload.scene_director_enabled = !!scene.enabled;
    payload.scene_director_scene = scene;
    payload.scene_director_json = JSON.stringify(scene);
    if(scene.enabled){
      const add = scenePrompt(scene);
      const basePos = String(payload.positive || scene.global_style || '').trim();
      const baseNeg = String(payload.negative || scene.negative || '').trim();
      payload.positive = [basePos, add].filter(Boolean).join(', ');
      payload.negative = [baseNeg, 'extra people, missing person, merged bodies, duplicate limbs, deformed anatomy, nude, nsfw, underwear, bikini'].filter(Boolean).join(', ');
      payload._neo_scene_director_note = 'Scene Director uses Neo main prompt/settings and augments prompt only when enabled.';
    }
    return payload;
  }
  function updateJson(){
    const scene = buildScene();
    const json = JSON.stringify(scene,null,2);
    if($('scene-director-json')) $('scene-director-json').value=json;
    const badge=$('scene-director-status-badge');
    if(badge){ badge.textContent = scene.enabled ? `ON · ${scene.subjects.length} subject${scene.subjects.length===1?'':'s'}` : 'OFF'; badge.classList.toggle('ok', scene.enabled); }
    const sum=$('scene-director-summary-badge');
    if(sum) sum.textContent = `${scene.subjects.length} subject${scene.subjects.length===1?'':'s'} · ${scene.objects.length} prop${scene.objects.length===1?'':'s'}`;
  }
  function card(kind, item, idx){
    const isSub = kind==='subject';
    const boundOptions = state.subjects.map(s=>`<option value="${esc(s.id)}" ${(item.bound_to||[]).includes(s.id)?'selected':''}>${esc(s.label)}</option>`).join('');
    return `<div class="generation-unit-card" data-scene-card="${kind}" data-id="${esc(item.id)}" style="padding:10px; border:1px solid rgba(255,255,255,.10); border-radius:12px;">
      <div class="row-between" style="gap:8px; margin-bottom:8px;"><strong>${isSub?'Person':'Prop'} ${idx+1}</strong><button class="btn btn-small" data-scene-delete="${esc(item.id)}" type="button">Delete</button></div>
      <label>${isSub?'Character prompt':'Prop prompt'}</label><textarea data-scene-field="prompt" rows="2">${esc(item.prompt)}</textarea>
      <div class="grid grid-2" style="gap:8px; margin-top:8px;">
        ${isSub?`<div><label>Pose</label><select data-scene-field="pose_type"><option value="standing relaxed">standing relaxed</option><option value="turning slightly">turning slightly</option><option value="walking">walking</option><option value="leaning">leaning</option><option value="sitting">sitting</option></select></div><div><label>Facing</label><select data-scene-field="facing"><option value="camera">camera</option>${state.subjects.filter(s=>s.id!==item.id).map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('')}</select></div>`:`<div><label>Relation</label><input data-scene-field="relation" value="${esc(item.relation||'')}"/></div><div><label>Bound to</label><select data-scene-field="bound_to" multiple>${boundOptions}</select></div>`}
      </div>
      <div class="grid grid-4" style="gap:8px; margin-top:8px;"><div><label>X%</label><input data-bbox="0" type="number" step="1" value="${Math.round(item.bbox[0]*100)}"></div><div><label>Y%</label><input data-bbox="1" type="number" step="1" value="${Math.round(item.bbox[1]*100)}"></div><div><label>X2%</label><input data-bbox="2" type="number" step="1" value="${Math.round(item.bbox[2]*100)}"></div><div><label>Y2%</label><input data-bbox="3" type="number" step="1" value="${Math.round(item.bbox[3]*100)}"></div></div>
    </div>`;
  }
  function renderCards(){
    if($('scene-director-subject-list')) $('scene-director-subject-list').innerHTML=state.subjects.map((s,i)=>card('subject',s,i)).join('');
    if($('scene-director-object-list')) $('scene-director-object-list').innerHTML=state.objects.map((o,i)=>card('object',o,i)).join('');
    document.querySelectorAll('[data-scene-card]').forEach(el=>{
      const id=el.dataset.id; const arr=el.dataset.sceneCard==='subject'?state.subjects:state.objects; const item=arr.find(x=>x.id===id); if(!item) return;
      const pose=el.querySelector('[data-scene-field="pose_type"]'); if(pose) pose.value=item.pose_type||'standing relaxed';
      const facing=el.querySelector('[data-scene-field="facing"]'); if(facing) facing.value=item.facing||'camera';
      el.addEventListener('input',()=>updateFromCards()); el.addEventListener('change',()=>updateFromCards());
    });
    document.querySelectorAll('[data-scene-delete]').forEach(btn=>btn.addEventListener('click',()=>{ const id=btn.dataset.sceneDelete; state.subjects=state.subjects.filter(x=>x.id!==id); state.objects=state.objects.filter(x=>x.id!==id); render(); }));
  }
  function updateFromCards(){
    document.querySelectorAll('[data-scene-card]').forEach(el=>{
      const arr=el.dataset.sceneCard==='subject'?state.subjects:state.objects; const item=arr.find(x=>x.id===el.dataset.id); if(!item) return;
      item.prompt=el.querySelector('[data-scene-field="prompt"]')?.value||'';
      const pose=el.querySelector('[data-scene-field="pose_type"]'); if(pose) item.pose_type=pose.value;
      const facing=el.querySelector('[data-scene-field="facing"]'); if(facing) item.facing=facing.value;
      const rel=el.querySelector('[data-scene-field="relation"]'); if(rel) item.relation=rel.value;
      const bound=el.querySelector('[data-scene-field="bound_to"]'); if(bound) item.bound_to=Array.from(bound.selectedOptions).map(o=>o.value);
      el.querySelectorAll('[data-bbox]').forEach(input=>{ item.bbox[Number(input.dataset.bbox)] = clamp(Number(input.value||0)/100,0,1); });
      if(item.bbox[2] <= item.bbox[0]+0.03) item.bbox[2]=clamp(item.bbox[0]+0.15,0,1);
      if(item.bbox[3] <= item.bbox[1]+0.03) item.bbox[3]=clamp(item.bbox[1]+0.30,0,1);
    });
    renderCanvas(); updateRelations(); updateJson();
  }
  function renderCanvas(){
    const c=$('scene-director-canvas'); if(!c) return;
    Array.from(c.querySelectorAll('.scene-director-box')).forEach(n=>n.remove());
    const make=(kind,item,idx)=>{
      const b=item.bbox; const d=document.createElement('div'); d.className='scene-director-box'; d.dataset.id=item.id; d.dataset.kind=kind;
      d.style.cssText=`position:absolute; left:${b[0]*100}%; top:${b[1]*100}%; width:${(b[2]-b[0])*100}%; height:${(b[3]-b[1])*100}%; border:2px solid ${kind==='subject'?'rgba(119,170,255,.95)':'rgba(255,205,105,.95)'}; background:${kind==='subject'?'rgba(119,170,255,.10)':'rgba(255,205,105,.12)'}; border-radius:10px; cursor:move; box-sizing:border-box;`;
      d.innerHTML=`<div style="position:absolute; left:6px; top:5px; font-size:12px; background:rgba(0,0,0,.45); padding:2px 6px; border-radius:999px;">${kind==='subject'?'Person':'Prop'} ${idx+1}</div><div style="position:absolute; right:4px; bottom:4px; width:12px; height:12px; border-right:2px solid currentColor; border-bottom:2px solid currentColor; cursor:nwse-resize;" data-resize="1"></div>`;
      c.appendChild(d);
    };
    state.subjects.forEach((s,i)=>make('subject',s,i)); state.objects.forEach((o,i)=>make('object',o,i));
  }
  function updateRelations(){
    const fill=(el, opts)=>{ if(!el) return; const old=el.value; el.innerHTML=opts; if([...el.options].some(o=>o.value===old)) el.value=old; };
    const subOpts=state.subjects.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('');
    fill($('scene-relation-from'), subOpts); fill($('scene-relation-to'), subOpts);
    if($('scene-relation-to') && $('scene-relation-to').value===$('scene-relation-from')?.value && state.subjects[1]) $('scene-relation-to').value=state.subjects[1].id;
    fill($('scene-relation-object'), '<option value="">None</option>'+state.objects.map(o=>`<option value="${esc(o.id)}">${esc(o.label)}</option>`).join(''));
  }
  function render(){ renderCards(); renderCanvas(); updateRelations(); updateJson(); }
  function bind(){
    if(!$('scene-director-panel')) return;
    $('scene-director-enabled')?.addEventListener('change', updateJson);
    $('scene-director-preset')?.addEventListener('change', e=>applyPreset(e.target.value));
    ['scene-director-mode','scene-director-camera-framing','scene-director-camera-angle','scene-relation-from','scene-relation-to','scene-relation-type','scene-relation-object','generation-positive','generation-negative','generation-width','generation-height'].forEach(id=>$(id)?.addEventListener('input',updateJson));
    $('scene-director-auto-layout')?.addEventListener('click',()=>applyPreset($('scene-director-preset')?.value));
    $('scene-director-add-subject')?.addEventListener('click',()=>{ const n=state.subjects.length+1; state.subjects.push({id:`person_${n}`,label:`Person ${n}`,prompt:subjectDefaults[Math.min(n-1,3)],bbox:bboxForPreset(Math.max(n,2),Math.min(n-1,3)),pose_type:'standing relaxed',facing:'camera',required:true}); render(); });
    $('scene-director-add-object')?.addEventListener('click',()=>{ const n=state.objects.length+1; state.objects.push({id:`object_${n}`,label:`Prop ${n}`,prompt:'small prop',bbox:[0.42,0.42,0.58,0.58],bound_to:state.subjects.slice(0,2).map(s=>s.id),relation:'near characters'}); render(); });
    $('scene-director-copy-json')?.addEventListener('click',()=>navigator.clipboard?.writeText($('scene-director-json')?.value||''));
    $('scene-director-download-json')?.addEventListener('click',()=>{ const blob=new Blob([$('scene-director-json')?.value||'{}'],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='neo_scene_director_scene.json'; a.click(); URL.revokeObjectURL(a.href); });
    const canvas=$('scene-director-canvas');
    canvas?.addEventListener('pointerdown',e=>{ const box=e.target.closest('.scene-director-box'); if(!box) return; const item=[...state.subjects,...state.objects].find(x=>x.id===box.dataset.id); if(!item) return; const rect=canvas.getBoundingClientRect(); state.drag={id:item.id, kind:box.dataset.kind, resize:!!e.target.dataset.resize, startX:e.clientX, startY:e.clientY, rect, bbox:[...item.bbox]}; box.setPointerCapture?.(e.pointerId); e.preventDefault(); });
    window.addEventListener('pointermove',e=>{ if(!state.drag) return; const item=[...state.subjects,...state.objects].find(x=>x.id===state.drag.id); if(!item) return; const dx=(e.clientX-state.drag.startX)/state.drag.rect.width; const dy=(e.clientY-state.drag.startY)/state.drag.rect.height; const b=[...state.drag.bbox]; if(state.drag.resize){ b[2]=clamp(b[2]+dx,b[0]+0.05,1); b[3]=clamp(b[3]+dy,b[1]+0.05,1); } else { const w=b[2]-b[0], h=b[3]-b[1]; b[0]=clamp(b[0]+dx,0,1-w); b[1]=clamp(b[1]+dy,0,1-h); b[2]=b[0]+w; b[3]=b[1]+h; } item.bbox=b; renderCanvas(); updateJson(); });
    window.addEventListener('pointerup',()=>{ if(state.drag){ state.drag=null; render(); } });
    applyPreset('two_interaction');
  }
  window.NeoSceneDirector = { buildScene, applyToPayload, render, state };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', bind); else bind();
})();
