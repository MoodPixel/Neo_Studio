(function(){
  const K='neo-studio-voice-skeleton-draft';

  function getDraft(){
    try { return JSON.parse(localStorage.getItem(K)||'{}') || {}; }
    catch(_) { return {}; }
  }

  function currentJobValue(){
    return $('voice-job-type')?.value || 'tts';
  }

  function currentStyleValue(){
    return $('voice-style')?.value || 'clean';
  }

  function currentJobLabel(){
    return $('voice-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Text to speech';
  }

  function currentStyleLabel(){
    return $('voice-style')?.selectedOptions?.[0]?.textContent?.trim() || 'Clean narrator';
  }

  function emitVoiceShellState(){
    document.dispatchEvent(new CustomEvent('neo-voice-style-changed', {
      detail: { value: currentStyleValue(), label: currentStyleLabel() }
    }));
    document.dispatchEvent(new CustomEvent('neo-voice-job-changed', {
      detail: { value: currentJobValue(), label: currentJobLabel() }
    }));
  }

  function restore(){
    const d = getDraft();
    ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => {
      if ($(id) && d[id]) $(id).value = d[id];
    });
    render();
  }

  function render(){
    const job = currentJobValue();
    const style = currentStyleValue();
    const lang = $('voice-language')?.value || 'English';
    const speed = $('voice-speed')?.value || '1.0';
    const seed = $('voice-seed')?.value || '—';
    const script = ($('voice-script')?.value || '').trim();
    const notes = ($('voice-notes')?.value || '').trim();
    if ($('voice-surface-summary')) $('voice-surface-summary').textContent = `${job} · ${style} voice · ${lang} · speed ${speed}`;
    if ($('voice-plan-output')) $('voice-plan-output').value = [
      `Job lane: ${job}`,
      `Voice style: ${style}`,
      `Language: ${lang}`,
      `Speed: ${speed}`,
      `Variation seed: ${seed}`,
      '',
      'Script:',
      script || '(empty)',
      '',
      'Direction notes:',
      notes || '(empty)',
      '',
      'Status: Skeleton only — runtime generation lands in a later phase.'
    ].join('\n');
    emitVoiceShellState();
  }

  function save(show=true){
    const payload = {};
    ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => payload[id] = $(id)?.value || '');
    localStorage.setItem(K, JSON.stringify(payload));
    render();
    if (show) setStatus('voice-status', 'Saved local voice brief draft.', 'ok');
  }

  function clear(){
    localStorage.removeItem(K);
    ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => {
      if (!$(id)) return;
      if (id === 'voice-job-type') $(id).value = 'tts';
      else if (id === 'voice-style') $(id).value = 'clean';
      else if (id === 'voice-speed') $(id).value = '1.0';
      else $(id).value = '';
    });
    render();
    setStatus('voice-status', 'Cleared local voice brief draft.', 'ok');
  }

  function bind(){
    restore();
    ['voice-job-type','voice-style','voice-language','voice-speed','voice-seed','voice-script','voice-notes'].forEach(id => {
      $(id)?.addEventListener('input', render);
      $(id)?.addEventListener('change', render);
    });
    $('btn-voice-save-brief')?.addEventListener('click', () => save(true));
    $('btn-voice-build-summary')?.addEventListener('click', () => { render(); setStatus('voice-status', 'Built voice planning summary.', 'ok'); });
    $('btn-voice-clear-brief')?.addEventListener('click', clear);
    $('btn-voice-open-admin')?.addEventListener('click', () => window.switchMainTab?.('admin'));
    $('btn-voice-run-placeholder')?.addEventListener('click', () => setStatus('voice-status', 'Voice runtime hookup is not connected yet. This phase only builds the surface skeleton.', 'warn'));
    render();
  }

  window.neoRefreshVoiceSurface = render;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
