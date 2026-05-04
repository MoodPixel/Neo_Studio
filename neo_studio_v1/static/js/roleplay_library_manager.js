(function () {
  const cache = { universe: new Map(), character: new Map(), world: new Map(), region: new Map(), city: new Map(), location: new Map(), organization: new Map(), artifact: new Map(), ritual: new Map(), cycle: new Map(), creature: new Map(), legend: new Map(), pack: new Map(), scenario: new Map() };
  const state = {
    characters: [],
    worlds: [],
    regions: [],
    cities: [],
    locations: [],
    organizations: [],
    artifacts: [],
    rituals: [],
    cycles: [],
    creatures: [],
    universes: [],
    legends: [],
    packs: [],
    scenarios: [],
    characterRelationships: [],
    characterAbilities: [],
    characterWardrobes: [],
    characterHooks: [],
    scenarioCast: [],
    importPreview: null,
  };

  function el(id) { return document.getElementById(id); }
  function trimValue(value) { return String(value || '').trim(); }
  function libraryStatus(id, message = '', level = '') { if (typeof setStatus === 'function') setStatus(id, message, level); }
  function optionLabel(item, fallback = 'Untitled') {
    const title = trimValue(item?.title) || fallback;
    const subtitle = trimValue(item?.subtitle);
    return subtitle ? `${title} — ${subtitle}` : title;
  }
  function assetUrl(assetPath) {
    const clean = trimValue(assetPath);
    return clean ? `/api/roleplay/asset/file?asset_path=${encodeURIComponent(clean)}` : '';
  }
  function setImagePreview(imgId, emptyId, assetPath) {
    const img = el(imgId);
    const empty = el(emptyId);
    const url = assetUrl(assetPath);
    if (img) {
      if (url) {
        img.src = url;
        img.classList.remove('hidden');
      } else {
        img.removeAttribute('src');
        img.classList.add('hidden');
      }
    }
    if (empty) empty.classList.toggle('hidden', !!url);
  }
  function humanizeKey(value) {
    return trimValue(value).replace(/[_-]+/g, ' ').replace(/\b\w/g, m => m.toUpperCase());
  }
  function parseJsonArray(raw, fallback = []) {
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return Array.isArray(data) ? data : fallback.slice();
    } catch (_err) {
      return fallback.slice();
    }
  }
  function summarizeArray(items, mapper) {
    const lines = [];
    (Array.isArray(items) ? items : []).forEach(item => {
      const text = trimValue(mapper(item || {}));
      if (text) lines.push(text);
    });
    return lines;
  }

  const IMPORT_KIND_LABELS = { legend: 'Legends', universe: 'Universes', world: 'Worlds', region: 'Kingdoms / Regions', city: 'Cities / Settlements', location: 'Locations', organization: 'Organizations / Factions', character: 'Characters', artifact: 'Weapons / Artifacts', ritual: 'Spells / Rituals / Techniques', cycle: 'Cycles / Conditions / Systems', creature: 'Creatures / Animals / Fauna', pack: 'Packs', scenario: 'Scenarios' };
  const IMPORT_SECTION_SUMMARIES = { legend: 'Legends', universe: 'Universes', world: 'Worlds', region: 'Kingdoms / Regions', city: 'Cities / Settlements', location: 'Locations', organization: 'Organizations / Factions', character: 'Characters', artifact: 'Weapons / Artifacts', ritual: 'Spells / Rituals / Techniques', cycle: 'Cycles / Conditions / Systems', creature: 'Creatures / Animals / Fauna', pack: 'Packs', scenario: 'Scenarios' };
  const LIBRARY_SELECT_IDS = { character: 'roleplay-library-character-select', world: 'roleplay-library-world-select', region: 'roleplay-library-region-select', city: 'roleplay-library-city-select', location: 'roleplay-library-location-select', organization: 'roleplay-library-organization-select', artifact: 'roleplay-library-artifact-select', ritual: 'roleplay-library-ritual-select', cycle: 'roleplay-library-cycle-select', creature: 'roleplay-library-creature-select', universe: 'roleplay-library-universe-select', legend: 'roleplay-library-legend-select', pack: 'roleplay-library-pack-select', scenario: 'roleplay-library-scenario-select' };
  const BUILDER_ASSIST_CONFIG = {
    character: { summary: 'Characters', title: 'Character builder assist', hint: 'Draft identity, voice, personality, and appearance fields from a short brief. Nothing is auto-saved.' },
    world: { summary: 'Worlds', title: 'World builder assist', hint: 'Draft world structure, lore, and setting notes into the world form. Nothing is auto-saved.' },
    location: { summary: 'Locations', title: 'Location builder assist', hint: 'Draft place mood, function, hazards, and scene-use notes for the current location form. Nothing is auto-saved.' },
    scenario: { summary: 'Scenarios', title: 'Scenario builder assist', hint: 'Draft playable scene setup, objective, premise, and opening beat fields. Nothing is auto-saved.' },
  };
  const BUILDER_ASSIST_FIELD_IDS = {
    character: {
      name: 'roleplay-library-character-name', display_name: 'roleplay-library-character-display-name', gender: 'roleplay-library-character-gender', pronouns: 'roleplay-library-character-pronouns', role_tier: 'roleplay-library-character-role-tier', species: 'roleplay-library-character-species', designation: 'roleplay-library-character-designation', occupation: 'roleplay-library-character-occupation', student_details: 'roleplay-library-character-student-details', hobbies: 'roleplay-library-character-hobbies', affiliations: 'roleplay-library-character-affiliations', summary: 'roleplay-library-character-summary', appearance: 'roleplay-library-character-appearance', personality: 'roleplay-library-character-personality', speech_style: 'roleplay-library-character-speech-style', relationship_notes: 'roleplay-library-character-relationship-notes', canon_notes: 'roleplay-library-character-canon-notes'
    },
    world: {
      name: 'roleplay-library-world-name', summary: 'roleplay-library-world-summary', realm_type: 'roleplay-library-world-realm-type', calendar_notes: 'roleplay-library-world-calendar-notes', lore: 'roleplay-library-world-lore', rules: 'roleplay-library-world-rules', geography_notes: 'roleplay-library-world-geography-notes', society_notes: 'roleplay-library-world-society-notes', faith_notes: 'roleplay-library-world-faith-notes', people_notes: 'roleplay-library-world-people-notes', canon_notes: 'roleplay-library-world-canon-notes'
    },
    location: {
      name: 'roleplay-library-location-name', display_name: 'roleplay-library-location-display-name', function_label: 'roleplay-library-location-function-label', location_type: 'roleplay-library-location-type', summary: 'roleplay-library-location-summary', atmosphere: 'roleplay-library-location-atmosphere', access_notes: 'roleplay-library-location-access-notes', hazards: 'roleplay-library-location-hazards', rules: 'roleplay-library-location-rules', public_notes: 'roleplay-library-location-public-notes', hidden_truth: 'roleplay-library-location-hidden-truth', canon_notes: 'roleplay-library-location-canon-notes'
    },
    scenario: {
      title: 'roleplay-library-scenario-title', tone: 'roleplay-library-scenario-tone', location_label: 'roleplay-library-scenario-location-label', objective: 'roleplay-library-scenario-objective', premise: 'roleplay-library-scenario-premise', opening_beat: 'roleplay-library-scenario-opening-beat', scene_notes: 'roleplay-library-scenario-scene-notes'
    },
  };

  function importStatus(message = '', level = '') { libraryStatus('roleplay-library-import-status', message, level); }
  function setImportButtonsDisabled(disabled) { ['btn-roleplay-library-import-apply', 'btn-roleplay-library-import-save'].forEach(id => { const node = el(id); if (node) node.disabled = !!disabled; }); }
  function jsonEditorValue() { return trimValue(el('roleplay-library-json-editor')?.value); }
  function setJsonEditorValue(value = '') { const node = el('roleplay-library-json-editor'); if (!node) return; node.value = String(value || ''); node.dispatchEvent(new Event('input', { bubbles: true })); }
  function renderImportPreview(preview = null) {
    state.importPreview = preview || null;
    const summaryNode = el('roleplay-library-import-summary');
    const previewNode = el('roleplay-library-import-preview-json');
    if (!preview || !preview.summary) {
      if (summaryNode) summaryNode.innerHTML = '<div class="muted small">No import preview yet.</div>';
      if (previewNode) previewNode.textContent = 'No preview loaded.';
      setImportButtonsDisabled(true);
      return;
    }
    const summary = preview.summary || {};
    const warnings = Array.isArray(summary.warnings) ? summary.warnings.filter(Boolean) : [];
    const items = Array.isArray(summary.items) ? summary.items : [];
    if (summaryNode) {
      const rows = [
        `<div><strong>${escapeHtml(summary.source_name || 'Import file')}</strong></div>`,
        `<div class="muted small" style="margin-top:4px;">${escapeHtml(summary.import_kind_label || IMPORT_KIND_LABELS[summary.import_kind] || humanizeKey(summary.import_kind || 'record'))} • ${escapeHtml(summary.source_type || 'json')} • ${escapeHtml(String(summary.record_count || 0))} record(s)</div>`
      ];
      if (summary.overwrite_count) rows.push(`<div class="mini-note" style="margin-top:8px;">${escapeHtml(String(summary.overwrite_count))} existing record(s) will be updated if you commit this preview.</div>`);
      if (items.length) rows.push(`<ul style="margin:10px 0 0 18px;">${items.slice(0, 6).map(item => `<li><strong>${escapeHtml(item.label || 'Untitled')}</strong>${item.subtitle ? ` — ${escapeHtml(item.subtitle)}` : ''}${item.id ? ` <span class="muted small">(${escapeHtml(item.id)})</span>` : ''}</li>`).join('')}</ul>`);
      if (warnings.length) rows.push(`<div class="mini-note" style="margin-top:10px; color:#ffcc7a;">${warnings.map(line => escapeHtml(line)).join('<br/>')}</div>`);
      summaryNode.innerHTML = rows.join('');
    }
    if (previewNode) {
      const previewRecords = Array.isArray(preview.records) ? preview.records : [];
      const payload = previewRecords.length <= 2 ? previewRecords : [...previewRecords.slice(0, 2), { note: `... ${previewRecords.length - 2} more record(s) omitted from preview` }];
      previewNode.textContent = JSON.stringify(previewRecords.length === 1 ? payload[0] : payload, null, 2);
    }
    if (preview.source_type === 'json' && trimValue(preview.raw_text || preview.draft_json)) setJsonEditorValue(preview.draft_json || preview.raw_text || '');
    setImportButtonsDisabled(false);
  }
  function importStatusIdForKind(kind) { return `roleplay-library-${trimValue(kind)}-status`; }
  function reorderLibrarySections() {
    const body = document.querySelector('#roleplay-library-panel .roleplay-collapsible-body');
    if (!body) return;
    const blocks = Array.from(body.querySelectorAll(':scope > details.accordion-block'));
    if (!blocks.length) return;
    const order = ['Import / export', 'Legends', 'Universes', 'Worlds', 'Kingdoms / Regions', 'Cities / Settlements', 'Locations', 'Organizations / Factions', 'Characters', 'Weapons / Artifacts', 'Spells / Rituals / Techniques', 'Cycles / Conditions / Systems', 'Creatures / Animals / Fauna', 'Packs', 'Scenarios'];
    const byLabel = new Map(blocks.map(block => [trimValue(block.querySelector('summary')?.textContent), block]));
    order.forEach(label => {
      const node = byLabel.get(label);
      if (node) body.appendChild(node);
    });
  }
  function openLibraryAccordion(kind) {
    const wanted = trimValue(IMPORT_SECTION_SUMMARIES[kind]);
    if (!wanted) return;
    Array.from(document.querySelectorAll('#roleplay-library-panel details.accordion-block')).forEach(block => {
      const label = trimValue(block.querySelector('summary')?.textContent);
      if (label === wanted) block.open = true;
    });
  }
  function fillBuilderForKind(kind, record) {
    if (kind === 'character') return fillCharacterForm(record);
    if (kind === 'world') return fillWorldForm(record);
    if (kind === 'region') return fillRegionForm(record);
    if (kind === 'city') return fillCityForm(record);
    if (kind === 'location') return fillLocationForm(record);
    if (kind === 'organization') return fillOrganizationForm(record);
    if (kind === 'artifact') return fillArtifactForm(record);
    if (kind === 'ritual') return fillRitualForm(record);
    if (kind === 'cycle') return fillCycleForm(record);
    if (kind === 'creature') return fillCreatureForm(record);
    if (kind === 'universe') return fillUniverseForm(record);
    if (kind === 'legend') return fillLegendForm(record);
    if (kind === 'pack') return fillPackForm(record);
    if (kind === 'scenario') return fillScenarioForm(record);
  }
  function applyPreviewToBuilder() {
    const preview = state.importPreview;
    const records = Array.isArray(preview?.records) ? preview.records : [];
    const kind = trimValue(preview?.import_kind || records[0]?.kind);
    if (!preview || !records.length || !kind) { importStatus('Preview an import first.', 'warn'); return; }
    if (records.length !== 1) { importStatus('Apply to builder only works for single-record previews. Commit saves all records directly.', 'warn'); return; }
    openLibraryAccordion(kind);
    fillBuilderForKind(kind, records[0]);
    const statusId = importStatusIdForKind(kind);
    libraryStatus(statusId, 'Import preview loaded into the builder. Review and save or commit when ready.', 'ok');
    importStatus('Preview applied to the matching builder.', 'ok');
  }

  function currentSelectedLibraryRecordId(kind) {
    return trimValue(el(LIBRARY_SELECT_IDS[kind])?.value);
  }
  function parseDownloadFilename(headerValue = '', fallback = 'download.json') {
    const raw = trimValue(headerValue);
    if (!raw) return fallback;
    const utfMatch = raw.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch?.[1]) {
      try { return decodeURIComponent(utfMatch[1]); } catch (_err) { return utfMatch[1]; }
    }
    const plainMatch = raw.match(/filename="?([^";]+)"?/i);
    return trimValue(plainMatch?.[1]) || fallback;
  }
  async function downloadJsonFromApi(url, fallbackFilename) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      let message = 'Download failed.';
      try {
        const data = await response.json();
        message = data?.error || data?.message || message;
      } catch (_err) {}
      throw new Error(message);
    }
    const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackFilename);
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
    return filename;
  }

  function builderAssistStatusId(kind) { return `roleplay-builder-assist-status-${trimValue(kind)}`; }
  function builderAssistBriefId(kind) { return `roleplay-builder-assist-brief-${trimValue(kind)}`; }
  function builderAssistModeId(kind) { return `roleplay-builder-assist-mode-${trimValue(kind)}`; }
  function builderAssistButtonId(kind) { return `btn-roleplay-builder-assist-${trimValue(kind)}`; }
  function builderAssistCardMarkup(kind, config) {
    return `
      <div data-builder-assist-kind="${escapeHtml(kind)}" style="margin:14px 0 16px; border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:12px; background:rgba(255,255,255,.03);">
        <div class="row-between" style="gap:12px; align-items:flex-start;">
          <div>
            <div style="font-weight:600;">${escapeHtml(config.title || 'Builder assist')}</div>
            <div class="muted small" style="margin-top:4px;">${escapeHtml(config.hint || 'Draft fields into the form. Nothing is auto-saved.')}</div>
          </div>
          <div class="badge">Optional</div>
        </div>
        <label for="${escapeHtml(builderAssistBriefId(kind))}" style="margin-top:12px;">Brief</label>
        <textarea id="${escapeHtml(builderAssistBriefId(kind))}" rows="4" placeholder="Write a short brief for this ${escapeHtml(kind)}. Example: anxious transfer student, honors kid, hides anger behind neat politeness."></textarea>
        <div class="grid grid-2" style="margin-top:12px; gap:12px; align-items:end;">
          <div>
            <label for="${escapeHtml(builderAssistModeId(kind))}">Assist mode</label>
            <select id="${escapeHtml(builderAssistModeId(kind))}">
              <option value="fill_missing">Fill missing fields only</option>
              <option value="rewrite_current">Rewrite current draft</option>
            </select>
          </div>
          <div class="row" style="gap:8px; flex-wrap:wrap;">
            <button class="btn btn-small" id="${escapeHtml(builderAssistButtonId(kind))}" type="button">Draft fields into form</button>
          </div>
        </div>
        <div class="mini-note" style="margin-top:10px;">This updates the form only. Review it, then save manually when you are happy.</div>
        <div class="status" id="${escapeHtml(builderAssistStatusId(kind))}" style="margin-top:10px;"></div>
      </div>
    `;
  }
  function ensureBuilderAssistUi() {
    Array.from(document.querySelectorAll('#roleplay-library-panel details.accordion-block')).forEach(block => {
      const summaryText = trimValue(block.querySelector('summary')?.textContent);
      const entry = Object.entries(BUILDER_ASSIST_CONFIG).find(([, config]) => trimValue(config.summary) === summaryText);
      if (!entry) return;
      const [kind, config] = entry;
      if (block.querySelector(`[data-builder-assist-kind="${kind}"]`)) return;
      const host = document.createElement('div');
      host.innerHTML = builderAssistCardMarkup(kind, config);
      const card = host.firstElementChild;
      const summary = block.querySelector('summary');
      if (summary && card) summary.insertAdjacentElement('afterend', card);
    });
  }
  function builderAssistCurrentPayload(kind) {
    if (kind === 'character') return characterFormData();
    if (kind === 'world') return worldFormData();
    if (kind === 'location') return locationFormData();
    if (kind === 'scenario') return scenarioFormData();
    return {};
  }
  function hasMeaningfulBuilderDraft(payload) {
    return Object.entries(payload || {}).some(([key, value]) => key !== 'kind' && key !== 'record_id' && trimValue(value));
  }
  function applyBuilderAssistSuggestion(kind, suggestion, mode) {
    const fieldMap = BUILDER_ASSIST_FIELD_IDS[kind] || {};
    const applied = [];
    Object.entries(fieldMap).forEach(([field, id]) => {
      const node = el(id);
      if (!node) return;
      const nextValue = trimValue(suggestion?.[field]);
      if (!nextValue) return;
      const currentValue = trimValue(node.value);
      if (mode === 'fill_missing' && currentValue) return;
      node.value = nextValue;
      node.dispatchEvent(new Event('input', { bubbles: true }));
      node.dispatchEvent(new Event('change', { bubbles: true }));
      applied.push(field);
    });
    return applied;
  }
  function bindBuilderAssistActions() {
    ensureBuilderAssistUi();
    Object.keys(BUILDER_ASSIST_CONFIG).forEach(kind => {
      el(builderAssistButtonId(kind))?.addEventListener('click', async () => {
        const statusId = builderAssistStatusId(kind);
        if (!requireBackendRole('text', statusId, 'Connect a Text Backend first. Builder assist uses the active text model.')) return;
        const brief = trimValue(el(builderAssistBriefId(kind))?.value);
        const mode = trimValue(el(builderAssistModeId(kind))?.value) || 'fill_missing';
        const currentPayload = builderAssistCurrentPayload(kind);
        if (!brief && !hasMeaningfulBuilderDraft(currentPayload)) {
          libraryStatus(statusId, 'Add a brief or load a draft first.', 'warn');
          return;
        }
        if (mode === 'rewrite_current' && currentSelectedLibraryRecordId(kind)) {
          const ok = window.confirm('This will rewrite the current loaded draft in the form. It will not save automatically. Continue?');
          if (!ok) return;
        }
        const form = new FormData();
        form.append('kind', kind);
        form.append('brief', brief);
        form.append('mode', mode);
        form.append('model', typeof currentModel === 'function' ? currentModel() : 'default');
        form.append('current_record_json', JSON.stringify(currentPayload || {}));
        libraryStatus(statusId, 'Drafting builder fields...', '');
        setBusy(builderAssistButtonId(kind), true, 'Drafting...');
        try {
          const data = await safeFetchJson('/api/roleplay/library/builder-assist', { method: 'POST', body: form, cache: 'no-store' });
          const applied = applyBuilderAssistSuggestion(kind, data.suggestion || {}, mode);
          openLibraryAccordion(kind);
          if (!applied.length) {
            libraryStatus(statusId, 'The helper returned no usable field updates for this draft.', 'warn');
            return;
          }
          libraryStatus(statusId, `${data.message || 'Builder assist updated the form.'} Applied: ${applied.map(humanizeKey).join(', ')}.`, 'ok');
        } catch (err) {
          libraryStatus(statusId, err.message || 'Could not run builder assist.', 'warn');
        } finally {
          setBusy(builderAssistButtonId(kind), false);
        }
      });
    });
  }

  function populateSelect(selectId, items, placeholder, selected = '') {
    const node = el(selectId);
    if (!node) return;
    const current = trimValue(selected || node.value || '');
    node.innerHTML = '';
    const base = document.createElement('option');
    base.value = '';
    base.textContent = placeholder;
    node.appendChild(base);
    (Array.isArray(items) ? items : []).forEach(item => {
      const opt = document.createElement('option');
      opt.value = trimValue(item?.id);
      opt.textContent = optionLabel(item, placeholder.replace(/^Select\s+/i, '').replace(/^Choose\s+/i, ''));
      node.appendChild(opt);
    });
    node.value = current && Array.from(node.options).some(opt => opt.value === current) ? current : '';
  }

  function characterOptionNodes(selected = '') {
    const current = trimValue(selected);
    const opts = ['<option value="">Choose character</option>'];
    state.characters.forEach(item => {
      const id = trimValue(item?.id);
      opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Character'))}</option>`);
    });
    return opts.join('');
  }
  function worldOptionNodes(selected = '') {
    const current = trimValue(selected);
    const opts = ['<option value="">None</option>'];
    state.worlds.forEach(item => {
      const id = trimValue(item?.id);
      opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'World'))}</option>`);
    });
    return opts.join('');
  }

function regionOptionNodes(selected = '', worldId = '') {
    const current = trimValue(selected);
    const worldFilter = trimValue(worldId);
    const opts = ['<option value="">None</option>'];
    state.regions.filter(item => !worldFilter || trimValue(item?.world_id) === worldFilter).forEach(item => {
      const id = trimValue(item?.id);
      opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Region'))}</option>`);
    });
    return opts.join('');
  }

  function cityOptionNodes(selected = '', worldId = '', regionId = '') {
    const current = trimValue(selected);
    const worldFilter = trimValue(worldId);
    const regionFilter = trimValue(regionId);
    const opts = ['<option value="">None</option>'];
    state.cities
      .filter(item => (!worldFilter || trimValue(item?.world_id) === worldFilter) && (!regionFilter || trimValue(item?.region_id) === regionFilter))
      .forEach(item => {
        const id = trimValue(item?.id);
        opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'City'))}</option>`);
      });
    return opts.join('');
  }

  function locationMatches(item, { universeId = '', worldId = '', regionId = '', cityId = '' } = {}) {
    const itemUniverse = trimValue(item?.universe_id);
    const itemWorld = trimValue(item?.world_id);
    const itemRegion = trimValue(item?.region_id);
    const itemCity = trimValue(item?.city_id);
    const u = trimValue(universeId);
    const w = trimValue(worldId);
    const r = trimValue(regionId);
    const c = trimValue(cityId);
    if (c) return itemCity === c || (!itemCity && itemRegion === r) || (!itemCity && !itemRegion && itemWorld === w) || (!itemCity && !itemRegion && !itemWorld && itemUniverse === u);
    if (r) return itemRegion === r || (!itemRegion && itemWorld === w) || (!itemRegion && !itemWorld && itemUniverse === u);
    if (w) return itemWorld === w || (!itemWorld && itemUniverse === u);
    if (u) return itemUniverse === u;
    return true;
  }

  function locationOptionNodes(selected = '', filters = {}) {
    const current = trimValue(selected);
    const opts = ['<option value="">None</option>'];
    state.locations
      .filter(item => locationMatches(item, filters))
      .forEach(item => {
        const id = trimValue(item?.id);
        opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Location'))}</option>`);
      });
    return opts.join('');
  }

  function organizationOptionNodes(selectedValues = [], filters = {}) {
    const selected = new Set((Array.isArray(selectedValues) ? selectedValues : [selectedValues]).map(value => trimValue(value)).filter(Boolean));
    const universeFilter = trimValue(filters.universeId);
    const worldFilter = trimValue(filters.worldId);
    const regionFilter = trimValue(filters.regionId);
    const cityFilter = trimValue(filters.cityId);
    const excludeId = trimValue(filters.excludeId);
    return state.organizations
      .filter(item => (!universeFilter || trimValue(item?.universe_id) === universeFilter) && (!worldFilter || trimValue(item?.world_id) === worldFilter) && (!regionFilter || trimValue(item?.region_id) === regionFilter) && (!cityFilter || trimValue(item?.city_id) === cityFilter) && (!excludeId || trimValue(item?.id) !== excludeId))
      .map(item => {
        const id = trimValue(item?.id);
        return `<option value="${escapeHtml(id)}"${selected.has(id) ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Organization'))}</option>`;
      }).join('');
  }

  function artifactOptionNodes(selectedValues = []) {
    const selected = new Set((Array.isArray(selectedValues) ? selectedValues : []).map(value => trimValue(value)));
    return state.artifacts.map(item => {
      const id = trimValue(item?.id);
      return `<option value="${escapeHtml(id)}"${selected.has(id) ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Artifact'))}</option>`;
    }).join('');
  }

  function ritualOptionNodes(selectedValues = []) {
    const selected = new Set((Array.isArray(selectedValues) ? selectedValues : []).map(value => trimValue(value)));
    return state.rituals.map(item => {
      const id = trimValue(item?.id);
      return `<option value="${escapeHtml(id)}"${selected.has(id) ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Ritual'))}</option>`;
    }).join('');
  }

  function cycleOptionNodes(selectedValues = []) {
    const selected = new Set((Array.isArray(selectedValues) ? selectedValues : []).map(value => trimValue(value)));
    return state.cycles.map(item => {
      const id = trimValue(item?.id);
      return `<option value="${escapeHtml(id)}"${selected.has(id) ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Cycle'))}</option>`;
    }).join('');
  }

function creatureOptionNodes(selectedValues = [], categoryFilter = '') {
    const selected = new Set((Array.isArray(selectedValues) ? selectedValues : []).map(value => trimValue(value)));
    return state.creatures
      .filter(item => !categoryFilter || trimValue(item?.category) === categoryFilter)
      .map(item => {
        const id = trimValue(item?.id);
        return `<option value="${escapeHtml(id)}"${selected.has(id) ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Creature'))}</option>`;
      }).join('');
  }

function universeOptionNodes(selected = '') {
    const current = trimValue(selected);
    const opts = ['<option value="">None</option>'];
    state.universes.forEach(item => {
      const id = trimValue(item?.id);
      opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml(optionLabel(item, 'Universe'))}</option>`);
    });
    return opts.join('');
  }


  function selectedOptionValues(selectId) {
    return Array.from(el(selectId)?.selectedOptions || []).map(opt => trimValue(opt.value)).filter(Boolean);
  }

  function firstFilled(...values) {
    for (const value of values) {
      const clean = trimValue(value);
      if (clean) return clean;
    }
    return '';
  }

  function inferAiContextFromCurrentUI(kind = '') {
    const targetKind = trimValue(kind || el('roleplay-library-import-kind')?.value);
    const inferred = {
      universeId: '',
      worldId: '',
      regionId: '',
      cityId: '',
      locationId: '',
      scenarioId: '',
      speciesHint: '',
      organizationIds: [],
    };
    if (targetKind === 'character') {
      inferred.universeId = trimValue(el('roleplay-library-character-universe-id')?.value);
      inferred.worldId = firstFilled(el('roleplay-library-character-current-world-id')?.value, el('roleplay-world-id')?.value);
      inferred.regionId = trimValue(el('roleplay-library-character-current-region-id')?.value);
      inferred.cityId = trimValue(el('roleplay-library-character-current-city-id')?.value);
      inferred.locationId = trimValue(el('roleplay-library-character-current-location-id')?.value);
      inferred.speciesHint = trimValue(el('roleplay-library-character-species')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-character-organizations');
      inferred.scenarioId = trimValue(el('roleplay-scenario-id')?.value);
      return inferred;
    }
    if (targetKind === 'world') {
      inferred.universeId = trimValue(el('roleplay-library-world-universe-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-world-organizations');
      return inferred;
    }
    if (targetKind === 'region') {
      inferred.worldId = trimValue(el('roleplay-library-region-world-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-region-organizations');
      return inferred;
    }
    if (targetKind === 'city') {
      inferred.worldId = trimValue(el('roleplay-library-city-world-id')?.value);
      inferred.regionId = trimValue(el('roleplay-library-city-region-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-city-organizations');
      return inferred;
    }
    if (targetKind === 'location') {
      inferred.universeId = trimValue(el('roleplay-library-location-universe-id')?.value);
      inferred.worldId = trimValue(el('roleplay-library-location-world-id')?.value);
      inferred.regionId = trimValue(el('roleplay-library-location-region-id')?.value);
      inferred.cityId = trimValue(el('roleplay-library-location-city-id')?.value);
      inferred.locationId = trimValue(el('roleplay-library-location-parent-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-location-organizations');
      return inferred;
    }
    if (targetKind === 'organization') {
      inferred.universeId = trimValue(el('roleplay-library-organization-universe-id')?.value);
      inferred.worldId = trimValue(el('roleplay-library-organization-world-id')?.value);
      inferred.regionId = trimValue(el('roleplay-library-organization-region-id')?.value);
      inferred.cityId = trimValue(el('roleplay-library-organization-city-id')?.value);
      inferred.locationId = trimValue(el('roleplay-library-organization-base-location-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-organization-allies');
      return inferred;
    }
    if (targetKind === 'scenario') {
      inferred.worldId = firstFilled(el('roleplay-world-id')?.value, el('roleplay-library-character-current-world-id')?.value);
      inferred.regionId = trimValue(el('roleplay-library-scenario-location-region-id')?.value);
      inferred.cityId = trimValue(el('roleplay-library-scenario-location-city-id')?.value);
      inferred.locationId = trimValue(el('roleplay-library-scenario-location-id')?.value);
      inferred.organizationIds = selectedOptionValues('roleplay-library-scenario-organizations');
      inferred.scenarioId = firstFilled(el('roleplay-scenario-id')?.value, el('roleplay-library-scenario-select')?.value);
      return inferred;
    }
    inferred.worldId = trimValue(el('roleplay-world-id')?.value);
    inferred.scenarioId = trimValue(el('roleplay-scenario-id')?.value);
    return inferred;
  }

  function renderAiContextControls() {
    const inferred = inferAiContextFromCurrentUI();
    const universeId = firstFilled(el('roleplay-library-ai-universe-id')?.value, inferred.universeId);
    const worldId = firstFilled(el('roleplay-library-ai-world-id')?.value, inferred.worldId);
    const regionId = firstFilled(el('roleplay-library-ai-region-id')?.value, inferred.regionId);
    const cityId = firstFilled(el('roleplay-library-ai-city-id')?.value, inferred.cityId);
    const locationId = firstFilled(el('roleplay-library-ai-location-id')?.value, inferred.locationId);
    const scenarioId = firstFilled(el('roleplay-library-ai-scenario-id')?.value, inferred.scenarioId);
    const speciesHint = firstFilled(el('roleplay-library-ai-species-hint')?.value, inferred.speciesHint);
    const organizationIds = selectedOptionValues('roleplay-library-ai-organizations');
    const selectedOrganizations = organizationIds.length ? organizationIds : inferred.organizationIds;
    if (el('roleplay-library-ai-universe-id')) el('roleplay-library-ai-universe-id').innerHTML = universeOptionNodes(universeId);
    if (el('roleplay-library-ai-world-id')) el('roleplay-library-ai-world-id').innerHTML = worldOptionNodes(worldId);
    if (el('roleplay-library-ai-region-id')) el('roleplay-library-ai-region-id').innerHTML = regionOptionNodes(regionId, worldId);
    if (el('roleplay-library-ai-city-id')) el('roleplay-library-ai-city-id').innerHTML = cityOptionNodes(cityId, worldId, regionId);
    if (el('roleplay-library-ai-location-id')) el('roleplay-library-ai-location-id').innerHTML = locationOptionNodes(locationId, { universeId, worldId, regionId, cityId });
    if (el('roleplay-library-ai-scenario-id')) populateSelect('roleplay-library-ai-scenario-id', state.scenarios, 'None', scenarioId);
    setMultiSelectValues('roleplay-library-ai-organizations', selectedOrganizations, organizationOptionNodes(selectedOrganizations, { universeId, worldId, regionId, cityId }));
    if (el('roleplay-library-ai-species-hint') && !trimValue(el('roleplay-library-ai-species-hint')?.value) && speciesHint) el('roleplay-library-ai-species-hint').value = speciesHint;
  }

  function buildAiDraftContext(kind = '') {
    const inferred = inferAiContextFromCurrentUI(kind);
    return {
      universeId: firstFilled(el('roleplay-library-ai-universe-id')?.value, inferred.universeId),
      worldId: firstFilled(el('roleplay-library-ai-world-id')?.value, inferred.worldId),
      regionId: firstFilled(el('roleplay-library-ai-region-id')?.value, inferred.regionId),
      cityId: firstFilled(el('roleplay-library-ai-city-id')?.value, inferred.cityId),
      locationId: firstFilled(el('roleplay-library-ai-location-id')?.value, inferred.locationId),
      scenarioId: firstFilled(el('roleplay-library-ai-scenario-id')?.value, inferred.scenarioId),
      speciesHint: firstFilled(el('roleplay-library-ai-species-hint')?.value, inferred.speciesHint),
      organizationIds: (() => {
        const chosen = selectedOptionValues('roleplay-library-ai-organizations');
        return chosen.length ? chosen : inferred.organizationIds;
      })(),
    };
  }

  async function fetchState() {
    return safeFetchJson(`/api/roleplay/library/state?ts=${Date.now()}`, { cache: 'no-store' });
  }
  async function fetchRecord(kind, recordId) {
    const cleanId = trimValue(recordId);
    if (!cleanId) return null;
    if (cache[kind]?.has(cleanId)) return cache[kind].get(cleanId);
    const data = await safeFetchJson(`/api/roleplay/library/record?kind=${encodeURIComponent(kind)}&record_id=${encodeURIComponent(cleanId)}&ts=${Date.now()}`, { cache: 'no-store' });
    const record = data.record || null;
    if (record) cache[kind].set(cleanId, record);
    return record;
  }
  function stashRecord(kind, record) {
    const cleanId = trimValue(record?.id);
    if (!kind || !cleanId || !cache[kind]) return;
    cache[kind].set(cleanId, record);
  }
  function clearRecord(kind, recordId) {
    const cleanId = trimValue(recordId);
    if (!kind || !cleanId || !cache[kind]) return;
    cache[kind].delete(cleanId);
  }

  function renderRelationshipRows() {
    const root = el('roleplay-library-character-relationships');
    if (!root) return;
    if (!state.characterRelationships.length) state.characterRelationships = [{ target_id: '', target_name: '', relationship_type: 'friend', notes: '' }];
    root.innerHTML = '';
    state.characterRelationships.forEach((row, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Character</label><select data-rel-target data-index="${index}">${characterOptionNodes(row.target_id)}</select></div>
        <div><label>Type</label><select data-rel-type data-index="${index}">
          ${['friend','family','relative','enemy','rival','ally','mentor','student','lover','ex','other'].map(opt => `<option value="${opt}"${trimValue(row.relationship_type)===opt?' selected':''}>${humanizeKey(opt)}</option>`).join('')}
        </select></div>
        <div><label>Notes</label><input data-rel-notes data-index="${index}" type="text" value="${escapeHtml(row.notes || '')}" placeholder="Bond, history, tension..."/></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-rel-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
  }
  function renderAbilityRows() {
    const root = el('roleplay-library-character-abilities');
    if (!root) return;
    root.innerHTML = '';
    state.characterAbilities.forEach((row, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Ability</label><input data-ability-name data-index="${index}" type="text" value="${escapeHtml(row.name || '')}" placeholder="Moonfire"/></div>
        <div><label>State</label><select data-ability-state data-index="${index}">
          ${['active','dormant','latent','sealed','unstable','lost','custom'].map(opt => `<option value="${opt}"${trimValue(row.state)===opt?' selected':''}>${humanizeKey(opt)}</option>`).join('')}
        </select></div>
        <div><label>Notes</label><input data-ability-notes data-index="${index}" type="text" value="${escapeHtml(row.notes || '')}" placeholder="What it does / limits"/></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-ability-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
  }
  function renderWardrobeRows() {
    const root = el('roleplay-library-character-wardrobes');
    if (!root) return;
    root.innerHTML = '';
    state.characterWardrobes.forEach((row, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Look label</label><input data-wardrobe-label data-index="${index}" type="text" value="${escapeHtml(row.label || '')}" placeholder="Everyday black layers"/></div>
        <div style="grid-column: span 2;"><label>Notes</label><input data-wardrobe-notes data-index="${index}" type="text" value="${escapeHtml(row.notes || '')}" placeholder="Fabrics, vibe, recurring outfit notes"/></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-wardrobe-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
  }
  function renderHookRows() {
    const root = el('roleplay-library-character-hooks');
    if (!root) return;
    root.innerHTML = '';
    state.characterHooks.forEach((row, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Hook type</label><select data-hook-type data-index="${index}">
          ${['dream','vision','omen','secret','oath','prophecy','memory_shard','past_life','other'].map(opt => `<option value="${opt}"${trimValue(row.type)===opt?' selected':''}>${humanizeKey(opt)}</option>`).join('')}
        </select></div>
        <div><label>Label</label><input data-hook-title data-index="${index}" type="text" value="${escapeHtml(row.title || '')}" placeholder="Recurring bell dream"/></div>
        <div style="grid-column: span 2;"><label>Notes</label><input data-hook-notes data-index="${index}" type="text" value="${escapeHtml(row.notes || '')}" placeholder="Why it matters in the story"/></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-hook-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
  }
  function renderScenarioCastRows() {
    const root = el('roleplay-library-scenario-cast');
    if (!root) return;
    root.innerHTML = '';
    state.scenarioCast.forEach((row, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Character</label><select data-scn-cast-character data-index="${index}">${characterOptionNodes(row.character_id)}</select></div>
        <div><label>Scene role</label><select data-scn-cast-role data-index="${index}">${['pov','partner','lead','supporting','antagonist','narrator','npc','off_screen'].map(opt => `<option value="${opt}"${trimValue(row.scene_role)===opt?' selected':''}>${humanizeKey(opt)}</option>`).join('')}</select></div>
        <div><label>Presence</label><select data-scn-cast-presence data-index="${index}">${['on_scene','nearby','off_screen','mentioned_only'].map(opt => `<option value="${opt}"${trimValue(row.presence)===opt?' selected':''}>${humanizeKey(opt)}</option>`).join('')}</select></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-scn-cast-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
  }

  function syncRelationshipStateFromDom() {
    const root = el('roleplay-library-character-relationships');
    if (!root) return;
    state.characterRelationships = Array.from(root.querySelectorAll('[data-rel-target]')).map(node => {
      const idx = node.getAttribute('data-index');
      const targetId = trimValue(node.value);
      const selectedText = trimValue(node.selectedOptions?.[0]?.textContent || '').replace(/\s+—.*$/, '');
      return {
        target_id: targetId,
        target_name: targetId ? selectedText : '',
        relationship_type: trimValue(root.querySelector(`[data-rel-type][data-index="${idx}"]`)?.value) || 'friend',
        notes: trimValue(root.querySelector(`[data-rel-notes][data-index="${idx}"]`)?.value),
      };
    }).filter(row => row.target_id || row.notes);
  }
  function syncAbilityStateFromDom() {
    const root = el('roleplay-library-character-abilities');
    if (!root) return;
    state.characterAbilities = Array.from(root.querySelectorAll('[data-ability-name]')).map(node => {
      const idx = node.getAttribute('data-index');
      return {
        name: trimValue(node.value),
        state: trimValue(root.querySelector(`[data-ability-state][data-index="${idx}"]`)?.value) || 'active',
        notes: trimValue(root.querySelector(`[data-ability-notes][data-index="${idx}"]`)?.value),
      };
    }).filter(row => row.name || row.notes);
  }
  function syncWardrobeStateFromDom() {
    const root = el('roleplay-library-character-wardrobes');
    if (!root) return;
    state.characterWardrobes = Array.from(root.querySelectorAll('[data-wardrobe-label]')).map(node => {
      const idx = node.getAttribute('data-index');
      return { label: trimValue(node.value), notes: trimValue(root.querySelector(`[data-wardrobe-notes][data-index="${idx}"]`)?.value) };
    }).filter(row => row.label || row.notes);
  }
  function syncHookStateFromDom() {
    const root = el('roleplay-library-character-hooks');
    if (!root) return;
    state.characterHooks = Array.from(root.querySelectorAll('[data-hook-type]')).map(node => {
      const idx = node.getAttribute('data-index');
      return {
        type: trimValue(node.value) || 'other',
        title: trimValue(root.querySelector(`[data-hook-title][data-index="${idx}"]`)?.value),
        notes: trimValue(root.querySelector(`[data-hook-notes][data-index="${idx}"]`)?.value),
      };
    }).filter(row => row.title || row.notes);
  }
  function syncScenarioCastStateFromDom() {
    const root = el('roleplay-library-scenario-cast');
    if (!root) return;
    state.scenarioCast = Array.from(root.querySelectorAll('[data-scn-cast-character]')).map(node => {
      const idx = node.getAttribute('data-index');
      const characterId = trimValue(node.value);
      const selectedText = trimValue(node.selectedOptions?.[0]?.textContent || '').replace(/\s+—.*$/, '');
      return {
        character_id: characterId,
        character_name: characterId ? selectedText : '',
        scene_role: trimValue(root.querySelector(`[data-scn-cast-role][data-index="${idx}"]`)?.value) || 'supporting',
        presence: trimValue(root.querySelector(`[data-scn-cast-presence][data-index="${idx}"]`)?.value) || 'on_scene',
      };
    }).filter(row => row.character_id || row.character_name);
  }

  function fillCharacterForm(record = null) {
    const item = record || {};
    state.characterRelationships = parseJsonArray(item.relationships, []);
    state.characterAbilities = parseJsonArray(item.abilities, []);
    state.characterWardrobes = parseJsonArray(item.wardrobes, []);
    state.characterHooks = parseJsonArray(item.story_hooks, []);
    if (el('roleplay-library-character-select')) el('roleplay-library-character-select').value = trimValue(item.id);
    if (el('roleplay-library-character-name')) el('roleplay-library-character-name').value = item.name || '';
    if (el('roleplay-library-character-display-name')) el('roleplay-library-character-display-name').value = item.display_name || '';
    if (el('roleplay-library-character-gender')) el('roleplay-library-character-gender').value = item.gender || '';
    if (el('roleplay-library-character-pronouns')) el('roleplay-library-character-pronouns').value = item.pronouns || '';
    if (el('roleplay-library-character-role-tier')) el('roleplay-library-character-role-tier').value = item.role_tier || 'main';
    if (el('roleplay-library-character-species')) el('roleplay-library-character-species').value = item.species || '';
    if (el('roleplay-library-character-designation')) el('roleplay-library-character-designation').value = item.designation || '';
    if (el('roleplay-library-character-occupation')) el('roleplay-library-character-occupation').value = item.occupation || '';
    if (el('roleplay-library-character-origin-world-id')) el('roleplay-library-character-origin-world-id').value = item.origin_world_id || '';
    if (el('roleplay-library-character-current-world-id')) el('roleplay-library-character-current-world-id').value = item.current_world_id || item.world_id || '';
    if (el('roleplay-library-character-origin-region-id')) el('roleplay-library-character-origin-region-id').innerHTML = regionOptionNodes(item.origin_region_id || '', item.origin_world_id || '');
    if (el('roleplay-library-character-current-region-id')) el('roleplay-library-character-current-region-id').innerHTML = regionOptionNodes(item.current_region_id || '', item.current_world_id || item.world_id || '');
    if (el('roleplay-library-character-origin-city-id')) el('roleplay-library-character-origin-city-id').innerHTML = cityOptionNodes(item.origin_city_id || '', item.origin_world_id || '', item.origin_region_id || '');
    if (el('roleplay-library-character-current-city-id')) el('roleplay-library-character-current-city-id').innerHTML = cityOptionNodes(item.current_city_id || '', item.current_world_id || item.world_id || '', item.current_region_id || '');
    if (el('roleplay-library-character-origin-location-id')) el('roleplay-library-character-origin-location-id').innerHTML = locationOptionNodes(item.origin_location_id || '', { worldId: item.origin_world_id || '', regionId: item.origin_region_id || '', cityId: item.origin_city_id || '' });
    if (el('roleplay-library-character-current-location-id')) el('roleplay-library-character-current-location-id').innerHTML = locationOptionNodes(item.current_location_id || '', { worldId: item.current_world_id || item.world_id || '', regionId: item.current_region_id || '', cityId: item.current_city_id || '' });
    if (el('roleplay-library-character-summary')) el('roleplay-library-character-summary').value = item.summary || '';
    if (el('roleplay-library-character-appearance')) el('roleplay-library-character-appearance').value = item.appearance || '';
    if (el('roleplay-library-character-personality')) el('roleplay-library-character-personality').value = item.personality || '';
    if (el('roleplay-library-character-speech-style')) el('roleplay-library-character-speech-style').value = item.speech_style || '';
    if (el('roleplay-library-character-relationship-notes')) el('roleplay-library-character-relationship-notes').value = item.relationship_notes || '';
    if (el('roleplay-library-character-affiliations')) el('roleplay-library-character-affiliations').value = item.affiliations || '';
    if (el('roleplay-library-character-hobbies')) el('roleplay-library-character-hobbies').value = item.hobbies || '';
    if (el('roleplay-library-character-student-details')) el('roleplay-library-character-student-details').value = item.student_details || '';
    if (el('roleplay-library-character-current-location-label')) el('roleplay-library-character-current-location-label').value = item.current_location_label || '';
    if (el('roleplay-library-character-canon-notes')) el('roleplay-library-character-canon-notes').value = item.canon_notes || '';
    setMultiSelectValues('roleplay-library-character-artifacts', item.artifact_ids || [], artifactOptionNodes(item.artifact_ids || []));
    setMultiSelectValues('roleplay-library-character-rituals', item.ritual_ids || [], ritualOptionNodes(item.ritual_ids || []));
    setMultiSelectValues('roleplay-library-character-cycles', item.cycle_ids || [], cycleOptionNodes(item.cycle_ids || []));
    setMultiSelectValues('roleplay-library-character-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { worldId: item.current_world_id || item.world_id || '', regionId: item.current_region_id || '', cityId: item.current_city_id || '' }));
    renderRelationshipRows();
    renderAbilityRows();
    renderWardrobeRows();
    renderHookRows();
    setImagePreview('roleplay-library-character-avatar-preview', 'roleplay-library-character-avatar-empty', (item.avatar || {}).image_path || '');
  }

  function fillWorldForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-world-select')) el('roleplay-library-world-select').value = trimValue(item.id);
    if (el('roleplay-library-world-name')) el('roleplay-library-world-name').value = item.name || '';
    if (el('roleplay-library-world-summary')) el('roleplay-library-world-summary').value = item.summary || '';
    if (el('roleplay-library-world-realm-type')) el('roleplay-library-world-realm-type').value = item.realm_type || '';
    if (el('roleplay-library-world-calendar-notes')) el('roleplay-library-world-calendar-notes').value = item.calendar_notes || '';
    if (el('roleplay-library-world-lore')) el('roleplay-library-world-lore').value = item.lore || '';
    if (el('roleplay-library-world-rules')) el('roleplay-library-world-rules').value = item.rules || '';
    if (el('roleplay-library-world-geography-notes')) el('roleplay-library-world-geography-notes').value = item.geography_notes || '';
    if (el('roleplay-library-world-society-notes')) el('roleplay-library-world-society-notes').value = item.society_notes || '';
    if (el('roleplay-library-world-faith-notes')) el('roleplay-library-world-faith-notes').value = item.faith_notes || '';
    if (el('roleplay-library-world-people-notes')) el('roleplay-library-world-people-notes').value = item.people_notes || '';
    if (el('roleplay-library-world-canon-notes')) el('roleplay-library-world-canon-notes').value = item.canon_notes || '';
    setMultiSelectValues('roleplay-library-world-inhabitant-species', item.inhabitant_species_ids || [], creatureOptionNodes(item.inhabitant_species_ids || []));
    setMultiSelectValues('roleplay-library-world-creature-fauna', item.creature_fauna_ids || [], creatureOptionNodes(item.creature_fauna_ids || []));
    setMultiSelectValues('roleplay-library-world-cycles', item.cycle_ids || [], cycleOptionNodes(item.cycle_ids || []));
    setMultiSelectValues('roleplay-library-world-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { universeId: item.universe_id || '' }));
  }

  function fillUniverseForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-universe-select')) el('roleplay-library-universe-select').value = trimValue(item.id);
    if (el('roleplay-library-universe-name')) el('roleplay-library-universe-name').value = item.name || '';
    if (el('roleplay-library-universe-summary')) el('roleplay-library-universe-summary').value = item.summary || '';
    if (el('roleplay-library-universe-canon-notes')) el('roleplay-library-universe-canon-notes').value = item.canon_notes || '';
  }

  function fillLegendForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-legend-select')) el('roleplay-library-legend-select').value = trimValue(item.id);
    if (el('roleplay-library-legend-title')) el('roleplay-library-legend-title').value = item.title || '';
    if (el('roleplay-library-legend-scope')) el('roleplay-library-legend-scope').value = item.scope || 'world';
    if (el('roleplay-library-legend-type')) el('roleplay-library-legend-type').value = item.legend_type || 'myth';
    if (el('roleplay-library-legend-truth')) el('roleplay-library-legend-truth').value = item.truth_status || 'disputed';
    if (el('roleplay-library-legend-universe-id')) el('roleplay-library-legend-universe-id').innerHTML = universeOptionNodes(item.universe_id || '');
    if (el('roleplay-library-legend-world-id')) el('roleplay-library-legend-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-legend-public-version')) el('roleplay-library-legend-public-version').value = item.public_version || '';
    if (el('roleplay-library-legend-hidden-version')) el('roleplay-library-legend-hidden-version').value = item.hidden_version || '';
    if (el('roleplay-library-legend-canon-notes')) el('roleplay-library-legend-canon-notes').value = item.canon_notes || '';
  }

  function fillPackForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-pack-select')) el('roleplay-library-pack-select').value = trimValue(item.id);
    if (el('roleplay-library-pack-title')) el('roleplay-library-pack-title').value = item.title || '';
    if (el('roleplay-library-pack-type')) el('roleplay-library-pack-type').value = item.pack_type || 'rule';
    if (el('roleplay-library-pack-summary')) el('roleplay-library-pack-summary').value = item.summary || '';
    if (el('roleplay-library-pack-content')) el('roleplay-library-pack-content').value = item.content || '';
    if (el('roleplay-library-pack-canon-notes')) el('roleplay-library-pack-canon-notes').value = item.canon_notes || '';
  }

  function fillRegionForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-region-select')) el('roleplay-library-region-select').value = trimValue(item.id);
    if (el('roleplay-library-region-name')) el('roleplay-library-region-name').value = item.name || '';
    if (el('roleplay-library-region-type')) el('roleplay-library-region-type').value = item.region_type || 'kingdom';
    if (el('roleplay-library-region-world-id')) el('roleplay-library-region-world-id').value = item.world_id || '';
    if (el('roleplay-library-region-parent-id')) el('roleplay-library-region-parent-id').innerHTML = regionOptionNodes(item.parent_region_id || '', item.world_id || '');
    setMultiSelectValues('roleplay-library-region-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { worldId: item.world_id || '' }));
    if (el('roleplay-library-region-parent-id')) el('roleplay-library-region-parent-id').value = item.parent_region_id || '';
    if (el('roleplay-library-region-summary')) el('roleplay-library-region-summary').value = item.summary || '';
    if (el('roleplay-library-region-canon-notes')) el('roleplay-library-region-canon-notes').value = item.canon_notes || '';
  }

  function fillCityForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-city-select')) el('roleplay-library-city-select').value = trimValue(item.id);
    if (el('roleplay-library-city-name')) el('roleplay-library-city-name').value = item.name || '';
    if (el('roleplay-library-city-type')) el('roleplay-library-city-type').value = item.city_type || 'city';
    if (el('roleplay-library-city-world-id')) el('roleplay-library-city-world-id').value = item.world_id || '';
    if (el('roleplay-library-city-region-id')) el('roleplay-library-city-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    setMultiSelectValues('roleplay-library-city-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { worldId: item.world_id || '', regionId: item.region_id || '' }));
    if (el('roleplay-library-city-region-id')) el('roleplay-library-city-region-id').value = item.region_id || '';
    if (el('roleplay-library-city-summary')) el('roleplay-library-city-summary').value = item.summary || '';
    if (el('roleplay-library-city-access-notes')) el('roleplay-library-city-access-notes').value = item.access_notes || '';
    if (el('roleplay-library-city-canon-notes')) el('roleplay-library-city-canon-notes').value = item.canon_notes || '';
  }

  function fillLocationForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-location-select')) el('roleplay-library-location-select').value = trimValue(item.id);
    if (el('roleplay-library-location-name')) el('roleplay-library-location-name').value = item.name || '';
    if (el('roleplay-library-location-display-name')) el('roleplay-library-location-display-name').value = item.display_name || '';
    if (el('roleplay-library-location-function-label')) el('roleplay-library-location-function-label').value = item.function_label || '';
    if (el('roleplay-library-location-type')) el('roleplay-library-location-type').value = item.location_type || 'building';
    if (el('roleplay-library-location-anchor-type')) el('roleplay-library-location-anchor-type').value = item.anchor_type || 'world';
    if (el('roleplay-library-location-universe-id')) el('roleplay-library-location-universe-id').innerHTML = universeOptionNodes(item.universe_id || '');
    if (el('roleplay-library-location-world-id')) el('roleplay-library-location-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-location-region-id')) el('roleplay-library-location-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    if (el('roleplay-library-location-city-id')) el('roleplay-library-location-city-id').innerHTML = cityOptionNodes(item.city_id || '', item.world_id || '', item.region_id || '');
    if (el('roleplay-library-location-parent-id')) el('roleplay-library-location-parent-id').innerHTML = locationOptionNodes(item.parent_location_id || '', { universeId: item.universe_id || '', worldId: item.world_id || '', regionId: item.region_id || '', cityId: item.city_id || '' });
    if (el('roleplay-library-location-universe-id')) el('roleplay-library-location-universe-id').value = item.universe_id || '';
    if (el('roleplay-library-location-world-id')) el('roleplay-library-location-world-id').value = item.world_id || '';
    if (el('roleplay-library-location-region-id')) el('roleplay-library-location-region-id').value = item.region_id || '';
    if (el('roleplay-library-location-city-id')) el('roleplay-library-location-city-id').value = item.city_id || '';
    if (el('roleplay-library-location-parent-id')) el('roleplay-library-location-parent-id').value = item.parent_location_id || '';
    if (el('roleplay-library-location-summary')) el('roleplay-library-location-summary').value = item.summary || '';
    if (el('roleplay-library-location-atmosphere')) el('roleplay-library-location-atmosphere').value = item.atmosphere || '';
    setMultiSelectValues('roleplay-library-location-scene-uses', item.scene_uses || [], Array.from(el('roleplay-library-location-scene-uses')?.options || []).map(opt => `<option value="${escapeHtml(opt.value)}">${escapeHtml(opt.textContent || opt.value)}</option>`).join(''));
    if (el('roleplay-library-location-access-notes')) el('roleplay-library-location-access-notes').value = item.access_notes || '';
    if (el('roleplay-library-location-hazards')) el('roleplay-library-location-hazards').value = item.hazards || '';
    if (el('roleplay-library-location-rules')) el('roleplay-library-location-rules').value = item.rules || '';
    if (el('roleplay-library-location-public-notes')) el('roleplay-library-location-public-notes').value = item.public_notes || '';
    if (el('roleplay-library-location-hidden-truth')) el('roleplay-library-location-hidden-truth').value = item.hidden_truth || '';
    setMultiSelectValues('roleplay-library-location-artifacts', item.artifact_ids || [], artifactOptionNodes(item.artifact_ids || []));
    setMultiSelectValues('roleplay-library-location-rituals', item.ritual_ids || [], ritualOptionNodes(item.ritual_ids || []));
    setMultiSelectValues('roleplay-library-location-cycles', item.cycle_ids || [], cycleOptionNodes(item.cycle_ids || []));
    setMultiSelectValues('roleplay-library-location-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { universeId: item.universe_id || '', worldId: item.world_id || '', regionId: item.region_id || '', cityId: item.city_id || '' }));
    if (el('roleplay-library-location-canon-notes')) el('roleplay-library-location-canon-notes').value = item.canon_notes || '';
  }

  function fillArtifactForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-artifact-select')) el('roleplay-library-artifact-select').value = trimValue(item.id);
    if (el('roleplay-library-artifact-name')) el('roleplay-library-artifact-name').value = item.name || '';
    if (el('roleplay-library-artifact-type')) el('roleplay-library-artifact-type').value = item.item_type || 'weapon';
    if (el('roleplay-library-artifact-rarity')) el('roleplay-library-artifact-rarity').value = item.rarity || 'normal';
    if (el('roleplay-library-artifact-state')) el('roleplay-library-artifact-state').value = item.state || 'active';
    if (el('roleplay-library-artifact-world-id')) el('roleplay-library-artifact-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-artifact-region-id')) el('roleplay-library-artifact-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    if (el('roleplay-library-artifact-city-id')) el('roleplay-library-artifact-city-id').innerHTML = cityOptionNodes(item.city_id || '', item.world_id || '', item.region_id || '');
    if (el('roleplay-library-artifact-location-id')) el('roleplay-library-artifact-location-id').innerHTML = locationOptionNodes(item.location_id || '', { worldId: item.world_id || '', regionId: item.region_id || '', cityId: item.city_id || '' });
    if (el('roleplay-library-artifact-holder-id')) el('roleplay-library-artifact-holder-id').innerHTML = characterOptionNodes(item.current_holder_character_id || '');
    if (el('roleplay-library-artifact-world-id')) el('roleplay-library-artifact-world-id').value = item.world_id || '';
    if (el('roleplay-library-artifact-region-id')) el('roleplay-library-artifact-region-id').value = item.region_id || '';
    if (el('roleplay-library-artifact-city-id')) el('roleplay-library-artifact-city-id').value = item.city_id || '';
    if (el('roleplay-library-artifact-location-id')) el('roleplay-library-artifact-location-id').value = item.location_id || '';
    if (el('roleplay-library-artifact-holder-id')) el('roleplay-library-artifact-holder-id').value = item.current_holder_character_id || '';
    if (el('roleplay-library-artifact-source')) el('roleplay-library-artifact-source').value = item.source_tradition || '';
    if (el('roleplay-library-artifact-summary')) el('roleplay-library-artifact-summary').value = item.summary || '';
    if (el('roleplay-library-artifact-effects')) el('roleplay-library-artifact-effects').value = item.effects || '';
    if (el('roleplay-library-artifact-costs')) el('roleplay-library-artifact-costs').value = item.costs || '';
    if (el('roleplay-library-artifact-activation')) el('roleplay-library-artifact-activation').value = item.activation || '';
    if (el('roleplay-library-artifact-lawful-status')) el('roleplay-library-artifact-lawful-status').value = item.lawful_status || '';
    if (el('roleplay-library-artifact-canon-notes')) el('roleplay-library-artifact-canon-notes').value = item.canon_notes || '';
  }

  function fillRitualForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-ritual-select')) el('roleplay-library-ritual-select').value = trimValue(item.id);
    if (el('roleplay-library-ritual-name')) el('roleplay-library-ritual-name').value = item.name || '';
    if (el('roleplay-library-ritual-type')) el('roleplay-library-ritual-type').value = item.ritual_type || 'ritual';
    if (el('roleplay-library-ritual-school')) el('roleplay-library-ritual-school').value = item.school || '';
    if (el('roleplay-library-ritual-state')) el('roleplay-library-ritual-state').value = item.state || 'known';
    if (el('roleplay-library-ritual-world-id')) el('roleplay-library-ritual-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-ritual-region-id')) el('roleplay-library-ritual-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    if (el('roleplay-library-ritual-location-id')) el('roleplay-library-ritual-location-id').innerHTML = locationOptionNodes(item.location_id || '', { worldId: item.world_id || '', regionId: item.region_id || '' });
    if (el('roleplay-library-ritual-world-id')) el('roleplay-library-ritual-world-id').value = item.world_id || '';
    if (el('roleplay-library-ritual-region-id')) el('roleplay-library-ritual-region-id').value = item.region_id || '';
    if (el('roleplay-library-ritual-location-id')) el('roleplay-library-ritual-location-id').value = item.location_id || '';
    if (el('roleplay-library-ritual-effect-summary')) el('roleplay-library-ritual-effect-summary').value = item.effect_summary || '';
    if (el('roleplay-library-ritual-requirements')) el('roleplay-library-ritual-requirements').value = item.requirements || '';
    if (el('roleplay-library-ritual-risks')) el('roleplay-library-ritual-risks').value = item.risks || '';
    if (el('roleplay-library-ritual-lawful-status')) el('roleplay-library-ritual-lawful-status').value = item.lawful_status || '';
    if (el('roleplay-library-ritual-canon-notes')) el('roleplay-library-ritual-canon-notes').value = item.canon_notes || '';
  }

  function fillCycleForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-cycle-select')) el('roleplay-library-cycle-select').value = trimValue(item.id);
    if (el('roleplay-library-cycle-name')) el('roleplay-library-cycle-name').value = item.name || '';
    if (el('roleplay-library-cycle-type')) el('roleplay-library-cycle-type').value = item.cycle_type || 'celestial';
    if (el('roleplay-library-cycle-scope-type')) el('roleplay-library-cycle-scope-type').value = item.scope_type || 'world';
    if (el('roleplay-library-cycle-universe-id')) el('roleplay-library-cycle-universe-id').innerHTML = universeOptionNodes(item.universe_id || '');
    if (el('roleplay-library-cycle-world-id')) el('roleplay-library-cycle-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-cycle-region-id')) el('roleplay-library-cycle-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    if (el('roleplay-library-cycle-location-id')) el('roleplay-library-cycle-location-id').innerHTML = locationOptionNodes(item.location_id || '', { universeId: item.universe_id || '', worldId: item.world_id || '', regionId: item.region_id || '' });
    if (el('roleplay-library-cycle-universe-id')) el('roleplay-library-cycle-universe-id').value = item.universe_id || '';
    if (el('roleplay-library-cycle-world-id')) el('roleplay-library-cycle-world-id').value = item.world_id || '';
    if (el('roleplay-library-cycle-region-id')) el('roleplay-library-cycle-region-id').value = item.region_id || '';
    if (el('roleplay-library-cycle-location-id')) el('roleplay-library-cycle-location-id').value = item.location_id || '';
    if (el('roleplay-library-cycle-affected-species')) el('roleplay-library-cycle-affected-species').value = item.affected_species || '';
    if (el('roleplay-library-cycle-affected-designation')) el('roleplay-library-cycle-affected-designation').value = item.affected_designation || '';
    if (el('roleplay-library-cycle-cadence')) el('roleplay-library-cycle-cadence').value = item.cadence || '';
    if (el('roleplay-library-cycle-trigger')) el('roleplay-library-cycle-trigger').value = item.trigger || '';
    if (el('roleplay-library-cycle-stages')) el('roleplay-library-cycle-stages').value = item.stages || '';
    if (el('roleplay-library-cycle-effects')) el('roleplay-library-cycle-effects').value = item.effects || '';
    if (el('roleplay-library-cycle-safeguards')) el('roleplay-library-cycle-safeguards').value = item.safeguards || '';
    if (el('roleplay-library-cycle-canon-notes')) el('roleplay-library-cycle-canon-notes').value = item.canon_notes || '';
  }

  function setMultiSelectValues(selectId, values, html) {
    const node = el(selectId);
    if (!node) return;
    node.innerHTML = html;
    const want = new Set((Array.isArray(values) ? values : []).map(value => trimValue(value)));
    Array.from(node.options).forEach(opt => { opt.selected = want.has(trimValue(opt.value)); });
  }

  function fillCreatureForm(record = null) {
    const item = record || {};
    if (el('roleplay-library-creature-select')) el('roleplay-library-creature-select').value = trimValue(item.id);
    if (el('roleplay-library-creature-name')) el('roleplay-library-creature-name').value = item.name || '';
    if (el('roleplay-library-creature-category')) el('roleplay-library-creature-category').value = item.category || 'creature';
    if (el('roleplay-library-creature-world-id')) el('roleplay-library-creature-world-id').value = item.world_id || '';
    if (el('roleplay-library-creature-sentience')) el('roleplay-library-creature-sentience').value = item.sentience || 'unknown';
    if (el('roleplay-library-creature-summary')) el('roleplay-library-creature-summary').value = item.summary || '';
    if (el('roleplay-library-creature-canon-notes')) el('roleplay-library-creature-canon-notes').value = item.canon_notes || '';
  }

  function fillScenarioForm(record = null) {
    const item = record || {};
    state.scenarioCast = parseJsonArray(item.cast, []);
    if (el('roleplay-library-scenario-select')) el('roleplay-library-scenario-select').value = trimValue(item.id);
    if (el('roleplay-library-scenario-title')) el('roleplay-library-scenario-title').value = item.title || '';
    if (el('roleplay-library-scenario-tone')) el('roleplay-library-scenario-tone').value = item.tone || '';
    if (el('roleplay-library-scenario-location-label')) el('roleplay-library-scenario-location-label').value = item.location_label || '';
    if (el('roleplay-library-scenario-location-region-id')) el('roleplay-library-scenario-location-region-id').innerHTML = regionOptionNodes(item.location_region_id || '', item.world_id || '');
    if (el('roleplay-library-scenario-location-city-id')) el('roleplay-library-scenario-location-city-id').innerHTML = cityOptionNodes(item.location_city_id || '', item.world_id || '', item.location_region_id || '');
    if (el('roleplay-library-scenario-location-id')) el('roleplay-library-scenario-location-id').innerHTML = locationOptionNodes(item.location_id || '', { worldId: item.world_id || '', regionId: item.location_region_id || '', cityId: item.location_city_id || '' });
    setMultiSelectValues('roleplay-library-scenario-organizations', item.organization_ids || [], organizationOptionNodes(item.organization_ids || [], { worldId: item.world_id || '', regionId: item.location_region_id || '', cityId: item.location_city_id || '' }));
    if (el('roleplay-library-scenario-objective')) el('roleplay-library-scenario-objective').value = item.objective || '';
    if (el('roleplay-library-scenario-premise')) el('roleplay-library-scenario-premise').value = item.premise || '';
    if (el('roleplay-library-scenario-opening-beat')) el('roleplay-library-scenario-opening-beat').value = item.opening_beat || '';
    if (el('roleplay-library-scenario-scene-notes')) el('roleplay-library-scenario-scene-notes').value = item.scene_notes || '';
    renderScenarioCastRows();
  }

  function applyCharacterToSurface(record, target) {
    if (!record) return;
    const displayName = trimValue(record.display_name || record.name);
    if (target === 'user') {
      if (el('roleplay-user-character-id')) el('roleplay-user-character-id').value = trimValue(record.id);
      if (el('roleplay-user-name') && displayName) el('roleplay-user-name').value = displayName;
    } else {
      if (el('roleplay-partner-character-id')) el('roleplay-partner-character-id').value = trimValue(record.id);
      if (el('roleplay-partner-name') && displayName) el('roleplay-partner-name').value = displayName;
    }
    setMultiSelectValues('roleplay-library-region-organizations', Array.from(el('roleplay-library-region-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-region-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: el('roleplay-library-region-world-id')?.value }));
    setMultiSelectValues('roleplay-library-city-organizations', Array.from(el('roleplay-library-city-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-city-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: el('roleplay-library-city-world-id')?.value, regionId: el('roleplay-library-city-region-id')?.value }));
    setMultiSelectValues('roleplay-library-scenario-organizations', Array.from(el('roleplay-library-scenario-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-scenario-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value, regionId: el('roleplay-library-scenario-location-region-id')?.value, cityId: el('roleplay-library-scenario-location-city-id')?.value }));
    setMultiSelectValues('roleplay-library-organization-allies', Array.from(el('roleplay-library-organization-allies')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-organization-allies')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-organization-rivals', Array.from(el('roleplay-library-organization-rivals')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-organization-rivals')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    window.neoRefreshRoleplayLibrarySelections?.();
  }
  function applyWorldToSurface(record) {
    if (!record) return;
    if (el('roleplay-world-id')) el('roleplay-world-id').value = trimValue(record.id);
    if (el('roleplay-story-world') && !trimValue(el('roleplay-story-world').value) && trimValue(record.name)) el('roleplay-story-world').value = trimValue(record.name);
    window.neoRefreshRoleplayLibrarySelections?.();
  }
  function applyScenarioToSurface(record) {
    if (!record) return;
    if (el('roleplay-scenario-id')) el('roleplay-scenario-id').value = trimValue(record.id);
    if (el('roleplay-scenario')) {
      const premise = [trimValue(record.premise), trimValue(record.opening_beat)].filter(Boolean).join('\n\n');
      el('roleplay-scenario').value = premise || trimValue(record.title);
    }
    if (el('roleplay-scene-notes') && trimValue(record.scene_notes)) el('roleplay-scene-notes').value = trimValue(record.scene_notes);
    const tone = trimValue(record.tone);
    if (tone) {
      const toneSelect = el('roleplay-tone');
      const customInput = el('roleplay-custom-tone');
      if (toneSelect && Array.from(toneSelect.options).some(opt => opt.value === tone)) {
        toneSelect.value = tone;
        if (customInput) customInput.value = '';
      } else if (toneSelect) {
        toneSelect.value = 'Custom';
        if (customInput) customInput.value = tone;
      }
      toneSelect?.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (typeof window.neoSetRoleplaySceneCast === 'function') {
      window.neoSetRoleplaySceneCast(parseJsonArray(record.cast, []), { silent: true });
    }
    window.neoRefreshRoleplayLibrarySelections?.();
  }

  async function refreshLibraryState(options = {}, providedState = null) {
    const data = providedState || await fetchState();
    state.characters = Array.isArray(data.characters) ? data.characters : [];
    state.worlds = Array.isArray(data.worlds) ? data.worlds : [];
    state.regions = Array.isArray(data.regions) ? data.regions : [];
    state.cities = Array.isArray(data.cities) ? data.cities : [];
    state.locations = Array.isArray(data.locations) ? data.locations : [];
    state.organizations = Array.isArray(data.organizations) ? data.organizations : [];
    state.artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
    state.rituals = Array.isArray(data.rituals) ? data.rituals : [];
    state.cycles = Array.isArray(data.cycles) ? data.cycles : [];
    state.creatures = Array.isArray(data.creatures) ? data.creatures : [];
    state.universes = Array.isArray(data.universes) ? data.universes : [];
    state.legends = Array.isArray(data.legends) ? data.legends : [];
    state.packs = Array.isArray(data.packs) ? data.packs : [];
    state.scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
    populateSelect('roleplay-user-character-id', state.characters, 'None', options.userCharacterId);
    populateSelect('roleplay-partner-character-id', state.characters, 'None', options.partnerCharacterId);
    populateSelect('roleplay-library-character-select', state.characters, 'Select a character', options.characterRecordId);
    populateSelect('roleplay-world-id', state.worlds, 'None', options.worldId);
    populateSelect('roleplay-library-world-select', state.worlds, 'Select a world', options.worldRecordId);
    populateSelect('roleplay-library-region-world-id', state.worlds, 'None', el('roleplay-library-region-world-id')?.value);
    populateSelect('roleplay-library-character-origin-world-id', state.worlds, 'None', el('roleplay-library-character-origin-world-id')?.value);
    populateSelect('roleplay-library-character-current-world-id', state.worlds, 'None', el('roleplay-library-character-current-world-id')?.value);
    populateSelect('roleplay-library-region-select', state.regions, 'Select a region', options.regionRecordId);
    populateSelect('roleplay-library-city-select', state.cities, 'Select a city', options.cityRecordId);
    populateSelect('roleplay-library-location-select', state.locations, 'Select a location', options.locationRecordId);
    populateSelect('roleplay-library-organization-select', state.organizations, 'Select an organization', options.organizationRecordId);
    populateSelect('roleplay-library-artifact-select', state.artifacts, 'Select an artifact', options.artifactRecordId);
    populateSelect('roleplay-library-ritual-select', state.rituals, 'Select a ritual', options.ritualRecordId);
    populateSelect('roleplay-library-cycle-select', state.cycles, 'Select a cycle', options.cycleRecordId);
    populateSelect('roleplay-library-creature-select', state.creatures, 'Select a creature', options.creatureRecordId);
    populateSelect('roleplay-library-universe-select', state.universes, 'Select a universe', options.universeRecordId);
    populateSelect('roleplay-library-legend-select', state.legends, 'Select a legend', options.legendRecordId);
    populateSelect('roleplay-library-pack-select', state.packs, 'Select a pack', options.packRecordId);
    populateSelect('roleplay-library-creature-world-id', state.worlds, 'None', el('roleplay-library-creature-world-id')?.value);
    populateSelect('roleplay-library-city-world-id', state.worlds, 'None', el('roleplay-library-city-world-id')?.value);
    populateSelect('roleplay-scenario-id', state.scenarios, 'None', options.scenarioId);
    el('roleplay-library-legend-universe-id') && (el('roleplay-library-legend-universe-id').innerHTML = universeOptionNodes(el('roleplay-library-legend-universe-id')?.value));
    el('roleplay-library-legend-world-id') && (el('roleplay-library-legend-world-id').innerHTML = worldOptionNodes(el('roleplay-library-legend-world-id')?.value));
    el('roleplay-library-location-universe-id') && (el('roleplay-library-location-universe-id').innerHTML = universeOptionNodes(el('roleplay-library-location-universe-id')?.value));
    el('roleplay-library-location-world-id') && (el('roleplay-library-location-world-id').innerHTML = worldOptionNodes(el('roleplay-library-location-world-id')?.value));
    el('roleplay-library-organization-universe-id') && (el('roleplay-library-organization-universe-id').innerHTML = universeOptionNodes(el('roleplay-library-organization-universe-id')?.value));
    el('roleplay-library-organization-world-id') && (el('roleplay-library-organization-world-id').innerHTML = worldOptionNodes(el('roleplay-library-organization-world-id')?.value));
    populateSelect('roleplay-library-scenario-select', state.scenarios, 'Select a scenario', options.scenarioRecordId);
    const originWorld = el('roleplay-library-character-origin-world-id')?.value || '';
    const currentWorld = el('roleplay-library-character-current-world-id')?.value || '';
    el('roleplay-library-character-origin-region-id') && (el('roleplay-library-character-origin-region-id').innerHTML = regionOptionNodes(el('roleplay-library-character-origin-region-id')?.value, originWorld));
    el('roleplay-library-character-current-region-id') && (el('roleplay-library-character-current-region-id').innerHTML = regionOptionNodes(el('roleplay-library-character-current-region-id')?.value, currentWorld));
    el('roleplay-library-character-origin-city-id') && (el('roleplay-library-character-origin-city-id').innerHTML = cityOptionNodes(el('roleplay-library-character-origin-city-id')?.value, originWorld, el('roleplay-library-character-origin-region-id')?.value));
    el('roleplay-library-character-current-city-id') && (el('roleplay-library-character-current-city-id').innerHTML = cityOptionNodes(el('roleplay-library-character-current-city-id')?.value, currentWorld, el('roleplay-library-character-current-region-id')?.value));
    el('roleplay-library-character-origin-location-id') && (el('roleplay-library-character-origin-location-id').innerHTML = locationOptionNodes(el('roleplay-library-character-origin-location-id')?.value, { worldId: originWorld, regionId: el('roleplay-library-character-origin-region-id')?.value, cityId: el('roleplay-library-character-origin-city-id')?.value }));
    el('roleplay-library-character-current-location-id') && (el('roleplay-library-character-current-location-id').innerHTML = locationOptionNodes(el('roleplay-library-character-current-location-id')?.value, { worldId: currentWorld, regionId: el('roleplay-library-character-current-region-id')?.value, cityId: el('roleplay-library-character-current-city-id')?.value }));
    el('roleplay-library-region-parent-id') && (el('roleplay-library-region-parent-id').innerHTML = regionOptionNodes(el('roleplay-library-region-parent-id')?.value, el('roleplay-library-region-world-id')?.value));
    el('roleplay-library-city-region-id') && (el('roleplay-library-city-region-id').innerHTML = regionOptionNodes(el('roleplay-library-city-region-id')?.value, el('roleplay-library-city-world-id')?.value));
    el('roleplay-library-location-region-id') && (el('roleplay-library-location-region-id').innerHTML = regionOptionNodes(el('roleplay-library-location-region-id')?.value, el('roleplay-library-location-world-id')?.value));
    el('roleplay-library-location-city-id') && (el('roleplay-library-location-city-id').innerHTML = cityOptionNodes(el('roleplay-library-location-city-id')?.value, el('roleplay-library-location-world-id')?.value, el('roleplay-library-location-region-id')?.value));
    el('roleplay-library-location-parent-id') && (el('roleplay-library-location-parent-id').innerHTML = locationOptionNodes(el('roleplay-library-location-parent-id')?.value, { universeId: el('roleplay-library-location-universe-id')?.value, worldId: el('roleplay-library-location-world-id')?.value, regionId: el('roleplay-library-location-region-id')?.value, cityId: el('roleplay-library-location-city-id')?.value }));
    el('roleplay-library-organization-region-id') && (el('roleplay-library-organization-region-id').innerHTML = regionOptionNodes(el('roleplay-library-organization-region-id')?.value, el('roleplay-library-organization-world-id')?.value));
    el('roleplay-library-organization-city-id') && (el('roleplay-library-organization-city-id').innerHTML = cityOptionNodes(el('roleplay-library-organization-city-id')?.value, el('roleplay-library-organization-world-id')?.value, el('roleplay-library-organization-region-id')?.value));
    el('roleplay-library-organization-base-location-id') && (el('roleplay-library-organization-base-location-id').innerHTML = locationOptionNodes(el('roleplay-library-organization-base-location-id')?.value, { universeId: el('roleplay-library-organization-universe-id')?.value, worldId: el('roleplay-library-organization-world-id')?.value, regionId: el('roleplay-library-organization-region-id')?.value, cityId: el('roleplay-library-organization-city-id')?.value }));
    if (el('roleplay-library-organization-parent-id')) el('roleplay-library-organization-parent-id').innerHTML = `<option value="">None</option>${organizationOptionNodes(el('roleplay-library-organization-parent-id')?.value, { excludeId: '' })}`;
    el('roleplay-library-scenario-location-region-id') && (el('roleplay-library-scenario-location-region-id').innerHTML = regionOptionNodes(el('roleplay-library-scenario-location-region-id')?.value, el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value));
    el('roleplay-library-scenario-location-city-id') && (el('roleplay-library-scenario-location-city-id').innerHTML = cityOptionNodes(el('roleplay-library-scenario-location-city-id')?.value, el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value, el('roleplay-library-scenario-location-region-id')?.value));
    el('roleplay-library-scenario-location-id') && (el('roleplay-library-scenario-location-id').innerHTML = locationOptionNodes(el('roleplay-library-scenario-location-id')?.value, { worldId: el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value, regionId: el('roleplay-library-scenario-location-region-id')?.value, cityId: el('roleplay-library-scenario-location-city-id')?.value }));
    setMultiSelectValues('roleplay-library-world-inhabitant-species', Array.from(el('roleplay-library-world-inhabitant-species')?.selectedOptions || []).map(opt => trimValue(opt.value)), creatureOptionNodes(Array.from(el('roleplay-library-world-inhabitant-species')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-world-creature-fauna', Array.from(el('roleplay-library-world-creature-fauna')?.selectedOptions || []).map(opt => trimValue(opt.value)), creatureOptionNodes(Array.from(el('roleplay-library-world-creature-fauna')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-world-cycles', Array.from(el('roleplay-library-world-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value)), cycleOptionNodes(Array.from(el('roleplay-library-world-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-world-organizations', Array.from(el('roleplay-library-world-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-world-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), {}));
    setMultiSelectValues('roleplay-library-character-artifacts', Array.from(el('roleplay-library-character-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value)), artifactOptionNodes(Array.from(el('roleplay-library-character-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-character-rituals', Array.from(el('roleplay-library-character-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value)), ritualOptionNodes(Array.from(el('roleplay-library-character-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-character-cycles', Array.from(el('roleplay-library-character-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value)), cycleOptionNodes(Array.from(el('roleplay-library-character-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-character-organizations', Array.from(el('roleplay-library-character-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-character-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: currentWorld, regionId: el('roleplay-library-character-current-region-id')?.value, cityId: el('roleplay-library-character-current-city-id')?.value }));
    setMultiSelectValues('roleplay-library-location-artifacts', Array.from(el('roleplay-library-location-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value)), artifactOptionNodes(Array.from(el('roleplay-library-location-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-location-rituals', Array.from(el('roleplay-library-location-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value)), ritualOptionNodes(Array.from(el('roleplay-library-location-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-location-cycles', Array.from(el('roleplay-library-location-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value)), cycleOptionNodes(Array.from(el('roleplay-library-location-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))));
    setMultiSelectValues('roleplay-library-location-organizations', Array.from(el('roleplay-library-location-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-location-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { universeId: el('roleplay-library-location-universe-id')?.value, worldId: el('roleplay-library-location-world-id')?.value, regionId: el('roleplay-library-location-region-id')?.value, cityId: el('roleplay-library-location-city-id')?.value }));
    renderAiContextControls();
    renderRelationshipRows();
    renderScenarioCastRows();
    return data;
  }

  function characterFormData() {
    syncRelationshipStateFromDom();
    syncAbilityStateFromDom();
    syncWardrobeStateFromDom();
    syncHookStateFromDom();
    return {
      kind: 'character',
      record_id: trimValue(el('roleplay-library-character-select')?.value),
      name: trimValue(el('roleplay-library-character-name')?.value) || trimValue(el('roleplay-library-character-display-name')?.value) || trimValue(el('roleplay-user-name')?.value),
      display_name: trimValue(el('roleplay-library-character-display-name')?.value) || trimValue(el('roleplay-library-character-name')?.value) || trimValue(el('roleplay-user-name')?.value),
      gender: trimValue(el('roleplay-library-character-gender')?.value),
      pronouns: trimValue(el('roleplay-library-character-pronouns')?.value),
      role_tier: trimValue(el('roleplay-library-character-role-tier')?.value) || 'main',
      species: trimValue(el('roleplay-library-character-species')?.value),
      designation: trimValue(el('roleplay-library-character-designation')?.value),
      occupation: trimValue(el('roleplay-library-character-occupation')?.value),
      origin_world_id: trimValue(el('roleplay-library-character-origin-world-id')?.value),
      current_world_id: trimValue(el('roleplay-library-character-current-world-id')?.value),
      origin_region_id: trimValue(el('roleplay-library-character-origin-region-id')?.value),
      current_region_id: trimValue(el('roleplay-library-character-current-region-id')?.value),
      origin_city_id: trimValue(el('roleplay-library-character-origin-city-id')?.value),
      current_city_id: trimValue(el('roleplay-library-character-current-city-id')?.value),
      origin_location_id: trimValue(el('roleplay-library-character-origin-location-id')?.value),
      current_location_id: trimValue(el('roleplay-library-character-current-location-id')?.value),
      current_location_label: trimValue(el('roleplay-library-character-current-location-label')?.value) || trimValue(el('roleplay-library-character-current-location-id')?.selectedOptions?.[0]?.textContent || '') || trimValue(el('roleplay-library-character-current-city-id')?.selectedOptions?.[0]?.textContent || '') || trimValue(el('roleplay-library-character-current-region-id')?.selectedOptions?.[0]?.textContent || ''),
      summary: trimValue(el('roleplay-library-character-summary')?.value),
      appearance: trimValue(el('roleplay-library-character-appearance')?.value),
      personality: trimValue(el('roleplay-library-character-personality')?.value),
      speech_style: trimValue(el('roleplay-library-character-speech-style')?.value),
      relationship_notes: trimValue(el('roleplay-library-character-relationship-notes')?.value),
      affiliations: trimValue(el('roleplay-library-character-affiliations')?.value),
      hobbies: trimValue(el('roleplay-library-character-hobbies')?.value),
      student_details: trimValue(el('roleplay-library-character-student-details')?.value),
      canon_notes: trimValue(el('roleplay-library-character-canon-notes')?.value),
      relationships_json: JSON.stringify(state.characterRelationships),
      abilities_json: JSON.stringify(state.characterAbilities),
      artifact_ids_json: JSON.stringify(Array.from(el('roleplay-library-character-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      ritual_ids_json: JSON.stringify(Array.from(el('roleplay-library-character-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      cycle_ids_json: JSON.stringify(Array.from(el('roleplay-library-character-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-character-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      wardrobes_json: JSON.stringify(state.characterWardrobes),
      story_hooks_json: JSON.stringify(state.characterHooks),
    };
  }
  function worldFormData() {
    return {
      kind: 'world',
      record_id: trimValue(el('roleplay-library-world-select')?.value),
      name: trimValue(el('roleplay-library-world-name')?.value) || trimValue(el('roleplay-story-world')?.value),
      summary: trimValue(el('roleplay-library-world-summary')?.value),
      realm_type: trimValue(el('roleplay-library-world-realm-type')?.value),
      calendar_notes: trimValue(el('roleplay-library-world-calendar-notes')?.value),
      lore: trimValue(el('roleplay-library-world-lore')?.value),
      rules: trimValue(el('roleplay-library-world-rules')?.value),
      geography_notes: trimValue(el('roleplay-library-world-geography-notes')?.value),
      society_notes: trimValue(el('roleplay-library-world-society-notes')?.value),
      faith_notes: trimValue(el('roleplay-library-world-faith-notes')?.value),
      people_notes: trimValue(el('roleplay-library-world-people-notes')?.value),
      inhabitant_species_ids_json: JSON.stringify(Array.from(el('roleplay-library-world-inhabitant-species')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      creature_fauna_ids_json: JSON.stringify(Array.from(el('roleplay-library-world-creature-fauna')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      cycle_ids_json: JSON.stringify(Array.from(el('roleplay-library-world-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-world-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      canon_notes: trimValue(el('roleplay-library-world-canon-notes')?.value),
    };
  }
  function regionFormData() {
    return {
      kind: 'region',
      record_id: trimValue(el('roleplay-library-region-select')?.value),
      name: trimValue(el('roleplay-library-region-name')?.value),
      world_id: trimValue(el('roleplay-library-region-world-id')?.value),
      parent_region_id: trimValue(el('roleplay-library-region-parent-id')?.value),
      region_type: trimValue(el('roleplay-library-region-type')?.value) || 'kingdom',
      summary: trimValue(el('roleplay-library-region-summary')?.value),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-region-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      canon_notes: trimValue(el('roleplay-library-region-canon-notes')?.value),
    };
  }

  function cityFormData() {
    return {
      kind: 'city',
      record_id: trimValue(el('roleplay-library-city-select')?.value),
      name: trimValue(el('roleplay-library-city-name')?.value),
      world_id: trimValue(el('roleplay-library-city-world-id')?.value),
      region_id: trimValue(el('roleplay-library-city-region-id')?.value),
      city_type: trimValue(el('roleplay-library-city-type')?.value) || 'city',
      summary: trimValue(el('roleplay-library-city-summary')?.value),
      access_notes: trimValue(el('roleplay-library-city-access-notes')?.value),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-city-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      canon_notes: trimValue(el('roleplay-library-city-canon-notes')?.value),
    };
  }

  function locationFormData() {
    return {
      kind: 'location',
      record_id: trimValue(el('roleplay-library-location-select')?.value),
      name: trimValue(el('roleplay-library-location-name')?.value) || trimValue(el('roleplay-library-location-display-name')?.value),
      display_name: trimValue(el('roleplay-library-location-display-name')?.value) || trimValue(el('roleplay-library-location-name')?.value),
      function_label: trimValue(el('roleplay-library-location-function-label')?.value),
      location_type: trimValue(el('roleplay-library-location-type')?.value) || 'building',
      anchor_type: trimValue(el('roleplay-library-location-anchor-type')?.value) || 'world',
      universe_id: trimValue(el('roleplay-library-location-universe-id')?.value),
      world_id: trimValue(el('roleplay-library-location-world-id')?.value),
      region_id: trimValue(el('roleplay-library-location-region-id')?.value),
      city_id: trimValue(el('roleplay-library-location-city-id')?.value),
      parent_location_id: trimValue(el('roleplay-library-location-parent-id')?.value),
      summary: trimValue(el('roleplay-library-location-summary')?.value),
      atmosphere: trimValue(el('roleplay-library-location-atmosphere')?.value),
      scene_uses_json: JSON.stringify(Array.from(el('roleplay-library-location-scene-uses')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      artifact_ids_json: JSON.stringify(Array.from(el('roleplay-library-location-artifacts')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      ritual_ids_json: JSON.stringify(Array.from(el('roleplay-library-location-rituals')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      cycle_ids_json: JSON.stringify(Array.from(el('roleplay-library-location-cycles')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-location-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      access_notes: trimValue(el('roleplay-library-location-access-notes')?.value),
      hazards: trimValue(el('roleplay-library-location-hazards')?.value),
      rules: trimValue(el('roleplay-library-location-rules')?.value),
      public_notes: trimValue(el('roleplay-library-location-public-notes')?.value),
      hidden_truth: trimValue(el('roleplay-library-location-hidden-truth')?.value),
      canon_notes: trimValue(el('roleplay-library-location-canon-notes')?.value),
    };
  }

  function fillOrganizationForm(item = {}) {
    populateSelect('roleplay-library-organization-select', state.organizations, 'Select an organization', item.id || '');
    if (el('roleplay-library-organization-name')) el('roleplay-library-organization-name').value = item.name || '';
    if (el('roleplay-library-organization-display-name')) el('roleplay-library-organization-display-name').value = item.display_name || item.name || '';
    if (el('roleplay-library-organization-group-type')) el('roleplay-library-organization-group-type').value = item.group_type || 'organization';
    if (el('roleplay-library-organization-universe-id')) el('roleplay-library-organization-universe-id').innerHTML = universeOptionNodes(item.universe_id || '');
    if (el('roleplay-library-organization-world-id')) el('roleplay-library-organization-world-id').innerHTML = worldOptionNodes(item.world_id || '');
    if (el('roleplay-library-organization-region-id')) el('roleplay-library-organization-region-id').innerHTML = regionOptionNodes(item.region_id || '', item.world_id || '');
    if (el('roleplay-library-organization-city-id')) el('roleplay-library-organization-city-id').innerHTML = cityOptionNodes(item.city_id || '', item.world_id || '', item.region_id || '');
    if (el('roleplay-library-organization-base-location-id')) el('roleplay-library-organization-base-location-id').innerHTML = locationOptionNodes(item.base_location_id || '', { universeId: item.universe_id || '', worldId: item.world_id || '', regionId: item.region_id || '', cityId: item.city_id || '' });
    setMultiSelectValues('roleplay-library-organization-allies', item.ally_organization_ids || [], organizationOptionNodes(item.ally_organization_ids || [], { excludeId: item.id || '' }));
    setMultiSelectValues('roleplay-library-organization-rivals', item.rival_organization_ids || [], organizationOptionNodes(item.rival_organization_ids || [], { excludeId: item.id || '' }));
    if (el('roleplay-library-organization-parent-id')) el('roleplay-library-organization-parent-id').innerHTML = `<option value="">None</option>${organizationOptionNodes(item.parent_organization_id || '', { excludeId: item.id || '' })}`;
    if (el('roleplay-library-organization-summary')) el('roleplay-library-organization-summary').value = item.summary || '';
    if (el('roleplay-library-organization-leadership')) el('roleplay-library-organization-leadership').value = item.leadership || '';
    if (el('roleplay-library-organization-beliefs')) el('roleplay-library-organization-beliefs').value = item.beliefs || '';
    if (el('roleplay-library-organization-goals')) el('roleplay-library-organization-goals').value = item.goals || '';
    if (el('roleplay-library-organization-reputation')) el('roleplay-library-organization-reputation').value = item.reputation || '';
    if (el('roleplay-library-organization-resources')) el('roleplay-library-organization-resources').value = item.resources || '';
    if (el('roleplay-library-organization-membership-rules')) el('roleplay-library-organization-membership-rules').value = item.membership_rules || '';
    if (el('roleplay-library-organization-public-face')) el('roleplay-library-organization-public-face').value = item.public_face || '';
    if (el('roleplay-library-organization-hidden-truth')) el('roleplay-library-organization-hidden-truth').value = item.hidden_truth || '';
    if (el('roleplay-library-organization-canon-notes')) el('roleplay-library-organization-canon-notes').value = item.canon_notes || '';
  }

  function organizationFormData() {
    return {
      kind: 'organization',
      record_id: trimValue(el('roleplay-library-organization-select')?.value),
      name: trimValue(el('roleplay-library-organization-name')?.value),
      display_name: trimValue(el('roleplay-library-organization-display-name')?.value),
      group_type: trimValue(el('roleplay-library-organization-group-type')?.value) || 'organization',
      universe_id: trimValue(el('roleplay-library-organization-universe-id')?.value),
      world_id: trimValue(el('roleplay-library-organization-world-id')?.value),
      region_id: trimValue(el('roleplay-library-organization-region-id')?.value),
      city_id: trimValue(el('roleplay-library-organization-city-id')?.value),
      base_location_id: trimValue(el('roleplay-library-organization-base-location-id')?.value),
      parent_organization_id: trimValue(el('roleplay-library-organization-parent-id')?.value),
      summary: trimValue(el('roleplay-library-organization-summary')?.value),
      leadership: trimValue(el('roleplay-library-organization-leadership')?.value),
      beliefs: trimValue(el('roleplay-library-organization-beliefs')?.value),
      goals: trimValue(el('roleplay-library-organization-goals')?.value),
      reputation: trimValue(el('roleplay-library-organization-reputation')?.value),
      resources: trimValue(el('roleplay-library-organization-resources')?.value),
      membership_rules: trimValue(el('roleplay-library-organization-membership-rules')?.value),
      public_face: trimValue(el('roleplay-library-organization-public-face')?.value),
      hidden_truth: trimValue(el('roleplay-library-organization-hidden-truth')?.value),
      canon_notes: trimValue(el('roleplay-library-organization-canon-notes')?.value),
      ally_organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-organization-allies')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      rival_organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-organization-rivals')?.selectedOptions || []).map(opt => trimValue(opt.value))),
    };
  }

  function artifactFormData() {
    return {
      kind: 'artifact',
      record_id: trimValue(el('roleplay-library-artifact-select')?.value),
      name: trimValue(el('roleplay-library-artifact-name')?.value),
      item_type: trimValue(el('roleplay-library-artifact-type')?.value) || 'weapon',
      rarity: trimValue(el('roleplay-library-artifact-rarity')?.value) || 'normal',
      state_value: trimValue(el('roleplay-library-artifact-state')?.value) || 'active',
      world_id: trimValue(el('roleplay-library-artifact-world-id')?.value),
      region_id: trimValue(el('roleplay-library-artifact-region-id')?.value),
      city_id: trimValue(el('roleplay-library-artifact-city-id')?.value),
      location_id: trimValue(el('roleplay-library-artifact-location-id')?.value),
      current_holder_character_id: trimValue(el('roleplay-library-artifact-holder-id')?.value),
      source_tradition: trimValue(el('roleplay-library-artifact-source')?.value),
      summary: trimValue(el('roleplay-library-artifact-summary')?.value),
      effects: trimValue(el('roleplay-library-artifact-effects')?.value),
      costs: trimValue(el('roleplay-library-artifact-costs')?.value),
      activation: trimValue(el('roleplay-library-artifact-activation')?.value),
      lawful_status: trimValue(el('roleplay-library-artifact-lawful-status')?.value),
      canon_notes: trimValue(el('roleplay-library-artifact-canon-notes')?.value),
    };
  }

  function ritualFormData() {
    return {
      kind: 'ritual',
      record_id: trimValue(el('roleplay-library-ritual-select')?.value),
      name: trimValue(el('roleplay-library-ritual-name')?.value),
      ritual_type: trimValue(el('roleplay-library-ritual-type')?.value) || 'ritual',
      school: trimValue(el('roleplay-library-ritual-school')?.value),
      state_value: trimValue(el('roleplay-library-ritual-state')?.value) || 'known',
      world_id: trimValue(el('roleplay-library-ritual-world-id')?.value),
      region_id: trimValue(el('roleplay-library-ritual-region-id')?.value),
      location_id: trimValue(el('roleplay-library-ritual-location-id')?.value),
      effect_summary: trimValue(el('roleplay-library-ritual-effect-summary')?.value),
      requirements: trimValue(el('roleplay-library-ritual-requirements')?.value),
      risks: trimValue(el('roleplay-library-ritual-risks')?.value),
      lawful_status: trimValue(el('roleplay-library-ritual-lawful-status')?.value),
      canon_notes: trimValue(el('roleplay-library-ritual-canon-notes')?.value),
    };
  }

  function cycleFormData() {
    return {
      kind: 'cycle',
      record_id: trimValue(el('roleplay-library-cycle-select')?.value),
      name: trimValue(el('roleplay-library-cycle-name')?.value),
      cycle_type: trimValue(el('roleplay-library-cycle-type')?.value) || 'celestial',
      scope_type: trimValue(el('roleplay-library-cycle-scope-type')?.value) || 'world',
      universe_id: trimValue(el('roleplay-library-cycle-universe-id')?.value),
      world_id: trimValue(el('roleplay-library-cycle-world-id')?.value),
      region_id: trimValue(el('roleplay-library-cycle-region-id')?.value),
      location_id: trimValue(el('roleplay-library-cycle-location-id')?.value),
      affected_species: trimValue(el('roleplay-library-cycle-affected-species')?.value),
      affected_designation: trimValue(el('roleplay-library-cycle-affected-designation')?.value),
      cadence: trimValue(el('roleplay-library-cycle-cadence')?.value),
      trigger: trimValue(el('roleplay-library-cycle-trigger')?.value),
      stages: trimValue(el('roleplay-library-cycle-stages')?.value),
      effects: trimValue(el('roleplay-library-cycle-effects')?.value),
      safeguards: trimValue(el('roleplay-library-cycle-safeguards')?.value),
      canon_notes: trimValue(el('roleplay-library-cycle-canon-notes')?.value),
    };
  }

  function creatureFormData() {
    return {
      kind: 'creature',
      record_id: trimValue(el('roleplay-library-creature-select')?.value),
      name: trimValue(el('roleplay-library-creature-name')?.value),
      world_id: trimValue(el('roleplay-library-creature-world-id')?.value),
      category: trimValue(el('roleplay-library-creature-category')?.value) || 'creature',
      sentience: trimValue(el('roleplay-library-creature-sentience')?.value) || 'unknown',
      summary: trimValue(el('roleplay-library-creature-summary')?.value),
      canon_notes: trimValue(el('roleplay-library-creature-canon-notes')?.value),
    };
  }

  function universeFormData() {
    return { kind: 'universe', record_id: trimValue(el('roleplay-library-universe-select')?.value), name: trimValue(el('roleplay-library-universe-name')?.value), summary: trimValue(el('roleplay-library-universe-summary')?.value), canon_notes: trimValue(el('roleplay-library-universe-canon-notes')?.value) };
  }

  function legendFormData() {
    return { kind: 'legend', record_id: trimValue(el('roleplay-library-legend-select')?.value), title: trimValue(el('roleplay-library-legend-title')?.value), scope: trimValue(el('roleplay-library-legend-scope')?.value) || 'world', legend_type: trimValue(el('roleplay-library-legend-type')?.value) || 'myth', truth_status: trimValue(el('roleplay-library-legend-truth')?.value) || 'disputed', universe_id: trimValue(el('roleplay-library-legend-universe-id')?.value), world_id: trimValue(el('roleplay-library-legend-world-id')?.value), public_version: trimValue(el('roleplay-library-legend-public-version')?.value), hidden_version: trimValue(el('roleplay-library-legend-hidden-version')?.value), canon_notes: trimValue(el('roleplay-library-legend-canon-notes')?.value) };
  }

  function packFormData() {
    return { kind: 'pack', record_id: trimValue(el('roleplay-library-pack-select')?.value), title: trimValue(el('roleplay-library-pack-title')?.value), pack_type: trimValue(el('roleplay-library-pack-type')?.value) || 'rule', summary: trimValue(el('roleplay-library-pack-summary')?.value), content: trimValue(el('roleplay-library-pack-content')?.value), canon_notes: trimValue(el('roleplay-library-pack-canon-notes')?.value) };
  }

  function scenarioFormData() {
    syncScenarioCastStateFromDom();
    return {
      kind: 'scenario',
      record_id: trimValue(el('roleplay-library-scenario-select')?.value),
      title: trimValue(el('roleplay-library-scenario-title')?.value) || trimValue(el('roleplay-scenario')?.value).split('\n')[0].slice(0, 60),
      tone: trimValue(el('roleplay-library-scenario-tone')?.value),
      location_label: trimValue(el('roleplay-library-scenario-location-label')?.value) || trimValue(el('roleplay-library-scenario-location-id')?.selectedOptions?.[0]?.textContent || '') || trimValue(el('roleplay-library-scenario-location-city-id')?.selectedOptions?.[0]?.textContent || '') || trimValue(el('roleplay-library-scenario-location-region-id')?.selectedOptions?.[0]?.textContent || ''),
      location_region_id: trimValue(el('roleplay-library-scenario-location-region-id')?.value),
      location_city_id: trimValue(el('roleplay-library-scenario-location-city-id')?.value),
      location_id: trimValue(el('roleplay-library-scenario-location-id')?.value),
      objective: trimValue(el('roleplay-library-scenario-objective')?.value),
      premise: trimValue(el('roleplay-library-scenario-premise')?.value),
      opening_beat: trimValue(el('roleplay-library-scenario-opening-beat')?.value),
      scene_notes: trimValue(el('roleplay-library-scenario-scene-notes')?.value),
      organization_ids_json: JSON.stringify(Array.from(el('roleplay-library-scenario-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value))),
      cast_json: JSON.stringify(state.scenarioCast),
    };
  }

  async function saveRecord(payload, statusId, successLabel) {
    const form = new FormData();
    Object.entries(payload).forEach(([key, value]) => form.append(key, String(value || '')));
    const data = await safeFetchJson('/api/roleplay/library/save', { method: 'POST', body: form, cache: 'no-store' });
    const record = data.record || null;
    if (record) stashRecord(payload.kind, record);
    await refreshLibraryState({
      characterRecordId: payload.kind === 'character' ? record?.id : undefined,
      worldRecordId: payload.kind === 'world' ? record?.id : undefined,
      regionRecordId: payload.kind === 'region' ? record?.id : undefined,
      cityRecordId: payload.kind === 'city' ? record?.id : undefined,
      locationRecordId: payload.kind === 'location' ? record?.id : undefined,
      artifactRecordId: payload.kind === 'artifact' ? record?.id : undefined,
      ritualRecordId: payload.kind === 'ritual' ? record?.id : undefined,
      cycleRecordId: payload.kind === 'cycle' ? record?.id : undefined,
      creatureRecordId: payload.kind === 'creature' ? record?.id : undefined,
      universeRecordId: payload.kind === 'universe' ? record?.id : undefined,
      legendRecordId: payload.kind === 'legend' ? record?.id : undefined,
      packRecordId: payload.kind === 'pack' ? record?.id : undefined,
      scenarioRecordId: payload.kind === 'scenario' ? record?.id : undefined,
      userCharacterId: el('roleplay-user-character-id')?.value,
      partnerCharacterId: el('roleplay-partner-character-id')?.value,
      worldId: el('roleplay-world-id')?.value,
      scenarioId: el('roleplay-scenario-id')?.value,
    }, data);
    libraryStatus(statusId, data.message || successLabel, 'ok');
    return record;
  }
  async function deleteRecord(kind, selectId, statusId) {
    const recordId = trimValue(el(selectId)?.value);
    if (!recordId) {
      libraryStatus(statusId, 'Select a saved record first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('kind', kind);
    form.append('record_id', recordId);
    const data = await safeFetchJson('/api/roleplay/library/delete', { method: 'POST', body: form, cache: 'no-store' });
    clearRecord(kind, recordId);
    if (kind === 'character') fillCharacterForm(null);
    if (kind === 'world') fillWorldForm(null);
    if (kind === 'region') fillRegionForm(null);
    if (kind === 'city') fillCityForm(null);
    if (kind === 'location') fillLocationForm(null);
    if (kind === 'artifact') fillArtifactForm(null);
    if (kind === 'ritual') fillRitualForm(null);
    if (kind === 'cycle') fillCycleForm(null);
    if (kind === 'creature') fillCreatureForm(null);
    if (kind === 'universe') fillUniverseForm(null);
    if (kind === 'legend') fillLegendForm(null);
    if (kind === 'pack') fillPackForm(null);
    if (kind === 'scenario') fillScenarioForm(null);
    await refreshLibraryState({
      userCharacterId: el('roleplay-user-character-id')?.value,
      partnerCharacterId: el('roleplay-partner-character-id')?.value,
      worldId: el('roleplay-world-id')?.value,
      scenarioId: el('roleplay-scenario-id')?.value,
    });
    window.neoRefreshRoleplayLibrarySelections?.();
    libraryStatus(statusId, data.message || `Deleted ${kind}.`, 'ok');
  }

  async function uploadCharacterAvatar() {
    let recordId = trimValue(el('roleplay-library-character-select')?.value);
    const fileInput = el('roleplay-library-character-avatar-file');
    const file = fileInput?.files?.[0];
    if (!recordId) {
      const provisional = await saveRecord(characterFormData(), 'roleplay-library-character-status', 'Character saved.');
      fillCharacterForm(provisional);
      recordId = trimValue(provisional?.id);
      if (!recordId) { libraryStatus('roleplay-library-character-status', 'Save the character first, then upload an image.', 'warn'); return; }
    }
    if (!file) { libraryStatus('roleplay-library-character-status', 'Choose an image file first.', 'warn'); return; }
    const form = new FormData();
    form.append('asset_kind', 'character_avatar');
    form.append('record_id', recordId);
    form.append('file', file);
    const data = await safeFetchJson('/api/roleplay/asset/upload', { method: 'POST', body: form, cache: 'no-store' });
    const record = data.record || null;
    if (record) {
      stashRecord('character', record);
      fillCharacterForm(record);
      await refreshLibraryState({ characterRecordId: record.id, userCharacterId: el('roleplay-user-character-id')?.value, partnerCharacterId: el('roleplay-partner-character-id')?.value, worldId: el('roleplay-world-id')?.value, scenarioId: el('roleplay-scenario-id')?.value });
    }
    if (fileInput) fileInput.value = '';
    libraryStatus('roleplay-library-character-status', data.message || 'Character image uploaded.', 'ok');
  }

  function bindRepeaters() {
    el('btn-roleplay-character-relationship-add')?.addEventListener('click', () => { syncRelationshipStateFromDom(); state.characterRelationships.push({ target_id: '', target_name: '', relationship_type: 'friend', notes: '' }); renderRelationshipRows(); });
    el('btn-roleplay-character-ability-add')?.addEventListener('click', () => { syncAbilityStateFromDom(); state.characterAbilities.push({ name: '', state: 'active', notes: '' }); renderAbilityRows(); });
    el('btn-roleplay-character-wardrobe-add')?.addEventListener('click', () => { syncWardrobeStateFromDom(); state.characterWardrobes.push({ label: '', notes: '' }); renderWardrobeRows(); });
    el('btn-roleplay-character-hook-add')?.addEventListener('click', () => { syncHookStateFromDom(); state.characterHooks.push({ type: 'dream', title: '', notes: '' }); renderHookRows(); });
    el('btn-roleplay-scenario-cast-add')?.addEventListener('click', () => { syncScenarioCastStateFromDom(); state.scenarioCast.push({ character_id: '', character_name: '', scene_role: 'supporting', presence: 'on_scene' }); renderScenarioCastRows(); });

    document.addEventListener('click', (event) => {
      const btn = event.target.closest('button');
      if (!btn) return;
      const idx = Number(btn.dataset.index || -1);
      if (btn.hasAttribute('data-rel-remove')) { syncRelationshipStateFromDom(); state.characterRelationships.splice(idx, 1); renderRelationshipRows(); }
      if (btn.hasAttribute('data-ability-remove')) { syncAbilityStateFromDom(); state.characterAbilities.splice(idx, 1); renderAbilityRows(); }
      if (btn.hasAttribute('data-wardrobe-remove')) { syncWardrobeStateFromDom(); state.characterWardrobes.splice(idx, 1); renderWardrobeRows(); }
      if (btn.hasAttribute('data-hook-remove')) { syncHookStateFromDom(); state.characterHooks.splice(idx, 1); renderHookRows(); }
      if (btn.hasAttribute('data-scn-cast-remove')) { syncScenarioCastStateFromDom(); state.scenarioCast.splice(idx, 1); renderScenarioCastRows(); }
    });
  }

  function bindCharacterActions() {
    el('btn-roleplay-character-load')?.addEventListener('click', async () => {
      try {
        const record = await fetchRecord('character', el('roleplay-library-character-select')?.value);
        if (!record) { libraryStatus('roleplay-library-character-status', 'Select a saved character first.', 'warn'); return; }
        fillCharacterForm(record);
        libraryStatus('roleplay-library-character-status', `Loaded character: ${record.display_name || record.name || 'Character'}`, 'ok');
      } catch (err) { libraryStatus('roleplay-library-character-status', err.message || 'Could not load character.', 'warn'); }
    });
    el('btn-roleplay-character-save')?.addEventListener('click', async () => {
      try { const record = await saveRecord(characterFormData(), 'roleplay-library-character-status', 'Character saved.'); fillCharacterForm(record); }
      catch (err) { libraryStatus('roleplay-library-character-status', err.message || 'Could not save character.', 'warn'); }
    });
    el('btn-roleplay-character-delete')?.addEventListener('click', () => deleteRecord('character', 'roleplay-library-character-select', 'roleplay-library-character-status').catch(err => libraryStatus('roleplay-library-character-status', err.message || 'Could not delete character.', 'warn')));
    el('btn-roleplay-character-avatar-upload')?.addEventListener('click', () => uploadCharacterAvatar().catch(err => libraryStatus('roleplay-library-character-status', err.message || 'Could not upload image.', 'warn')));
    el('roleplay-user-character-id')?.addEventListener('change', async event => { try { const record = await fetchRecord('character', event.target.value); if (record) applyCharacterToSurface(record, 'user'); } catch (_err) {} });
    el('roleplay-partner-character-id')?.addEventListener('change', async event => { try { const record = await fetchRecord('character', event.target.value); if (record) applyCharacterToSurface(record, 'partner'); } catch (_err) {} });
  }
  function bindWorldActions() {
    el('btn-roleplay-world-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('world', el('roleplay-library-world-select')?.value); if (!record) { libraryStatus('roleplay-library-world-status', 'Select a saved world first.', 'warn'); return; } fillWorldForm(record); libraryStatus('roleplay-library-world-status', `Loaded world: ${record.name || 'World'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-world-status', err.message || 'Could not load world.', 'warn'); }
    });
    el('btn-roleplay-world-save')?.addEventListener('click', async () => { try { const record = await saveRecord(worldFormData(), 'roleplay-library-world-status', 'World saved.'); fillWorldForm(record); } catch (err) { libraryStatus('roleplay-library-world-status', err.message || 'Could not save world.', 'warn'); } });
    el('btn-roleplay-world-delete')?.addEventListener('click', () => deleteRecord('world', 'roleplay-library-world-select', 'roleplay-library-world-status').catch(err => libraryStatus('roleplay-library-world-status', err.message || 'Could not delete world.', 'warn')));
    el('roleplay-world-id')?.addEventListener('change', async event => { try { const record = await fetchRecord('world', event.target.value); if (record) applyWorldToSurface(record); } catch (_err) {} });
  }
  function bindRegionActions() {
    el('btn-roleplay-region-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('region', el('roleplay-library-region-select')?.value); if (!record) { libraryStatus('roleplay-library-region-status', 'Select a saved region first.', 'warn'); return; } fillRegionForm(record); libraryStatus('roleplay-library-region-status', `Loaded region: ${record.name || 'Region'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-region-status', err.message || 'Could not load region.', 'warn'); }
    });
    el('btn-roleplay-region-save')?.addEventListener('click', async () => { try { const record = await saveRecord(regionFormData(), 'roleplay-library-region-status', 'Region saved.'); fillRegionForm(record); } catch (err) { libraryStatus('roleplay-library-region-status', err.message || 'Could not save region.', 'warn'); } });
    el('btn-roleplay-region-delete')?.addEventListener('click', () => deleteRecord('region', 'roleplay-library-region-select', 'roleplay-library-region-status').catch(err => libraryStatus('roleplay-library-region-status', err.message || 'Could not delete region.', 'warn')));
    el('roleplay-library-region-world-id')?.addEventListener('change', () => { if (el('roleplay-library-region-parent-id')) el('roleplay-library-region-parent-id').innerHTML = regionOptionNodes('', el('roleplay-library-region-world-id')?.value); setMultiSelectValues('roleplay-library-region-organizations', Array.from(el('roleplay-library-region-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-region-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: el('roleplay-library-region-world-id')?.value })); });
    el('roleplay-library-character-origin-world-id')?.addEventListener('change', () => { if (el('roleplay-library-character-origin-region-id')) el('roleplay-library-character-origin-region-id').innerHTML = regionOptionNodes('', el('roleplay-library-character-origin-world-id')?.value); });
    el('roleplay-library-character-current-world-id')?.addEventListener('change', () => { if (el('roleplay-library-character-current-region-id')) el('roleplay-library-character-current-region-id').innerHTML = regionOptionNodes('', el('roleplay-library-character-current-world-id')?.value); });
  }


  function bindCityActions() {
    el('btn-roleplay-city-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('city', el('roleplay-library-city-select')?.value); if (!record) { libraryStatus('roleplay-library-city-status', 'Select a saved city first.', 'warn'); return; } fillCityForm(record); libraryStatus('roleplay-library-city-status', `Loaded city: ${record.name || 'City'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-city-status', err.message || 'Could not load city.', 'warn'); }
    });
    el('btn-roleplay-city-save')?.addEventListener('click', async () => { try { const record = await saveRecord(cityFormData(), 'roleplay-library-city-status', 'City saved.'); fillCityForm(record); } catch (err) { libraryStatus('roleplay-library-city-status', err.message || 'Could not save city.', 'warn'); } });
    el('btn-roleplay-city-delete')?.addEventListener('click', () => deleteRecord('city', 'roleplay-library-city-select', 'roleplay-library-city-status').catch(err => libraryStatus('roleplay-library-city-status', err.message || 'Could not delete city.', 'warn')));
    el('roleplay-library-city-world-id')?.addEventListener('change', () => { if (el('roleplay-library-city-region-id')) el('roleplay-library-city-region-id').innerHTML = regionOptionNodes('', el('roleplay-library-city-world-id')?.value); setMultiSelectValues('roleplay-library-city-organizations', Array.from(el('roleplay-library-city-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), organizationOptionNodes(Array.from(el('roleplay-library-city-organizations')?.selectedOptions || []).map(opt => trimValue(opt.value)), { worldId: el('roleplay-library-city-world-id')?.value, regionId: el('roleplay-library-city-region-id')?.value })); });
  }

  function bindLocationActions() {
    el('btn-roleplay-location-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('location', el('roleplay-library-location-select')?.value); if (!record) { libraryStatus('roleplay-library-location-status', 'Select a saved location first.', 'warn'); return; } fillLocationForm(record); libraryStatus('roleplay-library-location-status', `Loaded location: ${record.display_name || record.name || 'Location'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-location-status', err.message || 'Could not load location.', 'warn'); }
    });
    el('btn-roleplay-location-save')?.addEventListener('click', async () => { try { const record = await saveRecord(locationFormData(), 'roleplay-library-location-status', 'Location saved.'); fillLocationForm(record); } catch (err) { libraryStatus('roleplay-library-location-status', err.message || 'Could not save location.', 'warn'); } });
    el('btn-roleplay-location-delete')?.addEventListener('click', () => deleteRecord('location', 'roleplay-library-location-select', 'roleplay-library-location-status').catch(err => libraryStatus('roleplay-library-location-status', err.message || 'Could not delete location.', 'warn')));
    el('roleplay-library-location-world-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-location-world-id')?.value || '';
      if (el('roleplay-library-location-region-id')) el('roleplay-library-location-region-id').innerHTML = regionOptionNodes('', worldId);
      if (el('roleplay-library-location-city-id')) el('roleplay-library-location-city-id').innerHTML = cityOptionNodes('', worldId, '');
      if (el('roleplay-library-location-parent-id')) el('roleplay-library-location-parent-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-location-universe-id')?.value, worldId });
    });
    el('roleplay-library-location-region-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-location-world-id')?.value || '';
      const regionId = el('roleplay-library-location-region-id')?.value || '';
      if (el('roleplay-library-location-city-id')) el('roleplay-library-location-city-id').innerHTML = cityOptionNodes('', worldId, regionId);
      if (el('roleplay-library-location-parent-id')) el('roleplay-library-location-parent-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-location-universe-id')?.value, worldId, regionId });
    });
    el('roleplay-library-location-city-id')?.addEventListener('change', () => {
      if (el('roleplay-library-location-parent-id')) el('roleplay-library-location-parent-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-location-universe-id')?.value, worldId: el('roleplay-library-location-world-id')?.value, regionId: el('roleplay-library-location-region-id')?.value, cityId: el('roleplay-library-location-city-id')?.value });
    });
  }

  function bindLocationChains() {
    el('roleplay-library-character-origin-world-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-character-origin-world-id')?.value || '';
      if (el('roleplay-library-character-origin-region-id')) el('roleplay-library-character-origin-region-id').innerHTML = regionOptionNodes('', worldId);
      if (el('roleplay-library-character-origin-city-id')) el('roleplay-library-character-origin-city-id').innerHTML = cityOptionNodes('', worldId, '');
      if (el('roleplay-library-character-origin-location-id')) el('roleplay-library-character-origin-location-id').innerHTML = locationOptionNodes('', { worldId });
    });
    el('roleplay-library-character-origin-region-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-character-origin-world-id')?.value || '';
      const regionId = el('roleplay-library-character-origin-region-id')?.value || '';
      if (el('roleplay-library-character-origin-city-id')) el('roleplay-library-character-origin-city-id').innerHTML = cityOptionNodes('', worldId, regionId);
      if (el('roleplay-library-character-origin-location-id')) el('roleplay-library-character-origin-location-id').innerHTML = locationOptionNodes('', { worldId, regionId });
    });
    el('roleplay-library-character-origin-city-id')?.addEventListener('change', () => {
      if (el('roleplay-library-character-origin-location-id')) el('roleplay-library-character-origin-location-id').innerHTML = locationOptionNodes('', { worldId: el('roleplay-library-character-origin-world-id')?.value, regionId: el('roleplay-library-character-origin-region-id')?.value, cityId: el('roleplay-library-character-origin-city-id')?.value });
    });
    el('roleplay-library-character-current-world-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-character-current-world-id')?.value || '';
      if (el('roleplay-library-character-current-region-id')) el('roleplay-library-character-current-region-id').innerHTML = regionOptionNodes('', worldId);
      if (el('roleplay-library-character-current-city-id')) el('roleplay-library-character-current-city-id').innerHTML = cityOptionNodes('', worldId, '');
      if (el('roleplay-library-character-current-location-id')) el('roleplay-library-character-current-location-id').innerHTML = locationOptionNodes('', { worldId });
    });
    el('roleplay-library-character-current-region-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-library-character-current-world-id')?.value || '';
      const regionId = el('roleplay-library-character-current-region-id')?.value || '';
      if (el('roleplay-library-character-current-city-id')) el('roleplay-library-character-current-city-id').innerHTML = cityOptionNodes('', worldId, regionId);
      if (el('roleplay-library-character-current-location-id')) el('roleplay-library-character-current-location-id').innerHTML = locationOptionNodes('', { worldId, regionId });
    });
    el('roleplay-library-character-current-city-id')?.addEventListener('change', () => {
      if (el('roleplay-library-character-current-location-id')) el('roleplay-library-character-current-location-id').innerHTML = locationOptionNodes('', { worldId: el('roleplay-library-character-current-world-id')?.value, regionId: el('roleplay-library-character-current-region-id')?.value, cityId: el('roleplay-library-character-current-city-id')?.value });
    });
    el('roleplay-library-scenario-location-region-id')?.addEventListener('change', () => {
      const worldId = el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value || '';
      const regionId = el('roleplay-library-scenario-location-region-id')?.value || '';
      if (el('roleplay-library-scenario-location-city-id')) el('roleplay-library-scenario-location-city-id').innerHTML = cityOptionNodes('', worldId, regionId);
      if (el('roleplay-library-scenario-location-id')) el('roleplay-library-scenario-location-id').innerHTML = locationOptionNodes('', { worldId, regionId });
    });
    el('roleplay-library-scenario-location-city-id')?.addEventListener('change', () => {
      if (el('roleplay-library-scenario-location-id')) el('roleplay-library-scenario-location-id').innerHTML = locationOptionNodes('', { worldId: el('roleplay-world-id')?.value || el('roleplay-library-character-current-world-id')?.value, regionId: el('roleplay-library-scenario-location-region-id')?.value, cityId: el('roleplay-library-scenario-location-city-id')?.value });
    });
  }

  function bindOrganizationActions() {
    el('btn-roleplay-organization-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('organization', el('roleplay-library-organization-select')?.value); if (!record) { libraryStatus('roleplay-library-organization-status', 'Select a saved organization first.', 'warn'); return; } fillOrganizationForm(record); libraryStatus('roleplay-library-organization-status', `Loaded organization: ${record.display_name || record.name || 'Organization'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-organization-status', err.message || 'Could not load organization.', 'warn'); }
    });
    el('btn-roleplay-organization-save')?.addEventListener('click', async () => { try { const record = await saveRecord(organizationFormData(), 'roleplay-library-organization-status', 'Organization saved.'); fillOrganizationForm(record); } catch (err) { libraryStatus('roleplay-library-organization-status', err.message || 'Could not save organization.', 'warn'); } });
    el('btn-roleplay-organization-delete')?.addEventListener('click', () => deleteRecord('organization', 'roleplay-library-organization-select', 'roleplay-library-organization-status').catch(err => libraryStatus('roleplay-library-organization-status', err.message || 'Could not delete organization.', 'warn')));
    el('roleplay-library-organization-world-id')?.addEventListener('change', () => { if (el('roleplay-library-organization-region-id')) el('roleplay-library-organization-region-id').innerHTML = regionOptionNodes('', el('roleplay-library-organization-world-id')?.value); if (el('roleplay-library-organization-city-id')) el('roleplay-library-organization-city-id').innerHTML = cityOptionNodes('', el('roleplay-library-organization-world-id')?.value, ''); });
    el('roleplay-library-organization-region-id')?.addEventListener('change', () => { if (el('roleplay-library-organization-city-id')) el('roleplay-library-organization-city-id').innerHTML = cityOptionNodes('', el('roleplay-library-organization-world-id')?.value, el('roleplay-library-organization-region-id')?.value); if (el('roleplay-library-organization-base-location-id')) el('roleplay-library-organization-base-location-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-organization-universe-id')?.value, worldId: el('roleplay-library-organization-world-id')?.value, regionId: el('roleplay-library-organization-region-id')?.value, cityId: el('roleplay-library-organization-city-id')?.value }); });
    el('roleplay-library-organization-city-id')?.addEventListener('change', () => { if (el('roleplay-library-organization-base-location-id')) el('roleplay-library-organization-base-location-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-organization-universe-id')?.value, worldId: el('roleplay-library-organization-world-id')?.value, regionId: el('roleplay-library-organization-region-id')?.value, cityId: el('roleplay-library-organization-city-id')?.value }); });
  }

  function bindArtifactActions() {
    el('btn-roleplay-artifact-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('artifact', el('roleplay-library-artifact-select')?.value); if (!record) { libraryStatus('roleplay-library-artifact-status', 'Select a saved artifact first.', 'warn'); return; } fillArtifactForm(record); libraryStatus('roleplay-library-artifact-status', `Loaded artifact: ${record.name || 'Artifact'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-artifact-status', err.message || 'Could not load artifact.', 'warn'); } });
    el('btn-roleplay-artifact-save')?.addEventListener('click', async () => { try { const record = await saveRecord(artifactFormData(), 'roleplay-library-artifact-status', 'Artifact saved.'); fillArtifactForm(record); } catch (err) { libraryStatus('roleplay-library-artifact-status', err.message || 'Could not save artifact.', 'warn'); } });
    el('btn-roleplay-artifact-delete')?.addEventListener('click', () => deleteRecord('artifact', 'roleplay-library-artifact-select', 'roleplay-library-artifact-status').catch(err => libraryStatus('roleplay-library-artifact-status', err.message || 'Could not delete artifact.', 'warn')));
    el('roleplay-library-artifact-world-id')?.addEventListener('change', () => { const worldId = el('roleplay-library-artifact-world-id')?.value || ''; if (el('roleplay-library-artifact-region-id')) el('roleplay-library-artifact-region-id').innerHTML = regionOptionNodes('', worldId); if (el('roleplay-library-artifact-city-id')) el('roleplay-library-artifact-city-id').innerHTML = cityOptionNodes('', worldId, ''); if (el('roleplay-library-artifact-location-id')) el('roleplay-library-artifact-location-id').innerHTML = locationOptionNodes('', { worldId }); });
    el('roleplay-library-artifact-region-id')?.addEventListener('change', () => { const worldId = el('roleplay-library-artifact-world-id')?.value || ''; const regionId = el('roleplay-library-artifact-region-id')?.value || ''; if (el('roleplay-library-artifact-city-id')) el('roleplay-library-artifact-city-id').innerHTML = cityOptionNodes('', worldId, regionId); if (el('roleplay-library-artifact-location-id')) el('roleplay-library-artifact-location-id').innerHTML = locationOptionNodes('', { worldId, regionId }); });
    el('roleplay-library-artifact-city-id')?.addEventListener('change', () => { if (el('roleplay-library-artifact-location-id')) el('roleplay-library-artifact-location-id').innerHTML = locationOptionNodes('', { worldId: el('roleplay-library-artifact-world-id')?.value, regionId: el('roleplay-library-artifact-region-id')?.value, cityId: el('roleplay-library-artifact-city-id')?.value }); });
  }

  function bindRitualActions() {
    el('btn-roleplay-ritual-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('ritual', el('roleplay-library-ritual-select')?.value); if (!record) { libraryStatus('roleplay-library-ritual-status', 'Select a saved ritual first.', 'warn'); return; } fillRitualForm(record); libraryStatus('roleplay-library-ritual-status', `Loaded ritual: ${record.name || 'Ritual'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-ritual-status', err.message || 'Could not load ritual.', 'warn'); } });
    el('btn-roleplay-ritual-save')?.addEventListener('click', async () => { try { const record = await saveRecord(ritualFormData(), 'roleplay-library-ritual-status', 'Ritual saved.'); fillRitualForm(record); } catch (err) { libraryStatus('roleplay-library-ritual-status', err.message || 'Could not save ritual.', 'warn'); } });
    el('btn-roleplay-ritual-delete')?.addEventListener('click', () => deleteRecord('ritual', 'roleplay-library-ritual-select', 'roleplay-library-ritual-status').catch(err => libraryStatus('roleplay-library-ritual-status', err.message || 'Could not delete ritual.', 'warn')));
    el('roleplay-library-ritual-world-id')?.addEventListener('change', () => { const worldId = el('roleplay-library-ritual-world-id')?.value || ''; if (el('roleplay-library-ritual-region-id')) el('roleplay-library-ritual-region-id').innerHTML = regionOptionNodes('', worldId); if (el('roleplay-library-ritual-location-id')) el('roleplay-library-ritual-location-id').innerHTML = locationOptionNodes('', { worldId }); });
    el('roleplay-library-ritual-region-id')?.addEventListener('change', () => { if (el('roleplay-library-ritual-location-id')) el('roleplay-library-ritual-location-id').innerHTML = locationOptionNodes('', { worldId: el('roleplay-library-ritual-world-id')?.value, regionId: el('roleplay-library-ritual-region-id')?.value }); });
  }

  function bindCycleActions() {
    el('btn-roleplay-cycle-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('cycle', el('roleplay-library-cycle-select')?.value); if (!record) { libraryStatus('roleplay-library-cycle-status', 'Select a saved cycle first.', 'warn'); return; } fillCycleForm(record); libraryStatus('roleplay-library-cycle-status', `Loaded cycle: ${record.name || 'Cycle'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-cycle-status', err.message || 'Could not load cycle.', 'warn'); } });
    el('btn-roleplay-cycle-save')?.addEventListener('click', async () => { try { const record = await saveRecord(cycleFormData(), 'roleplay-library-cycle-status', 'Cycle saved.'); fillCycleForm(record); } catch (err) { libraryStatus('roleplay-library-cycle-status', err.message || 'Could not save cycle.', 'warn'); } });
    el('btn-roleplay-cycle-delete')?.addEventListener('click', () => deleteRecord('cycle', 'roleplay-library-cycle-select', 'roleplay-library-cycle-status').catch(err => libraryStatus('roleplay-library-cycle-status', err.message || 'Could not delete cycle.', 'warn')));
    el('roleplay-library-cycle-world-id')?.addEventListener('change', () => { const worldId = el('roleplay-library-cycle-world-id')?.value || ''; if (el('roleplay-library-cycle-region-id')) el('roleplay-library-cycle-region-id').innerHTML = regionOptionNodes('', worldId); if (el('roleplay-library-cycle-location-id')) el('roleplay-library-cycle-location-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-cycle-universe-id')?.value, worldId }); });
    el('roleplay-library-cycle-region-id')?.addEventListener('change', () => { if (el('roleplay-library-cycle-location-id')) el('roleplay-library-cycle-location-id').innerHTML = locationOptionNodes('', { universeId: el('roleplay-library-cycle-universe-id')?.value, worldId: el('roleplay-library-cycle-world-id')?.value, regionId: el('roleplay-library-cycle-region-id')?.value }); });
  }

  function bindCreatureActions() {
    el('btn-roleplay-creature-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('creature', el('roleplay-library-creature-select')?.value); if (!record) { libraryStatus('roleplay-library-creature-status', 'Select a saved creature first.', 'warn'); return; } fillCreatureForm(record); libraryStatus('roleplay-library-creature-status', `Loaded creature: ${record.name || 'Creature'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-creature-status', err.message || 'Could not load creature.', 'warn'); }
    });
    el('btn-roleplay-creature-save')?.addEventListener('click', async () => { try { const record = await saveRecord(creatureFormData(), 'roleplay-library-creature-status', 'Creature saved.'); fillCreatureForm(record); } catch (err) { libraryStatus('roleplay-library-creature-status', err.message || 'Could not save creature.', 'warn'); } });
    el('btn-roleplay-creature-delete')?.addEventListener('click', () => deleteRecord('creature', 'roleplay-library-creature-select', 'roleplay-library-creature-status').catch(err => libraryStatus('roleplay-library-creature-status', err.message || 'Could not delete creature.', 'warn')));
  }

  function bindUniverseActions() {
    el('btn-roleplay-universe-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('universe', el('roleplay-library-universe-select')?.value); if (!record) { libraryStatus('roleplay-library-universe-status', 'Select a saved universe first.', 'warn'); return; } fillUniverseForm(record); libraryStatus('roleplay-library-universe-status', `Loaded universe: ${record.name || 'Universe'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-universe-status', err.message || 'Could not load universe.', 'warn'); } });
    el('btn-roleplay-universe-save')?.addEventListener('click', async () => { try { const record = await saveRecord(universeFormData(), 'roleplay-library-universe-status', 'Universe saved.'); fillUniverseForm(record); } catch (err) { libraryStatus('roleplay-library-universe-status', err.message || 'Could not save universe.', 'warn'); } });
    el('btn-roleplay-universe-delete')?.addEventListener('click', () => deleteRecord('universe', 'roleplay-library-universe-select', 'roleplay-library-universe-status').catch(err => libraryStatus('roleplay-library-universe-status', err.message || 'Could not delete universe.', 'warn')));
  }

  function bindLegendActions() {
    el('btn-roleplay-legend-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('legend', el('roleplay-library-legend-select')?.value); if (!record) { libraryStatus('roleplay-library-legend-status', 'Select a saved legend first.', 'warn'); return; } fillLegendForm(record); libraryStatus('roleplay-library-legend-status', `Loaded legend: ${record.title || 'Legend'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-legend-status', err.message || 'Could not load legend.', 'warn'); } });
    el('btn-roleplay-legend-save')?.addEventListener('click', async () => { try { const record = await saveRecord(legendFormData(), 'roleplay-library-legend-status', 'Legend saved.'); fillLegendForm(record); } catch (err) { libraryStatus('roleplay-library-legend-status', err.message || 'Could not save legend.', 'warn'); } });
    el('btn-roleplay-legend-delete')?.addEventListener('click', () => deleteRecord('legend', 'roleplay-library-legend-select', 'roleplay-library-legend-status').catch(err => libraryStatus('roleplay-library-legend-status', err.message || 'Could not delete legend.', 'warn')));
  }

  function bindPackActions() {
    el('btn-roleplay-pack-load')?.addEventListener('click', async () => { try { const record = await fetchRecord('pack', el('roleplay-library-pack-select')?.value); if (!record) { libraryStatus('roleplay-library-pack-status', 'Select a saved pack first.', 'warn'); return; } fillPackForm(record); libraryStatus('roleplay-library-pack-status', `Loaded pack: ${record.title || 'Pack'}`, 'ok'); } catch (err) { libraryStatus('roleplay-library-pack-status', err.message || 'Could not load pack.', 'warn'); } });
    el('btn-roleplay-pack-save')?.addEventListener('click', async () => { try { const record = await saveRecord(packFormData(), 'roleplay-library-pack-status', 'Pack saved.'); fillPackForm(record); } catch (err) { libraryStatus('roleplay-library-pack-status', err.message || 'Could not save pack.', 'warn'); } });
    el('btn-roleplay-pack-delete')?.addEventListener('click', () => deleteRecord('pack', 'roleplay-library-pack-select', 'roleplay-library-pack-status').catch(err => libraryStatus('roleplay-library-pack-status', err.message || 'Could not delete pack.', 'warn')));
  }

  function bindScenarioActions() {
    el('btn-roleplay-scenario-load')?.addEventListener('click', async () => {
      try { const record = await fetchRecord('scenario', el('roleplay-library-scenario-select')?.value); if (!record) { libraryStatus('roleplay-library-scenario-status', 'Select a saved scenario first.', 'warn'); return; } fillScenarioForm(record); libraryStatus('roleplay-library-scenario-status', `Loaded scenario: ${record.title || 'Scenario'}`, 'ok'); }
      catch (err) { libraryStatus('roleplay-library-scenario-status', err.message || 'Could not load scenario.', 'warn'); }
    });
    el('btn-roleplay-scenario-save')?.addEventListener('click', async () => { try { const record = await saveRecord(scenarioFormData(), 'roleplay-library-scenario-status', 'Scenario saved.'); fillScenarioForm(record); } catch (err) { libraryStatus('roleplay-library-scenario-status', err.message || 'Could not save scenario.', 'warn'); } });
    el('btn-roleplay-scenario-delete')?.addEventListener('click', () => deleteRecord('scenario', 'roleplay-library-scenario-select', 'roleplay-library-scenario-status').catch(err => libraryStatus('roleplay-library-scenario-status', err.message || 'Could not delete scenario.', 'warn')));
    el('roleplay-scenario-id')?.addEventListener('change', async event => { try { const record = await fetchRecord('scenario', event.target.value); if (record) applyScenarioToSurface(record); } catch (_err) {} });
  }

  function bindImportActions() {
    renderImportPreview(null);
    ['roleplay-library-import-kind', 'roleplay-library-ai-universe-id', 'roleplay-library-ai-world-id', 'roleplay-library-ai-region-id', 'roleplay-library-ai-city-id', 'roleplay-library-ai-location-id', 'roleplay-library-ai-scenario-id'].forEach(id => {
      el(id)?.addEventListener('change', () => renderAiContextControls());
    });
    el('roleplay-library-ai-species-hint')?.addEventListener('blur', () => renderAiContextControls());
    el('btn-roleplay-library-import-preview')?.addEventListener('click', async () => {
      const fileInput = el('roleplay-library-import-file');
      const file = fileInput?.files?.[0];
      if (!file) { importStatus('Choose a JSON, Markdown, or TXT file first.', 'warn'); return; }
      const form = new FormData();
      form.append('target_kind', trimValue(el('roleplay-library-import-kind')?.value));
      form.append('file', file);
      importStatus('Building import preview...', '');
      setBusy('btn-roleplay-library-import-preview', true, 'Previewing...');
      try {
        const data = await safeFetchJson('/api/roleplay/library/import-preview', { method: 'POST', body: form, cache: 'no-store' });
        renderImportPreview(data);
        importStatus(data.message || 'Import preview ready.', 'ok');
      } catch (err) {
        renderImportPreview(null);
        importStatus(err.message || 'Could not preview import.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-import-preview', false);
      }
    });
    el('btn-roleplay-library-ai-draft')?.addEventListener('click', async () => {
      if (!requireBackendRole('text', 'roleplay-library-import-status', 'Connect a Text Backend first. AI JSON drafting uses the active text model.')) return;
      const kind = trimValue(el('roleplay-library-import-kind')?.value);
      const brief = trimValue(el('roleplay-library-ai-brief')?.value);
      const draftMode = trimValue(el('roleplay-library-ai-mode')?.value) || 'draft_scratch';
      const draftStyle = trimValue(el('roleplay-library-ai-style')?.value) || 'balanced';
      const currentJson = jsonEditorValue();
      const aiContext = buildAiDraftContext(kind);
      if (!kind) { importStatus('Choose a target library kind first.', 'warn'); return; }
      if (!brief && draftMode === 'draft_scratch') { importStatus('Write a short brief before drafting JSON with AI.', 'warn'); return; }
      const form = new FormData();
      form.append('target_kind', kind);
      form.append('brief', brief);
      form.append('draft_mode', draftMode);
      form.append('draft_style', draftStyle);
      form.append('model', typeof currentModel === 'function' ? currentModel() : 'default');
      form.append('current_json', currentJson);
      form.append('universe_id', aiContext.universeId || '');
      form.append('world_id', aiContext.worldId || '');
      form.append('region_id', aiContext.regionId || '');
      form.append('city_id', aiContext.cityId || '');
      form.append('location_id', aiContext.locationId || '');
      form.append('scenario_id', aiContext.scenarioId || '');
      form.append('species_hint', aiContext.speciesHint || '');
      form.append('organization_ids_json', JSON.stringify(aiContext.organizationIds || []));
      importStatus('Drafting schema JSON with AI...', '');
      setBusy('btn-roleplay-library-ai-draft', true, 'Drafting...');
      try {
        const data = await safeFetchJson('/api/roleplay/library/ai-draft-preview', { method: 'POST', body: form, cache: 'no-store' });
        setJsonEditorValue(data.draft_json || '');
        renderImportPreview(data);
        importStatus(data.message || 'AI draft ready. Review the JSON editor and preview before committing.', 'ok');
      } catch (err) {
        importStatus(err.message || 'Could not draft JSON with AI.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-ai-draft', false);
      }
    });
    el('btn-roleplay-library-json-preview')?.addEventListener('click', async () => {
      const sourceText = jsonEditorValue();
      const kind = trimValue(el('roleplay-library-import-kind')?.value);
      if (!sourceText) { importStatus('Paste or generate JSON in the editor first.', 'warn'); return; }
      const form = new FormData();
      form.append('target_kind', kind);
      form.append('source_text', sourceText);
      form.append('source_name', `editor_${kind || 'draft'}.json`);
      importStatus('Previewing JSON editor...', '');
      setBusy('btn-roleplay-library-json-preview', true, 'Previewing...');
      try {
        const data = await safeFetchJson('/api/roleplay/library/import-preview-text', { method: 'POST', body: form, cache: 'no-store' });
        renderImportPreview(data);
        importStatus(data.message || 'JSON editor preview ready.', 'ok');
      } catch (err) {
        renderImportPreview(null);
        importStatus(err.message || 'Could not preview the JSON editor.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-json-preview', false);
      }
    });
    el('btn-roleplay-library-import-apply')?.addEventListener('click', () => applyPreviewToBuilder());
    el('btn-roleplay-library-import-save')?.addEventListener('click', async () => {
      const previewId = trimValue(state.importPreview?.preview_id);
      if (!previewId) { importStatus('Preview an import first.', 'warn'); return; }
      const form = new FormData();
      form.append('preview_id', previewId);
      importStatus('Saving imported record...', '');
      setBusy('btn-roleplay-library-import-save', true, 'Saving...');
      try {
        const data = await safeFetchJson('/api/roleplay/library/import-commit', { method: 'POST', body: form, cache: 'no-store' });
        await refreshLibraryState({
          characterRecordId: data.import_kind === 'character' ? data.record?.id : undefined,
          worldRecordId: data.import_kind === 'world' ? data.record?.id : undefined,
          regionRecordId: data.import_kind === 'region' ? data.record?.id : undefined,
          cityRecordId: data.import_kind === 'city' ? data.record?.id : undefined,
          locationRecordId: data.import_kind === 'location' ? data.record?.id : undefined,
          artifactRecordId: data.import_kind === 'artifact' ? data.record?.id : undefined,
          ritualRecordId: data.import_kind === 'ritual' ? data.record?.id : undefined,
          cycleRecordId: data.import_kind === 'cycle' ? data.record?.id : undefined,
          creatureRecordId: data.import_kind === 'creature' ? data.record?.id : undefined,
          universeRecordId: data.import_kind === 'universe' ? data.record?.id : undefined,
          legendRecordId: data.import_kind === 'legend' ? data.record?.id : undefined,
          packRecordId: data.import_kind === 'pack' ? data.record?.id : undefined,
          scenarioRecordId: data.import_kind === 'scenario' ? data.record?.id : undefined,
          userCharacterId: el('roleplay-user-character-id')?.value,
          partnerCharacterId: el('roleplay-partner-character-id')?.value,
          worldId: el('roleplay-world-id')?.value,
          scenarioId: el('roleplay-scenario-id')?.value,
        });
        if (data.record && data.import_kind) {
          fillBuilderForKind(data.import_kind, data.record);
          openLibraryAccordion(data.import_kind);
          libraryStatus(importStatusIdForKind(data.import_kind), data.message || 'Imported record saved.', 'ok');
        }
        window.neoRefreshRoleplayLibrarySelections?.();
        importStatus(data.message || 'Imported record saved.', 'ok');
      } catch (err) {
        importStatus(err.message || 'Could not save imported record.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-import-save', false);
      }
    });
    el('btn-roleplay-library-template-download')?.addEventListener('click', async () => {
      const kind = trimValue(el('roleplay-library-import-kind')?.value);
      if (!kind) { importStatus('Choose a target library kind first.', 'warn'); return; }
      importStatus('Downloading JSON template...', '');
      setBusy('btn-roleplay-library-template-download', true, 'Downloading...');
      try {
        const filename = await downloadJsonFromApi(`/api/roleplay/library/export-template?kind=${encodeURIComponent(kind)}`, `roleplay_${kind}_template.json`);
        importStatus(`Downloaded ${filename}.`, 'ok');
      } catch (err) {
        importStatus(err.message || 'Could not download JSON template.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-template-download', false);
      }
    });
    el('btn-roleplay-library-record-export')?.addEventListener('click', async () => {
      const kind = trimValue(el('roleplay-library-import-kind')?.value);
      if (!kind) { importStatus('Choose a target library kind first.', 'warn'); return; }
      const recordId = currentSelectedLibraryRecordId(kind);
      if (!recordId) { importStatus('Load or select a saved library record first.', 'warn'); return; }
      importStatus('Exporting selected record...', '');
      setBusy('btn-roleplay-library-record-export', true, 'Exporting...');
      try {
        const filename = await downloadJsonFromApi(`/api/roleplay/library/export-record?kind=${encodeURIComponent(kind)}&record_id=${encodeURIComponent(recordId)}`, `roleplay_${kind}_${recordId}.json`);
        importStatus(`Downloaded ${filename}.`, 'ok');
      } catch (err) {
        importStatus(err.message || 'Could not export selected record.', 'warn');
      } finally {
        setBusy('btn-roleplay-library-record-export', false);
      }
    });
  }


  async function bindManager() {
    reorderLibrarySections();
    await refreshLibraryState({ userCharacterId: el('roleplay-user-character-id')?.value, partnerCharacterId: el('roleplay-partner-character-id')?.value, worldId: el('roleplay-world-id')?.value, scenarioId: el('roleplay-scenario-id')?.value }).catch(() => {});
    bindRepeaters();
    bindCharacterActions();
    bindWorldActions();
    bindLocationChains();
    bindRegionActions();
    bindCityActions();
    bindLocationActions();
    bindOrganizationActions();
    bindArtifactActions();
    bindRitualActions();
    bindCycleActions();
    bindCreatureActions();
    bindUniverseActions();
    bindLegendActions();
    bindPackActions();
    bindScenarioActions();
    bindImportActions();
    fillCharacterForm(null);
    fillScenarioForm(null);
  }

  window.neoRefreshRoleplayLibraryState = refreshLibraryState;
  window.neoGetRoleplayLibraryRecord = fetchRecord;
  window.neoResolveRoleplayAssetUrl = assetUrl;
  window.neoGetRoleplayLibraryStateSnapshot = () => ({ characters: state.characters.slice(), worlds: state.worlds.slice(), regions: state.regions.slice(), cities: state.cities.slice(), locations: state.locations.slice(), organizations: state.organizations.slice(), artifacts: state.artifacts.slice(), rituals: state.rituals.slice(), cycles: state.cycles.slice(), creatures: state.creatures.slice(), universes: state.universes.slice(), legends: state.legends.slice(), packs: state.packs.slice(), scenarios: state.scenarios.slice() });

  if (document.readyState === 'complete') bindManager();
  else document.addEventListener('DOMContentLoaded', bindManager, { once: true });
})();
