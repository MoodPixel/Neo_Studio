async function refreshSavedCharacters(selectedName='') {
  try {
    const data = await safeFetchJson('/api/character-records');
    fillSavedCharacterEntries(data.entries || [], selectedName || loadedCharacterName);
  } catch (e) {
    setStatus('character-status', e.message, 'error');
  }
}

async function loadSavedCharacter() {
  const name = $('saved-character-name').value || '';
  if (!name) {
    setStatus('character-status', 'Pick a saved character first.', 'warn');
    return;
  }
  try {
    const data = await safeFetchJson(`/api/character-record?name=${encodeURIComponent(name)}`);
    const rec = data.record || {};
    loadedCharacterName = rec.name || name;
    $('character-name').value = rec.name || '';
    $('character-content').value = rec.content || '';
    updateCounter('character-content', 'character-content-counter');
    setStatus('character-status', 'Loaded character.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('character-status', e.message, 'error');
  }
}

async function saveCharacter() {
  const fd = new FormData();
  const name = trim($('character-name').value) || trim($('saved-character-name').value);
  fd.append('name', name);
  fd.append('content', $('character-content').value || '');
  try {
    const data = await safeFetchJson('/api/save-character', { method:'POST', body:fd });
    loadedCharacterName = data.record?.name || name;
    $('character-name').value = loadedCharacterName;
    fillSavedCharacterEntries(data.entries || [], loadedCharacterName);
    setStatus('character-status', data.message || 'Character saved.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('character-status', e.message, 'error');
  }
}

async function deleteCharacter() {
  const name = trim($('saved-character-name').value || $('character-name').value);
  if (!name) {
    setStatus('character-status', 'Pick a saved character first.', 'warn');
    return;
  }
  if (!confirm('Delete the selected character?')) return;
  const fd = new FormData();
  fd.append('name', name);
  try {
    const data = await safeFetchJson('/api/delete-character', { method:'POST', body:fd });
    loadedCharacterName = '';
    $('character-name').value = '';
    $('character-content').value = '';
    updateCounter('character-content', 'character-content-counter');
    fillSavedCharacterEntries(data.entries || [], '');
    setStatus('character-status', data.message || 'Deleted.');
    if (typeof refreshRecentItems === 'function') refreshRecentItems();
  } catch (e) {
    setStatus('character-status', e.message, 'error');
  }
}

async function improveCharacter() {
  if (!requireBackendRole('text', 'character-status', 'Connect a Text Backend first. Character improve uses the active text model.')) return;
  const content = trim($('character-content').value);
  if (!content) {
    setStatus('character-status', 'Nothing to improve yet.', 'warn');
    return;
  }
  const fd = new FormData();
  fd.append('model', currentModel());
  fd.append('content', content);
  fd.append('mode', $('character-improve-mode').value);
  startTimer('character', 'character-elapsed');
  setStatus('character-status', 'Improving character...');
  try {
    const data = await safeFetchJson('/api/improve-character', { method:'POST', body:fd });
    $('character-content').value = data.content || content;
    updateCounter('character-content', 'character-content-counter');
    setStatus('character-status', 'Character updated.');
  } catch (e) {
    setStatus('character-status', e.message, 'error');
  } finally {
    stopTimer('character');
  }
}
