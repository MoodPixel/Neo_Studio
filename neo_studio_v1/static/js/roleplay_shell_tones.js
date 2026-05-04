/* Legacy Roleplay V1 shell tone file retained for migration/reference only. Not included in the active index shell. New roleplay shell work belongs in roleplay_v2_shell.js. */
(function(){
  function $(id){ return document.getElementById(id); }

  function currentBackendState(){
    const chip = $('surface-backend-roleplay-state');
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
      note: 'This active text model reads like a standard text-only roleplay lane.'
    };
  }

  function modeTone(value){
    const clean = String(value || 'roleplay').toLowerCase();
    if (clean === 'roleplay') return 'primary';
    if (clean === 'short_story') return 'recovery';
    if (clean === 'novel') return 'specialty';
    if (clean === 'cinematic') return 'warning';
    return 'neutral';
  }

  function applyTone(card, tone, state='ready'){
    if (!card) return;
    card.dataset.uiTone = tone;
    card.dataset.uiState = state;
  }

  function emitModeChange(){
    document.dispatchEvent(new CustomEvent('neo-roleplay-mode-changed', {
      detail: {
        outputPreset: $('roleplay-output-preset')?.value || 'roleplay',
        interactionMode: $('roleplay-interaction-mode')?.value || 'roleplay'
      }
    }));
  }

  function refresh(){
    const backendCard = $('roleplay-setup-shell-backend-card');
    const modelCard = $('roleplay-setup-shell-model-card');
    const modeCard = $('roleplay-setup-shell-mode-card');
    const capabilityBadge = $('roleplay-model-capability-badge');
    const currentLabel = $('roleplay-model-current-label');
    const capabilityNote = $('roleplay-model-capability-note');
    const modeBadge = $('roleplay-mode-active-badge');
    const modeMeta = $('roleplay-mode-meta');

    const backendState = currentBackendState();
    applyTone(backendCard, backendTone(backendState), backendState === 'offline' ? 'idle' : 'ready');

    const modelName = $('model-select')?.selectedOptions?.[0]?.textContent?.trim() || $('model-select')?.value || 'default';
    const capability = resolveModelCapability(modelName);
    applyTone(modelCard, capability.tone, 'ready');
    if (capabilityBadge) capabilityBadge.textContent = capability.label;
    if (currentLabel) currentLabel.textContent = `Current model · ${modelName}`;
    if (capabilityNote) capabilityNote.textContent = `${capability.note} Change the active model in Prompt & Caption if you want a different global text lane.`;

    const outputPreset = $('roleplay-output-preset')?.value || 'roleplay';
    const outputLabel = $('roleplay-output-preset')?.selectedOptions?.[0]?.textContent?.trim() || 'Roleplay';
    const interactionLabel = $('roleplay-interaction-mode')?.selectedOptions?.[0]?.textContent?.trim() || 'Roleplay';
    applyTone(modeCard, modeTone(outputPreset), 'ready');
    if (modeBadge) modeBadge.textContent = outputLabel;
    if (modeMeta) modeMeta.textContent = `Output preset sets the prose lane. Interaction mode is currently ${interactionLabel}.`;
  }

  function bind(){
    $('model-select')?.addEventListener('change', () => refresh());
    $('roleplay-output-preset')?.addEventListener('change', () => { emitModeChange(); refresh(); });
    $('roleplay-interaction-mode')?.addEventListener('change', () => { emitModeChange(); refresh(); });
    $('btn-roleplay-apply-preset')?.addEventListener('click', () => window.setTimeout(() => { emitModeChange(); refresh(); }, 0));
    $('btn-roleplay-open-model-manager')?.addEventListener('click', () => {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('manager');
      if (typeof window.switchManagerSubTab === 'function') window.switchManagerSubTab('prompt');
    });
    refresh();
    document.addEventListener('neo-backend-state', refresh);
    document.addEventListener('neo-manager-model-changed', refresh);
    document.addEventListener('neo-roleplay-mode-changed', refresh);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true });
  else bind();
})();
