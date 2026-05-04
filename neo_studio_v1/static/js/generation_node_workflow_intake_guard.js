// Neo Studio Generation Node Workflow Intake Guard
// Phase 7: declarative guard for adding Comfy/node workflow features without leaking
// family-blocked modules into the wrong workflow path.
// Phase 9: extension workflow compatibility support. Core specs and extension-provided
// workflow specs now share the same gate, but extension specs keep source/extension_id
// metadata so they are not confused with built-in SDXL/Qwen feature modules.
(function () {
  const DEFAULT_SPEC = Object.freeze({
    id: '',
    title: '',
    families: [],
    blocked_families: [],
    feature_key: '',
    requires_nodes: [],
    optional_nodes: [],
    payload_key: '',
    module_payload_key: '',
    ui_card: '',
    owner_module: '',
    host_tabs: ['generation'],
    status: 'active',
    notes: '',
    source: 'core',
    extension_id: '',
    workflow_id: '',
    workflow_path: '',
    workflow_kind: '',
    backend_role: '',
  });

  const CORE_WORKFLOW_FEATURE_SPECS = Object.freeze({
    dynamic_thresholding: Object.freeze({
      id: 'dynamic_thresholding',
      title: 'CFG Fix / Dynamic Thresholding',
      families: ['sdxl_sd'],
      blocked_families: [],
      feature_key: 'dynamic_thresholding',
      requires_nodes: ['DynamicThresholdingSimple'],
      optional_nodes: ['DynamicThresholdingFull'],
      payload_key: 'dynamic_thresholding',
      module_payload_key: 'modules.dynamic_thresholding',
      ui_card: 'generation-dynamic-thresholding-card',
      owner_module: 'static/js/generation_catalog_state.js',
      host_tabs: ['generation'],
      status: 'active',
      source: 'core',
      notes: 'SDXL-only. Must be hidden and forcibly disabled for Qwen/Flux/ZImage.',
    }),
    controlnet: Object.freeze({
      id: 'controlnet',
      title: 'ControlNet',
      families: ['sdxl_sd', 'flux', 'qwen_image_edit'],
      blocked_families: [],
      feature_key: 'controlnet',
      requires_nodes: [],
      optional_nodes: ['ControlNetApplyAdvanced', 'ControlNetLoader', 'ACN_AdvancedControlNetApply'],
      payload_key: 'controlnet',
      module_payload_key: 'modules.controlnet',
      ui_card: 'generation-controlnet-card',
      owner_module: 'static/js/generation_workspace_forms.js',
      host_tabs: ['generation', 'image'],
      status: 'candidate',
      source: 'core',
      notes: 'Allowed by family gate, but node support differs by backend.',
    }),
    ipadapter: Object.freeze({
      id: 'ipadapter',
      title: 'IP-Adapter',
      families: ['sdxl_sd'],
      blocked_families: [],
      feature_key: 'ipadapter',
      requires_nodes: [],
      optional_nodes: ['IPAdapterAdvanced', 'IPAdapterUnifiedLoader'],
      payload_key: 'ipadapter',
      module_payload_key: 'modules.ipadapter',
      ui_card: 'generation-ipadapter-card',
      owner_module: 'static/js/generation_workspace_forms.js',
      host_tabs: ['generation'],
      status: 'candidate',
      source: 'core',
      notes: 'Keep family-gated until Qwen/Flux paths have explicit adapter support.',
    }),
  });

  const extensionSpecs = new Map();

  const REQUIRED_FIELDS = Object.freeze([
    'id',
    'title',
    'families',
    'feature_key',
    'owner_module',
  ]);

  function slug(value) {
    return String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'workflow';
  }

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function normalizeFamily(family) {
    const registry = window.NeoGenerationFeatureAvailability;
    if (registry && typeof registry.normalizeFamily === 'function') return registry.normalizeFamily(family);
    return String(family || 'sdxl_sd').trim().toLowerCase() || 'sdxl_sd';
  }

  function knownFamilies() {
    const registry = window.NeoGenerationFeatureAvailability;
    const families = registry && registry.families ? Object.keys(registry.families) : [];
    return families.length ? families : ['sdxl_sd', 'flux', 'qwen_image_edit', 'zimage'];
  }

  function normalizeFamilyList(values, fallbackAll) {
    const raw = Array.isArray(values) ? values : [];
    const normalized = raw.map(normalizeFamily).filter(Boolean);
    const unique = Array.from(new Set(normalized));
    return unique.length ? unique : (fallbackAll ? knownFamilies() : []);
  }

  function cloneSpec(spec) {
    const item = Object.assign({}, DEFAULT_SPEC, spec || {});
    return Object.assign(item, {
      families: Array.isArray(item.families) ? item.families.slice() : [],
      blocked_families: Array.isArray(item.blocked_families) ? item.blocked_families.slice() : [],
      requires_nodes: Array.isArray(item.requires_nodes) ? item.requires_nodes.slice() : [],
      optional_nodes: Array.isArray(item.optional_nodes) ? item.optional_nodes.slice() : [],
      host_tabs: Array.isArray(item.host_tabs) ? item.host_tabs.slice() : [],
    });
  }

  function normalizeSpec(raw) {
    const item = cloneSpec(raw);
    const source = String(item.source || 'core').trim().toLowerCase() || 'core';
    item.source = source;
    item.id = String(item.id || item.workflow_id || item.feature_key || '').trim();
    item.workflow_id = String(item.workflow_id || item.id || '').trim();
    item.extension_id = String(item.extension_id || '').trim();
    item.title = String(item.title || item.id || 'Workflow').trim();
    item.feature_key = String(item.feature_key || item.id || item.workflow_id || '').trim();
    item.families = normalizeFamilyList(item.families, source === 'extension');
    item.blocked_families = normalizeFamilyList(item.blocked_families, false);
    item.host_tabs = Array.isArray(item.host_tabs) && item.host_tabs.length ? item.host_tabs : ['generation'];
    item.owner_module = String(item.owner_module || (source === 'extension' ? `extension:${item.extension_id || 'unknown'}` : '')).trim();
    item.ui_card = String(item.ui_card || (source === 'extension' ? `extension-workflow-${slug(item.id)}` : '')).trim();
    item.status = String(item.status || 'active').trim().toLowerCase();
    return item;
  }

  function getSpec(id) {
    const key = String(id || '').trim();
    if (CORE_WORKFLOW_FEATURE_SPECS[key]) return normalizeSpec(CORE_WORKFLOW_FEATURE_SPECS[key]);
    if (extensionSpecs.has(key)) return cloneSpec(extensionSpecs.get(key));
    return null;
  }

  function listCoreSpecs() {
    return Object.keys(CORE_WORKFLOW_FEATURE_SPECS).sort().map(getSpec);
  }

  function listExtensionSpecs() {
    return Array.from(extensionSpecs.keys()).sort().map(key => cloneSpec(extensionSpecs.get(key)));
  }

  function listSpecs() {
    return listCoreSpecs().concat(listExtensionSpecs());
  }

  function isKnownRegistryFeature(feature, family) {
    const registry = window.NeoGenerationFeatureAvailability;
    if (!registry || typeof registry.getFamilyFeatures !== 'function') return false;
    const features = registry.getFamilyFeatures(family);
    return Object.prototype.hasOwnProperty.call(features || {}, String(feature || '').trim());
  }

  function validateSpec(spec) {
    const item = normalizeSpec(spec);
    const issues = [];
    REQUIRED_FIELDS.forEach(field => {
      const value = item[field];
      if (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)) {
        issues.push(`Missing required field: ${field}`);
      }
    });
    if (item.source === 'core' && item.id && item.feature_key && item.id !== item.feature_key) {
      issues.push('id and feature_key should match unless there is a documented alias.');
    }
    if (item.families.some(family => normalizeFamily(family) !== family)) {
      issues.push('families should use canonical family ids from NeoGenerationFeatureAvailability.');
    }
    if (item.blocked_families.some(family => normalizeFamily(family) !== family)) {
      issues.push('blocked_families should use canonical family ids from NeoGenerationFeatureAvailability.');
    }
    if (item.payload_key && item.payload_key.includes(' ')) issues.push('payload_key must not contain spaces.');
    if (item.module_payload_key && !item.module_payload_key.startsWith('modules.')) {
      issues.push('module_payload_key should use modules.<feature_key> format.');
    }
    if (item.source === 'core' && item.ui_card && !String(item.ui_card).startsWith('generation-')) {
      issues.push('core ui_card should use a stable generation-* id.');
    }
    if (item.source === 'extension' && !item.extension_id) {
      issues.push('extension workflow specs require extension_id.');
    }
    if (item.status && !['active', 'candidate', 'blocked', 'deprecated'].includes(item.status)) {
      issues.push(`Invalid status: ${item.status}`);
    }
    return { id: item.id, source: item.source, extension_id: item.extension_id, valid: issues.length === 0, issues };
  }

  function validateRegistry() {
    const specs = listSpecs();
    const seen = new Set();
    const reports = specs.map(validateSpec);
    specs.forEach(spec => {
      if (!spec.id) return;
      if (seen.has(spec.id)) reports.push({ id: spec.id, valid: false, issues: ['Duplicate workflow feature id.'] });
      seen.add(spec.id);
    });
    const issues = reports.filter(report => !report.valid);
    return { valid: issues.length === 0, total: specs.length, issue_count: issues.length, reports, issues };
  }

  function isAllowed(id, family) {
    const spec = getSpec(id);
    if (!spec || spec.status === 'blocked' || spec.status === 'deprecated') return false;
    const normalizedFamily = normalizeFamily(family);
    if (spec.blocked_families.includes(normalizedFamily)) return false;
    if (!spec.families.includes(normalizedFamily)) return false;
    const registry = window.NeoGenerationFeatureAvailability;
    if (registry && typeof registry.isFeatureAllowed === 'function' && isKnownRegistryFeature(spec.feature_key || spec.id, normalizedFamily)) {
      return registry.isFeatureAllowed(spec.feature_key || spec.id, normalizedFamily);
    }
    return true;
  }

  function setNestedDisabled(payload, dottedKey) {
    if (!payload || !dottedKey) return;
    const parts = String(dottedKey).split('.').filter(Boolean);
    let cursor = payload;
    while (parts.length > 1) {
      const part = parts.shift();
      if (!cursor[part] || typeof cursor[part] !== 'object') cursor[part] = {};
      cursor = cursor[part];
    }
    cursor[parts[0]] = Object.assign({}, cursor[parts[0]] || {}, { enabled: false, preset: 'off' });
  }

  function sanitizePayload(payload, family) {
    const out = payload && typeof payload === 'object' ? payload : {};
    listSpecs().forEach(spec => {
      if (isAllowed(spec.id, family)) return;
      if (spec.payload_key) setNestedDisabled(out, spec.payload_key);
      if (spec.module_payload_key) setNestedDisabled(out, spec.module_payload_key);
    });
    return out;
  }

  function workflowPackToSpec(pack) {
    const extensionId = String(pack?.extension_id || pack?.extension || '').trim();
    const workflowId = String(pack?.workflow_id || pack?.id || '').trim();
    if (!extensionId || !workflowId) return null;
    const allowedFamilies = Array.isArray(pack.allowed_families) && pack.allowed_families.length ? pack.allowed_families : pack.families;
    const familyList = Array.isArray(allowedFamilies) && allowedFamilies.length ? allowedFamilies : (pack.family ? [pack.family] : []);
    return normalizeSpec({
      id: workflowId,
      workflow_id: workflowId,
      extension_id: extensionId,
      title: pack.title || workflowId,
      families: familyList,
      blocked_families: pack.blocked_families || pack.disabled_families || [],
      feature_key: pack.feature_key || workflowId,
      requires_nodes: pack.requires_nodes || pack.required_nodes || [],
      optional_nodes: pack.optional_nodes || [],
      payload_key: pack.payload_key || '',
      module_payload_key: pack.module_payload_key || '',
      ui_card: pack.ui_card || '',
      owner_module: pack.owner_module || `extension:${extensionId}`,
      host_tabs: pack.host_tabs || pack.sections || [pack.target_tab || pack.surface || 'generation'],
      status: pack.enabled === false ? 'blocked' : 'active',
      notes: pack.description || '',
      source: 'extension',
      workflow_path: pack.workflow_path || '',
      workflow_kind: pack.workflow_kind || '',
      backend_role: pack.backend_role || '',
    });
  }

  function registerSpec(rawSpec) {
    const spec = normalizeSpec(rawSpec);
    if (!spec.id) return { ok: false, error: 'missing_id' };
    if (CORE_WORKFLOW_FEATURE_SPECS[spec.id] && spec.source !== 'core') {
      return { ok: false, error: 'reserved_core_id', id: spec.id };
    }
    const report = validateSpec(spec);
    if (!report.valid) return { ok: false, error: 'invalid_spec', report };
    extensionSpecs.set(spec.id, Object.freeze(spec));
    emit('neo-generation-workflow-spec-registered', { spec });
    return { ok: true, spec };
  }

  function registerExtensionWorkflowPacks(packs) {
    const results = [];
    (Array.isArray(packs) ? packs : []).forEach(pack => {
      const spec = workflowPackToSpec(pack);
      if (!spec) {
        results.push({ ok: false, error: 'invalid_pack', pack });
        return;
      }
      results.push(registerSpec(spec));
    });
    emit('neo-generation-extension-workflow-packs-registered', { count: results.filter(item => item.ok).length, results });
    return results;
  }

  function clearExtensionSpecs(extensionId) {
    const target = String(extensionId || '').trim();
    Array.from(extensionSpecs.entries()).forEach(([id, spec]) => {
      if (!target || spec.extension_id === target) extensionSpecs.delete(id);
    });
    emit('neo-generation-extension-workflow-specs-cleared', { extension_id: target });
  }

  let report = validateRegistry();
  if (!report.valid) {
    console.warn('[Neo Node Workflow Intake Guard] Registry issues detected:', report.issues);
  }

  window.NeoGenerationNodeWorkflowIntakeGuard = Object.freeze({
    specs: CORE_WORKFLOW_FEATURE_SPECS,
    getSpec,
    listSpecs,
    listCoreSpecs,
    listExtensionSpecs,
    validateSpec,
    validateRegistry,
    isAllowed,
    sanitizePayload,
    workflowPackToSpec,
    registerSpec,
    registerExtensionWorkflowPacks,
    clearExtensionSpecs,
    getLastReport: () => report,
    refreshReport: () => (report = validateRegistry()),
  });
})();
