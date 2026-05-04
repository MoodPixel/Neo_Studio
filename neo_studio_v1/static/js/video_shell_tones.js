(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-video-state');
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

  function profileTone(value){
    const clean = String(value || 'wan22_5b_balanced').toLowerCase();
    if (clean === 'wan22_5b_balanced') return 'primary';
    if (clean === 'wan22_14b_t2v_quality') return 'warning';
    if (clean === 'wan22_14b_i2v_quality') return 'specialty';
    return 'neutral';
  }

  function modeTone(value){
    const clean = String(value || 't2v').toLowerCase();
    if (clean === 't2v') return 'primary';
    if (clean === 'i2v') return 'specialty';
    return 'neutral';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function refresh(){
    const backendCard = $('video-setup-shell-backend-card');
    const profileCard = $('video-setup-shell-profile-card');
    const laneCard = $('video-setup-shell-lane-card');
    const profileLabel = $('video-profile-active-badge');
    const modeLabel = $('video-mode-active-badge');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const profileValue = $('video-profile')?.value || 'wan22_5b_balanced';
    applyTone(profileCard, profileTone(profileValue), 'ready');
    if (profileLabel) profileLabel.textContent = $('video-profile')?.selectedOptions?.[0]?.textContent?.trim() || 'Balanced / Low VRAM';

    const modeValue = $('video-mode')?.value || 't2v';
    applyTone(laneCard, modeTone(modeValue), 'ready');
    if (modeLabel) modeLabel.textContent = $('video-mode')?.selectedOptions?.[0]?.textContent?.trim() || 'Text to Video';
  }

  function bind(){
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-video-profile-changed', refresh);
    document.addEventListener('neo-video-mode-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
  else bind();
})();
