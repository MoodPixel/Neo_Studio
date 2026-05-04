(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-audio-state');
    const classes = Array.from(chip?.classList || []);
    const stateClass = classes.find(name => name.startsWith('state-')) || 'state-offline';
    return stateClass.replace('state-', '');
  }

  function backendTone(state){
    const clean = String(state || 'offline').toLowerCase();
    if (clean === 'connected' || clean === 'busy') return 'success';
    if (clean === 'checking') return 'primary';
    if (clean === 'degraded') return 'warning';
    if (clean === 'error') return 'danger';
    return 'neutral';
  }

  function formatTone(value){
    const clean = String(value || 'wav').toLowerCase();
    if (clean === 'wav') return 'primary';
    if (clean === 'flac') return 'success';
    if (clean === 'mp3') return 'warning';
    return 'neutral';
  }

  function jobTone(value){
    const clean = String(value || 'music').toLowerCase();
    if (clean === 'music') return 'primary';
    if (clean === 'sfx') return 'specialty';
    if (clean === 'ambience') return 'recovery';
    return 'neutral';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function refresh(){
    const backendCard = $('audio-setup-shell-backend-card');
    const formatCard = $('audio-setup-shell-format-card');
    const jobCard = $('audio-setup-shell-job-card');
    const formatBadge = $('audio-format-active-badge');
    const jobBadge = $('audio-job-active-badge');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const formatValue = $('audio-format')?.value || 'wav';
    applyTone(formatCard, formatTone(formatValue), 'ready');
    if (formatBadge) formatBadge.textContent = $('audio-format')?.selectedOptions?.[0]?.textContent?.trim() || 'WAV';

    const jobValue = $('audio-job-type')?.value || 'music';
    applyTone(jobCard, jobTone(jobValue), 'ready');
    if (jobBadge) jobBadge.textContent = $('audio-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Music';
  }

  function bind(){
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-audio-format-changed', refresh);
    document.addEventListener('neo-audio-job-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
