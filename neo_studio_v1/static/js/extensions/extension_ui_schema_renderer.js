(function () {
  'use strict';

  const SUPPORTED_CONTROL_TYPES = new Set([
    'toggle', 'select', 'text', 'number', 'slider', 'checkbox', 'radio', 'textarea',
    'button', 'action', 'info', 'warning', 'source_selector', 'target_selector', 'output_policy_selector'
  ]);

  function asArray(value) { return Array.isArray(value) ? value.slice() : []; }
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function text(value) { return String(value == null ? '' : value).trim(); }
  function safeId(value) { return text(value).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'control'; }
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }



  const SHELL_CONTRACT_VERSION = 'external-extension-ui-contract-v1';
  const DEFAULT_SHELL = Object.freeze({
    version: SHELL_CONTRACT_VERSION,
    shell: 'standard_collapsible',
    default_expanded: false,
    show_status_chips: true,
    show_target: true,
    show_output_policy: true,
    show_validation: true,
    show_payload_details: false,
  });

  function bool(value, fallback) {
    if (value === true || value === 'true' || value === 1 || value === '1') return true;
    if (value === false || value === 'false' || value === 0 || value === '0') return false;
    return !!fallback;
  }

  function firstText() {
    for (let i = 0; i < arguments.length; i += 1) {
      const value = arguments[i];
      if (Array.isArray(value)) {
        const hit = value.map(text).find(Boolean);
        if (hit) return hit;
      } else {
        const hit = text(value);
        if (hit) return hit;
      }
    }
    return '';
  }

  function normalizeUiContract(record, schema) {
    const rawManifest = asObject(record.raw_manifest);
    const ui = Object.assign({}, DEFAULT_SHELL, asObject(rawManifest.ui), asObject(record.ui), asObject(schema.ui));
    ui.version = text(ui.version || ui.contract || DEFAULT_SHELL.version) || DEFAULT_SHELL.version;
    ui.shell = text(ui.shell || DEFAULT_SHELL.shell) || DEFAULT_SHELL.shell;
    ui.default_expanded = bool(ui.default_expanded, DEFAULT_SHELL.default_expanded);
    ui.show_status_chips = bool(ui.show_status_chips, DEFAULT_SHELL.show_status_chips);
    ui.show_target = bool(ui.show_target, DEFAULT_SHELL.show_target);
    ui.show_output_policy = bool(ui.show_output_policy, DEFAULT_SHELL.show_output_policy);
    ui.show_validation = bool(ui.show_validation, DEFAULT_SHELL.show_validation);
    ui.show_payload_details = bool(ui.show_payload_details, DEFAULT_SHELL.show_payload_details);
    return ui;
  }

  function readCollapsed(extensionId, ui) {
    const key = `neo:extension-shell:${extensionId}:collapsed`;
    try {
      const stored = window.localStorage ? window.localStorage.getItem(key) : null;
      if (stored === 'true') return true;
      if (stored === 'false') return false;
    } catch (_) {}
    return !ui.default_expanded;
  }

  function writeCollapsed(extensionId, collapsed) {
    try {
      if (window.localStorage) window.localStorage.setItem(`neo:extension-shell:${extensionId}:collapsed`, collapsed ? 'true' : 'false');
    } catch (_) {}
  }

  function chip(label, value, tone) {
    const safeLabel = escapeHtml(label || '');
    const safeValue = escapeHtml(value || '');
    const cls = `neo-extension-shell-chip${tone ? ' neo-extension-shell-chip--' + escapeHtml(tone) : ''}`;
    return `<span class="${cls}">${safeLabel}${safeValue ? `: <strong>${safeValue}</strong>` : ''}</span>`;
  }

  function normalizeShellState(record, schema, storeEntry, rawState) {
    const validation = asObject(storeEntry.validation);
    const effective = asObject(storeEntry.effective_state);
    const recordWorkflow = asObject(record.workflow);
    const recordOutput = asObject(record.output);
    const recordVisibility = asObject(record.output_visibility);
    const workflowPatch = asObject(effective.workflow_patch || rawState.workflow_patch || record.workflow_patch);
    const warnings = asArray(validation.warnings).concat(asArray(effective.warnings)).filter(Boolean);
    const errors = asArray(validation.errors).concat(asArray(effective.errors)).filter(Boolean);
    const disabledReason = firstText(validation.disabled_reason, effective.disabled_reason, record.disabled_reason, errors[0]);
    const enabled = !!storeEntry.enabled || !!rawState.enabled || !!record.enabled;
    const dirty = !!storeEntry.dirty;
    const validationStatus = dirty ? 'dirty' : firstText(validation.status, effective.validation_status, enabled ? 'ready' : 'idle');
    const target = firstText(effective.target, effective.workflow_target, rawState.target, rawState.workflow_target, schema.target, recordWorkflow.target, record.target, record.supported_workflows, record.target_sections);
    const outputPolicy = firstText(effective.output_policy, rawState.output_policy, schema.output_policy, recordOutput.default_policy, recordOutput.policy, record.output_policy_default, record.output_policy);
    const workflowMode = firstText(effective.workflow_mode, workflowPatch.mode, rawState.workflow_mode, schema.workflow_mode, recordWorkflow.mode, recordWorkflow.default_mode, record.workflow_mode);
    const primaryOutput = firstText(effective.primary_output_type, effective.primary_type, rawState.primary_output_type, schema.primary_output_type, recordOutput.primary_output_type, recordOutput.primary_type, record.primary_output_type);
    const batchPolicy = firstText(effective.batch_policy, rawState.batch_policy, schema.batch_policy, recordOutput.batch_policy, record.batch_policy);
    return { enabled, dirty, validationStatus, warnings, errors, disabledReason, target, outputPolicy, workflowMode, primaryOutput, batchPolicy, effective, outputVisibility: recordVisibility };
  }

  function renderShellChips(shell, ui) {
    const chips = [];
    if (ui.show_status_chips) {
      chips.push(chip(shell.enabled ? 'Enabled' : 'Disabled', '', shell.enabled ? 'good' : 'muted'));
      chips.push(chip('State', shell.validationStatus || 'idle', shell.errors.length || shell.disabledReason ? 'bad' : (shell.warnings.length ? 'warn' : 'good')));
    }
    const visibility = asObject(shell.outputVisibility);
    if (ui.show_target && visibility.target_visible !== false && shell.target) chips.push(chip('Target', shell.target, 'neutral'));
    if (ui.show_output_policy && visibility.output_policy_visible !== false && shell.outputPolicy) chips.push(chip('Output', shell.outputPolicy, 'neutral'));
    if (visibility.workflow_mode_visible !== false && shell.workflowMode) chips.push(chip('Workflow', shell.workflowMode, shell.workflowMode === 'replace_workflow' ? 'warn' : 'neutral'));
    if (visibility.primary_output_visible !== false && shell.primaryOutput) chips.push(chip('Primary', shell.primaryOutput, 'neutral'));
    if (visibility.batch_policy_visible !== false && shell.batchPolicy) chips.push(chip('Batch', shell.batchPolicy, shell.batchPolicy === 'force_1' ? 'warn' : 'neutral'));
    return chips.join('');
  }

  function bindShell(card, extensionId) {
    const button = card.querySelector('[data-neo-ext-shell-toggle]');
    const body = card.querySelector('[data-neo-ext-shell-body]');
    if (!button || !body) return;
    button.addEventListener('click', () => {
      const collapsed = card.getAttribute('data-neo-ext-shell-collapsed') !== 'true';
      card.setAttribute('data-neo-ext-shell-collapsed', collapsed ? 'true' : 'false');
      button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      body.hidden = collapsed;
      writeCollapsed(extensionId, collapsed);
    });
  }


  function normalizeOptions(control, fallback = []) {
    const options = control.options || fallback;
    return asArray(options).map(option => {
      if (option && typeof option === 'object') {
        return { value: text(option.value), label: text(option.label || option.value) };
      }
      return { value: text(option), label: text(option) };
    }).filter(item => item.value);
  }

  function getStoreEntry(extensionId) {
    const store = window.NeoExtensionStateStore;
    return store && typeof store.getExtension === 'function' ? store.getExtension(extensionId) : null;
  }

  function getStoreRaw(extensionId) {
    const item = getStoreEntry(extensionId);
    return asObject(item && item.raw_state);
  }

  function update(extensionId, key, value) {
    if (!key) return;
    const store = window.NeoExtensionStateStore;
    if (store) {
      if (key === 'enabled' && typeof store.setEnabled === 'function') store.setEnabled(extensionId, !!value);
      else if (typeof store.setRaw === 'function') store.setRaw(extensionId, key, value);
    }
    window.dispatchEvent(new CustomEvent('neo:external-extension-ui-control-changed', {
      detail: { extension_id: extensionId, key, value }
    }));
  }

  function renderInput(control, extensionId, rawState) {
    const c = asObject(control);
    const key = text(c.key);
    const type = text(c.type || 'text').toLowerCase();
    const id = `neo-ext-${safeId(extensionId)}-${safeId(key || type)}`;
    const label = escapeHtml(c.label || key || type);
    const value = rawState[key] != null ? rawState[key] : c.default;
    const help = c.help ? `<div class="muted small" style="margin-top:4px;">${escapeHtml(c.help)}</div>` : '';
    const disabled = c.disabled ? 'disabled' : '';

    if (!SUPPORTED_CONTROL_TYPES.has(type)) {
      return `<div class="status warn" data-neo-ext-control-unsupported="${escapeHtml(type)}">Unsupported control type: ${escapeHtml(type)}</div>`;
    }
    if (type === 'info' || type === 'warning') {
      const cls = type === 'warning' ? 'status warn' : 'mini-note';
      return `<div class="${cls}" data-neo-ext-control="${escapeHtml(key || type)}">${escapeHtml(c.text || c.label || '')}</div>`;
    }
    if (type === 'toggle' || type === 'checkbox') {
      const checked = value === true || value === 'true' || value === 1 || value === '1' ? 'checked' : '';
      return `<label class="mini-note" style="display:flex; gap:8px; align-items:center; cursor:pointer;">
        <input id="${escapeHtml(id)}" type="checkbox" data-neo-ext-control-key="${escapeHtml(key)}" ${checked} ${disabled}>
        <span>${label}</span>
      </label>${help}`;
    }
    if (type === 'select' || type === 'source_selector' || type === 'target_selector' || type === 'output_policy_selector') {
      let fallback = [];
      if (type === 'output_policy_selector') fallback = ['preview', 'new_run', 'append', 'replace'];
      if (type === 'source_selector') fallback = ['none', 'prompt', 'selected_image', 'upload', 'output'];
      if (type === 'target_selector') fallback = ['base_generation', 'build', 'prompt_stack', 'reference', 'finish', 'assets', 'output', 'preview'];
      const options = normalizeOptions(c, fallback);
      const opts = options.map(option => `<option value="${escapeHtml(option.value)}" ${String(value || '') === option.value ? 'selected' : ''}>${escapeHtml(option.label)}</option>`).join('');
      return `<label for="${escapeHtml(id)}">${label}</label><select id="${escapeHtml(id)}" data-neo-ext-control-key="${escapeHtml(key)}" ${disabled}>${opts}</select>${help}`;
    }
    if (type === 'radio') {
      const options = normalizeOptions(c);
      return `<fieldset class="mini-note" style="border:0; padding:10px; margin:0;"><legend>${label}</legend>${options.map(option => `<label style="display:inline-flex; gap:6px; align-items:center; margin-right:12px;"><input type="radio" name="${escapeHtml(id)}" value="${escapeHtml(option.value)}" data-neo-ext-control-key="${escapeHtml(key)}" ${String(value || '') === option.value ? 'checked' : ''} ${disabled}> ${escapeHtml(option.label)}</label>`).join('')}</fieldset>${help}`;
    }
    if (type === 'textarea') {
      return `<label for="${escapeHtml(id)}">${label}</label><textarea id="${escapeHtml(id)}" rows="${Number(c.rows || 3)}" data-neo-ext-control-key="${escapeHtml(key)}" ${disabled}>${escapeHtml(value || '')}</textarea>${help}`;
    }
    if (type === 'number' || type === 'slider') {
      const inputType = type === 'slider' ? 'range' : 'number';
      const attrs = ['min', 'max', 'step'].map(attr => c[attr] != null ? `${attr}="${escapeHtml(c[attr])}"` : '').join(' ');
      return `<label for="${escapeHtml(id)}">${label}</label><input id="${escapeHtml(id)}" type="${inputType}" value="${escapeHtml(value == null ? '' : value)}" data-neo-ext-control-key="${escapeHtml(key)}" ${attrs} ${disabled}>${help}`;
    }
    if (type === 'button' || type === 'action') {
      return `<button class="btn" type="button" data-neo-ext-action="${escapeHtml(c.action || key)}" data-neo-ext-control-key="${escapeHtml(key)}" ${disabled}>${label}</button>${help}`;
    }
    return `<label for="${escapeHtml(id)}">${label}</label><input id="${escapeHtml(id)}" type="text" value="${escapeHtml(value || '')}" data-neo-ext-control-key="${escapeHtml(key)}" ${disabled}>${help}`;
  }

  function bindControls(card, extensionId) {
    card.querySelectorAll('[data-neo-ext-control-key]').forEach(control => {
      const key = control.getAttribute('data-neo-ext-control-key');
      if (!key) return;
      const eventName = control.tagName === 'SELECT' || control.type === 'checkbox' || control.type === 'radio' ? 'change' : 'input';
      control.addEventListener(eventName, () => {
        let value;
        if (control.type === 'checkbox') value = !!control.checked;
        else if (control.type === 'radio') {
          if (!control.checked) return;
          value = control.value;
        } else value = control.value;
        update(extensionId, key, value);
      });
    });
    card.querySelectorAll('[data-neo-ext-action]').forEach(button => {
      button.addEventListener('click', () => {
        window.dispatchEvent(new CustomEvent('neo:external-extension-ui-action', {
          detail: { extension_id: extensionId, action: button.getAttribute('data-neo-ext-action') || '', key: button.getAttribute('data-neo-ext-control-key') || '' }
        }));
      });
    });
  }

  function render(extensionRecord, mountEl) {
    const record = asObject(extensionRecord);
    const schema = asObject(record.ui_schema);
    const extensionId = text(record.extension_id || record.id);
    if (!extensionId || !mountEl || !schema.sections) return null;
    const storeEntry = getStoreEntry(extensionId) || {};
    const rawState = getStoreRaw(extensionId);
    if (rawState.enabled == null) rawState.enabled = !!storeEntry.enabled;
    const ui = normalizeUiContract(record, schema);
    const shell = normalizeShellState(record, schema, storeEntry, rawState);
    const sections = asArray(schema.sections);
    const collapsed = ui.shell === 'standard_collapsible' ? readCollapsed(extensionId, ui) : false;
    const card = document.createElement('div');
    card.className = `card-lite neo-extension-schema-card neo-extension-shell neo-extension-shell--${safeId(ui.shell)}`;
    card.dataset.neoExternalExtensionPanel = extensionId;
    card.dataset.neoExtensionUiContract = ui.version;
    card.dataset.neoExtensionUiShell = ui.shell;
    card.dataset.neoExtShellCollapsed = collapsed ? 'true' : 'false';
    card.style.marginTop = '12px';

    const title = escapeHtml(schema.title || record.name || extensionId);
    const subtitle = escapeHtml(extensionId);
    const chips = renderShellChips(shell, ui);
    const notices = [
      shell.disabledReason ? `<div class="status warn neo-extension-shell-notice" data-neo-ext-disabled-reason="${escapeHtml(extensionId)}">Disabled: ${escapeHtml(shell.disabledReason)}</div>` : '',
      shell.errors.length ? `<div class="status warn neo-extension-shell-notice" data-neo-ext-errors="${escapeHtml(extensionId)}">Blocked: ${escapeHtml(shell.errors[0])}</div>` : '',
      shell.warnings.length ? `<div class="status warn neo-extension-shell-notice" data-neo-ext-warnings="${escapeHtml(extensionId)}">Warning: ${escapeHtml(shell.warnings[0])}</div>` : '',
      shell.dirty ? '<div class="mini-note neo-extension-shell-notice">Settings changed. Validation must refresh before run.</div>' : '',
    ].filter(Boolean).join('');

    const body = sections.map(section => {
      const sec = asObject(section);
      const controls = asArray(sec.controls).map(control => `<div class="neo-extension-schema-control">${renderInput(control, extensionId, rawState)}</div>`).join('');
      return `<section class="neo-extension-schema-section" data-neo-ext-section="${escapeHtml(sec.id || '')}">
        ${sec.title ? `<div class="stat-title">${escapeHtml(sec.title)}</div>` : ''}
        ${sec.description ? `<div class="muted small neo-extension-schema-description">${escapeHtml(sec.description)}</div>` : ''}
        ${controls || '<div class="mini-note">No controls declared in this schema section.</div>'}
      </section>`;
    }).join('');

    const payloadDetails = ui.show_payload_details ? `<details class="neo-extension-shell-payload"><summary>Payload details</summary><pre>${escapeHtml(JSON.stringify({ raw_state: rawState, effective_state: shell.effective }, null, 2))}</pre></details>` : '';

    if (ui.shell === 'standard_collapsible') {
      card.innerHTML = `
        <div class="neo-extension-shell-header">
          <button class="neo-extension-shell-toggle" type="button" data-neo-ext-shell-toggle aria-expanded="${collapsed ? 'false' : 'true'}">
            <span class="neo-extension-shell-chevron" aria-hidden="true">▾</span>
            <span class="neo-extension-shell-title-wrap">
              <span class="neo-extension-shell-title">${title}</span>
              <span class="neo-extension-shell-subtitle">${subtitle}</span>
            </span>
          </button>
          <div class="neo-extension-shell-chips">${chips}</div>
        </div>
        ${notices ? `<div class="neo-extension-shell-notices">${notices}</div>` : ''}
        <div class="neo-extension-shell-body" data-neo-ext-shell-body ${collapsed ? 'hidden' : ''}>${body}${payloadDetails}</div>`;
    } else {
      card.innerHTML = `
        <div class="row-between" style="gap:12px; align-items:flex-start; flex-wrap:wrap;">
          <div><div class="accordion-title">${title}</div><div class="muted small">${subtitle}</div></div>
          <div class="neo-extension-shell-chips">${chips}</div>
        </div>
        ${notices}${body}${payloadDetails}`;
    }

    bindControls(card, extensionId);
    bindShell(card, extensionId);
    mountEl.appendChild(card);
    mountEl.dataset.neoSlotEmpty = 'false';
    return card;
  }


  window.NeoExtensionUiSchemaRenderer = { render, SUPPORTED_CONTROL_TYPES: Array.from(SUPPORTED_CONTROL_TYPES), DEFAULT_SHELL, SHELL_CONTRACT_VERSION };
})();
