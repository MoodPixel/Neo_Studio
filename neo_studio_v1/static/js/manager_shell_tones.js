(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-manager-state');
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
        note: 'This model name suggests image-aware captioning or multimodal reasoning support.'
      };
    }
    return {
      label: 'Text-only',
      tone: 'primary',
      note: 'This model name reads like a text-only instruction / reasoning lane.'
    };
  }

  function laneTone(lane){
    const clean = String(lane || 'prompt').toLowerCase();
    if (clean === 'prompt') return 'primary';
    if (clean === 'caption') return 'specialty';
    if (clean === 'library') return 'recovery';
    if (clean === 'settings') return 'warning';
    return 'neutral';
  }

  function laneLabel(lane){
    return document.querySelector(`#tab-manager [data-manager-subtab="${lane}"]`)?.textContent?.trim() || 'Prompt Studio';
  }

  function activeLane(){
    return document.querySelector('#tab-manager [data-manager-subtab].active')?.dataset.managerSubtab || 'prompt';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function refresh(){
    const backendCard = $('manager-setup-shell-backend-card');
    const modelCard = $('manager-setup-shell-model-card');
    const laneCard = $('manager-setup-shell-lane-card');
    const capabilityBadge = $('manager-model-capability-badge');
    const capabilityNote = $('manager-model-capability-note');
    const currentLabel = $('manager-model-current-label');
    const laneBadge = $('manager-lane-active-badge');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const modelName = $('model-select')?.selectedOptions?.[0]?.textContent?.trim() || $('model-select')?.value || 'default';
    const capability = resolveModelCapability(modelName);
    applyTone(modelCard, capability.tone, 'ready');
    if (capabilityBadge) capabilityBadge.textContent = capability.label;
    if (capabilityNote) capabilityNote.textContent = `${capability.note} Capability stays heuristic until the backend exposes a direct contract.`;
    if (currentLabel) currentLabel.textContent = `Current model · ${modelName}`;

    const lane = activeLane();
    applyTone(laneCard, laneTone(lane), 'ready');
    if (laneBadge) laneBadge.textContent = laneLabel(lane);
  }

  function bind(){
    const modelSelect = $('model-select');
    modelSelect?.addEventListener('change', () => {
      document.dispatchEvent(new CustomEvent('neo-manager-model-changed', { detail: { value: modelSelect.value || '', label: modelSelect.selectedOptions?.[0]?.textContent?.trim() || modelSelect.value || '' } }));
      refresh();
    });
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-manager-model-changed', refresh);
    document.addEventListener('neo-manager-lane-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
