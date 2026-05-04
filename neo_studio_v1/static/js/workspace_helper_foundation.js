(function () {
  function node(id) { return window.$ ? $(id) : document.getElementById(id); }
  function val(id) { return node(id)?.value?.toString?.().trim?.() || ''; }
  function selectText(id) {
    const el = node(id);
    const opt = el?.options?.[el.selectedIndex];
    return opt ? String(opt.textContent || '').trim() : '';
  }
  function setHelperStatus(id, text, level = '') {
    if (typeof window.setStatus === 'function') window.setStatus(id, text, level);
  }

  function resolveSurfaceLabel(surfaceId, fallback = '') {
    const target = String(surfaceId || '').trim();
    if (!target) return fallback || '';
    const registryLabel = window.NeoSurfaceRegistry?.getSurface?.(target)?.label;
    if (registryLabel) return String(registryLabel);
    const bootRows = Array.isArray(window.NEO_STUDIO_BOOT?.surfaceDefinitions) ? window.NEO_STUDIO_BOOT.surfaceDefinitions : [];
    const bootRow = bootRows.find(row => String(row?.id || '') === target);
    if (bootRow?.label) return String(bootRow.label);
    return fallback || target;
  }

  const ACTIONS = {
    brainstorm: { label: 'Brainstorm', instruction: 'Offer multiple strong directions before locking into one.' },
    improve: { label: 'Improve', instruction: 'Strengthen the current setup without throwing away what is already working.' },
    explain: { label: 'Explain current setup', instruction: 'Explain what the current setup is doing, why it may be working, and where the pressure points are.' },
    rewrite: { label: 'Rewrite', instruction: 'Rewrite the current material into a cleaner, stronger version while respecting the original intent.' },
    troubleshoot: { label: 'Troubleshoot', instruction: 'Diagnose likely weak points, contradictions, or workflow mistakes before suggesting fixes.' },
  };

  const HELPERS = {
    generation: {
      label: `${resolveSurfaceLabel('generate', 'Image')} helper`,
      mode: 'creative',
      workspace: 'generation',
      targetId: 'generation-helper-target',
      actionId: 'generation-helper-action',
      promptId: 'generation-helper-prompt',
      previewId: 'generation-helper-context-preview',
      noteId: 'generation-helper-note',
      statusId: 'generation-helper-status',
      refreshBtnId: 'btn-generation-helper-refresh',
      openBtnId: 'btn-generation-helper-open-assistant',
      applyBtnId: 'btn-generation-helper-apply-last',
      applyOpenBtnId: 'btn-generation-helper-apply-open',
      targets: {
        prompt_direction: { label: 'Prompt direction', instruction: 'Help shape, focus, or expand the main generation prompt direction.' },
        settings_tune: { label: 'Settings tune', instruction: 'Use the current generation settings to suggest cleaner defaults, safer tweaks, or better matching values.' },
        workflow_debug: { label: 'Workflow / debug', instruction: 'Look for mismatched workflow settings, unnecessary complexity, or likely quality blockers.' },
        variation_ideas: { label: 'Variation ideas', instruction: 'Suggest multiple new directions or variations that still fit the current generation context.' },
      },
      collectContext() {
        const lines = [];
        const positive = val('generation-positive');
        const negative = val('generation-negative');
        const sizePreset = selectText('generation-size-preset');
        const width = val('generation-width');
        const height = val('generation-height');
        const steps = val('generation-steps');
        const cfg = val('generation-cfg');
        const seed = val('generation-seed');
        if (positive) lines.push(`Positive prompt: ${positive}`);
        if (negative) lines.push(`Negative prompt: ${negative}`);
        if (sizePreset) lines.push(`Size preset: ${sizePreset}`);
        if (width || height) lines.push(`Canvas: ${width || '?'} × ${height || '?'}`);
        if (steps) lines.push(`Steps: ${steps}`);
        if (cfg) lines.push(`CFG: ${cfg}`);
        if (seed) lines.push(`Seed: ${seed}`);
        return lines.join('\n') || `(${resolveSurfaceLabel('generate', 'Image')} workspace is still mostly empty.)`;
      },
    },
    prompt: {
      label: 'Prompt helper',
      mode: 'writing',
      workspace: 'prompt',
      targetId: 'prompt-helper-target',
      actionId: 'prompt-helper-action',
      promptId: 'prompt-helper-prompt',
      previewId: 'prompt-helper-context-preview',
      noteId: 'prompt-helper-note',
      statusId: 'prompt-helper-status',
      refreshBtnId: 'btn-prompt-helper-refresh',
      openBtnId: 'btn-prompt-helper-open-assistant',
      applyBtnId: 'btn-prompt-helper-apply-last',
      applyOpenBtnId: 'btn-prompt-helper-apply-open',
      targets: {
        prompt_draft: { label: 'Prompt draft', instruction: 'Help draft, expand, or clean the working prompt text.' },
        style_convert: { label: 'Style convert', instruction: 'Convert the prompt into a stronger style while respecting the original concept.' },
        preset_cleanup: { label: 'Preset cleanup', instruction: 'Use the current preset and custom rules to tighten, simplify, or clean the prompt setup.' },
        prompt_debug: { label: 'Prompt / QA', instruction: 'Look for contradictions, weak phrasing, repetition, or formatting issues in the prompt workflow.' },
      },
      collectContext() {
        const lines = [];
        const idea = val('prompt-idea');
        const output = val('prompt-output');
        const preset = selectText('prompt-preset');
        const style = selectText('prompt-style');
        const custom = val('prompt-custom');
        const maxTokens = val('prompt-max-tokens');
        const temperature = val('prompt-temperature');
        const topP = val('prompt-top-p');
        const topK = val('prompt-top-k');
        if (idea) lines.push(`Idea / source prompt: ${idea}`);
        if (output) lines.push(`Current prompt output: ${output}`);
        if (preset) lines.push(`Preset: ${preset}`);
        if (style) lines.push(`Prompt style: ${style}`);
        if (custom) lines.push(`Custom instructions: ${custom}`);
        if (maxTokens) lines.push(`Max tokens: ${maxTokens}`);
        if (temperature || topP || topK) lines.push(`Sampling: temp ${temperature || '?'} · top-p ${topP || '?'} · top-k ${topK || '?'}`);
        return lines.join('\n') || '(Prompt Studio is still mostly empty.)';
      },
    },
    caption: {
      label: 'Caption helper',
      mode: 'writing',
      workspace: 'caption',
      targetId: 'caption-helper-target',
      actionId: 'caption-helper-action',
      promptId: 'caption-helper-prompt',
      previewId: 'caption-helper-context-preview',
      noteId: 'caption-helper-note',
      statusId: 'caption-helper-status',
      refreshBtnId: 'btn-caption-helper-refresh',
      openBtnId: 'btn-caption-helper-open-assistant',
      applyBtnId: 'btn-caption-helper-apply-last',
      applyOpenBtnId: 'btn-caption-helper-apply-open',
      targets: {
        caption_draft: { label: 'Caption draft', instruction: 'Help draft or strengthen the main caption text from the current Studio state.' },
        platform_rewrite: { label: 'Platform rewrite', instruction: 'Adapt the caption for a different platform, audience, or tone while keeping the core idea.' },
        caption_cleanup: { label: 'Caption cleanup', instruction: 'Tighten and simplify the current caption output without flattening the useful visual information.' },
        caption_debug: { label: 'Caption / batch QA', instruction: 'Look for messy output, batch issues, weak settings, or mismatches between the input and current caption setup.' },
      },
      collectContext() {
        const lines = [];
        const fileName = node('caption-image')?.files?.[0]?.name || '';
        const output = val('caption-output');
        const preset = selectText('caption-preset');
        const style = selectText('caption-style');
        const length = selectText('caption-length');
        const outputStyle = selectText('caption-output-style');
        if (fileName) lines.push(`Image file: ${fileName}`);
        if (output) lines.push(`Current caption output: ${output}`);
        if (preset) lines.push(`Preset: ${preset}`);
        if (style) lines.push(`Prompt style: ${style}`);
        if (length) lines.push(`Caption length: ${length}`);
        if (outputStyle) lines.push(`Output style: ${outputStyle}`);
        return lines.join('\n') || '(Caption Studio is still mostly empty.)';
      },
    },
  };


  function switchToWorkspace(workspace) {
    if (workspace === 'generation') {
      if (typeof switchTab === 'function') switchTab('generate');
      return;
    }
    if (workspace === 'prompt') {
      if (typeof switchTab === 'function') switchTab('prompt');
      if (typeof switchManagerSubTab === 'function') switchManagerSubTab('prompt');
      return;
    }
    if (workspace === 'caption') {
      if (typeof switchTab === 'function') switchTab('prompt');
      if (typeof switchManagerSubTab === 'function') switchManagerSubTab('caption');
    }
  }

  function setFieldValue(id, value) {
    const el = node(id);
    if (!el || value === undefined || value === null) return false;
    const next = String(value).trim();
    if (!next) return false;
    el.value = next;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  function escRegex(value) {
    return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function repairJsonCandidate(candidate) {
    let next = String(candidate || '').trim();
    if (!next) return '';
    next = next
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .replace(/^[`]+|[`]+$/g, '')
      .replace(/^json\s*/i, '')
      .replace(/\/\/.*$/gm, '')
      .replace(/,\s*([}\]])/g, '$1')
      .replace(/([{,]\s*)([A-Za-z0-9_\- ]+)(\s*:)/g, (_, lead, key, tail) => `${lead}"${String(key).trim()}"${tail}`)
      .replace(/'([^'\\]*(?:\\.[^'\\]*)*)'\s*:/g, (_, key) => `"${key}" :`)
      .replace(/:\s*'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, value) => `: "${String(value).replace(/\"/g, '\\\"')}"`)
      .trim();
    return next;
  }

  function normalizeJsonObject(data) {
    if (!data || typeof data !== 'object') return null;
    const out = Array.isArray(data) ? {} : {};
    if (Array.isArray(data)) {
      out.items = data.map(item => String(item || '').trim()).filter(Boolean).join('\n');
      return out;
    }
    Object.entries(data).forEach(([key, value]) => {
      const cleanKey = String(key || '').trim().toLowerCase();
      if (!cleanKey) return;
      if (Array.isArray(value)) out[cleanKey] = value.map(item => String(item || '').trim()).filter(Boolean).join('\n');
      else if (value && typeof value === 'object') out[cleanKey] = JSON.stringify(value, null, 2);
      else out[cleanKey] = String(value || '').trim();
    });
    return out;
  }

  function parseJsonBlock(text) {
    const raw = String(text || '');
    const matches = [...raw.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)];
    for (let i = matches.length - 1; i >= 0; i -= 1) {
      const block = String(matches[i]?.[1] || '').trim();
      if (!block) continue;
      try {
        const parsed = normalizeJsonObject(JSON.parse(block));
        if (parsed && typeof parsed === 'object') return { data: parsed, repaired: false };
      } catch (_err) {
        try {
          const repaired = repairJsonCandidate(block);
          const parsed = normalizeJsonObject(JSON.parse(repaired));
          if (parsed && typeof parsed === 'object') return { data: parsed, repaired: true };
        } catch (_err2) {}
      }
    }
    return { data: null, repaired: false };
  }

  function extractSection(text, labels = []) {
    const lines = String(text || '').split(/\r?\n/);
    const escaped = labels.map(escRegex).filter(Boolean);
    if (!escaped.length) return '';
    const startRe = new RegExp(`^(?:#{1,6}\\s*)?(?:${escaped.join('|')})\\s*:\\s*(.*)$`, 'i');
    const nextRe = /^(?:#{1,6}\s*)?[A-Za-z][A-Za-z0-9 /()&+_-]{1,40}\s*:\s*(.*)$/;
    for (let i = 0; i < lines.length; i += 1) {
      const match = lines[i].match(startRe);
      if (!match) continue;
      const out = [];
      if (match[1]) out.push(match[1]);
      for (let j = i + 1; j < lines.length; j += 1) {
        const row = lines[j];
        if (nextRe.test(row)) break;
        out.push(row);
      }
      const joined = out.join('\n').trim();
      if (joined) return joined;
    }
    return '';
  }

  function cleanDraftText(text) {
    return String(text || '')
      .replace(/```(?:json)?[\s\S]*?```/gi, ' ')
      .replace(/\r/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function bestDraftSection(text, labels = []) {
    return extractSection(text, labels) || cleanDraftText(text);
  }

  function applyToGeneration(text, target = '') {
    const parsed = parseJsonBlock(text);
    const changed = [];
    const set = (id, value, label) => { if (setFieldValue(id, value)) changed.push(label); };
    if (parsed.data) {
      set('generation-positive', parsed.data.positive_prompt || parsed.data.positive || parsed.data.prompt || parsed.data.prompt_output, 'positive prompt');
      set('generation-negative', parsed.data.negative_prompt || parsed.data.negative, 'negative prompt');
      set('generation-steps', parsed.data.steps, 'steps');
      set('generation-cfg', parsed.data.cfg || parsed.data.cfg_scale, 'CFG');
      set('generation-seed', parsed.data.seed, 'seed');
      set('generation-width', parsed.data.width, 'width');
      set('generation-height', parsed.data.height, 'height');
    }
    if (!changed.length) {
      const positive = bestDraftSection(text, ['Workspace-aware draft', 'Positive prompt', 'Prompt draft', 'Draft', 'Prompt']);
      const negative = extractSection(text, ['Negative prompt', 'Negative']);
      const steps = extractSection(text, ['Steps']);
      const cfg = extractSection(text, ['CFG', 'CFG scale']);
      const seed = extractSection(text, ['Seed']);
      const width = extractSection(text, ['Width']);
      const height = extractSection(text, ['Height']);
      if (positive && (target === 'prompt_direction' || target === 'variation_ideas' || target === 'settings_tune' || target === 'workflow_debug' || !target)) set('generation-positive', positive, 'positive prompt');
      if (negative) set('generation-negative', negative, 'negative prompt');
      if (steps) set('generation-steps', steps, 'steps');
      if (cfg) set('generation-cfg', cfg, 'CFG');
      if (seed) set('generation-seed', seed, 'seed');
      if (width) set('generation-width', width, 'width');
      if (height) set('generation-height', height, 'height');
    }
    return changed;
  }

  function applyToPrompt(text, _target = '') {
    const parsed = parseJsonBlock(text);
    const changed = [];
    const set = (id, value, label) => { if (setFieldValue(id, value)) changed.push(label); };
    if (parsed.data) {
      set('prompt-idea', parsed.data.idea || parsed.data.source || parsed.data.brief, 'idea');
      set('prompt-output', parsed.data.prompt_output || parsed.data.output || parsed.data.prompt || parsed.data.text, 'prompt output');
      set('prompt-custom', parsed.data.custom || parsed.data.custom_instructions, 'custom instructions');
    }
    if (!changed.length) {
      const output = bestDraftSection(text, ['Workspace-aware draft', 'Prompt output', 'Prompt draft', 'Draft', 'Prompt']);
      const idea = extractSection(text, ['Idea', 'Source idea', 'Concept']);
      const custom = extractSection(text, ['Custom instructions', 'Rules', 'Notes']);
      if (idea) set('prompt-idea', idea, 'idea');
      if (output) set('prompt-output', output, 'prompt output');
      if (custom) set('prompt-custom', custom, 'custom instructions');
    }
    return changed;
  }

  function applyToCaption(text, _target = '') {
    const parsed = parseJsonBlock(text);
    const changed = [];
    const set = (id, value, label) => { if (setFieldValue(id, value)) changed.push(label); };
    if (parsed.data) {
      set('caption-output', parsed.data.caption_output || parsed.data.output || parsed.data.caption || parsed.data.text, 'caption output');
    }
    if (!changed.length) {
      const output = bestDraftSection(text, ['Workspace-aware draft', 'Caption output', 'Caption', 'Draft']);
      if (output) set('caption-output', output, 'caption output');
    }
    return changed;
  }

  function applyAssistantDraftFromText(text, workspace, options = {}) {
    const clean = String(text || '').trim();
    if (!clean) return { ok: false, message: 'No Assistant draft text was found yet.', parseMode: 'fallback', repaired: false, changed: [] };
    const target = String(options.target || '').trim();
    const parsed = parseJsonBlock(clean);
    let changed = [];
    let parseMode = parsed.data ? (parsed.repaired ? 'json_repaired' : 'json') : 'fallback';
    if (workspace === 'generation') {
      changed = applyToGeneration(clean, target);
      if (!changed.length) parseMode = extractSection(clean, ['Workspace-aware draft', 'Positive prompt', 'Prompt draft', 'Draft', 'Prompt', 'Negative prompt']) ? 'sections' : parseMode;
    } else if (workspace === 'prompt') {
      changed = applyToPrompt(clean, target);
      if (!changed.length) parseMode = extractSection(clean, ['Workspace-aware draft', 'Prompt output', 'Prompt draft', 'Draft', 'Prompt', 'Idea']) ? 'sections' : parseMode;
    } else if (workspace === 'caption') {
      changed = applyToCaption(clean, target);
      if (!changed.length) parseMode = extractSection(clean, ['Workspace-aware draft', 'Caption output', 'Caption', 'Draft']) ? 'sections' : parseMode;
    } else {
      return { ok: false, message: 'This workspace does not support helper write-back yet.', parseMode, repaired: !!parsed.repaired, changed: [] };
    }
    if (!changed.length) return { ok: false, message: 'Could not map that Assistant draft into the current workspace fields yet.', parseMode, repaired: !!parsed.repaired, changed: [] };
    if (options.openWorkspace) switchToWorkspace(workspace);
    const parseNote = parseMode === 'json_repaired'
      ? ' Used repaired JSON validation.'
      : parseMode === 'json'
        ? ' Used validated JSON output.'
        : parseMode === 'sections'
          ? ' Used labeled section parsing.'
          : ' Used fallback draft parsing.';
    return {
      ok: true,
      changed,
      parseMode,
      repaired: !!parsed.repaired,
      message: `Applied Assistant draft to ${workspace} (${changed.join(', ')}).${parseNote}`,
    };
  }

  function applyLastAssistantDraft(key, options = {}) {
    const helper = HELPERS[key];
    const api = window.NeoAssistantSurface;
    if (!helper || !api || typeof api.getActiveSession !== 'function') {
      return { ok: false, message: 'Assistant is not ready yet. Open the Assistant tab once and try again.' };
    }
    const session = api.getActiveSession();
    if (!session || String(session?.helper_context?.workspace || '').trim() !== helper.workspace) {
      return { ok: false, message: `Open a ${helper.label.toLowerCase()} thread in Assistant first.` };
    }
    const messages = Array.isArray(session.messages) ? session.messages : [];
    const assistantMessages = messages.filter(item => item && item.role === 'assistant' && String(item.content || '').trim());
    const last = assistantMessages[assistantMessages.length - 1];
    if (!last) return { ok: false, message: 'No Assistant reply was found to apply yet.' };
    return applyAssistantDraftFromText(last.content || '', helper.workspace, {
      openWorkspace: !!options.openWorkspace,
      target: String(session?.helper_context?.target || '').trim(),
    });
  }

  function renderHelperMeta(key) {
    const helper = HELPERS[key];
    if (!helper) return;
    const targetKey = val(helper.targetId) || Object.keys(helper.targets)[0] || '';
    const actionKey = val(helper.actionId) || 'brainstorm';
    const target = helper.targets[targetKey] || Object.values(helper.targets)[0];
    const action = ACTIONS[actionKey] || ACTIONS.brainstorm;
    const preview = node(helper.previewId);
    const note = node(helper.noteId);
    if (preview) preview.value = helper.collectContext();
    if (note) note.textContent = `${target.label}: ${target.instruction} ${action.label}: ${action.instruction}`;
  }

  function buildPacket(key) {
    const helper = HELPERS[key];
    const targetKey = val(helper.targetId) || Object.keys(helper.targets)[0] || '';
    const actionKey = val(helper.actionId) || 'brainstorm';
    const request = val(helper.promptId);
    const context = helper.collectContext();
    const target = helper.targets[targetKey] || Object.values(helper.targets)[0];
    const action = ACTIONS[actionKey] || ACTIONS.brainstorm;
    return {
      title: `${helper.label}`,
      mode: helper.mode,
      thread_instruction: `You are helping inside Neo Studio ${helper.label.replace(' helper', '')}. Stay grounded in the actual workspace context, keep suggestions practical, and make them directly useful inside Neo Studio instead of generic advice.`,
      helper_context: {
        workspace: helper.workspace,
        target: targetKey,
        action: actionKey,
        label: helper.label,
        instruction: `${target.instruction} ${action.instruction}`,
        context_summary: context,
        response_sections: ['Direct recommendation', 'Workspace-aware draft', 'What to change next'],
      },
      composer_text: [
        `I need help with the Neo Studio ${helper.label.toLowerCase()}.`,
        '',
        `Target: ${target.label}`,
        `Action: ${action.label}`,
        `Action guidance: ${action.instruction}`,
        `Workspace focus: ${target.instruction}`,
        '',
        'Current workspace context:',
        context,
        '',
        'My request:',
        request || `Help me with this ${helper.workspace} workspace using the context above.`,
        '',
        'Please give:',
        '1. A direct recommendation',
        '2. A workspace-aware draft or plan',
        '3. A short next-step section',
      ].join('\n'),
      status_message: `${helper.label} opened in Assistant.`,
    };
  }

  async function openInAssistant(key) {
    const api = window.NeoAssistantSurface;
    if (!api || typeof api.startWorkspaceHelperChat !== 'function') {
      setHelperStatus(HELPERS[key].statusId, 'Assistant is not ready yet. Open the Assistant tab once and try again.', 'warn');
      return;
    }
    renderHelperMeta(key);
    setHelperStatus(HELPERS[key].statusId, 'Packaging workspace helper context...', '');
    await api.startWorkspaceHelperChat(buildPacket(key));
    setHelperStatus(HELPERS[key].statusId, `Moved the ${HELPERS[key].label.toLowerCase()} context into Assistant.`, 'ok');
  }

  function bindHelper(key) {
    const helper = HELPERS[key];
    if (!node(helper.targetId)) return;
    [helper.targetId, helper.actionId, helper.promptId].forEach(id => {
      const el = node(id);
      if (!el) return;
      el.addEventListener('input', () => renderHelperMeta(key));
      el.addEventListener('change', () => renderHelperMeta(key));
    });
    // Also watch key workspace fields so preview stays useful.
    ['generation-positive','generation-negative','generation-width','generation-height','generation-steps','generation-cfg','generation-seed','generation-size-preset','prompt-idea','prompt-output','prompt-preset','prompt-style','prompt-custom','prompt-max-tokens','prompt-temperature','prompt-top-p','prompt-top-k','caption-image','caption-output','caption-preset','caption-style','caption-length','caption-output-style'].forEach(id => {
      const el = node(id);
      if (!el) return;
      el.addEventListener('input', () => renderHelperMeta(key));
      el.addEventListener('change', () => renderHelperMeta(key));
    });
    node(helper.refreshBtnId)?.addEventListener('click', () => {
      renderHelperMeta(key);
      setHelperStatus(helper.statusId, 'Context preview refreshed.', 'ok');
    });
    node(helper.openBtnId)?.addEventListener('click', () => {
      openInAssistant(key).catch(err => setHelperStatus(helper.statusId, err.message || `Could not open the ${helper.label.toLowerCase()} in Assistant.`, 'warn'));
    });
    node(helper.applyBtnId)?.addEventListener('click', () => {
      const result = applyLastAssistantDraft(key, { openWorkspace: false });
      setHelperStatus(helper.statusId, result.message, result.ok ? 'ok' : 'warn');
    });
    node(helper.applyOpenBtnId)?.addEventListener('click', () => {
      const result = applyLastAssistantDraft(key, { openWorkspace: true });
      setHelperStatus(helper.statusId, result.message, result.ok ? 'ok' : 'warn');
    });
    renderHelperMeta(key);
  }

  function bindAll() {
    Object.keys(HELPERS).forEach(bindHelper);
  }

  window.NeoWorkspaceHelperBridge = {
    applyAssistantDraftFromText,
    applyLastAssistantDraft,
    switchToWorkspace,
  };

  if (document.readyState === 'complete' || document.readyState === 'interactive') bindAll();
  else document.addEventListener('DOMContentLoaded', bindAll, { once: true });
})();
