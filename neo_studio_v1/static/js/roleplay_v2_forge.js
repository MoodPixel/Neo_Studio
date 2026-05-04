(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;
  state.forge = state.forge || {
    builders: [],
    templates: {},
    foundation: null,
    sqliteBackbone: null,
    sharedContracts: {},
    hierarchy: null,
    selectedGroupId: 'universe_world',
    selectedKind: 'universe',
    activeView: 'form',
    selectedRecordId: '',
    recordsByKind: {},
    workingPayload: null,
    lastNormalization: null,
    recentLinkSelections: [],
    selectedSubcategoryFilters: {},
    activeScope: {},
    recordListView: 'current_kind',
    recordGroupBy: 'scope',
    recordStatusFilter: '',
    recordSearch: '',
    jsonApplyMode: 'fill_empty_only',
    utilityView: 'inspector',
    resizableShells: false,
  };

  let activeLinkPicker = null;

  const FORGE_RAIL_GROUPS = [
    { id: 'universe_world', label: 'Universe / World', builders: ['universe', 'world', 'region', 'city'] },
    { id: 'locations', label: 'Locations', builders: ['location'] },
    { id: 'characters', label: 'Characters', builders: ['character'] },
    { id: 'organizations', label: 'Organizations', builders: ['organization'] },
    { id: 'artifacts', label: 'Artifacts', builders: ['artifact'] },
    { id: 'rituals', label: 'Rituals', builders: ['ritual'] },
    { id: 'cycles', label: 'Cycles / Systems', builders: ['cycle'] },
    { id: 'creatures', label: 'Creatures', builders: ['creature'] },
    { id: 'legends', label: 'Legends', builders: ['legend'] },
    { id: 'scenarios', label: 'Scenarios', builders: ['scenario'] },
  ];

  function forgeState() {
    return state.forge || {};
  }

  function deepClone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function safeStringify(value) {
    try { return JSON.stringify(value, null, 2); } catch (_) { return String(value || ''); }
  }

  function isFilledValue(value) {
    if (value === null || value === undefined) return false;
    if (typeof value === 'string') return value.trim().length > 0;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'object') return Object.keys(value).length > 0;
    return true;
  }

  function deepMergeOverwrite(baseValue, incomingValue) {
    if (Array.isArray(incomingValue)) return deepClone(incomingValue);
    if (incomingValue && typeof incomingValue === 'object') {
      const target = baseValue && typeof baseValue === 'object' && !Array.isArray(baseValue) ? deepClone(baseValue) : {};
      Object.entries(incomingValue).forEach(([key, value]) => {
        target[key] = deepMergeOverwrite(target[key], value);
      });
      return target;
    }
    return deepClone(incomingValue);
  }

  function deepMergeFillEmpty(baseValue, incomingValue) {
    if (!isFilledValue(baseValue)) return deepClone(incomingValue);
    if (incomingValue && typeof incomingValue === 'object' && !Array.isArray(incomingValue) && baseValue && typeof baseValue === 'object' && !Array.isArray(baseValue)) {
      const target = deepClone(baseValue);
      Object.entries(incomingValue).forEach(([key, value]) => {
        target[key] = deepMergeFillEmpty(target[key], value);
      });
      return target;
    }
    return deepClone(baseValue);
  }

  function setByPath(target, path, value) {
    const parts = String(path || '').split('.').filter(Boolean);
    if (!parts.length) return;
    let cursor = target;
    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1;
      if (isLast) {
        cursor[part] = value;
        return;
      }
      if (!cursor[part] || typeof cursor[part] !== 'object' || Array.isArray(cursor[part])) cursor[part] = {};
      cursor = cursor[part];
    });
  }

  function getByPath(target, path) {
    return String(path || '').split('.').filter(Boolean).reduce((cursor, part) => {
      if (!cursor || typeof cursor !== 'object') return undefined;
      return cursor[part];
    }, target);
  }

  function flattenRecord(record) {
    return {
      id: core.text(record?.id),
      kind: core.text(record?.kind),
      label: core.text(record?.label || record?.display_label || record?.title),
      summary: core.text(record?.summary),
      status: core.text(record?.status || record?.meta?.status || 'draft'),
    };
  }


  function recordStatusTheme(status = '') {
    const clean = core.text(status).toLowerCase();
    const themes = {
      draft: {
        tone: 'Draft',
        border: 'rgba(255,255,255,0.12)',
        glow: 'none',
        bg: 'rgba(255,255,255,0.03)',
      },
      draft_stub: {
        tone: 'Draft stub',
        border: 'rgba(244, 180, 0, 0.28)',
        glow: '0 0 0 1px rgba(244, 180, 0, 0.08), 0 0 14px rgba(244, 180, 0, 0.08)',
        bg: 'rgba(244, 180, 0, 0.04)',
      },
      reviewed: {
        tone: 'Reviewed',
        border: 'rgba(99, 179, 237, 0.28)',
        glow: '0 0 0 1px rgba(99, 179, 237, 0.06), 0 0 14px rgba(99, 179, 237, 0.06)',
        bg: 'rgba(99, 179, 237, 0.04)',
      },
      approved: {
        tone: 'Approved',
        border: 'rgba(147, 197, 253, 0.28)',
        glow: '0 0 0 1px rgba(147, 197, 253, 0.06), 0 0 14px rgba(147, 197, 253, 0.06)',
        bg: 'rgba(147, 197, 253, 0.04)',
      },
      runtime_ready: {
        tone: 'Runtime ready',
        border: 'rgba(52, 211, 153, 0.32)',
        glow: '0 0 0 1px rgba(52, 211, 153, 0.10), 0 0 18px rgba(52, 211, 153, 0.12)',
        bg: 'rgba(52, 211, 153, 0.05)',
      },
      archived: {
        tone: 'Archived',
        border: 'rgba(148, 163, 184, 0.24)',
        glow: 'none',
        bg: 'rgba(148, 163, 184, 0.03)',
      },
    };
    return themes[clean] || {
      tone: prettyLabel(clean || 'draft'),
      border: 'rgba(255,255,255,0.12)',
      glow: 'none',
      bg: 'rgba(255,255,255,0.03)',
    };
  }

  function availabilityLabel() {
    return 'Ready';
  }

  function builderSummary(kind) {
    const selected = core.text(kind) || core.text(forgeState().selectedKind) || 'universe';
    return (forgeState().builders || []).find(item => core.text(item.kind) === selected) || null;
  }

  function templatePayload(kind) {
    const selected = core.text(kind) || core.text(forgeState().selectedKind) || 'universe';
    return forgeState().templates?.[selected] || null;
  }

  function entitySpec(kind) {
    const selected = core.text(kind) || core.text(forgeState().selectedKind) || 'universe';
    return forgeState().foundation?.foundation?.entity_specs?.[selected] || null;
  }

  function hierarchyContract() {
    return forgeState().hierarchy || {};
  }

  function hierarchyEntry(kind) {
    const selected = core.text(kind) || core.text(forgeState().selectedKind) || 'universe';
    return hierarchyContract()?.kinds?.[selected] || null;
  }

  function hierarchyEntryPoints() {
    const points = hierarchyContract()?.entry_points;
    return Array.isArray(points) ? points : [];
  }

  function groupForKind(kind) {
    const cleanKind = core.text(kind);
    return FORGE_RAIL_GROUPS.find(group => group.builders.includes(cleanKind)) || FORGE_RAIL_GROUPS[0];
  }

  function activeGroup() {
    const selected = core.text(forgeState().selectedGroupId);
    return FORGE_RAIL_GROUPS.find(group => group.id === selected) || groupForKind(forgeState().selectedKind);
  }

  function recordCountForKind(kind) {
    const items = Array.isArray(forgeState().recordsByKind?.[kind]) ? forgeState().recordsByKind[kind] : [];
    return items.filter(recordMatchesActiveScope).length;
  }

  function selectedSubcategoryFilter(kind = '') {
    const cleanKind = core.text(kind || forgeState().selectedKind);
    return core.text(forgeState().selectedSubcategoryFilters?.[cleanKind]);
  }

  function setSelectedSubcategoryFilter(kind = '', value = '') {
    const cleanKind = core.text(kind || forgeState().selectedKind);
    forgeState().selectedSubcategoryFilters = forgeState().selectedSubcategoryFilters || {};
    forgeState().selectedSubcategoryFilters[cleanKind] = core.text(value);
  }

  function activeScope() {
    return forgeState().activeScope || {};
  }

  function hasActiveScope() {
    return ['universe_id', 'world_id', 'region_id', 'city_id'].some(key => core.text(activeScope()?.[key]));
  }

  function universeWorldIds(universeId = '') {
    const cleanUniverseId = core.text(universeId);
    const items = forgeState().recordsByKind?.world || [];
    return new Set(items.filter(item => core.text(item.scope_values?.universe_id) === cleanUniverseId).map(item => core.text(item.id)).filter(Boolean));
  }

  function collectScopeDescendantIds(scope = {}) {
    const ids = new Set();
    const add = value => {
      const clean = core.text(value);
      if (clean) ids.add(clean);
    };
    const hasAny = keys => keys.some(key => core.text(scope?.[key]));
    add(scope?.universe_id);
    add(scope?.world_id);
    add(scope?.region_id);
    add(scope?.city_id);

    const worldItems = forgeState().recordsByKind?.world || [];
    const regionItems = forgeState().recordsByKind?.region || [];
    const cityItems = forgeState().recordsByKind?.city || [];
    const locationItems = forgeState().recordsByKind?.location || [];

    const worldIds = new Set();
    const regionIds = new Set();
    const cityIds = new Set();
    const locationIds = new Set();

    worldItems.forEach(item => {
      const values = item.scope_values || {};
      if ((core.text(scope?.universe_id) && core.text(values.universe_id) === core.text(scope.universe_id)) || (core.text(scope?.world_id) && core.text(item.id) === core.text(scope.world_id))) {
        worldIds.add(core.text(item.id));
      }
    });

    regionItems.forEach(item => {
      const values = item.scope_values || {};
      if ((core.text(scope?.region_id) && core.text(item.id) === core.text(scope.region_id)) || (core.text(values.world_id) && worldIds.has(core.text(values.world_id))) || (core.text(scope?.world_id) && core.text(values.world_id) === core.text(scope.world_id))) {
        regionIds.add(core.text(item.id));
      }
    });

    cityItems.forEach(item => {
      const values = item.scope_values || {};
      if ((core.text(scope?.city_id) && core.text(item.id) === core.text(scope.city_id)) || (core.text(values.region_id) && regionIds.has(core.text(values.region_id))) || (core.text(values.world_id) && worldIds.has(core.text(values.world_id))) || (core.text(scope?.region_id) && core.text(values.region_id) === core.text(scope.region_id)) || (core.text(scope?.world_id) && core.text(values.world_id) === core.text(scope.world_id))) {
        cityIds.add(core.text(item.id));
      }
    });

    locationItems.forEach(item => {
      const values = item.scope_values || {};
      if ((core.text(values.city_id) && cityIds.has(core.text(values.city_id))) || (core.text(values.region_id) && regionIds.has(core.text(values.region_id))) || (core.text(values.world_id) && worldIds.has(core.text(values.world_id))) || (core.text(scope?.city_id) && core.text(values.city_id) === core.text(scope.city_id)) || (core.text(scope?.region_id) && core.text(values.region_id) === core.text(scope.region_id)) || (core.text(scope?.world_id) && core.text(values.world_id) === core.text(scope.world_id))) {
        locationIds.add(core.text(item.id));
      }
    });

    [worldIds, regionIds, cityIds, locationIds].forEach(set => set.forEach(add));
    return ids;
  }

  function recordLookupById(recordId = '') {
    const cleanId = core.text(recordId);
    if (!cleanId) return null;
    const groups = forgeState().recordsByKind || {};
    for (const items of Object.values(groups)) {
      const found = Array.isArray(items) ? items.find(item => core.text(item.id) === cleanId) : null;
      if (found) return found;
    }
    return null;
  }

  function recordLabelById(recordId = '') {
    const row = recordLookupById(recordId);
    return core.text(row?.label || row?.display_label || row?.id || recordId);
  }

  function recordMatchesActiveScope(item) {
    if (!hasActiveScope()) return true;
    const row = item || {};
    const values = Object.values(row.scope_values || {}).map(value => core.text(value)).filter(Boolean);
    const descendantIds = collectScopeDescendantIds(activeScope());
    if (descendantIds.has(core.text(row.id))) return true;
    return values.some(value => descendantIds.has(core.text(value)));
  }

  function deriveScopeFromPayload(kind = '', payload = {}) {
    const cleanKind = core.text(kind || payload?.kind || forgeState().selectedKind);
    const rawScope = payload?.links?.scope && typeof payload.links.scope === 'object' ? payload.links.scope : {};
    const scope = {
      universe_id: core.text(rawScope.universe_id),
      world_id: core.text(rawScope.world_id),
      region_id: core.text(rawScope.region_id),
      city_id: core.text(rawScope.city_id),
      source_kind: cleanKind,
      source_id: core.text(payload?.id),
      source_label: core.text(payload?.label || payload?.display_label || payload?.title),
    };
    if (cleanKind === 'universe' && core.text(payload?.id)) scope.universe_id = core.text(payload.id);
    if (cleanKind === 'world' && core.text(payload?.id)) scope.world_id = core.text(payload.id);
    if (cleanKind === 'region' && core.text(payload?.id)) scope.region_id = core.text(payload.id);
    if (cleanKind === 'city' && core.text(payload?.id)) scope.city_id = core.text(payload.id);
    return scope;
  }

  function applyActiveScopeToPayload(kind = '', payload = {}) {
    const entry = hierarchyEntry(kind);
    const slots = Array.isArray(entry?.scope_slots) ? entry.scope_slots : [];
    if (!payload.links || typeof payload.links !== 'object') payload.links = {};
    if (!payload.links.scope || typeof payload.links.scope !== 'object') payload.links.scope = {};
    const scope = activeScope() || {};
    const sourceKind = core.text(scope?.source_kind);
    const sourceId = core.text(scope?.source_id);
    const genericMap = {
      universe_id: core.text(scope?.universe_id),
      world_id: core.text(scope?.world_id),
      region_id: core.text(scope?.region_id),
      city_id: core.text(scope?.city_id),
      current_world_id: core.text(scope?.world_id),
      current_region_id: core.text(scope?.region_id),
      current_city_id: core.text(scope?.city_id),
      current_location_id: sourceKind === 'location' ? sourceId : '',
      location_id: sourceKind === 'location' ? sourceId : '',
      base_location_id: sourceKind === 'location' ? sourceId : '',
      parent_location_id: sourceKind === 'location' ? sourceId : '',
      parent_organization_id: sourceKind === 'organization' ? sourceId : '',
    };
    slots.forEach(slot => {
      const scopedValue = core.text(scope?.[slot] || genericMap?.[slot]);
      if (scopedValue && !core.text(payload.links.scope?.[slot])) payload.links.scope[slot] = scopedValue;
    });
    if (core.text(kind) === 'world' && core.text(scope?.universe_id) && !core.text(payload.links.scope?.universe_id)) {
      payload.links.scope.universe_id = core.text(scope.universe_id);
    }
    if (core.text(kind) === 'region' && core.text(scope?.world_id) && !core.text(payload.links.scope?.world_id)) {
      payload.links.scope.world_id = core.text(scope.world_id);
    }
    if (core.text(kind) === 'city') {
      if (core.text(scope?.world_id) && !core.text(payload.links.scope?.world_id)) payload.links.scope.world_id = core.text(scope.world_id);
      if (core.text(scope?.region_id) && !core.text(payload.links.scope?.region_id)) payload.links.scope.region_id = core.text(scope.region_id);
    }
    return payload;
  }

  function setActiveScope(scope = {}, statusMessage = '') {
    forgeState().activeScope = scope || {};
    renderScopeBar();
    renderScopePicker();
    renderScopeChildActions();
    renderEntryLauncher();
    renderGroupRail();
    renderBuilderRail();
    renderRecordList();
    if (statusMessage) core.setStatus('roleplay-v2-forge-status', statusMessage, 'success');
  }

  function renderScopeBar() {
    const bar = core.$('roleplay-v2-forge-scope-bar');
    if (!bar) return;
    bar.innerHTML = '';
    if (!hasActiveScope()) {
      bar.textContent = 'No active build scope set yet.';
      return;
    }
    const label = document.createElement('span');
    label.className = 'mini-note';
    label.textContent = 'Active build scope';
    bar.appendChild(label);
    const order = ['universe_id', 'world_id', 'region_id', 'city_id'];
    order.forEach((slot, index) => {
      const value = core.text(activeScope()?.[slot]);
      if (!value) return;
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'btn btn-small';
      chip.textContent = `${prettyLabel(slot)} · ${recordLabelById(value) || value}`;
      chip.title = value;
      chip.addEventListener('click', () => {
        const trimmed = {
          universe_id: index >= 0 ? core.text(activeScope().universe_id) : '',
          world_id: index >= 1 ? core.text(activeScope().world_id) : '',
          region_id: index >= 2 ? core.text(activeScope().region_id) : '',
          city_id: index >= 3 ? core.text(activeScope().city_id) : '',
          source_kind: activeScope().source_kind || '',
          source_id: activeScope().source_id || '',
          source_label: activeScope().source_label || '',
        };
        setActiveScope(trimmed, `Scope trimmed to ${prettyLabel(slot)}.`);
      });
      bar.appendChild(chip);
    });
  }

  function scopePickerMatches(item, pickerKind) {
    const row = item || {};
    const values = row.scope_values || {};
    const cleanKind = core.text(pickerKind);
    if (cleanKind === 'world' && core.text(activeScope().universe_id)) {
      return core.text(values.universe_id) === core.text(activeScope().universe_id);
    }
    if (cleanKind === 'region' && core.text(activeScope().world_id)) {
      return core.text(values.world_id) === core.text(activeScope().world_id);
    }
    if (cleanKind === 'city') {
      if (core.text(activeScope().region_id)) return core.text(values.region_id) === core.text(activeScope().region_id);
      if (core.text(activeScope().world_id)) return core.text(values.world_id) === core.text(activeScope().world_id);
    }
    return true;
  }

  function renderScopeChildActions() {
    const root = core.$('roleplay-v2-forge-scope-child-actions');
    if (!root) return;
    root.innerHTML = '';
    if (!hasActiveScope()) {
      root.textContent = 'Select or lock a scope to unlock smart child creation.';
      return;
    }
    const sourceKind = core.text(activeScope().source_kind);
    const entry = hierarchyEntry(sourceKind);
    const childKinds = Array.isArray(entry?.recommended_child_kinds) && entry.recommended_child_kinds.length
      ? entry.recommended_child_kinds
      : (Array.isArray(entry?.child_kinds) ? entry.child_kinds.slice(0, 4) : []);
    const label = document.createElement('span');
    label.className = 'mini-note';
    label.textContent = `Create child records inside ${core.text(activeScope().source_label || recordLabelById(activeScope().source_id) || activeScope().source_id)}`;
    root.appendChild(label);
    childKinds.forEach(kind => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-small';
      btn.textContent = `Create ${core.text(hierarchyEntry(kind)?.display_name || prettyLabel(kind))} here`;
      btn.addEventListener('click', async () => {
        setSelectedSubcategoryFilter(kind, '');
        await setSelectedKind(kind, { resetRecord: true, forceNew: true });
        core.setStatus('roleplay-v2-forge-status', `${core.text(hierarchyEntry(kind)?.display_name || prettyLabel(kind))} builder opened with the current active scope applied.`, 'success');
      });
      root.appendChild(btn);
    });
  }

  function renderScopePicker() {
    const root = core.$('roleplay-v2-forge-scope-picker-list');
    if (!root) return;
    const pickerKind = core.text(core.$('roleplay-v2-forge-scope-kind-select')?.value) || 'universe';
    const search = core.text(core.$('roleplay-v2-forge-scope-search')?.value).toLowerCase();
    const items = Array.isArray(forgeState().recordsByKind?.[pickerKind]) ? forgeState().recordsByKind[pickerKind] : [];
    const filtered = items
      .filter(item => scopePickerMatches(item, pickerKind))
      .filter(item => JSON.stringify(item || {}).toLowerCase().includes(search))
      .slice(0, 80);
    root.innerHTML = '';
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'No scope records match this view yet.';
      root.appendChild(empty);
      return;
    }
    filtered.forEach(item => {
      const row = document.createElement('div');
      row.style.display = 'grid';
      row.style.gridTemplateColumns = 'minmax(0, 1fr) auto';
      row.style.gap = '8px';
      row.style.alignItems = 'center';
      const meta = document.createElement('div');
      meta.style.display = 'grid';
      meta.style.gap = '4px';
      meta.innerHTML = `<span>${core.text(item.label) || core.text(item.id)}</span><span class="mini-note">${core.text(item.id)}</span>`;
      meta.title = core.text(item.id);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-small';
      btn.textContent = 'Set scope';
      btn.addEventListener('click', () => {
        const scope = deriveScopeFromPayload(core.text(item.kind), {
          id: core.text(item.id),
          kind: core.text(item.kind),
          label: core.text(item.label),
          display_label: core.text(item.display_label),
          links: { scope: item.scope_values || {} },
        });
        setActiveScope(scope, `Scope set from ${core.text(item.label) || core.text(item.id)}.`);
      });
      row.appendChild(meta);
      row.appendChild(btn);
      root.appendChild(row);
    });
  }

  function totalCountForBuilders(builders = []) {
    return (builders || []).reduce((total, kind) => total + recordCountForKind(kind), 0);
  }

  function currentScopeRows(entry, payload) {
    const scope = payload?.links?.scope && typeof payload.links.scope === 'object' ? payload.links.scope : {};
    const order = Array.isArray(entry?.scope_priority) && entry.scope_priority.length ? entry.scope_priority : (entry?.scope_slots || []);
    return order.map(slot => ({ slot, value: core.text(scope?.[slot]) })).filter(row => row.value);
  }

  function currentPayload() {
    if (!forgeState().workingPayload) {
      const template = templatePayload(forgeState().selectedKind);
      forgeState().workingPayload = deepClone(template?.json_template_payload || {});
    }
    return forgeState().workingPayload || {};
  }

  function updateRecordBadge() {
    const badge = core.$('roleplay-v2-forge-record-badge');
    if (!badge) return;
    const payload = currentPayload();
    const label = core.text(payload?.label || payload?.display_label || payload?.title);
    if (core.text(payload?.id)) {
      badge.textContent = `${label || payload.id} · ${payload.id}`;
    } else {
      badge.textContent = label ? `${label} · unsaved` : 'No record loaded';
    }
  }

  function syncJsonEditor() {
    const editor = core.$('roleplay-v2-forge-json-editor');
    if (editor) editor.value = safeStringify(currentPayload());
    updateRecordBadge();
  }

  function renderForgeViews() {
    const current = core.text(forgeState().activeView) || 'form';
    document.querySelectorAll('#roleplay-v2-forge-viewbar [data-roleplay-v2-forge-view]').forEach(btn => {
      btn.classList.toggle('active', core.text(btn.getAttribute('data-roleplay-v2-forge-view')) === current);
    });
    document.querySelectorAll('[data-roleplay-v2-forge-panel]').forEach(panel => {
      panel.classList.toggle('hidden', core.text(panel.getAttribute('data-roleplay-v2-forge-panel')) !== current);
    });
    applyForgeShellSizing();
  }

  function applyForgeShellSizing() {
    const enabled = !!forgeState().resizableShells;
    const railShell = core.$('roleplay-v2-forge-rail-shell');
    const editorShell = core.$('roleplay-v2-forge-editor-shell');
    const railToggle = core.$('btn-roleplay-v2-forge-auto-height-rail');
    const editorToggle = core.$('btn-roleplay-v2-forge-auto-height-editor');
    [railShell, editorShell].forEach(shell => {
      if (!shell) return;
      shell.style.minHeight = enabled ? '420px' : '';
      shell.style.overflow = enabled ? 'auto' : '';
      shell.style.resize = enabled ? 'vertical' : '';
    });
    [railToggle, editorToggle].forEach(btn => {
      if (!btn) return;
      btn.textContent = enabled ? 'Drag resize on' : 'Drag resize off';
      btn.classList.toggle('btn-primary', enabled);
    });
  }

  function toggleForgeAutoHeight() {
    forgeState().resizableShells = !forgeState().resizableShells;
    applyForgeShellSizing();
  }

  function renderForgeUtilityShell() {
    const internalTools = !!core.internalToolsVisible?.();
    const requested = core.text(forgeState().utilityView) || 'inspector';
    const current = !internalTools && requested === 'sqlite' ? 'inspector' : requested;
    forgeState().utilityView = current;
    const sqliteButton = document.querySelector('#roleplay-v2-forge-utility-viewbar [data-roleplay-v2-forge-utility-view="sqlite"]');
    if (sqliteButton) sqliteButton.classList.toggle('hidden', !internalTools);
    const meta = current === 'sqlite'
      ? { title: 'SQLite debug', note: 'Sync file records into the canonical SQLite backbone and inspect current entity, edge, memory fragment, shared-memory, and callback rows.', badge: 'SQLite' }
      : { title: 'Inspector', note: 'Shared contract summary, builder implementation state, and current payload validation.', badge: 'Inspector' };
    document.querySelectorAll('#roleplay-v2-forge-utility-viewbar [data-roleplay-v2-forge-utility-view]').forEach(btn => {
      btn.classList.toggle('active', core.text(btn.getAttribute('data-roleplay-v2-forge-utility-view')) === current);
    });
    document.querySelectorAll('[data-roleplay-v2-forge-utility-panel]').forEach(panel => {
      const isSqlite = core.text(panel.getAttribute('data-roleplay-v2-forge-utility-panel')) === 'sqlite';
      panel.classList.toggle('hidden', core.text(panel.getAttribute('data-roleplay-v2-forge-utility-panel')) !== current || (isSqlite && !internalTools));
    });
    const title = core.$('roleplay-v2-forge-utility-title');
    const note = core.$('roleplay-v2-forge-utility-note');
    const badge = core.$('roleplay-v2-forge-utility-badge');
    if (title) title.textContent = meta.title;
    if (note) note.textContent = meta.note;
    if (badge) badge.textContent = meta.badge;
  }

  async function setSelectedKind(kind, { resetRecord = true, forceNew = true } = {}) {
    const cleanKind = core.text(kind) || 'universe';
    forgeState().selectedKind = cleanKind;
    forgeState().selectedGroupId = groupForKind(cleanKind).id;
    if (resetRecord) forgeState().selectedRecordId = '';
    forgeState().workingPayload = null;
    forgeState().memoryPreview = null;
    renderEntryLauncher();
    renderGroupRail();
    await refreshTemplatesForSelected();
    await refreshRecordList();
    if (forceNew) newFromTemplate();
    else renderSelectedBuilder();
  }

  function createBuilderChip(kind) {
    const hierarchy = hierarchyEntry(kind);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn btn-small ${core.text(kind) === core.text(forgeState().selectedKind) ? 'btn-primary' : ''}`.trim();
    btn.style.justifyContent = 'space-between';
    btn.style.display = 'flex';
    btn.style.width = '100%';
    btn.innerHTML = `<span>${core.text(hierarchy?.display_name || kind)}</span><span class="badge">${recordCountForKind(kind)} saved</span>`;
    btn.title = hierarchy ? `${core.text(hierarchy.entry_label || '')} · parents: ${(hierarchy.parent_kinds || []).map(prettyLabel).join(', ') || 'none'}` : '';
    btn.addEventListener('click', async () => {
      setSelectedSubcategoryFilter(kind, '');
      await setSelectedKind(kind, { resetRecord: true, forceNew: true });
    });
    return btn;
  }

  function renderSubcategoryChipsInto(panel, kind = '') {
    if (!panel) return;
    panel.innerHTML = '';
    const hierarchy = hierarchyEntry(kind || forgeState().selectedKind);
    const subcategory = hierarchy?.subcategory;
    if (!subcategory || !Array.isArray(subcategory.values) || !subcategory.values.length) {
      const note = document.createElement('div');
      note.className = 'mini-note';
      note.textContent = 'No sub-category chips for this builder.';
      panel.appendChild(note);
      return;
    }
    const heading = document.createElement('div');
    heading.className = 'mini-note';
    heading.style.width = '100%';
    heading.textContent = `${subcategory.label} chips`; 
    panel.appendChild(heading);
    const payload = currentPayload();
    const currentValue = core.text(selectedSubcategoryFilter(kind || forgeState().selectedKind) || getByPath(payload, subcategory.field_path)).toLowerCase();
    subcategory.values.forEach(value => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const isActive = core.text(kind || forgeState().selectedKind) === core.text(forgeState().selectedKind) && currentValue === core.text(value).toLowerCase();
      btn.className = `btn btn-small ${isActive ? 'btn-primary' : ''}`.trim();
      btn.textContent = prettyLabel(value);
      btn.addEventListener('click', () => {
        setSelectedSubcategoryFilter(kind || forgeState().selectedKind, value);
        setByPath(currentPayload(), subcategory.field_path, value);
        renderRecordList();
        renderSelectedBuilder();
        core.setStatus('roleplay-v2-forge-status', `${subcategory.label} set to ${prettyLabel(value)} for the current ${prettyLabel(forgeState().selectedKind)} form.`, 'success');
      });
      panel.appendChild(btn);
    });
  }

  function renderEntryLauncher() {
    const root = core.$('roleplay-v2-forge-entry-list');
    if (!root) return;
    root.innerHTML = '';
    const entries = hierarchyEntryPoints();
    if (!entries.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'Hierarchy entry points are not available yet.';
      root.appendChild(empty);
      return;
    }
    entries.forEach(entry => {
      const cleanKind = core.text(entry?.kind);
      const isContinue = !cleanKind;
      const isActive = isContinue ? hasActiveScope() : cleanKind === core.text(forgeState().selectedKind);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn ${isActive ? 'btn-primary' : ''}`.trim();
      btn.style.display = 'grid';
      btn.style.gap = '4px';
      btn.style.textAlign = 'left';
      const recommended = Array.isArray(entry?.recommended_for) ? entry.recommended_for.slice(0, 2).map(prettyLabel).join(' · ') : '';
      btn.innerHTML = `
        <span>${core.text(entry?.label) || 'Start here'}</span>
        <span class="mini-note">${core.text(entry?.description) || 'Open the matching builder lane.'}</span>
        <span class="mini-note">${recommended || (isContinue ? 'Reuse a saved universe/world/region/city scope.' : `Open the ${prettyLabel(cleanKind)} builder.`)}</span>
      `;
      btn.addEventListener('click', async () => {
        if (isContinue) {
          const select = core.$('roleplay-v2-forge-scope-kind-select');
          const search = core.$('roleplay-v2-forge-scope-search');
          if (hasActiveScope()) {
            const sourceLabel = core.text(activeScope().source_label || recordLabelById(activeScope().source_id) || activeScope().source_id);
            core.setStatus('roleplay-v2-forge-status', `Continuing from existing scope ${sourceLabel || 'current scope'}. Child creation buttons and scope auto-fill are live.`, 'success');
          } else {
            if (select) {
              const preferred = core.text(forgeState().selectedKind);
              if (['universe', 'world', 'region', 'city'].includes(preferred)) select.value = preferred;
            }
            renderScopePicker();
            if (search) search.focus();
            core.setStatus('roleplay-v2-forge-status', 'Pick a saved universe, world, region, or city in the scope picker to continue an existing hierarchy.', 'warning');
          }
          return;
        }
        setSelectedSubcategoryFilter(cleanKind, '');
        await setSelectedKind(cleanKind, { resetRecord: true, forceNew: true });
        const scopeNote = hasActiveScope() ? ' The active scope will auto-fill matching parent slots.' : '';
        core.setStatus('roleplay-v2-forge-status', `${core.text(entry?.label) || `Opened ${prettyLabel(cleanKind)}`}.${scopeNote}`, 'success');
      });
      root.appendChild(btn);
    });
  }


  function renderGroupRail() {
    const panel = core.$('roleplay-v2-forge-group-list');
    const note = core.$('roleplay-v2-forge-group-note');
    if (!panel) return;
    panel.innerHTML = '';
    FORGE_RAIL_GROUPS.forEach(group => {
      const card = document.createElement('div');
      card.style.display = 'grid';
      card.style.gap = '8px';
      const btn = document.createElement('button');
      btn.type = 'button';
      const isActive = group.id === activeGroup()?.id;
      btn.className = `btn btn-small ${isActive ? 'btn-primary' : ''}`.trim();
      btn.style.display = 'flex';
      btn.style.gap = '8px';
      btn.style.alignItems = 'center';
      btn.style.justifyContent = 'space-between';
      btn.style.width = '100%';
      btn.innerHTML = `<span>${group.label}</span><span class="badge">${totalCountForBuilders(group.builders)}</span>`;
      btn.addEventListener('click', async () => {
        forgeState().selectedGroupId = group.id;
        if (!group.builders.includes(core.text(forgeState().selectedKind))) {
          await setSelectedKind(group.builders[0], { resetRecord: true, forceNew: true });
        } else {
          renderGroupRail();
          renderBuilderRail();
          renderSubcategoryChips();
        }
      });
      card.appendChild(btn);

      if (isActive) {
        const detail = document.createElement('div');
        detail.style.display = 'grid';
        detail.style.gap = '10px';
        detail.style.padding = '8px 0 0 10px';

        const builderList = document.createElement('div');
        builderList.style.display = 'grid';
        builderList.style.gap = '8px';
        (group.builders || []).forEach(kind => builderList.appendChild(createBuilderChip(kind)));
        detail.appendChild(builderList);

        const subPanel = document.createElement('div');
        subPanel.style.display = 'flex';
        subPanel.style.gap = '8px';
        subPanel.style.flexWrap = 'wrap';
        subPanel.style.alignContent = 'flex-start';
        renderSubcategoryChipsInto(subPanel, forgeState().selectedKind);
        detail.appendChild(subPanel);

        card.appendChild(detail);
      }

      panel.appendChild(card);
    });
    if (note) {
      const group = activeGroup();
      note.textContent = `Current category · ${group?.label || 'Universe / World'}. Builder and sub-category chips now stay directly under the selected main category.`;
    }
  }

  function renderBuilderRail() {
    const list = core.$('roleplay-v2-forge-builder-list');
    if (list) list.innerHTML = '';
  }

  function renderSubcategoryChips() {
    const panel = core.$('roleplay-v2-forge-subcategory-list');
    if (panel) panel.innerHTML = '';
  }

  async function loadRecordIntoForge(recordId = '') {
    const cleanId = core.text(recordId);
    if (!cleanId) throw new Error('record_id is required.');
    const data = await core.getJson(`/api/roleplay/v2/builders/record?record_id=${encodeURIComponent(cleanId)}`);
    forgeState().selectedRecordId = cleanId;
    forgeState().workingPayload = deepClone(data.builder_payload || {});
    forgeState().lastNormalization = data.normalization || null;
    forgeState().selectedGroupId = groupForKind(data.builder_payload?.kind || data.record?.kind || forgeState().selectedKind).id;
    await refreshMemoryPreview(cleanId);
    syncJsonEditor();
    renderEntryLauncher();
    renderGroupRail();
    renderBuilderRail();
    renderRecordList();
    renderSubcategoryChips();
    renderSelectedBuilder(data.validation || null);
    core.setOutput(data);
    return data;
  }

  async function deleteBuilderRecord(recordId = '', { label = '' } = {}) {
    const cleanId = core.text(recordId);
    if (!cleanId) throw new Error('Select a saved record first.');
    const cleanLabel = core.text(label) || cleanId;
    const ok = window.confirm(`Delete record?

${cleanLabel}
${cleanId}

This removes the saved Forge record. Linked references may remain until you update them.`);
    if (!ok) return null;
    const data = await core.postForm('/api/roleplay/v2/builders/delete', { record_id: cleanId });
    if (core.text(forgeState().selectedRecordId) === cleanId || core.text(currentPayload()?.id) === cleanId) {
      forgeState().selectedRecordId = '';
      forgeState().workingPayload = null;
      forgeState().memoryPreview = null;
      newFromTemplate();
    }
    await refreshLibraryOverview();
    await refreshRecordList();
    if (typeof core.refreshRoleplayV2LibraryView === 'function') {
      try { await core.refreshRoleplayV2LibraryView(); } catch (_) {}
    }
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    core.setStatus('roleplay-v2-forge-status', `Deleted ${cleanLabel} (${cleanId}).`, 'success');
    core.setOutput(data);
    return data;
  }

  function recordListView() {
    return core.text(forgeState().recordListView || core.$('roleplay-v2-forge-record-view')?.value) || 'current_kind';
  }

  function recordGroupBy() {
    return core.text(forgeState().recordGroupBy || core.$('roleplay-v2-forge-record-group-by')?.value) || 'scope';
  }

  function recordStatusFilter() {
    return core.text(forgeState().recordStatusFilter || core.$('roleplay-v2-forge-record-status-filter')?.value).toLowerCase();
  }

  function recordSearchValue() {
    return core.text(forgeState().recordSearch || core.$('roleplay-v2-forge-record-search')?.value).toLowerCase();
  }

  function recordScopeLabel(item = {}) {
    const values = item.scope_values || {};
    const order = ['universe_id', 'world_id', 'region_id', 'city_id'];
    const parts = order
      .map(slot => ({ slot, value: core.text(values?.[slot]) }))
      .filter(row => row.value)
      .map(row => `${prettyLabel(row.slot.replace(/_id$/, ''))}: ${recordLabelById(row.value) || row.value}`);
    return parts.length ? parts.join(' · ') : 'Unscoped';
  }

  function currentRecordPool() {
    const view = recordListView();
    if (view === 'all') {
      return Object.entries(forgeState().recordsByKind || {}).flatMap(([kind, items]) => (Array.isArray(items) ? items.map(item => ({ ...item, kind: core.text(item.kind || kind) || kind })) : []));
    }
    if (view === 'active_group') {
      const builders = activeGroup()?.builders || [];
      return builders.flatMap(kind => (Array.isArray(forgeState().recordsByKind?.[kind]) ? forgeState().recordsByKind[kind].map(item => ({ ...item, kind: core.text(item.kind || kind) || kind })) : []));
    }
    const kind = core.text(forgeState().selectedKind) || 'universe';
    return (forgeState().recordsByKind?.[kind] || []).map(item => ({ ...item, kind: core.text(item.kind || kind) || kind }));
  }

  function recordMatchesListFilters(item = {}) {
    const search = recordSearchValue();
    const status = recordStatusFilter();
    const currentKind = core.text(forgeState().selectedKind) || 'universe';
    const activeSubcategory = recordListView() === 'current_kind' ? core.text(selectedSubcategoryFilter(currentKind)).toLowerCase() : '';
    if (!recordMatchesActiveScope(item)) return false;
    if (status && core.text(item.status).toLowerCase() !== status) return false;
    if (activeSubcategory && core.text(item.subcategory_value).toLowerCase() !== activeSubcategory) return false;
    if (!search) return true;
    const hay = [
      core.text(item.id),
      core.text(item.kind),
      core.text(item.label),
      core.text(item.display_label),
      core.text(item.summary),
      core.text(item.status),
      core.text(item.subcategory_value),
      recordScopeLabel(item),
    ].join(' ').toLowerCase();
    return hay.includes(search);
  }

  function recordGroupMeta(item = {}) {
    const groupBy = recordGroupBy();
    if (groupBy === 'kind') return { key: core.text(item.kind) || 'unknown', label: prettyLabel(core.text(item.kind) || 'unknown') };
    if (groupBy === 'subcategory') {
      const sub = core.text(item.subcategory_value) || 'none';
      return { key: `subcategory:${sub}`, label: sub === 'none' ? 'No sub-category' : prettyLabel(sub) };
    }
    if (groupBy === 'status') {
      const status = core.text(item.status) || 'draft';
      return { key: `status:${status}`, label: `${prettyLabel(status)} status` };
    }
    const scopeLabel = recordScopeLabel(item);
    return { key: `scope:${scopeLabel}`, label: scopeLabel };
  }

  function renderRecordCounts(totalCount = 0, scopedCount = 0, filteredCount = 0) {
    const note = core.$('roleplay-v2-forge-record-counts');
    if (!note) return;
    const viewLabel = recordListView() === 'all' ? 'all Forge kinds' : recordListView() === 'active_group' ? `${activeGroup()?.label || 'current rail group'}` : `${prettyLabel(core.text(forgeState().selectedKind) || 'current builder')}`;
    note.textContent = `Showing ${filteredCount} of ${scopedCount} scope-matching / ${totalCount} total · view ${viewLabel} · grouped by ${prettyLabel(recordGroupBy())}.`;
  }

  function renderRecordList() {
    const panel = core.$('roleplay-v2-forge-record-list');
    if (!panel) return;
    panel.innerHTML = '';
    const pool = currentRecordPool();
    const scopedItems = pool.filter(recordMatchesActiveScope);
    const filteredItems = pool.filter(recordMatchesListFilters);
    renderRecordCounts(pool.length, scopedItems.length, filteredItems.length);
    if (!filteredItems.length) {
      panel.textContent = 'No saved Forge records match the current search, status, scope, and sub-category filters.';
      return;
    }
    const grouped = new Map();
    filteredItems.forEach(item => {
      const meta = recordGroupMeta(item);
      if (!grouped.has(meta.key)) grouped.set(meta.key, { label: meta.label, items: [] });
      grouped.get(meta.key).items.push(item);
    });
    Array.from(grouped.values()).forEach(section => {
      const groupCard = document.createElement('div');
      groupCard.className = 'panel';
      groupCard.style.padding = '10px';
      groupCard.style.background = 'rgba(255,255,255,0.02)';
      groupCard.style.border = '1px solid rgba(255,255,255,0.06)';
      groupCard.style.display = 'grid';
      groupCard.style.gap = '8px';

      const header = document.createElement('div');
      header.className = 'row-between';
      header.innerHTML = `<div class="mini-note">${section.label}</div><span class="badge">${Number(section.items.length)} records</span>`;
      groupCard.appendChild(header);

      section.items.forEach(item => {
        const row = document.createElement('div');
        row.style.display = 'grid';
        row.style.gridTemplateColumns = 'minmax(0, 1fr) auto auto';
        row.style.gap = '8px';
        row.style.alignItems = 'stretch';
        const statusTheme = recordStatusTheme(item.status || 'draft');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `btn btn-small ${core.text(item.id) === core.text(forgeState().selectedRecordId) ? 'btn-primary' : ''}`.trim();
        btn.style.display = 'grid';
        btn.style.gap = '6px';
        btn.style.width = '100%';
        btn.style.textAlign = 'left';
        btn.style.borderColor = statusTheme.border;
        btn.style.background = statusTheme.bg;
        btn.style.boxShadow = statusTheme.glow;
        btn.innerHTML = `
          <span>${core.text(item.label) || core.text(item.id)}</span>
          <span class="mini-note"><span class="badge" style="margin-right:6px; border-color:${statusTheme.border}; box-shadow:${statusTheme.glow}; background:${statusTheme.bg};">${statusTheme.tone}</span>${prettyLabel(core.text(item.kind) || 'record')}${core.text(item.subcategory_value) ? ` · ${prettyLabel(core.text(item.subcategory_value))}` : ''}</span>
          <span class="mini-note">${recordScopeLabel(item)}</span>
          <span class="mini-note">${Number(item.edge_count || 0)} edges · ${Number(item.reverse_edge_count || 0)} incoming</span>`;
        btn.addEventListener('click', async () => {
          try {
            await loadRecordIntoForge(core.text(item.id));
            core.setStatus('roleplay-v2-forge-status', `Loaded ${core.text(item.id)}.`, 'success');
          } catch (err) {
            core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error');
          }
        });
        const scopeBtn = document.createElement('button');
        scopeBtn.type = 'button';
        scopeBtn.className = 'btn btn-small';
        scopeBtn.textContent = 'Scope';
        scopeBtn.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          const scope = deriveScopeFromPayload(core.text(item.kind), {
            id: core.text(item.id),
            kind: core.text(item.kind),
            label: core.text(item.label),
            display_label: core.text(item.display_label),
            links: { scope: item.scope_values || {} },
          });
          setActiveScope(scope, `Scope set from ${core.text(item.label) || core.text(item.id)}.`);
        });
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'btn btn-small';
        del.textContent = 'Delete';
        del.addEventListener('click', async event => {
          event.preventDefault();
          event.stopPropagation();
          try { await deleteBuilderRecord(core.text(item.id), { label: core.text(item.label) }); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
        });
        row.appendChild(btn);
        row.appendChild(scopeBtn);
        row.appendChild(del);
        groupCard.appendChild(row);
      });
      panel.appendChild(groupCard);
    });
  }

  function prettyLabel(key) {
    const text = String(key || '').replace(/_/g, ' ').trim();
    return text
      .split(/\s+/)
      .filter(Boolean)
      .map(word => {
        const lower = word.toLowerCase();
        if (lower === 'id') return 'ID';
        if (lower === 'ids') return 'IDs';
        if (lower === 'md') return 'MD';
        if (lower === 'json') return 'JSON';
        return lower.charAt(0).toUpperCase() + lower.slice(1);
      })
      .join(' ');
  }

  function optionValuesForField(key, path = '') {
    const lower = core.text(key).toLowerCase();
    const lowerPath = core.text(path).toLowerCase();
    const shared = forgeState().sharedContracts || {};
    const visibility = shared.record?.shared_enums?.visibility || ['public', 'restricted', 'hidden', 'author_private'];
    const canonStatus = shared.record?.shared_enums?.canon_status || ['primary_canon', 'secondary_canon', 'alternate_canon', 'uncertain_canon', 'legacy_canon'];
    const revealModes = shared.memory_hints?.reveal_gating_values || ['open', 'staged', 'gated_by_trust', 'gated_by_discovery', 'gm_only', 'restricted'];
    const priorityValues = shared.memory_hints?.priority_values || ['low', 'medium', 'high'];
    const map = {
      canon_status: canonStatus,
      visibility,
      status: (shared.record?.shared_enums?.record_status || ['draft', 'draft_stub', 'reviewed', 'approved', 'runtime_ready', 'archived']),
      universe_type: ['single_world', 'multi_world', 'layered_realms', 'mythic_cosmos', 'fractured_multiverse', 'hybrid'],
      reality_model: ['material_only', 'material_plus_spiritual', 'layered_metaphysical', 'fragmented_multiversal', 'unknown', 'hybrid'],
      interworld_travel_status: ['common', 'restricted', 'rare', 'forbidden', 'unknown'],
      realm_type: ['mortal_world', 'divine_world', 'threshold_world', 'shattered_world', 'hidden_world', 'hybrid'],
      world_role: ['primary_setting', 'secondary_setting', 'mythic_source_world', 'lost_world', 'sealed_world', 'contested_world'],
      region_type: ['kingdom', 'province', 'territory', 'duchy', 'city_state_region', 'frontier', 'holy_region', 'tribal_domain', 'hybrid'],
      settlement_type: ['capital_city', 'major_city', 'port_city', 'trade_town', 'fortress_town', 'village', 'religious_settlement', 'hidden_settlement', 'ruined_settlement', 'frontier_settlement', 'hybrid'],
      location_type: ['hall', 'temple', 'market', 'street', 'port', 'gate', 'forest_site', 'ruin', 'estate', 'tavern', 'archive', 'crypt', 'fort', 'bridge', 'sanctum', 'wild_site', 'hybrid'],
      anchor_type: ['universe_anchor', 'world_anchor', 'region_anchor', 'city_anchor', 'nested_location', 'free_roaming_site', 'hidden_site'],
      role_tier: ['major_character', 'supporting_character', 'minor_character', 'background_character'],
      group_type: ['royal_house', 'court', 'guild', 'religious_order', 'military_order', 'criminal_network', 'cult', 'archive_or_scholarly_body', 'mercantile_power', 'clan', 'political_faction', 'rebel_group', 'intelligence_network', 'hybrid'],
      reach_scale: ['local', 'regional', 'world', 'multiworld', 'hidden_network'],
      artifact_type: ['weapon', 'relic', 'ceremonial_item', 'cursed_item', 'key_item', 'tool', 'heirloom', 'ritual_focus', 'seal_or_token', 'armor', 'hybrid'],
      practice_type: ['ritual', 'spell', 'potion', 'technique', 'discipline', 'binding', 'healing_method', 'combat_method', 'forbidden_practice', 'hybrid'],
      system_type: ['cycle', 'condition', 'curse', 'disease', 'metaphysical_system', 'social_system', 'biological_system', 'transformation_system', 'environmental_pattern', 'hybrid'],
      category: ['animal', 'beast', 'predator', 'mount', 'companion', 'magical_fauna', 'sentient_being', 'hidden_being', 'aquatic_creature', 'avian_creature', 'hybrid'],
      legend_type: ['origin_legend', 'prophecy', 'historical_legend', 'saint_or_hero_legend', 'warning_tale', 'monster_legend', 'sacred_legend', 'dynastic_legend', 'hidden_history', 'hybrid'],
      format_hint: ['roleplay_scene', 'conversation_scene', 'conflict_scene', 'investigation_scene', 'romance_scene', 'journey_scene', 'ritual_scene', 'social_pressure_scene', 'hybrid'],
      access_tier: ['public', 'restricted', 'elite_restricted', 'sealed', 'forbidden'],
      reach_scale: ['local', 'regional', 'world', 'multiworld', 'hidden_network'],
      link_resolution_status: ['resolved', 'stub', 'unresolved_text'],
      relationship_type: ['family', 'romantic', 'friend', 'ally', 'rival', 'enemy', 'mentor', 'student', 'leader', 'follower', 'caretaker', 'obsession', 'political', 'spiritual', 'place_bond', 'artifact_bond', 'other'],
      world_creation_model: ['created_together', 'branched', 'shattered_from_one_source', 'unknown'],
      interworld_travel_status: ['common', 'restricted', 'rare', 'forbidden', 'unknown'],
      truth_status: ['true', 'mostly_true', 'partially_true', 'distorted', 'false_but_powerful', 'unknown', 'suppressed_truth'],
      scope_type: ['universe', 'world', 'region', 'location', 'lineage', 'culture', 'organization', 'hybrid'],
      reach_scale: ['local', 'regional', 'world', 'multiworld', 'hidden_network'],
      rarity: ['common', 'uncommon', 'rare', 'very_rare', 'legendary', 'unique'],
      state: ['active', 'dormant', 'sealed', 'broken', 'lost', 'fragmented', 'corrupted', 'unknown'],
      visibility_status: ['publicly_known', 'publicly_known_but_restricted', 'restricted', 'hidden'],
      authenticity_status: ['verified_original', 'verified_copy', 'disputed', 'unknown'],
      mode: revealModes,
      scene_use_relevance: priorityValues,
      emotional_salience: priorityValues,
      continuity_priority: priorityValues,
      priority: priorityValues,
      scene_relevance: priorityValues,
    };
    if (lowerPath.endsWith('memory_hints.reveal_gating.mode')) return revealModes;
    if (lowerPath.includes('memory_hints.priority.')) return priorityValues;
    return map[lower] || null;
  }

  function isLinkField(path, key) {
    const lowerPath = core.text(path).toLowerCase();
    const lowerKey = core.text(key).toLowerCase();
    return lowerPath.startsWith('links.') && (lowerKey.endsWith('_id') || lowerKey.endsWith('_ids'));
  }

  function targetKindsForLinkField(key) {
    const lower = core.text(key).toLowerCase();
    const singular = lower.endsWith('_ids') ? lower.slice(0, -4) : lower.endsWith('_id') ? lower.slice(0, -3) : lower;
    const normalized = singular
      .replace(/^origin_/, '')
      .replace(/^current_/, '')
      .replace(/^featured_/, '')
      .replace(/^source_/, '')
      .replace(/^cast_/, '')
      .replace(/^linked_/, '')
      .replace(/^focus_/, '')
      .replace(/^primary_/, '')
      .replace(/^base_/, '')
      .replace(/^seat_/, '')
      .replace(/^member_/, '')
      .replace(/^leader_/, '')
      .replace(/^ally_/, '')
      .replace(/^rival_/, '')
      .replace(/^anchor_/, '')
      .replace(/^capital_of_/, '')
      .replace(/^capital_/, 'city_');
    const map = {
      universe: ['universe'],
      world: ['world'],
      region: ['region'],
      city: ['city'],
      location: ['location'],
      character: ['character'],
      organization: ['organization'],
      artifact: ['artifact'],
      ritual: ['ritual'],
      cycle: ['cycle'],
      creature: ['creature'],
      legend: ['legend'],
      scenario: ['scenario'],
      holder: ['character', 'organization'],
      entity: ['character', 'world', 'universe', 'region', 'city', 'location', 'organization', 'scenario', 'artifact', 'ritual', 'cycle', 'creature', 'legend'],
      project: [],
      source_container: [],
    };
    return map[normalized] || [];
  }

  async function ensureRecordCache(kind) {
    const cleanKind = core.text(kind);
    if (!cleanKind) return [];
    if (Array.isArray(forgeState().recordsByKind?.[cleanKind])) return forgeState().recordsByKind[cleanKind];
    const data = await core.getJson(`/api/roleplay/v2/builders/records?kind=${encodeURIComponent(cleanKind)}`);
    forgeState().recordsByKind[cleanKind] = Array.isArray(data.records) ? data.records : [];
    return forgeState().recordsByKind[cleanKind];
  }

  async function combinedLinkRecords(kinds) {
    const seen = new Set();
    const items = [];
    for (const kind of (kinds || [])) {
      const rows = await ensureRecordCache(kind);
      (rows || []).forEach(item => {
        const id = core.text(item.id);
        if (!id || seen.has(id)) return;
        seen.add(id);
        items.push({ ...item, kind });
      });
    }
    return items;
  }


  function linkPickerCategoryForKind(kind = '') {
    return core.text(groupForKind(kind)?.id || 'other');
  }

  function linkPickerScopeState(record = {}) {
    const values = Object.values(record?.scope_values || {}).map(value => core.text(value)).filter(Boolean);
    if (!values.length) return 'unscoped';
    return recordMatchesActiveScope(record) ? 'active_scope' : 'outside_scope';
  }

  function syncLinkPickerFilterControls() {
    const filters = activeLinkPicker?.filters || {};
    if (core.$('roleplay-v2-link-picker-kind-filter')) core.$('roleplay-v2-link-picker-kind-filter').value = core.text(filters.kind);
    if (core.$('roleplay-v2-link-picker-scope-filter')) core.$('roleplay-v2-link-picker-scope-filter').value = core.text(filters.scope || (hasActiveScope() ? 'active_scope' : 'all')) || 'all';
    if (core.$('roleplay-v2-link-picker-category-filter')) core.$('roleplay-v2-link-picker-category-filter').value = core.text(filters.category);
    if (core.$('roleplay-v2-link-picker-subcategory-filter')) core.$('roleplay-v2-link-picker-subcategory-filter').value = core.text(filters.subcategory);
    if (core.$('roleplay-v2-link-picker-status-filter')) core.$('roleplay-v2-link-picker-status-filter').value = core.text(filters.status);
  }

  function populateLinkPickerFilterOptions() {
    if (!activeLinkPicker) return;
    const records = Array.isArray(activeLinkPicker.records) ? activeLinkPicker.records : [];
    const kindSelect = core.$('roleplay-v2-link-picker-kind-filter');
    const categorySelect = core.$('roleplay-v2-link-picker-category-filter');
    const subcategorySelect = core.$('roleplay-v2-link-picker-subcategory-filter');
    const statusSelect = core.$('roleplay-v2-link-picker-status-filter');
    const scopeSelect = core.$('roleplay-v2-link-picker-scope-filter');
    const kinds = Array.from(new Set((activeLinkPicker.targetKinds?.length ? activeLinkPicker.targetKinds : records.map(item => core.text(item.kind))).map(value => core.text(value)).filter(Boolean))).sort();
    const categories = Array.from(new Set(records.map(item => linkPickerCategoryForKind(item.kind)).filter(Boolean))).sort();
    const subcategories = Array.from(new Set(records.map(item => core.text(item.subcategory_value)).filter(Boolean))).sort();
    const statuses = Array.from(new Set(records.map(item => core.text(item.status || 'draft')).filter(Boolean))).sort();

    const fillSelect = (select, options, emptyLabel, formatter = (value) => prettyLabel(value)) => {
      if (!select) return;
      const currentValue = core.text(select.value);
      select.innerHTML = '';
      const base = document.createElement('option');
      base.value = '';
      base.textContent = emptyLabel;
      select.appendChild(base);
      options.forEach(value => {
        const option = document.createElement('option');
        option.value = core.text(value);
        option.textContent = formatter(value);
        select.appendChild(option);
      });
      const nextValue = options.includes(currentValue) ? currentValue : '';
      select.value = nextValue;
      return nextValue;
    };

    const nextKind = fillSelect(kindSelect, kinds, activeLinkPicker.targetKinds?.length === 1 ? `Only ${prettyLabel(activeLinkPicker.targetKinds[0])}` : 'All kinds');
    const nextCategory = fillSelect(categorySelect, categories, 'All categories');
    const nextSubcategory = fillSelect(subcategorySelect, subcategories, 'All sub-categories');
    const nextStatus = fillSelect(statusSelect, statuses, 'All statuses');
    if (scopeSelect && !hasActiveScope() && core.text(scopeSelect.value) === 'active_scope') scopeSelect.value = 'all';
    activeLinkPicker.filters = {
      ...(activeLinkPicker.filters || {}),
      kind: nextKind,
      category: nextCategory,
      subcategory: nextSubcategory,
      status: nextStatus,
      scope: core.text(scopeSelect?.value || activeLinkPicker?.filters?.scope || (hasActiveScope() ? 'active_scope' : 'all')) || 'all',
    };
    syncLinkPickerFilterControls();
  }

  function linkPickerMatchesFilters(record = {}) {
    const filters = activeLinkPicker?.filters || {};
    const kindValue = core.text(filters.kind);
    const categoryValue = core.text(filters.category);
    const subcategoryValue = core.text(filters.subcategory).toLowerCase();
    const statusValue = core.text(filters.status).toLowerCase();
    const scopeValue = core.text(filters.scope || 'all');
    if (kindValue && core.text(record.kind) !== kindValue) return false;
    if (categoryValue && linkPickerCategoryForKind(record.kind) !== categoryValue) return false;
    if (subcategoryValue && core.text(record.subcategory_value).toLowerCase() !== subcategoryValue) return false;
    if (statusValue && core.text(record.status || 'draft').toLowerCase() !== statusValue) return false;
    if (scopeValue === 'unscoped') return linkPickerScopeState(record) === 'unscoped';
    if (scopeValue === 'outside_scope') return hasActiveScope() ? linkPickerScopeState(record) === 'outside_scope' : true;
    if (scopeValue === 'active_scope') return hasActiveScope() ? linkPickerScopeState(record) === 'active_scope' : true;
    return true;
  }

  function closeLinkPicker() {
    activeLinkPicker = null;
    core.$('roleplay-v2-link-picker-modal')?.classList.add('hidden');
    if (core.$('roleplay-v2-link-picker-search')) core.$('roleplay-v2-link-picker-search').value = '';
    if (core.$('roleplay-v2-link-picker-kind-filter')) core.$('roleplay-v2-link-picker-kind-filter').value = '';
    if (core.$('roleplay-v2-link-picker-scope-filter')) core.$('roleplay-v2-link-picker-scope-filter').value = 'all';
    if (core.$('roleplay-v2-link-picker-category-filter')) core.$('roleplay-v2-link-picker-category-filter').value = '';
    if (core.$('roleplay-v2-link-picker-subcategory-filter')) core.$('roleplay-v2-link-picker-subcategory-filter').value = '';
    if (core.$('roleplay-v2-link-picker-status-filter')) core.$('roleplay-v2-link-picker-status-filter').value = '';
    if (core.$('roleplay-v2-link-picker-results')) core.$('roleplay-v2-link-picker-results').innerHTML = '';
    if (core.$('roleplay-v2-link-picker-status')) core.$('roleplay-v2-link-picker-status').textContent = '';
  }

  function renderLinkPickerResults() {
    const host = core.$('roleplay-v2-link-picker-results');
    if (!host) return;
    host.innerHTML = '';
    const searchValue = core.text(core.$('roleplay-v2-link-picker-search')?.value).toLowerCase();
    const currentValue = core.text(activeLinkPicker?.currentValue);
    const records = (activeLinkPicker?.records || []).filter(item => {
      if (!linkPickerMatchesFilters(item)) return false;
      if (!searchValue) return true;
      const hay = [item.id, item.label, item.display_label, item.summary, item.status, item.kind, item.subcategory_value, linkPickerCategoryForKind(item.kind)].map(v => core.text(v).toLowerCase()).join(' ');
      return hay.includes(searchValue);
    });

    const renderRecordButton = (record) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.style.display = 'grid';
      btn.style.gap = '4px';
      btn.style.width = '100%';
      btn.style.textAlign = 'left';
      btn.style.justifyContent = 'start';
      const scopeBits = [];
      const scopeState = linkPickerScopeState(record);
      if (scopeState === 'active_scope') scopeBits.push('current scope');
      else if (scopeState === 'outside_scope') scopeBits.push('outside scope');
      else scopeBits.push('unscoped');
      if (core.text(record.subcategory_value)) scopeBits.push(prettyLabel(record.subcategory_value));
      btn.innerHTML = `<span>${core.text(record.label) || core.text(record.id)}</span><span class="mini-note">${core.text(record.id)} · ${core.text(record.kind)} · ${core.text(record.status || 'draft')} · ${scopeBits.join(' · ')}</span>${core.text(record.summary) ? `<span class="mini-note">${core.text(record.summary)}</span>` : ''}`;
      btn.addEventListener('click', () => {
        rememberRecentLinkRecord(record);
        activeLinkPicker?.onPick?.(record);
        closeLinkPicker();
      });
      return btn;
    };

    if (currentValue) {
      const currentCard = document.createElement('div');
      currentCard.className = 'panel';
      currentCard.style.padding = '10px';
      currentCard.style.background = 'rgba(255,255,255,0.02)';
      currentCard.style.border = '1px solid rgba(255,255,255,0.06)';
      const matched = (activeLinkPicker?.records || []).find(item => core.text(item.id) === currentValue);
      currentCard.innerHTML = `<div class="stat-title">Currently linked</div><div class="mini-note">${matched ? `${core.text(matched.label)} · ${core.text(matched.id)} · ${core.text(matched.kind)}` : currentValue}</div>`;
      host.appendChild(currentCard);
    }

    const summary = document.createElement('div');
    summary.className = 'mini-note';
    summary.textContent = `${Number(records.length)} result${records.length === 1 ? '' : 's'} · kind ${core.text(activeLinkPicker?.filters?.kind) || 'all'} · scope ${prettyLabel(core.text(activeLinkPicker?.filters?.scope || 'all'))}`;
    host.appendChild(summary);

    const recentIds = new Set((forgeState().recentLinkSelections || []).map(item => core.text(item.id)));
    const recentRecords = records.filter(item => recentIds.has(core.text(item.id)));
    if (recentRecords.length) {
      const heading = document.createElement('div');
      heading.className = 'stat-title';
      heading.textContent = 'Recent records';
      host.appendChild(heading);
      recentRecords.slice(0, 6).forEach(record => host.appendChild(renderRecordButton(record)));
    }

    const grouped = {};
    records.forEach(record => {
      const id = core.text(record.id);
      if (recentIds.has(id)) return;
      const kind = core.text(record.kind || 'record');
      grouped[kind] = grouped[kind] || [];
      grouped[kind].push(record);
    });

    const groupKeys = Object.keys(grouped).sort();
    if (!recentRecords.length && !groupKeys.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'No matching records yet.';
      host.appendChild(empty);
      return;
    }

    groupKeys.forEach(kind => {
      const heading = document.createElement('div');
      heading.className = 'stat-title';
      heading.style.marginTop = recentRecords.length ? '10px' : '0';
      heading.textContent = `${prettyLabel(kind)} records`;
      host.appendChild(heading);
      grouped[kind].forEach(record => host.appendChild(renderRecordButton(record)));
    });
  }

  async function refreshLinkPickerResults(force = false) {
    if (!activeLinkPicker) return;
    if (force) {
      for (const kind of (activeLinkPicker.targetKinds || [])) {
        if (forgeState().recordsByKind) delete forgeState().recordsByKind[kind];
      }
    }
    activeLinkPicker.records = await combinedLinkRecords(activeLinkPicker.targetKinds || []);
    populateLinkPickerFilterOptions();
    renderLinkPickerResults();
  }

  function buildScopedDraftSeedPayload(kind = '', seedPayload = {}) {
    const payload = deepClone(seedPayload && typeof seedPayload === 'object' ? seedPayload : {});
    if (!payload.links || typeof payload.links !== 'object') payload.links = {};
    if (!payload.links.scope || typeof payload.links.scope !== 'object') payload.links.scope = {};
    const targetScope = templatePayload(kind)?.json_template_payload?.links?.scope && typeof templatePayload(kind).json_template_payload.links.scope === 'object'
      ? templatePayload(kind).json_template_payload.links.scope
      : {};
    const hostScope = currentPayload()?.links?.scope && typeof currentPayload().links.scope === 'object' ? currentPayload().links.scope : {};
    const active = activeScope() || {};
    const sourceKind = core.text(active?.source_kind);
    const sourceId = core.text(active?.source_id);
    const genericMap = {
      universe_id: core.text(active?.universe_id || hostScope?.universe_id),
      world_id: core.text(active?.world_id || hostScope?.world_id),
      region_id: core.text(active?.region_id || hostScope?.region_id),
      city_id: core.text(active?.city_id || hostScope?.city_id),
      current_world_id: core.text(active?.world_id || hostScope?.world_id),
      current_region_id: core.text(active?.region_id || hostScope?.region_id),
      current_city_id: core.text(active?.city_id || hostScope?.city_id),
      current_location_id: sourceKind === 'location' ? sourceId : '',
      location_id: sourceKind === 'location' ? sourceId : '',
      base_location_id: sourceKind === 'location' ? sourceId : '',
      parent_location_id: sourceKind === 'location' ? sourceId : '',
      parent_organization_id: sourceKind === 'organization' ? sourceId : '',
    };
    Object.entries(hostScope).forEach(([slot, value]) => {
      if (core.text(value) && !core.text(payload.links.scope?.[slot])) payload.links.scope[slot] = core.text(value);
    });
    Object.keys(targetScope || {}).forEach(slot => {
      const nextValue = core.text(payload.links.scope?.[slot] || hostScope?.[slot] || genericMap[slot]);
      if (nextValue && !core.text(payload.links.scope?.[slot])) payload.links.scope[slot] = nextValue;
    });
    applyActiveScopeToPayload(kind, payload);
    if (!payload.meta || typeof payload.meta !== 'object') payload.meta = {};
    if (!core.text(payload.meta.status)) payload.meta.status = 'draft_stub';
    return payload;
  }

  async function createScopedStub(kind = '', label = '', seedPayload = {}) {
    const cleanKind = core.text(kind);
    const cleanLabel = core.text(label);
    if (!cleanKind || !cleanLabel) throw new Error('kind and label are required for stub creation.');
    const payload = buildScopedDraftSeedPayload(cleanKind, seedPayload);
    const data = await core.postForm('/api/roleplay/v2/builders/create-stub', {
      kind: cleanKind,
      label: cleanLabel,
      source_container_id: core.text(core.$('roleplay-v2-project-select')?.value),
      payload_json: JSON.stringify(payload || {}),
    });
    if (forgeState().recordsByKind) delete forgeState().recordsByKind[cleanKind];
    if (data.sqlite_overview) {
      forgeState().sqliteBackbone = forgeState().sqliteBackbone || {};
      forgeState().sqliteBackbone.overview = data.sqlite_overview;
    }
    return data;
  }

  async function createStubFromLinkPicker() {
    if (!activeLinkPicker || !activeLinkPicker.allowStub || !(activeLinkPicker.targetKinds || []).length) return;
    const label = core.text(core.$('roleplay-v2-link-picker-search')?.value);
    if (!label) throw new Error('Enter a label in the search field first.');
    const kind = activeLinkPicker.targetKinds[0];
    const data = await createScopedStub(kind, label);
    for (const cacheKind of (activeLinkPicker.targetKinds || [])) {
      if (forgeState().recordsByKind) delete forgeState().recordsByKind[cacheKind];
    }
    await refreshLinkPickerResults(true);
    activeLinkPicker?.onPick?.(data.record || {});
    const sqliteNote = data.sqlite_sync ? ` SQLite ${Number(data.sqlite_sync.edge_count || 0)} edges synced.` : '';
    core.setStatus('roleplay-v2-forge-status', `Created ${kind} stub ${core.text(data.record?.id)}.${sqliteNote}`, 'success');
    closeLinkPicker();
  }

  async function openLinkPicker(config) {
    activeLinkPicker = {
      title: core.text(config?.title) || 'Select linked record',
      note: core.text(config?.note) || '',
      targetKinds: Array.isArray(config?.targetKinds) ? config.targetKinds.filter(Boolean) : [],
      allowStub: !!config?.allowStub,
      onPick: typeof config?.onPick === 'function' ? config.onPick : null,
      currentValue: core.text(config?.currentValue || config?.initialQuery),
      filters: {
        kind: '',
        scope: core.text(config?.scopeFilter || (hasActiveScope() ? 'active_scope' : 'all')) || 'all',
        category: '',
        subcategory: '',
        status: '',
      },
      records: [],
    };
    const modal = core.$('roleplay-v2-link-picker-modal');
    if (!modal) return;
    if (core.$('roleplay-v2-link-picker-title')) core.$('roleplay-v2-link-picker-title').textContent = activeLinkPicker.title;
    if (core.$('roleplay-v2-link-picker-note')) core.$('roleplay-v2-link-picker-note').textContent = activeLinkPicker.note || 'Search existing records or create a draft stub when the target does not exist yet.';
    if (core.$('roleplay-v2-link-picker-search')) core.$('roleplay-v2-link-picker-search').value = core.text(config?.initialQuery);
    core.$('roleplay-v2-link-picker-create-stub')?.classList.toggle('hidden', !activeLinkPicker.allowStub || activeLinkPicker.targetKinds.length !== 1);
    syncLinkPickerFilterControls();
    modal.classList.remove('hidden');
    await refreshLinkPickerResults(false);
    core.$('roleplay-v2-link-picker-search')?.focus();
    renderLinkPickerResults();
  }

  function normalizeLinkValue(rawValue, records) {
    const textValue = core.text(rawValue);
    if (!textValue) return '';
    const exact = (records || []).find(item => core.text(item.id) === textValue || core.text(item.label) === textValue || core.text(item.display_label) === textValue);
    return exact ? core.text(exact.id) : textValue;
  }


  function rememberRecentLinkRecord(record) {
    const id = core.text(record?.id);
    if (!id) return;
    const existing = Array.isArray(forgeState().recentLinkSelections) ? forgeState().recentLinkSelections.slice() : [];
    const compact = existing.filter(item => core.text(item?.id) !== id);
    compact.unshift({
      id,
      kind: core.text(record?.kind),
      label: core.text(record?.label || record?.display_label || record?.id),
      summary: core.text(record?.summary),
      status: core.text(record?.status || 'draft'),
    });
    forgeState().recentLinkSelections = compact.slice(0, 12);
  }

  function fieldHelpText(key, path) {
    const lowerPath = core.text(path).toLowerCase();
    const lower = core.text(key).toLowerCase();
    const hints = {
      'links.scope.universe_id': 'Choose the parent universe record this builder belongs to.',
      'links.scope.world_id': 'Choose the parent world record. Reverse world membership views are derived automatically.',
      'links.scope.region_id': 'Choose the parent region only when this record truly sits at regional scope.',
      'links.scope.city_id': 'Choose the parent city when this record is anchored at settlement level.',
      'links.scope.location_id': 'Use a location link when the record is tied to a specific scene anchor.',
      'links.scope.primary_world_id': 'Use this only when a universe has a primary world anchor in addition to broader related-world links.',
      'links.related.member_character_ids': 'Use this for actual organization members, not just notable faces.',
      'links.related.location_ids': 'Use this for recurring organization-controlled or organization-critical locations beyond the base location.',
      'links.related.anchor_entity_id': 'Use this when the location is explicitly anchored to another record in the graph.',
      'fields.truth_layers.public_cosmology': 'This is what the world at large believes or is taught openly.',
      'fields.truth_layers.hidden_truth': 'This should be materially riskier or more destabilizing than the public layer.',
      'fields.myths_truths.known_myths_vs_truth': 'Write the public myth and the actual truth with enough tension between them to matter.',
      'fields.mythic_hidden_legacy.hidden_legacy': 'This is the local buried truth or inheritance wound underneath the public region story.',
      'fields.rumors_truths.hidden_city_truth': 'This should be the city-level truth that makes the public city story incomplete or dishonest.',
      'fields.scene_utility.scene_use_overview': 'Write this like a runtime handoff note for what the place or scenario is best at doing in play.',
      'fields.public_hidden_truth.hidden_truth': 'This is the dangerous or gated version of the place that should not be public baseline knowledge.',
      'fields.story_roleplay_use.scene_use_overview': 'Describe how this character should feel in live scene use, not just in static lore.',
      'fields.relationships': 'Use structured relationship entries so the social graph stays linkable later.',
      'fields.public_hidden_truth.public_face': 'This is the respectable outer story the organization uses to justify itself.',
      'fields.public_hidden_truth.hidden_truth': 'This should contain the institutional contradiction or dangerous private reality under the public face.',
      'fields.function_effects_use.costs': 'Costs should feel narratively meaningful, not like a tiny balancing note.',
      'fields.function_effects.effect_summary': 'Write the method effect in clear scene language first, then deepen it elsewhere.',
      'fields.activation_procedure.activation': 'Describe how the method actually starts in play, not just abstractly.',
      'fields.trigger_cadence_onset.trigger': 'Name what sets the system off in-world, not just a vague condition.',
      'fields.trigger_cadence_onset.cadence': 'Write cadence so future runtime or timeline tools can reason about it.',
      'fields.public_hidden_versions.hidden_version': 'This should materially change the stakes of the legend, not just add trivia.',
      'fields.premise_objective_stakes.premise': 'Write the playable setup first, not the whole story arc.',
      'fields.opening_state_trigger_beat.opening_beat': 'This should feel like a scene drop-in line, not a broad summary.',
      'fields.calendar_chronology.major_eras': 'Keep eras short and scannable here; deeper nuance can live in notes.',
      'fields.timeline.ages': 'Add age cards with names and transition markers so future timeline tools can use them cleanly.',
      'memory_hints.memory_fragment_candidates': 'These candidates tell the compiler which paths should become retrievable memory fragments later.',
      'meta.status': 'Draft saves softly. Reviewed warns harder. Approved and runtime-ready block unresolved or missing validation issues.',
    };
    if (hints[lowerPath]) return hints[lowerPath];
        if (lowerPath.startsWith('memory_hints.priority.')) return 'Use priority to tell the compiler what should stay hottest in continuity and scene retrieval.';
    if (lower === 'tags' || lower === 'tone_tags') return 'Use short reusable tokens instead of long descriptive phrases.';
    return '';
  }

  function sectionDescription(sectionKey, path) {
    const lower = core.text(sectionKey).toLowerCase();
    const lowerPath = core.text(path).toLowerCase();
    const hints = {
      cosmology: 'Define the big reality structure, public creation story, and hidden origin logic.',
      core_laws: 'These become strong canon guards later, so keep them precise.',
      timeline: 'Use this to anchor ages, transitions, and what history is visible vs buried.',
      world_scope: 'Curated world framing only — the actual reverse world list is derived.',
      travel: 'This should read like runtime-safe travel logic, not vague lore.',
      truth_layers: 'Public cosmology, restricted truth, and hidden truth should be meaningfully distinct.',
      calendar_chronology: 'Treat this like a real world-bible chronology block, not a tiny date note.',
      geography_environment: 'Macro geography should help scene logic, travel logic, and regional differentiation.',
      governance_law_diplomacy: 'This should explain how power actually behaves in the setting.',
      society_institutions: 'Use this for lived daily texture, not only elite structures.',
      faith_magic_craft: 'Clarify access, taboo, and institutional control — not just vibes.',
      travel_access_hazards: 'Travel, access, and danger should work together as one runtime layer.',
      peoples_species_creatures: 'Use this to define who inhabits the world and how they relate.',
      economy_language: 'Trade and language shape scene texture more than people expect.',
      myths_truths: 'Keep public world story clearly separate from hidden world truth.',
      placement_scope: 'Keep graph placement clean and minimal; reverse views are derived automatically.',
      governance_ruling_power: 'Focus on ruling authority, structure, and who can actually enforce decisions.',
      geography_places: 'Notable places should help future city and location builders connect cleanly.',
      travel_access_security: 'This is local movement pressure — routes, gates, risk, and watched entry.',
      politics_law_diplomacy: 'Regional law should feel distinct from world law and reveal local tension.',
      society_culture_education: 'Regional culture should affect speech, behavior, and pressure in scenes.',
      mythic_hidden_legacy: 'Keep the public story readable while preserving the buried regional truth.',
      governance_control: 'This is city-level power: who actually runs the place, who watches it, and how pressure is enforced.',
      layout_districts: 'Treat districts and notable areas as playable social terrain, not just map flavor.',
      access_safety_restrictions: 'Use this to define how visitors move, where risk lives, and what parts of the city are watched.',
      rumors_truths: 'Public city story and hidden city truth should create real scene tension when they collide.',
      access_entry: 'Write this like live scene access logic: who gets in, how, and what happens if they should not.',
      spatial_layout: 'Locations should read like scene geometry, not just lore summary.',
      rules_behavior_logic: 'This is the local social rule layer: what you can do here, say here, and get punished for here.',
      goals_desire_fear_wounds: 'This is the emotional engine of the character. It should drive runtime behavior.',
      personality_behavior_speech: 'Keep this behaviorally specific enough that replies feel recognizable across sessions.',
      relationships: 'Relationship rows should hold real scene-driving tension, not vague biography notes.',
      leadership_structure: 'Make the command shape legible enough that character and power dynamics can plug into it later.',
      beliefs_doctrine_mission: 'This should explain what the organization believes, wants, and uses to justify itself.',
      membership_recruitment: 'Recruitment and punishment rules are where the group starts feeling real.',
      resources_assets_territory: 'Use this to show how the group survives materially and how far its power really reaches.',
      function_effects_use: 'Effects, activation, and costs should work like a real scene-facing method contract.',
      law_safety_restriction: 'Keep legality, taboo, and who polices the object or method very explicit.',
      risks_costs_consequences: 'This is where the ritual or object stops being cool and starts becoming narratively expensive.',
      activation_procedure: 'Use this to describe how the action unfolds step by step in live play.',
      trigger_cadence_onset: 'This is the timing engine for the cycle or condition — what starts it, how often, and under what pressure.',
      stages_progression: 'Use stages like a real escalation model so the system can shape scenes over time.',
      effects_outcomes: 'Describe how the system changes bodies, minds, social space, or metaphysical pressure.',
      safeguards_resistance_management: 'This is the containment and relief layer — how the setting copes with the system.',
      sentience_social_pattern: 'Creature intelligence and bonding rules should be scene-useful, not vague bestiary notes.',
      danger_threat_utility: 'Make danger and usefulness both legible so the creature can matter in different scene types.',
      role_in_world_society_scene: 'This is where the creature becomes part of travel, omen logic, or everyday world texture.',
      public_hidden_versions: 'Legends need a meaningful split between the version people repeat and the version power hides.',
      consequences_stakes: 'Write why the legend matters now, not just what it says.',
      premise_objective_stakes: 'Scenarios should read like playable pressure packets, not general story summaries.',
      opening_state_trigger_beat: 'This is the live scene entry point — the room condition right before play begins.',
      constraints_rules_boundaries: 'Use this to protect scenario tone and prevent runtime from blowing past the intended scene frame.',
      scene_notes_gm_narrator: 'These notes should help runtime behave like a facilitator, not just a text generator.',
      requirements_conditions: 'Requirements should explain what the method needs before it can even begin.',
      public_hidden_truth: 'Public notes should stand on their own while hidden truth stays more dangerous or gated.',
      public_hidden_versions: 'Public and hidden versions should not be small wording tweaks — they should meaningfully diverge.',
    };
    if (hints[lower]) return hints[lower];
    if (lowerPath.includes('memory_hints')) return 'Use this block to tell the compiler what should stay hot in long-term narrative memory.';
    return '';
  }

  function isLongTextField(key, path = '') {
    const lower = core.text(key).toLowerCase();
    const lowerPath = core.text(path).toLowerCase();
    if (lowerPath.includes('memory_fragment_candidates') && lower === 'notes') return true;
    return ['summary', 'story', 'truth', 'overview', 'identity', 'geography', 'diplomacy', 'society', 'culture', 'presence', 'stakes', 'premise', 'objective', 'atmosphere', 'beliefs', 'effects', 'risks', 'traditions', 'customs', 'superstitions', 'history', 'legacy', 'notes', 'constraints', 'pressure', 'goal', 'function', 'role', 'consequences', 'management', 'safeguards', 'significance', 'reputation', 'burden', 'profile'].some(token => lower.includes(token));
  }

  function rowsForField(key, path = '') {
    const lower = core.text(key).toLowerCase();
    const lowerPath = core.text(path).toLowerCase();
    if (lowerPath.includes('memory_hints.runtime_guard_notes')) return 5;
    if (lowerPath.includes('memory_hints.reveal_gating.notes')) return 4;
    if (['public_version', 'hidden_version', 'public_story', 'hidden_truth', 'public_cosmology', 'restricted_truth', 'consequences_if_true', 'contradiction_handling_notes', 'public_region_story', 'hidden_world_truth', 'known_myths_vs_truth'].includes(lower)) return 7;
    if (['summary', 'overview', 'story', 'truth', 'geography', 'diplomacy', 'society', 'culture', 'stakes', 'premise', 'objective', 'atmosphere'].some(token => lower.includes(token))) return 6;
    if (['notes', 'traditions', 'variants', 'contradictions', 'superstitions', 'customs', 'legacy', 'management', 'safeguards'].some(token => lower.includes(token))) return 4;
    return 3;
  }

  function isWideField(key, path = '') {
    const lower = core.text(key).toLowerCase();
    const lowerPath = core.text(path).toLowerCase();
    if (isLinkField(path, key)) return true;
    if (isLongTextField(key, path)) return true;
    if (lowerPath.includes('memory_hints')) return true;
    return ['public_', 'hidden_', 'story', 'truth', 'overview', 'notes', 'constraints', 'pressure', 'consequences', 'role', 'significance'].some(token => lower.includes(token));
  }

  function simpleArrayShape(key, value, path = '') {
    const lower = core.text(key).toLowerCase();
    if (lower === 'ages') {
      return { name: '', summary: '', start_marker: '', end_marker: '', status: '', notes: '' };
    }
    if (lower === 'memory_fragment_candidates' || core.text(path).includes('memory_fragment_candidates')) {
      return { path: '', fragment_type: '', visibility: '', priority: 'high', notes: '' };
    }
    if (Array.isArray(value) && value.length && value.every(item => item && typeof item === 'object')) return value[0];
    return null;
  }

  function createSelect(options, currentValue, onChange, includeBlank = false) {
    const select = document.createElement('select');
    if (includeBlank) {
      const blank = document.createElement('option');
      blank.value = '';
      blank.textContent = '—';
      select.appendChild(blank);
    }
    (options || []).forEach(option => {
      const el = document.createElement('option');
      el.value = option;
      el.textContent = option;
      if (String(currentValue || '') === option) el.selected = true;
      select.appendChild(el);
    });
    select.addEventListener('change', () => onChange(select.value));
    return select;
  }

  function createPrimitiveListWidget(key, value, path, applyChange) {
    const wrap = document.createElement('div');
    wrap.style.display = 'grid';
    wrap.style.gap = '8px';
    wrap.style.gridColumn = '1 / -1';
    const label = document.createElement('label');
    label.textContent = prettyLabel(key);
    wrap.appendChild(label);
    const items = Array.isArray(value) ? value.slice() : [];
    const list = document.createElement('div');
    list.style.display = 'grid';
    list.style.gap = '8px';
    wrap.appendChild(list);
    const targetKinds = isLinkField(path, key) ? targetKindsForLinkField(key) : [];

    const renderItems = () => {
      list.innerHTML = '';
      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'mini-note';
        empty.textContent = targetKinds.length ? `No linked ${targetKinds.join('/')} records yet.` : 'No entries yet.';
        list.appendChild(empty);
      }
      items.forEach((item, index) => {
        const row = document.createElement('div');
        row.style.display = 'grid';
        row.style.gridTemplateColumns = targetKinds.length ? (targetKinds.length === 1 ? 'minmax(0, 1fr) auto auto auto' : 'minmax(0, 1fr) auto auto') : 'minmax(0, 1fr) auto';
        row.style.gap = '8px';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = targetKinds.length ? `Link ${targetKinds.join('/')} record by ID or label` : 'Add entry';
        input.value = String(item || '');
        input.addEventListener('input', () => {
          items[index] = input.value;
          applyChange(items.filter(v => core.text(v)));
        });
        input.addEventListener('change', async () => {
          if (!targetKinds.length) return;
          const records = await combinedLinkRecords(targetKinds);
          items[index] = normalizeLinkValue(input.value, records);
          input.value = items[index];
          applyChange(items.filter(v => core.text(v)));
        });
        row.appendChild(input);

        if (targetKinds.length) {
          const browseBtn = document.createElement('button');
          browseBtn.type = 'button';
          browseBtn.className = 'btn btn-small';
          browseBtn.textContent = 'Browse';
          browseBtn.addEventListener('click', async () => {
            await openLinkPicker({
              title: `Select ${prettyLabel(key)} entry`,
              note: targetKinds.length === 1
                ? `Choose an existing ${targetKinds[0]} record or create a stub if it does not exist yet.`
                : `Choose an existing linked record across ${targetKinds.join(', ')}.`,
              targetKinds,
              allowStub: targetKinds.length === 1,
              initialQuery: input.value,
              currentValue: input.value,
              onPick: (record) => {
                const nextId = core.text(record?.id);
                if (!nextId) return;
                input.value = nextId;
                items[index] = nextId;
                applyChange(items.filter(v => core.text(v)));
              },
            });
          });
          row.appendChild(browseBtn);

          if (targetKinds.length === 1) {
            const stubBtn = document.createElement('button');
            stubBtn.type = 'button';
            stubBtn.className = 'btn btn-small';
            stubBtn.textContent = 'Stub';
            stubBtn.addEventListener('click', async () => {
              const labelValue = core.text(input.value);
              if (!labelValue) return;
              const data = await createScopedStub(targetKinds[0], labelValue);
              const id = core.text(data.record?.id);
              if (forgeState().recordsByKind) delete forgeState().recordsByKind[targetKinds[0]];
              input.value = id;
              items[index] = id;
              applyChange(items.filter(v => core.text(v)));
              await refreshRecordList();
              core.setStatus('roleplay-v2-forge-status', `Created ${targetKinds[0]} stub ${id}.`, 'success');
            });
            row.appendChild(stubBtn);
          }
        }

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-small';
        removeBtn.textContent = 'Remove';
        removeBtn.addEventListener('click', () => {
          items.splice(index, 1);
          applyChange(items.filter(v => core.text(v)));
          renderItems();
        });
        row.appendChild(removeBtn);
        list.appendChild(row);
      });
    };

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-small';
    addBtn.textContent = targetKinds.length ? `Add ${targetKinds.join('/')} link` : 'Add entry';
    addBtn.addEventListener('click', () => {
      items.push('');
      applyChange(items);
      renderItems();
    });
    wrap.appendChild(addBtn);
    renderItems();
    return wrap;
  }

  function createObjectArrayWidget(key, value, path, applyChange) {
    const wrap = document.createElement('div');
    wrap.style.display = 'grid';
    wrap.style.gap = '10px';
    wrap.style.gridColumn = '1 / -1';
    const label = document.createElement('label');
    label.textContent = prettyLabel(key);
    wrap.appendChild(label);
    const helper = document.createElement('div');
    helper.className = 'mini-note';
    if (core.text(key).toLowerCase() === 'ages') helper.textContent = 'Use ages as named timeline cards with summary and markers.';
    if (core.text(key).toLowerCase() === 'memory_fragment_candidates') helper.textContent = 'Each candidate can point at a field path and explain how it should compile into memory.';
    if (helper.textContent) wrap.appendChild(helper);
    const items = Array.isArray(value) ? deepClone(value) : [];
    const shape = simpleArrayShape(key, value, path) || { label: '', notes: '' };
    const list = document.createElement('div');
    list.style.display = 'grid';
    list.style.gap = '10px';
    wrap.appendChild(list);
    const renderItems = () => {
      list.innerHTML = '';
      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'mini-note';
        empty.textContent = 'No structured entries yet.';
        list.appendChild(empty);
      }
      items.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'panel';
        card.style.padding = '12px';
        card.style.background = 'rgba(255,255,255,0.02)';
        card.style.border = '1px solid rgba(255,255,255,0.06)';
        const head = document.createElement('div');
        head.style.display = 'flex';
        head.style.justifyContent = 'space-between';
        head.style.alignItems = 'center';
        const headTitle = document.createElement('div');
        headTitle.className = 'stat-title';
        headTitle.textContent = `${prettyLabel(key)} entry ${index + 1}`;
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-small';
        removeBtn.textContent = 'Remove';
        removeBtn.addEventListener('click', () => {
          items.splice(index, 1);
          applyChange(items);
          renderItems();
        });
        head.appendChild(headTitle);
        head.appendChild(removeBtn);
        card.appendChild(head);
        const grid = document.createElement('div');
        grid.style.display = 'grid';
        grid.style.gap = '10px';
        grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(220px, 1fr))';
        grid.style.marginTop = '10px';
        Object.keys(shape).forEach(fieldKey => {
          const fieldWrap = document.createElement('div');
          fieldWrap.style.display = 'grid';
          fieldWrap.style.gap = '6px';
          const fieldLabel = document.createElement('label');
          fieldLabel.textContent = prettyLabel(fieldKey);
          const fieldValue = item?.[fieldKey] ?? shape[fieldKey] ?? '';
          const fieldPath = `${path}.${index}.${fieldKey}`;
          const options = optionValuesForField(fieldKey, fieldPath);
          let fieldInput;
          if (options) {
            fieldInput = createSelect(options, fieldValue, next => {
              items[index] = { ...(items[index] || {}), [fieldKey]: next };
              applyChange(items);
            }, true);
          } else {
            const useTextarea = isLongTextField(fieldKey, fieldPath);
            fieldInput = useTextarea ? document.createElement('textarea') : document.createElement('input');
            if (useTextarea) {
              fieldInput.rows = rowsForField(fieldKey, fieldPath);
              fieldInput.value = String(fieldValue || '');
            } else {
              fieldInput.type = 'text';
              fieldInput.value = String(fieldValue || '');
            }
            fieldInput.addEventListener('input', () => {
              items[index] = { ...(items[index] || {}), [fieldKey]: fieldInput.value };
              applyChange(items);
            });
          }
          if (isWideField(fieldKey, fieldPath)) fieldWrap.style.gridColumn = '1 / -1';
          fieldWrap.appendChild(fieldLabel);
          fieldWrap.appendChild(fieldInput);
          grid.appendChild(fieldWrap);
        });
        card.appendChild(grid);
        list.appendChild(card);
      });
    };
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-small';
    addBtn.textContent = core.text(key).toLowerCase() === 'ages' ? 'Add age card' : 'Add structured entry';
    addBtn.addEventListener('click', () => {
      items.push(deepClone(shape));
      applyChange(items);
      renderItems();
    });
    wrap.appendChild(addBtn);
    renderItems();
    return wrap;
  }

  function createLinkInputWidget(key, value, path, applyChange) {
    const wrap = document.createElement('div');
    wrap.style.display = 'grid';
    wrap.style.gap = '6px';
    wrap.style.gridColumn = '1 / -1';
    const label = document.createElement('label');
    label.textContent = prettyLabel(key);
    wrap.appendChild(label);
    const targetKinds = targetKindsForLinkField(key);
    const helper = document.createElement('div');
    helper.className = 'mini-note';
    helper.textContent = targetKinds.length ? `Browse ${targetKinds.join('/')} records, search by label or ID, or create a draft stub inline when the target is not built yet.` : 'Store a linked record ID here.';
    wrap.appendChild(helper);

    const row = document.createElement('div');
    row.style.display = 'grid';
    row.style.gridTemplateColumns = targetKinds.length ? (targetKinds.length === 1 ? 'minmax(0, 1fr) auto auto' : 'minmax(0, 1fr) auto') : 'minmax(0, 1fr)';
    row.style.gap = '8px';

    const input = document.createElement('input');
    input.type = 'text';
    input.value = String(value || '');
    input.placeholder = targetKinds.length ? `Select ${targetKinds.join('/')} record` : 'Enter linked record id';
    input.addEventListener('input', () => applyChange(input.value));
    input.addEventListener('change', async () => {
      if (!targetKinds.length) return;
      const records = await combinedLinkRecords(targetKinds);
      const nextValue = normalizeLinkValue(input.value, records);
      input.value = nextValue;
      applyChange(nextValue);
    });
    row.appendChild(input);

    if (targetKinds.length) {
      const browseBtn = document.createElement('button');
      browseBtn.type = 'button';
      browseBtn.className = 'btn btn-small';
      browseBtn.textContent = 'Browse';
      browseBtn.addEventListener('click', async () => {
        await openLinkPicker({
          title: `Select ${prettyLabel(key)}`,
          note: targetKinds.length === 1
            ? `Choose an existing ${targetKinds[0]} record or create a stub if it does not exist yet.`
            : `Choose a linked record across ${targetKinds.join(', ')}.`,
          targetKinds,
          allowStub: targetKinds.length === 1,
          initialQuery: input.value,
          currentValue: input.value,
          onPick: (record) => {
            const nextId = core.text(record?.id);
            if (!nextId) return;
            input.value = nextId;
            applyChange(nextId);
          },
        });
      });
      row.appendChild(browseBtn);

      if (targetKinds.length === 1) {
        const createBtn = document.createElement('button');
        createBtn.type = 'button';
        createBtn.className = 'btn btn-small';
        createBtn.textContent = 'Create stub';
        createBtn.addEventListener('click', async () => {
          const labelValue = core.text(input.value);
          if (!labelValue) throw new Error('Enter a label or record id first.');
          const data = await createScopedStub(targetKinds[0], labelValue);
          const nextId = core.text(data.record?.id);
          if (forgeState().recordsByKind) delete forgeState().recordsByKind[targetKinds[0]];
          input.value = nextId;
          applyChange(nextId);
          await refreshRecordList();
          core.setStatus('roleplay-v2-forge-status', `Created ${targetKinds[0]} stub ${nextId}.`, 'success');
        });
        row.appendChild(createBtn);
      }
    }

    wrap.appendChild(row);
    return wrap;
  }

  function inputForValue(key, value, path) {
    const wrap = document.createElement('div');
    wrap.style.display = 'grid';
    wrap.style.gap = '6px';
    if (isWideField(key, path)) wrap.style.gridColumn = '1 / -1';
    const label = document.createElement('label');
    label.textContent = prettyLabel(key);
    wrap.appendChild(label);
    const helpText = fieldHelpText(key, path);
    if (helpText) {
      const help = document.createElement('div');
      help.className = 'mini-note';
      help.textContent = helpText;
      wrap.appendChild(help);
    }

    const applyChange = (nextValue) => {
      setByPath(currentPayload(), path, nextValue);
      syncJsonEditor();
      updateRecordBadge();
    };

    // Array/link fields such as scene link IDs must stay arrays.
    // Keep this before isLinkField(), otherwise character_ids can be edited as a
    // single string and get stripped/normalised away during save/validation.
    if (Array.isArray(value)) {
      const shape = simpleArrayShape(key, value, path);
      if (shape || (Array.isArray(value) && value.length && value.every(item => item && typeof item === 'object'))) {
        return createObjectArrayWidget(key, value, path, applyChange);
      }
      return createPrimitiveListWidget(key, value, path, applyChange);
    }

    if (isLinkField(path, key)) return createLinkInputWidget(key, value, path, applyChange);

    if (value && typeof value === 'object') {
      const input = document.createElement('textarea');
      input.rows = 6;
      input.style.width = '100%';
      input.value = safeStringify(value);
      input.addEventListener('change', () => {
        try {
          applyChange(JSON.parse(input.value || '{}'));
          input.classList.remove('error');
        } catch (_) {
          input.classList.add('error');
        }
      });
      wrap.appendChild(input);
      return wrap;
    }

    const options = optionValuesForField(key, path);
    if (options) {
      wrap.appendChild(createSelect(options, value, next => applyChange(next), true));
      return wrap;
    }

    let input;
    if (typeof value === 'number') {
      input = document.createElement('input');
      input.type = 'number';
      input.value = String(value);
      input.addEventListener('input', () => applyChange(Number(input.value || 0)));
    } else {
      const useTextarea = isLongTextField(key, path);
      input = useTextarea ? document.createElement('textarea') : document.createElement('input');
      if (useTextarea) {
        input.rows = rowsForField(key, path);
        input.value = String(value || '');
        input.addEventListener('input', () => applyChange(input.value));
      } else {
        input.type = 'text';
        input.value = String(value || '');
        input.addEventListener('input', () => applyChange(input.value));
      }
    }
    wrap.appendChild(input);
    return wrap;
  }

  function isTruthLikeSection(key, value) {
    const lower = core.text(key).toLowerCase();
    if (['truth_layers', 'public_hidden_truth', 'public_hidden_versions', 'myths_truths', 'mythic_hidden_legacy'].includes(lower)) return true;
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const keys = Object.keys(value || {}).map(item => core.text(item).toLowerCase());
    return keys.some(item => item.startsWith('public_')) && (keys.some(item => item.startsWith('hidden_')) || keys.includes('restricted_truth'));
  }

  function renderTruthSection(container, key, value, path, depth) {
    const section = document.createElement('div');
    section.className = 'panel';
    section.style.padding = '14px';
    section.style.background = 'rgba(255,255,255,0.02)';
    section.style.border = '1px solid rgba(255,255,255,0.06)';
    section.style.gridColumn = '1 / -1';
    const title = document.createElement(depth < 1 ? 'h4' : 'div');
    title.textContent = prettyLabel(key);
    title.className = depth < 1 ? '' : 'stat-title';
    section.appendChild(title);
    const descText = sectionDescription(key, path);
    if (descText) {
      const desc = document.createElement('div');
      desc.className = 'mini-note';
      desc.style.marginTop = '4px';
      desc.textContent = descText;
      section.appendChild(desc);
    }
    const truthOrder = ['public_version', 'public_story', 'public_region_story', 'public_world_story', 'public_notes', 'public_cosmology', 'restricted_truth', 'hidden_version', 'hidden_truth', 'hidden_world_truth'];
    const grid = document.createElement('div');
    grid.style.display = 'grid';
    grid.style.gap = '12px';
    grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(280px, 1fr))';
    grid.style.marginTop = '10px';
    truthOrder.forEach(fieldKey => {
      if (!(fieldKey in (value || {}))) return;
      grid.appendChild(inputForValue(fieldKey, value[fieldKey], `${path}.${fieldKey}`));
    });
    Object.keys(value || {}).forEach(fieldKey => {
      if (truthOrder.includes(fieldKey)) return;
      const fieldValue = value[fieldKey];
      if (fieldValue && typeof fieldValue === 'object' && !Array.isArray(fieldValue)) {
        const nested = document.createElement('div');
        nested.style.gridColumn = '1 / -1';
        renderObjectSection(nested, { [fieldKey]: fieldValue }, path, depth + 1);
        grid.appendChild(nested);
      } else {
        grid.appendChild(inputForValue(fieldKey, fieldValue, `${path}.${fieldKey}`));
      }
    });
    section.appendChild(grid);
    container.appendChild(section);
  }

  function renderObjectSection(container, obj, pathPrefix = '', depth = 0) {
    Object.entries(obj || {}).forEach(([key, value]) => {
      const path = pathPrefix ? `${pathPrefix}.${key}` : key;
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        if (isTruthLikeSection(key, value)) {
          renderTruthSection(container, key, value, path, depth);
          return;
        }
        const section = document.createElement('div');
        section.className = 'panel';
        section.style.padding = '14px';
        section.style.background = 'rgba(255,255,255,0.02)';
        section.style.border = '1px solid rgba(255,255,255,0.06)';
        const cleanKey = core.text(key).toLowerCase();
        if (
          depth < 1 ||
          cleanKey.includes('rich_authoring') ||
          cleanKey.includes('scene_utility') ||
          cleanKey.includes('reveal_gating') ||
          cleanKey === 'priority' ||
          path.includes('links.scope') ||
          path.includes('links.related')
        ) {
          section.style.gridColumn = '1 / -1';
        }
        const title = document.createElement(depth < 1 ? 'h4' : 'div');
        title.textContent = prettyLabel(key);
        title.className = depth < 1 ? '' : 'stat-title';
        section.appendChild(title);
        const descText = sectionDescription(key, path);
        if (descText) {
          const desc = document.createElement('div');
          desc.className = 'mini-note';
          desc.style.marginTop = '4px';
          desc.textContent = descText;
          section.appendChild(desc);
        }
        const inner = document.createElement('div');
        inner.style.display = 'grid';
        inner.style.gap = '12px';
        inner.style.gridTemplateColumns = (path.includes('memory_hints.reveal_gating') || path.includes('memory_hints.priority') || path.includes('links.scope') || path.includes('links.related'))
          ? 'repeat(auto-fit, minmax(320px, 1fr))'
          : 'repeat(auto-fit, minmax(260px, 1fr))';
        inner.style.marginTop = '10px';
        renderObjectSection(inner, value, path, depth + 1);
        section.appendChild(inner);
        container.appendChild(section);
      } else {
        container.appendChild(inputForValue(key, value, path));
      }
    });
  }


  function summarizeFilledLinks(links) {
    const scope = links && typeof links === 'object' && links.scope && typeof links.scope === 'object' ? links.scope : {};
    const related = links && typeof links === 'object' && links.related && typeof links.related === 'object' ? links.related : {};
    const isFilled = value => Array.isArray(value) ? value.length > 0 : !!core.text(value);
    const filledScope = Object.entries(scope).filter(([, value]) => isFilled(value));
    const filledRelated = Object.entries(related).filter(([, value]) => isFilled(value));
    return {
      scopeKeys: Object.keys(scope),
      relatedKeys: Object.keys(related),
      filledScope,
      filledRelated,
    };
  }

  function buildContractPreviewPayload(kind, summary, spec, validation) {
    return {
      builder: kind,
      availability: availabilityLabel(summary?.implementation_status),
      primary_label_key: core.text(spec?.primary_label_key) || 'label',
      builder_sections: spec?.builder_sections || [],
      canonical_fields: spec?.canonical_fields || [],
      authoring_field_paths: spec?.authoring_field_paths || [],
      link_ownership: spec?.link_ownership || {},
      edge_sections: spec?.edge_sections || [],
      derived_reverse_links: spec?.derived_reverse_links || [],
      runtime_surface: spec?.runtime_surface || {},
      memory_compile: spec?.memory_compile || {},
      validation: validation || null,
    };
  }

  function renderForm(validation) {
    const root = core.$('roleplay-v2-forge-form-root');
    if (!root) return;
    root.innerHTML = '';
    root.style.gridTemplateColumns = 'repeat(auto-fit, minmax(320px, 1fr))';
    root.style.alignContent = 'start';
    const payload = currentPayload();

    if (validation && (validation.missing_paths?.length || validation.link_issues?.length)) {
      const warn = document.createElement('div');
      warn.className = `status ${validation.severity === 'error' ? 'error' : 'warning'}`;
      const parts = [];
      if (validation.missing_paths?.length) parts.push(`Missing required paths: ${validation.missing_paths.join(', ')}`);
      if (validation.link_issues?.length) parts.push(`Link issues: ${validation.link_issues.map(issue => `${issue.slot} → ${issue.value} (${issue.status})`).join(', ')}`);
      warn.textContent = parts.join(' | ');
      warn.style.gridColumn = '1 / -1';
      root.appendChild(warn);
    }

    const top = document.createElement('div');
    top.className = 'panel';
    top.style.padding = '14px';
    top.style.background = 'rgba(255,255,255,0.02)';
    top.style.border = '1px solid rgba(255,255,255,0.06)';
    const title = document.createElement('div');
    title.className = 'stat-title';
    title.textContent = 'Record envelope';
    top.appendChild(title);
    const note = document.createElement('div');
    note.className = 'mini-note';
    note.style.marginTop = '4px';
    note.textContent = 'This envelope should now mirror the canonical saved builder record shape.';
    top.appendChild(note);
    const topGrid = document.createElement('div');
    topGrid.style.display = 'grid';
    topGrid.style.gap = '12px';
    topGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(240px, 1fr))';
    topGrid.style.marginTop = '10px';
    ['label', 'display_label', 'summary', 'source_container_id', 'canon_status', 'visibility', 'tags', 'tone_tags'].forEach(key => {
      topGrid.appendChild(inputForValue(key, payload[key], key));
    });
    topGrid.appendChild(inputForValue('status', payload?.meta?.status || 'draft', 'meta.status'));
    top.appendChild(topGrid);
    top.style.gridColumn = '1 / -1';
    root.appendChild(top);

    if (payload.links && typeof payload.links === 'object') {
      const linksPanel = document.createElement('div');
      linksPanel.className = 'panel';
      linksPanel.style.padding = '14px';
      linksPanel.style.background = 'rgba(255,255,255,0.02)';
      linksPanel.style.border = '1px solid rgba(255,255,255,0.06)';
      const linksTitle = document.createElement('div');
      linksTitle.className = 'stat-title';
      linksTitle.textContent = 'Links / graph placement';
      linksPanel.appendChild(linksTitle);
      const linksNote = document.createElement('div');
      linksNote.className = 'mini-note';
      linksNote.style.marginTop = '4px';
      linksNote.textContent = 'Scope links place the record in the graph. Related links connect it to other records. Reverse links are derived automatically.';
      linksPanel.appendChild(linksNote);

      const linksGrid = document.createElement('div');
      linksGrid.style.display = 'grid';
      linksGrid.style.gap = '12px';
      linksGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(320px, 1fr))';
      linksGrid.style.marginTop = '10px';

      if (payload.links.scope && typeof payload.links.scope === 'object') {
        const scopePanel = document.createElement('div');
        scopePanel.className = 'panel';
        scopePanel.style.padding = '12px';
        scopePanel.style.background = 'rgba(255,255,255,0.02)';
        scopePanel.style.border = '1px solid rgba(255,255,255,0.06)';
        const scopeTitle = document.createElement('div');
        scopeTitle.className = 'stat-title';
        scopeTitle.textContent = 'Scope';
        scopePanel.appendChild(scopeTitle);
        const scopeGrid = document.createElement('div');
        scopeGrid.style.display = 'grid';
        scopeGrid.style.gap = '12px';
        scopeGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(320px, 1fr))';
        scopeGrid.style.marginTop = '10px';
        renderObjectSection(scopeGrid, payload.links.scope, 'links.scope', 1);
        scopePanel.appendChild(scopeGrid);
        scopePanel.style.gridColumn = '1 / -1';
        linksGrid.appendChild(scopePanel);
      }

      if (payload.links.related && typeof payload.links.related === 'object') {
        const relatedPanel = document.createElement('div');
        relatedPanel.className = 'panel';
        relatedPanel.style.padding = '12px';
        relatedPanel.style.background = 'rgba(255,255,255,0.02)';
        relatedPanel.style.border = '1px solid rgba(255,255,255,0.06)';
        relatedPanel.style.gridColumn = '1 / -1';
        const relatedTitle = document.createElement('div');
        relatedTitle.className = 'stat-title';
        relatedTitle.textContent = 'Related';
        relatedPanel.appendChild(relatedTitle);
        const relatedGrid = document.createElement('div');
        relatedGrid.style.display = 'grid';
        relatedGrid.style.gap = '12px';
        relatedGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(220px, 1fr))';
        relatedGrid.style.marginTop = '10px';
        renderObjectSection(relatedGrid, payload.links.related, 'links.related', 1);
        relatedPanel.appendChild(relatedGrid);
        linksGrid.appendChild(relatedPanel);
      }

      if (payload.links.reverse_links) {
        const reverseNote = document.createElement('div');
        reverseNote.className = 'mini-note';
        reverseNote.style.gridColumn = '1 / -1';
        reverseNote.textContent = `Reverse links are derived automatically · strategy: ${core.text(payload.links.reverse_links?.strategy) || 'derived'}`;
        linksGrid.appendChild(reverseNote);
      }

      linksPanel.appendChild(linksGrid);
      linksPanel.style.gridColumn = '1 / -1';
      root.appendChild(linksPanel);
    }

    if (payload.fields && typeof payload.fields === 'object') renderObjectSection(root, payload.fields, 'fields', 0);

    if (payload.memory_hints && typeof payload.memory_hints === 'object') {
      const memPanel = document.createElement('div');
      memPanel.className = 'panel';
      memPanel.style.padding = '14px';
      memPanel.style.background = 'rgba(255,255,255,0.02)';
      memPanel.style.border = '1px solid rgba(255,255,255,0.06)';
      const memTitle = document.createElement('div');
      memTitle.className = 'stat-title';
      memTitle.textContent = 'Memory hints';
      memPanel.appendChild(memTitle);
      const memNote = document.createElement('div');
      memNote.className = 'mini-note';
      memNote.style.marginTop = '4px';
      memNote.textContent = 'Use this section to promote retrieval behavior, callbacks, and reveal gating without replacing canonical world or character facts.';
      memPanel.appendChild(memNote);
      const memGrid = document.createElement('div');
      memGrid.style.display = 'grid';
      memGrid.style.gap = '12px';
      memGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(240px, 1fr))';
      memGrid.style.marginTop = '10px';
      renderObjectSection(memGrid, payload.memory_hints, 'memory_hints', 1);
      memPanel.appendChild(memGrid);
      memPanel.style.gridColumn = '1 / -1';
      root.appendChild(memPanel);
    }
  }


  async function refreshMemoryPreview(recordId = '') {
    const cleanRecordId = core.text(recordId || currentPayload()?.id);
    const inspector = core.$('roleplay-v2-forge-inspector');
    if (!inspector) return null;
    if (!cleanRecordId) return null;
    try {
      const data = await core.getJson(`/api/roleplay/v2/memory/by-record?record_id=${encodeURIComponent(cleanRecordId)}&limit=6`);
      forgeState().memoryPreview = data;
      return data;
    } catch (err) {
      forgeState().memoryPreview = { error: err.message || String(err) };
      return forgeState().memoryPreview;
    }
  }

  function renderSelectedBuilder(validation = null) {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const summary = builderSummary(kind);
    const template = templatePayload(kind);
    const spec = entitySpec(kind);
    const hierarchy = hierarchyEntry(kind);
    const title = core.$('roleplay-v2-forge-builder-title');
    const badge = core.$('roleplay-v2-forge-builder-kind-badge');
    const status = core.$('roleplay-v2-forge-builder-status');
    const mdEditor = core.$('roleplay-v2-forge-md-editor');
    const contractPreview = core.$('roleplay-v2-forge-contract-preview');
    const inspector = core.$('roleplay-v2-forge-inspector');
    const payload = currentPayload();
    const linkSummary = summarizeFilledLinks(payload?.links || {});
    if (title) title.textContent = `${core.text(hierarchy?.display_name) || `${kind[0].toUpperCase()}${kind.slice(1)}`} builder`;
    if (badge) badge.textContent = availabilityLabel(summary?.implementation_status);
    if (status) status.textContent = validation?.missing_paths?.length || validation?.link_issues?.length
      ? `Loaded ${core.text(hierarchy?.display_name || kind)}. ${validation?.missing_paths?.length || 0} required-path gaps · ${validation?.link_issues?.length || 0} link issues.`
      : `Loaded ${core.text(hierarchy?.display_name || kind)} editor shell with hierarchy-aware scope rules.`;
    if (mdEditor) mdEditor.value = core.text(template?.md_template_text) || '';
    if (contractPreview) {
      contractPreview.textContent = JSON.stringify(buildContractPreviewPayload(kind, summary, spec, validation), null, 2);
    }
    renderScopeBar();
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    if (inspector) {
      const shared = forgeState().sharedContracts || {};
      const memoryPreview = forgeState().memoryPreview || null;
      const graph = payload?.graph && typeof payload.graph === 'object' ? payload.graph : {};
      const edgeSummary = graph?.edge_summary && typeof graph.edge_summary === 'object' ? graph.edge_summary : {};
      const idPolicy = graph?.id_policy && typeof graph.id_policy === 'object' ? graph.id_policy : {};
      const normalization = forgeState().lastNormalization || null;
      const currentScope = currentScopeRows(hierarchy, payload);
      const lines = [
        `Builder · ${kind}`,
        `Display name · ${core.text(hierarchy?.display_name) || prettyLabel(kind)}`,
        `Entry lane · ${core.text(hierarchy?.entry_label) || `Build a ${prettyLabel(kind)}`}`,
        `Lane family · ${core.text(hierarchy?.lane) || 'general'}`,
        `Scope tier · ${core.text(hierarchy?.scope_tier) || 'n/a'}`,
        `Primary parent · ${core.text(hierarchy?.primary_parent_kind) || 'none'}`,
        `Allowed parents · ${(hierarchy?.parent_kinds || []).map(prettyLabel).join(', ') || 'none'}`,
        `Auto-fill scope links · ${(hierarchy?.auto_scope_paths || []).join(', ') || 'none'}`,
        `Recommended children · ${(hierarchy?.recommended_child_kinds || []).map(prettyLabel).join(', ') || 'none'}`,
        hierarchy?.subcategory ? `Sub-category rule · ${core.text(hierarchy.subcategory.label)} → ${core.text(hierarchy.subcategory.field_path)} (${Number(hierarchy.subcategory.values?.length || 0)} values)` : 'Sub-category rule · none',
        currentScope.length ? `Current scope path · ${currentScope.map(row => `${prettyLabel(row.slot)}=${row.value}`).join(' · ')}` : 'Current scope path · none',
        `Availability · ${availabilityLabel(summary?.implementation_status)}`,
        `Record id · ${core.text(payload?.id) || 'unsaved'}`,
        `Label · ${core.text(payload?.label) || 'missing'}`,
        `Source container · ${core.text(payload?.source_container_id) || 'none'}`,
        `ID strategy · ${core.text(idPolicy?.strategy) || core.text(shared.record?.id_policy?.strategy) || 'n/a'}`,
        `Stable ID · ${core.text(idPolicy?.stable_id) || core.text(payload?.id) || 'unsaved'}`,
        `Slug basis · ${core.text(idPolicy?.slug) || 'n/a'}`,
        `Primary label key · ${core.text(spec?.primary_label_key) || 'label'}`,
        `Builder sections · ${(spec?.builder_sections || []).length}`,
        `Canonical field count · ${(spec?.canonical_fields || []).length}`,
        `Authoring path count · ${(spec?.authoring_field_paths || []).length}`,
        `Edge sections · ${(spec?.edge_sections || []).join(', ') || 'none'}`,
        `Runtime surfaces · ${Object.keys(spec?.runtime_surface || {}).join(', ') || 'none'}`,
        `Graph edges · ${Number(edgeSummary?.edge_count || 0)}`,
        `Incoming edges · ${Number(edgeSummary?.reverse_edge_count || 0)}`,
        `Edge families · ${Object.entries(edgeSummary?.by_family || {}).map(([name, count]) => `${name}:${count}`).join(', ') || 'none'}`,
        `Edge relations · ${Object.entries(edgeSummary?.by_relation || {}).map(([name, count]) => `${name}:${count}`).join(', ') || 'none'}`,
        `Target kinds · ${Object.entries(edgeSummary?.by_target_kind || {}).map(([name, count]) => `${name}:${count}`).join(', ') || 'none'}`,
        `Scope links filled · ${linkSummary.filledScope.length}/${linkSummary.scopeKeys.length}`,
        `Related links filled · ${linkSummary.filledRelated.length}/${linkSummary.relatedKeys.length}`,
        validation?.missing_paths?.length ? `Missing required · ${validation.missing_paths.join(', ')}` : 'Missing required · none',
        validation?.link_issues?.length ? `Link issues · ${validation.link_issues.map(issue => `${issue.slot}:${issue.status}`).join(', ')}` : 'Link issues · none',
        validation?.status_rule ? `Validation mode · ${validation.status_rule}` : 'Validation mode · n/a',
        normalization ? `Normalization drops · ${Number(normalization?.dropped_count || 0)}` : 'Normalization drops · n/a',
        normalization?.unknown_field_paths?.length ? `Unknown fields dropped · ${normalization.unknown_field_paths.join(', ')}` : '',
        normalization?.unknown_link_paths?.length ? `Unknown links dropped · ${normalization.unknown_link_paths.join(', ')}` : '',
        '',
        `Shared record keys · ${(shared.record?.record_envelope?.required_top_level_keys || []).join(', ')}`,
        `Reveal gating modes · ${(shared.memory_hints?.reveal_gating_values || []).join(', ')}`,
        `Link resolution states · ${(shared.links?.normalized_edge_enums?.link_resolution_status || []).join(', ')}`,
        forgeState().sqliteBackbone?.overview ? `SQLite backbone · ${Number(forgeState().sqliteBackbone.overview.entity_count || 0)} entities / ${Number(forgeState().sqliteBackbone.overview.edge_count || 0)} edges / ${Number(forgeState().sqliteBackbone.overview.version_count || 0)} versions` : '',
        forgeState().sqliteBackbone?.db_path ? `SQLite path · ${core.text(forgeState().sqliteBackbone.db_path)}` : '',
        '',
        memoryPreview?.error ? `Memory preview error · ${memoryPreview.error}` : `Memory fragments · ${Number(memoryPreview?.count || 0)}`,
        memoryPreview && !memoryPreview.error ? `Shared continuity · ${Number(memoryPreview?.shared_count || 0)}` : '',
        ...(Array.isArray(memoryPreview?.memory_fragments) ? memoryPreview.memory_fragments.slice(0, 3).map(row => `• ${core.text(row.title || row.id)}${core.text(row.memory_type) ? ` · ${core.text(row.memory_type)}` : ''}`) : []),
        ...(Array.isArray(memoryPreview?.shared_memories) && memoryPreview.shared_memories.length ? ['Shared rows:'].concat(memoryPreview.shared_memories.slice(0, 2).map(row => `• ${core.text(row.title || row.id)}`)) : []),
      ].filter(Boolean);
      inspector.textContent = lines.join('\n');
    }
    renderForm(validation);
    syncJsonEditor();
    renderForgeViews();
    renderForgeUtilityShell();
    refreshSqliteDebugView({ silent: true }).catch(() => {});
  }


  async function refreshTemplatesForSelected() {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const data = await core.getJson(`/api/roleplay/v2/builders/template?kind=${encodeURIComponent(kind)}`);
    if (!forgeState().templates) forgeState().templates = {};
    forgeState().templates[kind] = data.template || null;
  }


  async function refreshLibraryOverview() {
    const data = await core.getJson('/api/roleplay/v2/builders/forge-state');
    forgeState().recordsByKind = data.records_by_kind || forgeState().recordsByKind || {};
    return data;
  }

  async function refreshRecordList() {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const view = recordListView();
    if (view === 'current_kind') {
      if (!Array.isArray(forgeState().recordsByKind?.[kind])) {
        const data = await core.getJson(`/api/roleplay/v2/builders/records?kind=${encodeURIComponent(kind)}`);
        forgeState().recordsByKind[kind] = Array.isArray(data.records) ? data.records : [];
      }
    } else if (!forgeState().recordsByKind || !Object.keys(forgeState().recordsByKind).length) {
      await refreshLibraryOverview();
    }
    renderRecordList();
  }

  function newFromTemplate() {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const template = templatePayload(kind);
    forgeState().selectedRecordId = '';
    forgeState().memoryPreview = null;
    forgeState().workingPayload = deepClone(template?.json_template_payload || {});
    if (forgeState().workingPayload) {
      forgeState().workingPayload.id = '';
      forgeState().workingPayload.source_container_id = core.text(core.$('roleplay-v2-project-select')?.value);
      forgeState().workingPayload.label = '';
      forgeState().workingPayload.display_label = '';
      forgeState().workingPayload.summary = '';
      applyActiveScopeToPayload(kind, forgeState().workingPayload);
    }
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    renderRecordList();
    renderSelectedBuilder();
    core.setStatus('roleplay-v2-forge-status', `Started new ${kind} record from template.`, 'success');
  }

  function applyJsonEditor() {
    const editor = core.$('roleplay-v2-forge-json-editor');
    if (!editor) return;
    const incomingPayload = JSON.parse(editor.value || '{}');
    if (!incomingPayload || typeof incomingPayload !== 'object') throw new Error('JSON editor must contain a valid object payload.');
    const mode = core.text(core.$('roleplay-v2-forge-json-apply-mode')?.value || forgeState().jsonApplyMode) || 'fill_empty_only';
    const current = deepClone(currentPayload() || {});
    let nextPayload = {};
    if (mode === 'replace_all') nextPayload = deepClone(incomingPayload);
    else if (mode === 'merge_overwrite') nextPayload = deepMergeOverwrite(current, incomingPayload);
    else nextPayload = deepMergeFillEmpty(current, incomingPayload);
    forgeState().jsonApplyMode = mode;
    forgeState().workingPayload = nextPayload;
    const nextKind = core.text(nextPayload.kind) || core.text(forgeState().selectedKind) || 'universe';
    forgeState().selectedKind = nextKind;
    forgeState().selectedGroupId = groupForKind(nextKind).id;
    forgeState().selectedRecordId = core.text(nextPayload.id);
    forgeState().memoryPreview = null;
    syncJsonEditor();
    renderEntryLauncher();
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    renderRecordList();
    renderSelectedBuilder();
    const modeLabel = mode === 'replace_all' ? 'Replace all' : mode === 'merge_overwrite' ? 'Merge + overwrite' : 'Fill empty only';
    core.setStatus('roleplay-v2-forge-status', `Applied JSON editor payload into the Forge form · mode ${modeLabel}.`, 'success');
  }



  async function normalizeImportEditor(importFormat) {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const format = core.text(importFormat || 'json').toLowerCase();
    const payloadText = format === 'markdown'
      ? core.text(core.$('roleplay-v2-forge-md-editor')?.value)
      : core.text(core.$('roleplay-v2-forge-json-editor')?.value);
    const data = await core.postForm('/api/roleplay/v2/builders/normalize-import', {
      kind,
      import_format: format === 'markdown' ? 'markdown' : 'json',
      payload_text: payloadText,
    });
    forgeState().workingPayload = deepClone(data.normalized_payload || {});
    forgeState().lastNormalization = data.normalization || null;
    forgeState().selectedRecordId = core.text(data.normalized_payload?.id);
    forgeState().memoryPreview = null;
    renderSelectedBuilder(data.validation || null);
    core.setStatus('roleplay-v2-forge-status', `Normalized ${format.toUpperCase()} into the ${kind} builder shell.`, data.validation?.severity === 'error' ? 'error' : data.validation?.severity === 'warning' ? 'warning' : 'success');
    core.setOutput(data);
  }

  async function saveCurrentRecord() {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const payload = deepClone(currentPayload() || {});
    applyActiveScopeToPayload(kind, payload);
    forgeState().workingPayload = payload;
    const data = await core.postForm('/api/roleplay/v2/builders/save', {
      kind,
      payload_json: JSON.stringify(payload || {}),
    });
    forgeState().workingPayload = deepClone(data.builder_payload || {});
    forgeState().lastNormalization = data.normalization || null;
    if (data.sqlite_overview) {
      forgeState().sqliteBackbone = forgeState().sqliteBackbone || {};
      forgeState().sqliteBackbone.overview = data.sqlite_overview;
    }
    forgeState().selectedRecordId = core.text(data.record?.id);
    await refreshMemoryPreview(core.text(data.record?.id));
    syncJsonEditor();
    await refreshLibraryOverview();
    await refreshRecordList();
    if (typeof core.refreshRoleplayV2LibraryView === 'function') {
      try { await core.refreshRoleplayV2LibraryView(); } catch (_) {}
    }
    renderSelectedBuilder(data.validation || null);
    const sqliteNote = data.sqlite_sync ? ` SQLite ${Number(data.sqlite_sync.edge_count || 0)} edges synced.` : '';
    core.setStatus('roleplay-v2-forge-status', `Saved ${kind} record ${core.text(data.record?.id)}.${sqliteNote}`, data.validation?.missing_paths?.length ? 'warning' : 'success');
    core.setOutput(data);
    return data;
  }

  function collectMissingLinkDraftFields(node, path = '') {
    const fields = [];
    if (Array.isArray(node)) {
      node.forEach((item, index) => {
        const nextPath = path ? `${path}.${index}` : String(index);
        if (item && typeof item === 'object') fields.push(...collectMissingLinkDraftFields(item, nextPath));
      });
      return fields;
    }
    if (!node || typeof node !== 'object') return fields;
    Object.entries(node).forEach(([key, value]) => {
      const nextPath = path ? `${path}.${key}` : key;
      if (nextPath === 'links.source_container_id' || nextPath.startsWith('links.scope.') || nextPath.startsWith('links.reverse_links.')) return;
      if (isLinkField(nextPath, key)) {
        fields.push({
          path: nextPath,
          key,
          targetKinds: targetKindsForLinkField(key),
          isArray: Array.isArray(value),
          values: Array.isArray(value) ? value.slice() : [value],
        });
        return;
      }
      if (value && typeof value === 'object') fields.push(...collectMissingLinkDraftFields(value, nextPath));
    });
    return fields;
  }

  async function resolveMissingLinkedDraftValue(rawValue, targetKinds, draftCache) {
    const cleanValue = core.text(rawValue);
    if (!cleanValue) return { status: 'empty', value: '' };
    const records = await combinedLinkRecords(targetKinds || []);
    const lowerValue = cleanValue.toLowerCase();
    const existing = (records || []).find(item => {
      const id = core.text(item.id);
      const label = core.text(item.label).toLowerCase();
      const display = core.text(item.display_label).toLowerCase();
      return id === cleanValue || label === lowerValue || display === lowerValue;
    });
    if (existing) {
      return { status: existing.id === cleanValue ? 'existing' : 'normalized', value: core.text(existing.id), record: existing };
    }
    if (!Array.isArray(targetKinds) || !targetKinds.length) {
      return { status: 'skipped', reason: 'unsupported_link_target', value: cleanValue };
    }
    if (targetKinds.length !== 1) {
      return { status: 'skipped', reason: 'ambiguous_target_kind', value: cleanValue };
    }
    const cacheKey = `${core.text(targetKinds[0])}::${lowerValue}`;
    if (draftCache.has(cacheKey)) {
      return { status: 'created', value: draftCache.get(cacheKey).id, record: draftCache.get(cacheKey), reused_batch_stub: true };
    }
    const data = await createScopedStub(targetKinds[0], cleanValue);
    const created = {
      id: core.text(data.record?.id),
      kind: core.text(data.record?.kind || targetKinds[0]),
      label: core.text(data.record?.label || cleanValue),
    };
    draftCache.set(cacheKey, created);
    return { status: 'created', value: created.id, record: created, data };
  }

  async function createMissingLinkedDraftsForPayload(payload = {}) {
    const fields = collectMissingLinkDraftFields(payload);
    const report = { created: [], normalized: [], existing: [], skipped: [], touched_paths: [] };
    const draftCache = new Map();
    for (const field of fields) {
      const nextValues = [];
      for (const rawValue of (field.values || [])) {
        const result = await resolveMissingLinkedDraftValue(rawValue, field.targetKinds, draftCache);
        if (result.status === 'empty') continue;
        if (result.status === 'existing') {
          nextValues.push(result.value);
          report.existing.push({ path: field.path, value: result.value, kind: core.text(result.record?.kind) });
          continue;
        }
        if (result.status === 'normalized') {
          nextValues.push(result.value);
          report.normalized.push({ path: field.path, from: core.text(rawValue), to: result.value, kind: core.text(result.record?.kind) });
          if (!report.touched_paths.includes(field.path)) report.touched_paths.push(field.path);
          continue;
        }
        if (result.status === 'created') {
          nextValues.push(result.value);
          report.created.push({ path: field.path, from: core.text(rawValue), to: result.value, kind: core.text(result.record?.kind), reused_batch_stub: !!result.reused_batch_stub });
          if (!report.touched_paths.includes(field.path)) report.touched_paths.push(field.path);
          continue;
        }
        nextValues.push(core.text(rawValue));
        report.skipped.push({ path: field.path, value: core.text(rawValue), reason: core.text(result.reason || 'skipped') });
      }
      setByPath(payload, field.path, field.isArray ? nextValues.filter(value => core.text(value)) : core.text(nextValues[0] || ''));
    }
    return report;
  }

  async function saveCurrentRecordWithLinkedDrafts() {
    const payload = currentPayload();
    const report = await createMissingLinkedDraftsForPayload(payload);
    syncJsonEditor();
    renderSelectedBuilder();
    const data = await saveCurrentRecord();
    const pieces = [];
    if (report.created.length) pieces.push(`created ${Number(report.created.length)} linked draft${report.created.length === 1 ? '' : 's'}`);
    if (report.normalized.length) pieces.push(`normalized ${Number(report.normalized.length)} linked value${report.normalized.length === 1 ? '' : 's'}`);
    if (report.skipped.length) pieces.push(`skipped ${Number(report.skipped.length)} ambiguous link${report.skipped.length === 1 ? '' : 's'}`);
    if (pieces.length) {
      core.setStatus('roleplay-v2-forge-status', `Saved ${core.text(data.record?.kind || forgeState().selectedKind)} record ${core.text(data.record?.id)} · ${pieces.join(' · ')}.`, report.skipped.length ? 'warning' : 'success');
    }
    core.setOutput({ ...(data || {}), linked_draft_report: report });
    return { ...(data || {}), linked_draft_report: report };
  }

  async function loadForgeState() {
    const [forgeData, foundationData] = await Promise.all([
      core.getJson('/api/roleplay/v2/builders/forge-state'),
      core.getJson('/api/roleplay/v2/foundation-state'),
    ]);
    state.forge.builders = forgeData.builders || [];
    state.forge.templates = forgeData.templates || {};
    state.forge.sharedContracts = forgeData.shared_contracts || {};
    state.forge.sqliteBackbone = forgeData.sqlite_backbone || null;
    state.forge.hierarchy = forgeData.authoring_hierarchy || null;
    state.forge.foundation = foundationData || null;
    state.forge.recordsByKind = forgeData.records_by_kind || state.forge.recordsByKind || {};
    if (!builderSummary(forgeState().selectedKind) && (state.forge.builders || []).length) {
      forgeState().selectedKind = core.text(state.forge.builders[0]?.kind) || 'universe';
    }
    forgeState().selectedGroupId = groupForKind(forgeState().selectedKind).id;
    if (core.$('roleplay-v2-forge-record-view')) core.$('roleplay-v2-forge-record-view').value = recordListView();
    if (core.$('roleplay-v2-forge-record-group-by')) core.$('roleplay-v2-forge-record-group-by').value = recordGroupBy();
    if (core.$('roleplay-v2-forge-record-status-filter')) core.$('roleplay-v2-forge-record-status-filter').value = core.text(forgeState().recordStatusFilter);
    if (core.$('roleplay-v2-forge-record-search')) core.$('roleplay-v2-forge-record-search').value = core.text(forgeState().recordSearch);
    if (core.$('roleplay-v2-forge-json-apply-mode')) core.$('roleplay-v2-forge-json-apply-mode').value = core.text(forgeState().jsonApplyMode) || 'fill_empty_only';
    renderEntryLauncher();
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    renderScopeBar();
    renderScopePicker();
    renderScopeChildActions();
    await refreshTemplatesForSelected();
    await refreshRecordList();
    if (!forgeState().workingPayload && core.text(forgeState().selectedRecordId)) {
      try {
        await loadRecordIntoForge(core.text(forgeState().selectedRecordId));
      } catch (_) {
        forgeState().selectedRecordId = '';
        newFromTemplate();
      }
    } else if (!forgeState().workingPayload) newFromTemplate();
    else { await refreshMemoryPreview(core.text(forgeState().workingPayload?.id)); renderSelectedBuilder(); }
    renderForgeUtilityShell();
    core.setStatus('roleplay-v2-forge-status', 'Forge foundation loaded with grouped builder chips.', 'success');
  }

  async function createStub() {
    const kind = core.text(forgeState().selectedKind) || 'universe';
    const label = core.text(core.$('roleplay-v2-forge-stub-label')?.value);
    if (!label) throw new Error('Enter a label for the draft stub first.');
    const sourceContainerId = core.text(core.$('roleplay-v2-project-select')?.value);
    const data = await core.postForm('/api/roleplay/v2/builders/create-stub', {
      kind,
      label,
      source_container_id: sourceContainerId,
    });
    const sqliteNote = data.sqlite_sync ? ` SQLite ${Number(data.sqlite_sync.edge_count || 0)} edges synced.` : '';
    core.setStatus('roleplay-v2-forge-status', `Created ${kind} stub ${core.text(data.record?.id)}.${sqliteNote}`, 'success');
    if (core.$('roleplay-v2-forge-stub-result')) core.$('roleplay-v2-forge-stub-result').textContent = JSON.stringify(data.record || {}, null, 2);
    if (core.$('roleplay-v2-forge-stub-label')) core.$('roleplay-v2-forge-stub-label').value = '';
    await refreshLibraryOverview();
    await refreshRecordList();
    renderGroupRail();
    renderBuilderRail();
    renderSubcategoryChips();
    core.setOutput(data);
  }

  async function compileCurrentBuilderMemory() {
    const recordId = core.text(currentPayload()?.id);
    if (!recordId) throw new Error('Save the builder record before compiling memory from Forge.');
    const data = await core.modules?.studio?.compileMemoryForRecord?.(recordId, { statusMessage: `Compiled builder memory for ${recordId} from Forge.` });
    if (data?.sqlite_overview) {
      forgeState().sqliteBackbone = forgeState().sqliteBackbone || {};
      forgeState().sqliteBackbone.overview = data.sqlite_overview;
      forgeState().sqliteBackbone.db_path = data?.sqlite_sync?.db_path || forgeState().sqliteBackbone.db_path || '';
    }
    await refreshMemoryPreview(recordId);
    await refreshSqliteDebugView({ silent: true }).catch(() => {});
    renderSelectedBuilder(data?.validation || null);
    return data;
  }

  async function buildRuntimeFromCurrentRecord() {
    const recordId = core.text(currentPayload()?.id);
    if (!recordId) throw new Error('Save the builder record before building a Scene packet from Forge.');
    const data = await core.modules?.studio?.buildRuntimeForRecord?.(recordId, { statusMessage: `Built Scene packet from ${recordId} in Forge.` });
    return data;
  }

  async function refreshSqliteDebugView({ silent = false } = {}) {
    const kind = core.text(forgeState().selectedKind) || '';
    const query = core.text(core.$('roleplay-v2-forge-sqlite-search')?.value);
    const entityId = core.text(currentPayload()?.id || forgeState().selectedRecordId);
    const output = core.$('roleplay-v2-forge-sqlite-debug');
    const [overview, entities, edges, fragments, sharedMemories, callbacks] = await Promise.all([
      core.getJson('/api/roleplay/v2/sqlite/overview'),
      core.getJson(`/api/roleplay/v2/sqlite/entities?kind=${encodeURIComponent(kind)}&query=${encodeURIComponent(query)}&limit=8`),
      core.getJson(`/api/roleplay/v2/sqlite/edges?entity_id=${encodeURIComponent(entityId)}&limit=12`),
      core.getJson(`/api/roleplay/v2/sqlite/memory-fragments?entity_id=${encodeURIComponent(entityId)}&query=${encodeURIComponent(query)}&limit=10`),
      core.getJson(`/api/roleplay/v2/sqlite/shared-memories?entity_id=${encodeURIComponent(entityId)}&query=${encodeURIComponent(query)}&limit=8`),
      core.getJson(`/api/roleplay/v2/sqlite/callback-anchors?entity_id=${encodeURIComponent(entityId)}&query=${encodeURIComponent(query)}&limit=10`),
    ]);
    forgeState().sqliteBackbone = forgeState().sqliteBackbone || {};
    forgeState().sqliteBackbone.db_path = overview.db_path || forgeState().sqliteBackbone.db_path || '';
    forgeState().sqliteBackbone.overview = overview;
    if (output) {
      const lines = [
        `SQLite DB · ${core.text(overview?.db_path) || 'n/a'}`,
        `Entities · ${Number(overview?.entity_count || 0)} · Edges · ${Number(overview?.edge_count || 0)} · Versions · ${Number(overview?.version_count || 0)}`,
        `Fragments · ${Number(overview?.memory_fragment_count || 0)} · Shared · ${Number(overview?.shared_memory_count || 0)} · Callbacks · ${Number(overview?.callback_anchor_count || 0)}`,
        '',
        `Entity rows (${core.text(kind) || 'all'}):`,
        ...(Array.isArray(entities?.rows) && entities.rows.length ? entities.rows.map(row => `• ${core.text(row.label || row.entity_id)} [${core.text(row.kind)}] · edges ${Number(row.edge_count || 0)} / incoming ${Number(row.reverse_edge_count || 0)}`) : ['• none']),
        '',
        `Edge rows for ${core.text(entityId) || 'current selection'}:`,
        ...(Array.isArray(edges?.rows) && edges.rows.length ? edges.rows.map(row => `• ${core.text(row.direction || 'edge')} · ${core.text(row.family)} · ${core.text(row.relation)} :: ${core.text(row.source_label || row.source_id)} -> ${core.text(row.target_label || row.target_id)}`) : ['• none']),
        '',
        `Memory fragments for ${core.text(entityId) || 'current selection'}:`,
        ...(Array.isArray(fragments?.rows) && fragments.rows.length ? fragments.rows.map(row => `• [${core.text(row.memory_type)}] ${core.text(row.title || row.memory_id)} · salience ${Number(row.salience || 0).toFixed(2)} · ${core.text(row.summary || '').slice(0, 140)}`) : ['• none']),
        '',
        `Shared memories for ${core.text(entityId) || 'current selection'}:`,
        ...(Array.isArray(sharedMemories?.rows) && sharedMemories.rows.length ? sharedMemories.rows.map(row => `• ${core.text(row.label || row.shared_memory_id)} :: ${core.text(row.entity_a_label || row.entity_a_id)} ↔ ${core.text(row.entity_b_label || row.entity_b_id)} · ${core.text(row.text || '').slice(0, 140)}`) : ['• none']),
        '',
        `Callback anchors for ${core.text(entityId) || 'current selection'}:`,
        ...(Array.isArray(callbacks?.rows) && callbacks.rows.length ? callbacks.rows.map(row => `• ${core.text(row.label || row.callback_id)} · ${core.text(row.anchor_text || '').slice(0, 140)}`) : ['• none']),
      ];
      output.textContent = lines.join('\n');
    }
    if (!silent) {
      core.setStatus('roleplay-v2-forge-status', 'SQLite debug view refreshed.', 'success');
    }
    return { overview, entities, edges, fragments, sharedMemories, callbacks };
  }

  async function syncSqliteBackbone() {
    const data = await core.postForm('/api/roleplay/v2/sqlite/sync-builders', { prune_missing: '1' });
    forgeState().sqliteBackbone = forgeState().sqliteBackbone || {};
    forgeState().sqliteBackbone.db_path = data.db_path || forgeState().sqliteBackbone.db_path || '';
    forgeState().sqliteBackbone.overview = data.overview || forgeState().sqliteBackbone.overview || null;
    await refreshSqliteDebugView({ silent: true });
    core.setStatus('roleplay-v2-forge-status', `SQLite sync complete. ${Number(data.synced || 0)} records synced, ${Number(data.pruned || 0)} pruned.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function routeAssistDraftToJson(kind = '', draftJson = '', { applyMode = '' } = {}) {
    const cleanKind = core.text(kind) || 'universe';
    const cleanDraft = String(draftJson || '').trim();
    if (!cleanDraft) throw new Error('Assist JSON draft is empty.');
    await setSelectedKind(cleanKind, { resetRecord: true, forceNew: true });
    forgeState().activeView = 'json';
    renderForgeViews();
    const editor = core.$('roleplay-v2-forge-json-editor');
    if (!editor) throw new Error('Forge JSON editor is unavailable.');
    editor.value = cleanDraft;
    if (core.$('roleplay-v2-forge-json-apply-mode') && core.text(applyMode)) {
      core.$('roleplay-v2-forge-json-apply-mode').value = core.text(applyMode);
      forgeState().jsonApplyMode = core.text(applyMode);
    }
    core.setSubtab('forge');
    core.setStatus('roleplay-v2-forge-status', `Assist draft routed to Forge → ${prettyLabel(cleanKind)} → JSON. Review it, then apply when ready.`, 'success');
    return { kind: cleanKind, active_view: forgeState().activeView };
  }

  async function boot() {
    document.querySelectorAll('#roleplay-v2-forge-viewbar [data-roleplay-v2-forge-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        forgeState().activeView = core.text(btn.getAttribute('data-roleplay-v2-forge-view')) || 'form';
        renderForgeViews();
      });
    });
    document.querySelectorAll('#roleplay-v2-forge-utility-viewbar [data-roleplay-v2-forge-utility-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        forgeState().utilityView = core.text(btn.getAttribute('data-roleplay-v2-forge-utility-view')) || 'inspector';
        renderForgeUtilityShell();
        if (forgeState().utilityView === 'sqlite') refreshSqliteDebugView({ silent: true }).catch(() => {});
      });
    });
    core.$('btn-roleplay-v2-forge-auto-height-rail')?.addEventListener('click', toggleForgeAutoHeight);
    core.$('btn-roleplay-v2-forge-auto-height-editor')?.addEventListener('click', toggleForgeAutoHeight);
    core.$('btn-roleplay-v2-forge-refresh')?.addEventListener('click', async () => {
      try { await loadForgeState(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-create-stub')?.addEventListener('click', async () => {
      try { await createStub(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-records-refresh')?.addEventListener('click', async () => {
      try {
        await refreshLibraryOverview();
        await refreshRecordList();
        renderGroupRail();
        renderBuilderRail();
        core.setStatus('roleplay-v2-forge-status', 'Builder record list refreshed.', 'success');
      } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-forge-record-search')?.addEventListener('input', event => {
      forgeState().recordSearch = core.text(event?.target?.value);
      renderRecordList();
    });
    core.$('roleplay-v2-forge-record-view')?.addEventListener('change', event => {
      forgeState().recordListView = core.text(event?.target?.value) || 'current_kind';
      refreshRecordList().catch(err => core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'));
    });
    core.$('roleplay-v2-forge-record-group-by')?.addEventListener('change', event => {
      forgeState().recordGroupBy = core.text(event?.target?.value) || 'scope';
      renderRecordList();
    });
    core.$('roleplay-v2-forge-record-status-filter')?.addEventListener('change', event => {
      forgeState().recordStatusFilter = core.text(event?.target?.value);
      renderRecordList();
    });
    core.$('roleplay-v2-forge-json-apply-mode')?.addEventListener('change', event => {
      forgeState().jsonApplyMode = core.text(event?.target?.value) || 'fill_empty_only';
    });
    core.$('btn-roleplay-v2-forge-new-record')?.addEventListener('click', () => {
      try { newFromTemplate(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-sync-json')?.addEventListener('click', () => {
      try { syncJsonEditor(); core.setStatus('roleplay-v2-forge-status', 'JSON editor refreshed from the current Forge form.', 'success'); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-apply-json')?.addEventListener('click', () => {
      try { applyJsonEditor(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-apply-md')?.addEventListener('click', async () => {
      try { await normalizeImportEditor('markdown'); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-save-record')?.addEventListener('click', async () => {
      try { await saveCurrentRecord(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-save-create-drafts')?.addEventListener('click', async () => {
      try { await saveCurrentRecordWithLinkedDrafts(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-delete-record')?.addEventListener('click', async () => {
      try {
        const payload = currentPayload();
        await deleteBuilderRecord(core.text(payload?.id), { label: core.text(payload?.label || payload?.display_label) });
      } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-use-current-scope')?.addEventListener('click', () => {
      const payload = currentPayload();
      const derived = deriveScopeFromPayload(core.text(forgeState().selectedKind), payload);
      if (!['universe_id', 'world_id', 'region_id', 'city_id'].some(key => core.text(derived[key]))) {
        core.setStatus('roleplay-v2-forge-status', 'Current record does not expose a usable universe/world/region/city scope yet.', 'warn');
        return;
      }
      setActiveScope(derived, `Scope locked to ${core.text(derived.source_label || derived.source_id)}.`);
    });
    core.$('btn-roleplay-v2-forge-clear-scope')?.addEventListener('click', () => {
      setActiveScope({}, 'Cleared active build scope.');
    });
    core.$('roleplay-v2-forge-scope-kind-select')?.addEventListener('change', renderScopePicker);
    core.$('roleplay-v2-forge-scope-search')?.addEventListener('input', renderScopePicker);
    core.$('btn-roleplay-v2-forge-scope-refresh')?.addEventListener('click', async () => {
      await refreshLibraryOverview();
      renderScopePicker();
      core.setStatus('roleplay-v2-forge-status', 'Refreshed scope picker records.', 'success');
    });
    core.$('btn-roleplay-v2-forge-compile-memory')?.addEventListener('click', async () => {
      try {
        const data = await compileCurrentBuilderMemory();
        const counts = data?.compiled_counts || {};
        const sqliteSync = data?.sqlite_sync || {};
        core.setStatus('roleplay-v2-forge-status', `Builder memory compiled from Forge. ${Number(counts.memory_fragments || 0)} fragments, ${Number(counts.shared_memories || 0)} shared, ${Number(sqliteSync.callback_anchor_count || 0)} callbacks synced to SQLite.`, 'success');
      } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-build-runtime')?.addEventListener('click', async () => {
      try { await buildRuntimeFromCurrentRecord(); core.setStatus('roleplay-v2-forge-status', 'Scene packet built from Forge record.', 'success'); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-sqlite-sync')?.addEventListener('click', async () => {
      try { await syncSqliteBackbone(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-forge-sqlite-refresh')?.addEventListener('click', async () => {
      try { await refreshSqliteDebugView(); } catch (err) { core.setStatus('roleplay-v2-forge-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-forge-sqlite-search')?.addEventListener('input', () => { refreshSqliteDebugView({ silent: true }).catch(() => {}); });
    core.$('btn-roleplay-v2-link-picker-close')?.addEventListener('click', () => closeLinkPicker());
    core.$('roleplay-v2-link-picker-modal')?.addEventListener('click', e => { if (e.target?.id === 'roleplay-v2-link-picker-modal') closeLinkPicker(); });
    core.$('roleplay-v2-link-picker-search')?.addEventListener('input', () => renderLinkPickerResults());
    core.$('roleplay-v2-link-picker-kind-filter')?.addEventListener('change', event => {
      if (!activeLinkPicker) return;
      activeLinkPicker.filters = { ...(activeLinkPicker.filters || {}), kind: core.text(event?.target?.value) };
      renderLinkPickerResults();
    });
    core.$('roleplay-v2-link-picker-scope-filter')?.addEventListener('change', event => {
      if (!activeLinkPicker) return;
      activeLinkPicker.filters = { ...(activeLinkPicker.filters || {}), scope: core.text(event?.target?.value || 'all') || 'all' };
      renderLinkPickerResults();
    });
    core.$('roleplay-v2-link-picker-category-filter')?.addEventListener('change', event => {
      if (!activeLinkPicker) return;
      activeLinkPicker.filters = { ...(activeLinkPicker.filters || {}), category: core.text(event?.target?.value) };
      renderLinkPickerResults();
    });
    core.$('roleplay-v2-link-picker-subcategory-filter')?.addEventListener('change', event => {
      if (!activeLinkPicker) return;
      activeLinkPicker.filters = { ...(activeLinkPicker.filters || {}), subcategory: core.text(event?.target?.value) };
      renderLinkPickerResults();
    });
    core.$('roleplay-v2-link-picker-status-filter')?.addEventListener('change', event => {
      if (!activeLinkPicker) return;
      activeLinkPicker.filters = { ...(activeLinkPicker.filters || {}), status: core.text(event?.target?.value) };
      renderLinkPickerResults();
    });
    core.$('btn-roleplay-v2-link-picker-refresh')?.addEventListener('click', async () => {
      try { await refreshLinkPickerResults(true); core.setStatus('roleplay-v2-link-picker-status', 'Link results refreshed.', 'success'); } catch (err) { core.setStatus('roleplay-v2-link-picker-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-link-picker-create-stub')?.addEventListener('click', async () => {
      try { await createStubFromLinkPicker(); } catch (err) { core.setStatus('roleplay-v2-link-picker-status', err.message || String(err), 'error'); }
    });
    applyForgeShellSizing();
    await loadForgeState();
    applyForgeShellSizing();
  }

  async function onInternalToolsToggle(enabled) {
    if (!enabled && core.text(forgeState().utilityView) === 'sqlite') forgeState().utilityView = 'inspector';
    renderForgeUtilityShell();
    if (enabled && core.text(forgeState().utilityView) === 'sqlite') {
      await refreshSqliteDebugView({ silent: true }).catch(() => {});
    }
  }

  core.registerModule('forge', { boot, loadForgeState, createStub, createScopedStub, saveCurrentRecord, saveCurrentRecordWithLinkedDrafts, normalizeImportEditor, refreshMemoryPreview, compileCurrentBuilderMemory, buildRuntimeFromCurrentRecord, refreshSqliteDebugView, syncSqliteBackbone, routeAssistDraftToJson, setSelectedKind, onInternalToolsToggle });
})();


