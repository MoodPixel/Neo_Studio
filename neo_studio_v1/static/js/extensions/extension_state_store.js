(function () {
  'use strict';

  const STORE_VERSION = 'external-extension-state-store-v2';
  const EVENT_CHANGED = 'neo:external-extension-store:changed';
  const EVENT_PATCHED = 'neo:external-extension-store:patched';
  const EVENT_VALIDATION = 'neo:external-extension-store:validation-applied';
  const EVENT_HYDRATED = 'neo:external-extension-store:hydrated';
  const RESERVED_IDS = new Set(['scene_director', 'image.scene_director', 'neo.scene_director']);

  const listeners = new Set();
  let syncingFromCore = false;

  const state = {
    version: STORE_VERSION,
    external_extensions: {},
    registry: {
      installed: [],
      enabled: [],
      disabled: [],
      invalid: [],
      warnings: [],
    },
    last_context: {},
    last_validation_at: null,
    last_patch_at: null,
    last_hydrated_at: null,
    dirty_count: 0,
  };

  function asArray(value) { return Array.isArray(value) ? value.slice() : []; }
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function clone(value) { try { return JSON.parse(JSON.stringify(value)); } catch (_) { return value; } }
  function text(value) { return String(value == null ? '' : value).trim(); }
  function normalizeId(value) { return text(value).toLowerCase(); }
  function nowIso() { return new Date().toISOString(); }

  function normalizeRecord(record) {
    const src = asObject(record);
    const extensionId = normalizeId(src.extension_id || src.id);
    const surface = text(src.surface || (extensionId.includes('.') ? extensionId.split('.')[0] : '')) || 'global';
    const slug = text(src.slug || (extensionId.includes('.') ? extensionId.split('.').slice(1).join('.') : extensionId));
    return {
      extension_id: extensionId,
      id: extensionId,
      name: text(src.name || src.display_name || slug || extensionId || 'External extension'),
      type: text(src.type || 'external_extension') || 'external_extension',
      surface,
      slug,
      enabled: !!src.enabled || text(src.status).toLowerCase() === 'enabled',
      installed: src.installed !== false,
      status: text(src.status || (src.enabled ? 'enabled' : 'disabled')).toLowerCase() || 'disabled',
      target_sections: asArray(src.target_sections),
      supported_workflows: asArray(src.supported_workflows),
      supported_model_families: asArray(src.supported_model_families),
      source_policy: asArray(src.source_policy),
      output_policy: asArray(src.output_policy),
      batch_policy: text(src.batch_policy || ''),
      context_policy: asArray(src.context_policy),
      metadata_adapter_version: text(src.metadata_adapter_version || ''),
      ui: asObject(src.ui),
      workflow: asObject(src.workflow),
      output: asObject(src.output),
      output_visibility: asObject(src.output_visibility),
      workflow_mode: text(src.workflow_mode || src.workflow?.mode || ''),
      output_policy_default: text(src.output_policy_default || src.output?.default_policy || src.output?.policy || ''),
      primary_output_type: text(src.primary_output_type || src.output?.primary_output_type || src.output?.primary_type || ''),
      disabled_reason: text(src.disabled_reason || ''),
      warnings: asArray(src.warnings),
      ui_schema: asObject(src.ui_schema),
      raw_manifest: clone(src),
    };
  }

  function normalizeRegistry(registry) {
    const src = asObject(registry);
    const installed = asArray(src.installed || src.external_extensions).map(normalizeRecord).filter(item => item.extension_id);
    const enabled = asArray(src.enabled).length ? asArray(src.enabled).map(normalizeRecord).filter(item => item.extension_id) : installed.filter(item => item.enabled || item.status === 'enabled');
    const disabled = asArray(src.disabled).length ? asArray(src.disabled).map(normalizeRecord).filter(item => item.extension_id) : installed.filter(item => !item.enabled && item.status !== 'invalid');
    const invalid = asArray(src.invalid || src.invalid_extensions).map(normalizeRecord).filter(item => item.extension_id);
    return { installed, enabled, disabled, invalid, warnings: asArray(src.warnings), raw: clone(src) };
  }

  function emptyEntry(record) {
    const normalized = record ? normalizeRecord(record) : null;
    return {
      extension_id: normalized?.extension_id || '',
      enabled: !!normalized?.enabled,
      raw_state: {},
      effective_state: {},
      validation: {
        status: normalized?.status === 'invalid' ? 'blocked' : 'idle',
        warnings: asArray(normalized?.warnings),
        errors: normalized?.disabled_reason ? [normalized.disabled_reason] : [],
        disabled_reason: normalized?.disabled_reason || null,
        source: 'registry',
      },
      dirty: false,
      record: normalized || null,
      updated_at: nowIso(),
    };
  }

  function ensure(extensionId, record) {
    const normalized = record ? normalizeRecord(record) : null;
    const id = normalizeId(extensionId || normalized?.extension_id);
    if (!id || RESERVED_IDS.has(id)) return null;
    if (!state.external_extensions[id]) state.external_extensions[id] = emptyEntry(normalized || { extension_id: id });
    if (normalized) {
      state.external_extensions[id].record = normalized;
      if (normalized.enabled && state.external_extensions[id].enabled === false && !state.external_extensions[id].dirty) {
        state.external_extensions[id].enabled = true;
      }
    }
    state.external_extensions[id].extension_id = id;
    return state.external_extensions[id];
  }

  function summarize() {
    const entries = Object.values(state.external_extensions);
    const active = entries.filter(item => item.enabled).length;
    const effectiveActive = entries.filter(item => item.effective_state && item.effective_state.effective_enabled).length;
    const dirty = entries.filter(item => item.dirty).length;
    const blocked = entries.filter(item => item.validation && (item.validation.status === 'blocked' || asArray(item.validation.errors).length)).length;
    return { total: entries.length, active, effective_active: effectiveActive, dirty, blocked };
  }

  function emit(reason, extensionId, extra = {}) {
    state.dirty_count = summarize().dirty;
    const detail = { reason: reason || 'changed', extension_id: extensionId || '', snapshot: api.getSnapshot(), ...asObject(extra) };
    window.dispatchEvent(new CustomEvent(EVENT_CHANGED, { detail }));
    listeners.forEach(listener => { try { listener(detail); } catch (_) {} });
  }

  function patchCoreRaw(extensionId, patch) {
    if (syncingFromCore) return;
    const core = window.NeoExternalExtensionState;
    if (core && typeof core.setRawState === 'function') core.setRawState(extensionId, patch);
  }

  function patchCoreEnabled(extensionId, enabled) {
    if (syncingFromCore) return;
    const core = window.NeoExternalExtensionState;
    if (core && typeof core.setEnabled === 'function') core.setEnabled(extensionId, !!enabled);
  }

  function applyRegistry(registryPayload, options = {}) {
    state.registry = normalizeRegistry(registryPayload);
    state.registry.installed.forEach(record => ensure(record.extension_id, record));
    state.registry.invalid.forEach(record => {
      const item = ensure(record.extension_id, record);
      if (!item) return;
      item.enabled = false;
      item.validation = {
        status: 'blocked',
        warnings: asArray(record.warnings),
        errors: [record.disabled_reason || 'Manifest is invalid.'],
        disabled_reason: record.disabled_reason || 'Manifest is invalid.',
        source: 'registry',
      };
      item.dirty = false;
    });
    state.last_hydrated_at = nowIso();
    if (!asObject(options).silent) {
      emit('registry_applied');
      window.dispatchEvent(new CustomEvent(EVENT_HYDRATED, { detail: { registry: clone(state.registry), snapshot: api.getSnapshot() } }));
    }
    return api.getSnapshot();
  }

  function hydrateFromCore() {
    const core = window.NeoExternalExtensionState;
    if (!core || typeof core.getSnapshot !== 'function') return api.getSnapshot();
    syncingFromCore = true;
    try {
      const snapshot = core.getSnapshot() || {};
      if (snapshot.registry) applyRegistry(snapshot.registry);
      const raw = asObject(snapshot.raw);
      const active = asObject(snapshot.active);
      const effective = asObject(snapshot.effective);
      const warnings = asObject(snapshot.warnings);
      const disabledReasons = asObject(snapshot.disabledReasons);
      const ids = new Set(Object.keys(raw).concat(Object.keys(active)).concat(Object.keys(effective)).concat(Object.keys(disabledReasons)));
      ids.forEach(id => {
        const item = ensure(id);
        if (!item) return;
        item.enabled = !!active[id] || !!effective[id]?.enabled;
        item.raw_state = clone(raw[id] || {});
        item.effective_state = clone(effective[id]?.effective_state || effective[id] || {});
        const disabledReason = effective[id]?.disabled_reason || disabledReasons[id] || null;
        item.validation = {
          status: effective[id]?.effective_enabled ? 'valid' : (disabledReason ? 'blocked' : 'idle'),
          warnings: clone(warnings[id] || effective[id]?.warnings || []),
          errors: disabledReason ? [disabledReason] : [],
          disabled_reason: disabledReason,
          source: 'core_preflight',
        };
        item.dirty = false;
        item.updated_at = nowIso();
      });
      state.last_context = clone(snapshot.lastContext || state.last_context || {});
      state.last_validation_at = nowIso();
    } finally {
      syncingFromCore = false;
    }
    emit('core_hydrated');
    return api.getSnapshot();
  }

  function buildPayloadBlock() {
    const out = {};
    Object.keys(state.external_extensions).sort().forEach(id => {
      const item = state.external_extensions[id];
      out[id] = {
        enabled: !!item.enabled,
        raw_state: clone(item.raw_state || {}),
        effective_state: clone(item.effective_state || {}),
        validation: clone(item.validation || { status: 'idle', warnings: [], errors: [] }),
        dirty: !!item.dirty,
      };
    });
    return out;
  }

  const api = {
    STORE_VERSION,
    EVENT_CHANGED,
    EVENT_PATCHED,
    EVENT_VALIDATION,
    EVENT_HYDRATED,
    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    ensure,
    applyRegistry,
    hydrateFromCore,
    getSnapshot() {
      return clone({ ...state, summary: summarize() });
    },
    getExtension(extensionId) {
      hydrateFromCore._reading = true;
      const item = state.external_extensions[normalizeId(extensionId)] || null;
      hydrateFromCore._reading = false;
      return clone(item);
    },
    list() {
      return Object.keys(state.external_extensions).sort().map(id => clone(state.external_extensions[id]));
    },
    setEnabled(extensionId, enabled) {
      const id = normalizeId(extensionId);
      const item = ensure(id);
      if (!item) return false;
      item.enabled = !!enabled;
      item.dirty = true;
      item.validation = { ...asObject(item.validation), status: 'dirty', errors: [], disabled_reason: null };
      item.updated_at = nowIso();
      patchCoreEnabled(id, !!enabled);
      emit('enabled_updated', id);
      return true;
    },
    setRaw(extensionId, keyOrPatch, value) {
      const id = normalizeId(extensionId);
      const item = ensure(id);
      if (!item) return false;
      const patch = typeof keyOrPatch === 'string' ? { [keyOrPatch]: value } : asObject(keyOrPatch);
      item.raw_state = { ...asObject(item.raw_state), ...clone(patch) };
      item.dirty = true;
      item.validation = { ...asObject(item.validation), status: 'dirty', errors: [], disabled_reason: null };
      item.updated_at = nowIso();
      state.last_patch_at = nowIso();
      patchCoreRaw(id, patch);
      window.dispatchEvent(new CustomEvent(EVENT_PATCHED, { detail: { extension_id: id, patch: clone(patch), snapshot: api.getSnapshot() } }));
      emit('raw_updated', id);
      return true;
    },
    replaceRaw(extensionId, rawState = {}) {
      const id = normalizeId(extensionId);
      const item = ensure(id);
      if (!item) return false;
      item.raw_state = clone(asObject(rawState));
      item.dirty = true;
      item.validation = { ...asObject(item.validation), status: 'dirty', errors: [], disabled_reason: null };
      item.updated_at = nowIso();
      patchCoreRaw(id, item.raw_state);
      emit('raw_replaced', id);
      return true;
    },
    applyValidation(extensionId, validation = {}) {
      const id = normalizeId(extensionId);
      const item = ensure(id);
      if (!item) return false;
      const errors = asArray(validation.errors || validation.blocked_reasons);
      const disabledReason = text(validation.disabled_reason || errors[0] || '');
      item.validation = {
        status: text(validation.status || (errors.length || disabledReason ? 'blocked' : 'valid')) || 'valid',
        warnings: asArray(validation.warnings),
        errors,
        disabled_reason: disabledReason || null,
        source: text(validation.source || 'validation'),
      };
      item.effective_state = clone(validation.effective_state || validation.effective || item.effective_state || {});
      if (validation.effective_enabled != null) item.effective_state.effective_enabled = !!validation.effective_enabled;
      item.dirty = false;
      item.updated_at = nowIso();
      state.last_validation_at = nowIso();
      window.dispatchEvent(new CustomEvent(EVENT_VALIDATION, { detail: { extension_id: id, validation: clone(item.validation), snapshot: api.getSnapshot() } }));
      emit('validation_applied', id);
      return true;
    },
    applyBulkValidation(validationPayload = {}) {
      const payload = asObject(validationPayload);
      const extensions = asObject(payload.extensions || payload.external_extensions || payload.validation?.extensions);
      Object.keys(extensions).forEach(id => api.applyValidation(id, extensions[id]));
      state.last_validation_at = nowIso();
      emit('bulk_validation_applied');
      return api.getSnapshot();
    },
    setContext(context = {}) {
      state.last_context = clone(asObject(context));
      emit('context_updated');
      return clone(state.last_context);
    },
    markDirty(extensionId, dirty = true) {
      const item = ensure(extensionId);
      if (!item) return false;
      item.dirty = !!dirty;
      if (dirty) item.validation = { ...asObject(item.validation), status: 'dirty' };
      emit('dirty_updated', normalizeId(extensionId));
      return true;
    },
    getPayloadBlock: buildPayloadBlock,
    getRunGate() {
      const snapshot = summarize();
      const blocked = {};
      Object.entries(state.external_extensions).forEach(([id, item]) => {
        const validation = asObject(item.validation);
        if (item.enabled && (validation.status === 'blocked' || asArray(validation.errors).length)) {
          blocked[id] = validation.disabled_reason || asArray(validation.errors)[0] || 'Extension is invalid.';
        }
        if (item.enabled && item.dirty) blocked[id] = 'Extension settings changed and need validation.';
      });
      return { ok: Object.keys(blocked).length === 0, blocked, summary: snapshot };
    },
    reset(extensionId) {
      const id = normalizeId(extensionId);
      if (!id || !state.external_extensions[id]) return false;
      const record = state.external_extensions[id].record;
      state.external_extensions[id] = emptyEntry(record || { extension_id: id });
      patchCoreEnabled(id, false);
      patchCoreRaw(id, {});
      emit('extension_reset', id);
      return true;
    },
  };

  window.NeoExtensionStateStore = api;

  window.addEventListener('neo:external-extensions:registry-refreshed', event => {
    if (event?.detail?.registry) api.applyRegistry(event.detail.registry);
    else api.hydrateFromCore();
  });
  window.addEventListener('neo:external-extensions:state-changed', () => {
    if (!hydrateFromCore._reading) api.hydrateFromCore();
  });
  window.addEventListener('neo:external-extension-ui-control-changed', () => {
    // UI renderer already writes through the store. This event exists for other panels.
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => api.hydrateFromCore(), { once: true });
  } else {
    window.setTimeout(() => api.hydrateFromCore(), 0);
  }
})();
