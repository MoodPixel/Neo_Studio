(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;

  function setStoriesBusy(isBusy) {
    state.storiesBusy = !!isBusy;
    [
      'btn-roleplay-v2-stories-refresh',
      'btn-roleplay-v2-stories-new',
      'btn-roleplay-v2-stories-create-from-scene',
      'btn-roleplay-v2-stories-submit-storyline',
      'btn-roleplay-v2-stories-fill-from-scene',
      'btn-roleplay-v2-stories-clear-form',
      'btn-roleplay-v2-stories-new-session',
      'btn-roleplay-v2-stories-submit-session',
      'btn-roleplay-v2-stories-clear-session-form',
      'btn-roleplay-v2-stories-open-reader',
      'btn-roleplay-v2-stories-resume-scene',
    ].forEach(id => {
      const el = core.$(id);
      if (el) el.disabled = !!isBusy;
    });
  }

  function text(value) {
    return core.text(value);
  }

  function byId(items, id) {
    const cleanId = text(id);
    return (Array.isArray(items) ? items : []).find(item => text(item?.id) === cleanId) || null;
  }

  function setInspectorView(viewName = 'summary') {
    const clean = text(viewName) || 'summary';
    state.storyInspectorView = clean;
    document.querySelectorAll('#roleplay-v2-stories-inspector-viewbar [data-roleplay-v2-stories-view]').forEach(btn => {
      btn.classList.toggle('active', text(btn.getAttribute('data-roleplay-v2-stories-view')) === clean);
    });
    document.querySelectorAll('[data-roleplay-v2-stories-panel]').forEach(panel => {
      panel.classList.toggle('hidden', text(panel.getAttribute('data-roleplay-v2-stories-panel')) !== clean);
    });
  }

  function setStoriesSubtab(viewName = 'workspace') {
    const clean = text(viewName) || 'workspace';
    state.storySubtab = clean;
    document.querySelectorAll('#roleplay-v2-stories-subtabbar [data-roleplay-v2-stories-subtab]').forEach(btn => {
      btn.classList.toggle('active', text(btn.getAttribute('data-roleplay-v2-stories-subtab')) === clean);
    });
    document.querySelectorAll('[data-roleplay-v2-stories-subtab-panel]').forEach(panel => {
      panel.classList.toggle('hidden', text(panel.getAttribute('data-roleplay-v2-stories-subtab-panel')) !== clean);
    });
  }

  function setArchiveView(viewName = 'stories') {
    const clean = text(viewName) || 'stories';
    state.storyArchiveView = clean;
    document.querySelectorAll('#roleplay-v2-stories-archive-viewbar [data-roleplay-v2-stories-archive-view]').forEach(btn => {
      btn.classList.toggle('active', text(btn.getAttribute('data-roleplay-v2-stories-archive-view')) === clean);
    });
    document.querySelectorAll('[data-roleplay-v2-stories-archive-panel]').forEach(panel => {
      panel.classList.toggle('hidden', text(panel.getAttribute('data-roleplay-v2-stories-archive-panel')) !== clean);
    });
  }

  function setContinuityView(viewName = 'rows') {
    const clean = text(viewName) || 'rows';
    state.storyContinuityView = clean;
    document.querySelectorAll('#roleplay-v2-stories-continuity-viewbar [data-roleplay-v2-stories-continuity-view]').forEach(btn => {
      btn.classList.toggle('active', text(btn.getAttribute('data-roleplay-v2-stories-continuity-view')) === clean);
    });
    document.querySelectorAll('[data-roleplay-v2-stories-continuity-panel]').forEach(panel => {
      panel.classList.toggle('hidden', text(panel.getAttribute('data-roleplay-v2-stories-continuity-panel')) !== clean);
    });
  }

  function setStoriesStatus(message, tone = '') {
    core.setStatus('roleplay-v2-stories-status', message, tone);
  }

  function syncSceneBinding() {
    core.modules.scene?.renderStoryBinding?.();
  }

  function shortIso(value) {
    const clean = text(value);
    return clean ? clean.replace('T', ' ').slice(0, 16) : '';
  }

  function inferSceneStorylineTitle() {
    const premise = text(core.$('roleplay-v2-scene-premise')?.value);
    if (premise) return premise.split(/[.!?\n]/)[0].slice(0, 120);
    const focus = text(state.activeRuntimeBundle?.packet?.entity_focus?.label) || text(state.activeRuntimeBundle?.packet?.entity_focus?.id);
    if (focus) return `${focus} storyline`.slice(0, 120);
    const bundleId = text(state.activeRuntimeBundle?.id);
    if (bundleId) return `Runtime ${bundleId} storyline`.slice(0, 120);
    return 'Scene storyline';
  }

  function modeLabelForPair(outputPreset = '', interactionMode = '') {
    return core.normalizeModeSelection({ outputPreset, interactionMode, prefer: 'output' }).goal_label;
  }

  function fillStorylineDraftFromScene({ preserveTitle = false } = {}) {
    const titleEl = core.$('roleplay-v2-stories-form-title');
    const summaryEl = core.$('roleplay-v2-stories-form-summary');
    const projectEl = core.$('roleplay-v2-stories-form-project-id');
    const continuityEl = core.$('roleplay-v2-stories-form-continuity-policy');
    const sceneState = state.sceneState || state.sceneContinuity?.scene_state || state.activeRuntimeBundle?.packet?.scene_state_seed || {};
    if (titleEl && (!preserveTitle || !text(titleEl.value))) titleEl.value = inferSceneStorylineTitle();
    if (summaryEl && !text(summaryEl.value)) {
      summaryEl.value = text(core.$('roleplay-v2-scene-premise')?.value) || text(state.sceneContinuity?.continuity_note) || '';
    }
    if (projectEl && !text(projectEl.value)) {
      projectEl.value = text(state.activeRuntimeBundle?.project_id) || text(state.activeRuntimeBundle?.packet?.project_id) || text(state.selectedStoryline?.project_id);
    }
    if (continuityEl) continuityEl.value = text(sceneState.continuity_mode) || text(continuityEl.value) || 'runtime_anchored';
    refreshStoriesMetaPanels();
  }

  function clearStorylineForm() {
    if (core.$('roleplay-v2-stories-form-title')) core.$('roleplay-v2-stories-form-title').value = '';
    if (core.$('roleplay-v2-stories-form-summary')) core.$('roleplay-v2-stories-form-summary').value = '';
    if (core.$('roleplay-v2-stories-form-project-id')) core.$('roleplay-v2-stories-form-project-id').value = text(state.selectedStoryline?.project_id);
    if (core.$('roleplay-v2-stories-form-continuity-policy')) core.$('roleplay-v2-stories-form-continuity-policy').value = text(state.selectedStoryline?.continuity_policy) || 'runtime_anchored';
    refreshStoriesMetaPanels();
  }

  function clearSessionForm() {
    if (core.$('roleplay-v2-stories-session-summary')) core.$('roleplay-v2-stories-session-summary').value = '';
    if (core.$('roleplay-v2-stories-session-seed-checkpoint')) core.$('roleplay-v2-stories-session-seed-checkpoint').checked = !!text(state.selectedCheckpointId);
    refreshStoriesMetaPanels();
  }

  function storylineFormPayload({ preferScene = false } = {}) {
    const continuityPolicy = text(core.$('roleplay-v2-stories-form-continuity-policy')?.value) || text(state.selectedStoryline?.continuity_policy) || 'runtime_anchored';
    const sceneState = state.sceneState || state.sceneContinuity?.scene_state || state.activeRuntimeBundle?.packet?.scene_state_seed || {};
    return {
      title: text(core.$('roleplay-v2-stories-form-title')?.value) || (preferScene ? inferSceneStorylineTitle() : ''),
      summary: text(core.$('roleplay-v2-stories-form-summary')?.value) || (preferScene ? text(core.$('roleplay-v2-scene-premise')?.value) : ''),
      project_id: text(core.$('roleplay-v2-stories-form-project-id')?.value) || text(state.selectedStoryline?.project_id) || text(state.activeRuntimeBundle?.project_id) || text(state.activeRuntimeBundle?.packet?.project_id),
      linked_world_id: text(sceneState.active_world_id),
      linked_universe_id: '',
      linked_scenario_ids_json: JSON.stringify(Array.isArray(sceneState.active_scenario_id) ? sceneState.active_scenario_id : [text(sceneState.active_scenario_id)].filter(Boolean)),
      linked_entity_ids_json: JSON.stringify(Array.isArray(sceneState.cast_entity_ids) ? sceneState.cast_entity_ids : []),
      continuity_policy: continuityPolicy,
    };
  }

  function sessionCreatePayload() {
    const mode = core.currentModeSelection();
    const seedCheckpoint = !!core.$('roleplay-v2-stories-session-seed-checkpoint')?.checked;
    const resumeSceneState = state.storyResumePreview?.resume?.scene_state || {};
    const checkpointState = state.selectedCheckpoint?.scene_state || {};
    const sessionSeed = Object.assign({}, resumeSceneState, checkpointState, {
      output_preset: mode.output_preset,
      interaction_mode: mode.interaction_mode,
      continuity_mode: text(state.selectedCheckpoint?.continuity_payload?.continuity_mode) || text(state.selectedStoryline?.continuity_policy) || text(state.sceneState?.continuity_mode) || 'runtime_anchored',
    });
    return {
      storyline_id: text(state.selectedStorylineId),
      project_id: text(state.selectedStoryline?.project_id),
      continuity_mode: text(state.selectedStoryline?.continuity_policy) || text(sessionSeed.continuity_mode) || 'runtime_anchored',
      seed_checkpoint_id: seedCheckpoint ? text(state.selectedCheckpointId) : '',
      seed_runtime_bundle_id: text(state.selectedCheckpoint?.runtime_bundle_id) || text(state.selectedSession?.latest_runtime_bundle_id) || text(state.selectedSession?.seed_runtime_bundle_id) || text(state.storyResumePreview?.resume?.runtime_bundle_id),
      output_preset: mode.output_preset,
      interaction_mode: mode.interaction_mode,
      scene_state_seed_json: JSON.stringify(sessionSeed),
      session_summary: text(core.$('roleplay-v2-stories-session-summary')?.value) || text(state.selectedCheckpoint?.summary) || text(state.selectedCheckpoint?.title),
    };
  }

  function refreshStoriesMetaPanels() {
    const structureNote = core.$('roleplay-v2-stories-structure-note');
    const modeNote = core.$('roleplay-v2-stories-mode-lock-note');
    const restoreNote = core.$('roleplay-v2-stories-restore-note');
    const sessionModeNote = core.$('roleplay-v2-stories-session-mode-note');
    const resumeTarget = core.$('roleplay-v2-stories-resume-target');
    const resumeMode = core.$('roleplay-v2-stories-resume-mode');
    const mode = core.currentModeSelection();
    const resume = state.storyResumePreview?.resume || {};
    const restoreCheckpointTitle = text(state.selectedCheckpoint?.title || state.selectedCheckpoint?.id || resume.checkpoint_id);
    const restoreSessionId = text(state.selectedSession?.id || resume.session_id);
    const restoreStorylineTitle = text(state.selectedStoryline?.title || resume.storyline_id);
    const restoreRuntime = text(resume.runtime_bundle_id || state.selectedCheckpoint?.runtime_bundle_id || state.selectedSession?.latest_runtime_bundle_id || state.selectedSession?.seed_runtime_bundle_id);
    const selectedSeedNote = text(state.selectedCheckpointId) && !!core.$('roleplay-v2-stories-session-seed-checkpoint')?.checked
      ? `New session will seed from checkpoint ${text(state.selectedCheckpoint?.title || state.selectedCheckpointId)}.`
      : 'New session will start fresh inside the selected storyline unless a checkpoint seed is enabled.';
    if (structureNote) structureNote.textContent = `Storyline = umbrella. Session = one active run. Checkpoint = a restorable save inside that session. Current selection: ${restoreStorylineTitle || 'no storyline'} → ${restoreSessionId || 'no session'} → ${restoreCheckpointTitle || 'no checkpoint'}.`;
    if (modeNote) modeNote.textContent = `New sessions inherit the current canonical mode lock: ${mode.goal_label} → output_preset=${mode.output_preset} · interaction_mode=${mode.interaction_mode}.`;
    if (restoreNote) restoreNote.textContent = restoreRuntime
      ? `Restore preview is ready. Scene will reopen runtime ${restoreRuntime} and reapply the saved mode lock before continuing.`
      : 'Restore preview will show the exact runtime and mode lock once a session or checkpoint is selected.';
    if (sessionModeNote) sessionModeNote.textContent = `${selectedSeedNote} Current mode lock preview: ${mode.goal_label}.`;
    if (resumeTarget) resumeTarget.textContent = restoreStorylineTitle || restoreSessionId || restoreCheckpointTitle
      ? `Restore target · storyline ${restoreStorylineTitle || 'none'} · session ${restoreSessionId || 'none'} · checkpoint ${restoreCheckpointTitle || 'session active checkpoint'}.`
      : 'Restore target preview will appear here once a storyline, session, or checkpoint is selected.';
    if (resumeMode) {
      const restoreOutput = text(resume.output_preset || state.selectedSession?.output_preset || mode.output_preset) || 'roleplay';
      const restoreInteraction = text(resume.interaction_mode || state.selectedSession?.interaction_mode || mode.interaction_mode) || 'roleplay';
      const label = modeLabelForPair(restoreOutput, restoreInteraction);
      const warnings = Array.isArray(resume.mode_lock_warnings) ? resume.mode_lock_warnings.filter(Boolean) : [];
      resumeMode.textContent = `${label} restore · output_preset=${restoreOutput} · interaction_mode=${restoreInteraction}${warnings.length ? ` · warnings: ${warnings.join(' | ')}` : ''}`;
    }
  }


  function renderActionState() {
    const hasStoryline = !!text(state.selectedStorylineId);
    const hasSession = !!text(state.selectedSessionId);
    const hasCheckpoint = !!text(state.selectedCheckpointId);
    const busy = !!state.storiesBusy;
    const newSessionBtn = core.$('btn-roleplay-v2-stories-new-session');
    const submitSessionBtn = core.$('btn-roleplay-v2-stories-submit-session');
    const openReaderBtn = core.$('btn-roleplay-v2-stories-open-reader');
    const resumeBtn = core.$('btn-roleplay-v2-stories-resume-scene');
    const refreshBtn = core.$('btn-roleplay-v2-stories-refresh');
    const newBtn = core.$('btn-roleplay-v2-stories-new');
    const submitStorylineBtn = core.$('btn-roleplay-v2-stories-submit-storyline');
    const createFromSceneBtn = core.$('btn-roleplay-v2-stories-create-from-scene');
    if (newSessionBtn) newSessionBtn.disabled = busy || !hasStoryline;
    if (submitSessionBtn) submitSessionBtn.disabled = busy || !hasStoryline;
    if (openReaderBtn) openReaderBtn.disabled = busy || !hasCheckpoint;
    if (resumeBtn) resumeBtn.disabled = busy || !(hasStoryline || hasSession || hasCheckpoint);
    if (refreshBtn) refreshBtn.disabled = busy;
    if (newBtn) newBtn.disabled = busy;
    if (submitStorylineBtn) submitStorylineBtn.disabled = busy;
    if (createFromSceneBtn) createFromSceneBtn.disabled = busy;
  }

  function storylineList() {
    return Array.isArray(state.storylines) ? state.storylines : [];
  }

  function sessionsForSelectedStoryline() {
    return Array.isArray(state.storySessions) ? state.storySessions : [];
  }

  function checkpointsForSelectedSession() {
    const checkpoints = Array.isArray(state.storyCheckpoints) ? state.storyCheckpoints : [];
    const selectedSessionId = text(state.selectedSessionId);
    if (!selectedSessionId) return checkpoints;
    return checkpoints.filter(row => text(row?.session_id) === selectedSessionId);
  }


  function continuitySnapshotCounts(snapshot) {
    const clean = snapshot || {};
    return {
      turnSummaries: Number((clean.turn_summaries || []).length || 0),
      relationshipState: Number((clean.relationship_state || []).length || 0),
      unresolvedThreads: Number((clean.unresolved_threads || []).length || 0),
      callbackAnchors: Number((clean.callback_anchors || []).length || 0),
      postTurnRows: Number((clean.post_turn_rows || []).length || 0),
      sourceRefs: Number((clean.source_refs || []).length || 0),
    };
  }

  function canPublishSharedScope(scopeName = '') {
    const storyline = state.selectedStoryline || {};
    const checkpoint = state.selectedCheckpoint || {};
    const cleanScope = text(scopeName);
    if (!text(storyline.id) || !text(checkpoint.id)) return false;
    if (cleanScope === 'shared_world') return !!text(storyline.linked_world_id);
    if (cleanScope === 'shared_universe') return !!text(storyline.linked_universe_id);
    return false;
  }

  function selectedCheckpointPublication(scopeName = '') {
    const publications = state.selectedCheckpoint?.extra?.shared_continuity_publications || {};
    return publications[text(scopeName)] || null;
  }

  async function publishSelectedCheckpointShared(scopeName = 'shared_world') {
    const storylineId = text(state.selectedStorylineId);
    const sessionId = text(state.selectedSessionId);
    const checkpointId = text(state.selectedCheckpointId);
    const cleanScope = text(scopeName) || 'shared_world';
    if (!storylineId || !sessionId || !checkpointId) {
      setStoriesStatus('Select a storyline, session, and checkpoint before publishing shared continuity.', 'warning');
      return null;
    }
    if (!canPublishSharedScope(cleanScope)) {
      setStoriesStatus(`This storyline is not linked to a ${cleanScope.replace('shared_', '')} scope yet.`, 'warning');
      return null;
    }
    setStoriesBusy(true);
    try {
      const data = await core.postForm('/api/roleplay/v2/story-checkpoint/publish-shared', {
        storyline_id: storylineId,
        session_id: sessionId,
        checkpoint_id: checkpointId,
        publish_scope: cleanScope,
      });
      state.selectedStoryline = data.storyline || state.selectedStoryline || null;
      state.storySessions = Array.isArray(data.sessions) ? data.sessions : state.storySessions;
      state.storyCheckpoints = Array.isArray(data.checkpoints) ? data.checkpoints : state.storyCheckpoints;
      state.selectedSession = byId(state.storySessions, sessionId) || state.selectedSession || null;
      state.selectedSessionId = text(state.selectedSession?.id || sessionId);
      const scopedCheckpoints = checkpointsForSelectedSession();
      state.selectedCheckpoint = byId(scopedCheckpoints, checkpointId) || byId(state.storyCheckpoints, checkpointId) || state.selectedCheckpoint || null;
      state.selectedCheckpointId = text(state.selectedCheckpoint?.id || checkpointId);
      await refreshResumePreview().catch(() => { state.storyResumePreview = null; });
      renderWorkspace();
      renderInspector();
      syncSceneBinding();
      core.setOutput(data);
      setStoriesStatus(data.message || 'Published shared continuity.', 'success');
      return data;
    } finally {
      setStoriesBusy(false);
    }
  }

  function storiesContinuityFilters() {
    const checkpoint = state.selectedCheckpoint || {};
    const session = state.selectedSession || {};
    const resume = state.storyResumePreview?.resume || {};
    const sceneState = resume.scene_state || {};
    const checkpointEntities = Array.isArray(checkpoint.selected_entity_ids) ? checkpoint.selected_entity_ids : [];
    const resumeEntities = Array.isArray(sceneState.cast_entity_ids) ? sceneState.cast_entity_ids : [];
    return {
      project_id: text(state.selectedStoryline?.project_id),
      bundle_id: text(checkpoint.runtime_bundle_id || session.latest_runtime_bundle_id || session.seed_runtime_bundle_id || resume.runtime_bundle_id),
      entity_id: text(checkpointEntities[0] || resumeEntities[0] || sceneState.active_entity_id),
      source_ref: text((resume.continuity_payload || {}).writeback_source_ref || (resume.continuity_payload || {}).source_ref),
      origin: 'auto',
    };
  }

  async function refreshResumePreview() {
    const storylineId = text(state.selectedStorylineId);
    const sessionId = text(state.selectedSessionId);
    const checkpointId = text(state.selectedCheckpointId);
    if (!(storylineId || sessionId || checkpointId)) {
      state.storyResumePreview = null;
      return null;
    }
    const params = new URLSearchParams();
    if (storylineId) params.set('storyline_id', storylineId);
    if (sessionId) params.set('session_id', sessionId);
    if (checkpointId) params.set('checkpoint_id', checkpointId);
    const data = await core.getJson(`/api/roleplay/v2/story-resume?${params.toString()}`);
    state.storyResumePreview = data || null;
    return data;
  }

  function selectSession(sessionId = '') {
    const sessions = sessionsForSelectedStoryline();
    const cleanId = text(sessionId);
    const nextSession = byId(sessions, cleanId) || sessions[0] || null;
    state.selectedSession = nextSession;
    state.selectedSessionId = text(nextSession?.id);

    const checkpoints = checkpointsForSelectedSession();
    const activeCheckpointId = text(nextSession?.active_checkpoint_id);
    const selectedCheckpoint = byId(checkpoints, state.selectedCheckpointId) || byId(checkpoints, activeCheckpointId) || checkpoints[0] || null;
    state.selectedCheckpoint = selectedCheckpoint;
    state.selectedCheckpointId = text(selectedCheckpoint?.id);
    core.modules?.continuityControls?.refreshContext?.('stories', { silent: true }).catch(() => null);
  }

  function buildSummaryText() {
    const storyline = state.selectedStoryline || {};
    const session = state.selectedSession || {};
    const checkpoint = state.selectedCheckpoint || {};
    const checkpointSnapshot = checkpoint.extra?.continuity_snapshot || {};
    const sessionSnapshot = session.extra?.continuity_snapshot || {};
    const resume = state.storyResumePreview?.resume || {};
    const resumeSnapshot = resume.continuity_snapshot || {};
    const checkpointCounts = continuitySnapshotCounts(checkpointSnapshot);
    const sessionCounts = continuitySnapshotCounts(sessionSnapshot);
    const resumeCounts = continuitySnapshotCounts(resumeSnapshot);
    const lines = [
      'Save hierarchy · Storyline → Session → Checkpoint',
      `Storyline · ${text(storyline.title) || 'none'}`,
      `Session · ${text(session.id) || 'none'}`,
      `Checkpoint · ${text(checkpoint.title || checkpoint.id) || 'session active checkpoint'}`,
      `Resume goal · ${modeLabelForPair(text(resume.output_preset || session.output_preset), text(resume.interaction_mode || session.interaction_mode))}`,
      `Resume runtime bundle · ${text(resume.runtime_bundle_id || checkpoint.runtime_bundle_id || session.latest_runtime_bundle_id || session.seed_runtime_bundle_id) || 'none'}`,
      '',
      `Status · ${text(storyline.meta?.status || storyline.status) || 'draft'}`,
      `Project · ${text(storyline.project_id) || 'none'}`,
      `Continuity policy · ${text(storyline.continuity_policy) || 'runtime_anchored'}`,
      `Linked world · ${text(storyline.linked_world_id) || 'none'}`,
      `Linked universe · ${text(storyline.linked_universe_id) || 'none'}`,
      `Shared continuity world total · ${Number(storyline.extra?.shared_continuity_summary?.published_counts?.shared_world || 0)}`,
      `Shared continuity universe total · ${Number(storyline.extra?.shared_continuity_summary?.published_counts?.shared_universe || 0)}`,
      `Linked scenarios · ${(storyline.linked_scenario_ids || []).length}`,
      `Linked entities · ${(storyline.linked_entity_ids || []).length}`,
      '',
      `Selected session · ${text(session.id) || 'none'}`,
      `Session mode · ${text(session.session_mode) || 'n/a'}`,
      `Checkpoint count · ${Number((session.checkpoint_ids || []).length || 0)}`,
      `Active checkpoint · ${text(session.active_checkpoint_id) || 'none'}`,
      `Output preset · ${text(session.output_preset) || 'roleplay'}`,
      `Interaction mode · ${text(session.interaction_mode) || 'roleplay'}`,
      `Session continuity snapshot · turn ${sessionCounts.turnSummaries} · relationship ${sessionCounts.relationshipState} · unresolved ${sessionCounts.unresolvedThreads}`,
      '',
      `Selected checkpoint · ${text(checkpoint.title) || 'none'}`,
      `Checkpoint type · ${text(checkpoint.checkpoint_type) || 'n/a'}`,
      `Branch label · ${text(checkpoint.branch_label) || 'none'}`,
      `Runtime bundle · ${text(checkpoint.runtime_bundle_id) || 'none'}`,
      `Checkpoint continuity snapshot · turn ${checkpointCounts.turnSummaries} · relationship ${checkpointCounts.relationshipState} · unresolved ${checkpointCounts.unresolvedThreads}`,
      `Checkpoint shared world publish · ${Number(selectedCheckpointPublication('shared_world')?.published_counts?.total || 0)} items`,
      `Checkpoint shared universe publish · ${Number(selectedCheckpointPublication('shared_universe')?.published_counts?.total || 0)} items`,
      `Resume preview snapshot · turn ${resumeCounts.turnSummaries} · relationship ${resumeCounts.relationshipState} · unresolved ${resumeCounts.unresolvedThreads}`,
      '',
      storyline.summary ? `Storyline summary\n${text(storyline.summary)}` : 'No storyline summary yet.',
      checkpoint.summary ? `\nCheckpoint summary\n${text(checkpoint.summary)}` : '',
    ];
    return lines.filter(Boolean).join('\n');
  }

  function quietReaderChunk(value = '') {
    return text(value).replace(/^(user|assistant|system|narrator|scene)\s*:\s*/i, '').trim();
  }

  function buildReaderText() {
    const checkpoint = state.selectedCheckpoint || {};
    const sceneText = quietReaderChunk(checkpoint.scene_text);
    if (sceneText) return sceneText;
    const transcript = Array.isArray(checkpoint.transcript) ? checkpoint.transcript : [];
    if (transcript.length) {
      return transcript
        .map(item => quietReaderChunk(item.content))
        .filter(Boolean)
        .join('\n\n');
    }
    return 'Select a checkpoint to preview readable story text here.';
  }


  function assetUrl(assetPath = '') {
    const clean = text(assetPath);
    return clean ? `/api/roleplay/asset/file?asset_path=${encodeURIComponent(clean)}` : '';
  }

  function archiveInitial(label = '') {
    const clean = text(label);
    return clean ? clean.charAt(0).toUpperCase() : '?';
  }

  function buildCheckpointReadable(checkpoint = {}) {
    const sceneText = quietReaderChunk(checkpoint.scene_text);
    if (sceneText) return sceneText;
    const transcript = Array.isArray(checkpoint.transcript) ? checkpoint.transcript : [];
    if (transcript.length) {
      return transcript.map(item => quietReaderChunk(item.content)).filter(Boolean).join('\n\n');
    }
    return text(checkpoint.summary) || 'No readable text saved for this checkpoint yet.';
  }

  function archiveCoverPath(cover) {
    if (!cover || typeof cover !== 'object') return '';
    return text(cover.thumb_path || cover.image_path || cover.asset_path);
  }

  function buildArchiveStoryCards() {
    const selectedId = text(state.selectedStoryline?.id || state.selectedStorylineId);
    return storylineList().map(item => {
      const live = text(item.id) === selectedId ? (state.selectedStoryline || {}) : {};
      return {
        id: text(item.id),
        title: text(item.title) || 'Untitled storyline',
        summary: text(item.summary) || 'No storyline summary yet.',
        cover: (live.cover && typeof live.cover === 'object' && Object.keys(live.cover).length) ? live.cover : item.cover,
        chips: [
          text(item.status) || 'draft',
          item.session_count != null ? `${Number(item.session_count || 0)} session${Number(item.session_count || 0) === 1 ? '' : 's'}` : '',
          item.checkpoint_count != null ? `${Number(item.checkpoint_count || 0)} checkpoint${Number(item.checkpoint_count || 0) === 1 ? '' : 's'}` : '',
          text(item.project_id) ? `Project ${text(item.project_id)}` : '',
        ].filter(Boolean),
        open: () => openStoryArchiveCard(text(item.id)).catch(err => setStoriesStatus(err.message || String(err), 'error')),
      };
    });
  }

  function buildArchiveRoleplayCards() {
    const storyline = state.selectedStoryline || {};
    return sessionsForSelectedStoryline().map(session => ({
      id: text(session.id),
      title: text(session.session_summary) || text(session.id) || 'Roleplay session',
      summary: [
        modeLabelForPair(text(session.output_preset), text(session.interaction_mode)),
        text(session.session_mode) || 'live_scene',
        text(session.active_checkpoint_id) ? `Active checkpoint ${text(session.active_checkpoint_id)}` : '',
      ].filter(Boolean).join(' · '),
      cover: storyline.cover,
      chips: [
        text(storyline.title) || '',
        `${Number((session.checkpoint_ids || []).length || session.checkpoint_count || 0)} checkpoint${Number((session.checkpoint_ids || []).length || session.checkpoint_count || 0) === 1 ? '' : 's'}`,
        text(session.last_turn_at || session.updated_at) ? `Updated ${shortIso(session.last_turn_at || session.updated_at)}` : '',
      ].filter(Boolean),
      open: () => openRoleplayArchiveCard(text(session.id)),
    }));
  }

  function flattenCanonArchiveCards() {
    const groups = (state.storyCanonArchive && state.storyCanonArchive.groups && typeof state.storyCanonArchive.groups === 'object') ? state.storyCanonArchive.groups : {};
    const cards = [];
    Object.entries(groups).forEach(([kind, records]) => {
      (Array.isArray(records) ? records : []).forEach(record => {
        cards.push({
          id: text(record.id),
          title: text(record.display_label || record.label) || 'Untitled record',
          summary: text(record.summary) || 'Runtime-ready Forge record.',
          kind: text(record.kind || kind),
          chips: [
            text(record.kind || kind),
            text(record.status) || 'runtime_ready',
            text(record.scope_values?.current_world_id || record.scope_values?.current_universe_id) ? 'Scoped' : '',
          ].filter(Boolean),
          open: () => openCanonArchiveCard(text(record.id)).catch(err => setStoriesStatus(err.message || String(err), 'error')),
        });
      });
    });
    cards.sort((a, b) => a.title.localeCompare(b.title));
    return cards;
  }

  function renderArchiveMeta(targetId, chips) {
    const root = core.$(targetId);
    if (!root) return;
    root.innerHTML = '';
    (Array.isArray(chips) ? chips : []).filter(Boolean).forEach(value => {
      const chip = document.createElement('span');
      chip.className = 'roleplay-v2-archive-chip';
      chip.textContent = value;
      root.appendChild(chip);
    });
  }

  function renderArchiveCards(rootId, cards, emptyMessage) {
    const root = core.$(rootId);
    if (!root) return;
    root.innerHTML = '';
    if (!Array.isArray(cards) || !cards.length) {
      const empty = document.createElement('div');
      empty.className = 'roleplay-v2-archive-empty';
      empty.textContent = emptyMessage;
      root.appendChild(empty);
      return;
    }
    cards.forEach(card => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'roleplay-v2-archive-card';
      const cover = document.createElement('div');
      cover.className = 'roleplay-v2-archive-cover';
      const coverPath = archiveCoverPath(card.cover);
      if (coverPath) {
        const img = document.createElement('img');
        img.src = assetUrl(coverPath);
        img.alt = text(card.title) || 'Archive cover';
        cover.appendChild(img);
      } else {
        cover.textContent = archiveInitial(card.title);
      }
      const title = document.createElement('div');
      title.className = 'roleplay-v2-archive-card-title';
      title.textContent = text(card.title) || 'Untitled';
      const summary = document.createElement('div');
      summary.className = 'roleplay-v2-archive-card-summary';
      const copy = text(card.summary) || 'No summary yet.';
      summary.textContent = copy.length > 180 ? `${copy.slice(0, 177)}...` : copy;
      const meta = document.createElement('div');
      meta.className = 'roleplay-v2-archive-card-meta';
      (Array.isArray(card.chips) ? card.chips : []).filter(Boolean).slice(0, 4).forEach(value => {
        const chip = document.createElement('span');
        chip.className = 'roleplay-v2-archive-chip';
        chip.textContent = value;
        meta.appendChild(chip);
      });
      btn.appendChild(cover);
      btn.appendChild(title);
      btn.appendChild(summary);
      if (meta.childElementCount) btn.appendChild(meta);
      btn.addEventListener('click', () => {
        if (typeof card.open === 'function') card.open();
      });
      root.appendChild(btn);
    });
  }

  function closeArchiveModal() {
    state.storyArchiveModal = null;
    const modal = core.$('roleplay-v2-stories-archive-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  function setArchiveModalCover(cover, title = '') {
    const root = core.$('roleplay-v2-stories-archive-modal-cover');
    if (!root) return;
    root.innerHTML = '';
    const coverPath = archiveCoverPath(cover);
    if (coverPath) {
      const img = document.createElement('img');
      img.src = assetUrl(coverPath);
      img.alt = text(cover?.alt_text) || text(title) || 'Archive cover';
      root.appendChild(img);
    } else {
      root.textContent = archiveInitial(title);
    }
  }

  function renderArchiveModalPart(index = 0) {
    const modalState = state.storyArchiveModal || {};
    const parts = Array.isArray(modalState.parts) ? modalState.parts : [];
    const nextIndex = Math.max(0, Math.min(Number(index || 0), Math.max(parts.length - 1, 0)));
    modalState.activePartIndex = nextIndex;
    state.storyArchiveModal = modalState;
    const partBar = core.$('roleplay-v2-stories-archive-modal-parts');
    const partMeta = core.$('roleplay-v2-stories-archive-modal-part-meta');
    const body = core.$('roleplay-v2-stories-archive-modal-body');
    if (partBar) {
      partBar.innerHTML = '';
      parts.forEach((part, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.classList.toggle('active', idx === nextIndex);
        btn.textContent = text(part.label) || `Part ${idx + 1}`;
        btn.addEventListener('click', () => renderArchiveModalPart(idx));
        partBar.appendChild(btn);
      });
    }
    const active = parts[nextIndex] || {};
    if (partMeta) partMeta.textContent = text(active.meta) || '';
    if (body) body.textContent = text(active.body) || 'No readable content saved for this item yet.';
  }

  function openArchiveModal(payload = {}) {
    const modal = core.$('roleplay-v2-stories-archive-modal');
    const eyebrow = core.$('roleplay-v2-stories-archive-modal-eyebrow');
    const title = core.$('roleplay-v2-stories-archive-modal-title');
    const summary = core.$('roleplay-v2-stories-archive-modal-summary');
    const meta = core.$('roleplay-v2-stories-archive-modal-meta');
    const uploadBtn = core.$('btn-roleplay-v2-stories-archive-upload-cover');
    state.storyArchiveModal = {
      mode: text(payload.mode),
      recordId: text(payload.recordId),
      cover: payload.cover && typeof payload.cover === 'object' ? payload.cover : {},
      title: text(payload.title),
      summary: text(payload.summary),
      parts: Array.isArray(payload.parts) && payload.parts.length ? payload.parts : [{ label: 'Overview', body: text(payload.summary) || 'No readable content saved for this item yet.', meta: '' }],
      metaLines: Array.isArray(payload.metaLines) ? payload.metaLines.filter(Boolean) : [],
      uploadEnabled: !!payload.uploadEnabled,
      activePartIndex: 0,
    };
    if (eyebrow) eyebrow.textContent = text(payload.eyebrow) || 'Archive viewer';
    if (title) title.textContent = text(payload.title) || 'Archive item';
    if (summary) summary.textContent = text(payload.summary) || 'No summary available for this archive item yet.';
    if (meta) {
      meta.innerHTML = '';
      (Array.isArray(payload.metaLines) ? payload.metaLines : []).filter(Boolean).forEach(line => {
        const chip = document.createElement('span');
        chip.className = 'roleplay-v2-archive-chip';
        chip.textContent = line;
        meta.appendChild(chip);
      });
    }
    if (uploadBtn) uploadBtn.classList.toggle('hidden', !payload.uploadEnabled);
    setArchiveModalCover(payload.cover, payload.title);
    renderArchiveModalPart(0);
    if (modal) {
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
    }
  }

  async function handleArchiveCoverUpload(file) {
    const modalState = state.storyArchiveModal || {};
    if (!modalState.uploadEnabled || modalState.mode !== 'storyline') throw new Error('Cover upload is only available for storyline archive cards right now.');
    const recordId = text(modalState.recordId);
    if (!recordId) throw new Error('Storyline id is missing for this archive item.');
    const form = new FormData();
    form.append('storyline_id', recordId);
    form.append('file', file);
    const res = await fetch('/api/roleplay/v2/storyline/cover-upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Cover upload failed.');
    state.storylines = Array.isArray(data.storylines) ? data.storylines : state.storylines;
    if (text(state.selectedStorylineId) === recordId) state.selectedStoryline = data.storyline || state.selectedStoryline || null;
    if (state.storyArchiveModal && text(state.storyArchiveModal.recordId) === recordId) {
      state.storyArchiveModal.cover = (data.storyline && data.storyline.cover) || {};
      setArchiveModalCover(state.storyArchiveModal.cover, state.storyArchiveModal.title);
    }
    renderStorylineList();
    renderArchiveViews();
    setStoriesStatus(data.message || 'Saved archive cover.', 'success');
    return data;
  }

  async function openStoryArchiveCard(storylineId = '') {
    const cleanId = text(storylineId);
    if (!cleanId) throw new Error('Storyline id is required.');
    const data = await core.getJson(`/api/roleplay/v2/storyline?storyline_id=${encodeURIComponent(cleanId)}`);
    const storyline = data.storyline || {};
    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    const checkpoints = (Array.isArray(data.checkpoints) ? data.checkpoints : []).slice().sort((a, b) => Number(a.order_index || 0) - Number(b.order_index || 0));
    const parts = [{
      id: 'overview',
      label: 'Overview',
      body: text(storyline.summary) || 'No storyline summary yet.',
      meta: `${sessions.length} session${sessions.length === 1 ? '' : 's'} · ${checkpoints.length} checkpoint${checkpoints.length === 1 ? '' : 's'}`,
    }].concat(checkpoints.map((checkpoint, index) => ({
      id: text(checkpoint.id) || `checkpoint-${index + 1}`,
      label: text(checkpoint.title) || text(checkpoint.branch_label) || `Part ${index + 1}`,
      body: buildCheckpointReadable(checkpoint),
      meta: [text(checkpoint.checkpoint_type) || 'live_save', text(checkpoint.branch_label) ? `Branch ${text(checkpoint.branch_label)}` : '', text(checkpoint.updated_at || checkpoint.meta?.updated_at) ? `Updated ${shortIso(checkpoint.updated_at || checkpoint.meta?.updated_at)}` : ''].filter(Boolean).join(' · '),
    })));
    openArchiveModal({
      eyebrow: 'Story archive',
      mode: 'storyline',
      recordId: text(storyline.id),
      title: text(storyline.title) || 'Untitled storyline',
      summary: text(storyline.summary) || 'Saved storyline archive view.',
      cover: storyline.cover,
      parts,
      uploadEnabled: true,
      metaLines: [
        text(storyline.meta?.status || storyline.status) || 'draft',
        text(storyline.project_id) ? `Project ${text(storyline.project_id)}` : '',
        `${sessions.length} session${sessions.length === 1 ? '' : 's'}`,
        `${checkpoints.length} checkpoint${checkpoints.length === 1 ? '' : 's'}`,
      ],
    });
  }

  function openRoleplayArchiveCard(sessionId = '') {
    const cleanId = text(sessionId);
    const session = byId(sessionsForSelectedStoryline(), cleanId);
    if (!session) throw new Error('Roleplay session not found in the selected storyline.');
    const storyline = state.selectedStoryline || {};
    const checkpoints = (Array.isArray(state.storyCheckpoints) ? state.storyCheckpoints : []).filter(row => text(row?.session_id) === cleanId);
    const parts = [{
      id: 'overview',
      label: 'Overview',
      body: text(session.session_summary) || 'No session summary yet.',
      meta: [modeLabelForPair(text(session.output_preset), text(session.interaction_mode)), text(session.session_mode) || 'live_scene'].filter(Boolean).join(' · '),
    }].concat(checkpoints.map((checkpoint, index) => ({
      id: text(checkpoint.id) || `checkpoint-${index + 1}`,
      label: text(checkpoint.title) || `Checkpoint ${index + 1}`,
      body: buildCheckpointReadable(checkpoint),
      meta: [text(checkpoint.checkpoint_type) || 'live_save', text(checkpoint.branch_label) ? `Branch ${text(checkpoint.branch_label)}` : '', text(checkpoint.updated_at || checkpoint.meta?.updated_at) ? `Updated ${shortIso(checkpoint.updated_at || checkpoint.meta?.updated_at)}` : ''].filter(Boolean).join(' · '),
    })));
    openArchiveModal({
      eyebrow: 'Roleplay archive',
      mode: 'session',
      recordId: cleanId,
      title: text(session.session_summary) || text(storyline.title) || cleanId,
      summary: `Session ${cleanId}${text(storyline.title) ? ` · ${text(storyline.title)}` : ''}`,
      cover: storyline.cover,
      parts,
      uploadEnabled: false,
      metaLines: [
        modeLabelForPair(text(session.output_preset), text(session.interaction_mode)),
        text(session.session_mode) || 'live_scene',
        `${checkpoints.length} checkpoint${checkpoints.length === 1 ? '' : 's'}`,
      ],
    });
  }

  function collectReadableFieldLines(value, prefix = '', lines = [], limit = 14) {
    if (lines.length >= limit || value == null) return lines;
    if (Array.isArray(value)) {
      value.forEach((item, index) => collectReadableFieldLines(item, prefix ? `${prefix} ${index + 1}` : `${index + 1}`, lines, limit));
      return lines;
    }
    if (typeof value === 'object') {
      Object.entries(value).forEach(([key, item]) => {
        if (lines.length >= limit) return;
        collectReadableFieldLines(item, prefix ? `${prefix} › ${key}` : key, lines, limit);
      });
      return lines;
    }
    const clean = text(value);
    if (!clean) return lines;
    const normalizedPrefix = text(prefix).replace(/[_]+/g, ' ');
    if (normalizedPrefix && /(^id$| ids$|path$|slug$|status$)/i.test(normalizedPrefix)) return lines;
    lines.push(normalizedPrefix ? `${normalizedPrefix}: ${clean}` : clean);
    return lines;
  }

  async function openCanonArchiveCard(recordId = '') {
    const cleanId = text(recordId);
    if (!cleanId) throw new Error('Canon record id is required.');
    const data = await core.getJson(`/api/roleplay/v2/builders/record?record_id=${encodeURIComponent(cleanId)}`);
    const record = data.record || {};
    const builderPayload = data.builder_payload || {};
    const lines = [];
    if (text(builderPayload.summary || record.summary)) lines.push(text(builderPayload.summary || record.summary));
    collectReadableFieldLines((builderPayload && builderPayload.fields) || {}, '', lines, 18);
    openArchiveModal({
      eyebrow: 'Canon archive',
      mode: 'canon',
      recordId: cleanId,
      title: text(builderPayload.display_label || builderPayload.label || record.display_label || record.label) || cleanId,
      summary: text(builderPayload.summary || record.summary) || 'Runtime-ready Forge record.',
      cover: {},
      parts: [{ label: 'Overview', body: lines.join('\n\n') || 'No readable overview was available for this record yet.', meta: text(record.kind) || 'record' }],
      uploadEnabled: false,
      metaLines: [
        text(record.kind) || 'entity',
        text(record.meta?.status || record.status) || 'runtime_ready',
        text(data.path) ? 'Stored record' : '',
      ],
    });
  }

  function renderArchiveViews() {
    const storyCards = buildArchiveStoryCards();
    const roleplayCards = buildArchiveRoleplayCards();
    const canonCards = flattenCanonArchiveCards();
    renderArchiveMeta('roleplay-v2-stories-archive-stories-meta', [`${storyCards.length} stor${storyCards.length === 1 ? 'y' : 'ies'}`]);
    renderArchiveMeta('roleplay-v2-stories-archive-roleplay-meta', [text(state.selectedStoryline?.title) || 'Select a storyline', `${roleplayCards.length} session${roleplayCards.length === 1 ? '' : 's'}`]);
    renderArchiveMeta('roleplay-v2-stories-archive-canon-meta', [`${canonCards.length} runtime-ready`, text((state.storyCanonArchive && state.storyCanonArchive.visible_statuses && state.storyCanonArchive.visible_statuses.join(', ')) || 'runtime_ready')]);
    renderArchiveCards('roleplay-v2-stories-archive-stories-grid', storyCards, 'No archived stories yet. Save or create a storyline first.');
    renderArchiveCards('roleplay-v2-stories-archive-roleplay-grid', roleplayCards, text(state.selectedStoryline?.id) ? 'No roleplay sessions are saved for the selected storyline yet.' : 'Select a storyline first, then this lane will show its saved roleplay sessions.');
    renderArchiveCards('roleplay-v2-stories-archive-canon-grid', canonCards, 'No runtime-ready Forge records are available yet. Compile or save records to surface them here.');
  }

  async function refreshCanonArchive({ silent = true } = {}) {
    if (state.storyCanonArchiveLoading) return state.storyCanonArchiveLoading;
    const pending = core.getJson('/api/roleplay/v2/builders/library-state')
      .then(data => {
        state.storyCanonArchive = data || { groups: {}, counts: {}, visible_statuses: ['runtime_ready'] };
        renderArchiveViews();
        return data;
      })
      .catch(err => {
        if (!silent) setStoriesStatus(err.message || String(err), 'error');
        throw err;
      })
      .finally(() => {
        state.storyCanonArchiveLoading = null;
      });
    state.storyCanonArchiveLoading = pending;
    return pending;
  }

  function buildContinuityText() {
    const storyline = state.selectedStoryline || {};
    const session = state.selectedSession || {};
    const checkpoint = state.selectedCheckpoint || {};
    const continuity = checkpoint.continuity_payload || {};
    const checkpointSnapshot = checkpoint.extra?.continuity_snapshot || {};
    const sessionSnapshot = session.extra?.continuity_snapshot || {};
    const resume = state.storyResumePreview?.resume || {};
    const resumeSceneState = resume.scene_state || {};
    const resumePayload = resume.continuity_payload || {};
    const resumeSnapshot = resume.continuity_snapshot || {};
    const mergeTrace = resume.resume_merge_trace || {};
    const checkpointCounts = continuitySnapshotCounts(checkpointSnapshot);
    const sessionCounts = continuitySnapshotCounts(sessionSnapshot);
    const resumeCounts = continuitySnapshotCounts(resumeSnapshot);
    const lines = [
      `Storyline · ${text(storyline.title) || 'none'}`,
      `Session · ${text(session.id) || 'none'}`,
      `Checkpoint · ${text(checkpoint.id || checkpoint.title) || 'none'}`,
      `Resume Scene packet · ${text(resume.runtime_bundle_id || checkpoint.runtime_bundle_id || session.latest_runtime_bundle_id || session.seed_runtime_bundle_id) || 'none'}`,
      `Resume output preset · ${text(resume.output_preset || session.output_preset) || 'roleplay'}`,
      `Resume interaction mode · ${text(resume.interaction_mode || session.interaction_mode) || 'roleplay'}`,
      '',
      `Checkpoint continuity note · ${text(continuity.continuity_note) || 'none'}`,
      `Checkpoint snapshot · turn ${checkpointCounts.turnSummaries} · relationship ${checkpointCounts.relationshipState} · unresolved ${checkpointCounts.unresolvedThreads} · callbacks ${checkpointCounts.callbackAnchors}`,
      `Session snapshot · turn ${sessionCounts.turnSummaries} · relationship ${sessionCounts.relationshipState} · unresolved ${sessionCounts.unresolvedThreads} · callbacks ${sessionCounts.callbackAnchors}`,
      `Resume snapshot · turn ${resumeCounts.turnSummaries} · relationship ${resumeCounts.relationshipState} · unresolved ${resumeCounts.unresolvedThreads} · callbacks ${resumeCounts.callbackAnchors}`,
      '',
      'Checkpoint continuity snapshot',
      JSON.stringify(checkpointSnapshot || {}, null, 2),
      '',
      'Session continuity snapshot',
      JSON.stringify(sessionSnapshot || {}, null, 2),
      '',
      'Resume continuity payload',
      JSON.stringify(resumePayload || {}, null, 2),
      '',
      'Resume scene state preview',
      JSON.stringify(resumeSceneState || {}, null, 2),
      '',
      'Resume merge trace',
      JSON.stringify(mergeTrace || {}, null, 2),
    ];
    return lines.join('\n');
  }

  function buildProvenanceText() {
    const checkpoint = state.selectedCheckpoint || {};
    const session = state.selectedSession || {};
    const continuity = checkpoint.continuity_payload || {};
    const resume = state.storyResumePreview?.resume || {};
    const sceneState = checkpoint.scene_state || session.scene_state_seed || {};
    const mergeTrace = resume.resume_merge_trace || {};
    const lines = [
      `Storyline id · ${text(state.selectedStorylineId) || 'none'}`,
      `Session id · ${text(session.id) || 'none'}`,
      `Checkpoint id · ${text(checkpoint.id) || 'none'}`,
      `Runtime bundle · ${text(checkpoint.runtime_bundle_id || session.latest_runtime_bundle_id || session.seed_runtime_bundle_id) || 'none'}`,
      `Runtime source scope · ${text(checkpoint.runtime_source_scope) || 'none'}`,
      `Runtime source id · ${text(checkpoint.runtime_source_id) || 'none'}`,
      `Selected entity ids · ${(checkpoint.selected_entity_ids || []).length}`,
      `Selected memory ids · ${(checkpoint.selected_memory_ids || []).length}`,
      `Continuity note · ${text(continuity.continuity_note) || 'none'}`,
      `Resume merge sources · runtime ${Number((mergeTrace.runtime_seed_keys || []).length || 0)} · session ${Number((mergeTrace.session_seed_keys || []).length || 0)} · checkpoint ${Number((mergeTrace.checkpoint_state_keys || []).length || 0)} · continuity ${Number((mergeTrace.continuity_snapshot_keys || []).length || 0)}`,
      '',
      'Scene state snapshot',
      JSON.stringify(sceneState || {}, null, 2),
      '',
      'Resume merge trace summary',
      JSON.stringify(mergeTrace || {}, null, 2),
    ];
    return lines.join('\n');
  }

  function renderInspector() {
    const activeBadge = core.$('roleplay-v2-stories-active-badge');
    const summary = core.$('roleplay-v2-stories-summary');
    const reader = core.$('roleplay-v2-stories-reader');
    const continuity = core.$('roleplay-v2-stories-continuity');
    const provenance = core.$('roleplay-v2-stories-provenance');
    if (activeBadge) activeBadge.textContent = text(state.selectedStoryline?.title) || 'No storyline selected';
    if (summary) summary.textContent = buildSummaryText();
    if (reader) reader.textContent = buildReaderText();
    if (continuity) continuity.textContent = buildContinuityText();
    if (provenance) provenance.textContent = buildProvenanceText();
  }

  function renderStorylineList() {
    const root = core.$('roleplay-v2-stories-list');
    const railCount = core.$('roleplay-v2-stories-rail-count');
    if (!root) return;
    const search = text(core.$('roleplay-v2-stories-search')?.value).toLowerCase();
    const statusFilter = text(core.$('roleplay-v2-stories-filter-status')?.value).toLowerCase();
    const items = storylineList().filter(item => {
      const haystack = JSON.stringify(item || {}).toLowerCase();
      if (search && !haystack.includes(search)) return false;
      if (statusFilter && text(item.status).toLowerCase() !== statusFilter) return false;
      return true;
    });
    if (railCount) railCount.textContent = String(items.length);
    root.innerHTML = '';
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = storylineList().length ? 'No storylines match the current filter.' : 'No storylines yet. Use “New storyline” to create the first one.';
      root.appendChild(empty);
      return;
    }
    items.forEach(item => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.style.display = 'grid';
      btn.style.gap = '4px';
      btn.style.textAlign = 'left';
      btn.classList.toggle('btn-primary', text(item.id) === text(state.selectedStorylineId));
      btn.innerHTML = `
        <span>${text(item.title) || 'Untitled storyline'}</span>
        <span class="mini-note">${text(item.status) || 'draft'} · sessions ${Number(item.session_count || 0)} · checkpoints ${Number(item.checkpoint_count || 0)}</span>
        <span class="mini-note">${text(item.project_id) ? `Project · ${text(item.project_id)}` : 'No project linked'}${text(item.active_session_id) ? ` · active ${text(item.active_session_id)}` : ''}</span>
        <span class="mini-note">Updated ${shortIso(item.updated_at) || 'unknown'}</span>
      `;
      btn.addEventListener('click', () => loadStorylineDetail(text(item.id)).catch(err => setStoriesStatus(err.message || String(err), 'error')));
      root.appendChild(btn);
    });
  }

  function renderWorkspace() {
    const title = core.$('roleplay-v2-stories-header-title');
    const note = core.$('roleplay-v2-stories-header-note');
    const badge = core.$('roleplay-v2-stories-workspace-badge');
    const root = core.$('roleplay-v2-stories-session-list');
    if (!root) return;
    const storyline = state.selectedStoryline || {};
    const sessions = sessionsForSelectedStoryline();
    const checkpoints = checkpointsForSelectedSession();
    if (title) title.textContent = text(storyline.title) || 'Session + checkpoint timeline';
    if (note) note.textContent = text(storyline.summary) || 'Select a storyline to inspect sessions and saved checkpoints.';
    if (badge) badge.textContent = text(state.selectedSession?.id) ? 'Timeline active' : 'Timeline';
    root.innerHTML = '';

    const resume = state.storyResumePreview?.resume || {};
    const restorePanel = document.createElement('div');
    restorePanel.className = 'panel';
    restorePanel.style.padding = '12px';
    restorePanel.style.background = 'rgba(255,255,255,0.02)';
    restorePanel.style.border = '1px solid rgba(255,255,255,0.06)';
    const restoreWarnings = Array.isArray(resume.mode_lock_warnings) ? resume.mode_lock_warnings.filter(Boolean) : [];
    restorePanel.innerHTML = `
      <div class="stat-title">Restore target</div>
      <div class="mini-note" style="margin-top:8px;">Storyline · ${text(storyline.title) || 'none'} · Session · ${text(state.selectedSession?.id) || 'none'} · Checkpoint · ${text(state.selectedCheckpoint?.title || state.selectedCheckpoint?.id) || 'session active checkpoint'}</div>
      <div class="mini-note" style="margin-top:6px;">Mode lock · ${modeLabelForPair(text(resume.output_preset || state.selectedSession?.output_preset), text(resume.interaction_mode || state.selectedSession?.interaction_mode))} · output ${text(resume.output_preset || state.selectedSession?.output_preset) || 'roleplay'} · interaction ${text(resume.interaction_mode || state.selectedSession?.interaction_mode) || 'roleplay'}</div>
      <div class="mini-note" style="margin-top:6px;">Runtime · ${text(resume.runtime_bundle_id || state.selectedCheckpoint?.runtime_bundle_id || state.selectedSession?.latest_runtime_bundle_id || state.selectedSession?.seed_runtime_bundle_id) || 'none'}</div>
      <div class="mini-note" style="margin-top:6px;">Resume fallback · checkpoint first, then session active checkpoint, then storyline active session.</div>
      ${restoreWarnings.length ? `<div class="mini-note" style="margin-top:8px; color:#f6c26b;">Mode warnings · ${restoreWarnings.join(' | ')}</div>` : ''}
    `;
    root.appendChild(restorePanel);

    const overview = document.createElement('div');
    overview.className = 'panel';
    overview.style.padding = '12px';
    overview.style.background = 'rgba(255,255,255,0.02)';
    overview.style.border = '1px solid rgba(255,255,255,0.06)';
    const publicationSummary = storyline.extra?.shared_continuity_summary || {};
    const selectedCheckpoint = state.selectedCheckpoint || {};
    const worldPublish = selectedCheckpointPublication('shared_world');
    const universePublish = selectedCheckpointPublication('shared_universe');
    overview.innerHTML = `
      <div class="stat-title">Storyline overview</div>
      <div class="mini-note" style="margin-top:8px;">${text(storyline.title) ? `${text(storyline.title)} · ${text(storyline.meta?.status || storyline.status) || 'draft'}` : 'No storyline selected.'}</div>
      <div class="mini-note" style="margin-top:6px;">Project · ${text(storyline.project_id) || 'none'} · scenarios ${(storyline.linked_scenario_ids || []).length} · entities ${(storyline.linked_entity_ids || []).length}</div>
      <div class="mini-note" style="margin-top:6px;">Shared world link · ${text(storyline.linked_world_id) || 'none'} · published ${Number(publicationSummary.published_counts?.shared_world || 0)}</div>
      <div class="mini-note" style="margin-top:6px;">Shared universe link · ${text(storyline.linked_universe_id) || 'none'} · published ${Number(publicationSummary.published_counts?.shared_universe || 0)}</div>
      <div class="mini-note" style="margin-top:8px;">Selected checkpoint publish state · world ${Number(worldPublish?.published_counts?.total || 0)} · universe ${Number(universePublish?.published_counts?.total || 0)}</div>
    `;
    root.appendChild(overview);

    const publishPanel = document.createElement('div');
    publishPanel.className = 'panel';
    publishPanel.style.padding = '12px';
    publishPanel.style.background = 'rgba(255,255,255,0.02)';
    publishPanel.style.border = '1px solid rgba(255,255,255,0.06)';
    const publishHeader = document.createElement('div');
    publishHeader.className = 'stat-title';
    publishHeader.textContent = 'Shared continuity';
    publishPanel.appendChild(publishHeader);
    const publishNote = document.createElement('div');
    publishNote.className = 'mini-note';
    publishNote.style.marginTop = '8px';
    publishNote.textContent = text(state.selectedCheckpointId) ? 'Publish the selected checkpoint into an explicit shared continuity lane. This does not merge story sandboxes automatically.' : 'Select a checkpoint to publish deliberate shared continuity.';
    publishPanel.appendChild(publishNote);
    const publishRow = document.createElement('div');
    publishRow.style.display = 'flex';
    publishRow.style.flexWrap = 'wrap';
    publishRow.style.gap = '8px';
    publishRow.style.marginTop = '10px';
    const publishWorldBtn = document.createElement('button');
    publishWorldBtn.type = 'button';
    publishWorldBtn.className = 'btn';
    publishWorldBtn.textContent = 'Publish checkpoint → shared world';
    publishWorldBtn.disabled = !!state.storiesBusy || !canPublishSharedScope('shared_world');
    publishWorldBtn.addEventListener('click', () => publishSelectedCheckpointShared('shared_world').catch(err => setStoriesStatus(err.message || String(err), 'error')));
    publishRow.appendChild(publishWorldBtn);
    const publishUniverseBtn = document.createElement('button');
    publishUniverseBtn.type = 'button';
    publishUniverseBtn.className = 'btn';
    publishUniverseBtn.textContent = 'Publish checkpoint → shared universe';
    publishUniverseBtn.disabled = !!state.storiesBusy || !canPublishSharedScope('shared_universe');
    publishUniverseBtn.addEventListener('click', () => publishSelectedCheckpointShared('shared_universe').catch(err => setStoriesStatus(err.message || String(err), 'error')));
    publishRow.appendChild(publishUniverseBtn);
    publishPanel.appendChild(publishRow);
    const publishMeta = document.createElement('div');
    publishMeta.className = 'mini-note';
    publishMeta.style.marginTop = '10px';
    publishMeta.textContent = `Checkpoint ${text(state.selectedCheckpoint?.title || state.selectedCheckpoint?.id) || 'none'} · world publish ${Number(selectedCheckpointPublication('shared_world')?.published_counts?.total || 0)} · universe publish ${Number(selectedCheckpointPublication('shared_universe')?.published_counts?.total || 0)}`;
    publishPanel.appendChild(publishMeta);
    root.appendChild(publishPanel);

    const sessionPanel = document.createElement('div');
    sessionPanel.className = 'panel';
    sessionPanel.style.padding = '12px';
    sessionPanel.style.background = 'rgba(255,255,255,0.02)';
    sessionPanel.style.border = '1px solid rgba(255,255,255,0.06)';
    const sessionHeader = document.createElement('div');
    sessionHeader.className = 'stat-title';
    sessionHeader.textContent = 'Sessions';
    sessionPanel.appendChild(sessionHeader);
    const sessionList = document.createElement('div');
    sessionList.style.display = 'grid';
    sessionList.style.gap = '8px';
    sessionList.style.marginTop = '10px';
    if (!sessions.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = text(storyline.id) ? 'No sessions yet for this storyline.' : 'Select or create a storyline first.';
      sessionList.appendChild(empty);
    } else {
      sessions.forEach(session => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.style.display = 'grid';
        btn.style.gap = '4px';
        btn.style.textAlign = 'left';
        btn.classList.toggle('btn-primary', text(session.id) === text(state.selectedSessionId));
        btn.innerHTML = `
          <span>${text(session.id)}</span>
          <span class="mini-note">${modeLabelForPair(text(session.output_preset), text(session.interaction_mode))} · ${text(session.session_mode) || 'live_scene'} · ${text(session.meta?.status || session.status) || 'draft'} · checkpoints ${(session.checkpoint_ids || []).length}</span>
          <span class="mini-note">${text(session.session_summary) || 'No session summary yet.'}</span>
          <span class="mini-note">Updated ${shortIso(session.updated_at || session.meta?.updated_at) || 'unknown'}${text(session.active_checkpoint_id) ? ` · active checkpoint ${text(session.active_checkpoint_id)}` : ''}</span>
        `;
        btn.addEventListener('click', async () => {
          selectSession(text(session.id));
          await refreshResumePreview().catch(() => { state.storyResumePreview = null; });
          renderWorkspace();
          renderInspector();
          syncSceneBinding();
        });
        sessionList.appendChild(btn);
      });
    }
    sessionPanel.appendChild(sessionList);
    root.appendChild(sessionPanel);

    const checkpointPanel = document.createElement('div');
    checkpointPanel.className = 'panel';
    checkpointPanel.style.padding = '12px';
    checkpointPanel.style.background = 'rgba(255,255,255,0.02)';
    checkpointPanel.style.border = '1px solid rgba(255,255,255,0.06)';
    const checkpointHeader = document.createElement('div');
    checkpointHeader.className = 'stat-title';
    checkpointHeader.textContent = 'Checkpoints';
    checkpointPanel.appendChild(checkpointHeader);
    const checkpointList = document.createElement('div');
    checkpointList.style.display = 'grid';
    checkpointList.style.gap = '8px';
    checkpointList.style.marginTop = '10px';
    if (!checkpoints.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = text(state.selectedSessionId) ? 'No checkpoints yet for the selected session.' : 'Select a session to inspect saved checkpoints.';
      checkpointList.appendChild(empty);
    } else {
      checkpoints.forEach(checkpoint => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.style.display = 'grid';
        btn.style.gap = '4px';
        btn.style.textAlign = 'left';
        btn.classList.toggle('btn-primary', text(checkpoint.id) === text(state.selectedCheckpointId));
        btn.innerHTML = `
          <span>${text(checkpoint.title) || text(checkpoint.id)}</span>
          <span class="mini-note">${text(checkpoint.checkpoint_type) || 'live_save'}${text(checkpoint.branch_label) ? ` · branch ${text(checkpoint.branch_label)}` : ''} · ${modeLabelForPair(text(checkpoint.extra?.mode_lock?.output_preset || state.selectedSession?.output_preset), text(checkpoint.extra?.mode_lock?.interaction_mode || state.selectedSession?.interaction_mode))}</span>
          <span class="mini-note">${text(checkpoint.summary) || 'No checkpoint summary yet.'}</span>
          <span class="mini-note">Order ${Number(checkpoint.order_index || 0)} · updated ${shortIso(checkpoint.updated_at || checkpoint.meta?.updated_at) || 'unknown'}${text(checkpoint.runtime_bundle_id) ? ` · runtime ${text(checkpoint.runtime_bundle_id)}` : ''}</span>
        `;
        btn.addEventListener('click', async () => {
          state.selectedCheckpoint = checkpoint;
          state.selectedCheckpointId = text(checkpoint.id);
          await refreshResumePreview().catch(() => { state.storyResumePreview = null; });
          renderWorkspace();
          renderInspector();
          core.modules?.continuityControls?.refreshContext?.('stories', { silent: true }).catch(() => null);
          syncSceneBinding();
        });
        checkpointList.appendChild(btn);
      });
    }
    checkpointPanel.appendChild(checkpointList);
    root.appendChild(checkpointPanel);
  }

  function renderStoriesView() {
    renderStorylineList();
    renderWorkspace();
    renderInspector();
    renderArchiveViews();
    refreshStoriesMetaPanels();
    renderActionState();
  }

  async function fetchStorylines({ preserveSelection = true } = {}) {
    setStoriesBusy(true);
    try {
      const previousSelectedId = preserveSelection ? text(state.selectedStorylineId) : '';
      const data = await core.getJson('/api/roleplay/v2/stories');
      state.storylines = Array.isArray(data.storylines) ? data.storylines : [];
      const nextSelectedId = previousSelectedId && byId(state.storylines, previousSelectedId) ? previousSelectedId : text(state.storylines[0]?.id);
      if (nextSelectedId) {
        await loadStorylineDetail(nextSelectedId, { preserveSessionSelection: true, silent: true });
      } else {
        state.selectedStoryline = null;
        state.selectedStorylineId = '';
        state.storySessions = [];
        state.selectedSession = null;
        state.selectedSessionId = '';
        state.storyCheckpoints = [];
        state.selectedCheckpoint = null;
        state.selectedCheckpointId = '';
        state.storyResumePreview = null;
        renderStoriesView();
      }
      syncSceneBinding();
      core.setOutput(data);
      return data;
    } finally {
      setStoriesBusy(false);
    }
  }

  async function loadStorylineDetail(storylineId, { preserveSessionSelection = false, preferredSessionId = '', preferredCheckpointId = '', silent = false } = {}) {
    const cleanId = text(storylineId);
    if (!cleanId) {
      state.selectedStoryline = null;
      state.selectedStorylineId = '';
      state.storySessions = [];
      state.selectedSession = null;
      state.selectedSessionId = '';
      state.storyCheckpoints = [];
      state.selectedCheckpoint = null;
      state.selectedCheckpointId = '';
      state.storyResumePreview = null;
      renderStoriesView();
      syncSceneBinding();
      return null;
    }
    setStoriesBusy(true);
    try {
      const data = await core.getJson(`/api/roleplay/v2/storyline?storyline_id=${encodeURIComponent(cleanId)}`);
      const previousSessionId = preserveSessionSelection ? text(state.selectedSessionId) : '';
      const previousCheckpointId = preserveSessionSelection ? text(state.selectedCheckpointId) : '';
      state.selectedStoryline = data.storyline || null;
      state.selectedStorylineId = cleanId;
      if (!text(core.$('roleplay-v2-stories-form-project-id')?.value)) {
        const projectEl = core.$('roleplay-v2-stories-form-project-id');
        if (projectEl) projectEl.value = text(data.storyline?.project_id);
      }
      const continuityEl = core.$('roleplay-v2-stories-form-continuity-policy');
      if (continuityEl && !text(continuityEl.value)) continuityEl.value = text(data.storyline?.continuity_policy) || 'runtime_anchored';
      state.storySessions = Array.isArray(data.sessions) ? data.sessions : [];
      state.storyCheckpoints = Array.isArray(data.checkpoints) ? data.checkpoints : [];
      const nextSession = byId(state.storySessions, preferredSessionId) || byId(state.storySessions, previousSessionId) || byId(state.storySessions, text(state.selectedStoryline?.active_session_id)) || state.storySessions[0] || null;
      state.selectedSession = nextSession;
      state.selectedSessionId = text(nextSession?.id);
      const scopedCheckpoints = checkpointsForSelectedSession();
      const nextCheckpoint = byId(scopedCheckpoints, preferredCheckpointId) || byId(scopedCheckpoints, previousCheckpointId) || byId(scopedCheckpoints, text(nextSession?.active_checkpoint_id)) || scopedCheckpoints[0] || null;
      state.selectedCheckpoint = nextCheckpoint;
      state.selectedCheckpointId = text(nextCheckpoint?.id);
      await refreshResumePreview().catch(() => { state.storyResumePreview = null; });
      renderStoriesView();
      core.modules?.continuityControls?.refreshContext?.('stories', { silent: true }).catch(() => null);
      syncSceneBinding();
      core.setOutput(data);
      if (!silent) setStoriesStatus(`Loaded storyline: ${text(state.selectedStoryline?.title) || cleanId}`, 'success');
      return data;
    } finally {
      setStoriesBusy(false);
    }
  }

  async function handleNewStoryline({ preferScene = false } = {}) {
    const payload = storylineFormPayload({ preferScene });
    if (!text(payload.title)) {
      if (preferScene) fillStorylineDraftFromScene();
      core.$('roleplay-v2-stories-form-title')?.focus();
      setStoriesStatus('Storyline title is required. Fill the form instead of using a prompt.', 'warning');
      return;
    }
    setStoriesBusy(true);
    try {
      const data = await core.postForm('/api/roleplay/v2/storyline/create', payload);
      state.storylines = Array.isArray(data.storylines) ? data.storylines : storylineList();
      const createdId = text(data.storyline?.id);
      if (createdId) {
        await loadStorylineDetail(createdId, { silent: true });
      } else {
        renderStoriesView();
      }
      if (!text(core.$('roleplay-v2-stories-form-project-id')?.value)) {
        const projectEl = core.$('roleplay-v2-stories-form-project-id');
        if (projectEl) projectEl.value = text(data.storyline?.project_id);
      }
      syncSceneBinding();
      core.setOutput(data);
      setStoriesStatus(data.message || 'Created storyline.', 'success');
      return data;
    } finally {
      setStoriesBusy(false);
    }
  }

  async function handleNewSession() {
    const storylineId = text(state.selectedStorylineId);
    if (!storylineId) {
      setStoriesStatus('Select a storyline first.', 'warning');
      return;
    }
    const payload = sessionCreatePayload();
    setStoriesBusy(true);
    try {
      const data = await core.postForm('/api/roleplay/v2/story-session/create', payload);
      const createdId = text(data.session?.id);
      await loadStorylineDetail(storylineId, { preferredSessionId: createdId, preferredCheckpointId: text(payload.seed_checkpoint_id), silent: true });
      core.setOutput(data);
      setStoriesStatus(data.message || 'Created story session.', 'success');
      return data;
    } finally {
      setStoriesBusy(false);
    }
  }

  async function boot() {
    setStoriesSubtab(state.storySubtab || 'workspace');
    setArchiveView(state.storyArchiveView || 'stories');
    setInspectorView(state.storyInspectorView || 'summary');
    core.$('btn-roleplay-v2-stories-new')?.addEventListener('click', () => handleNewStoryline({ preferScene: true }).catch(err => setStoriesStatus(err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-stories-submit-storyline')?.addEventListener('click', () => handleNewStoryline({ preferScene: false }).catch(err => setStoriesStatus(err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-stories-fill-from-scene')?.addEventListener('click', () => fillStorylineDraftFromScene());
    core.$('btn-roleplay-v2-stories-clear-form')?.addEventListener('click', clearStorylineForm);
    core.$('btn-roleplay-v2-stories-refresh')?.addEventListener('click', () => fetchStorylines({ preserveSelection: true }).catch(err => setStoriesStatus(err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-stories-create-from-scene')?.addEventListener('click', async () => {
      try {
        if (!core.modules.scene?.createStorylineFromScene) throw new Error('Scene module is not ready for story creation yet.');
        const payload = storylineFormPayload({ preferScene: true });
        if (!text(payload.title)) {
          fillStorylineDraftFromScene();
          core.$('roleplay-v2-stories-form-title')?.focus();
          throw new Error('Storyline title is required before creating from Scene.');
        }
        const created = await core.modules.scene.createStorylineFromScene({
          title: payload.title,
          summary: payload.summary,
          projectId: payload.project_id,
          linkedWorldId: payload.linked_world_id,
          linkedUniverseId: payload.linked_universe_id,
          linkedScenarioIds: JSON.parse(payload.linked_scenario_ids_json || '[]'),
          linkedEntityIds: JSON.parse(payload.linked_entity_ids_json || '[]'),
          continuityPolicy: payload.continuity_policy,
        });
        const createdStorylineId = text(created?.storyline?.id);
        if (createdStorylineId) await loadStorylineDetail(createdStorylineId, { preferredSessionId: text(created?.session?.id), preferredCheckpointId: text(created?.checkpoint_id), silent: true });
        setStoriesStatus('Created storyline from the current Scene and synced Stories selection.', 'success');
      } catch (err) {
        setStoriesStatus(err.message || String(err), 'error');
      }
    });
    core.$('btn-roleplay-v2-stories-new-session')?.addEventListener('click', () => handleNewSession().catch(err => setStoriesStatus(err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-stories-submit-session')?.addEventListener('click', () => handleNewSession().catch(err => setStoriesStatus(err.message || String(err), 'error')));
    core.$('btn-roleplay-v2-stories-clear-session-form')?.addEventListener('click', clearSessionForm);
    core.$('btn-roleplay-v2-stories-open-reader')?.addEventListener('click', () => { setStoriesSubtab('archive'); setArchiveView('stories'); });
    core.$('btn-roleplay-v2-stories-resume-scene')?.addEventListener('click', async () => {
      try {
        if (!core.modules.scene?.resumeFromStorySelection) throw new Error('Scene resume bridge is not ready yet.');
        await core.modules.scene.resumeFromStorySelection({
          storylineId: state.selectedStorylineId,
          sessionId: state.selectedSessionId,
          checkpointId: state.selectedCheckpointId,
        });
        setStoriesStatus('Stories selection resumed into Scene.', 'success');
      } catch (err) {
        setStoriesStatus(err.message || String(err), 'error');
      }
    });
    core.$('roleplay-v2-stories-search')?.addEventListener('input', renderStorylineList);
    core.$('roleplay-v2-stories-filter-status')?.addEventListener('change', renderStorylineList);
    core.$('roleplay-v2-stories-form-title')?.addEventListener('input', refreshStoriesMetaPanels);
    core.$('roleplay-v2-stories-form-summary')?.addEventListener('input', refreshStoriesMetaPanels);
    core.$('roleplay-v2-stories-form-project-id')?.addEventListener('input', refreshStoriesMetaPanels);
    core.$('roleplay-v2-stories-form-continuity-policy')?.addEventListener('change', refreshStoriesMetaPanels);
    core.$('roleplay-v2-stories-session-summary')?.addEventListener('input', refreshStoriesMetaPanels);
    core.$('roleplay-v2-stories-session-seed-checkpoint')?.addEventListener('change', refreshStoriesMetaPanels);
    core.$('roleplay-v2-output-preset')?.addEventListener('change', refreshStoriesMetaPanels);
    core.$('roleplay-v2-interaction-mode')?.addEventListener('change', refreshStoriesMetaPanels);
    document.querySelectorAll('#roleplay-v2-stories-subtabbar [data-roleplay-v2-stories-subtab]').forEach(btn => {
      btn.addEventListener('click', () => setStoriesSubtab(btn.getAttribute('data-roleplay-v2-stories-subtab')));
    });
    document.querySelectorAll('#roleplay-v2-stories-archive-viewbar [data-roleplay-v2-stories-archive-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        setStoriesSubtab('archive');
        setArchiveView(btn.getAttribute('data-roleplay-v2-stories-archive-view'));
      });
    });
    document.querySelectorAll('#roleplay-v2-stories-inspector-viewbar [data-roleplay-v2-stories-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        setStoriesSubtab('inspector');
        setInspectorView(btn.getAttribute('data-roleplay-v2-stories-view'));
      });
    });
    document.querySelectorAll('#roleplay-v2-stories-continuity-viewbar [data-roleplay-v2-stories-continuity-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        setStoriesSubtab('inspector');
        setInspectorView('continuity');
        setContinuityView(btn.getAttribute('data-roleplay-v2-stories-continuity-view'));
      });
    });
    core.$('btn-roleplay-v2-stories-archive-close')?.addEventListener('click', closeArchiveModal);
    core.$('roleplay-v2-stories-archive-modal')?.addEventListener('click', event => {
      if (event.target === core.$('roleplay-v2-stories-archive-modal')) closeArchiveModal();
    });
    core.$('btn-roleplay-v2-stories-archive-upload-cover')?.addEventListener('click', () => core.$('roleplay-v2-stories-archive-upload-input')?.click());
    core.$('roleplay-v2-stories-archive-upload-input')?.addEventListener('change', async event => {
      const file = event.target?.files?.[0];
      if (!file) return;
      try {
        await handleArchiveCoverUpload(file);
      } catch (err) {
        setStoriesStatus(err.message || String(err), 'error');
      } finally {
        event.target.value = '';
      }
    });
    core.modules?.continuityControls?.registerContext?.('stories', {
      listId: 'roleplay-v2-continuity-stories-list',
      inspectorId: 'roleplay-v2-continuity-stories-inspector',
      statusId: 'roleplay-v2-continuity-stories-status',
      countId: 'roleplay-v2-continuity-stories-count',
      refreshButtonId: 'btn-roleplay-v2-continuity-stories-refresh',
      getFilters: storiesContinuityFilters,
      onSelect: row => {
        if (row && core.$('roleplay-v2-memory-control-id')) core.$('roleplay-v2-memory-control-id').value = text(row.memory_id || row.id);
      },
    });
    clearSessionForm();
    setContinuityView(state.storyContinuityView || 'rows');
    renderStoriesView();
    syncSceneBinding();
    await fetchStorylines({ preserveSelection: false }).catch(err => setStoriesStatus(err.message || String(err), 'error'));
    await refreshCanonArchive({ silent: true }).catch(() => null);
    refreshStoriesMetaPanels();
    setStoriesStatus('Stories browser, restore preview, and save forms are ready.', 'success');
  }

  core.registerModule('stories', {
    boot,
    fetchStorylines,
    loadStorylineDetail,
    publishSelectedCheckpointShared,
    renderStoriesView,
    setStoriesSubtab,
    setArchiveView,
    setInspectorView,
    setContinuityView,
  });
})();
