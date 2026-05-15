(function () {
  'use strict';

  const VALIDATE_URL = '/api/extensions/validate';

  function asObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function clone(value) {
    try { return JSON.parse(JSON.stringify(value)); } catch (_) { return value; }
  }

  function applyServerValidation(data) {
    const store = window.NeoExtensionStateStore;
    if (store && typeof store.applyBulkValidation === 'function') {
      store.applyBulkValidation(data || {});
    }
    window.dispatchEvent(new CustomEvent('neo:external-extensions:server-validation', {
      detail: { data: clone(data || {}), source: 'server' },
    }));
  }

  async function validate(payload = {}) {
    const body = asObject(payload);
    try {
      const res = await fetch(VALIDATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        const message = data.error || data.message || `HTTP ${res.status}`;
        throw new Error(message);
      }
      applyServerValidation(data);
      return { ok: !!data.valid, source: 'server', data };
    } catch (err) {
      const core = window.NeoExternalExtensionState;
      const report = core && typeof core.getValidationReport === 'function'
        ? core.getValidationReport(body)
        : { ok: true, warnings: ['Server validation endpoint is not available yet. Using local preflight only.'], blocked: [] };
      return {
        ok: !!report.ok,
        source: 'local_preflight',
        data: {
          valid: !!report.ok,
          validation: clone(report),
          warnings: report.warnings || [],
          errors: report.blocked || [],
        },
        warning: `Server validation endpoint unavailable: ${err && err.message ? err.message : err}`,
      };
    }
  }

  window.NeoExtensionValidationClient = { validate };
})();
