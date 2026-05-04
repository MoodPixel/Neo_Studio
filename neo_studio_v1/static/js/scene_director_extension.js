(function () {
  const EXTENSION_ID = 'image.scene_director';
  const ALLOWED_FAMILIES = new Set(['sdxl_sd', 'sdxl', 'sd', 'sd15', 'sd1.5']);
  const BLOCKED_FAMILIES = new Set(['flux', 'qwen', 'qwen_image_edit', 'zimage']);
  const STATE_KEY = 'neo_scene_director_ui_state_v1';
  const DEFAULT_CONTRACTS = {
    enabled: true,
    use_node_auto_prompts: false,
    count_contract: 'exactly {count} visible subjects, one subject per enabled region, no extra subjects',
    subject_contract: 'one complete subject inside this region, not merged, not duplicated',
    negative_contract: 'extra people, missing subject, wrong number of subjects, merged bodies, fused faces',
    style_merge: 'use Neo main prompt as the scene style and composition intent'
  };


  const REGION_LAYOUT_PRESETS = {
    'one_person': { label: '1 Person', description: 'Centered portrait / full body single subject.', regions: [
      { label: 'Person 1', type: 'character', rect: { x: 0.33, y: 0.10, w: 0.34, h: 0.78 }, prompt: 'main subject, centered, clean silhouette' },
    ] },
    'two_side_by_side': { label: '2 People Side-by-Side', description: 'Balanced duo with clean identity separation.', regions: [
      { label: 'Person 1', type: 'character', rect: { x: 0.12, y: 0.13, w: 0.31, h: 0.74 }, prompt: 'left subject, clear individual identity' },
      { label: 'Person 2', type: 'character', rect: { x: 0.57, y: 0.13, w: 0.31, h: 0.74 }, prompt: 'right subject, clear individual identity' },
    ] },
    'two_close_interaction': { label: '2 People Close Interaction', description: 'Closer interaction layout with safer separated masks.', regions: [
      { label: 'Person 1', type: 'character', rect: { x: 0.08, y: 0.12, w: 0.42, h: 0.76 }, prompt: 'left foreground subject, interacting naturally' },
      { label: 'Person 2', type: 'character', rect: { x: 0.50, y: 0.12, w: 0.42, h: 0.76 }, prompt: 'right foreground subject, interacting naturally' },
    ] },
    'three_triangle': { label: '3 Triangle', description: 'Three-person triangle grouping with center focus.', regions: [
      { label: 'Person 1', type: 'character', rect: { x: 0.35, y: 0.08, w: 0.30, h: 0.56 }, prompt: 'center back subject, primary focus' },
      { label: 'Person 2', type: 'character', rect: { x: 0.10, y: 0.34, w: 0.30, h: 0.56 }, prompt: 'front left subject, separated identity' },
      { label: 'Person 3', type: 'character', rect: { x: 0.60, y: 0.34, w: 0.30, h: 0.56 }, prompt: 'front right subject, separated identity' },
    ] },
    'four_grid': { label: '4 Grid', description: 'Four-region lineup/grid for groups or character sheets.', regions: [
      { label: 'Person 1', type: 'character', rect: { x: 0.07, y: 0.12, w: 0.20, h: 0.74 }, prompt: 'far left subject' },
      { label: 'Person 2', type: 'character', rect: { x: 0.29, y: 0.12, w: 0.20, h: 0.74 }, prompt: 'left center subject' },
      { label: 'Person 3', type: 'character', rect: { x: 0.51, y: 0.12, w: 0.20, h: 0.74 }, prompt: 'right center subject' },
      { label: 'Person 4', type: 'character', rect: { x: 0.73, y: 0.12, w: 0.20, h: 0.74 }, prompt: 'far right subject' },
    ] },
    'interview_setup': { label: 'Interview Setup', description: 'Host + guest framing with seated conversation spacing.', regions: [
      { label: 'Host', type: 'character', rect: { x: 0.10, y: 0.22, w: 0.32, h: 0.62 }, prompt: 'host, seated or standing, engaged expression' },
      { label: 'Guest', type: 'character', rect: { x: 0.58, y: 0.22, w: 0.32, h: 0.62 }, prompt: 'guest, seated or standing, engaged expression' },
    ] },
    'product_model': { label: 'Product + Model', description: 'Human subject plus product/object hero region.', regions: [
      { label: 'Model', type: 'character', rect: { x: 0.12, y: 0.12, w: 0.36, h: 0.76 }, prompt: 'model presenting the product' },
      { label: 'Product', type: 'object', rect: { x: 0.56, y: 0.32, w: 0.32, h: 0.36 }, prompt: 'hero product, sharp details, clean readable shape' },
    ] },
  };

  const MIN_RECT_SIZE = 0.035;
  let selectedRegionId = null;
  let activeInteraction = null;

  let mounted = false;
  let registryRecord = null;
  let regions = [];
  let identityProfiles = [];
  let loadedIdentityProfileCache = new Map();

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) { return document.getElementById(id); }

  function isSceneDirectorEnabled() {
    return !!$('neo-scene-director-enabled')?.checked;
  }

  function makeEl(tag, className = '', html = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html) el.innerHTML = html;
    return el;
  }

  function getFamily() {
    return String($('generation-family')?.value || 'sdxl_sd').trim().toLowerCase();
  }

  function getWorkflowMode() {
    return String($('generation-workflow-type')?.value || 'txt2img').trim().toLowerCase();
  }

  function getSceneDirectorModePolicy(mode = getWorkflowMode()) {
    if (mode === 'outpaint') {
      return {
        supported: false,
        reason: 'outpaint_not_supported',
        message: 'Scene Director is not used for outpaint. Outpaint uses the source canvas expansion editor instead.',
      };
    }
    if (mode === 'txt2img' || mode === 'img2img' || mode === 'inpaint') {
      return { supported: true, reason: '', message: '' };
    }
    return {
      supported: false,
      reason: 'unsupported_mode_' + mode,
      message: 'Scene Director is not applied to this workflow mode yet.',
    };
  }

  function getSize() {
    const width = Math.max(64, parseInt($('generation-width')?.value || '1024', 10) || 1024);
    const height = Math.max(64, parseInt($('generation-height')?.value || '1024', 10) || 1024);
    return { width, height };
  }

  function isAllowedFamily(family = getFamily()) {
    if (BLOCKED_FAMILIES.has(family)) return false;
    return ALLOWED_FAMILIES.has(family);
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STATE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      regions = Array.isArray(parsed.regions) ? parsed.regions : [];
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      regions = [];
      return {};
    }
  }

  function saveState(extra = {}) {
    const enabled = !!$('neo-scene-director-enabled')?.checked;
    const contracts = extra.contracts || (document.getElementById('neo-scene-count-contract') ? getPromptContracts() : undefined);
    // Keep localStorage and the hidden payload in sync with the live region array.
    // Phase 10.3 hotfix: manual canvas edits must win over the last clicked layout preset.
    regions = regions.map((region, index) => normalizeRegionData(region, index));
    const state = { enabled, regions, ...(contracts ? { contracts } : {}), ...extra };
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (_) {}
    const stateNode = $('neo-scene-director-state');
    if (stateNode) stateNode.value = JSON.stringify(state);
    window.NeoSceneDirectorExtension.state = state;
    window.dispatchEvent(new CustomEvent('neo-scene-director-regions-updated', { detail: getSceneRegionTargets() }));
    if (window.NeoStudioApp?.generation?.workflow?.refreshLoraApplyTargets) window.NeoStudioApp.generation.workflow.refreshLoraApplyTargets();
    if ($('neo-scene-director-state')) syncPromptPayload();
  }

  function getSceneRegionTargets() {
    return regions.map((region, index) => normalizeRegionData(region, index))
      .filter(region => region.enabled && region.visible !== false)
      .map((region, index) => ({
        value: `scene_region_${index + 1}`,
        region_index: index + 1,
        id: region.id,
        label: region.label || `Region ${index + 1}`
      }));
  }

  async function fetchRecord() {
    try {
      const res = await fetch(`/api/extensions/packs?target_surface=image&workspace=assets&_=${Date.now()}`, { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.ok) return null;
      return (data.packs || []).find(pack => pack.extension_id === EXTENSION_ID || pack.id === EXTENSION_ID) || null;
    } catch (_) {
      return null;
    }
  }

  async function setExtensionEnabled(enabled) {
    try {
      const res = await fetch('/api/extensions/packs/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extension_id: EXTENSION_ID, enabled: !!enabled }),
      });
      const data = await res.json();
      if (data && data.ok && data.record) registryRecord = data.record;
      setStatus(enabled ? summarizePromptReadiness() : 'Scene Director disabled. Normal Neo generation remains untouched.', enabled ? 'ok' : 'muted');
    } catch (_) {
      setStatus('Could not update the extension registry toggle. Local UI state was still saved.', 'warn');
    }
  }

  function setStatus(text, tone = 'muted') {
    const node = $('neo-scene-director-status');
    if (!node) return;
    node.textContent = text || '';
    node.dataset.tone = tone;
  }

  function canvasLabel(width, height) {
    if (width === height) return 'Square';
    return width > height ? 'Landscape' : 'Vertical';
  }


  function normalizeIdentityProfileSummary(item) {
    const safe = item && typeof item === 'object' ? item : {};
    return {
      id: String(safe.id || safe.slug || safe.profile_name || safe.name || '').trim(),
      slug: String(safe.slug || safe.id || safe.profile_name || safe.name || '').trim(),
      name: String(safe.profile_name || safe.name || safe.id || safe.slug || 'Identity Profile').trim(),
      mode: String(safe.ipadapter_mode || safe.mode || 'faceid').trim().toLowerCase(),
      reference_count: Number(safe.reference_count || 0) || 0,
      has_lora: !!safe.has_lora,
    };
  }

  function normalizeIdentityProfile(profile) {
    const safe = profile && typeof profile === 'object' ? profile : {};
    const name = String(safe.profile_name || safe.name || safe.id || '').trim();
    const refs = Array.isArray(safe.reference_images) ? safe.reference_images.map(item => String(item || '').trim()).filter(Boolean) : [];
    const lora = safe.lora && typeof safe.lora === 'object' ? safe.lora : {};
    return {
      id: String(safe.id || name || '').trim(),
      profile_name: name || 'Identity Profile',
      name: name || 'Identity Profile',
      ipadapter_mode: String(safe.ipadapter_mode || safe.mode || 'faceid').trim().toLowerCase() || 'faceid',
      ipadapter_model: String(safe.ipadapter_model || safe.model || '').trim(),
      clip_vision_model: String(safe.clip_vision_model || safe.clip_vision || 'auto').trim() || 'auto',
      reference_images: refs,
      weight: clamp(Number(safe.weight ?? 0.45), 0, 2),
      start_at: clamp(Number(safe.start_at ?? 0), 0, 1),
      end_at: clamp(Number(safe.end_at ?? 0.65), 0, 1),
      lora: { name: String(lora.name || '').trim(), weight: clamp(Number(lora.weight ?? 0.8), 0, 2) },
      trigger_words: String(safe.trigger_words || '').trim(),
      notes: String(safe.notes || '').trim(),
    };
  }

  function getIdentityProfileById(id) {
    const key = String(id || '').trim();
    if (!key) return null;
    return loadedIdentityProfileCache.get(key) || identityProfiles.find(item => item.id === key || item.slug === key || item.name === key) || null;
  }

  function buildIdentityProfileOptions(current='') {
    const active = String(current || '').trim();
    const rows = ['<option value="">None / manual IPAdapter</option>'];
    identityProfiles.forEach(profile => {
      const value = profile.slug || profile.id || profile.name;
      const bits = [profile.name, profile.mode === 'faceid' ? 'FaceID' : 'IPAdapter'];
      if (profile.reference_count) bits.push(profile.reference_count + ' ref');
      rows.push(`<option value="${escapeHtml(value)}" ${String(value) === active || String(profile.id) === active ? 'selected' : ''}>${escapeHtml(bits.join(' · '))}</option>`);
    });
    return rows.join('');
  }

  function profileStorageNote() {
    return 'Profiles are stored locally under neo_library_data/studio_user_data/identity_profiles. Reference image entries should match Comfy input filenames/paths for now.';
  }

  function getIdentityProfileFormPayload() {
    const name = String($('neo-identity-profile-name')?.value || '').trim();
    const mode = String($('neo-identity-profile-mode')?.value || 'faceid').trim().toLowerCase();
    const refs = String($('neo-identity-profile-refs')?.value || '').split(/\r?\n|,/).map(item => item.trim()).filter(Boolean);
    return normalizeIdentityProfile({
      id: $('neo-identity-profile-id')?.value || name,
      profile_name: name,
      name,
      ipadapter_mode: mode,
      ipadapter_model: mode === 'faceid' ? 'ip-adapter-faceid-plusv2_sdxl.bin' : 'ip-adapter-plus_sdxl_vit-h.safetensors',
      clip_vision_model: $('neo-identity-profile-clip')?.value || 'auto',
      reference_images: refs,
      weight: Number($('neo-identity-profile-weight')?.value || 0.45),
      start_at: Number($('neo-identity-profile-start')?.value || 0),
      end_at: Number($('neo-identity-profile-end')?.value || 0.65),
      lora: { name: $('neo-identity-profile-lora')?.value || '', weight: Number($('neo-identity-profile-lora-weight')?.value || 0.8) },
      trigger_words: $('neo-identity-profile-triggers')?.value || '',
      notes: $('neo-identity-profile-notes')?.value || '',
    });
  }

  function setIdentityProfileForm(profile={}) {
    const safe = normalizeIdentityProfile(profile);
    if ($('neo-identity-profile-id')) $('neo-identity-profile-id').value = safe.id || '';
    if ($('neo-identity-profile-name')) $('neo-identity-profile-name').value = safe.profile_name === 'Identity Profile' ? '' : safe.profile_name;
    if ($('neo-identity-profile-mode')) $('neo-identity-profile-mode').value = safe.ipadapter_mode || 'faceid';
    if ($('neo-identity-profile-refs')) $('neo-identity-profile-refs').value = (safe.reference_images || []).join('\n');
    if ($('neo-identity-profile-clip')) $('neo-identity-profile-clip').value = safe.clip_vision_model || 'auto';
    if ($('neo-identity-profile-weight')) $('neo-identity-profile-weight').value = Number(safe.weight ?? 0.45);
    if ($('neo-identity-profile-start')) $('neo-identity-profile-start').value = Number(safe.start_at ?? 0);
    if ($('neo-identity-profile-end')) $('neo-identity-profile-end').value = Number(safe.end_at ?? 0.65);
    if ($('neo-identity-profile-lora')) $('neo-identity-profile-lora').value = safe.lora?.name || '';
    if ($('neo-identity-profile-lora-weight')) $('neo-identity-profile-lora-weight').value = Number(safe.lora?.weight ?? 0.8);
    if ($('neo-identity-profile-triggers')) $('neo-identity-profile-triggers').value = safe.trigger_words || '';
    if ($('neo-identity-profile-notes')) $('neo-identity-profile-notes').value = safe.notes || '';
  }

  async function refreshIdentityProfiles(selectValue='') {
    try {
      const res = await fetch('/api/scene-director/identity-profiles', { cache: 'no-store' });
      const data = await res.json();
      identityProfiles = data && data.ok && Array.isArray(data.profiles) ? data.profiles.map(normalizeIdentityProfileSummary) : [];
      const select = $('neo-identity-profile-select');
      if (select) {
        select.innerHTML = '<option value="">Select profile...</option>' + identityProfiles.map(profile => `<option value="${escapeHtml(profile.slug || profile.id || profile.name)}">${escapeHtml(profile.name)} · ${escapeHtml(profile.mode === 'faceid' ? 'FaceID' : 'IPAdapter')} · ${profile.reference_count || 0} ref</option>`).join('');
        if (selectValue) select.value = selectValue;
      }
      renderRegions();
      return identityProfiles;
    } catch (_) {
      setStatus('Could not refresh Identity Profiles.', 'warn');
      return [];
    }
  }

  async function loadIdentityProfile(key='') {
    const profileKey = String(key || $('neo-identity-profile-select')?.value || '').trim();
    if (!profileKey) { setStatus('Choose an Identity Profile to load.', 'warn'); return null; }
    try {
      const res = await fetch('/api/scene-director/identity-profiles/' + encodeURIComponent(profileKey), { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Load failed');
      const profile = normalizeIdentityProfile(data.profile || {});
      loadedIdentityProfileCache.set(profileKey, profile);
      loadedIdentityProfileCache.set(profile.id, profile);
      loadedIdentityProfileCache.set(data.meta?.slug || profileKey, profile);
      setIdentityProfileForm(profile);
      setStatus(`Loaded Identity Profile: ${profile.profile_name}`, 'ok');
      renderRegions();
      return profile;
    } catch (err) {
      setStatus(`Could not load Identity Profile. ${err?.message || ''}`.trim(), 'warn');
      return null;
    }
  }

  async function saveIdentityProfile() {
    const profile = getIdentityProfileFormPayload();
    const name = profile.profile_name;
    if (!name || name === 'Identity Profile') { setStatus('Identity Profile name is required before saving.', 'warn'); return; }
    try {
      const res = await fetch('/api/scene-director/identity-profiles', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, profile }),
      });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Save failed');
      const slug = data.profile?.slug || profile.id || name;
      loadedIdentityProfileCache.set(slug, profile);
      loadedIdentityProfileCache.set(profile.id, profile);
      await refreshIdentityProfiles(slug);
      setStatus(`Saved Identity Profile: ${name}`, 'ok');
    } catch (err) {
      setStatus(`Could not save Identity Profile. ${err?.message || ''}`.trim(), 'warn');
    }
  }

  async function deleteIdentityProfile() {
    const key = String($('neo-identity-profile-select')?.value || $('neo-identity-profile-id')?.value || $('neo-identity-profile-name')?.value || '').trim();
    if (!key) { setStatus('Choose an Identity Profile to delete.', 'warn'); return; }
    try {
      const res = await fetch('/api/scene-director/identity-profiles/' + encodeURIComponent(key), { method: 'DELETE' });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Delete failed');
      loadedIdentityProfileCache.delete(key);
      setIdentityProfileForm({});
      await refreshIdentityProfiles();
      setStatus('Deleted Identity Profile.', 'ok');
    } catch (err) {
      setStatus(`Could not delete Identity Profile. ${err?.message || ''}`.trim(), 'warn');
    }
  }

  function buildSceneDirectorIdentityUnits(normalizedRegions) {
    const units = [];
    let characterSlot = 0;
    normalizedRegions.filter(region => region.enabled && region.visible !== false).forEach((region) => {
      const isCharacter = String(region.type || 'character').toLowerCase() !== 'object';
      if (isCharacter) characterSlot += 1;
      if (!isCharacter || !region.identity_profile_id) return;
      const profile = getIdentityProfileById(region.identity_profile_id) || region.identity_profile || null;
      if (!profile) return;
      const safe = normalizeIdentityProfile(profile);
      const imageNames = Array.isArray(safe.reference_images) ? safe.reference_images.filter(Boolean) : [];
      units.push({
        region_id: region.id,
        region_index: characterSlot,
        label: region.label,
        profile_id: region.identity_profile_id,
        profile_name: safe.profile_name,
        mode: safe.ipadapter_mode,
        reference_images: imageNames,
        image_name: imageNames[0] || '',
        image_names: imageNames,
        model: safe.ipadapter_mode === 'faceid' ? (safe.ipadapter_model || 'ip-adapter-faceid-plusv2_sdxl.bin') : (safe.ipadapter_model || 'ip-adapter-plus_sdxl_vit-h.safetensors'),
        clip_vision: safe.clip_vision_model,
        weight: safe.weight,
        weight_faceidv2: safe.weight_faceidv2 || safe.weight,
        start_at: safe.start_at,
        end_at: safe.end_at,
        lora: safe.lora,
        trigger_words: safe.trigger_words,
        use_region_mask: true,
        attn_mask_output_index: 5 + characterSlot,
        composer_mode: 'identity_profile',
      });
    });
    return units;
  }



  function getIpAdapterSlotInfo(slotNumber) {
    const slot = Math.max(1, Math.min(8, parseInt(slotNumber || '1', 10) || 1));
    let row = null;
    let enabled = false;
    let mode = 'standard';
    let model = '';
    let clipVision = '';
    let refCount = 0;
    let weight = 1;
    let faceWeight = 1;
    let facePreset = '';
    if (slot === 1) {
      row = document.querySelector('.generation-unit-card-ipadapter[data-primary="true"]');
      enabled = !!$('generation-ipadapter-enabled')?.checked;
      mode = String($('generation-ipadapter-mode')?.value || 'standard').toLowerCase();
      model = String($('generation-ipadapter-name')?.value || '').trim();
      clipVision = String($('generation-ipadapter-clip-vision')?.value || '').trim();
      weight = Number($('generation-ipadapter-weight')?.value || 1);
      faceWeight = Number($('generation-ipadapter-weight-faceidv2')?.value || weight || 1);
      facePreset = String($('generation-ipadapter-faceid-preset')?.value || '').trim();
      refCount = $('generation-ipadapter-image')?.files?.length || 0;
    } else {
      row = Array.from(document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row'))[slot - 2] || null;
      enabled = !!row?.querySelector('.generation-unit-enabled')?.checked;
      mode = String(row?.querySelector('.generation-ipadapter-mode')?.value || 'standard').toLowerCase();
      model = String(row?.querySelector('.generation-ipadapter-name')?.value || '').trim();
      clipVision = String(row?.querySelector('.generation-ipadapter-clip-vision')?.value || '').trim();
      weight = Number(row?.querySelector('.generation-ipadapter-weight')?.value || 1);
      faceWeight = Number(row?.querySelector('.generation-ipadapter-weight-faceidv2')?.value || weight || 1);
      facePreset = String(row?.querySelector('.generation-ipadapter-faceid-preset')?.value || '').trim();
      refCount = row?.querySelector('.generation-ipadapter-image')?.files?.length || 0;
    }
    return {
      slot, exists: slot === 1 ? !!document.getElementById('generation-ipadapter-enabled') : !!row,
      enabled, mode, is_faceid: mode === 'faceid', model, clip_vision: clipVision,
      has_model: !!model || mode === 'faceid', has_clip_vision: !!clipVision,
      has_reference: refCount > 0, ref_count: refCount,
      weight: Number.isFinite(weight) ? weight : 1,
      face_weight: Number.isFinite(faceWeight) ? faceWeight : 1,
      face_preset: facePreset,
    };
  }

  function getIpAdapterBindingDiagnostics(region) {
    if (!region || !region.ipadapter) return [];
    const slot = getIpAdapterSlotInfo(region.ipadapter_slot || 1);
    const rows = [];
    rows.push({ tone: slot.exists ? 'ok' : 'warn', text: slot.exists ? `Slot ${slot.slot} found` : `Slot ${slot.slot} missing` });
    rows.push({ tone: slot.enabled ? 'ok' : 'warn', text: slot.enabled ? 'Slot enabled' : 'Slot disabled' });
    rows.push({ tone: slot.is_faceid ? 'warn' : 'ok', text: slot.is_faceid ? 'FaceID mode' : 'Standard mode' });
    rows.push({ tone: slot.has_reference ? 'ok' : 'warn', text: slot.has_reference ? `${slot.ref_count} ref image${slot.ref_count === 1 ? '' : 's'}` : 'Reference missing' });
    rows.push({ tone: slot.has_clip_vision ? 'ok' : 'warn', text: slot.has_clip_vision ? 'CLIP Vision set' : 'CLIP Vision missing' });
    rows.push({ tone: region.ipadapter_use_region_mask === false ? 'warn' : 'ok', text: region.ipadapter_use_region_mask === false ? 'Mask off' : 'Masked to region' });
    if (slot.is_faceid && (slot.weight > 0.65 || slot.face_weight > 0.8)) rows.push({ tone: 'warn', text: 'High FaceID weight' });
    return rows;
  }

  function renderIpAdapterBadges(region) {
    return getIpAdapterBindingDiagnostics(region).map(item => {
      const bg = item.tone === 'ok' ? 'rgba(34,197,94,.14)' : item.tone === 'warn' ? 'rgba(245,158,11,.16)' : 'rgba(148,163,184,.16)';
      const border = item.tone === 'ok' ? 'rgba(34,197,94,.35)' : item.tone === 'warn' ? 'rgba(245,158,11,.38)' : 'rgba(148,163,184,.25)';
      return `<span class="badge" data-tone="${item.tone}" style="background:${bg}; border-color:${border};">${escapeHtml(item.text)}</span>`;
    }).join('');
  }

  function rectsOverlap(a, b) {
    const ar = normalizeRegionRect(a);
    const br = normalizeRegionRect(b);
    const eps = 0.0025;
    return !(ar.x + ar.w <= br.x + eps || br.x + br.w <= ar.x + eps || ar.y + ar.h <= br.y + eps || br.y + br.h <= ar.y + eps);
  }


  function getMainPrompt() {
    return String($("generation-positive")?.value || $("generation-prompt")?.value || $("prompt")?.value || "").trim();
  }

  function getMainNegativePrompt() {
    return String($("generation-negative")?.value || $("generation-negative-prompt")?.value || $("negative-prompt")?.value || $("negative_prompt")?.value || "").trim();
  }

  function normalizeRegionData(region, index = 0) {
    const safe = region && typeof region === 'object' ? region : {};
    return {
      id: safe.id || 'region_' + Date.now() + '_' + index,
      label: String(safe.label || 'Person ' + (index + 1)),
      type: String(safe.type || 'character'),
      enabled: safe.enabled === false ? false : true,
      locked: safe.locked === true,
      visible: safe.visible === false ? false : true,
      prompt: String(safe.prompt || ''),
      negative_prompt: String(safe.negative_prompt || ''),
      strength: clamp(Number(safe.strength ?? 1), 0, 2),
      reference: String(safe.reference || 'off'),
      reference_note: String(safe.reference_note || ''),
      ipadapter_model: String(safe.ipadapter_model || 'ip-adapter-plus_sdxl_vit-h.safetensors'),
      ipadapter_clip_vision: String(safe.ipadapter_clip_vision || 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
      ipadapter_weight: clamp(Number(safe.ipadapter_weight ?? 0.52), 0, 2),
      ipadapter_start_at: clamp(Number(safe.ipadapter_start_at ?? 0.05), 0, 1),
      ipadapter_end_at: clamp(Number(safe.ipadapter_end_at ?? 0.75), 0, 1),
      pose: String(safe.pose || 'off'),
      ipadapter: safe.ipadapter === true,
      ipadapter_slot: Math.max(1, Math.min(8, parseInt(safe.ipadapter_slot || safe.ipadapterSlot || (index + 1), 10) || (index + 1))),
      ipadapter_use_region_mask: safe.ipadapter_use_region_mask === false ? false : true,
      ipadapter_weight_mode: String(safe.ipadapter_weight_mode || 'slot_default'),
      identity_profile_id: String(safe.identity_profile_id || safe.profile_id || safe.character_profile_id || '').trim(),
      identity_profile_name: String(safe.identity_profile_name || safe.profile_name || safe.character_profile_name || '').trim(),
      identity_profile: safe.identity_profile && typeof safe.identity_profile === 'object' ? normalizeIdentityProfile(safe.identity_profile) : null,
      rect: normalizeRegionRect(safe.rect, index),
      loras: Array.isArray(safe.loras) ? safe.loras : [],
    };
  }

  function getPromptContracts() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STATE_KEY) || '{}') || {}; } catch (_) { saved = {}; }
    const savedContracts = saved.contracts && typeof saved.contracts === 'object' ? saved.contracts : {};
    const contracts = { ...DEFAULT_CONTRACTS, ...savedContracts };
    const enabledNode = $('neo-scene-contracts-enabled');
    const autoNode = $('neo-scene-node-auto-prompts');
    const countNode = $('neo-scene-count-contract');
    const subjectNode = $('neo-scene-subject-contract');
    const negativeNode = $('neo-scene-negative-contract');
    const styleNode = $('neo-scene-style-merge');
    return {
      enabled: enabledNode ? !!enabledNode.checked : contracts.enabled !== false,
      use_node_auto_prompts: autoNode ? !!autoNode.checked : contracts.use_node_auto_prompts === true,
      count_contract: String(countNode ? countNode.value : contracts.count_contract || '').trim(),
      subject_contract: String(subjectNode ? subjectNode.value : contracts.subject_contract || '').trim(),
      negative_contract: String(negativeNode ? negativeNode.value : contracts.negative_contract || '').trim(),
      style_merge: String(styleNode ? styleNode.value : contracts.style_merge || '').trim()
    };
  }

  function resetPromptContracts() {
    const map = {
      'neo-scene-contracts-enabled': DEFAULT_CONTRACTS.enabled,
      'neo-scene-node-auto-prompts': DEFAULT_CONTRACTS.use_node_auto_prompts,
      'neo-scene-count-contract': DEFAULT_CONTRACTS.count_contract,
      'neo-scene-subject-contract': DEFAULT_CONTRACTS.subject_contract,
      'neo-scene-negative-contract': DEFAULT_CONTRACTS.negative_contract,
      'neo-scene-style-merge': DEFAULT_CONTRACTS.style_merge
    };
    Object.entries(map).forEach(([id, value]) => {
      const node = $(id);
      if (!node) return;
      if (node.type === 'checkbox') node.checked = !!value;
      else node.value = String(value || '');
    });
    saveState({ contracts: getPromptContracts() });
    syncPromptPayload();
    setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
  }

  function readLiveCanvasRectFromBox(box) {
    if (!box) return null;
    // Phase 10.3.1: inline percent styles are the canonical canvas coordinates.
    // getBoundingClientRect can drift during panel reflow/zoom/border math and caused
    // region boxes to shrink slightly after every generation/payload sync.
    const parsePct = (value, fallback) => {
      const text = String(value || '').trim();
      if (text.endsWith('%')) {
        const n = Number(text.slice(0, -1));
        return Number.isFinite(n) ? n / 100 : fallback;
      }
      const n = Number(text);
      return Number.isFinite(n) ? n : fallback;
    };
    const style = box.style || {};
    const styledRect = {
      x: parsePct(style.left, NaN),
      y: parsePct(style.top, NaN),
      w: parsePct(style.width, NaN),
      h: parsePct(style.height, NaN),
    };
    if ([styledRect.x, styledRect.y, styledRect.w, styledRect.h].every(Number.isFinite)) {
      return normalizeRegionRect(styledRect);
    }
    const frame = $('neo-scene-director-canvas-frame');
    try {
      const fb = frame?.getBoundingClientRect?.();
      const bb = box.getBoundingClientRect?.();
      if (fb && bb && fb.width > 0 && fb.height > 0) {
        return normalizeRegionRect({ x: (bb.left - fb.left) / fb.width, y: (bb.top - fb.top) / fb.height, w: bb.width / fb.width, h: bb.height / fb.height });
      }
    } catch (_) {}
    return normalizeRegionRect({ x: 0, y: 0, w: 0.3, h: 0.7 });
  }


  function syncRegionsFromLiveCanvas() {
    const layer = $('neo-scene-director-region-layer');
    if (!layer) return regions;
    const boxes = Array.from(layer.querySelectorAll('.neo-scene-director-region-box[data-region-id]'));
    if (!boxes.length) return regions;
    const rectById = new Map();
    boxes.forEach((box) => { const id = box.dataset.regionId || ''; const rect = readLiveCanvasRectFromBox(box); if (id && rect) rectById.set(id, rect); });
    if (!rectById.size) return regions;
    regions = regions.map((region, index) => { const normalized = normalizeRegionData(region, index); const liveRect = rectById.get(normalized.id); return liveRect ? { ...normalized, rect: liveRect } : normalized; });
    return regions;
  }

  function forceLiveCanvasState(reason = 'live_canvas') {
    syncRegionsFromLiveCanvas();
    const enabled = !!$('neo-scene-director-enabled')?.checked;
    const contracts = document.getElementById('neo-scene-count-contract') ? getPromptContracts() : undefined;
    const state = { enabled, regions: regions.map((region, index) => normalizeRegionData(region, index)), ...(contracts ? { contracts } : {}), manual_layout_override: true, last_layout_preset: '', coordinate_source: reason };
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (_) {}
    const stateNode = $('neo-scene-director-state');
    if (stateNode) stateNode.value = JSON.stringify(state);
    window.NeoSceneDirectorExtension.state = state;
    return state;
  }

  function getPromptPayload() {
    const { width, height } = getSize();
    syncRegionsFromLiveCanvas();
    const normalizedRegions = regions.map((region, index) => normalizeRegionData(region, index));
    // Make the normalized live canvas coordinates canonical before generation reads state.
    regions = normalizedRegions;
    const activeRegions = normalizedRegions.filter(region => region.enabled && region.visible !== false);
    const identityUnits = buildSceneDirectorIdentityUnits(normalizedRegions);
    return {
      version: 1,
      extension_id: EXTENSION_ID,
      enabled: !!$('neo-scene-director-enabled')?.checked,
      family: getFamily(),
      mode: getWorkflowMode(),
      allowed: isAllowedFamily() && getSceneDirectorModePolicy().supported,
      mode_policy: getSceneDirectorModePolicy(),
      size: { width, height },
      global: { prompt: getMainPrompt(), negative_prompt: getMainNegativePrompt(), source: 'neo_image_tab' },
      contracts: getPromptContracts(),
      regions: normalizedRegions,
      active_region_count: activeRegions.length,
      identity_profiles: identityProfiles,
      identity_profile_units: identityUnits,
      scene_director_identity_units: identityUnits,
    };
  }

  function validatePromptPayload(payload = getPromptPayload()) {
    const warnings = [];
    if (payload.enabled && payload.mode_policy && !payload.mode_policy.supported) warnings.push(payload.mode_policy.message || 'Scene Director is not applied to this workflow mode yet.');
    else if (payload.enabled && !payload.allowed) warnings.push('Scene Director only supports SDXL / SD 1.5.');
    if (payload.enabled && payload.active_region_count < 1) warnings.push('Add at least one enabled visible region.');
    const ipSlots = new Map();
    const active = payload.regions.filter(region => region.enabled && region.visible !== false);
    active.forEach((region, index) => {
      const label = region.label || 'Region ' + (index + 1);
      if (!String(region.prompt || '').trim()) warnings.push(label + ' has no region prompt.');
      if (region.identity_profile_id) {
        const profile = getIdentityProfileById(region.identity_profile_id) || region.identity_profile;
        if (!profile) warnings.push(label + ' uses an Identity Profile that is not loaded/found.');
        else {
          const safeProfile = normalizeIdentityProfile(profile);
          if (!(safeProfile.reference_images || []).length) warnings.push(label + ' Identity Profile  + safeProfile.profile_name +  has no reference images.');
          if (safeProfile.ipadapter_mode === 'faceid' && safeProfile.weight > 0.65) warnings.push(label + ' Identity Profile FaceID weight is high. Use lower weights for safer multi-subject identity routing.');
        }
      }
      if (region.ipadapter && !Number.isFinite(Number(region.ipadapter_slot))) warnings.push(label + ' IPAdapter slot binding is invalid.');
      if (region.ipadapter && !region.identity_profile_id) {
        const slotKey = String(region.ipadapter_slot || '');
        const slot = getIpAdapterSlotInfo(region.ipadapter_slot || 1);
        if (ipSlots.has(slotKey)) warnings.push(label + ' shares IPAdapter slot ' + slotKey + ' with ' + ipSlots.get(slotKey) + '. Use one unique slot per region.');
        else ipSlots.set(slotKey, label);
        if (!slot.exists) warnings.push(label + ' points to IPAdapter slot ' + slotKey + ', but that slot does not exist in Neo IPAdapter.');
        if (slot.exists && !slot.enabled) warnings.push(label + ' points to IPAdapter slot ' + slotKey + ', but that slot is disabled.');
        if (slot.exists && !slot.has_reference) warnings.push(label + ' IPAdapter slot ' + slotKey + ' has no reference image.');
        if (slot.exists && !slot.has_clip_vision) warnings.push(label + ' IPAdapter slot ' + slotKey + ' has no CLIP Vision model.');
        if (region.ipadapter_use_region_mask === false) warnings.push(label + ' IPAdapter region mask is OFF; identity may bleed globally.');
        if (slot.is_faceid && (slot.weight > 0.65 || slot.face_weight > 0.8)) warnings.push(label + ' FaceID weight is high. For multi-subject scenes, keep weights lower until Safe Staged Refinement is added.');
      }
    });
    const faceIdRegions = active.filter(region => (region.ipadapter && getIpAdapterSlotInfo(region.ipadapter_slot || 1).is_faceid) || (region.identity_profile_id && normalizeIdentityProfile(getIdentityProfileById(region.identity_profile_id) || region.identity_profile || {}).ipadapter_mode === 'faceid'));
    if (faceIdRegions.length > 1) warnings.push('Multiple FaceID identities are active. Current chained mode can bleed identities; recommended path is Safe Staged Refinement.');
    for (let i = 0; i < active.length; i += 1) {
      for (let j = i + 1; j < active.length; j += 1) {
        if (rectsOverlap(active[i].rect, active[j].rect)) warnings.push((active[i].label || `Region ${i + 1}`) + ' overlaps ' + (active[j].label || `Region ${j + 1}`) + '. Overlap can cause prompt/IPAdapter bleed.');
      }
    }
    return warnings;
  }

  function summarizePromptReadiness() {
    const payload = getPromptPayload();
    const warnings = validatePromptPayload(payload);
    if (!payload.enabled) return 'Prompt system ready. Enable Scene Director when you want regions included in the future adapter payload.';
    if (payload.mode_policy && !payload.mode_policy.supported) return payload.mode_policy.message || 'Scene Director is not applied to this workflow mode yet.';
    if (warnings.length) return 'Prompt system needs attention: ' + warnings[0];
    return 'Prompt system ready: ' + payload.active_region_count + ' active region' + (payload.active_region_count === 1 ? '' : 's') + ' staged. SDXL / SD 1.5 V052 + IPAdapter slot binding adapter is active.';
  }

  function syncPromptPayload() {
    const payload = getPromptPayload();
    const stateNode = $('neo-scene-director-state');
    if (stateNode) stateNode.value = JSON.stringify(payload);
    const summary = $('neo-scene-director-prompt-summary');
    if (summary) {
      const warnings = validatePromptPayload(payload);
      summary.textContent = warnings.length ? warnings.join(' ') : 'Ready payload: ' + payload.active_region_count + ' active region' + (payload.active_region_count === 1 ? '' : 's') + ', global prompt linked from Neo.';
      summary.dataset.tone = warnings.length ? 'warn' : 'ok';
    }
    window.NeoSceneDirectorExtension.promptPayload = payload;
    return payload;
  }

  function updateCanvasShell() {
    const frame = $('neo-scene-director-canvas-frame');
    const meta = $('neo-scene-director-canvas-meta');
    if (!frame) return;
    const { width, height } = getSize();
    frame.style.aspectRatio = `${width} / ${height}`;
    frame.dataset.orientation = canvasLabel(width, height).toLowerCase();
    if (meta) meta.textContent = `${width} × ${height} · ${canvasLabel(width, height)} preview shell`;
    renderGhostBoxes(width, height);
    saveState({ size: { width, height } });
  }

  function normalizeRect(index) {
    const presets = [
      { x: 0.08, y: 0.14, w: 0.28, h: 0.70 },
      { x: 0.36, y: 0.12, w: 0.28, h: 0.72 },
      { x: 0.64, y: 0.14, w: 0.28, h: 0.70 },
    ];
    return presets[index % presets.length];
  }

  function makeLayoutRegion(template, index, existingRegion, replacePrompts=false) {
    const existing = existingRegion && typeof existingRegion === 'object' ? existingRegion : {};
    const base = {
      ...existing,
      id: existing.id || `region_${Date.now()}_${index}`,
      label: template.label || existing.label || `Person ${index + 1}`,
      type: template.type || existing.type || 'character',
      enabled: true,
      locked: false,
      visible: true,
      rect: template.rect || normalizeRect(index),
      ipadapter_slot: existing.ipadapter_slot || (index + 1),
      ipadapter_use_region_mask: existing.ipadapter_use_region_mask === false ? false : true,
      identity_profile_id: existing.identity_profile_id || '',
      identity_profile_name: existing.identity_profile_name || '',
      identity_profile: existing.identity_profile || null,
    };
    if (replacePrompts) {
      base.prompt = template.prompt || '';
      base.negative_prompt = template.negative_prompt || '';
    } else {
      base.prompt = existing.prompt || '';
      base.negative_prompt = existing.negative_prompt || '';
    }
    return normalizeRegionData(base, index);
  }

  function applyRegionLayoutPreset(key) {
    const preset = REGION_LAYOUT_PRESETS[key];
    if (!preset || !Array.isArray(preset.regions)) {
      setStatus('Choose a valid region layout preset.', 'warn');
      return;
    }
    const replacePrompts = !!$('neo-scene-layout-replace-prompts')?.checked;
    const keepBindings = $('neo-scene-layout-keep-bindings')?.checked !== false;
    const current = regions.map((region, index) => normalizeRegionData(region, index));
    regions = preset.regions.map((template, index) => {
      const existing = keepBindings ? current[index] : {};
      return makeLayoutRegion(template, index, existing, replacePrompts);
    });
    selectedRegionId = regions[0]?.id || null;
    renderRegions();
    updateCanvasShell();
    saveState({ last_layout_preset: key });
    setStatus(`Applied layout preset: ${preset.label}. ${regions.length} region${regions.length === 1 ? '' : 's'} ready.`, 'ok');
  }

  function renderLayoutPresetButtons() {
    return Object.entries(REGION_LAYOUT_PRESETS).map(([key, preset]) => {
      return `<button class="btn btn-small neo-scene-layout-preset-btn" type="button" data-scene-layout-preset="${escapeHtml(key)}" title="${escapeHtml(preset.description || '')}">${escapeHtml(preset.label)}</button>`;
    }).join('');
  }

  function addRegion() {
    const index = regions.length;
    regions.push(normalizeRegionData({
      id: `region_${Date.now()}`,
      label: `Person ${index + 1}`,
      type: 'character',
      enabled: true,
      locked: false,
      visible: true,
      prompt: '',
      negative_prompt: '',
      strength: 1,
      reference: 'off',
      reference_note: '',
      ipadapter_model: 'ip-adapter-plus_sdxl_vit-h.safetensors',
      ipadapter_clip_vision: 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors',
      ipadapter_weight: 0.52,
      ipadapter_start_at: 0.05,
      ipadapter_end_at: 0.75,
      pose: 'off',
      ipadapter: false,
      ipadapter_slot: index + 1,
      ipadapter_use_region_mask: true,
      ipadapter_weight_mode: 'slot_default',
      identity_profile_id: '',
      identity_profile_name: '',
      identity_profile: null,
      lora: false,
      lora_slot: index + 1,
      lora_weight_mode: 'slot_default',
      lora_strength: 0.8,
      rect: normalizeRect(index),
      loras: [],
    }, index));
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function removeRegion(id) {
    regions = regions.filter(region => region.id !== id);
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function updateRegion(id, patch) {
    regions = regions.map(region => region.id === id ? { ...region, ...patch } : region);
    renderGhostBoxes();
    saveState();
  }

  function clamp(value, min = 0, max = 1) {
    return Math.max(min, Math.min(max, Number.isFinite(value) ? value : min));
  }

  function normalizeRegionRect(rect, fallbackIndex = 0) {
    const fallback = normalizeRect(fallbackIndex);
    let x = clamp(Number(rect?.x ?? fallback.x));
    let y = clamp(Number(rect?.y ?? fallback.y));
    let w = clamp(Number(rect?.w ?? fallback.w), MIN_RECT_SIZE, 1);
    let h = clamp(Number(rect?.h ?? fallback.h), MIN_RECT_SIZE, 1);
    if (x + w > 1) x = Math.max(0, 1 - w);
    if (y + h > 1) y = Math.max(0, 1 - h);
    return { x, y, w, h };
  }

  function getRegion(id) {
    return regions.find(region => region.id === id) || null;
  }

  function setSelectedRegion(id) {
    selectedRegionId = id || null;
    document.querySelectorAll('.neo-scene-director-region-box').forEach(box => {
      box.dataset.selected = box.dataset.regionId === selectedRegionId ? 'true' : 'false';
    });
    document.querySelectorAll('.neo-scene-director-region-card').forEach(card => {
      card.dataset.selected = card.dataset.regionId === selectedRegionId ? 'true' : 'false';
    });
  }

  function applyRectToRegion(id, rect, options = {}) {
    const region = getRegion(id);
    if (!region) return;
    const nextRect = normalizeRegionRect(rect);
    // Replace the region object instead of mutating it in-place so every payload reader gets fresh coordinates.
    regions = regions.map((item, index) => item.id === id ? normalizeRegionData({ ...item, rect: nextRect }, index) : normalizeRegionData(item, index));
    const box = document.querySelector(`.neo-scene-director-region-box[data-region-id="${CSS.escape(id)}"]`);
    if (box) applyRectToBox(box, nextRect);
    const stateExtra = options.manual ? { manual_layout_override: true, last_layout_preset: '' } : {};
    saveState(stateExtra);
    syncPromptPayload();
  }

  function applyRectToBox(box, rect) {
    const safe = normalizeRegionRect(rect);
    box.style.left = `${safe.x * 100}%`;
    box.style.top = `${safe.y * 100}%`;
    box.style.width = `${safe.w * 100}%`;
    box.style.height = `${safe.h * 100}%`;
  }

  function makeResizeHandles(region) {
    return ['nw', 'ne', 'sw', 'se'].map(handle =>
      `<button type="button" class="neo-scene-director-resize-handle neo-scene-director-resize-${handle}" data-region-resize="${region.id}" data-handle="${handle}" aria-label="Resize ${escapeHtml(region.label || 'region')} ${handle}"></button>`
    ).join('');
  }

  function renderGhostBoxes() {
    const layer = $('neo-scene-director-region-layer');
    if (!layer) return;
    layer.innerHTML = '';
    // Canvas overlay should never be affected by saved/preset regions while Scene Director is off.
    if (!isSceneDirectorEnabled()) {
      if (selectedRegionId) selectedRegionId = null;
      setSelectedRegion(null);
      return;
    }
    regions.filter(region => region.visible !== false).forEach((region, index) => {
      region.rect = normalizeRegionRect(region.rect, index);
      const box = makeEl('div', 'neo-scene-director-region-box', `
        <span>${escapeHtml(region.label || `Region ${index + 1}`)}</span>
        ${makeResizeHandles(region)}
      `);
      box.tabIndex = 0;
      box.dataset.regionId = region.id;
      box.dataset.enabled = region.enabled === false ? 'false' : 'true';
      box.dataset.locked = region.locked === true ? 'true' : 'false';
      box.dataset.selected = region.id === selectedRegionId ? 'true' : 'false';
      box.title = region.locked ? 'Region locked' : 'Drag to move. Resize from the corners.';
      applyRectToBox(box, region.rect);
      layer.appendChild(box);
    });
    if (selectedRegionId && !getRegion(selectedRegionId)) selectedRegionId = null;
    setSelectedRegion(selectedRegionId);
  }

  function beginInteraction(event, id, mode, handle = null) {
    const frame = $('neo-scene-director-canvas-frame');
    const region = getRegion(id);
    if (!frame || !region || region.locked) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedRegion(id);
    const bounds = frame.getBoundingClientRect();
    const startRect = normalizeRegionRect(region.rect);
    activeInteraction = {
      id,
      mode,
      handle,
      bounds,
      startX: event.clientX,
      startY: event.clientY,
      startRect,
      pointerId: event.pointerId,
    };
    try { event.currentTarget.setPointerCapture?.(event.pointerId); } catch (_) {}
    document.body.classList.add('neo-scene-director-dragging');
  }

  function rectFromInteraction(event) {
    if (!activeInteraction) return null;
    const { bounds, startX, startY, startRect, mode, handle } = activeInteraction;
    const dx = (event.clientX - startX) / Math.max(1, bounds.width);
    const dy = (event.clientY - startY) / Math.max(1, bounds.height);
    let { x, y, w, h } = startRect;

    if (mode === 'move') {
      x = clamp(startRect.x + dx, 0, 1 - startRect.w);
      y = clamp(startRect.y + dy, 0, 1 - startRect.h);
      return { x, y, w, h };
    }

    if (mode === 'resize') {
      const fromLeft = handle.includes('w');
      const fromTop = handle.includes('n');
      const fromRight = handle.includes('e');
      const fromBottom = handle.includes('s');

      let left = startRect.x;
      let top = startRect.y;
      let right = startRect.x + startRect.w;
      let bottom = startRect.y + startRect.h;

      if (fromLeft) left = clamp(startRect.x + dx, 0, right - MIN_RECT_SIZE);
      if (fromRight) right = clamp(startRect.x + startRect.w + dx, left + MIN_RECT_SIZE, 1);
      if (fromTop) top = clamp(startRect.y + dy, 0, bottom - MIN_RECT_SIZE);
      if (fromBottom) bottom = clamp(startRect.y + startRect.h + dy, top + MIN_RECT_SIZE, 1);

      x = left; y = top; w = right - left; h = bottom - top;

      if (event.shiftKey) {
        const ratio = startRect.w / Math.max(MIN_RECT_SIZE, startRect.h);
        if (w / Math.max(MIN_RECT_SIZE, h) > ratio) w = h * ratio;
        else h = w / ratio;
        if (fromLeft) x = right - w;
        if (fromTop) y = bottom - h;
      }

      if (event.altKey) {
        const cx = startRect.x + startRect.w / 2;
        const cy = startRect.y + startRect.h / 2;
        x = clamp(cx - w / 2, 0, 1 - w);
        y = clamp(cy - h / 2, 0, 1 - h);
      }
      return normalizeRegionRect({ x, y, w, h });
    }
    return null;
  }

  function endInteraction() {
    if (!activeInteraction) return;
    activeInteraction = null;
    document.body.classList.remove('neo-scene-director-dragging');
  }

  function option(value, current, label) {
    return '<option value="' + escapeHtml(value) + '" ' + (String(current || '') === String(value) ? 'selected' : '') + '>' + escapeHtml(label) + '</option>';
  }

  function renderRegions() {
    const host = $('neo-scene-director-regions-host');
    if (!host) return;
    regions = regions.map((region, index) => normalizeRegionData(region, index));
    if (!regions.length) {
      host.innerHTML = '<div class="mini-note">No regions yet. Add one, then drag the box, resize from the corners, and add a region prompt.</div>';
      syncPromptPayload();
      return;
    }
    host.innerHTML = '';
    regions.forEach((region, index) => {
      const regionIsCharacter = String(region.type || 'character') === 'character';
      const card = makeEl('div', 'neo-scene-director-region-card');
      card.dataset.regionId = region.id;
      card.dataset.selected = region.id === selectedRegionId ? 'true' : 'false';
      card.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:center;">
          <div class="row" style="gap:8px; align-items:center; flex-wrap:wrap;">
            <input type="checkbox" data-region-enabled="${region.id}" ${region.enabled === false ? '' : 'checked'} title="Enable this region for the future adapter payload" />
            <input class="neo-scene-director-label-input" data-region-label="${region.id}" value="${escapeHtml(region.label || `Person ${index + 1}`)}" />
            <select data-region-type="${region.id}" title="Region type">
              ${option('character', region.type, 'Character')}
              ${option('object', region.type, 'Object')}
              ${option('background', region.type, 'Background')}
              ${option('style', region.type, 'Style area')}
            </select>
          </div>
          <div class="row" style="gap:8px; flex-wrap:wrap;">
            <button class="btn btn-small" type="button" data-region-lock="${region.id}">${region.locked ? 'Unlock' : 'Lock'}</button>
            <button class="btn btn-small" type="button" data-region-visible="${region.id}">${region.visible === false ? 'Show' : 'Hide'}</button>
            <button class="btn btn-small" type="button" data-region-copy="${region.id}">Duplicate</button>
            <button class="btn btn-small" type="button" data-region-remove="${region.id}">Delete</button>
          </div>
        </div>
        <div class="neo-scene-identity-panel" data-character-profile-panel="${region.id}" style="display:${regionIsCharacter ? 'block' : 'none'}; margin-top:10px; padding:10px; border:1px solid rgba(168,85,247,.24); border-radius:12px; background:rgba(88,28,135,.14);">
          <div class="row-between" style="gap:10px; align-items:center; flex-wrap:wrap;">
            <div>
              <label>Character Profile</label>
              <select data-region-profile="${region.id}">${buildIdentityProfileOptions(region.identity_profile_id)}</select>
            </div>
            <div class="mini-note">Assigning a profile overrides manual IPAdapter for this region and prepares identity routing for this region.</div>
          </div>
        </div>
        <div class="grid grid-2" style="margin-top:10px; gap:10px;">
          <div>
            <label for="neo-scene-prompt-${region.id}">Region prompt</label>
            <textarea id="neo-scene-prompt-${region.id}" data-region-prompt="${region.id}" rows="4" placeholder="Prompt only for this region. Neo main prompt stays global.">${escapeHtml(region.prompt || '')}</textarea>
          </div>
          <div>
            <label for="neo-scene-negative-${region.id}">Region negative prompt</label>
            <textarea id="neo-scene-negative-${region.id}" data-region-negative="${region.id}" rows="4" placeholder="Optional negative prompt only for this region.">${escapeHtml(region.negative_prompt || '')}</textarea>
          </div>
        </div>
        <div class="grid grid-2" style="margin-top:10px; gap:10px; align-items:end;">
          <div>
            <label>Prompt strength</label>
            <input type="number" step="0.05" min="0" max="2" data-region-strength="${region.id}" value="${Number(region.strength || 1)}" />
          </div>
          <div class="mini-note">ControlNet stays global. Use the normal Neo ControlNet panel for Canny, OpenPose, Depth, etc.</div>
        </div>
        <div class="neo-scene-ipadapter-panel" style="margin-top:10px; padding:10px; border:1px solid rgba(148,163,184,.16); border-radius:12px; background:rgba(15,23,42,.24); opacity:${region.identity_profile_id ? '.58' : '1'};" data-enabled="${region.ipadapter ? 'true' : 'false'}">
          <div class="row-between" style="gap:10px; align-items:center;">
            <div>
              <label class="neo-toggle-line"><input type="checkbox" data-region-ipadapter="${region.id}" ${region.ipadapter ? 'checked' : ''} ${region.identity_profile_id ? 'disabled' : ''}/> Use IPAdapter for this region</label>
              <div class="muted small">${region.identity_profile_id ? 'Manual IPAdapter is locked because a Character Profile is assigned.' : 'Reference image/model stays in the main Neo IPAdapter slot. Scene Director only binds that slot to this region mask.'}</div>
              <div class="row" style="gap:6px; flex-wrap:wrap; margin-top:6px;">${region.ipadapter ? renderIpAdapterBadges(region) : '<span class="badge">Binding off</span>'}</div>
            </div>
            <span class="badge">Region mask</span>
          </div>
          <div class="grid grid-4" style="margin-top:10px; gap:10px; align-items:end; opacity:${region.ipadapter ? '1' : '.45'};">
            <div>
              <label>Neo IPAdapter slot</label>
              <select data-region-ip-slot="${region.id}" ${region.ipadapter ? '' : 'disabled'}>
                ${[1,2,3,4,5,6,7,8].map(slot => option(String(slot), String(region.ipadapter_slot || (index + 1)), 'IPAdapter ' + slot)).join('')}
              </select>
            </div>
            <div>
              <label>Weight source</label>
              <select data-region-ip-weight-mode="${region.id}" ${region.ipadapter ? '' : 'disabled'}>
                ${option('slot_default', region.ipadapter_weight_mode, 'Use slot default')}
                ${option('custom', region.ipadapter_weight_mode, 'Custom override')}
              </select>
            </div>
            <div>
              <label>Custom weight</label>
              <input type="number" step="0.01" min="0" max="2" data-region-ip-weight="${region.id}" value="${Number(region.ipadapter_weight ?? 0.52)}" ${region.ipadapter ? '' : 'disabled'} />
            </div>
            <div>
              <label class="neo-toggle-line"><input type="checkbox" data-region-ip-mask="${region.id}" ${region.ipadapter_use_region_mask === false ? '' : 'checked'} ${region.ipadapter ? '' : 'disabled'} /> Use region mask</label>
            </div>
          </div>
          <div class="mini-note" style="margin-top:8px;">When Scene Director is ON, normal global IPAdapter is suppressed. Only region-bound IPAdapter slots are applied to prevent face bleed.</div>
        </div>
        `;
      host.appendChild(card);
    });
    syncPromptPayload();
  }

  function duplicateRegion(id) {
    const source = regions.find(region => region.id === id);
    if (!source) return;
    regions.push({ ...source, id: `region_${Date.now()}`, label: `${source.label || 'Region'} Copy`, rect: normalizeRegionRect({ ...(source.rect || normalizeRect(0)), x: (source.rect?.x || 0) + 0.04, y: (source.rect?.y || 0) + 0.04 }) });
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function bindRegionEvents(root) {
    root.addEventListener('input', event => {
      const target = event.target;
      if (!target) return;
      const labelId = target.getAttribute('data-region-label');
      const promptId = target.getAttribute('data-region-prompt');
      const negativeId = target.getAttribute('data-region-negative');
      const strengthId = target.getAttribute('data-region-strength');
      const refNoteId = target.getAttribute('data-region-ref-note');
      const ipModelId = target.getAttribute('data-region-ip-model');
      const ipClipId = target.getAttribute('data-region-ip-clip');
      const ipWeightId = target.getAttribute('data-region-ip-weight');
      const ipStartId = target.getAttribute('data-region-ip-start');
      const ipEndId = target.getAttribute('data-region-ip-end');
      const ipSlotId = target.getAttribute('data-region-ip-slot');
      const ipWeightModeId = target.getAttribute('data-region-ip-weight-mode');
      const profileId = target.getAttribute('data-region-profile');
      const loraStrengthId = target.getAttribute('data-region-lora-strength');
      const loraSlotId = target.getAttribute('data-region-lora-slot');
      const loraWeightModeId = target.getAttribute('data-region-lora-weight-mode');
      if (labelId) updateRegion(labelId, { label: target.value });
      if (promptId) updateRegion(promptId, { prompt: target.value });
      if (negativeId) updateRegion(negativeId, { negative_prompt: target.value });
      if (strengthId) updateRegion(strengthId, { strength: clamp(Number(target.value || 1), 0, 2) });
      if (refNoteId) updateRegion(refNoteId, { reference_note: target.value });
      if (ipModelId) updateRegion(ipModelId, { ipadapter_model: target.value });
      if (ipClipId) updateRegion(ipClipId, { ipadapter_clip_vision: target.value });
      if (ipWeightId) updateRegion(ipWeightId, { ipadapter_weight: clamp(Number(target.value || 0.52), 0, 2) });
      if (ipStartId) updateRegion(ipStartId, { ipadapter_start_at: clamp(Number(target.value || 0.05), 0, 1) });
      if (ipEndId) updateRegion(ipEndId, { ipadapter_end_at: clamp(Number(target.value || 0.75), 0, 1) });
      if (ipSlotId) updateRegion(ipSlotId, { ipadapter_slot: Math.max(1, Math.min(8, parseInt(target.value || '1', 10) || 1)) });
      if (ipWeightModeId) updateRegion(ipWeightModeId, { ipadapter_weight_mode: target.value || 'slot_default' });
      if (loraStrengthId) updateRegion(loraStrengthId, { lora_strength: clamp(Number(target.value || 0.8), -4, 4) });
      if (loraSlotId) updateRegion(loraSlotId, { lora_slot: Math.max(1, Math.min(8, parseInt(target.value || '1', 10) || 1)) });
      if (loraWeightModeId) updateRegion(loraWeightModeId, { lora_weight_mode: target.value || 'slot_default' });
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
    root.addEventListener('change', event => {
      const target = event.target;
      const enabledId = target?.getAttribute('data-region-enabled');
      const typeId = target?.getAttribute('data-region-type');
      const refId = target?.getAttribute('data-region-ref');
      const poseId = target?.getAttribute('data-region-pose');
      const ipadapterId = target?.getAttribute('data-region-ipadapter');
      const ipMaskId = target?.getAttribute('data-region-ip-mask');
      const loraId = target?.getAttribute('data-region-lora');
      const profileId = target?.getAttribute('data-region-profile');
      if (profileId) {
        const selectedProfileKey = String(target.value || '').trim();
        if (selectedProfileKey) {
          loadIdentityProfile(selectedProfileKey).then((profile) => {
            const safe = profile ? normalizeIdentityProfile(profile) : null;
            updateRegion(profileId, {
              identity_profile_id: selectedProfileKey,
              identity_profile_name: safe?.profile_name || selectedProfileKey,
              identity_profile: safe || null,
              ipadapter: false,
            });
            renderRegions();
            syncPromptPayload();
            setStatus(safe ? `Assigned Identity Profile ${safe.profile_name} to region.` : 'Assigned Identity Profile to region.', 'ok');
          });
        } else {
          updateRegion(profileId, { identity_profile_id: '', identity_profile_name: '', identity_profile: null });
          renderRegions();
          syncPromptPayload();
          setStatus('Identity Profile removed from region.', 'muted');
        }
      }
      if (enabledId) updateRegion(enabledId, { enabled: !!target.checked });
      if (typeId) {
        const nextType = target.value || 'character';
        const patch = { type: nextType };
        if (nextType !== 'character') {
          patch.identity_profile_id = '';
          patch.identity_profile_name = '';
          patch.identity_profile = null;
        }
        updateRegion(typeId, patch);
        renderRegions();
        updateCanvasShell();
      }
      if (refId) updateRegion(refId, { reference: target.value || 'off' });
      if (poseId) updateRegion(poseId, { pose: target.value || 'off' });
      if (ipadapterId) { updateRegion(ipadapterId, { ipadapter: !!target.checked }); renderRegions(); }
      if (ipMaskId) updateRegion(ipMaskId, { ipadapter_use_region_mask: !!target.checked });
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
    root.addEventListener('click', event => {
      const target = event.target;
      const removeId = target?.getAttribute('data-region-remove');
      const copyId = target?.getAttribute('data-region-copy');
      const lockId = target?.getAttribute('data-region-lock');
      const visibleId = target?.getAttribute('data-region-visible');
      const card = target?.closest?.('.neo-scene-director-region-card');
      if (card?.dataset?.regionId && !removeId && !copyId && !lockId && !visibleId) setSelectedRegion(card.dataset.regionId);
      if (removeId) removeRegion(removeId);
      if (copyId) duplicateRegion(copyId);
      if (lockId) { const region = getRegion(lockId); if (region) updateRegion(lockId, { locked: !region.locked }); renderRegions(); updateCanvasShell(); }
      if (visibleId) { const region = getRegion(visibleId); if (region) updateRegion(visibleId, { visible: region.visible === false }); renderRegions(); updateCanvasShell(); }
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
  }

  function updateEligibility() {
    const family = getFamily();
    const allowed = isAllowedFamily(family);
    const shell = $('neo-scene-director-shell');
    const familyBadge = $('neo-scene-director-family-badge');
    const enabledInput = $('neo-scene-director-enabled');
    if (shell) shell.dataset.familyAllowed = allowed ? 'true' : 'false';
    if (familyBadge) familyBadge.textContent = allowed ? 'SD / SDXL ready' : `${family || 'family'} blocked`;
    if (enabledInput && !allowed) enabledInput.checked = false;
    const modePolicy = getSceneDirectorModePolicy();
    const ready = allowed && modePolicy.supported;
    setStatus(ready ? summarizePromptReadiness() : (modePolicy.message || 'Scene Director is blocked for this family. Flux, Qwen, and Z-Image stay untouched.'), ready ? 'muted' : 'warn');
    saveState({ family, mode: getWorkflowMode(), scene_director_mode_policy: modePolicy.reason || 'supported' });
  }


  function collectLoraMappings() {
    return Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row')).map((row, index) => ({
      index: index + 1,
      uid: row.dataset.uid || '',
      enabled: !!row.querySelector('.generation-unit-enabled')?.checked,
      name: row.querySelector('.generation-lora-name')?.value || '',
      strength: Number(row.querySelector('.generation-lora-strength')?.value || 0.8),
      apply_to: row.querySelector('.generation-lora-apply-to')?.value || 'global',
      target: row.querySelector('.generation-lora-target')?.value || 'both',
    }));
  }

  function applyLoraMappings(mappings) {
    if (!Array.isArray(mappings)) return;
    const rows = Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row'));
    mappings.forEach((item, index) => {
      const row = rows[index];
      if (!row) return;
      const enabled = row.querySelector('.generation-unit-enabled');
      const name = row.querySelector('.generation-lora-name');
      const strength = row.querySelector('.generation-lora-strength');
      const applyTo = row.querySelector('.generation-lora-apply-to');
      const target = row.querySelector('.generation-lora-target');
      if (enabled) enabled.checked = item.enabled !== false;
      if (name && item.name != null) name.value = item.name || '';
      if (strength && item.strength != null) strength.value = Number(item.strength || 0.8);
      if (applyTo && item.apply_to) {
        applyTo.dataset.value = item.apply_to;
        applyTo.value = item.apply_to;
      }
      if (target && item.target) target.value = item.target;
      row.querySelectorAll('input, select, textarea').forEach(el => el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })));
    });
    if (window.NeoStudioApp?.generation?.workflow?.refreshLoraApplyTargets) window.NeoStudioApp.generation.workflow.refreshLoraApplyTargets();
  }

  function dispatchNeoInput(node) {
    if (!node) return;
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function getScenePresetName() {
    return String($('neo-scene-preset-name')?.value || '').trim();
  }

  function captureScenePresetPayload(name='') {
    return {
      version: 1,
      name: name || getScenePresetName() || 'Untitled Scene Preset',
      saved_at: new Date().toISOString(),
      global_prompt: $('generation-positive')?.value || '',
      negative_prompt: $('generation-negative')?.value || '',
      width: Number($('generation-width')?.value || 1024),
      height: Number($('generation-height')?.value || 1024),
      enabled: !!$('neo-scene-director-enabled')?.checked,
      contracts: getPromptContracts(),
      regions: regions.map((region, index) => normalizeRegionData(region, index)),
      identity_profiles: identityProfiles,
      identity_profile_bindings: regions.map((region, index) => normalizeRegionData(region, index)).filter(region => region.identity_profile_id).map(region => ({ region_id: region.id, label: region.label, profile_id: region.identity_profile_id, profile_name: region.identity_profile_name })),
      ipadapter_bindings: regions.map((region, index) => normalizeRegionData(region, index)).filter(region => region.ipadapter).map(region => ({
        region_id: region.id,
        label: region.label,
        slot: region.ipadapter_slot,
        use_region_mask: region.ipadapter_use_region_mask,
        weight_mode: region.ipadapter_weight_mode,
        custom_weight: region.ipadapter_weight,
      })),
      lora_apply_to: collectLoraMappings(),
      scene_director_settings: {
        selected_region_id: selectedRegionId,
        family: getFamily(),
      },
    };
  }

  function applyScenePresetPayload(preset) {
    if (!preset || typeof preset !== 'object') return;
    if ($('generation-positive') && preset.global_prompt != null) { $('generation-positive').value = preset.global_prompt || ''; dispatchNeoInput($('generation-positive')); }
    if ($('generation-negative') && preset.negative_prompt != null) { $('generation-negative').value = preset.negative_prompt || ''; dispatchNeoInput($('generation-negative')); }
    if ($('generation-width') && preset.width) { $('generation-width').value = Number(preset.width || 1024); dispatchNeoInput($('generation-width')); }
    if ($('generation-height') && preset.height) { $('generation-height').value = Number(preset.height || 1024); dispatchNeoInput($('generation-height')); }
    if ($('neo-scene-director-enabled') && preset.enabled != null) $('neo-scene-director-enabled').checked = !!preset.enabled;
    const contracts = { ...DEFAULT_CONTRACTS, ...(preset.contracts || {}) };
    const map = {
      'neo-scene-contracts-enabled': contracts.enabled,
      'neo-scene-node-auto-prompts': contracts.use_node_auto_prompts,
      'neo-scene-count-contract': contracts.count_contract,
      'neo-scene-subject-contract': contracts.subject_contract,
      'neo-scene-negative-contract': contracts.negative_contract,
      'neo-scene-style-merge': contracts.style_merge,
    };
    Object.entries(map).forEach(([id, value]) => {
      const node = $(id);
      if (!node) return;
      if (node.type === 'checkbox') node.checked = !!value;
      else node.value = String(value || '');
      dispatchNeoInput(node);
    });
    regions = Array.isArray(preset.regions) ? preset.regions.map((region, index) => normalizeRegionData(region, index)) : [];
    selectedRegionId = preset.scene_director_settings?.selected_region_id || (regions[0]?.id || null);
    renderRegions();
    updateCanvasShell();
    saveState({ contracts, last_loaded_preset: preset.name || '' });
    applyLoraMappings(preset.lora_apply_to || []);
    setStatus(`Loaded scene preset: ${preset.name || 'Untitled'}`, 'ok');
  }

  async function refreshScenePresetList(selectValue='') {
    const select = $('neo-scene-preset-select');
    if (!select) return [];
    try {
      const res = await fetch('/api/scene-director/presets', { cache: 'no-store' });
      const data = await res.json();
      const presets = data && data.ok && Array.isArray(data.presets) ? data.presets : [];
      select.innerHTML = '<option value="">Select saved preset...</option>' + presets.map(item => `<option value="${escapeHtml(item.slug)}">${escapeHtml(item.name)} (${item.region_count || 0} regions)</option>`).join('');
      if (selectValue) select.value = selectValue;
      return presets;
    } catch (_) {
      setStatus('Could not refresh Scene Preset list.', 'warn');
      return [];
    }
  }

  async function saveScenePreset() {
    const name = getScenePresetName();
    if (!name) { setStatus('Preset name is required before saving.', 'warn'); return; }
    const preset = captureScenePresetPayload(name);
    try {
      const res = await fetch('/api/scene-director/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, preset }),
      });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Save failed');
      await refreshScenePresetList(data.preset?.slug || '');
      setStatus(`Saved scene preset: ${name}`, 'ok');
    } catch (err) {
      setStatus(`Could not save scene preset. ${err?.message || ''}`.trim(), 'warn');
    }
  }

  async function loadScenePreset() {
    const key = $('neo-scene-preset-select')?.value || getScenePresetName();
    if (!key) { setStatus('Choose a preset to load.', 'warn'); return; }
    try {
      const res = await fetch('/api/scene-director/presets/' + encodeURIComponent(key), { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Load failed');
      if ($('neo-scene-preset-name')) $('neo-scene-preset-name').value = data.name || data.preset?.name || key;
      applyScenePresetPayload(data.preset || {});
    } catch (err) {
      setStatus(`Could not load scene preset. ${err?.message || ''}`.trim(), 'warn');
    }
  }

  async function deleteScenePreset() {
    const key = $('neo-scene-preset-select')?.value || getScenePresetName();
    if (!key) { setStatus('Choose a preset to delete.', 'warn'); return; }
    try {
      const res = await fetch('/api/scene-director/presets/' + encodeURIComponent(key), { method: 'DELETE' });
      const data = await res.json();
      if (!data || !data.ok) throw new Error(data?.error || data?.message || data?.detail || 'Delete failed');
      if ($('neo-scene-preset-name')) $('neo-scene-preset-name').value = '';
      await refreshScenePresetList();
      setStatus('Deleted scene preset.', 'ok');
    } catch (err) {
      setStatus(`Could not delete scene preset. ${err?.message || ''}`.trim(), 'warn');
    }
  }

  function mountShell(parent) {
    if (!parent || $('neo-scene-director-shell')) return;
    const saved = loadState();
    const shell = makeEl('details', 'accordion-block generation-inline-accordion neo-scene-director-shell');
    shell.id = 'neo-scene-director-shell';
    shell.open = false;
    shell.innerHTML = `
      <summary class="accordion-summary">
        <div>
          <div class="accordion-title">Scene Director</div>
          <div class="accordion-hint">Regional prompting UI shell for SD / SDXL. Uses Neo main prompt and image settings as the global base.</div>
        </div>
        <span class="badge" id="neo-scene-director-family-badge">SD / SDXL ready</span>
        <span class="accordion-chevron" aria-hidden="true">▾</span>
      </summary>
      <div class="accordion-body">
        <div class="neo-scene-director-topbar">
          <label class="neo-toggle-line"><input id="neo-scene-director-enabled" type="checkbox" ${saved.enabled ? 'checked' : ''}/> Enable Scene Director</label>
          <span class="badge">Identity Profiles</span>
        </div>
        <div class="mini-note" id="neo-scene-director-status">Loading Scene Director shell...</div>
        <input id="neo-scene-director-state" type="hidden" value="" />
        <details class="neo-scene-identity-profile-panel" style="margin:12px 0; padding:12px; border:1px solid rgba(168,85,247,.22); border-radius:14px; background:rgba(88,28,135,.16);">
          <summary class="row-between" style="gap:10px; align-items:center; flex-wrap:wrap; cursor:pointer; list-style:none;">
            <div>
              <div class="stat-title">Identity Profiles</div>
              <div class="muted small">Reusable character profiles: refs, FaceID/IPAdapter mode, weights, optional LoRA, and notes.</div>
            </div>
            <span class="badge">Profiles ▾</span>
          </summary>
          <div class="grid grid-4" style="gap:10px; margin-top:10px; align-items:end;">
            <div><label>Saved profile</label><select id="neo-identity-profile-select"><option value="">Select profile...</option></select></div>
            <div><label>Profile name</label><input id="neo-identity-profile-name" type="text" placeholder="Maya" /></div>
            <div><label>Mode</label><select id="neo-identity-profile-mode"><option value="faceid">FaceID</option><option value="standard">IPAdapter standard</option></select></div>
            <div class="row" style="gap:8px; flex-wrap:wrap;"><button class="btn btn-small" type="button" id="neo-identity-profile-load">Load</button><button class="btn btn-small" type="button" id="neo-identity-profile-save">Save</button><button class="btn btn-small" type="button" id="neo-identity-profile-delete">Delete</button></div>
          </div>
          <input id="neo-identity-profile-id" type="hidden" value="" />
          <div class="grid grid-2" style="gap:10px; margin-top:10px;">
            <div><label>Reference image filenames / paths</label><textarea id="neo-identity-profile-refs" rows="3" placeholder="maya_ref_01.png&#10;maya_ref_02.png"></textarea></div>
            <div><label>Notes / trigger words</label><textarea id="neo-identity-profile-notes" rows="3" placeholder="Main character notes, outfit locks, etc."></textarea></div>
          </div>
          <div class="grid grid-4" style="gap:10px; margin-top:10px; align-items:end;">
            <div><label>CLIP Vision</label><input id="neo-identity-profile-clip" value="auto" /></div>
            <div><label>Weight</label><input id="neo-identity-profile-weight" type="number" step="0.01" min="0" max="2" value="0.45" /></div>
            <div><label>Start</label><input id="neo-identity-profile-start" type="number" step="0.01" min="0" max="1" value="0" /></div>
            <div><label>End</label><input id="neo-identity-profile-end" type="number" step="0.01" min="0" max="1" value="0.65" /></div>
          </div>
          <div class="grid grid-4" style="gap:10px; margin-top:10px; align-items:end;">
            <div><label>Optional LoRA</label><input id="neo-identity-profile-lora" placeholder="character_lora.safetensors" /></div>
            <div><label>LoRA weight</label><input id="neo-identity-profile-lora-weight" type="number" step="0.05" min="0" max="2" value="0.8" /></div>
            <div><label>Trigger words</label><input id="neo-identity-profile-triggers" placeholder="maya character" /></div>
            <button class="btn btn-small" type="button" id="neo-identity-profile-new">Clear / New</button>
          </div>
          <div class="mini-note" style="margin-top:8px;">${profileStorageNote()}</div>
        </details>
        <details class="neo-scene-preset-panel" style="margin:12px 0; padding:12px; border:1px solid rgba(148,163,184,.18); border-radius:14px; background:rgba(15,23,42,.28);">
          <summary class="row-between" style="gap:10px; align-items:center; flex-wrap:wrap; cursor:pointer; list-style:none;">
            <div>
              <div class="stat-title">Scene Presets</div>
              <div class="muted small">Save/load global prompt, contracts, region layout, region prompts, IPAdapter bindings, and LoRA Apply-To mapping.</div>
            </div>
            <span class="badge">Presets ▾</span>
          </summary>
          <div class="grid grid-4" style="gap:10px; margin-top:10px; align-items:end;">
            <div>
              <label>Saved preset</label>
              <select id="neo-scene-preset-select"><option value="">Select saved preset...</option></select>
            </div>
            <div>
              <label>Preset name</label>
              <input id="neo-scene-preset-name" type="text" placeholder="Couple Portrait" />
            </div>
            <button class="btn btn-small" type="button" id="neo-scene-preset-save">Save / Save As</button>
            <div class="row" style="gap:8px; flex-wrap:wrap;">
              <button class="btn btn-small" type="button" id="neo-scene-preset-load">Load</button>
              <button class="btn btn-small" type="button" id="neo-scene-preset-delete">Delete</button>
              <button class="btn btn-small" type="button" id="neo-scene-preset-refresh">Refresh</button>
            </div>
          </div>
          <div class="mini-note" style="margin-top:8px;">Preset files are stored locally under <code>neo_library_data/studio_user_data/scene_presets</code>.</div>
        </details>
        <details class="neo-scene-layout-preset-panel" style="margin:12px 0; padding:12px; border:1px solid rgba(148,163,184,.18); border-radius:14px; background:rgba(15,23,42,.24);">
          <summary class="row-between" style="gap:10px; align-items:center; flex-wrap:wrap; cursor:pointer; list-style:none;">
            <div>
              <div class="stat-title">Region Layout Presets</div>
              <div class="muted small">Quick-create common region boxes. Existing prompts and IPAdapter bindings are kept by index unless you replace prompts.</div>
            </div>
            <span class="badge">Layouts ▾</span>
          </summary>
          <div class="row" style="gap:8px; flex-wrap:wrap; margin-top:10px;">
            ${renderLayoutPresetButtons()}
            <button class="btn btn-small" type="button" id="neo-scene-layout-clear">Clear Regions</button>
          </div>
          <div class="row" style="gap:14px; flex-wrap:wrap; margin-top:10px;">
            <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-layout-keep-bindings" checked /> Keep existing prompts/IPAdapter by matching index</label>
            <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-layout-replace-prompts" /> Replace region prompts with preset helper text</label>
          </div>
          <div class="mini-note" style="margin-top:8px;">Tip: use layout presets first, then assign LoRA Apply-To and IPAdapter slots. For multi-FaceID, keep masks separated to reduce identity bleed.</div>
        </details>
        <div class="neo-scene-director-layout">
          <div class="neo-scene-director-canvas-wrap">
            <div class="row-between" style="gap:12px; align-items:flex-start;">
              <div>
                <div class="stat-title">Canvas regional editor</div>
                <div class="muted small" id="neo-scene-director-canvas-meta">Matches Neo output size.</div>
              </div>
              <button class="btn btn-small" id="neo-scene-director-add-region" type="button">+ Add Region</button>
            </div>
            <div class="neo-scene-director-canvas-frame" id="neo-scene-director-canvas-frame">
              <div class="neo-scene-director-region-layer" id="neo-scene-director-region-layer"></div>
              <div class="neo-scene-director-canvas-empty">Drag boxes to move. Use corner handles to resize.</div>
            </div>
          </div>
          <div class="neo-scene-director-global-card">
            <details class="neo-scene-linked-inputs-collapse" id="neo-scene-linked-inputs-collapse">
              <summary class="row-between" style="cursor:pointer; gap:10px; align-items:center; list-style:none;">
                <div>
                  <div class="stat-title">Neo-linked inputs</div>
                  <div class="muted small">Prompt/contracts and Neo input routing. Expand only when editing contracts.</div>
                </div>
                <span class="badge">Expand</span>
              </summary>
              <div class="neo-scene-director-chip-grid" style="margin-top:10px;">
                <span>Main prompt: global</span>
                <span>Negative: global</span>
                <span>Sampler/settings: Neo</span>
                <span>Preview/output: Neo</span>
              </div>
            <div class="neo-scene-contract-panel" style="margin-top:12px; padding:12px; border:1px solid rgba(148,163,184,.18); border-radius:14px; background:rgba(15,23,42,.34);">
              <div class="row-between" style="gap:10px; align-items:center;">
                <div>
                  <div class="stat-title">Prompt Contracts</div>
                  <div class="muted small">Editable structure text. No hidden gender, body type, couple type, or style is injected by Neo.</div>
                </div>
                <button class="btn btn-small" type="button" id="neo-scene-reset-contracts">Reset Defaults</button>
              </div>
              <div class="grid grid-2" style="gap:10px; margin-top:10px;">
                <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-contracts-enabled" ${((saved.contracts || {}).enabled === false) ? '' : 'checked'} /> Enable editable contracts</label>
                <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-node-auto-prompts" ${((saved.contracts || {}).use_node_auto_prompts === true) ? 'checked' : ''} /> Use V052 node auto prompts</label>
              </div>
              <label style="margin-top:10px; display:block;">Count contract</label>
              <textarea id="neo-scene-count-contract" rows="2" placeholder="exactly {count} visible subjects...">${escapeHtml((saved.contracts || {}).count_contract || DEFAULT_CONTRACTS.count_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Subject contract</label>
              <textarea id="neo-scene-subject-contract" rows="2" placeholder="one complete subject inside this region...">${escapeHtml((saved.contracts || {}).subject_contract || DEFAULT_CONTRACTS.subject_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Negative contract</label>
              <textarea id="neo-scene-negative-contract" rows="2" placeholder="extra people, missing subject...">${escapeHtml((saved.contracts || {}).negative_contract || DEFAULT_CONTRACTS.negative_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Style merge note</label>
              <textarea id="neo-scene-style-merge" rows="2" placeholder="use Neo main prompt as scene style...">${escapeHtml((saved.contracts || {}).style_merge || DEFAULT_CONTRACTS.style_merge)}</textarea>
              <div class="mini-note" style="margin-top:8px;">Use <code>{count}</code> inside contracts. Identity/gender/body words should live in your main or region prompts only.</div>
            </div>
            <div class="mini-note" id="neo-scene-director-prompt-summary" style="margin-top:10px;">Prompt payload will be staged here.</div><div class="mini-note" style="margin-top:10px;">LoRA per region is intentionally staged until the backend node patch lands.</div>
          </div>
        </div>
        <div class="neo-scene-director-region-list-head row-between">
          <div>
            <div class="stat-title">Regions</div>
            <div class="muted small">Controls live below the canvas so the right-side Prompt Stack and Image Preview shell stay intact.</div>
          </div>
        </div>
        <div id="neo-scene-director-regions-host"></div>
      </div>`;
    parent.prepend(shell);
    bindRegionEvents(shell);
    refreshScenePresetList();
    refreshIdentityProfiles();
    $('neo-identity-profile-load')?.addEventListener('click', () => loadIdentityProfile());
    $('neo-identity-profile-save')?.addEventListener('click', saveIdentityProfile);
    $('neo-identity-profile-delete')?.addEventListener('click', deleteIdentityProfile);
    $('neo-identity-profile-new')?.addEventListener('click', () => { setIdentityProfileForm({}); setStatus('Ready for a new Identity Profile.', 'muted'); });
    $('neo-identity-profile-select')?.addEventListener('change', event => { if (event.target.value) loadIdentityProfile(event.target.value); });
    $('neo-scene-preset-refresh')?.addEventListener('click', () => refreshScenePresetList());
    $('neo-scene-preset-save')?.addEventListener('click', saveScenePreset);
    $('neo-scene-preset-load')?.addEventListener('click', loadScenePreset);
    $('neo-scene-preset-delete')?.addEventListener('click', deleteScenePreset);
    $('neo-scene-preset-select')?.addEventListener('change', event => {
      const label = event.target.selectedOptions?.[0]?.textContent || '';
      if ($('neo-scene-preset-name') && event.target.value) $('neo-scene-preset-name').value = label.replace(/\s+\(\d+ regions\)$/, '');
    });
    shell.querySelectorAll('[data-scene-layout-preset]').forEach(btn => btn.addEventListener('click', event => applyRegionLayoutPreset(event.currentTarget.getAttribute('data-scene-layout-preset'))));
    $('neo-scene-layout-clear')?.addEventListener('click', () => { regions = []; selectedRegionId = null; renderRegions(); updateCanvasShell(); saveState({ manual_layout_override: true, last_layout_preset: '' }); setStatus('Scene Director regions cleared.', 'muted'); });
    $('neo-scene-director-add-region')?.addEventListener('click', addRegion);
    const layer = $('neo-scene-director-region-layer');
    layer?.addEventListener('pointerdown', event => {
      const handle = event.target?.closest?.('[data-region-resize]');
      if (handle) { beginInteraction(event, handle.getAttribute('data-region-resize'), 'resize', handle.getAttribute('data-handle') || 'se'); return; }
      const box = event.target?.closest?.('.neo-scene-director-region-box');
      if (box?.dataset?.regionId) beginInteraction(event, box.dataset.regionId, 'move');
    });
    window.addEventListener('pointermove', event => {
      if (!activeInteraction) return;
      const rect = rectFromInteraction(event);
      if (rect) applyRectToRegion(activeInteraction.id, rect, { manual: true });
    });
    window.addEventListener('pointerup', () => { if (activeInteraction) saveState({ manual_layout_override: true, last_layout_preset: '' }); endInteraction(); });
    window.addEventListener('pointercancel', () => { if (activeInteraction) saveState({ manual_layout_override: true, last_layout_preset: '' }); endInteraction(); });
    shell.addEventListener('keydown', event => {
      if (!selectedRegionId || ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName)) return;
      const region = getRegion(selectedRegionId);
      if (!region || region.locked) return;
      const step = event.shiftKey ? 0.025 : 0.006;
      const rect = normalizeRegionRect(region.rect);
      if (event.key === 'ArrowLeft') rect.x -= step;
      else if (event.key === 'ArrowRight') rect.x += step;
      else if (event.key === 'ArrowUp') rect.y -= step;
      else if (event.key === 'ArrowDown') rect.y += step;
      else return;
      event.preventDefault();
      applyRectToRegion(selectedRegionId, rect, { manual: true });
    });
    $('neo-scene-director-enabled')?.addEventListener('change', event => {
      const enabled = !!event.target.checked;
      if (!isAllowedFamily()) {
        event.target.checked = false;
        updateEligibility();
        return;
      }
      saveState();
      setExtensionEnabled(enabled);
      updateCanvasShell();
    });
    ['generation-width', 'generation-height'].forEach(id => $(id)?.addEventListener('input', updateCanvasShell));
    ['generation-ipadapter-enabled', 'generation-ipadapter-mode', 'generation-ipadapter-name', 'generation-ipadapter-clip-vision', 'generation-ipadapter-weight', 'generation-ipadapter-weight-faceidv2', 'generation-ipadapter-image'].forEach(id => $(id)?.addEventListener('change', () => { renderRegions(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); }));
    document.getElementById('generation-ipadapter-extra-list')?.addEventListener('change', () => { renderRegions(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); });
    ['generation-positive', 'generation-negative', 'generation-prompt', 'prompt', 'generation-negative-prompt', 'negative-prompt', 'negative_prompt'].forEach(id => $(id)?.addEventListener('input', () => { syncPromptPayload(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); }));
    ['neo-scene-contracts-enabled', 'neo-scene-node-auto-prompts', 'neo-scene-count-contract', 'neo-scene-subject-contract', 'neo-scene-negative-contract', 'neo-scene-style-merge'].forEach(id => $(id)?.addEventListener('input', () => { saveState({ contracts: getPromptContracts() }); syncPromptPayload(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); }));
    $('neo-scene-reset-contracts')?.addEventListener('click', resetPromptContracts);
    document.addEventListener('neo-generation-family-changed', updateEligibility);
    renderRegions();
    updateCanvasShell();
    updateEligibility();
  }

  async function init() {
    if (mounted) return;
    const host = $('generation-assets-tab-host');
    if (!host) return;
    mounted = true;
    registryRecord = await fetchRecord();
    mountShell(host);
    if (registryRecord && $('neo-scene-director-enabled')) {
      $('neo-scene-director-enabled').checked = !!registryRecord.enabled || !!loadState().enabled;
      saveState({ registry_enabled: !!registryRecord.enabled });
    }
  }

  function retryInit(attempt = 0) {
    if ($('generation-assets-tab-host')) { init(); return; }
    if (attempt > 40) return;
    window.setTimeout(() => retryInit(attempt + 1), 125);
  }

  window.NeoSceneDirectorExtension = {
    id: EXTENSION_ID,
    phase: 10.3,
    ready: true,
    mount: init,
    getState: () => { forceLiveCanvasState('generation_live_canvas'); return getPromptPayload(); },
    getRegionTargets: () => getSceneRegionTargets(),
    validate: () => validatePromptPayload(),
    savePresetPayload: captureScenePresetPayload,
    loadPresetPayload: applyScenePresetPayload,
    refreshIdentityProfiles,
    getIdentityProfiles: () => identityProfiles,
    getIdentityUnits: () => buildSceneDirectorIdentityUnits(regions.map((region, index) => normalizeRegionData(region, index))),
  };

  ready(() => retryInit());
})();
