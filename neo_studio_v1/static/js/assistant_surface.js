(function () {
  let assistantProfile = null;
  let assistantModes = {};
  let assistantSessions = [];
  let assistantProjects = [];
  let assistantSearchResults = [];
  let activeSession = null;
  let activeSaveTimer = null;
  let profileSaveTimer = null;
  let streamController = null;
  let isStreaming = false;
  let memoryBackendStatus = null;
  let memoryAdminState = null;
  let currentPlaceholderId = '';
  let assistantAutoFollow = true;
  const STREAM_FIRST_EVENT_TIMEOUT_MS = 90000;
  const STREAM_IDLE_TIMEOUT_MS = 20000;
  const assistantStatusTimers = {};

  function scheduleAssistantStatusClear(id, delay = 4200) {
    const el = $(id);
    if (!el) return;
    if (assistantStatusTimers[id]) window.clearTimeout(assistantStatusTimers[id]);
    const level = String(el.className || '');
    if (!trim(el.textContent || '') || /warn|error/.test(level)) return;
    assistantStatusTimers[id] = window.setTimeout(() => {
      const node = $(id);
      if (!node) return;
      const liveLevel = String(node.className || '');
      if (!trim(node.textContent || '') || /warn|error/.test(liveLevel)) return;
      setStatus(id, '', '');
    }, delay);
  }

  function bindAssistantStatusAutoClear(id) {
    const el = $(id);
    if (!el || el.dataset.assistantStatusBound === '1') return;
    el.dataset.assistantStatusBound = '1';
    const observer = new MutationObserver(() => scheduleAssistantStatusClear(id));
    observer.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['class'] });
  }

  function ids() {
    return {
      sessionSearch: $('assistant-session-search'),
      projectFilter: $('assistant-project-filter'),
      sessionList: $('assistant-session-list'),
      sessionStatus: $('assistant-session-status'),
      threadTitle: $('assistant-thread-title'),
      threadMeta: $('assistant-thread-meta'),
      thread: $('assistant-thread'),
      emptyState: $('assistant-empty-state'),
      composer: $('assistant-composer'),
      chatStatus: $('assistant-chat-status'),
      settingsStatus: $('assistant-settings-status'),
      projectSelect: $('assistant-project-select'),
      mode: $('assistant-mode'),
      modeMeta: $('assistant-mode-meta'),
      threadInstruction: $('assistant-thread-instruction'),
      maxTokens: $('assistant-max-tokens'),
      temperature: $('assistant-temperature'),
      topP: $('assistant-top-p'),
      topK: $('assistant-top-k'),
      activeModel: $('assistant-active-model'),
      activeModelMeta: $('assistant-active-model-meta'),
      backendNote: $('assistant-text-backend-note'),
      backendNoteBody: $('assistant-text-backend-note-body'),
      profileName: $('assistant-profile-name'),
      profileUserName: $('assistant-profile-user-name'),
      profileAddressStyle: $('assistant-profile-address-style'),
      profileDefaultMode: $('assistant-profile-default-mode'),
      profileResponseDetail: $('assistant-profile-response-detail'),
      profileSupportStyle: $('assistant-profile-support-style'),
      profileAboutUser: $('assistant-profile-about-user'),
      profilePreferences: $('assistant-profile-preferences'),
      profileAvoid: $('assistant-profile-avoid'),
    };
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function newMessageId() {
    return `assistant_msg_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function activeModeConfig(modeKey) {
    const key = trim(modeKey || activeSession?.mode || assistantProfile?.default_mode || 'general') || 'general';
    return assistantModes[key] || assistantModes.general || {
      label: 'General',
      description: 'Balanced day-to-day help.',
      max_tokens: 640,
      temperature: 0.7,
      top_p: 0.92,
      top_k: 60,
    };
  }

  function updateStreamingState(active, busyText = 'Sending...') {
    isStreaming = !!active;
    const sendBtn = $('btn-assistant-send');
    const stopBtn = $('btn-assistant-stop');
    const continueBtn = $('btn-assistant-continue');
    const regenBtn = $('btn-assistant-regenerate');
    if (sendBtn) {
      if (active) {
        sendBtn.dataset.originalText = sendBtn.textContent;
        sendBtn.textContent = busyText;
      } else if (sendBtn.dataset.originalText) {
        sendBtn.textContent = sendBtn.dataset.originalText;
      }
      sendBtn.disabled = !!active;
    }
    if (stopBtn) stopBtn.disabled = !active;
    if (continueBtn) continueBtn.disabled = !!active || !canContinueReply();
    if (regenBtn) regenBtn.disabled = !!active || !canRegenerate();
  }

  function canContinueReply() {
    if (activeSession?.pending_continue) return true;
    if (!activeSession || !Array.isArray(activeSession.messages) || !activeSession.messages.length) return false;
    const last = activeSession.messages[activeSession.messages.length - 1];
    if (last?.role !== 'assistant') return false;
    const finishReason = trim(last?.meta?.finish_reason || '');
    return !!trim(last?.content || '') && (finishReason === 'length' || finishReason === 'partial' || finishReason === 'stopped');
  }

  function canRegenerate() {
    if (!activeSession || !Array.isArray(activeSession.messages) || !activeSession.messages.length) return false;
    const last = activeSession.messages[activeSession.messages.length - 1];
    const prev = activeSession.messages[activeSession.messages.length - 2];
    return last?.role === 'assistant' && prev?.role === 'user';
  }

  function helperWorkspace(session = activeSession) {
    return trim(session?.helper_context?.workspace || '').toLowerCase();
  }

  function isRoleplayHelperSession(session = activeSession) {
    return helperWorkspace(session) === 'roleplay';
  }

  function isDirectWorkspaceHelperSession(session = activeSession) {
    return ['generation', 'prompt', 'caption'].includes(helperWorkspace(session));
  }

  function workspaceHelperLabel(session = activeSession) {
    const workspace = helperWorkspace(session);
    if (workspace === 'generation') return 'Generation';
    if (workspace === 'prompt') return 'Prompt Studio';
    if (workspace === 'caption') return 'Caption Studio';
    return 'Workspace';
  }

  function applyAssistantMessageToRoleplay(messageId, options = {}) {
    if (!activeSession || !isRoleplayHelperSession()) {
      setStatus('assistant-chat-status', 'This chat is not a Roleplay helper thread.', 'warn');
      return;
    }
    const bridge = window.NeoRoleplayHelperBridge;
    if (!bridge || typeof bridge.applyAssistantDraftFromText !== 'function') {
      setStatus('assistant-chat-status', 'Roleplay write-back is not ready yet. Open the Roleplay workspace and try again.', 'warn');
      return;
    }
    const message = (activeSession.messages || []).find(item => String(item?.id || '') === String(messageId || ''));
    if (!message || message.role !== 'assistant' || !trim(message.content || '')) {
      setStatus('assistant-chat-status', 'No Assistant draft was found on that message yet.', 'warn');
      return;
    }
    const target = trim(activeSession?.helper_context?.target || '').toLowerCase();
    const result = bridge.applyAssistantDraftFromText(message.content || '', target, { openRoleplay: !!options.openRoleplay });
    if (!result?.ok) {
      setStatus('assistant-chat-status', result?.message || 'Could not map that Assistant draft into the Roleplay fields yet.', 'warn');
      return;
    }
    if (options.openRoleplay && typeof switchTab === 'function') switchTab('roleplay_v2');
    autoLinkProjectRecord('roleplay_v2', `Roleplay apply · ${activeSession?.title || 'Assistant chat'}`, `Applied Assistant draft into ${target} fields.`, 'assistant_apply');
    setStatus('assistant-chat-status', result.message || `Applied the Assistant draft into ${target} fields. Review it before saving.`, 'ok');
  }

  function applyAssistantMessageToWorkspace(messageId, options = {}) {
    if (!activeSession || !isDirectWorkspaceHelperSession()) {
      setStatus('assistant-chat-status', 'This chat is not a Generation / Prompt / Caption helper thread.', 'warn');
      return;
    }
    const bridge = window.NeoWorkspaceHelperBridge;
    if (!bridge || typeof bridge.applyAssistantDraftFromText !== 'function') {
      setStatus('assistant-chat-status', 'Workspace write-back is not ready yet. Open the target workspace once and try again.', 'warn');
      return;
    }
    const message = (activeSession.messages || []).find(item => String(item?.id || '') === String(messageId || ''));
    if (!message || message.role !== 'assistant' || !trim(message.content || '')) {
      setStatus('assistant-chat-status', 'No Assistant draft was found on that message yet.', 'warn');
      return;
    }
    const workspace = helperWorkspace();
    const result = bridge.applyAssistantDraftFromText(message.content || '', workspace, {
      openWorkspace: !!options.openWorkspace,
      target: trim(activeSession?.helper_context?.target || ''),
    });
    if (!result?.ok) {
      setStatus('assistant-chat-status', result?.message || 'Could not map that Assistant draft into the workspace fields yet.', 'warn');
      return;
    }
    autoLinkProjectRecord(workspace, `${workspaceHelperLabel()} apply · ${activeSession?.title || 'Assistant chat'}`, `Applied Assistant draft into ${workspaceHelperLabel()} fields.`, 'assistant_apply');
    setStatus('assistant-chat-status', result.message || `Applied the Assistant draft into ${workspaceHelperLabel()} fields. Review it before saving.`, 'ok');
  }

  function exportAssistantMessage(messageId, target = '') {
    if (!activeSession) return;
    const message = (activeSession.messages || []).find(item => String(item?.id || '') === String(messageId || ''));
    const content = trim(message?.content || '');
    if (!content) {
      setStatus('assistant-chat-status', 'No Assistant text was found to export from that message yet.', 'warn');
      return;
    }
    const focusField = (id) => {
      const el = $(id);
      if (!el) return false;
      el.value = content;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      window.setTimeout(() => el.focus(), 0);
      return true;
    };
    if (target === 'prompt') {
      if (typeof switchTab === 'function') switchTab('prompt');
      if (typeof switchManagerSubTab === 'function') switchManagerSubTab('prompt');
      if (!focusField('prompt-idea')) {
        setStatus('assistant-chat-status', 'Prompt Studio is not ready yet.', 'warn');
        return;
      }
      autoLinkProjectRecord('prompt', `Prompt Studio export · ${activeSession?.title || 'Assistant chat'}`, 'Exported an Assistant reply into Prompt Studio.', 'assistant_export');
      setStatus('assistant-chat-status', 'Sent that Assistant reply into Prompt Studio.', 'ok');
      return;
    }
    if (target === 'caption') {
      if (typeof switchTab === 'function') switchTab('prompt');
      if (typeof switchManagerSubTab === 'function') switchManagerSubTab('caption');
      if (!focusField('caption-output')) {
        setStatus('assistant-chat-status', 'Caption Studio is not ready yet.', 'warn');
        return;
      }
      autoLinkProjectRecord('caption', `Caption Studio export · ${activeSession?.title || 'Assistant chat'}`, 'Exported an Assistant reply into Caption Studio.', 'assistant_export');
      setStatus('assistant-chat-status', 'Sent that Assistant reply into Caption Studio.', 'ok');
      return;
    }
    if (target === 'generation') {
      if (typeof switchTab === 'function') switchTab('generate');
      if (!focusField('generation-positive')) {
        setStatus('assistant-chat-status', 'Generation is not ready yet.', 'warn');
        return;
      }
      autoLinkProjectRecord('generation', `Generation export · ${activeSession?.title || 'Assistant chat'}`, 'Exported an Assistant reply into Generation.', 'assistant_export');
      setStatus('assistant-chat-status', 'Sent that Assistant reply into Generation.', 'ok');
    }
  }

  function shouldKeepContinueAvailable(reason = '') {
    const finishReason = trim(reason || '').toLowerCase();
    return finishReason === 'length' || finishReason === 'partial' || finishReason === 'stopped';
  }

  function markPendingContinue(reason = '') {
    if (!activeSession) return;
    activeSession.pending_continue = true;
    activeSession.pending_continue_reason = trim(reason || '') || 'partial';
  }

  function clearPendingContinue() {
    if (!activeSession) return;
    activeSession.pending_continue = false;
    activeSession.pending_continue_reason = '';
  }


  function isNearBottom(node, threshold = 72) {
    if (!node) return true;
    return (node.scrollHeight - node.scrollTop - node.clientHeight) <= threshold;
  }

  function syncJumpLatestVisibility(forceHide = false) {
    const thread = $('assistant-thread');
    const btn = $('btn-assistant-jump-latest');
    if (!thread || !btn) return;
    const nearBottom = isNearBottom(thread);
    if (forceHide || nearBottom) btn.classList.add('hidden');
    else btn.classList.remove('hidden');
  }

  function scrollThreadToLatest(behavior = 'auto') {
    const thread = $('assistant-thread');
    if (!thread) return;
    thread.scrollTo({ top: thread.scrollHeight, behavior });
    assistantAutoFollow = true;
    syncJumpLatestVisibility(true);
  }

  function renderModeSelects() {
    const el = ids();
    const modeKeys = Object.keys(assistantModes || {});
    ['mode', 'profileDefaultMode'].forEach(key => {
      const select = el[key];
      if (!select) return;
      const current = select.value;
      select.innerHTML = '';
      modeKeys.forEach(modeKey => {
        const data = assistantModes[modeKey] || {};
        const opt = document.createElement('option');
        opt.value = modeKey;
        opt.textContent = data.label || modeKey;
        if (modeKey === current) opt.selected = true;
        select.appendChild(opt);
      });
    });
  }



  function activeProjectMeta() {
    const projectId = trim(activeSession?.project_id || $('assistant-project-select')?.value || '');
    if (!projectId) return null;
    return (assistantProjects || []).find(item => item.id === projectId) || null;
  }


  function projectTitle(projectId) {
    const clean = trim(projectId || '');
    if (!clean) return '';
    return (assistantProjects || []).find(item => item.id === clean)?.title || '';
  }

  async function saveProjectPatch(project, patch = {}) {
    if (!project?.id) throw new Error('Select a project on this thread first.');
    const payload = {
      project_id: project.id,
      description: patch.description !== undefined ? patch.description : (project.description || ''),
      brief: patch.brief !== undefined ? patch.brief : (project.brief || ''),
      context_cards: Array.isArray(patch.context_cards) ? patch.context_cards : (Array.isArray(project.context_cards) ? project.context_cards : []),
      context_files: Array.isArray(patch.context_files) ? patch.context_files : (Array.isArray(project.context_files) ? project.context_files : []),
      linked_records: Array.isArray(patch.linked_records) ? patch.linked_records : (Array.isArray(project.linked_records) ? project.linked_records : []),
    };
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    return data;
  }

  function renderAssistantSearchResults(results = [], query = '') {
    const wrap = $('assistant-search-results');
    if (!wrap) return;
    const cleanQuery = trim(query || '');
    wrap.innerHTML = '';
    if (!cleanQuery || !Array.isArray(results) || !results.length) {
      wrap.classList.add('hidden');
      return;
    }
    wrap.classList.remove('hidden');
    results.forEach((item, index) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'assistant-search-result-card';
      btn.dataset.searchResultIndex = String(index);
      btn.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:flex-start;">
          <div>
            <div class="assistant-search-result-title">${escapeHtml(item.title || item.label || 'Assistant result')}</div>
            <div class="assistant-search-result-meta">${escapeHtml(item.label || 'Result')}</div>
          </div>
          <div class="badge">${escapeHtml(item.kind || 'result')}</div>
        </div>
        <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(item.snippet || '')}</div>
      `;
      wrap.appendChild(btn);
    });
  }

  async function searchAssistantContext() {
    const query = trim($('assistant-session-search')?.value || '');
    if (query.length < 2) {
      setStatus('assistant-session-status', 'Type at least 2 characters to search Assistant context.', 'warn');
      renderAssistantSearchResults([], '');
      return;
    }
    const data = await safeFetchJson(`/api/assistant/search?q=${encodeURIComponent(query)}`);
    assistantSearchResults = Array.isArray(data.results) ? data.results : [];
    renderAssistantSearchResults(assistantSearchResults, query);
    setStatus('assistant-session-status', assistantSearchResults.length ? `Found ${assistantSearchResults.length} Assistant matches.` : 'No Assistant context matched that search.', assistantSearchResults.length ? 'ok' : 'warn');
  }

  function renderContextSourceRow() {
    const row = $('assistant-context-source-row');
    if (!row) return;
    row.innerHTML = '';
    if (!activeSession) {
      row.classList.add('hidden');
      return;
    }
    const project = activeProjectMeta();
    const chips = [];
    if (trim(activeSession.thread_instruction || '')) chips.push('Thread instruction');
    if (trim(activeSession.context_note || '')) chips.push('Thread note');
    const threadItems = Array.isArray(activeSession.context_items) ? activeSession.context_items : [];
    const imageBridgeCount = threadItems.filter(item => trim(item?.source_kind || '') === 'image_bridge').length;
    const threadFileCount = threadItems.filter(item => trim(item?.source_kind || '') !== 'image_bridge').length;
    if (threadFileCount) chips.push(`Thread files (${Number(threadFileCount)})`);
    if (imageBridgeCount) chips.push(`Image context (${Number(imageBridgeCount)})`);
    if (trim(activeSession.memory_summary || '')) chips.push('Thread memory');
    if (trim(activeSession.helper_context?.workspace || '')) chips.push(`Workspace helper: ${activeSession.helper_context.workspace}`);
    if (project?.brief) chips.push('Project brief');
    if ((project?.context_cards || []).length) chips.push(`Project cards (${Number((project?.context_cards || []).length)})`);
    if ((project?.context_files || []).length) chips.push(`Project files (${Number((project?.context_files || []).length)})`);
    if (trim(assistantProfile?.about_user || '') || trim(assistantProfile?.preferences || '') || trim(assistantProfile?.avoid || '')) chips.push('Profile');
    if (!chips.length) {
      row.classList.add('hidden');
      return;
    }
    chips.forEach(label => {
      const chip = document.createElement('span');
      chip.className = 'assistant-context-source-chip';
      chip.textContent = label;
      row.appendChild(chip);
    });
    row.classList.remove('hidden');
  }

  function renderProjectControls() {
    const filter = $('assistant-project-filter');
    const select = $('assistant-project-select');
    const currentFilter = filter?.value || 'all';
    const currentSelect = select?.value || activeSession?.project_id || '';
    if (filter) {
      filter.innerHTML = '';
      [
        { value: 'all', label: 'All projects' },
        { value: '__unassigned__', label: 'Unassigned chats' },
        ...(assistantProjects || []).map(project => ({ value: project.id, label: `${project.title} (${Number(project.thread_count || 0)})` })),
      ].forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.value;
        opt.textContent = item.label;
        if (item.value === currentFilter) opt.selected = true;
        filter.appendChild(opt);
      });
    }
    if (select) {
      select.innerHTML = '';
      const base = document.createElement('option');
      base.value = '';
      base.textContent = 'Unassigned';
      if (!currentSelect) base.selected = true;
      select.appendChild(base);
      (assistantProjects || []).forEach(project => {
        const opt = document.createElement('option');
        opt.value = project.id;
        opt.textContent = project.title;
        if (project.id === currentSelect) opt.selected = true;
        select.appendChild(opt);
      });
    }
  }

  function renderProjectBriefEditor() {
    const area = $('assistant-project-brief');
    const meta = $('assistant-project-brief-meta');
    const btn = $('btn-assistant-save-project-brief');
    const project = activeProjectMeta();
    if (!area || !meta || !btn) return;
    if (!project) {
      area.value = '';
      area.disabled = true;
      btn.disabled = true;
      meta.textContent = 'Assign this thread to a project to keep a shared brief and context that every related chat can inherit.';
      return;
    }
    area.disabled = false;
    btn.disabled = false;
    area.value = project.brief || '';
    meta.textContent = `Shared brief for project: ${project.title}`;
  }


  function renderProjectCardShelf() {
    const wrap = $('assistant-project-card-list');
    const meta = $('assistant-project-cards-meta');
    const titleInput = $('assistant-project-card-title');
    const contentInput = $('assistant-project-card-content');
    const addBtn = $('btn-assistant-add-project-card');
    const project = activeProjectMeta();
    if (!wrap || !meta || !titleInput || !contentInput || !addBtn) return;
    wrap.innerHTML = '';
    if (!project) {
      titleInput.value = '';
      contentInput.value = '';
      titleInput.disabled = true;
      contentInput.disabled = true;
      addBtn.disabled = true;
      meta.textContent = 'Assign this thread to a project first, then add reusable project context cards here.';
      return;
    }
    titleInput.disabled = false;
    contentInput.disabled = false;
    addBtn.disabled = false;
    meta.textContent = `Reusable context cards for project: ${project.title}`;
    const cards = Array.isArray(project.context_cards) ? project.context_cards : [];
    if (!cards.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-session-empty';
      empty.textContent = 'No project context cards yet.';
      wrap.appendChild(empty);
      return;
    }
    cards.forEach(card => {
      const node = document.createElement('div');
      node.className = 'card-lite assistant-context-item';
      const preview = trim(String(card.content || '').replace(/\s+/g, ' ')).slice(0, 180);
      node.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:flex-start;">
          <div>
            <div class="stat-title">${escapeHtml(card.title || 'Context card')}</div>
            <div class="mini-note" style="margin-top:6px;">${Number(card.char_count || (card.content || '').length || 0)} chars</div>
          </div>
          <button class="btn btn-small" data-assistant-remove-project-card="${escapeHtml(card.id || '')}" type="button">Remove</button>
        </div>
        <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(preview)}${(card.content || '').length > 180 ? '…' : ''}</div>
      `;
      wrap.appendChild(node);
    });
  }


  function renderProjectFileShelf() {
    const wrap = $('assistant-project-file-list');
    const meta = $('assistant-project-files-meta');
    const input = $('assistant-project-file-upload');
    const addBtn = $('btn-assistant-add-project-file');
    const project = activeProjectMeta();
    if (!wrap || !meta || !input || !addBtn) return;
    wrap.innerHTML = '';
    if (!project) {
      input.value = '';
      input.disabled = true;
      addBtn.disabled = true;
      meta.textContent = 'Assign this thread to a project first, then add reusable text attachments here.';
      return;
    }
    input.disabled = false;
    addBtn.disabled = false;
    meta.textContent = `Reusable project text attachments for: ${project.title}`;
    const files = Array.isArray(project.context_files) ? project.context_files : [];
    if (!files.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-session-empty';
      empty.textContent = 'No project text attachments yet.';
      wrap.appendChild(empty);
      return;
    }
    files.forEach(file => {
      const node = document.createElement('div');
      node.className = 'card-lite assistant-context-item';
      const preview = trim(String(file.content || '').replace(/\s+/g, ' ')).slice(0, 180);
      node.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:flex-start;">
          <div>
            <div class="stat-title">${escapeHtml(file.title || 'Project file')}</div>
            <div class="mini-note" style="margin-top:6px;">${escapeHtml(String(file.source_kind || 'text').replace(/_/g, ' ').toUpperCase())} · ${Number(file.char_count || (file.content || '').length || 0)} chars</div>
          </div>
          <button class="btn btn-small" data-assistant-remove-project-file="${escapeHtml(file.id || '')}" type="button">Remove</button>
        </div>
        <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(preview)}${(file.content || '').length > 180 ? '…' : ''}</div>
      `;
      wrap.appendChild(node);
    });
  }


  function renderProjectDashboard() {
    const meta = $('assistant-project-dashboard-meta');
    const summary = $('assistant-project-dashboard-summary');
    const stats = $('assistant-project-dashboard-stats');
    const threadList = $('assistant-project-thread-list');
    const recordList = $('assistant-project-record-list');
    const titleInput = $('assistant-project-record-title');
    const typeSelect = $('assistant-project-record-type');
    const noteInput = $('assistant-project-record-note');
    const addBtn = $('btn-assistant-add-project-record');
    const project = activeProjectMeta();
    if (!meta || !summary || !stats || !threadList || !recordList || !titleInput || !typeSelect || !noteInput || !addBtn) return;
    stats.innerHTML = '';
    threadList.innerHTML = '';
    recordList.innerHTML = '';
    if (!project) {
      meta.textContent = 'Assign this thread to a project to see a quick overview, linked chats, and linked records.';
      summary.textContent = 'No active project yet.';
      titleInput.value = '';
      noteInput.value = '';
      titleInput.disabled = true;
      typeSelect.disabled = true;
      noteInput.disabled = true;
      addBtn.disabled = true;
      const emptyThreads = document.createElement('div');
      emptyThreads.className = 'assistant-session-empty';
      emptyThreads.textContent = 'No project selected.';
      threadList.appendChild(emptyThreads);
      const emptyRecords = document.createElement('div');
      emptyRecords.className = 'assistant-session-empty';
      emptyRecords.textContent = 'No linked records yet.';
      recordList.appendChild(emptyRecords);
      return;
    }
    titleInput.disabled = false;
    typeSelect.disabled = false;
    noteInput.disabled = false;
    addBtn.disabled = false;
    const linkedThreads = (assistantSessions || []).filter(item => trim(item?.project_id || '') === project.id);
    const linkedRecords = Array.isArray(project.linked_records) ? project.linked_records : [];
    const briefPreview = trim(project.brief || '').replace(/\s+/g, ' ').slice(0, 180);
    summary.innerHTML = `
      <div class="stat-title">${escapeHtml(project.title || 'Project')}</div>
      <div class="muted small" style="margin-top:8px; line-height:1.55;">${escapeHtml(project.description || 'No project description yet.')}</div>
      <div class="mini-note" style="margin-top:10px;">${briefPreview ? escapeHtml(briefPreview) + (trim(project.brief || '').length > 180 ? '…' : '') : 'No shared brief added yet.'}</div>
    `;
    [
      { label: 'Linked chats', value: linkedThreads.length },
      { label: 'Context cards', value: Number((project.context_cards || []).length) },
      { label: 'Text attachments', value: Number((project.context_files || []).length) },
      { label: 'Linked records', value: linkedRecords.length },
    ].forEach(item => {
      const card = document.createElement('div');
      card.className = 'card-lite';
      card.innerHTML = `<div class="stat-title">${escapeHtml(item.label)}</div><div class="stat-value">${escapeHtml(String(item.value))}</div>`;
      stats.appendChild(card);
    });
    if (!linkedThreads.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-session-empty';
      empty.textContent = 'No chats are linked to this project yet.';
      threadList.appendChild(empty);
    } else {
      linkedThreads.slice().sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || ''))).slice(0, 8).forEach(row => {
        const card = document.createElement('div');
        card.className = 'card-lite assistant-context-item';
        card.innerHTML = `
          <div class="row-between" style="gap:10px; align-items:flex-start;">
            <div>
              <div class="stat-title">${escapeHtml(row.title || 'Assistant chat')}</div>
              <div class="mini-note" style="margin-top:6px;">${escapeHtml(sessionSummary(row))}</div>
            </div>
            <button class="btn btn-small" data-project-thread-open="${escapeHtml(row.id || '')}" type="button">Open</button>
          </div>
        `;
        threadList.appendChild(card);
      });
    }
    if (!linkedRecords.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-session-empty';
      empty.textContent = 'No linked records yet.';
      recordList.appendChild(empty);
    } else {
      linkedRecords.slice().sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).forEach(item => {
        const card = document.createElement('div');
        card.className = 'card-lite assistant-context-item';
        card.innerHTML = `
          <div class="row-between" style="gap:10px; align-items:flex-start;">
            <div>
              <div class="stat-title">${escapeHtml(item.title || 'Linked record')}</div>
              <div class="mini-note" style="margin-top:6px;">${escapeHtml(String(item.record_type || 'other').replace(/_/g, ' ').toUpperCase())}${item.source ? ` · ${escapeHtml(item.source)}` : ''}${item.created_at ? ` · ${escapeHtml(formatDateTime(item.created_at))}` : ''}</div>
            </div>
            <button class="btn btn-small" data-assistant-remove-project-record="${escapeHtml(item.id || '')}" type="button">Remove</button>
          </div>
          <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(item.note || 'No note yet.')}</div>
        `;
        recordList.appendChild(card);
      });
    }
    meta.textContent = `Project dashboard for: ${project.title}`;
  }

  async function addProjectLinkedRecord(payload = null) {
    const project = activeProjectMeta();
    if (!project) {
      setStatus('assistant-project-record-status', 'Select a project on this thread first.', 'warn');
      return { ok: false };
    }
    const title = trim((payload && payload.title) || $('assistant-project-record-title')?.value || '');
    const recordType = trim((payload && payload.record_type) || $('assistant-project-record-type')?.value || 'other') || 'other';
    const note = trim((payload && payload.note) || $('assistant-project-record-note')?.value || '');
    const source = trim((payload && payload.source) || 'assistant');
    if (!title) {
      setStatus('assistant-project-record-status', 'Add a linked record title first.', 'warn');
      return { ok: false };
    }
    const linked = Array.isArray(project.linked_records) ? project.linked_records.slice() : [];
    const duplicate = linked.find(item => trim(item.title || '') === title && trim(item.record_type || '') === recordType && trim(item.note || '') === note);
    if (duplicate) return { ok: true, skipped: true, message: 'That linked record already exists.' };
    linked.push({
      id: `project_record_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      title,
      record_type: recordType,
      note,
      source,
      created_at: nowIso(),
    });
    const data = await saveProjectPatch(project, { linked_records: linked });
    renderProjectDashboard();
    if (!payload) {
      $('assistant-project-record-title').value = '';
      $('assistant-project-record-note').value = '';
      setStatus('assistant-project-record-status', data.message || 'Linked record added.', 'ok');
    }
    return { ok: true, message: data.message || 'Linked record added.' };
  }

  async function removeProjectLinkedRecord(recordId) {
    const project = activeProjectMeta();
    if (!project || !recordId) return;
    const linked = (project.linked_records || []).filter(item => item.id !== recordId);
    await saveProjectPatch(project, { linked_records: linked });
    renderProjectDashboard();
    setStatus('assistant-project-record-status', 'Linked record removed.', 'ok');
  }

  function autoLinkProjectRecord(recordType, title, note = '', source = 'assistant') {
    if (!activeProjectMeta()) return;
    addProjectLinkedRecord({ title, record_type: recordType, note, source }).catch(() => {});
  }

  function renderProfile() {
    const el = ids();
    const profile = assistantProfile || {};
    renderModeSelects();
    if (el.profileName) el.profileName.value = profile.assistant_name || 'Neo';
    if (el.profileUserName) el.profileUserName.value = profile.user_name || '';
    if (el.profileAddressStyle) el.profileAddressStyle.value = profile.address_style || 'adaptive';
    if (el.profileDefaultMode) el.profileDefaultMode.value = profile.default_mode || 'general';
    if (el.profileResponseDetail) el.profileResponseDetail.value = profile.response_detail || 'balanced';
    if (el.profileSupportStyle) el.profileSupportStyle.value = profile.support_style || 'balanced';
    if (el.profileAboutUser) el.profileAboutUser.value = profile.about_user || '';
    if (el.profilePreferences) el.profilePreferences.value = profile.preferences || '';
    if (el.profileAvoid) el.profileAvoid.value = profile.avoid || '';
  }

  function sessionSummary(session) {
    const count = Number(session?.message_count ?? session?.messages?.length ?? 0);
    const mode = activeModeConfig(session?.mode || 'general');
    const bits = [count ? `${count} message${count === 1 ? '' : 's'}` : 'No messages'];
    const project = projectTitle(session?.project_id || '');
    const contextCount = Array.isArray(session?.context_items) ? session.context_items.length : Number(session?.context_count || 0);
    if (project) bits.push(project);
    if (contextCount) bits.push(`${contextCount} context item${contextCount === 1 ? '' : 's'}`);
    bits.push(mode.label || 'General');
    bits.push(`Updated ${formatDateTime(session?.updated_at)}`);
    return bits.join(' · ');
  }

  function formatDateTime(value) {
    if (!value) return 'just now';
    try {
      return new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    } catch (_err) {
      return String(value || '');
    }
  }

  function renderAssistantMemoryBackend(data = null) {
    const select = $('assistant-memory-backend');
    const note = $('assistant-memory-backend-note');
    const backend = data && typeof data === 'object' ? data : memoryBackendStatus;
    if (!select || !note) return;
    const rows = Array.isArray(backend?.backends) ? backend.backends : [];
    select.innerHTML = rows.map(item => `<option value="${escapeHtml(item.key || '')}"${String(backend?.active_backend || '') === String(item.key || '') ? ' selected' : ''}${item.available ? '' : ' disabled'}>${escapeHtml(item.label || item.key || 'Backend')}${item.available ? '' : ' (unavailable)'}</option>`).join('');
    const active = rows.find(item => String(item.key || '') === String(backend?.active_backend || ''));
    const label = String(backend?.active_backend_label || active?.label || active?.key || 'Memory backend').trim();
    const storage = String(backend?.storage_mode_label || '').trim();
    const message = String(backend?.ui_message || backend?.summary || '').trim();
    const downloads = String(backend?.downloads_note || (active?.needs_download ? 'May download model assets on first semantic use.' : 'No external model downloads.')).trim();
    const segments = [label, storage, message, downloads].filter(Boolean);
    note.textContent = segments.length ? segments.join(' · ') : 'Memory backend status will appear here.';
  }

  async function fetchAssistantMemoryBackendStatus() {
    const data = await safeFetchJson('/api/assistant/memory-backends');
    memoryBackendStatus = data;
    renderAssistantMemoryBackend(data);
    return data;
  }

  async function applyAssistantMemoryBackend() {
    const select = $('assistant-memory-backend');
    if (!select) return;
    setBusy('btn-assistant-apply-memory-backend', true, 'Applying...');
    try {
      const data = await safeFetchJson('/api/assistant/memory-backend-select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend_key: select.value, reindex: true }),
      });
      memoryBackendStatus = data;
      renderAssistantMemoryBackend(data);
      const indexed = Number(data?.reindex_result?.indexed || 0);
      setStatus('assistant-memory-status', `${data.message || 'Embedding backend updated.'} Reindexed ${indexed} chunk(s).`, 'ok');
      if (activeSession?.id) previewAssistantAdaptiveMemory({ quiet: true }).catch(() => {});
    } finally {
      setBusy('btn-assistant-apply-memory-backend', false);
    }
  }

  function renderSessionList() {
    const wrap = $('assistant-session-list');
    const query = trim($('assistant-session-search')?.value || '').toLowerCase();
    const projectFilter = trim($('assistant-project-filter')?.value || 'all');
    if (!wrap) return;
    wrap.innerHTML = '';
    const rows = (assistantSessions || []).filter(item => {
      const matchesProject = projectFilter === 'all'
        ? true
        : projectFilter === '__unassigned__'
          ? !trim(item.project_id || '')
          : trim(item.project_id || '') === projectFilter;
      if (!matchesProject) return false;
      if (!query) return true;
      const hay = `${item.title || ''} ${item.mode || ''} ${item.preview || ''} ${projectTitle(item.project_id || '')} ${item.helper_label || ''}`.toLowerCase();
      return hay.includes(query);
    });
    if (!rows.length) {
      const node = document.createElement('div');
      node.className = 'assistant-session-empty';
      node.textContent = 'No chats match that search.';
      wrap.appendChild(node);
      return;
    }
    rows.forEach(item => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `assistant-session-card${item.id === activeSession?.id ? ' active' : ''}`;
      btn.dataset.assistantSessionId = item.id;
      btn.innerHTML = `
        <div class="assistant-session-card-title">${escapeHtml(item.title || 'New assistant chat')}</div>
        <div class="assistant-session-card-meta">${escapeHtml(sessionSummary(item))}</div>
      `;
      wrap.appendChild(btn);
    });
  }

  function renderThreadHeader() {
    const title = $('assistant-thread-title');
    const meta = $('assistant-thread-meta');
    const helperMeta = $('assistant-helper-meta');
    if (!activeSession) {
      if (title) title.textContent = 'Assistant chat';
      if (meta) meta.textContent = 'No thread selected yet.';
      if (helperMeta) { helperMeta.textContent = ''; helperMeta.classList.add('hidden'); }
      renderContextSourceRow();
      return;
    }
    if (title) title.textContent = activeSession.title || 'Assistant chat';
    if (meta) meta.textContent = `${sessionSummary(activeSession)} · Assistant: ${assistantProfile?.assistant_name || 'Neo'}`;
    const helperLabel = trim(activeSession?.helper_context?.label || activeSession?.helper_context?.target || '');
    if (helperMeta) {
      if (helperLabel) {
        helperMeta.textContent = `Workspace helper: ${helperLabel}`;
        helperMeta.classList.remove('hidden');
      } else {
        helperMeta.textContent = '';
        helperMeta.classList.add('hidden');
      }
    }
    renderContextSourceRow();
  }

  function renderContextShelf() {
    const wrap = $('assistant-context-list');
    if (!wrap) return;
    wrap.innerHTML = '';
    const items = Array.isArray(activeSession?.context_items) ? activeSession.context_items : [];
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-session-empty';
      empty.textContent = 'No uploaded context yet. Add a text file when this thread needs extra grounded context.';
      wrap.appendChild(empty);
      return;
    }
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'card-lite assistant-context-item';
      const preview = trim(String(item.content || '').replace(/\s+/g, ' ')).slice(0, 180);
      card.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:flex-start;">
          <div>
            <div class="stat-title">${escapeHtml(item.title || 'Context item')}</div>
            <div class="mini-note" style="margin-top:6px;">${escapeHtml(String(item.source_kind || 'note').replace(/_/g, ' ').toUpperCase())} · ${Number(item.char_count || (item.content || '').length || 0)} chars</div>
          </div>
          <button class="btn btn-small" data-assistant-remove-context="${escapeHtml(item.id || '')}" type="button">Remove</button>
        </div>
        <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(preview)}${(item.content || '').length > 180 ? '…' : ''}</div>
      `;
      wrap.appendChild(card);
    });
  }


  function renderThreadMemory() {
    const area = $('assistant-memory-summary');
    const btn = $('btn-assistant-refresh-memory');
    if (!area) return;
    if (!activeSession) {
      area.value = '';
      area.placeholder = 'Thread memory will appear here once the conversation gets longer.';
      if (btn) btn.disabled = true;
      setStatus('assistant-memory-status', 'Select a thread to manage rolling memory.', '');
      renderAssistantMemoryInspector(null);
      return;
    }
    const summary = trim(activeSession.memory_summary || '');
    const updatedAt = trim(activeSession.memory_updated_at || '');
    area.placeholder = 'Thread memory will appear here once the conversation gets longer.';
    area.value = summary || '';
    if (btn) btn.disabled = false;
    renderAssistantMemoryInspector(null);
    if (summary) {
      const updatedText = updatedAt ? ` Updated ${formatDateTime(updatedAt)}.` : '';
      setStatus('assistant-memory-status', `Older turns are compressed into rolling memory.${updatedText}`, 'ok');
    } else {
      const count = Array.isArray(activeSession.messages) ? activeSession.messages.length : 0;
      setStatus('assistant-memory-status', count > 10 ? 'Save or refresh to rebuild the rolling memory summary.' : 'This thread is still short enough to use raw recent messages without a memory summary yet.', '');
    }
  }

  async function refreshThreadMemory() {
    if (!activeSession) {
      setStatus('assistant-memory-status', 'Select a thread first.', 'warn');
      return;
    }
    const btn = $('btn-assistant-refresh-memory');
    setBusy('btn-assistant-refresh-memory', true, 'Refreshing...');
    try {
      await saveActiveSession({ silent: true });
      renderThreadMemory();
      renderContextSourceRow();
      setStatus('assistant-memory-status', trim(activeSession?.memory_summary || '') ? 'Rolling memory summary refreshed.' : 'This thread is still short enough that a rolling memory summary is not needed yet.', trim(activeSession?.memory_summary || '') ? 'ok' : '');
    } catch (err) {
      setStatus('assistant-memory-status', err?.message || 'Could not refresh the rolling memory summary.', 'warn');
      throw err;
    } finally {
      setBusy('btn-assistant-refresh-memory', false);
    }
  }


  function renderAssistantMemoryInspector(data = null) {
    const preview = $('assistant-retrieved-memory-preview');
    const list = $('assistant-memory-item-list');
    const previewBtn = $('btn-assistant-preview-memory');
    const repairBtn = $('btn-assistant-repair-memory');
    const resetThreadBtn = $('btn-assistant-reset-session-memory');
    const resetProjectBtn = $('btn-assistant-reset-project-memory');
    if (previewBtn) previewBtn.disabled = !activeSession;
    if (repairBtn) repairBtn.disabled = !activeSession;
    if (resetThreadBtn) resetThreadBtn.disabled = !activeSession;
    if (resetProjectBtn) resetProjectBtn.disabled = !trim(activeSession?.project_id || '');
    if (!preview || !list) return;
    if (!activeSession) {
      preview.value = '';
      preview.placeholder = 'Preview what Neo would inject from adaptive memory for this thread.';
      list.innerHTML = '';
      return;
    }
    const retrieval = data && typeof data === 'object' ? (data.retrieval_preview || {}) : {};
    if (data?.backend) { memoryBackendStatus = data.backend; renderAssistantMemoryBackend(data.backend); }
    const retrievalItems = Array.isArray(retrieval.items) ? retrieval.items : [];
    const recentChunks = Array.isArray(data?.recent_chunks) ? data.recent_chunks : [];
    const summaries = Array.isArray(data?.summaries) ? data.summaries : [];
    const writes = Array.isArray(data?.recent_writes) ? data.recent_writes : [];
    preview.placeholder = 'Preview what Neo would inject from adaptive memory for this thread.';
    preview.value = trim(retrieval.summary || '');
    const cards = [];
    summaries.slice(0, 2).forEach(item => {
      cards.push(`
        <div class="card-lite assistant-context-item">
          <div class="stat-title">${escapeHtml(String(item.summary_type || 'summary').replace(/_/g, ' '))}</div>
          <div class="mini-note" style="margin-top:6px;">Scope: ${escapeHtml(item.scope_type || '')}${item.scope_id ? ` · ${escapeHtml(item.scope_id)}` : ''}</div>
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
            <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.entity_type || '')}${item.updated_at ? ` · ${escapeHtml(formatDateTime(item.updated_at))}` : ''}</div>
            <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.document || '').slice(0, 220))}${String(item.document || '').length > 220 ? '…' : ''}</div>
          </div>`);
      });
    }
    writes.slice(0, 2).forEach(item => {
      cards.push(`
        <div class="card-lite assistant-context-item">
          <div class="stat-title">Write log · ${escapeHtml(item.operation || '')}</div>
          <div class="mini-note" style="margin-top:6px;">${escapeHtml(item.entity_type || '')}${item.created_at ? ` · ${escapeHtml(formatDateTime(item.created_at))}` : ''}</div>
          <div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(JSON.stringify(item.details || {}).slice(0, 220))}${JSON.stringify(item.details || {}).length > 220 ? '…' : ''}</div>
        </div>`);
    });
    list.innerHTML = cards.length ? cards.join('') : '<div class="assistant-session-empty">No adaptive memory preview yet. Use Preview adaptive memory to inspect what Neo would carry forward.</div>';
  }

  async function previewAssistantAdaptiveMemory(options = {}) {
    if (!activeSession?.id) {
      renderAssistantMemoryInspector(null);
      setStatus('assistant-memory-status', 'Select a thread first.', 'warn');
      return null;
    }
    const q = trim(options.query || $('assistant-composer')?.value || '');
    const data = await safeFetchJson(`/api/assistant/memory-inspect?session_id=${encodeURIComponent(activeSession.id)}&q=${encodeURIComponent(q)}`);
    renderAssistantMemoryInspector(data);
    if (!options.quiet) {
      const counts = data?.counts || {};
      const dropped = Number(data?.retrieval_preview?.diagnostics?.dropped?.length || 0);
      const backendLabel = String(data?.backend?.active_backend_label || memoryBackendStatus?.active_backend_label || data?.backend?.active_backend || 'Hashing local');
      const storageLabel = String(data?.backend?.storage_mode_label || memoryBackendStatus?.storage_mode_label || '').trim();
      setStatus('assistant-memory-status', `Adaptive memory preview ready. ${Number(data?.retrieval_preview?.item_count || 0)} retrieved item(s) from ${Number(data?.retrieval_preview?.candidate_count || 0)} candidate(s), ${dropped} dropped by ranking rules. Memory path: ${backendLabel}${storageLabel ? ` · ${storageLabel}` : ''}. Profile ${Number(counts.profile || 0)} · Project ${Number(counts.project || 0)} · Thread ${Number(counts.session || 0)}.`, 'ok');
    }
    return data;
  }

  async function repairAssistantAdaptiveMemory() {
    if (!activeSession?.id) {
      setStatus('assistant-memory-status', 'Select a thread first.', 'warn');
      return;
    }
    setBusy('btn-assistant-repair-memory', true, 'Rebuilding...');
    try {
      const data = await safeFetchJson('/api/assistant/memory-repair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSession.id, q: trim($('assistant-composer')?.value || '') }),
      });
      renderAssistantMemoryInspector(data);
      setStatus('assistant-memory-status', data.message || 'Assistant adaptive memory rebuilt.', 'ok');
    } finally {
      setBusy('btn-assistant-repair-memory', false);
    }
  }

  async function resetAssistantAdaptiveMemory(scopeType) {
    if (!activeSession?.id) {
      setStatus('assistant-memory-status', 'Select a thread first.', 'warn');
      return;
    }
    if (scopeType === 'project' && !trim(activeSession.project_id || '')) {
      setStatus('assistant-memory-status', 'This thread is not linked to a project yet.', 'warn');
      return;
    }
    setBusy(scopeType === 'project' ? 'btn-assistant-reset-project-memory' : 'btn-assistant-reset-session-memory', true, 'Resetting...');
    try {
      const data = await safeFetchJson('/api/assistant/memory-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope_type: scopeType, session_id: activeSession.id, project_id: activeSession.project_id || '', chunk_type: trim($('assistant-memory-chunk-type-filter')?.value || '') }),
      });
      if (scopeType === 'session') {
        const refreshed = await safeFetchJson(`/api/assistant/session-load?session_id=${encodeURIComponent(activeSession.id)}`);
        activeSession = refreshed.session || activeSession;
        if ($('assistant-composer')) $('assistant-composer').value = activeSession?.draft || '';
        renderSurface();
      }
      renderAssistantMemoryInspector(data);
      setStatus('assistant-memory-status', data.message || `Assistant ${scopeType} memory reset.`, 'ok');
    } finally {
      setBusy(scopeType === 'project' ? 'btn-assistant-reset-project-memory' : 'btn-assistant-reset-session-memory', false);
    }
  }

  function renderMemoryAdmin(data = null) {
    const overviewWrap = $('assistant-memory-admin-overview');
    const conflictWrap = $('assistant-memory-conflict-list');
    const itemWrap = $('assistant-memory-admin-item-list');
    const laneSelect = $('assistant-memory-admin-lane');
    const chunkTypeSelect = $('assistant-memory-admin-chunk-type');
    const queryInput = $('assistant-memory-admin-query');
    const includeSuppressed = $('assistant-memory-admin-include-suppressed');
    const payload = data && typeof data === 'object' ? data : memoryAdminState;
    if (laneSelect && payload?.filters) laneSelect.value = payload.filters.lane || '';
    if (chunkTypeSelect && payload?.filters) chunkTypeSelect.value = payload.filters.chunk_type || '';
    if (queryInput && payload?.filters && document.activeElement !== queryInput) queryInput.value = payload.filters.q || '';
    if (includeSuppressed && payload?.filters) includeSuppressed.checked = Boolean(payload.filters.include_suppressed);
    if (payload?.backend) { memoryBackendStatus = payload.backend; renderAssistantMemoryBackend(payload.backend); }
    if (overviewWrap) {
      const totals = payload?.overview?.totals || {};
      const laneTypes = payload?.overview?.by_lane_chunk_type || {};
      const assistantTypes = Object.entries(laneTypes.assistant || {}).slice(0, 4).map(([key, value]) => `${String(key).replace(/_/g, ' ')} ${Number(value || 0)}`).join(' · ');
      const roleplayTypes = Object.entries(laneTypes.roleplay || {}).slice(0, 4).map(([key, value]) => `${String(key).replace(/_/g, ' ')} ${Number(value || 0)}`).join(' · ');
      overviewWrap.innerHTML = `
        <div class="card-lite"><div class="stat-title">Active chunks</div><div class="display-value" style="font-size:1.5rem; margin-top:6px;">${Number(totals.all || 0)}</div><div class="mini-note" style="margin-top:8px;">Pinned ${Number(totals.pinned || 0)} · Suppressed ${Number(totals.suppressed || 0)}</div></div>
        <div class="card-lite"><div class="stat-title">Assistant lane</div><div class="display-value" style="font-size:1.5rem; margin-top:6px;">${Number(totals.assistant || 0)}</div><div class="mini-note" style="margin-top:8px;">${escapeHtml(assistantTypes || 'No assistant chunk data yet.')}</div></div>
        <div class="card-lite"><div class="stat-title">Roleplay lane</div><div class="display-value" style="font-size:1.5rem; margin-top:6px;">${Number(totals.roleplay || 0)}</div><div class="mini-note" style="margin-top:8px;">${escapeHtml(roleplayTypes || 'No roleplay chunk data yet.')}</div></div>`;
    }
    if (conflictWrap) {
      const conflicts = Array.isArray(payload?.conflicts) ? payload.conflicts : [];
      conflictWrap.innerHTML = conflicts.length ? conflicts.map(conflict => {
        const items = Array.isArray(conflict.items) ? conflict.items : [];
        const buttons = items.map(item => `<button class="btn btn-small" data-memory-conflict-keep="${escapeHtml(item.chunk_id || '')}" data-memory-conflict-drop="${escapeHtml((items.filter(other => other.chunk_id !== item.chunk_id).map(other => other.chunk_id || '')).join(','))}" type="button">Keep ${escapeHtml(String(item.chunk_type || 'memory').replace(/_/g, ' '))}</button>`).join(' ');
        return `<div class="card-lite assistant-context-item"><div class="row-between" style="gap:10px; align-items:flex-start;"><div><div class="stat-title">Conflict · ${escapeHtml(String(conflict.chunk_type || 'memory').replace(/_/g, ' '))}</div><div class="mini-note" style="margin-top:6px;">${escapeHtml(conflict.lane || '')} · ${escapeHtml(conflict.scope_type || '')}${conflict.scope_id ? ` · ${escapeHtml(conflict.scope_id)}` : ''} · similarity ${Number(conflict.similarity || 0).toFixed(2)} · ${escapeHtml(conflict.reason || '')}</div></div><div class="row" style="gap:8px; flex-wrap:wrap;">${buttons}</div></div><div class="grid grid-2" style="margin-top:12px; gap:12px;">${items.map(item => `<div class="card-lite" style="padding:12px; border-style:dashed;"><div class="stat-title">${escapeHtml(String(item.chunk_type || 'memory').replace(/_/g, ' '))}${item.is_pinned ? ' · pinned' : ''}</div><div class="mini-note" style="margin-top:6px;">${escapeHtml(item.entity_type || '')}${item.updated_at ? ` · ${escapeHtml(formatDateTime(item.updated_at))}` : ''}</div><div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.document || '').slice(0, 220))}${String(item.document || '').length > 220 ? '…' : ''}</div></div>`).join('')}</div></div>`;
      }).join('') : '<div class="assistant-session-empty">No obvious memory conflicts detected right now.</div>';
    }
    if (itemWrap) {
      const items = Array.isArray(payload?.items) ? payload.items : [];
      itemWrap.innerHTML = items.length ? items.map(item => {
        const meta = item.metadata || {};
        const pinLabel = item.is_pinned ? 'Unpin' : 'Pin';
        const suppressLabel = item.is_suppressed ? 'Restore' : 'Suppress';
        const note = trim(item.pin_note || item.suppressed_reason || meta.pin_note || '');
        return `<div class="card-lite assistant-context-item"><div class="row-between" style="gap:10px; align-items:flex-start;"><div><div class="stat-title">${escapeHtml(String(item.chunk_type || 'memory').replace(/_/g, ' '))}${item.is_pinned ? ' · pinned' : ''}${item.is_suppressed ? ' · suppressed' : ''}</div><div class="mini-note" style="margin-top:6px;">${escapeHtml(item.lane || '')} · ${escapeHtml(item.entity_type || '')}${item.entity_id ? `:${escapeHtml(item.entity_id)}` : ''} · ${escapeHtml(item.scope_type || '')}${item.scope_id ? `:${escapeHtml(item.scope_id)}` : ''} · importance ${Number(item.importance || 0).toFixed(2)}</div>${note ? `<div class="mini-note" style="margin-top:6px;">${escapeHtml(note)}</div>` : ''}</div><div class="row" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;"><button class="btn btn-small" data-memory-pin-toggle="${escapeHtml(item.chunk_id || '')}" data-memory-pin-state="${item.is_pinned ? '0' : '1'}" type="button">${pinLabel}</button><button class="btn btn-small" data-memory-suppress-toggle="${escapeHtml(item.chunk_id || '')}" data-memory-suppress-state="${item.is_suppressed ? '0' : '1'}" type="button">${suppressLabel}</button></div></div><div class="muted small" style="margin-top:10px; line-height:1.5;">${escapeHtml(String(item.document || '').slice(0, 320))}${String(item.document || '').length > 320 ? '…' : ''}</div></div>`;
      }).join('') : '<div class="assistant-session-empty">No memory items match this filter yet.</div>';
    }
  }

  async function refreshMemoryAdmin(options = {}) {
    setBusy('btn-assistant-refresh-memory-admin', true, 'Refreshing...');
    try {
      const lane = trim((options.lane ?? ($('assistant-memory-admin-lane')?.value || '')));
      const chunkType = trim((options.chunkType ?? ($('assistant-memory-admin-chunk-type')?.value || '')));
      const q = trim((options.query ?? ($('assistant-memory-admin-query')?.value || '')));
      const includeSuppressed = Boolean(options.includeSuppressed ?? Boolean($('assistant-memory-admin-include-suppressed')?.checked));
      const data = await safeFetchJson(`/api/assistant/memory-admin?lane=${encodeURIComponent(lane)}&chunk_type=${encodeURIComponent(chunkType)}&q=${encodeURIComponent(q)}&include_suppressed=${includeSuppressed ? 'true' : 'false'}`);
      memoryAdminState = data;
      renderMemoryAdmin(data);
      if (!options.quiet) setStatus('assistant-memory-admin-status', `Global memory ready. ${Number(data?.items?.length || 0)} item(s), ${Number(data?.conflicts?.length || 0)} potential conflict(s).`, 'ok');
      return data;
    } finally {
      setBusy('btn-assistant-refresh-memory-admin', false);
    }
  }

  async function updateMemoryItemState(chunkId, updates = {}) {
    if (!chunkId) return;
    const data = await safeFetchJson('/api/assistant/memory-item-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chunk_id: chunkId, ...updates, reindex: true }),
    });
    memoryAdminState = data;
    renderMemoryAdmin(data);
    if (activeSession?.id) previewAssistantAdaptiveMemory({ quiet: true }).catch(() => {});
    setStatus('assistant-memory-admin-status', data.message || 'Memory item updated.', 'ok');
    return data;
  }

  async function resolveMemoryConflict(preferredChunkId, rejectedChunkIds = []) {
    if (!preferredChunkId || !rejectedChunkIds.length) return;
    const data = await safeFetchJson('/api/assistant/memory-conflict-resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferred_chunk_id: preferredChunkId, rejected_chunk_ids: rejectedChunkIds, reason: 'manual_conflict_resolution' }),
    });
    memoryAdminState = data;
    renderMemoryAdmin(data);
    if (activeSession?.id) previewAssistantAdaptiveMemory({ quiet: true }).catch(() => {});
    setStatus('assistant-memory-admin-status', data.message || 'Memory conflict resolved.', 'ok');
    return data;
  }

  function renderThreadSettings() {
    const el = ids();
    if (!activeSession) {
      if (el.projectSelect) el.projectSelect.value = '';
      if (el.mode) el.mode.value = assistantProfile?.default_mode || 'general';
      if (el.threadInstruction) el.threadInstruction.value = '';
      if (el.contextNote) el.contextNote.value = '';
      const wrap = $('assistant-context-list');
      if (wrap) wrap.innerHTML = '';
      renderProjectDashboard();
      renderThreadMemory();
      return;
    }
    renderModeSelects();
    if (el.projectSelect) el.projectSelect.value = activeSession.project_id || '';
    if (el.contextNote) el.contextNote.value = activeSession.context_note || '';
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderProjectDashboard();
    renderContextShelf();
    renderThreadMemory();
    if (el.mode) el.mode.value = activeSession.mode || assistantProfile?.default_mode || 'general';
    if (el.threadInstruction) el.threadInstruction.value = activeSession.thread_instruction || '';
    if (el.maxTokens) el.maxTokens.value = activeSession.params?.max_tokens ?? activeModeConfig(activeSession.mode).max_tokens;
    if (el.temperature) el.temperature.value = activeSession.params?.temperature ?? activeModeConfig(activeSession.mode).temperature;
    if (el.topP) el.topP.value = activeSession.params?.top_p ?? activeModeConfig(activeSession.mode).top_p;
    if (el.topK) el.topK.value = activeSession.params?.top_k ?? activeModeConfig(activeSession.mode).top_k;
    syncModeMeta();
    updateActiveModelNote();
  }

  function renderMessages() {
    const thread = $('assistant-thread');
    const empty = $('assistant-empty-state');
    if (!thread) return;
    const previousDistanceFromBottom = Math.max(0, thread.scrollHeight - thread.scrollTop - thread.clientHeight);
    const shouldFollow = assistantAutoFollow || isNearBottom(thread, 96);
    thread.querySelectorAll('.assistant-message').forEach(node => node.remove());
    const messages = Array.isArray(activeSession?.messages) ? activeSession.messages : [];
    if (!messages.length) {
      empty?.classList.remove('hidden');
      syncJumpLatestVisibility(true);
      return;
    }
    empty?.classList.add('hidden');
    messages.forEach(message => {
      const role = message?.role === 'assistant' ? 'assistant' : 'user';
      const card = document.createElement('div');
      card.className = `assistant-message role-${role}${message?.meta?.streaming ? ' is-streaming' : ''}`;
      card.dataset.messageId = message.id || '';
      const roleplayHelperActions = role === 'assistant' && isRoleplayHelperSession()
        ? `
            <button class="btn btn-small" data-assistant-apply-roleplay data-message-id="${escapeHtml(message.id || '')}" type="button">Apply to Roleplay</button>
            <button class="btn btn-small" data-assistant-open-roleplay data-message-id="${escapeHtml(message.id || '')}" type="button">Apply + Open</button>`
        : '';
      const workspaceHelperActions = role === 'assistant' && isDirectWorkspaceHelperSession()
        ? `
            <button class="btn btn-small" data-assistant-apply-workspace data-message-id="${escapeHtml(message.id || '')}" type="button">Apply to ${escapeHtml(workspaceHelperLabel())}</button>
            <button class="btn btn-small" data-assistant-open-workspace data-message-id="${escapeHtml(message.id || '')}" type="button">Apply + Open</button>`
        : '';
      const transformActions = role === 'assistant'
        ? `
          <div class="assistant-message-actions">
            ${roleplayHelperActions}
            ${workspaceHelperActions}
            <button class="btn btn-small" data-assistant-transform="shorter" data-message-id="${escapeHtml(message.id || '')}" type="button">Shorter</button>
            <button class="btn btn-small" data-assistant-transform="warmer" data-message-id="${escapeHtml(message.id || '')}" type="button">Warmer</button>
            <button class="btn btn-small" data-assistant-transform="professional" data-message-id="${escapeHtml(message.id || '')}" type="button">Professional</button>
            <button class="btn btn-small" data-assistant-transform="client_reply" data-message-id="${escapeHtml(message.id || '')}" type="button">Client reply</button>
            <button class="btn btn-small" data-assistant-transform="email" data-message-id="${escapeHtml(message.id || '')}" type="button">Email</button>
            <button class="btn btn-small" data-assistant-transform="bullets" data-message-id="${escapeHtml(message.id || '')}" type="button">Bullets</button>
            <button class="btn btn-small" data-assistant-transform="checklist" data-message-id="${escapeHtml(message.id || '')}" type="button">Checklist</button>
            <button class="btn btn-small" data-assistant-transform="brief" data-message-id="${escapeHtml(message.id || '')}" type="button">Brief</button>
            <button class="btn btn-small" data-assistant-transform="caption" data-message-id="${escapeHtml(message.id || '')}" type="button">Caption</button>
            <button class="btn btn-small" data-assistant-transform="prompt" data-message-id="${escapeHtml(message.id || '')}" type="button">Prompt</button>
            <button class="btn btn-small" data-assistant-export="prompt" data-message-id="${escapeHtml(message.id || '')}" type="button">To Prompt</button>
            <button class="btn btn-small" data-assistant-export="caption" data-message-id="${escapeHtml(message.id || '')}" type="button">To Caption</button>
            <button class="btn btn-small" data-assistant-export="generation" data-message-id="${escapeHtml(message.id || '')}" type="button">To Generation</button>
            <button class="btn btn-small" data-assistant-copy-message data-message-id="${escapeHtml(message.id || '')}" type="button">Copy</button>
          </div>`
        : `<div class="assistant-message-actions"><button class="btn btn-small" data-assistant-copy-message data-message-id="${escapeHtml(message.id || '')}" type="button">Copy</button></div>`;
      card.innerHTML = `
        <div class="assistant-message-meta">${role === 'assistant' ? escapeHtml(assistantProfile?.assistant_name || 'Assistant') : 'You'} · ${escapeHtml(formatDateTime(message?.created_at || ''))}${message?.meta?.transform_label ? ` · ${escapeHtml(message.meta.transform_label)}` : ''}${message?.meta?.finish_reason === 'length' ? ' · Clipped' : ''}${message?.meta?.finish_reason === 'partial' ? ' · Partial' : ''}${message?.meta?.finish_reason === 'stopped' ? ' · Stopped' : ''}</div>
        <div class="assistant-message-body">${escapeHtml(String(message?.content || '')).replace(/\n/g, '<br/>')}</div>
        ${transformActions}
      `;
      thread.appendChild(card);
    });
    window.requestAnimationFrame(() => {
      if (!thread) return;
      if (shouldFollow) {
        scrollThreadToLatest('auto');
      } else {
        thread.scrollTop = Math.max(0, thread.scrollHeight - thread.clientHeight - previousDistanceFromBottom);
        syncJumpLatestVisibility();
      }
    });
  }

  function renderSurface() {
    renderProfile();
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderProjectDashboard();
    renderSessionList();
    renderThreadHeader();
    renderThreadSettings();
    renderThreadMemory();
    renderMessages();
    updateBackendNote();
    updateStreamingState(isStreaming);
  }

  function syncModeMeta() {
    const modeKey = trim($('assistant-mode')?.value || activeSession?.mode || assistantProfile?.default_mode || 'general') || 'general';
    const mode = activeModeConfig(modeKey);
    if ($('assistant-mode-meta')) $('assistant-mode-meta').textContent = mode.description || '';
  }

  function collectProfileFromDom() {
    return {
      assistant_name: trim($('assistant-profile-name')?.value || 'Neo') || 'Neo',
      user_name: trim($('assistant-profile-user-name')?.value || ''),
      address_style: trim($('assistant-profile-address-style')?.value || 'adaptive') || 'adaptive',
      default_mode: trim($('assistant-profile-default-mode')?.value || 'general') || 'general',
      response_detail: trim($('assistant-profile-response-detail')?.value || 'balanced') || 'balanced',
      support_style: trim($('assistant-profile-support-style')?.value || 'balanced') || 'balanced',
      about_user: trim($('assistant-profile-about-user')?.value || ''),
      preferences: trim($('assistant-profile-preferences')?.value || ''),
      avoid: trim($('assistant-profile-avoid')?.value || ''),
    };
  }

  function applyProfileToLocal(profile) {
    assistantProfile = { ...(assistantProfile || {}), ...(profile || {}) };
  }

  function collectThreadFromDom() {
    if (!activeSession) return null;
    return {
      ...activeSession,
      project_id: trim($('assistant-project-select')?.value || activeSession.project_id || ''),
      context_note: String($('assistant-context-note')?.value || activeSession.context_note || ''),
      context_items: Array.isArray(activeSession.context_items) ? activeSession.context_items : [],
      mode: trim($('assistant-mode')?.value || activeSession.mode || assistantProfile?.default_mode || 'general') || 'general',
      thread_instruction: String($('assistant-thread-instruction')?.value || ''),
      params: {
        max_tokens: Number($('assistant-max-tokens')?.value || activeModeConfig(activeSession.mode).max_tokens || 640),
        temperature: Number($('assistant-temperature')?.value || activeModeConfig(activeSession.mode).temperature || 0.7),
        top_p: Number($('assistant-top-p')?.value || activeModeConfig(activeSession.mode).top_p || 0.92),
        top_k: Number($('assistant-top-k')?.value || activeModeConfig(activeSession.mode).top_k || 60),
      },
      draft: String($('assistant-composer')?.value || activeSession.draft || ''),
    };
  }

  function updateActiveModelNote() {
    const model = typeof currentModel === 'function' ? currentModel() : 'default';
    if ($('assistant-active-model')) $('assistant-active-model').textContent = model || 'default';
    if ($('assistant-active-model-meta')) {
      const hasTextBackend = typeof window.isBackendRoleConnected === 'function' ? !!window.isBackendRoleConnected('text') : false;
      $('assistant-active-model-meta').textContent = hasTextBackend
        ? 'Assistant uses the shared active text model right now.'
        : 'Connect a Text Backend so the shared active model can answer live.';
    }
  }

  function updateBackendNote() {
    const textConnected = typeof getRoleSession === 'function' ? !!getRoleSession('text')?.connected : false;
    if (typeof updateBackendRequiredNote === 'function') {
      updateBackendRequiredNote(
        'assistant-text-backend-note',
        'assistant-text-backend-note-body',
        textConnected,
        'Text backend connected. Neo Assistant is ready for live replies, rewrites, and transforms.',
        'Connect a Text Backend to send live assistant messages. Profile setup, thread management, and saved drafts still stay usable locally.',
      );
    }
    updateActiveModelNote();
  }

  async function fetchBootstrap() {
    const data = await safeFetchJson('/api/assistant/bootstrap');
    assistantProfile = data.profile || {};
    assistantModes = data.modes || {};
    assistantProjects = Array.isArray(data.projects) ? data.projects : [];
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSurface();
    if (!assistantSessions.length) {
      await createSession({ mode: assistantProfile?.default_mode || 'general', title: 'New assistant chat' }, { silent: true });
      return;
    }
    const targetId = activeSession?.id || assistantSessions[0]?.id || '';
    if (targetId) await loadSession(targetId, { silent: true });
  }

  async function loadSession(sessionId, options = {}) {
    if (!sessionId) return;
    const data = await safeFetchJson(`/api/assistant/session-load?session_id=${encodeURIComponent(sessionId)}`);
    activeSession = data.session || null;
    const meta = assistantSessions.find(item => item.id === sessionId);
    if (meta && activeSession) Object.assign(meta, { ...meta, ...activeSession });
    if ($('assistant-composer')) $('assistant-composer').value = activeSession?.draft || '';
    renderSurface();
    previewAssistantAdaptiveMemory({ quiet: true }).catch(() => renderAssistantMemoryInspector(null));
    if (!options.silent) setStatus('assistant-session-status', `${activeSession?.title || 'Assistant chat'} loaded.`, 'ok');
  }

  async function createSession(payload = {}, options = {}) {
    const data = await safeFetchJson('/api/assistant/session-create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}) });
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    activeSession = data.session || null;
    renderSurface();
    if ($('assistant-composer')) $('assistant-composer').value = activeSession?.draft || '';
    if (!options.silent) setStatus('assistant-session-status', data.message || 'Assistant chat created.', 'ok');
  }

  async function saveActiveSession(options = {}) {
    if (!activeSession) return null;
    const payload = collectThreadFromDom();
    if (!payload) return null;
    const data = await safeFetchJson('/api/assistant/session-save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    activeSession = data.session || activeSession;
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    renderSurface();
    if (!options.silent) setStatus('assistant-session-status', data.message || 'Assistant chat saved.', 'ok');
    return activeSession;
  }

  function scheduleSessionSave() {
    if (activeSaveTimer) window.clearTimeout(activeSaveTimer);
    activeSaveTimer = window.setTimeout(() => {
      saveActiveSession({ silent: true }).catch(err => setStatus('assistant-session-status', err.message || 'Could not save the chat.', 'warn'));
    }, 550);
  }

  async function saveProfileNow(options = {}) {
    const payload = collectProfileFromDom();
    const data = await safeFetchJson('/api/assistant/profile-save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    applyProfileToLocal(data.profile || payload);
    renderSurface();
    if (!options.silent) setStatus('assistant-profile-status', data.message || 'Assistant profile saved.', 'ok');
  }

  function scheduleProfileSave() {
    if (profileSaveTimer) window.clearTimeout(profileSaveTimer);
    profileSaveTimer = window.setTimeout(() => {
      saveProfileNow({ silent: true }).catch(err => setStatus('assistant-profile-status', err.message || 'Could not save the assistant profile.', 'warn'));
    }, 600);
  }



  async function createProject() {
    const title = window.prompt('New assistant project name:', 'New project');
    if (title === null) return;
    const clean = trim(title);
    if (!clean) return;
    const data = await safeFetchJson('/api/assistant/project-create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: clean }) });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    renderSurface();
    setStatus('assistant-session-status', data.message || 'Assistant project created.', 'ok');
  }

  async function renameSelectedProject() {
    const projectId = trim($('assistant-project-filter')?.value || activeSession?.project_id || '');
    if (!projectId || projectId === 'all' || projectId === '__unassigned__') {
      setStatus('assistant-session-status', 'Pick a real project first.', 'warn');
      return;
    }
    const current = projectTitle(projectId) || 'Project';
    const title = window.prompt('Rename this assistant project:', current);
    if (title === null) return;
    const clean = trim(title);
    if (!clean) return;
    const data = await safeFetchJson('/api/assistant/project-rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: projectId, title: clean }) });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    if (activeSession?.project_id === projectId) activeSession.project_id = projectId;
    renderSurface();
    setStatus('assistant-session-status', data.message || 'Assistant project renamed.', 'ok');
  }

  async function deleteSelectedProject() {
    const projectId = trim($('assistant-project-filter')?.value || activeSession?.project_id || '');
    if (!projectId || projectId === 'all' || projectId === '__unassigned__') {
      setStatus('assistant-session-status', 'Pick a real project first.', 'warn');
      return;
    }
    const current = projectTitle(projectId) || 'this project';
    if (!window.confirm(`Delete project "${current}"? Linked chats will become unassigned.`)) return;
    const data = await safeFetchJson('/api/assistant/project-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: projectId }) });
    assistantProjects = Array.isArray(data.projects) ? data.projects : [];
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    if (activeSession?.project_id === projectId) activeSession.project_id = '';
    if ($('assistant-project-filter')) $('assistant-project-filter').value = 'all';
    renderSurface();
    setStatus('assistant-session-status', data.message || 'Assistant project deleted.', 'ok');
  }

  async function uploadContextFile() {
    if (!activeSession) {
      setStatus('assistant-context-status', 'Open or create a chat first.', 'warn');
      return;
    }
    const input = $('assistant-context-upload');
    const file = input?.files?.[0];
    if (!file) {
      setStatus('assistant-context-status', 'Choose a text file first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('file', file);
    const data = await safeFetchJson('/api/assistant/context-upload', { method: 'POST', body: form });
    const item = data.item || null;
    if (!item) {
      setStatus('assistant-context-status', 'Could not read that context file.', 'warn');
      return;
    }
    activeSession.context_items = Array.isArray(activeSession.context_items) ? activeSession.context_items : [];
    activeSession.context_items = activeSession.context_items.concat([{
      id: `ctx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      title: item.title || file.name || 'Context item',
      source_kind: item.source_kind || 'text',
      content: String(item.content || ''),
      created_at: nowIso(),
      char_count: Number(item.char_count || String(item.content || '').length || 0),
    }]).slice(-8);
    if (input) input.value = '';
    renderContextShelf();
    renderSessionList();
    scheduleSessionSave();
    setStatus('assistant-context-status', data.message || 'Context file added to this thread.', 'ok');
  }

  async function addImageBridgeContext() {
    if (!activeSession) {
      setStatus('assistant-image-bridge-status', 'Open or create a chat first.', 'warn');
      return;
    }
    const input = $('assistant-image-bridge-upload');
    const file = input?.files?.[0];
    const focus = trim($('assistant-image-bridge-instruction')?.value || '');
    if (!file) {
      setStatus('assistant-image-bridge-status', 'Choose an image first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('image', file);
    form.append('model', typeof currentModel === 'function' ? currentModel() : 'default');
    form.append('prompt_style', 'Descriptive');
    form.append('caption_length', 'medium');
    form.append('output_style', 'Auto (match input)');
    form.append('caption_mode', 'full_image');
    form.append('detail_level', 'detailed');
    if (focus) form.append('custom_prompt', focus);
    setBusy('btn-assistant-add-image-bridge', true, 'Describing...');
    setStatus('assistant-image-bridge-status', 'Turning the image into Assistant context...', '');
    try {
      const data = await safeFetchJson('/api/caption-image', { method: 'POST', body: form });
      const caption = trim(data.caption || '');
      if (!caption) {
        setStatus('assistant-image-bridge-status', 'No image context was returned.', 'warn');
        return;
      }
      const parts = [`Image file: ${file.name}`];
      if (focus) parts.push(`Focus: ${focus}`);
      parts.push(`Image description:
${caption}`);
      const content = parts.join('\n\n');
      activeSession.context_items = Array.isArray(activeSession.context_items) ? activeSession.context_items : [];
      activeSession.context_items = activeSession.context_items.concat([{
        id: `img_ctx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        title: `Image context: ${file.name}`,
        source_kind: 'image_bridge',
        content,
        created_at: nowIso(),
        char_count: Number(content.length || 0),
      }]).slice(-8);
      if (input) input.value = '';
      renderContextShelf();
      renderThreadHeader();
      renderSessionList();
      scheduleSessionSave();
      setStatus('assistant-image-bridge-status', data.warning ? `Image context added. ${data.warning}` : 'Image context added to this thread.', data.warning ? 'warn' : 'ok');
      setStatus('assistant-context-status', 'Image context added to the thread context shelf.', 'ok');
    } catch (err) {
      setStatus('assistant-image-bridge-status', err?.message || 'Could not turn that image into Assistant context.', 'warn');
      throw err;
    } finally {
      setBusy('btn-assistant-add-image-bridge', false);
    }
  }

  function removeContextItem(itemId) {
    if (!activeSession || !itemId) return;
    activeSession.context_items = (activeSession.context_items || []).filter(item => item.id !== itemId);
    renderContextShelf();
    renderSessionList();
    scheduleSessionSave();
    setStatus('assistant-context-status', 'Context item removed.', 'ok');
  }

  async function clearContextShelf() {
    if (!activeSession) return;
    const hasItems = Array.isArray(activeSession.context_items) && activeSession.context_items.length;
    const hasNote = trim($('assistant-context-note')?.value || activeSession.context_note || '');
    if (!hasItems && !hasNote) return;
    if (!window.confirm('Clear the pinned context note and all uploaded context items from this thread?')) return;
    activeSession.context_items = [];
    activeSession.context_note = '';
    if ($('assistant-context-note')) $('assistant-context-note').value = '';
    renderContextShelf();
    renderSessionList();
    await saveActiveSession({ silent: true });
    setStatus('assistant-context-status', 'Context shelf cleared.', 'ok');
  }


  async function saveSelectedProjectBrief() {
    const project = activeProjectMeta();
    const area = $('assistant-project-brief');
    if (!project || !area) {
      setStatus('assistant-project-status', 'Select a project on this thread first.', 'warn');
      return;
    }
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: project.id,
        description: project.description || '',
        brief: String(area.value || ''),
      }),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderSessionList();
    setStatus('assistant-project-status', data.message || 'Project brief saved.', 'ok');
  }


  async function addProjectContextCard() {
    const project = activeProjectMeta();
    const titleInput = $('assistant-project-card-title');
    const contentInput = $('assistant-project-card-content');
    if (!project || !titleInput || !contentInput) {
      setStatus('assistant-project-card-status', 'Select a project on this thread first.', 'warn');
      return;
    }
    const title = trim(titleInput.value || '');
    const content = trim(contentInput.value || '');
    if (!title || !content) {
      setStatus('assistant-project-card-status', 'Add both a card title and content.', 'warn');
      return;
    }
    const cards = Array.isArray(project.context_cards) ? project.context_cards.slice() : [];
    cards.push({ id: `project_ctx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`, title, content, created_at: nowIso(), char_count: content.length });
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: project.id,
        description: project.description || '',
        brief: project.brief || '',
        context_cards: cards,
      }),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    titleInput.value = '';
    contentInput.value = '';
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderSessionList();
    setStatus('assistant-project-card-status', data.message || 'Project context card added.', 'ok');
  }

  async function removeProjectContextCard(cardId) {
    const project = activeProjectMeta();
    if (!project || !cardId) return;
    const cards = (project.context_cards || []).filter(item => item.id !== cardId);
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: project.id,
        description: project.description || '',
        brief: project.brief || '',
        context_cards: cards,
      }),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderSessionList();
    setStatus('assistant-project-card-status', 'Project context card removed.', 'ok');
  }


  async function addProjectContextFile() {
    const project = activeProjectMeta();
    const input = $('assistant-project-file-upload');
    const file = input?.files?.[0];
    if (!project || !input) {
      setStatus('assistant-project-file-status', 'Select a project on this thread first.', 'warn');
      return;
    }
    if (!file) {
      setStatus('assistant-project-file-status', 'Choose a text file first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('file', file);
    const parsed = await safeFetchJson('/api/assistant/context-upload', { method: 'POST', body: form });
    const item = parsed.item || null;
    if (!item) {
      setStatus('assistant-project-file-status', 'Could not read that text file.', 'warn');
      return;
    }
    const files = Array.isArray(project.context_files) ? project.context_files.slice() : [];
    files.push({
      id: `project_file_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      title: item.title || file.name || 'Project file',
      source_kind: item.source_kind || 'text',
      content: String(item.content || ''),
      created_at: nowIso(),
      char_count: Number(item.char_count || String(item.content || '').length || 0),
    });
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: project.id,
        description: project.description || '',
        brief: project.brief || '',
        context_cards: Array.isArray(project.context_cards) ? project.context_cards : [],
        context_files: files,
      }),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    if (input) input.value = '';
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderSessionList();
    setStatus('assistant-project-file-status', parsed.message || 'Project file attached.', 'ok');
  }

  async function removeProjectContextFile(fileId) {
    const project = activeProjectMeta();
    if (!project || !fileId) return;
    const files = (project.context_files || []).filter(item => item.id !== fileId);
    const data = await safeFetchJson('/api/assistant/project-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: project.id,
        description: project.description || '',
        brief: project.brief || '',
        context_cards: Array.isArray(project.context_cards) ? project.context_cards : [],
        context_files: files,
      }),
    });
    assistantProjects = Array.isArray(data.projects) ? data.projects : assistantProjects;
    renderProjectControls();
    renderProjectBriefEditor();
    renderProjectCardShelf();
    renderProjectFileShelf();
    renderSessionList();
    setStatus('assistant-project-file-status', 'Project file removed.', 'ok');
  }


  async function renameActiveSession() {
    if (!activeSession) return;
    const title = window.prompt('Rename this assistant chat:', activeSession.title || 'Assistant chat');
    if (title === null) return;
    const clean = trim(title);
    if (!clean) return;
    const data = await safeFetchJson('/api/assistant/session-rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: activeSession.id, title: clean }) });
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    activeSession = data.session || activeSession;
    renderSurface();
    setStatus('assistant-session-status', data.message || 'Assistant chat renamed.', 'ok');
  }

  async function deleteActiveSession() {
    if (!activeSession) return;
    const approved = window.confirm(`Delete "${activeSession.title || 'this chat'}"?`);
    if (!approved) return;
    const deletingId = activeSession.id;
    const data = await safeFetchJson('/api/assistant/session-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: deletingId }) });
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : [];
    activeSession = null;
    renderSurface();
    setStatus('assistant-session-status', data.message || 'Assistant chat deleted.', 'ok');
    if (!assistantSessions.length) {
      await createSession({ mode: assistantProfile?.default_mode || 'general', title: 'New assistant chat' }, { silent: true });
      return;
    }
    await loadSession(assistantSessions[0].id, { silent: true });
  }

  async function clearThread() {
    if (!activeSession) return;
    const approved = window.confirm('Clear all messages from this chat?');
    if (!approved) return;
    activeSession.messages = [];
    currentPlaceholderId = '';
    if ($('assistant-composer')) activeSession.draft = $('assistant-composer').value || '';
    await saveActiveSession({ silent: true });
    setStatus('assistant-chat-status', 'Thread cleared.', 'ok');
  }

  function addLocalMessage(role, content, meta = {}) {
    if (!activeSession) return null;
    const message = { id: newMessageId(), role, content: String(content || ''), created_at: nowIso(), meta: meta || {} };
    activeSession.messages = Array.isArray(activeSession.messages) ? activeSession.messages.concat([message]) : [message];
    renderMessages();
    renderThreadHeader();
    return message;
  }

  function replaceMessageContent(messageId, content, meta = null) {
    if (!activeSession) return;
    activeSession.messages = (activeSession.messages || []).map(item => item.id === messageId ? { ...item, content: String(content || ''), meta: meta || item.meta || {} } : item);
    renderMessages();
    renderThreadHeader();
  }

  function removeMessageById(messageId) {
    if (!activeSession) return;
    activeSession.messages = (activeSession.messages || []).filter(item => item.id !== messageId);
    renderMessages();
    renderThreadHeader();
  }

  function lastUserMessageIndex() {
    const messages = activeSession?.messages || [];
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i]?.role === 'user') return i;
    }
    return -1;
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
          timeoutId = window.setTimeout(() => reject(makeStreamTimeoutError(code, code === 'STREAM_IDLE_TIMEOUT' ? 'The live reply stalled before finishing.' : 'The live reply timed out before visible output arrived.')), timeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
    }
  }

  async function consumeAssistantStream(response, handlers = {}) {
    const meta = { sawAnyEvent: false, sawFinal: false, rawText: '', stalled: false };
    const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase();
    if (!response.body) {
      meta.rawText = trim(await response.text());
      return meta;
    }
    if (!contentType.includes('text/event-stream')) {
      meta.rawText = trim(await response.text());
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

  async function runAssistantStream(sourceMessages, options = {}) {
    if (!activeSession) return;
    if (!requireBackendRole('text', 'assistant-chat-status', 'Connect a Text Backend first. Neo Assistant uses the active text model.')) return;
    streamController = new AbortController();
    updateStreamingState(true, options.busyText || 'Sending...');
    clearPendingContinue();
    currentPlaceholderId = addLocalMessage('assistant', '', { streaming: true })?.id || '';
    let assistantText = '';
    try {
      const payload = {
        model: typeof currentModel === 'function' ? currentModel() : 'default',
        profile: assistantProfile || {},
        session: collectThreadFromDom(),
        messages: sourceMessages,
      };
      const response = await fetch('/api/assistant/chat-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: streamController.signal,
        cache: 'no-store',
      });
      if (!response.ok) {
        let message = 'Assistant request failed.';
        try { const data = await response.json(); message = data.error || data.message || message; } catch (_err) {}
        throw new Error(message);
      }
      const meta = await consumeAssistantStream(response, {
        delta(data) {
          assistantText = String(data.text || `${assistantText}${data.delta || ''}`);
          replaceMessageContent(currentPlaceholderId, assistantText, { streaming: true });
        },
        final(data) {
          assistantText = String(data.reply || assistantText || '');
          const finishReason = trim(data.finish_reason || '');
          replaceMessageContent(currentPlaceholderId, assistantText, { streaming: false, finish_reason: finishReason, warning: trim(data.warning || '') });
          const placeholder = (activeSession?.messages || []).find(item => item.id === currentPlaceholderId);
          if (placeholder) placeholder.meta = { ...(placeholder.meta || {}), streaming: false, finish_reason: finishReason, warning: trim(data.warning || '') };
          if (shouldKeepContinueAvailable(finishReason)) markPendingContinue(finishReason);
          else clearPendingContinue();
          if (trim(data.warning || '')) setStatus('assistant-chat-status', data.warning || 'Assistant reply ready.', 'warn');
          else setStatus('assistant-chat-status', data.message || 'Assistant reply ready.', 'ok');
        },
        error(data) {
          throw new Error(data.error || 'Assistant streaming failed.');
        },
      });
      if (!meta?.sawFinal && assistantText) {
        replaceMessageContent(currentPlaceholderId, assistantText, { streaming: false, finish_reason: 'partial' });
        markPendingContinue(meta?.stalled ? 'stalled' : 'partial');
        setStatus('assistant-chat-status', meta.stalled ? 'The live reply stalled, but the visible partial output was recovered. Use Continue to keep going.' : 'Recovered the visible reply after the stream ended unexpectedly. Use Continue to keep going.', 'warn');
      }
      if (assistantText) await saveActiveSession({ silent: true });
      else {
        removeMessageById(currentPlaceholderId);
        if (activeSession?.pending_continue) await saveActiveSession({ silent: true });
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        if (assistantText) {
          replaceMessageContent(currentPlaceholderId, assistantText, { streaming: false, finish_reason: 'stopped' });
          markPendingContinue('stopped');
          await saveActiveSession({ silent: true });
          setStatus('assistant-chat-status', 'Generation stopped. The partial reply was kept. Use Continue to keep going.', 'warn');
        } else {
          removeMessageById(currentPlaceholderId);
          clearPendingContinue();
          setStatus('assistant-chat-status', 'Generation stopped.', 'ok');
        }
      } else {
        if (assistantText) {
          replaceMessageContent(currentPlaceholderId, assistantText, { streaming: false, finish_reason: 'partial' });
          markPendingContinue('partial');
          await saveActiveSession({ silent: true });
        } else {
          removeMessageById(currentPlaceholderId);
          markPendingContinue('stalled');
          await saveActiveSession({ silent: true });
        }
        setStatus('assistant-chat-status', err.message || 'Assistant request failed. Use Continue to try picking it back up.', 'warn');
      }
    } finally {
      currentPlaceholderId = '';
      streamController = null;
      updateStreamingState(false);
      renderMessages();
    }
  }

  async function sendComposerMessage() {
    if (!activeSession || isStreaming) return;
    const composer = $('assistant-composer');
    const content = trim(composer?.value || '');
    if (!content) {
      setStatus('assistant-chat-status', 'Write a message first.', 'warn');
      return;
    }
    assistantAutoFollow = true;
    clearPendingContinue();
    addLocalMessage('user', content);
    if (composer) composer.value = '';
    activeSession.draft = '';
    renderMessages();
    await saveActiveSession({ silent: true });
    const sourceMessages = clone(activeSession.messages);
    await runAssistantStream(sourceMessages, { busyText: 'Replying...' });
  }

  async function continueAssistantReply() {
    if (!activeSession || isStreaming || !canContinueReply()) return;
    assistantAutoFollow = true;
    clearPendingContinue();
    const continuePrompt = 'Continue exactly from where your previous reply stopped. Do not restart, summarize, or repeat the earlier text. Continue the same answer immediately.';
    addLocalMessage('user', continuePrompt, { continue_prompt: true });
    await saveActiveSession({ silent: true });
    const sourceMessages = clone(activeSession.messages);
    await runAssistantStream(sourceMessages, { busyText: 'Continuing...' });
  }


  async function regenerateLastReply() {
    if (!activeSession || isStreaming || !canRegenerate()) return;
    assistantAutoFollow = true;
    clearPendingContinue();
    activeSession.messages.pop();
    renderMessages();
    await saveActiveSession({ silent: true });
    const sourceMessages = clone(activeSession.messages);
    await runAssistantStream(sourceMessages, { busyText: 'Regenerating...' });
  }

  async function transformMessage(messageId, transform) {
    if (!activeSession || isStreaming) return;
    const message = (activeSession.messages || []).find(item => item.id === messageId);
    if (!message || message.role !== 'assistant') return;
    if (!requireBackendRole('text', 'assistant-chat-status', 'Connect a Text Backend first. Assistant transforms use the active text model.')) return;
    setStatus('assistant-chat-status', 'Running transform...', '');
    const data = await safeFetchJson('/api/assistant/message-transform', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: typeof currentModel === 'function' ? currentModel() : 'default',
        profile: assistantProfile || {},
        session: collectThreadFromDom(),
        source_text: message.content || '',
        transform,
      }),
    });
    assistantAutoFollow = true;
    addLocalMessage('assistant', data.text || '', { transform_label: String(transform || '').replace(/_/g, ' ').replace(/\b[a-z]/g, m => m.toUpperCase()) });
    await saveActiveSession({ silent: true });
    setStatus('assistant-chat-status', data.message || 'Transform ready.', 'ok');
  }

  async function copyMessage(messageId) {
    const message = (activeSession?.messages || []).find(item => item.id === messageId);
    if (!message?.content) {
      setStatus('assistant-chat-status', 'Nothing to copy.', 'warn');
      return;
    }
    try {
      await navigator.clipboard.writeText(message.content);
      setStatus('assistant-chat-status', 'Copied to clipboard.', 'ok');
    } catch (_err) {
      setStatus('assistant-chat-status', 'Could not copy that message.', 'warn');
    }
  }

  function applyModeDefaults() {
    if (!activeSession) return;
    const modeKey = trim($('assistant-mode')?.value || activeSession.mode || 'general') || 'general';
    const mode = activeModeConfig(modeKey);
    activeSession.mode = modeKey;
    activeSession.params = {
      max_tokens: Number(mode.max_tokens || 640),
      temperature: Number(mode.temperature || 0.7),
      top_p: Number(mode.top_p || 0.92),
      top_k: Number(mode.top_k || 60),
    };
    renderThreadSettings();
    scheduleSessionSave();
    setStatus('assistant-settings-status', `${mode.label || 'Mode'} defaults applied to this thread.`, 'ok');
  }

  function handleStarter(text) {
    if ($('assistant-composer')) $('assistant-composer').value = text || '';
    if (activeSession) {
      activeSession.draft = text || '';
      scheduleSessionSave();
    }
    $('assistant-composer')?.focus();
    setStatus('assistant-chat-status', 'Starter copied into the composer.', 'ok');
  }

  function bindSurface() {
    $('btn-assistant-new-session')?.addEventListener('click', () => createSession({ mode: assistantProfile?.default_mode || 'general', title: 'New assistant chat' }).catch(err => setStatus('assistant-session-status', err.message || 'Could not create a new chat.', 'warn')));
    $('btn-assistant-new-project')?.addEventListener('click', () => createProject().catch(err => setStatus('assistant-session-status', err.message || 'Could not create the project.', 'warn')));
    $('btn-assistant-rename-project')?.addEventListener('click', () => renameSelectedProject().catch(err => setStatus('assistant-session-status', err.message || 'Could not rename the project.', 'warn')));
    $('btn-assistant-delete-project')?.addEventListener('click', () => deleteSelectedProject().catch(err => setStatus('assistant-session-status', err.message || 'Could not delete the project.', 'warn')));
    $('btn-assistant-add-context-file')?.addEventListener('click', () => uploadContextFile().catch(err => setStatus('assistant-context-status', err.message || 'Could not add that context file.', 'warn')));
    $('btn-assistant-add-image-bridge')?.addEventListener('click', () => addImageBridgeContext().catch(() => {}));
    $('btn-assistant-refresh-memory')?.addEventListener('click', () => refreshThreadMemory().catch(() => {}));
    $('btn-assistant-apply-memory-backend')?.addEventListener('click', () => applyAssistantMemoryBackend().catch(err => setStatus('assistant-memory-status', err.message || 'Could not switch the embedding backend.', 'warn')));
    $('btn-assistant-preview-memory')?.addEventListener('click', () => previewAssistantAdaptiveMemory().catch(err => setStatus('assistant-memory-status', err.message || 'Could not preview adaptive memory.', 'warn')));
    $('btn-assistant-repair-memory')?.addEventListener('click', () => repairAssistantAdaptiveMemory().catch(err => setStatus('assistant-memory-status', err.message || 'Could not rebuild adaptive memory.', 'warn')));
    $('btn-assistant-reset-session-memory')?.addEventListener('click', () => resetAssistantAdaptiveMemory('session').catch(err => setStatus('assistant-memory-status', err.message || 'Could not reset thread memory.', 'warn')));
    $('btn-assistant-reset-project-memory')?.addEventListener('click', () => resetAssistantAdaptiveMemory('project').catch(err => setStatus('assistant-memory-status', err.message || 'Could not reset project memory.', 'warn')));
    $('btn-assistant-refresh-memory-admin')?.addEventListener('click', () => refreshMemoryAdmin().catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not refresh global memory.', 'warn')));
    $('assistant-memory-admin-lane')?.addEventListener('change', () => refreshMemoryAdmin({ quiet: true }).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not filter global memory.', 'warn')));
    $('assistant-memory-admin-chunk-type')?.addEventListener('change', () => refreshMemoryAdmin({ quiet: true }).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not filter global memory.', 'warn')));
    $('assistant-memory-admin-include-suppressed')?.addEventListener('change', () => refreshMemoryAdmin({ quiet: true }).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not filter global memory.', 'warn')));
    $('assistant-memory-admin-query')?.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      refreshMemoryAdmin().catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not search global memory.', 'warn'));
    });
    $('btn-assistant-clear-context')?.addEventListener('click', () => clearContextShelf().catch(err => setStatus('assistant-context-status', err.message || 'Could not clear the context shelf.', 'warn')));
    $('btn-assistant-save-project-brief')?.addEventListener('click', () => saveSelectedProjectBrief().catch(err => setStatus('assistant-project-status', err.message || 'Could not save the project brief.', 'warn')));
    $('btn-assistant-add-project-card')?.addEventListener('click', () => addProjectContextCard().catch(err => setStatus('assistant-project-card-status', err.message || 'Could not add the project context card.', 'warn')));
    $('btn-assistant-add-project-file')?.addEventListener('click', () => addProjectContextFile().catch(err => setStatus('assistant-project-file-status', err.message || 'Could not add the project file.', 'warn')));
    $('btn-assistant-add-project-record')?.addEventListener('click', () => addProjectLinkedRecord().catch(err => setStatus('assistant-project-record-status', err.message || 'Could not add the linked record.', 'warn')));
    $('btn-assistant-rename-session')?.addEventListener('click', () => renameActiveSession().catch(err => setStatus('assistant-session-status', err.message || 'Could not rename the chat.', 'warn')));
    $('btn-assistant-continue')?.addEventListener('click', () => continueAssistantReply().catch(err => setStatus('assistant-chat-status', err.message || 'Could not continue the reply.', 'warn')));
    $('btn-assistant-delete-session')?.addEventListener('click', () => deleteActiveSession().catch(err => setStatus('assistant-session-status', err.message || 'Could not delete the chat.', 'warn')));
    $('btn-assistant-clear-thread')?.addEventListener('click', () => clearThread().catch(err => setStatus('assistant-chat-status', err.message || 'Could not clear the thread.', 'warn')));
    $('btn-assistant-send')?.addEventListener('click', () => sendComposerMessage().catch(err => setStatus('assistant-chat-status', err.message || 'Could not send the message.', 'warn')));
    $('btn-assistant-stop')?.addEventListener('click', () => { if (streamController) streamController.abort(); });
    $('btn-assistant-regenerate')?.addEventListener('click', () => regenerateLastReply().catch(err => setStatus('assistant-chat-status', err.message || 'Could not regenerate that reply.', 'warn')));
    $('btn-assistant-apply-mode')?.addEventListener('click', applyModeDefaults);
    $('btn-assistant-save-profile')?.addEventListener('click', () => saveProfileNow({ silent: false }).catch(err => setStatus('assistant-profile-status', err.message || 'Could not save the assistant profile.', 'warn')));
    $('btn-assistant-open-manager')?.addEventListener('click', () => {
      if (typeof switchTab === 'function') switchTab('prompt');
      setStatus('assistant-settings-status', 'Opened Prompt & Caption so you can adjust the shared active text model.', 'ok');
    });
    $('btn-assistant-note-manage-backend')?.addEventListener('click', () => window.openBackendManager?.('text'));

    ['assistant-session-status','assistant-chat-status','assistant-profile-status','assistant-project-status','assistant-project-card-status','assistant-project-file-status','assistant-project-record-status','assistant-context-status','assistant-image-bridge-status','assistant-settings-status','assistant-memory-status','assistant-memory-admin-status'].forEach(bindAssistantStatusAutoClear);

    $('assistant-session-search')?.addEventListener('input', () => {
      renderSessionList();
      if (!trim($('assistant-session-search')?.value || '')) {
        assistantSearchResults = [];
        renderAssistantSearchResults([], '');
      }
    });
    $('assistant-project-filter')?.addEventListener('change', renderSessionList);
    $('btn-assistant-search-context')?.addEventListener('click', () => searchAssistantContext().catch(err => setStatus('assistant-session-status', err.message || 'Could not search Assistant content.', 'warn')));
    $('btn-assistant-clear-search-results')?.addEventListener('click', () => {
      assistantSearchResults = [];
      renderAssistantSearchResults([], '');
      setStatus('assistant-session-status', 'Assistant search results cleared.', 'ok');
    });
    $('assistant-session-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-assistant-session-id]');
      if (!btn) return;
      loadSession(btn.dataset.assistantSessionId || '').catch(err => setStatus('assistant-session-status', err.message || 'Could not load that chat.', 'warn'));
    });
    $('assistant-search-results')?.addEventListener('click', event => {
      const card = event.target.closest('[data-search-result-index]');
      if (!card) return;
      const idx = Number(card.getAttribute('data-search-result-index') || '-1');
      const item = Number.isFinite(idx) ? assistantSearchResults[idx] : null;
      if (!item) return;
      const sessionId = trim(item.session_id || '');
      const projectId = trim(item.project_id || '');
      if (sessionId) {
        loadSession(sessionId).catch(err => setStatus('assistant-session-status', err.message || 'Could not load that Assistant result.', 'warn'));
        return;
      }
      if (projectId) {
        if ($('assistant-project-filter')) $('assistant-project-filter').value = projectId;
        renderSessionList();
        const firstSession = (assistantSessions || []).find(row => trim(row.project_id || '') === projectId);
        if (firstSession?.id) {
          loadSession(firstSession.id).catch(err => setStatus('assistant-session-status', err.message || 'Could not load a project-linked chat.', 'warn'));
          return;
        }
        setStatus('assistant-session-status', `Showing Assistant project matches for ${projectTitle(projectId) || 'that project'}.`, 'ok');
      }
    });

    $('assistant-composer')?.addEventListener('input', () => {
      if (activeSession) {
        activeSession.draft = $('assistant-composer')?.value || '';
        scheduleSessionSave();
      }
    });
    $('assistant-composer')?.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendComposerMessage().catch(err => setStatus('assistant-chat-status', err.message || 'Could not send the message.', 'warn'));
      }
    });

    ['assistant-project-select', 'assistant-mode', 'assistant-thread-instruction', 'assistant-context-note', 'assistant-max-tokens', 'assistant-temperature', 'assistant-top-p', 'assistant-top-k'].forEach(id => {
      $(id)?.addEventListener('input', () => {
        if (!activeSession) return;
        Object.assign(activeSession, collectThreadFromDom());
        syncModeMeta();
        scheduleSessionSave();
      });
      $(id)?.addEventListener('change', () => {
        if (!activeSession) return;
        Object.assign(activeSession, collectThreadFromDom());
        syncModeMeta();
        scheduleSessionSave();
      });
    });

    ['assistant-profile-name', 'assistant-profile-user-name', 'assistant-profile-address-style', 'assistant-profile-default-mode', 'assistant-profile-response-detail', 'assistant-profile-support-style', 'assistant-profile-about-user', 'assistant-profile-preferences', 'assistant-profile-avoid'].forEach(id => {
      $(id)?.addEventListener('input', () => {
        applyProfileToLocal(collectProfileFromDom());
        renderThreadHeader();
        scheduleProfileSave();
      });
      $(id)?.addEventListener('change', () => {
        applyProfileToLocal(collectProfileFromDom());
        renderThreadHeader();
        scheduleProfileSave();
      });
    });

    $('assistant-context-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-assistant-remove-context]');
      if (!btn) return;
      removeContextItem(btn.getAttribute('data-assistant-remove-context') || '');
    });

    $('assistant-project-card-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-assistant-remove-project-card]');
      if (!btn) return;
      removeProjectContextCard(btn.getAttribute('data-assistant-remove-project-card') || '').catch(err => setStatus('assistant-project-card-status', err.message || 'Could not remove that project context card.', 'warn'));
    });

    $('assistant-project-file-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-assistant-remove-project-file]');
      if (!btn) return;
      removeProjectContextFile(btn.getAttribute('data-assistant-remove-project-file') || '').catch(err => setStatus('assistant-project-file-status', err.message || 'Could not remove that project file.', 'warn'));
    });

    $('assistant-project-thread-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-project-thread-open]');
      if (!btn) return;
      loadSession(btn.getAttribute('data-project-thread-open') || '').catch(err => setStatus('assistant-project-record-status', err.message || 'Could not open that linked chat.', 'warn'));
    });

    $('assistant-project-record-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-assistant-remove-project-record]');
      if (!btn) return;
      removeProjectLinkedRecord(btn.getAttribute('data-assistant-remove-project-record') || '').catch(err => setStatus('assistant-project-record-status', err.message || 'Could not remove that linked record.', 'warn'));
    });

    $('assistant-memory-admin-item-list')?.addEventListener('click', event => {
      const pinBtn = event.target.closest('[data-memory-pin-toggle]');
      if (pinBtn) {
        const chunkId = pinBtn.getAttribute('data-memory-pin-toggle') || '';
        const nextState = String(pinBtn.getAttribute('data-memory-pin-state') || '0') === '1';
        updateMemoryItemState(chunkId, { is_pinned: nextState, pin_note: nextState ? 'Pinned in global memory admin' : '' }).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not update that memory pin.', 'warn'));
        return;
      }
      const suppressBtn = event.target.closest('[data-memory-suppress-toggle]');
      if (suppressBtn) {
        const chunkId = suppressBtn.getAttribute('data-memory-suppress-toggle') || '';
        const nextState = String(suppressBtn.getAttribute('data-memory-suppress-state') || '0') === '1';
        updateMemoryItemState(chunkId, { is_suppressed: nextState, suppressed_reason: nextState ? 'Suppressed in global memory admin' : '' }).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not update that memory item.', 'warn'));
      }
    });

    $('assistant-memory-conflict-list')?.addEventListener('click', event => {
      const btn = event.target.closest('[data-memory-conflict-keep]');
      if (!btn) return;
      const keepId = btn.getAttribute('data-memory-conflict-keep') || '';
      const dropIds = String(btn.getAttribute('data-memory-conflict-drop') || '').split(',').map(item => trim(item)).filter(Boolean);
      resolveMemoryConflict(keepId, dropIds).catch(err => setStatus('assistant-memory-admin-status', err.message || 'Could not resolve that memory conflict.', 'warn'));
    });

    $('assistant-thread')?.addEventListener('scroll', () => {
      const thread = $('assistant-thread');
      if (!thread) return;
      assistantAutoFollow = isNearBottom(thread, 72);
      syncJumpLatestVisibility();
    });
    $('btn-assistant-jump-latest')?.addEventListener('click', () => scrollThreadToLatest('smooth'));

    $('assistant-thread')?.addEventListener('click', event => {
      const applyRoleplayBtn = event.target.closest('[data-assistant-apply-roleplay]');
      if (applyRoleplayBtn) {
        applyAssistantMessageToRoleplay(applyRoleplayBtn.getAttribute('data-message-id') || '', { openRoleplay: false });
        return;
      }
      const openRoleplayBtn = event.target.closest('[data-assistant-open-roleplay]');
      if (openRoleplayBtn) {
        applyAssistantMessageToRoleplay(openRoleplayBtn.getAttribute('data-message-id') || '', { openRoleplay: true });
        return;
      }
      const applyWorkspaceBtn = event.target.closest('[data-assistant-apply-workspace]');
      if (applyWorkspaceBtn) {
        applyAssistantMessageToWorkspace(applyWorkspaceBtn.getAttribute('data-message-id') || '', { openWorkspace: false });
        return;
      }
      const openWorkspaceBtn = event.target.closest('[data-assistant-open-workspace]');
      if (openWorkspaceBtn) {
        applyAssistantMessageToWorkspace(openWorkspaceBtn.getAttribute('data-message-id') || '', { openWorkspace: true });
        return;
      }
      const transformBtn = event.target.closest('[data-assistant-transform]');
      if (transformBtn) {
        transformMessage(transformBtn.getAttribute('data-message-id') || '', transformBtn.getAttribute('data-assistant-transform') || '').catch(err => setStatus('assistant-chat-status', err.message || 'Could not transform that reply.', 'warn'));
        return;
      }
      const exportBtn = event.target.closest('[data-assistant-export]');
      if (exportBtn) {
        exportAssistantMessage(exportBtn.getAttribute('data-message-id') || '', exportBtn.getAttribute('data-assistant-export') || '');
        return;
      }
      const copyBtn = event.target.closest('[data-assistant-copy-message]');
      if (copyBtn) {
        copyMessage(copyBtn.getAttribute('data-message-id') || '').catch(err => setStatus('assistant-chat-status', err.message || 'Could not copy that reply.', 'warn'));
      }
    });

    document.addEventListener('click', event => {
      const starter = event.target.closest('[data-assistant-starter]');
      if (!starter) return;
      handleStarter(starter.getAttribute('data-assistant-starter') || '');
    });
    $('model-select')?.addEventListener('change', updateActiveModelNote);
    document.addEventListener('neo-backend-state', updateBackendNote);

    fetchBootstrap().catch(err => setStatus('assistant-session-status', err.message || 'Could not load the Assistant surface.', 'warn'));
    fetchAssistantMemoryBackendStatus().catch(() => renderAssistantMemoryBackend(null));
  }

  async function startWorkspaceHelperChat(packet = {}) {
    if (!assistantProfile || !Object.keys(assistantModes || {}).length) await fetchBootstrap();
    const payload = {
      title: trim(packet.title || 'Workspace helper'),
      mode: trim(packet.mode || assistantProfile?.default_mode || 'general') || 'general',
      thread_instruction: String(packet.thread_instruction || ''),
      helper_context: packet.helper_context && typeof packet.helper_context === 'object' ? packet.helper_context : {},
    };
    const data = await safeFetchJson('/api/assistant/session-create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    assistantSessions = Array.isArray(data.sessions) ? data.sessions : assistantSessions;
    activeSession = data.session || null;
    const draftText = String(packet.composer_text || '').trim();
    if (activeSession && draftText) {
      activeSession.draft = draftText;
      if ($('assistant-composer')) $('assistant-composer').value = draftText;
      await saveActiveSession({ silent: true });
    }
    assistantAutoFollow = true;
    renderSurface();
    if (typeof switchTab === 'function') switchTab('assistant');
    setStatus('assistant-session-status', packet.status_message || 'Workspace helper packet opened in Assistant.', 'ok');
    if (draftText) setStatus('assistant-chat-status', 'Helper context loaded. Review or send when ready.', 'ok');
    window.setTimeout(() => $('assistant-composer')?.focus(), 0);
    return clone(activeSession || {});
  }

  window.neoRefreshAssistantSurface = renderSurface;
  window.NeoAssistantSurface = {
    refresh: renderSurface,
    loadSession,
    startWorkspaceHelperChat,
    getActiveSession: () => clone(activeSession || {}),
    getProfile: () => clone(assistantProfile || {}),
  };

  if (document.readyState === 'complete' || document.readyState === 'interactive') bindSurface();
  else document.addEventListener('DOMContentLoaded', bindSurface, { once: true });
})();


(function(){
  function bindAssistantWorkspaceTabs(){
    const shell = document.getElementById('assistant-workspace-tabs-shell');
    if (!shell || shell.__neoAssistantWorkspaceTabsBound) return;
    shell.__neoAssistantWorkspaceTabsBound = true;
    const buttons = Array.from(shell.querySelectorAll('[data-assistant-workspace-tab]'));
    const panels = Array.from(shell.querySelectorAll('[data-assistant-workspace-panel]'));
    function activate(key){
      const target = String(key || 'chat');
      buttons.forEach(btn => {
        const active = String(btn.getAttribute('data-assistant-workspace-tab') || '') === target;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      panels.forEach(panel => {
        const active = String(panel.getAttribute('data-assistant-workspace-panel') || '') === target;
        panel.classList.toggle('active', active);
      });
    }
    buttons.forEach(btn => btn.addEventListener('click', () => activate(btn.getAttribute('data-assistant-workspace-tab') || 'chat')));
    activate('chat');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindAssistantWorkspaceTabs, { once:true });
  else bindAssistantWorkspaceTabs();
  document.addEventListener('neo-surface-activated', bindAssistantWorkspaceTabs);
})();
