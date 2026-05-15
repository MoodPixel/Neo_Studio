(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const trim = value => String(value || '').trim();
  const esc = value => String(value ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const pretty = value => JSON.stringify(value, null, 2);

  function setStatus(id, text, tone) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('ok', tone === 'ok');
    el.classList.toggle('warn', tone === 'warn');
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...(options || {})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.message || `Request failed (${response.status})`);
    }
    return data;
  }

  function statCard(label, value, note) {
    return `<div class="card-lite"><div class="mini-note">${esc(label)}</div><div class="stat-value" style="font-size:20px;">${esc(value)}</div>${note ? `<div class="mini-note">${esc(note)}</div>` : ''}</div>`;
  }

  function renderList(id, items, render, empty) {
    const el = $(id);
    if (!el) return;
    const arr = Array.isArray(items) ? items : [];
    el.innerHTML = arr.length ? arr.map(render).join('') : `<div class="mini-note">${esc(empty || 'No items yet.')}</div>`;
  }

  function activeSessionId() {
    return window.__neoAssistantActiveSessionId || $('assistant-session-id')?.value || '';
  }

  function activeProjectId() {
    return $('assistant-project-select')?.value || '';
  }

  function parseJsonField(id, fallback) {
    const raw = trim($(id)?.value || '');
    if (!raw) return fallback || {};
    try { return JSON.parse(raw); } catch (err) { throw new Error(`${id} must contain valid JSON.`); }
  }

  function localActionExamples(actionType) {
    if (actionType === 'launch_app') return '{"app_id":"explorer"}';
    if (actionType === 'run_command_preset') return '{"preset_id":"python.version"}';
    if (actionType === 'reveal_path') return '{"path":"F:/LLM/sd-webui-forge-neo"}';
    return '{"path":"F:/LLM/sd-webui-forge-neo"}';
  }

  async function loadLocalActions() {
    setStatus('assistant-phase12-local-catalog-status', 'Loading local action catalog...', '');
    const data = await fetchJson('/api/assistant/local-actions/catalog');
    const catalog = data.catalog || {};
    if ($('assistant-phase12-local-platform')) $('assistant-phase12-local-platform').textContent = `Platform: ${catalog.platform || 'unknown'}`;
    const actions = Array.isArray(catalog.actions) ? catalog.actions : [];
    const apps = catalog.app_presets || {};
    const commands = catalog.command_presets || {};
    const guardrails = catalog.guardrails || {};
    if ($('assistant-phase12-local-stats')) {
      $('assistant-phase12-local-stats').innerHTML = [
        statCard('Actions', actions.length, catalog.version || ''),
        statCard('App presets', Object.keys(apps).length, catalog.platform || ''),
        statCard('Command presets', Object.keys(commands).length, guardrails.medium_actions_require_confirmation ? 'confirm medium risk' : '')
      ].join('');
    }
    renderList('assistant-phase12-local-action-list', actions, action => `<button class="assistant-session-card" type="button" data-phase12-local-action="${esc(action.id)}"><div class="assistant-session-card-title">${esc(action.id)} · ${esc(action.label)}</div><div class="assistant-session-card-meta">risk: ${esc(action.risk)} · confirmation: ${esc(action.requires_confirmation)} · ${esc(action.description)}</div></button>`, 'No local actions registered.');
    renderList('assistant-phase12-local-app-presets', Object.entries(apps), ([id, app]) => `<button class="assistant-session-card" type="button" data-phase12-local-preset-type="launch_app" data-phase12-local-preset-id="${esc(id)}"><div class="assistant-session-card-title">${esc(id)} · ${esc(app.label || '')}</div><div class="assistant-session-card-meta">risk: ${esc(app.risk || 'safe')} · confirmation: ${esc(app.requires_confirmation)}</div></button>`, 'No app presets available for this OS.');
    renderList('assistant-phase12-local-command-presets', Object.entries(commands), ([id, cmd]) => `<button class="assistant-session-card" type="button" data-phase12-local-preset-type="run_command_preset" data-phase12-local-preset-id="${esc(id)}"><div class="assistant-session-card-title">${esc(id)} · ${esc(cmd.label || '')}</div><div class="assistant-session-card-meta">risk: ${esc(cmd.risk || '')} · confirmation: ${esc(cmd.requires_confirmation)} · ${esc(cmd.description || '')}</div></button>`, 'No command presets available.');
    setStatus('assistant-phase12-local-catalog-status', 'Local action catalog ready.', 'ok');
    return catalog;
  }

  async function previewLocalAction() {
    const actionType = trim($('assistant-phase12-local-action-type')?.value || '');
    const args = parseJsonField('assistant-phase12-local-args', {});
    setStatus('assistant-phase12-local-action-status', 'Previewing local action...', '');
    const data = await fetchJson('/api/assistant/local-actions/preview', { method: 'POST', body: JSON.stringify({ action_type: actionType, arguments: args }) });
    const preview = data.preview || {};
    if ($('assistant-phase12-local-risk-preview')) {
      $('assistant-phase12-local-risk-preview').value = `${preview.risk || 'unknown'}${preview.requires_confirmation ? ' · confirmation required' : ' · no confirmation required'}`;
    }
    if ($('assistant-phase12-local-output')) $('assistant-phase12-local-output').textContent = pretty(data);
    setStatus('assistant-phase12-local-action-status', 'Preview ready. Review before executing.', preview.requires_confirmation ? 'warn' : 'ok');
    return data;
  }

  async function executeLocalAction() {
    const actionType = trim($('assistant-phase12-local-action-type')?.value || '');
    const args = parseJsonField('assistant-phase12-local-args', {});
    setStatus('assistant-phase12-local-action-status', 'Executing local action...', '');
    const data = await fetchJson('/api/assistant/local-actions/execute', {
      method: 'POST',
      body: JSON.stringify({
        action_type: actionType,
        arguments: args,
        confirmed: Boolean($('assistant-phase12-local-confirmed')?.checked),
        session_id: activeSessionId(),
        project_id: activeProjectId()
      })
    });
    if ($('assistant-phase12-local-output')) $('assistant-phase12-local-output').textContent = pretty(data);
    setStatus('assistant-phase12-local-action-status', 'Local action executed.', 'ok');
    await refreshLocalHistory().catch(() => {});
    return data;
  }

  async function refreshLocalHistory() {
    setStatus('assistant-phase12-local-history-status', 'Loading local action memory...', '');
    const params = new URLSearchParams({ session_id: activeSessionId(), project_id: activeProjectId(), limit: '32' });
    const data = await fetchJson(`/api/assistant/action-memory-recent?${params.toString()}`);
    const items = (data.items || []).filter(item => String(item.document || item.summary || item.chunk_type || '').toLowerCase().includes('local'));
    renderList('assistant-phase12-local-history', items, item => `<div class="card-lite"><div class="row-between"><strong>${esc(item.chunk_type || 'local_action')}</strong><span class="badge">${esc(item.created_at || '')}</span></div><div class="mini-note" style="margin-top:8px; white-space:pre-wrap;">${esc(item.document || item.summary || '')}</div></div>`, 'No local action memory yet.');
    setStatus('assistant-phase12-local-history-status', `${items.length} local action item(s) loaded.`, 'ok');
  }

  function bind(id, fn, statusId) {
    $(id)?.addEventListener('click', () => fn().catch(err => setStatus(statusId, err.message || String(err), 'warn')));
  }

  document.addEventListener('DOMContentLoaded', () => {
    bind('btn-assistant-phase12-load-local-actions', loadLocalActions, 'assistant-phase12-local-catalog-status');
    bind('btn-assistant-phase12-preview-local-action', previewLocalAction, 'assistant-phase12-local-action-status');
    bind('btn-assistant-phase12-execute-local-action', executeLocalAction, 'assistant-phase12-local-action-status');
    bind('btn-assistant-phase12-refresh-local-history', refreshLocalHistory, 'assistant-phase12-local-history-status');
    $('assistant-phase12-local-action-type')?.addEventListener('change', event => {
      const type = event.target.value;
      if ($('assistant-phase12-local-args')) $('assistant-phase12-local-args').value = localActionExamples(type);
      if ($('assistant-phase12-local-risk-preview')) $('assistant-phase12-local-risk-preview').value = 'Preview required';
    });
    $('assistant-phase12-local-action-list')?.addEventListener('click', event => {
      const node = event.target.closest('[data-phase12-local-action]');
      if (!node) return;
      const actionType = node.dataset.phase12LocalAction || 'open_path';
      if ($('assistant-phase12-local-action-type')) $('assistant-phase12-local-action-type').value = actionType;
      if ($('assistant-phase12-local-args')) $('assistant-phase12-local-args').value = localActionExamples(actionType);
    });
    document.addEventListener('click', event => {
      const node = event.target.closest('[data-phase12-local-preset-type][data-phase12-local-preset-id]');
      if (!node) return;
      const type = node.dataset.phase12LocalPresetType;
      const id = node.dataset.phase12LocalPresetId;
      if ($('assistant-phase12-local-action-type')) $('assistant-phase12-local-action-type').value = type;
      if ($('assistant-phase12-local-args')) {
        $('assistant-phase12-local-args').value = type === 'launch_app' ? pretty({ app_id: id }) : pretty({ preset_id: id });
      }
      if ($('assistant-phase12-local-risk-preview')) $('assistant-phase12-local-risk-preview').value = 'Preview required';
    });
    loadLocalActions().catch(() => {});
  });
})();
