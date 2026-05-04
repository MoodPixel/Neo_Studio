(function () {
  const core = window.neoRoleplayV2;
  if (!core) return;
  const { state } = core;
  state.continuityControl = state.continuityControl || {
    contexts: {},
    rowsByContext: {},
    selectedByContext: {},
  };

  function text(value) { return core.text(value); }
  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function boolValue(value) { return !!value; }
  function uniq(values) { return Array.from(new Set((Array.isArray(values) ? values : []).map(item => text(item)).filter(Boolean))); }
  function rowId(row) { return text(row?.memory_id || row?.id || row?.shared_memory_id || row?.callback_id); }
  function activeControlLabel(row) {
    const control = row?.control_state || {};
    const cooldown = row?.cooldown_state || {};
    if (control.is_pinned) return 'Pinned';
    if (control.is_suppressed) return 'Suppressed';
    if (control.is_resolved) return 'Resolved';
    if (cooldown.any_active) return 'Cooling down';
    return 'Neutral';
  }
  function recurrenceLabel(row) {
    const recurrence = row?.recurrence_state || {};
    const count = Number(recurrence.selected_count || 0);
    if (count <= 0) return 'Fresh';
    return `Seen ${count}×`;
  }
  function formatTraceRef(ref = {}) {
    const bits = [
      text(ref.row_origin),
      text(ref.trace_id),
      text(ref.bundle_id),
      text(ref.source_ref),
      text(ref.query_text),
      text(ref.created_at),
    ].filter(Boolean);
    return bits.join(' · ');
  }
  function toneForRow(row) {
    const control = row?.control_state || {};
    const cooldown = row?.cooldown_state || {};
    if (control.is_pinned) return 'primary';
    if (control.is_suppressed || control.is_resolved) return 'neutral';
    if (cooldown.any_active) return 'warning';
    return 'neutral';
  }
  function setStatusFor(contextKey, message, tone = '') {
    const cfg = state.continuityControl.contexts[contextKey] || {};
    const id = cfg.statusId;
    if (!id) return;
    core.setStatus(id, message, tone);
  }
  function currentRows(contextKey) {
    return Array.isArray(state.continuityControl.rowsByContext[contextKey]) ? state.continuityControl.rowsByContext[contextKey] : [];
  }
  function selectedId(contextKey) {
    return text(state.continuityControl.selectedByContext[contextKey]);
  }
  function selectedRow(contextKey) {
    const id = selectedId(contextKey);
    return currentRows(contextKey).find(row => rowId(row) === id) || null;
  }

  function mergeSeedRows(seedRows = [], payloadRows = []) {
    const map = new Map();
    (Array.isArray(payloadRows) ? payloadRows : []).forEach(row => {
      const id = rowId(row);
      if (id) map.set(id, Object.assign({}, row));
    });
    (Array.isArray(seedRows) ? seedRows : []).forEach((seed, index) => {
      const id = rowId(seed);
      if (!id) return;
      const existing = map.get(id) || { memory_id: id, trace_refs: [], row_sources: [] };
      map.set(id, Object.assign({}, existing, {
        memory_id: id,
        title: text(seed.title) || existing.title || id,
        summary: text(seed.summary) || existing.summary || '',
        text_excerpt: text(seed.text || seed.document || seed.summary).slice(0, 360) || existing.text_excerpt || '',
        memory_type: text(seed.memory_type) || existing.memory_type || '',
        entity_id: text(seed.entity_id) || existing.entity_id || '',
        entity_label: text(seed.entity_label) || existing.entity_label || '',
        source_ref: text(seed.source_ref) || existing.source_ref || '',
        score: Number(seed.score || existing.score || 0),
        rerank_score: Number(seed.rerank_score || existing.rerank_score || 0),
        continuity_bias: Number(seed.continuity_bias || existing.continuity_bias || 0),
        retrieval_rank: Number(seed.retrieval_rank || existing.retrieval_rank || index + 1),
        selected_from_trace: seed.selected_from_trace === true || existing.selected_from_trace === true,
        recovery_tags: uniq([...(existing.recovery_tags || []), ...(seed.recovery_tags || [])]),
        row_sources: uniq([...(existing.row_sources || []), 'seed_row']),
      }));
    });
    return Array.from(map.values()).sort((a, b) => {
      const pinnedDelta = Number(boolValue(b?.control_state?.is_pinned)) - Number(boolValue(a?.control_state?.is_pinned));
      if (pinnedDelta) return pinnedDelta;
      const selectedDelta = Number(boolValue(b?.selected_from_trace)) - Number(boolValue(a?.selected_from_trace));
      if (selectedDelta) return selectedDelta;
      const rankA = Number(a?.retrieval_rank || 999999);
      const rankB = Number(b?.retrieval_rank || 999999);
      if (rankA !== rankB) return rankA - rankB;
      const recurrenceA = Number(a?.recurrence_state?.selected_count || 0);
      const recurrenceB = Number(b?.recurrence_state?.selected_count || 0);
      if (recurrenceA !== recurrenceB) return recurrenceB - recurrenceA;
      const scoreA = Number(a?.score || 0);
      const scoreB = Number(b?.score || 0);
      if (scoreA !== scoreB) return scoreB - scoreA;
      const salienceA = Number(a?.salience || 0);
      const salienceB = Number(b?.salience || 0);
      if (salienceA !== salienceB) return salienceB - salienceA;
      return rowId(a).localeCompare(rowId(b));
    });
  }

  function rowCardHtml(row, contextKey) {
    const id = rowId(row);
    const selected = id && id === selectedId(contextKey);
    const controlLabel = activeControlLabel(row);
    const recurrence = recurrenceLabel(row);
    const recoveryTags = Array.isArray(row?.recovery_tags) && row.recovery_tags.length ? row.recovery_tags.join(', ') : '';
    const sourceTrace = Array.isArray(row?.trace_refs) && row.trace_refs.length ? formatTraceRef(row.trace_refs[0]) : text(row?.source_ref);
    const metrics = [
      row?.retrieval_rank ? `rank ${Number(row.retrieval_rank)}` : '',
      row?.score ? `score ${Number(row.score).toFixed(3)}` : '',
      row?.rerank_score ? `rerank ${Number(row.rerank_score).toFixed(3)}` : '',
      row?.continuity_bias ? `bias ${Number(row.continuity_bias).toFixed(3)}` : '',
      Number(row?.recurrence_state?.selected_count || 0) > 0 ? recurrence : recurrence,
      controlLabel,
      recoveryTags ? `recovery ${recoveryTags}` : '',
    ].filter(Boolean).join(' · ');
    return `<button type="button" class="btn${selected ? ' btn-primary' : ''}" data-continuity-context="${escapeHtml(contextKey)}" data-continuity-row-id="${escapeHtml(id)}" style="display:grid; gap:5px; text-align:left; width:100%; padding:10px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.02);">
      <span style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start;">
        <strong style="font-size:13px;">${escapeHtml(text(row?.title) || id)}</strong>
        <span class="badge" data-ui-tone="${escapeHtml(toneForRow(row))}">${escapeHtml(controlLabel)}</span>
      </span>
      <span class="mini-note">${escapeHtml(text(row?.summary) || text(row?.text_excerpt) || 'No continuity summary available yet.')}</span>
      <span class="mini-note" style="opacity:0.85;">${escapeHtml(metrics || 'No continuity metrics yet.')}</span>
      ${sourceTrace ? `<span class="mini-note" style="opacity:0.7;">${escapeHtml(sourceTrace)}</span>` : ''}
    </button>`;
  }

  function renderRowList(contextKey) {
    const cfg = state.continuityControl.contexts[contextKey] || {};
    const root = cfg.listId ? core.$(cfg.listId) : null;
    const badge = cfg.countId ? core.$(cfg.countId) : null;
    if (!root) return;
    const rows = currentRows(contextKey);
    if (badge) badge.textContent = String(rows.length || 0);
    if (!rows.length) {
      root.innerHTML = '<div class="mini-note">No continuity rows available in this context yet.</div>';
      return;
    }
    root.innerHTML = rows.map(row => rowCardHtml(row, contextKey)).join('');
    root.querySelectorAll('[data-continuity-row-id]').forEach(btn => {
      btn.addEventListener('click', () => selectRow(contextKey, text(btn.getAttribute('data-continuity-row-id'))));
    });
  }

  function renderInspector(contextKey) {
    const cfg = state.continuityControl.contexts[contextKey] || {};
    const root = cfg.inspectorId ? core.$(cfg.inspectorId) : null;
    if (!root) return;
    const row = selectedRow(contextKey);
    if (!row) {
      root.innerHTML = '<div class="mini-note">Select a continuity row to inspect its control state, recurrence, cooldown, and source traces.</div>';
      return;
    }
    const control = row.control_state || {};
    const recurrence = row.recurrence_state || {};
    const cooldown = row.cooldown_state || {};
    const traceRefs = Array.isArray(row.trace_refs) ? row.trace_refs : [];
    const traceHtml = traceRefs.length
      ? `<div style="display:grid; gap:6px; max-height:180px; overflow:auto;">${traceRefs.map(ref => `<div class="mini-note" style="padding:8px; border:1px solid rgba(255,255,255,0.06); border-radius:10px; background:rgba(255,255,255,0.02);">${escapeHtml(formatTraceRef(ref) || 'Trace')}</div>`).join('')}</div>`
      : '<div class="mini-note">No source traces linked yet.</div>';
    root.innerHTML = `
      <div style="display:grid; gap:10px;">
        <div class="row-between" style="gap:12px; align-items:flex-start;">
          <div>
            <div class="stat-title">${escapeHtml(text(row.title) || rowId(row))}</div>
            <div class="mini-note">${escapeHtml(text(row.summary) || text(row.text_excerpt) || 'No continuity summary available.')}</div>
          </div>
          <div class="badge" data-ui-tone="${escapeHtml(toneForRow(row))}">${escapeHtml(activeControlLabel(row))}</div>
        </div>
        <div class="grid grid-2" style="gap:10px; align-items:start;">
          <div class="panel" style="padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
            <div class="stat-title">Control state</div>
            <div class="mini-note" style="margin-top:8px;">Pinned · ${control.is_pinned ? 'yes' : 'no'}</div>
            <div class="mini-note">Suppressed · ${control.is_suppressed ? 'yes' : 'no'}</div>
            <div class="mini-note">Resolved · ${control.is_resolved ? 'yes' : 'no'}</div>
            <div class="mini-note">Control cooldown · ${escapeHtml(text(control.cooldown_until) || 'none')}</div>
          </div>
          <div class="panel" style="padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
            <div class="stat-title">Recurrence state</div>
            <div class="mini-note" style="margin-top:8px;">Selected count · ${Number(recurrence.selected_count || 0)}</div>
            <div class="mini-note">Bucket · ${escapeHtml(text(recurrence.bucket_key) || 'none')}</div>
            <div class="mini-note">Last selected · ${escapeHtml(text(recurrence.last_selected_at) || 'never')}</div>
            <div class="mini-note">Recurrence cooldown · ${escapeHtml(text(recurrence.cooldown_until) || 'none')}</div>
          </div>
        </div>
        <div class="panel" style="padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
          <div class="row-between"><div><div class="stat-title">Trace + identity</div></div><div class="badge">${escapeHtml(text(row.memory_type) || 'memory')}</div></div>
          <div class="mini-note" style="margin-top:8px;">Memory id · ${escapeHtml(rowId(row))}</div>
          <div class="mini-note">Entity · ${escapeHtml(text(row.entity_label) || text(row.entity_id) || 'none')}</div>
          <div class="mini-note">Source ref · ${escapeHtml(text(row.source_ref) || 'none')}</div>
          <div class="mini-note">Cooldown active · ${cooldown.any_active ? 'yes' : 'no'}</div>
          <div class="mini-note">Row sources · ${escapeHtml((row.row_sources || []).join(', ') || 'none')}</div>
          ${Array.isArray(row.shared_with) && row.shared_with.length ? `<div class="mini-note">Shared with · ${escapeHtml(row.shared_with.join(', '))}</div>` : ''}
          ${row.score ? `<div class="mini-note">Score · ${Number(row.score).toFixed(3)}</div>` : ''}
          ${row.rerank_score ? `<div class="mini-note">Rerank score · ${Number(row.rerank_score).toFixed(3)}</div>` : ''}
          ${row.continuity_bias ? `<div class="mini-note">Continuity bias · ${Number(row.continuity_bias).toFixed(3)}</div>` : ''}
          ${Array.isArray(row.recovery_tags) && row.recovery_tags.length ? `<div class="mini-note">Recovery tags · ${escapeHtml(row.recovery_tags.join(', '))}</div>` : ''}
        </div>
        <div class="panel" style="padding:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);">
          <div class="row-between"><div><div class="stat-title">Source traces</div></div><div class="badge">${traceRefs.length}</div></div>
          <div style="margin-top:8px;">${traceHtml}</div>
        </div>
        <div class="row" style="gap:8px; flex-wrap:wrap; align-items:center;">
          <button type="button" class="btn btn-small" data-continuity-action="pin" data-continuity-context="${escapeHtml(contextKey)}">Pin</button>
          <button type="button" class="btn btn-small" data-continuity-action="suppress" data-continuity-context="${escapeHtml(contextKey)}">Suppress</button>
          <button type="button" class="btn btn-small" data-continuity-action="resolve" data-continuity-context="${escapeHtml(contextKey)}">Resolve</button>
          <button type="button" class="btn btn-small" data-continuity-action="cooldown" data-continuity-context="${escapeHtml(contextKey)}">Cool down</button>
          <button type="button" class="btn btn-small" data-continuity-action="clear" data-continuity-context="${escapeHtml(contextKey)}">Clear</button>
        </div>
      </div>`;
    root.querySelectorAll('[data-continuity-action]').forEach(btn => {
      btn.addEventListener('click', () => applyAction(contextKey, text(btn.getAttribute('data-continuity-action'))).catch(err => setStatusFor(contextKey, err.message || String(err), 'error')));
    });
  }

  function syncLinkedInput(row = null) {
    const id = text(rowId(row));
    if (!id) return;
    if (core.$('roleplay-v2-memory-control-id')) core.$('roleplay-v2-memory-control-id').value = id;
  }

  function selectRow(contextKey, memoryId, options = {}) {
    const cleanId = text(memoryId);
    if (!cleanId) return;
    state.continuityControl.selectedByContext[contextKey] = cleanId;
    const row = selectedRow(contextKey);
    if (options.syncInput !== false) syncLinkedInput(row);
    renderRowList(contextKey);
    renderInspector(contextKey);
    const cfg = state.continuityControl.contexts[contextKey] || {};
    if (typeof cfg.onSelect === 'function') {
      try { cfg.onSelect(row || null); } catch (_) {}
    }
  }

  async function refreshContext(contextKey, options = {}) {
    const cfg = state.continuityControl.contexts[contextKey] || {};
    if (!cfg || typeof cfg.getFilters !== 'function') return { rows: [] };
    const filters = cfg.getFilters() || {};
    const seedRows = typeof cfg.getSeedRows === 'function' ? (cfg.getSeedRows() || []) : [];
    const seedIds = uniq(seedRows.map(rowId));
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      const clean = text(value);
      if (clean) params.set(key, clean);
    });
    if (seedIds.length) params.set('memory_ids', seedIds.join(','));
    if (!params.get('limit')) params.set('limit', String(Number(cfg.limit || 36) || 36));
    const url = `/api/roleplay/v2/runtime/continuity-rows?${params.toString()}`;
    const data = await core.getJson(url);
    const mergedRows = mergeSeedRows(seedRows, data.rows || []);
    state.continuityControl.rowsByContext[contextKey] = mergedRows;
    const preferredId = text(options.preferredId) || selectedId(contextKey) || rowId(mergedRows[0]);
    if (preferredId) state.continuityControl.selectedByContext[contextKey] = preferredId;
    renderRowList(contextKey);
    renderInspector(contextKey);
    const selected = selectedRow(contextKey);
    if (selected) syncLinkedInput(selected);
    if (!options.silent) setStatusFor(contextKey, data.count ? `Loaded ${data.count} continuity row(s).` : 'No continuity rows available for this context yet.', data.count ? 'success' : '');
    return { ...data, rows: mergedRows };
  }

  async function applyAction(contextKey, action = 'pin', cooldownMinutes = 60) {
    const row = selectedRow(contextKey);
    const memoryId = rowId(row);
    if (!memoryId) throw new Error('Select a continuity row first.');
    const cfg = state.continuityControl.contexts[contextKey] || {};
    const filters = typeof cfg.getFilters === 'function' ? (cfg.getFilters() || {}) : {};
    const payload = await core.postForm('/api/roleplay/v2/runtime/memory-control', {
      memory_id: memoryId,
      project_id: text(filters.project_id),
      entity_id: text(filters.entity_id),
      action,
      cooldown_minutes: action === 'cooldown' ? cooldownMinutes : 60,
    });
    await refreshContext(contextKey, { preferredId: memoryId, silent: true });
    setStatusFor(contextKey, payload.message || `${action} applied to ${memoryId}.`, 'success');
    if (contextKey !== 'studio') core.setStatus('roleplay-v2-memory-control-status', payload.message || `${action} applied to ${memoryId}.`, 'success');
    return payload;
  }

  function registerContext(contextKey, config = {}) {
    state.continuityControl.contexts[contextKey] = Object.assign({}, config || {});
    const cfg = state.continuityControl.contexts[contextKey];
    if (cfg.refreshButtonId) core.$(cfg.refreshButtonId)?.addEventListener('click', () => refreshContext(contextKey).catch(err => setStatusFor(contextKey, err.message || String(err), 'error')));
    renderRowList(contextKey);
    renderInspector(contextKey);
    return cfg;
  }

  function bindExternalSelection(contextKey, rowOrId) {
    const cleanId = typeof rowOrId === 'string' ? text(rowOrId) : rowId(rowOrId);
    if (!cleanId) return;
    if (currentRows(contextKey).some(row => rowId(row) === cleanId)) {
      selectRow(contextKey, cleanId);
      return;
    }
    refreshContext(contextKey, { preferredId: cleanId, silent: true }).catch(() => {});
  }

  core.registerModule('continuityControls', {
    registerContext,
    refreshContext,
    applyAction,
    selectRow,
    bindExternalSelection,
  });
})();
