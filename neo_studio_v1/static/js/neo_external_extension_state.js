(function () {
  'use strict';

  const REGISTRY_URL = '/api/extensions/external-registry';
  const CAPABILITIES_URL = '/api/extensions/capabilities';
  const EVENT_CHANGED = 'neo:external-extensions:state-changed';
  const EVENT_REGISTRY = 'neo:external-extensions:registry-refreshed';
  const EVENT_VALIDATE = 'neo:external-extensions:validated';
  const RESERVED_BUILT_IN_IDS = new Set(['scene_director', 'image.scene_director', 'neo.scene_director']);
  const DEFAULT_EXTERNAL_POLICIES = Object.freeze({
    source_policy: ['none'],
    output_policy: ['preview'],
    batch_policy: 'force_1',
    context_policy: ['prompt', 'model'],
  });
  const RESTRICTED_OUTPUT_POLICIES = new Set(['replace']);
  const RESTRICTED_CONTEXT_POLICIES = new Set(['identity']);

  const state = {
    installed: {},
    active: {},
    raw: {},
    effective: {},
    warnings: {},
    disabledReasons: {},
    validationReport: { ok: true, active: [], blocked: [], disabled: {}, warnings: [], auto_fixes: {}, validator_version: 'external-extension-workflow-validator-v1' },
    registry: {
      installed: [],
      enabled: [],
      disabled: [],
      invalid: [],
      warnings: [],
    },
    capabilities: {},
    capabilityWarnings: [],
    capabilitySearchPaths: {},
    lastCapabilityRefreshAt: null,
    lastContext: {},
    lastRefreshAt: null,
    initialized: false,
  };

  const listeners = new Set();

  function clone(value) {
    try { return JSON.parse(JSON.stringify(value)); } catch (_) { return value; }
  }

  function asArray(value) {
    return Array.isArray(value) ? value.slice() : [];
  }

  function asObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function text(value) {
    return String(value == null ? '' : value).trim();
  }

  function normalizeId(value) {
    return text(value).toLowerCase();
  }

  function normalizeExtensionRecord(record) {
    const src = asObject(record);
    const extensionId = normalizeId(src.extension_id || src.id);
    const surface = text(src.surface || src.target_surface || (extensionId.includes('.') ? extensionId.split('.')[0] : '')) || 'global';
    const slug = text(src.slug || (extensionId.includes('.') ? extensionId.split('.').slice(1).join('.') : extensionId));
    const status = text(src.status || (src.enabled ? 'enabled' : 'disabled')).toLowerCase() || 'disabled';
    return {
      extension_id: extensionId,
      id: extensionId,
      name: text(src.name || src.display_name || slug || extensionId || 'External extension'),
      type: text(src.type || 'external_extension') || 'external_extension',
      surface,
      slug,
      enabled: !!src.enabled || status === 'enabled',
      installed: src.installed !== false,
      status,
      target_sections: asArray(src.target_sections),
      supported_workflows: asArray(src.supported_workflows),
      supported_model_families: asArray(src.supported_model_families),
      source_policy: asArray(src.source_policy).length ? asArray(src.source_policy) : DEFAULT_EXTERNAL_POLICIES.source_policy.slice(),
      output_policy: asArray(src.output_policy).length ? asArray(src.output_policy) : DEFAULT_EXTERNAL_POLICIES.output_policy.slice(),
      batch_policy: text(src.batch_policy || DEFAULT_EXTERNAL_POLICIES.batch_policy),
      context_policy: asArray(src.context_policy).length ? asArray(src.context_policy) : DEFAULT_EXTERNAL_POLICIES.context_policy.slice(),
      ui_schema: asObject(src.ui_schema),
      capability_requirements: asObject(src.capability_requirements),
      required_comfy_nodes: asArray(src.required_comfy_nodes),
      required_workflow_templates: asArray(src.required_workflow_templates),
      policy_version: text(src.policy_version || 'external-extension-policy-v1'),
      policy_defaults_applied: asObject(src.policy_defaults_applied),
      policy_restricted: asObject(src.policy_restricted),
      policy_warnings: asArray(src.policy_warnings),
      disabled_reason: text(src.disabled_reason || ''),
      warnings: asArray(src.warnings),
      raw_manifest: clone(src),
    };
  }

  function dedupeRecords(list) {
    const out = [];
    const seen = new Set();
    asArray(list).forEach(item => {
      const record = normalizeExtensionRecord(item);
      if (!record.extension_id || seen.has(record.extension_id)) return;
      seen.add(record.extension_id);
      out.push(record);
    });
    return out;
  }

  function normalizeRegistryPayload(payload) {
    const src = asObject(payload);
    const installed = dedupeRecords(src.installed || src.external_extensions || []);
    const enabled = dedupeRecords(src.enabled || installed.filter(item => item.enabled || item.status === 'enabled'));
    const disabled = dedupeRecords(src.disabled || installed.filter(item => !item.enabled && item.status !== 'invalid'));
    const invalid = dedupeRecords(src.invalid || src.invalid_extensions || []);
    return {
      installed,
      enabled,
      disabled,
      invalid,
      warnings: asArray(src.warnings),
      raw: clone(src),
    };
  }

  function buildContext(partial = {}) {
    const root = document.getElementById('tab-generate') || document;
    const activeWorkspace = document.querySelector('[data-generation-workspace].active')?.getAttribute('data-generation-workspace') || '';
    const workflow = text(document.getElementById('generation-workflow-type')?.value || partial.workflow || partial.workflow_type || 'txt2img') || 'txt2img';
    const family = text(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || document.getElementById('generation-family')?.value || partial.family || 'sdxl_sd') || 'sdxl_sd';
    const batchSize = Number(document.getElementById('generation-batch-size')?.value || partial.batch_size || partial.batchSize || 1) || 1;
    const hasSourceImage = !!document.getElementById('generation-source-image')?.files?.[0] || !!partial.has_source_image;
    const positive = text(document.getElementById('generation-positive')?.value || partial.positive || '');
    return {
      surface: 'image',
      workspace: activeWorkspace || partial.workspace || 'create',
      workflow,
      workflow_type: workflow,
      family,
      batch_size: batchSize,
      has_source_image: hasSourceImage,
      has_prompt: !!positive,
      source_image_available: hasSourceImage,
      prompt_available: !!positive,
      root_available: !!root,
      ...asObject(partial),
    };
  }

  function extensionSupportsList(record, field, value) {
    const allowed = asArray(record[field]).map(item => text(item).toLowerCase()).filter(Boolean);
    const current = text(value).toLowerCase();
    return !allowed.length || allowed.includes('*') || allowed.includes('any') || allowed.includes(current);
  }

  function sourceAvailable(record, context) {
    const policy = asArray(record.source_policy).map(item => text(item).toLowerCase()).filter(Boolean);
    if (!policy.length || policy.includes('none') || policy.includes('prompt')) return true;
    if (policy.includes('selected_image') || policy.includes('upload') || policy.includes('source_image')) return !!(context.has_source_image || context.source_image_available);
    if (policy.includes('output')) return !!context.selected_output_available;
    return true;
  }

  function validateRecord(record, context = {}) {
    const warnings = asArray(record.warnings).concat(asArray(record.policy_warnings));
    let disabledReason = text(record.disabled_reason || '');
    let effectiveEnabled = !!state.active[record.extension_id] || !!record.enabled || record.status === 'enabled';

    if (record.type !== 'external_extension') {
      effectiveEnabled = false;
      disabledReason = 'Only external_extension records can use NeoExternalExtensionState.';
    }
    if (RESERVED_BUILT_IN_IDS.has(record.extension_id)) {
      effectiveEnabled = false;
      disabledReason = 'Reserved built-in module ID. Built-in systems are not external extensions.';
    }
    if (record.status === 'invalid') {
      effectiveEnabled = false;
      disabledReason = disabledReason || 'Manifest is invalid.';
    }
    if (record.status === 'missing_dependency') {
      effectiveEnabled = false;
      disabledReason = disabledReason || 'Missing dependency.';
    }
    if (effectiveEnabled && !extensionSupportsList(record, 'supported_workflows', context.workflow || context.workflow_type)) {
      effectiveEnabled = false;
      disabledReason = `Unsupported workflow: ${context.workflow || context.workflow_type || 'unknown'}`;
    }
    if (effectiveEnabled && !extensionSupportsList(record, 'supported_model_families', context.family)) {
      effectiveEnabled = false;
      disabledReason = `Unsupported model family: ${context.family || 'unknown'}`;
    }
    if (effectiveEnabled && !sourceAvailable(record, context)) {
      effectiveEnabled = false;
      disabledReason = 'Required source is not available.';
    }
    const selectedOutputPolicy = text(state.raw[record.extension_id]?.output_policy || record.output_policy?.[0] || DEFAULT_EXTERNAL_POLICIES.output_policy[0]).toLowerCase();
    if (RESTRICTED_OUTPUT_POLICIES.has(selectedOutputPolicy) && !state.raw[record.extension_id]?.replace_confirmed) {
      effectiveEnabled = false;
      disabledReason = 'Replacement output policy requires visible user confirmation.';
    }
    const contextPolicy = asArray(record.context_policy).map(item => text(item).toLowerCase()).filter(Boolean);
    if (contextPolicy.some(item => RESTRICTED_CONTEXT_POLICIES.has(item)) && !state.raw[record.extension_id]?.identity_context_confirmed) {
      effectiveEnabled = false;
      disabledReason = 'Identity context requires explicit visible user confirmation.';
    }
    const batchPolicy = text(record.batch_policy || DEFAULT_EXTERNAL_POLICIES.batch_policy).toLowerCase();
    if (effectiveEnabled && batchPolicy === 'blocked' && Number(context.batch_size || 1) > 1) {
      effectiveEnabled = false;
      disabledReason = 'Batch mode is blocked by this extension.';
    }
    if (effectiveEnabled && batchPolicy === 'force_1' && Number(context.batch_size || 1) > 1) {
      warnings.push('Batch policy force_1 is active. Backend must clamp or block before workflow mutation.');
    }

    return {
      enabled: !!state.active[record.extension_id],
      effective_enabled: !!effectiveEnabled,
      source: state.raw[record.extension_id]?.source || record.source_policy?.[0] || 'none',
      target_sections: asArray(record.target_sections),
      output_policy: state.raw[record.extension_id]?.output_policy || record.output_policy?.[0] || 'preview',
      batch_policy: record.batch_policy || DEFAULT_EXTERNAL_POLICIES.batch_policy,
      context_policy: asArray(record.context_policy),
      policy_version: record.policy_version || 'external-extension-policy-v1',
      raw_state: clone(state.raw[record.extension_id] || {}),
      effective_state: {
        extension_id: record.extension_id,
        status: record.status,
        workflow: context.workflow || context.workflow_type || '',
        family: context.family || '',
        batch_size: Number(context.batch_size || 1) || 1,
      },
      warnings: warnings.filter(Boolean),
      disabled_reason: disabledReason || null,
    };
  }

  function emitChanged(reason = 'state_changed') {
    const detail = { reason, snapshot: api.getSnapshot() };
    window.dispatchEvent(new CustomEvent(EVENT_CHANGED, { detail }));
    listeners.forEach(listener => {
      try { listener(detail); } catch (_) {}
    });
    renderStatePanel();
  }

  function applyRegistry(registry) {
    state.registry = normalizeRegistryPayload(registry);
    state.installed = {};
    state.registry.installed.forEach(record => {
      state.installed[record.extension_id] = record;
      if (record.enabled || record.status === 'enabled') state.active[record.extension_id] = true;
      if (!state.raw[record.extension_id]) state.raw[record.extension_id] = {};
    });
    state.registry.invalid.forEach(record => {
      if (record.extension_id) state.disabledReasons[record.extension_id] = record.disabled_reason || 'Manifest is invalid.';
    });
    state.initialized = true;
    state.lastRefreshAt = new Date().toISOString();
    api.revalidate(state.lastContext || {});
    window.dispatchEvent(new CustomEvent(EVENT_REGISTRY, { detail: { registry: api.getRegistrySnapshot() } }));
    emitChanged('registry_refreshed');
    return api.getRegistrySnapshot();
  }

  function renderStatePanel() {
    const host = document.getElementById('neo-ext-slot-image-extensions-manager');
    if (!host) return;
    const registry = state.registry || {};
    const installed = asArray(registry.installed);
    const invalid = asArray(registry.invalid);
    const enabledCount = Object.values(state.effective || {}).filter(item => item && item.effective_enabled).length;
    const warningCount = Object.values(state.warnings || {}).reduce((total, list) => total + asArray(list).length, 0);
    const disabledCount = Object.values(state.disabledReasons || {}).filter(Boolean).length;
    host.dataset.neoSlotEmpty = installed.length ? 'false' : 'true';
    const cards = installed.slice(0, 24).map(record => {
      const effective = state.effective[record.extension_id] || validateRecord(record, state.lastContext || {});
      const warnings = asArray(effective.warnings);
      const capability = asObject(state.capabilities[record.extension_id]);
      const missingCapability = asArray(capability.missing);
      const disabledReason = effective.disabled_reason || state.disabledReasons[record.extension_id] || '';
      return `<div class="mini-note" data-neo-external-extension-card="${record.extension_id}" style="margin-top:10px;">
        <div class="row-between" style="gap:10px; align-items:flex-start; flex-wrap:wrap;">
          <div><strong>${escapeHtml(record.name)}</strong><div class="muted small">${escapeHtml(record.extension_id)} · ${escapeHtml(record.surface)}</div></div>
          <span class="badge">${effective.effective_enabled ? 'Active' : record.status || 'Disabled'}</span>
          <span class="badge">${capability.available ? 'Ready' : (missingCapability.length ? 'Missing requirements' : 'Capability unchecked')}</span>
        </div>
        <div class="muted small" style="margin-top:6px;">Targets: ${escapeHtml(asArray(record.target_sections).join(', ') || 'Not declared')}</div>
        <div class="muted small" style="margin-top:4px;">Policies: source=${escapeHtml(asArray(record.source_policy).join('/') || 'none')} · output=${escapeHtml(asArray(record.output_policy).join('/') || 'preview')} · batch=${escapeHtml(record.batch_policy || 'force_1')} · context=${escapeHtml(asArray(record.context_policy).join('/') || 'prompt/model')}</div>
        ${missingCapability.length ? `<div class="status warn" style="margin-top:6px;">Missing: ${escapeHtml(missingCapability.slice(0, 3).join(', '))}</div>` : ''}
        ${disabledReason ? `<div class="status warn" style="margin-top:6px;">Disabled: ${escapeHtml(disabledReason)}</div>` : ''}
        ${warnings.length ? `<div class="status warn" style="margin-top:6px;">Warning: ${escapeHtml(warnings[0])}</div>` : ''}
      </div>`;
    }).join('');
    const invalidHtml = invalid.length ? `<div class="status warn" style="margin-top:10px;">${invalid.length} invalid external extension manifest${invalid.length === 1 ? '' : 's'} blocked.</div>` : '';
    let stateRoot = host.querySelector(':scope > [data-neo-extension-state-summary="true"]');
    if (!stateRoot) {
      stateRoot = document.createElement('div');
      stateRoot.dataset.neoExtensionStateSummary = 'true';
      host.prepend(stateRoot);
    }
    stateRoot.innerHTML = `
      <div class="mini-note" style="margin-top:0;">
        <strong>Central external extension state</strong>
        <div class="muted small" style="margin-top:4px;">Installed: ${installed.length} · Effective active: ${enabledCount} · Disabled reasons: ${disabledCount} · Warnings: ${warningCount}</div>
      </div>
      ${cards || '<div class="mini-note" style="margin-top:10px;">No external extensions registered yet. State shell is ready and will stay empty until valid external manifests are installed.</div>'}
      ${invalidHtml}`;
    const empty = document.getElementById('generation-external-extensions-empty');
    if (empty) empty.textContent = installed.length
      ? 'External extension state is visible below. Invalid or disabled extensions cannot mutate generation payloads.'
      : 'No external extension UI is mounted yet. Central state is active and ready for future add-ons.';
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }


  function buildValidationReport() {
    const block = state.effective || {};
    const active = [];
    const blocked = [];
    const disabled = {};
    const warnings = [];
    const autoFixes = {};
    Object.keys(block).sort().forEach(id => {
      const item = block[id] || {};
      if (item.effective_enabled) active.push(id);
      if (item.enabled && !item.effective_enabled) blocked.push(id);
      if (item.disabled_reason) disabled[id] = item.disabled_reason;
      asArray(item.warnings).forEach(warning => warnings.push(`${id}: ${warning}`));
      const fixes = asArray(item.effective_state && item.effective_state.auto_fixes);
      if (fixes.length) autoFixes[id] = fixes;
    });
    return {
      ok: blocked.length === 0,
      active,
      blocked,
      disabled,
      warnings,
      auto_fixes: autoFixes,
      validator_version: 'external-extension-workflow-validator-v1',
      policy: 'block_or_auto_disable_with_visible_reason',
    };
  }

  const api = {
    get initialized() { return state.initialized; },
    get EVENT_CHANGED() { return EVENT_CHANGED; },
    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot() {
      return clone({
        installed: state.installed,
        active: state.active,
        raw: state.raw,
        effective: state.effective,
        warnings: state.warnings,
        disabledReasons: state.disabledReasons,
        validationReport: state.validationReport,
        registry: state.registry,
        capabilities: state.capabilities,
        capabilityWarnings: state.capabilityWarnings,
        capabilitySearchPaths: state.capabilitySearchPaths,
        lastCapabilityRefreshAt: state.lastCapabilityRefreshAt,
        lastContext: state.lastContext,
        lastRefreshAt: state.lastRefreshAt,
        initialized: state.initialized,
      });
    },
    getRegistrySnapshot() {
      return clone(state.registry);
    },
    getCapabilitySnapshot() {
      return clone({ capabilities: state.capabilities, warnings: state.capabilityWarnings, search_paths: state.capabilitySearchPaths, lastRefreshAt: state.lastCapabilityRefreshAt });
    },
    async refreshCapabilities() {
      try {
        const res = await fetch(`${CAPABILITIES_URL}?surface=image&_=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`External extension capabilities returned HTTP ${res.status}`);
        const data = await res.json();
        state.capabilities = asObject(data.capabilities);
        state.capabilityWarnings = asArray(data.warnings);
        state.capabilitySearchPaths = asObject(data.search_paths);
        state.lastCapabilityRefreshAt = new Date().toISOString();
        emitChanged('capabilities_refreshed');
        return api.getCapabilitySnapshot();
      } catch (err) {
        state.capabilityWarnings = [`Could not load external extension capabilities: ${err?.message || err}`];
        emitChanged('capabilities_refresh_failed');
        return api.getCapabilitySnapshot();
      }
    },
    async refreshRegistry() {
      try {
        const res = await fetch(`${REGISTRY_URL}?_=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`External extension registry returned HTTP ${res.status}`);
        const data = await res.json();
        const registry = applyRegistry(data);
        api.refreshCapabilities();
        return registry;
      } catch (err) {
        state.registry.warnings = [`Could not load external extension registry: ${err?.message || err}`];
        emitChanged('registry_refresh_failed');
        return api.getRegistrySnapshot();
      }
    },
    setRawState(extensionId, rawState = {}) {
      const id = normalizeId(extensionId);
      if (!id || RESERVED_BUILT_IN_IDS.has(id)) return false;
      state.raw[id] = { ...asObject(state.raw[id]), ...asObject(rawState) };
      api.revalidate(state.lastContext || {});
      emitChanged('raw_state_updated');
      return true;
    },
    setEnabled(extensionId, enabled) {
      const id = normalizeId(extensionId);
      if (!id || RESERVED_BUILT_IN_IDS.has(id)) return false;
      state.active[id] = !!enabled;
      api.revalidate(state.lastContext || {});
      emitChanged('enabled_state_updated');
      return true;
    },
    revalidate(context = {}) {
      const nextContext = buildContext(context);
      state.lastContext = nextContext;
      state.effective = {};
      state.warnings = {};
      state.disabledReasons = {};
      asArray(state.registry.installed).forEach(record => {
        const effective = validateRecord(record, nextContext);
        state.effective[record.extension_id] = effective;
        state.warnings[record.extension_id] = asArray(effective.warnings);
        if (effective.disabled_reason) state.disabledReasons[record.extension_id] = effective.disabled_reason;
      });
      asArray(state.registry.invalid).forEach(record => {
        if (record.extension_id) state.disabledReasons[record.extension_id] = record.disabled_reason || 'Manifest is invalid.';
      });
      state.validationReport = buildValidationReport();
      if (window.NeoExtensionStateStore && typeof window.NeoExtensionStateStore.applyBulkValidation === 'function') {
        window.NeoExtensionStateStore.applyBulkValidation({ extensions: state.effective });
      }
      window.dispatchEvent(new CustomEvent(EVENT_VALIDATE, { detail: { context: clone(nextContext), effective: clone(state.effective) } }));
      renderStatePanel();
      return clone(state.effective);
    },
    getPayloadBlock(context = {}) {
      api.revalidate(context);
      const block = {};
      Object.keys(state.effective || {}).sort().forEach(id => {
        const item = state.effective[id];
        if (!item) return;
        block[id] = clone(item);
      });
      return block;
    },
    getValidationReport(context = {}) {
      if (context && Object.keys(asObject(context)).length) api.revalidate(context);
      return clone(state.validationReport || buildValidationReport());
    },
    getPolicyDefaults() {
      return clone(DEFAULT_EXTERNAL_POLICIES);
    },
    applyToPayload(payload = {}, context = {}) {
      const target = asObject(payload);
      const block = api.getPayloadBlock({ ...buildContext(target), ...asObject(context) });
      target.external_extensions = block;
      const validationReport = api.getValidationReport();
      target._neo_external_extensions_validation = validationReport;
      const store = window.NeoExtensionStateStore;
      const storeSnapshot = store && typeof store.getSnapshot === 'function' ? store.getSnapshot() : null;
      const storeGate = store && typeof store.getRunGate === 'function' ? store.getRunGate() : null;
      target._neo_external_extensions_frontend_state = {
        visible: true,
        raw_effective_separated: true,
        initialized: state.initialized,
        active: Object.keys(block).filter(id => block[id]?.effective_enabled),
        disabled: Object.keys(block).filter(id => !block[id]?.effective_enabled && block[id]?.disabled_reason),
        warnings: Object.fromEntries(Object.entries(block).map(([id, item]) => [id, asArray(item.warnings)])),
        validation: validationReport,
        store_version: storeSnapshot?.version || null,
        store_summary: storeSnapshot?.summary || null,
        store_gate: storeGate || null,
      };
      return target;
    },
    render: renderStatePanel,
  };

  window.NeoExternalExtensionState = api;

  function scheduleValidation(reason) {
    window.clearTimeout(scheduleValidation._timer);
    scheduleValidation._timer = window.setTimeout(() => {
      api.revalidate({ reason });
      emitChanged(reason || 'context_changed');
    }, 80);
  }

  function bindContextListeners() {
    [
      'generation-workflow-type',
      'generation-family',
      'generation-batch-size',
      'generation-positive',
      'generation-model-source',
      'generation-source-image',
    ].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const eventName = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? 'input' : 'change';
      el.addEventListener(eventName, () => scheduleValidation(`${id}_changed`));
      el.addEventListener('change', () => scheduleValidation(`${id}_changed`));
    });
    window.addEventListener('neo:generation-family-changed', () => scheduleValidation('generation_family_changed'));
    window.addEventListener('neo:generation-workspace-changed', event => scheduleValidation(event?.detail?.workspace || 'workspace_changed'));
    window.addEventListener('neo:extension-mounted', () => scheduleValidation('extension_mounted'));
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  ready(() => {
    bindContextListeners();
    api.refreshRegistry();
    renderStatePanel();
  });
})();
