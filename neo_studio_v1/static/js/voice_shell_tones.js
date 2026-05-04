(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-voice-state');
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

  function styleTone(value){
    const clean = String(value || 'clean').toLowerCase();
    if (clean === 'clean') return 'primary';
    if (clean === 'warm') return 'success';
    if (clean === 'character') return 'specialty';
    if (clean === 'ad') return 'warning';
    return 'neutral';
  }

  function jobTone(value){
    const clean = String(value || 'tts').toLowerCase();
    if (clean === 'tts') return 'primary';
    if (clean === 'preview') return 'recovery';
    if (clean === 'pack') return 'specialty';
    return 'neutral';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function refresh(){
    const backendCard = $('voice-setup-shell-backend-card');
    const styleCard = $('voice-setup-shell-style-card');
    const jobCard = $('voice-setup-shell-job-card');
    const styleBadge = $('voice-style-active-badge');
    const jobBadge = $('voice-job-active-badge');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const styleValue = $('voice-style')?.value || 'clean';
    applyTone(styleCard, styleTone(styleValue), 'ready');
    if (styleBadge) styleBadge.textContent = $('voice-style')?.selectedOptions?.[0]?.textContent?.trim() || 'Clean narrator';

    const jobValue = $('voice-job-type')?.value || 'tts';
    applyTone(jobCard, jobTone(jobValue), 'ready');
    if (jobBadge) jobBadge.textContent = $('voice-job-type')?.selectedOptions?.[0]?.textContent?.trim() || 'Text to speech';
  }

  function bind(){
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-voice-style-changed', refresh);
    document.addEventListener('neo-voice-job-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
