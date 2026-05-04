(function(){
  const K='neo-studio-audio-skeleton-draft';

  function getDraft(){
    try { return JSON.parse(localStorage.getItem(K)||'{}') || {}; }
    catch(_) { return {}; }
  }

  function currentJobValue(){
    return $('audio-job-type')?.value || 'music';
  }

  function currentFormatValue(){
    return $('audio-format')?.value || 'wav';
  }

  function currentJobLabel(){
    return $('audio-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Music';
  }

  function currentFormatLabel(){
    return $('audio-format')?.selectedOptions?.[0]?.textContent?.trim() || 'WAV';
  }

  function emitAudioShellState(){
    document.dispatchEvent(new CustomEvent('neo-audio-format-changed', {
      detail: { value: currentFormatValue(), label: currentFormatLabel() }
    }));
    document.dispatchEvent(new CustomEvent('neo-audio-job-changed', {
      detail: { value: currentJobValue(), label: currentJobLabel() }
    }));
  }

  function restore(){
    const d = getDraft();
    ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => {
      if ($(id) && d[id]) $(id).value = d[id];
    });
    render();
  }

  function render(){
    const job = currentJobValue();
    const len = $('audio-length')?.value || '15';
    const bpm = $('audio-bpm')?.value || '96';
    const mood = $('audio-mood')?.value || '—';
    const format = currentFormatValue();
    const prompt = ($('audio-prompt')?.value || '').trim();
    const notes = ($('audio-notes')?.value || '').trim();
    if ($('audio-surface-summary')) $('audio-surface-summary').textContent = `${job} lane · ${len}s · ${bpm} BPM · ${format.toUpperCase()}`;
    if ($('audio-plan-output')) $('audio-plan-output').value = [
      `Job lane: ${job}`,
      `Length: ${len} sec`,
      `BPM: ${bpm}`,
      `Mood: ${mood}`,
      `Output idea: ${format}`,
      '',
      'Prompt brief:',
      prompt || '(empty)',
      '',
      'Direction notes:',
      notes || '(empty)',
      '',
      'Status: Skeleton only — runtime generation lands in a later phase.'
    ].join('\n');
    emitAudioShellState();
  }

  function save(show=true){
    const payload = {};
    ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => payload[id] = $(id)?.value || '');
    localStorage.setItem(K, JSON.stringify(payload));
    render();
    if (show) setStatus('audio-status','Saved local music / SFX brief draft.','ok');
  }

  function clear(){
    localStorage.removeItem(K);
    ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => {
      if (!$(id)) return;
      if (id === 'audio-job-type') $(id).value = 'music';
      else if (id === 'audio-length') $(id).value = '15';
      else if (id === 'audio-bpm') $(id).value = '96';
      else if (id === 'audio-format') $(id).value = 'wav';
      else $(id).value = '';
    });
    render();
    setStatus('audio-status','Cleared local music / SFX brief draft.','ok');
  }

  function bind(){
    restore();
    ['audio-job-type','audio-length','audio-bpm','audio-mood','audio-format','audio-prompt','audio-notes'].forEach(id => {
      $(id)?.addEventListener('input', render);
      $(id)?.addEventListener('change', render);
    });
    $('btn-audio-save-brief')?.addEventListener('click', () => save(true));
    $('btn-audio-build-summary')?.addEventListener('click', () => { render(); setStatus('audio-status','Built music / SFX planning summary.','ok'); });
    $('btn-audio-clear-brief')?.addEventListener('click', clear);
    $('btn-audio-open-admin')?.addEventListener('click', () => window.switchMainTab?.('admin'));
    $('btn-audio-run-placeholder')?.addEventListener('click', () => setStatus('audio-status','Music / SFX runtime hookup is not connected yet. This phase only builds the surface skeleton.','warn'));
    render();
  }

  window.neoRefreshAudioSurface = render;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
