// Neo Studio Extension Workflow Compatibility Guard
// Phase 9: bridges installed extension workflow packs into the generation workflow intake guard.
(function () {
  'use strict';

  const state = {
    loaded: false,
    loading: false,
    lastFamily: '',
    lastPayload: null,
    lastError: null,
  };

  function normalizeFamily(family) {
    const registry = window.NeoGenerationFeatureAvailability;
    if (registry && typeof registry.normalizeFamily === 'function') return registry.normalizeFamily(family);
    return String(family || document.documentElement.dataset.neoGenerationFamily || 'sdxl_sd').trim().toLowerCase() || 'sdxl_sd';
  }

  function getActiveFamily() {
    const registry = window.NeoGenerationFeatureAvailability;
    if (registry && typeof registry.getActiveFamily === 'function') return normalizeFamily(registry.getActiveFamily());
    return normalizeFamily(document.documentElement.dataset.neoGenerationFamily || 'sdxl_sd');
  }

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  async function loadExtensionWorkflowPacks(options) {
    const guard = window.NeoGenerationNodeWorkflowIntakeGuard;
    if (!guard || typeof guard.registerExtensionWorkflowPacks !== 'function') {
      state.lastError = 'node_workflow_intake_guard_missing';
      return { ok: false, error: state.lastError };
    }
    const opts = options || {};
    const family = normalizeFamily(opts.family || getActiveFamily());
    if (state.loading && !opts.force) return { ok: false, error: 'already_loading' };
    state.loading = true;
    state.lastFamily = family;
    try {
      const query = new URLSearchParams({ surface: 'generation', family, enabled_only: 'true' });
      const response = await fetch(`/api/extensions/workflow-packs?${query.toString()}`);
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.message || 'Could not load extension workflow packs.');
      guard.clearExtensionSpecs();
      const results = guard.registerExtensionWorkflowPacks(payload.packs || []);
      state.loaded = true;
      state.lastPayload = payload;
      state.lastError = null;
      emit('neo-generation-extension-workflow-compat-loaded', {
        family,
        packs: payload.packs || [],
        results,
      });
      return { ok: true, family, packs: payload.packs || [], results };
    } catch (error) {
      state.lastError = error && error.message ? error.message : String(error);
      console.warn('[Neo Extension Workflow Compat Guard] load failed', error);
      emit('neo-generation-extension-workflow-compat-error', { family, error: state.lastError });
      return { ok: false, family, error: state.lastError };
    } finally {
      state.loading = false;
    }
  }

  function refresh(options) {
    return loadExtensionWorkflowPacks(Object.assign({ force: true }, options || {}));
  }

  window.NeoGenerationExtensionWorkflowCompatGuard = Object.freeze({
    state,
    loadExtensionWorkflowPacks,
    refresh,
    getActiveFamily,
  });

  window.addEventListener('neo-generation-family-changed', (event) => {
    const family = event && event.detail ? event.detail.family : '';
    refresh({ family }).catch(() => {});
  });
  window.addEventListener('neo:extension-hook-loaded', () => refresh().catch(() => {}));
  window.addEventListener('neo:extension-panel-mounted', () => refresh().catch(() => {}));

  document.addEventListener('DOMContentLoaded', () => {
    loadExtensionWorkflowPacks().catch(() => {});
  });
})();
