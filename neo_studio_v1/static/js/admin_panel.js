let adminPanelLoaded = false;
let adminCurrentSection = 'system';
const NEO_EXTENSION_PERMISSION_META = {
  filesystem_read: { label: 'Filesystem read', risk: 'medium', note: 'Can inspect local files/folders allowed by the extension.' },
  filesystem_write: { label: 'Filesystem write', risk: 'high', note: 'Can create or modify local files.' },
  network: { label: 'Network access', risk: 'medium', note: 'Can call local or remote network resources.' },
  provider_access: { label: 'Provider access', risk: 'medium', note: 'Can use configured provider/backends.' },
  comfy_access: { label: 'Comfy access', risk: 'medium', note: 'Can interact with Comfy-related workflows or APIs.' },
  task_create: { label: 'Task creation', risk: 'medium', note: 'Can create Neo runtime tasks.' },
  frontend_hooks: { label: 'Frontend hooks', risk: 'low', note: 'Can add panels/buttons/sidebar items through Neo hooks.' },
  frontend_injection: { label: 'Frontend injection', risk: 'medium', note: 'Can load extension frontend scripts/styles.' },
  backend_routes: { label: 'Backend routes', risk: 'high', note: 'Can expose extension API routes under Neo.' },
  settings_read: { label: 'Settings read', risk: 'medium', note: 'Can read Neo settings.' },
  settings_write: { label: 'Settings write', risk: 'high', note: 'Can modify Neo settings.' },
  models_read: { label: 'Models read', risk: 'low', note: 'Can inspect model lists/metadata.' },
  models_write: { label: 'Models write', risk: 'high', note: 'Can modify model-related files or metadata.' },
  logs_read: { label: 'Logs read', risk: 'low', note: 'Can read extension/runtime logs.' },
  logs_write: { label: 'Logs write', risk: 'low', note: 'Can write extension/runtime logs.' },
};


const NEO_EXTENSION_DEPENDENCY_LABELS = {
  python: 'Python packages',
  npm: 'NPM packages',
  neo_extensions: 'Neo extensions',
  providers: 'Providers / backends',
  comfy_nodes: 'Comfy nodes',
  models: 'Models',
  external_apps: 'External apps',
  notes: 'Notes',
};

function normalizeExtensionDependencyNotes(match) {
  const source = (match && typeof match.dependency_notes === 'object' && match.dependency_notes)
    ? match.dependency_notes
    : ((match && typeof match.dependencies === 'object' && !Array.isArray(match.dependencies)) ? match.dependencies : {});
  const out = {};
  Object.keys(NEO_EXTENSION_DEPENDENCY_LABELS).forEach(key => {
    const value = source ? source[key] : [];
    out[key] = Array.isArray(value) ? value.filter(Boolean).map(String) : (value ? [String(value)] : []);
  });
  return out;
}

function renderExtensionDependencyDisplay(match) {
  const box = $('admin-extension-dependency-display');
  const list = $('admin-extension-dependency-list');
  const summary = $('admin-extension-dependency-summary');
  if (!box || !list || !summary) return;
  box.style.display = match ? '' : 'none';
  list.innerHTML = '';
  if (!match) {
    summary.textContent = 'Select an extension to review dependency notes.';
    return;
  }
  const notes = normalizeExtensionDependencyNotes(match);
  const total = Object.values(notes).reduce((sum, arr) => sum + arr.length, 0);
  if (!total) {
    summary.textContent = 'No dependency notes declared.';
    list.innerHTML = '<div class="mini-note">This extension does not declare Python packages, nodes, models, providers, or external apps.</div>';
    return;
  }
  summary.textContent = String(total) + ' dependency note' + (total === 1 ? '' : 's') + ' declared · display-only, no auto-install yet.';
  Object.keys(NEO_EXTENSION_DEPENDENCY_LABELS).forEach(key => {
    const items = notes[key] || [];
    if (!items.length) return;
    const group = document.createElement('div');
    group.className = 'dependency-group';
    const chips = items.map(item => '<span class="dependency-chip">' + escapeHtml(item) + '</span>').join('');
    group.innerHTML = '<div class="dependency-group-title">' + escapeHtml(NEO_EXTENSION_DEPENDENCY_LABELS[key]) + '</div>' +
      '<div class="dependency-chip-row">' + chips + '</div>';
    list.appendChild(group);
  });
}

function neoExtensionPermissionMeta(key) {
  const clean = String(key || '').trim();
  return NEO_EXTENSION_PERMISSION_META[clean] || { label: clean || 'Unknown permission', risk: 'custom', note: 'Custom permission declared by this extension.' };
}

function neoExtensionPermissionRiskRank(risk) {
  return ({ high: 3, medium: 2, low: 1, custom: 1 })[String(risk || '').toLowerCase()] || 0;
}

function renderExtensionPermissionDisplay(match) {
  const box = $('admin-extension-permission-display');
  const list = $('admin-extension-permission-list');
  const summary = $('admin-extension-permission-summary');
  if (!box || !list || !summary) return;
  const permissions = Array.isArray(match?.permissions) ? match.permissions.filter(Boolean) : [];
  box.style.display = match ? '' : 'none';
  list.innerHTML = '';
  if (!match) {
    summary.textContent = 'Select an extension to review permissions.';
    return;
  }
  if (!permissions.length) {
    summary.textContent = 'No permissions declared. Treat old/legacy extensions with caution until their manifest is updated.';
    list.innerHTML = '<div class="mini-note">This extension did not declare any permissions.</div>';
    return;
  }
  const metas = permissions.map(key => ({ key, ...neoExtensionPermissionMeta(key) }))
    .sort((a, b) => neoExtensionPermissionRiskRank(b.risk) - neoExtensionPermissionRiskRank(a.risk) || String(a.key).localeCompare(String(b.key)));
  const high = metas.filter(item => item.risk === 'high').length;
  const medium = metas.filter(item => item.risk === 'medium').length;
  const custom = metas.filter(item => item.risk === 'custom').length;
  summary.textContent = String(permissions.length) + ' permission' + (permissions.length === 1 ? '' : 's') + ' declared · ' + String(high) + ' high risk · ' + String(medium) + ' medium risk' + (custom ? ' · ' + String(custom) + ' custom' : '');
  metas.forEach(item => {
    const row = document.createElement('div');
    row.className = 'permission-row permission-risk-' + (item.risk || 'custom');
    row.innerHTML = '<div class="permission-main">' +
      '<span class="permission-key">' + escapeHtml(item.label || item.key) + '</span>' +
      '<span class="permission-code">' + escapeHtml(item.key) + '</span>' +
      '</div>' +
      '<span class="permission-risk">' + escapeHtml(String(item.risk || 'custom').toUpperCase()) + '</span>' +
      '<div class="permission-note">' + escapeHtml(item.note || '') + '</div>';
    list.appendChild(row);
  });
}


function adminRenderExtensionRegistry(data) {
  const counts = (data && typeof data.counts === 'object' && data.counts) ? data.counts : {};
  const ext = Array.isArray(data?.extension_packs) ? data.extension_packs : [];
  const workflows = Array.isArray(data?.workflow_packs) ? data.workflow_packs : [];
  if ($('admin-extension-summary')) {
    $('admin-extension-summary').textContent = `${Number(counts.enabled_extension_packs ?? counts.extensions_enabled ?? 0)} / ${Number(counts.extension_packs ?? counts.extensions_total ?? 0)} extension packs enabled · ${Number(counts.enabled_workflow_packs ?? 0)} / ${Number(counts.workflow_packs ?? counts.workflow_packs_total ?? 0)} workflow packs enabled`;
  }
  const select = $('admin-extension-pack-select');
  if (select) {
    const current = String(select.value || '');
    select.innerHTML = '<option value="">Select an extension pack…</option>';
    ext.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.extension_id || '';
      opt.textContent = `${item.title || item.extension_id}${item.enabled ? '' : ' · disabled'}`;
      if (current && current === opt.value) opt.selected = true;
      select.appendChild(opt);
    });
  }
  window.neoExtensionRegistryCache = { extension_packs: ext, workflow_packs: workflows, counts };
  adminRenderSelectedExtensionPack();
}

function adminRenderSelectedExtensionPack() {
  const select = $('admin-extension-pack-select');
  const details = $('admin-extension-pack-details');
  const toggle = $('btn-admin-extension-toggle');
  const cache = window.neoExtensionRegistryCache || { extension_packs: [], workflow_packs: [] };
  const extensionId = String(select?.value || '');
  const match = (cache.extension_packs || []).find(item => String(item.extension_id || '') === extensionId);
  if (!details) return;
  const actionButtons = [
    'btn-admin-extension-toggle',
    'btn-admin-extension-update',
    'btn-admin-extension-repair',
    'btn-admin-extension-open-folder',
    'btn-admin-extension-view-manifest',
    'btn-admin-extension-view-log',
    'btn-admin-extension-remove',
  ].map(id => $(id)).filter(Boolean);
  if (!match) {
    details.textContent = 'Pick an extension pack to inspect its injected sections, actions, guides, and backend requirements.';
    actionButtons.forEach(btn => btn.setAttribute('disabled', 'disabled'));
    renderExtensionPermissionDisplay(null);
    renderExtensionDependencyDisplay(null);
    return;
  }
  actionButtons.forEach(btn => btn.removeAttribute('disabled'));
  if (toggle) {
    toggle.textContent = match.enabled ? 'Disable Pack' : 'Enable Pack';
  }
  renderExtensionPermissionDisplay(match);
  renderExtensionDependencyDisplay(match);
  const related = (cache.workflow_packs || []).filter(item => (item.requires_extensions || []).includes(match.extension_id));
  const relatedWorkflowLines = related.map(item => {
    const path = item.workflow_path ? ' @ ' + item.workflow_path : '';
    const backend = item.backend_role ? ' [' + item.backend_role + ']' : '';
    return (item.title || item.workflow_id || 'workflow') + backend + path;
  });
  details.textContent = [
    `ID: ${match.extension_id || '—'}`,
    `Surface: ${match.surface || '—'}`,
    `Target surface: ${match.target_surface || '—'}`,
    `Workspace: ${match.workspace || match.target_subtab || match.target_tab || '—'}`,
    `Allowed families: ${(match.allowed_families || match.families || []).join(', ') || '—'}`,
    `Blocked families: ${(match.blocked_families || match.disabled_families || []).join(', ') || '—'}`,
    `Families: ${(match.families || []).join(', ') || '—'}`,
    `Backends: ${(match.requires_backends || []).join(', ') || '—'}`,
    `Nodes: ${(match.requires_nodes || match.required_nodes || []).join(', ') || '—'}`,
    `UI entry: ${match.ui_entry || '—'}`,
    `Adapter: ${match.adapter || match.adapter_path || '—'}`,
    `Mount type: ${match.mount_type || '—'}`,
    `Author: ${match.author || '—'}`,
    `Permissions: ${(match.permissions || []).join(', ') || '—'}`,
    `Dependency notes: ${JSON.stringify(normalizeExtensionDependencyNotes(match))}`,
    `Backend routes: ${match.backend_routes || '—'}`,
    `CSS entry: ${match.entry_css || '—'}`,
    `Manifest: ${match.manifest_path || '—'}`,
    `Manifest warnings: ${(match.manifest_warnings || []).join(', ') || '—'}`,
    `Injected sections: ${(match.injects_sections || []).join(', ') || '—'}`,
    `Injected actions: ${(match.injects_actions || []).join(', ') || '—'}`,
    `Injected guides: ${(match.injects_guides || []).join(', ') || '—'}`,
    `Related workflow packs: ${relatedWorkflowLines.join('; ') || '—'}`,
    `Workflow import count: ${related.length}`,
    `Enabled: ${match.enabled ? 'yes' : 'no'}`,
  ].join('\n');
}

async function adminShowManifestStandard() {
  const box = $('admin-extension-manifest-standard');
  if (!box) return;
  box.style.display = '';
  box.textContent = 'Loading manifest standard…';
  const data = await safeFetchJson(`/api/extensions/manifest-standard?_=${Date.now()}`, { cache:'no-store' });
  const template = data?.template || {};
  box.textContent = [
    'Required manifest filename: ' + (data?.filename || 'neo_extension.json'),
    'Legacy filename still read: ' + (data?.legacy_filename || 'manifest.json'),
    '',
    'Template:',
    JSON.stringify(template, null, 2),
  ].join('\n');
}

async function adminLoadExtensionRegistry(force=false) {
  if (!force && window.neoExtensionRegistryCache) {
    adminRenderExtensionRegistry(window.neoExtensionRegistryCache);
    return;
  }
  const data = await safeFetchJson(`/api/extensions/registry?surface=&_=${Date.now()}`, { cache:'no-store' });
  adminRenderExtensionRegistry(data || {});
}

async function adminToggleSelectedExtensionPack() {
  const select = $('admin-extension-pack-select');
  const cache = window.neoExtensionRegistryCache || { extension_packs: [] };
  const extensionId = String(select?.value || '');
  const match = (cache.extension_packs || []).find(item => String(item.extension_id || '') === extensionId);
  if (!match) return;
  await safeFetchJson('/api/extensions/packs/toggle', {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ extension_id: extensionId, enabled: !match.enabled }),
  });
  await adminLoadExtensionRegistry(true);
}


function adminSelectedExtensionId() {
  return String($('admin-extension-pack-select')?.value || '').trim();
}

function adminSetExtensionActionStatus(message, type='') {
  setStatus('admin-extension-action-status', message || '', type || '');
}

async function adminExtensionPost(url, payload) {
  const data = await safeFetchJson(url, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify(payload || {}),
  });
  await adminLoadExtensionRegistry(true);
  if (data?.log_path) adminSetExtensionActionStatus(`Done. Log: ${data.log_path}`, 'ok');
  else adminSetExtensionActionStatus('Done.', 'ok');
  return data;
}

async function adminInstallExtensionGit() {
  const gitUrl = String($('admin-extension-git-url')?.value || '').trim();
  const branch = String($('admin-extension-git-branch')?.value || '').trim();
  const overwrite = !!$('admin-extension-overwrite')?.checked;
  if (!gitUrl) {
    adminSetExtensionActionStatus('Paste a Git URL first.', 'error');
    return;
  }
  adminSetExtensionActionStatus('Installing extension from Git…', '');
  await adminExtensionPost('/api/extensions/install/git', { git_url: gitUrl, branch, overwrite, enable: true });
}

async function adminInstallExtensionZip() {
  const input = $('admin-extension-zip-file');
  const file = input?.files?.[0];
  if (!file) {
    adminSetExtensionActionStatus('Choose a ZIP file first.', 'error');
    return;
  }
  const form = new FormData();
  form.append('file', file);
  form.append('overwrite', $('admin-extension-overwrite')?.checked ? 'true' : 'false');
  form.append('enable', 'true');
  adminSetExtensionActionStatus('Installing extension ZIP…', '');
  const data = await safeFetchJson('/api/extensions/install/zip', { method:'POST', body: form });
  await adminLoadExtensionRegistry(true);
  adminSetExtensionActionStatus(data?.log_path ? `Installed. Log: ${data.log_path}` : 'Installed.', 'ok');
}

async function adminUpdateSelectedExtension() {
  const extensionId = adminSelectedExtensionId();
  if (!extensionId) return;
  adminSetExtensionActionStatus('Updating extension…', '');
  await adminExtensionPost('/api/extensions/update', { extension_id: extensionId });
}

async function adminRepairSelectedExtension() {
  const extensionId = adminSelectedExtensionId();
  if (!extensionId) return;
  adminSetExtensionActionStatus('Repairing extension registry…', '');
  await adminExtensionPost('/api/extensions/repair', { extension_id: extensionId });
}

async function adminRemoveSelectedExtension() {
  const extensionId = adminSelectedExtensionId();
  if (!extensionId) return;
  const ok = window.confirm(`Remove extension "${extensionId}" from Neo extensions?`);
  if (!ok) return;
  adminSetExtensionActionStatus('Removing extension…', '');
  await adminExtensionPost('/api/extensions/remove', { extension_id: extensionId, delete_files: true });
}

async function adminOpenSelectedExtensionFolder() {
  const extensionId = adminSelectedExtensionId();
  if (!extensionId) return;
  await adminExtensionPost('/api/extensions/open-folder', { extension_id: extensionId });
}

async function adminViewSelectedExtensionManifest() {
  const extensionId = adminSelectedExtensionId();
  const box = $('admin-extension-manifest-standard');
  if (!extensionId || !box) return;
  box.style.display = '';
  box.textContent = 'Loading extension manifest…';
  const data = await safeFetchJson(`/api/extensions/manifest/${encodeURIComponent(extensionId)}?_=${Date.now()}`, { cache:'no-store' });
  box.textContent = JSON.stringify(data?.manifest || data || {}, null, 2);
}

async function adminViewSelectedExtensionLog() {
  const extensionId = adminSelectedExtensionId();
  const box = $('admin-extension-manifest-standard');
  if (!extensionId || !box) return;
  box.style.display = '';
  box.textContent = 'Loading extension log…';
  const data = await safeFetchJson(`/api/extensions/logs/${encodeURIComponent(extensionId)}?_=${Date.now()}`, { cache:'no-store' });
  box.textContent = data?.log || 'No extension log yet.';
}

function adminShowExtensionSubtab(subtab) {
  const key = String(subtab || 'extension-manager').trim().toLowerCase() || 'extension-manager';
  document.querySelectorAll('[data-admin-extension-subtab-panel]').forEach(panel => {
    panel.style.display = (panel.getAttribute('data-admin-extension-subtab-panel') === key) ? '' : 'none';
  });
  document.querySelectorAll('[data-admin-extension-subtab]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-admin-extension-subtab') === key);
  });
  if (key === 'extension-manager') {
    adminLoadExtensionRegistry(false).catch(() => {});
  } else if (key === 'node-manager' && typeof fetchNodeManagerState === 'function') {
    fetchNodeManagerState(true).catch(() => {});
  }
}

function adminDevModeEnabled() {
  return !!($('admin-setting-dev-mode')?.checked || window.NeoAppSettingsCache?.startup?.dev_mode);
}

function adminApplyDeveloperBoundary(devMode) {
  document.querySelectorAll('[data-admin-dev-only]').forEach(el => {
    el.style.display = devMode ? '' : 'none';
  });
  if (!devMode && adminCurrentSection === 'developer') {
    adminShowSection('system');
  }
  const mode = $('generation-experimental-mode');
  const slotA = $('generation-advanced-slot-a');
  const slotB = $('generation-advanced-slot-b');
  if (!devMode) {
    let changed = false;
    if (mode && mode.value !== 'off') { mode.value = 'off'; changed = true; }
    if (slotA && slotA.value !== 'none') { slotA.value = 'none'; changed = true; }
    if (slotB && slotB.value !== 'none') { slotB.value = 'none'; changed = true; }
    if (changed) {
      [mode, slotA, slotB].forEach(el => el?.dispatchEvent(new Event('change', { bubbles:true })));
    } else if (typeof window.renderGenerationExperimentalMode === 'function') {
      window.renderGenerationExperimentalMode();
    }
  } else if (typeof window.renderGenerationExperimentalMode === 'function') {
    window.renderGenerationExperimentalMode();
  }
}

function adminShowSection(section) {
  let key = String(section || 'system').trim().toLowerCase() || 'system';
  if (key === 'developer' && !adminDevModeEnabled()) key = 'system';
  adminCurrentSection = key;
  document.querySelectorAll('[data-admin-section-target]').forEach(el => {
    el.style.display = (el.getAttribute('data-admin-section-target') === key) ? '' : 'none';
  });
  document.querySelectorAll('[data-admin-section]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-admin-section') === key);
  });
}

function adminApplySettings(settings) {
  window.NeoAppSettingsCache = settings || window.NeoAppSettingsCache || {};
  document.dispatchEvent(new CustomEvent('neo-settings-updated', { detail: { settings: window.NeoAppSettingsCache } }));
  const startup = (settings && typeof settings.startup === 'object' && settings.startup) ? settings.startup : {};
  const ui = (settings && typeof settings.ui === 'object' && settings.ui) ? settings.ui : {};
  if ($('admin-setting-show-welcome')) $('admin-setting-show-welcome').checked = !!startup.show_welcome_on_launch;
  if ($('admin-setting-dev-mode')) $('admin-setting-dev-mode').checked = !!startup.dev_mode;
  if ($('admin-setting-compact-backend')) $('admin-setting-compact-backend').checked = !!ui.compact_backend_status;
  if ($('admin-setting-workspace-setup')) $('admin-setting-workspace-setup').checked = !!ui.use_workspace_setup_strip;
  if ($('admin-setting-generation-action-order')) $('admin-setting-generation-action-order').value = String(ui.generation_action_order || 'left');
  adminApplyDeveloperBoundary(!!startup.dev_mode);
}

function adminRenderOverview(data) {
  const recent = (data && typeof data.recent_totals === 'object' && data.recent_totals) ? data.recent_totals : {};
  const nodeState = (data && typeof data.node_manager === 'object' && data.node_manager) ? data.node_manager : {};
  if ($('admin-system-summary')) {
    $('admin-system-summary').textContent = `Welcome screen ${data?.app_settings?.startup?.show_welcome_on_launch ? 'on' : 'off'} · Dev mode ${data?.app_settings?.startup?.dev_mode ? 'on' : 'off'} · Runtime ${backendManagerState?.settings?.settings?.low_vram_mode ? 'low VRAM' : 'balanced'}`;
  }
  if ($('admin-workspace-summary')) {
    $('admin-workspace-summary').textContent = `Setup strips ${data?.app_settings?.ui?.use_workspace_setup_strip ? 'on' : 'off'} · Compact backend ${data?.app_settings?.ui?.compact_backend_status ? 'on' : 'off'} · Action order ${data?.app_settings?.ui?.generation_action_order === 'right' ? 'right' : 'left'}`;
  }
  if ($('admin-overview-system')) {
    $('admin-overview-system').textContent = `Welcome ${data?.app_settings?.startup?.show_welcome_on_launch ? 'on' : 'off'} · Dev mode ${data?.app_settings?.startup?.dev_mode ? 'on' : 'off'} · Runtime ${backendManagerState?.settings?.settings?.low_vram_mode ? 'low VRAM' : 'balanced'}`;
  }
  if ($('admin-overview-workspace')) {
    $('admin-overview-workspace').textContent = `Setup strips ${data?.app_settings?.ui?.use_workspace_setup_strip ? 'on' : 'off'} · Compact backend ${data?.app_settings?.ui?.compact_backend_status ? 'on' : 'off'} · Action order ${data?.app_settings?.ui?.generation_action_order === 'right' ? 'right' : 'left'}`;
  }
  if ($('admin-overview-providers')) {
    const session = (data?.backend_state?.session) || {};
    const connected = ['text','image','video','voice','audio'].filter(role => !!session?.[role]?.connected).length;
    $('admin-overview-providers').textContent = `${connected} shared backend lane${connected === 1 ? '' : 's'} connected · save profiles here once and reuse them across surfaces`;
  }
  if ($('admin-data-summary')) {
    $('admin-data-summary').textContent = `Prompt presets ${recent.prompt_presets || 0} · Caption presets ${recent.caption_presets || 0} · Bundles ${recent.bundles || 0} · Metadata ${recent.metadata || 0}`;
  }
  if ($('admin-guides-summary')) {
    $('admin-guides-summary').textContent = `${Number(data?.support_guides_count || 0)} support guides loaded · ${Number(data?.helper_packets_count || 0)} helper packets stored`;
  }
  if ($('admin-memory-summary')) {
    const mem = (data && typeof data.memory_health === 'object' && data.memory_health) ? data.memory_health : {};
    const issueCount = Array.isArray(mem.issues) ? mem.issues.length : 0;
    $('admin-memory-summary').textContent = `Assistant sessions ${Number(mem.assistant_index_rows || 0)} indexed / ${Number(mem.assistant_session_files || 0)} files · Roleplay parts ${Number(mem.roleplay_part_files || 0)} · Memory chunks ${Number(mem.memory_chunks_total || 0)} · Summary records ${Number(mem.summary_records_count || 0)}${issueCount ? ` · Issues ${issueCount}` : ''}`;
  }
  if ($('admin-extension-summary')) {
    const counts = (data && typeof data.extension_registry_counts === 'object' && data.extension_registry_counts) ? data.extension_registry_counts : {};
    $('admin-extension-summary').textContent = `${Number(counts.enabled_extension_packs ?? counts.extensions_enabled ?? 0)} / ${Number(counts.extension_packs ?? counts.extensions_total ?? 0)} extension packs enabled · ${Number(nodeState.installed_count || 0)} installed custom node folders`;
  }
  if ($('admin-dev-summary')) {
    const session = (data?.backend_state?.session) || {};
    const textConnected = !!session.text?.connected;
    const imageConnected = !!session.image?.connected;
    $('admin-dev-summary').textContent = `Text backend ${textConnected ? 'connected' : 'offline'} · Image backend ${imageConnected ? 'connected' : 'offline'}`;
  }
  if ($('admin-overview-developer')) {
    $('admin-overview-developer').textContent = data?.app_settings?.startup?.dev_mode ? 'Dev mode enabled · diagnostics lane is visible' : 'Dev mode off · diagnostics lane stays hidden';
  }
  adminApplySettings(data?.app_settings || {});
}

async function adminLoadOverview(force=false) {
  if (adminPanelLoaded && !force) return;
  const data = await safeFetchJson(`/api/admin/overview?_=${Date.now()}`, { cache:'no-store' });
  adminRenderOverview(data || {});
  adminPanelLoaded = true;
}

async function adminSaveSettings() {
  const payload = {
    startup: {
      show_welcome_on_launch: !!$('admin-setting-show-welcome')?.checked,
      dev_mode: !!$('admin-setting-dev-mode')?.checked,
    },
    ui: {
      compact_backend_status: !!$('admin-setting-compact-backend')?.checked,
      use_workspace_setup_strip: !!$('admin-setting-workspace-setup')?.checked,
      generation_action_order: String($('admin-setting-generation-action-order')?.value || 'left'),
    },
  };
  const data = await safeFetchJson('/api/admin/settings', {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify(payload),
  });
  adminApplySettings(data?.settings || {});
  setStatus('admin-system-status', 'Saved admin settings.', 'ok');
  setStatus('admin-workspace-status', 'Saved admin settings.', 'ok');
}


async function adminCheckExtensionHealth() {
  const box = $('admin-extension-health-display');
  if (!box) return;
  box.style.display = '';
  box.textContent = 'Checking extension health…';
  const data = await safeFetchJson(`/api/extensions/health?_=${Date.now()}`, { cache:'no-store' });
  const counts = data?.counts || {};
  const lines = [
    `Extension Health: ${counts.healthy || 0} healthy · ${counts.disabled || 0} disabled · ${counts.warning || 0} warning · ${counts.broken || 0} broken · ${counts.total || 0} total`,
    '',
  ];
  (data?.health || []).forEach(item => {
    lines.push(`[${String(item.severity || '').toUpperCase()}] ${item.name || item.extension_id || 'unknown'} (${item.extension_id || '—'})`);
    lines.push(`Status: ${item.status || 'unknown'} · Enabled: ${item.enabled ? 'yes' : 'no'}`);
    lines.push(`Reason: ${item.reason || '—'}`);
    if (item.manifest_path) lines.push(`Manifest: ${item.manifest_path}`);
    lines.push('');
  });
  box.textContent = lines.join('\n').trim() || 'No extension health data returned.';
  await adminLoadExtensionRegistry(true);
}

async function adminDisableBrokenExtensions() {
  const ok = window.confirm('Disable broken / missing-dependency / version-mismatch extensions in the registry? Files will not be deleted.');
  if (!ok) return;
  const data = await safeFetchJson('/api/extensions/disable-broken', { method:'POST' });
  await adminLoadExtensionRegistry(true);
  adminSetExtensionActionStatus((data?.disabled || []).length ? `Disabled: ${(data.disabled || []).join(', ')}` : 'No broken extensions needed disabling.', 'ok');
  await adminCheckExtensionHealth();
}

async function adminClearExtensionCache() {
  const ok = window.confirm('Clear the Neo extension cache folder? Installed extensions will not be removed.');
  if (!ok) return;
  const data = await safeFetchJson('/api/extensions/cache/clear', { method:'POST' });
  adminSetExtensionActionStatus(`Extension cache cleared. Removed ${Number(data?.removed_items || 0)} item(s).`, 'ok');
}
function adminFormatBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  const units = ['B','KB','MB','GB','TB'];
  let value = n;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) { value /= 1024; idx += 1; }
  return (idx === 0 ? String(Math.round(value)) : value.toFixed(value >= 10 ? 1 : 2)) + ' ' + units[idx];
}

const ADMIN_CLEANUP_TARGET_LABELS = {
  neo_generation_inputs: 'Neo generation inputs',
  comfy_input: 'Comfy input folder',
  comfy_output: 'Comfy output folder',
};

function adminRenderStorageCleanupTargets(targets) {
  const host = $('admin-storage-cleanup-targets');
  const summary = $('admin-storage-cleanup-summary');
  if (!host) return;
  host.innerHTML = '';
  const rows = Object.entries(targets || {});
  let totalFiles = 0;
  let totalBytes = 0;
  rows.forEach(([key, item]) => {
    totalFiles += Number(item?.file_count || 0);
    totalBytes += Number(item?.size_bytes || 0);
    const card = document.createElement('label');
    card.className = 'backend-info-box cleanup-target-card';
    card.style.display = 'block';
    const disabled = !item?.path || !item?.safe;
    card.innerHTML = '<div class="row" style="gap:8px; align-items:center;">' +
      '<input type="checkbox" data-cleanup-target="' + escapeHtml(key) + '" ' + (disabled ? 'disabled' : 'checked') + ' />' +
      '<strong>' + escapeHtml(ADMIN_CLEANUP_TARGET_LABELS[key] || key) + '</strong>' +
      '</div>' +
      '<div class="mini-note" style="margin-top:8px; word-break:break-all;">' + escapeHtml(item?.path || 'Not found') + '</div>' +
      '<div class="mini-note" style="margin-top:8px;">' +
      String(Number(item?.file_count || 0)) + ' file(s) · ' + adminFormatBytes(item?.size_bytes || 0) +
      (item?.exists ? '' : ' · folder missing') +
      (item?.safe ? '' : ' · blocked') +
      '</div>';
    host.appendChild(card);
  });
  if (summary) summary.textContent = rows.length ? `${totalFiles} file(s) found across cleanup targets · ${adminFormatBytes(totalBytes)} total` : 'No cleanup targets found.';
}

async function adminLoadStorageCleanupTargets() {
  const status = $('admin-storage-cleanup-status');
  if (status) status.textContent = 'Scanning cleanup folders…';
  const data = await safeFetchJson(`/api/admin/storage-cleanup/targets?_=${Date.now()}`, { cache:'no-store' });
  adminRenderStorageCleanupTargets(data?.targets || {});
  if (status) status.textContent = 'Cleanup folder scan complete.';
}

async function adminCleanSelectedStorageTargets() {
  const selected = Array.from(document.querySelectorAll('[data-cleanup-target]:checked')).map(el => el.getAttribute('data-cleanup-target')).filter(Boolean);
  if (!selected.length) {
    setStatus('admin-storage-cleanup-status', 'Select at least one cleanup target first.', 'error');
    return;
  }
  const labels = selected.map(key => ADMIN_CLEANUP_TARGET_LABELS[key] || key).join(', ');
  const ok = window.confirm('Clean selected temporary folders?\n\n' + labels + '\n\nNeo final outputs, models, custom nodes, and extensions will not be touched.');
  if (!ok) return;
  setStatus('admin-storage-cleanup-status', 'Cleaning selected folders…', '');
  const data = await safeFetchJson('/api/admin/storage-cleanup/clean', {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ targets: selected }),
  });
  adminRenderStorageCleanupTargets(data?.targets || {});
  const cleaned = data?.cleaned || {};
  const parts = Object.entries(cleaned).map(([key, item]) => {
    const errors = Array.isArray(item?.errors) ? item.errors.length : 0;
    return `${ADMIN_CLEANUP_TARGET_LABELS[key] || key}: removed ${Number(item?.removed_files || 0)} file(s), ${Number(item?.removed_folders || 0)} folder(s)${errors ? `, ${errors} error(s)` : ''}`;
  });
  setStatus('admin-storage-cleanup-status', parts.join(' · ') || 'Cleanup complete.', 'ok');
}

function initAdminPanel() {
  document.querySelectorAll('[data-admin-section]').forEach(btn => {
    btn.addEventListener('click', () => {
      adminShowSection(btn.getAttribute('data-admin-section') || 'system');
      const key = btn.getAttribute('data-admin-section') || '';
      if (key === 'data') { adminLoadOverview(true).catch(() => {}); adminLoadStorageCleanupTargets().catch(() => {}); }
      if (key === 'extensions') adminShowExtensionSubtab(document.querySelector('[data-admin-extension-subtab].active')?.getAttribute('data-admin-extension-subtab') || 'extension-manager');
    });
  });
  $('btn-admin-refresh-overview')?.addEventListener('click', () => { adminLoadOverview(true).catch(err => setStatus('admin-system-status', err.message || 'Could not refresh admin overview.', 'error')); adminLoadExtensionRegistry(true).catch(() => {}); });
  document.querySelectorAll("[data-admin-extension-subtab]").forEach(btn => {
    btn.addEventListener("click", () => adminShowExtensionSubtab(btn.getAttribute("data-admin-extension-subtab") || "extension-manager"));
  });
  $('admin-extension-pack-select')?.addEventListener('change', adminRenderSelectedExtensionPack);
  $('btn-admin-extension-refresh')?.addEventListener('click', () => { adminLoadExtensionRegistry(true).catch(err => setStatus('admin-system-status', err.message || 'Could not refresh extension registry.', 'error')); });
  $("btn-admin-extension-health")?.addEventListener("click", () => { adminCheckExtensionHealth().catch(err => adminSetExtensionActionStatus(err.message || "Could not check extension health.", "error")); });
  $("btn-admin-extension-disable-broken")?.addEventListener("click", () => { adminDisableBrokenExtensions().catch(err => adminSetExtensionActionStatus(err.message || "Could not disable broken extensions.", "error")); });
  $("btn-admin-extension-clear-cache")?.addEventListener("click", () => { adminClearExtensionCache().catch(err => adminSetExtensionActionStatus(err.message || "Could not clear extension cache.", "error")); });
  $('btn-admin-extension-show-manifest')?.addEventListener('click', () => { adminShowManifestStandard().catch(err => setStatus('admin-system-status', err.message || 'Could not load manifest standard.', 'error')); });
  $('btn-admin-extension-toggle')?.addEventListener('click', () => { adminToggleSelectedExtensionPack().catch(err => setStatus('admin-system-status', err.message || 'Could not toggle extension pack.', 'error')); });
  $('btn-admin-extension-install-git')?.addEventListener('click', () => { adminInstallExtensionGit().catch(err => adminSetExtensionActionStatus(err.message || 'Could not install Git extension.', 'error')); });
  $('btn-admin-extension-install-zip')?.addEventListener('click', () => { adminInstallExtensionZip().catch(err => adminSetExtensionActionStatus(err.message || 'Could not install ZIP extension.', 'error')); });
  $('btn-admin-extension-update')?.addEventListener('click', () => { adminUpdateSelectedExtension().catch(err => adminSetExtensionActionStatus(err.message || 'Could not update extension.', 'error')); });
  $('btn-admin-extension-repair')?.addEventListener('click', () => { adminRepairSelectedExtension().catch(err => adminSetExtensionActionStatus(err.message || 'Could not repair extension.', 'error')); });
  $('btn-admin-extension-open-folder')?.addEventListener('click', () => { adminOpenSelectedExtensionFolder().catch(err => adminSetExtensionActionStatus(err.message || 'Could not open extension folder.', 'error')); });
  $('btn-admin-extension-view-manifest')?.addEventListener('click', () => { adminViewSelectedExtensionManifest().catch(err => adminSetExtensionActionStatus(err.message || 'Could not view manifest.', 'error')); });
  $('btn-admin-extension-view-log')?.addEventListener('click', () => { adminViewSelectedExtensionLog().catch(err => adminSetExtensionActionStatus(err.message || 'Could not view log.', 'error')); });
  $('btn-admin-extension-remove')?.addEventListener('click', () => { adminRemoveSelectedExtension().catch(err => adminSetExtensionActionStatus(err.message || 'Could not remove extension.', 'error')); });
  document.querySelectorAll('[data-admin-save-settings]').forEach(btn => {
    btn.addEventListener('click', () => {
      adminSaveSettings().catch(err => {
        const msg = err.message || 'Could not save admin settings.';
        setStatus('admin-system-status', msg, 'error');
        setStatus('admin-workspace-status', msg, 'error');
      });
    });
  });
  $('btn-admin-open-welcome-board')?.addEventListener('click', () => { if (typeof window.openWelcomeBoard === 'function') window.openWelcomeBoard(); });
  $('btn-admin-storage-refresh')?.addEventListener('click', () => { adminLoadStorageCleanupTargets().catch(err => setStatus('admin-storage-cleanup-status', err.message || 'Could not scan cleanup folders.', 'error')); });
  $('btn-admin-storage-clean-selected')?.addEventListener('click', () => { adminCleanSelectedStorageTargets().catch(err => setStatus('admin-storage-cleanup-status', err.message || 'Could not clean selected folders.', 'error')); });
  const adminTabBtn = document.querySelector('[data-main-tab="admin"]');
  adminTabBtn?.addEventListener('click', () => { adminLoadOverview(false).catch(() => {}); adminLoadExtensionRegistry(false).catch(() => {}); });
  adminShowExtensionSubtab('extension-manager');
  adminShowSection('system');
}

document.addEventListener('DOMContentLoaded', initAdminPanel);
