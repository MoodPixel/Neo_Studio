(function () {
  'use strict';

  const REGISTRY_URL = '/api/extensions/external-registry';
  const CAPABILITIES_URL = '/api/extensions/capabilities';
  const COMPATIBILITY_URL = '/api/extensions/compatibility';
  const EVENT_CHANGED = 'neo:external-extensions:state-changed';
  const EVENT_REGISTRY = 'neo:external-extensions:registry-refreshed';
  const EVENT_VALIDATE = 'neo:external-extensions:validated';
  const EVENT_COMPATIBILITY = 'neo:external-extensions:compatibility-refreshed';
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
    validationReport: { ok: true, active: [], blocked: [], disabled: {}, warnings: [], auto_fixes: {}, validator_version: 'external-extension-workflow-validator-v2' },
    registry: {
      installed: [],
      enabled: [],
      disabled: [],
      invalid: [],
      warnings: [],
    },
    capabilities: {},
    compatibility: { ok: true, results: {}, visible: [], enabled: [], blocked: [], warnings: [], errors: [] },
    lastCompatibilityRefreshAt: null,
    compatibilityWarnings: [],
    capabilityWarnings: [],
    capabilitySearchPaths: {},
    lastCapabilityRefreshAt: null,
    lastContext: {},
    lastCompatibilityQuery: '',
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
      extension_targets: asArray(src.extension_targets || src.targets),
      targets: asArray(src.targets || src.extension_targets),
      image_systems: asArray(src.image_systems || src.systems),
      systems: asArray(src.systems || src.image_systems),
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
      metadata_adapter_version: text(src.metadata_adapter_version || ''),
      ui: asObject(src.ui),
      workflow: asObject(src.workflow),
      output: asObject(src.output),
      output_visibility: asObject(src.output_visibility),
      workflow_mode: text(src.workflow_mode || src.workflow?.mode || ''),
      output_policy_default: text(src.output_policy_default || src.output?.default_policy || src.output?.policy || ''),
      primary_output_type: text(src.primary_output_type || src.output?.primary_output_type || src.output?.primary_type || ''),
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

  function getNeoImageStateSnapshot() {
    const api = window.NeoImageState;
    if (!api || typeof api.getState !== 'function') return {};
    try { return asObject(api.getState()); } catch (_) { return {}; }
  }

  function buildContext(partial = {}) {
    const root = document.getElementById('tab-generate') || document;
    const activeWorkspace = document.querySelector('[data-generation-workspace].active')?.getAttribute('data-generation-workspace') || '';
    const imageState = getNeoImageStateSnapshot();
    const imageSource = asObject(imageState.source);
    const workflow = text(partial.workflow || partial.workflow_type || imageState.workflow_type || imageState.mode || document.getElementById('generation-workflow-type')?.value || 'txt2img') || 'txt2img';
    const family = text(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || partial.family || imageState.build?.family || document.getElementById('generation-family')?.value || 'sdxl_sd') || 'sdxl_sd';
    const backend = text(partial.backend || partial.inpaint_backend || partial.outpaint_backend || document.getElementById('generation-outpaint-backend')?.value || document.getElementById('generation-inpaint-backend')?.value || 'standard') || 'standard';
    const section = text(partial.section || partial.target_section || '');
    const batchSize = Number(partial.batch_size || partial.batchSize || document.getElementById('generation-batch-size')?.value || 1) || 1;
    const lockedSource = asObject(imageSource.locked_source || imageSource.preview_action_target || imageSource.selected_output_snapshot);
    const hasSourceImage = !!document.getElementById('generation-source-image')?.files?.[0] || !!partial.has_source_image || !!imageSource.active_source_image || !!lockedSource.filename || !!lockedSource.output_id;
    const positive = text(partial.positive || imageState.prompt?.positive || document.getElementById('generation-positive')?.value || '');
    return {
      surface: 'image',
      workspace: activeWorkspace || partial.workspace || 'create',
      workflow,
      workflow_type: workflow,
      family,
      backend,
      section,
      batch_size: batchSize,
      has_source_image: hasSourceImage,
      has_prompt: !!positive,
      source_image_available: hasSourceImage,
      source_kind: text(imageSource.explicit_source_type || imageSource.source_route_state?.source_kind || lockedSource.source_type || 'none') || 'none',
      source_id: text(imageSource.source_route_state?.source_id || lockedSource.output_id || lockedSource.filename || imageSource.active_source_image || ''),
      prompt_available: !!positive,
      root_available: !!root,
      workflow_state_owner: 'NeoImageState',
      image_workflow_state: {
        mode: workflow,
        workflow_type: workflow,
        source_kind: text(imageSource.explicit_source_type || imageSource.source_route_state?.source_kind || lockedSource.source_type || 'none') || 'none',
        source_id: text(imageSource.source_route_state?.source_id || lockedSource.output_id || lockedSource.filename || imageSource.active_source_image || ''),
      },
      ...asObject(partial),
    };
  }



  function firstText(...values) {
    for (const value of values) {
      if (Array.isArray(value)) {
        for (const item of value) {
          const hit = text(item).toLowerCase().replace(/\s+/g, '_');
          if (hit) return hit;
        }
      } else {
        const hit = text(value).toLowerCase().replace(/\s+/g, '_');
        if (hit) return hit;
      }
    }
    return '';
  }

  function metadataBlocks(record) {
    return {
      workflow: asObject(record.workflow),
      output: asObject(record.output),
      visibility: asObject(record.output_visibility),
    };
  }

  function workflowModeFor(record, raw = {}) {
    const blocks = metadataBlocks(record);
    return firstText(raw.workflow_mode, blocks.workflow.mode, record.workflow_mode, blocks.workflow.patch_strategies, 'metadata_only');
  }

  function outputPolicyFor(record, raw = {}) {
    const blocks = metadataBlocks(record);
    return firstText(raw.output_policy, blocks.output.policy, blocks.output.default_policy, record.output_policy_default, record.output_policy, DEFAULT_EXTERNAL_POLICIES.output_policy[0]);
  }

  function outputTargetFor(record, raw = {}) {
    const blocks = metadataBlocks(record);
    return firstText(raw.target, blocks.workflow.target, record.target, record.supported_workflows, record.target_sections);
  }

  function outputAffectingFor(record, raw = {}) {
    const blocks = metadataBlocks(record);
    const mode = workflowModeFor(record, raw);
    const policy = outputPolicyFor(record, raw);
    return !!(
      blocks.output.output_affecting ||
      blocks.output.primary_type ||
      blocks.output.primary_output_type ||
      asArray(blocks.output.outputs).length ||
      ['replace_workflow', 'sidecar_run', 'postprocess_output', 'preprocess_source', 'mixed_workflow'].includes(mode) ||
      ['new_run', 'append', 'replace'].includes(policy) ||
      blocks.workflow.patch_count
    );
  }

  function visibilityErrorsFor(record, raw = {}) {
    if (!outputAffectingFor(record, raw)) return [];
    const blocks = metadataBlocks(record);
    const errors = [];
    const mode = workflowModeFor(record, raw);
    if (blocks.visibility.hidden_behavior_allowed) errors.push('hidden_output_behavior_not_allowed');
    if (blocks.visibility.target_visible === false) errors.push('output_target_must_be_visible');
    if (blocks.visibility.output_policy_visible === false) errors.push('output_policy_must_be_visible');
    if (['replace_workflow', 'sidecar_run', 'postprocess_output', 'preprocess_source', 'mixed_workflow'].includes(mode) && blocks.visibility.workflow_mode_visible === false) errors.push('workflow_mode_must_be_visible');
    if (!outputTargetFor(record, raw)) errors.push('output_affecting_extension_missing_target');
    if (!outputPolicyFor(record, raw)) errors.push('output_affecting_extension_missing_output_policy');
    if (mode === 'replace_workflow' && !blocks.workflow.requires_visible_confirmation && !raw.replace_workflow_confirmed) errors.push('replace_workflow_requires_visible_confirmation');
    return errors;
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


  function compatibilityFor(extensionId) {
    const id = normalizeId(extensionId);
    const report = asObject(state.compatibility);
    return asObject(asObject(report.results)[id]);
  }

  function compatibilityMessages(result, kind) {
    const bucket = kind === 'warnings' ? asArray(result.warnings) : asArray(result.errors);
    return bucket.map(item => typeof item === 'string' ? item : text(item.message || item.code)).filter(Boolean);
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
    const rawState = asObject(state.raw[record.extension_id]);
    const selectedOutputPolicy = outputPolicyFor(record, rawState);
    const workflowMode = workflowModeFor(record, rawState);
    const outputTarget = outputTargetFor(record, rawState);
    const outputAffecting = outputAffectingFor(record, rawState);
    const visibilityErrors = visibilityErrorsFor(record, rawState);
    if (RESTRICTED_OUTPUT_POLICIES.has(selectedOutputPolicy) && !rawState.replace_confirmed) {
      effectiveEnabled = false;
      disabledReason = 'Replacement output policy requires visible user confirmation.';
    }
    if (effectiveEnabled && visibilityErrors.length) {
      effectiveEnabled = false;
      disabledReason = visibilityErrors[0];
    }
    const capability = asObject(state.capabilities[record.extension_id]);
    const missingComfyNodes = asArray(capability.missing || capability.missing_nodes || capability.missing_comfy_nodes);
    if (effectiveEnabled && missingComfyNodes.length) {
      effectiveEnabled = false;
      disabledReason = `missing_comfy_nodes:${missingComfyNodes.join(',')}`;
    }
    const compatibility = compatibilityFor(record.extension_id);
    if (Object.keys(compatibility).length) {
      compatibilityMessages(compatibility, 'warnings').forEach(message => { if (!warnings.includes(message)) warnings.push(message); });
      if (effectiveEnabled && compatibility.blocked) {
        effectiveEnabled = false;
        disabledReason = compatibility.disabled_message || compatibility.disabled_reason || 'Extension is disabled by compatibility resolver.';
      }
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
      output_policy: selectedOutputPolicy || 'preview',
      workflow_mode: workflowMode,
      output_target: outputTarget,
      output_affecting: outputAffecting,
      batch_policy: record.batch_policy || DEFAULT_EXTERNAL_POLICIES.batch_policy,
      compatibility,
      context_policy: asArray(record.context_policy),
      policy_version: record.policy_version || 'external-extension-policy-v1',
      raw_state: clone(rawState || {}),
      effective_state: {
        extension_id: record.extension_id,
        status: record.status,
        workflow: context.workflow || context.workflow_type || '',
        family: context.family || '',
        batch_size: Number(context.batch_size || 1) || 1,
        workflow_mode: workflowMode,
        output_policy: selectedOutputPolicy || 'preview',
        output_target: outputTarget,
        output_affecting: outputAffecting,
        visibility_errors: visibilityErrors,
        missing_comfy_nodes: missingComfyNodes,
        compatibility,
        status_chip: missingComfyNodes.length ? 'Needs node' : (disabledReason && String(disabledReason).includes('conflict') ? 'Conflict' : (effectiveEnabled ? 'Ready' : 'Blocked')),
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
      const compatibility = asObject(effective.compatibility || compatibilityFor(record.extension_id));
      const compatStatus = text(compatibility.status || '');
      const compatReason = text(compatibility.disabled_message || compatibility.disabled_reason || '');
      const disabledReason = effective.disabled_reason || state.disabledReasons[record.extension_id] || '';
      return `<div class="mini-note" data-neo-external-extension-card="${record.extension_id}" style="margin-top:10px;">
        <div class="row-between" style="gap:10px; align-items:flex-start; flex-wrap:wrap;">
          <div><strong>${escapeHtml(record.name)}</strong><div class="muted small">${escapeHtml(record.extension_id)} · ${escapeHtml(record.surface)}</div></div>
          <span class="badge">${effective.effective_enabled ? 'Active' : record.status || 'Disabled'}</span>
          <span class="badge">${capability.available ? 'Ready' : (missingCapability.length ? 'Missing requirements' : 'Capability unchecked')}</span>
          ${compatStatus ? `<span class="badge">Compat: ${escapeHtml(compatStatus)}</span>` : ''}
        </div>
        <div class="muted small" style="margin-top:6px;">Targets: ${escapeHtml(asArray(record.extension_targets).concat(asArray(record.target_sections)).filter(Boolean).join(', ') || 'Not declared')}</div>
        <div class="muted small" style="margin-top:4px;">Policies: source=${escapeHtml(asArray(record.source_policy).join('/') || 'none')} · output=${escapeHtml(asArray(record.output_policy).join('/') || 'preview')} · batch=${escapeHtml(record.batch_policy || 'force_1')} · context=${escapeHtml(asArray(record.context_policy).join('/') || 'prompt/model')}</div>
        ${missingCapability.length ? `<div class="status warn" style="margin-top:6px;">Missing: ${escapeHtml(missingCapability.slice(0, 3).join(', '))}</div>` : ''}
        ${compatReason ? `<div class="status warn" style="margin-top:6px;">Compatibility: ${escapeHtml(compatReason)}</div>` : ''}
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
        <div class="muted small" style="margin-top:4px;">Installed: ${installed.length} · Effective active: ${enabledCount} · Disabled reasons: ${disabledCount} · Warnings: ${warningCount} · Compatibility blocks: ${asArray(asObject(state.compatibility).blocked).length}</div>
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
      compatibility: clone(state.compatibility || {}),
      compatibility_resolver_version: text(asObject(state.compatibility).version || ''),
      validator_version: 'external-extension-workflow-validator-v2',
      policy: 'block_or_auto_disable_with_visible_reason',
    };
  }


  function compatibilityQuery(context) {
    const src = buildContext(context || {});
    return [src.surface || 'image', src.family || 'sdxl_sd', src.workflow || src.workflow_type || 'txt2img', src.backend || 'standard', src.section || ''].join('|');
  }

  function scheduleCompatibilityRefresh(context = {}) {
    const query = compatibilityQuery(context);
    if (state.lastCompatibilityQuery === query) return;
    state.lastCompatibilityQuery = query;
    window.clearTimeout(scheduleCompatibilityRefresh._timer);
    scheduleCompatibilityRefresh._timer = window.setTimeout(() => {
      api.refreshCompatibility(context, { silent: true });
    }, 120);
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
        compatibility: state.compatibility,
        compatibilityWarnings: state.compatibilityWarnings,
        lastCompatibilityRefreshAt: state.lastCompatibilityRefreshAt,
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

    async refreshCompatibility(context = {}, options = {}) {
      const nextContext = buildContext(context);
      const params = new URLSearchParams({
        surface: nextContext.surface || 'image',
        family: nextContext.family || 'sdxl_sd',
        workflow: nextContext.workflow || nextContext.workflow_type || 'txt2img',
        backend: nextContext.backend || 'standard',
        section: nextContext.section || '',
        _: String(Date.now()),
      });
      try {
        const res = await fetch(`${COMPATIBILITY_URL}?${params.toString()}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`Extension compatibility returned HTTP ${res.status}`);
        const data = await res.json();
        state.compatibility = asObject(data);
        state.compatibilityWarnings = asArray(data.warnings);
        state.lastCompatibilityRefreshAt = new Date().toISOString();
        window.dispatchEvent(new CustomEvent(EVENT_COMPATIBILITY, { detail: { compatibility: clone(state.compatibility), context: clone(nextContext) } }));
        if (!asObject(options).silent) emitChanged('compatibility_refreshed');
        api.revalidate(nextContext, { skipCompatibilityRefresh: true });
        return clone(state.compatibility);
      } catch (err) {
        state.compatibilityWarnings = [`Could not load extension compatibility: ${err?.message || err}`];
        if (!asObject(options).silent) emitChanged('compatibility_refresh_failed');
        return clone(state.compatibility);
      }
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
        api.refreshCompatibility(state.lastContext || {}, { silent: true });
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
    revalidate(context = {}, options = {}) {
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
      const replaceIds = Object.keys(state.effective).filter(id => state.effective[id]?.enabled && state.effective[id]?.effective_state?.workflow_mode === 'replace_workflow');
      if (replaceIds.length > 1) {
        const reason = `workflow_replacement_conflict:${replaceIds.join(',')}`;
        replaceIds.forEach(id => {
          const item = state.effective[id];
          item.effective_enabled = false;
          item.disabled_reason = reason;
          item.warnings = asArray(item.warnings).concat(['Only one external extension may replace the base workflow per run.']);
          item.effective_state = {
            ...asObject(item.effective_state),
            effective_enabled: false,
            workflow_conflict: true,
            conflicting_extensions: replaceIds.slice(),
            status_chip: 'Conflict',
          };
          state.warnings[id] = asArray(item.warnings);
          state.disabledReasons[id] = reason;
        });
      }
      asArray(state.registry.invalid).forEach(record => {
        if (record.extension_id) state.disabledReasons[record.extension_id] = record.disabled_reason || 'Manifest is invalid.';
      });
      state.validationReport = buildValidationReport();
      if (!asObject(options).skipCompatibilityRefresh) scheduleCompatibilityRefresh(nextContext);
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
      'generation-inpaint-backend',
      'generation-outpaint-backend',
    ].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const eventName = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? 'input' : 'change';
      el.addEventListener(eventName, () => scheduleValidation(`${id}_changed`));
      el.addEventListener('change', () => scheduleValidation(`${id}_changed`));
    });
    window.addEventListener('neo:generation-family-changed', () => scheduleValidation('generation_family_changed'));
    window.addEventListener('neo:image:workflow-mode-changed', event => scheduleValidation(event?.detail?.mode || 'image_workflow_mode_changed'));
    window.addEventListener('neo:image:workflow-validation-changed', () => scheduleValidation('image_workflow_validation_changed'));
    window.addEventListener('neo-image-state-changed', event => scheduleValidation(event?.detail?.source || 'image_state_changed'));
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
