(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;

  function numValue(id, fallback) {
    const raw = Number(core.$(id)?.value || fallback || 0);
    return Number.isFinite(raw) ? raw : fallback;
  }

  function internalToolsEnabled() {
    return !!core.internalToolsVisible?.();
  }

  async function refreshInternalStudioDiagnostics() {
    if (!internalToolsEnabled()) return null;
    await refreshChromaStatus();
    await refreshMigrationStatus();
    await refreshCutoverStatus();
    return true;
  }

  function renderProjects() {
    const select = core.$('roleplay-v2-project-select');
    if (!select) return;
    const current = core.text(select.value);
    select.innerHTML = '<option value="">Select project</option>';
    state.projects.forEach(project => {
      const opt = document.createElement('option');
      opt.value = core.text(project.id);
      opt.textContent = `${core.text(project.title)}${core.text(project.author) ? ` — ${core.text(project.author)}` : ''}`;
      if (opt.value === current) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function studioModeSelection() {
    return core.currentModeSelection();
  }

  function isNovelAuthoringMode() {
    const mode = studioModeSelection();
    return mode.output_preset === 'novel' && mode.interaction_mode === 'authoring';
  }

  function studioModeProfile() {
    const mode = studioModeSelection();
    const isCanonicalRoleplay = mode.output_preset === 'roleplay' && mode.interaction_mode === 'roleplay';
    const internalTools = !!core.internalToolsVisible?.();
    const visibleSubtabs = isCanonicalRoleplay
      ? ['guide', 'assist', 'advanced', 'libraries', 'compile', 'runtime', 'engine']
      : ['guide', 'workspace', 'source', 'assist', 'advanced', 'libraries', 'compile', 'runtime', 'engine'];
    if (internalTools) visibleSubtabs.push('inspector');
    return {
      mode,
      isCanonicalRoleplay,
      defaultSubtab: isCanonicalRoleplay ? 'guide' : 'workspace',
      visibleSubtabs,
    };
  }

  function normalizeStudioSubtab(subtab = '') {
    const profile = studioModeProfile();
    const requested = core.text(subtab) || profile.defaultSubtab;
    return profile.visibleSubtabs.includes(requested) ? requested : profile.defaultSubtab;
  }

  function applyModeScopedStudioLayout() {
    const profile = studioModeProfile();
    document.querySelectorAll('#roleplay-v2-studio-subtabbar [data-roleplay-v2-studio-tab]').forEach(btn => {
      const tab = core.text(btn.getAttribute('data-roleplay-v2-studio-tab'));
      const visible = profile.visibleSubtabs.includes(tab);
      btn.classList.toggle('hidden', !visible);
      if (!visible) btn.classList.remove('active');
    });
    const breakdownCard = core.$('roleplay-v2-compile-breakdown-card');
    const sourceFields = core.$('roleplay-v2-compile-source-fields');
    const roleplayFields = core.$('roleplay-v2-compile-roleplay-fields');
    const canonButton = core.$('btn-roleplay-v2-canon-compile');
    const compileLaneNote = core.$('roleplay-v2-compile-lane-note');
    const breakdownNote = core.$('roleplay-v2-compile-breakdown-note');
    const pipelineNote = core.$('roleplay-v2-pipeline-note');
    if (profile.isCanonicalRoleplay) {
      breakdownCard?.classList.add('hidden');
      sourceFields?.classList.add('hidden');
      roleplayFields?.classList.remove('hidden');
      if (canonButton) canonButton.classList.add('hidden');
      if (compileLaneNote) compileLaneNote.textContent = 'Build memory from the selected Forge record, then rebuild the Scene packet that Scene will use.';
      if (breakdownNote) breakdownNote.textContent = 'Breakdown stays off the roleplay path.';
      if (pipelineNote) pipelineNote.textContent = 'Roleplay path = Forge → Compile → Runtime → Scene → Stories.';
    } else {
      breakdownCard?.classList.remove('hidden');
      sourceFields?.classList.remove('hidden');
      roleplayFields?.classList.add('hidden');
      if (canonButton) canonButton.classList.remove('hidden');
      if (compileLaneNote) compileLaneNote.textContent = 'Turn approved breakdowns into canon, then memory.';
      if (breakdownNote) breakdownNote.textContent = 'Generate helper output, then approve it for canon compile.';
      if (pipelineNote) pipelineNote.textContent = 'Authoring path = Project → Source → Compile → Runtime → Scene → Stories.';
    }
    const normalized = normalizeStudioSubtab(state.activeStudioSubtab);
    if (normalized !== state.activeStudioSubtab) {
      core.setStudioSubtab(normalized);
    }
    return profile;
  }

  const SHARED_GENERATION_DEFAULTS = {
    max_tokens: 320,
    temperature: 0.82,
    top_p: 0.92,
    top_k: 60,
    author_notes: '',
  };
  const SHARED_GENERATION_SETTINGS_KEY = 'neo_rpv2_shared_generation_defaults';

  function defaultSharedGenerationSettings() {
    return { ...SHARED_GENERATION_DEFAULTS };
  }

  function sanitizeSharedGenerationSettings(payload = {}) {
    const raw = payload && typeof payload === 'object' ? payload : {};
    return {
      max_tokens: Math.max(96, Math.min(2600, Number(raw.max_tokens || SHARED_GENERATION_DEFAULTS.max_tokens) || SHARED_GENERATION_DEFAULTS.max_tokens)),
      temperature: Math.max(0, Math.min(1.5, Number(raw.temperature ?? SHARED_GENERATION_DEFAULTS.temperature) || SHARED_GENERATION_DEFAULTS.temperature)),
      top_p: Math.max(0, Math.min(1, Number(raw.top_p ?? SHARED_GENERATION_DEFAULTS.top_p) || SHARED_GENERATION_DEFAULTS.top_p)),
      top_k: Math.max(0, Math.min(200, Number(raw.top_k ?? SHARED_GENERATION_DEFAULTS.top_k) || SHARED_GENERATION_DEFAULTS.top_k)),
      author_notes: core.text(raw.author_notes),
    };
  }

  function getStoredSharedGenerationSettings() {
    if (state.sharedGenerationSettings) return sanitizeSharedGenerationSettings(state.sharedGenerationSettings);
    let parsed = {};
    try { parsed = JSON.parse(core.safeLocalStorageGet(SHARED_GENERATION_SETTINGS_KEY) || '{}'); } catch (_err) { parsed = {}; }
    state.sharedGenerationSettings = sanitizeSharedGenerationSettings(parsed);
    return state.sharedGenerationSettings;
  }

  function sharedGenerationSettingsFromForm() {
    return sanitizeSharedGenerationSettings({
      max_tokens: numValue('roleplay-v2-shared-max-tokens', SHARED_GENERATION_DEFAULTS.max_tokens),
      temperature: Number(core.$('roleplay-v2-shared-temperature')?.value || SHARED_GENERATION_DEFAULTS.temperature),
      top_p: Number(core.$('roleplay-v2-shared-top-p')?.value || SHARED_GENERATION_DEFAULTS.top_p),
      top_k: numValue('roleplay-v2-shared-top-k', SHARED_GENERATION_DEFAULTS.top_k),
      author_notes: core.text(core.$('roleplay-v2-shared-author-notes')?.value),
    });
  }

  function renderSharedGenerationSettings() {
    const settings = getStoredSharedGenerationSettings();
    if (core.$('roleplay-v2-shared-max-tokens')) core.$('roleplay-v2-shared-max-tokens').value = String(settings.max_tokens);
    if (core.$('roleplay-v2-shared-temperature')) core.$('roleplay-v2-shared-temperature').value = String(settings.temperature);
    if (core.$('roleplay-v2-shared-top-p')) core.$('roleplay-v2-shared-top-p').value = String(settings.top_p);
    if (core.$('roleplay-v2-shared-top-k')) core.$('roleplay-v2-shared-top-k').value = String(settings.top_k);
    if (core.$('roleplay-v2-shared-author-notes')) core.$('roleplay-v2-shared-author-notes').value = settings.author_notes || '';
    if (core.$('roleplay-v2-shared-settings-badge')) core.$('roleplay-v2-shared-settings-badge').textContent = `max ${settings.max_tokens} · temp ${settings.temperature} · top_k ${settings.top_k}`;
    if (core.$('roleplay-v2-advanced-model-badge')) core.$('roleplay-v2-advanced-model-badge').textContent = `Scene + Assist · ${typeof currentModel === 'function' ? currentModel() : 'default'}`;
    if (core.$('roleplay-v2-shared-generation-note')) core.$('roleplay-v2-shared-generation-note').textContent = 'These defaults feed Scene live turns and Studio Assist drafts. The active text backend model still comes from the main model selector.';
    return settings;
  }

  function saveSharedGenerationSettings({ persist = true, announce = true } = {}) {
    const settings = sharedGenerationSettingsFromForm();
    state.sharedGenerationSettings = settings;
    if (persist) core.safeLocalStorageSet(SHARED_GENERATION_SETTINGS_KEY, JSON.stringify(settings));
    renderSharedGenerationSettings();
    if (announce) core.setStatus('roleplay-v2-advanced-status', 'Shared Scene + Assist defaults saved.', 'success');
    return settings;
  }

  function resetSharedGenerationSettings() {
    state.sharedGenerationSettings = defaultSharedGenerationSettings();
    core.safeLocalStorageSet(SHARED_GENERATION_SETTINGS_KEY, JSON.stringify(state.sharedGenerationSettings));
    renderSharedGenerationSettings();
    core.setStatus('roleplay-v2-advanced-status', 'Shared Scene + Assist defaults reset.', 'success');
    return state.sharedGenerationSettings;
  }

  function getSharedGenerationSettings() {
    return sanitizeSharedGenerationSettings(state.sharedGenerationSettings || getStoredSharedGenerationSettings());
  }

  function sharedAuthorNotesText() {
    return core.text(getSharedGenerationSettings().author_notes);
  }

  function appendSharedAuthorNotes(baseText = '') {
    const cleanBase = core.text(baseText);
    const notes = sharedAuthorNotesText();
    if (!notes) return cleanBase;
    return [cleanBase, `Shared author notes:\n${notes}`].filter(Boolean).join('\n\n');
  }



  const ASSIST_FORGE_WORKFLOWS = [
    { value: 'universe', label: 'Universe' },
    { value: 'world', label: 'World' },
    { value: 'region', label: 'Region' },
    { value: 'city', label: 'City' },
    { value: 'location', label: 'Location' },
    { value: 'organization', label: 'Organization' },
    { value: 'character', label: 'Character' },
    { value: 'artifact', label: 'Artifact' },
    { value: 'ritual', label: 'Ritual' },
    { value: 'cycle', label: 'Cycle / System' },
    { value: 'creature', label: 'Creature' },
    { value: 'legend', label: 'Legend' },
    { value: 'scenario', label: 'Scenario' },
  ];

  const ASSIST_SOURCE_WORKFLOWS = [
    { value: 'novel_source_document', label: 'Novel source ingest' },
  ];

  function currentAssistTarget() {
    return core.text(core.$('roleplay-v2-assist-target')?.value) || 'forge';
  }

  function assistWorkflowOptions(target = '') {
    return core.text(target) === 'source' ? ASSIST_SOURCE_WORKFLOWS : ASSIST_FORGE_WORKFLOWS;
  }

  function currentAssistWorkflow() {
    const options = assistWorkflowOptions(currentAssistTarget());
    const fallback = core.text(options[0]?.value);
    const current = core.text(core.$('roleplay-v2-assist-workflow')?.value) || fallback;
    return options.some(option => core.text(option.value) === current) ? current : fallback;
  }

  function assistWorkflowLabel(target = '', workflow = '') {
    const entry = assistWorkflowOptions(target).find(option => core.text(option.value) === core.text(workflow));
    return core.text(entry?.label) || core.text(workflow) || 'Workflow';
  }

  function renderAssistWorkflows() {
    const select = core.$('roleplay-v2-assist-workflow');
    if (!select) return;
    const target = currentAssistTarget();
    const current = core.text(select.value);
    const options = assistWorkflowOptions(target);
    select.innerHTML = '';
    options.forEach(option => {
      const node = document.createElement('option');
      node.value = core.text(option.value);
      node.textContent = core.text(option.label);
      select.appendChild(node);
    });
    select.value = options.some(option => core.text(option.value) === current) ? current : core.text(options[0]?.value);
  }

  function renderAssistUi() {
    renderAssistWorkflows();
    const target = currentAssistTarget();
    const workflow = currentAssistWorkflow();
    const workflowLabel = assistWorkflowLabel(target, workflow);
    const sourceCard = core.$('roleplay-v2-assist-source-card');
    const badge = core.$('roleplay-v2-assist-target-badge');
    const routeNote = core.$('roleplay-v2-assist-route-note');
    const outputNote = core.$('roleplay-v2-assist-output-note');
    const sendBtn = core.$('btn-roleplay-v2-assist-send');
    if (sourceCard) sourceCard.classList.toggle('hidden', target !== 'source');
    if (badge) badge.textContent = target === 'source' ? 'Source ingest JSON' : `${workflowLabel} markdown`;
    if (routeNote) routeNote.textContent = target === 'source'
      ? 'Target route · Studio → Source ingest form'
      : `Target route · Forge → ${workflowLabel} → markdown → normalize → JSON`;
    if (outputNote) outputNote.textContent = target === 'source'
      ? 'Assist fills the Source ingest form only. Review it, then save manually into the current project.'
      : 'Assist drafts parser-safe markdown, normalizes it into JSON, then routes it into the matching Forge editor. Review it, then apply/save manually.';
    if (sendBtn) sendBtn.textContent = target === 'source' ? 'Send to Source ingest' : `Send to Forge: ${workflowLabel}`;
  }

  function buildCurrentSourceAssistPayload() {
    return {
      title: core.text(core.$('roleplay-v2-doc-title')?.value),
      source_name: '',
      raw_text: core.text(core.$('roleplay-v2-doc-text')?.value),
      cleaned_text: '',
      source_format: 'text',
      document_type: core.text(core.$('roleplay-v2-doc-type')?.value) || 'novel_chapter',
      order_index: Number(core.$('roleplay-v2-doc-order-index')?.value || 0) || 1,
      chapter_number: Number(core.$('roleplay-v2-doc-chapter-number')?.value || 0) || 0,
      scene_number: Number(core.$('roleplay-v2-doc-scene-number')?.value || 0) || 0,
      extra: sourceDocumentExtraFromForm(),
    };
  }



  function hasMeaningfulSourceAssistPayload(payload = {}) {
    const record = payload && typeof payload === 'object' ? payload : {};
    const extra = record.extra && typeof record.extra === 'object' ? record.extra : {};
    return [
      core.text(record.title),
      core.text(record.raw_text),
      core.text(record.cleaned_text),
      core.text(extra.part_arc),
      core.text(extra.pov),
      core.text(extra.chapter_goal),
      core.text(extra.author_notes),
    ].some(Boolean)
      || Number(record.order_index || 0) > 1
      || Number(record.chapter_number || 0) > 1
      || Number(record.scene_number || 0) > 0
      || (core.text(record.document_type) && core.text(record.document_type) !== 'novel_chapter')
      || (core.text(extra.draft_status) && core.text(extra.draft_status) !== 'draft')
      || (core.text(extra.tense) && core.text(extra.tense) !== 'past');
  }

  function forgeAssistSeedJson(workflow = '') {
    const editorText = String(core.$('roleplay-v2-forge-json-editor')?.value || '').trim();
    if (!editorText) return '';
    try {
      const parsed = JSON.parse(editorText);
      if (!parsed || typeof parsed !== 'object') return '';
      if (core.text(parsed.kind) !== core.text(workflow)) return '';
      return JSON.stringify(parsed, null, 2);
    } catch (_err) {
      return '';
    }
  }

  function currentAssistJsonSeed(target = '', workflow = '') {
    const output = String(core.$('roleplay-v2-assist-json-output')?.value || '').trim();
    if (output) return output;
    if (core.text(target) === 'source') {
      const sourcePayload = buildCurrentSourceAssistPayload();
      return hasMeaningfulSourceAssistPayload(sourcePayload) ? JSON.stringify(sourcePayload, null, 2) : '';
    }
    return forgeAssistSeedJson(workflow);
  }

  function collectAssistForgeContext() {
    const scope = state.forge?.activeScope || {};
    return {
      universe_id: core.text(scope.universe_id),
      world_id: core.text(scope.world_id),
      region_id: core.text(scope.region_id),
      city_id: core.text(scope.city_id),
      location_id: '',
      scenario_id: '',
      species_hint: '',
      organization_ids_json: '[]',
    };
  }

  async function runAssistForgeDraft() {
    const workflow = currentAssistWorkflow();
    const settings = getSharedGenerationSettings();
    const brief = appendSharedAuthorNotes(core.text(core.$('roleplay-v2-assist-brief')?.value));
    const form = {
      target_kind: workflow,
      brief,
      draft_mode: core.text(core.$('roleplay-v2-assist-mode')?.value) || 'draft_scratch',
      draft_style: core.text(core.$('roleplay-v2-assist-style')?.value) || 'balanced',
      model: typeof currentModel === 'function' ? currentModel() : 'default',
      current_json: currentAssistJsonSeed('forge', workflow),
      max_tokens: settings.max_tokens,
      temperature: settings.temperature,
      top_p: settings.top_p,
      top_k: settings.top_k,
      ...collectAssistForgeContext(),
    };
    return core.postForm('/api/roleplay/v2/builders/assist-draft', form);
  }

  async function runAssistSourceDraft() {
    const settings = getSharedGenerationSettings();
    const brief = appendSharedAuthorNotes(core.text(core.$('roleplay-v2-assist-brief')?.value));
    const sourceText = String(core.$('roleplay-v2-assist-source-text')?.value || '');
    const currentJson = currentAssistJsonSeed('source', 'novel_source_document');
    const file = core.$('roleplay-v2-assist-source-file')?.files?.[0] || null;
    const form = new FormData();
    form.append('brief', brief);
    form.append('source_text', sourceText);
    form.append('source_name', file ? String(file.name || '') : '');
    form.append('draft_mode', core.text(core.$('roleplay-v2-assist-mode')?.value) || 'draft_scratch');
    form.append('draft_style', core.text(core.$('roleplay-v2-assist-style')?.value) || 'balanced');
    form.append('model', typeof currentModel === 'function' ? currentModel() : 'default');
    form.append('current_json', currentJson);
    form.append('max_tokens', String(settings.max_tokens));
    form.append('temperature', String(settings.temperature));
    form.append('top_p', String(settings.top_p));
    form.append('top_k', String(settings.top_k));
    if (file) form.append('file', file);
    const res = await fetch('/api/roleplay/v2/source/assist-json', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Source assist request failed.');
    return data;
  }

  async function buildAssistDraft() {
    const target = currentAssistTarget();
    core.setStatus('roleplay-v2-assist-status', target === 'source' ? 'Drafting source ingest JSON...' : 'Drafting Forge markdown...', '');
    const data = target === 'source' ? await runAssistSourceDraft() : await runAssistForgeDraft();
    if (core.$('roleplay-v2-assist-json-output')) core.$('roleplay-v2-assist-json-output').value = core.text(data.draft_markdown || data.draft_text || data.draft_json);
    core.setStatus('roleplay-v2-assist-status', data.message || 'Assist JSON ready.', 'success');
    core.setOutput(data);
    return data;
  }

  function applyAssistSourceDraft(payload = {}) {
    const record = payload && typeof payload === 'object' ? payload : {};
    const extra = record.extra && typeof record.extra === 'object' ? record.extra : {};
    core.setSubtab('studio');
    core.setStudioSubtab('source');
    if (core.$('roleplay-v2-doc-title')) core.$('roleplay-v2-doc-title').value = core.text(record.title);
    if (core.$('roleplay-v2-doc-type')) core.$('roleplay-v2-doc-type').value = core.text(record.document_type) || 'novel_chapter';
    if (core.$('roleplay-v2-doc-order-index')) core.$('roleplay-v2-doc-order-index').value = String(Number(record.order_index || 0) || 1);
    if (core.$('roleplay-v2-doc-chapter-number')) core.$('roleplay-v2-doc-chapter-number').value = String(Number(record.chapter_number || 0) || 0);
    if (core.$('roleplay-v2-doc-scene-number')) core.$('roleplay-v2-doc-scene-number').value = String(Number(record.scene_number || 0) || 0);
    if (core.$('roleplay-v2-doc-draft-status')) core.$('roleplay-v2-doc-draft-status').value = core.text(extra.draft_status) || 'draft';
    if (core.$('roleplay-v2-doc-part-arc')) core.$('roleplay-v2-doc-part-arc').value = core.text(extra.part_arc);
    if (core.$('roleplay-v2-doc-pov')) core.$('roleplay-v2-doc-pov').value = core.text(extra.pov);
    if (core.$('roleplay-v2-doc-tense')) core.$('roleplay-v2-doc-tense').value = core.text(extra.tense) || 'past';
    if (core.$('roleplay-v2-doc-chapter-goal')) core.$('roleplay-v2-doc-chapter-goal').value = core.text(extra.chapter_goal);
    if (core.$('roleplay-v2-doc-author-notes')) core.$('roleplay-v2-doc-author-notes').value = core.text(extra.author_notes);
    if (core.$('roleplay-v2-doc-text')) core.$('roleplay-v2-doc-text').value = core.text(record.raw_text || record.cleaned_text);
    core.setStatus('roleplay-v2-doc-status', 'Assist JSON routed into Source ingest. Review it, then save manually.', 'success');
    return record;
  }

  async function sendAssistDraft() {
    const target = currentAssistTarget();
    const draftText = String(core.$('roleplay-v2-assist-json-output')?.value || '').trim();
    if (!draftText) throw new Error(target === 'source' ? 'Assist JSON draft is empty. Build or paste JSON first.' : 'Assist markdown draft is empty. Build or paste markdown first.');
    if (target === 'source') {
      let payload;
      try {
        payload = JSON.parse(draftText);
      } catch (err) {
        throw new Error(`Assist JSON draft is not valid JSON: ${err.message || err}`);
      }
      if (!payload || typeof payload !== 'object') throw new Error('Assist JSON draft must be a JSON object.');
      applyAssistSourceDraft(payload);
      core.setStatus('roleplay-v2-assist-status', 'Assist JSON routed into Source ingest form.', 'success');
      return payload;
    }
    const workflow = currentAssistWorkflow();
    const normalized = await core.postForm('/api/roleplay/v2/builders/normalize-import', {
      kind: workflow,
      import_format: 'markdown',
      payload_text: draftText,
    });
    const payload = normalized && typeof normalized.normalized_payload === 'object' ? normalized.normalized_payload : null;
    if (!payload) throw new Error('Forge markdown normalize step did not return a normalized payload.');
    const forgeModule = core.modules?.forge;
    if (!forgeModule || typeof forgeModule.routeAssistDraftToJson !== 'function') throw new Error('Forge routing is unavailable right now.');
    await forgeModule.routeAssistDraftToJson(workflow, JSON.stringify(payload, null, 2), { applyMode: 'fill_empty_only' });
    core.setStatus('roleplay-v2-assist-status', `Assist markdown normalized and routed to Forge → ${assistWorkflowLabel('forge', workflow)} → JSON.`, 'success');
    return payload;
  }

  function clearAssistDraft() {
    if (core.$('roleplay-v2-assist-brief')) core.$('roleplay-v2-assist-brief').value = '';
    if (core.$('roleplay-v2-assist-source-text')) core.$('roleplay-v2-assist-source-text').value = '';
    if (core.$('roleplay-v2-assist-source-file')) core.$('roleplay-v2-assist-source-file').value = '';
    if (core.$('roleplay-v2-assist-json-output')) core.$('roleplay-v2-assist-json-output').value = '';
    core.setStatus('roleplay-v2-assist-status', 'Assist draft cleared.', 'success');
    renderAssistUi();
  }

  function draftStatusLabel(value = '') {
    const clean = core.text(value).replace(/_/g, ' ');
    return clean ? clean[0].toUpperCase() + clean.slice(1) : 'Draft';
  }

  function documentTypeLabel(value = '') {
    const clean = core.text(value).toLowerCase();
    return {
      novel_chapter: 'Novel chapter',
      novel_scene_section: 'Scene / section',
      novel_outline: 'Outline',
      author_notes: 'Author notes',
      reference_excerpt: 'Reference excerpt',
    }[clean] || (clean ? clean.replace(/_/g, ' ') : 'Source document');
  }

  function compactText(value = '', limit = 120) {
    const clean = core.text(value).replace(/\s+/g, ' ');
    return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean;
  }

  function sourceDocumentExtraFromForm() {
    return {
      part_arc: core.text(core.$('roleplay-v2-doc-part-arc')?.value),
      pov: core.text(core.$('roleplay-v2-doc-pov')?.value),
      tense: core.text(core.$('roleplay-v2-doc-tense')?.value) || 'past',
      chapter_goal: core.text(core.$('roleplay-v2-doc-chapter-goal')?.value),
      author_notes: core.text(core.$('roleplay-v2-doc-author-notes')?.value),
      draft_status: core.text(core.$('roleplay-v2-doc-draft-status')?.value) || 'draft',
    };
  }

  function clearSourceDraftForm({ keepDocumentSelection = false } = {}) {
    if (core.$('roleplay-v2-doc-title')) core.$('roleplay-v2-doc-title').value = '';
    if (core.$('roleplay-v2-doc-type')) core.$('roleplay-v2-doc-type').value = 'novel_chapter';
    if (core.$('roleplay-v2-doc-order-index')) core.$('roleplay-v2-doc-order-index').value = '1';
    if (core.$('roleplay-v2-doc-chapter-number')) core.$('roleplay-v2-doc-chapter-number').value = '1';
    if (core.$('roleplay-v2-doc-scene-number')) core.$('roleplay-v2-doc-scene-number').value = '0';
    if (core.$('roleplay-v2-doc-draft-status')) core.$('roleplay-v2-doc-draft-status').value = 'draft';
    if (core.$('roleplay-v2-doc-part-arc')) core.$('roleplay-v2-doc-part-arc').value = '';
    if (core.$('roleplay-v2-doc-pov')) core.$('roleplay-v2-doc-pov').value = '';
    if (core.$('roleplay-v2-doc-tense')) core.$('roleplay-v2-doc-tense').value = 'past';
    if (core.$('roleplay-v2-doc-chapter-goal')) core.$('roleplay-v2-doc-chapter-goal').value = '';
    if (core.$('roleplay-v2-doc-author-notes')) core.$('roleplay-v2-doc-author-notes').value = '';
    if (core.$('roleplay-v2-doc-text')) core.$('roleplay-v2-doc-text').value = '';
    if (!keepDocumentSelection && core.$('roleplay-v2-document-select')) core.$('roleplay-v2-document-select').value = '';
  }

  function hydrateSourceForm(document = null) {
    const doc = document && typeof document === 'object' ? document : {};
    const extra = doc.extra && typeof doc.extra === 'object' ? doc.extra : {};
    if (core.$('roleplay-v2-doc-title')) core.$('roleplay-v2-doc-title').value = core.text(doc.title);
    if (core.$('roleplay-v2-doc-type')) core.$('roleplay-v2-doc-type').value = core.text(doc.document_type) || 'novel_chapter';
    if (core.$('roleplay-v2-doc-order-index')) core.$('roleplay-v2-doc-order-index').value = String(Number(doc.order_index || 0) || 1);
    if (core.$('roleplay-v2-doc-chapter-number')) core.$('roleplay-v2-doc-chapter-number').value = String(Number(doc.chapter_number || 0) || 1);
    if (core.$('roleplay-v2-doc-scene-number')) core.$('roleplay-v2-doc-scene-number').value = String(Number(doc.scene_number || 0) || 0);
    if (core.$('roleplay-v2-doc-draft-status')) core.$('roleplay-v2-doc-draft-status').value = core.text(extra.draft_status || doc.draft_status) || 'draft';
    if (core.$('roleplay-v2-doc-part-arc')) core.$('roleplay-v2-doc-part-arc').value = core.text(extra.part_arc || doc.part_arc);
    if (core.$('roleplay-v2-doc-pov')) core.$('roleplay-v2-doc-pov').value = core.text(extra.pov || doc.pov);
    if (core.$('roleplay-v2-doc-tense')) core.$('roleplay-v2-doc-tense').value = core.text(extra.tense || doc.tense) || 'past';
    if (core.$('roleplay-v2-doc-chapter-goal')) core.$('roleplay-v2-doc-chapter-goal').value = core.text(extra.chapter_goal || doc.chapter_goal);
    if (core.$('roleplay-v2-doc-author-notes')) core.$('roleplay-v2-doc-author-notes').value = core.text(extra.author_notes || doc.author_notes);
    if (core.$('roleplay-v2-doc-text')) core.$('roleplay-v2-doc-text').value = core.text(doc.raw_text || doc.cleaned_text);
  }

  async function loadSourceDocumentIntoForm(documentId = '', { silent = false } = {}) {
    const cleanId = core.text(documentId || core.$('roleplay-v2-document-select')?.value);
    if (!cleanId) {
      if (!silent) clearSourceDraftForm({ keepDocumentSelection: false });
      return null;
    }
    const data = await core.getJson(`/api/roleplay/v2/source/document?document_id=${encodeURIComponent(cleanId)}`);
    hydrateSourceForm(data.document || {});
    if (!silent) {
      core.setStatus('roleplay-v2-doc-status', `Loaded ${core.text(data.document?.title) || cleanId} back into the source form.`, 'success');
      core.setOutput(data);
    }
    return data;
  }

  function renderSourceMode() {
    applyModeScopedStudioLayout();
    const badge = core.$('roleplay-v2-source-mode-badge');
    const note = core.$('roleplay-v2-source-authoring-note');
    const ingestNote = core.$('roleplay-v2-source-ingest-note');
    if (isNovelAuthoringMode()) {
      if (badge) badge.textContent = 'Novel authoring';
      if (note) note.textContent = 'This is the canonical novel + authoring path. Capture part / chapter / section / POV / tense / goal metadata here, then compile from the same source project without inventing a second novel workflow.';
      if (ingestNote) ingestNote.textContent = 'Save authored chapter or section text with structure metadata, then pick the exact document you want to break down and compile.';
      if (core.$('roleplay-v2-doc-type') && !core.text(core.$('roleplay-v2-doc-type').value)) core.$('roleplay-v2-doc-type').value = 'novel_chapter';
      return;
    }
    if (badge) badge.textContent = 'Source';
    if (note) note.textContent = 'Source stays inside the same V2 project path. Save source text + metadata here, then break it down and compile it into canon + memory.';
    if (ingestNote) ingestNote.textContent = 'Save chapter or section text into the selected V2 project, then break down the exact source document you want to compile.';
  }

  function renderWorkspace() {
    const summary = core.$('roleplay-v2-workspace-summary');
    const docSelect = core.$('roleplay-v2-document-select');
    const projectBadge = core.$('roleplay-v2-project-badge');
    const meta = core.$('roleplay-v2-workspace-meta');
    if (!summary || !docSelect || !projectBadge || !meta) return;
    const ws = state.workspace;
    const current = core.text(docSelect.value);
    docSelect.innerHTML = '<option value="">Select document</option>';
    if (!ws) {
      summary.textContent = 'No workspace loaded yet.';
      projectBadge.textContent = 'No project';
      meta.textContent = 'No workspace loaded yet.';
      return;
    }
    const docs = Array.isArray(ws.documents) ? ws.documents : [];
    docs.forEach(doc => {
      const opt = document.createElement('option');
      opt.value = core.text(doc.id);
      const parts = [
        core.text(doc.title) || core.text(doc.id),
        documentTypeLabel(doc.document_type),
        Number(doc.chapter_number || 0) > 0 ? `ch ${Number(doc.chapter_number)}` : '',
        Number(doc.scene_number || 0) > 0 ? `sec ${Number(doc.scene_number)}` : '',
        core.text(doc.part_arc) ? core.text(doc.part_arc) : '',
        core.text(doc.pov) ? `POV ${core.text(doc.pov)}` : '',
        core.text(doc.draft_status) ? draftStatusLabel(doc.draft_status) : '',
      ].filter(Boolean);
      opt.textContent = parts.join(' · ');
      if (opt.value === current) opt.selected = true;
      docSelect.appendChild(opt);
    });
    projectBadge.textContent = core.text(ws.project?.title) || core.text(ws.project?.id) || 'Project';
    const stats = ws.stats || {};
    const statusCounts = Object.entries(stats.draft_status_counts || {}).map(([key, value]) => `${draftStatusLabel(key)} ${value}`);
    meta.textContent = `${docs.length} document(s) · ${stats.total_characters || 0} chars · ${stats.chapter_count || 0} chapter slot(s) · ${stats.section_count || 0} section slot(s) · ${stats.part_count || 0} part/arc tag(s) · ${stats.pov_count || 0} POV tag(s)`;
    const lines = [
      `Project · ${core.text(ws.project?.title) || core.text(ws.project?.id) || 'Untitled project'}`,
      core.text(ws.project?.author) ? `Author · ${core.text(ws.project?.author)}` : '',
      `Documents · ${docs.length}`,
      `Total characters · ${stats.total_characters || 0}`,
      `Chapter slots · ${stats.chapter_count || 0}`,
      `Section slots · ${stats.section_count || 0}`,
      `Part / arc tags · ${stats.part_count || 0}`,
      `POV tags · ${stats.pov_count || 0}`,
      statusCounts.length ? `Draft statuses · ${statusCounts.join(' · ')}` : '',
      '',
      ...docs.map((doc, index) => {
        const docBits = [
          `${index + 1}. ${core.text(doc.title) || core.text(doc.id)}`,
          `type ${documentTypeLabel(doc.document_type)}`,
          Number(doc.order_index || 0) > 0 ? `order ${Number(doc.order_index)}` : '',
          Number(doc.chapter_number || 0) > 0 ? `chapter ${Number(doc.chapter_number)}` : '',
          Number(doc.scene_number || 0) > 0 ? `section ${Number(doc.scene_number)}` : '',
          core.text(doc.part_arc) ? `part ${core.text(doc.part_arc)}` : '',
          core.text(doc.pov) ? `POV ${core.text(doc.pov)}` : '',
          core.text(doc.tense) ? `${core.text(doc.tense)} tense` : '',
          core.text(doc.draft_status) ? draftStatusLabel(doc.draft_status) : '',
        ].filter(Boolean).join(' · ');
        const goal = core.text(doc.chapter_goal) ? `\n   Goal · ${compactText(doc.chapter_goal, 120)}` : '';
        const notes = core.text(doc.author_notes) ? `\n   Notes · ${compactText(doc.author_notes, 120)}` : '';
        return `${docBits}${goal}${notes}`;
      }),
    ].filter(Boolean);
    summary.textContent = lines.join('\n');
  }

  function isoMillis(value = '') {
    const clean = core.text(value);
    if (!clean) return 0;
    const stamp = Date.parse(clean);
    return Number.isFinite(stamp) ? stamp : 0;
  }

  function latestRuntimeBundleForEntity(entityId = '') {
    const cleanEntityId = core.text(entityId || core.$('roleplay-v2-entity-id')?.value);
    const rows = Array.isArray(state.runtimeBundles) ? state.runtimeBundles.slice() : [];
    const matching = cleanEntityId
      ? rows.filter(bundle => core.text(bundle.source_id) === cleanEntityId || (Array.isArray(bundle.selected_entity_ids) && bundle.selected_entity_ids.map(item => core.text(item)).includes(cleanEntityId)) || core.text(bundle.source_record_id) === cleanEntityId)
      : rows;
    matching.sort((left, right) => isoMillis(right?.updated_at || right?.latest_input_at) - isoMillis(left?.updated_at || left?.latest_input_at));
    return matching[0] || null;
  }

  function renderRuntimeFreshness(bundle = null, compileStatus = null) {
    const badge = core.$('roleplay-v2-runtime-freshness-badge');
    const note = core.$('roleplay-v2-runtime-freshness-note');
    const button = core.$('btn-roleplay-v2-runtime-build');
    const freshness = bundle && typeof bundle === 'object' ? bundle : null;
    if (button) button.textContent = freshness?.is_stale ? 'Rebuild Scene packet' : 'Build Scene packet';
    if (badge) badge.textContent = freshness ? (freshness.freshness_status === 'needs_rebuild' ? 'needs rebuild' : 'fresh') : (compileStatus?.needs_memory_recompile ? 'build memory first' : 'idle');
    if (note) {
      if (freshness?.is_stale) {
        note.textContent = `Latest Scene packet is stale. Reasons: ${(freshness.stale_reasons || []).join(', ') || 'input drift'}. Rebuild it before going live in Scene.`;
      } else if (freshness) {
        note.textContent = `Latest Scene packet is fresh. Built ${core.text(freshness.updated_at || freshness.bundle_updated_at || freshness.latest_input_at) || 'recently'} from ${core.text(freshness.source_record_label || freshness.source_record_id || freshness.source_id) || 'current focus'}.`;
      } else if (compileStatus?.needs_memory_recompile) {
        note.textContent = 'Build memory first, then create a fresh Scene packet for Scene.';
      } else {
        note.textContent = 'Scene packet = the active memory snapshot Scene uses. Rebuild it after changing records, canon, or memory build output.';
      }
    }
  }

  async function refreshPipelineStatus() {
    const panel = core.$('roleplay-v2-pipeline-status');
    const badge = core.$('roleplay-v2-pipeline-badge');
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    if (!panel || !badge) return null;
    if (!entityId) {
      const profile = studioModeProfile();
      badge.textContent = 'idle';
      panel.textContent = profile.isCanonicalRoleplay
        ? [
            'Compile guide',
            '- Roleplay path: start in Forge.',
            '- Pick a focus record, then build memory.',
            '- Build or rebuild the Scene packet before opening Scene.',
          ].join('\n')
        : [
            'Compile guide',
            '- Authoring path: Project → Source → Compile.',
            '- Save source text, generate breakdown, approve canon, then build memory.',
            '- Rebuild the Scene packet after any memory or canon pass before going back to Scene.',
          ].join('\n');
      renderRuntimeFreshness(null, null);
      return null;
    }
    let recordData = null;
    let memoryData = null;
    try { recordData = await core.getJson(`/api/roleplay/v2/builders/record?record_id=${encodeURIComponent(entityId)}`); } catch (_) { recordData = null; }
    try { memoryData = await core.getJson(`/api/roleplay/v2/memory/by-record?record_id=${encodeURIComponent(entityId)}&limit=6`); } catch (_) { memoryData = null; }
    const compileStatus = memoryData?.compile_status || {};
    const bundle = latestRuntimeBundleForEntity(entityId);
    const recordReady = !!recordData?.record;
    const memoryCompiled = !!compileStatus.memory_compiled_at;
    const memoryFresh = memoryCompiled && !compileStatus.needs_memory_recompile;
    const bundleFresh = !!bundle && !bundle.is_stale;
    const saveStage = recordReady ? 'ready' : 'missing';
    const compileStage = !recordReady ? 'missing' : (!memoryCompiled ? 'pending' : (memoryFresh ? 'fresh' : 'needs refresh'));
    const linkedStage = !recordReady ? 'missing' : (!memoryCompiled ? 'pending' : `ready · ${Number(compileStatus.fragment_id_count || 0)} fragments / ${Number(compileStatus.shared_id_count || 0)} shared / ${Number(compileStatus.relationship_id_count || 0)} relationships`);
    const runtimeStage = !bundle ? 'pending' : (bundleFresh ? `fresh · ${core.text(bundle.id)}` : `needs rebuild · ${core.text(bundle.id)}`);
    const rebuildStage = !bundle ? 'build first' : (bundleFresh ? 'not needed' : `recommended · ${(bundle.stale_reasons || []).join(', ') || 'input drift'}`);
    const tone = bundle?.is_stale || compileStatus?.needs_memory_recompile ? 'action needed' : bundleFresh ? 'runtime fresh' : memoryFresh ? 'ready to build' : recordReady ? 'compile next' : 'record missing';
    badge.textContent = tone;
    const lines = [
      `Focus entity · ${core.text(compileStatus.record_label || recordData?.record?.label || recordData?.record?.display_label || entityId)}`,
      `Record id · ${entityId}`,
      `Save record · ${saveStage}${recordData?.record ? ` · updated ${core.text(compileStatus.record_updated_at || recordData?.record?.meta?.updated_at) || 'unknown'}` : ''}`,
      `Build record memory · ${compileStage}${memoryCompiled ? ` · ${core.text(compileStatus.memory_compiled_at)}` : ''}`,
      `Linked memory set · ${linkedStage}`,
      `Build Scene packet · ${runtimeStage}`,
      `Rebuild Scene packet · ${rebuildStage}`,
    ];
    if (bundle?.latest_input_at) lines.push(`Latest packet input change · ${core.text(bundle.latest_input_at)}`);
    if (bundle?.source_record_label || bundle?.source_record_id) lines.push(`Packet source record · ${core.text(bundle.source_record_label || bundle.source_record_id)}`);
    panel.textContent = lines.join('\n');
    renderRuntimeFreshness(bundle, compileStatus);
    return { recordData, memoryData, bundle };
  }

  function renderListCard(row, rankLabel = '') {
    const title = core.text(row?.title) || core.text(row?.id) || 'Untitled memory';
    const summary = core.text(row?.summary) || core.text(row?.text).slice(0, 220) || core.text(row?.document).slice(0, 220) || 'No summary available.';
    const meta = [
      rankLabel,
      core.text(row?.memory_type),
      core.text(row?.source_ref),
      row?.score ? `score ${Number(row.score).toFixed(3)}` : '',
      row?.rerank_backend ? `via ${core.text(row.rerank_backend)}` : '',
      Array.isArray(row?.recovery_tags) && row.recovery_tags.length ? `recovery ${row.recovery_tags.join(',')}` : '',
      row?.continuity_bias ? `bias ${Number(row.continuity_bias).toFixed(3)}` : '',
    ].filter(Boolean).join(' · ');
    const memoryId = core.text(row?.memory_id || row?.id || row?.shared_memory_id || row?.callback_id);
    const dataAttrs = memoryId ? ` data-runtime-memory-id="${memoryId}"` : '';
    return `<button type="button" class="btn"${dataAttrs} style="display:grid; gap:6px; width:100%; text-align:left; padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
      <span class="row-between" style="align-items:start; gap:8px;"><strong style="font-size:13px;">${title}</strong><span class="badge">${core.text(row?.entity_id) || 'memory'}</span></span>
      <span class="mini-note" style="margin-top:0;">${summary}</span>
      <span class="mini-note" style="margin-top:0; opacity:0.8;">${meta || 'No scoring metadata.'}</span>
    </button>`;
  }

  function hydrateRetrievalTrace(trace = {}) {
    const cleanTrace = trace && typeof trace === 'object' ? trace : {};
    return {
      backend: cleanTrace.backend,
      reranker_backend: cleanTrace.reranker_backend,
      candidate_count: cleanTrace.candidate_count,
      result_count: cleanTrace.result_count,
      candidates: Array.isArray(cleanTrace.candidates) ? cleanTrace.candidates : [],
      reranked_candidates: Array.isArray(cleanTrace.reranked_candidates) ? cleanTrace.reranked_candidates : [],
      results: Array.isArray(cleanTrace.results) ? cleanTrace.results : [],
      diagnostics: cleanTrace.diagnostics || {},
      file_index: cleanTrace.file_index || null,
      sqlite_bridge: cleanTrace.sqlite_bridge || null,
      chroma_bridge: cleanTrace.chroma_bridge || null,
      selection_policy: cleanTrace.selection_policy || '',
      hybrid_rerank_backend: cleanTrace.hybrid_rerank_backend || '',
      diversity_backend: cleanTrace.diversity_backend || cleanTrace.diagnostics?.diversity_backend || '',
      control_backend: cleanTrace.control_backend || cleanTrace.diagnostics?.control_backend || '',
      continuity_tuning_backend: cleanTrace.continuity_tuning_backend || cleanTrace.diagnostics?.continuity_tuning_backend || '',
      source_weights: cleanTrace.source_weights || {},
      bucket_weights: cleanTrace.bucket_weights || {},
      mode_profile: cleanTrace.mode_profile || {},
      closed_loop_guardrails: cleanTrace.closed_loop_guardrails || cleanTrace.diagnostics?.closed_loop_guardrails || {},
      session_pressure_profile: cleanTrace.session_pressure_profile || cleanTrace.diagnostics?.session_pressure_profile || {},
      saturation_guardrails: cleanTrace.saturation_guardrails || cleanTrace.diagnostics?.saturation_guardrails || {},
      pressure_eval: cleanTrace.pressure_eval || {},
      budget_map: cleanTrace.budget_map || {},
      budget_trace: cleanTrace.budget_trace || {},
      trace_id: cleanTrace.trace_id || '',
      bundle_id: cleanTrace.bundle_id || '',
      created_at: cleanTrace.created_at || '',
    };
  }

  function renderRetrievalHistory() {
    const panel = core.$('roleplay-v2-retrieval-history');
    const badge = core.$('roleplay-v2-retrieval-history-count');
    const rows = Array.isArray(state.retrievalHistoryRows) ? state.retrievalHistoryRows : [];
    if (!panel || !badge) return;
    badge.textContent = String(rows.length || 0);
    if (!rows.length) {
      panel.textContent = 'No persisted retrieval traces yet.';
      return;
    }
    panel.innerHTML = rows.map((row, idx) => {
      const title = core.text(row?.query_text) || core.text(row?.bundle_id) || core.text(row?.trace_id) || `trace #${idx + 1}`;
      const meta = [
        core.text(row?.created_at),
        core.text(row?.selection_policy),
        row?.selected_count ? `${row.selected_count} selected` : '',
        core.text(row?.entity_label) || core.text(row?.entity_id),
      ].filter(Boolean).join(' · ');
      const budgets = row?.budget_map && typeof row.budget_map === 'object' ? Object.entries(row.budget_map).map(([k, v]) => `${k}:${v}`).join(', ') : '';
      return `<button type="button" class="btn" data-runtime-trace-id="${core.text(row?.trace_id)}" data-runtime-bundle-id="${core.text(row?.bundle_id)}" style="text-align:left; padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
        <div class="row-between" style="gap:8px; align-items:start;"><strong style="font-size:13px;">${title}</strong><span class="badge">${core.text(row?.mode) || 'roleplay'}</span></div>
        <div class="mini-note" style="margin-top:6px;">${meta || 'No history metadata.'}</div>
        <div class="mini-note" style="margin-top:6px; opacity:0.8;">${budgets || 'No packet budget metadata.'}</div>
      </button>`;
    }).join('');
    panel.querySelectorAll('[data-runtime-trace-id]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const traceId = core.text(btn.getAttribute('data-runtime-trace-id'));
        if (!traceId) return;
        try {
          await loadRetrievalHistoryEntry(traceId);
        } catch (err) {
          core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error');
        }
      });
    });
  }

  function renderRecoveryEval() {
    const panel = core.$('roleplay-v2-recovery-eval');
    const badge = core.$('roleplay-v2-recovery-eval-badge');
    const data = state.lastRecoveryEval || null;
    if (badge) badge.textContent = data?.evaluation ? 'ready' : 'idle';
    if (!panel) return;
    if (!data) {
      panel.textContent = 'Run a retrieval trace or select a persisted trace, then use the eval harness here.';
      return;
    }
    panel.textContent = JSON.stringify(data, null, 2);
  }

  async function runRecoveryEval() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const bundleId = core.text(core.$('roleplay-v2-scene-runtime-select')?.value) || core.text(state.lastRetrievalResult?.bundle_id);
    const traceId = core.text(state.lastRetrievalResult?.trace_id);
    const queryText = core.text(core.$('roleplay-v2-query')?.value);
    const mode = core.currentModeSelection();
    const topK = Number(core.$('roleplay-v2-runtime-top-k')?.value || 8);
    const params = new URLSearchParams();
    if (traceId) params.set('trace_id', traceId);
    else if (bundleId) params.set('bundle_id', bundleId);
    else {
      if (projectId) params.set('project_id', projectId);
      if (entityId) params.set('entity_id', entityId);
      if (queryText) params.set('query', queryText);
      params.set('mode', mode.output_preset);
      params.set('top_k', String(topK));
    }
    const data = await core.getJson(`/api/roleplay/v2/runtime/recovery-eval?${params.toString()}`);
    state.lastRecoveryEval = data;
    renderRecoveryEval();
    core.setStatus('roleplay-v2-runtime-status', `Recovery eval ready from ${core.text(data.source) || 'runtime trace'}.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function applyMemoryControl(action = 'pin', cooldownMinutes = 60) {
    const inferredId = core.text(core.$('roleplay-v2-memory-control-id')?.value) || core.text((state.lastRetrievalResult?.results || [])[0]?.id);
    if (!inferredId) throw new Error('Provide a memory id or build a Scene packet first so Studio can infer one.');
    const projectId = core.text(state.activeProjectId) || core.text(state.activeRuntimeBundle?.project_id) || core.text(state.lastRetrievalResult?.diagnostics?.project_id);
    const entityId = core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id) || core.text(state.lastRetrievalResult?.diagnostics?.entity_id);
    const payload = await core.postForm('/api/roleplay/v2/runtime/memory-control', {
      memory_id: inferredId,
      project_id: projectId,
      entity_id: entityId,
      action,
      cooldown_minutes: cooldownMinutes,
    });
    if (core.$('roleplay-v2-memory-control-id')) core.$('roleplay-v2-memory-control-id').value = inferredId;
    core.setStatus('roleplay-v2-memory-control-status', `${action} applied to ${inferredId}.`, 'success');
    core.setOutput(payload);
    return payload;
  }



function renderCutoverStatus() {
  const badge = core.$('roleplay-v2-cutover-badge');
  const statusPanel = core.$('roleplay-v2-cutover-status');
  const note = core.$('roleplay-v2-cutover-note');
  const data = state.cutoverStatus || null;
  const blockers = Array.isArray(data?.blockers) ? data.blockers : [];
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
  const validation = data?.validation?.counts || {};
  if (badge) {
    if (!data) badge.textContent = 'idle';
    else if (blockers.length) badge.textContent = `blocked · ${blockers.length}`;
    else if (data.ready_for_hard_removal) badge.textContent = `validated · ${validation.passed || 0}/${validation.total || 0}`;
    else if (data.state?.soft_cutover_active) badge.textContent = `active · ${warnings.length} warning(s)`;
    else badge.textContent = `ready · ${warnings.length} warning(s)`;
  }
  if (statusPanel) statusPanel.textContent = data ? JSON.stringify(data, null, 2) : 'Cutover validation status will appear here.';
  if (note) {
    if (data?.ready_for_hard_removal) note.textContent = 'V2 validation passed and legacy transition dependencies are clear. Remaining notes are environment-level only.';
    else if (data?.state?.soft_cutover_active) note.textContent = blockers.length
      ? 'Soft cutover is active, but validation still has real blockers.'
      : 'Soft cutover is active. Remaining warnings are validation or environment follow-up, not normal-user navigation blockers.';
    else note.textContent = blockers.length
      ? 'Soft cutover is still blocked by remaining validation blockers.'
      : 'Soft cutover can be applied once you are ready.';
  }
}

async function refreshCutoverStatus() {
  const data = await core.getJson('/api/roleplay/v2/cutover/status');
  state.cutoverStatus = data;
  renderCutoverStatus();
  try { window.neoRoleplayV2Cutover?.applyStatus?.(data); } catch (_) {}
  try { core.modules?.libraries?.syncLegacyButtons?.(); } catch (_) {}
  return data;
}

async function applySoftCutover(enabled = true) {
  const data = await core.postForm('/api/roleplay/v2/cutover/apply', { enabled: enabled ? '1' : '0', force: '0' });
  state.cutoverStatus = data.status || null;
  renderCutoverStatus();
  try { window.neoRoleplayV2Cutover?.applyStatus?.(state.cutoverStatus); } catch (_) {}
  try { core.modules?.libraries?.syncLegacyButtons?.(); } catch (_) {}
  core.setStatus('roleplay-v2-cutover-note', data.message || (enabled ? 'Soft cutover applied.' : 'Soft cutover disabled.'), 'success');
  core.setOutput(data);
  return data;
}

function renderMigrationStatus() {
  const badge = core.$('roleplay-v2-migration-badge');
  const statusPanel = core.$('roleplay-v2-migration-status');
  const reportPanel = core.$('roleplay-v2-migration-report');
  const data = state.phase14MigrationStatus || null;
  const report = state.phase14MigrationReport || null;
  if (badge) badge.textContent = data?.gaps?.length ? `needs work · ${data.gaps.length}` : (data ? 'ready' : 'idle');
  if (statusPanel) statusPanel.textContent = data ? JSON.stringify(data, null, 2) : 'Migration status will appear here.';
  if (reportPanel) reportPanel.textContent = report ? JSON.stringify(report, null, 2) : 'Last migration run report will appear here.';
}

async function refreshMigrationStatus() {
  const data = await core.getJson('/api/roleplay/v2/migration/status');
  state.phase14MigrationStatus = data;
  renderMigrationStatus();
  return data;
}

async function runPhase14Migration() {
  const data = await core.postForm('/api/roleplay/v2/migration/run', {
    sync_builders: '1',
    backfill_memory: '1',
    backfill_stories: '1',
    sync_chroma: '1',
    prune_missing: '0',
  });
  state.phase14MigrationReport = data;
  state.phase14MigrationStatus = data.status || null;
  renderMigrationStatus();
  await refreshRetrievalStatus();
  await refreshRetrievalHistory();
  await refreshChromaStatus();
  core.setStatus('roleplay-v2-runtime-status', 'Phase 14 migration + cleanup finished.', 'success');
  core.setOutput(data);
  return data;
}

  function formatChromaStatusText(status = null) {
    if (!status || typeof status !== 'object') return 'Chroma mirror status will appear here.';
    const backend = status.embedding_status && typeof status.embedding_status === 'object' ? status.embedding_status : {};
    const overview = status.sqlite_overview && typeof status.sqlite_overview === 'object' ? status.sqlite_overview : {};
    const lines = [];
    const stateLabel = core.text(status.badge_label || status.state || (status.chroma_ready ? 'ready' : 'offline'));
    const backendLabel = core.text(backend.active_backend_label || backend.active_backend || 'Memory backend');
    const storageLabel = core.text(status.storage_mode_label || backend.storage_mode_label);
    const collection = core.text(status.resolved_collection || (backend.resolved_collections || {}).roleplay_v2 || status.collection);
    lines.push(`State: ${stateLabel}`);
    lines.push(`Backend: ${backendLabel}`);
    if (storageLabel) lines.push(`Storage: ${storageLabel}`);
    if (collection) lines.push(`Collection: ${collection}`);
    const summary = core.text(status.summary || backend.summary);
    const hint = core.text(status.action_hint || backend.ui_message);
    if (summary) {
      lines.push('');
      lines.push(summary);
    }
    if (hint) lines.push(hint);
    const counts = [
      `fragments ${Number(overview.memory_fragment_count || 0)}`,
      `shared ${Number(overview.shared_memory_count || 0)}`,
      `callbacks ${Number(overview.callback_anchor_count || 0)}`,
      `summaries ${Number(overview.turn_summary_count || 0)}`,
      `traces ${Number(overview.retrieval_trace_count || 0)}`,
    ];
    lines.push('');
    lines.push(`SQLite overview: ${counts.join(' · ')}`);
    return lines.join('\n');
  }

  function renderChromaStatus() {
    const out = core.$('roleplay-v2-chroma-status');
    const badge = core.$('roleplay-v2-chroma-ready-badge');
    const resultBadge = core.$('roleplay-v2-chroma-result-count');
    const results = core.$('roleplay-v2-chroma-results');
    const status = state.chromaStatus || null;
    if (badge) badge.textContent = core.text(status?.badge_label || status?.state || (status?.chroma_ready ? 'ready' : 'offline')) || 'offline';
    if (out) out.textContent = formatChromaStatusText(status);
    const rows = Array.isArray(state.chromaQueryRows) ? state.chromaQueryRows : [];
    if (resultBadge) resultBadge.textContent = String(rows.length || 0);
    if (results) results.innerHTML = rows.length ? rows.map((row, idx) => renderListCard({
      id: row.id,
      title: row.metadata?.title || row.id,
      summary: row.document,
      source_ref: row.metadata?.source_ref,
      score: typeof row.distance === 'number' ? (1 - row.distance) : '',
      memory_type: row.metadata?.memory_type || row.metadata?.chunk_type,
      entity_id: row.metadata?.entity_id || row.metadata?.builder_record_id || row.metadata?.source_ref,
    }, `semantic #${idx + 1}`)).join('') : 'No semantic preview results yet.';
  }

  async function refreshChromaStatus() {
    const data = await core.getJson('/api/roleplay/v2/runtime/chroma-status');
    state.chromaStatus = data;
    renderChromaStatus();
    return data;
  }

  async function syncChromaMirror() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const data = await core.postForm('/api/roleplay/v2/runtime/chroma-sync', { project_id: projectId, entity_id: entityId, limit: 500 });
    state.chromaStatus = data;
    renderChromaStatus();
    core.setStatus('roleplay-v2-runtime-status', data.message || `Mirrored ${data.indexed || 0} SQLite memory rows into Chroma.`, data.ok === false ? 'error' : 'success');
    core.setOutput(data);
    return data;
  }

  async function runChromaPreview() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const queryText = core.text(core.$('roleplay-v2-chroma-query')?.value);
    if (!queryText) throw new Error('Chroma semantic query is required.');
    const data = await core.getJson(`/api/roleplay/v2/runtime/chroma-query?query_text=${encodeURIComponent(queryText)}&project_id=${encodeURIComponent(projectId)}&entity_id=${encodeURIComponent(entityId)}&limit=10`);
    state.chromaQueryRows = Array.isArray(data.rows) ? data.rows : [];
    renderChromaStatus();
    const backend = data?.embedding_status || state.chromaStatus?.embedding_status || {};
    const backendLabel = core.text(backend.active_backend_label || backend.active_backend || 'Memory backend');
    const storageLabel = core.text(backend.storage_mode_label || state.chromaStatus?.storage_mode_label);
    core.setStatus('roleplay-v2-runtime-status', `Chroma semantic preview returned ${state.chromaQueryRows.length} row(s). ${backendLabel}${storageLabel ? ` · ${storageLabel}` : ''}.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function refreshRetrievalHistory() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const bundleId = core.text(core.$('roleplay-v2-scene-runtime-select')?.value);
    const data = await core.getJson(`/api/roleplay/v2/runtime/retrieval-history?project_id=${encodeURIComponent(projectId)}&entity_id=${encodeURIComponent(entityId)}&bundle_id=${encodeURIComponent(bundleId)}&limit=16`);
    state.retrievalHistoryRows = Array.isArray(data.rows) ? data.rows : [];
    renderRetrievalHistory();
    return data;
  }

  async function loadRetrievalHistoryEntry(traceId = '') {
    const cleanTraceId = core.text(traceId);
    if (!cleanTraceId) throw new Error('Trace id is required.');
    const data = await core.getJson(`/api/roleplay/v2/runtime/retrieval-history-entry?trace_id=${encodeURIComponent(cleanTraceId)}`);
    const entry = data.entry || {};
    state.lastRetrievalResult = hydrateRetrievalTrace({ ...(entry.trace || {}), trace_id: entry.trace_id, bundle_id: entry.bundle_id, created_at: entry.created_at });
    state.lastRecoveryEval = null;
    if (core.$('roleplay-v2-scene-runtime-select') && core.text(entry.bundle_id)) core.$('roleplay-v2-scene-runtime-select').value = core.text(entry.bundle_id);
    renderSourceMode();
    applyModeScopedStudioLayout();
    renderAssistUi();
    renderSharedGenerationSettings();
    renderRetrievalPanels();
    renderRecoveryEval();
    core.setStatus('roleplay-v2-runtime-status', `Loaded persisted retrieval history ${cleanTraceId}.`, 'success');
    core.setOutput(data);
    return data;
  }

  function currentStudioContinuitySeedRows() {
    const candidates = Array.isArray(state.lastRetrievalResult?.candidates) ? state.lastRetrievalResult.candidates : [];
    const reranked = Array.isArray(state.lastRetrievalResult?.reranked_candidates) ? state.lastRetrievalResult.reranked_candidates : [];
    const results = Array.isArray(state.lastRetrievalResult?.results) ? state.lastRetrievalResult.results : [];
    const merged = [...results, ...reranked, ...candidates];
    return merged.map((row, index) => ({
      memory_id: core.text(row?.memory_id || row?.id || row?.shared_memory_id || row?.callback_id),
      title: core.text(row?.title),
      summary: core.text(row?.summary),
      text: core.text(row?.text || row?.document),
      memory_type: core.text(row?.memory_type),
      entity_id: core.text(row?.entity_id),
      entity_label: core.text(row?.entity_label),
      source_ref: core.text(row?.source_ref),
      score: Number(row?.score || 0),
      rerank_score: Number(row?.rerank_score || 0),
      continuity_bias: Number(row?.continuity_bias || 0),
      retrieval_rank: Number(row?.rank || row?.retrieval_rank || index + 1),
      selected_from_trace: results.some(item => core.text(item?.memory_id || item?.id || item?.shared_memory_id || item?.callback_id) === core.text(row?.memory_id || row?.id || row?.shared_memory_id || row?.callback_id)),
      recovery_tags: Array.isArray(row?.recovery_tags) ? row.recovery_tags : [],
    })).filter(row => row.memory_id);
  }

  function studioContinuityFilters() {
    return {
      project_id: core.text(core.$('roleplay-v2-project-select')?.value),
      entity_id: core.text(core.$('roleplay-v2-entity-id')?.value) || core.text(state.lastRuntimeBundle?.packet?.entity_focus?.id),
      bundle_id: core.text(state.lastRuntimeBundle?.id) || core.text(core.$('roleplay-v2-scene-runtime-select')?.value),
      trace_id: core.text(state.lastRetrievalResult?.trace_id),
      source_ref: core.text(state.lastRuntimeBundle?.packet?.working_memory?.source_ref),
      query: core.text(core.$('roleplay-v2-query')?.value),
      origin: 'auto',
    };
  }

  function renderRetrievalPanels() {
    const diagnostics = core.$('roleplay-v2-retrieval-diagnostics');
    const candidates = core.$('roleplay-v2-retrieval-candidates');
    const results = core.$('roleplay-v2-retrieval-results');
    const candidateBadge = core.$('roleplay-v2-retrieval-candidate-count');
    const resultBadge = core.$('roleplay-v2-retrieval-result-count');
    const data = state.lastRetrievalResult;
    if (!diagnostics || !candidates || !results || !candidateBadge || !resultBadge) return;
    if (!data) {
      diagnostics.textContent = 'Run retrieval to inspect the trace.';
      candidates.textContent = 'No retrieval candidates yet.';
      results.textContent = 'No reranked results yet.';
      candidateBadge.textContent = '0';
      resultBadge.textContent = '0';
      renderRecoveryEval();
      core.modules?.continuityControls?.refreshContext?.('studio', { silent: true }).catch(() => null);
      return;
    }
    candidateBadge.textContent = String(data.candidate_count || (data.candidates || []).length || 0);
    resultBadge.textContent = String(data.result_count || (data.results || []).length || 0);
    diagnostics.textContent = JSON.stringify({
      backend: data.backend,
      reranker_backend: data.reranker_backend,
      selection_policy: data.selection_policy,
      hybrid_rerank_backend: data.hybrid_rerank_backend,
      continuity_tuning_backend: data.continuity_tuning_backend,
      source_weights: data.source_weights,
      bucket_weights: data.bucket_weights,
      mode_profile: data.mode_profile,
      budget_map: data.budget_map,
      budget_trace: data.budget_trace,
      diagnostics: data.diagnostics,
      file_index: data.file_index,
      sqlite_bridge: data.sqlite_bridge,
      chroma_bridge: data.chroma_bridge,
      trace_id: data.trace_id,
      bundle_id: data.bundle_id,
      created_at: data.created_at,
    }, null, 2);
    const candidateRows = Array.isArray(data.candidates) ? data.candidates : [];
    const rerankedRows = Array.isArray(data.reranked_candidates) ? data.reranked_candidates : [];
    const finalRows = Array.isArray(data.results) ? data.results : [];
    candidates.innerHTML = candidateRows.length ? candidateRows.map((row, idx) => renderListCard(row, `candidate #${idx + 1}`)).join('') : 'No retrieval candidates yet.';
    results.innerHTML = finalRows.length ? finalRows.map((row, idx) => renderListCard(row, `result #${idx + 1}`)).join('') : (rerankedRows.length ? rerankedRows.slice(0, Math.max(1, data.diagnostics?.top_k || 8)).map((row, idx) => renderListCard(row, `result #${idx + 1}`)).join('') : 'No reranked results yet.');
    [candidates, results].forEach(root => {
      root?.querySelectorAll('[data-runtime-memory-id]').forEach(btn => {
        btn.addEventListener('click', () => core.modules?.continuityControls?.bindExternalSelection?.('studio', core.text(btn.getAttribute('data-runtime-memory-id'))));
      });
    });
    core.modules?.continuityControls?.refreshContext?.('studio', { silent: true }).catch(() => null);
  }

  function renderEngineStatusCards() {
    const embedding = core.$('roleplay-v2-engine-embedding-status');
    const reranker = core.$('roleplay-v2-engine-reranker-status');
    const index = core.$('roleplay-v2-engine-index-status');
    const data = state.retrievalStatus;
    if (!embedding || !reranker || !index) return;
    if (!data) {
      embedding.textContent = 'Waiting for retrieval status.';
      reranker.textContent = 'Waiting for retrieval status.';
      index.textContent = 'Waiting for retrieval status.';
      return;
    }
    embedding.textContent = [
      `backend: ${core.text(data.settings?.backend) || 'hashing_local'}`,
      `ready: ${data.backend_ready ? 'yes' : 'no'}`,
      `path exists: ${data.paths?.embedding_model_exists ? 'yes' : 'no'}`,
      `embedding status: ${core.text(data.index?.embedding_status) || 'unknown'}`,
    ].join('\n');
    reranker.textContent = [
      `backend: ${core.text(data.settings?.reranker_backend) || 'token_overlap'}`,
      `ready: ${data.reranker_ready ? 'yes' : 'no'}`,
      `path exists: ${data.paths?.reranker_model_exists ? 'yes' : 'no'}`,
      `deps: sentence_transformers=${data.dependencies?.sentence_transformers ? 'yes' : 'no'}`,
    ].join('\n');
    index.textContent = [
      `entries: ${data.index?.entry_count || 0}`,
      `indexed at: ${core.text(data.index?.last_indexed_at) || 'never'}`,
      `top_k: ${data.settings?.top_k || 8}`,
      `preview_k: ${data.settings?.preview_k || 16}`,
    ].join('\n');
  }

  function renderRetrievalStatus() {
    const data = state.retrievalStatus;
    const badge = core.$('roleplay-v2-backend-badge');
    if (!data || !badge) return;
    badge.textContent = `${core.text(data.settings?.backend) || 'hashing_local'} · ${data.index?.entry_count || 0} indexed`;
    if (core.$('roleplay-v2-retrieval-backend')) core.$('roleplay-v2-retrieval-backend').value = core.text(data.settings?.backend) || 'hashing_local';
    if (core.$('roleplay-v2-reranker-backend')) core.$('roleplay-v2-reranker-backend').value = core.text(data.settings?.reranker_backend) || 'token_overlap';
    if (core.$('roleplay-v2-embedding-path')) core.$('roleplay-v2-embedding-path').value = core.text(data.settings?.embedding_model_path);
    if (core.$('roleplay-v2-reranker-path')) core.$('roleplay-v2-reranker-path').value = core.text(data.settings?.reranker_model_path);
    if (core.$('roleplay-v2-retrieval-top-k')) core.$('roleplay-v2-retrieval-top-k').value = String(data.settings?.top_k || 8);
    if (core.$('roleplay-v2-retrieval-preview-k')) core.$('roleplay-v2-retrieval-preview-k').value = String(data.settings?.preview_k || 16);
    if (core.$('roleplay-v2-runtime-top-k') && !core.text(core.$('roleplay-v2-runtime-top-k').value)) core.$('roleplay-v2-runtime-top-k').value = String(data.settings?.top_k || 8);
    if (core.$('roleplay-v2-runtime-preview-k') && !core.text(core.$('roleplay-v2-runtime-preview-k').value)) core.$('roleplay-v2-runtime-preview-k').value = String(data.settings?.preview_k || 16);
    renderEngineStatusCards();
    renderWorkspace();
  }

  async function refreshProjects() {
    const data = await core.getJson('/api/roleplay/v2/source/project/list');
    state.projects = Array.isArray(data.projects) ? data.projects : [];
    renderProjects();
    return data;
  }

  async function refreshRetrievalStatus() {
    const data = await core.getJson('/api/roleplay/v2/retrieval/status');
    state.retrievalStatus = data;
    renderRetrievalStatus();
    return data;
  }

  async function saveRetrievalSettings() {
    const data = await core.postForm('/api/roleplay/v2/retrieval/settings/save', {
      backend: core.text(core.$('roleplay-v2-retrieval-backend')?.value) || 'hashing_local',
      embedding_model_path: core.text(core.$('roleplay-v2-embedding-path')?.value),
      reranker_backend: core.text(core.$('roleplay-v2-reranker-backend')?.value) || 'token_overlap',
      reranker_model_path: core.text(core.$('roleplay-v2-reranker-path')?.value),
      top_k: numValue('roleplay-v2-retrieval-top-k', 8),
      preview_k: numValue('roleplay-v2-retrieval-preview-k', 16),
    });
    core.setStatus('roleplay-v2-settings-status', data.message || 'Retrieval settings saved.', 'success');
    await refreshRetrievalStatus();
    core.setOutput(data);
  }

  async function rebuildIndex() {
    const data = await core.postForm('/api/roleplay/v2/retrieval/reindex', {});
    core.setStatus('roleplay-v2-settings-status', data.message || 'Retrieval index rebuilt.', 'success');
    await refreshRetrievalStatus();
    core.setOutput(data);
  }

  async function loadWorkspace(projectId) {
    if (!core.text(projectId)) throw new Error('Select a source project first.');
    const data = await core.getJson(`/api/roleplay/v2/source/project/workspace?project_id=${encodeURIComponent(projectId)}`);
    state.workspace = data;
    renderSourceMode();
    renderWorkspace();
    await refreshRuntimeBundles();
    return data;
  }

  async function createProject() {
    const title = core.text(core.$('roleplay-v2-project-title')?.value);
    const author = core.text(core.$('roleplay-v2-project-author')?.value);
    if (!title) throw new Error('Project title is required.');
    const data = await core.postForm('/api/roleplay/v2/source/project/create', { title, author, source_language: 'en' });
    core.setStatus('roleplay-v2-project-status', data.message || 'Project created.', 'success');
    await refreshProjects();
    core.$('roleplay-v2-project-select').value = core.text(data.project?.id);
    await loadWorkspace(core.text(data.project?.id));
    core.setOutput(data);
  }

  async function saveDocument() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const title = core.text(core.$('roleplay-v2-doc-title')?.value);
    const rawText = core.text(core.$('roleplay-v2-doc-text')?.value);
    const documentType = core.text(core.$('roleplay-v2-doc-type')?.value) || 'novel_chapter';
    const orderIndex = Number(core.$('roleplay-v2-doc-order-index')?.value || 0) || 1;
    const chapterNumber = Number(core.$('roleplay-v2-doc-chapter-number')?.value || 0) || 0;
    const sceneNumber = Number(core.$('roleplay-v2-doc-scene-number')?.value || 0) || 0;
    const extra = sourceDocumentExtraFromForm();
    if (!projectId) throw new Error('Select a source project first.');
    if (!rawText) throw new Error('Source text is required.');
    const fallbackTitle = documentType === 'novel_scene_section'
      ? `Chapter ${chapterNumber || 1} · Section ${sceneNumber || 1}`
      : documentType === 'novel_outline'
        ? `Outline ${orderIndex}`
        : documentType === 'author_notes'
          ? `Author notes ${orderIndex}`
          : `Chapter ${chapterNumber || 1}`;
    const data = await core.postForm('/api/roleplay/v2/source/document/save-text', {
      project_id: projectId,
      title: title || fallbackTitle,
      raw_text: rawText,
      chapter_number: chapterNumber,
      scene_number: sceneNumber,
      document_type: documentType,
      source_format: 'text',
      order_index: orderIndex,
      extra_json: JSON.stringify(extra),
    });
    core.setStatus('roleplay-v2-doc-status', data.message || 'Source document saved.', 'success');
    await loadWorkspace(projectId);
    core.$('roleplay-v2-document-select').value = core.text(data.document?.id);
    await loadSourceDocumentIntoForm(core.text(data.document?.id), { silent: true }).catch(() => null);
    core.setOutput(data);
  }

  async function generateBreakdown() {
    const documentId = core.text(core.$('roleplay-v2-document-select')?.value);
    if (!documentId) throw new Error('Select a source document first.');
    const data = await core.postForm('/api/roleplay/v2/breakdown/from-document', { document_id: documentId });
    state.lastHelperOutput = data.helper_output || null;
    core.$('roleplay-v2-helper-output-id').value = core.text(data.helper_output?.id);
    core.setStatus('roleplay-v2-breakdown-status', data.message || 'Breakdown generated.', 'success');
    core.setOutput(data);
  }

  async function approveBreakdown() {
    let helper = state.lastHelperOutput;
    const helperId = core.text(core.$('roleplay-v2-helper-output-id')?.value);
    if (!helperId) throw new Error('Helper output id is required.');
    if (!helper || core.text(helper.id) !== helperId) {
      const fetched = await core.getJson(`/api/roleplay/v2/breakdown/output?helper_output_id=${encodeURIComponent(helperId)}`);
      helper = fetched.helper_output || null;
    }
    if (!helper) throw new Error('Helper output not found.');
    const data = await core.postForm('/api/roleplay/v2/breakdown/review-save', {
      helper_output_id: helperId,
      cleaned_text: core.text(helper.cleaned_text),
      structured_payload_json: JSON.stringify(helper.structured_payload || {}),
      approved: 'true',
      review_notes: 'Approved from Roleplay V2 surface',
    });
    state.lastHelperOutput = data.helper_output || null;
    core.setStatus('roleplay-v2-breakdown-status', data.message || 'Breakdown approved.', 'success');
    core.setOutput(data);
  }

  async function compileCanon() {
    const helperId = core.text(core.$('roleplay-v2-helper-output-id')?.value);
    if (!helperId) throw new Error('Helper output id is required.');
    const data = await core.postForm('/api/roleplay/v2/canon/compile-from-breakdown', { helper_output_id: helperId });
    state.lastCanonRecord = data.canon_record || null;
    core.$('roleplay-v2-canon-id').value = core.text(data.canon_record?.id);
    const entityIds = Array.isArray(data.canon_record?.linked_entity_ids) ? data.canon_record.linked_entity_ids : [];
    if (entityIds.length && !core.text(core.$('roleplay-v2-entity-id')?.value)) core.$('roleplay-v2-entity-id').value = core.text(entityIds[0]);
    core.setStatus('roleplay-v2-compile-status', data.message || 'Canon compiled.', 'success');
    core.setOutput(data);
  }

  async function compileMemory() {
    const canonId = core.text(core.$('roleplay-v2-canon-id')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    let data;
    if (canonId) {
      data = await core.postForm('/api/roleplay/v2/memory/compile-from-canon', { canon_id: canonId });
    } else if (entityId) {
      data = await core.postForm('/api/roleplay/v2/memory/compile-from-builder', { record_id: entityId });
    } else {
      throw new Error('Canon id or focus entity id is required.');
    }
    core.setStatus('roleplay-v2-compile-status', data.message || 'Memory compiled. Stage 2 complete; runtime may now need rebuild.', 'success');
    await refreshRetrievalStatus();
    if (internalToolsEnabled()) await refreshChromaStatus();
    await refreshRuntimeBundles();
    core.setOutput(data);
  }

  async function compileMemoryForRecord(recordId = '', options = {}) {
    const cleanRecordId = core.text(recordId || core.$('roleplay-v2-entity-id')?.value);
    if (!cleanRecordId) throw new Error('Builder record id is required.');
    if (core.$('roleplay-v2-entity-id')) core.$('roleplay-v2-entity-id').value = cleanRecordId;
    core.setSubtab('studio');
    core.setStudioSubtab('compile');
    const data = await core.postForm('/api/roleplay/v2/memory/compile-from-builder', { record_id: cleanRecordId });
    core.setStatus('roleplay-v2-compile-status', options.statusMessage || data.message || `Builder memory compiled for ${cleanRecordId}.`, 'success');
    await refreshRetrievalStatus();
    if (internalToolsEnabled()) await refreshChromaStatus();
    await refreshRuntimeBundles();
    core.setOutput(data);
    return data;
  }

  async function buildRuntimeForRecord(recordId = '', options = {}) {
    const cleanRecordId = core.text(recordId || core.$('roleplay-v2-entity-id')?.value);
    if (!cleanRecordId) throw new Error('Builder record id is required.');
    if (core.$('roleplay-v2-entity-id')) core.$('roleplay-v2-entity-id').value = cleanRecordId;
    core.setSubtab('studio');
    core.setStudioSubtab('runtime');
    const data = await core.postForm('/api/roleplay/v2/runtime/build', {
      mode: core.currentModeSelection().output_preset,
      interaction_mode: core.currentModeSelection().interaction_mode,
      source_scope: 'builder_record',
      source_id: cleanRecordId,
      project_id: core.text(core.$('roleplay-v2-project-select')?.value),
      entity_id: cleanRecordId,
      query: core.text(core.$('roleplay-v2-query')?.value),
      top_k: numValue('roleplay-v2-runtime-top-k', 8),
      save_bundle: 'true',
    });
    state.lastRuntimeBundle = data.bundle || null;
    await refreshRuntimeBundles();
    if (state.lastRuntimeBundle?.id && core.$('roleplay-v2-scene-runtime-select')) core.$('roleplay-v2-scene-runtime-select').value = core.text(state.lastRuntimeBundle.id);
    if (data.packet?.working_memory?.retrieval_trace) {
      state.lastRetrievalResult = hydrateRetrievalTrace(data.packet.working_memory.retrieval_trace);
      }
    await refreshRetrievalHistory();
    await refreshPipelineStatus();
    core.setStatus('roleplay-v2-runtime-status', options.statusMessage || data.message || `Scene packet built from ${cleanRecordId}. Status: fresh.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function runRetrieval() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const query = core.text(core.$('roleplay-v2-query')?.value);
    const memoryType = core.text(core.$('roleplay-v2-retrieval-memory-type')?.value);
    if (!projectId && !entityId) throw new Error('Select a source project or focus entity first.');
    if (!query) throw new Error('Retrieval query is required.');
    const data = await core.postForm('/api/roleplay/v2/retrieval/query', {
      project_id: projectId,
      entity_id: entityId,
      memory_type: memoryType,
      query,
      top_k: numValue('roleplay-v2-runtime-top-k', 8),
      preview_k: numValue('roleplay-v2-runtime-preview-k', 16),
    });
    state.lastRetrievalResult = data;
    applyModeScopedStudioLayout();
    renderAssistUi();
    renderSharedGenerationSettings();
    renderRetrievalPanels();
    core.setStatus('roleplay-v2-runtime-status', `Retrieved ${data.result_count || 0} memory result(s).`, 'success');
    core.setOutput(data);
  }

  async function refreshRuntimeBundles() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    if (!projectId && !entityId) {
      state.runtimeBundles = [];
      renderRuntimeBundleOptions();
      await refreshPipelineStatus();
      return { runtime_bundles: [], count: 0 };
    }
    const data = await core.getJson(`/api/roleplay/v2/runtime/project?project_id=${encodeURIComponent(projectId)}`);
    state.runtimeBundles = Array.isArray(data.runtime_bundles) ? data.runtime_bundles : [];
    renderRuntimeBundleOptions();
    await refreshRetrievalHistory();
    await refreshPipelineStatus();
    return data;
  }

  function renderRuntimeBundleOptions() {
    const select = core.$('roleplay-v2-scene-runtime-select');
    if (!select) return;
    const current = core.text(select.value);
    select.innerHTML = '<option value="">Select Scene packet</option>';
    state.runtimeBundles.forEach(bundle => {
      const opt = document.createElement('option');
      opt.value = core.text(bundle.id);
      const q = core.text(bundle.query);
      const world = core.text(bundle.active_world_id);
      const freshness = core.text(bundle.freshness_status);
      opt.textContent = `${core.text(bundle.id)}${q ? ` · ${q}` : ''}${world ? ` · ${world}` : ''}${freshness ? ` · ${freshness.replace(/_/g, ' ')}` : ''}`;
      if (opt.value === current) opt.selected = true;
      select.appendChild(opt);
    });
  }

  async function buildRuntime() {
    const projectId = core.text(core.$('roleplay-v2-project-select')?.value);
    const entityId = core.text(core.$('roleplay-v2-entity-id')?.value);
    const query = core.text(core.$('roleplay-v2-query')?.value);
    if (!projectId && !entityId) throw new Error('Select a source project or focus entity first.');
    const sourceScope = projectId ? 'project' : 'builder_record';
    const sourceId = projectId || entityId;
    const data = await core.postForm('/api/roleplay/v2/runtime/build', {
      mode: core.currentModeSelection().output_preset,
      interaction_mode: core.currentModeSelection().interaction_mode,
      source_scope: sourceScope,
      source_id: sourceId,
      project_id: projectId,
      entity_id: entityId || sourceId,
      query,
      top_k: numValue('roleplay-v2-runtime-top-k', 8),
      save_bundle: 'true',
    });
    state.lastRuntimeBundle = data.bundle || null;
    await refreshRuntimeBundles();
    if (state.lastRuntimeBundle?.id && core.$('roleplay-v2-scene-runtime-select')) core.$('roleplay-v2-scene-runtime-select').value = core.text(state.lastRuntimeBundle.id);
    if (data.packet?.working_memory?.retrieval_trace) {
      state.lastRetrievalResult = hydrateRetrievalTrace(data.packet.working_memory.retrieval_trace);
      applyModeScopedStudioLayout();
    renderRetrievalPanels();
    }
    await refreshRetrievalHistory();
    await refreshPipelineStatus();
    core.setStatus('roleplay-v2-runtime-status', data.message || 'Scene packet built. Status: fresh.', 'success');
    core.setOutput(data);
  }

  async function loadRuntimeBundleTrace(bundleId = '') {
    const cleanBundleId = core.text(bundleId || core.$('roleplay-v2-scene-runtime-select')?.value);
    if (!cleanBundleId) throw new Error('Scene packet id is required.');
    const data = await core.getJson(`/api/roleplay/v2/runtime/retrieval-trace?bundle_id=${encodeURIComponent(cleanBundleId)}`);
    state.lastRetrievalResult = hydrateRetrievalTrace(data.trace || {});
    applyModeScopedStudioLayout();
    renderRetrievalPanels();
    await refreshRetrievalHistory();
    core.setStatus('roleplay-v2-runtime-status', `Loaded retrieval trace for ${cleanBundleId}.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function refreshAll() {
    renderSourceMode();
    await refreshProjects();
    await refreshRetrievalStatus();
    applyModeScopedStudioLayout();
    renderAssistUi();
    renderSharedGenerationSettings();
    renderRetrievalPanels();
    if (core.modules.shell?.renderBackendMirror) core.modules.shell.renderBackendMirror();
    if (core.modules.shell?.renderModelCapability) core.modules.shell.renderModelCapability();
    if (core.text(core.$('roleplay-v2-project-select')?.value)) await loadWorkspace(core.text(core.$('roleplay-v2-project-select')?.value));
    await refreshRetrievalHistory();
    await refreshInternalStudioDiagnostics();
    core.setStatus('roleplay-v2-settings-status', 'Roleplay V2 refreshed.', 'success');
  }

  async function boot() {
    document.querySelectorAll('#roleplay-v2-subtabbar [data-roleplay-v2-tab]').forEach(btn => {
      btn.addEventListener('click', () => core.setSubtab(core.text(btn.getAttribute('data-roleplay-v2-tab')) || 'scene'));
    });
    document.querySelectorAll('#roleplay-v2-studio-subtabbar [data-roleplay-v2-studio-tab]').forEach(btn => {
      btn.addEventListener('click', () => { core.setSubtab('studio'); core.setStudioSubtab(core.text(btn.getAttribute('data-roleplay-v2-studio-tab')) || 'workspace'); });
    });
    core.$('roleplay-v2-assist-target')?.addEventListener('change', () => { renderAssistUi(); });
    core.$('roleplay-v2-assist-workflow')?.addEventListener('change', () => { renderAssistUi(); });
    core.$('btn-roleplay-v2-assist-build')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('assist'); await buildAssistDraft(); } catch (err) { core.setStatus('roleplay-v2-assist-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-assist-send')?.addEventListener('click', async () => {
      try { await sendAssistDraft(); } catch (err) { core.setStatus('roleplay-v2-assist-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-assist-clear')?.addEventListener('click', () => { clearAssistDraft(); });
    core.$('btn-roleplay-v2-advanced-save')?.addEventListener('click', () => { saveSharedGenerationSettings(); });
    core.$('btn-roleplay-v2-advanced-reset')?.addEventListener('click', () => { resetSharedGenerationSettings(); });
    core.$('btn-roleplay-v2-refresh')?.addEventListener('click', async () => {
      try { await refreshAll(); } catch (err) { core.setStatus('roleplay-v2-settings-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-settings-save')?.addEventListener('click', async () => {
      try { await saveRetrievalSettings(); } catch (err) { core.setStatus('roleplay-v2-settings-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-reindex')?.addEventListener('click', async () => {
      try { await rebuildIndex(); } catch (err) { core.setStatus('roleplay-v2-settings-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-workspace-load')?.addEventListener('click', async () => {
      try {
        const data = await loadWorkspace(core.text(core.$('roleplay-v2-project-select')?.value));
        core.setStatus('roleplay-v2-project-status', 'Workspace loaded.', 'success');
        core.setOutput(data);
      } catch (err) {
        core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error');
      }
    });
    core.$('btn-roleplay-v2-project-create')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('workspace'); await createProject(); } catch (err) { core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-doc-save')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('source'); await saveDocument(); } catch (err) { core.setStatus('roleplay-v2-doc-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-doc-clear')?.addEventListener('click', () => {
      clearSourceDraftForm();
      core.setStatus('roleplay-v2-doc-status', 'Source draft form cleared.', 'success');
    });
    core.$('roleplay-v2-document-select')?.addEventListener('change', async () => {
      try { await loadSourceDocumentIntoForm(core.text(core.$('roleplay-v2-document-select')?.value)); } catch (err) { core.setStatus('roleplay-v2-doc-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-output-preset')?.addEventListener('change', () => { renderSourceMode(); renderAssistUi(); refreshPipelineStatus().catch(() => {}); core.refreshUserPathGuide?.(); });
    core.$('roleplay-v2-interaction-mode')?.addEventListener('change', () => { renderSourceMode(); renderAssistUi(); refreshPipelineStatus().catch(() => {}); core.refreshUserPathGuide?.(); });
    core.$('btn-roleplay-v2-breakdown')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('compile'); await generateBreakdown(); } catch (err) { core.setStatus('roleplay-v2-breakdown-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-breakdown-approve')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('compile'); await approveBreakdown(); } catch (err) { core.setStatus('roleplay-v2-breakdown-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-canon-compile')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('compile'); await compileCanon(); } catch (err) { core.setStatus('roleplay-v2-compile-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-compile')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('compile'); await compileMemory(); } catch (err) { core.setStatus('roleplay-v2-compile-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-query-run')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('runtime'); await runRetrieval(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-runtime-build')?.addEventListener('click', async () => {
      try { core.setSubtab('studio'); core.setStudioSubtab('runtime'); await buildRuntime(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-recovery-eval')?.addEventListener('click', async () => {
      try { await runRecoveryEval(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-pin')?.addEventListener('click', async () => {
      try { await applyMemoryControl('pin'); } catch (err) { core.setStatus('roleplay-v2-memory-control-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-suppress')?.addEventListener('click', async () => {
      try { await applyMemoryControl('suppress'); } catch (err) { core.setStatus('roleplay-v2-memory-control-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-resolve')?.addEventListener('click', async () => {
      try { await applyMemoryControl('resolve'); } catch (err) { core.setStatus('roleplay-v2-memory-control-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-cooldown')?.addEventListener('click', async () => {
      try { await applyMemoryControl('cooldown', 60); } catch (err) { core.setStatus('roleplay-v2-memory-control-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-memory-clear')?.addEventListener('click', async () => {
      try { await applyMemoryControl('clear'); } catch (err) { core.setStatus('roleplay-v2-memory-control-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-chroma-status')?.addEventListener('click', async () => {
      try { await refreshChromaStatus(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-chroma-sync')?.addEventListener('click', async () => {
      try { await syncChromaMirror(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-chroma-query')?.addEventListener('click', async () => {
      try { await runChromaPreview(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-migration-refresh')?.addEventListener('click', async () => {
      try { await refreshMigrationStatus(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-migration-run')?.addEventListener('click', async () => {
      try { await runPhase14Migration(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-cutover-refresh')?.addEventListener('click', async () => {
      try { await refreshCutoverStatus(); } catch (err) { core.setStatus('roleplay-v2-cutover-note', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-cutover-apply')?.addEventListener('click', async () => {
      try { await applySoftCutover(true); } catch (err) { core.setStatus('roleplay-v2-cutover-note', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-cutover-disable')?.addEventListener('click', async () => {
      try { await applySoftCutover(false); } catch (err) { core.setStatus('roleplay-v2-cutover-note', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-chroma-query')?.addEventListener('keydown', async (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      try { await runChromaPreview(); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-scene-runtime-select')?.addEventListener('change', async (event) => {
      const bundleId = core.text(event.target?.value);
      if (!bundleId) return;
      try { await loadRuntimeBundleTrace(bundleId); } catch (err) { core.setStatus('roleplay-v2-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-entity-id')?.addEventListener('change', () => { refreshPipelineStatus().catch(() => {}); });
    core.$('roleplay-v2-project-select')?.addEventListener('change', async (event) => {
      const projectId = core.text(event.target?.value);
      if (!projectId) return;
      try { await loadWorkspace(projectId); } catch (err) { core.setStatus('roleplay-v2-project-status', err.message || String(err), 'error'); }
    });
    core.modules?.continuityControls?.registerContext?.('studio', {
      listId: 'roleplay-v2-continuity-studio-list',
      inspectorId: 'roleplay-v2-continuity-studio-inspector',
      statusId: 'roleplay-v2-continuity-studio-status',
      countId: 'roleplay-v2-continuity-studio-count',
      refreshButtonId: 'btn-roleplay-v2-continuity-studio-refresh',
      getFilters: studioContinuityFilters,
      getSeedRows: currentStudioContinuitySeedRows,
      onSelect: row => {
        if (row && core.$('roleplay-v2-memory-control-id')) core.$('roleplay-v2-memory-control-id').value = core.text(row.memory_id || row.id);
      },
    });
    applyModeScopedStudioLayout();
    renderAssistUi();
    renderSharedGenerationSettings();
    renderRetrievalPanels();
    renderRetrievalHistory();
    renderRecoveryEval();
    renderChromaStatus();
    renderMigrationStatus();
    renderCutoverStatus();
    await refreshProjects();
    await refreshRetrievalStatus();
    await refreshRetrievalHistory();
    await refreshInternalStudioDiagnostics();
    await refreshPipelineStatus();
  }

  core.refreshRoleplayV2RuntimeBundles = refreshRuntimeBundles;
  core.loadRoleplayV2Workspace = loadWorkspace;
  async function onInternalToolsToggle(enabled) {
    if (!enabled) return;
    renderChromaStatus();
    renderMigrationStatus();
    renderCutoverStatus();
    await refreshInternalStudioDiagnostics();
  }

  core.registerModule('studio', { boot, refreshAll, refreshProjects, refreshRetrievalStatus, refreshRuntimeBundles, refreshRetrievalHistory, refreshChromaStatus, refreshMigrationStatus, refreshCutoverStatus, runPhase14Migration, applySoftCutover, syncChromaMirror, runChromaPreview, loadRetrievalHistoryEntry, loadWorkspace, buildRuntime, compileMemoryForRecord, buildRuntimeForRecord, compileMemory, runRetrieval, loadRuntimeBundleTrace, runRecoveryEval, applyMemoryControl, normalizeStudioSubtab, applyModeScopedStudioLayout, applyAssistSourceDraft, buildAssistDraft, sendAssistDraft, renderAssistUi, getSharedGenerationSettings, sharedAuthorNotesText, saveSharedGenerationSettings, resetSharedGenerationSettings, onInternalToolsToggle });
})();
