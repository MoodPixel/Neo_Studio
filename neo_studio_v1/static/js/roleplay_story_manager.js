(function () {
  function storyEl(id) { return document.getElementById(id); }

  const readerState = {
    mode: 'edit',
    story: null,
    parts: [],
    currentPartIndex: 0,
  };
  const storyBranchMaps = new Map();

  function assetUrl(assetPath) {
    return typeof window.neoResolveRoleplayAssetUrl === 'function'
      ? window.neoResolveRoleplayAssetUrl(assetPath)
      : (assetPath ? `/api/roleplay/asset/file?asset_path=${encodeURIComponent(assetPath)}` : '');
  }

  function trimValue(value) {
    return String(value || '').trim();
  }
  const LINKED_CONTEXT_FIELDS = [
    { key: 'legend_ids', snapshot: 'legends', suffix: 'legends' },
    { key: 'universe_ids', snapshot: 'universes', suffix: 'universes' },
    { key: 'world_ids', snapshot: 'worlds', suffix: 'worlds' },
    { key: 'region_ids', snapshot: 'regions', suffix: 'regions' },
    { key: 'city_ids', snapshot: 'cities', suffix: 'cities' },
    { key: 'location_ids', snapshot: 'locations', suffix: 'locations' },
    { key: 'organization_ids', snapshot: 'organizations', suffix: 'organizations' },
    { key: 'character_ids', snapshot: 'characters', suffix: 'characters' },
    { key: 'artifact_ids', snapshot: 'artifacts', suffix: 'artifacts' },
    { key: 'ritual_ids', snapshot: 'rituals', suffix: 'rituals' },
    { key: 'cycle_ids', snapshot: 'cycles', suffix: 'cycles' },
    { key: 'creature_ids', snapshot: 'creatures', suffix: 'creatures' },
    { key: 'pack_ids', snapshot: 'packs', suffix: 'packs' },
    { key: 'scenario_ids', snapshot: 'scenarios', suffix: 'scenarios' },
  ];

  function normalizeLinkedContext(raw = {}) {
    const clean = {};
    LINKED_CONTEXT_FIELDS.forEach(field => {
      const values = Array.isArray(raw?.[field.key]) ? raw[field.key] : [];
      const ids = values.map(item => trimValue(item)).filter(Boolean);
      clean[field.key] = [...new Set(ids)];
    });
    return clean;
  }

  function librarySnapshot() {
    return typeof window.neoGetRoleplayLibraryStateSnapshot === 'function'
      ? (window.neoGetRoleplayLibraryStateSnapshot() || {})
      : {};
  }

  function linkedSelectId(prefix, suffix) {
    return `roleplay-${prefix}-link-${suffix}`;
  }

  function selectedMultiValues(id) {
    return Array.from(storyEl(id)?.selectedOptions || []).map(opt => trimValue(opt.value)).filter(Boolean);
  }

  function setMultiSelectOptions(id, items, selected = []) {
    const node = storyEl(id);
    if (!node) return;
    const current = new Set((Array.isArray(selected) ? selected : []).map(item => trimValue(item)).filter(Boolean));
    const options = [];
    (Array.isArray(items) ? items : []).forEach(item => {
      const value = trimValue(item?.id || '');
      if (!value) return;
      const label = trimValue(item?.title || item?.name || item?.display_name || 'Untitled');
      options.push(`<option value="${escapeHtml(value)}"${current.has(value) ? ' selected' : ''}>${escapeHtml(label)}</option>`);
    });
    node.innerHTML = options.length ? options.join('') : '<option value="">No saved records yet</option>';
  }

  function readLinkedContext(prefix) {
    const context = {};
    LINKED_CONTEXT_FIELDS.forEach(field => {
      context[field.key] = selectedMultiValues(linkedSelectId(prefix, field.suffix));
    });
    return normalizeLinkedContext(context);
  }

  function applyLinkedContext(prefix, raw = {}) {
    const context = normalizeLinkedContext(raw);
    const snapshot = librarySnapshot();
    LINKED_CONTEXT_FIELDS.forEach(field => {
      setMultiSelectOptions(linkedSelectId(prefix, field.suffix), snapshot[field.snapshot] || [], context[field.key] || []);
    });
  }

  function clearLinkedContext(prefix) {
    applyLinkedContext(prefix, {});
  }

  function linkedContextSummary(raw = {}, label = 'Linked context') {
    const snapshot = librarySnapshot();
    const context = normalizeLinkedContext(raw);
    const lines = [];
    LINKED_CONTEXT_FIELDS.forEach(field => {
      const ids = context[field.key] || [];
      if (!ids.length) return;
      const names = ids.map(id => {
        const match = (snapshot[field.snapshot] || []).find(item => trimValue(item?.id) === id);
        return trimValue(match?.title || match?.name || match?.display_name || '');
      }).filter(Boolean);
      if (!names.length) return;
      const heading = field.key.replace('_ids', '').replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
      lines.push(`${heading}: ${names.join(', ')}`);
    });
    return lines.length ? `${label}:\n${lines.join('\n')}` : '';
  }

  function renderLinkedContextSelectors() {
    applyLinkedContext('story', readLinkedContext('story'));
    applyLinkedContext('part', readLinkedContext('part'));
  }

  function setStoryCoverPreview(assetPath) {
    const img = storyEl('roleplay-story-cover-preview');
    const empty = storyEl('roleplay-story-cover-empty');
    const url = assetUrl(assetPath || '');
    if (img) {
      if (url) {
        img.src = url;
        img.classList.remove('hidden');
      } else {
        img.removeAttribute('src');
        img.classList.add('hidden');
      }
    }
    if (empty) empty.classList.toggle('hidden', !!url);
  }

  function storyFormState() {
    const explicitLeads = trimValue(storyEl('roleplay-story-leads')?.value);
    const fallbackLeads = [trimValue(storyEl('roleplay-user-name')?.value), trimValue(storyEl('roleplay-partner-name')?.value)].filter(Boolean).join(', ');
    const explicitWorld = trimValue(storyEl('roleplay-story-world')?.value);
    const selectedWorld = storyEl('roleplay-world-id')?.selectedOptions?.[0]?.textContent || '';
    return {
      story_id: trimValue(storyEl('roleplay-story-id')?.value),
      title: trimValue(storyEl('roleplay-story-title')?.value),
      summary: trimValue(storyEl('roleplay-story-summary')?.value),
      universe_label: trimValue(storyEl('roleplay-story-universe')?.value),
      world_label: explicitWorld || (selectedWorld && selectedWorld !== 'None' ? selectedWorld.split(' — ')[0].trim() : ''),
      lead_characters: explicitLeads || fallbackLeads,
      status: storyEl('roleplay-story-status')?.value || 'draft',
      canon_mode: storyEl('roleplay-canon-mode')?.value || 'what_if',
      output_preset: storyEl('roleplay-output-preset')?.value || 'roleplay',
      story_mode: storyEl('roleplay-story-form-mode')?.value || storyEl('roleplay-story-mode')?.value || 'linear',
      branch_option_count: Number(storyEl('roleplay-story-form-option-count')?.value || storyEl('roleplay-branch-option-count')?.value || 3),
      branch_allow_custom_option: String(storyEl('roleplay-story-form-allow-custom')?.value || storyEl('roleplay-branch-allow-custom')?.value || 'true') === 'true',
      linked_context_json: JSON.stringify(readLinkedContext('story')),
    };
  }

  function clearStoryForm() {
    ['roleplay-story-id', 'roleplay-part-id', 'roleplay-story-title', 'roleplay-story-summary', 'roleplay-story-universe', 'roleplay-story-world', 'roleplay-story-leads', 'roleplay-part-title'].forEach(id => {
      if (storyEl(id)) storyEl(id).value = '';
    });
    if (storyEl('roleplay-story-status')) storyEl('roleplay-story-status').value = 'draft';
    if (storyEl('roleplay-story-form-mode')) storyEl('roleplay-story-form-mode').value = 'linear';
    if (storyEl('roleplay-story-form-option-count')) storyEl('roleplay-story-form-option-count').value = '3';
    if (storyEl('roleplay-story-form-allow-custom')) storyEl('roleplay-story-form-allow-custom').value = 'true';
    clearLinkedContext('story');
    if (storyEl('roleplay-story-cover-file')) storyEl('roleplay-story-cover-file').value = '';
    setStoryCoverPreview('');
    setStatus('roleplay-story-status-msg', '');
  }

  function applyStoryRecord(record) {
    if (!record) return;
    if (storyEl('roleplay-story-id')) storyEl('roleplay-story-id').value = record.id || '';
    if (storyEl('roleplay-story-title')) storyEl('roleplay-story-title').value = record.title || '';
    if (storyEl('roleplay-story-summary')) storyEl('roleplay-story-summary').value = record.summary || '';
    if (storyEl('roleplay-story-universe')) storyEl('roleplay-story-universe').value = record.universe_label || '';
    if (storyEl('roleplay-story-world')) storyEl('roleplay-story-world').value = record.world_label || '';
    if (storyEl('roleplay-story-leads')) storyEl('roleplay-story-leads').value = (record.lead_character_names || []).join(', ');
    if (storyEl('roleplay-story-status')) storyEl('roleplay-story-status').value = record.meta?.status || 'draft';
    if (storyEl('roleplay-story-form-mode')) storyEl('roleplay-story-form-mode').value = record.story_mode || record.branching?.story_mode || 'linear';
    if (storyEl('roleplay-story-form-option-count')) storyEl('roleplay-story-form-option-count').value = String(record.branching?.option_count || 3);
    if (storyEl('roleplay-story-form-allow-custom')) storyEl('roleplay-story-form-allow-custom').value = String(record.branching?.allow_custom_option !== false);
    if (storyEl('roleplay-story-mode')) storyEl('roleplay-story-mode').value = record.story_mode || record.branching?.story_mode || 'linear';
    if (storyEl('roleplay-branch-option-count')) storyEl('roleplay-branch-option-count').value = String(record.branching?.option_count || 3);
    if (storyEl('roleplay-branch-allow-custom')) storyEl('roleplay-branch-allow-custom').value = String(record.branching?.allow_custom_option !== false);
    applyLinkedContext('story', record.linked_context || {});
    setStoryCoverPreview(record.cover?.image_path || '');
  }

  function storyThumbLabel(card) {
    const words = String(card.title || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return 'S';
    return words.slice(0, 2).map(word => word[0]).join('').toUpperCase();
  }

  function formatStoryMeta(card) {
    const parts = [];
    if (card.universe_label) parts.push(`Universe: ${card.universe_label}`);
    if (card.world_label) parts.push(`World: ${card.world_label}`);
    if ((card.lead_character_names || []).length) parts.push(`Cast: ${(card.lead_character_names || []).join(', ')}`);
    parts.push(`Parts: ${card.part_count || 0}`);
    if ((card.story_mode || 'linear') === 'branching') parts.push(`Mode: Branching (${card.branching?.option_count || 3} choices)`);
    if (card.status) parts.push(`Status: ${card.status}`);
    return parts.join(' · ');
  }

  function formatPartMeta(part) {
    const bits = [`Turns: ${part.turn_count || 0}`];
    if (part.parent_part_id) bits.push(`Checkpoint: ${part.branch_label || 'Alternate path'}`);
    else bits.push('Checkpoint: Start');
    if (part.progression_summary) bits.push(part.progression_summary);
    if (Number(part.choice_history_count || 0)) bits.push(`Choices: ${Number(part.choice_history_count || 0)}`);
    if (part.status) bits.push(`Status: ${part.status}`);
    return bits.join(' · ');
  }

  async function fetchStoryParts(storyId) {
    const data = await safeFetchJson(`/api/roleplay/story-parts?story_id=${encodeURIComponent(storyId || '')}`);
    return Array.isArray(data.parts) ? data.parts : [];
  }

  async function fetchStoryReader(storyId) {
    const data = await safeFetchJson(`/api/roleplay/story-reader?story_id=${encodeURIComponent(storyId || '')}`);
    return {
      story: data.story || null,
      parts: Array.isArray(data.parts) ? data.parts : [],
    };
  }

  async function fetchStoryBranchMap(storyId) {
    const data = await safeFetchJson(`/api/roleplay/story-branch-map?story_id=${encodeURIComponent(storyId || '')}`);
    const payload = {
      story: data.story || null,
      nodes: Array.isArray(data.nodes) ? data.nodes : [],
      startPartId: trimValue(data.start_part_id || ''),
      checkpointCount: Number(data.checkpoint_count || 0),
      branchCount: Number(data.branch_count || 0),
    };
    storyBranchMaps.set(trimValue(storyId), payload);
    return payload;
  }

  function cachedStoryBranchMap(storyId) {
    return storyBranchMaps.get(trimValue(storyId || '')) || null;
  }

  function resolveStoryStartPartId(storyId) {
    const payload = cachedStoryBranchMap(storyId);
    if (trimValue(payload?.startPartId)) return trimValue(payload.startPartId);
    const fallback = (readerState.parts || []).find(part => !trimValue(part.parent_part_id));
    return trimValue(fallback?.id || '');
  }

  async function replayCheckpoint(storyId, partId, label = 'Checkpoint') {
    await loadPartIntoRoleplay(storyId, partId);
    setStatus('roleplay-story-status-msg', `Replay ready from ${label}.`, 'ok');
  }

  async function replayStoryFromStart(storyId) {
    const map = cachedStoryBranchMap(storyId) || await fetchStoryBranchMap(storyId);
    const startPartId = trimValue(map?.startPartId || '');
    if (!startPartId) throw new Error('No starting checkpoint found for this story yet.');
    await replayCheckpoint(storyId, startPartId, 'the start');
  }

  async function createAlternatePathFromCheckpoint(storyId, node) {
    const checkpointId = trimValue(node?.id || '');
    if (!checkpointId) throw new Error('Checkpoint not found.');
    const options = Array.isArray(node?.latest_options) ? node.latest_options : [];
    let chosen = null;
    if (options.length) {
      const choiceList = options.map((option, index) => `${index + 1}. ${trimValue(option.label) || `Option ${index + 1}`} — ${trimValue(option.text)}`).join('\n');
      const raw = window.prompt(`Choose an alternate path from this checkpoint. Type a number, or write a custom path instead.\n\n${choiceList}`);
      const answer = trimValue(raw);
      if (!answer) return;
      const pickedIndex = Number(answer);
      if (Number.isFinite(pickedIndex) && pickedIndex >= 1 && pickedIndex <= options.length) {
        chosen = { ...options[pickedIndex - 1], source: 'generated' };
      } else {
        chosen = { id: 'custom', label: 'Custom alternate path', text: answer, source: 'custom' };
      }
    } else {
      const raw = window.prompt('This checkpoint has no saved generated choices yet. Write the alternate path you want to branch into.');
      const answer = trimValue(raw);
      if (!answer) return;
      chosen = { id: 'custom', label: 'Custom alternate path', text: answer, source: 'custom' };
    }
    const form = new FormData();
    form.append('part_id', checkpointId);
    form.append('branch_label', trimValue(chosen.label || node?.branch_label || 'Alternate path') || 'Alternate path');
    form.append('choice_id', trimValue(chosen.id || ''));
    form.append('choice_label', trimValue(chosen.label || 'Alternate path'));
    form.append('choice_text', trimValue(chosen.text || ''));
    form.append('choice_source', trimValue(chosen.source || 'generated') || 'generated');
    const data = await safeFetchJson('/api/roleplay/part/branch', { method: 'POST', body: form });
    if (data.branch_map?.story?.id) storyBranchMaps.set(trimValue(data.branch_map.story.id), {
      story: data.branch_map.story || null,
      nodes: Array.isArray(data.branch_map.nodes) ? data.branch_map.nodes : [],
      startPartId: trimValue(data.branch_map.start_part_id || ''),
      checkpointCount: Number(data.branch_map.checkpoint_count || 0),
      branchCount: Number(data.branch_map.branch_count || 0),
    });
    setStatus('roleplay-story-status-msg', data.message || 'Alternate path created.', 'ok');
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
    if (data.part?.id) await replayCheckpoint(storyId, data.part.id, data.part.title || 'alternate path');
  }

  async function loadStoryRecord(storyId) {
    const data = await safeFetchJson(`/api/roleplay/story?story_id=${encodeURIComponent(storyId || '')}`);
    applyStoryRecord(data.story || null);
    return data.story || null;
  }

  async function loadPartIntoRoleplay(storyId, partId) {
    const data = await safeFetchJson(`/api/roleplay/session/load-part?story_id=${encodeURIComponent(storyId || '')}&part_id=${encodeURIComponent(partId || '')}`);
    if (typeof window.neoApplyRoleplaySessionState === 'function') window.neoApplyRoleplaySessionState(data.session || {});
    if (storyEl('roleplay-part-id')) storyEl('roleplay-part-id').value = partId || '';
    if (storyEl('roleplay-part-title')) storyEl('roleplay-part-title').value = data.session?.part_title || '';
    if (typeof window.neoSetRoleplaySessionLink === 'function') window.neoSetRoleplaySessionLink(storyId || '', partId || '');
    setStatus('roleplay-story-status-msg', data.message || 'Story part loaded.', 'ok');
  }

  function closePartEditor() {
    storyEl('roleplay-part-editor')?.classList.add('hidden');
    if (storyEl('roleplay-part-editor-badge')) storyEl('roleplay-part-editor-badge').textContent = 'No part loaded';
    ['roleplay-part-editor-title', 'roleplay-part-editor-summary', 'roleplay-part-editor-scene-notes', 'roleplay-part-editor-canon', 'roleplay-part-editor-text', 'roleplay-part-branch-label'].forEach(id => {
      if (storyEl(id)) storyEl(id).value = '';
    });
    clearLinkedContext('part');
    setStatus('roleplay-part-editor-status', '');
  }

  async function openPartEditor(partId) {
    const data = await safeFetchJson(`/api/roleplay/part?part_id=${encodeURIComponent(partId || '')}`);
    const part = data.part || {};
    if (storyEl('roleplay-part-id')) storyEl('roleplay-part-id').value = part.id || '';
    if (storyEl('roleplay-part-title')) storyEl('roleplay-part-title').value = part.title || '';
    if (storyEl('roleplay-part-editor-title')) storyEl('roleplay-part-editor-title').value = part.title || '';
    if (storyEl('roleplay-part-editor-summary')) storyEl('roleplay-part-editor-summary').value = part.summary || '';
    if (storyEl('roleplay-part-editor-scene-notes')) storyEl('roleplay-part-editor-scene-notes').value = part.scene_notes || '';
    if (storyEl('roleplay-part-editor-canon')) storyEl('roleplay-part-editor-canon').value = part.pinned_canon || '';
    applyLinkedContext('part', part.linked_context || {});
    if (storyEl('roleplay-part-editor-text')) storyEl('roleplay-part-editor-text').value = part.scene_text || '';
    if (storyEl('roleplay-part-branch-label')) storyEl('roleplay-part-branch-label').value = '';
    if (storyEl('roleplay-part-editor-badge')) storyEl('roleplay-part-editor-badge').textContent = part.title || 'Part editor';
    storyEl('roleplay-part-editor')?.classList.remove('hidden');
    setStatus('roleplay-part-editor-status', '');
  }

  function setStoryMode(mode = 'edit') {
    readerState.mode = mode === 'reader' ? 'reader' : 'edit';
    const isReader = readerState.mode === 'reader';
    storyEl('roleplay-story-edit-pane')?.classList.toggle('hidden', isReader);
    storyEl('roleplay-story-reader-pane')?.classList.toggle('hidden', !isReader);
    const editBtn = storyEl('btn-roleplay-story-mode-edit');
    const readBtn = storyEl('btn-roleplay-story-open-reader');
    if (editBtn) {
      editBtn.disabled = !isReader;
      editBtn.classList.toggle('btn-primary', !isReader);
    }
    if (readBtn) {
      readBtn.disabled = isReader && !!readerState.story;
      readBtn.classList.toggle('btn-primary', isReader && !!readerState.story);
    }
    const hint = storyEl('roleplay-story-mode-hint');
    if (hint) {
      hint.textContent = isReader
        ? 'Reader mode is active. Use part navigation to move through the story without the live chat bubble layout.'
        : 'Edit mode keeps story cards, form fields, and save actions visible. Reader mode opens a cleaner scroll reading view for the selected story.';
    }
  }

  function createReaderMetaRow(label, value) {
    if (!trimValue(value)) return null;
    const row = document.createElement('div');
    row.className = 'muted small';
    row.style.marginTop = '6px';
    const strong = document.createElement('strong');
    strong.textContent = `${label}: `;
    row.append(strong, document.createTextNode(String(value || '')));
    return row;
  }

  function stripReadableSpeakerPrefixes(text) {
    const lines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const cleaned = [];
    for (let index = 0; index < lines.length; index += 1) {
      const raw = lines[index] || '';
      const line = raw.trim();
      if (!line) { cleaned.push(''); continue; }
      if (/^(?:[A-Z][A-Za-z0-9'’_-]{0,20})(?: [A-Z][A-Za-z0-9'’_-]{0,20}){0,3}$/.test(line) && index + 1 < lines.length) continue;
      cleaned.push(raw.replace(/^\s*(?:You|Partner|(?:[A-Z][A-Za-z0-9'’_-]{0,20})(?: [A-Z][A-Za-z0-9'’_-]{0,20}){0,3})\s*:\s*/, ''));
    }
    return cleaned.join('\n').replace(/\n{3,}/g, '\n\n').trim();
  }

  function readablePartText(part) {
    const sceneText = stripReadableSpeakerPrefixes(trimValue(part.scene_text));
    if (sceneText) return sceneText;
    const transcript = Array.isArray(part.transcript) ? part.transcript : [];
    if (!transcript.length) return '';
    return transcript.map(entry => stripReadableSpeakerPrefixes(trimValue(entry.content))).filter(Boolean).join('\n\n').trim();
  }

  function paragraphBlocksFromPart(part) {
    const readableText = readablePartText(part);
    if (!readableText) return [];
    return readableText.split(/\n\n+/).map(block => block.trim()).filter(Boolean);
  }

  function buildReaderHeader(story) {
    const root = storyEl('roleplay-story-reader-header');
    if (!root) return;
    root.innerHTML = '';
    if (!story) {
      root.textContent = 'No story loaded.';
      return;
    }
    const wrap = document.createElement('div');
    wrap.style.display = 'grid';
    wrap.style.gridTemplateColumns = 'minmax(140px, 220px) 1fr';
    wrap.style.gap = '18px';
    wrap.style.alignItems = 'start';

    const coverCard = document.createElement('div');
    coverCard.style.border = '1px solid rgba(255,255,255,0.08)';
    coverCard.style.borderRadius = '16px';
    coverCard.style.padding = '10px';
    coverCard.style.background = 'rgba(255,255,255,0.02)';

    const coverUrl = assetUrl(story.cover?.image_path || story.cover_image_path || '');
    if (coverUrl) {
      const img = document.createElement('img');
      img.src = coverUrl;
      img.alt = `${story.title || 'Story'} cover`;
      img.style.width = '100%';
      img.style.display = 'block';
      img.style.borderRadius = '12px';
      img.style.objectFit = 'cover';
      coverCard.appendChild(img);
    } else {
      const empty = document.createElement('div');
      empty.style.minHeight = '180px';
      empty.style.display = 'flex';
      empty.style.alignItems = 'center';
      empty.style.justifyContent = 'center';
      empty.style.borderRadius = '12px';
      empty.style.background = 'rgba(255,255,255,0.04)';
      empty.style.fontSize = '34px';
      empty.textContent = storyThumbLabel(story);
      coverCard.appendChild(empty);
    }

    const copy = document.createElement('div');
    const title = document.createElement('h2');
    title.textContent = story.title || 'Untitled story';
    title.style.margin = '0';
    title.style.fontSize = '1.65rem';
    const summary = document.createElement('p');
    summary.textContent = story.summary || 'No story summary yet.';
    summary.style.margin = '10px 0 0';
    summary.style.lineHeight = '1.7';
    summary.style.maxWidth = '70ch';
    copy.appendChild(title);
    copy.appendChild(summary);
    [
      createReaderMetaRow('Universe', story.universe_label),
      createReaderMetaRow('World', story.world_label),
      createReaderMetaRow('Cast', (story.lead_character_names || []).join(', ')),
      createReaderMetaRow('Mode', (story.story_mode || 'linear') === 'branching' ? 'Branching' : 'Linear'),
      createReaderMetaRow('Status', story.meta?.status || story.status || ''),
      createReaderMetaRow('Parts', String((story.part_ids || []).length || readerState.parts.length || 0)),
    ].filter(Boolean).forEach(node => copy.appendChild(node));

    wrap.append(coverCard, copy);
    root.appendChild(wrap);
    if (storyEl('roleplay-story-reader-badge')) storyEl('roleplay-story-reader-badge').textContent = story.title || 'Reader mode';
  }

  function scrollReaderToPart(index, behavior = 'smooth') {
    const parts = readerState.parts || [];
    if (!parts.length) return;
    const safeIndex = Math.max(0, Math.min(index, parts.length - 1));
    readerState.currentPartIndex = safeIndex;
    const target = storyEl('roleplay-story-reader-scroll')?.querySelector(`[data-reader-part-index="${safeIndex}"]`);
    if (target) target.scrollIntoView({ block: 'start', behavior });
    if (storyEl('roleplay-story-reader-part-select')) storyEl('roleplay-story-reader-part-select').value = String(safeIndex);
    const tocButtons = storyEl('roleplay-story-reader-toc')?.querySelectorAll('[data-reader-toc-index]') || [];
    tocButtons.forEach(btn => { btn.classList.toggle('btn-primary', Number(btn.dataset.readerTocIndex || -1) === safeIndex); });
  }

  function renderReaderToc(parts) {
    const root = storyEl('roleplay-story-reader-toc');
    if (!root) return;
    root.innerHTML = '';
    if (!parts.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.textContent = 'No saved parts yet for reader mode.';
      root.appendChild(empty);
      return;
    }
    const label = document.createElement('div');
    label.className = 'mini-note';
    label.style.marginBottom = '10px';
    label.textContent = 'Chapter navigation';
    root.appendChild(label);
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.flexWrap = 'wrap';
    row.style.gap = '8px';
    parts.forEach((part, index) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn btn-small${index === readerState.currentPartIndex ? ' btn-primary' : ''}`;
      btn.dataset.readerTocIndex = String(index);
      btn.textContent = part.title || `Part ${index + 1}`;
      btn.addEventListener('click', () => scrollReaderToPart(index));
      row.appendChild(btn);
    });
    root.appendChild(row);
  }

  function renderReaderBody(parts) {
    const root = storyEl('roleplay-story-reader-scroll');
    if (!root) return;
    root.innerHTML = '';
    if (!parts.length) {
      const empty = document.createElement('div');
      empty.className = 'muted small';
      empty.textContent = 'No saved parts yet.';
      root.appendChild(empty);
      return;
    }
    parts.forEach((part, index) => {
      const section = document.createElement('article');
      section.dataset.readerPartIndex = String(index);
      section.style.padding = index === 0 ? '0 0 28px' : '28px 0';
      section.style.borderTop = index === 0 ? 'none' : '1px solid rgba(255,255,255,0.08)';
      section.style.maxWidth = '78ch';
      section.style.margin = '0 auto';

      const title = document.createElement('h3');
      title.textContent = part.title || `Part ${index + 1}`;
      title.style.margin = '0';
      title.style.fontSize = '1.35rem';
      section.appendChild(title);

      const meta = document.createElement('div');
      meta.className = 'muted small';
      meta.style.marginTop = '8px';
      meta.textContent = formatPartMeta(part);
      section.appendChild(meta);

      if (trimValue(part.summary)) {
        const summary = document.createElement('p');
        summary.textContent = part.summary;
        summary.style.marginTop = '14px';
        summary.style.lineHeight = '1.8';
        summary.style.fontStyle = 'italic';
        section.appendChild(summary);
      }

      if (trimValue(part.scene_notes)) {
        const notes = document.createElement('div');
        notes.style.marginTop = '16px';
        notes.style.padding = '12px 14px';
        notes.style.borderRadius = '12px';
        notes.style.border = '1px solid rgba(255,255,255,0.08)';
        notes.style.background = 'rgba(255,255,255,0.03)';
        const label = document.createElement('div');
        label.className = 'mini-note';
        label.textContent = 'Scene notes';
        const body = document.createElement('div');
        body.style.marginTop = '6px';
        body.style.lineHeight = '1.7';
        body.textContent = part.scene_notes;
        notes.append(label, body);
        section.appendChild(notes);
      }

      if (trimValue(part.pinned_canon)) {
        const canon = document.createElement('div');
        canon.style.marginTop = '12px';
        canon.style.padding = '12px 14px';
        canon.style.borderRadius = '12px';
        canon.style.border = '1px solid rgba(255,255,255,0.08)';
        canon.style.background = 'rgba(255,255,255,0.02)';
        const label = document.createElement('div');
        label.className = 'mini-note';
        label.textContent = 'Pinned canon';
        const body = document.createElement('div');
        body.style.marginTop = '6px';
        body.style.lineHeight = '1.7';
        body.textContent = part.pinned_canon;
        canon.append(label, body);
        section.appendChild(canon);
      }

      const blocks = paragraphBlocksFromPart(part);
      const prose = document.createElement('div');
      prose.className = 'roleplay-story-reader-prose';
      prose.style.marginTop = '18px';
      prose.style.display = 'grid';
      prose.style.gap = '14px';
      if (!blocks.length) {
        const empty = document.createElement('div');
        empty.className = 'muted small';
        empty.textContent = 'No scene text saved for this part yet.';
        prose.appendChild(empty);
      } else {
        blocks.forEach(block => {
          const paragraph = document.createElement('p');
          paragraph.textContent = block;
          prose.appendChild(paragraph);
        });
      }
      section.appendChild(prose);
      root.appendChild(section);
    });
  }

  function renderReader() {
    buildReaderHeader(readerState.story);
    renderReaderToc(readerState.parts);
    renderReaderBody(readerState.parts);
    const select = storyEl('roleplay-story-reader-part-select');
    if (select) {
      select.innerHTML = '';
      if (!readerState.parts.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No parts';
        select.appendChild(opt);
      } else {
        readerState.parts.forEach((part, index) => {
          const opt = document.createElement('option');
          opt.value = String(index);
          opt.textContent = part.title || `Part ${index + 1}`;
          select.appendChild(opt);
        });
        select.value = String(Math.max(0, Math.min(readerState.currentPartIndex, readerState.parts.length - 1)));
      }
    }
    requestAnimationFrame(() => scrollReaderToPart(readerState.currentPartIndex, 'auto'));
  }

  async function openStoryReader(storyId = '', preferredPartId = '') {
    const cleanStoryId = trimValue(storyId) || trimValue(storyEl('roleplay-story-id')?.value);
    if (!cleanStoryId) {
      setStatus('roleplay-story-status-msg', 'Load or save a story first, then open Reader mode.', 'warn');
      return;
    }
    const payload = await fetchStoryReader(cleanStoryId);
    if ((payload.story?.story_mode || 'linear') === 'branching') {
      await fetchStoryBranchMap(cleanStoryId).catch(() => null);
    }
    readerState.story = payload.story || null;
    readerState.parts = Array.isArray(payload.parts) ? payload.parts : [];
    const preferredIndex = preferredPartId
      ? readerState.parts.findIndex(part => trimValue(part.id) === trimValue(preferredPartId))
      : 0;
    readerState.currentPartIndex = preferredIndex >= 0 ? preferredIndex : 0;
    renderReader();
    setStoryMode('reader');
    setStatus('roleplay-story-reader-status', `Reader loaded: ${readerState.story?.title || 'Story'}`, 'ok');
  }

  function closeStoryReader() {
    setStoryMode('edit');
    setStatus('roleplay-story-reader-status', '');
  }

  async function refreshReaderIfOpen() {
    if (readerState.mode !== 'reader' || !readerState.story?.id) return;
    const currentPartId = readerState.parts?.[readerState.currentPartIndex]?.id || '';
    await openStoryReader(readerState.story.id, currentPartId).catch(() => {});
  }

  function renderPartList(parts, storyId) {
    const wrap = document.createElement('div');
    wrap.className = 'roleplay-story-parts';
    if (!parts.length) {
      const empty = document.createElement('div');
      empty.className = 'roleplay-story-part-empty';
      empty.textContent = 'No saved parts yet.';
      wrap.appendChild(empty);
      return wrap;
    }
    parts.forEach(part => {
      const row = document.createElement('div');
      row.className = 'roleplay-story-part-row';
      const info = document.createElement('div');
      info.className = 'roleplay-story-part-copy';
      const title = document.createElement('strong');
      title.textContent = part.title || 'Untitled part';
      const meta = document.createElement('div');
      meta.className = 'roleplay-story-part-meta';
      meta.textContent = formatPartMeta(part);
      info.append(title, meta);
      const actions = document.createElement('div');
      actions.className = 'roleplay-story-part-actions';

      const readBtn = document.createElement('button');
      readBtn.className = 'btn btn-small';
      readBtn.type = 'button';
      readBtn.textContent = 'Read';
      readBtn.addEventListener('click', () => openStoryReader(storyId, part.id).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not open reader mode.', 'warn')));

      const loadBtn = document.createElement('button');
      loadBtn.className = 'btn btn-small';
      loadBtn.type = 'button';
      loadBtn.textContent = 'Replay';
      loadBtn.addEventListener('click', () => replayCheckpoint(storyId, part.id, part.title || 'checkpoint').catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not replay this checkpoint.', 'warn')));

      const editBtn = document.createElement('button');
      editBtn.className = 'btn btn-small';
      editBtn.type = 'button';
      editBtn.textContent = 'Edit';
      editBtn.addEventListener('click', () => {
        setStoryMode('edit');
        openPartEditor(part.id).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not open part editor.', 'warn'));
      });

      const branchBtn = document.createElement('button');
      branchBtn.className = 'btn btn-small';
      branchBtn.type = 'button';
      branchBtn.textContent = 'Alt path';
      branchBtn.addEventListener('click', () => {
        const branchMap = cachedStoryBranchMap(storyId);
        const node = (branchMap?.nodes || []).find(item => trimValue(item.id) === trimValue(part.id));
        createAlternatePathFromCheckpoint(storyId, node || part).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not create alternate path.', 'warn'));
      });

      actions.append(readBtn, loadBtn, editBtn, branchBtn);
      row.append(info, actions);
      wrap.appendChild(row);
    });
    return wrap;
  }


  function renderBranchExplorer(branchMap, storyId) {
    const wrap = document.createElement('div');
    wrap.className = 'panel';
    wrap.style.marginTop = '12px';
    wrap.style.padding = '12px';
    wrap.style.border = '1px solid rgba(255,255,255,0.08)';
    wrap.style.borderRadius = '14px';
    wrap.style.background = 'rgba(255,255,255,0.02)';

    const title = document.createElement('div');
    title.className = 'row-between';
    title.style.gap = '10px';
    title.style.alignItems = 'center';
    title.innerHTML = `<div><strong>Replay / checkpoints</strong><div class="mini-note" style="margin-top:4px;">Explore saved checkpoints, replay from earlier beats, or branch into an alternate path.</div></div>`;
    const badge = document.createElement('div');
    badge.className = 'badge';
    badge.textContent = `${Number(branchMap?.checkpointCount || 0)} checkpoints · ${Number(branchMap?.branchCount || 0)} branches`;
    title.appendChild(badge);
    wrap.appendChild(title);

    const nodes = Array.isArray(branchMap?.nodes) ? branchMap.nodes : [];
    if (!nodes.length) {
      const empty = document.createElement('div');
      empty.className = 'mini-note';
      empty.style.marginTop = '10px';
      empty.textContent = 'No saved checkpoints yet. Save the current scene into parts first.';
      wrap.appendChild(empty);
      return wrap;
    }

    const list = document.createElement('div');
    list.style.display = 'grid';
    list.style.gap = '8px';
    list.style.marginTop = '12px';

    nodes.forEach(node => {
      const row = document.createElement('div');
      row.style.marginLeft = `${Math.max(0, Number(node.depth || 0)) * 18}px`;
      row.style.padding = '10px 12px';
      row.style.borderRadius = '12px';
      row.style.border = '1px solid rgba(255,255,255,0.08)';
      row.style.background = 'rgba(255,255,255,0.02)';

      const head = document.createElement('div');
      head.className = 'row-between';
      head.style.gap = '10px';
      head.style.alignItems = 'flex-start';

      const copy = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = node.title || 'Untitled part';
      const meta = document.createElement('div');
      meta.className = 'mini-note';
      const bits = [];
      bits.push(node.is_root ? 'Start checkpoint' : `Branch: ${trimValue(node.branch_label || 'Alternate path') || 'Alternate path'}`);
      if (node.progression_summary) bits.push(node.progression_summary);
      if (Number(node.choice_history_count || 0)) bits.push(`Choices tracked: ${Number(node.choice_history_count || 0)}`);
      if (Number(node.child_count || 0)) bits.push(`Alt paths: ${Number(node.child_count || 0)}`);
      meta.textContent = bits.join(' · ');
      copy.append(strong, meta);

      const actions = document.createElement('div');
      actions.className = 'row';
      actions.style.gap = '8px';
      actions.style.flexWrap = 'wrap';

      const replayBtn = document.createElement('button');
      replayBtn.type = 'button';
      replayBtn.className = 'btn btn-small';
      replayBtn.textContent = 'Replay here';
      replayBtn.addEventListener('click', () => replayCheckpoint(storyId, node.id, node.title || 'checkpoint').catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not replay this checkpoint.', 'warn')));

      const readBtn = document.createElement('button');
      readBtn.type = 'button';
      readBtn.className = 'btn btn-small';
      readBtn.textContent = 'Read here';
      readBtn.addEventListener('click', () => openStoryReader(storyId, node.id).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not open this checkpoint in reader mode.', 'warn')));

      const altBtn = document.createElement('button');
      altBtn.type = 'button';
      altBtn.className = 'btn btn-small';
      altBtn.textContent = 'Alternate path';
      altBtn.addEventListener('click', () => createAlternatePathFromCheckpoint(storyId, node).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not create an alternate path.', 'warn')));

      actions.append(replayBtn, readBtn, altBtn);
      head.append(copy, actions);
      row.appendChild(head);

      if (Array.isArray(node.latest_options) && node.latest_options.length) {
        const hint = document.createElement('div');
        hint.className = 'mini-note';
        hint.style.marginTop = '8px';
        hint.textContent = `Saved branch options: ${node.latest_options.map(option => trimValue(option.label || option.text)).filter(Boolean).join(' · ')}`;
        row.appendChild(hint);
      }

      list.appendChild(row);
    });

    wrap.appendChild(list);
    return wrap;
  }

  async function renderStoryCards(stories) {
    const root = storyEl('roleplay-story-cards');
    if (!root) return;
    root.innerHTML = '';
    const items = Array.isArray(stories) ? stories : [];
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'muted small';
      empty.style.marginTop = '8px';
      empty.textContent = 'No saved stories yet.';
      root.appendChild(empty);
      return;
    }
    for (const card of items) {
      const node = document.createElement('div');
      node.className = 'roleplay-story-card';
      const thumb = document.createElement('div');
      thumb.className = 'roleplay-story-card-thumb';
      const coverUrl = assetUrl(card.cover_image_path || card.cover_thumb_path || '');
      if (coverUrl) {
        const img = document.createElement('img');
        img.src = coverUrl;
        img.alt = `${card.title || 'Story'} cover`;
        thumb.appendChild(img);
      } else {
        const thumbLabel = document.createElement('span');
        thumbLabel.textContent = storyThumbLabel(card);
        thumb.appendChild(thumbLabel);
      }
      const bodyWrap = document.createElement('div');
      bodyWrap.className = 'roleplay-story-card-body';
      const title = document.createElement('h4');
      title.textContent = card.title || 'Untitled story';
      const summary = document.createElement('p');
      summary.className = 'roleplay-story-card-summary';
      summary.textContent = card.summary || 'No summary yet.';
      const meta = document.createElement('div');
      meta.className = 'roleplay-story-card-meta';
      meta.textContent = formatStoryMeta(card);
      const actions = document.createElement('div');
      actions.className = 'roleplay-story-card-actions';

      const replayStartBtn = document.createElement('button');
      replayStartBtn.className = 'btn btn-small';
      replayStartBtn.type = 'button';
      replayStartBtn.textContent = 'Replay from start';
      replayStartBtn.addEventListener('click', () => replayStoryFromStart(card.id || '').catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not replay from the story start.', 'warn')));

      const readBtn = document.createElement('button');
      readBtn.className = 'btn btn-small';
      readBtn.type = 'button';
      readBtn.textContent = 'Read story';
      readBtn.addEventListener('click', () => openStoryReader(card.id || '').catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not open reader mode.', 'warn')));

      const editBtn = document.createElement('button');
      editBtn.className = 'btn btn-small';
      editBtn.type = 'button';
      editBtn.textContent = 'Edit story';
      editBtn.addEventListener('click', async () => {
        await loadStoryRecord(card.id || '');
        setStoryMode('edit');
        setStatus('roleplay-story-status-msg', `Loaded story: ${card.title || 'Story'}`, 'ok');
      });

      const exportBtn = document.createElement('button');
      exportBtn.className = 'btn btn-small';
      exportBtn.type = 'button';
      exportBtn.textContent = 'Export';
      exportBtn.addEventListener('click', () => triggerStoryExport(card.id || '').catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not export story.', 'warn')));

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-small btn-danger';
      deleteBtn.type = 'button';
      deleteBtn.textContent = 'Delete';
      deleteBtn.addEventListener('click', async () => {
        const form = new FormData();
        form.append('story_id', card.id || '');
        const data = await safeFetchJson('/api/roleplay/story/delete', { method: 'POST', body: form });
        setStatus('roleplay-story-status-msg', data.message || 'Story deleted.', 'ok');
        if (trimValue(storyEl('roleplay-story-id')?.value) === trimValue(card.id)) clearStoryForm();
        if (trimValue(readerState.story?.id) === trimValue(card.id)) closeStoryReader();
        renderStoryCards(data.stories || []);
      });

      const parts = await fetchStoryParts(card.id || '');
      let branchMap = null;
      if ((card.story_mode || 'linear') === 'branching') {
        branchMap = await fetchStoryBranchMap(card.id || '').catch(() => null);
      } else {
        storyBranchMaps.delete(trimValue(card.id || ''));
      }
      actions.append(replayStartBtn, readBtn, editBtn, exportBtn, deleteBtn);
      bodyWrap.append(title, summary, meta, actions);
      bodyWrap.append(renderPartList(parts, card.id || ''));
      if (branchMap) bodyWrap.append(renderBranchExplorer(branchMap, card.id || ''));
      node.append(thumb, bodyWrap);
      root.appendChild(node);
    }
  }

  async function refreshStories() {
    const data = await safeFetchJson('/api/roleplay/stories');
    await renderStoryCards(data.stories || []);
  }

  function storyExportOptions() {
    return {
      exportFormat: trimValue(storyEl('roleplay-story-export-format')?.value) || 'md',
      exportMode: trimValue(storyEl('roleplay-story-export-mode')?.value) || 'readable',
    };
  }

  async function triggerStoryExport(storyId = '', saveCopy = false) {
    const cleanStoryId = trimValue(storyId) || trimValue(storyEl('roleplay-story-id')?.value);
    if (!cleanStoryId) {
      setStatus('roleplay-story-status-msg', 'Load or save a story first, then export it.', 'warn');
      return;
    }
    const { exportFormat, exportMode } = storyExportOptions();
    const url = `/api/roleplay/story/export?story_id=${encodeURIComponent(cleanStoryId)}&export_format=${encodeURIComponent(exportFormat)}&export_mode=${encodeURIComponent(exportMode)}${saveCopy ? '&save_copy=true' : ''}`;
    const response = await fetch(url, { method: 'GET', cache: 'no-store' });
    if (!response.ok) {
      let message = 'Could not export story.';
      try {
        const data = await response.json();
        message = data.error || data.message || message;
      } catch (_) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const header = response.headers.get('Content-Disposition') || '';
    const match = header.match(/filename="([^"]+)"/i);
    const fallbackName = `story_export.${exportFormat}`;
    const filename = match?.[1] || fallbackName;
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    const savedPath = response.headers.get('X-Neo-Export-Path') || '';
    const suffix = savedPath ? ` Saved copy: ${savedPath}` : '';
    setStatus('roleplay-story-status-msg', `Story export ready: ${filename}.${suffix}`, 'ok');
  }


  async function saveStoryCard() {
    const state = storyFormState();
    if (!state.title) {
      setStatus('roleplay-story-status-msg', 'Story title is required.', 'warn');
      return null;
    }
    const form = new FormData();
    Object.entries(state).forEach(([key, value]) => form.append(key, String(value || '')));
    const data = await safeFetchJson('/api/roleplay/story/save', { method: 'POST', body: form });
    applyStoryRecord(data.story || null);
    setStatus('roleplay-story-status-msg', data.message || 'Story saved.', 'ok');
    if (typeof window.neoSetRoleplaySessionLink === 'function') window.neoSetRoleplaySessionLink(data.story?.id || '', trimValue(storyEl('roleplay-part-id')?.value));
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
    return data.story || null;
  }

  async function saveCurrentSceneToPart() {
    let storyId = trimValue(storyEl('roleplay-story-id')?.value);
    if (!storyId && trimValue(storyEl('roleplay-story-title')?.value)) {
      const saved = await saveStoryCard();
      storyId = saved?.id || '';
    }
    if (!storyId) {
      setStatus('roleplay-story-status-msg', 'Save a story card first, then save the scene into a part.', 'warn');
      return;
    }
    if (typeof window.neoGetRoleplaySessionState !== 'function') {
      setStatus('roleplay-story-status-msg', 'Roleplay surface is not ready yet.', 'warn');
      return;
    }
    const form = new FormData();
    const suggestedTitle = typeof window.neoSuggestRoleplayPartTitle === 'function' ? trimValue(window.neoSuggestRoleplayPartTitle()) : '';
    const resolvedPartTitle = trimValue(storyEl('roleplay-part-title')?.value) || suggestedTitle;
    if (storyEl('roleplay-part-title') && resolvedPartTitle) storyEl('roleplay-part-title').value = resolvedPartTitle;
    form.append('story_id', storyId);
    form.append('part_id', trimValue(storyEl('roleplay-part-id')?.value));
    form.append('part_title', resolvedPartTitle);
    form.append('roleplay_state_json', JSON.stringify(window.neoGetRoleplaySessionState() || {}));
    const data = await safeFetchJson('/api/roleplay/session/save-part', { method: 'POST', body: form });
    if (storyEl('roleplay-part-id')) storyEl('roleplay-part-id').value = data.part?.id || '';
    if (typeof window.neoSetRoleplaySessionLink === 'function') window.neoSetRoleplaySessionLink(storyId, data.part?.id || '');
    if (storyEl('roleplay-part-title') && !trimValue(storyEl('roleplay-part-title')?.value)) storyEl('roleplay-part-title').value = data.part?.title || '';
    setStatus('roleplay-story-status-msg', data.message || 'Scene saved into story part.', 'ok');
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
  }

  async function recoverLastDraft() {
    const data = await safeFetchJson('/api/roleplay/session/recover');
    if (typeof window.neoApplyRoleplaySessionState === 'function') window.neoApplyRoleplaySessionState(data.session || {});
    if (storyEl('roleplay-story-id')) storyEl('roleplay-story-id').value = data.session?.story_id || '';
    if (storyEl('roleplay-part-id')) storyEl('roleplay-part-id').value = data.session?.part_id || '';
    if (typeof window.neoSetRoleplaySessionLink === 'function') window.neoSetRoleplaySessionLink(data.session?.story_id || '', data.session?.part_id || '');
    if (storyEl('roleplay-part-title')) storyEl('roleplay-part-title').value = data.session?.part_title || '';
    if (data.session?.story_id) await loadStoryRecord(data.session.story_id).catch(() => {});
    setStatus('roleplay-story-status-msg', data.message || 'Recovered last draft.', 'ok');
  }

  async function savePartEdits() {
    const partId = trimValue(storyEl('roleplay-part-id')?.value);
    if (!partId) {
      setStatus('roleplay-part-editor-status', 'Open a part first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('part_id', partId);
    form.append('title', trimValue(storyEl('roleplay-part-editor-title')?.value));
    form.append('summary', trimValue(storyEl('roleplay-part-editor-summary')?.value));
    form.append('scene_notes', trimValue(storyEl('roleplay-part-editor-scene-notes')?.value));
    form.append('pinned_canon', trimValue(storyEl('roleplay-part-editor-canon')?.value));
    form.append('scene_text', trimValue(storyEl('roleplay-part-editor-text')?.value));
    form.append('linked_context_json', JSON.stringify(readLinkedContext('part')));
    const data = await safeFetchJson('/api/roleplay/part/save', { method: 'POST', body: form });
    if (storyEl('roleplay-part-title')) storyEl('roleplay-part-title').value = data.part?.title || '';
    if (storyEl('roleplay-part-editor-badge')) storyEl('roleplay-part-editor-badge').textContent = data.part?.title || 'Part editor';
    setStatus('roleplay-part-editor-status', data.message || 'Part saved.', 'ok');
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
  }

  async function createPartBranch() {
    const partId = trimValue(storyEl('roleplay-part-id')?.value);
    if (!partId) {
      setStatus('roleplay-part-editor-status', 'Open a part first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('part_id', partId);
    form.append('branch_label', trimValue(storyEl('roleplay-part-branch-label')?.value));
    const data = await safeFetchJson('/api/roleplay/part/branch', { method: 'POST', body: form });
    setStatus('roleplay-part-editor-status', data.message || 'Branch created.', 'ok');
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
  }


  async function importStoryBlueprint() {
    const textInput = storyEl('roleplay-blueprint-text');
    const fileInput = storyEl('roleplay-blueprint-file');
    const file = fileInput?.files?.[0] || null;
    const sourceText = trimValue(textInput?.value || '');
    if (!file && !sourceText) {
      setStatus('roleplay-story-status-msg', 'Paste source text or pick a text file first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('source_kind', trimValue(storyEl('roleplay-blueprint-source-kind')?.value) || 'auto');
    form.append('title', trimValue(storyEl('roleplay-blueprint-title')?.value));
    form.append('source_text', sourceText);
    form.append('status', trimValue(storyEl('roleplay-story-status')?.value) || 'draft');
    form.append('canon_mode', trimValue(storyEl('roleplay-canon-mode')?.value) || 'what_if');
    form.append('output_preset', trimValue(storyEl('roleplay-output-preset')?.value) || 'novel');
    form.append('linked_context_json', JSON.stringify(readLinkedContext('story')));
    form.append('story_mode', trimValue(storyEl('roleplay-story-form-mode')?.value || storyEl('roleplay-story-mode')?.value) || 'linear');
    form.append('branch_option_count', String(Number(storyEl('roleplay-story-form-option-count')?.value || storyEl('roleplay-branch-option-count')?.value || 3)));
    form.append('branch_allow_custom_option', String(String(storyEl('roleplay-story-form-allow-custom')?.value || storyEl('roleplay-branch-allow-custom')?.value || 'true') === 'true'));
    if (file) form.append('file', file);
    const data = await safeFetchJson('/api/roleplay/story/import-blueprint', { method: 'POST', body: form });
    applyStoryRecord(data.story || null);
    setStatus('roleplay-story-status-msg', data.message || 'Story blueprint imported.', 'ok');
    await renderStoryCards(data.stories || []);
    if (textInput) textInput.value = '';
    if (fileInput) fileInput.value = '';
    if (storyEl('roleplay-blueprint-title')) storyEl('roleplay-blueprint-title').value = '';
    if (data.story?.id && data.first_part_id) {
      await loadPartIntoRoleplay(data.story.id, data.first_part_id).catch(() => {});
    }
  }

  async function uploadStoryCover() {
    const storyId = trimValue(storyEl('roleplay-story-id')?.value);
    const fileInput = storyEl('roleplay-story-cover-file');
    const file = fileInput?.files?.[0];
    if (!storyId) {
      setStatus('roleplay-story-status-msg', 'Save the story card first, then upload a cover.', 'warn');
      return;
    }
    if (!file) {
      setStatus('roleplay-story-status-msg', 'Choose a cover image first.', 'warn');
      return;
    }
    const form = new FormData();
    form.append('asset_kind', 'story_cover');
    form.append('record_id', storyId);
    form.append('file', file);
    const data = await safeFetchJson('/api/roleplay/asset/upload', { method: 'POST', body: form, cache: 'no-store' });
    applyStoryRecord(data.record || null);
    setStatus('roleplay-story-status-msg', data.message || 'Story cover uploaded.', 'ok');
    await renderStoryCards(data.stories || []);
    await refreshReaderIfOpen();
    if (fileInput) fileInput.value = '';
  }

  function bindStoryManager() {
    storyEl('btn-roleplay-story-save')?.addEventListener('click', () => saveStoryCard().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not save story.', 'warn')));
    storyEl('btn-roleplay-story-save-part')?.addEventListener('click', () => saveCurrentSceneToPart().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not save scene part.', 'warn')));
    storyEl('btn-roleplay-story-recover')?.addEventListener('click', () => recoverLastDraft().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not recover draft.', 'warn')));
    storyEl('btn-roleplay-story-cover-upload')?.addEventListener('click', () => uploadStoryCover().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not upload cover.', 'warn')));
    storyEl('btn-roleplay-blueprint-import')?.addEventListener('click', () => importStoryBlueprint().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not import story blueprint.', 'warn')));
    storyEl('btn-roleplay-story-clear')?.addEventListener('click', clearStoryForm);
    storyEl('btn-roleplay-story-refresh')?.addEventListener('click', () => refreshStories().catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not refresh stories.', 'warn')));
    storyEl('btn-roleplay-story-export-current')?.addEventListener('click', () => triggerStoryExport('', false).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not export story.', 'warn')));
    storyEl('btn-roleplay-story-export-save-copy')?.addEventListener('click', () => triggerStoryExport('', true).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not export story.', 'warn')));
    storyEl('btn-roleplay-part-save')?.addEventListener('click', () => savePartEdits().catch(err => setStatus('roleplay-part-editor-status', err.message || 'Could not save part.', 'warn')));
    storyEl('btn-roleplay-part-branch')?.addEventListener('click', () => createPartBranch().catch(err => setStatus('roleplay-part-editor-status', err.message || 'Could not create branch.', 'warn')));
    storyEl('btn-roleplay-part-close')?.addEventListener('click', closePartEditor);

    storyEl('btn-roleplay-story-mode-edit')?.addEventListener('click', closeStoryReader);
    storyEl('btn-roleplay-story-open-reader')?.addEventListener('click', () => openStoryReader().catch(err => setStatus('roleplay-story-reader-status', err.message || 'Could not open reader mode.', 'warn')));
    storyEl('btn-roleplay-story-reader-close')?.addEventListener('click', closeStoryReader);
    storyEl('btn-roleplay-story-reader-prev')?.addEventListener('click', () => scrollReaderToPart(readerState.currentPartIndex - 1));
    storyEl('btn-roleplay-story-reader-next')?.addEventListener('click', () => scrollReaderToPart(readerState.currentPartIndex + 1));
    storyEl('btn-roleplay-story-reader-replay-start')?.addEventListener('click', () => {
      const storyId = trimValue(readerState.story?.id || storyEl('roleplay-story-id')?.value || '');
      replayStoryFromStart(storyId).catch(err => setStatus('roleplay-story-reader-status', err.message || 'Could not replay from the story start.', 'warn'));
    });
    storyEl('btn-roleplay-story-reader-replay-current')?.addEventListener('click', () => {
      const storyId = trimValue(readerState.story?.id || storyEl('roleplay-story-id')?.value || '');
      const part = readerState.parts?.[readerState.currentPartIndex];
      if (!storyId || !part?.id) { setStatus('roleplay-story-reader-status', 'Pick a checkpoint first.', 'warn'); return; }
      replayCheckpoint(storyId, part.id, part.title || 'checkpoint').catch(err => setStatus('roleplay-story-reader-status', err.message || 'Could not replay this checkpoint.', 'warn'));
    });
    storyEl('roleplay-story-reader-part-select')?.addEventListener('change', event => scrollReaderToPart(Number(event.target.value || 0)));
    storyEl('btn-roleplay-story-reader-edit-current')?.addEventListener('click', () => {
      const part = readerState.parts?.[readerState.currentPartIndex];
      if (!part?.id) {
        setStatus('roleplay-story-reader-status', 'Pick a story part first.', 'warn');
        return;
      }
      setStoryMode('edit');
      openPartEditor(part.id).catch(err => setStatus('roleplay-story-status-msg', err.message || 'Could not open part editor.', 'warn'));
    });

    refreshStories().catch(() => {});
    setStoryMode('edit');
  }

  window.neoGetRoleplayStoryLinkedContext = function () { return readLinkedContext('story'); };
  window.neoGetRoleplayPartLinkedContext = function () { return readLinkedContext('part'); };
  window.neoSaveCurrentSceneToPart = function () { return saveCurrentSceneToPart(); };
  window.neoGetRoleplayStoryLinkedContextText = function () { return linkedContextSummary(readLinkedContext('story'), 'Story linked context'); };
  window.neoGetRoleplayPartLinkedContextText = function () { return linkedContextSummary(readLinkedContext('part'), 'Part linked context'); };
  window.neoRefreshRoleplayStoryContextSelections = renderLinkedContextSelectors;

  function bindWithLinkedContext() {
    bindStoryManager();
    renderLinkedContextSelectors();
    window.setTimeout(renderLinkedContextSelectors, 250);
  }

  if (document.readyState === 'complete') bindWithLinkedContext();
  else document.addEventListener('DOMContentLoaded', bindWithLinkedContext, { once: true });
})();
