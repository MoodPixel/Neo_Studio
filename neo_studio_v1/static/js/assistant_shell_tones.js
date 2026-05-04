(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-assistant-state');
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

  function resolveModelCapability(modelName){
    const clean = String(modelName || '').trim().toLowerCase();
    const visionHints = ['vision', 'vl', 'llava', 'qwen2.5-vl', 'qwen-vl', 'pixtral', 'molmo', 'omni', 'multimodal'];
    const isVision = visionHints.some(hint => clean.includes(hint));
    if (isVision) {
      return {
        label: 'Vision-capable',
        tone: 'specialty',
        note: 'This active text model looks image-aware or multimodal.'
      };
    }
    return {
      label: 'Text-only',
      tone: 'primary',
      note: 'This active text model reads like a standard text-only assistant lane.'
    };
  }

  function modeTone(value){
    const clean = String(value || 'general').toLowerCase();
    if (clean === 'general') return 'primary';
    if (clean === 'support') return 'success';
    if (clean === 'creative') return 'specialty';
    if (clean === 'analysis') return 'recovery';
    if (clean === 'system') return 'warning';
    return 'primary';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function emitModeChange(){
    document.dispatchEvent(new CustomEvent('neo-assistant-mode-changed', {
      detail: {
        mode: $('assistant-mode')?.value || 'general',
        project: $('assistant-project-select')?.value || ''
      }
    }));
  }

  function refresh(){
    const backendCard = $('assistant-setup-shell-backend-card');
    const modelCard = $('assistant-setup-shell-model-card');
    const modeCard = $('assistant-setup-shell-mode-card');
    const capabilityBadge = $('assistant-model-capability-badge');
    const capabilityNote = $('assistant-model-capability-note');
    const modeBadge = $('assistant-mode-active-badge');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const modelName = $('assistant-active-model')?.textContent?.trim() || (typeof currentModel === 'function' ? currentModel() : 'default');
    const capability = resolveModelCapability(modelName);
    applyTone(modelCard, capability.tone, 'ready');
    if (capabilityBadge) capabilityBadge.textContent = capability.label;
    if (capabilityNote) capabilityNote.textContent = `${capability.note} Change the shared text model in Prompt & Caption if you want a different assistant lane.`;

    const modeValue = $('assistant-mode')?.value || 'general';
    const modeLabel = $('assistant-mode')?.selectedOptions?.[0]?.textContent?.trim() || 'General';
    applyTone(modeCard, modeTone(modeValue), 'ready');
    if (modeBadge) modeBadge.textContent = modeLabel;
  }

  function bind(){
    $('model-select')?.addEventListener('change', () => {
      document.dispatchEvent(new CustomEvent('neo-manager-model-changed', { detail: { value: $('model-select')?.value || '', label: $('model-select')?.selectedOptions?.[0]?.textContent?.trim() || '' } }));
      refresh();
    });
    $('assistant-mode')?.addEventListener('change', () => { emitModeChange(); refresh(); });
    $('assistant-project-select')?.addEventListener('change', () => { emitModeChange(); refresh(); });
    $('btn-assistant-open-model-manager')?.addEventListener('click', () => {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('manager');
      if (typeof window.switchManagerSubTab === 'function') window.switchManagerSubTab('prompt');
    });
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-manager-model-changed', refresh);
    document.addEventListener('neo-assistant-mode-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
