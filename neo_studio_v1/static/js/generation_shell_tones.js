(function () {
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  const FAMILY_TONES = {
    sdxl_sd: { tone: 'primary', state: 'active' },
    flux: { tone: 'success', state: 'ready' },
    qwen_image_edit: { tone: 'specialty', state: 'ready' },
    zimage: { tone: 'warning', state: 'disabled' },
  };

  const WORKSPACE_TONES = {
    txt2img: { tone: 'primary', state: 'active' },
    img2img: { tone: 'specialty', state: 'active' },
    inpaint: { tone: 'warning', state: 'active' },
    outpaint: { tone: 'recovery', state: 'active' },
  };

  const PRESET_TONES = {
    'builtin:create_portrait_safe': { tone: 'primary', state: 'active' },
    'builtin:create_square_safe': { tone: 'primary', state: 'active' },
    'builtin:create_landscape_safe': { tone: 'primary', state: 'active' },
    'builtin:reference_same_face': { tone: 'specialty', state: 'active' },
    'builtin:reference_same_character': { tone: 'specialty', state: 'active' },
    'builtin:reference_style_carry': { tone: 'specialty', state: 'active' },
    'builtin:repair_small_area': { tone: 'warning', state: 'active' },
    'builtin:repair_face_hands': { tone: 'warning', state: 'active' },
    'builtin:cleanup_remove_object': { tone: 'warning', state: 'active' },
    'builtin:cleanup_cut_out_subject': { tone: 'warning', state: 'active' },
    'builtin:finish_preserve_2x': { tone: 'success', state: 'ready' },
    'builtin:finish_portrait_restore': { tone: 'success', state: 'ready' },
    'builtin:finish_heavy_rescue': { tone: 'success', state: 'ready' },
    'builtin:recover_output_rebuild': { tone: 'recovery', state: 'active' },
    'builtin:recover_output_inspect': { tone: 'recovery', state: 'active' },
  };

  const BACKEND_TONES = {
    offline: { tone: 'neutral', state: 'neutral' },
    checking: { tone: 'primary', state: 'active' },
    connected: { tone: 'success', state: 'ready' },
    busy: { tone: 'success', state: 'ready' },
    degraded: { tone: 'warning', state: 'degraded' },
    error: { tone: 'danger', state: 'error' },
  };

  function applyCardState(id, tone = 'neutral', state = 'neutral') {
    const el = $(id);
    if (!el) return;
    el.dataset.uiTone = tone;
    el.dataset.uiState = state;
  }

  function syncBackendTone(state = 'offline') {
    const entry = BACKEND_TONES[String(state || 'offline').trim().toLowerCase()] || BACKEND_TONES.offline;
    applyCardState('generation-setup-shell-backend-card', entry.tone, entry.state);
  }

  function syncFamilyTone(family = '') {
    const entry = FAMILY_TONES[String(family || $('generation-family')?.value || 'sdxl_sd').trim()] || { tone: 'neutral', state: 'neutral' };
    applyCardState('generation-setup-shell-family-card', entry.tone, entry.state);
  }

  function currentWorkspaceMode() {
    return $('generation-workflow-type')?.value || document.querySelector('[data-generation-shell-workspace].active')?.getAttribute('data-generation-shell-workspace') || 'txt2img';
  }

  function syncWorkspaceTone(mode = '') {
    const entry = WORKSPACE_TONES[String(mode || currentWorkspaceMode()).trim()] || { tone: 'neutral', state: 'neutral' };
    applyCardState('generation-setup-shell-goal-card', entry.tone, entry.state);
  }

  function syncPresetTone(value = '') {
    const selected = String(value || $('generation-shell-snapshot-select')?.value || '').trim();
    const entry = PRESET_TONES[selected] || { tone: 'neutral', state: 'neutral' };
    applyCardState('generation-setup-shell-preset-card', entry.tone, entry.state);
  }

  function syncFromBackendManager(detail) {
    const state = detail?.session?.image?.state || window.getBackendRoleState?.('image')?.state || 'offline';
    syncBackendTone(state);
  }

  function boot() {
    syncFromBackendManager(window.getBackendManagerState?.() || null);
    syncFamilyTone();
    syncWorkspaceTone();
    syncPresetTone();
  }

  document.addEventListener('neo-backend-state', event => syncFromBackendManager(event.detail || null));
  document.addEventListener('neo-generation-family-changed', event => syncFamilyTone(event.detail?.family || ''));
  document.addEventListener('neo-generation-goal-changed', event => syncWorkspaceTone(event.detail?.goalId || event.detail?.mode || ''));
  document.addEventListener('neo-generation-workspace-changed', event => syncWorkspaceTone(event.detail?.mode || ''));
  document.addEventListener('neo-generation-preset-changed', event => syncPresetTone(event.detail?.presetId || ''));

  ready(boot);
})();
