(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const DEFAULT_SCENE = {
    version: '0.5.2', mode: 'relation_focused', canvas: { width: 1024, height: 1024 },
    camera: { framing: 'medium full body', angle: 'eye level', lens: '50mm' },
    global_style: 'cinematic realistic image, clean studio lighting, detailed clothing, safe composition',
    subjects: [
      { id: 'person_1', bbox: [0.08, 0.12, 0.42, 0.92], prompt: 'adult woman wearing a modest red dress, full body, clear face, natural hands', pose_type: 'standing relaxed, facing person_2', facing: 'person_2', required: true, identity: { ipadapter_slot: 'subject_1_mask', weight: 0.55 } },
      { id: 'person_2', bbox: [0.58, 0.12, 0.92, 0.92], prompt: 'adult man wearing a navy suit, full body, clear face, natural hands', pose_type: 'standing relaxed, facing person_1', facing: 'person_1', required: true, identity: { ipadapter_slot: 'subject_2_mask', weight: 0.55 } }
    ],
    objects: [{ id: 'gift_box', bbox: [0.42, 0.42, 0.58, 0.58], prompt: 'small wrapped gift box held between both people', bound_to: ['person_1', 'person_2'], relation: 'held between them' }],
    relations: [{ from: 'person_1', to: 'person_2', type: 'handing_to', object: 'gift_box' }],
    negative: 'extra people, missing person, merged bodies, duplicate limbs, bad hands, deformed anatomy, nude, nsfw, underwear, bikini, child, teenager'
  };
  const PRESETS = {
    two: DEFAULT_SCENE,
    three: { version: '0.5.2', mode: 'count_locked', canvas: { width: 1344, height: 768 }, camera: { framing: 'wide full body', angle: 'eye level', lens: '50mm' }, global_style: 'cinematic realistic group photo, clean background, full body, balanced lighting', subjects: [
      { id: 'person_1', bbox: [0.05, 0.10, 0.30, 0.92], prompt: 'adult woman in white sci-fi armor, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_1_mask', weight: 0.50 } },
      { id: 'person_2', bbox: [0.375, 0.10, 0.625, 0.92], prompt: 'adult man in black sci-fi armor, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_2_mask', weight: 0.50 } },
      { id: 'person_3', bbox: [0.70, 0.10, 0.95, 0.92], prompt: 'adult woman in silver sci-fi armor, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_3_mask', weight: 0.50 } }
    ], objects: [], relations: [], negative: 'extra people, missing person, merged bodies, duplicate limbs, bad hands, deformed anatomy, nude, nsfw, child, teenager' },
    four: { version: '0.5.2', mode: 'count_locked', canvas: { width: 1536, height: 768 }, camera: { framing: 'wide full body', angle: 'eye level', lens: '50mm' }, global_style: 'cinematic realistic squad lineup, clean background, full body, balanced lighting', subjects: [
      { id: 'person_1', bbox: [0.03, 0.10, 0.23, 0.92], prompt: 'adult woman in red explorer outfit, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_1_mask', weight: 0.48 } },
      { id: 'person_2', bbox: [0.27, 0.10, 0.47, 0.92], prompt: 'adult man in blue explorer outfit, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_2_mask', weight: 0.48 } },
      { id: 'person_3', bbox: [0.53, 0.10, 0.73, 0.92], prompt: 'adult woman in green explorer outfit, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_3_mask', weight: 0.48 } },
      { id: 'person_4', bbox: [0.77, 0.10, 0.97, 0.92], prompt: 'adult man in black explorer outfit, separate full body person', pose_type: 'standing relaxed', required: true, identity: { ipadapter_slot: 'subject_4_mask', weight: 0.48 } }
    ], objects: [], relations: [], negative: 'extra people, missing person, merged bodies, duplicate limbs, bad hands, deformed anatomy, nude, nsfw, child, teenager' }
  };
  function stringify(obj) { return JSON.stringify(obj, null, 2); }
  function copyText(text) { return navigator.clipboard?.writeText ? navigator.clipboard.writeText(text) : Promise.reject(new Error('clipboard unavailable')); }
  function downloadText(filename, text) { const blob = new Blob([text], { type: 'application/json;charset=utf-8' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 500); }
  function status(msg) { const el = $('neo-scene-director-status'); if (el) el.textContent = msg; }
  function buildPanel() {
    const wrap = document.createElement('details');
    wrap.className = 'accordion-block generation-inline-accordion neo-scene-director-assets';
    wrap.id = 'neo-scene-director-assets-accordion';
    wrap.setAttribute('data-accordion-id', 'neo-scene-director-assets');
    wrap.style.marginTop = '14px';
    wrap.innerHTML = `<summary class="accordion-summary"><div><div class="accordion-title">Scene Director · Regional Characters</div><div class="accordion-hint">Layout-locked multi-subject scene JSON, subject masks, and IPAdapter prep for the Comfy custom node.</div></div><span aria-hidden="true" class="accordion-chevron">▾</span></summary><div class="accordion-body"><div class="card-lite" style="padding:12px;"><div class="row-between" style="gap:12px; flex-wrap:wrap; align-items:flex-start;"><div><div class="stat-title">Neo Scene Director v0.5.2</div><div class="muted small">Use this as the structured regional prompt brain. It outputs layout preview, mask preview, and subject masks for IPAdapter region tests.</div></div><span class="badge">Assets lane</span></div><div class="grid grid-3" style="margin-top:12px; gap:10px; align-items:end;"><div><label for="neo-scene-director-preset">Preset</label><select id="neo-scene-director-preset"><option value="two">2 people + object interaction</option><option value="three">3 people count locked</option><option value="four">4 people count locked</option></select></div><div><label for="neo-scene-director-mode-note">Recommended mode</label><input id="neo-scene-director-mode-note" readonly value="relation_focused / count_locked" /></div><div class="row" style="gap:8px; flex-wrap:wrap;"><button class="btn" type="button" id="neo-scene-director-load-preset">Load preset</button><button class="btn btn-primary" type="button" id="neo-scene-director-copy-json">Copy JSON</button><button class="btn" type="button" id="neo-scene-director-download-json">Download JSON</button></div></div><label for="neo-scene-director-json" style="margin-top:12px;">Scene JSON</label><textarea id="neo-scene-director-json" rows="18" spellcheck="false" style="font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size:12px;"></textarea><div class="row" style="gap:8px; flex-wrap:wrap; margin-top:10px;"><a class="btn" href="/static/scene_director/Neo_Scene_Director_v0_5_2_IPAdapter_Region_Prep.zip" download>Download Comfy node pack</a><a class="btn" href="/static/scene_director/neo_scene_director_v052_pose_interaction_checkpoint_gguf_vae_api.json" download>Workflow · 2 people</a><a class="btn" href="/static/scene_director/neo_scene_director_v052_3_people_checkpoint_gguf_vae_api.json" download>Workflow · 3 people</a><a class="btn" href="/static/scene_director/neo_scene_director_v052_4_people_checkpoint_gguf_vae_api.json" download>Workflow · 4 people</a></div><div class="mini-note" style="margin-top:10px;">IPAdapter note: regular IPAdapter can use the subject masks. FaceID models still need InsightFace installed. Start one identity at a time, around 0.45–0.60 weight.</div><div class="status" id="neo-scene-director-status" style="margin-top:10px;"></div></div></div>`;
    return wrap;
  }
  function loadPreset() { const key = $('neo-scene-director-preset')?.value || 'two'; const data = PRESETS[key] || DEFAULT_SCENE; const box = $('neo-scene-director-json'); if (box) box.value = stringify(data); const note = $('neo-scene-director-mode-note'); if (note) note.value = data.mode || 'relation_focused'; status('Preset loaded. Copy this JSON into the Scene Director node scene_json field, or use a workflow template.'); }
  function bindPanel() { const panel = $('neo-scene-director-assets-accordion'); if (!panel || panel.dataset.neoBound === '1') return; panel.dataset.neoBound = '1'; $('neo-scene-director-preset')?.addEventListener('change', loadPreset); $('neo-scene-director-load-preset')?.addEventListener('click', loadPreset); $('neo-scene-director-copy-json')?.addEventListener('click', () => copyText($('neo-scene-director-json')?.value || '').then(() => status('Scene JSON copied.')).catch(() => status('Copy failed. Select the JSON manually.'))); $('neo-scene-director-download-json')?.addEventListener('click', () => { const key = $('neo-scene-director-preset')?.value || 'scene'; downloadText(`neo_scene_director_${key}_scene.json`, $('neo-scene-director-json')?.value || stringify(DEFAULT_SCENE)); status('Scene JSON downloaded.'); }); loadPreset(); }
  function attachPanel() { const host = $('generation-assets-tab-host'); if (!host) return false; if (!$('neo-scene-director-assets-accordion')) host.prepend(buildPanel()); bindPanel(); return true; }
  function start() { if (attachPanel()) return; let tries = 0; const timer = setInterval(() => { tries += 1; if (attachPanel() || tries > 80) clearInterval(timer); }, 250); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.NeoSceneDirectorAssets = { attachPanel, presets: PRESETS };
})();
