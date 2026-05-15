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
    const validation = asObject(storeEntry.validation);
    const warnings = asArray(validation.warnings);
    const errors = asArray(validation.errors);
    const dirty = !!storeEntry.dirty;
    const status = dirty ? 'dirty' : text(validation.status || 'idle');
    const sections = asArray(schema.sections);
    const card = document.createElement('div');
    card.className = 'card-lite neo-extension-schema-card';
    card.dataset.neoExternalExtensionPanel = extensionId;
    card.style.marginTop = '12px';
    const header = `
      <div class="row-between" style="gap:12px; align-items:flex-start; flex-wrap:wrap;">
        <div>
          <div class="accordion-title">${escapeHtml(schema.title || record.name || extensionId)}</div>
          <div class="muted small">${escapeHtml(extensionId)} · schema-rendered external panel</div>
        </div>
        <span class="badge" data-neo-ext-state-badge="${escapeHtml(extensionId)}">${escapeHtml(status || 'idle')}</span>
      </div>
      ${errors.length ? `<div class="status warn" style="margin-top:8px;">Blocked: ${escapeHtml(errors[0])}</div>` : ''}
      ${warnings.length ? `<div class="status warn" style="margin-top:8px;">Warning: ${escapeHtml(warnings[0])}</div>` : ''}
      ${dirty ? '<div class="mini-note" style="margin-top:8px;">Settings changed. Validation must refresh before run.</div>' : ''}`;
    const body = sections.map(section => {
      const sec = asObject(section);
      const controls = asArray(sec.controls).map(control => `<div class="neo-extension-schema-control" style="margin-top:10px;">${renderInput(control, extensionId, rawState)}</div>`).join('');
      return `<section class="neo-extension-schema-section" data-neo-ext-section="${escapeHtml(sec.id || '')}" style="margin-top:12px;">
        ${sec.title ? `<div class="stat-title">${escapeHtml(sec.title)}</div>` : ''}
        ${sec.description ? `<div class="muted small" style="margin-top:4px;">${escapeHtml(sec.description)}</div>` : ''}
        ${controls || '<div class="mini-note" style="margin-top:8px;">No controls declared in this schema section.</div>'}
      </section>`;
    }).join('');
    card.innerHTML = header + body;
    bindControls(card, extensionId);
    mountEl.appendChild(card);
    mountEl.dataset.neoSlotEmpty = 'false';
    return card;
  }

  window.NeoExtensionUiSchemaRenderer = { render, SUPPORTED_CONTROL_TYPES: Array.from(SUPPORTED_CONTROL_TYPES) };
})();
