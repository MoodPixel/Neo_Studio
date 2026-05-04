let backendManagerState = null;
let backendChoiceResolver = null;
let backendStatusPollHandle = null;
const backendEditLockUntil = {};

function markBackendRoleEditing(role) {
  backendEditLockUntil[role] = Date.now() + 45000;
}

function isBackendRoleEditing(role) {
  const form = getBackendForm(role);
  const active = document.activeElement;
  const launcherFields = [form.launchType, form.launchPath, form.launchCwd, form.launchArgs, form.nativeUiUrl, form.name, form.url, form.timeout].filter(Boolean);
  if (launcherFields.includes(active)) return true;
  return (backendEditLockUntil[role] || 0) > Date.now();
}

function clearBackendRoleEditing(role) {
  backendEditLockUntil[role] = 0;
}

function clearBackendManagerCache() {
  try { window.NeoGenerationPerf?.clearCache?.('backend-manager-state'); } catch (_) {}
}

function rememberBackendManagerState(data) {
  backendManagerState = data;
  try { window.NeoGenerationPerf?.writeCache?.('backend-manager-state', data); } catch (_) {}
}

const DEFAULT_BACKEND_TYPE_BY_ROLE = {
  text: 'koboldcpp',
  image: 'comfyui',
  video: 'comfyui',
  voice: 'kokoro',
  audio: 'stable_audio',
};

const DEFAULT_TIMEOUT_BY_ROLE = {
  text: 8,
  image: 12,
  video: 20,
  voice: 20,
  audio: 30,
};

const surfaceBackendBindings = {
  generate: { role:'image', stateId:'surface-backend-generate-state', nameId:'surface-backend-generate-name', metaId:'surface-backend-generate-meta', launchId:'btn-surface-backend-generate-launch', connectId:'btn-surface-backend-generate-connect', disconnectId:'btn-surface-backend-generate-disconnect', manageId:'btn-surface-backend-generate-manage' },
  manager: { role:'text', stateId:'surface-backend-manager-state', nameId:'surface-backend-manager-name', metaId:'surface-backend-manager-meta', launchId:'btn-surface-backend-manager-launch', connectId:'btn-surface-backend-manager-connect', disconnectId:'btn-surface-backend-manager-disconnect', manageId:'btn-surface-backend-manager-manage' },
  video: { role:'video', roleLabel:'Video', stateId:'surface-backend-video-state', nameId:'surface-backend-video-name', metaId:'surface-backend-video-meta', launchId:'btn-surface-backend-video-launch', connectId:'btn-surface-backend-video-connect', disconnectId:'btn-surface-backend-video-disconnect', manageId:'btn-surface-backend-video-manage' },
  voice: { role:'voice', roleLabel:'Voice', stateId:'surface-backend-voice-state', nameId:'surface-backend-voice-name', metaId:'surface-backend-voice-meta', launchId:'btn-surface-backend-voice-launch', connectId:'btn-surface-backend-voice-connect', disconnectId:'btn-surface-backend-voice-disconnect', manageId:'btn-surface-backend-voice-manage' },
  audio: { role:'audio', roleLabel:'Music / SFX', stateId:'surface-backend-audio-state', nameId:'surface-backend-audio-name', metaId:'surface-backend-audio-meta', launchId:'btn-surface-backend-audio-launch', connectId:'btn-surface-backend-audio-connect', disconnectId:'btn-surface-backend-audio-disconnect', manageId:'btn-surface-backend-audio-manage' },
  roleplay: { role:'text', stateId:'surface-backend-roleplay-state', nameId:'surface-backend-roleplay-name', metaId:'roleplay-text-backend-note-body', launchId:'btn-surface-backend-roleplay-launch', connectId:'btn-surface-backend-roleplay-connect', disconnectId:'btn-surface-backend-roleplay-disconnect', manageId:'btn-roleplay-note-manage-backend', containerId:'roleplay-text-backend-note' },
  assistant: { role:'text', stateId:'surface-backend-assistant-state', nameId:'surface-backend-assistant-name', metaId:'assistant-text-backend-note-body', launchId:'btn-surface-backend-assistant-launch', connectId:'btn-surface-backend-assistant-connect', disconnectId:'btn-surface-backend-assistant-disconnect', manageId:'btn-assistant-note-manage-backend', containerId:'assistant-text-backend-note' },
};

function backendRoleLabel(role) {
  const key = String(role || '').toLowerCase();
  if (key === 'image') return 'Image';
  if (key === 'video') return 'Video';
  if (key === 'voice') return 'Voice';
  if (key === 'audio') return 'Music / SFX';
  return 'Text';
}

function managedBackendRoles() {
  const roles = backendManagerState?.managed_roles;
  if (Array.isArray(roles) && roles.length) return roles.slice();
  return ['text', 'image', 'video', 'voice', 'audio'];
}

function resolveSurfaceBindingRole(surfaceId, binding) {
  const registryRole = window.NeoSurfaceRegistry?.getBackendUsage?.(surfaceId)?.required?.[0];
  const allowed = new Set(managedBackendRoles());
  if (registryRole && allowed.has(registryRole)) return registryRole;
  if (binding?.role && allowed.has(binding.role)) return binding.role;
  return binding?.role || 'text';
}

function backendStateLabel(state) {
  const text = String(state || 'offline').toLowerCase();
  if (text === 'connected') return 'Connected';
  if (text === 'degraded') return 'Degraded';
  if (text === 'checking') return 'Checking';
  if (text === 'error') return 'Error';
  if (text === 'busy') return 'Busy';
  return 'Offline';
}

function applyBackendChipState(el, state) {
  if (!el) return;
  const clean = String(state || 'offline').toLowerCase();
  el.className = `backend-chip state-${clean}`;
  el.textContent = backendStateLabel(clean);
}

function getBackendForm(role) {
  return {
    type: $(`backend-${role}-type`),
    profile: $(`backend-${role}-profile`),
    name: $(`backend-${role}-name`),
    url: $(`backend-${role}-url`),
    timeout: $(`backend-${role}-timeout`),
    autoReconnect: $(`backend-${role}-auto-reconnect`),
    launchType: $(`backend-${role}-launch-type`),
    launchPath: $(`backend-${role}-launch-path`),
    launchCwd: $(`backend-${role}-launch-cwd`),
    launchArgs: $(`backend-${role}-launch-args`),
    nativeUiUrl: $(`backend-${role}-native-ui-url`),
    launchStatus: $(`backend-${role}-launch-status`),
    status: $(`backend-${role}-status`),
    result: $(`backend-${role}-result`),
    cardState: $(`backend-card-${role}-state`),
  };
}

function normalizeBackendProfiles(role) {
  const profiles = backendManagerState?.profiles?.[role];
  return Array.isArray(profiles) ? profiles : [];
}

function getActiveBackendProfile(role) {
  const activeId = backendManagerState?.active_profile_ids?.[role] || '';
  const rows = normalizeBackendProfiles(role);
  return rows.find(row => row.id === activeId) || rows[0] || null;
}

function getBackendProfileById(role, profileId) {
  return normalizeBackendProfiles(role).find(row => row.id === profileId) || null;
}

function fillBackendProfileSelect(role, selectedId='') {
  const form = getBackendForm(role);
  if (!form.profile) return;
  const rows = normalizeBackendProfiles(role);
  form.profile.innerHTML = '';
  rows.forEach(row => {
    const opt = document.createElement('option');
    opt.value = row.id || '';
    opt.textContent = row.name || row.id || '(unnamed)';
    if ((selectedId && row.id === selectedId) || (!selectedId && row.id === (backendManagerState?.active_profile_ids?.[role] || ''))) opt.selected = true;
    form.profile.appendChild(opt);
  });
  if (!form.profile.value && rows[0]?.id) form.profile.value = rows[0].id;
}

function applyBackendProfileToForm(role, profile) {
  const form = getBackendForm(role);
  if (!form.type) return;
  const data = profile || getActiveBackendProfile(role) || {};
  if (form.type) form.type.value = data.backend_type || DEFAULT_BACKEND_TYPE_BY_ROLE[role] || 'koboldcpp';
  if (form.name) form.name.value = data.name || '';
  if (form.url) form.url.value = data.base_url || '';
  if (form.timeout) form.timeout.value = data.timeout_sec ?? DEFAULT_TIMEOUT_BY_ROLE[role] ?? 8;
  if (form.autoReconnect) form.autoReconnect.checked = !!data.auto_reconnect;
  const launcher = data.launcher || {};
  if (form.launchType) form.launchType.value = launcher.launch_type || 'bat';
  if (form.launchPath) form.launchPath.value = launcher.backend_path || '';
  if (form.launchCwd) form.launchCwd.value = launcher.working_dir || '';
  if (form.launchArgs) form.launchArgs.value = launcher.launch_args || '';
  if (form.nativeUiUrl) form.nativeUiUrl.value = launcher.native_ui_url || '';
  if (form.profile && data.id) form.profile.value = data.id;
}

function renderBackendResult(role) {
  const form = getBackendForm(role);
  if (!form.result) return;
  const session = backendManagerState?.session?.[role] || {};
  const profile = getBackendProfileById(role, session.profile_id) || getActiveBackendProfile(role) || {};
  applyBackendChipState(form.cardState, session.state || 'offline');
  const details = session.details || {};
  const caps = Array.isArray(session.capabilities) && session.capabilities.length ? session.capabilities.join(' · ') : 'No capabilities confirmed yet.';
  const profileName = session.profile_name || profile.name || 'No saved profile selected';
  const url = session.base_url || profile.base_url || '—';
  const lastChecked = session.last_checked ? String(session.last_checked).replace('T', ' ').replace('Z', ' UTC') : '—';
  const latency = session.latency_ms != null ? `${session.latency_ms} ms` : '—';
  const modelCount = Array.isArray(details.models) ? details.models.length : 0;
  const extras = [];
  const launchRuntime = backendManagerState?.launcher_runtime?.[role] || {};
  if (form.launchStatus) {
    if (launchRuntime.message || launchRuntime.status) {
      const status = launchRuntime.status || 'unknown';
      const when = launchRuntime.started_at ? String(launchRuntime.started_at).replace('T', ' ').replace('Z', ' UTC') : '—';
      form.launchStatus.textContent = `${status.toUpperCase()} · ${launchRuntime.message || 'No launch message.'} · Started: ${when} · Log: ${launchRuntime.log_path || '—'}`;
    } else {
      form.launchStatus.textContent = 'Launcher not used yet.';
    }
  }
  if (modelCount) extras.push(`Models visible: ${modelCount}`);
  if (details.status_code) extras.push(`Status: ${details.status_code}`);
  if (details.queue_status) extras.push(`Queue: ${details.queue_status}`);
  if (details.history_status) extras.push(`History: ${details.history_status}`);
  form.result.innerHTML = `
    <div><strong>${profileName}</strong></div>
    <div class="mini-note">${session.message || 'No probe result yet.'}</div>
    <div class="mini-note" style="margin-top:8px;">URL: ${url}</div>
    <div class="mini-note">Latency: ${latency} · Last checked: ${lastChecked}</div>
    <div class="mini-note">Capabilities: ${caps}</div>
    ${extras.length ? `<div class="mini-note">${extras.join(' · ')}</div>` : ''}
  `;
  if (form.status && !form.status.textContent.trim()) {
    setStatus(form.status.id, session.message || '', session.connected ? 'success' : (session.state === 'error' ? 'error' : ''));
  }
  if (role === 'text' && Array.isArray(details.models) && details.models.length && $('model-select')) {
    const sel = $('model-select');
    const current = sel.value;
    sel.innerHTML = '';
    details.models.forEach(model => {
      const opt = document.createElement('option');
      opt.value = model;
      opt.textContent = model;
      if (model === current) opt.selected = true;
      sel.appendChild(opt);
    });
    if (!sel.value && details.models[0]) sel.value = details.models[0];
  }
}

function renderBackendSummary() {
  const summaryText = `Text: ${backendStateLabel(backendManagerState?.session?.text?.state)} · Image: ${backendStateLabel(backendManagerState?.session?.image?.state)} · Video: ${backendStateLabel(backendManagerState?.session?.video?.state)} · Low VRAM mode: ${!!backendManagerState?.settings?.settings?.low_vram_mode ? 'on' : 'off'}`;
  ['backend-manager-summary', 'admin-backend-summary'].forEach(id => {
    const summary = $(id);
    if (summary) summary.textContent = summaryText;
  });
  if ($('backend-low-vram-toggle')) $('backend-low-vram-toggle').checked = !!backendManagerState?.settings?.settings?.low_vram_mode;
}

function renderSurfaceBackendStrips() {
  Object.entries(surfaceBackendBindings).forEach(([surfaceId, binding]) => {
    const role = resolveSurfaceBindingRole(surfaceId, binding);
    const roleLabel = binding.roleLabel || backendRoleLabel(role);
    const session = backendManagerState?.session?.[role] || {};
    const state = String(session.state || 'offline').toLowerCase();
    const profile = getActiveBackendProfile(role) || {};
    const hasProfile = !!((profile.id || profile.profile_id) && profile.base_url);
    applyBackendChipState($(binding.stateId), state);
    const nameEl = $(binding.nameId);
    const metaEl = $(binding.metaId);
    const launchBtn = $(binding.launchId);
    const connectBtn = $(binding.connectId);
    const disconnectBtn = $(binding.disconnectId);
    const container = binding.containerId ? $(binding.containerId) : null;
    if (nameEl) {
      const backendName = session.profile_name || profile.name || `${roleLabel} backend`;
      const backendType = session.backend_type || profile.backend_type || profile.adapter || '';
      nameEl.textContent = session.connected ? `${backendName}${backendType ? ' · ' + backendType : ''}` : `No active ${role} backend`;
    }
    if (metaEl) {
      const bits = [];
      if (session.connected) {
        if (session.base_url) bits.push(session.base_url);
        if (session.latency_ms != null) bits.push(`${session.latency_ms} ms`);
        if (Array.isArray(session.capabilities) && session.capabilities.length) bits.push(session.capabilities.join(' · '));
      }
      if (bits.length) {
        metaEl.textContent = bits.join(' · ');
      } else if (binding.metaId === 'surface-backend-video-meta') {
        metaEl.textContent = 'Video now keeps a separate role-based backend lane. It can still target the same adapter family as Image without sharing the same contract owner.';
      } else if (binding.metaId === 'surface-backend-voice-meta') {
        metaEl.textContent = 'Voice stays at skeleton level for now. Use this adapter card to decide the future TTS backend without wiring the whole surface yet.';
      } else if (binding.metaId === 'surface-backend-audio-meta') {
        metaEl.textContent = 'Music / SFX stays at skeleton level for now. Pick the future audio backend here so the surface contract stays clear.';
      } else if (role === 'image') {
        metaEl.textContent = 'Generation stays usable locally. Connect an Image Backend only when you want to queue or run jobs.';
      } else if (binding.metaId === 'roleplay-text-backend-note-body') {
        metaEl.textContent = 'Connect a Text Backend to start scenes, continue turns, and run in-character replies. Setup notes and transcript drafting still work offline.';
      } else if (binding.metaId === 'assistant-text-backend-note-body') {
        metaEl.textContent = 'Connect a Text Backend to send live assistant messages. Profile setup, thread management, and saved drafts still stay usable locally.';
      } else {
        metaEl.textContent = 'Prompt, caption, and batch AI actions unlock after a Text Backend is connected. Local saves and library browsing still work offline.';
      }
    }
    if (launchBtn) {
      const launchRuntime = backendManagerState?.launcher_runtime?.[role] || {};
      const launchStatus = String(launchRuntime.status || 'unknown').toLowerCase();
      const launcher = profile.launcher || {};
      const hasLaunchTarget = !!String(launcher.backend_path || '').trim();
      const verifiedRunning = !!session.connected || launchRuntime.verified_running === true || launchRuntime.tracked_process_alive === true;
      const backendLooksLive = verifiedRunning || launchStatus === 'launching';
      launchBtn.disabled = backendLooksLive;
      launchBtn.textContent = launchStatus === 'launching'
        ? 'Launching...'
        : (verifiedRunning ? 'Backend Running' : (hasLaunchTarget ? 'Launch Backend' : 'Set launch path'));
      launchBtn.title = launchStatus === 'launching'
        ? 'Backend launch is in progress. Refresh after the backend finishes starting.'
        : (verifiedRunning
          ? 'Neo has proof this backend is alive from a connected session or a tracked launch process.'
          : (hasLaunchTarget ? `Launch active  backend profile` : `Add a  backend launch path in Admin first.`));
    }
    if (connectBtn) {
      connectBtn.textContent = session.connected
        ? `Refresh ${roleLabel} Backend`
        : (hasProfile ? `Connect ${roleLabel} Backend` : `Set up ${roleLabel} Backend`);
    }
    if (disconnectBtn) disconnectBtn.disabled = !session.connected;
    if (container) {
      container.classList.toggle('connected', !!session.connected);
      container.classList.toggle('offline', !session.connected);
    }
  });
}

function renderBackendManagerState() {
  if (!backendManagerState) return;
  renderBackendSummary();
  renderSurfaceBackendStrips();
  managedBackendRoles().forEach(role => {
    const activeId = backendManagerState?.active_profile_ids?.[role] || '';
    if (!isBackendRoleEditing(role)) {
      fillBackendProfileSelect(role, activeId);
      applyBackendProfileToForm(role, getBackendProfileById(role, activeId) || getActiveBackendProfile(role));
    }
    renderBackendResult(role);
  });
  document.dispatchEvent(new CustomEvent('neo-backend-state', { detail: backendManagerState }));
}

function getBackendRoleState(role) {
  return backendManagerState?.session?.[role] || { state:'offline', connected:false };
}

function isBackendRoleConnected(role) {
  return !!getBackendRoleState(role).connected;
}

window.getBackendManagerState = () => backendManagerState;
window.getBackendRoleState = getBackendRoleState;
window.isBackendRoleConnected = isBackendRoleConnected;
window.openBackendManager = openBackendManager;
window.fetchBackendManagerState = fetchBackendManagerState;
window.quickConnectBackendRole = quickConnectBackendRole;
window.quickDisconnectBackendRole = quickDisconnectBackendRole;

async function fetchBackendManagerState(options={}) {
  const force = !!options.force;
  if (force) clearBackendManagerCache();
  const cached = !force && window.NeoGenerationPerf?.readCache ? window.NeoGenerationPerf.readCache('backend-manager-state', 5000) : null;
  if (cached) {
    backendManagerState = cached;
    renderBackendManagerState();
    if (!options.silent) ['backend-text-status','backend-image-status','backend-voice-status','backend-audio-status'].forEach(id => setStatus(id, '', ''));
    return cached;
  }
  try {
    const data = await safeFetchJson('/api/backend-manager/state');
    rememberBackendManagerState(data);
    renderBackendManagerState();
    if (!options.silent) ['backend-text-status','backend-image-status','backend-voice-status','backend-audio-status'].forEach(id => setStatus(id, '', ''));
    return data;
  } catch (err) {
    if (!options.silent) {
      ['backend-text-status','backend-image-status','backend-voice-status','backend-audio-status'].forEach(id => setStatus(id, err.message || 'Failed to load backend state.', 'error'));
    }
    throw err;
  }
}

function openBackendManager(role='') {
  if (typeof switchMainTab === 'function') switchMainTab('admin');
  else document.querySelector('[data-main-tab="admin"]')?.click();
  window.requestAnimationFrame(() => {
    const target = role ? document.querySelector(`#admin-backend-card-${role}`) || document.querySelector(`[data-backend-role="${role}"]`) : $('tab-admin');
    target?.scrollIntoView({ behavior:'smooth', block:'start' });
  });
  fetchBackendManagerState({ silent:true, force:true }).catch(() => {});
}

function closeBackendManager() {
  // Backend controls now live in the Admin surface.
}

function openBackendChoice(message) {
  const modal = $('backend-choice-modal');
  if (!modal) return Promise.resolve('keep');
  $('backend-choice-message').textContent = message || 'Choose how to continue.';
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
  return new Promise(resolve => { backendChoiceResolver = resolve; });
}

function closeBackendChoice(choice='cancel') {
  const modal = $('backend-choice-modal');
  if (modal) modal.classList.add('hidden');
  if (!$('backend-manager-modal') || $('backend-manager-modal').classList.contains('hidden')) document.body.classList.remove('modal-open');
  if (backendChoiceResolver) {
    backendChoiceResolver(choice);
    backendChoiceResolver = null;
  }
}

async function saveBackendManagerSettings() {
  try {
    const data = await safeFetchJson('/api/backend-manager/settings-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ low_vram_mode: !!$('backend-low-vram-toggle')?.checked }),
    });
    rememberBackendManagerState(data);
    renderBackendManagerState();
  } catch (err) {
    setStatus('backend-text-status', err.message || 'Failed to save backend settings.', 'error');
    setStatus('backend-image-status', err.message || 'Failed to save backend settings.', 'error');
  }
}

function buildBackendProfilePayload(role) {
  const form = getBackendForm(role);
  return {
    role,
    profile_id: form.profile?.value || '',
    id: form.profile?.value || '',
    backend_type: form.type?.value || ({ image:'comfyui', voice:'kokoro', audio:'stable_audio' }[role] || 'koboldcpp'),
    name: trim(form.name?.value),
    base_url: trim(form.url?.value),
    timeout_sec: Number(form.timeout?.value || ({ image:12, voice:20, audio:30 }[role] || 8)),
    auto_reconnect: !!form.autoReconnect?.checked,
    launcher: {
      launch_type: trim(form.launchType?.value || 'bat'),
      backend_path: trim(form.launchPath?.value),
      working_dir: trim(form.launchCwd?.value),
      launch_args: trim(form.launchArgs?.value),
      native_ui_url: trim(form.nativeUiUrl?.value),
      enabled: true,
    },
  };
}

async function persistActiveBackendProfile(role, profileId) {
  const data = await safeFetchJson('/api/backend-manager/profile-select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, profile_id: profileId }),
  });
  rememberBackendManagerState(data);
  renderBackendManagerState();
  return data;
}

async function connectBackendProfile(role, profileId, statusId='') {
  const otherRole = null;
  const lowVram = !!backendManagerState?.settings?.settings?.low_vram_mode;
  const otherSession = backendManagerState?.session?.[otherRole] || {};
  if (otherRole && lowVram && otherSession.connected) {
    const choice = await openBackendChoice(`${backendRoleLabel(otherRole)} backend is already connected. Disconnect it before connecting ${backendRoleLabel(role).toLowerCase()} backend?`);
    if (choice === 'cancel') {
      if (statusId) setStatus(statusId, 'Connect cancelled.', '');
      return null;
    }
    if (choice === 'disconnect') {
      await safeFetchJson('/api/backend-manager/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: otherRole }),
      });
      await fetchBackendManagerState({ silent:true });
    }
  }
  const data = await safeFetchJson('/api/backend-manager/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, profile_id: profileId }),
  });
  rememberBackendManagerState(data);
  renderBackendManagerState();
  if (statusId) setStatus(statusId, data.message || 'Connected.', data.success ? 'success' : 'error');
  return data;
}

async function refreshBackendRole(role, statusId='') {
  const data = await safeFetchJson('/api/backend-manager/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
  rememberBackendManagerState(data);
  renderBackendManagerState();
  if (statusId) setStatus(statusId, data.message || 'Refreshed.', data.success ? 'success' : 'error');
  return data;
}

async function quickConnectBackendRole(role) {
  if (!backendManagerState) await fetchBackendManagerState({ silent:true });
  const session = backendManagerState?.session?.[role] || {};
  if (session.connected) {
    await refreshBackendRole(role);
    return;
  }
  const profileId = backendManagerState?.active_profile_ids?.[role] || getActiveBackendProfile(role)?.id || '';
  const profile = getBackendProfileById(role, profileId) || getActiveBackendProfile(role);
  if (!profileId || !profile || !profile.base_url) {
    openBackendManager(role);
    return;
  }
  await connectBackendProfile(role, profileId);
}



async function quickLaunchBackendRole(role) {
  // Always fetch fresh state before launching from a surface. The Admin launcher form may
  // have just saved a path, and cached state can make the surface button think it is empty.
  await fetchBackendManagerState({ silent:true, force:true });
  const profileId = backendManagerState?.active_profile_ids?.[role] || getActiveBackendProfile(role)?.id || '';
  const profile = getBackendProfileById(role, profileId) || getActiveBackendProfile(role);
  const launcher = profile?.launcher || {};
  const hasLaunchTarget = !!String(launcher.backend_path || '').trim();
  if (!profileId || !profile || !hasLaunchTarget) {
    openBackendManager(role);
    const form = getBackendForm(role);
    if (form.status) setStatus(form.status.id, `Add and save a ${backendRoleLabel(role)} backend launch path first.`, 'error');
    return;
  }
  const data = await safeFetchJson('/api/backend-manager/launch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, profile_id: profileId }),
  });
  rememberBackendManagerState(data);
  renderBackendManagerState();
}

window.quickLaunchBackendRole = quickLaunchBackendRole;

async function quickDisconnectBackendRole(role) {
  if (!backendManagerState) await fetchBackendManagerState({ silent:true });
  const session = backendManagerState?.session?.[role] || {};
  if (!session.connected) return;
  const data = await safeFetchJson('/api/backend-manager/disconnect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
  rememberBackendManagerState(data);
  renderBackendManagerState();
}

async function handleBackendAction(role, action) {
  const form = getBackendForm(role);
  if (!form.status) return;
  if (action === 'new') {
    form.profile.value = '';
    form.name.value = ({ image:'ComfyUI Local', voice:'Kokoro Local', audio:'Stable Audio Local' }[role] || 'KoboldCpp Local');
    form.url.value = ({ image:'http://127.0.0.1:8188', voice:'', audio:'' }[role] ?? 'http://127.0.0.1:5001');
    form.timeout.value = ({ image:12, voice:20, audio:30 }[role] || 8);
    form.autoReconnect.checked = false;
    if (form.launchType) form.launchType.value = 'bat';
    if (form.launchPath) form.launchPath.value = '';
    if (form.launchCwd) form.launchCwd.value = '';
    if (form.launchArgs) form.launchArgs.value = '';
    if (form.nativeUiUrl) form.nativeUiUrl.value = '';
    if (form.launchStatus) form.launchStatus.textContent = 'Launcher not used yet.';
    setStatus(form.status.id, 'Editing a new unsaved profile.');
    return;
  }
  try {
    if (action === 'save') {
      const payload = buildBackendProfilePayload(role);
      const data = await safeFetchJson('/api/backend-manager/profile-save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      rememberBackendManagerState(data);
      clearBackendRoleEditing(role);
      renderBackendManagerState();
      setStatus(form.status.id, data.message || 'Profile saved.', 'success');
      return;
    }
    if (action === 'delete') {
      const profileId = form.profile?.value || '';
      if (!profileId) throw new Error('Pick a saved profile to delete.');
      const data = await safeFetchJson('/api/backend-manager/profile-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, profile_id: profileId }),
      });
      rememberBackendManagerState(data);
      renderBackendManagerState();
      setStatus(form.status.id, data.message || 'Profile deleted.', 'success');
      return;
    }
    if (action === 'test') {
      const payload = buildBackendProfilePayload(role);
      const data = await safeFetchJson('/api/backend-manager/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = data.result || {};
      setStatus(form.status.id, result.message || 'Probe finished.', result.ok ? 'success' : 'error');
      form.result.innerHTML = `
        <div><strong>${payload.name || '(unsaved profile)'}</strong></div>
        <div class="mini-note">${result.message || 'No result returned.'}</div>
        <div class="mini-note" style="margin-top:8px;">URL: ${result.base_url || payload.base_url || '—'}</div>
        <div class="mini-note">Latency: ${result.latency_ms != null ? result.latency_ms + ' ms' : '—'}</div>
        <div class="mini-note">Capabilities: ${Array.isArray(result.capabilities) && result.capabilities.length ? result.capabilities.join(' · ') : 'No capabilities confirmed yet.'}</div>
      `;
      return;
    }
    if (action === 'launch') {
      // Always save the visible profile + launcher fields first.
      // This prevents launcher paths from disappearing after state refresh and makes Start Backend work without pressing Save separately.
      const saved = await safeFetchJson('/api/backend-manager/profile-save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBackendProfilePayload(role)),
      });
      rememberBackendManagerState(saved);
      clearBackendRoleEditing(role);
      const profileId = saved.profile?.id || saved.profile?.profile_id || backendManagerState?.active_profile_ids?.[role] || form.profile?.value || '';
      renderBackendManagerState();
      const data = await safeFetchJson('/api/backend-manager/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, profile_id: profileId }),
      });
      rememberBackendManagerState(data);
      renderBackendManagerState();
      setStatus(form.status.id, data.message || 'Backend launch requested.', 'success');
      return;
    }
    if (action === 'open-ui') {
      const saved = await safeFetchJson('/api/backend-manager/profile-save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBackendProfilePayload(role)),
      });
      rememberBackendManagerState(saved);
      clearBackendRoleEditing(role);
      const profileId = saved.profile?.id || saved.profile?.profile_id || backendManagerState?.active_profile_ids?.[role] || form.profile?.value || '';
      renderBackendManagerState();
      const data = await safeFetchJson('/api/backend-manager/open-native-ui', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, profile_id: profileId }),
      });
      setStatus(form.status.id, data.message || 'Native UI opened in browser only.', 'success');
      return;
    }
    if (action === 'view-launch-log') {
      const data = await safeFetchJson('/api/backend-manager/launch-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, profile_id: form.profile?.value || '' }),
      });
      if (form.result) {
        form.result.innerHTML = `<div><strong>Launcher log</strong></div><div class="mini-note">${data.log_path || '—'}</div><pre style="white-space:pre-wrap;max-height:260px;overflow:auto;margin-top:8px;"></pre>`;
        const pre = form.result.querySelector('pre');
        if (pre) pre.textContent = data.log || 'No launch log yet.';
      }
      setStatus(form.status.id, 'Launch log loaded.', 'success');
      return;
    }
    if (action === 'connect') {
      let profileId = form.profile?.value || '';
      if (!profileId) {
        const saved = await safeFetchJson('/api/backend-manager/profile-save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildBackendProfilePayload(role)),
        });
        rememberBackendManagerState(saved);
        renderBackendManagerState();
        profileId = saved.profile?.id || backendManagerState?.active_profile_ids?.[role] || '';
      } else {
        await persistActiveBackendProfile(role, profileId);
      }
      await connectBackendProfile(role, profileId, form.status.id);
      return;
    }
    if (action === 'disconnect') {
      const data = await safeFetchJson('/api/backend-manager/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      rememberBackendManagerState(data);
      renderBackendManagerState();
      setStatus(form.status.id, data.message || 'Disconnected.', 'success');
      return;
    }
    if (action === 'refresh') {
      await refreshBackendRole(role, form.status.id);
    }
  } catch (err) {
    setStatus(form.status.id, err.message || 'Backend action failed.', 'error');
  }
}

function bindBackendManagerEvents() {
  $('backend-choice-modal')?.addEventListener('click', e => { if (e.target.id === 'backend-choice-modal') closeBackendChoice('cancel'); });
  $('btn-backend-choice-disconnect')?.addEventListener('click', () => closeBackendChoice('disconnect'));
  $('btn-backend-choice-keep')?.addEventListener('click', () => closeBackendChoice('keep'));
  $('btn-backend-choice-cancel')?.addEventListener('click', () => closeBackendChoice('cancel'));
  $('btn-refresh-backend-state')?.addEventListener('click', () => fetchBackendManagerState({ force:true }).catch(() => {}));
  $('backend-low-vram-toggle')?.addEventListener('change', saveBackendManagerSettings);
  $('btn-prompt-note-manage-backend')?.addEventListener('click', () => openBackendManager('text'));
  $('btn-caption-note-manage-backend')?.addEventListener('click', () => openBackendManager('text'));
  $('btn-batch-note-manage-backend')?.addEventListener('click', () => openBackendManager('text'));
  Object.entries(surfaceBackendBindings).forEach(([surfaceId, binding]) => {
    const resolve = () => resolveSurfaceBindingRole(surfaceId, binding);
    $(binding.manageId)?.addEventListener('click', () => openBackendManager(resolve()));
    $(binding.launchId)?.addEventListener('click', () => { quickLaunchBackendRole(resolve()).catch(err => console.error(err)); });
    $(binding.connectId)?.addEventListener('click', () => { quickConnectBackendRole(resolve()).catch(err => console.error(err)); });
    $(binding.disconnectId)?.addEventListener('click', () => { quickDisconnectBackendRole(resolve()).catch(err => console.error(err)); });
  });
  managedBackendRoles().forEach(role => {
    const form = getBackendForm(role);
    [form.name, form.url, form.timeout, form.launchType, form.launchPath, form.launchCwd, form.launchArgs, form.nativeUiUrl].filter(Boolean).forEach(input => {
      input.addEventListener('focus', () => markBackendRoleEditing(role));
      input.addEventListener('input', () => markBackendRoleEditing(role));
      input.addEventListener('change', () => markBackendRoleEditing(role));
      input.addEventListener('blur', () => {
        backendEditLockUntil[role] = Date.now() + 5000;
      });
    });
    form.profile?.addEventListener('change', async e => {
      const profileId = e.target.value || '';
      if (!profileId) return;
      try {
        clearBackendRoleEditing(role);
        await persistActiveBackendProfile(role, profileId);
        applyBackendProfileToForm(role, getBackendProfileById(role, profileId));
        setStatus(form.status.id, `${backendRoleLabel(role)} profile selected.`);
      } catch (err) {
        setStatus(form.status.id, err.message || 'Could not switch profile.', 'error');
      }
    });
    document.querySelectorAll(`[data-backend-role="${role}"][data-backend-action], [data-backend-action][data-backend-role="${role}"]`).forEach(btn => {
      btn.addEventListener('click', () => handleBackendAction(role, btn.dataset.backendAction));
    });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (!$('backend-choice-modal')?.classList.contains('hidden')) closeBackendChoice('cancel');
    }
  });
}

function initializeBackendManager() {
  bindBackendManagerEvents();
  fetchBackendManagerState({ silent:true, force:true }).catch(() => {});
  if (backendStatusPollHandle) clearInterval(backendStatusPollHandle);
  backendStatusPollHandle = setInterval(() => {
    fetchBackendManagerState({ silent:true, force:true }).catch(() => {});
  }, 15000);
}
