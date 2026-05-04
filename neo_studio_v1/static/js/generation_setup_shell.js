(function(){
  const KEY = 'neo-generation-setup-shell-open';
  const FAMILY_TONES = {
    sdxl_sd: 'primary',
    flux: 'success',
    qwen_image_edit: 'specialty',
    zimage: 'warning',
  };
  const WORKSPACE_TONES = {
    txt2img: 'primary',
    img2img: 'specialty',
    inpaint: 'warning',
    outpaint: 'recovery',
  };
  const PRESET_TONES = {
    'builtin:create_portrait_safe': 'primary',
    'builtin:create_square_safe': 'primary',
    'builtin:create_landscape_safe': 'primary',
    'builtin:reference_same_face': 'specialty',
    'builtin:reference_same_character': 'specialty',
    'builtin:reference_style_carry': 'specialty',
    'builtin:repair_small_area': 'warning',
    'builtin:repair_face_hands': 'warning',
    'builtin:cleanup_remove_object': 'warning',
    'builtin:cleanup_cut_out_subject': 'warning',
    'builtin:finish_preserve_2x': 'success',
    'builtin:finish_portrait_restore': 'success',
    'builtin:finish_heavy_rescue': 'success',
    'builtin:recover_output_rebuild': 'recovery',
    'builtin:recover_output_inspect': 'recovery',
  };

  function $(id){
    return document.getElementById(id);
  }

  function chip(label, value, tone='neutral') {
    return `<span class="generation-setup-shell-summary-chip" data-ui-tone="${tone}">${label} · ${value}</span>`;
  }

  function currentBackendState(){
    const chip = $('surface-backend-generate-state');
    const classes = Array.from(chip?.classList || []);
    const stateClass = classes.find(name => name.startsWith('state-')) || 'state-offline';
    return stateClass.replace('state-', '');
  }

  function currentFamilyId(){
    return $('generation-family')?.value || document.querySelector('[data-generation-family].active')?.getAttribute('data-generation-family') || 'sdxl_sd';
  }

  function currentFamilyLabel(){
    return $('generation-family-title')?.textContent?.trim()
      || document.querySelector('[data-generation-family].active')?.textContent?.trim()
      || 'No family';
  }

  function currentWorkspaceMode(){
    return $('generation-workflow-type')?.value || document.querySelector('[data-generation-shell-workspace].active')?.getAttribute('data-generation-shell-workspace') || 'txt2img';
  }

  function currentWorkspaceLabel(){
    return document.querySelector('[data-generation-shell-workspace].active')?.textContent?.trim()
      || $('generation-goal-active-badge')?.textContent?.trim()
      || 'Text → Image';
  }

  function currentPresetValue(){
    return String($('generation-shell-snapshot-select')?.value || '').trim();
  }

  function currentPresetLabel(){
    const select = $('generation-shell-snapshot-select');
    const option = select?.selectedOptions?.[0];
    const label = option?.textContent?.trim() || '';
    return label || 'Default workspace';
  }

  function currentPresetTone(){
    const value = currentPresetValue();
    if (!value) return 'neutral';
    return PRESET_TONES[value] || 'primary';
  }

  function renderSummary(){
    const strip = $('generation-setup-shell-summary-strip');
    if (!strip) return;
    const backendState = currentBackendState();
    const backendLabel = $('surface-backend-generate-state')?.textContent?.trim() || 'Offline';
    const familyId = currentFamilyId();
    const workspaceMode = currentWorkspaceMode();
    strip.innerHTML = `
      <span class="generation-setup-shell-summary-label">Current setup</span>
      <span class="backend-chip state-${backendState}">${backendLabel}</span>
      ${chip('Engine', currentFamilyLabel(), FAMILY_TONES[familyId] || 'neutral')}
      ${chip('Workspace', currentWorkspaceLabel(), WORKSPACE_TONES[workspaceMode] || 'neutral')}
      ${chip('Preset', currentPresetLabel(), currentPresetTone())}`;
    const presetBadge = $('generation-preset-active-badge');
    if (presetBadge) presetBadge.textContent = currentPresetLabel();
  }

  function apply(open){
    const header = $('generation-setup-shell-header');
    const content = $('generation-setup-shell-content');
    const panel = document.querySelector('.generation-setup-shell-panel');
    const strip = $('generation-setup-shell-summary-strip');
    const toggleCopy = $('generation-setup-shell-toggle-copy');
    if (!content || !panel) return;
    const isOpen = !!open;
    renderSummary();
    content.style.display = isOpen ? '' : 'none';
    panel.classList.toggle('is-collapsed', !isOpen);
    header?.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    strip?.classList.toggle('hidden', isOpen);
    if (toggleCopy) toggleCopy.textContent = isOpen ? 'Collapse setup' : 'Expand setup';
    try { window.sessionStorage.setItem(KEY, isOpen ? 'true' : 'false'); } catch(_) {}
  }

  function toggle(){
    const content = $('generation-setup-shell-content');
    apply(!!(content && content.style.display === 'none'));
  }

  function bind(){
    const header = $('generation-setup-shell-header');
    const saved = (() => { try { return window.sessionStorage.getItem(KEY); } catch(_) { return null; } })();
    apply(saved === null ? true : saved === 'true');
    header?.addEventListener('click', toggle);
    header?.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggle();
      }
    });
    $('generation-shell-snapshot-select')?.addEventListener('change', renderSummary);
    document.addEventListener('neo-backend-state', () => renderSummary());
    document.addEventListener('neo-generation-family-changed', () => renderSummary());
    document.addEventListener('neo-generation-goal-changed', () => renderSummary());
    document.addEventListener('neo-generation-workspace-changed', () => renderSummary());
    document.addEventListener('neo-generation-preset-changed', () => renderSummary());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
  else bind();
})();
