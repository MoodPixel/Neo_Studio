(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;

  function libraryTitleFor(kind, item) {
    const row = item || {};
    return core.text(row.label) || core.text(row.display_label) || core.text(row.title) || core.text(row.name) || core.text(row.id) || 'Untitled';
  }


  function libraryStatusTheme(status = '') {
    const clean = core.text(status).toLowerCase();
    const themes = {
      runtime_ready: {
        tone: 'Runtime ready',
        border: 'rgba(52, 211, 153, 0.32)',
        glow: '0 0 0 1px rgba(52, 211, 153, 0.10), 0 0 18px rgba(52, 211, 153, 0.12)',
        bg: 'rgba(52, 211, 153, 0.05)',
      },
      approved: {
        tone: 'Approved',
        border: 'rgba(147, 197, 253, 0.28)',
        glow: '0 0 0 1px rgba(147, 197, 253, 0.06), 0 0 14px rgba(147, 197, 253, 0.06)',
        bg: 'rgba(147, 197, 253, 0.04)',
      },
      reviewed: {
        tone: 'Reviewed',
        border: 'rgba(99, 179, 237, 0.28)',
        glow: '0 0 0 1px rgba(99, 179, 237, 0.06), 0 0 14px rgba(99, 179, 237, 0.06)',
        bg: 'rgba(99, 179, 237, 0.04)',
      },
      draft: {
        tone: 'Draft',
        border: 'rgba(255,255,255,0.12)',
        glow: 'none',
        bg: 'rgba(255,255,255,0.03)',
      },
    };
    return themes[clean] || {
      tone: clean ? clean.replace(/_/g, ' ') : 'Draft',
      border: 'rgba(255,255,255,0.12)',
      glow: 'none',
      bg: 'rgba(255,255,255,0.03)',
    };
  }

  function renderLibraryCounts() {
    const root = core.$('roleplay-v2-library-counts');
    if (!root) return;
    const counts = state.v2LibraryCounts || {};
    root.innerHTML = '';
    Object.entries(counts).forEach(([kind, count]) => {
      const chip = document.createElement('span');
      chip.className = 'badge';
      chip.textContent = `${kind.replace(/_/g, ' ')} · ${count}`;
      root.appendChild(chip);
    });
  }

  function renderLibraryList() {
    const root = core.$('roleplay-v2-library-list');
    const badge = core.$('roleplay-v2-library-kind-badge');
    if (!root || !badge) return;
    const kind = core.text(core.$('roleplay-v2-library-kind-select')?.value) || 'character';
    const search = core.text(core.$('roleplay-v2-library-search')?.value).toLowerCase();
    state.selectedLibraryKind = kind;
    const items = Array.isArray((state.v2LibraryGroups || {})[kind]) ? (state.v2LibraryGroups || {})[kind] : [];
    badge.textContent = kind.charAt(0).toUpperCase() + kind.slice(1);
    root.innerHTML = '';
    const filtered = items.filter(item => JSON.stringify(item || {}).toLowerCase().includes(search));
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'No runtime-ready V2 records match this view yet.';
      root.appendChild(empty);
      return;
    }
    filtered.slice(0, 160).forEach(item => {
      const statusTheme = libraryStatusTheme(item.status || 'draft');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.style.display = 'grid';
      btn.style.gap = '6px';
      btn.style.textAlign = 'left';
      btn.style.borderColor = statusTheme.border;
      btn.style.background = statusTheme.bg;
      btn.style.boxShadow = statusTheme.glow;
      btn.innerHTML = `<span>${libraryTitleFor(kind, item)}</span><span class="mini-note">${core.text(item.id)} · <span class="badge" style="margin-left:6px; border-color:${statusTheme.border}; box-shadow:${statusTheme.glow}; background:${statusTheme.bg};">${statusTheme.tone}</span></span>${core.text(item.summary) ? `<span class="mini-note">${core.text(item.summary)}</span>` : ''}`;
      btn.addEventListener('click', () => {
        state.selectedLibraryItem = item;
        renderLibraryPreview();
      });
      root.appendChild(btn);
    });
  }

  function previewScopeSummary(record) {
    const scope = record?.scope_values || record?.links?.scope || {};
    const labels = [
      scope.current_universe_id || scope.universe_id,
      scope.current_world_id || scope.world_id,
      scope.current_region_id || scope.region_id,
      scope.current_city_id || scope.city_id,
      scope.current_location_id || scope.location_id,
    ].map(value => core.text(value)).filter(Boolean);
    return labels.length ? labels.join(' → ') : 'No explicit scope saved yet.';
  }

  function previewValidationSummary(validation) {
    const payload = validation && typeof validation === 'object' ? validation : {};
    const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
    const errors = Array.isArray(payload.errors) ? payload.errors.filter(Boolean) : [];
    if (!warnings.length && !errors.length) return 'No validation warnings.';
    const lines = [];
    if (errors.length) lines.push(`Errors · ${errors.slice(0, 4).join(' | ')}`);
    if (warnings.length) lines.push(`Warnings · ${warnings.slice(0, 4).join(' | ')}`);
    return lines.join('\n');
  }

  function previewMemorySummary(memoryPreview) {
    if (!memoryPreview) return 'No memory preview available yet.';
    const fragments = Array.isArray(memoryPreview.memory_fragments) ? memoryPreview.memory_fragments : [];
    const shared = Array.isArray(memoryPreview.shared_memories) ? memoryPreview.shared_memories : [];
    const fragLines = fragments.slice(0, 4).map(row => `- ${core.text(row?.title) || core.text(row?.source_ref) || core.text(row?.id) || 'Untitled fragment'}`);
    const sharedLines = shared.slice(0, 3).map(row => `- ${core.text(row?.title) || core.text(row?.summary) || core.text(row?.id) || 'Untitled shared memory'}`);
    return [
      `Memory fragments · ${Number(memoryPreview.count || fragments.length || 0)}`,
      `Shared memory · ${Number(memoryPreview.shared_count || shared.length || 0)}`,
      fragLines.length ? `Top memory rows\n${fragLines.join('\n')}` : '',
      sharedLines.length ? `Shared rows\n${sharedLines.join('\n')}` : '',
    ].filter(Boolean).join('\n');
  }

  async function renderLibraryPreview() {
    const preview = core.$('roleplay-v2-library-preview');
    if (!preview) return;
    const item = state.selectedLibraryItem;
    if (!item?.id) {
      preview.textContent = 'Select a V2 record to review it here.';
      return;
    }
    try {
      const data = await core.getJson(`/api/roleplay/v2/builders/record?record_id=${encodeURIComponent(core.text(item.id))}`);
      let memoryPreview = null;
      try { memoryPreview = await core.getJson(`/api/roleplay/v2/memory/by-record?record_id=${encodeURIComponent(core.text(item.id))}&limit=6`); } catch (_) {}
      const record = data.record || {};
      const meta = record.meta || {};
      preview.textContent = [
        `Title · ${libraryTitleFor(state.selectedLibraryKind, record)}`,
        `Kind · ${core.text(record.kind) || core.text(item.kind) || core.text(state.selectedLibraryKind) || 'record'}`,
        `Record id · ${core.text(record.id) || core.text(item.id)}`,
        `Status · ${core.text(meta.status || item.status) || 'draft'}`,
        core.text(record.summary) ? `Summary · ${core.text(record.summary)}` : '',
        `Scope · ${previewScopeSummary(record)}`,
        '',
        'Validation',
        previewValidationSummary(data.validation),
        '',
        'Memory preview',
        previewMemorySummary(memoryPreview),
      ].filter(Boolean).join('\n');
    } catch (err) {
      preview.textContent = `Failed to load record preview: ${err.message || String(err)}`;
    }
  }

  async function refreshLibraryView() {
    const data = await core.getJson('/api/roleplay/v2/builders/library-state');
    state.v2LibraryGroups = data.groups || {};
    state.v2LibraryCounts = data.counts || {};
    const currentKind = core.text(state.selectedLibraryKind) || core.text(core.$('roleplay-v2-library-kind-select')?.value) || 'character';
    const visibleIds = new Set(((state.v2LibraryGroups || {})[currentKind] || []).map(item => core.text(item.id)).filter(Boolean));
    if (core.text(state.selectedLibraryItem?.id) && !visibleIds.has(core.text(state.selectedLibraryItem?.id))) {
      state.selectedLibraryItem = null;
    }
    renderLibraryCounts();
    renderLibraryList();
    await renderLibraryPreview();
    core.refreshUserPathGuide?.();
  }


  async function compileSelectedMemory() {
    const item = state.selectedLibraryItem;
    if (!item?.id) throw new Error('Select a V2 builder record first.');
    if (core.$('roleplay-v2-entity-id')) core.$('roleplay-v2-entity-id').value = core.text(item.id);
    const data = await core.modules?.studio?.compileMemoryForRecord?.(core.text(item.id), { statusMessage: `Compiled memory for ${core.text(item.id)} from Libraries.` });
    await renderLibraryPreview();
    return data;
  }

  async function buildRuntimeFromSelected() {
    const item = state.selectedLibraryItem;
    if (!item?.id) throw new Error('Select a V2 builder record first.');
    if (core.$('roleplay-v2-entity-id')) core.$('roleplay-v2-entity-id').value = core.text(item.id);
    const data = await core.modules?.studio?.buildRuntimeForRecord?.(core.text(item.id), { statusMessage: `Built Scene packet from ${core.text(item.id)} in Libraries.` });
    return data;
  }

  async function openSelectedInForge() {
    const item = state.selectedLibraryItem;
    if (!item?.id) {
      core.setStatus('roleplay-v2-project-status', 'Select a V2 builder record first.', 'error');
      return;
    }
    state.forge = state.forge || {};
    state.forge.selectedKind = core.text(item.kind) || state.selectedLibraryKind || 'character';
    state.forge.selectedRecordId = core.text(item.id);
    state.forge.workingPayload = null;
    core.setSubtab('forge');
    await core.modules?.forge?.loadForgeState?.();
    core.setStatus('roleplay-v2-forge-status', `Opened ${core.text(item.id)} in Forge.`, 'success');
  }

  async function boot() {
    core.$('btn-roleplay-v2-library-refresh')?.addEventListener('click', () => refreshLibraryView().catch(err => core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error')));
    core.$('roleplay-v2-library-kind-select')?.addEventListener('change', renderLibraryList);
    core.$('roleplay-v2-library-search')?.addEventListener('input', renderLibraryList);
    core.$('btn-roleplay-v2-library-use-id')?.addEventListener('click', () => {
      const id = core.text(state.selectedLibraryItem?.id);
      if (!id) { core.setStatus('roleplay-v2-project-status', 'Selected library item has no id to bridge yet.', 'error'); return; }
      if (core.$('roleplay-v2-entity-id')) core.$('roleplay-v2-entity-id').value = id;
      core.setStatus('roleplay-v2-project-status', `Bridged ${id} into the Studio focus field.`, 'success');
      core.setSubtab('studio');
      core.setStudioSubtab('compile');
    });
    core.$('btn-roleplay-v2-library-open-in-forge')?.addEventListener('click', () => openSelectedInForge().catch(err => core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-library-compile-memory')?.addEventListener('click', () => compileSelectedMemory().catch(err => core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-library-build-runtime')?.addEventListener('click', () => buildRuntimeFromSelected().catch(err => core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error')));
    await refreshLibraryView();
  }

  core.refreshRoleplayV2LibraryView = refreshLibraryView;
  core.registerModule('libraries', { boot, refreshLibraryView });
})();
