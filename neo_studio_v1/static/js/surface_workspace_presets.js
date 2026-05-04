(function(){
  function $(id){ return document.getElementById(id); }
  function emit(name, detail){ document.dispatchEvent(new CustomEvent(name, { detail })); }
  function setStatusSafe(id, text, level=''){ if (id && typeof window.setStatus === 'function') window.setStatus(id, text, level); }
  function safeGet(key, fallback=''){ try { return window.localStorage.getItem(key) || fallback; } catch(_){ return fallback; } }
  function safeSet(key, value){ try { window.localStorage.setItem(key, value); } catch(_){} }
  function safeRemove(key){ try { window.localStorage.removeItem(key); } catch(_){} }
  function readJson(key, fallback){ try { const raw = window.localStorage.getItem(key); return raw ? (JSON.parse(raw) || fallback) : fallback; } catch(_){ return fallback; } }
  function writeJson(key, value){ try { window.localStorage.setItem(key, JSON.stringify(value)); } catch(_){} }
  function slugify(value){ return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || `preset-${Date.now().toString(36)}`; }
  function uid(prefix){ return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`; }
  function setValue(id, value){ const el = $(id); if (!el) return; el.value = value == null ? '' : String(value); el.dispatchEvent(new Event('input', { bubbles:true })); el.dispatchEvent(new Event('change', { bubbles:true })); }
  function selectedText(id, fallback=''){ return $(id)?.selectedOptions?.[0]?.textContent?.trim() || fallback; }
  function clickManagerLane(lane){ const btn = document.querySelector(`#tab-manager [data-manager-subtab="${lane}"]`); if (btn) btn.click(); }
  function currentManagerLane(){ return document.querySelector('#tab-manager [data-manager-subtab].active')?.dataset.managerSubtab || 'prompt'; }
  function currentRoleplayMode(){ return window.neoRoleplayV2?.currentModeSelection?.() || { output_preset:'roleplay', interaction_mode:'roleplay', goal_label:'Roleplay' }; }

  const CONFIG = {
    video: {
      selectId:'video-shell-preset-select', badgeId:'video-preset-active-badge', statusId:'video-status', event:'neo-video-preset-changed', manualLabel:'Manual setup',
      placeholder:'Workspace presets…', defaultName(){ return `${selectedText('video-mode', 'Text to Video')} · ${selectedText('video-profile', 'Balanced / Low VRAM')}`; },
      builtins:[
        {id:'video_balanced_t2v', name:'Balanced · Text to Video', tone:'primary', snapshot:{ mode:'t2v', profile:'wan22_5b_balanced' }},
        {id:'video_balanced_i2v', name:'Balanced · Image to Video', tone:'specialty', snapshot:{ mode:'i2v', profile:'wan22_5b_balanced' }},
        {id:'video_quality_t2v', name:'High Quality · Text to Video', tone:'warning', snapshot:{ mode:'t2v', profile:'wan22_14b_t2v_quality' }},
        {id:'video_quality_i2v', name:'High Quality · Image to Video', tone:'specialty', snapshot:{ mode:'i2v', profile:'wan22_14b_i2v_quality' }},
      ],
      capture(){
        return {
          mode: $('video-mode')?.value || 't2v',
          profile: $('video-profile')?.value || 'wan22_5b_balanced',
          duration: $('video-duration')?.value || '5',
          fps: $('video-fps')?.value || '16',
          size: $('video-size')?.value || '832x480',
          source_image: $('video-source-image')?.value || '',
          prompt: $('video-prompt')?.value || '',
          negative: $('video-negative')?.value || '',
          seed: $('video-seed')?.value || '',
          post_pipeline_template: $('video-post-pipeline-template')?.value || 'generate_only',
          quality_style_prompt: $('video-quality-style')?.value || '',
          quality_camera_prompt: $('video-quality-camera')?.value || '',
          balanced_unet_name: $('video-balanced-unet')?.value || '',
          balanced_clip_name: $('video-balanced-encoder')?.value || '',
          balanced_vae_name: $('video-balanced-vae')?.value || '',
          quality_high_noise_unet_name: $('video-quality-high-noise-unet')?.value || '',
          quality_low_noise_unet_name: $('video-quality-low-noise-unet')?.value || '',
          quality_clip_name: $('video-quality-encoder')?.value || '',
          quality_vae_name: $('video-quality-vae')?.value || '',
          advanced_adapters_enabled: $('video-adapters-enabled')?.checked ? 'true' : '',
          adapter_pair_preset_id: $('video-adapter-preset-select')?.value || '',
          adapter_single: $('video-adapter-single')?.value || '',
          adapter_high_noise: $('video-adapter-high-noise')?.value || '',
          adapter_low_noise: $('video-adapter-low-noise')?.value || '',
          adapter_strength: $('video-adapter-strength-quality')?.value || $('video-adapter-strength')?.value || '0.8',
          upscale_profile: $('video-upscale-profile')?.value || 'fast_local',
          upscale_target_resolution: $('video-upscale-target')?.value || '1920x1080',
          upscale_fps_mode: $('video-upscale-fps-mode')?.value || 'preserve',
          upscale_output_fps: $('video-upscale-custom-fps')?.value || '24',
          upscale_output_container: $('video-upscale-container')?.value || 'mp4',
          upscale_output_codec: $('video-upscale-codec')?.value || 'auto',
          upscale_source_label: $('video-upscale-source-label')?.value || '',
          repair_strength_preset: $('video-repair-strength')?.value || 'balanced',
          repair_cleanup_focus: $('video-repair-focus')?.value || 'general_cleanup',
          repair_stabilize_temporal: $('video-repair-stabilize')?.checked ? 'true' : '',
          repair_source_label: $('video-repair-source-label')?.value || '',
          interpolation_preset: $('video-interpolate-preset')?.value || '',
          interpolate_target_fps: $('video-interpolate-target-fps')?.value || '30',
          interpolate_multiplier: $('video-interpolate-multiplier')?.value || '2',
          interpolate_quality_mode: $('video-interpolate-quality')?.value || 'balanced',
          interpolate_timing_intent: $('video-interpolate-intent')?.value || 'preserve_timing',
          interpolate_source_label: $('video-interpolate-source-label')?.value || '',
        };
      },
      applySnapshot(snapshot={}){
        const mode = snapshot.mode === 'txt2video' ? 't2v' : snapshot.mode === 'img2video' || snapshot.mode === 'extend' ? 'i2v' : (snapshot.mode || 't2v');
        const profile = snapshot.profile || 'wan22_5b_balanced';
        setValue('video-mode', mode);
        setValue('video-profile', profile);
        setValue('video-duration', snapshot.duration || '5');
        setValue('video-fps', snapshot.fps || '16');
        setValue('video-size', snapshot.size || '832x480');
        setValue('video-source-image', snapshot.source_image || '');
        setValue('video-prompt', snapshot.prompt || '');
        setValue('video-negative', snapshot.negative || '');
        setValue('video-seed', snapshot.seed || '');
        setValue('video-post-pipeline-template', snapshot.post_pipeline_template || 'generate_only');
        setValue('video-quality-style', snapshot.quality_style_prompt || snapshot.quality_style || '');
        setValue('video-quality-camera', snapshot.quality_camera_prompt || snapshot.quality_camera || '');
        setValue('video-balanced-unet', snapshot.balanced_unet_name || '');
        setValue('video-balanced-encoder', snapshot.balanced_clip_name || '');
        setValue('video-balanced-vae', snapshot.balanced_vae_name || '');
        setValue('video-quality-high-noise-unet', snapshot.quality_high_noise_unet_name || '');
        setValue('video-quality-low-noise-unet', snapshot.quality_low_noise_unet_name || '');
        setValue('video-quality-encoder', snapshot.quality_clip_name || '');
        setValue('video-quality-vae', snapshot.quality_vae_name || '');
        const adapterToggle = $('video-adapters-enabled');
        if (adapterToggle) { adapterToggle.checked = String(snapshot.advanced_adapters_enabled || '').toLowerCase() === 'true'; adapterToggle.dispatchEvent(new Event('change', { bubbles:true })); }
        setValue('video-adapter-preset-select', snapshot.adapter_pair_preset_id || '');
        setValue('video-adapter-single', snapshot.adapter_single || '');
        setValue('video-adapter-high-noise', snapshot.adapter_high_noise || '');
        setValue('video-adapter-low-noise', snapshot.adapter_low_noise || '');
        setValue('video-adapter-strength', snapshot.adapter_strength || '0.8');
        setValue('video-adapter-strength-quality', snapshot.adapter_strength || '0.8');
        setValue('video-upscale-profile', snapshot.upscale_profile || 'fast_local');
        setValue('video-upscale-target', snapshot.upscale_target_resolution || '1920x1080');
        setValue('video-upscale-fps-mode', snapshot.upscale_fps_mode || 'preserve');
        setValue('video-upscale-custom-fps', snapshot.upscale_output_fps || '24');
        setValue('video-upscale-container', snapshot.upscale_output_container || 'mp4');
        setValue('video-upscale-codec', snapshot.upscale_output_codec || 'auto');
        setValue('video-upscale-source-label', snapshot.upscale_source_label || '');
        setValue('video-repair-strength', snapshot.repair_strength_preset || 'balanced');
        setValue('video-repair-focus', snapshot.repair_cleanup_focus || 'general_cleanup');
        const repairStabilize = $('video-repair-stabilize'); if (repairStabilize) { repairStabilize.checked = String(snapshot.repair_stabilize_temporal || '').trim() === 'true'; repairStabilize.dispatchEvent(new Event('change', { bubbles:true })); }
        setValue('video-repair-source-label', snapshot.repair_source_label || '');
        setValue('video-interpolate-preset', snapshot.interpolation_preset || '');
        setValue('video-interpolate-target-fps', snapshot.interpolate_target_fps || '30');
        setValue('video-interpolate-multiplier', snapshot.interpolate_multiplier || '2');
        setValue('video-interpolate-quality', snapshot.interpolate_quality_mode || 'balanced');
        setValue('video-interpolate-intent', snapshot.interpolate_timing_intent || 'preserve_timing');
        setValue('video-interpolate-source-label', snapshot.interpolate_source_label || '');
        window.neoRefreshVideoSurface?.();
      },
    },
    voice: {
      selectId:'voice-shell-preset-select', badgeId:'voice-preset-active-badge', statusId:'voice-status', event:'neo-voice-preset-changed', manualLabel:'Manual setup',
      placeholder:'Workspace presets…', defaultName(){ return `${selectedText('voice-style', 'Clean narrator')} · ${selectedText('voice-job-type', 'Text to speech')}`; },
      builtins:[
        {id:'voice_clean_tts', name:'Clean TTS', tone:'primary', snapshot:{ 'voice-style':'clean', 'voice-job-type':'tts' }},
        {id:'voice_warm_narration', name:'Warm narration', tone:'success', snapshot:{ 'voice-style':'warm', 'voice-job-type':'tts' }},
        {id:'voice_character_preview', name:'Character preview', tone:'specialty', snapshot:{ 'voice-style':'character', 'voice-job-type':'preview' }},
      ],
      capture(){
        const payload = {};
        ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => payload[id] = $(id)?.value || '');
        return payload;
      },
      applySnapshot(snapshot={}){
        ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => setValue(id, snapshot[id] || (id === 'voice-job-type' ? 'tts' : id === 'voice-style' ? 'clean' : id === 'voice-speed' ? '1.0' : '')));
        window.neoRefreshVoiceSurface?.();
      },
    },
    audio: {
      selectId:'audio-shell-preset-select', badgeId:'audio-preset-active-badge', statusId:'audio-status', event:'neo-audio-preset-changed', manualLabel:'Manual setup',
      placeholder:'Workspace presets…', defaultName(){ return `${selectedText('audio-job-type', 'Music')} · ${selectedText('audio-format', 'WAV')}`; },
      builtins:[
        {id:'audio_music_wav', name:'Music cue · WAV', tone:'primary', snapshot:{ 'audio-job-type':'music', 'audio-format':'wav' }},
        {id:'audio_sfx_flac', name:'SFX design · FLAC', tone:'specialty', snapshot:{ 'audio-job-type':'sfx', 'audio-format':'flac' }},
        {id:'audio_ambience_mp3', name:'Ambience bed · MP3', tone:'recovery', snapshot:{ 'audio-job-type':'ambience', 'audio-format':'mp3' }},
      ],
      capture(){
        const payload = {};
        ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => payload[id] = $(id)?.value || '');
        return payload;
      },
      applySnapshot(snapshot={}){
        ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => setValue(id, snapshot[id] || (id === 'audio-job-type' ? 'music' : id === 'audio-length' ? '15' : id === 'audio-bpm' ? '96' : id === 'audio-format' ? 'wav' : '')));
        window.neoRefreshAudioSurface?.();
      },
    },
    manager: {
      selectId:'manager-shell-preset-select', badgeId:'manager-preset-active-badge', statusId:'manager-shell-preset-status', event:'neo-manager-preset-changed', manualLabel:'Manual setup',
      placeholder:'Workspace presets…', defaultName(){ return `${selectedText('manager-lane-select', '') || (currentManagerLane() === 'caption' ? 'Caption Studio' : currentManagerLane() === 'library' ? 'Library' : 'Prompt Studio')} shell`; },
      builtins:[
        {id:'manager_prompt_focus', name:'Prompt Studio focus', tone:'primary', snapshot:{ lane:'prompt' }},
        {id:'manager_caption_focus', name:'Caption Studio focus', tone:'specialty', snapshot:{ lane:'caption' }},
        {id:'manager_library_review', name:'Library review', tone:'recovery', snapshot:{ lane:'library' }},
      ],
      capture(){ return { lane: currentManagerLane() }; },
      applySnapshot(snapshot={}){ clickManagerLane(snapshot.lane || 'prompt'); },
    },
    assistant: {
      selectId:'assistant-shell-preset-select', badgeId:'assistant-preset-active-badge', statusId:'assistant-shell-preset-status', event:'neo-assistant-preset-changed', manualLabel:'Manual setup',
      placeholder:'Workspace presets…', defaultName(){ return selectedText('assistant-mode', 'General help'); },
      builtins:[
        {id:'assistant_general', name:'General help', tone:'primary', snapshot:{ mode:'general' }},
        {id:'assistant_support', name:'Support pass', tone:'success', snapshot:{ mode:'support' }},
        {id:'assistant_creative', name:'Creative pass', tone:'specialty', snapshot:{ mode:'creative' }},
        {id:'assistant_analysis', name:'Analysis pass', tone:'recovery', snapshot:{ mode:'analysis' }},
      ],
      capture(){ return { mode: $('assistant-mode')?.value || 'general' }; },
      applySnapshot(snapshot={}){ setValue('assistant-mode', snapshot.mode || 'general'); },
    },
  };

  function selectedKey(surface){ return `neo-${surface}-workspace-preset-selected`; }
  function defaultKey(surface){ return `neo-${surface}-workspace-preset-default`; }
  function activeKey(surface){ return `neo-${surface}-workspace-preset-active`; }
  function savedKey(surface){ return `neo-${surface}-workspace-presets`; }
  function selectedRef(surface){ return safeGet(selectedKey(surface), ''); }
  function defaultRef(surface){ return safeGet(defaultKey(surface), ''); }
  function activeRef(surface){ return safeGet(activeKey(surface), ''); }
  function setSelectedRef(surface, ref){ if (ref) safeSet(selectedKey(surface), ref); else safeRemove(selectedKey(surface)); }
  function setDefaultRef(surface, ref){ if (ref) safeSet(defaultKey(surface), ref); else safeRemove(defaultKey(surface)); }
  function setActiveRef(surface, ref){ if (ref) safeSet(activeKey(surface), ref); else safeRemove(activeKey(surface)); }
  function getSaved(surface){
    const raw = readJson(savedKey(surface), []);
    return Array.isArray(raw) ? raw.filter(item => item && typeof item === 'object' && String(item.id || '').trim()) : [];
  }
  function setSaved(surface, items){ writeJson(savedKey(surface), Array.isArray(items) ? items : []); }
  function builtinRef(id){ return `builtin:${id}`; }
  function savedRef(id){ return `saved:${id}`; }

  function resolveItem(surface, ref){
    const cfg = CONFIG[surface];
    if (!cfg || !ref) return null;
    const clean = String(ref || '').trim();
    if (clean.startsWith('builtin:')) {
      const id = clean.slice(8);
      const item = (cfg.builtins || []).find(row => String(row.id) === id);
      return item ? { ...item, ref: clean, type: 'builtin', name: item.name || item.label || id } : null;
    }
    if (clean.startsWith('saved:')) {
      const id = clean.slice(6);
      const item = getSaved(surface).find(row => String(row.id) === id);
      return item ? { ...item, ref: clean, type: 'saved', tone: item.tone || 'neutral', name: item.name || 'Untitled preset' } : null;
    }
    return null;
  }

  function emitPreset(surface, ref){
    const cfg = CONFIG[surface];
    const item = resolveItem(surface, ref);
    emit(cfg.event, { presetId: ref || '', tone: item?.tone || 'neutral', label: item?.name || cfg.manualLabel || 'Manual setup' });
  }

  function updateBadge(surface, ref){
    const cfg = CONFIG[surface];
    const badge = $(cfg.badgeId);
    if (!badge) return;
    const item = resolveItem(surface, ref);
    badge.textContent = item?.name || cfg.manualLabel || 'Manual setup';
    badge.dataset.uiTone = item?.tone || 'neutral';
  }

  function buildSelect(surface){
    const cfg = CONFIG[surface];
    const select = $(cfg.selectId);
    if (!select) return;
    select.innerHTML = '';
    const base = document.createElement('option');
    base.value = '';
    base.textContent = cfg.placeholder || 'Workspace presets…';
    select.appendChild(base);
    const builtinGroup = document.createElement('optgroup');
    builtinGroup.label = 'Built-in starters';
    (cfg.builtins || []).forEach(item => {
      const opt = document.createElement('option');
      opt.value = builtinRef(item.id);
      opt.textContent = item.name || item.label || item.id;
      builtinGroup.appendChild(opt);
    });
    select.appendChild(builtinGroup);
    const savedItems = getSaved(surface);
    if (savedItems.length) {
      const savedGroup = document.createElement('optgroup');
      savedGroup.label = 'Saved workspace presets';
      savedItems.forEach(item => {
        const opt = document.createElement('option');
        opt.value = savedRef(item.id);
        opt.textContent = item.name || 'Untitled preset';
        savedGroup.appendChild(opt);
      });
      select.appendChild(savedGroup);
    }
    const preferred = selectedRef(surface) || activeRef(surface) || defaultRef(surface) || '';
    if (preferred && resolveItem(surface, preferred)) select.value = preferred;
  }

  function refreshButtons(surface){
    const cfg = CONFIG[surface];
    const ref = $(cfg.selectId)?.value || '';
    const item = resolveItem(surface, ref);
    const updateBtn = $(cfg.updateBtnId || `btn-${surface}-update-preset`);
    const deleteBtn = $(cfg.deleteBtnId || `btn-${surface}-delete-preset`);
    if (updateBtn) updateBtn.disabled = !(item && item.type === 'saved');
    if (deleteBtn) deleteBtn.disabled = !(item && item.type === 'saved');
  }

  function syncSurface(surface){
    buildSelect(surface);
    updateBadge(surface, activeRef(surface));
    emitPreset(surface, activeRef(surface));
    refreshButtons(surface);
  }

  function applyPreset(surface, ref, { announce = true } = {}){
    const cfg = CONFIG[surface];
    const item = resolveItem(surface, ref);
    if (!item) {
      setActiveRef(surface, '');
      updateBadge(surface, '');
      emitPreset(surface, '');
      if (announce) setStatusSafe(cfg.statusId, 'Workspace preset selection cleared. Current UI stays manual.', 'ok');
      refreshButtons(surface);
      return;
    }
    cfg.applySnapshot(item.snapshot || {});
    setSelectedRef(surface, item.ref);
    setActiveRef(surface, item.ref);
    const select = $(cfg.selectId);
    if (select) select.value = item.ref;
    updateBadge(surface, item.ref);
    emitPreset(surface, item.ref);
    refreshButtons(surface);
    if (announce) setStatusSafe(cfg.statusId, `${item.type === 'builtin' ? 'Loaded starter preset' : 'Loaded workspace preset'}: ${item.name || 'Untitled preset'}`, 'ok');
  }

  function savePreset(surface, { updateExisting = false } = {}){
    const cfg = CONFIG[surface];
    const currentRef = $(cfg.selectId)?.value || selectedRef(surface) || activeRef(surface) || '';
    const currentItem = resolveItem(surface, currentRef);
    if (updateExisting && (!currentItem || currentItem.type !== 'saved')) {
      setStatusSafe(cfg.statusId, 'Pick a saved workspace preset first if you want to update one.', 'warn');
      return;
    }
    const snapshot = cfg.capture();
    const suggested = currentItem?.name || cfg.defaultName?.() || `${surface} workspace preset`;
    const promptText = updateExisting ? 'Update this workspace preset name if needed:' : 'Name this workspace preset:';
    const nextName = String(window.prompt(promptText, suggested) || '').trim();
    if (!nextName) {
      setStatusSafe(cfg.statusId, 'Workspace preset save cancelled.', 'warn');
      return;
    }
    const items = getSaved(surface);
    let target;
    if (updateExisting && currentItem) {
      target = items.find(row => String(row.id) === String(currentItem.id));
      if (!target) {
        setStatusSafe(cfg.statusId, 'That workspace preset no longer exists in this browser.', 'warn');
        return;
      }
      target.name = nextName;
      target.snapshot = snapshot;
      target.updated_at = new Date().toISOString();
    } else {
      target = {
        id: slugify(uid(surface)),
        name: nextName,
        snapshot,
        tone: currentItem?.tone || 'neutral',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      items.push(target);
    }
    setSaved(surface, items);
    const ref = savedRef(target.id);
    setSelectedRef(surface, ref);
    setActiveRef(surface, ref);
    syncSurface(surface);
    applyPreset(surface, ref, { announce: false });
    setStatusSafe(cfg.statusId, `${updateExisting ? 'Updated' : 'Saved'} workspace preset: ${nextName}`, 'ok');
  }

  function deletePreset(surface){
    const cfg = CONFIG[surface];
    const ref = $(cfg.selectId)?.value || '';
    const item = resolveItem(surface, ref);
    if (!item || item.type !== 'saved') {
      setStatusSafe(cfg.statusId, 'Pick a saved workspace preset first.', 'warn');
      return;
    }
    if (!window.confirm(`Delete workspace preset "${item.name || 'Untitled preset'}"?`)) return;
    const items = getSaved(surface).filter(row => String(row.id) !== String(item.id));
    setSaved(surface, items);
    if (selectedRef(surface) === item.ref) setSelectedRef(surface, '');
    if (activeRef(surface) === item.ref) setActiveRef(surface, '');
    if (defaultRef(surface) === item.ref) setDefaultRef(surface, '');
    syncSurface(surface);
    setStatusSafe(cfg.statusId, `Deleted workspace preset: ${item.name || 'Untitled preset'}`, 'ok');
  }

  function setDefaultPreset(surface){
    const cfg = CONFIG[surface];
    const ref = $(cfg.selectId)?.value || '';
    const item = resolveItem(surface, ref);
    if (!item) {
      setStatusSafe(cfg.statusId, 'Pick a workspace preset first.', 'warn');
      return;
    }
    setDefaultRef(surface, item.ref);
    setStatusSafe(cfg.statusId, `Default workspace preset set: ${item.name || 'Untitled preset'}`, 'ok');
  }

  function clearDefaultPreset(surface){
    const cfg = CONFIG[surface];
    setDefaultRef(surface, '');
    setStatusSafe(cfg.statusId, 'Default workspace preset cleared.', 'ok');
  }

  function bindSurface(surface){
    const cfg = CONFIG[surface];
    if (!$(cfg.selectId)) return;
    syncSurface(surface);
    $(cfg.selectId)?.addEventListener('change', event => {
      const ref = String(event?.target?.value || '').trim();
      setSelectedRef(surface, ref);
      refreshButtons(surface);
    });
    $(cfg.loadBtnId || `btn-${surface}-load-preset`)?.addEventListener('click', () => applyPreset(surface, $(cfg.selectId)?.value || '', { announce: true }));
    $(cfg.saveBtnId || `btn-${surface}-save-preset`)?.addEventListener('click', () => savePreset(surface, { updateExisting:false }));
    $(cfg.updateBtnId || `btn-${surface}-update-preset`)?.addEventListener('click', () => savePreset(surface, { updateExisting:true }));
    $(cfg.deleteBtnId || `btn-${surface}-delete-preset`)?.addEventListener('click', () => deletePreset(surface));
    $(cfg.defaultBtnId || `btn-${surface}-set-default-preset`)?.addEventListener('click', () => setDefaultPreset(surface));
    $(cfg.clearDefaultBtnId || `btn-${surface}-clear-default-preset`)?.addEventListener('click', () => clearDefaultPreset(surface));

    const startupRef = activeRef(surface) || defaultRef(surface) || '';
    if (startupRef && resolveItem(surface, startupRef)) {
      const select = $(cfg.selectId);
      if (select) select.value = startupRef;
      applyPreset(surface, startupRef, { announce:false });
    }
  }

  function bind(){ Object.keys(CONFIG).forEach(bindSurface); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
