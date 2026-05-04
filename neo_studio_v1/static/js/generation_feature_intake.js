(function () {
  const blueprint = window.NeoGenerationSectionBlueprint || {};
  const allowedStateTypes = Array.isArray(blueprint.state_types) ? blueprint.state_types : ['toggle', 'selection', 'hybrid'];
  const allowedLazyInit = Array.isArray(blueprint.lazy_init_values) ? blueprint.lazy_init_values : ['eager', 'on_open'];
  const allowedSnapshotScopes = Array.isArray(blueprint.snapshot_scope_values) ? blueprint.snapshot_scope_values : ['full', 'partial', 'none'];
  const allowedPresetSupport = Array.isArray(blueprint.preset_support_values) ? blueprint.preset_support_values : ['full', 'partial', 'none'];
  const allowedSecondaryBadges = Array.isArray(blueprint.secondary_badges) ? blueprint.secondary_badges : ['count', 'mode', 'single_name', 'custom'];
  const requiredFields = Array.isArray(blueprint.required_intake_fields)
    ? blueprint.required_intake_fields
    : ['id', 'title', 'hint', 'state_type', 'lazy_init', 'snapshot_scope', 'preset_support', 'owner_module', 'selectors', 'guidance_key', 'supports_default_preset', 'needs_dependency_audit'];

  const FEATURE_TEMPLATE = Object.freeze({
    id: 'generation-new-section',
    title: 'New section',
    hint: 'One-line summary of what this section controls.',
    state_type: 'toggle',
    lazy_init: 'on_open',
    snapshot_scope: 'full',
    preset_support: 'full',
    supports_default_preset: true,
    needs_dependency_audit: false,
    dependency_keys: [],
    owner_module: 'static/js/app.js',
    selectors: ['#new-section-root'],
    guidance_key: 'generation.new_section',
    status_pattern: { primary: 'toggle', secondary: 'custom' },
    lazy_init_handler: '',
    owner_surface: 'generation',
    level: 'advanced',
    management_mode: 'quick_use',
    cost_level: 'light',
    goal_categories: ['create_from_scratch'],
    host_tab: 'tools',
    visibility_mode: 'secondary',
    notes: '',
  });

  function validateSectionSpec(spec) {
    const section = spec || {};
    const issues = [];

    requiredFields.forEach(field => {
      const value = section[field];
      const missing = value === undefined || value === null || (typeof value === 'string' && !String(value).trim());
      if (missing) issues.push(`Missing required field: ${field}`);
    });

    if (section.id && !String(section.id).startsWith('generation-')) issues.push('Section id should start with "generation-" for consistency.');
    if (section.state_type && !allowedStateTypes.includes(section.state_type)) issues.push(`Invalid state_type: ${section.state_type}`);
    if (section.lazy_init && !allowedLazyInit.includes(section.lazy_init)) issues.push(`Invalid lazy_init: ${section.lazy_init}`);
    if (section.snapshot_scope && !allowedSnapshotScopes.includes(section.snapshot_scope)) issues.push(`Invalid snapshot_scope: ${section.snapshot_scope}`);
    if (section.preset_support && !allowedPresetSupport.includes(section.preset_support)) issues.push(`Invalid preset_support: ${section.preset_support}`);
    if (section.selectors && (!Array.isArray(section.selectors) || !section.selectors.length)) issues.push('selectors must be a non-empty array.');
    if (Array.isArray(section.selectors) && section.selectors.some(selector => !String(selector || '').trim().startsWith('#'))) issues.push('selectors should use stable id-based selectors when possible.');
    if (section.status_pattern?.secondary && !allowedSecondaryBadges.includes(section.status_pattern.secondary)) issues.push(`Invalid secondary badge type: ${section.status_pattern.secondary}`);
    if (section.needs_dependency_audit && !Array.isArray(section.dependency_keys)) issues.push('dependency_keys must be an array when needs_dependency_audit is true.');
    if (section.needs_dependency_audit && Array.isArray(section.dependency_keys) && !section.dependency_keys.length) issues.push('dependency_keys should list at least one audit key when needs_dependency_audit is true.');
    if (section.snapshot_scope === 'none' && section.supports_default_preset) issues.push('supports_default_preset should be false when snapshot_scope is none.');
    if (section.preset_support === 'none' && section.supports_default_preset) issues.push('supports_default_preset should be false when preset_support is none.');
    if (section.lazy_init === 'on_open' && !String(section.lazy_init_handler || '').trim()) issues.push('lazy_init_handler is recommended when lazy_init is on_open.');
    return {
      id: String(section.id || ''),
      valid: issues.length === 0,
      issues,
    };
  }

  function validateRegistry(registry) {
    const list = Array.isArray(registry) ? registry : [];
    const seen = new Set();
    const reports = list.map(validateSectionSpec);
    list.forEach(spec => {
      const key = String(spec?.id || '');
      if (!key) return;
      if (seen.has(key)) reports.push({ id: key, valid: false, issues: ['Duplicate section id detected.'] });
      seen.add(key);
    });
    const issues = reports.filter(report => !report.valid);
    return {
      valid: issues.length === 0,
      total: list.length,
      issue_count: issues.length,
      reports,
      issues,
    };
  }

  function buildFeatureIntakeChecklist(specOrId) {
    const spec = typeof specOrId === 'string'
      ? (window.getNeoGenerationSectionSpec?.(specOrId) || null)
      : specOrId;
    if (!spec) return null;
    return {
      id: spec.id,
      title: spec.title,
      checklist: [
        { label: 'Section host', value: spec.id || '—' },
        { label: 'State type', value: spec.state_type || '—' },
        { label: 'Header badge pattern', value: `${spec.status_pattern?.primary || 'custom'} / ${spec.status_pattern?.secondary || 'custom'}` },
        { label: 'Snapshot support', value: spec.snapshot_scope || '—' },
        { label: 'Default preset support', value: spec.supports_default_preset ? 'Yes' : 'No' },
        { label: 'Dependency audit', value: spec.needs_dependency_audit ? `Yes (${(spec.dependency_keys || []).join(', ') || 'keys pending'})` : 'No' },
        { label: 'Guidance source', value: spec.guidance_key || '—' },
        { label: 'Lazy init', value: spec.lazy_init === 'on_open' ? `On open (${spec.lazy_init_handler || 'handler pending'})` : 'Eager' },
        { label: 'Owner module', value: spec.owner_module || '—' },
        { label: 'Level / mode', value: `${spec.level || '—'} / ${spec.management_mode || '—'}` },
        { label: 'Host tab / cost', value: `${spec.host_tab || '—'} / ${spec.cost_level || '—'}` },
      ],
    };
  }

  function logRegistryIssues(report) {
    if (!report || report.valid) return;
    const lines = [];
    report.issues.forEach(issue => {
      lines.push(`${issue.id || 'unknown'}: ${issue.issues.join(' | ')}`);
    });
    console.warn('[Neo Generation Feature Intake] Registry issues detected:\n' + lines.join('\n'));
  }

  const initialReport = validateRegistry(window.NeoGenerationSectionRegistry || []);
  logRegistryIssues(initialReport);

  window.NeoGenerationFeatureIntake = Object.freeze({
    template: FEATURE_TEMPLATE,
    validateSpec: validateSectionSpec,
    validateRegistry,
    buildChecklist: buildFeatureIntakeChecklist,
    getLastReport: () => initialReport,
  });
})();
