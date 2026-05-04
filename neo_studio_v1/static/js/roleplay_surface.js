(function () {
  const STORAGE_KEY = 'neo-roleplay-surface-v1';
  let transcript = [];
  let lastReplyRequest = null;
  let activeStoryId = '';
  let activePartId = '';
  let autosaveTimer = null;
  let persistTimer = null;
  let lastPersistedPayload = '';
  let sceneCast = [];
  let streamController = null;
  let isStreaming = false;
  let lastFinishReason = '';
  let lastTruncated = false;
  let sessionStoryLinkedContext = {};
  let sessionPartLinkedContext = {};
  let sessionStoryLinkedContextText = '';
  let sessionPartLinkedContextText = '';
  let branchOptions = [];
  let branchChoiceHistory = [];
  const STREAM_FIRST_EVENT_TIMEOUT_MS = 90000;
  const STREAM_IDLE_TIMEOUT_MS = 20000;
  const ROLEPLAY_PRESET_DEFAULTS = {
    roleplay: { style: 'Immersive dialogue', max_tokens: 320, temperature: 0.82, top_p: 0.92, top_k: 60, meta: 'Roleplay keeps turns tighter and dialogue-first.' },
    short_story: { style: 'Dialogue with light narration', max_tokens: 520, temperature: 0.8, top_p: 0.92, top_k: 55, meta: 'Short Story stays scene-focused but leaves more room for fuller prose and author-guided beats.' },
    novel: { style: 'Novel-like prose', max_tokens: 760, temperature: 0.76, top_p: 0.92, top_k: 55, meta: 'Novel Mode opens the token budget for slower pacing, denser narration, and longer author-led continuations.' },
    cinematic: { style: 'Cinematic narration', max_tokens: 620, temperature: 0.8, top_p: 0.92, top_k: 55, meta: 'Cinematic Mode leans into atmosphere, body language, and visual beats with a roomier continuation window.' },
  };
  function normalizeMessages(messages) { return (Array.isArray(messages) ? messages : []).map(entry => ({ role: entry?.role === 'assistant' ? 'assistant' : 'user', content: String(entry?.content || '').trim() })).filter(entry => entry.content); }
  function ids() {
    return {
      scenario: $('roleplay-scenario'), userName: $('roleplay-user-name'), partnerName: $('roleplay-partner-name'), userCharacterId: $('roleplay-user-character-id'), partnerCharacterId: $('roleplay-partner-character-id'), worldId: $('roleplay-world-id'), scenarioId: $('roleplay-scenario-id'), tone: $('roleplay-tone'), customTone: $('roleplay-custom-tone'), customToneWrap: $('roleplay-custom-tone-wrap'), canonMode: $('roleplay-canon-mode'), outputPreset: $('roleplay-output-preset'), interactionMode: $('roleplay-interaction-mode'), inputIntent: $('roleplay-input-intent'), continuousSceneMode: $('roleplay-continuous-scene-mode'), storyMode: $('roleplay-story-mode'), branchOptionCount: $('roleplay-branch-option-count'), branchAllowCustom: $('roleplay-branch-allow-custom'), branchPanel: $('roleplay-branching-panel'), branchMeta: $('roleplay-branching-meta'), branchOptions: $('roleplay-branch-options'), branchCustomWrap: $('roleplay-branch-custom-wrap'), branchCustomInput: $('roleplay-branch-custom-input'), presetMeta: $('roleplay-preset-meta'), style: $('roleplay-style'), sceneNotes: $('roleplay-scene-notes'), memoryNotes: $('roleplay-memory-notes'), authorNote: $('roleplay-author-note'), storyScopeNotes: $('roleplay-story-scope-notes'), chapterScopeNotes: $('roleplay-chapter-scope-notes'), partScopeNotes: $('roleplay-part-scope-notes'), chapterIndex: $('roleplay-chapter-index'), chapterLabel: $('roleplay-chapter-label'), partIndex: $('roleplay-part-index'), beatFocus: $('roleplay-beat-focus'), activePov: $('roleplay-active-pov'), activeLocation: $('roleplay-active-location'), activeCastFocus: $('roleplay-active-cast-focus'), partObjective: $('roleplay-part-objective'), tensionLevel: $('roleplay-tension-level'), pacingTarget: $('roleplay-pacing-target'), maxTokens: $('roleplay-max-tokens'), temperature: $('roleplay-temperature'), topP: $('roleplay-top-p'), topK: $('roleplay-top-k'), userInput: $('roleplay-user-input'), userInputLabel: $('roleplay-user-input-label'), userInputHint: $('roleplay-user-input-hint'), transcript: $('roleplay-transcript'), transcriptCount: $('roleplay-transcript-count'), sceneCastList: $('roleplay-scene-cast-list')
    };
  }
  function cleanCast(items) {
    return (Array.isArray(items) ? items : []).map(item => ({
      character_id: trim(item?.character_id || ''),
      character_name: trim(item?.character_name || ''),
      scene_role: trim(item?.scene_role || 'supporting') || 'supporting',
      presence: trim(item?.presence || 'on_scene') || 'on_scene',
      notes: trim(item?.notes || ''),
    })).filter(item => item.character_id || item.character_name || item.notes);
  }
  function sceneCastFromDom() {
    const root = ids().sceneCastList;
    if (!root) return sceneCast.slice();
    return Array.from(root.querySelectorAll('[data-scene-cast-character]')).map(node => {
      const idx = node.getAttribute('data-index');
      const characterId = trim(node.value);
      const selectedText = trim(node.selectedOptions?.[0]?.textContent || '').replace(/\s+—.*$/, '');
      return {
        character_id: characterId,
        character_name: characterId ? selectedText : trim(root.querySelector(`[data-scene-cast-name][data-index="${idx}"]`)?.value),
        scene_role: trim(root.querySelector(`[data-scene-cast-role][data-index="${idx}"]`)?.value) || 'supporting',
        presence: trim(root.querySelector(`[data-scene-cast-presence][data-index="${idx}"]`)?.value) || 'on_scene',
        notes: trim(root.querySelector(`[data-scene-cast-notes][data-index="${idx}"]`)?.value),
      };
    }).filter(item => item.character_id || item.character_name || item.notes);
  }
  function characterOptionNodes(selected = '') {
    const current = trim(selected);
    const list = window.neoGetRoleplayLibraryStateSnapshot?.().characters || [];
    const opts = ['<option value="">Custom / none</option>'];
    list.forEach(item => {
      const id = trim(item?.id || '');
      opts.push(`<option value="${escapeHtml(id)}"${id === current ? ' selected' : ''}>${escapeHtml((item?.title || 'Character'))}</option>`);
    });
    return opts.join('');
  }
  function renderSceneCast() {
    const root = ids().sceneCastList;
    if (!root) return;
    root.innerHTML = '';
    sceneCast.forEach((entry, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'grid grid-4';
      wrap.style.gap = '10px';
      wrap.style.alignItems = 'end';
      wrap.innerHTML = `
        <div><label>Character</label><select data-scene-cast-character data-index="${index}">${characterOptionNodes(entry.character_id)}</select></div>
        <div><label>Custom name</label><input data-scene-cast-name data-index="${index}" type="text" value="${escapeHtml(entry.character_name || '')}" placeholder="Use only if not linking a saved character"/></div>
        <div><label>Scene role</label><select data-scene-cast-role data-index="${index}">${['pov','partner','lead','supporting','antagonist','narrator','npc','off_screen'].map(opt => `<option value="${opt}"${trim(entry.scene_role)===opt?' selected':''}>${opt.replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase())}</option>`).join('')}</select></div>
        <div><label>Presence</label><select data-scene-cast-presence data-index="${index}">${['on_scene','nearby','off_screen','mentioned_only'].map(opt => `<option value="${opt}"${trim(entry.presence)===opt?' selected':''}>${opt.replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase())}</option>`).join('')}</select></div>
        <div style="grid-column: span 3;"><label>Notes</label><input data-scene-cast-notes data-index="${index}" type="text" value="${escapeHtml(entry.notes || '')}" placeholder="Optional scene-specific note"/></div>
        <div class="row" style="gap:8px;"><button class="btn btn-small btn-danger" data-scene-cast-remove data-index="${index}" type="button">Remove</button></div>`;
      root.appendChild(wrap);
    });
    if (!sceneCast.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'No extra cast yet. Add characters here when the scene has more than the main two.';
      root.appendChild(empty);
    }
  }
  function normalizedProgressionFromElements(el) {
    const chapterIndex = Math.max(1, Number(el.chapterIndex?.value || 1));
    const partIndex = Math.max(1, Number(el.partIndex?.value || 1));
    const tension = trim(el.tensionLevel?.value || 'medium') || 'medium';
    const pacing = trim(el.pacingTarget?.value || 'steady') || 'steady';
    return {
      chapter_index: chapterIndex,
      chapter_label: trim(el.chapterLabel?.value || ''),
      part_index: partIndex,
      beat_focus: trim(el.beatFocus?.value || ''),
      active_pov: trim(el.activePov?.value || ''),
      active_location: trim(el.activeLocation?.value || ''),
      active_cast_focus: trim(el.activeCastFocus?.value || ''),
      part_objective: trim(el.partObjective?.value || ''),
      tension_level: tension,
      pacing_target: pacing,
    };
  }
  function progressionSummary(prog = {}) {
    const bits = [];
    const chapter = `Chapter ${prog.chapter_index || 1}${prog.chapter_label ? ` — ${prog.chapter_label}` : ''}`;
    bits.push(chapter);
    bits.push(`Part ${prog.part_index || 1}`);
    if (prog.beat_focus) bits.push(`Beat: ${prog.beat_focus}`);
    if (prog.active_pov) bits.push(`POV: ${prog.active_pov}`);
    if (prog.active_location) bits.push(`Location: ${prog.active_location}`);
    if (prog.active_cast_focus) bits.push(`Cast: ${prog.active_cast_focus}`);
    if (prog.part_objective) bits.push(`Objective: ${prog.part_objective}`);
    bits.push(`Tension: ${prog.tension_level || 'medium'}`);
    bits.push(`Pacing: ${(prog.pacing_target || 'steady').replace(/_/g, ' ')}`);
    return bits.join(' | ');
  }
  function suggestPartTitle(state = null) {
    const current = state || getState();
    const prog = current.progression || {};
    const chapterBits = [`Chapter ${prog.chapter_index || 1}`];
    if (prog.chapter_label) chapterBits.push(prog.chapter_label);
    const partBits = [`Part ${prog.part_index || 1}`];
    if (prog.beat_focus) partBits.push(prog.beat_focus);
    else if (prog.active_location) partBits.push(prog.active_location);
    return [...chapterBits, ...partBits].join(' · ');
  }
  function primePartTitleFromProgression(force = false) {
    const node = $('roleplay-part-title');
    if (!node) return '';
    if (!force && trim(node.value)) return trim(node.value);
    const suggested = suggestPartTitle();
    if (suggested) node.value = suggested;
    return suggested;
  }
  function normalizeBranchOptions(items) {
    return (Array.isArray(items) ? items : []).map((item, index) => ({
      id: trim(item?.id || `opt_${index + 1}`) || `opt_${index + 1}`,
      label: trim(item?.label || `Option ${index + 1}`) || `Option ${index + 1}`,
      text: trim(item?.text || ''),
    })).filter(item => item.text);
  }
  function normalizeBranchChoiceHistory(items) {
    return (Array.isArray(items) ? items : []).map(item => ({
      assistant_turn_index: Number(item?.assistant_turn_index || 0),
      choice_id: trim(item?.choice_id || ''),
      label: trim(item?.label || ''),
      text: trim(item?.text || ''),
      source: trim(item?.source || 'generated') || 'generated',
    })).filter(item => item.text);
  }
  function isBranchingMode(value) {
    return trim(value || '').toLowerCase() === 'branching';
  }
  function renderBranchOptions() {
    const el = ids();
    const branching = isBranchingMode(el.storyMode?.value || 'linear');
    if (el.branchPanel) el.branchPanel.style.display = branching ? '' : 'none';
    if (!branching) return;
    if (el.branchMeta) el.branchMeta.textContent = branchOptions.length ? `Generated ${branchOptions.length} clickable next-step choices for the current beat.` : 'Branching mode generates clickable next-step choices after the latest reply.';
    if (el.branchCustomWrap) el.branchCustomWrap.style.display = String(el.branchAllowCustom?.value || 'true') === 'true' ? '' : 'none';
    if (!el.branchOptions) return;
    if (!branchOptions.length) {
      el.branchOptions.innerHTML = '<div class="mini-note">No generated choices yet. Continue the scene or refresh choices after the latest reply.</div>';
      return;
    }
    el.branchOptions.innerHTML = branchOptions.map((option, index) => `<button class="btn" type="button" data-branch-choice-index="${index}"><strong>${escapeHtml(option.label)}</strong><div class="mini-note" style="margin-top:6px;">${escapeHtml(option.text)}</div></button>`).join('');
  }
  function renderRoleplayContinuityInspector(data = null) {
    const preview = $('roleplay-continuity-preview');
    const list = $('roleplay-continuity-item-list');
    const backendNote = $('roleplay-continuity-backend-note');
    const previewBtn = $('btn-roleplay-preview-continuity');
    const repairBtn = $('btn-roleplay-repair-continuity');
    const resetPartBtn = $('btn-roleplay-reset-part-continuity');
    const resetStoryBtn = $('btn-roleplay-reset-story-continuity');
    if (previewBtn) previewBtn.disabled = !activeStoryId && !activePartId;
    if (repairBtn) repairBtn.disabled = !activeStoryId && !activePartId;
    if (resetPartBtn) resetPartBtn.disabled = !activePartId;
    if (resetStoryBtn) resetStoryBtn.disabled = !activeStoryId;
    if (!preview || !list) return;
    if (!activeStoryId && !activePartId) {
      preview.value = '';
      preview.placeholder = 'Preview continuity memory for the active story / part.';
      list.innerHTML = '<div class="assistant-session-empty">Link a story or part first to inspect continuity memory.</div>';
      return;
    }
    const retrieval = data && typeof data === 'object' ? (data.retrieval_preview || {}) : {};
    if (backendNote) {
      const backend = data?.backend && typeof data.backend === 'object' ? data.backend : null;
      const active = Array.isArray(backend?.backends) ? backend.backends.find(item => String(item.key || '') === String(backend.active_backend || '')) : null;
      backendNote.textContent = active ? `${active.label}: ${active.description} ${active.needs_download ? 'May download model assets on first semantic use.' : 'No external model downloads.'}` : 'Embedding backend details will appear here.';
    }
    const retrievalItems = Array.isArray(retrieval.items) ? retrieval.items : [];
    const summaries = Array.isArray(data?.summaries) ? data.summaries : [];
    const recentChunks = Array.isArray(data?.recent_chunks) ? data.recent_chunks : [];
    const writes = Array.isArray(data?.recent_writes) ? data.recent_writes : [];
    preview.placeholder = 'Preview continuity memory for the active story / part.';
    preview.value = trim(retrieval.summary || '');
    const cards = [];
    summaries.slice(0, 3).forEach(item => {
      cards.push(`
        <div class="card-lite assistant-context-item">
          <div class="stat-title">${escapeHtml(String(item.summary_type || 'summary').replace(/_/g, ' '))}</div>
          <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.scope_type || '')}${item.scope_id ? ` · ${escapeHtml(item.scope_id)}` : ''}</div>
          <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.content || '').slice(0, 220))}${String(item.content || '').length > 220 ? '…' : ''}</div>
        </div>`);
    });
    retrievalItems.slice(0, 4).forEach(item => {
      const meta = item && typeof item === 'object' ? (item.metadata || {}) : {};
      const diag = item && typeof item === 'object' ? (item.diagnostics || {}) : {};
      cards.push(`
        <div class="card-lite assistant-context-item">
          <div class="stat-title">Retrieved ${escapeHtml(String(meta.chunk_type || 'memory').replace(/_/g, ' '))}</div>
          <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.source || 'memory')} · score ${Number(item.score || 0).toFixed(2)} · base ${Number(diag.base_score || 0).toFixed(2)} · scope ${Number(diag.scope_bonus || 0).toFixed(2)} · overlap ${Number(diag.overlap_bonus || 0).toFixed(2)}</div>
          <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.document || '').slice(0, 220))}${String(item.document || '').length > 220 ? '…' : ''}</div>
        </div>`);
    });
    if (!cards.length) {
      recentChunks.slice(0, 3).forEach(item => {
        cards.push(`
          <div class="card-lite assistant-context-item">
            <div class="stat-title">Saved ${escapeHtml(String(item.chunk_type || 'memory').replace(/_/g, ' '))}</div>
            <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.entity_type || '')}${item.updated_at ? ` · ${escapeHtml(item.updated_at)}` : ''}</div>
            <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.document || '').slice(0, 220))}${String(item.document || '').length > 220 ? '…' : ''}</div>
          </div>`);
      });
    }
    writes.slice(0, 2).forEach(item => {
      cards.push(`
        <div class="card-lite assistant-context-item">
          <div class="stat-title">Write log · ${escapeHtml(item.operation || '')}</div>
          <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.entity_type || '')}${item.created_at ? ` · ${escapeHtml(item.created_at)}` : ''}</div>
          <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(JSON.stringify(item.details || {}).slice(0, 220))}${JSON.stringify(item.details || {}).length > 220 ? '…' : ''}</div>
        </div>`);
    });
    list.innerHTML = cards.length ? cards.join('') : '<div class="assistant-session-empty">No continuity preview yet. Use Preview continuity to inspect what Neo would carry forward.</div>';
  }

  async function previewRoleplayContinuity(options = {}) {
    if (!activeStoryId && !activePartId) {
      renderRoleplayContinuityInspector(null);
      setStatus('roleplay-continuity-status', 'Link a story or part first.', 'warn');
      return null;
    }
    const q = trim(options.query || $('roleplay-user-input')?.value || '');
    const data = await safeFetchJson(`/api/roleplay/continuity-inspect?story_id=${encodeURIComponent(activeStoryId || '')}&part_id=${encodeURIComponent(activePartId || '')}&q=${encodeURIComponent(q)}`);
    renderRoleplayContinuityInspector(data);
    if (!options.quiet) {
      const dropped = Number(data?.retrieval_preview?.diagnostics?.dropped?.length || 0);
      const backend = String(data?.backend?.active_backend || 'hashing_local');
      setStatus('roleplay-continuity-status', `Continuity preview ready. ${Number(data?.retrieval_preview?.item_count || 0)} retrieved item(s) from ${Number(data?.retrieval_preview?.candidate_count || 0)} candidate(s), ${dropped} dropped by ranking rules. Backend: ${backend}.`, 'ok');
    }
    return data;
  }

  async function repairRoleplayContinuity() {
    setBusy('btn-roleplay-repair-continuity', true, 'Repairing...');
    try {
      const data = await safeFetchJson('/api/roleplay/continuity-repair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ story_id: activeStoryId || '', part_id: activePartId || '', q: trim($('roleplay-user-input')?.value || '') }),
      });
      renderRoleplayContinuityInspector(data);
      setStatus('roleplay-continuity-status', data.message || 'Roleplay continuity rebuilt.', 'ok');
    } finally {
      setBusy('btn-roleplay-repair-continuity', false);
    }
  }

  async function resetRoleplayContinuity(scopeType) {
    if (scopeType === 'story' && !activeStoryId) {
      setStatus('roleplay-continuity-status', 'No active story is linked yet.', 'warn');
      return;
    }
    if (scopeType === 'part' && !activePartId) {
      setStatus('roleplay-continuity-status', 'No active part is linked yet.', 'warn');
      return;
    }
    const btnId = scopeType === 'story' ? 'btn-roleplay-reset-story-continuity' : 'btn-roleplay-reset-part-continuity';
    setBusy(btnId, true, 'Resetting...');
    try {
      const data = await safeFetchJson('/api/roleplay/continuity-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope_type: scopeType, story_id: activeStoryId || '', part_id: activePartId || '', chunk_type: trim($('roleplay-continuity-chunk-type-filter')?.value || '') }),
      });
      renderRoleplayContinuityInspector(data);
      setStatus('roleplay-continuity-status', data.message || `Roleplay ${scopeType} continuity reset.`, 'ok');
    } finally {
      setBusy(btnId, false);
    }
  }

  function branchChoiceIntent(state) {
    return isAuthoringMode(state.interaction_mode || '') ? 'story_text' : 'in_scene_turn';
  }
  async function chooseBranchOption(option, source = 'generated') {
    const state = getState();
    if (!option?.text) return;
    branchChoiceHistory.push({
      assistant_turn_index: transcript.length - 1,
      choice_id: trim(option.id || ''),
      label: trim(option.label || ''),
      text: trim(option.text || ''),
      source,
    });
    if (ids().branchCustomInput) ids().branchCustomInput.value = '';
    persistState();
    await runRoleplay('reply', { user_message: option.text, input_intent: branchChoiceIntent(state), clear_input: true });
  }
  async function requestBranchOptions() {
    const state = getState();
    if (!isBranchingMode(state.story_mode || 'linear')) return;
    const last = transcript[transcript.length - 1];
    if (!last || last.role !== 'assistant' || !trim(last.content || '')) {
      renderBranchOptions();
      return;
    }
    const payload = new FormData();
    payload.append('model', currentModel());
    payload.append('scenario', state.scenario);
    payload.append('user_name', state.user_name);
    payload.append('partner_name', state.partner_name);
    payload.append('user_character_id', state.user_character_id || '');
    payload.append('partner_character_id', state.partner_character_id || '');
    payload.append('world_id', state.world_id || '');
    payload.append('scenario_id', state.scenario_id || '');
    payload.append('cast_json', JSON.stringify(state.cast_json || []));
    payload.append('tone', state.tone);
    payload.append('custom_tone', state.custom_tone || '');
    payload.append('style', state.style);
    payload.append('canon_mode', state.canon_mode || 'what_if');
    payload.append('output_preset', state.output_preset || 'roleplay');
    payload.append('interaction_mode', state.interaction_mode || 'roleplay');
    payload.append('scene_notes', state.scene_notes || '');
    payload.append('memory_notes', state.memory_notes || '');
    payload.append('author_note', state.author_note || '');
    payload.append('story_scope_notes', state.story_scope_notes || '');
    payload.append('chapter_scope_notes', state.chapter_scope_notes || '');
    payload.append('part_scope_notes', state.part_scope_notes || '');
    payload.append('chapter_index', String(state.chapter_index || 1));
    payload.append('chapter_label', state.chapter_label || '');
    payload.append('part_index', String(state.part_index || 1));
    payload.append('beat_focus', state.beat_focus || '');
    payload.append('active_pov', state.active_pov || '');
    payload.append('active_location', state.active_location || '');
    payload.append('active_cast_focus', state.active_cast_focus || '');
    payload.append('part_objective', state.part_objective || '');
    payload.append('tension_level', state.tension_level || 'medium');
    payload.append('pacing_target', state.pacing_target || 'steady');
    payload.append('story_linked_context_json', JSON.stringify(state.story_linked_context || {}));
    payload.append('part_linked_context_json', JSON.stringify(state.part_linked_context || {}));
    payload.append('story_linked_context_text', state.story_linked_context_text || '');
    payload.append('part_linked_context_text', state.part_linked_context_text || '');
    payload.append('story_id', activeStoryId || '');
    payload.append('part_id', activePartId || '');
    payload.append('transcript_json', JSON.stringify(state.transcript || []));
    payload.append('option_count', String(state.branch_option_count || 3));
    payload.append('allow_custom_option', String(!!state.branch_allow_custom_option));
    const data = await safeFetchJson('/api/roleplay-branch-options', { method: 'POST', body: payload });
    branchOptions = normalizeBranchOptions(data.options || []);
    renderBranchOptions();
    persistState();
  }
  async function refreshBranchChoicesAfterTurn() {
    const state = getState();
    if (!isBranchingMode(state.story_mode || 'linear')) {
      branchOptions = [];
      renderBranchOptions();
      persistState();
      return;
    }
    await requestBranchOptions();
  }
  async function closeCurrentPart() {
    const storyId = trim($('roleplay-story-id')?.value || activeStoryId || '');
    if (!storyId) { setStatus('roleplay-setup-status', 'Save a story card first so Neo knows where to file the part.', 'warn'); return; }
    if (!transcript.length) { setStatus('roleplay-setup-status', 'There is no active transcript to close into a part yet.', 'warn'); return; }
    primePartTitleFromProgression(true);
    if (typeof window.neoSaveCurrentSceneToPart !== 'function') { setStatus('roleplay-setup-status', 'Story manager is not ready yet.', 'warn'); return; }
    await window.neoSaveCurrentSceneToPart();
    setStatus('roleplay-setup-status', 'Current part saved. Start the next part when you are ready to shift the beat.', 'ok');
  }
  async function startNextPart() {
    const storyId = trim($('roleplay-story-id')?.value || activeStoryId || '');
    if (!storyId && transcript.length) {
      setStatus('roleplay-setup-status', 'Save the story card first so Neo can archive the current part before moving on.', 'warn');
      return;
    }
    if (storyId && transcript.length && typeof window.neoSaveCurrentSceneToPart === 'function') {
      primePartTitleFromProgression(true);
      await window.neoSaveCurrentSceneToPart();
    }
    const el = ids();
    const nextIndex = Math.max(1, Number(el.partIndex?.value || 1)) + 1;
    if (el.partIndex) el.partIndex.value = String(nextIndex);
    if (el.partScopeNotes) el.partScopeNotes.value = '';
    if (el.beatFocus) el.beatFocus.value = '';
    if (el.partObjective) el.partObjective.value = '';
    const partIdNode = $('roleplay-part-id');
    if (partIdNode) partIdNode.value = '';
    activePartId = '';
    transcript = [];
    lastReplyRequest = null;
    lastFinishReason = '';
    lastTruncated = false;
    primePartTitleFromProgression(true);
    renderTranscript();
    persistState();
    setStatus('roleplay-setup-status', `Moved to Part ${nextIndex}. The previous part was saved${storyId ? '' : ' if a story card was active'}.`, 'ok');
    setStatus('roleplay-chat-status', '');
  }

  function getState() {
    const el = ids();
    sceneCast = sceneCastFromDom();
    const pov = sceneCast.find(item => item.scene_role === 'pov') || sceneCast[0] || {};
    const partner = sceneCast.find(item => item.scene_role === 'partner') || sceneCast.find(item => item.scene_role === 'lead' && item !== pov) || sceneCast[1] || {};
    const userName = trim(pov.character_name || el.userName?.value || 'You');
    const partnerName = trim(partner.character_name || el.partnerName?.value || 'Scene partner');
    const userCharacterId = trim(pov.character_id || el.userCharacterId?.value || '');
    const partnerCharacterId = trim(partner.character_id || el.partnerCharacterId?.value || '');
    if (el.userName) el.userName.value = userName;
    if (el.partnerName) el.partnerName.value = partnerName;
    if (el.userCharacterId) el.userCharacterId.value = userCharacterId;
    if (el.partnerCharacterId) el.partnerCharacterId.value = partnerCharacterId;
    return {
      story_id: activeStoryId,
      part_id: activePartId,
      scenario: trim(el.scenario?.value || ''),
      user_name: userName,
      partner_name: partnerName,
      user_character_id: userCharacterId,
      partner_character_id: partnerCharacterId,
      world_id: trim(el.worldId?.value || ''),
      scenario_id: trim(el.scenarioId?.value || ''),
      tone: trim(el.tone?.value || ''),
      custom_tone: trim(el.customTone?.value || ''),
      canon_mode: trim(el.canonMode?.value || 'what_if'),
      output_preset: trim(el.outputPreset?.value || 'roleplay'),
      interaction_mode: trim(el.interactionMode?.value || 'roleplay'),
      input_intent: trim(el.inputIntent?.value || 'auto'),
      continuous_scene_mode: String(el.continuousSceneMode?.value || 'false') === 'true',
      story_mode: trim(el.storyMode?.value || 'linear'),
      branch_option_count: Math.max(2, Math.min(6, Number(el.branchOptionCount?.value || 3))),
      branch_allow_custom_option: String(el.branchAllowCustom?.value || 'true') === 'true',
      style: trim(el.style?.value || ''),
      scene_notes: trim(el.sceneNotes?.value || ''),
      memory_notes: trim(el.memoryNotes?.value || ''),
      author_note: trim(el.authorNote?.value || ''),
      story_scope_notes: trim(el.storyScopeNotes?.value || ''),
      chapter_scope_notes: trim(el.chapterScopeNotes?.value || ''),
      part_scope_notes: trim(el.partScopeNotes?.value || ''),
      progression: normalizedProgressionFromElements(el),
      chapter_index: Math.max(1, Number(el.chapterIndex?.value || 1)),
      chapter_label: trim(el.chapterLabel?.value || ''),
      part_index: Math.max(1, Number(el.partIndex?.value || 1)),
      beat_focus: trim(el.beatFocus?.value || ''),
      active_pov: trim(el.activePov?.value || ''),
      active_location: trim(el.activeLocation?.value || ''),
      active_cast_focus: trim(el.activeCastFocus?.value || ''),
      part_objective: trim(el.partObjective?.value || ''),
      tension_level: trim(el.tensionLevel?.value || 'medium'),
      pacing_target: trim(el.pacingTarget?.value || 'steady'),
      max_tokens: Number(el.maxTokens?.value || 320),
      temperature: Number(el.temperature?.value || 0.82),
      top_p: Number(el.topP?.value || 0.92),
      top_k: Number(el.topK?.value || 60),
      cast_json: sceneCast.slice(),
      story_linked_context: contextFromWindow('neoGetRoleplayStoryLinkedContext', sessionStoryLinkedContext),
      part_linked_context: contextFromWindow('neoGetRoleplayPartLinkedContext', sessionPartLinkedContext),
      story_linked_context_text: contextTextFromWindow('neoGetRoleplayStoryLinkedContextText', sessionStoryLinkedContextText),
      part_linked_context_text: contextTextFromWindow('neoGetRoleplayPartLinkedContextText', sessionPartLinkedContextText),
      branching: {
        story_mode: trim(el.storyMode?.value || 'linear'),
        option_count: Math.max(2, Math.min(6, Number(el.branchOptionCount?.value || 3))),
        allow_custom_option: String(el.branchAllowCustom?.value || 'true') === 'true',
        latest_options: branchOptions.slice(),
        choice_history: branchChoiceHistory.slice(),
      },
      transcript: transcript.slice(),
    };
  }
  function exportSessionState() { const el = ids(); const pendingEntry = [...transcript].reverse().find(entry => entry?.role === 'assistant' && entry?._streaming); const pendingReply = pendingEntry?.content || ''; return { ...getState(), user_input: trim(el.userInput?.value || ''), pending_reply: trim(pendingReply || ''), latest_finish_reason: lastFinishReason, truncated: !!lastTruncated, lastReplyRequest }; }
  async function pushAutosave() { try { const state = exportSessionState(); if (!state.scenario && !state.transcript.length && !state.user_input) return; const form = new FormData(); form.append('story_id', activeStoryId || ''); form.append('part_id', activePartId || ''); form.append('roleplay_state_json', JSON.stringify(state)); await safeFetchJson('/api/roleplay/session/autosave', { method: 'POST', body: form }); } catch (_err) {} }
  function scheduleAutosave() { window.clearTimeout(autosaveTimer); autosaveTimer = window.setTimeout(() => { pushAutosave(); }, 900); }
  function flushPersistState() { try { const payload = JSON.stringify(exportSessionState()); if (payload === lastPersistedPayload) { scheduleAutosave(); return; } lastPersistedPayload = payload; window.sessionStorage.setItem(STORAGE_KEY, payload); } catch (err) { console.warn('Could not persist roleplay state.', err); } scheduleAutosave(); }
  function persistState() { window.clearTimeout(persistTimer); persistTimer = window.setTimeout(flushPersistState, 140); }
  function syncCustomToneVisibility() { const el = ids(); const custom = String(el.tone?.value || '').trim().toLowerCase() === 'custom'; el.customToneWrap?.classList.toggle('hidden', !custom); }
  function isAuthoringMode(value) {
    return String(value || '').trim().toLowerCase() === 'authoring';
  }
  function resolvedInputIntent(mode, interactionMode, inputIntent) {
    const explicit = String(inputIntent || '').trim().toLowerCase();
    if (explicit && explicit !== 'auto') return explicit;
    if (isAuthoringMode(interactionMode)) return 'author_direction';
    return String(mode || 'reply').trim().toLowerCase() === 'reply' ? 'in_scene_turn' : 'auto';
  }
  function shouldAddUserTurnToTranscript(interactionMode, inputIntent) {
    const intent = String(inputIntent || '').trim().toLowerCase();
    if (intent === 'story_text' || intent === 'in_scene_turn') return true;
    if (!isAuthoringMode(interactionMode) && (intent === 'auto' || !intent)) return true;
    return false;
  }
  function normalizeLinkedContext(raw) {
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      const clean = {};
      Object.entries(raw).forEach(([key, value]) => {
        if (!Array.isArray(value)) return;
        const ids = value.map(item => trim(String(item || ''))).filter(Boolean);
        if (ids.length) clean[key] = [...new Set(ids)];
      });
      return clean;
    }
    return {};
  }
  function contextFromWindow(fnName, fallback = {}) {
    const fn = window[fnName];
    if (typeof fn !== 'function') return normalizeLinkedContext(fallback);
    const value = normalizeLinkedContext(fn() || {});
    return Object.keys(value).length ? value : normalizeLinkedContext(fallback);
  }
  function contextTextFromWindow(fnName, fallback = '') {
    const fn = window[fnName];
    const text = typeof fn === 'function' ? trim(fn() || '') : '';
    return text || trim(fallback || '');
  }
  function syncInteractionUi() {
    const el = ids();
    const authoring = isAuthoringMode(el.interactionMode?.value || '');
    const presetLabel = el.outputPreset?.selectedOptions?.[0]?.textContent || 'current mode';
    if (el.userInputLabel) el.userInputLabel.textContent = authoring ? 'Author guidance / next instruction' : 'Your next turn';
    if (el.userInputHint) {
      el.userInputHint.textContent = authoring
        ? `In Authoring mode, what you type is treated as direction for ${presetLabel} by default, not automatic in-scene dialogue.`
        : 'In Roleplay mode, your text is treated as the next in-scene turn.';
    }
    if (el.userInput) {
      el.userInput.placeholder = authoring
        ? 'Guide pacing, POV, beat focus, or scene direction here. Use Input intent if this should become story text instead.'
        : 'Type your reply here, then send it into the scene.';
    }
  }
  function syncPresetMeta() {
    const el = ids();
    const presetKey = String(el.outputPreset?.value || 'roleplay').trim();
    const preset = ROLEPLAY_PRESET_DEFAULTS[presetKey] || ROLEPLAY_PRESET_DEFAULTS.roleplay;
    const authoring = isAuthoringMode(el.interactionMode?.value || '');
    if (el.presetMeta) el.presetMeta.textContent = `${preset.meta || ''}${authoring ? ' Continue Scene stays open for author-guided continuation in this mode.' : ''}${isBranchingMode(el.storyMode?.value || 'linear') ? ' Branching mode will generate clickable next-step choices after each reply.' : ''}`.trim();
    syncInteractionUi();
    renderBranchOptions();
  }
  function roleLabel(role) { const el = ids(); return role === 'assistant' ? trim(el.partnerName?.value || 'Scene partner') : trim(el.userName?.value || 'You'); }
  function renderTranscript() {
    const el = ids(); if (!el.transcript) return; el.transcript.innerHTML = '';
    if (!transcript.length) { const empty = document.createElement('div'); empty.className = 'roleplay-empty-state'; empty.textContent = 'No scene turns yet. Set the premise, then hit Start scene or write the first line yourself.'; el.transcript.appendChild(empty); }
    else {
      transcript.forEach((entry, index) => {
        const bubble = document.createElement('article');
        bubble.className = `roleplay-message role-${entry.role}`;
        if (entry._streaming) bubble.classList.add('roleplay-message-streaming');
        bubble.dataset.index = String(index);
        bubble.dataset.role = entry.role;
        const meta = document.createElement('div');
        meta.className = 'roleplay-message-meta';
        meta.textContent = entry._streaming ? `${roleLabel(entry.role)} · streaming…` : roleLabel(entry.role);
        const body = document.createElement('div');
        body.className = 'roleplay-message-body';
        body.textContent = entry.content;
        bubble.append(meta, body);
        el.transcript.appendChild(bubble);
      });
    }
    if (el.transcriptCount) el.transcriptCount.textContent = `${transcript.length} ${transcript.length === 1 ? 'turn' : 'turns'}`;
    el.transcript.scrollTop = el.transcript.scrollHeight; setStreamUiState(); persistState();
  }
  function applySessionState(saved = {}, options = {}) {
    const el = ids(); activeStoryId = trim(saved.story_id || activeStoryId || ''); activePartId = trim(saved.part_id || activePartId || '');
    if (el.scenario) el.scenario.value = saved.scenario || '';
    if (el.userName) el.userName.value = saved.user_name || '';
    if (el.partnerName) el.partnerName.value = saved.partner_name || '';
    if (el.userCharacterId) el.userCharacterId.value = saved.user_character_id || '';
    if (el.partnerCharacterId) el.partnerCharacterId.value = saved.partner_character_id || '';
    if (el.worldId) el.worldId.value = saved.world_id || '';
    if (el.scenarioId) el.scenarioId.value = saved.scenario_id || '';
    if (el.tone) el.tone.value = saved.tone || 'Warm tension';
    if (el.style) el.style.value = saved.style || 'Immersive dialogue';
    if (el.customTone) el.customTone.value = saved.custom_tone || '';
    if (el.canonMode && saved.canon_mode) el.canonMode.value = saved.canon_mode;
    if (el.outputPreset && saved.output_preset) el.outputPreset.value = saved.output_preset;
    if (el.interactionMode) el.interactionMode.value = saved.interaction_mode || 'roleplay';
    if (el.inputIntent) el.inputIntent.value = saved.input_intent || 'auto';
    if (el.continuousSceneMode) el.continuousSceneMode.value = String(!!saved.continuous_scene_mode);
    if (el.storyMode) el.storyMode.value = saved.story_mode || saved.branching?.story_mode || 'linear';
    if (el.branchOptionCount) el.branchOptionCount.value = saved.branch_option_count ?? saved.branching?.option_count ?? 3;
    if (el.branchAllowCustom) el.branchAllowCustom.value = String(saved.branch_allow_custom_option ?? saved.branching?.allow_custom_option ?? true);
    if (el.storyMode) el.storyMode.value = saved.story_mode || saved.branching?.story_mode || 'linear';
    if (el.branchOptionCount) el.branchOptionCount.value = saved.branch_option_count ?? saved.branching?.option_count ?? 3;
    if (el.branchAllowCustom) el.branchAllowCustom.value = String(saved.branch_allow_custom_option ?? saved.branching?.allow_custom_option ?? true);
    if (el.sceneNotes) el.sceneNotes.value = saved.scene_notes || '';
    if (el.memoryNotes) el.memoryNotes.value = saved.memory_notes || '';
    if (el.authorNote) el.authorNote.value = saved.author_note || '';
    if (el.storyScopeNotes) el.storyScopeNotes.value = saved.story_scope_notes || '';
    if (el.chapterScopeNotes) el.chapterScopeNotes.value = saved.chapter_scope_notes || '';
    if (el.partScopeNotes) el.partScopeNotes.value = saved.part_scope_notes || '';
    if (el.chapterIndex) el.chapterIndex.value = saved.chapter_index ?? saved.progression?.chapter_index ?? 1;
    if (el.chapterLabel) el.chapterLabel.value = saved.chapter_label || saved.progression?.chapter_label || '';
    if (el.partIndex) el.partIndex.value = saved.part_index ?? saved.progression?.part_index ?? 1;
    if (el.beatFocus) el.beatFocus.value = saved.beat_focus || saved.progression?.beat_focus || '';
    if (el.activePov) el.activePov.value = saved.active_pov || saved.progression?.active_pov || '';
    if (el.activeLocation) el.activeLocation.value = saved.active_location || saved.progression?.active_location || '';
    if (el.activeCastFocus) el.activeCastFocus.value = saved.active_cast_focus || saved.progression?.active_cast_focus || '';
    if (el.partObjective) el.partObjective.value = saved.part_objective || saved.progression?.part_objective || '';
    if (el.tensionLevel) el.tensionLevel.value = saved.tension_level || saved.progression?.tension_level || 'medium';
    if (el.pacingTarget) el.pacingTarget.value = saved.pacing_target || saved.progression?.pacing_target || 'steady';
    if (el.maxTokens) el.maxTokens.value = saved.max_tokens ?? 320;
    if (el.temperature) el.temperature.value = saved.temperature ?? 0.82;
    if (el.topP) el.topP.value = saved.top_p ?? 0.92;
    if (el.topK) el.topK.value = saved.top_k ?? 60;
    if (el.userInput) el.userInput.value = saved.user_input || '';
    sceneCast = cleanCast(saved.cast_json || saved.scene_cast || []);
    sessionStoryLinkedContext = normalizeLinkedContext(saved.story_linked_context || {});
    sessionPartLinkedContext = normalizeLinkedContext(saved.part_linked_context || {});
    sessionStoryLinkedContextText = trim(saved.story_linked_context_text || '');
    sessionPartLinkedContextText = trim(saved.part_linked_context_text || '');
    branchOptions = normalizeBranchOptions(saved.branch_latest_options || saved.branching?.latest_options || []);
    branchChoiceHistory = normalizeBranchChoiceHistory(saved.branch_choice_history || saved.branching?.choice_history || []);
    branchOptions = normalizeBranchOptions(saved.branch_latest_options || saved.branching?.latest_options || []);
    branchChoiceHistory = normalizeBranchChoiceHistory(saved.branch_choice_history || saved.branching?.choice_history || []);
    renderSceneCast();
    transcript = normalizeMessages(saved.transcript);
    lastReplyRequest = saved.lastReplyRequest || null;
    lastFinishReason = trim(saved.latest_finish_reason || '');
    lastTruncated = !!saved.truncated;
    syncCustomToneVisibility(); syncPresetMeta(); syncInteractionUi(); renderTranscript(); renderBranchOptions();
    if (!options.silent) { setStatus('roleplay-setup-status', options.message || 'Roleplay session restored.', 'ok'); setStatus('roleplay-chat-status', ''); }
  }
  function loadState() { try { const raw = window.sessionStorage.getItem(STORAGE_KEY); if (!raw) return; applySessionState(JSON.parse(raw) || {}, { silent: true }); } catch (err) { console.warn('Could not load roleplay state.', err); } }
  function refreshBackendNote() {
    const textSession = typeof getRoleSession === 'function' ? getRoleSession('text') : { connected: false };
    if (typeof updateBackendRequiredNote === 'function') { updateBackendRequiredNote('roleplay-text-backend-note','roleplay-text-backend-note-body',!!textSession?.connected,'Text backend connected. Start scenes, continue turns, and in-character replies are ready.','Connect a Text Backend to start scenes, continue turns, and run in-character replies. Setup notes and transcript drafting still work offline.'); return; }
    const note = $('roleplay-text-backend-note'); const body = $('roleplay-text-backend-note-body'); if (!note || !body) return;
    note.classList.toggle('offline', !textSession?.connected); note.classList.toggle('connected', !!textSession?.connected);
    body.textContent = textSession?.connected ? 'Text backend connected. Start scenes, continue turns, and in-character replies are ready.' : 'Connect a Text Backend to start scenes, continue turns, and run in-character replies. Setup notes and transcript drafting still work offline.';
  }
  function setRoleplayBusy(busy, label = 'Thinking...') { setBusy('btn-roleplay-start-scene', busy, label); setBusy('btn-roleplay-continue-scene', busy, label); setBusy('btn-roleplay-send', busy, label); setBusy('btn-roleplay-regenerate', busy, label); }
  function setStreamUiState() {
    const stopBtn = $('btn-roleplay-stop');
    const continueBtn = $('btn-roleplay-continue-cutoff');
    if (stopBtn) stopBtn.disabled = !isStreaming;
    if (continueBtn) {
      continueBtn.disabled = isStreaming || !lastTruncated;
      continueBtn.classList.toggle('btn-primary', !isStreaming && !!lastTruncated);
    }
  }
  function setStreamActive(active) { isStreaming = !!active; setStreamUiState(); }
  function updateFinishState(finishReason = '') { lastFinishReason = trim(finishReason || ''); lastTruncated = lastFinishReason === 'length'; setStreamUiState(); }
  function ensureStreamingAssistantTurn() {
    const last = transcript[transcript.length - 1];
    if (last?.role === 'assistant' && last?._streaming) return transcript.length - 1;
    transcript.push({ role: 'assistant', content: '', _streaming: true });
    renderTranscript();
    return transcript.length - 1;
  }
  function updateStreamingAssistant(text) {
    const index = ensureStreamingAssistantTurn();
    transcript[index] = { ...transcript[index], role: 'assistant', content: trim(text || ''), _streaming: true };
    renderTranscript();
  }
  function finalizeStreamingAssistant(text = '') {
    const last = transcript[transcript.length - 1];
    if (last?.role !== 'assistant') return;
    if (last?.role === 'assistant' && last?._streaming) {
      transcript[transcript.length - 1] = { role: 'assistant', content: trim(text || last.content || '') };
      if (!transcript[transcript.length - 1].content) transcript.pop();
      renderTranscript();
    }
  }
  function discardStreamingAssistant() {
    const last = transcript[transcript.length - 1];
    if (last?.role === 'assistant' && last?._streaming) {
      transcript.pop();
      renderTranscript();
    }
  }
  function stopRoleplayStream() {
    if (streamController) streamController.abort();
  }
  function sanitizeRoleplayStreamText(text, partnerName = '') {
    let cleaned = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    cleaned = cleaned.replace(/<\s*\/?\s*(think|analysis|reasoning|thought|scratchpad)\b[^>]*>/gi, '');
    const prefixes = ['<', '</'];
    ['think', 'analysis', 'reasoning', 'thought', 'scratchpad'].forEach(tag => {
      for (let i = 1; i <= tag.length; i += 1) {
        prefixes.push(`<${tag.slice(0, i)}`);
        prefixes.push(`</${tag.slice(0, i)}`);
      }
    });
    const lowered = cleaned.toLowerCase();
    const lastLt = lowered.lastIndexOf('<');
    if (lastLt >= 0) {
      const tail = lowered.slice(lastLt).replace(/\s+/g, '');
      if (prefixes.some(prefix => prefix.startsWith(tail) || tail.startsWith(prefix))) cleaned = cleaned.slice(0, lastLt);
    }
    if (trim(partnerName)) {
      const escaped = partnerName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      cleaned = cleaned.replace(new RegExp(`^\\s*(?:${escaped})\\s*:?[ \t]*\\n+`, 'i'), '');
      cleaned = cleaned.replace(new RegExp(`^\\s*(?:${escaped})\\s*:[ \t]*`, 'i'), '');
    }
    cleaned = cleaned.replace(/^(?:\s*[A-Z][^\n:]{1,80}:\s*)/, '');
    cleaned = cleaned.replace(/^\s*(?:final\s+answer|answer|final\s+prompt|prompt)\s*:\s*/i, '');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
    return trim(cleaned);
  }
  function parseSseBlock(block) {
    const normalized = String(block || '').replace(/\r/g, '');
    const lines = normalized.split(/\n/);
    let event = 'message';
    const dataLines = [];
    lines.forEach(line => {
      if (line.startsWith(':')) return;
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
          timeoutId = window.setTimeout(() => reject(makeStreamTimeoutError(code, code === 'STREAM_IDLE_TIMEOUT' ? 'The live reply stalled before finishing.' : 'The live reply timed out before any visible output arrived.')), timeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
    }
  }
  async function consumeRoleplayStream(response, handlers = {}) {
    const meta = { sawAnyEvent: false, sawDelta: false, sawFinal: false, rawText: '', stalled: false };
    const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase();
    if (!response.body) {
      const raw = await response.text();
      meta.rawText = trim(raw || '');
      return meta;
    }
    if (!contentType.includes('text/event-stream')) {
      const raw = await response.text();
      meta.rawText = trim(raw || '');
      if (meta.rawText && typeof handlers.message === 'function') handlers.message({ raw: meta.rawText });
      return meta;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await readStreamChunkWithTimeout(reader, meta.sawAnyEvent ? STREAM_IDLE_TIMEOUT_MS : STREAM_FIRST_EVENT_TIMEOUT_MS, meta.sawAnyEvent ? 'STREAM_IDLE_TIMEOUT' : 'STREAM_FIRST_TIMEOUT');
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, '\n');
        let splitAt = buffer.indexOf('\n\n');
        while (splitAt >= 0) {
          const block = buffer.slice(0, splitAt);
          buffer = buffer.slice(splitAt + 2);
          const parsed = parseSseBlock(block);
          if (!parsed) { splitAt = buffer.indexOf('\n\n'); continue; }
          meta.sawAnyEvent = true;
          if (parsed.event === 'delta') meta.sawDelta = true;
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
      if (tail.event === 'delta') meta.sawDelta = true;
      if (tail.event === 'final') meta.sawFinal = true;
      if (typeof handlers[tail.event] === 'function') handlers[tail.event](tail.payload || {});
    }
    return meta;
  }
  function applyPresetDefaults(options = {}) { const el = ids(); const preset = ROLEPLAY_PRESET_DEFAULTS[String(el.outputPreset?.value || 'roleplay').trim()] || ROLEPLAY_PRESET_DEFAULTS.roleplay; if (el.style) el.style.value = preset.style; if (el.maxTokens) el.maxTokens.value = preset.max_tokens; if (el.temperature) el.temperature.value = preset.temperature; if (el.topP) el.topP.value = preset.top_p; if (el.topK) el.topK.value = preset.top_k; syncPresetMeta(); persistState(); if (!options.quiet) setStatus('roleplay-setup-status', `${(el.outputPreset?.selectedOptions?.[0]?.textContent || 'Preset')} defaults applied.`, 'ok'); }
  function addTurn(role, content) { const clean = trim(content); if (!clean) return; transcript.push({ role, content: clean }); renderTranscript(); }
  async function runRoleplay(mode, extra = {}) {
    const targetStatus = mode === 'reply' ? 'roleplay-chat-status' : 'roleplay-setup-status';
    if (isStreaming) { setStatus(targetStatus, 'A roleplay turn is already generating.', 'warn'); return; }
    if (!requireBackendRole('text', targetStatus, 'Connect a Text Backend first. Roleplay uses the active text model.')) return;
    const state = getState();
    const payload = new FormData();
    const userMessage = trim(extra.user_message || '');
    const interactionMode = trim(state.interaction_mode || 'roleplay') || 'roleplay';
    const inputIntent = resolvedInputIntent(mode, interactionMode, extra.input_intent || state.input_intent || 'auto');
    payload.append('model', currentModel()); payload.append('mode', mode); payload.append('scenario', state.scenario); payload.append('user_name', state.user_name); payload.append('partner_name', state.partner_name); payload.append('user_character_id', state.user_character_id || ''); payload.append('partner_character_id', state.partner_character_id || ''); payload.append('world_id', state.world_id || ''); payload.append('scenario_id', state.scenario_id || ''); payload.append('story_id', activeStoryId || ''); payload.append('part_id', activePartId || ''); payload.append('cast_json', JSON.stringify(state.cast_json || [])); payload.append('tone', state.tone); payload.append('custom_tone', state.custom_tone || ''); payload.append('canon_mode', state.canon_mode || 'what_if'); payload.append('output_preset', state.output_preset || 'roleplay'); payload.append('interaction_mode', interactionMode); payload.append('input_intent', inputIntent); payload.append('continuous_scene_mode', String(!!state.continuous_scene_mode)); payload.append('story_mode', state.story_mode || 'linear'); payload.append('option_count', String(state.branch_option_count || 3)); payload.append('allow_custom_option', String(!!state.branch_allow_custom_option)); payload.append('style', state.style); payload.append('scene_notes', state.scene_notes); payload.append('memory_notes', state.memory_notes); payload.append('author_note', state.author_note); payload.append('story_scope_notes', state.story_scope_notes || ''); payload.append('chapter_scope_notes', state.chapter_scope_notes || ''); payload.append('part_scope_notes', state.part_scope_notes || ''); payload.append('chapter_index', String(state.chapter_index || 1)); payload.append('chapter_label', state.chapter_label || ''); payload.append('part_index', String(state.part_index || 1)); payload.append('beat_focus', state.beat_focus || ''); payload.append('active_pov', state.active_pov || ''); payload.append('active_location', state.active_location || ''); payload.append('active_cast_focus', state.active_cast_focus || ''); payload.append('part_objective', state.part_objective || ''); payload.append('tension_level', state.tension_level || 'medium'); payload.append('pacing_target', state.pacing_target || 'steady'); payload.append('story_linked_context_json', JSON.stringify(state.story_linked_context || {})); payload.append('part_linked_context_json', JSON.stringify(state.part_linked_context || {})); payload.append('story_linked_context_text', state.story_linked_context_text || ''); payload.append('part_linked_context_text', state.part_linked_context_text || ''); payload.append('max_tokens', String(state.max_tokens || 320)); payload.append('temperature', String(state.temperature || 0.82)); payload.append('top_p', String(state.top_p || 0.92)); payload.append('top_k', String(state.top_k || 60)); payload.append('transcript_json', JSON.stringify(state.transcript || [])); payload.append('user_message', userMessage);
    setRoleplayBusy(true, mode === 'reply' ? 'Replying...' : 'Running...'); setStatus('roleplay-setup-status', ''); setStatus('roleplay-chat-status', ''); updateFinishState('');
    if (userMessage && shouldAddUserTurnToTranscript(interactionMode, inputIntent)) addTurn('user', userMessage);
    if (isBranchingMode(state.story_mode || 'linear') && userMessage) { branchOptions = []; renderBranchOptions(); }
    if (userMessage && extra.clear_input !== false) { const userInput = $('roleplay-user-input'); if (userInput) userInput.value = ''; }
    let assistantText = '';
    streamController = new AbortController();
    setStreamActive(true);
    try {
      const response = await fetch('/api/roleplay-reply-stream', { method: 'POST', body: payload, signal: streamController.signal, cache: 'no-store' });
      if (!response.ok) {
        let message = 'Roleplay request failed.';
        try { const data = await response.json(); message = data.error || data.message || message; } catch (_err) {}
        throw new Error(message);
      }
      const streamMeta = await consumeRoleplayStream(response, {
        delta(data) {
          assistantText = sanitizeRoleplayStreamText(data.text || `${assistantText}${data.delta || ''}`, state.partner_name || '');
          if (assistantText) updateStreamingAssistant(assistantText);
        },
        final(data) {
          assistantText = sanitizeRoleplayStreamText(data.reply || assistantText || '', state.partner_name || '');
          if (assistantText) finalizeStreamingAssistant(assistantText); else discardStreamingAssistant();
          updateFinishState(data.finish_reason || '');
          lastReplyRequest = { mode, payload: { ...state, interaction_mode: interactionMode, input_intent: inputIntent, user_message: userMessage } };
          const warning = trim(data.warning || '');
          const message = trim(data.message || 'Turn ready.');
          setStatus(targetStatus, warning || message, warning ? 'warn' : 'ok');
        },
        error(data) {
          throw new Error(data.error || 'Streaming roleplay request failed.');
        },
      });
      if (!streamMeta?.sawFinal) {
        if (assistantText) {
          finalizeStreamingAssistant(assistantText);
          updateFinishState(streamMeta?.stalled ? 'length' : lastFinishReason || '');
          lastReplyRequest = { mode, payload: { ...state, interaction_mode: interactionMode, input_intent: inputIntent, user_message: userMessage } };
          setStatus(targetStatus, streamMeta?.stalled ? 'The live reply stalled, but the partial output was recovered. Use Continue cut-off to keep going.' : 'The stream ended without a final marker. Recovered the visible reply.', 'warn');
        } else if (trim(streamMeta?.rawText || '')) {
          assistantText = sanitizeRoleplayStreamText(streamMeta.rawText || '', state.partner_name || '');
          finalizeStreamingAssistant(assistantText);
          updateFinishState('');
          lastReplyRequest = { mode, payload: { ...state, interaction_mode: interactionMode, input_intent: inputIntent, user_message: userMessage } };
          setStatus(targetStatus, 'Recovered a non-stream reply body after the live stream ended unexpectedly.', 'warn');
        } else {
          throw new Error(streamMeta?.stalled ? 'The live reply stalled before any visible output arrived.' : 'The live reply ended before any visible output arrived.');
        }
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        if (assistantText) finalizeStreamingAssistant(assistantText); else discardStreamingAssistant();
        updateFinishState(assistantText ? 'length' : '');
        setStatus(targetStatus, assistantText ? 'Generation stopped. Use Continue cut-off to keep going from the partial reply.' : 'Generation stopped.', assistantText ? 'warn' : 'ok');
        if (assistantText) lastReplyRequest = { mode, payload: { ...state, interaction_mode: interactionMode, input_intent: inputIntent, user_message: userMessage } };
      } else {
        if (assistantText) {
          finalizeStreamingAssistant(assistantText);
          updateFinishState(err?.code === 'STREAM_IDLE_TIMEOUT' ? 'length' : lastFinishReason || '');
          lastReplyRequest = { mode, payload: { ...state, interaction_mode: interactionMode, input_intent: inputIntent, user_message: userMessage } };
          setStatus(targetStatus, err?.code === 'STREAM_IDLE_TIMEOUT' ? 'The live reply stalled, but the visible partial output was recovered. Use Continue cut-off to keep going.' : (err.message || 'Roleplay request failed.'), 'warn');
        } else {
          discardStreamingAssistant();
          setStatus(targetStatus, err.message || 'Roleplay request failed.', 'warn');
        }
      }
    } finally {
      streamController = null;
      setStreamActive(false);
      setRoleplayBusy(false);
      if (assistantText && isBranchingMode(getState().story_mode || 'linear')) {
        try { await refreshBranchChoicesAfterTurn(); } catch (err) { setStatus('roleplay-chat-status', err.message || 'Could not refresh branch choices.', 'warn'); }
      } else if (!isBranchingMode(getState().story_mode || 'linear')) {
        branchOptions = [];
        renderBranchOptions();
      }
      persistState();
    }
  }
  async function regenerateReply() {
    if (!lastReplyRequest) { setStatus('roleplay-chat-status', 'No previous reply request to regenerate yet.', 'warn'); return; }
    const payload = lastReplyRequest.payload || {};
    if (transcript.length && transcript[transcript.length - 1]?.role === 'assistant') transcript.pop();
    if (lastReplyRequest.mode === 'reply' && trim(payload.user_message || '') && transcript.length && transcript[transcript.length - 1]?.role === 'user' && shouldAddUserTurnToTranscript(payload.interaction_mode || 'roleplay', payload.input_intent || 'auto')) transcript.pop();
    renderTranscript();
    await runRoleplay(lastReplyRequest.mode || 'continue', { user_message: payload.user_message || '', input_intent: payload.input_intent || 'auto', clear_input: false });
  }
  function clearScene() { if (streamController) streamController.abort(); transcript = []; lastReplyRequest = null; lastFinishReason = ''; lastTruncated = false; activePartId = ''; const partIdInput = $('roleplay-part-id'); if (partIdInput) partIdInput.value = ''; setStatus('roleplay-setup-status', 'Transcript cleared.', 'ok'); setStatus('roleplay-chat-status', ''); renderTranscript(); renderRoleplayContinuityInspector(null); }
  async function copyTranscript() { const fullText = transcript.map(entry => `${roleLabel(entry.role)}: ${entry.content}`).join('\n\n'); if (!fullText) { setStatus('roleplay-chat-status', 'Nothing to copy yet.', 'warn'); return; } try { await navigator.clipboard.writeText(fullText); setStatus('roleplay-chat-status', 'Transcript copied.', 'ok'); } catch (_err) { setStatus('roleplay-chat-status', 'Could not copy transcript.', 'warn'); } }
  function bindCastEvents() {
    $('btn-roleplay-scene-cast-add')?.addEventListener('click', () => { sceneCast = sceneCastFromDom(); sceneCast.push({ character_id: '', character_name: '', scene_role: 'supporting', presence: 'on_scene', notes: '' }); renderSceneCast(); persistState(); });
    document.addEventListener('click', event => {
      const btn = event.target.closest('button[data-scene-cast-remove]');
      if (!btn) return;
      sceneCast = sceneCastFromDom();
      const idx = Number(btn.dataset.index || -1);
      if (idx >= 0) sceneCast.splice(idx, 1);
      renderSceneCast();
      persistState();
    });
    document.addEventListener('input', event => {
      if (event.target.closest('#roleplay-scene-cast-list')) persistState();
    });
    document.addEventListener('change', event => {
      if (event.target.closest('#roleplay-scene-cast-list')) persistState();
    });
  }
  function reorderRoleplayLibraries() {
    const panel = document.getElementById('roleplay-library-panel');
    if (!panel) return;
    const body = panel.querySelector('.roleplay-collapsible-body') || panel;
    const desired = ['Legends','Universes','Worlds','Kingdoms / Regions','Cities / Settlements','Locations','Organizations / Factions','Characters','Weapons / Artifacts','Spells / Rituals / Techniques','Cycles / Conditions / Systems','Creatures / Animals / Fauna','Packs','Scenarios'];
    const blocks = Array.from(body.querySelectorAll(':scope > details.accordion-block'));
    if (!blocks.length) return;
    const byLabel = new Map(blocks.map(block => [String(block.querySelector('summary')?.textContent || '').trim(), block]));
    desired.forEach(label => { const node = byLabel.get(label); if (node) body.appendChild(node); });
  }

  function bindSurface() {
    loadState(); renderSceneCast(); renderTranscript(); renderRoleplayContinuityInspector(null); syncCustomToneVisibility(); syncPresetMeta(); refreshBackendNote(); bindCastEvents();
    $('btn-roleplay-note-manage-backend')?.addEventListener('click', () => { if (typeof openBackendManager === 'function') openBackendManager('text'); });
    $('btn-roleplay-start-scene')?.addEventListener('click', () => runRoleplay('start'));
    $('btn-roleplay-apply-preset')?.addEventListener('click', applyPresetDefaults);
    $('roleplay-tone')?.addEventListener('change', () => { syncCustomToneVisibility(); persistState(); });
    $('roleplay-output-preset')?.addEventListener('change', () => { applyPresetDefaults(); });
    $('roleplay-interaction-mode')?.addEventListener('change', () => { syncPresetMeta(); persistState(); });
    $('roleplay-input-intent')?.addEventListener('change', () => { syncInteractionUi(); persistState(); });
    $('btn-roleplay-continue-scene')?.addEventListener('click', () => {
      const state = getState();
      const message = trim($('roleplay-user-input')?.value || '');
      if (isAuthoringMode(state.interaction_mode || '') && message) runRoleplay('continue', { user_message: message, clear_input: true });
      else runRoleplay('continue');
    });
    $('btn-roleplay-send')?.addEventListener('click', () => {
      const state = getState();
      const message = trim($('roleplay-user-input')?.value || '');
      if (!message) { setStatus('roleplay-chat-status', isAuthoringMode(state.interaction_mode || '') ? 'Write an author instruction or switch the Input intent if you want to inject story text.' : 'Write your turn first.', 'warn'); return; }
      runRoleplay('reply', { user_message: message, clear_input: true });
    });
    $('btn-roleplay-regenerate')?.addEventListener('click', regenerateReply);
    $('btn-roleplay-stop')?.addEventListener('click', stopRoleplayStream);
    $('btn-roleplay-continue-cutoff')?.addEventListener('click', () => {
      const state = getState();
      const message = trim($('roleplay-user-input')?.value || '');
      if (isAuthoringMode(state.interaction_mode || '') && message) runRoleplay('continue', { user_message: message, clear_input: true });
      else runRoleplay('continue');
    });
    $('btn-roleplay-close-part')?.addEventListener('click', () => closeCurrentPart().catch(err => setStatus('roleplay-setup-status', err.message || 'Could not close the current part.', 'warn')));
    $('btn-roleplay-next-part')?.addEventListener('click', () => startNextPart().catch(err => setStatus('roleplay-setup-status', err.message || 'Could not move to the next part.', 'warn')));
    $('btn-roleplay-clear-scene')?.addEventListener('click', clearScene);
    $('btn-roleplay-copy-transcript')?.addEventListener('click', copyTranscript);
    $('btn-roleplay-preview-continuity')?.addEventListener('click', () => previewRoleplayContinuity().catch(err => setStatus('roleplay-continuity-status', err.message || 'Could not preview continuity.', 'warn')));
    $('btn-roleplay-repair-continuity')?.addEventListener('click', () => repairRoleplayContinuity().catch(err => setStatus('roleplay-continuity-status', err.message || 'Could not repair continuity.', 'warn')));
    $('btn-roleplay-reset-part-continuity')?.addEventListener('click', () => resetRoleplayContinuity('part').catch(err => setStatus('roleplay-continuity-status', err.message || 'Could not reset part continuity.', 'warn')));
    $('btn-roleplay-reset-story-continuity')?.addEventListener('click', () => resetRoleplayContinuity('story').catch(err => setStatus('roleplay-continuity-status', err.message || 'Could not reset story continuity.', 'warn')));
    $('btn-roleplay-refresh-choices')?.addEventListener('click', () => requestBranchOptions().catch(err => setStatus('roleplay-chat-status', err.message || 'Could not refresh branch choices.', 'warn')));
    $('btn-roleplay-branch-send-custom')?.addEventListener('click', () => { const custom = trim($('roleplay-branch-custom-input')?.value || ''); if (!custom) { setStatus('roleplay-chat-status', 'Write a custom branch choice first.', 'warn'); return; } chooseBranchOption({ id: 'custom', label: 'Custom choice', text: custom }, 'custom').catch(err => setStatus('roleplay-chat-status', err.message || 'Could not apply the custom choice.', 'warn')); });
    document.addEventListener('click', event => { const btn = event.target.closest('button[data-branch-choice-index]'); if (!btn) return; const idx = Number(btn.getAttribute('data-branch-choice-index') || -1); const option = branchOptions[idx]; if (!option) return; chooseBranchOption(option, 'generated').catch(err => setStatus('roleplay-chat-status', err.message || 'Could not apply the branch choice.', 'warn')); });
    ['roleplay-scenario','roleplay-user-name','roleplay-partner-name','roleplay-user-character-id','roleplay-partner-character-id','roleplay-world-id','roleplay-scenario-id','roleplay-tone','roleplay-style','roleplay-custom-tone','roleplay-canon-mode','roleplay-output-preset','roleplay-interaction-mode','roleplay-input-intent','roleplay-continuous-scene-mode','roleplay-story-mode','roleplay-branch-option-count','roleplay-branch-allow-custom','roleplay-scene-notes','roleplay-memory-notes','roleplay-author-note','roleplay-story-scope-notes','roleplay-chapter-scope-notes','roleplay-part-scope-notes','roleplay-chapter-index','roleplay-chapter-label','roleplay-part-index','roleplay-beat-focus','roleplay-active-pov','roleplay-active-location','roleplay-active-cast-focus','roleplay-part-objective','roleplay-tension-level','roleplay-pacing-target','roleplay-max-tokens','roleplay-temperature','roleplay-top-p','roleplay-top-k','roleplay-user-input','roleplay-branch-custom-input'].forEach(id => { const node = $(id); if (!node) return; node.addEventListener('input', persistState); node.addEventListener('change', persistState); });
    $('roleplay-user-input')?.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); $('btn-roleplay-send')?.click(); } });
    document.addEventListener('neo-backend-state', refreshBackendNote);
  }
  window.neoRefreshRoleplaySurface = refreshBackendNote;
  window.neoRefreshRoleplayLibrarySelections = function () { persistState(); renderSceneCast(); };
  window.neoFlushRoleplayState = flushPersistState;
  window.neoGetRoleplaySessionState = exportSessionState;
  window.neoSuggestRoleplayPartTitle = function () { return suggestPartTitle(); };
  window.neoApplyRoleplaySessionState = function (saved, options = {}) { applySessionState(saved || {}, options); };
  window.neoSetRoleplaySessionLink = function (storyId = '', partId = '') { activeStoryId = trim(storyId || ''); activePartId = trim(partId || ''); renderRoleplayContinuityInspector(null); persistState(); };
  window.neoSetRoleplaySceneCast = function (items = [], options = {}) { sceneCast = cleanCast(items); renderSceneCast(); if (!options.silent) persistState(); };
  window.neoGetRoleplaySceneCast = function () { return sceneCastFromDom(); };
  if (document.readyState === 'complete') bindSurface(); else document.addEventListener('DOMContentLoaded', bindSurface, { once: true });
})();
