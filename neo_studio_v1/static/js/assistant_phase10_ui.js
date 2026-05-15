(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trim = (value) => String(value ?? '').trim();
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
  const pretty = (value) => JSON.stringify(value ?? {}, null, 2);

  function activeSessionId() {
    return document.querySelector('.assistant-session-card.active')?.dataset?.assistantSessionId || '';
  }
  function activeProjectId() {
    return trim($('assistant-project-select')?.value || '');
  }
  function setStatus(id, text, tone = '') {
    const node = $(id);
    if (!node) return;
    node.textContent = text || '';
    node.dataset.tone = tone || '';
  }
  async function fetchJson(url, options = {}) {
    const res = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || `Request failed (${res.status})`);
    return data;
  }
  function parseJsonField(id, fallback = {}) {
    const raw = trim($(id)?.value || '');
    if (!raw) return fallback;
    try { return JSON.parse(raw); }
    catch (err) { throw new Error(`${id} must contain valid JSON.`); }
  }
  function statCard(title, value, note = '') {
    return `<div class="card-lite"><div class="stat-title">${esc(title)}</div><div class="stat-value">${esc(value)}</div>${note ? `<div class="mini-note" style="margin-top:6px;">${esc(note)}</div>` : ''}</div>`;
  }
  function renderList(id, items, renderer, empty = 'Nothing to show yet.') {
    const wrap = $(id);
    if (!wrap) return;
    const rows = Array.isArray(items) ? items : [];
    wrap.innerHTML = rows.length ? rows.map(renderer).join('') : `<div class="assistant-session-empty">${esc(empty)}</div>`;
  }

  async function refreshContextPack() {
    const sid = activeSessionId();
    if (!sid) throw new Error('Select an Assistant chat first.');
    setStatus('assistant-phase10-context-status', 'Building context pack...', '');
    const q = trim($('assistant-phase10-context-query')?.value || $('assistant-composer')?.value || '');
    const data = await fetchJson(`/api/assistant/context-pack-preview?session_id=${encodeURIComponent(sid)}&q=${encodeURIComponent(q)}`);
    const pack = data.context_pack || {};
    const diag = pack.diagnostics || {};
    if ($('assistant-phase10-context-stats')) $('assistant-phase10-context-stats').innerHTML = [
      statCard('Sections', diag.section_count ?? 0),
      statCard('Memory items', pack.item_count ?? 0, `Candidates: ${pack.candidate_count ?? 0}`),
      statCard('Repo matches', diag.repo_index_result_count ?? 0, `Files indexed: ${diag.repo_index_file_count ?? 0}`),
    ].join('');
    renderList('assistant-phase10-context-sections', pack.prompt_sections || [], item => `<div class="card-lite"><div class="row-between"><strong>${esc(item.title || 'Section')}</strong><span class="badge">${esc(item.kind || 'context')} · ${esc(item.priority ?? '')}</span></div><div class="mini-note" style="margin-top:8px; white-space:pre-wrap;">${esc(String(item.content || '').slice(0, 700))}</div></div>`);
    if ($('assistant-phase10-context-prompt')) $('assistant-phase10-context-prompt').textContent = pack.prompt_block || '';
    setStatus('assistant-phase10-context-status', 'Context pack ready.', 'ok');
  }

  async function searchRepoIndex() {
    const q = trim($('assistant-phase10-repo-query')?.value || 'assistant');
    setStatus('assistant-phase10-repo-status', 'Searching repo index...', '');
    const data = await fetchJson(`/api/assistant/repo-index?q=${encodeURIComponent(q)}&limit=12`);
    const payload = data.repo_index || {};
    if ($('assistant-phase10-repo-stats')) $('assistant-phase10-repo-stats').innerHTML = [
      statCard('Files indexed', payload.file_count ?? 0),
      statCard('Matches', payload.result_count ?? (payload.results || []).length),
      statCard('Version', payload.version || 'repo_index'),
    ].join('');
    renderList('assistant-phase10-repo-results', payload.results || [], item => `<div class="card-lite"><div class="row-between"><strong>${esc(item.path || 'file')}</strong><span class="badge">${esc(item.kind || '')} · ${Number(item.score || 0).toFixed(2)}</span></div><div class="mini-note" style="margin-top:8px;">${esc(item.summary || '')}</div></div>`);
    setStatus('assistant-phase10-repo-status', 'Repo search ready.', 'ok');
  }
  async function rebuildRepoIndex() {
    setStatus('assistant-phase10-repo-status', 'Rebuilding repo index...', '');
    const data = await fetchJson('/api/assistant/repo-index-rebuild', { method: 'POST', body: JSON.stringify({ max_files: 1200 }) });
    const payload = data.repo_index || {};
    if ($('assistant-phase10-repo-stats')) $('assistant-phase10-repo-stats').innerHTML = [statCard('Files indexed', payload.file_count ?? 0), statCard('Skipped after limit', payload.skipped_after_limit ?? 0), statCard('Indexed at', payload.indexed_at || '')].join('');
    setStatus('assistant-phase10-repo-status', 'Repo index rebuilt.', 'ok');
  }

  async function loadToolCatalog() {
    setStatus('assistant-phase10-tool-status', 'Loading tools...', '');
    const category = trim($('assistant-phase10-tool-category')?.value || '');
    const data = await fetchJson(`/api/assistant/tool-catalog?category=${encodeURIComponent(category)}`);
    const catalog = data.catalog || {};
    const select = $('assistant-phase10-tool-category');
    if (select && !select.dataset.loaded) {
      select.innerHTML = '<option value="">All categories</option>' + (catalog.categories || []).map(cat => `<option value="${esc(cat)}">${esc(cat)}</option>`).join('');
      select.dataset.loaded = '1';
    }
    renderList('assistant-phase10-tool-list', catalog.tools || [], tool => `<button class="assistant-session-card" type="button" data-assistant-phase10-tool="${esc(tool.id || '')}"><div class="assistant-session-card-title">${esc(tool.id || '')} · ${esc(tool.name || '')}</div><div class="assistant-session-card-meta">${esc(tool.category || '')} · risk: ${esc(tool.risk || '')} · ${tool.read_only ? 'read-only' : 'write-capable'}</div></button>`, 'No registered Assistant tools.');
    setStatus('assistant-phase10-tool-status', `${catalog.count || 0} tool(s) loaded.`, 'ok');
  }
  async function toolCall(endpoint) {
    const toolId = trim($('assistant-phase10-tool-id')?.value || '');
    if (!toolId) throw new Error('Tool ID is required.');
    const args = parseJsonField('assistant-phase10-tool-args', {});
    const body = { tool_id: toolId, arguments: args, confirmed: Boolean($('assistant-phase10-tool-confirmed')?.checked), session_id: activeSessionId(), project_id: activeProjectId() };
    const data = await fetchJson(endpoint, { method: 'POST', body: JSON.stringify(body) });
    if ($('assistant-phase10-tool-output')) $('assistant-phase10-tool-output').textContent = pretty(data);
  }

  async function patchCall(endpoint) {
    const plan = parseJsonField('assistant-phase10-patch-json', {});
    const data = await fetchJson(endpoint, { method: 'POST', body: JSON.stringify({ plan, confirmed: Boolean($('assistant-phase10-patch-confirmed')?.checked), allow_delete: Boolean($('assistant-phase10-patch-allow-delete')?.checked) }) });
    if ($('assistant-phase10-patch-output')) $('assistant-phase10-patch-output').textContent = pretty(data);
    setStatus('assistant-phase10-patch-status', 'Patch action completed.', 'ok');
  }

  async function refreshActions() {
    const data = await fetchJson(`/api/assistant/action-memory-recent?session_id=${encodeURIComponent(activeSessionId())}&project_id=${encodeURIComponent(activeProjectId())}&limit=24`);
    renderList('assistant-phase10-action-list', data.items || [], item => `<div class="card-lite"><div class="row-between"><strong>${esc(item.chunk_type || 'action')}</strong><span class="badge">${esc(item.created_at || '')}</span></div><div class="mini-note" style="margin-top:8px; white-space:pre-wrap;">${esc(item.document || item.summary || '')}</div></div>`, 'No action memory yet.');
  }
  async function writeTaskMemory() {
    const summary = trim($('assistant-phase10-task-summary')?.value || '');
    if (!summary) throw new Error('Task summary is required.');
    const data = await fetchJson('/api/assistant/task-memory-write', { method: 'POST', body: JSON.stringify({ summary, outcome: trim($('assistant-phase10-task-outcome')?.value || ''), session_id: activeSessionId(), project_id: activeProjectId(), details: { source: 'phase10_ui' } }) });
    setStatus('assistant-phase10-task-status', 'Task memory saved.', 'ok');
    await refreshActions();
    return data;
  }

  async function previewPersona() {
    const sid = activeSessionId();
    if (!sid) throw new Error('Select an Assistant chat first.');
    const data = await fetchJson('/api/assistant/persona-preview', { method: 'POST', body: JSON.stringify({ session_id: sid, q: trim($('assistant-phase10-persona-query')?.value || '') }) });
    const p = data.persona || {};
    if ($('assistant-phase10-persona-stats')) $('assistant-phase10-persona-stats').innerHTML = [statCard('Assistant', p.assistant_name || p.name || 'Neo'), statCard('Tone', p.tone || p.address_style || ''), statCard('Rules', Array.isArray(p.rules) ? p.rules.length : (p.rule_count || 0))].join('');
    if ($('assistant-phase10-persona-output')) $('assistant-phase10-persona-output').textContent = pretty(p);
    setStatus('assistant-phase10-persona-status', 'Persona preview ready.', 'ok');
  }

  function bind(id, fn, statusId) {
    $(id)?.addEventListener('click', () => fn().catch(err => statusId ? setStatus(statusId, err.message || String(err), 'warn') : console.warn(err)));
  }
  document.addEventListener('DOMContentLoaded', () => {
    bind('btn-assistant-phase10-refresh-context', refreshContextPack, 'assistant-phase10-context-status');
    bind('btn-assistant-phase10-search-repo', searchRepoIndex, 'assistant-phase10-repo-status');
    bind('btn-assistant-phase10-rebuild-repo', rebuildRepoIndex, 'assistant-phase10-repo-status');
    bind('btn-assistant-phase10-load-tools', loadToolCatalog, 'assistant-phase10-tool-status');
    bind('btn-assistant-phase10-preview-tool', () => toolCall('/api/assistant/tool-preview'), 'assistant-phase10-tool-status');
    bind('btn-assistant-phase10-execute-tool', () => toolCall('/api/assistant/tool-execute'), 'assistant-phase10-tool-status');
    bind('btn-assistant-phase10-validate-patch', () => patchCall('/api/assistant/patch-plan-validate'), 'assistant-phase10-patch-status');
    bind('btn-assistant-phase10-preview-patch', () => patchCall('/api/assistant/patch-plan-preview'), 'assistant-phase10-patch-status');
    bind('btn-assistant-phase10-apply-patch', () => patchCall('/api/assistant/patch-plan-apply'), 'assistant-phase10-patch-status');
    bind('btn-assistant-phase10-refresh-actions', refreshActions, 'assistant-phase10-task-status');
    bind('btn-assistant-phase10-write-task', writeTaskMemory, 'assistant-phase10-task-status');
    bind('btn-assistant-phase10-preview-persona', previewPersona, 'assistant-phase10-persona-status');
    $('assistant-phase10-tool-list')?.addEventListener('click', event => {
      const node = event.target.closest('[data-assistant-phase10-tool]');
      if (!node) return;
      if ($('assistant-phase10-tool-id')) $('assistant-phase10-tool-id').value = node.dataset.assistantPhase10Tool || '';
    });
    loadToolCatalog().catch(() => {});
  });
})();
