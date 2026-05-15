(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[ch]));
  const pretty = value => JSON.stringify(value, null, 2);
  const setStatus = (id, text, tone = '') => { const node = $(id); if (node) { node.textContent = text || ''; node.dataset.tone = tone || ''; } };
  const statCard = (label, value) => `<div class="card-lite"><div class="mini-note">${esc(label)}</div><strong>${esc(value)}</strong></div>`;

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || data.message || `Request failed: ${response.status}`);
    return data;
  }

  function renderValidationResult(data) {
    const summary = data.summary || {};
    if ($('assistant-phase13-validation-stats')) {
      $('assistant-phase13-validation-stats').innerHTML = [
        statCard('Passed', summary.passed ?? 0),
        statCard('Failed', summary.failed ?? 0),
        statCard('Critical failed', summary.critical_failed ?? 0),
      ].join('');
    }
    const list = $('assistant-phase13-validation-results');
    if (list) {
      const items = data.results || [];
      list.innerHTML = items.length ? items.map(item => {
        const ok = item.status === 'pass';
        return `<div class="card-lite"><div class="row-between"><strong>${esc(item.label || item.id)}</strong><span class="badge">${esc(item.status || '')} · ${esc(item.severity || '')}</span></div><div class="mini-note" style="margin-top:8px; white-space:pre-wrap;">${esc(item.message || JSON.stringify(item.details || {}, null, 2).slice(0, 700))}</div></div>`;
      }).join('') : '<div class="empty-state">No validation run loaded yet.</div>';
    }
    if ($('assistant-phase13-validation-output')) $('assistant-phase13-validation-output').textContent = pretty(data);
  }

  async function runValidation() {
    setStatus('assistant-phase13-validation-status', 'Running Assistant validation suite...', '');
    const data = await fetchJson('/api/assistant/validation/run', { method: 'POST', body: JSON.stringify({ include_optional: true }) });
    renderValidationResult(data);
    setStatus('assistant-phase13-validation-status', data.ok ? 'Validation passed.' : 'Validation finished with failures.', data.ok ? 'ok' : 'warn');
  }

  async function loadValidationLogs() {
    setStatus('assistant-phase13-validation-status', 'Loading validation logs...', '');
    const data = await fetchJson('/api/assistant/validation/status?limit=8');
    const latest = (data.items || []).slice(-1)[0];
    if (latest) renderValidationResult(latest);
    if ($('assistant-phase13-validation-output')) $('assistant-phase13-validation-output').textContent = pretty(data);
    setStatus('assistant-phase13-validation-status', `${data.count || 0} validation log record(s) loaded.`, 'ok');
  }

  async function loadEventLogs() {
    setStatus('assistant-phase13-log-status', 'Loading Assistant event logs...', '');
    const kind = $('assistant-phase13-log-kind')?.value || 'events';
    const data = await fetchJson(`/api/assistant/logs?kind=${encodeURIComponent(kind)}&limit=40`);
    const list = $('assistant-phase13-log-list');
    if (list) {
      const items = data.items || [];
      list.innerHTML = items.length ? items.reverse().map(item => `<div class="card-lite"><div class="row-between"><strong>${esc(item.event_type || (item.summary ? 'validation_suite_run' : 'log'))}</strong><span class="badge">${esc(item.status || (item.ok ? 'pass' : ''))} · ${esc(item.logged_at || item.finished_at || '')}</span></div><div class="mini-note" style="margin-top:8px; white-space:pre-wrap;">${esc(JSON.stringify(item.details || item.summary || item, null, 2).slice(0, 900))}</div></div>`).join('') : '<div class="empty-state">No Assistant logs yet.</div>';
    }
    setStatus('assistant-phase13-log-status', `${data.count || 0} log item(s) loaded.`, 'ok');
  }

  async function writeManualLog() {
    const note = ($('assistant-phase13-manual-log')?.value || '').trim();
    if (!note) throw new Error('Write a short log note first.');
    const data = await fetchJson('/api/assistant/log-event', { method: 'POST', body: JSON.stringify({ event_type: 'manual_validation_note', source: 'phase13_ui', status: 'info', details: { note } }) });
    $('assistant-phase13-manual-log').value = '';
    setStatus('assistant-phase13-log-status', 'Manual Assistant log saved.', 'ok');
    await loadEventLogs();
  }

  function bind(id, fn, statusId) {
    const node = $(id);
    if (!node) return;
    node.addEventListener('click', async () => {
      try { await fn(); } catch (err) { setStatus(statusId || 'assistant-phase13-validation-status', err.message || String(err), 'error'); }
    });
  }

  function init() {
    bind('btn-assistant-phase13-run-validation', runValidation, 'assistant-phase13-validation-status');
    bind('btn-assistant-phase13-load-validation', loadValidationLogs, 'assistant-phase13-validation-status');
    bind('btn-assistant-phase13-load-logs', loadEventLogs, 'assistant-phase13-log-status');
    bind('btn-assistant-phase13-write-log', writeManualLog, 'assistant-phase13-log-status');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
