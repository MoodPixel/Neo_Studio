(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;
  const STREAM_FIRST_EVENT_TIMEOUT_MS = 90000;
  const STREAM_IDLE_TIMEOUT_MS = 20000;
  let streamController = null;


  function parseSseBlock(block) {
    const normalized = String(block || '').replace(/\r\n/g, '\n').trim();
    if (!normalized) return null;
    const lines = normalized.split('\n');
    let event = 'message';
    const dataLines = [];
    lines.forEach(line => {
      if (line.startsWith('event:')) event = line.slice(6).trim() || 'message';
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    });
    const raw = dataLines.join('\n');
    if (!raw) return null;
    try { return { event, payload: JSON.parse(raw) }; } catch (_err) { return { event, payload: { raw } }; }
  }

  function makeStreamTimeoutError(code, message) {
    const err = new Error(message);
    err.code = code;
    return err;
  }

  async function readStreamChunkWithTimeout(reader, timeoutMs, code) {
    let timeoutId = null;
    try {
      return await Promise.race([
        reader.read(),
        new Promise((_, reject) => {
          timeoutId = window.setTimeout(() => reject(makeStreamTimeoutError(code, code === 'STREAM_IDLE_TIMEOUT' ? 'The live scene stream stalled before finishing.' : 'The live scene stream timed out before visible output arrived.')), timeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
    }
  }

  async function consumeSceneStream(response, handlers = {}) {
    const meta = { sawAnyEvent: false, sawFinal: false, rawText: '', stalled: false };
    const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase();
    if (!response.body) {
      meta.rawText = core.text(await response.text());
      return meta;
    }
    if (!contentType.includes('text/event-stream')) {
      meta.rawText = core.text(await response.text());
      return meta;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await readStreamChunkWithTimeout(reader, meta.sawAnyEvent ? STREAM_IDLE_TIMEOUT_MS : STREAM_FIRST_EVENT_TIMEOUT_MS, meta.sawAnyEvent ? 'STREAM_IDLE_TIMEOUT' : 'STREAM_FIRST_TIMEOUT');
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let splitAt = buffer.indexOf('\n\n');
        while (splitAt >= 0) {
          const block = buffer.slice(0, splitAt);
          buffer = buffer.slice(splitAt + 2);
          const parsed = parseSseBlock(block);
          if (!parsed) { splitAt = buffer.indexOf('\n\n'); continue; }
          meta.sawAnyEvent = true;
          if (parsed.event === 'final') meta.sawFinal = true;
          if (typeof handlers[parsed.event] === 'function') handlers[parsed.event](parsed.payload || {});
          splitAt = buffer.indexOf('\n\n');
        }
      }
    } catch (err) {
      if (err?.code === 'STREAM_IDLE_TIMEOUT' || err?.code === 'STREAM_FIRST_TIMEOUT') meta.stalled = true;
      try { await reader.cancel(err); } catch (_cancelErr) {}
      throw err;
    }
    const tail = parseSseBlock(buffer);
    if (tail) {
      meta.sawAnyEvent = true;
      if (tail.event === 'final') meta.sawFinal = true;
      if (typeof handlers[tail.event] === 'function') handlers[tail.event](tail.payload || {});
    }
    return meta;
  }

  function setSceneBusy(isBusy) {
    state.sceneBusy = !!isBusy;
    const sendBtn = core.$('btn-roleplay-v2-scene-send-bridge');
    const continueBtn = core.$('btn-roleplay-v2-scene-continue');
    const saveBtn = core.$('btn-roleplay-v2-scene-save-checkpoint');
    const createStoryBtn = core.$('btn-roleplay-v2-scene-create-storyline');
    const refreshContinuityBtn = core.$('btn-roleplay-v2-scene-refresh-session-continuity');
    const autosaveToggle = core.$('roleplay-v2-scene-autosave-toggle');
    const turnInputStyle = core.$('roleplay-v2-scene-turn-input-style');
    const input = core.$('roleplay-v2-scene-user-input');
    const stateBadge = core.$('roleplay-v2-scene-transcript-state');
    [sendBtn, continueBtn, saveBtn, createStoryBtn, refreshContinuityBtn, autosaveToggle, turnInputStyle, input].forEach(el => { if (el) el.disabled = !!isBusy; });
    if (stateBadge) stateBadge.textContent = isBusy ? 'Busy' : 'Idle';
  }

  function buildSceneStatePayload() {
    const runtimeSeed = state.activeRuntimeBundle?.packet?.scene_state_seed || {};
    const continuityState = state.sceneContinuity?.scene_state || {};
    const merged = Object.assign({}, runtimeSeed, continuityState, state.sceneState || {});
    const mode = core.applyModeSelection({ outputPreset: core.$('roleplay-v2-output-preset')?.value || merged.output_preset, interactionMode: core.$('roleplay-v2-interaction-mode')?.value || merged.interaction_mode, prefer: 'output' });
    merged.runtime_bundle_id = core.text(state.activeRuntimeBundle?.id) || core.text(runtimeSeed.runtime_bundle_id);
    merged.output_preset = mode.output_preset;
    merged.interaction_mode = mode.interaction_mode;
    merged.scene_goal = core.text(core.$('roleplay-v2-scene-premise')?.value) || core.text(merged.scene_goal);
    merged.scene_notes = core.text(core.$('roleplay-v2-scene-notes')?.value) || core.text(merged.scene_notes);
    merged.narrator_posture = core.text(core.$('roleplay-v2-scene-posture')?.value) || core.text(merged.narrator_posture) || (novelAuthoringSceneActive() ? 'omniscient_narration' : 'partner_focus');
    merged.continuity_mode = core.text(core.$('roleplay-v2-scene-continuity-mode')?.value) || core.text(merged.continuity_mode) || 'runtime_anchored';
    merged.focus_stack = Array.isArray(merged.focus_stack) ? merged.focus_stack : [];
    merged.cast_entity_ids = Array.isArray(merged.cast_entity_ids) ? merged.cast_entity_ids : [];
    merged.memory_source_ids = Array.isArray(merged.memory_source_ids) ? merged.memory_source_ids : [];
    merged.canon_guard_source_ids = Array.isArray(merged.canon_guard_source_ids) ? merged.canon_guard_source_ids : [];
    state.sceneState = merged;
    return merged;
  }

  function currentTurnInputStyle() {
    const value = core.text(core.$('roleplay-v2-scene-turn-input-style')?.value || state.sceneTurnInputStyle || 'free_typing').toLowerCase();
    return ['free_typing', 'choice_assist', 'hybrid'].includes(value) ? value : 'free_typing';
  }

  function sceneModeSelection() {
    return core.currentModeSelection();
  }

  function novelAuthoringSceneActive() {
    const mode = sceneModeSelection();
    return mode.output_preset === 'novel' && mode.interaction_mode === 'authoring';
  }

  function ensureNovelAuthoringSceneDefaults() {
    if (!novelAuthoringSceneActive()) return;
    const posture = core.$('roleplay-v2-scene-posture');
    const style = core.$('roleplay-v2-scene-style');
    if (posture && ['','partner_focus'].includes(core.text(posture.value))) posture.value = 'omniscient_narration';
    if (style && ['','Immersive dialogue'].includes(core.text(style.value))) style.value = 'Novel-like prose';
  }

  function applySceneModeCopy() {
    const setupNote = core.$('roleplay-v2-scene-setup-note');
    const brief = core.$('roleplay-v2-scene-authoring-brief');
    const premiseLabel = core.$('roleplay-v2-scene-premise-label');
    const premise = core.$('roleplay-v2-scene-premise');
    const notesLabel = core.$('roleplay-v2-scene-notes-label');
    const notes = core.$('roleplay-v2-scene-notes');
    const chatNote = core.$('roleplay-v2-scene-chat-note');
    const inputLabel = core.$('roleplay-v2-scene-user-input-label');
    const input = core.$('roleplay-v2-scene-user-input');
    const sendBtn = core.$('btn-roleplay-v2-scene-send-bridge');
    const continueBtn = core.$('btn-roleplay-v2-scene-continue');
    const inputStyleShell = core.$('roleplay-v2-scene-turn-input-style-shell');
    const roleplayEligible = roleplayChoiceAssistEligible();
    if (inputStyleShell) inputStyleShell.classList.toggle('hidden', !roleplayEligible);
    if (novelAuthoringSceneActive()) {
      ensureNovelAuthoringSceneDefaults();
      if (setupNote) setupNote.textContent = 'Authoring lane. Scene loads a Scene packet, keeps chapter continuity anchored, and helps you continue or shape prose without slipping back into roleplay framing.';
      if (brief) brief.classList.remove('hidden');
      if (premiseLabel) premiseLabel.textContent = 'Chapter / scene brief';
      if (premise) premise.placeholder = 'Chapter 7 · Section 2. POV: Mara. Goal: push the confession closer without resolving it.';
      if (notesLabel) notesLabel.textContent = 'Author notes';
      if (notes) notes.placeholder = 'POV guardrails, tense, sequence reminders, continuity notes, or revision instructions.';
      if (chatNote) chatNote.textContent = 'Drafting / continuation lane using the active Scene packet plus explicit scene state.';
      if (inputLabel) inputLabel.textContent = 'Author input';
      if (input) input.placeholder = 'Write the next prose beat, revision instruction, or continuation note.';
      if (sendBtn) sendBtn.textContent = 'Draft next beat';
      if (continueBtn) continueBtn.textContent = 'Continue draft';
      renderSceneChoiceAssist();
      return;
    }
    if (setupNote) setupNote.textContent = 'Live use lane. Scene loads a Studio-built Scene packet, tracks scene state, and hands checkpoints off to Stories.';
    if (brief) brief.classList.add('hidden');
    if (premiseLabel) premiseLabel.textContent = 'Scene premise';
    if (premise) premise.placeholder = 'Late-night reunion in the harbor after the ban on magic.';
    if (notesLabel) notesLabel.textContent = 'Scene notes';
    if (notes) notes.placeholder = 'Stage direction, continuity notes, or what the Scene packet should emphasize.';
    if (chatNote) chatNote.textContent = 'Live roleplay and writing lane using the active Scene packet plus explicit scene state.';
    if (inputLabel) inputLabel.textContent = 'User input';
    if (input) input.placeholder = 'Type the next scene turn here.';
    if (sendBtn) sendBtn.textContent = 'Send scene turn';
    if (continueBtn) continueBtn.textContent = 'Continue scene';
    renderSceneChoiceAssist();
  }

  function roleplayChoiceAssistEligible() {
    const mode = core.currentModeSelection();
    return mode.output_preset === 'roleplay' && mode.interaction_mode === 'roleplay';
  }

  function clearSceneChoiceAssist() {
    state.sceneSuggestedActions = [];
    state.sceneLastBranchChoice = null;
  }

  function renderSceneChoiceAssist() {
    const shell = core.$('roleplay-v2-scene-choice-assist');
    const list = core.$('roleplay-v2-scene-choice-list');
    const note = core.$('roleplay-v2-scene-choice-assist-note');
    const badge = core.$('roleplay-v2-scene-choice-assist-badge');
    if (!shell || !list || !note || !badge) return;
    const inputStyle = currentTurnInputStyle();
    state.sceneTurnInputStyle = inputStyle;
    const eligible = roleplayChoiceAssistEligible();
    const active = eligible && inputStyle !== 'free_typing';
    shell.classList.toggle('hidden', !active);
    badge.textContent = !eligible ? 'Roleplay only' : (inputStyle === 'choice_assist' ? 'Choice assist' : inputStyle === 'hybrid' ? 'Hybrid' : 'Hidden');
    if (!eligible) {
      note.textContent = 'Choice assist only activates for output_preset=roleplay + interaction_mode=roleplay.';
      list.textContent = 'Choice assist is inactive for the current non-roleplay mode.';
      return;
    }
    if (!active) {
      note.textContent = 'Free typing is active. Suggested next actions stay hidden until you switch to Choice assist or Hybrid.';
      list.textContent = 'Free typing is active.';
      return;
    }
    note.textContent = inputStyle === 'choice_assist'
      ? 'Suggested next actions are primary here. Manual typing still works if you want to override them.'
      : 'Hybrid mode keeps both suggested next actions and manual typing visible.';
    const actions = Array.isArray(state.sceneSuggestedActions) ? state.sceneSuggestedActions : [];
    list.innerHTML = '';
    if (!actions.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'Suggested next actions will appear after the latest assistant reply.';
      list.appendChild(empty);
      return;
    }
    actions.forEach((action, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.style.display = 'grid';
      btn.style.gap = '4px';
      btn.style.textAlign = 'left';
      btn.innerHTML = `
        <span>${core.text(action.label) || `Choice ${idx + 1}`}</span>
        <span class="mini-note">${core.text(action.prompt)}</span>
      `;
      btn.addEventListener('click', async () => {
        try {
          await sendSceneTurn('reply', { forcedUserMessage: core.text(action.prompt), branchChoice: {
            id: core.text(action.id) || `choice_${idx + 1}`,
            label: core.text(action.label) || `Choice ${idx + 1}`,
            prompt: core.text(action.prompt),
            source: 'roleplay_choice_assist',
            tone: core.text(action.tone),
            intent: core.text(action.intent) || 'scene_turn',
          } });
        } catch (err) {
          core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error');
        }
      });
      list.appendChild(btn);
    });
  }

  function syncSceneTurnInputStyle() {
    const select = core.$('roleplay-v2-scene-turn-input-style');
    if (select && core.text(select.value) !== currentTurnInputStyle()) select.value = currentTurnInputStyle();
    renderSceneChoiceAssist();
  }

  function modeLockedBranchChoice(branchChoice = null) {
    const clean = branchChoice && typeof branchChoice === 'object' ? { ...branchChoice } : {};
    const mode = core.currentModeSelection();
    if (!Object.keys(clean).length) return {};
    clean.output_preset = mode.output_preset;
    clean.interaction_mode = mode.interaction_mode;
    clean.turn_input_style = currentTurnInputStyle();
    return clean;
  }

  function sceneSuggestedActionsFromResponse(data = null) {
    const actions = Array.isArray(data?.suggested_actions) ? data.suggested_actions : [];
    state.sceneSuggestedActions = actions.map((action, idx) => ({
      id: core.text(action?.id) || `choice_${idx + 1}`,
      label: core.text(action?.label) || `Choice ${idx + 1}`,
      prompt: core.text(action?.prompt || action?.text),
      intent: core.text(action?.intent) || 'scene_turn',
      tone: core.text(action?.tone),
    })).filter(action => action.prompt);
    renderSceneChoiceAssist();
  }

  function sceneProjectId() {
    return core.text(state.activeRuntimeBundle?.project_id)
      || core.text(state.activeRuntimeBundle?.packet?.project_id)
      || core.text(state.selectedStoryline?.project_id);
  }

  function trimTo(value, limit = 120) {
    return core.text(value).slice(0, limit);
  }

  function inferStorylineTitle() {
    const premise = core.text(core.$('roleplay-v2-scene-premise')?.value);
    if (premise) return trimTo(premise.split(/[.!?\n]/)[0], 120) || 'Scene storyline';
    const focus = core.text(state.activeRuntimeBundle?.packet?.entity_focus?.label) || core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id);
    if (focus) return trimTo(`${focus} storyline`, 120);
    const bundleId = core.text(state.activeRuntimeBundle?.id);
    if (bundleId) return trimTo(`Runtime ${bundleId} storyline`, 120);
    return 'Scene storyline';
  }

  function buildCheckpointTitle(session = null) {
    const checkpointCount = Array.isArray(session?.checkpoint_ids) ? session.checkpoint_ids.length : (Array.isArray(state.selectedSession?.checkpoint_ids) ? state.selectedSession.checkpoint_ids.length : 0);
    const base = trimTo(core.$('roleplay-v2-scene-premise')?.value || state.selectedStoryline?.title || inferStorylineTitle(), 90);
    return `${base || 'Scene'} — checkpoint ${checkpointCount + 1}`;
  }

  function buildCheckpointSummary() {
    const premise = core.text(core.$('roleplay-v2-scene-premise')?.value);
    const notes = core.text(core.$('roleplay-v2-scene-notes')?.value);
    const latestAssistant = [...(state.sceneTranscript || [])].reverse().find(item => item?.role === 'assistant');
    const parts = [premise, notes ? `Notes: ${notes}` : '', latestAssistant?.content ? `Latest beat: ${core.text(latestAssistant.content).slice(0, 240)}` : ''].filter(Boolean);
    return trimTo(parts.join('\n'), 4000);
  }

  function linkedScenarioIdsFromScene(sceneState) {
    const scenarioId = core.text(sceneState?.active_scenario_id);
    return scenarioId ? [scenarioId] : [];
  }

  function linkedEntityIdsFromScene(sceneState) {
    return Array.isArray(sceneState?.cast_entity_ids) ? sceneState.cast_entity_ids : [];
  }


  function currentTranscriptUserTurns() {
    return (state.sceneTranscript || []).filter(item => item?.role === 'user').length;
  }

  function clearSceneContinuityRefreshLoop() {
    if (state.sceneContinuityRefreshHandle) {
      window.clearInterval(state.sceneContinuityRefreshHandle);
      state.sceneContinuityRefreshHandle = null;
    }
  }

  function renderAutosaveStatus() {
    const badge = core.$('roleplay-v2-scene-autosave-badge');
    const note = core.$('roleplay-v2-scene-autosave-note');
    const toggle = core.$('roleplay-v2-scene-autosave-toggle');
    if (toggle) toggle.checked = !!state.sceneAutosaveEnabled;
    const hasBinding = core.text(state.selectedStorylineId) && core.text(state.selectedSessionId);
    const label = state.sceneAutosaveEnabled
      ? (hasBinding ? `Autosave on · every live turn` : 'Autosave waiting for storyline/session')
      : 'Autosave off';
    state.sceneAutosaveStatus = label;
    if (badge) badge.textContent = label;
    if (note) {
      note.textContent = state.sceneAutosaveEnabled
        ? (hasBinding
          ? 'Live scene turns will silently save checkpoints into the bound session and refresh continuity restore state on the loop.'
          : 'Autosave is enabled, but Scene needs a bound storyline + session before silent checkpoint saves can happen.')
        : 'When enabled, Scene will silently save fresh checkpoints for the bound session and refresh continuity restore state.';
    }
  }

  async function refreshSceneSessionContinuity({ silent = true } = {}) {
    const storylineId = core.text(state.selectedStorylineId);
    const sessionId = core.text(state.selectedSessionId);
    if (!(storylineId && sessionId)) {
      renderAutosaveStatus();
      return null;
    }
    const query = new URLSearchParams();
    query.set('storyline_id', storylineId);
    query.set('session_id', sessionId);
    if (core.text(state.selectedCheckpointId)) query.set('checkpoint_id', core.text(state.selectedCheckpointId));
    const data = await core.getJson(`/api/roleplay/v2/story-resume?${query.toString()}`);
    const resume = data.resume || {};
    state.storyResumePreview = data || state.storyResumePreview;
    const continuitySnapshot = resume.continuity_snapshot || {};
    const mergeTrace = resume.resume_merge_trace || {};
    state.sceneContinuity = Object.assign({}, state.sceneContinuity || {}, resume.continuity_payload || {}, {
      runtime_bundle_id: core.text(resume.runtime_bundle_id) || core.text(state.sceneContinuity?.runtime_bundle_id),
      project_id: core.text(data.storyline?.project_id) || sceneProjectId(),
      focus_label: core.text(state.activeRuntimeBundle?.packet?.entity_focus?.label) || core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id) || core.text(state.sceneContinuity?.focus_label),
      transcript_turns: currentTranscriptUserTurns(),
      continuity_snapshot: continuitySnapshot,
      resume_merge_trace: mergeTrace,
      state_note: silent ? 'Session continuity refresh loop synced the latest checkpoint restore state.' : 'Scene continuity refreshed from the active storyline/session restore payload.',
      scene_state: state.sceneState || {},
    });
    renderSceneContinuity();
    renderAutosaveStatus();
    if (!silent) {
      core.setStatus('roleplay-v2-scene-send-status', 'Scene continuity refreshed from the current storyline/session checkpoint state.', 'success');
      core.setOutput(data);
    }
    return data;
  }

  async function maybeAutosaveSceneTurn({ silent = true, force = false } = {}) {
    if (!state.sceneAutosaveEnabled) {
      renderAutosaveStatus();
      return null;
    }
    const storylineId = core.text(state.selectedStorylineId);
    const sessionId = core.text(state.selectedSessionId);
    if (!(storylineId && sessionId)) {
      renderAutosaveStatus();
      return null;
    }
    const currentTurns = currentTranscriptUserTurns();
    if (!force && currentTurns <= Number(state.sceneAutosaveLastTranscriptLength || 0)) {
      renderAutosaveStatus();
      return null;
    }
    const data = await saveSceneCheckpoint({ storylineId, sessionId, silent });
    state.sceneAutosaveLastTranscriptLength = currentTurns;
    state.sceneAutosaveLastCheckpointId = core.text(data?.checkpoint?.id);
    await refreshSceneSessionContinuity({ silent: true }).catch(() => null);
    renderAutosaveStatus();
    return data;
  }

  function restartSceneContinuityRefreshLoop() {
    clearSceneContinuityRefreshLoop();
    if (!state.sceneAutosaveEnabled) {
      renderAutosaveStatus();
      return;
    }
    state.sceneContinuityRefreshHandle = window.setInterval(() => {
      refreshSceneSessionContinuity({ silent: true }).catch(() => null);
    }, Number(state.sceneAutosaveIntervalMs || 20000));
    renderAutosaveStatus();
  }

  function renderStoryBinding() {
    const storylineBadge = core.$('roleplay-v2-scene-storyline-badge');
    const sessionBadge = core.$('roleplay-v2-scene-session-badge');
    const saveBtn = core.$('btn-roleplay-v2-scene-save-checkpoint');
    if (storylineBadge) storylineBadge.textContent = core.text(state.selectedStoryline?.title) ? `Story · ${core.text(state.selectedStoryline.title)}` : 'No storyline bound · save will create one';
    if (sessionBadge) sessionBadge.textContent = core.text(state.selectedSession?.id) ? `Session · ${core.text(state.selectedSession.id)}` : 'No session bound';
    if (saveBtn) saveBtn.disabled = !!state.sceneBusy;
    renderAutosaveStatus();
  }

  function renderSceneStateSummary() {
    const panel = core.$('roleplay-v2-scene-state-summary');
    if (!panel) return;
    const sceneState = buildSceneStatePayload();
    const lines = [
      `Posture · ${core.text(sceneState.narrator_posture) || (novelAuthoringSceneActive() ? 'omniscient_narration' : 'partner_focus')}`,
      `Continuity · ${core.text(sceneState.continuity_mode) || 'runtime_anchored'}`,
      `Cast ids · ${(sceneState.cast_entity_ids || []).length}`,
      `Focus stack · ${(sceneState.focus_stack || []).join(', ') || 'none'}`,
    ];
    if (core.text(sceneState.active_world_id)) lines.push(`World · ${core.text(sceneState.active_world_id)}`);
    if (core.text(sceneState.active_scenario_id)) lines.push(`Scenario · ${core.text(sceneState.active_scenario_id)}`);
    if (core.text(sceneState.runtime_bundle_id)) lines.push(`Runtime bundle · ${core.text(sceneState.runtime_bundle_id)}`);
    if ((sceneState.memory_source_ids || []).length) lines.push(`Memory source ids · ${(sceneState.memory_source_ids || []).length}`);
    if ((sceneState.canon_guard_source_ids || []).length) lines.push(`Canon guard ids · ${(sceneState.canon_guard_source_ids || []).length}`);
    panel.textContent = lines.join('\n');
  }

  function sceneContinuityFilters() {
    return {
      bundle_id: core.text(state.activeRuntimeBundle?.id) || core.text(core.$('roleplay-v2-scene-runtime-select')?.value),
      project_id: sceneProjectId(),
      entity_id: core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id) || core.text(state.sceneState?.focus_stack?.[0]),
      source_ref: core.text(state.sceneContinuity?.writeback_source_ref) || core.text(state.sceneContinuity?.source_ref),
      origin: 'writeback',
    };
  }

  async function refreshWritebackDebugView({ silent = true } = {}) {
    const panel = core.$('roleplay-v2-scene-writeback-debug');
    if (!internalToolsEnabled()) {
      if (panel) panel.textContent = 'Turn-save debug rows stay hidden until internal tools are enabled.';
      return null;
    }
    const bundleId = core.text(state.activeRuntimeBundle?.id) || core.text(core.$('roleplay-v2-scene-runtime-select')?.value);
    const entityId = core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id) || core.text(state.sceneState?.focus_stack?.[0]);
    const projectId = sceneProjectId();
    const sourceRef = core.text(state.sceneContinuity?.writeback_source_ref) || core.text(state.sceneContinuity?.source_ref);
    if (!(bundleId || entityId || sourceRef)) {
      if (panel) panel.textContent = 'Turn-save debug rows will appear here after live turns persist summaries and continuity memory.';
      return null;
    }
    const turnsQs = `bundle_id=${encodeURIComponent(bundleId)}&project_id=${encodeURIComponent(projectId)}&entity_id=${encodeURIComponent(entityId)}&source_ref=${encodeURIComponent(sourceRef)}&limit=24`;
    const memoryQs = `bundle_id=${encodeURIComponent(bundleId)}&entity_id=${encodeURIComponent(entityId)}&source_ref=${encodeURIComponent(sourceRef)}&limit=24`;
    const [turns, memory] = await Promise.all([
      core.getJson(`/api/roleplay/v2/runtime/writeback-turn-summaries?${turnsQs}`),
      core.getJson(`/api/roleplay/v2/runtime/writeback-memory?${memoryQs}`),
    ]);
    const modeTotals = {};
    (turns.rows || []).forEach(row => {
      const modeKey = core.text(row.summary_payload?.mode_profile?.key) || core.text(row.mode) || 'roleplay';
      modeTotals[modeKey] = Number(modeTotals[modeKey] || 0) + 1;
    });
    const payload = {
      bundle_id: bundleId,
      project_id: projectId,
      entity_id: entityId,
      source_ref: sourceRef,
      mode_totals: modeTotals,
      turn_summaries: turns.rows || [],
      memory,
    };
    if (panel) panel.textContent = JSON.stringify(payload, null, 2);
    core.modules?.continuityControls?.refreshContext?.('scene', { silent: true }).catch(() => null);
    if (!silent) {
      core.setStatus('roleplay-v2-scene-send-status', `Writeback debug refreshed for ${bundleId || entityId || 'scene state'}.`, 'success');
      core.setOutput(payload);
    }
    return payload;
  }

  function renderWritebackEval() {
    const panel = core.$('roleplay-v2-scene-writeback-eval');
    if (!panel) return;
    panel.textContent = state.lastWritebackEval ? JSON.stringify(state.lastWritebackEval, null, 2) : 'Writeback mode eval will appear here after you run the inspector.';
  }

  async function runWritebackEval() {
    if (!internalToolsEnabled()) return null;
    const bundleId = core.text(state.activeRuntimeBundle?.id) || core.text(core.$('roleplay-v2-scene-runtime-select')?.value);
    const entityId = core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id) || core.text(state.sceneState?.focus_stack?.[0]);
    const projectId = sceneProjectId();
    const sourceRef = core.text(state.sceneContinuity?.writeback_source_ref) || core.text(state.sceneContinuity?.source_ref);
    const data = await core.getJson(`/api/roleplay/v2/runtime/writeback-eval?bundle_id=${encodeURIComponent(bundleId)}&project_id=${encodeURIComponent(projectId)}&entity_id=${encodeURIComponent(entityId)}&source_ref=${encodeURIComponent(sourceRef)}&limit=24`);
    state.lastWritebackEval = data;
    renderWritebackEval();
    core.setStatus('roleplay-v2-scene-send-status', `Writeback eval ready for ${core.text(bundleId) || 'scene bundle'}.`, 'success');
    core.setOutput(data);
    return data;
  }

  function renderSceneMeta() {
    const badge = core.$('roleplay-v2-scene-turn-meta-badge');
    const count = core.$('roleplay-v2-scene-transcript-count');
    if (count) {
      const userTurns = (state.sceneTranscript || []).filter(item => item.role === 'user').length;
      count.textContent = `${userTurns} turns`;
    }
    if (!badge) return;
    if (state.sceneBusy) {
      badge.textContent = 'Generating';
      return;
    }
    const meta = state.sceneTurnMeta || {};
    badge.textContent = core.text(meta.warning) || core.text(meta.finish_reason) || 'Ready';
  }

  function renderSceneContinuity() {
    const panel = core.$('roleplay-v2-scene-continuity-summary');
    const memoryPanel = core.$('roleplay-v2-scene-memory-preview');
    if (!panel) return;
    const continuity = state.sceneContinuity;
    if (!continuity) {
      panel.textContent = 'Continuity state will appear here once Scene is anchored to a loaded packet.';
      if (memoryPanel) memoryPanel.textContent = 'Recent continuity memory will appear here after live scene turns save back into V2 memory.';
      renderWritebackEval();
      return;
    }
    const lines = [
      `Runtime bundle · ${core.text(continuity.runtime_bundle_id) || 'none'}`,
      `Focus · ${core.text(continuity.focus_label) || 'none'}`,
      `Turns · ${Number(continuity.transcript_turns || 0)}`,
    ];
    if (core.text(continuity.retrieval_query)) lines.push(`Retrieval query · ${core.text(continuity.retrieval_query)}`);
    if (core.text(continuity.continuity_note)) lines.push(`Guard · ${core.text(continuity.continuity_note)}`);
    const writebackProfile = continuity.writeback_mode_profile || continuity.writeback?.mode_profile || {};
    const closedLoop = state.activeRuntimeBundle?.packet?.working_memory?.closed_loop_guardrails || {};
    const sessionPressure = state.activeRuntimeBundle?.packet?.working_memory?.session_pressure_profile || {};
    const saturation = state.activeRuntimeBundle?.packet?.working_memory?.saturation_guardrails || {};
    if (core.text(writebackProfile.key)) lines.push(`Writeback profile · ${core.text(writebackProfile.key)}${core.text(writebackProfile.focus) ? ` · ${core.text(writebackProfile.focus)}` : ''}`);
    if (sessionPressure?.focus_tags?.length) lines.push(`Session pressure · ${sessionPressure.focus_tags.join(', ')}`);
    if (closedLoop?.mode_drift_detected) lines.push(`Mode drift warning · ${core.text(closedLoop.dominant_writeback_mode) || 'recent writeback'} vs ${core.text(state.activeRuntimeBundle?.packet?.mode) || 'runtime mode'}`);
    if (saturation?.warnings?.length) lines.push(`Saturation guardrail · ${core.text(saturation.warnings[0])}`);
    (continuity.mode_lock_warnings || []).slice(0, 3).forEach(item => lines.push(`Mode lock guardrail · ${core.text(item)}`));
    if (core.text(continuity.state_note)) lines.push(`State · ${core.text(continuity.state_note)}`);
    if (core.text(continuity.scene_state_summary)) lines.push(`Scene state\n${core.text(continuity.scene_state_summary)}`);
    panel.textContent = lines.join('\n');
    renderSceneStateSummary();
    renderWritebackEval();
  }

  function renderSceneTranscript() {
    const panel = core.$('roleplay-v2-scene-transcript');
    if (!panel) return;
    const items = Array.isArray(state.sceneTranscript) ? state.sceneTranscript : [];
    if (!items.length) {
      panel.textContent = 'Scene transcript will render here once you start sending turns.';
      renderSceneMeta();
      return;
    }
    panel.innerHTML = '';
    items.forEach((item, index) => {
      const row = document.createElement('div');
      row.style.marginBottom = '12px';
      row.style.padding = '12px';
      row.style.border = item.role === 'assistant' ? '1px solid rgba(110,170,255,0.22)' : '1px solid rgba(255,255,255,0.06)';
      row.style.background = item.role === 'assistant' ? 'rgba(80,130,255,0.08)' : 'rgba(255,255,255,0.015)';
      row.style.borderRadius = '12px';
      const label = document.createElement('div');
      label.className = 'mini-note';
      label.style.marginBottom = '6px';
      const roleLabel = item.role === 'assistant' ? (novelAuthoringSceneActive() ? 'Draft continuation' : 'Scene reply') : item.role === 'system' ? 'System' : (novelAuthoringSceneActive() ? 'Author input' : 'You');
      label.textContent = `${roleLabel} · turn ${Math.ceil((index + 1) / 2)}`;
      const body = document.createElement('div');
      body.style.whiteSpace = 'pre-wrap';
      body.textContent = core.text(item.content);
      row.appendChild(label);
      row.appendChild(body);
      panel.appendChild(row);
    });
    panel.scrollTop = panel.scrollHeight;
    renderSceneMeta();
  }

  function renderActiveRuntimePreview() {
    const preview = core.$('roleplay-v2-scene-runtime-preview');
    const summary = core.$('roleplay-v2-scene-runtime-summary');
    if (!preview || !summary) return;
    const bundle = state.activeRuntimeBundle;
    if (!bundle) {
      summary.textContent = 'No Scene packet is active yet.';
      preview.textContent = 'Runtime preview will land here once you load a Studio-built bundle into Scene.';
      renderSceneMeta();
      renderSceneStateSummary();
      return;
    }
    const packet = bundle.packet || {};
    const blocks = packet.context_blocks || {};
    const sceneSeed = packet.scene_state_seed || {};
    summary.textContent = [
      `Bundle · ${core.text(bundle.id)}`,
      `Mode · ${core.text(bundle.mode)}${core.text(bundle.interaction_mode) ? ` / ${core.text(bundle.interaction_mode)}` : ''}`,
      `World · ${core.text(sceneSeed.active_world_id) || 'none'}`,
      `Focus stack · ${(sceneSeed.focus_stack || []).join(', ') || 'none'}`,
    ].join('\n');
    const parts = [
      `Bundle: ${core.text(bundle.id)}`,
      `Mode: ${core.text(bundle.mode)}${core.text(bundle.interaction_mode) ? ` / ${core.text(bundle.interaction_mode)}` : ''}`,
      `Narrator posture: ${core.text(sceneSeed.narrator_posture) || (novelAuthoringSceneActive() ? 'omniscient_narration' : 'partner_focus')}`,
      `Continuity mode: ${core.text(sceneSeed.continuity_mode) || 'runtime_anchored'}`,
      '',
      blocks.identity_block ? `IDENTITY\n${blocks.identity_block}` : '',
      blocks.relationship_block ? `\nRELATIONSHIPS\n${blocks.relationship_block}` : '',
      blocks.world_block ? `\nWORLD\n${blocks.world_block}` : '',
      blocks.episodic_block ? `\nEPISODIC\n${blocks.episodic_block}` : '',
      blocks.shared_block ? `\nSHARED\n${blocks.shared_block}` : '',
      blocks.guard_block ? `\nGUARDS\n${blocks.guard_block}` : '',
    ].filter(Boolean);
    preview.textContent = parts.join('\n');
    renderSceneMeta();
    renderSceneStateSummary();
  }

  async function loadRuntimeIntoScene(bundleId = '') {
    const cleanBundleId = core.text(bundleId || core.$('roleplay-v2-scene-runtime-select')?.value);
    if (!cleanBundleId) throw new Error('Select a Scene packet first.');
    const data = await core.getJson(`/api/roleplay/v2/runtime/bundle?bundle_id=${encodeURIComponent(cleanBundleId)}`);
    state.activeRuntimeBundle = data.bundle || null;
    state.sceneTurnMeta = null;
    clearSceneChoiceAssist();
    state.sceneState = Object.assign({}, state.activeRuntimeBundle?.packet?.scene_state_seed || {}, { runtime_bundle_id: cleanBundleId });
    core.applyModeSelection({ outputPreset: state.sceneState.output_preset, interactionMode: state.sceneState.interaction_mode, prefer: 'output' });
    if (core.$('roleplay-v2-scene-posture')) core.$('roleplay-v2-scene-posture').value = core.text(state.sceneState.narrator_posture) || (novelAuthoringSceneActive() ? 'omniscient_narration' : 'partner_focus');
    if (core.$('roleplay-v2-scene-continuity-mode')) core.$('roleplay-v2-scene-continuity-mode').value = core.text(state.sceneState.continuity_mode) || 'runtime_anchored';
    applySceneModeCopy();
    const continuityNote = state.sceneSessionBundleId && state.sceneTranscript.length && state.sceneSessionBundleId !== cleanBundleId
      ? 'The loaded Scene packet changed while this transcript already exists. Reset continuity if you want a clean re-anchor.'
      : 'Scene is aligned to the currently loaded packet.';
    state.sceneContinuity = {
      runtime_bundle_id: cleanBundleId,
      project_id: core.text(state.activeRuntimeBundle?.project_id) || core.text(state.activeRuntimeBundle?.packet?.project_id),
      focus_label: core.text(state.activeRuntimeBundle?.packet?.entity_focus?.label) || core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id),
      retrieval_query: core.text(state.activeRuntimeBundle?.packet?.working_memory?.retrieval_query),
      continuity_note: core.text(state.activeRuntimeBundle?.packet?.continuity_guard?.note),
      transcript_turns: Math.floor((state.sceneTranscript || []).length / 2),
      state_note: continuityNote,
      scene_state: state.sceneState,
      scene_state_summary: '',
    };
    renderActiveRuntimePreview();
    const packet = state.activeRuntimeBundle?.packet || {};
    if (!core.text(core.$('roleplay-v2-scene-premise')?.value)) {
      const firstMemory = packet.episodic_memories?.[0]?.text || packet.world_facts?.[0]?.text || '';
      if (core.$('roleplay-v2-scene-premise')) core.$('roleplay-v2-scene-premise').value = core.text(firstMemory);
    }
    if (core.$('roleplay-v2-scene-notes')) {
      const notes = [packet.working_memory?.retrieval_query ? `Runtime query: ${packet.working_memory.retrieval_query}` : '', packet.continuity_guard?.note || ''].filter(Boolean).join('\n');
      core.$('roleplay-v2-scene-notes').value = notes;
    }
    applySceneModeCopy();
    renderSceneTranscript();
    renderSceneMeta();
    renderSceneContinuity();
    syncSceneTurnInputStyle();
    renderStoryBinding();
    core.modules?.continuityControls?.refreshContext?.('scene', { silent: true }).catch(() => null);
    core.setStatus('roleplay-v2-scene-runtime-status', `Loaded Scene packet ${cleanBundleId} into the ${novelAuthoringSceneActive() ? 'authoring' : 'Scene'} lane.`, 'success');
    core.setOutput(data);
    return data;
  }

  async function sendSceneTurn(mode = 'reply', { forcedUserMessage = '', branchChoice = null } = {}) {
    const cleanMode = core.text(mode) || 'reply';
    const bundleId = core.text(core.$('roleplay-v2-scene-runtime-select')?.value) || core.text(state.activeRuntimeBundle?.id);
    const userMessage = cleanMode === 'continue' ? '' : core.text(forcedUserMessage || core.$('roleplay-v2-scene-user-input')?.value);
    if (!bundleId) throw new Error('Load a Scene packet into Scene first.');
    if (cleanMode === 'reply' && !userMessage) throw new Error(novelAuthoringSceneActive() ? 'Write the next prose beat or author direction before sending.' : 'Type a scene turn before sending.');
    setSceneBusy(true);
    core.setStatus('roleplay-v2-scene-send-status', cleanMode === 'continue' ? (novelAuthoringSceneActive() ? 'Continuing the authored draft from current continuity…' : 'Continuing the live scene from current continuity…') : (novelAuthoringSceneActive() ? 'Streaming the authored draft through the active text backend…' : 'Streaming the live scene turn through the active text backend…'), '');

    const branchChoicePayload = cleanMode === 'continue' ? {} : modeLockedBranchChoice(branchChoice || null);
    state.sceneLastBranchChoice = Object.keys(branchChoicePayload).length ? branchChoicePayload : null;

    const sharedSettings = core.modules?.studio?.getSharedGenerationSettings?.() || {};
    const sharedAuthorNotes = core.modules?.studio?.sharedAuthorNotesText?.() || '';
    const sceneStatePayload = buildSceneStatePayload();
    const baseTranscript = Array.isArray(state.sceneTranscript) ? state.sceneTranscript.map(item => ({ role: item.role, content: core.text(item.content) })) : [];
    let draftTranscript = baseTranscript.slice();
    if (cleanMode !== 'continue' && userMessage) draftTranscript.push({ role: 'user', content: userMessage });
    draftTranscript.push({ role: 'assistant', content: '' });
    state.sceneTranscript = draftTranscript;
    renderSceneTranscript();

    let assistantText = '';
    let finalPayload = null;
    streamController = new AbortController();
    try {
      const formData = new FormData();
      formData.append('bundle_id', bundleId);
      formData.append('user_message', userMessage);
      formData.append('transcript_json', JSON.stringify(baseTranscript));
      formData.append('scene_state_json', JSON.stringify(sceneStatePayload));
      formData.append('scene_premise', core.text(core.$('roleplay-v2-scene-premise')?.value));
      const mergedSceneNotes = [core.text(core.$('roleplay-v2-scene-notes')?.value), sharedAuthorNotes ? `Shared author notes:\n${sharedAuthorNotes}` : ''].filter(Boolean).join('\n\n');
      formData.append('scene_notes', mergedSceneNotes);
      formData.append('tone', core.text(core.$('roleplay-v2-scene-tone')?.value) || 'Warm tension');
      formData.append('style', core.text(core.$('roleplay-v2-scene-style')?.value) || 'Immersive dialogue');
      formData.append('output_preset', core.currentModeSelection().output_preset);
      formData.append('interaction_mode', core.currentModeSelection().interaction_mode);
      formData.append('storyline_id', core.text(state.selectedStorylineId));
      formData.append('session_id', core.text(state.selectedSessionId));
      formData.append('checkpoint_id', core.text(state.selectedCheckpointId));
      formData.append('mode', cleanMode);
      formData.append('turn_input_style', currentTurnInputStyle());
      formData.append('model', core.text(core.$('model-select')?.value) || 'default');
      formData.append('max_tokens', String(Number(sharedSettings.max_tokens || 320) || 320));
      formData.append('temperature', String(Number(sharedSettings.temperature || 0.82) || 0.82));
      formData.append('top_p', String(Number(sharedSettings.top_p || 0.92) || 0.92));
      formData.append('top_k', String(Number(sharedSettings.top_k || 60) || 60));

      const response = await fetch('/api/roleplay/v2/scene/turn-stream', {
        method: 'POST',
        body: formData,
        signal: streamController.signal,
        cache: 'no-store',
      });
      if (!response.ok) {
        let message = 'Scene request failed.';
        try { const data = await response.json(); message = data.error || data.message || message; } catch (_err) {}
        throw new Error(message);
      }
      const meta = await consumeSceneStream(response, {
        delta(data) {
          assistantText = core.text(data.text || `${assistantText}${data.delta || ''}`);
          draftTranscript[draftTranscript.length - 1] = { role: 'assistant', content: assistantText };
          state.sceneTranscript = draftTranscript.slice();
          renderSceneTranscript();
        },
        final(data) {
          finalPayload = data || null;
        },
        error(data) {
          throw new Error(data.error || 'Scene streaming failed.');
        },
      });

      if (!finalPayload) {
        if (!assistantText) throw new Error(meta?.stalled ? 'The live scene stream stalled before any visible output arrived.' : 'The live scene stream ended before any visible output arrived.');
        finalPayload = {
          ok: true,
          message: 'Recovered the visible scene reply after the stream ended unexpectedly.',
          reply_mode: cleanMode,
          reply_text: assistantText,
          transcript: draftTranscript,
          finish_reason: 'partial',
          reasoning_stripped: false,
          continuity: state.sceneContinuity || {},
          scene_state: sceneStatePayload,
          warning: meta?.stalled ? 'The live scene stream stalled, but the visible partial output was recovered. Continue to keep going.' : 'Recovered the visible scene reply after the stream ended unexpectedly.',
          continuity_saved: {},
          writeback: {},
          turn_input_style: currentTurnInputStyle(),
          suggested_actions: [],
          suggested_actions_warning: '',
        };
      }

      state.sceneTranscript = Array.isArray(finalPayload.transcript) ? finalPayload.transcript : draftTranscript;
      state.sceneSessionBundleId = bundleId;
      state.sceneTurnMeta = { finish_reason: core.text(finalPayload.finish_reason), warning: core.text(finalPayload.warning), reply_mode: core.text(finalPayload.reply_mode) };
      state.sceneContinuity = Object.assign({}, finalPayload.continuity || {}, { writeback: finalPayload.writeback || {}, state_note: core.text(finalPayload.warning) || 'Scene continuity updated from the latest live turn.' });
      state.sceneState = finalPayload.scene_state || state.sceneState;
      sceneSuggestedActionsFromResponse(finalPayload);
      applySceneModeCopy();
      if (cleanMode !== 'continue' && core.$('roleplay-v2-scene-user-input')) core.$('roleplay-v2-scene-user-input').value = '';
      renderSceneTranscript();
      renderSceneContinuity();
      refreshWritebackDebugView();
      renderStoryBinding();
      if (state.sceneAutosaveEnabled && core.text(finalPayload.reply_text || '')) {
        await maybeAutosaveSceneTurn({ silent: true }).catch(err => {
          state.sceneAutosaveStatus = `Autosave error · ${core.text(err?.message || err) || 'unknown'}`;
          renderAutosaveStatus();
        });
      }
      core.setStatus('roleplay-v2-scene-send-status', finalPayload.warning || finalPayload.message || 'Scene turn ready.', finalPayload.warning ? 'warning' : 'success');
      core.setOutput(finalPayload);
      return finalPayload;
    } catch (err) {
      if (assistantText) {
        draftTranscript[draftTranscript.length - 1] = { role: 'assistant', content: assistantText };
        state.sceneTranscript = draftTranscript.slice();
        state.sceneTurnMeta = { finish_reason: 'partial', warning: core.text(err?.message || err), reply_mode: cleanMode };
        renderSceneTranscript();
        core.setStatus('roleplay-v2-scene-send-status', core.text(err?.message || err) || 'Scene request failed.', 'warning');
      } else {
        state.sceneTranscript = baseTranscript;
        renderSceneTranscript();
        core.setStatus('roleplay-v2-scene-send-status', core.text(err?.message || err) || 'Scene request failed.', 'error');
      }
      throw err;
    } finally {
      streamController = null;
      setSceneBusy(false);
      renderSceneMeta();
      renderStoryBinding();
    }
  }


  function clearSceneTranscript() {
    state.sceneTranscript = [];
    state.sceneTurnMeta = null;
    state.sceneSessionBundleId = '';
    clearSceneChoiceAssist();
    state.sceneAutosaveLastTranscriptLength = 0;
    state.sceneAutosaveLastCheckpointId = '';
    state.sceneContinuity = state.activeRuntimeBundle ? {
      runtime_bundle_id: core.text(state.activeRuntimeBundle.id),
      project_id: core.text(state.activeRuntimeBundle.project_id) || core.text(state.activeRuntimeBundle.packet?.project_id),
      focus_label: core.text(state.activeRuntimeBundle.packet?.entity_focus?.label) || core.text(state.activeRuntimeBundle.packet?.entity_focus?.id),
      retrieval_query: core.text(state.activeRuntimeBundle.packet?.working_memory?.retrieval_query),
      continuity_note: core.text(state.activeRuntimeBundle.packet?.continuity_guard?.note),
      transcript_turns: 0,
      state_note: 'Continuity reset. Scene is ready to anchor fresh turns to the active Scene packet.',
      scene_state: buildSceneStatePayload(),
      scene_state_summary: '',
    } : null;
    applySceneModeCopy();
    renderSceneTranscript();
    renderSceneContinuity();
    refreshWritebackDebugView();
    renderStoryBinding();
    core.setStatus('roleplay-v2-scene-send-status', 'Scene transcript cleared in the V2 bridge lane.', 'success');
  }

  async function createStorySessionForStoryline(storylineId, sceneState) {
    const data = await core.postForm('/api/roleplay/v2/story-session/create', {
      storyline_id: core.text(storylineId),
      project_id: sceneProjectId(),
      continuity_mode: core.text(sceneState?.continuity_mode) || 'runtime_anchored',
      seed_runtime_bundle_id: core.text(state.activeRuntimeBundle?.id),
      output_preset: core.currentModeSelection().output_preset,
      interaction_mode: core.currentModeSelection().interaction_mode,
      scene_state_seed_json: JSON.stringify(sceneState || {}),
      session_summary: buildCheckpointSummary(),
    });
    return data;
  }

  async function refreshStoriesSelection(storylineId, preferredSessionId = '', preferredCheckpointId = '') {
    if (core.modules.stories?.loadStorylineDetail) {
      await core.modules.stories.loadStorylineDetail(storylineId, { preserveSessionSelection: true, preferredSessionId, preferredCheckpointId, silent: true });
    } else if (core.modules.stories?.fetchStorylines) {
      await core.modules.stories.fetchStorylines({ preserveSelection: true });
    }
    renderStoryBinding();
  }

  async function saveSceneCheckpoint({ storylineId = '', sessionId = '', silent = false } = {}) {
    let targetStorylineId = core.text(storylineId || state.selectedStorylineId);
    if (!targetStorylineId) {
      const created = await createStorylineFromScene({ silent, switchToStories: false });
      return created || null;
    }
    const sceneState = buildSceneStatePayload();
    let targetSessionId = core.text(sessionId || state.selectedSessionId);
    if (!targetSessionId) {
      const sessionCreate = await createStorySessionForStoryline(targetStorylineId, sceneState);
      targetSessionId = core.text(sessionCreate.session?.id);
    }
    if (!targetSessionId) throw new Error('Unable to resolve a story session for checkpoint save.');

    const sessionForTitle = core.text(state.selectedSessionId) === targetSessionId ? state.selectedSession : { checkpoint_ids: [] };
    const parentCheckpointId = core.text(state.selectedSessionId) === targetSessionId ? core.text(state.selectedSession?.active_checkpoint_id) : '';
    const payload = {
      storyline_id: targetStorylineId,
      session_id: targetSessionId,
      title: buildCheckpointTitle(sessionForTitle),
      summary: buildCheckpointSummary(),
      checkpoint_type: 'live_save',
      transcript_json: JSON.stringify(state.sceneTranscript || []),
      scene_text: '',
      scene_state_json: JSON.stringify(sceneState),
      continuity_payload_json: JSON.stringify(state.sceneContinuity || {}),
      runtime_bundle_id: core.text(state.activeRuntimeBundle?.id),
      runtime_source_scope: 'runtime_bundle',
      runtime_source_id: core.text(state.activeRuntimeBundle?.id),
      selected_entity_ids_json: JSON.stringify(linkedEntityIdsFromScene(sceneState)),
      selected_memory_ids_json: JSON.stringify(Array.isArray(sceneState.memory_source_ids) ? sceneState.memory_source_ids : []),
      linked_scenario_ids_json: JSON.stringify(linkedScenarioIdsFromScene(sceneState)),
      linked_entity_ids_json: JSON.stringify(linkedEntityIdsFromScene(sceneState)),
      parent_checkpoint_id: parentCheckpointId,
      branch_label: '',
      branch_choice_json: JSON.stringify(modeLockedBranchChoice(state.sceneLastBranchChoice)),
    };

    const data = await core.postForm('/api/roleplay/v2/story-checkpoint/save', payload);
    const checkpointId = core.text(data.checkpoint?.id);
    state.sceneAutosaveLastCheckpointId = checkpointId;
    await refreshStoriesSelection(targetStorylineId, targetSessionId, checkpointId);
    await refreshSceneSessionContinuity({ silent: true }).catch(() => null);
    core.setOutput(data);
    if (!silent) core.setStatus('roleplay-v2-scene-send-status', data.message || 'Checkpoint saved into Stories.', 'success');
    renderAutosaveStatus();
    return data;
  }

  async function createStorylineFromScene({ silent = false, switchToStories = true, title = '', summary = '', projectId = '', linkedWorldId = '', linkedUniverseId = '', linkedScenarioIds = null, linkedEntityIds = null, continuityPolicy = '' } = {}) {
    const sceneState = buildSceneStatePayload();
    const defaultTitle = inferStorylineTitle();
    const resolvedTitle = core.text(title) || defaultTitle;
    if (!resolvedTitle) return null;
    const storylineData = await core.postForm('/api/roleplay/v2/storyline/create', {
      title: resolvedTitle,
      summary: core.text(summary) || core.text(core.$('roleplay-v2-scene-premise')?.value),
      project_id: core.text(projectId) || sceneProjectId(),
      linked_world_id: core.text(linkedWorldId) || core.text(sceneState.active_world_id),
      linked_universe_id: core.text(linkedUniverseId),
      linked_scenario_ids_json: JSON.stringify(Array.isArray(linkedScenarioIds) ? linkedScenarioIds : linkedScenarioIdsFromScene(sceneState)),
      linked_entity_ids_json: JSON.stringify(Array.isArray(linkedEntityIds) ? linkedEntityIds : linkedEntityIdsFromScene(sceneState)),
      continuity_policy: core.text(continuityPolicy) || core.text(sceneState.continuity_mode) || 'runtime_anchored',
    });
    const storylineId = core.text(storylineData.storyline?.id);
    if (!storylineId) throw new Error('Storyline creation did not return an id.');
    const sessionData = await createStorySessionForStoryline(storylineId, sceneState);
    const sessionId = core.text(sessionData.session?.id);
    let checkpointId = '';
    if ((state.sceneTranscript || []).length || core.text(core.$('roleplay-v2-scene-premise')?.value) || core.text(state.activeRuntimeBundle?.id)) {
      const checkpointData = await saveSceneCheckpoint({ storylineId, sessionId, silent: true });
      checkpointId = core.text(checkpointData?.checkpoint?.id);
    } else {
      await refreshStoriesSelection(storylineId, sessionId, '');
    }
    if (switchToStories) core.setSubtab('stories');
    if (!silent) core.setStatus('roleplay-v2-scene-send-status', checkpointId ? 'Created storyline and saved the current Scene as the first checkpoint.' : 'Created storyline and bound the current Scene to a new story session.', 'success');
    return { storyline: storylineData.storyline, session: sessionData.session, checkpoint_id: checkpointId };
  }


  async function resumeFromStorySelection({ storylineId = '', sessionId = '', checkpointId = '' } = {}) {
    const query = new URLSearchParams();
    if (core.text(storylineId || state.selectedStorylineId)) query.set('storyline_id', core.text(storylineId || state.selectedStorylineId));
    if (core.text(sessionId || state.selectedSessionId)) query.set('session_id', core.text(sessionId || state.selectedSessionId));
    if (core.text(checkpointId || state.selectedCheckpointId)) query.set('checkpoint_id', core.text(checkpointId || state.selectedCheckpointId));
    const data = await core.getJson(`/api/roleplay/v2/story-resume?${query.toString()}`);
    const resume = data.resume || {};
    state.storyResumePreview = data || state.storyResumePreview;
    const runtimeBundleId = core.text(resume.runtime_bundle_id);
    if (runtimeBundleId) {
      await loadRuntimeIntoScene(runtimeBundleId);
      if (core.$('roleplay-v2-scene-runtime-select')) core.$('roleplay-v2-scene-runtime-select').value = runtimeBundleId;
    } else {
      state.activeRuntimeBundle = null;
      if (core.$('roleplay-v2-scene-runtime-select')) core.$('roleplay-v2-scene-runtime-select').value = '';
    }
    state.selectedStoryline = data.storyline || state.selectedStoryline;
    state.selectedStorylineId = core.text(data.storyline?.id) || core.text(state.selectedStorylineId);
    state.selectedSession = data.session || state.selectedSession;
    state.selectedSessionId = core.text(data.session?.id) || core.text(state.selectedSessionId);
    state.selectedCheckpoint = data.checkpoint || state.selectedCheckpoint;
    state.selectedCheckpointId = core.text(data.checkpoint?.id) || core.text(state.selectedCheckpointId);
    core.applyModeSelection({ outputPreset: resume.output_preset, interactionMode: resume.interaction_mode, prefer: 'output' });
    state.sceneTranscript = Array.isArray(resume.transcript) ? resume.transcript : [];
    state.sceneState = resume.scene_state || {};
    clearSceneChoiceAssist();
    state.sceneSessionBundleId = runtimeBundleId;
    state.sceneTurnMeta = { finish_reason: 'resume', warning: '', reply_mode: 'resume' };
    if (core.$('roleplay-v2-scene-premise')) core.$('roleplay-v2-scene-premise').value = core.text(state.sceneState.scene_goal) || core.text(data.storyline?.summary) || core.text(data.checkpoint?.summary);
    if (core.$('roleplay-v2-scene-notes')) core.$('roleplay-v2-scene-notes').value = core.text(state.sceneState.scene_notes) || core.text(data.checkpoint?.summary) || core.text((resume.continuity_payload || {}).continuity_note);
    if (core.$('roleplay-v2-scene-posture')) core.$('roleplay-v2-scene-posture').value = core.text(state.sceneState.narrator_posture) || (novelAuthoringSceneActive() ? 'omniscient_narration' : 'partner_focus');
    if (core.$('roleplay-v2-scene-continuity-mode')) core.$('roleplay-v2-scene-continuity-mode').value = core.text(state.sceneState.continuity_mode) || 'runtime_anchored';
    state.sceneContinuity = Object.assign({}, resume.continuity_payload || {}, {
      runtime_bundle_id: runtimeBundleId,
      project_id: core.text(data.storyline?.project_id) || sceneProjectId(),
      focus_label: core.text(state.activeRuntimeBundle?.packet?.entity_focus?.label) || core.text(state.activeRuntimeBundle?.packet?.entity_focus?.id),
      retrieval_query: core.text(state.activeRuntimeBundle?.packet?.working_memory?.retrieval_query) || core.text((resume.continuity_payload || {}).retrieval_query),
      continuity_note: core.text((resume.continuity_payload || {}).continuity_note) || core.text(state.activeRuntimeBundle?.packet?.continuity_guard?.note),
      transcript_turns: (state.sceneTranscript || []).filter(item => item?.role === 'user').length,
      state_note: 'Scene resumed from Stories.',
      mode_lock_warnings: Array.isArray(resume.mode_lock_warnings) ? resume.mode_lock_warnings : [],
      scene_state: state.sceneState,
      scene_state_summary: '',
    });
    if (core.$('roleplay-v2-scene-user-input')) core.$('roleplay-v2-scene-user-input').value = '';
    state.sceneAutosaveLastTranscriptLength = currentTranscriptUserTurns();
    state.sceneAutosaveLastCheckpointId = core.text(data.checkpoint?.id);
    renderActiveRuntimePreview();
    renderSceneTranscript();
    renderSceneContinuity();
    syncSceneTurnInputStyle();
    renderStoryBinding();
    core.modules?.continuityControls?.refreshContext?.('scene', { silent: true }).catch(() => null);
    core.setSubtab('scene');
    core.setStatus('roleplay-v2-scene-send-status', `Resumed Scene from ${core.text(data.checkpoint?.title) || core.text(data.storyline?.title) || 'Stories'}.`, 'success');
    core.refreshUserPathGuide?.();
    core.setOutput(data);
    return data;
  }

  async function boot() {
    core.$('btn-roleplay-v2-scene-runtime-refresh')?.addEventListener('click', async () => {
      try { await core.refreshRoleplayV2RuntimeBundles(); core.setStatus('roleplay-v2-scene-runtime-status', 'Runtime bundles refreshed for the active project.', 'success'); } catch (err) { core.setStatus('roleplay-v2-scene-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-runtime-load')?.addEventListener('click', async () => {
      try { await loadRuntimeIntoScene(); } catch (err) { core.setStatus('roleplay-v2-scene-runtime-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-send-bridge')?.addEventListener('click', async () => {
      try { await sendSceneTurn('reply'); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-continue')?.addEventListener('click', async () => {
      try { await sendSceneTurn('continue'); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-clear-transcript')?.addEventListener('click', clearSceneTranscript);
    core.$('btn-roleplay-v2-scene-create-storyline')?.addEventListener('click', async () => {
      try { await createStorylineFromScene(); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-save-checkpoint')?.addEventListener('click', async () => {
      try { await saveSceneCheckpoint(); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-refresh-session-continuity')?.addEventListener('click', async () => {
      try { await refreshSceneSessionContinuity({ silent: false }); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('roleplay-v2-scene-autosave-toggle')?.addEventListener('change', event => {
      state.sceneAutosaveEnabled = !!event.target?.checked;
      restartSceneContinuityRefreshLoop();
      renderAutosaveStatus();
    });
    core.$('roleplay-v2-scene-turn-input-style')?.addEventListener('change', event => {
      state.sceneTurnInputStyle = core.text(event.target?.value) || 'free_typing';
      renderSceneChoiceAssist();
    });
    core.$('roleplay-v2-scene-user-input')?.addEventListener('keydown', async event => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        try { await sendSceneTurn('reply'); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
      }
    });
    core.$('roleplay-v2-scene-posture')?.addEventListener('change', renderSceneStateSummary);
    core.$('roleplay-v2-scene-continuity-mode')?.addEventListener('change', renderSceneStateSummary);
    core.$('roleplay-v2-output-preset')?.addEventListener('change', () => { applySceneModeCopy(); syncSceneTurnInputStyle(); renderSceneStateSummary(); });
    core.$('roleplay-v2-interaction-mode')?.addEventListener('change', () => { applySceneModeCopy(); syncSceneTurnInputStyle(); renderSceneStateSummary(); });
    core.$('btn-roleplay-v2-scene-writeback-refresh')?.addEventListener('click', async () => {
      try { await refreshWritebackDebugView({ silent: false }); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.$('btn-roleplay-v2-scene-writeback-eval')?.addEventListener('click', async () => {
      try { await runWritebackEval(); } catch (err) { core.setStatus('roleplay-v2-scene-send-status', err.message || String(err), 'error'); }
    });
    core.modules?.continuityControls?.registerContext?.('scene', {
      listId: 'roleplay-v2-continuity-scene-list',
      inspectorId: 'roleplay-v2-continuity-scene-inspector',
      statusId: 'roleplay-v2-continuity-scene-status',
      countId: 'roleplay-v2-continuity-scene-count',
      refreshButtonId: 'btn-roleplay-v2-continuity-scene-refresh',
      getFilters: sceneContinuityFilters,
      onSelect: row => {
        if (row && core.$('roleplay-v2-memory-control-id')) core.$('roleplay-v2-memory-control-id').value = core.text(row.memory_id || row.id);
      },
    });
    applySceneModeCopy();
    renderSceneTranscript();
    renderSceneStateSummary();
    renderStoryBinding();
    renderWritebackEval();
    renderAutosaveStatus();
    syncSceneTurnInputStyle();
    restartSceneContinuityRefreshLoop();
  }

  async function onInternalToolsToggle(enabled) {
    if (!enabled) return;
    renderWritebackEval();
    await refreshWritebackDebugView().catch(() => null);
  }

  core.registerModule('scene', {
    boot,
    loadRuntimeIntoScene,
    sendSceneTurn,
    clearSceneTranscript,
    renderStoryBinding,
    createStorylineFromScene,
    saveSceneCheckpoint,
    resumeFromStorySelection,
    refreshSceneSessionContinuity,
    maybeAutosaveSceneTurn,
    refreshWritebackDebugView,
    runWritebackEval,
    onInternalToolsToggle,
  });
})();
