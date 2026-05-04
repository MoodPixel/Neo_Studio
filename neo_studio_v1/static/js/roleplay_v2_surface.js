(function () {
  const state = {
    projects: [],
    workspace: null,
    retrievalStatus: null,
    lastRetrievalResult: null,
    lastRecoveryEval: null,
    lastHelperOutput: null,
    lastCanonRecord: null,
    lastRuntimeBundle: null,
    librarySnapshot: null,
    selectedLibraryKind: 'characters',
    selectedLibraryItem: null,
    runtimeBundles: [],
    activeRuntimeBundle: null,
    sceneTranscript: [],
    sceneTurnMeta: null,
    lastWritebackEval: null,
    sceneBusy: false,
    sceneContinuity: null,
    sceneSessionBundleId: '',
    sceneState: null,
    sceneTurnInputStyle: 'free_typing',
    sceneSuggestedActions: [],
    sceneLastBranchChoice: null,
    sceneAutosaveEnabled: false,
    sceneAutosaveIntervalMs: 20000,
    sceneAutosaveLastTranscriptLength: 0,
    sceneAutosaveLastCheckpointId: '',
    sceneAutosaveStatus: 'Autosave off',
    sceneContinuityRefreshHandle: null,
    storylines: [],
    selectedStorylineId: '',
    selectedStoryline: null,
    storySessions: [],
    selectedSessionId: '',
    selectedSession: null,
    storyCheckpoints: [],
    selectedCheckpointId: '',
    selectedCheckpoint: null,
    storyInspectorView: 'summary',
    storyContinuityView: 'rows',
    storyReaderState: null,
    storyResumePreview: null,
    storyDraftSnapshot: null,
    storiesBusy: false,
    lastAuthoringOutputPreset: 'novel',
    internalToolsVisible: false,
    activeSubtab: 'studio',
    activeStudioSubtab: 'guide',
  };

  const MODE_GOALS = {
    roleplay: { output_preset: 'roleplay', interaction_mode: 'roleplay', goal_key: 'roleplay', goal_label: 'Roleplay', is_authoring: false },
    short_story: { output_preset: 'short_story', interaction_mode: 'authoring', goal_key: 'short_story', goal_label: 'Short story authoring', is_authoring: true },
    novel: { output_preset: 'novel', interaction_mode: 'authoring', goal_key: 'novel', goal_label: 'Novel authoring', is_authoring: true },
    cinematic: { output_preset: 'cinematic', interaction_mode: 'authoring', goal_key: 'cinematic', goal_label: 'Cinematic authoring', is_authoring: true },
  };
  const AUTHORING_OUTPUT_PRESETS = new Set(['short_story', 'novel', 'cinematic']);

  function normalizeRoleplayV2ModeSelection({ outputPreset = '', interactionMode = '', prefer = 'output' } = {}) {
    let output = core.text(outputPreset).toLowerCase();
    let interaction = core.text(interactionMode).toLowerCase();
    const preferKey = core.text(prefer).toLowerCase() || 'output';
    const fallbackAuthoringPreset = AUTHORING_OUTPUT_PRESETS.has(core.text(state.lastAuthoringOutputPreset).toLowerCase())
      ? core.text(state.lastAuthoringOutputPreset).toLowerCase()
      : 'novel';
    if (!MODE_GOALS[output]) output = '';
    if (!['roleplay', 'authoring'].includes(interaction)) interaction = '';
    if (preferKey === 'interaction') {
      if (interaction === 'authoring') {
        output = AUTHORING_OUTPUT_PRESETS.has(output) ? output : fallbackAuthoringPreset;
      } else if (interaction === 'roleplay') {
        output = MODE_GOALS[output] ? output : 'roleplay';
      } else {
        output = 'roleplay';
        interaction = 'roleplay';
      }
    } else {
      if (AUTHORING_OUTPUT_PRESETS.has(output)) {
        interaction = ['roleplay', 'authoring'].includes(interaction) ? interaction : 'authoring';
      } else {
        output = 'roleplay';
        interaction = 'roleplay';
      }
    }
    const goal = MODE_GOALS[output] || MODE_GOALS.roleplay;
    return {
      output_preset: goal.output_preset,
      interaction_mode: goal.interaction_mode,
      goal_key: goal.goal_key,
      goal_label: goal.goal_label,
      is_authoring: !!goal.is_authoring,
    };
  }

  const core = {
    state,
    SHELL_KEY: 'neo-roleplay-v2-setup-shell-open',
    INTERNAL_TOOLS_KEY: 'neo-roleplay-v2-internal-tools',
    modules: {},
    $(id) { return document.getElementById(id); },
    text(value) { return String(value || '').trim(); },
    setStatus(id, message, tone = '') {
      const el = core.$(id);
      if (!el) return;
      el.className = `status ${tone}`.trim();
      el.textContent = message || '';
    },
    setOutput(payload) {
      const el = core.$('roleplay-v2-output');
      if (!el) return;
      el.textContent = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
    },
    async postForm(url, fields) {
      const fd = new FormData();
      Object.entries(fields || {}).forEach(([key, value]) => fd.append(key, value == null ? '' : String(value)));
      const res = await fetch(url, { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Request failed.');
      return data;
    },
    async getJson(url) {
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Request failed.');
      return data;
    },
    safeLocalStorageGet(key) {
      try { return window.localStorage.getItem(key); } catch (_) { return null; }
    },
    safeLocalStorageSet(key, value) {
      try { window.localStorage.setItem(key, value); } catch (_) {}
    },
    readInitialInternalToolsVisible() {
      try {
        const params = new URLSearchParams(window.location.search || '');
        const flag = core.text(params.get('rpv2dev') || params.get('roleplay_v2_dev')).toLowerCase();
        if (['1', 'true', 'on', 'yes'].includes(flag)) return true;
      } catch (_) {}
      return core.safeLocalStorageGet(core.INTERNAL_TOOLS_KEY) === '1';
    },
    internalToolsVisible() {
      return !!state.internalToolsVisible;
    },
    applyInternalToolsVisibility() {
      const enabled = !!state.internalToolsVisible;
      document.querySelectorAll('[data-roleplay-v2-dev]').forEach(panel => {
        panel.classList.toggle('hidden', !enabled);
      });
      const badge = core.$('roleplay-v2-internal-tools-badge');
      if (badge) badge.textContent = enabled ? 'Internal tools on' : 'Internal tools hidden';
      const toggle = core.$('btn-roleplay-v2-internal-tools-toggle');
      if (toggle) toggle.textContent = enabled ? 'Hide internal tools' : 'Show internal tools';
    },
    setInternalToolsVisible(enabled, { persist = true } = {}) {
      state.internalToolsVisible = !!enabled;
      if (persist) core.safeLocalStorageSet(core.INTERNAL_TOOLS_KEY, state.internalToolsVisible ? '1' : '0');
      core.applyInternalToolsVisibility();
      Object.values(core.modules || {}).forEach(mod => {
        if (mod && typeof mod.onInternalToolsToggle === 'function') mod.onInternalToolsToggle(state.internalToolsVisible);
      });
      return state.internalToolsVisible;
    },
    setSubtab(tabId) {
      const requestedTab = core.text(tabId) || 'studio';
      const cleanTab = requestedTab === 'libraries' ? 'studio' : requestedTab;
      state.activeSubtab = cleanTab;
      document.querySelectorAll('#roleplay-v2-subtabbar [data-roleplay-v2-tab]').forEach(btn => {
        btn.classList.toggle('active', core.text(btn.getAttribute('data-roleplay-v2-tab')) === cleanTab);
      });
      document.querySelectorAll('[data-roleplay-v2-panel]').forEach(panel => {
        panel.classList.toggle('hidden', core.text(panel.getAttribute('data-roleplay-v2-panel')) !== cleanTab);
      });
      core.refreshWorkflowPath();
      core.refreshUserPathGuide();
    },
    setStudioSubtab(name) {
      const requested = core.text(name) || 'guide';
      const clean = core.modules?.studio?.normalizeStudioSubtab?.(requested) || requested;
      state.activeStudioSubtab = clean;
      document.querySelectorAll('#roleplay-v2-studio-subtabbar [data-roleplay-v2-studio-tab]').forEach(btn => {
        btn.classList.toggle('active', core.text(btn.getAttribute('data-roleplay-v2-studio-tab')) === clean);
      });
      document.querySelectorAll('[data-roleplay-v2-studio-panel]').forEach(panel => {
        panel.classList.toggle('hidden', core.text(panel.getAttribute('data-roleplay-v2-studio-panel')) !== clean);
      });
      core.refreshWorkflowPath();
      core.refreshUserPathGuide();
    },
    openWorkspaceLane(tabId, studioSubtab = '') {
      const requestedTab = core.text(tabId) || 'scene';
      const cleanTab = requestedTab === 'libraries' ? 'studio' : requestedTab;
      const nextStudioSubtab = requestedTab === 'libraries' ? 'libraries' : studioSubtab;
      core.setSubtab(cleanTab);
      if (cleanTab === 'studio' && nextStudioSubtab) core.setStudioSubtab(nextStudioSubtab);
      return cleanTab;
    },
    latestRuntimeBundle() {
      const rows = Array.isArray(state.runtimeBundles) ? state.runtimeBundles.slice() : [];
      rows.sort((a, b) => Date.parse(b?.updated_at || b?.created_at || 0) - Date.parse(a?.updated_at || a?.created_at || 0));
      return rows[0] || null;
    },
    normalizeModeSelection(payload = {}) {
      return normalizeRoleplayV2ModeSelection(payload);
    },
    currentModeSelection() {
      return normalizeRoleplayV2ModeSelection({
        outputPreset: core.$('roleplay-v2-output-preset')?.value,
        interactionMode: core.$('roleplay-v2-interaction-mode')?.value,
        prefer: 'output',
      });
    },
    applyModeSelection(payload = {}) {
      const resolved = normalizeRoleplayV2ModeSelection(payload);
      if (AUTHORING_OUTPUT_PRESETS.has(resolved.output_preset)) state.lastAuthoringOutputPreset = resolved.output_preset;
      const outputEl = core.$('roleplay-v2-output-preset');
      const interactionEl = core.$('roleplay-v2-interaction-mode');
      if (outputEl && core.text(outputEl.value).toLowerCase() !== resolved.output_preset) outputEl.value = resolved.output_preset;
      if (interactionEl && core.text(interactionEl.value).toLowerCase() !== resolved.interaction_mode) interactionEl.value = resolved.interaction_mode;
      return resolved;
    },
    refreshWorkflowPath() {
      return null;
    },
    refreshUserPathGuide() {
      const badge = core.$('roleplay-v2-user-path-badge');
      const panel = core.$('roleplay-v2-user-path-summary');
      if (!badge || !panel) return;
      const mode = core.currentModeSelection();
      const isCanonicalRoleplay = mode.output_preset === 'roleplay' && mode.interaction_mode === 'roleplay';
      const isCanonicalNovel = mode.output_preset === 'novel' && mode.interaction_mode === 'authoring';
      const badgeLabel = isCanonicalRoleplay
        ? 'Roleplay'
        : isCanonicalNovel
          ? 'Novel'
          : mode.goal_label;
      const lines = [
        'Roleplay:',
        'Forge → Compile → Runtime → Scene → Stories',
        '',
        'Novel:',
        'Project → Source → Compile → Runtime → Scene → Stories',
      ];
      if (!isCanonicalRoleplay && !isCanonicalNovel) {
        lines.push('', `Active authoring preset: ${mode.goal_label}`);
      }
      badge.textContent = badgeLabel;
      panel.textContent = lines.join('\n');
    },
    registerModule(name, api) {
      core.modules[name] = api || {};
      return core.modules[name];
    },
  };

  window.neoRoleplayV2 = core;
  window.neoRefreshRoleplayV2Surface = async function () {
    for (const name of ['shell', 'studio', 'libraries', 'forge', 'scene', 'stories']) {
      const mod = core.modules[name];
      if (mod && typeof mod.refreshAll === 'function') {
        await mod.refreshAll();
        continue;
      }
      if (mod && typeof mod.refreshLibraryView === 'function') {
        await mod.refreshLibraryView();
      }
    }
  };

  async function boot() {
    if (!core.$('tab-roleplay_v2')) return;
    state.internalToolsVisible = core.readInitialInternalToolsVisible();
    core.setSubtab('studio');
    core.setStudioSubtab('guide');
    core.applyInternalToolsVisibility();
    core.$('btn-roleplay-v2-internal-tools-toggle')?.addEventListener('click', () => {
      core.setInternalToolsVisible(!core.internalToolsVisible());
    });


    for (const name of ['shell', 'studio', 'libraries', 'forge', 'scene', 'stories']) {
      const mod = core.modules[name];
      if (mod && typeof mod.boot === 'function') {
        await mod.boot();
      }
    }
    core.refreshWorkflowPath();
    core.refreshUserPathGuide();
  }

  window.addEventListener('DOMContentLoaded', boot);
})();
