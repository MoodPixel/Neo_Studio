function renderSearchGroup(title, key, items) {
  const group = document.createElement('div');
  group.className = 'search-group';
  group.innerHTML = `<h3>${escapeHtml(title)} <span class="kbd">${items.length}</span></h3>`;
  items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'search-result-item';
    const meta = [item.category || '', item.model || '', item.style || item.preset_kind || '', item.updated_at ? String(item.updated_at).replace('T', ' ') : ''].filter(Boolean).join(' · ');
    row.innerHTML = `
      <div>
        <div><strong>${escapeHtml(item.name || '(untitled)')}</strong></div>
        <div class="search-result-meta">${escapeHtml(meta || key)}</div>
        <div class="search-result-snippet">${escapeHtml(item.snippet || '')}</div>
      </div>
      <div class="row">
        <button class="btn" type="button" data-search-open="${key}" data-search-id="${escapeHtml(item.id || '')}" data-search-name="${escapeHtml(item.name || '')}">Open</button>
      </div>
    `;
    group.appendChild(row);
  });
  return group;
}

function clearGlobalSearchResults() {
  $('global-search-query').value = '';
  $('global-search-results').innerHTML = '';
  $('global-search-results').classList.add('hidden');
  setStatus('global-search-status', '');
}

async function runGlobalSearch() {
  const query = trim($('global-search-query').value || '');
  if (!query) {
    setStatus('global-search-status', 'Type something to search.', 'warn');
    $('global-search-results').classList.add('hidden');
    return;
  }
  setBusy('btn-run-global-search', true, 'Searching...');
  try {
    const data = await safeFetchJson(`/api/global-search?q=${encodeURIComponent(query)}&limit=10`);
    const wrap = $('global-search-results');
    wrap.innerHTML = '';
    const mapping = [
      ['prompts', 'Prompts'],
      ['captions', 'Captions'],
      ['characters', 'Characters'],
      ['presets', 'Presets'],
      ['loras', 'LoRAs / TI'],
      ['metadata_records', 'Metadata Records'],
      ['bundles', 'Bundles / Projects'],
    ];
    let total = 0;
    mapping.forEach(([key, label]) => {
      const items = data.results?.[key] || [];
      if (!items.length) return;
      total += items.length;
      wrap.appendChild(renderSearchGroup(label, key, items));
    });
    if (!total) {
      wrap.innerHTML = '<div class="card-lite"><div class="muted">No matches found.</div></div>';
    }
    wrap.classList.remove('hidden');
    setStatus('global-search-status', `${total} result(s) found.`);
  } catch (e) {
    setStatus('global-search-status', e.message, 'error');
  } finally {
    setBusy('btn-run-global-search', false);
  }
}

async function openSearchResult(kind, id, name) {
  if (kind === 'prompts') {
    switchTab('prompt');
    try {
      const data = await safeFetchJson(`/api/prompt-record?prompt_id=${encodeURIComponent(id)}`);
      const rec = data.record || {};
      loadedPromptId = rec.id || id;
      $('prompt-name').value = rec.name || '';
      fillCategorySelect('prompt-category', [rec.category || 'uncategorized'], rec.category || 'uncategorized');
      if ($('saved-prompt-category')) fillCategorySelect('saved-prompt-category', [rec.category || 'uncategorized'], rec.category || 'uncategorized');
      $('prompt-output').value = rec.prompt || rec.raw_prompt || '';
      $('prompt-raw').value = rec.raw_prompt || rec.prompt || '';
      $('prompt-notes').value = rec.notes || '';
      $('prompt-style').value = rec.style || $('prompt-style').value;
      currentPromptFinishReason = rec.finish_reason || '';
      $('prompt-finish-reason').textContent = `finish: ${currentPromptFinishReason || '—'}`;
      updateCounter('prompt-output', 'prompt-output-counter');
      if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
      setStatus('saved-prompt-status', 'Loaded prompt from search.');
    } catch (e) {
      setStatus('saved-prompt-status', e.message, 'error');
    }
    return;
  }
  if (kind === 'captions') {
    switchTab('caption');
    await loadCaptionRecord(id);
    return;
  }
  if (kind === 'characters') {
    switchTab('prompt');
    if ($('saved-character-name')) {
      $('saved-character-name').value = id || name;
      await loadSavedCharacter();
    }
    return;
  }
  if (kind === 'presets') {
    if ((id || '').startsWith('prompt:')) {
      switchTab('prompt');
      $('prompt-preset').value = name;
      applyPromptPreset(name, true);
      setStatus('prompt-preset-status', `Loaded preset: ${name}`);
      return;
    }
    if ((id || '').startsWith('caption:')) {
      switchTab('caption');
      $('caption-preset').value = name;
      applyCaptionPreset(name, true);
      setStatus('caption-preset-status', `Loaded preset: ${name}`);
      return;
    }
  }
  if (kind === 'loras') {
    switchTab('prompt');
    const insert = `<lora:${name}:1>`;
    const current = trim($('prompt-output').value || $('prompt-idea').value || '');
    $('prompt-output').value = current ? `${current}, ${insert}` : insert;
    $('prompt-raw').value = $('prompt-output').value;
    updateCounter('prompt-output', 'prompt-output-counter');
    if (typeof maybeRunPromptQA === 'function') maybeRunPromptQA('auto');
    setStatus('prompt-run-status', `Inserted LoRA token for ${name}.`);
    return;
  }
  if (kind === 'metadata_records') {
    await loadMetadataRecord(id);
    return;
  }
}



const _openSearchResultOriginal = openSearchResult;
openSearchResult = async function(kind, id, name) {
  if (kind === 'bundles') {
    switchTab('prompt');
    try {
      const data = await safeFetchJson(`/api/bundle-record?bundle_id=${encodeURIComponent(id)}`);
      applyBundleToForm(data.record || {});
      applyBundleToWorkspace(data.record || {});
      setStatus('bundle-status', 'Bundle loaded from search.');
    } catch (e) {
      setStatus('bundle-status', e.message, 'error');
    }
    return;
  }
  return _openSearchResultOriginal(kind, id, name);
};
