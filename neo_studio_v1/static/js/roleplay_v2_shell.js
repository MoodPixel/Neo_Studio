(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;

  function textBackendSession() {
    return window.getBackendRoleState?.('text') || { state: 'offline', connected: false };
  }
  function currentTextBackendState() {
    return core.text(textBackendSession()?.state || 'offline').toLowerCase() || 'offline';
  }
  function currentTextBackendLabel() {
    const session = textBackendSession();
    const manager = window.getBackendManagerState?.() || {};
    const profileId = manager?.active_profile_ids?.text || '';
    const profiles = Array.isArray(manager?.profiles?.text) ? manager.profiles.text : [];
    const profile = profiles.find(row => core.text(row?.id) === core.text(profileId)) || profiles[0] || null;
    if (session?.connected) return core.text(session.profile_name) || core.text(profile?.name) || 'Active text backend';
    return core.text(profile?.name) || 'No active text backend';
  }
  function currentTextBackendBody() {
    const session = textBackendSession();
    const manager = window.getBackendManagerState?.() || {};
    const profileId = manager?.active_profile_ids?.text || '';
    const profiles = Array.isArray(manager?.profiles?.text) ? manager.profiles.text : [];
    const profile = profiles.find(row => core.text(row?.id) === core.text(profileId)) || profiles[0] || null;
    if (session?.connected) {
      const bits = [];
      if (session.base_url) bits.push(session.base_url);
      if (session.latency_ms != null) bits.push(`${session.latency_ms} ms`);
      if (Array.isArray(session.capabilities) && session.capabilities.length) bits.push(session.capabilities.join(' · '));
      return bits.join(' · ') || 'Text backend connected for live Scene use.';
    }
    if (profile?.base_url) return `Saved text backend profile ready at ${profile.base_url}. Connect it here or manage it in Admin.`;
    return 'Set up a Text Backend in Admin to use live Scene turns. Studio prep work still works without it.';
  }
  function currentModelLabel() {
    return core.text(core.$('model-select')?.selectedOptions?.[0]?.textContent) || core.text(core.$('model-select')?.value) || 'default';
  }
  function currentModelTone() {
    const clean = currentModelLabel().toLowerCase();
    return ['vision', 'vl', 'llava', 'qwen2.5-vl', 'qwen-vl', 'pixtral', 'molmo', 'omni', 'multimodal'].some(h => clean.includes(h)) ? 'specialty' : 'primary';
  }
  function shellChip(label, value, tone = 'neutral') {
    return `<span class="surface-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`;
  }
  function safeRemove(key){ try { window.localStorage.removeItem(key); } catch (_) {} }
  function readJson(key, fallback){ try { const raw = window.localStorage.getItem(key); return raw ? (JSON.parse(raw) || fallback) : fallback; } catch (_) { return fallback; } }
  function writeJson(key, value){ try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (_) {} }
  function slugify(value){ return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || `rpv2-${Date.now().toString(36)}`; }
  function uid(prefix){ return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`; }

  const PRESET_SELECTED_KEY = 'neo-roleplay-v2-workspace-preset-selected';
  const PRESET_DEFAULT_KEY = 'neo-roleplay-v2-workspace-preset-default';
  const PRESET_ACTIVE_KEY = 'neo-roleplay-v2-workspace-preset-active';
  const PRESET_SAVED_KEY = 'neo-roleplay-v2-workspace-presets';
  const BUILTIN_PRESETS = [
    { id:'live_scene', name:'Live scene', tone:'primary', snapshot:{ output_preset:'roleplay', interaction_mode:'roleplay' } },
    { id:'short_story_authoring', name:'Short story authoring', tone:'recovery', snapshot:{ output_preset:'short_story', interaction_mode:'authoring' } },
    { id:'novel_authoring', name:'Novel authoring', tone:'success', snapshot:{ output_preset:'novel', interaction_mode:'authoring' } },
    { id:'cinematic_authoring', name:'Cinematic authoring', tone:'warning', snapshot:{ output_preset:'cinematic', interaction_mode:'authoring' } },
  ];

  function selectedRef(){ return core.text(core.safeLocalStorageGet(PRESET_SELECTED_KEY)); }
  function activeRef(){ return core.text(core.safeLocalStorageGet(PRESET_ACTIVE_KEY)); }
  function defaultRef(){ return core.text(core.safeLocalStorageGet(PRESET_DEFAULT_KEY)); }
  function setSelectedRef(ref){ ref ? core.safeLocalStorageSet(PRESET_SELECTED_KEY, ref) : safeRemove(PRESET_SELECTED_KEY); }
  function setActiveRef(ref){ ref ? core.safeLocalStorageSet(PRESET_ACTIVE_KEY, ref) : safeRemove(PRESET_ACTIVE_KEY); }
  function setDefaultRef(ref){ ref ? core.safeLocalStorageSet(PRESET_DEFAULT_KEY, ref) : safeRemove(PRESET_DEFAULT_KEY); }
  function getSavedPresets(){ const rows = readJson(PRESET_SAVED_KEY, []); return Array.isArray(rows) ? rows.filter(item => item && typeof item === 'object' && core.text(item.id)) : []; }
  function setSavedPresets(rows){ writeJson(PRESET_SAVED_KEY, Array.isArray(rows) ? rows : []); }
  function builtinRef(id){ return `builtin:${id}`; }
  function savedRef(id){ return `saved:${id}`; }
  function currentModeSnapshot(){
    const mode = core.currentModeSelection();
    return { output_preset: mode.output_preset, interaction_mode: mode.interaction_mode, goal_label: mode.goal_label };
  }
  function defaultPresetName(){
    const mode = currentModeSnapshot();
    return mode.goal_label || `${mode.output_preset} · ${mode.interaction_mode}`;
  }
  function resolvePreset(ref){
    const clean = core.text(ref);
    if (!clean) return null;
    if (clean.startsWith('builtin:')) {
      const item = BUILTIN_PRESETS.find(row => row.id === clean.slice(8));
      return item ? { ...item, ref: clean, type:'builtin' } : null;
    }
    if (clean.startsWith('saved:')) {
      const item = getSavedPresets().find(row => core.text(row.id) === clean.slice(6));
      return item ? { ...item, ref: clean, type:'saved', tone: item.tone || 'neutral', name: item.name || 'Untitled preset' } : null;
    }
    return null;
  }
  function syncPresetSelect(){
    const select = core.$('roleplay-v2-shell-preset-select');
    if (!select) return;
    select.innerHTML = '';
    const base = document.createElement('option');
    base.value = '';
    base.textContent = 'Workspace presets…';
    select.appendChild(base);
    const builtinGroup = document.createElement('optgroup');
    builtinGroup.label = 'Built-in starters';
    BUILTIN_PRESETS.forEach(item => {
      const opt = document.createElement('option');
      opt.value = builtinRef(item.id);
      opt.textContent = item.name;
      builtinGroup.appendChild(opt);
    });
    select.appendChild(builtinGroup);
    const savedRows = getSavedPresets();
    if (savedRows.length) {
      const savedGroup = document.createElement('optgroup');
      savedGroup.label = 'Saved workspace presets';
      savedRows.forEach(item => {
        const opt = document.createElement('option');
        opt.value = savedRef(item.id);
        opt.textContent = item.name || 'Untitled preset';
        savedGroup.appendChild(opt);
      });
      select.appendChild(savedGroup);
    }
    const preferred = selectedRef() || activeRef() || defaultRef() || '';
    if (preferred && resolvePreset(preferred)) select.value = preferred;
    syncPresetButtons();
  }
  function syncPresetButtons(){
    const item = resolvePreset(core.$('roleplay-v2-shell-preset-select')?.value);
    const updateBtn = core.$('btn-roleplay-v2-update-preset');
    const deleteBtn = core.$('btn-roleplay-v2-delete-preset');
    if (updateBtn) updateBtn.disabled = !(item && item.type === 'saved');
    if (deleteBtn) deleteBtn.disabled = !(item && item.type === 'saved');
  }
  function syncPresetBadge(ref = '') {
    const item = resolvePreset(ref);
    const badge = core.$('roleplay-v2-preset-active-badge');
    const meta = core.$('roleplay-v2-preset-meta');
    const mode = currentModeSnapshot();
    if (badge) {
      badge.textContent = item?.name || 'Manual setup';
      badge.dataset.uiTone = item?.tone || 'neutral';
    }
    if (meta) {
      if (item) {
        const intro = item.type === 'saved'
          ? 'Workspace preset is saved in this browser.'
          : 'Built-in starter is active.';
        meta.textContent = `${intro} Current pair → output_preset=${mode.output_preset} · interaction_mode=${mode.interaction_mode}. It only restores the top shell mode pairing. Studio focus, memory build state, retrieval paths, Scene packets, and saved V2 records still stay separate.`;
      } else {
        meta.textContent = 'Manual setup leaves the current shell framing untouched. Studio focus, memory build state, retrieval paths, Scene packets, and saved V2 records still stay separate.';
      }
    }
  }
  function applyResolvedPreset(item, { announce = true } = {}) {
    if (!item) {
      setActiveRef('');
      syncPresetBadge('');
      renderModeSummary();
      renderShellSummary();
      if (announce) core.setStatus('roleplay-v2-preset-status', 'Workspace preset selection cleared. Current shell stays manual.', 'success');
      return;
    }
    core.applyModeSelection(item.snapshot || {});
    const select = core.$('roleplay-v2-shell-preset-select');
    if (select) select.value = item.ref;
    setSelectedRef(item.ref);
    setActiveRef(item.ref);
    syncPresetBadge(item.ref);
    renderModeSummary();
    renderShellSummary();
    syncPresetButtons();
    if (announce) core.setStatus('roleplay-v2-preset-status', `${item.type === 'saved' ? 'Loaded workspace preset' : 'Loaded starter preset'}: ${item.name || 'Untitled preset'}`, 'success');
  }
  function loadSelectedPreset(){
    const item = resolvePreset(core.$('roleplay-v2-shell-preset-select')?.value || '');
    if (!item) {
      applyResolvedPreset(null, { announce:true });
      return;
    }
    applyResolvedPreset(item, { announce:true });
  }
  function savePreset({ updateExisting = false } = {}) {
    const currentItem = resolvePreset(core.$('roleplay-v2-shell-preset-select')?.value || selectedRef() || activeRef() || '');
    if (updateExisting && (!currentItem || currentItem.type !== 'saved')) {
      core.setStatus('roleplay-v2-preset-status', 'Pick a saved workspace preset first if you want to update one.', 'warn');
      return;
    }
    const nextName = String(window.prompt(updateExisting ? 'Update this workspace preset name if needed:' : 'Name this workspace preset:', currentItem?.name || defaultPresetName()) || '').trim();
    if (!nextName) {
      core.setStatus('roleplay-v2-preset-status', 'Workspace preset save cancelled.', 'warn');
      return;
    }
    const snapshot = currentModeSnapshot();
    const rows = getSavedPresets();
    let target;
    if (updateExisting && currentItem) {
      target = rows.find(row => core.text(row.id) === core.text(currentItem.id));
      if (!target) {
        core.setStatus('roleplay-v2-preset-status', 'That workspace preset no longer exists in this browser.', 'warn');
        return;
      }
      target.name = nextName;
      target.snapshot = { output_preset: snapshot.output_preset, interaction_mode: snapshot.interaction_mode };
      target.updated_at = new Date().toISOString();
    } else {
      target = {
        id: slugify(uid('rpv2')),
        name: nextName,
        tone: currentItem?.tone || 'neutral',
        snapshot: { output_preset: snapshot.output_preset, interaction_mode: snapshot.interaction_mode },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      rows.push(target);
    }
    setSavedPresets(rows);
    syncPresetSelect();
    const ref = savedRef(target.id);
    const select = core.$('roleplay-v2-shell-preset-select');
    if (select) select.value = ref;
    applyResolvedPreset(resolvePreset(ref), { announce:false });
    core.setStatus('roleplay-v2-preset-status', `${updateExisting ? 'Updated' : 'Saved'} workspace preset: ${nextName}`, 'success');
  }
  function deletePreset(){
    const item = resolvePreset(core.$('roleplay-v2-shell-preset-select')?.value || '');
    if (!item || item.type !== 'saved') {
      core.setStatus('roleplay-v2-preset-status', 'Pick a saved workspace preset first.', 'warn');
      return;
    }
    if (!window.confirm(`Delete workspace preset "${item.name || 'Untitled preset'}"?`)) return;
    const rows = getSavedPresets().filter(row => core.text(row.id) !== core.text(item.id));
    setSavedPresets(rows);
    if (selectedRef() === item.ref) setSelectedRef('');
    if (activeRef() === item.ref) setActiveRef('');
    if (defaultRef() === item.ref) setDefaultRef('');
    syncPresetSelect();
    syncPresetBadge('');
    renderShellSummary();
    core.setStatus('roleplay-v2-preset-status', `Deleted workspace preset: ${item.name || 'Untitled preset'}`, 'success');
  }
  function setDefaultPreset(){
    const item = resolvePreset(core.$('roleplay-v2-shell-preset-select')?.value || '');
    if (!item) {
      core.setStatus('roleplay-v2-preset-status', 'Pick a workspace preset first.', 'warn');
      return;
    }
    setDefaultRef(item.ref);
    core.setStatus('roleplay-v2-preset-status', `Default workspace preset set: ${item.name || 'Untitled preset'}`, 'success');
  }
  function clearDefaultPreset(){
    setDefaultRef('');
    core.setStatus('roleplay-v2-preset-status', 'Default workspace preset cleared.', 'success');
  }
  function manualizePresetSelection(){
    setActiveRef('');
    const select = core.$('roleplay-v2-shell-preset-select');
    if (select) select.value = '';
    setSelectedRef('');
    syncPresetButtons();
    syncPresetBadge('');
  }

  function captureShellState() {
    const mode = core.currentModeSelection();
    return {
      backend_state: currentTextBackendState(),
      backend_label: currentTextBackendLabel(),
      engine: currentModelLabel(),
      engine_tone: currentModelTone(),
      output_preset: mode.output_preset,
      interaction_mode: mode.interaction_mode,
      goal_key: mode.goal_key,
      goal_label: mode.goal_label,
      preset_label: core.text(core.$('roleplay-v2-preset-active-badge')?.textContent) || 'Manual setup',
    };
  }
  function renderShellDetails() {
    const pre = core.$('roleplay-v2-shell-summary');
    if (!pre) return;
    pre.textContent = JSON.stringify(captureShellState(), null, 2);
  }
  function renderModelCapability() {
    const label = currentModelLabel();
    const badge = core.$('roleplay-v2-model-capability-badge');
    const meta = core.$('roleplay-v2-model-current-label');
    const note = core.$('roleplay-v2-model-capability-note');
    if (badge) badge.textContent = currentModelTone() === 'specialty' ? 'Vision-capable' : 'Text-only';
    if (meta) meta.textContent = `Current model · ${label}`;
    if (note) note.textContent = currentModelTone() === 'specialty'
      ? 'Current model looks multimodal/vision-capable. V2 still treats the Scene lane as text-first until full multimodal scene support lands.'
      : 'Current model is treated as text-first for the V2 scene/runtime flow.';
    renderShellSummary();
  }
  function renderBackendMirror() {
    const session = textBackendSession();
    const stateValue = currentTextBackendState();
    const stateEl = core.$('surface-backend-roleplay-v2-state');
    const nameEl = core.$('surface-backend-roleplay-v2-name');
    const bodyEl = core.$('roleplay-v2-text-backend-note-body');
    const note = core.$('roleplay-v2-text-backend-note');
    const connectBtn = core.$('btn-surface-backend-roleplay-v2-connect');
    const disconnectBtn = core.$('btn-surface-backend-roleplay-v2-disconnect');
    if (stateEl) {
      stateEl.className = `backend-chip state-${stateValue}`;
      stateEl.textContent = stateValue === 'online' ? 'Online' : stateValue === 'ready' ? 'Ready' : stateValue === 'busy' ? 'Busy' : stateValue === 'connected' ? 'Connected' : stateValue === 'error' ? 'Error' : 'Offline';
    }
    if (nameEl) nameEl.textContent = currentTextBackendLabel();
    if (bodyEl) bodyEl.textContent = currentTextBackendBody();
    if (note) {
      note.classList.toggle('offline', !session?.connected);
      note.classList.toggle('connected', !!session?.connected);
    }
    if (connectBtn) connectBtn.textContent = session?.connected ? 'Refresh Text Backend' : 'Connect Text Backend';
    if (disconnectBtn) disconnectBtn.disabled = !session?.connected;
    renderShellSummary();
  }
  function renderModeSummary() {
    const badge = core.$('roleplay-v2-mode-active-badge');
    const meta = core.$('roleplay-v2-mode-meta');
    const mode = core.currentModeSelection();
    if (badge) badge.textContent = mode.goal_label;
    if (meta) meta.textContent = `Session goal is locked to one canonical pair. Current: ${mode.goal_label} → output_preset=${mode.output_preset} · interaction_mode=${mode.interaction_mode}.`;
    syncPresetBadge(activeRef());
    renderShellSummary();
  }
  function renderShellSummary() {
    const strip = core.$('roleplay-v2-setup-shell-summary-strip');
    if (!strip) return;
    const shell = captureShellState();
    strip.innerHTML = `<span class="surface-setup-shell-summary-label">Current setup</span><span class="backend-chip state-${shell.backend_state}">${shell.backend_label}</span>${shellChip('Engine', shell.engine, shell.engine_tone)}${shellChip('Goal', shell.goal_label, 'primary')}${shellChip('Output', shell.output_preset, 'primary')}${shellChip('Interaction', shell.interaction_mode, 'neutral')}${shellChip('Preset', shell.preset_label, 'neutral')}`;
    renderShellDetails();
  }
  function applyShellOpen(open) {
    const header = core.$('roleplay-v2-setup-shell-header');
    const content = core.$('roleplay-v2-setup-shell-content');
    const panel = core.$('roleplay-v2-setup-shell-panel');
    const summary = core.$('roleplay-v2-setup-shell-summary-strip');
    const toggleCopy = core.$('roleplay-v2-setup-shell-toggle-copy');
    if (!content || !panel) return;
    const isOpen = !!open;
    renderShellSummary();
    content.style.display = isOpen ? '' : 'none';
    panel.classList.toggle('is-collapsed', !isOpen);
    header?.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    summary?.classList.toggle('hidden', isOpen);
    if (toggleCopy) toggleCopy.textContent = isOpen ? 'Collapse setup' : 'Expand setup';
    try { window.sessionStorage.setItem(core.SHELL_KEY, isOpen ? 'true' : 'false'); } catch (_) {}
  }
  function toggleShell() {
    const content = core.$('roleplay-v2-setup-shell-content');
    applyShellOpen(!!(content && content.style.display === 'none'));
  }
  async function handleConnectOrRefresh() {
    try {
      if (window.quickConnectBackendRole) await window.quickConnectBackendRole('text');
      else if (window.openBackendManager) window.openBackendManager('text');
      renderBackendMirror();
    } catch (err) {
      core.setStatus('roleplay-v2-settings-status', err.message || String(err), 'error');
    }
  }
  async function handleDisconnect() {
    try {
      if (window.quickDisconnectBackendRole) await window.quickDisconnectBackendRole('text');
      else if (window.openBackendManager) window.openBackendManager('text');
      renderBackendMirror();
    } catch (err) {
      core.setStatus('roleplay-v2-settings-status', err.message || String(err), 'error');
    }
  }
  async function boot() {
    const header = core.$('roleplay-v2-setup-shell-header');
    const saved = (() => { try { return window.sessionStorage.getItem(core.SHELL_KEY); } catch (_) { return null; } })();
    applyShellOpen(saved === null ? true : saved === 'true');
    header?.addEventListener('click', toggleShell);
    header?.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleShell();
      }
    });
    document.addEventListener('neo-backend-state', renderBackendMirror);
    document.addEventListener('neo-manager-model-changed', renderModelCapability);
    core.$('btn-surface-backend-roleplay-v2-connect')?.addEventListener('click', () => { handleConnectOrRefresh().catch(() => {}); });
    core.$('btn-surface-backend-roleplay-v2-disconnect')?.addEventListener('click', () => { handleDisconnect().catch(() => {}); });
    core.$('btn-roleplay-v2-manage-backend')?.addEventListener('click', () => window.openBackendManager?.('text'));
    core.$('roleplay-v2-shell-preset-select')?.addEventListener('change', event => {
      setSelectedRef(core.text(event?.target?.value));
      syncPresetButtons();
    });
    core.$('btn-roleplay-v2-load-preset')?.addEventListener('click', loadSelectedPreset);
    core.$('btn-roleplay-v2-save-preset')?.addEventListener('click', () => savePreset({ updateExisting:false }));
    core.$('btn-roleplay-v2-update-preset')?.addEventListener('click', () => savePreset({ updateExisting:true }));
    core.$('btn-roleplay-v2-delete-preset')?.addEventListener('click', deletePreset);
    core.$('btn-roleplay-v2-set-default-preset')?.addEventListener('click', setDefaultPreset);
    core.$('btn-roleplay-v2-clear-default-preset')?.addEventListener('click', clearDefaultPreset);
    core.$('roleplay-v2-output-preset')?.addEventListener('change', () => {
      core.applyModeSelection({ outputPreset: core.$('roleplay-v2-output-preset')?.value, interactionMode: core.$('roleplay-v2-interaction-mode')?.value, prefer: 'output' });
      manualizePresetSelection();
      renderModeSummary();
    });
    core.$('roleplay-v2-interaction-mode')?.addEventListener('change', () => {
      core.applyModeSelection({ outputPreset: core.$('roleplay-v2-output-preset')?.value, interactionMode: core.$('roleplay-v2-interaction-mode')?.value, prefer: 'interaction' });
      manualizePresetSelection();
      renderModeSummary();
    });
    try { await window.fetchBackendManagerState?.({ silent: true }); } catch (_) {}
    syncPresetSelect();
    const startupRef = activeRef() || defaultRef() || '';
    if (startupRef && resolvePreset(startupRef)) {
      const select = core.$('roleplay-v2-shell-preset-select');
      if (select) select.value = startupRef;
      applyResolvedPreset(resolvePreset(startupRef), { announce:false });
    } else {
      renderModeSummary();
      syncPresetBadge('');
    }
    renderBackendMirror();
    renderModelCapability();
    renderModeSummary();
  }

  core.renderRoleplayV2ShellSummary = renderShellSummary;
  core.captureRoleplayV2ShellState = captureShellState;
  core.registerModule('shell', { boot, renderShellSummary, renderModelCapability, renderBackendMirror, captureShellState });
})();
